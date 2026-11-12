# scenes.py : "The derivative, explained" (S-g17-manim-derivative). draw(t) is pure: same t -> same pixels.
# All timing comes from one 66 BPM grid: SCHEDULE (scenes) and the cue times below are beat numbers through bt().
import math

from PIL import Image, ImageDraw

import engine as E
from engine import (
    clamp,
    lerp,
    prog,
    ease_out_cubic,
    ease_in_cubic,
    ease_in_out_cubic,
    ease_out_back,
)
import kit as K
from kit import (
    BG,
    INK,
    MUTED,
    GRID,
    BLUE,
    CORAL,
    GOLD,
    GREEN,
    PANEL,
    T,
    Gap,
    Frac,
    Lim,
    Axes,
)

BPM = 66


def bt(n):  # time of beat n (0-based) on the 66 BPM grid
    return n * 60.0 / BPM


SCHEDULE = {  # scene -> (start, end) in seconds, every boundary on a beat
    "hook": (bt(0), bt(7)),  # 0.000 - 6.364
    "question": (bt(7), bt(11)),  # 6.364 - 10.000
    "average": (bt(11), bt(21)),  # 10.000 - 19.091
    "shrink": (bt(21), bt(34)),  # 19.091 - 30.909
    "definition": (bt(34), bt(44)),  # 30.909 - 40.000
    "example": (bt(44), bt(55)),  # 40.000 - 50.000
    "think": (bt(55), bt(60)),  # 50.000 - 54.545
    "close": (bt(60), bt(66)),  # 54.545 - 60.000
}
DURATION = bt(66)  # 60.0
CAP_FADE, TITLE_FADE, END_FADE, XF = 0.1, 0.2, 0.3, 0.3

CAPS = [  # caption strip: (start, end, exact text)
    (bt(0), bt(2), "60 km/h."),
    (bt(2), bt(7), "In one frozen instant, the car moves 0 km in 0 h."),
    (bt(7), bt(9.5), "So what is 60 measuring?"),
    (bt(11) + XF, bt(21), "Average speed: rise over run."),  # after the title dissolve
    (bt(21), bt(29), "Shrink the gap."),
    (bt(29), bt(34), "The slope settles on one number."),
    (bt(34), bt(44), "That number is the derivative."),
    (bt(44), bt(55), "For x squared, the slope at x is 2x."),
    (bt(55), bt(58), "Where is the slope exactly zero?"),
    (bt(58), bt(60), "At x = 0."),
    (bt(60), bt(63), "Position. Velocity. Acceleration."),
]
TITLE = (bt(9.5), bt(11), "The derivative")  # half-beat cue inside the question scene
END = (bt(63), bt(66), "The derivative:", " how fast, right now.")
XFADE_IN = {
    "average",
    "definition",
    "example",
    "think",
    "close",
}  # dissolve from the previous scene's last frame

# cues shared with the music build (music.py reads these)
SHRINK = (bt(22), bt(30))  # h eases from 1 to 0.001
GOLD_AT = bt(30)  # secant turns into the gold tangent
POINTS_AT = (bt(13), bt(14))  # the two points land (soft ticks)
TANGENT_A = (1, 2, -1)  # worked-example tangents
DROP_AT = tuple(bt(50.5 + i) for i in range(3))  # green points land (one bell each)
RING = (bt(55), bt(55) + 2.4)  # think ring fills for 2.4 s
ANSWER_AT = bt(58)
CUES = dict(
    bell=[bt(0), TITLE[0]],
    ticks=list(POINTS_AT),
    rise=[bt(n) for n in range(22, 30)],
    warm=GOLD_AT,
    drops=list(DROP_AT),
    pause=(bt(55), ANSWER_AT),
    answer=ANSWER_AT,
    final=END[0],
)


# ---------- the maths: every number on screen comes from here ----------
def f(x):
    return x * x


BINOM = [math.comb(2, k) for k in range(3)]  # (x + h)^2 = x^2 + 2xh + h^2
C1 = BINOM[1]  # f'(x) = C1 * x
for _a in TANGENT_A:  # the algebra and the numbers agree
    assert abs(K.deriv(f, _a) - C1 * _a) < 1e-6


def h_at(t):
    k = ease_in_out_cubic(prog(t, SHRINK[0], SHRINK[1] - SHRINK[0]))
    return lerp(1.0, 0.001, k)  # h eases from 1 to 0.001 with ease_in_out_cubic


def zero_of_slope():
    lo, hi = -2.0, 2.0  # bisection on f'(x) from f itself
    for _ in range(60):
        mid = (lo + hi) / 2
        if K.deriv(f, lo) * K.deriv(f, mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


X0 = zero_of_slope()


def vel(t):
    return K.deriv(f, t)


def acc(t):
    return K.deriv(vel, t, 1e-3)


def ein(t, t0, d=0.35):
    return ease_out_cubic(prog(t, t0, d))


def centered_row(img, d, items, size, cx, base, **kw):
    w = K.row_m(items, size)[0]
    return K.math_row(img, d, items, size, cx - w / 2, base, **kw)


# ---------- scene 1 and 2: speedometer and frozen car ----------
SPEED, VMAX = 60, 120
FROZEN_DT = 0.0  # a frozen instant: no time passes, so no distance either
DC, DR = (600, 440), 280


def dial_pt(v, r):
    a = math.radians(210 - 240 * v / VMAX)
    return DC[0] + r * math.cos(a), DC[1] - r * math.sin(a)


def draw_hook(img, d, t, dim, focus):
    cx, cy = DC
    s = E.SS
    d.ellipse(
        (
            s * (cx - DR - 10),
            s * (cy - DR - 10),
            s * (cx + DR + 10),
            s * (cy + DR + 10),
        ),
        fill=K.rgba(GRID, 0.9 * dim),
    )
    box = (s * (cx - DR), s * (cy - DR), s * (cx + DR), s * (cy + DR))
    d.pieslice(
        box, 150, 150 + 240 * SPEED / VMAX, fill=K.rgba(GOLD, 0.10 * focus)
    )  # swept reading
    d.arc(box, 150, 390, fill=K.rgba(MUTED, dim), width=int(6 * s))
    d.arc(
        box, 150, 150 + 240 * SPEED / VMAX, fill=K.rgba(GOLD, focus), width=int(10 * s)
    )
    for v in range(0, VMAX + 1, 10):
        major = v % 20 == 0
        K.line(
            d,
            [dial_pt(v, DR - (34 if major else 18)), dial_pt(v, DR - 4)],
            INK if major else MUTED,
            4 if major else 3,
            dim,
        )
        if major:
            x, y = dial_pt(v, DR + 42)
            K.text(img, str(v), x, y, "ui", 36, INK, dim, anchor="mm", group=f"dial{v}")
    tip, ang = dial_pt(SPEED, DR - 50), math.radians(210 - 240 * SPEED / VMAX)
    px, py = math.sin(ang) * 9, math.cos(ang) * 9
    tail = (cx - math.cos(ang) * 30, cy + math.sin(ang) * 30)
    d.polygon(
        [
            (s * tip[0], s * tip[1]),
            (s * (cx + px), s * (cy + py)),
            (s * tail[0], s * tail[1]),
            (s * (cx - px), s * (cy - py)),
        ],
        fill=K.rgba(GOLD, focus),
    )
    K.dot(d, cx, cy, 17, INK, focus)
    K.dot(d, cx, cy, 6, BG, focus)
    K.text(
        img,
        str(SPEED),
        cx,
        612,
        "uib",
        110,
        GOLD,
        focus,
        anchor="ms",
        group="readout60",
    )
    K.text(img, "km/h", cx, 664, "ui", 38, INK, focus, anchor="ms", group="kmh")
    # road and car (a generic silhouette, frozen)
    d.rectangle((s * 1000, s * 652, s * 1840, s * 712), fill=K.rgba(GRID, dim))
    for x in range(1010, 1830, 70):
        K.line(d, [(x, 682), (x + 36, 682)], MUTED, 4, dim)
    for x0, x1, y in ((1080, 1200, 520), (1110, 1210, 560), (1060, 1190, 600)):
        K.line(d, [(x0, y), (x1, y)], MUTED, 4, 0.6 * dim)
    car = K.rgba(INK, 0.92 * dim)
    d.rounded_rectangle((s * 1230, s * 545, s * 1610, s * 622), int(26 * s), fill=car)
    d.polygon(
        [
            (s * x, s * y)
            for x, y in ((1290, 548), (1360, 478), (1505, 478), (1565, 548))
        ],
        fill=car,
    )
    for poly in (
        ((1312, 540), (1370, 490), (1428, 490), (1428, 540)),
        ((1440, 540), (1440, 490), (1498, 490), (1545, 540)),
    ):
        d.polygon([(s * x, s * y) for x, y in poly], fill=K.rgba(BG, dim))
    for wx in (1320, 1520):
        K.dot(d, wx, 622, 36, BG, dim, outline=INK, ow=10)
        K.dot(d, wx, 622, 8, MUTED, dim)
    pulse = (
        0.5 + 0.25 * math.sin(2 * math.pi * t / bt(2))
    ) * dim  # frozen-frame brackets breathe
    l, tp, r, b, L = 1180, 430, 1660, 736, 40
    for x, y, dx, dy in ((l, tp, 1, 1), (r, tp, -1, 1), (l, b, 1, -1), (r, b, -1, -1)):
        K.line(d, [(x + dx * L, y), (x, y), (x, y + dy * L)], INK, 4, pulse)
    a = ein(t, bt(2), 0.3) * dim
    K.text(img, f"distance = {K.fmt_trim(f(P0 + FROZEN_DT) - f(P0))} km", 1200, 352, "uib", 40, CORAL, a, group="dist")
    K.text(img, f"time = {K.fmt_trim(FROZEN_DT)} h", 1200, 408, "uib", 40, BLUE, a, group="time")


def scene_hook(img, d, t):
    draw_hook(img, d, t, 1.0, 1.0)


def scene_question(img, d, t):
    k1 = ease_in_out_cubic(prog(t, bt(7), 0.5))
    k2 = ease_in_out_cubic(
        prog(t, TITLE[0], 0.25)
    )  # dial and car leave fully under the title
    if k2 < 1:
        draw_hook(img, d, t, lerp(lerp(1.0, 0.3, k1), 0.0, k2), lerp(1.0, 0.0, k2))
    e = ease_out_cubic(prog(t, TITLE[0], TITLE_FADE))
    K.text(
        img,
        TITLE[2],
        960,
        500 + 18 * (1 - e),
        "rm",
        124,
        INK,
        e,
        anchor="mm",
        group="title",
    )
    r = ease_out_cubic(prog(t, TITLE[0] + 0.1, 0.4))
    K.line(d, [(960 - 220 * r, 590), (960 + 220 * r, 590)], MUTED, 3, e)


# ---------- scenes 3 and 4: distance-time graph, secant to tangent ----------
AX1 = Axes((200, 110, 1080, 840), (0, 2.6), (0, 7))
P0 = 1.0  # the fixed point t = 1


def graph_base(img, d, t, curve_k):
    AX1.grid(d, [0.5 * i for i in range(1, 6)], range(1, 8))
    AX1.axes(d)
    for v in (1, 2):
        x, y = AX1.px(v, 0)
        K.text(img, str(v), x, y + 12, "ui", 34, MUTED, anchor="mt", group=f"tx{v}")
    for v in (2, 4, 6):
        x, y = AX1.px(0, v)
        K.text(img, str(v), x - 14, y, "ui", 34, MUTED, anchor="rm", group=f"ty{v}")
    K.text(img, "t (h)", 1094, 840, "ui", 36, MUTED, anchor="lm", group="tlabel")
    K.text(img, "distance (km)", 200, 92, "ui", 36, MUTED, group="dlabel")
    AX1.curve(d, f, 0, 2.6, BLUE, 5, curve_k, record="f")
    lx, ly = AX1.px(1.35, 6.0)
    K.math_row(
        img,
        d,
        [
            T("f", "it", BLUE),
            T("(", "rm", BLUE),
            T("t", "it", BLUE),
            T(")", "rm", BLUE),
            Gap(0.25),
            T("=", "rm", BLUE),
            Gap(0.25),
            T("t", "it", BLUE),
            T("²", "rm", BLUE),
        ],
        46,
        lx,
        ly,
        group="flabel",
    )


def secant(d, h, k_line, a_line, col=CORAL, span=(0.25, 2.55)):
    m = (f(P0 + h) - f(P0)) / h
    mid = P0 + h / 2
    ta, tb = mid - k_line * (mid - span[0]), mid + k_line * (span[1] - mid)
    AX1.seg(d, (ta, f(P0) + m * (ta - P0)), (tb, f(P0) + m * (tb - P0)), col, 5, a_line)
    return m


def legs(img, d, h, k_run, k_rise, a=1.0):
    x0, y0 = AX1.px(P0, f(P0))
    x1, _ = AX1.px(P0 + h, f(P0))
    _, y1 = AX1.px(P0 + h, f(P0 + h))
    K.line(d, [(x0, y0), (lerp(x0, x1, k_run), y0)], BLUE, 5, a * (k_run > 0))
    K.line(d, [(x1, y0), (x1, lerp(y0, y1, k_rise))], CORAL, 5, a * (k_rise > 0))
    return (x0, y0, x1, y1)


def scene_average(img, d, t):
    graph_base(img, d, t, ease_in_out_cubic(prog(t, bt(11), bt(12) - bt(11))))
    h = 1.0
    secant(d, h, ease_out_cubic(prog(t, bt(15), 0.6)), 1.0 if t >= bt(15) else 0.0)
    k_run, k_rise = (
        ease_out_cubic(prog(t, bt(16), 0.35)),
        ease_out_cubic(prog(t, bt(16.5), 0.35)),
    )
    x0, y0, x1, y1 = legs(img, d, h, k_run, k_rise)
    run, rise = (P0 + h) - P0, f(P0 + h) - f(P0)
    K.text(
        img,
        f"run = {K.fmt_trim(run)}",
        (x0 + x1) / 2,
        y0 + 16,
        "uib",
        36,
        BLUE,
        ein(t, bt(16)),
        anchor="mt",
        group="runlabel",
    )
    K.text(
        img,
        f"rise = {K.fmt_trim(rise)}",
        x1 + 20,
        (y0 + y1) / 2,
        "uib",
        36,
        CORAL,
        ein(t, bt(16.5)),
        anchor="lm",
        group="riselabel",
    )
    for tp, at in ((P0, POINTS_AT[0]), (P0 + h, POINTS_AT[1])):
        s = ease_out_back(prog(t, at, 0.3))
        x, y = AX1.px(tp, f(tp))
        K.dot(d, x, y, 11 * max(0, s), INK)
    a = ein(t, bt(17))
    K.text(img, "average speed", 1170, 300, "uib", 42, INK, a, group="avg_head")
    avg = rise / run
    K.math_row(
        img,
        d,
        [
            Frac(
                [T("rise", "rm", CORAL, "r")],
                [T("run", "rm", BLUE, "r")],
                key="r",
                bar=INK,
            ),
            Gap(0.25),
            T("=", "rm", INK, "r"),
            Gap(0.25),
            Frac(
                [T(K.fmt_trim(rise), "rm", CORAL, "r")],
                [T(K.fmt_trim(run), "rm", BLUE, "r")],
                key="r",
            ),
            Gap(0.25),
            T("=", "rm", INK, "r"),
            Gap(0.25),
            T(K.fmt_trim(avg), "rm", CORAL, "r"),
        ],
        60,
        1170,
        440,
        alpha={"r": a},
        group="avg_row",
    )
    K.text(
        img,
        f"{K.fmt_trim(avg)} km/h on average",
        1170,
        560,
        "ui",
        38,
        MUTED,
        a,
        group="avg_note",
    )


def scene_shrink(img, d, t):
    graph_base(img, d, t, 1.0)
    h = h_at(t)
    g = ease_in_out_cubic(prog(t, GOLD_AT, 0.5))
    m = secant(d, h, 1.0, 1.0 - g, span=(0.25, 2.2))
    x0, y0, x1, y1 = legs(img, d, h, 1.0, 1.0, 1.0 - g)
    K.text(
        img,
        "h",
        (x0 + x1) / 2,
        y0 + 14,
        "it",
        40,
        BLUE,
        clamp((h - 0.12) / 0.25) * (1 - g),
        anchor="mt",
        group="hlabel",
    )
    s_tan = K.deriv(f, P0)
    AX1.seg(
        d,
        (0.25, f(P0) + s_tan * (0.25 - P0)),
        (2.2, f(P0) + s_tan * (2.2 - P0)),
        GOLD,
        6,
        g,
    )
    xq, yq = AX1.px(P0 + h, f(P0 + h))
    K.dot(d, xq, yq, 11, INK, 1 - g)
    xp, yp = AX1.px(P0, f(P0))
    K.dot(d, xp, yp, 11, INK)
    K.dot(d, xp, yp, 11, GOLD, g)
    a_in = ein(t, bt(21) + 0.1, 0.3)
    go = ease_in_cubic(prog(t, GOLD_AT, 0.2))  # old readouts leave first
    gi = ease_out_cubic(prog(t, GOLD_AT + 0.2, 0.3))  # then the limit readouts arrive
    K.math_row(
        img,
        d,
        [
            T("h", "it", BLUE),
            Gap(0.25),
            T("=", "rm", INK),
            Gap(0.25),
            T(K.fmt(h, 3), "rm", BLUE),
        ],
        64,
        1170,
        330,
        alpha={None: a_in * (1 - go)},
        group="h_row",
    )
    K.math_row(  # at the gold moment: the limit, not the last sample
        img,
        d,
        [
            T("h", "it", BLUE, "l"),
            Gap(0.25),
            T("→", "rm", INK, "l"),
            Gap(0.25),
            T("0", "rm", BLUE, "l"),
        ],
        64,
        1170,
        330,
        alpha={"l": gi},
        group="h_limit",
    )
    sec = [
        T("slope", "rm", CORAL, "s"),
        Gap(0.25),
        T("=", "rm", INK, "s"),
        Gap(0.25),
        T(K.fmt(m, 3), "rm", CORAL, "s"),
    ]
    K.math_row(
        img, d, sec, 64, 1170, 450, alpha={"s": a_in * (1 - go)}, group="slope_row"
    )
    tan = [
        T("slope", "rm", GOLD, "g"),
        Gap(0.25),
        T("=", "rm", GOLD, "g"),
        Gap(0.25),
        T(K.fmt_trim(s_tan), "rm", GOLD, "g"),
    ]
    K.math_row(img, d, tan, 64, 1170, 450, alpha={"g": gi}, group="tan_row")
    K.text(
        img,
        f"secant through t = {K.fmt_trim(P0)} and t = {K.fmt_trim(P0)} + h",
        1170,
        530,
        "ui",
        36,
        MUTED,
        a_in * (1 - go),
        group="sec_note",
    )
    K.text(img, f"tangent at t = {K.fmt_trim(P0)}", 1170, 530, "ui", 36, GOLD, gi, group="tan_note")


# ---------- scene 5: the definition ----------
AX2 = Axes((1240, 230, 1760, 690), (-0.2, 2.1), (-0.3, 4.2))


def scene_definition(img, d, t):
    def c(s, st, col, key):
        return T(s, st, col, key)

    num = [
        c("f", "it", CORAL, "num"),
        c("(", "rm", CORAL, "num"),
        c("x", "it", CORAL, "num"),
        c(" + ", "rm", CORAL, "num"),
        c("h", "it", CORAL, "num"),
        c(")", "rm", CORAL, "num"),
        c(" − ", "rm", CORAL, "num"),
        c("f", "it", CORAL, "num"),
        c("(", "rm", CORAL, "num"),
        c("x", "it", CORAL, "num"),
        c(")", "rm", CORAL, "num"),
    ]
    items = [
        c("f", "it", INK, "lhs"),
        c("′", "rm", INK, "lhs"),
        c("(", "rm", INK, "lhs"),
        c("x", "it", INK, "lhs"),
        c(")", "rm", INK, "lhs"),
        Gap(0.28),
        c("=", "rm", INK, "lhs"),
        Gap(0.28),
        Lim([T("h", "it", BLUE), T(" → 0", "rm", INK)], key="lim"),
        Gap(0.22),
        Frac(num, [c("h", "it", BLUE, "den")], den_key="den"),
    ]
    al = {
        "lhs": 1.0,
        "lim": ein(t, bt(35)),
        "num": ein(t, bt(36)),
        "den": ein(t, bt(37)),
    }
    bx = K.math_row(img, d, items, 84, 120, 500, alpha=al, group="definition")
    a_lab = ein(t, bt(38))
    nl, nt, nr, nb = bx["num"]
    K.line(
        d, [(nl, nt - 14), (nl, nt - 24), (nr, nt - 24), (nr, nt - 14)], CORAL, 3, a_lab
    )
    K.text(
        img,
        "rise",
        (nl + nr) / 2,
        nt - 36,
        "uib",
        38,
        CORAL,
        a_lab,
        anchor="ms",
        group="rise_tag",
    )
    dl, dt_, dr, db = bx["den"]
    K.text(
        img,
        "run",
        (dl + dr) / 2,
        db + 18,
        "uib",
        38,
        BLUE,
        a_lab,
        anchor="mt",
        group="run_tag",
    )
    # mini graph: the same picture the formula describes
    AX2.grid(d, [0.5, 1.0, 1.5, 2.0], [1, 2, 3, 4])
    AX2.axes(d)
    AX2.curve(
        d,
        f,
        -0.2,
        2.1,
        BLUE,
        5,
        ease_in_out_cubic(prog(t, bt(34), 0.9)),
        record="f_mini",
    )
    xa = 0.8
    hm = 0.6 + 0.3 * math.cos(2 * math.pi * max(0.0, t - bt(38)) / bt(8))
    m = (f(xa + hm) - f(xa)) / hm
    AX2.seg(
        d,
        (xa - 0.5, f(xa) - 0.5 * m),
        (xa + hm + 0.3, f(xa) + m * (hm + 0.3)),
        CORAL,
        4,
        a_lab,
    )
    x0, y0 = AX2.px(xa, f(xa))
    x1, y1 = AX2.px(xa + hm, f(xa + hm))
    K.line(d, [(x0, y0), (x1, y0)], BLUE, 5, a_lab)
    K.line(d, [(x1, y0), (x1, y1)], CORAL, 5, a_lab)
    K.dot(d, x0, y0, 9, INK, a_lab)
    K.dot(d, x1, y1, 9, INK, a_lab)
    K.text(
        img,
        "h",
        (x0 + x1) / 2,
        y0 + 12,
        "it",
        38,
        BLUE,
        a_lab,
        anchor="mt",
        group="mini_h",
    )
    K.text(
        img,
        "rise",
        x1 + 16,
        (y0 + y1) / 2,
        "uib",
        36,
        CORAL,
        a_lab,
        anchor="lm",
        group="mini_rise",
    )
    K.text(
        img,
        "x",
        AX2.px(2.1, 0)[0],
        AX2.px(2.1, 0)[1] - 14,
        "it",
        36,
        MUTED,
        anchor="rs",
        group="mini_x",
    )


# ---------- scene 6: worked example and the check on the graph ----------
AX3 = Axes((1060, 200, 1800, 860), (-2.6, 2.6), (-5.5, 7))
ALG = 46


def sq(key, col, s="x"):
    return [T(s, "it", col, key), T("²", "rm", col, key)]


def scene_example(img, d, t):
    x0 = 110
    al = {"L1": 1.0}
    for k, n in (("L2", 45), ("L3", 46), ("L4", 47.5), ("L5", 48), ("L6", 49)):
        al[k] = ein(t, bt(n))
    cut = ein(t, bt(47), 0.4)
    al["c1"] = al["c2"] = al["L3"] * (1 - 0.55 * cut)
    al["_strike"] = cut
    one = "" if BINOM[0] == 1 else str(BINOM[0])
    L1 = [
        T("f", "it", BLUE, "L1"),
        T("(", "rm", BLUE, "L1"),
        T("x", "it", BLUE, "L1"),
        T(")", "rm", BLUE, "L1"),
        Gap(0.25),
        T("=", "rm", BLUE, "L1"),
        Gap(0.25),
    ] + sq("L1", BLUE)
    K.math_row(img, d, L1, ALG, x0, 160, alpha=al, group="L1")
    lhs = Frac(
        [
            T("f", "it", CORAL, "L2"),
            T("(", "rm", CORAL, "L2"),
            T("x", "it", CORAL, "L2"),
            T(" + ", "rm", CORAL, "L2"),
            T("h", "it", CORAL, "L2"),
            T(")", "rm", CORAL, "L2"),
            T(" − ", "rm", CORAL, "L2"),
            T("f", "it", CORAL, "L2"),
            T("(", "rm", CORAL, "L2"),
            T("x", "it", CORAL, "L2"),
            T(")", "rm", CORAL, "L2"),
        ],
        [T("h", "it", BLUE, "L2")],
        key="L2",
    )
    x_eq = x0 + K.row_m([lhs, Gap(0.25)], ALG)[0]
    rhs2 = Frac(
        [
            T("(", "rm", CORAL, "L2"),
            T("x", "it", CORAL, "L2"),
            T(" + ", "rm", CORAL, "L2"),
            T("h", "it", CORAL, "L2"),
            T(")²", "rm", CORAL, "L2"),
            T(" − ", "rm", CORAL, "L2"),
        ]
        + sq("L2", CORAL),
        [T("h", "it", BLUE, "L2")],
        key="L2",
    )
    K.math_row(
        img,
        d,
        [lhs, Gap(0.25), T("=", "rm", INK, "L2"), Gap(0.25), rhs2],
        ALG,
        x0,
        300,
        alpha=al,
        group="L2",
    )
    n3 = (
        [T(one, "rm", CORAL, "c1")]
        + sq("c1", CORAL)
        + [
            T(f" + {BINOM[1]}", "rm", CORAL, "L3"),
            T("x", "it", CORAL, "L3"),
            T("h", "it", CORAL, "L3"),
            T(" + " + ("" if BINOM[2] == 1 else str(BINOM[2])), "rm", CORAL, "L3"),
        ]
        + sq("L3", CORAL, "h")
        + [T(" − ", "rm", CORAL, "c2")]
        + sq("c2", CORAL)
    )
    K.math_row(
        img,
        d,
        [
            T("=", "rm", INK, "L3"),
            Gap(0.25),
            Frac(n3, [T("h", "it", BLUE, "L3")], key="L3"),
        ],
        ALG,
        x_eq,
        440,
        alpha=al,
        group="L3",
        strike=("c1", "c2"),
    )
    n4 = [
        T(str(BINOM[1]), "rm", CORAL, "L4"),
        T("x", "it", CORAL, "L4"),
        T("h", "it", CORAL, "L4"),
        T(" + ", "rm", CORAL, "L4"),
    ] + sq("L4", CORAL, "h")
    K.math_row(
        img,
        d,
        [
            T("=", "rm", INK, "L4"),
            Gap(0.25),
            Frac(n4, [T("h", "it", BLUE, "L4")], key="L4"),
        ],
        ALG,
        x_eq,
        580,
        alpha=al,
        group="L4",
    )
    K.math_row(
        img,
        d,
        [
            T("=", "rm", INK, "L5"),
            Gap(0.25),
            T(str(BINOM[1]), "rm", INK, "L5"),
            T("x", "it", INK, "L5"),
            T(" + ", "rm", INK, "L5"),
            T("h", "it", BLUE, "L5"),
        ],
        ALG,
        x_eq,
        700,
        alpha=al,
        group="L5",
    )
    L6 = [
        T("f", "it", GREEN, "L6"),
        T("′", "rm", GREEN, "L6"),
        T("(", "rm", GREEN, "L6"),
        T("x", "it", GREEN, "L6"),
        T(")", "rm", GREEN, "L6"),
        Gap(0.25),
        T("=", "rm", GREEN, "L6"),
        Gap(0.25),
        T(str(C1), "rm", GREEN, "L6"),
        T("x", "it", GREEN, "L6"),
    ]
    b6 = K.math_row(img, d, L6, ALG + 6, x0 + 14, 806, alpha=al, group="L6")
    if "L6" in b6:
        l, tp, r, b = b6["L6"]
        d.rounded_rectangle(
            (E.SS * (l - 16), E.SS * (tp - 14), E.SS * (r + 16), E.SS * (b + 14)),
            int(12 * E.SS),
            outline=K.rgba(GREEN, al["L6"]),
            width=int(3 * E.SS),
        )
    for txt, key, y in (
        ("expand", "L3", 440),
        ("cancel", "L4", 580),
        ("divide", "L5", 700),
    ):
        K.text(
            img,
            txt,
            960,
            y,
            "ui",
            36,
            MUTED,
            al[key] if key != "L4" else cut,
            anchor="rs",
            group="note_" + txt,
        )
    K.math_row(
        img,
        d,
        [
            T("let ", "ui", MUTED, "n6"),
            T("h", "it", BLUE, "n6"),
            T(" → 0", "rm", MUTED, "n6"),
        ],
        36,
        960
        - K.row_m(
            [T("let ", "ui", MUTED), T("h", "it", BLUE), T(" → 0", "rm", MUTED)], 36
        )[0],
        806,
        alpha={"n6": al["L6"]},
        group="note_h0",
    )
    # graph: tangents drop the green points that trace f'(x)
    AX3.grid(d, [-2, -1, 1, 2], range(-5, 8))
    AX3.axes(d)
    for v in (-2, -1, 1, 2):
        x, y = AX3.px(v, 0)
        K.text(
            img,
            K.fmt_trim(v),
            x + 8,
            y + 8,
            "ui",
            34,
            MUTED,
            anchor="lt",
            group=f"ex_tx{v}",
        )
    for v in (-4, -2, 2, 4, 6):
        x, y = AX3.px(0, v)
        K.text(
            img,
            K.fmt_trim(v),
            x - 12,
            y,
            "ui",
            34,
            MUTED,
            anchor="rm",
            group=f"ex_ty{v}",
        )
    AX3.curve(
        d, f, -2.6, 2.6, BLUE, 5, ease_in_out_cubic(prog(t, bt(44), 0.9)), record="f_ex"
    )
    lx, ly = AX3.px(-2.0, 6.15)
    K.math_row(img, d, L1, 42, lx, ly, group="ex_flabel")
    K.text(
        img,
        "tangent slopes",
        1060,
        112,
        "ui",
        36,
        MUTED,
        ein(t, bt(50)),
        group="slopes_head",
    )
    cx = 1060.0
    for i, a in enumerate(TANGENT_A):
        s = K.deriv(f, a)
        on = bt(50 + i)
        e = ein(t, on, 0.3)
        off = ease_in_cubic(prog(t, bt(51 + i), 0.3)) if i < len(TANGENT_A) - 1 else 0.0
        w = 2.2 / math.sqrt(1 + s * s)
        AX3.seg(d, (a - w, f(a) - s * w), (a + w, f(a) + s * w), GOLD, 5, e * (1 - off))
        xa, ya = AX3.px(a, f(a))
        K.dot(d, xa, ya, 9, GOLD, e * (1 - off))
        kd = ease_in_out_cubic(prog(t, DROP_AT[i] - 0.4, 0.4))
        xg, yg = AX3.px(a, lerp(f(a), s, kd))
        K.dashed(d, (xa, ya), (xg, yg), MUTED, 3, 0.8 * e)
        K.dot(d, xg, yg, 11, GREEN, e)
        cell = [
            T("x", "it", INK, "c"),
            T(" = " + K.fmt_trim(a), "rm", INK, "c"),
            T(":  ", "rm", MUTED, "c"),
            T(K.fmt_trim(s), "rm", GOLD, "c"),
        ]
        K.math_row(img, d, cell, 44, cx, 170, alpha={"c": e}, group=f"cell{i}")
        cx += K.row_m(cell, 44)[0] + 56
    AX3.curve(
        d,
        lambda x: C1 * x,
        -2.6,
        2.6,
        GREEN,
        5,
        ease_in_out_cubic(prog(t, bt(53), bt(54) - bt(53))),
        record="fprime",
    )
    gx, gy = AX3.px(0.35, 6.15)
    K.math_row(img, d, L6, 42, gx, gy, alpha={"L6": ein(t, bt(53.5))}, group="ex_gl")


# ---------- scene 7: think pause ----------
AX4 = Axes((860, 170, 1760, 850), (-2.2, 2.2), (-1.2, 4.6))
RC, RR = (440, 470), 150


def scene_think(img, d, t):
    s = E.SS
    AX4.grid(d, [-2, -1, 1, 2], range(-1, 5))
    AX4.axes(d)
    AX4.curve(d, f, -2.2, 2.2, BLUE, 5, 1.0, record="f_think")
    p = clamp((t - RING[0]) / (RING[1] - RING[0]))
    box = (s * (RC[0] - RR), s * (RC[1] - RR), s * (RC[0] + RR), s * (RC[1] + RR))
    d.arc(box, 0, 360, fill=K.rgba(GRID), width=int(16 * s))
    if p > 0:
        d.arc(box, -90, -90 + 360 * p, fill=K.rgba(INK), width=int(16 * s))
    ans = ein(t, ANSWER_AT + 0.1, 0.25)
    q_out = ease_in_cubic(prog(t, ANSWER_AT - 0.15, 0.15))
    d.arc(box, 0, 360, fill=K.rgba(GOLD, ans), width=int(16 * s))
    K.text(img, "?", RC[0], RC[1], "rm", 180, INK, 1 - q_out, anchor="mm", group="qmark")
    centered_row(
        img,
        d,
        [
            T("x", "it", INK, "a"),
            T(" = ", "rm", INK, "a"),
            T(K.fmt_trim(X0), "rm", GOLD, "a"),
        ],
        84,
        RC[0],
        RC[1] + 28,
        alpha={"a": ans},
        group="x0",
    )
    AX4.seg(d, (X0 - 1.3, f(X0)), (X0 + 1.3, f(X0)), GOLD, 7, ans)
    vx, vy = AX4.px(X0, f(X0))
    K.dot(d, vx, vy, 11, GOLD, ans)
    lx, ly = AX4.px(X0 + 0.18, -0.72)
    K.math_row(
        img,
        d,
        [
            T("slope", "rm", GOLD, "a"),
            Gap(0.25),
            T("=", "rm", GOLD, "a"),
            Gap(0.25),
            T(K.fmt_trim(K.deriv(f, X0)), "rm", GOLD, "a"),
        ],
        46,
        lx,
        ly,
        alpha={"a": ans},
        group="slope0",
    )


# ---------- scene 8: position, velocity, acceleration, end card ----------
def scene_close(img, d, t):
    k = ease_in_out_cubic(prog(t, END[0], 0.6))
    up, dim = 40 * k, 1.0  # cards stay at full strength under the end card
    tc = lerp(
        0.3, 2.3, (t - bt(60)) / (bt(66) - bt(60))
    )  # one shared "right now" cursor
    graphs = (
        ("position", f, BLUE, (0, 6.5), [T("t", "it", BLUE)] + [T("²", "rm", BLUE)]),
        (
            "velocity",
            vel,
            GREEN,
            (0, 5.5),
            [T(K.fmt_trim(vel(1.0)), "rm", GREEN), T("t", "it", GREEN)],
        ),
        ("acceleration", acc, GREEN, (0, 3.5), [T(K.fmt_trim(acc(1.0)), "rm", GREEN)]),
    )
    for i, (name, fn, col, yr, lab) in enumerate(graphs):
        e = (1.0 if i == 0 else ein(t, bt(60 + i))) * dim
        l, r, tp, b = 150 + 600 * i, 590 + 600 * i, 230 - up, 530 - up
        d.rounded_rectangle(
            (E.SS * l, E.SS * tp, E.SS * r, E.SS * b),
            int(14 * E.SS),
            fill=K.rgba(GRID, e),
        )
        ax = Axes((l + 40, tp + 30, r - 30, b - 40), (0, 2.5), yr)
        ax.axes(d, e)
        ax.curve(d, fn, 0, 2.5, col, 5, 1.0, a=e, n=200, record=f"close_{name}")
        cxp, _ = ax.px(tc, 0)
        K.dashed(d, (cxp, tp + 30), (cxp, b - 40), MUTED, 2, 0.7 * e, dash=8, gap=7)
        K.dot(d, *ax.px(tc, fn(tc)), 8, col, e)
        K.text(img, name, l, tp - 18, "uib", 38, INK, e, group=f"name_{name}")
        for it in lab:
            it.key = "lab"
        K.math_row(
            img, d, lab, 44, l + 64, tp + 78, alpha={"lab": e}, group=f"lab_{name}"
        )
        if i:
            ya = (tp + b) / 2
            K.arrow(d, (l - 135, ya), (l - 25, ya), MUTED, 3, e)
            K.math_row(
                img,
                d,
                [
                    T("d", "it", INK, "dd"),
                    T("/", "rm", INK, "dd"),
                    T("d", "it", INK, "dd"),
                    T("t", "it", INK, "dd"),
                ],
                40,
                l - 80 - K.row_m([T("d/dt", "it")], 40)[0] / 2,
                ya - 16,
                alpha={"dd": e},
                group=f"ddt{i}",
            )
    e = ein(t, END[0], END_FADE)
    d.rounded_rectangle(  # band behind the end line
        (E.SS * 160, E.SS * 655, E.SS * 1760, E.SS * 805),
        int(20 * E.SS),
        fill=K.rgba(GRID, e),
    )
    centered_row(
        img,
        d,
        [T(END[2], "uib", GOLD, "e"), T(END[3], "uib", INK, "e")],
        66,
        960,
        745 + 20 * (1 - e),
        alpha={"e": e},
        group="endcard",
    )


SCENES = dict(
    hook=scene_hook,
    question=scene_question,
    average=scene_average,
    shrink=scene_shrink,
    definition=scene_definition,
    example=scene_example,
    think=scene_think,
    close=scene_close,
)


def scene_img(name, t):
    img = Image.new("RGB", (E.W * E.SS, E.H * E.SS), K.rgb(BG))
    SCENES[name](img, ImageDraw.Draw(img, "RGBA"), t)
    return img


def captions(img, t):
    """Caption strip, drawn as a separate pass over the finished scene."""
    for a, b, s in CAPS:
        if a <= t < b:
            al = 1.0 if a == 0 else ease_out_cubic(clamp((t - a) / CAP_FADE))
            w = K.text_w(s, "uib", 44)
            d = ImageDraw.Draw(img, "RGBA")
            d.rounded_rectangle(
                (
                    E.SS * (960 - w / 2 - 32),
                    E.SS * 928,
                    E.SS * (960 + w / 2 + 32),
                    E.SS * 1010,
                ),
                int(14 * E.SS),
                fill=K.rgba(PANEL, 0.92 * al),
            )
            K.text(img, s, 960, 969, "uib", 44, INK, al, anchor="mm", group="caption")


def draw(t):
    name, lt, k = E.scene_at(t, SCHEDULE)
    img = scene_img(name, t)
    a = SCHEDULE[name][0]
    if name in XFADE_IN and t - a < XF:
        prev = list(SCHEDULE)[list(SCHEDULE).index(name) - 1]
        img = Image.blend(
            scene_img(prev, a - 1e-4), img, ease_in_out_cubic(clamp((t - a) / XF))
        )
    captions(img, t)
    return E.finish(img)


# reading holds for gate 4: (text, fully drawn at, exit starts at)
HOLDS = (
    [(s, a + (0 if a == 0 else CAP_FADE), b) for a, b, s in CAPS]
    + [
        (TITLE[2], TITLE[0] + TITLE_FADE, TITLE[1]),
        (END[2] + END[3], END[0] + END_FADE, END[1]),
        ("distance = 0 km", bt(2) + 0.3, bt(9.5)),
        ("rise / run = 3 / 1 = 3", bt(17) + 0.35, bt(21)),
        ("run = 1", bt(16) + 0.35, bt(21)),
        ("rise = 3", bt(16.5) + 0.35, bt(21)),
        ("slope = 2", GOLD_AT + 0.5, bt(34)),
        ("h → 0", GOLD_AT + 0.5, bt(34)),
        ("rise", bt(38) + 0.35, bt(44)),
        ("run", bt(38) + 0.35, bt(44)),
        ("f'(x) = 2x", bt(49) + 0.35, bt(55)),
    ]
    + [(f"x = {a}: slope", bt(50 + i) + 0.3, bt(55)) for i, a in enumerate(TANGENT_A)]
    + [
        ("x = 0", ANSWER_AT + 0.35, bt(60)),
        ("slope = 0", ANSWER_AT + 0.35, bt(60)),
    ]
    + [
        (n, bt(60 + i) + (0 if i == 0 else 0.35), bt(66))
        for i, n in enumerate(("position", "velocity", "acceleration"))
    ]
)
