# scenes.py : one video. draw(t) is pure: same t -> same pixels. All timing lives in SCHEDULE.
# The registry (text_items, CUES, KEY_TIMES) lets qa.py and proof.py check and show this video without guessing.
import random
import engine as E
from engine import *

INK, PAPER, ACCENT = (
    "#101828",
    "#F7F3EA",
    "#FF6B4A",
)  # replace with the chosen style's palette
LINES = {"hook": "{hook line}", "point": "{one idea}", "cta": "{call to action}"}

SCHEDULE = {  # seconds; the ONLY place timing is defined
    "hook": (0.0, 2.5),
    "point": (2.5, 5.0),
    "cta": (5.0, 7.5),
}
DURATION = 7.5
BPM = 120  # qa.py checks scene starts against this grid

# Registry: every cue the picture and sound must share (t, label, kind), kind "both", "audio" or "picture".
CUES = [(a, f"cut to {name}", "both") for name, (a, b) in SCHEDULE.items() if a > 0]
CUE_LAG = 0  # frames the picture may trail its cue by design (a pixel-art hit lands 2 to 4 frames late)
KEY_TIMES = []  # extra moments the proof sheet must show (punchlines, reveals); captions and cuts are added for you


def title_state(name, lt):
    """Layout of a scene's title at local time lt: (alpha, y, size). draw() and text_items() both use it."""
    a0, b0 = SCHEDULE[name]
    enter = (
        1.0 if a0 == 0 else ease_out_expo(prog(lt, 0.1, 0.5))
    )  # the first scene starts fully drawn
    leave = ease_in_cubic(prog(lt, (b0 - a0) - 0.25, 0.25))
    size = fit_size(
        LINES[name], min(W, H) * 0.09, W * 0.84
    )  # short side, so 9:16 does not overflow
    y = H / 2 + lerp(40, 0, enter) - lerp(0, 30, leave)
    return enter * (1 - leave), y, size


def text_items(t):
    """Registry for qa.py: every text drawn at time t, with its box in output pixels, colour, alpha and size."""
    name, lt, k = scene_at(t, SCHEDULE)
    a, y, size = title_state(name, lt)
    if a <= 0:
        return []
    s = LINES[name]
    w = text_w(s, size)
    col = INK if name == "point" else "#FFFFFF"
    box = (W / 2 - w / 2, y - size * 0.55, W / 2 + w / 2, y + size * 0.55)
    return [{"s": s, "box": box, "fg": col, "alpha": a, "px": size, "bold": True}]


def bg(t, name):
    img = (
        gradient("#1B2440", "#0B1020")
        if name != "point"
        else gradient("#F7F3EA", "#E8E1D0")
    )
    rnd = random.Random(7)  # seeded: identical every frame
    for i in range(6):  # slow-drifting soft circles keep holds alive
        x = (rnd.random() * W + t * 12 * (i + 1)) % W
        y = rnd.random() * H
        rrect(img, (x - 60, y - 60, x + 60, y + 60), 60, hexrgb(ACCENT, 28))
    return img


def title(img, name, lt, k, light):
    """Entrance 0.5 s ease_out_expo (slide up + fade), exit last 0.25 s faster (ease_in). The first scene starts fully drawn (thumbnail)."""
    a, y, size = title_state(name, lt)
    col = INK if light else "#FFFFFF"
    if not light:
        shadow(img, (W * 0.1, y - size, W * 0.9, y + size), 24, alpha=0.25 * a)
    text(img, LINES[name], (W / 2, y), size, col, "mm", a)
    bar = ease_out_cubic(prog(lt, 0.25, 0.45))  # accent rule draws in from the left
    if bar <= 0:  # a zero-width rounded rect still paints a dot
        return
    rrect(
        img,
        (W / 2 - 120, y + size * 0.9, W / 2 - 120 + 240 * bar, y + size * 0.9 + 8),
        4,
        ACCENT,
    )


def draw(t):
    name, lt, k = scene_at(t, SCHEDULE)
    img = bg(t, name)
    title(img, name, lt, k, light=(name == "point"))
    return finish(img)
