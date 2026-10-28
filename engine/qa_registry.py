# qa_registry.py : what draw(t) really paints against what text_items(t) reports (Q204 to Q206, Q208, Q209).
# A recorder patches PIL around scenes.draw(t) only. It logs every ImageDraw.text call (string, ink box with its
# stroke, glyph box, fill alpha, font size, stroke width, the image it drew on), and every crop, resize, paste and
# composite carries those records to where they land, so text drawn on a tile, a cached sprite or a window layer is
# still found on the frame. qa.py and proof.py labels are drawn outside the recorder and are never logged.
import contextlib
import importlib.util
import itertools
import math
import multiprocessing
import os
import sys
import time
import weakref

import contract as C
import numpy as np
from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageText

# Frames sampled: every one inside a transition or caption changeover, and one every GRID seconds elsewhere.
GRID = 0.25
# Q204 is a FIX only for text at least this opaque and this big (px at 1080 on the short side).
READ_ALPHA, READ_PX = 0.5, 24
BOX_PX = 2  # Q205: a box from engine.text_box must sit within this many px of the drawn glyph box
HAND_EM = 0.6  # Q205: a hand-made box may reach this far past the glyph box, in em (the template's is +/- 0.55 em)
EXPOSED = 0.7  # Q206: a registered text with less of its ink exposed than this is covered (OVH textcheck)
CHANGED = 8  # Q206: a pixel is the text's when drawing the frame without it moves a channel by this many levels
SEEN = 0.25  # a drawn box with less of its area on the frame than this (off screen, clipped away) is not counted
REFINE = 20  # Q204 walks the span edges of this many unreported strings a frame at a time (the rest keep the grid)

# ---- the recorder ----

_R = None  # the active Recorder while one draw(t) runs; the hooks pass straight through while it is None
# creation order of records (a word drawn letter by letter is in order) and serials of the images drawn on
_SEQ, _LAYERS = itertools.count(), itertools.count(1)


class Rec:
    """One ImageDraw.text call. Its boxes are in the pixels of the image it drew on (its layer)."""

    __slots__ = (
        "alpha",  # fill opacity 0..1 (the value itself on an L mask)
        "font",  # (path, size, index): calls of one word share it
        "frame",  # which draw(t) call made it; -1 while scenes.py was imported
        "glyph",  # textbbox without the stroke: what engine.text_box reports for the same call
        "ink",  # textbbox with the stroke: every pixel the call can touch
        "layer",  # serial of the image drawn on
        "lref",  # weak reference to that image (for the ink mask of a cached tile)
        "mask",  # (x0, y0, bool array): this call's own ink in layer px, kept from the call on
        "s",  # the string
        "seq",
        "sig",  # (call signature, occurrence): how the differential pass finds this call again
        "size",  # font size in layer px
        "stroke",  # stroke width in layer px
        "xy",  # the anchor point it was drawn at
    )


class Frame:
    """What one draw(t) call put on screen. lands: [(rec, (ox, oy, sx, sy, clip, opacity))], each record's layer px
    mapped to output px; lost: records on screen at an unknown place (rotated); loose: calls that never reached a
    frame-sized image, matched by their string alone.
    When the image draw(t) returns still carries records, exactly what reached it is on screen: a frame-sized
    scratch layer (a cached end card not shown yet) and a tile made but clipped away do not count, so the answer
    never depends on what a cache already held. When the chain broke (the frame came back through numpy: a
    motion-blur average, a numpy compositor), every record that reached a frame-sized image counts, and so does
    every call that never did (text masks composited in numpy)."""

    def __init__(self, R, img):
        self.calls, self.skipped = R.calls, R.skipped
        at = _at(img)
        k = R.canvas(img) if at is not None else 0
        if k:
            lands, self.lost, self.loose = {}, [], []
            for rec, ox, oy, sx, sy, c, op in at:
                if ox is None:
                    self.lost.append(rec)
                    continue
                m = (ox / k, oy / k, sx / k, sy / k, tuple(v / k for v in c), op)
                key = (id(rec), round(m[0], 1), round(m[1], 1), round(m[2], 4))
                lands[key] = (rec, m)
            self.lands = list(lands.values())
        else:
            self.lands, self.lost = list(R.lands.values()), R.lost
            on = {id(r) for r, _ in self.lands} | {id(r) for r in self.lost}
            self.loose = [r for r in self.calls if id(r) not in on]


class Recorder:
    """State for the hooks: the frame size, what the current draw(t) call drew, and what the differential skips."""

    def __init__(self, W, H):
        self.W, self.H = W, H
        self.depth = 0  # above 0 inside a hooked PIL call: PIL's own inner calls are not counted twice
        self.serial = 0
        self.total = 0  # text calls seen inside draw(t) over the whole run
        self.begin(-1)

    def begin(self, frame, skip=None):
        self.frame = frame
        self.skip_sig, self.skip_rec = skip or (set(), set())
        self.calls, self.lost, self.lands, self.counts, self.skipped = [], [], {}, {}, 0

    def canvas(self, im):
        """k when im is the frame at k times its size (the supersampled canvas, or the finished frame at k = 1)."""
        w, h = im.size
        k = w // self.W
        return k if 0 < k <= 8 and w == k * self.W and h == k * self.H else 0


def _call(R, f, *a, **k):
    R.depth += 1
    try:
        return f(*a, **k)
    finally:
        R.depth -= 1


def _at(im):
    """The records an image carries: [(rec, ox, oy, sx, sy, clip, opacity)], each rec's layer px mapped into this
    image, clip the part of it that shows, opacity what blends and composites left of it."""
    return getattr(im, "_zt_at", None) if isinstance(im, Image.Image) else None


def _isect(a, b):
    l, t, r, b_ = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    return (l, t, r, b_) if r > l and b_ > t else None


def _land(R, p, k):
    """A record reached a frame-sized image: keep its mapping to output px, one entry per placement. A later
    composition of the same placement replaces it (a scene canvas, then the crossfade that dims it)."""
    if R.frame < 0:
        return
    rec, ox, oy, sx, sy, c, op = p
    if ox is None:
        R.lost.append(rec)
        return
    m = (ox / k, oy / k, sx / k, sy / k, tuple(v / k for v in c), op)
    R.lands[(id(rec), round(m[0], 1), round(m[1], 1), round(m[2], 4))] = (rec, m)


def _carry(R, dst, at, ox=0.0, oy=0.0, sx=1.0, sy=1.0, clip=None, op=1.0):
    """Give dst the records in at, mapped by x' = x * sx + ox and y' = y * sy + oy. clip is the part of the source
    that was used (a crop or a source box, in the source's px), or a function of the place giving that box, None for
    no limit or False when nothing of it shows (a composite's mask). ox None: the geometry is lost (rotate,
    transform). op scales each record's opacity: a number (a blend's weight) or a function of the place."""
    have = getattr(dst, "_zt_at", None) or []
    index = {(id(p[0]),) + tuple(p[1:5]): j for j, p in enumerate(have)}
    k = R.canvas(dst)
    for p in at:
        rec, px, py, psx, psy, pc, pop = p
        f = op(p) if callable(op) else op
        if px is None or ox is None:
            q = (rec, None, None, None, None, None, pop * f)
        else:
            cl = clip(p) if callable(clip) else clip
            if cl is False:
                continue
            c = _isect(pc, cl) if cl is not None else pc
            if c is None:
                continue
            c = _isect(
                (c[0] * sx + ox, c[1] * sy + oy, c[2] * sx + ox, c[3] * sy + oy),
                (0, 0) + dst.size,
            )
            if c is None:
                continue
            q = (rec, px * sx + ox, py * sy + oy, psx * sx, psy * sy, c, pop * f)
        key = (id(rec),) + tuple(q[1:5])
        if key in index:  # the same text placed again: the latest composition counts
            have[index[key]] = q
        else:
            index[key] = len(have)
            have.append(q)
        if k:
            _land(R, q, k)
    dst._zt_at = have


def _layer_id(im):
    i = getattr(im, "_zt_id", None)
    if i is None:
        i = im._zt_id = next(_LAYERS)
    return i


def _alpha(fill, mode):
    """Opacity 0..1 of a fill on a draw of this mode: the 4th channel on RGBA, the value itself on an L mask."""
    if fill is None:
        return 1.0
    if isinstance(fill, str):
        try:
            fill = ImageColor.getcolor(
                fill, mode if mode in ("RGBA", "LA", "L", "RGB") else "RGBA"
            )
        except ValueError:
            return 1.0
    if isinstance(fill, (int, float)):
        return min(1.0, max(0.0, fill / 255)) if mode == "L" else 1.0
    fill = tuple(fill)
    if mode in ("RGBA", "PA") and len(fill) == 4:
        return fill[3] / 255
    if mode == "LA" and len(fill) == 2:
        return fill[1] / 255
    if mode == "L" and fill:
        return fill[0] / 255
    return 1.0


_TEXT_ARGS = (
    "fill",
    "font",
    "anchor",
    "spacing",
    "align",
    "direction",
    "features",
    "language",
    "stroke_width",
    "stroke_fill",
    "embedded_color",
)


def _rec(R, d, lay, xy, text, p, font_size):
    """The Rec for one call (an ImageText.Text or a string, any font_size), or None when the differential pass
    skips this call."""
    tt = isinstance(text, ImageText.Text)
    s = text.text if tt else text
    s = s.decode("latin-1") if isinstance(s, bytes) else str(s)
    f = text.font if tt else p.get("font") or d._getfont(font_size)
    stroke = (text.stroke_width if tt else p.get("stroke_width")) or 0
    anchor, align = p.get("anchor"), p.get("align", "left")
    try:
        if tt:
            ink = text.get_bbox(xy, anchor, align)
            plain = ImageText.Text(
                text.text,
                text.font,
                text.mode,
                text.spacing,
                text.direction,
                text.features,
                text.language,
            )
            glyph = plain.get_bbox(xy, anchor, align) if stroke else ink
        else:
            kw = {
                "font": f,
                "anchor": anchor,
                "spacing": p.get("spacing", 4),
                "align": align,
                "direction": p.get("direction"),
                "features": p.get("features"),
                "language": p.get("language"),
                "embedded_color": p.get("embedded_color", False),
            }
            ink = d.textbbox(xy, text, stroke_width=stroke, **kw)
            glyph = d.textbbox(xy, text, **kw) if stroke else ink
    except (ValueError, TypeError, OSError, AttributeError):
        # a font or mode textbbox cannot measure: the call still counts, without a box
        ink = glyph = None
    size = getattr(f, "size", None) or getattr(getattr(f, "font", None), "size", None)
    path = getattr(f, "path", None)
    if not isinstance(
        path, str
    ):  # load_default(size) makes a new font from bytes per call
        try:
            path = f.getname()
        except (AttributeError, OSError):
            path = type(f).__name__
    fk = (path, size, getattr(f, "index", 0))
    x, y = float(xy[0]), float(xy[1])
    sig = (s, round(x, 2), round(y, 2), anchor, fk, stroke, lay.size if lay else None)
    n = R.counts[sig] = R.counts.get(sig, 0) + 1
    if (sig, n) in R.skip_sig:
        R.skipped += 1
        return None
    r = Rec()
    r.s, r.xy, r.ink, r.glyph, r.size, r.stroke, r.font = (
        s,
        (x, y),
        ink,
        glyph,
        size,
        stroke,
        fk,
    )
    r.alpha = _alpha(p.get("fill"), d.mode)
    if stroke and p.get("stroke_fill") is not None:
        r.alpha = max(r.alpha, _alpha(p.get("stroke_fill"), d.mode))
    r.layer, r.lref = (
        (_layer_id(lay), weakref.ref(lay)) if lay is not None else (0, None)
    )
    r.seq, r.sig, r.frame, r.mask = next(_SEQ), (sig, n), R.frame, None
    return r


def _ibox(b, size):
    """A float box widened to whole px and clipped to an image of this size, or None when nothing is left."""
    return _isect(
        (
            math.floor(b[0]) - 1,
            math.floor(b[1]) - 1,
            math.ceil(b[2]) + 1,
            math.ceil(b[3]) + 1,
        ),
        (0, 0) + size,
    )


def _px(im, box):
    return np.asarray(_CROP(im, box))


def _snap(lay, b):
    """The layer's pixels under a call's ink box, before the call."""
    if lay is None or b is None:
        return None
    ib = _ibox(b, lay.size)
    return (ib, _px(lay, ib).astype(np.int16)) if ib else None


def _ink_of(lay, before):
    """(x0, y0, bool mask) of the pixels one call changed: its own ink even on a layer shared with other text."""
    ib, a0 = before
    a1 = _px(lay, ib).astype(np.int16)
    d = np.abs(a1 - a0)
    if d.ndim == 3:
        d = (
            d[..., -1]
            if lay.mode in ("RGBA", "LA", "PA") and d[..., -1].any()
            else d.max(2)
        )
    top = d.max() if d.size else 0
    return (ib[0], ib[1], d >= max(1, top // 2)) if top else None


def _lazy_mask(rec):
    """The ink of a record whose call kept no mask (no box was measurable then): its layer's alpha or value under
    its box, while that layer is still alive."""
    lay = rec.lref() if rec.lref else None
    if lay is None or rec.ink is None or lay.mode not in ("RGBA", "LA", "PA", "L"):
        return None
    ib = _ibox(rec.ink, lay.size)
    if not ib:
        return None
    a = _px(lay, ib)
    a = a[..., -1] if a.ndim == 3 else a
    top = int(a.max()) if a.size else 0
    return (ib[0], ib[1], a >= max(1, top // 2)) if top else None


def _place(R, rec, lay):
    """Log the call on the image it drew on; a call on the frame-sized canvas has landed already."""
    if R.frame >= 0:
        R.calls.append(rec)
        R.total += 1
    if lay is None:
        return
    p = (rec, 0.0, 0.0, 1.0, 1.0, (0, 0) + lay.size, 1.0)
    at = getattr(lay, "_zt_at", None)
    if at is None:
        at = lay._zt_at = []
    at.append(p)
    k = R.canvas(lay)
    if k:
        _land(R, p, k)


# ---- the hooks: each wraps one PIL entry point while installed() is active ----


def _hook_text(orig):
    def text(self, xy, text, *a, **k):
        R = _R
        if R is None or R.depth:
            return orig(self, xy, text, *a, **k)
        p = dict(zip(_TEXT_ARGS, a))
        p.update((n, k[n]) for n in _TEXT_ARGS if n in k)
        lay = getattr(self, "_image", None)  # Pillow 13 keeps the drawn-on image here
        rec = _rec(R, self, lay, xy, text, p, k.get("font_size"))
        if rec is None:
            return None
        before = _snap(
            lay, rec.ink
        )  # always: a cached tile's helper layer is gone by the time Q206 needs it
        _call(R, orig, self, xy, text, *a, **k)
        if before is not None:
            rec.mask = _ink_of(lay, before)
        _place(R, rec, lay)

    return text


def _hook_same(orig):
    """copy, convert, filter, point, getchannel: the result keeps the source's records where they were."""

    def f(self, *a, **k):
        R = _R
        if R is None or R.depth:
            return orig(self, *a, **k)
        out = _call(R, orig, self, *a, **k)
        at = _at(self)
        if at and isinstance(out, Image.Image):
            _carry(R, out, at)
        return out

    return f


def _hook_split(orig):
    def split(self):
        R = _R
        if R is None or R.depth:
            return orig(self)
        out = _call(R, orig, self)
        at = _at(self)
        for b in out if at else ():
            _carry(R, b, at)
        return out

    return split


def _hook_crop(orig):
    def crop(self, box=None):
        R = _R
        if R is None or R.depth:
            return orig(self, box)
        out = _call(R, orig, self, box)
        at = _at(self)
        if at:
            b = tuple(box) if box is not None else (0, 0) + self.size
            _carry(R, out, at, -b[0], -b[1], clip=b)
        return out

    return crop


def _scaled(R, src, out, box):
    at = _at(src)
    if at:
        b = tuple(box) if box is not None else (0, 0) + src.size
        sx, sy = out.width / (b[2] - b[0]), out.height / (b[3] - b[1])
        _carry(R, out, at, -b[0] * sx, -b[1] * sy, sx, sy, clip=b)


def _hook_resize(orig):
    def resize(self, size, resample=None, box=None, reducing_gap=None):
        R = _R
        if R is None or R.depth:
            return orig(self, size, resample, box, reducing_gap)
        out = _call(R, orig, self, size, resample, box, reducing_gap)
        _scaled(R, self, out, box)
        return out

    return resize


def _hook_reduce(orig):
    def reduce(self, factor, box=None):
        R = _R
        if R is None or R.depth:
            return orig(self, factor, box)
        out = _call(R, orig, self, factor, box)
        _scaled(R, self, out, box)
        return out

    return reduce


def _hook_lost(orig):
    """rotate, transform, transpose: the records go along, but where they end up is no longer known."""

    def f(self, *a, **k):
        R = _R
        if R is None or R.depth:
            return orig(self, *a, **k)
        out = _call(R, orig, self, *a, **k)
        at = _at(self)
        if at and isinstance(out, Image.Image):
            _carry(R, out, at, None)
        return out

    return f


def _skipped(R, at):
    """True when the differential pass removes text these records belong to (a cached tile or sprite)."""
    if at and R.skip_rec and any(p[0] in R.skip_rec for p in at):
        R.skipped += 1
        return True
    return False


def _hook_paste(orig):
    def paste(self, im, box=None, mask=None):
        R = _R
        if R is None or R.depth:
            return orig(self, im, box, mask)
        if isinstance(box, Image.Image) and mask is None:  # the paste(im, mask) form
            box, mask = None, box
        at = (_at(im) or []) + (_at(mask) or [])
        if _skipped(R, at):
            return None
        _call(R, orig, self, im, box, mask)
        if at:
            _carry(R, self, at, *((box[0], box[1]) if box is not None else (0, 0)))

    return paste


def _hook_alpha_composite(orig):
    def alpha_composite(self, im, dest=(0, 0), source=(0, 0)):
        R = _R
        if R is None or R.depth:
            return orig(self, im, dest, source)
        at = _at(im)
        if _skipped(R, at):
            return None
        _call(R, orig, self, im, dest, source)
        if at:
            s = tuple(source) if len(source) == 4 else tuple(source) + im.size
            _carry(R, self, at, dest[0] - s[0], dest[1] - s[1], clip=s)

    return alpha_composite


def _hook_putalpha(orig):
    def putalpha(self, alpha):
        R = _R
        if R is None or R.depth:
            return orig(self, alpha)
        _call(R, orig, self, alpha)
        at = _at(alpha)
        if at:
            _carry(R, self, at)

    return putalpha


def _hook_alpha_composite_fn(orig):
    """Image.alpha_composite(a, b): b over a; with b's text skipped it returns a copy of a."""

    def alpha_composite(im1, im2):
        R = _R
        if R is None or R.depth:
            return orig(im1, im2)
        if _skipped(R, _at(im2)):
            return im1.copy()
        out = _call(R, orig, im1, im2)
        for im in (im1, im2):
            if _at(im):
                _carry(R, out, _at(im))
        return out

    return alpha_composite


def _hook_blend(orig):
    """Image.blend(a, b, alpha), ImageChops.blend: a's texts keep 1 - alpha of their opacity and b's keep alpha (a
    crossfade, a dip through a colour)."""

    def blend(im1, im2, alpha):
        R = _R
        if R is None or R.depth:
            return orig(im1, im2, alpha)
        out = _call(R, orig, im1, im2, alpha)
        for im, w in ((im1, 1 - alpha), (im2, alpha)):
            if _at(im):
                _carry(R, out, _at(im), op=min(1.0, max(0.0, w)))
        return out

    return blend


def _shown(mask, p, white):
    """(clip, opacity) a composite mask leaves a placed record: the box, in the source's px, around the part of the
    record's box the mask shows (0.5 or more of the white image, under 0.5 for the black one), and the mask's mean
    over that part. (False, 0.0) when it shows none of it; (None, 1.0) when the record has no box to read."""
    rec, px, py, sx, sy = p[:5]
    b = rec.glyph or rec.ink
    if b is None or px is None:
        return None, 1.0
    ib = _ibox(
        (b[0] * sx + px, b[1] * sy + py, b[2] * sx + px, b[3] * sy + py), mask.size
    )
    if not ib:
        return False, 0.0
    a = _px(mask if mask.mode in ("L", "1") else mask.getchannel("A"), ib)
    a = a.astype(np.float32) / (1 if a.dtype == bool else 255)
    a = a if white else 1 - a
    on = a >= 0.5
    if not on.any():
        return False, 0.0
    ys, xs = np.nonzero(on.any(1))[0], np.nonzero(on.any(0))[0]
    box = (
        ib[0] + int(xs[0]),
        ib[1] + int(ys[0]),
        ib[0] + int(xs[-1]) + 1,
        ib[1] + int(ys[-1]) + 1,
    )
    return box, float(a[on].mean())


def _hook_composite(orig):
    """Image.composite(a, b, mask), ImageChops.composite: a where the mask is white, b where it is black. A text is
    clipped to the part of its box the mask shows (a wipe halfway across a caption shows that half, the box a viewer
    sees), at the mask's mean opacity over that part."""

    def composite(image1, image2, mask):
        R = _R
        if R is None or R.depth:
            return orig(image1, image2, mask)
        out = _call(R, orig, image1, image2, mask)
        for im, white in ((image1, True), (image2, False)):
            if _at(im):
                memo = {}

                def look(p, w=white, memo=memo):
                    if id(p) not in memo:
                        memo[id(p)] = _shown(mask, p, w)
                    return memo[id(p)]

                _carry(
                    R,
                    out,
                    _at(im),
                    clip=lambda p, f=look: f(p)[0],
                    op=lambda p, f=look: f(p)[1],
                )
        if _at(mask):
            _carry(R, out, _at(mask))
        return out

    return composite


def _hook_union(orig):
    """Image.merge and the other ImageChops operations: the result holds every input's records."""

    def f(*a, **k):
        R = _R
        if R is None or R.depth:
            return orig(*a, **k)
        out = _call(R, orig, *a, **k)
        if isinstance(out, Image.Image):
            for v in (*a, *k.values()):
                for im in v if isinstance(v, (list, tuple)) else (v,):
                    if _at(im):
                        _carry(R, out, _at(im))
        return out

    return f


_CHOPS = (
    "add",
    "add_modulo",
    "blend",
    "composite",
    "darker",
    "difference",
    "hard_light",
    "lighter",
    "logical_and",
    "logical_or",
    "logical_xor",
    "multiply",
    "overlay",
    "screen",
    "soft_light",
    "subtract",
    "subtract_modulo",
)
HOOKS = [
    # the class attribute, which scenes.py's star-import of engine cannot bypass
    (ImageDraw.ImageDraw, "text", _hook_text),
    *[
        (Image.Image, n, _hook_same)
        for n in ("copy", "convert", "filter", "point", "getchannel")
    ],
    (Image.Image, "split", _hook_split),
    (Image.Image, "crop", _hook_crop),
    (Image.Image, "resize", _hook_resize),
    (Image.Image, "reduce", _hook_reduce),
    *[(Image.Image, n, _hook_lost) for n in ("rotate", "transform", "transpose")],
    (Image.Image, "paste", _hook_paste),
    (Image.Image, "alpha_composite", _hook_alpha_composite),
    (Image.Image, "putalpha", _hook_putalpha),
    (Image, "alpha_composite", _hook_alpha_composite_fn),
    (Image, "blend", _hook_blend),
    (Image, "composite", _hook_composite),
    (Image, "merge", _hook_union),
    *[
        (
            ImageChops,
            n,
            {"blend": _hook_blend, "composite": _hook_composite}.get(n, _hook_union),
        )
        for n in _CHOPS
        if hasattr(ImageChops, n)
    ],
]
_CROP = Image.Image.crop  # the real crop, for the recorder's own reads


@contextlib.contextmanager
def installed(R):
    """The hooks in place for the body only, then PIL exactly as it was (also on an error)."""
    global _R
    saved = [(o, n, getattr(o, n)) for o, n, _ in HOOKS]
    for (o, n, wrap), (_, _, f) in zip(HOOKS, saved):
        setattr(o, n, wrap(f))
    _R = R
    try:
        yield R
    finally:
        _R = None
        for o, n, f in saved:
            setattr(o, n, f)


# ---- one draw(t) under the recorder ----


def _frame(scn, t, R, skip=None):
    """draw(t) with the hooks in place for that call only: (the frame, Frame)."""
    R.serial += 1
    R.begin(R.serial, skip)
    with installed(R):
        img = scn.draw(t)
    return img, Frame(R, img)


_COPY = "_qa_registry_scenes"


def _fresh(scenes):
    """A private copy of scenes.py, imported with the hooks on: its caches start empty, so a tile or sprite made
    before this gate ran (by text_gates' contrast frames) is made again and recorded, and sprites made at import
    keep their records. Returns (module, why) and falls back to the module qa.py imported if the copy fails."""
    path = getattr(scenes, "__file__", None)
    if not path:
        return (
            scenes,
            "scenes has no file: cached text drawn before this gate is not seen",
        )
    spec = importlib.util.spec_from_file_location(_COPY, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_COPY] = mod  # dataclasses and pickling look modules up by name
    R = Recorder(1, 1)
    try:
        with installed(R):
            spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001 (whatever a scenes.py import raises, fall back to qa's module)
        sys.modules.pop(_COPY, None)
        return scenes, f"a second import of scenes.py failed ({type(e).__name__}: {e})"
    return mod, None


# ---- what a person reads on one frame ----


def _key(s):
    """Strings compare with their whitespace collapsed and case folded: wraps and capitalisation are layout."""
    return " ".join(str(s).split()).casefold()


def _registry(scn, t):
    """text_items(t) as [{key, s, box, alpha, known, texture, reveal_end}]; reads the older kit form {text, ...} too
    (no box, no alpha). known: the item gave its alpha (a missing alpha reads 1.0, as qa.py reads it)."""
    out = []
    for it in scn.text_items(t) or []:
        s = it.get("s", it.get("text"))
        if s is None:
            continue
        b = it.get("box")
        out.append(
            {
                "key": _key(s),
                "s": str(s),
                "box": tuple(float(v) for v in b) if b is not None else None,
                "alpha": float(it.get("alpha", 1.0)),
                "known": "alpha" in it,
                "texture": bool(it.get("texture", False)),
                "reveal_end": it.get("reveal_end"),
            }
        )
    return out


def _map(b, m):
    ox, oy, sx, sy = m[:4]
    return (b[0] * sx + ox, b[1] * sy + oy, b[2] * sx + ox, b[3] * sy + oy)


def _union(boxes):
    bs = [b for b in boxes if b and b[2] > b[0] and b[3] > b[1]]
    if not bs:
        return None
    return (
        min(b[0] for b in bs),
        min(b[1] for b in bs),
        max(b[2] for b in bs),
        max(b[3] for b in bs),
    )


def _mean(boxes):
    return (
        tuple(sum(b[i] for b in boxes) / len(boxes) for i in range(4))
        if boxes
        else None
    )


def _area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1]) if b else 0.0


def _iou(a, b):
    i = _isect(a, b) if a and b else None
    return _area(i) / (_area(a) + _area(b) - _area(i)) if i else 0.0


def _runs(recs):
    """Letter-by-letter calls (tracking, a beam reveal) joined into their words. recs share one layer; a call joins
    the run before it when both are one character in one font on one baseline, it moves right, and its glyph starts
    within 0.6 em of the run's last glyph (single-letter labels further apart stay apart)."""
    out, right = [], None
    for r in sorted(recs, key=lambda r: r.seq):
        p = out[-1][-1] if out else None
        gap = (
            r.glyph[0] - right
            if right is not None and r.glyph and r.glyph[2] > r.glyph[0]
            else 0.0
        )
        if (
            p is not None
            and len(r.s) == 1
            and len(p.s) == 1
            and r.font == p.font
            and abs(r.xy[1] - p.xy[1]) < 0.5
            and r.xy[0] > p.xy[0]
            and gap <= 0.6 * (r.size or 0)
        ):
            out[-1].append(r)
        else:
            out.append([r])
            right = None
        if (
            r.glyph and r.glyph[2] > r.glyph[0]
        ):  # a space has none: measure from the letter before
            right = r.glyph[2]
    return out


def _inst(run, m, W, H, k0):
    """One drawn string at one placement m (layer px to output px), or unplaced (m None). None when it is off the
    frame or clipped away. box and ink are what a viewer sees: the glyph and stroked ink boxes cut by the placement's
    clip (a crop, a composite mask) and the frame edge, the box the registry reports; whole and whole_ink uncut."""
    s = "".join(r.s for r in run)
    glyph = ink = whole = whole_ink = None
    sx = 1 / k0
    if m is not None:
        whole = _union(_map(r.glyph, m) for r in run if r.glyph)
        whole_ink = _union(_map(r.ink, m) for r in run if r.ink)
        b = whole or whole_ink
        if b is None:
            return None
        view = _isect(m[4], (0, 0, W, H))
        if _area(_isect(b, view) if view else None) < SEEN * _area(b):
            return None
        glyph = _isect(whole, view) if whole else None
        ink = _isect(whole_ink, view) if whole_ink else None
        sx = m[2]
    return {
        "key": _key(s),
        "s": s,
        "box": glyph,
        "ink": ink,
        "whole": whole,
        "whole_ink": whole_ink,
        "alpha": max(r.alpha for r in run) * (m[5] if m else 1.0),
        "px": max(r.size or 0 for r in run) * sx,
        "stroke": max(r.stroke for r in run),
        "recs": run,
        "map": m,
    }


def _items(fr, W, H, k0):
    """What a person reads on this frame: [{key, s, box, boxes, ink, alpha, px, recs, fill}]. Letter-by-letter calls
    are joined into words; copies of one string at one place (a halo under its fill, a glow mask under its alpha
    mask, a drop shadow, the sub-frames of a motion blur) count once. box is the glyph box of the most opaque fill
    copies, in output px (their mean: blur sub-frames; a fainter shadow copy never drags it), boxes each of those
    copies; None when the text never reached a frame-sized image (composited through numpy, rotated): then it is
    matched by its string alone."""
    groups = {}
    for rec, m in fr.lands:
        # one placement: the layer, its mapping, the part a crop left and what blends and composites left of it
        # (two strings on one layer end apart when a wipe shows only one of them)
        key = (rec.layer,) + tuple(round(v, 3) for v in m[:4])
        key += (round(m[5], 2),) + tuple(round(v) for v in m[4])
        g = groups.setdefault(key, (m, []))
        g[1].append(rec)
    landed = {id(r) for r, _ in fr.lands}
    loose = {}
    for r in fr.loose + fr.lost:
        if id(r) not in landed:
            loose.setdefault(r.layer, {})[id(r)] = r
    inst = [
        _inst(run, m, W, H, k0) for m, recs in groups.values() for run in _runs(recs)
    ]
    inst += [
        _inst(run, None, W, H, k0)
        for g in loose.values()
        for run in _runs(list(g.values()))
    ]
    items = []
    for d in sorted((d for d in inst if d and d["key"]), key=lambda d: -d["alpha"]):
        for it in items:
            if it["key"] == d["key"] and (
                (it["box"] is None and d["box"] is None)
                or _iou(it["box"], d["box"]) >= 0.5
            ):
                it["parts"].append(d)
                break
        else:
            items.append({"key": d["key"], "box": d["box"], "parts": [d]})
    out = []
    for it in items:
        parts = it["parts"]
        # a halo or glow copy (stroked) is never the fill
        fill = [d for d in parts if d["stroke"] == 0] or parts
        top = max(d["alpha"] for d in fill)
        lead = [d for d in fill if d["box"] and d["alpha"] >= top - 0.01]
        bs, ws = [d["box"] for d in lead], [d["whole"] for d in lead if d["whole"]]
        out.append(
            {
                "key": it["key"],
                "s": fill[0]["s"],
                "box": _mean(bs),
                "boxes": bs,
                "whole": _mean(ws),
                "wholes": ws,
                "ink": _union(d["ink"] for d in parts),
                "whole_ink": _union(d["whole_ink"] for d in parts),
                "alpha": max(d["alpha"] for d in parts),
                "px": max(d["px"] for d in fill),
                "recs": [r for d in parts for r in d["recs"]],
                "fill": [(r, d["map"]) for d in fill for r in d["recs"]],
            }
        )
    return out


# ---- drawn against registered ----


def _near(d, r):
    """Drawn d sits on registry item r (within half an em, at least 8 px), or one of them has no position."""
    if d["box"] is None or r["box"] is None:
        return True
    m = max(8.0, 0.5 * d["px"])
    b = r["box"]
    return _isect(d["box"], (b[0] - m, b[1] - m, b[2] + m, b[3] + m)) is not None


def _long(d, s, r=None, t=None, full=0.98):
    """Whether a part-of-a-string match counts. Placed text always does. Text with no position needs 3 characters,
    unless it is symbols only (an ampersand inside a held title) or r, the registered string it would be part of, is
    mid-reveal at t (alpha under full, or before its reveal_end): a beam or a typewriter shows one or two letters
    first."""
    if d["box"] is not None or len(s) >= 3 or not any(c.isalnum() for c in s):
        return True
    if r is None:
        return False
    end = r["reveal_end"]
    return r["alpha"] < full or (t is not None and end is not None and t < end)


def _gap(d, r):
    if d["box"] is None or r["box"] is None:
        return 0.0
    a, b = d["box"], r["box"]
    return math.hypot((a[0] + a[2] - b[0] - b[2]) / 2, (a[1] + a[3] - b[1] - b[3]) / 2)


def _match(d, reg, t=None, full=0.98):
    """(registry item, how, used) for drawn item d at time t. how: 'eq'; 'part' (d is part of a registered string: a
    typewriter reveal, one line of a wrapped block); 'words' (registered items around d spell each of its words);
    None when the registry does not report d. used: the registry items d accounts for. Last, the strings are compared
    with their spaces taken out: letters drawn one at a time with the spaces skipped join without them."""
    near = [r for r in reg if r["key"] and _near(d, r)]
    eq = [r for r in near if r["key"] == d["key"]]
    if eq:
        return min(eq, key=lambda r: _gap(d, r)), "eq", eq
    part = [r for r in near if d["key"] in r["key"] and _long(d, d["key"], r, t, full)]
    if part:
        return min(part, key=lambda r: _gap(d, r)), "part", part
    inside = [r for r in near if r["key"] in d["key"] and _long(d, r["key"])]
    if inside and all(any(w in r["key"] for r in inside) for w in d["key"].split()):
        return inside[0], "words", inside
    flat = d["key"].replace(" ", "")
    for how, ok in (
        ("eq", lambda r: r["key"].replace(" ", "") == flat),
        (
            "part",
            lambda r: flat in r["key"].replace(" ", "") and _long(d, flat, r, t, full),
        ),
    ):
        hit = [r for r in near if flat and ok(r)]
        if hit:
            return min(hit, key=lambda r: _gap(d, r)), how, hit
    return None, None, inside


def _edges(rb, refs):
    """How far box rb is from the nearest of refs: its largest edge difference, px."""
    return min(max(abs(rb[i] - b[i]) for i in range(4)) for b in refs)


def _box_check(d, r):
    """(error px, limit px, kind) of registry box r against drawn d. The registry reports what a viewer sees: the
    glyph box cut by its clip (a crop, a wipe's mask, the frame edge), so hidden ink never counts for overlap or the
    safe area. The drawn box is the mean of the most opaque copies, each copy alone, or the stroked ink box, all so
    cut, whichever is nearest (blur sub-frames, a same-alpha shadow under the fill, an outline). Within BOX_PX of it
    passes. A box that matches the uncut glyph box while part of the text is hidden reports hidden ink. A box as tall
    as a drawn one came from a textbbox (engine.text_box): every edge within BOX_PX. Any other box is hand-made (the
    template's y +/- 0.55 em): the glyphs must sit inside it within BOX_PX, and no edge may reach more than HAND_EM
    past them, because Q201 and Q202 judge the text by this box."""
    rb, gb = r["box"], d["box"]
    refs = [b for b in (gb, *d.get("boxes", ()), d["ink"]) if b]
    whole = [b for b in (d.get("whole"), *d.get("wholes", ()), d.get("whole_ink")) if b]
    err = _edges(rb, refs)
    if err <= BOX_PX:
        return err, BOX_PX, "text_box"
    if whole and _edges(rb, whole) <= BOX_PX:
        return err, BOX_PX, "the whole box while part of the text is hidden"
    if any(abs((rb[3] - rb[1]) - (b[3] - b[1])) <= BOX_PX for b in refs):
        return err, BOX_PX, "text_box"
    out = max(rb[0] - gb[0], rb[1] - gb[1], gb[2] - rb[2], gb[3] - rb[3])
    if out > BOX_PX:
        return out, BOX_PX, "hand box, glyphs outside it"
    over = max(gb[0] - rb[0], gb[1] - rb[1], rb[2] - gb[2], rb[3] - gb[3])
    lim = HAND_EM * d["px"]
    if over > lim:
        return over, lim, "hand box, larger than the text"
    return max(out, 0.0), BOX_PX, "hand box"


def _compare(t, items, reg, acc, scale, full):
    """Fold one frame into the tallies: drawn items nobody reported (Q204), registry boxes against drawn boxes (Q205;
    unplaced: matched only where the place is unknown), and registered texts nothing drew (Q209; blind: those whose
    item gives no alpha, so being off screen may be right)."""
    used = set()
    for d in items:
        if d["alpha"] < 0.05:
            continue
        acc["items"] += 1
        r, how, u = _match(d, reg, t, full)
        used.update(id(x) for x in u)
        if r is not None and d["box"] is None:
            acc["unplaced"] += 1
        if r is None:
            px = d["px"] * scale
            read = (
                d["alpha"] >= READ_ALPHA
                and px >= READ_PX
                and any(c.isalnum() for c in d["s"])
            )
            e = acc["unrep"].setdefault(
                d["key"], {"s": d["s"], "t": [], "read": [], "best": None}
            )
            e["t"].append(t)
            if read:
                e["read"].append(t)
            score = (read, d["alpha"] * px)
            if e["best"] is None or score > e["best"][0]:
                e["best"] = (score, t, d["alpha"], px)
        elif how == "eq" and d["box"] is not None and r["box"] is not None:
            err, lim, kind = _box_check(d, r)
            acc["compared"] += 1
            e = acc["box"].setdefault(
                r["key"], {"s": r["s"], "n": 0, "bad": [], "worst": None}
            )
            e["n"] += 1
            if err > lim:
                e["bad"].append(t)
                if e["worst"] is None or err - lim > e["worst"][0] - e["worst"][1]:
                    e["worst"] = (err, lim, kind, t, r["box"], d["box"])
    for r in reg:
        if r["alpha"] >= READ_ALPHA and not r["texture"]:
            acc["regs"] += 1
            if id(r) not in used:
                tally = acc["miss"] if r["known"] else acc["blind"]
                tally.setdefault(r["key"], {"s": r["s"], "t": []})["t"].append(t)


def _exact_spans(scn, R, regs, idx, key, shown, fps, W, H, k0, full):
    """[(t0, t1)]: the first and last frame of each run where key is drawn unreported. shown: the sampled frames that
    showed it. Each run is walked out a frame at a time, never past the sampled frame beside it that did not."""
    pos = {f: j for j, f in enumerate(idx)}
    runs = []
    for f in sorted(shown):
        if runs and pos[f] == pos[runs[-1][1]] + 1:
            runs[-1][1] = f
        else:
            runs.append([f, f])

    def shows(g):
        _, fr = _frame(scn, g / fps, R)
        return any(
            d["key"] == key
            and d["alpha"] >= 0.05
            and _match(d, regs[g], g / fps, full)[0] is None
            for d in _items(fr, W, H, k0)
        )

    out = []
    for a, b in runs:
        lo = idx[pos[a] - 1] if pos[a] else -1
        hi = idx[pos[b] + 1] if pos[b] + 1 < len(idx) else len(regs)
        while a - 1 > lo and shows(a - 1):
            a -= 1
        while b + 1 < hi and shows(b + 1):
            b += 1
        out.append((a / fps, b / fps))
    return out


# ---- which frames to draw ----


def _windows(scn):
    """scenes.WINDOWS as [(t0, t1)]: transition overlaps given as (t0, t1), (name, t0, t1), {t0, t1}, {name: (t0, t1)}
    or objects with t0 and t1."""
    w = getattr(scn, "WINDOWS", None) or []
    out = []
    for x in w.values() if isinstance(w, dict) else w:
        if isinstance(x, dict):
            a, b = x.get("t0", x.get("start")), x.get("t1", x.get("end"))
        elif hasattr(x, "t0"):
            a, b = x.t0, x.t1
        else:
            a, b = [v for v in x if not isinstance(v, str)][:2]
        out.append((float(a), float(b)))
    return out


def _samples(scn, fps, regs, full):
    """Frame indices to draw: every frame inside a transition window or a caption changeover (a registered alpha
    between 0.05 and full, or the set of shown strings changing), one every GRID seconds elsewhere, and the last.
    Returns (indices, how many came from windows and changeovers, how many from the grid alone)."""
    n = len(regs)
    busy = set()
    for a, b in _windows(scn):
        busy.update(
            range(max(0, C.frame_of(a, fps) - 1), min(n, C.frame_of(b, fps) + 2))
        )
    prev = None
    for i, items in enumerate(regs):
        shown = frozenset(it["key"] for it in items if it["alpha"] > 0.05)
        if any(0.05 < it["alpha"] < full for it in items):
            busy.add(i)
        if prev is not None and shown != prev:
            busy.update((i - 1, i))
        prev = shown
    grid = {C.frame_of(j * GRID, fps) for j in range(int(n / fps / GRID) + 1)} | {n - 1}
    grid = {i for i in grid if 0 <= i < n} - busy
    return sorted(busy | grid), len(busy), len(grid)


# ---- Q206: OVH's differential on the frames the registry gates judge ----


def _shrink(b, k=1):
    return (b[0] + k, b[1] + k, b[2] - k, b[3] - k)


def _cover_tests(regs, full, fps):
    """{frame: {key}}: the middle frame of every rest span of every string (one of the frames Q301 measures its
    contrast at, by qa._mid's rule) and the first frame of each pair of registered texts whose boxes overlap (where
    Q202 and Q203 report it)."""
    n = len(regs)
    spans, opened = {}, {}
    for i, items in enumerate(regs):
        shown = {it["key"] for it in items if it["alpha"] >= full and not it["texture"]}
        for k in shown:
            opened.setdefault(k, i)
        for k in [k for k in opened if k not in shown]:
            spans.setdefault(k, []).append((opened.pop(k), i))
    for k, a in opened.items():
        spans.setdefault(k, []).append((a, n))
    tests = {}
    for k, sp in spans.items():
        for (
            a,
            b,
        ) in sp:  # [a, b) in frames: the nearest frame to the middle, kept inside the span (qa._mid)
            tests.setdefault(min(C.frame_of((a + b) / 2 / fps, fps), b - 1), set()).add(
                k
            )
    pairs = {}
    for i, items in enumerate(regs):
        vis = [
            it for it in items if it["alpha"] > 0.05 and not it["texture"] and it["box"]
        ]
        for x in range(len(vis)):
            for y in range(x + 1, len(vis)):
                a, b = vis[x], vis[y]
                if a["key"] != b["key"] and _isect(
                    _shrink(a["box"]), _shrink(b["box"])
                ):
                    pairs.setdefault((a["key"], b["key"]), i)
    for (ka, kb), i in pairs.items():
        tests.setdefault(i, set()).update((ka, kb))
    return tests


def _stamp(out, mk, m):
    """OR a record's layer-px ink mask into an output-px mask through its placement m."""
    x0, y0, a = mk
    ox, oy, sx, sy, clip = m[:5]
    w, h = max(1, round(a.shape[1] * sx)), max(1, round(a.shape[0] * sy))
    if (w, h) != (a.shape[1], a.shape[0]):
        a = (
            np.asarray(
                Image.fromarray(a.astype(np.uint8) * 255).resize((w, h), Image.BILINEAR)
            )
            >= 128
        )
    X, Y = round(x0 * sx + ox), round(y0 * sy + oy)
    c = _isect((X, Y, X + w, Y + h), clip)
    c = _isect(c, (0, 0, out.shape[1], out.shape[0])) if c else None
    if c is None:
        return
    l, t, r, b = math.ceil(c[0]), math.ceil(c[1]), math.floor(c[2]), math.floor(c[3])
    if r > l and b > t:
        out[t:b, l:r] |= a[t - Y : b - Y, l - X : r - X]


def _exposure(scn, t, d, A, A2, R, W, H):
    """(exposed, ink px, why) for drawn item d on frame A (RGB). exposed is the fraction of d's ink that changes when
    the frame is drawn without d's calls (or without the cached tile or sprite that carries d). It is None when it
    cannot be measured, with why: "no ink" (no mask, or under 12 px of it), "impure" (A2, the same frame drawn again,
    differs from A inside d's ink box, so a change there proves nothing), "kept" (nothing could be left out)."""
    ink = np.zeros((H, W), bool)
    for rec, m in d["fill"]:
        mk = rec.mask or _lazy_mask(rec)
        if mk is not None and m is not None:
            _stamp(ink, mk, m)
    n = int(ink.sum())
    if n < 12:
        return None, n, "no ink"
    ys, xs = np.nonzero(ink.any(1))[0], np.nonzero(ink.any(0))[0]
    box = (int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1)
    a, a2 = (np.asarray(im.crop(box), np.int16) for im in (A, A2))
    if (np.abs(a - a2).max(2) >= CHANGED).any():
        return None, n, "impure"
    B, fr = _frame(scn, t, R, skip=({r.sig for r in d["recs"]}, set(d["recs"])))
    if fr.skipped == 0:
        return None, n, "kept"
    b = np.asarray(B.convert("RGB").crop(box), np.int16)
    sub = ink[box[1] : box[3], box[0] : box[2]]
    return float((np.abs(a - b).max(2) >= CHANGED)[sub].sum()) / n, n, None


# ---- the sampling pass: one process, or several when it would take long ----

# Frames drawn first (spread over the piece) to time the pass, and the seconds above which the rest goes to workers.
PROBE, SLOW = 6, 20.0


def _summary(items):
    """What _compare needs of a frame's drawn items: small and picklable, so a worker can send it back."""
    return [
        {
            k: d[k]
            for k in (
                "key",
                "s",
                "box",
                "boxes",
                "whole",
                "wholes",
                "ink",
                "whole_ink",
                "alpha",
                "px",
            )
        }
        for d in items
    ]


def _one(scn, R, i, fps, W, H, k0):
    """Draw frame i under the recorder: (i, its drawn items, text calls, records on it)."""
    n = R.total
    _, fr = _frame(scn, i / fps, R)
    landed = len({id(r) for r, _ in fr.lands} | {id(r) for r in fr.calls})
    return i, _summary(_items(fr, W, H, k0)), R.total - n, landed


_W = None  # in a worker: (scenes module, Recorder, fps, W, H, k0)


def _winit(path, file, size):
    """A worker takes the parent's sys.path and frame size, then makes its own first import of scenes.py with the
    hooks on (Windows starts workers fresh, and scenes reads E.W, E.H at import)."""
    global _W
    sys.path[:] = path
    import engine as E

    E.W, E.H, E.FPS, E.SS = size
    spec = importlib.util.spec_from_file_location("scenes", file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["scenes"] = mod
    with installed(Recorder(1, 1)):
        spec.loader.exec_module(mod)
    W, H, fps, ss = size
    _W = (mod, Recorder(W, H), fps, W, H, max(1, int(ss)))


def _wframe(i):
    scn, R, fps, W, H, k0 = _W
    return _one(scn, R, i, fps, W, H, k0)


def _procs(opts):
    """(processes, forced): --registry-procs N always uses N (1 or less: none); without it, up to what
    render.render_parallel uses, and only when the pass would be slow."""
    n = (opts or {}).get("registry_procs")
    if n is not None:
        return max(1, int(n)), True
    return max(1, min(8, (os.cpu_count() or 2) // 4)), False


def _sample(scn, idx, fps, W, H, k0, R, procs, file, ss):
    """Every sampled frame as (i, items, calls, records), and how many processes drew them. procs is (n, forced)
    from _procs. PROBE frames spread over the piece time the pass; workers draw the rest when n > 1 and either it
    was asked for or the rest would take over SLOW seconds (draw(t) is pure, so any process gives the same frame)."""
    t0 = time.perf_counter()
    probe = idx[:: max(1, len(idx) // PROBE)][
        :PROBE
    ]  # spread over the piece: scenes cost differently
    out = [_one(scn, R, i, fps, W, H, k0) for i in probe]
    rest = sorted(set(idx) - set(probe))
    per = (time.perf_counter() - t0) / max(1, len(out))
    procs, forced = procs
    if procs > 1 and file and rest and (forced or per * len(rest) > SLOW):
        with multiprocessing.get_context("spawn").Pool(
            procs, initializer=_winit, initargs=(list(sys.path), file, (W, H, fps, ss))
        ) as pool:
            out += pool.map(_wframe, rest, chunksize=max(1, len(rest) // (procs * 4)))
        return out, procs
    return out + [_one(scn, R, i, fps, W, H, k0) for i in rest], 1


def add_check_args(parser):
    """qa.py check flags for this gate (they reach rows() as ctx.opts)."""
    parser.add_argument(
        "--registry-procs",
        type=int,
        help="processes for the text recorder's sampling pass (default: up to 8, only when one would take over 20 s)",
    )


# ---- rows ----


def _span_pad(fps):
    return math.ceil(GRID * fps) + 1  # frames: samples GRID apart join one span


def _fmt(b):
    return "(" + ", ".join(f"{v:.0f}" for v in b) + ")"


# Q206 PASSes only when at least this share of its tests could be measured; under it the row is a NOTE.
MEASURED = 0.5
_WHY = {  # why a Q206 test could not be measured, as the row says it
    "unplaced": "drawn only where its place is unknown: composited through numpy, rotated or transformed",
    "not drawn": "not drawn at that frame",
    "no ink": "with too little ink to measure",
    "kept": "that could not be drawn without it",
}


def _q206(scn, R, regs, full, fps, W, H, k0, no_text, has_reg):
    """Q206 rows: OVH's differential at the frames the registry gates judge. A covered text is a FIX. A test that
    cannot be measured is counted by its reason; when under MEASURED of the tests could be measured, the row is a
    NOTE that says so, never a PASS. An impure draw at a tested text is NOT CHECKED (the differential means nothing
    there; Q1201 is the purity gate)."""
    if no_text:
        return [
            C.row(True, "Q206", "no registry by design (NO_TEXT)", "", considered=0)
        ]
    if not has_reg:
        return [
            C.not_checked(
                "Q206",
                "no text_items(t): no registered text to test",
                "add text_items(t)",
            )
        ]
    tests = _cover_tests(regs, full, fps)
    covered, tested, lowest, why, impure = {}, 0, 1.0, {}, []
    for i in sorted(tests):
        t = i / fps
        A, frA = _frame(scn, t, R)
        A, A2 = A.convert("RGB"), None
        items = _items(frA, W, H, k0)
        for key in sorted(tests[i]):
            r = next((x for x in regs[i] if x["key"] == key), None)
            hits = []
            for d in items if r is not None else ():
                rr, how, _ = _match(d, [r], t, full)
                if rr is r:
                    hits.append((how != "eq", d))
            cand = [h for h in hits if h[1]["box"] is not None]
            if not cand:
                w = "unplaced" if hits else "not drawn"
                why[w] = why.get(w, 0) + 1
                continue
            if (
                A2 is None
            ):  # the same frame drawn again: a change in the ink box must not come from impurity
                A2 = _frame(scn, t, R)[0].convert("RGB")
            frac, n_ink, w = _exposure(
                scn, t, min(cand, key=lambda c: c[0])[1], A, A2, R, W, H
            )
            if w == "impure":
                impure.append(round(t, 3))
                continue
            if frac is None:
                why[w] = why.get(w, 0) + 1
                continue
            tested += 1
            lowest = min(lowest, frac)
            if frac < EXPOSED and (key not in covered or frac < covered[key][0]):
                covered[key] = (frac, t, r["s"], n_ink)
    out = [
        C.row(
            False,
            "Q206",
            f"{s!r} is covered: {frac:.2f} of its {n_ink} ink px show at {t:.2f} s (needs {EXPOSED})",
            "draw the text after whatever covers it, or move one of them; the registry gates judged it as visible",
            item=s,
            worst_t=round(t, 3),
            t0=t,
            t1=t,
            spans=[(t, t)],
            metric=round(frac, 3),
            limit=EXPOSED,
            considered=tested,
        )
        for frac, t, s, n_ink in covered.values()
    ]
    if impure:
        out.append(
            C.not_checked(
                "Q206",
                f"draw(t) gave different pixels inside a tested text on a second call at {impure[:3]} s, so the"
                " differential cannot run there",
                "make draw(t) pure (seeded randomness, no module state): qa.py purity, Q1201",
                worst_t=impure[0],
            )
        )
    if covered or impure:
        return out
    total = tested + sum(why.values())
    reasons = "; ".join(f"{n} {_WHY[w]}" for w, n in sorted(why.items()))
    if not tests:
        return [
            C.row(
                True,
                "Q206",
                "no registered text at rest: nothing to test",
                "",
                considered=0,
            )
        ]
    if tested and tested >= MEASURED * total:
        return [
            C.row(
                True,
                "Q206",
                f"registered text exposed where Q202, Q203 and Q301 look: {tested} tested, lowest {lowest:.2f}"
                + (f" (not measurable: {reasons})" if reasons else ""),
                "",
                considered=tested,
            )
        ]
    head = (
        f"only {tested} of {total}" if tested else f"none of {total}"
    ) + f" registered text{'s' * (total != 1)}"
    return [
        C.row(
            False,
            "Q206",
            f"{head} could be measured where Q202, Q203 and Q301 look ({reasons})"
            + (f"; lowest {lowest:.2f}" if tested else ""),
            "nothing to do for text composited through numpy, rotated or transformed; text drawn with the engine"
            " helpers onto the frame is measured",
            note=True,
            considered=tested,
        )
    ]


def _q209(scn, acc, no_text, has_reg, idx, fps, pad, tol):
    """Q209 rows: text_items(t) reports text at alpha READ_ALPHA or more that nothing drawn matches, one NOTE per
    moment (the lines of one caption share it), honouring ALLOW["Q209"]."""
    if no_text:
        return [
            C.row(True, "Q209", "no registry by design (NO_TEXT)", "", considered=0)
        ]
    if not has_reg:
        return [
            C.not_checked(
                "Q209",
                "no text_items(t): no registered text to look for",
                "add text_items(t)",
            )
        ]
    moments, let = {}, 0
    for e in acc["miss"].values():
        times = [t for t in e["t"] if not C.allowed(scn, "Q209", t, tol)]
        let += not times
        if times:
            moments.setdefault(tuple(C.merge_spans(times, fps, pad)), []).append(e["s"])
    out = []
    for spans, strs in moments.items():
        when = ", ".join(
            f"{a:.2f} s" if a == b else f"{a:.2f} to {b:.2f} s" for a, b in spans[:3]
        )
        out.append(
            C.row(
                False,
                "Q209",
                f"text_items(t) reports {', '.join(repr(s) for s in strs[:4])}{', ...' if len(strs) > 4 else ''}"
                f" at alpha >= {READ_ALPHA}, but nothing drawn matches (at {when}{', ...' if len(spans) > 3 else ''})",
                "report alpha 0 (or leave it out) while it is not drawn; text drawn as a bitmap or a pasted image"
                " is invisible to the recorder",
                note=True,
                item=strs[0],
                worst_t=C.snap(C.worst_of(list(spans)), fps),
                t0=spans[0][0],
                t1=spans[-1][1],
                spans=list(spans),
                considered=acc["regs"],
            )
        )
    # items with no alpha: off screen may be right (a line below its reveal clip), so one row that says alpha is
    # unknown, not one per caption
    times = sorted(
        {
            t
            for e in acc["blind"].values()
            for t in e["t"]
            if not C.allowed(scn, "Q209", t, tol)
        }
    )
    if times:
        strs = [e["s"] for e in acc["blind"].values()]
        spans = C.merge_spans(times, fps, pad)
        out.append(
            C.row(
                False,
                "Q209",
                f"text_items(t) gives no alpha, so it is unknown whether {len(strs)} listed strings should be on screen"
                f" where nothing drawn matches them ({', '.join(repr(s) for s in strs[:4])}{', ...' if len(strs) > 4 else ''};"
                f" {len(times)} sampled frames, first at {times[0]:.2f} s)",
                "report alpha in every text_items(t) item, 0 while a text is hidden or clipped (engine/scenes.py)",
                note=True,
                item=strs[0],
                worst_t=C.snap(times[0], fps),
                t0=spans[0][0],
                t1=spans[-1][1],
                spans=spans,
                considered=acc["regs"],
            )
        )
    if not out:
        allowed = f" ({let} let through by ALLOW)" if let else ""
        msg = (
            f"every registered text at alpha >= {READ_ALPHA} is drawn: {acc['regs']} looked for over {len(idx)}"
            f" frames{allowed}"
            if acc["regs"]
            else f"text_items(t) reports no text at alpha >= {READ_ALPHA}: nothing to look for"
        )
        out.append(C.row(True, "Q209", msg, "", considered=acc["regs"]))
    return out


def rows(scenes, W, H, fps, opts=None):
    """Q204, Q205, Q206, Q208 and Q209 for one scenes module. Needs no video: qa.proof_rows calls it too."""
    import qa

    import engine as E

    t0 = time.perf_counter()
    full = getattr(qa, "FULL", 0.98)  # at rest from this alpha up, as qa's gates
    k0 = max(1, int(getattr(E, "SS", 1)))  # supersampling, for text never on the canvas
    scn, why = _fresh(scenes)
    try:
        return _rows(
            scn,
            why,
            W,
            H,
            fps,
            k0,
            full,
            t0,
            _procs(opts),
            getattr(scenes, "__file__", None),
            E.SS,
        )
    finally:
        sys.modules.pop(_COPY, None)


def _rows(scn, why, W, H, fps, k0, full, t0, procs, file, ss):
    """rows() on the private copy scn: the sampling pass, then the Q204, Q205, Q209, Q206 and Q208 rows."""
    R = Recorder(W, H)
    no_text, has_reg = C.declared(scn, "NO_TEXT"), hasattr(scn, "text_items")
    n = C.frame_of(
        scn.DURATION, fps
    )  # frames in the piece, by the rule render.py counts them with
    regs = [_registry(scn, i / fps) if has_reg else [] for i in range(n)]
    idx, n_busy, n_grid = _samples(scn, fps, regs, full)
    acc = {
        "unrep": {},
        "box": {},
        "miss": {},
        "blind": {},
        "items": 0,
        "compared": 0,
        "regs": 0,
        "unplaced": 0,
    }
    scale = 1080 / min(W, H)  # the size rules are written for 1080 px on the short side
    done, used = _sample(scn, idx, fps, W, H, k0, R, procs, file, ss)
    # landed: records on the frames, the calls inside draw(t) plus tiles and sprites made earlier
    calls = landed = 0
    for i, items, c, n_on in sorted(
        done, key=lambda d: d[0]
    ):  # the same order in one process or many
        calls, landed = calls + c, landed + n_on
        _compare(i / fps, items, regs[i], acc, scale, full)
    t1, s0 = (
        time.perf_counter(),
        R.serial,
    )  # frames drawn after this: Q204 span edges, Q206
    out, pad, tol = [], _span_pad(fps), 1 / fps
    nreg = len({it["key"] for items in regs for it in items})
    note = f" ({why})" if why else ""
    print(
        f"qa_registry: drew {len(idx)} of {n} frames ({n_busy} in transitions and changeovers, {n_grid} more on"
        f" the {GRID:g} s grid) in {t1 - t0:.1f} s on {used} process{'es' * (used > 1)}; {calls} text calls,"
        f" {landed} records on frames{note}"
    )
    if not landed:
        if no_text:
            return [
                C.row(
                    True,
                    "Q204",
                    "no text drawn: none by design (NO_TEXT)",
                    "",
                    considered=0,
                ),
                C.row(
                    True,
                    "Q208",
                    f"the recorder saw no text call in {len(idx)} drawn frames; NO_TEXT is declared",
                    "",
                ),
            ]
        reg_note = (
            f", while text_items(t) reports {nreg} string{'s' * (nreg != 1)}"
            if nreg
            else ""
        )
        return [
            C.not_checked(
                "Q208",
                f"the text recorder saw no ImageDraw.text call in {len(idx)} drawn frames{reg_note}: Q204 to Q206 and Q209 did not run",
                "draw text with engine.text, text_outline, text_halo or ImageDraw.text (bitmap fonts, numpy masks and"
                " pasted images are invisible to it), or set NO_TEXT = True if the piece has no text",
            )
        ]

    # Q204: drawn text the registry does not report
    unrep = acc["unrep"]
    if unrep and not has_reg and not no_text:
        best = max(unrep.values(), key=lambda e: e["best"][0])
        times = [t for e in unrep.values() for t in e["t"]]
        out.append(
            C.row(
                False,
                "Q204",
                f"scenes.py has no text_items(t): {len(unrep)} drawn strings are unreported ("
                + ", ".join(repr(e["s"]) for e in list(unrep.values())[:6])
                + (", ..." if len(unrep) > 6 else "")
                + ")",
                "add text_items(t) reporting every drawn string with its engine.text_box box (references/qa-gates.md)",
                note=not any(e["read"] for e in unrep.values()),
                item=best["s"],
                worst_t=round(best["best"][1], 3),
                t0=min(times),
                t1=max(times),
                spans=C.merge_spans(times, fps, pad),
                considered=acc["items"],
            )
        )
    else:
        let = 0  # NOTE-level strings ALLOW lets through
        for j, (key, e) in enumerate(unrep.items()):
            fix = bool(e["read"])
            times = (
                e["t"]
                if fix
                else [t for t in e["t"] if not C.allowed(scn, "Q204", t, tol)]
            )
            if not times:
                let += 1
                continue
            frames = {C.frame_of(t, fps) for t in times}
            spans = (
                _exact_spans(scn, R, regs, idx, key, frames, fps, W, H, k0, full)
                if j < REFINE
                else C.merge_spans(times, fps, pad)
            )
            read = {C.frame_of(t, fps) for t in e["read"]}
            hit = [s for s in spans if any(s[0] <= f / fps <= s[1] for f in read)]
            _, _, a, px = e["best"]
            what = (
                f"NO_TEXT is declared, but draw(t) paints {e['s']!r}"
                if no_text
                else f"drawn text not in text_items(t): {e['s']!r}"
            )
            when = ", ".join(f"{s0:.2f} to {s1:.2f} s" for s0, s1 in spans[:3])
            out.append(
                C.row(
                    False,
                    "Q204",
                    f"{what} ({px:.0f} px at 1080, alpha {a:.2f}; {when}"
                    + (", ..." if len(spans) > 3 else "")
                    + ")",
                    "drop NO_TEXT and report it in text_items(t)"
                    if no_text
                    else "report it in text_items(t) with its engine.text_box box"
                    + ("" if fix else ", or with texture=True if nobody must read it"),
                    note=not fix,
                    item=e["s"],
                    worst_t=C.snap(C.worst_of(hit or spans), fps),
                    t0=spans[0][0],
                    t1=spans[-1][1],
                    spans=spans,
                    metric=round(px, 1),
                    limit=READ_PX,
                    considered=acc["items"],
                )
            )
        if not any(r.code == "Q204" for r in out):
            out.append(
                C.row(
                    True,
                    "Q204",
                    f"every drawn text is in text_items(t): {acc['items']} drawn items over {len(idx)} frames"
                    + (
                        f" ({let} faint string{'s' * (let != 1)} let through by ALLOW)"
                        if let
                        else ""
                    ),
                    "",
                    considered=acc["items"],
                )
            )

    # Q205: registry boxes against the drawn boxes
    if no_text:
        out.append(
            C.row(True, "Q205", "no registry by design (NO_TEXT)", "", considered=0)
        )
    elif not has_reg:
        out.append(
            C.not_checked(
                "Q205",
                "no text_items(t): no registry box to compare",
                "add text_items(t) with boxes from engine.text_box",
            )
        )
    else:
        n205 = 0
        for e in acc["box"].values():
            if not e["bad"]:
                continue
            err, lim, kind, wt, rb, db = e["worst"]
            n205 += 1
            out.append(
                C.row(
                    False,
                    "Q205",
                    f"registry box of {e['s']!r} is {err:.1f} px off the drawn glyph box ({kind}, limit {lim:.1f} px;"
                    f" registry {_fmt(rb)}, drawn {_fmt(db)}; {len(e['bad'])} of {e['n']} frames)",
                    "report the box engine.text_box gives for the string, xy, size and anchor draw(t) uses",
                    item=e["s"],
                    worst_t=round(wt, 3),
                    t0=min(e["bad"]),
                    t1=max(e["bad"]),
                    spans=C.merge_spans(e["bad"], fps, pad),
                    metric=round(err, 1),
                    limit=round(lim, 1),
                    considered=acc["compared"],
                )
            )
        if not n205:
            unplaced = (
                f" ({acc['unplaced']} matches drawn where the place is unknown, not compared)"
                if acc["unplaced"]
                else ""
            )
            if acc["compared"]:
                out.append(
                    C.row(
                        True,
                        "Q205",
                        f"registry boxes match the drawn glyph boxes: {acc['compared']} compared"
                        f" ({BOX_PX} px for text_box boxes, glyphs inside hand boxes){unplaced}",
                        "",
                        considered=acc["compared"],
                    )
                )
            elif nreg and not any(it["box"] for items in regs for it in items):
                out.append(
                    C.not_checked(
                        "Q205",
                        "text_items(t) reports no box (the older kit form), so no box was compared",
                        "report each text's box from engine.text_box (references/qa-gates.md)",
                    )
                )
            elif nreg:  # matched by string where nothing gives a place: a NOTE, or such a piece never passes
                cause = (
                    f"the {acc['unplaced']} matches were drawn where the place is unknown (composited through"
                    " numpy, rotated or transformed)"
                    if acc["unplaced"]
                    else "registered strings were drawn only in parts (per word or letter, mid-reveal)"
                )
                out.append(
                    C.row(
                        False,
                        "Q205",
                        f"positions not compared: {cause}",
                        "nothing to do for such text; text drawn whole with the engine helpers onto the frame is compared",
                        note=True,
                        considered=0,
                    )
                )
            else:
                out.append(
                    C.row(
                        True,
                        "Q205",
                        "text_items(t) reports no text: nothing to compare",
                        "",
                        considered=0,
                    )
                )

    out += _q209(scn, acc, no_text, has_reg, idx, fps, pad, tol)

    # Q206: registered text covered by something drawn after it
    out += _q206(scn, R, regs, full, fps, W, H, k0, no_text, has_reg)

    out.append(
        C.row(
            True,
            "Q208",
            f"text recorder live: {calls} text calls, {landed} records on {len(idx)} drawn frames",
            "",
            considered=landed,
        )
    )
    print(
        f"qa_registry: Q204 span edges and Q206 drew {R.serial - s0} more frames in"
        f" {time.perf_counter() - t1:.1f} s"
    )
    return out


def check_rows(ctx):
    """The qa.py check hook: rows() on the video's scenes.py at the file's size and rate. A recorder that fails is
    reported as a row, never as a crash of the whole check."""
    scn = ctx.scenes
    if scn is None or not hasattr(scn, "draw"):
        return []
    try:
        return rows(scn, ctx.w, ctx.h, ctx.fps, ctx.opts)
    except Exception as e:  # noqa: BLE001 (a recorder failure is a row, never a crash of qa.py check)
        return [
            C.not_checked(
                "Q208",
                f"the text recorder failed: {type(e).__name__}: {e}",
                "run qa_registry.rows(scenes, W, H, fps) to see the traceback",
            )
        ]
