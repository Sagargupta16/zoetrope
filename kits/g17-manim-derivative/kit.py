# kit.py : drawing kit for this video (palette, fonts, a tiny math typesetter, axes). Pure helpers, no state across frames.
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import engine as E

# palette (style card S-g17 + scenario 2); one colour per role in every scene
BG = "#0D1117"
INK = "#E8ECF3"
MUTED = "#7D8597"
GRID = "#2A3140"
BLUE = "#58C4DD"  # the function and the run
CORAL = "#FF7A59"  # secant and rise
GOLD = "#FFD166"  # tangent, the derivative moment
GREEN = "#7EE081"  # the derivative graph
PANEL = "#161C26"  # caption strip panel (darkened grid tone)

FONTS = {  # style card font -> installed Windows font
    "rm": ("C:/Windows/Fonts/cambria.ttc", 0),  # STIX Two Text -> Cambria
    "it": (
        "C:/Windows/Fonts/cambriai.ttf",
        0,
    ),  # STIX Two Text Italic -> Cambria Italic
    "math": ("C:/Windows/Fonts/cambria.ttc", 1),  # symbols -> Cambria Math
    "ui": ("C:/Windows/Fonts/segoeui.ttf", 0),  # Avenir Next -> Segoe UI
    "uib": ("C:/Windows/Fonts/seguisb.ttf", 0),  # Avenir Next Demi -> Segoe UI Semibold
}
_fc = {}

REC_MIN = 0.5  # QA only: log runs drawn above this alpha (hold frames 0.5; transition sweeps lower)
RECORD = False  # QA only: when True, every text run and readout box is logged; pixels never depend on it
LOG = []


def font(style, size, ss=True):
    """Font at output size (ss=True: scaled by E.SS for drawing). A missing font raises; never the Pillow default."""
    s = int(round(size * (E.SS if ss else 1)))
    key = (style, s)
    if key not in _fc:
        path, idx = FONTS[style]
        if not os.path.exists(path):
            raise FileNotFoundError(f"font for '{style}' missing: {path}")
        _fc[key] = ImageFont.truetype(path, s, index=idx)
    return _fc[key]


def rgba(c, a=1.0):
    h = c.lstrip("#")
    return (
        int(h[0:2], 16),
        int(h[2:4], 16),
        int(h[4:6], 16),
        int(255 * max(0.0, min(1.0, a))),
    )


def rgb(c):
    return rgba(c)[:3]


# ---------- numbers: always computed, never "-0.00" ----------
def fmt(v, d=3):
    r = round(float(v), d)
    if r == 0:
        r = 0.0  # kills -0.0
    return f"{r:.{d}f}".replace("-", "\u2212")


def fmt_trim(v, d=3):
    s = fmt(v, d)
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("\u22120", "") else s


def deriv(fn, a, h=1e-5):
    """Slope of fn at a from fn itself (central difference)."""
    return (fn(a + h) - fn(a - h)) / (2 * h)


# ---------- drawing primitives (coordinates in output px) ----------
def S(v):
    return v * E.SS


def text(img, s, x, y, style, size, col, a=1.0, anchor="ls", group=None):
    """Text with real alpha (pasted through a mask). Returns its box in output px."""
    if not s:
        return None
    f = font(style, size)
    l, t, r, b = f.getbbox(s, anchor=anchor)
    if a <= 0.003:  # invisible: nothing drawn, but the box still places labels
        return (
            (S(x) + l) / E.SS,
            (S(y) + t) / E.SS,
            (S(x) + r) / E.SS,
            (S(y) + b) / E.SS,
        )
    m = Image.new("L", (r - l + 4, b - t + 4), 0)
    ImageDraw.Draw(m).text(
        (-l + 2, -t + 2), s, font=f, fill=int(255 * min(1, a)), anchor=anchor
    )
    ox, oy = int(round(S(x))) + l - 2, int(round(S(y))) + t - 2
    img.paste(rgb(col), (ox, oy), m)
    box = ((S(x) + l) / E.SS, (S(y) + t) / E.SS, (S(x) + r) / E.SS, (S(y) + b) / E.SS)
    if RECORD and a > REC_MIN:
        f1 = font(style, size, ss=False)
        LOG.append(
            dict(
                kind="text",
                s=s,
                style=style,
                size=size,
                col=col,
                x=x,
                y=y,
                anchor=anchor,
                font=f1,
                box=box,
                group=group or s,
            )
        )
    return box


def text_w(s, style, size):
    return font(style, size).getlength(s) / E.SS


def line(d, pts, col, w, a=1.0):
    if a <= 0.003 or len(pts) < 2:
        return
    ww = max(1, int(round(S(w))))
    sp = [(S(x), S(y)) for x, y in pts]
    if a >= 0.999:
        d.line(sp, fill=rgba(col), width=ww, joint="curve")
        return
    # translucent polyline: draw once into a mask so joints do not double up into beads
    img = d._image
    pad = ww + 2
    x0 = max(0, int(min(p[0] for p in sp)) - pad)
    y0 = max(0, int(min(p[1] for p in sp)) - pad)
    x1 = min(img.size[0], int(max(p[0] for p in sp)) + pad)
    y1 = min(img.size[1], int(max(p[1] for p in sp)) + pad)
    if x1 <= x0 or y1 <= y0:
        return
    m = Image.new("L", (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(m).line(
        [(x - x0, y - y0) for x, y in sp], fill=int(255 * a), width=ww, joint="curve"
    )
    img.paste(rgb(col), (x0, y0), m)


def dot(d, x, y, r, col, a=1.0, outline=None, ow=0):
    if a <= 0.003 or r <= 0:
        return
    d.ellipse(
        (S(x - r), S(y - r), S(x + r), S(y + r)),
        fill=rgba(col, a),
        outline=rgba(outline, a) if outline else None,
        width=int(S(ow)),
    )


def dashed(d, p0, p1, col, w, a=1.0, dash=12, gap=9):
    (x0, y0), (x1, y1) = p0, p1
    L = math.hypot(x1 - x0, y1 - y0)
    if L < 1:
        return
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    s = 0.0
    while s < L:
        e = min(L, s + dash)
        line(d, [(x0 + ux * s, y0 + uy * s), (x0 + ux * e, y0 + uy * e)], col, w, a)
        s = e + gap


def arrow(d, p0, p1, col, w, a=1.0, head=16):
    line(d, [p0, p1], col, w, a)
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    pts = [
        p1,
        (p1[0] - head * math.cos(ang - 0.45), p1[1] - head * math.sin(ang - 0.45)),
        (p1[0] - head * math.cos(ang + 0.45), p1[1] - head * math.sin(ang + 0.45)),
    ]
    d.polygon([(S(x), S(y)) for x, y in pts], fill=rgba(col, a))


# ---------- tiny math typesetter ----------
class T:  # a text run
    def __init__(self, s, style="it", col=INK, key=None, scale=1.0):
        self.s, self.style, self.col, self.key, self.scale = s, style, col, key, scale


class Gap:
    def __init__(self, em):
        self.em = em


class Frac:
    def __init__(self, num, den, key=None, num_key=None, den_key=None, bar=INK):
        self.num, self.den, self.bar = num, den, bar
        self.num_key, self.den_key = num_key or key, den_key or key


FGAP = 0.21  # space between a fraction bar and its rows, in em


class Lim:  # "lim" with a subscript row below
    def __init__(self, sub, key=None, col=INK):
        self.sub, self.key, self.col = sub, key, col


def _m(it, size):
    """(width, ascent, descent) in output px."""
    if isinstance(it, T):
        f = font(it.style, size * it.scale)
        l, t, r, b = f.getbbox(it.s, anchor="ls")
        ic = (
            0.12 * size * it.scale if it.style == "it" and it.s.endswith("f") else 0.0
        )  # italic f overhang
        return f.getlength(it.s) / E.SS + ic, -t / E.SS, b / E.SS
    if isinstance(it, Gap):
        return it.em * size, 0, 0
    if isinstance(it, Frac):
        nw, na, nd = row_m(it.num, size)
        dw, da, dd = row_m(it.den, size)
        ax, gp = 0.26 * size, FGAP * size
        return max(nw, dw) + 0.24 * size, ax + gp + nd + na, -ax + gp + da + dd
    if isinstance(it, Lim):
        lw, la, ld = _m(T("lim", "rm"), size)
        sw, sa, sd = row_m(it.sub, size * 0.55)
        return max(lw, sw), la, 0.2 * size + sa + sd
    raise TypeError(it)


def row_m(items, size):
    w, a, d = 0.0, 0.0, 0.0
    for it in items:
        iw, ia, idd = _m(it, size)
        w, a, d = w + iw, max(a, ia), max(d, idd)
    return w, a, d


def math_row(img, d, items, size, x, base, alpha=None, group=None, strike=()):
    """Lay out and draw items left to right on a baseline. alpha: dict key -> 0..1 (missing key = 1).
    Returns {key: (l, t, r, b)} boxes in output px for placing labels."""
    alpha = alpha or {}
    boxes = {}

    def grow(k, b):
        if k is None or b is None:
            return
        o = boxes.get(k)
        boxes[k] = (
            b
            if o is None
            else (min(o[0], b[0]), min(o[1], b[1]), max(o[2], b[2]), max(o[3], b[3]))
        )

    def draw_row(its, sz, x0, bl, force=None, fkey=None):
        cx = x0
        for it in its:
            w, asc, desc = _m(it, sz)
            if isinstance(it, T):
                a = alpha.get(it.key, 1.0) if force is None else force
                b = text(
                    img, it.s, cx, bl, it.style, sz * it.scale, it.col, a, group=group
                )
                grow(it.key if fkey is None else fkey, b)
                grow("_all", b)
            elif isinstance(it, Frac):
                nw, na, nd = row_m(it.num, sz)
                dw, da, dd = row_m(it.den, sz)
                ax, gp = 0.26 * sz, FGAP * sz
                axis = bl - ax
                draw_row(it.num, sz, cx + (w - nw) / 2, axis - gp - nd)
                draw_row(it.den, sz, cx + (w - dw) / 2, axis + gp + da)
                ab = alpha.get(it.den_key, 1.0)
                line(
                    d,
                    [(cx + 0.04 * sz, axis), (cx + w - 0.04 * sz, axis)],
                    it.bar,
                    max(2, sz * 0.05),
                    ab,
                )
                grow(it.den_key, (cx, axis - 2, cx + w, axis + 2))
            elif isinstance(it, Lim):
                a = alpha.get(it.key, 1.0)
                lw = _m(T("lim", "rm"), sz)[0]
                b = text(
                    img, "lim", cx + (w - lw) / 2, bl, "rm", sz, it.col, a, group=group
                )
                grow(it.key, b)
                sw, sa, sd = row_m(it.sub, sz * 0.55)
                draw_row(
                    it.sub, sz * 0.55, cx + (w - sw) / 2, bl + 0.2 * sz + sa, a, it.key
                )
            cx += w
        return cx

    end = draw_row(items, size, x, base)
    boxes["_end"] = end
    for k in strike:  # cancel marks across a term
        if k in boxes:
            l, t, r, b = boxes[k]
            line(
                d, [(l - 4, b - 2), (r + 4, t + 6)], MUTED, 4, alpha.get("_strike", 1.0)
            )
    return boxes


# ---------- axes ----------
class Axes:
    def __init__(self, box, xr, yr):
        self.box, self.xr, self.yr = box, xr, yr

    def px(self, x, y):
        l, t, r, b = self.box
        return (
            l + (x - self.xr[0]) / (self.xr[1] - self.xr[0]) * (r - l),
            b - (y - self.yr[0]) / (self.yr[1] - self.yr[0]) * (b - t),
        )

    def grid(self, d, xs, ys, a=1.0):
        for x in xs:
            line(d, [self.px(x, self.yr[0]), self.px(x, self.yr[1])], GRID, 2, a)
        for y in ys:
            line(d, [self.px(self.xr[0], y), self.px(self.xr[1], y)], GRID, 2, a)

    def axes(self, d, a=1.0, x0=0.0, y0=0.0):
        line(d, [self.px(self.xr[0], y0), self.px(self.xr[1], y0)], MUTED, 3, a)
        line(d, [self.px(x0, self.yr[0]), self.px(x0, self.yr[1])], MUTED, 3, a)

    def curve(self, d, fn, xa, xb, col, w=5, prog=1.0, a=1.0, n=500, record=None):
        if prog <= 0 or a <= 0.003:
            return
        xs = np.linspace(xa, xa + (xb - xa) * min(1, prog), n)
        ys = np.array([fn(x) for x in xs])
        ok = (ys >= self.yr[0]) & (ys <= self.yr[1])
        seg = []
        for x, y, k in zip(xs, ys, ok):
            if k:
                seg.append(self.px(x, y))
            elif seg:
                line(d, seg, col, w, a)
                seg = []
        line(d, seg, col, w, a)
        if RECORD and record and a > 0.5:
            LOG.append(
                dict(
                    kind="curve",
                    name=record,
                    pts=[self.px(x, y) for x, y, k in zip(xs, ys, ok) if k],
                )
            )

    def seg(self, d, p0, p1, col, w=5, a=1.0):
        """Data-space segment clipped to the axes ranges (Liang-Barsky)."""
        (x0, y0), (x1, y1) = p0, p1
        dx, dy = x1 - x0, y1 - y0
        u0, u1 = 0.0, 1.0
        for p, q in (
            (-dx, x0 - self.xr[0]),
            (dx, self.xr[1] - x0),
            (-dy, y0 - self.yr[0]),
            (dy, self.yr[1] - y0),
        ):
            if p == 0:
                if q < 0:
                    return
                continue
            r = q / p
            if p < 0:
                u0 = max(u0, r)
            else:
                u1 = min(u1, r)
        if u0 >= u1:
            return
        line(
            d,
            [self.px(x0 + u0 * dx, y0 + u0 * dy), self.px(x0 + u1 * dx, y0 + u1 * dy)],
            col,
            w,
            a,
        )
