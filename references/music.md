# Music synthesized in numpy only

No scipy: filters here are one-pole (`lp`, `hp`) and block-wise for sweeps. All sound is seeded (`RandomState`) so every render is identical. `engine/synth.py` is the tested synth kit: it runs under python3 + numpy, and `python synth.py demo.wav` writes a 4 s stereo wav (44.1 kHz). Write wavs with the `wave` module as it does, then use ffmpeg for everything else.

Notes:
- Pitch helper `hz(midi)`. Reference roots from our past scores: A2=45, F2=41, G2=43, C3=48; chords A minor [57,60,64], F [53,57,60], C major [60,64,67,71].
- `lp` is a Python loop (slow on long buffers). For bars of pad/bass keep sounds short, or run per note and place with `put`. Never filter the full 60 s bus sample by sample.
- Build two buses: music and sfx. Duck the music bus on kicks. Add reverb last. Peak-normalize to 0.89, then master with loudnorm (`mixing.md`; `audio.master` does both passes).
- Sweeps (riser, whoosh) filter in blocks of 512 to 2048 samples with a moving cutoff.

The kit lives in `engine/synth.py` (`import synth as S`): `tt`, `ex`, `hz`, `lp`, `hp`, `kick`, `snare`, `hat`, `clap`, `saw`, `bass`, `pad`, `pluck`, `riser`, `boom`, `whoosh`, `tick`, `reverb`, `duck` (sidechain on kicks), `put`, `put_peak`, and `build(bpm, bars)`, the 2-bar demo groove.

### Song builder on a BPM grid

All timing derives from one beat length so cuts and music agree: `B = 60/BPM`, bar = `4*B`, phrase = 4 bars (16 beats). Put every element with `put(bus, sig, bar*4*B + beat*B)`. Structure per phrase:

- Intro (bars 1 to 2): pad + soft hats, kick muted or absent.
- Riser bar (last bar before a drop): `riser(2*B or 4*B)`, snare/clap roll doubling in density (2 then 4 hits per beat).
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

120 BPM gives a 2 s bar and a 0.5 s beat, which maps cleanly to 30 fps (15 frames per beat). Other BPMs do not land on whole frames: place cuts on the nearest frame and let audio keep the exact beat time.

Extra instruments seen in past scores (add if needed): `bell(m,dur)` = sine at f plus partials at 2.76f and 5.4f with fast decays; `blip(m)` = FM sine with `exp(-t/0.03)` modulation; `swish(dur,fc0,fc1)` = short band-passed noise with sine envelope; `crash` = high-passed noise (above 5 kHz) with `exp(-t/0.45)`.
