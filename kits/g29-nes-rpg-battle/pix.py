# pix.py : 320x180 palette-index canvas. Every pixel is an index into the strict NES-like palette,
# so the frame can only ever contain palette colours. Bayer 4x4 for every gradient. No blending.
import numpy as np
from PIL import Image, ImageDraw

import font5x7 as F

CW, CH = 320, 180  # drawn size; the engine scales x6 nearest to 1920x1080
HEX = [
    "#000000",
    "#FCFCFC",
    "#7C7C7C",
    "#BCBCBC",
    "#3C3C3C",  # 0 black 1 white 2 grey 3 lgrey 4 dgrey
    "#0000BC",
    "#0058F8",
    "#3CBCFC",
    "#A4E4FC",  # 5 navy 6 blue 7 sky 8 pale
    "#4428BC",
    "#6844FC",
    "#9878F8",
    "#D8B8F8",
    "#200838",  # 9 v1 10 v2 11 v3 12 v4 13 dark violet
    "#D800CC",
    "#F878F8",
    "#A81000",
    "#F83800",
    "#F8B800",  # 14 magenta 15 pink 16 red 17 orange 18 gold
    "#FCE0A8",
    "#00A800",
    "#58D854",  # 19 peach 20 green 21 lime
]
PAL = np.array([[int(h[i : i + 2], 16) for i in (1, 3, 5)] for h in HEX], np.uint8)
NAMES = "K W g l d N B S P v V u U D M p R O Y e G L".split()
C = {n: i for i, n in enumerate(NAMES)}  # sprite key -> palette index
(
    BLACK,
    WHITE,
    GREY,
    LGREY,
    DGREY,
    NAVY,
    BLUE,
    SKY,
    PALE,
    V1,
    V2,
    V3,
    V4,
    DVIO,
    MAGENTA,
    PINK,
    RED,
    ORANGE,
    GOLD,
    PEACH,
    GREEN,
    LIME,
) = range(22)

BAYER = np.array(
    [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], np.uint8
)
BY = np.tile(BAYER, (CH // 4, CW // 4))  # per-pixel threshold 0..15
YY, XX = np.mgrid[0:CH, 0:CW]


def new(color=BLACK):
    return np.full((CH, CW), color, np.uint8)


def to_rgb(idx):
    return PAL[idx]


def to_image(idx, W=1920, H=1080):
    rgb = PAL[idx]
    sx, sy = W // CW, H // CH
    if sx == sy and W == CW * sx and H == CH * sy:
        return Image.fromarray(rgb.repeat(sy, 0).repeat(sx, 1), "RGB")
    return Image.fromarray(rgb, "RGB").resize((W, H), Image.NEAREST)


def dith(f):
    """Bayer mask for coverage f (0..1): True where the second colour shows."""
    return BY < np.clip(f, 0, 1) * 16


def vgrad(c, y0, y1, stops, x0=0, x1=CW):
    """Vertical dithered gradient on rows y0..y1 through stops [(pos 0..1, colour), ...]."""
    ys = np.arange(y0, y1)
    p = (ys - y0) / max(1, (y1 - y0 - 1))
    pos = np.array([s[0] for s in stops], float)
    col = np.array([s[1] for s in stops])
    j = np.clip(np.searchsorted(pos, p, side="right") - 1, 0, len(stops) - 2)
    f = (p - pos[j]) / np.maximum(1e-9, pos[j + 1] - pos[j])
    c0, c1 = col[j][:, None], col[j + 1][:, None]
    m = BY[y0:y1, x0:x1] < (np.clip(f, 0, 1) * 16)[:, None]
    c[y0:y1, x0:x1] = np.where(m, c1, c0)


def rect(c, x0, y0, x1, y1, color):
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    x1, y1 = min(CW, int(x1)), min(CH, int(y1))
    if x1 > x0 and y1 > y0:
        c[y0:y1, x0:x1] = color


def box(c, x0, y0, x1, y1, fill=NAVY, border=WHITE):
    """NES window: black edge, white 1 px border, fill. Corners clipped one pixel."""
    rect(c, x0, y0, x1, y1, BLACK)
    rect(c, x0 + 1, y0 + 1, x1 - 1, y1 - 1, border)
    rect(c, x0 + 2, y0 + 2, x1 - 2, y1 - 2, fill)
    for x, y in (
        (x0 + 1, y0 + 1),
        (x1 - 2, y0 + 1),
        (x0 + 1, y1 - 2),
        (x1 - 2, y1 - 2),
    ):
        if 0 <= x < CW and 0 <= y < CH:
            c[y, x] = BLACK


def put_mask(c, m, x, y, color, where=None):
    """Write colour where boolean mask m is set, mask top-left at (x, y); clipped to canvas."""
    x, y = int(x), int(y)
    h, w = m.shape
    sx0, sy0 = max(0, -x), max(0, -y)
    sx1, sy1 = min(w, CW - x), min(h, CH - y)
    if sx1 <= sx0 or sy1 <= sy0:
        return
    sub = m[sy0:sy1, sx0:sx1]
    if where is not None:
        sub = sub & where[y + sy0 : y + sy1, x + sx0 : x + sx1]
    reg = c[y + sy0 : y + sy1, x + sx0 : x + sx1]
    if np.isscalar(color) or np.ndim(color) == 0:
        reg[sub] = color
    else:
        reg[sub] = np.asarray(color)[sy0:sy1, sx0:sx1][sub]


def outline_of(m):
    """Auto-outline: 1 px ring (8-neighbour) around mask m, returned padded by 1 px on each side."""
    p = np.pad(m, 1)
    d = p.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            d |= np.roll(np.roll(p, dy, 0), dx, 1)
    return d & ~p


def sprite(c, spr, x, y, flip=False, lut=None, outline=BLACK, solid=None, where=None):
    """Blit an index sprite (255 = transparent) with an automatic 1 px outline. solid paints every pixel one colour."""
    a = spr[:, ::-1] if flip else spr
    m = a != 255
    if outline is not None:
        put_mask(c, outline_of(m), x - 1, y - 1, outline, where)
    if solid is not None:
        put_mask(c, m, x, y, solid, where)
        return
    col = a if lut is None else lut[a]
    put_mask(c, m, x, y, col, where)


def text(c, s, x, y, color=WHITE, scale=1, outline=None, boxes=None, tag=None):
    """Bitmap text, top-left at (x, y). Records (tag, box in canvas px, colour) for the QA gates."""
    m = F.mask(s, scale)
    if outline is not None:
        put_mask(c, outline_of(m), x - 1, y - 1, outline)
    put_mask(c, m, x, y, color)
    if boxes is not None:
        boxes.append(
            (
                tag or s,
                (int(x), int(y), int(x) + m.shape[1], int(y) + m.shape[0]),
                color,
            )
        )
    return F.width(s, scale)


def text_c(c, s, cx, y, color=WHITE, scale=1, **kw):
    return text(c, s, cx - F.width(s, scale) // 2, y, color, scale, **kw)


def text_r(c, s, rx, y, color=WHITE, scale=1, **kw):
    return text(c, s, rx - F.width(s, scale), y, color, scale, **kw)


def disc(r):
    yy, xx = np.mgrid[-r : r + 1, -r : r + 1]
    return xx * xx + yy * yy <= r * r + r * 0.6


def ring(ro, ri):
    """Annulus mask sized like disc(ro)."""
    d = ro - ri
    return disc(ro) & ~np.pad(disc(ri), d)


def ellipse_mask(rx, ry):
    yy, xx = np.mgrid[-ry : ry + 1, -rx : rx + 1]
    return (xx / max(rx, 0.5)) ** 2 + (yy / max(ry, 0.5)) ** 2 <= 1.0


def line(c, x0, y0, x1, y1, color, where=None):
    """Bresenham line, hard pixels."""
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    dx, dy = abs(x1 - x0), -abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx + dy
    while True:
        if 0 <= x0 < CW and 0 <= y0 < CH and (where is None or where[y0, x0]):
            c[y0, x0] = color
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def poly_mask(pts):
    im = Image.new("L", (CW, CH), 0)
    ImageDraw.Draw(im).polygon([(int(x), int(y)) for x, y in pts], fill=1)
    return np.asarray(im, bool)


def parse(rows, keymap=None):
    """Sprite from strings; '.' is transparent (255). Keys are palette names in NAMES."""
    km = keymap or C
    a = np.full((len(rows), len(rows[0])), 255, np.uint8)
    for y, r in enumerate(rows):
        assert len(r) == len(rows[0]), (y, r)
        for x, ch in enumerate(r):
            if ch != ".":
                a[y, x] = km[ch]
    return a


def lut_from(pairs):
    lut = np.arange(256, dtype=np.uint8)
    for a, b in pairs.items():
        lut[a] = b
    return lut
