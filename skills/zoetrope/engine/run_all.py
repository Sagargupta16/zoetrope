# run_all.py : proof -> picture -> audio -> master -> mux -> QA. Run in stages: proof first, wait for approval, then
# the rest. Every stage takes --size WxH, --fps N and --ss N, read before scenes is imported (a 9:16 run needs no edit).
#   python run_all.py proof          proof gates, proof.png, proof_keys.png, review_times.json and qa_proof.json
#   python run_all.py full [procs]   every frame piped into video.mp4, then audio, master, mux and every QA gate
#   python run_all.py audio          audio, master, mux and QA again on the same video.mp4: no frame is redrawn
# full also takes --budget-mb N (a bitrate cap from a size budget), --keep-frames (frames/ kept as PNG) and, with
# --keep-frames, --redraw T0-T1[,T0-T1] (draw only those passages again, read the rest back from frames/).
# full and audio take --loudness <youtube|spotify|podcast|apple|broadcast|LUFS> (default youtube, -14): the master's
# target, recorded in build.json and read by Q801; audio without it keeps the one build.json already has.
# Delivery variants (none is the approved picture, none runs the gates):
#   python run_all.py draft [procs]  the whole film small (long side 640 px, half the frame rate) with its raw mix, in
#                                    draft.mp4 only: no out.mp4, video.mp4, build.json, approved/, frames.hash or
#                                    thumbs.npy, no approval. Ends with one DRAFT line.
#   python run_all.py alpha [procs] [--format webm|mov]
#                                    scenes.draw_rgba(t) (an RGBA image, E.W x E.H) for every frame into out_alpha.webm
#                                    (VP9 yuva420p) or out_alpha.mov (ProRes 4444 yuva444p10le), with mix.wav as its
#                                    sound when there is one. Ends with one ALPHA line.
#   python run_all.py batch --sizes 1920x1080,1080x1920 <stage> [that stage's flags]
#                                    the stage once per size, each in variants/<WxH>/ made from this folder's sources
#                                    (never its build outputs); one summary line per size.
# full and audio end with an APPROVAL line and exactly one DELIVERED line, or move the file aside and say why:
# <name>.rejected.mp4 when a row is FIX or NOT CHECKED, <name>.unchecked.mp4 when the run broke before a verdict.
import argparse
import ast
import fnmatch
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import contract as C

import engine as E

# the defaults; --size, --fps and --ss replace them before scenes is imported
E.W, E.H, E.FPS, E.SS = 1920, 1080, 30, 1
FULL = (
    E.W,
    E.H,
    E.FPS,
)  # the size and rate the build would have, which a draft is made from
DRAFT_LONG = 640  # px: the long side of a draft
OUT = "out.mp4"  # rename per video: {slug}_{aspect}_{length}s_v{n}.mp4 (up here: batch needs it before the imports)


def draft_size(w, h, fps):
    """(w, h, fps) of a draft of a w x h film at fps: the long side DRAFT_LONG px (both sides even, x264 wants it),
    half the frame rate when that is a whole number of at least 10. About a ninth of the pixels in half the frames."""
    s = min(1.0, DRAFT_LONG / max(w, h))
    dw, dh = (max(2, round(v * s / 2) * 2) for v in (w, h))
    return dw, dh, (fps // 2 if fps % 2 == 0 and fps // 2 >= 10 else fps)


def size_flags(argv):
    """--size, --fps and --ss, read here and not in main(): scenes reads E.W, E.H, E.FPS and E.SS when it is
    imported, and every render worker runs the top of this file again with the same argv. A draft run then swaps
    in draft_size (and SS 1): the stage name is the one token "draft", which no flag takes as a value."""
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--size")
    p.add_argument("--fps", type=int)
    p.add_argument("--ss", type=int)
    a, _ = p.parse_known_args(argv)
    if a.size:
        E.W, E.H = (int(v) for v in a.size.lower().split("x"))
    if a.fps:
        E.FPS = a.fps
    if a.ss:
        E.SS = a.ss
    global FULL
    FULL = (E.W, E.H, E.FPS)
    if "draft" in argv:
        E.W, E.H, E.FPS = draft_size(*FULL)
        E.SS = 1


size_flags(sys.argv[1:])

BATCH_STAGES = ("proof", "full", "audio", "draft", "alpha")
# What a variant folder does not get from the working folder: its build outputs, other variants and caches. Folders
# are named for the top of the folder only (a kit may have a frames/ of its own); the files, anywhere.
NOT_SOURCE_DIRS = {
    "variants",
    "frames",
    "review",
    C.APPROVED,
    "outputs",
    "draft_work",
    "__pycache__",
    ".git",
    ".venv",
    ".ruff_cache",
}
NOT_SOURCE_FILES = (
    OUT,
    C.VIDEO,
    "draft.mp4",
    f"{Path(OUT).stem}_alpha.*",
    "*.rejected.mp4",
    "*.unchecked.mp4",
    "*.log",
    "proof*.png",
    C.THUMBS,
    C.FRAMES_HASH,
    C.MIX_RAW,
    C.MIX,
    C.SFX,
    C.CUESHEET,
    C.CUE_SOUNDS,
    C.BUILD,
    C.BUILD_STATE,
    C.QA_PROOF,
    C.QA_JSON,
    C.REVIEW_TIMES,
)


def batch_summary(text):
    """The line of a stage's output that is its verdict: the last one that starts with a verdict word, else the last."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    marks = ("DELIVERED", "REJECTED", "UNCHECKED", "PROOF:", "DRAFT ", "ALPHA ")
    pick = [ln for ln in lines if ln.startswith(marks)]
    return (pick or lines or ["no output"])[-1]


def batch(argv):
    """run_all.py batch --sizes WxH,WxH <stage> [flags]: the stage once per size, one after the other, each in
    variants/<WxH>/ made from this folder's sources (the engine, scenes.py, local modules, kits, plates, narration;
    NOT_SOURCE_DIRS and NOT_SOURCE_FILES stay behind) with their file times kept, so no build file of one size meets
    another's. Sources are copied over on every run and a variant's own outputs stay, so `batch full` and then
    `batch audio` work. Every refusal comes before the first copy. One line per size; the exit code is the worst of
    the stages."""
    sizes, rest, it = None, [], iter(argv)
    for tok in it:
        if tok == "--sizes":
            sizes = next(it, "")
        elif tok.startswith("--sizes="):
            sizes = tok.split("=", 1)[1]
        else:
            rest.append(tok)
    stage = rest[0] if rest else None
    sizes = [v.strip().lower() for v in (sizes or "").split(",") if v.strip()]
    bad = [v for v in sizes if not re.fullmatch(r"[1-9]\d*x[1-9]\d*", v)]
    why = None
    if not sizes or bad or len(set(sizes)) != len(sizes):
        why = f"--sizes needs distinct WxH values, for example --sizes 1920x1080,1080x1920 (got {', '.join(bad or sizes) or 'none'})"
    elif stage not in BATCH_STAGES:
        why = f"the stage after --sizes must be one of {', '.join(BATCH_STAGES)}"
    elif any(t == "--size" or t.startswith("--size=") for t in rest):
        why = "batch sets --size itself: give --sizes only"
    elif not Path("scenes.py").is_file():
        why = "no scenes.py here: run it from the video's working folder"
    if why:
        print(f"BATCH refused: {why}")
        return 1

    def ignore(folder, names):
        top = Path(folder).resolve() == Path.cwd().resolve()
        skip = {n for n in names if top and n in NOT_SOURCE_DIRS}
        for pat in NOT_SOURCE_FILES:
            skip |= set(fnmatch.filter(names, pat))
        return skip

    worst = 0
    for size in sizes:
        where = Path("variants", size)
        shutil.copytree(".", where, ignore=ignore, dirs_exist_ok=True)
        log = where / "run.log"
        with log.open("wb") as f:
            rc = subprocess.run(
                [sys.executable, "run_all.py", *rest, "--size", size],
                cwd=where,
                stdin=subprocess.DEVNULL,
                stdout=f,
                stderr=subprocess.STDOUT,
                check=False,
            ).returncode
        said = batch_summary(log.read_text(encoding="utf-8", errors="replace"))
        print(f"BATCH {size} {stage} exit {rc}: {said} (log {log.as_posix()})")
        worst = max(worst, rc)
    return worst


if __name__ == "__main__" and sys.argv[1:2] == ["batch"]:
    sys.exit(batch(sys.argv[2:]))

import plate3d

# A 3D plate older than its stage script, unfinished, still being rendered or (for the full render) of proof quality:
# say so and stop here, before scenes.py opens it, or the reader gets a traceback from that import in place of the
# command that clears it. Only the run itself asks: a render worker runs the top of this file again under another
# name.
if __name__ == "__main__" and (
    _stale := plate3d.check(final=sys.argv[1:2] == ["full"])
):
    for _why in _stale:
        print(f"PLATE: {_why}")
    sys.exit(1)

import footage

# The same for a video clip a scene reads (footage.Clip): no cache, a cache made from other bytes, or frames missing.
if __name__ == "__main__" and (_clips := footage.check()):
    for _why in _clips:
        print(f"CLIP: {_why}")
    sys.exit(1)

import audio
import proof
import qa
import render
import scenes

CRF = 18  # 20 for grain-heavy styles (formats.md)
# True peak of the decoded mp4, dBTP: gate 8's limit, the EBU R128 meter tolerance kept clear of it (so the aim is
# -1.3), how many re-masters master_and_mux may run, and the extra dB each one takes off. First ceiling: audio.CEILING.
TP_MAX, TP_TOL, RETRIES, MARGIN = -1.0, 0.3, 3, 0.2
FFMPEG_FALLBACKS = (
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
)  # when ffmpeg is not on PATH (macOS)


def find_ffmpeg():
    """ffmpeg on PATH, else a known install, whose folder then goes on PATH so qa.py's own ffprobe and ffmpeg calls
    find it too (they call them by name)."""
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    for p in FFMPEG_FALLBACKS:
        if Path(p).exists():
            os.environ["PATH"] = (
                f"{Path(p).parent}{os.pathsep}{os.environ.get('PATH', '')}"
            )
            return p
    return None


def clean(*names):
    """A failed run must not leave the last good file to be reviewed."""
    for p in (*names, *Path().glob("*.rejected.mp4"), *Path().glob("*.unchecked.mp4")):
        Path(p).unlink(missing_ok=True)


def mb(path):
    return f"{Path(path).stat().st_size / 1e6:.1f} MB"


def proof_stage():
    """The proof gates on drawn frames (qa.proof_rows, purity, lint, the quiz) first, so the key sheet can show the
    moments they name, then proof.png and proof_keys.png. Exit 1 on any FIX, else 2 on any NOT CHECKED."""
    import qa_lint
    import qa_purity
    import qa_quiz

    C.write_state("proof", "running")
    rows = (
        qa.proof_rows(scenes, E.W, E.H, E.FPS)
        + qa_purity.run(".", E.FPS, (E.W, E.H))
        + qa_lint.run("scenes.py")
        + qa_quiz.quiz_rows(".", scenes, E.FPS)
    )
    C.write_rows(rows, C.QA_PROOF)
    proof.contact_sheet("proof.png")  # then show it in a session tab, ask for approval
    print(f"wrote proof.png ({len(proof.proof_times(scenes.SCHEDULE))} stills)")
    out, n_keys, n_shown = proof.key_sheet(findings=rows)  # prints the sheets it wrote
    print(f"{out}: {n_shown} of {n_keys} key moments; {C.REVIEW_TIMES}, {C.QA_PROOF}")
    for r in rows:
        print(C.line(r))
    verdict = C.summary(rows, "PROOF")
    print(verdict)
    C.write_state("proof", "done", [verdict])
    return C.exit_code(rows)


def caps(budget_mb, duration, silent):
    """(maxrate, bufsize) in kb/s for a size budget (Z14): 95 percent of it spread over the duration, less the audio;
    bufsize equal to maxrate under 30 s, else twice it. x264's VBV can still pass the total by up to about
    0.9 x bufsize, so this is a cap, not a guarantee: Q1001 checks the file itself."""
    akbps = (
        0.0 if silent else float(C.AAC_ARGS[C.AAC_ARGS.index("-b:a") + 1].rstrip("k"))
    )
    maxrate = 0.95 * budget_mb * 8000 / duration - akbps
    if maxrate <= 0:
        raise SystemExit(
            f"a {budget_mb:g} MB budget leaves no video bitrate for {duration:g} s with {akbps:g} kb/s of audio"
        )
    return maxrate, (maxrate if duration < 30 else 2 * maxrate)


def redraw_spans(arg):
    """--redraw T0-T1[,T0-T1] as [(t0, t1), ...] in seconds; ValueError names the first span that is not two
    finite numbers with T0 under T1."""
    spans = []
    for s in arg.split(","):
        try:
            t0, t1 = (float(v) for v in s.split("-"))
        except ValueError:
            raise ValueError(
                f"--redraw: {s!r} is not T0-T1 in seconds (for example 1.5-3)"
            ) from None
        if not (math.isfinite(t0) and math.isfinite(t1) and t0 < t1):
            raise ValueError(
                f"--redraw: {s!r} must be two finite times in seconds with T0 under T1"
            )
        spans.append((t0, t1))
    return spans


def picture(ff, a, budget, redraw):
    """Every frame drawn and piped into video.mp4, the silent picture (capped when a size budget is set); redraw: the
    parsed --redraw spans, or None."""
    maxrate = bufsize = None
    if budget:
        maxrate, bufsize = caps(budget, scenes.DURATION, C.declared(scenes, "SILENT"))
        print(
            f"size budget {budget:g} MB for {scenes.DURATION:g} s: maxrate {maxrate:.0f} kb/s, "
            f"bufsize {bufsize:.0f} kb/s (a cap, not a guarantee: Q1001 checks the file)"
        )
    t0 = time.perf_counter()
    n = render.render_to_ffmpeg(
        C.VIDEO, a.procs, CRF, maxrate, bufsize, a.keep_frames, redraw, ff
    )
    print(
        f"wrote {C.VIDEO} ({n} frames, {E.W}x{E.H} at {E.FPS} fps, SS {E.SS}, {mb(C.VIDEO)}) "
        f"in {time.perf_counter() - t0:.1f} s"
    )


def picture_is_current():
    """True when video.mp4 still shows today's scenes.py: the first, middle and last frame of every SCHEDULE span
    (at most 12 in all) are drawn again and hashed against frames.hash. The audio stage reuses the picture, so this
    is the only thing tying it to the source when no approval exists."""
    n = render.frame_count(scenes)
    m = C.read_frame_manifest() or {}
    was = (m.get("w"), m.get("h"), m.get("fps"), m.get("ss", 1), m.get("n"))
    if was != (E.W, E.H, E.FPS, E.SS, n):
        print(
            f"{C.VIDEO} was rendered at {was[0]}x{was[1]}, {was[2]} fps, SS {was[3]}, {was[4]} frames; this run is "
            f"{E.W}x{E.H}, {E.FPS} fps, SS {E.SS}, {n} frames: pass the same --size, --fps and --ss, or run run_all.py full"
        )
        return False
    at = sorted(
        {
            min(n - 1, max(0, C.frame_of(t, E.FPS) - back))
            for a, b in scenes.SCHEDULE.values()
            for t, back in ((a, 0), ((a + b) / 2, 0), (b, 1))
        }
    )
    if len(at) > 12:
        at = sorted({at[round(k * (len(at) - 1) / 11)] for k in range(12)})
    if old := render.stale(scenes, at):
        print(
            f"{C.VIDEO} predates scenes.py: frame {old[0]} ({old[0] / E.FPS:.2f} s) and {len(old) - 1} more of "
            f"{len(at)} checked differ from {C.FRAMES_HASH} (or its size, fps, SS or length): run run_all.py full"
        )
        return False
    return True


def mux(ff, mix):
    """video.mp4 and mix.wav (None: a silent piece) into OUT with contract.mux_cmd, the one mux qa.py calib runs too:
    the picture stream copied, the audio encoded once, cut to the shorter one."""
    r = subprocess.run(
        C.mux_cmd(ff, C.VIDEO, mix, OUT), capture_output=True, text=True, check=False
    )
    if r.returncode:
        Path(OUT).unlink(missing_ok=True)
        raise RuntimeError(
            f"mux failed (exit {r.returncode}): {r.stderr.strip()[-600:]}"
        )


def _clean_master(m, loud):
    """A master that leaves the file inside gate 8 with its own rows (Q805) clean."""
    return loud["peak"] <= TP_MAX and not any(
        r.status in (C.FIX, C.NOT_CHECKED) for r in m.get("rows", [])
    )


def master_and_mux(ff, target=qa.LOUDNESS_DEFAULT):
    """Master, mux, then measure the true peak of the decoded mp4, which the AAC encode raises. While it is over the
    aim (-1 dBTP less the 0.3 dB meter tolerance), master and mux again at most 3 times: new ceiling = min(ceiling,
    the mix's own true peak) - (excess + margin) / slope, where slope is how far the file's peak really moved per dB
    of ceiling over the last two tries (1 at first; measured 0.69 on one mix). Lowering a ceiling the limiter never
    reached changes nothing (Z03), so a peak that does not follow the ceiling stops the loop. Then the kept master:
    the clean one (Q805 clean, file inside -1 dBTP) with the lowest peak, else the try with the lowest peak and the
    gentlest ceiling; it is mastered and muxed again if it is not the last. A lower ceiling makes the limiter work
    harder, so this keeps a file that passed from becoming a reject. One line per master, for the delivery report.
    target: the LUFS the master aims at (--loudness). Returns (the kept master's rows, the file's loudness)."""
    aim, ceiling, tries = TP_MAX - TP_TOL, audio.CEILING, []
    for k in range(RETRIES + 1):
        m = audio.master(C.MIX_RAW, C.MIX, ff, target=target, TP=ceiling)
        mux(ff, C.MIX)
        loud = qa.loud(OUT, ff)
        tries.append((ceiling, m, loud))
        what = "master" if k == 0 else f"re-master {k} of {RETRIES}"
        own = ", ".join(f"{r.code} {r.status}" for r in m.get("rows", []))
        print(
            f"{what}: ceiling {ceiling:.2f} dBTP, {C.MIX} {m['I']:.1f} LUFS at {m['tp']:.2f} dBTP"
            f"{f' ({own})' if own else ''} -> {OUT} {loud['I']:.1f} LUFS at {loud['peak']:.2f} dBTP"
        )
        if loud["peak"] <= aim or k == RETRIES:
            break
        slope = 1.0
        if len(tries) > 1:
            (c0, _, l0), (c1, _, l1) = tries[-2:]
            slope = (l0["peak"] - l1["peak"]) / (c0 - c1) if c0 != c1 else 0.0
            if slope < 0.1:
                print(
                    f"the file's peak did not follow the ceiling ({c0:.2f} to {c1:.2f} dBTP moved it "
                    f"{l0['peak']:.2f} to {l1['peak']:.2f}): no lower ceiling will help"
                )
                break
        ceiling = min(ceiling, m["tp"]) - (loud["peak"] - aim + MARGIN) / min(
            1.0, max(0.25, slope)
        )
    clean = [t for t in tries if _clean_master(t[1], t[2])]
    best = min(clean or tries, key=lambda t: (t[2]["peak"], -t[0]))
    if best is not tries[-1]:
        ceiling = best[0]
        m = audio.master(C.MIX_RAW, C.MIX, ff, target=target, TP=ceiling)
        mux(ff, C.MIX)
        loud = qa.loud(OUT, ff)
        print(
            f"kept the {'cleanest' if clean else 'least limited'} master: ceiling {ceiling:.2f} dBTP -> {OUT} "
            f"{loud['I']:.1f} LUFS at {loud['peak']:.2f} dBTP"
        )
    if aim < loud["peak"] <= TP_MAX:
        print(
            f"note: {loud['peak']:.2f} dBTP is inside gate 8 but within the {TP_TOL:g} dB meter tolerance of it "
            "(a lower ceiling made the master fail its own check)"
        )
    if loud["peak"] > TP_MAX:
        print(
            f"true peak still over {TP_MAX:g} dBTP after {len(tries) - 1} re-masters: lower the hits Q802 names"
        )
    return list(m.get("rows", [])), loud


def guarded(module, fn, *args):
    """fn's rows, or qa.check's own Q100 NOT CHECKED row for a gate module that raised: a gate that crashes is not a
    verdict on the file, and the build still gets every other row."""
    try:
        return fn(*args)
    except Exception as e:  # noqa: BLE001 - a crashing gate becomes its Q100 row, as qa.check does
        return [qa._module_row(module, e)]


def is_approval(r):
    """A row about the approval (qa_approve's own codes, or its crash): a review state, never a file defect."""
    import qa_approve

    return r.code in qa_approve.OWN or (r.code == "Q100" and r.item == "qa_approve")


APPROVAL_STATE = {
    C.PASS: "current",
    C.NOTE: "note",
    C.FIX: "stale",
    C.NOT_CHECKED: "unknown",
}


def approval_line(own):
    """APPROVAL: none yet | current | stale: <what> -> <next step>, from the approval rows' fields (code, status,
    item, fix), never from their wording."""
    stale = [r for r in own if r.status in (C.FIX, C.NOT_CHECKED)]
    if stale:
        what = ", ".join(
            f"{r.code} {r.item}" if r.item else f"{r.code} {r.status}" for r in stale
        )
        return f"APPROVAL: stale: {what} -> re-review the changed scenes, then qa.py approve"
    if own:
        then = next((r.fix for r in own if r.status == C.NOTE and r.fix), None)
        return f"APPROVAL: current -> {then or 'nothing to do: the approval covers this build'}"
    return "APPROVAL: none yet -> final review, then qa.py approve"


def set_aside(tag, why):
    """Move OUT aside, so the deliverable path never holds a file that failed or was never judged: tag "rejected"
    for a FIX or NOT CHECKED row, "unchecked" when the run broke before a verdict."""
    if Path(OUT).exists():
        dst = Path(OUT).with_name(f"{Path(OUT).stem}.{tag}.mp4")
        Path(OUT).replace(dst)
        print(f"{tag.upper()} {dst}: {why}")


def scorer():
    """What makes this build's sound: score.py's render_audio when the working folder has one, else the template's
    (audio.render_audio). The contract is the template's: render_audio(scenes, folder=".", fps=None) writes MIX_RAW,
    SFX, the cue sheet and its sounds, and returns their paths. The file is parsed first, never run to find out: an
    older kit's score.py is a script, not this function."""
    p = Path("score.py")
    if p.is_file():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        if any(
            isinstance(n, ast.FunctionDef) and n.name == "render_audio"
            for n in tree.body
        ):
            import score

            return score.render_audio
    return audio.render_audio


def deliver(ff, budget, stage="full", target=qa.LOUDNESS_DEFAULT):
    """Audio, master and mux with the decoded-file true-peak loop, then the scans of the drawn frames (thumbs.npy) and
    every gate on the file (Z10). Any FIX or NOT CHECKED row moves the file to <name>.rejected.mp4 and says why; the
    approval rows are a review state and give the APPROVAL line instead; an error before the verdict (in any step,
    or an interrupt) moves it to <name>.unchecked.mp4 and the error stands. The rows' moments join review_times.json
    and the review sheets are redrawn with every row the verdict used. A clean pass ends with the APPROVAL line and
    one DELIVERED line. build_state.json gets the verdict lines; after an error it still says the stage is running."""
    import qa_scan

    silent = C.declared(scenes, "SILENT")
    rows, loud, judged = [], None, False
    try:
        if silent:
            mux(ff, None)
        else:
            t0 = time.perf_counter()
            made = scorer()(scenes, fps=E.FPS)  # cut sounds land on frames
            names = ", ".join(Path(p).name for p in made.values())
            print(f"wrote {names} in {time.perf_counter() - t0:.1f} s")
            rows, loud = master_and_mux(ff, target)
        if Path(C.THUMBS).exists() and Path(C.FRAMES_HASH).exists():
            # Q1101 to Q1104 on every drawn frame, before the encode
            rows += guarded("qa_scan", qa_scan.scan_thumbs, ".", scenes)
        rows += qa.check(
            OUT,
            fps=E.FPS,
            size=f"{E.W}x{E.H}",
            bpm=getattr(scenes, "BPM", None),
            scenes_dir=".",
            max_mb=budget,
            silent=silent,
            loudness=target,
        )
        judged = True
    finally:
        if not judged:
            set_aside(
                "unchecked", "the run broke before the QA verdict (the error follows)"
            )
    # printed only now, outside the try: a print that fails (a character the console cannot show) is not a verdict
    own = [r for r in rows if is_approval(r)]
    rows = [r for r in rows if not is_approval(r)]
    for r in rows:
        print(C.line(r))
    for r in own:
        print(
            f"approval {APPROVAL_STATE.get(r.status, r.status)}: {r.code} {r.msg}"
            + (f" -> {r.fix}" if r.fix else "")
        )
    verdict = C.summary(rows)
    print(verdict)
    bad = [f"{r.code} {r.status}" for r in rows if r.status in (C.FIX, C.NOT_CHECKED)]
    if bad:
        set_aside("rejected", ", ".join(bad))
    C.add_review_times(proof.finding_entries(rows + own))
    # proof_keys.png, proof_strips.png and proof_gantt.png with every row the verdict used
    proof.keys(rows=rows + own)
    if bad:
        C.write_state(stage, "done", [verdict, f"REJECTED: {', '.join(bad)}"])
        return C.exit_code(rows) or 1
    approval = approval_line(own)
    print(approval)
    p = qa.probe(OUT)
    sound = (
        "silent" if loud is None else f"{loud['I']:.1f} LUFS, {loud['peak']:.1f} dBTP"
    )
    delivered = f"DELIVERED {Path(OUT).resolve().as_posix()} ({p['size_mb']:.1f} MB, {p['duration']:.2f} s, {sound})"
    print(delivered)
    C.write_state(stage, "done", [verdict, approval, delivered])
    return 0


def record_build(loudness=None):
    """C.write_build for this run's size, plus the "loudness" key (the LUFS Q801 wants). loudness None keeps the one the
    last build recorded (a proof run in between must not reset it) and writes none when there never was one."""
    p = Path(C.BUILD)
    try:
        kept = json.loads(p.read_text(encoding="utf-8")).get("loudness")
    except (OSError, ValueError, AttributeError):
        kept = None
    C.write_build(E.W, E.H, E.FPS, E.SS)
    loudness = kept if loudness is None else loudness
    if loudness is not None:
        b = json.loads(p.read_text(encoding="utf-8"))
        p.write_text(json.dumps({**b, "loudness": loudness}), encoding="utf-8")


DRAFT = "draft.mp4"
DRAFT_DIR = "draft_work"  # scratch for the draft (its picture, raw mix and cue sheet); gone when the stage ends
DRAFT_CRF = 30


def draft_stage(ff, procs):
    """The whole film as draft.mp4: drawn at draft_size (E.W, E.H and E.FPS were set to it before scenes was imported),
    encoded veryfast, with scenes' raw mix (not mastered) when it has sound. Frames are pure functions of t, so a draft
    frame is the very frame the full build draws at that time; with the rate halved, every draft frame is also one of
    the full build's frames, and a cut or cue lands within half a draft frame (1/30 s at 15 fps) of where the full
    build puts it. Nothing of the real build is touched: not out.mp4, video.mp4, build.json, build_state.json,
    approved/, frames.hash, thumbs.npy, nor the mix and cue sheet of the last build (the sound is made in DRAFT_DIR).
    Refusals come before the old draft is removed."""
    silent = C.declared(scenes, "SILENT")
    shutil.rmtree(DRAFT_DIR, ignore_errors=True)
    Path(DRAFT).unlink(missing_ok=True)
    Path(DRAFT_DIR).mkdir()
    ok, t0 = False, time.perf_counter()
    try:
        picture = f"{DRAFT_DIR}/picture.mp4"
        render.render_to_ffmpeg(picture, procs, DRAFT_CRF, ff=ff, draft=True)
        mix = None
        if not silent:
            scorer()(scenes, folder=DRAFT_DIR, fps=E.FPS)
            mix = f"{DRAFT_DIR}/{C.MIX_RAW}"
        r = subprocess.run(
            C.mux_cmd(ff, picture, mix, DRAFT),
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode:
            raise RuntimeError(
                f"draft mux failed (exit {r.returncode}): {r.stderr.strip()[-600:]}"
            )
        ok = True
    finally:
        shutil.rmtree(DRAFT_DIR, ignore_errors=True)
        if not ok:
            Path(DRAFT).unlink(missing_ok=True)
    p = qa.probe(DRAFT, ff)
    n, d = (int(x) for x in p["fps"].split("/"))
    print(f"wrote {DRAFT} in {time.perf_counter() - t0:.1f} s ({mb(DRAFT)})")
    print(
        f"DRAFT {Path(DRAFT).resolve().as_posix()} ({p['w']}x{p['h']}, {n / d:g} fps, {p['duration']:.2f} s)"
    )
    return 0


def flag_of(args, name):
    """The value after name in an ffmpeg argument list."""
    return args[args.index(name) + 1]


def alpha_refusal(ff, fmt):
    """Why the alpha stage cannot run, or None. Checked before anything is written: scenes.py needs draw_rgba(t) giving
    an RGBA image of the build's size (frame 0 is drawn once here to see), and this ffmpeg needs the picture encoder
    of the format and the audio encoder its sound would use."""
    draw = getattr(scenes, "draw_rgba", None)
    if not callable(draw):
        return (
            "scenes.py has no draw_rgba(t): add a function that returns an RGBA image of E.W x E.H with the "
            "transparent parts at alpha 0 (draw(t) stays the picture the other stages use)"
        )
    try:
        render.checked_rgba(draw(0.0), 0)
    except (ValueError, AttributeError) as e:
        return f"scenes.draw_rgba(0) is not an RGBA image of {E.W}x{E.H}: {e}"
    _, video, _, audio = render.ALPHA[fmt]
    r = subprocess.run(
        [ff, "-nostdin", "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=False,
    )
    have = {w[1] for w in (ln.split() for ln in r.stdout.splitlines()) if len(w) > 1}
    for enc in (flag_of(video, "-c:v"), flag_of(audio, "-c:a")):
        if enc not in have:
            return f"this ffmpeg has no {enc} encoder (ffmpeg -encoders), which {fmt} output needs"
    return None


ALPHA_PIX = re.compile(r"^(yuva|gbra|rgba|bgra|argb|abgr|ya\d)")


def alpha_stage(ff, procs, fmt):
    """scenes.draw_rgba(t) for every frame into <OUT stem>_alpha.webm (VP9 yuva420p) or .mov (ProRes 4444
    yuva444p10le), with mix.wav as its sound when the last build made one (this stage does not master or mix). The file
    is read back before it is called done: its pixel format (VP9's native decoder reports yuv420p and the alpha_mode
    tag, so ffprobe is asked with libvpx-vp9) must carry alpha, and its length must match DURATION. Prints one ALPHA
    line. Not gated by qa.py: the gates are for the H.264 deliverable."""
    ext = render.ALPHA[fmt][0]
    out = f"{Path(OUT).stem}_alpha.{ext}"
    silent = C.declared(scenes, "SILENT")
    mix = None if silent or not Path(C.MIX).exists() else C.MIX
    if not silent and not mix:
        print(f"note: no {C.MIX} here (run full or audio first), so {out} has no sound")
    if mix:
        # a mix of another length would only be found after the whole render: refuse first
        try:
            got = float(
                C.ffprobe_json(
                    mix, "-show_entries", "format=duration", ffprobe=C.ffprobe_of(ff)
                )["format"]["duration"]
            )
        except (subprocess.CalledProcessError, KeyError, ValueError) as e:
            print(
                f"ALPHA refused: {C.MIX} cannot be read ({e}); run full or audio again"
            )
            return 1
        if abs(got - scenes.DURATION) > 0.1:
            print(
                f"ALPHA refused: {C.MIX} is {got:.2f} s and the film is {scenes.DURATION:.2f} s (made before the "
                "timeline changed): run full again, or delete it for a silent alpha file"
            )
            return 1
        if Path(mix).stat().st_mtime < Path("scenes.py").stat().st_mtime:
            print(
                f"note: {C.MIX} is older than scenes.py, so its sound may not match the picture; run full for a "
                "fresh mix"
            )
    Path(out).unlink(missing_ok=True)
    t0 = time.perf_counter()
    try:
        n = render.render_to_ffmpeg(out, procs, ff=ff, alpha=fmt, mix=mix)
        tag = ["-c:v", "libvpx-vp9"] if fmt == "webm" else []
        j = C.ffprobe_json(
            out,
            *tag,
            "-show_entries",
            "stream=codec_type,pix_fmt:stream_tags=alpha_mode:format=duration",
            ffprobe=C.ffprobe_of(ff),
        )
        v = next(s for s in j["streams"] if s["codec_type"] == "video")
        pix = v.get("pix_fmt", "?")
        has_alpha = (
            bool(ALPHA_PIX.match(pix)) or v.get("tags", {}).get("alpha_mode") == "1"
        )
        dur = float(j["format"]["duration"])
        if not has_alpha:
            raise RuntimeError(f"{out} came back as {pix} with no alpha channel")
        if abs(dur - n / E.FPS) > 0.1:
            raise RuntimeError(f"{out} is {dur:.2f} s, the film is {n / E.FPS:.2f} s")
    except BaseException:
        Path(out).unlink(missing_ok=True)
        raise
    print(f"wrote {out} ({n} frames) in {time.perf_counter() - t0:.1f} s")
    print(
        f"ALPHA {Path(out).resolve().as_posix()} ({E.W}x{E.H}, {E.FPS} fps, {dur:.2f} s, {pix}, {mb(out)}, "
        f"{'with ' + C.MIX if mix else 'no sound'})"
    )
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="build stages for one video, run from its working folder"
    )
    ap.add_argument(
        "stage",
        choices=("proof", "full", "audio", "draft", "alpha"),
        help="(batch --sizes WxH,WxH <stage> runs one of these once per size)",
    )
    ap.add_argument(
        "procs",
        nargs="?",
        type=int,
        help="full, draft, alpha: render processes (default cores / 4, at most 8)",
    )
    ap.add_argument("--size", help="WxH, for example 1080x1920 (default 1920x1080)")
    ap.add_argument("--fps", type=int, help="frames per second (default 30)")
    ap.add_argument(
        "--ss",
        type=int,
        help="supersampling: draw at N times the size, then scale down (default 1; 2 for thin lines and small text)",
    )
    ap.add_argument(
        "--budget-mb",
        type=float,
        help="size budget in MB: caps the video bitrate (formats.md); Q1001 checks the file",
    )
    ap.add_argument(
        "--keep-frames",
        action="store_true",
        help="full: also keep every frame as PNG in frames/",
    )
    ap.add_argument(
        "--redraw",
        help="full --keep-frames: T0-T1[,T0-T1] seconds to draw again; the rest is read back from frames/",
    )
    ap.add_argument(
        "--loudness",
        help="full, audio: the master's target, youtube or spotify (-14, the default), podcast or apple (-16), "
        "broadcast (-23, EBU R128), or a number of LUFS; recorded in build.json for Q801",
    )
    ap.add_argument(
        "--format",
        choices=tuple(render.ALPHA),
        help="alpha: webm (VP9 yuva420p, the default) or mov (ProRes 4444)",
    )
    a = ap.parse_args()
    target = None
    if a.loudness is not None:
        if a.stage not in ("full", "audio"):
            ap.error("--loudness is for the full and audio stages")
        try:
            target = qa.loudness_target(a.loudness)
        except ValueError as e:
            ap.error(str(e))
    if a.format and a.stage != "alpha":
        ap.error("--format is for the alpha stage")
    if a.stage in ("draft", "alpha") and (a.budget_mb or a.keep_frames or a.redraw):
        ap.error(f"{a.stage} takes no --budget-mb, --keep-frames or --redraw")
    if a.redraw and not a.keep_frames:
        ap.error(
            "--redraw needs --keep-frames (and frames/ from an earlier --keep-frames run)"
        )
    # parsed here once, so a bad span stops the run before anything is cleaned
    redraw = None
    if a.redraw and a.stage == "full":
        try:
            redraw = redraw_spans(a.redraw)
        except ValueError as e:
            ap.error(str(e))
    asked = (a.size and a.size.lower() != f"{E.W}x{E.H}") or (a.fps and a.fps != E.FPS)
    if a.stage == "draft":
        if (E.W, E.H, E.FPS, E.SS) != (*draft_size(*FULL), 1):
            print(
                f"note: scenes.py sets {E.W}x{E.H} at {E.FPS} fps, SS {E.SS} itself, so this draft is not made smaller"
            )
    elif asked or (a.ss and a.ss != E.SS):
        print(
            f"note: scenes.py sets {E.W}x{E.H} at {E.FPS} fps, SS {E.SS} itself, which wins over --size, --fps and --ss"
        )
    budget = a.budget_mb or getattr(scenes, "BUDGET_MB", None)
    if a.stage != "proof":
        ff = find_ffmpeg()
        if not ff:
            print(
                "NO_FFMPEG: no ffmpeg on this machine. Every rung of the encode ladder needs one: install an ffmpeg "
                "with libx264, then check it with setup.sh"
            )
            return 1
        # every refusal comes before the clean-up, so a refused run leaves the last build and build.json as they were
        if a.stage == "audio" and not Path(C.VIDEO).exists():
            print(f"no {C.VIDEO} here: run `run_all.py full` first")
            return 1
        if a.stage == "audio" and not picture_is_current():
            return 1
        if a.stage == "full" and budget:
            caps(budget, scenes.DURATION, C.declared(scenes, "SILENT"))
        if redraw:
            _, why = render.reuse_check(render.frame_count(scenes), E.FPS, redraw)
            if why:
                print(f"--redraw: {why}")
                return 1
        if a.stage == "alpha" and (why := alpha_refusal(ff, a.format or "webm")):
            print(f"ALPHA refused: {why}")
            return 1
        # a draft and an alpha file are not the build: neither writes build.json nor build_state.json
        if a.stage == "draft":
            return draft_stage(ff, a.procs)
        if a.stage == "alpha":
            return alpha_stage(ff, a.procs, a.format or "webm")
    # full masters to --loudness (youtube, -14, when none is given); audio keeps what build.json says unless it is given
    if a.stage == "full":
        target = qa.LOUDNESS_DEFAULT if target is None else target
    elif a.stage == "audio" and target is None:
        target = qa.build_loudness()
    # the size this build really uses (after scenes.py), for qa.py purity, lint, diff, approve and proof.py keys;
    # here and not at the top, which every render worker runs again
    record_build(target)
    if a.stage == "proof":
        return proof_stage()
    built = (C.MIX_RAW, C.SFX, C.CUESHEET, C.CUE_SOUNDS, C.MIX, OUT)
    if a.stage == "full":
        built += (C.VIDEO, f"{C.VIDEO}.log", C.FRAMES_HASH, C.THUMBS)
    clean(*built)
    C.write_state(a.stage, "running")
    if a.stage == "full":
        picture(ff, a, budget, redraw)
    return deliver(ff, budget, a.stage, target)


# required: Windows runs the top of this file again in every render worker, never this block
if __name__ == "__main__":
    # a registered string may hold characters a redirected console cannot encode; show them escaped, never crash
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")
    sys.exit(main())
