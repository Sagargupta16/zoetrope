# qa_audiostrip.py : review/audio.png, a picture of the sound for a reviewer who cannot hear (Z20).
# CLI: `python qa.py audiostrip out.mp4 --scenes . [--out review/audio.png]`; a mix.wav works too (proof stage).
# Lanes on one time axis, top to bottom: the scenes, a log-frequency spectrogram, the CUES ticks coloured by their
# measured offset, momentary and short-term loudness with the integrated line, the true peak per 100 ms with every
# frame over -1 dBTP in red, and the proof key sheet's numbered cells.
import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path

import contract as C
import numpy as np
from PIL import Image, ImageDraw, ImageFont

WIDTH = 1600  # never over 2000 (the reviewer's limit); about 1600 x 640 is read without a resize
LEFT, RIGHT = 84, 16  # margins: lane names and frequency labels on the left
SR = 48000
F0, F1, NFFT = 30.0, 16000.0, 4096
LUFS_LO, LUFS_HI, TP_LO, TP_MAX = -45.0, -5.0, -30.0, -1.0
BG, PANEL, GRID = (17, 17, 20), (27, 27, 32), (60, 60, 68)
TEXT, DIM = (228, 228, 232), (150, 150, 160)
GREEN, AMBER, RED, GREY = (60, 205, 95), (245, 170, 40), (240, 64, 52), (128, 128, 138)
M_COL, S_COL, I_COL = (90, 190, 255), (255, 160, 70), (245, 245, 245)
# magma-like ramp: anchors read off the published magma map at every eighth, linearly interpolated
MAGMA = [
    (0, 0, 4),
    (28, 16, 68),
    (79, 18, 123),
    (129, 37, 129),
    (181, 54, 122),
    (229, 80, 100),
    (251, 135, 97),
    (254, 194, 135),
    (252, 253, 191),
]
# one ebur128 line per 100 ms; FTPK has one value per channel (probed on ffmpeg 9.0.2, 2026-10-28)
FRAME = re.compile(
    r"t:\s*(?P<t>[\d.]+)\s+TARGET:.*?M:\s*(?P<M>\S+)\s+S:\s*(?P<S>\S+)\s+I:\s*(?P<I>\S+) LUFS"
    r"(?:.*?FTPK:(?P<ftpk>[^d]*)dBFS)?"
)


def _num(s):
    try:
        return float(s)
    except ValueError:
        return float("nan")


def ebur128(path, ff=None):
    """One ebur128=peak=true pass over the audio: the Summary (I, LRA and true peak, read as qa.loud reads them) and
    every 100 ms line as {t, M, S, I, ftpk}. Each line closes the 100 ms frame ending at t; FTPK is that frame's
    true peak (the max over channels here). metadata=1 carries only the running peak, so the text log is parsed."""
    ff = ff or C.find_ffmpeg() or "ffmpeg"
    err = subprocess.run(
        [ff, "-hide_banner", "-nostdin", "-i", str(path), "-vn"]
        + ["-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True,
        text=True,
        errors="replace",
        check=False,  # a failed decode leaves no Summary, which run() reports
    ).stderr
    frames = []
    for m in FRAME.finditer(err):
        tp = [v for v in map(_num, (m["ftpk"] or "").split()) if not math.isnan(v)]
        frames.append(
            {
                "t": float(m["t"]),
                "M": _num(m["M"]),
                "S": _num(m["S"]),
                "I": _num(m["I"]),
                "ftpk": max(tp) if tp else None,
            }
        )
    s = err[err.rfind("Summary:") :]

    def num(pat):
        m = re.search(pat, s)
        return _num(m.group(1)) if m else None

    return {
        "I": num(r"I:\s+(-?[\d.]+) LUFS"),
        "LRA": num(r"LRA:\s+(-?[\d.]+) LU"),
        "peak": num(r"Peak:\s+(-?[\d.]+|-inf) dBFS"),
        "frames": frames,
    }


def logspec(a, sr, cols, rows, dur):
    """(rows, cols) power in dB, row 0 the lowest band: one Hann-windowed NFFT frame centred on each pixel column's
    time, binned onto rows spaced evenly in log frequency from F0 to F1 (a two-bin interpolation where a row is
    narrower than one FFT bin, the mean of its bins above that)."""
    edges = F0 * (F1 / F0) ** (np.arange(rows + 1) / rows)
    df = sr / NFFT
    band = np.zeros((rows, NFFT // 2 + 1), np.float32)
    for r in range(rows):
        lo, hi = edges[r] / df, edges[r + 1] / df
        if hi - lo < 1:
            c = np.sqrt(lo * hi)
            i = int(c)
            band[r, i], band[r, i + 1] = 1 - (c - i), c - i
        else:
            i0, i1 = int(lo), int(np.ceil(hi))
            band[r, i0:i1] = 1 / (i1 - i0)
    half = NFFT // 2
    total = max(len(a), int(np.ceil(dur * sr)) + 1)
    pad = np.zeros(half + total + half + 1, np.float32)
    pad[half : half + len(a)] = a
    centre = np.round((np.arange(cols) + 0.5) * dur / cols * sr).astype(np.int64)
    win = np.hanning(NFFT).astype(np.float32)
    out = np.empty((rows, cols), np.float32)
    for c0 in range(0, cols, 128):
        idx = centre[c0 : c0 + 128, None] + np.arange(NFFT)[None, :]
        p = np.abs(np.fft.rfft(pad[idx] * win, axis=1)) ** 2
        out[:, c0 : c0 + 128] = band @ p.T.astype(np.float32)
    return 10 * np.log10(out + 1e-20)


def lut(n=256):
    a = np.array(MAGMA, float)
    x = np.linspace(0, len(a) - 1, n)
    i = np.minimum(x.astype(int), len(a) - 2)
    f = (x - i)[:, None]
    return (a[i] * (1 - f) + a[i + 1] * f).round().astype(np.uint8)


def _windows(scenes):
    """[(t0, t1)] of scenes.WINDOWS (transition overlaps): a list of pairs, of dicts with t0/t1 or start/end, or a
    dict of name to either."""
    w = getattr(scenes, "WINDOWS", None) if scenes is not None else None
    out = []
    try:
        for v in (w.values() if isinstance(w, dict) else w) or []:
            a, b = (
                (v.get("t0", v.get("start")), v.get("t1", v.get("end")))
                if isinstance(v, dict)
                else (v[0], v[1])
            )
            if a is not None and b is not None and float(b) > float(a):
                out.append((float(a), float(b)))
    except (TypeError, ValueError, IndexError, KeyError):
        return []
    return out


def _cues(scenes):
    """(cues, problem): contract.cues of scenes.CUES (every shape it reads, a dict of label to times included), or []
    with the reason when it cannot read them."""
    if scenes is None:
        return [], None
    try:
        return C.cues(scenes), None
    except (TypeError, ValueError, KeyError, IndexError) as e:
        return [], f"CUES not in registry form ({type(e).__name__}: {e})"


def _offsets(ctx):
    """qa_sync.cue_offsets(ctx), or [] with the reason. Any error there is reported in the header, never fatal:
    the strip is still worth having without the sync colours."""
    try:
        import qa_sync

        return list(qa_sync.cue_offsets(ctx) or []), None
    except Exception as e:  # noqa: BLE001 (another module's failure must not lose the picture)
        return [], f"cue_offsets failed ({type(e).__name__}: {e})"


def cue_status(rec, kind, fps):
    """(colour, word) of one cue's audio from its qa_sync.cue_offsets record (status ok, late, early or missing):
    green within 1 frame, amber within 100 ms, red missing or further out, grey when not measured (no record, or a
    picture-only cue)."""
    if rec is None or kind == "picture" or rec.get("source") == "picture":
        return GREY, "not measured"
    ms = rec.get("audio_ms")
    if ms is None:
        return (
            (RED, "missing")
            if rec.get("status") == "missing"
            else (GREY, "not measured")
        )
    if abs(ms) <= 1000 / fps + 1e-6:
        return GREEN, "within 1 frame"
    return (AMBER, "within 100 ms") if abs(ms) <= 100 else (RED, "missing")


def _match(recs, c):
    """The offset record for cue c: same time (1 ms), same label preferred."""
    near = []
    for r in recs:
        try:
            if abs(float(r.get("t")) - c["t"]) <= 1e-3:
                near.append(r)
        except (TypeError, ValueError):
            continue
    return next(
        (r for r in near if r.get("label") == c["label"]), near[0] if near else None
    )


def _vdash(d, x, y0, y1, fill, on=5, off=4):
    for y in range(int(y0), int(y1), on + off):
        d.line([(x, y), (x, min(y1, y + on - 1))], fill=fill)


def _hdash(d, y, x0, x1, fill, on=6, off=5):
    for x in range(int(x0), int(x1), on + off):
        d.line([(x, y), (min(x1, x + on - 1), y)], fill=fill)


def _labels(d, items, y, rows, font, lo, hi, centre=False):
    """Draw (x, text, fill) labels left to right on up to `rows` lines from y; a label that fits no line is dropped
    (its tick still shows). Returns how many were dropped."""
    ends, dropped, lh = [-1e9] * rows, 0, font.size + 3
    for x, text, fill in sorted(items, key=lambda it: it[0]):
        w = d.textlength(text, font=font)
        x0 = min(max((x - w / 2) if centre else x + 3, lo), hi - w)
        for r in range(rows):
            if x0 >= ends[r] + 4:
                d.text((x0, y + r * lh), text, fill=fill, font=font)
                ends[r] = x0 + w
                break
        else:
            dropped += 1
    return dropped


def _key_labels(nums, X, px=6):
    """(x, text, fill) per group of numbered key cells whose ticks sit within px of each other (the frame before a
    cut and the cut itself): one label, '2-3' for a run, '2,5' otherwise."""
    groups = []
    for e in sorted(nums, key=lambda e: float(e["t"])):
        x = X(float(e["t"]))
        if groups and x - groups[-1][1] < px:
            groups[-1][1] = x
            groups[-1][2].append(str(e["n"]))
        else:
            groups.append([x, x, [str(e["n"])]])
    out = []
    for x0, x1, ns in groups:
        run = all(n.isdigit() for n in ns) and int(ns[-1]) - int(ns[0]) == len(ns) - 1
        out.append(
            (
                (x0 + x1) / 2,
                f"{ns[0]}-{ns[-1]}" if run and len(ns) > 1 else ",".join(ns),
                TEXT,
            )
        )
    return out


def _segments(d, xy, parts, font, limit=WIDTH - 8):
    """Draw [(text, fill), ...] one after another from xy; text past `limit` px is cut with '...' (the console line
    carries the whole of it)."""
    x, y = xy
    for text, fill in parts:
        if x + d.textlength(text, font=font) > limit:
            while text and x + d.textlength(text + "...", font=font) > limit:
                text = text[:-1]
            text += "..."
        d.text((x, y), text, fill=fill, font=font)
        x += d.textlength(text, font=font)
    return x


def _polyline(d, pts, fill, width=2):
    """Lines through the points, broken wherever a point is None (a gap in the meter)."""
    run = []
    for p in pts + [None]:
        if p is None:
            if len(run) > 1:
                d.line(run, fill=fill, width=width)
            run = []
        else:
            run.append(p)


def strip(ctx, frames, out=C.AUDIO_PNG):
    """Draw and save the strip for ctx (ctx.loudness set; frames from ebur128). Returns what it measured."""
    dur = float(ctx.probe["duration"])
    P = WIDTH - LEFT - RIGHT
    fps = ctx.fps or 30
    f_small, f_mid, f_big = (ImageFont.load_default(size=s) for s in (12, 13, 15))

    def X(t):
        return LEFT + min(max(t, 0.0), dur) / dur * P

    lanes, y = {}, 70  # two header lines, then the time axis at 50 to 66
    for name, h in (
        ("band", 20),
        ("spec", 220),
        ("cue", 46),
        ("loud", 150),
        ("tp", 50),
        ("keys", 44),
    ):
        lanes[name] = (y, y + h)
        y += h + 5
    H = y + 26
    img = Image.new("RGB", (WIDTH, H), BG)
    d = ImageDraw.Draw(img)
    for name in ("cue", "loud", "tp", "keys"):
        y0, y1 = lanes[name]
        d.rectangle([LEFT, y0, LEFT + P - 1, y1 - 1], fill=PANEL)

    # time axis: about 12 to 16 labelled ticks, grid lines through the meter lanes
    step = next((s for s in (0.5, 1, 2, 5, 10, 15, 30, 60, 120) if dur / s <= 16), 300)
    ticks = [k * step for k in range(int(dur / step) + 1)]
    for t in ticks:
        x = X(t)
        d.line([(x, 60), (x, 67)], fill=DIM)
        d.text((x + 3, 51), f"{t:g} s", fill=DIM, font=f_small)
        for name in ("loud", "tp"):
            d.line([(x, lanes[name][0]), (x, lanes[name][1] - 1)], fill=GRID)

    # scenes band: one shaded block per SCHEDULE entry with its name
    notes = []
    sched = getattr(ctx.scenes, "SCHEDULE", None) if ctx.scenes is not None else None
    y0, y1 = lanes["band"]
    if sched:
        for k, (name, (a, b)) in enumerate(sched.items()):
            x0, x1 = X(a), X(b)
            d.rectangle(
                [x0, y0, max(x0, x1 - 1), y1 - 1],
                fill=(44, 44, 54) if k % 2 else (34, 34, 42),
            )
            label = str(name)
            while label and d.textlength(label, font=f_small) > x1 - x0 - 6:
                label = label[:-1]
            d.text((x0 + 3, y0 + 3), label, fill=TEXT, font=f_small)
    else:
        d.text(
            (LEFT + 4, y0 + 3),
            "no SCHEDULE (pass --scenes): cuts not drawn",
            fill=DIM,
            font=f_small,
        )

    # spectrogram: one column per pixel, log frequency, magma-like ramp over the top 80 dB
    y0, y1 = lanes["spec"]
    a = ctx.audio(SR)
    db = logspec(a, SR, P, y1 - y0, dur)
    top = float(db.max())
    v = np.clip((db - (top - 80)) / 80, 0, 1)
    img.paste(
        Image.fromarray(lut()[(v[::-1] * 255).astype(np.uint8)], "RGB"), (LEFT, y0)
    )
    for f in (50, 100, 200, 500, 1000, 2000, 5000, 10000):
        yy = y1 - np.log(f / F0) / np.log(F1 / F0) * (y1 - y0)
        d.line([(LEFT - 5, yy), (LEFT - 1, yy)], fill=DIM)
        txt = f"{f // 1000}k" if f >= 1000 else str(f)
        d.text(
            (LEFT - 8 - d.textlength(txt, font=f_small), yy - 7),
            txt,
            fill=DIM,
            font=f_small,
        )
    d.text((6, y0 + 2), "Hz", fill=TEXT, font=f_mid)

    # true peak per 100 ms frame; frames over -1 dBTP in red, also marked along the top of the spectrogram
    y0, y1 = lanes["tp"]

    def Ytp(val):
        return y1 - 1 - (min(max(val, TP_LO), 0.0) - TP_LO) / -TP_LO * (y1 - y0 - 2)

    over = [f for f in frames if f["ftpk"] is not None and f["ftpk"] > TP_MAX]
    for f in frames:
        if f["ftpk"] is None or f["ftpk"] <= TP_LO:
            continue
        x0, x1 = X(f["t"] - 0.1), X(f["t"])
        hot = f["ftpk"] > TP_MAX
        d.rectangle(
            [x0, Ytp(f["ftpk"]), max(x0, x1 - 1), y1 - 1],
            fill=RED if hot else (105, 105, 122),
        )
        if hot:
            d.rectangle(
                [x0, lanes["spec"][0], max(x0 + 1, x1 - 1), lanes["spec"][0] + 5],
                fill=RED,
            )
    _hdash(d, Ytp(TP_MAX), LEFT, LEFT + P - 1, RED)
    d.text((6, y0 + 2), "TP", fill=TEXT, font=f_mid)
    d.text((LEFT - 22, Ytp(TP_MAX) - 7), "-1", fill=RED, font=f_small)
    d.text((LEFT - 30, y1 - 15), f"{TP_LO:g}", fill=DIM, font=f_small)
    if not any(f["ftpk"] is not None for f in frames):
        d.text(
            (LEFT + 4, y0 + 4),
            "no FTPK lines in the ebur128 log",
            fill=DIM,
            font=f_small,
        )

    # loudness: momentary (400 ms) and short-term (3 s) at their window centres, integrated as a dashed line
    y0, y1 = lanes["loud"]

    def Y(val):
        return (
            y1
            - 1
            - (min(max(val, LUFS_LO), LUFS_HI) - LUFS_LO)
            / (LUFS_HI - LUFS_LO)
            * (y1 - y0 - 2)
        )

    for g in (-14, -24, -34):
        d.line(
            [(LEFT, Y(g)), (LEFT + P - 1, Y(g))],
            fill=(88, 88, 100) if g == -14 else GRID,
        )
        d.text(
            (LEFT - 30, Y(g) - 7), f"{g}", fill=TEXT if g == -14 else DIM, font=f_small
        )
    d.text((6, y0 + 2), "LUFS", fill=TEXT, font=f_mid)
    for key, lag, col in (("S", 1.5, S_COL), ("M", 0.2, M_COL)):
        _polyline(
            d,
            [
                (X(f["t"] - lag), Y(f[key]))
                if not math.isnan(f[key])
                and f[key] > -70  # -120.7 until a window fills
                else None
                for f in frames
            ],
            col,
        )
    L = ctx.loudness or {}
    if L.get("I") is not None:
        _hdash(d, Y(L["I"]), LEFT, LEFT + P - 1, I_COL)
        d.text(
            (LEFT + P - 70, Y(L["I"]) - 16), f"I {L['I']:.1f}", fill=I_COL, font=f_small
        )

    # cues: one tick per CUES entry, coloured by its measured audio offset
    cues, cue_problem = _cues(ctx.scenes)
    recs, rec_problem = _offsets(ctx) if cues else ([], None)
    y0, y1 = lanes["cue"]
    counts, items = {}, []
    for c in cues:
        col, word = cue_status(_match(recs, c), c["kind"], fps)
        if c["kind"] != "picture":
            counts[word] = counts.get(word, 0) + 1
        x = X(c["t"])
        big = bool(c.get("payoff"))
        d.line([(x, y0), (x, y0 + 18)], fill=col, width=6 if big else 4)
        d.line(
            [(x, lanes["spec"][1] - 14), (x, lanes["spec"][1] - 1)], fill=col, width=1
        )
        label = ("* " if big else "") + (c["label"] or f"{c['t']:.2f}")[:18]
        items.append((x, label, col))
    dropped = _labels(d, items, y0 + 18, 2, f_small, LEFT, LEFT + P)
    d.text((6, y0 + 2), "cues", fill=TEXT, font=f_mid)
    if not cues:
        d.text((LEFT + 4, y0 + 4), cue_problem or "no CUES", fill=DIM, font=f_small)

    # proof key cells: numbered ticks from review_times.json ("n", written by proof.py)
    y0, y1 = lanes["keys"]
    keys = C.read_review_times(Path(ctx.workdir, C.REVIEW_TIMES))
    nums = [e for e in keys if e.get("n") is not None]
    for e in keys:
        x = X(float(e["t"]))
        d.line(
            [(x, y0), (x, y0 + (10 if e.get("n") is not None else 5))],
            fill=TEXT if e.get("n") is not None else DIM,
        )
    _labels(d, _key_labels(nums, X), y0 + 11, 2, f_small, LEFT, LEFT + P, True)
    d.text((6, y0 + 2), "keys", fill=TEXT, font=f_mid)
    if not nums:
        why = (
            "no review_times.json"
            if not keys
            else "review_times.json has no cell numbers"
        )
        d.text((LEFT + 4, y0 + 14), why, fill=DIM, font=f_small)

    # transition windows shaded over every lane, then the scene cuts dashed on top
    shade = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for a0, b0 in _windows(ctx.scenes):
        sd.rectangle(
            [X(a0), lanes["band"][0], X(b0), lanes["keys"][1]], fill=(120, 160, 255, 50)
        )
    img = Image.alpha_composite(img.convert("RGBA"), shade).convert("RGB")
    d = ImageDraw.Draw(img)
    for a0, _ in (sched or {}).values():
        if a0 > 0:
            _vdash(d, X(a0), lanes["band"][0], lanes["keys"][1], (235, 235, 240))

    # header: the file, then loudness, true peak and the sync summary
    written = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(Path(ctx.path).stat().st_mtime)
    )
    size = f"{ctx.w}x{ctx.h}, {fps} fps, " if ctx.w else ""
    about = f"   {dur:.2f} s, {size}audio {ctx.probe.get('acodec')}, written {written}"
    _segments(d, (8, 6), [(Path(ctx.path).name, TEXT), (about, DIM)], f_big)
    n_aud = sum(counts.values())
    if not cues:
        sync = f"sync: {cue_problem or 'no CUES'}"
    elif not recs:
        sync = f"sync: not measured ({rec_problem or 'qa_sync.cue_offsets gave nothing'}), {n_aud} audio cues"
    else:
        sync = (
            "sync: "
            + ", ".join(
                f"{counts[w]} {w}"
                for w in ("within 1 frame", "within 100 ms", "missing", "not measured")
                if counts.get(w)
            )
            + f" (of {n_aud} audio cues)"
        )
    i_ok = L.get("I") is not None and abs(L["I"] + 14) <= 1
    tp_ok = L.get("peak") is not None and L["peak"] <= TP_MAX
    _segments(
        d,
        (8, 26),
        [
            (f"I {L.get('I')} LUFS (want -14 +/- 1)", TEXT if i_ok else AMBER),
            (f"   LRA {L.get('LRA')} LU   ", DIM),
            (
                f"true peak {L.get('peak')} dBTP (want <= -1): {len(over)} of {len(frames)} frames over",
                TEXT if tp_ok and not over else RED,
            ),
            (
                f"   {sync}",
                TEXT if recs and not counts.get("missing") else AMBER if cues else DIM,
            ),
        ],
        f_big,
    )

    # legend
    yl = H - 22
    _segments(
        d,
        (8, yl),
        [
            ("M momentary", M_COL),
            ("  S short-term", S_COL),
            ("  I integrated", I_COL),
            ("  (M, S at window centres)   ", DIM),
            ("TP over -1 dBTP", RED),
            ("   cue audio: ", DIM),
            ("within 1 frame", GREEN),
            ("  within 100 ms", AMBER),
            ("  missing", RED),
            ("  not measured", GREY),
            (
                "   * payoff   dashed: scene cut   shaded: transition   numbers: proof_keys.png cells",
                DIM,
            ),
        ],
        f_small,
    )
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    notes += [cue_problem, rec_problem] + (
        [f"{dropped} cue labels did not fit"] if dropped else []
    )
    return {
        "out": str(out),
        "size": img.size,
        "I": L.get("I"),
        "peak": L.get("peak"),
        "over": len(over),
        "frames": len(frames),
        "cues": counts,
        "sync": sync,
        "notes": [n for n in notes if n],
    }


def _probe_audio(path):
    """qa.probe's fields for a file with no video stream (mix.wav at the proof stage)."""
    j = json.loads(
        subprocess.check_output(
            [
                C.ffprobe_of(C.find_ffmpeg() or "ffmpeg"),
                "-v",
                "error",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ]
        )
    )
    a = [s for s in j["streams"] if s["codec_type"] == "audio"]
    return {
        "duration": float(j["format"]["duration"]),
        "size_mb": int(j["format"]["size"]) / 1e6,
        "w": None,
        "h": None,
        "fps": None,
        "frames": 0,
        "vcodec": None,
        "pix": None,
        "acodec": a[0]["codec_name"] if a else None,
    }


def run(a):
    """qa.py audiostrip: the same Ctx qa.py check builds, one ebur128 pass, the strip. Exit 0 when written, 2 when
    there is no audio to draw (0 for a declared SILENT piece)."""
    import qa  # before the scenes folder joins sys.path: it may hold an older qa.py

    t_start = time.perf_counter()
    try:
        p = qa.probe(a.video)
    except StopIteration:  # no video stream
        p = _probe_audio(a.video)
    rate = None
    if p["fps"]:
        n, dd = (int(x) for x in p["fps"].split("/"))
        rate = n / dd
    scn = None
    if a.scenes:
        sys.path.insert(0, str(Path(a.scenes).resolve()))
        import engine as E

        if p["w"]:
            E.W, E.H = p["w"], p["h"]
        if rate:
            E.FPS = round(rate)
        import scenes as scn

        rate = rate or E.FPS
    ctx = C.Ctx(a.video, p, round(rate or 30), p["w"], p["h"], scn, a.scenes)
    if not p["acodec"]:
        print(f"no audio stream in {a.video}: nothing to draw")
        return 0 if ctx.declared("SILENT") else 2
    L = ebur128(a.video, ctx.ff)
    if L["I"] is None:
        print(f"ebur128 gave no Summary for {a.video}: nothing drawn")
        return 2
    ctx.loudness = {k: L[k] for k in ("I", "LRA", "peak")}
    info = strip(ctx, L["frames"], a.out)
    print(
        f"wrote {info['out']} ({info['size'][0]}x{info['size'][1]}) in {time.perf_counter() - t_start:.1f} s: "
        f"I {info['I']} LUFS, TP {info['peak']} dBTP, {info['over']} of {info['frames']} frames over -1 dBTP; "
        f"{info['sync']}"
    )
    for n in info["notes"]:
        print(f"note: {n}")
    return 0


def add_cli(sub):
    s = sub.add_parser(
        "audiostrip",
        help="review/audio.png: spectrogram, cues, loudness and true peak on one time axis",
    )
    s.add_argument("video", help="the finished video, or mix.wav at the proof stage")
    s.add_argument(
        "--scenes",
        help="folder holding the video's scenes.py (SCHEDULE, WINDOWS, CUES) and review_times.json",
    )
    s.add_argument("--out", default=C.AUDIO_PNG)
    s.set_defaults(func=run)
