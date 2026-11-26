"""One row per build, one column per stage: missing, done or stale (from file existence and mtimes).

python studio/studio.py status <batch>
"""

from __future__ import annotations

import json
from pathlib import Path

STAGES = ("script", "voice", "shots", "stills", "lint", "frames", "render", "review")


def _mtime(path: Path) -> float | None:
    return path.stat().st_mtime if path.exists() else None


def _newest(folder: Path) -> float | None:
    times = (
        [item.stat().st_mtime for item in folder.rglob("*") if item.is_file()]
        if folder.is_dir()
        else []
    )
    return max(times) if times else None


def _state(made: float | None, *inputs: float | None) -> str:
    if made is None:
        return "missing"
    return (
        "stale" if any(item is not None and item > made for item in inputs) else "done"
    )


def _script(build: Path, made: float | None, source: float | None) -> str:
    """script.json against script.md: missing with no script.json; done when script.md is no newer, or when it
    is newer and its tables still hold the lines and the lexicon script.json holds (the voice step writes its
    measured read into script.md after `script` ran, which changes no line of the film); stale otherwise."""
    if made is None:
        return "missing"
    if source is None or source <= made:
        return "done"
    import studio  # the one reader of a script.md table

    try:
        text = (build / "script.md").read_text(encoding="utf-8")
        lines, lexicon = studio.script_lines(text), studio.script_lexicon(text)
        held = json.loads((build / "script.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "stale"
    if lexicon is not None and lexicon != (held.get("lexicon") or {}):
        return "stale"
    return "done" if lines == held.get("lines") else "stale"


def _stills(build: Path) -> str:
    """The stills of a build: missing when the shot list asks for stills and none is made, stale while some are
    still to make or redraw, done when every shot that asks for a still has its picture drawn from its present
    prompt (or none asks). It reads the shot list and media/state.json and no file times: a still is current
    when its recorded hash is the one `stills` computes now, and a shot whose clip was adopted with no still
    (build plays the clip) counts as made."""
    from gen import STILL, digest  # the one definition of a still's hash

    try:
        plan = json.loads((build / "shots.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "missing"
    record = build / "media" / "state.json"
    try:
        state = (
            json.loads(record.read_text(encoding="utf-8")) if record.is_file() else {}
        )
    except ValueError:
        state = {}
    asked = [shot for shot in plan.get("shots", []) if shot.get("still")]
    made, current = 0, 0
    for shot in asked:
        entry = state.get(shot["id"], {})
        if "still" not in entry:
            adopted = "adopted" in entry.get("clip", {})
            made += adopted
            current += adopted
            continue
        if not (build / "media" / f"{shot['id']}.png").is_file():
            continue
        spec = {**STILL, **plan.get("still_defaults", {}), **shot["still"]}
        key = digest(
            [{k: v for k, v in spec.items() if k != "check"}, plan.get("look", "")]
        )
        made += 1
        current += entry["still"].get("hash") == key
    if current == len(asked):
        return "done"
    return "stale" if made else "missing"


def _slug(build: Path) -> str:
    try:
        return json.loads((build / "timeline.json").read_text(encoding="utf-8"))["slug"]
    except (OSError, ValueError, KeyError):
        return build.name


def row(build: Path) -> dict[str, str]:
    import studio  # the one definition of a stale timeline

    t = lambda *parts: _mtime(build.joinpath(*parts))  # noqa: E731
    script, layout, shots, timeline = (
        t("script.json"),
        t("narration", "layout.json"),
        t("shots.json"),
        t("timeline.json"),
    )
    video = t("out", f"{_slug(build)}.mp4")
    stage = {
        "script": _script(build, script, t("script.md")),
        "voice": _state(layout, script),
        # shots.json holds cues, not times: a newer script.json makes the timeline stale (below), not the shot list
        "shots": _state(shots, t("shots.py")),
        "stills": _stills(build),
        "lint": _state(t("proof", "qa_lint.json"), timeline, shots),
        "frames": _state(t("proof", "qa_frames.json"), timeline, shots),
        "render": _state(video, timeline, shots, t("graphics.js"), layout),
        "review": _state(_newest(build / "proof" / "reviews"), video),
    }
    if shots is not None and (timeline is None or studio.stale_input(build)):
        stage["shots"] = "stale"
        if video is not None:
            stage["render"] = "stale"
    return stage


def show(batch_dir: Path) -> int:
    builds = sorted(item for item in (batch_dir / "builds").glob("*") if item.is_dir())
    if not builds:
        print(f"no builds in {batch_dir / 'builds'}")
        return 0
    width = max(len("build"), *(len(item.name) for item in builds))
    print("  ".join(["build".ljust(width), *(name.ljust(7) for name in STAGES)]))
    for build in builds:
        cells = row(build)
        print(
            "  ".join(
                [build.name.ljust(width), *(cells[name].ljust(7) for name in STAGES)]
            )
        )
    return 0
