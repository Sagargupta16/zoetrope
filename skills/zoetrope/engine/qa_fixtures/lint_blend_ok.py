# lint_blend_ok.py : what Q1207 must leave alone (qa_lint.run): a blending ImageDraw on an RGB picture; a transparent
# layer that is composited, with its clear colour named here, in the palette module beside this file and behind the
# parameter of a layer maker; a layer that comes back from a helper it was handed to; a layer that starts
# see-through; a mask; an opaque colour and an erase (alpha 0) on the RGBA canvas; an alpha name that holds 255; a
# helper that draws opaque on the canvas and see-through only on a layer; one that draws straight on only where a
# test of its own alpha finds it full, and through a layer otherwise; a def under a decorator that hands it a fresh
# layer; a pen helper that asks for the mode only on an RGB picture; a card layer with a smaller opaque picture
# pasted at its corner; a see-through outline at width 0, which Pillow does not draw; a table of effects called by a
# constant key, one of them on a layer; an alpha that folds to 255 through ** and math.floor; a window cut in an
# opaque picture by a helper that returns it, with a tint drawn into the window; a colour helper with its alpha left
# at the default; a picture that an if/else makes in two modes; and a helper whose picture the lint cannot name.
# Never drawn: the lint reads it and imports it.
import math

import lint_blend_look as L
from engine import canvas, finish, hexrgb
from PIL import Image, ImageDraw, ImageFilter

SCHEDULE = {"a": (0.0, 1.0)}
DURATION = 1.0
BPM = 120
INK = (240, 236, 220)
PAPER = "#101820"
CLEAR = (0, 0, 0, 0)
TINT = (*INK, 40)
OPAQUE = 255
FULL = 2**8 - 1


def pen(img):
    # every caller passes an RGB picture: this blends
    return ImageDraw.Draw(img, "RGBA")


def glow(img, t):
    lay = Image.new("RGBA", img.size, CLEAR)
    ImageDraw.Draw(lay).ellipse((10, 10, 90, 90), fill=(*INK, int(255 * t)))
    img.alpha_composite(lay)


def soften(im):
    return im.filter(ImageFilter.GaussianBlur(2))


def halo(img, t):
    # the clear colour lives in the palette module, and the layer comes back from the helper it is handed to
    lay = soften(Image.new("RGBA", img.size, L.CLEAR))
    ImageDraw.Draw(lay).ellipse((10, 10, 90, 90), outline=(*INK, int(255 * t)))
    img.alpha_composite(lay)
    # a layer maker whose start colour is a parameter, left at its clear default
    top = L.layer(img.size)
    ImageDraw.Draw(top).line((0, 0, 9, 9), fill=L.rgba(INK, 0.5))
    img.alpha_composite(top)


def wash(size):
    # starts see-through: a layer being built, where replacing the pixels is meant
    lay = Image.new("RGBA", size, TINT)
    ImageDraw.Draw(lay, "RGBA").line((0, 0, 9, 9), fill=(*INK, 80))
    return lay


def mask(size):
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).ellipse((0, 0, 9, 9), fill=255)
    return m


def dot(im, x, alpha=255):
    # opaque on the canvas and see-through only on a layer: no one call hands it both
    ImageDraw.Draw(im).ellipse((x, 0, x + 9, 9), fill=(*INK, alpha))


def rule(img, xy, alpha=1.0):
    # straight on at full alpha, through a layer below it: the draw under the test is not judged
    if alpha >= 1:
        ImageDraw.Draw(img).line(xy, fill=(*INK, int(255 * alpha)))
        return
    lay = Image.new("RGBA", img.size, CLEAR)
    ImageDraw.Draw(lay).line(xy, fill=(*INK, int(255 * alpha)))
    img.alpha_composite(lay)


def on_layer(fn):
    # hands the def a fresh layer and composites it: the def under it does not get its caller's picture
    def run(img, *args):
        lay = Image.new("RGBA", img.size, CLEAR)
        fn(lay, *args)
        img.alpha_composite(lay)

    return run


@on_layer
def ring(img, t):
    ImageDraw.Draw(img).ellipse((10, 10, 90, 90), outline=(*INK, int(255 * t)))


def any_pen(img):
    # blends where Pillow can: the mode is asked for only on an RGB picture
    return ImageDraw.Draw(img, "RGBA") if img.mode == "RGB" else ImageDraw.Draw(img)


def card(img):
    # the photo covers the top of the card only: the band below it lands on clear pixels
    lay = Image.new("RGBA", (400, 300), CLEAR)
    lay.paste(Image.new("RGB", (400, 200), INK))
    ImageDraw.Draw(lay).rectangle((0, 200, 400, 300), fill=(*INK, 120))
    img.alpha_composite(lay, (10, 10))


def boxed(img, box, edge=0):
    # no edge unless a call asks for one: at width 0 Pillow draws no outline
    ImageDraw.Draw(img).rectangle(box, fill=INK, outline=TINT, width=edge)


def glow_on(lay, t):
    ImageDraw.Draw(lay).ellipse((10, 10, 90, 90), fill=(*INK, int(255 * t)))


def grid_on(img, t):
    ImageDraw.Draw(img).line((0, 30, 90, 30), fill=INK)


FX = {"glow": glow_on, "grid": grid_on}


def with_window(im, box):
    # clears a part of the picture it is given: what it gives back is no longer read as opaque
    im.paste(CLEAR, box)
    return im


def plate(t):
    # two modes by an if/else: the lint cannot tell which, so it says nothing
    if t < 0.5:
        img = canvas(PAPER)
    else:
        img = Image.new("RGB", (640, 360), INK)
    ImageDraw.Draw(img, "RGBA").line((0, 0, 9, 9), fill=(*INK, 90))
    return img


def unknown(img):
    # nobody calls this with a picture the lint can name
    ImageDraw.Draw(img).line((0, 0, 5, 5), fill=(*INK, 90))


def draw(t):
    base = Image.new("RGB", (640, 360), INK)
    pen(base).line((0, 0, 100, 100), fill=(*INK, 128), width=4)
    img = canvas(PAPER)
    glow(img, t)
    halo(img, t)
    img.alpha_composite(wash(img.size))
    lay = Image.new("RGBA", img.size, CLEAR)
    dot(img, 0)
    dot(lay, 20, int(255 * t))
    img.alpha_composite(lay)
    rule(img, (0, 80, 30, 80), t)
    ring(img, t)
    any_pen(img).rectangle((0, 90, 30, 99), fill=INK)
    card(img)
    boxed(img, (40, 0, 70, 30))
    # each key reaches its own entry: the glow only ever gets the layer
    FX.get("glow")(lay, t)
    FX.get("grid")(img, t)
    cover = with_window(canvas(PAPER), (10, 10, 40, 40))
    ImageDraw.Draw(cover).rectangle((10, 10, 40, 40), fill=(*INK, 60))
    img.alpha_composite(cover)
    d = ImageDraw.Draw(img)
    # opaque: replacing the pixel is the same as blending
    d.rectangle((0, 0, 30, 30), fill=INK)
    d.rectangle((0, 40, 30, 70), fill=(*INK, OPAQUE))
    # alphas that fold to 255
    d.rectangle((0, 100, 30, 110), fill=(*INK, FULL))
    d.rectangle((0, 110, 30, 120), fill=(*INK, math.floor(255.0)))
    # an erase is meant to replace
    d.ellipse((5, 5, 25, 25), fill=CLEAR)
    # the helper's alpha left at its default
    d.line((0, 0, 30, 30), fill=hexrgb(PAPER), width=2)
    plate(t)
    img.putalpha(mask(img.size))
    return finish(img)
