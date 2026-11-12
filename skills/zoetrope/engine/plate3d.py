# plate3d.py : true 3D in a video, as a plate. Blender (the bpy wheel: Cycles, path traced on the GPU) renders a
# stage script (stage.py, written with stage3d.py's helpers) to one image per frame in its own Python 3.13 uv
# environment; scenes.py then reads those frames like footage with Plate.frame(t), so draw(t) stays pure and every
# gate measures the finished picture. Rendering 3D ahead of the 2D pass is how film compositing works; doing it for
# a code-made video is lemo-opuscar's idea (lemomo-ai/lemo-opuscar TECHNIQUE.md section 9, three.js in a headless
# browser, MIT, read 2026-11-10; no code taken).
#   python plate3d.py fetch                             download Blender 5.2.3 LTS as a module (324 MB, GPL-3.0)
#   python plate3d.py render stage.py --quality proof   every frame at half size, for the proof (about 0.5 s each)
#   python plate3d.py render stage.py                   final quality (about 3.3 s a 1080p frame on an RTX 4070)
#   python plate3d.py check [--final]                   what run_all.py asks before it draws: stale or draft plates
#   python plate3d.py info                              each plate in plates/: frames, quality, seconds
#   python plate3d.py run stage.py <args>               run the stage script in Blender's Python (a measurement)
# render also takes --name (plates/<name>, default main), --frames A-B and --stills T,T (a few frames to look at).
# A render that was stopped picks up where it stopped: frames already on disk are kept while the stage is unchanged.
import argparse
import ast
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image

import engine as E

# Blender as a Python module, in its own uv environment like the voice engines: bpy 5.2.3 has wheels for Python
# 3.13 only. GPL-3.0-or-later: stage3d.py and every stage.py call its API, so they could only ever be shared under
# GPL-compatible terms (this repo is MIT, which is).
PYTHON = "3.13"
PACKAGES = ("bpy==5.2.3",)
BLENDER_DIR = Path(
    os.environ.get("ZOETROPE_BLENDER")
    or Path.home() / ".cache" / "zoetrope" / "blender"
)
PLATES = "plates"
LOCK = "render.lock"  # in a plate folder while a render is writing it
QUALITIES = ("proof", "final")
# print one progress line per this many frames. No clock is read in this file: scenes.py imports it, and the lint
# (Q1202) follows that import; the seconds in a progress line are the ones Blender's side measured.
EVERY = 24


def _uv(*tail):
    with_ = [x for p in PACKAGES for x in ("--with", p)]
    return ["uv", "run", "--no-project", "--python", PYTHON, *with_, *tail]


def _fetched():
    """The note fetch() leaves once this pin has imported here. uv keeps no copy of a wheel this large that an
    offline run can find (uv 0.13.6, 2026-11-10), so the cache itself cannot be asked."""
    return BLENDER_DIR / f"{PACKAGES[0].replace('==', '-')}.txt"


def missing():
    """What is not ready, by name (empty when a plate can render)."""
    if not shutil.which("uv"):
        return ["uv (winget install astral-sh.uv)"]
    if _fetched().is_file():
        return []
    return [
        f"Blender as a Python module ({PACKAGES[0]}, 324 MB): python plate3d.py fetch"
    ]


def fetch():
    """Download the Blender module into the uv cache (nothing is installed globally) and note that it imports.
    Exit 0 when it does."""
    if not shutil.which("uv"):
        print("not ready: uv (winget install astral-sh.uv)")
        return 1
    r = subprocess.run(
        _uv("python", "-c", "import bpy; print(bpy.app.version_string)"),
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    if r.returncode:
        print(r.stderr.strip()[-600:])
        return r.returncode
    version = r.stdout.strip().splitlines()[-1]
    BLENDER_DIR.mkdir(parents=True, exist_ok=True)
    _fetched().write_text(version, encoding="utf-8")
    print(f"have Blender {version} ({PACKAGES[0]})")
    return 0


def _files(root, dotted):
    """Where a dotted module name could live under root: a/b.py, a/b/__init__.py, and each package above it."""
    parts, out = dotted.split("."), []
    for k in range(1, len(parts) + 1):
        base = root.joinpath(*parts[:k])
        out += [base.with_suffix(".py"), base / "__init__.py"]
    return out


def sources(stage):
    """The stage script and every local module it imports, however deep (stage3d.py, a shared beats.py, a module
    inside a package beside it): the Python files whose bytes decide what the plate shows. A font or a data file
    the stage reads is not among them: render again after changing one."""
    stage = Path(stage)
    root, seen, todo = stage.parent, [], [stage]
    while todo:
        p = todo.pop()
        if p in seen or not p.is_file():
            continue
        seen.append(p)
        for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                # a relative import starts at the importing file's folder; "from pkg import beats" may name a
                # module (pkg/beats.py) as well as a name inside pkg
                base = ".".join(p.parent.relative_to(root).parts) if node.level else ""
                mod = ".".join(x for x in (base, node.module or "") if x)
                names = ([mod] if mod else []) + [
                    ".".join(x for x in (mod, a.name) if x) for a in node.names
                ]
            else:
                continue
            todo += [f for n in names for f in _files(root, n)]
    return sorted(seen)


def key(stage):
    """What makes a plate: the bytes of its sources and the Blender pin."""
    stage = Path(stage)
    h = hashlib.sha256(repr(PACKAGES).encode())
    for p in sources(stage):
        h.update(p.relative_to(stage.parent).as_posix().encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def _meta(folder):
    p = Path(folder, "plate.json")
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def render(stage="stage.py", name="main", quality="final", frames=None, stills=None):
    """Render plates/<name> from the stage script in the Blender environment. Frames from another source or another
    quality are deleted first, so a plate never mixes two; frames of this one are kept, so a stopped render resumes.
    Exit code of the render."""
    stage, out = Path(stage), Path(PLATES, name)
    if not stage.is_file():
        print(f"no {stage} here: write the stage script first (references/plates.md)")
        return 1
    if miss := missing():
        print("not ready: " + "; ".join(miss))
        return 1
    out.mkdir(parents=True, exist_ok=True)
    lock = out / LOCK
    try:
        # one render per plate: a second one would delete the first one's frames, or mix its own in with them
        with lock.open("x", encoding="utf-8") as f:
            f.write(f"{stage.as_posix()} {quality}")
    except FileExistsError:
        print(
            f"{out.as_posix()} is being rendered ({lock.read_text(encoding='utf-8').strip()}): wait for it, or use "
            f"another --name. If that render is gone, delete {lock.as_posix()}"
        )
        return 1
    try:
        return _render(stage, out, quality, frames, stills)
    finally:
        lock.unlink(missing_ok=True)


def _render(stage, out, quality, frames, stills):
    want, stamp = f"{key(stage)} {quality}", out / "plate.key"
    if not stamp.is_file() or stamp.read_text(encoding="utf-8") != want:
        for p in (*out.glob("*.jpg"), out / "plate.json"):
            p.unlink(missing_ok=True)
        stamp.write_text(want, encoding="utf-8")
    args = ["--out", str(out), "--quality", quality, "--key", want.split()[0]]
    args += ["--frames", frames] if frames else []
    args += ["--stills", stills] if stills else []
    log, n = out / "render.log", 0
    with (
        log.open("a", encoding="utf-8", errors="backslashreplace") as keep,
        subprocess.Popen(
            _uv("python", str(stage), "--", *args),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="backslashreplace",
            # the stage prints paths: without this a piped Windows console encodes them as cp1252
            env={**os.environ, "PYTHONUTF8": "1"},
        ) as proc,
    ):
        for line in proc.stdout:
            keep.write(line)
            if line.startswith("plate "):
                n += 1
                if n % EVERY == 1:
                    print(line.strip(), flush=True)
            elif line.startswith("PLATE "):
                print(line.strip(), flush=True)
    if proc.returncode:
        tail = log.read_text(encoding="utf-8").splitlines()[-25:]
        print(
            f"the render failed (exit {proc.returncode}); the end of {log.as_posix()}:"
        )
        for line in tail:
            print(line)
        return proc.returncode
    meta = _meta(out)
    if meta is None or meta.get("key") != want.split()[0]:
        print(
            f"{stage} ran but wrote no plate.json for this render: it must end with "
            'S3.run(build, ...) under if __name__ == "__main__":'
        )
        return 1
    meta["stage"] = stage.as_posix()
    (out / "plate.json").write_text(json.dumps(meta), encoding="utf-8")
    return 0


def run(stage, args=()):
    """Run a stage script in the Blender environment with its own arguments and show what it prints: for a
    measurement on the rig that needs no render (the kit's `stage.py contact`). Exit code of the script."""
    if miss := missing():
        print("not ready: " + "; ".join(miss))
        return 1
    r = subprocess.run(
        _uv("python", str(stage), *args),
        stdin=subprocess.DEVNULL,
        env={**os.environ, "PYTHONUTF8": "1"},
        check=False,
    )
    return r.returncode


def _frames(folder):
    """The frame numbers on disk in a plate folder."""
    return {int(p.stem[2:]) for p in Path(folder).glob("f_*.jpg")}


def used(scenes="scenes.py"):
    """The plates a build draws from: the names in every Plate(...) call in its scenes.py, read from the source
    without running it (Plate() with no name is "main"). Empty for a 2D build."""
    p = Path(scenes)
    if not p.is_file():
        return set()
    names = set()
    for node in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
        f = getattr(node, "func", None)
        if isinstance(node, ast.Call) and "Plate" in (
            getattr(f, "id", None),
            getattr(f, "attr", None),
        ):
            first = node.args[0] if node.args else None
            named = next((k.value for k in node.keywords if k.arg == "name"), first)
            if named is None:
                names.add("main")
            elif isinstance(named, ast.Constant) and isinstance(named.value, str):
                names.add(named.value)
    return names


def check(final=False, folder=PLATES, scenes="scenes.py"):
    """Why a build must not draw yet, one line per plate its scenes.py uses, each ending with the command that
    clears it (empty when every one is ready, or the video uses none): a plate not rendered, still being rendered,
    older than its stage script, with frames missing, or, for the full render, of proof quality. run_all.py refuses
    on any line, so a draft plate cannot reach a delivered file. Other folders under plates/ (stills rendered to
    look at under another name) are nobody's business here."""
    out = []
    for name in sorted(used(scenes)):
        d = Path(folder, name)
        m = _meta(d)
        if (d / LOCK).is_file():
            out.append(
                f"{folder}/{name} is being rendered ({LOCK} is there): wait for it"
            )
            continue
        if m is None:
            what = (
                "has no plate.json (a render that did not finish)"
                if (d / "plate.key").is_file()
                else "is not rendered"
            )
            out.append(
                f"{folder}/{name} {what}: python plate3d.py render stage.py --name {name} --quality proof"
            )
            continue
        stage = m.get("stage", "stage.py")
        redo = f"python plate3d.py render {stage} --name {name}"
        gone = sorted(set(range(m["frames"])) - _frames(d))
        if not Path(stage).is_file():
            out.append(f"{folder}/{name}: its stage script {stage} is not here")
        elif m["key"] != key(stage):
            out.append(
                f"{folder}/{name} is older than {stage} (or a module it imports): {redo} --quality {m['quality']}"
            )
        elif gone:
            out.append(
                f"{folder}/{name} lacks {len(gone)} of {m['frames']} frames (first: {gone[0]}): "
                f"{redo} --quality {m['quality']}"
            )
        elif final and m["quality"] != "final":
            out.append(
                f"{folder}/{name} is a {m['quality']} render ({m['rendered'][0]}x{m['rendered'][1]}, "
                f"{m['samples']} samples): {redo}"
            )
    return out


@lru_cache(maxsize=6)
def _read(path, size):
    with Image.open(path) as im:
        im = im.convert("RGB")
        return im if im.size == size else im.resize(size, Image.LANCZOS)


class Plate:
    """A rendered plate for scenes.py: PLATE = plate3d.Plate("main") at module level, then PLATE.frame(t) inside
    draw(t) gives that moment's 3D picture as an RGBA canvas to draw type and graphics on."""

    def __init__(self, name="main", folder=PLATES):
        self.name, self.dir = name, Path(folder, name)
        m = _meta(self.dir)
        if m is None:
            raise FileNotFoundError(
                f"{self.dir.as_posix()} has no plate.json: python plate3d.py render stage.py --name {name} "
                "--quality proof"
            )
        self.fps, self.n, self.quality, self.size = (
            m["fps"],
            m["frames"],
            m["quality"],
            tuple(m["size"]),
        )
        self.duration, self.tracks = self.n / self.fps, m.get("tracks", {})
        w, h = self.size
        if abs(w * E.H - h * E.W) > max(
            w, h
        ):  # the same shape, to within a pixel of rounding
            raise ValueError(
                f"{self.dir.as_posix()} was rendered for {w}x{h} and this build is {E.W}x{E.H}: set the stage "
                "script's size to the video's and render the plate again"
            )

    def need(self, duration):
        """Fail early when the plate is shorter than the video it is in (call once, after compile_schedule)."""
        if self.duration + 0.5 / self.fps < duration:
            raise ValueError(
                f"{self.dir.as_posix()} is {self.duration:.2f} s and the video is {duration:.2f} s: set the stage "
                "script's dur to the video's and render the plate again"
            )

    def index(self, t):
        """The plate frame shown at time t: the last one that has started. At the video's own fps that is frame
        t x fps; a plate at half the video's fps holds each frame for two video frames (on twos), from the frame its
        pose is for, so a landing posed for a cue's time is seen on the cue and never a frame early."""
        return min(self.n - 1, max(0, math.floor(t * self.fps + 1e-6)))

    def frame(self, t):
        """The plate at time t as a new RGBA image of the canvas size (W x SS, H x SS)."""
        p = self.dir / f"f_{self.index(t):06d}.jpg"
        if not p.is_file():
            raise FileNotFoundError(
                f"{p.as_posix()} is not rendered: python plate3d.py render stage.py --name {self.name}"
            )
        return _read(str(p), (E.W * E.SS, E.H * E.SS)).convert("RGBA")

    def at(self, track, t):
        """Where a tracked 3D point (Stage.track in the stage script) is on the canvas at time t: (x, y), or None
        while it is behind the camera. Draw a caption, an arrow or a counter there and it follows the object."""
        x, y, depth = self.tracks[track][self.index(t)]
        if depth <= 0:
            return None
        return x * E.W * E.SS / self.size[0], y * E.H * E.SS / self.size[1]


def info(folder=PLATES):
    rows = [
        (d.name, _meta(d), len(list(d.glob("f_*.jpg"))))
        for d in sorted(Path(folder).glob("*"))
        if d.is_dir()
    ]
    for name, m, have in rows:
        if m is None:
            print(f"{name}: {have} frames, no plate.json (not finished)")
            continue
        each = (
            f"{m['per_frame']} s a frame"
            if m.get("per_frame")
            else "nothing rendered in the last run"
        )
        print(
            f"{name}: {have} of {m['frames']} frames at {m['fps']} fps, {m['quality']} "
            f"({m['rendered'][0]}x{m['rendered'][1]}, {m['samples']} samples, {m['device']}), {each}, "
            f"Blender {m['blender']}, tracks: {', '.join(m.get('tracks', {})) or 'none'}"
        )
    if not rows:
        print(f"no plates in {folder}/")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="3D plates for one video, run from its working folder"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser(
        "missing",
        help="exit 1 and say what is missing when the Blender environment is not cached",
    )
    sub.add_parser(
        "fetch", help=f"download {PACKAGES[0]} (324 MB, GPL-3.0) into the uv cache"
    )
    sub.add_parser("info", help="each plate here")
    c = sub.add_parser(
        "check", help="stale, unfinished or (with --final) draft plates; exit 1 on any"
    )
    c.add_argument("--final", action="store_true")
    r = sub.add_parser("render", help="render a stage script to plates/<name>")
    r.add_argument("stage", nargs="?", default="stage.py")
    r.add_argument("--name", default="main")
    r.add_argument("--quality", choices=QUALITIES, default="final")
    r.add_argument("--frames", help="A-B, both included")
    r.add_argument("--stills", help="T,T: only the frames at these seconds")
    u = sub.add_parser(
        "run",
        help="run a stage script in the Blender environment with your own arguments (a measurement, no render)",
    )
    u.add_argument("stage")
    u.add_argument("args", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        return run(a.stage, a.args)
    if a.cmd == "missing":
        miss = missing()
        print("\n".join(miss) if miss else "ready")
        return 1 if miss else 0
    if a.cmd == "fetch":
        return fetch()
    if a.cmd == "info":
        return info()
    if a.cmd == "check":
        why = check(a.final)
        print("\n".join(f"PLATE: {w}" for w in why) if why else "PLATES: ready")
        return 1 if why else 0
    return render(a.stage, a.name, a.quality, a.frames, a.stills)


if __name__ == "__main__":
    sys.exit(main())
