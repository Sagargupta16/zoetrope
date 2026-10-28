# reg_box.py : planted fault for Q205 (lane T's f3_box, at 640x360). The registry box comes from engine.text_box, but
# 6 px below where draw(t) puts the text (a stale offset). Expect Q205 FIX, item "Registered title", metric 6.0 px
# (limit 2).
import engine as E
from engine import finish, gradient, text, text_box

SCHEDULE = {"only": (0.0, 2.0)}
DURATION = 2.0
TITLE = "Registered title"


def text_items(t):
    box = text_box(TITLE, (E.W / 2, 106), 32, "mm")  # the fault: draw(t) uses y = 100
    return [{"s": TITLE, "box": box, "fg": "#FFFFFF", "alpha": 1.0, "px": 32}]


def draw(t):
    img = gradient("#1B2440", "#0B1020")
    text(img, TITLE, (E.W / 2, 100), 32, "#FFFFFF", "mm")
    return finish(img)
