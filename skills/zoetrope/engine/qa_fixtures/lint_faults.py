# lint_faults.py : planted faults for the scenes lint (qa_lint.run), one per code, each on its own line: unseeded
# randomness in draw (Q1202 FIX), module state written in draw (Q1203), an engine helper redefined (Q1204), text drawn
# with ImageDraw (Q1205), a colour literal in a function (Q1206), a cue 0.4 frame off the 30 fps grid (Q904) and a
# BPM whose beat is not a whole number of frames (Q905). Never drawn: the lint reads it and imports it.
import random

from PIL import ImageDraw

from engine import finish, gradient

SCHEDULE = {"a": (0.0, 1.0), "b": (1.0, 2.0)}
DURATION = 2.0
BPM = 128  # Q905: one beat is 14.06 frames at 30 fps
CUES = [(1.0 + 0.4 / 30, "hit", "both")]  # Q904: 0.4 frame off the grid
COUNT = [0]
BG = ("#1B2440", "#0B1020")  # the palette block: colours named here are fine


def text(img, s):  # Q1204: redefines engine.text
    ImageDraw.Draw(img).text((10, 10), s)  # Q1205: text outside the engine helpers
    return img


def draw(t):
    COUNT[0] += 1  # Q1203: module state written inside draw
    img = gradient(*BG)
    jitter = random.random()  # Q1202: unseeded randomness
    ImageDraw.Draw(img).rectangle((0, 0, 10 + jitter, 10), fill=(200, 40, 40))  # Q1206
    return finish(text(img, "x"))
