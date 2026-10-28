# reg_missing.py : planted fault for Q204 (lane T's f1_missing, at 640x360). A 19 px caption (57 px at 1080) is drawn
# from 0.5 to 1.5 s, but text_items(t) reports only the title. Expect Q204 FIX, item "Missing caption", worst_t about
# 0.97 s (the middle of its readable span, 0.5 to 1.467 s).
import engine as E
from engine import finish, gradient, text, text_box

SCHEDULE = {"only": (0.0, 2.0)}
DURATION = 2.0
TITLE, CAP = "Registered title", "Missing caption"


def text_items(t):
    box = text_box(TITLE, (E.W / 2, 100), 32, "mm")
    return [{"s": TITLE, "box": box, "fg": "#FFFFFF", "alpha": 1.0, "px": 32}]


def draw(t):
    img = gradient("#1B2440", "#0B1020")
    text(img, TITLE, (E.W / 2, 100), 32, "#FFFFFF", "mm")
    if 0.5 <= t < 1.5:
        text(img, CAP, (E.W / 2, 267), 19, "#FFFFFF", "mm")
    return finish(img)
