# contract.py : what every engine module shares: the frame clock, the QA row, the files a build writes, and how
# they are read. No module here imports scenes or engine, so anything can import this first.
import hashlib
import json
import math
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

# ---- frame clock (Z06): one rounding rule everywhere, nearest frame and nearest sample ----


def frame_of(t, fps):
    """Nearest frame index of time t. frame_of(i / fps, fps) == i for every i, despite float error."""
    return math.floor(t * fps + 0.5 + 1e-9)


def t_of(frame, fps):
    return frame / fps


def snap(t, fps):
    """t moved onto the frame grid."""
    return frame_of(t, fps) / fps


def mid_frame(a, b, fps):
    """Middle frame of a span [a, b) whose end b is the first frame after it (qa.text_spans), never b itself: a
    text on screen for one frame has its middle on the half frame, which frame_of rounds into the next frame."""
    return min(frame_of((a + b) / 2, fps), frame_of(b, fps) - 1)


def sample_of(t, sr):
    """Nearest sample index of time t (int(t * sr) truncates and drifts up to one sample early)."""
    return math.floor(t * sr + 0.5 + 1e-9)


def frame_sample(frame, fps, sr):
    """First sample of a frame: 1470 at 44.1 kHz and 30 fps, 1837.5 rounded at 24 fps."""
    return math.floor(frame * sr / fps + 0.5 + 1e-9)


def stepped(t, rate):
    """Index of a held step at `rate` per second (held drawings, typewriters, gear steps), safe on frame times."""
    return math.floor(t * rate + 1e-4)


def on_grid(t, fps, tol=1e-3):
    """True when t sits within tol of a frame (tol in frames)."""
    return abs(t * fps - round(t * fps)) <= tol


def whole_frame_beat(bpm, fps):
    """True when one beat is a whole number of frames (120 BPM at 30 fps is 15 frames; 128 BPM is not)."""
    f = 60 / bpm * fps
    return abs(f - round(f)) < 1e-6


# ---- QA rows (Z11) ----

PASS, FIX, NOTE, NOT_CHECKED = "PASS", "FIX", "NOTE", "NOT CHECKED"


@dataclass
class Row:
    """One gate result. Unpacks like the old (status, code, msg, fix) tuple, so `for st, code, msg, fix in rows` works."""

    status: str  # PASS, FIX, NOTE or NOT CHECKED (NOT CHECKED fails the run with exit code 2 unless a FIX is also present)
    code: str
    msg: str
    fix: str = ""
    t0: float | None = None  # first and last second the finding covers
    t1: float | None = None
    worst_t: float | None = None  # the one moment a reviewer should open first
    item: str | None = None  # what failed: the string, the cue label, the scene name
    metric: float | None = None  # the measured number (contrast ratio, dBTP, ms, ...)
    limit: float | None = None  # the number it was held to
    spans: list = field(
        default_factory=list
    )  # [(t0, t1), ...] merged runs of frames, from merge_spans
    considered: int | None = (
        None  # how many items the gate looked at; 0 with no opt-out is NOT CHECKED
    )

    def __iter__(self):
        yield from (self.status, self.code, self.msg, self.fix)

    def __getitem__(self, i):
        return (self.status, self.code, self.msg, self.fix)[i]

    def __len__(self):
        """The old tuple's length, so code written for (status, code, msg, fix) keeps working."""
        return 4

    def as_dict(self):
        d = asdict(self)
        d["spans"] = [list(s) for s in self.spans]
        return d


def row(ok, code, msg, fix, note=False, **kw):
    """PASS when ok, else NOTE (note=True) or FIX. The fix text is kept only on a failure."""
    status = PASS if ok else NOTE if note else FIX
    return Row(status, code, msg, "" if ok else fix, **kw)


def not_checked(code, msg, fix, **kw):
    """A NOT CHECKED row; considered defaults to 0 (a caller may say how many it looked at before it stopped)."""
    kw.setdefault("considered", 0)
    return Row(NOT_CHECKED, code, msg, fix, **kw)


def exit_code(rows):
    """0 all clear, 1 any FIX, 2 something could not be checked (and nothing to FIX)."""
    if any(r.status == FIX for r in rows):
        return 1
    return 2 if any(r.status == NOT_CHECKED for r in rows) else 0


def summary(rows, label="QA"):
    n = {s: sum(r.status == s for r in rows) for s in (FIX, NOTE, NOT_CHECKED)}
    state = (
        f"FIX ({n[FIX]})"
        if n[FIX]
        else f"NOT CHECKED ({n[NOT_CHECKED]})"
        if n[NOT_CHECKED]
        else "PASS"
    )
    return f"{label}: {state} ({len(rows)} checks, {n[FIX]} FIX, {n[NOTE]} NOTE, {n[NOT_CHECKED]} NOT CHECKED)"


def line(r):
    """The printed form of a row: status, code, message, the worst moment, how many items, then -> fix. ASCII
    only (other characters as \\u escapes): a registered string with an arrow or a Greek letter once raised
    UnicodeEncodeError on a redirected Windows stdout (cp1252) and rejected a build whose gates all passed."""
    s = f"{r.status:<4} {r.code:<5} {r.msg}"
    if r.status != PASS and r.worst_t is not None:
        s += f" [worst {r.worst_t:.2f} s]"
    if r.considered is not None:
        s += f" [{r.considered} checked]"
    s += f" -> {r.fix}" if r.fix else ""
    return s.encode("ascii", "backslashreplace").decode("ascii")


def _plain(o):
    """json.dumps' fallback: numpy scalars and arrays as Python numbers and lists, anything else as its str."""
    return o.tolist() if hasattr(o, "tolist") else str(o)


def write_rows(rows, path):
    Path(path).write_text(
        json.dumps([r.as_dict() for r in rows], indent=1, default=_plain),
        encoding="utf-8",
    )


def read_rows(path):
    rows = [Row(**d) for d in json.loads(Path(path).read_text(encoding="utf-8"))]
    # JSON has no tuples; spans come back as the (t0, t1) pairs merge_spans makes
    for r in rows:
        r.spans = [tuple(s) for s in r.spans]
    return rows


def merge_spans(times, fps, pad_frames=2):
    """Sorted runs [(t0, t1), ...] of the given frame times; gaps up to pad_frames frames join one run."""
    fr = sorted({frame_of(t, fps) for t in times})
    runs = []
    for f in fr:
        if runs and f - runs[-1][1] <= pad_frames:
            runs[-1][1] = f
        else:
            runs.append([f, f])
    return [(a / fps, b / fps) for a, b in runs]


def worst_of(spans):
    """Middle of the longest span: the fallback worst_t when a gate has no better measure."""
    if not spans:
        return None
    a, b = max(spans, key=lambda s: s[1] - s[0])
    return round((a + b) / 2, 3)


# ---- what a scenes.py declares (opt-outs, allow lists, cues) ----

OPT_OUTS = (
    "NO_TEXT",  # no on-screen text by design: the text gates are n/a, not NOT CHECKED
    "NO_CUES",  # no sound cue the picture must hit, by design
    "SILENT",  # no audio track on purpose (same as --silent)
)


def declared(scenes, name):
    return bool(scenes is not None and getattr(scenes, name, False))


def allowed(scenes, code, t, tol):
    """True when scenes.ALLOW[code] lists t (a time, or a (t0, t1) span) within tol seconds: a designed one-frame
    flash, an intended freeze, a planned off-grid cut. Used only by NOTE-level scans."""
    for a in getattr(scenes, "ALLOW", {}).get(code, []) if scenes is not None else []:
        lo, hi = a if isinstance(a, (tuple, list)) else (a, a)
        if lo - tol <= t <= hi + tol:
            return True
    return False


def cues(scenes):
    """scenes.CUES as dicts {t, label, kind, ...}, sorted by time. Entries may be (t, label), (t, label, kind) or
    dicts; kind is "both" (default), "audio" or "picture". A dict entry keeps every other key it carries, for example
    payoff=True (the stack guard keeps other sounds off a payoff cue). CUES may also be one dict of label to a time
    or a list of times."""
    raw = getattr(scenes, "CUES", None) or []
    if isinstance(
        raw, dict
    ):  # CUES = dict(bell=[t0, t1], warm=t): label to a time or a list of times
        raw = [
            (t, label)
            for label, v in raw.items()
            for t in (v if isinstance(v, (list, tuple)) else [v])
        ]
    out = []
    for c in raw:
        if isinstance(c, dict):
            d = {
                **c,
                "t": float(c["t"]),
                "label": c.get("label", ""),
                "kind": c.get("kind", "both"),
            }
        else:
            d = {
                "t": float(c[0]),
                "label": c[1] if len(c) > 1 else "",
                "kind": c[2] if len(c) > 2 else "both",
            }
        out.append(d)
    return sorted(out, key=lambda d: d["t"])


# ---- files a build writes (all in the working folder) ----

VIDEO = "video.mp4"  # the silent picture encode; run_all muxes it with mix.wav into OUT (Z01)
FRAMES_HASH = "frames.hash"  # JSON {"w", "h", "fps", "n", "algo", "hash": [hex, ...]} one digest per drawn frame
THUMBS = "thumbs.npy"  # uint8 (n, 108, 192) grey copy of every drawn frame, before the encode
MIX_RAW = "mix_raw.wav"  # the pre-master mix (hash this, not mix.wav: the master gain moves every sample)
MIX = "mix.wav"  # the mastered mix, 48 kHz
SFX = "sfx.wav"  # the SFX bus alone, pre-master, same scale and rate as mix_raw.wav (Z12 measures cues on it)
CUESHEET = "cuesheet.json"  # every placed sound, see CUESHEET_KEYS
CUE_SOUNDS = "cue_sounds.npz"  # each placed sound's own buffer, key "c<i>", pre-gain, at the sheet's sr
REVIEW_TIMES = (
    "review_times.json"  # every moment a reviewer must see, see add_review_times
)
QA_PROOF = "qa_proof.json"  # rows from run_all.py proof
QA_JSON = "qa.json"  # rows from qa.py check --json
APPROVED = "approved"  # folder qa.py approve writes (Z04, Z10)
APPROVAL = "approval.json"  # inside APPROVED
AUDIO_PNG = "review/audio.png"  # qa.py audiostrip (Z20)
GANTT = "proof_gantt.png"  # proof.py timeline strip (Z19)
BUILD = "build.json"  # {"w", "h", "fps", "ss"} written by run_all.py, read by every standalone CLI

CUESHEET_KEYS = {
    "i": "index, also the key c<i> in cue_sounds.npz",
    "label": "the CUES label this sound serves ('' when it serves none)",
    "sound": "generator name, for example 'hit' or 'whoosh'",
    "t": "the event time in seconds where the landmark lands, including any designed offset (place(offset=...))",
    "align": "onset, peak, end or pad: which instant of the sound sits on t",
    "landmark_s": "seconds from the sound's first sample to its landmark",
    "start_s": "seconds where the first kept sample was placed (t - landmark_s, clipped at 0; CUE_SOUNDS still holds "
    "the whole buffer, head included, so a trimmed sound is measured from t - landmark_s)",
    "gain": "linear gain applied when placed",
    "peak_dbfs": "the sound's own sample peak before gain, dBFS",
    "heavy": "true for kick, hit, boom, impact, drop: the stack guard counts these",
    "bus": "sfx or music",
    "trim_s": "seconds cut off the head when the sound would start before 0 (the kept head fades in over 3 ms)",
    "audible_s": "seconds from the sound's first sample to its audible onset, the -15 dB pad point (every row, put() "
    "rows included)",
    "landmark_tol": "the tolerance of a measured landmark, in seconds (0 for a landmark the generator reports)",
}


def write_cuesheet(entries, sounds, sr, folder="."):
    """entries: list of dicts with CUESHEET_KEYS; sounds: {i: np.ndarray}. Writes CUESHEET and CUE_SOUNDS."""
    Path(folder, CUESHEET).write_text(
        json.dumps({"sr": sr, "cues": entries}, indent=1), encoding="utf-8"
    )
    np.savez_compressed(
        Path(folder, CUE_SOUNDS),
        **{f"c{i}": np.asarray(s, np.float32) for i, s in sounds.items()},
    )


def read_cuesheet(folder="."):
    """(entries, sounds or None, sr); entries is [] when the build wrote no sheet."""
    p = Path(folder, CUESHEET)
    if not p.exists():
        return [], None, None
    j = json.loads(p.read_text(encoding="utf-8"))
    npz = Path(folder, CUE_SOUNDS)
    sounds = dict(np.load(npz)) if npz.exists() else None
    return j["cues"], sounds, j["sr"]


def write_build(w, h, fps, ss=1, folder="."):
    """Record the frame size a build uses, so qa.py purity, lint, diff and proof.py keys never guess it."""
    Path(folder, BUILD).write_text(
        json.dumps({"w": w, "h": h, "fps": fps, "ss": ss}), encoding="utf-8"
    )


def read_build(folder="."):
    """(w, h, fps, ss) from BUILD, or None when run_all.py has not written one yet."""
    p = Path(folder, BUILD)
    if not p.exists():
        return None
    b = json.loads(p.read_text(encoding="utf-8"))
    return b["w"], b["h"], b["fps"], b.get("ss", 1)


# ---- frame digests and thumbs (Z01 writes them; Z04, Z09, Z17 read them) ----

THUMB_SIZE = (192, 108)  # w, h


def frame_digest(img, raw=None):
    """blake2b-8 of mode, size and raw bytes: identical pixels give identical digests in any process. raw: the
    img.tobytes() the caller already made (the render worker pipes it), so the bytes are not copied twice."""
    h = hashlib.blake2b(digest_size=8)
    h.update(f"{img.mode}{img.size}".encode())
    h.update(img.tobytes() if raw is None else raw)
    return h.hexdigest()


def thumb(img):
    """uint8 (108, 192) grey copy for scans and diffs (PIL luma, box filter). Same function at render and at diff."""
    return np.asarray(img.convert("L").resize(THUMB_SIZE, Image.BOX), np.uint8)


SRGB_LUT = np.where(
    np.arange(256) / 255 <= 0.04045,
    np.arange(256) / 255 / 12.92,
    ((np.arange(256) / 255 + 0.055) / 1.055) ** 2.4,
).astype(np.float32)  # IEC 61966-2-1 code value to linear light


def lin_thumb(img):
    """float32 (108, 192, 3) linear-light RGB of a drawn frame, averaged down in linear light: the frame the flash
    gate measures, on the same scale as Ctx.lin()."""
    a = SRGB_LUT[np.asarray(img.convert("RGB"))]
    return np.stack(
        [
            np.asarray(Image.fromarray(a[..., c], "F").resize(THUMB_SIZE, Image.BOX))
            for c in range(3)
        ],
        -1,
    ).astype(np.float32)


def write_frame_manifest(digests, w, h, fps, folder=".", ss=1):
    Path(folder, FRAMES_HASH).write_text(
        json.dumps(
            {
                "w": w,
                "h": h,
                "fps": fps,
                "ss": ss,
                "n": len(digests),
                "algo": "blake2b-8",
                "hash": digests,
            }
        ),
        encoding="utf-8",
    )


def read_frame_manifest(folder="."):
    p = Path(folder, FRAMES_HASH)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def block64(g):
    """(n, 108, 192) grey to (n, 36, 64) by exact 3x3 block mean: the flash gate's old resolution from one decode."""
    n = len(g)
    return g.reshape(n, 36, 3, 64, 3).mean((2, 4))


# ---- review times (proof.py, qa.py check --json, qa.py diff and the scans all add to one list) ----

KINDS = (
    "finding",
    "changed",
    "pop",
    "cut",
    "window",
    "key",
    "audio",
    "rest",
)  # highest rank first
SEVERITY = {FIX: 3, NOT_CHECKED: 2, NOTE: 1, PASS: 0}


def read_review_times(path=REVIEW_TIMES):
    p = Path(path)
    if not p.exists():
        return []
    out = []
    for e in json.loads(p.read_text(encoding="utf-8")):
        e.setdefault("kind", "key")
        e.setdefault("kinds", [e["kind"]])
        e.setdefault("code", None)
        e.setdefault("status", None)
        e.setdefault("strip", False)
        out.append(e)
    return out


def add_review_times(entries, path=REVIEW_TIMES):
    """Merge entries {t, why, kind, code?, status?, strip?, n?} into the file: one entry per time (3 decimals),
    reasons joined with '; ', every kind kept in `kinds` (ranked as KINDS) with `kind` the highest, `status` the
    most severe one seen (FIX over NOT CHECKED over NOTE), strip kept if any asks for it. Returns the merged list."""
    merged = {}
    rank = {k: i for i, k in enumerate(KINDS)}
    for e in read_review_times(path) + list(entries):
        t = round(float(e["t"]), 3)
        m = merged.setdefault(
            t,
            {
                "t": t,
                "why": "",
                "kind": None,
                "kinds": [],
                "code": None,
                "status": None,
                "strip": False,
            },
        )
        # part by part: a reason that holds "; " came back once more on every merge
        have = m["why"].split("; ") if m["why"] else []
        for part in e.get("why", "").split("; "):
            if part and part not in have:
                have.append(part)
        m["why"] = "; ".join(have)
        for k in [e.get("kind")] + list(e.get("kinds", [])):
            if k and k not in m["kinds"]:
                m["kinds"].append(k)
        m["kinds"].sort(key=lambda k: rank.get(k, len(rank)))
        m["kind"] = m["kinds"][0] if m["kinds"] else "key"
        m["code"] = m["code"] or e.get("code")
        st = e.get("status")
        if st and SEVERITY.get(st, -1) > SEVERITY.get(m["status"], -1):
            m["status"] = st
        m["strip"] = m["strip"] or bool(e.get("strip"))
        if "n" in e:
            m["n"] = e["n"]
    out = sorted(merged.values(), key=lambda e: e["t"])
    Path(path).write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


# ---- colour (Z16): BT.709 limited range, written and tagged; probed on ffmpeg 9.0.2 on 2026-10-28 ----
# Untagged RGB to yuv420p came back up to 40 levels off on pure green when decoded as BT.709; this chain read back
# bt709/tv tags and at most 1 level of error on saturated swatches.

COLOR_VF = (
    "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,"
    "setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv"
)
COLOR_FLAGS = [
    "-colorspace",
    "bt709",
    "-color_primaries",
    "bt709",
    "-color_trc",
    "bt709",
    "-color_range",
    "tv",
]
# How a player reads the file; prefix every RGB decode with it. accurate_rnd rounds instead of truncating: without it a
# dark end card drawn at 32.42 decoded at 31.02 (now 32.32), which once flipped the template's Q502 to FIX.
DECODE_709 = (
    "scale=in_color_matrix=bt709:in_range=tv:flags=accurate_rnd+full_chroma_int"
)
# Linear light for the flash gate: the file's RGB read as sRGB code values (WCAG defines luminance on sRGB), turned
# to linear light, and only then averaged down. Averaging code values first underrated sparse content (1 px white lines
# every 10 px, 10 percent linear, passed until they were 5 px); this reads them 0.0992 and grey 128 as 0.2162 (sRGB
# 0.2158).
DECODE_LINEAR = "zscale=tin=iec61966-2-1:min=709:rin=limited:pin=709:t=linear:npl=100:p=709,format=gbrpf32le"
# The audio encode in the mux. 320k, not 192k: over 9 mixes the native AAC encoder raised the decoded true peak by
# up to 1.23 dB at 192k and at most 0.45 dB at 320k (2026-10-28), so the -2.0 dBTP master ceiling keeps 0.55 dB
# under the -1 dBTP gate. run_all still measures the mp4 and re-masters lower when it is over.
AAC_ARGS = ["-c:a", "aac", "-b:a", "320k"]


def mux_cmd(ff, video, mix, out):
    """The one mux: picture stream copied, audio encoded once with AAC_ARGS, cut to the shorter stream, moov first.
    mix=None muxes a silent piece. run_all.py and qa.py calib both run it, so the calibration cannot drift."""
    sound = ["-i", mix, "-map", "0:v", "-map", "1:a"] if mix else ["-map", "0:v"]
    tail = [*AAC_ARGS, "-shortest"] if mix else []
    return [
        ff,
        "-y",
        "-v",
        "error",
        "-i",
        video,
        *sound,
        "-c:v",
        "copy",
        *tail,
        "-movflags",
        "+faststart",
        out,
    ]


# ---- the Q codes: one table for every gate, its owner module, gate number and status on failure ----
# owner is the module whose function makes the row. Docs (qa-gates.md) and qa.py selftest read this table.

CODES = {
    "Q100": (
        "qa",
        0,
        "NOT CHECKED",
        "a gate module raised, so its gates did not run (item names the module)",
    ),
    "Q200": (
        "qa",
        2,
        "NOT CHECKED",
        "no text_items(t) and no NO_TEXT: gates 2 to 4 did not run (also when text_items reports nothing readable, "
        + "or only the older kit form)",
    ),
    "Q201": ("qa", 2, "FIX", "text at rest outside the 4 percent safe area"),
    "Q202": ("qa", 2, "FIX", "two texts overlapping at rest"),
    "Q203": ("qa", 2, "FIX", "two texts overlapping while either fades"),
    "Q204": (
        "qa_registry",
        2,
        "FIX",
        "text drawn that text_items(t) does not report (NOTE under alpha 0.5, under 24 px at 1080, or symbols only)",
    ),
    "Q205": (
        "qa_registry",
        2,
        "FIX",
        "registry box more than 2 px from the drawn ink box",
    ),
    "Q206": (
        "qa_registry",
        2,
        "FIX",
        "registered text covered: under 0.7 of its ink exposed",
    ),
    "Q207": ("qa", 2, "NOTE", "caption changeover gap of 3 frames to 0.5 s"),
    "Q208": (
        "qa_registry",
        2,
        "NOT CHECKED",
        "the text recorder saw no text call at all, or could not run",
    ),
    "Q209": (
        "qa_registry",
        2,
        "NOTE",
        "text_items(t) reports text at alpha 0.5 or more that nothing draws",
    ),
    "Q301": ("qa", 3, "FIX", "text under its contrast minimum"),
    "Q401": ("qa", 4, "FIX", "reading hold under the card's profile"),
    "Q402": ("qa", 4, "NOTE", "key text under 36 px at 1080"),
    "Q403": ("qa", 4, "FIX", "registered text never reaches rest (alpha 0.98)"),
    "Q404": (
        "qa",
        4,
        "FIX",
        "reveal incomplete: under 0.98 of the ink drawn at reveal_end",
    ),
    "Q501": ("qa", 5, "FIX", "first frame dark or flat"),
    "Q502": ("qa", 5, "FIX", "last frame dark"),
    "Q503": ("qa", 5, "NOTE", "end card not held 1 s"),
    "Q601": (
        "qa_scan",
        6,
        "FIX",
        "more than 3 general flashes in a 1 s window (WCAG 2.2)",
    ),
    "Q602": ("qa_scan", 6, "FIX", "more than 3 red flashes in a 1 s window (WCAG 2.2)"),
    "Q603": (
        "qa_scan",
        6,
        "NOTE",
        "4 to 6 transitions held for 4 of 5 s (extended band)",
    ),
    "Q701": ("qa", 7, "FIX", "duration off"),
    "Q702": ("qa", 7, "FIX", "fps off"),
    "Q703": ("qa", 7, "FIX", "resolution off"),
    "Q704": ("qa", 7, "FIX", "frame count off"),
    "Q705": ("qa", 7, "FIX", "not yuv420p"),
    "Q706": ("qa", 7, "FIX", "no audio stream"),
    "Q707": ("qa", 7, "FIX", "colour tags not bt709 / tv"),
    "Q708": ("qa", 7, "FIX", "colour round trip off by more than 8 levels"),
    "Q801": ("qa", 8, "FIX", "integrated loudness off -14 LUFS"),
    "Q802": (
        "qa_stack",
        8,
        "FIX",
        "true peak above -1 dBTP, with the cues that stack there",
    ),
    "Q803": ("qa", 8, "NOTE", "near-silent second inside the piece"),
    "Q804": (
        "qa_stack",
        8,
        "NOTE",
        "heavy sounds stacked within 3 frames, or over 2 cues in 100 ms",
    ),
    "Q805": ("audio", 8, "FIX", "master not linear, or missed its loudness target"),
    "Q901": ("qa", 9, "NOTE", "scene start or cut off the BPM grid"),
    "Q902": (
        "qa_sync",
        9,
        "FIX",
        "cue late by more than 1 frame or early by more than 40 ms (NOTE outside -5..+15 ms)",
    ),
    "Q903": (
        "qa_sync",
        9,
        "FIX",
        "audio lags the mux: decoded mp4 vs mix.wav over 1 ms, or start times differ",
    ),
    "Q904": ("qa_lint", 9, "NOTE", "SCHEDULE or CUES time off the frame grid"),
    "Q905": ("qa_lint", 9, "NOTE", "one beat is not a whole number of frames"),
    "Q906": ("qa_sync", 9, "FIX", "calibration flash and blip not at 0 ms"),
    "Q1001": ("qa", 10, "FIX", "file over its size budget"),
    "Q1002": ("qa", 10, "NOTE", "bitrate over 12 Mb/s"),
    "Q1101": ("qa_scan", 1, "NOTE", "one-frame pop"),
    "Q1102": ("qa_scan", 1, "NOTE", "frozen run of 3 s or more outside a hold"),
    "Q1103": ("qa_scan", 1, "NOTE", "hard cut not on a SCHEDULE boundary or a cue"),
    "Q1104": ("qa_scan", 1, "NOTE", "stall: a repeated frame inside motion"),
    "Q1105": (
        "qa_scan",
        1,
        "FIX",
        "the encoded file does not match the drawn frames (thumbs.npy): a wrong-size or sheared encode",
    ),
    "Q1201": ("qa_purity", 1, "FIX", "draw(t) not pure: same frame, different pixels"),
    "Q1202": ("qa_lint", 1, "FIX", "unseeded randomness or wall-clock time in scenes"),
    "Q1203": ("qa_lint", 1, "NOTE", "module state written inside draw"),
    "Q1204": ("qa_lint", 1, "NOTE", "scenes.py redefines an engine helper"),
    "Q1205": ("qa_lint", 1, "NOTE", "text drawn outside the engine text helpers"),
    "Q1206": ("qa_lint", 1, "NOTE", "colour literal outside the palette block"),
    "Q1301": (
        "qa_approve",
        1,
        "FIX",
        "approval stale: scenes changed since the PASS, or the picture is not the approved one (NOTE: only the audio "
        + "changed, or a human override is recorded)",
    ),
    "Q1302": (
        "qa_approve",
        1,
        "FIX",
        "regression: a gate went from PASS to FIX against the baseline",
    ),
    "Q1303": (
        "qa_approve",
        1,
        "FIX",
        "undeclared change: frames or 100 ms audio blocks changed outside --expect (NOTE inside it), or an --expect "
        + "window that saw no change",
    ),
    "Q1304": (
        "qa_approve",
        1,
        "NOT CHECKED",
        "environment changed since approval: re-approve (NOTE when the redrawn key frames did not move)",
    ),
}

# Modules whose check_rows(ctx) -> [Row] qa.py check calls, in this order, and whose add_cli(sub) adds subcommands.
GATE_MODULES = ("qa_scan", "qa_stack", "qa_sync", "qa_registry", "qa_approve")
CLI_MODULES = (
    "qa_purity",
    "qa_lint",
    "qa_approve",
    "qa_sync",
    "qa_audiostrip",
    "qa_selftest",
)


# ---- the ffmpeg every stage runs ----


def find_ffmpeg():
    """The ffmpeg to run: the one on PATH, else the usual Homebrew and /usr/local places; None when there is none.
    run_all.py and qa.py both use it, so the encode and the checks run the same binary."""
    return shutil.which("ffmpeg") or next(
        (
            p
            for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg")
            if Path(p).exists()
        ),
        None,
    )


def ffprobe_of(ff):
    """The ffprobe beside an ffmpeg: "ffmpeg" gives "ffprobe", C:/x/ffmpeg.exe gives C:/x/ffprobe.exe."""
    p = Path(ff)
    return str(p.with_name(p.name.replace("ffmpeg", "ffprobe")))


# ---- what a gate module gets from qa.py check ----


class Ctx:
    """The file under check plus everything decoded from it once. Gate modules read from here and never decode
    the file again themselves."""

    def __init__(
        self, path, probe, fps, w, h, scenes=None, workdir=None, opts=None, ff="ffmpeg"
    ):
        self.path, self.probe, self.fps, self.w, self.h = str(path), probe, fps, w, h
        self.scenes, self.ff = scenes, ff
        self.workdir = Path(workdir) if workdir else Path(path).resolve().parent
        # write review_times.json only into a build folder that was named
        self.record = workdir is not None
        # bpm, max_mb, silent, baseline, json, ... as given on the command line
        self.opts = opts or {}
        self.loudness = None  # qa.loud(path) summary {I, LRA, peak}, set by qa.check before the gate modules run
        self.rows = []  # every row qa.check made before the gate modules, then theirs as each returns (Q1302 reads it)
        self._rgb = self._lin = self._grey = self._audio = None

    def _ff(self, args):
        """stdout of ffmpeg on the file. stdin is closed: an inherited stdin let a piped "q" stop the decode after
        200 of 1800 frames, and the gates went on with the rest missing."""
        return subprocess.run(
            [self.ff, "-nostdin", "-v", "error", "-i", self.path, *args, "-"],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            check=True,
        ).stdout

    def _counted(self, a):
        """a, after checking it holds every frame ffprobe counted (within 1): a short decode raises rather than
        letting each gate pass on part of the film."""
        want = self.probe.get("frames") or 0
        if want and abs(len(a) - want) > 1:
            raise RuntimeError(
                f"decoded {len(a)} of the {want} frames ffprobe counts in {self.path}"
            )
        return a

    def rgb(self):
        """uint8 (n, 108, 192, 3) of every encoded frame, decoded as a player would (BT.709 limited). Convert to RGB at
        full size first, then average down: one combined scale read a dark end card 0.86 levels low (25.06 vs 25.92)."""
        if self._rgb is None:
            w, h = THUMB_SIZE
            raw = self._ff(
                [
                    "-vf",
                    f"{DECODE_709},format=rgb24,scale={w}:{h}:flags=area",  # convert, then scale
                    "-f",
                    "rawvideo",
                ]
            )
            self._rgb = self._counted(np.frombuffer(raw, np.uint8).reshape(-1, h, w, 3))
        return self._rgb

    def lin(self):
        """float32 (n, 108, 192, 3) linear-light RGB of every encoded frame (DECODE_LINEAR, then an area average in
        linear light), for the flash gate. About 0.45 GB for 60 s at 30 fps; cached like rgb()."""
        if self._lin is None:
            w, h = THUMB_SIZE
            raw = self._ff(
                ["-vf", f"{DECODE_LINEAR},scale={w}:{h}:flags=area", "-f", "rawvideo"]
            )
            g = np.frombuffer(raw, np.float32).reshape(-1, 3, h, w)  # planes G, B, R
            self._lin = self._counted(
                np.ascontiguousarray(g[:, [2, 0, 1]].transpose(0, 2, 3, 1))
            )
        return self._lin

    def grey(self):
        """uint8 (n, 108, 192) PIL-style luma of rgb(): the same scale as thumbs.npy. Cached: built twice, it was
        7.6 s of a 13.4 s check on a 60 s film."""
        if self._grey is None:
            c = self.rgb().astype(np.float32)
            self._grey = np.clip(
                c @ np.array([0.299, 0.587, 0.114], np.float32) + 0.5, 0, 255
            ).astype(np.uint8)
        return self._grey

    def grey64(self):
        return block64(self.grey())

    def audio(self, sr=48000, mono=True):
        """float32 audio of the file at sr, cached per (sr, mono); empty when the file has no audio. mono=True is the
        mean of the channels (ffmpeg's -ac 1 reads dual mono 3.01 dB hot); mono=False is (n, 2), which true-peak
        work needs because the AAC encode makes the two channels of a dual-mono mix differ (up to 0.66 measured).
        A mono file is read as mono and copied to both columns: -ac 2 upmixes it 3.01 dB down per channel."""
        self._audio = self._audio or {}
        if (sr, mono) not in self._audio:
            if not self.probe.get("acodec"):
                self._audio[sr, mono] = np.zeros((0,) if mono else (0, 2), np.float32)
            else:
                ac = 1 if self.probe.get("channels") == 1 else 2
                raw = self._ff(
                    [
                        "-vn",
                        "-af",
                        "aresample=first_pts=0",
                        "-ac",
                        str(ac),
                        "-ar",
                        str(sr),
                        "-f",
                        "f32le",
                    ]
                )
                st = np.frombuffer(raw, np.float32).reshape(-1, ac)
                if mono:
                    self._audio[sr, mono] = st.mean(1, dtype=np.float32)
                else:
                    self._audio[sr, mono] = np.repeat(st, 2 // ac, axis=1)
        return self._audio[sr, mono]

    def allowed(self, code, t, tol=None):
        return allowed(self.scenes, code, t, 1 / self.fps if tol is None else tol)

    def declared(self, name):
        return declared(self.scenes, name) or (
            name == "SILENT" and bool(self.opts.get("silent"))
        )
