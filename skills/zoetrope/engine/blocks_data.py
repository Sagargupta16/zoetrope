"""blocks_data.py : data blocks a scene drops onto its canvas: charts, counters, rings, a route and an audio visualizer.

The ideas come from the block registries of HeyGen's hyperframes (Apache-2.0) and Remotion's chart elements; no code is
copied. Every block is a pure draw plus a twin that reports its text, so the picture is a function of t and the text
gates (Q200 to Q209, Q402) see every label as it reads at t.

    bar_race(img, t, keys, periods=None, ...)       bars that grow, re-sort and slide as values change between keys
    line_draw(img, t, values, xlabels=None, ...)    a line chart that draws on, with ticks and a value on its head
    pie(img, t, parts, donut=True, ...)             a pie or donut that sweeps in, a legend and a centre total
    counter(img, t, value, ...)                     a number that rolls to a value: separators, prefix, suffix
    stat_ring(img, t, pct, ...)                     a ring that fills to a percentage, the figure in its centre
    progress_bar(img, t, pct, ...)                  a bar that fills to a percentage, with a label and the figure
    route_arc(img, t, a, b, labels, ...)            a curved route between two points: dashed trail, solid draw-on,
                                                    an arrowhead or dot, end markers and labels (plain or image plate)
    audio_bars(img, t, levels, style, ...)          bars, a mirror or a wave from analyse_wav() band levels
    analyse_wav(path, fps, bands)                   per-frame band levels of a WAV, 0 to 1, computed once and cached
    format_number(v, decimals, prefix, suffix, sep) the number format every block uses

Contract, for each block `name`:

    name(img, t, ..., t0=, dur=, alpha=)   draws onto img (an RGBA canvas, supersampled as the template's draw) and
                                           returns it. Same arguments, same pixels, in any order and process.
    name_items(t, ...)                     the same arguments without img; the records for the scene's text_items(t),
                                           with the keys the template's records use (s, box, fg, alpha, px, bold), and
                                           ticker=True for a value that changes while it is on screen.

Both come from one plan(t, ...) per block that lists the shapes and the labels, so the registry cannot drift from the
picture. t0 is when the block starts moving and dur how long its move lasts, in the scene's seconds; alpha multiplies
the whole block (a scene fade). box is (x0, y0, x1, y1) in output px, default the frame less 6 percent a side. Text is
never under 36 px (Q402). The colours are parameters whose defaults are the DATA_* constants below; pass the style's.
Over a photo, check the text against it (Q301) or pass halo= to route_arc.
"""

import hashlib
import inspect
import itertools
import math
import struct
from functools import lru_cache
from pathlib import Path

import engine as E
import numpy as np
from contract import frame_of, read_wav_chunks
from engine import (
    clamp,
    ease_in_out_cubic,
    ease_in_out_sine,
    ease_out_cubic,
    fit_size,
    hexrgb,
    lerp,
    prog,
    rrect,
    smoothstep,
    text,
    text_box,
    text_halo,
    text_w,
)
from PIL import Image, ImageDraw

DATA_TEXT = "#F7F3EA"  # labels and figures on a dark ground
DATA_MUTED = "#8A93A8"  # grid, axes and dashed trails
DATA_TRACK = "#2A3350"  # the empty part of a ring or bar
DATA_ACCENT = "#FF6B4A"  # the one highlighted thing
DATA_HALO = "#101828"  # the soft shadow under text over a picture
DATA_SERIES = (  # one colour a series, in order
    "#FF6B4A",
    "#4AA3FF",
    "#F5C451",
    "#5BD6A0",
    "#B58CFF",
    "#FF8FB1",
    "#7AD7F0",
    "#C7D36F",
)
LABEL_MIN = 36  # px: Q402 notes key text under this at 1080


# ---------------------------------------------------------------- shared helpers


def format_number(v, decimals=0, prefix="", suffix="", sep=","):
    """v as text: 1234567.891 -> '$1,234,568%' with prefix '$', suffix '%'. sep groups the thousands ('' for none)."""
    d = max(0, int(decimals))
    r = round(float(v), d)
    if r == 0:
        r = 0.0  # never "-0"
    s = f"{abs(r):,.{d}f}"
    if sep != ",":
        s = s.replace(",", sep)
    return ("-" if r < 0 else "") + prefix + s + suffix


def _u():
    """Scale against a 1080 short side, so sizes hold in 1920x1080 and 1080x1920."""
    return min(E.W, E.H) / 1080


def _px(size):
    return max(LABEL_MIN, size)


def _pr(t, t0, dur):
    return prog(t, t0, max(dur, 1e-6))


def _frame(box, margin=0.06):
    if box is None:
        return (E.W * margin, E.H * margin, E.W * (1 - margin), E.H * (1 - margin))
    return tuple(box)


def _lab(s, xy, size, anchor, fill, alpha=1.0, halo=None, ticker=False):
    return {
        "s": s,
        "xy": xy,
        "size": _px(size),
        "anchor": anchor,
        "fill": fill,
        "alpha": alpha,
        "halo": halo,
        "ticker": ticker,
    }


def _scale(prims, labels, alpha):
    """The plan with every alpha multiplied by the block's own."""
    if alpha >= 1:
        return prims, labels
    prims = [p[:-1] + (p[-1] * alpha,) for p in prims]
    return prims, [{**L, "alpha": L["alpha"] * alpha} for L in labels]


def _records(labels):
    """text_items(t) records of a plan's labels."""
    out = []
    for L in labels:
        if L["alpha"] <= 0 or not L["s"]:
            continue
        rec = {
            "s": L["s"],
            "box": text_box(L["s"], L["xy"], L["size"], L["anchor"], True),
            "fg": L["fill"],
            "alpha": L["alpha"],
            "px": L["size"],
            "bold": True,
        }
        if L["ticker"]:
            rec["ticker"] = True
        out.append(rec)
    return out


def _paint(img, bounds, colour, alpha, painter, pad=3):
    """Anti-aliased shape: painter(d, f, u) draws white on a mask 3 to 4 times finer than img inside bounds
    (l, t, r, b output px); f maps an output point to the mask, u is mask px per output px. Colour goes through it."""
    if alpha <= 0:
        return
    ss = E.SS
    k = 4 if ss == 1 else 2
    x0 = max(0, math.floor(bounds[0] * ss) - pad)
    y0 = max(0, math.floor(bounds[1] * ss) - pad)
    x1 = min(img.width, math.ceil(bounds[2] * ss) + pad)
    y1 = min(img.height, math.ceil(bounds[3] * ss) + pad)
    if x1 <= x0 or y1 <= y0:
        return
    mask = Image.new("L", ((x1 - x0) * k, (y1 - y0) * k), 0)

    def f(p):
        return ((p[0] * ss - x0) * k, (p[1] * ss - y0) * k)

    painter(ImageDraw.Draw(mask), f, k * ss)
    c = hexrgb(colour) if isinstance(colour, str) else colour
    cov = np.asarray(mask.resize((x1 - x0, y1 - y0), Image.BOX), float)
    a = np.rint(cov * (alpha * c[3] / 255)).astype(np.uint8)
    lay = Image.new("RGBA", (x1 - x0, y1 - y0), c[:3] + (0,))
    lay.putalpha(Image.fromarray(a))
    if img.mode == "RGBA":
        img.alpha_composite(lay, (x0, y0))
    else:
        img.paste(lay, (x0, y0), lay)


def _bounds(points, grow):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return (min(xs) - grow, min(ys) - grow, max(xs) + grow, max(ys) + grow)


def _stroke(img, lines, width, colour, alpha):
    pts = [p for ln in lines for p in ln]
    if not pts or alpha <= 0:
        return

    def painter(d, f, u):
        w = max(1, round(width * u))
        for ln in lines:
            q = [f(p) for p in ln]
            if len(q) > 1:
                d.line(q, fill=255, width=w, joint="curve")
            for e in (q[0], q[-1]):  # round caps
                d.ellipse(
                    [e[0] - w / 2, e[1] - w / 2, e[0] + w / 2, e[1] + w / 2], fill=255
                )

    _paint(img, _bounds(pts, width), colour, alpha, painter)


def _poly(img, pts, colour, alpha):
    def painter(d, f, u):
        d.polygon([f(p) for p in pts], fill=255)

    _paint(img, _bounds(pts, 1), colour, alpha, painter)


def _dot(img, c, r, colour, alpha):
    def painter(d, f, u):
        x, y = f(c)
        d.ellipse([x - r * u, y - r * u, x + r * u, y + r * u], fill=255)

    _paint(img, (c[0] - r, c[1] - r, c[0] + r, c[1] + r), colour, alpha, painter)


def _sector(img, c, r_in, r_out, a0, a1, caps, colour, alpha):
    """A pie slice or ring segment from a0 to a1 degrees, clockwise from 12 o'clock; caps rounds the ends."""
    if a1 <= a0:
        return

    def painter(d, f, u):
        x, y = f(c)
        ro, ri = r_out * u, r_in * u
        if a1 - a0 >= 359.99:
            d.ellipse([x - ro, y - ro, x + ro, y + ro], fill=255)
        else:
            d.pieslice([x - ro, y - ro, x + ro, y + ro], a0 - 90, a1 - 90, fill=255)
        if ri > 0:
            d.ellipse([x - ri, y - ri, x + ri, y + ri], fill=0)
        if caps and a1 - a0 < 359.99:
            rm, rc = (ro + ri) / 2, (ro - ri) / 2
            for a in (a0, a1):
                px = x + rm * math.sin(math.radians(a))
                py = y - rm * math.cos(math.radians(a))
                d.ellipse([px - rc, py - rc, px + rc, py + rc], fill=255)

    _paint(
        img,
        (c[0] - r_out, c[1] - r_out, c[0] + r_out, c[1] + r_out),
        colour,
        alpha,
        painter,
    )


def _render(img, prims, labels):
    for p in prims:
        k = p[0]
        if k == "rect":
            rrect(img, p[1], p[2], p[3], p[4])
        elif k == "stroke":
            _stroke(img, p[1], p[2], p[3], p[4])
        elif k == "poly":
            _poly(img, p[1], p[2], p[3])
        elif k == "dot":
            _dot(img, p[1], p[2], p[3], p[4])
        elif k == "sector":
            _sector(img, *p[1:])
    for L in labels:
        if L["alpha"] <= 0 or not L["s"]:
            continue
        if L["halo"] is not None:
            text_halo(
                img,
                L["s"],
                L["xy"],
                L["size"],
                L["fill"],
                L["halo"],
                8,
                0.75,
                L["anchor"],
                L["alpha"],
            )
        else:
            text(img, L["s"], L["xy"], L["size"], L["fill"], L["anchor"], L["alpha"])
    return img


def _twins(plan, name):
    """(name, name_items) from plan(t, ...) -> (prims, labels): the draw and the text registry twin."""

    def draw(img, t, *a, **kw):
        return _render(img, *plan(t, *a, **kw))

    def items(t, *a, **kw):
        return _records(plan(t, *a, **kw)[1])

    params = list(inspect.signature(plan).parameters.values())
    first = inspect.Parameter("img", inspect.Parameter.POSITIONAL_OR_KEYWORD)
    draw.__signature__ = inspect.Signature([first, *params])
    items.__signature__ = inspect.Signature(params)
    draw.__name__ = draw.__qualname__ = name
    items.__name__ = items.__qualname__ = name + "_items"
    draw.__doc__ = (plan.__doc__ or "") + "\n    Draws onto img and returns it."
    items.__doc__ = (
        f"The text records {name} draws at t: pass what {name} gets after img."
    )
    return draw, items


def _nice_ticks(lo, hi, n=4):
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / max(1, n)
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if raw <= m * mag * 1.0000001)
    a, b = math.floor(lo / step + 1e-9) * step, math.ceil(hi / step - 1e-9) * step
    return [a + i * step for i in range(round((b - a) / step) + 1)], step


# ---------------------------------------------------------------- bar chart race


def _race_pos(t, times):
    """(i, j, k): the keys t sits between and the eased way from i to j."""
    n = len(times)
    if n == 1 or t <= times[0]:
        return 0, 0, 0.0
    if t >= times[-1]:
        return n - 1, n - 1, 0.0
    i = max(j for j in range(n) if times[j] <= t)
    return i, i + 1, ease_in_out_sine(_pr(t, times[i], times[i + 1] - times[i]))


def _race_ranks(vals, names):
    order = sorted(names, key=lambda n: (-vals.get(n, 0.0), names.index(n)))
    return {n: i for i, n in enumerate(order)}


def _race_slide(names, ra, rb, pos, row, text_h, wn, wv, gap, k):
    """({name: px}, {name: px}): how far each name and each value slides left (clear of the others' text) where two
    rows pass. Of two rows that cross, the one that travels farther slides, by the other's width and its own slide."""
    far = {n: (abs(rb[n] - ra[n]), i) for i, n in enumerate(names)}
    sn, sv = dict.fromkeys(names, 0.0), dict.fromkeys(names, 0.0)
    settle = smoothstep(min(k, 1 - k) / 0.05)  # no slide on a key, so none jumps in
    for p in sorted(names, key=far.get):
        for q in names:
            if far[q] < far[p] and (ra[p] - ra[q]) * (rb[p] - rb[q]) < 0:
                w = (
                    smoothstep((4 * text_h - abs(pos[p] - pos[q]) * row) / (3 * text_h))
                    * settle
                )
                sn[p] = max(sn[p], w * (sn[q] + wn[q] + gap))
                sv[p] = max(sv[p], w * (sv[q] + wv[q] + gap))
    return sn, sv


@lru_cache(maxsize=8)
def _race_room(frozen, names, row, text_h, nsize, ls, fmt, gap):
    """(left, right) px the slide of _race_slide can need, found by walking every pair of keys: 0 and 0 when no rows
    pass. Widths are each name's and its peak value's, so it is at least what any frame uses."""
    wn = {n: text_w(str(n), nsize) for n in names}
    wv = {
        n: text_w(format_number(max(dict(v).get(n, 0.0) for _, v in frozen), *fmt), ls)
        for n in names
    }
    most, ranks = [0.0, 0.0], []
    for _, vals in frozen:
        d = dict(vals)
        ranks.append(_race_ranks(d, list(names)))
    for ra, rb in itertools.pairwise(ranks):
        for s in range(33):
            pos = {n: lerp(ra[n], rb[n], s / 32) for n in names}
            sn, sv = _race_slide(
                list(names), ra, rb, pos, row, text_h, wn, wv, gap, s / 32
            )
            most = [max(most[0], max(sn.values())), max(most[1], max(sv.values()))]
    return most[0], most[1]


def _plan_race(
    t,
    keys,
    periods=None,
    top=None,
    box=None,
    prefix="",
    suffix="",
    decimals=0,
    sep=",",
    colors=None,
    text_color=DATA_TEXT,
    muted=DATA_MUTED,
    t0=0.0,
    dur=0.6,
    alpha=1.0,
):
    """Bar chart race. keys: [(time, {name: value}), ...] in scene seconds, ascending; values and ranks ease between
    two keys (before the first and after the last they hold). periods: one label a key (a year), shown top right as
    the nearer key's. Names stand left of the bars and values in a column at the right edge; where two rows pass each
    other the one moving up slips sideways clear of the other's text (a reserved margin), so no two labels overlap.
    top: rows shown (default all); a row sliding out or in shows a value the gates read as settled, wanting a 1 s hold,
    so keep top at the number of names unless that is meant. Hold the first and last key 1 s or more. colors:
    {name: colour}, default DATA_SERIES in order of first appearance. Bars and labels come in over t0, dur."""
    a = ease_out_cubic(_pr(t, t0, dur))
    if a <= 0 or not keys:
        return [], []
    x0, y0, x1, y1 = _frame(box)
    u = _u()
    names = []
    for _, vals in keys:
        for n in vals:
            if n not in names:
                names.append(n)
    top = len(names) if top is None else max(1, min(top, len(names)))
    i, j, k = _race_pos(t, [kk[0] for kk in keys])
    va, vb = keys[i][1], keys[j][1]
    vals = {n: lerp(va.get(n, 0.0), vb.get(n, 0.0), k) for n in names}
    ra, rb = _race_ranks(va, names), _race_ranks(vb, names)
    ls = _px(40 * u)
    labels = []
    if periods:
        ps = _px(88 * u)
        labels.append(
            _lab(
                periods[i if k < 0.5 else j], (x1, y0), ps, "ra", muted, a, ticker=True
            )
        )
        y0 += ps * 1.3
    row = min(
        (y1 - y0) / top, 84 * u
    )  # rows pass at a pace a ticker's boxes can follow (Q401)
    y0 += ((y1 - y0) - row * top) / 2
    bar_h = min(row * 0.7, 96 * u)
    longest = max(names, key=lambda n: text_w(str(n), ls))
    nsize = fit_size(str(longest), ls, (x1 - x0) * 0.3)
    fmt = (decimals, prefix, suffix, sep)
    namew = text_w(str(longest), nsize)
    peak = max(max(kk[1].values(), default=0.0) for kk in keys)
    valw = text_w(format_number(peak, *fmt), ls)
    gap = 18 * u
    text_h = ls * 1.4
    frozen = tuple(
        (kk[0], tuple(sorted(kk[1].items(), key=lambda x: str(x[0])))) for kk in keys
    )
    rn, rv = _race_room(frozen, tuple(names), row, text_h, nsize, ls, fmt, gap)
    ax0 = x0 + namew + 2 * gap + rn
    ax1 = x1 - valw - gap - rv
    vmax = max(max(vals.values()), 1e-9)
    pos = {n: lerp(ra[n], rb[n], k) for n in names}
    wn = {n: text_w(str(n), nsize) for n in names}
    wv = {n: text_w(format_number(vals[n], *fmt), ls) for n in names}
    sn, sv = _race_slide(names, ra, rb, pos, row, text_h, wn, wv, gap, k)
    prims = []
    for n in names:
        vis = clamp(top - pos[n]) * a
        if vis <= 0:
            continue
        cy = y0 + (pos[n] + 0.5) * row
        length = (ax1 - ax0) * clamp(vals[n] / vmax) * a
        col = (colors or {}).get(n) or DATA_SERIES[names.index(n) % len(DATA_SERIES)]
        if length >= 1:
            prims.append(
                (
                    "rect",
                    (ax0, cy - bar_h / 2, ax0 + length, cy + bar_h / 2),
                    min(bar_h * 0.25, length / 2),
                    col,
                    vis,
                )
            )
        labels.append(
            _lab(str(n), (ax0 - gap - sn[n], cy), nsize, "rm", text_color, vis)
        )
        labels.append(
            _lab(
                format_number(vals[n], *fmt),
                (x1 - sv[n], cy),
                ls,
                "rm",
                text_color,
                vis,
                ticker=True,
            )
        )
    return _scale(prims, labels, alpha)


bar_race, bar_race_items = _twins(_plan_race, "bar_race")


# ---------------------------------------------------------------- line chart


def _plan_line(
    t,
    values,
    xlabels=None,
    box=None,
    ymin=None,
    ymax=None,
    prefix="",
    suffix="",
    decimals=0,
    sep=",",
    color=DATA_ACCENT,
    text_color=DATA_TEXT,
    muted=DATA_MUTED,
    t0=0.0,
    dur=1.6,
    alpha=1.0,
):
    """Line chart that draws on over t0, dur. values: y values at even x steps. xlabels: one string a value ('' for
    none), under the axis. ymin and ymax pin the axis, else it rounds out to nice ticks. A dot leads the line; when it
    arrives the last point lights up and shows its value (decimals, prefix, suffix, sep): hold the scene 1 s or more
    after t0 + dur + 0.3 for the reading hold (Q401)."""
    if not values:
        return [], []
    x0, y0, x1, y1 = _frame(box)
    u = _u()
    ls, hs = _px(36 * u), _px(44 * u)
    lo, hi = (
        (min(values) if ymin is None else ymin),
        (max(values) if ymax is None else ymax),
    )
    ticks, step = _nice_ticks(lo, hi)
    lo, hi = (ticks[0] if ymin is None else ymin), (ticks[-1] if ymax is None else ymax)
    td = 0 if step >= 1 else math.ceil(-math.log10(step) - 1e-9)
    tick_s = [format_number(v, td, prefix, suffix, sep) for v in ticks]
    ax0 = x0 + max(text_w(s, ls) for s in tick_s) + 22 * u
    ax1 = x1 - 40 * u
    top = y0 + hs + 40 * u
    bot = y1 - (ls * 1.3 + 34 * u if xlabels else 0)
    n = len(values)
    fade = ease_out_cubic(_pr(t, t0, min(dur * 0.3, 0.4)))
    prims, labels = [], []

    def py(v):
        return bot - (v - lo) / max(hi - lo, 1e-9) * (bot - top)

    for v, s in zip(ticks, tick_s):
        if lo <= v <= hi:
            prims.append(
                ("stroke", [[(ax0, py(v)), (ax1, py(v))]], 2 * u, muted, 0.35 * fade)
            )
            labels.append(_lab(s, (ax0 - 14 * u, py(v)), ls, "rm", muted, fade))
    prims.append(("stroke", [[(ax0, bot), (ax1, bot)]], 3 * u, muted, 0.8 * fade))
    pts = [
        (ax0 + i / max(n - 1, 1) * (ax1 - ax0), py(clamp(v, lo, hi)))
        for i, v in enumerate(values)
    ]
    for i, s in enumerate(xlabels or []):
        if s and i < n:
            labels.append(_lab(s, (pts[i][0], bot + 34 * u), ls, "mt", muted, fade))
    p = ease_in_out_sine(_pr(t, t0, dur))
    h = p * (n - 1)
    kk = min(int(h), n - 1)
    if kk >= n - 1:
        head = pts[-1]
    else:
        f = h - kk
        head = (
            lerp(pts[kk][0], pts[kk + 1][0], f),
            lerp(pts[kk][1], pts[kk + 1][1], f),
        )
    prims.append(("stroke", [pts[: kk + 1] + [head]], 7 * u, color, fade))
    prims.append(("dot", head, 11 * u, color, fade))
    land = ease_out_cubic(_pr(t, t0 + dur, 0.3))  # the last point lights up on arrival
    if land > 0:
        last = pts[-1]
        prims.append(("dot", last, 24 * u, color, 0.3 * land))
        s = format_number(values[-1], decimals, prefix, suffix, sep)
        hw = text_w(s, hs) / 2
        above = last[1] - 28 * u - hs >= y0
        labels.append(
            _lab(
                s,
                (
                    clamp(last[0], ax0 + hw, x1 - hw),
                    last[1] - 28 * u if above else last[1] + 28 * u,
                ),
                hs,
                "mb" if above else "mt",
                text_color,
                land,
            )
        )
    return _scale(prims, labels, alpha)


line_draw, line_draw_items = _twins(_plan_line, "line_draw")


# ---------------------------------------------------------------- pie and donut


def _plan_pie(
    t,
    parts,
    donut=True,
    total_label="Total",
    box=None,
    hole=0.58,
    prefix="",
    suffix="",
    decimals=0,
    sep=",",
    pct_decimals=0,
    colors=None,
    text_color=DATA_TEXT,
    muted=DATA_MUTED,
    t0=0.0,
    dur=1.4,
    alpha=1.0,
):
    """Pie or donut sweeping in clockwise from 12 o'clock over t0, dur. parts: [(label, value), ...]. A legend
    (swatch, label, share) sits beside the pie in landscape and under it in portrait, each row fading in as the sweep
    passes its slice. donut=True leaves a hole of `hole` of the radius holding the total (prefix, suffix, decimals,
    sep) rolling up with the sweep and total_label under it ('' for none). colors: [colour, ...], default DATA_SERIES."""
    parts = [(str(n), float(v)) for n, v in parts if v > 0]
    total = sum(v for _, v in parts)
    if not parts:
        return [], []
    x0, y0, x1, y1 = _frame(box)
    u = _u()
    ls = _px(40 * u)
    bw, bh = x1 - x0, y1 - y0
    land = E.W >= E.H
    d = min(bh, bw * 0.5) if land else min(bw, bh * 0.55)
    r_out = d / 2
    cx, cy = (x0 + r_out, y0 + bh / 2) if land else (x0 + bw / 2, y0 + r_out)
    sweep = ease_out_cubic(_pr(t, t0, dur)) * 360
    cols = colors or DATA_SERIES
    pct = [format_number(v / total * 100, pct_decimals, "", "%") for _, v in parts]
    swatch = ls * 0.7
    namew = max(text_w(n, ls) for n, _ in parts)
    pctw = max(text_w(s, ls) for s in pct)
    lw = swatch + 18 * u + namew + 40 * u + pctw
    if land:
        lx = cx + r_out + 70 * u
        lw = min(lw, x1 - lx)
        rows_y0, rows_h = y0, bh
    else:
        lx = x0 + (bw - min(lw, bw)) / 2
        lw = min(lw, bw)
        rows_y0 = cy + r_out + 50 * u
        rows_h = y1 - rows_y0
    row = min(ls * 1.55, rows_h / len(parts))
    ry0 = rows_y0 + (rows_h - row * len(parts)) / 2 if land else rows_y0
    prims, labels, acc = [], [], 0.0
    gap = 1.6 if len(parts) > 1 else 0.0
    for i, (n, v) in enumerate(parts):
        a0, a1 = acc / total * 360, (acc + v) / total * 360
        acc += v
        col = cols[i % len(cols)]
        g = gap / 2 if a1 - a0 > 4 * gap else 0.0
        end = min(a1 - g, sweep)
        if end > a0 + g:
            prims.append(
                (
                    "sector",
                    (cx, cy),
                    r_out * hole if donut else 0.0,
                    r_out,
                    a0 + g,
                    end,
                    False,
                    col,
                    1.0,
                )
            )
        vis = clamp((sweep - a0) / min(30.0, 360.0 - a0))
        if vis > 0:
            cyy = ry0 + (i + 0.5) * row
            prims.append(
                (
                    "rect",
                    (lx, cyy - swatch / 2, lx + swatch, cyy + swatch / 2),
                    swatch * 0.2,
                    col,
                    vis,
                )
            )
            labels.append(
                _lab(n, (lx + swatch + 18 * u, cyy), ls, "lm", text_color, vis)
            )
            labels.append(_lab(pct[i], (lx + lw, cyy), ls, "rm", muted, vis))
    if donut:
        rh = r_out * hole
        final = format_number(total, decimals, prefix, suffix, sep)
        ns = fit_size(final, min(rh * 0.55, 120 * u), rh * 1.5)
        shown = format_number(total * sweep / 360, decimals, prefix, suffix, sep)
        labels.append(
            _lab(
                shown,
                (cx, cy - (ls * 0.45 if total_label else 0)),
                ns,
                "mm",
                text_color,
                1.0,
                ticker=True,
            )
        )
        if total_label:
            labels.append(
                _lab(
                    total_label,
                    (cx, cy + ns * 0.55),
                    ls,
                    "mm",
                    muted,
                    clamp(sweep / 90),
                )
            )
    return _scale(prims, labels, alpha)


pie, pie_items = _twins(_plan_pie, "pie")


# ---------------------------------------------------------------- counter


def _plan_counter(
    t,
    value,
    start=0.0,
    xy=None,
    size=160,
    anchor="mm",
    decimals=0,
    prefix="",
    suffix="",
    sep=",",
    maxw=None,
    ease=ease_out_cubic,
    color=DATA_TEXT,
    t0=0.0,
    dur=1.5,
    alpha=1.0,
):
    """A number rolling from start to value over t0, dur through `ease` (an engine easing), drawn at xy (default the
    frame centre) with `anchor`. The size is fitted once to the wider of the two end values within maxw (default 88
    percent of the frame width), so it never changes mid-roll."""
    fmt = (decimals, prefix, suffix, sep)
    xy = xy or (E.W / 2, E.H / 2)
    widest = max(
        (format_number(v, *fmt) for v in (start, value)), key=lambda s: text_w(s, size)
    )
    s = fit_size(widest, size * _u(), maxw or E.W * 0.88)
    v = lerp(start, value, ease(_pr(t, t0, dur)))
    return _scale(
        [],
        [_lab(format_number(v, *fmt), xy, s, anchor, color, 1.0, ticker=True)],
        alpha,
    )


counter, counter_items = _twins(_plan_counter, "counter")


# ---------------------------------------------------------------- stat ring and progress bar


def _plan_ring(
    t,
    pct,
    label="",
    box=None,
    decimals=0,
    thickness=0.16,
    color=DATA_ACCENT,
    track=DATA_TRACK,
    text_color=DATA_TEXT,
    muted=DATA_MUTED,
    t0=0.0,
    dur=1.4,
    alpha=1.0,
):
    """Ring filling clockwise from 12 o'clock to pct (0 to 100) over t0, dur, with the figure rolling in its centre and
    an optional label under it. thickness is a share of the radius. Centred in box, as large as fits."""
    x0, y0, x1, y1 = _frame(box)
    u = _u()
    r = min(x1 - x0, y1 - y0) / 2
    c = ((x0 + x1) / 2, (y0 + y1) / 2)
    cur = clamp(pct, 0, 100) * ease_out_cubic(_pr(t, t0, dur))
    r_in = r * (1 - thickness)
    prims = [("sector", c, r_in, r, 0.0, 360.0, False, track, 1.0)]
    if cur > 0:
        prims.append(("sector", c, r_in, r, 0.0, cur * 3.6, True, color, 1.0))
    final = format_number(pct, decimals, "", "%")
    ns = fit_size(final, min(r_in * 0.6, 150 * u), r_in * 1.5)
    labels = [
        _lab(
            format_number(cur, decimals, "", "%"),
            (c[0], c[1] - (ns * 0.18 if label else 0)),
            ns,
            "mm",
            text_color,
            1.0,
            ticker=True,
        )
    ]
    if label:
        labels.append(
            _lab(
                label,
                (c[0], c[1] + ns * 0.62),
                _px(40 * u),
                "mm",
                muted,
                ease_out_cubic(_pr(t, t0, 0.4)),
            )
        )
    return _scale(prims, labels, alpha)


stat_ring, stat_ring_items = _twins(_plan_ring, "stat_ring")


def _plan_progress(
    t,
    pct,
    label="",
    box=None,
    decimals=0,
    color=DATA_ACCENT,
    track=DATA_TRACK,
    text_color=DATA_TEXT,
    t0=0.0,
    dur=1.2,
    alpha=1.0,
):
    """Bar filling left to right to pct (0 to 100) over t0, dur: the label above its left end, the figure above its
    right end, both on the bar's line. The bar sits in the middle of box and is 44 px tall at 1080."""
    x0, y0, x1, y1 = _frame(box)
    u = _u()
    bh = 44 * u
    cy = (y0 + y1) / 2 + 30 * u
    cur = clamp(pct, 0, 100) * ease_out_cubic(_pr(t, t0, dur))
    prims = [("rect", (x0, cy - bh / 2, x1, cy + bh / 2), bh / 2, track, 1.0)]
    w = (x1 - x0) * cur / 100
    if w >= 1:
        prims.append(
            (
                "rect",
                (x0, cy - bh / 2, x0 + max(w, bh), cy + bh / 2),
                bh / 2,
                color,
                1.0,
            )
        )
    ls = _px(48 * u)
    y = cy - bh / 2 - 18 * u
    labels = [
        _lab(
            format_number(cur, decimals, "", "%"),
            (x1, y),
            ls,
            "rb",
            text_color,
            1.0,
            ticker=True,
        )
    ]
    if label:
        labels.append(
            _lab(label, (x0, y), ls, "lb", text_color, ease_out_cubic(_pr(t, t0, 0.4)))
        )
    return _scale(prims, labels, alpha)


progress_bar, progress_bar_items = _twins(_plan_progress, "progress_bar")


# ---------------------------------------------------------------- route arc


def _bezier(a, b, bulge, n=96):
    """n + 1 points of the quadratic curve a to b bowed by bulge x the distance (positive: up for a left-to-right
    route), and the running length at each."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    cp = ((a[0] + b[0]) / 2 + dy * bulge, (a[1] + b[1]) / 2 - dx * bulge)
    pts = []
    for i in range(n + 1):
        s = i / n
        pts.append(
            (
                (1 - s) ** 2 * a[0] + 2 * (1 - s) * s * cp[0] + s * s * b[0],
                (1 - s) ** 2 * a[1] + 2 * (1 - s) * s * cp[1] + s * s * b[1],
            )
        )
    run = [0.0]
    for p, q in itertools.pairwise(pts):
        run.append(run[-1] + math.hypot(q[0] - p[0], q[1] - p[1]))
    return pts, run


def _along(pts, run, s):
    """(point, unit tangent, the points before it) at running length s."""
    s = clamp(s, 0.0, run[-1])
    i = min(max(k for k in range(len(run)) if run[k] <= s), len(run) - 2)
    seg = max(run[i + 1] - run[i], 1e-9)
    f = (s - run[i]) / seg
    p = (lerp(pts[i][0], pts[i + 1][0], f), lerp(pts[i][1], pts[i + 1][1], f))
    return (
        p,
        ((pts[i + 1][0] - pts[i][0]) / seg, (pts[i + 1][1] - pts[i][1]) / seg),
        pts[: i + 1],
    )


def _dashes(pts, run, dash, gap):
    out, s = [], 0.0
    while s < run[-1]:
        e = min(s + dash, run[-1])
        p, _, before = _along(pts, run, s)
        q, _, mid = _along(pts, run, e)
        out.append([p] + mid[len(before) :] + [q])
        s += dash + gap
    return out


def _plan_route(
    t,
    a,
    b,
    labels=("", ""),
    bulge=0.25,
    head="arrow",
    halo=None,
    size=44,
    color=DATA_ACCENT,
    trail=DATA_MUTED,
    text_color=DATA_TEXT,
    t0=0.0,
    dur=1.8,
    alpha=1.0,
):
    """A route from point a to point b (output px) bowed by `bulge` of its length (negative bows the other way). The
    dashed trail shows the whole way, the solid line draws on over t0, dur under a moving `head` ('arrow', 'dot' or
    None), and a marker and label stand at each end (labels: (from, to)): the first from t0, the second on arrival.
    halo: a colour puts a soft shadow under the labels so they read over an image plate (None: plain text)."""
    u = _u()
    pts, run = _bezier(a, b, bulge)
    p = ease_in_out_cubic(_pr(t, t0, dur))
    fade_a = ease_out_cubic(_pr(t, t0, 0.3))
    fade_b = ease_out_cubic(_pr(t, t0 + dur, 0.3))
    if fade_a <= 0:
        return [], []
    prims = [("stroke", _dashes(pts, run, 22 * u, 16 * u), 4 * u, trail, 0.7 * fade_a)]
    pos, tan, before = _along(pts, run, p * run[-1])
    if p > 0:
        prims.append(("stroke", [before + [pos]], 9 * u, color, 1.0))
    prims.append(("dot", a, 13 * u, color, fade_a))
    prims.append(("dot", b, 13 * u, color, fade_b))
    prims.append(("dot", b, 26 * u, color, 0.3 * fade_b))
    if head and p > 0:
        if head == "dot":
            prims.append(("dot", pos, 17 * u, color, 1.0))
        else:
            n = (-tan[1], tan[0])
            s = 30 * u
            tip = (pos[0] + tan[0] * s * 0.6, pos[1] + tan[1] * s * 0.6)
            tail = (pos[0] - tan[0] * s * 0.8, pos[1] - tan[1] * s * 0.8)
            prims.append(
                (
                    "poly",
                    [
                        tip,
                        (tail[0] + n[0] * s * 0.7, tail[1] + n[1] * s * 0.7),
                        (tail[0] - n[0] * s * 0.7, tail[1] - n[1] * s * 0.7),
                    ],
                    color,
                    1.0,
                )
            )
    ls = _px(size * u)
    out = []
    for pt, s, al in ((a, labels[0], fade_a), (b, labels[1], fade_b)):
        if s:
            hw = text_w(s, ls) / 2
            x = clamp(pt[0], E.W * 0.05 + hw, E.W * 0.95 - hw)
            out.append(
                _lab(s, (x, pt[1] + 26 * u), ls, "mt", text_color, al, halo=halo)
            )
    return _scale(prims, out, alpha)


route_arc, route_arc_items = _twins(_plan_route, "route_arc")


# ---------------------------------------------------------------- audio visualizer


def _mix(c1, c2, k):
    a, b = hexrgb(c1), hexrgb(c2)
    return tuple(round(lerp(a[i], b[i], k)) for i in range(3)) + (255,)


def _plan_audio(
    t,
    levels,
    style="bars",
    box=None,
    fps=None,
    offset=0.0,
    release=0.55,
    gap=0.35,
    color=DATA_ACCENT,
    color2=None,
    t0=0.0,
    dur=0.5,
    alpha=1.0,
):
    """Audio visualizer from analyse_wav() levels (frames x bands, 0 to 1): the row of frame_of(t + offset). style
    'bars' stands bars on the box floor, 'mirror' grows them both ways from its middle line, 'wave' fills a smooth
    mirrored shape. release 0 to 1 is how slowly a bar falls (the max of the last rows, each times release again).
    color2 blends across the bands. fps is the rate of levels (default the build's). Draws no text."""
    a = ease_out_cubic(_pr(t, t0, dur))
    lv = np.asarray(levels, float)
    if a <= 0 or lv.ndim != 2 or not len(lv):
        return [], []
    i = min(max(frame_of(t + offset, fps or E.FPS), 0), len(lv) - 1)
    row = np.zeros(lv.shape[1])
    for j in range(6):
        if i - j >= 0:
            row = np.maximum(row, lv[i - j] * release**j)
    x0, y0, x1, y1 = _frame(box, 0.08)
    u = _u()
    n = lv.shape[1]
    cy, half = (y0 + y1) / 2, (y1 - y0) / 2
    prims = []
    if style == "wave":
        xs = np.linspace(0, 1, n)
        fine = np.linspace(0, 1, n * 6)
        env = np.interp(fine, xs, row)
        env = np.convolve(np.pad(env, 8, mode="edge"), np.ones(9) / 9, mode="valid")[
            : len(fine)
        ]
        env = np.maximum(env * a * half, 3 * u)
        px = x0 + fine * (x1 - x0)
        up = [(float(x), cy - float(h)) for x, h in zip(px, env)]
        dn = [(float(x), cy + float(h)) for x, h in zip(px[::-1], env[::-1])]
        prims.append(("poly", up + dn, _mix(color, color2 or color, 0.5), 1.0))
        return _scale(prims, [], alpha)
    slot = (x1 - x0) / n
    bw = slot * (1 - gap)
    for b in range(n):
        h = max(float(row[b]) * a * (2 * half if style == "bars" else half), 4 * u)
        xa = x0 + b * slot + (slot - bw) / 2
        col = _mix(color, color2 or color, b / max(n - 1, 1))
        if style == "bars":
            prims.append(
                ("rect", (xa, y1 - h, xa + bw, y1), min(bw / 2, 12 * u), col, 1.0)
            )
        else:
            prims.append(
                ("rect", (xa, cy - h, xa + bw, cy + h), min(bw / 2, 12 * u), col, 1.0)
            )
    return _scale(prims, [], alpha)


audio_bars, audio_bars_items = _twins(_plan_audio, "audio_bars")


def _pcm(fmt, data):
    """(mono float samples, rate) of a WAV's fmt and data chunks: 8, 16, 24 and 32 bit PCM, 32 and 64 bit float."""
    tag, ch, rate, _, _, bits = struct.unpack("<HHIIHH", fmt[:16])
    if tag == 0xFFFE and len(fmt) >= 26:
        tag = struct.unpack("<H", fmt[24:26])[0]
    ch = max(ch, 1)
    if tag == 3 and bits in (32, 64):
        x = np.frombuffer(
            data[: len(data) // (bits // 8) * (bits // 8)],
            np.float32 if bits == 32 else np.float64,
        )
    elif tag == 1 and bits == 8:
        x = (np.frombuffer(data, np.uint8).astype(np.float64) - 128) / 128
    elif tag == 1 and bits == 16:
        x = np.frombuffer(data[: len(data) // 2 * 2], "<i2") / 32768
    elif tag == 1 and bits == 24:
        b = (
            np.frombuffer(data[: len(data) // 3 * 3], np.uint8)
            .reshape(-1, 3)
            .astype(np.int32)
        )
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = np.where(v >= 1 << 23, v - (1 << 24), v) / 8388608
    elif tag == 1 and bits == 32:
        x = np.frombuffer(data[: len(data) // 4 * 4], "<i4") / 2147483648
    else:
        raise ValueError(
            f"WAV format {tag} at {bits} bits is not readable (PCM 8 to 32 bit or float)"
        )
    x = np.asarray(x, np.float64)
    return x[: len(x) // ch * ch].reshape(-1, ch).mean(axis=1), rate


@lru_cache(maxsize=4)
def _analysed(path, digest, fps, bands):
    """analyse_wav's table for one file (its bytes, by digest), rate and band count. Read-only."""
    fmt, data = read_wav_chunks(path)
    x, sr = _pcm(fmt, data or b"")
    n = max(1, math.ceil(len(x) / sr * fps))
    win = 2048
    xp = np.pad(x, (win // 2, win // 2 + win))
    hann = np.hanning(win)
    freqs = np.fft.rfftfreq(win, 1 / sr)
    edges = np.geomspace(40.0, min(16000.0, sr / 2 * 0.95), bands + 1)
    lo = np.searchsorted(freqs, edges[:-1])
    hi = np.maximum(np.searchsorted(freqs, edges[1:]), lo + 1)
    tilt = 3 * np.log2(
        np.sqrt(edges[:-1] * edges[1:]) / 1000
    )  # dB: music falls about 3 dB an octave
    db = np.empty((n, bands))
    step = 256
    for s in range(0, n, step):
        idx = np.rint(np.arange(s, min(n, s + step)) / fps * sr).astype(np.int64)
        seg = xp[idx[:, None] + np.arange(win)[None, :]] * hann
        p = np.abs(np.fft.rfft(seg, axis=1)) ** 2
        for b in range(bands):
            db[s : s + len(idx), b] = 10 * np.log10(
                p[:, lo[b] : hi[b]].mean(axis=1) + 1e-12
            )
    db += tilt
    top = db.max()
    out = np.clip((db - (top - 50)) / 50, 0, 1) if top > -60 else np.zeros_like(db)
    out = out.astype(np.float32)
    out.flags.writeable = False
    return out


def analyse_wav(path, fps=None, bands=32):
    """Band levels of a WAV for audio_bars: a float32 array (frames, bands), 0 to 1, row i being the sound around
    frame i at fps (default the build's). Bands run 40 Hz to 16 kHz on a log scale, tilted 3 dB an octave, scaled so
    the loudest band of the file reaches 1 over a 50 dB range. Computed once per file contents, rate and band count
    (an lru_cache keyed by the bytes' digest), read-only. Call it once at import and pass the array to draw."""
    p = str(Path(path).resolve())
    digest = hashlib.sha1(Path(p).read_bytes()).hexdigest()
    return _analysed(p, digest, fps or E.FPS, int(bands))
