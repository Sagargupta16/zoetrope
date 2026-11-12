# grain_test.py : file size per grain setting at one CRF, encoded exactly like run_all's picture encode (raw frames
# piped through render.encode_cmd, BT.709 chain), and how much of the grain the encode keeps. Run it before
# rendering any grainy style, from a working folder that holds this kit's scenes.py next to the engine.
#   uv run --no-project --with-requirements requirements.txt python grain_test.py [crf] [seconds]
# No seconds: the 4 s slice (0-2 s and 33-35 s). A slice that short is about one x264 GOP, so it overstates grain
# that is coded once and then reused (static); pass 60 for the real per-minute figure.
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

# name: (kit GRAIN_STD, GRAIN_CELL, GRAIN_SMOOTH, engine grain hz after the weave: None = off, "fps/2" = its default)
KIT = "kit as shipped"  # the kit's own grain: 2 px cells, new every frame, added before the weave
VARIANTS = {
    KIT: (1.6, 2, False, None),
    "no grain": (0.0, 2, False, None),
    "every frame": (
        0.0,
        2,
        False,
        24,
    ),  # from here on grain.grain at STD, 1 px, after the weave
    "fps/2 stepped": (0.0, 2, False, "fps/2"),
    "static": (0.0, 2, False, 0),
}
STD, FPS = 1.6, 24
ROOT = Path("gtest")
_w = {}


def _init(params):
    import engine as E

    E.W, E.H, E.FPS, E.SS = 1920, 1080, FPS, 1
    import grain
    import scenes

    std, cell, smooth, hz = params
    scenes.GRAIN_STD, scenes.GRAIN_CELL, scenes.GRAIN_SMOOTH = std, cell, smooth
    if hz is not None:
        kit_film = scenes.film

        def film(P, t):  # the kit's flicker and weave, then the engine grain on top
            return grain.grain(kit_film(P, t), t, STD, None if hz == "fps/2" else hz)

        scenes.film = film
    _w["scenes"] = scenes


def _job(t):
    return _w["scenes"].draw(t).tobytes()


def grey(mp4):
    """Every 4th decoded frame of a sky band (x 580..1340, y 150..400) in grey, rounded as a player would."""
    import contract as C

    vf = (
        r"select=not(mod(n\,4)),crop=760:250:580:150,"
        f"{C.DECODE_709}:flags=accurate_rnd+full_chroma_int,format=gray"
    )
    args = ["-vf", vf, "-fps_mode", "passthrough", "-f", "rawvideo", "-"]
    cmd = ["ffmpeg", "-v", "error", "-i", str(mp4), *args]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, 250, 760)


if __name__ == "__main__":
    import render

    crf = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 0
    times = (
        [i / FPS for i in range(round(secs * FPS))]
        if secs
        else [i / FPS for i in range(48)] + [33 + i / FPS for i in range(48)]
    )
    dur = len(times) / FPS
    shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir()
    out = {}
    for name, params in VARIANTS.items():
        mp4 = ROOT / f"{name.replace(' ', '_').replace('/', '-')}_crf{crf}.mp4"
        t0 = time.perf_counter()
        cmd = render.encode_cmd("ffmpeg", mp4, 1920, 1080, FPS, crf)
        with (
            ProcessPoolExecutor(6, initializer=_init, initargs=(params,)) as ex,
            subprocess.Popen(cmd, stdin=subprocess.PIPE) as p,
        ):
            for raw in ex.map(_job, times, buffersize=12):
                p.stdin.write(raw)
            p.stdin.close()
        if p.returncode:
            sys.exit(f"ffmpeg failed on {name} (exit {p.returncode})")
        out[name] = (mp4, time.perf_counter() - t0)
    base = grey(out["no grain"][0])
    for name, (mp4, took) in out.items():
        mb = mp4.stat().st_size / 1e6
        left = float(
            np.mean(
                [
                    np.std(v - b, dtype=np.float64)
                    for v, b in zip(grey(mp4).astype(np.int16), base)
                ]
            )
        )
        drawn = f"{VARIANTS[name][0] or STD:g}" if name != "no grain" else "0"
        print(
            f"{name:15s} crf {crf}, {dur:g} s: {mb:.2f} MB -> {mb * 60 / dur:.1f} MB per minute "
            f"({mb * 8 / dur:.2f} Mb/s); grain left {left:.2f} of {drawn} grey levels [{took:.0f} s]"
        )
