# reg_stale.py : planted fault for Q209 (lane T's f14_stale, at 640x360). draw(t) shows a caption until 1.0 s, but
# text_items(t) keeps reporting it at alpha 1 until 1.5 s (a stale registry). Expect Q209 NOTE, item "Stale
# caption", worst_t about 1.23 s (its span 1.0 to 1.467 s).
import engine as E
from engine import finish, gradient, text, text_box

SCHEDULE = {"only": (0.0, 2.0)}
DURATION = 2.0
TITLE, CAP = "Registered title", "Stale caption"
INK = "#FFFFFF"


def text_items(t):
    out = [
        {
            "s": TITLE,
            "box": text_box(TITLE, (E.W / 2, 100), 32, "mm"),
            "fg": INK,
            "alpha": 1.0,
            "px": 32,
        }
    ]
    if t < 1.5:  # the fault: the drawing stops at 1.0 s
        box = text_box(CAP, (E.W / 2, 267), 19, "mm")
        out.append({"s": CAP, "box": box, "fg": INK, "alpha": 1.0, "px": 19})
    return out


def draw(t):
    img = gradient("#1B2440", "#0B1020")
    text(img, TITLE, (E.W / 2, 100), 32, INK, "mm")
    if t < 1.0:
        text(img, CAP, (E.W / 2, 267), 19, INK, "mm")
    return finish(img)
