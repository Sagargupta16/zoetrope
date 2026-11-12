# registry.py : the text recorder (qa_registry.rows, Q204 to Q209) on tiny scenes files at 640x360, no video: text
# drawn but not reported, a registry box 6 px off, a covered caption, text that never goes through ImageDraw.text,
# a stale registry, and a drop-shadow card that must pass. Lifted from lane T's faults/ (outputs/batchA/notes/t.md).
import qa_registry

from qa_fixtures import case, clean, want
from qa_fixtures.fake import scenes_file

W, H, FPS = 640, 360, 30


def rows(name):
    def go(fx):
        mod = scenes_file(name, W, H, FPS)
        return qa_registry.rows(mod, W, H, FPS, {"registry_procs": 1})

    return go


CASES = [
    case(
        "registry.missing",
        rows("reg_missing.py"),
        [want("Q204", "FIX", "Missing caption", 0.967, tol=0.1, n=1)],
        files=["reg_missing.py"],
    ),
    case(
        "registry.box",
        rows("reg_box.py"),
        [
            want(
                "Q205",
                "FIX",
                "Registered title",
                0.0,
                tol=0.01,
                metric=6.0,
                mtol=0.5,
                n=1,
            )
        ],
        files=["reg_box.py"],
    ),
    case(
        "registry.cover",
        rows("reg_cover.py"),
        [
            want(
                "Q206",
                "FIX",
                "Covered caption",
                1.0,
                tol=0.5,
                metric=0.4,
                mtol=0.1,
                n=1,
            )
        ],
        files=["reg_cover.py"],
    ),
    case(
        "registry.paste",
        rows("reg_paste.py"),
        [want("Q208", "NOT CHECKED")],
        files=["reg_paste.py"],
    ),
    case(
        "registry.stale",
        rows("reg_stale.py"),
        [want("Q209", "NOTE", "Stale caption", 1.233, tol=0.1)],
        files=["reg_stale.py"],
    ),
    case(
        "registry.shadow",
        rows("reg_shadow.py"),
        [
            clean(),
            want("Q204", "PASS"),
            want("Q205", "PASS"),
            want("Q206", "PASS"),
            want("Q208", "PASS"),
            want("Q209", "PASS"),
        ],
        files=["reg_shadow.py"],
    ),
]
