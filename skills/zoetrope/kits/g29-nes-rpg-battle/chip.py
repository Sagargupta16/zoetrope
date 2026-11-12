# chip.py : small numpy chip synth in the style of the 2A03: two pulse channels (duty 12.5/25/50/75),
# a 32-step triangle, LFSR noise. Register state comes from song.ticks() (60 Hz driver), so the audio
# plays exactly the notes the tracker shows. Usage: python chip.py mix_raw.wav
import sys
import wave

import numpy as np

import song

SR = 44100
SPT = SR // song.TICK_HZ  # 735 samples per driver tick


def per_sample(a):
    return np.repeat(np.asarray(a, float), SPT)


def blep(t, dt):
    out = np.zeros_like(t)
    m1 = t < dt
    x = t[m1] / dt[m1]
    out[m1] = x + x - x * x - 1
    m2 = t > 1 - dt
    x = (t[m2] - 1) / dt[m2]
    out[m2] = x * x + x + x + 1
    return out


def pulse(f, vol, duty):
    """Band-limited (polyBLEP) pulse, 0..vol like the 4-bit DAC level of the channel."""
    f, vol, duty = per_sample(f), per_sample(vol), per_sample(duty)
    dt = np.maximum(f / SR, 1e-9)
    ph = np.cumsum(dt) % 1.0
    y = np.where(ph < duty, 1.0, -1.0) + blep(ph, dt) - blep((ph - duty) % 1.0, dt)
    return vol * (y + 1) / 2


TRI_SEQ = np.array(list(range(15, -1, -1)) + list(range(16)), float)  # 32 steps


def triangle(f, on):
    """32-step triangle; when the channel is silenced the sequencer halts and holds its level (as on hardware)."""
    f, on = per_sample(f), per_sample(on) > 0
    ph = np.cumsum(np.where(on, f / SR, 0.0))
    return TRI_SEQ[(np.floor(ph * 32) % 32).astype(int)]


def lfsr(short=False, n=32767):
    reg, bits = 1, np.zeros(n, np.uint8)
    tap = 6 if short else 1
    for i in range(n):
        bits[i] = reg & 1
        fb = (reg & 1) ^ ((reg >> tap) & 1)
        reg = (reg >> 1) | (fb << 14)
    return bits


def noise(pidx, vol):
    seq = lfsr()
    rate = per_sample(song.CPU / np.array(song.NOISE_PERIODS, float)[np.asarray(pidx)])
    pos = np.floor(np.cumsum(rate / SR)).astype(np.int64) % len(seq)
    return per_sample(vol) * (1 - seq[pos])


def movavg(x, n):
    c = np.cumsum(np.concatenate([[0.0], x]))
    h = n // 2
    i = np.arange(len(x))
    lo, hi = np.clip(i - h, 0, len(x)), np.clip(i + h + 1, 0, len(x))
    return (c[hi] - c[lo]) / (hi - lo)


def render():
    T = song.ticks()
    p1 = pulse(*T["p1"])
    p2 = pulse(*T["p2"])
    tr = triangle(*T["tri"])
    nz = noise(*T["noi"])
    tnd = lambda t, n: np.where(
        (t + n) > 0, 159.79 / (1 / (t / 8227 + n / 12241 + 1e-12) + 100), 0.0
    )  # noqa: E731
    pls = lambda p: np.where(p > 0, 95.88 / (8128 / np.maximum(p, 1e-9) + 100), 0.0)  # noqa: E731
    t_n = tnd(tr, nz * 1.35)  # noise lifted a little so the drums carry the hits
    L = pls(p1 * 1.08 + p2 * 0.92) + t_n
    R = pls(p1 * 0.92 + p2 * 1.08) + t_n
    out = []
    for x in (L, R):
        x = x - movavg(
            movavg(x, 2205), 2205
        )  # DC and sub rumble out (about 10 Hz high-pass)
        x = np.convolve(
            x, [0.25, 0.5, 0.25], "same"
        )  # gentle top roll-off, like the console output stage
        out.append(x)
    return np.stack(out, 1)


def write(path, st, peak=0.85):
    raw_peak = max(1e-9, np.abs(st).max())
    print(
        f"raw synth peak {20 * np.log10(raw_peak):.1f} dBFS, gain lift to {20 * np.log10(peak):.1f} dBFS peak: "
        f"+{20 * np.log10(peak / raw_peak):.1f} dB"
    )
    st = st / raw_peak * peak
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((st * 32767).astype("<i2").tobytes())


if __name__ == "__main__":
    st = render()
    path = sys.argv[1] if len(sys.argv) > 1 else "mix_raw.wav"
    write(path, st)
    print("wrote", path, f"{len(st) / SR:.3f} s")
