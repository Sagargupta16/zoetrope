# scenes.py : "Storm over Saltmere", an original 8-bit battle. draw(t) is pure: same t -> same pixels.
# Everything is a function of the frame number. All timing comes from the song grid (song.py):
# SCHEDULE (scenes), MSGS (message box) and the hit tables below are in beats of the same 150 BPM grid
# that the chip synth plays, and every hit frame lands LAG frames after its kick, snare or crash.
import math
import random
from functools import lru_cache

import numpy as np

import engine as E
import pix as X
import song
import sprites as S
from pix import (
    BLACK,
    WHITE,
    GREY,
    LGREY,
    DGREY,
    NAVY,
    BLUE,
    SKY,
    PALE,
    V1,
    V2,
    V3,
    V4,
    DVIO,
    MAGENTA,
    PINK,
    RED,
    ORANGE,
    GOLD,
    PEACH,
    GREEN,
    LIME,
)

FPS = 30
FPB = 12  # frames per beat (150 BPM at 30 fps); a 16th note is 3 frames
LAG = 2  # hit frames land 2 frames after their drum note (style card: 2 to 4)


def bf(beat):
    return int(round(beat * FPB))


def sec(bars):
    return round(bars * song.BAR, 6)


SCHEDULE = {
    k: (sec(a), sec(b)) for k, (a, b) in song.SECTION_BARS.items()
}  # seconds, from the bar grid
SCHEDULE["endcard"] = (sec(36), round(song.DURATION, 6))
DURATION = round(song.DURATION, 6)

# party hits on the boss: id, beat, effect, attacker, damage (None = what is left), pop x (centre), pop y
P_HITS = [
    ("k1", 33, "slash", "KNIGHT", 128, 200, 56),
    ("m1", 44, "frost", "MAGE", 240, 204, 58),
    ("r1", 49, "arrow", "RANGER", 32, 196, 56),
    ("r2", 50, "arrow", "RANGER", 32, 220, 72),
    ("r3", 51, "arrow", "RANGER", 32, 244, 88),
    ("m2", 60, "bolt", "MAGE", 360, 204, 58),
    ("k2", 69, "slash", "KNIGHT", 200, 200, 56),
    ("k3", 89, "rising", "KNIGHT", 640, 206, 58),
    ("m3", 96, "frost", "MAGE", 920, 204, 58),
    ("c1", 112, "slash", "KNIGHT", 1240, 186, 56),
    ("c2", 113, "frost", "MAGE", 1480, 216, 72),
    ("c3", 114, "arrow", "RANGER", 1320, 246, 88),
    ("tb", 124, "tidebreaker", "KNIGHT", None, 206, 60),
]
BOSS_MAX = 9999
_dealt = sum(h[4] for h in P_HITS if h[4] is not None)
P_HITS[-1] = (
    P_HITS[-1][:4] + (BOSS_MAX - _dealt,) + P_HITS[-1][5:]
)  # the final blow takes exactly what is left
DMG = {h[0]: h[4] for h in P_HITS}
assert sum(DMG.values()) == BOSS_MAX
# boss attacks on the party: beat, effect, damage per member, shake amplitude in px
B_HITS = [
    (38, "wave", {"KNIGHT": 42, "MAGE": 38, "RANGER": 40}, 2),
    (54, "tail", {"KNIGHT": 64}, 2),
    (66, "bite", {"KNIGHT": 88}, 3),
    (72, "roar", {}, 2),
    (80, "maelstrom", {"KNIGHT": 96, "MAGE": 72, "RANGER": 80}, 3),
]
PARTY_MAX = {"KNIGHT": 340, "MAGE": 210, "RANGER": 260}
PARTY_POS = {"RANGER": (18, 84), "MAGE": (42, 84), "KNIGHT": (66, 84)}
MENU = ["FIGHT", "MAGIC", "SKILL", "ITEM"]

MSGS = [  # start beat, end beat, text, command under the cursor
    (25, 32, "THE TIDE SERPENT RISES!", None),
    (32, 36, f"KNIGHT ATTACKS! {DMG['k1']}", "FIGHT"),
    (36, 42, "SERPENT USES TIDAL WAVE!", None),
    (42, 48, f"MAGE CASTS FROST! {DMG['m1']}", "MAGIC"),
    (48, 53, f"RANGER: TRIPLE SHOT! {DMG['r1'] + DMG['r2'] + DMG['r3']}", "SKILL"),
    (53, 58, "SERPENT LASHES ITS TAIL!", None),
    (58, 64, f"MAGE CASTS THUNDER! {DMG['m2']}", "MAGIC"),
    (64, 68, "SERPENT BITES!", None),
    (68, 72, f"KNIGHT COUNTERS! {DMG['k2']}", "FIGHT"),
    (72, 78, "THE SERPENT IS ENRAGED!", None),
    (78, 82, "MAELSTROM!", None),
    (82, 88, "PARTY HOLDS THE LINE!", None),
    (88, 94, f"KNIGHT: RISING SLASH! {DMG['k3']}", "SKILL"),
    (94, 100, f"MAGE CASTS BLIZZARD! {DMG['m3']}", "MAGIC"),
    (100, 104, "THE SEA RISES!", None),
    (104, 110, "THE STORM BREAKS", None),
    (110, 116, "STRIKE AS ONE!", "FIGHT"),
    (116, 124, "DAWN GATHERS ON THE BLADE", "SKILL"),
    (124, 128, "TIDEBREAKER!", "SKILL"),
    (128, 134, "VICTORY!", None),
    (134, 144, "THE SEA IS CALM.", None),
]
TYPE_CPF = 99  # messages land whole on their beat (no typewriter: a half-typed line read as a bug on stills)
POP_F, POP_BOUNCE = 42, 8  # damage numbers: 1.4 s on screen, the first 8 frames bounce
END_TITLE, END_SUB = "STORM OVER SALTMERE", "AN ORIGINAL 8-BIT BATTLE THEME"

F_WIPE0, F_WIPE1 = (
    bf(24),
    bf(25),
)  # dither wipe from the tracker into the battle (bar 6)
F_RAGE, F_HERO, F_VICT, F_END = bf(72), bf(104), bf(128), bf(144)
HF = {h[0]: bf(h[1]) + LAG for h in P_HITS}
F_TB = HF["tb"]
HORIZON, FIELD_H, WL = 70, 123, 116

for (
    _h
) in P_HITS:  # every visual hit sits on a kick, snare or crash of the noise channel
    assert song.drum_at(song.beat_row(_h[1])) in ("K", "S", "X"), _h
for _b in B_HITS:
    assert song.drum_at(song.beat_row(_b[0])) in ("K", "S", "X"), _b


def hp_boss(f):
    return BOSS_MAX - sum(h[4] for h in P_HITS if HF[h[0]] <= f)


def hp_party(name, f):
    return PARTY_MAX[name] - sum(
        d.get(name, 0) for b, _, d, _ in B_HITS if bf(b) + LAG <= f
    )


def message(f):
    for a, b, s, cmd in MSGS:
        if bf(a) <= f < bf(b):
            return s, min(len(s), (f - bf(a) + 1) * TYPE_CPF), cmd
    return None


# ------------------------------------------------------------------ backgrounds
rnd = random.Random(29)
CLOUDS = [
    (
        rnd.randrange(0, 320),
        rnd.randrange(2, 34),
        rnd.randrange(18, 34),
        rnd.randrange(5, 9),
        rnd.choice([1, 2, 3]),
    )
    for _ in range(9)
]
RAIN = [(rnd.randrange(0, 320), rnd.randrange(0, FIELD_H)) for _ in range(70)]
DASH = [
    (
        y,
        [
            (rnd.randrange(0, 320), rnd.randrange(3, 9))
            for _ in range(7 + (y - HORIZON) // 6)
        ],
    )
    for y in range(HORIZON + 3, 180, 5)
]
SKY_STOPS = {
    "storm": [(0, BLACK), (0.45, NAVY), (1, BLUE)],
    "rage": [(0, BLACK), (0.35, DVIO), (0.75, V1), (1, MAGENTA)],
    "dawn": [(0, NAVY), (0.3, BLUE), (0.6, SKY), (0.85, PALE), (1, PEACH)],
}
SEA_STOPS = {
    "storm": [(0, NAVY), (1, BLUE)],
    "rage": [(0, DVIO), (1, V1)],
    "dawn": [(0, PALE), (0.25, SKY), (1, BLUE)],
}


@lru_cache(None)
def cloud_mask(i):
    _, _, rx, ry, _ = CLOUDS[i]
    w, h = 2 * rx + 1, 2 * ry + 5
    m = np.zeros((h, w), bool)
    for ox, oy, sx, sy in (
        (0, 2, 1.0, 1.0),
        (-rx // 2, 4, 0.6, 0.7),
        (rx // 2, 3, 0.55, 0.8),
    ):
        e = X.ellipse_mask(max(2, int(rx * sx)), max(2, int(ry * sy)))
        y0, x0 = oy + ry - e.shape[0] // 2, ox + rx - e.shape[1] // 2
        ys, xs = max(0, y0), max(0, x0)
        ye, xe = min(h, y0 + e.shape[0]), min(w, x0 + e.shape[1])
        m[ys:ye, xs:xe] |= e[ys - y0 : ye - y0, xs - x0 : xe - x0]
    return m


def clouds(c, f, body, top, bottom=None, part=0):
    for i, (cx, cy, rx, ry, sp) in enumerate(CLOUDS):
        m = cloud_mask(i)
        x = (cx + (f * sp) // 8) % (320 + 2 * rx + 40) - rx - 20
        if part:  # clouds part to both sides at the final blow
            x += int(part * (-200 if cx < 160 else 200))
        hi = m & ~np.pad(m, ((2, 0), (0, 0)))[:-2]
        X.put_mask(c, m, x, cy, body)
        X.put_mask(c, hi, x, cy, top)
        if bottom is not None:
            lo = m & ~np.pad(m, ((0, 2), (0, 0)))[2:]
            X.put_mask(c, lo, x, cy, bottom)


def rain(c, f, col, n=70):
    for x0, y0 in RAIN[:n]:
        x, y = (x0 - 2 * f) % 320, (y0 + 7 * f) % FIELD_H
        X.line(c, x, y, x - 2, y + 4, col)


def sea(c, f, th, bottom=FIELD_H, calm=False):
    X.vgrad(c, HORIZON, bottom, SEA_STOPS["storm" if th == "hero" else th])
    cols = {
        "storm": (SKY, PALE),
        "rage": (V2, PINK),
        "dawn": (WHITE, PALE),
        "hero": (SKY, PEACH),
    }[th]
    for y, ds in DASH:
        if y >= bottom:
            break
        sp = 1 + (y - HORIZON) // 14
        for k, (x0, L) in enumerate(ds):
            x = (x0 + (f * sp) // (6 if calm else 2)) % 340 - 10
            X.rect(c, x, y, x + L, y + 1, cols[(k + y) % 2])
    if th in ("dawn", "hero"):  # sun path on the water
        for i, y in enumerate(range(HORIZON + 2, min(bottom, HORIZON + 40), 3)):
            w = 2 + i // 2
            x = 150 - w + ((f // 6 + i) % 3) - 1
            X.rect(c, x, y, x + 2 * w, y + 1, GOLD if i % 2 else PEACH)


def sky(c, f, th, f_local=0, part=0):
    if th == "hero":
        X.vgrad(c, 0, HORIZON, SKY_STOPS["storm"])
        h = 4 + min(26, (f - F_HERO) // 9)  # dawn band grows behind the storm
        X.vgrad(c, HORIZON - h, HORIZON, [(0, BLUE), (0.55, PALE), (1, PEACH)])
        clouds(c, f, DGREY, GREY, PEACH)
        return
    X.vgrad(c, 0, HORIZON, SKY_STOPS[th])
    if th == "storm":
        clouds(c, f, DGREY, GREY)
    elif th == "rage":
        clouds(c, f, DVIO, V1, MAGENTA)
    else:
        sun_y = HORIZON - 2 - max(0, (f - F_VICT) // 40)
        X.put_mask(c, X.disc(15) & X.dith(0.5)[:31, :31], 150 - 15, sun_y - 15, PEACH)
        X.put_mask(c, X.disc(11), 150 - 11, sun_y - 11, GOLD)
        X.put_mask(c, X.disc(7), 150 - 7, sun_y - 7, PEACH)
        if part < 1:
            clouds(c, f, PALE, WHITE, None, part=part)


BOLTS = {  # background lightning: beat -> x; slow, local, no full-frame flash
    40: 60,
    56: 280,
    74: 120,
    86: 40,
    98: 300,
}


def bg_bolts(c, f):
    for b, bx in BOLTS.items():
        k = f - bf(b)
        if 0 <= k < 5 and k != 2:
            r = random.Random(b)
            x, y = bx, 0
            while y < HORIZON - 4:
                nx, ny = x + r.randrange(-6, 7), y + r.randrange(6, 11)
                X.line(c, x, y, nx, ny, WHITE)
                X.line(c, x + 1, y, nx + 1, ny, PALE if k < 2 else LGREY)
                x, y = nx, ny


ROCK = [
    (0, 104),
    (10, 101),
    (24, 102),
    (40, 101),
    (56, 102),
    (74, 101),
    (90, 103),
    (100, 108),
    (108, 114),
    (114, 120),
    (118, 180),
    (0, 180),
]


@lru_cache(None)
def rock_mask():
    return X.poly_mask(ROCK)


def rocks(c, f, bottom=FIELD_H):
    m = rock_mask().copy()
    m[bottom:] = False
    c[m] = DGREY
    top = m & ~np.roll(m, 3, 0)
    c[top] = GREY
    c[m & ~np.roll(m, 1, 0)] = LGREY
    speck = m & (X.BY == 5) & (X.YY > 106)
    c[speck] = GREY
    for x in range(100, 124):  # foam where the sea meets the rock
        y = int(108 + (x - 100) * 0.55)
        if (x + f // 3) % 4 < 2 and y < bottom:
            c[y, x] = WHITE


# ------------------------------------------------------------------ the serpent
SERP_LUT = {
    "storm": None,
    "hero": None,
    "dawn": None,
    "rage": X.lut_from({GREEN: V2, LIME: V3, PEACH: V4, ORANGE: MAGENTA, GOLD: PINK}),
}


def bezier(p, n):
    s = np.linspace(0, 1, n)[:, None]
    p0, p1, p2, p3 = (np.array(q, float) for q in p)
    return ((1 - s) ** 3) * p0 + 3 * ((1 - s) ** 2) * s * p1 + 3 * (
        1 - s
    ) * s * s * p2 + s**3 * p3, s[:, 0]


def tube(layer, pts, r0, r1, spikes=True, belly=True):
    """Thick serpent body along pts into layer: green, lime back highlight, peach belly, orange spikes."""
    n = len(pts)
    tang = np.gradient(pts, axis=0)
    tang /= np.maximum(1e-6, np.linalg.norm(tang, axis=1))[:, None]
    nb = np.stack([-tang[:, 1], tang[:, 0]], 1)
    flip = (-nb[:, 0] + nb[:, 1]) < 0
    nb[flip] *= -1  # belly normal points to the lower left (towards the party)
    rs = np.linspace(r0, r1, n)
    for i in range(n):
        r = int(round(rs[i]))
        x, y = pts[i]
        X.put_mask(layer, X.disc(r), x - r, y - r, GREEN)
    for i in range(n):
        r = rs[i]
        x, y = pts[i]
        hr = max(1, int(r * 0.45))
        hx, hy = x - nb[i, 0] * r * 0.4, y - nb[i, 1] * r * 0.4
        X.put_mask(layer, X.disc(hr), hx - hr, hy - hr, LIME, where=(layer == GREEN))
        if belly:
            br = max(1, int(r * 0.5))
            bx, by = x + nb[i, 0] * r * 0.5, y + nb[i, 1] * r * 0.5
            X.put_mask(layer, X.disc(br), bx - br, by - br, PEACH, where=(layer != 255))
    if belly:
        for i in range(2, n, 3):
            r = rs[i]
            a = pts[i] + nb[i] * r * 0.15
            b = pts[i] + nb[i] * r * 0.95
            X.line(layer, a[0], a[1], b[0], b[1], GOLD, where=(layer == PEACH))
    if spikes:
        for i in range(3, n - 2, 5):
            r = rs[i]
            base = pts[i] - nb[i] * (r - 1)
            tip = pts[i] - nb[i] * (r + 4) + tang[i] * 2
            q = [base + tang[i] * 3, base - tang[i] * 3, tip]
            m = X.poly_mask(q)
            layer[m & (layer == 255)] = ORANGE


def serpent(c, f, th, rise=0, hdx=0, hdy=0, jaw=0, solid=None, tail=None):
    layer = np.full((180, 320), 255, np.uint8)
    bob = 1 if (f % FPB) < 6 else 0  # head bobs on the beat
    for cx, cy, ro in ((292, WL + 3, 11), (316, WL + 4, 9)):  # coils behind the neck
        cy += rise
        ring = X.ring(ro, ro - 6)
        X.put_mask(layer, ring, cx - ro, cy - ro, GREEN)
        X.put_mask(
            layer, ring & ~np.pad(ring, ((3, 0), (0, 0)))[:-3], cx - ro, cy - ro, LIME
        )
    J = (226 + hdx, 62 + hdy + rise + bob)
    pts, _ = bezier(
        [(262, 130 + rise), (298, 96 + rise), (252 + hdx * 0.4, 50 + rise + hdy), J], 46
    )
    tube(layer, pts, 13, 8)
    hx, hy = int(J[0] - 41), int(J[1] - 10)
    if jaw > 0:  # red mouth behind the lowered jaw
        X.put_mask(layer, S.MOUTH != 255, hx + 1, hy + 12, RED)
    _blit(layer, S.JAW, hx + 1, hy + 13 + jaw)
    _blit(layer, S.HEAD, hx, hy)
    if tail is not None:
        tube(layer, tail, 6, 2, spikes=False, belly=False)
    if SERP_LUT[th] is not None:
        layer = np.where(layer != 255, SERP_LUT[th][layer], 255).astype(np.uint8)
    if solid == "hurt":
        layer = np.where(layer != 255, HURT_LUT[layer], 255).astype(np.uint8)
    elif solid is not None:
        layer[layer != 255] = solid
    m = layer != 255
    where = X.YY < WL
    ol = X.outline_of(m)[1:-1, 1:-1]
    c[ol & where] = BLACK
    c[m & where] = layer[m & where]
    for x in range(236, 284):  # foam ring where the neck meets the water
        if (x * 3 + f // 2) % 7 < 4:
            c[WL, x] = WHITE
        if (x + f // 3) % 5 == 0:
            c[WL - 1, x] = PALE


HURT_LUT = X.lut_from({GREEN: PALE, LIME: WHITE, PEACH: WHITE, ORANGE: PEACH, GOLD: WHITE, RED: PINK,
                       V2: V4, V3: WHITE, V4: WHITE, MAGENTA: PINK, PINK: WHITE})


def _blit(layer, spr, x, y):
    m = spr != 255
    X.put_mask(layer, m, x, y, spr)


# ------------------------------------------------------------------ party and effects
KNIGHT_GLOW = S.KNIGHT.copy()
KNIGHT_GLOW[0:10, 13] = GOLD


def ease_i(a, b, k):
    k = max(0.0, min(1.0, k))
    return int(round(a + (b - a) * (1 - (1 - k) ** 2)))


def member_state(name, f):
    """(x, y, sprite) of a party member at frame f, before the screen shake; None while it blinks."""
    vict = f >= F_VICT
    spr = dict(S.PARTY)[name]
    x, y = PARTY_POS[name]
    img = spr
    for hid, beat, fx, who, *_ in P_HITS:
        if who != name:
            continue
        hf = HF[hid]
        k = f - hf
        if fx in ("slash",) and -10 <= k <= 10:
            x += 8 if -6 <= k <= 4 else 4
        if fx == "rising" and -10 <= k <= 10:
            x += 10 if -6 <= k <= 4 else 5
            y -= 2 if 0 <= k <= 3 else 0
        if fx in ("frost", "bolt") and -10 <= k <= 4:
            y -= 1
        if fx == "arrow" and 0 <= k <= 2:
            x -= 1
        if fx == "tidebreaker" and -24 <= k <= 36:
            keys = [
                (-24, (66, 84)),
                (-14, (110, 40)),
                (-6, (150, 24)),
                (0, (176, 46)),
                (8, (176, 46)),
                (24, (100, 70)),
                (36, (66, 84)),
            ]
            for (k0, p0), (k1, p1) in zip(keys, keys[1:]):
                if k0 <= k <= k1:
                    q = (k - k0) / (k1 - k0)
                    x, y = (
                        int(round(p0[0] + (p1[0] - p0[0]) * q)),
                        int(round(p0[1] + (p1[1] - p0[1]) * q)),
                    )
    if name == "KNIGHT" and bf(116) <= f < F_TB + 8:
        img = KNIGHT_GLOW if (f // 3) % 2 == 0 else S.KNIGHT
    hurt = [
        f - (bf(b) + LAG)
        for b, _, d, _ in B_HITS
        if name in d and 0 <= f - (bf(b) + LAG) < 8
    ]
    if hurt:
        x -= 2 if hurt[0] < 4 else 1  # knocked back
        if hurt[0] in (1, 3, 5):
            return None  # blink
    if vict:
        off = {"KNIGHT": 0, "MAGE": 4, "RANGER": 8}[name]
        ph = (f - F_VICT + off) % FPB
        y -= (0, 2, 4, 5, 5, 4, 2, 0, 0, 0, 0, 0)[ph]
    if vict:  # weapon raised during the hop; the pose sprite is taller by S.RAISE rows
        img, y = S.RAISED[name], y - S.RAISE
    return x, y, img


def party(c, f, th):
    hold = bf(82) <= f < bf(88)
    for name, _ in S.PARTY:
        st = member_state(name, f)
        if st is None:
            continue
        x, y, img = st
        X.sprite(c, img, x, y, outline=GOLD if hold and (f // 3) % 2 else BLACK)
        if hold:
            a = f * 0.35 + {"KNIGHT": 0, "MAGE": 2, "RANGER": 4}[name]
            for j in range(2):
                sx = int(x + 8 + 11 * math.cos(a + j * math.pi)) - 2
                sy = int(y + 10 + 6 * math.sin(a + j * math.pi)) - 2
                X.sprite(c, S.SPARK, sx, sy, outline=None)


def fx_slash(c, cx, cy, k, big=False):
    if not 0 <= k <= 6:
        return
    L = (8, 14, 18, 18, 18, 16, 12)[k] * (2 if big else 1)
    for o in (-3, 0, 3):
        col = WHITE if o == 0 else SKY
        if k >= 5 and o:
            continue
        X.line(c, cx - L + o, cy - L, cx + L + o, cy + L, col)
        if big:
            X.line(c, cx + L + o, cy - L, cx - L + o, cy + L, GOLD if o else WHITE)


def fx_frost(c, cx, cy, k):
    if -9 <= k < 0:
        r = int(-k * 3.5)
        for j in range(4):
            a = j * math.pi / 2 + 0.6
            X.sprite(
                c,
                S.ICE,
                cx + int(r * math.cos(a)) - 3,
                cy + int(r * math.sin(a)) - 3,
                outline=NAVY,
            )
    elif 0 <= k <= 9:
        r = 4 + 3 * k
        if k < 4:
            X.put_mask(c, X.disc(10) & X.dith(0.5)[:21, :21], cx - 10, cy - 10, PALE)
        for j in range(6):
            a = j * math.pi / 3
            X.sprite(
                c,
                S.ICE,
                cx + int(r * math.cos(a)) - 3,
                cy + int(r * math.sin(a)) - 3,
                outline=NAVY,
            )


def fx_arrow(c, x0, y0, cx, cy, k):
    if -6 <= k < 0:
        q = (k + 6) / 6
        X.sprite(c, S.ARROW, int(x0 + (cx - x0) * q) - 9, int(y0 + (cy - y0) * q) - 1)
    elif 0 <= k <= 3:
        X.sprite(c, S.SPARK, cx - 2, cy - 2, outline=None)


def fx_bolt(c, cx, cy, k, seed):
    if not -2 <= k <= 5 or k == 2:
        return
    r = random.Random(seed)
    x, y = cx + r.randrange(-10, 10), 24
    while y < cy:
        nx, ny = x + r.randrange(-5, 6), min(cy, y + r.randrange(5, 9))
        X.line(c, x, y, nx, ny, WHITE)
        X.line(c, x - 1, y, nx - 1, ny, GOLD)
        x, y = nx, ny
    if 0 <= k <= 3:
        X.put_mask(c, X.disc(9) & X.dith(0.4)[:19, :19], cx - 9, cy - 9, PALE)


def fx_rising(c, cx, cy, k):
    """An upward crescent cut that sweeps from the water to above the head over 6 frames."""
    if 0 <= k <= 6:
        top = max(30, cy + 40 - 16 * k)
        X.rect(c, cx - 1, top, cx + 2, cy + 44, WHITE)
        X.rect(c, cx - 4, top + 5, cx - 1, cy + 40, GOLD)
        X.rect(c, cx + 2, top + 5, cx + 5, cy + 40, GOLD)
        if k >= 2:
            arc = X.ring(14, 12)
            arc[15:] = False
            X.put_mask(c, arc, cx - 14, top - 2, WHITE)


def fx_wave(c, f, hf):
    """Tidal wave: dithered body (sky to blue), white crest, a curling lip and spray; passes behind the party."""
    k = f - hf
    if not -14 <= k <= 12:
        return
    front = ease_i(196, 4, (k + 14) / 14) if k <= 0 else 4
    hgt = 46 if k <= 0 else max(0, 46 - 4 * k)
    if hgt <= 0:
        return
    xs = np.arange(320)
    d = xs - front
    hh = np.where(d < 30, hgt * (0.45 + 0.55 * d / 30), hgt - (d - 30) / 5)
    hh = np.where((xs >= front) & (xs < 250), np.maximum(0, hh), 0).astype(int)
    top = 116 - hh
    yy = X.YY
    body = (yy >= top[None, :]) & (yy < 121) & (hh[None, :] > 0)
    rel = (yy - top[None, :]) / np.maximum(1, hh[None, :])
    col = np.where(X.BY < rel * 20, BLUE, SKY)
    c[body] = col[body]
    c[body & (yy == top[None, :])] = WHITE
    c[body & (yy == top[None, :] + 1) & ((X.XX + f) % 3 > 0)] = PALE
    tf = 116 - int(hh[min(319, front + 1)])
    for dx, dy in ((-1, 0), (-2, 1), (-3, 2), (-3, 3), (-2, 4)):  # the lip curls forward
        x, y = front + dx, tf + dy
        if 0 <= x < 320 and 0 <= y < 180:
            c[y, x] = WHITE
    r = random.Random(hf)
    for j in range(9):
        x = front + r.randrange(0, 30)
        y = tf - 2 - (r.randrange(0, 5) + k) % 7
        if 0 <= x < 320 and 0 <= y < 180:
            c[y, x] = WHITE if j % 2 else PALE


def tail_pts(f, hf):
    k = f - hf
    if not -10 <= k <= 10:
        return None
    up = min(1.0, (k + 10) / 6) if k < 4 else max(0.0, 1 - (k - 4) / 6)
    swing = -16 if k >= 0 else 0
    tip = (110 + swing, int(124 - 34 * up))
    pts, _ = bezier(
        [(150, 128), (150, 100 - 10 * up), (124 + swing, 92 + 30 * (1 - up)), tip], 24
    )
    return pts


def fx_roar(c, f, hf, th):
    k = f - hf
    if 0 <= k <= 20:
        for j in range(3):
            r = 6 + 4 * ((k + j * 4) % 12)
            ring = X.ring(r, r - 1)
            ring[:, r:] = False  # only towards the party
            X.put_mask(
                c,
                ring & (X.dith(0.6)[: 2 * r + 1, : 2 * r + 1]),
                186 - r,
                70 - r,
                PINK if th == "rage" else PALE,
            )


def fx_maelstrom(c, f):
    a0, a1 = bf(78), bf(82)
    if not a0 <= f < a1:
        return
    t = f - a0
    for arm in range(3):
        for i in range(40):
            r = 2 + i * 0.7
            a = arm * 2.094 + r * 0.28 - t * 0.22
            x, y = int(150 + r * math.cos(a)), int(100 + r * 0.33 * math.sin(a))
            if HORIZON < y < FIELD_H:
                c[y, x] = V4 if i % 3 else WHITE
    hf = bf(80) + LAG
    for name in ("KNIGHT", "MAGE", "RANGER"):
        x, y = PARTY_POS[name]
        fx_bolt(c, x + 8, y + 4, f - hf, seed=hash(name) % 997 + 7)


def pop(c, s, cx, y, k, boxes, col=WHITE, scale=1):
    if not 0 <= k < POP_F:
        return
    y += (0, -2, -4, -5, -5, -4, -2, 0)[k] if k < 8 else 0
    X.text_c(c, s, cx, y, col, scale, outline=BLACK, boxes=boxes, tag="pop " + s)


def flash_sky(c, f):
    """One big sky flash at the roar and at the maelstrom strike (two in the whole film)."""
    for b in (72, 80):
        if 0 <= f - (bf(b) + LAG) < 2:
            m = X.YY < HORIZON
            c[m & X.dith(0.5)] = PINK
            return


# ------------------------------------------------------------------ scenes
def theme(f):
    if f < F_RAGE:
        return "storm"
    if f < F_HERO:
        return "rage"
    if f < F_TB:
        return "hero"
    return "dawn"


def field(f, bottom=FIELD_H, ui_hidden=False):
    c = X.new(BLACK)
    th = theme(f)
    if th == "dawn":
        k = (f - F_TB) / 18
        if k < 1:
            a = X.new(BLACK)
            sky(a, f, "hero")
            sea(a, f, "hero", bottom)
            sky(c, f, "dawn", part=k)
            sea(c, f, "dawn", bottom, calm=True)
            m = X.dith(k)
            c = np.where(m, c, a).astype(np.uint8)
        else:
            sky(c, f, "dawn", part=1)
            sea(c, f, "dawn", bottom, calm=True)
    else:
        sky(c, f, th)
        bg_bolts(c, f)
        sea(c, f, th, bottom)
    if th in ("storm", "rage"):
        flash_sky(c, f)
    # serpent state
    rise = 0
    if f < bf(31):
        rise = ease_i(96, 0, (f - F_WIPE0) / (bf(31) - F_WIPE0))
    hdx = hdy = jaw = 0
    solid = None
    tail = None
    for b, fx, d, _ in B_HITS:
        hf = bf(b) + LAG
        k = f - hf
        if fx == "bite" and -8 <= k <= 14:
            hdx = (
                ease_i(0, -92, (k + 8) / 8)
                if k <= 0
                else (-92 if k <= 3 else ease_i(-92, 0, (k - 3) / 11))
            )
            jaw = 5 if -4 <= k <= 1 else 0
        if fx == "roar" and -4 <= k <= 24:
            jaw, hdy = 6, -2
        if fx == "maelstrom" and -12 <= k <= 6:
            jaw = 4
        if fx == "wave" and -16 <= k <= -6:
            jaw = 4
        if fx == "tail":
            tail = tail_pts(f, hf)
    if th == "rage" and jaw == 0 and (f // 6) % 8 == 0:
        jaw = 2  # enraged: snapping jaw
    for hid, *_ in P_HITS:
        k = f - HF[hid]
        if hid != "tb" and k in (0, 1):
            solid = "hurt"
    gone = False
    if f >= F_TB:
        k = f - F_TB
        if k <= 3:
            solid = WHITE
        rise = max(rise, 0) + max(0, (k - 10) * 3)
        gone = rise > 120
    if not gone:
        serpent(c, f, th, rise, hdx, hdy, jaw, solid, tail)
    rocks(c, f, bottom)
    if bf(96) <= f < bf(108):  # the sea climbs the rocks during the chromatic run, then falls back
        lift = min(11, (f - bf(96)) // 6) if f < bf(104) else max(0, 11 - (f - bf(104)) // 3)
        if lift:
            y0 = 118 - lift
            X.vgrad(c, y0, FIELD_H, SEA_STOPS["storm" if th == "hero" else th])
            for x in range(320):
                if (x + f) % 5 < 3:
                    c[y0, x] = PINK if th == "rage" else WHITE
                if (x * 7 + f) % 11 == 0 and y0 - 1 >= 0:
                    c[y0 - 1, x] = V4 if th == "rage" else PALE
    for b, fx, d, _ in B_HITS:
        if fx == "wave":
            fx_wave(c, f, bf(b) + LAG)
    party(c, f, th)
    # effects
    for hid, beat, fx, who, dmg, px, py in P_HITS:
        k = f - HF[hid]
        tx, ty = px, py + 10
        if fx == "slash":
            fx_slash(c, tx, ty, k)
        elif fx == "frost":
            fx_frost(c, tx, ty, k)
        elif fx == "arrow":
            fx_arrow(c, 34, 93, tx, ty, k)
        elif fx == "bolt":
            fx_bolt(c, tx, ty, k, seed=beat)
        elif fx == "rising":
            fx_rising(c, tx, ty, k)
        elif fx == "tidebreaker":
            fx_slash(c, tx, ty, k - 1, big=True)
    for b, fx, d, _ in B_HITS:
        if fx == "roar":
            fx_roar(c, f, bf(b) + LAG, th)
    fx_maelstrom(c, f)
    if f == F_TB:
        c[:] = WHITE  # the one full-frame flash: the final blow
    if th in ("storm", "rage"):
        rain(c, f, GREY if th == "storm" else V3)
    elif th == "hero":
        rain(c, f, GREY, 30)
    return c


def shake(f):
    for b, _, _, amp in B_HITS:
        k = f - (bf(b) + LAG)
        if 0 <= k < 8:
            s = max(1, amp - k // 3)
            return ((s, -s)[k % 2], (-1, 1)[k % 2] if amp > 2 else 0)
    k = f - F_TB
    if 0 <= k < 10:
        s = max(1, 3 - k // 4)
        return ((s, -s)[k % 2], (s, -s)[(k // 2) % 2])
    return 0, 0


def apply_shake(c, dx, dy, h=FIELD_H):
    if not dx and not dy:
        return c
    p = np.pad(c[:h], 3, mode="edge")
    out = c.copy()
    out[:h] = p[3 - dy : 3 - dy + h, 3 - dx : 3 - dx + 320]
    return out


def ui(c, f, boxes):
    X.rect(c, 0, FIELD_H, 320, 180, BLACK)
    msg = message(f)
    cmd = msg[2] if msg else None
    X.box(c, 10, 125, 64, 171)
    for i, item in enumerate(MENU):
        y = 130 + i * 10
        X.text(c, item, 24, y, WHITE, boxes=boxes)
        if item == cmd:
            X.text(c, ">", 15, y, WHITE, boxes=boxes, tag="cursor")
    X.box(c, 66, 125, 310, 171)
    for i, (name, _) in enumerate(S.PARTY):
        y = 132 + i * 13
        hp, mx = hp_party(name, f), PARTY_MAX[name]
        X.text(c, name, 74, y, WHITE, boxes=boxes)
        X.rect(c, 116, y + 2, 252, y + 6, BLACK)
        w = int(math.ceil(134 * hp / mx))
        X.rect(
            c,
            117,
            y + 3,
            117 + w,
            y + 5,
            LIME if hp * 2 > mx else (GOLD if hp * 5 > mx else ORANGE),
        )
        X.text_r(c, f"{hp}/{mx}", 304, y, WHITE, boxes=boxes)
    if msg:
        s, n, _ = msg
        X.box(c, 10, 5, 310, 22)
        X.text(c, s[:n], 18, 11, WHITE, boxes=boxes, tag="msg " + s)
    if f < F_VICT:
        hp = hp_boss(f)
        X.box(c, 222, 24, 310, 46)
        X.text(c, "TIDE SERPENT", 229, 27, WHITE, boxes=boxes)
        X.text(c, "HP", 229, 36, WHITE, boxes=boxes)
        X.rect(c, 242, 37, 277, 42, BLACK)
        w = int(math.ceil(33 * hp / BOSS_MAX))
        X.rect(
            c,
            243,
            38,
            243 + w,
            41,
            LIME if hp * 2 > BOSS_MAX else (GOLD if hp * 5 > BOSS_MAX else ORANGE),
        )
        X.text_r(c, str(hp), 304, 36, WHITE, boxes=boxes)


TB_POP = (277, 80)  # centre x, rest y: on the serpent's neck, clear of the knight's strike and the X slash


def final_plate(f):
    """(text x, text y, plate box) of the final damage number at frame f, or None. It lands on the hit frame."""
    k = f - F_TB
    if k < 0 or f >= F_VICT:  # holds until the victory fanfare
        return None
    w = X.F.width(str(DMG["tb"]), 2)
    cx, y = TB_POP
    kb = min(k, POP_BOUNCE)
    y += (0, -2, -4, -5, -5, -4, -2, 0)[kb] if kb < 8 else 0
    x = cx - w // 2
    return x, y, (x - 4, y - 4, x + w + 4, y + 7 * 2 + 4)


def pops(c, f, boxes):
    for hid, beat, fx, who, dmg, px, py in P_HITS:
        k = f - HF[hid]
        if hid == "tb":
            r = final_plate(f)
            if r:  # black plate behind the big final number: it sits on the bright dawn sky
                x, y, (a, b, e, g) = r
                X.box(c, a, b, e, g, BLACK, GOLD)
                X.text(c, str(dmg), x, y, GOLD, 2, outline=BLACK, boxes=boxes, tag=f"pop {dmg}")
        else:
            pop(c, str(dmg), px, py, k, boxes, GOLD if hid.startswith("c") else WHITE)
    for b, fx, d, _ in B_HITS:
        k = f - (bf(b) + LAG)
        for name, v in d.items():
            x, y = PARTY_POS[name]
            pop(c, str(v), x + 8, y - 12, k, boxes)


def battle(f, boxes=None):
    c = field(f)
    c = apply_shake(c, *shake(f))
    pops(c, f, boxes)
    ui(c, f, boxes)
    return c


# ------------------------------------------------------------------ tracker intro
CH_NAMES = ["PULSE 1", "PULSE 2", "TRIANGLE", "NOISE"]
CH_COL = [GOLD, SKY, LIME, PINK]
COL_X = [30, 100, 170, 240]
ROWS_SHOWN, CUR_ROW, ROW_Y0, ROW_P = 11, 4, 75, 9


def scope(c, ch, f, x0, y0, w=60, h=11):
    T = song.ticks()
    tk = min(song.NTICKS - 1, int(f * song.TICK_HZ / FPS))
    mid = y0 + h // 2
    if ch < 2:
        fr, vol, du = (a[tk] for a in T["p1" if ch == 0 else "p2"])
        amp = int(round(vol / 15 * (h // 2)))
        if amp == 0:
            X.rect(c, x0, mid, x0 + w, mid + 1, DGREY)
            return
        per = max(10, int(round(28 * 262 / max(fr, 1))))
        for x in range(w):
            ph = ((x + f * 2) % per) / per
            yy = mid - amp if ph < du else mid + amp
            c[yy, x0 + x] = CH_COL[ch]
            if x and ((x - 1 + f * 2) % per) / per < du != (ph < du):
                X.rect(c, x0 + x, mid - amp, x0 + x + 1, mid + amp + 1, CH_COL[ch])
    elif ch == 2:
        fr, on = T["tri"][0][tk], T["tri"][1][tk]
        if not on:
            X.rect(c, x0, mid, x0 + w, mid + 1, DGREY)
            return
        per = max(8, int(round(24 * 110 / max(fr, 1))))
        for x in range(w):
            ph = ((x + f) % per) / per
            v = abs(ph * 2 - 1)  # triangle 1..0..1
            step = int(v * 7) / 7  # stepped like the 32-step sequencer
            c[int(mid - (h // 2) + step * (h - 1)), x0 + x] = CH_COL[ch]
    else:
        vol = T["noi"][1][tk]
        amp = int(round(vol / 15 * (h // 2)))
        if amp == 0:
            X.rect(c, x0, mid, x0 + w, mid + 1, DGREY)
            return
        r = random.Random(tk)
        for x in range(0, w, 2):
            yy = mid + r.randint(-amp, amp)
            X.rect(c, x0 + x, yy, x0 + x + 2, yy + 1, CH_COL[ch])


DUTY_TXT = {0.125: "DUTY 12.5%", 0.25: "DUTY 25%", 0.5: "DUTY 50%", 0.75: "DUTY 75%"}


def duty_txt(ch, f):
    if (
        ch < 2
    ):  # duty of the note playing now, or of the channel's first note before it enters
        n = song.active(ch, f / FPS) or song.channels()[ch][0]
        return DUTY_TXT[n.duty]
    return "32-STEP" if ch == 2 else "LFSR"


def tracker(f, boxes=None):
    c = X.new(BLACK)
    X.rect(c, 0, 5, 320, 25, BLUE)
    X.rect(c, 0, 25, 320, 26, NAVY)
    X.text_c(c, "STORM OVER SALTMERE", 160, 8, WHITE, 2, boxes=boxes, tag="title")
    g = int(f // 3)  # global row: one 16th = 3 frames
    X.text(c, "BPM 150", 14, 29, WHITE, boxes=boxes)
    X.text_r(
        c,
        "BAR/ROW %02d/%02X" % (g // 16, g % 16),
        306,
        29,
        WHITE,
        boxes=boxes,
        tag="barrow",
    )
    grid = song.cells()
    for i in range(4):
        x0 = COL_X[i]
        X.box(c, x0 - 3, 38, x0 + 66, 72, NAVY)
        X.text(c, CH_NAMES[i], x0 + 1, 42, WHITE, boxes=boxes)
        X.text(c, duty_txt(i, f), x0 + 1, 50, LGREY, boxes=boxes, tag="duty%d" % i)
        X.rect(c, x0 - 1, 58, x0 + 63, 70, BLACK)
        scope(c, i, f, x0 + 1, 59)
    X.rect(c, 10, 73, 310, 172, NAVY)
    cur_j = min(g, CUR_ROW)  # the cursor walks down to the middle, then the pattern scrolls under it
    yc = ROW_Y0 + cur_j * ROW_P
    X.rect(c, 10, yc - 1, 310, yc + 8, BLUE)
    for j in range(ROWS_SHOWN):
        r = g - cur_j + j
        if r < 0 or r >= len(grid):
            continue
        y = ROW_Y0 + j * ROW_P
        cur = j == cur_j
        rc = WHITE if cur or r % 4 == 0 else LGREY
        rc = GOLD if r % 16 == 0 and not cur else rc
        X.text(c, "%02X" % (r % 16), 14, y, rc, boxes=boxes, tag="rownum")
        for i in range(4):
            s = grid[r][i]
            tag = "cell"
            if s.startswith("..."):
                col, tag = (WHITE if cur else DGREY), "dots"  # empty-row marker: texture, not text to read
            elif s.startswith("---"):
                col = WHITE if cur else LGREY
            else:
                col = WHITE if cur else CH_COL[i]
            X.text(c, s, COL_X[i], y, col, boxes=boxes, tag=tag)
    return c


# ------------------------------------------------------------------ end card
def endcard(f, boxes=None):
    c = field(f)
    X.rect(c, 0, FIELD_H, 320, 180, BLACK)
    X.box(c, 40, 12, 280, 46, NAVY)
    X.text_c(c, END_TITLE, 160, 22, GOLD, 2, boxes=boxes, tag="end title")
    X.text_c(c, END_SUB, 160, 144, WHITE, 1, boxes=boxes, tag="end sub")
    for i, x in enumerate((60, 260)):  # two slow twinkles beside the subtitle
        if (f // 8 + i) % 3:
            X.sprite(c, S.DIAMOND, x - 2, 145, outline=None)
    return c


def frame(f, boxes=None):
    if f < F_WIPE0:
        return tracker(f, boxes)
    if f < F_WIPE1:
        k = (f - F_WIPE0 + 1) / (F_WIPE1 - F_WIPE0 + 1)
        a, b = tracker(f), battle(f, boxes)
        m = (X.XX / 320 + X.BY / 16 * 0.25) < k * 1.25
        return np.where(m, b, a).astype(np.uint8)
    if f >= F_END:
        return endcard(f, boxes)
    return battle(f, boxes)


def draw(t):
    f = int(round(t * FPS))
    return X.to_image(frame(f), E.W, E.H)


def layout(t):
    """Text boxes on screen at time t, in canvas pixels: (tag, (l, t, r, b), colour)."""
    boxes = []
    frame(int(round(t * FPS)), boxes)
    return boxes
