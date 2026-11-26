"""Turn a build's script, narration layout, shots and media into the stage's timeline.json.

  python studio/build.py cues builds/01-slug       every caption token with its time, for writing shots.json
  python studio/build.py timeline builds/01-slug   write timeline.json and print the shot table with warnings
  (add --batch <folder> when the build is not inside a folder that holds batch.json)

From code: timeline(batch, build) and cues(batch, build), where batch is the batch config (a dict, an
object with the same names, or None) and build is the build folder. A failed build leaves no timeline.json.

Cues. A shot starts at "cue": "L04:3" (when token 3 of line L04 is spoken), a number (absolute seconds)
or nothing for the first shot. An overlay's "at" and "out" take the same forms, plus "+0.4" (seconds after
its shot starts) and "L04:end" (when the line's speech ends). A cue may end in a shift in seconds:
"L23:0-0.4" lands 0.4 s before that word, "L04:end+0.2" just after the line. The last shot gives "len" seconds.
A shot shows its own clip or still (media/<id>...), or "use": "s03" to keep playing shot s03's clip from
where the cut lands (a cut-in on the same footage), or "media": {"kind": "none", "graphic": "name"}.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

FPS = 30
CUT_LEAD = 0.08  # a cut lands this long before its word
WORD_LEAD = 0.03  # an overlay lands this long before its word
STOPS = ",.;:?!"
STRIP = ' \t,.;:?!"()'
# A tin without "d" gets its kind's length: the most common d of each kind in the films of 2026-11-24
# (slide, never used there, moves as a whip does). The stage needs a length for every kind but a cut.
TIN_D = {
    "punch": 0.35,
    "flash": 0.3,
    "whip": 0.36,
    "slide": 0.36,
    "zoom": 0.5,
    "fade": 0.4,
}


def setting(batch: object, key: str, default: object = None) -> object:
    """One key of the batch config, whether it is a dict or an object with attributes."""
    if batch is None:
        return default
    if isinstance(batch, dict):
        return batch.get(key, default)
    return getattr(batch, key, default)


def batch_root(build: Path, given: str | None = None) -> Path | None:
    """The folder that holds batch.json: the one given, else the nearest parent of the build."""
    if given:
        return Path(given).resolve()
    for folder in [build.resolve(), *build.resolve().parents]:
        if (folder / "batch.json").exists():
            return folder
    return None


def snap(seconds: float) -> float:
    """The time of the nearest frame, written to four places so that it never lies after that frame.

    A third of all frame times are repeating decimals (frame 1214 at 30 fps is 40.4666...). Rounded to four
    places they sit a hair after the frame (40.4667), and the renderer shows a shot from the first frame at or
    after its start, so every such cut and overlay came one frame late (a caption page that started on the
    frame then stood one frame on the old picture). Cutting the fifth place puts the time on or just before
    its frame, which the renderer reads as that frame."""
    return int(round(seconds * FPS) / FPS * 10000 + 1e-6) / 10000


def load(build: Path) -> tuple[dict, dict, dict]:
    script = json.loads((build / "script.json").read_text(encoding="utf-8"))
    layout = json.loads(
        (build / "narration" / "layout.json").read_text(encoding="utf-8")
    )
    shots = json.loads((build / "shots.json").read_text(encoding="utf-8"))
    return script, layout, shots


def cue_time(
    cue: object, lines: dict, start: float | None, lead: float
) -> float | None:
    if cue is None:
        return None
    if isinstance(cue, (int, float)):
        return float(cue)
    text = str(cue)
    if text.startswith("+"):
        if start is None:
            raise SystemExit(f"cue {text} needs a shot to be relative to")
        return start + float(text[1:])
    name, _, index = text.partition(":")
    if name not in lines:
        raise SystemExit(f"cue {text}: no line {name}")
    line = lines[name]
    # "L23:0-0.4" and "L04:end+0.2": the token (or the line's end), then a shift in seconds
    found = re.fullmatch(r"(end|-?\d+)?([+-]\d*\.?\d+)?", index)
    if found is None:
        raise SystemExit(f"cue {text}: cannot read {index!r}")
    index, shift = found.group(1) or "", float(found.group(2) or 0)
    if index == "end":
        return line["t1"] + shift
    tokens = line["tokens"]
    position = int(index) if index else 0
    if not -len(tokens) <= position < len(tokens):
        raise SystemExit(f"cue {text}: line {name} has {len(tokens)} tokens")
    return tokens[position]["t0"] - lead + shift


NESTED_CUES = ("at", "t0", "t1", "failAt", "moveAt", "until", "hotAt")
# Keys of an overlay itself that hold a cue (its own "at" and "out" are handled apart).
TOP_CUES = (
    "failAt",
    "moveAt",
    "until",
    "closeAt",
    "offAt",
    "linkAt",
    "ringAt",
    "ringOut",
    "drawAt",
    "labelAt",
    "pulseAt",
    "aAt",
    "bAt",
    "cAt",
    "dAt",
    "eAt",
    "fAt",
    "gAt",
    "hAt",
    "iAt",
    "jAt",
    "kAt",
    "lAt",
    "mAt",
    "landAt",
)


def early_rows(spec: dict, start: float) -> list[float]:
    """Bare numbers under a row's `at` that fall before the shot starts. A bare number is absolute seconds, so
    this is almost always an offset written without its + (rows of 0.0 and 2.1 in a shot that starts at 57 s)."""
    found: list[float] = []

    def walk(value: object, top: bool) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item, False)
        elif isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, (list, dict)):
                    walk(item, False)
                elif (
                    not top
                    and key == "at"
                    and isinstance(item, (int, float))
                    and not isinstance(item, bool)
                    and item < start - 0.001
                ):
                    found.append(float(item))

    walk(spec, True)
    return found


def nested(value: object, lines: dict, start: float, top: bool = True) -> object:
    """Resolve cue strings inside an overlay's own lists and dicts (a signal's modes, a pulse's trips)."""
    if isinstance(value, list):
        return [nested(item, lines, start, False) for item in value]
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key in (TOP_CUES if top else NESTED_CUES) and isinstance(
                item, (str, int, float)
            ):
                out[key] = snap(cue_time(item, lines, start, WORD_LEAD))
            else:
                out[key] = (
                    nested(item, lines, start, False)
                    if isinstance(item, (list, dict))
                    else item
                )
        return out
    return value


def cues(batch: object, build: Path) -> None:
    _, layout, _ = load_partial(build)
    for line in layout["lines"]:
        print(f"{line['id']}  {line['t0']:7.2f}-{line['t1']:7.2f}  {line['text']}")
        print(
            "     "
            + "  ".join(
                f"{index}:{token['d']}@{token['t0']:.2f}"
                for index, token in enumerate(line["tokens"])
            )
        )
    print(f"speech ends {layout['speech_end']:.2f} s")


def load_partial(build: Path) -> tuple[dict, dict, dict | None]:
    script = json.loads((build / "script.json").read_text(encoding="utf-8"))
    layout = json.loads(
        (build / "narration" / "layout.json").read_text(encoding="utf-8")
    )
    shots_file = build / "shots.json"
    shots = (
        json.loads(shots_file.read_text(encoding="utf-8"))
        if shots_file.exists()
        else None
    )
    return script, layout, shots


def media_of(
    build: Path, shot: dict, owners: dict, state: dict, t0: float, warnings: list[str]
) -> dict:
    media = shot.get("media")
    if isinstance(media, dict):
        return media  # a drawn picture; the caller resolves the cues it holds
    owner_id = shot.get("use", shot["id"])
    owner = owners.get(owner_id)
    if owner is None and "offset" not in shot:
        # A later shot's media may be used too, but then the point in its clip has to be named.
        raise SystemExit(
            f"shot {shot['id']}: use {owner_id} is not an earlier shot (give an offset to use a later shot's media)"
        )
    folder = build / "media" / owner_id
    frames = sorted(folder.glob("f*.jpg")) if folder.exists() else []
    wants_clip = media != "still" and bool(frames)
    if wants_clip:
        fps = state.get(owner_id, {}).get("clip", {}).get("fps", 24)
        # A cut-in keeps playing the owner clip from where the cut lands; "offset" names a point in it.
        offset = round(t0 - owner["t0"], 4) if owner_id != shot["id"] and owner else 0.0
        if "offset" in shot:
            offset = float(shot["offset"])
        found = {
            "kind": "clip",
            "dir": f"media/{owner_id}",
            "frames": len(frames),
            "fps": fps,
            "offset": offset,
        }
        if (
            "rate" in shot
        ):  # -1 plays the clip backwards from its offset (an end card that lands on frame 0)
            found["rate"] = float(shot["rate"])
        return found
    still = build / "media" / f"{owner_id}.png"
    if still.exists():
        small = still.with_suffix(".jpg")
        if not small.exists() or small.stat().st_mtime < still.stat().st_mtime:
            scale = "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920"
            subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(still),
                    "-vf",
                    scale,
                    "-q:v",
                    "2",
                    str(small),
                ],
                check=True,
            )
        return {"kind": "still", "src": f"media/{owner_id}.jpg"}
    warnings.append(
        f"{shot['id']}: no clip frames and no still for {owner_id}; drawn on the plain ground"
    )
    return {"kind": "none"}


def timeline(batch: object, build: Path) -> None:
    """Write build/timeline.json atomically; any failure removes a timeline.json left from before."""
    target = build / "timeline.json"
    target.unlink(missing_ok=True)
    try:
        write_timeline(batch, build)
    except BaseException:
        target.unlink(missing_ok=True)
        raise


def write_timeline(batch: object, build: Path) -> None:
    script, layout, plan = load(build)
    lines = {line["id"]: line for line in layout["lines"]}
    state_file = build / "media" / "state.json"
    state = (
        json.loads(state_file.read_text(encoding="utf-8"))
        if state_file.exists()
        else {}
    )
    shots = plan["shots"]
    seen: set[str] = set()
    # media, use, the review and the film diff all find a shot by its id
    for shot in shots:
        if shot["id"] in seen:
            raise SystemExit(
                f"shot {shot['id']}: the id is used twice (every shot needs its own id)"
            )
        seen.add(shot["id"])
    starts = []
    for index, shot in enumerate(shots):
        moment = 0.0 if index == 0 else cue_time(shot.get("cue"), lines, None, CUT_LEAD)
        if moment is None:
            raise SystemExit(f"shot {shot['id']} needs a cue")
        starts.append(snap(max(0.0, moment)))
    for index in range(1, len(starts)):
        if starts[index] <= starts[index - 1]:
            raise SystemExit(
                f"shot {shots[index]['id']} starts at {starts[index]}, not after {shots[index - 1]['id']} ({starts[index - 1]})"
            )
    last = shots[-1]
    if "len" not in last:
        raise SystemExit("the last shot needs a len (seconds)")
    duration = snap(starts[-1] + float(last["len"]))
    ends = starts[1:] + [duration]
    warnings: list[str] = []
    owners: dict[str, dict] = {}
    out_shots = []
    mute = []
    quiet = []
    exempt = []
    says = []
    rows = []
    for shot, t0, t1 in zip(shots, starts, ends, strict=True):
        owners[shot["id"]] = {"t0": t0}
        media = media_of(build, shot, owners, state, t0, warnings)
        length = t1 - t0
        if length < 0.8:
            warnings.append(
                f"{shot['id']}: {length:.2f} s is too short to read as a shot"
            )
        if length > 4.6 and shot.get("long") is not True:
            warnings.append(
                f'{shot["id"]}: {length:.2f} s without a cut (mark "long": true if meant)'
            )
        if media["kind"] == "clip":
            have = (media["frames"] / media["fps"] - media.get("offset", 0.0)) / max(
                0.05, abs(media.get("rate", 1.0))
            )  # a slowed clip lasts longer
            if (
                media.get("rate", 1.0) < 0
            ):  # played backwards: what is left is what lies before the offset
                have = media.get("offset", 0.0) / max(0.05, abs(media.get("rate", 1.0)))
            if have < length - 0.05:
                warnings.append(
                    f"{shot['id']}: clip has {have:.2f} s left for a {length:.2f} s shot; the last frame holds {length - have:.2f} s"
                )
        overlays = []
        for spec in shot.get("over", []):
            if spec.get("type") == "number":
                for key in ("value", "from", "to"):
                    given = spec.get(key, 0)
                    if isinstance(given, bool) or not isinstance(given, (int, float)):
                        raise SystemExit(
                            f"shot {shot['id']}: number {key} {given!r} is not a number (the stage counts it)"
                        )
            item = nested(dict(spec), lines, t0)
            for early in early_rows(spec, t0):
                warnings.append(
                    f"{shot['id']}: {spec['type']} row at {early:g} is before the shot starts ({t0:.2f}); "
                    f'a bare number is absolute seconds, so write "+{early:g}" to count from the start of the shot'
                )
            at = cue_time(spec.get("at"), lines, t0, WORD_LEAD)
            item["at"] = snap(t0 if at is None else max(t0, at))
            out = cue_time(spec.get("out"), lines, t0, WORD_LEAD)
            item["out"] = None if out is None else snap(min(out, t1))
            if not t0 - 0.001 <= item["at"] < t1:
                raise SystemExit(
                    f"shot {shot['id']}: overlay {spec['type']} at {item['at']} is outside {t0}-{t1}"
                )
            shown = (item["out"] if item["out"] is not None else t1) - item["at"]
            text = (
                " ".join(spec.get("lines", []))
                or str(spec.get("text", ""))
                or str(spec.get("sub", ""))
            )
            words = len(text.split())
            need = 0.5 + 0.3 * words if words else 0.0
            if words and shown < need - 0.05:
                warnings.append(
                    f'{shot["id"]}: {spec["type"]} "{text[:28]}" shows {shown:.2f} s, needs {need:.2f} s for {words} words'
                )
            overlays.append(item)
            if spec.get("says"):
                # The device speaks the line (a title, a quote, a number, a stamp that is the spoken words):
                # caption pages that would begin while it stands are left out, so no frame says it twice.
                # "says": true covers the device's whole stand; a number of seconds covers that long
                # from its start (a hook whose first words only are the caption's).
                whole = item["out"] if item["out"] is not None else t1
                span = spec[
                    "says"
                ]  # not `length`: the shot table below prints the shot's length
                end = (
                    whole
                    if isinstance(span, bool)
                    else min(whole, item["at"] + float(span))
                )
                says.append([round(item["at"] - 0.3, 4), round(end, 4)])
        entry = {
            key: shot[key]
            for key in (
                "id",
                "cam",
                "tin",
                "grade",
                "shade",
                "floor",
                "vignette",
                "tag",
                "flip",
                "bright",
            )
            if key in shot
        }
        bright = entry.get("bright")
        if "bright" in entry and (
            isinstance(bright, bool)
            or not isinstance(bright, (int, float))
            or not bright > 0
        ):
            # the stage writes it into a CSS filter, and a bad value drops the whole filter (blur and all)
            raise SystemExit(
                f"shot {shot['id']}: bright {bright!r} is not a brightness (a number above 0)"
            )
        tin = entry.get("tin")
        if isinstance(tin, dict) and tin.get("kind") in TIN_D:
            if "d" not in tin:
                entry["tin"] = {**tin, "d": TIN_D[tin["kind"]]}
            elif isinstance(tin["d"], bool) or not isinstance(tin["d"], (int, float)):
                raise SystemExit(
                    f"shot {shot['id']}: tin d {tin['d']!r} is not seconds"
                )
        if media.get("kind") == "none":
            media = nested(
                dict(media), lines, t0
            )  # ringAt and other cues of a drawn picture
        entry.update({"t0": t0, "t1": t1, "media": media, "over": overlays})
        entry["owner"] = shot.get("use", shot["id"])
        entry["generated"] = media.get("kind") in ("clip", "still")
        entry["real"] = any(spec.get("real") is True for spec in shot.get("over", []))
        if shot.get("says"):
            # A shot-level "says" (true, or a number of seconds) needs no carrier overlay.
            whole = shot["says"]
            end = t1 if isinstance(whole, bool) else min(t1, t0 + float(whole))
            says.append([round(t0 - 0.3, 4), round(end, 4)])
        out_shots.append(entry)
        if shot.get("captions") is False:
            mute.append([t0, t1])
        if shot.get(
            "exempt"
        ):  # a shot the pace rules do not apply to (the viewer is doing a test)
            exempt.append([t0, t1])
        if (
            shot.get("captions") == "quiet"
        ):  # whole sentences, small and still (the viewer is doing a test)
            quiet.append([t0, t1])
        rows.append(
            f"{shot['id']:6} {t0:7.2f} {t1:7.2f} {length:5.2f}  {media['kind']:5} {shot.get('use', ''):5} {' '.join(spec['type'] for spec in shot.get('over', []))}"
        )
    tokens = []
    for line in layout["lines"]:
        for token in line["tokens"]:
            shown = token["d"].strip(STRIP)
            if shown:
                tokens.append(
                    {
                        "d": shown,
                        "t0": token["t0"],
                        "t1": token["t1"],
                        "stop": token["d"][-1:] in STOPS,
                        "end": token["d"][-1:] in ".?!",
                        # what a quiet page shows after the word: it keeps the marks a sentence is read by
                        "p": next(
                            (mark for mark in "?,:" if token["d"].endswith(mark)), ""
                        ),
                        "line": line["id"],
                    }
                )
    result = {
        "slug": script["slug"],
        "title": script.get("title", ""),
        "fps": FPS,
        "duration": duration,
        "accent": script.get("accent", setting(batch, "accent", "#ffd60a")),
        "graphics": (build / "graphics.js").exists(),
        "tag": script.get("tag", setting(batch, "tag", "")),
        "progress": script.get("progress", True),
        "shots": out_shots,
        "tokens": tokens,
        "mute": mute,
        "quiet": quiet,
        "exempt": exempt,
        "says": says,
    }
    for line in script.get("lines", []):
        if line.get("payoff") or line.get("beat") == "payoff":
            wanted = lines.get(line["id"])
            if wanted is None:
                raise SystemExit(
                    f"payoff line {line['id']} is not in the narration layout"
                )
            result["payoff"] = {"line": line["id"], "t": wanted["t0"]}
            break
    temp = build / "timeline.json.tmp"
    temp.write_text(json.dumps(result, indent=1), encoding="utf-8", newline=chr(10))
    os.replace(temp, build / "timeline.json")
    print(chr(10).join(rows))
    lengths = [t1 - t0 for t0, t1 in zip(starts, ends, strict=True)]
    middle = sorted(lengths)[len(lengths) // 2]
    print(
        f"{len(shots)} shots, {duration:.2f} s, median shot {middle:.2f} s, longest {max(lengths):.2f} s, speech ends {layout['speech_end']:.2f} s"
    )
    for warning in warnings:
        print("WARN " + warning)
    if not warnings:
        print("no warnings")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["cues", "timeline"])
    parser.add_argument("build")
    parser.add_argument(
        "--batch", help="the batch folder (default: found from the build path)"
    )
    args = parser.parse_args()
    build = Path(args.build)
    root = batch_root(build, args.batch)
    if not build.is_absolute() and not build.exists() and root is not None:
        build = root / build
    batch = None
    if root is not None and (root / "batch.json").exists():
        batch = json.loads((root / "batch.json").read_text(encoding="utf-8"))
    if args.command == "cues":
        cues(batch, build)
    else:
        timeline(batch, build)


if __name__ == "__main__":
    sys.exit(main())
