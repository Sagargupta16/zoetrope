# reg_cover.py : planted fault for Q206 (lane T's f4_cover, at 640x360). Two registered captions; a card drawn after
# the first covers its right 60 percent. Expect Q206 FIX, item "Covered caption", metric about 0.4 (limit 0.7);
# "Visible caption" passes.
import engine as E
from engine import finish, gradient, rrect, text, text_box

SCHEDULE = {"only": (0.0, 2.0)}
DURATION = 2.0
COVERED, VISIBLE = "Covered caption", "Visible caption"


def _boxes():
    a = text_box(COVERED, (E.W / 2, 167), 21, "mm")
    return a, text_box(VISIBLE, (E.W / 2, 267), 21, "mm")


def text_items(t):
    a, b = _boxes()
    return [
        {"s": COVERED, "box": a, "fg": "#FFFFFF", "alpha": 1.0, "px": 21},
        {"s": VISIBLE, "box": b, "fg": "#FFFFFF", "alpha": 1.0, "px": 21},
    ]


def draw(t):
    img = gradient("#1B2440", "#0B1020")
    text(img, COVERED, (E.W / 2, 167), 21, "#FFFFFF", "mm")
    text(img, VISIBLE, (E.W / 2, 267), 21, "#FFFFFF", "mm")
    a, _ = _boxes()
    x = a[0] + 0.4 * (
        a[2] - a[0]
    )  # the card slides in over the caption's right 60 percent
    rrect(img, (x, a[1] - 10, a[2] + 20, a[3] + 10), 5, "#E8E1D0")
    return finish(img)
