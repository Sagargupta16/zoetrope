# audio.py : numpy-only music + SFX on a BPM grid, 44.1 kHz stereo WAV (no scipy), and the two-pass loudness master
import json, subprocess, wave, numpy as np

SR = 44100


def tone(f, d, a=0.005, r=0.2, kind="sine"):
    t = np.arange(int(SR * d)) / SR
    w = np.sin(2 * np.pi * f * t) if kind == "sine" else 2 * ((f * t) % 1) - 1
    env = np.minimum(1, t / a) * np.exp(-t / r)
    return w * env


def kick():
    t = np.arange(int(SR * 0.35)) / SR
    return np.sin(2 * np.pi * (45 * t + 90 * (1 - np.exp(-t * 30)) / 30)) * np.exp(
        -t * 9
    )


def noise(d, seed=1):
    return np.random.default_rng(seed).standard_normal(int(SR * d))


def whoosh(d=0.5):
    n = noise(d)
    t = np.linspace(0, 1, len(n))
    k = np.maximum(
        3, (80 * (1 - t) + 6).astype(int)
    )  # moving-average length sweeps: low-pass opening
    c = np.cumsum(n)
    out = np.array([(c[i] - c[max(0, i - k[i])]) / k[i] for i in range(len(n))])
    return out * np.sin(np.pi * t) * 1.5


def hit():
    return (
        tone(70, 0.5, 0.002, 0.15)
        + noise(0.5, 3) * np.exp(-np.arange(int(SR * 0.5)) / SR * 30) * 0.3
    )


def tick():
    return noise(0.03, 2) * np.exp(-np.arange(int(SR * 0.03)) / SR * 150)


def place(buf, snd, at, gain=1.0):
    i = int(at * SR)
    n = min(len(snd), len(buf) - i)
    if n > 0:
        buf[i : i + n] += snd[:n] * gain


def music(dur, bpm, cuts=(), voice_spans=()):
    beat = 60 / bpm
    buf = np.zeros(int(SR * dur))
    for i in range(int(dur / beat)):
        at = i * beat
        if i % 4 in (0, 2):
            place(buf, kick(), at, 0.8)
        place(buf, tick(), at + beat / 2, 0.25)  # offbeat hat
        place(
            buf,
            tone([220, 261.63, 196, 246.94][(i // 4) % 4], beat, 0.01, 0.35),
            at,
            0.25,
        )  # simple bass/pad line
    for c in cuts:
        place(buf, whoosh(0.4), max(0, c - 0.3), 0.5)
        place(buf, hit(), c, 0.5)
    duck = np.ones(len(buf))
    for a, b in voice_spans:
        duck[int(a * SR) : int(b * SR)] = 10 ** (
            -8 / 20
        )  # duck music about 8 dB under voice
    return buf * duck


def write_wav(path, mono, voice=None):
    mix = mono.copy()
    if voice is not None:
        mix[: len(voice)] += voice[: len(mix)]
    mix = mix / max(1e-9, np.abs(mix).max()) * 0.85
    pcm = (np.stack([mix, mix], 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


LIMIT = "alimiter=limit=0.75:attack=4:release=60:level=false"  # peak-limit first, as in mixing.md


def master(src, dst, ff="ffmpeg", I=-14, TP=-3.0, LRA=11):
    """Two-pass loudnorm to I LUFS, true peak TP (mixing.md): limit, measure, then apply with linear=true. Writes 48 kHz.
    TP -3.0 because the AAC encode adds 1 to 1.5 dB of true peak (measured 2026-10-28: -1.5 in mix.wav became -0.4 in the mp4)."""
    af = f"{LIMIT},loudnorm=I={I}:TP={TP}:LRA={LRA}"
    err = subprocess.run(
        [
            ff,
            "-hide_banner",
            "-nostdin",
            "-i",
            src,
            "-af",
            af + ":print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stderr
    m = json.loads(err[err.rfind("{") : err.rfind("}") + 1])
    af += (
        f":measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}"
        f":measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true"
    )
    subprocess.run(
        [
            ff,
            "-y",
            "-v",
            "error",
            "-nostdin",
            "-i",
            src,
            "-af",
            af,
            "-ar",
            "48000",
            dst,
        ],
        check=True,
        capture_output=True,
    )
    return m
