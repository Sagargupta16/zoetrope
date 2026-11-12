# music.py : the score and SFX for scenes.py, numpy only, on the same 120 BPM grid as SCHEDULE.
# Boops come straight from scenes.EVENTS (one per outline, capped at 16 per second), so sound cannot drift from picture.
# Usage: python music.py mix_raw.wav   (44.1 kHz stereo 16-bit; audio.master makes the -14 LUFS 48 kHz mix)
import math
import random
import sys
import wave

import numpy as np

import engine as E

E.W, E.H, E.FPS, E.SS = 1080, 1920, 30, 1
import scenes  # noqa: E402
import synth as S  # noqa: E402

SR = S.SR
B = 60 / scenes.BPM
DUR = scenes.DURATION
N = int(round(DUR * SR))
BOOP_CAP = 16  # per second, inside the 14 to 20 the card asks for
THUNK_G = 0.7  # lid thunk (0.30 before the bed duck); measured +8.1 dB over the bed, true peak still under -2.5
CLICK_G = 0.3  # its attack click
PRE_DB = -6.0  # music bus while the lid flips
DUCK_DB = -12.0  # music bus under the hit

_c = {}


def cached(key, fn):
    if key not in _c:
        _c[key] = fn()
    return _c[key]


def att(n, a=0.0015):
    return np.minimum(1, S.tt(n) / a)


def marimba(m, dur=0.7):
    n, f = int(dur * SR), S.hz(m)
    t = S.tt(n)
    x = (
        np.sin(2 * np.pi * f * t) * np.exp(-t / 0.30)
        + 0.28 * np.sin(2 * np.pi * 3.93 * f * t) * np.exp(-t / 0.045)
        + 0.07 * np.sin(2 * np.pi * 9.2 * f * t) * np.exp(-t / 0.012)
    )
    return x * att(n)


def bell(m, dur=2.0):
    n, f = int(dur * SR), S.hz(m)
    t = S.tt(n)
    x = (
        np.sin(2 * np.pi * f * t) * np.exp(-t / 0.9)
        + 0.45 * np.sin(2 * np.pi * 2.76 * f * t) * np.exp(-t / 0.35)
        + 0.2 * np.sin(2 * np.pi * 5.4 * f * t) * np.exp(-t / 0.12)
    )
    return x * att(n, 0.002)


def boop(m, tau):
    n, f = int(SR * min(0.45, 6 * tau)), S.hz(m)
    t = S.tt(n)
    return (
        (np.sin(2 * np.pi * f * t) + 0.2 * np.sin(4 * np.pi * f * t))
        * np.exp(-t / tau)
        * att(n, 0.002)
    )


def glide(f0, f1, dur, g=1.0):
    n = int(dur * SR)
    t = S.tt(n)
    f = f0 * (f1 / f0) ** (t / dur)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / dur) * g


def shaker():
    n = int(0.05 * SR)
    return S.hp(S.noise("shaker", n), 6000) * S.ex(n, 0.012) * 0.5


def crash(dur=1.6):
    n = int(dur * SR)
    return S.hp(S.noise("crash", n, dur), 5000) * S.ex(n, 0.45)


def thunk():
    n = int(0.35 * SR)
    t = S.tt(n)
    body = np.sin(2 * np.pi * (85 + 40 * np.exp(-t * 40)) * t) * np.exp(-t / 0.09)
    knock = S.lp(S.noise("thunk knock", n), 900) * np.exp(-t / 0.03) * 3
    return np.tanh(1.5 * (body + knock))


CHORDS = ["C", "Am", "F", "G"]
PADN = {"C": [55, 60, 64], "Am": [57, 60, 64], "F": [57, 60, 65], "G": [55, 59, 62]}
ROOT = {"C": 36, "Am": 33, "F": 41, "G": 43}
MEL = {
    "C": [76, 79, 81, 79, 76, 72],
    "Am": [76, 72, 69, 72, 76, 79],
    "F": [77, 76, 72, 69, 72, 76],
    "G": [79, 74, 71, 74, 79, 81],
}
MEL_R = [0, 0.75, 1.5, 2.0, 2.5, 3.25]
ARP = {
    "C": [60, 64, 67, 72],
    "Am": [57, 60, 64, 69],
    "F": [53, 57, 60, 65],
    "G": [55, 59, 62, 67],
}
PENTA = [72, 74, 76, 79, 81, 84, 86, 88]


def chord(b):
    return "F" if b == 28 else "C" if b == 29 else CHORDS[b % 4]


def section(b):  # a variation at each section change, so the loop has an arc
    for last, name in (
        (1, "intro"),
        (5, "A"),
        (11, "B"),
        (17, "C"),
        (21, "D"),
        (25, "E"),
        (27, "F"),
        (28, "G"),
    ):
        if b <= last:
            return name
    return "end"


def build():
    pad, bass, mar, drums = (np.zeros(N) for _ in range(4))
    sfx = np.zeros((2, N))
    KICK, CLAP, HAT_O = (
        cached("k", lambda: S.kick(1.0)),
        cached("c", S.clap),
        cached("o", lambda: S.hat(True)),
    )
    SHK = cached("s", shaker)
    kicks = []

    def P(bus, sig, t, g=1.0):
        S.put(bus, sig, t, g)

    for b in range(30):
        t0, ch, sec = b * 4 * B, chord(b), section(b)
        fc = 2200 if sec in ("D", "end") else 1400
        P(
            pad,
            cached(("pad", ch, fc), lambda: S.pad(PADN[ch], 4 * B, fc)),
            t0,
            {"intro": 0.30, "C": 0.22, "end": 0.40}.get(sec, 0.26),
        )
        if sec == "intro":
            for k in range(4):
                P(
                    mar,
                    cached(
                        ("m", 72 + [0, 4, 7, 4][k]),
                        lambda: marimba(72 + [0, 4, 7, 4][k]),
                    ),
                    t0 + k * B,
                    0.16,
                )
            if b == 1:
                for k in range(8):
                    P(drums, SHK, t0 + k * B / 2, 0.22 if k % 2 else 0.1)
            continue
        if sec == "end":
            P(drums, KICK, t0, 0.55)
            kicks.append(t0)
            P(drums, cached("crash", crash), t0, 0.12)
            for k, m in enumerate([72, 76, 79, 84]):
                P(mar, cached(("m", m), lambda: marimba(m, 1.2)), t0 + k * B / 4, 0.24)
            continue
        kpat = [0, 1, 2, 3] if sec == "C" else [0, 2] if sec == "E" else [0, 1.75, 2]
        for kb in kpat:
            P(drums, KICK, t0 + kb * B, 0.5)
            kicks.append(t0 + kb * B)
        if sec != "E":
            for cb in (1, 3):
                P(drums, CLAP, t0 + cb * B, 0.32)
        for k in range(16):
            P(drums, SHK, t0 + k * B / 4, [0.12, 0.06, 0.2, 0.06][k % 4])
        if sec == "C":
            for k in range(4):
                P(drums, HAT_O, t0 + (k + 0.5) * B, 0.16)
        if sec == "G":  # clap roll into the end card
            for k in range(4):
                P(drums, CLAP, t0 + 3.5 * B + k * B / 8, 0.12 + 0.05 * k)
        pattern = (
            [0, 0, 12, 0, 7, 0, 12, 7]
            if sec != "E"
            else [0, None, None, None, 7, None, None, None]
        )
        for k, iv in enumerate(pattern):
            if iv is None:
                continue
            m = ROOT[ch] + iv
            P(bass, cached(("b", m), lambda: S.bass(m, 0.22)), t0 + k * B / 2, 0.36)
        up = 12 if sec == "C" else 0
        if sec in ("A", "C", "D", "E", "F", "G") or (sec == "B" and b % 2 == 0):
            for r, m in zip(MEL_R, MEL[ch]):
                P(
                    mar,
                    cached(("m", m + up), lambda: marimba(m + up)),
                    t0 + r * B,
                    0.3 if up else 0.36,
                )
        if sec in ("B", "C"):
            step = B / 4 if sec == "C" else B / 2
            for k in range(int(4 * B / step)):
                m = ARP[ch][k % 4] + 12
                P(
                    mar,
                    cached(("m", m), lambda: marimba(m, 0.4)),
                    t0 + k * step,
                    0.07 if sec == "C" else 0.1,
                )
    P(
        drums, cached("riser", lambda: S.riser(0.875)), 3.0, 0.22
    )  # riser 3.0 to 3.875, a 16th of air, drop at 4.0

    music = S.duck(pad + bass + mar + drums, kicks, 4)
    music = S.reverb(music, 0.12)

    # glitch 1 (Nepal): music cuts to near silence; glitch 2 (pizza): tape stop, then near silence until the lid scene
    env = np.ones(N)
    ramp = int(0.01 * SR)

    def dip(a, b, lvl=0.03):
        i, j = int(a * SR), int(b * SR)
        env[i:j] = lvl
        env[max(0, i - ramp) : i] = np.linspace(1, lvl, i - max(0, i - ramp))
        env[j : j + ramp] = np.linspace(lvl, 1, len(env[j : j + ramp]))

    dip(*scenes.GLITCHES[0])
    ts0, tl = scenes.GLITCHES[1][0], 0.7
    i0, L = int(ts0 * SR), int(tl * SR)
    tt = np.arange(L) / SR
    src = music[i0 : i0 + int(0.45 * SR)].copy()
    music[i0 : i0 + L] = np.interp(
        (tt - tt**2 / (2 * tl)) * SR, np.arange(len(src)), src
    ) * np.linspace(1, 0.03, L)
    dip(ts0 + tl, scenes.SCHEDULE["lid"][0])
    music *= env

    # the lid thunk must read: the music bus breathes out while the lid flips (PRE_DB from 0.4 s before),
    # ducks DUCK_DB under the hit (10 ms in, held 0.1 s), then eases back by 0.5 s after it
    t_lid = next(e["t"] for e in scenes.EVENTS if e["snd"] == "thunk")
    pre, lvl = 10 ** (PRE_DB / 20), 10 ** (DUCK_DB / 20)
    ia, i0, i1, i2, i3 = (
        int(round(x * SR))
        for x in (t_lid - 0.40, t_lid - 0.01, t_lid, t_lid + 0.10, t_lid + 0.50)
    )
    g = np.ones(N)
    g[ia:i0] = 1 - (1 - pre) * np.sin(np.linspace(0, np.pi / 2, i0 - ia))
    g[i0:i1] = np.linspace(pre, lvl, i1 - i0)
    g[i1:i2] = lvl
    g[i2:i3] = 1 - (1 - lvl) * np.exp(-np.arange(i3 - i2) / SR / 0.09)
    music *= g

    # SFX bus: boops from EVENTS, plus the named hits
    rnd = random.Random(60)
    last, k_scene, prev_scene, kept = -1.0, 0, None, []
    evs = scenes.EVENTS
    for i, e in enumerate(evs):
        if e["snd"] != "boop":
            continue
        if e["scene"] != prev_scene:
            k_scene, prev_scene = 0, e["scene"]
        k_scene += 1
        if e["t"] - last < 1 / BOOP_CAP - 1e-9:
            continue
        last = e["t"]
        near = [
            abs(evs[j]["t"] - e["t"])
            for j in (i - 1, i + 1)
            if 0 <= j < len(evs) and j != i
        ]
        dense = bool(near) and min(near) < 0.09
        tau, g = (0.022, 0.05) if dense else (0.08, 0.09)
        m = PENTA[(k_scene - 1) % len(PENTA)]
        cx = (e["rect"][0] + e["rect"][2]) / 2
        pan = (
            max(-0.25, min(0.25, (cx / scenes.W - 0.5) * 0.5))
            if 0 <= cx <= scenes.W
            else 0.0
        )
        s = cached(("boop", m, tau), lambda: boop(m, tau))
        S.put(sfx[0], s, e["t"], g * (1 - pan))
        S.put(sfx[1], s, e["t"], g * (1 + pan))
        kept.append(e["t"])

    def both(sig, t, g, peak=False):
        for ch in (0, 1):
            (S.put_peak if peak else S.put)(sfx[ch], sig, t, g)

    # the thunk no longer stacks on the beat's kick (the bed is ducked under it), so it can be louder again
    both(thunk(), t_lid, THUNK_G, peak=True)
    nclick = int(
        0.015 * SR
    )  # a short low click on the attack, so the box shutting has an edge
    click = S.lp(S.noise("lid click", nclick), 1800) * S.ex(nclick, 0.0025)
    both(click / (np.abs(click).max() + 1e-9), t_lid - 0.002, CLICK_G)
    both(bell(96), 58.1, 0.20)
    both(bell(84), 58.1, 0.12)
    both(S.whoosh(0.9), 11.45, 0.22, peak=True)  # pull up to the map
    both(marimba(96, 0.5), 12.2, 0.22)  # pin lands
    # every whoosh seeds its own noise (seed=): one whoosh more or less leaves the others' samples as they were
    for k, (fa, fb) in enumerate(scenes.FOLDS):  # page swishes, peak mid-fold
        both(S.whoosh(0.4, seed=f"fold {k}"), (fa + fb) / 2, 0.12, peak=True)
    both(S.whoosh(0.4, seed="nepal"), 42.3, 0.12, peak=True)  # Nepal drops in
    for _ in range(7):  # digital chirps under the scrambled digits
        tb = rnd.uniform(*scenes.GLITCHES[0])
        n = int(0.03 * SR)
        sq = np.sign(np.sin(2 * np.pi * rnd.uniform(600, 1800) * S.tt(n))) * S.ex(
            n, 0.01
        )
        both(sq, tb, 0.04)
    both(S.whoosh(0.4, seed="box"), 51.7, 0.10, peak=True)  # box slides in
    both(
        S.whoosh(0.4, seed="lid"), 52.85, 0.10, peak=True
    )  # lid flips (was 0.15; it sat right before the thunk)
    both(S.whoosh(0.75), 54.35, 0.22, peak=True)  # the film shrinks into the phone
    both(glide(700, 350, 0.25), 56.5, 0.06)  # the hand outline breaks
    both(S.tick(), 57.0, 0.25)  # the hand squares off

    out = np.stack([music + sfx[0], music + sfx[1]], 1)
    fade = int(0.3 * SR)
    out[-fade:] *= np.linspace(1, 0, fade)[:, None] ** 1.5
    out = out / (np.abs(out).max() + 1e-9) * 0.89
    return out, kept


def write(path, y):
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((y * 32767).astype("<i2").tobytes())


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "mix_raw.wav"
    y, kept = build()
    write(path, y)
    rate = max(np.histogram(kept, bins=np.arange(0, DUR + 1, 1.0))[0])
    print(
        f"wrote {path}: {len(y) / SR:.3f} s, boops {len(kept)} of {sum(e['snd'] == 'boop' for e in scenes.EVENTS)} "
        f"boop events, max boops in one second {rate}"
    )
