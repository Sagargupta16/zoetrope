# scenes.py : "Salt and Signal" opening credits (S-g11-movie-credits).
# draw(t) is pure: same t -> same pixels. All timing lives in SCHEDULE (60 BPM, bar = 4 s) and the
# beam clock below, which score.py imports too. lru_caches hold only static layers.
from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import engine as E
from engine import (
    clamp,
    ease_in_cubic,
    ease_in_out_cubic,
    ease_out_back,
    ease_out_cubic,
    ease_out_expo,
    prog,
)

E.W, E.H, E.FPS, E.SS = 1920, 1080, 24, 1
W, H, FPS = E.W, E.H, E.FPS
BPM = 60
BEAT = 60 / BPM
BAR = 4 * BEAT

SCHEDULE = {  # seconds; every boundary is a bar line
    "studio": (0.0, 8.0),
    "association": (8.0, 12.0),
    "director": (12.0, 16.0),
    "starring": (16.0, 28.0),
    "title": (28.0, 40.0),
    "crew": (40.0, 52.0),
    "directed": (52.0, 56.0),
    "begins": (56.0, 60.0),
}
DURATION = 60.0


def col(h: str) -> np.ndarray:
    return np.array(E.hexrgb(h)[:3], np.float32)


SKY_TOP, SKY_HOR, SEA = col("#1d2b44"), col("#3a4d6b"), col("#101a2a")
AMBER, CREAM, ASH = col("#ECA64E"), col("#EFE7DA"), col("#968C80")
WARM = np.array([255, 234, 200], np.float32)  # flare tint while the beam is on a letter
ASH_WARM = np.array([222, 192, 150], np.float32)
HALO = np.array([6, 10, 18], np.float32)
SIL = col("#0a111c")
RIPPLE = col("#2c3d5a")
RAIN = np.array([170, 186, 208], np.float32)
BRASS, BRASS_D = (104, 74, 40), (64, 46, 26)
BRASS_L = (236, 166, 78)

# ---- frame geometry: 2.39:1 picture inside 1920x1080 (1920 / 2.39 = 803.3 -> 804 rows) ----
PY0, PH = 138, 804
HZ = 500  # horizon, absolute y
HZL = HZ - PY0
SEA_H = PH - HZL
LAMP = (1500.0, 308.0)
BOAT = (330.0, 497.0)
LENS_C = (700.0, 520.0)


def smooth(e0: float, e1: float, x: float) -> float:
    k = clamp((x - e0) / (e1 - e0))
    return k * k * (3 - 2 * k)


# ---- the beam clock: one full turn per bar, a pinhole projection of a horizontal beam ----
F_CAM, CX = 1400.0, 960.0
LXW, LYW = (LAMP[0] - CX) / F_CAM, (HZ - LAMP[1]) / F_CAM
BEAM_D = 3.0
A0, OMEGA = (
    45.0,
    90.0,
)  # azimuth in degrees at every bar line; 90 deg/s = one turn per bar


def tip(a_deg):
    """Screen position of the beam's far end for azimuth a (0 = right, 90 = away from camera)."""
    a = np.radians(a_deg)
    z = 1 + BEAM_D * np.sin(a)
    return CX + F_CAM * (LXW + BEAM_D * np.cos(a)) / z, HZ - F_CAM * LYW / z


_AT = np.linspace(2.0, 178.0, 4000)
_XT = tip(_AT)[0]  # strictly decreasing: the far end sweeps right to left


def a_at_x(x: float) -> float:
    return float(np.interp(x, _XT[::-1], _AT[::-1]))


def pass_u(x: float) -> float:
    """Seconds after a bar line when the beam's far end crosses screen x."""
    return (a_at_x(x) - A0) / OMEGA


A_STOP = a_at_x(BOAT[0])  # the beam comes to rest on the boat in the last bar
T_SETTLE = 2 * (A_STOP - A0) / OMEGA


def azimuth(t: float) -> float:
    if t < 56.0:
        return (A0 + OMEGA * t) % 360.0
    tau = t - 56.0
    if tau >= T_SETTLE:
        return A_STOP
    return A0 + OMEGA * tau - 0.5 * (OMEGA / T_SETTLE) * tau * tau


def far_env(a: float) -> float:
    return smooth(5, 30, a) * (1 - smooth(150, 178, a)) if a <= 180 else 0.0


def glare(a: float) -> float:
    return math.exp(-(((a - 270.0) / 30.0) ** 2))


def shimmer_times() -> list[float]:
    """Beam passes across picture centre (score.py puts a shimmer on each)."""
    u = pass_u(CX)
    return [4.0 * k + u for k in range(15) if k not in (10, 11, 12, 14)]


def ramp52(t: float) -> float:
    return smooth(52.0, 54.0, t) * (1 - smooth(54.0, 56.0, t))


def rain_amt(t: float) -> float:
    return smooth(28.0, 31.5, t) if 28.0 <= t < 40.0 else 0.0


def swell(t: float) -> float:
    if 28.0 <= t < 40.0:
        return 1 + 1.3 * smooth(28.0, 32.0, t)
    if 52.0 <= t < 56.0:
        return 1.15 - 0.15 * smooth(54.0, 56.0, t)
    return 1.0


def title_dim(t: float) -> float:
    return (
        smooth(31.4, 32.4, t) * (1 - smooth(39.3, 40.0, t)) if 28.0 <= t < 40.0 else 0.0
    )


def beam_params(t: float) -> tuple[float, float]:
    if t < 32.0:
        return 1.0, 1.0
    if t < 40.0:
        return 0.7, 1.0
    if t < 56.0:
        r = ramp52(t)
        return 1.0 + 0.45 * r, 1.0 + 1.5 * r
    return 1.0 - 0.1 * smooth(56.0, 57.5, t), 1.0 + 0.15 * smooth(56.0, 57.0, t)


def lamp_extra(t: float, a: float) -> float:
    x = 1.1 * glare(a) if t < 56.0 else 0.0
    if 30.0 <= t < 34.0:
        x += 0.9 * smooth(30.0, 32.0, t) * (1 - smooth(32.2, 33.6, t))
    if 52.0 <= t < 56.0:
        x += 1.0 * ramp52(t)
    return x


# ---- text ----
NAME, ROLE, TITLE, TYPED = "name", "role", "title", "typed"
TRACK = {NAME: 0.26, ROLE: 0.05, TITLE: 0.2, TYPED: 0.0}


def fnt(kind: str, size: int):
    return E.font(size, bold=kind in (NAME, TITLE))


def credit(lines, cx, reveal, exit_t, exit_dur=0.5):
    return dict(lines=lines, cx=cx, reveal=reveal, exit=exit_t, exit_dur=exit_dur)


TYPE_T0, TYPE_T1 = 56.5, 57.9
CREDITS = {
    "studio": credit(
        [([("SALTGLASS PICTURES", NAME, 64)], 668)], 690, ("beam", 0), 7.5
    ),
    "presents": credit([([("presents", ROLE, 44)], 742)], 690, ("beam", 1), 7.5),
    "assoc": credit(
        [
            ([("in association with", ROLE, 42)], 630),
            ([("NORTHLIGHT & TIDE", NAME, 64)], 712),
        ],
        690,
        ("beam", 2),
        11.5,
    ),
    "director": credit(
        [([("a", ROLE, 46), ("MAREN HOLLOWAY", NAME, 64), ("film", ROLE, 46)], 700)],
        690,
        ("beam", 3),
        15.5,
    ),
    "idris": credit([([("IDRIS VALE", NAME, 62)], 616)], 470, ("beam", 4), 20.4),
    "nora": credit([([("NORA KESTREL", NAME, 62)], 846)], 880, ("beam", 5), 24.4),
    "benno": credit([([("BENNO STRAND", NAME, 62)], 730)], 610, ("beam", 6), 28.4),
    "title": credit(
        [([("SALT AND SIGNAL", TITLE, 84)], 549)], LENS_C[0], ("lens", 32.3), 39.5
    ),
    "directed": credit(
        [([("directed by", ROLE, 46)], 650), ([("MAREN HOLLOWAY", NAME, 76)], 742)],
        690,
        ("beam", 13),
        55.5,
    ),
    "typed": credit(
        [([("Someone is still out there.", TYPED, 52)], 752)],
        760,
        ("type", TYPE_T0, TYPE_T1),
        None,
    ),
}
CREW = [
    ("music by", "OREN BALLARD"),
    ("cinematography by", "TESSA LIND"),
    ("edited by", "KAI MORROW"),
    ("production design by", "JUNE ASHFORD"),
    ("written by", "LEO VANCE"),
    ("produced by", "HANNA ROOK"),
]
BAND_X0, BAND_V, BAND_LEAD = (
    2020.0,
    4200.0,
    0.1,
)  # interior light band: enters at slot - 0.1 s
for _k, (_role, _name) in enumerate(CREW):
    _ts = 40.0 + 2 * _k
    _rb, _nb = (404, 478) if _k % 2 == 0 else (640, 714)
    CREDITS[f"crew{_k}"] = credit(
        [([(_role, ROLE, 42)], _rb), ([(_name, NAME, 58)], _nb)],
        1290,
        ("band", _ts),
        52.0 if _k == 5 else _ts + 3.5,
        0.35
        if _k == 5
        else 0.3,  # crew5 gone by 52.35, before "directed by" starts lighting
    )
INTERIOR_CREDITS = [f"crew{k}" for k in range(len(CREW))]
EXTERIOR_CREDITS = [c for c in CREDITS if c not in INTERIOR_CREDITS]


@lru_cache(None)
def layout(cid: str):
    """Glyphs at rest: (text, x, y_la, kind, size, line). Absolute coords, anchor 'la' (qa.text_box convention)."""
    C = CREDITS[cid]
    out = []
    for li, (runs, base) in enumerate(C["lines"]):
        widths = []
        for text, kind, size in runs:
            f, tr = fnt(kind, size), TRACK[kind] * size
            widths.append(
                f.getlength(text)
                if kind == TYPED
                else sum(f.getlength(ch) for ch in text) + tr * (len(text) - 1)
            )
        # word gap between runs on one line (a / NAME / film): half the larger size, so italics do not crowd caps
        gaps = [0.5 * max(a[2], b[2]) for a, b in zip(runs, runs[1:])]
        x = C["cx"] - (sum(widths) + sum(gaps)) / 2
        for ri, (text, kind, size) in enumerate(runs):
            if ri:
                x += gaps[ri - 1]
            f, tr = fnt(kind, size), TRACK[kind] * size
            asc = f.getmetrics()[0]
            if kind == TYPED:
                out.append((text, x, base - asc, kind, size, li))
                x += f.getlength(text)
                continue
            for ch in text:
                if ch != " ":
                    out.append((ch, x, base - asc, kind, size, li))
                x += f.getlength(ch) + tr
            x -= tr
    return tuple(out)


@lru_cache(None)
def glyph_boxes(cid: str):
    res = []
    for text, x, y, kind, size, _ in layout(cid):
        l, t_, r, b = fnt(kind, size).getbbox(text)
        res.append((x + l, y + t_, x + r, y + b))
    return tuple(res)


@lru_cache(None)
def reveal_times(cid: str):
    C = CREDITS[cid]
    kind = C["reveal"][0]
    out = []
    for l, _, r, _ in glyph_boxes(cid):
        xc = (l + r) / 2
        if kind == "beam":
            out.append(BAR * C["reveal"][1] + pass_u(xc))
        elif kind == "band":
            out.append(C["reveal"][1] - BAND_LEAD + (BAND_X0 - xc) / BAND_V)
        else:
            out.append(C["reveal"][1])
    return tuple(out)


def fully_drawn(cid: str) -> float:
    """Time the whole block is fully visible and settled (gate 4 uses this)."""
    C = CREDITS[cid]
    kind = C["reveal"][0]
    if kind in ("beam", "band"):
        return max(reveal_times(cid)) + 0.12
    if kind == "lens":
        return C["reveal"][1] + 1.4
    return C["reveal"][2]


def flare(t: float, tp: float, period: float) -> float:
    s = 0.0
    for m in range(4):
        d = t - (tp + m * period)
        if d < -0.06:
            break
        s += (
            (1.0 if m == 0 else 0.35)
            * min(1.0, (d + 0.06) / 0.1)
            * math.exp(-max(d, 0.0) / 0.75)
        )
    return s


def states(cid: str, t: float):
    """Per-glyph (alpha, flare) plus spread, blur and typed character count; None when invisible."""
    C = CREDITS[cid]
    kind = C["reveal"][0]
    n = len(layout(cid))
    ex = C["exit"]
    if ex is not None and t >= ex + C["exit_dur"]:
        return None
    e = ease_in_cubic(prog(t, ex, C["exit_dur"])) if ex is not None else 0.0
    spread, blur, chars = 1 + 0.06 * e, 0.0, None
    tps = reveal_times(cid)
    if kind in ("beam", "band"):
        if t < min(tps) - 0.06:
            return None
        period = BAR if kind == "beam" else 2.0
        al = [ease_out_cubic(prog(t, tp - 0.05, 0.17)) * (1 - e) for tp in tps]
        fl = [flare(t, tp, period) for tp in tps]
    elif kind == "lens":
        t0 = C["reveal"][1]
        if t < t0:
            return None
        k = ease_out_cubic(prog(t, t0, 1.0))
        al = [k * (1 - e)] * n
        fl = [1.0 - 0.8 * ease_out_cubic(prog(t, t0, 2.0))] * n
        spread *= 1 + 0.45 * (1 - ease_out_cubic(prog(t, t0, 1.4)))
        blur = 7.0 * (1 - k)
    else:
        t0, t1 = C["reveal"][1], C["reveal"][2]
        if t < t0:
            return None
        total = len(layout(cid)[0][0])
        chars = min(total, 1 + int((t - t0) / ((t1 - t0) / (total - 1)) + 1e-6))
        al, fl = [1.0] * n, [0.0] * n
    return al, fl, spread, blur, chars


def soft(im: Image.Image, r: float) -> np.ndarray:
    w, h = im.size
    s = im.resize((max(1, w // 2), max(1, h // 2)), Image.BILINEAR)
    s = s.filter(ImageFilter.GaussianBlur(r / 2)).resize((w, h), Image.BILINEAR)
    return np.asarray(s, np.float32) / 255


def render_credit(P: np.ndarray, cid: str, t: float) -> None:
    st = states(cid, t)
    if st is None:
        return
    al, fl, spread, blur, chars = st
    if max(al) <= 0.002:
        return
    C = CREDITS[cid]
    G, B = layout(cid), glyph_boxes(cid)
    cx = C["cx"]
    dxs = [(cx + ((b[0] + b[2]) / 2 - cx) * spread) - (b[0] + b[2]) / 2 for b in B]
    pad = 48
    x0 = int(min(b[0] + d for b, d in zip(B, dxs))) - pad
    x1 = (
        int(max(b[2] + d for b, d in zip(B, dxs)))
        + pad
        + (30 if chars is not None else 0)
    )
    y0 = int(min(b[1] for b in B)) - pad
    y1 = int(max(b[3] for b in B)) + pad
    x0, x1 = max(0, x0), min(W, x1)
    y0, y1 = max(PY0, y0), min(PY0 + PH, y1)
    size = (x1 - x0, y1 - y0)
    A = Image.new("L", size, 0)
    Gm = Image.new("L", size, 0)
    RGB = Image.new("RGB", size, tuple(int(v) for v in CREAM))
    dA, dG, dC = ImageDraw.Draw(A), ImageDraw.Draw(Gm), ImageDraw.Draw(RGB)
    for (text, x, y, kind, sz, _), b, d, a, f in zip(G, B, dxs, al, fl):
        if a <= 0.002:
            continue
        ft = fnt(kind, sz)
        if kind == TYPED:
            s = text[:chars]
            dA.text((x - x0, y - y0), s, font=ft, fill=255)
            dG.text((x - x0, y - y0), s, font=ft, fill=30)
            dC.rectangle((0, 0, size[0], size[1]), fill=tuple(int(v) for v in CREAM))
            cx_ = x + ft.getlength(s) + 6
            on = t < TYPE_T1 or ((t - TYPE_T1) % 1.0) < 0.5
            if on:
                cb = (cx_ - x0, b[1] - y0 - 2, cx_ - x0 + 3, b[3] - y0 + 2)
                dA.rectangle(cb, fill=230)
                dC.rectangle(cb, fill=tuple(int(v) for v in AMBER))
            continue
        k = min(1.0, f)
        if kind == ROLE:
            c = ASH * (1 - 0.8 * k) + ASH_WARM * (0.8 * k)
        else:
            c = CREAM * (1 - k) + WARM * k
        glow = (0.16 + 0.8 * k) if kind != TITLE else max(0.18, f)
        gx = x + d - x0
        dA.text((gx, y - y0), text, font=ft, fill=int(round(255 * a)))
        dG.text((gx, y - y0), text, font=ft, fill=int(round(255 * a * min(1.0, glow))))
        dC.rectangle(  # this glyph's colour, limited to its own line so stacked lines keep theirs
            (b[0] + d - x0 - 3, b[1] - y0 - 4, b[2] + d - x0 + 3, b[3] - y0 + 4),
            fill=tuple(int(v) for v in c),
        )
    if blur > 0.3:
        A = A.filter(ImageFilter.GaussianBlur(blur))
        Gm = Gm.filter(ImageFilter.GaussianBlur(blur))
    a_ = np.asarray(A, np.float32)[..., None] / 255
    hm = (
        np.clip(soft(A, 26) * 2.6, 0, 1)[..., None] * 0.76
    )  # soft dark halo (legibility on the lit wall)
    gl = np.clip(soft(Gm, 14) * 1.4, 0, 1)[..., None]
    Pc = P[y0 - PY0 : y1 - PY0, x0:x1]
    Pc *= 1 - hm
    Pc += HALO * hm
    Pc += AMBER * gl * 0.5
    Pc *= 1 - a_
    Pc += np.asarray(RGB, np.float32) * a_


# ---- exterior layers ----
@lru_cache(1)
def base_exterior() -> np.ndarray:
    P = np.empty((PH, W, 3), np.float32)
    k = (np.arange(HZL, dtype=np.float32) / (HZL - 1))[:, None]
    P[:HZL] = (SKY_TOP * (1 - k) + SKY_HOR * k)[:, None, :]
    k2 = (np.arange(SEA_H, dtype=np.float32) / (SEA_H - 1))[:, None]
    haze = np.exp(-k2 * 9)
    P[HZL:] = (col("#1b2943") * haze + SEA * (1 - haze))[:, None, :]
    rng = np.random.default_rng(11)
    xs = np.arange(W, dtype=np.float32)[None, :]
    ys = np.arange(HZL, dtype=np.float32)[:, None]
    for _ in range(6):  # soft cloud bands
        cy, cx = rng.uniform(30, HZL - 70), rng.uniform(0, W)
        sx, sy = rng.uniform(320, 760), rng.uniform(9, 24)
        g = (
            np.exp(-(((xs - cx) / sx) ** 2) - ((ys - cy) / sy) ** 2)
            * rng.uniform(0.12, 0.24)
        )[..., None]
        P[:HZL] = P[:HZL] * (1 - g) + col("#152036") * g
    return P


@lru_cache(1)
def stars_data():
    rng = np.random.default_rng(3)
    n = 70
    return (
        (rng.random(n) * W).astype(int),
        (rng.random(n) ** 1.6 * 220 + 6).astype(int),
        10 + 30 * rng.random(n),
        rng.random(n) * 6.283,
        0.6 + 1.8 * rng.random(n),
    )


def stars(P: np.ndarray, t: float, k: float) -> None:
    if k <= 0.01:
        return
    xs, ys, b, ph, f = stars_data()
    tw = b * (0.7 + 0.3 * np.sin(ph + f * t)) * k
    for x, y, v in zip(xs, ys, tw):
        P[y : y + 2, x : x + 2] += np.array([v * 0.85, v * 0.9, v], np.float32)


@lru_cache(1)
def ripple_tex() -> np.ndarray:
    rng = np.random.default_rng(17)
    im = Image.new("L", (W, SEA_H), 0)
    d = ImageDraw.Draw(im)
    for _ in range(3000):
        yl = SEA_H * rng.random() ** 1.3
        dep = (yl + 6) / SEA_H
        ln = 5 + 160 * dep * (0.25 + rng.random())
        x = rng.random() * W
        fill, wd = int(70 + 150 * rng.random()), max(1, int(round(0.6 + 2.2 * dep)))
        for xo in (
            x,
            x - W,
        ):  # draw the wrapped copy too, so the rolled texture tiles without a seam
            d.line([(xo, yl), (xo + ln, yl)], fill=fill, width=wd)
    return np.asarray(im.filter(ImageFilter.GaussianBlur(0.9)), np.float32) / 255


@lru_cache(1)
def swell_rows():
    yl = np.arange(SEA_H, dtype=np.float32)
    return 34.0 / (yl + 24.0), smooth_arr(yl, 30.0, 140.0)


def smooth_arr(x, e0, e1):
    k = np.clip((x - e0) / (e1 - e0), 0, 1)
    return k * k * (3 - 2 * k)


BANDS = ((0, 110, 6.0), (110, 260, 13.0), (260, SEA_H, 24.0))


def ripples(P: np.ndarray, t: float, sw: float) -> None:
    tex = ripple_tex()
    S = P[HZL:]
    for y0, y1, v in BANDS:
        band = np.roll(tex[y0:y1], int(round(t * v)), axis=1)
        bob = int(round(sw * (y1 - y0) * 0.012 * math.sin(2 * math.pi * t / 6.5 + y0)))
        if bob:
            band = np.roll(band, bob, axis=0)
        a = (band * (0.30 + 0.14 * (sw - 1)))[..., None]
        S[y0:y1] += (RIPPLE - S[y0:y1]) * a
    z, fade = swell_rows()  # long swell crests rolling toward camera
    crest = (
        np.maximum(0, np.sin(2 * np.pi * (z - 0.13 * t))) ** 6 * fade * 0.05 * sw**1.5
    )
    xm = 0.65 + 0.35 * np.sin(np.arange(W, dtype=np.float32) / 210.0 + 0.4 * t)
    S += RIPPLE * (crest[:, None] * xm[None, :])[..., None]


@lru_cache(1)
def glitter_tex():
    rng = np.random.default_rng(31)
    out = []
    for _ in range(2):
        im = Image.new("L", (W, SEA_H), 0)
        d = ImageDraw.Draw(im)
        for _ in range(5200):
            yl = SEA_H * rng.random() ** 1.6
            dep = (yl + 8) / SEA_H
            ln = 3 + 46 * dep * rng.random()
            x = rng.random() * W
            fill, wd = int(110 + 145 * rng.random()), 1 if dep < 0.5 else 2
            for xo in (x, x - W):  # wrapped copy: the texture is indexed modulo W
                d.line([(xo, yl), (xo + ln, yl)], fill=fill, width=wd)
        out.append(
            np.asarray(im.filter(ImageFilter.GaussianBlur(0.5)), np.float32) / 255
        )
    return out


def column(
    P: np.ndarray,
    X: float,
    strength: float,
    t: float,
    sig0: float = 16.0,
    sig1: float = 0.24,
) -> None:
    """Glitter path on the sea under a light at screen x = X (the beam's far end, or the lamp)."""
    if strength < 0.01 or X < -300 or X > W + 300:
        return
    yl = np.arange(SEA_H, dtype=np.float32)[:, None]
    sig = sig0 + sig1 * yl
    smax = float(sig[-1, 0])
    x0, x1 = int(max(0, X - 3 * smax)), int(min(W, X + 3 * smax))
    if x1 <= x0:
        return
    xs = np.arange(x0, x1)
    m = np.exp(-(((xs[None, :].astype(np.float32) - X) / sig) ** 2)) * smooth_arr(
        yl, 0.0, 40.0
    )
    t0, t1 = glitter_tex()
    w0 = 0.5 + 0.5 * math.sin(2 * math.pi * 1.3 * t)
    g = t0[:, (xs + int(t * 40)) % W] * w0 + t1[:, (xs - int(t * 25)) % W] * (1 - w0)
    P[HZL:, x0:x1] += AMBER * (m * (0.10 + 0.95 * g) * strength)[..., None]


@lru_cache(1)
def beam_grid():
    ys = (np.arange(PH // 4) * 4 + 2 + PY0).astype(np.float32)
    xs = (np.arange(W // 4) * 4 + 2).astype(np.float32)
    X, Y = np.meshgrid(xs, ys)
    return X - LAMP[0], Y - LAMP[1]


def wide_glow(P: np.ndarray, amt: float) -> None:
    """Soft wide glow round the lamp (directed-by bar): low-res radial field, local, slow 2 s ramp."""
    if amt < 0.005:
        return
    dx, dy = beam_grid()
    g = np.exp(-(dx * dx + dy * dy) / (2 * 210.0**2)) * (0.36 * amt)
    g = np.asarray(
        Image.fromarray(g.astype(np.float32), "F").resize((W, PH), Image.BILINEAR)
    )
    P += AMBER * (g * 0.62)[..., None]


def beam(P: np.ndarray, a: float, strength: float, spread: float) -> None:
    if strength < 0.01:
        return
    dx, dy = beam_grid()
    tx, ty = tip(a)
    vx, vy = float(tx) - LAMP[0], float(ty) - LAMP[1]
    L = math.hypot(vx, vy)
    ux, uy = vx / L, vy / L
    s = dx * ux + dy * uy
    q = np.abs(dx * uy - dy * ux)
    sp = np.maximum(s, 0)
    w = (5 + 0.045 * sp) * spread
    core = np.exp(-((q / w) ** 2))
    haze = np.exp(-((q / (3.2 * w + 16)) ** 2)) * 0.28 * spread**0.5
    along = np.clip(s / 30, 0, 1) * np.exp(-sp / (0.75 * L + 380))
    end = 1 / (1 + np.exp(np.clip((s - 1.08 * L) / (0.10 * L + 30), -30, 30)))
    I = (core + haze) * along * end
    if L < 3000:
        I = (
            I
            + np.exp(-((dx - vx) ** 2 + (dy - vy) ** 2) / (2 * (46 * spread) ** 2))
            * 0.45
        )
    I = np.asarray(
        Image.fromarray((I * strength).astype(np.float32), "F").resize(
            (W, PH), Image.BILINEAR
        )
    )
    P += AMBER * (I * 0.62)[..., None]


@lru_cache(1)
def silhouette():
    x0, y0, x1, y1 = 1230, 228, 1830, 860
    S = 2
    im = Image.new("L", ((x1 - x0) * S, (y1 - y0) * S), 0)
    d = ImageDraw.Draw(im)

    def p(x, y):
        return ((x - x0) * S, (y - y0) * S)

    rng = np.random.default_rng(5)
    top = [
        (1262, 752),
        (1300, 728),
        (1336, 700),
        (1384, 678),
        (1432, 664),
        (1470, 660),
        (1540, 660),
        (1586, 667),
        (1634, 682),
        (1688, 704),
        (1738, 728),
        (1782, 750),
        (1806, 768),
    ]
    rock = [(x + rng.uniform(-4, 4), y + rng.uniform(-3, 3)) for x, y in top] + [
        (1810, 776),
        (1256, 776),
    ]
    d.polygon([p(*q) for q in rock], fill=255)
    d.polygon(
        [p(1452, 664), p(1548, 664), p(1531, 346), p(1469, 346)], fill=255
    )  # tower
    d.rectangle([p(1450, 334), p(1550, 347)], fill=255)  # gallery deck
    d.rectangle([p(1452, 318), p(1548, 321)], fill=255)  # rail
    for x in range(1456, 1548, 9):
        d.rectangle([p(x, 318), p(x + 1.5, 334)], fill=255)
    d.rectangle([p(1470, 282), p(1530, 287)], fill=255)  # lantern ring
    d.rectangle([p(1470, 329), p(1530, 334)], fill=255)  # lantern sill
    d.rectangle([p(1470, 282), p(1475, 334)], fill=255)  # mullions
    d.rectangle([p(1525, 282), p(1530, 334)], fill=255)
    d.polygon(
        [p(1464, 288), p(1536, 288), p(1522, 268), p(1500, 257), p(1478, 268)], fill=255
    )  # roof
    d.ellipse([p(1495, 247), p(1505, 257)], fill=255)
    d.rectangle([p(1499, 234), p(1501, 249)], fill=255)
    alpha = np.asarray(im.resize((x1 - x0, y1 - y0), Image.LANCZOS), np.float32) / 255
    yy = np.arange(y0, y1, dtype=np.float32)[:, None]
    xx = np.arange(x0, x1, dtype=np.float32)[None, :]
    refl = (
        0.42
        * np.clip(1 - (yy - 776) / 70, 0, 1)
        * (yy >= 776)
        * np.exp(-(((xx - 1532) / 250) ** 6))
    )
    alpha = np.maximum(alpha, refl)
    wim = Image.new("L", (x1 - x0, y1 - y0), 0)
    dw = ImageDraw.Draw(wim)
    for a, b, c, e in (
        (1495, 420, 1505, 440),
        (1496, 520, 1504, 538),
        (1497, 610, 1503, 626),
    ):
        dw.rectangle((a - x0, b - y0, c - x0, e - y0), fill=255)
    win = np.asarray(wim.filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255
    return alpha[..., None], win[..., None], x0, y0 - PY0


def draw_silhouette(P: np.ndarray) -> None:
    a, win, x0, y0 = silhouette()
    h, w = a.shape[:2]
    Pc = P[y0 : y0 + h, x0 : x0 + w]
    Pc *= 1 - a
    Pc += SIL * a
    Pc += AMBER * win * 0.45


def paste_add(P: np.ndarray, add: np.ndarray, cx: float, cy: float) -> None:
    h, w = add.shape[:2]
    x0, y0 = int(round(cx)) - w // 2, int(round(cy)) - PY0 - h // 2
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(W, x0 + w), min(PH, y0 + h)
    if xb > xa and yb > ya:
        P[ya:yb, xa:xb] += add[ya - y0 : yb - y0, xa - x0 : xb - x0]


@lru_cache(1)
def lamp_grid():
    r = np.arange(
        -320, 320, dtype=np.float32
    )  # half >= 3.6 sigma of the widest glow: no square edge
    X, Y = np.meshgrid(r, r)
    d2 = X * X + Y * Y
    return [np.exp(-d2 / (2 * s * s))[..., None] for s in (6.0, 22.0, 80.0, 88.0)]


def lamp(P: np.ndarray, base: float, extra: float) -> None:
    c, g1, g2, g3 = lamp_grid()
    add = WARM * (c * 1.5 * base) + AMBER * (
        g1 * 0.85 * base + g2 * 0.24 * (base + extra) + g3 * 0.26 * extra
    )
    paste_add(P, add, *LAMP)


@lru_cache(1)
def boat_grid():
    r = np.arange(-40, 40, dtype=np.float32)
    X, Y = np.meshgrid(r, r)
    d2 = X * X + Y * Y
    return np.exp(-d2 / (2 * 2.2**2))[..., None], np.exp(-d2 / (2 * 10.0**2))[..., None]


def boat(P: np.ndarray, t: float) -> None:
    if t < 56.0:
        return
    k = smooth(56.0, 56.8, t)
    blink = math.exp(-(((t - 58.1) / 0.22) ** 2)) + math.exp(
        -(((t - 58.9) / 0.22) ** 2)
    )
    b = k * (0.45 + 0.15 * smooth(59.0, 59.5, t)) + 0.9 * blink
    by, bx = int(BOAT[1]) - PY0, int(BOAT[0])
    hull = P[by + 2 : by + 6, bx - 13 : bx + 14]
    hull *= 1 - 0.7 * k
    hull += SIL * 0.7 * k
    c, g = boat_grid()
    paste_add(P, WARM * c * 1.6 * b + AMBER * g * 0.35 * b, *BOAT)


@lru_cache(1)
def rain_seeds():
    rng = np.random.default_rng(41)
    n = 260
    return (
        rng.random(n) * 2300 - 200,
        rng.random(n) * PH,
        1250 + 500 * rng.random(n),
        22 + 40 * rng.random(n),
        0.35 + 0.65 * rng.random(n),
    )


def rain(P: np.ndarray, t: float, amt: float) -> None:
    if amt <= 0.01:
        return
    x0, y0, v, ln, b = rain_seeds()
    n = int(len(x0) * amt)
    im = Image.new("L", (W, PH), 0)
    d = ImageDraw.Draw(im)
    for i in range(n):
        y = (y0[i] + v[i] * t) % (PH + 80) - 40
        x = (x0[i] - 0.22 * v[i] * t) % 2300 - 200
        d.line([(x, y), (x - 0.22 * ln[i], y + ln[i])], fill=int(255 * b[i]), width=1)
    m = (np.asarray(im, np.float32) / 255 * 0.32 * amt)[..., None]
    P += (RAIN - P) * m


# ---- the Fresnel lens (title) and the small lens above the clockwork ----
@lru_cache(None)
def lens_grid(half: int):
    r = np.arange(-half, half, dtype=np.float32)
    X, Y = np.meshgrid(r, r)
    R = np.hypot(X, Y)
    PHI = np.arctan2(Y, X)
    return R, np.cos(PHI), np.sin(PHI)


def ring_profile(q):
    return (
        0.14
        + 0.45 * q**2.2
        + 0.8 * np.exp(-(((q - 0.93) / 0.035) ** 2))
        - 0.1 * np.exp(-((q / 0.04) ** 2))
    )


def lens_value(half, r0, dr, n, scales, alphas):
    R = lens_grid(half)[0]
    s0, a0 = scales[0], alphas[0]
    r = R / s0
    V = (
        np.exp(-((r / 30) ** 2)) * 1.2
        + 0.4 * np.clip(r0 - r, 0, 1) * (0.35 + 0.65 * (r / r0) ** 2)
    ) * a0
    for i in range(1, n + 1):
        sc, al = scales[i], alphas[i]
        if al <= 0:
            continue
        r = R / sc
        q = (r - (r0 + (i - 1) * dr)) / dr
        edge = np.clip(q * dr * sc, 0, 1) * np.clip((1 - q) * dr * sc, 0, 1)
        V += ring_profile(np.clip(q, 0, 1)) * edge * al
    return V


LENS_R0, LENS_DR, LENS_N, LENS_HALF = (
    70.0,
    33.0,
    8,
    452,
)  # half > 1.3 x outer radius 334


HIT_LEAD = (
    1 / 48
)  # visual hits start half a frame before their beat (gate 9: picture changes on the hit frame)


def ring_state(t: float, i: int, t0: float = 32.0 - HIT_LEAD):
    k = prog(t, t0 + 0.11 * i, 0.85)
    return 1 + 0.3 * (1 - ease_out_expo(k)), ease_out_cubic(
        prog(t, t0 + 0.11 * i, 0.45)
    )


@lru_cache(1)
def lens_static():
    return lens_value(
        LENS_HALF, LENS_R0, LENS_DR, LENS_N, [1.0] * (LENS_N + 1), [1.0] * (LENS_N + 1)
    )


def fresnel(P: np.ndarray, t: float) -> None:
    amt = smooth(31.9, 32.0, t) * (1 - smooth(39.3, 40.0, t))
    if amt <= 0.001:
        return
    if t >= 33.8:
        V = lens_static()
    else:
        st = [ring_state(t, i) for i in range(LENS_N + 1)]
        V = lens_value(
            LENS_HALF, LENS_R0, LENS_DR, LENS_N, [s for s, _ in st], [a for _, a in st]
        )
    _, Cp, Sp = lens_grid(LENS_HALF)
    th = 0.45 * (t - 32.0) - 2.2
    hl = 0.62 + 0.38 * (Cp * math.cos(th) + Sp * math.sin(th))
    core = 1.0 - 0.3 * smooth(32.6, 34.0, t)
    Vh = (V * hl)[..., None]
    add = (AMBER * Vh * 0.5 + WARM * (Vh**3) * 0.18) * amt * core
    paste_add(P, add, *LENS_C)


@lru_cache(1)
def small_lens():
    # R701: rings scaled 0.6 (outer radius 27.6 + 4 x 15.6 = 90 px) so the whole lamp sits inside the picture
    V = lens_value(100, 46.0 * 0.6, 26.0 * 0.6, 4, [1.0] * 5, [1.0] * 5)
    _, Cp, Sp = lens_grid(100)
    hl = 0.6 + 0.4 * (Cp * math.cos(1.2) + Sp * math.sin(1.2))
    Vh = (V * hl)[..., None]
    return AMBER * Vh * 0.5 + WARM * (Vh**3) * 0.2


# ---- interior (crew): the lamp's clockwork ----
SMALL_LENS_C, SMALL_LENS_R = (430.0, 245.0), 90.0
GEAR_C = (430.0, 540.0)
PIN_C = (
    GEAR_C[0] + 217.6 * math.cos(math.radians(-40)),
    GEAR_C[1] + 217.6 * math.sin(math.radians(-40)),
)
DRUM_R = 40.0
CLOCK_BOX = (190, 300, 790, 942)  # absolute crop for the clockwork layer


@lru_cache(1)
def base_interior() -> np.ndarray:
    k = np.linspace(0, 1, PH, dtype=np.float32)[:, None]
    P = np.empty((PH, W, 3), np.float32)
    P[:] = (col("#1c283f") * (1 - k) + col("#0e1625") * k)[:, None, :]
    for row, y in enumerate(range(30, PH, 62)):
        P[y : y + 2] *= 0.86
        P[y + 2 : y + 3] *= 1.05
        for x in range(0 if row % 2 else 95, W, 190):
            P[y : y + 62, x : x + 2] *= 0.9
    X = np.arange(W, dtype=np.float32)[None, :]
    Y = np.arange(PH, dtype=np.float32)[:, None]
    g = np.exp(-(((X - 430) / 520) ** 2 + ((Y + 40) / 430) ** 2))
    P += AMBER * (g * 0.2)[..., None]
    v = np.clip(1 - 0.38 * (((X - 960) / 1150) ** 2 + ((Y - 402) / 700) ** 2), 0.5, 1)
    P *= v[..., None]
    return P


def gear_angle(t: float) -> float:
    """Escapement: one tooth (12 deg) per beat, a quick step with a small overshoot on each beat."""
    tau = max(
        0.0, t - 40.0 + HIT_LEAD
    )  # half a frame early, so the frame on the beat already shows the step
    n = math.floor(tau)
    return 12.0 * (n + ease_out_back(min(1.0, (tau - n) / 0.16), 1.3))


def gear_poly(cx, cy, n, rr, rt, theta, S, ox, oy):
    pts = []
    step = 360.0 / n
    for k in range(n):
        c = theta + k * step
        for da, r in ((-0.5, rr), (-0.34, rr), (-0.18, rt), (0.18, rt), (0.34, rr)):
            a = math.radians(c + da * step)
            pts.append(
                ((cx + r * math.cos(a) - ox) * S, (cy + r * math.sin(a) - oy) * S)
            )
    return pts


def clockwork(P: np.ndarray, t: float) -> None:
    x0, y0, x1, y1 = CLOCK_BOX
    S = 2
    im = Image.new("RGBA", ((x1 - x0) * S, (y1 - y0) * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def p(x, y):
        return ((x - x0) * S, (y - y0) * S)

    def circ(cx, cy, r, **kw):
        d.ellipse([p(cx - r, cy - r), p(cx + r, cy + r)], **kw)

    th = gear_angle(t)
    beta = -40.0
    thp = beta + 198.0 - 3.0 * (th - beta)
    d.polygon(
        gear_poly(*PIN_C, 10, 46, 62, thp, S, x0, y0),
        fill=BRASS,
        outline=BRASS_L,
        width=3,
    )
    circ(*PIN_C, 16, fill=BRASS_D, outline=BRASS_L, width=3)
    gx, gy = GEAR_C
    d.polygon(
        gear_poly(gx, gy, 30, 154, 172, th, S, x0, y0),
        fill=BRASS,
        outline=BRASS_L,
        width=3,
    )
    circ(gx, gy, 124, fill=(0, 0, 0, 0))
    circ(gx, gy, 124, outline=BRASS_L, width=3)
    for k in range(6):
        a = math.radians(th + 15 + k * 60)
        ca, sa = math.cos(a), math.sin(a)
        w = 11
        quad = [
            (gx + 26 * ca - w * sa, gy + 26 * sa + w * ca),
            (gx + 126 * ca - w * sa, gy + 126 * sa + w * ca),
            (gx + 126 * ca + w * sa, gy + 126 * sa - w * ca),
            (gx + 26 * ca + w * sa, gy + 26 * sa - w * ca),
        ]
        d.polygon([p(*q) for q in quad], fill=BRASS, outline=BRASS_L, width=2)
    circ(gx, gy, DRUM_R, fill=BRASS_D, outline=BRASS_L, width=3)
    circ(gx, gy, DRUM_R - 8, outline=(150, 105, 55), width=2)
    circ(gx, gy, 9, fill=BRASS_L)
    cxh = gx + DRUM_R
    yw = 740.0 + DRUM_R * math.radians(th)
    phase = (DRUM_R * math.radians(th)) % 32.0
    y = gy - 32 + phase
    j = 0
    while y < yw:
        if y > gy - 2:
            if j % 2 == 0:
                d.ellipse(
                    [p(cxh - 5, y - 9), p(cxh + 5, y + 9)],
                    outline=(196, 146, 84),
                    width=3,
                )
            else:
                d.rectangle(
                    [p(cxh - 1.2, y - 9), p(cxh + 1.2, y + 9)], fill=(196, 146, 84)
                )
        y += 16
        j += 1
    circ(cxh, yw + 4, 6, outline=(196, 146, 84), width=3)
    d.rounded_rectangle(
        [p(cxh - 24, yw + 10), p(cxh + 24, yw + 86)],
        6 * S,
        fill=BRASS,
        outline=BRASS_L,
        width=3,
    )
    for yy in (yw + 24, yw + 72):
        d.line([p(cxh - 22, yy), p(cxh + 22, yy)], fill=BRASS_D, width=3)
    lay = np.asarray(im.resize((x1 - x0, y1 - y0), Image.LANCZOS), np.float32)
    a = lay[..., 3:4] / 255
    Pc = P[y0 - PY0 : y1 - PY0, x0:x1]
    Pc *= 1 - a
    Pc += lay[..., :3] * a


def band_x(t: float) -> float | None:
    j = min(5, max(0, math.floor((t - 40.0 + BAND_LEAD) / 2.0)))
    ts = 40.0 + 2 * j
    xb = BAND_X0 - (t - (ts - BAND_LEAD)) * BAND_V
    return xb if -300 < xb < W + 300 else None


def interior(t: float) -> np.ndarray:
    P = base_interior().copy()
    j = min(5, max(0, math.floor((t - 40.0 + BAND_LEAD) / 2.0)))
    pulse = math.exp(-(((t - (40.0 + 2 * j - BAND_LEAD)) / 0.25) ** 2))
    # centre (430, 245): disc spans y 155-335, clear of the bar (138), pinion top (338) and gear top (368)
    paste_add(P, small_lens() * (0.85 + 0.35 * pulse), *SMALL_LENS_C)
    clockwork(P, t)
    xb = band_x(t)
    if xb is not None:
        xs = np.arange(W, dtype=np.float32)
        prof = np.exp(-(((xs - xb) / 90.0) ** 2))
        vert = 1.0 - 0.4 * np.linspace(0, 1, PH, dtype=np.float32)
        P += AMBER * (vert[:, None] * prof[None, :] * 0.14)[..., None]
    for cid in INTERIOR_CREDITS:
        render_credit(P, cid, t)
    return P


def exterior(t: float) -> np.ndarray:
    P = base_exterior().copy()
    wet = rain_amt(t)
    if wet > 0:
        P[:HZL] *= 1 - 0.14 * wet
    stars(P, t, 1 - wet)
    sw = swell(t)
    ripples(P, t, sw)
    a = azimuth(t)
    bs, spread = beam_params(t)
    strength = bs * far_env(a)
    column(P, float(tip(a)[0]), 0.85 * strength, t)
    column(P, LAMP[0], 0.30, t, sig0=6.0, sig1=0.10)
    beam(P, a, strength, spread)
    wide_glow(P, ramp52(t) if t >= 52.0 else 0.0)
    draw_silhouette(P)
    lamp(P, 1.0, lamp_extra(t, a))
    boat(P, t)
    rain(P, t, wet)
    dim = title_dim(t)
    if dim > 0:
        P *= 1 - 0.32 * dim
    fresnel(P, t)
    for cid in EXTERIOR_CREDITS:
        render_credit(P, cid, t)
    return P


def shift(P: np.ndarray, dx: int, dy: int) -> np.ndarray:
    if dy > 0:
        P = np.concatenate([np.repeat(P[:1], dy, 0), P[:-dy]], 0)
    elif dy < 0:
        P = np.concatenate([P[-dy:], np.repeat(P[-1:], -dy, 0)], 0)
    if dx > 0:
        P = np.concatenate([np.repeat(P[:, :1], dx, 1), P[:, :-dx]], 1)
    elif dx < 0:
        P = np.concatenate([P[:, -dx:], np.repeat(P[:, -1:], -dx, 1)], 1)
    return P


# grain amplitude (grey levels), tile scale, bilinear. 2.6 gave a 140 MB master; 1.6 with CRF 20 measured
# about 37 MB on a 4 s slice (grain_test.py), still visible as soft grain.
GRAIN_STD, GRAIN_CELL, GRAIN_SMOOTH = 1.6, 2, False


def film(P: np.ndarray, t: float) -> np.ndarray:
    """Soft seeded grain (new every frame), about 1 percent exposure flicker, whole-pixel gate weave."""
    i = int(round(t * FPS))
    tau = 2 * math.pi * t
    P *= 1 + 0.008 * math.sin(1.7 * tau + 0.4) + 0.005 * math.sin(4.3 * tau + 1.1)
    c = GRAIN_CELL
    g = np.random.default_rng(9000 + i).standard_normal(
        (-(-PH // c), -(-W // c)), dtype=np.float32
    )
    if (
        GRAIN_SMOOTH
    ):  # bilinear-scaled tile: softer grain, far fewer bits for the encoder
        g = np.asarray(Image.fromarray(g, "F").resize((W, PH), Image.BILINEAR))
    else:
        g = np.repeat(np.repeat(g, c, 0), c, 1)[:PH, :W]
    P += (g * GRAIN_STD)[..., None]
    dx = int(round(0.9 * math.sin(0.31 * tau + 0.7) + 0.4 * math.sin(0.83 * tau)))
    dy = int(round(0.8 * math.sin(0.27 * tau + 2.1) + 0.3 * math.sin(0.71 * tau + 0.3)))
    return shift(P, dx, dy) if (dx or dy) else P


def picture(t: float) -> np.ndarray:
    if 40.0 <= t < 52.0:
        return interior(t)
    if 52.0 <= t < 52.5:
        k = ease_in_out_cubic(prog(t, 52.0, 0.5))
        return interior(t) * (1 - k) + exterior(t) * k
    return exterior(t)


def draw(t: float) -> Image.Image:
    t = float(t)
    P = film(picture(t), t)
    out = np.zeros((H, W, 3), np.uint8)  # black letterbox bars top and bottom
    out[PY0 : PY0 + PH] = np.clip(P, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGB")
