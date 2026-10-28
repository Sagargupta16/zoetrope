# scenes.py : one video. draw(t) is pure: same t -> same pixels. All timing lives in TIMELINE.
# The registry (text_items, CUES, KEY_TIMES) lets qa.py and proof.py check and show this video without guessing.
import transitions

import engine as E
from engine import *

# the palette: replace with the chosen style's. NIGHT and DAY are the backgrounds (gradient top, bottom).
INK, PAPER, ACCENT, WHITE = "#101828", "#F7F3EA", "#FF6B4A", "#FFFFFF"
# NIGHT's bottom keeps frame 0 and the end card about 5 levels over the Q501 and Q502 floor of 25 once encoded
NIGHT, DAY = ("#1B2440", "#121A33"), (PAPER, "#E8E1D0")
LINES = {"hook": "{hook line}", "point": "{one idea}", "cta": "{call to action}"}

# The ONLY place timing is defined: the scenes in order, lengths in seconds (in beats with bpm=BPM). A
# Transition("crossfade", 0.4) between two scenes makes a window where both are drawn and crossfaded (layout());
# Scene("hook", 2.5, cues=[(0.5, "hit")]) adds a scene-local cue. Lengthen a scene and every later time moves too.
TIMELINE = [Scene("hook", 2.5), Scene("point", 2.5), Scene("cta", 2.5)]
SCHEDULE, DURATION, CUTS, WINDOWS, CUES = compile_schedule(TIMELINE)  # frame-exact
BPM = 120  # qa.py checks the cuts against this grid

# Registry: every cue the picture and sound must share (t, label, kind), kind "both", "audio" or "picture".
# A cut inside a transition window has no hard picture change: give its cue kind "audio".
CUES = sorted(
    CUES + [(c, f"cut to {n}", "both") for c, n in zip(CUTS, list(SCHEDULE)[1:])]
)
CUE_LAG = 0  # frames the picture may trail its cue by design (a pixel-art hit lands 2 to 4 frames late)
KEY_TIMES = []  # extra moments the proof sheet must show (punchlines, reveals); captions and cuts are added for you


def title_state(name, lt):
    """Layout of a scene's title at local time lt: (alpha, xy, size, colour)."""
    a0, b0 = SCHEDULE[name]
    # the first scene starts fully drawn (frame 0 is the thumbnail) and the last holds to the end (the end card);
    # the others start on their cut, so a changeover leaves one empty frame: Q207 allows 2 at most, and a longer
    # gap would repeat a frame between two moves (Q1104)
    enter = 1.0 if a0 == 0 else ease_out_expo(prog(lt, 0.0, 0.5))
    leave = 0.0 if b0 >= DURATION else ease_in_cubic(prog(lt, (b0 - a0) - 0.25, 0.25))
    size = fit_size(
        LINES[name], min(W, H) * 0.09, W * 0.84
    )  # short side, so 9:16 does not overflow
    y = H / 2 + lerp(40, 0, enter) - lerp(0, 30, leave)
    return enter * (1 - leave), (W / 2, y), size, INK if name == "point" else WHITE


def layout(t):
    """Every scene on screen at t: [(name, local_t, share, title_state)], one scene, or the outgoing then the
    incoming one inside a transition window, share being its weight in the crossfade. draw() paints exactly this
    and text_items() reports exactly this, so the registry cannot drift from the picture."""
    shown, mix = scenes_at(t, SCHEDULE)
    shares = [1.0] if len(shown) == 1 else [1 - mix, mix]
    return [(n, lt, w, title_state(n, lt)) for (n, lt, _), w in zip(shown, shares)]


def text_items(t):
    """Registry for qa.py: every text drawn at time t, with its box in output pixels, colour, alpha and size."""
    items = []
    for name, _, share, (a, xy, size, col) in layout(t):
        # a crossfade shows each title at its own alpha times its scene's share; the box comes from the same
        # font, xy and anchor title() draws with
        if a * share > 0:
            s = LINES[name]
            box = text_box(s, xy, size, "mm")
            items.append(
                {
                    "s": s,
                    "box": box,
                    "fg": col,
                    "alpha": a * share,
                    "px": size,
                    "bold": True,
                }
            )
    return items


def bg(t, name):
    img = gradient(*DAY) if name == "point" else gradient(*NIGHT)
    # slow-drifting soft circles keep holds alive; seeded by what the layer is, so every frame
    # gets the same six circles whatever order or process draws it
    g = rng("bg", "circles")
    for i, (u, v) in enumerate(zip(g.random(6), g.random(6))):
        x = (u * W + t * 12 * (i + 1)) % W
        y = v * H
        rrect(img, (x - 60, y - 60, x + 60, y + 60), 60, hexrgb(ACCENT, 28))
    return img


def title(img, name, lt, state):
    """Entrance 0.5 s ease_out_expo (slide up + fade), exit last 0.25 s faster (ease_in); see title_state."""
    a, xy, size, col = state
    if name != "point":  # dark scenes: a soft shadow under the title
        shadow(img, (W * 0.1, xy[1] - size, W * 0.9, xy[1] + size), 24, alpha=0.25 * a)
    text(img, LINES[name], xy, size, col, "mm", a)
    bar = ease_out_cubic(prog(lt, 0.25, 0.45))  # accent rule draws in from the left
    if bar <= 0:  # a zero-width rounded rect still paints a dot
        return
    y = xy[1] + size * 0.9
    rrect(img, (W / 2 - 120, y, W / 2 - 120 + 240 * bar, y + 8), 4, ACCENT)


def draw(t):
    shown, frames = layout(t), []
    for name, lt, _, state in shown:
        img = bg(t, name)
        title(img, name, lt, state)
        frames.append(img)
    if len(frames) == 1:
        return finish(frames[0])
    # a transition window: another transitions.py kind needs its own shares in layout(), or the registry drifts
    return finish(transitions.crossfade(frames[0], frames[1], shown[1][2]))
