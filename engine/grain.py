# grain.py : film grain as a few seeded noise tiles, stepped at a fraction of the frame rate (Z14). Fresh full-frame
# noise on every frame is what made the 140 MB master; a grain held for 2 frames and cut from 4 tiles costs far less.
from functools import lru_cache

import contract as C
import numpy as np
from PIL import Image

import engine as E

TILE = 256  # tile side in px; the tile repeats across the frame, invisible at std 1.6


@lru_cache(maxsize=32)
def _tile(seed, tiles, k):
    """Tile k of `tiles`: standard normal noise from its own seed, made once per process."""
    rng = np.random.default_rng([seed, 0, tiles, k])
    return rng.standard_normal((TILE, TILE), dtype=np.float32)


def _step_tile(t, hz, tiles, seed):
    """The tile for t's step, rolled by the step's whole-pixel offset: every frame inside one step gets the same
    grain. hz 0 is one step for the whole film."""
    s = C.stepped(t, hz) if hz else 0
    k, oy, ox = (
        int(v)
        for v in np.random.default_rng([seed, 1, s]).integers((tiles, TILE, TILE))
    )
    return np.roll(_tile(seed, tiles, k), (oy, ox), (0, 1))


def _cover(tile, h, w, ch):
    """tile (TILE, TILE) given ch channels and repeated over h x w. Built at tile size first, so the full-frame add
    runs on contiguous rows (broadcasting over the 3-sample channel axis made it 3x slower)."""
    if ch:
        tile = np.repeat(tile[..., None], ch, 2)
    reps = (-(-h // TILE), -(-w // TILE)) + ((1,) if ch else ())
    return np.tile(tile, reps)[:h, :w]


def grain(img, t, std=1.6, hz=None, tiles=4, seed=0):
    """Grain for frame time t: std grey levels of noise, the same on every colour channel, stepped hz times a second
    (default fps / 2, so each grain is held exactly 2 frames at any fps; 12 Hz at 30 fps would hold 3, 2, 3, 2).
    Pure in t. img is an RGB, RGBA or L PIL image (a new image comes back) or a numpy array (H, W) or (H, W, 3)
    (a new float32 array comes back, grain added, not clipped). Call it last, after any whole-pixel weave shift,
    so the grain stays put while the picture weaves."""
    hz = E.FPS / 2 if hz is None else hz
    tile = _step_tile(t, hz, tiles, seed)
    if isinstance(img, Image.Image):
        a = np.asarray(img, dtype=np.int16)  # a fresh, writable copy (uint8 to int16)
        q = np.rint(tile * std).astype(np.int16)
        if a.ndim == 2:
            a += _cover(q, *a.shape, 0)
        else:
            a[..., :3] += _cover(q, *a.shape[:2], 3)  # alpha, if any, untouched
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), img.mode)
    a = np.asarray(img, np.float32)
    return a + _cover(tile * np.float32(std), *a.shape[:2], 3 if a.ndim == 3 else 0)
