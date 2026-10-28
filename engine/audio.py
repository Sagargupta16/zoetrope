# audio.py : the template's music and SFX on a BPM grid (numpy only, 44.1 kHz), the build files they make (mix_raw.wav,
# the sfx.wav stem, the cue sheet), and the -14 LUFS master with a 4x oversampled true-peak limiter (numpy, no scipy)
import math
import subprocess
import wave
from pathlib import Path

import contract as C
import numpy as np
import synth as S

SR = 44100
SR_MASTER = 48000  # master() resamples to this and limits there
# master()'s default true-peak ceiling, dBTP. Measured 2026-10-28 on 9 mixes: the AAC encode raised the true peak by up
# to 1.23 dB at 192k and 0.45 dB at 320k, so at 320k -2.0 keeps 0.55 dB under gate 8's -1 dBTP; run_all re-masters
# lower when an encode overshoots more
CEILING = -2.0
# the cut whoosh's apex lands this long before the hit (Z02 correction 7: an offset, not a wider TP margin). Measured
# 2026-10-28: whoosh plus hit then peak 0.1 dB under the hit alone; 2.1.0 put the apex on the cut, 1.8 dB over it
WHOOSH_LEAD = 0.08


def tone(f, d, a=0.005, r=0.2, kind="sine"):
    t = np.arange(int(SR * d)) / SR
    w = np.sin(2 * np.pi * f * t) if kind == "sine" else 2 * ((f * t) % 1) - 1
    env = np.minimum(1, t / a) * np.exp(-t / r)
    return w * env


def kick():
    t = np.arange(int(SR * 0.35)) / SR
    return np.sin(2 * np.pi * (45 * t + 90 * (1 - np.exp(-t * 30)) / 30)) * np.exp(
        -t * 9
    )


def noise(d, seed=1):
    return np.random.default_rng(seed).standard_normal(int(SR * d))


def whoosh(d=0.5):
    n = noise(d)
    t = np.linspace(0, 1, len(n))
    k = np.maximum(
        3, (80 * (1 - t) + 6).astype(int)
    )  # moving-average length sweeps: low-pass opening
    c = np.cumsum(n)
    out = np.array([(c[i] - c[max(0, i - k[i])]) / k[i] for i in range(len(n))])
    return out * np.sin(np.pi * t) * 1.5


def hit():
    return (
        tone(70, 0.5, 0.002, 0.15)
        + noise(0.5, 3) * np.exp(-np.arange(int(SR * 0.5)) / SR * 30) * 0.3
    )


def tick():
    return noise(0.03, 2) * np.exp(-np.arange(int(SR * 0.03)) / SR * 150)


def place(buf, snd, at, gain=1.0, align=None, **kw):
    """Add snd * gain into buf so its landmark lands on `at` seconds (synth.place: align onset, peak, end, pad or
    start; None is the generator's own default when sound= names it, else onset; frame and fps for a frame cue)."""
    return S.place(buf, snd, at, gain, align, **kw)


def _near_cut(t, cuts, fps):
    """True when t is within 3 frames of a cut: counted in frames when fps is known (exactly 3 frames is near, whatever
    the float error), else within 0.1 s."""
    if fps:
        return any(abs(C.frame_of(t, fps) - C.frame_of(c, fps)) <= 3 for c in cuts)
    return any(abs(t - c) <= 0.1 + 1e-9 for c in cuts)


def bed(dur, bpm, cuts=(), voice_spans=(), fps=None, labels=()):
    """The template score as two mono buses (music, sfx) at SR. Music: kick on beats 1 and 3, an offbeat hat, a bass
    and pad line. SFX, per cut: a whoosh whose apex leads the cut by WHOOSH_LEAD and a hit whose onset is on it (frame
    cues when fps is given; labels[i] is the CUES label cut i serves). A kick within 3 frames of a cut is left out:
    the hit carries that beat, and two heavy sounds never stack (Z07). Gains: kick 0.6, hit 0.4, bass and pad line 0.3,
    so the master's limiter only catches peaks (under 1 dB on this bed). Only the music ducks, about 8 dB, under voice."""
    beat = 60 / bpm
    music, sfx = np.zeros(C.sample_of(dur, SR)), np.zeros(C.sample_of(dur, SR))
    for i in range(math.floor(dur / beat + 1e-6)):  # 11.2 / 0.8 is 13.999999999999998
        at = i * beat
        if i % 4 in (0, 2) and not _near_cut(at, cuts, fps):
            place(music, kick(), at, 0.6, sound="kick", stem="music")
        place(music, tick(), at + beat / 2, 0.25, sound="tick", stem="music")  # hat
        f = [220, 261.63, 196, 246.94][(i // 4) % 4]
        place(music, tone(f, beat, 0.01, 0.35), at, 0.3, sound="tone", stem="music")
    for k, c in enumerate(cuts):
        cue = {"frame": C.frame_of(c, fps), "fps": fps} if fps else {}
        place(sfx, whoosh(0.4), c, 0.5, sound="whoosh", offset=-WHOOSH_LEAD, **cue)
        lab = labels[k] if k < len(labels) else ""
        place(sfx, hit(), c, 0.4, sound="hit", label=lab, **cue)
    for a, b in voice_spans:
        music[C.sample_of(a, SR) : C.sample_of(b, SR)] *= 10 ** (-8 / 20)
    return music, sfx


def music(dur, bpm, cuts=(), voice_spans=()):
    """The template score as one mono buffer (bed() music plus SFX), for callers that want a single bus."""
    m, s = bed(dur, bpm, cuts, voice_spans)
    return m + s


def write_wav(path, mono, voice=None, scale=None):
    """mono (plus voice) as 16-bit stereo at SR, peak-normalised to 0.85 unless scale is given. Returns the scale,
    so a stem written with the same scale lines up with this mix sample for sample."""
    mix = np.array(mono, float)
    if voice is not None:
        mix[: len(voice)] += voice[: len(mix)]
    if scale is None:
        scale = 0.85 / max(1e-9, np.abs(mix).max())
    pcm = (np.stack([mix, mix], 1) * scale * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return scale


def render_audio(scenes, folder=".", fps=None):
    """The template's score for scenes, written as the build files in folder: MIX_RAW (music plus SFX), SFX (the SFX
    bus alone, same scale and rate), CUESHEET and CUE_SOUNDS (every placed sound, music and SFX). DURATION and BPM
    come from scenes; the cuts from scenes.CUTS when it exists, else every SCHEDULE start after 0; each cut's hit
    carries the CUES label at its time. Cuts land on frames when fps (or scenes.FPS) is known. Returns the paths."""
    fps = fps or getattr(scenes, "FPS", None)
    cuts = getattr(scenes, "CUTS", None)
    if cuts is None:
        cuts = sorted({a for a, b in scenes.SCHEDULE.values() if a > 0})
    tol = 0.5 / fps if fps else 1e-3
    cues = [c for c in C.cues(scenes) if c["kind"] != "picture"]
    labels = [
        next((c["label"] for c in cues if abs(c["t"] - t) <= tol), "") for t in cuts
    ]
    with S.recording() as sheet:
        m, s = bed(
            scenes.DURATION, getattr(scenes, "BPM", 120), cuts, fps=fps, labels=labels
        )
    scale = 0.85 / max(np.abs(m + s).max(), np.abs(s).max(), 1e-9)  # both files fit
    out = {k: str(Path(folder, getattr(C, k.upper()))) for k in ("mix_raw", "sfx")}
    write_wav(out["mix_raw"], m + s, scale=scale)
    write_wav(out["sfx"], s, scale=scale)
    out["cuesheet"], out["cue_sounds"] = sheet.write(folder, scale)
    return out


# ---- master (Z03): static gain to I LUFS, then a 4x oversampled true-peak limiter, re-measured with ebur128 ----

# oversampling and FIR taps per phase (BS.1770 Annex 2 uses 4x with 12 taps per phase)
OS, TAPS = 4, 32


def _phases():
    """The 4x interpolator as OS polyphase filters: Kaiser-windowed sinc (beta 10), odd length, so phase 0 returns
    the original samples and the true peak never reads under the sample peak."""
    n = OS * TAPS + 1
    k = np.arange(n) - (n - 1) / 2
    h = np.sinc(k / OS) * np.kaiser(n, 10)
    return [h[p::OS] for p in range(OS)]


def true_peak(x):
    """Per-sample true peak of x, (n,) or (n, ch): the largest |value| of the 4x interpolated signal in [i, i + 1),
    linked across channels. 20 * log10(true_peak(x).max()) is the dBTP figure."""
    x = np.asarray(x, float)
    x = x[:, None] if x.ndim == 1 else x
    tp = np.zeros(len(x))
    for h in _phases():
        for c in range(x.shape[1]):
            y = np.convolve(x[:, c], h)[TAPS // 2 : TAPS // 2 + len(x)]
            np.maximum(tp, np.abs(y), out=tp)
    return tp


def _gain(tp, ceiling, sr, look=0.003, release=0.1):
    """Gain per sample that keeps gain * tp at or under ceiling (linear). Per 1 ms block: the requirement, a sliding
    minimum from one block back to `look` ahead, a one-pole release toward 1, and a causal box over the lookahead
    (the attack ramp); then linear between block starts, and a final clamp to the requirement. Every block's gain is
    at or under its own and its neighbours' requirement, so the clamp never has to cut in."""
    r = np.minimum(1.0, ceiling / np.maximum(tp, 1e-12))
    b = C.sample_of(0.001, sr)
    nb = -(-len(r) // b)
    req = np.pad(r, (0, nb * b - len(r)), constant_values=1.0).reshape(nb, b).min(1)
    a = max(1, round(look / 0.001))
    rp = np.concatenate([[1.0], req, np.ones(a)])
    hold = np.min([rp[s : s + nb] for s in range(a + 2)], axis=0)  # req[k - 1 .. k + a]
    q, g, rel = math.exp(-0.001 / release), 1.0, np.empty(nb)
    for k in range(nb):
        g = min(hold[k], 1 - (1 - g) * q)
        rel[k] = g
    c = np.concatenate([[0.0], np.cumsum(rel)])
    k = np.arange(nb)
    lo = np.maximum(0, k - a + 1)
    att = (c[k + 1] - c[lo]) / (k + 1 - lo)
    return np.minimum(np.interp(np.arange(len(r)), k * b, att), r)


def tp_limit(mix, ceiling_db, sr=SR_MASTER, look=0.003, release=0.1):
    """mix, (n,) or (n, ch), limited so its 4x true peak stays at or under ceiling_db dBTP: lookahead `look` s (the
    gain is down before the peak, with no delay added), release `release` s. Returns (limited mix, gain per sample)."""
    mix = np.asarray(mix, float)
    g = _gain(true_peak(mix), 10 ** (ceiling_db / 20), sr, look, release)
    return mix * (g[:, None] if mix.ndim > 1 else g), g


def measure(src, ff="ffmpeg", sr=SR_MASTER):
    """{I (LUFS), LRA (LU), tp (dBTP)} by ffmpeg ebur128=peak=true, the meter qa.loud reads, at 3 decimals from the
    filter's metadata (its printed summary has 1). src is a file path or a float array (n, ch) at sr."""
    cmd, data = [ff, "-hide_banner", "-v", "error", "-nostdin"], None
    if isinstance(src, (str, Path)):
        cmd += ["-i", str(src)]
    else:
        a = np.ascontiguousarray(src, "<f4")
        ch = a.shape[1] if a.ndim > 1 else 1
        cmd += ["-f", "f32le", "-ar", str(sr), "-ac", str(ch), "-i", "pipe:0"]
        data = a.tobytes()
    af = "ebur128=peak=true:metadata=1,ametadata=print:file=-"
    out = subprocess.run(
        [*cmd, "-af", af, "-f", "null", "-"],
        input=data,
        capture_output=True,
        check=True,
    ).stdout.decode()
    last = dict(ln.split("=", 1) for ln in out.split() if ln.startswith("lavfi.r128."))
    tp = float(last["lavfi.r128.true_peak"])
    return {
        "I": float(last["lavfi.r128.I"]),
        "LRA": float(last["lavfi.r128.LRA"]),
        "tp": round(20 * math.log10(max(tp, 1e-6)), 3),
    }


def _decode(path, ff="ffmpeg", sr=SR_MASTER):
    """Any audio file as float (n, 2) at sr through ffmpeg (mono is doubled)."""
    raw = subprocess.run(
        [ff, "-v", "error", "-nostdin", "-i", str(path), "-f", "f32le", "-ac", "2"]
        + ["-ar", str(sr), "-"],
        capture_output=True,
        check=True,
    ).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).astype(float)


def _write16(path, y, sr):
    pcm = np.clip(np.round(y * 32767), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(y.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def master(src, dst, ff="ffmpeg", I=-14, TP=CEILING, passes=6, tol=0.05):
    """Master src to dst (16-bit stereo, 48 kHz): one static gain to I LUFS, the true-peak limiter at TP dBTP, then
    ebur128 again and the gain nudged, up to `passes` times, until I is within tol LU and the true peak is at or
    under TP (Z03). No delay is added (wave-0's alimiter delayed the mix by its 4 ms attack). Returns {I, LRA, tp
    (measured on dst), gain_db, passes, ceiling, limit_db (deepest gain reduction), limit_t (when), limited_s (seconds
    under more than 1 dB of it), cost_db (loudness the limiter took), input (src measured), rows: [Q805]}."""
    x = _decode(src, ff)
    m0 = measure(x, ff)
    if m0["I"] < -60:  # nothing to master: the raw mix is silent
        _write16(dst, x, SR_MASTER)
        msg = f"master: {src} is silent ({m0['I']} LUFS)"
        res = {**measure(dst, ff), "gain_db": 0.0, "passes": 0, "ceiling": TP}
        row = C.row(
            False, "Q805", msg, "check the raw mix", item=str(src), considered=1
        )
        return res | {"rows": [row]}
    tp = true_peak(x)
    gain_db, ceil_db, last = I - m0["I"], TP, None
    for p in range(1, passes + 1):
        lin = 10 ** (gain_db / 20)
        g = _gain(tp * lin, 10 ** (ceil_db / 20), SR_MASTER)
        y = x * (lin * g)[:, None]
        m = measure(y, ff)
        if (abs(m["I"] - I) <= tol and m["tp"] <= TP) or p == passes:
            break
        # the limiter eats part of every extra dB: step by the measured slope (secant, 1 to 3 dB per LU)
        slope = 1.0
        if last and abs(m["I"] - last[1]) > 1e-3:
            slope = min(3.0, max(1.0, (gain_db - last[0]) / (m["I"] - last[1])))
        last = (gain_db, m["I"])
        gain_db += (I - m["I"]) * slope
        # ebur128 read a hair over the ceiling: aim the limiter that much lower
        if m["tp"] > TP:
            ceil_db -= m["tp"] - TP + 0.01
    _write16(dst, y, SR_MASTER)
    res = measure(dst, ff)
    gr = -20 * np.log10(g)
    # what the limiter took: the gain applied, less the loudness it bought
    cost = gain_db - (res["I"] - m0["I"])
    res |= {
        "gain_db": round(gain_db, 3),
        "passes": p,
        "ceiling": TP,
        "limit_db": round(max(0.0, float(gr.max())), 2),
        "limit_t": round(int(np.argmax(gr)) / SR_MASTER, 3),
        "limited_s": round(float((gr > 1).sum()) / SR_MASTER, 3),
        "cost_db": round(cost, 3),
        "input": m0,
    }
    return res | {"rows": [q805(res, I, TP, dst)]}


# Q805's linear limits: the limiter is there to catch peaks; past these it is shaping the mix. Measured 2026-10-28: the
# five approved sample mixes cost 0.00 LU with at most 1.5 dB; the 2.1.0 template bed cost 1.08 LU, 3.1 dB on every kick
LINEAR_COST = 0.5  # LU of programme loudness the limiter may take
LINEAR_DEPTH = 6.0  # dB of gain reduction at any one moment (deeper, a stacked hit leaves a hole in the bed)


def q805(res, I, TP, dst):
    """Q805: FIX when dst missed I by over 0.1 LU or the ceiling by over 0.05 dB, or when the master could not stay
    linear: the limiter took more than LINEAR_COST LU off the programme (compressing, not catching peaks) or more
    than LINEAR_DEPTH dB at one moment. worst_t is the deepest gain reduction."""
    miss = abs(res["I"] - I) > 0.1 or res["tp"] > TP + 0.05
    squash = res["cost_db"] > LINEAR_COST or res["limit_db"] > LINEAR_DEPTH
    msg = (
        f"master {dst}: {res['I']:.2f} LUFS (want {I}), {res['tp']:.2f} dBTP (ceiling {TP}), gain "
        f"{res['gain_db']:+.2f} dB in {res['passes']} passes; the limiter took {res['cost_db']:.2f} LU, at most "
        f"{res['limit_db']:.1f} dB at {res['limit_t']:.2f} s, over 1 dB for {res['limited_s']:.2f} s"
    )
    if squash:
        fix = (
            f"lower the loudest hits or the bed's peaks in the raw mix, starting at {res['limit_t']:.2f} s "
            f"(limits {LINEAR_COST} LU, {LINEAR_DEPTH:g} dB), then rerun audio.master"
        )
        fields = {"metric": res["cost_db"], "limit": LINEAR_COST}
    else:
        fix = "rerun audio.master with more passes, or look for silence or clipping in the raw mix"
        fields = {"metric": res["I"], "limit": float(I)}
    return C.row(
        not (miss or squash),
        "Q805",
        msg,
        fix,
        worst_t=res["limit_t"],
        item=str(dst),
        considered=1,
        **fields,
    )
