# pure_pid.py : planted fault for Q1201. draw(t) is pure but for the frame of the cut at 1.0 s, where it paints a box
# coloured by the process id: every process draws that frame differently, and nothing else differs. Expect Q1201
# FIX, item "b", worst_t 1.0 (frame 30, always sampled as a cut frame), metric the box's 161 x 101 = 16261 pixels.
import os

import engine as E
from engine import finish, gradient, rrect

SCHEDULE = {"a": (0.0, 1.0), "b": (1.0, 2.0)}
DURATION = 2.0
BOX = (40, 40, 200, 140)


def draw(t):
    img = gradient("#1B2440", "#0B1020")
    if E.frame_of(t, E.FPS) == E.frame_of(1.0, E.FPS):
        pid = os.getpid()  # the fault: process state in a frame
        rrect(img, BOX, 0, (pid % 256, (pid >> 8) % 256, (pid >> 16) % 256, 255))
    return finish(img)
