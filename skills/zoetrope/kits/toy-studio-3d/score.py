# score.py : the sound of "Pip wants the star". A small waltz (120 BPM, three beats to the bar) on recorded
# instruments (sampler.py), and one sound of its own for every cue in scenes.CUES, placed on the SFX bus at the
# cue's time from beats.py, so Q902 can find each one. run_all.py calls render_audio() in place of the template
# score. The music drops out twice (under the jump that misses, and before the crate arrives): the landing and the
# idea are then the first things heard.
from pathlib import Path

import audio
import beats as B
import contract as C
import numpy as np
import sampler as P
import synth as S

BAR, BEAT = B.BAR, B.BEAT
BED, CUE = 1.85, 0.8  # the mix: the music bus's gain and the cue sounds' gain
# MIDI notes by name, C4 = 60
C2, D2, F2, G2, A2 = 36, 38, 41, 43, 45
C3, D3, E3, F3, G3, A3, B3 = 48, 50, 52, 53, 55, 57, 59
C4, D4, E4, F4, G4, A4, B4 = 60, 62, 64, 65, 67, 69, 71
C5, D5, E5, F5, G5, A5 = 72, 74, 76, 77, 79, 81
C6, E6, F6, G6, A6, B6 = 84, 88, 89, 91, 93, 95
C7, E7, G7 = 96, 100, 103


def together(*sigs):
    """Several sounds as one array, so a cue is one placed sound."""
    out = np.zeros(max(len(s) for s in sigs))
    for s in sigs:
        out[: len(s)] += s
    return out


def play(bus, inst, midi, at, dur, vel=0.7, g=0.3, seed=0):
    """One note of the music, its attack at `at`."""
    S.place(
        bus,
        P.note(inst, midi, dur, vel, seed),
        at,
        g,
        align="start",
        sound=inst,
        stem="music",
    )


def waltz(bus, bar, bass, chord, soft=1.0):
    """One bar of oom-pah-pah: a plucked bass on the first beat, the chord on the harp on the other two."""
    t = bar * BAR
    play(bus, "pizz", bass, t, 0.7, 0.7, 0.42 * soft)
    for beat in (1, 2):
        for k, m in enumerate(chord):
            play(
                bus,
                "harp",
                m,
                t + beat * BEAT,
                0.5,
                0.5,
                0.16 * soft,
                seed=beat * 10 + k,
            )


def music(bus):
    # want (bars 0 and 1): a wishing tune on the glockenspiel over the waltz
    waltz(bus, 0, C2, (E3, G3, C4))
    waltz(bus, 1, G2, (D3, F3, B3))
    for t, m in ((0.0, G6), (1.0, E6), (1.5, F6), (2.5, B6)):
        play(bus, "glockenspiel", m, t, 1.2, 0.55, 0.3)
    # fail (bars 2 and 3): a run up with the jump, then nothing until the landing, then three notes falling
    for k, m in enumerate((A3, C4, E4, A4, C5, E5)):
        play(bus, "marimba", m, 3.35 + 0.09 * k, 0.3, 0.6 + 0.05 * k, 0.16)
    play(bus, "cellos", F2, 4.5, 1.4, 0.4, 0.2)
    for t, m, d in ((4.6, E5, 0.45), (5.1, C5, 0.45), (5.6, A4, 0.75)):
        play(bus, "flute", m, t, d, 0.5, 0.26)
    # idea (bars 4 and 5): one low held note, almost silence; after the idea, a run up into the next scene
    play(bus, "cellos", D3, 6.0, 1.3, 0.3, 0.12)
    for k, m in enumerate((G2, B3 - 12, D3, G3, B3, D4)):
        play(bus, "pizz", m, 8.0 + 0.125 * k, 0.3, 0.55 + 0.06 * k, 0.22, seed=k)
    S.place(
        bus,
        P.hit("tambourine", "shake", 0.5),
        8.5,
        0.16,
        align="start",
        sound="shake",
        stem="music",
    )
    play(bus, "glockenspiel", B6, 8.75, 0.6, 0.6, 0.22)
    # reach (bars 6 and 7): the waltz in full, then a run up under the jump and room round the catch
    waltz(bus, 6, C2, (E3, G3, C4), 0.68)
    for t, m in ((9.0, E5), (9.5, G5), (10.0, C6)):
        play(bus, "marimba", m, t, 0.5, 0.7, 0.27)
    play(bus, "pizz", F2, 10.5, 0.4, 0.7, 0.4)
    # three notes, over two frames before the catch, and quiet: the catch has to be the loudest thing in the film
    for k, m in enumerate((F5, A5, C6)):
        play(bus, "marimba", m, 10.5 + 0.09 * k, 0.12, 0.6 + 0.08 * k, 0.18, seed=k)
    # a cymbal swell that tops out on the catch, and the strings answering it
    S.place(
        bus,
        P.hit("cymbal", "swell2", 0.6),
        B.TOUCH,
        0.15,
        align="peak",
        sound="swell",
        stem="music",
    )
    for m in (C5, E5, G5):
        play(bus, "violins", m, B.TOUCH, 0.5, 0.7, 0.32)
    for m in (C3, G3):
        play(bus, "cellos", m, B.TOUCH, 0.5, 0.7, 0.32)
    for m in (G3, B3, D4):
        play(bus, "violins", m, 11.3, 0.7, 0.5, 0.16)
    # end (bars 8 to 10): strings and horn under the tune, a harp run up to the last chord
    waltz(bus, 8, C2, (E4, G4, C5), 0.5)
    waltz(bus, 9, F2, (F3, A3, C4), 0.6)
    for t, d, notes in (
        (12.0, 1.4, (C4, E4, G4)),
        (13.5, 0.7, (F4, A4, C5)),
        (14.25, 0.7, (G4, B4, D5)),
    ):
        for m in notes:
            play(bus, "violins", m, t, d, 0.5, 0.1)
    for t, d, m in (
        (12.0, 1.4, C3),
        (13.5, 0.7, F2),
        (14.25, 0.7, G2),
        (15.0, 1.3, C3),
    ):
        play(bus, "horn", m, t, d, 0.5, 0.11)
    for t, m in (
        (12.0, G6),
        (12.5, E6),
        (13.0, C6),
        (13.5, A6),
        (14.0, G6),
        (14.5, B6),
        (15.0, C7),
    ):
        play(bus, "glockenspiel", m, t, 1.0, 0.6, 0.24)
    for m in (C4, E4, G4, C5):
        play(bus, "violins", m, 15.0, 1.3, 0.55, 0.1)
    for k, m in enumerate((C4, E4, G4, C5, E5, G5, C6)):
        play(bus, "harp", m, 15.0 + 0.085 * k, 1.2, 0.6, 0.16, seed=k)


def cue_sounds():
    """What each cue of scenes.CUES sounds like, by its label. No two are the same sound, so the sync check can
    tell them apart."""
    low = P.hit("bass_drum", vel=0.5)
    return {
        "hop": (P.note("marimba", E4, 0.3, 0.6), 0.55),
        "cut to fail": (P.note("pizz", A2, 0.7, 0.75), 0.5),
        "lands short": (together(P.note("timpani", 40, 0.9, 0.6), low * 0.7), 0.55),
        "cut to idea": (P.note("pizz", D2, 0.7, 0.55), 0.4),
        "crate stops": (
            together(P.note("marimba", 40, 0.4, 0.8), P.hit("bass_drum", vel=0.7)),
            0.6,
        ),
        "idea": (
            together(
                P.hit("triangle", "hit", 0.7), P.note("glockenspiel", E7, 1.2, 0.8)
            ),
            0.5,
        ),
        "cut to reach": (
            together(P.note("pizz", C2, 0.7, 0.8), P.hit("tambourine", "hit", 0.5)),
            0.42,
        ),
        "onto the crate": (together(P.note("marimba", G2, 0.4, 0.75), low * 0.5), 0.65),
        "catches the star": (
            together(
                P.chord("glockenspiel", (C7, E7, G7), 1.6, 0.7, strum=0.012) * 0.75,
                P.hit("triangle", "hit", 0.7, seed=1) * 0.7,
                # a harp chord under the bells, and strings held under both (music()): the catch is loud by what
                # lasts, not by its peak. Bells alone made the limiter take 6.5 dB and still measured quieter than
                # the cuts; more plucked notes on top only raised the peak again
                P.chord("harp", (C4, E4, G4, C5), 1.4, 0.8, strum=0.008) * 0.9,
            ),
            0.4,
        ),
        "lands with the star": (
            together(
                P.note("timpani", G2, 0.9, 0.7), P.hit("tambourine", "hit", 0.6, seed=1)
            ),
            0.5,
        ),
        "cut to end": (P.chord("harp", (C3, G3, E4, C5), 1.6, 0.8, strum=0.03), 0.23),
        "bounce 1": (
            together(
                P.note("pizz", F2, 0.6, 0.7), P.hit("tambourine", "hit", 0.45, seed=2)
            ),
            0.45,
        ),
        "bounce 2": (
            together(
                P.note("pizz", C2, 0.9, 0.8, seed=1),
                P.hit("tambourine", "hit", 0.5, seed=3),
            ),
            0.45,
        ),
    }


def render_audio(scenes, folder=".", fps=None):
    """The score as the build files in folder: MIX_RAW, SFX, CUESHEET and CUE_SOUNDS, as audio.render_audio writes
    them. Returns their paths."""
    n = C.sample_of(scenes.DURATION, S.SR)
    sounds = cue_sounds()
    with S.recording() as sheet:
        bus, sfx = np.zeros(n), np.zeros(n)
        music(bus)
        # the bed up and the cue sounds down a little (CUE): raw, the cues stood 5 dB over the level the
        # master aims for, and its limiter would have had to pull every one of them back
        bus = S.reverb(bus, 0.12) * BED
        for c in C.cues(scenes):
            if c["kind"] == "picture":
                continue
            sig, g = sounds[c["label"]]
            S.place(sfx, sig, c["t"], g * CUE, sound=c["label"], label=c["label"])
        # the crate sliding in: a rush of air that swells to the stop, so the slide is heard while it is seen
        S.place(
            sfx,
            S.whoosh(0.7, seed=7),
            B.CRATE_STOP - 0.08,
            0.14,
            align="peak",
            sound="slide",
        )
        # and a first breath of it as the crate comes into view: Pip turned and gasped 0.2 s before anything sounded
        S.place(
            sfx,
            S.whoosh(0.5, seed=8),
            B.CRATE_IN + 0.1,
            0.05,
            align="peak",
            sound="rush",
        )
    fade = C.sample_of(0.6, S.SR)
    bus[-fade:] *= np.linspace(1, 0, fade) ** 1.5
    sfx[-fade:] *= np.linspace(1, 0, fade) ** 1.5
    scale = 0.85 / max(np.abs(bus + sfx).max(), np.abs(sfx).max(), 1e-9)
    out = {k: str(Path(folder, getattr(C, k.upper()))) for k in ("mix_raw", "sfx")}
    audio.write_wav(out["mix_raw"], bus + sfx, scale=scale)
    audio.write_wav(out["sfx"], sfx, scale=scale)
    out["cuesheet"], out["cue_sounds"] = sheet.write(folder, scale)
    return out
