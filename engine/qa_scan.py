# qa_scan.py : frame scans on the decoded file. Gate 6 flashes to WCAG 2.2 (Q601 general, Q602 red, Q603 the
# extended band), the reviewer's pointers (Q1101 one-frame pops, Q1102 frozen runs, Q1103 unplanned hard cuts,
# Q1104 stalls) and Q1105, the file against the drawn frames. Everything reads the decode contract.Ctx makes once;
# scan_thumbs runs the pointers on thumbs.npy.
import re
from pathlib import Path

import contract as C
import numpy as np

# ---- gate 6: flashes (WCAG 2.2 "general flash and red flash thresholds"; the run accumulator follows EA IRIS) ----

STEP = 0.1  # a general transition moves relative luminance by 10 percent of the maximum (1.0) ...
DARK = 0.8  # ... and the darker of its two states is below 0.80
# a red transition is judged by WCAG 2.2 note 3 alone (one state R/(R+G+B) >= 0.8, the states over 0.2 apart in
# CIE 1976 u'v'); the saturated-red measure (R - G - B) x 320 (IRIS) only has to move by this, to keep noise out
RED_STEP = 1.0
RED_UV = 0.2
MAX_T = 6  # more than 6 transitions (3 flashes) in any 1 s fails
# extended band (IRIS): 4 to 6 transitions in the trailing second, held for 4 s of any 5 s
EXT = (4, 6, 4, 5)
AREA = 0.25  # a flash counts where it covers 25 percent of the frame or of one 10 degree window
# WCAG's reference screen, and the window on it that stands for a 10 degree visual field
VIEW, FIELD = (1024, 768), (341, 256)
# a reversal smaller than this (luminance, red measure) does not end a run: shimmer and noise
HYST = (0.005, 1.0)
CELLS = 48  # flash grid width: a cell is 4x4 pixels of the 192x108 decode
# a state this dark has no stable chromaticity: red against it counts, two such states never do
DARK_Y = 0.005
ALLOW_SLACK = 1.0  # seconds an ALLOW span may miss a flash passage by at either end

# sRGB code value to linear light (the WCAG 2.2 relative luminance formula, 0.04045 knee)
_c = np.arange(256) / 255
LIN = np.where(_c <= 0.04045, _c / 12.92, ((_c + 0.055) / 1.055) ** 2.4)
LIN = LIN.astype(np.float32)
Y_W = np.array([0.2126, 0.7152, 0.0722], np.float32)  # linear RGB to relative luminance
# linear sRGB to CIE XYZ (D65), for u'v'
XYZ = np.array(
    [[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]],
    np.float32,
)


def _lin(x):
    """sRGB-coded values in 0..1 to linear light, for float input."""
    x = np.clip(np.asarray(x, np.float64), 0, 1)
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def _cells(frames, linear, chunk=200):
    """Per cell of a grid about CELLS wide: mean relative luminance, mean red measure and the u'v' of the mean
    colour, each (n, cells), plus the grid (ny, nx). frames are linear-light float RGB (linear=True) or sRGB code
    values; either way the cells average linear light, which adds."""
    n, h, w = frames.shape[:3]
    b = max(1, round(w / CELLS))
    ny, nx = max(1, h // b), max(1, w // b)
    Y = np.empty((n, ny * nx), np.float32)
    R = np.empty_like(Y)
    UV = np.empty((n, ny * nx, 2), np.float32)

    def cell(a):  # block mean over b x b pixels, one cell per column
        s = a.reshape(len(a), ny, b, nx, b).sum(4).sum(2)
        return s.reshape(len(a), -1) / (b * b)

    for i in range(0, n, chunk):
        x = frames[i : i + chunk, : ny * b, : nx * b]
        if linear:
            r, g, bl = (np.asarray(x[..., k], np.float32) for k in range(3))
        else:
            r, g, bl = LIN[x[..., 0]], LIN[x[..., 1]], LIN[x[..., 2]]
        red = r - g - bl  # IRIS: (R - G - B) x 320 where R / (R + G + B) >= 0.8, else 0
        red[(red < 0) | (r < 0.8 * (r + g + bl))] = 0
        col = np.stack([cell(r), cell(g), cell(bl)], -1)  # mean linear colour per cell
        m = len(col)
        Y[i : i + m] = col @ Y_W
        R[i : i + m] = cell(red) * 320
        X, Yc, Z = np.moveaxis(col @ XYZ.T, -1, 0)
        den = X + 15 * Yc + 3 * Z
        with np.errstate(divide="ignore", invalid="ignore"):
            uv = np.stack([4 * X / den, 9 * Yc / den], -1)
        uv[Yc < DARK_Y] = np.nan
        UV[i : i + m] = uv
    return Y, R, UV, (ny, nx)


def _window(grid, aspect):
    """The 10 degree window in cells: WCAG's 341x256 on a 1024x768 view, with the frame fitted into that view.
    16:9 gives a third of the width by 0.44 of the height (64x48 px of the 192x108 decode, 16x12 cells); 9:16
    gives 0.79 of the width by a third of the height."""
    ny, nx = grid
    vw = min(VIEW[0], VIEW[1] * aspect)
    vh = vw / aspect
    wx = min(nx, max(1, round(nx * FIELD[0] / vw)))
    wy = min(ny, max(1, round(ny * FIELD[1] / vh)))
    return wy, wx


def _boxes(grid, win):
    """Every window position, one cell apart: origins [(y, x), ...] and cell indices (positions, cells). Any shape
    covering a quarter of a window then falls inside one; area is still counted in whole 4x4-pixel cells, so a
    flash within a cell of exactly a quarter can go either way."""
    ny, nx = grid
    wy, wx = win
    pos = [(y, x) for y in range(ny - wy + 1) for x in range(nx - wx + 1)]
    cells = np.arange(ny * nx).reshape(ny, nx)
    return pos, np.stack([cells[y : y + wy, x : x + wx].ravel() for y, x in pos])


def _box_means(S, grid, pos, win):
    """(n, positions): the mean of the per-cell series S over each window, from one integral image."""
    n = len(S)
    ny, nx = grid
    wy, wx = win
    cs = np.zeros((n, ny + 1, nx + 1))
    cs[:, 1:, 1:] = S.reshape(n, ny, nx).cumsum(1, dtype=np.float64).cumsum(2)
    y, x = np.array(pos).T
    box = cs[:, y + wy, x + wx] - cs[:, y, x + wx] - cs[:, y + wy, x] + cs[:, y, x]
    return (box / (wy * wx)).astype(np.float32)


def _transitions(M, S, idx, fps, step, hyst, ok):
    """bool (n, windows): the frames where each window completes a transition. The window's mean M splits into
    runs at its extremes (a reversal under hyst does not end a run). A run counts once, as soon as the window's
    cells that moved by step or more in its direction since the run started (over its last second only, as IRIS
    keeps the run) and pass ok(s0, s1, a, f, cells) cover AREA of the window: flashes occurring concurrently.
    Moving edges and texture change their cells out of step, so they do not add up to a flash."""
    n, nw = M.shape
    T = np.zeros((n, nw), bool)
    up = np.ones(nw, bool)  # direction of the current run
    ext = M[0].copy()  # its extreme so far, and the frame of it
    ei = np.zeros(nw, np.int64)
    si = np.zeros(nw, np.int64)  # the frame the run started from
    done = np.zeros(nw, bool)  # this run is counted already
    for f in range(1, n):
        v = M[f]
        rev = np.where(up, ext - v > hyst, v - ext > hyst)
        if rev.any():
            si = np.where(rev, ei, si)
            up ^= rev
            done &= ~rev
        grow = rev | np.where(up, v > ext, v < ext)
        if not grow.any():
            continue
        ext = np.where(grow, v, ext)
        ei = np.where(grow, f, ei)
        c = np.flatnonzero(grow & ~done)
        a = np.maximum(si[c], f - fps)
        # a quarter of the window moving by step moves the mean by at least AREA x step
        keep = np.abs(v[c] - M[a, c]) >= AREA * step
        c, a = c[keep], a[keep]
        if not len(c):
            continue
        cells = idx[c]
        s0, s1 = S[a[:, None], cells], S[f, cells]
        sign = np.where(up[c], 1, -1)[:, None]
        moved = ((s1 - s0) * sign >= step) & ok(s0, s1, a[:, None], f, cells)
        hit = c[moved.mean(1) >= AREA]
        T[f, hit] = True
        done[hit] = True
    return T


def _trailing(M, k):
    """How many True per column in the trailing k frames, the frame itself included."""
    c = np.cumsum(M, 0, dtype=np.int32)
    out = c.copy()
    out[k:] -= c[:-k]
    return out


def _runs(mask):
    """[(first, last), ...] index runs where mask is True."""
    d = np.diff(np.concatenate([[0], np.asarray(mask, np.int8), [0]]))
    return [
        (int(a), int(b))
        for a, b in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1)
    ]


def _passages(bad, k):
    """Index runs covered by the trailing k-frame windows that end on a bad frame: one passage per flashing stretch,
    however often the sliding count dips back under the limit inside it."""
    hot = _trailing(np.asarray(bad)[::-1, None], k)[::-1, 0] > 0
    return _runs(hot)


def _dark(s0, s1, a, f, cells):
    """WCAG: a general flash needs the darker of its two states below 0.80."""
    return np.minimum(s0, s1) < DARK


def flashes(L, fps, linear=False):
    """[(second, flashes)] for every passage over 3 flashes in any sliding 1 s window of a mean series L: mean grey
    0..255 read as sRGB code values (the old callers), or relative luminance 0..1 with linear=True. second is where
    the passage's worst window starts and flashes is transitions / 2 (3.5 means 7). It sees the whole-frame mean
    only, with no area or red test: a band over a third of the frame can flash 4 times a second and return [], so
    an empty list proves nothing. flash_rows on frames (contract.lin_thumb) is the gate."""
    L, fps = np.asarray(L, np.float64).reshape(-1, 1), round(fps)
    if not linear:
        L = _lin(L / 255)
    N = _trailing(
        _transitions(L, L, np.zeros((1, 1), int), fps, STEP, HYST[0], _dark), fps
    )[:, 0]
    out = []
    for a, b in _passages(N > MAX_T, fps):
        f = a + int(np.argmax(N[a : b + 1]))
        out.append((round(max(0, f - fps + 1) / fps, 2), float(N[f] / 2)))
    return out


def _times(x):
    """Every number in x, flattened: CUTS as a set, CUES as a list or the older dict of label -> times."""
    if isinstance(x, dict):
        x = list(x.values())
    if isinstance(x, (int, float, np.number)) and not isinstance(x, bool):
        return [float(x)]
    if isinstance(x, (list, tuple, set, frozenset)):
        return [t for v in x for t in _times(v)]
    return []


def _schedule(scenes):
    """[(name, start, end)] from SCHEDULE: values (start, end, ...) or dicts with start and end."""
    out = []
    for name, v in (getattr(scenes, "SCHEDULE", None) or {}).items():
        if isinstance(v, dict):
            v = (v.get("start", v.get("t0")), v.get("end", v.get("t1")))
        try:
            out.append((str(name), float(v[0]), float(v[1])))
        except (TypeError, ValueError, IndexError):
            continue
    return out


def _scene(scenes, t, fps):
    """The SCHEDULE scene at time t by engine.scene_at's rule: the first span that holds t's nearest frame
    (contract.frame_of on both ends), else the last scene."""
    sched = _schedule(scenes)
    f = C.frame_of(t, fps)
    for s, a, b in sched:
        if C.frame_of(a, fps) <= f < C.frame_of(b, fps):
            return s
    return sched[-1][0] if sched else None


def _allowed_span(scenes, code, a, b, slack):
    """One ALLOW[code] entry holds the whole finding from a to b seconds, give or take slack at either end."""
    for e in (
        (getattr(scenes, "ALLOW", None) or {}).get(code, [])
        if scenes is not None
        else []
    ):
        lo, hi = e if isinstance(e, (tuple, list)) else (e, e)
        if lo - slack <= a and b <= hi + slack:
            return True
    return False


FLASH_FIX = {
    "Q601": "at most 3 flashes a second: fewer flips, a smaller flashing area, a softer swing (under 10 percent "
    "luminance, or both states above 0.8), or stretch each flash over more frames",
    "Q602": "at most 3 saturated-red flips a second: desaturate the red, flip it less often, or shrink it",
    "Q603": "4 to 6 transitions a second held for 4 s: break the passage up or slow it down; list a designed one in "
    "ALLOW['Q603']",
}


def _flash_row(code, kind, N, pos, grid, win, fps, t0, scenes):
    """One row from per-window transition counts N (the last column the whole frame): FIX where any window passes
    MAX_T in a sliding second."""
    K = N.max(1)
    n = len(K)
    worst = int(np.argmax(K))
    peak = float(K[worst] / 2)
    if K[worst] <= MAX_T:
        return C.row(
            True,
            code,
            f"{kind} flashes: worst {peak:g} in any 1 s over a quarter of the frame or a 10 degree window (limit 3)",
            "",
            metric=peak,
            limit=3,
            considered=n,
        )
    spans = [
        (round(t0 + a / fps, 3), round(t0 + b / fps, 3))
        for a, b in _passages(K > MAX_T, fps)
    ]
    wt = round(t0 + max(0, worst - (fps - 1) / 2) / fps, 3)
    j = len(pos) if N[worst, -1] == K[worst] else int(np.argmax(N[worst]))
    if j == len(pos):
        where = "over a quarter of the frame"
    else:
        (y, x), (ny, nx), (wy, wx) = pos[j], grid, win
        where = (
            f"in the 10 degree window at x {100 * x // nx}-{100 * (x + wx) // nx}%, "
            f"y {100 * y // ny}-{100 * (y + wy) // ny}%"
        )
    return C.row(
        False,
        code,
        f"{kind} flashes: {peak:g} in 1 s around {wt:.2f} s {where} (limit 3), {len(spans)} passage(s) over it",
        FLASH_FIX[code],
        t0=spans[0][0],
        t1=spans[-1][1],
        worst_t=wt,
        item=_scene(scenes, wt, fps),
        metric=peak,
        limit=3,
        spans=spans,
        considered=n,
    )


def flash_rows(rgb, fps, aspect=None, t0=0.0, scenes=None, lin=None):
    """Q601 general and Q602 red flashes (FIX) and Q603 the extended band (NOTE, honours ALLOW). Frames: lin, float32
    (n, h, w, 3) linear-light RGB averaged in linear light (contract.Ctx.lin(), contract.lin_thumb), or rgb, uint8
    sRGB code values, which a downscale averaged in code values (sparse lines read dark there). Pass aspect = W / H
    when the frames were squeezed to 192x108; t0 is the time of the first frame. Every 10 degree window position and
    the whole frame count their own transitions (linear luminance, the IRIS run accumulator, a sliding 1 s window);
    a run counts where cells that moved together cover a quarter of the window. Windows are not pooled: two flashes
    in different 10 degree fields are judged apart, as WCAG judges any one field."""
    src = np.asarray(rgb if lin is None else lin)
    fps = round(fps)
    n, h, w = src.shape[:3]
    if n < 2:
        return [
            C.not_checked(
                code, f"{n} frame(s): no flash can be measured", "check the decode"
            )
            for code in ("Q601", "Q602", "Q603")
        ]
    Y, R, UV, grid = _cells(src, lin is not None)
    win = _window(grid, aspect or w / h)
    pos, idx = _boxes(grid, win)
    whole = np.arange(Y.shape[1])[None]

    def hue(s0, s1, a, f, cells):
        """WCAG 2.2 note 3: the two states over 0.2 apart in u'v'. A state too dark for a chromaticity (nan) counts
        against a lit one (red against black), never against another dark one."""
        u0, u1 = UV[a, cells], UV[f, cells]
        d = u0 - u1
        return (np.hypot(d[..., 0], d[..., 1]) > RED_UV) | (
            np.isnan(u0[..., 0]) ^ np.isnan(u1[..., 0])
        )

    rows, ext = [], []
    lo, hi, secs, span = EXT
    for code, kind, S, step, hy, ok in (
        ("Q601", "general", Y, STEP, HYST[0], _dark),
        ("Q602", "red", R, RED_STEP, HYST[1], hue),
    ):
        T = np.concatenate(
            [
                _transitions(_box_means(S, grid, pos, win), S, idx, fps, step, hy, ok),
                _transitions(S.mean(1, keepdims=True), S, whole, fps, step, hy, ok),
            ],
            1,
        )
        N = _trailing(T, fps)
        rows.append(_flash_row(code, kind, N, pos, grid, win, fps, t0, scenes))
        band = (N >= lo) & (N <= hi)
        held_w = (_trailing(band, span * fps) >= secs * fps) & band
        for a, b in _passages(held_w.any(1), span * fps):
            # the passage runs from its first to its last transition in the windows that held the band
            tf = np.flatnonzero(T[a : b + 1][:, held_w[a : b + 1].any(0)].any(1)) + a
            p, q = (int(tf[0]), int(tf[-1])) if len(tf) else (a, b)
            ta, tb = round(t0 + p / fps, 3), round(t0 + q / fps, 3)
            if not _allowed_span(scenes, "Q603", ta, tb, ALLOW_SLACK):
                ext.append((kind, ta, tb))
    if not ext:
        rows.append(
            C.row(
                True,
                "Q603",
                "extended band: no 5 s passage holding 4 to 6 transitions a second for 4 s",
                "",
                considered=n,
            )
        )
    for kind, a, b in ext:
        rows.append(
            C.row(
                False,
                "Q603",
                f"extended band ({kind}): 4 to 6 transitions a second held for 4 s, {a:.2f} to {b:.2f} s",
                FLASH_FIX["Q603"],
                note=True,
                t0=a,
                t1=b,
                worst_t=round((a + b) / 2, 3),
                item=_scene(scenes, (a + b) / 2, fps),
                metric=round(b - a, 2),
                limit=float(secs),
                spans=[(a, b)],
                considered=n,
            )
        )
    return rows


# ---- the reviewer's pointers (Z17): NOTE rows with times, from 192x108 grey (the decode or thumbs.npy) ----
# Calibrated on the five approved films of 2026-10-28 (counts in the lane notes): every threshold below was checked
# against all five and against planted faults.

TILES = 12  # pops are looked for on a 12 x 12 tile grid (anidoodle popscan)
# pop candidate: level, the tile share changed into and out of the frame, the most the across change may be (x the
# smaller)
POP = (4, 0.004, 0.35)
# the across test on each tile's 3x3 tile neighbourhood: moved content lands in a neighbour. 0.5, not the 0.35 of the
# tile test: at 0.35 the real one-frame head twitch in the battle sample (f359) is lost, as its body moves next to it
POP_HOOD = 0.5
# pop strength: the share of all pixels sitting 12 levels off both neighbours where the neighbours agree within 3,
# on lone tiles; a stale 36 px caption for one frame scores 0.0023
STRONG = (12, 3, 0.002)
CONTEXT = 0.25  # a pop tile's steps either side must change under this x its own pop step (still context)
# 3 or more pop frames within 3 frames of each other are one fast mover, not pops
MOVER = (3, 3)
POP_GROUP = 1.0  # pops less than a second apart are one row: a passage of designed accents is one pointer
# whole-frame tag: over 1 percent of pixels 12 levels off both neighbours while the neighbours agree (OVH isoframes)
ISO = (12, 0.01)
# frozen: under 0.2 percent of pixels move over 6 levels, for 3 s or more; a pixel moved when it leaves the 3x3
# range of the other frame by 6 levels, so a whole-picture weave of 1 pixel is not motion
STILL = (6, 0.002, 3.0)
BLACK = (25, 0.02)  # near-black: under 2 percent of pixels above 25/255
TAIL = 2.0  # seconds (plus a frame) of static end card that never counts as frozen (cinetic)
HOLD_SLACK = 2  # frames either side of a registry hold
# hard cut (OVH): share over 12 levels, mean change, and x the median of the 5 frames either side; a dark cut: share
# over 6 levels, mean, x the median; and either must be DOMINANT x its larger neighbouring step
CUT = (12, 0.30, 18, 3.0, 5)
DARK_CUT = (6, 0.30, 6, 4.0)
DOMINANT = 2.0
FLASH_BACK = 3  # a cut answered within 3 frames by a cut back to the picture before it is a flash (Q601's), not a cut
CUT_GROUP = 2  # cut frames this close are one fast transition (a zoom, a whip): one row
# stall: the pixels that move over 4 levels in both neighbouring steps (at least 0.5 percent of the frame) move in
# this step under 5 percent of the time (a planted repeat reads 0.000, designed slow steps on the samples 0.078 and
# up), both neighbouring steps move over 0.8 levels on average, and no other repeat sits within 6 frames (animation
# on twos)
STALL = (4, 0.005, 0.05, 0.8, 6)
STALL_BACK = 0.5  # under this share of those pixels differing between f + 1 and f - 2: a held flash, not a stall
# or a step whose mean change is under this (cinetic): an exact repeat on clean frames, where a hard-edged mover
# leaves no pixel that changes on two steps in a row for the mask to hold
STALL_EXACT = 0.05
MATCH = 4.0  # Q1105: a frame of the file whose mean grey differs from its drawn thumb by more than this is broken
MAX_ROWS = 5  # NOTE rows per scan; the rest fold into one row so a busy film cannot bury the reviewer

SCAN_FIX = {
    "Q1101": "open the f-2..f+2 strip: a stale or missing element for one frame is a draw(t) boundary bug; list a "
    "designed one-frame accent in ALLOW['Q1101']",
    "Q1102": "keep something alive in the hold or end it sooner; list an intended freeze in ALLOW['Q1102']",
    "Q1103": "put the cut on a SCHEDULE start, or add its time to CUTS or CUES; list an intended one in ALLOW['Q1103']",
    "Q1104": "the frame repeats its neighbour inside a move: check stepped or rounded timing there; list a designed "
    "hold in ALLOW['Q1104']",
}


def _range3(a):
    """(lo, hi): the 3x3 minimum and maximum of each (h, w) frame of a, edges padded."""
    p = np.pad(a, ((0, 0), (1, 1), (1, 1)), mode="edge")
    out = []
    for op in (np.minimum, np.maximum):
        x = op(op(p[:, :, :-2], p[:, :, 1:-1]), p[:, :, 2:])
        out.append(op(op(x[:, :-2], x[:, 1:-1]), x[:, 2:]))
    return out


def _stats(g, chunk=240):
    """Per step s (frame s to s + 1): tile shares over the POP level, whole-frame shares over the dark-cut and cut
    levels, the share that left the 3x3 range of frame s (still test), and the mean change. Per frame f (f - 1 to
    f + 1): tile shares across, the share 12 levels off both neighbours (iso), the per-tile share of that where the
    neighbours also agree within 3 (strong), the share across over 12, and the stall mask (the share moving in both
    neighbouring steps, and how much of it moves into f). Per frame: the share above near-black."""
    n, h, w = g.shape
    th, tw = h // TILES, w // TILES
    k = n - 1
    st = {
        "tile": np.zeros((k, TILES, TILES), np.float32),
        "s6": np.zeros(k),
        "s12": np.zeros(k),
        "still": np.zeros(k),
        "mad": np.zeros(k),
        "across": np.zeros((n, TILES, TILES), np.float32),
        "iso": np.zeros(n),
        "strong": np.zeros((n, TILES, TILES), np.float32),
        "acr12": np.zeros(n),
        "mshare": np.zeros(n),
        "mmoved": np.ones(n),
        "lit": (g.reshape(n, -1) > BLACK[0]).mean(1),
    }

    def tiles(m):
        return (
            m[:, : th * TILES, : tw * TILES]
            .reshape(len(m), TILES, th, TILES, tw)
            .mean((2, 4))
        )

    for i in range(0, k, chunk):
        lo = max(0, i - 1)  # one step before the chunk, for the stall mask
        a = g[lo : min(n, i + chunk + 2)].astype(np.int16)  # frames lo ..
        d = np.abs(np.diff(a, axis=0))  # d[q] = step lo + q
        o, j = i - lo, min(chunk, k - i)  # steps i .. i + j - 1 are d[o : o + j]
        dd = d[o : o + j]
        st["tile"][i : i + j] = tiles(dd > POP[0])
        flat = dd.reshape(j, -1)
        st["s6"][i : i + j] = (flat > DARK_CUT[0]).mean(1)
        st["s12"][i : i + j] = (flat > CUT[0]).mean(1)
        st["mad"][i : i + j] = flat.mean(1)
        rlo, rhi = _range3(a[o : o + j])
        nxt = a[o + 1 : o + 1 + j]
        left = (nxt < rlo - STILL[0]) | (nxt > rhi + STILL[0])
        st["still"][i : i + j] = left.reshape(j, -1).mean(1)
        m = min(
            j, len(a) - o - 2
        )  # frames f = i + 1 + q, q < m, with both neighbours here
        if m <= 0:
            continue
        acr = np.abs(a[o + 2 : o + 2 + m] - a[o : o + m])
        dn, up = d[o : o + m], d[o + 1 : o + 1 + m]  # into f, out of f
        st["across"][i + 1 : i + 1 + m] = tiles(acr > POP[0])
        off = (dn > ISO[0]) & (up > ISO[0])
        st["iso"][i + 1 : i + 1 + m] = off.reshape(m, -1).mean(1)
        strong = (dn > STRONG[0]) & (up > STRONG[0]) & (acr <= STRONG[1])
        st["strong"][i + 1 : i + 1 + m] = tiles(strong)
        st["acr12"][i + 1 : i + 1 + m] = (acr > ISO[0]).reshape(m, -1).mean(1)
        q0 = 1 - o  # the first frame here whose step into f - 1 is known
        if m > q0:
            prev = d[o - 1 + q0 : o - 1 + m] > STALL[0]
            mask = prev & (up[q0:] > STALL[0])
            cnt = mask.reshape(len(mask), -1).sum(1)
            moved = (mask & (dn[q0:] > STALL[0])).reshape(len(mask), -1).sum(1)
            st["mshare"][i + 1 + q0 : i + 1 + m] = cnt / mask[0].size
            st["mmoved"][i + 1 + q0 : i + 1 + m] = moved / np.maximum(cnt, 1)
    return st


def _fold(rows, code, what, fps, considered, scenes):
    """Keep the MAX_ROWS strongest rows (by metric), fold the rest into one row that points at the strongest of
    them and lists each one as a span, so every folded moment still reaches review_times.json."""
    if len(rows) <= MAX_ROWS:
        return sorted(rows, key=lambda r: r.worst_t)
    rows = sorted(rows, key=lambda r: -(r.metric or 0))
    keep, rest = rows[:MAX_ROWS], rows[MAX_ROWS:]
    ts = sorted(r.worst_t for r in rest)
    shown = ", ".join(f"{t:.2f}" for t in ts[:12]) + (" ..." if len(ts) > 12 else "")
    top = rest[0]
    extra = C.row(
        False,
        code,
        f"{len(rest)} more {what} at {shown} s",
        SCAN_FIX[code],
        note=True,
        t0=ts[0],
        t1=ts[-1],
        worst_t=top.worst_t,
        item=_scene(scenes, top.worst_t, fps),
        metric=top.metric,
        limit=top.limit,
        spans=[(t, t) for t in ts],
        considered=considered,
    )
    return sorted(keep, key=lambda r: r.worst_t) + [extra]


def _groups(frames, gap):
    """Sorted frame numbers split where two are more than gap frames apart."""
    out = []
    for f in sorted(frames):
        if out and f - out[-1][-1] <= gap:
            out[-1].append(f)
        else:
            out.append([f])
    return out


def _box3(m):
    """Mean over each tile's 3x3 tile neighbourhood, edges padded: (n, 12, 12) -> (n, 12, 12)."""
    p = np.pad(m, ((0, 0), (1, 1), (1, 1)), mode="edge")
    return (
        sum(p[:, i : i + TILES, j : j + TILES] for i in range(3) for j in range(3)) / 9
    )


def _pops(st, n, fps, scenes):
    """Q1101: a frame that changes into and out of itself while its neighbours agree (anidoodle popscan on a 12 x
    12 grid), on the tile and on its 3x3 tile neighbourhood. A tile that also pops on a neighbouring frame is
    alternation (on-ones sprites, a buzz), and one whose own steps either side also change is motion passing
    through (jitter, a blurred zoom, shake); neither is a one-frame event. What is left must be strong enough to
    matter (STRONG), and 3 or more pop frames within 3 frames of each other are a fast mover. Frames listed in ALLOW
    drop out; pops under POP_GROUP apart make one row, pointed at the strongest; tagged whole-frame when over 1
    percent of pixels sit 12 levels off both neighbours (OVH)."""
    share, ratio = POP[1:]
    if n < 3:
        return [], 0
    a, b, c = st["tile"][:-1], st["tile"][1:], st["across"][1:-1]  # frames 1 .. n - 2
    small = np.minimum(a, b)
    tile = (a >= share) & (b >= share) & (c <= ratio * small)
    tile &= _box3(c) <= POP_HOOD * np.minimum(_box3(a), _box3(b))
    alt = np.zeros_like(tile)
    alt[1:] |= tile[:-1]
    alt[:-1] |= tile[1:]
    lone = tile & ~alt
    # still context: frame f's tile, on the steps f - 2 to f - 1 and f + 1 to f + 2
    ctx = np.zeros_like(a)
    ctx[1:] = st["tile"][: len(a) - 1]
    ctx[:-1] = np.maximum(ctx[:-1], st["tile"][2:])
    lone &= ctx < CONTEXT * small
    # the strong share of the frame, counted on lone tiles only
    power = (st["strong"][1:-1] * lone).sum((1, 2)) / TILES**2
    hit = [int(f) for f in np.flatnonzero(lone.any((1, 2)) & (power >= STRONG[2])) + 1]
    hit = [f for g in _groups(hit, MOVER[1]) if len(g) < MOVER[0] for f in g]
    free = [f for f in hit if not C.allowed(scenes, "Q1101", f / fps, 1 / fps)]
    rows = []
    for fs in _groups(free, round(POP_GROUP * fps)):
        f = max(fs, key=lambda x: power[x - 1])
        t = round(f / fps, 3)
        whole = st["iso"][f] > ISO[1] and st["acr12"][f] <= ratio * st["iso"][f]
        r, cc = np.argwhere(lone[f - 1]).T
        where = (
            f"{len(r)} of {TILES * TILES} tiles, rows {r.min() + 1}-{r.max() + 1}, "
            f"cols {cc.min() + 1}-{cc.max() + 1}"
        )
        rows.append(
            C.row(
                False,
                "Q1101",
                f"one-frame pop at {t:.2f} s: {'whole-frame' if whole else 'local'}, {power[f - 1]:.2%} of "
                f"pixels 12 levels off both neighbours ({where})"
                + (
                    f"; {len(fs)} pops {fs[0] / fps:.2f} to {fs[-1] / fps:.2f} s"
                    if len(fs) > 1
                    else ""
                ),
                SCAN_FIX["Q1101"],
                note=True,
                t0=round(fs[0] / fps, 3),
                t1=round(fs[-1] / fps, 3),
                worst_t=t,
                item=_scene(scenes, t, fps),
                metric=round(float(power[f - 1]), 4),
                limit=STRONG[2],
                spans=C.merge_spans([x / fps for x in fs], fps),
                considered=n - 2,
            )
        )
    return _fold(rows, "Q1101", "pops", fps, n - 2, scenes), len(hit) - len(free)


def _holds(scenes, fps, n):
    """bool (n,) frames inside a hold, HOLD_SLACK frames either side: a registry string at rest (text_items), a span
    of scenes.HOLDS [(text, drawn at, exit at), ...] (the 2.1.0 form some kits ship), or a scenes.STATIC span (drawn
    once by design). Also why none apply ("" when either was read)."""
    m = np.zeros(n, bool)
    why = []

    def mark(a, b):
        lo = max(0, C.frame_of(a, fps) - HOLD_SLACK)
        m[lo : min(n, C.frame_of(b, fps) + HOLD_SLACK)] = True

    held = getattr(scenes, "HOLDS", None) if scenes is not None else None
    for e in held or []:
        ts = _times(e)
        if len(ts) >= 2:
            mark(ts[-2], ts[-1])
    for a, b in getattr(scenes, "STATIC", None) or [] if scenes is not None else []:
        mark(a, b)  # a span the render draws once on purpose is frozen by design
    if scenes is None or not hasattr(scenes, "text_items"):
        why.append("no text registry")
    else:
        import qa  # here, not at the top: qa imports this module

        try:  # a registry older than 2.2 (no "s" key) must not stop the other scans
            spans = qa.text_spans(qa.text_frames(scenes, fps))
        except (KeyError, TypeError, AttributeError, IndexError) as e:
            spans = {}
            why.append(f"text registry unreadable ({type(e).__name__} {e})")
        for sp in spans.values():
            for a, b in sp:
                mark(a, b)
    return m, "" if held else "; ".join(why)


def _still_pieces(g, a, b, share):
    """Frames a..b, a run of still pairs, split wherever the picture drifts from its piece's first frame by the
    still rule: a slow draw-on passes every pair test but is not frozen."""
    out, s = [], a
    while s <= b:
        if s == b:  # one frame left: a piece of its own
            out.append((s, s))
            break
        rlo, rhi = (x[0] for x in _range3(g[s : s + 1].astype(np.int16)))
        later = g[s + 1 : b + 1].astype(np.int16)
        left = (later < rlo - STILL[0]) | (later > rhi + STILL[0])
        k = np.flatnonzero(left.reshape(len(later), -1).mean(1) >= share)
        e = s + int(k[0]) if len(k) else b
        out.append((s, e))
        s = e + 1
    return out


def _frozen(st, g, n, fps, scenes):
    """Q1102: runs of 3 s or more where under 0.2 percent of pixels move over 6 levels (outside the 3x3 range of
    the other frame), both frame to frame and against the run's first frame. Near-black runs, holds (2 frames
    slack), the static end tail up to 2 s + 1 frame and ALLOW spans do not count."""
    share, secs = STILL[1:]
    holds, why = _holds(scenes, fps, n)
    free = ~holds
    free[max(0, n - round(TAIL * fps) - 1) :] = False  # an end card may sit still
    allow = (getattr(scenes, "ALLOW", None) or {}).get("Q1102", [])
    for e in allow:
        lo, hi = e if isinstance(e, (tuple, list)) else (e, e)
        free[max(0, C.frame_of(lo, fps) - 1) : C.frame_of(hi, fps) + 2] = False
    rows = []
    for a, b in _runs(st["still"] < share):  # still steps a..b: frames a .. b + 1 hold
        if (b - a + 2) / fps + 1e-9 < secs or np.median(st["lit"][a : b + 2]) < BLACK[
            1
        ]:
            continue
        for p, q in (
            (p + s0, q + s0)
            for s0, e0 in _still_pieces(g, a, b + 1, share)
            for p, q in _runs(free[s0 : e0 + 1])
        ):
            dur = (q - p + 1) / fps
            if dur + 1e-9 < secs:
                continue
            t0, t1 = round(p / fps, 3), round((q + 1) / fps, 3)
            rows.append(
                C.row(
                    False,
                    "Q1102",
                    f"frozen {dur:.2f} s from {t0:.2f} to {t1:.2f} s ({why or 'no hold covers it'})",
                    SCAN_FIX["Q1102"],
                    note=True,
                    t0=t0,
                    t1=t1,
                    worst_t=round((t0 + t1) / 2, 3),
                    item=_scene(scenes, t0, fps),
                    metric=round(dur, 2),
                    limit=secs,
                    spans=[(t0, t1)],
                    considered=n,
                )
            )
    return _fold(rows, "Q1102", "frozen runs", fps, n, scenes)


def _planned(scenes, fps):
    """What scenes.py plans, in frames: the cut frames (SCHEDULE starts and CUTS), the cue frames (CUES, the 2.2
    list or the older dict of label -> times) and the transition windows (WINDOWS [(t0, t1, out, in)], as frame
    spans)."""
    if scenes is None:
        return set(), set(), []
    try:
        cue_t = [c["t"] for c in C.cues(scenes)]
    except (TypeError, ValueError, KeyError, IndexError):
        cue_t = _times(getattr(scenes, "CUES", None))
    cuts = {
        C.frame_of(t, fps)
        for t in [a for _, a, _ in _schedule(scenes)]
        + _times(getattr(scenes, "CUTS", None))
    }
    wins = []
    for w in getattr(scenes, "WINDOWS", None) or []:
        try:
            wins.append((C.frame_of(float(w[0]), fps), C.frame_of(float(w[1]), fps)))
        except (TypeError, ValueError, IndexError):
            continue
    return cuts, {C.frame_of(t, fps) for t in cue_t}, wins


def _in_window(f, wins, slack=1):
    return any(a - slack <= f <= b + slack for a, b in wins)


def _cut_frames(st, g):
    """Frames where a hard cut lands: a step over CUT (OVH) or DARK_CUT that is also DOMINANT x its larger
    neighbouring step (a ramp of a fast zoom or a collapse has no dominant step), minus flashes: a cut answered
    within FLASH_BACK frames by a cut back to the picture before it."""
    mad, side = st["mad"], CUT[4]
    out = []
    for i in range(len(mad)):
        near = np.concatenate([mad[max(0, i - side) : i], mad[i + 1 : i + 1 + side]])
        med = np.median(near) if len(near) else 0.0
        hard = st["s12"][i] > CUT[1] and mad[i] > CUT[2] and mad[i] > CUT[3] * med
        dark = (
            st["s6"][i] > DARK_CUT[1]
            and mad[i] > DARK_CUT[2]
            and mad[i] > DARK_CUT[3] * med
        )
        nb = max(mad[i - 1] if i else 0.0, mad[i + 1] if i + 1 < len(mad) else 0.0)
        if (hard or dark) and mad[i] >= DOMINANT * nb:
            out.append(i + 1)  # the change lands in frame i + 1
    flash = set()
    for f in out:
        for f2 in (x for x in out if f < x <= f + FLASH_BACK):
            back = np.abs(g[f2].astype(np.int16) - g[f - 1]).mean()
            if back <= POP[2] * mad[f - 1]:
                flash |= {f, f2}
    return [f for f in out if f not in flash]


def _cuts(st, g, n, fps, scenes):
    """Q1103: hard cuts (_cut_frames) that are not within 1 frame of a SCHEDULE start or a CUTS time, not within
    [cue - 1, cue + CUE_LAG + 1] of a CUES entry, and not inside a transition window (WINDOWS). Dissolves are not
    cuts, so this is the unplanned-hard-cut check only."""
    mad = st["mad"]
    cut = _cut_frames(st, g)
    if scenes is None:
        return [], len(cut)
    cuts, cue_f, wins = _planned(scenes, fps)
    lag = int(getattr(scenes, "CUE_LAG", 0) or 0)
    if not cuts and not cue_f:
        return [
            C.not_checked(
                "Q1103",
                f"{len(cut)} hard cuts found but scenes.py has no SCHEDULE, CUTS or CUES to compare them with",
                "declare SCHEDULE (and CUES) in scenes.py",
            )
        ], len(cut)
    free = [
        f
        for f in cut
        if not any(abs(f - p) <= 1 for p in cuts)
        and not any(p - 1 <= f <= p + lag + 1 for p in cue_f)
        and not _in_window(f, wins)
        and not C.allowed(scenes, "Q1103", f / fps, 1 / fps)
    ]
    planned = cuts | cue_f
    rows = []
    for fs in _groups(free, CUT_GROUP):
        f = max(fs, key=lambda x: mad[x - 1])
        t = round(f / fps, 3)
        p = min(planned, key=lambda q: abs(q - f))
        # name the rule that found it: the bright OVH rule, or the dark-cut rule (over 6 levels, mean over 6)
        bright = st["s12"][f - 1] > CUT[1] and mad[f - 1] > CUT[2]
        lvl, share, mean = (
            (CUT[0], st["s12"][f - 1], CUT[2])
            if bright
            else (DARK_CUT[0], st["s6"][f - 1], DARK_CUT[2])
        )
        rows.append(
            C.row(
                False,
                "Q1103",
                f"hard cut at {t:.2f} s not on a SCHEDULE start, CUTS or CUES time (nearest {p / fps:.2f} s; "
                f"{share:.0%} of pixels changed over {lvl} levels, mean {mad[f - 1]:.0f} levels)"
                + (f"; {len(fs)} cut frames in a row" if len(fs) > 1 else ""),
                SCAN_FIX["Q1103"],
                note=True,
                t0=round(fs[0] / fps, 3),
                t1=round(fs[-1] / fps, 3),
                worst_t=t,
                item=_scene(scenes, t, fps),
                metric=round(float(mad[f - 1]), 1),
                limit=mean,
                spans=[(round(fs[0] / fps, 3), round(fs[-1] / fps, 3))],
                considered=n - 1,
            )
        )
    return _fold(rows, "Q1103", "unplanned cuts", fps, n - 1, scenes), len(cut)


def _stalls(st, g, n, fps, scenes):
    """Q1104: frame f repeats frame f - 1 while the steps either side move over 0.8 levels on average: the pixels
    that move over 4 levels in both neighbouring steps (at least 0.5 percent of the frame) move into f under 5
    percent of the time, so film grain, which never moves 4 levels, cannot hide the repeat; or, on clean frames, the
    step into f changes under 0.05 on average. No other repeat sits within 6 frames, so animation on twos is not a
    stall. Not counted: a held flash (f + 1 returns to f - 2: a 2-frame blink is Q601's), inside a transition
    window (an eased crossfade starts with a near-still frame), and a hold of up to 2 frames right after a SCHEDULE
    start or CUTS time (the changeover gap Q207 asks for)."""
    mshare, moved, move, iso = STALL[1:]
    mad = np.concatenate(
        [[0.0], st["mad"], [0.0]]
    )  # mad[f] = the step into frame f, mad[f + 1] the step out of it
    exact = mad[:-1] < STALL_EXACT
    masked = (st["mshare"] >= mshare) & (st["mmoved"] < moved)
    # next to a cut every pixel moves, so the mask is just the other step's movers: the mask test does not apply there
    s12 = np.concatenate([[0.0], st["s12"], [0.0]])
    masked[1:-1] &= (s12[:-3] < CUT[1]) & (s12[2:-1] < CUT[1])
    rep = masked | exact
    rep[1:-1] &= (mad[:-3] > move) & (mad[2:-1] > move)  # into f - 1, out of f
    rep[[0, -1]] = False
    cuts, _, wins = _planned(scenes, fps)
    for f in np.flatnonzero(
        rep
    ):  # what is not a repeat goes before the twos test, so it cannot hide a real one
        f = int(f)
        a, b, c, d = (g[x].astype(np.int16) for x in (f - 2, f - 1, f, f + 1))
        mask = (np.abs(b - a) > STALL[0]) & (np.abs(d - c) > STALL[0])
        back = (
            mask.any() and (np.abs(d - a) > STALL[0])[mask].mean() < STALL_BACK
        )  # the picture came back
        if (
            back
            or _in_window(f, wins)
            or any(p < f <= p + 2 for p in cuts)
            or C.allowed(scenes, "Q1104", f / fps, 1 / fps)
        ):
            rep[f] = False
    rows = []
    for f in np.flatnonzero(rep):
        f = int(f)
        lo, hi = max(0, f - iso), min(n, f + iso + 1)
        if rep[lo:hi].sum() > 1:
            continue
        t = round(f / fps, 3)
        how, metric, limit = (
            (f"mean change {mad[f]:.2f}", float(mad[f]), STALL_EXACT)
            if exact[f]
            else (
                (
                    f"{st['mmoved'][f]:.0%} of the pixels moving either side moved into it, "
                    f"{st['mshare'][f]:.1%} of the frame"
                ),
                float(st["mmoved"][f]),
                moved,
            )
        )
        rows.append(
            C.row(
                False,
                "Q1104",
                f"stall at {t:.2f} s: the frame repeats the one before ({how}) between moves of "
                f"{mad[f - 1]:.1f} and {mad[f + 1]:.1f} levels",
                SCAN_FIX["Q1104"],
                note=True,
                t0=t,
                t1=t,
                worst_t=t,
                item=_scene(scenes, t, fps),
                metric=round(metric, 3),
                limit=limit,
                spans=[(t, t)],
                considered=n - 1,
            )
        )
    return _fold(rows, "Q1104", "stalls", fps, n - 1, scenes)


def scan_rows(g, fps, scenes=None):
    """Q1101 to Q1104 (all NOTE, all honour ALLOW) on uint8 (n, h, w) grey frames: ctx.grey() of the file, or
    thumbs.npy. A scan with nothing to report gives one PASS row that says how much it looked at. Q1103 needs a
    scenes.py to compare with, so without one it gives no row (as Q901)."""
    g, fps = np.asarray(g), round(fps)
    n = len(g)
    if n < 3:
        return [
            C.not_checked(code, f"{n} frame(s): too few to scan", "check the decode")
            for code in ("Q1101", "Q1102", "Q1103", "Q1104")
        ]
    st = _stats(g)
    pops, allowed = _pops(st, n, fps, scenes)
    frozen = _frozen(st, g, n, fps, scenes)
    cuts, ncut = _cuts(st, g, n, fps, scenes)
    stalls = _stalls(st, g, n, fps, scenes)
    rows = pops or [
        C.row(
            True,
            "Q1101",
            "no one-frame pops" + (f" ({allowed} listed in ALLOW)" if allowed else ""),
            "",
            considered=n - 2,
        )
    ]
    rows += frozen or [
        C.row(
            True,
            "Q1102",
            "no frozen run of 3 s outside holds and the end card",
            "",
            considered=n,
        )
    ]
    if scenes is not None:
        rows += cuts or [
            C.row(
                True,
                "Q1103",
                f"{ncut} hard cuts, every one on a SCHEDULE start, CUTS or CUES time (or in ALLOW)",
                "",
                considered=n - 1,
            )
        ]
    rows += stalls or [
        C.row(True, "Q1104", "no repeated frame inside motion", "", considered=n - 1)
    ]
    return rows


def match_rows(g, folder, fps):
    """Q1105: the file against the frames that were drawn (folder/thumbs.npy, on the same grey scale): a frame whose
    mean grey differs by over MATCH levels, or a different frame count, is a broken encode (a wrong-size frame
    shears every frame after it; the template differs by under 0.5). No thumbs.npy and no frames.hash: no row (not a
    2.2 render); frames.hash without thumbs.npy: NOT CHECKED."""
    folder = Path(folder)
    p = folder / C.THUMBS
    if not p.exists():
        if (folder / C.FRAMES_HASH).exists():
            return [
                C.not_checked(
                    "Q1105",
                    f"frames.hash but no {C.THUMBS} in {folder}: the file was not compared with the drawn frames",
                    "render the frames again (run_all.py full writes both)",
                )
            ]
        return []
    th = np.load(p)
    if th.shape[1:] != np.shape(g)[1:]:
        return [
            C.row(
                False,
                "Q1105",
                f"{C.THUMBS} is {th.shape[1:]} a frame but the decode is {np.shape(g)[1:]}",
                "render the frames and the file again together",
            )
        ]
    k = min(len(th), len(g))
    parts = [
        np.abs(g[i : min(i + 240, k)].astype(np.int16) - th[i : min(i + 240, k)])
        .reshape(-1, th[0].size)
        .mean(1)
        for i in range(0, k, 240)
    ]
    diff = np.concatenate(parts) if parts else np.zeros(1)
    bad = np.flatnonzero(diff > MATCH)
    worst = int(np.argmax(diff)) if k else 0
    same = len(th) == len(g)
    msg = (
        f"decoded file against the drawn frames: worst {diff[worst]:.2f} levels mean at {worst / fps:.2f} s, "
        f"{len(bad)} of {k} frames over {MATCH:g}"
        + ("" if same else f"; the file has {len(g)} frames, the drawing {len(th)}")
    )
    spans = C.merge_spans([f / fps for f in bad], fps)
    return [
        C.row(
            not len(bad) and same,
            "Q1105",
            msg,
            "the encode does not show what draw(t) drew: check frame sizes (every frame E.W x E.H) and the ffmpeg "
            "log, then run run_all.py full again",
            t0=spans[0][0] if spans else None,
            t1=spans[-1][1] if spans else None,
            worst_t=round(worst / fps, 3),
            metric=round(float(diff[worst]), 2),
            limit=MATCH,
            spans=spans,
            considered=k,
        )
    ]


WHY = {  # what a finding says in review_times.json (after its code and status)
    "Q601": "general flashes over 3 a second",
    "Q602": "red flashes over 3 a second",
    "Q603": "4 to 6 transitions a second held for 4 s",
    "Q1101": "one-frame pop",
    "Q1102": "frozen run",
    "Q1103": "unplanned hard cut",
    "Q1104": "stall: a repeated frame inside motion",
    "Q1105": "the file does not match the drawn frames",
}


def _why(r):
    """A finding's reason in review_times.json: code and status first (lane K's sheet shows it), then what and
    where, kept stable so the thumbs scan and the file scan merge into one reason."""
    s = f"{r.code} {r.status} {WHY.get(r.code, r.code)}"
    m = (
        re.search(r"rows (\d+)-(\d+), cols (\d+)-(\d+)", r.msg)
        if r.code == "Q1101"
        else None
    )
    if m:
        s += f" in tile rows {m[1]}-{m[2]}, cols {m[3]}-{m[4]}"
    return s + (f" ({r.item})" if r.item else "")


def add_review(rows, folder):
    """Every finding's moment into folder/review_times.json: kind "pop" with an f-2..f+2 strip for Q1101 (the
    strongest pop and each distinct pop of the row, folded ones included), "finding" for the rest; a flash row adds
    the middle of each of its passages too."""
    out = []
    for r in rows:
        if r.status == C.PASS or r.worst_t is None:
            continue
        ts = {r.worst_t}
        if r.code in ("Q601", "Q602"):
            ts |= {round((a + b) / 2, 3) for a, b in r.spans}
        if r.code == "Q1101":
            ts |= {round(a, 3) for a, _ in r.spans}
        for t in sorted(ts):
            out.append(
                {
                    "t": t,
                    "why": _why(r),
                    "kind": "pop" if r.code == "Q1101" else "finding",
                    "code": r.code,
                    "status": r.status,
                    "strip": r.code == "Q1101",
                }
            )
    if out:
        C.add_review_times(out, Path(folder) / C.REVIEW_TIMES)
    return out


def scan_thumbs(folder=".", scenes=None, fps=None):
    """Q1101 to Q1104 on thumbs.npy, every drawn frame before the encode, so a pop or freeze shows up before the
    file exists; findings go into review_times.json like check_rows. fps comes from frames.hash when not given."""
    folder = Path(folder)
    p = folder / C.THUMBS
    fps = fps or (C.read_frame_manifest(folder) or {}).get("fps")
    if not p.exists() or not fps:
        why = (
            f"no {C.THUMBS} in {folder}"
            if not p.exists()
            else "no fps (frames.hash missing)"
        )
        return [
            C.not_checked(
                code,
                f"{why}: the frame scans did not run",
                "render the frames first (they write thumbs.npy and frames.hash), or pass fps",
            )
            for code in ("Q1101", "Q1102", "Q1103", "Q1104")
        ]
    rows = scan_rows(np.load(p), round(fps), scenes)
    add_review(rows, folder)
    return rows


def check_rows(ctx):
    """Gate 6 on the linear-light decode, the frame scans on the grey one, and Q1105 against thumbs.npy; when the
    check names a build folder (ctx.record), each finding's moment also goes into its review_times.json."""
    rows = flash_rows(None, ctx.fps, ctx.w / ctx.h, scenes=ctx.scenes, lin=ctx.lin())
    g = ctx.grey()
    rows += scan_rows(g, ctx.fps, ctx.scenes)
    rows += match_rows(g, ctx.workdir, ctx.fps)
    if ctx.record:
        add_review(rows, ctx.workdir)
    return rows
