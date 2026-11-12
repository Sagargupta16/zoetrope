# sound.py : the audio gates on synthetic 48 kHz float WAVs and a tiny synthetic build, made in the case's temp
# folder. Q802 true peak: EBU Tech 3341 signals 15 to 18 (-6.0 dBTP, read as such) and 19 (+3.0 dBTP with its samples
# at -0.03 dBFS), and stacked hits at -0.8 and -0.3 dBTP naming the sounds that stack (Z18 stack_check 1 and 3).
# Q804 the stack guard on planted cue sheets; Q805 the master on a raw mix with a hot stacked transient; Q902 and
# Q903 on a 4 s build with a tick 60 ms late, a hit 50 ms early, a tick 20 ms late (NOTE), a cue no sound serves and
# a mux 5 ms late (its stems are 16-bit 44.1 kHz, the format the engine's own build files have); Q906 calib with the
# mux moved. Lifted from lanes A, S1 and S2 (notes/a.md probe_q805, s1.md fx/, s2.md fx_stack.py and fx_peak.py).
import math
import types

import audio
import contract as C
import numpy as np
import qa
import qa_stack
import qa_sync

from qa_fixtures import case, clean, media, want

SR = 48000


# ---- Q802: true peak on float WAVs ----


def peak_ctx(fx, x, sheet=()):
    """A Ctx on fx.tmp/mix.wav holding x, with ctx.loudness from qa.loud as qa.check sets it, and a cue sheet when
    given: [(sound, label, start s, buffer, gain)]."""
    if sheet:
        entries, sounds = [], {}
        for i, (snd, lab, st, buf, g) in enumerate(sheet):
            land = int(np.argmax(np.abs(buf))) / SR
            entries.append(
                {
                    "i": i,
                    "label": lab,
                    "sound": snd,
                    "t": round(st + land, 4),
                    "align": "peak",
                    "landmark_s": round(land, 4),
                    "start_s": st,
                    "gain": g,
                    "peak_dbfs": round(float(20 * np.log10(np.abs(buf).max())), 2),
                    "heavy": snd in ("hit", "kick", "boom"),
                    "bus": "sfx",
                }
            )
            sounds[i] = buf
        C.write_cuesheet(entries, sounds, SR, fx.tmp)
    path = media.wav(fx.tmp / "mix.wav", x)
    probe = {"acodec": "pcm_f32le", "vcodec": None, "channels": 2, "frames": 0}
    ctx = C.Ctx(path, probe, 30, 320, 180, None, fx.tmp, ff=fx.ff)
    ctx.loudness = qa.loud(str(path), fx.ff)
    return qa_stack.peak_rows(ctx)


# EBU Tech 3341 table 1 (48 kHz stereo sines): signal: (frequency, amplitude, phase in degrees, true peak dBTP)
EBU = {
    15: (12000, 0.5, 0, -6.0),
    16: (12000, 0.5, 45, -6.0),
    17: (8000, 0.5, 60, -6.0),
    18: (6000, 0.5, 67.5, -6.0),
}
EBU[19] = (12000, 1.41, 45, 3.0)


def ebu(k):
    f, amp, deg, _ = EBU[k]
    return lambda fx: peak_ctx(fx, media.tone(f, 3.0, amp, phase=math.radians(deg)))


def hits():
    """Three heavy sounds for one instant: a 60 Hz kick, a 180 Hz hit with a noise snap, a 40 Hz boom."""
    t = np.arange(round(0.4 * SR)) / SR
    rng = np.random.default_rng(3)
    kick = np.sin(2 * np.pi * (60 * t + 4 * (1 - np.exp(-t * 30)))) * np.exp(-t * 9)
    hit = np.sin(2 * np.pi * 180 * t) * np.exp(-t / 0.12) + 0.5 * rng.standard_normal(
        len(t)
    ) * np.exp(-t / 0.01)
    boom = np.sin(2 * np.pi * 40 * t) * np.exp(-t / 0.3)
    att = np.minimum(1, t / 0.002)
    return [b * att for b in (kick, hit, boom)]


def stacked(tp_db):
    """A quiet 110 Hz bed with the three hits stacked at 1.5 s, scaled so the 4x true peak of the mix is tp_db."""

    def go(fx):
        n = 3 * SR
        bed = 0.05 * np.sin(2 * np.pi * 110 * np.arange(n) / SR)
        bufs, sfx = hits(), np.zeros(n)
        a = C.sample_of(1.5, SR)
        for b in bufs:
            sfx[a : a + len(b)] += b
        g = (
            10 ** (tp_db / 20) / audio.true_peak(bed + sfx).max()
        )  # one gain for both, so the bed's share moves too
        sheet = [
            (s, lab, 1.5, b, g)
            for (s, lab), b in zip(
                (("kick", "one"), ("hit", "two"), ("boom", "three")), bufs
            )
        ]
        mono = (bed + sfx) * g
        return peak_ctx(fx, np.stack([mono, mono], 1), sheet)

    return go


# ---- Q804: the stack guard on planted cue sheets (no audio) ----


def sheet_ctx(fx, items, cues=()):
    """stack_rows on a sheet of (i, sound, t, label, heavy, bus, start, align, length s)."""
    entries, sounds = [], {}
    for i, snd, t, lab, heavy, bus, start, align, length in items:
        entries.append(
            {
                "i": i,
                "label": lab,
                "sound": snd,
                "t": t,
                "align": align,
                "landmark_s": 0.0 if start is None else round(t - start, 6),
                "start_s": t if start is None else start,
                "gain": 0.5,
                "peak_dbfs": -1.0,
                "bus": bus,
                "heavy": heavy,
            }
        )
        sounds[i] = np.zeros(round(length * 44100), np.float32)
    C.write_cuesheet(entries, sounds, 44100, fx.tmp)
    scn = types.SimpleNamespace(CUES=list(cues), SCHEDULE={}, DURATION=10.0)
    ctx = C.Ctx(fx.tmp / "none.mp4", {"acodec": "aac"}, 30, 1920, 1080, scn, fx.tmp)
    return qa_stack.stack_rows(ctx)


F = 1 / 30


def stack_planted(fx):
    """Two heavy sounds 1 frame apart and a third cue in the same 100 ms; a music-bed kick under them is not a layer."""
    return sheet_ctx(
        fx,
        [
            (0, "hit", 2.5, "cut", True, "sfx", None, "onset", 0.3),
            (1, "boom", round(2.5 + F, 4), "logo", True, "sfx", None, "onset", 0.3),
            (
                2,
                "tick",
                round(2.5 + 2 * F, 4),
                "blip",
                False,
                "sfx",
                None,
                "onset",
                0.3,
            ),
            (3, "kick", 2.5, "", True, "music", None, "onset", 0.3),
        ],
    )


def stack_payoff(fx):
    """A second sound 2 frames after a payoff cue."""
    return sheet_ctx(
        fx,
        [
            (0, "chime", 5.0, "reveal", False, "sfx", None, "onset", 0.3),
            (
                1,
                "pop",
                round(5.0 + 2 * F, 4),
                "sparkle",
                False,
                "sfx",
                None,
                "onset",
                0.3,
            ),
        ],
        cues=[{"t": 5.0, "label": "reveal", "payoff": True}],
    )


def stack_template(fx):
    """The template's cut sounds (a whoosh 0.3 s before each hit) with the bed's kick under the second cut: clean."""
    return sheet_ctx(
        fx,
        [
            (0, "whoosh", 2.2, "cut to point", False, "sfx", None, "onset", 0.4),
            (1, "hit", 2.5, "cut to point", True, "sfx", None, "onset", 0.5),
            (2, "whoosh", 4.7, "cut to cta", False, "sfx", None, "onset", 0.4),
            (3, "hit", 5.0, "cut to cta", True, "sfx", None, "onset", 0.5),
            (4, "kick", 5.0, "", True, "music", None, "onset", 0.35),
            (5, "kick", 4.0, "", True, "music", None, "onset", 0.35),
        ],
    )


# ---- Q805: the master ----


def master(spike):
    """audio.master on a 4 s raw mix: a 110 Hz bed with noise, plus (spike) a hot stacked transient at 2.0 s that the
    limiter must take far more than 6 dB off to reach the ceiling."""

    def go(fx):
        t = np.arange(4 * SR) / SR
        x = 0.1 * np.sin(2 * np.pi * 110 * t) + 0.02 * np.random.default_rng(
            1
        ).standard_normal(len(t))
        if spike:
            a = C.sample_of(2.0, SR)
            k = np.arange(round(0.03 * SR)) / SR
            x[a : a + len(k)] += 0.95 * np.sin(2 * np.pi * 150 * k) * np.exp(-k / 0.01)
        src = media.wav(fx.tmp / "mix_raw.wav", np.stack([x, x], 1))
        return audio.master(str(src), str(fx.tmp / "mix.wav"), fx.ff)["rows"]

    return go


# ---- Q902 and Q903: a 4 s build with a cue sheet, stems, a picture and a mux ----

SYNC_DUR, SYNC_SR = 4.0, 44100


def _t(n):
    return np.arange(n) / SYNC_SR


def sync_build(fx, faults, shift=False):
    """Writes the build files into fx.tmp and returns qa_sync.check_rows on its out.mp4: four cues (a hit on time,
    a tick, a hit, a tick) placed on the SFX bus by contract.write_cuesheet; faults puts the first tick 60 ms late,
    the second hit 50 ms early (the sheet still says 3.0 s: a mixer bug) and the second tick 20 ms late, and adds a
    cue no sound serves; shift muxes the audio 5 ms late."""
    rng = np.random.default_rng(12)
    n_hit, n_tick = round(0.3 * SYNC_SR), round(0.02 * SYNC_SR)
    hit = (
        np.sin(2 * np.pi * 180 * _t(n_hit))
        * np.minimum(1, _t(n_hit) / 0.002)
        * np.exp(-_t(n_hit) / 0.12)
    )
    hit += 0.5 * rng.standard_normal(n_hit) * np.exp(-_t(n_hit) / 0.01)
    tick = qa_sync.band(rng.standard_normal(n_tick), SYNC_SR, 3000) * np.exp(
        -_t(n_tick) / 0.004
    )
    # (cue t, label, sound, buffer, where it really lands, what the sheet says)
    plan = [
        (1.0, "hit on time", "hit", hit, 1.0, 1.0),
        (
            2.0,
            "tick late 60",
            "tick",
            tick,
            2.06 if faults else 2.0,
            2.06 if faults else 2.0,
        ),
        (3.0, "hit early 50", "hit", hit, 2.95 if faults else 3.0, 3.0),
        (
            3.5,
            "tick late 20",
            "tick",
            tick,
            3.52 if faults else 3.5,
            3.52 if faults else 3.5,
        ),
    ]
    n = C.sample_of(SYNC_DUR, SYNC_SR)
    sfx, rows, sounds = np.zeros(n), [], {}
    for i, (_, lab, snd, buf, real, said) in enumerate(plan):
        a = C.sample_of(real, SYNC_SR)
        sfx[a : a + len(buf)] += 0.5 * buf
        rows.append(
            {
                "i": i,
                "label": lab,
                "sound": snd,
                "t": said,
                "align": "onset",
                "landmark_s": 0.0,
                "start_s": said,
                "gain": 0.5,
                "peak_dbfs": round(float(20 * np.log10(np.abs(buf).max())), 3),
                "heavy": snd == "hit",
                "bus": "sfx",
                "audible_s": 0.0025,
            }
        )
        sounds[i] = buf
    hum = 0.08 * np.sin(2 * np.pi * 110 * _t(n))  # the music bed
    scale = 0.85 / np.abs(sfx + hum).max()
    C.write_cuesheet(
        [{**r, "gain": r["gain"] * scale} for r in rows], sounds, SYNC_SR, fx.tmp
    )
    qa_sync.write16(fx.tmp / C.SFX, sfx * scale, SYNC_SR)
    qa_sync.write16(fx.tmp / C.MIX_RAW, (sfx + hum) * scale, SYNC_SR)
    qa_sync.write16(
        fx.tmp / C.MIX, (sfx + hum) * scale, SYNC_SR
    )  # no master: mix.wav is what the mux encodes
    # the picture steps its grey on every cue frame, so the picture side sees each cue land
    nf = C.frame_of(SYNC_DUR, 30)
    level = np.full(nf, 60.0)
    for j, (c, *_) in enumerate(plan):
        level[C.frame_of(c, 30) :] = 60 + 50 * ((j + 1) % 2)
    pic = (
        np.repeat(level.astype(np.uint8)[:, None, None, None], 180, 1)
        .repeat(320, 2)
        .repeat(3, 3)
    )
    video = media.encode(fx.ff, fx.tmp / C.VIDEO, pic, 30)
    argv = C.mux_cmd(fx.ff, str(video), str(fx.tmp / C.MIX), str(fx.tmp / "out.mp4"))
    if shift:  # the planted mux fault: the audio input 5 ms late
        k = argv.index(str(fx.tmp / C.MIX))
        argv[k - 1 : k - 1] = ["-itsoffset", "0.005"]
    media.run(argv)
    scn = types.SimpleNamespace(
        SCHEDULE={"a": (0.0, SYNC_DUR)},
        DURATION=SYNC_DUR,
        BPM=120,
        NO_TEXT=True,
        CUE_LAG=0,
        # faults also declares a cue no sound serves
        CUES=[(c, lab, "both") for c, lab, *_ in plan]
        + ([(3.8, "no sound", "both")] if faults else []),
    )
    out = fx.tmp / "out.mp4"
    p = qa.probe(str(out), fx.ff)
    ctx = C.Ctx(out, p, 30, p["w"], p["h"], scn, fx.tmp, ff=fx.ff)
    return qa_sync.check_rows(ctx)


# ---- Q906: calib, clean and with the mux moved ----


def calib(shift):
    def go(fx):
        real = C.mux_cmd

        def late(
            ff, video, mix, out
        ):  # the planted fault: the audio input 5 ms late in the one mux
            argv = real(ff, video, mix, out)
            k = argv.index(mix)
            return [*argv[: k - 1], "-itsoffset", "0.005", *argv[k - 1 :]]

        if shift:
            C.mux_cmd = late
        try:
            return qa_sync.calib(30, "320x180", str(fx.tmp / "calib"), fx.ff)
        finally:
            C.mux_cmd = real

    return go


CASES = [
    *[
        case(
            f"sound.ebu3341_{k}",
            ebu(k),
            [want("Q802", "PASS", t=1.5, tol=1.5, metric=-6.0, mtol=0.3)],
        )
        for k in (15, 16, 17, 18)
    ],
    case(
        "sound.ebu3341_19",
        ebu(19),
        [want("Q802", "FIX", t=1.5, tol=1.5, metric=3.0, mtol=0.3)],
    ),
    case(
        "sound.stack_tp08",
        stacked(-0.8),
        [
            want(
                "Q802",
                "FIX",
                "kick 'one' + hit 'two' + boom 'three'",
                1.5,
                tol=0.05,
                metric=-0.8,
                mtol=0.3,
            )
        ],
    ),
    case(
        "sound.stack_tp03",
        stacked(-0.3),
        [
            want(
                "Q802",
                "FIX",
                "kick 'one' + hit 'two' + boom 'three'",
                1.5,
                tol=0.05,
                metric=-0.3,
                mtol=0.3,
            )
        ],
    ),
    case(
        "sound.stack_planted",
        stack_planted,
        [
            want(
                "Q804",
                "NOTE",
                "hit 'cut' + boom 'logo' + tick 'blip'",
                2.5,
                tol=0.01,
                metric=1.0,
                mtol=0.01,
            )
        ],
    ),
    case(
        "sound.stack_payoff",
        stack_payoff,
        [want("Q804", "NOTE", "chime 'reveal' + pop 'sparkle'", 5.0, tol=0.01)],
    ),
    case("sound.stack_template", stack_template, [want("Q804", "PASS")]),
    case(
        "sound.master_spike",
        master(True),
        [want("Q805", "FIX", "mix.wav", 2.0, tol=0.05, msg="at 2.00 s")],
    ),
    case(
        "sound.master_clean",
        master(False),
        [want("Q805", "PASS", metric=-14.0, mtol=0.1)],
    ),
    case(
        "sound.sync_clean",
        lambda fx: sync_build(fx, False),
        [
            clean(),
            want("Q902", "PASS"),
            want("Q903", "PASS", msg="against mix.wav", metric=0.0, mtol=0.2),
        ],
    ),
    case(
        "sound.sync_faults",
        lambda fx: sync_build(fx, True),
        [
            want("Q902", "FIX", "tick late 60", 2.0, tol=0.001, metric=60.0, mtol=3.0),
            want("Q902", "FIX", "hit early 50", 3.0, tol=0.001, metric=-50.0, mtol=3.0),
            want("Q902", "NOTE", "tick late 20", 3.5, tol=0.001, metric=20.0, mtol=3.0),
            want("Q902", "FIX", "no sound", 3.8, tol=0.001, msg="no sound"),
        ],
    ),
    case(
        "sound.sync_mux_late",
        lambda fx: sync_build(fx, False, shift=True),
        [
            want(
                "Q903",
                "FIX",
                t=0.48,
                tol=0.01,
                msg="against mix.wav",
                metric=5.0,
                mtol=0.3,
            )
        ],
    ),
    case(
        "sound.calib_clean",
        calib(False),
        [clean(), want("Q906", "PASS", msg="blip lands", metric=0.0, mtol=0.3)],
    ),
    case(
        "sound.calib_mux_late",
        calib(True),
        [want("Q906", "FIX", msg="blip lands", t=2.0, metric=5.0, mtol=0.3)],
    ),
]
