# voice.py : measure voice files, size voiced sections in beats, duck the music bed under speech (numpy + ffmpeg)
import math
import subprocess

import numpy as np

SR = 44100  # same rate as audio.py and synth.py; audio.master writes the final 48 kHz mix


def dec(path, af=None, ch=1, sr=SR):
    """Decode any audio file to float32 with ffmpeg, optionally through a filter chain af."""
    cmd = (
        ["ffmpeg", "-v", "error", "-i", path]
        + (["-af", af] if af else [])
        + ["-f", "f32le", "-ac", str(ch), "-ar", str(sr), "-"]
    )
    return np.frombuffer(
        subprocess.run(cmd, capture_output=True, check=True).stdout, np.float32
    )


def span(y, sr=SR):
    """Speech start and end in seconds: 10 ms RMS windows within 40 dB of the loudest one."""
    w = sr // 100
    m = len(y) // w
    db = 20 * np.log10(np.sqrt((y[: m * w].reshape(m, w) ** 2).mean(1)) + 1e-9)
    on = np.where(db > db.max() - 40)[0]
    return on[0] * 0.01, (on[-1] + 1) * 0.01


def section_beats(speech_len, bpm, hold=0.5, lead=0.06, tempo=1.04, min_beats=2):
    """Whole, even number of beats a voiced section needs (mixing.md, voice placement)."""
    need = lead + speech_len / tempo + hold
    return max(min_beats, 2 * math.ceil(need / (60 / bpm) / 2))


def duck_mix(bed, voice, sr=SR, depth_db=8):
    """Voice over the bed: bed at about -18 dBFS RMS, ducked depth_db while the voice speaks (fast attack, slow release)."""
    n = max(len(bed), len(voice))
    bed = np.pad(np.asarray(bed, float), (0, n - len(bed)))
    voice = np.pad(np.asarray(voice, float), (0, n - len(voice)))
    voice = voice * 0.89 / (np.abs(voice).max() + 1e-9)  # voice peak 0.89
    w = sr // 100
    m = n // w  # 10 ms windows
    act = (
        np.sqrt((voice[: m * w].reshape(m, w) ** 2).mean(1)) > 10 ** (-38 / 20)
    ).astype(float)  # voice gate -38 dB
    env = np.zeros(m)
    g = 0.0
    for i in range(m):  # fast attack, slow release
        c = 0.01 / (0.04 if act[i] > g else 0.30)
        g += (act[i] - g) * min(1, c * 3)
        env[i] = g
    env = np.repeat(env, w)
    env = np.concatenate([env, np.full(n - len(env), env[-1])])
    bed = (
        bed / (np.sqrt((bed**2).mean()) + 1e-9) * 10 ** (-18 / 20)
    )  # bed about -18 dBFS RMS before ducking
    return (
        bed * 10 ** (-depth_db * env / 20) + voice * 1.26
    )  # music ducks depth_db while voice speaks
