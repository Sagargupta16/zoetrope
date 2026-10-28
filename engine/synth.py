# synth.py : numpy-only instrument kit (no scipy), each sound's landmarks, and the one placement path (place, put,
# put_peak) that records the cue sheet. `python synth.py out.wav` writes a 4 s 120 BPM demo (stereo 16-bit, 44.1 kHz)
import contextlib
import math
import sys
import warnings
import wave
import weakref
import zlib
from pathlib import Path

import contract as C
import numpy as np

SR = 44100
# kept for old scores that still draw from synth.rng; the generators and kits seed per sound (rng_for, noise)
rng = np.random.RandomState(7)


def tt(n):
    return np.arange(n) / SR


def ex(n, tau):
    return np.exp(-tt(n) / tau)


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def rng_for(name, *args):
    """A numpy Generator seeded from a sound's name and arguments (crc32 of their text, numbers as %.9g): one stream
    per sound, so adding, removing or reordering one sound never changes another's draws (a shared RandomState
    shifted every later sound). Use it for phases, jitter and noise alike."""
    key = "|".join(
        [name]
        + [
            f"{float(a):.9g}" if isinstance(a, (int, float, np.number)) else str(a)
            for a in args
        ]
    )
    return np.random.default_rng(zlib.crc32(key.encode()))


def noise(name, n, *args):
    """n samples of uniform noise in [-1, 1) from rng_for(name, *args)."""
    return rng_for(name, *args).uniform(-1, 1, n)


_KNOWN = {}  # id(sound) -> what its generator knows about it ({"attack": s} for pad's linear ramp)


def _known(sig, **facts):
    """Remember what a generator knows about the array it returns, for as long as that array lives, so place() can
    use the exact value instead of measuring it. A copy or a scaled array is a new object and is measured instead."""
    _KNOWN[id(sig)] = facts
    weakref.finalize(sig, _KNOWN.pop, id(sig), None)
    return sig


def lp(x, fc):  # one-pole low-pass (no scipy)
    a = np.exp(-2 * np.pi * fc / SR)
    y = np.empty_like(x)
    s = 0.0
    for i in range(len(x)):
        s = (1 - a) * x[i] + a * s
        y[i] = s
    return y


def hp(x, fc):
    return x - lp(x, fc)


def kick(g=1.0, seed=0):
    n = int(0.4 * SR)
    t = tt(n)
    ph = 2 * np.pi * np.cumsum(48 + 130 * np.exp(-t * 30)) / SR
    click = hp(noise("kick", n, seed) * ex(n, 0.003), 2500) * 0.4
    return np.tanh(1.6 * (np.sin(ph) * ex(n, 0.16) + click)) * g


def snare(g=1.0, seed=0):
    n = int(0.25 * SR)
    t = tt(n)
    return (
        hp(noise("snare", n, seed), 1500) * ex(n, 0.08) * 0.6
        + np.sin(2 * np.pi * 190 * t) * ex(n, 0.05) * 0.5
    ) * g


def hat(op=False, seed=0):
    n = int((0.2 if op else 0.05) * SR)
    return hp(noise("hat", n, op, seed), 7000) * ex(n, 0.07 if op else 0.014) * 0.4


def clap(seed=0):
    n = int(0.3 * SR)
    x = np.zeros(n)
    for k, d in enumerate([0, 0.011, 0.023]):
        i = int(d * SR)
        m = n - i
        x[i:] += hp(lp(noise("clap", m, k, seed), 5200), 900) * ex(
            m, 0.012 if k < 2 else 0.07
        )
    return x * 0.6


def saw(f, n, det=0.0):
    return 2 * ((tt(n) * f * (1 + det)) % 1.0) - 1


def bass(m, dur):
    n = int(dur * SR)
    f = hz(m)
    x = 0.6 * saw(f, n) + 0.6 * np.sin(2 * np.pi * f * tt(n))
    return (
        np.tanh(1.4 * lp(x, 420))
        * np.minimum(1, tt(n) / 0.005)
        * ex(n, dur * 0.7)
        * 0.55
    )


def pad(notes, dur, fc=1400, att=0.25):
    n = int(dur * SR)
    x = sum(saw(hz(m), n, d) for m in notes for d in (-0.006, 0, 0.007))
    x = lp(x, fc) / (3 * len(notes))
    t = tt(n)
    env = np.minimum(1, t / att) * np.clip((dur - t) / 0.3, 0, 1)
    # heard at att * 10 ** (-15 / 20) whatever the chord's beating: place() reads it from _known
    return _known(x * env, attack=att)


def pluck(m, dur=0.4):
    n = int(dur * SR)
    return (
        lp(saw(hz(m), n) * 0.6 + saw(hz(m) * 2, n, 0.003) * 0.25, 3500)
        * ex(n, 0.16)
        * np.minimum(1, tt(n) / 0.002)
    )


def riser(dur, seed=0):
    n = int(dur * SR)
    t = tt(n) / dur
    x = noise("riser", n, dur, seed)
    out = np.zeros(n)
    for i in range(0, n, 2048):
        out[i : i + 2048] = hp(
            lp(x[i : i + 2048], 500 + 6000 * t[i] ** 2), 200 + 1500 * t[i] ** 2
        )
    return out * t**2 * 3


def boom(dur=1.2):
    n = int(dur * SR)
    t = tt(n)
    return (
        np.tanh(
            2
            * np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-t * 8)) / SR)
            * ex(n, 0.5)
        )
        * 0.9
    )


def whoosh(dur=0.5, seed=0):
    n = int(dur * SR)
    t = tt(n) / dur
    x = noise("whoosh", n, dur, seed)
    out = np.zeros(n)
    for i in range(0, n, 512):
        out[i : i + 512] = hp(lp(x[i : i + 512], 400 * 20 ** t[i]), 200 * 10 ** t[i])
    return out * np.sin(np.pi * t) ** 1.5 * 3


def tick(f=4200, seed=0):
    n = int(0.02 * SR)
    return hp(noise("tick", n, f, seed), f * 0.8) * ex(n, 0.0025) * 0.5


def reverb(
    x,
    wet=0.2,
    taps=((0.029, 0.5), (0.043, 0.4), (0.067, 0.3), (0.097, 0.22), (0.131, 0.15)),
):
    y = x.copy()
    for d, g in taps:
        i = int(d * SR)
        y[i:] += wet * g * x[:-i]
        y[2 * i :] += wet * g * g * x[: -2 * i]
    return y


def duck(bus, times, depth_db=6, rel=0.12, dur=0.3):
    g = np.ones(len(bus))
    n = C.sample_of(dur, SR)
    for t in times:
        i = C.sample_of(t, SR)
        j = min(len(bus), i + n)
        g[i:j] = np.minimum(
            g[i:j], 1 - (1 - 10 ** (-depth_db / 20)) * np.exp(-tt(j - i) / rel)
        )
    return bus * g


# ---- landmarks (Z02): which instant of a sound sits on its event time ----

ALIGN = {  # the instant that lands on the event, per generator name; a name not listed aligns its onset
    "kick": "onset",
    "snare": "onset",
    "clap": "onset",
    "hat": "onset",
    "tick": "onset",
    "hit": "onset",
    "pluck": "onset",
    "bass": "onset",
    "tone": "onset",
    "boom": "onset",  # decays from its first cycle, so onset and peak coincide (OVH, showtime)
    "whoosh": "peak",
    "swell": "end",  # swells climax on their last sample (earshot, showtime); peak only for climax-then-ring shapes
    "riser": "end",
    "reverse": "end",
    "pad": "pad",
    "chord": "pad",
}
# peak = the middle of the loudest 50 ms for these; 5 ms for every other named sound
SLOW = {"whoosh", "riser", "swell", "reverse"}
# the cue sheet's heavy flag: the stack guard counts these
HEAVY = {"kick", "hit", "boom", "impact", "drop"}
RING = 0.030  # an end-aligned sound may ring this long past its climax before the climax lands audibly early
PAD_TOL = 0.65  # a measured pad point may be off by this fraction of itself (beating chords, 2026-10-28)


def _energy(x, w):
    """Energy of every w-sample window x[i:i + w] (len(x) - w + 1 values), by cumulative sum."""
    w = max(1, min(w, len(x)))
    c = np.concatenate([[0.0], np.cumsum(x * x)])
    return c[w:] - c[:-w], w


def _blocks(x, w):
    """Mean square of consecutive w-sample blocks from the first sample (the last block zero-padded)."""
    m = -(-len(x) // w)
    return np.pad(x * x, (0, m * w - len(x))).reshape(m, w).mean(1)


def _peak(x, win):
    e, w = _energy(x, C.sample_of(win, SR))
    return int(np.argmax(e)) + w / 2


def _marks(sig, sound=None, pad_db=-15.0):
    """landmarks() in samples (floats: a window middle can fall on a half sample)."""
    known = _KNOWN.get(id(sig), {})
    x = np.asarray(sig, float)
    m = {"onset": 0.0, "peak": 0.0, "end": float(len(x)), "pad": 0.0, "ring": 0.0}
    m |= {"win": 0.005, "peak_dbfs": -120.0, "pad_known": "attack" in known}
    if not x.any():
        return m
    w1, w5 = C.sample_of(0.001, SR), C.sample_of(0.005, SR)
    b1, b5 = _blocks(x, w1), _blocks(x, w5)
    last = np.nonzero(b5 >= b5.max() / 1e5)[0][-1]  # the last 5 ms block within 50 dB
    m["onset"] = float(np.argmax(b1 >= b1.max() / 1e3) * w1)  # first 1 ms within 30 dB
    m["end"] = float(min(len(x), (last + 1) * w5))
    e5, w = _energy(x, w5)
    climax = int(np.argmax(e5)) + w / 2
    m["pad"] = int(np.argmax(e5 >= e5.max() * 10 ** (pad_db / 10))) + w / 2
    # the generator's own ramp is exact, where a beating chord's loudest window is a beat crest
    if "attack" in known:
        m["pad"] = known["attack"] * 10 ** (pad_db / 20) * SR
    if sound in SLOW:
        m["win"] = 0.05
    elif sound not in ALIGN and sound not in HEAVY:
        # unnamed: a sound still rising 30 ms after its onset is a swell, not a hit
        m["win"] = 0.005 if climax - m["onset"] <= 0.03 * SR else 0.05
    m["peak"] = climax if m["win"] == 0.005 else _peak(x, m["win"])
    m["ring"] = m["end"] - climax
    m["peak_dbfs"] = round(20 * math.log10(np.abs(x).max()), 3)
    return m


def landmarks(sig, sound=None, pad_db=-15.0):
    """Where a sound's perceptual instants sit, in seconds from its first sample (Z02):
    onset  start of the first 1 ms RMS block within 30 dB of the loudest block
    peak   middle of the loudest window: 50 ms for whoosh, riser, swell and reverse (a 1 or 5 ms argmax on noise moved
           by up to 130 ms between seeds), 5 ms for every other named sound; an unnamed sound takes 5 ms when it
           rises within 30 ms of its onset, else 50 ms
    end    end of the last 5 ms block within 50 dB of the loudest (earshot), not len(sig)
    pad    the attack point of slow chords and pads, pad_db under full level (Vos and Rasch: -15 dB; valid -6 to
           -15 dB). synth.pad's own arrays report it from their ramp (att * 10 ** (pad_db / 20)); any other
           sound is measured (middle of the first 5 ms window pad_db under the loudest). On beating chords that
           read 0.65 to 2.8 times the true ramp point (14 pads, att 0.25 and 0.5 s: the loudest window is a beat
           crest), so a measured pad point carries a tolerance of 0.65 x itself (PAD_TOL). Rise times over 80 ms
           are untested
    ring   end minus the climax (the loudest 5 ms): past RING, align='end' lands the climax that much early
    Also win (the peak window, s), peak_dbfs (the sample peak, dBFS) and pad_known (the pad point came from
    the generator, not a measurement)."""
    if not -15 <= pad_db <= -6:
        raise ValueError(f"pad_db {pad_db} outside -15..-6 dB")
    m = _marks(sig, sound, pad_db)
    return {
        k: (v / SR if k in ("onset", "peak", "end", "pad", "ring") else v)
        for k, v in m.items()
    }


# ---- the cue sheet (Z07, Z12): every sound placed while one is recording ----

SHEET = None  # the CueSheet place() records into; recording() sets it


class CueSheet:
    """One contract.CUESHEET_KEYS row per placed sound, plus each sound's own buffer (pre-gain) under its row index."""

    def __init__(self, sr=SR):
        self.sr, self.entries, self.sounds = sr, [], {}

    def add(self, sig, row):
        row = {"i": len(self.entries), **row}
        self.entries.append(row)
        self.sounds[row["i"]] = sig
        return row

    def write(self, folder=".", scale=1.0):
        """CUESHEET and CUE_SOUNDS in folder. scale is the gain the whole mix got after placement (the peak
        normalise); it is folded into every row's gain, so the sheet matches mix_raw.wav and sfx.wav."""
        rows = [{**e, "gain": e["gain"] * scale} for e in self.entries]
        C.write_cuesheet(rows, self.sounds, self.sr, folder)
        return str(Path(folder, C.CUESHEET)), str(Path(folder, C.CUE_SOUNDS))


@contextlib.contextmanager
def recording(sr=SR):
    """with synth.recording() as sheet: every place, put and put_peak inside adds its row to sheet."""
    global SHEET
    old, SHEET = SHEET, CueSheet(sr)
    try:
        yield SHEET
    finally:
        SHEET = old


# ---- placement: one path for every sound ----


def place(
    buf,
    sig,
    at=None,
    g=1.0,
    align=None,
    sound=None,
    label="",
    stem="sfx",
    frame=None,
    fps=None,
    offset=0.0,
    pad_db=-15.0,
    landmark=None,
):
    """Add sig * g into buf so the chosen instant of sig lands on the event: at seconds, or a frame cue (frame at fps,
    the frame's first sample). align: start (the first sample, as put), onset, peak, end or pad (see landmarks); None
    takes the generator's default from ALIGN, onset when sound is unnamed. landmark (seconds from the first sample)
    replaces the measured instant, for a sound whose generator knows it. offset moves the landmark off the event
    (seconds, negative = earlier), so a lead-in can sit just before a hit instead of on it. The first sample goes at
    round((at - landmark) * SR); a start before 0 trims the head and fades the kept part in over 3 ms, so the bus does
    not step at its first sample. While a cue sheet is recording, the row and sig itself (whole) are added to it.
    Rows also carry trim_s (seconds cut off the head), audible_s (the pad_db attack point: when the sound is heard)
    and landmark_tol (seconds the instant may be off: PAD_TOL x a measured pad point, 0 when exact). Warns when
    the landmark lands before 0, and when a labelled start or onset row is heard more than 10 ms after the instant
    placed on its cue. Returns the row."""
    align = align or ALIGN.get(sound, "onset")
    if align not in ("start", "onset", "peak", "end", "pad"):
        raise ValueError(f"align {align!r}: use start, onset, peak, end or pad")
    ev = C.frame_sample(frame, fps, SR) if frame is not None else C.sample_of(at, SR)
    ev += C.sample_of(offset, SR)
    m = (
        _marks(sig, sound, pad_db)
        if align != "start" or SHEET is not None or label
        else None
    )
    if landmark is not None:
        lm = C.sample_of(landmark, SR)
    else:
        lm = 0 if align == "start" else math.floor(m[align] + 0.5)
    i0 = ev - lm
    s = sig
    # a cut head: fade what is kept in over 3 ms (on a copy; the sheet keeps the whole sound)
    if i0 < 0:
        s = np.array(sig[-i0:], float)
        f = min(len(s), C.sample_of(0.003, SR))
        if f:
            s[:f] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(f) / f)
    trim, i0 = max(0, -i0), max(0, i0)
    n = min(len(s), len(buf) - i0)
    if n > 0:
        buf[i0 : i0 + n] += s[:n] * g
    where = f"{sound or 'sound'} at {ev / SR:.3f} s"
    if ev < 0:
        warnings.warn(
            f"{where}: its {align} lands before 0, so only what follows it plays",
            stacklevel=2,
        )
    if align == "end" and m["ring"] > RING * SR:
        warnings.warn(
            f"{where} rings {m['ring'] / SR * 1000:.0f} ms past its climax: align='end' lands the climax that "
            "early (trim the tail or align='peak')",
            stacklevel=2,
        )
    late = None if m is None else m["pad"] - lm
    if label and align in ("start", "onset") and late > 0.010 * SR:
        warnings.warn(
            f"{where} ({label!r}) is heard {late / SR * 1000:.0f} ms after the instant placed on its cue (a slow "
            "attack): place it with align='pad', or pass landmark=, so the attack lands on the cue",
            stacklevel=2,
        )
    measured = align == "pad" and landmark is None and not m["pad_known"]
    tol = round(PAD_TOL * m["pad"] / SR, 4) if measured else 0.0
    row = {
        "label": label,
        "sound": sound or "",
        "t": ev / SR,
        "align": align,
        "landmark_s": lm / SR,
        "start_s": i0 / SR,
        "gain": float(g),
        "peak_dbfs": None,
        "heavy": sound in HEAVY,
        "bus": stem,
        "trim_s": trim / SR,
        "audible_s": None if m is None else m["pad"] / SR,
        "landmark_tol": tol,
    }
    if SHEET is not None and n > 0:
        peak = np.abs(sig).max() if m is None else 10 ** (m["peak_dbfs"] / 20)
        row["peak_dbfs"] = round(20 * math.log10(max(peak, 1e-6)), 3)
        row = SHEET.add(sig, row)
    return row


def put(bus, sig, t0, g=1.0, **kw):
    """Add sig * g into bus with its first sample at t0 (nearest sample; a negative start trims the head). Any place()
    keyword works here too: align='onset' to land the audible start instead, frame and fps for a frame cue."""
    return place(bus, sig, t0, g, **{"align": "start", **kw})


def put_peak(bus, sig, event_t, g=1.0, **kw):
    """Place sig so its loudest instant lands on event_t, not its file start: the middle of its loudest 50 ms for
    whooshes and swells, 5 ms for hits (landmarks). Name the generator (sound='whoosh') to skip the guess."""
    return place(bus, sig, event_t, g, align="peak", **kw)


def build(bpm=120, bars=2):
    B = 60 / bpm
    N = int((bars * 4 * B + 0.5) * SR)
    m = np.zeros(N)
    fx = np.zeros(N)
    ks = []
    for b in range(bars):
        t0 = b * 4 * B
        for k in range(4):
            t = t0 + k * B
            put(m, kick(), t)
            ks.append(t)
            put(m, hat(), t + B / 2, 0.7)
            put(m, bass(45 if b % 2 == 0 else 41, B * 0.45), t + B / 2, 0.8)
        put(m, snare(), t0 + B, 0.6)
        put(m, snare(), t0 + 3 * B, 0.6)
        put(m, pad([57, 60, 64] if b % 2 == 0 else [53, 57, 60], 4 * B), t0, 0.5)
        for s in range(8):
            put(m, pluck([69, 72, 76, 72][s % 4], 0.3), t0 + s * B / 2, 0.25)
    put(fx, riser(B * 2), (bars * 4 - 2) * B - 0.0, 0.6)
    put(fx, whoosh(0.5), B * 2, 0.5)
    put(fx, boom(), 0, 0.5)
    put(fx, tick(), 3 * B, 0.8)
    m = duck(m, ks, 3)
    m = reverb(m, 0.15)
    out = m + fx
    return out


if __name__ == "__main__":
    y = build(120, 2)[: 4 * SR]
    y = y / (np.abs(y).max() + 1e-9) * 0.89
    path = sys.argv[1] if len(sys.argv) > 1 else "synth_demo.wav"
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.repeat(y[:, None], 2, 1) * 32767).astype("<i2").tobytes())
    print("wrote", path, len(y) / SR, "s")
