# transitions.py : scene-to-scene transitions as pure f(a, b, p) -> Image, ported from gl-transitions to PIL and numpy.
# a and b are two frames of one size and mode (RGB or RGBA) and p runs 0 -> 1 through the window (scenes_at's mix):
# p = 0 returns a and p = 1 returns b, pixel for pixel, and the inputs are never changed. Ease p yourself, for
# example wipe(a, b, ease_in_out_cubic(mix)). flash_risk "check" means the transition can swing luminance hard
# (dip to white between dark scenes): run qa.flash_window over its window before the render.
import math

import numpy as np
from PIL import Image, ImageColor

MENU = {}  # name -> function; MENU[name].flash_risk is "low" or "check"
STEP = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}


def _menu(flash_risk):
    """Register a transition in MENU under its name, with its flash_risk tag."""

    def reg(fn):
        fn.flash_risk = flash_risk
        MENU[fn.__name__] = fn
        return fn

    return reg


def _ends(a, b, p):
    """A copy of a at p <= 0 and of b at p >= 1, else None; also checks that the two frames can be mixed."""
    if a.size != b.size or a.mode != b.mode:
        raise ValueError(
            f"a transition needs two frames of one size and mode: {a.mode} {a.size}, {b.mode} {b.size}"
        )
    if p <= 0:
        return a.copy()
    if p >= 1:
        return b.copy()
    return None


def _step(direction):
    if direction not in STEP:
        raise ValueError(f"direction {direction!r}: use one of {', '.join(STEP)}")
    return STEP[direction]


def _through(a, b, alpha):
    """b over a through alpha: a float array that broadcasts to (h, w), clipped to 0..1. The mask is rounded to
    uint8 before it is broadcast, so a wipe's one row of alpha never becomes a full float frame."""
    w, h = a.size
    m = np.round(np.clip(alpha, 0, 1) * 255).astype(np.uint8)
    m = np.ascontiguousarray(np.broadcast_to(m, (h, w)))
    return Image.composite(b, a, Image.fromarray(m, "L"))


def _axis(a, direction):
    """Pixel-centre positions along the direction of travel (0 at the side the edge leaves from) and their count."""
    dx, _ = _step(direction)
    w, h = a.size
    n = w if dx else h
    pos = np.arange(n) + 0.5
    if direction in ("left", "up"):
        pos = n - pos
    return (pos.reshape(1, n) if dx else pos.reshape(n, 1)), n


def _centres(n, c):
    """float32 pixel-centre offsets from c along one axis: the iris and clock grids at half the cost of float64."""
    return np.arange(n, dtype=np.float32) + np.float32(0.5 - c)


def _edge(pos, length, p, soft):
    """Revealed share at each position for an edge p of the way along length, feathered over soft (same units)."""
    if soft <= 0:
        return (pos < p * length).astype(np.float32)
    return (p * (length + soft) - pos) / soft


@_menu("low")
def crossfade(a, b, p):
    """Dissolve: b blended over a by p."""
    e = _ends(a, b, p)
    return e if e is not None else Image.blend(a, b, p)


@_menu("low")
def wipe(a, b, p, direction="right", soft=0):
    """b revealed behind an edge travelling in direction (left, right, up, down); soft feathers the edge, in px."""
    e = _ends(a, b, p)
    if e is not None:
        return e
    pos, n = _axis(a, direction)
    return _through(a, b, _edge(pos, n, p, soft))


@_menu("low")
def push(a, b, p, direction="left"):
    """b pushes a out of the frame, both moving in direction."""
    e = _ends(a, b, p)
    if e is not None:
        return e
    (dx, dy), (w, h) = _step(direction), a.size
    ox, oy = round(p * w) * dx, round(p * h) * dy
    out = Image.new(a.mode, a.size)
    out.paste(a, (ox, oy))
    out.paste(b, (ox - dx * w, oy - dy * h))
    return out


@_menu("low")
def slide(a, b, p, direction="left"):
    """b slides in over a, which holds still, moving in direction."""
    e = _ends(a, b, p)
    if e is not None:
        return e
    (dx, dy), (w, h) = _step(direction), a.size
    out = a.copy()
    out.paste(b, (round(p * w) * dx - dx * w, round(p * h) * dy - dy * h))
    return out


@_menu("low")
def iris(a, b, p, center=None, soft=1.5):
    """b inside a circle that opens from center (x, y), default the frame centre, until it covers the frame; soft
    feathers the rim, in px."""
    e = _ends(a, b, p)
    if e is not None:
        return e
    w, h = a.size
    cx, cy = center if center is not None else (w / 2, h / 2)
    reach = max(math.hypot(x - cx, y - cy) for x in (0, w) for y in (0, h))
    xx, yy = _centres(w, cx), _centres(h, cy)[:, None]
    return _through(a, b, _edge(np.hypot(xx, yy), reach, p, soft))


@_menu("low")
def clock(a, b, p, center=None, start=-90, soft=0.5):
    """b swept in by a clock hand turning clockwise from start degrees (-90 is twelve o'clock) around center;
    soft feathers the hand, in degrees."""
    e = _ends(a, b, p)
    if e is not None:
        return e
    w, h = a.size
    cx, cy = center if center is not None else (w / 2, h / 2)
    xx, yy = _centres(w, cx), _centres(h, cy)[:, None]
    ang = (np.degrees(np.arctan2(yy, xx)) - start) % 360
    return _through(a, b, _edge(ang, 360, p, soft))


@_menu("low")
def blinds(a, b, p, n=8, direction="down", soft=0):
    """b revealed through n slats that all wipe open at once in direction (venetian blinds); soft in px."""
    e = _ends(a, b, p)
    if e is not None:
        return e
    pos, length = _axis(a, direction)
    # whole-pixel slats, so no pixel centre sits on a slat's starting edge (it would open at any p > 0)
    edges = np.floor(np.arange(n + 1) * length / n + 0.5)
    s = (np.searchsorted(edges, pos.ravel(), side="right") - 1).reshape(pos.shape)
    return _through(a, b, _edge(pos - edges[s], edges[s + 1] - edges[s], p, soft))


@_menu("check")
def dip(a, b, p, color="#000000"):
    """a fades to a flat colour by p = 0.5, then the colour fades to b (dip to black, dip to white). A dip to white
    between dark scenes swings luminance hard: run qa.flash_window over the window."""
    e = _ends(a, b, p)
    if e is not None:
        return e
    if isinstance(color, str):
        fill = ImageColor.getcolor(color, a.mode)
    else:
        fill = (tuple(color) + (255,))[: len(a.getbands())]
    c = Image.new(a.mode, a.size, fill)
    return Image.blend(a, c, p * 2) if p < 0.5 else Image.blend(c, b, p * 2 - 1)


@_menu("low")
def luma(a, b, p, ramp, soft=0.1):
    """b revealed where ramp is below p, so any gradient, shape or noise picture becomes a wipe (gl-transitions
    luma). ramp: an L image or a 0..1 array of the frame's size; soft widens the edge, in ramp units."""
    e = _ends(a, b, p)
    if e is not None:
        return e
    r = np.asarray(ramp, np.float32)
    if isinstance(ramp, Image.Image) or np.asarray(ramp).dtype == np.uint8:
        r = r / 255
    if r.shape != (a.size[1], a.size[0]):
        raise ValueError(f"ramp is {r.shape[::-1]} but the frames are {a.size}")
    return _through(a, b, _edge(r, 1, p, soft))
