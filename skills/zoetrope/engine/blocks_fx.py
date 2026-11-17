"""blocks_fx.py : reusable effects for scenes.py: animated backgrounds, a light leak, transitions and camera moves.

Ideas from the block catalogues of HeyGen's hyperframes (light leak, aurora, mesh gradient, fractal noise, starfield,
halftone field, glitch, chromatic radial split, domain warp dissolve, camera dolly zoom, rack focus) and Remotion's
light leaks; every line here is written from the engine's own noise, rng and PIL, no code copied.

Every function is pure: same arguments, same pixels, in any order and process. Seeds go through engine.rng or are
ints (never hash()); colours are parameters whose defaults are the module constants below; engine.W, H and SS are
read when a function is called; nothing here reads a clock, and the only module state is lru_cache of pure results
(built once per size, never changed, never handed out). No text is drawn here.

BACKGROUNDS: f(t, ...) -> RGB image of W*SS x H*SS, a full frame to paste or draw on (convert("RGBA") for a canvas).
    mesh_gradient(t, colors, speed, seed)       colour points that drift slowly, blended smoothly
    aurora(t, colors, sky, bands, speed, seed)  curtains of light with fine rays over a dark sky
    noise_field(t, colors, scale, speed, ...)   fractal noise walking through a colour ramp, optional domain warp
    starfield(t, n, sky, cool, warm, drift ...) seeded stars in three depths, parallax drift, twinkle
    halftone_field(t, color, bg, cell, angle..) a rotated dot grid whose dot size follows a moving noise field
    paper_texture(t, color, grain, fiber ...)   paper: fine grain, fibres, mottling, a slow drifting shade
    diagonal_stripes(t, a, b, width, angle ...) anti-aliased stripes sliding along their normal

OVERLAY: on any rendered frame, not only a background.
    light_leak(img, t, t0, dur, color, hot ...) a warm noise-shaped light that blooms in and retracts (screen blend)

TRANSITIONS: f(a, b, p) -> image, the signature of transitions.py (p = 0 is a, p = 1 is b, pixel for pixel; ease
p yourself, whip_pan and zoom_through ease themselves). Collected in FX_MENU, each with a flash_risk tag: "check"
means run qa.flash_window over its window before the render.
    glitch_slices   bands of the frame jump sideways and swap a for b in steps, with a red/blue split   (check)
    chromatic_split a crossfade whose colour channels zoom apart and back                               (low)
    noise_warp      both frames ripple through a noise displacement while a noise ramp dissolves a to b (low)
    whip_pan        a pan with a motion blur that peaks mid-way                                         (low)
    zoom_through    a punches in past the camera, b settles in behind it, a radial blur between         (low)

CAMERA: k runs 0 to 1 and is eased inside (pass ease= to change it); focus is (x, y) as shares of the frame.
    push_in(img, k)                scale 1 -> scale about focus
    pull_out(img, k)               scale -> 1 about focus
    dolly_zoom(fg, bg, k)          fg (RGBA) grows while bg shrinks, so the world seems to stretch behind it
    rack_focus(fg, bg, k)          blur crosses over from bg to fg (or back) between two layers
    vignette(img)                  soft edge darkening (or tinting)
"""

import math
from functools import lru_cache

import engine as E
import numpy as np
from PIL import Image, ImageChops, ImageFilter

# default colours: the palette of every block here, named so a scene can pass its own
MESH_COLORS = ("#FF6B4A", "#7A5CFF", "#22D3EE", "#FFC857", "#2B3A67")
AURORA_COLORS = ("#3DF5A8", "#4D8DFF", "#B05CFF")
AURORA_SKY = ("#050B1C", "#0B1A33")
NOISE_COLORS = ("#101A3A", "#3B4FA8", "#E6EEFF")
STAR_SKY = ("#060A18", "#101C3C")
STAR_COOL = "#CFE0FF"
STAR_WARM = "#FFE2B8"
HALF_DOT = "#1C2540"
HALF_BG = "#F4EFE4"
PAPER_TONE = "#F2ECDD"
STRIPE_A = "#FF6B4A"
STRIPE_B = "#F7F3EA"
LEAK_WARM = "#FF8A3D"
LEAK_HOT = "#FFE3A8"
VIGNETTE_COLOR = "#000000"

FX_MENU = {}  # name -> function; FX_MENU[name].flash_risk is "low" or "check"


def _menu(flash_risk):
    """Register a transition in FX_MENU under its name, with its flash_risk tag."""

    def reg(fn):
        fn.flash_risk = flash_risk
        FX_MENU[fn.__name__] = (
            fn  # zoetrope: state-ok (the table is filled while the module imports)
        )
        return fn

    return reg


# ---------------------------------------------------------------- shared helpers


def _dims():
    """(w, h, s): the supersampled canvas size and SS, read from the engine at call time."""
    return E.W * E.SS, E.H * E.SS, E.SS


def _rgb(c):
    """A colour (hex string or an (r, g, b) tuple) as float32 (3,)."""
    if isinstance(c, str):
        return np.array(E.hexrgb(c)[:3], np.float32)
    return np.array(tuple(c)[:3], np.float32)


def _low(w, h, long=256):
    """Size of the small grid a smooth field is worked out on: `long` px wide at most, the frame's aspect."""
    lw = min(w, long)
    return lw, max(2, round(lw * h / w))


def _frozen(a):
    a.flags.writeable = False
    return a


@lru_cache(maxsize=8)
def _coords(lw, lh):
    """Pixel-centre shares (u (1, lw), v (lh, 1)) of a lw x lh grid, 0 to 1, read only."""
    u = (np.arange(lw, dtype=np.float32) + 0.5) / lw
    v = (np.arange(lh, dtype=np.float32) + 0.5) / lh
    return _frozen(u[None, :]), _frozen(v[:, None])


def _up(f, w, h):
    """A float (lh, lw, 3) or (lh, lw) array in 0..255 as a PIL image of w x h (bilinear), RGB or L."""
    a = np.clip(f + 0.5, 0, 255).astype(np.uint8)
    im = Image.fromarray(a, "RGB" if a.ndim == 3 else "L")
    return im if im.size == (w, h) else im.resize((w, h), Image.BILINEAR)


def _upf(f, w, h):
    """A float (lh, lw) array scaled to w x h (bilinear), float32, a new array."""
    im = Image.fromarray(np.ascontiguousarray(f, dtype=np.float32), "F")
    return np.asarray(im.resize((w, h), Image.BILINEAR), dtype=np.float32)


@lru_cache(maxsize=4)
def _ramp(c1, c2, h):
    """A vertical ramp c1 -> c2 of h rows as float32 (h, 1, 3), read only."""
    a, b = _rgb(c1), _rgb(c2)
    k = (np.arange(h, dtype=np.float32) + 0.5) / h
    return _frozen(a + (b - a) * k[:, None, None] * np.ones((1, 1, 1), np.float32))


@lru_cache(maxsize=2)
def _sky(c1, c2, w, h):
    """A vertical ramp c1 -> c2 as an RGB image of w x h, built once: copy it before drawing on it."""
    row = np.clip(_ramp(c1, c2, h) + 0.5, 0, 255).astype(np.uint8)
    return Image.fromarray(row, "RGB").resize((w, h), Image.NEAREST)


def _stops(colors, f):
    """Colour ramp through the stops `colors` at the 0..1 field f (any shape): float32 (*f.shape, 3)."""
    cols = np.stack([_rgb(c) for c in colors])
    at = np.linspace(0.0, 1.0, len(cols))
    flat = np.clip(f, 0.0, 1.0).ravel()
    out = np.stack([np.interp(flat, at, cols[:, c]) for c in range(3)], -1)
    return out.reshape(f.shape + (3,)).astype(np.float32)


def _same_mode(img):
    if img.mode not in ("RGB", "RGBA"):
        raise ValueError(f"blocks_fx works on RGB or RGBA images, not {img.mode}")
    return img.mode


# ---------------------------------------------------------------- backgrounds


def mesh_gradient(t, colors=MESH_COLORS, speed=0.1, seed=0):
    """Mesh gradient: one soft colour point per entry of colors, each drifting on slow loops of its own (speed is
    loops a second, about), blended by inverse distance. Pure in t."""
    w, h, _ = _dims()
    n = len(colors)
    g = E.rng("mesh", seed, n)
    base = g.random((n, 2)).astype(np.float32)
    rate = (0.6 + 0.8 * g.random((n, 2))).astype(np.float32)
    phase = (2 * np.pi * g.random((n, 2))).astype(np.float32)
    ang = 2 * np.pi * speed * t * rate + phase
    px = 0.5 + (base[:, 0] - 0.5) * 1.1 + 0.2 * np.sin(ang[:, 0])
    py = 0.5 + (base[:, 1] - 0.5) * 1.1 + 0.2 * np.cos(ang[:, 1])
    lw, lh = _low(w, h, 192)
    u, v = _coords(lw, lh)
    aspect = np.float32(w / h)
    d2 = (aspect * (u - px[:, None, None])) ** 2 + (v - py[:, None, None]) ** 2
    wt = 1.0 / (d2 + 0.03) ** 2
    wt /= wt.sum(0, keepdims=True)
    cols = np.stack([_rgb(c) for c in colors])
    return _up(np.einsum("nhw,nc->hwc", wt, cols), w, h)


def aurora(t, colors=AURORA_COLORS, sky=AURORA_SKY, bands=3, speed=0.2, seed=0):
    """Aurora: `bands` curtains, one colour each (cycling through colors), over a dark sky ramp (sky: top, bottom).
    A curtain has a sharp lower edge that rides a noise curve, a soft glow above it and vertical rays. Pure in t."""
    w, h, _ = _dims()
    lw, lh = _low(w, h, 384)
    u, v = _coords(lw, lh)
    aspect = w / h
    out = np.broadcast_to(_ramp(sky[0], sky[1], lh), (lh, lw, 3)).copy()
    x = u * aspect
    for i in range(bands):
        sd = f"aurora-{seed}-{i}"
        z = t * speed
        cy = 0.62 - 0.1 * i + 0.16 * E.fbm(x * 0.9 + 5.3 * i, 0.37 + i, z + 0.5, 3, sd)
        rays = np.clip(
            0.62 + 0.55 * E.fbm(x * 16 + 3.1 * i, 7.7 + i, z * 1.6 + 4.0, 2, sd), 0, 1.3
        )
        below = np.exp(-(((v - cy) / 0.035) ** 2))
        above = np.exp(-(((cy - v) / 0.2) ** 2))
        prof = np.where(v >= cy, below, above) * rays
        out += (prof * 0.95)[..., None] * _rgb(colors[i % len(colors)])
    return _up(out, w, h)


def noise_field(
    t,
    colors=NOISE_COLORS,
    scale=2.4,
    speed=0.08,
    octaves=3,
    warp=0.0,
    contrast=1.0,
    seed=0,
):
    """Fractal noise field walking slowly through a colour ramp (colors, dark to light, any count of 2 or more).
    scale is features across the frame height; warp above 0 feeds the field through itself (domain warp), 0.5 to
    1.5 gives marble-like folds; contrast stretches the ramp. Pure in t."""
    w, h, _ = _dims()
    lw, lh = _low(w, h, 160)
    u, v = _coords(lw, lh)
    x, y, z = u * (w / h) * scale, v * scale, t * speed
    if warp:
        qx = E.fbm(x + 5.2, y + 1.3, z, 2, seed)
        qy = E.fbm(x + 1.7, y + 9.2, z, 2, seed)
        x, y = x + warp * qx, y + warp * qy
    f = E.fbm(x, y, z, octaves, seed)
    return _up(_stops(colors, 0.5 + 0.85 * contrast * f), w, h)


_DEPTHS = np.array([0.25, 0.55, 1.0], np.float32)
_DEPTH_SHARE = np.array([0.55, 0.3, 0.15])


def starfield(
    t,
    n=260,
    sky=STAR_SKY,
    cool=STAR_COOL,
    warm=STAR_WARM,
    drift=(22.0, 4.0),
    twinkle=0.35,
    seed=0,
):
    """Starfield: n seeded stars in three depths over a sky ramp (sky: top, bottom). drift is px a second of the
    nearest depth, (x, y) in output px at 1x; the far stars move slower (parallax) and are smaller and dimmer.
    Stars wrap at the edges, are drawn as sub-pixel gaussians (no shimmer while they move) and twinkle by
    `twinkle` (0 is steady, 1 goes fully dark). Pure in t."""
    w, h, s = _dims()
    g = E.rng("starfield", seed, n)
    u, v = g.random(n), g.random(n)
    depth = g.choice(_DEPTHS, size=n, p=_DEPTH_SHARE)
    lum, tint = g.random(n), g.random(n)
    rate, phase = 0.15 + 0.6 * g.random(n), 2 * np.pi * g.random(n)
    x = (u * w + drift[0] * s * depth * t) % w
    y = (v * h + drift[1] * s * depth * t) % h
    sig = ((0.7 + 0.8 * depth) * s)[:, None, None]
    amp = (0.45 + 0.55 * depth) * (0.6 + 0.4 * lum)
    amp = amp * (1 - twinkle * (0.5 + 0.5 * np.sin(2 * np.pi * rate * t + phase)))
    r = math.ceil(4.2 * s)
    off = np.arange(-r, r + 1)
    gx = np.floor(x)[:, None] + off  # (n, K) pixel columns
    gy = np.floor(y)[:, None] + off
    wk = np.exp(
        -(
            ((gx - x[:, None])[:, None, :] ** 2 + (gy - y[:, None])[:, :, None] ** 2)
            / (2 * sig**2)
        )
    )
    wk *= amp[:, None, None]
    idx = (
        (gy % h).astype(np.int64)[:, :, None] * w
        + (gx % w).astype(np.int64)[:, None, :]
    ).ravel()
    # sum the gaussians that land on one pixel without a full-frame array: sort, then add up each run
    order = np.argsort(idx, kind="stable")
    si = idx[order]
    first = np.concatenate(([0], np.flatnonzero(np.diff(si)) + 1))
    out = _sky(sky[0], sky[1], w, h).copy()
    for share, color in ((1 - tint, cool), (tint, warm)):
        wt = (wk * share[:, None, None]).ravel()[order]
        m = np.zeros(h * w, np.uint8)
        m[si[first]] = np.clip(np.add.reduceat(wt, first) * 255 + 0.5, 0, 255).astype(
            np.uint8
        )
        out.paste(
            tuple(int(c) for c in _rgb(color)),
            mask=Image.fromarray(m.reshape(h, w), "L"),
        )
    return out


@lru_cache(maxsize=2)
def _dot_grid(w, h, cell, angle, aa):
    """Per pixel, for a dot grid rotated by angle: the distance to its cell centre in levels (px * 255 / aa, float32)
    and its cell's flat index, plus the cell grid (ni, nj, imin, jmin). Built once per size; read only."""
    th = math.radians(angle)
    c, s = np.float32(math.cos(th)), np.float32(math.sin(th))
    x = (np.arange(w, dtype=np.float32) + 0.5)[None, :]
    y = (np.arange(h, dtype=np.float32) + 0.5)[:, None]
    u = (x * c + y * s) / np.float32(cell)
    v = (y * c - x * s) / np.float32(cell)
    i, j = np.floor(u), np.floor(v)
    d = np.hypot(u - i - 0.5, v - j - 0.5) * np.float32(cell * 255 / aa)
    imin, jmin = int(i.min()), int(j.min())
    ni, nj = int(i.max()) - imin + 1, int(j.max()) - jmin + 1
    idx = ((j - jmin) * ni + (i - imin)).astype(np.int32)
    return _frozen(d), _frozen(idx), ni, nj, imin, jmin


def halftone_field(
    t, color=HALF_DOT, bg=HALF_BG, cell=30, angle=30.0, speed=0.12, scale=0.06, seed=0
):
    """Halftone dots on a grid rotated by angle degrees, cell px apart (at 1x); each dot's size follows a noise
    field (scale: field features per cell, speed: how fast it moves), from nothing to dots that touch. Pure in t."""
    w, h, s = _dims()
    aa = 1.2 * s
    d, idx, ni, nj, imin, jmin = _dot_grid(w, h, cell * s, angle, aa)
    ci = (np.arange(ni, dtype=np.float32) + imin + 0.5) * scale
    cj = (np.arange(nj, dtype=np.float32) + jmin + 0.5) * scale
    f = E.fbm(ci[None, :], cj[:, None], t * speed, 2, seed)
    cov = np.clip(0.5 + 0.85 * f, 0.0, 1.0) ** 0.8
    # coverage in levels: (radius - distance) / aa + 0.5, times 255, with distance already in levels
    lvl = (cell * s * 0.74 * cov * (255 / aa) + 127.5).astype(np.float32).ravel()
    m = lvl[idx]
    m -= d
    np.clip(m, 0, 255, out=m)
    out = Image.new("RGB", (w, h), tuple(int(c) for c in _rgb(bg)))
    out.paste(
        tuple(int(c) for c in _rgb(color)),
        mask=Image.fromarray(m.astype(np.uint8), "L"),
    )
    return out


@lru_cache(maxsize=2)
def _paper_static(w, h, seed, grain, fiber, mottle):
    """The part of paper_texture that never moves, as an L image centred on 128 (one level per grey level), read
    only: callers build new images from it."""
    g = E.rng("paper", seed, 0)
    out = grain * g.standard_normal((h, w), dtype=np.float32)
    lw, lh = _low(w, h, 480)
    u, v = _coords(lw, lh)
    a = w / h
    fib = 0.7 * E.fbm(u * a * 6, v * 220, 0.5, 2, f"paper-{seed}-0")
    fib = fib + 0.4 * E.fbm(u * a * 200, v * 7, 0.5, 2, f"paper-{seed}-1")
    out += fiber * 2.2 * _upf(fib, w, h)
    lw, lh = _low(w, h, 96)
    u, v = _coords(lw, lh)
    out += mottle * 2.0 * _upf(E.fbm(u * a * 3, v * 3, 0.5, 3, f"paper-{seed}-2"), w, h)
    return Image.fromarray(np.clip(np.rint(out) + 128, 0, 255).astype(np.uint8), "L")


def paper_texture(
    t, color=PAPER_TONE, grain=4.0, fiber=3.0, mottle=3.5, shade=5.0, seed=0
):
    """Paper: color with fine grain, fibres, soft mottling (each in grey levels of swing) and a very slow drifting
    shade (shade levels) so a long hold is not dead. Pure in t; the static layers are built once per size."""
    w, h, _ = _dims()
    lw, lh = _low(w, h, 64)
    u, v = _coords(lw, lh)
    sh = np.sin(2 * np.pi * (0.55 * u + 0.35 * v - 0.04 * t)) * shade
    low = Image.fromarray(np.clip(np.rint(sh) + 128, 0, 255).astype(np.uint8), "L")
    lum = ImageChops.add(
        _paper_static(w, h, seed, grain, fiber, mottle),
        low.resize((w, h), Image.BILINEAR),
        1.0,
        -128,
    )
    base = Image.new("RGB", (w, h), tuple(int(c) for c in _rgb(color)))
    return ImageChops.add(base, Image.merge("RGB", (lum, lum, lum)), 1.0, -128)


@lru_cache(maxsize=2)
def _stripe_index(w, h, angle):
    """Where each pixel sits along the normal of stripes at angle degrees, in 1/16 px from the smallest, int32
    (h, w), and that smallest in 1/16 px; read only."""
    th = math.radians(angle)
    x = (np.arange(w, dtype=np.float32) + 0.5)[None, :]
    y = (np.arange(h, dtype=np.float32) + 0.5)[:, None]
    q = np.floor((x * np.float32(math.cos(th)) + y * np.float32(math.sin(th))) * 16)
    lo = int(q.min())
    return _frozen((q - lo).astype(np.int32)), lo


def diagonal_stripes(t, a=STRIPE_A, b=STRIPE_B, width=90, angle=-35.0, speed=40.0):
    """Stripes of width px (at 1x), alternating a and b, their edges at angle degrees from vertical's normal, sliding
    along their normal at speed px a second, edges anti-aliased. Pure in t."""
    w, h, s = _dims()
    wd = float(width * s)
    idx, lo = _stripe_index(w, h, angle)
    pos = (
        np.arange(int(idx.max()) + 1) + lo + 0.5
    ) / 16 - speed * s * t  # px along the normal
    tri = np.abs(((pos / (2 * wd)) % 1.0) * 2 - 1)  # 0 mid-stripe a, 1 mid-stripe b
    lut = (np.clip((tri - 0.5) * (wd / (1.2 * s)) + 0.5, 0, 1) * 255).astype(np.uint8)
    out = Image.new("RGB", (w, h), tuple(int(c) for c in _rgb(a)))
    out.paste(tuple(int(c) for c in _rgb(b)), mask=Image.fromarray(lut[idx], "L"))
    return out


BACKGROUNDS = {
    "mesh_gradient": mesh_gradient,
    "aurora": aurora,
    "noise_field": noise_field,
    "starfield": starfield,
    "halftone_field": halftone_field,
    "paper_texture": paper_texture,
    "diagonal_stripes": diagonal_stripes,
}  # name -> function, all f(t, ...) -> RGB W*SS x H*SS


# ---------------------------------------------------------------- light leak


def _screen(img, leak):
    """img with leak (RGB, same size) screen-blended on; alpha untouched."""
    if _same_mode(img) == "RGB":
        return ImageChops.screen(img, leak)
    out = ImageChops.screen(img.convert("RGB"), leak).convert("RGBA")
    out.putalpha(img.getchannel("A"))
    return out


def light_leak(
    img, t, t0, dur, color=LEAK_WARM, hot=LEAK_HOT, strength=0.75, side="left", seed=0
):
    """A warm light that blooms in from one side of the frame and retracts: img with a noise-shaped glow screen
    blended on between t0 and t0 + dur (nothing before or after: a copy of img comes back). The glow's reach and
    brightness follow sin(pi k)^2, so it starts and ends at nothing and cannot flash on its own; keep dur at 0.5 s
    or more and strength under 0.9 over a dark frame. side: left, right, top or bottom; the core goes to hot."""
    _same_mode(img)
    k = E.prog(t, t0, dur)
    if k <= 0 or k >= 1:
        return img.copy()
    env = math.sin(math.pi * k) ** 2
    w, h = img.size
    lw, lh = _low(w, h, 192)
    u, v = _coords(lw, lh)
    aspect = w / h
    along = E.rng("leak", seed, 0).random() * 0.5 + 0.25
    ax, ay = {
        "left": (-0.12, along),
        "right": (1.12, along),
        "top": (along, -0.12),
        "bottom": (along, 1.12),
    }[side]
    n = E.fbm(u * aspect * 2.0 + 3.0, v * 2.0, k * 1.4 + 0.3, 3, f"leak-{seed}")
    dist = np.hypot(aspect * (u - ax), v - ay)
    reach = np.maximum(1.25 * env * (1 + 0.45 * n), 1e-4)
    g = np.clip(1 - dist / reach, 0, 1)
    g = g * g * (3 - 2 * g)
    glow = _rgb(color) * g[..., None] + _rgb(hot) * (g**3)[..., None]
    leak = _up(glow * (strength * (0.4 + 0.6 * env)), w, h)
    return _screen(img, leak)


# ---------------------------------------------------------------- transitions


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


def _split_rgb(img):
    """(bands, alpha or None) of an RGB or RGBA image."""
    bands = img.split()
    return bands[:3], (bands[3] if len(bands) == 4 else None)


@_menu("check")
def glitch_slices(a, b, p, slices=12, shift=0.14, steps=12, seed=0):
    """Glitch: horizontal bands of the frame jump sideways (up to shift of the width, red and blue split apart) and
    change from a to b one band at a time, the pattern re-drawn `steps` times through the window, strongest at
    p = 0.5. The hard steps flicker on purpose: run qa.flash_window over the window."""
    e = _ends(a, b, p)
    if e is not None:
        return e
    w, h = a.size
    g = E.rng("glitch", seed, min(int(p * steps), steps - 1))
    cuts = np.unique(g.integers(1, h, slices - 1))
    edges = [0, *[int(c) for c in cuts], h]
    nb = len(edges) - 1
    thr = 0.2 + 0.6 * g.random(
        nb
    )  # a band is b from this p on: all a before 0.2, all b after 0.8
    jump = (
        (g.random(nb) < 0.65)
        * (g.random(nb) * 2 - 1)
        * shift
        * w
        * math.sin(math.pi * p)
    )
    split = max(1, round(0.012 * w * math.sin(math.pi * p)))
    arr = (np.asarray(a), np.asarray(b))
    out = np.empty_like(arr[0])
    for i in range(nb):
        y0, y1 = edges[i], edges[i + 1]
        seg = arr[1][y0:y1] if p >= thr[i] else arr[0][y0:y1]
        d = round(jump[i])
        if d == 0:
            out[y0:y1] = seg
            continue
        out[y0:y1] = np.roll(seg, d, axis=1)
        out[y0:y1, :, 0] = np.roll(seg[..., 0], d + split, axis=1)
        out[y0:y1, :, 2] = np.roll(seg[..., 2], d - split, axis=1)
    return Image.fromarray(out, a.mode)


def _zoom(img, z, fx, fy, resample=Image.BILINEAR):
    """img scaled by z (1 or more; less is read as 1) about the point (fx, fy) shares of the frame; RGBA is scaled premultiplied, so a
    soft edge gets no dark fringe."""
    if z <= 1:  # only ever scaled up: a smaller z would show the edge of the frame
        return img.copy()
    w, h = img.size
    box = (fx * w * (1 - 1 / z), fy * h * (1 - 1 / z), 0, 0)
    box = (box[0], box[1], box[0] + w / z, box[1] + h / z)
    if img.mode == "RGBA":
        return img.convert("RGBa").resize(img.size, resample, box).convert("RGBA")
    return img.resize(img.size, resample, box)


@_menu("low")
def chromatic_split(a, b, p, amount=0.05, center=(0.5, 0.5)):
    """A crossfade whose red, green and blue channels zoom about center by different amounts (up to `amount` of the
    frame) and settle back, so the colours fringe apart radially mid-way (a chromatic aberration burst)."""
    e = _ends(a, b, p)
    if e is not None:
        return e
    k = p * p * (3 - 2 * p)
    bands, alpha = _split_rgb(Image.blend(a, b, k))
    s = math.sin(math.pi * p) * amount
    fringe = [
        _zoom(bands[c], 1 + s * m, *center) for c, m in enumerate((1.0, 0.5, 0.0))
    ]
    out = Image.merge("RGB", fringe)
    if alpha is not None:
        out.putalpha(alpha)
    return out


@lru_cache(maxsize=4)
def _warp_fields(w, h, gx, gy, scale, seed):
    """(dx, dy) at the (gy + 1, gx + 1) vertices of a mesh over the frame, each in -1..1 and zero on the border, and
    the dissolve ramp (0..1) on a small grid; read only."""
    u = (np.arange(gx + 1, dtype=np.float32) / gx)[None, :]
    v = (np.arange(gy + 1, dtype=np.float32) / gy)[:, None]
    pin = np.sqrt(np.clip(np.sin(np.pi * u), 0, 1) * np.clip(np.sin(np.pi * v), 0, 1))
    a = w / h
    key = f"warp-{seed}"
    dx = np.clip(1.7 * E.fbm(u * a * scale, v * scale, 0.5, 2, key), -1, 1) * pin
    dy = (
        np.clip(1.7 * E.fbm(u * a * scale + 9.1, v * scale + 4.4, 0.5, 2, key), -1, 1)
        * pin
    )
    lw, lh = _low(w, h, 96)
    cu, cv = _coords(lw, lh)
    ramp = 0.5 + 0.5 * np.clip(
        1.7 * E.fbm(cu * a * scale * 0.8, cv * scale * 0.8, 3.5, 3, key), -1, 1
    )
    return (
        _frozen(dx.astype(np.float32)),
        _frozen(dy.astype(np.float32)),
        _frozen(ramp.astype(np.float32)),
    )


def _mesh(img, dx, dy, amount):
    """img with each mesh vertex pulled to its source position displaced by (dx, dy) * amount px (piecewise bilinear)."""
    w, h = img.size
    gy, gx = dx.shape[0] - 1, dx.shape[1] - 1
    xs = np.rint(np.linspace(0, w, gx + 1)).astype(int)
    ys = np.rint(np.linspace(0, h, gy + 1)).astype(int)
    sx = xs[None, :] + dx * amount
    sy = ys[:, None] + dy * amount
    data = []
    for j in range(gy):
        for i in range(gx):
            data.append(
                (
                    (int(xs[i]), int(ys[j]), int(xs[i + 1]), int(ys[j + 1])),
                    (
                        sx[j, i], sy[j, i],
                        sx[j + 1, i], sy[j + 1, i],
                        sx[j + 1, i + 1], sy[j + 1, i + 1],
                        sx[j, i + 1], sy[j, i + 1],
                    ),
                )
            )  # fmt: skip
    return img.transform(img.size, Image.MESH, data, Image.BILINEAR)


@_menu("low")
def noise_warp(a, b, p, strength=0.07, scale=2.5, soft=0.35, seed=0):
    """Domain-warp dissolve: a is pulled out of shape by a noise displacement that grows with p while b settles from
    the same displacement, and a noise ramp (not a flat fade) decides where b appears first. strength is the
    largest displacement as a share of the frame width, scale the noise features across the height, soft the ramp's
    feathering."""
    e = _ends(a, b, p)
    if e is not None:
        return e
    w, h = a.size
    gx = max(4, min(48, w // 24))
    gy = max(3, min(27, h // 24))
    dx, dy, ramp = _warp_fields(w, h, gx, gy, scale, seed)
    amt = strength * w
    m = np.clip((p * (1 + soft) - ramp) / soft, 0, 1)
    if m.max() <= 0:  # b has not shown yet
        return _mesh(a, dx, dy, amt * p)
    if m.min() >= 1:  # a is gone
        return _mesh(b, dx, dy, -amt * (1 - p))
    wa, wb = _mesh(a, dx, dy, amt * p), _mesh(b, dx, dy, -amt * (1 - p))
    return Image.composite(wb, wa, _up(m * 255, w, h))


_FLIP = {
    "left": (None, None),
    "right": (Image.FLIP_LEFT_RIGHT, Image.FLIP_LEFT_RIGHT),
    "up": (Image.TRANSPOSE, Image.TRANSPOSE),
    "down": (
        (Image.TRANSPOSE, Image.FLIP_LEFT_RIGHT),
        (Image.FLIP_LEFT_RIGHT, Image.TRANSPOSE),
    ),
}


def _orient(img, ops):
    for op in (ops,) if not isinstance(ops, tuple) else ops:
        if op is not None:
            img = img.transpose(op)
    return img


@_menu("low")
def whip_pan(a, b, p, direction="left", blur=0.2):
    """A whip pan: a and b sit side by side and the camera sweeps from a to b (content moves in direction: left,
    right, up, down), with a motion blur along the move that peaks in the middle (blur: its widest box, as a share of
    the frame's length along the move). p is linear time; the pan eases itself, so do not ease p."""
    e = _ends(a, b, p)
    if e is not None:
        return e
    if direction not in _FLIP:
        raise ValueError(f"direction {direction!r}: use one of {', '.join(_FLIP)}")
    fwd, back = _FLIP[direction]
    a2, b2 = _orient(a, fwd), _orient(b, fwd)
    w, h = a2.size
    strip = Image.new(a2.mode, (2 * w, h))
    strip.paste(a2, (0, 0))
    strip.paste(b2, (w, 0))
    x0 = round(w * E.ease_in_out_cubic(p))
    rx = round(
        blur * w * 4 * p * (1 - p) / 2
    )  # two passes of rx make a box about blur * w wide
    m = 2 * rx + 2
    lo, hi = max(0, x0 - m), min(2 * w, x0 + w + m)
    piece = strip.crop((lo, 0, hi, h))
    if rx > 0:
        for _ in range(2):
            piece = piece.filter(ImageFilter.BoxBlur((rx, 0)))
    return _orient(piece.crop((x0 - lo, 0, x0 - lo + w, h)), back)


@_menu("low")
def zoom_through(a, b, p, focus=(0.5, 0.5), depth=1.9, blur=0.6, samples=8):
    """Zoom through: a punches in about focus (1 -> depth) while b, already pushed in a third of the way, settles
    back to full size behind it; the two crossfade in the middle under a radial zoom blur (blur: its strength, 0 is
    none; samples: scales averaged). Both frames only ever scale up, so no edge shows."""
    e = _ends(a, b, p)
    if e is not None:
        return e
    fx, fy = focus
    za = 1 + (depth - 1) * p
    zb = 1 + (depth - 1) * 0.35 * (1 - p) ** 2
    k = p * p * (3 - 2 * p)
    sharp = Image.blend(_zoom(a, za, fx, fy), _zoom(b, zb, fx, fy), k)
    bump = math.sin(math.pi * p)
    bw = min(1.0, blur * bump * 1.6)
    if bw <= 0.01 or samples < 2:
        return sharp
    ah, bh = a.reduce(4), b.reduce(4)  # the smear is worked out on quarter-size copies
    acc = None
    for i in range(samples):
        f = 1 + (i / (samples - 1) - 0.5) * 0.22 * blur * bump
        part = np.asarray(
            Image.blend(_zoom(ah, za * f, fx, fy), _zoom(bh, zb * f, fx, fy), k),
            dtype=np.uint16,
        )
        acc = part if acc is None else acc + part
    smear = Image.fromarray(
        ((acc + samples // 2) // samples).astype(np.uint8), a.mode
    ).resize(a.size, Image.BILINEAR)
    return Image.blend(sharp, smear, bw)


# ---------------------------------------------------------------- camera moves


def push_in(img, k, scale=1.2, focus=(0.5, 0.5), ease=E.ease_in_out_cubic):
    """Camera push in: img at scale 1 when k = 0, scaled up to `scale` about focus when k = 1 (eased). Never shows
    an edge, because it only scales up."""
    return _zoom(img, 1 + (scale - 1) * ease(E.clamp(k)), *focus, Image.BICUBIC)


def pull_out(img, k, scale=1.2, focus=(0.5, 0.5), ease=E.ease_in_out_cubic):
    """Camera pull out: img scaled up to `scale` about focus when k = 0, back at scale 1 when k = 1 (eased)."""
    return _zoom(img, scale - (scale - 1) * ease(E.clamp(k)), *focus, Image.BICUBIC)


def _over(fg, bg):
    """fg (RGBA) over bg, in bg's mode."""
    out = Image.alpha_composite(bg.convert("RGBA"), fg.convert("RGBA"))
    return out if bg.mode == "RGBA" else out.convert(bg.mode)


def dolly_zoom(fg, bg, k, strength=0.3, focus=(0.5, 0.5), ease=E.ease_in_out_cubic):
    """Dolly zoom feel: the subject layer fg (RGBA) grows from 1 to 1 + strength about focus while the background
    shrinks the other way, so the two scales multiply to the same 1 + strength all through: the world stretches
    behind the subject. bg is already zoomed by 1 + strength at k = 0 (so it can shrink without showing an edge):
    pass a bg drawn a little larger than the action. Returns bg's mode."""
    e = ease(E.clamp(k))
    zf = 1 + strength * e
    return _over(_zoom(fg, zf, *focus), _zoom(bg, (1 + strength) / zf, *focus))


def _soft(img, r):
    """img blurred by a gaussian of radius r px (premultiplied for RGBA); a copy at r under 0.3. A wide blur is
    worked out on a 2x or 4x smaller copy (the blur hides the loss), which is several times faster."""
    if r < 0.3:
        return img.copy()
    f = 1 if r < 6 else 2 if r < 16 else 4
    small = img.convert("RGBa") if img.mode == "RGBA" else img
    if f > 1:
        small = small.reduce(f)
    small = small.filter(ImageFilter.GaussianBlur(r / f))
    if f > 1:
        small = small.resize(img.size, Image.BILINEAR)
    return small.convert("RGBA") if img.mode == "RGBA" else small


def rack_focus(fg, bg, k, blur=22.0, start="fg", ease=E.ease_in_out_cubic):
    """Rack focus between a foreground layer fg (RGBA) and a background bg: at k = 0 the `start` layer ("fg" or "bg")
    is sharp and the other blurred by `blur` px (gaussian radius), at k = 1 the focus has moved to the other one,
    the blurs crossing over between. Returns bg's mode."""
    if start not in ("fg", "bg"):
        raise ValueError(f"start {start!r}: use fg or bg")
    e = ease(E.clamp(k))
    to_fg = e if start == "bg" else 1 - e  # 1 when the foreground is the sharp one
    return _over(_soft(fg, blur * (1 - to_fg)), _soft(bg, blur * to_fg))


@lru_cache(maxsize=4)
def _vignette_mask(w, h, strength, softness):
    """The multiply mask of a vignette as an L image: 255 in the middle, 255 * (1 - strength) at the corners."""
    x = ((np.arange(w, dtype=np.float32) + 0.5) / w * 2 - 1)[None, :]
    y = ((np.arange(h, dtype=np.float32) + 0.5) / h * 2 - 1)[:, None]
    r = np.sqrt((x * x + y * y) / 2)  # 0 in the middle, 1 at the corners
    f = np.clip((r - (1 - softness)) / max(softness, 1e-3), 0, 1)
    f = f * f * (3 - 2 * f)
    return Image.fromarray(np.rint(255 * (1 - strength * f)).astype(np.uint8), "L")


def vignette(img, strength=0.45, softness=0.7, color=VIGNETTE_COLOR):
    """Vignette: the edges of img pulled toward color (black by default) by up to `strength` at the corners,
    starting (1 - softness) of the way out. Alpha untouched."""
    _same_mode(img)
    mask = _vignette_mask(
        img.width, img.height, round(float(strength), 4), round(float(softness), 4)
    )
    fill = tuple(int(c) for c in _rgb(color))
    rgb = img.convert("RGB")
    out = Image.composite(rgb, Image.new("RGB", rgb.size, fill), mask)
    if img.mode == "RGB":
        return out
    out = out.convert("RGBA")
    out.putalpha(img.getchannel("A"))
    return out
