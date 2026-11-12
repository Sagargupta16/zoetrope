# scenes.py : Nook launch film (S-g04-best-launch), 1920x1080, 30 fps, 60.0 s, 96 BPM lo-fi in F major.
# draw(t) is pure: same t -> same pixels. Random is seeded; the caches only hold pure sprites.
# Scene timing lives in SCHEDULE, in-scene events in CUE and CAPS. All three come from one beat grid
# T(bar, beat), and build_audio.py reads the same numbers, so picture and music cannot drift.
from __future__ import annotations

import math
import random
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
    hexrgb,
    lerp,
    prog,
    scene_at,
)

W, H, FPS, SS = (
    E.W,
    E.H,
    E.FPS,
    E.SS,
)  # the runner sets these on engine before importing scenes


def back(k):
    """ease_out_back that is exactly 0 before the move starts (the float result at k = 0 is not)."""
    return 0.0 if k <= 0 else ease_out_back(k)


# ---------- palette (scenario 1 and card S-g04) ----------
CORAL, PLUM, CREAM, MINT, LILAC = "#ff6b4a", "#2b1b3f", "#fff6ec", "#6fd6b5", "#cfc4f2"
CORAL_TXT, MINT_TXT = (
    "#c9452a",
    "#23966f",
)  # small-text tints; the bright ones fail on cream
WHITE, MUTED, TRACK = "#ffffff", "#5a4a6e", "#ece5f6"
PLUM_TOP, PLUM_BOT = "#33214b", "#22152f"
CREAM_TOP, CREAM_BOT = "#fff8f0", "#fbece0"

# ---------- one grid ----------
BPM = 96
B = 60 / BPM  # 0.625 s
BAR = 4 * B  # 2.5 s


def T(bar: float, beat: float = 1.0) -> float:
    """Seconds at a 1-based bar and 1-based beat of the 96 BPM grid."""
    return (bar - 1) * BAR + (beat - 1) * B


SCHEDULE = {  # every scene starts on a bar line
    "noise": (T(1), T(4)),
    "reveal": (T(4), T(6)),
    "timer": (T(6), T(9)),
    "tasks": (T(9), T(12)),
    "quiet": (T(12), T(15)),
    "streak": (T(15), T(18)),
    "word": (T(18), T(21)),
    "payoff": (T(21), T(24)),
    "end": (T(24), T(25)),
}
DURATION = T(25)  # 60.0

FP = (
    960,
    450,
)  # focus point: task card, coral point, tile, timer ring, dictionary card
CAP_Y, CAP_SIZE, CAP_IN, CAP_OUT = 915, 64, 0.3, 0.25

# captions: (text, t_in, t_out, tone); tone "light" = cream text on plum, "dark" = plum text on cream
CAPS = [
    ("You sat down to do one thing.", 0.0, 3.4, "light"),
    ("Then everything else showed up.", 3.6, 6.8, "light"),
    ("One thing at a time.", 11.2, 13.8, "dark"),  # rides over the zoom into the timer
    ("Focus for 25.", 13.8, 16.8, "dark"),
    ("Breathe for 5.", T(7, 4), 19.85, "dark"),
    ("Your list, in order.", T(9, 1.5), 24.1, "dark"),
    ("Unfinished? It waits for tomorrow.", T(10, 4), 27.25, "dark"),
    ("Quiet mode.", T(12, 3.5), 31.5, "light"),
    ("Let the world wait.", T(13, 3.5), 34.25, "light"),
    ("Show up. Keep the streak.", T(15, 2.5), 42.25, "dark"),
    ("On your desk. In your pocket.", T(19, 3.5), 49.85, "dark"),
    ("One thing. Done.", T(21, 2.5), 53.1, "dark"),
]


def _card_times() -> list[float]:
    """22 notification pops from 1.6 s, faster and faster, snapped to frames (pings use the same times)."""
    return [round((1.6 + 4.9 * (i / 21) ** 0.6) * FPS) / FPS for i in range(22)]


DICT_TEXT = "nook (n.): a small, quiet place to do one thing."
TYPE_T0, TYPE_CPS = 42.9, 25.0

CUE = {
    "card_t": _card_times(),
    "collapse": (6.85, 0.15),
    "suck_end": 7.0,
    "tile": (T(4), 0.6),
    "wipe_in": (T(4), 1.0),  # 1.0 s (was 0.8) for flash margin in second 7
    "square": (T(4) + 0.6, 0.3),
    "hops": [T(4, 3), T(4, 4), T(5)],  # 8.75, 9.375, 10.0 (wood toks)
    "drop": T(5),  # groove drops
    "slide": (10.1, 0.5),
    "word": (10.6, 0.35),
    "zoom": (12.0, 0.5),
    "bg_in": (
        T(6),
        0.6,
    ),  # timer background: flat cream at the cut, gradient and blobs back by 13.1
    "ring_on": (T(6), 0.6),
    "chips_in": 12.9,
    "count": (T(6, 3), T(7, 4)),  # 25:00 -> 00:00, 13.75 -> 16.875
    "taps": [T(8, 2), T(8, 3)],  # chip 25, chip 30
    "timer_out": (19.75, 0.25),
    "panel_in": (T(9), 0.5),
    "drag": (T(9, 3), T(10)),  # 21.25 -> 22.5
    "checks": [T(10), T(10, 2)],  # claps
    "roll": (24.0, T(10, 4)),  # clock 11:59 PM -> 12:00 AM, lands on the bell
    "bell": [T(10, 4), T(10, 4.5)],  # two-note midnight bell
    "leave": (T(11), 0.4),
    "slide_up": (25.3, 0.45),
    "tags": 25.55,
    "tasks_out": (27.25, 0.25),
    "toggle_in": (T(12), 0.4),
    "toggle_on": T(12, 2),
    "wipe_dark": (28.3, 0.8),
    "session_ticks": [29.6 + 0.8 * k for k in range(7)],  # 18:42 -> 18:35
    "qnotif": [T(12, 4), T(13), T(13, 2), T(13, 3.5), T(14), T(14, 2)],
    "wipe_light": (34.4, 0.6),
    "lp": ((T(12, 2), 0.75), (34.4, 0.6)),  # quiet-mode filter down, then up
    "quiet_out": (34.75, 0.25),
    "fills": [T(15, 2) + k * B for k in range(7)],
    "rest": 3,  # Thursday stays dim
    "wave": T(17),
    "streak_out": (42.2, 0.3),
    "dict_in": (T(18), 0.35),
    "type_t": [TYPE_T0 + i / TYPE_CPS for i in range(len(DICT_TEXT))],
    "dict_move": (T(19, 2), 0.5),
    "desk_in": (T(19, 2.5), 0.6),  # rises while the dictionary card moves up
    "phone_in": (T(19, 3), 0.6),
    "riser": (T(20), BAR),
    "word_out": (49.75, 0.25),
    "task2_in": (T(21), 0.35),
    "check2": T(21, 2),
    "task2_out": (52.85, 0.25),
    "lk_tile": T(22, 2),
    "lk_square": T(22, 2.25),
    "lk_dot": (T(22, 2.5), T(22, 3)),
    "lk_word": (T(22, 3), 0.35),
    "lk_tag": (T(22, 3.5), 0.3),
    "pills": [T(22, 4) + i * B / 4 for i in range(4)],
    "chord": T(23),
    "disclaimer": (T(23, 4), 0.3),
    "push": (T(24), BAR),
    "fade": (59.4, 0.6),
}

PILLS = ["Focus timer", "Carry-over list", "Quiet mode", "Streaks"]
DISCLAIMER = "Sample film. Nook is a fictional app."
TAGLINE = "One thing at a time."

# ---------- primitives (coordinates in output px; the canvas is W*SS x H*SS) ----------
TEXT_LOG: list[
    dict
] = []  # text drawn by the current draw(t) call, read by the QA gates


def rgba(c, a: float = 1.0) -> tuple[int, int, int, int]:
    r, g, b, al = hexrgb(c) if isinstance(c, str) else (tuple(c) + (255,))[:4]
    return (r, g, b, max(0, min(255, int(round(al * a)))))


def mix(c1: str, c2: str, k: float) -> tuple[int, int, int, int]:
    a, b = hexrgb(c1), hexrgb(c2)
    k = clamp(k)
    return tuple(int(round(lerp(a[i], b[i], k))) for i in range(3)) + (255,)


def comp(img: Image.Image, lay: Image.Image, X: int, Y: int) -> None:
    """alpha_composite lay at canvas px (X, Y), clipped to the canvas."""
    sx, sy = max(0, -X), max(0, -Y)
    dx, dy = max(0, X), max(0, Y)
    w = min(lay.width - sx, img.width - dx)
    h = min(lay.height - sy, img.height - dy)
    if w <= 0 or h <= 0:
        return
    if sx or sy or w != lay.width or h != lay.height:
        lay = lay.crop((sx, sy, sx + w, sy + h))
    img.alpha_composite(lay, dest=(dx, dy))


def _win(img, x0, y0, x1, y1, pad=2):
    X0 = max(0, int(math.floor(x0 * SS)) - pad)
    Y0 = max(0, int(math.floor(y0 * SS)) - pad)
    X1 = min(img.width, int(math.ceil(x1 * SS)) + pad)
    Y1 = min(img.height, int(math.ceil(y1 * SS)) + pad)
    if X1 <= X0 or Y1 <= Y0:
        return None
    return X0, Y0, X1, Y1


def shape(
    img,
    kind,
    box,
    fill=None,
    a=1.0,
    r=0.0,
    outline=None,
    width=0.0,
    start=0.0,
    end=360.0,
):
    """rrect, ellipse, pie or arc on a small local layer, composited with opacity a."""
    if a <= 0.003:
        return
    x0, y0, x1, y1 = box
    if x1 - x0 < 0.05 or y1 - y0 < 0.05:
        return
    win = _win(img, x0, y0, x1, y1, pad=int(width * SS) + 2)
    if win is None:
        return
    X0, Y0, X1, Y1 = win
    lay = Image.new("RGBA", (X1 - X0, Y1 - Y0), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    bx = [
        round(x0 * SS - X0),
        round(y0 * SS - Y0),
        round(x1 * SS - X0),
        round(y1 * SS - Y0),
    ]
    bx[2], bx[3] = max(bx[2], bx[0]), max(bx[3], bx[1])
    f = rgba(fill, a) if fill is not None else None
    o = rgba(outline, a) if outline is not None else None
    w = max(1, int(round(width * SS))) if width else 1
    if kind == "rrect":
        d.rounded_rectangle(bx, radius=max(0, int(r * SS)), fill=f, outline=o, width=w)
    elif kind == "ellipse":
        d.ellipse(bx, fill=f, outline=o, width=w)
    elif kind == "pie":
        d.pieslice(bx, start, end, fill=f)
    elif kind == "arc":
        d.arc(bx, start, end, fill=o, width=w)
    comp(img, lay, X0, Y0)


def line(img, pts, color, width, a=1.0):
    """Polyline with round joints and caps."""
    if a <= 0.003 or len(pts) < 2:
        return
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    win = _win(img, min(xs) - width, min(ys) - width, max(xs) + width, max(ys) + width)
    if win is None:
        return
    X0, Y0, X1, Y1 = win
    lay = Image.new("RGBA", (X1 - X0, Y1 - Y0), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    q = [(x * SS - X0, y * SS - Y0) for x, y in pts]
    c = rgba(color, a)
    w = max(1, int(round(width * SS)))
    d.line(q, fill=c, width=w, joint="curve")
    rr = w / 2
    for x, y in (q[0], q[-1]):
        d.ellipse((x - rr, y - rr, x + rr, y + rr), fill=c)
    comp(img, lay, X0, Y0)


def dots(img, items):
    """Many small circles on one layer: items = [(x, y, r, color, alpha)]."""
    items = [it for it in items if it[4] > 0.01]
    if not items:
        return
    x0 = min(x - r for x, y, r, c, a in items)
    y0 = min(y - r for x, y, r, c, a in items)
    x1 = max(x + r for x, y, r, c, a in items)
    y1 = max(y + r for x, y, r, c, a in items)
    win = _win(img, x0, y0, x1, y1)
    if win is None:
        return
    X0, Y0, X1, Y1 = win
    lay = Image.new("RGBA", (X1 - X0, Y1 - Y0), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    for x, y, r, c, a in items:
        d.ellipse(
            (
                (x - r) * SS - X0,
                (y - r) * SS - Y0,
                (x + r) * SS - X0,
                (y + r) * SS - Y0,
            ),
            fill=rgba(c, a),
        )
    comp(img, lay, X0, Y0)


def font(size, key="bold"):
    return E.font(max(1, size * SS), {"bold": True, "reg": False}.get(key, key))


def text_w(s, size, key="bold"):
    return font(size, key).getlength(s) / SS


def text(
    img,
    s,
    xy,
    size,
    fill,
    key="bold",
    anchor="la",
    a=1.0,
    role="ui",
    log=None,
    nolog=False,
):
    """Draw text; log its font, string and 'la' origin so qa.text_box can rebuild the exact box.
    Returns the glyph box in output px (or None)."""
    if a <= 0.003 or not s or size < 1:
        return None
    f = font(size, key)
    x, y = xy[0] * SS, xy[1] * SS
    l, t_, r, b = f.getbbox(s, anchor=anchor)
    win = (
        max(0, int(math.floor(x + l)) - 3),
        max(0, int(math.floor(y + t_)) - 3),
        min(img.width, int(math.ceil(x + r)) + 3),
        min(img.height, int(math.ceil(y + b)) + 3),
    )
    if win[2] > win[0] and win[3] > win[1]:
        X0, Y0, X1, Y1 = win
        lay = Image.new("RGBA", (X1 - X0, Y1 - Y0), (0, 0, 0, 0))
        ImageDraw.Draw(lay).text(
            (x - X0, y - Y0), s, font=f, fill=rgba(fill, a), anchor=anchor
        )
        comp(img, lay, X0, Y0)
    if not nolog:
        l0, t0, _, _ = f.getbbox(s, anchor="la")
        e = dict(
            font=f,
            s=s,
            xy=(x + l - l0, y + t_ - t0),
            M=(0.0, 0.0, 1 / SS),
            fill=fill,
            size=size,
            key=key,
            role=role,
            a=a,
        )
        (TEXT_LOG if log is None else log).append(e)
    return (x + l) / SS, (y + t_) / SS, (x + r) / SS, (y + b) / SS


def with_alpha(im, a):
    if a >= 0.999:
        return im
    q = int(round(clamp(a) * 255))
    out = im.copy()
    out.putalpha(im.getchannel("A").point([v * q // 255 for v in range(256)]))
    return out


def place(img, spr, x, y, scale=1.0, a=1.0, crop=1.0):
    """Composite a sprite (im, ax, ay, logs) so its anchor lands on output px (x, y); log its text."""
    if a <= 0.003 or scale <= 0.005 or crop <= 0.001:
        return
    im, ax, ay, logs = spr
    sc = 1.0
    if abs(scale - 1) > 1e-3:
        w, h = (
            max(1, int(round(im.width * scale))),
            max(1, int(round(im.height * scale))),
        )
        sc = w / im.width
        im = im.resize((w, h), Image.Resampling.BICUBIC)
    if crop < 0.999:
        im = im.crop((0, 0, max(1, int(im.width * crop)), im.height))
    X, Y = int(round(x * SS - ax * sc)), int(round(y * SS - ay * sc))
    comp(img, with_alpha(im, a), X, Y)
    if crop >= 0.999:
        for e in logs:
            TEXT_LOG.append({**e, "M": (X / SS, Y / SS, sc / SS), "a": e["a"] * a})


@lru_cache(maxsize=512)
def _shadow_mask(w, h, r, blur):
    pad = blur * 3 + 2
    m = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    ImageDraw.Draw(m).rounded_rectangle((pad, pad, pad + w, pad + h), r, fill=255)
    return m.filter(ImageFilter.GaussianBlur(blur)), pad


def shadow(img, box, r, blur=22, dy=12, a=0.3, color=(24, 12, 36)):
    if a <= 0.003:
        return
    x0, y0, x1, y1 = [v * SS for v in box]
    w, h = int(round(x1 - x0)), int(round(y1 - y0))
    if w < 2 or h < 2:
        return
    m, pad = _shadow_mask(w, h, int(r * SS), max(1, int(blur * SS)))
    lay = Image.new("RGBA", m.size, color + (0,))
    q = int(round(clamp(a) * 255))
    lay.putalpha(m.point([v * q // 255 for v in range(256)]))
    comp(img, lay, int(round(x0)) - pad, int(round(y0 + dy * SS)) - pad)


# ---------- backgrounds ----------
BG_SMALL = (960, 540)
BLOBS_DARK = [  # colour, alpha, radius, x0, y0, ax, ay, fx, fy, phase
    (LILAC, 0.17, 430, 360, 250, 70, 50, 0.031, 0.023, 0.0),
    (CORAL, 0.12, 340, 1570, 830, 80, 60, 0.027, 0.035, 1.7),
    (LILAC, 0.10, 300, 1520, 170, 60, 40, 0.019, 0.029, 3.1),
]
BLOBS_LIGHT = [
    (LILAC, 0.34, 470, 280, 860, 80, 50, 0.024, 0.031, 0.4),
    (MINT, 0.22, 390, 1640, 230, 70, 60, 0.029, 0.021, 2.2),
    (CORAL, 0.11, 330, 1520, 930, 60, 40, 0.021, 0.027, 4.0),
]


@lru_cache(maxsize=4)
def _grad_small(c1, c2):
    a, b = np.array(hexrgb(c1)[:3], float), np.array(hexrgb(c2)[:3], float)
    ramp = a + (b - a) * np.linspace(0, 1, BG_SMALL[1])[:, None]
    arr = np.repeat(ramp[:, None, :], BG_SMALL[0], 1).round().astype(np.uint8)
    return Image.fromarray(arr, "RGB").convert("RGBA")


@lru_cache(maxsize=16)
def _blob(r, color, alpha):
    k = BG_SMALL[0] / W
    rs = r * k
    pad = rs * 0.9
    n = int(2 * (rs + pad))
    m = Image.new("L", (n, n), 0)
    ImageDraw.Draw(m).ellipse((pad, pad, n - pad, n - pad), fill=int(255 * alpha))
    m = m.filter(ImageFilter.GaussianBlur(rs * 0.45))
    lay = Image.new("RGBA", (n, n), hexrgb(color)[:3] + (0,))
    lay.putalpha(m)
    return lay


@lru_cache(maxsize=1)
def _flat_cream_small():
    return Image.new("RGBA", BG_SMALL, hexrgb(CREAM))


def bg_image(t, dark, mood=1.0):
    """Gradient plus drifting blobs. mood < 1 blends the light world toward flat cream #fff6ec
    (R701: the zoom ends on the flat cream square, so the timer scene starts flat and eases in)."""
    small = (
        _grad_small(PLUM_TOP, PLUM_BOT) if dark else _grad_small(CREAM_TOP, CREAM_BOT)
    ).copy()
    k = BG_SMALL[0] / W
    for c, al, r, x0, y0, ax, ay, fx, fy, ph in BLOBS_DARK if dark else BLOBS_LIGHT:
        x = x0 + ax * math.sin(2 * math.pi * fx * t + ph)
        y = y0 + ay * math.cos(2 * math.pi * fy * t + ph * 0.7)
        bl = _blob(r, c, al)
        comp(
            small,
            bl,
            int(round(x * k - bl.width / 2)),
            int(round(y * k - bl.height / 2)),
        )
    if not dark and mood < 1:
        small = Image.blend(_flat_cream_small(), small, clamp(mood))
    return small.resize((W * SS, H * SS), Image.Resampling.BICUBIC)


def circle_wipe(base, top, cx, cy, r):
    """Paste `top` over `base` inside a circle of radius r (output px) centred at (cx, cy)."""
    if r <= 0:
        return base
    m = Image.new("L", base.size, 0)
    ImageDraw.Draw(m).ellipse(
        ((cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS), fill=255
    )
    base.paste(top, (0, 0), m)
    return base


def wipe_radius(k, cx, cy):
    """Circle radius whose covered area grows like an in-out ease (keeps the luminance swing soft)."""
    far = max(math.hypot(cx - x, cy - y) for x in (0, W) for y in (0, H)) + 4
    return far * math.sqrt(ease_in_out_cubic(clamp(k)))


def background(t, name):
    if name == "noise":
        return bg_image(t, True)
    if name == "reveal":
        k = prog(t, *CUE["wipe_in"])
        if k >= 1:
            return bg_image(t, False)
        return circle_wipe(
            bg_image(t, True), bg_image(t, False), FP[0], FP[1], wipe_radius(k, *FP)
        )
    if name == "quiet":
        kd, kl = prog(t, *CUE["wipe_dark"]), prog(t, *CUE["wipe_light"])
        kx, ky = KNOB_ON
        if kd <= 0:
            return bg_image(t, False)
        if kl <= 0:
            if kd >= 1:
                return bg_image(t, True)
            return circle_wipe(
                bg_image(t, False), bg_image(t, True), kx, ky, wipe_radius(kd, kx, ky)
            )
        if kl >= 1:
            return bg_image(t, False)
        return circle_wipe(
            bg_image(t, True), bg_image(t, False), kx, ky, wipe_radius(kl, kx, ky)
        )
    if (
        name == "timer"
    ):  # cream on cream at the 12.5 s match cut, then the blobs ease back in
        return bg_image(t, False, ease_in_out_cubic(prog(t, *CUE["bg_in"])))
    return bg_image(t, False)


# ---------- captions ----------
def draw_caps(img, t):
    for s, t_in, t_out, tone in CAPS:
        if not (t_in <= t < t_out):
            continue
        ki = 1.0 if t_in == 0 else ease_out_expo(prog(t, t_in, CAP_IN))
        ko = ease_in_cubic(prog(t, t_out - CAP_OUT, CAP_OUT))
        a = (1.0 if t_in == 0 else ease_out_cubic(prog(t, t_in, CAP_IN))) * (1 - ko)
        y = CAP_Y + lerp(26, 0, ki) - 14 * ko
        text(
            img,
            s,
            (W / 2, y),
            CAP_SIZE,
            CREAM if tone == "light" else PLUM,
            "bold",
            "mm",
            a,
            role="caption",
        )


# ---------- the nook mark ----------
TILE, TILE_R, SQ, SQ_R, DOOR_R, DOT_R = 300, 70, 170, 20, 92, 22
DOT_HOME = (-45.0, 45.0)
WM_SIZE = 210


def draw_mark(img, cx, cy, s, size=TILE, rad=TILE_R, sq=1.0, dot=None, a=1.0):
    """Coral tile, cream square with a quarter-circle doorway at its lower left, plum dot in the doorway."""
    h = size * s / 2
    shape(img, "rrect", (cx - h, cy - h, cx + h, cy + h), CORAL, a, r=min(rad * s, h))
    if sq > 0.001:
        q = SQ / 2 * s * sq
        shape(img, "rrect", (cx - q, cy - q, cx + q, cy + q), CREAM, a, r=SQ_R * s * sq)
        ox, oy, rr = cx - q, cy + q, DOOR_R * s * sq
        shape(
            img,
            "pie",
            (ox - rr, oy - rr, ox + rr, oy + rr),
            CORAL,
            a,
            start=270,
            end=360,
        )
    if dot:
        dx, dy, sx, sy = dot
        x, y = cx + dx * s, cy + dy * s + DOT_R * s * (1 - sy)
        rx, ry = DOT_R * s * sx, DOT_R * s * sy
        shape(img, "ellipse", (x - rx, y - ry, x + rx, y + ry), PLUM, a)


@lru_cache(maxsize=2)
def wordmark_sprite():
    f = font(WM_SIZE, "black")
    l, t_, r, b = f.getbbox("nook", anchor="ls")
    xh = -f.getbbox("o", anchor="ls")[1]
    pad = 8
    im = Image.new("RGBA", (r - l + 2 * pad, b - t_ + 2 * pad), (0, 0, 0, 0))
    ox, oy = pad - l, pad - t_
    ImageDraw.Draw(im).text((ox, oy), "nook", font=f, fill=rgba(PLUM), anchor="ls")
    l0, t0, _, _ = f.getbbox("nook", anchor="la")
    logs = [
        dict(
            font=f,
            s="nook",
            xy=(ox + l - l0, oy + t_ - t0),
            fill=PLUM,
            size=WM_SIZE,
            key="black",
            role="ui",
            a=1.0,
        )
    ]
    return im, ox, oy - xh / 2, logs  # anchor: left edge, middle of the x-height


@lru_cache(maxsize=1)
def lock_geom():
    ww = text_w("nook", WM_SIZE, "black")
    gw = TILE + 56 + ww
    left = W / 2 - gw / 2
    return left + TILE / 2, left + TILE + 56


def squash(t, t_land, dur=0.14, amt=0.22):
    k = (t - t_land) / dur
    if 0 <= k < 1:
        v = math.sin(math.pi * k) * amt * (1 - k)
        return 1 + v, 1 - v
    return 1.0, 1.0


HOPS = [  # (t0, t1, from, to, height): a fall onto the tile, then two hops into the doorway
    (T(4, 2), CUE["hops"][0], (250.0, -330.0), (108.0, 30.0), 0),
    (CUE["hops"][0], CUE["hops"][1], (108.0, 30.0), (28.0, -18.0), 120),
    (CUE["hops"][1], CUE["hops"][2], (28.0, -18.0), DOT_HOME, 70),
]


def dot_state(t, hops=HOPS):
    if t < hops[0][0]:
        return None
    sx, sy = 1.0, 1.0
    for _, b, *_ in hops:
        qx, qy = squash(t, b)
        sx, sy = sx * qx, sy * qy
    for a, b, p0, p1, h in hops:
        if t < b:
            u = (t - a) / (b - a)
            x = lerp(p0[0], p1[0], u)
            y = (
                lerp(p0[1], p1[1], u * u)
                if h == 0
                else lerp(p0[1], p1[1], u) - h * 4 * u * (1 - u)
            )
            return (x, y, sx, sy)
    return (DOT_HOME[0], DOT_HOME[1], sx, sy)


# ---------- scene 1: noise ----------
NOTIF_SRC = ["Group chat", "Mail", "Shop", "Calendar", "News"]
NOTIF_MSG = {
    "Group chat": [
        "are you coming tonight?",
        "lol look at this",
        "who has the charger?",
        "ok but hear me out",
        "you there?",
    ],
    "Mail": [
        "Re: Re: quick question",
        "Following up on this",
        "Action needed: review",
        "Your weekly digest",
        "Can we hop on a call?",
    ],
    "Shop": [
        "Your cart misses you",
        "Back in stock",
        "Your order has shipped",
        "Something new for you",
        "Your receipt is here",
    ],
    "Calendar": [
        "Standup starts soon",
        "Reminder: call back",
        "Team sync moved",
        "Lunch is in your calendar",
        "Focus time? Not today",
    ],
    "News": [
        "Top stories for you",
        "You will not believe this",
        "Trending right now",
        "Catch up on today",
        "Breaking: more news",
    ],
}
NOTIF_ICON = {
    "Group chat": (MINT, PLUM),
    "Mail": (LILAC, PLUM),
    "Shop": (CORAL, PLUM),
    "Calendar": (CORAL_TXT, WHITE),
    "News": (PLUM, CREAM),
}
NW, NH = 440, 108


def _card_layout():
    rnd = random.Random(2026)
    keep_out = (
        540,
        340,
        1380,
        560,
    )  # the task card plus a margin; the caption band starts below y 840
    pos, tries = [], 0
    while len(pos) < 22:
        x, y = rnd.uniform(316, 1604), rnd.uniform(122, 762)
        bx = (x - 236, y - 76, x + 236, y + 76)
        if not (
            bx[2] <= keep_out[0]
            or bx[0] >= keep_out[2]
            or bx[3] <= keep_out[1]
            or bx[1] >= keep_out[3]
        ):
            continue
        tries += 1
        if tries < 5000 and any(
            math.hypot(x - px, (y - py) * 2.2) < 260 for px, py in pos
        ):
            continue
        pos.append((x, y))
    return pos


CARD_POS = _card_layout()


@lru_cache(maxsize=32)
def notif_sprite(i):
    src = NOTIF_SRC[i % 5]
    msg = NOTIF_MSG[src][i // 5]
    pad = 44
    im = Image.new("RGBA", ((NW + 2 * pad) * SS, (NH + 2 * pad) * SS), (0, 0, 0, 0))
    shadow(im, (pad, pad, pad + NW, pad + NH), 24, blur=16, dy=10, a=0.42)
    shape(
        im, "rrect", (pad, pad, pad + NW, pad + NH), [CREAM, WHITE, LILAC][i % 3], r=24
    )
    ic, lc = NOTIF_ICON[src]
    shape(im, "rrect", (pad + 22, pad + 26, pad + 78, pad + 82), ic, r=16)
    junk: list = []
    text(im, src[0], (pad + 50, pad + 54), 30, lc, "bold", "mm", log=junk)
    text(im, src, (pad + 98, pad + 44), 27, PLUM, "bold", "ls", log=junk)
    text(im, "now", (pad + NW - 22, pad + 44), 22, MUTED, False, "rs", log=junk)
    text(im, msg, (pad + 98, pad + 82), 26, PLUM, False, "ls", log=junk)
    ang = random.Random(77 + i).uniform(-5.5, 5.5)
    im = im.rotate(ang, resample=Image.Resampling.BICUBIC, expand=True)
    # the rotated card's bounds, logged as a texture box so the QA can keep captions clear of it
    c, s_ = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    hw, hh = NW / 2, NH / 2
    ex, ey = abs(hw * c) + abs(hh * s_), abs(hw * s_) + abs(hh * c)
    cxp, cyp = im.width / 2, im.height / 2
    box = (cxp - ex * SS, cyp - ey * SS, cxp + ex * SS, cyp + ey * SS)
    logs = [
        dict(
            box=box,
            s=f"card: {src}: {msg}",
            fill=PLUM,
            size=26,
            key=False,
            role="texture",
            a=1.0,
        )
    ]
    return im, cxp, cyp, logs


def draw_task(img, cx, cy, s=1.0, a=1.0, fill=CREAM, caret=True, chk=0.0, strike=0.0):
    """The one task card, 'Write the proposal'."""
    w, h = 760 * s, 150 * s
    box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
    shadow(img, box, 30 * s, blur=max(1, 26 * s), dy=14 * s, a=0.36 * a)
    shape(img, "rrect", box, fill, a, r=30 * s)
    bx, by = cx - 310 * s, cy
    shape(
        img,
        "ellipse",
        (bx - 24 * s, by - 24 * s, bx + 24 * s, by + 24 * s),
        None,
        a,
        outline=PLUM,
        width=4 * s,
    )
    if chk > 0:
        rr = 24 * s * chk
        shape(img, "ellipse", (bx - rr, by - rr, bx + rr, by + rr), MINT, a)
        line(
            img,
            [
                (bx - 11 * s, by + 1 * s),
                (bx - 3 * s, by + 9 * s),
                (bx + 12 * s, by - 9 * s),
            ],
            PLUM,
            5 * s,
            a * clamp(chk),
        )
    gb = text(
        img,
        "Write the proposal",
        (cx - 262 * s, cy),
        54 * s,
        mix(PLUM, MUTED, strike),
        "semi",
        "lm",
        a,
        role="ui",
    )
    if gb and caret:
        x = gb[2] + 10 * s
        shape(img, "rrect", (x, cy - 31 * s, x + 5 * s, cy + 31 * s), PLUM, a, r=2 * s)
    if gb and strike > 0:
        x0, x1 = gb[0] - 4 * s, gb[2] + 4 * s
        line(
            img,
            [(x0, cy + 3 * s), (lerp(x0, x1, strike), cy + 3 * s)],
            PLUM,
            4 * s,
            a * 0.8,
        )


def draw_point(img, t, k):
    cx, cy = FP
    g = glow_sprite(CORAL)
    place(img, g, cx, cy, 0.55 + 0.05 * math.sin(t * 6), 0.55 * clamp(k))
    r = 14 * k
    shape(img, "ellipse", (cx - r, cy - r, cx + r, cy + r), CORAL)


@lru_cache(maxsize=4)
def glow_sprite(color):
    n = 300 * SS
    m = Image.new("L", (n, n), 0)
    ImageDraw.Draw(m).ellipse((n * 0.3, n * 0.3, n * 0.7, n * 0.7), fill=200)
    m = m.filter(ImageFilter.GaussianBlur(n * 0.09))
    lay = Image.new("RGBA", (n, n), hexrgb(color)[:3] + (0,))
    lay.putalpha(m)
    return lay, n / 2, n / 2, []


def scene_noise(img, t):
    ck = ease_in_cubic(prog(t, *CUE["collapse"]))
    if ck < 1:
        caret = (t % (2 * B)) < B  # blinks once per two beats; on at t = 0
        draw_task(img, FP[0], FP[1], s=lerp(1, 0.03, ck), a=1 - ck**4, caret=caret)
        jit = 7 * clamp((t - 3.4) / 3.2) ** 2
        fi = int(round(t * FPS))
        for i, ti in enumerate(CUE["card_t"]):
            if t < ti:
                break
            s = lerp(0.72, 1.0, back(prog(t, ti, 0.22)))
            a = ease_out_cubic(prog(t, ti, 0.1))
            x, y = CARD_POS[i]
            if jit > 0:
                rj = random.Random(i * 7919 + fi)
                x, y = x + rj.uniform(-1, 1) * jit, y + rj.uniform(-1, 1) * jit
            if ck > 0:
                x, y, s = lerp(x, FP[0], ck), lerp(y, FP[1], ck), s * lerp(1, 0.03, ck)
            place(img, notif_sprite(i), x, y, s, a)
    pk = back(prog(t, 6.93, 0.12))
    if pk > 0:
        draw_point(img, t, pk)


# ---------- scene 2: reveal ----------
def scene_reveal(img, t):
    tcx_l, wx_l = lock_geom()
    cy = FP[1]
    zk = ease_in_out_cubic(prog(t, *CUE["zoom"]))
    sc = 34**zk
    tcx = lerp(FP[0], tcx_l, ease_in_out_cubic(prog(t, *CUE["slide"])))
    P = (
        tcx_l + 12,
        cy - 12,
    )  # zoom origin: inside the cream square, clear of the doorway
    C = (lerp(P[0], FP[0], zk), lerp(P[1], FP[1], zk))

    def cam(x, y):
        if zk <= 0:
            return x, y
        return C[0] + sc * (x - P[0]), C[1] + sc * (y - P[1])

    gk = prog(t, *CUE["tile"])
    size = lerp(28, TILE, back(gk)) if gk < 1 else TILE
    rad = lerp(14, TILE_R, ease_out_cubic(gk))
    if gk < 1:
        place(img, glow_sprite(CORAL), FP[0], FP[1], 0.55, 0.55 * (1 - gk))
    sq = back(prog(t, *CUE["square"]))
    mx, my = cam(tcx, cy)
    draw_mark(img, mx, my, sc, size=size, rad=rad, sq=sq, dot=dot_state(t))
    wk = prog(t, *CUE["word"])
    if wk > 0:
        wx, wy = cam(wx_l - 30 * (1 - ease_out_cubic(wk)), cy)
        if wx < W + 50:
            place(img, wordmark_sprite(), wx, wy, sc, 1.0, crop=ease_out_cubic(wk))


# ---------- scene 3: focus timer ----------
RING_R, RING_W = 240, 30


def clock(t):
    """(mode, remaining seconds, ring fraction): the one clock function the digits and the ring both read."""
    a, b = CUE["count"]
    if t < b:
        rem = 1500 * (1 - clamp((t - a) / (b - a)))
        return "focus", rem, rem / 1500
    k = ease_out_cubic(prog(t, b, 0.35))
    rem = 300 - max(0.0, t - (b + 0.35)) * 10  # the break runs at 10x
    return "break", rem, k * rem / 300


def mmss(rem):
    s = int(math.ceil(rem - 1e-6))
    return f"{s // 60:02d}:{s % 60:02d}"


def slot_text(img, s, cx, baseline, size, fill, key, a, role="ui"):
    """Digits in fixed-width slots so a running clock does not wobble."""
    dw = max(text_w(d, size, key) for d in "0123456789")
    ws = [
        dw if ch.isdigit() else text_w(ch, size, key) + size * 0.08 for ch in s
    ]  # air around the colon
    x = cx - sum(ws) / 2
    for ch, w in zip(s, ws):
        text(img, ch, (x + w / 2, baseline), size, fill, key, "ms", a, role=role)
        x += w


def ring(img, cx, cy, R, st, frac, color, a=1.0, track_a=1.0):
    o = R + st / 2
    shape(
        img,
        "ellipse",
        (cx - o, cy - o, cx + o, cy + o),
        None,
        a * track_a,
        outline=TRACK,
        width=st,
    )
    if frac <= 0.002:
        return
    if frac >= 0.999:
        shape(
            img,
            "ellipse",
            (cx - o, cy - o, cx + o, cy + o),
            None,
            a,
            outline=color,
            width=st,
        )
        return
    shape(
        img,
        "arc",
        (cx - o, cy - o, cx + o, cy + o),
        None,
        a,
        outline=color,
        width=st,
        start=-90,
        end=-90 + 360 * frac,
    )
    caps = []
    for ang in (-90, -90 + 360 * frac):
        x = cx + R * math.cos(math.radians(ang))
        y = cy + R * math.sin(math.radians(ang))
        caps.append((x, y, st / 2, color, a))
    dots(img, caps)


CHIPS = [("25", 880), ("30", 1040)]
CHIP_Y = 790


def scene_timer(img, t):
    ao = 1 - ease_in_cubic(prog(t, *CUE["timer_out"]))
    so = 1 - 0.06 * ease_in_cubic(prog(t, *CUE["timer_out"]))
    mode, rem, frac = clock(t)
    on = ease_out_cubic(prog(t, *CUE["ring_on"]))
    cx, cy = FP
    col = (
        CORAL if mode == "focus" else MINT
    )  # the coral arc is empty at the switch; mint refills from 0
    ring(img, cx, cy, RING_R * so, RING_W, min(on, frac), col, ao, track_a=on)
    da = ao * ease_out_cubic(prog(t, T(6) + 0.15, 0.4))
    slot_text(img, mmss(rem), cx, cy + 42, 148, PLUM, "bold", da)
    if mode == "focus":
        text(img, "Focus", (cx, cy + 110), 40, CORAL_TXT, "semi", "mm", da)
    else:
        text(img, "Break", (cx, cy + 110), 40, MINT_TXT, "semi", "mm", ao)
    for j, (lab, x) in enumerate(CHIPS):
        ki = back(prog(t, CUE["chips_in"] + 0.08 * j, 0.35))
        if ki <= 0:
            continue
        tap = CUE["taps"][j]
        press = (
            1 - 0.08 * math.sin(math.pi * clamp((t - tap) / 0.2)) if t >= tap else 1.0
        )
        s = ki * press
        w, h = 132 * s, 66 * s
        box = (x - w / 2, CHIP_Y - h / 2, x + w / 2, CHIP_Y + h / 2)
        on_k = (
            clamp((t - CUE["taps"][1]) / 0.15)
            if j == 1
            else 1 - clamp((t - CUE["taps"][1]) / 0.15)
        )
        a = ao * clamp(ki)
        shape(
            img,
            "rrect",
            box,
            mix(WHITE, PLUM, on_k),
            a,
            r=h / 2,
            outline=LILAC,
            width=3,
        )
        text(img, lab, (x, CHIP_Y), 40 * s, mix(PLUM, CREAM, on_k), "bold", "mm", a)
        if t >= tap:
            u = clamp((t - tap) / 0.45)
            rr = lerp(30, 95, ease_out_cubic(u))
            shape(
                img,
                "ellipse",
                (x - rr, CHIP_Y - rr, x + rr, CHIP_Y + rr),
                None,
                ao * 0.5 * (1 - u),
                outline=PLUM,
                width=4,
            )


# ---------- scene 4: task list ----------
TASKS = [
    "Plan the week",
    "Call the plumber",
    "Water the plants",
    "Draft the newsletter",
]
PANEL_X0, PANEL_X1, PANEL_Y0 = 510, 1410, 90
ROW0, ROW_H = 275, 100
DONE = (3, 1)  # 'Draft the newsletter' and 'Call the plumber' get checked
KEEP = (0, 2)


def row_y(r):
    return ROW0 + r * ROW_H


def task_rows(t):
    """Row index (float) per task: the bottom task is dragged to the top, then the done ones leave."""
    d0, d1 = CUE["drag"]
    mv = ease_in_out_cubic(prog(t, d0 + 0.15, d1 - d0 - 0.35))
    rows = {3: lerp(3, 0, mv)}
    for i in (0, 1, 2):
        rows[i] = i + ease_in_out_cubic(prog(t, d0 + 0.3 + 0.06 * i, 0.7))
    up = ease_in_out_cubic(prog(t, *CUE["slide_up"]))
    rows[0] = lerp(rows[0], 0, up)
    rows[2] = lerp(rows[2], 1, up)
    return rows


def clock_roll(img, t, x, y):
    a0, a1 = CUE["roll"]
    k = ease_in_out_cubic(prog(t, a0, a1 - a0))
    old, new = "11:59 PM", "12:00 AM"
    if k <= 0 or k >= 1:
        text(img, old if k <= 0 else new, (x, y), 44, PLUM, "semi", "rs")
        return
    # roll inside a clip box aligned to the text baseline
    bw, bh = 260, 70
    lay = Image.new("RGBA", (bw * SS, bh * SS), (0, 0, 0, 0))
    lx, ly = bw - 4, bh - 18  # baseline position inside the clip
    text(lay, old, (lx, ly - 52 * k), 44, PLUM, "semi", "rs", 1 - k, nolog=True)
    text(lay, new, (lx, ly + 52 * (1 - k)), 44, PLUM, "semi", "rs", k, nolog=True)
    comp(img, lay, int(round((x - lx) * SS)), int(round((y - ly) * SS)))


def scene_tasks(img, t):
    ki = ease_out_expo(prog(t, *CUE["panel_in"]))
    ko = ease_in_cubic(prog(t, *CUE["tasks_out"]))
    a = clamp(ki) * (1 - ko)
    dy = lerp(60, 0, ki) - 30 * ko
    if a <= 0.003:
        return
    up = ease_in_out_cubic(prog(t, *CUE["slide_up"]))
    leave = ease_in_cubic(prog(t, *CUE["leave"]))
    add_r = lerp(4, 2, up)
    y1 = row_y(add_r) + 70
    box = (PANEL_X0, PANEL_Y0 + dy, PANEL_X1, y1 + dy)
    shadow(img, box, 34, blur=30, dy=16, a=0.18 * a)
    shape(img, "rrect", box, WHITE, a, r=34)
    text(img, "Today", (PANEL_X0 + 50, 165 + dy), 52, PLUM, "bold", "lm", a)
    if a > 0.99:
        clock_roll(img, t, PANEL_X1 - 50, 181 + dy)
    else:
        text(
            img,
            "11:59 PM" if t < CUE["roll"][0] else "12:00 AM",
            (PANEL_X1 - 50, 181 + dy),
            44,
            PLUM,
            "semi",
            "rs",
            a,
        )
    shape(
        img, "rrect", (PANEL_X0 + 40, 220 + dy, PANEL_X1 - 40, 223 + dy), LILAC, a, r=1
    )
    rows = task_rows(t)
    d0, d1 = CUE["drag"]
    lift = clamp((t - d0) / 0.15) * (1 - clamp((t - (d1 - 0.2)) / 0.2))
    order = sorted(
        range(4), key=lambda i: (i == 3 and lift > 0, rows[i])
    )  # dragged row on top
    for i in order:
        y = row_y(rows[i]) + dy
        ra, rx = a, 0.0
        if i in DONE:
            ra *= 1 - leave
            rx = 140 * leave
        if ra <= 0.003:
            continue
        if i == 3 and lift > 0:
            s = 1 + 0.025 * lift
            rb = (
                PANEL_X0 + 26 - 8 * lift,
                y - 44 * s,
                PANEL_X1 - 26 + 8 * lift,
                y + 44 * s,
            )
            shadow(img, rb, 22, blur=18, dy=10, a=0.22 * lift * ra)
            shape(img, "rrect", rb, mix(WHITE, "#f3effb", lift), ra, r=22)
        x0 = PANEL_X0 + 60 + rx
        ck = 0.0
        if i in DONE:
            ck = back(prog(t, CUE["checks"][DONE.index(i)], 0.25))
        shape(
            img,
            "ellipse",
            (x0 - 20, y - 20, x0 + 20, y + 20),
            None,
            ra,
            outline=PLUM,
            width=3.5,
        )
        if ck > 0:
            rr = 20 * ck
            shape(img, "ellipse", (x0 - rr, y - rr, x0 + rr, y + rr), MINT, ra)
            line(
                img,
                [(x0 - 9, y + 1), (x0 - 2, y + 8), (x0 + 10, y - 8)],
                PLUM,
                4.5,
                ra * clamp(ck),
            )
        st = clamp(ck)
        gb = text(
            img, TASKS[i], (x0 + 45, y), 44, mix(PLUM, MUTED, st), False, "lm", ra
        )
        if gb and st > 0:
            line(
                img,
                [
                    (gb[0] - 3, y + 3),
                    (lerp(gb[0] - 3, gb[2] + 3, ease_out_cubic(st)), y + 3),
                ],
                MUTED,
                3.5,
                ra * 0.85,
            )
        if i in KEEP:
            tk = back(prog(t, CUE["tags"] + 0.1 * KEEP.index(i), 0.25))
            if tk > 0:
                tw = text_w("Carried over", 36, "semi") + 40
                cx = PANEL_X1 - 50 - tw / 2
                w, h = tw * tk, 54 * tk
                shape(
                    img,
                    "rrect",
                    (cx - w / 2, y - h / 2, cx + w / 2, y + h / 2),
                    LILAC,
                    ra * clamp(tk),
                    r=h / 2,
                )
                text(
                    img,
                    "Carried over",
                    (cx, y),
                    36 * tk,
                    PLUM,
                    "semi",
                    "mm",
                    ra * clamp(tk),
                )
    ya = row_y(add_r) + dy
    x0 = PANEL_X0 + 60
    shape(
        img,
        "ellipse",
        (x0 - 20, ya - 20, x0 + 20, ya + 20),
        None,
        a,
        outline=LILAC,
        width=3.5,
    )
    line(img, [(x0 - 9, ya), (x0 + 9, ya)], MUTED, 3.5, a)
    line(img, [(x0, ya - 9), (x0, ya + 9)], MUTED, 3.5, a)
    text(img, "Add a task", (x0 + 45, ya), 40, MUTED, False, "lm", a)


# ---------- scene 5: quiet mode ----------
TOG = (690, 90, 1230, 200)
TRACK_BOX = (1090, 113, 1190, 177)
KNOB_OFF, KNOB_ON = (1122, 145), (1158, 145)
NOOK_S = 0.8
SESSION = (720, 640, 1200, 750)
QN_LANES = [
    (-1, 330, 0),
    (1, 520, 1),
    (-1, 560, 2),
    (1, 340, 3),
    (-1, 450, 4),
    (1, 470, 0),
]
QW, QH = 320, 84


@lru_cache(maxsize=8)
def qnotif_sprite(j):
    src = NOTIF_SRC[j % 5]
    msg = NOTIF_MSG[src][(j + 2) % 5]
    pad = 30
    im = Image.new("RGBA", ((QW + 2 * pad) * SS, (QH + 2 * pad) * SS), (0, 0, 0, 0))
    shape(im, "rrect", (pad, pad, pad + QW, pad + QH), WHITE, r=22)
    ic, lc = NOTIF_ICON[src]
    shape(im, "ellipse", (pad + 18, pad + 20, pad + 62, pad + 64), ic)
    logs: list = []
    text(im, src[0], (pad + 40, pad + 42), 24, lc, "bold", "mm", log=logs)
    text(im, src, (pad + 78, pad + 36), 25, PLUM, "bold", "ls", log=logs)
    text(im, msg, (pad + 78, pad + 68), 23, PLUM, False, "ls", log=logs)
    for e in logs:
        e["role"] = "texture"
    return im, im.width / 2, im.height / 2, logs


def qnotif(img, t, j):
    t0 = CUE["qnotif"][j]
    side, y, src = QN_LANES[j]
    if t < t0:
        return
    fly, dis = 0.9, 0.7
    x_start = -200 if side < 0 else W + 200
    x_stop = FP[0] + side * 490
    if t < t0 + fly + 0.25:
        x = lerp(x_start, x_stop, ease_out_cubic(prog(t, t0, fly)))
        a = 1 - clamp((t - (t0 + fly)) / 0.25)
        place(img, qnotif_sprite(src), x, y, 1.0 - 0.15 * (1 - a), a)
    u = (t - (t0 + fly)) / dis
    if 0 <= u < 1:
        rnd = random.Random(500 + j)
        dt = t - (t0 + fly)
        items = []
        for _ in range(44):
            px, py = (
                x_stop + rnd.uniform(-QW / 2, QW / 2),
                y + rnd.uniform(-QH / 2, QH / 2),
            )
            vx, vy = -side * rnd.uniform(40, 150), rnd.uniform(-70, 70)
            r = rnd.uniform(2.5, 6.0)
            c = rnd.choice([CREAM, LILAC, WHITE])
            items.append(
                (
                    px + vx * dt,
                    py + vy * dt - 20 * dt,
                    r * (1 - 0.4 * u),
                    c,
                    (1 - u) ** 1.6 * clamp(dt / 0.06),
                )
            )
        dots(img, items)


def scene_quiet(img, t):
    ki = ease_out_expo(prog(t, *CUE["toggle_in"]))
    ko = ease_in_cubic(prog(t, *CUE["quiet_out"]))
    a = clamp(ki) * (1 - ko)
    dy = lerp(-30, 0, ki)
    dark = prog(t, *CUE["wipe_dark"]) > 0.5 and prog(t, *CUE["wipe_light"]) < 0.5
    # the nook, with a soft glow while quiet
    gk = clamp((t - CUE["wipe_dark"][0]) / 0.8) * (
        1 - clamp((t - CUE["wipe_light"][0]) / 0.5)
    )
    if gk > 0:
        place(
            img,
            glow_sprite(CORAL),
            FP[0],
            FP[1],
            1.1 + 0.05 * math.sin(t * 2.2),
            0.42 * gk * a,
        )
    draw_mark(
        img,
        FP[0],
        FP[1] + dy * 0.5,
        NOOK_S * lerp(0.9, 1.0, ki),
        dot=(DOT_HOME[0], DOT_HOME[1], 1.0, 1.0),
        a=a,
    )
    for j in range(len(CUE["qnotif"])):
        qnotif(img, t, j)
    # toggle card
    box = (TOG[0], TOG[1] + dy, TOG[2], TOG[3] + dy)
    shadow(img, box, 30, blur=24, dy=12, a=(0.4 if dark else 0.16) * a)
    shape(img, "rrect", box, WHITE, a, r=30)
    text(
        img,
        "Quiet mode",
        (TOG[0] + 45, (TOG[1] + TOG[3]) / 2 + dy),
        46,
        PLUM,
        "bold",
        "lm",
        a,
    )
    kon = ease_in_out_cubic(prog(t, CUE["toggle_on"], 0.2)) * (
        1 - ease_in_out_cubic(prog(t, CUE["wipe_light"][0] - 0.2, 0.2))
    )
    tb = (TRACK_BOX[0], TRACK_BOX[1] + dy, TRACK_BOX[2], TRACK_BOX[3] + dy)
    shape(img, "rrect", tb, mix(LILAC, CORAL, kon), a, r=32)
    kx = lerp(KNOB_OFF[0], KNOB_ON[0], kon)
    ky = KNOB_OFF[1] + dy
    shadow(img, (kx - 26, ky - 26, kx + 26, ky + 26), 26, blur=6, dy=3, a=0.25 * a)
    shape(img, "ellipse", (kx - 26, ky - 26, kx + 26, ky + 26), WHITE, a)
    # session card
    sk = ease_out_expo(prog(t, CUE["wipe_dark"][0] + 0.5, 0.5))
    sa = a * clamp(sk)
    if sa > 0.003:
        sdy = lerp(30, 0, sk)
        sb = (SESSION[0], SESSION[1] + sdy, SESSION[2], SESSION[3] + sdy)
        shadow(img, sb, 28, blur=24, dy=12, a=0.4 * sa)
        shape(img, "rrect", sb, WHITE, sa, r=28)
        n = sum(1 for tk in CUE["session_ticks"] if t >= tk)
        rem = 18 * 60 + 42 - n
        mid = (sb[1] + sb[3]) / 2
        text(img, "Focus session", (sb[0] + 40, mid), 36, PLUM, "semi", "lm", sa)
        text(
            img,
            f"{rem // 60:02d}:{rem % 60:02d}",
            (sb[2] - 40, mid),
            56,
            PLUM,
            "bold",
            "rm",
            sa,
        )


# ---------- scene 6: streak ----------
DAYS = ["M", "T", "W", "T", "F", "S", "S"]
TS, TG, TILE_Y = 150, 28, 470


def tile_x(i):
    x0 = W / 2 - (7 * TS + 6 * TG) / 2
    return x0 + TS / 2 + i * (TS + TG)


def scene_streak(img, t):
    ko = ease_in_cubic(prog(t, *CUE["streak_out"]))
    fills = CUE["fills"]
    rest = CUE["rest"]
    count = sum(1 for i, f in enumerate(fills) if t >= f and i != rest)
    # counter
    la = (1 - ko) * ease_out_cubic(prog(t, T(15) + 0.1, 0.4))
    nsz, lsz = 170, 50
    dw = max(text_w(d, nsz, "black") for d in "0123456789")
    lw = text_w("day streak", lsz, "semi")
    gx = W / 2 - (dw + 28 + lw) / 2
    base = 290
    if count > 0:
        last = max(f for i, f in enumerate(fills) if t >= f and i != rest)
        pop = 1 + 0.16 * (1 - ease_out_cubic(prog(t, last, 0.3)))
        text(
            img, str(count), (gx + dw / 2, base), nsz * pop, PLUM, "black", "ms", 1 - ko
        )
    text(img, "day streak", (gx + dw + 28, base - 8), lsz, CORAL_TXT, "semi", "ls", la)
    # tiles
    for i in range(7):
        ki = back(prog(t, T(15) + 0.05 * i, 0.4))
        a = clamp(ki) * (1 - ko)
        if a <= 0.003:
            continue
        x = tile_x(i)
        wave = (
            -18 * math.sin(math.pi * prog(t, CUE["wave"] + 0.07 * i, 0.35))
            if i != rest
            else 0.0
        )
        y = TILE_Y + wave + 30 * ko
        fk = prog(t, fills[i], 0.25)
        if i == rest:
            pulse = 1 - 0.05 * math.sin(math.pi * fk)
            s = ki * pulse
            h = TS / 2 * s
            shape(
                img,
                "rrect",
                (x - h, y - h, x + h, y + h),
                mix(WHITE, LILAC, 0.45),
                a,
                r=34 * s,
                outline=LILAC,
                width=4,
            )
            line(img, [(x - 22 * s, y), (x + 22 * s, y)], MUTED, 6 * s, a * 0.45)
        else:
            s = ki * (lerp(0.86, 1.0, back(fk)) if fk > 0 else 1.0)
            h = TS / 2 * s
            fill = mix(WHITE, MINT, clamp(fk / 0.6))
            shape(
                img,
                "rrect",
                (x - h, y - h, x + h, y + h),
                fill,
                a,
                r=34 * s,
                outline=mix(LILAC, MINT, clamp(fk / 0.6)),
                width=4,
            )
            ck = ease_out_cubic(prog(t, fills[i] + 0.06, 0.2))
            if ck > 0:
                p0, p1, p2 = (
                    (x - 30 * s, y + 2 * s),
                    (x - 9 * s, y + 23 * s),
                    (x + 32 * s, y - 22 * s),
                )
                pts = [
                    p0,
                    (
                        lerp(p0[0], p1[0], clamp(ck * 2)),
                        lerp(p0[1], p1[1], clamp(ck * 2)),
                    ),
                ]
                if ck > 0.5:
                    pts.append(
                        (
                            lerp(p1[0], p2[0], (ck - 0.5) * 2),
                            lerp(p1[1], p2[1], (ck - 0.5) * 2),
                        )
                    )
                line(img, pts, PLUM, 9 * s, a)
        text(
            img,
            DAYS[i],
            (x, TILE_Y + TS / 2 + 52 + 30 * ko),
            36,
            MUTED,
            "semi",
            "mm",
            a,
        )


# ---------- scene 7: the word, and devices ----------
CARD_W, CARD_H = 1130, 300
DICT_SEGS = [  # (text, font key, size, colour, line, typed chars before it, extra gap before it)
    ("nook", "black", 112, PLUM, 0, 0, 0),
    (
        " (n.):",
        "ital",
        60,
        CORAL_TXT,
        0,
        4,
        8,
    ),  # 8 px so the italic overhang clears the k
    ("a small, quiet place to do one thing.", False, 60, PLUM, 1, 11, 0),
]
LINE_BASE = (140, 238)
DICT_TOP = (960, 172)
DICT_TOP_S = 0.65


def typed(t):
    return sum(1 for tt in CUE["type_t"] if t >= tt)


def draw_dict(img, x0, y0, n, a=1.0, caret_on=False, log=None):
    """Dictionary card with the first n characters of DICT_TEXT typed; (x0, y0) = card top-left."""
    box = (x0, y0, x0 + CARD_W, y0 + CARD_H)
    shadow(img, box, 36, blur=30, dy=16, a=0.2 * a)
    shape(img, "rrect", box, WHITE, a, r=36)
    shape(img, "rrect", (x0, y0 + 40, x0 + 10, y0 + CARD_H - 40), CORAL, a, r=5)
    xs = [x0 + 70, x0 + 70]  # pen x per line
    cx_end, cy_end = x0 + 70, y0 + LINE_BASE[0]
    for s, key, size, col, ln, before, gap in DICT_SEGS:
        xs[ln] += gap
        k = max(0, min(len(s), n - before))
        yb = y0 + LINE_BASE[ln]
        if k > 0:
            text(img, s[:k], (xs[ln], yb), size, col, key, "ls", a, log=log)
            cx_end, cy_end = xs[ln] + text_w(s[:k], size, key), yb
        xs[ln] += text_w(s, size, key)
    if caret_on:
        shape(
            img,
            "rrect",
            (cx_end + 6, cy_end - 58, cx_end + 11, cy_end + 10),
            PLUM,
            a,
            r=2,
        )


@lru_cache(maxsize=1)
def dict_sprite():
    pad = 60
    im = Image.new(
        "RGBA", ((CARD_W + 2 * pad) * SS, (CARD_H + 2 * pad) * SS), (0, 0, 0, 0)
    )
    logs: list = []
    draw_dict(im, pad, pad, len(DICT_TEXT), log=logs)
    return im, (pad + CARD_W / 2) * SS, (pad + CARD_H / 2) * SS, logs


def device_screen(img, cx, cy, R, st, dsz, t, a):
    rem = 1500 - max(0.0, t - CUE["desk_in"][0])
    ring(img, cx, cy, R, st, rem / 1500, CORAL, a)
    slot_text(img, mmss(rem), cx, cy + dsz * 0.36, dsz, PLUM, "bold", a)


def scene_word(img, t):
    ko = ease_in_cubic(prog(t, *CUE["word_out"]))
    ki = ease_out_expo(prog(t, *CUE["dict_in"]))
    mk = ease_in_out_cubic(prog(t, *CUE["dict_move"]))
    a = clamp(ki) * (1 - ko)
    n = typed(t)
    if mk <= 0:
        x0 = FP[0] - CARD_W / 2
        y0 = FP[1] - CARD_H / 2 + lerp(40, 0, ki)
        caret = n < len(DICT_TEXT) or (t % (2 * B)) < B
        draw_dict(img, x0, y0, n, a, caret_on=caret and t >= CUE["dict_in"][0] + 0.2)
    else:
        x = lerp(FP[0], DICT_TOP[0], mk)
        y = lerp(FP[1], DICT_TOP[1], mk)
        place(img, dict_sprite(), x, y, lerp(1, DICT_TOP_S, mk), a)
    # desktop
    dk = ease_out_expo(prog(t, *CUE["desk_in"]))
    if dk > 0:
        da = clamp(dk) * (1 - ko)
        oy = lerp(620, 0, dk)
        mx0, my0, mx1, my1 = 450, 330 + oy, 1150, 740 + oy
        shadow(img, (mx0, my0, mx1, my1), 24, blur=30, dy=18, a=0.22 * da)
        shape(img, "rrect", (785, my1 - 10, 815, my1 + 48), PLUM, da, r=6)
        shape(img, "rrect", (690, my1 + 44, 910, my1 + 62), PLUM, da, r=9)
        shape(img, "rrect", (mx0, my0, mx1, my1), PLUM, da, r=24)
        shape(img, "rrect", (mx0 + 18, my0 + 18, mx1 - 18, my1 - 18), CREAM, da, r=10)
        device_screen(img, (mx0 + mx1) / 2, (my0 + my1) / 2, 118, 18, 64, t, da)
    pk = ease_out_expo(prog(t, *CUE["phone_in"]))
    if pk > 0:
        pa = clamp(pk) * (1 - ko)
        oy = lerp(620, 0, pk)
        px0, py0, px1, py1 = 1220, 335 + oy, 1440, 785 + oy
        shadow(img, (px0, py0, px1, py1), 40, blur=26, dy=16, a=0.25 * pa)
        shape(img, "rrect", (px0, py0, px1, py1), PLUM, pa, r=40)
        shape(img, "rrect", (px0 + 12, py0 + 12, px1 - 12, py1 - 12), CREAM, pa, r=30)
        shape(img, "rrect", (1300, py0 + 24, 1360, py0 + 36), PLUM, pa, r=6)
        device_screen(img, (px0 + px1) / 2, (py0 + py1) / 2, 72, 12, 40, t, pa)


# ---------- scenes 8 and 9: payoff and end hold ----------
END_CY = 360
TAG_Y, PILL_Y, DISC_Y = 590, 712, 852
PILL_H, PILL_SIZE = 68, 36


@lru_cache(maxsize=1)
def pill_layout():
    ws = [
        text_w(p, PILL_SIZE, "semi") + 94 for p in PILLS
    ]  # 28 pad, 14 dot, 16 gap, text, 36 pad
    gap = 22
    x = W / 2 - (sum(ws) + gap * (len(ws) - 1)) / 2
    out = []
    for w in ws:
        out.append((x, x + w))
        x += w + gap
    return out


CONFETTI_C = [CORAL, MINT, LILAC, PLUM, CORAL_TXT, MINT_TXT]


def confetti(img, t, t0, x, y):
    dt = t - t0
    if dt < 0 or dt > 1.2:
        return
    rnd = random.Random(4242)
    items = []
    for _ in range(46):
        vx, vy = rnd.uniform(-460, 460), rnd.uniform(-980, -380)
        r = rnd.uniform(4, 8)
        c = rnd.choice(CONFETTI_C)
        px = x + vx * dt
        py = y + vy * dt + 0.5 * 1700 * dt * dt
        items.append((px, py, r, c, 1 - clamp((dt - 0.75) / 0.45)))
    dots(img, items)


def draw_lockup(img, t, log=None, final=False):
    """Tile, wordmark, tagline and the four feature pills, built on the beat (final=True draws the end state)."""
    tcx, wx = lock_geom()
    f = (lambda v: 1.0) if final else (lambda v: v)
    kt = f(back(prog(t, CUE["lk_tile"], 0.4)))
    if kt > 0:
        sq = f(back(prog(t, CUE["lk_square"], 0.3)))
        d0, d1 = CUE["lk_dot"]
        dot = None
        if final or t >= d0:
            u = 1.0 if final else clamp((t - d0) / (d1 - d0))
            sx, sy = (1.0, 1.0) if final else squash(t, d1)
            dot = (DOT_HOME[0], lerp(-260, DOT_HOME[1], u * u), sx, sy)
        draw_mark(img, tcx, END_CY, kt, sq=sq, dot=dot)
    wk = f(prog(t, *CUE["lk_word"]))
    if wk > 0:
        spr = wordmark_sprite()
        if log is None:
            place(
                img,
                spr,
                wx - 30 * (1 - ease_out_cubic(wk)),
                END_CY,
                1.0,
                1.0,
                crop=ease_out_cubic(wk),
            )
        else:
            im, ax, ay, logs = spr
            X, Y = int(round(wx * SS - ax)), int(round(END_CY * SS - ay))
            comp(img, im, X, Y)
            # store in canvas px so later placements (scale 1 or the end push-in) can re-map one M for all
            log.extend(
                {**e, "xy": (X + e["xy"][0], Y + e["xy"][1]), "M": (0.0, 0.0, 1 / SS)}
                for e in logs
            )
    tk = f(prog(t, *CUE["lk_tag"]))
    if tk > 0:
        text(
            img,
            TAGLINE,
            (W / 2, TAG_Y + lerp(22, 0, ease_out_expo(tk))),
            64,
            PLUM,
            "bold",
            "mm",
            ease_out_cubic(tk),
            log=log,
        )
    for i, (x0, x1) in enumerate(pill_layout()):
        pk = f(back(prog(t, CUE["pills"][i], 0.3)))
        if pk <= 0:
            continue
        cx = (x0 + x1) / 2
        w, h = (x1 - x0) * pk, PILL_H * pk
        pa = clamp(pk)
        shape(
            img,
            "rrect",
            (cx - w / 2, PILL_Y - h / 2, cx + w / 2, PILL_Y + h / 2),
            LILAC,
            pa,
            r=h / 2,
        )
        dx, dy = cx - w / 2 + 35 * pk, 2 * pk
        shape(
            img,
            "ellipse",
            (dx - 7 * pk, PILL_Y + dy - 7 * pk, dx + 7 * pk, PILL_Y + dy + 7 * pk),
            [CORAL, MINT_TXT, PLUM, CORAL_TXT][i],
            pa,
        )
        text(
            img,
            PILLS[i],
            (cx + 11 * pk, PILL_Y),
            PILL_SIZE * pk,
            PLUM,
            "semi",
            "mm",
            pa,
            log=log,
        )


@lru_cache(maxsize=1)
def end_layer():
    """The finished lockup plus the sample-film line, as one transparent canvas (pure, cached)."""
    lay = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    logs: list = []
    draw_lockup(lay, DURATION, log=logs, final=True)
    text(lay, DISCLAIMER, (W / 2, DISC_Y), 36, MUTED, False, "mm", log=logs)
    return lay, logs


def scene_payoff(img, t):
    ki = back(prog(t, *CUE["task2_in"]))
    ko = ease_in_cubic(prog(t, *CUE["task2_out"]))
    if ki > 0 and ko < 1:
        chk = back(prog(t, CUE["check2"], 0.25))
        strike = ease_out_cubic(prog(t, CUE["check2"] + 0.1, 0.3))
        draw_task(
            img,
            FP[0],
            FP[1],
            s=lerp(0.86, 1.0, ki) * (1 - 0.1 * ko),
            a=clamp(ki) * (1 - ko),
            fill=WHITE,
            caret=False,
            chk=chk,
            strike=strike,
        )
        confetti(img, t, CUE["check2"], FP[0] - 310, FP[1])
    if t >= CUE["pills"][-1] + 0.35:
        lay, logs = end_layer()
        da = ease_out_cubic(prog(t, *CUE["disclaimer"]))
        if da >= 1:
            img.alpha_composite(lay)
            TEXT_LOG.extend({**e, "M": (0.0, 0.0, 1 / SS)} for e in logs)
        else:
            draw_lockup(img, DURATION, final=True)
            text(img, DISCLAIMER, (W / 2, DISC_Y), 36, MUTED, False, "mm", da)
    else:
        draw_lockup(img, t)


def scene_end(img, t):
    lay, logs = end_layer()
    s = lerp(1.0, 1.03, ease_in_out_cubic(prog(t, *CUE["push"])))
    cx, cy = W / 2 * SS, H / 2 * SS
    Wc, Hc = W * SS, H * SS
    box = (cx - cx / s, cy - cy / s, cx + (Wc - cx) / s, cy + (Hc - cy) / s)
    img.alpha_composite(lay.resize((Wc, Hc), Image.Resampling.BICUBIC, box=box))
    ox, oy = W / 2 * (1 - s), H / 2 * (1 - s)
    TEXT_LOG.extend({**e, "M": (ox, oy, s / SS)} for e in logs)


SCENES = {
    "noise": scene_noise,
    "reveal": scene_reveal,
    "timer": scene_timer,
    "tasks": scene_tasks,
    "quiet": scene_quiet,
    "streak": scene_streak,
    "word": scene_word,
    "payoff": scene_payoff,
    "end": scene_end,
}

# frame-blended windows (pitfall 15: the card collapse and the 1 to 34 zoom step at 30 fps)
PROOF_EXTRA = (12.45, 12.55)  # stills either side of the 12.5 s match cut (review R701)

BLEND = [
    ((CUE["collapse"][0], CUE["suck_end"] + 1 / FPS), 8),
    ((CUE["zoom"][0], CUE["zoom"][0] + CUE["zoom"][1] + 1 / FPS), 16),
]


def _draw(t):
    TEXT_LOG.clear()
    name, _, _ = scene_at(t, SCHEDULE)
    img = background(t, name)
    SCENES[name](img, t)
    draw_caps(img, t)
    return E.finish(img)


def draw(t):
    for (a, b), n in BLEND:
        if a <= t < b:
            acc = None
            for j in range(n):
                fr = np.asarray(
                    _draw(t + ((j + 0.5) / n - 0.5) / FPS), dtype=np.float32
                )
                acc = fr if acc is None else acc + fr
            return Image.fromarray(np.round(acc / n).astype(np.uint8), "RGB")
    return _draw(t)


# ---------- reading holds for gate 4 (from the numbers above, not from frames) ----------
def holds():
    out = []
    for s, t_in, t_out, _ in CAPS:
        full = t_in if t_in == 0 else t_in + CAP_IN
        out.append((f'caption "{s}"', len(s.split()), full, t_out - CAP_OUT))
    tag_full = CUE["lk_tag"][0] + CUE["lk_tag"][1]
    out += [
        ('task card "Write the proposal" (noise)', 4, 0.0, CUE["collapse"][0]),
        (
            'wordmark "nook" (reveal)',
            1,
            CUE["word"][0] + CUE["word"][1],
            CUE["zoom"][0],
        ),
        ('timer label "Focus"', 1, T(6) + 0.55, CUE["count"][1]),
        ('timer label "Break"', 1, CUE["count"][1], CUE["timer_out"][0]),
        ('chips "25" "30"', 1, CUE["chips_in"] + 0.43, CUE["timer_out"][0]),
        (
            'panel header "Today"',
            1,
            CUE["panel_in"][0] + CUE["panel_in"][1],
            CUE["tasks_out"][0],
        ),
        (
            'tag "Carried over" (second row)',
            2,
            CUE["tags"] + 0.1 + 0.25,
            CUE["tasks_out"][0],
        ),
        (
            'row "Add a task"',
            3,
            CUE["panel_in"][0] + CUE["panel_in"][1],
            CUE["tasks_out"][0],
        ),
        (
            'toggle label "Quiet mode"',
            2,
            CUE["toggle_in"][0] + CUE["toggle_in"][1],
            CUE["quiet_out"][0],
        ),
        (
            'session label "Focus session"',
            2,
            CUE["wipe_dark"][0] + 1.0,
            CUE["quiet_out"][0],
        ),
        ('label "day streak"', 2, T(15) + 0.5, CUE["streak_out"][0]),
        (
            "dictionary line",
            len(DICT_TEXT.split()),
            CUE["type_t"][-1],
            CUE["word_out"][0],
        ),
        (
            'wordmark "nook" (end card)',
            1,
            CUE["lk_word"][0] + CUE["lk_word"][1],
            DURATION,
        ),
        (f'tagline "{TAGLINE}" (end card)', len(TAGLINE.split()), tag_full, DURATION),
        *[
            (f'pill "{p}"', len(p.split()), CUE["pills"][i] + 0.3, DURATION)
            for i, p in enumerate(PILLS)
        ],
        (
            f'line "{DISCLAIMER}"',
            len(DISCLAIMER.split()),
            CUE["disclaimer"][0] + CUE["disclaimer"][1],
            DURATION,
        ),
    ]
    return out
