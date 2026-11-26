"""Generate a build's stills (Z-Image Turbo) and clips (LTX-2.5 image to video) on the local ComfyUI.

One shot at a time, each saved as soon as it is made, so a stopped run continues where it left off:
a shot whose files exist and whose prompt has not changed is skipped.

  python studio/gen.py stills builds/01-slug            # every missing still
  python studio/gen.py clips  builds/01-slug            # every missing clip
  python studio/gen.py clips  builds/01-slug --only s03,s07 --reseed
  python studio/gen.py status builds/01-slug
  python studio/gen.py adopt  builds/02-slug --only s03 --source builds/01-slug/media/s03

From code: gen.run(batch, build, "stills", only="s03,s07", reseed=False). `batch` is the batch config
(a batch.Batch or a plain dict); the ComfyUI paths come from batch["comfy"] = {exe, home, url} and the
batch root from batch["root"]. Pass --batch <batch.json> on the command line (default: ../batch.json).

builds/<slug>/shots.json:
  {"slug": "...", "shots": [
     {"id": "s01", "still": {"prompt": "...", "seed": 11, "check": ["features to look for"]}, "clip": {"prompt": "...", "seconds": 4}},
     {"id": "s02", "from": "s01", "clip": {"prompt": "..."}},   continues from the last frame of s01
     {"id": "s03", "still": {"prompt": "..."}}                   a still only
  ]}

Files land in builds/<slug>/media/: <id>.png (still), <id>.mp4 (clip as generated), <id>/f0001.jpg ...
(clip frames at 1080x1920), <id>/last.png (the clip's last frame, the start of a continuation),
<id>.wav (the clip's own sound) and state.json (a still's `check` is kept there for the review).
ComfyUI must be running (the batch's comfy.url).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent / "comfy"
DEFAULT_URL = "http://127.0.0.1:8188"
STILL = {"w": 1088, "h": 1920, "steps": 8}
CLIP = {
    "seconds": 4,
    "fps": 30,
    "aspect": "9:16 (Portrait Widescreen)",
    "megapixels": 1.4,
}
NEGATIVE = "pc game, console game, video game, cartoon, childish, ugly, text, letters, watermark, logo, subtitles"
STILL_TAIL = " No text, no letters, no numbers, no watermark, no logo."
CLIP_HEAD = "Use the provided start image as the first frame. "
CLIP_TAIL = " No text, no captions, no black frames."


def sh(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    # comfy-cli prints a check mark; a piped Windows console would encode it as cp1252 and crash.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=kwargs.pop("check", False),
        **kwargs,
    )


class Comfy:
    """Where ComfyUI and the batch live, read from the batch config (a dict or a batch.Batch)."""

    def __init__(self, batch):
        def get(source, key, default=None):
            if isinstance(source, dict):
                return source.get(key, default)
            return getattr(source, key, default)

        comfy = get(batch, "comfy") or {}
        self.root = Path(str(get(batch, "root") or ".")).resolve()
        self.exe = Path(str(get(comfy, "exe") or "comfy"))
        home = get(comfy, "home")
        if not home:
            raise SystemExit(
                "the batch config has no comfy.home (the ComfyUI folder that holds input/ and output/)"
            )
        self.home = Path(str(home))
        self.url = str(get(comfy, "url") or DEFAULT_URL).rstrip("/")


def digest(value: object) -> str:
    return hashlib.sha1(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()[
        :12
    ]


def set_slots(ctx: Comfy, workflow: Path, values: dict[str, object]) -> None:
    pairs = [f"{address}={json.dumps(value)}" for address, value in values.items()]
    done = sh(
        [str(ctx.exe), "--no-json", "workflow", "set-slot", str(workflow), *pairs]
    )
    if done.returncode:
        raise SystemExit(f"set-slot failed: {done.stdout[-400:]} {done.stderr[-400:]}")


UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def history(ctx: Comfy, query: str) -> dict:
    import urllib.request

    try:
        with urllib.request.urlopen(f"{ctx.url}/history{query}", timeout=30) as reply:
            return json.loads(reply.read().decode("utf-8"))
    except (OSError, ValueError):
        return {}


def files_of(ctx: Comfy, entry: dict, suffix: str) -> list[Path]:
    """The output files one history entry names (a cached reply names the files of the run it was served from)."""
    found = []
    for node in (entry.get("outputs") or {}).values():
        for items in node.values():
            for item in items if isinstance(items, list) else []:
                if (
                    isinstance(item, dict)
                    and item.get("type", "output") == "output"
                    and str(item.get("filename", "")).endswith(suffix)
                ):
                    path = (
                        ctx.home
                        / "output"
                        / item.get("subfolder", "")
                        / item["filename"]
                    )
                    if path.exists():
                        found.append(path)
    return found


def made_by(
    ctx: Comfy, prefix: str, suffix: str, ids: list[str], began: float
) -> Path | None:
    """The file of THIS request. ComfyUI answers an identical job from its cache and writes nothing, so the
    newest file under the prefix may be an older picture (a prompt moved to another shot id): ask the history
    for the prompt id the CLI printed, or else for the newest request since `began` that saved under this prefix."""
    entries = {key: history(ctx, f"/{key}").get(key) for key in ids}
    entries = {key: entry for key, entry in entries.items() if entry}
    if not entries:
        recent = history(ctx, "?max_items=40")
        stamps = {}
        for key, entry in recent.items():
            graph = (entry.get("prompt") or [None, None, {}])[2] or {}
            if not any(
                isinstance(node, dict)
                and node.get("inputs", {}).get("filename_prefix") == prefix
                for node in graph.values()
            ):
                continue
            messages = entry.get("status", {}).get("messages", [])
            times = [
                m[1].get("timestamp", 0)
                for m in messages
                if len(m) > 1 and isinstance(m[1], dict)
            ]
            if times and max(times) / 1000 >= began - 2:
                stamps[key] = max(times)
        entries = {
            key: recent[key] for key in sorted(stamps, key=stamps.get, reverse=True)[:1]
        }
    for entry in entries.values():
        files = files_of(ctx, entry, suffix)
        if files:
            return files[-1]
    return None


def comfy_run(
    ctx: Comfy, workflow: Path, prefix: str, suffix: str, timeout: int = 1500
) -> tuple[Path, float]:
    """Run the workflow and return the output file of this request, with the wall time."""
    began = time.time()
    done = sh(
        [
            str(ctx.exe),
            "--no-json",
            "run",
            "--workflow",
            str(workflow),
            "--wait",
            "--timeout",
            str(timeout),
            "--no-notify",
        ]
    )
    took = time.time() - began
    made = None
    if not done.returncode:
        folder = (ctx.home / "output" / prefix).parent
        stem = Path(prefix).name
        ids = list(dict.fromkeys(UUID.findall(done.stdout + done.stderr)))
        made = made_by(ctx, prefix, suffix, ids, began)
        if (
            made is None
        ):  # no history to ask: a file written during this run is this request's
            fresh = [
                p
                for p in folder.glob(f"{stem}_*{suffix}")
                if p.stat().st_mtime >= began - 2
            ]
            made = max(fresh, key=lambda path: path.stat().st_mtime) if fresh else None
    if done.returncode or made is None:
        raise SystemExit(
            f"run failed for {prefix}: rc {done.returncode}; no output of this request found; {done.stdout[-600:]} {done.stderr[-600:]}"
        )
    return made, took


def load(build: Path, write: bool = True) -> tuple[dict, dict, Path]:
    """The plan, the state and the media folder of a build; write=False creates nothing."""
    if not (build / "shots.json").is_file():
        raise SystemExit(
            f"no shots.json in {build}: make the build and run build first"
        )
    plan = json.loads((build / "shots.json").read_text(encoding="utf-8"))
    media = build / "media"
    if write:
        media.mkdir(parents=True, exist_ok=True)
    state_file = media / "state.json"
    state = (
        json.loads(state_file.read_text(encoding="utf-8"))
        if state_file.exists()
        else {}
    )
    return plan, state, media


def save(media: Path, state: dict) -> None:
    (media / "state.json").write_text(json.dumps(state, indent=1), encoding="utf-8")


def shot_ids(only) -> str | None:
    """`only` as the one form the rest of this file reads: "s03,s07", or None for every shot. Callers pass a
    comma-separated string (the command line) or a list of ids (studio.py)."""
    if only is None or isinstance(only, str):
        items = (only or "").split(",")
    else:
        items = [str(item) for item in only]
    return ",".join(item.strip() for item in items if item.strip()) or None


def wanted(plan: dict, only: str | None) -> list[dict]:
    names = set(shot_ids(only).split(",")) if shot_ids(only) else None
    return [shot for shot in plan["shots"] if names is None or shot["id"] in names]


def chain_length(shot: dict, by_id: dict[str, dict]) -> int:
    """How many clips stand in a row up to this shot: 1 for a clip from its own still, 2 for one that
    continues another clip (`from`), 3 for one that continues a continuation."""
    length, seen = 1, {shot["id"]}
    while shot.get("from") in by_id and shot["from"] not in seen:
        shot = by_id[shot["from"]]
        seen.add(shot["id"])
        length += 1
    return length


def long_chains(plan: dict, only: str | None) -> list[str]:
    """The wanted clips that would be a third link: each continuation drifts further from its still, so the
    house rule is at most two clips in a chain. Checked before any clip is made."""
    by_id = {shot["id"]: shot for shot in plan["shots"]}
    return [
        shot["id"]
        for shot in wanted(plan, only)
        if shot.get("clip") and chain_length(shot, by_id) > 2
    ]


def shift_up(path: Path, pixels: int) -> None:
    """Move a still's picture up (negative: down) and fill the freed band with its own edge rows, stretched
    over the band and blurred.

    Places a subject exactly without drawing the still again in the hope of a better composition; it suits
    pictures whose top or bottom is plain (sky, space, a dark floor). The edge is stretched and not
    mirrored: a mirrored copy turned a subject standing at the edge upside down (boots, 2026-11-24).
    """
    amount = abs(int(pixels))
    temp = path.with_name(path.stem + ".shift.png")
    edge = 4  # the generator's outermost rows are a little brighter; they are cut, never copied
    band = amount + edge
    fill = f"scale=iw:{band}:flags=bicubic,gblur=sigma=18:steps=2"
    if pixels > 0:
        graph = f"[0:v]crop=iw:ih-{band}:0:{amount},split=2[body][b];[b]crop=iw:8:0:ih-8,{fill}[fill];[body][fill]vstack=inputs=2"
    else:
        graph = f"[0:v]crop=iw:ih-{band}:0:{edge},split=2[body][b];[b]crop=iw:8:0:0,{fill}[fill];[fill][body]vstack=inputs=2"
    done = sh(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(path),
            "-filter_complex",
            graph,
            "-frames:v",
            "1",
            str(temp),
        ]
    )
    if done.returncode or not temp.exists():
        raise SystemExit(f"shift failed for {path.name}: {done.stderr[-300:]}")
    temp.replace(path)


def free_models(ctx: Comfy) -> None:
    """Ask ComfyUI to unload its models before a run with another model.

    The image and the video model do not fit in memory together: with both loaded a clip run failed with
    'hostbuf_file_reader_read failed' (5 GB of RAM left, 2026-11-24).
    """
    import urllib.request

    request = urllib.request.Request(
        f"{ctx.url}/free",
        data=b'{"unload_models": true, "free_memory": true}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(request, timeout=30).read()
        time.sleep(3)
    except OSError as error:
        print(f"could not free ComfyUI's models: {error}", flush=True)


def stills(ctx: Comfy, build: Path, only: str | None, reseed: bool) -> None:
    plan, state, media = load(build)
    free_models(ctx)
    slug = plan["slug"]
    workflow = media / "_zimage.json"
    for shot in wanted(plan, only):
        spec = shot.get("still")
        if not spec:
            continue
        spec = {**STILL, **plan.get("still_defaults", {}), **spec}
        entry = state.setdefault(shot["id"], {})
        target = media / f"{shot['id']}.png"
        bump = entry.get("still", {}).get("bump", 0) + (1 if reseed and only else 0)
        key = digest(
            [{k: v for k, v in spec.items() if k != "check"}, plan.get("look", "")]
        )
        if (
            target.exists()
            and entry.get("still", {}).get("hash") == key
            and not (reseed and only)
        ):
            continue
        seed = int(spec.get("seed", 1000 + sum(shot["id"].encode()))) + bump
        shutil.copyfile(TEMPLATES / "z-image-turbo.json", workflow)
        prefix = f"{slug}/{shot['id']}"
        set_slots(
            ctx,
            workflow,
            {
                "57.text": (spec["prompt"].strip() + " " + plan.get("look", "")).strip()
                + STILL_TAIL,
                "57.seed": seed,
                "57.width": spec["w"],
                "57.height": spec["h"],
                "57.steps": spec["steps"],
                "9.filename_prefix": prefix,
            },
        )
        made, took = comfy_run(ctx, workflow, prefix, ".png")
        shutil.copyfile(made, target)
        if spec.get(
            "shift_up"
        ):  # place the subject: {"shift_up": 280} lifts the picture 280 px
            shift_up(target, int(spec["shift_up"]))
        entry["still"] = {
            "hash": key,
            "seed": seed,
            "bump": bump,
            "seconds": round(took, 1),
            "generator": "Z-Image Turbo int8",
        }
        if spec.get("check"):
            entry["still"]["check"] = spec[
                "check"
            ]  # what the review looks for in this picture
        entry.pop("clip", None)  # a new still makes the old clip stale
        save(media, state)
        print(f"still {shot['id']} seed {seed} {took:.0f} s", flush=True)


def start_image(shot: dict, media: Path) -> Path:
    if shot.get("from"):
        return media / shot["from"] / "last.png"
    return media / f"{shot['id']}.png"


def unpack(clip: Path, folder: Path) -> int:
    """Clip frames at 1080x1920 for the stage, the last frame as generated, and the clip's sound."""
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    scale = "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,unsharp=5:5:0.5:5:5:0.0"
    sh(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(clip),
            "-vf",
            scale,
            "-q:v",
            "2",
            str(folder / "f%04d.jpg"),
        ]
    )
    frames = sorted(folder.glob("f*.jpg"))
    sh(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-sseof",
            "-0.2",
            "-i",
            str(clip),
            "-update",
            "1",
            "-frames:v",
            "1",
            str(folder / "last.png"),
        ]
    )
    if (
        not (folder / "last.png").exists() and frames
    ):  # fall back to the last unpacked frame
        sh(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(frames[-1]),
                str(folder / "last.png"),
            ]
        )
    sh(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(clip),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "44100",
            str(folder.with_suffix(".wav")),
        ]
    )
    return len(frames)


def clips(ctx: Comfy, build: Path, only: str | None, reseed: bool) -> None:
    plan, state, media = load(build)
    chained = long_chains(plan, only)
    if chained:
        raise SystemExit(
            f"clips refused: {', '.join(chained)} would be the third clip in a chain (`from` continues another "
            "clip; at most two in a row). Give the shot a still of its own."
        )
    free_models(ctx)
    slug = plan["slug"]
    workflow = media / "_ltx_i2v.json"
    for shot in wanted(plan, only):
        spec = shot.get("clip")
        if not spec:
            continue
        spec = {**CLIP, **plan.get("clip_defaults", {}), **spec}
        entry = state.setdefault(shot["id"], {})
        source = start_image(shot, media)
        if not source.exists():
            print(
                f"clip {shot['id']}: start image {source.name} is missing, skipped",
                flush=True,
            )
            continue
        target = media / f"{shot['id']}.mp4"
        key = digest(
            [
                spec,
                shot.get("from"),
                entry.get("still", {}).get("hash"),
                state.get(shot.get("from") or "", {}).get("clip", {}).get("hash"),
            ]
        )
        bump = entry.get("clip", {}).get("bump", 0) + (1 if reseed and only else 0)
        if (
            target.exists()
            and entry.get("clip", {}).get("hash") == key
            and not (reseed and only)
        ):
            continue
        seed = int(spec.get("seed", 2000 + sum(shot["id"].encode()))) + bump
        staged = ctx.home / "input" / f"{slug}-{shot['id']}.png"
        shutil.copyfile(source, staged)
        shutil.copyfile(TEMPLATES / "ltx-2.5-i2v.json", workflow)
        prefix = f"{slug}/{shot['id']}"
        set_slots(
            ctx,
            workflow,
            {
                "395.image": staged.name,
                "398.value": CLIP_HEAD + spec["prompt"].strip() + CLIP_TAIL,
                "398.value_2": spec["seconds"],
                "398.value_5": spec["fps"],
                "398.noise_seed": seed,
                "398/373.text": plan.get("negative", NEGATIVE),
                "403.aspect_ratio": spec["aspect"],
                "403.megapixels": spec["megapixels"],
                "75.filename_prefix": prefix,
            },
        )
        made, took = comfy_run(ctx, workflow, prefix, ".mp4")
        shutil.copyfile(made, target)
        count = unpack(target, media / shot["id"])
        entry["clip"] = {
            "hash": key,
            "seed": seed,
            "bump": bump,
            "seconds": round(took, 1),
            "frames": count,
            "fps": spec["fps"],
            "generator": "LTX-2.5 distilled int8 i2v",
        }
        save(media, state)
        print(f"clip {shot['id']} seed {seed} {count} frames {took:.0f} s", flush=True)


def adopt(root: Path, build: Path, only: str | None, source: str | None) -> None:
    """Take a still and clip made in another build as this shot's media, so a proven picture is not drawn again.

    --only names one shot; --source is the other build's media path without a suffix (builds/00-mp/media/m01).
    """
    if not only or not source or "," in only:
        print(
            "adopt needs one --only <shot id> and --source <path without suffix>",
            file=sys.stderr,
        )
        raise SystemExit(64)
    plan, state, media = load(build, write=False)
    shot = next((item for item in plan["shots"] if item["id"] == only), None)
    if shot is None:
        print(f"adopt: no shot {only} in {build / 'shots.json'}", file=sys.stderr)
        raise SystemExit(64)
    origin = Path(source) if Path(source).is_absolute() else root / source
    still = origin.with_suffix(".png")
    if not still.exists() and not origin.with_suffix(".mp4").exists():
        raise SystemExit(
            f"adopt: no {still.name} or {origin.with_suffix('.mp4').name} at {origin.parent}"
        )
    media.mkdir(parents=True, exist_ok=True)
    entry = state.setdefault(shot["id"], {})
    if shot.get("still") and still.exists():
        spec = {**STILL, **plan.get("still_defaults", {}), **shot["still"]}
        shutil.copyfile(still, media / f"{shot['id']}.png")
        entry["still"] = {
            "hash": digest(
                [{k: v for k, v in spec.items() if k != "check"}, plan.get("look", "")]
            ),
            "seed": spec.get("seed"),
            "bump": 0,
            "seconds": 0,
            "generator": "Z-Image Turbo int8",
            "adopted": str(still),
        }
    clip = origin.with_suffix(".mp4")
    if shot.get("clip") and clip.exists():
        spec = {**CLIP, **plan.get("clip_defaults", {}), **shot["clip"]}
        target = media / f"{shot['id']}.mp4"
        shutil.copyfile(clip, target)
        count = unpack(target, media / shot["id"])
        entry["clip"] = {
            "hash": digest(
                [
                    spec,
                    shot.get("from"),
                    entry.get("still", {}).get("hash"),
                    state.get(shot.get("from") or "", {}).get("clip", {}).get("hash"),
                ]
            ),
            "seed": spec.get("seed"),
            "bump": 0,
            "seconds": 0,
            "frames": count,
            "fps": spec["fps"],
            "generator": "LTX-2.5 distilled int8 i2v",
            "adopted": str(clip),
        }
    save(media, state)
    print(f"adopted {shot['id']} from {origin}: {sorted(entry)}", flush=True)


def status(build: Path) -> None:
    plan, state, media = load(build, write=False)
    rows = []
    for shot in plan["shots"]:
        entry = state.get(shot["id"], {})
        still = (
            "-"
            if not shot.get("still")
            else (
                "done"
                if (media / f"{shot['id']}.png").exists() and "still" in entry
                else "todo"
            )
        )
        clip = (
            "-"
            if not shot.get("clip")
            else (
                f"done {entry['clip']['frames']}f"
                if (media / f"{shot['id']}.mp4").exists() and "clip" in entry
                else "todo"
            )
        )
        rows.append(f"{shot['id']:8} still {still:5} clip {clip}")
    print(chr(10).join(rows))


def load_batch(path: str | None):
    """The batch config: batch.load(path) when batch.py is beside this file, else the JSON as a dict."""
    here = Path(__file__).resolve().parent
    file = Path(path) if path else here.parent / "batch.json"
    if not file.exists():
        raise SystemExit(f"no batch config at {file} (pass --batch)")
    sys.path.insert(0, str(here))
    try:
        from batch import load as load_config  # noqa: PLC0415 - not imported at module import time
    except ImportError:
        return json.loads(file.read_text(encoding="utf-8"))
    finally:
        sys.path.remove(str(here))
    return load_config(file)


def run(batch, build: Path | str, cmd: str, **opts) -> None:
    """stills, clips, status or adopt on a build. opts: only, reseed, source."""
    ctx = Comfy(batch) if cmd in ("stills", "clips") else None
    root = Path(str(batch["root"] if isinstance(batch, dict) else batch.root)).resolve()
    build = Path(build) if Path(build).is_absolute() else (root / build).resolve()
    only, reseed, source = (
        shot_ids(opts.get("only")),
        bool(opts.get("reseed")),
        opts.get("source"),
    )
    if cmd == "stills":
        stills(ctx, build, only, reseed)
    elif cmd == "clips":
        clips(ctx, build, only, reseed)
    elif cmd == "adopt":
        adopt(root, build, only, source)
    elif cmd == "status":
        status(build)
    else:
        raise SystemExit(f"unknown command {cmd}: stills, clips, status or adopt")


def selftest() -> int:
    """The parts that need no ComfyUI: the shot filter in each form a caller passes, and the chain rule."""
    plan = {
        "shots": [
            {"id": "s01", "still": {"prompt": "a"}, "clip": {"prompt": "a"}},
            {"id": "s02", "from": "s01", "clip": {"prompt": "b"}},
            {"id": "s03", "from": "s02", "clip": {"prompt": "c"}},
            {"id": "s04", "still": {"prompt": "d"}},
        ]
    }
    ids = lambda only: [shot["id"] for shot in wanted(plan, shot_ids(only))]  # noqa: E731
    cases = [
        ("no filter gives every shot", ids(None), ["s01", "s02", "s03", "s04"]),
        ("an empty list gives every shot", ids([]), ["s01", "s02", "s03", "s04"]),
        ("a string names shots", ids("s02, s04"), ["s02", "s04"]),
        ("a list names shots", ids(["s04"]), ["s04"]),
        ("the third clip in a chain is refused", long_chains(plan, None), ["s03"]),
        ("two clips in a chain pass", long_chains(plan, "s01,s02"), []),
        ("a still is no link", long_chains(plan, "s04"), []),
    ]
    with tempfile.TemporaryDirectory() as scratch:
        build = Path(scratch) / "01-x"
        build.mkdir()
        (build / "shots.json").write_text(json.dumps(plan), encoding="utf-8")

        def code(*args) -> object:
            try:
                adopt(Path(scratch), build, *args)
            except SystemExit as stop:
                return stop.code if isinstance(stop.code, int) else 2
            return 0

        cases += [
            ("adopt with no png or mp4 exits 2", code("s01", "nope/nope"), 2),
            ("adopt with an unknown shot exits 64", code("zz", "nope/nope"), 64),
            ("adopt with two shots exits 64", code("s01,s02", "nope/nope"), 64),
            (
                "adopt writes nothing when refused",
                sorted(p.name for p in build.iterdir()),
                ["shots.json"],
            ),
        ]
    failed = [
        f"{name}: got {got}, want {want}" for name, got, want in cases if got != want
    ]
    for line in failed:
        print("FAIL " + line)
    print(f"GEN SELFTEST: {'FAIL' if failed else 'PASS'} ({len(cases)} cases)")
    return 1 if failed else 0


def main() -> None:
    if sys.argv[1:] == ["selftest"]:
        raise SystemExit(selftest())
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["stills", "clips", "status", "adopt"])
    parser.add_argument("build")
    parser.add_argument("--batch")
    parser.add_argument("--only")
    parser.add_argument("--reseed", action="store_true")
    parser.add_argument("--source")
    args = parser.parse_args()
    run(
        load_batch(args.batch),
        args.build,
        args.command,
        only=args.only,
        reseed=args.reseed,
        source=args.source,
    )


if __name__ == "__main__":
    sys.exit(main())
