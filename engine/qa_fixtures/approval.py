# approval.py : the approval gates (qa_approve, Q1301 to Q1304) on a tiny build: appr_piece.py rendered once by
# run_all.py full at 320x180 and approved with a reviewer reply, then copied per case and changed: scene b's colour
# (a stale approval, an undeclared change, an --expect window that saw nothing, a declared change), the build's SS
# (the frame size moved) and the Pillow version in the approval (the environment moved, no frame did). Q1302 runs on
# a planted baseline, no build. Lifted from lane H's lane_h_tests.sh and fix_unit.py (outputs/batchA/notes/h.md).
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import contract as C
import qa
import qa_approve

from qa_fixtures import case, want

HERE = Path(__file__).resolve().parent
SIZE = "320x180"


def _build(fx):
    """The approved build, made once a selftest run: the engine, appr_piece.py as scenes.py, run_all.py full, and
    qa.py approve with a REVIEW PASS reply that names the file and its written time."""

    def make(folder):
        for p in fx.engine.glob("*.py"):
            shutil.copy2(p, folder / p.name)
        shutil.copy2(HERE / "appr_piece.py", folder / "scenes.py")
        r = subprocess.run(
            [sys.executable, "run_all.py", "full", "--size", SIZE],
            cwd=folder,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            check=False,
        )
        (folder / "full.log").write_text(r.stdout + r.stderr, encoding="utf-8")
        if r.returncode or "DELIVERED " not in r.stdout:
            tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
            raise RuntimeError(
                f"run_all.py full did not deliver the build (exit {r.returncode}): {' | '.join(tail)}"
            )
        written = time.strftime(
            qa_approve.STAMP, time.localtime((folder / "out.mp4").stat().st_mtime)
        )
        review = folder / "review.txt"
        review.write_text(
            f"REVIEW PASS\nstage: final | file: out.mp4 (written {written})\nreviewer: qa.py selftest\n"
            "frames seen: 0.50, 1.00, 1.50 s\n",
            encoding="utf-8",
        )
        rc = qa_approve.approve(folder, review=review, procs=2)
        if rc:
            raise RuntimeError(f"qa.py approve refused the build (exit {rc})")
        return folder

    src = fx.shared("approval", make)
    dst = fx.tmp / "build"
    shutil.copytree(src, dst)  # copy2 keeps the written times the approval is bound to
    return dst


def recolour(folder):
    """The planted source change: scene b's colour."""
    p = folder / "scenes.py"
    p.write_text(
        p.read_text(encoding="utf-8").replace('"#D09070"', '"#70D090"'),
        encoding="utf-8",
    )


def check(folder):
    """The approval rows qa.py check adds for the build's out.mp4."""
    out = folder / "out.mp4"
    p = qa.probe(str(out))
    return qa_approve.check_rows(C.Ctx(out, p, 30, p["w"], p["h"], None, folder))


def current(fx):
    return check(_build(fx))


def stale(fx):
    b = _build(fx)
    recolour(b)
    return check(b)


def diffed(expect):
    def go(fx):
        b = _build(fx)
        recolour(b)
        return qa_approve.diff(b, expect, procs=2)

    return go


def resized(fx):
    """The build now runs at SS 2 (build.json): the approved frames cannot be compared."""
    b = _build(fx)
    j = json.loads((b / C.BUILD).read_text(encoding="utf-8"))
    (b / C.BUILD).write_text(json.dumps({**j, "ss": 2}), encoding="utf-8")
    return check(b)


def new_pillow(fx):
    """The approval says another Pillow; every key frame still redraws the same, so the approval stands (NOTE)."""
    b = _build(fx)
    p = b / C.APPROVED / C.APPROVAL
    a = json.loads(p.read_text(encoding="utf-8"))
    a["env"]["pillow"] = "12.9.9"
    p.write_text(json.dumps(a, indent=1), encoding="utf-8")
    return check(b)


def baseline(regress):
    """Q1302 on rows handed in ctx.rows against a baseline qa.json where Q201 and Q501 passed."""

    def go(fx):
        base = fx.tmp / "baseline.json"
        C.write_rows(
            [C.row(True, "Q201", "inside", ""), C.row(True, "Q501", "lit", "")], base
        )
        q201 = C.row(
            not regress,
            "Q201",
            "'Call' 8 px outside",
            "move it",
            item="Call",
            worst_t=2.0,
        )
        ctx = C.Ctx(
            fx.tmp / "none.mp4",
            {},
            30,
            320,
            180,
            None,
            fx.tmp,
            opts={"baseline": str(base)},
        )
        ctx.rows = [q201, C.row(True, "Q501", "lit", "")]
        return qa_approve.baseline_rows(ctx)

    return go


CASES = [
    case(
        "approval.current",
        current,
        [
            want("Q1301", "PASS", msg="approval current"),
            want("Q1304", "PASS", msg="environment as approved"),
        ],
        files=["appr_piece.py"],
    ),
    case(
        "approval.stale",
        stale,
        [
            want(
                "Q1301",
                "FIX",
                "b",
                1.0,
                tol=0.01,
                metric=1,
                mtol=0.01,
                msg="STALE APPROVAL",
            )
        ],
        files=["appr_piece.py"],
    ),
    case(
        "approval.diff_undeclared",
        diffed(()),
        [
            want(
                "Q1303",
                "FIX",
                "b",
                1.0,
                tol=0.01,
                metric=30,
                mtol=0.5,
                msg="undeclared change",
            )
        ],
        files=["appr_piece.py"],
    ),
    case(
        "approval.diff_unmet",
        diffed([(0.0, 1.0)]),
        [want("Q1303", "FIX", "--expect 0-1", msg="declared change not found")],
        files=["appr_piece.py"],
    ),
    case(
        "approval.diff_declared",
        diffed([(1.0, 2.0)]),
        [
            want(
                "Q1303",
                "NOTE",
                "b",
                1.0,
                tol=0.01,
                metric=30,
                mtol=0.5,
                msg="declared change",
            )
        ],
        files=["appr_piece.py"],
    ),
    case(
        "approval.resized",
        resized,
        [want("Q1304", "NOT CHECKED", "SS 1 -> 2")],
        files=["appr_piece.py"],
    ),
    case(
        "approval.new_pillow",
        new_pillow,
        [want("Q1304", "NOTE", msg="12.9.9"), want("Q1301", "PASS")],
        files=["appr_piece.py"],
    ),
    case(
        "approval.baseline_regress",
        baseline(True),
        [want("Q1302", "FIX", "Q201", 2.0, tol=0.001)],
    ),
    case("approval.baseline_same", baseline(False), [want("Q1302", "PASS")]),
]
