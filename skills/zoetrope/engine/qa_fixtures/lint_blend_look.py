# lint_blend_look.py : the palette module of lint_blend_ok.py, copied beside it in the selftest's build folder. Q1207
# reads the clear colour, the layer maker (its start colour is a parameter) and the colour helper from here.
from PIL import Image

CLEAR = (0, 0, 0, 0)


def layer(size, colour=CLEAR):
    return Image.new("RGBA", size, colour)


def rgba(c, a=1.0):
    return (c[0], c[1], c[2], int(255 * a))
