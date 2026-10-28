# grain_test.py : file-size test of grain settings on a 4 s slice (0-2 s and 33-35 s), encoded like rung a.
from __future__ import annotations

import shutil
import subprocess
import time
from multiprocessing import Pool
from pathlib import Path

VARIANTS = {  # name: (GRAIN_STD, GRAIN_CELL, GRAIN_SMOOTH)
    "E_1p2": (1.2, 2, False),
}
TIMES = [i / 24 for i in range(0, 48)] + [33 + i / 24 for i in range(0, 48)]
ROOT = Path("gtest")


def _init(params):
    global scenes, E
    import engine as E

    E.W, E.H, E.FPS, E.SS = 1920, 1080, 24, 1
    import scenes

    scenes.GRAIN_STD, scenes.GRAIN_CELL, scenes.GRAIN_SMOOTH = params


def _job(args):
    k, t, out = args
    scenes.draw(t).save(Path(out) / f"f{k:05d}.png")
    return k


if __name__ == "__main__":
    shutil.rmtree(ROOT, ignore_errors=True)
    for name, params in VARIANTS.items():
        d = ROOT / name
        d.mkdir(parents=True)
        t0 = time.perf_counter()
        with Pool(6, initializer=_init, initargs=(params,)) as pool:
            list(
                pool.imap_unordered(
                    _job, [(k, t, str(d)) for k, t in enumerate(TIMES)], chunksize=8
                )
            )
        sizes = []
        for crf in (18, 20):
            mp4 = ROOT / f"{name}_crf{crf}.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-y",
                    "-framerate",
                    "24",
                    "-i",
                    str(d / "f%05d.png"),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "medium",
                    "-crf",
                    str(crf),
                    "-pix_fmt",
                    "yuv420p",
                    "-r",
                    "24",
                    str(mp4),
                ],
                check=True,
            )
            sizes.append(mp4.stat().st_size / 1e6)
        print(
            f"{name:8s} std={params[0]} cell={params[1]} smooth={params[2]}: 4 s = {sizes[0]:.2f} MB (crf18) "
            f"{sizes[1]:.2f} MB (crf20) -> 60 s about {sizes[0] * 15:.0f} / {sizes[1] * 15:.0f} MB "
            f"({sizes[0] * 2:.1f} / {sizes[1] * 2:.1f} Mbps) [{time.perf_counter() - t0:.0f} s]"
        )
