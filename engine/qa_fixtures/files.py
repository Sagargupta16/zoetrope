# files.py : the gates qa.check runs on the file itself, on short synthetic MP4s made in the case's temp folder: a
# clean 2 s card at -14 LUFS that every gate must pass; a bad encode (25 fps, yuv444p, untagged, no audio, black
# first and last frames, wrong duration and size asked for, the colour chain swapped for one that is 40 levels off);
# a quiet file whose audio outlasts its picture with a silent second inside; the clean file cut short, whose last
# second does not decode; a lossless noise file over its size cap and bitrate, checked while one gate module raises.
# Lifted from lane Q's filecase and p_colour (notes/q.md).
from pathlib import Path

import contract as C
import numpy as np
import qa
import qa_stack

from qa_fixtures import case, clean, media, want

W, H = 320, 180


def good(fx):
    v = media.encode(fx.ff, fx.tmp / "video.mp4", media.card(60, H, W), 30)
    # a 1 kHz stereo tone at -14 dBFS peak reads -14.0 LUFS on this ffmpeg (EBU Tech 3341 case 1, scaled)
    a = media.wav(fx.tmp / "mix.wav", media.tone(1000, 2.0, 10 ** (-14 / 20)))
    out = media.mux(fx.ff, v, a, fx.tmp / "good.mp4")
    return qa.check(str(out), duration=2.0, fps=30, size=f"{W}x{H}", max_mb=5, ff=fx.ff)


def bad(fx):
    frames = media.card(50, H, W)
    frames[0] = 0  # Q501: the first frame black and flat
    frames[-1] = (
        0  # Q502: the last frame black; Q503: the second before it is the bright card
    )
    v = media.encode(fx.ff, fx.tmp / "bad.mp4", frames, 25, tagged=False, pix="yuv444p")
    old = C.COLOR_VF
    # Q708: the chain writes the BT.601 matrix under BT.709 tags (lane Q's planted chain: 40 levels off on green)
    C.COLOR_VF = (
        "scale=out_color_matrix=bt601:out_range=tv,format=yuv420p,"
        "setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv"
    )
    try:
        return qa.check(str(v), duration=4.0, fps=30, size="640x360", ff=fx.ff)
    finally:
        C.COLOR_VF = old


def quiet(fx):
    v = media.encode(
        fx.ff, fx.tmp / "video.mp4", media.card(105, H, W), 30
    )  # 3.5 s of picture
    x = media.tone(1000, 4.0, 10 ** (-30 / 20))  # 4 s of audio at about -30 LUFS
    x[48000:96000] = 0  # Q803: second 1 to 2 silent
    a = media.wav(fx.tmp / "mix.wav", x)
    out = media.mux(
        fx.ff, v, a, fx.tmp / "quiet.mp4", shortest=False
    )  # Q704: 105 frames in a 4 s file
    return qa.check(str(out), fps=30, size=f"{W}x{H}", ff=fx.ff)


def cut(fx):
    v = media.encode(fx.ff, fx.tmp / "video.mp4", media.card(60, H, W), 30)
    a = media.wav(fx.tmp / "mix.wav", media.tone(1000, 2.0, 10 ** (-14 / 20)))
    whole = Path(media.mux(fx.ff, v, a, fx.tmp / "whole.mp4")).read_bytes()
    # the moov box is in front (+faststart), so ffprobe still counts every frame; the last second is gone (the last
    # frame stops decoding at a 50 percent cut on ffmpeg 9.0.2, 2026-11-01; 35 keeps a margin)
    part = fx.tmp / "cut.mp4"
    part.write_bytes(whole[: len(whole) * 35 // 100])
    return qa.check(str(part), duration=2.0, fps=30, size=f"{W}x{H}", ff=fx.ff)


def noise(fx):
    frames = np.random.default_rng(7).integers(0, 256, (30, H, W, 3), dtype=np.uint8)
    v = media.encode(
        fx.ff, fx.tmp / "noise.mp4", frames, 30, crf=0
    )  # lossless noise: about 20 Mb/s

    def boom(ctx):
        raise ZeroDivisionError("planted: a gate module that raises")

    real, qa_stack.check_rows = (
        qa_stack.check_rows,
        boom,
    )  # Q100: its gates must become one NOT CHECKED row
    try:
        return qa.check(str(v), max_mb=1.0, silent=True, ff=fx.ff)
    finally:
        qa_stack.check_rows = real


CASES = [
    case(
        "files.good",
        good,
        [
            clean(),
            want("Q501", "PASS"),
            want("Q502", "PASS"),
            want("Q503", "PASS"),
            want("Q701", "PASS"),
            want("Q702", "PASS"),
            want("Q703", "PASS"),
            want("Q704", "PASS"),
            want("Q705", "PASS"),
            want("Q706", "PASS"),
            want("Q707", "PASS"),
            want("Q708", "PASS", metric=0, mtol=2),
            want("Q801", "PASS", metric=-14.0, mtol=0.3),
            want("Q802", "PASS", metric=-14.0, mtol=0.3),
            want("Q1001", "PASS"),
            want("Q1002", "PASS"),
            want("Q1101", "PASS"),
            want("Q1104", "PASS"),
            want("Q601", "PASS"),
            want("Q903", "PASS", msg="against mix.wav", metric=0.0, mtol=0.2),
        ],
    ),
    case(
        "files.bad",
        bad,
        [
            want("Q501", "FIX", t=0.0, metric=0.0, mtol=3),
            want("Q502", "FIX", t=1.96, tol=0.01, metric=0.0, mtol=3),
            want("Q503", "NOTE", t=1.96, tol=0.01, metric=100, mtol=40),
            want("Q701", "FIX", metric=2.0, mtol=0.05),
            want("Q702", "FIX", metric=25, mtol=0.01),
            want("Q703", "FIX", msg="size 320x180 (want 640x360)"),
            want("Q705", "FIX", msg="yuv444p"),
            want("Q706", "FIX", msg="audio stream None"),
            want("Q707", "FIX", "unknown / unknown / unknown / unknown"),
            want("Q708", "FIX", "(0, 255, 0)", metric=40, mtol=15),
        ],
    ),
    case(
        "files.quiet",
        quiet,
        [
            want("Q704", "FIX", metric=105, mtol=0.5),
            want("Q801", "FIX", metric=-30.0, mtol=1.0),
            want("Q803", "NOTE", "1-2 s", 1.5, tol=0.01),
        ],
    ),
    case(
        "files.cut",
        cut,
        [
            want("Q501", "PASS"),
            want("Q502", "NOT CHECKED", msg="last frame did not decode"),
            want("Q503", "NOT CHECKED"),
        ],
    ),
    case(
        "files.noise",
        noise,
        [
            want("Q100", "NOT CHECKED", "qa_stack", msg="ZeroDivisionError"),
            want("Q1001", "FIX", "--max-mb", metric=2.6, mtol=1.0),
            want("Q1002", "NOTE", metric=21, mtol=7),
        ],
    ),
]
