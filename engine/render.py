# render.py : write every frame as PNG (numbered from 0) into frames/, in one process or several
# scenes is imported inside the functions, never at the top: a worker must set the frame size first.
import os, shutil
from multiprocessing import Pool
import engine as E


def render_frames(outdir="frames"):
    import scenes

    shutil.rmtree(outdir, ignore_errors=True)
    os.makedirs(outdir)
    n = int(round(scenes.DURATION * E.FPS))
    for i in range(n):
        scenes.draw(i / E.FPS).save(f"{outdir}/f{i:05d}.png", compress_level=1)
    return n


_worker = None


def _init(size):
    """Each worker sets the frame size before importing scenes (Windows starts workers fresh)."""
    global _worker
    E.W, E.H, E.FPS, E.SS = size
    import scenes

    _worker = scenes


def _job(job):
    i, outdir, skip = job
    path = f"{outdir}/f{i:05d}.png"
    if skip and os.path.exists(path):
        return 0
    _worker.draw(i / E.FPS).save(
        path, compress_level=1
    )  # level 1: much faster to write than the default
    return 1


def render_parallel(outdir="frames", procs=None, skip_existing=False, frames=None):
    """Render frames across processes; draw(t) is pure, so order does not matter. frames: an index range to
    re-render only part of the film (a fixed passage). Call it from under `if __name__ == "__main__":`."""
    import scenes

    n = int(round(scenes.DURATION * E.FPS))
    idx = list(frames) if frames is not None else list(range(n))
    if frames is None and not skip_existing:
        shutil.rmtree(outdir, ignore_errors=True)
    os.makedirs(outdir, exist_ok=True)
    procs = procs or max(1, min(8, (os.cpu_count() or 2) // 4))
    with Pool(procs, initializer=_init, initargs=((E.W, E.H, E.FPS, E.SS),)) as pool:
        done = sum(
            pool.imap_unordered(
                _job, ((i, outdir, skip_existing) for i in idx), chunksize=8
            )
        )
    return done
