# blocks_text.py : text and UI blocks a scene drops in instead of hand-writing them (ideas only from public block
# registries; generic looks, no product or brand UI). Every block is a pure draw plus a registry twin.
"""Text and UI blocks. `name(img, t, ..., t0=..., dur=...)` draws onto the scene's canvas and returns it; the twin
`name_items(t, ...)` (same arguments, no img) returns the text_items(t) records for the same moment. Add the twin's
records to the scene's text_items(t) so the text gates see every word. Both read one private plan, so they cannot
drift. Timing is in seconds: the block starts at t0 and lasts dur (what dur spans is named in each docstring).
Colours are hex strings, parameters whose defaults are the constants below; size and position come from engine.W,
engine.H and engine.SS at call time.

Blocks:
  lower_third(img, t, name, role, style, ...)      name and role over the picture, 6 styles, each with an in and out
  captions(img, t, words, style, ...)              word-synced captions in 4 styles, fed by (word, start, end)
  caption_words(narration, line, offset)           the (word, start, end) list of a narration.json, a line or a dict
  marker(img, t, kind, box, ...)                   hand-drawn circle, underline, strike, cross or arrow, drawn on
  end_card(img, t, title, handle, nudge, ...)      title, handle and a follow nudge that pops in, then pulses
  chat_thread(img, t, messages, ...)               a generic chat that reveals message by message, with typing dots
  notification(img, t, title, body, ...)           a generic notification card that slides in, holds and leaves
  code_typing(img, t, code, lang, ...)             code typed character by character with a caret, Python or JS colours
  code_diff(img, t, old, new, lang, ...)           two versions of code: removed lines fade red, added lines grow in
Each has a `<name>_items` twin; marker's returns [] (it draws no text). Fonts: the code blocks use
JetBrains Mono (`python fonts.py fetch` once); everything else uses the engine's default fonts."""

import difflib
import itertools
import json
import math
import re
from pathlib import Path

import engine as E
from PIL import Image, ImageChops, ImageDraw

# the palette: same names as the template's. Pass your card's own colours to any block.
INK, PAPER, ACCENT, WHITE = "#101828", "#F7F3EA", "#FF6B4A", "#FFFFFF"
SHADE = "#0B1020"  # dark bars and outlines behind white text
SOFT = "#E8ECF4"  # a light bubble
MUTED = "#B9C3D6"  # words not yet sung
MUTED_DARK = "#475467"  # secondary text on a light card
PANEL = "#0F172A"  # the code window
RED_TINT, GREEN_TINT = "#FF5C70", "#3DDC97"
CODE_FONT = "JetBrains Mono:500"
CODE_COLOURS = {
    "plain": "#E6EAF2",
    "kw": "#C4A7FF",
    "str": "#8FE3A7",
    "num": "#FFC27A",
    "com": "#8A9BB8",
}

LOWER_THIRD_STYLES = (
    "clean_bar",
    "accent_underline",
    "side_rule",
    "soft_pill",
    "kicker",
    "stacked_bars",
)
CAPTION_STYLES = ("pill", "pop", "highlight", "karaoke")
MARKER_KINDS = ("circle", "underline", "strike", "cross", "arrow")

_AA = 3  # marker strokes are drawn this many times larger, then reduced
_MIN_ALPHA = 0.004  # under this the 8-bit alpha is 0 and nothing is drawn or reported


# ---- plan, draw, report: the one mechanism every block uses ----


def _rect(ops, box, r, fill, alpha=1.0):
    if alpha > _MIN_ALPHA and box[2] - box[0] >= 1 and box[3] - box[1] >= 1:
        ops.append({"k": "rect", "box": box, "r": r, "fill": fill, "alpha": alpha})


def _txt(ops, s, xy, size, fill, alpha, anchor="lm", bold=True, **kw):
    """One text op. kw: style ("outline" or "halo") with edge and edge_w, tracking, clip (0..1: only that left share is
    drawn), rec (False: drawn but not reported), texture (True: reported as decoration)."""
    if s and alpha > _MIN_ALPHA and size >= 4:
        ops.append(
            {"k": "text", "s": s, "xy": xy, "size": size, "fill": fill, "alpha": alpha}
            | {"anchor": anchor, "bold": bold}
            | kw
        )


def _text_clip(img, o):
    """The text of op o drawn only up to its left `clip` share (a karaoke fill), through a layer."""
    ss = E.SS
    l, t, r, b = E.text_box(
        o["s"], o["xy"], o["size"], o["anchor"], o["bold"], o.get("tracking", 0)
    )
    pad = 6
    x0, y0 = max(0, math.floor((l - pad) * ss)), max(0, math.floor((t - pad) * ss))
    x1 = min(img.width, math.ceil((r + pad) * ss))
    y1 = min(img.height, math.ceil((b + pad) * ss))
    if x1 <= x0 or y1 <= y0:
        return
    lay = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    xy = (o["xy"][0] - x0 / ss, o["xy"][1] - y0 / ss)
    E.text(
        lay,
        o["s"],
        xy,
        o["size"],
        o["fill"],
        o["anchor"],
        o["alpha"],
        o["bold"],
        1.0,
        o.get("tracking", 0),
    )
    cut = round(l * ss - x0 + (r - l) * ss * E.clamp(o["clip"]))
    mask = Image.new("L", lay.size, 0)
    mask.paste(255, (0, 0, max(0, min(lay.width, cut)), lay.height))
    lay.putalpha(ImageChops.multiply(lay.getchannel("A"), mask))
    img.alpha_composite(lay, (x0, y0))


def _draw_text(img, o):
    st = o.get("style")
    a = (img, o["s"], o["xy"], o["size"], o["fill"])
    if o.get("clip") is not None:
        _text_clip(img, o)
    elif st == "outline":
        E.text_outline(*a, o["edge"], o["edge_w"], o["anchor"], o["alpha"], o["bold"])
    elif st == "halo":
        E.text_halo(*a, o["edge"], o["edge_w"], 0.6, o["anchor"], o["alpha"], o["bold"])
    else:
        E.text(*a, o["anchor"], o["alpha"], o["bold"], 1.0, o.get("tracking", 0))


def _run(img, ops):
    for o in ops:
        k = o["k"]
        if k == "rect":
            E.rrect(img, o["box"], o["r"], o["fill"], o["alpha"])
        elif k == "shadow":
            E.shadow(img, o["box"], o["r"], o["blur"], o["dy"], o["alpha"])
        elif k == "stroke":
            _stroke(img, o["strokes"], o["width"], o["fill"], o["alpha"])
        else:
            _draw_text(img, o)
    return img


def _records(ops):
    """text_items(t) records of a plan: the string, its glyph box, colour, alpha and size, as the template reports."""
    out = []
    for o in ops:
        if o["k"] != "text" or o.get("rec") is False:
            continue
        l, t, r_, b = E.text_box(
            o["s"], o["xy"], o["size"], o["anchor"], o["bold"], o.get("tracking", 0)
        )
        l, t, r_, b = max(l, 0.0), max(t, 0.0), min(r_, E.W), min(b, E.H)
        if (
            r_ <= l or b <= t
        ):  # wholly off the frame (a card sliding in): nothing is seen
            continue
        r = {
            "s": o["s"],
            "box": (l, t, r_, b),
            "fg": o["fill"],
            "alpha": o["alpha"],
            "px": o["size"],
            "bold": o["bold"] is not False,
        }
        if o.get("texture"):
            r["texture"] = True
        out.append(r)
    return out


def _mix(a, b, k):
    """Hex colour k of the way from a to b."""
    ra, rb = E.hexrgb(a), E.hexrgb(b)
    return "#" + "".join(
        f"{round(x + (y - x) * k):02X}" for x, y in zip(ra[:3], rb[:3])
    )


def _inout(t, t0, dur, anim, ein=E.ease_out_cubic):
    """0 -> 1 over anim seconds from t0, held, then 1 -> 0 over the last anim seconds of dur (ease in for the out)."""
    a = max(1e-6, min(anim, dur / 2))
    k_out = E.ease_in_cubic(E.prog(t, t0 + dur - a, a))
    return ein(E.prog(t, t0, a)) * (1 - k_out)


def _stroke(img, strokes, width, fill, alpha=1.0):
    """Polylines (output px) with round caps and joins, anti-aliased by drawing _AA times larger then reducing."""
    pts = [p for s in strokes for p in s]
    if alpha <= _MIN_ALPHA or not pts:
        return
    ss, k = E.SS, _AA
    w = max(1.0, width * ss)
    pad = w / 2 + 2
    l = max(0, math.floor(min(p[0] for p in pts) * ss - pad))
    t = max(0, math.floor(min(p[1] for p in pts) * ss - pad))
    r = min(img.width, math.ceil(max(p[0] for p in pts) * ss + pad))
    b = min(img.height, math.ceil(max(p[1] for p in pts) * ss + pad))
    if r <= l or b <= t:
        return
    mask = Image.new("L", ((r - l) * k, (b - t) * k), 0)
    d = ImageDraw.Draw(mask)
    for s in strokes:
        q = [((x * ss - l) * k, (y * ss - t) * k) for x, y in s]
        if len(q) > 1:
            d.line(q, fill=255, width=max(1, round(w * k)), joint="curve")
        for x, y in q:
            d.ellipse(
                (x - w * k / 2, y - w * k / 2, x + w * k / 2, y + w * k / 2), fill=255
            )
    mask = mask.resize((r - l, b - t), Image.BOX)
    if alpha < 1:
        mask = mask.point(lambda v: int(v * alpha))
    lay = Image.new("RGBA", mask.size, E.hexrgb(fill)[:3] + (0,))
    lay.putalpha(mask)
    img.alpha_composite(lay, (l, t))


# ---- lower thirds ----


def _lt_plan(
    style, t, name, role, t0, dur, anim, xy, size, ink, bar, accent, paper, dark
):
    if style not in LOWER_THIRD_STYLES:
        raise ValueError(
            f"lower_third style {style!r}: use one of {', '.join(LOWER_THIRD_STYLES)}"
        )
    m = min(E.W, E.H)
    x, y = xy if xy else (m * 0.08, E.H * (0.84 if E.W >= E.H else 0.74))
    size = int(E.fit_size(name, size or m * 0.056, E.W * 0.86 - x - m * 0.1))
    rs = int(size * 0.64)
    p = _inout(t, t0, dur, anim)
    ta = E.clamp(
        (p - 0.35) / 0.65
    )  # the text arrives after its shape and leaves before it
    slide = (1 - ta) * size * 0.35
    wn = E.text_w(name, size, True)
    wr = E.text_w(role, rs, False) if role else 0.0
    pad, hn = size * 0.4, size * 1.3
    hr = rs * 1.35 if role else 0.0
    ops = []
    if style == "clean_bar":
        w, h = max(wn, wr) + 2 * pad + 12, hn + hr + 2 * pad
        top = y - h
        _rect(ops, (x, top, x + w * p, y), 10, bar, 0.88)
        _rect(ops, (x, top, x + min(12, w * p), y), 5, accent)
        tx = x + pad + 12 - slide
        _txt(ops, name, (tx, top + pad + hn / 2), size, ink, ta)
        _txt(ops, role, (tx, top + pad + hn + hr / 2), rs, accent, ta, bold=False)
    elif style == "accent_underline":
        ul = max(5, size * 0.1)
        top = y - (hn + ul + hr)
        edge = {"style": "halo", "edge": bar, "edge_w": 6}
        _txt(ops, name, (x - slide, top + hn / 2), size, ink, ta, **edge)
        _rect(ops, (x, top + hn - 2, x + wn * p, top + hn - 2 + ul), ul / 2, accent)
        _txt(
            ops,
            role,
            (x - slide, top + hn + ul + hr / 2),
            rs,
            ink,
            ta,
            bold=False,
            **edge,
        )
    elif style == "side_rule":
        h = hn + hr
        _rect(ops, (x, y - h * p, x + 8, y), 4, accent)
        edge = {"style": "halo", "edge": bar, "edge_w": 6}
        _txt(ops, name, (x + 28 - slide, y - h + hn / 2), size, ink, ta, **edge)
        _txt(ops, role, (x + 28 - slide, y - hr / 2), rs, ink, ta, bold=False, **edge)
    elif style == "soft_pill":
        h = size * 1.7
        gap = size * 0.7 if role else 0.0
        w = wn + wr + gap + pad * 3
        _rect(ops, (x, y - h, x + w * p, y), h / 2, paper, 0.95)
        cy, tx = y - h / 2 - slide * 0.4, x + pad * 1.5 - slide
        _txt(ops, name, (tx, cy), size, dark, ta)
        if role:
            d = size * 0.2
            dx = tx + wn + gap / 2
            _rect(
                ops,
                (dx - d / 2, y - h / 2 - d / 2, dx + d / 2, y - h / 2 + d / 2),
                d / 2,
                accent,
                ta,
            )
            _txt(ops, role, (tx + wn + gap, cy), rs, MUTED_DARK, ta, bold=False)
    elif style == "kicker":
        kick = role.upper()
        track = 3
        kb = E.text_box(kick, (0, 0), rs, "la", True, track) if kick else (0, 0, 0, 0)
        wk = kb[
            2
        ]  # tracked text is drawn from its top left: centre it on the chip by its measured box
        hk = rs * 1.7 if kick else 0.0
        top = y - hk - hn
        if kick:
            _rect(ops, (x, top, x + (wk + rs) * p, top + hk), hk / 2, accent)
            _txt(
                ops,
                kick,
                (x + rs / 2 - slide, top + hk / 2 - (kb[1] + kb[3]) / 2),
                rs,
                dark,
                ta,
                "la",
                tracking=track,
            )
        edge = {"style": "halo", "edge": bar, "edge_w": 6}
        _txt(
            ops,
            name,
            (x - slide, top + hk + hn / 2 + slide * 0.5),
            size,
            ink,
            ta,
            **edge,
        )
    else:  # stacked_bars
        p2 = E.clamp((p - 0.3) / 0.7)
        h1, h2 = hn + pad * 0.9, (hr + pad * 0.7 if role else 0.0)
        _rect(ops, (x, y - h1 - h2, x + (wn + 2 * pad) * p, y - h2), 6, bar, 0.92)
        _txt(
            ops,
            name,
            (x + pad - slide, y - h2 - h1 / 2),
            size,
            ink,
            E.clamp((p - 0.4) / 0.6),
        )
        if role:
            x2 = x + pad * 1.4
            _rect(ops, (x2, y - h2, x2 + (wr + 2 * pad) * p2, y), 6, accent)
            _txt(
                ops,
                role,
                (x2 + pad - slide, y - h2 / 2),
                rs,
                dark,
                E.clamp((p2 - 0.4) / 0.6),
                bold=False,
            )
    return ops


def lower_third(
    img,
    t,
    name,
    role="",
    style="clean_bar",
    t0=0.0,
    dur=4.0,
    anim=0.45,
    xy=None,
    size=None,
    ink=WHITE,
    bar=SHADE,
    accent=ACCENT,
    paper=PAPER,
    dark=INK,
):
    """A name (and a role) near the bottom left. style: clean_bar (dark bar with an accent edge), accent_underline (an
    accent line drawn under the name), side_rule (a rule that grows up the side), soft_pill (a light pill, name and
    role on one line), kicker (the role, uppercased, as a chip over the name), stacked_bars (name bar over a role bar).
    dur is the whole time on screen; the in and the out take anim seconds each (the shape moves first in, last out).
    xy is the bottom left of the block (default: left margin, 0.84 of the height; 0.74 in portrait); size the name's
    px. ink is the text colour on a dark ground, dark on a light one, bar the dark fill (and the halo behind
    text drawn straight on the picture)."""
    return _run(
        img,
        _lt_plan(
            style, t, name, role, t0, dur, anim, xy, size, ink, bar, accent, paper, dark
        ),
    )


def lower_third_items(
    t,
    name,
    role="",
    style="clean_bar",
    t0=0.0,
    dur=4.0,
    anim=0.45,
    xy=None,
    size=None,
    ink=WHITE,
    bar=SHADE,
    accent=ACCENT,
    paper=PAPER,
    dark=INK,
):
    """The text_items(t) records of lower_third with the same arguments (without img)."""
    return _records(
        _lt_plan(
            style, t, name, role, t0, dur, anim, xy, size, ink, bar, accent, paper, dark
        )
    )


# ---- word-synced captions ----


def caption_words(narration, line=None, offset=0.0):
    """[(word, start, end)] from a narration.json path, a loaded narration dict ({"lines": [...]}), a bare list of
    lines (voice.load_narration forms) or one line dict with "words". line: only the line with that id. offset moves
    every time (a line's words are in seconds of the narration file; add the scene's start if the audio starts later)."""
    if isinstance(narration, (str, Path)):
        narration = json.loads(Path(narration).read_text(encoding="utf-8"))
    if isinstance(narration, dict):
        narration = [narration] if "words" in narration else narration["lines"]
    out = []
    for ln in narration:
        if line is None or ln.get("id") == line:
            out += [
                (w["w"], w["start"] + offset, w["end"] + offset)
                for w in ln.get("words") or []
            ]
    return out


def _norm_words(words):
    if isinstance(words, (dict, str, Path)):
        words = caption_words(words)
    ws = [
        (w["w"], w["start"], w["end"]) if isinstance(w, dict) else (w[0], w[1], w[2])
        for w in words
    ]
    return sorted(ws, key=lambda w: w[1])


def _pages(ws, per_page, split_gap=0.6):
    """Words grouped into pages: per_page words, a sentence end, or a pause over split_gap seconds ends one. A page
    that is full runs one word over when the next word would stand alone on a page."""
    end = [
        i + 1 == len(ws)
        or w[0].rstrip().endswith((".", "?", "!"))
        or ws[i + 1][1] - w[2] > split_gap
        for i, w in enumerate(ws)
    ]
    pages, cur = [], []
    for i, w in enumerate(ws):
        cur.append(w)
        if end[i] or (len(cur) >= per_page and not end[i + 1]):
            pages.append(cur)
            cur = []
    return pages


def _page_spans(pages, lead, tail, join):
    """[(show_from, show_to, follows_directly, followed_directly)] per page. A page whose next word comes within `join`
    seconds stays until that word and the next page replaces it in the same frame; otherwise it fades after `tail`."""
    out = []
    for i, pg in enumerate(pages):
        s, e = pg[0][1], pg[-1][2]
        jp = i > 0 and s - pages[i - 1][-1][2] <= join
        jn = i + 1 < len(pages) and pages[i + 1][0][1] - e <= join
        b = pages[i + 1][0][1] if jn else e + tail
        if i + 1 < len(pages) and not jn:
            b = min(b, pages[i + 1][0][1] - lead)
        out.append((s if jp else s - lead, b, jp, jn))
    return out


def _cap_plan(
    t,
    words,
    style,
    xy,
    size,
    max_w,
    per_page,
    lead,
    tail,
    join,
    ink,
    accent,
    dark,
    pill,
    dim,
    edge,
):
    if style not in CAPTION_STYLES:
        raise ValueError(
            f"captions style {style!r}: use one of {', '.join(CAPTION_STYLES)}"
        )
    pages = _pages(_norm_words(words), per_page)
    page = None
    for pg, sp in zip(pages, _page_spans(pages, lead, tail, join)):
        if sp[0] <= t < sp[1]:
            page = (pg, sp)
    if page is None:
        return []
    pg, (a, b, jp, jn) = page
    ain = 1.0 if jp else E.smoothstep(E.prog(t, a, 0.1))
    al = ain * (1.0 if jn else 1 - E.smoothstep(E.prog(t, b - 0.12, 0.12)))
    m = min(E.W, E.H)
    size = int(size or m * 0.058)
    cx, yb = xy if xy else (E.W / 2, E.H * (0.82 if E.W >= E.H else 0.74))
    yb += (1 - ain) * size * 0.25
    max_w = max_w or E.W * 0.86
    gap, lh = size * 0.32, size * 1.38
    ww = [E.text_w(w[0], size, True) for w in pg]
    lines, row, rw = [], [], 0.0
    for i, w in enumerate(ww):
        if row and rw + gap + w > max_w:
            lines.append(row)
            row, rw = [], 0.0
        rw += w + (gap if row else 0.0)
        row.append(i)
    lines.append(row)
    pos, ext = {}, []
    for j, row in enumerate(lines):
        lw = sum(ww[i] for i in row) + gap * (len(row) - 1)
        x = cx - lw / 2
        cy = yb - lh * (len(lines) - 1 - j) - lh / 2
        ext.append((x, x + lw))
        for i in row:
            pos[i] = (x + ww[i] / 2, cy)
            x += ww[i] + gap
    cur = max((i for i, w in enumerate(pg) if w[1] <= t), default=None)
    ops = []
    if style == "pill":
        l, r = min(e[0] for e in ext), max(e[1] for e in ext)
        top, bot = yb - lh * len(lines), yb
        px, py = size * 0.5, size * 0.1
        _rect(
            ops,
            (l - px, top - py, r + px, bot + py),
            min((bot - top) / 2 + py, size * 0.8),
            pill,
            0.9 * al,
        )
    out = {"style": "outline", "edge": edge, "edge_w": max(3, size * 0.075)}
    for i, (w, s, e) in enumerate(pg):
        x, y = pos[i]
        is_cur = i == cur
        if style == "highlight" and is_cur:
            wk = E.ease_out_cubic(E.prog(t, s, 0.1))
            hx, hy = size * 0.16, size * 0.58
            _rect(
                ops,
                (
                    x - ww[i] / 2 - hx,
                    y - hy,
                    x - ww[i] / 2 - hx + (ww[i] + 2 * hx) * wk,
                    y + hy,
                ),
                size * 0.3,
                accent,
                al,
            )
    for i, (w, s, e) in enumerate(pg):
        x, y = pos[i]
        is_cur = i == cur
        if style == "pill":
            _txt(ops, w, (x, y), size, accent if is_cur else ink, al, "mm")
        elif style == "pop":
            bump = E.there_and_back(E.prog(t, s, 0.3))
            _txt(
                ops,
                w,
                (x, y - size * 0.05 * bump),
                size * (1 + 0.08 * bump),
                accent if is_cur else ink,
                al,
                "mm",
                **out,
            )
        elif style == "highlight":
            if is_cur:
                _txt(ops, w, (x, y), size, dark, al, "mm")
            else:
                _txt(ops, w, (x, y), size, ink, al, "mm", **out)
        else:  # karaoke
            fr = E.prog(t, s, max(e - s, 0.05))
            if fr >= 1:
                _txt(ops, w, (x, y), size, accent, al, "mm", **out)
            else:
                _txt(ops, w, (x, y), size, dim, al, "mm", **out)
                if fr > 0:
                    _txt(ops, w, (x, y), size, accent, al, "mm", clip=fr, rec=False)
    return ops


def captions(
    img,
    t,
    words,
    style="pill",
    xy=None,
    size=None,
    max_w=None,
    per_page=5,
    lead=0.12,
    tail=0.5,
    join=0.6,
    ink=WHITE,
    accent=ACCENT,
    dark=INK,
    pill=SHADE,
    dim=MUTED,
    edge=SHADE,
):
    """Word-synced captions. words: [(word, start, end)] in seconds, or anything caption_words() reads (a narration
    path, dict or line). Words are grouped into pages of up to per_page (a sentence end or a pause also ends one); a
    page shows from `lead` s before its first word until the next page's first word (hard cut in one frame, when it
    comes within `join` s) or until `tail` s after its last word (then it fades). style: pill (a rounded dark pill
    behind the page, the spoken word in the accent colour), pop (outlined words, the spoken one pops and takes the
    accent colour), highlight (an accent marker swipes onto the spoken word, drawn in dark), karaoke (each word fills
    left to right with the accent colour as it is said and stays filled). xy is the bottom centre of the block
    (default 0.82 of the height; 0.74 in portrait). Every word is its own record, so a page needs the reading hold
    of its words: pick a HOLD_PROFILE of "caption" and keep per_page to what the voice says in about 2 s."""
    return _run(
        img,
        _cap_plan(
            t,
            words,
            style,
            xy,
            size,
            max_w,
            per_page,
            lead,
            tail,
            join,
            ink,
            accent,
            dark,
            pill,
            dim,
            edge,
        ),
    )


def captions_items(
    t,
    words,
    style="pill",
    xy=None,
    size=None,
    max_w=None,
    per_page=5,
    lead=0.12,
    tail=0.5,
    join=0.6,
    ink=WHITE,
    accent=ACCENT,
    dark=INK,
    pill=SHADE,
    dim=MUTED,
    edge=SHADE,
):
    """The text_items(t) records of captions with the same arguments (without img): one per word on screen."""
    return _records(
        _cap_plan(
            t,
            words,
            style,
            xy,
            size,
            max_w,
            per_page,
            lead,
            tail,
            join,
            ink,
            accent,
            dark,
            pill,
            dim,
            edge,
        )
    )


# ---- hand-drawn markers ----


def _hand(pts, amp, seed):
    """pts with a light hand wobble: engine.wobble walked along the path, so the same stroke on every frame."""
    n = max(1, len(pts) - 1)
    out = []
    for i, (x, y) in enumerate(pts):
        dx, dy = E.wobble(i / n, amp, 3.0, seed)
        out.append((x + dx, y + dy))
    return out


def _line_pts(a, b, n=20):
    return [
        (E.lerp(a[0], b[0], i / n), E.lerp(a[1], b[1], i / n)) for i in range(n + 1)
    ]


def _marker_strokes(kind, box, width, amp, seed):
    if kind not in MARKER_KINDS:
        raise ValueError(f"marker kind {kind!r}: use one of {', '.join(MARKER_KINDS)}")
    l, t, r, b = box
    w, h = r - l, b - t
    if kind == "arrow":  # box is (tail x, tail y, head x, head y)
        c = ((l + r) / 2 - h * 0.22, (t + b) / 2 + w * 0.22)
        shaft = [
            (
                (1 - u) ** 2 * l + 2 * u * (1 - u) * c[0] + u * u * r,
                (1 - u) ** 2 * t + 2 * u * (1 - u) * c[1] + u * u * b,
            )
            for u in (i / 28 for i in range(29))
        ]
        (x0, y0), (x1, y1) = shaft[-4], shaft[-1]
        ang = math.atan2(y1 - y0, x1 - x0)
        hl = max(26.0, width * 5.5)
        barbs = [
            [
                (x1, y1),
                (x1 - hl * math.cos(ang + s * 0.5), y1 - hl * math.sin(ang + s * 0.5)),
            ]
            for s in (-1, 1)
        ]
        return [_hand(shaft, amp, seed)] + barbs
    pad = h * 0.3 + 6
    if kind == "circle":
        n, a0 = 64, -2.4
        pts = [
            (
                (l + r) / 2
                + (w / 2 * 1.04 + h * 0.3)
                * (1 + 0.07 * i / n)
                * math.cos(a0 + (2 * math.pi + 0.5) * i / n),
                (t + b) / 2
                + (h / 2 * 1.1 + h * 0.15)
                * (1 + 0.07 * i / n)
                * math.sin(a0 + (2 * math.pi + 0.5) * i / n),
            )
            for i in range(n + 1)
        ]
        return [_hand(pts, amp, seed)]
    if kind == "underline":
        y = b + width * 1.2 + 4
        return [
            _hand(
                _line_pts((l - pad * 0.3, y), (r + pad * 0.3, y + h * 0.05)), amp, seed
            )
        ]
    if kind == "strike":
        return [
            _hand(
                _line_pts(
                    (l - pad * 0.3, (t + b) / 2 + h * 0.04),
                    (r + pad * 0.3, (t + b) / 2 - h * 0.04),
                ),
                amp,
                seed,
            )
        ]
    return [  # cross
        _hand(_line_pts((l, t), (r, b)), amp, seed),
        _hand(_line_pts((r, t), (l, b)), amp, seed + 1),
    ]


def marker(
    img,
    t,
    kind,
    box,
    t0=0.0,
    dur=0.7,
    colour=ACCENT,
    width=None,
    hand=None,
    seed=0,
    t_out=None,
):
    """A hand-drawn mark that draws on over dur seconds from t0 (ease in and out), with a light wobble that is part of
    the stroke (it does not shake over time). kind: circle (a loose ring that overshoots), underline, strike (a line
    through), cross (an X over the box), arrow (box is then (tail x, tail y, head x, head y): a curved shaft, then
    the head). box is the (l, t, r, b) of what is marked, in output px: pass the text_box of the words. width: stroke
    px (default 0.7 percent of the short side), hand: wobble px (default 0.6 of the width), seed: another seed is
    another hand. t_out starts a 0.3 s fade-out. It draws no text, so marker_items is empty."""
    width = width or max(5.0, min(E.W, E.H) * 0.007)
    strokes = _marker_strokes(
        kind, box, width, width * 0.6 if hand is None else hand, seed
    )
    a = 1 - (E.prog(t, t_out, 0.3) if t_out is not None else 0.0)
    p = E.ease_in_out_quad(E.prog(t, t0, dur))
    total = sum(math.dist(u, v) for s in strokes for u, v in itertools.pairwise(s))
    left, cut = total * p, []
    for s in strokes:
        if left <= 0:
            break
        part = [s[0]]
        for u, v in itertools.pairwise(s):
            d = math.dist(u, v)
            if left >= d:
                part.append(v)
                left -= d
            else:
                f = left / d if d else 0.0
                part.append((E.lerp(u[0], v[0], f), E.lerp(u[1], v[1], f)))
                left = 0.0
                break
        cut.append(part)
    _stroke(img, cut, width, colour, a)
    return img


def marker_items(
    t,
    kind=None,
    box=None,
    t0=0.0,
    dur=0.7,
    colour=ACCENT,
    width=None,
    hand=None,
    seed=0,
    t_out=None,
):
    """marker draws no text: an empty list, so every block has its twin."""
    return []


# ---- end card ----


def _end_plan(t, title, handle, nudge, t0, dur, xy, ink, accent, dark):
    m = min(E.W, E.H)
    cx, cy = xy if xy else (E.W / 2, E.H / 2)
    ts = int(E.fit_size(title, m * 0.09, E.W * 0.84))
    hs, ns = int(max(36, ts * 0.52)), int(max(36, ts * 0.42))
    th, hh, ph = ts * 1.25, hs * 1.4 if handle else 0.0, ns * 2.0 if nudge else 0.0
    g = ts * 0.3
    total = th + g + 6 + (g + hh if handle else 0.0) + (g * 1.4 + ph if nudge else 0.0)
    y = cy - total / 2
    ops = []
    a = E.ease_out_expo(E.prog(t, t0, 0.4 * dur))
    _txt(ops, title, (cx, y + th / 2 + (1 - a) * 40), ts, ink, a, "mm")
    wt = min(E.text_w(title, ts, True) * 0.5, 320.0)
    e = E.ease_out_cubic(E.prog(t, t0 + 0.2 * dur, 0.35 * dur))
    _rect(
        ops, (cx - wt * e / 2, y + th + g, cx + wt * e / 2, y + th + g + 6), 3, accent
    )
    y += th + g + 6
    if handle:
        a = E.ease_out_cubic(E.prog(t, t0 + 0.35 * dur, 0.4 * dur))
        _txt(ops, handle, (cx, y + g + hh / 2 + (1 - a) * 24), hs, accent, a, "mm")
        y += g + hh
    if nudge:
        u = E.prog(t, t0 + 0.55 * dur, 0.45 * dur)
        s = E.ease_out_back(u)
        if t > t0 + dur:  # a slow pulse keeps the hold alive
            s *= 1 + 0.035 * E.there_and_back(((t - t0 - dur) % 1.8) / 1.8)
        pc = (cx, y + g * 1.4 + ph / 2)
        arm, thick, gap = ns * 0.34, ns * 0.12, ns * 0.5
        tw = E.text_w(nudge, ns, True)
        w = 2 * ns * 0.9 + arm * 2 + gap + tw
        al = E.clamp(u * 4)
        _rect(
            ops,
            (
                pc[0] - w * s / 2,
                pc[1] - ph * s / 2,
                pc[0] + w * s / 2,
                pc[1] + ph * s / 2,
            ),
            ph * s / 2,
            accent,
            al,
        )
        px = pc[0] - w * s / 2 + ns * 0.9 * s + arm * s
        for bx in (
            (px - arm * s, pc[1] - thick * s / 2, px + arm * s, pc[1] + thick * s / 2),
            (px - thick * s / 2, pc[1] - arm * s, px + thick * s / 2, pc[1] + arm * s),
        ):
            _rect(ops, bx, thick * s / 2, dark, al)
        _txt(ops, nudge, (px + (arm + gap) * s, pc[1]), ns * s, dark, al, "lm")
    return ops


def end_card(
    img,
    t,
    title,
    handle="",
    nudge="Follow for more",
    t0=0.0,
    dur=1.4,
    xy=None,
    ink=WHITE,
    accent=ACCENT,
    dark=INK,
):
    """The closing card: title (rises in), an accent rule that draws, the handle (as typed: pass "@name"), and a pill
    nudge with a plus that pops in (ease_out_back), then pulses slowly. dur is the entrance only (from t0); the card
    then holds to the end of its scene. xy is the centre of the stack (default the frame centre). ink is the title
    colour, accent the rule, handle and pill, dark the pill's text. Leave handle or nudge empty to drop it."""
    return _run(img, _end_plan(t, title, handle, nudge, t0, dur, xy, ink, accent, dark))


def end_card_items(
    t,
    title,
    handle="",
    nudge="Follow for more",
    t0=0.0,
    dur=1.4,
    xy=None,
    ink=WHITE,
    accent=ACCENT,
    dark=INK,
):
    """The text_items(t) records of end_card with the same arguments (without img)."""
    return _records(_end_plan(t, title, handle, nudge, t0, dur, xy, ink, accent, dark))


# ---- chat thread ----


def _sc(pt, c, s):
    """pt scaled by s around c."""
    return (c[0] + (pt[0] - c[0]) * s, c[1] + (pt[1] - c[1]) * s)


def _chat_plan(
    t, messages, t0, step, dur, typing, xy, width, size, me, them, ink, dots
):
    m = min(E.W, E.H)
    ts = int(size or m * 0.04)
    width = width or m * 0.9
    padx, pady, lh, gap = ts * 0.6, ts * 0.45, ts * 1.3, ts * 0.4
    rows = []
    for i, msg in enumerate(messages):
        who, s = msg[0], msg[1]
        if who not in ("me", "them"):
            raise ValueError(f"chat message {i}: who is {who!r}, use 'me' or 'them'")
        lines = E.wrap(s, ts, width * 0.74 - 2 * padx, False)
        bw = max(E.text_w(ln, ts, False) for ln in lines) + 2 * padx
        rows.append(
            (
                who,
                lines,
                msg[2] if len(msg) > 2 else t0 + i * step,
                bw,
                len(lines) * lh + 2 * pady,
            )
        )
    cx, top = xy if xy else (E.W / 2, None)
    if top is None:
        top = max(
            E.H * 0.06, (E.H - sum(r[4] for r in rows) - gap * (len(rows) - 1)) / 2
        )
    left, right = cx - width / 2, cx + width / 2
    ops, y = [], top
    for who, lines, at, bw, bh in rows:
        x0 = left if who == "them" else right - bw
        fill = them if who == "them" else me
        if typing and who == "them" and at - typing <= t < at:
            al = E.smoothstep(E.prog(t, at - typing, 0.15))
            dw, dh = ts * 2.3, ts * 1.5
            _rect(ops, (x0, y, x0 + dw, y + dh), dh / 2, fill, al)
            for j in range(3):
                bounce = max(0.0, math.sin(2 * math.pi * (t * 1.6 - j * 0.18)))
                dx, dy, d = (
                    x0 + dw / 2 + (j - 1) * ts * 0.5,
                    y + dh / 2 - bounce * ts * 0.22,
                    ts * 0.14,
                )
                _rect(ops, (dx - d, dy - d, dx + d, dy + d), d, MUTED_DARK, al)
        elif t >= at:
            a = E.ease_out_cubic(E.prog(t, at, dur * 0.6))
            s = E.lerp(0.8, 1.0, E.ease_out_back(E.prog(t, at, dur)))
            lift = (1 - a) * ts * 0.4
            corner = (x0 if who == "them" else x0 + bw, y + bh)
            p0, p1 = (
                _sc((x0, y + lift), corner, s),
                _sc((x0 + bw, y + bh + lift), corner, s),
            )
            _rect(ops, (p0[0], p0[1], p1[0], p1[1]), min(ts * 0.7, bh / 2) * s, fill, a)
            for j, ln in enumerate(lines):
                c = _sc((x0 + padx, y + lift + pady + j * lh + lh / 2), corner, s)
                _txt(ops, ln, c, ts * s, ink, a, "lm", bold=False)
        y += bh + gap
    return ops


def chat_thread(
    img,
    t,
    messages,
    t0=0.0,
    step=1.3,
    dur=0.4,
    typing=0.7,
    xy=None,
    width=None,
    size=None,
    me=ACCENT,
    them=SOFT,
    ink=INK,
):
    """A generic chat that reveals message by message. messages: [("them", "text"), ("me", "text"), ...] or with a third
    item, the message's own time (default t0 + index * step). A message pops in over dur seconds (scale, fade and a
    small rise) and stays; an incoming ("them") message is announced by typing dots for `typing` s before it (0 for
    none). Every bubble's slot is reserved, so nothing moves when one arrives. xy is (centre x, top) of the thread
    (default centred in the frame); width the column width (default 0.9 of the short side); me and them the bubble
    colours, ink the message colour (dark: keep both bubbles light or mid-tone)."""
    return _run(
        img,
        _chat_plan(
            t,
            messages,
            t0,
            step,
            dur,
            typing,
            xy,
            width,
            size,
            me,
            them,
            ink,
            MUTED_DARK,
        ),
    )


def chat_thread_items(
    t,
    messages,
    t0=0.0,
    step=1.3,
    dur=0.4,
    typing=0.7,
    xy=None,
    width=None,
    size=None,
    me=ACCENT,
    them=SOFT,
    ink=INK,
):
    """The text_items(t) records of chat_thread with the same arguments (without img): one per line of a message."""
    return _records(
        _chat_plan(
            t,
            messages,
            t0,
            step,
            dur,
            typing,
            xy,
            width,
            size,
            me,
            them,
            ink,
            MUTED_DARK,
        )
    )


# ---- notification card ----


def _note_plan(
    t,
    title,
    body,
    t0,
    dur,
    anim,
    xy,
    width,
    icon,
    stamp,
    card,
    ink,
    muted,
    accent,
    dark,
):
    m = min(E.W, E.H)
    ts = int(m * 0.04)
    bs, ss = int(ts * 0.88), int(ts * 0.7)
    width = width or m * 0.92
    pad, isz = ts * 0.7, ts * 1.7
    cx, top = xy if xy else (E.W / 2, m * 0.06)
    left = cx - width / 2
    tx = left + pad + isz + pad * 0.8
    maxw = left + width - pad - tx
    lines = E.wrap(body, bs, maxw, False) if body else []
    sw = E.text_w(stamp, ss, False) + pad if stamp else 0.0
    ts = int(E.fit_size(title, ts, maxw - sw))
    h = max(isz + 2 * pad, 2 * pad + ts * 1.3 + len(lines) * bs * 1.35)
    p = _inout(t, t0, dur, anim, ein=E.ease_out_back)
    oy = -(top + h + 60) * (
        1 - p
    )  # slides down from above, overshoots a little, leaves upward
    a = (
        E.clamp(p) ** 3
    )  # opaque only once in place, and gone before it leaves the frame
    y = top + oy
    ops = []
    if a > _MIN_ALPHA:
        ops.append(
            {
                "k": "shadow",
                "box": (left, y, left + width, y + h),
                "r": 22,
                "blur": 26,
                "dy": 12,
                "alpha": 0.32 * a,
            }
        )
    _rect(ops, (left, y, left + width, y + h), 22, card, a)
    ib = (left + pad, y + pad, left + pad + isz, y + pad + isz)
    _rect(ops, ib, isz * 0.28, accent, a)
    _txt(
        ops,
        icon or title[:1].upper(),
        ((ib[0] + ib[2]) / 2, (ib[1] + ib[3]) / 2),
        int(ts * 0.95),
        dark,
        a,
        "mm",
    )
    _txt(ops, title, (tx, y + pad + ts * 0.65), ts, ink, a, "lm")
    if stamp:
        _txt(
            ops,
            stamp,
            (left + width - pad, y + pad + ts * 0.65),
            ss,
            muted,
            a,
            "rm",
            bold=False,
            texture=True,
        )
    for j, ln in enumerate(lines):
        _txt(
            ops,
            ln,
            (tx, y + pad + ts * 1.3 + j * bs * 1.35 + bs * 0.675),
            bs,
            muted,
            a,
            "lm",
            bold=False,
        )
    return ops


def notification(
    img,
    t,
    title,
    body="",
    t0=0.0,
    dur=3.2,
    anim=0.5,
    xy=None,
    width=None,
    icon=None,
    stamp="now",
    card=PAPER,
    ink=INK,
    muted=MUTED_DARK,
    accent=ACCENT,
    dark=INK,
):
    """A generic notification card: a rounded icon tile (icon: 1 to 2 characters, default the title's first letter),
    a bold title, a small time stamp at the right (stamp "" drops it), and a wrapped body. It slides down from above the
    frame with a small overshoot at t0, holds, and slides up and away over the last anim seconds of dur. xy is
    (centre x, top) of the card (default top centre); width default 0.92 of the short side."""
    return _run(
        img,
        _note_plan(
            t,
            title,
            body,
            t0,
            dur,
            anim,
            xy,
            width,
            icon,
            stamp,
            card,
            ink,
            muted,
            accent,
            dark,
        ),
    )


def notification_items(
    t,
    title,
    body="",
    t0=0.0,
    dur=3.2,
    anim=0.5,
    xy=None,
    width=None,
    icon=None,
    stamp="now",
    card=PAPER,
    ink=INK,
    muted=MUTED_DARK,
    accent=ACCENT,
    dark=INK,
):
    """The text_items(t) records of notification with the same arguments (without img). The time stamp is reported as
    texture (decoration), the rest as text."""
    return _records(
        _note_plan(
            t,
            title,
            body,
            t0,
            dur,
            anim,
            xy,
            width,
            icon,
            stamp,
            card,
            ink,
            muted,
            accent,
            dark,
        )
    )


# ---- code: typing and diff ----

_KEYWORDS = {
    "python": frozenset(
        [
            "and",
            "as",
            "assert",
            "async",
            "await",
            "break",
            "class",
            "continue",
            "def",
            "del",
            "elif",
            "else",
            "except",
            "finally",
            "for",
            "from",
            "global",
            "if",
            "import",
            "in",
            "is",
            "lambda",
            "None",
            "not",
            "or",
            "pass",
            "raise",
            "return",
            "self",
            "True",
            "False",
            "try",
            "while",
            "with",
            "yield",
        ]
    ),
    "javascript": frozenset(
        [
            "async",
            "await",
            "break",
            "case",
            "catch",
            "class",
            "const",
            "continue",
            "default",
            "delete",
            "do",
            "else",
            "export",
            "extends",
            "false",
            "finally",
            "for",
            "from",
            "function",
            "if",
            "import",
            "in",
            "instanceof",
            "let",
            "new",
            "null",
            "of",
            "return",
            "static",
            "super",
            "switch",
            "this",
            "throw",
            "true",
            "try",
            "typeof",
            "undefined",
            "var",
            "void",
            "while",
            "yield",
        ]
    ),
}
_COMMENT = {"python": "#", "javascript": "//"}
_PIECE = re.compile(
    r"""(?P<str>"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?|`(?:\\.|[^`\\])*`?)|(?P<num>\b\d[\d_]*\.?\d*\b)|(?P<word>[A-Za-z_$][\w$]*)|(?P<sp>\s+)|(?P<other>.)"""
)


def _tokens(line, lang):
    """[(column, text, class)] of one line: class kw, str, num, com or plain. Neighbouring plain pieces join up to the
    next space, so `foo(a,` is one token; a string or comment keeps its inner spaces."""
    if lang not in _KEYWORDS:
        raise ValueError(f"code lang {lang!r}: use one of {', '.join(_KEYWORDS)}")
    out, i, mark = [], 0, _COMMENT[lang]
    while i < len(line):
        if line.startswith(mark, i):
            out.append((i, line[i:].rstrip(), "com"))
            break
        mt = _PIECE.match(line, i)
        kind, text = mt.lastgroup, mt.group()
        i = mt.end()
        if kind == "sp":
            continue
        cls = (
            "kw"
            if kind == "word" and text in _KEYWORDS[lang]
            else "plain"
            if kind in ("word", "other")
            else kind
        )
        if (
            out
            and cls == "plain"
            and out[-1][2] == "plain"
            and out[-1][0] + len(out[-1][1]) == mt.start()
        ):
            out[-1] = (out[-1][0], out[-1][1] + text, "plain")
        else:
            out.append((mt.start(), text, cls))
    return out


def _code_geom(lines, size, xy, mono):
    """(size, advance, pad, line height, panel box) for a block of lines, shrunk to fit the frame width."""
    m = min(E.W, E.H)
    cols = max((len(ln) for ln in lines), default=1)
    size = int(size or m * 0.04)
    while True:
        adv = E.text_w("M" * 20, size, mono) / 20
        pad = size * 0.9
        if size <= 20 or cols * adv + 2 * pad <= E.W * 0.9:
            break
        size -= 1
    lh = size * 1.5
    w, h = max(cols * adv + 2 * pad, m * 0.5), len(lines) * lh + 2 * pad
    cx, cy = xy if xy else (E.W / 2, E.H / 2)
    return size, adv, pad, lh, (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def _panel(ops, box, ap, panel):
    if ap > _MIN_ALPHA:
        ops.append(
            {
                "k": "shadow",
                "box": box,
                "r": 22,
                "blur": 30,
                "dy": 14,
                "alpha": 0.4 * ap,
            }
        )
    _rect(ops, box, 22, panel, ap)


def _typing_plan(t, code, lang, t0, dur, lead, xy, size, mono, pal, panel, caret):
    text = code.expandtabs(4).strip("\n")
    lines = text.split("\n")
    size, adv, pad, lh, box = _code_geom(lines, size, xy, mono)
    ap = E.smoothstep(E.prog(t, t0 - lead, max(min(lead, 0.3), 0.05)))
    ops = []
    _panel(ops, box, ap, panel)
    n = int(E.clamp((t - t0) / dur) * len(text) + 1e-9)
    start, cur = 0, (0, 0)
    for i, line in enumerate(lines):
        k = n - start
        if k >= 0:
            cur = (i, min(k, len(line)))
        if k < 0:
            break
        cy = box[1] + pad + i * lh + lh / 2
        for col, tok, cls in _tokens(line, lang):
            if col >= k:
                break
            piece = tok[: k - col].rstrip()
            _txt(
                ops,
                piece,
                (box[0] + pad + col * adv, cy),
                size,
                pal[cls],
                ap,
                "lm",
                mono,
                texture=len(piece) < len(tok),
            )
        start += len(line) + 1
    on = 0 < n < len(text) or math.floor((t - t0) * 2) % 2 == 0
    if on:
        i, col = cur
        cy = box[1] + pad + i * lh + lh / 2
        cx = box[0] + pad + col * adv
        _rect(
            ops,
            (cx, cy - size * 0.62, cx + max(2.0, size * 0.1), cy + size * 0.62),
            1,
            caret,
            ap,
        )
    return ops


def code_typing(
    img,
    t,
    code,
    lang="python",
    t0=0.0,
    dur=3.0,
    lead=0.4,
    xy=None,
    size=None,
    mono=CODE_FONT,
    palette=CODE_COLOURS,
    panel=PANEL,
    caret=ACCENT,
):
    """Code typed in order, character by character, into a dark window with a caret. lang: python or javascript
    (keywords, strings, numbers and comments are coloured per line; nothing else is parsed). The typing runs from
    t0 over dur seconds (a newline counts as a key) and the finished code holds; the window fades in `lead` s before t0.
    The caret is solid while typing and blinks after. xy is the window centre (default the frame centre); size the
    code px (default 4 percent of the short side, shrunk until the longest line fits 90 percent of the width). mono
    is an engine font spec for a monospaced face, palette a dict with plain, kw, str, num, com. A token still being
    typed is reported as texture; each finished token is a record that needs its own reading hold, so leave the
    finished code up for a second or more."""
    return _run(
        img,
        _typing_plan(
            t, code, lang, t0, dur, lead, xy, size, mono, palette, panel, caret
        ),
    )


def code_typing_items(
    t,
    code,
    lang="python",
    t0=0.0,
    dur=3.0,
    lead=0.4,
    xy=None,
    size=None,
    mono=CODE_FONT,
    palette=CODE_COLOURS,
    panel=PANEL,
    caret=ACCENT,
):
    """The text_items(t) records of code_typing with the same arguments (without img): one per token typed so far."""
    return _records(
        _typing_plan(
            t, code, lang, t0, dur, lead, xy, size, mono, palette, panel, caret
        )
    )


def _diff_rows(old, new):
    """[(kind, text)] with kind keep, del or add, in unified-diff order (removed lines before the lines that replace them)."""
    a, b = (
        old.expandtabs(4).strip("\n").split("\n"),
        new.expandtabs(4).strip("\n").split("\n"),
    )
    rows = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(
        None, a, b, autojunk=False
    ).get_opcodes():
        if op == "equal":
            rows += [("keep", x) for x in a[i1:i2]]
        else:
            rows += [("del", x) for x in a[i1:i2]] + [("add", x) for x in b[j1:j2]]
    return rows, a, b


def _diff_plan(
    t, old, new, lang, t0, dur, lead, xy, size, mono, pal, panel, red, green
):
    rows, a, b = _diff_rows(old, new)
    # the window fits the longest line and the taller version, so it does not move while lines come and go
    cols = max(len(x) for _, x in rows)
    size, adv, pad, lh, box = _code_geom(
        ["x" * cols] * max(len(a), len(b)), size, xy, mono
    )
    u = E.prog(t, t0, dur)
    ap = E.smoothstep(E.prog(t, t0 - lead, 0.3))
    ops = []
    _panel(ops, box, ap, panel)
    y, x = box[1] + pad, box[0] + pad
    for kind, line in rows:
        tint, h, ta, strip = 0.0, 1.0, 1.0, 0.0
        if kind == "del":
            tint = E.ease_out_cubic(E.prog(u, 0.0, 0.2))
            ta = 1 - E.prog(u, 0.2, 0.2)
            h = 1 - E.ease_in_out_quad(E.prog(u, 0.4, 0.15))
            strip = 0.28 * tint
        elif kind == "add":
            h = E.ease_in_out_quad(E.prog(u, 0.5, 0.15))
            ta = E.prog(u, 0.65, 0.22)
            strip = 0.28 * h * (1 - E.prog(u, 0.87, 0.13))
        if h > 0.001:
            col = red if kind == "del" else green
            _rect(
                ops,
                (box[0] + pad * 0.4, y, box[2] - pad * 0.4, y + h * lh),
                6,
                col,
                strip * ap,
            )
            for c, tok, cls in _tokens(line, lang):
                fill = _mix(pal[cls], red, 0.6 * tint) if kind == "del" else pal[cls]
                _txt(
                    ops, tok, (x + c * adv, y + lh / 2), size, fill, ta * ap, "lm", mono
                )
        y += h * lh
    return ops


def code_diff(
    img,
    t,
    old,
    new,
    lang="python",
    t0=1.0,
    dur=2.4,
    lead=1.0,
    xy=None,
    size=None,
    mono=CODE_FONT,
    palette=CODE_COLOURS,
    panel=PANEL,
    red=RED_TINT,
    green=GREEN_TINT,
):
    """The change between two versions of some code (difflib, line by line). Before t0 the window shows old; from t0
    over dur seconds the removed lines tint red and fade out, their rows close up, the new rows open and the added
    lines fade in with a green tint that settles, so it ends showing new. The window fades in `lead` s before t0 and
    is sized for the taller version. xy, size, mono, palette, panel as code_typing. Text appears in the registry only
    while its row is open, and each line of old needs a reading hold before t0, so give lead 1 s or more."""
    return _run(
        img,
        _diff_plan(
            t, old, new, lang, t0, dur, lead, xy, size, mono, palette, panel, red, green
        ),
    )


def code_diff_items(
    t,
    old,
    new,
    lang="python",
    t0=1.0,
    dur=2.4,
    lead=1.0,
    xy=None,
    size=None,
    mono=CODE_FONT,
    palette=CODE_COLOURS,
    panel=PANEL,
    red=RED_TINT,
    green=GREEN_TINT,
):
    """The text_items(t) records of code_diff with the same arguments (without img): one per token on screen."""
    return _records(
        _diff_plan(
            t, old, new, lang, t0, dur, lead, xy, size, mono, palette, panel, red, green
        )
    )
