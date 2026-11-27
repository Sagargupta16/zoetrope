"""The studio's own selftest: run it before trusting a change to the studio.

  python -I studio/selftest.py --quick           the lint's rules, shotkit, a drawn probe film's timeline (standard library only)
  python studio/selftest.py --render             also render the probe at four times and compare the frames with the golden (needs
                                                 playwright, Chrome, Pillow, numpy: uv run --no-project --with-requirements studio/requirements.txt)
                                                 and check that a film with one frame five ticks short is refused by the
                                                 file check and by package
  python studio/selftest.py --bless              --render, then write selftest/golden/<os>/frames.json (look at the frames first)
  python studio/selftest.py --bless-timeline     rebuild selftest/probe/timeline.golden.json after a deliberate build.py change

Prints one ok or FAIL line per part, then "STUDIO SELFTEST: PASS (<n> parts)" or "STUDIO SELFTEST: FAIL (...)"; exit 0 or 1.
The probe (selftest/probe/) is a film of three lines and four drawn shots with hand-written word times: no picture is
generated and no voice is made, so it builds the same on every machine.

A rendered frame is compared by its PNG sha256 first. Chrome's GPU rasteriser is not bit-stable: two runs of the
same code can differ by one or two levels on a few edge pixels of large type (measured 2026-11-25: 3 to 58 pixels
of a frame, in the probe and in a finished film alike). So a frame whose digest differs is compared by the mean
colour of each 60 px block, which that jitter moves by under 0.05 of 255 and a moved, missing or recoloured
element moves by whole levels; the line printed says how many frames matched by digest and how many by blocks.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

STUDIO = Path(__file__).resolve().parent
PROBE = STUDIO / "selftest" / "probe"
GOLDEN_TIMELINE = PROBE / "timeline.golden.json"
OPTIONS = (
    STUDIO / "selftest" / "options" / "shots.json"
)  # part_options: carried overlays and the end card
FRAME_TIMES = (0.5, 2.5, 4.0, 8.0)
BLOCK = 60  # px: the side of a block when a frame is compared by its mean colours
JITTER = 0.25  # of 255: how far a block's mean colour may sit from the golden's
HOST = platform.system().lower()


def run(*args: object, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )


def last_line(done: subprocess.CompletedProcess) -> str:
    lines = (done.stdout + done.stderr).strip().splitlines()
    return lines[-1] if lines else "(no output)"


def part_lint() -> str | None:
    done = run(STUDIO / "lint.py", "selftest")
    if done.returncode or "LINT SELFTEST: PASS" not in done.stdout:
        return f"lint selftest: {last_line(done)}"
    return None


def part_shotkit() -> str | None:
    done = run(STUDIO / "shotkit.py", "--selftest")
    if done.returncode or "SHOTKIT: PASS" not in done.stdout:
        return f"shotkit selftest: {last_line(done)}"
    return None


def part_batch() -> str | None:
    done = run(STUDIO / "batch.py", "selftest")
    if done.returncode or "BATCH SELFTEST: PASS" not in done.stdout:
        return f"batch selftest: {last_line(done)}"
    return None


def part_gen() -> str | None:
    done = run(STUDIO / "gen.py", "selftest")
    if done.returncode or "GEN SELFTEST: PASS" not in done.stdout:
        return f"gen selftest: {last_line(done)}"
    return None


def part_negators() -> str | None:
    """The caption pager (kit.js) and the lint's L13 (lint.py) must hold the same negators: when they differ the
    pager makes pages the lint then fails, and no rewording by the builder is the right fix."""
    pager = re.search(
        r"const NEGATORS = \[([^\]]*)\]",
        (STUDIO / "kit.js").read_text(encoding="utf-8"),
    )
    lint = re.search(
        r"^NEGATORS = \{([^}]*)\}",
        (STUDIO / "lint.py").read_text(encoding="utf-8"),
        re.M,
    )
    if not pager or not lint:
        return "negator lists: not found in kit.js or lint.py"
    one, two = (set(re.findall(r"[a-z]+", found.group(1))) for found in (pager, lint))
    if one != two:
        return f"negator lists differ: kit.js only {sorted(one - two)}, lint.py only {sorted(two - one)}"
    return None


PAGER_HARNESS = """
const fs = require("fs");
const kit = fs.readFileSync(process.argv[2], "utf8");
const from = kit.indexOf("  const MONTHS = [");
const to = kit.indexOf("  const captions = (tokens, mute, quiet, says = [])");
if (from < 0 || to < 0) throw new Error("the pager was not found in kit.js");
const groupTokens = new Function(kit.slice(from, to) + ";return groupTokens;")();
const STOPS = ".,:;?!";
const bare = w => { while (w.length && STOPS.includes(w[w.length - 1])) w = w.slice(0, -1); return w; };
const tokens = text => text.split(" ").map((w, i) => ({
  d: bare(w), t0: i * 0.3, t1: i * 0.3 + 0.28, line: "L01",
  stop: STOPS.includes(w[w.length - 1]), end: ".?!".includes(w[w.length - 1]),
  p: w.endsWith("?") ? "?" : w.endsWith(",") ? "," : "",
}));
const pages = JSON.parse(fs.readFileSync(0, "utf8")).map(text => groupTokens(tokens(text)).map(g => g.map(x => x.d).join(" ").toUpperCase()));
console.log(JSON.stringify(pages));
"""
PAGER_CASES = (
    # a date in day-month order stays on one page, with its year (film 12 showed 29 / FEBRUARY)
    ("and leaves out 29 February.", ["AND LEAVES OUT", "29 FEBRUARY"]),
    (
        "It began on 29 February 2024 at noon.",
        ["IT BEGAN ON", "29 FEBRUARY 2024", "AT NOON"],
    ),
    ("5 May 2025 was a Monday.", ["5 MAY 2025", "WAS A MONDAY"]),
    # may and march are plain words unless a year follows
    ("About 1 in 3 may say yes.", ["ABOUT 1", "IN 3", "MAY SAY YES"]),
    # month first, as before
    ("On November 19 2026 it flew past.", ["ON NOVEMBER 19 2026", "IT FLEW PAST"]),
    # a number keeps its unit: people and pair are units too (film 12 showed 23 / PEOPLE and 1 / PAIR)
    ("23 people: just over half.", ["23 PEOPLE", "JUST OVER HALF"]),
    ("Every 2 people make 1 pair.", ["EVERY 2 PEOPLE", "MAKE 1 PAIR"]),
    ("The rope held 24 hours.", ["THE ROPE HELD", "24 HOURS"]),
    # a hedge opens the page of its negator; a number after a determiner ends the phrase before it
    (
        "The option that almost nobody takes can change which of the other 2 you pick.",
        [
            "THE OPTION THAT",
            "ALMOST NOBODY TAKES",
            "CAN CHANGE WHICH",
            "OF THE OTHER 2",
            "YOU PICK",
        ],
    ),
    (
        "Join every pair of the 23 with a line.",
        ["JOIN EVERY PAIR", "OF THE 23", "WITH A LINE"],
    ),
    (
        "Another 100 saw only the first and the last.",
        ["ANOTHER 100", "SAW ONLY THE", "FIRST AND", "THE LAST"],
    ),
    # a number that ends its clause joins the page before it; one that would only flash joins the next
    (
        "A class of 60? Over 99%, by the same sum.",
        ["A CLASS OF 60", "OVER 99%", "BY THE", "SAME SUM"],
    ),
    (
        "We made our medium for 1 job: to sell the large.",
        ["WE MADE OUR", "MEDIUM FOR", "1 JOB", "TO SELL", "THE LARGE"],
    ),
)


def part_pager() -> str | None:
    """The caption pager of kit.js on a few sentences: a date stays on one page in either order, a number keeps
    its unit and never flashes alone, a hedge stays with its negator, and May is a month only where a year
    follows."""
    node = shutil.which("node")
    if not node:
        return "caption pager: node not found, so the pages were not checked"
    with tempfile.TemporaryDirectory() as folder:
        harness = Path(folder) / "pager.js"
        harness.write_text(PAGER_HARNESS, encoding="utf-8")
        done = subprocess.run(
            [node, str(harness), str(STUDIO / "kit.js")],
            input=json.dumps([text for text, _ in PAGER_CASES]),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    if done.returncode:
        return f"caption pager: {last_line(done)}"
    try:
        pages = json.loads(done.stdout)
    except ValueError:
        return f"caption pager: no pages came back ({last_line(done)})"
    for (text, want), got in zip(PAGER_CASES, pages):
        if got != want:
            return f"caption pager: {text!r} pages as {got}, not {want}"
    return None


def part_owner() -> str | None:
    """Two things the owner of a film relies on. status calls a script stale only when its lines changed (the
    voice step writes its measured read into script.md after `script` ran), and the gate of package reads the
    look sheets: none, or sheets older than the video, means nobody has looked at this film."""
    import time

    if str(STUDIO) not in sys.path:
        sys.path.insert(0, str(STUDIO))
    import status
    import studio

    # what a copy of engine/ leaves out: caches, never a dot-file that is part of the engine
    with tempfile.TemporaryDirectory(prefix="studio-selftest-") as scratch:
        (Path(scratch) / ".ruff_cache").mkdir()
        (Path(scratch) / ".python-version").write_text("3.13\n", encoding="utf-8")
        names = [".ruff_cache", ".python-version", "__pycache__", "mix.pyc", "mix.py"]
        left_out = studio.cache_names(scratch, names)
        if left_out != {".ruff_cache", "__pycache__", "mix.pyc"}:
            return f"upgrade: a copy of engine/ leaves out {sorted(left_out)}"
    table = (
        "# T (script v1)\n\n| id | beat | caption | spoken | gap |\n|---|---|---|---|---|\n"
        "| L01 | hook | One. | One. | |\n| L02 | close | Two. | Two. | 0.5 |\n"
    )
    with tempfile.TemporaryDirectory(prefix="studio-selftest-") as scratch:
        build = Path(scratch)
        source, made = build / "script.md", build / "script.json"
        source.write_text(table, encoding="utf-8")
        made.write_text(
            json.dumps({"lines": studio.script_lines(table)}), encoding="utf-8"
        )
        now = time.time()

        def aged(path: Path, seconds: float) -> float:
            os.utime(path, (now - seconds, now - seconds))
            return path.stat().st_mtime

        if status._script(build, aged(made, 60), aged(source, 120)) != "done":
            return "status: a script.md older than script.json is not read as done"
        source.write_text(
            table + "\n## Measured read\n\nSpeech ends at 2.1 s.\n", encoding="utf-8"
        )
        if status._script(build, aged(made, 60), aged(source, 30)) != "done":
            return "status: a note under the table made the script stale"
        source.write_text(table.replace("Two.", "Three."), encoding="utf-8")
        if status._script(build, aged(made, 60), aged(source, 30)) != "stale":
            return "status: a changed line did not make the script stale"
        if status._script(build, None, aged(source, 30)) != "missing":
            return "status: no script.json is not read as missing"
        # the Lexicon table of script.md is part of the script: a row script.json lacks makes it stale
        lexicon = "\n## Lexicon\n\n| word | say |\n|---|---|\n| Baarle | Barla |\n"
        if studio.script_lexicon(table) is not None:
            return "script: a script.md with no Lexicon table does not read as None"
        if studio.script_lexicon(table + lexicon) != {"Baarle": "Barla"}:
            return f"script: the Lexicon table reads as {studio.script_lexicon(table + lexicon)!r}"
        source.write_text(table + lexicon, encoding="utf-8")
        if status._script(build, aged(made, 60), aged(source, 30)) != "stale":
            return (
                "status: a Lexicon row script.json lacks did not make the script stale"
            )
        made.write_text(
            json.dumps(
                {"lines": studio.script_lines(table), "lexicon": {"Baarle": "Barla"}}
            ),
            encoding="utf-8",
        )
        if status._script(build, aged(made, 60), aged(source, 30)) != "done":
            return "status: a Lexicon table script.json already holds made the script stale"
        video = build / "out" / "film.mp4"
        video.parent.mkdir()
        video.write_bytes(b"0")
        if studio.looked(build, video):
            return "package gate: a film with no look sheets counts as looked at"
        sheet = build / "proof" / "look" / "look_01.png"
        sheet.parent.mkdir(parents=True)
        sheet.write_bytes(b"0")
        aged(sheet, 300)
        aged(video, 200)
        if studio.looked(build, video):
            return "package gate: sheets older than the video count as a look at it"
        aged(sheet, 100)
        if not studio.looked(build, video):
            return "package gate: sheets newer than the video do not count"
    return None


def part_look() -> tuple[str | None, str]:
    """`look` on a test film built like a rendered one: 3 s of picture from a PNG that carries an ICC profile
    (so ffprobe ends the row of the stream's length with a comma) under 3.6 s of sound. One frame every second
    and the last one of the PICTURE, on sheets as tall as their rows, no cell left empty, and the sheets of an
    earlier look cleared. Needs ffmpeg and Pillow (the --render tier). Returns (problem, note)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return "look: ffmpeg not found", ""
    if str(STUDIO) not in sys.path:
        sys.path.insert(0, str(STUDIO))
    try:
        import sheet
        from PIL import Image, ImageCms, ImageDraw
    except ImportError as error:
        return f"look: {error} (run with studio/requirements.txt)", ""
    # what ffprobe really printed for finished films, and what it prints when it knows no length
    for answer, want in (
        ("112.266667,\r\n", 112.266667),
        ("3.000000\n", 3.0),
        ("N/A\n", None),
        ("", None),
    ):
        if sheet.seconds(answer) != want:
            return (
                f"look: seconds({answer!r}) is {sheet.seconds(answer)!r}, not {want!r}",
                "",
            )
    with tempfile.TemporaryDirectory(prefix="studio-selftest-") as scratch:
        film, still = Path(scratch) / "film.mp4", Path(scratch) / "still.png"
        picture = Image.new("RGB", (270, 480), (40, 80, 160))
        ImageDraw.Draw(picture).rectangle((60, 120, 210, 360), fill=(250, 210, 0))
        picture.save(
            still,
            icc_profile=ImageCms.ImageCmsProfile(
                ImageCms.createProfile("sRGB")
            ).tobytes(),
        )
        made = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-y",
                "-loop",
                "1",
                "-framerate",
                "30",
                "-t",
                "3",
                "-i",
                str(still),
                "-f",
                "lavfi",
                "-t",
                "3.6",
                "-i",
                "sine=frequency=440",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(film),
            ],
            capture_output=True,
            check=False,
        )
        if made.returncode or not film.is_file():
            return "look: the test film was not made", ""
        out = Path(scratch) / "look"
        try:
            sheets, frames = sheet.look(film, out, step=1.0, cols=3, rows=1, width=90)
        except (OSError, RuntimeError) as error:
            return f"look: {error}", ""
        if frames != 4 or len(sheets) != 2:
            return (
                f"look: {frames} frames on {len(sheets)} sheets, not 4 on 2 (the sound outlasts the picture: "
                "the frames must come from the picture's length)",
                "",
            )
        with Image.open(sheets[0]) as first, Image.open(sheets[1]) as second:
            sizes = [first.size, second.size]
            # the last frame's cell holds the still's yellow block, not the sheet's dark ground
            last = second.convert("RGB").getpixel((45, 80))
        if sizes != [(270, 160), (270, 160)]:
            return f"look: the sheets measure {sizes}, not two of (270, 160)", ""
        if not (last[0] > 180 and last[1] > 150 and last[2] < 110):
            return (
                f"look: the last frame's cell is {last}, not the picture (an empty cell)",
                "",
            )
        again, _ = sheet.look(film, out, step=3.0, cols=3, rows=1, width=90)
        if sorted(item.name for item in out.glob("*")) != [item.name for item in again]:
            return "look: sheets of an earlier look were left in the folder", ""
    return (
        None,
        "4 frames of the picture on 2 sheets under a longer sound, an earlier look cleared",
    )


def part_options() -> tuple[str | None, str]:
    """The kit's carried overlays and its end card, on frames of a short film (the probe's script under the shot
    list in selftest/options). A hook, a number and a stamp with `standing` read on the first frame after the
    cut exactly as on the last frame before it; a number takes its `x` and, with `align: "center"`, the middle
    of the frame; the end card sets its chip, lights its marked words and breaks its send line where the text
    does. Needs the browser (the --render tier). Returns (problem, note)."""
    with tempfile.TemporaryDirectory(prefix="studio-selftest-") as scratch:
        build = plant_probe(Path(scratch))
        shutil.copyfile(OPTIONS, build / "shots.json")
        done = run(STUDIO / "build.py", "timeline", build)
        if done.returncode:
            return f"options build: {last_line(done)}", ""
        timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
        starts = {shot["id"]: shot["t0"] for shot in timeline["shots"]}
        frame = 1 / timeline.get("fps", 30)
        # the last frame before each cut and the first after it; the end card once it has settled
        times = {
            f"{name} {side}": round(starts[name] + offset, 4)
            for name in ("s01b", "s03", "s05")
            for side, offset in (("before", -frame), ("after", 0.0001))
        }
        times["end"] = round(starts["end"] + 1.5, 4)
        out = Path(scratch) / "frames"
        done = run(
            STUDIO / "render.py",
            "stills",
            "--video",
            build,
            "--times",
            ",".join(str(moment) for moment in times.values()),
            "--out",
            out,
        )
        if done.returncode:
            return f"options render: {last_line(done)}", ""
        frames = json.loads((out / "registry.json").read_text(encoding="utf-8"))[
            "frames"
        ]

    def boxes(when: str, role: str) -> list[dict]:
        return [box for box in frames[f"{times[when]:.2f}"] if box["role"] == role]

    def same(first: list[dict], second: list[dict]) -> bool:
        return (
            len(first) == len(second) == 1
            and all(abs(first[0][key] - second[0][key]) <= 1 for key in "xywh")
            and first[0]["text"] == second[0]["text"]
            and first[0]["opacity"] == second[0]["opacity"] == 1
        )

    problems = []
    for role, shot in (("hook", "s01b"), ("stamp", "s05")):
        if not same(boxes(f"{shot} before", role), boxes(f"{shot} after", role)):
            problems.append(
                f"a standing {role} does not stand as it stood before the cut:"
                f" {boxes(f'{shot} before', role)} then {boxes(f'{shot} after', role)}"
            )
    # the stamp of the options film is 56 px with a hedge line: 133 px tall with the hedge at 0.62 of its words,
    # 163 px with the 62 px hedge a small stamp used to wear
    small = boxes("s05 before", "stamp")  # the stamp at rest, before the cut
    if len(small) != 1 or small[0]["h"] > 145:
        problems.append(
            f"a 56 px stamp wears a hedge above 0.62 of its words: its box is {small[0]['h'] if small else 'missing'}"
        )
    landed, carried = boxes("s03 before", "number"), boxes("s03 after", "number")
    if len(landed) != 1 or abs(landed[0]["x"] - 300) > 1 or landed[0]["text"] != "23":
        problems.append(f"a number with x 300 stands at {landed}")
    if (
        len(carried) != 1
        or carried[0]["text"] != "23"
        or carried[0]["opacity"] != 1
        or abs(carried[0]["x"] + carried[0]["w"] / 2 - 540) > 2
        or abs(carried[0]["w"] - (landed[0]["w"] if landed else 0)) > 1
    ):
        problems.append(
            f"a standing, centred number does not stand landed and centred after the cut: {carried}"
        )
    card = {box["text"]: box for box in boxes("end", "endcard")}
    chip = [box for box in boxes("end", "label") if box["text"] == "AS OF 2026"]
    line = [box for text, box in card.items() if text.lower().startswith("send this")]
    if len(chip) != 1 or abs(chip[0]["x"] + chip[0]["w"] / 2 - 540) > 2:
        problems.append(f"the end card's chip is not set in the middle: {chip}")
    if any("*" in text for text in card) or "STILLMOVING ON2026" not in card:
        problems.append(f"the end card prints its markers: {sorted(card)}")
    if len(line) != 1 or line[0]["h"] < 100 or line[0]["w"] > 700:
        problems.append(f"the end card's send line does not break in two lines: {line}")
    if problems:
        return "options: " + "; ".join(problems), ""
    return None, (
        "a standing hook, number and stamp hold across their cuts, a number takes x and the centre, the end card"
        " sets its chip, its marked words and its line break"
    )


def part_tag_warning() -> str | None:
    """`build` warns when a film's script.json tag is not the batch's (the script step copies the batch's tag, so
    a batch that changed or emptied its tag does not reach the film until script.json follows), and says nothing
    about the tag when the two agree. The probe's tag is PROBE."""
    with tempfile.TemporaryDirectory(prefix="studio-selftest-") as scratch:
        root = Path(scratch)
        build = plant_probe(root)
        settings = {
            "root": ".",
            "accent": "#ffd60a",
            "end": {},
            "music_dir": "music",
            "voice": {},
        }
        for tag, expected in (("", True), ("PROBE", False)):
            (root / "batch.json").write_text(
                json.dumps({**settings, "tag": tag}), encoding="utf-8"
            )
            done = run(STUDIO / "build.py", "timeline", build, "--batch", root)
            if done.returncode:
                return f"tag warning: the probe did not build under a batch with the tag {tag!r}: {last_line(done)}"
            warned = "WARN script.json sets the tag 'PROBE'" in done.stdout
            if warned != expected:
                return (
                    f"tag warning: under a batch with the tag {tag!r} the build "
                    f"{'warned' if warned else 'did not warn'} about the film's tag PROBE"
                )
    return None


def part_timing() -> tuple[str | None, str]:
    """A film with one frame five ticks short, as a join by container length once left finished films: its
    r_frame_rate still reads 30/1, its average rate does not. `check file` must give a V01 FIX for it and `package`
    must refuse it. The same film before the fault, and again after the manual's ffmpeg line has put its timestamps
    back on the grid, must pass both. Needs ffmpeg and the --render tier's modules. Returns (problem, note)."""
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        return "timing: ffmpeg or ffprobe not found", ""
    if str(STUDIO) not in sys.path:
        sys.path.insert(0, str(STUDIO))
    try:
        import package
        import qa
    except ImportError as error:
        return f"timing: {error} (run with studio/requirements.txt)", ""

    def made(*args: str) -> bool:
        return (
            subprocess.run(
                [ffmpeg, "-v", "error", "-y", *args], capture_output=True, check=False
            ).returncode
            == 0
        )

    def rates(video: Path) -> list[str]:
        """[r_frame_rate, avg_frame_rate] as ffprobe prints them."""
        done = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=r_frame_rate,avg_frame_rate",
                "-of",
                "json",
                str(video),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        try:
            stream = json.loads(done.stdout)["streams"][0]
        except (ValueError, KeyError, IndexError):
            return ["", ""]
        return [stream.get("r_frame_rate", ""), stream.get("avg_frame_rate", "")]

    with tempfile.TemporaryDirectory(prefix="studio-selftest-") as scratch:
        root = Path(scratch)
        build = root / "builds" / "01-timing"
        (build / "out").mkdir(parents=True)
        even, uneven, mended = (
            root / name for name in ("even.mp4", "uneven.mp4", "mended.mp4")
        )
        # two seconds of a moving test picture, no B-frames, so a packet's number is its place on screen
        if not made(
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1080x1920:rate=30:duration=2",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=2",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-profile:v",
            "high",
            "-pix_fmt",
            "yuv420p",
            "-bf",
            "0",
            "-c:a",
            "aac",
            str(even),
        ):
            return "timing: the test film was not made", ""
        # the fault: packet 29 lasts 5 ticks less and every later one starts 5 ticks early (512 ticks to a frame)
        fault = "setts=pts=PTS-5*gte(N\\,30):dts=DTS-5*gte(N\\,30):duration=if(eq(N\\,29)\\,DURATION-5\\,DURATION)"
        if not made(
            "-i", str(even), "-map", "0", "-c", "copy", "-bsf:v", fault, str(uneven)
        ):
            return "timing: the fault was not planted", ""
        # the cure the manual names (studio.md, V01)
        cure = "setts=pts=round(PTS/512)*512:dts=round(DTS/512)*512:duration=512"
        if not made(
            "-i",
            str(uneven),
            "-map",
            "0",
            "-c",
            "copy",
            "-bsf:v",
            cure,
            "-movflags",
            "+faststart",
            str(mended),
        ):
            return "timing: the manual's ffmpeg line did not run", ""
        if rates(even) != ["30/1", "30/1"]:
            return f"timing: the test film reads {rates(even)}, not an even 30/1", ""
        if rates(uneven)[0] != "30/1" or rates(uneven)[1] in ("30/1", ""):
            return (
                f"timing: the planted film reads {rates(uneven)}: the fault is not the one films carried",
                "",
            )
        if rates(mended) != ["30/1", "30/1"]:
            return (
                f"timing: after the manual's ffmpeg line the film reads {rates(mended)}",
                "",
            )

        def digest(video: Path, *stream: str) -> str:
            """ffmpeg's md5 of one stream: the decoded picture, or the sound as it lies in the file."""
            done = subprocess.run(
                [ffmpeg, "-v", "error", "-i", str(video), *stream, "-f", "md5", "-"],
                capture_output=True,
                text=True,
                check=False,
            )
            return done.stdout.strip()

        for name, stream in (
            ("picture", ("-map", "0:v:0")),
            ("sound", ("-map", "0:a:0", "-c", "copy")),
        ):
            before, after = digest(uneven, *stream), digest(mended, *stream)
            if not before.startswith("MD5=") or before != after:
                return (
                    f"timing: the manual's ffmpeg line changed the {name} ({before} to {after})",
                    "",
                )
        (build / "timeline.json").write_text(
            json.dumps({"slug": "timing"}), encoding="utf-8"
        )
        (build / "post.json").write_text(
            json.dumps(
                {
                    "title": "Timing",
                    "caption": "A test film.",
                    "alt_text": "A moving test pattern under a tone.",
                    "sources": [{"title": "A source", "url": "https://example.org/"}],
                    "cover_ms": 500,
                }
            ),
            encoding="utf-8",
        )
        batch = mock.Mock(package={}, videos=root / "videos")

        def judged(video: Path) -> tuple[list[dict], int, str]:
            """(the file check's rows about timing, package's exit code, what package printed)."""
            rows: list[dict] = []
            said = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()):
                qa.encoded(video, 2.0, rows)
            shutil.copyfile(video, build / "out" / "timing.mp4")
            with contextlib.redirect_stdout(said):
                code = package.package(batch, build)
            return (
                [row for row in rows if "evenly timed" in row["what"]],
                code,
                said.getvalue(),
            )

        for name, video in (("even", even), ("mended", mended)):
            rows, code, said = judged(video)
            if rows:
                return (
                    f"timing: the {name} film drew {rows[0]['code']} {rows[0]['level']}: {rows[0]['what']}",
                    "",
                )
            if code != 0:
                return (
                    f"timing: package refused the {name} film: {said.strip().splitlines()[0] if said.strip() else code}",
                    "",
                )
        rows, code, said = judged(uneven)
        if [(row["code"], row["level"]) for row in rows] != [("V01", "FIX")]:
            return (
                f"timing: a frame five ticks short drew {[(row['code'], row['level']) for row in rows]}, not one V01 FIX",
                "",
            )
        if code != 1 or "evenly timed" not in said:
            return (
                f"timing: package gave exit {code} for a frame five ticks short and did not refuse it for its timing",
                "",
            )
    return (
        None,
        "a frame five ticks short is a V01 FIX and package refuses it; the even film and the mended one pass",
    )


def part_filmdiff() -> str | None:
    done = run(STUDIO / "filmdiff.py", "--selftest")
    if done.returncode or "FILMDIFF: PASS" not in done.stdout:
        return f"film comparison selftest: {last_line(done)}"
    return None


def part_workflows() -> str | None:
    """Every workflow script must open with its meta literal, parse as the body of an async function (which is how
    the Workflow tool runs it) and never call a clock or a random number: those calls throw there."""
    node = shutil.which("node")
    if not node:
        return "workflow scripts: node not found, so their syntax was not checked"
    scripts = sorted((STUDIO / "workflows").glob("*.js"))
    if not scripts:
        return "workflow scripts: none found in workflows/"
    # any spacing JavaScript allows: Date.now (), Math . random(), new Date(0), new Date, Date()
    banned = re.compile(
        r"\bDate\s*\.\s*now\b|\bMath\s*\.\s*random\b|\bnew\s+Date\b|(?<![\w$.])Date\s*\("
    )
    with tempfile.TemporaryDirectory() as folder:
        for script in scripts:
            text = script.read_text(encoding="utf-8")
            if not text.startswith("export const meta = {"):
                return f"{script.name}: must open with `export const meta = {{`"
            used = sorted({found.group(0) for found in banned.finditer(text)})
            if used:
                return f"{script.name}: calls {', '.join(used)}, which throw in a workflow script"
            wrapped = Path(folder) / script.name
            wrapped.write_text(
                "async function workflow_body(args, agent, parallel, pipeline, phase, log, budget, workflow) {\n"
                + text.replace("export const meta", "const meta", 1)
                + "\n}\n",
                encoding="utf-8",
            )
            done = subprocess.run(
                [node, "--check", str(wrapped)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            if done.returncode:
                lines = [line for line in done.stderr.splitlines() if line.strip()]
                return f"{script.name}: does not parse: {' | '.join(lines[:4])}"
    return None


def plant_probe(folder: Path) -> Path:
    build = folder / "probe"
    shutil.copytree(PROBE, build, ignore=shutil.ignore_patterns("*.golden.json"))
    return build


def first_difference(want: object, got: object, path: str = "") -> str:
    if isinstance(want, dict) and isinstance(got, dict):
        for key in sorted(set(want) | set(got)):
            if key not in want or key not in got:
                return f"{path}/{key} is {'missing' if key not in got else 'new'}"
            found = first_difference(want[key], got[key], f"{path}/{key}")
            if found:
                return found
        return ""
    if isinstance(want, list) and isinstance(got, list):
        if len(want) != len(got):
            return f"{path} has {len(got)} items, golden has {len(want)}"
        for index, (a, b) in enumerate(zip(want, got, strict=True)):
            found = first_difference(a, b, f"{path}[{index}]")
            if found:
                return found
        return ""
    return "" if want == got else f"{path} is {got!r}, golden has {want!r}"


def build_probe(folder: Path) -> tuple[Path, str | None]:
    build = plant_probe(folder)
    done = run(STUDIO / "build.py", "timeline", build)
    if done.returncode:
        return build, f"probe build: {last_line(done)}"
    return build, None


def part_timeline(bless: bool = False) -> str | None:
    with tempfile.TemporaryDirectory(prefix="studio-selftest-") as scratch:
        build, problem = build_probe(Path(scratch))
        if problem:
            return problem
        text = (build / "timeline.json").read_text(encoding="utf-8")
        if bless:
            GOLDEN_TIMELINE.write_text(text, encoding="utf-8", newline="\n")
            return None
        if not GOLDEN_TIMELINE.exists():
            return "probe timeline: no selftest/probe/timeline.golden.json, run --bless-timeline"
        diff = first_difference(
            json.loads(GOLDEN_TIMELINE.read_text(encoding="utf-8")), json.loads(text)
        )
        return f"probe timeline differs from the golden: {diff}" if diff else None


def part_probe_lint() -> str | None:
    with tempfile.TemporaryDirectory(prefix="studio-selftest-") as scratch:
        build, problem = build_probe(Path(scratch))
        if problem:
            return problem
        done = run(STUDIO / "lint.py", build, "static")
        if done.returncode:
            return f"probe lint (static): {last_line(done)}; the probe must have 0 FIX"
        return None


RUNS = {  # review save inputs: one that has a reader, four that have none, one with two readers of one name
    "rounds": {
        "history": [
            {"round": 0, "checks": [{"key": "design", "verdict": "NOT READY"}]},
            {
                "round": 1,
                "checks": [],
            },  # film.js pushes an empty round when every reader fails
        ]
    },
    "stopped": {"stopped": "gate", "gate": {"exit_code": 1}},
    "strings": ["finding one", "finding two"],
    "empty": [],
    "unknown": "x",
    "twins": [
        {"reader": "design", "verdict": "READY"},
        {"reader": "design", "verdict": "NOT READY"},
        {"reader": "de sign"},
        {"reader": "de-sign"},
    ],
}


def upgrade_in_process(
    batch: Path, held: Path | None = None, stuck: Path | None = None
) -> tuple[int, str]:
    """`studio.py upgrade <batch> --force` in this process, with a fault planted: renaming `held` fails, as it does
    on Windows when a file inside it is open, and removing `stuck` fails, as it does when a file in it is open."""
    spec = importlib.util.spec_from_file_location(
        "studio_upgrade", STUDIO / "studio.py"
    )
    studio = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(studio)
    real_replace, real_rename, real_rmtree = os.replace, os.rename, shutil.rmtree

    def same(path: object, other: Path | None) -> bool:
        return other is not None and Path(path).resolve() == other.resolve()

    def replace(source, destination, *args, **kwargs):
        if same(source, held):
            raise PermissionError(13, "selftest: a file in it is open", str(source))
        return real_replace(source, destination, *args, **kwargs)

    def rename(source, destination, *args, **kwargs):
        if same(source, held):
            raise PermissionError(13, "selftest: a file in it is open", str(source))
        return real_rename(source, destination, *args, **kwargs)

    def rmtree(path, *args, **kwargs):
        if same(path, stuck) and not kwargs.get("ignore_errors"):
            raise PermissionError(13, "selftest: a file in it is open", str(path))
        return real_rmtree(path, *args, **kwargs)

    said = io.StringIO()
    with (
        mock.patch.object(os, "replace", replace),
        mock.patch.object(os, "rename", rename),
        mock.patch.object(shutil, "rmtree", rmtree),
        contextlib.redirect_stdout(said),
    ):
        try:
            code = studio.main(["upgrade", str(batch), "--force"])
        except Exception as error:  # noqa: BLE001 - a crash exits 1, which reads as FIX
            code = 1
            print(f"{type(error).__name__}: {error}")
    return code, said.getvalue()


def part_cli() -> str | None:
    """The command line's contract on a scratch batch holding the probe: a stale timeline is refused (3), a failed
    build leaves no timeline, a check that cannot run leaves no older result (2), check stills on a missing build
    creates nothing (2), script reads only the id table and keeps a per-film voice, render refuses a film with no
    music (3), exit codes 2 and 64, two builds never share a slug (3), a run of shots on a bare plate is a FIX of
    the plan check until a picture stands inside it, keep refuses a bad name (64) and a build with no film (2),
    new dates a film by the local day or --date, review save refuses a run with no reader (1) and keeps two readers
    of one name, review answers on a stage with nothing saved is 2, diff counts what only the other folder has, and
    upgrade replaces a batch's copy of the engine, refusing one with an edited, added or deleted file or with no
    SNAPSHOT.txt (3) unless forced, and puts the old copy back whole when a move fails midway (2)."""
    import time

    sample = {
        "root": ".",
        "accent": "#fff",
        "tag": "T",
        "end": {"handle": "h", "follow": "f", "ai_line": "a"},
        "music_dir": "music",
        "voice": {"name": "af_heart", "speed": 1.0},
    }
    env = {
        **os.environ,
        "ZOETROPE_STUDIO_ENV": "1",
    }  # no hand-over to the pinned environment
    with tempfile.TemporaryDirectory(prefix="studio-selftest-") as scratch:
        batch = Path(scratch) / "batch"
        (batch / "builds").mkdir(parents=True)
        (batch / "batch.json").write_text(json.dumps(sample), encoding="utf-8")
        probe = batch / "builds" / "01-probe"
        shutil.copytree(PROBE, probe, ignore=shutil.ignore_patterns("*.golden.json"))
        timeline = probe / "timeline.json"

        def cli(*args: object, zone: str | None = None) -> tuple[int, str]:
            done = subprocess.run(
                [sys.executable, "-I", str(STUDIO / "studio.py"), *map(str, args)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env if zone is None else {**env, "TZ": zone},
                timeout=120,
                check=False,
            )
            return done.returncode, done.stdout + done.stderr

        made = Path(scratch) / "made"
        second = Path(scratch) / "second"

        def copied_without_cache() -> str | None:
            """new-batch run from the first batch's own copy of the engine (its engine/ holds a planted cache)."""
            done = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    str(made / "studio" / "studio.py"),
                    "new-batch",
                    str(second),
                    "--config",
                    str(batch / "batch.json"),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                env=env,
                timeout=120,
                check=False,
            )
            if done.returncode:
                said = (done.stdout + done.stderr).strip()[-200:]
                return f"cli: new-batch from a batch's own copy exited {done.returncode}: {said}"
            snapshot = (second / "SNAPSHOT.txt").read_text(encoding="utf-8")
            if (
                second / "engine" / ".ruff_cache"
            ).exists() or ".ruff_cache" in snapshot:
                return "cli: a tool's cache folder of engine/ went into a new batch or its snapshot"
            if (
                not (second / "engine" / ".python-version").is_file()
                or "engine/.python-version" not in snapshot
            ):
                return "cli: the engine's .python-version did not travel into a new batch and its snapshot"
            return None

        def forced_upgrade() -> str | None:
            """upgrade --force over a copy with an edit, an added and a deleted file, whose snapshot still holds
            the two cache lines appended above: it names the three, and no cache line as removed."""
            code, said = cli("upgrade", made, "--force")
            wanted = (
                "dropped a local edit: studio/qa.py",
                "dropped an added file: studio/fonts/Inter.ttf",
                "dropped a local deletion: studio/sheet.py",
            )
            if code != 0 or any(part not in said for part in wanted):
                return f"cli: `upgrade <made> --force` exited {code} (want 0, {wanted!r}): {said.strip()[-200:]}"
            listed = [line for line in said.splitlines() if ".ruff_cache" in line]
            if listed:
                return f"cli: upgrade --force listed a cache line of an older snapshot: {listed[0]}"
            return None

        def pictured(plan: dict) -> dict:
            plan["shots"][1]["media"] = {"kind": "still", "src": "media/none.jpg"}
            return plan

        def expect(want: int, args: tuple, text: str | tuple = "") -> str | None:
            code, said = cli(*args)
            texts = (text,) if isinstance(text, str) else text
            if code != want or any(part not in said for part in texts):
                shown = " ".join(str(a) for a in args).replace(str(batch), "<batch>")
                return f"cli: `{shown}` exited {code} (want {want}{', ' + repr(text) if text else ''}): {said.strip()[-200:]}"
            return None

        tables = batch / "builds" / "03-tables"

        def tables_json(**more: object) -> dict | None:
            """script.json of the tables build as a dict; with keys, they are written into it and None comes back."""
            held = json.loads((tables / "script.json").read_text(encoding="utf-8"))
            if not more:
                return held
            (tables / "script.json").write_text(
                json.dumps({**held, **more}), encoding="utf-8"
            )
            return None

        def tables_md(more: str) -> None:
            """Adds text to the end of the tables build's script.md."""
            with (tables / "script.md").open(
                "a", encoding="utf-8", newline=""
            ) as handle:
                handle.write(more)

        def local_day() -> str | None:
            """The brief is dated by the local day: in a zone 14 hours ahead of UTC and in one 12 hours behind,
            one of which is on another day than UTC at any hour, so a UTC date fails here."""
            days = []
            for number, zone in ((6, "AAA-14"), (7, "BBB+12")):
                slug = f"0{number}-zone{number}"
                code, said = cli(
                    "new", batch, slug, "--title", "T", "--topic", "X", zone=zone
                )
                day = subprocess.run(
                    [
                        sys.executable,
                        "-I",
                        "-c",
                        "import time; print(time.strftime('%Y-%m-%d'))",
                    ],
                    capture_output=True,
                    text=True,
                    env={**env, "TZ": zone},
                    check=False,
                ).stdout.strip()
                brief = batch / "builds" / slug / "brief.md"
                if code or f"({day})" not in brief.read_text(encoding="utf-8"):
                    return f"cli: new with TZ={zone} did not date the brief {day}: {said.strip()[-200:]}"
                days.append(day)
            if all(day == time.strftime("%Y-%m-%d", time.gmtime()) for day in days):
                return "cli: no zone of the local-day check is on another day than UTC"
            return None

        def failed_upgrade(fault: dict) -> str | None:
            """An upgrade that fails says NOT CHECKED (2) and leaves the batch's copy as it was."""
            code, said = upgrade_in_process(made, **fault)
            if code != 2 or "the batch's copy" not in said:
                return f"cli: upgrade with {fault} exited {code}: {said.strip()[-200:]}"
            if (
                (made / "studio" / "qa.py").read_text(encoding="utf-8") != "edited\n"
                or (made / ".engine-upgrade").exists()
                or not cli("diff", made)[1].strip().endswith("3 file(s) differ")
            ):
                return f"cli: upgrade with {fault} did not leave the old copy as it was"
            return None

        steps = [
            lambda: expect(0, ("build", probe)),
            # 1 and 3: an input newer than the timeline, by the one definition, refuses every reader of it
            # (the other inputs are aged first: on a fresh checkout every file of the probe is seconds old)
            lambda: (
                [
                    os.utime(probe / name, (time.time() - 120,) * 2)
                    for name in ("shots.py", "shots.json", "script.json", "graphics.js")
                    if (probe / name).is_file()
                ]
                and None
            ),
            lambda: os.utime(timeline, (time.time() - 60,) * 2),
            lambda: os.utime(
                probe / "narration" / "layout.json", (time.time() - 30,) * 2
            ),
            lambda: expect(
                3, ("check", probe, "plan"), "older than narration/layout.json"
            ),
            lambda: expect(3, ("table", probe), "REFUSED timeline.json is older"),
            lambda: expect(0, ("build", probe)),
            lambda: expect(0, ("check", probe, "lint")),
            # 2: a failed shots.py leaves no timeline; 4: the lint that then cannot run leaves no result
            lambda: (probe / "shots.py").write_text(
                'raise SystemExit("typo")\n', encoding="utf-8"
            ),
            lambda: expect(1, ("build", probe), "FIX shots.py failed"),
            lambda: (
                "cli: a failed build left timeline.json" if timeline.exists() else None
            ),
            lambda: expect(2, ("check", probe, "lint")),
            lambda: (
                "cli: lint left an older qa_lint.json"
                if (probe / "proof" / "qa_lint.json").exists()
                else None
            ),
            lambda: (probe / "shots.py").unlink(),
            lambda: expect(0, ("build", probe)),
            # 9: render refuses before any frame when script.json names no music
            lambda: expect(3, ("render", probe), "REFUSED script.json names no music"),
            # 12: the probe is four shots on the kit's bare plate, 10.1 s in a row; a picture in the second one
            # breaks the run
            lambda: expect(1, ("check", probe, "plan"), "P12"),
            lambda: timeline.write_text(
                json.dumps(pictured(json.loads(timeline.read_text(encoding="utf-8")))),
                encoding="utf-8",
            ),
            lambda: (
                None
                if (found := cli("check", probe, "plan"))[0] in (0, 1)
                and "qa plan:" in found[1]
                and "P12" not in found[1]
                else f"cli: check plan with a picture inside the run exited {found[0]}"
                f" ({'P12 fired' if 'P12' in found[1] else 'no qa plan: line'}): {found[1].strip()[-200:]}"
            ),
            lambda: expect(0, ("build", probe)),
            # 13: keep
            lambda: expect(64, ("keep", probe, "bad name")),
            lambda: expect(2, ("keep", probe, "pass1"), "run render first"),
            # 14: upgrade a batch made by new-batch
            lambda: expect(0, ("new-batch", made, "--config", batch / "batch.json")),
            lambda: (
                "cli: new-batch copied a stray SNAPSHOT.txt into studio/"
                if (made / "studio" / "SNAPSHOT.txt").exists()
                else None
            ),
            lambda: expect(0, ("upgrade", made), "0 changed, 0 added, 0 removed"),
            # an engine whose engine/ folder holds a tool's cache hands on neither the cache nor a snapshot line
            # for it, and its .python-version still travels: the batch's own copy, with a cache planted in its
            # engine/, makes a second batch
            lambda: (made / "engine" / ".ruff_cache").mkdir(exist_ok=True),
            lambda: (made / "engine" / ".ruff_cache" / "x").write_bytes(b"cache"),
            lambda: copied_without_cache(),
            # a snapshot written by an older engine lists cache files: one that changed since and one that is
            # gone are no edits of the copy
            lambda: (
                (made / "SNAPSHOT.txt")
                .open("a", encoding="utf-8", newline="")
                .write(
                    f"{'0' * 64}  engine/.ruff_cache/x\n{'0' * 64}  engine/.ruff_cache/gone\n"
                )
                and None
            ),
            lambda: expect(0, ("diff", made), "0 file(s) differ"),
            lambda: (made / "studio" / "qa.py").write_text(
                "edited\n", encoding="utf-8"
            ),
            lambda: expect(3, ("upgrade", made), "changed since its snapshot"),
            # a file added to the copy (its own fonts) and a file deleted from it would be dropped too
            lambda: (made / "studio" / "fonts").mkdir(),
            lambda: (made / "studio" / "fonts" / "Inter.ttf").write_bytes(b"font"),
            lambda: expect(3, ("upgrade", made), "studio/fonts/Inter.ttf (added)"),
            lambda: (made / "studio" / "sheet.py").unlink(),
            lambda: expect(3, ("upgrade", made), "studio/sheet.py (missing)"),
            # a tool's cache in a dot-folder is not an edit; a file only the other folder has is counted
            lambda: (made / "studio" / ".cache").mkdir(),
            lambda: (made / "studio" / ".cache" / "x").write_bytes(b"cache"),
            lambda: expect(1, ("diff", made), "3 file(s) differ"),
            lambda: expect(
                1, ("diff", made, "--against", STUDIO), f"only in {STUDIO}: sheet.py"
            ),
            # a move that fails midway (a held file in engine/, then in the new engine/) puts the old copy back
            # whole, and a previous copy that cannot be cleared stops it before anything moves
            *(
                lambda fault=fault: failed_upgrade(fault)
                for fault in (
                    {"held": made / "engine"},
                    {"held": made / ".engine-upgrade" / "engine"},
                    {"stuck": made / "engine-before-upgrade"},
                )
            ),
            lambda: forced_upgrade(),
            lambda: (
                None
                if (made / "studio" / "qa.py").read_bytes()
                == (STUDIO / "qa.py").read_bytes()
                else "cli: upgrade --force left the edited file"
            ),
            lambda: expect(0, ("diff", made), "0 file(s) differ"),
            lambda: (made / "SNAPSHOT.txt").unlink(),
            lambda: expect(3, ("upgrade", made), "no SNAPSHOT.txt"),
            lambda: expect(0, ("upgrade", made, "--force"), "without an edit check"),
            lambda: expect(0, ("diff", made), "0 file(s) differ"),
            # 6 and 10: missing input is 2 and creates nothing; a wrong argument is 64
            lambda: expect(2, ("check", batch / "builds" / "09-nope", "stills")),
            lambda: expect(
                2, ("review", "answers", batch / "builds" / "09-nope", "--stage", "r1")
            ),
            lambda: (
                "cli: a command created a misspelled build"
                if (batch / "builds" / "09-nope").exists()
                else None
            ),
            lambda: expect(64, ("review", "bogus", probe, "--stage", "r1")),
            lambda: expect(64, ("sheet", probe, "--times", "abc")),
            lambda: expect(2, ("diff", batch), "SNAPSHOT.txt"),
            # 11: a second build with the probe's slug
            lambda: expect(
                3, ("new", batch, "02-probe", "--title", "T", "--topic", "X")
            ),
            lambda: expect(
                0, ("new", batch, "03-tables", "--title", "T", "--topic", "X")
            ),
            # new dates the brief by the local day (the workflows' `today`), or by --date
            lambda: expect(
                0,
                ("new", batch, "04-dated", "--title", "T", "--topic", "X")
                + ("--date", "2026-01-02"),
            ),
            lambda: (
                None
                if "(2026-01-02)"
                in (batch / "builds" / "04-dated" / "brief.md").read_text(
                    encoding="utf-8"
                )
                else "cli: new did not date the brief by --date"
            ),
            lambda: expect(
                64,
                ("new", batch, "05-bad", "--title", "T", "--topic", "X")
                + ("--date", "1/2"),
            ),
            local_day,
            # review save: a run with no reader saves nothing and says so (1); two readers of one name keep both
            lambda: (probe / "runs").mkdir(),
            *(
                lambda name=name, data=data: (
                    probe / "runs" / f"{name}.json"
                ).write_text(json.dumps(data), encoding="utf-8")
                for name, data in RUNS.items()
            ),
            lambda: expect(
                0,
                (
                    "review",
                    "save",
                    probe,
                    probe / "runs" / "rounds.json",
                    "--stage",
                    "a",
                ),
            ),
            lambda: (
                None
                if (probe / "proof" / "reviews" / "a_design.json").is_file()
                else "cli: review save lost the findings of an earlier round"
            ),
            *(
                lambda name=name: expect(
                    1,
                    ("review", "save", probe, probe / "runs" / f"{name}.json")
                    + ("--stage", "b"),
                    "FIX nothing saved",
                )
                for name in ("stopped", "strings", "empty", "unknown")
            ),
            lambda: (
                "cli: review save wrote a file for a run with no reader"
                if list((probe / "proof" / "reviews").glob("b_*.json"))
                else None
            ),
            lambda: expect(
                0,
                (
                    "review",
                    "save",
                    probe,
                    probe / "runs" / "twins.json",
                    "--stage",
                    "c",
                ),
            ),
            lambda: (
                None
                if sorted(
                    p.name for p in (probe / "proof" / "reviews").glob("c_*.json")
                )
                == [
                    "c_de-sign-2.json",
                    "c_de-sign.json",
                    "c_design-2.json",
                    "c_design.json",
                ]
                else "cli: review save overwrote a reader of the same name"
            ),
            lambda: expect(
                2,
                ("review", "answers", probe, "--stage", "b"),
                "no proof/reviews/b_*.json",
            ),
            lambda: (
                "cli: review answers wrote a skeleton for a stage with nothing saved"
                if (probe / "proof" / "b_answers.md").exists()
                else None
            ),
            lambda: (batch / "builds" / "03-tables" / "script.md").write_text(
                "# Tables\n\n| key | value |\n|---|---|\n| K1 | a |\n\n"
                "| id | caption | spoken |\n|---|---|---|\n| L01 | One | One. |\n| L02 | Two | Two. |\n\n"
                "| id | claim |\n|---|---|\n| F1 | not a line |\n",
                encoding="utf-8",
            ),
            lambda: (batch / "builds" / "03-tables" / "script.json").write_text(
                json.dumps({"voice": {"speed": 1.12}}), encoding="utf-8"
            ),
            lambda: expect(
                0,
                ("script", batch / "builds" / "03-tables"),
                "script.json: 2 lines (no music",
            ),
            lambda: (
                None
                if json.loads(
                    (batch / "builds" / "03-tables" / "script.json").read_text(
                        encoding="utf-8"
                    )
                )["voice"]
                == {"speed": 1.12}
                else "cli: script did not keep the per-film voice speed"
            ),
            # a lexicon, a lead and a progress put into script.json by hand outlive a script run
            lambda: tables_json(lexicon={"Baarle": "Barla"}, lead=0.3, progress=False),
            lambda: expect(
                0,
                ("script", batch / "builds" / "03-tables"),
                "script.json: 2 lines, lexicon: Baarle (no music",
            ),
            lambda: (
                None
                if [tables_json().get(key) for key in ("lexicon", "lead", "progress")]
                == [{"Baarle": "Barla"}, 0.3, False]
                else "cli: script dropped a lexicon, lead or progress an earlier script.json held"
            ),
            # the Lexicon table of script.md wins, and a word it no longer lists is dropped out loud
            lambda: tables_md(
                "\n## Lexicon\n\n| word | say |\n|---|---|\n| Johannes | Yo-hahn-ess |\n"
            ),
            lambda: expect(
                0,
                ("script", batch / "builds" / "03-tables"),
                (
                    "NOTE lexicon: Baarle was in the earlier script.json",
                    "lexicon: Johannes (no music",
                ),
            ),
            lambda: (
                None
                if tables_json().get("lexicon") == {"Johannes": "Yo-hahn-ess"}
                else "cli: script did not take the lexicon from script.md's Lexicon table"
            ),
            lambda: tables_md("| Schmidt | |\n"),
            lambda: expect(
                1,
                ("script", batch / "builds" / "03-tables"),
                "FIX lexicon row",
            ),
        ]
        for step in steps:
            problem = step()
            if isinstance(problem, str):
                return problem
    return None


def blocks_of(path: Path) -> list[int]:
    """The mean colour of every 60 px block of a frame (rows, then columns, then R, G, B), in hundredths."""
    import numpy as np
    from PIL import Image

    with Image.open(path) as image:
        pixels = np.asarray(image.convert("RGB"), dtype=float)
    high, wide = pixels.shape[0] // BLOCK, pixels.shape[1] // BLOCK
    means = (
        pixels[: high * BLOCK, : wide * BLOCK]
        .reshape(high, BLOCK, wide, BLOCK, 3)
        .mean(axis=(1, 3))
    )
    return [int(round(value * 100)) for value in means.reshape(-1)]


def frame_digests() -> tuple[dict[str, dict] | None, str | None]:
    with tempfile.TemporaryDirectory(prefix="studio-selftest-") as scratch:
        build, problem = build_probe(Path(scratch))
        if problem:
            return None, problem
        out = Path(scratch) / "frames"
        times = ",".join(str(t) for t in FRAME_TIMES)
        done = run(
            STUDIO / "render.py",
            "stills",
            "--video",
            build,
            "--times",
            times,
            "--out",
            out,
        )
        if done.returncode:
            return None, f"probe render: {last_line(done)}"
        try:
            digests = {
                f"{t:.2f}": {
                    "sha256": hashlib.sha256(
                        (out / f"t{t:07.2f}.png").read_bytes()
                    ).hexdigest(),
                    "blocks": blocks_of(out / f"t{t:07.2f}.png"),
                }
                for t in FRAME_TIMES
            }
        except ImportError as error:
            return None, f"probe frames: {error} (run with studio/requirements.txt)"
        return digests, None


def part_frames(bless: bool) -> tuple[str | None, str]:
    """Returns (problem, note); note starts with "skip:" when there is nothing to compare against."""
    golden = STUDIO / "selftest" / "golden" / HOST / "frames.json"
    digests, problem = frame_digests()
    if problem:
        return problem, ""
    if bless:
        golden.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            f" {json.dumps(t)}: {json.dumps(found, separators=(',', ':'))}"
            for t, found in digests.items()
        ]
        golden.write_text(
            "{\n" + ",\n".join(rows) + "\n}\n", encoding="utf-8", newline="\n"
        )
        return None, f"blessed {golden.relative_to(STUDIO).as_posix()}"
    if not golden.exists():
        return None, f"skip: no golden frames for {HOST}, run --bless"
    want = json.loads(golden.read_text(encoding="utf-8"))
    same, near, changed, worst = 0, 0, [], 0.0
    for t, found in digests.items():
        old = want.get(t) or {}
        if old.get("sha256") == found["sha256"]:
            same += 1
            continue
        a, b = old.get("blocks") or [], found["blocks"]
        gap = max((abs(x - y) for x, y in zip(a, b, strict=False)), default=0) / 100
        if len(a) != len(b) or not a or gap > JITTER:
            changed.append(
                f"{t} s (a block is {gap:.2f} of 255 off)"
                if a and len(a) == len(b)
                else f"{t} s"
            )
        else:
            near += 1
            worst = max(worst, gap)
    if changed:
        return f"probe frames differ from the golden at {', '.join(changed)}", ""
    note = f"{same} of {len(digests)} frames have the golden's digest"
    if near:
        note += f", {near} within render jitter (largest block difference {worst:.2f} of 255, limit {JITTER})"
    return None, note


def main(argv: list[str]) -> int:
    flags = set(argv)
    unknown = flags - {"--quick", "--render", "--bless", "--bless-timeline"}
    if unknown or not flags:
        print(__doc__, file=sys.stderr)
        return 64
    if "--bless-timeline" in flags:
        problem = part_timeline(bless=True)
        print(f"FAIL {problem}" if problem else f"ok   blessed {GOLDEN_TIMELINE.name}")
        return 1 if problem else 0
    parts = [
        ("lint rules, their controls and the regression cases", part_lint),
        ("shotkit golden", part_shotkit),
        ("batch config", part_batch),
        ("generator shot filter and chain rule", part_gen),
        ("pager and lint hold the same negators", part_negators),
        (
            "caption pager: dates, units, a hedge with its negator, no number flashing alone",
            part_pager,
        ),
        (
            "status reads a script by its lines, package asks for the look of its owner",
            part_owner,
        ),
        ("workflow scripts open with meta, parse and call no clock", part_workflows),
        ("film comparison: stats lines, runs and the shots a run names", part_filmdiff),
        ("probe timeline equals the golden", part_timeline),
        ("probe lint, static tier, 0 FIX", part_probe_lint),
        ("build warns when a film's tag is not the batch's", part_tag_warning),
        (
            "command line: stale, failed build, exit codes, script, slugs, dates, bare plate, keep, review, diff, upgrade",
            part_cli,
        ),
    ]
    failed, count = [], 0
    for name, part in parts:
        problem = part()
        count += 1
        print(f"FAIL {problem}" if problem else f"ok   {name}")
        if problem:
            failed.append(name)
    if flags & {"--render", "--bless"}:
        problem, note = part_frames("--bless" in flags)
        count += 1
        if problem:
            print(f"FAIL {problem}")
            failed.append("probe frames")
        else:
            print(f"ok   probe frames: {note}")
        problem, note = part_look()
        count += 1
        if problem:
            print(f"FAIL {problem}")
            failed.append("look")
        else:
            print(f"ok   look: {note}")
        problem, note = part_options()
        count += 1
        if problem:
            print(f"FAIL {problem}")
            failed.append("kit options")
        else:
            print(f"ok   kit options: {note}")
        problem, note = part_timing()
        count += 1
        if problem:
            print(f"FAIL {problem}")
            failed.append("uneven timing")
        else:
            print(f"ok   uneven timing: {note}")
    if failed:
        print(f"STUDIO SELFTEST: FAIL ({'; '.join(failed)})")
        return 1
    print(f"STUDIO SELFTEST: PASS ({count} parts)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
