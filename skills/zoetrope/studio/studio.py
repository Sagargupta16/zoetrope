"""The studio engine's command line: one command per stage of a narrated film.

  python studio/studio.py new-batch <dir> --config batch.json
  python studio/studio.py new <batch> 01-slug --title T --topic X [--date YYYY-MM-DD]
  python studio/studio.py status <batch>
  python studio/studio.py script|voice|build|render|table|package|stills|clips|adopt|check|sheet|review <build> ...
  python studio/studio.py look <build> [--step 1.25]
  python studio/studio.py keep <build> <name>
  python studio/studio.py changed <build> [--before OLD.mp4] [--db 45]
  python studio/studio.py diff <batch> [--against SNAPSHOT|<folder>]
  python <newer engine>/studio/studio.py upgrade <batch> [--force]

Exit codes: 0 PASS, 1 FIX, 2 NOT CHECKED or missing input, 3 refused (stale input), 64 usage error.
Every stage module is imported inside its handler, so one module that does not import never blocks the others.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

PASS, FIX, NOT_CHECKED, REFUSED, USAGE = 0, 1, 2, 3, 64
STAGES = ("plan", "lint", "frames", "stills", "file")
TEMPLATES = ("brief.md", "script.md", "shots.py", "caption.md")


class Parser(argparse.ArgumentParser):
    def error(self, message: str):  # argparse's own 2 would read as NOT CHECKED
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        raise SystemExit(USAGE)


def module(name: str):
    try:
        return importlib.import_module(name)
    except ImportError as error:
        print(f"NOT CHECKED: module {name} does not import ({error})")
        return None


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_script(name: str, *args: object) -> int:
    """Run one of the studio's scripts as its own process. Every stage that loads the audio engine goes this
    way: the engine has its own qa.py, audio.py and render.py, and its modules import each other by those
    names, so the two sets cannot share one interpreter."""
    return subprocess.run(
        [sys.executable, str(HERE / name), *map(str, args)], check=False
    ).returncode


def load_batch(path: str):
    import batch as batch_module

    try:
        return batch_module.find(path)
    except batch_module.BatchError as error:
        print(f"NOT CHECKED: {error}")
        return None


def build_dir(arg: str) -> Path:
    return Path(arg).resolve()


def stale_input(build: Path) -> list[str]:
    """The one definition of a stale timeline: the inputs newer than timeline.json (shots.py, shots.json,
    script.json, graphics.js, narration/layout.json, and media/<id>.png or .mp4 of every shot the timeline
    uses), by their path in the build. Empty when there is no timeline.json or nothing is newer."""
    timeline = build / "timeline.json"
    if not timeline.is_file():
        return []
    made = timeline.stat().st_mtime
    try:
        shots = json.loads(timeline.read_text(encoding="utf-8")).get("shots") or []
    except (OSError, ValueError, AttributeError):
        shots = []
    owners = sorted(
        {
            str(shot.get("owner") or shot.get("id"))
            for shot in shots
            if isinstance(shot, dict)
        }
    )
    names = [
        "shots.py",
        "shots.json",
        "script.json",
        "graphics.js",
        "narration/layout.json",
    ]
    names += [f"media/{owner}{ext}" for owner in owners for ext in (".png", ".mp4")]
    return [
        name
        for name in names
        if (build / name).is_file() and (build / name).stat().st_mtime > made
    ]


def refuse_stale(build: Path) -> int | None:
    """REFUSED (3) with the newer files named when the timeline is stale; None when the stage may run."""
    stale = stale_input(build)
    if not stale:
        return None
    print(f"REFUSED timeline.json is older than {', '.join(stale)}: run build again")
    return REFUSED


# ---- batch and build setup ----


def copy_engine(target: Path) -> list[str]:
    """Copy this engine into a batch folder (studio/, the audio engine as engine/, the manual and the rule
    list as docs/) and return its snapshot lines. new-batch and upgrade share it, so a batch always holds a
    whole copy of one engine."""
    copied = []
    for source in sorted(HERE.rglob("*")):
        relative = source.relative_to(HERE)
        if (
            not source.is_file()
            or "__pycache__" in relative.parts
            or source.suffix == ".pyc"
            or any(part.startswith(".") for part in relative.parts)  # a tool's cache
        ):
            continue
        destination = target / "studio" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        copied.append(f"{sha256(destination)}  studio/{relative.as_posix()}")
    engine = HERE.parent / "engine"
    if engine.is_dir() and engine.resolve() != (target / "engine").resolve():
        shutil.copytree(
            engine,
            target / "engine",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        print(f"engine copied to {target / 'engine'}")
    else:
        print(f"note: no engine folder at {engine}; voice and mix need <batch>/engine")
    # The manual and the rule list travel with the kit they describe: <batch>/docs/ (from the skill's
    # references/, or from the docs/ of the batch this studio was itself copied into).
    manual = next(
        (
            f
            for f in (HERE.parent / "references", HERE.parent / "docs")
            if (f / "studio.md").is_file()
        ),
        None,
    )
    if manual is not None and manual.resolve() != (target / "docs").resolve():
        (target / "docs").mkdir(exist_ok=True)
        for name in ("studio.md", "studio-checklist.md"):
            if (manual / name).is_file():
                shutil.copyfile(manual / name, target / "docs" / name)
        print(f"manual copied to {target / 'docs'}")
    for folder in (
        "engine",
        "docs",
    ):  # every copied file is in the snapshot, not only studio/
        for path in sorted((target / folder).rglob("*")):
            relative = path.relative_to(target).as_posix()
            if (
                path.is_file()
                and "__pycache__" not in relative
                and path.suffix != ".pyc"
            ):
                copied.append(f"{sha256(path)}  {relative}")
    return copied


def read_snapshot(path: Path) -> dict[str, str]:
    """SNAPSHOT.txt as {file name: sha256}; empty when there is none."""
    if not path.is_file():
        return {}
    recorded = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        if name:
            recorded[name] = digest
    return recorded


def copy_changes(target: Path, recorded: dict[str, str]) -> list[tuple[str, str]]:
    """How a batch's copy (studio/, engine/, docs/) differs from its snapshot, as (added, changed or missing,
    file name). A file under __pycache__ or a dot-folder, or a .pyc, is not counted as added: copy_engine never
    copies one into studio/, so it is a tool's cache, not an edit."""
    found = []
    for folder in PARTS:
        for path in sorted((target / folder).rglob("*")):
            relative = path.relative_to(target)
            name = relative.as_posix()
            if (
                path.is_file()
                and "__pycache__" not in relative.parts
                and path.suffix != ".pyc"
                and not any(part.startswith(".") for part in relative.parts)
                and name not in recorded
            ):
                found.append(("added", name))
    for name, digest in sorted(recorded.items()):
        path = target / name
        if not path.is_file():
            found.append(("missing", name))
        elif sha256(path) != digest:
            found.append(("changed", name))
    return found


def cmd_new_batch(args) -> int:
    import batch as batch_module

    target = Path(args.dir).resolve()
    config = Path(args.config).resolve()
    if not config.is_file():
        print(f"missing config {config}")
        return NOT_CHECKED
    if (target / "batch.json").exists():
        print(f"{target / 'batch.json'} exists: refusing to overwrite a batch")
        return REFUSED
    try:
        batch_module.load(config)
    except batch_module.BatchError as error:
        print(f"FIX {error}")
        return FIX
    target.mkdir(parents=True, exist_ok=True)
    copied = copy_engine(target)
    shutil.copyfile(config, target / "batch.json")
    (target / "builds").mkdir(exist_ok=True)
    (target / "videos").mkdir(exist_ok=True)
    (target / "SNAPSHOT.txt").write_text(
        chr(10).join(copied) + chr(10), encoding="utf-8", newline=""
    )
    print(f"batch {target}: {len(copied)} files copied, SNAPSHOT.txt written")
    return PASS


KEPT = "engine-before-upgrade"  # the batch's copy from before the last upgrade, one generation
PARTS = ("studio", "engine", "docs")


def cmd_upgrade(args) -> int:
    """Replace a batch's copy of the engine with this one. Run the NEWER engine's studio.py; the batch's
    builds, videos and batch.json are not touched. The copy it replaces is kept in <batch>/engine-before-upgrade."""
    batch = load_batch(args.batch)
    if batch is None:
        return NOT_CHECKED
    target = batch.path.resolve()
    if (target / "studio").resolve() == HERE:
        print(
            "REFUSED this studio.py is the batch's own copy: run the newer engine's studio.py upgrade <batch>"
        )
        return REFUSED
    snapshot = target / "SNAPSHOT.txt"
    if not snapshot.is_file() and not args.force:
        print(
            "REFUSED no SNAPSHOT.txt: the copy cannot be checked for edits;"
            " pass --force to replace it unchecked"
        )
        return REFUSED
    checked = snapshot.is_file()
    before = read_snapshot(snapshot)
    # every file the upgrade would drop: an edit, a file added to the copy, a file deleted from it
    local = copy_changes(target, before) if checked else []
    if local and not args.force:
        shown = ", ".join(f"{name} ({state})" for state, name in local[:5]) + (
            " ..." if len(local) > 5 else ""
        )
        print(
            f"REFUSED {len(local)} file(s) of the batch's copy changed since its snapshot ({shown}):"
            " move those edits into the engine first, or pass --force to drop them"
        )
        return REFUSED
    fresh = target / ".engine-upgrade"
    kept = target / KEPT
    try:  # cleared and filled before anything of the batch moves
        for folder in (fresh, kept):
            if folder.exists():
                shutil.rmtree(folder)
        fresh.mkdir()
        copied = copy_engine(fresh)
        kept.mkdir()
    except OSError as error:
        shutil.rmtree(fresh, ignore_errors=True)
        print(
            f"NOT CHECKED upgrade did not start, the batch's copy was not touched: {error}"
        )
        return NOT_CHECKED
    moved: list[str] = []  # the old parts now in kept
    placed: list[str] = []  # the new parts now in the batch
    try:
        # os.replace only renames, never copies: a folder holding an open file fails whole, before any of it moves
        for name in (*PARTS, "SNAPSHOT.txt"):
            if (target / name).exists():
                os.replace(target / name, kept / name)
                moved.append(name)
        for name in PARTS:
            if (fresh / name).is_dir():
                os.replace(fresh / name, target / name)
                placed.append(name)
    except OSError as error:
        left = []  # the old parts that could not go back
        for source, destination, names in (
            (target, fresh, placed),
            (kept, target, moved),
        ):  # the new parts out first, then the old ones back, so the batch is never left with a mixed engine
            for name in reversed(names):
                try:
                    os.replace(source / name, destination / name)
                except OSError:
                    left.append(name)
        shutil.rmtree(fresh, ignore_errors=True)
        if left:
            print(
                f"NOT CHECKED upgrade stopped and could not put back {', '.join(dict.fromkeys(left))}:"
                f" the old copy of those is in {kept}, move it back into {target} by hand ({error})"
            )
        else:
            print(
                f"NOT CHECKED upgrade stopped, the batch's copy is as it was: {error}"
            )
        return NOT_CHECKED
    shutil.rmtree(fresh, ignore_errors=True)
    (target / "SNAPSHOT.txt").write_text(
        chr(10).join(copied) + chr(10), encoding="utf-8", newline=""
    )
    after = {}
    for line in copied:
        digest, _, name = line.partition("  ")
        after[name] = digest
    groups = (
        ("changed", sorted(n for n in after if n in before and before[n] != after[n])),
        ("added", sorted(n for n in after if n not in before)),
        ("removed", sorted(n for n in before if n not in after)),
    )
    for label, names in groups:
        for name in names:
            print(f"{label}: {name}")
    if not checked:  # only with --force
        print(
            "note: there was no SNAPSHOT.txt, so the copy was replaced without an edit check"
        )
    dropped = {
        "changed": "dropped a local edit",
        "added": "dropped an added file",
        "missing": "dropped a local deletion",
    }
    for (
        state,
        name,
    ) in local:  # only with --force; an added file stays in engine-before-upgrade
        print(f"{dropped[state]}: {name}")
    counts = ", ".join(f"{len(names)} {label}" for label, names in groups)
    print(
        f"upgrade {target}: {len(copied)} files, {counts}; the copy before it is in {kept}"
    )
    return PASS


def cmd_new(args) -> int:
    batch = load_batch(args.batch)
    if batch is None:
        return NOT_CHECKED
    if not re.fullmatch(r"\d\d-[a-z0-9]+(-[a-z0-9]+)*", args.slug):
        print(f"slug {args.slug} must look like 01-some-name")
        return USAGE
    build = batch.builds / args.slug
    if build.exists():
        print(f"{build} exists: refusing")
        return REFUSED
    # the film's slug is the name without its number, so two builds of one batch never share it
    slug = re.sub("^[0-9]+-", "", args.slug)
    twin = next(
        (
            item
            for item in sorted(batch.builds.glob("*"))
            if item.is_dir() and re.sub("^[0-9]+-", "", item.name) == slug
        ),
        None,
    )
    if twin is not None:
        print(
            f"REFUSED {twin.name} already has the slug {slug}: name the film another way"
        )
        return REFUSED
    build.mkdir(parents=True)
    for name in TEMPLATES:
        template = HERE / "templates" / name
        if template.is_file():
            text = template.read_text(encoding="utf-8")
        else:
            mark = "#" if name.endswith(".py") else None
            line = f"stub for {name}: the template is not installed yet"
            text = f"# {line}\n" if mark else f"<!-- {line} -->\n"
            print(f"note: templates/{name} is absent, wrote an empty stub")
        for key, value in (
            ("{title}", args.title),
            ("{topic}", args.topic),
            ("{width}", "1080"),
            ("{height}", "1920"),
            ("{fps}", "30"),
            (
                "{slug}",
                slug,
            ),  # the film's slug, as script.json and the timeline carry it
        ):
            text = text.replace(key, value)
        # the date in the heading only: a later {date} is a row the writer fills when something changes
        text = text.replace("{date}", args.date, 1)
        (build / name).write_text(text, encoding="utf-8", newline="")
    print(build)
    return PASS


def cmd_status(args) -> int:
    import status

    batch = load_batch(args.batch)
    return NOT_CHECKED if batch is None else status.show(batch.root)


# ---- stages ----


def script_lines(text: str) -> list[dict]:
    """The lines of a script.md as script.json holds them: the first table whose header has an id column, to
    its last row (every other table is ignored). Raises ValueError, naming what is wrong, when there is no such
    table or a gap is not a number."""
    rows, head, found = [], None, False
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            if found:
                break
            head = None
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if head is None:
            head = [cell.lower() for cell in cells]
            found = "id" in head
        elif found and not all(set(cell) <= set("-: ") for cell in cells):
            rows.append(dict(zip(head, cells)))
    if not rows:
        raise ValueError("script.md has no table with an id column")
    lines = []
    for row in rows:
        if not row.get("id"):
            continue
        beat = row.get("beat", "")
        entry = {
            "id": row["id"],
            "caption": row.get("caption", ""),
            "spoken": row.get("spoken", ""),
            "beat": beat.lower(),
        }
        if beat.lower() == "payoff":
            entry["payoff"] = True
        if row.get("gap"):
            try:
                entry["gap"] = float(row["gap"])
            except ValueError:
                raise ValueError(
                    f"line {row['id']}: gap {row['gap']!r} is not a number"
                ) from None
        lines.append(entry)
    return lines


def cmd_script(args) -> int:
    """script.md table (id, beat, caption, spoken, gap) plus the batch tag and accent into script.json."""
    batch = load_batch(args.build)
    if batch is None:
        return NOT_CHECKED
    source = build_dir(args.build) / "script.md"
    if not source.is_file():
        print(f"missing {source}")
        return NOT_CHECKED
    text = source.read_text(encoding="utf-8")
    try:
        lines = script_lines(text)
    except ValueError as error:
        print(f"FIX {error}")
        return FIX
    target = source.parent / "script.json"
    old = {}
    if target.is_file():
        try:
            old = json.loads(target.read_text(encoding="utf-8"))
        except ValueError:
            old = {}
    first = text.splitlines()[0] if text else ""
    heading = re.match(r"#\s+(.*?)(?:\s+\(script\b.*)?$", first)
    out = {
        # the film's name without the build's number: builds/02-blind-spot-test makes out/blind-spot-test.mp4
        "slug": old.get("slug") or re.sub("^[0-9]+-", "", source.parent.name),
        "title": (heading.group(1) if heading else "") or old.get("title", ""),
        "accent": batch.accent,
        "tag": batch.tag,
        # an earlier per-film voice wins; the batch's speed fills only a missing key
        "voice": {"speed": batch.voice.get("speed", 1.0), **old.get("voice", {})},
    }
    music = dict(old.get("music", {}))
    for key, value in (
        ("theme", args.theme),
        ("track", args.track),
        ("start", args.start),
        ("fade_out", args.fade_out),
        ("duck_db", args.duck_db),
    ):
        if value is not None:
            music[key] = value
    if music:
        music.setdefault("start", 0.0)
        music.setdefault("fade_out", 2.4)
        music.setdefault("duck_db", 12)
        out["music"] = music
    out["lines"] = lines
    target.write_text(
        json.dumps(out, indent=2, ensure_ascii=False) + chr(10),
        encoding="utf-8",
        newline="",
    )
    note = (
        ""
        if music.get("theme") and music.get("track")
        else f" (no music: render refuses until script {args.build} --theme <theme> --track <track>)"
    )
    print(f"script.json: {len(lines)} lines{note}")
    return PASS


def cmd_voice(args) -> int:
    """Narrate script.json, write cues.txt, then hold what the voice says against the script (the engine's
    speech check, Q806): exit 1 when a word is misheard, 2 when the voice or the check could not run."""
    import contextlib
    import io

    audio, build_module = module("audio"), module("build")
    batch = load_batch(args.build)
    if audio is None or build_module is None or batch is None:
        return NOT_CHECKED
    build = build_dir(args.build)
    if not (build / "script.json").is_file():
        print(f"missing {build / 'script.json'}: run script first")
        return NOT_CHECKED
    sys.stdout.flush()
    code = run_script(
        "audio.py", "narrate", build, "--batch", batch.path / "batch.json"
    )
    if code != PASS:
        print(f"NOT CHECKED voice: the narration exited {code}")
        return NOT_CHECKED
    text = io.StringIO()
    with contextlib.redirect_stdout(text):
        build_module.cues(batch, build)
    (build / "cues.txt").write_text(text.getvalue(), encoding="utf-8", newline="")
    print(f"cues.txt: {text.getvalue().count(chr(10))} rows")
    engine = audio.engine_dir(batch)
    done = subprocess.run(
        [
            sys.executable,
            str(engine / "qa.py"),
            "speech",
            str(build / "narration" / "narration.json"),
        ],
        cwd=engine,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    said = (done.stdout + done.stderr).strip()
    proof = build / "proof"
    proof.mkdir(exist_ok=True)
    (proof / "qa_speech.log").write_text(said + chr(10), encoding="utf-8", newline="")
    print(said)
    if done.returncode not in (PASS, FIX) or "SPEECH:" not in done.stdout:
        print(f"NOT CHECKED speech: the check exited {done.returncode}")
        return NOT_CHECKED
    return done.returncode


def cmd_gen(args) -> int:
    gen = module("gen")
    batch = load_batch(args.build)
    if gen is None or batch is None:
        return NOT_CHECKED
    build = build_dir(args.build)
    try:
        code = int(
            gen.run(
                batch,
                build,
                args.cmd,
                only=args.only,
                reseed=args.reseed,
                source=args.source,
            )
            or PASS
        )
    except SystemExit as stop:  # gen.py stops with a message: a refused chain, or a missing input or setting
        if not isinstance(stop.code, str):
            raise
        print(stop.code)
        return REFUSED if stop.code.startswith("clips refused") else NOT_CHECKED
    if args.cmd == "stills" and code == PASS:
        checklist = module("checklist")
        if checklist is not None:
            checklist.write(build)
    return code


def cmd_build(args) -> int:
    build_module = module("build")
    batch = load_batch(args.build)
    if build_module is None or batch is None:
        return NOT_CHECKED
    build = build_dir(args.build)
    timeline = build / "timeline.json"
    if not build.is_dir():
        print(f"missing {build}")
        return NOT_CHECKED
    timeline.unlink(
        missing_ok=True
    )  # first: a build that fails anywhere leaves no timeline
    if (build / "shots.py").is_file():
        done = subprocess.run(
            [sys.executable, "-I", str(build / "shots.py")], cwd=build, check=False
        )
        if done.returncode != 0:
            print("FIX shots.py failed")
            return FIX
    missing = [
        name
        for name in ("script.json", "narration/layout.json", "shots.json")
        if not (build / name).is_file()
    ]
    if missing:
        print(f"missing {', '.join(missing)} in {build}")
        return NOT_CHECKED
    try:
        code = int(build_module.timeline(batch, build) or PASS)
    except (Exception, SystemExit) as error:  # noqa: BLE001 - build.py stops with a message on a bad shot
        timeline.unlink(missing_ok=True)
        print(f"FIX timeline build failed: {error}")
        return FIX
    if code != PASS:
        timeline.unlink(missing_ok=True)
        return code
    import table

    checklist = module("checklist")
    if checklist is not None:
        checklist.write(
            build
        )  # the still checker's list names this timeline's uses and frames
    print(table.write(build))
    return PASS


def qa_stage(stage: str, build: Path) -> int:
    """plan and frames through qa.py's own functions, file as its own process (it loads the engine's checks);
    a check that cannot run is NOT CHECKED and leaves no result from an earlier run to be read as a pass."""
    result = build / "proof" / f"qa_{stage}.json"
    if stage == "file":
        result.unlink(missing_ok=True)
        if not (build / "timeline.json").is_file():
            print("NOT CHECKED file: no timeline.json (run build, then render)")
            return NOT_CHECKED
        sys.stdout.flush()
        code = run_script("qa.py", "file", build)
        if not result.is_file():
            print(f"NOT CHECKED file: the check exited {code} and wrote no result")
            return NOT_CHECKED
        return code
    qa = module("qa")
    if qa is None:
        return NOT_CHECKED
    try:
        call = {
            "plan": lambda: qa.plan(build),
            "frames": lambda: qa.frames(build, None),
        }[stage]
        return int(call() or PASS)
    except (OSError, ImportError, subprocess.CalledProcessError, SystemExit) as error:
        result.unlink(missing_ok=True)
        print(f"NOT CHECKED {stage}: {error}")
        return NOT_CHECKED


RESULTS = {
    "plan": "qa_plan.json",
    "lint": "qa_lint.json",
    "frames": "qa_frames.json",
    "lint-frames": "qa_lint_frames.json",
    "stills": "qa_stills.json",
    "file": "qa_file.json",
}


def load_rows(path: Path) -> list[dict] | None:
    """The rows of a proof/qa_<stage>.json, or None when it is missing or unreadable."""
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return (
        [row for row in rows if isinstance(row, dict)]
        if isinstance(rows, list)
        else None
    )


def run_stage(stage: str, build: Path) -> int:
    """One check stage; `lint-frames` is the frames tier of the lint (it follows `frames` in `all`). A stage that
    cannot run, or that crashes, is NOT CHECKED and leaves no result older than this run; a FIX row accept.json
    names is printed as accepted and left out of the exit code."""
    result = build / "proof" / RESULTS[stage]
    began, rows = time.time(), None
    try:
        if stage in ("lint", "lint-frames"):
            lint = module("lint")
            if lint is None:
                code = NOT_CHECKED
            else:
                rows = lint.report(build, "static" if stage == "lint" else "frames")
                code = lint.exit_code(rows)  # 0, 1 on a FIX, 2 on a NOT CHECKED
        elif stage == "stills":
            checklist = module("checklist")
            if checklist is not None and not isinstance(
                checklist.load(build / "shots.json"), dict
            ):
                print(f"NOT CHECKED stills: no readable shots.json in {build}")
                checklist = None
            # checklist.check returns the FIX count
            code = (
                NOT_CHECKED
                if checklist is None
                else min(int(checklist.check(build)), FIX)
            )
        else:
            code = qa_stage(stage, build)
            if stage == "frames" and code != NOT_CHECKED:
                checklist = module("checklist")
                if checklist is not None:
                    checklist.write(build)  # now it names the frames just shot
    except Exception as error:  # noqa: BLE001 - a check that crashes is not checked, never a FIX
        print(f"NOT CHECKED {stage}: {type(error).__name__}: {error}")
        result.unlink(missing_ok=True)
        return NOT_CHECKED
    if code == NOT_CHECKED:
        if result.is_file() and result.stat().st_mtime < began:
            result.unlink()
    elif code == FIX:
        rows = load_rows(result) if rows is None else rows
        if rows is not None and not open_fixes(build, rows):
            code = PASS
    return code


ALL_ORDER = ("plan", "lint", "frames", "lint-frames", "stills", "file")


def cmd_check(args) -> int:
    choices = (*STAGES, "lint-frames", "all")
    if args.build in choices and args.stage not in choices:
        args.build, args.stage = args.stage, args.build
    if args.stage not in choices:
        print(f"unknown check {args.stage!r}: one of {', '.join(choices)}")
        return USAGE
    build = build_dir(args.build)
    if not build.is_dir():
        print(f"missing {build}")
        return NOT_CHECKED
    refused = refuse_stale(build)
    if refused:
        return refused
    stages = ALL_ORDER if args.stage == "all" else (args.stage,)
    worst = PASS
    for stage in stages:
        code = run_stage(stage, build)
        print(f"check {stage}: exit {code}")
        worst = max(worst, code)
    accept_notes(build)
    if args.stage == "all":
        print(f"check all: exit {worst}")  # the one line a gate reads
    return worst


def accept_entries(build: Path) -> list[dict]:
    path = build / "accept.json"
    try:
        entries = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    except ValueError:
        entries = []
    return (
        [entry for entry in entries if isinstance(entry, dict)]
        if isinstance(entries, list)
        else []
    )


def names_row(entry: dict, row: dict) -> bool:
    """An accept.json entry names a row by its code and its time (within 0.05 s, or both without a time)."""
    if entry.get("code") != row.get("code"):
        return False
    a, b = entry.get("t"), row.get("t")
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 0.05
    return a is None and b is None


def accepted(build: Path, row: dict) -> str | None:
    """Why the owner accepted this finding, from <build>/accept.json: [{"code": "L03", "t": 47.76, "why": "..."}].
    An entry names one row by its code and time (within 0.05 s) and must say why; check, render and package
    leave a row it names out of their exit code."""
    for entry in accept_entries(build):
        if names_row(entry, row) and str(entry.get("why") or "").strip():
            return str(entry["why"]).strip()
    return None


def open_fixes(build: Path, rows: list[dict]) -> list[dict]:
    """The FIX rows accept.json does not name; the accepted ones are printed."""
    found = []
    for row in rows:
        if row.get("level") != "FIX":
            continue
        why = accepted(build, row)
        if why:
            print(
                f"accepted in accept.json: FIX {row.get('code')} at {row.get('t')}: {row.get('what')} ({why})"
            )
        else:
            found.append(row)
    return found


def accept_notes(build: Path) -> None:
    """A NOTE for every accept.json entry that names no FIX row of the current results (proof/qa_*.json)."""
    entries = accept_entries(build)
    if not entries:
        return
    rows = []
    for path in sorted((build / "proof").glob("qa_*.json")):
        rows += load_rows(path) or []
    for entry in entries:
        if not any(names_row(entry, row) for row in rows if row.get("level") == "FIX"):
            print(
                f"NOTE accept.json names no finding: {entry.get('code')} at {entry.get('t')}"
            )


GATE_RENDER = ("qa_plan.json", "qa_lint.json")
GATE_PACKAGE = (
    *GATE_RENDER,
    "qa_frames.json",
    "qa_lint_frames.json",
    "qa_stills.json",
    "qa_file.json",
)


def gate_problems(
    build: Path, names: tuple[str, ...] = GATE_RENDER, video: Path | None = None
) -> list[str]:
    """Why render or package must refuse: a check result that is missing, older than what it checked
    (timeline.json; the video for qa_file.json), or holds a FIX row that accept.json does not name."""
    problems = []
    for name in names:
        path, stage = build / "proof" / name, name[3:-5].replace("_", "-")
        checked = video if name == "qa_file.json" and video else build / "timeline.json"
        registry = build / "proof" / "frames" / "registry.json"
        if (
            name == "qa_lint_frames.json"
            and registry.is_file()
            and registry.stat().st_mtime > checked.stat().st_mtime
        ):
            checked = (
                registry  # the lint's frames tier must have read the frames that stand
            )
        if not path.is_file():
            problems.append(f"proof/{name} is missing: run `check {stage}`")
            continue
        if path.stat().st_mtime < checked.stat().st_mtime:
            problems.append(
                f"proof/{name} is older than {checked.relative_to(build).as_posix()}: run `check {stage}` again"
            )
            continue
        rows = load_rows(path)
        if rows is None:
            problems.append(
                f"proof/{name} is not valid JSON: run `check {stage}` again"
            )
            continue
        problems += [
            f"FIX {row.get('code')} at {row.get('t')}: {row.get('what')} -> {row.get('fix')}"
            for row in open_fixes(build, rows)
        ]
        problems += [  # a result that says a check did not run is not a pass
            f"NOT CHECKED {row.get('code')}: {row.get('what')} -> {row.get('fix')}"
            for row in rows
            if row.get("level") == "NOT CHECKED"
        ]
    return problems


def music_missing(build: Path) -> bool:
    try:
        music = (
            json.loads((build / "script.json").read_text(encoding="utf-8")).get("music")
            or {}
        )
    except (OSError, ValueError, AttributeError):
        music = {}
    return not (music.get("theme") and music.get("track"))


def cmd_render(args) -> int:
    batch = load_batch(args.build)
    if batch is None:
        return NOT_CHECKED
    build = build_dir(args.build)
    timeline = build / "timeline.json"
    if not timeline.is_file():
        print("missing timeline.json: run build first")
        return NOT_CHECKED
    refused = refuse_stale(build)
    if refused:
        return refused
    if music_missing(build):
        print(
            f"REFUSED script.json names no music: run script {args.build} --theme <theme> --track <track>"
        )
        return REFUSED
    problems = gate_problems(build)
    if problems:
        print("REFUSED render: the plan and lint checks do not stand at 0 FIX")
        for item in problems:
            print(f"  {item}")
        return REFUSED
    accept_notes(build)
    render = module("render")
    if render is None:
        return NOT_CHECKED
    options = {
        "workers": args.workers or batch.render.get("workers"),
        "maxrate": args.maxrate or batch.render.get("maxrate"),
    }
    silent = (
        build / "out" / "video.mp4"
    )  # the picture alone; the mix writes out/<slug>.mp4 from it
    silent.parent.mkdir(exist_ok=True)
    try:
        render.render(batch, build, out=silent, **options)
    except (Exception, SystemExit) as error:  # noqa: BLE001 - a render that fails is never a pass
        print(f"NOT CHECKED render: {error}")
        return NOT_CHECKED
    sys.stdout.flush()
    code = run_script(
        "audio.py",
        "mix",
        build,
        "--batch",
        batch.path / "batch.json",
        "--video",
        silent,
    )
    if code != PASS:
        print(f"NOT CHECKED render: the mix exited {code}")
        return NOT_CHECKED
    done = qa_stage("file", build)
    rows = load_rows(build / "proof" / "qa_file.json")
    if done == FIX and rows is not None and not open_fixes(build, rows):
        done = PASS
    import table

    print(table.write(build))
    return done


def cmd_table(args) -> int:
    import table

    build = build_dir(args.build)
    if not (build / "timeline.json").is_file():
        print("missing timeline.json")
        return NOT_CHECKED
    refused = refuse_stale(build)
    if refused:
        return refused
    print(table.write(build))
    return PASS


def cmd_changed(args) -> int:
    import filmdiff

    return filmdiff.report(
        build_dir(args.build), Path(args.before) if args.before else None, args.db
    )


def cmd_keep(args) -> int:
    import filmdiff

    return filmdiff.keep(build_dir(args.build), args.name)


def cmd_package(args) -> int:
    import package

    batch = load_batch(args.build)
    if batch is None:
        return NOT_CHECKED
    build = build_dir(args.build)
    missing = [
        name for name in ("post.json", "timeline.json") if not (build / name).is_file()
    ]
    if missing:
        print(f"missing {', '.join(missing)} in {build}")
        return NOT_CHECKED
    refused = refuse_stale(build)
    if refused:
        return refused
    # package ships only a checked film: the video and every check result must be newer than the timeline
    try:
        slug = json.loads((build / "timeline.json").read_text(encoding="utf-8"))["slug"]
    except (ValueError, KeyError, TypeError) as error:
        print(f"NOT CHECKED: timeline.json names no slug ({error})")
        return NOT_CHECKED
    video = build / "out" / f"{slug}.mp4"
    if not video.is_file():
        print(f"missing {video}: run render first")
        return NOT_CHECKED
    if video.stat().st_mtime < (build / "timeline.json").stat().st_mtime:
        print(f"REFUSED out/{slug}.mp4 is older than timeline.json: run render again")
        return REFUSED
    problems = gate_problems(build, GATE_PACKAGE, video)
    if problems:
        print("REFUSED package: the checks do not stand at 0 FIX on this video")
        for item in problems:
            print(f"  {item}")
        return REFUSED
    if not looked(build, video):
        print(
            f"REFUSED package: nobody has looked at out/{slug}.mp4 since it was rendered: run  look {args.build}  "
            "and open every sheet (three readers saying READY is not the bar)"
        )
        return REFUSED
    accept_notes(build)
    return package.package(batch, build)


def looked(build: Path, video: Path) -> bool:
    """Whether the owner's sheets (proof/look/look_*.png, written by `look`) are newer than the video."""
    sheets = list((build / "proof" / "look").glob("look_*.png"))
    return (
        bool(sheets)
        and min(item.stat().st_mtime for item in sheets) >= video.stat().st_mtime
    )


def cmd_look(args) -> int:
    """Sheets of the finished film at even steps: the owner's own look before the film is packaged."""
    build = build_dir(args.build)
    try:
        slug = json.loads((build / "timeline.json").read_text(encoding="utf-8"))["slug"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"NOT CHECKED: timeline.json names no slug ({error})")
        return NOT_CHECKED
    video = build / "out" / f"{slug}.mp4"
    if not video.is_file():
        print(f"missing {video}: run render first")
        return NOT_CHECKED
    try:
        import sheet
    except ImportError as error:
        print(f"NOT CHECKED: look needs Pillow ({error})")
        return NOT_CHECKED
    try:
        sheets, frames = sheet.look(video, build / "proof" / "look", args.step)
    except (OSError, RuntimeError) as error:
        print(f"NOT CHECKED: {error}")
        return NOT_CHECKED
    for path in sheets:
        print(path)
    print(
        f"look: {frames} frames on {len(sheets)} sheets, one every {args.step:g} s of out/{slug}.mp4: "
        "open every sheet before you package"
    )
    return PASS


def cmd_sheet(args) -> int:
    build = build_dir(args.build)
    proof = build / "proof"
    if args.times:
        try:
            names = [f"t{float(item):07.2f}.png" for item in args.times.split(",")]
        except ValueError:
            print(f"--times {args.times!r} must be seconds separated by commas")
            return USAGE
        refused = refuse_stale(build)  # frames shot from an older timeline
        if refused:
            return refused
        paths = [proof / "frames" / name for name in names]
        out, crop = proof / "strip_times.png", (0, 250, 1080, 1300)
    elif args.clip:
        folder = build / "media" / args.clip
        frames = (
            sorted(item for item in folder.glob("*") if item.suffix in (".png", ".jpg"))
            if folder.is_dir()
            else []
        )
        paths = (
            [frames[round(i * (len(frames) - 1) / 5)] for i in range(6)]
            if len(frames) >= 6
            else frames
        )
        out, crop = proof / f"strip_clip_{args.clip}.png", None
    else:
        ids = [item for item in (args.media or "").split(",") if item]
        paths = [
            next(
                (
                    build / "media" / f"{item}{ext}"
                    for ext in (".png", ".jpg")
                    if (build / "media" / f"{item}{ext}").is_file()
                ),
                build / "media" / item,
            )
            for item in ids
        ]
        out, crop = proof / "strip_media.png", None
    try:
        import sheet
    except ImportError as error:
        print(f"NOT CHECKED: sheet needs Pillow ({error})")
        return NOT_CHECKED
    missing = [str(path) for path in paths if not path.is_file()]
    if missing or not paths:
        print(
            "missing "
            + (", ".join(missing) or "pictures (give --times, --clip or --media)")
        )
        return NOT_CHECKED
    print(sheet.strip(paths, out, args.height, crop))
    return PASS


def reader_files(data) -> list[tuple[str, object]]:
    """What a review run holds, by reader: a list of {key or reader, ...}, an object keyed by reader, or the
    result of the film workflow (its last round that has readers: history[].checks, also inside a task's
    {"result": ...} wrapper), so the file a finished workflow leaves can be saved as it is. Raises ValueError,
    naming why, when it holds no reader: a run that stopped before its readers, a history with no reader in
    any round, an empty list, an item that is not an object, or a shape it does not know."""
    if isinstance(data, dict) and isinstance(data.get("result"), dict):
        data = data["result"]
    if isinstance(data, dict) and data.get("stopped") and "history" not in data:
        raise ValueError(f"the run stopped at {data['stopped']} before any reader")
    if isinstance(data, dict) and isinstance(data.get("history"), list):
        rounds = [
            item["checks"]
            for item in data["history"]
            if isinstance(item, dict)
            and isinstance(item.get("checks"), list)
            and item["checks"]
        ]
        if not rounds:
            raise ValueError("no round of its history holds a reader")
        data = rounds[-1]
    if isinstance(data, list):
        if not data:
            raise ValueError("the list of readers is empty")
        stray = next(
            (n for n, item in enumerate(data, 1) if not isinstance(item, dict)), None
        )
        if stray is not None:
            raise ValueError(f"item {stray} of the list is not an object")
        return [
            (str(item.get("key") or item.get("reader") or f"reader{number}"), item)
            for number, item in enumerate(data, 1)
        ]
    if (
        isinstance(data, dict)
        and data
        and all(isinstance(v, dict) for v in data.values())
    ):
        return list(data.items())
    raise ValueError(
        "it is not a list of readers, an object keyed by reader or a film workflow's result"
    )


def cmd_review(args) -> int:
    build = build_dir(args.build)
    if not build.is_dir():
        print(f"missing {build}")
        return NOT_CHECKED
    reviews = build / "proof" / "reviews"
    if args.action == "save":
        source = Path(args.file)
        if not source.is_file():
            print(f"missing {source}")
            return NOT_CHECKED
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except ValueError as error:
            print(f"FIX {source} is not valid JSON: {error}")
            return FIX
        try:
            readers = reader_files(data)
        except ValueError as error:
            print(f"FIX nothing saved from {source}: {error}")
            return FIX
        reviews.mkdir(parents=True, exist_ok=True)
        used: set[str] = set()
        for reader, payload in readers:
            base = re.sub(r"[^A-Za-z0-9_-]+", "-", reader).strip("-") or "reader"
            name, number = base, 1
            while name in used:  # two readers of one name both keep their file
                number += 1
                name = f"{base}-{number}"
            if name != base:
                print(f"note: a second reader is named {base}; saved as {name}")
            used.add(name)
            target = reviews / f"{args.stage}_{name}.json"
            target.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + chr(10),
                encoding="utf-8",
                newline="",
            )
            print(target)
        return PASS
    rows = []
    saved = sorted(reviews.glob(f"{args.stage}_*.json"))
    if not saved:
        print(
            f"NOT CHECKED no proof/reviews/{args.stage}_*.json in {build}: run review save with that --stage first"
        )
        return NOT_CHECKED
    for path in saved:
        payload = json.loads(path.read_text(encoding="utf-8"))
        reader = path.stem[len(args.stage) + 1 :]
        if not isinstance(payload, dict):
            payload = {"findings": payload if isinstance(payload, list) else []}
        rows.append(f"## {reader}")
        rows.append(f"Verdict: {payload.get('verdict', '(none)')}")
        for label, key in (("Still open", "still_open"), ("Findings", "findings")):
            items = payload.get(key) or []
            rows.append(f"### {label} ({len(items)})")
            for number, item in enumerate(items, 1):
                if isinstance(item, dict):
                    where = " ".join(
                        str(item[k]) for k in ("shot", "time") if item.get(k)
                    )
                    what = (
                        item.get("problem")
                        or item.get("what")
                        or item.get("text")
                        or ""
                    )
                    head = " ".join(
                        part
                        for part in (
                            f"{key}.{number}",
                            str(item.get("severity", "")),
                            where,
                        )
                        if part
                    )
                    rows.append(f"- [ ] {head}: {what}")
                else:
                    rows.append(f"- [ ] {key}.{number}: {item}")
                rows.append("  Answer: ")
        rows.append("")
    target = build / "proof" / f"{args.stage}_answers.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"# Answers: {args.stage}" + chr(10) + chr(10) + chr(10).join(rows) + chr(10),
        encoding="utf-8",
        newline="",
    )
    print(target)
    return PASS


def cmd_diff(args) -> int:
    batch = load_batch(args.batch)
    if batch is None:
        return NOT_CHECKED
    changed = 0
    if args.against == "SNAPSHOT":
        snapshot = batch.path / "SNAPSHOT.txt"
        if not snapshot.is_file():
            print(
                f"NOT CHECKED: no {snapshot} (new-batch writes it); diff --against <folder> compares studio/"
            )
            return NOT_CHECKED
        recorded = read_snapshot(snapshot)
        for state, name in copy_changes(batch.path, recorded):
            changed += 1
            print(f"{state}: {name}")
    else:
        other = Path(args.against).resolve()
        if not other.is_dir():
            print(f"missing {other}")
            return NOT_CHECKED

        def engine_files(
            folder: Path,
        ) -> list[Path]:  # what copy_engine copies from a studio folder
            return [
                path.relative_to(folder)
                for path in sorted(folder.rglob("*"))
                if path.is_file()
                and "__pycache__" not in path.relative_to(folder).parts
                and path.suffix != ".pyc"
                and not any(
                    part.startswith(".") for part in path.relative_to(folder).parts
                )
            ]

        here = engine_files(batch.path / "studio")
        for relative in here:
            path = batch.path / "studio" / relative
            twin = other / relative
            if not twin.is_file() or sha256(twin) != sha256(path):
                changed += 1
                done = subprocess.run(
                    ["git", "diff", "--no-index", "--", str(twin), str(path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                print(done.stdout or f"only here: {relative}")
        for relative in sorted(set(engine_files(other)) - set(here)):
            changed += 1
            print(f"only in {other}: {relative.as_posix()}")
    print(f"{changed} file(s) differ")
    return PASS if changed == 0 else FIX


# ---- parser ----


def day(text: str) -> str:
    """A --date: YYYY-MM-DD."""
    try:
        if not re.fullmatch(r"\d{4}-\d\d-\d\d", text):
            raise ValueError(text)
        time.strptime(text, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{text} is not a date like 2026-11-25"
        ) from None
    return text


def make_parser() -> argparse.ArgumentParser:
    parser = Parser(
        prog="studio.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True, parser_class=Parser)

    def add(name: str, handler, first: str, **kw):
        p = sub.add_parser(name, **kw)
        p.add_argument(first)
        p.set_defaults(handler=handler)
        return p

    p = add("new-batch", cmd_new_batch, "dir")
    p.add_argument("--config", required=True)
    p = add("new", cmd_new, "batch")
    p.add_argument("slug")
    p.add_argument("--title", required=True)
    p.add_argument("--topic", required=True)
    p.add_argument(
        "--date", type=day, default=time.strftime("%Y-%m-%d")
    )  # the local date, as the workflows' `today`
    add("status", cmd_status, "batch")
    p = add("script", cmd_script, "build")
    p.add_argument("--theme")
    p.add_argument("--track")
    p.add_argument("--start", type=float)
    p.add_argument("--fade-out", dest="fade_out", type=float)
    p.add_argument("--duck-db", dest="duck_db", type=float)
    add("voice", cmd_voice, "build")
    for name in ("stills", "clips", "adopt"):
        p = add(name, cmd_gen, "build")
        p.set_defaults(cmd=name)
        p.add_argument("--only")
        p.add_argument("--reseed", action="store_true")
        p.add_argument("--source")
    add("build", cmd_build, "build")
    p = add(
        "check", cmd_check, "build"
    )  # `check <build> <stage>`; `check <stage> <build>` also works
    p.add_argument("stage")
    p = add("render", cmd_render, "build")
    p.add_argument("--workers", type=int)
    p.add_argument("--maxrate", type=int)
    p = add("sheet", cmd_sheet, "build")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--times")
    group.add_argument("--clip")
    group.add_argument("--media")
    p.add_argument("--height", type=int, default=700)
    add("table", cmd_table, "build")
    p = add("review", cmd_review, "action")
    p.add_argument("build")
    p.add_argument("file", nargs="?")
    p.add_argument("--stage", required=True)
    add("package", cmd_package, "build")
    p = add("look", cmd_look, "build")
    p.add_argument("--step", type=float, default=1.25)
    p = add("keep", cmd_keep, "build")
    p.add_argument("name")
    p = add("changed", cmd_changed, "build")
    p.add_argument("--before")
    p.add_argument("--db", type=float, default=45.0)
    p = add("diff", cmd_diff, "batch")
    p.add_argument("--against", default="SNAPSHOT")
    p = add("upgrade", cmd_upgrade, "batch")
    p.add_argument("--force", action="store_true")
    return parser


ENV_FLAG = "ZOETROPE_STUDIO_ENV"  # set in the child, so a command is handed over once and never loops
PACKAGES = ("playwright", "PIL", "numpy")  # requirements.in, by import name
LIGHT_CHECKS = ("plan", "lint", "stills")  # standard library only


def needs_packages(argv: list[str]) -> bool:
    """Whether the command loads playwright, Pillow or numpy: voice, render, sheet, look, and every check but plan,
    lint and stills. The rest runs on the standard library, so `selftest.py --quick` needs no environment."""
    if not argv:
        return False
    if argv[0] in ("voice", "render", "sheet", "look"):
        return True
    return argv[0] == "check" and not any(item in LIGHT_CHECKS for item in argv[1:])


def in_environment(argv: list[str]) -> int | None:
    """Run the command again inside the pinned environment (requirements.txt, through uv) when it needs a package
    this interpreter lacks, so `python studio.py render ...` works from any shell. None means: carry on here."""
    if os.environ.get(ENV_FLAG) or not needs_packages(argv):
        return None
    if all(importlib.util.find_spec(name) is not None for name in PACKAGES):
        return None
    uv = shutil.which("uv")
    if uv is None:
        print(
            f"note: playwright, pillow or numpy is missing and uv is not on PATH: install {HERE / 'requirements.txt'}",
            file=sys.stderr,
        )
        return None
    command = [
        uv,
        "run",
        "--no-project",
        "--with-requirements",
        str(HERE / "requirements.txt"),
    ]
    command += ["python", str(HERE / "studio.py"), *argv]
    sys.stdout.flush()
    return subprocess.run(
        command, env={**os.environ, ENV_FLAG: "1"}, check=False
    ).returncode


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    handed = in_environment(argv)
    if handed is not None:
        return handed
    args = make_parser().parse_args(argv)
    if args.command == "review" and args.action not in ("save", "answers"):
        make_parser().error(f"review {args.action}: the action is save or answers")
    if args.command == "review" and args.action == "save" and not args.file:
        make_parser().error("review save needs a run.json")
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
