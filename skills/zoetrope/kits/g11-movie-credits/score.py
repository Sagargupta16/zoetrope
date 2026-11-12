# score.py : the music for "Salt and Signal" (numpy only), from the same grid and beam clock as scenes.py.
# D minor, 60 BPM (bar 4 s), 15 bars = 60 s. Writes mix_raw.wav (44.1 kHz stereo 16-bit) and cues.json.
from __future__ import annotations

import json
import wave

import numpy as np

import engine as E

E.W, E.H, E.FPS, E.SS = 1920, 1080, 24, 1
import scenes as SC  # noqa: E402
import synth as S  # noqa: E402

SR = S.SR
DUR = SC.DURATION
N = int(round(DUR * SR))
B = SC.BEAT
T = np.arange(N) / SR


def tt(n: int) -> np.ndarray:
    return np.arange(n) / SR


def hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def sm(x, e0, e1):
    k = np.clip((x - e0) / (e1 - e0), 0, 1)
    return k * k * (3 - 2 * k)


def fft_filter(
    x: np.ndarray, lo: float | None = None, hi: float | None = None, order: int = 2
) -> np.ndarray:
    """Zero-phase Butterworth-shaped band filter in the frequency domain (no scipy, no per-sample loop)."""
    n = len(x)
    nf = 1 << int(np.ceil(np.log2(n + SR // 2)))
    X = np.fft.rfft(x, nf)
    f = np.fft.rfftfreq(nf, 1 / SR)
    Hm = np.ones_like(f)
    if hi:
        Hm /= np.sqrt(1 + (f / hi) ** (2 * order))
    if lo:
        Hm /= np.sqrt(1 + (lo / np.maximum(f, 1e-3)) ** (2 * order))
    return np.fft.irfft(X * Hm, nf)[:n]


def piano(m: float, dur: float = 3.5, vel: float = 0.5) -> np.ndarray:
    n = int(dur * SR)
    t = tt(n)
    f = hz(m)
    tau = float(np.clip(2.4 * (440 / f) ** 0.35, 0.7, 5.5))
    rng = S.rng_for("piano", m, dur, vel)  # one stream per note
    y = np.zeros(n)
    for k in range(1, 10):
        fk = k * f * np.sqrt(1 + 0.0004 * k * k)
        if fk > 11000:
            break
        y += (
            (vel ** (0.1 * k) / k**1.15)
            * np.sin(2 * np.pi * fk * t + rng.uniform(0, 6.283))
            * np.exp(-t / (tau / (1 + 0.5 * (k - 1))))
        )
    y *= 0.55 + 0.45 * np.exp(-t / 0.25)
    hammer = (
        fft_filter(rng.standard_normal(n) * np.exp(-t / 0.01), lo=900, hi=4500) * 0.05
    )
    return (
        (y * np.minimum(1, t / 0.004) + hammer) * vel * np.clip((dur - t) / 0.4, 0, 1)
    )


def strings(
    notes, dur: float, att: float = 0.9, rel: float = 1.0, fc: float = 1500.0
) -> np.ndarray:
    n = int(dur * SR)
    t = tt(n)
    y = np.zeros(n)
    for m in notes:
        for det in (-0.004, -0.0015, 0.0012, 0.0035):
            f = hz(m) * (1 + det)
            vib = 1 + 0.0018 * np.sin(
                2 * np.pi * (4.6 + det * 200) * t
                + S.rng_for("strings", m, det).uniform(0, 6.283)
            )
            ph = np.cumsum(f * vib) / SR
            y += 2 * (ph % 1.0) - 1
    y = fft_filter(y, lo=55, hi=fc) / (4 * len(notes))
    return y * np.minimum(1, t / att) * np.clip((dur - t) / rel, 0, 1)


def bell(m: float, dur: float = 2.2, vel: float = 0.3) -> np.ndarray:
    n = int(dur * SR)
    t = tt(n)
    f = hz(m)
    y = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.9)
    y += 0.4 * np.sin(2 * np.pi * 2.76 * f * t) * np.exp(-t / 0.35)
    y += 0.2 * np.sin(2 * np.pi * 5.4 * f * t) * np.exp(-t / 0.15)
    return y * np.minimum(1, t / 0.003) * vel


def shimmer(
    notes=(86, 93, 98), rise: float = 0.45, tail: float = 1.4, vel: float = 0.12
) -> np.ndarray:
    """Soft glassy cluster that swells to its peak at `rise` s, for a beam pass."""
    n = int((rise + tail * 3) * SR)
    t = tt(n)
    y = np.zeros(n)
    for i, m in enumerate(notes):
        for det in (-0.003, 0.0028):
            ph = S.rng_for("shimmer", m, det).uniform(0, 6.283)
            y += np.sin(2 * np.pi * hz(m) * (1 + det) * t + ph) / (1 + 0.4 * i)
    trem = 0.75 + 0.25 * np.sin(2 * np.pi * 7.0 * t)
    env = np.where(t < rise, (t / rise) ** 2, np.exp(-(t - rise) / tail))
    return y * trem * env * vel / len(notes)


def foghorn(dur: float = 3.4) -> np.ndarray:
    """Low saw near 65 Hz through a low-pass, slow attack, a small pitch drop at the end."""
    n = int(dur * SR)
    t = tt(n)
    f = 65.4 * (1 - 0.07 * sm(t, dur - 0.7, dur))
    ph = np.cumsum(f) / SR
    y = (
        (2 * (ph % 1) - 1)
        + 0.6 * (2 * ((ph * 1.0075) % 1) - 1)
        + 0.5 * np.sin(2 * np.pi * ph)
    )
    y = fft_filter(y, lo=38, hi=360)
    return y * np.minimum(1, t / 0.35) ** 1.5 * np.clip((dur - t) / 0.6, 0, 1)


def tick(f: float) -> np.ndarray:
    n = int(0.06 * SR)
    t = tt(n)
    nz = S.rng_for("tick", f).standard_normal(n)
    click = fft_filter(nz * np.exp(-t / 0.003), lo=1800, hi=6000)
    return click * 0.6 + np.sin(2 * np.pi * f * t) * np.exp(-t / 0.014) * 0.5


def thump() -> np.ndarray:
    n = int(0.4 * SR)
    t = tt(n)
    ph = 2 * np.pi * np.cumsum(hz(38) * (1 + 0.6 * np.exp(-t / 0.03))) / SR
    return np.sin(ph) * np.exp(-t / 0.16) * np.minimum(1, t / 0.006)


def key_click(i: int) -> np.ndarray:
    n = int(0.05 * SR)
    t = tt(n)
    return (
        fft_filter(
            S.rng_for("key click", i).standard_normal(n) * np.exp(-t / 0.003),
            lo=1500,
            hi=6000,
        )
        * 0.5
        + np.sin(2 * np.pi * 310 * t) * np.exp(-t / 0.01) * 0.3
    )


def ir(seed: int, dur: float = 3.2) -> np.ndarray:
    n = int(dur * SR)
    t = tt(n)
    r = np.random.default_rng(seed).standard_normal(n) * np.exp(-t / 0.85)
    r = fft_filter(r, lo=120, hi=6500)
    return r / np.sqrt(
        (r**2).sum()
    )  # unit energy (pitfall 6: normalised impulse response)


def convolve(x: np.ndarray, h: np.ndarray) -> np.ndarray:
    nf = 1 << int(np.ceil(np.log2(len(x) + len(h))))
    return np.fft.irfft(np.fft.rfft(x, nf) * np.fft.rfft(h, nf), nf)[: len(x)]


def bar_t(k: int, beat: float = 0.0) -> float:
    return SC.BAR * k + beat * B


def build():
    music = np.zeros(N)  # reverb bus
    dry = np.zeros((N, 2))  # pre-panned, no reverb
    cues: dict[str, list] = {"bar_lines": [SC.BAR * k for k in range(15)]}

    # open-fifth drone D2 A2 D3, the whole piece. Its own stream, seeded 2026 as the approved build drew it, so the
    # 6 s beating of its detuned pairs lands where it did; no other sound draws from it
    dr = np.zeros(N)
    ph = iter(np.random.default_rng(2026).uniform(0, 6.283, 18))
    for m, g in ((38, 0.5), (45, 0.35), (50, 0.22)):
        for det in (-0.0012, 0.0011):
            for k, a in ((1, 1.0), (2, 0.35), (3, 0.12)):
                dr += g * a * np.sin(2 * np.pi * hz(m) * k * (1 + det) * T + next(ph))
    dr *= np.minimum(1, T / 2.5) * (0.8 + 0.2 * np.sin(2 * np.pi * T / 9.0)) / 2.5
    dr *= 1 - 0.35 * sm(T, 40.0, 40.05) * (
        1 - sm(T, 52.0, 52.5)
    )  # thinner inside the lamp room

    # sea wash: filtered noise in slow swells; muffled inside (40-52); bigger in the weather (28-40)
    inside = sm(T, 40.0, 40.05) * (1 - sm(T, 52.0, 52.5))
    weather = sm(T, 28.0, 31.5) * (1 - sm(T, 39.9, 40.0))
    sea = np.zeros((N, 2))
    for ch, seed in ((0, 11), (1, 12)):
        nz = np.random.default_rng(seed).standard_normal(N)
        body = fft_filter(nz, lo=140, hi=1300)
        hiss = fft_filter(nz, lo=2200, hi=7000)
        muff = fft_filter(nz, lo=60, hi=320)
        wave_env = (
            0.5 + 0.5 * (0.5 + 0.5 * np.sin(2 * np.pi * T / 7.3 + 1.0 + 0.4 * ch)) ** 2
        )
        foam = (0.5 + 0.5 * np.sin(2 * np.pi * T / 7.3 + 0.2 + 0.4 * ch)) ** 4
        outside = (body * wave_env + 0.45 * hiss * foam) * (1 + 0.9 * weather)
        sea[:, ch] = outside * (1 - inside) + muff * 1.6 * inside * wave_env
        sea[:, ch] += (
            fft_filter(
                np.random.default_rng(seed + 20).standard_normal(N), lo=3000, hi=9000
            )
            * 0.5
            * weather
        )
    sea /= np.sqrt((sea[: 8 * SR] ** 2).mean()) + 1e-9
    sea *= 0.055 * np.minimum(1, T / 1.5)[:, None]

    # sparse piano from bar 3 (8 s); low cluster on the 32.0 downbeat; D-A-F# at 56.0
    PIANO = [
        (2, [(0, [46, 58], 0.5), (1, [65], 0.42), (2, [62], 0.38), (3, [69], 0.42)]),
        (3, [(0, [41, 53], 0.5), (1, [69], 0.42), (2, [65], 0.38), (3.5, [72], 0.4)]),
        (4, [(0, [38, 50], 0.55), (1, [69], 0.42), (2, [65], 0.4), (3, [62], 0.4)]),
        (5, [(0, [46, 58], 0.52), (1, [70], 0.42), (2, [65], 0.4), (3, [62], 0.4)]),
        (6, [(0, [41, 53], 0.52), (1, [69], 0.42), (2, [72], 0.42), (3, [77], 0.45)]),
        (7, [(0, [48, 55], 0.5), (1, [67], 0.4), (2, [64], 0.38)]),
        (8, [(0, [26, 33, 38, 40, 41], 0.48), (2, [69], 0.45), (3, [74], 0.45)]),
        (9, [(0, [46, 58], 0.5), (1, [65], 0.42), (2, [70], 0.42), (3, [74], 0.45)]),
        (
            13,
            [(0, [48, 55], 0.5), (1, [64], 0.42), (2, [45, 57], 0.5), (3, [73], 0.48)],
        ),
        (14, [(0, [38, 50, 62], 0.6), (0.75, [69], 0.5), (1.5, [78], 0.5)]),
    ]
    for k, hits in PIANO:
        for beat, notes, vel in hits:
            for m in notes:
                S.put(
                    music, piano(m, 5.0 if m < 45 else 3.6, vel), bar_t(k, beat), 0.32
                )
    OST = {
        10: (38, [62, 69, 65, 69, 74, 69, 65, 69]),
        11: (34, [58, 65, 62, 65, 70, 65, 62, 65]),
        12: (41, [53, 60, 57, 60, 65, 60, 57, 60]),
    }
    for k, (bass, line) in OST.items():  # soft eighth-note ostinato in the lamp room
        S.put(music, piano(bass, 4.0, 0.45), bar_t(k), 0.3)
        for i, m in enumerate(line):
            S.put(music, piano(m, 1.6, 0.25), bar_t(k, i * 0.5), 0.22)
    cues["piano_cluster"] = [bar_t(8)]

    # low strings from 16 s; swell through bar 14 (C then A); D major from 56
    STR = {
        4: [38, 45, 53],
        5: [34, 41, 50],
        6: [41, 48, 57],
        7: [36, 43, 52],
        8: [38, 45, 53],
        9: [34, 41, 50],
        10: [38, 45, 53],
        11: [34, 41, 50],
        12: [41, 48, 57],
    }
    for k, notes in STR.items():
        g = 0.5 if k < 8 else (0.62 if k < 10 else 0.4)
        S.put(
            music,
            strings(notes, 4.9, att=0.9 if k > 4 else 1.6, rel=1.0),
            bar_t(k) - (0.0 if k == 4 else 0.25),
            g,
        )
    sw = strings([36, 43, 52, 60], 2.6, att=0.6, rel=0.5)
    S.put(music, sw * np.linspace(0.45, 0.8, len(sw)), bar_t(13) - 0.1, 1.0)
    sw = strings([33, 40, 49, 57], 2.4, att=0.4, rel=0.35)
    S.put(music, sw * np.linspace(0.8, 1.1, len(sw)), bar_t(13, 2) - 0.05, 1.0)
    fin = strings([38, 45, 54, 62], 4.0, att=0.12, rel=1.6)
    S.put(music, fin, bar_t(14), 0.95)
    cues["d_major"] = [bar_t(14)]

    # riser into the title (28-32): noise riser, rising tone and a reversed piano chord, all ending on 32.0
    rz = S.riser(4.0)
    rz = rz / (np.abs(rz).max() + 1e-9)
    S.put(dry[:, 0], rz, 28.0, 0.16)
    S.put(dry[:, 1], rz, 28.0, 0.16)
    n4 = int(4.0 * SR)
    t4 = tt(n4)
    f4 = hz(50) * 2 ** (2 * (t4 / 4.0) ** 1.6)
    S.put(music, np.sin(2 * np.pi * np.cumsum(f4) / SR) * (t4 / 4.0) ** 2 * 0.08, 28.0)
    rev = sum(piano(m, 2.0, 0.5) for m in (62, 65, 69))[::-1]
    S.put(music, rev, 32.0 - 2.0, 0.25)

    # foghorn on the title downbeat
    S.put(music, foghorn(), 32.0, 0.42)
    cues["foghorn"] = [32.0]

    # shimmer on every beam pass (the far end crosses picture centre); a wider one for the directed-by turn
    sh_t = SC.shimmer_times()
    for i, ts in enumerate(sh_t):
        wide = ts > 52.0
        sig = shimmer(
            (86, 93, 98, 100) if wide else (86, 93, 98),
            0.45,
            1.9 if wide else 1.4,
            0.16 if wide else 0.11,
        )
        pan = 0.2 if i % 2 else -0.2
        tmp = np.zeros(N)
        S.put_peak(tmp, sig, ts)
        music[:] += tmp * 0.6
        dry[:, 0] += tmp * 0.4 * (1 - pan)
        dry[:, 1] += tmp * 0.4 * (1 + pan)
    settle = 56.0 + 0.5  # the last pass sweeps while the beam settles on the boat
    tmp = np.zeros(N)
    S.put_peak(tmp, shimmer((86, 93, 97), 0.45, 1.6, 0.1), settle)
    music += tmp
    cues["shimmer"] = sh_t + [settle]

    # lamp room: glints as the light band crosses the credits, clockwork ticks and a soft pulse on beats
    glint_notes = [74, 77, 79, 81, 84, 86]
    gl = []
    for j in range(6):
        tg = 40.0 + 2 * j - SC.BAND_LEAD + (SC.BAND_X0 - 1290.0) / SC.BAND_V
        tmp = np.zeros(N)
        S.put_peak(tmp, bell(glint_notes[j], 2.0, 0.22), tg)
        music += tmp
        gl.append(tg)
    cues["glints"] = gl
    tk = []
    for i in range(12):
        tb = 40.0 + i * B
        tmp = np.zeros(N)
        S.put_peak(tmp, tick(1900 if i % 2 == 0 else 1450), tb)
        pan = 0.15 if i % 2 else -0.15
        dry[:, 0] += tmp * 0.11 * (1 - pan)
        dry[:, 1] += tmp * 0.11 * (1 + pan)
        S.put(music, thump(), tb, 0.12)
        tk.append(tb)
    cues["ticks"] = tk

    # quiet key clicks under the typed line
    n_ch = len(SC.CREDITS["typed"]["lines"][0][0][0][0])
    dt = (SC.TYPE_T1 - SC.TYPE_T0) / (n_ch - 1)
    for i in range(n_ch):
        tmp = np.zeros(N)
        S.put(tmp, key_click(i), SC.TYPE_T0 + i * dt)
        dry[:, 0] += tmp * 0.035
        dry[:, 1] += tmp * 0.035

    # mix: music bus with a 3.2 s synthetic reverb, then drone, sea and dry hits
    wetL, wetR = convolve(music, ir(101)), convolve(music, ir(202))
    out = np.zeros((N, 2))
    out[:, 0] = music + 0.32 * wetL + dr
    out[:, 1] = music + 0.32 * wetR + dr
    out += sea + dry
    out *= (1 - sm(T, 58.6, 60.0) ** 1.5)[
        :, None
    ] * 0.98 + 0.0  # ring-out, no hard stop
    out[-int(0.02 * SR) :] *= np.linspace(1, 0, int(0.02 * SR))[:, None]
    return out, cues


def write(path: str, y: np.ndarray) -> float:
    peak = float(np.abs(y).max())
    y = y / (peak + 1e-9) * 0.89
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(y, -1, 1) * 32767).astype("<i2").tobytes())
    return peak


if __name__ == "__main__":
    y, cues = build()
    pk = write("mix_raw.wav", y)
    with open("cues.json", "w", encoding="utf-8") as f:
        json.dump(cues, f, indent=1)
    sec = np.sqrt((y[: (N // SR) * SR].reshape(-1, SR, 2) ** 2).mean((1, 2)))
    db = 20 * np.log10(sec / (pk + 1e-9) * 0.89 + 1e-9)
    print(f"wrote mix_raw.wav {len(y) / SR:.3f} s, raw peak {pk:.3f}")
    print("per-second RMS dBFS:", " ".join(f"{v:.0f}" for v in db))
