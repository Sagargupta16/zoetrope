# scans.py : gate 6 (qa_scan flashes, WCAG 2.2 on the linear-light decode) on short encoded clips, the reviewer's
# pointer scans (Q1101 to Q1104) on synthetic thumbs.npy files, and Q1105 on a file whose encode does not show the
# drawn frames. The two flash fixtures the old gate could not fail (a 3.4 Hz triangle with every step under 20/255,
# an equal-luminance red and green strobe) must fail here. Lifted from lane F's make_flash.py, fix/regress.py and
# fix/q1105.py (outputs/batchA/notes/f.md).
import types

import contract as C
import numpy as np
import qa
import qa_scan
from PIL import Image, ImageDraw

from qa_fixtures import case, clean, media, want

W, H, FPS = 320, 180, 30


def flat(c):
    return np.broadcast_to(np.array(c, np.uint8), (H, W, 3)).copy()


def tri(i, hz=3.4):
    p = (i / FPS * hz) % 1.0
    return 1 - abs(2 * p - 1)


def local(i):
    a = flat((40, 40, 40))
    if (i // 3) % 2:
        a[20:70, 40:90] = (
            255  # 50 x 50 px: 4.3 percent of the frame, a third of one 10 degree window
        )
    return a


def calm(i):
    x = np.linspace(0, 1, W)[None, :, None]
    v = 60 + 120 * (
        0.5 + 0.5 * np.sin(2 * np.pi * (x + i / FPS / 4))
    )  # a drifting gradient, no flash
    return np.broadcast_to(v, (H, W, 3)).astype(np.uint8)


# name: (seconds, frame i -> uint8 (H, W, 3))
CLIPS = {
    "tri34": (
        4,
        lambda i: flat([round(80 + 80 * tri(i))] * 3),
    ),  # 3.4 Hz, steps under 20/255
    "redgreen5": (
        4,
        lambda i: flat((255, 0, 0) if (i // 3) % 2 else (0, 148, 0)),
    ),  # equal luminance, 5 Hz
    "bw5": (4, lambda i: flat([255 * ((i // 3) % 2)] * 3)),
    "local5": (4, local),
    "ext25": (
        7,
        lambda i: flat([255 * ((i // 6) % 2)] * 3),
    ),  # 2.5 Hz for 7 s: the extended band
    "darkflicker": (
        4,
        lambda i: flat([10 if (i // 3) % 2 else 45] * 3),
    ),  # 0.003 to 0.026 linear: no flash
    "dipblack": (
        4,
        lambda i: flat([150 - 25 * (6 - min(abs(i - 36), 6))] * 3),
    ),  # one dip: 1 flash
    "calm": (4, calm),
}


def flash(name):
    """The clip encoded as run_all encodes (BT.709 tagged), then qa_scan.check_rows on the Ctx qa.check builds."""

    def go(fx):
        secs, fn = CLIPS[name]
        frames = np.stack([fn(i) for i in range(secs * FPS)])
        path = media.encode(fx.ff, fx.tmp / f"{name}.mp4", frames, FPS)
        p = qa.probe(str(path), fx.ff)
        return qa_scan.check_rows(
            C.Ctx(path, p, FPS, p["w"], p["h"], None, fx.tmp, ff=fx.ff)
        )

    return go


# ---- Q1101 to Q1104 on thumbs.npy (192x108 grey, what run_all's scan_thumbs reads) ----


def clip(n=90):
    """Mid grey with a small mover, so every step changes a little (as a lane F regression input)."""
    g = np.full((n, 108, 192), 60, np.uint8)
    for i in range(n):
        g[i, 10:20, (2 * i) % 170 : (2 * i) % 170 + 20] = 200
    return g


def thumbs(make, **scn):
    """scan_thumbs on fx.tmp/thumbs.npy holding make(), with frames.hash for the fps and a scenes stand-in."""

    def go(fx):
        g = make()
        np.save(fx.tmp / C.THUMBS, g)
        C.write_frame_manifest(["0"] * len(g), 192, 108, FPS, fx.tmp)
        sc = types.SimpleNamespace(**{"SCHEDULE": {"x": (0, len(g) / FPS)}, **scn})
        return qa_scan.scan_thumbs(fx.tmp, sc)

    return go


def pop():
    g = np.full((60, 108, 192), 30, np.uint8)
    g[30, :, 90:100] = 230  # a bar for exactly one frame: 1.00 s
    return g


def sweep():
    g = np.full((60, 108, 192), 30, np.uint8)
    for k in range(
        6
    ):  # a bar sweeping 35 px a frame: a fast mover, lit at each place for one frame
        g[30 + k, :, 5 + 35 * k : 15 + 35 * k] = 230
    return g


def frozen():
    g = clip(240)
    g[30:150] = g[30]  # 1.00 to 5.00 s held, with no hold declared
    return g


def cut():
    g = clip()
    g[45:] = np.clip(g[45:].astype(int) + 120, 0, 255).astype(
        np.uint8
    )  # a hard cut into frame 45 (1.50 s)
    return g


def flash2():
    g = clip()
    g[45:47] = 255  # a 2-frame white flash: Q601's business, not a cut
    return g


def stall():
    g = np.full((90, 108, 192), 40, np.uint8)
    for i in range(90):  # a bar moving 3 px a frame across the frame
        g[i, :, 10 + 3 * i : 20 + 3 * i] = 210
    g[45] = g[
        44
    ]  # the planted stall: frame 45 (1.50 s) repeats frame 44 inside the motion
    return g


def moving():
    g = stall()
    g[45] = np.full((108, 192), 40, np.uint8)
    g[45, :, 145:155] = 210  # the same motion with no repeat
    return g


# ---- Q1105: the encoded file against the drawn frames ----


def drawn(i, size=(W, H)):
    im = Image.new("RGB", size, (30, 40, 70))
    d = ImageDraw.Draw(im)
    x = 20 + i * 4
    d.rectangle((x, 60, x + 60, 120), fill=(230, 200, 90))
    return im


def match(turned):
    """thumbs.npy from the frames draw() meant; the encode gets frame 20 drawn 180 x 320 when turned (the same byte
    count, so ffmpeg says nothing)."""

    def go(fx):
        frames, th = [], []
        for i in range(60):
            im = drawn(i)
            th.append(C.thumb(im))
            bad = turned and i == 20
            frames.append(np.asarray(drawn(i, (H, W)) if bad else im).reshape(H, W, 3))
        np.save(fx.tmp / C.THUMBS, np.stack(th))
        C.write_frame_manifest(["0"] * 60, W, H, FPS, fx.tmp)
        path = media.encode(fx.ff, fx.tmp / "out.mp4", np.stack(frames), FPS)
        p = qa.probe(str(path), fx.ff)
        return qa_scan.check_rows(
            C.Ctx(path, p, FPS, p["w"], p["h"], None, fx.tmp, ff=fx.ff)
        )

    return go


CASES = [
    case(
        "scans.tri34",
        flash("tri34"),
        [
            want("Q601", "FIX", t=2.0, tol=2.0, metric=3.5, mtol=0.5),
            want("Q602", "PASS"),
        ],
    ),
    case(
        "scans.redgreen5",
        flash("redgreen5"),
        [
            want("Q602", "FIX", t=2.0, tol=2.0, metric=5.0, mtol=0.5),
            want("Q601", "PASS"),
        ],
    ),
    case(
        "scans.bw5",
        flash("bw5"),
        [want("Q601", "FIX", t=2.0, tol=2.0, metric=5.0, mtol=0.5)],
    ),
    case(
        "scans.local5",
        flash("local5"),
        [want("Q601", "FIX", metric=5.0, mtol=0.5, msg="10 degree window")],
    ),
    case(
        "scans.ext25",
        flash("ext25"),
        [
            want("Q603", "NOTE", t=3.5, tol=0.5, metric=6.9, mtol=0.5),
            want("Q601", "PASS"),
        ],
    ),
    case(
        "scans.darkflicker",
        flash("darkflicker"),
        [want("Q601", "PASS"), want("Q602", "PASS")],
    ),
    case("scans.dipblack", flash("dipblack"), [want("Q601", "PASS")]),
    case(
        "scans.calm",
        flash("calm"),
        [clean(), want("Q601", "PASS"), want("Q602", "PASS"), want("Q603", "PASS")],
    ),
    case("scans.pop", thumbs(pop), [want("Q1101", "NOTE", "x", 1.0, tol=0.001)]),
    case("scans.sweep", thumbs(sweep), [want("Q1101", "PASS")]),
    case(
        "scans.frozen",
        thumbs(frozen),
        [want("Q1102", "NOTE", "x", 3.0, tol=0.1, metric=4.0, mtol=0.1)],
    ),
    case(
        "scans.frozen_held",
        thumbs(frozen, HOLDS=[("Average speed", 1.0, 5.0)]),
        [want("Q1102", "PASS")],
    ),
    case(
        "scans.cut",
        thumbs(cut, CUES=[(1.43, "hit", "both")]),
        [want("Q1103", "NOTE", "x", 1.5, tol=0.001, metric=119, mtol=6)],
    ),
    case(
        "scans.cut_late_cue",
        thumbs(cut, CUES=[(1.43, "hit", "both")], CUE_LAG=2),
        [want("Q1103", "PASS")],
    ),
    case("scans.flash_not_cut", thumbs(flash2), [want("Q1103", "PASS")]),
    case("scans.stall", thumbs(stall), [want("Q1104", "NOTE", "x", 1.5, tol=0.001)]),
    case("scans.moving", thumbs(moving), [clean(), want("Q1104", "PASS")]),
    case(
        "scans.match_turned",
        match(True),
        [want("Q1105", "FIX", t=0.667, tol=0.001, metric=19, mtol=8)],
    ),
    case(
        "scans.match_clean", match(False), [want("Q1105", "PASS", metric=0.1, mtol=0.5)]
    ),
]
