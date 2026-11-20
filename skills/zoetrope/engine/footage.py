# footage.py : a video clip as a plate. A clip the parent session made (FramePack or Wan 2.2 through ComfyUI) or any
# file with a licence is decoded once into clips/<name>/ (one PNG a frame, lossless, plus clip.json); scenes.py then
# reads it like footage with Clip.frame(t), so draw(t) stays pure and every gate measures the finished picture, the
# way plate3d.Plate reads Blender frames. Nothing here downloads or generates anything.
#   python footage.py prepare <name|all>   decode clips/<name>.mp4 (or a path) into clips/<name>/ with its hashes
#   python footage.py check                what run_all.py asks before it draws: clips with no cache, a stale one
#   python footage.py info                 each clip in clips/: size, fps, frames, seconds, cache state
# In scenes.py: CLIP = footage.Clip("rain", fit="cover", mode="loop", start=2.0, speed=1.0) at module level, then
# CLIP.frame(t) inside draw(t). The source frame is floor((t - start) * speed * fps + 1e-9); past the last frame the
# clip holds it (mode "hold"), starts again ("loop") or runs back and forth ("bounce"); before start it shows frame 0.
# No clock is read in this file: scenes.py imports it, and the lint (Q1202) follows that import.
import argparse
import ast
import hashlib
import json
import math
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import contract as C
import engine as E
from PIL import Image

CLIPS = "clips"
SUFFIXES = (".mp4", ".mov", ".webm", ".mkv")
FITS = ("cover", "contain")
MODES = ("hold", "loop", "bounce")
LETTERBOX = (0, 0, 0)  # the bars of fit="contain" unless bg says otherwise


def _bad_name(name):
    """Why name cannot name a clip (None when it can): a name for clips/<name>.mp4, or a path to a video file."""
    if isinstance(name, (str, Path)) and str(name).strip() not in ("", ".", ".."):
        return None
    return f"{name!r} is not a clip name: give clips/<name>.mp4 as a name, such as rain, or a path to a video"


def _source(name, folder=CLIPS):
    """The video file a name stands for: a name with a video suffix or a folder part is a path, else
    clips/<name>.mp4."""
    p = Path(name)
    if p.suffix.lower() in SUFFIXES or p.parent != Path("."):
        return p
    return Path(folder, f"{name}.mp4")


def _dir(name, folder=CLIPS):
    """The cache folder of a clip: clips/<stem of its source>."""
    return Path(folder, _source(name, folder).stem)


def _clash(src):
    """Another video beside src with the same stem (a.mp4 and a.mov), or None: the two would share one cache folder,
    and preparing one would overwrite the other's frames."""
    src = Path(src)
    if not src.parent.is_dir():
        return None
    return next(
        (
            x
            for x in sorted(src.parent.iterdir())
            if x.name != src.name
            and x.stem == src.stem
            and x.suffix.lower() in SUFFIXES
        ),
        None,
    )


def _meta(d):
    p = Path(d, "clip.json")
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    except ValueError:
        return None


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        while block := f.read(1 << 20):
            h.update(block)
    return h.hexdigest()


def _frames(d):
    """The frame numbers on disk in a cache folder."""
    return {int(p.stem[2:]) for p in Path(d).glob("f_*.png")}


def _ffmpeg():
    ff = C.find_ffmpeg()
    if not ff:
        raise RuntimeError("ffmpeg is not installed (winget install Gyan.FFmpeg)")
    return ff


def _probe(src):
    """(info, why): the first video stream's size, fps and decoded frame count from ffprobe, or why the file is no
    clip (cut, empty, no video)."""
    try:
        j = C.ffprobe_json(
            src,
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,avg_frame_rate,r_frame_rate,nb_read_frames",
        )
    except (subprocess.CalledProcessError, OSError):
        return (
            None,
            f"{src.as_posix()} cannot be read by ffprobe: a cut or unfinished file, or not a video",
        )
    streams = j.get("streams") or []
    if not streams:
        return None, f"{src.as_posix()} has no video stream"
    s = streams[0]
    try:
        num, den = (int(x) for x in s["avg_frame_rate"].split("/"))
        if not den or not num:
            num, den = (int(x) for x in s["r_frame_rate"].split("/"))
        fps = num / den
        n, w, h = int(s["nb_read_frames"]), int(s["width"]), int(s["height"])
    except (KeyError, ValueError, ZeroDivisionError):
        return (
            None,
            f"{src.as_posix()} reports no usable frame rate, size or frame count",
        )
    if n < 1 or fps <= 0 or w < 1 or h < 1:
        return (
            None,
            f"{src.as_posix()} holds no decodable frames ({n} frames at {fps:g} fps)",
        )
    return {"fps": fps, "frames": n, "size": [w, h]}, None


def prepare(name):
    """Decode clips/<name>.mp4 (or the path) into clips/<stem>/ and write clip.json with the source sha256, fps, frame
    count and size. Frames of a cache that is already current are kept. Exit code: 0 when the clip is ready."""
    if why := _bad_name(name):
        print(why)
        return 1
    src, d = _source(name), _dir(name)
    if not src.is_file():
        print(
            f"no {src.as_posix()}: put the video there (a FramePack or Wan clip, or any file you may use)"
        )
        return 1
    if other := _clash(src):
        print(
            f"REFUSED: {src.as_posix()} and {other.as_posix()} would share the cache folder {d.as_posix()}: "
            "rename one of them"
        )
        return 1
    try:
        ff = _ffmpeg()
    except RuntimeError as e:
        print(f"not ready: {e}")
        return 1
    digest = _sha(src)
    m = _meta(d)
    if m and m.get("sha256") == digest and _frames(d) >= set(range(m["frames"])):
        print(f"{d.as_posix()}: ready ({m['frames']} frames at {m['fps']:g} fps)")
        return 0
    info, why = _probe(src)
    if why:
        print(f"REFUSED: {why}")
        return 1
    part = d.with_name(d.name + ".part")
    shutil.rmtree(part, ignore_errors=True)
    part.mkdir(parents=True)
    r = subprocess.run(
        [
            ff,
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(src),
            "-map",
            "0:v:0",
            "-an",
            "-fps_mode",
            "passthrough",
            "-pix_fmt",
            "rgb24",
            "-start_number",
            "0",
            str(part / "f_%06d.png"),
        ],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    got = len(_frames(part))
    if r.returncode or got != info["frames"]:
        print(
            f"REFUSED: {src.as_posix()} decoded {got} of the {info['frames']} frames ffprobe counts "
            f"(ffmpeg exit {r.returncode}): the file is cut or damaged; make it again"
        )
        shutil.rmtree(part, ignore_errors=True)
        return 1
    meta = {"source": src.as_posix(), "sha256": digest, **info}
    (part / "clip.json").write_text(json.dumps(meta), encoding="utf-8")
    shutil.rmtree(d, ignore_errors=True)
    part.replace(d)
    print(
        f"{d.as_posix()}: {info['frames']} frames at {info['fps']:g} fps, {info['size'][0]}x{info['size'][1]}"
    )
    return 0


def _names(scenes):
    """(names, unread): the clip names in every Clip(...) call in scenes.py, read from the source without running it
    (a string, or a module-level constant set once to one), and a "file:line" line for each call whose name cannot
    be read that way."""
    p = Path(scenes)
    if not p.is_file():
        return set(), []
    tree = ast.parse(p.read_text(encoding="utf-8"))
    nodes = list(ast.walk(tree))
    clip = {"Clip"} | {
        a.asname
        for n in nodes
        if isinstance(n, ast.ImportFrom) and n.module == "footage"
        for a in n.names
        if a.name == "Clip" and a.asname
    }
    const = {}
    for s in tree.body:
        if (
            isinstance(s, ast.Assign)
            and len(s.targets) == 1
            and isinstance(s.targets[0], ast.Name)
            and isinstance(s.value, ast.Constant)
            and isinstance(s.value.value, str)
        ):
            const[s.targets[0].id] = s.value.value
    names, unread = set(), []
    for n in nodes:
        f = getattr(n, "func", None)
        if not isinstance(n, ast.Call) or not (
            getattr(f, "id", None) in clip or getattr(f, "attr", None) == "Clip"
        ):
            continue
        first = next((k.value for k in n.keywords if k.arg == "name"), None) or (
            n.args[0] if n.args else None
        )
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            names.add(first.value)
        elif isinstance(first, ast.Name) and first.id in const:
            names.add(const[first.id])
        else:
            unread.append(
                f"{p.as_posix()}:{n.lineno} {ast.unparse(n)} names its clip with something this check cannot "
                'read: give the name as a string, Clip("rain"), or as a module-level NAME = "rain"'
            )
    return names, unread


def used(scenes="scenes.py"):
    """The clips a build draws from: the names in every Clip(...) call in its scenes.py. Empty for a build with none."""
    return _names(scenes)[0]


def check(folder=".", scenes=None):
    """Why a build must not draw yet, one line per clip its scenes.py uses (empty when every one is ready or the video
    uses none): no cache, a cache made from other bytes than the video now holds, frames missing, or a use of Clip
    whose name this check cannot read. run_all.py refuses on any line. folder is the working folder."""
    root = Path(folder)
    names, out = _names(scenes or root / "scenes.py")
    for name in sorted(names):
        if why := _bad_name(name):
            out.append(why)
            continue
        src, d = root / _source(name), root / _dir(name)
        redo = f"python footage.py prepare {name}"
        m = _meta(d)
        if not src.is_file():
            out.append(
                f"{src.as_posix()} is not here: put the video there, then {redo}"
            )
        elif other := _clash(src):
            out.append(
                f"{src.as_posix()} and {other.as_posix()} share the cache folder {d.as_posix()}: rename one, "
                f"then {redo}"
            )
        elif m is None:
            out.append(f"{d.as_posix()} is not decoded: {redo}")
        elif m.get("sha256") != _sha(src):
            out.append(
                f"{d.as_posix()} was made from other bytes than {src.as_posix()} now holds: {redo}"
            )
        elif gone := sorted(set(range(m["frames"])) - _frames(d)):
            out.append(
                f"{d.as_posix()} lacks {len(gone)} of {m['frames']} frames (first: {gone[0]}): {redo}"
            )
    return out


@lru_cache(maxsize=8)
def _fitted(path, size, fit, bg):
    """The frame file at path as an RGB image of size, by fit."""
    with Image.open(path) as im:
        im = im.convert("RGB")
    w, h = im.size
    if (w, h) == size:
        return im
    if fit == "cover":
        k = max(size[0] / w, size[1] / h)
        nw, nh = max(size[0], round(w * k)), max(size[1], round(h * k))
        im = im.resize((nw, nh), Image.LANCZOS)
        x, y = (nw - size[0]) // 2, (nh - size[1]) // 2
        return im.crop((x, y, x + size[0], y + size[1]))
    k = min(size[0] / w, size[1] / h)
    nw, nh = min(size[0], max(1, round(w * k))), min(size[1], max(1, round(h * k)))
    canvas = Image.new("RGB", size, bg)
    canvas.paste(
        im.resize((nw, nh), Image.LANCZOS), ((size[0] - nw) // 2, (size[1] - nh) // 2)
    )
    return canvas


class Clip:
    """A decoded clip for scenes.py: CLIP = footage.Clip("rain", mode="loop") at module level, then CLIP.frame(t)
    inside draw(t) gives that moment's picture as an RGB image to draw type and graphics on.
    fit "cover" fills the canvas and crops the overflow, "contain" shows the whole picture with bars of colour bg.
    mode says what follows the last frame: "hold", "loop" or "bounce". The clip starts at start seconds of the video
    and plays at speed times its own rate."""

    def __init__(
        self, name, fit="cover", mode="hold", start=0.0, speed=1.0, bg=LETTERBOX
    ):
        if why := _bad_name(name):
            raise ValueError(why)
        if fit not in FITS or mode not in MODES:
            raise ValueError(
                f"fit is one of {FITS} and mode one of {MODES}, not {fit!r} and {mode!r}"
            )
        if not speed > 0:
            raise ValueError(f"speed must be above 0, not {speed!r}")
        self.name, self.fit, self.mode = name, fit, mode
        self.start, self.speed, self.bg = float(start), float(speed), tuple(bg)
        self.dir = _dir(name)
        m = _meta(self.dir)
        if m is None:
            raise FileNotFoundError(
                f"{self.dir.as_posix()} is not decoded: python footage.py prepare {name}"
            )
        self.fps, self.n, self.size = m["fps"], m["frames"], tuple(m["size"])
        self.duration = self.n / self.fps

    def index(self, t):
        """The source frame shown at time t: floor((t - start) x speed x fps), held at the first frame before start
        and, past the last frame, held, wrapped (loop) or run back and forth (bounce; the end frames show once)."""
        k = max(0, math.floor((t - self.start) * self.speed * self.fps + 1e-9))
        if self.mode == "hold" or self.n == 1:
            return min(k, self.n - 1)
        if self.mode == "loop":
            return k % self.n
        m = k % (2 * self.n - 2)
        return m if m < self.n else 2 * self.n - 2 - m

    def frame(self, t, size=None):
        """The clip at time t as a new RGB image of size (default the canvas, W x SS by H x SS)."""
        size = tuple(size) if size else (E.W * E.SS, E.H * E.SS)
        p = self.dir / f"f_{self.index(t):06d}.png"
        if not p.is_file():
            raise FileNotFoundError(
                f"{p.as_posix()} is missing: python footage.py prepare {self.name}"
            )
        return _fitted(str(p), size, self.fit, self.bg).copy()


def info(folder=CLIPS):
    rows = sorted(p for p in Path(folder).glob("*") if p.suffix.lower() in SUFFIXES)
    for src in rows:
        m = _meta(Path(folder, src.stem))
        if m is None:
            print(f"{src.stem}: not decoded (python footage.py prepare {src.stem})")
            continue
        have = len(_frames(Path(folder, src.stem)))
        print(
            f"{src.stem}: {m['size'][0]}x{m['size'][1]}, {m['fps']:g} fps, {m['frames']} frames "
            f"({m['frames'] / m['fps']:.2f} s), {have} on disk"
        )
    if not rows:
        print(f"no clips in {folder}/")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="video clips as plates for one video, run from its working folder"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser(
        "prepare", help="decode clips/<name>.mp4 (or all of clips/) into frames"
    )
    p.add_argument("name", help="a clip name, a path to a video, or all")
    sub.add_parser("info", help="each clip here")
    sub.add_parser(
        "check",
        help="clips scenes.py uses that are not decoded or are stale; exit 1 on any",
    )
    a = ap.parse_args(argv)
    if a.cmd == "info":
        return info()
    if a.cmd == "check":
        why = check()
        print("\n".join(f"CLIP: {w}" for w in why) if why else "CLIPS: ready")
        return 1 if why else 0
    if a.name == "all":
        todo = sorted(
            x.stem for x in Path(CLIPS).glob("*") if x.suffix.lower() in SUFFIXES
        )
        if not todo:
            print(f"no clips in {CLIPS}/")
        return max([prepare(n) for n in todo] or [0])
    return prepare(a.name)


if __name__ == "__main__":
    sys.exit(main())
