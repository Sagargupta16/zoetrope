"""Which frames of a film differ between two renders, and which shots they fall in.

  python studio/studio.py keep <build> <name>
  python studio/studio.py changed <build> [--before OLD.mp4] [--db 45]

`keep` copies the film in out/ and its timeline to out/<slug>_before_<name>.mp4 and .timeline.json before a
pass changes them. `changed` compares the film in out/ with such a copy (by default the newest one): ffmpeg's
psnr filter measures every frame pair. A re-encode of an unchanged frame stays far above the threshold
(measured 2026-11-25 on a 99 s film: median 50.8 dB) and a moved or changed element drops it (20 to 37 dB), so
the runs printed are the places where a pass changed the picture. A pass that named three shots and changed a
fourth shows here. Only the picture is compared: a change to the sound alone (voice, music, a cue) shows no run.

A run names every shot on screen during it: a shot shows from the first frame at or after its start, as the
renderer draws it, and an overlapping transition (whip, slide, zoom, fade, of length d) shows the incoming shot
from d/2 before the cut and keeps the outgoing one until d/2 after it, so a run inside one names both shots.

When the pass moved a cut (a gap grew, a shot was added) the two films no longer line up frame by frame. With
the kept timeline beside the kept film, `changed` then compares shot by shot: each shot's frames against the
same shot of the older film, from the shot's own first frame. That works because every motion in the kit runs
on its shot's or its device's own clock. Two things run on film time: the progress bar, so the top 12 px are
left out of that comparison, and the word captions, which follow the narration as the cuts do. It needs a
unique id per shot in both timelines, and a comparison that matched no shot of the kept timeline compared no
frame, so it is NOT CHECKED.

After the runs come up to three lines. "changed shots" names the shots that hold a changed frame, each with its
lowest value. "fine detail only, in clips" names the shots whose changed frames all show a clip (their
own, or a neighbour's through an overlapping transition) and pass two more measures: with both pictures scaled down 16 times every frame reads at or above the threshold, and no
block of 16 x 16 px differs by 24 of 255 or more in its mean brightness. A re-encoded clip of fine moving
texture reads so with nothing changed (measured 2026-11-26 on two films: 36.3 to 44.5 dB at full size, 49.5 to
54.4 dB scaled down, blocks of 4 to 11), while a moved label or a caption page read 30.8 and 35.6 dB scaled down
with blocks of 141 and 158; the first measure catches a change spread over the whole picture (a grade), the
second a small one. It is a reading, not a ruling: look at one frame of each. "cuts next to a changed shot" lists
the cuts into and out of the changed shots, each with the two times to give ffmpeg's -ss for the last frame
before it and the first after it, to look at as frame pairs: a drawing that stands on both sides of a cut has
to stand in the same place and size on both, or move there in one visible move.

Standard library only; needs ffmpeg and ffprobe on the path. Exit codes: 0 compared (or kept), 2 NOT CHECKED,
3 refused, 64 usage error.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

DB = 45.0  # dB: a frame pair under this average PSNR counts as changed
GAP = 2  # frames: two changed frames this close are one run
CROP = 12  # px at the top left out of a shot-by-shot comparison (the progress bar runs on film time)
COARSE = 16  # the second measures scale both pictures down this many times (so a block is 16 x 16 px)
BLOCK = 24.0  # of 255: a block whose mean brightness differs by this much holds a change, not encoder noise
TOL = 1e-6  # frames: a time this little after a frame's own time is float noise and reads as that frame
# (a time rounded to four places, 0.0667 for frame 2, lies a thousandth of a frame after it: that is a real
# step to the next frame, as the renderer draws it, so the tolerance must stay far under it)
# the tins that show both shots for d/2 either side of the cut (runtime.js OVERLAP)
OVERLAP = {"whip", "slide", "zoom", "fade"}
PASS, NOT_CHECKED, REFUSED = 0, 2, 3


def parse(text: str) -> list[tuple[int, float]]:
    """The psnr filter's stats lines as (frame index from 0, average PSNR in dB; inf for an identical pair)."""
    rows = []
    for line in text.splitlines():
        number = re.search(r"\bn:(\d+)", line)
        level = re.search(r"psnr_avg:(inf|[0-9.]+)", line)
        if number and level:
            rows.append((int(number.group(1)) - 1, float(level.group(1))))
    return rows


def parse_blocks(text: str) -> list[tuple[int, float]]:
    """The metadata filter's print lines as (frame index from 0, the largest value in that frame's picture)."""
    rows: list[tuple[int, float]] = []
    frame = None
    for line in text.splitlines():
        head = re.match(r"frame:(\d+)", line)
        if head:
            frame = int(head.group(1))
            continue
        level = re.search(r"YMAX=([0-9.]+)", line)
        if level and frame is not None:
            rows.append((frame, float(level.group(1))))
            frame = None
    return rows


def runs(
    rows: list[tuple[int, float]], limit: float = DB, gap: int = GAP
) -> list[tuple[int, int, float]]:
    """Runs of changed frames as (first frame, last frame, lowest dB in the run)."""
    found: list[list] = []
    for frame, level in rows:
        if level >= limit:
            continue
        if found and frame - found[-1][1] <= gap:
            found[-1][1] = frame
            found[-1][2] = min(found[-1][2], level)
        else:
            found.append([frame, frame, level])
    return [(first, last, low) for first, last, low in found]


def frame_at(seconds: float, fps: float) -> int:
    """The first frame at or after a time: the renderer draws frame f at f / fps and shows a shot from its start
    on, so a cut whose time sits a hair before its frame (every snapped cut on a repeating decimal) is that
    frame, and one a hair after it is the next."""
    return math.ceil(seconds * fps - TOL)


def lap(shot: dict | None) -> float:
    """Half the length of the shot's incoming transition when both shots show during it (runtime.js), else 0."""
    tin = shot.get("tin") if shot else None
    if not isinstance(tin, dict) or tin.get("kind") not in OVERLAP:
        return 0.0
    d = tin.get("d")
    if isinstance(d, bool) or not isinstance(d, (int, float)) or not math.isfinite(d):
        return 0.0
    return d / 2


def shots_in(timeline: dict, first: int, last: int) -> list[str]:
    """The ids of the shots on screen during a run of frames, in film order. A shot counts on the frames from
    its start to its end and, around an overlapping transition, on the frames where it lies under or over its
    neighbour, so a run inside a transition names both shots and a run that ends on a cut does not name the
    shot after the cut."""
    fps = timeline.get("fps", 30)
    shots = sorted(timeline.get("shots", []), key=lambda shot: shot["t0"])
    named = []
    for place, shot in enumerate(shots):
        after = shots[place + 1] if place + 1 < len(shots) else None
        start = frame_at(shot["t0"] - lap(shot), fps)
        stop = frame_at(shot["t1"] + lap(after), fps)
        if start <= last and stop > first:
            named.append(shot["id"])
    return named


def cuts(timeline: dict) -> list[tuple[str, int, int]]:
    """Every shot as (id, its first frame, the frame after its last), in film order."""
    fps = timeline.get("fps", 30)
    return [
        (shot["id"], frame_at(shot["t0"], fps), frame_at(shot["t1"], fps))
        for shot in timeline.get("shots", [])
    ]


def spans(timeline: dict) -> dict[str, tuple[int, int]]:
    """Every shot as (its first frame, the frame after its last), by id, in film order."""
    return {shot: (start, stop) for shot, start, stop in cuts(timeline)}


def fault(timeline: object) -> str:
    """Why a timeline's shot list cannot be read (a shot without a text id or a number t0 and t1), or ''."""
    shots = timeline.get("shots") if isinstance(timeline, dict) else None
    if not isinstance(shots, list):
        return "it has no shots list"
    for place, shot in enumerate(shots, 1):
        if not isinstance(shot, dict) or not isinstance(shot.get("id"), str):
            return f"shot {place} has no id"
        for key in ("t0", "t1"):
            value = shot.get(key)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            ):
                return f"shot {shot['id']} has no number {key}"
    return ""


def repeated(timeline: dict) -> list[str]:
    """The shot ids that more than one shot uses."""
    ids = [shot["id"] for shot in timeline.get("shots", [])]
    return sorted({shot for shot in ids if ids.count(shot) > 1})


def frames(path: Path) -> int | None:
    """The film's frame count, or None when ffprobe cannot say."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    done = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_packets",
            "-show_entries",
            "stream=nb_read_packets",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    digits = re.search(r"\d+", done.stdout)
    return int(digits.group(0)) if done.returncode == 0 and digits else None


def seek(frame: int, fps: float) -> list[str]:
    """Input options that start decoding at a frame: half a frame early, so the frame itself is never dropped."""
    return [] if frame <= 0 else ["-ss", f"{(frame - 0.5) / fps:.6f}"]


def measure(
    old: Path,
    new: Path,
    *,
    fps: float = 30,
    old_from: int = 0,
    new_from: int = 0,
    count: int | None = None,
    crop: int = 0,
    mode: str = "fine",
) -> tuple[list[tuple[int, float]] | None, str]:
    """Every frame pair's PSNR as (index from 0, dB), or None with the reason it could not be measured. With
    old_from, new_from and count it compares `count` frames from those two frames on; crop leaves out that
    many rows at the top of both pictures. mode "coarse" measures the PSNR with both pictures scaled down
    COARSE times, and mode "blocks" gives, in place of a PSNR, the largest difference in mean brightness over
    any block of COARSE x COARSE px (0 to 255)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None, "ffmpeg not found"
    with tempfile.TemporaryDirectory() as folder:
        stats = Path(folder) / "psnr.log"
        name = stats.as_posix().replace(
            ":", chr(92) + ":"
        )  # the filter reads a bare colon as an option separator
        cut = f"crop=iw:ih-{crop}:0:{crop}" if crop else "null"
        # psnr pairs frames by time, so both inputs are numbered afresh, frame n at n / fps. Their own times
        # will not do: a seeked input starts half a frame late and one at frame 0 does not, and a film whose
        # parts were joined can run a fraction of a millisecond early from a join on (measured 2026-11-25:
        # 0.65 ms after frame 2567 of a 115 s film), which paired every later frame with its neighbour.
        clock = f"setpts=N/({fps:g}*TB)"
        small = f"scale=iw/{COARSE}:ih/{COARSE}:flags=area"
        soft = f",{small}" if mode == "coarse" else ""
        if mode == "blocks":
            # 8-bit code values whatever the film's own depth: BLOCK is of 255
            soft = ",format=yuv420p"
        graph = f"[0:v]{clock},{cut}{soft}[n];[1:v]{clock},{cut}{soft}[o];[n][o]"
        if mode == "blocks":
            # the difference first, then the mean of each block: the brightest pixel left is the worst block
            graph += (
                f"blend=all_mode=difference,{small},signalstats,"
                f"metadata=print:key=lavfi.signalstats.YMAX:file='{name}'"
            )
        else:
            graph += f"psnr=stats_file='{name}'"
        limit = [] if count is None else ["-frames:v", str(count)]
        done = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                *seek(new_from, fps),
                "-i",
                str(new),
                *seek(old_from, fps),
                "-i",
                str(old),
                "-lavfi",
                graph,
                *limit,
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if done.returncode or not stats.is_file():
            return None, (done.stderr.strip().splitlines() or ["ffmpeg failed"])[-1]
        text = stats.read_text(encoding="utf-8")
        rows = parse_blocks(text) if mode == "blocks" else parse(text)
        return (rows if count is None else rows[:count]), ""


def sort_shots(
    timeline: dict,
    fine: dict[int, float],
    coarse: dict[int, float],
    blocks: dict[int, float],
    limit: float = DB,
) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    """The shots that hold a changed frame, in film order and in two lists of (id, lowest dB): the shots that
    changed, and the shots that differ in fine detail only. A shot is of the second kind when every one of its
    changed frames shows a clip (its own, or a neighbour's through an overlapping transition: clip_frames),
    reads at or above the limit with both pictures scaled down (coarse) and has no block that differs by BLOCK
    or more (blocks); a frame without both values keeps its shot in the first list. A frame belongs to the shot
    the cut gives it to."""
    on_clip = clip_frames(timeline)
    changed: list[tuple[str, float]] = []
    detail: list[tuple[str, float]] = []
    for shot, (start, stop) in spans(timeline).items():
        under = [
            frame for frame in range(start, stop) if fine.get(frame, math.inf) < limit
        ]
        if not under:
            continue
        low = min(fine[frame] for frame in under)
        calm = all(
            frame in on_clip
            and coarse.get(frame, -math.inf) >= limit
            and blocks.get(frame, math.inf) < BLOCK
            for frame in under
        )
        (detail if calm else changed).append((shot, low))
    return changed, detail


def cut_list(
    timeline: dict, ids: list[str], older: dict | None = None
) -> list[tuple[float, str, str]]:
    """The cuts into and out of the named shots as (time, the shot before, the shot after), in film order, each
    cut once. With the kept timeline of the older film it also lists every cut whose two shots did not follow
    each other there: when a shot is gone or two shots changed places, a cut between two unchanged shots is new."""
    shots = sorted(timeline.get("shots", []), key=lambda shot: shot["t0"])
    was = (
        None
        if older is None
        else sorted(older.get("shots", []), key=lambda shot: shot["t0"])
    )
    pairs = (
        None
        if was is None
        else {(a["id"], b["id"]) for a, b in zip(was, was[1:], strict=False)}
    )
    found = []
    for before, after in zip(shots, shots[1:], strict=False):
        pair = (before["id"], after["id"])
        if (
            pair[0] in ids
            or pair[1] in ids
            or (pairs is not None and pair not in pairs)
        ):
            found.append((after["t0"], *pair))
    return found


def clip_frames(timeline: dict) -> set[int]:
    """The frames on which a clip is on screen: every frame of a shot that plays a clip and, around an
    overlapping transition, the frames of its neighbour on which the clip already shows or still shows (the
    same window shots_in names a shot for). A fade or a whip into a clip carries the clip's re-encode onto the
    last frames of the shot before it."""
    fps = timeline.get("fps", 30)
    shots = sorted(timeline.get("shots", []), key=lambda shot: shot["t0"])
    found: set[int] = set()
    for place, shot in enumerate(shots):
        media = shot.get("media")
        if not isinstance(media, dict) or media.get("kind") != "clip":
            continue
        after = shots[place + 1] if place + 1 < len(shots) else None
        found.update(
            range(
                frame_at(shot["t0"] - lap(shot), fps),
                frame_at(shot["t1"] + lap(after), fps),
            )
        )
    return found


def clips_under(
    timeline: dict, fine: dict[int, float], limit: float
) -> list[tuple[str, int, int]]:
    """The shots that hold a changed frame on which a clip shows (their own, or a neighbour's through an
    overlapping transition), as (id, first frame, the frame after the last): the shots the second measures
    are taken for."""
    on_clip = clip_frames(timeline)
    return [
        (shot, start, stop)
        for shot, (start, stop) in spans(timeline).items()
        if any(
            frame in on_clip and fine.get(frame, math.inf) < limit
            for frame in range(start, stop)
        )
    ]


def tail(
    timeline: dict,
    fine: dict[int, float],
    coarse: dict[int, float],
    blocks: dict[int, float],
    moved: list[str],
    limit: float,
    older: dict | None = None,
) -> None:
    """Print which shots changed, which clips differ in fine detail only and the cuts next to a changed shot.
    moved names the shots that are new or changed their length: they changed whatever their frames read, so
    none of them is listed as fine detail. older is the kept timeline when the cuts moved (see cut_list)."""
    changed, detail = sort_shots(timeline, fine, coarse, blocks, limit)
    lows = dict(changed)
    lows.update((shot, low) for shot, low in detail if shot in moved)
    detail = [(shot, low) for shot, low in detail if shot not in moved]
    order = {shot["id"]: place for place, shot in enumerate(timeline.get("shots", []))}
    ids = sorted(
        set(lows) | {shot for shot in moved if shot in order},
        key=lambda item: order.get(item, 0),
    )
    if ids:
        print(
            "  changed shots: "
            + ", ".join(
                f"{shot} {lows[shot]:.1f} dB" if shot in lows else shot for shot in ids
            )
        )
    if detail:
        print(
            "  fine detail only, in clips: "
            + ", ".join(f"{shot} {low:.1f} dB" for shot, low in detail)
        )
        print(
            f"    (scaled down {COARSE} times each frame reads {limit:g} dB or more, and no block of {COARSE} px"
            f" differs by {BLOCK:g} of 255 or more: a re-encoded clip reads so with nothing changed; look at one"
            " frame of each)"
        )
    near = cut_list(timeline, ids, older)
    if near:
        fps = timeline.get("fps", 30)

        def pair(at: float) -> str:
            """The two times to seek to for the last frame before a cut and the first after it. ffmpeg's -ss
            gives the first frame at or after a time, so each lies half a frame before its frame (as seek())."""
            frame = frame_at(at, fps)
            return f"{(frame - 1.5) / fps:.3f} and {(frame - 0.5) / fps:.3f}"

        print(
            "  cuts next to a changed shot, to look at as frame pairs (ffmpeg -ss to each of the two times): "
            + ", ".join(
                f"{at:.3f} ({before} | {after}: {pair(at)})"
                for at, before, after in near
            )
        )


def kept_names(build: Path, slug: str, name: str) -> tuple[Path, Path]:
    stem = build / "out" / f"{slug}_before_{name}"
    return stem.with_suffix(".mp4"), stem.with_suffix(".timeline.json")


def read_timeline(build: Path) -> dict | None:
    try:
        timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
        return timeline if isinstance(timeline.get("slug"), str) else None
    except (OSError, ValueError, AttributeError):
        return None


def keep(build: Path, name: str) -> int:
    """Copy the film in out/ and its timeline to out/<slug>_before_<name>.*; a copy that exists is left alone,
    so a pass that starts twice keeps the film from before its first start."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        print(f"keep: the name {name!r} may hold letters, digits, - and _ only")
        return 64
    timeline = read_timeline(build)
    if timeline is None:
        print(
            "NOT CHECKED keep: no readable timeline.json with a slug (run build first)"
        )
        return NOT_CHECKED
    film = build / "out" / f"{timeline['slug']}.mp4"
    if not film.is_file():
        print(f"NOT CHECKED keep: missing {film} (run render first)")
        return NOT_CHECKED
    video, plan = kept_names(build, timeline["slug"], name)
    if video.is_file():
        print(f"kept already, not overwritten: {video}")
        return PASS
    if (build / "timeline.json").stat().st_mtime > film.stat().st_mtime:
        print(
            "REFUSED keep: timeline.json is newer than the film in out/, so that film was not rendered from it"
            " (keep before you change the plan, or render first)"
        )
        return REFUSED
    shutil.copyfile(build / "timeline.json", plan)
    shutil.copyfile(film, video)
    print(f"kept: {video}")
    print(f"kept: {plan}")
    return PASS


def line(first: int, last: int, low: float, fps: float, ids: list[str]) -> str:
    return (
        f"  frames {first} to {last} ({first / fps:.2f} to {(last + 1) / fps:.2f} s), lowest {low:.1f} dB,"
        f" shots {', '.join(ids) or 'none'}"
    )


def by_shot(
    old: Path,
    new: Path,
    before: dict,
    timeline: dict,
    limit: float,
    seen: dict | None = None,
) -> tuple[int, list[str], int, int, int]:
    """Compare shot by shot. Returns (exit code, touched shot ids, runs, changed frames, compared frames) and
    prints one line per run, per shot whose length changed, per new shot and per shot that is gone. A dict
    given as seen is filled for `tail`: "fine", "coarse" and "blocks" hold each measure by the new film's
    frame number (the last two for the clips that hold a changed frame), and "moved" names the shots that are
    new or changed their length."""
    fps = timeline.get("fps", 30)
    was, now = spans(before), spans(timeline)
    touched: list[str] = []
    found = changed = compared = 0
    code = PASS
    if seen is not None:
        seen.update({"fine": {}, "coarse": {}, "blocks": {}, "moved": []})
    for shot, (start, stop) in now.items():
        if shot not in was:
            print(f"  shot {shot}: new (frames {start} to {stop - 1})")
            touched.append(shot)
            if seen is not None:
                seen["moved"].append(shot)
            continue
        old_start, old_stop = was[shot]
        count = min(stop - start, old_stop - old_start)
        if stop - start != old_stop - old_start:
            more = (stop - start) - (old_stop - old_start)
            print(
                f"  shot {shot}: {abs(more)} frames {'longer' if more > 0 else 'shorter'}"
                f" ({old_stop - old_start} to {stop - start})"
            )
            touched.append(shot)
            if seen is not None:
                seen["moved"].append(shot)
        if count <= 0:
            continue
        rows, problem = measure(
            old,
            new,
            fps=fps,
            old_from=old_start,
            new_from=start,
            count=count,
            crop=CROP,
        )
        if not rows:
            print(f"  NOT CHECKED shot {shot}: {problem or 'ffmpeg compared no frame'}")
            code = NOT_CHECKED
            continue
        compared += len(rows)
        if seen is not None:
            seen["fine"].update((start + index, level) for index, level in rows)
            if clips_under(
                timeline, {start + index: level for index, level in rows}, limit
            ):
                # this shot plays a clip and holds a changed frame: the two measures that tell a re-encode
                # from a change (a measure that fails leaves the shot among the changed ones)
                for mode in ("coarse", "blocks"):
                    more_rows, _ = measure(
                        old,
                        new,
                        fps=fps,
                        old_from=old_start,
                        new_from=start,
                        count=count,
                        crop=CROP,
                        mode=mode,
                    )
                    seen[mode].update(
                        (start + index, level) for index, level in more_rows or []
                    )
        for first, last, low in runs(rows, limit):
            # the shots on screen in either film: a run inside a transition names both shots of it
            ids = shots_in(timeline, start + first, start + last)
            ids += [
                other
                for other in shots_in(before, old_start + first, old_start + last)
                if other in now and other not in ids
            ]
            ids.sort(key=list(now).index)
            print(line(start + first, start + last, low, fps, ids))
            found += 1
            changed += last - first + 1
            touched.extend(other for other in ids if other not in touched)
    gone = [shot for shot in was if shot not in now]
    for shot in gone:
        print(f"  shot {shot}: gone")
    if code == PASS and not compared:
        print(
            "  NOT CHECKED no frame compared: no shot of the kept timeline is in the new one under the same id"
        )
        code = NOT_CHECKED
    order = {shot: place for place, shot in enumerate(now)}
    touched.sort(key=lambda item: order.get(item, 0))
    return code, touched + [f"{shot} (gone)" for shot in gone], found, changed, compared


def report(build: Path, before: Path | None = None, limit: float = DB) -> int:
    """Print the changed runs of the build's film against an older render; 0 when compared, 2 when not."""
    timeline = read_timeline(build)
    if timeline is None:
        print(
            "NOT CHECKED changed: no readable timeline.json with a slug (run build first)"
        )
        return NOT_CHECKED
    slug = timeline["slug"]
    new = build / "out" / f"{slug}.mp4"
    if not new.is_file():
        print(f"NOT CHECKED changed: missing {new} (run render first)")
        return NOT_CHECKED
    if before is None:
        kept = sorted(
            (build / "out").glob(f"{slug}_before_*.mp4"),
            key=lambda path: path.stat().st_mtime,
        )
        if not kept:
            print(
                f"NOT CHECKED changed: no {slug}_before_*.mp4 in {build / 'out'}; keep one with `keep`, or name"
                " the older film with --before"
            )
            return NOT_CHECKED
        before = kept[-1]
    elif not before.is_file():
        print(f"NOT CHECKED changed: missing {before}")
        return NOT_CHECKED
    if fault(timeline):
        print(
            f"NOT CHECKED changed: timeline.json: {fault(timeline)} (run build again)"
        )
        return NOT_CHECKED
    fps = timeline.get("fps", 30)
    older = None
    plan = before.with_suffix(".timeline.json")
    if plan.is_file():
        try:
            older = json.loads(plan.read_text(encoding="utf-8"))
            why = fault(older)
        except ValueError:
            why = "it is not JSON"
        if why:
            print(
                f"NOTE {plan.name} cannot be read ({why}), so the films are compared frame by frame"
            )
            older = None
    if older is not None and cuts(older) != cuts(timeline):
        twice = [
            f"{shot} in {name}"
            for plan_of, name in ((older, plan.name), (timeline, "timeline.json"))
            for shot in repeated(plan_of)
        ]
        if twice:
            print(
                f"NOT CHECKED changed: the cuts moved, and a shot id is used twice ({', '.join(twice)}), so the"
                " shots of the two films cannot be matched"
            )
            return NOT_CHECKED
        print(
            f"changed: {new.name} against {before.name}, shot by shot (the cuts moved), threshold {limit:g} dB,"
            f" top {CROP} px left out"
        )
        seen: dict = {}
        code, touched, found, changed, compared = by_shot(
            before, new, older, timeline, limit, seen
        )
        print(
            f"changed: {found} runs, {changed} of {compared} frames, shots: {', '.join(touched) or 'none'}"
        )
        tail(
            timeline,
            seen["fine"],
            seen["coarse"],
            seen["blocks"],
            seen["moved"],
            limit,
            older,
        )
        return code
    rows, problem = measure(before, new, fps=fps)
    if not rows:
        print(f"NOT CHECKED changed: {problem or 'ffmpeg compared no frame'}")
        return NOT_CHECKED
    print(
        f"changed: {new.name} against {before.name}, {len(rows)} frame pairs, threshold {limit:g} dB"
    )
    counts = frames(before), frames(new)
    if None not in counts and counts[0] != counts[1]:
        print(
            f"NOTE the two films differ in length ({counts[0]} and {counts[1]} frames) and no readable kept timeline lies"
            f" beside {before.name}: from the first moved cut on every frame differs, so only the runs before it"
            " say what changed (`keep` saves the timeline with the film)"
        )
    found = runs(rows, limit)
    order = {shot["id"]: place for place, shot in enumerate(timeline.get("shots", []))}
    touched: set[str] = set()
    for first, last, low in found:
        ids = shots_in(timeline, first, last)
        touched.update(ids)
        print(line(first, last, low, fps, ids))
    names = ", ".join(sorted(touched, key=lambda item: order.get(item, 0))) or "none"
    print(
        f"changed: {len(found)} runs, {sum(last - first + 1 for first, last, _ in found)} of {len(rows)} frames,"
        f" shots: {names}"
    )
    fine = dict(rows)
    more: dict[str, dict[int, float]] = {"coarse": {}, "blocks": {}}
    if clips_under(timeline, fine, limit):
        for mode in more:
            again, why = measure(before, new, fps=fps, mode=mode)
            if again:
                more[mode] = dict(again)
            else:
                print(
                    f"  NOTE the {mode} measure failed ({why or 'ffmpeg compared no frame'}), so every clip"
                    " that holds a changed frame is listed as changed"
                )
    tail(timeline, fine, more["coarse"], more["blocks"], [], limit)
    return PASS


def moved_cut_test(problems: list[str]) -> bool:
    """Three short test films, the second with ten new frames between its two shots, the third the second shot
    alone: the shot-by-shot comparison must find both old shots unchanged and one new shot, the plain
    comparison of the same pair must not, and a comparison from the right frames (also when only the old film
    seeks) must find nothing while one a frame off finds a change, so a seek that lands on the wrong frame or
    does nothing fails. False when ffmpeg is missing (the test is skipped)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        first, second = base / "a.mp4", base / "b.mp4"
        common = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "12", "-crf", "12"]
        made = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=320x568:rate=30:duration=2",
                *common,
                str(first),
            ],
            capture_output=True,
            check=False,
        )
        graph = (
            "[0:v]split[x][y];[x]trim=end_frame=30,setpts=PTS-STARTPTS[a];"
            "[y]trim=start_frame=30,setpts=PTS-STARTPTS[c];"
            "color=c=gray:size=320x568:rate=30:duration=0.3334,trim=end_frame=10,format=yuv420p[b];"
            "[a][b][c]concat=n=3:v=1:a=0"
        )
        made2 = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-y",
                "-i",
                str(first),
                "-lavfi",
                graph,
                *common,
                str(second),
            ],
            capture_output=True,
            check=False,
        )
        # the second shot alone: a shot that moved to the start of the film
        third = base / "c.mp4"
        made3 = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-y",
                "-i",
                str(first),
                "-vf",
                "trim=start_frame=30,setpts=PTS-STARTPTS",
                *common,
                str(third),
            ],
            capture_output=True,
            check=False,
        )
        if (
            made.returncode
            or made2.returncode
            or made3.returncode
            or frames(second) != 70
            or frames(third) != 30
        ):
            problems.append(
                f"the test films were not made ({made.returncode}, {made2.returncode}, {made3.returncode},"
                f" {frames(second)} and {frames(third)} frames)"
            )
            return True
        before = {
            "fps": 30,
            "shots": [
                {"id": "s1", "t0": 0.0, "t1": 1.0},
                {"id": "s2", "t0": 1.0, "t1": 2.0},
            ],
        }
        after = {
            "fps": 30,
            "shots": [
                {"id": "s1", "t0": 0.0, "t1": 1.0},
                {"id": "mid", "t0": 1.0, "t1": 1.3333},
                {"id": "s2", "t0": 1.3333, "t1": 2.3333},
            ],
        }
        import contextlib
        import io

        quiet = io.StringIO()
        with contextlib.redirect_stdout(quiet):
            code, touched, found, _, compared = by_shot(
                first, second, before, after, 30.0
            )
        if (code, touched, found, compared) != (PASS, ["mid"], 0, 60):
            problems.append(
                f"moved cut: by_shot gave {(code, touched, found, compared)}: {quiet.getvalue()!r}"
            )
        rows, _ = measure(first, second, fps=30)
        plain = runs(rows or [], 30.0)
        if not plain or plain[0][0] != 30:
            problems.append(f"moved cut: the plain comparison gave {plain[:2]}")
        # one frame off must show: the same shot compared from the wrong frame is a changed shot
        rows, _ = measure(first, second, fps=30, old_from=30, new_from=41, count=20)
        if not runs(rows or [], 30.0):
            problems.append(
                "moved cut: a comparison one frame off found nothing changed"
            )
        # only the old film seeks (the shot is first in the new film): the frames must still pair up, and one
        # frame off must still show
        rows, _ = measure(first, third, fps=30, old_from=30, new_from=0, count=20)
        if len(rows or []) != 20 or runs(rows, 30.0):
            problems.append(
                f"moved to the start: {len(rows or [])} frames compared, runs {runs(rows or [], 30.0)[:2]}"
            )
        rows, _ = measure(first, third, fps=30, old_from=31, new_from=0, count=20)
        if not runs(rows or [], 30.0):
            problems.append(
                "moved to the start: a comparison one frame off found nothing changed"
            )
        # the same pictures with timestamps that run 0.7 ms early from frame 20 on (what a join between two
        # rendered parts can leave): frames must still pair by number, so nothing reads as changed
        slipped = base / "d.mp4"
        made4 = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-y",
                "-i",
                str(first),
                "-c",
                "copy",
                "-bsf:v",  # 11 ticks of 1/15360 s; a filter would round the slip away in its 1/30 time base
                "setts=pts=PTS-gte(N"
                + chr(92)
                + ",20)*11:dts=DTS-gte(N"
                + chr(92)
                + ",20)*11",
                str(slipped),
            ],
            capture_output=True,
            check=False,
        )
        if made4.returncode or frames(slipped) != 60:
            problems.append(
                f"timestamp slip: the test film was not made ({made4.returncode}, {frames(slipped)} frames)"
            )
        else:
            rows, _ = measure(first, slipped, fps=30)
            if len(rows or []) != 60 or runs(rows, 30.0):
                problems.append(
                    f"timestamp slip: {len(rows or [])} frames compared, runs {runs(rows or [], 30.0)[:2]}"
                )
            rows, _ = measure(
                first, slipped, fps=30, old_from=30, new_from=30, count=20
            )
            if len(rows or []) != 20 or runs(rows, 30.0):
                problems.append(
                    f"timestamp slip, seeked: {len(rows or [])} frames compared, runs {runs(rows or [], 30.0)[:2]}"
                )
    return True


def detail_test(problems: list[str]) -> bool:
    """Four short test films of one noisy picture: the same film encoded twice (fine detail only), one with a
    small box drawn in (the block measure must catch it) and one made a little brighter (the block measure
    misses that, so the scaled-down PSNR must catch it). The first pair must read as fine detail and the other
    two as changed, through `measure` and through `by_shot`. False when ffmpeg is missing (the test is
    skipped)."""
    import contextlib
    import io

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    # what each pair has to show for the test to mean anything: (fine, coarse, worst block) -> bool
    legs = {
        "again": lambda fine, coarse, block: fine < DB <= coarse and block < BLOCK,
        "boxed": lambda fine, coarse, block: fine < DB and block >= BLOCK,
        "bright": lambda fine, coarse, block: coarse < DB and block < BLOCK,
    }
    with tempfile.TemporaryDirectory() as folder:
        base = Path(folder)
        source = base / "source.mp4"
        codec = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "12"]
        picture = (
            "testsrc2=size=320x568:rate=30:duration=1,noise=alls=10:allf=t:all_seed=7"
        )
        made = [
            subprocess.run(
                [ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", picture]
                + codec
                + ["-crf", "0", str(source)],
                capture_output=True,
                check=False,
            ).returncode
        ]
        films = {
            "first": ("null", "12"),
            "again": ("null", "20"),
            "boxed": ("drawbox=x=120:y=200:w=40:h=20:color=white:t=fill", "12"),
            "bright": ("eq=brightness=0.04", "12"),
        }
        for name, (change, quality) in films.items():
            made.append(
                subprocess.run(
                    [ffmpeg, "-v", "error", "-y", "-i", str(source), "-vf", change]
                    + codec
                    + ["-crf", quality, str(base / f"{name}.mp4")],
                    capture_output=True,
                    check=False,
                ).returncode
            )
        if any(made):
            problems.append(f"the fine detail test films were not made ({made})")
            return True
        # two shots, so the shot-by-shot comparison takes its second measures after a seek (the clip starts at
        # frame 15); the first shot shows a still, which is never fine detail
        plan = {
            "fps": 30,
            "shots": [
                {"id": "c0", "t0": 0.0, "t1": 0.5, "media": {"kind": "still"}},
                {"id": "c1", "t0": 0.5, "t1": 1.0, "media": {"kind": "clip"}},
            ],
        }
        first = base / "first.mp4"
        want = {
            "again": (["c0"], ["c1"]),
            "boxed": (["c0", "c1"], []),
            "bright": (["c0", "c1"], []),
        }
        for name, (changed, detail) in want.items():
            other = base / f"{name}.mp4"
            read = {}
            for mode in ("fine", "coarse", "blocks"):
                rows, why = measure(other, first, mode=mode)
                if not rows or len(rows) != 30:
                    problems.append(
                        f"fine detail test: the {mode} measure of {name} gave {len(rows or [])} rows ({why})"
                    )
                read[mode] = dict(rows or [])
            got = sort_shots(plan, read["fine"], read["coarse"], read["blocks"], DB)
            if ([shot for shot, _ in got[0]], [shot for shot, _ in got[1]]) != (
                changed,
                detail,
            ):
                problems.append(
                    f"fine detail test: {name} sorted as {got}; lowest fine {min(read['fine'].values(), default=0):.1f},"
                    f" lowest coarse {min(read['coarse'].values(), default=0):.1f}, worst block"
                    f" {max(read['blocks'].values(), default=0):.0f}"
                )
            lows = (
                min(read["fine"].values(), default=0.0),
                min(read["coarse"].values(), default=0.0),
                max(read["blocks"].values(), default=0.0),
            )
            if not legs[name](*lows):
                problems.append(
                    f"fine detail test: {name} does not test its measure (lowest fine {lows[0]:.1f}, lowest"
                    f" coarse {lows[1]:.1f}, worst block {lows[2]:.0f})"
                )
            seen: dict = {}
            with contextlib.redirect_stdout(io.StringIO()):
                by_shot(other, first, plan, plan, DB, seen)
            again = sort_shots(plan, seen["fine"], seen["coarse"], seen["blocks"], DB)
            if ([shot for shot, _ in again[0]], [shot for shot, _ in again[1]]) != (
                changed,
                detail,
            ):
                problems.append(
                    f"fine detail test: shot by shot, {name} sorted as {again}"
                )
    return True


def selftest() -> int:
    """The comparison's own arithmetic (the stats lines it reads, how changed frames join into runs, which
    shots a run names, how the second measures sort a clip) and, when ffmpeg is on the path, a moved cut on
    two test films and fine detail against a change on four."""
    problems: list[str] = []
    stats = "\n".join(
        [
            "n:1 mse_avg:0.00 psnr_avg:inf psnr_y:inf",
            "n:2 mse_avg:0.41 psnr_avg:52.03 psnr_y:51.2",
            "n:3 mse_avg:90.1 psnr_avg:28.58 psnr_y:27.9",
            "n:4 mse_avg:0.39 psnr_avg:52.21 psnr_y:51.4",
            "n:5 mse_avg:120.5 psnr_avg:27.32 psnr_y:26.1",
            "n:9 mse_avg:75.2 psnr_avg:29.37 psnr_y:28.8",
        ]
    )
    rows = parse(stats)
    if [frame for frame, _ in rows] != [0, 1, 2, 3, 4, 8] or rows[0][1] != float("inf"):
        problems.append(f"parse read {rows}")
    found = runs(rows, 45.0)
    if found != [(2, 4, 27.32), (8, 8, 29.37)]:
        problems.append(f"runs gave {found}")
    timeline = {
        "fps": 30,
        "shots": [
            {"id": "s01", "t0": 0.0, "t1": 0.1},
            {"id": "s02", "t0": 0.1, "t1": 1.0},
        ],
    }
    named = [
        shots_in(timeline, 0, 2),
        shots_in(timeline, 2, 4),
        shots_in(timeline, 3, 8),
    ]
    if named != [["s01"], ["s01", "s02"], ["s02"]]:
        problems.append(f"shots_in gave {named}")
    if spans(timeline) != {"s01": (0, 3), "s02": (3, 30)}:
        problems.append(f"spans gave {spans(timeline)}")
    # a snapped cut sits a hair before its frame (1.2333 is frame 36.999): a run that ends on it names one shot
    snapped = {
        "fps": 30,
        "shots": [
            {"id": "s01", "t0": 0.0, "t1": 1.2333},
            {"id": "s02", "t0": 1.2333, "t1": 3.0},
        ],
    }
    if [shots_in(snapped, 0, 36), shots_in(snapped, 37, 40)] != [["s01"], ["s02"]]:
        problems.append(
            f"snapped cut: shots_in gave {shots_in(snapped, 0, 36)} and {shots_in(snapped, 37, 40)}"
        )
    # a time off its frame starts on the next frame, as the renderer draws it; 8.3 is frame 249 although
    # 8.3 * 30 is 249.00000000000003 in floats
    loose = {
        "fps": 30,
        "shots": [
            {"id": "a", "t0": 1.35, "t1": 8.3},
            {"id": "b", "t0": 40.4667, "t1": 41.0},
        ],
    }
    if spans(loose) != {"a": (41, 249), "b": (1215, 1230)}:
        problems.append(f"a time off its frame: spans gave {spans(loose)}")
    # a fade of 0.4 s shows A and B together on frames 24 to 35: a run there names both
    faded = {
        "fps": 30,
        "shots": [
            {"id": "A", "t0": 0.0, "t1": 1.0},
            {"id": "B", "t0": 1.0, "t1": 2.0, "tin": {"kind": "fade", "d": 0.4}},
        ],
    }
    named = [shots_in(faded, *run) for run in ((0, 23), (24, 29), (30, 35), (36, 59))]
    if named != [["A"], ["A", "B"], ["A", "B"], ["B"]]:
        problems.append(f"a fade: shots_in gave {named}")
    if (fault({"shots": [{"id": "a", "t0": 0}]}), fault({}), fault(timeline)) != (
        "shot a has no number t1",
        "it has no shots list",
        "",
    ) or repeated({"shots": [{"id": "x"}, {"id": "y"}, {"id": "x"}]}) != ["x"]:
        problems.append("fault or repeated misread a timeline")
    # no shot id in common: nothing was compared, so it is not checked
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        none = by_shot(
            Path("old.mp4"),
            Path("new.mp4"),
            {"fps": 30, "shots": [{"id": "x1", "t0": 0.0, "t1": 1.0}]},
            {"fps": 30, "shots": [{"id": "y1", "t0": 0.0, "t1": 1.0}]},
            45.0,
        )
    if none[0] != NOT_CHECKED or none[4] != 0:
        problems.append(f"no shot in common: by_shot gave {none}")
    if seek(0, 30) != [] or seek(30, 30) != ["-ss", "0.983333"]:
        problems.append(f"seek gave {seek(0, 30)} and {seek(30, 30)}")
    # the second measures: only a clip whose changed frames all pass both reads as fine detail
    printed = "\n".join(
        [
            "frame:0    pts:0       pts_time:0",
            "lavfi.signalstats.YMAX=7",
            "frame:1    pts:1       pts_time:0.0333",
            "lavfi.signalstats.YMAX=141",
        ]
    )
    if parse_blocks(printed) != [(0, 7.0), (1, 141.0)]:
        problems.append(f"parse_blocks read {parse_blocks(printed)}")
    mixed = {
        "fps": 30,
        "shots": [
            {"id": "a", "t0": 0.0, "t1": 1.0, "media": {"kind": "still"}},
            {"id": "b", "t0": 1.0, "t1": 2.0, "media": {"kind": "clip"}},
            {"id": "c", "t0": 2.0, "t1": 3.0, "media": {"kind": "clip"}},
            {"id": "d", "t0": 3.0, "t1": 4.0, "media": {"kind": "clip"}},
            {"id": "e", "t0": 4.0, "t1": 5.0, "media": {"kind": "none"}},
        ],
    }
    fine = {10: 30.0, 40: 38.0, 41: 39.0, 70: 37.0, 100: 44.0, 130: 50.0}
    coarse = {10: 50.0, 40: 50.0, 41: 47.0, 70: 50.0, 100: 41.0}
    blocks = {10: 5.0, 40: 9.0, 41: 11.0, 70: 42.0, 100: 6.0}
    sorted_ = sort_shots(mixed, fine, coarse, blocks, 45.0)
    # a: not a clip; b: both measures pass; c: one block differs; d: still low when scaled down; e: no frame
    if sorted_ != ([("a", 30.0), ("c", 37.0), ("d", 44.0)], [("b", 38.0)]):
        problems.append(f"sort_shots gave {sorted_}")
    if sort_shots(mixed, {40: 38.0}, {}, {}, 45.0) != ([("b", 38.0)], []):
        problems.append(
            "sort_shots took a clip without its second measures for fine detail"
        )
    if clips_under(mixed, fine, 45.0) != [("b", 30, 60), ("c", 60, 90), ("d", 90, 120)]:
        problems.append(f"clips_under gave {clips_under(mixed, fine, 45.0)}")
    near = cut_list(mixed, ["a", "c"])
    if near != [(1.0, "a", "b"), (2.0, "b", "c"), (3.0, "c", "d")]:
        problems.append(f"cut_list gave {near}")
    if cut_list(mixed, ["e"]) != [(4.0, "d", "e")] or cut_list(mixed, []) != []:
        problems.append("cut_list misread the last shot or an empty list")
    # the older film had a shot x between b and c: with x gone, the cut from b to c is new though neither changed
    with_x = {
        "fps": 30,
        "shots": [
            {"id": name, "t0": start, "t1": start + 1.0}
            for name, start in zip(
                "abxcde", (0.0, 1.0, 2.0, 3.0, 4.0, 5.0), strict=True
            )
        ],
    }
    if cut_list(mixed, [], with_x) != [(2.0, "b", "c")] or cut_list(mixed, [], mixed):
        problems.append(
            f"cut_list with the older timeline gave {cut_list(mixed, [], with_x)} and {cut_list(mixed, [], mixed)}"
        )
    # a fade into a clip shows the clip on the last frames of the still before it: re-encode noise there is
    # fine detail for both shots, and a changed frame of the still outside the fade keeps it among the changed
    faded_clip = {
        "fps": 30,
        "shots": [
            {"id": "A", "t0": 0.0, "t1": 1.0, "media": {"kind": "still"}},
            {
                "id": "B",
                "t0": 1.0,
                "t1": 2.0,
                "media": {"kind": "clip"},
                "tin": {"kind": "fade", "d": 0.4},
            },
            {
                "id": "C",
                "t0": 2.0,
                "t1": 3.0,
                "media": {"kind": "still"},
                "tin": {"kind": "fade", "d": 0.4},
            },
        ],
    }
    # the clip B shows on frames 24 to 65: the last six of A, its own, and the first six of C
    noise = dict.fromkeys(range(24, 66), 40.0)
    for name, extra, want in (
        ("a fade into and out of a clip", {}, ([], ["A", "B", "C"])),
        ("a still changed before the fade in", {10: 40.0}, (["A"], ["B", "C"])),
        ("a still changed after the fade out", {80: 40.0}, (["C"], ["A", "B"])),
    ):
        read = {**noise, **extra}
        got = sort_shots(
            faded_clip, read, dict.fromkeys(read, 50.0), dict.fromkeys(read, 5.0), 45.0
        )
        if ([shot for shot, _ in got[0]], [shot for shot, _ in got[1]]) != want:
            problems.append(f"{name}: sort_shots gave {got}")
    if [shot for shot, _, _ in clips_under(faded_clip, noise, 45.0)] != ["A", "B", "C"]:
        problems.append(
            f"a fade into and out of a clip: clips_under gave {clips_under(faded_clip, noise, 45.0)}"
        )
    # a clip whose length changed is a changed shot, never fine detail
    with contextlib.redirect_stdout(io.StringIO()) as said:
        tail(mixed, fine, coarse, blocks, ["b"], 45.0)
    lines = said.getvalue().splitlines()
    if (
        len(lines) != 2
        or lines[0] != "  changed shots: a 30.0 dB, b 38.0 dB, c 37.0 dB, d 44.0 dB"
    ):
        problems.append(f"tail with a moved clip printed {lines}")
    with contextlib.redirect_stdout(io.StringIO()) as said:
        tail(mixed, fine, coarse, blocks, ["e"], 45.0)
    lines = said.getvalue().splitlines()
    if (
        len(lines) != 4
        or lines[0] != "  changed shots: a 30.0 dB, c 37.0 dB, d 44.0 dB, e"
        or lines[1] != "  fine detail only, in clips: b 38.0 dB"
        or not lines[3].endswith(
            "1.000 (a | b: 0.950 and 0.983), 2.000 (b | c: 1.950 and 1.983),"
            " 3.000 (c | d: 2.950 and 2.983), 4.000 (d | e: 3.950 and 3.983)"
        )
    ):
        problems.append(f"tail printed {lines}")
    films = moved_cut_test(problems)
    measures = detail_test(problems)
    for problem in problems:
        print(f"FAIL {problem}")
    parts = (
        "stats lines, runs, shots, the two second measures"
        + (
            ", a moved cut on two test films"
            if films
            else "; no ffmpeg, so the moved cut was not tried"
        )
        + (", fine detail against a change on four test films" if measures else "")
    )
    print("FILMDIFF: FAIL" if problems else f"FILMDIFF: PASS ({parts})")
    return 1 if problems else 0


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    print(__doc__, file=sys.stderr)
    sys.exit(64)
