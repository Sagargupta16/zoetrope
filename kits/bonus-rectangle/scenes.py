# scenes.py : "Everything is a rectangle" (S-bonus-rectangle), 1080x1920, 30 fps, 60.0 s.
# draw(t) is pure: same t -> same pixels. Timing lives in SCHEDULE; CAPTIONS and EVENTS are built from it.
# EVENTS is the one list of (time, rectangle): the counter, the outlines and the boops (music.py) all read it.
import itertools
import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw

import engine as E
from engine import (
    clamp,
    ease_in_cubic,
    ease_in_out_cubic,
    ease_out_back,
    ease_out_cubic,
    ease_out_expo,
    lerp,
    prog,
)

W, H, FPS = 1080, 1920, 30
assert (E.W, E.H) == (W, H), "set E.W, E.H = 1080, 1920 before importing scenes"

# ---------- fonts: the card's Poppins is not installed; closest installed faces, missing font raises ----------
FONT_BOLD_PATH = "C:/Windows/Fonts/segoeuib.ttf"  # Poppins Bold -> Segoe UI Bold
FONT_SEMI_PATH = "C:/Windows/Fonts/seguisb.ttf"  # Poppins SemiBold -> Segoe UI Semibold
for _p in (FONT_BOLD_PATH, FONT_SEMI_PATH):
    if not os.path.exists(_p):
        raise FileNotFoundError(f"font not installed: {_p}")
if E.FONT_BOLD[0] != FONT_BOLD_PATH:
    E.FONT_BOLD.insert(0, FONT_BOLD_PATH)
if E.FONT_REG[0] != FONT_SEMI_PATH:
    E.FONT_REG.insert(0, FONT_SEMI_PATH)


def C(h):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


PAPER, INK, BLUE, WHITE = C("#F4F1EA"), C("#141414"), C("#2B59FF"), (255, 255, 255)

# ---------- timing ----------
BPM = 120
BEAT = 60 / BPM  # 0.5 s, bar 2 s, 30 bars
SCHEDULE = {  # seconds; the ONLY place scene timing is defined
    "hook": (0.0, 4.5),
    "objects": (4.5, 11.0),
    "zoom": (11.0, 13.0),
    "cricket": (13.0, 18.0),
    "tatami": (18.0, 23.0),
    "solar": (23.0, 27.0),
    "city": (27.0, 31.0),
    "port": (31.0, 36.0),
    "flags": (36.0, 42.0),
    "nepal": (42.0, 45.0),
    "fold": (45.0, 49.0),
    "pizza": (49.0, 52.0),
    "lid": (52.0, 54.0),
    "pullback": (54.0, 58.0),
    "end": (58.0, 60.0),
}
DURATION = 60.0
GLITCHES = [
    (43.0, 44.0),
    (50.0, 51.0),
]  # counter shows ???? ; music near silence (music.py)
CUTS = {a for a, b in SCHEDULE.values()} | {DURATION}


def fq(t):
    """First frame time at or after t: outlines, counter and boops all use this quantized time."""
    return math.ceil(t * FPS - 1e-6) / FPS


# ---------- type ----------
HERO, BIG, SMALL, LABEL, DIGITS = 124, 116, 46, 36, 104
CAP_X, CAP_TOP, MAXW = 72, 262, 860
ENTER, EXIT, STAG = 0.3, 0.3, 0.05
COUNTER_LABEL_XY, COUNTER_DIGITS_XY = (64, 64), (60, 100)


def lh_of(size, bold):
    return (
        round(size * 1.05) if bold else round(size * 1.26)
    )  # bold lines 1.05 em apart


def bwrap(s, size, bold, maxw=MAXW):
    """Balanced wrap: fewest lines, then no one-word orphan, then the narrowest widest line."""
    words = s.split()
    f = E.font(size, bold)
    n = len(E.wrap(s, size, maxw, bold))
    if n <= 1:
        return [s]
    best, best_key = None, None
    for br in itertools.combinations(range(1, len(words)), n - 1):
        cuts = (0,) + br + (len(words),)
        lines = [" ".join(words[a:b]) for a, b in zip(cuts, cuts[1:])]
        ws = [f.getlength(x) for x in lines]
        if max(ws) > maxw:
            continue
        orphan = (  # a short last word stranded under longer lines
            len(lines[-1].split()) == 1
            and any(len(x.split()) > 1 for x in lines[:-1])
            and ws[-1] < 0.4 * max(ws)
        )
        key = (orphan, max(ws))
        if best_key is None or key < best_key:
            best, best_key = lines, key
    return best or E.wrap(s, size, maxw, bold)


CAPTIONS = []


def cap(text, t_in, t_out, size=BIG, y=CAP_TOP, bold=True, cut_in=False, ticker=None):
    c = dict(
        text=text,
        t_in=t_in,
        t_out=t_out,
        size=size,
        bold=bold,
        y=y,
        x=CAP_X,
        lines=bwrap(text, size, bold),
        lh=lh_of(size, bold),
        cut_in=cut_in or t_in == 0,
        ticker=ticker,
        track=round(-0.035 * size) if bold else 0,
    )
    CAPTIONS.append(c)
    return c


def cap_bottom(c):
    asc, desc = E.font(c["size"], c["bold"]).getmetrics()
    return c["y"] + (len(c["lines"]) - 1) * c["lh"] + asc + desc


def below(c, gap=22):
    return cap_bottom(c) + gap


def full_at(c):
    return (
        c["t_in"] if c["cut_in"] else c["t_in"] + ENTER + STAG * (len(c["lines"]) - 1)
    )


def exit_at(c):
    """Start of exit, the end of the reading hold. At a scene cut the caption leaves with the cut; when it is
    replaced in place, all its lines leave one STAG early so they are gone before the new lines show."""
    return c["t_out"] if c["t_out"] in CUTS else c["t_out"] - STAG


def gone_at(c):
    return c["t_out"] if c["t_out"] in CUTS else exit_at(c) + EXIT


# hook: three stacked lines, the first fully drawn on frame 0
_h1 = cap("Look around.", 0.0, 4.5, HERO)
_h2 = cap(
    "Count the rectangles.",
    1.5,
    4.5,
    HERO,
    y=_h1["y"] + len(_h1["lines"]) * _h1["lh"] + 28,
)
_h3 = cap(
    "We'll wait.", 3.0, 4.5, HERO, y=_h2["y"] + len(_h2["lines"]) * _h2["lh"] + 28
)
# objects: two-row ticker so each line holds about 1.7 s while the objects change every second
TICK_A, TICK_B = CAP_TOP, CAP_TOP + BIG
TICK_CLIP = (0, TICK_A + 32, W, TICK_B + 158)
_tick = ["Your phone.", "Your laptop.", "Your door.", "Your book.", "Your bed."]
for _i, _s in enumerate(_tick):
    cap(
        _s,
        4.5 + _i,
        4.5 + _i + 2 if _i + 2 < len(_tick) else 11.0,
        BIG,
        y=TICK_B,
        ticker=_i,
    )
cap("Now zoom out.", 11.0, 13.0)
_c = cap("A cricket pitch.", 13.0, 18.0)
cap("22 yards by 10 feet.", 15.5, 18.0, SMALL, y=below(_c), bold=False)
_c = cap("Tatami mats.", 18.0, 23.0)
cap("Twice as long as they are wide.", 20.0, 23.0, SMALL, y=below(_c), bold=False)
_c = cap("A solar farm.", 23.0, 27.0)
cap("Panel after panel.", 24.5, 27.0, SMALL, y=below(_c), bold=False)
cap("City blocks.", 27.0, 31.0)
_c = cap("Shipping containers.", 31.0, 36.0)
cap("Stacked to the sky.", 33.0, 36.0, SMALL, y=below(_c), bold=False)
_c = cap("Almost every national flag is a rectangle.", 36.0, 42.0)
cap(
    "Two are square: Switzerland and Vatican City.",
    39.0,
    42.0,
    SMALL,
    y=below(_c),
    bold=False,
)
cap("Only Nepal said no.", 42.5, 45.0)
_c = cap("Fold A4 in half.", 45.0, 49.0)
cap("Same shape. Just smaller.", 46.5, 49.0, SMALL, y=below(_c), bold=False)
cap("Finally, something round.", 49.0, 51.5)
cap(
    "We put it in a square box.", 51.5, 54.5
)  # 7 words need 2.6 s: starts 0.5 s early, holds 0.5 s into the pull back
_c = cap("Even this video is a rectangle.", 54.5, 58.0)
cap("On a rectangle. In your hand.", 55.0, 58.0, SMALL, y=below(_c), bold=False)
cap("Everything is a rectangle.", 58.0, 60.0, HERO, y=700, cut_in=True)

# header panel bottom per scene: tallest caption block shown in that scene + margin
HB = {}
for _n, (_a, _b) in SCHEDULE.items():
    if _n in ("hook", "end"):
        HB[_n] = None
        continue
    _bot = max(
        [cap_bottom(c) for c in CAPTIONS if c["t_in"] < _b and gone_at(c) > _a] + [418]
    )
    HB[_n] = int(_bot + 44) // 2 * 2
_g = max(
    HB["pizza"], HB["lid"], HB["pullback"]
)  # one header for pizza, lid and pull back (continuous shot)
HB["pizza"] = HB["lid"] = HB["pullback"] = _g
VCY = {n: ((HB[n] or 0) + H) / 2 for n in SCHEDULE}


# ---------- drawing helpers ----------
class Cam:
    """screen = s * (world - pivot) + anchor"""

    def __init__(self, s=1.0, px=0.0, py=0.0, ax=0.0, ay=0.0):
        self.s, self.px, self.py, self.ax, self.ay = s, px, py, ax, ay

    def p(self, x, y):
        return (self.ax + (x - self.px) * self.s, self.ay + (y - self.py) * self.s)

    def r(self, b):
        x0, y0 = self.p(b[0], b[1])
        x1, y1 = self.p(b[2], b[3])
        return (x0, y0, x1, y1)


IDENT = Cam()


def norm(b):
    x0, y0, x1, y1 = b
    return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def R(d, b, fill):
    d.rectangle(norm(b), fill=fill)


def RR(d, b, r, fill):
    x0, y0, x1, y1 = norm(b)
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    if r < 1:
        d.rectangle((x0, y0, x1, y1), fill=fill)
    else:
        d.rounded_rectangle((x0, y0, x1, y1), r, fill=fill)


def off(b, dx, dy):
    return (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy)


def inset(b, k):
    return (b[0] + k, b[1] + k, b[2] - k, b[3] - k)


def mix(c1, c2, k):
    return tuple(int(round(a + (b - a) * k)) for a, b in zip(c1, c2))


def ellipse_sd(h, w, oy, cx, cy, rx, ry):
    """Approximate signed distance (px) to an ellipse for an h x w pixel grid starting at row oy."""
    ys = (np.arange(h, dtype=np.float32) + oy + 0.5)[:, None]
    xs = (np.arange(w, dtype=np.float32) + 0.5)[None, :]
    nx, ny = (xs - cx) / rx, (ys - cy) / ry
    r = np.sqrt(nx * nx + ny * ny) + 1e-6
    g = np.sqrt((nx / rx) ** 2 + (ny / ry) ** 2) / r + 1e-9
    return (r - 1) / g


def mask_from(a):
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "L")


def ss_tile(w, h, fn, ss=3):
    """Draw with fn(draw, ss) on an ss-times RGBA tile, return it downsampled (anti-aliased)."""
    big = Image.new("RGBA", (int(w * ss), int(h * ss)), (0, 0, 0, 0))
    fn(ImageDraw.Draw(big), ss)
    return big.resize((int(w), int(h)), Image.LANCZOS)


# ---------- dashed outlines ----------
DASH, GAP, LW, HALO = 16, 10, 3, 2


def _dash_spans(P, t):
    per = DASH + GAP
    s = -((t * 24) % per)
    out = []
    while s < P:
        a, b = max(s, 0.0), min(s + DASH, P)
        if b > a:
            out.append((a, b))
        s += per
    return out


def view_top(scene):
    """First pixel row below the scene's header rule (0 when the scene has no header panel)."""
    return HB[scene] + 4 if HB.get(scene) else 0


def snap_box(box, age, pad, top=0):
    """Where an outline is drawn: box plus pad; while snapping it starts a little large and settles.
    The snap never grows past the frame edge or up under the header (top = view_top), so an outline
    is visible on the very frame of its boop."""
    x0, y0, x1, y1 = norm(box)
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    if age < 0.2:
        k = ease_out_cubic(age / 0.2)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        hw, hh = (
            (x1 - x0) / 2 * (1 + 0.14 * (1 - k)) + 10 * (1 - k),
            (y1 - y0) / 2 * (1 + 0.14 * (1 - k)) + 10 * (1 - k),
        )
        e = LW / 2 + HALO + 1
        x0, y0 = max(min(x0, e), cx - hw), max(min(y0, top + e), cy - hh)
        x1, y1 = min(max(x1, W - e), cx + hw), min(max(y1, H - e), cy + hh)
    return x0, y0, x1, y1


def dashed_rect(d, box, t, age=9.0, pad=6, top=0):
    x0, y0, x1, y1 = snap_box(box, age, pad, top)
    w, h = x1 - x0, y1 - y0
    edges = [
        ((x0, y0), (1, 0), w),
        ((x1, y0), (0, 1), h),
        ((x1, y1), (-1, 0), w),
        ((x0, y1), (0, -1), h),
    ]
    pieces = []
    for a, b in _dash_spans(2 * (w + h), t):
        base = 0.0
        for (sx, sy), (dx, dy), L in edges:
            lo, hi = max(a, base), min(b, base + L)
            if hi > lo:
                pieces.append(
                    (
                        sx + dx * (lo - base),
                        sy + dy * (lo - base),
                        sx + dx * (hi - base),
                        sy + dy * (hi - base),
                    )
                )
            base += L
    hw_halo, hw_line = LW / 2 + HALO, LW / 2
    for e in (hw_halo, hw_line):
        col = WHITE if e == hw_halo else BLUE
        for px0, py0, px1, py1 in pieces:
            d.rectangle(norm((px0 - e, py0 - e, px1 + e, py1 + e)), fill=col)


def dash_path(pts, t, closed=True):
    """Dashes along any polyline: returns a list of short polylines."""
    if closed:
        pts = list(pts) + [pts[0]]
    seg = [
        (pts[i], pts[i + 1], math.dist(pts[i], pts[i + 1])) for i in range(len(pts) - 1)
    ]
    P = sum(s[2] for s in seg)
    out = []
    for a, b in _dash_spans(P, t):
        cur, base = [], 0.0
        for p, q, L in seg:
            lo, hi = max(a, base), min(b, base + L)
            if hi > lo and L > 0:
                u0, u1 = (lo - base) / L, (hi - base) / L
                p0 = (p[0] + (q[0] - p[0]) * u0, p[1] + (q[1] - p[1]) * u0)
                p1 = (p[0] + (q[0] - p[0]) * u1, p[1] + (q[1] - p[1]) * u1)
                if not cur:
                    cur.append(p0)
                cur.append(p1)
            base += L
        if len(cur) >= 2:
            out.append(cur)
    return out


def draw_dashes(d, dashes):
    for col, w in ((WHITE, LW + 2 * HALO), (BLUE, LW)):
        for pl in dashes:
            d.line(pl, fill=col, width=int(w), joint="curve")


def rrect_path(b, r, n=8):
    x0, y0, x1, y1 = b
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    if r < 1:
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    pts = []
    for cx, cy, a0 in (
        (x1 - r, y0 + r, -90),
        (x1 - r, y1 - r, 0),
        (x0 + r, y1 - r, 90),
        (x0 + r, y0 + r, 180),
    ):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def failed_outline(d, t, box, t_on, t_break, seed, bend=0.0):
    """A dashed outline that snaps on, jitters harder and harder, then breaks and falls (no count)."""
    if t < t_on:
        return
    fi = int(round(t * FPS))
    x0, y0, x1, y1 = box
    side = min(x1 - x0, y1 - y0)
    if t < t_break:
        k = prog(t, t_on, t_break - t_on)
        rnd = random.Random(seed * 1000 + fi)
        amp = 4 + 36 * k * k
        r = side * 0.5 * bend * ease_in_out_cubic(clamp(k * 1.6))
        pts = rrect_path(box, r)
        pts = (
            [
                (x + rnd.uniform(-amp, amp), y + rnd.uniform(-amp, amp) * 0.7)
                for x, y in pts
            ]
            if r < 1
            else [
                (x + rnd.uniform(-amp, amp) * 0.4, y + rnd.uniform(-amp, amp) * 0.4)
                for x, y in pts
            ]
        )
        if t - t_on < 0.2:
            g = 1 + 0.14 * (1 - ease_out_cubic((t - t_on) / 0.2))
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            pts = [(cx + (x - cx) * g, cy + (y - cy) * g) for x, y in pts]
        draw_dashes(d, dash_path(pts, t))
        return
    tau = t - t_break
    if tau > 0.6:
        return
    r = side * 0.5 * bend
    dashes = dash_path(rrect_path(box, r), t_break)
    rnd = random.Random(seed)
    out = []
    for pl in dashes:
        vx, vy = rnd.uniform(-160, 160), rnd.uniform(-420, -60)
        dx, dy = vx * tau, vy * tau + 0.5 * 2600 * tau * tau
        if rnd.random() < tau / 0.6:
            continue
        out.append([(x + dx, y + dy) for x, y in pl])
    draw_dashes(d, out)


# ---------- text ----------
_tiles = {}


def text_tile(s, size, bold, track):
    key = (s, size, bold, track)
    if key not in _tiles:
        f = E.font(size, bold)
        asc, desc = f.getmetrics()
        wpx = int(f.getlength(s) + max(0, track) * len(s) + 12)
        tile = Image.new("L", (wpx, asc + desc + 6), 0)
        td = ImageDraw.Draw(tile)
        if track:
            for i, ch in enumerate(s):
                td.text(
                    (f.getlength(s[:i]) + i * track, 0),
                    ch,
                    font=f,
                    fill=255,
                    anchor="la",
                )
        else:
            td.text((0, 0), s, font=f, fill=255, anchor="la")
        _tiles[key] = tile
    return _tiles[key]


def put_text(img, s, x, y, size, bold, color, track=0, clip=None):
    tile = text_tile(s, size, bold, track)
    x, y = int(round(x)), int(round(y))
    bx0, by0, bx1, by1 = x, y, x + tile.width, y + tile.height
    cx0, cy0, cx1, cy1 = clip if clip else (0, 0, W, H)
    cx0, cy0, cx1, cy1 = max(cx0, 0), max(cy0, 0), min(cx1, W), min(cy1, H)
    ix0, iy0, ix1, iy1 = max(bx0, cx0), max(by0, cy0), min(bx1, cx1), min(by1, cy1)
    if ix1 <= ix0 or iy1 <= iy0:
        return
    m = tile.crop((ix0 - bx0, iy0 - by0, ix1 - bx0, iy1 - by0))
    img.paste(color, (ix0, iy0, ix1, iy1), m)


def text_items(t):
    """Every text line on screen at t: draw position, rest position, clip and whether it is in its hold."""
    items = []
    for c in CAPTIONS:
        if t < c["t_in"] or t >= gone_at(c):
            continue
        size, lh = c["size"], c["lh"]
        asc, desc = E.font(size, c["bold"]).getmetrics()
        D = 1.25 * lh
        base = c["y"]
        if c["ticker"] is not None and c["ticker"] + 1 < len(_tick):
            base = TICK_B - (TICK_B - TICK_A) * ease_out_expo(
                prog(t, c["t_in"] + 1, 0.3)
            )
        exit_anim = c["t_out"] not in CUTS
        for i, line in enumerate(c["lines"]):
            y_rest = base + i * lh
            e_in = (
                1.0
                if c["cut_in"]
                else ease_out_expo(prog(t, c["t_in"] + i * STAG, ENTER))
            )
            e_out = (
                ease_out_expo(prog(t, exit_at(c), EXIT))
                if exit_anim and t >= exit_at(c)
                else 0.0
            )
            clip = (
                TICK_CLIP
                if c["ticker"] is not None
                else (0, y_rest + int(0.28 * size), W, y_rest + asc + desc + 2)
            )
            items.append(
                dict(
                    text=line,
                    x=c["x"],
                    y=y_rest + D * (1 - e_in) - D * e_out,
                    y_rest=y_rest,
                    size=size,
                    bold=c["bold"],
                    track=c["track"],
                    color=INK,
                    clip=clip,
                    hold=(t >= full_at(c) and t < exit_at(c)),
                    cap=c["text"],
                )
            )
    items.append(
        dict(
            text="RECTANGLES SPOTTED",
            x=COUNTER_LABEL_XY[0],
            y=COUNTER_LABEL_XY[1],
            y_rest=COUNTER_LABEL_XY[1],
            size=LABEL,
            bold=False,
            track=2,
            color=INK,
            clip=None,
            hold=True,
            cap="counter label",
        )
    )
    digits, col, (dx, dy) = counter_text(t)
    items.append(
        dict(
            text=digits,
            x=COUNTER_DIGITS_XY[0] + dx,
            y=COUNTER_DIGITS_XY[1] + dy,
            y_rest=COUNTER_DIGITS_XY[1],
            size=DIGITS,
            bold=True,
            track=0,
            color=col,
            clip=None,
            hold=not in_glitch(t),
            cap="counter digits",
        )
    )
    if 11.8 <= t < 13.0:  # once the map has resolved
        items.append(
            dict(
                text="Schematic map",
                x=CAP_X,
                y=MAP_NOTE_Y,
                y_rest=MAP_NOTE_Y,
                size=LABEL,
                bold=False,
                track=0,
                color=INK,
                clip=None,
                hold=True,
                cap="map note",
            )
        )
    return items


# ---------- scene geometry and the event list ----------
EVENTS = []


def ev(t, scene, rect, pad=6, snd="boop", until=None, **kw):
    EVENTS.append(
        dict(
            t=fq(t), scene=scene, rect=tuple(rect), pad=pad, snd=snd, until=until, **kw
        )
    )


# objects (4.5-11.0)
OCX, OCY = W / 2, VCY["objects"] - 20


def _o(a, b, c, d):
    return (OCX + a, OCY + b, OCX + c, OCY + d)


OBJ_T = {"phone": 4.5, "laptop": 5.5, "door": 6.5, "book": 7.5, "bed": 8.5}
P_BODY, P_SCREEN, P_DOCK = (
    _o(-200, -400, 200, 400),
    _o(-184, -384, 184, 384),
    _o(-150, 250, 150, 340),
)
P_TILES = [
    _o(-148, -300, -20, -172),
    _o(20, -300, 148, -172),
    _o(-148, -132, -20, -4),
    _o(20, -132, 148, -4),
]
L_LID, L_DISP = _o(-330, -430, 330, -130), _o(-308, -410, 308, -150)
L_W1, L_W2 = _o(-282, -386, -26, -200), _o(4, -346, 282, -172)
L_DECK, L_KEYS, L_PAD = (
    _o(-330, -112, 330, 335),
    _o(-292, -80, 292, 132),
    _o(-112, 165, 112, 302),
)
D_FRAME, D_SLAB, D_SLOT = (
    _o(-250, -520, 250, 470),
    _o(-210, -490, 210, 470),
    _o(-90, -104, 90, -72),
)
D_PANELS = [
    _o(-170, -450, -22, -150),
    _o(22, -450, 170, -150),
    _o(-170, 30, -22, 420),
    _o(22, 30, 170, 420),
]
B_COVER, B_LP, B_RP = (
    _o(-400, -290, 400, 290),
    _o(-382, -272, -6, 272),
    _o(6, -272, 382, 272),
)
B_BLOCKS = [
    _o(-344, -222, -44, -44),
    _o(-344, -8, -44, 222),
    _o(44, -222, 344, -92),
    _o(44, -56, 344, 222),
]
BD_RUG, BD_FRAME = _o(-390, 40, 390, 560), _o(-275, -480, 275, 385)
BD_DUVET, BD_FOLD = _o(-255, -300, 255, 365), _o(-255, -300, 255, -205)
BD_PIL = [_o(-235, -440, -15, -320), _o(15, -440, 235, -320)]
BD_NS = [_o(-430, -470, -295, -335), _o(295, -470, 430, -335)]
BD_PHONE = _o(335, -452, 381, -365)
OBJ_EVENTS = {
    "phone": [P_BODY, P_SCREEN] + P_TILES + [P_DOCK],
    "laptop": [L_DECK, L_LID, L_DISP, L_KEYS, L_PAD, L_W1, L_W2],
    "door": [D_FRAME, D_SLAB] + D_PANELS + [D_SLOT],
    "book": [B_COVER, B_LP, B_RP] + B_BLOCKS,
    "bed": [BD_RUG, BD_FRAME, BD_DUVET, BD_FOLD] + BD_PIL + BD_NS + [BD_PHONE],
}
for _n, _rs in OBJ_EVENTS.items():
    for _k, _r in enumerate(_rs):
        ev(OBJ_T[_n] + 0.125 * (_k + 1), "objects", _r, obj=_n)

# zoom (11.0-13.0): square-pixel map, 5-degree cells, 72 x 26 (lat 75N to 55S), hand-built and rough
LAND = {
    0: [(3, 7), (11, 23), (25, 31), (46, 47), (52, 58), (60, 63), (66, 68)],
    1: [(3, 19), (20, 23), (25, 31), (38, 71)],
    2: [(3, 16), (21, 23), (26, 28), (31, 32), (37, 71)],
    3: [(4, 16), (20, 24), (35, 35), (37, 63), (66, 68)],
    4: [(10, 18), (20, 25), (34, 36), (36, 63), (64, 64), (67, 67)],
    5: [(11, 24), (35, 43), (44, 62), (64, 64)],
    6: [(11, 22), (34, 40), (44, 46), (50, 63), (64, 64)],
    7: [(11, 21), (34, 35), (38, 38), (40, 46), (49, 63), (63, 64)],
    8: [(12, 20), (34, 47), (48, 50), (51, 60), (62, 63)],
    9: [(13, 16), (19, 19), (33, 42), (43, 47), (47, 49), (50, 60)],
    10: [(14, 16), (19, 20), (32, 43), (43, 47), (49, 55), (56, 57)],
    11: [(15, 18), (21, 22), (32, 43), (44, 46), (50, 52), (55, 57), (60, 60)],
    12: [(17, 19), (21, 23), (32, 44), (51, 51), (55, 57), (60, 61)],
    13: [(19, 25), (33, 45), (52, 52), (55, 56), (61, 61)],
    14: [(20, 26), (37, 45), (55, 59), (60, 60)],
    15: [(20, 29), (37, 44), (56, 59), (62, 65)],
    16: [(20, 29), (38, 43), (57, 58), (64, 65)],
    17: [(20, 28), (38, 44), (45, 45), (62, 64)],
    18: [(21, 28), (38, 43), (45, 45), (60, 65)],
    19: [(22, 27), (38, 42), (45, 45), (58, 66)],
    20: [(21, 26), (39, 42), (58, 66)],
    21: [(21, 25), (39, 41), (59, 60), (63, 66)],
    22: [(21, 24), (64, 65), (70, 71)],
    23: [(21, 23), (65, 65), (70, 70)],
    24: [(21, 22), (69, 69)],
    25: [(21, 22)],
}
LAND_CELLS = sorted(
    {(r, c) for r, spans in LAND.items() for a, b in spans for c in range(a, b + 1)}
)
CELL, MAP_COLS, MAP_ROWS = 14, 72, 26
MX0 = W / 2 - MAP_COLS * CELL / 2
MY0 = VCY["zoom"] - MAP_ROWS * CELL / 2
MAP_NOTE_Y = int(MY0 + MAP_ROWS * CELL + 26)
BED_CELL, PIN_CELL = (
    (13, 36),
    (11, 51),
)  # the bed lands on a land cell near the middle; the pin drops on India


def cell_center(rc):
    return (MX0 + rc[1] * CELL + CELL / 2, MY0 + rc[0] * CELL + CELL / 2)


# cricket (13.0-18.0), world in metres, pitch centre at the origin
CR_RX, CR_RY = 74.0, 84.0
CR_SW, CR_ST = 6.6, 44.0  # px per metre: wide shot, then pushed in on the pitch
PITCH_HL, PITCH_HW = 10.06, 1.525  # 22 yd between bowling creases, 10 ft wide
POP, RET = (
    1.22,
    1.32,
)  # popping crease 4 ft in front; return creases 4 ft 4 in from the middle stump
CR_SQUARE = (-12.0, -15.0, 12.0, 15.0)
CR_SCREENS = [(-9.0, -83.0, 9.0, -80.0), (-9.0, 80.0, 9.0, 83.0)]
CR_PITCH = (-PITCH_HW, -PITCH_HL, PITCH_HW, PITCH_HL)
CR_BOXES = [
    (-RET, -PITCH_HL, RET, -PITCH_HL + POP),
    (-RET, PITCH_HL - POP, RET, PITCH_HL),
]
ev(13.5, "cricket", CR_SCREENS[0])
ev(13.75, "cricket", CR_SCREENS[1])
ev(
    14.0, "cricket", CR_SQUARE, until=14.25
)  # outline leaves before the push-in outgrows the frame
ev(15.5, "cricket", CR_PITCH)
ev(16.0, "cricket", CR_BOXES[0])
ev(16.25, "cricket", CR_BOXES[1])


def cam_cricket(t):
    u = ease_in_out_cubic(prog(t, 14.25, 0.75))
    s = CR_SW * (CR_ST / CR_SW) ** u * (1 + 0.02 * prog(t, 15.0, 3.0))
    return Cam(s, 0, 0, W / 2, VCY["cricket"])


# tatami (18.0-23.0), world in mat units (1 unit = 0.9 m), an 8-mat room with no four-corner meeting
TA_MATS = [
    (0, 0, 2, 1),
    (2, 0, 4, 1),
    (3, 1, 4, 3),
    (2, 3, 4, 4),
    (0, 3, 2, 4),
    (0, 1, 1, 3),
    (1, 1, 3, 2),
    (1, 2, 3, 3),
]
TA_TABLE = (1.38, 1.62, 2.62, 2.38)
TA_CUSH = [
    (1.7, 0.86, 2.3, 1.46),
    (1.7, 2.54, 2.3, 3.14),
    (0.68, 1.7, 1.28, 2.3),
    (2.72, 1.7, 3.32, 2.3),
]
for _k, _m in enumerate(TA_MATS):
    ev(18.5 + 0.25 * _k, "tatami", _m)
ev(21.0, "tatami", TA_TABLE)
for _k, _m in enumerate(TA_CUSH):
    ev(21.5 + 0.125 * _k, "tatami", _m)


def cam_tatami(t):
    return Cam(196 * (1 + 0.04 * prog(t, 18.0, 5.0)), 2, 2, W / 2, VCY["tatami"])


# solar farm (23.0-27.0), world in px
SO_COLS, SO_ROWS, SO_W, SO_H, SO_GX, SO_PITCH = 8, 13, 116, 66, 6, 96
SO_X0 = W / 2 - (SO_COLS * SO_W + (SO_COLS - 1) * SO_GX) / 2
SO_Y0 = VCY["solar"] - (SO_ROWS * SO_PITCH - (SO_PITCH - SO_H)) / 2
SO_MODS = [
    (
        SO_X0 + c * (SO_W + SO_GX),
        SO_Y0 + r * SO_PITCH,
        SO_X0 + c * (SO_W + SO_GX) + SO_W,
        SO_Y0 + r * SO_PITCH + SO_H,
    )
    for r in range(SO_ROWS)
    for c in range(SO_COLS)
]
for _k, _m in enumerate(SO_MODS):
    ev(23.5 + 3.0 * (_k / len(SO_MODS)) ** 0.7, "solar", _m, pad=4)


def cam_solar(t):
    return Cam(1 + 0.025 * prog(t, 23.0, 4.0), W / 2, VCY["solar"], W / 2, VCY["solar"])


# city grid (27.0-31.0), 80 blocks
CI_COLS, CI_ROWS, CI_BW, CI_BH, CI_ST = 8, 10, 108, 112, 22
CI_X0 = W / 2 - (CI_COLS * CI_BW + (CI_COLS - 1) * CI_ST) / 2
CI_Y0 = VCY["city"] - (CI_ROWS * CI_BH + (CI_ROWS - 1) * CI_ST) / 2
_rnd = random.Random(27)
CI_BLOCKS = []
for _r in range(CI_ROWS):
    for _c in range(CI_COLS):
        _x, _y = CI_X0 + _c * (CI_BW + CI_ST), CI_Y0 + _r * (CI_BH + CI_ST)
        CI_BLOCKS.append(
            dict(
                rect=(_x, _y, _x + CI_BW, _y + CI_BH),
                park=_rnd.random() < 0.08,
                rc=(_r, _c),
                key=_r + _c + _rnd.uniform(-0.6, 0.6),
                seed=_rnd.randrange(1 << 30),
            )
        )
for _k, _b in enumerate(sorted(CI_BLOCKS, key=lambda b: b["key"])):
    ev(27.5 + 2.0 * (_k / len(CI_BLOCKS)) ** 0.75, "city", _b["rect"], pad=5)
CI_CABS = []
for _i in range(26):
    _vert = _rnd.random() < 0.5
    _lane = _rnd.randrange(1, (CI_COLS if _vert else CI_ROWS))
    CI_CABS.append(
        (
            _vert,
            _lane,
            _rnd.uniform(0, 2000),
            _rnd.choice([-1, 1]) * _rnd.uniform(60, 140),
        )
    )


def cam_city(t):
    return Cam(1 + 0.025 * prog(t, 27.0, 4.0), W / 2, VCY["city"], W / 2, VCY["city"])


# container port (31.0-36.0): drops into stacks, up to 3 high
PO_COLS, PO_ROWS, PO_W, PO_H, PO_GX, PO_GY = 6, 28, 152, 30, 22, 7
PO_X0 = W / 2 - (PO_COLS * PO_W + (PO_COLS - 1) * PO_GX) / 2
PO_Y0 = VCY["port"] - (PO_ROWS * PO_H + (PO_ROWS - 1) * PO_GY) / 2
PO_COLORS = [C("#A4482C"), C("#233C5E"), C("#C28A2C"), C("#2E7C78")]
_rnd = random.Random(31)
_slots = [(r, c) for r in range(PO_ROWS) for c in range(PO_COLS)]
_tiers = [list(_slots)]
_tiers.append([s for s in _tiers[0] if _rnd.random() < 0.55])
_tiers.append([s for s in _tiers[1] if _rnd.random() < 0.45])
PO_BOXES = []
for _tier, _ss in enumerate(_tiers):
    for _s in sorted(_ss, key=lambda s: s[0] + _rnd.uniform(-3, 3)):
        _x = PO_X0 + _s[1] * (PO_W + PO_GX) - 4 * _tier
        _y = PO_Y0 + _s[0] * (PO_H + PO_GY) - 6 * _tier
        PO_BOXES.append(
            dict(rect=(_x, _y, _x + PO_W, _y + PO_H), tier=_tier, col=_rnd.randrange(4))
        )
for _k, _b in enumerate(PO_BOXES):
    _b["t"] = fq(31.15 + 3.5 * (_k / len(PO_BOXES)) ** 0.85)
    ev(_b["t"], "port", _b["rect"], pad=2, box=_k)


def cam_port(t):
    return Cam(1 + 0.02 * prog(t, 31.0, 5.0), W / 2, VCY["port"], W / 2, VCY["port"])


# flags (36.0-42.0): plain stripes only, real ratios (height:width)
FLAGS = [  # name, (h, w), orientation, colours
    ("France", (2, 3), "v", ["#002395", "#FFFFFF", "#ED2939"]),
    ("Italy", (2, 3), "v", ["#009246", "#FFFFFF", "#CE2B37"]),
    ("Germany", (3, 5), "h", ["#000000", "#DD0000", "#FFCE00"]),
    ("Ireland", (1, 2), "v", ["#169B62", "#FFFFFF", "#FF883E"]),
    ("Switzerland", (1, 1), "x", ["#DA291C", "#FFFFFF"]),
    ("Belgium", (13, 15), "v", ["#000000", "#FDDA24", "#EF3340"]),
    ("Netherlands", (2, 3), "h", ["#AE1C28", "#FFFFFF", "#21468B"]),
    ("Austria", (2, 3), "h", ["#C8102E", "#FFFFFF", "#C8102E"]),
    ("Nigeria", (1, 2), "v", ["#008751", "#FFFFFF", "#008751"]),
    ("Peru", (2, 3), "v", ["#D91023", "#FFFFFF", "#D91023"]),
    ("Romania", (2, 3), "v", ["#002B7F", "#FCD116", "#CE1126"]),
]
FH, FL_PITCH = 130, 215
FL_RECTS = []
for _i, (_n, (_rh, _rw), _o2, _cs) in enumerate(FLAGS):
    _row = _i // 3
    _cx = [200, 540, 880][_i % 3] if _row < 3 else [370, 710][_i % 3]
    _cy = VCY["flags"] + (_row - 1.5) * FL_PITCH
    _w = FH * _rw / _rh
    FL_RECTS.append((_cx - _w / 2, _cy - FH / 2, _cx + _w / 2, _cy + FH / 2))
SWISS = 4
SW_LIFT = (W / 2 - 176, VCY["flags"] - 140 - 176, W / 2 + 176, VCY["flags"] - 140 + 176)
_j = 0
for _i in range(len(FLAGS)):
    if _i != SWISS:
        ev(36.5 + 0.25 * _j, "flags", FL_RECTS[_i])
        _j += 1
ev(39.5, "flags", SW_LIFT)

# nepal (42.0-45.0): stylised double pennant, the deliberate exception (never counted)
NP_L = 360
NP_BORDER = 20
NP_CX, NP_CY = W / 2, VCY["nepal"] - 10

# A4 fold (45.0-49.0): A4 210 x 297 mm, each half keeps the root-2 ratio
A4H = 820
A4W = A4H / math.sqrt(2)
A4 = (W / 2 - A4W / 2, VCY["fold"] - A4H / 2, W / 2 + A4W / 2, VCY["fold"] + A4H / 2)
A5 = (A4[0], (A4[1] + A4[3]) / 2, A4[2], A4[3])
A6 = ((A5[0] + A5[2]) / 2, A5[1], A5[2], A5[3])
A7 = (A6[0], (A6[1] + A6[3]) / 2, A6[2], A6[3])
FOLDS = [(45.5, 46.0), (46.5, 47.0), (47.5, 48.0)]
ev(45.125, "fold", A4, until=45.5)
ev(46.0, "fold", A5, until=46.5)
ev(47.0, "fold", A6, until=47.5)
ev(48.0, "fold", A7)

# pizza, lid and pull back (49.0-58.0)
PZ_C = (W / 2, VCY["pizza"] - 140)
PZ_R = 245
BOX = (PZ_C[0] - 280, PZ_C[1] - 280, PZ_C[0] + 280, PZ_C[1] + 280)
ev(53.0, "lid", BOX, pad=8, snd="thunk")

PB_TOP = (
    HB["pullback"] + 4 + 40.0
)  # the screen sits 40 px under the header rule, whatever the header height
_pdy = PB_TOP - 740.0  # the hand was laid out for a screen top of 740
PB_SCREEN = (324.0, PB_TOP, 756.0, PB_TOP + 768.0)  # 9:16, the film itself
PB_BODY = (PB_SCREEN[0] - 24, PB_SCREEN[1] - 26, PB_SCREEN[2] + 24, PB_SCREEN[3] + 26)
PB_PIVOT = (
    W / 2,
    PB_SCREEN[1] / (1 - (PB_SCREEN[3] - PB_SCREEN[1]) / H),
)  # fixed point of the pull back
PB_PALM = (318.0, 1350.0 + _pdy, 770.0, 1900.0)
PB_THUMB = off((742.0, 1136.0, 814.0, 1432.0), 0, _pdy)
PB_FINGERS = [
    off(f, 0, _pdy)
    for f in [
        (262.0, 996.0, 344.0, 1068.0),
        (256.0, 1084.0, 340.0, 1156.0),
        (260.0, 1172.0, 344.0, 1244.0),
        (270.0, 1260.0, 342.0, 1326.0),
    ]
]
ev(55.0, "pullback", PB_SCREEN)
ev(55.5, "pullback", PB_BODY)
for _k, _r in enumerate([PB_PALM, PB_THUMB] + PB_FINGERS):
    ev(57.25 + 0.125 * _k, "pullback", _r)

END_FRAME = (40.0, 40.0, W - 40.0, H - 40.0)
ev(58.1, "end", END_FRAME, pad=0, snd="ding")

EVENTS.sort(key=lambda e: e["t"])
EV_T = np.array([e["t"] for e in EVENTS])
TOTAL = len(EVENTS)


def count_at(t):
    return int(np.searchsorted(EV_T, t + 1e-9, side="right"))


def in_glitch(t):
    return any(a <= t < b for a, b in GLITCHES)


def counter_text(t):
    n = count_at(t)
    for a, b in GLITCHES:
        if a <= t < b:
            fi = int(round(t * FPS))
            rnd = random.Random(fi * 7 + 3)
            s = (
                "".join(str(rnd.randint(0, 9)) for _ in range(4))
                if (t - a < 0.12 or b - t < 0.12)
                else "????"
            )
            return s, INK, (rnd.randint(-7, 7), rnd.randint(-4, 4))
    return f"{n:04d}", BLUE, (0, 0)


def outlines(d, scene, t, cam, only=None):
    for e in EVENTS:
        if e["scene"] != scene or e["t"] > t + 1e-9:
            continue
        if e["until"] is not None and t >= e["until"]:
            continue
        if only and not only(e):
            continue
        dashed_rect(d, cam.r(e["rect"]), t, t - e["t"], e["pad"], view_top(scene))


# ---------- scenes ----------
def header(img, d, name):
    hb = HB[name]
    if hb is None:
        return
    R(d, (0, 0, W, hb), PAPER)
    R(d, (0, hb, W, hb + 4), INK)


DESK, DESK_SH, GRAIN = C("#D8B88A"), C("#BE9E70"), C("#CFAE7E")


def desk(d, hb, col=DESK, grain=GRAIN):
    R(d, (0, hb, W, H), col)
    for i in range(20):
        y = hb + 30 + i * 71 + (i * 37) % 23
        d.line((0, y, W, y + 5), fill=grain, width=2)


def draw_objects(img, d, t):
    name = max((n for n in OBJ_T if OBJ_T[n] <= t), key=lambda n: OBJ_T[n])
    t0 = OBJ_T[name]
    c = Cam(0.93 + 0.07 * ease_out_back(prog(t, t0, 0.22)), OCX, OCY, OCX, OCY)
    s = c.s
    hb = HB["objects"]
    if name == "phone":
        desk(d, hb)
        RR(d, off(c.r(P_BODY), 14, 18), 46 * s, DESK_SH)
        RR(d, c.r(P_BODY), 46 * s, C("#1C1C1F"))
        RR(d, c.r(P_SCREEN), 32 * s, C("#EDE6D8"))
        for r, col in zip(P_TILES, ["#E76F51", "#2A9D8F", "#E9C46A", "#6D597A"]):
            RR(d, c.r(r), 26 * s, C(col))
        RR(d, c.r(P_DOCK), 30 * s, C("#D9D0BF"))
        RR(d, c.r(_o(-40, -374, 40, -360)), 7 * s, C("#1C1C1F"))
    elif name == "laptop":
        desk(d, hb)
        RR(
            d,
            off(c.r((L_LID[0], L_LID[1], L_DECK[2], L_DECK[3])), 14, 18),
            18 * s,
            DESK_SH,
        )
        RR(d, c.r(L_LID), 16 * s, C("#A7ADB4"))
        R(d, c.r(L_DISP), C("#2E3440"))
        R(d, c.r(L_W1), C("#EDE6D8"))
        R(d, c.r((L_W1[0], L_W1[1], L_W1[2], L_W1[1] + 22)), C("#CFC6B4"))
        R(d, c.r(L_W2), C("#E9C46A"))
        R(d, c.r((L_W2[0], L_W2[1], L_W2[2], L_W2[1] + 22)), C("#D4AD4E"))
        RR(d, c.r(L_DECK), 18 * s, C("#BCC2C8"))
        R(
            d,
            c.r((L_DECK[0] + 30, L_DECK[1], L_DECK[2] - 30, L_DECK[1] + 12)),
            C("#8E949B"),
        )
        RR(d, c.r(L_KEYS), 8 * s, C("#3A3F47"))
        kx0, ky0, kx1, ky1 = L_KEYS
        kw, kh = (kx1 - kx0 - 16) / 12, (ky1 - ky0 - 16) / 4
        for rr in range(4):
            for cc in range(12):
                R(
                    d,
                    c.r(
                        (
                            kx0 + 8 + cc * kw + 3,
                            ky0 + 8 + rr * kh + 3,
                            kx0 + 8 + (cc + 1) * kw - 3,
                            ky0 + 8 + (rr + 1) * kh - 3,
                        )
                    ),
                    C("#4E545D"),
                )
        RR(d, c.r(L_PAD), 10 * s, C("#AEB4BB"))
    elif name == "door":
        R(d, (0, hb, W, H), C("#E6DCCB"))
        fy = c.p(0, OCY + 470)[1]
        R(d, (0, fy, W, H), C("#B08D64"))
        for i in range(8):
            d.line(
                (0, fy + 30 + i * 52, W, fy + 30 + i * 52), fill=C("#9E7C55"), width=2
            )
        R(d, c.r(D_FRAME), C("#F7F4EE"))
        R(d, c.r(D_SLAB), C("#2F5D62"))
        for p in D_PANELS:
            R(d, c.r(p), C("#3A6E73"))
            d.rectangle(norm(c.r(inset(p, 12))), outline=C("#264D51"), width=4)
        R(d, c.r(D_SLOT), C("#C9A54B"))
        kx, ky = c.p(OCX + 150, OCY - 25)
        d.ellipse(
            (kx - 16 * s, ky - 16 * s, kx + 16 * s, ky + 16 * s), fill=C("#C9A54B")
        )
    elif name == "book":
        desk(d, hb, C("#C9A27A"), C("#BE966D"))
        RR(d, off(c.r(B_COVER), 12, 16), 10 * s, C("#A8845F"))
        RR(d, c.r(B_COVER), 10 * s, C("#7A2E2E"))
        R(d, c.r(B_LP), C("#FBF8F1"))
        R(d, c.r(B_RP), C("#FBF8F1"))
        R(d, c.r(_o(-6, -272, 6, 272)), C("#D9D2C3"))
        for b in B_BLOCKS:
            y = b[1] + 4
            k = 0
            while y + 9 <= b[3]:
                x1 = b[2] if (k % 6) != 5 else b[0] + (b[2] - b[0]) * 0.55
                R(d, c.r((b[0] + 4, y, x1 - 4, y + 9)), C("#BDB6AA"))
                y += 20
                k += 1
        R(d, c.r(_o(-12, 272, 8, 392)), C("#C9A54B"))
    else:  # bed
        R(d, (0, hb, W, H), C("#D9CBB4"))
        for i in range(13):
            x = c.p(i * 90, 0)[0] - 30
            d.line((x, hb, x, H), fill=C("#CDBEA5"), width=2)
        R(d, c.r(BD_RUG), C("#B5654A"))
        d.rectangle(norm(c.r(inset(BD_RUG, 24))), outline=C("#9A4F38"), width=4)
        for ns in BD_NS:
            R(d, off(c.r(ns), 8, 10), C("#BBAA90"))
            R(d, c.r(ns), C("#8A6A4E"))
        lx, ly = c.p((BD_NS[0][0] + BD_NS[0][2]) / 2, (BD_NS[0][1] + BD_NS[0][3]) / 2)
        d.ellipse(
            (lx - 38 * s, ly - 38 * s, lx + 38 * s, ly + 38 * s), fill=C("#E0CC8F")
        )
        d.ellipse(
            (lx - 30 * s, ly - 30 * s, lx + 30 * s, ly + 30 * s), fill=C("#F2E3B3")
        )
        R(d, c.r(BD_PHONE), C("#1C1C1F"))
        R(d, off(c.r(BD_FRAME), 10, 14), C("#BBAA90"))
        R(d, c.r(BD_FRAME), C("#6B4F3A"))
        R(
            d,
            c.r((BD_FRAME[0], BD_FRAME[1], BD_FRAME[2], BD_FRAME[1] + 30)),
            C("#5A412F"),
        )
        R(d, c.r(BD_DUVET), C("#A8B89A"))
        for i in range(1, 5):
            y = BD_FOLD[3] + i * 110
            d.line(
                c.p(BD_DUVET[0] + 20, y) + c.p(BD_DUVET[2] - 20, y + 8),
                fill=C("#9AAB8C"),
                width=3,
            )
        R(d, c.r(BD_FOLD), C("#F2EFE8"))
        for p in BD_PIL:
            RR(d, c.r(p), 22 * s, C("#E2DED6"))
            RR(d, c.r(inset(p, 4)), 20 * s, C("#FFFFFF"))
    outlines(d, "objects", t, c, only=lambda e: e["obj"] == name)


_cache = {}


def bed_square():
    if "bed" not in _cache:
        im = render_view("objects", 10.99)
        _cache["bed"] = im.crop((0, int(OCY - 540), W, int(OCY + 540)))
    return _cache["bed"]


LAND_COL = C("#BDB6A9")


def draw_zoom(img, d, t):
    R(d, (0, HB["zoom"], W, H), PAPER)
    u = ease_in_out_cubic(prog(t, 11.0, 0.9))
    z = (W / 12) ** (1 - u)
    F0 = cell_center(BED_CELL)
    cx, cy = lerp(W / 2, F0[0], u), lerp(OCY, F0[1], u)
    half = 6 * z
    for rc in LAND_CELLS:
        if rc == BED_CELL:
            continue
        F = cell_center(rc)
        x, y = cx + (F[0] - F0[0]) * z, cy + (F[1] - F0[1]) * z
        if x + half < 0 or x - half > W or y + half < HB["zoom"] or y - half > H:
            continue
        R(
            d,
            (x - half, y - half, x + half, y + half),
            mix(PAPER, LAND_COL, clamp(u * 3)),
        )  # cells fade in as we pull up
    size = max(2, int(round(12 * z)))
    bed = bed_square().resize(
        (size, size), Image.BILINEAR if size < 300 else Image.LANCZOS
    )
    img.paste(bed, (int(round(cx - size / 2)), int(round(cy - size / 2))))
    if t >= 12.0:  # the square pin drops on India
        k = ease_out_back(prog(t, 12.0, 0.3), 2.2)
        px, py = cell_center(PIN_CELL)
        y = py - 20 - 360 * (1 - k)
        R(d, (px - 3, y, px + 3, y + 18), BLUE)  # short stem under the square
        R(d, (px - 17, y - 34, px + 17, y), INK)
        R(d, (px - 14, y - 31, px + 14, y - 3), BLUE)


CR_OUT, CR_F1, CR_F2, CR_ROPE = C("#355E3B"), C("#5C9A45"), C("#67A64F"), C("#F4F1EA")
CR_SQ1, CR_SQ2, CR_CLAY, CR_LINE = (
    C("#8DB85E"),
    C("#9CC46B"),
    C("#D2AE76"),
    C("#FFFFFF"),
)


def draw_cricket(img, d, t):
    hb = HB["cricket"]
    c = cam_cricket(t)
    R(d, (0, hb, W, H), CR_OUT)
    hh = H - hb
    stripes = Image.new("RGB", (W, hh), CR_F1)
    sd = ImageDraw.Draw(stripes)
    for k in range(-12, 12):
        if k % 2 == 0:
            y0, y1 = c.p(0, k * 8.0)[1] - hb, c.p(0, (k + 1) * 8.0)[1] - hb
            if y1 >= 0 and y0 <= hh:
                sd.rectangle((0, max(0, y0), W, min(hh, y1)), fill=CR_F2)
    cx, cy = c.p(0, 0)
    sdist = ellipse_sd(hh, W, hb, cx, cy, CR_RX * c.s, CR_RY * c.s)
    img.paste(stripes, (0, hb), mask_from(0.5 - sdist))
    lw = max(2.5, 0.35 * c.s)
    img.paste(
        CR_ROPE, (0, hb, W, H), mask_from(lw / 2 + 0.5 - np.abs(sdist + 2.2 * c.s))
    )
    R(d, c.r(CR_SQUARE), CR_SQ1)
    for k in range(7):
        x0 = -7 * 1.525 + k * 3.05
        R(d, c.r((x0, -14.0, x0 + 3.05, 14.0)), CR_SQ2 if k % 2 else CR_SQ1)
    R(
        d,
        c.r((-PITCH_HW - 0.25, -PITCH_HL - 2.4, PITCH_HW + 0.25, PITCH_HL + 2.4)),
        CR_CLAY,
    )
    ln = max(2.0, 0.06 * c.s) / c.s
    for sgn in (-1, 1):
        yb, yp = sgn * PITCH_HL, sgn * (PITCH_HL - POP)
        R(d, c.r((-RET, yb - ln / 2, RET, yb + ln / 2)), CR_LINE)  # bowling crease
        R(d, c.r((-1.83, yp - ln / 2, 1.83, yp + ln / 2)), CR_LINE)  # popping crease
        for xr in (-RET, RET):  # return creases, back 8 ft from the popping crease
            ya, yz = sorted((yp, yp + sgn * 2.44))
            R(d, c.r((xr - ln / 2, ya, xr + ln / 2, yz)), CR_LINE)
        R(d, c.r((-0.115, yb - 0.07, 0.115, yb + 0.07)), C("#3B2A1E"))  # stumps
    for sc in CR_SCREENS:
        R(
            d,
            c.r(
                (
                    sc[0] - 1,
                    sc[1] - 1.5 if sc[1] < 0 else sc[1],
                    sc[2] + 1,
                    sc[3] if sc[1] < 0 else sc[3] + 1.5,
                )
            ),
            C("#6E6A62"),
        )
        R(d, c.r(sc), C("#F4F1EA"))
    if t >= 15.5:  # ink dimension lines for 22 yd and 10 ft
        k = ease_out_cubic(prog(t, 15.5, 0.4))
        xd = PITCH_HW + 1.3
        y0, y1 = -PITCH_HL, -PITCH_HL + 2 * PITCH_HL * k
        a, b = c.p(xd, y0), c.p(xd, y1)
        d.line(a + b, fill=INK, width=3)
        for yy in (y0, y1):
            p = c.p(xd, yy)
            d.line((p[0] - 12, p[1], p[0] + 12, p[1]), fill=INK, width=3)
        yd = -PITCH_HL - 1.6
        x0, x1 = -PITCH_HW, -PITCH_HW + 2 * PITCH_HW * k
        a, b = c.p(x0, yd), c.p(x1, yd)
        d.line(a + b, fill=INK, width=3)
        for xx in (x0, x1):
            p = c.p(xx, yd)
            d.line((p[0], p[1] - 12, p[0], p[1] + 12), fill=INK, width=3)
    outlines(d, "cricket", t, c)


TA_OUT, TA_WOOD, TA_PLANK = C("#3E2F22"), C("#8A6440"), C("#7A5636")
TA_STRAW = [C("#CDB97C"), C("#D6C48A")]
TA_WEAVE, TA_HERI = C("#BCA76A"), C("#2B3A2E")


def draw_tatami(img, d, t):
    hb = HB["tatami"]
    c = cam_tatami(t)
    R(d, (0, hb, W, H), TA_OUT)
    R(d, c.r((-0.4, -0.4, 4.4, 4.4)), TA_WOOD)
    for i in range(12):
        x = -0.4 + i * 0.4
        d.line(c.p(x, -0.4) + c.p(x, 4.4), fill=TA_PLANK, width=2)
    R(d, c.r((-0.03, -0.03, 4.03, 4.03)), C("#2A2018"))
    for m in TA_MATS:
        x0, y0, x1, y1 = m
        horiz = (x1 - x0) > (y1 - y0)
        R(d, c.r(m), TA_STRAW[horiz])
        n = int((x1 - x0 if horiz else y1 - y0) / 0.045)
        for i in range(1, n):
            if horiz:
                x = x0 + i * 0.045
                d.line(c.p(x, y0) + c.p(x, y1), fill=TA_WEAVE, width=1)
            else:
                y = y0 + i * 0.045
                d.line(c.p(x0, y) + c.p(x1, y), fill=TA_WEAVE, width=1)
        hw = 0.055
        if horiz:
            R(d, c.r((x0, y0, x1, y0 + hw)), TA_HERI)
            R(d, c.r((x0, y1 - hw, x1, y1)), TA_HERI)
        else:
            R(d, c.r((x0, y0, x0 + hw, y1)), TA_HERI)
            R(d, c.r((x1 - hw, y0, x1, y1)), TA_HERI)
        d.rectangle(norm(c.r(m)), outline=C("#A8935A"), width=1)
    R(d, off(c.r(TA_TABLE), 8, 10), C("#9C8A5A"))
    R(d, c.r(TA_TABLE), C("#4A3020"))
    R(d, c.r(inset(TA_TABLE, 0.06)), C("#5A3B28"))
    for cu in TA_CUSH:
        R(d, c.r(cu), C("#9C3D2E"))
        mx, my = (cu[0] + cu[2]) / 2, (cu[1] + cu[3]) / 2
        R(d, c.r((mx - 0.04, my - 0.04, mx + 0.04, my + 0.04)), C("#7E2F23"))
    outlines(d, "tatami", t, c)


def draw_solar(img, d, t):
    hb = HB["solar"]
    c = cam_solar(t)
    R(d, (0, hb, W, H), C("#CDBB86"))
    for i in range(30):
        y = hb + i * 47 + (i * 13) % 17
        d.line((0, y, W, y), fill=C("#C3B07B"), width=2)
    for r in range(SO_ROWS):
        y = SO_Y0 + r * SO_PITCH
        R(
            d,
            c.r(
                (
                    SO_MODS[0][0] - 6,
                    y + SO_H,
                    SO_MODS[SO_COLS - 1][2] + 6,
                    y + SO_H + 14,
                )
            ),
            C("#A99567"),
        )
    for m in SO_MODS:
        sm = c.r(m)
        R(d, sm, C("#C3C9D0"))
        x0, y0, x1, y1 = inset(sm, 2)
        R(d, (x0, y0, x1, y1), C("#2C3E50"))
        for k in (1, 2, 3):
            x = x0 + (x1 - x0) * k / 4
            d.line((x, y0, x, y1), fill=C("#3F566E"), width=1)
        ym = (y0 + y1) / 2
        d.line((x0, ym, x1, ym), fill=C("#3F566E"), width=1)
    outlines(d, "solar", t, c)


CI_GREYS = [C("#B9BDC2"), C("#8C9196"), C("#CDD0D3"), C("#777C82"), C("#A3A8AD")]


def draw_city(img, d, t):
    hb = HB["city"]
    c = cam_city(t)
    R(d, (0, hb, W, H), C("#45484D"))
    for cc in range(1, CI_COLS):  # dashed centre lines
        x = CI_X0 + cc * (CI_BW + CI_ST) - CI_ST / 2
        for y in range(int(CI_Y0) - 200, H + 200, 34):
            R(d, c.r((x - 1, y, x + 1, y + 16)), C("#C9A84A"))
    for rr in range(1, CI_ROWS):
        y = CI_Y0 + rr * (CI_BH + CI_ST) - CI_ST / 2
        for x in range(-200, W + 200, 34):
            R(d, c.r((x, y - 1, x + 16, y + 1)), C("#C9A84A"))
    for b in CI_BLOCKS:
        x0, y0, x1, y1 = b["rect"]
        R(d, c.r(b["rect"]), C("#B8BBBF"))
        rnd = random.Random(b["seed"])
        if b["park"]:
            R(d, c.r(inset(b["rect"], 6)), C("#7FA36B"))
            for _ in range(7):
                tx, ty = rnd.uniform(x0 + 14, x1 - 24), rnd.uniform(y0 + 14, y1 - 24)
                R(d, c.r((tx, ty, tx + 12, ty + 12)), C("#5E8750"))
            continue
        ix0, iy0, ix1, iy1 = inset(b["rect"], 6)
        if rnd.random() < 0.5:  # split into two or three buildings
            xs = sorted(
                [ix0, ix1]
                + [rnd.uniform(ix0 + 25, ix1 - 25) for _ in range(rnd.randint(1, 2))]
            )
            parts = [
                (
                    xs[i] + (2 if i else 0),
                    iy0,
                    xs[i + 1] - (2 if i + 2 < len(xs) else 0),
                    iy1,
                )
                for i in range(len(xs) - 1)
            ]
        else:
            ys = sorted(
                [iy0, iy1]
                + [rnd.uniform(iy0 + 25, iy1 - 25) for _ in range(rnd.randint(1, 2))]
            )
            parts = [
                (
                    ix0,
                    ys[i] + (2 if i else 0),
                    ix1,
                    ys[i + 1] - (2 if i + 2 < len(ys) else 0),
                )
                for i in range(len(ys) - 1)
            ]
        for p in parts:
            R(d, c.r(p), rnd.choice(CI_GREYS))
            if rnd.random() < 0.5:
                q = inset(p, 8)
                if q[2] - q[0] > 10 and q[3] - q[1] > 10:
                    R(d, c.r(q), rnd.choice(CI_GREYS))
    span_x, span_y = CI_COLS * (CI_BW + CI_ST), CI_ROWS * (CI_BH + CI_ST)
    for vert, lane, s0, v in CI_CABS:
        if vert:
            x = CI_X0 + lane * (CI_BW + CI_ST) - CI_ST / 2 + (4 if v > 0 else -4)
            y = CI_Y0 - CI_ST + (s0 + v * (t - 27.0)) % (span_y + CI_ST)
            R(d, c.r((x - 5, y - 9, x + 5, y + 9)), C("#F2C230"))
        else:
            y = CI_Y0 + lane * (CI_BH + CI_ST) - CI_ST / 2 + (4 if v > 0 else -4)
            x = CI_X0 - CI_ST + (s0 + v * (t - 27.0)) % (span_x + CI_ST)
            R(d, c.r((x - 9, y - 5, x + 9, y + 5)), C("#F2C230"))
    outlines(d, "city", t, c)


def draw_port(img, d, t):
    hb = HB["port"]
    c = cam_port(t)
    R(d, (0, hb, W, H), C("#5B5F63"))
    for cc in range(1, PO_COLS):
        x = PO_X0 + cc * (PO_W + PO_GX) - PO_GX / 2
        for y in range(int(PO_Y0) - 60, int(PO_Y0 + PO_ROWS * (PO_H + PO_GY)) + 60, 30):
            R(d, c.r((x - 1.5, y, x + 1.5, y + 14)), C("#D9B44A"))
    R(
        d,
        c.r((PO_X0 - 20, PO_Y0 - 40, PO_X0 + PO_COLS * (PO_W + PO_GX), PO_Y0 - 36)),
        C("#D9B44A"),
    )
    fall = 0.18
    for k, b in enumerate(PO_BOXES):
        tl = b["t"]
        if t < tl - fall:
            break
        col = PO_COLORS[b["col"]]
        dark = mix(col, (0, 0, 0), 0.25)
        rect = b["rect"]
        if t < tl:  # falling toward its stack from the camera side
            g = 1 + 0.45 * (1 - ease_in_cubic(prog(t, tl - fall, fall)))
            cx, cy = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
            hw, hh = (rect[2] - rect[0]) / 2 * g, (rect[3] - rect[1]) / 2 * g
            rect = (cx - hw, cy - hh, cx + hw, cy + hh)
        else:
            R(d, off(c.r(rect), 5, 7), mix(C("#5B5F63"), (0, 0, 0), 0.35))
        sr = c.r(rect)
        R(d, sr, col)
        x0, y0, x1, y1 = sr
        step = max(5.0, (x1 - x0) / 22)
        x = x0 + step
        while x < x1 - 10:
            d.line((x, y0 + 2, x, y1 - 2), fill=dark, width=1)
            x += step
        R(d, (x1 - 9 * c.s, y0, x1, y1), dark)
        d.rectangle(norm(sr), outline=mix(col, (0, 0, 0), 0.45), width=1)
        if t >= tl:
            dashed_rect(d, sr, t, t - tl, 2, view_top("port"))


FL_WALL, FL_SHADOW = C("#E4DED2"), C("#CFC7B8")


def draw_flag(d, i, box):
    name, (rh, rw), o, cols = FLAGS[i]
    x0, y0, x1, y1 = box
    if (
        o == "x"
    ):  # Switzerland: square, 32-unit grid, arms 7 long and 6 wide (one-sixth longer than wide)
        R(d, box, C(cols[0]))
        u = (x1 - x0) / 32
        R(d, (x0 + 13 * u, y0 + 6 * u, x0 + 19 * u, y0 + 26 * u), C(cols[1]))
        R(d, (x0 + 6 * u, y0 + 13 * u, x0 + 26 * u, y0 + 19 * u), C(cols[1]))
        return
    for k, col in enumerate(cols):
        if o == "v":
            R(d, (x0 + (x1 - x0) * k / 3, y0, x0 + (x1 - x0) * (k + 1) / 3, y1), C(col))
        else:
            R(d, (x0, y0 + (y1 - y0) * k / 3, x1, y0 + (y1 - y0) * (k + 1) / 3), C(col))


def flag_box(i, t):
    k = ease_out_back(prog(t, 36.0 + 0.04 * i, 0.22))
    x0, y0, x1, y1 = FL_RECTS[i]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    g = 0.8 + 0.2 * k
    return (
        cx - (x1 - x0) / 2 * g,
        cy - (y1 - y0) / 2 * g,
        cx + (x1 - x0) / 2 * g,
        cy + (y1 - y0) / 2 * g,
    )


def draw_flags(img, d, t):
    hb = HB["flags"]
    R(d, (0, hb, W, H), FL_WALL)
    for i in range(len(FLAGS)):
        if i == SWISS and t >= 39.0:
            R(
                d, off(FL_RECTS[i], 0, 0), C("#D9D2C4")
            )  # the empty slot it lifted out of
            continue
        b = flag_box(i, t)
        R(d, off(b, 5, 7), FL_SHADOW)
        draw_flag(d, i, b)
    outlines(d, "flags", t, IDENT, only=lambda e: e["rect"] != SW_LIFT)
    if t >= 39.0:
        k = ease_in_out_cubic(prog(t, 39.0, 0.5))
        view = img.crop((0, hb + 4, W, H))
        img.paste(
            Image.blend(view, Image.new("RGB", view.size, FL_WALL), 0.5 * k),
            (0, hb + 4),
        )
        a, b = FL_RECTS[SWISS], SW_LIFT
        box = tuple(lerp(a[j], b[j], k) for j in range(4))
        sh = 6 + 18 * k
        R(d, off(box, sh * 0.6, sh), mix(FL_WALL, (0, 0, 0), 0.16))
        draw_flag(d, SWISS, box)
        outlines(d, "flags", t, IDENT, only=lambda e: e["rect"] == SW_LIFT)


def nepal_points():
    """Flag of Nepal construction (A, B, E, G, C) in units of the base AB, y up from A."""
    s2 = 1 / math.sqrt(2)
    return [(0.0, 0.0), (1.0, 0.0), (1 - s2, s2), (1.0, s2), (0.0, 4 / 3)]


def offset_polygon(pts, dist):
    n = len(pts)
    area = sum(
        pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
        for i in range(n)
    )
    sgn = 1 if area > 0 else -1
    out = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]

        def nrm(a, b):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy)
            return (sgn * dy / L, -sgn * dx / L)

        n1, n2 = nrm(p0, p1), nrm(p1, p2)
        k = 1 + n1[0] * n2[0] + n1[1] * n2[1]
        out.append(
            (p1[0] + dist * (n1[0] + n2[0]) / k, p1[1] + dist * (n1[1] + n2[1]) / k)
        )
    return out


def nepal_tile():
    if "nepal" in _cache:
        return _cache["nepal"]
    L, bd = NP_L, NP_BORDER
    base = nepal_points()
    outer_u = offset_polygon(base, bd / L)
    xs, ys = [p[0] for p in outer_u], [p[1] for p in outer_u]
    minx, maxy = min(xs), max(ys)
    tw, th = (max(xs) - minx) * L + 40, (maxy - min(ys)) * L + 40

    def to(p, ss):
        return ((p[0] - minx) * L * ss + 10 * ss, (maxy - p[1]) * L * ss + 10 * ss)

    def paint(dr, ss):
        dr.polygon(
            [(x + 10 * ss, y + 14 * ss) for x, y in (to(p, ss) for p in outer_u)],
            fill=FL_SHADOW + (255,),
        )
        dr.polygon([to(p, ss) for p in outer_u], fill=C("#003893") + (255,))
        dr.polygon([to(p, ss) for p in base], fill=C("#DC143C") + (255,))
        wh = (255, 255, 255, 255)
        cr = C("#DC143C") + (255,)
        mx, my = to((0.22, 0.93), ss)
        r = 0.11 * L * ss
        dr.ellipse(
            (mx - r, my - r, mx + r, my + r), fill=wh
        )  # crescent: disc minus a raised crimson disc
        r2 = 0.105 * L * ss
        dr.ellipse(
            (mx - r2, my - r2 - 0.045 * L * ss, mx + r2, my + r2 - 0.045 * L * ss),
            fill=cr,
        )
        sx, sy = to((0.22, 0.975), ss)
        rs = 0.045 * L * ss
        dr.pieslice((sx - rs, sy - rs, sx + rs, sy + rs), 180, 360, fill=wh)
        for j in range(8):  # rays of the moon
            a = math.radians(180 + 11 + j * (158 / 7))
            tip = (sx + math.cos(a) * rs * 1.9, sy + math.sin(a) * rs * 1.9)
            l = (
                sx + math.cos(a - 0.18) * rs * 1.05,
                sy + math.sin(a - 0.18) * rs * 1.05,
            )
            rr = (
                sx + math.cos(a + 0.18) * rs * 1.05,
                sy + math.sin(a + 0.18) * rs * 1.05,
            )
            dr.polygon([l, tip, rr], fill=wh)
        ux, uy = to((0.22, 0.30), ss)
        ru = 0.085 * L * ss
        dr.ellipse((ux - ru, uy - ru, ux + ru, uy + ru), fill=wh)
        for j in range(12):  # rays of the sun
            a = math.radians(j * 30)
            tip = (ux + math.cos(a) * ru * 1.6, uy + math.sin(a) * ru * 1.6)
            l = (ux + math.cos(a - 0.2) * ru * 0.95, uy + math.sin(a - 0.2) * ru * 0.95)
            rr = (
                ux + math.cos(a + 0.2) * ru * 0.95,
                uy + math.sin(a + 0.2) * ru * 0.95,
            )
            dr.polygon([l, tip, rr], fill=wh)

    tile = ss_tile(tw, th, paint)
    ox, oy = to((minx, maxy), 1)
    bx = to((max(xs), min(ys)), 1)
    _cache["nepal"] = (tile, (bx[0] - ox, bx[1] - oy), (ox, oy))
    return _cache["nepal"]


def nepal_box(dy=0.0):
    tile, (bw, bh), (ox, oy) = nepal_tile()
    x0, y0 = NP_CX - bw / 2, NP_CY - bh / 2 + dy
    return (x0, y0, x0 + bw, y0 + bh), (x0 - ox, y0 - oy)


def draw_nepal(img, d, t):
    hb = HB["nepal"]
    R(d, (0, hb, W, H), FL_WALL)
    k = ease_out_back(prog(t, 42.0, 0.45), 1.3)
    dy = -1100 * (1 - k)
    tile = nepal_tile()[0]
    box, (tx, ty) = nepal_box(dy)
    img.paste(tile, (int(round(tx)), int(round(ty))), tile)
    rest, _ = nepal_box(0)
    failed_outline(d, t, inset(rest, -12), 42.5, 44.0, seed=42)


def a_sheet(d, b, shadow=True):
    if shadow:
        R(d, off(b, 8, 10), C("#D3CCBE"))
    R(d, b, WHITE)


def flap(d, hinge, a, b, th, horiz):
    """A half-sheet folding over a hinge. horiz: hinge is horizontal at y=hinge, flap spans x a..b and folds down."""
    th = math.pi * th
    co, si = math.cos(th), math.sin(th)
    face = (
        (255 - int(40 * si),) * 2 + (252 - int(40 * si),)
        if co >= 0
        else (236 + int(14 * -co), 233 + int(14 * -co), 226 + int(14 * -co))
    )
    if horiz:
        x0, x1, y_free_len = a[0], a[1], b
        yf = hinge - y_free_len * co
        cx, hw = (x0 + x1) / 2, (x1 - x0) / 2 * (1 + 0.12 * si)
        d.polygon([(x0, hinge), (x1, hinge), (cx + hw, yf), (cx - hw, yf)], fill=face)
    else:
        y0, y1, x_free_len = a[0], a[1], b
        xf = hinge - x_free_len * co
        cy, hh = (y0 + y1) / 2, (y1 - y0) / 2 * (1 + 0.12 * si)
        d.polygon([(hinge, y0), (hinge, y1), (xf, cy + hh), (xf, cy - hh)], fill=face)


DIAG = C("#77736C")


def draw_fold(img, d, t):
    hb = HB["fold"]
    R(d, (0, hb, W, H), C("#E9E3D6"))
    for b, t0 in (
        (A4, 45.5),
        (A5, 46.5),
        (A6, 47.5),
    ):  # nested-ratio diagram, built as each sheet folds
        if t >= t0:
            d.rectangle(norm(b), outline=DIAG, width=3)
    (f1a, f1b), (f2a, f2b), (f3a, f3b) = FOLDS
    yh1, xh2, yh3 = A5[1], A6[0], A7[1]
    if t < f1a:
        a_sheet(d, A4)
    elif t < f1b:
        a_sheet(d, A5)
        flap(
            d,
            yh1,
            (A4[0], A4[2]),
            yh1 - A4[1],
            ease_in_out_cubic(prog(t, f1a, f1b - f1a)),
            True,
        )
    elif t < f2a:
        a_sheet(d, A5)
    elif t < f2b:
        a_sheet(d, A6)
        flap(
            d,
            xh2,
            (A5[1], A5[3]),
            xh2 - A5[0],
            ease_in_out_cubic(prog(t, f2a, f2b - f2a)),
            False,
        )
    elif t < f3a:
        a_sheet(d, A6)
    elif t < f3b:
        a_sheet(d, A7)
        flap(
            d,
            yh3,
            (A6[0], A6[2]),
            yh3 - A6[1],
            ease_in_out_cubic(prog(t, f3a, f3b - f3a)),
            True,
        )
    else:
        a_sheet(d, A7)
    for (fa, fb), (p, q) in zip(
        FOLDS,
        [
            ((A4[0], yh1), (A4[2], yh1)),
            ((xh2, A5[1]), (xh2, A5[3])),
            ((A6[0], yh3), (A6[2], yh3)),
        ],
    ):
        if fa - 0.3 <= t < fb:  # the hinge line draws across before each fold
            k = ease_out_cubic(prog(t, fa - 0.3, 0.25))
            d.line(
                (p[0], p[1], lerp(p[0], q[0], k), lerp(p[1], q[1], k)),
                fill=INK,
                width=4,
            )
    outlines(d, "fold", t, IDENT)


def pizza_tile():
    if "pizza" in _cache:
        return _cache["pizza"]
    r = PZ_R
    sz = 2 * r + 20

    def paint(dr, ss):
        c0 = (sz / 2 * ss, sz / 2 * ss)

        def circ(cx, cy, rad, col):
            dr.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=col + (255,))

        circ(c0[0] + 8 * ss, c0[1] + 12 * ss, r * ss, C("#CFC7B8"))
        circ(*c0, r * ss, C("#D9A55B"))
        circ(*c0, (r - 26) * ss, C("#C2452D"))
        circ(*c0, (r - 36) * ss, C("#F2D27A"))
        rnd = random.Random(49)
        for _ in range(18):
            a, q = rnd.uniform(0, 2 * math.pi), rnd.uniform(0, r - 70)
            circ(
                c0[0] + math.cos(a) * q * ss,
                c0[1] + math.sin(a) * q * ss,
                rnd.uniform(14, 30) * ss,
                C("#F6DE95"),
            )
        for k in range(6):
            a = math.radians(k * 60 + 20)
            dr.line(
                (
                    c0[0],
                    c0[1],
                    c0[0] + math.cos(a) * (r - 30) * ss,
                    c0[1] + math.sin(a) * (r - 30) * ss,
                ),
                fill=C("#C9944E") + (255,),
                width=int(4 * ss),
            )
        for k in range(9):
            a = math.radians(k * 40 + rnd.uniform(-8, 8))
            q = (r - 95) * (0.35 + 0.6 * (k % 3) / 2)
            circ(
                c0[0] + math.cos(a) * q * ss,
                c0[1] + math.sin(a) * q * ss,
                30 * ss,
                C("#A8322A"),
            )
            circ(
                c0[0] + math.cos(a) * q * ss - 6 * ss,
                c0[1] + math.sin(a) * q * ss - 6 * ss,
                9 * ss,
                C("#BF4A3F"),
            )
        for k in range(3):
            a = math.radians(k * 120 + 75)
            x, y = c0[0] + math.cos(a) * 95 * ss, c0[1] + math.sin(a) * 95 * ss
            dr.ellipse(
                (x - 20 * ss, y - 11 * ss, x + 20 * ss, y + 11 * ss),
                fill=C("#4E8B3A") + (255,),
            )

    _cache["pizza"] = ss_tile(sz, sz, paint)
    return _cache["pizza"]


BOX_IN, BOX_OUT, BOX_EDGE = C("#DDBF93"), C("#C49A66"), C("#A9825A")


def draw_box_base(d, dy):
    R(d, off(BOX, 10, 14 + dy), C("#CFC7B8"))
    R(d, off(BOX, 0, dy), BOX_EDGE)
    R(d, off(inset(BOX, 14), 0, dy), C("#B88E5E"))


def draw_open_lid(d, dy, th):
    """Lid hinged on the base's bottom edge; th = 0 lies open below, th = 1 closed on top."""
    hy = BOX[3] + dy
    L = BOX[3] - BOX[1]
    a = math.pi * th
    co, si = math.cos(a), math.sin(a)
    yf = hy + L * co
    cx, hw = (BOX[0] + BOX[2]) / 2, (BOX[2] - BOX[0]) / 2 * (1 + 0.14 * si)
    face = (
        mix(BOX_IN, (0, 0, 0), 0.18 * si)
        if co >= 0
        else mix(BOX_OUT, (0, 0, 0), 0.18 * si)
    )
    d.polygon([(BOX[0], hy), (BOX[2], hy), (cx + hw, yf), (cx - hw, yf)], fill=face)
    if co < 0 and th >= 1:
        d.rectangle(norm(off(BOX, 0, dy)), outline=BOX_EDGE, width=6)


def draw_pizza(img, d, t, lid=False):
    hb = HB["pizza"]
    R(d, (0, hb, W, H), C("#E9E3D6"))
    dy = 0.0
    if t >= 51.5:
        dy = 760 * (1 - ease_out_cubic(prog(t, 51.5, 0.45)))
    th = ease_in_cubic(prog(t, 52.5, 0.5)) if lid else 0.0
    if t >= 51.5:
        draw_box_base(d, dy)
        if th < 0.5:
            draw_open_lid(d, dy, th)
    tile = pizza_tile()
    img.paste(
        tile, (int(PZ_C[0] - tile.width / 2), int(PZ_C[1] - tile.height / 2)), tile
    )
    if th >= 0.5:
        draw_open_lid(d, dy, th)
    if lid and t >= 53.0:
        R(d, BOX, BOX_OUT)
        R(d, (BOX[0], BOX[3] - 10, BOX[2], BOX[3]), BOX_EDGE)
        d.line(
            (BOX[0] + 30, BOX[1] + 90, BOX[2] - 30, BOX[1] + 90),
            fill=mix(BOX_OUT, (0, 0, 0), 0.1),
            width=3,
        )
        outlines(d, "lid", t, IDENT)
    if not lid:
        pz = (PZ_C[0] - PZ_R, PZ_C[1] - PZ_R, PZ_C[0] + PZ_R, PZ_C[1] + PZ_R)
        failed_outline(d, t, inset(pz, -14), 49.5, 50.0, seed=50, bend=0.85)


def draw_lid(img, d, t):
    draw_pizza(img, d, t, lid=True)


def inner_film():
    if "inner" not in _cache:
        _cache["inner"] = render_view("lid", 53.99)
    return _cache["inner"]


SKIN, SKIN_SH = C("#E3A983"), C("#C98E68")


def draw_pullback(img, d, t):
    R(d, (0, 0, W, H), PAPER)
    u = ease_in_out_cubic(prog(t, 54.0, 0.75))
    s = (W / (PB_SCREEN[2] - PB_SCREEN[0])) ** (1 - u)
    c = Cam(s, PB_PIVOT[0], PB_PIVOT[1], PB_PIVOT[0], PB_PIVOT[1])
    sq = ease_in_out_cubic(prog(t, 57.0, 0.25))  # the hand squares off
    rad = lambda r0: r0 * (1 - sq)  # noqa: E731
    hy = 900 * (
        1 - ease_out_cubic(prog(t, 54.0, 0.75))
    )  # the hand rises into place, off-screen at the cut
    RR(d, c.r(off(PB_PALM, 0, hy)), rad(150) * s, SKIN)
    RR(d, off(c.r(PB_BODY), 10 * s, 14 * s), 44 * s, C("#D6D0C4"))
    RR(d, c.r(PB_BODY), 44 * s, C("#1C1C1F"))
    sr = [int(round(v)) for v in c.r(PB_SCREEN)]
    film = inner_film()
    fw, fh = sr[2] - sr[0], sr[3] - sr[1]
    if fw >= W - 1:
        img.paste(film, (0, 0))
    else:
        img.paste(film.resize((fw, fh), Image.LANCZOS), (sr[0], sr[1]))
    for f in PB_FINGERS + [PB_THUMB]:
        f = off(f, 0, hy)
        RR(d, c.r(f), rad(36) * s + 2, SKIN_SH)
        RR(d, c.r(inset(f, 3)), rad(33) * s, SKIN)
    hand = (min(r[0] for r in PB_FINGERS), PB_FINGERS[0][1], PB_THUMB[2], PB_PALM[3])
    failed_outline(d, t, inset(hand, -10), 56.0, 56.5, seed=56)
    outlines(d, "pullback", t, c)


def draw_end(img, d, t):
    outlines(d, "end", t, IDENT)


def draw_hook(img, d, t):
    pass


DRAW = {
    "hook": draw_hook,
    "objects": draw_objects,
    "zoom": draw_zoom,
    "cricket": draw_cricket,
    "tatami": draw_tatami,
    "solar": draw_solar,
    "city": draw_city,
    "port": draw_port,
    "flags": draw_flags,
    "nepal": draw_nepal,
    "fold": draw_fold,
    "pizza": draw_pizza,
    "lid": draw_lid,
    "pullback": draw_pullback,
    "end": draw_end,
}


def render_view(name, t):
    """The picture without any text: world, outlines and the paper header panel."""
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    DRAW[name](img, d, t)
    header(img, d, name)
    return img


def draw(t):
    name, lt, k = E.scene_at(t, SCHEDULE)
    img = render_view(name, t)
    for it in text_items(t):
        put_text(
            img,
            it["text"],
            it["x"],
            it["y"],
            it["size"],
            it["bold"],
            it["color"],
            it["track"],
            it["clip"],
        )
    return img
