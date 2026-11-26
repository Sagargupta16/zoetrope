"""The per-still checklist: what a program cannot see in a generated picture, asked once per still before review.

  python studio/checklist.py builds/01-slug [write]   proof/checklist.md: every generated still, its prompt and
                                                      its still.check features, every use with the line spoken
                                                      over it and its chips, a frame per use, items C1 to C6
  python studio/checklist.py builds/01-slug check     proof/checklist_answers.json against the checklist: a
                                                      missing or failed answer is a FIX (proof/qa_stills.json)

From code: write(build) -> the checklist path; check(build) -> the number of FIX rows.
An answer is {"still": "s02", "item": "C4", "ok": true, "frame": "proof/frames/t0012.30.png", "note": "..."}:
ok is true when the still passes the item. An answer older than its still (media/<id>.png newer than
checklist_answers.json) is a FIX: the still was remade after it was answered. Exit 0 PASS, 1 any FIX, 2 no
readable shots.json, 64 a usage error.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ITEMS = {
    "C1": (
        "the wrong object",
        (
            "Is it the thing the film names, checked end to end against the real thing and the features above "
            "(leaf shape, fruit, a stalk at one end only, the right kind of whale)?"
        ),
    ),
    "C2": (
        "later than the date",
        (
            "Is anything in the frame later than the date it stands under? Look at the corners and the bottom at "
            "full size: fenders, buoys, rivets, machine stitching, milled or lettered coins, wires, modern dress."
        ),
    ),
    "C3": (
        "built against grown",
        (
            "Does anything contradict the line over it: planks, posts, balusters or rope on a thing said to be "
            "grown, or growth on a thing said to be built?"
        ),
    ),
    "C4": (
        "the subject under y 1074",
        (
            "Does what the shot is about sit in the visible band (y 400 to 1000), nothing of it at or under the "
            "captions (y 1074) or the app's text (below y 1250), with the captions on?"
        ),
    ),
    "C5": (
        "a face, lettering or a badge",
        "Is there an identifiable face, readable invented text, a logo, a flag or a badge anywhere in it?",
    ),
    "C6": (
        "a picture that says more than the words",
        "Does the picture claim more than the words under it (a star close up under 'over a light-year away')?",
    ),
}
CHIPS = (
    "label",
    "source",
    "title",
    "hook",
    "lower",
    "lowerstand",
    "callout",
    "stamp",
    "number",
    "quote",
    "chip",
)


def load(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def owner(shot: dict) -> str:
    """The still a timeline shot shows (the key build.py writes, else read from its media path)."""
    if shot.get("owner"):
        return shot["owner"]
    media = shot.get("media") or {}
    found = re.search(
        r"media/([^/.]+)", str(media.get("dir") or media.get("src") or "")
    )
    return found.group(1) if found else shot["id"]


def plain(text: object) -> str:
    return re.sub(r"[*\[\]]", "", str(text or ""))


def chip_text(spec: dict) -> str:
    lines = " / ".join(
        plain(line) for line in spec.get("lines") or [] if isinstance(line, str)
    )
    text = lines or plain(spec.get("text"))
    if spec.get("type") == "number" and "value" in spec:
        text = f"{plain(spec.get('prefix'))}{spec['value']} {plain(spec.get('unit'))}".strip()
    return text


def stills(build: Path) -> list[dict]:
    """Every shot of shots.json that asks for a generated still, with what its uses show in the timeline."""
    plan = load(build / "shots.json")
    if not isinstance(plan, dict):
        return []
    state = load(build / "media" / "state.json") or {}
    timeline = load(build / "timeline.json")
    shots = timeline.get("shots", []) if isinstance(timeline, dict) else []
    tokens = timeline.get("tokens", []) if isinstance(timeline, dict) else []
    registry = load(build / "proof" / "frames" / "registry.json") or {}
    shot_at = sorted(float(key) for key in (registry.get("frames") or {}))
    found = []
    for spec in plan.get("shots", []):
        still = spec.get("still")
        if not isinstance(still, dict) or not still.get("prompt"):
            continue
        check = (
            still.get("check")
            or (state.get(spec["id"], {}).get("still") or {}).get("check")
            or []
        )
        uses = []
        for shot in shots:
            if owner(shot) != spec["id"] or (shot.get("media") or {}).get(
                "kind"
            ) not in ("clip", "still"):
                continue
            spoken = [t for t in tokens if shot["t0"] <= t["t0"] < shot["t1"]]
            middle = (shot["t0"] + shot["t1"]) / 2
            inside = [m for m in shot_at if shot["t0"] + 0.05 <= m < shot["t1"] - 0.05]
            moment = (
                min(inside, key=lambda m: abs(m - middle))
                if inside
                else round(middle, 2)
            )
            frame = f"proof/frames/t{moment:07.2f}.png"
            uses.append(
                {
                    "shot": shot["id"],
                    "t0": shot["t0"],
                    "t1": shot["t1"],
                    "grade": shot.get("grade", "none"),
                    "lines": sorted({t["line"] for t in spoken}),
                    "said": " ".join(t["d"] for t in spoken),
                    "chips": [
                        f"{o['type']}: {chip_text(o)}"
                        for o in shot.get("over", [])
                        if o.get("type") in CHIPS and chip_text(o)
                    ],
                    "frame": frame
                    if inside
                    else f"{frame} (not shot yet: studio.py check <build> frames)",
                }
            )
        found.append(
            {
                "id": spec["id"],
                "prompt": still["prompt"],
                "seed": still.get("seed"),
                "check": check,
                "uses": uses,
            }
        )
    return found


def write(build: Path | str) -> Path:
    build = Path(build)
    found = stills(build)
    look = (load(build / "shots.json") or {}).get("look", "")
    out = [
        f"# Still checklist: {build.name}",
        "",
        "One block per generated still. Open every frame named under it at full size, captions on, and answer each",
        "item C1 to C6 in proof/checklist_answers.json as",
        '`{"still": "<id>", "item": "C1", "ok": true, "frame": "<frame path>", "note": "what you saw"}`',
        "(ok: true when the still passes the item). `studio.py check <build> stills` turns a missing or failed",
        "answer into a FIX.",
        "",
    ]
    if look:
        out += [f"Look line (ends every prompt): {look}", ""]
    if not (build / "timeline.json").exists():
        out += [
            "No timeline.json yet: the uses below are empty until the build is made.",
            "",
        ]
    for still in found:
        out += [
            f"## {still['id']}"
            + (f" (seed {still['seed']})" if still["seed"] is not None else ""),
            "",
            f"Prompt: {still['prompt']}",
            "",
        ]
        if still["check"]:
            out += ["Check for: " + "; ".join(still["check"]), ""]
        else:
            out += [
                "Check for: no still.check features in shots.json; name the checkable feature of the subject.",
                "",
            ]
        lines = {tuple(use["lines"]) for use in still["uses"] if use["lines"]}
        if len(lines) > 1:
            out += [
                f"Used under {len(lines)} different lines: is it the same thing, the same date and place, each time?",
                "",
            ]
        for use in still["uses"]:
            out.append(
                f"- {use['shot']} {use['t0']:.2f} to {use['t1']:.2f} s, grade {use['grade']}, {use['frame']}"
            )
            out.append(
                f"  said: {use['said'] or '(no speech)'} [{', '.join(use['lines']) or '-'}]"
            )
            if use["chips"]:
                out.append("  on screen: " + "; ".join(use["chips"]))
        if not still["uses"]:
            out.append("- not used in the timeline")
        out.append("")
        out += [
            f"- [ ] {code} {name}: {question}"
            for code, (name, question) in ITEMS.items()
        ]
        out.append("")
    path = build / "proof" / "checklist.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out), encoding="utf-8", newline="\n")
    print(
        f"checklist: {len(found)} stills, {sum(len(s['uses']) for s in found)} uses -> {path}"
    )
    return path


def rows_of(build: Path) -> list[dict]:
    found = stills(build)
    path = build / "proof" / "checklist_answers.json"
    answers = load(path)
    answered = path.stat().st_mtime if path.is_file() else None
    given = {}
    for answer in answers if isinstance(answers, list) else []:
        if isinstance(answer, dict):
            given[(str(answer.get("still")), str(answer.get("item")))] = answer
    rows = []
    for still in found:
        for code, (name, _) in ITEMS.items():
            answer = given.get((still["id"], code))
            when = still["uses"][0]["t0"] if still["uses"] else None
            picture = build / "media" / f"{still['id']}.png"
            if (
                answer is not None
                and picture.is_file()
                and picture.stat().st_mtime > answered
            ):
                rows.append(
                    {
                        "code": code,
                        "level": "FIX",
                        "t": when,
                        "what": f"{still['id']}: {name}: the still was remade after it was answered (media/{still['id']}.png is newer than proof/checklist_answers.json)",
                        "fix": "look at the new still's frames and answer it again in proof/checklist_answers.json",
                    }
                )
            elif answer is None:
                rows.append(
                    {
                        "code": code,
                        "level": "FIX",
                        "t": when,
                        "what": f"{still['id']}: {name} is not answered",
                        "fix": "look at its frames and answer it in proof/checklist_answers.json",
                    }
                )
            elif answer.get("ok") is not True:
                rows.append(
                    {
                        "code": code,
                        "level": "FIX",
                        "t": when,
                        "what": f"{still['id']}: {name}: {answer.get('note') or 'failed'} ({answer.get('frame') or 'no frame named'})",
                        "fix": "a new still, a reprompt with the feature in it, a crop or the camera, then answer again",
                    }
                )
    return rows


def check(build: Path | str) -> int:
    build = Path(build)
    rows = rows_of(build)
    (build / "proof").mkdir(parents=True, exist_ok=True)
    (build / "proof" / "qa_stills.json").write_text(
        json.dumps(rows, indent=1), encoding="utf-8", newline="\n"
    )
    for item in rows:
        when = "      " if item["t"] is None else f"{item['t']:6.2f}"
        print(
            f"{item['level']:4} {item['code']} {when}  {item['what']}  ->  {item['fix']}"
        )
    fixes = sum(1 for item in rows if item["level"] == "FIX")
    print(f"stills: {len(stills(build))} checked, {fixes} FIX")
    return fixes


def main(argv: list[str]) -> int:
    if (
        not argv
        or len(argv) > 2
        or (len(argv) == 2 and argv[1] not in ("write", "check"))
    ):
        print("usage: checklist.py <build> [write|check]", file=sys.stderr)
        return 64
    build = Path(argv[0])
    if not isinstance(load(build / "shots.json"), dict):
        print(f"no readable shots.json in {build}", file=sys.stderr)
        return 2
    if len(argv) == 2 and argv[1] == "check":
        return 1 if check(build) else 0
    write(build)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
