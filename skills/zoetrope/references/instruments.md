# Recorded instruments: `engine/sampler.py`

`synth.py` makes every sound from oscillators and noise, which reads as synthetic. `sampler.py` plays real recorded instruments from two CC0 sample libraries by Versilian Studios: glockenspiel, marimba, harp, pizzicato and sustained strings, flute, horn, timpani and orchestral percussion. Every sound comes back as a mono float array at `synth.SR` (44.1 kHz) whose attack starts at sample 0, so it goes through `synth.place` like any synth sound, onto the music bus or the SFX bus, inside a cue-sheet recording.

numpy and the standard library only, plus ffmpeg (already required) to decode each file once. No scipy, no new dependency.

## Fetch first

Instruments are fetched on demand, so a build pulls only what it plays. The builder agent cannot download: fetch in the main chat before the build.

```
python engine/sampler.py list                     # each instrument: family, kind, playable range, layers, MB, cached or not
python engine/sampler.py fetch glockenspiel pizz  # just these (all 14 when no name is given: 232.8 MB)
python engine/sampler.py missing                  # what is not cached yet (exit 1 when anything is)
python engine/sampler.py demo out.wav             # an 8-bar phrase at 100 BPM on five instruments, mastered to -14 LUFS
```

The cache is `~/.cache/zoetrope/instruments` (override with `ZOETROPE_INSTRUMENTS`), one folder for every build, never inside the repo. Originals keep their library paths under `VSCO-2-CE/` and `VCSL/`. Each file is downloaded from `raw.githubusercontent.com` at the pinned commit and kept only when its size and sha256 match the manifest; `fetch` then decodes it once (ffmpeg to float32 at 44.1 kHz, the two channels averaged) into `<name>.<sha256[:12]>.npy` beside the original, so later builds never call ffmpeg. All 14 instruments take 232.8 MB of originals and 199 MiB of decoded copies. A note on an instrument that is not cached raises `FileNotFoundError` naming the `python sampler.py fetch <name>` command.

## Play

```python
import numpy as np
import contract as C, sampler as SP, synth as S

with S.recording() as sheet:
    music, sfx = np.zeros(C.sample_of(DUR, S.SR)), np.zeros(C.sample_of(DUR, S.SR))
    S.place(sfx, SP.note("glockenspiel", 84, 1.5), 2.5, 0.5, label="logo reveal")  # a ding on its cue
    S.place(music, SP.chord("violins", [60, 64, 67], 4.0, vel=0.45), 4.0, 0.3, align="pad", stem="music")
    for k, m in enumerate([48, 55, 60, 55]):  # pizz eighths, seed=k alternates the round robins
        S.place(music, SP.note("pizz", m, 0.3, vel=0.7, seed=k), 4.0 + k * 0.3, 0.4, stem="music")
    S.place(sfx, SP.hit("cymbal", "swell4"), 8.0, 0.4, align="peak", sound="swell", label="reveal")
    S.place(sfx, SP.note("timpani", 43, 1.0, vel=0.9), 12.0, 0.5, sound="hit", label="drop")  # heavy: Q804 counts it
```

Then write the mix, the SFX stem and the sheet on one scale and master, exactly as `music.md` shows.

- `note(inst, midi, dur, vel=0.8, seed=0)`: a pitched note held for `dur` seconds. A float `midi` plays between the keys. `dur=None` lets a struck or plucked note ring out, or plays a sustain's recording as it is.
- `chord(inst, midis, dur, vel=0.8, strum=0.0, seed=0)`: the notes summed, each at `vel` (not normalised), all released at `dur`. `strum` seconds between notes in the order given; negative strums from the last note. Note k takes `seed + k`.
- `hit(inst, variant=None, vel=0.8, seed=0)`: an unpitched hit, whole. `variants(inst)` lists the variants, the default first.
- `instruments()`, `spans(inst)` (the playable MIDI runs), `missing(names=None)`, `fetch(names=None)`, `credits(names)`.

How each part behaves:

- **Pitch.** A note plays from the recording nearest its pitch, resampled to the exact pitch by FFT (the spectrum cut or zero-padded at the lower Nyquist with a raised-cosine roll-off over its top 5 percent, so nothing aliases and attacks do not ring). Each recording's own tuning is in the manifest (measured: the glockenspiel is 8 to 25 cents sharp, the harp 1 to 31 cents flat), so a note lands on the equal-tempered pitch, not on the recording's. The largest shift allowed is 4 semitones (`MAX_SHIFT`), and 2 past the lowest or highest recording (`EDGE`). In practice no note moves more than 3.5 semitones (half the glockenspiel's and marimba's widest gap) except at the edges of the horn's gap: the library has no horn between C4 and D5, so the horn plays G1 to E4 and B4 to G5 and `note()` raises a `ValueError` naming the spans for anything else.
- **Velocity.** `vel` in (0, 1] picks the dynamic layer, ceil(vel x the layer count) or the nearest one the key has, and sets the peak: `vel ** 1.6` (`VEL_CURVE`; vel 1 peaks at full scale, 0.8 at -3.1 dB, 0.5 at -9.6 dB). Every recording is peak-normalised first, because the libraries keep their natural levels (the softest timpani peak at -62 dBFS).
- **Round robins.** Chosen from the call's own arguments plus `seed`, with no global random state, so the same call returns bit-identical samples in any process. Consecutive seeds always alternate: pass `seed=i` for note i of a repeated pattern.
- **Decay instruments** (glockenspiel, marimba, harp, pizz, timpani) ring for `dur` and are then damped, `exp(-t / damp)` for six time constants (damp 0.05 s for pizz up to 0.15 s for timpani). Only the part that plays is resampled, which keeps a score's audio build to seconds.
- **Sustained instruments** (violins, cellos, flute, horn) are held for `dur`. Past the recording, the steady part is looped: the loop lies in the longest stretch whose smoothed 50 ms level stays within 4 dB of the sustain level, is at least half that stretch long, and returns where the waveform matches best (normalised correlation over 0.15 s). Every return is crossfaded over 0.15 s with a gain that keeps the power constant for the measured correlation: equal gain for a matched solo tone, equal power for a section whose phases never line up. At `dur` the note is spliced into its own recorded release, which starts within 0.1 s after `dur`; a note stopped during its attack fades out over 0.2 s instead. Strings, flute and horn take time to speak: they reach -15 dB up to 171 ms in (violins; cellos 126, flute 120, horn 117 ms at worst), so place them with `align="pad"` to land the swell on the beat.
- **Onset.** Every returned sound, chords included, starts 2 ms before its onset, `synth.landmarks`' measure (the first 1 ms block within 30 dB of the loudest), with those 2 ms faded in. Cue sync measures where a placed sound is heard, so this makes `align="onset"` and `align="start"` agree to 2 ms.
- **Short sustains are quieter.** A string or flute note under about 2 s is released while it is still swelling, so it peaks 2 to 4 dB under what its `vel` gives a long one (violins G4 at vel 0.8: 0.52 for 1 s, 0.69 for 8 s; the horn is the same at both; a second reader measured this on 2026-11-10). Raise `g` for a short one. The swells and the shake (`cymbal` `swell2` and `swell4`, `tambourine` `shake`) reach a tenth of their peak 118 to 654 ms in by design: place them by their peak, not their onset.
- **Placement names.** A sampled sound has no generator name, so `place` aligns its onset. Name the heavy ones (`sound="hit"` or `"boom"` for timpani and bass drum accents) so Q804's stack guard counts them. Place the cymbal swells by their peak (`align="peak", sound="swell"`): they ring for seconds after the climax, so `align="end"` would land the climax early.

## The instruments

All CC0 1.0. Ranges are what `note()` plays (scientific pitch, C4 = MIDI 60). Fetched 2026-11-10: 210 files, 232,796,254 bytes.

| Name | Library | Files | MB | Range | Layers | Kind | Why it is in the set |
|---|---|---|---|---|---|---|---|
| glockenspiel | VCSL | 18 | 17.2 | F#5 to D8 | 3 | decay | sparkle, reveal dings, a bright top-line melody |
| marimba | VCSL | 20 | 22.1 | E2 to C#7 | 2 | decay | warm wooden ostinato and bass for friendly explainers |
| harp | VSCO 2 CE | 20 | 27.8 | C2 to F#7 | 1 | decay | arpeggios and strummed chords, soft openings |
| pizz | VSCO 2 CE | 56 | 18.8 | B1 to E6 | 2 | decay | the playful pizzicato line; cellos under G3, violins from G3 |
| timpani | VSCO 2 CE | 10 | 11.3 | E2 to G#3 | 2 | decay | tuned booms on downbeats and reveals |
| violins | VSCO 2 CE | 22 | 46.0 | F3 to E6 | 2 | sustain | section pad and long melody, with vibrato |
| cellos | VSCO 2 CE | 10 | 23.8 | A#1 to A4 | 1 | sustain | warm low pad and held bass, with vibrato |
| flute | VSCO 2 CE | 10 | 19.3 | A#3 to D7 | 1 | sustain | a light melody over a pad, with vibrato |
| horn | VSCO 2 CE | 11 | 20.7 | G1 to E4, B4 to G5 | 1 | sustain | warm brass pad and swells, low and middle register |
| bass_drum | VCSL | 8 | 4.6 | variant hit | 4 | hit | orchestral boom under a hit or a cut |
| snare | VCSL | 9 | 3.8 | variants hit, roll | 4 | hit | concert snare accents, a roll under a build |
| cymbal | VCSL | 6 | 12.3 | variants hit, swell2, swell4 | 4 | hit | suspended cymbal; 2 s and 4 s crescendos into a reveal |
| triangle | VCSL | 6 | 4.0 | variants hit, mute | 2 | hit | a bright accent on a payoff; mute for a short tick |
| tambourine | VCSL | 4 | 1.1 | variants hit, shake | 2 | hit | the upbeat pulse: hit on 2 and 4, shake on the offbeats |

Where each comes from, at the pinned commits:

- glockenspiel: VCSL `Idiophones/Struck Idiophones/Glockenspiel`, soft, medium and loud. The file names read one octave under the sounding pitch (`glock_loud_C5` sounds C6); the manifest keys are the measured sounding pitch.
- marimba: VCSL `Idiophones/Struck Idiophones/Marimba`, soft and loud (the medium layer is left out for size).
- harp: VSCO 2 CE `Strings/Harp`, mf, 20 of 23 notes (E1, G1 and B1 left out for size).
- pizz: VSCO 2 CE `Strings/Violin Section/Pizz` (11 notes, 2 layers, 2 round robins) and `Strings/Cello Section/pizzT` (the 6 notes under G3, 2 layers, 1 round robin).
- timpani: VSCO 2 CE `Percussion/Timpani`, five drums, layers v1 and v3, one round robin. Read from each drum's principal tone, they are tuned F2 +49 cents, B2 -22, D3 +48, E3 +42 and F#3 +46 (four of the five near quarter tones), and `note()` retunes them to the note asked.
- violins: VSCO 2 CE `Strings/Violin Section/susVib`, 11 notes, both layers.
- cellos: VSCO 2 CE `Strings/Cello Section/susvib`, layer v1, the 10 notes up to G3.
- flute: VSCO 2 CE `Woodwinds/Flute/susvib`, layer v1, 10 notes.
- horn: VSCO 2 CE `Brass/F Horn/sus`, layer v1, 11 notes (the library has none from C#4 to C#5).
- bass_drum: VCSL `Membranophones/Struck Membranophones/Bass Drum 1`.
- snare: VCSL `Membranophones/Struck Membranophones/Snare Drum, Modern 1`, snares on: 4 layers with 2 round robins, and one roll.
- cymbal: VCSL `Idiophones/Struck Idiophones/Suspended Cymbal 1`: soft-mallet hits pp, mp, f and fff, and the 2 s and 4 s crescendos.
- triangle: VCSL `Idiophones/Struck Idiophones/Triangles`, Triangle 1: open hits (2 layers, 2 round robins) and muted hits.
- tambourine: VCSL `Idiophones/Struck Idiophones/Tambourine 1`: hits (2 layers) and shakes (2 round robins).

In the folders used here the file names put middle C at C3, except the harp's, which put it at C4. Every root in the manifest was measured from the recording, not read from its name.

## Licences and credits

| Library | Repository and pinned commit | Licence |
|---|---|---|
| VSCO 2: Community Edition, Versilian Studios (Sam Gossner, Simon Dalzell) | `sgossner/VSCO-2-CE` at `440300901dfe9275fd84e0b7763af1f8443ae62e` (master, 2020-08-05) | CC0 1.0 Universal: `LICENSE` at the repository root; GitHub's licence field reads CC0-1.0 |
| Versilian Community Sample Library (VCSL), Versilian Studios | `sgossner/VCSL` at `c1ea7bcc3c7309650ab0da9d15c9cd1fbc4a4c7e` (master, 2026-01-14) | CC0 1.0 Universal: `LICENSE` at the repository root (added in that commit); GitHub's licence field reads CC0-1.0 |

Both licence files were read at the pinned commits on 2026-11-10. Every file in the set is from these two repositories; no file under another licence was needed or used. CC0 asks for no credit. VSCO 2 CE's `Readme.txt` asks users to credit Versilian Studios (and Ivy Audio where it applies), to link the VSCO CE homepage, and not to sell the samples on their own; VCSL's `README.md` says no credit is needed. We credit both anyway: `SP.credits(names)` returns the lines for the delivery report's "Media and credits" field, one per library, for example:

```
Sampled instruments (pizz, violins): VSCO 2: Community Edition by Versilian Studios (Sam Gossner, Simon Dalzell), CC0 1.0, https://versilian-studios.com/vsco-community/ (files from github.com/sgossner/VSCO-2-CE at 4403009)
Sampled instruments (glockenspiel, cymbal): Versilian Community Sample Library by Versilian Studios, CC0 1.0, https://github.com/sgossner/VCSL (files from github.com/sgossner/VCSL at c1ea7bc)
```

## Left out, and why

- **Kalimba.** VCSL has two (Kenya and Tanzania). Both ring sympathetically: other tines sound within 0 to 10 dB of the played note, and on the high keys the low ones are louder than the note itself. Shifted, that cloud moves with every pitch, so chords and melodies smear. Left out after reading the spectra of 12 files on 2026-11-10.
- **Celesta, music box, toy piano, ukulele.** Neither library has one.
- **Vibraphone, tubular bells, a second horn or cello layer, timpani rolls.** They exist, but would push the set past 250 MB; add a row (and its sha256) to `FILES` to fetch one.

## Measured on 2026-11-10

The check scripts are in `outputs/scratch/sampler/` (not committed).

- Pitch: five notes across each pitched instrument's range land within 7.3 cents of the target (timpani G#3); every playable note at two velocities (770 notes) within 9.4 cents (timpani G3). Both are read by the FFT peak with parabolic interpolation, the reading the manifest's tuning came from. An autocorrelation reading agrees within 5.6 cents on the harmonic instruments (harp, strings, flute, horn) but cannot read the inharmonic ones (marimba, glockenspiel, timpani).
- Determinism: eight calls, including a 30 s looped note, a strummed chord and a cold decode, gave identical sha256 in separate processes with different `PYTHONHASHSEED`.
- Seams: every one of the 53 sustained recordings held for three times its length: the largest sample-to-sample jump in the extended part never exceeds the recording's own (ratio 1.00 at most); the 10 ms level step at the seams is at most 0.6 dB over the largest the recording makes on its own.
- Onset: 586 sounds (every recording at its own key and 3 semitones either side, every variant, and chords) have their onset at most 2 ms after sample 0.
- Cue sheet: a glockenspiel note placed at 2.5 s with a label is recorded at 2.5 s, and Q902's own search (`qa_sync.locate` on the SFX stem) finds it at 2.5 s, within 0.01 ms.
- Not checked by ear: the demo and its synth A/B were written for a person to listen to.
