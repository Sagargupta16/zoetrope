# appr_piece.py : the build the approval fixtures approve and then change (Q1301, Q1303, Q1304): 2 s at 320x180, two
# still scenes cut on the 120 BPM grid, no text and no cues by design, so run_all.py full delivers it cleanly. The
# cases change B_TOP (scene b's colour) after the approval.
import engine as E
from engine import finish, gradient, rrect

SCHEDULE = {"a": (0.0, 1.0), "b": (1.0, 2.0)}
DURATION = 2.0
BPM = 120
NO_TEXT = True
NO_CUES = True
A_TOP, B_TOP, BOTTOM, CARD = "#7090D0", "#D09070", "#101828", "#F7F3EA"


def draw(t):
    name = E.scene_at(t, SCHEDULE)[0]
    img = gradient(A_TOP if name == "a" else B_TOP, BOTTOM)
    rrect(img, (40, 60, 120, 120), 12, CARD)
    return finish(img)
