# qa_purity.py : the purity gate (Q1201). draw(t) must give the same pixels for the same t, whatever was drawn before
# it and in whichever process. At most about 2 + 2n frames (the ends, both sides of the cuts, then window and scene
# midpoints, CUES and KEY_TIMES, then frames spread over the rest) are drawn three ways: in order in this process
# while a fresh `python -I` process (a new str hash seed, no PYTHON* variables) draws them reversed, then through a
# spawn Pool with imap_unordered like render.render_parallel. Digests (contract.frame_digest) are compared exactly:
# Pillow and numpy repeat bit for bit on one machine and build. On a mismatch it prints the differing pixels and the
# poisoner diagnosis: the failing frame drawn cold, twice, under two hash seeds and behind its nearest samples.
# CLI: `python qa.py purity [--scenes .] [--n 16] [--t T] [--grid S]`. run_all.py proof calls run(scenes_dir, fps, size).
import json
import os
import subprocess
import sys
import tempfile
import time
import types
import zlib
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import TimeoutError as PoolTimeout
from multiprocessing import get_context
from pathlib import Path

import contract as C
import numpy as np
import qa_lint as L
from PIL import Image

# A fresh process: put the working folder on sys.path (-I drops the script folder), then run worker(job).
WORKER = "import sys; sys.path.insert(0, sys.argv[1]); import qa_purity; qa_purity.worker(sys.argv[2])"
# seconds for one fresh process, one pool frame or the in-order pass: a hang is reported, inside the builder's
# 4-minute rule
TIMEOUT = 240
NEAREST = 8  # the diagnosis draws the failing frame behind this many of its nearest samples (c4: 256 took 65.6 s)
MON = 4  # the sys.monitoring tool id pass 1 uses to see whether a Q1202 site ran (0 to 2 and 5 are the usual tools)
FIX = (
    "make draw(t) depend on t alone: no counter, list or cache written inside draw (key a cache by everything it "
    "depends on), sort a set of strings before drawing from it, seed randomness per frame (engine.rng); qa.py lint "
    "names the line"
)


def _spread(xs, k):
    """k evenly spaced items of xs, first and last kept (proof.spread)."""
    if k <= 0:
        return []
    return (
        xs
        if len(xs) <= k
        else [xs[round(i * (len(xs) - 1) / max(1, k - 1))] for i in range(k)]
    )


def sample(scn, fps, n=16, extra=(), grid=None):
    """[(frame, why)] to check, sorted: at most 2 + 2n frames, plus the asked ones.
    - The first and the last frame.
    - Cut frames, at most n: both sides of a cut (the frame before it and its first frame) for every cut, spread
      over them when there are more than n / 2 (SCHEDULE starts and ends, scenes.CUTS, the edges of scenes.WINDOWS),
      then the frame after the cut for a few cuts spread over the piece while the budget lasts.
    - Interior frames, n (our extension: no source samples them, but state leaks show at crossfades and hits): the
      midpoint of every window and scene, then CUES and KEY_TIMES (each kind keeps at least half the budget when the
      other has more), then frames spread evenly over the rest.
    - Every `extra` second, and with `grid` one frame every grid seconds: a dense check, not capped."""
    dur = float(scn.DURATION)
    last = C.frame_of(dur, fps) - 1
    why = {}

    def put(f, w):
        if 0 <= f <= last and w not in why.setdefault(f, []):
            why[f].append(w)

    put(0, "first frame")
    put(last, "last frame")
    sched = getattr(scn, "SCHEDULE", {})
    names = list(sched)
    starts = {a for a, b in sched.values()}
    ends = {b for a, b in sched.values()}
    # a start on another scene's end is a cut; overlapping scenes (a window) keep their own edges
    edges = [
        (a, f"cut to {nm}" if a in ends else f"{nm} starts")
        for nm, (a, b) in sched.items()
    ]
    edges += [(b, f"{nm} ends") for nm, (a, b) in sched.items() if b not in starts]
    cuts = L.cut_list(scn)
    named = (
        len(cuts) == len(names) - 1
    )  # compile_schedule's CUTS[i] is the cut into scene i + 1
    edges += [
        (c, f"cut to {names[i + 1]}" if named else f"cut at {c:g} s")
        for i, c in enumerate(cuts)
    ]
    wins = L.window_spans(scn)
    for a, b, lab in wins:
        w = f"window {lab}" if lab else "window"
        edges += [(a, f"{w} opens"), (b, f"{w} closes")]
    at = {}
    for c, w in edges:
        if 0 < c < dur and w not in at.setdefault(C.frame_of(c, fps), []):
            at[C.frame_of(c, fps)].append(w)
    pick = _spread(sorted(at), max(1, n // 2))
    for c in pick:
        lab = "; ".join(at[c])
        put(c - 1, f"{lab} -1 frame")
        put(c, lab)
    for c in _spread(pick, n - 2 * len(pick)):
        put(c + 1, f"{'; '.join(at[c])} +1 frame")
    try:
        cues = C.cues(scn)
    except (TypeError, ValueError, KeyError, IndexError):
        cues = []  # an unreadable CUES form: skipped, the cuts still count
    mids = [
        (
            C.frame_of((a + b) / 2, fps),
            f"window {lab} mid (extension)".replace("  ", " "),
        )
        for a, b, lab in wins
    ]
    mids += [
        (C.frame_of((a + b) / 2, fps), f"{nm} mid (spread)")
        for nm, (a, b) in sched.items()
    ]
    hits = [
        (C.frame_of(c["t"], fps), f"cue {c['label'] or c['t']} (extension)")
        for c in cues
    ]
    for k in getattr(scn, "KEY_TIMES", None) or []:
        try:
            hits.append(
                (
                    C.frame_of(float(k[0] if isinstance(k, (tuple, list)) else k), fps),
                    "key time (extension)",
                )
            )
        except (TypeError, ValueError, IndexError):
            continue  # not a time: skipped

    def fresh(group):
        return sorted(
            {f: w for f, w in group if f not in why and 0 <= f <= last}.items()
        )

    m, h = fresh(mids), fresh(hits)
    take_m = min(len(m), max(n - len(h), n // 2))
    chosen = _spread(m, take_m) + _spread(h, min(len(h), n - take_m))
    for f, w in chosen:
        put(f, w)
    room = n - len(chosen)
    if room > 0:  # the rest of the interior budget: even steps over the piece
        step = (last + 1) / (room + 1)
        for i in range(1, room + 1):
            f = round(i * step)
            while f in why and f < last:
                f += 1
            put(f, "even step (spread)")
    for t in extra:
        put(C.frame_of(t, fps), "asked")
    if grid:
        for f in range(0, last + 1, max(1, C.frame_of(grid, fps))):
            put(f, "grid")
    return [(f, "; ".join(why[f])) for f in sorted(why)]


# ---- fresh processes (pass 2 and the diagnosis) ----


def _pixels(mode, size, raw):
    return np.asarray(Image.frombytes(mode, size, raw))


def _unhold(h):
    """The pixels of a frame kept as (mode, size, zlib level 1 bytes)."""
    mode, size, z = h
    return _pixels(mode, size, zlib.decompress(z))


def worker(job_path):
    """Runs in a fresh process: set the frame size, import scenes, draw the frames in the order given and write
    [[frame, digest], ...] to <job>.out. With job["hold"] it keeps each frame compressed, then reads the parent's
    digests on stdin and saves only the frames that differ (<tag>_<frame>.npy)."""
    # a print in scenes.py must not crash a child on a narrow code page
    for s in (sys.stdout, sys.stderr):
        s.reconfigure(errors="backslashreplace")
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    import engine as E

    E.W, E.H, E.FPS, E.SS = job["size"]
    import scenes

    out, held = {"drawn": [], "errors": {}}, {}
    for f in job["frames"]:
        try:
            img = scenes.draw(f / E.FPS)
        except L.USER_ERRORS as e:
            out["errors"][str(f)] = f"{type(e).__name__}: {e}"
            continue
        raw = img.tobytes()
        out["drawn"].append([f, C.frame_digest(img, raw)])
        if job["hold"]:
            held[f] = (img.mode, img.size, zlib.compress(raw, 1))
    if job["hold"]:
        expect = json.loads(sys.stdin.read() or "{}")
        for f, d in out["drawn"]:
            if expect.get(str(f)) not in (None, d):
                np.save(
                    Path(job_path).with_name(f"{job['tag']}_{f}.npy"), _unhold(held[f])
                )
    Path(job_path).with_suffix(".out").write_text(json.dumps(out), encoding="utf-8")


def _start(folder, size, frames, tmp, tag, seed=None, hold=False):
    """Start drawing frames in a new interpreter: `python -I` when seed is None (a new hash seed, PYTHON* ignored),
    else with PYTHONHASHSEED=seed (the diagnosis needs a fixed seed, and -I would ignore it). hold: the child waits
    for the parent's digests on stdin (send with _send) and keeps only the frames that differ."""
    job = Path(tmp, f"{tag}.json")
    job.write_text(
        json.dumps({"size": list(size), "frames": frames, "tag": tag, "hold": hold}),
        encoding="utf-8",
    )
    cmd = [
        sys.executable,
        "-I" if seed is None else "-s",
        "-c",
        WORKER,
        str(folder),
        str(job),
    ]
    env = None if seed is None else {**os.environ, "PYTHONHASHSEED": str(seed)}
    # stderr goes to a file, so a chatty child never blocks on a full pipe
    with job.with_suffix(".err").open("w", encoding="utf-8") as err:
        proc = subprocess.Popen(
            cmd,
            cwd=folder,
            env=env,
            stdin=subprocess.PIPE if hold else subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=err,
        )
    return proc, job


def _send(started, digests):
    """Give a holding child the parent's digests ({frame: digest}); a child that already died is reported by
    _finish."""
    proc, _ = started
    try:
        proc.stdin.write(json.dumps({str(k): v for k, v in digests.items()}).encode())
        proc.stdin.close()
    except OSError:
        pass  # the child is gone: _finish reads its error file


def _finish(started, timeout=TIMEOUT):
    """(result, error) of a process from _start, waiting at most timeout seconds; a hang is killed."""
    proc, job = started
    try:
        proc.wait(timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        return None, f"timed out after {timeout} s"
    out = job.with_suffix(".out")
    if proc.returncode or not out.exists():
        err = job.with_suffix(".err").read_text(encoding="utf-8", errors="replace")
        tail = [ln.strip() for ln in err.splitlines() if ln.strip()][-1:]
        return None, tail[0] if tail else f"exit code {proc.returncode}"
    return json.loads(out.read_text(encoding="utf-8")), None


def _fresh(folder, size, frames, tmp, tag, seed):
    return _finish(_start(folder, size, frames, tmp, tag, seed))


# ---- the pool (pass 3), the same mechanics as render.render_parallel ----

_scn = _err = None


def _pinit(folder, size):
    """Pool worker start, as render._init: the frame size is set before scenes is imported. An import error is
    kept and returned for every frame (a raising initializer would make the pool restart workers forever)."""
    global _scn, _err
    if folder not in sys.path:
        sys.path.insert(0, folder)
    import engine as E

    E.W, E.H, E.FPS, E.SS = size
    try:
        import scenes

        _scn = scenes
    except L.USER_ERRORS as e:
        _err = f"scenes.py did not import in a pool worker: {type(e).__name__}: {e}"


def _pjob(job):
    """(frame, digest, pixels when the digest is not the expected one, error)."""
    f, expect = job
    import engine as E

    if _err:
        return f, None, None, _err
    try:
        img = _scn.draw(f / E.FPS)
    except L.USER_ERRORS as e:
        return f, None, None, f"{type(e).__name__}: {e}"
    raw = img.tobytes()
    d = C.frame_digest(img, raw)
    return (
        f,
        d,
        _pixels(img.mode, img.size, raw) if expect not in (None, d) else None,
        None,
    )


def _diff(a, b):
    """(pixels that differ in any channel, largest channel difference) of two frames."""
    a, b = np.asarray(a, np.int16), np.asarray(b, np.int16)
    if a.shape != b.shape:
        return a.size, 255
    d = np.abs(a - b)
    return int((d.reshape(d.shape[0], d.shape[1], -1).max(-1) > 0).sum()), int(d.max())


def diagnose(folder, size, f, others, why, tmp, procs):
    """Why frame f is not pure, from fresh processes only (anidoodle's poisoner step): drawn cold twice with one
    hash seed, cold with a second seed, twice in one process, and once behind each of its NEAREST nearest samples.
    A sentence."""
    fps = size[2]
    others = sorted(others, key=lambda g: abs(g - f))[:NEAREST]
    jobs = {
        "cold1": ([f], 1),
        "cold1b": ([f], 1),
        "cold2": ([f], 2),
        "twice": ([f, f], 1),
    }
    jobs.update({f"after{g}": ([g, f], 1) for g in others})
    with ThreadPoolExecutor(procs) as ex:
        futs = {
            k: ex.submit(_fresh, folder, size, fr, tmp, k, s)
            for k, (fr, s) in jobs.items()
        }
        res = {k: v.result() for k, v in futs.items()}

    def last(k):
        r = res[k][0]
        return (
            r["drawn"][-1][1] if r and r["drawn"] and r["drawn"][-1][0] == f else None
        )

    c1, c1b, c2 = last("cold1"), last("cold1b"), last("cold2")
    if None in (c1, c1b, c2):
        r, err = res[next(k for k in ("cold1", "cold1b", "cold2") if last(k) is None)]
        if r is None:
            return f"a fresh process could not run to it ({err})"
        return (
            f"drawn cold in a fresh process it raises {r['errors'].get(str(f), '')}: it needs state that an earlier "
            "frame leaves behind"
        )
    if c1 != c1b:
        return (
            "two cold draws with the same hash seed differ: draw(t) reads something new on every run (the clock, "
            "os.urandom, an unseeded random source, or id() of an object)"
        )
    if c1 != c2:
        return (
            "a cold draw changes with the str hash seed (PYTHONHASHSEED 1 against 2): draw(t) iterates a set of "
            "strings or uses hash() of a str, and every new process and render worker gets a new seed"
        )
    parts = []
    tw = res["twice"][0]
    if tw and len(tw["drawn"]) == 2 and tw["drawn"][1][1] != c1:
        parts.append(
            "drawn twice in one cold process the second draw differs: draw writes state it reads back"
        )
    bad = [g for g in others if last(f"after{g}") not in (None, c1)]
    if bad:
        named = ", ".join(f"frame {g} ({g / fps:.3f} s, {why[g]})" for g in bad[:3])
        parts.append(
            f"{named} poison{'s' if len(bad) == 1 else ''} it ({len(bad)} of its {len(others)} nearest samples): "
            f"drawn cold it hashes {c1}, drawn after frame {bad[0]} it hashes {last(f'after{bad[0]}')}"
        )
    if not parts:
        parts.append(
            f"cold, twice and behind its {len(others)} nearest samples it hashes the same: the difference needs "
            "several earlier frames, or the pool's process layout"
        )
    return "; ".join(parts)


def _scene(scn, t):
    names = [nm for nm, (a, b) in getattr(scn, "SCHEDULE", {}).items() if a <= t < b]
    return "+".join(names) or None


# ---- did the in-order pass run the lines the lint flags? (c4: the g29 bolts drew on no sampled frame) ----


def _codes(mod):
    """Every code object a module's functions and classes define, nested ones included."""
    todo = []
    for v in vars(mod).values():
        if isinstance(v, types.FunctionType) and v.__module__ == mod.__name__:
            todo.append(v.__code__)
        elif isinstance(v, type) and v.__module__ == mod.__name__:
            todo += [
                m.__code__
                for m in vars(v).values()
                if isinstance(m, types.FunctionType)
            ]
    out = []
    while todo:
        c = todo.pop()
        out.append(c)
        todo += [k for k in c.co_consts if isinstance(k, types.CodeType)]
    return out


def flagged(folder):
    """{code object: {line: "func (file:line)"}} of the Q1202 sites the lint finds inside functions of scenes.py and
    its modules (a module-level site runs once at import, so every frame shows it)."""
    found, _ = L.findings(Path(folder, "scenes.py"))
    sites = {}
    for d in found:
        if d["code"] == "Q1202" and d["func"] != "<module>":
            sites.setdefault((Path(d["file"]).stem, d["func"]), {})[d["line"]] = (
                f"{d['func']} ({d['file']}:{d['line']})"
            )
    out = {}
    for (stem, func), lines in sites.items():
        mod = sys.modules.get(stem)
        for c in _codes(mod) if mod is not None else []:
            if c.co_name == func:
                out[c] = lines
    return out


def _watch(sites):
    """Note which flagged lines run (sys.monitoring LINE events in the flagged functions only; any other line
    disables itself after its first event): (ran, stop) or None when there is nothing to watch or the tool id is
    taken."""
    mon = sys.monitoring
    if not sites or mon.get_tool(MON) is not None:
        return None
    mon.use_tool_id(MON, "zoetrope purity")
    ran = set()

    def on_line(code, line):
        where = sites.get(code, {}).get(line)
        if where is None:
            return mon.DISABLE
        ran.add(where)
        return None

    mon.register_callback(MON, mon.events.LINE, on_line)
    for c in sites:
        mon.set_local_events(MON, c, mon.events.LINE)

    def stop():
        for c in sites:
            mon.set_local_events(MON, c, 0)
        mon.register_callback(MON, mon.events.LINE, None)
        mon.free_tool_id(MON)
        mon.restart_events()

    return ran, stop


def run(
    scenes_dir=".", fps=None, size=None, n=16, ss=None, times=(), procs=None, grid=None
):
    """Q1201 rows. fps, size (W, H) and ss default to the engine's current settings when scenes is already imported
    (run_all.py proof), else to the folder's build.json (qa_lint.settings). times: extra seconds to check; grid: also
    one frame every grid seconds. Call it from under `if __name__ == "__main__":` (the pool starts fresh Windows
    workers)."""
    clock = time.perf_counter()
    folder = Path(scenes_dir).resolve()
    try:
        scn, _ = L.load_scenes(folder, fps, size, ss)
    except L.USER_ERRORS as e:
        return [
            C.not_checked(
                "Q1201",
                f"scenes.py did not import ({type(e).__name__}: {e}), so no frame was drawn",
                "fix the import error (qa.py owner --traceback), then rerun qa.py purity",
            )
        ]
    import engine as E

    cfg = (E.W, E.H, E.FPS, E.SS)
    if getattr(scn, "DURATION", None) is None:
        return [
            C.not_checked(
                "Q1201",
                "scenes.py has no DURATION, so no frames were sampled",
                "declare DURATION",
            )
        ]
    picks = sample(scn, E.FPS, n, times, grid)
    frames, why = [f for f, _ in picks], dict(picks)
    procs = procs or max(2, min(4, (os.cpu_count() or 2) // 4))
    try:
        codes = flagged(folder)
    except (SyntaxError, OSError, ValueError):
        codes = {}
    rows = []
    with tempfile.TemporaryDirectory(
        prefix="zoetrope_purity_", ignore_cleanup_errors=True
    ) as tmp:
        # pass 2 starts first and runs alongside pass 1; it holds its frames until it gets pass 1's digests
        fresh = _start(folder, cfg, frames[::-1], tmp, "fresh", hold=True)
        try:
            # pass 1: in order, here, after whatever this process drew before; frames kept compressed for the diff
            held, d1, err1, ran, cut = {}, {}, {}, {}, []
            watch = _watch(codes)
            watched = watch is not None
            t1 = time.perf_counter()
            try:
                for i, f in enumerate(frames):
                    if time.perf_counter() - t1 > TIMEOUT:
                        cut = frames[i:]
                        break
                    if watch:
                        watch[0].clear()
                    try:
                        img = scn.draw(f / E.FPS)
                    except L.USER_ERRORS as e:
                        err1[f] = f"{type(e).__name__}: {e}"
                        continue
                    raw = img.tobytes()
                    d1[f] = C.frame_digest(img, raw)
                    held[f] = (img.mode, img.size, zlib.compress(raw, 1))
                    if watch:
                        ran[f] = set(watch[0])
            finally:
                if watch:
                    watch[1]()
            _send(fresh, d1)
            # pass 3: the pool returns pixels only where it disagrees with pass 1
            d3, a3, err3, pool_fail = {}, {}, {}, None
            try:
                with get_context("spawn").Pool(
                    procs, initializer=_pinit, initargs=(str(folder), cfg)
                ) as pool:
                    pooled = pool.imap_unordered(
                        _pjob, [(f, d1[f]) for f in frames if f in d1], chunksize=1
                    )
                    for _ in range(len(d1)):
                        f, d, arr, e = pooled.next(TIMEOUT)
                        if e:
                            err3[f] = e
                        else:
                            d3[f] = d
                            if arr is not None:
                                a3[f] = arr
            except PoolTimeout:
                pool_fail = f"the pool pass waited {TIMEOUT} s for one frame (a worker died or hung)"
            r2, e2 = _finish(fresh)
        finally:
            if fresh[0].poll() is None:
                fresh[0].kill()
        d2 = {f: d for f, d in r2["drawn"]} if r2 else {}
        err2 = {int(k): v for k, v in r2["errors"].items()} if r2 else {}
        if r2 is None:
            rows.append(
                C.not_checked(
                    "Q1201",
                    f"a fresh python -I process could not draw scenes.py ({e2}): it may need PYTHONPATH, user "
                    "site-packages or a file outside the working folder",
                    "make scenes.py import and draw with only the working folder on sys.path",
                )
            )
        if pool_fail:
            rows.append(
                C.not_checked(
                    "Q1201",
                    pool_fail,
                    "check memory and disk (an environment failure), then rerun qa.py purity",
                )
            )
        if cut:
            rows.append(
                C.not_checked(
                    "Q1201",
                    f"the in-order pass stopped at its {TIMEOUT} s budget: {len(cut)} of {len(frames)} frames were "
                    "not compared",
                    "lower --n, or check those times with --t",
                    worst_t=cut[0] / E.FPS,
                )
            )
        if err1:
            listed = "; ".join(
                f"frame {f} ({f / E.FPS:.3f} s): {e}"
                for f, e in sorted(err1.items())[:3]
            )
            rows.append(
                C.not_checked(
                    "Q1201",
                    f"draw(t) raised in this process at {len(err1)} sampled frames, so they were not compared: {listed}",
                    "fix the exception first (qa.py owner --traceback names the function)",
                    worst_t=min(err1) / E.FPS,
                    item=_scene(scn, min(err1) / E.FPS),
                )
            )
        passes = ([("reversed fresh process", d2, err2)] if r2 else []) + [
            ("pool", d3, err3)
        ]
        bad = {}  # frame -> (which passes differ, pixels, max channel diff)
        for f, d in d1.items():
            ways = [
                label + (f" (raised {errs[f]})" if f in errs else "")
                for label, digs, errs in passes
                if f in errs or (f in digs and digs[f] != d)
            ]
            if not ways:
                continue
            npy = Path(tmp, f"fresh_{f}.npy")
            other = np.load(npy) if npy.exists() else a3.get(f)
            px, mx = (
                _diff(_unhold(held[f]), other) if other is not None else (None, None)
            )
            bad[f] = (ways, px, mx)
        if bad:
            worst = max(bad, key=lambda f: (bad[f][1] or 0, -f))
            others = [g for g in d1 if g != worst]
            diag = diagnose(folder, cfg, worst, others, why, tmp, max(procs, 4))
            ways, px, mx = bad[worst]
            wt = worst / E.FPS
            fns = L.owner(t=wt, path=folder / "scenes.py", fps=E.FPS)["functions"]
            size_txt = (
                f": {px} px differ, max channel diff {mx}" if px is not None else ""
            )
            rows.append(
                C.row(
                    False,
                    "Q1201",
                    f"draw(t) not pure: {len(bad)} of {len(d1)} frames differ; worst frame {worst} ({wt:.3f} s, "
                    f"{why[worst]}) in the {' and the '.join(ways)}{size_txt}; {diag}; owner: "
                    + ", ".join(f"{nm} ({sp})" for nm, sp in fns),
                    FIX,
                    t0=min(bad) / E.FPS,
                    t1=max(bad) / E.FPS,
                    worst_t=round(wt, 3),
                    item=_scene(scn, wt),
                    metric=px,
                    limit=0,
                    spans=C.merge_spans([f / E.FPS for f in bad], E.FPS),
                    considered=len(d1),
                )
            )
        elif d1 and (r2 or not pool_fail):
            # every frame that drew here agrees with the passes that ran; a failed pass has its own row above
            ok = list(d1)
            kinds = {
                "ends and cuts": 0,
                "windows, cues and key times": 0,
                "scene midpoints and even steps": 0,
                "asked": 0,
            }
            for f in ok:
                w = why[f]
                k = (
                    "asked"
                    if w in ("asked", "grid")
                    else "windows, cues and key times"
                    if "(extension)" in w
                    else "scene midpoints and even steps"
                    if "(spread)" in w
                    else "ends and cuts"
                )
                kinds[k] += 1
            mix = ", ".join(f"{v} {k}" for k, v in kinds.items() if v)
            how = " and ".join(
                ["reversed in a fresh python -I process (alongside)"] * bool(r2)
                + [f"through a {procs}-process spawn pool"] * (not pool_fail)
            )
            lint_note = ""
            if codes and not watched:
                lint_note = (
                    "; the Q1202 sites were not watched (sys.monitoring tool id in use)"
                )
            elif codes:
                sites = ", ".join(
                    sorted({w for lines in codes.values() for w in lines.values()})
                )
                hit = [f for f in ok if ran.get(f)]
                lint_note = (
                    f"; the Q1202 site {sites} ran on {len(hit)} of them"
                    if hit
                    else f"; but the Q1202 site {sites} ran on none of them, so its output was not compared: "
                    "check the moments it draws with --t"
                )
            rows.append(
                C.row(
                    True,
                    "Q1201",
                    f"draw(t) pure: {len(ok)} frames ({mix}) hash the same in order here, {how}, at {E.W}x{E.H}, "
                    f"{E.FPS} fps, SS {E.SS} ({time.perf_counter() - clock:.1f} s){lint_note}",
                    "",
                    considered=len(ok),
                )
            )
    return rows


def _cli(a):
    size = tuple(int(x) for x in a.size.lower().split("x")) if a.size else None
    times = [float(x) for x in a.t.split(",")] if a.t else ()
    rows = run(a.scenes, a.fps, size, a.n, a.ss, times, a.procs, a.grid)
    for r in rows:
        print(C.line(r))
    if a.json:
        C.write_rows(rows, a.json)
    print(C.summary(rows, "PURITY"))
    return C.exit_code(rows)


def add_cli(sub):
    p = sub.add_parser(
        "purity",
        help="draw(t) hashes the same in order here, reversed in a fresh python -I process and through the pool (Q1201)",
    )
    p.add_argument("--scenes", default=".", help="folder holding scenes.py")
    p.add_argument(
        "--n",
        type=int,
        default=16,
        help="cut frames and interior frames, each at most n (2 + 2n in all, plus --t and --grid)",
    )
    p.add_argument(
        "--fps", type=int, help="default: build.json (run_all.py writes it), else 30"
    )
    p.add_argument("--size", help="WxH, default: build.json, else 1920x1080")
    p.add_argument("--ss", type=int, help="supersampling, default: build.json, else 1")
    p.add_argument(
        "--t", help="extra comma-separated seconds to check, for example a fixed moment"
    )
    p.add_argument(
        "--grid",
        type=float,
        help="also one frame every GRID seconds: a dense check, about 3 draws a frame",
    )
    p.add_argument("--procs", type=int, help="pool size (default 2 to 4)")
    p.add_argument("--json", help="also write the rows as JSON to this path")
    p.set_defaults(func=_cli)
