# sprites.py : hand-drawn original sprites as palette strings ('.' transparent). Outlines are added
# automatically by pix.sprite. Keys: K black W white g grey l lgrey d dgrey N navy B blue S sky P pale
# v/V/u/U violets D dark violet M magenta p pink R red O orange Y gold e peach G green L lime.
import numpy as np

import pix as X

KNIGHT = X.parse(
    [
        "....RRR......W..",
        "...RRlllll...W..",
        "...RlllllWl..W..",
        "...lllllllll.W..",
        "...llldKKKKl.W..",
        "...lllllllll.W..",
        "....gllllll..W..",
        "..RRlWWWWll..W..",
        ".RRRBBBBBBll.W..",
        ".RRBBBYBBBBl.W..",
        ".RRBBYYYBBBlYYY.",
        ".RRBBBYBBBB.ld..",
        ".RRBBBBBBBB..Y..",
        ".RRggYYYgg......",
        ".RRBBBBBBBB.....",
        "..RBBB..BBB.....",
        "...lll..lll.....",
        "...ll....ll.....",
        "..ggg....ggg....",
        "................",
    ]
)

MAGE = X.parse(
    [
        "..VV............",
        "...VVV......PS..",
        "...VVVV....SSSS.",
        "....VVVu....SS..",
        "...VVVVVu....R..",
        "..YYYYYYYY...R..",
        ".VVVVVVVVVV..R..",
        "....eeeeKe...R..",
        "....eeeeee...R..",
        "....WWWWWWW.lR..",
        "...vVWWWWWVVll..",
        "..vvVVWWWVVV.R..",
        "..vvVVVWVVVV.R..",
        "..vvYVVVVVVV.R..",
        "..vvVVVVVVVV.R..",
        "..vvVVVVVVVVVR..",
        ".vvvVVVVVVVVVR..",
        ".vvvVVVVVVVVVR..",
        "..YYYYYYYYYY.R..",
        "................",
    ]
)

RANGER = X.parse(
    [
        "................",
        "..W..GGGG.......",
        "..WWGGLLGG...O..",
        "...RGLeeeG..lO..",
        "...RGeeeKe..l.O.",
        "...RGeeeee..l.O.",
        "...RGGeeeG..l.O.",
        "...RGGGGGGG.l.O.",
        "..RRGLLLLGGeeeO.",
        "..RRGLLLLGG.l.O.",
        "..RRGLLLLGG.l.O.",
        "...RGGYYGGG.l.O.",
        "...GGLLLLGG.l.O.",
        "...GGLLLLGG.l.O.",
        "...GGL..LGG.lO..",
        "....dd..dd...O..",
        "....dd..dd......",
        "....dd..dd......",
        "...ddd..ddd.....",
        "................",
    ]
)

# Serpent head facing left: upper skull and a separate lower jaw so the mouth can open.
HEAD = X.parse(
    [
        "..........................O....O....O.......",
        ".........................OO...OO...OO.......",
        "...................GGGGGOOGGGOOOGGOOO.......",
        "..............GGGGGLLLLLLGGGGGGGGGGGOO......",
        "..........GGGGLLLLLLLLLLLLLGGGGGGGGGGGG.....",
        ".......GGGGLLLLLLLLLLLLLLLLLGGGGGGGGGGGG....",
        ".....GGGLLLLLLLLLLLLKKKKLLLLGGGGGGGGGGGGG...",
        "...GGGLLLLLLLLLLLLLKYYYYKLLLGGGGGGGGGGGGGG..",
        "..GGLLLLLLLLLLLLLLKYYKYYKLLGGGGGGGGGGGGGGGG.",
        ".GKGLLLLLLLLLLLLLLKYYKYYKGGGGGGGGGGGGGGGGGGG",
        "GGGGGGGGGGGGGGGGGGGKKKKGGGGGGGGGGGGGGGGGGGGG",
        "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
        "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
        ".WGGWGGWGGWGGWGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",
        ".W..W..W..W..W..............................",
    ]
)
JAW = X.parse(
    [
        "..W..W..W..W..W.............................",
        ".eeeeeeeeeeeeeeeeeeeeeeGGGGGGGGGGGGGGGGGGGGG",
        "..eeeeeeeeeeeeeeeeeeeeeeeGGGGGGGGGGGGGGGGGGG",
        "....eeeeeeeeeeeeeeeeeeeeeeeGGGGGGGGGGGGGGGG.",
        "......eeeeeeeeeeeeeeeeeeeeeeeGGGGGGGGGGGGG..",
        ".........eeeeeeeeeeeeeeeeeeeeeeGGGGGGGGGG...",
        ".............eeeeeeeeeeeeeeeeeeeeeGGGG......",
    ]
)
MOUTH = X.parse(
    [  # red mouth interior shown behind the jaw when it opens
        "RRRRRRRRRRRRRRRRRRRRRR......................",
        ".RRRRRRRRRRRRRRRRRRRRR......................",
        "..RRRRRRRRRRRRRRRRRRRR......................",
        "...RRRRRRRRRRRRRRRRRRR......................",
        ".....RRRRRRRRRRRRRRRRR......................",
    ]
)

ARROW = X.parse(
    [
        "W.....l...",
        ".WllllllYY",
        "W.....l...",
    ]
)

ICE = X.parse(
    [
        "...W...",
        "..WPW..",
        ".PSPSP.",
        "WPSWSPW",
        ".PSPSP.",
        "..WPW..",
        "...W...",
    ]
)

SPARK = X.parse(
    [
        "..Y..",
        "..W..",
        "YWWWY",
        "..W..",
        "..Y..",
    ]
)

DIAMOND = X.parse([
    "..Y..",
    ".YWY.",
    "YWWWY",
    ".YWY.",
    "..Y..",
])

RAISE = 3  # victory pose: the weapon (and the hand on it) lifts 3 px


def raised(spr: np.ndarray, m: np.ndarray, dy: int = RAISE) -> np.ndarray:
    """Pose frame: pixels under mask m move up dy rows; the sprite grows dy rows at the top."""
    h, w = spr.shape
    out = np.full((h + dy, w), 255, np.uint8)
    out[dy:][~m] = spr[~m]
    moved = np.where(m, spr, 255)
    sel = moved != 255
    out[:h][sel] = moved[sel]
    return out


_r, _c = np.mgrid[0:20, 0:16]
RAISED = {
    "KNIGHT": raised(KNIGHT, _c >= 12),  # sword, crossguard, hand
    "MAGE": raised(MAGE, (_c >= 13) | ((_r <= 3) & (_c >= 11))),  # staff and orb slide up through the hand
    "RANGER": raised(RANGER, _c >= 12),  # bow, string, hand
}

PARTY = [("KNIGHT", KNIGHT), ("MAGE", MAGE), ("RANGER", RANGER)]
