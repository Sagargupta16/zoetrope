"""Checks for a build, each a row: code, FIX or NOTE, when, what, and the change that clears it.

  python studio/qa.py plan builds/01-slug
      from timeline.json and the narration layout alone: pace, the hook, reading holds, dead stretches,
      speech coverage, the end card.
  uv run --no-project --with playwright --with pillow --with numpy python studio/qa.py frames builds/01-slug
      shoots frames through the stage, reads every text box (safe box, size, overlap, contrast), measures
      dark frames and how much of the picture text covers, and writes proof/sheet_NN.png.
  uv run --no-project --with numpy --with pillow python studio/qa.py file builds/01-slug
      the encoded file: spec, length, size, loudness, flashes, black spans (the engine's probe, loud and
      flash_report_file, and ffmpeg's blackdetect), and stretches where the picture does not change. A check
      that cannot run is a V00 FIX, never a silent pass.

Exit 1 when any row is a FIX (file: 2 when a check could not run and nothing else is wrong). Rows also go
to builds/<slug>/proof/qa_<stage>.json.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAFE = {
    "x0": 60,
    "x1": 1020,
    "y0": 270,
    "y1": 1252,
}  # critical text; captions end at 1252
LOOSE_Y1 = {"source": 1340, "endcard": 1500}
MIN_PX = 32


def row(
    rows: list[dict], code: str, level: str, when: float | None, what: str, fix: str
) -> None:
    rows.append(
        {
            "code": code,
            "level": level,
            "t": None if when is None else round(when, 2),
            "what": what,
            "fix": fix,
        }
    )


def finish(build: Path, stage: str, rows: list[dict]) -> int:
    proof = build / "proof"
    proof.mkdir(exist_ok=True)
    (proof / f"qa_{stage}.json").write_text(
        json.dumps(rows, indent=1), encoding="utf-8"
    )
    for item in sorted(
        rows, key=lambda r: (r["level"] != "FIX", r["t"] if r["t"] is not None else -1)
    ):
        when = "      " if item["t"] is None else f"{item['t']:6.2f}"
        print(
            f"{item['level']:4} {item['code']} {when}  {item['what']}  ->  {item['fix']}"
        )
    fixes = sum(1 for item in rows if item["level"] == "FIX")
    print(f"qa {stage}: {fixes} FIX, {len(rows) - fixes} NOTE")
    return 1 if fixes else 0


def words_of(spec: dict) -> int:
    text = " ".join(spec.get("lines", [])) or str(spec.get("text", ""))
    return len(text.replace("*", "").split())


def same_words(a: dict, b: dict) -> bool:
    return (a.get("lines"), a.get("text")) == (b.get("lines"), b.get("text"))


def device_times(spec: dict) -> list[float]:
    """Moments inside a drawn device when the picture changes (a signal's mode, a pulse's trip, a move)."""
    found = [
        spec[key]
        for key in (
            "failAt",
            "moveAt",
            "closeAt",
            "offAt",
            "linkAt",
            "drawAt",
            "labelAt",
            "until",
        )
        if isinstance(spec.get(key), (int, float))
    ]
    for row in spec.get("rows") if isinstance(spec.get("rows"), list) else []:
        if spec.get("type") == "compare" and isinstance(row.get("at"), (int, float)):
            found.append(
                spec["at"] + row["at"]
            )  # a bar that starts later than its overlay
        elif isinstance(row.get("at"), (int, float)):
            found.append(
                row["at"]
            )  # a row that arrives at its own cue (a list, a word, a dictionary row)
        count = row.get("count")
        if isinstance(count, dict) and isinstance(count.get("t1"), (int, float)):
            found.append(count["t1"])  # a ladder row landing on its value
    for mark in spec.get("marks") or []:
        if isinstance(mark.get("t0"), (int, float)):
            found.append(mark["t0"])
    for key in ("modes", "trips"):
        for item in spec.get(key) or []:
            for name in ("at", "t0"):
                if isinstance(item.get(name), (int, float)):
                    found.append(item[name])
    fade = spec.get("fade")
    if isinstance(fade, dict) and isinstance(fade.get("at"), (int, float)):
        found.append(fade["at"])
    count = spec.get("count")
    if isinstance(count, dict):  # a device that counts in (a row of Moons)
        found += [
            count[name]
            for name in ("t0", "t1")
            if isinstance(count.get(name), (int, float))
        ]
    for key in ("stops", "senses"):  # a rail's stops, a dictionary entry's senses
        for item in spec.get(key) or []:
            for name in ("at", "hotAt"):
                if isinstance(item.get(name), (int, float)):
                    found.append(item[name])
    found += [
        spec[name]
        for name in (
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
            "pulseAt",
            "ringAt",
        )
        if isinstance(spec.get(name), (int, float))
    ]
    return found


BARE_RUN = 10.0  # seconds: the longest run of shots on a bare plate (P12)
CLIPS_A_MINUTE = 4  # the rule list's 8 clips in a two-minute film (P13)


def plan(build: Path) -> int:
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    layout = json.loads(
        (build / "narration" / "layout.json").read_text(encoding="utf-8")
    )
    rows: list[dict] = []
    shots = timeline["shots"]
    duration = timeline["duration"]
    # Exempt stretches: shots the pace rules do not apply to (the viewer is doing a test on a still card).
    exempt = timeline.get("exempt") or []

    def free(moment: float) -> bool:
        return any(a - 0.01 <= moment < b for a, b in exempt)

    lengths = [shot["t1"] - shot["t0"] for shot in shots if not free(shot["t0"])] or [
        0.0
    ]
    middle = sorted(lengths)[len(lengths) // 2]
    if not 60 <= duration <= 179:
        row(
            rows,
            "P01",
            "FIX",
            None,
            f"the video runs {duration:.1f} s",
            "keep it between 60 and 179 s (Reels over 3 minutes leave the Reels tab)",
        )
    if middle > 2.9:
        row(
            rows,
            "P02",
            "FIX",
            None,
            f"median shot is {middle:.2f} s",
            "cut more often: aim for a median near 2.2 s",
        )
    # STYLE: "The picture changes three times in the first 3.5 s: count the cuts and punch-ins".
    early = len(
        {round(shot["t0"], 2) for shot in shots if 0 < shot["t0"] <= 3.5}
        | {
            round(spec["at"], 2)
            for shot in shots
            for spec in shot["over"]
            if spec["type"] == "punch" and 0 < spec["at"] <= 3.5
        }
    )
    if early < 3 and not free(0.0):
        row(
            rows,
            "P03",
            "FIX",
            0.0,
            f"{early} picture change(s) in the first 3.5 s",
            "three cuts or punch-ins before 3.5 s",
        )
    first = shots[0]
    hooks = [spec for spec in first["over"] if spec["type"] == "hook"]
    if not hooks or hooks[0]["at"] > 0.001:
        row(
            rows,
            "P04",
            "FIX",
            0.0,
            "no hook standing on frame 0",
            "give the first shot a hook overlay with no cue",
        )
    # STYLE: "hook up to 190 (six words or fewer, complete on frame 0)"
    elif words_of(hooks[0]) > 6:
        row(
            rows,
            "P04",
            "FIX",
            0.0,
            f"the on-screen hook has {words_of(hooks[0])} words",
            "six words or fewer",
        )
    hook_end = layout["lines"][0]["t1"]
    if hook_end > 3.5:
        row(
            rows,
            "P05",
            "FIX",
            hook_end,
            f"the spoken hook ends at {hook_end:.2f} s",
            "cut words until it is over by 3.0 s",
        )
    elif hook_end > 3.05:
        row(
            rows,
            "P05",
            "NOTE",
            hook_end,
            f"the spoken hook ends at {hook_end:.2f} s",
            "over by 3.0 s is the target",
        )
    events = sorted(
        {0.0, duration}
        | {shot["t0"] for shot in shots}
        | {spec["at"] for shot in shots for spec in shot["over"]}
        | {
            moment
            for shot in shots
            for spec in shot["over"]
            for moment in device_times(spec)
            if moment >= 0
        }
        | {
            moment
            for shot in shots
            for moment in device_times(shot["media"])
            if moment >= 0
        }
    )
    for before, after in zip(events, events[1:], strict=False):
        if after - before > 3.3 and before < duration - 3.6 and not free(before):
            row(
                rows,
                "P06",
                "FIX",
                before,
                f"nothing new on screen for {after - before:.1f} s",
                "add a cut, a cut-in or an overlay inside this stretch",
            )
    for index, shot in enumerate(shots):
        length = shot["t1"] - shot["t0"]
        for spec in shot["over"]:
            count = words_of(spec)
            if not count or spec["type"] in ("end",):
                continue
            shown = (spec["out"] if spec["out"] is not None else shot["t1"]) - spec[
                "at"
            ]
            # The same words carried over cuts are one continuous hold (a punch-in on the hook, a source line under
            # four shots of one drawing): walk out from this shot for as long as the neighbour carries them too.
            # Counting one neighbour only called a ten-word line short at 3.33 s while it stood 7.17 s.
            # The hold must be unbroken: this copy stands to the cut and the twin from it (a line that leaves
            # and comes back is two short stands), and a neighbour carrying the words twice counts once.
            for step in (-1, 1):
                at, here, inner = index + step, spec, shot
                while 0 <= at < len(shots):
                    other = shots[at]
                    if step > 0:
                        reaches = (
                            here["out"] is None or here["out"] >= inner["t1"] - 0.01
                        )
                    else:
                        reaches = here["at"] <= inner["t0"] + 0.01
                    twins = [
                        twin
                        for twin in other.get("over", [])
                        if twin["type"] == spec["type"]
                        and same_words(twin, spec)
                        and (
                            twin["at"] <= other["t0"] + 0.01
                            if step > 0
                            else twin["out"] is None
                            or twin["out"] >= other["t1"] - 0.01
                        )
                    ]
                    if not reaches or not twins:
                        break
                    stands = {
                        (twin["out"] if twin["out"] is not None else other["t1"])
                        - twin["at"]: twin
                        for twin in twins
                    }
                    longest = max(stands)
                    shown += longest
                    here, inner = stands[longest], other
                    at += step
            need = min(0.5 + 0.3 * count, 4.0)
            if shown < need - 0.06:
                row(
                    rows,
                    "P07",
                    "FIX",
                    spec["at"],
                    f"{shot['id']} {spec['type']} ({count} words) shows {shown:.2f} s",
                    f"needs {need:.2f} s: cut words, cue it earlier or hold the shot",
                )
        media = shot["media"]
        if media["kind"] == "clip":
            have = (media["frames"] / media["fps"] - media.get("offset", 0.0)) / max(
                0.05, abs(media.get("rate", 1.0))
            )  # a slowed clip lasts longer
            if media.get("rate", 1.0) < 0:  # played backwards from its offset
                have = media.get("offset", 0.0) / max(0.05, abs(media.get("rate", 1.0)))
            if have < length - 0.5:
                row(
                    rows,
                    "P08",
                    "NOTE",
                    shot["t0"],
                    f"{shot['id']} holds its last frame {length - have:.1f} s",
                    "shorten the shot, cut in, or continue the clip",
                )
    spoken = sum(line["t1"] - line["t0"] for line in layout["lines"])
    cover = spoken / layout["speech_end"]
    if cover < 0.86 and not exempt:
        row(
            rows,
            "P09",
            "FIX",
            None,
            f"speech covers {100 * cover:.0f}% of the narrated stretch",
            "tighten the gaps between lines: 88% or more",
        )
    for before, after in zip(layout["lines"], layout["lines"][1:], strict=False):
        gap = after["t0"] - before["t1"]
        if gap > 0.75 and not free(before["t1"]):
            row(
                rows,
                "P10",
                "NOTE",
                before["t1"],
                f"{gap:.2f} s of silence before {after['id']}",
                "fine when a picture beat fills it; otherwise shorten",
            )
    last = shots[-1]
    if not any(spec["type"] == "end" for spec in last["over"]):
        row(
            rows,
            "P11",
            "FIX",
            last["t0"],
            "the last shot has no end card",
            "add an end overlay",
        )
    elif last["t1"] - last["t0"] < 2.5 - 0.001:  # both ends are snapped frame times
        row(
            rows,
            "P11",
            "FIX",
            last["t0"],
            f"the end card holds {last['t1'] - last['t0']:.1f} s",
            "2.5 s or more",
        )
    # P12: a shot whose media is "none" shows a drawing or type on the kit's bare plate. One is a card; a run of
    # them is a slide deck (the engine's first film held 22 s and 17 s of it and every reader still said READY).
    # A graphic drawn as an overlay of a blurred picture shot has a picture under it and does not count, nor
    # does a shot whose media is the kit's `plate` (a blurred picture) or that has a `plate` layer for the whole
    # shot. A `ground` layer covers the picture under it. An exempt bare shot keeps a run open but adds no time.
    bare: list[list[float]] = []
    for shot in shots:
        media = shot.get("media") or {}
        over = shot.get("over") or []
        # a layer counts only when it stands for the whole shot: a ground that flashes over a picture for half a
        # second does not make the shot bare, and a plate that leaves early does not make it pictured
        whole = [
            spec.get("type")
            for spec in over
            if spec.get("at", shot["t0"]) <= shot["t0"] + 0.01
            and (spec.get("out") is None or spec["out"] >= shot["t1"] - 0.01)
        ]
        pictured = (
            (media.get("kind", "none") != "none" or media.get("graphic") == "plate")
            and "ground" not in whole
        ) or "plate" in whole
        if pictured:
            continue
        counted = 0.0 if free(shot["t0"]) else shot["t1"] - shot["t0"]
        if bare and abs(bare[-1][1] - shot["t0"]) < 0.01:
            bare[-1][1] = shot["t1"]
            bare[-1][2] += counted
        elif counted:
            bare.append([shot["t0"], shot["t1"], counted])
    for start, stop, counted in bare:
        if counted > BARE_RUN:
            row(
                rows,
                "P12",
                "FIX",
                start,
                f"{counted:.1f} s in a row stand on a bare plate ({start:.2f} to {stop:.2f} s"
                + (
                    ", exempt shots not counted)"
                    if counted < stop - start - 0.01
                    else ")"
                ),
                f"{BARE_RUN:.0f} s at most: set the drawings over a blurred, drifting picture (a picture shot with"
                " the graphic as an overlay) or cut a picture in between",
            )
    # P13: the rule list asks for 8 to 14 clips in a two-minute film, which is 4 a minute.
    clips = {
        str(shot["media"].get("dir"))
        for shot in shots
        if (shot.get("media") or {}).get("kind") == "clip"
    }
    # An exempt stretch (a test on a still card) needs no clips: only the rest of the film counts.
    moving = max(0.0, duration - sum(b - a for a, b in exempt))
    wanted = round(CLIPS_A_MINUTE * moving / 60)
    if len(clips) < wanted:
        row(
            rows,
            "P13",
            "NOTE",
            None,
            f"{len(clips)} clips in {moving:.0f} s"
            + (" outside the exempt shots" if exempt else ""),
            f"the rule list asks for about {wanted} or more where the story moves (8 to 14 in two minutes)",
        )
    rate = sum(len(line["words"]) for line in layout["lines"]) / max(1.0, spoken)
    print(
        f"plan: {len(shots)} shots, {duration:.1f} s, median shot {middle:.2f} s, longest {max(lengths):.2f} s, speech {100 * cover:.0f}% at {rate:.2f} words/s"
    )
    return finish(build, "plan", rows)


def luminance(rgb: tuple[float, float, float]) -> float:
    def channel(value: float) -> float:
        value /= 255
        return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2])
    )


def frames(build: Path, extra: str | None) -> int:
    import numpy as np
    from PIL import Image

    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    moments: dict[float, str] = {}
    shots = timeline["shots"]
    for index, shot in enumerate(shots):
        # stay clear of the windows where two shots overlap in a whip, zoom or fade
        lead = (
            shot.get("tin", {}).get("d", 0) / 2
            if shot.get("tin", {}).get("kind") in ("whip", "slide", "zoom", "fade")
            else 0
        )
        after = shots[index + 1].get("tin", {}) if index + 1 < len(shots) else {}
        tail = (
            after.get("d", 0) / 2
            if after.get("kind") in ("whip", "slide", "zoom", "fade")
            else 0
        )
        first, last = shot["t0"] + lead + 0.1, shot["t1"] - tail - 0.1
        if last <= first:
            first = last = (shot["t0"] + shot["t1"]) / 2
        for moment in (first, (first + last) / 2, last):
            moments[round(moment, 2)] = shot["id"]
        for spec in shot["over"]:
            moments[round(min(max(spec["at"] + 0.7, first), last), 2)] = shot["id"]
            # a stop that pops its name as it is reached (route big: 8% from its left edge, over its note)
            for stop in spec.get("stops") or []:
                if (
                    isinstance(stop, dict)
                    and isinstance(stop.get("at"), (int, float))
                    and first <= stop["at"] + 0.1 <= last
                ):
                    moments[round(stop["at"] + 0.1, 2)] = shot["id"]
            # an answer row pops as it lights: the frame after it lands is its widest, where F01 must see it
            if spec.get("type") == "answers":
                for item in spec.get("rows") or []:
                    if (
                        isinstance(item, dict)
                        and isinstance(item.get("at"), (int, float))
                        and shot["t0"] <= item["at"] + 0.04 < shot["t1"]
                    ):
                        moments[round(item["at"] + 0.04, 2)] = shot["id"]
            # a count's landing, just before and just after it, so the lint's L07 sees both sides
            land = spec.get("landAt") if spec.get("type") == "number" else None
            if spec.get("standing"):
                land = None  # a standing number is landed from its first frame: the kit does not read landAt
            if spec.get("type") in ("rail", "years"):
                land = spec.get("until")
            if isinstance(land, (int, float)):
                for moment in (land - 0.1, land + 0.1):
                    if 0 <= moment < shots[-1]["t1"]:
                        moments[round(moment, 2)] = shot["id"]
    moments[0.0] = timeline["shots"][0]["id"]
    for value in (extra or "").split(","):
        if value.strip():
            moments[round(float(value), 2)] = "extra"
    times = sorted(moments)
    proof = build / "proof"
    shots_dir = proof / "frames"
    if shots_dir.exists():
        for old in shots_dir.glob("*"):
            old.unlink()
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "studio" / "render.py"),
            "stills",
            "--video",
            str(build.resolve()),  # absolute: the check runs from any working folder
            "--times",
            ",".join(f"{moment:.2f}" for moment in times),
            "--out",
            str(shots_dir),
        ],
        check=True,
    )
    registry = json.loads((shots_dir / "registry.json").read_text(encoding="utf-8"))[
        "frames"
    ]
    rows: list[dict] = []
    for moment in times:
        boxes = registry[f"{moment:.2f}"]
        with Image.open(shots_dir / f"t{moment:07.2f}.png") as image:
            pixels = np.asarray(image.convert("RGB"), dtype=float)
        luma = (
            0.2126 * pixels[..., 0] + 0.7152 * pixels[..., 1] + 0.0722 * pixels[..., 2]
        )
        shot_id = moments[moment]
        dark = float((luma < 24).mean())
        last_shot = timeline["shots"][-1]["id"]
        if shot_id != last_shot:
            if dark > 0.6:
                row(
                    rows,
                    "F05",
                    "FIX",
                    moment,
                    f"{shot_id}: {100 * dark:.0f}% of the frame is near black",
                    "use a lit picture under the graphics",
                )
            elif dark > 0.42:
                row(
                    rows,
                    "F05",
                    "NOTE",
                    moment,
                    f"{shot_id}: {100 * dark:.0f}% of the frame is near black",
                    "brighter picture if it reads as a dead screen",
                )
        if moment == 0.0:
            if luma.mean() < 40:
                row(
                    rows,
                    "F06",
                    "FIX",
                    0.0,
                    f"frame 0 is dark (mean {luma.mean():.0f} of 255)",
                    "open on a lit picture",
                )
            if not any(box["role"] == "hook" for box in boxes):
                row(
                    rows,
                    "F06",
                    "FIX",
                    0.0,
                    "no hook text on frame 0",
                    "the hook stands complete on the first frame",
                )
        area = 0
        for index, box in enumerate(boxes):
            x0, y0, x1, y1 = (
                box["x"],
                box["y"],
                box["x"] + box["w"],
                box["y"] + box["h"],
            )
            area += box["w"] * box["h"]
            limit = LOOSE_Y1.get(box["role"], SAFE["y1"])
            label = f'{shot_id} {box["role"]} "{box["text"][:26]}"'
            if x0 < SAFE["x0"] or x1 > SAFE["x1"] or y0 < SAFE["y0"] or y1 > limit:
                row(
                    rows,
                    "F01",
                    "FIX",
                    moment,
                    f"{label} at x {x0}-{x1}, y {y0}-{y1} leaves the safe box",
                    f"keep it inside x {SAFE['x0']}-{SAFE['x1']}, y {SAFE['y0']}-{limit}",
                )
            if box["px"] < MIN_PX:
                row(
                    rows,
                    "F02",
                    "FIX",
                    moment,
                    f"{label} is {box['px']:.0f} px",
                    f"{MIN_PX} px or more",
                )
            # a line box is taller than its letters: compare the middle 72% of each box
            trim = 0.14 * (y1 - y0)
            for other in boxes[index + 1 :]:
                ox0, ox1 = other["x"], other["x"] + other["w"]
                cut = 0.14 * other["h"]
                oy0, oy1 = other["y"] + cut, other["y"] + other["h"] - cut
                across = max(0, min(x1, ox1) - max(x0, ox0))
                down = max(0, min(y1 - trim, oy1) - max(y0 + trim, oy0))
                shared = across * down
                smaller = min(box["w"] * box["h"], other["w"] * other["h"]) * 0.72
                # half a letter covered either way: a route name that pops 8% over the first letter of its
                # note covers far less than 8% of a long note's box (film 05)
                glyph = 0.5 * min(box["px"], other["px"])
                if (
                    smaller
                    and (shared / smaller > 0.08 or (across >= glyph and down >= glyph))
                    and box["opacity"] > 0.5
                    and other["opacity"] > 0.5
                ):
                    row(
                        rows,
                        "F03",
                        "FIX",
                        moment,
                        f'{label} overlaps {other["role"]} "{other["text"][:20]}"',
                        "move one of them or cue them apart",
                    )
            if box["role"] in ("caption", "stamp") or box["opacity"] < 0.9:
                continue
            numbers = [
                float(value) for value in re.findall(r"[0-9.]+", box["color"])[:3]
            ]
            if len(numbers) < 3:
                continue
            # what the letters sit on is inside their box (a chip's own fill, or the picture under a title):
            # a margin around a small chip samples the paper around it instead (film 06, 1.7:1 on a fine chip)
            pad = 14 if box["w"] * box["h"] < 400 else 0
            xa, xb = max(0, int(x0) - pad), min(1080, int(x1) + pad)
            ya, yb = max(0, int(y0) - pad), min(1920, int(y1) + pad)
            region = pixels[ya:yb, xa:xb].reshape(-1, 3)
            if not len(region):
                continue
            back = np.median(region, axis=0)
            high, low = sorted(
                (luminance(tuple(numbers)), luminance(tuple(back))), reverse=True
            )
            ratio = (high + 0.05) / (low + 0.05)
            if ratio < 1.8:
                row(
                    rows,
                    "F04",
                    "NOTE",
                    moment,
                    f"{label} has contrast {ratio:.1f}:1 against the picture; only its outline separates it",
                    "look at the frame at phone size; shade the picture there if it reads weak",
                )
        share = area / (1080 * 1920)
        if share > 0.45:
            row(
                rows,
                "F07",
                "FIX",
                moment,
                f"{shot_id}: text boxes cover {100 * share:.0f}% of the frame",
                "less text: the picture carries the frame",
            )
        elif share > 0.32:
            row(
                rows,
                "F07",
                "NOTE",
                moment,
                f"{shot_id}: text boxes cover {100 * share:.0f}% of the frame",
                "Instagram shows Reels mostly covered by text less often",
            )
    stills = sorted(shots_dir.glob("t*.png"))
    for number in range(0, len(stills), 24):
        batch = [str(path) for path in stills[number : number + 24]]
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "studio" / "sheet.py"),
                str(proof / f"sheet_{number // 24 + 1:02d}.png"),
                *batch,
                "--cols",
                "8",
                "--width",
                "270",
            ],
            check=True,
            capture_output=True,
        )
    print(f"frames: {len(times)} shot, sheets in {proof}")
    return finish(build, "frames", rows)


def engine_dir() -> Path:
    """The audio engine's folder, found as audio.py finds it: the batch's `engine` key, else <root>/engine.
    Read straight from batch.json, since the engine's own modules must not meet the studio's by name."""

    def at(value: str) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else (ROOT / path).resolve()

    try:
        data = json.loads((ROOT / "batch.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ROOT / "engine"
    return (
        at(data["engine"])
        if data.get("engine")
        else at(data.get("root") or ".") / "engine"
    )


def engine():
    """The engine's qa module (probe, loud, flash_report_file), from the batch's audio engine (engine_dir)."""
    import importlib.util

    folder = engine_dir()
    if str(folder) not in sys.path:
        # its own imports (contract, qa_scan) live there
        sys.path.insert(0, str(folder))
    spec = importlib.util.spec_from_file_location("engine_qa", folder / "qa.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"no engine qa.py in {folder}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def encoded(video: Path, expect: float, rows: list[dict]) -> list[str]:
    """Spec, length, loudness, flashes and black spans of the encoded file, each a V01 FIX when it fails.
    A check that cannot run is a V00 FIX and is named in the returned list: never a silent pass."""
    unchecked: list[str] = []
    try:
        tools = engine()
    except Exception as error:  # an import of numpy, Pillow or the engine itself
        row(
            rows,
            "V00",
            "FIX",
            None,
            f"the engine checks did not load: {error}",
            "run with numpy and pillow",
        )
        return ["spec", "length", "loudness", "flashes", "black"]
    try:
        info = tools.probe(str(video))
        print(
            f"spec: {info['w']}x{info['h']} {info['vcodec']} {info['pix']} {info['fps']} fps, "
            f"{info['duration']:.3f} s (timeline {expect:.3f} s), audio {info['acodec']}"
        )
        fps = info["fps"].split("/")
        rate = float(fps[0]) / float(fps[1] if len(fps) > 1 else 1)
        for ok, what in (
            (
                (info["w"], info["h"]) == (1080, 1920),
                f"{info['w']}x{info['h']}, not 1080x1920",
            ),
            (
                info["vcodec"] == "h264" and info["pix"] == "yuv420p",
                f"{info['vcodec']} {info['pix']}, not h264 yuv420p",
            ),
            (abs(rate - 30) < 0.01, f"{rate:g} fps, not 30"),
            (info["acodec"] is not None, "no audio stream"),
            (
                abs(info["duration"] - expect) <= 1 / 30 + 0.01,
                f"{info['duration']:.3f} s, the timeline says {expect:.3f} s",
            ),
        ):
            if not ok:
                row(rows, "V01", "FIX", None, what, "render again with render.py")
        # Evenly timed frames: a join between rendered parts once left every later frame a fraction of a
        # millisecond early (the average rate then reads 26519040/883963, not 30/1). No player shows it,
        # but a tool that pairs frames by time pairs neighbours from there on.
        even = (
            subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=avg_frame_rate",
                    "-of",
                    "csv=p=0",
                    str(video),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            .stdout.strip()
            .strip(",")
        )
        if even and even != "30/1":
            row(
                rows,
                "V01",
                "NOTE",
                None,
                f"the frames are not evenly timed (average rate {even})",
                "render again: render.py joins its parts by their exact lengths",
            )
    except Exception as error:
        unchecked += ["spec", "length"]
        row(
            rows,
            "V00",
            "FIX",
            None,
            f"ffprobe did not run: {error}",
            "the spec and length are NOT CHECKED",
        )
    try:
        level = tools.loud(str(video))
        print(f"loudness: {level['I']:.1f} LUFS, true peak {level['peak']:.1f} dBTP")
        if not -17.0 <= level["I"] <= -13.0 or level["peak"] > -1.0:
            row(
                rows,
                "V01",
                "FIX",
                None,
                f"loudness {level['I']:.1f} LUFS, true peak {level['peak']:.1f} dBTP",
                "master at -14 LUFS (1 LU either way), true peak at or under -1 dBTP",
            )
    except Exception as error:
        unchecked.append("loudness")
        row(
            rows,
            "V00",
            "FIX",
            None,
            f"the loudness check did not run: {error}",
            "loudness is NOT CHECKED",
        )
    try:
        for found in tools.flash_report_file(str(video)):
            if found.status == "FIX":
                row(
                    rows,
                    "V01",
                    "FIX",
                    found.t0,
                    found.msg,
                    found.fix or "at most three large brightness swings a second",
                )
            elif found.status == "NOT CHECKED":
                unchecked.append("flashes")
                row(
                    rows,
                    "V00",
                    "FIX",
                    None,
                    f"{found.code}: {found.msg}",
                    "flashes are NOT CHECKED",
                )
    except Exception as error:
        unchecked.append("flashes")
        row(
            rows,
            "V00",
            "FIX",
            None,
            f"the flash check did not run: {error}",
            "flashes are NOT CHECKED",
        )
    done = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-i",
            str(video),
            "-an",
            "-vf",
            "blackdetect=d=0.05:pix_th=0.10",
            "-f",
            "null",
            "-",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if done.returncode:
        unchecked.append("black")
        row(
            rows,
            "V00",
            "FIX",
            None,
            f"blackdetect did not run: {done.stderr.strip()[-120:]}",
            "black spans are NOT CHECKED",
        )
    for a, b in re.findall(r"black_start:([0-9.]+) black_end:([0-9.]+)", done.stderr):
        row(
            rows,
            "V01",
            "FIX",
            float(a),
            f"black from {float(a):.2f} to {float(b):.2f} s",
            "frame 0 is never black and no black gap between shots",
        )
    return unchecked


def file(build: Path, path: str | None) -> int:
    """The encoded file. Exit 1 on a FIX; 2 when a check could not run and nothing else is wrong."""
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    video = Path(path) if path else build / "out" / f"{timeline['slug']}.mp4"
    rows: list[dict] = []
    if not video.exists():
        row(
            rows,
            "V00",
            "FIX",
            None,
            f"no file at {video}",
            "render it first: the file is NOT CHECKED",
        )
        finish(build, "file", rows)
        return 2
    unchecked = encoded(video, timeline["duration"], rows)
    size = video.stat().st_size / 1e6
    if size > 95:
        row(
            rows,
            "V02",
            "FIX",
            None,
            f"the file is {size:.1f} MB",
            "under 95 MB: lower the maxrate",
        )
    try:
        import numpy as np
    except ImportError:
        unchecked.append("still stretches")
        row(
            rows,
            "V00",
            "FIX",
            None,
            "numpy is missing",
            "still stretches are NOT CHECKED",
        )
        finish(build, "file", rows)
        print(f"NOT CHECKED: {', '.join(dict.fromkeys(unchecked))}")
        return 1 if any(r["level"] == "FIX" and r["code"] != "V00" for r in rows) else 2
    raw = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-vf",
            "fps=4,scale=90:160,format=gray",
            "-f",
            "rawvideo",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    grid = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 160, 90).astype(float)
    change = np.abs(np.diff(grid, axis=0)).mean(axis=(1, 2))
    quiet = 0
    for index, value in enumerate(change):
        quiet = quiet + 1 if value < 0.35 else 0
        start = (index - 11) / 4
        # a shot marked exempt is still on purpose (the viewer is doing a test on it)
        held = any(a - 0.3 <= start < b for a, b in timeline.get("exempt", []))
        if quiet == 12 and index / 4 < timeline["duration"] - 3.5 and not held:
            row(
                rows,
                "V03",
                "FIX",
                (index - 11) / 4,
                "the picture does not change for 3 s",
                "add motion, a cut or an overlay there",
            )
    print(
        f"file: {size:.1f} MB, mean picture change {change.mean():.2f} (0 to 255, frames 0.25 s apart)"
    )
    code = finish(build, "file", rows)
    if unchecked:
        print(f"NOT CHECKED: {', '.join(dict.fromkeys(unchecked))}")
        if all(r["code"] == "V00" for r in rows if r["level"] == "FIX"):
            return 2
    return code


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["plan", "frames", "file"])
    parser.add_argument("build")
    parser.add_argument("--times")
    parser.add_argument("--video")
    args = parser.parse_args()
    build = Path(args.build) if Path(args.build).is_absolute() else ROOT / args.build
    code = {
        "plan": lambda: plan(build),
        "frames": lambda: frames(build, args.times),
        "file": lambda: file(build, args.video),
    }[args.command]()
    sys.exit(code)


if __name__ == "__main__":
    main()
