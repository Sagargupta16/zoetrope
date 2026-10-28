# qa.py : the gates in references/qa-gates.md as functions. Each returns numbers; print a pass/fail table from them.
# CLI: `python qa.py check out.mp4 --scenes . --size 1920x1080` prints coded findings and exits 1 on any FIX;
#      `python qa.py look out.mp4` writes small frame copies plus review/look.jpg for a model to view.
import importlib
import json
import math
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path

import contract as C
import numpy as np
from PIL import Image, ImageDraw


def contact_sheet(draw, SCHEDULE, fps=30, cols=4, w=480):
    """Every scene boundary (one frame before and after the cut) and midpoint, labelled with its time (gate 1)."""
    ts = []
    for s, e in SCHEDULE.values():  # scene start/end in seconds
        ts += [max(0, s - 1 / fps), s + 1 / fps, (s + e) / 2]
    ts = sorted(set(round(t, 3) for t in ts))
    thumbs = []
    for t in ts:
        im = draw(t).convert("RGB")
        im = im.resize((w, int(w * im.height / im.width)))
        ImageDraw.Draw(im).text((6, 6), f"{t:.2f}s", fill=(255, 0, 0))
        thumbs.append(im)
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * thumbs[0].height), (30, 30, 30))
    for i, im in enumerate(thumbs):
        sheet.paste(im, ((i % cols) * w, (i // cols) * im.height))
    return sheet


def text_box(font, text, xy):
    """(l, t, r, b) of text at its final font size (gate 2)."""
    return ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox(xy, text, font=font)


def inside(b, W, H, m=0.04):
    """Box inside the safe area: 4 percent edge pad, the safe area in playbook.md (gate 2)."""
    return (
        b[0] >= W * m and b[1] >= H * m and b[2] <= W * (1 - m) and b[3] <= H * (1 - m)
    )


def overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def lum(rgb):
    c = np.asarray(rgb, float) / 255
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def contrast(fg, bg):
    a, b = sorted([lum(fg), lum(bg)], reverse=True)
    return (a + 0.05) / (b + 0.05)


def region_contrast(frame, box, fg):
    """Contrast of fg against the median colour of the real pixels in box (gate 3)."""
    l, t, r, b = box
    bg = np.median(np.asarray(frame.convert("RGB"))[t:b, l:r].reshape(-1, 3), axis=0)
    return contrast(fg, bg)


# Reading pace per card (gate 4, Z15): need = max(floor, 0.5 s + 0.3 s per word, characters / cps + pad). Characters
# count spaces, as the Netflix and vos limits do. At 20 cps with a 0.5 s pad the character term equals the word term
# on 5-letter words, so it only adds time for long words, numbers and URLs. A card picks one with HOLD_PROFILE in
# scenes.py; an item in text_items(t) may carry its own "profile".
HOLD_PROFILES = {
    # the default: titles, labels, end cards (our own judgement)
    "display": {"cps": 20, "pad": 0.5, "floor": 1.0},
    # read while the picture moves (Netflix children's, vos)
    "caption": {"cps": 17, "pad": 0.5, "floor": 1.0},
    # dense explainer cards: OVH's explainer pace
    "slow": {"cps": 15, "pad": 1.0, "floor": 1.5},
}


def hold_profile(profile=None):
    """(name, {cps, pad, floor}) for a profile name (any case), a dict of overrides, or None (display). An unknown
    name raises ValueError naming the profiles."""
    if isinstance(profile, dict):
        return "custom", {**HOLD_PROFILES["display"], **profile}
    name = str(profile or "display").strip().lower()
    if name not in HOLD_PROFILES:
        raise ValueError(
            f"HOLD_PROFILE {profile!r} is not one of {', '.join(HOLD_PROFILES)} (or a dict of cps, pad, floor)"
        )
    return name, HOLD_PROFILES[name]


def chars(s):
    """Characters a reader takes in: spaces counted, a run of white space counted once."""
    return len(" ".join(str(s).split()))


def min_hold(text_or_words, profile=None):
    """Shortest allowed hold for a text block (gate 4). min_hold(words) is the original rule: 0.5 s + 0.3 s per word,
    at least 1 s. Given the text, it adds the profile's character term (chars / cps + pad; HOLD_PROFILES, None is
    display), so a line of long words, numbers or a URL gets its time."""
    _, p = hold_profile(profile)
    if not isinstance(text_or_words, str):
        return max(p["floor"], 0.5 + 0.3 * text_or_words)
    s = text_or_words
    return max(p["floor"], 0.5 + 0.3 * len(s.split()), chars(s) / p["cps"] + p["pad"])


def slot_budget(has, profile=None):
    """(words_max, chars_max) a line can carry when it is on screen for `has` seconds (entrance already taken off),
    from the same profile as min_hold. To fit a slot, cut words, not reading time."""
    _, p = hold_profile(profile)
    if has + 1e-6 < p["floor"]:
        return 0, 0
    return (
        max(0, math.floor((has - 0.5) / 0.3 + 1e-6)),
        max(0, math.floor((has - p["pad"]) * p["cps"] + 1e-6)),
    )


def first_frame(draw):
    """(ok, mean, std) of frame 0 in grey; dark or blank fails (gate 5)."""
    a = np.asarray(draw(0.0).convert("L"), float)
    return bool(a.mean() > 25 and a.std() > 12), float(a.mean()), float(a.std())


def _flash_frames(draw, i0, i1, fps):
    """Drawn frames i0 to i1 - 1 as the flash gate reads them: float32 linear-light RGB at 192x108, box-averaged in
    linear light (contract.lin_thumb, the scale of Ctx.lin()), each frame's mean grey on the thumbs.npy scale, and
    the frame's aspect W / H."""
    lin, grey, aspect = [], [], 16 / 9
    for i in range(i0, i1):
        im = draw(i / fps).convert("RGB")
        aspect = im.width / im.height
        lin.append(C.lin_thumb(im))
        grey.append(C.thumb(im).mean())
    return np.stack(lin), np.array(grey), aspect


def _flash_list(lin, fps, t0):
    """The pre-2.2.0 shape [(second, flashes)] (one entry per passage over 3 flashes in a sliding second, counts as
    int when whole) from the whole-frame mean luminance: no area and no red test, so an empty list proves nothing."""
    import qa_scan

    L = (lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)).mean((1, 2))
    return [
        (round(t0 + s, 2), int(n) if n == int(n) else n)
        for s, n in qa_scan.flashes(L, fps, linear=True)
    ]


def flash_report(draw, dur, fps=30, rows=True):
    """Gate 6 on the drawn film before any render: qa_scan's rows (Q601 general and Q602 red flashes, Q603 the
    extended band, by area and in linear light). rows=False gives the old [(second, flashes)] list instead."""
    import qa_scan

    lin, _, aspect = _flash_frames(draw, 0, C.frame_of(dur, fps), fps)
    if not rows:
        return _flash_list(lin, fps, 0.0)
    return qa_scan.flash_rows(None, fps, aspect=aspect, lin=lin)


def flash_window(draw, t0, t1, fps=30, rows=True):
    """Gate 6 on drawn frames for one passage (a wipe, a hit) before the film is rendered: qa_scan's rows for the
    passage, times on the film's clock. rows=False gives the old ([(second, flashes)], biggest frame-to-frame jump
    of the mean grey in /255) instead, which is blind to a flash over part of the frame and to red."""
    import qa_scan

    i0, i1 = C.frame_of(t0, fps), C.frame_of(t1, fps) + 1
    lin, grey, aspect = _flash_frames(draw, i0, i1, fps)
    if rows:
        # aspect: the frames were squeezed to 192x108, so a 9:16 film must say so or its 10 degree window is wrong
        return qa_scan.flash_rows(None, fps, aspect=aspect, t0=i0 / fps, lin=lin)
    jumps = np.abs(np.diff(grey))
    return _flash_list(lin, fps, i0 / fps), float(jumps.max()) if len(jumps) else 0.0


def storyboard_holds(md_text, section=None, entrance=0.4, profile=None):
    """Planning check on a scenario's storyboard tables: each quoted on-screen line gets its slot (an explicit
    "(a-b)" after the line, else an equal share of its row's time), minus an entrance; returns rows of
    (status, row time, line, has, needs), needs from min_hold(text, profile); slot_budget(has, profile) says how
    many words and characters the slot fits. Lines joined by " / " are shown together and read as one block."""
    parts = re.split(r"(?m)^## ", md_text)
    if section is not None:
        parts = [
            p for p in parts if p.split("\n", 1)[0].strip().startswith(str(section))
        ]
    out = []
    num = r"(\d+(?:\.\d+)?)"
    for part in parts:
        rows = [
            ln
            for ln in part.splitlines()
            if ln.startswith("|") and not set(ln) <= set("|-: ")
        ]
        if not rows:
            continue
        table, header = [], None
        for ln in rows:
            cells = [c.strip() for c in ln.strip("|").split("|")]
            low = [c.lower() for c in cells]
            if any(c.startswith("time") for c in low) and any("text" in c for c in low):
                header = (
                    next(i for i, c in enumerate(low) if c.startswith("time")),
                    next(i for i, c in enumerate(low) if "text" in c),
                )
                continue
            if header and len(cells) > max(header):
                m = re.search(num + r"\s*-\s*" + num, cells[header[0]]) or re.search(
                    num, cells[header[0]]
                )
                if m:
                    table.append((m, cells[header[0]], cells[header[1]]))
        for k, (m, tcell, text) in enumerate(table):
            a = float(m.group(1))
            b = (
                float(m.group(2))
                if m.lastindex and m.lastindex >= 2
                else (float(table[k + 1][0].group(1)) if k + 1 < len(table) else a)
            )
            if "for example" in text.lower():
                continue
            quotes = list(
                re.finditer(
                    r'"([^"]+)"(?:\s*\(' + num + r"\s*-\s*" + num + r"\))?", text
                )
            )
            groups = []
            for i, q in enumerate(quotes):
                joined = i > 0 and "/" in text[quotes[i - 1].end() : q.start()]
                if joined:
                    groups[-1]["lines"].append(q.group(1))
                    if q.group(2):
                        groups[-1]["win"] = (float(q.group(2)), float(q.group(3)))
                else:
                    groups.append(
                        {
                            "lines": [q.group(1)],
                            "win": (float(q.group(2)), float(q.group(3)))
                            if q.group(2)
                            else None,
                        }
                    )
            if not groups:
                continue
            fixed = sum(g["win"][1] - g["win"][0] for g in groups if g["win"])
            free = [g for g in groups if not g["win"]]
            share = max(0.0, (b - a) - fixed) / len(free) if free else 0.0
            for g in groups:
                has = (g["win"][1] - g["win"][0] if g["win"] else share) - entrance
                needs = min_hold(" ".join(g["lines"]), profile)
                out.append(
                    (
                        "OK" if has + 1e-6 >= needs else "SHORT",
                        tcell,
                        " / ".join(g["lines"]),
                        round(has, 2),
                        round(needs, 2),
                    )
                )
    return out


def flash_report_file(path, fps=30, ff="ffmpeg", rows=True):
    """The same gate on an encoded file, decoded once as a player would (contract.Ctx.lin(), linear light);
    rows=False gives the old [(second, flashes)] list."""
    import qa_scan

    p = probe(path, ff)
    ctx = C.Ctx(path, p, fps, p["w"], p["h"], ff=ff)
    if not rows:
        return _flash_list(ctx.lin(), fps, 0.0)
    return qa_scan.flash_rows(None, fps, aspect=p["w"] / p["h"], lin=ctx.lin())


COLOR_KEYS = ("color_space", "color_primaries", "color_transfer", "color_range")
# what contract.COLOR_VF and COLOR_FLAGS write (Q707)
COLOR_WANT = ("bt709", "bt709", "bt709", "tv")


def probe(path, ff="ffmpeg"):
    """Duration, size, resolution, fps, codecs, frame count, audio channels and colour tags from the ffprobe beside
    ff (gate 7; run_all passes the ffmpeg it found, never a bare name). A colour tag the file does not carry reads
    "unknown"."""
    out = subprocess.run(
        [
            C.ffprobe_of(ff),
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        check=True,
    ).stdout
    j = json.loads(out)
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    a = [s for s in j["streams"] if s["codec_type"] == "audio"]
    return dict(
        duration=float(j["format"]["duration"]),
        size_mb=int(j["format"]["size"]) / 1e6,
        w=v["width"],
        h=v["height"],
        fps=v["r_frame_rate"],
        frames=int(v.get("nb_frames", 0)),
        vcodec=v["codec_name"],
        pix=v.get("pix_fmt"),
        acodec=a[0]["codec_name"] if a else None,
        channels=a[0].get("channels") if a else None,
        **{k: v.get(k) or "unknown" for k in COLOR_KEYS},
    )


SWATCHES = ((40, 180, 60), (192, 32, 32), (0, 255, 0), (30, 60, 200), (128, 128, 128))


def colour_round_trip(ff="ffmpeg", crf=18):
    """(worst level error, its swatch) of flat swatches encoded with libx264 through contract.COLOR_VF and
    COLOR_FLAGS and read back with DECODE_709 (gate 7, Q708); None when the encode or decode fails. The swatches
    are saturated because BT.601 against BT.709 gives no error on greys; the grey one catches a range error."""
    k = 32  # px per swatch; the median of each 16 px core skips the chroma blur at the edges
    frame = np.zeros((k, k * len(SWATCHES), 3), np.uint8)
    for i, c in enumerate(SWATCHES):
        frame[:, i * k : (i + 1) * k] = c
    enc = subprocess.run(
        [
            ff,
            "-v",
            "error",
            "-f",
            "rawvideo",
            "-pixel_format",
            "rgb24",
            "-video_size",
            f"{frame.shape[1]}x{k}",
            "-framerate",
            "30",
            "-i",
            "-",
            "-vf",
            C.COLOR_VF,
            *C.COLOR_FLAGS,
            "-c:v",
            "libx264",
            "-crf",
            str(crf),
            "-f",
            "h264",
            "-",
        ],
        input=frame.tobytes() * 2,
        capture_output=True,
        check=False,
    )
    if enc.returncode or not enc.stdout:
        return None
    dec = subprocess.run(
        [
            ff,
            "-v",
            "error",
            "-f",
            "h264",
            "-i",
            "-",
            "-frames:v",
            "1",
            "-vf",
            f"{C.DECODE_709},format=rgb24",
            "-f",
            "rawvideo",
            "-",
        ],
        input=enc.stdout,
        capture_output=True,
        check=False,
    )
    if dec.returncode or len(dec.stdout) < frame.size:
        return None
    got = np.frombuffer(dec.stdout[: frame.size], np.uint8).reshape(frame.shape)
    errs = [
        int(
            np.abs(
                np.median(got[8:-8, i * k + 8 : (i + 1) * k - 8].reshape(-1, 3), axis=0)
                - c
            ).max()
        )
        for i, c in enumerate(SWATCHES)
    ]
    worst = int(np.argmax(errs))
    return errs[worst], SWATCHES[worst]


LOUD_FRAME = re.compile(  # one ebur128 line per 100 ms: t, momentary, short-term, integrated, per-channel true peak
    r"t:\s*([\d.]+)\s+TARGET:.*?M:\s*(\S+)\s+S:\s*(\S+)\s+I:\s*(\S+) LUFS(?:.*?FTPK:([^d]*)dBFS)?"
)


def _num(x):
    """float(x), or nan for whatever ebur128 prints when a value is undefined."""
    try:
        return float(x)
    except ValueError:
        return float("nan")


def loud(path, ff="ffmpeg"):
    """Integrated loudness (LUFS), LRA (LU) and true peak (dBFS) from ebur128 (gate 8), plus "frames": every 100 ms
    line of the same run as {t, M, S, I, ftpk} (ftpk the frame's true peak, the max over channels), so Q802 can span
    every frame over -1 dBTP without a second pass. Silence reads -inf (ebur128 prints "Peak: -inf dBFS"), and an
    all-gated loudness its "-70.0" floor."""
    r = subprocess.run(
        [
            ff,
            "-hide_banner",
            "-nostdin",
            "-i",
            str(path),
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        # utf-8, not the console code page: an A-acute in the path once left stderr undecoded (None)
        encoding="utf-8",
        errors="replace",
        check=False,
    ).stderr
    s = r[r.rfind("Summary:") :]
    num = lambda pat: float(re.search(pat, s).group(1))  # noqa: E731
    v = r"(-?(?:inf|[\d.]+))"  # float() reads "-inf" too
    frames = []
    for m in LOUD_FRAME.finditer(r):
        tp = [x for x in map(_num, (m[5] or "").split()) if not math.isnan(x)]
        frames.append(
            {
                "t": float(m[1]),
                "M": _num(m[2]),
                "S": _num(m[3]),
                "I": _num(m[4]),
                "ftpk": max(tp) if tp else None,
            }
        )
    return dict(
        I=num(rf"I:\s+{v} LUFS"),
        LRA=num(rf"LRA:\s+{v} LU"),
        peak=num(rf"Peak:\s+{v} dBFS"),
        frames=frames,
    )


def snap_ok(t_cut, bpm, fps=30, tol_frames=1):
    """Cut time within tol_frames of the nearest beat (gate 9). The 1e-6 frame of slack keeps float error from
    flagging a cut exactly one frame off: 31/30 s at 120 BPM measured 1.000000000000003 frames."""
    beat = 60 / bpm
    nearest = round(t_cut / beat) * beat
    return abs(t_cut - nearest) * fps <= tol_frames + 1e-6


def frame_grey(path, w, h, last=False, ff="ffmpeg"):
    """Grey (PIL luma) of the first frame, or the last one (read back from the final second), decoded at full size
    as a player shows it (contract.DECODE_709): what Q501 and Q502 measure, on the scale of first_frame(draw)."""
    pre, vf = (["-sseof", "-1"], "reverse,") if last else ([], "")
    raw = subprocess.run(
        [
            ff,
            "-nostdin",
            "-v",
            "error",
            *pre,
            "-i",
            str(path),
            "-vf",
            f"{vf}{C.DECODE_709},format=rgb24",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-",
        ],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        check=True,
    ).stdout
    rgb = np.frombuffer(raw[: w * h * 3], np.uint8).reshape(h, w, 3).astype(float)
    return rgb @ np.array([0.299, 0.587, 0.114])


FULL = (
    0.98  # alpha at or above this counts as "at rest" for holds, safe area and overlap
)
# alpha above this is on screen: overlaps in a transition, changeovers, Q403
VISIBLE = 0.05


def _rgb(c):
    if isinstance(c, str):
        h = c.lstrip("#")
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
    return tuple(c[:3])


def _shrink(b, k=1):
    return (b[0] + k, b[1] + k, b[2] - k, b[3] - k)


def text_frames(scenes, fps):
    """[(t, items), ...] for every frame, from scenes.text_items(t) (the registry; see qa-gates.md)."""
    return [
        (i / fps, scenes.text_items(i / fps))
        for i in range(C.frame_of(scenes.DURATION, fps))
    ]


def text_spans(frames):
    """{string: [(start, end), ...]} spans of consecutive frames where a non-texture string is at rest."""
    step = frames[1][0] - frames[0][0] if len(frames) > 1 else 0
    spans, opened = {}, {}
    for t, items in frames:
        shown = {
            it["s"]
            for it in items
            if it.get("alpha", 1) >= FULL and not it.get("texture")
        }
        for s in shown:
            opened.setdefault(s, t)
        for s in [s for s in opened if s not in shown]:
            spans.setdefault(s, []).append((opened.pop(s), t))
    for s, a in opened.items():
        spans.setdefault(s, []).append((a, frames[-1][0] + step))
    return spans


def ring_bg(arr, box, pad=6):
    """Median colour of a ring of real pixels just outside a text box; the box itself is mostly glyph ink."""
    H, W = arr.shape[:2]
    l, t, r, b = (int(round(v)) for v in box)
    L, T, R, B = max(0, l - pad), max(0, t - pad), min(W, r + pad), min(H, b + pad)
    ring = np.concatenate(
        [
            arr[T : max(T, t), L:R].reshape(-1, 3),
            arr[min(B, b) : B, L:R].reshape(-1, 3),
            arr[T:B, L : max(L, l)].reshape(-1, 3),
            arr[T:B, min(R, r) : R].reshape(-1, 3),
        ]
    )
    return np.median(ring if len(ring) else arr[T:B, L:R].reshape(-1, 3), axis=0)


def _overflow(b, W, H, m=0.04):
    """How far a box pokes out of the 4 percent safe area, in px (0 when inside)."""
    return max(0.0, W * m - b[0], H * m - b[1], b[2] - W * (1 - m), b[3] - H * (1 - m))


def _area(a, b):
    """Area two boxes share, in px squared."""
    w, h = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _n(k, word):
    """'1 string', '3 strings'."""
    return f"{k} {word}{'' if k == 1 else 's'}"


def _when(spans):
    """'1.20 to 2.40 s' for the first span, and how many more there are."""
    a, b = spans[0]
    s = f"{a:.2f} s" if b - a < 1e-6 else f"{a:.2f} to {b:.2f} s"
    return s + (f" and {len(spans) - 1} more" if len(spans) > 1 else "")


def _worst(hits):
    """(t, value) of the largest [(t, value)] hit. A tie (a static overlap, a constant overflow) takes the middle
    tied frame, as contract.worst_of does for a span."""
    best = max(v for _, v in hits)
    tied = sorted(t for t, v in hits if abs(v - best) <= 1e-6 * max(1.0, abs(best)))
    return tied[len(tied) // 2], best


def _mid(a, b, fps):
    """Middle frame of a rest span [a, b) (b is the first frame after it)."""
    return min(C.frame_of((a + b) / 2, fps), C.frame_of(b, fps) - 1)


def _readable(items):
    """The registry items on screen that someone must read (alpha over VISIBLE, not texture)."""
    return [
        it for it in items if it.get("alpha", 1) > VISIBLE and not it.get("texture")
    ]


def _item(items, s):
    return next((x for x in items if x["s"] == s and not x.get("texture")), None)


def _ink(arr, box, fg, tol=24):
    """(count, bbox) of the pixels within tol levels of the text colour inside its box (2 px pad): the glyph ink
    Q404 compares; bbox (l, t, r, b) is None when there is no ink."""
    H, W = arr.shape[:2]
    l, t = max(0, math.floor(box[0]) - 2), max(0, math.floor(box[1]) - 2)
    r, b = min(W, math.ceil(box[2]) + 2), min(H, math.ceil(box[3]) + 2)
    if r <= l or b <= t:
        return 0, None
    d = np.abs(arr[t:b, l:r].astype(np.int16) - np.array(_rgb(fg), np.int16))
    ys, xs = np.nonzero(d.max(axis=2) <= tol)
    if not len(xs):
        return 0, None
    return len(xs), (l + xs.min(), t + ys.min(), l + xs.max() + 1, t + ys.max() + 1)


INK_SLACK = 3  # px: the registry box is the drawn ink box within 2 (Q205), and the fg match loses 1 at the edge


def _finding(code, item, msg, fix, spans, worst_t, metric, limit, n, note=False):
    """The row for one defect: the frames it is seen on (spans), the moment to open first, its number and limit."""
    return C.row(
        False,
        code,
        msg,
        fix,
        note,
        item=item,
        t0=spans[0][0],
        t1=spans[-1][1],
        worst_t=round(worst_t, 3),
        metric=metric,
        limit=limit,
        spans=spans,
        considered=n,
    )


def _defect_rows(code, found, n, clean, say, fix, fps):
    """One FIX row per defect in found {item: [(t, value)]}, worst_t at the largest value; else one PASS row."""
    if not found:
        return [C.row(True, code, clean, "", considered=n)]
    rows = []
    for item, hits in found.items():
        sp, (wt, v) = C.merge_spans([h[0] for h in hits], fps), _worst(hits)
        rows.append(
            _finding(code, item, say(item, v, sp), fix, sp, wt, round(v, 1), 0.0, n)
        )
    return rows


def _layout_rows(frames, W, H, fps):
    """Q201 safe area, Q202 overlap at rest, Q203 overlap while either fades, on every frame: one row per string or
    pair, worst_t at the largest overflow or shared area."""
    out, rest, trans = {}, {}, {}  # item -> [(t, px outside)] or [(t, px2 shared)]
    at_rest, pairs = set(), {True: set(), False: set()}
    for t, items in frames:
        vis = _readable(items)
        for it in vis:
            if it.get("alpha", 1) >= FULL:
                at_rest.add(it["s"])
                px = _overflow(it["box"], W, H)
                if px > 0:
                    out.setdefault(it["s"], []).append((t, px))
        for j, a in enumerate(vis):
            for b in vis[j + 1 :]:
                if a["s"] == b["s"]:
                    continue
                key = " / ".join(sorted((a["s"], b["s"])))
                both = a.get("alpha", 1) >= FULL and b.get("alpha", 1) >= FULL
                pairs[both].add(key)
                area = _area(_shrink(a["box"]), _shrink(b["box"]))
                if area > 0:
                    (rest if both else trans).setdefault(key, []).append((t, area))
    n_r, n_t = len(pairs[True]), len(pairs[False])
    return (
        _defect_rows(
            "Q201",
            out,
            len(at_rest),
            f"text at rest inside the 4% safe area: {_n(len(at_rest), 'string')}",
            lambda s, v, sp: (
                f"{s!r} {v:.0f} px outside the 4% safe area at rest ({_when(sp)})"
            ),
            "move or shrink it inside the safe area",
            fps,
        )
        + _defect_rows(
            "Q202",
            rest,
            n_r,
            f"no two texts overlap at rest ({_n(n_r, 'pair')} at rest together)",
            lambda s, v, sp: f"{s!r} overlap at rest, up to {v:.0f} px2 ({_when(sp)})",
            "move one, or stagger the exit before the entry",
            fps,
        )
        + _defect_rows(
            "Q203",
            trans,
            n_t,
            f"no two texts overlap while one fades ({_n(n_t, 'pair')} on screen in a fade)",
            lambda s, v, sp: (
                f"{s!r} overlap while one fades, up to {v:.0f} px2 ({_when(sp)})"
            ),
            "fade the old text out before the new one fades in; never crossfade two strings in one spot",
            fps,
        )
    )


def _changeover_rows(scenes, frames, fps):
    """Q207, the Netflix gap rule: text replaced in one place leaves a gap of 2 frames or less, or of 0.5 s or more.
    A NOTE for each changeover in between that ALLOW does not list."""
    runs = {}  # string -> [[first frame, last frame, box at first, box at last], ...] while on screen
    for i, (_, items) in enumerate(frames):
        for it in _readable(items):
            r = runs.setdefault(it["s"], [])
            if r and r[-1][1] >= i - 1:
                r[-1][1], r[-1][3] = i, it["box"]
            else:
                r.append([i, i, it["box"], it["box"]])
    starts = [(r[0], s, r[2]) for s, rs in runs.items() for r in rs]
    gaps, n = [], 0
    for s, rs in runs.items():
        for _, fe, _, box in rs:
            nxt = min(
                (
                    (fs, s2)
                    for fs, s2, b2 in starts
                    if fs > fe and s2 != s and overlap(box, b2)
                ),
                default=None,
            )
            if nxt is None:
                continue
            n += 1
            g, t0, t1 = nxt[0] - fe - 1, (fe + 1) / fps, (nxt[0] - 1) / fps
            if 2 < g < 0.5 * fps and not C.allowed(
                scenes, "Q207", (t0 + t1) / 2, (t1 - t0) / 2 + 1 / fps
            ):
                gaps.append((s, nxt[1], g, t0, t1))
    if not gaps:
        return [
            C.row(
                True,
                "Q207",
                f"text changeovers in one place: {n}, none with a gap of 3 frames to 0.5 s",
                "",
                considered=n,
            )
        ]
    return [
        _finding(
            "Q207",
            f"{s} -> {s2}",
            f"changeover {s!r} -> {s2!r} in one place: {g} empty frames ({g / fps:.2f} s, {t0:.2f} to {t1:.2f} s)",
            "close the gap to 2 frames, or leave the place empty for 0.5 s or more",
            [(round(t0, 3), round(t1, 3))],
            C.snap((t0 + t1) / 2, fps),
            round(g / fps, 3),
            0.5,
            n,
            note=True,
        )
        for s, s2, g, t0, t1 in gaps
    ]


def _ticker_passing(frames):
    """The values a ticker shows on its way (registry items with ticker=True: a counter, a clock): a value whose
    every run on screen hands over to another ticker value in the same place within 2 frames. Only the value a run
    settles on is there to be read; 313 counter values of the rectangle film each rested 0.03 to 0.87 s and every
    one was a Q401 FIX. Returns (passing strings, number of values a ticker settles on)."""
    runs = {}  # string -> [[first frame, last frame, box at first, box at last], ...] while on screen
    for i, (_, items) in enumerate(frames):
        for it in _readable(items):
            if it.get("ticker"):
                r = runs.setdefault(it["s"], [])
                if r and r[-1][1] >= i - 1:
                    r[-1][1], r[-1][3] = i, it["box"]
                else:
                    r.append([i, i, it["box"], it["box"]])
    starts = [(r[0], s, r[2]) for s, rs in runs.items() for r in rs]
    passing, settled = set(), set()
    for s, rs in runs.items():
        for _, fe, _, box in rs:
            hands = any(
                s2 != s and fe - 1 <= fs <= fe + 3 and overlap(box, b2)
                for fs, s2, b2 in starts
            )
            (passing if hands else settled).add(s)
    return passing - settled, len(settled)


def _contrast_rows(scenes, frames, spans, fps, scale, passing=()):
    """Q301 on real pixels: every rest span measured at its first, middle and last frame (each frame drawn once),
    against a ring of pixels around the box; worst_t at the lowest ratio against its minimum. A ticker's values on
    the way (passing) are not sampled: a counter changing every 2 frames for 10 s was 300 more frames to draw."""
    samples = {}
    for s, sp in spans.items():
        if s in passing:
            continue
        for a, b in sp:
            fa, fb = C.frame_of(a, fps), C.frame_of(b, fps)
            ks = range(fa, fb) if fb - fa <= 3 else (fa + 1, _mid(a, b, fps), fb - 2)
            for k in ks:
                samples.setdefault(k, set()).add(s)
    measured = {}  # string -> [(t, ratio, minimum)]
    for k in sorted(samples):
        arr = None
        for s in sorted(samples[k]):
            it = _item(frames[k][1], s)
            if it is None or "fg" not in it:
                continue
            if arr is None:
                arr = np.asarray(scenes.draw(frames[k][0]).convert("RGB"))
            px = it.get("px")
            large = px is not None and (
                px * scale >= 36 or (px * scale >= 24 and it.get("bold", False))
            )
            ratio = contrast(_rgb(it["fg"]), ring_bg(arr, it["box"]))
            measured.setdefault(s, []).append(
                (frames[k][0], ratio, 3.0 if large else 4.5)
            )
    rows, n = [], len(measured)
    for s, m in measured.items():
        hits = [x[0] for x in m if x[1] < x[2]]
        if hits:
            wt, ratio, need = min(m, key=lambda x: x[1] / x[2])
            sp = C.merge_spans(hits, fps)
            rows.append(
                _finding(
                    "Q301",
                    s,
                    f"{s!r} contrast {ratio:.2f}:1, needs {need:g}:1 (under on {len(hits)} of {len(m)} sampled rest frames, {_when(sp)})",
                    "darken the text tint, add a halo or scrim, or move it off the busy area",
                    sp,
                    wt,
                    round(ratio, 2),
                    need,
                    n,
                )
            )
    nofg = [s for s in spans if s not in measured and s not in passing]
    if nofg:
        rows.append(
            C.not_checked(
                "Q301",
                f"text at rest with no fg in the registry, contrast not measured: {len(nofg)} ({'; '.join(map(repr, nofg[:3]))})",
                "give every text_items entry its fg colour",
                item=nofg[0],
            )
        )
    if not rows and not measured:  # only ticker values on the way ever rest
        rows.append(
            C.not_checked(
                "Q301",
                "only a ticker's values on the way are at rest, so no contrast was measured",
                "let the ticker settle at full alpha on its last value",
            )
        )
    if not rows:
        s, (_, ratio, need) = min(
            ((s, min(m, key=lambda x: x[1] / x[2])) for s, m in measured.items()),
            key=lambda x: x[1][1] / x[1][2],
        )
        rows.append(
            C.row(
                True,
                "Q301",
                f"text at its contrast minimum: {_n(n, 'string')} at the first, middle and last frame of each rest (lowest {s!r} {ratio:.2f}:1 against {need:g}:1)",
                "",
                considered=n,
            )
        )
    return rows


def _hold_rows(scenes, frames, spans, fps, scale, passing=()):
    """Q401 reading hold under the card's profile (scenes.HOLD_PROFILE, or the item's own "profile") and Q402 key
    text under 36 px at 1080, each from the string's longest rest; worst_t is the middle of that rest. A ticker's
    values on the way (passing, see _ticker_passing) need no hold; the value it settles on does."""
    card = getattr(scenes, "HOLD_PROFILE", None)
    short, small, tight, n_px, bad = [], [], None, 0, {}
    n_held = sum(s not in passing for s in spans)
    for s, sp in spans.items():
        a, b = max(sp, key=lambda x: x[1] - x[0])
        k = _mid(a, b, fps)
        it = _item(frames[k][1], s) or {}
        sp_in = [(round(x, 3), round(y - 1 / fps, 3)) for x, y in sp]  # last frames
        px = it.get("px")
        if px is not None:
            n_px += 1
            if px * scale < 36 and not C.allowed(scenes, "Q402", k / fps, 1 / fps):
                small.append((s, px * scale, k, sp_in))
        if s in passing:
            continue
        # "profile": None means the card's profile, not display
        prof, has = it.get("profile") or card, b - a
        # an unknown profile name: one NOT CHECKED row, and the other strings go on
        try:
            need = min_hold(s, prof)
        except ValueError as e:
            bad.setdefault(str(e), s)
            need = None
        if need is not None and has + 1e-6 < need:
            settles = "; the value its ticker settles on" if it.get("ticker") else ""
            short.append(
                _finding(
                    "Q401",
                    s,
                    f"{s!r} longest rest {has:.2f} s, needs {need:.2f} s ({_n(len(s.split()), 'word')}, "
                    f"{_n(chars(s), 'character')}, {hold_profile(prof)[0]} profile{settles})",
                    "cut words, lengthen the slot, or let the line stay through the next beat (cut words, not reading time)",
                    sp_in,
                    k / fps,
                    round(has, 2),
                    round(need, 2),
                    n_held,
                )
            )
        elif need is not None and (tight is None or has - need < tight[1] - tight[2]):
            tight = (s, has, need)
    on_way = (
        f"; {_n(len(passing), 'ticker value')} on the way to the one a ticker settles on need no hold"
        if passing
        else ""
    )
    rows = short + [
        C.not_checked(
            "Q401",
            f"{why}, so the hold of {s!r} and every string under that profile was not checked",
            "set HOLD_PROFILE (or the item's profile) to display, caption or slow",
            item=s,
        )
        for why, s in bad.items()
    ]
    rows = rows or [
        C.row(
            True,
            "Q401",
            f"reading holds at or over the {card if isinstance(card, str) else hold_profile(card)[0]} profile: "
            f"{_n(n_held, 'string')}"
            + (
                f" (tightest {tight[0]!r} {tight[1]:.2f}/{tight[2]:.2f} s)"
                if tight
                else ""
            )
            + on_way,
            "",
            considered=n_held,
        )
    ]
    rows += [
        _finding(
            "Q402",
            s,
            f"{s!r} {px:.0f} px at 1080 (key text wants 36)",
            "mark it texture=True if nobody must read it, else enlarge it",
            sp_in,
            k / fps,
            round(px, 1),
            36.0,
            n_px,
            note=True,
        )
        for s, px, k, sp_in in small
    ] or [
        C.row(
            True,
            "Q402",
            f"key text at 36 px or more at 1080: {_n(n_px, 'string')}",
            "",
            considered=n_px,
        )
    ]
    return rows


def _rest_rows(frames, fps):
    """Q403: readable text whose alpha never reaches 0.98 (an eased fade that stops short, a ghost left at half
    alpha). Q401 measures rests, so it cannot see these; no pixels are needed."""
    peak, seen = {}, {}
    for t, items in frames:
        for it in _readable(items):
            s, al = it["s"], it.get("alpha", 1)
            if al > peak.get(s, (-1.0, 0.0))[0]:
                peak[s] = (al, t)
            seen.setdefault(s, []).append(t)
    rows = []
    for s, (al, t) in peak.items():
        if al < FULL:
            sp = C.merge_spans(seen[s], fps)
            rows.append(
                _finding(
                    "Q403",
                    s,
                    f"{s!r} never reaches rest: alpha peaks at {al:.2f} at {t:.2f} s (on screen {_when(sp)})",
                    "let it settle to full alpha for its hold, or mark it texture=True if nobody must read it",
                    sp,
                    t,
                    round(al, 3),
                    FULL,
                    len(peak),
                )
            )
    return rows or [
        C.row(
            True,
            "Q403",
            f"every registered text reaches rest (alpha {FULL}): {_n(len(peak), 'string')}",
            "",
            considered=len(peak),
        )
    ]


def _reveal_rows(scenes, frames, spans, fps):
    """Q404: an item that carries reveal_end has all its glyph ink drawn by then. Ink is the pixels matching its fg
    in its box. At reveal_end the ink must reach both ends of the registered box (the whole string's box, which
    Q205 holds to the drawn ink within 2 px) within INK_SLACK, and be 0.98 of the ink at the last rest frame: a
    reveal whose progress stops short is just as short at rest, so the rest frame alone read it as complete."""
    reveal = {}
    for _, items in frames:
        for it in _readable(items):
            if "reveal_end" in it:
                reveal.setdefault((it["s"], float(it["reveal_end"])), it.get("fg"))

    def ink(k, it, fg):
        return _ink(np.asarray(scenes.draw(frames[k][0]).convert("RGB")), it["box"], fg)

    rows = []
    for (s, te), fg in reveal.items():
        kr = C.frame_of(te, fps)
        ends = [C.frame_of(b, fps) - 1 for _, b in spans.get(s, [])]  # last rest frames
        ks = next((e for e in ends if e >= kr), None)
        why = (
            "it has no fg"
            if fg is None
            else "reveal_end is outside the piece"
            if not 0 <= kr < len(frames)
            else "it is never at rest after reveal_end"
            if ks is None
            else None
        )
        if why is None:
            settled = _item(frames[ks][1], s)
            full = ink(ks, settled, fg)[0]
            why = None if full else "no pixel of its fg is in its box at rest"
        if why:
            rows.append(
                C.not_checked(
                    "Q404",
                    f"{s!r} declares reveal_end {te:.2f} s, but {why}, so the reveal was not compared",
                    "give the item its fg and a rest after reveal_end",
                    item=s,
                    worst_t=round(te, 3),
                )
            )
            continue
        drawn = _item(frames[kr][1], s) or settled
        n, bb = ink(kr, drawn, fg)
        box = drawn["box"]
        # how far the ink stops inside the registered box at its left or right end (px), the way text reveals run;
        # a box taller than the ink is Q205's to judge, not a reveal that stopped short. No ink is the whole width.
        short = max(bb[0] - box[0], box[2] - bb[2]) if bb else box[2] - box[0]
        ratio = n / full
        if ratio < FULL or short > INK_SLACK:
            tr = round(kr / fps, 3)
            say = f"{s!r} at reveal_end {te:.2f} s: " + (
                f"{ratio:.0%} of its ink at the rest frame ({ks / fps:.2f} s)"
                if ratio < FULL
                else f"its ink stops {short:.0f} px inside the registered box {tuple(round(v) for v in box)}"
            )
            rows.append(
                _finding(
                    "Q404",
                    s,
                    say,
                    "let the reveal reach 1.0 by reveal_end (clamp the eased progress), or move reveal_end to where it "
                    "is complete; the box must be the whole string's (engine.text_box)",
                    [(tr, tr)],
                    tr,
                    round(ratio, 3) if ratio < FULL else round(float(short), 1),
                    FULL if ratio < FULL else float(INK_SLACK),
                    len(reveal),
                )
            )
    return rows or [
        C.row(
            True,
            "Q404",
            f"reveals complete at reveal_end: {_n(len(reveal), 'item')}"
            if reveal
            else "no item declares reveal_end, so no reveal to compare",
            "",
            considered=len(reveal),
        )
    ]


def text_gates(scenes, W, H, fps):
    """Gates 2 to 4 from the text registry on every frame: Q201 safe area, Q202 overlap at rest, Q203 overlap while
    either fades, Q207 changeover gap, Q301 contrast, Q401 reading hold (the card's profile), Q402 key text size,
    Q403 never at rest, Q404 reveal incomplete at reveal_end. One row per defect (the string, or the pair as
    "a / b") with the frames it is seen on and worst_t, the moment to open first; one PASS row per clean code.
    `considered` says how many strings, pairs or changeovers a code looked at."""
    frames = text_frames(scenes, fps)
    if not any(_readable(items) for _, items in frames):
        # a registry with nothing readable in it checks nothing
        if C.declared(scenes, "NO_TEXT"):
            return [
                C.row(
                    True,
                    "Q200",
                    "no readable text in the registry, by design (NO_TEXT)",
                    "",
                    considered=0,
                )
            ]
        return [
            C.not_checked(
                "Q200",
                "text_items(t) reported no readable text on any frame, so gates 2 to 4 checked nothing",
                "register every text draw(t) writes (references/qa-gates.md), or set NO_TEXT = True if the piece has none",
            )
        ]
    spans = text_spans(frames)
    scale = 1080 / min(W, H)  # the size rules are written for 1080 px on the short side
    rows = _layout_rows(frames, W, H, fps) + _changeover_rows(scenes, frames, fps)
    if spans:
        passing = _ticker_passing(frames)[0]
        rows += _contrast_rows(scenes, frames, spans, fps, scale, passing)
        rows += _hold_rows(scenes, frames, spans, fps, scale, passing)
    else:
        rows += [
            C.not_checked(
                code,
                f"no registered text reaches rest (alpha {FULL}), so {what} was not measured (see Q403)",
                "let the text settle to full alpha for its hold",
            )
            for code, what in (
                ("Q301", "contrast"),
                ("Q401", "the reading hold"),
                ("Q402", "the text size"),
            )
        ]
    return rows + _rest_rows(frames, fps) + _reveal_rows(scenes, frames, spans, fps)


def cue_gates(scenes, a8k, g, fps):
    """Q902, now in qa_sync.py (kept here so qa.cue_gates still works)."""
    import qa_sync

    return qa_sync.cue_gates(scenes, a8k, g, fps)


def registry_rows(scenes, W, H, fps):
    """Gates 2 to 4 from the registry, or Q200: NOT CHECKED when scenes.py draws text with no text_items(t) and
    does not declare NO_TEXT."""
    if hasattr(scenes, "text_items"):
        old = _old_form(scenes, fps)
        if old:
            return [
                C.not_checked(
                    "Q200",
                    f"text_items(t) returns items without the s and box keys at {old[0]:.2f} s (keys {old[1]}), "
                    "the older kit form, so gates 2 to 4 cannot read them",
                    "report each text as {s, box from engine.text_box, fg, alpha, px} like engine/scenes.py",
                    worst_t=old[0],
                )
            ]
        return text_gates(scenes, W, H, fps)
    if C.declared(scenes, "NO_TEXT"):
        return [C.row(True, "Q200", "no on-screen text by design (NO_TEXT)", "")]
    return [
        C.not_checked(
            "Q200",
            "scenes.py has no text_items(t), so gates 2 to 4 did not run",
            "add the text registry (references/qa-gates.md), or set NO_TEXT = True if the piece has no text",
        )
    ]


def _old_form(scenes, fps, step=0.5):
    """(t, keys) of the first registry item without "s" and "box" (a kit registry from before the contract), or
    None. Sampled every step seconds: text_items is cheap, and one item is enough to know the form."""
    t = 0.0
    while t < scenes.DURATION:
        for it in scenes.text_items(t) or []:
            if "s" not in it or "box" not in it:
                return round(t, 2), sorted(it)
        t += step
    return None


def proof_rows(scenes, W, H, fps):
    """The gates run on drawn frames before any render (run_all.py proof): Q501 on frame 0, the registry gates and
    the registry recorder (qa_registry: text drawn but not reported, about 4 s on the template)."""
    import qa_registry

    ok, mean, std = first_frame(scenes.draw)
    return (
        [
            C.row(
                ok,
                "Q501",
                f"first frame mean {mean:.1f}, std {std:.1f} (want > 25 and > 12)",
                "draw the hook fully at t=0; animate only the extras",
                worst_t=0.0,
                metric=round(mean, 1),
                limit=25.0,
            )
        ]
        + registry_rows(scenes, W, H, fps)
        + qa_registry.rows(scenes, W, H, fps)
    )


def cut_times(scenes):
    """(times, source) of the cuts Q901 holds to the beat grid: scenes.CUTS when the module has it (compile_schedule
    writes it; seconds as numbers, (t, ...) or {"t": t}), else every SCHEDULE start after 0."""
    cuts = getattr(scenes, "CUTS", None)
    if cuts is None:
        return sorted(a for a, _ in scenes.SCHEDULE.values() if a > 0), "SCHEDULE"
    ts = (
        c["t"] if isinstance(c, dict) else c[0] if isinstance(c, (tuple, list)) else c
        for c in cuts
    )
    return sorted(
        {float(t) for t in ts if 0 < float(t) < scenes.DURATION - 1e-9}
    ), "CUTS"


def grid_rows(scenes, bpm, fps):
    """Q901: every cut within one frame of the BPM grid; one NOTE row per cut off it that ALLOW does not list."""
    ts, src = cut_times(scenes)
    names = {round(a, 6): n for n, (a, _) in scenes.SCHEDULE.items()}
    beat = 60 / bpm
    off = [
        (t, (t - round(t / beat) * beat) * fps)
        for t in ts
        if not snap_ok(t, bpm, fps) and not C.allowed(scenes, "Q901", t, 1 / fps)
    ]
    if not off:
        return [
            C.row(
                True,
                "Q901",
                f"{_n(len(ts), 'cut')} on the {bpm:g} BPM grid within 1 frame (from {src})",
                "",
                considered=len(ts),
            )
        ]
    return [
        C.row(
            False,
            "Q901",
            f"cut at {t:.3f} s ({names.get(round(t, 6), 'a cut')}) is {d:+.1f} frames off the {bpm:g} BPM grid (from {src})",
            "snap cuts to beats (strong cuts to bar lines), or list a planned off-grid cut in ALLOW",
            note=True,
            item=names.get(round(t, 6), f"cut at {t:.3f} s"),
            t0=t,
            t1=t,
            worst_t=round(t, 3),
            metric=round(d, 2),
            limit=1.0,
            spans=[(t, t)],
            considered=len(ts),
        )
        for t, d in off
    ]


def check(
    path,
    duration=None,
    fps=None,
    size=None,
    bpm=None,
    scenes_dir=None,
    max_mb=None,
    silent=False,
    ff="ffmpeg",
    **opts,
):
    """Every gate measurable on the final file, as contract.Row rows (they unpack as (status, code, message, fix)).
    Status is PASS, FIX, NOTE or NOT CHECKED; opts reach the gate modules as ctx.opts. ff is the ffmpeg to run
    (run_all passes the one it found; ffprobe is taken from beside it). scenes.SILENT counts as --silent."""
    rows = []

    def add(ok, code, msg, fix, note=False, **kw):
        rows.append(C.row(ok, code, msg, fix, note, **kw))

    p = probe(path, ff)
    n, d = (int(x) for x in p["fps"].split("/"))
    rate = n / d
    sched = scn = None
    if (
        scenes_dir
    ):  # SCHEDULE, DURATION and an optional BPM from the video's own scenes.py
        sys.path.insert(0, str(scenes_dir))
        import engine as E

        E.W, E.H, E.FPS = p["w"], p["h"], round(rate)
        # the supersample factor the build rendered at, so contrast frames match it
        b = C.read_build(scenes_dir)
        E.SS = b[3] if b else E.SS
        import scenes

        scn = scenes
        sched, duration = scenes.SCHEDULE, duration or scenes.DURATION
        bpm = bpm or getattr(scenes, "BPM", None)
        silent = silent or C.declared(scn, "SILENT")
    cap = max_mb if max_mb is not None else getattr(scn, "BUDGET_MB", None)
    cap_src = "--max-mb" if max_mb is not None else "scenes.BUDGET_MB"

    if duration:
        add(
            abs(p["duration"] - duration) <= 0.1,
            "Q701",
            f"duration {p['duration']:.2f} s (want {duration:.2f} +/- 0.10)",
            "trim or pad the audio with -shortest, or fix DURATION",
            metric=round(p["duration"], 3),
            limit=duration,
        )
    if fps:
        add(
            abs(rate - fps) < 0.01,
            "Q702",
            f"fps {rate:g} (want {fps:g})",
            "encode with -framerate and -r set to E.FPS",
            metric=rate,
            limit=fps,
        )
    if size:
        w, h = (int(x) for x in size.lower().split("x"))
        add(
            (p["w"], p["h"]) == (w, h),
            "Q703",
            f"size {p['w']}x{p['h']} (want {w}x{h})",
            "set E.W and E.H before importing scenes",
        )
    if p["frames"]:
        want = round(p["duration"] * rate)
        add(
            abs(p["frames"] - want) <= 1,
            "Q704",
            f"frames {p['frames']} (want {want} +/- 1)",
            "render every frame of DURATION * FPS, then re-encode",
            metric=p["frames"],
            limit=want,
        )
    # the pixel format and the BT.709 chain are checked on the H.264 deliverable only
    if p["vcodec"] != "h264":
        rows += [
            C.not_checked(
                code,
                f"{p['vcodec']} file: the {what} check is for the H.264 deliverable",
                "deliver H.264 (run_all.py full), or check the colours by eye",
            )
            for code, what in (
                ("Q705", "yuv420p"),
                ("Q707", "colour tag"),
                ("Q708", "colour round trip"),
            )
        ]
    else:
        add(
            p["pix"] == "yuv420p",
            "Q705",
            f"pixel format {p['pix']}",
            "encode with -pix_fmt yuv420p",
        )
        tags = tuple(p[k] for k in COLOR_KEYS)
        add(
            tags == COLOR_WANT,
            "Q707",
            f"colour tags {' / '.join(tags)} (space / primaries / transfer / range; want {' / '.join(COLOR_WANT)})",
            "encode through contract.COLOR_VF and COLOR_FLAGS (run_all.py does): an untagged file plays up to 40 levels off on saturated colours",
            item=" / ".join(tags),
        )
        rt = colour_round_trip(ff)
        if rt is None:
            rows.append(
                C.not_checked(
                    "Q708",
                    "colour round trip could not run: the libx264 encode or the decode of the swatch clip failed",
                    "use an ffmpeg build with libx264",
                )
            )
        else:
            add(
                rt[0] <= 8,
                "Q708",
                f"colour round trip through COLOR_VF and DECODE_709: worst {rt[0]} levels, on swatch {rt[1]} (want <= 8)",
                "the BT.709 chain in contract.COLOR_VF no longer round-trips on this ffmpeg: re-probe it on saturated swatches and fix the chain",
                item=str(rt[1]),
                metric=rt[0],
                limit=8,
                considered=len(SWATCHES),
            )
    if not silent:
        add(
            p["acodec"] is not None,
            "Q706",
            f"audio stream {p['acodec']}",
            "mux mix.wav into the encode, or pass --silent (or set SILENT in scenes.py) for a silent piece",
        )
    ctx = C.Ctx(
        path,
        p,
        round(rate),
        p["w"],
        p["h"],
        scn,
        scenes_dir,
        opts={"bpm": bpm, "max_mb": cap, "silent": silent, **opts},
        ff=ff,
    )
    if p["acodec"] and not silent:
        L = ctx.loudness = loud(path, ff)
        add(
            abs(L["I"] + 14) <= 1,
            "Q801",
            f"loudness {L['I']} LUFS (want -14 +/- 1)",
            "rerun audio.master on the raw mix, then re-encode",
            metric=L["I"],
            limit=-14.0,
        )
        rows += _silence_rows(ctx.audio(8000), scn)

    f0 = frame_grey(path, p["w"], p["h"], ff=ff)
    add(
        f0.mean() > 25 and f0.std() > 12,
        "Q501",
        f"first frame mean {f0.mean():.1f}, std {f0.std():.1f} (want > 25 and > 12)",
        "draw the hook fully at t=0; animate only the extras",
        worst_t=0.0,
        metric=round(float(f0.mean()), 1),
        limit=25.0,
    )
    f1 = frame_grey(path, p["w"], p["h"], last=True, ff=ff)
    last_t = round(((p["frames"] or round(p["duration"] * rate)) - 1) / rate, 3)
    add(
        f1.mean() > 25,
        "Q502",
        f"last frame mean {f1.mean():.1f} (want > 25)",
        "hold the end card instead of fading to black",
        worst_t=last_t,
        metric=round(float(f1.mean()), 1),
        limit=25.0,
    )
    try:
        g = ctx.grey64().reshape(-1, 36 * 64)
    except (
        RuntimeError,
        subprocess.CalledProcessError,
    ) as e:  # a short or failed decode (the gate modules say so too)
        rows.append(
            C.not_checked(
                "Q503",
                f"the decode failed ({str(e)[:200]}), so the end card hold was not measured",
                "check the file plays to its end",
            )
        )
    else:
        k = min(len(g) - 1, round(rate))
        held = np.abs(g[-1 - k] - g[-1]).mean()
        add(
            held < 10,
            "Q503",
            f"last 1 s change {held:.1f}/255 (want < 10: end card held)",
            "give the end card at least 1 s of hold",
            note=True,
            worst_t=last_t,
            metric=round(float(held), 1),
            limit=10.0,
        )
    if sched and bpm:
        rows += grid_rows(scn, bpm, rate)
    if scn is not None:
        rows += registry_rows(scn, p["w"], p["h"], round(rate))
    add(
        cap is None or p["size_mb"] <= cap,
        "Q1001",
        f"file size {p['size_mb']:.1f} MB"
        + (
            f" (cap {cap:g} MB, from {cap_src})"
            if cap is not None
            else " (no cap: pass --max-mb or set BUDGET_MB in scenes.py)"
        ),
        "raise CRF to 20, drop grain, or go 720p",
        item=cap_src if cap is not None else None,
        metric=round(p["size_mb"], 2),
        limit=cap,
    )
    mbps = p["size_mb"] * 8 / max(p["duration"], 1e-6)
    add(
        mbps <= 12,
        "Q1002",
        f"bitrate {mbps:.1f} Mb/s (flat graphics land at 1 to 5)",
        "baked grain is the usual cause: grain std 1.6 or less and CRF 20 (formats.md)",
        note=True,
        metric=round(mbps, 2),
        limit=12.0,
    )
    ctx.rows = rows  # the same list: each gate module sees every row before it (qa_approve's Q1302 reads them all)
    # each gate module owns its codes (contract.CODES) and reads the decoded file from ctx; one that raises becomes
    # one Q100 row and the others still run
    for m in C.GATE_MODULES:
        try:
            rows += importlib.import_module(m).check_rows(ctx)
        except Exception as e:  # noqa: BLE001
            rows.append(_module_row(m, e))
    return rows


def _module_row(m, e):
    """Q100 NOT CHECKED for gate module m that raised e, naming the error and the line it came from."""
    tb = traceback.extract_tb(e.__traceback__)
    # the deepest line in the engine's own files (subprocess.py:1553 says nothing), else the deepest line
    here = Path(__file__).resolve().parent
    own = [f for f in tb if Path(f.filename).resolve().parent == here] or tb
    where = f" at {Path(own[-1].filename).name}:{own[-1].lineno}" if own else ""
    return C.not_checked(
        "Q100",
        f"{m} raised {type(e).__name__}{where}: {str(e)[:300]}; its gates did not run",
        f"fix {m}.py; importing it and calling its check_rows alone shows the traceback",
        item=m,
    )


def _silence_rows(a, scenes):
    """Q803: a near-silent second (under -60 dBFS) inside the piece, one NOTE per run of seconds that ALLOW does not
    list. Seconds 1 to n - 2 are inside; a piece under 3 s has none, which is a PASS that says so. An audio stream
    that decodes to nothing is NOT CHECKED."""
    if not len(a):
        return [
            C.not_checked(
                "Q803",
                "the audio stream decoded to no samples, so silence was not measured",
                "check the audio track (ffmpeg -i <file>)",
            )
        ]
    secs = len(a) // 8000
    if secs < 3:
        return [
            C.row(
                True,
                "Q803",
                f"no second inside a {len(a) / 8000:.1f} s piece to measure (seconds 1 to n - 2 are inside)",
                "",
                considered=0,
            )
        ]
    db = 20 * np.log10(
        np.sqrt((a[: secs * 8000].reshape(secs, 8000) ** 2).mean(1)) + 1e-9
    )
    quiet = [
        s
        for s in range(1, secs - 1)
        if db[s] < -60 and not C.allowed(scenes, "Q803", s + 0.5, 0.5)
    ]
    rows = []
    for a0, a1 in C.merge_spans(quiet, 1, pad_frames=1):  # runs of whole seconds
        q = min(range(int(a0), int(a1) + 1), key=lambda s: db[s])
        rows.append(
            C.row(
                False,
                "Q803",
                f"near-silent seconds inside the piece: {a0:g} to {a1 + 1:g} s (quietest {db[q]:.0f} dBFS)",
                "fine if planned (a glitch, a think pause; list it in ALLOW); otherwise check the mix",
                note=True,
                item=f"{a0:g}-{a1 + 1:g} s",
                t0=a0,
                t1=a1 + 1,
                worst_t=q + 0.5,
                metric=round(float(db[q]), 1),
                limit=-60.0,
                spans=[(a0, a1 + 1)],
                considered=secs - 2,
            )
        )
    return rows or [
        C.row(
            True,
            "Q803",
            "near-silent seconds inside the piece: none",
            "",
            considered=secs - 2,
        )
    ]


def look(path, times=None, width=480, out="review", cols=4, ff="ffmpeg"):
    """Small JPEG copies of frames at times (default every 5 s plus the last frame) and one review/look.jpg sheet."""
    p = probe(path, ff)
    n, d = (int(x) for x in p["fps"].split("/"))
    last = (
        int((p["duration"] - 2 * d / n) * 100) / 100
    )  # rounded down, so the seek never passes the final frame
    times = times or sorted({*[t for t in range(0, int(last) + 1, 5)], last})
    Path(out).mkdir(exist_ok=True)
    thumbs = []
    for t in times:
        f = Path(out) / f"t{t:06.2f}.jpg"
        subprocess.run(
            [
                ff,
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-ss",
                str(t),
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-vf",
                f"scale={width}:-2",
                str(f),
            ],
            stdin=subprocess.DEVNULL,
            check=True,
        )
        im = Image.open(f).convert("RGB")
        ImageDraw.Draw(im).text((6, 6), f"{t:.2f}s", fill=(255, 0, 0))
        thumbs.append(im)
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * width, rows * thumbs[0].height), (30, 30, 30))
    for i, im in enumerate(thumbs):
        sheet.paste(im, ((i % cols) * width, (i // cols) * im.height))
    sheet.save(Path(out) / "look.jpg", quality=85)
    print(
        f"wrote {Path(out) / 'look.jpg'} ({len(thumbs)} frames at {width} px, {sheet.width}x{sheet.height})"
    )


# findings a reviewer needs to see as a few frames, not one
STRIP = ("Q203", "Q207", "Q404")
# gate modules that put their own findings into review_times.json (qa_scan.add_review): --json skips their codes
RECORDS_OWN = ("qa_scan",)


def review_entries(rows):
    """The review_times.json entries `qa.py check --json` adds: each finding's worst_t, reason "code status item"
    (the message when there is no item), whole. Codes whose module records them itself are left to it: a second
    copy came back under a different reason, cut at 80 characters mid-word."""
    return [
        {
            "t": r.worst_t,
            "why": f"{r.code} {r.status} {r.item or r.msg}",
            "kind": "finding",
            "code": r.code,
            "status": r.status,  # the sheet ranks by it; without it a NOTE fell back to its code's FIX
            "strip": r.code in STRIP,
        }
        for r in rows
        if r.status != C.PASS
        and r.worst_t is not None
        and C.CODES.get(r.code, ("",))[0] not in RECORDS_OWN
    ]


def _load(m, why):
    """Import gate or CLI module m, or None with one line on stderr: a module that does not import must not take
    qa.py check down with it (check itself reports it as Q100)."""
    try:
        return importlib.import_module(m)
    except Exception as e:  # noqa: BLE001
        print(
            f"qa.py: {m} did not import ({type(e).__name__}: {e}); {why}",
            file=sys.stderr,
        )
        return None


if __name__ == "__main__":
    import argparse

    # a redirected Windows stdout is cp1252: never die on a character a registered string carries
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    ap = argparse.ArgumentParser(description="QA gates on a finished video")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser(
        "check",
        help="coded findings for every gate measurable on the file; exit 1 on any FIX",
    )
    c.add_argument("video")
    c.add_argument("--duration", type=float)
    c.add_argument("--fps", type=float)
    c.add_argument("--size", help="WxH, for example 1080x1920")
    c.add_argument("--bpm", type=float)
    c.add_argument(
        "--scenes",
        help="folder holding the video's scenes.py (reads SCHEDULE, DURATION, BPM)",
    )
    c.add_argument("--max-mb", type=float)
    c.add_argument(
        "--silent", action="store_true", help="the piece has no audio on purpose"
    )
    c.add_argument(
        "--json",
        help="also write the rows as JSON to this path (and, with --scenes, every finding's worst_t to "
        "review_times.json there)",
    )
    for m in (
        C.GATE_MODULES
    ):  # a gate module may add its own check flags; they reach it as ctx.opts
        f = getattr(_load(m, "its check flags are missing"), "add_check_args", None)
        if f:
            f(c)
    lk = sub.add_parser("look", help="small frame copies and review/look.jpg")
    lk.add_argument("video")
    lk.add_argument("--times", help="comma-separated seconds")
    lk.add_argument("--width", type=int, default=480)
    lk.add_argument("--out", default="review")
    hd = sub.add_parser(
        "holds",
        help="planning check: every storyboard line gets its reading time (exit 1 if any is short)",
    )
    hd.add_argument("scenario", help="the scenario markdown with storyboard tables")
    hd.add_argument(
        "--section",
        help="only the section whose heading starts with this, for example 3",
    )
    hd.add_argument(
        "--profile",
        choices=sorted(HOLD_PROFILES),
        help="the card's reading pace (default display)",
    )
    for m in C.CLI_MODULES:  # subcommands owned by the gate modules (approve, diff, purity, lint, calib, ...)
        mod = _load(m, "its subcommands are missing")
        if mod is not None:
            mod.add_cli(sub)
    a = ap.parse_args()
    if getattr(a, "func", None):
        sys.exit(a.func(a))
    if a.cmd == "holds":
        name, prof = hold_profile(a.profile)
        rows = storyboard_holds(
            Path(a.scenario).read_text(encoding="utf-8"), a.section, profile=a.profile
        )
        for st, tcell, line, has, needs in rows:
            words, nchar = slot_budget(has, a.profile)
            print(
                f"{st:<6} {tcell:<14} {line[:60]!r}: about {has:.2f} s on screen, needs {needs:.2f} s; the slot fits {_n(words, 'word')}, {_n(nchar, 'character')}"
            )
        short = sum(r[0] == "SHORT" for r in rows)
        print(
            f"HOLDS: {'SHORT (' + str(short) + ')' if short else 'OK'} ({len(rows)} lines checked, entrance 0.4 s assumed, "
            f"{name} profile: {prof['cps']} characters a second counting spaces, plus {prof['pad']} s, at least {prof['floor']} s; "
            "to fit a slot, cut words, not reading time)"
        )
        sys.exit(1 if short else 0)
    ff = C.find_ffmpeg()
    if ff is None:
        sys.exit(
            "qa.py: no ffmpeg on PATH (nor in /opt/homebrew/bin or /usr/local/bin)"
        )
    if a.cmd == "look":
        look(
            a.video,
            [float(t) for t in a.times.split(",")] if a.times else None,
            a.width,
            a.out,
            ff=ff,
        )
        sys.exit(0)
    st = Path(a.video).stat()
    print(
        f"qa check: {a.video} (written {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))}, {st.st_size / 1e6:.1f} MB)"
    )
    base = (
        "cmd",
        "video",
        "duration",
        "fps",
        "size",
        "bpm",
        "scenes",
        "max_mb",
        "silent",
    )
    rows = check(
        a.video,
        a.duration,
        a.fps,
        a.size,
        a.bpm,
        a.scenes,
        a.max_mb,
        a.silent,
        ff=ff,
        **{k: v for k, v in vars(a).items() if k not in base},
    )
    if a.json:
        C.write_rows(rows, a.json)
        found = review_entries(rows)
        if found and a.scenes:  # only into a build folder that was named (ctx.record)
            C.add_review_times(found, Path(a.scenes, C.REVIEW_TIMES))
    per_code = {}
    for r in rows:  # a ticker or counter can make hundreds of rows of one code: print 10, keep all in --json
        per_code[r.code] = per_code.get(r.code, 0) + 1
        if per_code[r.code] <= 10:
            print(C.line(r))
    for code, n in per_code.items():
        if n > 10:
            print(f"     {n - 10} more {code} rows like these (every row is in --json)")
    print(C.summary(rows))
    if not a.scenes:
        print(
            "not checked here: safe area, overlap, contrast, reading holds and cue sync (pass --scenes . with a "
            "text_items(t) registry and CUES in scenes.py)"
        )
    print(
        "not checked by any script: how it looks and sounds to a person (the reviewer looks; nobody has listened)"
    )
    sys.exit(C.exit_code(rows))
