# build_audio.py : the 96 BPM lo-fi score in F major (FM Rhodes, sub bass, soft kit, bell, marimba, pings)
# plus every SFX, placed from the same SCHEDULE / CUE grid as the picture (scenes.py). numpy only.
# Writes mix_raw.wav (44.1 kHz stereo, peak 0.89); audio.master() makes the -14 LUFS mix later.
from __future__ import annotations

import math
import wave

import numpy as np

import engine as E

E.W, E.H, E.FPS, E.SS = 1920, 1080, 30, 2
import scenes as S  # noqa: E402
import synth as Y  # noqa: E402

SR = Y.SR
N = int(round(S.DURATION * SR))
B, T, CUE = S.B, S.T, S.CUE


def tt(n):
    return np.arange(n) / SR


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


class Bus:
    def __init__(self):
        self.L, self.R = np.zeros(N), np.zeros(N)

    def put(self, sig, t0, g=1.0, pan=0.0):
        i = int(round(t0 * SR))
        if i >= N:
            return
        if i < 0:
            sig, i = sig[-i:], 0
        j = min(N, i + len(sig))
        s = sig[: j - i] * g
        self.L[i:j] += s * math.cos((pan + 1) * math.pi / 4) * math.sqrt(2)
        self.R[i:j] += s * math.sin((pan + 1) * math.pi / 4) * math.sqrt(2)

    def put_peak(self, sig, t_event, g=1.0, pan=0.0):
        """Loudest instant (1 ms moving average of abs) lands on t_event (beat-sync.md, step 4)."""
        k = max(1, int(SR * 0.001))
        env = np.convolve(np.abs(sig), np.ones(k) / k, "same")
        self.put(sig, t_event - int(np.argmax(env)) / SR, g, pan)


# ---------- instruments ----------
def rhodes(m, dur, vel=1.0):
    n = int((dur + 0.4) * SR)
    t = tt(n)
    f = hz(m)
    idx = (1.5 * np.exp(-t / 0.18) + 0.3) * vel
    car = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * t))
    tine = (
        np.sin(2 * np.pi * 7.0 * f * t + 0.8 * np.sin(2 * np.pi * f * t))
        * np.exp(-t / 0.03)
        * 0.1
        * vel
    )
    amp = np.minimum(1, t / 0.004) * np.exp(-t / max(0.6, 1.9 - 0.012 * (m - 48)))
    rel = np.clip((dur + 0.4 - t) / 0.4, 0, 1)
    return (
        (car + tine) * amp * rel * (1 + 0.06 * np.sin(2 * np.pi * 4.2 * t)) * 0.5 * vel
    )


def chord_rhodes(bus, notes, t0, dur, vel=1.0, g=1.0):
    for k, m in enumerate(notes):  # tiny strum, low to high
        bus.put(
            rhodes(m, dur, vel),
            t0 + 0.006 * k,
            g / len(notes) * 2.2,
            pan=-0.25 + 0.5 * k / max(1, len(notes) - 1),
        )


def pad(notes, dur, att=0.8, rel=0.9, bright=0.3):
    n = int((dur + rel) * SR)
    t = tt(n)
    x = np.zeros(n)
    for m in notes:
        f = hz(m)
        for d in (-0.004, 0.0, 0.005):  # each partial's phase from its own stream
            ph = Y.rng_for("pad", m, d).uniform(0, 2 * np.pi)
            w = 2 * np.pi * f * (1 + d) * t + ph
            x += np.sin(w) + bright * 0.5 * np.sin(2 * w) + bright * 0.2 * np.sin(3 * w)
    x /= 3 * len(notes)
    return x * np.minimum(1, t / att) * np.clip((dur + rel - t) / rel, 0, 1)


def sub(m, dur):
    n = int((dur + 0.08) * SR)
    t = tt(n)
    f = hz(m)
    x = np.tanh(1.3 * (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t)))
    env = (
        np.minimum(1, t / 0.01)
        * np.clip((dur + 0.08 - t) / 0.08, 0, 1)
        * (0.75 + 0.25 * np.exp(-t / 0.25))
    )
    return x * env * 0.6


def kick():
    n = int(0.45 * SR)
    t = tt(n)
    ph = 2 * np.pi * np.cumsum(46 + 90 * np.exp(-t * 28)) / SR
    click = Y.lp(Y.noise("kick click", n) * np.exp(-t / 0.002), 3000) * 0.5
    return np.tanh(1.5 * np.sin(ph) * np.exp(-t / 0.2)) * 0.9 + click


def marimba(m, dur=0.9, vel=1.0):
    n = int(dur * SR)
    t = tt(n)
    f = hz(m)
    x = (
        np.sin(2 * np.pi * f * t) * np.exp(-t / 0.45)
        + 0.35 * np.sin(2 * np.pi * 4 * f * t) * np.exp(-t / 0.06)
        + 0.12 * np.sin(2 * np.pi * 9.9 * f * t) * np.exp(-t / 0.02)
    )
    return x * np.minimum(1, t / 0.002) * vel


def bell(m, dur=2.0, vel=1.0):
    n = int(dur * SR)
    t = tt(n)
    f = hz(m)
    x = (
        np.sin(2 * np.pi * f * t) * np.exp(-t / 0.9)
        + 0.5 * np.sin(2 * np.pi * 2.76 * f * t) * np.exp(-t / 0.35)
        + 0.25 * np.sin(2 * np.pi * 5.4 * f * t) * np.exp(-t / 0.12)
    )
    return x * np.minimum(1, t / 0.002) * vel


def ping(m):
    """Generic two-blip notification sound (no real product's sound)."""
    n = int(0.32 * SR)
    t = tt(n)
    out = np.zeros(n)
    for k, (mm, d) in enumerate(((m, 0.0), (m + 5, 0.075))):
        i = int(d * SR)
        tk = tt(n - i)
        out[i:] += (
            np.sin(2 * np.pi * hz(mm) * tk)
            * np.exp(-tk / (0.07 if k == 0 else 0.11))
            * np.minimum(1, tk / 0.002)
        )
    return out


def tok(f):
    n = int(0.14 * SR)
    t = tt(n)
    x = np.sin(2 * np.pi * f * t * (1 + 0.12 * np.exp(-t / 0.01))) * np.exp(-t / 0.035)
    x += 0.4 * np.sin(2 * np.pi * 2.6 * f * t) * np.exp(-t / 0.012)
    x += Y.hp(Y.noise("tok", n, f), 1500) * np.exp(-t / 0.002) * 0.3
    return x * 0.8


def crash(dur=1.4):
    n = int(dur * SR)
    t = tt(n)
    return Y.hp(Y.noise("crash", n, dur), 5000) * np.exp(-t / 0.45)


def typekey(k):
    n = int(0.05 * SR)
    t = tt(n)
    click = Y.hp(Y.noise("typekey", n, k), 2500) * np.exp(-t / 0.004)
    thunk = np.sin(2 * np.pi * 170 * t) * np.exp(-t / 0.012) * 0.5
    return click * 0.7 + thunk


# pre-rendered kit, every sound seeded on its own (synth.rng_for, synth.noise): adding or moving one sound
# leaves every other sample as it was; the round-robin hats and keys get one seed each
KICK = kick()
SNARE = Y.lp(Y.snare(0.8), 4200)
HATS = [Y.lp(Y.hat(seed=k), 9000) for k in range(4)]
CLAP = Y.clap()
TICK = Y.tick(4200)
TAP = Y.tick(2600)
KEYS = [typekey(k) for k in range(3)]

CH = {
    "F": [53, 57, 60, 64, 67],  # Fmaj9
    "Dm": [50, 53, 57, 60, 64],  # Dm9
    "Bb": [46, 50, 53, 57, 60],  # Bbmaj9
    "C": [48, 53, 58, 62, 67],  # C9sus4
}
ROOT = {"F": 41, "Dm": 38, "Bb": 34, "C": 36}
LOOP = ["F", "Dm", "Bb", "C"]


def chord_of(bar):
    if bar <= 3:
        return ["Dm", "Bb", "C"][bar - 1]
    if bar == 4:
        return "F"
    if bar <= 20:
        return LOOP[(bar - 5) % 4]
    return {21: "F", 22: "Bb", 23: "F", 24: "F"}[bar]


SWING = 0.56  # offbeat eighths sit at 56 percent of the beat
music, drums, sfx = Bus(), Bus(), Bus()
kicks: list[float] = []

# ---------- the bed ----------
for bar in range(1, 25):
    t0 = T(bar)
    c = chord_of(bar)
    groove = 5 <= bar <= 22 and bar not in (
        18,
        19,
        20,
    )  # the word scene drops to pad, hats, riser
    thin = 12 <= bar <= 14
    # pad
    if bar <= 3:
        music.put(
            pad(
                CH[c], S.BAR if bar < 3 else S.BAR - 0.75, att=1.0, rel=0.5, bright=0.15
            ),
            t0,
            0.60,
        )
    elif bar == 4:
        music.put(pad(CH["F"], S.BAR, att=0.6, rel=0.8, bright=0.25), t0, 0.50)
    elif bar <= 22:
        music.put(
            pad(CH[c] if bar != 22 else CH["Bb"], S.BAR, att=0.5, rel=0.6),
            t0,
            0.14 if groove else 0.24,
        )
    # Rhodes
    if bar == 4:
        chord_rhodes(music, CH["F"], t0, 2.0, 0.7, 0.85)
    elif bar == 18:
        chord_rhodes(music, CH[c], t0, S.BAR, 0.8, 0.8)
    elif 5 <= bar <= 22:
        notes = CH[c]
        if bar == 22:
            chord_rhodes(music, CH["Bb"], t0, 1.4 * B, 0.85, 0.8)
            chord_rhodes(music, CH["Bb"], t0 + (1 + SWING) * B, 0.4 * B, 0.6, 0.6)
            chord_rhodes(music, CH["C"], t0 + 2 * B, 1.4 * B, 0.85, 0.8)
            chord_rhodes(music, CH["C"], t0 + (3 + SWING) * B, 0.4 * B, 0.6, 0.6)
        else:
            v = 0.8 + 0.1 * Y.rng_for("rhodes velocity", bar).uniform()
            chord_rhodes(music, notes, t0, 1.4 * B, v, 0.8)
            chord_rhodes(music, notes[1:], t0 + (1 + SWING) * B, 0.45 * B, v * 0.7, 0.6)
            chord_rhodes(music, notes[2:], t0 + 3 * B, 0.6 * B, v * 0.75, 0.6)
    # sub bass
    if groove:
        r = ROOT[c] if bar != 22 else ROOT["Bb"]
        music.put(sub(r, 1.5 * B), t0, 0.9)
        music.put(sub(ROOT["C"] if bar == 22 else r, 1.0 * B), t0 + 2 * B, 0.8)
        music.put(
            sub(r + 12 if bar != 22 else ROOT["C"] + 7, 0.4 * B),
            t0 + (3 + SWING) * B,
            0.5,
        )
    elif bar in (18, 19, 20):
        music.put(sub(ROOT[c], S.BAR - 0.05), t0, 0.7)
    # drums
    for beat in range(4):
        tb = t0 + beat * B
        if groove and not thin:
            if beat in (0, 2):
                drums.put(KICK, tb, 0.85)
                kicks.append(tb)
            if beat == 2 and bar % 2 == 0:
                drums.put(KICK, tb - (1 - SWING) * B, 0.45)
            if beat in (1, 3):
                drums.put(SNARE, tb, 0.42, pan=0.05)
            drums.put(HATS[(bar + beat) % 4], tb, 0.22, pan=0.25)
            drums.put(HATS[(bar + beat + 1) % 4], tb + SWING * B, 0.30, pan=0.25)
        elif thin:
            if beat == 0:
                drums.put(KICK, tb, 0.6)
                kicks.append(tb)
            drums.put(HATS[beat % 4], tb, 0.14, pan=0.25)
        elif bar == 19:
            drums.put(HATS[beat % 4], tb + SWING * B, 0.22, pan=0.25)
        elif bar == 20:
            drums.put(HATS[beat % 4], tb, 0.16, pan=0.25)
            drums.put(HATS[(beat + 1) % 4], tb + SWING * B, 0.24, pan=0.25)
            for s in range(2 if beat < 2 else 4):  # soft snare build into the payoff
                drums.put(
                    SNARE,
                    tb + s * B / (2 if beat < 2 else 4),
                    0.08 + 0.05 * beat,
                    pan=0.05,
                )

# the final chord (55.0): Rhodes Fmaj9 + pad + sub, rings out through the end hold
tc = CUE["chord"]
final = [53, 60, 64, 67, 69, 72]
chord_rhodes(music, final, tc, 4.2, 0.9, 0.85)
music.put(pad(final, 4.0, att=0.15, rel=1.0, bright=0.3), tc, 0.22)
music.put(sub(29, 3.6), tc, 0.8)
music.put(sub(41, 3.6), tc, 0.5)
drums.put(KICK, tc, 0.7)
kicks.append(tc)
sfx.put(bell(89, 3.0), tc + 0.01, 0.06, pan=0.2)

# ---------- quiet mode: low-pass the music from 16 kHz to about 600 Hz, thin drums, reopen at 34.4 ----------
mix_bus_L = music.L + drums.L
mix_bus_R = music.R + drums.R
(d0, dd), (u0, ud) = CUE["lp"]
a_i, b_i = int((d0 - 0.05) * SR), int((u0 + ud + 0.1) * SR)
tq = np.arange(a_i, b_i) / SR
fc = np.full(len(tq), 16000.0)
kd = np.clip((tq - d0) / dd, 0, 1)
ku = np.clip((tq - u0) / ud, 0, 1)
fc = np.where(tq < u0, 16000.0 * (600 / 16000) ** kd, 600.0 * (16000 / 600) ** ku)
coef = np.exp(-2 * np.pi * fc / SR).tolist()


def lp_var(x, coef, stages=3):
    y = x.tolist()
    for _ in range(stages):
        s = y[0]
        for i, a in enumerate(coef):
            s = (1 - a) * y[i] + a * s
            y[i] = s
    return np.array(y)


mix_bus_L[a_i:b_i] = lp_var(mix_bus_L[a_i:b_i], coef)
mix_bus_R[a_i:b_i] = lp_var(mix_bus_R[a_i:b_i], coef)

# sidechain on kicks, then a little room
mix_bus_L = Y.reverb(Y.duck(mix_bus_L, kicks, 3), 0.16)
mix_bus_R = Y.reverb(Y.duck(mix_bus_R, kicks, 3), 0.16)

# ---------- SFX from the CUE grid ----------
pent = [77, 79, 81, 84, 86, 89, 91, 93]  # F major pentatonic, high
for i, tcard in enumerate(CUE["card_t"]):
    x = S.CARD_POS[i][0]
    sfx.put_peak(
        ping(pent[(i * 3) % len(pent)]),
        tcard,
        0.14 + 0.16 * i / 21,
        pan=(x - 960) / 960 * 0.6,
    )
# reverse suck into 7.0, then near silence until 7.5
suck = crash(1.3)[::-1] * np.linspace(0, 1, int(1.3 * SR)) ** 2
sfx.put(suck, CUE["suck_end"] - len(suck) / SR, 0.35)
for k, th in enumerate(CUE["hops"]):  # three wood toks on the hops
    sfx.put_peak(tok([784, 880, 1047][k]), th, 0.45)
sfx.put(crash(1.6), CUE["drop"], 0.05)
sfx.put_peak(Y.whoosh(0.6), CUE["zoom"][0] + 0.35, 0.12)
a, b = CUE["count"]
for k in range(1, 25):  # one tick per minute change; the 25th change is the chime
    sfx.put_peak(TICK, a + (b - a) * (60 * k / 1500), 0.28, pan=0.2 if k % 2 else -0.2)
for m in (89, 93, 96):
    sfx.put(bell(m, 2.0), b, 0.07, pan=0.1)
for tp in CUE["taps"]:
    sfx.put_peak(TAP, tp, 0.35)
d0, d1 = CUE["drag"]
gl = [65, 67, 69, 72, 74, 77, 79, 81, 84, 86]
for k, m in enumerate(gl):  # marimba glissando on the drag
    sfx.put(
        marimba(m, 0.6, 0.8),
        d0 + 0.15 + k * (d1 - d0 - 0.35) / len(gl),
        0.10,
        pan=-0.2 + 0.04 * k,
    )
for tc_ in CUE["checks"]:
    sfx.put_peak(CLAP, tc_, 0.30, pan=0.1)
for tb_, m in zip(CUE["bell"], (77, 72)):  # two-note midnight bell
    sfx.put(bell(m, 2.2), tb_, 0.12)
for tg in (CUE["toggle_on"], CUE["wipe_light"][0]):
    sfx.put_peak(TAP, tg, 0.3)
streak_notes = iter(
    [65, 67, 69, 72, 74, 77]
)  # ascending F major pentatonic, one per filled day
for i, tf in enumerate(CUE["fills"]):
    if i != CUE["rest"]:
        sfx.put(marimba(next(streak_notes), 0.9), tf, 0.22, pan=-0.3 + 0.1 * i)
for i, tk in enumerate(CUE["type_t"]):
    if S.DICT_TEXT[i] != " ":
        jit = Y.rng_for("type key", i)
        sfx.put_peak(
            KEYS[i % 3],
            tk,
            0.10 + 0.04 * jit.uniform(),
            pan=-0.15 + 0.3 * jit.uniform(),
        )
r0, rd = CUE["riser"]
sfx.put(Y.riser(rd), r0, 0.10)
sfx.put_peak(CLAP, CUE["check2"], 0.28)
for k, m in enumerate((84, 88, 91, 96)):  # small sparkle with the confetti
    sfx.put(bell(m, 0.8), CUE["check2"] + 0.04 * k, 0.035, pan=-0.3 + 0.2 * k)
sfx.put_peak(tok(880), CUE["lk_dot"][1], 0.2)

# lo-fi dust: sparse crackle and a faint hiss (seeded)
dust = np.zeros(N)
crackle = Y.rng_for("crackle").uniform(0, S.DURATION, int(4 * S.DURATION))
for j, p in enumerate(np.sort(crackle)):
    i = int(p * SR)
    n = min(N - i, 40)
    one = Y.rng_for("crackle", j)
    dust[i : i + n] += (
        one.uniform(-1, 1, n) * np.exp(-np.arange(n) / 6) * one.uniform(0.2, 1.0)
    )
hiss = np.convolve(Y.noise("hiss", N), np.ones(6) / 6, "same")
dust = dust * 0.02 + hiss * 0.004

L = mix_bus_L + sfx.L + dust
R = mix_bus_R + sfx.R + dust
fa, fd = CUE["fade"]  # 0.6 s fade at the very end
i0 = int(fa * SR)
fade = np.linspace(1, 0, N - i0) ** 1.5
L[i0:] *= fade
R[i0:] *= fade
peak = max(np.abs(L).max(), np.abs(R).max())
L, R = L / peak * 0.89, R / peak * 0.89

with wave.open("mix_raw.wav", "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((np.stack([L, R], 1) * 32767).astype("<i2").tobytes())

# measurements for the report (by measurement, not by ear)
mono = (L + R) / 2
rms = [
    20 * math.log10(np.sqrt(np.mean(mono[int(s * SR) : int((s + 1) * SR)] ** 2)) + 1e-9)
    for s in range(int(S.DURATION))
]
print(
    f"wrote mix_raw.wav {N / SR:.3f} s, {N} samples, raw peak scaled from {peak:.3f} to 0.89"
)
print("per-second RMS dBFS:", " ".join(f"{v:.0f}" for v in rms))


def hf_ratio(a, b, cut=1500):
    seg = (
        mix_bus_L[int(a * SR) : int(b * SR)] + mix_bus_R[int(a * SR) : int(b * SR)]
    ) / 2
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
    f = np.fft.rfftfreq(len(seg), 1 / SR)
    return 10 * math.log10(spec[f > cut].sum() / spec.sum())


print(
    "music-bus energy above 1.5 kHz, dB of total:",
    f"before quiet (25.0-28.0) {hf_ratio(25.0, 28.0):.1f}",
    f"| in quiet (29.5-34.0) {hf_ratio(29.5, 34.0):.1f}",
    f"| after reopen (35.5-38.5) {hf_ratio(35.5, 38.5):.1f}",
)
