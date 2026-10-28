# qa_stack.py : true peak with the sounds that stack there (Q802) and the SFX stack guard (Q804).
# Both read the build's cue sheet (cuesheet.json, one entry per placed sound, written by audio.py) from ctx.workdir;
# Q802 also reads the 48 kHz decode in ctx and the pre-master stems mix_raw.wav and sfx.wav.
import itertools
import struct
import zipfile
from pathlib import Path

import contract as C
import numpy as np

TP_MAX = -1.0  # dBTP, the gate
# frames: two designed sounds this close read as one stacked gesture (cinetic score.py stack_guard)
STACK_F = 3
# at most 2 cues in any 100 ms: a taste rule from anidoodle's sound-design notes, not enforced in its code
DENSE_S, DENSE_N = 0.1, 2
# CUESHEET_KEYS "heavy", used only when an entry has no heavy flag
HEAVY = ("kick", "hit", "boom", "impact", "drop")
# sounds that run into a moment (cinetic LEAD_IN); one that lands on a heavy sound is one gesture with it
LEAD_IN = ("riser", "swell", "suck", "reverse", "whoosh")
# Q802 fix order, a house heuristic: only impact-then-bell has an anecdote (weilanx ep28)
CUT_ORDER = (
    ("impact", ("impact", "hit", "boom", "kick", "slam", "thud", "crash")),
    ("chime or bell", ("chime", "bell", "ding", "ping", "glock")),
    ("press or drop", ("press", "drop", "click", "pop", "tap", "tick")),
)
TAPS = 16  # input samples each side of the 4x interpolator


def _sinc4():
    """Kaiser-windowed sinc for 4x upsampling, each polyphase branch summed to 1 (exact on DC, exact on the
    original samples): about what ebur128's 4x true-peak resampler does, in numpy."""
    n = np.arange(-4 * TAPS, 4 * TAPS + 1)
    h = np.sinc(n / 4) * np.kaiser(len(n), 8.0)
    for r in range(4):
        h[r::4] /= h[r::4].sum()
    return h.astype(np.float32)


H4 = _sinc4()


def peak_moment(a, sr, block=0.01, cand=None, near_db=6.0, span=None):
    """(t, linear peak) of the highest 4x-oversampled sample of a, (n,) or (n, channels), inside span=(t0, t1) seconds
    when given, else anywhere. Every 10 ms block whose sample peak is within near_db of the loudest (at most cand when
    set) is upsampled channel by channel and the highest wins: an intersample peak sits up to about 3 dB over its
    samples, and on a flat-topped master hundreds of blocks share the sample peak (a top-32 cut named the wrong block
    in 31 of 40 such masters, up to 0.6 dB low)."""
    x = np.asarray(a, np.float32)
    x = x[:, None] if x.ndim == 1 else x
    a0, a1 = 0, len(x)
    if span is not None:
        a0, a1 = max(0, C.sample_of(span[0], sr)), min(len(x), C.sample_of(span[1], sr))
    if a1 <= a0:
        return None, 0.0
    b = max(1, round(block * sr))
    nb = -(-(a1 - a0) // b)
    mag = np.zeros(nb * b, np.float32)
    mag[: a1 - a0] = np.abs(x[a0:a1]).max(1)
    bm = mag.reshape(nb, b).max(1)
    order = np.argsort(bm)[::-1][:cand]
    order = order[bm[order] >= bm[order[0]] * 10 ** (-near_db / 20)]
    best_t, best = None, -1.0
    for k in order:
        s0, s1 = a0 + int(k) * b, min(a1, a0 + (int(k) + 1) * b)
        lo, hi = max(0, s0 - TAPS), min(len(x), s1 + TAPS)
        j0, j1 = (s0 - lo) * 4, (s1 - lo) * 4
        for c in range(x.shape[1]):
            z = np.zeros((hi - lo) * 4, np.float32)
            z[::4] = x[lo:hi, c]
            y = np.abs(np.convolve(z, H4, "same"))
            j = j0 + int(np.argmax(y[j0:j1]))
            if y[j] > best:
                best_t, best = (lo + j / 4) / sr, float(y[j])
    return best_t, best


def read_wav(path):
    """(mono float32, sr) of a RIFF WAV (PCM 16, 24 or 32 bit, or float), channels averaged like Ctx.audio's mono:
    level-true for the engine's dual-mono stems."""
    b = Path(path).read_bytes()
    if b[:4] != b"RIFF" or b[8:12] != b"WAVE":
        raise ValueError(f"{path}: not a RIFF WAVE file")
    i, fmt, data = 12, None, None
    while i + 8 <= len(b):
        cid, size = b[i : i + 4], struct.unpack_from("<I", b, i + 4)[0]
        if cid == b"fmt ":
            fmt = b[i + 8 : i + 8 + size]
        elif cid == b"data":
            data = b[i + 8 : i + 8 + size]
        i += 8 + size + (size & 1)
    if fmt is None or data is None:
        raise ValueError(f"{path}: no fmt or data chunk")
    tag, ch, sr, _, _, bits = struct.unpack_from("<HHIIHH", fmt)
    # WAVE_FORMAT_EXTENSIBLE: the real format is the subformat's first two bytes
    if tag == 0xFFFE:
        tag = struct.unpack_from("<H", fmt, 24)[0]
    width = bits // 8
    data = data[: len(data) // (width * ch) * width * ch]
    if tag == 3:
        x = np.frombuffer(data, "<f4" if bits == 32 else "<f8").astype(np.float32)
    elif tag == 1 and bits == 24:
        u = np.frombuffer(data, np.uint8).reshape(-1, 3).astype(np.int32)
        x = ((u[:, 0] | (u[:, 1] << 8) | (u[:, 2] << 16)) << 8 >> 8) / 2**23
    elif tag == 1 and bits in (16, 32):
        x = np.frombuffer(data, f"<i{width}") / 2 ** (bits - 1)
    elif tag == 1 and bits == 8:
        x = (np.frombuffer(data, np.uint8).astype(np.float32) - 128) / 128
    else:
        raise ValueError(f"{path}: WAV format {tag} at {bits} bit is not read here")
    return np.asarray(x, np.float32).reshape(-1, ch).mean(1), sr


def _name(e):
    lab = e.get("label") or ""
    return (
        f"{e.get('sound') or 'sound'} {lab!r}"
        if lab
        else str(e.get("sound") or "sound")
    )


def _level(e):
    """The sound's placed peak on its bus: its own sample peak plus its gain, in dBFS (None when unknown)."""
    g, p = e.get("gain"), e.get("peak_dbfs")
    if g is None or p is None:
        return None
    return float(p) + 20 * np.log10(g) if g > 0 else float("-inf")


def _rank(e):
    s = f"{e.get('sound') or ''} {e.get('label') or ''}".lower()
    return next(
        (i for i, (_, keys) in enumerate(CUT_ORDER) if any(k in s for k in keys)),
        len(CUT_ORDER),
    )


def _bed_level(folder, t, half=0.05):
    """Pre-master peaks (dBFS) of the music bed (mix_raw.wav minus sfx.wav) and of the SFX bus within half
    seconds of t, or None when the stems are missing or do not match."""
    try:
        mix, sr = read_wav(Path(folder, C.MIX_RAW))
        sfx, sr2 = read_wav(Path(folder, C.SFX))
    except (OSError, ValueError):
        return None
    if sr != sr2:
        return None
    n = min(len(mix), len(sfx))
    i0, i1 = max(0, C.sample_of(t - half, sr)), min(n, C.sample_of(t + half, sr))
    if i1 <= i0:
        return None

    def db(x):
        return float(20 * np.log10(np.abs(x).max() + 1e-12))

    return db(mix[i0:i1] - sfx[i0:i1]), db(sfx[i0:i1])


def _db(v):
    return f"{v:+.1f} dBFS" if v > -120 else "silent"


def _sheet(folder):
    """(entries, sounds, sr, problem) of the build's cue sheet; problem is None when it read cleanly, "missing" when
    there is none, else why it could not be read."""
    if not Path(folder, C.CUESHEET).exists():
        return [], None, None, "missing"
    try:
        entries, sounds, sr = C.read_cuesheet(folder)
        for e in entries:
            float(e["t"])
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as e:
        return [], None, None, f"{type(e).__name__}: {e}"
    return entries, sounds, sr, None


def _bed_bus(e):
    """A music-bus entry is the bed unless it serves a cue label."""
    return e.get("bus") == "music" and not e.get("label")


def sounding(entries, sounds, sr, t, half=0.05):
    """The cue sheet entries sounding within half seconds of t, each with "start", "end" and "there" (its own peak in
    that window times its gain, dBFS on the stems' scale): a bell still ringing, a riser into the moment and a hit
    landing just after it are all named. An entry without a buffer in cue_sounds.npz counts when it starts in the
    0.5 s before t or its landmark is within 0.1 s of it, with "end" and "there" unknown. Muted entries never count."""
    out = []
    for e in entries:
        st, g = float(e.get("start_s", e["t"])), float(e.get("gain", 1.0))
        if g <= 0:
            continue
        snd = sounds.get(f"c{e['i']}") if sounds is not None and "i" in e else None
        if snd is not None and sr:
            j0 = max(0, C.sample_of(t - half - st, sr))
            j1 = min(len(snd), C.sample_of(t + half - st, sr))
            if j1 <= j0:
                continue
            pk = float(np.abs(snd[j0:j1]).max()) * g
            end, there = st + len(snd) / sr, 20 * np.log10(pk) if pk > 0 else -999.0
        elif t - 0.5 <= st <= t + half or abs(float(e["t"]) - t) <= 0.1:
            end, there = None, None
        else:
            continue
        out.append({**e, "start": st, "end": end, "there": there})
    return out


def moment(ctx, a, sr=48000):
    """(t, frames over TP_MAX, frames): the true-peak moment, searched inside the loudest ebur128 frames of
    ctx.loudness["frames"] (every frame within the 0.1 dB print step of the loudest, 10 ms either side), else over the
    whole decode."""
    frames = [
        f for f in (ctx.loudness or {}).get("frames") or [] if f.get("ftpk") is not None
    ]
    over = [f for f in frames if f["ftpk"] > TP_MAX]
    best_t, best = None, -1.0
    if frames:
        top = max(f["ftpk"] for f in frames)
        for f in frames:
            if f["ftpk"] >= top - 0.1 - 1e-9:
                t, v = peak_moment(a, sr, span=(f["t"] - 0.11, f["t"] + 0.01))
                if t is not None and v > best:
                    best_t, best = t, v
    if best_t is None:
        best_t = peak_moment(a, sr)[0]
    return best_t, over, frames


def _over_spans(over):
    """Merged (t0, t1) runs of the 100 ms ebur128 frames over TP_MAX (each line closes the frame ending at t)."""
    spans = []
    for f in sorted(over, key=lambda f: f["t"]):
        a, b = max(0.0, round(f["t"] - 0.1, 1)), round(f["t"], 1)
        if spans and a <= spans[-1][1] + 1e-6:
            spans[-1] = (spans[-1][0], b)
        else:
            spans.append((a, b))
    return spans


def peak_rows(ctx):
    """Q802: true peak from ebur128 (ctx.loudness) against -1 dBTP. The moment is found channel by channel on the
    4x-oversampled 48 kHz decode, inside ebur128's loudest 100 ms frame (the AAC encode makes the channels of a
    dual-mono mix differ, so their mean can peak seconds away). On a FIX the row spans every frame over the limit and
    names every cue sheet sound sounding within 50 ms of the moment (its span, gain, peak plus gain, its level there
    and bus), the music bed's level there, and the cut order."""
    if ctx.declared("SILENT"):
        return [C.row(True, "Q802", "no audio by design (SILENT): true peak n/a", "")]
    L = ctx.loudness
    if L is None:
        why = (
            "no audio stream"
            if not ctx.probe.get("acodec")
            else "loudness not measured"
        )
        return [
            C.not_checked(
                "Q802",
                f"true peak not measured: {why}",
                "mux mix.wav into the encode (Q706), or declare SILENT",
            )
        ]
    tp = float(L["peak"])
    t, over, frames = moment(ctx, ctx.audio(48000, mono=False))
    t = round(t, 3) if t is not None else None
    at = f"{t:.3f} s" if t is not None else "unknown (empty decode)"
    if tp <= TP_MAX or t is None:
        return [
            C.row(
                tp <= TP_MAX,
                "Q802",
                f"true peak {tp:.1f} dBTP (want <= {TP_MAX:g}); loudest moment {at}",
                "lower the sounds at the loudest moment before the master, then rerun audio.master",
                worst_t=t,
                metric=tp,
                limit=TP_MAX,
            )
        ]
    entries, sounds, sr, problem = _sheet(ctx.workdir)
    now = sorted(
        sounding(entries, sounds, sr, t), key=lambda e: (_bed_bus(e), e["start"])
    )

    def desc(e):
        span = (
            f"{e['start']:.2f} to {e['end']:.2f} s"
            if e["end"] is not None
            else f"from {e['start']:.2f} s"
        )
        lv = _level(e)
        return (
            f"{_name(e)} ({span}, gain {float(e.get('gain', 1)):.2f}"
            + (f", peak {lv:+.1f} dBFS" if lv is not None else "")
            + (f", {_db(e['there'])} there" if e["there"] is not None else "")
            + f", {e.get('bus', 'sfx')})"
        )

    if now:
        what = "sounding there: " + "; ".join(desc(e) for e in now[:8])
        what += f"; and {len(now) - 8} more" if len(now) > 8 else ""
    elif problem is None:
        what = "nothing in the cue sheet sounds within 50 ms of it"
    elif problem == "missing":
        what = f"no {C.CUESHEET} to name the sounds"
    else:
        what = f"{C.CUESHEET} unreadable ({problem})"
    bed = _bed_level(ctx.workdir, t)
    bedtxt = (
        f"music bed {_db(bed[0])}, SFX bus {_db(bed[1])} within 50 ms (pre-master)"
        if bed
        else f"music bed not measured (needs {C.MIX_RAW} and {C.SFX})"
    )
    # culprits: designed sounds no more than 20 dB under the loudest of them there (quieter ones cannot move the peak)
    designed = [e for e in now if not _bed_bus(e)]
    known = [e["there"] for e in designed if e["there"] is not None]
    loudest = max(known) if known else None
    cut = sorted(
        (
            e
            for e in designed
            if e["there"] is None or loudest is None or e["there"] >= loudest - 20
        ),
        key=lambda e: (_rank(e), -(e["there"] if e["there"] is not None else 999.0)),
    )
    if cut:
        names = ", ".join(_name(e) for e in cut)
        fix = (
            f"lower or cut, in this order: {names} (house heuristic: impact, then chime or bell, "
            "then press or drop)"
        )
        if bed and loudest is not None and bed[0] > loudest:
            fix += "; the music bed is louder there than any of them, so lower the bed first"
    elif bed or now:
        fix = f"nothing designed sounds at {t:.2f} s: lower the music bed there"
    else:
        fix = f"lower what sounds at {t:.2f} s before the master"
    spans = _over_spans(over)
    n_over = (
        f"; {len(over)} of {len(frames)} 100 ms frames over {TP_MAX:g}"
        if frames
        else ""
    )
    return [
        C.Row(
            C.FIX,
            "Q802",
            f"true peak {tp:.1f} dBTP (want <= {TP_MAX:g}) at {at}{n_over}; {what}; {bedtxt}",
            fix + ", then rerun audio.master",
            t0=spans[0][0] if spans else round(max(0.0, t - 0.05), 3),
            t1=spans[-1][1] if spans else round(t + 0.05, 3),
            worst_t=t,
            item=" + ".join(_name(e) for e in designed) or None,
            metric=tp,
            limit=TP_MAX,
            spans=spans,
        )
    ]


def payoffs(scenes):
    """[(t, label)] of the CUES entries marked payoff=True (contract.cues keeps the flag; any CUES shape it reads)."""
    try:
        return [(c["t"], c["label"]) for c in C.cues(scenes) if c.get("payoff")]
    except (TypeError, ValueError, KeyError, IndexError):
        return []


def _events(entries, sounds, sr):
    """The sheet entries the guard counts: every SFX-bus sound, and a music-bus sound only when it serves a CUES
    label (a designed accent). The bed's own drum pattern is texture, not a layer, and a muted sound is no layer."""
    out = []
    for e in entries:
        if _bed_bus(e) or float(e.get("gain", 1.0)) <= 0:
            continue
        name = str(e.get("sound") or "").lower()
        snd = sounds.get(f"c{e['i']}") if sounds is not None and "i" in e else None
        start = float(e.get("start_s", e["t"]))
        out.append(
            dict(
                e,
                t=float(e["t"]),
                start=start,
                end=start + len(snd) / sr if snd is not None and sr else None,
                heavy=bool(e["heavy"])
                if "heavy" in e
                else any(k in name for k in HEAVY),
                lead=any(k in name for k in LEAD_IN),
                name=_name(e),
            )
        )
    return out


def _span(es):
    ts = [e["t"] for e in es]
    return round(min(ts), 3), round(max(ts), 3)


def stack_rows(ctx):
    """Q804 NOTE, one row per stack (cinetic score.py stack_guard): 2+ heavy sounds within 3 frames; anything
    within 3 frames of a payoff cue, or a lead-in still sounding 0.1 s before it; more than 2 sounds in any 100 ms
    (a taste rule). A riser or whoosh whose end or landmark lands within 3 frames or 100 ms (whichever is longer: the
    template's whoosh apex leads its hit by a fixed 80 ms at any fps) of a heavy sound is one gesture with it (a riser
    into a boom), so it never counts. Honours ALLOW['Q804']. No cue sheet: one NOTE (the guard is NOTE-level and a
    sheet is not a declared expectation); a sheet that cannot be read: NOT CHECKED."""
    if ctx.declared("SILENT"):
        return [C.row(True, "Q804", "no audio by design (SILENT): stack guard n/a", "")]
    entries, sounds, sr, problem = _sheet(ctx.workdir)
    if problem == "missing":
        return [
            C.row(
                False,
                "Q804",
                f"no cue sheet ({C.CUESHEET}): the stack guard needs one",
                "place sounds with audio.place or synth.place so it is written",
                note=True,
                considered=0,
            )
        ]
    if problem:
        return [
            C.not_checked(
                "Q804",
                f"{C.CUESHEET} could not be read ({problem}), so the stack guard did not run",
                f"rerun run_all.py full so audio.py writes {C.CUESHEET} and {C.CUE_SOUNDS} again",
            )
        ]
    ev = _events(entries, sounds, sr)
    skipped = len(entries) - len(ev)
    win = STACK_F / ctx.fps + 1e-6
    lead_win = max(win, DENSE_S + 1e-6)
    heavy = [e for e in ev if e["heavy"]]
    exempt = []
    for e in ev:
        if e["lead"] and not e["heavy"]:
            marks = [e["t"]] + ([e["end"]] if e["end"] is not None else [])
            if any(
                h["t"] >= e["start"] and any(abs(h["t"] - m) <= lead_win for m in marks)
                for h in heavy
            ):
                exempt.append(e)
    ev = [e for e in ev if not any(e is x for x in exempt)]
    rows, used, allowed = [], set(), 0

    def add(es, msg, fix, worst, metric, limit):
        nonlocal allowed
        if ctx.allowed("Q804", worst, win):
            allowed += 1
            return
        t0, t1 = _span(es)
        rows.append(
            C.Row(
                C.NOTE,
                "Q804",
                msg,
                fix,
                t0=t0,
                t1=t1,
                worst_t=round(worst, 3),
                item=" + ".join(e["name"] for e in es),
                metric=metric,
                limit=limit,
                considered=len(ev),
            )
        )

    for p, lab in payoffs(ctx.scenes):
        near = [e for e in ev if abs(e["t"] - p) <= win and not e["lead"]]
        leads = [
            e
            for e in ev
            if e["lead"]
            and p - 0.75 <= e["t"] <= p + win
            and (e["end"] is None or e["end"] >= p - 0.1)
        ]
        used.update(id(e) for e in near + leads)
        if len(near) + len(leads) >= 2:
            es = sorted(near + leads, key=lambda e: (e["t"], e["start"]))
            add(
                es,
                f"stacked payoff {lab or p!r} at {p:.2f} s: {' + '.join(e['name'] for e in es)}: a second sound "
                f"within {STACK_F} frames, or a lead-in still sounding 0.1 s before it (a reveal lands on one "
                "clean element)",
                "keep one sound on the payoff; cut the rest or move them 4+ frames off (a riser ending on a boom "
                "is fine), or list the time in ALLOW['Q804'] if the stack is designed",
                p,
                len(es),
                1,
            )
    rest = sorted(
        (e for e in ev if id(e) not in used), key=lambda e: (e["t"], e["start"])
    )
    clusters = []
    for e in rest:  # sounds chained within 3 frames or 100 ms are one candidate stack
        if clusters and e["t"] - clusters[-1][-1]["t"] <= max(win, DENSE_S + 1e-6):
            clusters[-1].append(e)
        else:
            clusters.append([e])
    for cl in clusters:
        hv = [e for e in cl if e["heavy"]]
        pairs = [(a, b) for a, b in itertools.pairwise(hv) if b["t"] - a["t"] <= win]
        dense = max(
            ([f for f in cl if 0 <= f["t"] - e["t"] <= DENSE_S + 1e-6] for e in cl),
            key=len,
        )
        if not pairs and len(dense) <= DENSE_N:
            continue
        why, inv = [], []
        if pairs:
            gap = min(b["t"] - a["t"] for a, b in pairs) * ctx.fps
            why.append(
                f"{len({id(x) for pr in pairs for x in pr})} heavy {gap:.0f} frame(s) apart "
                f"(want more than {STACK_F})"
            )
            inv += [x for pr in pairs for x in pr]
        if len(dense) > DENSE_N:
            why.append(f"{len(dense)} in 100 ms (over {DENSE_N}, a taste rule)")
            inv += dense
        es = sorted(
            {id(e): e for e in inv}.values(), key=lambda e: (e["t"], e["start"])
        )
        add(
            es,
            f"stacked sounds at {es[0]['t']:.2f} s: {' + '.join(e['name'] for e in es)}: {'; '.join(why)}",
            "one sound per visible event: keep the heaviest, move the others 4+ frames off or cut them, or list "
            "the time in ALLOW['Q804'] if the stack is designed",
            es[0]["t"],
            round(gap, 2) if pairs else len(dense),
            STACK_F if pairs else DENSE_N,
        )
    if rows:
        return rows
    extra = [
        f"{len(exempt)} lead-in(s) into a heavy sound not counted" if exempt else "",
        f"{allowed} stack(s) allowed by ALLOW['Q804']" if allowed else "",
        f"{skipped} music-bed or muted sounds not counted" if skipped else "",
    ]
    extra = "; ".join(x for x in extra if x)
    return [
        C.row(
            True,
            "Q804",
            f"no stacked sounds: {len(ev)} placed sounds checked (heavy within {STACK_F} frames, payoff "
            f"neighbours, over {DENSE_N} in 100 ms)" + (f"; {extra}" if extra else ""),
            "",
            considered=len(ev),
        )
    ]


def check_rows(ctx):
    return peak_rows(ctx) + stack_rows(ctx)
