"""Write a build's shot table for reviewers: proof/shots_table.md from timeline.json and layout.json.

  python studio/studio.py table builds/01-slug

One row per shot: its times, what is under it (clip, still, drawing), the spoken words that fall inside it and
every on-screen text with the time it appears. Reviewers read this beside the proof sheets.
"""

from __future__ import annotations

import json
from pathlib import Path


def words(spec: dict) -> str:
    parts = []
    keys = ("lines", "text", "sub", "label", "handle", "line")
    if (
        spec.get("type") == "end"
    ):  # the end card's big lines and its chip (a route's `big` is a switch)
        keys = ("big", "chip", *keys)
    for key in keys:
        value = spec.get(key)
        if isinstance(value, list):
            parts.append(" / ".join(str(item) for item in value))
        elif value:
            parts.append(str(value))
    if spec.get("type") == "number":
        parts.insert(
            0,
            f"{spec.get('prefix', '')}{spec.get('value')} {spec.get('unit', '')}".strip(),
        )
    for mode in spec.get("modes") or []:
        if mode.get("label"):
            parts.append(f"[{mode['mode']} at {mode['at']:.2f}: {mode['label']}]")
    for trip in spec.get("trips") or []:
        if trip.get("label"):
            parts.append(f"[trip at {trip['t0']:.2f}: {trip['label']}]")
    count = spec.get("count")
    if isinstance(count, dict):
        parts.append(
            f"[counts to {count.get('display') or str(count.get('to')) + ' ' + str(count.get('unit', ''))}]"
        )
    for key in ("book", "script", "latin"):
        if isinstance(spec.get(key), str):
            parts.append(spec[key])
    for row in spec.get("rows") if isinstance(spec.get("rows"), list) else []:
        if "label" in row:
            parts.append(
                f"[{row.get('label')}: {row.get('display', row.get('value'))}]"
            )
        else:
            said = ", ".join(
                str(row[key])
                for key in ("text", "script", "latin", "ours", "gloss")
                if row.get(key)
            )
            at = row.get("at")
            when = (
                ""
                if not isinstance(at, (int, float))
                else " (not lit yet)"
                if at > 900
                else " (already lit)"
                if at < 0
                else f" at {at:.2f}"
            )
            parts.append(f"[{said}{when}]")
    for stop in spec.get("stops") or []:
        said = ", ".join(
            str(stop[key]) for key in ("name", "date", "note") if stop.get(key)
        )
        parts.append(
            f"[stop {said}"
            + (
                f" at {stop['at']:.2f}]"
                if isinstance(stop.get("at"), (int, float))
                else "]"
            )
        )
    for sense in spec.get("senses") or []:
        parts.append(f"[sense {sense.get('n')}: {sense.get('text')}]")
    for mark in spec.get("marks") or []:
        parts.append(f"[mark {mark.get('label')}]")
    if spec.get("type") in ("rail",):
        parts.insert(0, f"{spec.get('from')} to {spec.get('to')}")
    return "; ".join(parts).replace("*", "")


def drawn(media: dict) -> str:
    """Words inside a drawn picture: any text the timeline carries on the media entry itself."""
    parts = []
    for key in ("texts", "words", "lines"):
        value = media.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
    for key in ("text", "label", "title"):
        if media.get(key):
            parts.append(str(media[key]))
    for item in media.get("items") or []:
        parts.append(words(item) if isinstance(item, dict) else str(item))
    return "; ".join(part for part in parts if part).replace("*", "")


def write(build: Path) -> Path:
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    out = [
        f"# Shot table: {timeline['slug']} ({timeline['duration']:.2f} s, {len(timeline['shots'])} shots)",
        "",
        "| shot | from | to | s | picture | spoken inside the shot | on screen (type at time: text) |",
        "|---|---|---|---|---|---|---|",
    ]
    for shot in timeline["shots"]:
        media = shot["media"]
        if media["kind"] == "clip":
            picture = (
                f"clip {media['dir'].split('/')[-1]} from {media.get('offset', 0):.1f} s"
                + (" backwards" if media.get("rate", 1) < 0 else "")
            )
        elif media["kind"] == "still":
            picture = f"still {Path(media['src']).stem}"
        else:
            picture = f"drawing {media.get('graphic', 'plain ground')}"
        if shot.get("grade"):
            picture += f", {shot['grade']}"
        said = " ".join(
            token["d"]
            for token in timeline["tokens"]
            if shot["t0"] - 0.05 <= token["t0"] < shot["t1"] - 0.05
        )
        parts = [
            f"{spec['type']} at {spec['at']:.2f}: {words(spec)}"
            for spec in shot["over"]
        ]
        inside = drawn(media)
        if inside:
            parts.insert(0, f"drawn media: {inside}")
        out.append(
            f"| {shot['id']} | {shot['t0']:.2f} | {shot['t1']:.2f} | {shot['t1'] - shot['t0']:.2f} | {picture} | {said} | {' <br> '.join(parts)} |"
        )
    target = build / "proof" / "shots_table.md"
    target.parent.mkdir(exist_ok=True)
    target.write_text(chr(10).join(out) + chr(10), encoding="utf-8", newline="")
    return target
