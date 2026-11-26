# lint_blend.py : planted faults for Q1207 (qa_lint.run), the ways a see-through colour fails to blend through
# ImageDraw: a blending ImageDraw asked for on an RGBA picture (through a helper, as it happened on 2026-11-10: the
# picture is RGBA where draw() calls it), the same in a scene function reached through the scene table, a see-through
# fill through a plain ImageDraw on the RGBA canvas (a tuple, a hex colour with an alpha, a plain ImageDraw that a
# helper returns, under a check that the colour shows), one through a plain ImageDraw on an RGB picture, and
# see-through text, which never blends. Every other line must stay silent: the selftest counts the findings. Never
# drawn: the lint reads it and imports it.
from engine import canvas, finish
from PIL import Image, ImageDraw

SCHEDULE = {"a": (0.0, 1.0)}
DURATION = 1.0
BPM = 120
INK = (240, 236, 220)
PAPER = "#101820"
SHADE = (0, 0, 0, 110)
GLASS = "#F0ECDC40"


def pen(img):
    # Q1207: img is the RGBA canvas where draw() calls this, so nothing blends
    return ImageDraw.Draw(img, "RGBA")


def plain_pen(img):
    return ImageDraw.Draw(img)


def measure(img, t):
    pen(img).line((40, 40, 400, 40), fill=(*INK, int(255 * (1 - t))), width=6)


def scene_rule(img, t):
    # Q1207: img is the RGBA canvas that draw() hands every scene in SCENES
    d = ImageDraw.Draw(img, "RGBA")
    d.line((40, 60, 400, 60), fill=(*INK, 90), width=6)


SCENES = {"rule": scene_rule}


def draw(t):
    img = canvas(PAPER)
    measure(img, t)
    SCENES["rule"](img, t)
    d = ImageDraw.Draw(img)
    # Q1207: a see-through colour replaces the canvas pixel
    d.rectangle((40, 80, 400, 120), fill=SHADE)
    # Q1207: so does a hex colour with an alpha
    d.rectangle((40, 130, 400, 170), fill=GLASS)
    a = int(255 * (1 - t))
    if a > 0:
        # Q1207: and one drawn through the plain ImageDraw a helper returns; a check that it shows holds nothing
        plain_pen(img).ellipse((40, 180, 80, 220), fill=(*INK, a))
    flat = Image.new("RGB", img.size, INK)
    # Q1207: the alpha is dropped on RGB
    ImageDraw.Draw(flat).ellipse((0, 0, 90, 90), fill=(*INK, 128))
    soft = ImageDraw.Draw(flat, "RGBA")
    # Q1207: text never blends, even through the ImageDraw that blends shapes
    soft.text((0, 100), "x", fill=(*INK, 128))  # zoetrope: text-ok
    soft.rectangle((0, 200, 90, 290), fill=(*INK, 128))
    return finish(img)
