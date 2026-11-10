# scenes.py : "Pip wants the star", the first build of the toy-studio 3D card. The picture is a 3D plate (stage.py,
# rendered by plate3d.py); draw(t) reads its frame for t, lays the captions and the sparkles over it, and stays
# pure. All timing lives in beats.py, which the stage script reads too.
import math

import beats as B
import plate3d
from PIL import Image, ImageDraw

import engine as E

E.W, E.H, E.FPS = B.SIZE[0], B.SIZE[1], B.FPS  # before W, H and SS are copied from it
from engine import (
    SS,
    H,
    Scene,
    W,
    compile_schedule,
    ease_out_cubic,
    finish,
    lerp,
    prog,
    rng,
    rrect,
    shadow,
    text,
    text_box,
)

INK, WHITE = "#1c1a3a", "#ffffff"
SPARK = (255, 255, 255)
FONT = "Nunito:800"
SIZE, BIG = 58, 80  # caption and end-card type, px at 1080
PAD = (34, 22)  # the pill round a caption: x and y, px

TIMELINE = [Scene(name, d) for name, d in B.SCENES]
SCHEDULE, DURATION, CUTS, WINDOWS, _ = compile_schedule(TIMELINE)  # frame-exact
BPM = B.BPM
CARD = "toy-studio-3d"
PLATE = plate3d.Plate("main")
PLATE.need(DURATION)

# every moment the picture and the sound share: the cuts, and what Pip, the crate and the star do
CUES = [(c, f"cut to {n}", "both") for c, n in zip(CUTS, list(SCHEDULE)[1:])] + [
    (B.HOP_LAND, "hop", "both"),
    (B.LAND, "lands short", "both"),
    (B.CRATE_STOP, "crate stops", "both"),
    (B.IDEA, "idea", "both"),
    (B.ON_CRATE, "onto the crate", "both"),
    {"t": B.TOUCH, "label": "catches the star", "kind": "both", "payoff": True},
    (B.HOME, "lands with the star", "both"),
    *((b, f"bounce {i + 1}", "both") for i, b in enumerate(B.BOUNCES)),
]
CUE_LAG = 0
KEY_TIMES = [
    (B.LAND - B.JUMP_AIR / 2, "the top of the jump that misses"),
    (B.LAND + 1.0, "the slump"),
    (B.IDEA + 0.1, "the idea"),
    (B.TOUCH, "the catch"),
    (B.HOME + 0.5, "the happy eyes"),
]


def spots():
    """Where each caption sits, by line: (centre x or left x, centre y, size, anchor). The first two share the empty
    wall top left; the third hangs by Pip's head, placed once from the plate's track so it holds still to be read;
    the end card takes the right two thirds."""
    hx, hy = PLATE.at("pip", 8.625) or (W * SS * 0.4, H * SS * 0.5)
    by_head = (min(W * 0.8, hx / SS + W * 0.23), max(H * 0.16, hy / SS - H * 0.24))
    return [
        (W * 0.075, H * 0.15, SIZE, "lm"),
        (W * 0.075, H * 0.15, SIZE, "lm"),
        (*by_head, SIZE, "mm"),
        (W * 0.68, H * 0.5, BIG, "mm"),
    ]


SPOTS = spots()


def captions(t):
    """Every caption on screen at t: [(text, xy, size, anchor, alpha)]. draw() paints exactly this and text_items()
    reports exactly this."""
    out = []
    for (s, t0, t1), (x, y, size, anchor) in zip(B.LINES, SPOTS):
        if not t0 <= t < t1 and not (t1 >= DURATION and t >= t0):
            continue
        k = (
            1.0 if t0 == 0 else ease_out_cubic(prog(t, t0, 0.2))
        )  # frame 0 is the thumbnail: already there
        out.append((s, (x, y + lerp(18, 0, k)), size, anchor, k))
    return out


def text_items(t):
    """Registry for qa.py: every text drawn at time t, with its box in output pixels, colour, alpha and size."""
    return [
        {
            "s": s,
            "box": text_box(s, xy, size, anchor, FONT),
            "fg": WHITE,
            "alpha": a,
            "px": size,
            "bold": True,
        }
        for s, xy, size, anchor, a in captions(t)
    ]


def sparkles(img, t):
    """Ten four-point sparks flying out of the star when Pip catches it. They start where the plate says the star is
    on screen in that frame, so they leave from the star even while it is carried."""
    k = prog(t, B.TOUCH, 0.75)
    at = PLATE.at("star", t)
    if not 0 < k < 1 or at is None:
        return
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d, g = ImageDraw.Draw(lay), rng("sparkles")
    for i in range(10):
        # three quarters of the circle, up and to the right: none fly down-left over the face of who caught it
        ang = math.radians(200 + 260 * (i + 0.6 * g.random()) / 10)
        far = (
            (0.1 + (0.08 + 0.1 * g.random()) * ease_out_cubic(k)) * H * SS
        )  # from the star's rim outward
        r = (0.02 + 0.015 * g.random()) * H * SS * (1 - k) ** 0.6
        cx, cy = at[0] + far * math.cos(ang), at[1] + far * math.sin(ang)
        pts = [
            (
                cx + (r if j % 2 == 0 else r * 0.28) * math.cos(math.pi * j / 4),
                cy + (r if j % 2 == 0 else r * 0.28) * math.sin(math.pi * j / 4),
            )
            for j in range(8)
        ]
        d.polygon(pts, fill=(*SPARK, int(255 * (1 - k) ** 0.5)))
    img.alpha_composite(lay)


def draw(t):
    img = PLATE.frame(t)
    sparkles(img, t)
    for s, xy, size, anchor, a in captions(t):
        l, top, r, b = text_box(s, xy, size, anchor, FONT)
        pill = (l - PAD[0], top - PAD[1], r + PAD[0], b + PAD[1])
        shadow(img, pill, 26, blur=18, dy=8, alpha=0.22 * a)
        rrect(img, pill, 26, INK, 0.94 * a)
        text(img, s, xy, size, WHITE, anchor, a, FONT)
    return finish(img)
