# song.py : "Storm over Saltmere", 150 BPM, 4/4, A minor -> A major fanfare. The ONE note-event table:
# chip.py renders it to audio and scenes.py draws the tracker and keys every hit from it.
# Rows are 16th notes: 0.1 s each, exactly 3 frames at 30 fps and 6 driver ticks at 60 Hz.
from collections import namedtuple
from functools import lru_cache

import numpy as np

BPM = 150
BEAT = 60 / BPM  # 0.4 s
BAR = 4 * BEAT  # 1.6 s
RPB = 16  # rows per bar
ROW = BAR / RPB  # 0.1 s
NBARS = 36
RING = 2.4  # ring-out after bar 36 starts
DURATION = NBARS * BAR + RING  # 60.0 s
TICK_HZ = 60
TPR = int(round(ROW * TICK_HZ))  # 6 ticks per row
NTICKS = int(round(DURATION * TICK_HZ))  # 3600
CPU = 1789773.0
NOISE_PERIODS = [
    4,
    8,
    16,
    32,
    64,
    96,
    128,
    160,
    202,
    254,
    380,
    508,
    762,
    1016,
    2034,
    4068,
]

CHORDS = (
    "Am Am F G Am E E E Am F G Am Am F Dm E Am E "
    "Dm Dm Am Am Bb Bb E E F G Em Am F E A D E A"
).split()
assert len(CHORDS) == NBARS
SECTION_BARS = {  # bar ranges [a, b)
    "tracker": (0, 6),
    "encounter": (6, 8),
    "battle": (8, 18),
    "rage": (18, 26),
    "heroic": (26, 32),
    "victory": (32, 36),
}
ROOT = {
    "Am": 45,
    "F": 41,
    "G": 43,
    "E": 40,
    "Dm": 38,
    "Bb": 46,
    "Em": 40,
    "A": 45,
    "D": 38,
}
TONES = {  # triad as semitones over the root
    "Am": (0, 3, 7),
    "F": (0, 4, 7),
    "G": (0, 4, 7),
    "E": (0, 4, 7),
    "Dm": (0, 3, 7),
    "Bb": (0, 4, 7),
    "Em": (0, 3, 7),
    "A": (0, 4, 7),
    "D": (0, 4, 7),
}
SEMI = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
NAMES12 = ["C-", "C#", "D-", "D#", "E-", "F-", "F#", "G-", "G#", "A-", "A#", "B-"]

Note = namedtuple(
    "Note", "row midi rows vol duty inst"
)  # row = global row (bar*16 + r); midi None for noise
Drum = namedtuple("Drum", "row kind vol")


def midi(n):
    s = SEMI[n[0]]
    i = 1
    if n[1] in "#b":
        s += 1 if n[1] == "#" else -1
        i = 2
    return 12 * (int(n[i:]) + 1) + s


def name(m):
    return NAMES12[m % 12] + str(m // 12 - 1)


def tokens(bar, s, vol, duty, inst, total=RPB):
    out, r = [], 0
    for tok in s.split():
        n, d = tok.split(":")
        d = int(d)
        if n != "r":
            out.append(Note(bar * RPB + r, midi(n), d, vol, duty, inst))
        r += d
    assert r == total, (bar, s, r)
    return out


# ---------------------------------------------------------------- pulse 1: lead
LEAD = {
    4: "A4:6 C5:2 B4:2 A4:2 E4:4",
    5: "G#4:6 A4:2 B4:4 E5:4",
    6: "E4:1 G#4:1 B4:1 D5:1 E4:1 G#4:1 B4:1 D5:1 G#4:1 B4:1 D5:1 E5:1 G#4:1 B4:1 D5:1 E5:1",
    7: "B4:1 D5:1 E5:1 G#5:1 B4:1 D5:1 E5:1 G#5:1 D5:1 E5:1 G#5:1 B5:1 E5:1 G#5:1 B5:1 E6:1",
    8: "A4:3 E5:3 A5:2 G5:2 E5:2 C5:4",
    9: "F5:3 E5:3 C5:2 A4:4 C5:2 D5:2",
    10: "D5:3 B4:3 G4:2 B4:2 D5:2 G5:4",
    11: "E5:6 D5:2 C5:2 B4:2 A4:4",
    12: "A4:3 E5:3 A5:2 B5:2 C6:2 B5:2 A5:2",
    13: "A5:4 G5:2 F5:2 E5:2 F5:2 A5:4",
    14: "D6:6 C6:2 A5:2 F5:2 D5:4",
    15: "E5:4 G#5:4 B5:4 E6:4",
    16: "C6:6 B5:2 A5:2 E5:2 C5:2 E5:2",
    17: "B5:2 A5:2 G#5:2 E5:2 G#5:2 B5:2 D6:2 E6:2",
    18: "D5:2 D5:2 F5:2 A5:4 G5:2 F5:2 E5:2",
    19: "D5:6 A4:2 D5:2 F5:2 G5:2 A5:2",
    20: "C6:4 B5:2 A5:2 E5:4 A5:4",
    21: "G5:2 A5:2 B5:2 C6:2 B5:4 A5:4",
    22: "D6:4 C6:2 A#5:2 F5:4 A#5:4",
    23: "A5:2 A#5:2 C6:2 D6:2 F6:8",
    24: "E5:2 F5:2 F#5:2 G5:2 G#5:2 A5:2 A#5:2 B5:2",  # chromatic climbing run
    25: "C6:2 C#6:2 D6:2 D#6:2 E6:8",
    26: "C5:2 F5:2 A5:2 C6:6 A5:2 C6:2",
    27: "D6:6 B5:2 G5:2 B5:2 D6:2 G6:2",
    28: "E6:4 D6:2 B5:2 G5:4 B5:4",
    29: "C6:4 B5:2 A5:2 E5:2 A5:2 C6:4",
    30: "F4:1 A4:1 C5:1 F5:1 A4:1 C5:1 F5:1 A5:1 C5:1 F5:1 A5:1 C6:1 F5:1 A5:1 C6:1 F6:1",  # rising build
    31: "E6:8 B5:2 G#5:2 B5:2 D6:2",
    32: "C#5:2 E5:2 A5:4 E5:2 A5:2 C#6:4",
    33: "D6:4 C#6:2 B5:2 A5:2 F#5:2 A5:4",
    34: "B5:4 G#5:2 E5:2 B5:2 D6:2 E6:4",
    35: "C#6:4 B5:2 A5:2 B5:2 C#6:2 E6:4",
}
# ---------------------------------------------------------------- pulse 2: harmony and arps
HARM = {
    6: "E4:2 F4:2 E4:2 F4:2 E4:2 F4:2 E4:2 F4:2",
    7: "E4:2 F4:2 E4:2 F4:2 G#4:2 A4:2 B4:2 C5:2",
    24: "E4:2 F4:2 F#4:2 G4:2 G#4:2 A4:2 A#4:2 B4:2",
    25: "C5:2 C#5:2 D5:2 D#5:2 E5:8",
    30: "r:1 F4:1 A4:1 C5:1 F4:1 A4:1 C5:1 F5:1 A4:1 C5:1 F5:1 A5:1 C5:1 F5:1 A5:1 C6:1",
    31: "G#5:8 E5:2 D5:2 E5:2 G#5:2",
    32: "A4:2 C#5:2 E5:4 C#5:2 E5:2 A5:4",
    33: "A5:4 A5:2 F#5:2 F#5:2 D5:2 F#5:4",
    34: "G#5:4 E5:2 B4:2 G#5:2 B5:2 B5:4",
    35: "A5:4 G#5:2 E5:2 G#5:2 A5:2 C#6:4",
}


def lead_style(bar):
    if bar < 6:
        return 10, 0.5, "lead"
    if bar < 8:
        return 7 + (bar - 6) * 3, 0.25, "arp"
    if bar < 18:
        return 11, 0.5, "lead"
    if bar < 26:
        return 12, 0.25, "lead"
    if bar < 32:
        return 12, 0.5, "lead"
    return 13, 0.25, "fan"


def harm_style(bar):
    if bar < 6:
        return 6, 0.25, "arp"
    if bar < 8:
        return 7, 0.125, "lead"
    if bar < 18:
        return 6, 0.125, "arp"
    if bar < 26:
        return 7, 0.25, "arp" if bar < 24 else "lead"
    if bar < 32:  # heroic section: 75 percent duty (the fourth 2A03 setting)
        return 7, 0.75, "arp" if bar < 31 else "lead"
    return 9, 0.5, "fan"


def arp_bar(bar, step, octave_root, vol, duty):
    ch = CHORDS[bar]
    r = octave_root + ((ROOT[ch] - 45 + 6) % 12) - 6  # root kept within E3..D4
    t = TONES[ch]
    pat = [r + t[0], r + t[1], r + t[2], r + t[1]]
    return [
        Note(bar * RPB + i * step, pat[i % 4], step, vol, duty, "arp")
        for i in range(RPB // step)
    ]


@lru_cache(None)
def channels():
    p1, p2, tri, noi = [], [], [], []
    for bar, s in LEAD.items():
        v, d, ins = lead_style(bar)
        p1 += tokens(bar, s, v, d, ins)
    p1 += tokens(36, "A5:24", 12, 0.5, "ring", total=24)
    for bar in range(2, 36):
        v, d, ins = harm_style(bar)
        if bar in HARM:
            p2 += tokens(bar, HARM[bar], v, d, ins)
        elif bar < 6:
            p2 += arp_bar(bar, 2, 57, v, d)  # 8th arps from A3 up
        else:
            p2 += arp_bar(bar, 1, 57, v, d)  # 16th arps
    p2 += tokens(36, "C#5:24", 9, 0.5, "ring", total=24)
    # triangle bass
    for bar in range(NBARS):
        rt = ROOT[CHORDS[bar]]
        if bar < 8 or 26 <= bar < 30 or bar >= 32:
            pat = [0, 0, 12, 0, 0, 0, 12, 0]
            for i, o in enumerate(pat):
                tri.append(Note(bar * RPB + i * 2, rt + o, 2, 15, None, "tri"))
        elif bar < 18:
            pat = [0, 12, 0, 12, 0, 12, 0, 10 if bar % 2 else 12]
            for i, o in enumerate(pat):
                tri.append(Note(bar * RPB + i * 2, rt + o, 2, 15, None, "tri"))
        elif bar < 26 or bar == 30:
            for i in range(RPB):
                tri.append(
                    Note(
                        bar * RPB + i,
                        rt + (12 if i % 4 == 2 else 0),
                        1,
                        15,
                        None,
                        "tri",
                    )
                )
        else:  # bar 31: the final blow rings on the downbeat
            tri.append(Note(bar * RPB, rt, 8, 15, None, "tri"))
            for i in range(4):
                tri.append(
                    Note(
                        bar * RPB + 8 + i * 2,
                        rt + (12 if i % 2 else 0),
                        2,
                        15,
                        None,
                        "tri",
                    )
                )
    tri.append(Note(36 * RPB, 45, 16, 15, None, "tri"))

    # noise drums: K kick, S snare, H hat, X crash
    def d(bar, rows, kind, vol):
        for r in rows:
            noi.append(Drum(bar * RPB + r, kind, vol))

    for bar in range(6, 36):
        sec = "B" if 18 <= bar < 26 else "x"
        kicks = [0, 6, 8] if sec == "B" else [0, 8]
        snares = [4, 12]
        hats = [r for r in range(RPB) if r % 2 == 1] if sec == "B" else [2, 6, 10, 14]
        if bar == 7:
            snares = [4, 12, 13, 14, 15]
            hats = [2, 6, 10]
        if bar in (11, 15, 21):
            snares = [4, 12, 14, 15]
            hats = [2, 6, 10]
        if bar == 17:
            snares = [4, 12, 13, 14, 15]
            hats = [2, 6, 10]
        if bar == 25:
            kicks, snares, hats = [0, 8], [2, 4, 6, 10, 12, 14], []
        if bar == 30:
            kicks, snares, hats = [0, 8], list(range(RPB)), []
        if bar == 31:
            kicks, snares, hats = [8], [12], [2, 4, 6, 10, 14]
        if bar == 35:
            snares = [4, 12, 13, 14, 15]
            hats = [2, 6, 10]
        if bar == 32:
            kicks = [8]  # the crash takes row 0
        snares = [r for r in snares if r not in kicks]
        d(
            bar,
            [r for r in hats if r not in kicks and r not in snares],
            "H",
            5 if sec == "B" else 6,
        )
        d(bar, kicks, "K", 15)
        for r in snares:
            vol = (
                6 + (9 * r) // 15
                if bar == 30
                else (11 if r in (13, 14, 15) and bar != 25 else 13)
            )
            d(bar, [r], "S", vol)
    d(31, [0], "X", 15)
    d(32, [0], "X", 12)
    d(36, [0], "X", 13)
    noi.sort()
    rows = [n.row for n in noi]
    assert len(rows) == len(set(rows)), "two noise events on one row"
    return tuple(p1), tuple(p2), tuple(tri), tuple(noi)


# noise instruments: per-tick (period index, volume); period index 0 = highest pitch
DRUMS = {
    "K": ([9, 10, 11, 12, 13, 13, 14, 14], [15, 14, 12, 10, 7, 5, 3, 1]),
    "S": (
        [5, 6, 6, 7, 7, 7, 7, 7, 7, 7, 7, 7],
        [15, 13, 12, 10, 9, 8, 6, 5, 4, 3, 2, 1],
    ),
    "H": ([1, 1, 1, 1], [6, 4, 2, 1]),
    "X": (
        [10, 8, 4, 3] + [3] * 56,
        [15, 15, 14, 13] + [int(round(12 * (1 - i / 56) ** 1.6)) for i in range(56)],
    ),
}
NOISE_NOTE = {
    "K": 15 - 9,
    "S": 15 - 5,
    "H": 15 - 1,
    "X": 15 - 10,
}  # FamiTracker-style noise note 0-F


def drum_at(row):
    for n in channels()[3]:
        if n.row == row:
            return n.kind
    return None


def beat_row(beat):
    return int(round(beat * 4))


def env(inst, vol, n_ticks):
    """Volume per driver tick for one note."""
    k = np.arange(n_ticks)
    if inst == "lead":
        v = vol - np.minimum(4, k // 2)
    elif inst == "arp":
        v = vol - np.minimum(vol - 1, k)
    elif inst == "fan":
        v = np.where(k < 1, vol - 3, vol - np.minimum(2, k // 6))
    elif inst == "ring":
        v = np.round(vol * (1 - k / n_ticks) ** 1.4)
    else:
        v = np.full(n_ticks, vol)
    return np.clip(v, 0, 15).astype(np.int16)


@lru_cache(None)
def ticks():
    """Per-tick register state of all four channels, like a 60 Hz sound driver."""
    p1, p2, tri, noi = channels()
    out = {}
    tsec = np.arange(NTICKS) / TICK_HZ
    for key, notes in (("p1", p1), ("p2", p2)):
        f = np.zeros(NTICKS)
        v = np.zeros(NTICKS, np.int16)
        du = np.full(NTICKS, 0.5)
        for n in notes:
            a, b = n.row * TPR, min(NTICKS, (n.row + n.rows) * TPR)
            if b <= a:
                continue
            hz = 440.0 * 2 ** ((n.midi - 69) / 12)
            k = np.arange(b - a)
            if (
                n.inst in ("lead", "fan", "ring") and n.rows >= 3
            ):  # delayed vibrato, 6 Hz, about 18 cents
                cents = np.where(
                    k >= 10, 18 * np.sin(2 * np.pi * 6 * (k - 10) / TICK_HZ), 0
                )
                hz = hz * 2 ** (cents / 1200)
            per = np.clip(np.round(CPU / (16 * hz)) - 1, 8, 2047)  # 11-bit pulse period
            f[a:b] = CPU / (16 * (per + 1))
            v[a:b] = env(n.inst, n.vol, b - a)
            if n.inst != "ring" and b - a > 2:  # note gap so repeated notes re-attack
                v[b - 1] = 0
            du[a:b] = n.duty
        out[key] = (f, v, du)
    f = np.zeros(NTICKS)
    on = np.zeros(NTICKS, np.int16)
    for n in tri:
        a, b = n.row * TPR, min(NTICKS, (n.row + n.rows) * TPR)
        hz = 440.0 * 2 ** ((n.midi - 69) / 12)
        per = np.clip(np.round(CPU / (32 * hz)) - 1, 2, 2047)
        f[a:b] = CPU / (32 * (per + 1))
        gate = (
            max(1, (b - a) - 2) if n.rows <= 2 else (b - a) - 1
        )  # linear counter cuts a little early
        on[a : a + gate] = 15
    out["tri"] = (f, on)
    pi = np.zeros(NTICKS, np.int16)
    nv = np.zeros(NTICKS, np.int16)
    for n in noi:
        pers, vols = DRUMS[n.kind]
        a = n.row * TPR
        L = min(len(vols), NTICKS - a)
        pi[a : a + L] = pers[:L]
        nv[a : a + L] = np.round(np.array(vols[:L]) * n.vol / 15)
    out["noi"] = (pi, nv)
    out["t"] = tsec
    return out


@lru_cache(None)
def cells():
    """Tracker text per global row and channel: 'A-4 B' (note, volume hex) or '... .' / '--- .'."""
    p1, p2, tri, noi = channels()
    n_rows = NBARS * RPB + 24
    grid = [["... ."] * 4 for _ in range(n_rows)]
    for ci, notes in enumerate((p1, p2, tri)):
        ends = {}
        for n in notes:
            vol = "F" if ci == 2 else "%X" % n.vol
            grid[n.row][ci] = f"{name(n.midi)} {vol}"
            ends[n.row + n.rows] = True
        starts = {n.row for n in notes}
        for r in ends:
            if r < n_rows and r not in starts:
                grid[r][ci] = "--- ."
    for n in noi:
        grid[n.row][3] = "%X-# %X" % (NOISE_NOTE[n.kind], n.vol)
    return grid


def active(ch, t):
    """The note playing on pulse/triangle channel ch (0, 1, 2) at time t, or None."""
    notes = channels()[ch]
    r = t / ROW
    best = None
    for n in notes:
        if n.row <= r < n.row + n.rows:
            best = n
    return best
