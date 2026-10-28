# synth.py : numpy-only instrument kit (no scipy). `python synth.py out.wav` writes a 4 s 120 BPM demo (stereo 16-bit, 44.1 kHz)
import numpy as np, wave, sys

SR = 44100
rng = np.random.RandomState(7)


def tt(n):
    return np.arange(n) / SR


def ex(n, tau):
    return np.exp(-tt(n) / tau)


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def lp(x, fc):  # one-pole low-pass (no scipy)
    a = np.exp(-2 * np.pi * fc / SR)
    y = np.empty_like(x)
    s = 0.0
    for i in range(len(x)):
        s = (1 - a) * x[i] + a * s
        y[i] = s
    return y


def hp(x, fc):
    return x - lp(x, fc)


def kick(g=1.0):
    n = int(0.4 * SR)
    t = tt(n)
    ph = 2 * np.pi * np.cumsum(48 + 130 * np.exp(-t * 30)) / SR
    return (
        np.tanh(
            1.6
            * (
                np.sin(ph) * ex(n, 0.16)
                + hp(rng.uniform(-1, 1, n) * ex(n, 0.003), 2500) * 0.4
            )
        )
        * g
    )


def snare(g=1.0):
    n = int(0.25 * SR)
    t = tt(n)
    return (
        hp(rng.uniform(-1, 1, n), 1500) * ex(n, 0.08) * 0.6
        + np.sin(2 * np.pi * 190 * t) * ex(n, 0.05) * 0.5
    ) * g


def hat(op=False):
    n = int((0.2 if op else 0.05) * SR)
    return hp(rng.uniform(-1, 1, n), 7000) * ex(n, 0.07 if op else 0.014) * 0.4


def clap():
    n = int(0.3 * SR)
    x = np.zeros(n)
    for k, d in enumerate([0, 0.011, 0.023]):
        i = int(d * SR)
        m = n - i
        x[i:] += hp(lp(rng.uniform(-1, 1, m), 5200), 900) * ex(
            m, 0.012 if k < 2 else 0.07
        )
    return x * 0.6


def saw(f, n, det=0.0):
    return 2 * ((tt(n) * f * (1 + det)) % 1.0) - 1


def bass(m, dur):
    n = int(dur * SR)
    f = hz(m)
    x = 0.6 * saw(f, n) + 0.6 * np.sin(2 * np.pi * f * tt(n))
    return (
        np.tanh(1.4 * lp(x, 420))
        * np.minimum(1, tt(n) / 0.005)
        * ex(n, dur * 0.7)
        * 0.55
    )


def pad(notes, dur, fc=1400, att=0.25):
    n = int(dur * SR)
    x = sum(saw(hz(m), n, d) for m in notes for d in (-0.006, 0, 0.007))
    x = lp(x, fc) / (3 * len(notes))
    t = tt(n)
    return x * np.minimum(1, t / att) * np.clip((dur - t) / 0.3, 0, 1)


def pluck(m, dur=0.4):
    n = int(dur * SR)
    return (
        lp(saw(hz(m), n) * 0.6 + saw(hz(m) * 2, n, 0.003) * 0.25, 3500)
        * ex(n, 0.16)
        * np.minimum(1, tt(n) / 0.002)
    )


def riser(dur):
    n = int(dur * SR)
    t = tt(n) / dur
    x = rng.uniform(-1, 1, n)
    out = np.zeros(n)
    for i in range(0, n, 2048):
        out[i : i + 2048] = hp(
            lp(x[i : i + 2048], 500 + 6000 * t[i] ** 2), 200 + 1500 * t[i] ** 2
        )
    return out * t**2 * 3


def boom(dur=1.2):
    n = int(dur * SR)
    t = tt(n)
    return (
        np.tanh(
            2
            * np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-t * 8)) / SR)
            * ex(n, 0.5)
        )
        * 0.9
    )


def whoosh(dur=0.5):
    n = int(dur * SR)
    t = tt(n) / dur
    x = rng.uniform(-1, 1, n)
    out = np.zeros(n)
    for i in range(0, n, 512):
        out[i : i + 512] = hp(lp(x[i : i + 512], 400 * 20 ** t[i]), 200 * 10 ** t[i])
    return out * np.sin(np.pi * t) ** 1.5 * 3


def tick(f=4200):
    n = int(0.02 * SR)
    return hp(rng.uniform(-1, 1, n), f * 0.8) * ex(n, 0.0025) * 0.5


def reverb(
    x,
    wet=0.2,
    taps=((0.029, 0.5), (0.043, 0.4), (0.067, 0.3), (0.097, 0.22), (0.131, 0.15)),
):
    y = x.copy()
    for d, g in taps:
        i = int(d * SR)
        y[i:] += wet * g * x[:-i]
        y[2 * i :] += wet * g * g * x[: -2 * i]
    return y


def duck(bus, times, depth_db=6, rel=0.12, dur=0.3):
    g = np.ones(len(bus))
    for t in times:
        i = int(t * SR)
        j = min(len(bus), i + int(dur * SR))
        g[i:j] = np.minimum(
            g[i:j], 1 - (1 - 10 ** (-depth_db / 20)) * np.exp(-tt(j - i) / rel)
        )
    return bus * g


def put(bus, sig, t0, g=1.0):
    i = int(round(t0 * SR))
    j = min(len(bus), i + len(sig))
    if 0 <= i < len(bus):
        bus[i:j] += sig[: j - i] * g


def put_peak(bus, sig, event_t, g=1.0):
    """Place sig so its loudest instant (1 ms moving average of abs) lands on event_t, not its file start."""
    k = max(1, int(SR * 0.001))
    env = np.convolve(np.abs(sig), np.ones(k) / k, "same")
    start = event_t - int(np.argmax(env)) / SR
    if start < 0:
        sig = sig[int(round(-start * SR)) :]
        start = 0.0
    put(bus, sig, start, g)


def build(bpm=120, bars=2):
    B = 60 / bpm
    N = int((bars * 4 * B + 0.5) * SR)
    m = np.zeros(N)
    fx = np.zeros(N)
    ks = []
    for b in range(bars):
        t0 = b * 4 * B
        for k in range(4):
            t = t0 + k * B
            put(m, kick(), t)
            ks.append(t)
            put(m, hat(), t + B / 2, 0.7)
            put(m, bass(45 if b % 2 == 0 else 41, B * 0.45), t + B / 2, 0.8)
        put(m, snare(), t0 + B, 0.6)
        put(m, snare(), t0 + 3 * B, 0.6)
        put(m, pad([57, 60, 64] if b % 2 == 0 else [53, 57, 60], 4 * B), t0, 0.5)
        for s in range(8):
            put(m, pluck([69, 72, 76, 72][s % 4], 0.3), t0 + s * B / 2, 0.25)
    put(fx, riser(B * 2), (bars * 4 - 2) * B - 0.0, 0.6)
    put(fx, whoosh(0.5), B * 2, 0.5)
    put(fx, boom(), 0, 0.5)
    put(fx, tick(), 3 * B, 0.8)
    m = duck(m, ks, 3)
    m = reverb(m, 0.15)
    out = m + fx
    return out


if __name__ == "__main__":
    y = build(120, 2)[: 4 * SR]
    y = y / (np.abs(y).max() + 1e-9) * 0.89
    path = sys.argv[1] if len(sys.argv) > 1 else "synth_demo.wav"
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.repeat(y[:, None], 2, 1) * 32767).astype("<i2").tobytes())
    print("wrote", path, len(y) / SR, "s")
