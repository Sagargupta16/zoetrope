# reg_shadow.py : known-good control for the recorder (lane T's f15_shadow, at 640x360; review R5 finding 2). A drop
# shadow drawn as a second text() call, 3 px down and right at alpha 0.5, under the white fill; the registry box is
# the fill's text_box, which is right. Expect Q204, Q205, Q206, Q208 and Q209 PASS (Q205 was a false FIX once).
import engine as E
from engine import finish, gradient, text, text_box

SCHEDULE = {"only": (0.0, 2.0)}
DURATION = 2.0
S = "SHADOWED"


def text_items(t):
    box = text_box(S, (E.W / 2, E.H / 2), 40, "mm")
    return [{"s": S, "box": box, "fg": "#FFFFFF", "alpha": 1.0, "px": 40}]


def draw(t):
    img = gradient("#1B2440", "#0B1020")
    text(img, S, (E.W / 2 + 3, E.H / 2 + 3), 40, "#000000", "mm", 0.5)
    text(img, S, (E.W / 2, E.H / 2), 40, "#FFFFFF", "mm")
    return finish(img)
