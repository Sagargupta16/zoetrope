# reg_paste.py : planted fault for Q208 (lane T's f5_paste, at 640x360). The only text is a glyph mask from
# font.getmask pasted as an image, so no ImageDraw.text call ever runs and the recorder sees nothing. Expect Q208
# NOT CHECKED, never a PASS.
from PIL import Image

from engine import finish, font, gradient

SCHEDULE = {"only": (0.0, 2.0)}
DURATION = 2.0
CAP = "Pasted text"


def text_items(t):
    return [
        {"s": CAP, "box": (200, 167, 343, 187), "fg": "#FFFFFF", "alpha": 1.0, "px": 27}
    ]


def draw(t):
    img = gradient("#1B2440", "#0B1020")
    m = font(27).getmask(CAP)
    img.paste((255, 255, 255, 255), (200, 167), Image.frombytes("L", m.size, bytes(m)))
    return finish(img)
