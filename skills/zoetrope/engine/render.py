# render.py : draw every frame in a pool of processes into a shared-memory ring and pipe it, in order, into one ffmpeg
# H.264 encode (video.mp4), writing each frame's digest and grey thumb on the way (frames.hash, thumbs.npy). PNG
# frames only on request. scenes is imported inside the functions: each worker must set the frame size first.
import os
import shutil
import subprocess
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from contextlib import suppress
from multiprocessing import get_context, shared_memory
from pathlib import Path

import contract as C
import numpy as np
from PIL import Image

import engine as E

CRF = 18  # 20 for grain-heavy styles (formats.md)
FRAMES = "frames"  # PNG folder of render_parallel and keep_frames: f00000.png, f00001.png, ...
SLICE = (
    1 << 18
)  # stdin is written in 256 KiB slices, so a write Windows refuses costs one slice's retry
WRITE_TRIES = 40  # retries of one refused slice while ffmpeg is running (sleeps grow to 2 s, about 41 s in all)
POOL_TRIES = 6  # draws of one frame whose result the system refused (WinError 1450)
SPAWN = get_context(
    "spawn"
)  # fresh workers everywhere: a forked one keeps ffmpeg's stdin open and hangs its EOF


def frame_count(scenes):
    return C.frame_of(scenes.DURATION, E.FPS)


def default_procs():
    return max(1, min(8, (os.cpu_count() or 2) // 4))


def png_path(i, folder=FRAMES):
    return Path(folder, f"f{i:05d}.png")


def checked(img, i):
    """img as RGB once it is the build's size: one frame of the wrong size would shear every frame after it."""
    if img.size != (E.W, E.H):
        raise ValueError(
            f"frame {i} (t {i / E.FPS:.3f} s) is {img.size[0]}x{img.size[1]}; the build is {E.W}x{E.H}"
        )
    return img if img.mode == "RGB" else img.convert("RGB")


def render_frames(outdir=FRAMES):
    """Every frame as PNG in one process (slow; for a machine where the pool cannot start)."""
    import scenes

    shutil.rmtree(outdir, ignore_errors=True)
    Path(outdir).mkdir()
    n = frame_count(scenes)
    for i in range(n):
        checked(scenes.draw(i / E.FPS), i).save(png_path(i, outdir), compress_level=1)
    return n


_w = {}  # this worker's scenes module, job settings and frame ring, set once by _start


def _start(size, keep=None, read=frozenset(), ring=None):
    """Pool initializer: set the frame size, then import scenes (every worker starts fresh), and open the ring."""
    E.W, E.H, E.FPS, E.SS = size
    import scenes

    _w.update(scenes=scenes, keep=keep, read=read)
    if ring:
        _w["ring"] = shared_memory.SharedMemory(name=ring, track=False)


def _draw(i):
    return checked(_w["scenes"].draw(i / E.FPS), i)


def _png_job(job):
    i, outdir, skip = job
    path = png_path(i, outdir)
    if skip and path.exists():
        return 0
    # level 1: much faster to write than the default
    _draw(i).save(path, compress_level=1)
    return 1


def render_parallel(outdir=FRAMES, procs=None, skip_existing=False, frames=None):
    """PNG frames across processes; draw(t) is pure, so order does not matter. frames: an index range to re-render
    only part of the film (a fixed passage). Call it from under `if __name__ == "__main__":`."""
    import scenes

    idx = list(frames) if frames is not None else list(range(frame_count(scenes)))
    if frames is None and not skip_existing:
        shutil.rmtree(outdir, ignore_errors=True)
    Path(outdir).mkdir(parents=True, exist_ok=True)
    procs = procs or default_procs()
    size = (E.W, E.H, E.FPS, E.SS)
    with SPAWN.Pool(procs, initializer=_start, initargs=(size,)) as pool:
        return sum(
            pool.imap_unordered(
                _png_job, ((i, outdir, skip_existing) for i in idx), chunksize=8
            )
        )


def _frame(job):
    """Frame i drawn (or read back from its PNG) into ring slot `slot`. Returns (digest, thumb), both made here, so
    only those small values cross the pipe: a 6 MB result message is what Windows refused under parallel builds."""
    i, slot = job
    keep = _w["keep"]
    if keep and i in _w["read"]:
        with Image.open(png_path(i, keep)) as im:
            img = checked(im.convert("RGB"), i)
    else:
        img = _draw(i)
        if keep:
            img.save(png_path(i, keep), compress_level=1)
    raw = img.tobytes()
    _w["ring"].buf[slot * len(raw) : (slot + 1) * len(raw)] = raw
    return C.frame_digest(img, raw), C.thumb(img)


def _digest(i):
    return C.frame_digest(_draw(i))


def encode_cmd(ff, out, w, h, fps, crf=CRF, maxrate=None, bufsize=None):
    """ffmpeg argv: raw RGB frames on stdin to H.264 at out, BT.709 limited range converted and tagged (Z16), and
    a VBV cap in kb/s when maxrate is set (always with a bufsize: x264 ignores maxrate without one)."""
    cap = []
    if maxrate:
        cap = [
            "-maxrate",
            f"{maxrate:.0f}k",
            "-bufsize",
            f"{bufsize or 2 * maxrate:.0f}k",
        ]
    return [
        ff,
        "-y",
        "-v",
        "error",
        "-f",
        "rawvideo",
        "-pixel_format",
        "rgb24",
        "-video_size",
        f"{w}x{h}",
        "-framerate",
        str(fps),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        str(crf),
        "-vf",
        C.COLOR_VF,
        *C.COLOR_FLAGS,
        "-pix_fmt",
        "yuv420p",
        *cap,
        str(out),
    ]


def hold_samples(a, b, fps):
    """The frames a static span [a, b) is checked at: both ends, the middle, and about one a second (at most 6 more).
    A change shorter than the gaps between them is not seen: declare only frames that truly hold."""
    inner = list(range(a + round(fps), b - 1, round(fps)))
    if len(inner) > 6:
        inner = [inner[round(k * (len(inner) - 1) / 5)] for k in range(6)]
    return sorted({a, b - 1, (a + b) // 2, *inner})


def static_reuse(scenes, n, fps, ex):
    """{frame: frame whose bytes it reuses} for scenes.STATIC = [(t0, t1), ...] (seconds, end exclusive like
    SCHEDULE): a declared hold is drawn once, but only when every sampled frame of it hashes the same (both ends,
    the middle and about one a second; a flash between samples is not seen)."""
    reuse = {}
    for t0, t1 in getattr(scenes, "STATIC", None) or []:
        a, b = max(0, C.frame_of(t0, fps)), min(n, C.frame_of(t1, fps))
        if b - a < 2:
            continue
        at = hold_samples(a, b, fps)
        digs = list(ex.map(_digest, at))
        if moved := [i for i, d in zip(at, digs) if d != digs[0]]:
            print(
                f"warning: STATIC ({t0:g}, {t1:g}) s moves (frame {moved[0]} differs from frame {a}): every frame of it is drawn"
            )
            continue
        reuse.update(dict.fromkeys(range(a + 1, b), a))
    if reuse:
        print(f"STATIC: {len(reuse)} of {n} frames reuse a held frame")
    return reuse


def _result(ex, job, fut):
    """(digest, thumb) of one frame. When several builds share the machine, Windows can refuse a pipe message
    (WinError 1450, insufficient system resources) or a worker can run out of memory for a moment; draw is pure, so
    the frame is drawn again after a pause, up to POOL_TRIES times. Any other error is the frame's own."""
    attempt = 1
    while True:
        try:
            return fut.result()
        except (OSError, MemoryError) as e:
            busy = isinstance(e, MemoryError) or getattr(e, "winerror", None) == 1450
            if not busy or attempt == POOL_TRIES:
                raise
            print(f"note: frame {job[0]} drawn again after {type(e).__name__}: {e}")
        time.sleep(0.5 * attempt)
        attempt += 1
        fut = ex.submit(_frame, job)


def _in_order(ex, n, slots, reuse, ring, fb):
    """Frames 0 to n - 1 in order as (bytes, digest, thumb), `slots` in flight: the pool draws each into its own ring
    slot (submission k uses slot k % slots, free again once the parent has copied it out); a frame inside a static
    span is its span's first frame again. An explicit queue of futures, so it runs on Python 3.13 too."""
    todo = iter([i for i in range(n) if i not in reuse])
    pending, k = deque(), 0

    def submit():
        nonlocal k
        if (i := next(todo, None)) is not None:
            job = (i, k % slots)
            pending.append((job, ex.submit(_frame, job)))
            k += 1

    for _ in range(slots):
        submit()
    last_use = {}
    for i, a in reuse.items():
        last_use[a] = max(last_use.get(a, a), i)
    held = {}
    for i in range(n):
        if i in reuse:
            r = held[reuse[i]]
        else:
            job, fut = pending.popleft()
            dig, th = _result(ex, job, fut)
            s = job[1]
            r = (bytes(ring.buf[s * fb : (s + 1) * fb]), dig, th)
            submit()  # the slot is copied out, so the next frame may take it
        if i in last_use:
            held[i] = r
        if i in reuse and last_use[reuse[i]] == i:
            del held[reuse[i]]
        yield r


def _failed(proc, log, k, n):
    """The error for an encode that stopped: ffmpeg's own exit code and log (its first lines hold the cause). It is
    given 2 s to exit by itself, so the code is never our own kill unless it hung."""
    with suppress(OSError):  # stdin of a dead ffmpeg cannot flush; close it quietly
        proc.stdin.close()
    try:
        rc, how = proc.wait(timeout=2), "exit"
    except subprocess.TimeoutExpired:
        proc.kill()
        rc, how = proc.wait(), "killed after 2 s, exit"
    rc = rc - 2**32 if rc >= 2**31 else rc  # Windows reports -22 as 4294967274
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    said = lines if len(lines) <= 4 else [*lines[:3], "...", lines[-1]]
    return RuntimeError(
        f"ffmpeg stopped after {k} of {n} frames ({how} {rc}): {' | '.join(said) or f'nothing in {log}'}"
    )


def _send(proc, data, log, k, n):
    """Write one frame to ffmpeg in SLICE pieces. A slice refused while ffmpeg runs (Windows: Invalid argument,
    WinError 1450, when the system is short of resources) is retried with growing sleeps; only a dead ffmpeg is
    blamed, with its own exit code and log."""
    mv, off, tries = memoryview(data), 0, 0
    while off < len(mv):
        try:
            off += proc.stdin.raw.write(mv[off : off + SLICE]) or 0
            tries = 0
            continue
        except OSError as e:
            err = e
        if proc.poll() is not None:
            raise _failed(proc, log, k, n) from err
        tries += 1
        if tries > WRITE_TRIES:
            raise RuntimeError(
                f"write to ffmpeg failed while it was running (frame {k} of {n}, {WRITE_TRIES} retries): {err!r}"
            ) from err
        time.sleep(min(0.05 * tries, 2.0))


def render_to_ffmpeg(
    out=C.VIDEO,
    procs=None,
    crf=CRF,
    maxrate=None,
    bufsize=None,
    keep_frames=False,
    redraw=None,
    ff="ffmpeg",
):
    """Draw every frame across processes and pipe it raw, in order, into one H.264 encode at out: the silent
    picture, which run_all muxes with mix.wav. The same frames give frames.hash and thumbs.npy. maxrate and
    bufsize (kb/s) cap the bitrate when a size budget is set. keep_frames also keeps every frame as PNG in
    frames/; with redraw=[(t0, t1), ...] it draws only those passages again and reads the rest back from frames/.
    scenes.STATIC holds are drawn once (not with keep_frames). Any failure, including errors ffmpeg logs on a clean
    exit, kills ffmpeg, deletes the partial file and raises with ffmpeg's own log lines. Returns the frame count.
    Call it from under `if __name__ == "__main__":`."""
    import scenes

    n, w, h, fps = frame_count(scenes), E.W, E.H, E.FPS
    procs = procs or default_procs()
    keep, read = (FRAMES if keep_frames else None), frozenset()
    if keep_frames and redraw:
        fresh = {
            i
            for t0, t1 in redraw
            for i in range(max(0, C.frame_of(t0, fps)), min(n, C.frame_of(t1, fps)))
        }
        read = frozenset(i for i in range(n) if i not in fresh)
        missing = [i for i in sorted(read) if not png_path(i).exists()]
        if missing:
            raise FileNotFoundError(
                f"{FRAMES}/ lacks {len(missing)} of the frames to reuse (first {png_path(missing[0])}): "
                "run once with keep_frames and no redraw"
            )
    elif keep_frames:
        shutil.rmtree(FRAMES, ignore_errors=True)
        Path(FRAMES).mkdir()
    if keep_frames and getattr(scenes, "STATIC", None):
        print("note: STATIC is not used with keep_frames: every frame is drawn or read")
    slots, fb = 2 * procs, w * h * 3
    log = Path(f"{out}.log")
    digests, thumbs, ok = [], [], False
    ring = shared_memory.SharedMemory(create=True, size=slots * fb)
    try:
        with ProcessPoolExecutor(
            procs,
            mp_context=SPAWN,
            initializer=_start,
            initargs=((w, h, fps, E.SS), keep, read, ring.name),
        ) as ex:
            reuse = {} if keep_frames else static_reuse(scenes, n, fps, ex)
            with log.open("wb") as err:
                proc = subprocess.Popen(
                    encode_cmd(ff, out, w, h, fps, crf, maxrate, bufsize),
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=err,  # a file, not a PIPE: an unread stderr PIPE can hang ffmpeg on Windows
                )
                try:
                    for raw, dig, th in _in_order(ex, n, slots, reuse, ring, fb):
                        _send(proc, raw, log, len(digests), n)
                        digests.append(dig)
                        thumbs.append(th)
                    try:
                        proc.stdin.close()
                    except OSError as e:
                        raise _failed(proc, log, n, n) from e
                    # no timeout: x264 flushes its lookahead after the last frame
                    if proc.wait():
                        raise _failed(proc, log, n, n)
                    # -v error prints nothing on a good encode: anything here (a short buffer, a bad packet) fails it
                    if said := log.read_text(
                        encoding="utf-8", errors="replace"
                    ).strip():
                        raise RuntimeError(
                            f"ffmpeg exited 0 but logged errors: {said[-600:]}"
                        )
                    ok = True
                finally:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait()
                    if not ok:
                        Path(out).unlink(missing_ok=True)
                        ex.shutdown(cancel_futures=True)
    finally:
        ring.close()
        ring.unlink()
    log.unlink()
    C.write_frame_manifest(digests, w, h, fps, ss=E.SS)
    np.save(C.THUMBS, np.stack(thumbs))
    return n


def stale(scenes, frames):
    """The frames among `frames` whose draw(t) no longer matches frames.hash (all of them when there is no
    frames.hash, or it is for another size, fps, SS or length): video.mp4 is from another state of scenes.py."""
    m = C.read_frame_manifest()
    same = m and (m["w"], m["h"], m["fps"], m.get("ss", 1), m["n"]) == (
        E.W,
        E.H,
        E.FPS,
        E.SS,
        frame_count(scenes),
    )
    if not same:
        return list(frames)
    return [
        i
        for i in frames
        if C.frame_digest(checked(scenes.draw(i / E.FPS), i)) != m["hash"][i]
    ]
