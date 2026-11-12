# run_all.py : proof -> picture -> audio -> master -> mux -> QA. Run in stages: proof first, wait for approval, then
# the rest. Every stage takes --size WxH, --fps N and --ss N, read before scenes is imported (a 9:16 run needs no edit).
#   python run_all.py proof          proof gates, proof.png, proof_keys.png, review_times.json and qa_proof.json
#   python run_all.py full [procs]   every frame piped into video.mp4, then audio, master, mux and every QA gate
#   python run_all.py audio          audio, master, mux and QA again on the same video.mp4: no frame is redrawn
# full also takes --budget-mb N (a bitrate cap from a size budget), --keep-frames (frames/ kept as PNG) and, with
# --keep-frames, --redraw T0-T1[,T0-T1] (draw only those passages again, read the rest back from frames/).
# full and audio end with an APPROVAL line and exactly one DELIVERED line, or move the file aside and say why:
# <name>.rejected.mp4 when a row is FIX or NOT CHECKED, <name>.unchecked.mp4 when the run broke before a verdict.
import argparse
import ast
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import contract as C

import engine as E

# the defaults; --size, --fps and --ss replace them before scenes is imported
E.W, E.H, E.FPS, E.SS = 1920, 1080, 30, 1


def size_flags(argv):
    """--size, --fps and --ss, read here and not in main(): scenes reads E.W, E.H, E.FPS and E.SS when it is
    imported, and every render worker runs the top of this file again with the same argv."""
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


size_flags(sys.argv[1:])
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

import audio
import proof
import qa
import render
import scenes

OUT = "out.mp4"  # rename per video: {slug}_{aspect}_{length}s_v{n}.mp4
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
    """The proof gates on drawn frames (qa.proof_rows, purity, lint) first, so the key sheet can show the moments
    they name, then proof.png and proof_keys.png. Exit 1 on any FIX, else 2 on any NOT CHECKED."""
    import qa_lint
    import qa_purity

    C.write_state("proof", "running")
    rows = (
        qa.proof_rows(scenes, E.W, E.H, E.FPS)
        + qa_purity.run(".", E.FPS, (E.W, E.H))
        + qa_lint.run("scenes.py")
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


def picture(ff, a, budget):
    """Every frame drawn and piped into video.mp4, the silent picture (capped when a size budget is set)."""
    maxrate = bufsize = None
    if budget:
        maxrate, bufsize = caps(budget, scenes.DURATION, C.declared(scenes, "SILENT"))
        print(
            f"size budget {budget:g} MB for {scenes.DURATION:g} s: maxrate {maxrate:.0f} kb/s, "
            f"bufsize {bufsize:.0f} kb/s (a cap, not a guarantee: Q1001 checks the file)"
        )
    redraw = (
        [tuple(float(v) for v in s.split("-")) for s in a.redraw.split(",")]
        if a.redraw
        else None
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


def master_and_mux(ff):
    """Master, mux, then measure the true peak of the decoded mp4, which the AAC encode raises. While it is over the
    aim (-1 dBTP less the 0.3 dB meter tolerance), master and mux again at most 3 times: new ceiling = min(ceiling,
    the mix's own true peak) - (excess + margin) / slope, where slope is how far the file's peak really moved per dB
    of ceiling over the last two tries (1 at first; measured 0.69 on one mix). Lowering a ceiling the limiter never
    reached changes nothing (Z03), so a peak that does not follow the ceiling stops the loop. Then the kept master:
    the clean one (Q805 clean, file inside -1 dBTP) with the lowest peak, else the try with the lowest peak and the
    gentlest ceiling; it is mastered and muxed again if it is not the last. A lower ceiling makes the limiter work
    harder, so this keeps a file that passed from becoming a reject. One line per master, for the delivery report.
    Returns (the kept master's rows, the file's loudness)."""
    aim, ceiling, tries = TP_MAX - TP_TOL, audio.CEILING, []
    for k in range(RETRIES + 1):
        m = audio.master(C.MIX_RAW, C.MIX, ff, TP=ceiling)
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
        m = audio.master(C.MIX_RAW, C.MIX, ff, TP=ceiling)
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


def deliver(ff, budget, stage="full"):
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
            rows, loud = master_and_mux(ff)
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


def main():
    ap = argparse.ArgumentParser(
        description="build stages for one video, run from its working folder"
    )
    ap.add_argument("stage", choices=("proof", "full", "audio"))
    ap.add_argument(
        "procs",
        nargs="?",
        type=int,
        help="full: render processes (default cores / 4, at most 8)",
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
    a = ap.parse_args()
    if a.redraw and not a.keep_frames:
        ap.error(
            "--redraw needs --keep-frames (and frames/ from an earlier --keep-frames run)"
        )
    asked = (a.size and a.size.lower() != f"{E.W}x{E.H}") or (a.fps and a.fps != E.FPS)
    if asked or (a.ss and a.ss != E.SS):
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
    # the size this build really uses (after scenes.py), for qa.py purity, lint, diff, approve and proof.py keys;
    # here and not at the top, which every render worker runs again
    C.write_build(E.W, E.H, E.FPS, E.SS)
    if a.stage == "proof":
        return proof_stage()
    built = (C.MIX_RAW, C.SFX, C.CUESHEET, C.CUE_SOUNDS, C.MIX, OUT)
    if a.stage == "full":
        built += (C.VIDEO, f"{C.VIDEO}.log", C.FRAMES_HASH, C.THUMBS)
    clean(*built)
    C.write_state(a.stage, "running")
    if a.stage == "full":
        picture(ff, a, budget)
    return deliver(ff, budget, a.stage)


# required: Windows runs the top of this file again in every render worker, never this block
if __name__ == "__main__":
    # a registered string may hold characters a redirected console cannot encode; show them escaped, never crash
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.stderr.reconfigure(errors="backslashreplace")
    sys.exit(main())
