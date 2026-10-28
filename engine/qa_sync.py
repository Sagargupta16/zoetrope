# qa_sync.py : cue sync (Q902), the mux check (Q903) and the flash-and-blip calibration (Q906), numpy only.
# Q902 finds each cue's own sound on the lossless SFX stem by cross-correlation, so peak, end and pad cues are measured
# where they sit, not taken from the sheet; Q903 holds the decoded mp4 audio against mix.wav; `qa.py calib` sends one
# white frame and a one-frame 1 kHz blip through audio.master and contract.mux_cmd and reads both back.
import json
import math
import subprocess
import wave
from pathlib import Path

import contract as C
import numpy as np

# Q902 window in ms, positive = sound late. FIX: late by more than one frame (never more than 60 ms at any fps) or
# early by more than 40 ms. NOTE: outside -5..+15 ms. The numbers echo EBU R37, which is about lip sync on broadcast
# chains; for SFX cues that is an analogy, so the late FIX stays at one frame instead of R37's 60 ms.
EARLY, CEILING, NOTE_LO, NOTE_HI = -40.0, 60.0, -5.0, 15.0
# search +-250 ms; a peak within 4 ms of the window edge is no match; band 250 Hz to 9 kHz
SEARCH, GUARD, BAND = 0.25, 0.004, (250.0, 9000.0)
# a placed sound is found at a normalised correlation of 0.7 or more, on the stem or, when recorded neighbours overlap
# it, on the stem with them taken out. At 0.3 an absent 20 ms tick was "found" in 53 of 100 random stems (review R4
# finding 4); after isolation no absent tick of 240 reached 0.7, and present ones had p10 0.78
MATCH = 0.7
TWIN = 0.9  # two buffers this alike (same length within 1 percent) are one sound to the search: measured as a group
NEAR = 0.1  # an unlabelled sheet entry serves the cue it sits within 100 ms of
# the audible attack of a sound placed by its start or onset: where it first reaches -15 dB of its sustained level;
# it replaces the landmark when it comes 5 ms or more after it (a slow pad placed with put() is heard late)
ATTACK_DB, ATTACK_TOL = -15.0, 0.005
# the decoded file confirms a cue within +-20 ms of its stem position, may move it 2 ms, and needs match 0.5; a
# second peak within 0.01 of the best more than 0.5 ms away is a tonal comb (a bell's peaks 4.55 ms apart), no confirm
CONFIRM, CONFIRM_MATCH, CONFIRM_SEARCH, CONFIRM_COMB = 2.0, 0.5, 0.02, 0.01
# the no-cue-sheet detector: a 3 dB rise in 10 ms windows, on the whole mix or above 2 kHz, whichever rises more; a
# picture change is the share of pixels moving more than 12 levels on the 192x108 grey, 0.2 percent or more
RISE_DB, RISE_HP, PIX_LEVEL, PIX_SHARE = 3.0, 2000.0, 12, 0.2
# Q903: 2 s windows at 12, 45 and 85 percent, +-0.1 s, 500 Hz high-pass, FIX past 1 ms; when no window matches, again
# over +-1 s, where a match of 0.8 or more is a lag (review R4 finding 5: 98 ms read as a stale mix.wav)
MUX_AT, MUX_HALF, MUX_SEARCH, MUX_HP, MUX_MAX = (0.12, 0.45, 0.85), 1.0, 0.1, 500.0, 1.0
MUX_WIDE, MUX_WIDE_MATCH = 1.0, 0.8


# ---- signal helpers ----


def read_wav(path):
    """(mono float64, sr) of a PCM (8 to 32 bit) or float WAV, channels averaged, full scale 1.0. The stdlib wave
    module cannot read float files, and an ffmpeg decode could resample."""
    b = Path(path).read_bytes()
    i, fmt, data = 12, b"", b""
    while i + 8 <= len(b):
        cid, size = b[i : i + 4], int.from_bytes(b[i + 4 : i + 8], "little")
        if cid == b"fmt ":
            fmt = b[i + 8 : i + 8 + size]
        elif cid == b"data":
            data = b[i + 8 : i + 8 + size]
        i += 8 + size + (size & 1)
    tag, ch, sr = (
        int.from_bytes(fmt[a:z], "little") for a, z in ((0, 2), (2, 4), (4, 8))
    )
    # WAVE_FORMAT_EXTENSIBLE: the real format leads the sub-format GUID
    if tag == 0xFFFE:
        tag = int.from_bytes(fmt[24:26], "little")
    k = int.from_bytes(fmt[14:16], "little") // 8
    data = data[: len(data) // (k * ch) * k * ch]
    if tag == 3:
        x = np.frombuffer(data, f"<f{k}").astype(np.float64)
    elif k == 3:
        u = np.frombuffer(data, np.uint8).reshape(-1, 3).astype(np.int32)
        x = (((u[:, 0] | u[:, 1] << 8 | u[:, 2] << 16) ^ 0x800000) - 0x800000) / 2.0**23
    elif k == 1:
        x = (np.frombuffer(data, np.uint8) - 128.0) / 128
    else:
        x = np.frombuffer(data, f"<i{k}") / 2.0 ** (8 * k - 1)
    return x.reshape(-1, ch).mean(1), sr


def take(x, i, n):
    """x[i:i + n] with zeros where it runs off either end, so a sound clipped at 0 s or at the end still lines up."""
    out = np.zeros(n)
    a, b = max(i, 0), min(i + n, len(x))
    if b > a:
        out[a - i : b - i] = x[a:b]
    return out


def ms_round(v, nd=2):
    """v rounded, and never -0.0 (a print of -0.00 ms reads as a finding)."""
    return round(v, nd) + 0.0


def ms_text(v, nd=1):
    """Signed ms for a message: +60.0, -50.0, +0.0."""
    return f"{ms_round(v, nd):+.{nd}f}"


def band(x, sr, lo=0.0, hi=None):
    """x with every rfft bin outside lo..hi Hz zeroed (a brickwall band-pass), padded to twice its length so the
    ringing does not wrap round onto the start."""
    n = len(x)
    L = 1 << (2 * n).bit_length()
    X = np.fft.rfft(x, L)
    f = np.fft.rfftfreq(L, 1 / sr)
    X[(f < lo) | (f > (hi or sr / 2))] = 0
    return np.fft.irfft(X, L)[:n]


def resample(x, sr0, sr1):
    """x from sr0 to sr1 by FFT (band-limited, no phase shift), zero-padded by a whole number of samples at both
    rates so the edges neither ring nor shift."""
    if sr0 == sr1:
        return np.asarray(x, np.float64)
    unit = sr0 // math.gcd(sr0, sr1)
    p0 = unit * max(1, round(0.01 * sr0 / unit))
    p1 = p0 * sr1 // sr0
    y = np.concatenate([np.zeros(p0), x, np.zeros(p0)])
    n1 = round(len(y) * sr1 / sr0)
    Y = np.zeros(n1 // 2 + 1, complex)
    X = np.fft.rfft(y)
    k = min(len(X), len(Y))
    Y[:k] = X[:k]
    return np.fft.irfft(Y, n1)[p1 : p1 + round(len(x) * sr1 / sr0)] * (n1 / len(y))


def ncc(tpl, seg):
    """Normalised cross-correlation of tpl at every offset k of seg, k = 0 .. len(seg) - len(tpl): 1.0 is an exact
    copy at any gain. The denominator is the energy of seg under tpl, so a quiet copy beside loud neighbours scores."""
    n, m = len(tpl), len(seg)
    L = 1 << (n + m).bit_length()
    c = np.fft.irfft(np.fft.rfft(seg, L) * np.conj(np.fft.rfft(tpl, L)), L)[: m - n + 1]
    e = np.concatenate([[0.0], np.cumsum(seg * seg)])
    local = e[n:] - e[: m - n + 1]
    # silence scores 0, not rounding noise over rounding noise
    local = np.maximum(local, 1e-9 * local.max() + 1e-30)
    return c / np.sqrt((tpl * tpl).sum() * local)


def peak(r, centre, guard, tie=1e-9):
    """(sub-sample index of r's maximum, on_edge). Peaks within tie of the best go to the one nearest centre: an
    exact tie is two clean copies of one sound. A near tie is not broken this way (a tonal comb's nearest tooth is
    not its shift: correlate(comb=) refuses those). on_edge: it sits within guard samples of an end, so the true peak
    may lie outside the window."""
    top = r.max()
    cand = np.flatnonzero(r >= top - tie)
    k = int(cand[np.argmin(np.abs(cand - centre))])
    # climb to the local maximum
    while 0 < k < len(r) - 1 and max(r[k - 1], r[k + 1]) > r[k]:
        k += 1 if r[k + 1] > r[k - 1] else -1
    if k < guard or k > len(r) - 1 - guard:
        return float(k), True
    y0, y1, y2 = r[k - 1], r[k], r[k + 1]
    den = y0 - 2 * y1 + y2
    return k + (0.5 * (y0 - y2) / den if den < 0 else 0.0), False


def correlate(x, sr, buf, start, search, lo, hi, need=MATCH, tie=1e-9, comb=None):
    """(start s or None, match, why) of the best band-limited match of buf in x within +-search s of start. When
    start is None, why says why: "weak" (the best is under need), "edge" (the best sits on the search edge), "band"
    (buf has under 1 percent of its energy in the band), "silent", or with comb set "comb": another peak within comb
    of the best sits more than 0.5 ms away, so the best is one tooth of a tonal sound's comb."""
    t = band(buf, sr, lo, hi)
    if (t * t).sum() < 0.01 * (buf * buf).sum():
        return None, 0.0, "band"
    w, pad = round(search * sr), round(0.05 * sr)
    i = C.sample_of(start, sr) - w
    seg = band(take(x, i - pad, len(buf) + 2 * w + 2 * pad), sr, lo, hi)[pad:-pad]
    if not (seg * seg).sum():
        return None, 0.0, "silent"
    r = ncc(t, seg)
    k, edge = peak(r, w, round(GUARD * sr), tie)
    v = float(r[min(len(r) - 1, round(k))])
    if edge:
        return None, v, "edge"
    if v >= need and comb is not None:
        tops = (
            np.flatnonzero((r[1:-1] >= r[:-2]) & (r[1:-1] >= r[2:])) + 1
        )  # every local maximum
        if np.any((np.abs(tops - k) > 0.0005 * sr) & (r[tops] >= v - comb)):
            return None, v, "comb"
    return (None, v, "weak") if v < need else ((i + k) / sr, v, "")


def find(
    x,
    sr,
    buf,
    start,
    search=SEARCH,
    lo=BAND[0],
    hi=BAND[1],
    wide=True,
    need=MATCH,
    tie=1e-9,
    comb=None,
):
    """(start s or None, match, why) of buf inside x near start s: correlate() in the 250 Hz to 9 kHz band and, with
    wide set (a lossless stem), from 20 Hz when the band misses: a hit whose energy sits under 250 Hz scored 0.23 in
    the band under a whoosh's crest. Never wide on a limited or lossy copy, where a low tone can match a whole
    period off (measured: hit() through the HEAD master read +133 ms full band, +4.0 ms in band)."""
    got = correlate(x, sr, buf, start, search, lo, hi, need, tie, comb)
    if got[0] is None and wide and lo > 20.0:
        full = correlate(x, sr, buf, start, search, 20.0, hi, need, tie, comb)
        if full[0] is not None or full[1] > got[1]:
            return full
    return got


def locate(x, sr, buf, start, search=SEARCH, lo=BAND[0], hi=BAND[1], wide=True):
    """(start s or None, match): find() without its reason."""
    return find(x, sr, buf, start, search, lo, hi, wide)[:2]


def onset(x, sr, t, win=0.03):
    """First sharp rise within win s of t on x: the first 1 ms block at least 6 dB over the loudest block of the
    20 ms before it and within 30 dB of the loudest of the next 100 ms; None when no block qualifies. It reads the
    stem only, so an onset cue's recorded landmark_s is checked against the sound itself."""
    b = max(1, round(0.001 * sr))
    nw = round(2 * win * 1000)
    i0 = C.sample_of(t - win, sr) - 20 * b
    e = 10 * np.log10((take(x, i0, b * (nw + 121)).reshape(-1, b) ** 2).mean(1) + 1e-12)
    for k in range(20, 21 + nw):
        if e[k] >= e[k - 20 : k].max() + 6 and e[k] >= e[k : k + 100].max() - 30:
            return (i0 + k * b) / sr
    return None


def attack_of(buf, sr):
    """Seconds from a sound's first sample to its audible attack: the middle of the first 5 ms window within -15 dB
    of its sustained level, the 90th percentile of its 5 ms windows over the first second after its onset (Vos and
    Rasch put the perceived onset of a slow rise near -15 dB). Percussive sounds read 2.5 ms, the first window. A
    0.25 s pad reads 21 to 86 ms by chord (detuned saws start in phase, so the waveform rises faster than the ramp's
    44.5 ms): an estimate, used to show a slow attack, not to place one."""
    x = np.asarray(buf, np.float64)
    w = round(0.005 * sr)
    if len(x) <= w or not x.any():
        return 0.0
    c = np.concatenate([[0.0], np.cumsum(x * x)])
    e = (c[w:] - c[:-w]) / w
    on = int(np.argmax(e >= e.max() * 1e-3))
    ref = np.percentile(e[on : on + sr], 90)
    return (int(np.argmax(e[on:] >= ref * 10 ** (ATTACK_DB / 10))) + on + w / 2) / sr


def same_sound(a, b):
    """True when buffers a and b are one sound to the search: lengths within 1 percent and a normalised
    cross-correlation of TWIN or more at their best lag. Two placements of one buffer always are; ticks with other
    seeds, plucks at other pitches, a kick beside a snare are not (review R4 finding 1: twins went by name)."""
    if a is b:
        return True
    if abs(len(a) - len(b)) > 0.01 * max(len(a), len(b)):
        return False
    na, nb = np.sqrt((a * a).sum()), np.sqrt((b * b).sum())
    if not na or not nb:
        return False
    L = 1 << (len(a) + len(b)).bit_length()
    c = np.fft.irfft(np.fft.rfft(a, L) * np.conj(np.fft.rfft(b, L)), L)
    return float(c.max()) / (na * nb) >= TWIN


def strong(s, lo, hi, centre, floor):
    """Index of the strong peak of s[lo:hi] nearest centre: at least half the window's best and above floor."""
    seg = s[lo:hi]
    if not len(seg) or seg.max() < floor:
        return None
    cand = np.where(seg >= max(floor, 0.5 * seg.max()))[0] + lo
    return int(cand[np.argmin(np.abs(cand - centre))])


def grey(ctx):
    """ctx.grey() (n, 108, 192), or no frames when the file has no video stream (the audio strip runs on mix.wav at
    the proof stage): the picture side is then not measured."""
    if not ctx.probe.get("vcodec"):
        return np.zeros((0, 108, 192), np.float32)
    return ctx.grey()


def frame_change(g, box=None):
    """Percent of pixels moving more than 12 levels between neighbouring frames of a (n, h, w) grey stack, inside box
    (x0, y0, x1, y1 in g's pixels) when given: element i is the change from frame i to i + 1. A share, not a mean,
    so a small moving part (a gear, an outline) counts (calibration c2: the mean read 1 of 20 cues, this 11)."""
    g = np.asarray(g, np.float32)
    if box is not None and g.ndim == 3:
        x0, y0, x1, y1 = (round(v) for v in box)
        g = g[:, max(0, y0) : max(y0 + 1, y1), max(0, x0) : max(x0 + 1, x1)]
    g = g.reshape(len(g), -1)
    return (np.abs(np.diff(g, axis=0)) > PIX_LEVEL).mean(1) * 100


def picture_lag(d, t, fps, lag, floor=PIX_SHARE):
    """Frames from the cue frame to the strong picture change nearest it (d[i] = change from frame i to i + 1),
    searched from 4 frames before to CUE_LAG + 2 after; None when the picture does not change there."""
    fi = C.frame_of(t, fps)
    j = strong(d, max(0, fi - 4), min(len(d), fi + lag + 3), fi - 1, floor)
    return None if j is None else j + 1 - fi


def picture_status(pf, lag):
    """ok, late, early or missing for a picture change pf frames from its cue, against CUE_LAG + 1 frames."""
    if pf is None:
        return "missing"
    return "late" if pf > lag + 1 else "early" if pf < -1 else "ok"


def element_box(scenes, t, fps, lag):
    """The box (output pixels) of what the text registry says changes across a cue: every item that appears, leaves,
    moves more than 4 px or fades by half between the frame before the cue and CUE_LAG + 1 frames after it, joined.
    None when nothing there changes or text_items(t) is missing or not in the 2.2.0 form."""
    items = getattr(scenes, "text_items", None)
    if items is None:
        return None
    fi = C.frame_of(t, fps)
    try:
        before = {it["s"]: it for it in items((fi - 1) / fps)}
        after = {it["s"]: it for it in items((fi + lag + 1) / fps)}
        boxes = []
        for s in set(before) | set(after):
            a, b = before.get(s), after.get(s)
            moved = (
                a is None
                or b is None
                or abs(a.get("alpha", 1.0) - b.get("alpha", 1.0)) > 0.5
                or max(abs(p - q) for p, q in zip(a["box"], b["box"])) > 4
            )
            boxes += [it["box"] for it in (a, b) if moved and it is not None]
    except (KeyError, TypeError, ValueError, AttributeError, IndexError):
        return None
    if not boxes:
        return None
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def scaled(box, g, size):
    """A box in output pixels scaled to the grey stack, or None."""
    if box is None or g.ndim != 3 or not size or not size[0]:
        return None
    sx, sy = g.shape[2] / size[0], g.shape[1] / size[1]
    return box[0] * sx, box[1] * sy, box[2] * sx, box[3] * sy


def measure_picture(r, c, g, d, fps, lag, size, scenes=None):
    """The picture side of one cue into r: picture_frames and picture_bad, measured on the cue's region=(x0, y0, x1,
    y1) when its CUES entry has one, else on the registry text that changes across it, else on the whole frame.
    "not measured" on a file with no video and for a cue on the first frame (nothing comes before it); "not
    measurable" when only the whole frame was there to read and under 0.2 percent of it moves (calibration c5: 16 of
    18 cues read "no picture change" while the build's own check found every outline on its frame)."""
    if not len(g):
        r["picture"] = "not measured"
        return
    if C.frame_of(c["t"], fps) == 0:
        r["picture"] = "not measured (first frame)"
        return
    where, box = "its region", scaled(c.get("region"), g, size)
    if box is None:
        where, box = (
            "its registry text",
            scaled(element_box(scenes, c["t"], fps, lag), g, size),
        )
    if box is None:
        where = "the whole frame"
    pf = picture_lag(d if box is None else frame_change(g, box), c["t"], fps, lag)
    r["picture_frames"], r["picture_where"] = pf, where
    if pf is None and box is None:
        r["picture"] = "not measurable"
    else:
        r["picture_bad"] = pf is None or not -1 <= pf <= lag + 1


# ---- Q902 verdicts ----


def late_limit(fps):
    """Late FIX limit in ms: one frame (33.3 at 30 fps, 41.7 at 24), never above the 60 ms ceiling."""
    return min(1000 / fps, CEILING)


def verdict(ms, fps):
    """'late', 'early' or 'ok' against the FIX window, and whether ms is outside the -5..+15 ms NOTE window."""
    st = "late" if ms > late_limit(fps) else "early" if ms < EARLY else "ok"
    return st, not NOTE_LO <= ms <= NOTE_HI


RANK = {"missing": 3, "ambiguous": 3, "late": 2, "early": 2, "ok": 0}


def worse(a, b):
    """The worse of two per-sound results: missing or ambiguous, then out of the FIX window, then the NOTE window,
    then |ms|."""
    if a is None:
        return b

    def key(r):
        return RANK[r["status"]], r.get("note", False), abs(r.get("audio_ms") or 0)

    return b if key(b) > key(a) else a


def match(cues, entries):
    """{cue index: [sheet entries]}: by label, nearest in time when a label repeats; else the unlabelled entries
    nearest the cue within 100 ms, SFX bus first. Ties within 1 ms all count, so a whoosh and a hit on one cut are
    both measured."""
    labels = {c["label"] for c in cues if c["label"]}
    free = [e for e in entries if e.get("label", "") not in labels]

    def nearest(es, t):
        if not es:
            return []
        dmin = min(abs(e["t"] - t) for e in es)
        return [e for e in es if abs(e["t"] - t) <= dmin + 0.001]

    out = {}
    for i, c in enumerate(cues):
        got = nearest(
            [e for e in entries if c["label"] and e.get("label") == c["label"]], c["t"]
        )
        if not got:
            near = [e for e in free if abs(e["t"] - c["t"]) <= NEAR]
            got = nearest(
                [e for e in near if e.get("bus", "sfx") == "sfx"] or near, c["t"]
            )
        out[i] = got
    return out


# ---- placements on the stem: every recorded sound found where it really sits ----


def sheet_state(entries, sounds, sr_sheet, wavs):
    """What the placement functions share for one check: the sheet, the stems, each entry's buffer at a stem's rate
    and every placement once measured (twins as a group)."""
    return {
        "entries": entries,
        "sounds": sounds,
        "sr": sr_sheet,
        "wavs": wavs,
        "bufs": {},
        "placed": {},
    }


def stem_of(e, st):
    """The stem an entry is measured on: sfx.wav for the SFX bus when it exists, else mix_raw.wav (or None)."""
    if e.get("bus", "sfx") == "sfx" and C.SFX in st["wavs"]:
        return C.SFX
    return C.MIX_RAW if C.MIX_RAW in st["wavs"] else None


def on_stem(f, name):
    """True when entry f is heard on stem name (sfx.wav holds the SFX bus only; mix_raw.wav holds everything)."""
    return name == C.MIX_RAW or f.get("bus", "sfx") == "sfx"


def buf_of(f, st, sr):
    """Entry f's own buffer at rate sr (None when cue_sounds.npz has none), cached."""
    key = (f["i"], sr)
    if key not in st["bufs"]:
        b = st["sounds"].get(f"c{f['i']}")
        st["bufs"][key] = (
            None if b is None else resample(np.asarray(b, np.float64), st["sr"], sr)
        )
    return st["bufs"][key]


def want_of(f):
    """Where the sheet aimed an entry's first sample: t - landmark_s (start_s clips this at 0 for a trimmed head, the
    stored buffer does not)."""
    return float(f["t"]) - float(f["landmark_s"])


def twin_group(e, st, name, sr):
    """e and every placement of the same sound on its stem close enough to be taken for it (their search windows
    overlap), chained, sorted by where the sheet aimed them."""
    group, todo = [e], [e]
    while todo:
        f = todo.pop()
        bf = buf_of(f, st, sr)
        if bf is None:
            continue
        for q in st["entries"]:
            if q in group or not on_stem(q, name):
                continue
            bq = buf_of(q, st, sr)
            if (
                bq is None
                or abs(want_of(q) - want_of(f))
                > 2 * SEARCH + max(len(bf), len(bq)) / sr
            ):
                continue
            if same_sound(bf, bq):
                group.append(q)
                todo.append(q)
    return sorted(group, key=want_of)


def neighbours(skip, st, name, x, sr, t0, t1):
    """Every other recorded sound on the stem that overlaps t0..t1 s: [(buffer, start s)]. Entries already placed use
    that place; the rest are found alone (no isolation, so no recursion), or taken at the sheet's place when they
    are buried too (a whoosh under a bell): isolate() fits every gain by least squares, so a sound that is not where
    the sheet says only gets a near-zero gain there."""
    out = []
    for f in st["entries"]:
        if f in skip or not on_stem(f, name):
            continue
        b = buf_of(f, st, sr)
        if (
            b is None
            or want_of(f) - SEARCH > t1
            or want_of(f) + SEARCH + len(b) / sr < t0
        ):
            continue
        p = st["placed"].get(f["i"])
        s0 = p["start"] if p else find(x, sr, b, want_of(f))[0]
        if s0 is None:
            s0 = want_of(f)
        if s0 <= t1 and s0 + len(b) / sr >= t0:
            out.append((b, s0))
    return out


def isolate(x, sr, t0, t1, own, others):
    """x between t0 and t1 s with the other recorded sounds that overlap it taken out: others are (buffer, start s)
    at their measured places, own the same for the sound under test or None when its place is still unknown. The
    gains are fitted together by least squares, so a pan or a stale gain on the sheet does not leave a residue; a
    sound the sheet does not know stays in."""
    i0 = C.sample_of(t0, sr)
    n = C.sample_of(t1, sr) - i0
    seg = take(x, i0, n)
    cols = []
    for buf, s0 in ([own] if own else []) + others:
        col, j = np.zeros(n), C.sample_of(s0, sr) - i0
        a, b = max(0, j), min(n, j + len(buf))
        if b > a:
            col[a:b] = buf[a - j : b - j]
        cols.append(col)
    A = np.stack(cols, 1)
    g = np.linalg.lstsq(A, seg, rcond=None)[0]
    k = 1 if own else 0
    return seg - A[:, k:] @ g[k:]


def find_alone(x, sr, buf, want, search, near):
    """find() on the stem with the recorded neighbours near taken out (isolate): (start s or None, match, why)."""
    t0, t1 = want - search - 0.05, want + len(buf) / sr + search + 0.05
    i0 = C.sample_of(t0, sr)
    s0, v, why = find(
        isolate(x, sr, t0, t1, None, near), sr, buf, want - i0 / sr, search
    )
    return (None if s0 is None else s0 + i0 / sr), v, why


def place_alone(e, st, name, x, sr):
    """One sound with no twin near it: found on the stem, and when that fails (weak or on the edge) found again with
    the overlapping recorded sounds taken out."""
    buf, want = buf_of(e, st, sr), want_of(e)
    s0, v, why = find(x, sr, buf, want)
    out = {"start": s0, "match": v, "why": why, "how": "alone", "taken_out": 0}
    if s0 is None and why in ("weak", "edge"):
        span = (want - SEARCH - 0.05, want + len(buf) / sr + SEARCH + 0.05)
        near = neighbours([e], st, name, x, sr, *span)
        if near:
            s1, v1, why1 = find_alone(x, sr, buf, want, SEARCH, near)
            if s1 is not None or v1 > v:
                out.update(
                    start=s1, match=v1, why=why1, how="isolated", taken_out=len(near)
                )
    return out


def place_group(mem, st, name, x, sr):
    """Twins (one sound placed several times close together) measured together: the sum of all of them at the
    sheet's spacing is found once, which gives the group's shift even when the copies overlap or the whole group runs
    late by more than half the spacing; then each copy is refined inside half the distance to its nearest twin, with
    the others taken out. When the sum does not match (copies moved one by one) each copy is refined the same way
    around its own sheet place. A copy whose own peak is not in the inner half of its share is ambiguous, and copies
    that overlap with no group shift to go on are too."""
    w0 = want_of(mem[0])
    bufs = [buf_of(m, st, sr) for m in mem]
    offs = [C.sample_of(want_of(m) - w0, sr) for m in mem]
    comp = np.zeros(max(o + len(b) for o, b in zip(offs, bufs)))
    for m, o, b in zip(mem, offs, bufs):
        comp[o : o + len(b)] += float(m.get("gain") or 1.0) * b
    s0, v, why = find(x, sr, comp, w0)
    if s0 is None and why in ("weak", "edge"):
        span = (w0 - SEARCH - 0.05, w0 + len(comp) / sr + SEARCH + 0.05)
        near = neighbours(mem, st, name, x, sr, *span)
        if near:
            s1, v1, why1 = find_alone(x, sr, comp, w0, SEARCH, near)
            if s1 is not None or v1 > v:
                s0, v, why = s1, v1, why1
    delta = None if s0 is None else s0 - w0
    n, out = len(mem), {}
    for k, m in enumerate(mem):
        pos = want_of(m) + (delta or 0.0)
        r = min(
            SEARCH, min(abs(want_of(m) - want_of(q)) for q in mem if q is not m) / 2
        )
        rec = {
            "start": None,
            "match": v,
            "why": "ambiguous",
            "how": "group",
            "group_n": n,
            "spacing": r * 2,
        }
        rec["taken_out"] = n - 1
        if delta is not None:
            rec.update(start=pos, why="", group_ms=ms_round(delta * 1000))
        if (
            r >= 2 * GUARD + 0.001
        ):  # room to tell this copy from its twins: refine it alone
            t0, t1 = pos - r - 0.05, pos + len(bufs[k]) / sr + r + 0.05
            others = [
                (bufs[j], want_of(q) + (delta or 0.0))
                for j, q in enumerate(mem)
                if q is not m
            ]
            others += neighbours(mem, st, name, x, sr, t0, t1)
            i0 = C.sample_of(t0, sr)
            s1, v1, why1 = find(
                isolate(x, sr, t0, t1, None, others), sr, bufs[k], pos - i0 / sr, r
            )
            if s1 is not None and abs(s1 + i0 / sr - pos) <= r / 2:
                rec.update(start=s1 + i0 / sr, match=v1, why="", how="group, refined")
            else:
                gone = s1 is None and why1 == "weak"
                rec.update(start=None, match=v1, why="weak" if gone else "ambiguous")
        out[m["i"]] = rec
    return out


def placement(e, st):
    """Where entry e's sound really sits on its stem: {start (None when not found or ambiguous), match, why, how,
    taken_out, group_n}. Each placement is measured once; twins as one group."""
    if e["i"] not in st["placed"]:
        name = stem_of(e, st)
        x, sr = st["wavs"][name]
        group = twin_group(e, st, name, sr)
        if len(group) == 1:
            st["placed"][e["i"]] = place_alone(e, st, name, x, sr)
        else:
            st["placed"].update(place_group(group, st, name, x, sr))
    return st["placed"][e["i"]]


def onset_alone(x, sr, buf, start, lm, e, st, name):
    """Z02 correction 6 for an onset cue: the onset detector on the stem near the landmark, after isolate() takes
    out the other recorded sounds of the stem that overlap it. Seconds, or None."""
    t0, t1 = lm - 0.06, lm + 0.16
    i0 = C.sample_of(t0, sr)
    near = neighbours([e], st, name, x, sr, t0, t1)
    res = (
        isolate(x, sr, t0, t1, (buf, start), near)
        if near
        else take(x, i0, C.sample_of(t1, sr) - i0)
    )
    o = onset(res, sr, lm - i0 / sr)
    return None if o is None else o + i0 / sr


def file_confirm(r, buf, sr, start, cue_t, wavs, a48):
    """The decoded file's view of one placed sound (confirm only, a NOTE at most): the sound itself within +-20 ms of
    its stem position, else 200 ms of mix_raw.wav around the cue (the sound buried under music in the file, or a
    tonal sound whose match is a comb of near-equal peaks: a 2.5 s bell read -2.06 ms on a +4.0 ms master shift by
    the nearest tooth). No confirm when the window combs too."""
    kw = {
        "search": CONFIRM_SEARCH,
        "wide": False,
        "need": CONFIRM_MATCH,
        "comb": CONFIRM_COMB,
    }
    s2, v2, why2 = find(a48, 48000, resample(buf, sr, 48000), start, **kw)
    r["file_ms"], r["file_how"], r["file_match"] = (
        None,
        "comb" if why2 == "comb" else "sound",
        round(v2, 3),
    )
    if s2 is not None:
        r["file_ms"] = ms_round((s2 - start) * 1000)
    elif C.MIX_RAW in wavs:
        raw, srr = wavs[C.MIX_RAW]
        i = C.sample_of(cue_t - 0.1, srr)
        s3, v3, _ = find(
            a48,
            48000,
            resample(take(raw, i, C.sample_of(0.2, srr)), srr, 48000),
            i / srr,
            **kw,
        )
        if s3 is not None:
            r["file_ms"] = ms_round((s3 - i / srr) * 1000)
            r["file_how"], r["file_match"] = "mix window", round(v3, 3)


def measure_entry(e, st, cue_t, fps, a48):
    """One placed sound: where it really sits on its stem, the instant it is heard against the cue (its landmark,
    or its audible attack when it was placed by its start or onset and the attack comes later), the onset confirm
    for onset cues and the confirm on the decoded file."""
    name = stem_of(e, st)
    sound = e.get("sound") or "sound"
    if name is None:
        return {
            "status": "missing",
            "why": f"no {C.SFX} or {C.MIX_RAW} to find {sound} on",
        }
    x, sr = st["wavs"][name]
    buf = buf_of(e, st, sr)
    if buf is None:
        return {
            "status": "missing",
            "why": f"{C.CUE_SOUNDS} has no c{e['i']} ({sound})",
        }
    p = placement(e, st)
    base = {
        "sound": sound,
        "stem": name,
        "match": round(p["match"], 3),
        "how": p["how"],
    }
    if p["start"] is None:
        want, v = want_of(e), p["match"]
        why = {
            "edge": f"its best match ({v:.2f}) sits on the +-{SEARCH * 1000:.0f} ms search edge: more than that off,"
            " or not there",
            "band": f"it has no energy {BAND[0]:.0f} Hz to {BAND[1] / 1000:.0f} kHz",
            "silent": f"{name} is silent there",
            "ambiguous": f"it is one of {p.get('group_n')} copies of one sound {p.get('spacing', 0) * 1000:.0f} ms"
            " apart and its own peak is not in the middle of its share",
        }.get(p["why"], f"best match {v:.2f}, under {MATCH}")
        status = "ambiguous" if p["why"] == "ambiguous" else "missing"
        return {
            **base,
            "status": status,
            "why": f"the sheet places {sound} at {want:.3f} s but {name}: {why}",
        }
    start, align, landmark = (
        p["start"],
        e.get("align") or "onset",
        float(e["landmark_s"]),
    )
    lm = start + landmark
    heard, attack = lm, None
    # review R4 finding 2: a slow attack placed by its start or onset is heard late. The sheet's audible_s (the
    # generator's own attack point, recorded by synth.place) when it has one, else the estimate from the buffer
    if align in ("start", "onset"):
        a = e.get("audible_s")
        known = isinstance(a, (int, float))
        a = float(a) if known else attack_of(buf, sr)
        if a - landmark >= ATTACK_TOL:
            heard, attack = start + a, a - landmark
            base["attack_from"] = (
                "the sheet's audible_s" if known else "estimated from the buffer"
            )
    ms = (heard - cue_t) * 1000
    status, note = verdict(ms, fps)
    r = {
        **base,
        "status": status,
        "note": note,
        "audio_ms": ms_round(ms),
        "align": align,
    }
    r |= {"landmark_t": round(lm, 5), "moved_ms": ms_round((start - want_of(e)) * 1000)}
    r |= {
        "taken_out": p.get("taken_out", 0),
        "group_n": p.get("group_n", 1),
        "group_ms": p.get("group_ms"),
    }
    tol = e.get(
        "landmark_tol"
    )  # synth.place: 0.04 s for a measured pad point, 0 when the generator gave its own
    if isinstance(tol, (int, float)) and tol > 0:
        r["landmark_tol_ms"] = ms_round(tol * 1000, 0)
    if attack is not None:
        r["attack_ms"] = ms_round(attack * 1000)
        r["landmark_ms"] = ms_round((lm - cue_t) * 1000)
    if (
        align == "onset" and attack is None
    ):  # Z02 correction 6: an onset cue is also measured without the sheet
        o = onset_alone(x, sr, buf, start, lm, e, st, name)
        r["onset_ms"] = None if o is None else ms_round((o - lm) * 1000)
    if a48 is not None and len(a48):
        file_confirm(r, buf, sr, start, cue_t, st["wavs"], a48)
    return r


# ---- the detector for a score with no cue sheet ----


def rises(x, sr):
    """dB rise of each 10 ms window of x over the loudest of the previous 30 ms (a whoosh's noisy build stays small)."""
    w = round(0.01 * sr)
    m = len(x) // w
    if m <= 3:
        return None
    e = 10 * np.log10((x[: m * w].reshape(m, w) ** 2).mean(1) + 1e-10)
    prev = np.max(
        np.stack([np.concatenate([np.full(k, e[0]), e[:-k]]) for k in (1, 2, 3)]), 0
    )
    return e - prev


def onset_offsets(scenes, a8k, g, fps, a48=None, size=None):
    """The detector for a score with no cue sheet: per cue {t, label, kind, audio_ms, picture_frames, status,
    source}. Audio: the strong 3 dB rise nearest the cue on the whole mix or, given a48, above 2 kHz (whichever rises
    more; calibration: right on 63 of 70 cues of four approved samples, against 26 on the mix alone), or in the cue's
    own band when its CUES entry carries band=(lo, hi). Picture: the strong change nearest the cue frame, inside the
    cue's region=(x0, y0, x1, y1) when it carries one. It cannot tell a cue's sound from a neighbour's, so a cue it
    does not find is "not found", never missing, and what it finds is the nearest onset, not the cue's own."""
    lag = getattr(scenes, "CUE_LAG", 0)
    a8k = np.asarray(a8k, np.float64)
    rise = rises(a8k, 8000)
    if rise is not None and a48 is not None and len(a48):
        hp = rises(band(np.asarray(a48, np.float64), 48000, RISE_HP), 48000)
        n = min(len(rise), len(hp))
        rise = np.maximum(rise[:n], hp[:n])
    g = np.asarray(g, np.float32)
    d = frame_change(g) if len(g) > 1 else np.zeros(0)
    out = []
    for c in C.cues(scenes):
        t = c["t"]
        r = dict(
            c,
            audio_ms=None,
            picture_frames=None,
            status="ok",
            note=False,
            source="onset",
        )
        rr = rise
        if c.get("band") and a48 is not None and len(a48):
            lo, hi = c["band"]
            rr = rises(band(np.asarray(a48, np.float64), 48000, lo, hi), 48000)
        if c["kind"] in ("both", "audio") and rr is not None:
            lo, hi = (
                max(0, C.sample_of(t - 0.1, 100)),
                min(len(rr), C.sample_of(t + 0.1, 100) + 1),
            )
            i = strong(rr, lo, hi, t * 100, RISE_DB)
            if i is None:
                r.update(
                    status="not found",
                    why="no 3 dB onset within 100 ms (masked, quiet or slow)",
                )
            else:
                r["audio_ms"] = ms_round((i * 0.01 - t) * 1000, 1)
                late = r["audio_ms"] > 0
                r["status"] = (
                    "ok"
                    if abs(r["audio_ms"]) <= 1000 / fps
                    else "late"
                    if late
                    else "early"
                )
        if c["kind"] in ("both", "picture"):
            measure_picture(r, c, g, d, fps, lag, size, scenes)
            # a picture cue: the picture decides, and a change the detector does not see is "not found"
            if c["kind"] == "picture":
                pf = r["picture_frames"]
                if "picture" in r:
                    r["status"] = "not measured"
                else:
                    r["status"] = "not found" if pf is None else picture_status(pf, lag)
        out.append(r)
    return out


def cue_gates(scenes, a8k, g, fps):
    """Q902 from the detector used before cue sheets (qa.cue_gates wraps this): one row, a NOTE when any cue is off
    or not found."""
    return [onset_row(onset_offsets(scenes, a8k, g, fps), fps)]


def onset_row(res, fps, why=""):
    """The one Q902 row of the no-cue-sheet detector: PASS when it finds every cue in its window, else a NOTE that
    lists what it found off (with offsets, as the nearest onset) apart from what it did not find (no offsets: a
    miss is not a measurement), and says that without a cue sheet the counts are a guess (calibration c2: 19 of 20
    cues "off" on an approved sample, every one a miss of the old floors)."""
    aud = [r for r in res if r["kind"] in ("both", "audio")]
    a_off = [r for r in aud if r["status"] in ("late", "early")]
    a_miss = [r for r in aud if r["status"] == "not found"]
    pic = [
        r
        for r in res
        if r["kind"] in ("both", "picture")
        and r.get("picture") in (None, "not measurable")
    ]
    p_off = [r for r in pic if r.get("picture_bad") and r["picture_frames"] is not None]
    p_miss = [r for r in pic if r.get("picture_bad") and r["picture_frames"] is None]
    p_blind = [r for r in pic if r.get("picture") == "not measurable"]

    def worst_ms(r):
        return (
            abs(r["audio_ms"]) if r in a_off else abs(r["picture_frames"]) * 1000 / fps
        )

    off = sorted(a_off + p_off, key=worst_ms, reverse=True)
    w = off[0] if off else None
    parts = []
    if aud:
        part = f"audio: {len(aud) - len(a_off) - len(a_miss)} of {len(aud)} near an onset within 1 frame"
        if a_off:
            part += ", nearest onset off at " + ", ".join(
                f"{r['label'] or r['t']} {ms_text(r['audio_ms'], 0)} ms"
                for r in a_off[:3]
            )
        if a_miss:
            part += f", {len(a_miss)} not found by the detector (" + ", ".join(
                f"{r['t']:.2f}" for r in a_miss[:4]
            )
            part += " s)" if len(a_miss) <= 4 else ", ... s)"
        parts.append(part)
    if pic:
        n_ok = len(pic) - len(p_off) - len(p_miss) - len(p_blind)
        part = f"picture: {n_ok} of {len(pic)} change within CUE_LAG + 1 frames"
        if p_off:
            part += ", nearest change at " + ", ".join(
                f"{r['label'] or r['t']} {r['picture_frames']:+d} frames"
                for r in p_off[:3]
            )
        if p_miss:
            part += f", {len(p_miss)} with no change in their region or registry text"
        if p_blind:
            part += f", {len(p_blind)} not measurable on the whole frame (no region= or registry text for them)"
        parts.append(part)
    return C.row(
        not (a_off or a_miss or p_off or p_miss or p_blind),
        "Q902",
        "onset detector, no cue sheet (a guess, not a measurement: it reads the whole mix and frame and cannot tell "
        "a cue's sound from its neighbours"
        + (f"; {why}" if why else "")
        + "): "
        + "; ".join(parts),
        "record the score's placements (place sounds with synth.place inside synth.recording(), as audio.render_audio"
        " does) so Q902 measures each cue; or give hard cues band=(lo, hi) and region=(x0, y0, x1, y1) in CUES",
        note=True,
        worst_t=None if w is None else round(w["t"], 3),
        item=None if w is None else w["label"],
        metric=None if w is None or w not in a_off else w["audio_ms"],
        considered=len(res),
    )


# ---- Q903: the mux ----


def start_times(path, ffprobe=None):
    """{"video": s, "audio": s} from ffprobe's stream start_time (None where a stream has none)."""
    ffprobe = ffprobe or C.ffprobe_of(C.find_ffmpeg() or "ffmpeg")
    out = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,start_time",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    st = {}
    for s in json.loads(out).get("streams", []):
        v = s.get("start_time")
        st.setdefault(s["codec_type"], None if v in (None, "N/A") else float(v))
    return st


def mux_lag(ref, x, sr, at, half=MUX_HALF, search=MUX_SEARCH, hp=MUX_HP):
    """(lag s, match, why) of x against ref around time at, positive = x late: a 2 s window of ref searched +-search s
    in x after a hp Hz high-pass (zeroed rfft bins), with the edge guard and parabolic refinement. lag is None and why
    "silent" or "edge" when the window is silent or its best match sits on the search edge."""
    w, n = round(search * sr), round(2 * half * sr)
    i = C.sample_of(at - half, sr)
    tpl = band(take(ref, i, n), sr, hp)
    seg = band(take(x, i - w, n + 2 * w), sr, hp)
    if (tpl * tpl).sum() < 1e-12 * n or (seg * seg).sum() < 1e-12 * n:
        return None, 0.0, "silent"
    r = ncc(tpl, seg)
    k, edge = peak(r, w, round(GUARD * sr))
    return (None if edge else (k - w) / sr), float(r.max()), "edge" if edge else ""


def lag_row(ctx, name, what, fix, unmatched_note=False):
    """One Q903 row: the decoded file against the WAV `name` in the working folder, three 2 s windows (12, 45, 85
    percent, +-0.1 s, 500 Hz high-pass) and, when none matches there, again over +-1 s. FIX past 1 ms; NOT CHECKED
    (or a NOTE with unmatched_note) when no window matches, saying whether they were silent, on the edge or unlike."""
    ref, sr = read_wav(Path(ctx.workdir, name))
    x = ctx.audio(sr)
    dur = min(len(ref), len(x)) / sr
    got = [(f, *mux_lag(ref, x, sr, f * dur)) for f in MUX_AT]
    ok = [(f, lag, m) for f, lag, m, _ in got if lag is not None and m >= 0.5]
    span = MUX_SEARCH
    # a lag past 0.1 s reads as no match there (review R4 finding 5: 98 ms read as a stale mix.wav)
    if not ok and any(why != "silent" for *_, why in got):
        got = [(f, *mux_lag(ref, x, sr, f * dur, search=MUX_WIDE)) for f in MUX_AT]
        ok = [
            (f, lag, m)
            for f, lag, m, _ in got
            if lag is not None and m >= MUX_WIDE_MATCH
        ]
        span = MUX_WIDE
    if not ok:
        best = max(m for _, _, m, _ in got)
        why = (
            "the three windows are silent"
            if all(w == "silent" for *_, w in got)
            else f"its best match ({best:.2f}) sits on the +-{span * 1000:.0f} ms search edge"
            if any(w == "edge" for *_, w in got)
            else f"{name} does not match the file's audio (best match {best:.2f} in 3 windows)"
        )
        msg = f"{why}, so {what} was not measured"
        again = "re-run run_all.py full so the WAVs and the mp4 come from the same audio stage"
        if unmatched_note:
            return C.row(False, "Q903", msg, again, note=True)
        return C.not_checked("Q903", msg, again)
    f, lag, _ = max(ok, key=lambda o: abs(o[1]))
    each = ", ".join(f"{ms_text(lg * 1000, 2)} ms at {fr:.0%}" for fr, lg, _ in ok)
    found = f", found over +-{span:g} s" if span != MUX_SEARCH else ""
    return C.row(
        abs(lag) * 1000 <= MUX_MAX,
        "Q903",
        f"decoded audio against {name} ({what}): {each} (match {min(m for _, _, m in ok):.2f} or better{found}; "
        f"FIX past {MUX_MAX:g} ms)",
        fix,
        worst_t=round(f * dur, 3),
        metric=ms_round(lag * 1000, 3),
        limit=MUX_MAX,
        considered=len(ok),
    )


def mux_rows(ctx):
    """Q903 rows: the audio and video streams start together; the decoded audio lines up with mix.wav (the mux);
    and, when mix_raw.wav is there, with the mix before the master too (the master and the mux together: a delay the
    master adds shows only here; calibration c5 rebuilt a 2.1.0 score whose master ran 3.97 ms late while the mix.wav
    row read 0.00). No rows for a file without both streams (mix.wav itself at the proof stage has no mux)."""
    if (
        not ctx.probe.get("acodec")
        or not ctx.probe.get("vcodec")
        or ctx.declared("SILENT")
    ):
        return []
    rows = []
    st = start_times(ctx.path)
    v, a = st.get("video"), st.get("audio")
    if v is None or a is None:
        rows.append(
            C.row(
                False,
                "Q903",
                f"ffprobe reports no start_time (video {v}, audio {a})",
                "re-mux with ffmpeg into mp4 (run_all.py), which writes both",
                note=True,
            )
        )
    else:
        ms = (a - v) * 1000
        rows.append(
            C.row(
                abs(ms) <= MUX_MAX,
                "Q903",
                f"audio stream starts {ms_text(ms, 2)} ms from the video (start_time audio {a:.6f} s, video {v:.6f} s)",
                "re-mux without -itsoffset or a delayed input; a real offset is fixed in the mux, never in the mixer",
                worst_t=0.0,
                metric=ms_round(ms, 3),
                limit=MUX_MAX,
            )
        )
    if not Path(ctx.workdir, C.MIX).exists():
        if ctx.scenes is not None:  # a build folder is expected to hold its master
            rows.append(
                C.not_checked(
                    "Q903",
                    f"no {C.MIX} in {ctx.workdir}, so the mux lag was not measured",
                    "run qa.py check from the working folder run_all.py full wrote (it keeps mix.wav)",
                )
            )
        return rows
    rows.append(
        lag_row(
            ctx,
            C.MIX,
            "the mux",
            "the mux moved the audio: encode AAC straight from mix.wav in the mux (no ADTS round trip, no stream copy "
            "of an older AAC), keep the edit list, and fix a real offset in the mux (-itsoffset), never in the mixer",
        )
    )
    if Path(ctx.workdir, C.MIX_RAW).exists():
        rows.append(
            lag_row(
                ctx,
                C.MIX_RAW,
                "the master and the mux",
                "the master delays the mix (a lookahead limiter without delay compensation): fix audio.master, and "
                "run qa.py calib; never subtract the delay in the mixer",
                unmatched_note=True,
            )
        )
    return rows


# ---- Q902 on the cue sheet: measure once per Ctx, then rows and the per-cue list ----


def stems(folder):
    """{name: (mono, sr)} of the lossless stems a build writes: sfx.wav (the SFX bus alone) and mix_raw.wav."""
    return {
        n: read_wav(Path(folder, n))
        for n in (C.SFX, C.MIX_RAW)
        if Path(folder, n).exists()
    }


def measure(ctx):
    """Q902 per cue, measured once per Ctx so check_rows and cue_offsets agree: {"mode", "why", "rows", "cues"}.
    mode "sheet" measures on the stems, "onset" is the no-cue-sheet detector (NOTE only), "picture" a silent piece,
    and None means rows already say why nothing was measured."""
    if getattr(ctx, "_qa_sync", None) is None:
        ctx._qa_sync = _measure(ctx)
    return ctx._qa_sync


def _measure(ctx):
    s = ctx.scenes

    def stop(*rows):
        return {"mode": None, "why": "", "rows": list(rows), "cues": []}

    if (
        s is None
    ):  # no --scenes: nothing declared to hold the file against (qa.py names it under "not checked here")
        return stop()
    if C.declared(s, "NO_CUES"):
        return stop(
            C.row(True, "Q902", "no sound cues by design (NO_CUES)", "", considered=0)
        )
    try:
        cues = C.cues(s)
    except (TypeError, ValueError, KeyError, IndexError):
        return stop(
            C.not_checked(
                "Q902",
                "CUES could not be read as (t, label, kind) entries or dict(label=t), so cue sync did not run",
                "write CUES = [(t, label, kind), ...] or dict(label=t or [t, ...])",
            )
        )
    silent = ctx.declared("SILENT") or not ctx.probe.get("acodec")
    if not cues:
        if silent:
            return stop(
                C.row(
                    True,
                    "Q902",
                    "silent piece and no CUES: no cue to check",
                    "",
                    considered=0,
                )
            )
        why = "CUES is empty" if hasattr(s, "CUES") else "scenes.py has no CUES"
        return stop(
            C.not_checked(
                "Q902",
                f"{why}, so cue sync did not run",
                "list every moment sound and picture share in CUES = [(t, label, kind)], or set NO_CUES = True",
            )
        )
    g = grey(ctx)
    size = (ctx.w, ctx.h)
    entries, sounds, sr_sheet, wavs = [], None, None, {}
    sheet = Path(ctx.workdir, C.CUESHEET)
    if silent or not any(c["kind"] in ("both", "audio") for c in cues):
        mode, why = "picture", "silent piece: picture side only" if silent else ""
    elif not sheet.exists():
        mode, why = (
            "onset",
            f"no {C.CUESHEET}: the score does not record its placements",
        )
    else:
        # review R4 finding 6: a sheet without its buffers or stems cannot be measured, and must not quietly fall
        # back to the detector (a kick 90 ms late read as a NOTE)
        entries, sounds, sr_sheet = C.read_cuesheet(ctx.workdir)
        wavs = stems(ctx.workdir)
        lost = [
            n
            for n, ok in (
                (C.CUE_SOUNDS, sounds is not None),
                (f"{C.SFX} or {C.MIX_RAW}", bool(wavs)),
            )
            if not ok
        ]
        if lost:
            return stop(
                C.not_checked(
                    "Q902",
                    f"{C.CUESHEET} is here but {' and '.join(lost)} not, so the cues could not be measured",
                    "rebuild the audio stage (run_all.py audio writes the sheet, its buffers and the stems together), "
                    f"or delete a stale {C.CUESHEET}",
                )
            )
        for k, e in enumerate(
            entries
        ):  # review R4 finding 11: a row without these crashed qa.py check
            gap = [
                key
                for key in ("i", "t", "landmark_s")
                if not isinstance(e.get(key), (int, float))
            ]
            if gap:
                return stop(
                    C.not_checked(
                        "Q902",
                        f"{C.CUESHEET} row {k} ({e.get('sound') or 'sound'}) has no {', '.join(gap)}, so the cues "
                        "could not be measured",
                        "write the sheet with synth.recording() (contract.CUESHEET_KEYS lists every key)",
                    )
                )
        mode, why = "sheet", ""
    if mode == "onset":
        a48 = ctx.audio(48000)
        res = onset_offsets(s, ctx.audio(8000), g, ctx.fps, a48, size)
        return {"mode": mode, "why": why, "rows": [], "cues": res}
    lag = getattr(s, "CUE_LAG", 0)
    if mode == "picture" and not len(g):
        return stop(
            C.not_checked(
                "Q902",
                "no video stream and no audio cue to measure, so cue sync did not run",
                "run qa.py check on the finished mp4",
            )
        )
    d = frame_change(g) if len(g) > 1 else np.zeros(0)
    groups = match(cues, entries) if mode == "sheet" else {}
    st = sheet_state(entries, sounds, sr_sheet, wavs)
    a48 = ctx.audio(48000) if mode == "sheet" else None
    out = []
    for i, c in enumerate(cues):
        r = dict(
            c, audio_ms=None, picture_frames=None, status="ok", note=False, source=mode
        )
        if mode == "sheet" and c["kind"] in ("both", "audio"):
            worst = None
            for e in groups[i]:
                worst = worse(worst, measure_entry(e, st, c["t"], ctx.fps, a48))
            if worst is None:
                worst = {
                    "status": "missing",
                    "why": f"{C.CUESHEET} has no sound labelled {c['label']!r} and none within {NEAR * 1000:.0f} ms",
                }
            r.update(worst)
            r["source"] = worst.get("stem", mode)
        if c["kind"] == "picture":
            r["source"] = "picture"
        if c["kind"] in ("both", "picture"):
            measure_picture(r, c, g, d, ctx.fps, lag, size, s)
            # no audio measured: the picture decides the status
            if c["kind"] == "picture" or mode == "picture":
                r["status"] = (
                    "not measured"
                    if "picture" in r
                    else picture_status(r["picture_frames"], lag)
                )
        out.append(r)
    return {"mode": mode, "why": why, "rows": [], "cues": out}


def cue_offsets(ctx):
    """[{t, label, kind, audio_ms, picture_frames, status}] per cue for the audio strip (qa_audiostrip). status is
    ok, late, early, missing or ambiguous against the Q902 FIX window (picture-only cues: against CUE_LAG + 1
    frames); "not found" from the no-cue-sheet detector (a miss, not a measurement); "not measured" for a
    picture-only cue with no video stream or on the first frame, where picture says why. Extra keys: note (outside
    -5..+15 ms), sound, align, source (the stem, onset or picture), match, how, group_n, attack_ms and landmark_ms
    (a slow attack heard after its landmark), onset_ms, file_ms and file_how (sound or mix window), picture_bad, why."""
    return [dict(r) for r in measure(ctx)["cues"]]


def _cue_row(r, fps, lag):
    """The Row for one cue that is out of a window, or None when it lands."""
    name = r["label"] or f"cue at {r['t']:.2f} s"
    ms, st = r.get("audio_ms"), r["status"]
    audio = r["kind"] in ("both", "audio") and r["source"] != "picture"
    fix_audio = audio and st in ("missing", "late", "early")
    unsure = audio and st == "ambiguous"
    parts, fixes, metric, limit = [], [], None, None
    times = [r["t"]] + ([r["landmark_t"]] if r.get("landmark_t") is not None else [])
    if audio and st in ("missing", "ambiguous"):
        parts.append(
            ("no sound found" if st == "missing" else "not told apart")
            + f" ({r.get('why', 'not placed')})"
        )
        fixes.append(
            "place the cue's sound on its time with audio.place (it writes the sheet), or make the cue kind 'picture'"
            if st == "missing"
            else "space identical sounds wider than twice their error, or give each cue its own variant (a seed)"
        )
    elif audio and ms is not None and (fix_audio or r.get("note")):
        sound, align = r.get("sound", "sound"), r.get("align", "onset")
        if st == "late":
            limit = round(late_limit(fps), 1)
            how = f"late (FIX past +{limit:.1f} ms at {fps} fps)"
        elif st == "early":
            limit, how = EARLY, f"early (FIX past {EARLY:+.0f} ms)"
        else:
            limit = NOTE_HI if ms > NOTE_HI else NOTE_LO
            how = f"(NOTE outside {NOTE_LO:+.0f}..{NOTE_HI:+.0f} ms)"
        metric = ms
        heard = "is heard" if r.get("attack_ms") is not None else "lands"
        parts.append(
            f"{sound} ({align}) {heard} {ms_text(ms)} ms {how} on {r['source']}, match {r.get('match', 0):.2f}"
        )
        if r.get("attack_ms") is not None:
            parts.append(
                f"its audible attack (-15 dB, {r.get('attack_from', 'estimated')}) comes about "
                f"{r['attack_ms']:.0f} ms after its {align} landmark, which itself lands {ms_text(r['landmark_ms'])} ms"
            )
            fixes.append(
                f"align {sound} on its attack (align='pad'), or shorten its attack"
            )
        if r.get("group_n", 1) > 1:
            parts.append(
                f"measured with its {r['group_n'] - 1} twin(s), the group {ms_text(r.get('group_ms') or 0)} ms"
            )
        if r.get("landmark_tol_ms"):
            parts.append(
                f"its {align} landmark is measured, good to +-{r['landmark_tol_ms']:.0f} ms"
            )
        if abs(r.get("moved_ms") or 0) > 0.1:
            parts.append(
                f"it sits {ms_text(r['moved_ms'])} ms from where the sheet placed it"
            )
        fixes.append(
            f"move {sound} {ms_text(-ms, 0)} ms: place it by its landmark (align='{align}') on the cue time"
        )
    o = r.get("onset_ms")
    if o is not None and not NOTE_LO <= o <= NOTE_HI:
        parts.append(
            f"its onset on the stem sits {ms_text(o)} ms from the recorded landmark"
        )
        fixes.append("check the sound's landmark_s (leading silence, a slow attack)")
        times.append(r["landmark_t"] + o / 1000)
        # the row's number is then where the onset really sits against the cue
        if metric is None and ms is not None:
            metric, limit = ms_round(ms + o), NOTE_HI if o > NOTE_HI else NOTE_LO
    if (
        r.get("picture") == "not measurable"
    ):  # calibration c5: a miss on the whole frame is no finding
        parts.append(
            f"picture change not measurable near the cue (under {PIX_SHARE:g}% of the whole frame moves, and its "
            "CUES entry has no region= and no registry text changes there)"
        )
        fixes.append(
            "give the cue region=(x0, y0, x1, y1) in CUES around what moves, or check that frame by eye"
        )
    if r.get("picture_bad"):
        pf = r["picture_frames"]
        parts.append(
            f"no picture change in {r.get('picture_where', 'the frame')} near the cue"
            if pf is None
            else f"picture {pf:+d} frames in {r.get('picture_where', 'the frame')} (CUE_LAG {lag})"
        )
        fixes.append(
            "move the motion onto the cue frame, or set CUE_LAG for a designed trail"
        )
        if metric is None and pf is not None:  # in ms like every Q902 metric
            metric = ms_round(pf * 1000 / fps)
            limit = ms_round((lag + 1 if pf > 0 else -1) * 1000 / fps)
    if not parts:
        return None
    if not C.on_grid(r["t"], fps, 0.03):
        parts.append(
            f"cue time {r['t']:.4f} s is off the frame grid, so the picture can only change on a frame (Q904)"
        )
    text = f"{name} at {r['t']:.2f} s: " + "; ".join(parts)
    kw = {
        "t0": round(min(times), 3),
        "t1": round(max(times), 3),
        "worst_t": round(r["t"], 3),
        "item": name,
    }
    if unsure:  # review R4 finding 1: a peak outside its share is no reading
        return C.not_checked("Q902", text, "; ".join(fixes), **kw)
    return C.row(
        False,
        "Q902",
        text,
        "; ".join(fixes),
        note=not fix_audio,
        metric=metric,
        limit=limit,
        **kw,
    )


def cue_rows(ctx):
    """Q902 rows: one per cue out of a window (FIX on the audio FIX window and missing sounds; NOT CHECKED for a
    sound that cannot be told from its twins; NOTE for the NOTE window, the picture and the onset confirm, and NOTE
    rows honour ALLOW), one summary PASS row when every cue lands, and one NOTE when the decoded file moves
    confirmed cues by more than 2 ms against the stem (confirm only)."""
    m = measure(ctx)
    if m["mode"] is None:
        return m["rows"]
    s, fps = ctx.scenes, ctx.fps
    # the detector's findings are all NOTE-level, so ALLOW drops the cues it lists
    if m["mode"] == "onset":
        kept = [r for r in m["cues"] if not ctx.allowed("Q902", r["t"])]
        return [onset_row(kept, fps, m["why"])]
    lag = getattr(s, "CUE_LAG", 0)
    res = m["cues"]
    rows = []
    for r in res:
        row = _cue_row(r, fps, lag)
        if row is not None and not (
            row.status == C.NOTE and ctx.allowed("Q902", r["t"])
        ):
            rows.append(row)
    conf = [r for r in res if r.get("file_ms") is not None]
    moved = [r for r in conf if abs(r["file_ms"]) > CONFIRM]
    if not rows:
        aud = [r for r in res if r.get("audio_ms") is not None]
        worst = "picture side only"
        if aud:
            w = max(aud, key=lambda r: abs(r["audio_ms"]))
            n_aud = sum(r["kind"] in ("both", "audio") for r in res)
            worst = (
                f"audio worst {ms_text(w['audio_ms'])} ms on {w['source']}; the decoded file confirms "
                f"{len(conf) - len(moved)} of {n_aud} within {CONFIRM:g} ms"
            )
        land = "the 1 cue lands" if len(res) == 1 else f"all {len(res)} cues land"
        pic = (
            "picture within CUE_LAG + 1 frames"
            if ctx.probe.get("vcodec")
            else "picture not measured (no video)"
        )
        rows.append(
            C.row(
                True,
                "Q902",
                f"{land}: {worst} (NOTE outside {NOTE_LO:+.0f}..{NOTE_HI:+.0f} ms, FIX past "
                f"+{late_limit(fps):.1f} or {EARLY:+.0f} ms), {pic}"
                + (f" [{m['why']}]" if m["why"] else ""),
                "",
                considered=len(res),
            )
        )
    if moved and not ctx.allowed(
        "Q902", max(moved, key=lambda r: abs(r["file_ms"]))["t"]
    ):
        w = max(moved, key=lambda r: abs(r["file_ms"]))
        med = float(np.median([r["file_ms"] for r in conf]))
        rows.append(
            C.row(
                False,
                "Q902",
                f"the decoded file moves {len(moved)} of {len(conf)} confirmed cues by more than {CONFIRM:g} ms "
                f"against the stem (median {ms_text(med)} ms, worst {w['label'] or w['t']} {ms_text(w['file_ms'])} "
                "ms): confirm only",
                "the master or the mux shifts the sound: see Q903 and run qa.py calib",
                note=True,
                worst_t=round(w["t"], 3),
                item=w["label"],
                metric=w["file_ms"],
                limit=CONFIRM,
                considered=len(conf),
            )
        )
    return rows


def check_rows(ctx):
    """Q902 per cue and Q903 for qa.py check."""
    return cue_rows(ctx) + mux_rows(ctx)


# ---- Q906: the flash-and-blip calibration (qa.py calib) ----


def blip_at(x, sr, t, f=1000.0, half=0.25):
    """When the f Hz blip near t starts: where its band-passed envelope (FFT analytic signal) first reaches half its
    peak, interpolated between samples. Envelope timing, because a pure tone correlates almost as well one period
    (1 ms) off as on."""
    i0 = C.sample_of(t - half, sr)
    seg = band(take(x, i0, round(2 * half * sr)), sr, f / 2, 2 * f)
    n = len(seg)
    h = np.zeros(n)
    h[0] = 1
    h[1 : (n + 1) // 2] = 2
    if n % 2 == 0:
        h[n // 2] = 1
    env = np.abs(np.fft.ifft(np.fft.fft(seg) * h))
    half_top = 0.5 * env.max()
    j = int(np.argmax(env >= half_top))
    if j == 0:
        return i0 / sr
    return (i0 + j - 1 + (half_top - env[j - 1]) / (env[j] - env[j - 1])) / sr


def write16(path, mono, sr):
    """mono as 16-bit stereo PCM, the format mix_raw.wav has."""
    pcm = (np.clip(np.stack([mono, mono], 1), -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def picture_argv(ff, path, w, h, fps):
    """The picture encode run_all uses (render.encode_cmd) and which it was; the same argv by hand when render.py
    has none (an older engine)."""
    try:
        import render

        return render.encode_cmd(ff, str(path), w, h, fps), "render.encode_cmd"
    except (ImportError, AttributeError):
        pass
    argv = [ff, "-y", "-v", "error", "-f", "rawvideo", "-pixel_format", "rgb24"]
    argv += ["-video_size", f"{w}x{h}", "-framerate", str(fps), "-i", "-", "-an"]
    argv += ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-vf", C.COLOR_VF]
    return [*argv, *C.COLOR_FLAGS, "-pix_fmt", "yuv420p", str(path)], "own argv"


# a calib folder must not be a build: these are never written by calib, and video.mp4 or the mixes without calib.mp4
# beside them are a build's (review R4 finding 10: --out . overwrote the build's video.mp4 and mixes)
BUILD_FILES = ("scenes.py", "run_all.py", C.CUESHEET, C.CUE_SOUNDS, C.SFX)


def calib(fps=30, size="320x180", out="calib", ff=None):
    """Q906 rows: a 4 s clip, black but for one white frame at 2 s and quiet but for a one-frame 1 kHz blip on that
    frame (over a 3 to 6 kHz noise bed, so the master sees programme-like audio and the blip's band stays clean),
    through audio.master and contract.mux_cmd (the mux run_all runs), then measured back as a player reads it. A
    regression guard: it reports the offset and where it entered, and never writes one for the mixer to subtract
    (R37: do not retard audio; a real offset is fixed in the mux). Raises ValueError on a folder holding a build."""
    ff = ff or C.find_ffmpeg() or "ffmpeg"
    import audio  # the engine copy beside qa.py

    w, h = (int(v) for v in size.lower().split("x"))
    d = Path(out)
    video, raw, mix, mp4 = (d / f for f in (C.VIDEO, C.MIX_RAW, C.MIX, "calib.mp4"))
    held = [n for n in BUILD_FILES if (d / n).exists()]
    held += [p.name for p in (video, raw, mix) if p.exists() and not mp4.exists()]
    if held:
        raise ValueError(
            f"{d} holds a build ({', '.join(held)}): calib writes video.mp4 and the mixes there"
        )
    d.mkdir(parents=True, exist_ok=True)
    n, k = C.frame_of(4.0, fps), C.frame_of(2.0, fps)
    pic = np.zeros((n, h, w, 3), np.uint8)
    pic[k] = 255
    argv, how = picture_argv(ff, video, w, h, fps)
    subprocess.run(argv, input=pic.tobytes(), capture_output=True, check=True)
    sr = audio.SR
    y = band(
        np.random.default_rng(0).standard_normal(C.frame_sample(n, fps, sr)),
        sr,
        3000,
        6000,
    )
    y *= 0.05 / np.sqrt((y * y).mean())
    a0, a1 = C.frame_sample(k, fps, sr), C.frame_sample(k + 1, fps, sr)
    y[a0:a1] += 0.25 * np.sin(2 * np.pi * 1000 * np.arange(a1 - a0) / sr)
    write16(raw, y, sr)
    audio.master(str(raw), str(mix), ff)
    subprocess.run(
        C.mux_cmd(ff, str(video), str(mix), str(mp4)), capture_output=True, check=True
    )
    vr = subprocess.run([ff, "-version"], capture_output=True, text=True, check=True)
    ver = ([*vr.stdout.split(), "?", "?", "?"])[2]  # "ffmpeg version 9.0.2-..."
    # read back the way qa.py check reads a file: Ctx's BT.709 frame decode and its padded audio decode
    ctx = C.Ctx(mp4, {"acodec": "aac", "vcodec": "h264"}, fps, w, h, ff=ff)
    g = ctx.grey()
    kw = int(np.argmax(g.reshape(len(g), -1).mean(1)))
    t = k / fps
    t_raw, t_mix = blip_at(*read_wav(raw), t), blip_at(*read_wav(mix), t)
    t_mp4 = blip_at(ctx.audio(48000), 48000, t)
    st = start_times(mp4)
    sv, sa = st.get("video"), st.get("audio")
    ds = None if sv is None or sa is None else (sa - sv) * 1000
    bias = t_raw - t  # the envelope measure's own offset on the lossless source
    # a player shows decoded frame kw at the video stream's start_time plus kw / fps; the audio decode pads from 0
    av = (t_mp4 - (sv or 0.0) - kw / fps - bias) * 1000
    master_ms, mux_ms = (t_mix - t_raw) * 1000, (t_mp4 - t_mix) * 1000
    return [
        C.row(
            kw == k,
            "Q906",
            f"white frame came back as frame {kw} (sent as frame {k} at {fps} fps; picture by {how})",
            "the picture encode drops or repeats frames: check -framerate and the encode argv",
            worst_t=t,
        ),
        C.row(
            abs(av) <= MUX_MAX,
            "Q906",
            f"blip lands {ms_text(av, 2)} ms from the white frame (master {ms_text(master_ms, 2)} ms, "
            f"mux and AAC {ms_text(mux_ms, 2)} ms; ffmpeg {ver}; files in {d.as_posix()}/)",
            "find the stage that moved it (the master's limiter must not delay, the mux keeps the edit list) and "
            "fix it there; never subtract an offset in the mixer",
            worst_t=t,
            metric=ms_round(av, 3),
            limit=MUX_MAX,
        ),
        C.row(
            ds is not None and abs(ds) <= MUX_MAX,
            "Q906",
            f"stream start_time audio {sa} s, video {sv} s",
            "the mux shifted a stream (-itsoffset, a delayed input): mux with contract.mux_cmd, as run_all does",
            worst_t=0.0,
            metric=None if ds is None else ms_round(ds, 3),
            limit=MUX_MAX,
        ),
    ]


def calib_cmd(a):
    try:
        rows = calib(a.fps, a.size, a.out)
    except ValueError as e:
        print(f"refused: {e}; pass --out calib (the default) or an empty folder")
        return 2
    for r in rows:
        print(C.line(r))
    print(C.summary(rows, "CALIB"))
    return C.exit_code(rows)


def add_cli(sub):
    """qa.py calib: Q906, the flash-and-blip regression guard for the master and the mux."""
    p = sub.add_parser(
        "calib",
        help="Q906: one white frame and a one-frame 1 kHz blip through audio.master and the mux, measured back; "
        "exit 1 on any FIX",
    )
    p.add_argument("--fps", type=int, default=30)
    p.add_argument(
        "--size", default="320x180", help="WxH of the clip (default 320x180)"
    )
    p.add_argument(
        "--out",
        default="calib",
        help="folder for the clip and its files (default calib/; a folder holding a build is refused)",
    )
    p.set_defaults(func=calib_cmd)
