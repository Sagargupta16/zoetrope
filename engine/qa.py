# qa.py : the gates in references/qa-gates.md as functions. Each returns numbers; print a pass/fail table from them.
# CLI: `python qa.py check out.mp4 --scenes . --size 1920x1080` prints coded findings and exits 1 on any FIX;
#      `python qa.py look out.mp4` writes small frame copies plus review/look.jpg for a model to view.
import json
import re
import subprocess
import sys
import time
from pathlib import Path

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


def min_hold(words):
    """Shortest allowed hold for a text block: 0.5 s + 0.3 s per word, at least 1 s (gate 4)."""
    return max(1.0, 0.5 + 0.3 * words)


def first_frame(draw):
    """(ok, mean, std) of frame 0 in grey; dark or blank fails (gate 5)."""
    a = np.asarray(draw(0.0).convert("L"), float)
    return bool(a.mean() > 25 and a.std() > 12), float(a.mean()), float(a.std())


def _flashes(L, fps):
    d = np.abs(np.diff(L)) > 20  # big luminance jump between frames
    return [
        (s / fps, int(d[s : s + fps].sum() // 2))
        for s in range(0, len(d), fps)
        if d[s : s + fps].sum() // 2 > 3
    ]


def flash_report(draw, dur, fps=30):
    """(second, flashes) for every second with more than 3 flashes, from draw(t) (gate 6)."""
    L = np.array(
        [
            np.asarray(draw(i / fps).convert("L").resize((64, 36)), float).mean()
            for i in range(int(dur * fps))
        ]
    )
    return _flashes(L, fps)


def flash_window(draw, t0, t1, fps=30):
    """Gate 6 on drawn frames for one passage (a wipe, a hit) before the film is rendered:
    ([(second, flashes)] for seconds over 3, biggest frame-to-frame jump in /255)."""
    L = np.array(
        [
            np.asarray(draw(i / fps).convert("L").resize((64, 36)), float).mean()
            for i in range(int(t0 * fps), int(t1 * fps) + 1)
        ]
    )
    jumps = np.abs(np.diff(L))
    return [(round(t0 + s, 2), n) for s, n in _flashes(L, fps)], float(
        jumps.max()
    ) if len(jumps) else 0.0


def storyboard_holds(md_text, section=None, entrance=0.4):
    """Planning check on a scenario's storyboard tables: each quoted on-screen line gets its slot (an explicit
    "(a-b)" after the line, else an equal share of its row's time), minus an entrance; returns rows of
    (status, row time, line, has, needs). Lines joined by " / " are shown together and read as one block."""
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
                needs = min_hold(sum(len(s.split()) for s in g["lines"]))
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


def flash_report_file(path, fps=30, ff="ffmpeg"):
    """The same flash test on an encoded file, frames read with ffmpeg at 64x36 grey (gate 6)."""
    raw = subprocess.run(
        [
            ff,
            "-v",
            "error",
            "-i",
            path,
            "-vf",
            "scale=64:36,format=gray",
            "-f",
            "rawvideo",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    L = np.frombuffer(raw, np.uint8).reshape(-1, 36 * 64).mean(1)
    return _flashes(L, fps)


def probe(path):
    """Duration, size, resolution, fps, codecs and frame count from ffprobe (gate 7)."""
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path]
    )
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
    )


def loud(path, ff="ffmpeg"):
    """Integrated loudness (LUFS), LRA (LU) and true peak (dBFS) from ebur128 (gate 8)."""
    r = subprocess.run(
        [
            ff,
            "-hide_banner",
            "-nostdin",
            "-i",
            path,
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    ).stderr
    s = r[r.rfind("Summary:") :]
    num = lambda pat: float(re.search(pat, s).group(1))  # noqa: E731
    return dict(
        I=num(r"I:\s+(-?[\d.]+) LUFS"),
        LRA=num(r"LRA:\s+(-?[\d.]+) LU"),
        peak=num(r"Peak:\s+(-?[\d.]+) dBFS"),
    )


def snap_ok(t_cut, bpm, fps=30, tol_frames=1):
    """Cut time within tol_frames of the nearest beat (gate 9)."""
    beat = 60 / bpm
    nearest = round(t_cut / beat) * beat
    return abs(t_cut - nearest) * fps <= tol_frames


def _raw(path, args, dtype):
    cmd = ["ffmpeg", "-v", "error", "-i", path, *args, "-"]
    return np.frombuffer(
        subprocess.run(cmd, capture_output=True, check=True).stdout, dtype
    )


FULL = (
    0.98  # alpha at or above this counts as "at rest" for holds, safe area and overlap
)


def _rgb(c):
    if isinstance(c, str):
        h = c.lstrip("#")
        return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
    return tuple(c[:3])


def _shrink(b, k=1):
    return (b[0] + k, b[1] + k, b[2] - k, b[3] - k)


def text_frames(scenes, fps):
    """[(t, items), ...] for every frame, from scenes.text_items(t) (the registry; see qa-gates.md)."""
    n = int(round(scenes.DURATION * fps))
    return [(i / fps, scenes.text_items(i / fps)) for i in range(n)]


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


def text_gates(scenes, W, H, fps):
    """Gates 2 to 4 from the text registry: Q201 safe area, Q202 overlap at rest, Q203 overlap in a transition,
    Q301 contrast, Q401 reading hold, Q402 key text size."""
    rows = []

    def add(ok, code, msg, fix, note=False):
        rows.append(
            ("PASS" if ok else "NOTE" if note else "FIX", code, msg, "" if ok else fix)
        )

    frames = text_frames(scenes, fps)
    scale = 1080 / min(W, H)  # the size rules are written for 1080 px on the short side
    out, rest, trans = {}, {}, {}
    for t, items in frames:
        vis = [
            it for it in items if it.get("alpha", 1) > 0.05 and not it.get("texture")
        ]
        for it in vis:
            if it.get("alpha", 1) >= FULL and not inside(it["box"], W, H):
                out.setdefault(it["s"], round(t, 2))
        for i in range(len(vis)):
            for j in range(i + 1, len(vis)):
                a, b = vis[i], vis[j]
                if a["s"] == b["s"] or not overlap(
                    _shrink(a["box"]), _shrink(b["box"])
                ):
                    continue
                both = a.get("alpha", 1) >= FULL and b.get("alpha", 1) >= FULL
                (rest if both else trans).setdefault((a["s"], b["s"]), round(t, 2))
    ex = lambda d: "; ".join(
        f"{k if isinstance(k, str) else ' / '.join(k)!r} at {v} s"
        for k, v in list(d.items())[:3]
    )  # noqa: E731
    add(
        not out,
        "Q201",
        f"text outside the 4% safe area: {len(out)} ({ex(out) or 'none'})",
        "move or shrink it inside the safe area",
    )
    add(
        not rest,
        "Q202",
        f"text overlapping at rest: {len(rest)} ({ex(rest) or 'none'})",
        "move one, or stagger the exit before the entry",
    )
    add(
        not trans,
        "Q203",
        f"text overlapping during a transition: {len(trans)} ({ex(trans) or 'none'})",
        "fade the old text out before the new one fades in; never crossfade two strings in one spot",
    )

    spans = text_spans(frames)
    short, low, small = [], [], []
    for s, sp in spans.items():
        a, b = max(sp, key=lambda x: x[1] - x[0])
        need = min_hold(len(s.split()))
        if b - a + 1e-6 < need:
            short.append(f"{s!r} {b - a:.2f}/{need:.2f} s")
        tm = round(((a + b) / 2) * fps) / fps
        it = next((x for x in scenes.text_items(tm) if x["s"] == s), None)
        if it is None or "fg" not in it:
            continue
        px = it.get("px")
        large = px is not None and (
            px * scale >= 36 or (px * scale >= 24 and it.get("bold", False))
        )
        arr = np.asarray(scenes.draw(tm).convert("RGB"))
        ratio = contrast(_rgb(it["fg"]), ring_bg(arr, it["box"]))
        need_c = 3.0 if large else 4.5
        if ratio < need_c:
            low.append(f"{s!r} {ratio:.2f}:1 (needs {need_c}) at {tm:.2f} s")
        if px is not None and px * scale < 36:
            small.append(f"{s!r} {px * scale:.0f} px")
    add(
        not short,
        "Q401",
        f"reading holds under 0.5 s + 0.3 s per word: {len(short)} ({'; '.join(short[:3]) or 'none'})",
        "cut words, lengthen the slot, or let the line stay through the next beat",
    )
    add(
        not low,
        "Q301",
        f"text under its contrast minimum: {len(low)} ({'; '.join(low[:3]) or 'none'})",
        "darken the text tint, add a halo or scrim, or move it off the busy area",
    )
    add(
        not small,
        "Q402",
        f"key text under 36 px at 1080: {len(small)} ({'; '.join(small[:3]) or 'none'})",
        "mark it texture=True if nobody must read it, else enlarge it",
        note=True,
    )
    return rows


def cue_gates(scenes, a8k, g, fps):
    """Q902: each entry in scenes.CUES lands in the audio within one frame and in the picture within the allowed lag.
    CUES entries are (t, label) or (t, label, kind) with kind "both", "audio" or "picture"; CUE_LAG is the number
    of frames the picture may trail its cue by design (default 0)."""
    lag = getattr(scenes, "CUE_LAG", 0)
    w = 80  # 10 ms windows at 8 kHz
    m = len(a8k) // w
    e = 10 * np.log10((a8k[: m * w].reshape(m, w) ** 2).mean(1) + 1e-10)
    prev = (
        np.max(
            np.stack(
                [
                    np.concatenate([np.full(k, e[0] if m else 0), e[:-k]])
                    for k in (1, 2, 3)
                ]
            ),
            0,
        )
        if m > 3
        else e
    )
    rise = (
        e - prev
    )  # dB above the loudest of the previous 30 ms: noise flicker inside a whoosh stays small
    d = np.abs(np.diff(g, axis=0)).mean(1)  # d[i] = change from frame i to i+1

    def nearest(strength, lo, hi, centre, floor):
        """Index of the strong peak nearest the cue: strong = at least half the window's best and above floor."""
        seg = strength[lo:hi]
        if not len(seg) or seg.max() < floor:
            return None
        cand = np.where(seg >= max(floor, 0.5 * seg.max()))[0] + lo
        return int(cand[np.argmin(np.abs(cand - centre))])

    bad, worst = [], 0.0
    for cue in scenes.CUES:
        t, label = cue[0], cue[1] if len(cue) > 1 else ""
        kind = cue[2] if len(cue) > 2 else "both"
        if kind in ("both", "audio") and m > 3:
            i = nearest(
                rise,
                max(0, int((t - 0.1) / 0.01)),
                min(m, int((t + 0.1) / 0.01) + 1),
                t / 0.01,
                3.0,
            )
            if i is None:
                bad.append(f"{label or t} no audio onset within 100 ms")
            else:
                da = i * 0.01 - t
                worst = max(worst, abs(da))
                if abs(da) > 1 / fps:
                    bad.append(f"{label or t} audio {da * 1000:+.0f} ms")
        if kind in ("both", "picture") and len(d):
            fi = round(t * fps)
            j = nearest(d, max(0, fi - 4), min(len(d), fi + lag + 3), fi - 1, 2.0)
            if j is None:
                bad.append(f"{label or t} no picture change near the cue")
            else:
                dp = j + 1 - fi
                if dp < -1 or dp > lag + 1:
                    bad.append(f"{label or t} picture {dp:+d} frames")
    return [
        (
            "NOTE" if bad else "PASS",
            "Q902",
            f"cues off their audio or picture: {len(bad)} of {len(scenes.CUES)} ({'; '.join(bad[:4]) or 'none'}); worst audio offset {worst * 1000:.0f} ms",
            "move the sound or the motion onto the cue time (place SFX by their measured peak: synth.put_peak)"
            if bad
            else "",
        )
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
):
    """Every gate measurable on the final file, as (status, code, message, fix) rows. Status is PASS, FIX or NOTE."""
    rows = []

    def add(ok, code, msg, fix, note=False):
        rows.append(
            ("PASS" if ok else "NOTE" if note else "FIX", code, msg, "" if ok else fix)
        )

    p = probe(path)
    n, d = (int(x) for x in p["fps"].split("/"))
    rate = n / d
    sched = scn = a = None
    if (
        scenes_dir
    ):  # SCHEDULE, DURATION and an optional BPM from the video's own scenes.py
        sys.path.insert(0, str(scenes_dir))
        import engine as E

        E.W, E.H, E.FPS = p["w"], p["h"], round(rate)
        import scenes

        scn = scenes
        sched, duration = scenes.SCHEDULE, duration or scenes.DURATION
        bpm = bpm or getattr(scenes, "BPM", None)

    if duration:
        add(
            abs(p["duration"] - duration) <= 0.1,
            "Q701",
            f"duration {p['duration']:.2f} s (want {duration:.2f} +/- 0.10)",
            "trim or pad the audio with -shortest, or fix DURATION",
        )
    if fps:
        add(
            abs(rate - fps) < 0.01,
            "Q702",
            f"fps {rate:g} (want {fps:g})",
            "encode with -framerate and -r set to E.FPS",
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
        )
    if p["vcodec"] == "h264":
        add(
            p["pix"] == "yuv420p",
            "Q705",
            f"pixel format {p['pix']}",
            "encode with -pix_fmt yuv420p",
        )
    if not silent:
        add(
            p["acodec"] is not None,
            "Q706",
            f"audio stream {p['acodec']}",
            "mux mix.wav into the encode, or pass --silent for a silent piece",
        )
    if p["acodec"] and not silent:
        L = loud(path)
        add(
            abs(L["I"] + 14) <= 1,
            "Q801",
            f"loudness {L['I']} LUFS (want -14 +/- 1)",
            "rerun audio.master on the raw mix, then re-encode",
        )
        a = _raw(path, ["-vn", "-ac", "1", "-ar", "8000", "-f", "f32le"], np.float32)
        peak_t = int(np.argmax(np.abs(a))) / 8000 if len(a) else 0.0
        add(
            L["peak"] <= -1.0,
            "Q802",
            f"true peak {L['peak']} dBTP (want <= -1); loudest moment at {peak_t:.2f} s",
            f"lower the hits stacked at {peak_t:.2f} s before the master, then rerun audio.master (TP -1.5)",
        )
        secs = len(a) // 8000
        db = 20 * np.log10(
            np.sqrt((a[: secs * 8000].reshape(secs, 8000) ** 2).mean(1)) + 1e-9
        )
        quiet = [s for s in range(1, secs - 1) if db[s] < -60]
        add(
            not quiet,
            "Q803",
            f"near-silent seconds inside the piece: {quiet or 'none'}",
            "fine if planned (a glitch, a think pause); otherwise check the mix",
            note=True,
        )

    hw = round(480 * p["h"] / p["w"] / 2) * 2
    f0 = _raw(
        path,
        ["-frames:v", "1", "-vf", f"scale=480:{hw},format=gray", "-f", "rawvideo"],
        np.uint8,
    ).astype(float)
    add(
        f0.mean() > 25 and f0.std() > 12,
        "Q501",
        f"first frame mean {f0.mean():.1f}, std {f0.std():.1f} (want > 25 and > 12)",
        "draw the hook fully at t=0; animate only the extras",
    )
    g = (
        _raw(path, ["-vf", "scale=64:36,format=gray", "-f", "rawvideo"], np.uint8)
        .reshape(-1, 36 * 64)
        .astype(float)
    )
    add(
        g[-1].mean() > 25,
        "Q502",
        f"last frame mean {g[-1].mean():.1f} (want > 25)",
        "hold the end card instead of fading to black",
    )
    k = min(len(g) - 1, round(rate))
    held = np.abs(g[-1 - k] - g[-1]).mean()
    add(
        held < 10,
        "Q503",
        f"last 1 s change {held:.1f}/255 (want < 10: end card held)",
        "give the end card at least 1 s of hold",
        note=True,
    )
    bad = _flashes(g.mean(1), round(rate))
    add(
        not bad,
        "Q601",
        f"seconds over 3 flashes: {bad or 'none'}",
        "fewer flips, softer swings, or stretch the flash over more frames",
    )
    if sched and bpm:
        off = [
            round(a, 3)
            for a, _ in sched.values()
            if a > 0 and not snap_ok(a, bpm, rate)
        ]
        add(
            not off,
            "Q901",
            f"scene starts off the {bpm:g} BPM grid: {off or 'none'}",
            "snap scene starts to beats (strong cuts to bar lines)",
            note=True,
        )
    if scn is not None and hasattr(scn, "text_items"):
        rows += text_gates(scn, p["w"], p["h"], round(rate))
    elif scn is not None:
        rows.append(
            (
                "NOTE",
                "Q200",
                "scenes.py has no text_items(t), so gates 2 to 4 did not run",
                "add the text registry (references/qa-gates.md)",
            )
        )
    if scn is not None and getattr(scn, "CUES", None) and a is not None:
        rows += cue_gates(scn, a, g, round(rate))
    add(
        max_mb is None or p["size_mb"] <= max_mb,
        "Q1001",
        f"file size {p['size_mb']:.1f} MB" + (f" (limit {max_mb:g})" if max_mb else ""),
        "raise CRF to 20, drop grain, or go 720p",
    )
    mbps = p["size_mb"] * 8 / max(p["duration"], 1e-6)
    add(
        mbps <= 12,
        "Q1002",
        f"bitrate {mbps:.1f} Mb/s (flat graphics land at 1 to 5)",
        "baked grain is the usual cause: grain std 1.6 or less and CRF 20 (formats.md)",
        note=True,
    )
    return rows


def look(path, times=None, width=480, out="review", cols=4):
    """Small JPEG copies of frames at times (default every 5 s plus the last frame) and one review/look.jpg sheet."""
    p = probe(path)
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
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-ss",
                str(t),
                "-i",
                path,
                "-frames:v",
                "1",
                "-vf",
                f"scale={width}:-2",
                str(f),
            ],
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


if __name__ == "__main__":
    import argparse

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
    a = ap.parse_args()
    if a.cmd == "holds":
        rows = storyboard_holds(Path(a.scenario).read_text(encoding="utf-8"), a.section)
        for st, tcell, line, has, needs in rows:
            if st == "SHORT":
                print(
                    f"SHORT  {tcell:<14} {line[:70]!r}: about {has:.2f} s on screen, needs {needs:.2f} s"
                )
        short = sum(r[0] == "SHORT" for r in rows)
        print(
            f"HOLDS: {'SHORT (' + str(short) + ')' if short else 'OK'} ({len(rows)} lines checked, entrance 0.4 s assumed)"
        )
        sys.exit(1 if short else 0)
    if a.cmd == "look":
        look(
            a.video,
            [float(t) for t in a.times.split(",")] if a.times else None,
            a.width,
            a.out,
        )
        sys.exit(0)
    st = Path(a.video).stat()
    print(
        f"qa check: {a.video} (written {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))}, {st.st_size / 1e6:.1f} MB)"
    )
    rows = check(
        a.video, a.duration, a.fps, a.size, a.bpm, a.scenes, a.max_mb, a.silent
    )
    for status, code, msg, fix in rows:
        print(f"{status:<4} {code:<5} {msg}" + (f" -> {fix}" if fix else ""))
    nfix = sum(r[0] == "FIX" for r in rows)
    nnote = sum(r[0] == "NOTE" for r in rows)
    print(
        f"QA: {'FIX' if nfix else 'PASS'} ({len(rows)} checks, {nfix} FIX, {nnote} NOTE)"
    )
    if not any(r[1].startswith(("Q2", "Q3", "Q4")) and r[1] != "Q200" for r in rows):
        print(
            "not checked here: safe area, overlap, contrast, reading holds (pass --scenes . with a text_items(t) registry in scenes.py)"
        )
    print(
        "not checked by any script: how it looks and sounds to a person (the reviewer looks; nobody has listened)"
    )
    sys.exit(1 if nfix else 0)
