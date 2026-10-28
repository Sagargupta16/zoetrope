# source.py : the source gates on scenes files copied into a temp build folder with the engine beside them: purity
# (qa_purity.run, Q1201: one frame drawn from the process id) and the lint (qa_lint.run, Q1202 to Q1206, Q904,
# Q905, one planted fault each). Lifted from lane P's faults/ (outputs/batchA/notes/p.md).
import shutil
from pathlib import Path

import qa_lint
import qa_purity

from qa_fixtures import case, want

HERE = Path(__file__).resolve().parent


def folder(fx, name):
    """fx.tmp as a build folder: every engine file, and the fixture as scenes.py."""
    for p in fx.engine.glob("*.py"):
        shutil.copy2(p, fx.tmp / p.name)
    shutil.copy2(HERE / name, fx.tmp / "scenes.py")
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


L = "lint_faults.py"
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
]
