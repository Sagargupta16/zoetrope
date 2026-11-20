# plates.py : photo-like plates (a still image per scene, 9:16 up to 1152x2016, plus RGBA cutouts) under drawn graphics,
# with Ken Burns motion and parallax. Shared by every build (the engine folder is copied into each build folder), so a
# plate name resolves to HERE / "plates" / "<name>.png" in the build folder.
#
# Everything here is a pure function of its arguments: the only state is functools.lru_cache holding what a pure
# function gives (a plate read from disk, a blurred plate, a gradient or a mask). A cached image is shared by every
# caller and must never be changed: no function here mutates an input or a cached image, and every function that
# composes returns a new image the caller may draw on. Sizes come in as win = (w, h) in canvas px (the supersampled
# canvas: pass (engine.W * engine.SS, engine.H * engine.SS)); nothing assumes 1080x1920.
# Composing runs on RGBA layers with Image.alpha_composite; never draw on them with ImageDraw.Draw(img, "RGBA")
# (on an RGBA canvas it writes the stroke's alpha instead of blending).
import math
from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise
from pathlib import Path
from typing import Optional

import engine as E
import numpy as np
import transitions as T
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent

KEN_BURNS_MIN, KEN_BURNS_MAX = (
    1.0,
    1.3,
)  # past about 1.3x a plate goes soft (references/image-plates.md)
HAZE_COLOUR = (168, 184, 200)  # a cool atmospheric haze
DEFAULT_HAZE = (
    HAZE_COLOUR,
    0.0,
    0.30,
)  # (colour, alpha at the top, alpha at the bottom)
VIGNETTE_COLOUR = (0, 0, 0)
VIGNETTE_START = 0.45  # share of the way to the corner where the darkening begins
EASES = {
    "linear": E.linear,
    "ease_out_cubic": E.ease_out_cubic,
    "ease_in_cubic": E.ease_in_cubic,
    "in_out_cubic": E.ease_in_out_cubic,
    "ease_in_out_cubic": E.ease_in_out_cubic,
    "ease_out_expo": E.ease_out_expo,
}


# ---- reading plates ----


@lru_cache(maxsize=12)
def load(name):
    """Plate `name` (plates/<name>.png) as an RGB image, read once. Shared and read-only: never draw on it."""
    with Image.open(HERE / "plates" / f"{name}.png") as im:
        return im.convert("RGB")


@lru_cache(maxsize=8)
def load_rgba(name):
    """Cutout `name` (plates/<name>.png) as an RGBA image, read once. Shared and read-only: never draw on it."""
    with Image.open(HERE / "plates" / f"{name}.png") as im:
        return im.convert("RGBA")


@lru_cache(maxsize=32)
def _size(name):
    """(w, h) of plates/<name>.png from its header, without decoding it."""
    with Image.open(HERE / "plates" / f"{name}.png") as im:
        return im.size


@lru_cache(maxsize=4)
def _blurred(name, radius):
    """Plate `name` through a Gaussian blur of `radius` px, made once per (name, radius). Shared and read-only."""
    return load(name).filter(ImageFilter.GaussianBlur(radius))


def cover(plate_size, win):
    """The scale (win px per plate px) at which a plate of plate_size just covers a window win = (w, h)."""
    return max(win[0] / plate_size[0], win[1] / plate_size[1])


# ---- a shot: one plate and its Ken Burns move ----


@dataclass(frozen=True)
class Shot:
    """One plate and its move from t0 to t1 (seconds). s: zoom over cover (1.0 just covers the window, at most 1.3).
    c: the view centre in plate px, (x, y). Both eased from (s0, c0) to (s1, c1) with the engine ease named by `ease`
    (a key of EASES) and held at the end values outside t0..t1. fg: an optional second Shot whose plate is an RGBA
    cutout, drawn over this one on its own move so the two layers drift at different rates (parallax)."""

    plate: str
    t0: float
    t1: float
    s0: float
    s1: float
    c0: tuple
    c1: tuple
    ease: str = "in_out_cubic"
    fg: Optional["Shot"] = None

    def __post_init__(self):
        for s in (self.s0, self.s1):
            if not KEN_BURNS_MIN <= s <= KEN_BURNS_MAX:
                raise ValueError(
                    f"shot {self.plate}: zoom {s} is outside {KEN_BURNS_MIN} to {KEN_BURNS_MAX} (past about "
                    f"{KEN_BURNS_MAX}x the plate goes soft)"
                )
        if self.t1 < self.t0:
            raise ValueError(f"shot {self.plate}: t1 {self.t1} is before t0 {self.t0}")
        if self.ease not in EASES:
            raise ValueError(
                f"shot {self.plate}: ease {self.ease!r}: use one of {', '.join(EASES)}"
            )


def view(shot, t, win):
    """(s, cx, cy) of shot at time t for a window win = (w, h): zoom and centre eased between the shot's ends (held
    outside t0..t1), the centre clamped so the plate covers the window at every t."""
    p = 1.0 if shot.t1 <= shot.t0 else E.clamp((t - shot.t0) / (shot.t1 - shot.t0))
    e = EASES[shot.ease](p)
    s = E.lerp(shot.s0, shot.s1, e)
    cx = E.lerp(shot.c0[0], shot.c1[0], e)
    cy = E.lerp(shot.c0[1], shot.c1[1], e)
    return (s,) + _clamp_centre(_size(shot.plate), s, cx, cy, win)


def _clamp_centre(plate_size, s, cx, cy, win):
    """(cx, cy) moved the least so that a view at zoom s over cover stays inside the plate."""
    k = s * cover(plate_size, win)
    vw, vh = win[0] / k, win[1] / k
    pw, ph = plate_size
    return min(max(cx, vw / 2), pw - vw / 2), min(max(cy, vh / 2), ph - vh / 2)


def window(plate_img, s, cx, cy, win):
    """A new image of exactly win = (w, h): plate_img seen at zoom s over cover with plate point (cx, cy) at the
    window's centre (clamped so the plate covers the window), in one bicubic resample of a sub-pixel box of the
    plate's own pixels (Image.resize with box=: the same maths as an affine transform, 4x faster, and it filters
    when the window is smaller than the box; no full-plate resize, and a slow push never steps). An RGBA plate is sampled premultiplied, so the colour
    under transparent pixels never bleeds into an edge. plate_img is not changed."""
    ww, wh = win
    cx, cy = _clamp_centre(plate_img.size, s, cx, cy, win)
    k = s * cover(plate_img.size, win)
    x0, y0 = cx - ww / (2 * k), cy - wh / (2 * k)
    src = plate_img
    if plate_img.mode == "RGBA":
        # premultiply only the part the window reads (plus the bicubic margin), not the whole plate
        bx0, by0 = max(0, math.floor(x0) - 2), max(0, math.floor(y0) - 2)
        bx1 = min(plate_img.width, math.ceil(x0 + ww / k) + 2)
        by1 = min(plate_img.height, math.ceil(y0 + wh / k) + 2)
        src = plate_img.crop((bx0, by0, bx1, by1)).convert("RGBa")
        x0, y0 = x0 - bx0, y0 - by0
    x1, y1 = x0 + ww / k, y0 + wh / k
    box = (
        max(0.0, x0),
        max(0.0, y0),
        min(float(src.width), x1),
        min(float(src.height), y1),
    )
    out = src.resize((ww, wh), Image.BICUBIC, box=box)
    return out.convert("RGBA") if plate_img.mode == "RGBA" else out


# ---- haze and vignette ----


def _rgb(c):
    """'#RRGGBB' or an RGB tuple as an int triple."""
    if isinstance(c, str):
        h = c.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return int(c[0]), int(c[1]), int(c[2])


@lru_cache(maxsize=4)
def _haze_layer(w, h, rgb, a_top, a_bottom):
    """An RGBA layer w x h of one colour whose alpha runs linearly from a_top (first row) to a_bottom (last row)."""
    a = np.linspace(a_top, a_bottom, h, dtype=np.float32)
    a8 = (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)[:, None]
    arr = np.empty((h, w, 4), np.uint8)
    arr[..., :3] = rgb
    arr[..., 3] = a8
    return Image.fromarray(arr, "RGBA")


@lru_cache(maxsize=4)
def _vignette_layer(w, h, strength):
    """An RGBA layer w x h of VIGNETTE_COLOUR whose alpha is strength (0..1) at the corners and 0 inside
    VIGNETTE_START of the way out from the centre."""
    xs = (np.arange(w, dtype=np.float32) + 0.5) / (w / 2) - 1
    ys = (np.arange(h, dtype=np.float32) + 0.5) / (h / 2) - 1
    r = np.sqrt(xs[None, :] ** 2 + ys[:, None] ** 2) / math.sqrt(2)
    m = np.clip((r - VIGNETTE_START) / (1 - VIGNETTE_START), 0, 1) ** 2
    arr = np.empty((h, w, 4), np.uint8)
    arr[..., :3] = VIGNETTE_COLOUR
    arr[..., 3] = (m * strength * 255 + 0.5).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


# ---- parallax and sequence ----


def parallax(bg_shot, fg_shot, t, win, dof=0.0, haze=None, vignette=0.0):
    """The frame at t for win = (w, h) as a new RGB image: bg_shot's plate (RGB), blurred by a Gaussian of radius dof
    plate px when dof > 0 (once per plate and radius, then cached), then fg_shot's RGBA cutout on its own move over it
    (None for no cutout), so the two layers drift at different rates; then haze = (colour, alpha_top, alpha_bottom)
    (a vertical colour gradient, see DEFAULT_HAZE; None for none) and vignette (0 to 1, darkening toward the
    corners). Layers are composited as RGBA with Image.alpha_composite.
    dof is measured on the plate, so on screen it grows with the zoom and the plate-to-window scale. It is rounded to
    0.5 px steps: each distinct radius blurs the whole plate once (about 0.17 s on 1152x2016) and the cache keeps 4,
    so animate dof in a few steps, not continuously."""
    s, cx, cy = view(bg_shot, t, win)
    dof = round(float(dof) * 2) / 2
    base = _blurred(bg_shot.plate, dof) if dof > 0 else load(bg_shot.plate)
    out = window(base, s, cx, cy, win).convert("RGBA")
    if fg_shot is not None:
        fs, fx, fy = view(fg_shot, t, win)
        out = Image.alpha_composite(
            out, window(load_rgba(fg_shot.plate), fs, fx, fy, win)
        )
    if haze is not None:
        colour, a_top, a_bottom = haze
        out = Image.alpha_composite(
            out,
            _haze_layer(win[0], win[1], _rgb(colour), float(a_top), float(a_bottom)),
        )
    if vignette > 0:
        out = Image.alpha_composite(
            out, _vignette_layer(win[0], win[1], round(float(min(vignette, 1.0)), 4))
        )
    return out.convert("RGB")


def sequence(shots, t, win, xf, dof=0.0, haze=None, vignette=0.0):
    """The frame at t from a list of Shots played one after another, as a new RGB image. The cut between shots[i] and
    shots[i+1] is at shots[i+1].t0; the two dissolve (transitions.crossfade) over xf seconds centred on the cut, the
    outgoing shot holding its end values and the incoming one its start values meanwhile. A shot that carries `fg`
    is drawn with parallax. dof, haze and vignette are as in parallax. xf must fit between neighbouring cuts, and the
    first cut must sit at least xf / 2 after shots[0].t0 (otherwise frame 0 would already be a blend: a ValueError).
    Give each outgoing shot t1 <= its cut - xf / 2, so its move has finished before the dissolve starts."""
    cuts = [s.t0 for s in shots[1:]]
    if cuts and cuts[0] - xf / 2 < shots[0].t0:
        raise ValueError(
            f"the first cut at {cuts[0]} is within half the crossfade ({xf / 2} s) of the first shot's start "
            f"({shots[0].t0})"
        )
    for a, b in pairwise(cuts):
        if b - a < xf:
            raise ValueError(
                f"cuts at {a} and {b} are closer than the crossfade ({xf} s)"
            )
    i = sum(1 for c in cuts if t >= c + xf / 2)
    if i < len(cuts) and xf > 0 and t > cuts[i] - xf / 2:
        p = (t - (cuts[i] - xf / 2)) / xf
        a = parallax(shots[i], shots[i].fg, t, win, dof, haze, vignette)
        b = parallax(shots[i + 1], shots[i + 1].fg, t, win, dof, haze, vignette)
        return T.crossfade(a, b, p)
    return parallax(shots[i], shots[i].fg, t, win, dof, haze, vignette)
