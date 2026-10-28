# media.py : short synthetic files for the file-level fixtures, made at run time: frames piped into ffmpeg (tagged
# BT.709 through contract.COLOR_VF unless a case plants an untagged encode), float32 WAVs (Z18: never int16 through a
# scale that clips) and the muxes. Everything is written into the case's temp folder.
import struct
import subprocess

import contract as C
import numpy as np


def run(argv, data=None):
    """ffmpeg with argv; raises with the tail of its stderr when it fails."""
    r = subprocess.run(argv, input=data, capture_output=True, check=False)
    if r.returncode:
        raise RuntimeError(
            f"ffmpeg failed ({r.returncode}): {r.stderr.decode(errors='replace')[-400:]}"
        )
    return r


def encode(
    ff, path, frames, fps=30, tagged=True, pix="yuv420p", crf=18, preset="veryfast"
):
    """uint8 (n, h, w, 3) frames into an H.264 file: tagged BT.709 limited (what run_all writes) or, tagged=False,
    a plain encode with no colour tags in pix (yuv420p, yuv444p ...)."""
    _n, h, w = frames.shape[:3]
    colour = ["-vf", C.COLOR_VF, *C.COLOR_FLAGS] if tagged else ["-pix_fmt", pix]
    argv = [ff, "-y", "-v", "error", "-f", "rawvideo", "-pixel_format", "rgb24"]
    argv += ["-video_size", f"{w}x{h}", "-framerate", str(fps), "-i", "-", "-an"]
    argv += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), *colour, str(path)]
    run(argv, np.ascontiguousarray(frames, np.uint8).tobytes())
    return path


def wav(path, x, sr=48000):
    """float32 WAV (IEEE float, format 3) of x, (n,) mono or (n, ch)."""
    a = np.asarray(x, np.float32)
    a = a[:, None] if a.ndim == 1 else a
    ch, data = a.shape[1], a.astype("<f4").tobytes()
    fmt = struct.pack("<HHIIHH", 3, ch, sr, sr * ch * 4, ch * 4, 32)
    fact = struct.pack("<I", len(a))
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(fmt)) + fmt
    body += (
        b"fact"
        + struct.pack("<I", 4)
        + fact
        + b"data"
        + struct.pack("<I", len(data))
        + data
    )
    path.write_bytes(b"RIFF" + struct.pack("<I", len(body)) + body)
    return path


def mux(ff, video, audio, out, shortest=True):
    """contract.mux_cmd (the mux run_all runs); shortest=False keeps a longer audio stream whole."""
    argv = C.mux_cmd(ff, str(video), str(audio), str(out))
    if not shortest:
        argv.remove("-shortest")
    run(argv)
    return out


def tone(f, dur, amp, sr=48000, fade=0.05, phase=0.0):
    """A stereo sine of peak amp with raised-cosine fades (a sine that starts at full level rings at its first
    sample in any band-limited reading, lane A's probe)."""
    t = np.arange(round(dur * sr)) / sr
    x = amp * np.sin(2 * np.pi * f * t + phase)
    if fade:
        k = np.minimum(1, np.minimum(t, t[-1] - t) / fade)
        x *= 0.5 - 0.5 * np.cos(np.pi * k)
    return np.stack([x, x], 1)


def card(n, h, w, base=110):
    """n frames of a still card: a horizontal ramp with two bars, mean about base, std well over 12."""
    x = np.linspace(-60, 60, w)[None, :] + np.zeros((h, 1))
    x[h // 4 : h // 4 + h // 10] = 90
    x[h * 2 // 3 : h * 2 // 3 + h // 10] = -80
    im = np.clip(base + x, 0, 255).astype(np.uint8)
    return np.repeat(np.repeat(im[None, :, :, None], 3, 3), n, 0)
