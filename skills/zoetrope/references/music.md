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

Then `audio.master(C.MIX_RAW, C.MIX)`; in a build, put this score in the working folder as `score.py`, in a function `render_audio(scenes, folder=".", fps=None)` that returns the paths as `audio.render_audio` does: `run_all.py` then calls it in place of the template's. A score that writes into a bus without recording gets Q902 from the onset detector only (a guess) and one Q804 NOTE (`qa-gates.md`, gates 8 and 9).

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

### Recorded instruments

For real instruments instead of oscillators, `engine/sampler.py` (`import sampler as SP`) plays recorded glockenspiel, marimba, harp, pizzicato and sustained strings, flute, horn, timpani and orchestral percussion (CC0, Versilian Studios) as mono arrays at `S.SR`, placed with `S.place` beside this kit: `SP.note("harp", 60, 1.0)`, `SP.chord("violins", [60, 64, 67], 4.0)`, `SP.hit("cymbal", "swell4")`. Fetch what a score plays before the build (`python engine/sampler.py fetch harp pizz`), place sustained strings, flute and horn with `align="pad"`, and print `SP.credits(names)` in the delivery report. Ranges, layers, loops, licences and the measurements are in `instruments.md`.

### The template score as it plays

`audio.render_audio(scenes, folder=".", fps=None)` is the score a build gets unless the working folder has a `score.py`. It reads `DURATION` and `BPM` (120 when absent), takes the cuts from `scenes.CUTS` (else every `SCHEDULE` start after 0), gives each cut's hit the label of the CUES entry with sound within half a frame of it, and writes `mix_raw.wav`, `sfx.wav`, `cuesheet.json` and `cue_sounds.npz`, returning their paths under `mix_raw`, `sfx`, `cuesheet` and `cue_sounds`. `audio.bed(dur, bpm, cuts=(), voice_spans=(), fps=None, labels=())` returns the two buses at 44.1 kHz:

| Bus | Sound | When | Gain | Placed by |
|---|---|---|---|---|
| music | `audio.kick()`: 0.35 s sine falling from 135 to 45 Hz | beats 1 and 3 of each bar, left out within 3 frames of a cut (0.1 s without fps) | 0.6 | onset |
| music | `audio.tick()`: 30 ms of noise, named `tick` on the sheet | half a beat after every beat | 0.25 | onset |
| music | `audio.tone(f, beat, 0.01, 0.35)`: a sine one beat long, 10 ms attack, 0.35 s decay | every beat; f is 220, 261.63, 196, then 246.94 Hz, one per bar | 0.3 | onset |
| sfx | `audio.whoosh(0.4)`: noise through a low-pass that opens | apex `WHOOSH_LEAD` (0.08 s) before each cut | 0.5 | peak, `offset=-0.08` |
| sfx | `audio.hit()`: a 70 Hz thump with a noise burst, 0.5 s | on each cut, with the cut's CUES label | 0.4 | onset |

The kick is left out near a cut because the hit carries that beat. `voice_spans` multiplies the music bus by 10 ** (-8 / 20) inside each span and leaves the SFX bus alone; `render_audio` passes none. `audio.music(...)` returns the same score as one buffer, with no frame cues and no labels. `audio.place` is `synth.place` under another name. Both files are written at one scale: 0.85 over the larger of the mix's peak and the SFX bus's peak.

`audio.py` keeps its own small instruments, and their names clash with `synth.py`'s: `audio.kick`, `audio.whoosh` and `audio.tick` are other sounds than the `synth` ones. `audio.noise(d, seed=1)` takes seconds and draws standard normal noise from a fixed seed; `synth.noise(name, n, *args)` takes a sample count and draws uniform noise seeded from the name.

### The instruments and their peaks

"Lands by" is the default alignment for that `sound=` name (`synth.ALIGN`), "Heavy" the cue sheet flag Q804 counts (`synth.HEAVY`), "Peak" the buffer's own sample peak before any gain, measured on `engine/synth.py` on 2026-11-12.

| Call | Length | Sound | Lands by | Heavy | Peak |
|---|---|---|---|---|---|
| `kick(g=1.0, seed=0)` | 0.4 s | sine sweeping 178 down to 48 Hz plus a 2.5 kHz click, driven into tanh | onset | yes | -0.48 dBFS |
| `snare(g=1.0, seed=0)` | 0.25 s | noise over 1.5 kHz on a 190 Hz body | onset | no | +0.53 dBFS |
| `hat(op=False, seed=0)` | 50 ms; 200 ms open | noise over 7 kHz | onset | no | -13.22 dBFS, open -12.68 |
| `clap(seed=0)` | 0.3 s | three noise bursts between 900 Hz and 5.2 kHz at 0, 11 and 23 ms, the last ringing on | onset | no | -7.52 dBFS |
| `bass(m, dur)` | dur | MIDI note m: saw plus sine, low-passed at 420 Hz into tanh, 5 ms attack | onset | no | -11.22 dBFS (m 45, 1 s) |
| `pad(notes, dur, fc=1400, att=0.25)` | dur | chord of MIDI notes, three detuned saws a note, low-passed at fc, linear rise over att, 0.3 s fall | pad | no | -5.29 dBFS ([57, 61, 64], 1.5 s) |
| `pluck(m, dur=0.4)` | dur | a saw and its octave, low-passed at 3.5 kHz, 2 ms attack | onset | no | -2.15 dBFS (m 69) |
| `riser(dur, seed=0)` | dur | a noise band that opens and climbs, loudest at its last sample | end | no | +6.70 dBFS (2 s) |
| `boom(dur=1.2)` | dur | sine gliding 98 down to 38 Hz, driven into tanh | onset | yes | -1.24 dBFS |
| `whoosh(dur=0.5, seed=0)` | dur | noise band sweeping up, swelling to its middle | peak | no | +4.66 dBFS (0.5 s) |
| `tick(f=4200, seed=0)` | 20 ms | noise high-passed at 0.8 f | onset | no | -10.35 dBFS |

The peaks span about 20 dB, and a riser or a whoosh starts above full scale before its gain: write gains for these buffers, not for a normalised sound. `synth.ALIGN` also lists names with no generator in `synth.py`: `hit` and `tone` (the template's), `swell` and `reverse` (by end) and `chord` (by pad); a sound of your own given one of those names lands that way. `impact` and `drop` are heavy names with no generator.

Parts to build more from: `tt(n)` (time of each sample), `ex(n, tau)` (exponential decay), `hz(m)` (MIDI to Hz, 69 is 440 Hz), `saw(f, n, det=0.0)`, `lp`, `hp`, `noise(name, n, *args)`, `rng_for(name, *args)`. Two effects:

- `reverb(x, wet=0.2, taps=...)` adds five early echoes from 29 to 131 ms, each heard again at twice its delay with its gain squared. It returns an array as long as x, so pad a sound with silence first to keep its tail.
- `duck(bus, times, depth_db=6, rel=0.12, dur=0.3)` dips a bus by depth_db at each time and lets it back with time constant rel; where two dips overlap the deeper one holds. Keep it on the music bus: Q902 looks for each cue sound's own buffer on `sfx.wav`, and a dip reshapes what it finds.

The seed of a noisy generator is `rng_for(name, *args)`: the name and arguments joined by `|` (numbers as `%.9g`), hashed with crc32 into a numpy Generator, so `hat(seed=3)` is the same array on every call and `hat(seed=4)` another. Draw randomness of your own the same way (`rng_for("shaker", bar, beat)`). A seeded score writes the same bytes every run, and review relies on it: approval hashes `mix_raw.wav` in 100 ms blocks, Q1301 reads an audio-only change as a NOTE and `qa.py diff` names every changed block (Q1303). Q1202 reads `scenes.py` and the local modules it imports; a score file that only `run_all.py` imports is not read, so its seeds are up to you.
