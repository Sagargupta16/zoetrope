# music.py : 66 BPM ambient bed in D major from the same grid and cues as scenes.py (numpy only, seeded).
# Detuned additive pad, sub root, sparse bell arpeggio, cue bells, convolution reverb; pad alone in the think pause.
# usage: python music.py mix_raw.wav
import sys
import wave

import numpy as np

import synth as S
import scenes as SC

SR = S.SR
N = int(round(SC.DURATION * SR))
bt = SC.bt

CHORDS = [
    (0, "D"),
    (4, "Bm"),
    (8, "G"),
    (12, "A"),
    (16, "D"),
    (20, "Bm"),
    (24, "G"),
    (28, "A"),
    (30, "D"),
    (34, "Bm"),
    (38, "G"),
    (42, "A"),
    (44, "D"),
    (48, "Bm"),
    (52, "G"),
    (58, "A"),
    (60, "G"),
    (62, "A"),
    (63, "D"),
]
VOICE = {
    "D": [57, 62, 66, 69],
    "Bm": [54, 59, 62, 66],
    "G": [55, 59, 62, 67],
    "A": [57, 61, 64, 69],
}
ROOT = {"D": 38, "Bm": 35, "G": 43, "A": 33}


def chord_at(beat):
    name = CHORDS[0][1]
    for b, c in CHORDS:
        if b <= beat:
            name = c
    return name


def env(n, att, rel_start, rel):
    t = np.arange(n) / SR
    a = np.clip(t / att, 0, 1)
    a = 0.5 - 0.5 * np.cos(np.pi * a)  # sine-shaped swell
    r = np.clip(1 - (t - rel_start) / rel, 0, 1)
    return a * r


def pad_voice(notes, dur, cents, att=0.9, rel=1.3, hold=None):
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = np.zeros(n)
    for m in notes:
        for c in cents:
            f = S.hz(m) * 2 ** (c / 1200)
            ph = 2 * np.pi * f * t
            x += (
                np.sin(ph)
                + 0.32 * np.sin(2 * ph)
                + 0.12 * np.sin(3 * ph)
                + 0.05 * np.sin(4 * ph)
            )
    x /= len(notes) * len(cents)
    lfo = 1 + 0.06 * np.sin(2 * np.pi * 0.11 * t + notes[0])  # slow breathing
    return x * lfo * env(n, att, (hold if hold is not None else dur - rel), rel)


def bell(m, dur=3.2):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = S.hz(m)
    y = (
        np.sin(2 * np.pi * f * t) * np.exp(-t / 1.4)
        + 0.45 * np.sin(2 * np.pi * 2.76 * f * t) * np.exp(-t / 0.35)
        + 0.2 * np.sin(2 * np.pi * 5.4 * f * t) * np.exp(-t / 0.12)
    )
    return y * np.minimum(1, t / 0.003)


def soft_tick():
    n = int(0.08 * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * 2093 * t) * np.exp(-t / 0.018) * np.minimum(1, t / 0.001)


def sub(m, dur, rel=0.8):
    n = int(dur * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * S.hz(m) * t) * env(n, 0.4, dur - rel, rel)


def ir(seed, dur=2.6, tau=0.55):
    rng = np.random.RandomState(seed)
    n = int(dur * SR)
    t = np.arange(n) / SR
    x = rng.standard_normal(n) * np.exp(-t / tau)
    k = 6
    x = np.convolve(x, np.ones(k) / k, "same")  # darker tail
    x[: int(0.012 * SR)] = 0  # short pre-delay
    return x / np.sqrt((x**2).sum())  # unit energy (pitfalls 6)


def conv(x, h):
    L = len(x) + len(h) - 1
    nf = 1 << (L - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, nf) * np.fft.rfft(h, nf), nf)[: len(x)]


def put(bus, sig, t0, g=1.0, pan=0.0):
    """Stereo place with constant-power pan at round(t0 * SR)."""
    a = (pan + 1) * np.pi / 4
    S.put(bus[0], sig, t0, g * np.cos(a))
    S.put(bus[1], sig, t0, g * np.sin(a))


def build():
    pad = np.zeros((2, N))
    bed = np.zeros((2, N))  # everything that leaves during the think pause
    # pad and sub, one segment per chord change, overlapping into the next
    for i, (b, c) in enumerate(CHORDS):
        b_next = CHORDS[i + 1][0] if i + 1 < len(CHORDS) else 66
        t0, t1 = bt(b), bt(b_next)
        last = i + 1 == len(CHORDS)
        dur = (SC.DURATION - t0) if last else (t1 - t0 + 1.3)
        hold = (SC.DURATION - t0 - 0.8) if last else None
        rel = 0.8 if last else 1.3
        S.put(pad[0], pad_voice(VOICE[c], dur, (-7, 0, 5), rel=rel, hold=hold), t0, 0.5)
        S.put(pad[1], pad_voice(VOICE[c], dur, (-4, 0, 8), rel=rel, hold=hold), t0, 0.5)
        put(
            bed,
            sub(
                ROOT[c],
                min(dur, t1 - t0 + 0.6) if not last else dur,
                0.6 if not last else 0.8,
            ),
            t0,
            0.1,
        )
    # sparse bell arpeggio: three chord tones per bar, skipped near cue figures
    quiet = [
        (bt(21), bt(31)),
        (bt(49.5), bt(53)),
        (bt(55), bt(58)),
        (bt(62.5), SC.DURATION),
    ]
    cue_bells = SC.CUES["bell"] + [SC.CUES["answer"]]
    for bar in range(17):
        for j, off in enumerate((0, 1.5, 3)):
            beat = bar * 4 + off
            tb = bt(beat)
            if (
                tb >= SC.DURATION - 0.5
                or any(a <= tb < b for a, b in quiet)
                or any(abs(tb - c) < 0.6 for c in cue_bells)
            ):
                continue
            note = VOICE[chord_at(beat)][j + 1] + 12
            put(bed, bell(note), tb, 0.1, pan=(-0.3, 0.1, 0.3)[j])
    # cue sounds, each on its picture time
    put(bed, bell(74), SC.CUES["bell"][0], 0.26)  # hook: one bell
    put(bed, bell(81), SC.CUES["bell"][1], 0.24)  # title
    for tk in SC.CUES["ticks"]:  # the two points land
        S.put_peak(bed[0], soft_tick(), tk, 0.10)
        S.put_peak(bed[1], soft_tick(), tk, 0.10)
    for k, tr in enumerate(SC.CUES["rise"]):  # rising figure while h shrinks
        put(
            bed,
            bell([74, 76, 78, 79, 81, 83, 85, 86][k]),
            tr,
            0.10 + 0.012 * k,
            pan=-0.2 + 0.05 * k,
        )
    for k, m in enumerate((74, 78, 81, 86)):  # warm chord as the tangent turns gold
        put(bed, bell(m, 4.0), SC.CUES["warm"], 0.12)
    for tp, m in zip(SC.CUES["drops"], (81, 86, 78)):  # one bell per plotted point
        put(bed, bell(m), tp, 0.18)
    put(bed, bell(86), SC.CUES["answer"], 0.16)  # the answer
    for k, m in enumerate((62, 69, 74, 78, 81)):  # final D major chord
        put(bed, bell(m, 3.0), SC.CUES["final"], 0.11)
    # reverb (unit-energy impulses, decorrelated left and right)
    hL, hR = ir(11), ir(12)
    pad_w = np.stack([conv(pad[0], hL), conv(pad[1], hR)])
    bed_w = np.stack([conv(bed[0], hL), conv(bed[1], hR)])
    bed_mix = bed + 0.4 * bed_w
    pad_mix = pad + 0.3 * pad_w
    # think pause: the bed bus (sub, bells, their tails) leaves, the pad stays
    g = np.ones(N)
    t = np.arange(N) / SR
    a, b = SC.CUES["pause"]
    g = np.where((t >= a - 0.35) & (t < a), 1 - (t - (a - 0.35)) / 0.35, g)
    g = np.where((t >= a) & (t < b - 0.1), 0.0, g)
    g = np.where((t >= b - 0.1) & (t < b), (t - (b - 0.1)) / 0.1, g)
    out = pad_mix + bed_mix * g
    fade = np.clip((SC.DURATION - t) / 0.8, 0, 1) ** 1.5  # ring-out in the last 0.8 s
    out = out * fade
    return out / (np.abs(out).max() + 1e-9) * 0.89, pad_mix * fade, bed_mix * g * fade


def write(path, st):
    pcm = (np.clip(st.T, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


if __name__ == "__main__":
    out, pad_only, bed_only = build()
    p = sys.argv[1] if len(sys.argv) > 1 else "mix_raw.wav"
    write(p, out)
    sec = lambda x, s: float(
        np.sqrt((x[:, int(s * SR) : int((s + 1) * SR)] ** 2).mean())
    )  # noqa: E731
    k = 0.89 / (np.abs(pad_only + bed_only).max() + 1e-9)
    print(f"wrote {p}: {out.shape[1] / SR:.3f} s, peak {np.abs(out).max():.3f}")
    for s in (5, 25, 45, 50, 51, 52, 53, 56, 59):
        print(
            f"  second {s}: total rms {20 * np.log10(sec(out, s) + 1e-12):6.1f} dBFS, bed bus {20 * np.log10(sec(bed_only * k, s) + 1e-12):7.1f} dBFS"
        )
