# qa_approve.py : the approved build and every change after it (Q1301 to Q1304). `qa.py approve` keeps what the
# reviewer passed in approved/, `qa.py check` flags a stale approval, `qa.py diff` lists the frames and 100 ms audio
# blocks that changed since, with before | after | difference triptychs, and `qa.py verify` re-hashes the file.
# Approval is per hash, not per conversation turn: any change to what the reviewer saw shows up here.
# Frames are drawn by worker subprocesses (this file run as `python qa_approve.py _draw <job.json>`), never in the
# caller: each sets the frame size before importing scenes, and the approved and current scenes.py never share one.
import ast
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import contract as C
import numpy as np
import PIL
from PIL import Image, ImageDraw, ImageFont

# inside approved/: SRC holds scenes.py and every local module it imports, so a 'before' frame can be redrawn;
# AUDIO_HASH one digest per 100 ms block of mix_raw.wav
SRC, AUDIO_HASH, BLOCK_S = "src", "mix_raw.hash", 0.1
# approve writes the next approval into NEW and swaps it in; OLD holds the previous one between the two renames
NEW, OLD = f"{C.APPROVED}.new", f"{C.APPROVED}.old"
GLOBAL = 0.3  # more than this share of the film changed: a global change (grain, palette), sampled, not spans
SIZE_KEYS = ("W", "H", "FPS", "SS")
AUDIO_ONLY = "only the audio gates (Q801 to Q805) and cue sync (Q902, Q903) matter, no frame review"
STAMP = "%Y-%m-%d %H:%M:%S"  # how qa.py check prints a file's written time, which the reviewer quotes
STAMP_RE = r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d"
# this module's own codes (Q1301 to Q1304) describe the approval, not the film: a re-approval supersedes them, so
# approve does not count them as FIX rows and the baseline does not compare them
OWN = {code for code, v in C.CODES.items() if v[0] == "qa_approve"}
# the keys every reader of approval.json uses, checked before it is trusted
NEEDS = (
    ("approved_at",),
    ("duration",),
    ("scenes",),
    ("video", "path"),
    ("video", "sha256"),
    ("video", "streamhash"),
    ("frames", "n"),
    ("frames", "sha256"),
    ("env", "python"),
    ("env", "pillow"),
    ("env", "numpy"),
    ("env", "fonts"),
    ("env", "size"),
    ("env", "modules"),
)


# ---- hashes ----


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _sha_or_none(path):
    return sha256_file(path) if Path(path).is_file() else None


def stamp(path):
    return time.strftime(STAMP, time.localtime(Path(path).stat().st_mtime))


def streamhash(path, ff=None):
    """sha256 of the decoded video frames (ffmpeg -f streamhash), None when it cannot decode: equal when the picture
    is identical whatever the audio or container. It decodes; a stream copy would compare x264 bitstreams."""
    hashing = ["-map", "0:v:0", "-f", "streamhash", "-hash", "sha256", "-"]
    cmd = [ff or C.find_ffmpeg() or "ffmpeg", "-v", "error", "-i", str(path), *hashing]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    m = re.search(r"SHA256=([0-9a-f]+)", r.stdout)
    return m.group(1) if m else None


def ffmpeg_version(ff=None):
    try:
        out = subprocess.run(
            [ff or C.find_ffmpeg() or "ffmpeg", "-version"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.split()[2] if out.startswith("ffmpeg version") else out[:60]


def wav_data(path):
    """(sample rate, channels, bits, format code, raw data bytes) of a WAV in any sample format (PCM or float)."""
    b = Path(path).read_bytes()
    i, fmt, data = 12, None, b""
    while i + 8 <= len(b):
        cid, size = b[i : i + 4], int.from_bytes(b[i + 4 : i + 8], "little")
        if cid == b"fmt ":
            fmt = b[i + 8 : i + 8 + size]
        elif cid == b"data":
            data = b[i + 8 : i + 8 + size]
        i += 8 + size + (size & 1)
    sr, ch, bits, code = (
        int.from_bytes(fmt[a:b], "little")
        for a, b in ((4, 8), (2, 4), (14, 16), (0, 2))
    )
    # WAVE_FORMAT_EXTENSIBLE: the real format code opens the sub-format GUID
    if code == 0xFFFE and len(fmt) >= 26:
        code = int.from_bytes(fmt[24:26], "little")
    return sr, ch, bits, code, data


def wav_samples(path):
    """(sample rate, float64 (n, channels) in -1..1) of a 16 or 32-bit PCM or a float WAV; None for other formats."""
    sr, ch, bits, code, data = wav_data(path)
    kind = {
        (1, 16): ("<i2", 32768),
        (1, 32): ("<i4", 2**31),
        (3, 32): ("<f4", 1),
        (3, 64): ("<f8", 1),
    }
    if (code, bits) not in kind:
        return None
    dt, scale = kind[code, bits]
    step = ch * bits // 8
    x = np.frombuffer(data[: len(data) // step * step], dt)
    return sr, x.reshape(-1, ch).astype(np.float64) / scale


def audio_blocks(path, block_s=BLOCK_S):
    """One blake2b-8 per 100 ms of a WAV's raw samples. Run on mix_raw.wav, the pre-master mix: the master's single
    loudnorm gain moves every sample of mix.wav, so one edit there would mark the whole film."""
    sr, ch, bits, _, data = wav_data(path)
    step = ch * bits // 8
    n = len(data) // step
    out, k = [], 0
    while C.sample_of(k * block_s, sr) < n:
        a, b = C.sample_of(k * block_s, sr), min(n, C.sample_of((k + 1) * block_s, sr))
        out.append(
            hashlib.blake2b(data[a * step : b * step], digest_size=8).hexdigest()
        )
        k += 1
    return {
        "file": C.MIX_RAW,
        "sr": sr,
        "frame_bytes": step,
        "samples": n,
        "block_s": block_s,
        "algo": "blake2b-8",
        "hash": out,
    }


def block_runs(ks, block_s=BLOCK_S):
    """[(t0, t1), ...] of sorted block indices, neighbours joined."""
    runs = []
    for k in ks:
        if runs and k == runs[-1][1] + 1:
            runs[-1][1] = k
        else:
            runs.append([k, k])
    return [(round(a * block_s, 3), round((b + 1) * block_s, 3)) for a, b in runs]


def audio_change(old_hash, old_wav, new_wav, tol=2 / 32768):
    """(changed block indices, overall gain in dB or None) of new_wav against the approved mix. Blocks whose hashes
    match are unchanged. The rest are compared on their samples with one overall gain taken out first (the median
    of the per-block gains): audio.write_wav peak-normalises mix_raw.wav, so a quieter loudest hit rescales every
    sample, and hashes alone would call the whole film changed. A block changed when its residual is over tol RMS
    (2 steps of 16 bit: the two truncations leave under 1). Without the approved copy: the hash differences."""
    new_hash = audio_blocks(new_wav)
    a, b = old_hash["hash"], new_hash["hash"]
    nb = max(len(a), len(b))
    diff = [k for k in range(nb) if k >= len(a) or k >= len(b) or a[k] != b[k]]
    old = wav_samples(old_wav) if diff and Path(old_wav).exists() else None
    new = wav_samples(new_wav) if old else None
    if (
        not diff
        or old is None
        or new is None
        or old[0] != new[0]
        or old[1].shape[1] != new[1].shape[1]
    ):
        return diff, None
    sr = old[0]
    pairs = []  # (approved, new) samples of each block; unequal lengths where the mix got longer or shorter
    for k in range(nb):
        lo, hi = C.sample_of(k * BLOCK_S, sr), C.sample_of((k + 1) * BLOCK_S, sr)
        pairs.append((old[1][lo:hi], new[1][lo:hi]))
    gains = []
    for xo, yn in pairs:
        e = (xo**2).sum()
        if len(xo) == len(yn) and e > 1e-6:
            gains.append((yn * xo).sum() / e)
    g = float(np.median(gains)) if gains else 1.0
    bad = []
    for k in diff:
        xo, yn = pairs[k]
        if (
            len(xo) != len(yn)
            or not len(xo)
            or np.sqrt(((yn - g * xo) ** 2).mean()) > tol
        ):
            bad.append(k)
    return bad, 20 * math.log10(g) if g > 0 else None


# ---- what the build is made of, read from its files without importing them ----


def _tree(path):
    """The parsed module at path; None when it is missing or does not parse (the draw that imports it says why)."""
    try:
        return ast.parse(Path(path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return None


def _key(node, attr):
    """The size name an assignment target sets: E.W or engine.W in run_all.py (attr), a bare W in engine.py."""
    if attr:
        ok = isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
        return node.attr if ok and node.value.id in ("E", "engine") else None
    return node.id if isinstance(node, ast.Name) else None


def _literals(folder):
    """{W, H, FPS, SS: value} the build's files set as literals: run_all.py's `E.W, E.H, E.FPS, E.SS = ...` first,
    engine.py's own defaults for any it leaves out."""
    got = {}
    for name, attr in (("run_all.py", True), ("engine.py", False)):
        tree = _tree(Path(folder, name))
        for node in ast.walk(tree) if tree else []:
            if not isinstance(node, ast.Assign):
                continue
            for tgt in node.targets:
                tup = isinstance(tgt, ast.Tuple) and isinstance(node.value, ast.Tuple)
                for n, v in (
                    zip(tgt.elts, node.value.elts) if tup else [(tgt, node.value)]
                ):
                    k = _key(n, attr)
                    if k in SIZE_KEYS and k not in got:
                        try:
                            got[k] = ast.literal_eval(v)
                        except (ValueError, TypeError):
                            continue
    return got


def _from_manifest(folder):
    """(W, H, FPS, SS) from frames.hash, the last render's record, or None without one. A frames.hash from before
    its "ss" key takes SS from the literals."""
    man = C.read_frame_manifest(folder)
    if man is None:
        return None
    return man["w"], man["h"], man["fps"], man.get("ss", _literals(folder).get("SS", 1))


def build_size(folder="."):
    """(W, H, FPS, SS) the build renders at: build.json (run_all.py writes it in every stage, after --size, --fps
    and scenes.py have had their say), else frames.hash, else the literals in run_all.py and engine.py (None when
    they are not all literals). SS matters: frames drawn at another supersampling hash differently."""
    got = C.read_build(folder) or _from_manifest(folder)
    if got:
        return tuple(got)
    lit = _literals(folder)
    return (
        tuple(lit[k] for k in SIZE_KEYS) if all(k in lit for k in SIZE_KEYS) else None
    )


def size_now(folder="."):
    """The size to hold against the approval: build.json, else frames.hash; with neither, only SS from the literals
    (W, H and FPS None, as run_all.py's literals are only defaults that --size and --fps replace)."""
    got = C.read_build(folder) or _from_manifest(folder)
    return tuple(got) if got else (None, None, None, _literals(folder).get("SS", 1))


def build_out(folder="."):
    """The file run_all.py writes (its OUT = "..." or Path("...")), else out.mp4."""
    tree = _tree(Path(folder, "run_all.py"))
    for node in tree.body if tree else []:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "OUT" for t in node.targets
        ):
            v = (
                node.value.args[0]
                if isinstance(node.value, ast.Call) and node.value.args
                else node.value
            )
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                return v.value
    return "out.mp4"


def local_modules(folder="."):
    """Every local .py file the build imports, from scenes.py on (engine, grain, a kit's helpers ...), found from
    the import statements anywhere in each file, so an import inside draw() counts too. A file that does not parse
    still counts; the draw that imports it reports the error."""
    seen, todo = set(), ["scenes"]
    while todo:
        name = todo.pop()
        p = Path(folder, f"{name}.py")
        if name in seen or not p.exists():
            continue
        seen.add(name)
        tree = _tree(p)
        for node in ast.walk(tree) if tree else []:
            if isinstance(node, ast.Import):
                todo += [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                todo.append(node.module.split(".")[0])
    return sorted(f"{m}.py" for m in seen)


def scene_frames(schedule, fps, n):
    """{scene: (first, last)} frame indices of each scene in a film of n frames, by engine.scene_at's rule: a scene
    holds frames frame_of(a) to frame_of(b) - 1 (the nearest frame, contract.frame_of)."""
    out = {}
    for name, (a, b) in schedule.items():
        f0 = max(0, min(n - 1, C.frame_of(a, fps)))
        out[name] = (f0, max(f0, min(n - 1, C.frame_of(b, fps) - 1)))
    return out


def scene_of(i, spans):
    """The scene that draws frame i: the first whose span holds it, as in engine.scene_at (past the end, the last)."""
    return next((s for s, (f0, f1) in spans.items() if f0 <= i <= f1), list(spans)[-1])


def key_frames(schedule, fps, n, times=()):
    """{scene: [frame, ...]}: the frames the reviewer saw (review_times.json, the look copies) plus each scene's
    first, middle and last frame, each filed under the scene that draws it."""
    spans = scene_frames(schedule, fps, n)
    keys = {s: {f0, (f0 + f1) // 2, f1} for s, (f0, f1) in spans.items()}
    for t in times:
        i = min(n - 1, max(0, C.frame_of(t, fps)))
        keys[scene_of(i, spans)].add(i)
    return {s: sorted(v) for s, v in keys.items()}


def _scene_hash(frames, digests):
    return hashlib.sha256(
        "".join(f"{i}:{d};" for i, d in zip(frames, digests)).encode()
    ).hexdigest()


# ---- drawing in worker subprocesses ----


def default_procs():
    """The share of cores render.render_parallel takes."""
    return max(1, min(8, (os.cpu_count() or 2) // 4))


def _last_line(err):
    """A worker's error: the traceback's last line, with the last file and line it names."""
    lines = [x.strip() for x in (err or "").splitlines() if x.strip()]
    if not lines:
        return "a draw worker exited with no message"
    at = [m for x in lines if (m := re.match(r'File "(.+)", line (\d+)', x))]
    return lines[-1] + (
        f" ({Path(at[-1].group(1)).name}, line {at[-1].group(2)})" if at else ""
    )


def draw_frames(folder, src, size, frames, save=None, procs=None, timeout=3600):
    """Draw frames (indices) of src/scenes.py at size (W, H, FPS, SS) in worker subprocesses started in folder, so
    relative data paths resolve as in the build. Returns {"digests": {i: hex}, "schedule", "duration", "fonts"};
    save ({i: png path}) also writes those frames. Raises RuntimeError with the first failing worker's last line."""
    frames, save = sorted(set(frames)), save or {}
    k = max(1, min(procs or default_procs(), len(frames)))
    out = {"digests": {}, "fonts": set()}
    with tempfile.TemporaryDirectory() as tmp:
        jobs = []
        for j in range(k):
            mine = frames[j::k]  # strided, so a heavy scene spreads over every worker
            job = {
                "src": str(Path(src).resolve()),
                "size": list(size),
                "frames": mine,
                "save": {str(i): str(save[i]) for i in mine if i in save},
                "out": str(Path(tmp, f"out{j}.json")),
            }
            Path(tmp, f"job{j}.json").write_text(json.dumps(job), encoding="utf-8")
            cmd = [
                sys.executable,
                str(Path(__file__).resolve()),
                "_draw",
                str(Path(tmp, f"job{j}.json")),
            ]
            jobs.append(
                subprocess.Popen(
                    cmd,
                    cwd=folder,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        errs = []
        for j, p in enumerate(jobs):
            try:
                _, err = p.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                for q in jobs:
                    q.kill()
                    q.wait()
                raise RuntimeError(f"a draw worker ran over {timeout} s") from None
            if p.returncode:
                errs.append(_last_line(err))
                continue
            r = json.loads(Path(tmp, f"out{j}.json").read_text(encoding="utf-8"))
            out["digests"].update({int(i): d for i, d in r["digests"].items()})
            out["fonts"] |= set(r["fonts"])
            out["schedule"], out["duration"] = r["schedule"], r["duration"]
    if errs:
        raise RuntimeError(errs[0])
    return out


def _worker(job_path):
    """One worker (`python qa_approve.py _draw <job.json>`): import src/scenes.py at the job's frame size, as
    render.py's workers do, draw the frames, write their digests and any PNGs asked for, and every font file the
    drawing opened (ImageFont.truetype is wrapped before anything is imported, so a font opened and dropped at once
    counts too)."""
    sys.dont_write_bytecode = True  # leaves approved/src exactly the snapshot
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    src = Path(job["src"])
    opened, truetype = set(), ImageFont.truetype

    def recording(font=None, *a, **k):
        if isinstance(font, (str, os.PathLike)):
            opened.add(os.fspath(font))
        return truetype(font, *a, **k)

    ImageFont.truetype = recording
    sys.path.insert(0, str(src))
    import engine as E

    E.W, E.H, E.FPS, E.SS = job["size"]
    import scenes

    # a module missing from src would silently load from the working folder instead
    for m in (E, scenes):
        if Path(m.__file__).resolve().parent != src:
            raise ImportError(
                f"{m.__name__} loaded from {Path(m.__file__).parent}, not from {src}"
            )
    save = {int(i): p for i, p in job["save"].items()}
    digests = {}
    for i in job["frames"]:
        img = scenes.draw(C.t_of(i, E.FPS))
        if img.mode != "RGB":  # as render.py does before it hashes
            img = img.convert("RGB")
        digests[i] = C.frame_digest(img)
        if i in save:
            img.save(save[i], compress_level=1)
    lists = [getattr(E, a, []) for a in ("FONT_BOLD", "FONT_REG")]
    fonts = {
        next((p for p in lst if os.path.exists(p)), None) for lst in lists
    } | opened
    result = {
        "digests": digests,
        "schedule": {s: list(v) for s, v in scenes.SCHEDULE.items()},
        "duration": scenes.DURATION,
        "fonts": sorted(p for p in fonts if p),
    }
    Path(job["out"]).write_text(json.dumps(result), encoding="utf-8")


# ---- the environment: what decides the pixels besides the source ----


def _minor(v):
    """'3.14.9' -> '3.14': a patch release of Python does not change pixels; the key-frame redraw has the last word."""
    return ".".join(str(v).split(".")[:2])


def env_now(folder, size, fonts):
    """The env stanza: interpreter, Pillow, numpy, the font files and the frame size decide the pixels; ffmpeg
    decides only the encode; modules holds the sha256 of every local module the build imports (content, not
    environment: a change there is what diff and the key-frame check measure)."""
    return {
        "python": platform.python_version(),
        "pillow": PIL.__version__,
        "numpy": np.__version__,
        "ffmpeg": ffmpeg_version(),
        "fonts": {p: _sha_or_none(p) for p in sorted(fonts)},
        "size": dict(zip(SIZE_KEYS, size)),
        "modules": {m: sha256_file(Path(folder, m)) for m in local_modules(folder)},
    }


def env_changes(old):
    """What changed since the approval in what draws the pixels besides the source: Python (major.minor), Pillow,
    numpy, a font file. Short phrases; [] when nothing did. Such a change is held against the redrawn frames: it
    blocks the approval only when a frame moved."""
    out = []
    if _minor(old["python"]) != _minor(platform.python_version()):
        out.append(f"python {old['python']} -> {platform.python_version()}")
    out += [
        f"{k} {old[k]} -> {v}"
        for k, v in (("pillow", PIL.__version__), ("numpy", np.__version__))
        if old[k] != v
    ]
    for p, h in old["fonts"].items():
        cur = _sha_or_none(p)
        if cur != h:
            out.append(f"font {Path(p).name} {'missing' if cur is None else 'changed'}")
    return out


def size_changes(old, size):
    """E.W, E.H, E.FPS or E.SS the build uses now (size_now; None skipped) against the approved ones."""
    return [
        f"E.{k} {old['size'].get(k)} -> {v}"
        for k, v in zip(SIZE_KEYS, size)
        if v is not None and old["size"].get(k) != v
    ]


def _size_row(changes):
    return C.not_checked(
        "Q1304",
        f"frame size changed since approval: re-approve ({'; '.join(changes)})",
        "every frame differs at another size: review the film in full, then qa.py approve again",
        item="; ".join(changes),
    )


def _env_moved_row(changes, where, source_changed):
    """Q1304 NOT CHECKED: the environment changed and frames moved, so the approval cannot be held to them."""
    why = (
        "the source changed too, so which one moved them cannot be told"
        if source_changed
        else "the source is the approved one, so the environment moved them"
    )
    return C.not_checked(
        "Q1304",
        f"environment changed since approval ({'; '.join(changes)}) and frames moved ({where}): {why}: re-approve",
        "review the film in full, then qa.py approve again",
        item="; ".join(changes),
    )


def _env_same_row(changes, what):
    return C.row(
        False,
        "Q1304",
        f"environment changed since approval ({'; '.join(changes)}), but {what} the same: the approval stands",
        "nothing to do; re-approve to record the new environment",
        note=True,
        item="; ".join(changes),
    )


def _modules_changed(appr, folder):
    """Approved modules whose file differs now (or is gone), plus local modules the build imports now and did not."""
    old = appr["env"]["modules"]
    out = [m for m, h in old.items() if _sha_or_none(Path(folder, m)) != h]
    return sorted(out + [m for m in local_modules(folder) if m not in old])


# ---- approved/: written whole, read only when it matches what approval.json recorded ----


def approved_dir(folder="."):
    """approved/, or approved.old/ when an approve stopped between its two renames (the previous approval)."""
    cur, old = Path(folder, C.APPROVED), Path(folder, OLD)
    return old if not cur.exists() and old.exists() else cur


def read_approval(folder="."):
    """approved/approval.json as a dict, unchecked, or None when the build has no approval (approve keeps its history)."""
    p = Path(approved_dir(folder), C.APPROVAL)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def recorded_files(appr):
    """{path in approved/: sha256} of every file the approval holds: its `files`, and for an approval written before
    that key, frames.hash, mix_raw.wav and the src/ modules from the hashes it kept."""
    got = {C.FRAMES_HASH: appr["frames"]["sha256"]}
    if appr.get("audio"):
        got[C.MIX_RAW] = appr["audio"]["sha256"]
    got |= {f"{SRC}/{m}": h for m, h in appr["env"]["modules"].items()}
    return got | appr.get("files", {})


def load_approval(folder="."):
    """(approval, problem), checked before anything trusts it. (None, None): the build has no approval. A problem
    (for a NOT CHECKED row) when approval.json does not parse, lacks a key a reader needs, records a scene whose
    hash does not fit its digests, or when a file in approved/ is missing or not the sha256 recorded for it (an
    approve that stopped half way, or an edit behind its back)."""
    adir = approved_dir(folder)
    p = Path(adir, C.APPROVAL)
    if not p.exists():
        return None, None
    try:
        appr = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return None, f"{C.APPROVED}/{C.APPROVAL} unreadable ({e})"
    lacks = []  # each missing key named at its first missing level: a lost "env" is "env", not its six keys
    for path in NEEDS:
        v = appr
        for d, k in enumerate(path):
            v = v.get(k) if isinstance(v, dict) else None
            if v is None:
                if (
                    path != ("video", "streamhash")
                    and ".".join(path[: d + 1]) not in lacks
                ):
                    lacks.append(".".join(path[: d + 1]))
                break
    if lacks:
        return None, f"{C.APPROVED}/{C.APPROVAL} lacks {', '.join(lacks)}"
    for name, s in appr["scenes"].items():
        if _scene_hash(s.get("frames", []), s.get("digests", [])) != s.get("hash"):
            return (
                None,
                f"{C.APPROVED}/{C.APPROVAL}: the record of scene {name} does not fit its own hash",
            )
    if bad := [
        f for f, h in recorded_files(appr).items() if _sha_or_none(Path(adir, f)) != h
    ]:
        return (
            None,
            f"{C.APPROVED}/ does not match {C.APPROVAL}: {', '.join(bad[:4])} missing or changed since the approval",
        )
    return appr, None


def _swap(folder):
    """Put approved.new/ in the place of approved/ with two renames. The previous approval stays whole until the
    second rename has happened, and a failed rename puts it back."""
    cur, new, old = Path(folder, C.APPROVED), Path(folder, NEW), Path(folder, OLD)
    shutil.rmtree(old, ignore_errors=True)
    if old.exists():
        raise OSError(
            f"{old.name}/ is left from an earlier approve and cannot be removed (a file in it is open)"
        )
    if cur.exists():
        cur.rename(old)
    try:
        new.rename(cur)
    except OSError:
        if old.exists() and not cur.exists():
            old.rename(cur)
        raise
    shutil.rmtree(old, ignore_errors=True)


# ---- review times: what an earlier diff added is taken back before a new list is written ----


def times_file(folder):
    """review_times.json, readable or absent: a file that does not parse is moved to review_times.json.bad (with a
    warning) rather than stopping the run or being overwritten."""
    p = Path(folder, C.REVIEW_TIMES)
    if p.exists():
        try:
            C.read_review_times(p)
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            bad = p.with_name(f"{p.name}.bad")
            bad.unlink(missing_ok=True)
            p.replace(bad)
            print(
                f"warning: {p.name} did not parse ({e}); moved to {bad.name}, starting a new one"
            )
    return p


def _drop_changed(path):
    """Take out of review_times.json what an earlier diff added (reasons led by Q1303, kind changed), so a change
    since declared or reverted, or approved, is not still listed as undeclared. A time that only a diff asked for
    goes; one that others asked for keeps their reasons and kinds (and loses a status only this module set)."""
    if not Path(path).exists():
        return 0
    keep, dropped = [], 0
    for e in C.read_review_times(path):
        why = [p for p in e["why"].split("; ") if p and not p.startswith("Q1303 ")]
        kinds = [k for k in e["kinds"] if k != "changed"]
        dropped += "changed" in e["kinds"]
        if not why and not kinds:
            continue
        mine = e["code"] == "Q1303"
        e.update(why="; ".join(why), kinds=kinds, kind=kinds[0] if kinds else "key")
        e.update(code=None if mine else e["code"], status=None if mine else e["status"])
        keep.append(e)
    Path(path).write_text(json.dumps(keep, indent=1), encoding="utf-8")
    return dropped


# ---- approve ----


def read_review(path, reviewer=None, folder=".", since=0.0):
    """The reviewer's reply, kept verbatim (its text, and the sha256 of its bytes as saved) and what it states:
    verdict, reviewer id, stage, the file and its written time, and its 'frames seen:' line; plus the look copies
    (review/t*.jpg) qa.py look wrote after `since` (the video's modified time), the frames it extracted from this
    file. Read as utf-8-sig with any line ends, as Windows PowerShell saves it."""
    raw = Path(path).read_bytes()
    text = raw.decode("utf-8-sig")
    flat = text.replace("\r\n", "\n").replace("\r", "\n")

    def field(name):
        m = re.search(rf"(?im)^[ \t]*{name}[ \t]*:[ \t]*(.+?)[ \t]*$", flat)
        return m.group(1) if m else None

    v = re.search(r"(?m)^[ \t]*REVIEW (PASS|FIX)\b", flat)
    f = re.search(r"\bfile:[ \t]*([^\s(|]+)", flat)
    w = re.search(rf"\(written ({STAMP_RE})", flat)
    stage = re.search(r"\bstage:[ \t]*(\w+)", flat)
    looks = sorted(
        float(m.group(1))
        for p in Path(folder, "review").glob("t*.jpg")
        if (m := re.fullmatch(r"t(\d+\.\d+)\.jpg", p.name))
        and p.stat().st_mtime >= since
    )
    return {
        "verdict": f"REVIEW {v.group(1)}" if v else "no REVIEW PASS or REVIEW FIX line",
        "reviewer": reviewer or field("reviewer"),
        "stage": stage.group(1) if stage else None,
        "file": f.group(1) if f else None,
        "written": w.group(1) if w else None,
        "frames_seen": field("frames seen"),
        "look_copies": looks,
        "source": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "text": text,
    }


def _same_time(a, b):
    """Two written times in qa.py check's format within 1 s; False when either does not parse (fails closed)."""
    try:
        return (
            abs(
                time.mktime(time.strptime(a, STAMP))
                - time.mktime(time.strptime(b, STAMP))
            )
            <= 1
        )
    except (TypeError, ValueError):
        return False


def _review_refusals(rev, vid, rel):
    """What in the reply keeps it from binding to this file: a reply must say REVIEW PASS at the final stage and
    name this file with the written time qa.py check printed for it."""
    if rev is None:
        return [
            "no reviewer verdict: pass --review <file holding the reviewer's reply>"
        ]
    out = []
    if rev["verdict"] != "REVIEW PASS":
        out.append(f"the review says {rev['verdict']}")
    if not rev["stage"]:
        out.append(
            "the review names no stage (want 'stage: final'); approve after the final review"
        )
    elif rev["stage"] != "final":
        out.append(
            f"the review is a {rev['stage']}-stage review; approve after the final review"
        )
    if not rev["file"]:
        out.append(
            "the review names no file (want 'file: <name> (written <time>)' as qa.py check prints it)"
        )
    elif Path(rev["file"]).name != vid.name:
        out.append(f"the review is of {rev['file']}, not {rel}")
    if not rev["written"]:
        out.append(
            "the review gives no written time for the file (want '(written YYYY-MM-DD HH:MM:SS')"
        )
    elif not _same_time(rev["written"], stamp(vid)):
        out.append(
            f"the review saw a file written {rev['written']}; {rel} was written {stamp(vid)}"
        )
    return out


def _cannot(msgs):
    for m in msgs:
        print(f"CANNOT APPROVE: {m}")
    return 2


def approve(
    folder=".", review=None, video=None, reviewer=None, override=None, procs=None
):
    """Keep the reviewed build in approved/. Returns 0 approved, 1 refused (a review or QA reason; --override
    approves anyway and records why), 2 could not approve (an input is missing or is not from this build). It
    writes the whole approval into approved.new/ first, approval.json last, then swaps it in: a run that stops on
    the way leaves the previous approval as it was."""
    import qa

    folder = Path(folder)
    rel = video or build_out(folder)
    vid = folder / rel
    man = C.read_frame_manifest(folder)
    checks = (
        (
            (folder / "scenes.py").exists(),
            "no scenes.py here: pass --scenes <working folder>",
        ),
        (vid.exists(), f"no {rel}: render it first (python run_all.py full)"),
        (
            man is not None and (folder / C.THUMBS).exists(),
            f"no {C.FRAMES_HASH} and {C.THUMBS}: render with run_all.py full, which writes both",
        ),
        (review is None or Path(review).exists(), f"no review file {review}"),
    )
    if stop := [msg for ok, msg in checks if not ok]:
        return _cannot(stop)
    size = build_size(folder)  # build.json first: what run_all.py last ran at
    fps, n = size[2], man["n"]
    p = qa.probe(str(vid))
    thumbs = np.load(folder / C.THUMBS, mmap_mode="r")
    num, den = (int(x) for x in p["fps"].split("/"))
    rendered = _from_manifest(folder)
    other = (
        f"{C.FRAMES_HASH} is {rendered[0]}x{rendered[1]} at {rendered[2]} fps SS {rendered[3]}, the build "
        f"{size[0]}x{size[1]} at {fps} fps SS {size[3]}: render again at the build's size"
    )
    checks = (
        (rendered == size, other),
        (
            abs(num / den - fps) < 0.01,
            f"{rel} runs at {p['fps']} fps, the build at {fps}",
        ),
        (
            (p["w"], p["h"]) == size[:2],
            f"{rel} is {p['w']}x{p['h']}, the build {size[0]}x{size[1]}",
        ),
        (
            not p["frames"] or abs(p["frames"] - n) <= 1,
            f"{rel} has {p['frames']} frames, {C.FRAMES_HASH} {n}: not the same render",
        ),
        (
            thumbs.shape[0] == n,
            f"{C.THUMBS} has {thumbs.shape[0]} frames, {C.FRAMES_HASH} {n}",
        ),
    )
    if stop := [msg for ok, msg in checks if not ok]:
        return _cannot(stop)
    rev = read_review(review, reviewer, folder, vid.stat().st_mtime) if review else None
    times = [e["t"] for e in C.read_review_times(times_file(folder))]
    try:
        meta = draw_frames(folder, folder, size, [], procs=1)
        keys = key_frames(
            meta["schedule"], fps, n, times + (rev["look_copies"] if rev else [])
        )
        res = draw_frames(
            folder, folder, size, [i for v in keys.values() for i in v], procs=procs
        )
    except RuntimeError as e:
        return _cannot([f"scenes.py did not draw: {e}"])
    if bad := sorted(i for i, d in res["digests"].items() if man["hash"][i] != d):
        stale = (
            f"{C.FRAMES_HASH} does not match draw(t) at {len(bad)} of {len(res['digests'])} key frames "
            f"(first {bad[0] / fps:.2f} s): scenes.py changed after the render, or the render ran at another size "
            f"than {size[0]}x{size[1]} SS {size[3]}; re-render, then approve"
        )
        return _cannot([stale])

    # what the reviewer or the gates said against it; --override approves anyway, on the record
    refuse = _review_refusals(rev, vid, rel)
    if rev and not rev["reviewer"]:
        print(
            "note: the review names no reviewer (add 'reviewer:' to the reply or pass --reviewer)"
        )
    qa_path = folder / C.QA_JSON
    qa_rows = C.read_rows(qa_path) if qa_path.exists() else None
    if qa_rows is None:
        print(
            f"note: no {C.QA_JSON}, so no baseline for --baseline (qa.py check ... --json {C.QA_JSON} keeps one)"
        )
    else:
        for st in (C.FIX, C.NOT_CHECKED):
            if codes := sorted(
                {r.code for r in qa_rows if r.status == st and r.code not in OWN}
            ):
                refuse.append(f"{C.QA_JSON} has {st} rows: {', '.join(codes)}")
        if qa_path.stat().st_mtime < vid.stat().st_mtime:
            refuse.append(
                f"{C.QA_JSON} is older than {rel}: run qa.py check on it again with --json {C.QA_JSON}"
            )
    if refuse and not override:
        for r in refuse:
            print(f"REFUSED: {r}")
        print(
            'fix the cause, or approve anyway with --override "<why>" (kept in approval.json, shown by qa.py check)'
        )
        return 1
    now = time.strftime(STAMP)
    overrides = [{"what": r, "why": override, "at": now} for r in refuse]

    # everything goes here first; approved/ is not touched until the swap
    new = folder / NEW
    shutil.rmtree(new, ignore_errors=True)
    if new.exists():
        return _cannot(
            [
                f"{NEW}/ is left from an earlier approve and cannot be removed (a file in it is open)"
            ]
        )
    (new / SRC).mkdir(parents=True)
    mods = local_modules(folder)
    for m in mods:
        shutil.copy2(folder / m, new / SRC / m)
    for name in (C.FRAMES_HASH, C.THUMBS):
        shutil.copy2(folder / name, new / name)
    if qa_rows is not None:
        shutil.copy2(qa_path, new / C.QA_JSON)
    mix = folder / C.MIX_RAW
    blocks = audio_blocks(mix) if mix.exists() else None
    if blocks:  # the copy lets diff take the raw mix's peak-normalising gain out before it compares blocks
        (new / AUDIO_HASH).write_text(json.dumps(blocks), encoding="utf-8")
        shutil.copy2(mix, new / C.MIX_RAW)
    files = {
        f.relative_to(new).as_posix(): sha256_file(f)
        for f in sorted(new.rglob("*"))
        if f.is_file()
    }

    loud = qa.loud(str(vid)) if p["acodec"] else None
    scenes = {}
    for name, frames in keys.items():
        dig = [res["digests"][i] for i in frames]
        a, b = meta["schedule"][name]
        scenes[name] = {
            "t0": a,
            "t1": b,
            "frames": frames,
            "times": [round(i / fps, 3) for i in frames],
            "digests": dig,
            "hash": _scene_hash(frames, dig),
        }
    old = read_approval(folder)
    approval = {
        "approved_at": now,
        "video": {
            "path": str(rel),
            "sha256": sha256_file(vid),
            "bytes": vid.stat().st_size,
            "written": stamp(vid),
            "streamhash": streamhash(vid),
            "duration": p["duration"],
            "fps": p["fps"],
            "size": f"{p['w']}x{p['h']}",
            "frames": p["frames"],
            "lufs": loud["I"] if loud else None,
            "true_peak": loud["peak"] if loud else None,
        },
        "frames": {"n": n, "algo": man.get("algo"), "sha256": files[C.FRAMES_HASH]},
        "audio": None
        if blocks is None
        else {
            "file": C.MIX_RAW,
            "sha256": files[C.MIX_RAW],
            "blocks": len(blocks["hash"]),
            "block_s": BLOCK_S,
        },
        "qa": None
        if qa_rows is None
        else {
            "file": C.QA_JSON,
            "counts": {
                s: sum(r.status == s for r in qa_rows)
                for s in (C.PASS, C.FIX, C.NOTE, C.NOT_CHECKED)
            },
        },
        "duration": meta["duration"],
        "scenes": scenes,
        "review": rev,
        "overrides": overrides,
        "env": env_now(folder, size, res["fonts"] | meta["fonts"]),
        "files": files,
        "history": [] if old is None else [_summary(old), *old.get("history", [])],
    }
    (new / C.APPROVAL).write_text(json.dumps(approval, indent=1), encoding="utf-8")
    _swap(folder)
    # the diff times the review settled: an undeclared change now approved must not rank as FIX on the next sheet
    retired = _drop_changed(times_file(folder))
    nk = sum(len(v) for v in keys.values())
    print(
        f"APPROVED {rel} (sha256 {approval['video']['sha256'][:12]}, {n} frames, {len(scenes)} scenes, "
        f"{nk} key frames; {_who(approval)})"
    )
    audio = (
        f", {AUDIO_HASH} ({len(blocks['hash'])} blocks of 100 ms), {C.MIX_RAW}"
        if blocks
        else ""
    )
    qa_note = f", {C.QA_JSON}" if qa_rows is not None else ""
    print(
        f"wrote {folder / C.APPROVED}/: {C.APPROVAL}, {C.FRAMES_HASH}, {C.THUMBS}{qa_note}{audio}, {SRC}/ ({', '.join(mods)})"
    )
    if retired:
        print(
            f"retired {retired} diff times from {C.REVIEW_TIMES} (the review covered them)"
        )
    for o in overrides:
        print(f"OVERRIDE recorded: {o['what']} (why: {o['why']})")
    if override and not refuse:
        print("note: --override given but nothing needed overriding; none recorded")
    return 0


def _summary(appr):
    return {
        "approved_at": appr.get("approved_at"),
        "video": {k: (appr.get("video") or {}).get(k) for k in ("path", "sha256")},
        "review": {
            k: (appr.get("review") or {}).get(k) for k in ("verdict", "reviewer")
        },
        "overrides": appr.get("overrides", []),
    }


def _who(appr):
    r = appr.get("review") or {}
    return f"{r.get('verdict', 'no review')} by {r.get('reviewer') or 'an unnamed reviewer'}"


def _overrides(appr):
    return "; ".join(
        f"{o['what']} (why: {o['why']})" for o in appr.get("overrides", [])
    )


# ---- qa.py check: stale approval (Q1301), environment (Q1304), baseline regressions (Q1302) ----


def add_check_args(parser):
    parser.add_argument(
        "--baseline",
        help="qa.json of the approved build (approved/qa.json): Q1302 FIX for every gate that went from PASS to FIX",
    )


def check_rows(ctx):
    """Rows for qa.py check when the working folder holds an approval (none before the first qa.py approve), plus
    Q1302 against --baseline. Nothing here may stop qa.check: any error becomes a NOT CHECKED row of this module's
    own codes, so the approval state can never reject a file by crashing."""
    rows = []
    try:
        appr, problem = load_approval(ctx.workdir)
        if problem:
            fix = "re-approve after a review (qa.py approve --review <reply>); approved/ cannot be trusted as it is"
            rows.append(
                C.not_checked("Q1301", f"{problem}: the approval was not checked", fix)
            )
        elif appr is not None:
            rows += approval_rows(ctx, appr)
    except Exception as e:  # noqa: BLE001 -- approval state must never raise out of qa.check
        rows.append(
            C.not_checked(
                "Q1301",
                f"the approval check stopped: {type(e).__name__}: {e}",
                "fix the cause, then check again",
            )
        )
    if ctx.opts.get("baseline"):
        try:
            rows += baseline_rows(ctx)
        except Exception as e:  # noqa: BLE001 -- the baseline comparison must never raise out of qa.check
            rows.append(
                C.not_checked(
                    "Q1302",
                    f"the baseline check stopped: {type(e).__name__}: {e}",
                    "fix the cause",
                )
            )
    return rows


def approval_rows(ctx, appr):
    """Q1304 NOT CHECKED when the frame size changed; else the approved key frames are redrawn now. A change in
    Python, Pillow, numpy or a font is Q1304 NOT CHECKED only when a key frame moved (a NOTE when none did). Then
    Q1301: the scenes whose key frames changed (a renamed scene in its old slot is matched by its time), and what
    the file under check is: the approved one, the approved picture with new audio, or another picture."""
    folder = ctx.workdir
    size = tuple(appr["env"]["size"][k] for k in SIZE_KEYS)
    sizes = size_changes(appr["env"], size_now(folder))
    if (ctx.w, ctx.h, ctx.fps) != size[:3]:
        sizes.append(
            f"file {ctx.w}x{ctx.h} at {ctx.fps} fps, approved {size[0]}x{size[1]} at {size[2]}"
        )
    if sizes:
        return [_size_row(sizes)]
    env, fps = env_changes(appr["env"]), size[2]
    keys = sorted({i for s in appr["scenes"].values() for i in s["frames"]})
    try:
        now = draw_frames(folder, folder, size, keys)
    except RuntimeError as err:
        fix = "fix the error (python run_all.py proof shows it), then run qa.py check again"
        return [
            C.not_checked(
                "Q1301", f"could not redraw the approved key frames: {err}", fix
            )
        ]
    changed = {}
    for s, v in appr["scenes"].items():
        if bad := [
            i for i, d in zip(v["frames"], v["digests"]) if now["digests"].get(i) != d
        ]:
            changed[s] = bad
    mods = _modules_changed(appr, folder)
    if env and changed:
        return [_env_moved_row(env, f"key frames in {', '.join(changed)}", bool(mods))]
    e = appr["env"]
    rows = [
        _env_same_row(env, "every key frame redraws")
        if env
        else C.row(
            True,
            "Q1304",
            f"environment as approved: Python {e['python']}, Pillow {e['pillow']}, numpy {e['numpy']}, "
            f"{len(e['fonts'])} font files, {size[0]}x{size[1]} at {fps} fps, SS {size[3]}",
            "",
        )
    ]
    old_slots = {s: (v["t0"], v["t1"]) for s, v in appr["scenes"].items()}
    added = [s for s in now["schedule"] if s not in appr["scenes"]]
    removed = [s for s in appr["scenes"] if s not in now["schedule"]]
    # a scene renamed in place: same time slot, so its approved key frames were redrawn at the same frames
    renamed = {
        s: a
        for s in removed
        for a in added
        if tuple(now["schedule"][a]) == tuple(old_slots[s])
    }
    added = [s for s in added if s not in renamed.values()]
    removed = [s for s in removed if s not in renamed]
    stale = [
        renamed.get(s, s) for s in appr["scenes"] if s in changed or s in removed
    ] + added
    src = f"; source changed: {', '.join(mods)}" if mods else ""
    moved = (
        f"; renamed: {', '.join(f'{a} -> {b}' for a, b in renamed.items())}"
        if renamed
        else ""
    )
    same_file = sha256_file(ctx.path) == appr["video"]["sha256"]
    if stale:
        slots = list(
            dict.fromkeys(tuple(now["schedule"].get(s) or old_slots[s]) for s in stale)
        )
        first = (
            min(i for v in changed.values() for i in v) / fps
            if changed
            else slots[0][0]
        )
        detail = [
            f"key frames differ at {', '.join(f'{i / fps:.2f}' for i in v[:4])} s in {renamed.get(s, s)}"
            for s, v in changed.items()
        ]
        detail += [f"{s} added" for s in added] + [f"{s} removed" for s in removed]
        msg = f"STALE APPROVAL: scenes {', '.join(stale)} changed since the approval of {appr['approved_at']}"
        msg += f" ({'; '.join(detail)}{moved}{src})" + (
            "; the file is still the approved one" if same_file else ""
        )
        windows = ",".join(f"{a:g}-{b:g}" for a, b in slots)
        fix = (
            f"re-review those scenes (qa.py diff --expect {windows} writes the triptychs), then record the new "
            "verdict with qa.py approve --review <reply>"
        )
        kw = {
            "t0": min(a for a, _ in slots),
            "t1": max(b for _, b in slots),
            "worst_t": round(first, 3),
        }
        kw |= {
            "item": ", ".join(stale),
            "metric": len(stale),
            "limit": 0,
            "spans": slots,
            "considered": len(appr["scenes"]),
        }
        return [*rows, C.row(False, "Q1301", msg, fix, **kw)]
    ov = _overrides(appr)
    msg = f"approval current: key frames of {len(appr['scenes'])} scenes match the approval of {appr['approved_at']}"
    msg += f" ({_who(appr)})" + (
        "; the file is the approved one (sha256 matches)" if same_file else ""
    )
    msg += (f"; human override recorded: {ov}" if ov else "") + moved + src
    fix = "the override stands until a clean review is approved"
    rows.append(
        C.row(not ov, "Q1301", msg, fix, note=True, considered=len(appr["scenes"]))
    )
    if same_file:
        return rows
    sh = streamhash(ctx.path, ctx.ff)
    if sh is None or appr["video"]["streamhash"] is None:
        fix = "check ffmpeg can decode the file, then run qa.py check again"
        return [
            *rows,
            C.not_checked(
                "Q1301",
                "could not hash the decoded picture of the file or of the approval",
                fix,
            ),
        ]
    if sh == appr["video"]["streamhash"]:
        ks, gain, _ = _audio_change(appr, folder)
        spans = block_runs(ks)
        where = f": {C.MIX_RAW} changed at {_fmt(spans)}{_gain(gain)}" if spans else ""
        msg = f"only the audio changed since approval (decoded video streamhash matches){where}: {AUDIO_ONLY}"
        fix = "check the audio rows of this run; re-approve to bind the new file"
        kw = {
            "worst_t": spans[0][0] if spans else None,
            "item": "audio",
            "spans": spans,
            "metric": len(ks),
        }
        return [*rows, C.row(False, "Q1301", msg, fix, note=True, **kw)]
    return [*rows, _picture_row(appr, folder, fps)]


def _picture_row(appr, folder, fps):
    """Q1301 when the file's decoded picture is not the approved one though every key frame drawn now is. The last
    render's frames.hash tells which: the same digests as approved/frames.hash, so only the encode changed; other
    digests, so the file was rendered from another state of the source, or the change sits between key frames."""
    cur, old = (
        C.read_frame_manifest(folder),
        C.read_frame_manifest(approved_dir(folder)),
    )
    head = "the file's picture is not the approved one (decoded video streamhash differs) though every key frame is"
    if cur is None or old is None:
        return C.row(
            False,
            "Q1301",
            head,
            "run qa.py diff to find the changed frames, then re-review them",
            item="picture",
        )
    if cur["hash"] == old["hash"]:
        msg = f"{head}; the last render's frames.hash matches the approved one, so only the encode changed (CRF, preset, ffmpeg)"
        fix = "re-review the encoded file at the review times (qa.py look), then record it with qa.py approve"
        return C.row(False, "Q1301", msg, fix, item="encode")
    a, b = old["hash"], cur["hash"]
    bad = [
        i
        for i in range(max(len(a), len(b)))
        if i >= len(a) or i >= len(b) or a[i] != b[i]
    ]
    spans = C.merge_spans([i / fps for i in bad], fps)
    msg = (
        f"{head}; the last render's frames differ from the approved ones at {_fmt(spans)} ({len(bad)} frames): it "
        "was rendered from another state of the source, or the change sits between key frames"
    )
    fix = "re-render from the current source (python run_all.py full); if frames still differ, qa.py diff shows where"
    kw = {
        "t0": spans[0][0],
        "t1": spans[-1][1],
        "worst_t": C.worst_of(spans),
        "spans": spans,
        "metric": len(bad),
    }
    return C.row(False, "Q1301", msg, fix, item="picture", **kw)


def _audio_change(appr, folder):
    """(changed 100 ms block indices of mix_raw.wav against the approval, overall gain dB, approved blocks); approved
    blocks is 0 when there is nothing to compare (no audio approved, or a file missing)."""
    adir, mix = approved_dir(folder), Path(folder, C.MIX_RAW)
    ah = Path(adir, AUDIO_HASH)
    if not (appr.get("audio") and ah.exists() and mix.exists()):
        return [], None, 0
    old = json.loads(ah.read_text(encoding="utf-8"))
    ks, gain = audio_change(old, Path(adir, C.MIX_RAW), mix)
    return ks, gain, len(old["hash"])


def _gain(db):
    """The overall gain diff took out, when there was one worth naming."""
    if db is None or abs(db) < 0.01:
        return ""
    return f" (beyond an overall gain of {db:+.2f} dB: audio.write_wav peak-normalises {C.MIX_RAW})"


def _fmt(spans, k=4):
    s = ", ".join(f"{a:.2f}-{b:.2f}" for a, b in spans[:k])
    return s + (f" and {len(spans) - k} more" if len(spans) > k else "") + " s"


def baseline_rows(ctx):
    """Q1302 REGRESSION for each row whose gate (code) was PASS in the baseline and is FIX now; NOT CHECKED for the
    gates that passed in the baseline and made no row in this run (a flag the baseline run had is missing, so their
    regressions could not show). Nothing else is hidden: every gate, file integrity included, still reports its own
    row as usual."""
    path = ctx.opts["baseline"]
    try:
        base = C.read_rows(path)
    except (OSError, ValueError, TypeError) as e:
        fix = "pass the qa.json the approval kept: approved/qa.json"
        return [C.not_checked("Q1302", f"baseline {path} unreadable: {e}", fix)]
    # every row qa.check and the gate modules before this one made (qa_approve runs last in GATE_MODULES)
    now = [r for r in getattr(ctx, "rows", []) if r.code not in OWN]
    if not now:
        msg = "no rows from this run to compare with the baseline (qa.check hands them in ctx.rows)"
        return [
            C.not_checked("Q1302", msg, "run it through qa.py check with --baseline")
        ]
    was = {}
    for r in base:
        if r.code not in OWN:
            was.setdefault(r.code, set()).add(r.status)
    out = [
        C.row(
            False,
            "Q1302",
            f"REGRESSION: {r.code} went from PASS to FIX against the baseline: {r.msg}",
            r.fix,
            t0=r.t0,
            t1=r.t1,
            worst_t=r.worst_t,
            item=r.code,
            metric=r.metric,
            limit=r.limit,
            spans=list(r.spans),
        )
        for r in now
        if r.status == C.FIX
        and C.PASS in was.get(r.code, ())
        and C.FIX not in was[r.code]
    ]
    codes = {r.code for r in now}
    if gone := sorted(c for c, st in was.items() if C.PASS in st and c not in codes):
        msg = (
            f"{len(gone)} gates that passed in the baseline {path} made no row in this run "
            f"({', '.join(gone[:10])}{' ...' if len(gone) > 10 else ''}), so a regression there could not show"
        )
        out.append(
            C.not_checked(
                "Q1302",
                msg,
                "run qa.py check with the flags the baseline had (--scenes . for the text gates)",
                item=", ".join(gone),
            )
        )
    both = len(codes & set(was))
    if not both:
        msg = (
            f"the baseline {path} shares no gate with this run, so nothing was compared"
        )
        return [
            C.not_checked(
                "Q1302", msg, "pass the qa.json the approval kept: approved/qa.json"
            )
        ]
    msg = f"no gate went from PASS to FIX against the baseline {path} ({both} codes compared)"
    return out or [C.row(True, "Q1302", msg, "", considered=both)]


# ---- qa.py diff ----


def parse_expect(s):
    """'2.5-5,10-12.5' -> [(2.5, 5.0), (10.0, 12.5)]: the windows a declared change may touch."""
    out = []
    for part in s.split(","):
        if part.strip():
            a, b = part.split("-")
            out.append((float(a), float(b)))
    return out


def window_of_frame(i, windows, fps):
    """The --expect window that holds frame i, or None: frames frame_of(lo) to frame_of(hi) - 1, the same rule as a
    scene in SCHEDULE, so 2.5-5 declares frames 75 to 149 at 30 fps and the cut frame at 5.00 s is not in it."""
    return next(
        (w for w in windows if C.frame_of(w[0], fps) <= i < C.frame_of(w[1], fps)), None
    )


def window_of_block(k, windows):
    """The --expect window that holds 100 ms audio block k (the one starting at k * 0.1 s), or None."""
    t = k * BLOCK_S
    return next((w for w in windows if w[0] - 1e-6 <= t < w[1] - 1e-6), None)


def _wins(ws):
    return ",".join(f"{lo:g}-{hi:g}" for lo, hi in dict.fromkeys(ws))


def _font(px):
    return ImageFont.load_default(px)


def _shrink(img, k):
    """img made k times smaller; k is a whole factor, so the box filter gives exact block means."""
    return img.convert("RGB").resize((img.width // k, img.height // k), Image.BOX)


def _placeholder(size, text):
    im = Image.new("RGB", size, (60, 60, 60))
    ImageDraw.Draw(im).text((10, 10), text, fill=(255, 255, 255), font=_font(16))
    return im


def triptych(before, after, title, notes, pw=640):
    """One row: before | after | difference, each panel at most pw px on its long side, under two caption lines.
    The difference panel is the after frame dimmed, every changed pixel in magenta, brightened by the adaptive gain
    255 // (largest change) so a one-level change still shows, and kept through the shrink (block max). A side that
    is None has no frame there. Returns (image, share of pixels changed)."""
    ref = after if after is not None else before
    k = max(1, math.ceil(max(ref.size) / pw))
    w, h = ref.width // k, ref.height // k
    share, cap = 1.0, "difference: no frame on one side"
    diff = _placeholder((w, h), "no frame on one side")
    if before is not None and after is not None:
        d = np.abs(
            np.asarray(after.convert("RGB"), np.int32)
            - np.asarray(before.convert("RGB"), np.int32)
        ).max(2)
        mx, share = int(d.max()), float((d > 0).mean())
        gain = 255 // max(1, mx)
        m = d[: h * k, : w * k].reshape(h, k, w, k).max((1, 3))
        out = (np.asarray(_shrink(after, k), np.float32) * 0.3).astype(np.uint8)
        hit = m > 0
        ones = np.full(int(hit.sum()), 255)
        out[hit] = np.stack([ones, np.clip(m[hit] * gain, 0, 255), ones], -1)
        diff = Image.fromarray(out, "RGB")
        cap = (
            f"difference x{gain}: max {mx}/255, {share * 100:.2f} % of pixels"
            if mx
            else "difference: identical"
        )
    panels = [
        _shrink(im, k) if im is not None else _placeholder((w, h), txt)
        for im, txt in ((before, "no approved frame"), (after, "no frame now"))
    ] + [diff]
    gap, strip = 6, 44
    row = Image.new("RGB", (3 * w + 2 * gap, h + strip), (20, 20, 20))
    dr = ImageDraw.Draw(row)
    dr.text(
        (6, 3),
        _fit(dr, title, _font(16), row.width - 12),
        fill=(255, 255, 255),
        font=_font(16),
    )
    for j, (im, txt) in enumerate(zip(panels, [*notes, cap])):
        row.paste(im, (j * (w + gap), strip))
        colour = (255, 120, 255) if j == 2 else (200, 200, 200)
        dr.text(
            (j * (w + gap) + 6, 23),
            _fit(dr, txt, _font(14), w - 12),
            fill=colour,
            font=_font(14),
        )
    return row, share


def _fit(dr, text, font, width):
    """text cut to fit width px (ending '..'), so a caption never runs into the next panel's."""
    while len(text) > 2 and dr.textlength(text, font=font) > width:
        text = text[:-3] + ".."
    return text


def _pages(rows, max_h=1800):
    """Triptych rows stacked into pages at most max_h px tall (a model reads each page as one image)."""
    pages, cur = [], []
    for r in rows:
        if cur and sum(x.height for x in cur) + r.height > max_h:
            pages.append(cur)
            cur = []
        cur.append(r)
    pages += [cur] if cur else []
    out = []
    for pg in pages:
        sheet = Image.new(
            "RGB", (max(r.width for r in pg), sum(r.height for r in pg)), (30, 30, 30)
        )
        y = 0
        for r in pg:
            sheet.paste(r, (0, y))
            y += r.height
        out.append(sheet)
    return out


def _before_frames(folder, size, frames, tmp, procs):
    """{i: png} of the approved frames redrawn from approved/src in their own workers, and a caption saying how,
    and whether any redraw differs from the approved digest (the snapshot then misses something the build reads).
    None when the snapshot cannot be drawn: the caller falls back to the approved thumbs."""
    adir = approved_dir(folder)
    old = C.read_frame_manifest(adir)
    save = {i: Path(tmp, f"b{i}.png") for i in frames}
    try:
        res = draw_frames(folder, Path(adir, SRC), size, frames, save, procs)
    except RuntimeError as e:
        print(
            f"warning: approved/{SRC} could not be drawn ({e}); triptychs use the approved thumbs"
        )
        return None, f"before: approved thumb (approved/{SRC} did not draw)"
    off = [i for i in frames if res["digests"][i] != old["hash"][i]]
    if off:
        print(
            f"warning: approved/{SRC} redraws {len(off)} frames unlike the approval (first {off[0] / size[2]:.2f} s)"
        )
        return (
            save,
            f"before: approved/{SRC}, NOT the approved pixels ({len(off)} frames)",
        )
    return save, f"before: approved/{SRC}, hash matches"


def _write_sheets(review, named):
    """Replace an earlier diff's sheets with these {name: image}: old diff_*.jpg are removed where they can be, and
    a name another program holds open gets a free numbered one instead, so a viewer left open never stops the run."""
    review.mkdir(exist_ok=True)
    held = []
    for f in review.glob("diff_*.jpg"):
        try:
            f.unlink()
        except OSError:
            held.append(f.name)
    if held:
        print(
            f"warning: {len(held)} sheets from an earlier diff are open in another program and stay: {', '.join(held)}"
        )
    written = []
    for name, im in named.items():
        p, k = review / name, 1
        while p.name in held or p.exists():
            p, k = review / f"{Path(name).stem}-{k}.jpg", k + 1
        im.save(p, quality=90)
        written.append(p)
    return written


def _frame_rows(spans, kw, what, declared, fps):
    """Q1303 rows for frame spans: FIX for spans of undeclared frames, NOTE for spans of declared ones."""
    rows = []
    for t0, t1, ws in spans:
        if declared:
            msg = f"declared change: {what(t0, t1)} inside --expect {_wins(ws)}"
            rows.append(
                C.row(
                    False,
                    "Q1303",
                    msg,
                    "re-review the triptychs in review/, then the encoded file 0.5 s either side",
                    note=True,
                    **kw(t0, t1),
                )
            )
        else:
            # windows end exclusive, like a scene: one frame past the last changed one
            fix = f"if intended, declare it (--expect {t0:.2f}-{t1 + 1 / fps:.2f}) and re-review it; if not, find what moved it"
            rows.append(
                C.row(
                    False,
                    "Q1303",
                    f"undeclared change: {what(t0, t1)} outside --expect",
                    fix,
                    **kw(t0, t1),
                )
            )
    return rows


def _spans_of(frames, fps, windows=None):
    """[(t0, t1, windows)] runs of frames (2-frame pad, as merge_spans), with the --expect windows each touches."""
    out = []
    for t0, t1 in C.merge_spans([i / fps for i in frames], fps, pad_frames=2):
        ws = (
            [
                window_of_frame(i, windows, fps)
                for i in frames
                if t0 - 1e-6 <= i / fps <= t1 + 1e-6
            ]
            if windows
            else []
        )
        out.append((t0, t1, [w for w in ws if w]))
    return out


def diff(folder=".", expect=(), procs=None, out="review"):
    """Rows for every frame and 100 ms audio block that changed since the approval: Q1303 FIX for those outside every
    --expect window and for a window that saw no change, NOTE inside one, PASS when nothing changed; Q1304 or NOT
    CHECKED when they cannot be compared. Everything is drawn and compared before review/ and review_times.json are
    touched, so a diff that cannot finish leaves the last one's triptychs and times as they were."""
    folder, t_start, windows = Path(folder), time.perf_counter(), list(expect)
    appr, problem = load_approval(folder)
    if problem or appr is None:
        msg = (
            f"{problem}: nothing was compared"
            if problem
            else "no approved set in approved/: nothing to compare against"
        )
        return [
            C.not_checked(
                "Q1303",
                msg,
                "run qa.py approve --review <reply> on the reviewed build first",
            )
        ]
    adir = approved_dir(folder)
    old = C.read_frame_manifest(adir)
    size = tuple(appr["env"]["size"][k] for k in SIZE_KEYS)
    if sizes := size_changes(appr["env"], size_now(folder)):
        return [_size_row(sizes)]
    env = env_changes(appr["env"])
    fps, n_old, k = size[2], old["n"], procs or default_procs()
    mods = _modules_changed(appr, folder)
    print(f"source changed since approval: {', '.join(mods) or 'none'}")
    try:
        now = draw_frames(folder, folder, size, range(n_old), procs=k)
        n_now = C.frame_of(now["duration"], fps)
        if n_now > n_old:
            now["digests"].update(
                draw_frames(folder, folder, size, range(n_old, n_now), procs=k)[
                    "digests"
                ]
            )
    except RuntimeError as e:
        fix = "fix the error (python run_all.py proof shows it), then diff again"
        return [C.not_checked("Q1303", f"could not draw the current frames: {e}", fix)]
    n, new = max(n_old, n_now), now["digests"]
    changed = [
        i for i in range(n) if i >= n_old or i >= n_now or new[i] != old["hash"][i]
    ]
    rows = []
    if env:
        if changed:
            return [_env_moved_row(env, f"{len(changed)} of {n} frames", bool(mods))]
        rows.append(_env_same_row(env, f"all {n} frames redraw"))
    sf = scene_frames(now["schedule"], fps, n)
    touched = {scene_of(i, sf) for i in changed}
    # global: over 30 percent of the film and more than one scene (one scene of a three-scene film is 33 percent),
    # or the film's only scene
    is_global = len(changed) > GLOBAL * n and (len(touched) > 1 or len(sf) == 1)
    changed_set = set(changed)
    ks, gain, n_blocks = [], None, 0
    if appr.get("audio"):
        ks, gain, n_blocks = _audio_change(appr, folder)
        if not n_blocks:
            fix = "rebuild the mix (python run_all.py full), then diff again"
            msg = f"the approval has audio but {C.MIX_RAW} or approved/{AUDIO_HASH} is missing: audio not compared"
            rows.append(C.not_checked("Q1303", msg, fix, item="audio"))
        else:  # frames come from the source now; the mix only from the last render
            print(
                f"audio: {C.MIX_RAW} as the last render wrote it (diff redraws frames, it does not rebuild the mix)"
            )
    # each changed frame and block is declared when an --expect window holds it, frame by frame (end exclusive)
    dec_f = [i for i in changed if window_of_frame(i, windows, fps)]
    und_f = [i for i in changed if not window_of_frame(i, windows, fps)]
    dec_k = [b for b in ks if window_of_block(b, windows)]
    und_k = [b for b in ks if not window_of_block(b, windows)]
    f_dec, f_und = _spans_of(dec_f, fps, windows), _spans_of(und_f, fps)
    spans = sorted([(a, b) for a, b, _ in f_dec + f_und])

    def in_span(frames, t0, t1):
        return [i for i in frames if t0 - 1e-6 <= i / fps <= t1 + 1e-6]

    def names(t0, t1):
        return ", ".join(
            dict.fromkeys(scene_of(i, sf) for i in in_span(changed, t0, t1))
        )

    why = {}  # frame -> why the reviewer must see it
    if is_global:  # first, middle and last of one film-long span say nothing: sample the film and every cut
        step = max(1, round(now["duration"] / 12))
        pick = {C.frame_of(t, fps) for t in range(0, math.ceil(now["duration"]), step)}
        for a, _ in now["schedule"].values():
            if a > 0:
                pick |= {C.frame_of(a, fps) - 1, C.frame_of(a, fps)}
        pick = sorted(i for i in pick if 0 <= i < n)
        why = {
            i: "global change"
            if i in changed_set
            else "global change: sampled, unchanged here"
            for i in pick
        }
        print(
            f"global change: {len(changed)} of {n} frames changed ({len(changed) / n * 100:.0f} percent) in "
            f"{len(touched)} of {len(sf)} scenes: sampled every {step} s plus both sides of every cut ({len(pick)} frames)"
        )
    else:
        for t0, t1 in spans:
            f0, f1 = C.frame_of(t0, fps), C.frame_of(t1, fps)
            for i in (f0, (f0 + f1) // 2, f1):
                why.setdefault(
                    i, f"frames changed {t0:.2f}-{t1:.2f} s in {names(t0, t1)}"
                )
        pick = sorted(why)

    shares, named = {}, {}
    if (
        pick
    ):  # every picture is drawn and composed before anything in review/ is touched
        with tempfile.TemporaryDirectory() as tmp:
            after = {i: Path(tmp, f"a{i}.png") for i in pick if i < n_now}
            try:
                draw_frames(folder, folder, size, list(after), after, k)
            except RuntimeError as e:
                return [
                    C.not_checked(
                        "Q1303",
                        f"could not draw the changed frames: {e}",
                        "fix it, then diff again",
                    )
                ]
            before, note = _before_frames(
                folder, size, [i for i in pick if i < n_old], tmp, k
            )
            thumbs = np.load(Path(adir, C.THUMBS)) if before is None else None
            trip = []
            for i in pick:
                a = Image.open(after[i]) if i in after else None
                # no snapshot drawing: the approved thumbs, and the after frame thumbed the same way to compare
                if before is None:
                    b = Image.fromarray(thumbs[i]) if i < n_old else None
                    a = Image.fromarray(C.thumb(a)) if a is not None else None
                    b, a = (
                        x.convert("RGB").resize(size[:2], Image.NEAREST) if x else None
                        for x in (b, a)
                    )
                else:
                    b = Image.open(before[i]) if i < n_old else None
                title = f"t={i / fps:.2f} s (frame {i}): {why[i]}"
                row, shares[i] = triptych(
                    b,
                    a,
                    title,
                    [note, "after: scenes.py now"],
                    480 if is_global else 640,
                )
                trip.append((i, row))
        if is_global:
            named = {
                f"diff_global_{j:02d}.jpg": sheet
                for j, sheet in enumerate(_pages([r for _, r in trip]), 1)
            }
        else:
            named = {f"diff_t{i / fps:06.2f}.jpg": r for i, r in trip}

    def frames_kw(t0, t1):
        mine = in_span(pick, t0, t1)
        worst = max(mine, key=lambda i: shares.get(i, 0)) / fps if mine else t0
        nf = len(in_span(changed, t0, t1))
        return {
            "t0": t0,
            "t1": t1,
            "worst_t": round(worst, 3),
            "item": names(t0, t1),
            "metric": nf,
            "spans": [(t0, t1)],
        }

    def frames_what(t0, t1):
        nf, extra = (
            len(in_span(changed, t0, t1)),
            ", global change" if is_global else "",
        )
        return f"frames changed at {t0:.2f}-{t1:.2f} s in {names(t0, t1)} ({nf} frames{extra})"

    rows += _frame_rows(f_und, frames_kw, frames_what, False, fps)
    rows += _frame_rows(f_dec, frames_kw, frames_what, True, fps)
    big = " (a global audio change)" if n_blocks and len(ks) > GLOBAL * n_blocks else ""
    tail = f"; frames unchanged: {AUDIO_ONLY}" if not changed else ""
    for blocks, declared in ((und_k, False), (dec_k, True)):
        for t0, t1 in block_runs(blocks):
            what = (
                f"audio changed at {t0:.2f}-{t1:.2f} s in {C.MIX_RAW}{big}{_gain(gain)}"
            )
            kw = {
                "t0": t0,
                "t1": t1,
                "worst_t": t0,
                "item": "audio",
                "spans": [(t0, t1)],
            }
            if declared:
                ws = [
                    window_of_block(b, windows)
                    for b in blocks
                    if t0 - 1e-6 <= b * BLOCK_S < t1 - 1e-6
                ]
                msg = f"declared change: {what} inside --expect {_wins(ws)}{tail}"
                rows.append(
                    C.row(
                        False,
                        "Q1303",
                        msg,
                        "check the audio rows of qa.py check on the new file",
                        note=True,
                        **kw,
                    )
                )
            else:
                fix = "if intended, declare it with --expect; if not, look for what moved it (a shared random state shifts every later sound)"
                rows.append(
                    C.row(
                        False,
                        "Q1303",
                        f"undeclared change: {what} outside --expect{tail}",
                        fix,
                        **kw,
                    )
                )
    # a declared window where nothing changed: the fix it stands for did not land
    met = {window_of_frame(i, windows, fps) for i in dec_f} | {
        window_of_block(b, windows) for b in dec_k
    }
    for lo, hi in windows:
        if (lo, hi) not in met:
            msg = f"declared change not found: --expect {lo:g}-{hi:g} saw no frame or audio change since the approval"
            fix = "check the edit took effect (the right scene, the right file, saved), or drop the window"
            rows.append(
                C.row(
                    False,
                    "Q1303",
                    msg,
                    fix,
                    t0=lo,
                    t1=hi,
                    item=f"--expect {lo:g}-{hi:g}",
                )
            )
    if not changed and not ks:
        audio = f", {n_blocks} audio blocks" if n_blocks else ""
        quiet = (
            ""
            if appr.get("audio")
            else "; audio not compared: the approval has no mix_raw.wav"
        )
        msg = f"no frame{' or audio block' if n_blocks else ''} changed since the approval ({n} frames{audio} compared{quiet})"
        rows.append(C.row(True, "Q1303", msg, "", considered=n))

    # every changed time for the reviewer, the reason led by the code; status FIX for an undeclared frame or block,
    # NOTE for a declared one or an unchanged sample, so the key sheet ranks undeclared changes first
    def entry(t, state, what):
        st = C.FIX if state == "undeclared" else C.NOTE
        why_t = f"Q1303 {state} change since approval: {what}"
        return {
            "t": round(t, 3),
            "why": why_t,
            "kind": "changed",
            "code": "Q1303",
            "status": st,
        }

    entries = []
    for i in pick:
        state = (
            "sampled"
            if i not in changed_set
            else "declared"
            if window_of_frame(i, windows, fps)
            else "undeclared"
        )
        entries.append(entry(i / fps, state, why[i]))
    for blocks, state in ((und_k, "undeclared"), (dec_k, "declared")):
        for t0, t1 in block_runs(
            blocks
        ):  # snapped to frames, so qa.py look shows exactly these
            for t in sorted(
                {C.snap(t0, fps), C.snap((t0 + t1) / 2, fps), C.snap(t1 - BLOCK_S, fps)}
            ):
                entries.append(entry(t, state, f"audio changed {t0:.2f}-{t1:.2f} s"))
    # only now, with every result in hand, the last diff's sheets and times are replaced
    written = (
        _write_sheets(Path(folder, out), named)
        if named or Path(folder, out).exists()
        else []
    )
    tf = times_file(folder)
    _drop_changed(tf)
    if entries:
        C.add_review_times(entries, tf)
    if written:
        print(
            f"wrote {len(written)} {'sheets' if is_global else 'triptychs'}: {', '.join(str(p) for p in written)}"
        )
    if entries:
        print(f"added {len(entries)} times to {C.REVIEW_TIMES} (kind changed)")
    print(
        f"diff took {time.perf_counter() - t_start:.1f} s ({n} frames drawn on {k} processes)"
    )
    return rows


def _diff_verdict(rows):
    """The DIFF line from the rows: what changed, never more than they say."""
    code = C.exit_code(rows)
    if code == 2:
        return "DIFF: NOT CHECKED (could not compare; this says nothing about whether the build changed)"
    fix = [r for r in rows if r.status == C.FIX and r.code == "Q1303"]
    unmet = [r for r in fix if (r.item or "").startswith("--expect")]
    if code == 1:
        und = len(fix) - len(unmet)
        parts = [f"{und} undeclared change{'s' * (und != 1)}"] * bool(und)
        parts += [
            f"{len(unmet)} --expect window{'s' * (len(unmet) != 1)} saw no change"
        ] * bool(unmet)
        return f"DIFF: FIX ({'; '.join(parts) or 'see the FIX rows'})"
    if any(r.status == C.NOTE and r.code == "Q1303" for r in rows):
        return "DIFF: CHANGED, every change declared with --expect (re-review each NOTE above)"
    return "DIFF: SAME as the approval"


# ---- qa.py verify ----


def verify(folder=".", video=None):
    """Re-hash a file (default: the approved one) against approval.json: 0 same, 1 differs, 2 cannot compare."""
    appr, problem = load_approval(folder)
    if problem or appr is None:
        print(
            f"VERIFY: NOT CHECKED ({problem or 'no approval in approved/: run qa.py approve first'})"
        )
        return 2
    vid = Path(video) if video else Path(folder, appr["video"]["path"])
    if not vid.exists():
        print(f"VERIFY: NOT CHECKED ({vid} not found)")
        return 2
    sha, a = sha256_file(vid), appr["video"]
    if sha == a["sha256"]:
        print(
            f"VERIFY: SAME {vid} is the approved file (sha256 {sha[:12]}, approved {appr['approved_at']}, {_who(appr)})"
        )
        if ov := _overrides(appr):
            print(f"human override recorded: {ov}")
        return 0
    sh = streamhash(vid)
    pic = (
        "its picture could not be decoded"
        if sh is None
        else "its picture is identical (decoded video streamhash matches): only the audio or the container changed"
        if sh == a["streamhash"]
        else "its picture differs too (decoded video streamhash differs)"
    )
    print(
        f"VERIFY: DIFFERS {vid} is not the approved file (sha256 {sha[:12]}, approved {a['sha256'][:12]}); {pic}"
    )
    return 1


# ---- the subcommands qa.py adds ----


def _guard(f, label):
    """A subcommand that turns any error into its label and exit 2, never a traceback with exit 1, which diff and
    verify use for 'differs'."""

    def run(a):
        try:
            return f(a)
        except Exception as e:  # noqa: BLE001 -- exit 1 means 'differs' or 'refused'; a crash must read as 2
            print(f"{label} ({type(e).__name__}: {e})")
            return 2

    return run


def add_cli(sub):
    ap = sub.add_parser(
        "approve",
        help="record the reviewed build in approved/: hashes, source snapshot, QA rows, environment, the verdict",
    )
    ap.add_argument(
        "--scenes",
        default=".",
        help="the working folder (scenes.py, frames.hash, the video)",
    )
    ap.add_argument(
        "--review", help="file holding the reviewer's reply verbatim (REVIEW PASS ...)"
    )
    ap.add_argument(
        "--video",
        help="the reviewed file in the folder (default: run_all.py's OUT, else out.mp4)",
    )
    ap.add_argument(
        "--reviewer", help="reviewer id, when the reply has no 'reviewer:' line"
    )
    ap.add_argument(
        "--override",
        help="approve despite a refusal; the reason is kept and shown by qa.py check",
    )
    ap.add_argument("--procs", type=int)
    run = _guard(
        lambda a: approve(a.scenes, a.review, a.video, a.reviewer, a.override, a.procs),
        "CANNOT APPROVE",
    )
    ap.set_defaults(func=run)
    df = sub.add_parser(
        "diff",
        help="frames and 100 ms audio blocks changed since the approval, triptychs in review/ (exit 0 same or all "
        "declared, 1 an undeclared change or an --expect window that saw none, 2 could not compare)",
    )
    df.add_argument("--scenes", default=".", help="the working folder")
    df.add_argument(
        "--expect",
        type=parse_expect,
        default=[],
        help="declared change windows t0-t1[,t0-t1 ...] in s",
    )
    df.add_argument(
        "--procs", type=int, help=f"draw workers (default {default_procs()})"
    )
    df.set_defaults(func=_diff_cmd)
    vf = sub.add_parser(
        "verify",
        help="re-hash a file against the approval (exit 0 same, 1 differs, 2 no approval)",
    )
    vf.add_argument(
        "video",
        nargs="?",
        help="default: the approved file; or the path a DELIVERED line printed",
    )
    vf.add_argument(
        "--scenes", default=".", help="the working folder holding approved/"
    )
    vf.set_defaults(
        func=_guard(lambda a: verify(a.scenes, a.video), "VERIFY: NOT CHECKED")
    )


def _diff_cmd(a):
    try:
        rows = diff(a.scenes, a.expect, a.procs)
    except Exception as e:  # noqa: BLE001 -- exit 1 means an undeclared change; a crash must read as 2
        rows = [
            C.not_checked(
                "Q1303",
                f"diff stopped: {type(e).__name__}: {e}",
                "fix the cause, then diff again",
            )
        ]
    for r in rows:
        print(C.line(r))
    print(_diff_verdict(rows))
    return C.exit_code(rows)


# a draw worker: python qa_approve.py _draw <job.json> (qa.py runs everything else)
if __name__ == "__main__":
    if sys.argv[1:2] != ["_draw"]:
        sys.exit("run this through qa.py: qa.py approve | diff | verify")
    _worker(sys.argv[2])
