# source.py : the source gates on scenes files copied into a temp build folder with the engine beside them: purity
# (qa_purity.run, Q1201: one frame drawn from the process id) and the lint (qa_lint.run, Q1202 to Q1207, Q904,
# Q905, one planted fault each; Q1207 has its own file of seven faults, each held to its own line and message, and
# one of the patterns it must leave alone, with a palette module beside it). Lifted from lane P's faults/
# (outputs/batchA/notes/p.md).
import shutil
from pathlib import Path

import contract as C
import qa_lint
import qa_purity

from qa_fixtures import case, want

HERE = Path(__file__).resolve().parent


def folder(fx, name, also=()):
    """fx.tmp as a build folder: every engine file, the fixture as scenes.py, and the fixture's own helper modules
    (also) beside it under their names."""
    for p in fx.engine.glob("*.py"):
        shutil.copy2(p, fx.tmp / p.name)
    shutil.copy2(HERE / name, fx.tmp / "scenes.py")
    for extra in also:
        shutil.copy2(HERE / extra, fx.tmp / extra)
    return fx.tmp


def line_of(name, text):
    """scenes.py:<n>, the line of the fixture holding text: the lint must point at the planted line itself."""
    for i, ln in enumerate((HERE / name).read_text(encoding="utf-8").splitlines(), 1):
        if text in ln:
            return f"scenes.py:{i}"
    return f"scenes.py:? ({text!r} not in {name})"


def purity(fx):
    return qa_purity.run(folder(fx, "pure_pid.py"), 30, (320, 180))


def lint(fx):
    return qa_lint.run(folder(fx, "lint_faults.py") / "scenes.py", 30)


def lint_blend(fx):
    """The lint's rows, then one row for each Q1207 site, as `qa.py lint --all` lists them: the Q1207 row names only
    its first five, and every planted line is held to its own line and message. With n, the count also proves that
    no other line of the fixture is flagged."""
    path = folder(fx, B) / "scenes.py"
    sites = [
        C.row(
            False,
            "Q1207",
            f"{d['file']}:{d['line']} {d['text']} ({d['msg']})",
            qa_lint.FIXES["Q1207"],
            item=f"{d['file']}:{d['line']} {d['text']}",
            considered=1,
        )
        for d in qa_lint.findings(path)[0]
        if d["code"] == "Q1207"
    ]
    return qa_lint.run(path, 30) + sites


def lint_blend_ok(fx):
    return qa_lint.run(folder(fx, OK, also=[LOOK]) / "scenes.py", 30)


L = "lint_faults.py"
B = "lint_blend.py"
OK = "lint_blend_ok.py"
LOOK = "lint_blend_look.py"
CASES = [
    case(
        "source.purity_pid",
        purity,
        [want("Q1201", "FIX", "b", 1.0, tol=0.01, metric=16261, mtol=200)],
        files=["pure_pid.py"],
    ),
    case(
        "source.lint_faults",
        lint,
        [
            want("Q1202", "FIX", f"{line_of(L, 'random.random()')} random.random()"),
            want("Q1203", "NOTE", line_of(L, "COUNT[0] += 1")),
            want("Q1204", "NOTE", f"{line_of(L, 'def text(')} def text"),
            want("Q1205", "NOTE", line_of(L, "ImageDraw.Draw(img).text(")),
            want("Q1206", "NOTE", line_of(L, "fill=(200, 40, 40)")),
            want("Q904", "NOTE", "cue hit", 1.0133, tol=0.001, metric=0.4, mtol=0.01),
            want("Q905", "NOTE", "128 BPM", metric=14.0625, mtol=0.001),
        ],
        files=[L],
    ),
    case(
        "source.lint_blend",
        lint_blend,
        [
            # the row itself: its first site, the count, and 1 + 7 rows, so nothing else in the file is flagged
            want(
                "Q1207",
                "FIX",
                f'{line_of(B, "return ImageDraw.Draw(img, ")} ImageDraw.Draw(img, "RGBA")',
                msg="7 found",
                n=8,
            ),
            # the pen helper names the call that hands it the RGBA picture
            want(
                "Q1207",
                "FIX",
                line_of(B, "return ImageDraw.Draw(img, "),
                msg=f"(img is RGBA when called at {line_of(B, 'pen(img).line(')})",
            ),
            # a scene function reached through the scene table
            want(
                "Q1207",
                "FIX",
                f'{line_of(B, "d = ImageDraw.Draw(img, ")} ImageDraw.Draw(img, "RGBA")',
                msg=f"(img is RGBA when called at {line_of(B, 'SCENES[')})",
            ),
            want(
                "Q1207",
                "FIX",
                f"{line_of(B, 'fill=SHADE')} d.rectangle(",
                msg="straight onto an RGBA picture",
            ),
            want(
                "Q1207",
                "FIX",
                f"{line_of(B, 'fill=GLASS')} d.rectangle(",
                msg="straight onto an RGBA picture",
            ),
            want(
                "Q1207",
                "FIX",
                f"{line_of(B, 'plain_pen(img).ellipse(')} plain_pen(img).ellipse(",
                msg="straight onto an RGBA picture",
            ),
            want(
                "Q1207",
                "FIX",
                f"{line_of(B, 'ImageDraw.Draw(flat).ellipse(')} ImageDraw.Draw(flat).ellipse(",
                msg="plain ImageDraw on an RGB picture",
            ),
            want(
                "Q1207",
                "FIX",
                f"{line_of(B, 'soft.text(')} soft.text(",
                msg="never blends text",
            ),
        ],
        files=[B],
    ),
    case(
        "source.lint_blend_ok",
        lint_blend_ok,
        [want("Q1207", "PASS")],
        files=[OK, LOOK],
    ),
]
