# engine.py : helpers shared by scenes.py (device Python: PIL + numpy)
import math, os
import zlib
from collections import namedtuple
from fractions import Fraction
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
import numpy as np

import fonts

# the one frame clock (Z06), re-exported so `from engine import *` gives it to scenes.py
from contract import frame_of, frame_sample, on_grid, sample_of, snap, stepped  # noqa: F401

W, H, FPS, SS = 1920, 1080, 30, 1  # override before use: engine.W, engine.H = ...
FONT_BOLD = [
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial Bold.ttf",
]
FONT_REG = [
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
]


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def lerp(a, b, k):
    return a + (b - a) * k


def prog(t, t0, dur):
    return clamp((t - t0) / dur)  # 0..1 progress of a move that starts at t0


def linear(k):
    return k


def ease_out_cubic(k):
    return 1 - (1 - k) ** 3


def ease_in_cubic(k):
    return k**3


def ease_in_out_cubic(k):
    return 4 * k**3 if k < 0.5 else 1 - (-2 * k + 2) ** 3 / 2


def ease_out_expo(k):
    return 1.0 if k >= 1 else 1 - 2 ** (-10 * k)


def ease_out_back(k, s=1.70158):
    return 1 + (s + 1) * (k - 1) ** 3 + s * (k - 1) ** 2


def spring(t, stiffness=100, damping=10, mass=1):
    """0 -> 1 position of a spring t seconds after release, from rest: Remotion's spring() with the same defaults,
    closed form. Damping under 2 * sqrt(stiffness * mass) overshoots, then settles; at or over it the spring moves
    as critically damped, as Remotion's does, so its damping: 200 'no bounce' config ports as it is. 0 for t <= 0."""
    if damping <= 0:
        raise ValueError("spring damping must be over 0, or it never comes to rest")
    if t <= 0:
        return 0.0
    w0 = math.sqrt(stiffness / mass)
    z = damping / (2 * math.sqrt(stiffness * mass))
    if z >= 1:
        return 1 - math.exp(-w0 * t) * (1 + w0 * t)
    w1 = w0 * math.sqrt(1 - z * z)
    decay = math.exp(-z * w0 * t)
    return 1 - decay * (math.cos(w1 * t) + z * w0 / w1 * math.sin(w1 * t))


def settle_time(stiffness=100, damping=10, mass=1, fps=None, threshold=0.005):
    """Seconds until spring() is at rest, by Remotion's measureSpring: the first frame under threshold of 1, moved on
    past any frame over it in the next 20 (Remotion's loop, its reset kept), then / fps. A registry can report a
    springing item as at rest from here."""
    fps = fps or FPS

    def off(f):
        return abs(1 - spring(f / fps, stiffness, damping, mass)) >= threshold

    f, limit = 0, 600 * fps  # ten minutes: a spring not at rest by then never is
    while off(f) and f < limit:
        f += 1
    done, i = f, 0
    while i < 20 and f < limit:
        f += 1
        if off(f):
            i, done = 0, f + 1
        i += 1
    if f >= limit:
        raise ValueError(
            f"spring({stiffness}, {damping}, {mass}) is not at rest within 10 minutes"
        )
    return done / fps


_fc = {}


def font(size, bold=True):
    """The font every text helper draws with. bold: True or False for FONT_BOLD or FONT_REG above, or a free family
    the style cards name as "Family:weight[:italic]" (fonts.py: "Nunito:800", "Inter:600", "Bodoni Moda:400:italic"),
    so text(), text_box(), fit_size() and wrap() take a family through the same bold= argument."""
    key = (int(size), bold)
    if key not in _fc and isinstance(bold, str):
        _fc[key] = fonts.load(bold, int(size), SS)
    if key not in _fc:
        for p in FONT_BOLD if bold else FONT_REG:
            if os.path.exists(p):
                try:
                    _fc[key] = ImageFont.truetype(p, int(size))
                    break
                except Exception:
                    pass
        else:
            raise FileNotFoundError(
                f"no font found in {FONT_BOLD if bold else FONT_REG}; put an installed font path first"
            )
    return _fc[key]


def hexrgb(h, a=255):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def rng(*keys):
    """numpy Generator seeded by what is being drawn: rng("hook", "dust", frame). Strings go through zlib.crc32,
    ints (0 to 2**32 - 1: frames, indices) are used as they are, and the key count leads the seed, because numpy
    pads a seed with zeros (default_rng([5]) and default_rng([5, 0]) are the same stream). Seed each frame or
    element from its own keys, never from one stream advanced frame after frame: then any frame can be drawn alone,
    in any order, in any process, and the purity gate (Q1201) holds."""
    if not keys:
        raise TypeError("rng() needs a key, for example rng('hook', 'dust', frame)")
    seed = [len(keys)]
    for k in keys:
        if isinstance(k, str):
            seed.append(zlib.crc32(k.encode()))
        elif isinstance(k, (int, np.integer)):
            if not 0 <= k < 2**32:
                raise ValueError(f"rng key {k}: ints must be 0 to 2**32 - 1")
            seed.append(int(k))
        else:
            raise TypeError(
                f"rng key {k!r}: use a string or an int; for a time pass frame_of(t, FPS), not t"
            )
    return np.random.default_rng(seed)


def canvas(color="#000000"):
    return Image.new("RGBA", (W * SS, H * SS), hexrgb(color))


def gradient(c1, c2, vertical=True):
    a, b = np.array(hexrgb(c1)[:3], float), np.array(hexrgb(c2)[:3], float)
    n = H * SS if vertical else W * SS
    ramp = (a + (b - a) * np.linspace(0, 1, n)[:, None]).astype(np.uint8)
    arr = (
        np.repeat(ramp[:, None, :], W * SS, 1)
        if vertical
        else np.repeat(ramp[None, :, :], H * SS, 0)
    )
    return Image.fromarray(arr, "RGB").convert("RGBA")


def rrect(img, box, r, fill, alpha=1.0):
    """Rounded rectangle composited with opacity. box in output pixels (x0,y0,x1,y1)."""
    if alpha <= 0:
        return
    x0, y0, x1, y1 = [v * SS for v in box]
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    c = hexrgb(fill) if isinstance(fill, str) else fill
    ImageDraw.Draw(lay).rounded_rectangle(
        (x0, y0, x1, y1), r * SS, fill=c[:3] + (int(c[3] * alpha),)
    )
    img.alpha_composite(lay)


def shadow(img, box, r, blur=24, dy=12, alpha=0.35):
    x0, y0, x1, y1 = [v * SS for v in box]
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(lay).rounded_rectangle(
        (x0, y0 + dy * SS, x1, y1 + dy * SS), r * SS, fill=(0, 0, 0, int(255 * alpha))
    )
    img.alpha_composite(lay.filter(ImageFilter.GaussianBlur(blur * SS)))


def text(
    img,
    s,
    xy,
    size,
    fill="#FFFFFF",
    anchor="la",
    alpha=1.0,
    bold=True,
    scale=1.0,
    tracking=0,
):
    """Draw text at xy (output px). anchor: PIL anchors (la, mm, ra ...). scale > 1 grows around the anchor."""
    if alpha <= 0:
        return
    f = font(size * scale * SS, bold)
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    c = hexrgb(fill) if isinstance(fill, str) else fill
    d = ImageDraw.Draw(lay)
    if tracking:  # manual letter-spacing, left anchored
        x = xy[0] * SS
        for ch in s:
            d.text(
                (x, xy[1] * SS),
                ch,
                font=f,
                fill=c[:3] + (int(255 * alpha),),
                anchor="ls" if anchor[1] == "s" else "la",
            )
            x += d.textlength(ch, font=f) + tracking * SS
    else:
        d.text(
            (xy[0] * SS, xy[1] * SS),
            s,
            font=f,
            fill=c[:3] + (int(255 * alpha),),
            anchor=anchor,
        )
    img.alpha_composite(lay)


def text_w(s, size, bold=True):
    return font(size * SS, bold).getlength(s) / SS


def text_box(s, xy, size, anchor="la", bold=True, tracking=0):
    """(l, t, r, b) in output px of text drawn with text(): the box to report in scenes.text_items(t). Pass the same
    tracking text() got: letter-spaced text is drawn one letter at a time, so its box is the union of the letters."""
    f = font(size * SS, bold)
    d = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    if not tracking:
        l, t, r, b = d.textbbox((xy[0] * SS, xy[1] * SS), s, font=f, anchor=anchor)
        return (l / SS, t / SS, r / SS, b / SS)
    x, boxes = xy[0] * SS, []
    for ch in s:  # the same walk as text(tracking=)
        boxes.append(
            d.textbbox(
                (x, xy[1] * SS), ch, font=f, anchor="ls" if anchor[1] == "s" else "la"
            )
        )
        x += d.textlength(ch, font=f) + tracking * SS
    if not boxes:  # "" draws nothing (a typewriter reveal at its first frame): an empty box, as the untracked path
        return (xy[0], xy[1], xy[0], xy[1])
    l, t = min(b[0] for b in boxes), min(b[1] for b in boxes)
    r, b = max(b[2] for b in boxes), max(b[3] for b in boxes)
    return (l / SS, t / SS, r / SS, b / SS)


def fit_size(s, size, maxw, bold=True, floor=36):
    """Largest size up to `size` at which s fits in maxw px; never below `floor` (cut copy instead of shrinking)."""
    while size > floor and text_w(s, size, bold) > maxw:
        size -= 2
    return size


def text_outline(
    img,
    s,
    xy,
    size,
    fill="#FFFFFF",
    outline="#000000",
    width=4,
    anchor="la",
    alpha=1.0,
    bold=True,
):
    """Text with a solid outline (PIL stroke): for game, anime and caption styles over busy pictures."""
    if alpha <= 0:
        return
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    c, o = (hexrgb(v) if isinstance(v, str) else v for v in (fill, outline))
    ImageDraw.Draw(lay).text(
        (xy[0] * SS, xy[1] * SS),
        s,
        font=font(size * SS, bold),
        anchor=anchor,
        fill=c[:3] + (int(255 * alpha),),
        stroke_width=int(width * SS),
        stroke_fill=o[:3] + (int(255 * alpha),),
    )
    img.alpha_composite(lay)


def text_halo(
    img,
    s,
    xy,
    size,
    fill="#FFFFFF",
    halo="#000000",
    radius=10,
    strength=0.6,
    anchor="la",
    alpha=1.0,
    bold=True,
):
    """Text over a soft dark halo (blurred thick stroke) so it reads over imagery without a hard box."""
    if alpha <= 0:
        return
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    h = hexrgb(halo) if isinstance(halo, str) else halo
    ImageDraw.Draw(lay).text(
        (xy[0] * SS, xy[1] * SS),
        s,
        font=font(size * SS, bold),
        anchor=anchor,
        fill=h[:3] + (int(255 * strength * alpha),),
        stroke_width=int(radius * SS),
        stroke_fill=h[:3] + (int(255 * strength * alpha),),
    )
    img.alpha_composite(lay.filter(ImageFilter.GaussianBlur(radius * SS * 0.8)))
    text(img, s, xy, size, fill, anchor, alpha, bold)


def wrap(s, size, maxw, bold=True):
    out, line = [], ""
    for w in s.split():
        t = (line + " " + w).strip()
        if text_w(t, size, bold) <= maxw or not line:
            line = t
        else:
            out.append(line)
            line = w
    return out + ([line] if line else [])


def finish(img):
    """Downscale supersampled canvas and return RGB at W x H."""
    if SS > 1:
        img = img.resize((W, H), Image.LANCZOS)
    return img.convert("RGB")


@lru_cache(maxsize=64)
def _spans(key):
    """(name, first frame, end frame, a, b) per scene from a hashable (fps, ((name, a, b), ...)) key."""
    fps, items = key
    return tuple((n, frame_of(a, fps), frame_of(b, fps), a, b) for n, a, b in items)


def _frames(schedule):
    return _spans((FPS, tuple((n, v[0], v[1]) for n, v in schedule.items())))


def scene_at(t, schedule):
    """Return (name, local_t, k) for the scene active at time t; k = 0..1 through the scene. Decided on integer
    frames (nearest frame, contract.frame_of), so float error cannot start a scene one frame late. Where two spans
    overlap (a transition window) the first entry, the outgoing scene, wins. Past the end: the last scene at k = 1."""
    f = frame_of(t, FPS)
    for name, fa, fb, a, b in _frames(schedule):
        if fa <= f < fb:
            # the nearest frame can open a scene up to half a frame before a: hold local_t at 0 there
            lt = max(0.0, t - a)
            return name, lt, min(1.0, lt / (b - a))
    name, _, _, a, b = _frames(schedule)[-1]
    return name, b - a, 1.0


def scenes_at(t, schedule):
    """Every scene drawn at t as ([(name, local_t, k), ...], mix). Outside a transition window that is one scene and
    mix 0.0; inside one, the outgoing then the incoming scene, with mix 0 -> 1 through the window (0 on its first
    frame), ready for transitions.py: f(a, b, mix). Decided on integer frames, like scene_at."""
    f = frame_of(t, FPS)
    on = [s for s in _frames(schedule) if s[1] <= f < s[2]]
    if not on:
        name, _, _, a, b = _frames(schedule)[-1]
        return [(name, b - a, 1.0)], 0.0
    shown = []
    for name, _, _, a, b in on:
        lt = max(0.0, t - a)
        shown.append((name, lt, min(1.0, lt / (b - a))))
    if len(on) == 1:
        return shown, 0.0
    w0, w1 = max(s[1] for s in on), min(s[2] for s in on)
    return shown, (f - w0) / (w1 - w0)


def crossfade(a_img, b_img, k):
    return Image.blend(a_img, b_img, clamp(k))


# ---- declared timing (Z19): scenes as durations, transitions between them, scene-local cues ----

Scene = namedtuple("Scene", "name dur cues", defaults=((),))
Scene.__doc__ = """One scene for compile_schedule. dur: seconds (beats when bpm is given), a number or a function
that returns one, for example lambda: max(2.0, narration_s). cues: scene-local [(t, label[, kind])] or {label: t},
t counted from the scene's first drawn frame."""
Transition = namedtuple("Transition", "kind dur split", defaults=(0.5,))
Transition.__doc__ = """A transition window between the two scenes either side of it. kind: a transitions.py name for
your draw code. dur: seconds (beats when bpm is given). split: the share of the window before the cut (0.5 centres it
on the cut, 0 starts it on the cut)."""
Timeline = namedtuple("Timeline", "schedule duration cuts windows cues")


def _exact(v):
    """v as an exact fraction: ints and fractions as they are, other numbers as the nearest fraction with a
    denominator up to 10**6, which recovers both typed decimals (0.1 -> 1/10) and quotients (5 / 30 -> 1/6, where the
    shortest repr 0.16666666666666666 is 4.9999999999999998 frames at 30 fps and loses a frame at a half-frame tie)."""
    if isinstance(v, (int, Fraction)):
        return Fraction(v)
    return Fraction(float(v)).limit_denominator(10**6)


def _local_cues(cues):
    """Scene-local cues as (t, label, kind), from {label: t} or the CUES shapes (tuples or dicts)."""
    if isinstance(cues, dict):
        return [(t, label, "both") for label, t in cues.items()]
    out = []
    for c in cues:
        if isinstance(c, dict):
            out.append((c["t"], c.get("label", ""), c.get("kind", "both")))
        else:
            out.append(
                (c[0], c[1] if len(c) > 1 else "", c[2] if len(c) > 2 else "both")
            )
    return out


def compile_schedule(items, mode="straddle", bpm=None, fps=None):
    """Absolute timing from declared scenes: [Scene, Transition, Scene, Scene, ...] -> Timeline, unpacked in
    scenes.py as SCHEDULE, DURATION, CUTS, WINDOWS, CUES. Lengthen one scene and every later scene, window and cue
    moves with it. SCHEDULE {name: (a, b)}: the span each scene is drawn. CUTS: the time of every scene change.
    WINDOWS [(t0, t1, out_name, in_name)]: the transition windows. CUES [(t, label, kind)]: the scene cues, absolute.
    mode "straddle" (default): scenes run cut to cut, so DURATION is their sum and the cuts stay on the grid the
      durations lie on; a window spans its cut (split of it before the cut) and both scenes are drawn in it.
    mode "overlap" (Remotion): the next scene starts dur before this one ends, so DURATION loses every transition
      (60 + 60 - 15 = 105 frames) and the cut sits split of the way into the overlap.
    The arithmetic is exact (fractions of seconds, or of beats when bpm is given) and each instant is rounded once to
    its nearest frame, so nothing drifts off the grid. ValueError for a transition under 2 frames (no frame of it
    would be blended) or over half the shorter of its two scenes, a scene that rounds to no frame, and a cue that
    does not land on a frame of its own scene."""
    if mode not in ("straddle", "overlap"):
        raise ValueError(f'mode {mode!r}: use "straddle" or "overlap"')
    fps = fps or FPS
    unit = "s" if bpm is None else "beats"
    # frames per unit: per second, or per beat when bpm is given
    per = Fraction(fps) if bpm is None else Fraction(60 * fps) / _exact(bpm)
    # trans[i] sits between scenes[i] and scenes[i + 1]; None is a hard cut
    scenes, trans, pending = [], [], None
    for it in items:
        if isinstance(it, Transition):
            if not scenes or pending is not None:
                raise ValueError(f"{it} must sit between two scenes")
            pending = it
            continue
        sc = it if isinstance(it, Scene) else Scene(*it)
        if any(s.name == sc.name for s in scenes):
            raise ValueError(f"scene {sc.name!r} is declared twice")
        if scenes:
            trans.append(pending)
        scenes.append(sc)
        pending = None
    if pending is not None or not scenes:
        raise ValueError("a timeline needs a scene and must not end on a Transition")

    d = []  # exact frames per scene
    for s in scenes:
        v = _exact(s.dur() if callable(s.dur) else s.dur)
        if v <= 0:
            raise ValueError(
                f"scene {s.name!r} lasts {float(v):g} {unit}: it must be over 0"
            )
        d.append(v * per)
    x = [0 if tr is None else _exact(tr.dur) * per for tr in trans]  # window frames
    for i, tr in enumerate(trans):
        if tr is None:
            continue
        if not 0 <= tr.split <= 1:
            raise ValueError(f"{tr}: split must be 0 to 1")
        what = (
            f"{tr.kind!r} transition of {float(tr.dur):g} {unit} ({float(x[i]):.1f} frames) between "
            f"{scenes[i].name!r} ({float(d[i] / fps):.3f} s) and {scenes[i + 1].name!r} "
            f"({float(d[i + 1] / fps):.3f} s)"
        )
        # a window's first frame is all outgoing (mix 0), so under 2 frames nothing is blended
        if x[i] < 2:
            raise ValueError(
                f"{what} is under 2 frames at {fps} fps, so no frame of it is blended: make it at least "
                f"{2 / fps:.3f} s, or use a hard cut"
            )
        j = min((i, i + 1), key=lambda k: d[k])  # the shorter neighbour
        if 2 * x[i] > d[j]:
            raise ValueError(
                f"{what} is over half the shorter scene, {scenes[j].name!r} "
                f"({float(d[j] / fps / 2):.3f} s): shorten it or lengthen {scenes[j].name!r}"
            )
    split = [0 if tr is None else _exact(tr.split) for tr in trans]

    n = len(scenes)
    if mode == "straddle":
        # cut i (into scene i + 1) lies at the sum of the scenes before it; its window spans it
        cut = [sum(d[: i + 1]) for i in range(n - 1)]
        w0 = [c - p * xi for c, p, xi in zip(cut, split, x)]
        w1 = [c + (1 - p) * xi for c, p, xi in zip(cut, split, x)]
        end = sum(d)
    else:
        # scene i + 1 starts x[i] before scene i ends; the cut sits split of the way in
        w0 = []
        for i in range(n - 1):
            w0.append((w0[-1] if w0 else 0) + d[i] - x[i])
        w1 = [a + xi for a, xi in zip(w0, x)]
        cut = [a + p * xi for a, p, xi in zip(w0, split, x)]
        end = (w0[-1] if w0 else 0) + d[-1]
    # exact: scene i is drawn from the start of the window into it to the end of the one out of it
    start, stop = [Fraction(0), *w0], [*w1, end]

    def fr(v):  # the one rounding: nearest frame, halves up, as contract.frame_of
        return math.floor(v + Fraction(1, 2))

    for i, s in enumerate(scenes):
        # under about half a frame: no frame would show the scene, yet it would still make a cut
        if fr(stop[i]) <= fr(start[i]):
            raise ValueError(
                f"scene {s.name!r} lasts {float(d[i] / per):g} {unit} ({float(d[i]):.2f} frames) and rounds to no "
                f"frame at {fps} fps: lengthen it to at least one frame or drop it"
            )
    schedule = {
        s.name: (fr(start[i]) / fps, fr(stop[i]) / fps) for i, s in enumerate(scenes)
    }
    windows = [
        (fr(w0[i]) / fps, fr(w1[i]) / fps, scenes[i].name, scenes[i + 1].name)
        for i in range(n - 1)
        if trans[i] is not None
    ]
    cues = []
    for i, s in enumerate(scenes):
        for t, label, kind in _local_cues(s.cues):
            f = fr(start[i] + _exact(t) * per)
            # on a frame the scene itself draws: at its end the cue would be the next scene's first frame, or for
            # the last scene frame DURATION, which is never drawn
            if not fr(start[i]) <= f < fr(stop[i]):
                last = (fr(stop[i]) - 1 - fr(start[i])) / per
                raise ValueError(
                    f"cue {label!r} at {float(t):g} {unit} does not land on a frame of scene {s.name!r} "
                    f"(0 to {float(last):g} {unit}); a cue at the scene's end belongs to the next scene at 0"
                )
            cues.append((f / fps, label, kind))
    return Timeline(
        schedule, fr(end) / fps, [fr(c) / fps for c in cut], windows, sorted(cues)
    )
