# Music synthesized in numpy only

No scipy: filters here are one-pole (`lp`, `hp`) and block-wise for sweeps. Every generator seeds its noise from its own name and arguments (`synth.noise(name, n, *args)`), so adding, removing or moving one sound never changes another: with the old shared RandomState one sound more changed 6 of 6 later sounds (2026-10-28). Pass `seed=` (a number or a name) for a variant, one per round-robin copy; a score's own random draws (phases, jitter, Gaussian noise) come from `synth.rng_for(name, *args)`, one stream per sound, never one module RandomState for a whole score. `engine/synth.py` is the tested synth kit: it runs under python3 + numpy, and `python synth.py demo.wav` writes a 4 s stereo wav (44.1 kHz). Write wavs with the `wave` module as it does, then use ffmpeg for everything else.

Notes:
- Pitch helper `hz(midi)`. Reference roots from our past scores: A2=45, F2=41, G2=43, C3=48; chords A minor [57,60,64], F [53,57,60], C major [60,64,67,71].
- `lp` is a Python loop (slow on long buffers). For bars of pad/bass keep sounds short, or run per note and place with `put`. Never filter the full 60 s bus sample by sample.
- Build two buses, music and sfx, and keep every SFX on its own bus: Q902 measures cues on the SFX stem. Duck the music bus on kicks. Add reverb last. Then master with `audio.master` (`mixing.md`), never by peak-normalising alone.
- Sweeps (riser, whoosh) filter in blocks of 512 to 2048 samples with a moving cutoff.

The kit lives in `engine/synth.py` (`import synth as S`): `tt`, `ex`, `hz`, `lp`, `hp`, `rng_for`, `noise`, `kick`, `snare`, `hat`, `clap`, `saw`, `bass`, `pad`, `pluck`, `riser`, `boom`, `whoosh`, `tick`, `reverb`, `duck` (sidechain on kicks), `landmarks`, `place`, `put`, `put_peak`, `recording`, and `build(bpm, bars)`, the 2-bar demo groove. `synth.rng` (a RandomState) stays only for old scores that still draw from it.

### Record the placements

Place every sound with `S.place` (or `put`, `put_peak`) inside one recording, then write the mix, the SFX stem and the cue sheet on one scale, as `audio.render_audio` does for the template:

```python
import numpy as np
import audio, contract as C, synth as S

with S.recording() as sheet:
    music, sfx = np.zeros(C.sample_of(DUR, S.SR)), np.zeros(C.sample_of(DUR, S.SR))
    S.place(sfx, audio.hit(), 2.5, 0.4, sound="hit", label="cut to point")  # on its CUES label
    S.place(music, S.pad([57, 60, 64], 2.0), 4.0, 0.3, sound="pad", stem="music")
scale = 0.85 / max(np.abs(music + sfx).max(), np.abs(sfx).max())
audio.write_wav(C.MIX_RAW, music + sfx, scale=scale)
audio.write_wav(C.SFX, sfx, scale=scale)
sheet.write(".", scale)  # cuesheet.json and cue_sounds.npz
```

Then `audio.master(C.MIX_RAW, C.MIX)`; in a build, put this score where `run_all.deliver` calls `audio.render_audio`. A score that writes into a bus without recording gets Q902 from the onset detector only (a guess) and one Q804 NOTE (`qa-gates.md`, gates 8 and 9).

### Song builder on a BPM grid

All timing derives from one beat length so cuts and music agree: `B = 60/BPM`, bar = `4*B`, phrase = 4 bars (16 beats). Place every element at `bar*4*B + beat*B`, by its landmark (`beat-sync.md`, item 4). Structure per phrase:

- Intro (bars 1 to 2): pad + soft hats, kick muted or absent.
- Riser bar (last bar before a drop): `riser(2*B or 4*B)` placed by its end on the drop, snare/clap roll doubling in density (2 then 4 hits per beat).
- Drop (bar line, e.g. bar 3 or 5): `boom()` + crash (high-passed noise burst) + full kick, hats, bass, pad.
- Body: kick on every beat, clap or snare on beats 2 and 4, offbeat hat, bass on eighths, arp pluck on sixteenths from the second phrase on.
- Outro: drop the drums, hold pad, final kick + boom on the end card, 0.6 to 0.8 s fade (`np.linspace(1,0,n)**1.5`).

Align the video length to a whole number of bars (or end on a bar line plus a short tail for the final hit's decay). Scene lengths are whole beats (even numbers), and section starts that carry a hard cut sit on a multiple of 4 beats.

### Mood presets

| Preset | BPM | Beat (s) | Ingredients (our suggestion) |
|---|---|---|---|
| Tech pulse | 120 | 0.5 | four-on-floor kick, offbeat hat, clap 2/4, saw bass on eighths, pad, pluck arp, riser into drop |
| Upbeat pop | 112 | 0.536 | kick + snare backbeat, bright pluck/bell melody, pad, bass on beats |
| Cinematic swell | 80 | 0.75 | no drums until the drop, low pad, long riser, `boom()` impact, bell tails |
| Lo-fi | 84 | 0.714 | soft kick, snare, dusty hats (lower gain, low-pass), warm pad, sparse pluck |
| Chiptune | 140 | 0.429 | square/saw blips (`blip`), simple bass, tick hats, short kicks |
| Ambient | 70 | 0.857 | pads only, slow attack (0.4 s+), bell/pluck now and then, no drums |

120 BPM gives a 2 s bar and a 0.5 s beat, which maps cleanly to 30 fps (15 frames per beat). Other BPMs do not land on whole frames (Q905 notes them): place cuts on the nearest frame and let audio keep the exact beat time. A pad with a slow attack (the ambient preset) is heard late when placed by its first sample: place it with `align='pad'` on its cue, or shorten the attack under 80 ms and align its onset.

Extra instruments seen in past scores (add if needed): `bell(m,dur)` = sine at f plus partials at 2.76f and 5.4f with fast decays; `blip(m)` = FM sine with `exp(-t/0.03)` modulation; `swish(dur,fc0,fc1)` = short band-passed noise with sine envelope; `crash` = high-passed noise (above 5 kHz) with `exp(-t/0.45)`. Seed their noise with `S.rng_for("crash", k)`.
