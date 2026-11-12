# Beat sync

1. One grid: `t(bar, beat) = T0 + ((bar-1)*4 + (beat-1)) * B`. For our own synthesized music T0 is 0 and B is exact; every cut, scene start and SFX reads this function. Declare scene lengths in beats (`compile_schedule(TIMELINE, bpm=BPM)`) and the cuts stay on the grid, rounded once to the nearest frame.
2. Cuts on beats: scene boundaries on beats (strong cuts on bar lines, small changes on beats 2 to 4). Hard cut times are `SCHEDULE` or `CUTS` values, not hand-typed. At 30 fps a beat is a whole number of frames only at some tempos (120 BPM is 15 frames, 128 BPM is 14.06): Q905 notes the others, and their cuts land on the nearest frame while the audio keeps the exact beat time.
3. Drop on a bar line: the big visual change (logo, price, end card) lands on the first beat of a bar, with the riser filling the bar before. In a past build the last-bar-before-drop was the riser bar and the drop was the next bar.
4. SFX by landmark: `synth.place(bus, sfx, t, g, sound=name)` lands the generator's own instant on t, on the nearest sample; `frame=n, fps=f` places it on a frame's first sample instead. Place every sound this way inside `with synth.recording() as sheet:`, so it lands on the cue sheet Q902 and Q804 measure, and give the sound that serves a cue its CUES label (`label=`).

   | Align | Instant (from the sound's first sample) | Default for |
   |---|---|---|
   | `onset` | start of the first 1 ms block within 30 dB of the loudest | kick, snare, clap, hat, tick, hit, pluck, bass, tone, boom, any unnamed sound |
   | `peak` | middle of the loudest window: 50 ms for whoosh, riser, swell and reverse, 5 ms for the rest (an unnamed sound still rising 30 ms after its onset takes 50 ms) | whoosh |
   | `end` | end of the last 5 ms block within 50 dB of the loudest | swell, riser, reverse |
   | `pad` | the -15 dB point of the attack (`pad_db=` -15 to -6) | pad, chord |
   | `start` | the first sample | `synth.put` |

   - `synth.put_peak` is align peak; `synth.put` keeps the first sample on the time (beds and lead-ins are timed that way). A 1 ms argmax on a noise whoosh moved its peak by up to 128 ms between seeds (2026-10-28); the 50 ms window halves that.
   - A pad or chord lands its -15 dB attack with `align='pad'`: synth.pad knows its own ramp; any other generator that knows its instant passes `landmark=` (seconds). A measured pad point on a beating chord read 0.65 to 2.8 times the true one, so the sheet marks it with `landmark_tol`; rise times over 80 ms are untested.
   - A slow sound placed by its start or onset is heard late, and Q902 holds it to its audible attack (the sheet's `audible_s`): synth.pad's 0.25 s attack is heard 44 ms in. A labelled `put` or onset row heard over 10 ms late warns; place such a sound with `align='pad'`.
   - `offset=-0.08` lands a lead-in's apex just before a hit instead of on it: the template's whoosh peaks 80 ms before its cut hit (on the hit it stacked 1.8 dB of true peak onto it). `align='end'` warns when the sound rings over 30 ms past its climax (trim the tail, or align peak).
   - A sound that would start before 0 loses its head, fades in over 3 ms, and warns when its landmark itself is cut.
   - Whoosh peaks at the maximum speed of the move; chimes land on the beat after the dot lands (half a beat later in the past build).
5. Sound may lead the picture a little, never trail it. This is a house rule, justified by ITU-R BT.1359-1 (viewers detect sound more than 45 ms early or 125 ms late; a lip-sync figure, an analogy for SFX). Q902 holds every audio cue to it: a FIX when the sound is late by more than one frame (33.3 ms at 30 fps, 41.7 ms at 24, 16.7 ms at 60, never over 60 ms) or early by more than 40 ms, and a NOTE outside -5..+15 ms (the per-stage window of EBU R37, also lip sync). Put cue times on frame starts (the picture can only change on a frame); an off-grid time can miss the NOTE window by up to half a frame.
6. SFX level: SFX sit well under music (past builds used about -17 to -31 dB per hit relative to full scale, tick -28 to -31, whoosh -18). Pan ticks slightly left or right (about +/-0.2).
7. Check kick alignment (if music was not made by us, or to prove ours): low-pass the music (35 to 140 Hz band), take the envelope, mark each kick onset as the first upward crossing of 25 percent of the maximum with a 300 ms refractory window (sub bass can enter about 45 ms after a kick and would otherwise be counted). Fit `t = t0 + n*period` to the onsets within 40 ms of the grid by least squares. Pass if the largest residual is only a few milliseconds and the fitted BPM matches the preset. Autocorrelation tempo can come out as half or double: fold into 90 to 180 BPM. For a score with no cue sheet, give a hard cue its band and region in CUES, as the lighthouse build's own sync check did (ticks above 1.8 kHz, the cluster under 200 Hz, the gear's box): `{"t": 12.0, "label": "gear", "band": (1800, 9000), "region": (x0, y0, x1, y1)}`.
8. Frame check: convert each cut time to a frame with `frame_of(t, fps)` (the nearest frame; halves round up, the one rule in every module) and confirm in the contact sheet that the frame at the cut shows the new scene and the frame before shows the old one.
9. Tweens: start a tween one frame before its cue (`cue - 1/fps`), so the first visible change lands on the cue frame. Cue the sound at the perceived moment, about the 97 percent frame of the tween, not its last frame (cinetic).
10. Voice vs. beat: words that carry a cue (price, "now", brand name) are timed by the engine in `narration.json`: `C.snap(voice.word_cue(N, "now"), FPS)` is the cue (`voice.md`; sapi and kokoro-ts give word times). For a voice file from elsewhere, find the word's onset by RMS onset and convert it to video time with `t0 + (onset - trim) / TEMPO`.

11. The beat map in a style card writes a moment as bar.beat, both counted from 1, four beats to the bar (`3.1` is the first beat of bar 3). A score turns it into seconds with `def t(bar, beat): return ((bar - 1) * 4 + (beat - 1)) * 60 / BPM`; at 120 BPM `t(3, 1)` is 4.0 and `t(1, 2.5)` is the off-beat after beat 2.

## One clock for sound and picture

`contract.py` rounds time one way for both: `frame_of(t, fps)` is the nearest frame (halves up), `sample_of(t, sr)` the nearest sample (halves up), `frame_sample(frame, fps, sr)` the first sample of a frame (frame 60 at 30 fps is sample 88200 at 44.1 kHz; frame 1 at 24 fps is sample 1837.5, rounded to 1838). A sound placed on a frame cue (`frame=` and `fps=`) puts its landmark on that frame's first sample.

| Rate | Where |
|---|---|
| 44,100 Hz | `audio.SR`, `synth.SR`, `voice.SR`: every bus, `mix_raw.wav`, `sfx.wav`, the cue sheet and `narration.wav`; `voice.dec` brings any outside file in at this rate |
| 48,000 Hz | `audio.SR_MASTER`: `audio.master` decodes the raw mix at this rate through ffmpeg, limits there and writes `mix.wav` |
| the gates' own | decodes of the finished file: 48 kHz for the true peak, the cue confirm and the audio picture, 8 kHz for Q803 and the no-sheet onset detector |

A buffer made at another rate and added by sample count plays at the wrong speed: 44.1 kHz samples read as 48 kHz run 8.1 percent fast, so a sound meant for 8.0 s plays at 7.35 s, 650 ms early (`t x 44100 / 48000`). Build every buffer at `synth.SR`, bring outside audio in through `voice.dec`, and record the cue sheet at the rate of its buffers: Q902 resamples each sheet buffer to the stem's rate before it searches.

## Landmarks and place, in detail

`synth.landmarks(sig, sound=None, pad_db=-15.0)` also returns `ring` (`end` less the middle of the loudest 5 ms: how long the sound rings past its climax), `win` (the peak window), `peak_dbfs` and `pad_known` (the pad point came from the generator). `pad_db` outside -15 to -6 raises ValueError.

- The ramp of `synth.pad` is known only for the very array the generator returned (`synth._KNOWN`, keyed by the array's id). A copy or a scaled array is measured instead, and a beating chord measures badly (2026-10-28 `pad([57, 61, 64], 1.5)`: 44.5 ms at att 0.25 and 88.9 ms at att 0.5 known; the same arrays times 1.0 measured 34.5 and 205.9 ms). Set a sound's level with the `g` of `place`, never by scaling its array. A measured pad point carries `PAD_TOL` (0.65) times itself as `landmark_tol`.
- `place(buf, sig, at=None, g=1.0, align=None, sound=None, label="", stem="sfx", frame=None, fps=None, offset=0.0, pad_db=-15.0, landmark=None)`: the first sample lands at the event less the instant, to the nearest sample. A start before 0 cuts the head and fades what is kept in over 3 ms; anything past the end of `buf` is dropped; a sound wholly outside `buf` adds nothing and records no row. An unknown `align` raises ValueError. `landmark=` (seconds) replaces the measured instant. `put` is `place` with `align="start"`, `put_peak` with `align="peak"`.
- Warnings (printed in the audio stage): the instant lands before 0; a sound placed by its end rings more than `RING` (30 ms) past its climax; a labelled sound placed by start or onset is heard more than 10 ms after the instant on its cue.
- The name matters: `sound=` is matched exactly and picks the default alignment, the peak window and the heavy flag. `sound="kick2"` lands by onset, gets the unnamed peak rule and is not heavy, so Q804 never counts it. Q804's lead-in test matches by substring, so `whoosh_soft` is still a lead-in.

Which instant to put on a cue:

| The moment | Place it | Why |
|---|---|---|
| a drum, hit, pluck or tick on the frame where something lands | by onset (the default), as a frame cue | its first audible energy is the event |
| a whoosh into a cut | `sound="whoosh"` (peak) with `offset=-audio.WHOOSH_LEAD` | its apex leads the cut by 80 ms |
| a riser or swell into a drop | `sound="riser"` (end) | it climaxes on its last sample (`riser(2.0)` rings 10.1 ms, under `RING`) |
| a pad or chord heard on a moment | by its pad point (the default for `pad`, `chord`) | it starts from silence |
| a sound whose instant you computed | `landmark=` | the sheet records that instant |
| a bed loop whose first sample is the beat | `put()` | no landmark to find |

`whoosh(0.5)` rings 191.7 ms past its climax (`landmarks` ring, measured 2026-11-12), so placed by its end it warns and lands its apex early; place it by its peak. `riser(2.0)` rings 10.1 ms.

### What Q902 measures

For each CUES entry with sound (kind `both` or `audio`), Q902 (`qa_sync`) takes the sheet rows that carry its label (the nearest in time when a label repeats), else the unlabelled rows within 100 ms of it, SFX bus first. It finds each row's own buffer on its stem by normalised cross-correlation, within 250 ms of where the sheet put it and at a match of 0.7 or more: on `sfx.wav` for an SFX row, on `mix_raw.wav` for a music row. The instant it hears is the start it found plus `landmark_s`; for a row placed by start or onset whose `audible_s` comes 5 ms or more after the landmark (`ATTACK_TOL`), the start plus `audible_s` instead. The heard time less the cue time is judged by `qa_sync.verdict`:

| Offset | Row |
|---|---|
| later than one frame (`late_limit(fps)`: 1000 / fps ms, never over 60: 41.7 at 24 fps, 40.0 at 25, 33.3 at 30, 20.0 at 50, 16.7 at 60) | FIX |
| earlier than -40 ms | FIX |
| inside those, but outside -5 to +15 ms | NOTE |
| no sound found for the cue | FIX |
| a copy that cannot be told from its twins | NOT CHECKED |

Name the instant a listener hears and the cue lands. Give the cue's label to the sound that lands on it, never to its lead-in: a labelled whoosh placed 80 ms ahead is heard 80 ms early, a FIX. On 2026-11-01, on the clean-room template, a `pad([57, 61, 64], 1.5)` placed by `align="start"` on both cues was heard +44.5 ms late and Q902 rejected the file; placed by its pad point it read worst +0.0 ms. A row with no `audible_s` (written by hand) gets an estimate from its buffer (`qa_sync.attack_of`).

## Stems and the cue sheet

`with synth.recording() as sheet:` opens a `CueSheet` (at `synth.SR` unless given `sr`); every `place`, `put` and `put_peak` inside adds a row. Leaving the block puts back the sheet that was open before, or none. `sheet.write(folder=".", scale=1.0)` multiplies every row's gain by `scale` and writes `cuesheet.json` (`{"sr", "cues": [row, ...]}`) and `cue_sounds.npz` (each placed sound's whole buffer, before gain, float32 under `c<i>`). Row keys are `contract.CUESHEET_KEYS`:

| Key | Holds |
|---|---|
| `i` | row index, and its key `c<i>` in `cue_sounds.npz` |
| `label` | the CUES label the sound serves, or `""` |
| `sound` | the `sound=` name |
| `t` | event time in seconds, offset included |
| `align` | the instant placed on `t` |
| `landmark_s` | seconds from the first sample to that instant |
| `start_s` | where the first kept sample went, clipped at 0 |
| `gain` | placing gain times the write scale |
| `peak_dbfs` | the buffer's own sample peak |
| `heavy` | true for kick, hit, boom, impact, drop |
| `bus` | `sfx` or `music`, from `stem=` |
| `trim_s` | seconds cut off the head |
| `audible_s` | seconds to the -15 dB attack point |
| `landmark_tol` | how far a measured landmark may be off; 0 when the generator reported it |

- Put every sound that serves a cue on the SFX bus (`stem="sfx"`, the default) and the bed on the music bus. `sfx.wav` holds the SFX bus alone, so Q902 finds a cue's sound with no bed under it. Q804 counts SFX rows, and music rows only when they carry a label.
- Write `mix_raw.wav` and `sfx.wav` with `audio.write_wav(path, mono, voice=None, scale=...)` at one scale and give `sheet.write` the same scale: `sfx.wav` then matches the SFX part of `mix_raw.wav` sample for sample, and Q802 reads the bed as `mix_raw.wav` less `sfx.wav`.
- `write_wav` writes 16-bit stereo at `audio.SR`, the same mono in both channels. With no scale it peak-normalises to 0.85 and returns the scale used. A scale you pass is not clipped: samples 0, 0.5, 1.2 and -1.2 at scale 1.0 came back as 0, 16383, -26216 and 26216 (measured 2026-11-12).
- A score of your own must write all four files this way. Without `cuesheet.json`, Q902 falls back on an onset detector (one NOTE, says it guesses), Q804 gives one NOTE and Q802 cannot name the sounds at a peak. A sheet whose buffers or stems are missing makes Q902 NOT CHECKED.

## Tempo and the grid

A beat lasts `60 / BPM` seconds, `60 x fps / BPM` frames; `contract.whole_frame_beat(bpm, fps)` says whether that is whole.

| BPM | Beat | Frames at 30 fps |
|---|---|---|
| 75 | 0.8 s | 24 |
| 100 | 0.6 s | 18 |
| 120 | 0.5 s | 15 |
| 128 | 0.4688 s | 14.06, not whole |
| 150 | 0.4 s | 12 |

How a card's tempo reaches every part: the card's Format section gives the default; the scenario header carries it as `bpm:`; `scenes.py` sets `BPM` and gives scene lengths in beats with `compile_schedule(TIMELINE, bpm=BPM)`; `render_audio` and a score of your own read `scenes.BPM`; `run_all.deliver` passes it to `qa.check` for Q901, `qa_lint` reads it for Q905, and the Gantt sheet draws its bar lines from it. Two NOTE-level gates hold the grid: Q901 (every cut within one frame of the nearest beat, `qa.snap_ok`; a planned off-grid cut goes in `ALLOW["Q901"]`) and Q905 (one beat that is not a whole number of frames; its fix lists the whole-frame tempos at the build's rate, which are in `formats.md`). At a tempo off that list, a bed placed at beat times in seconds keeps the exact beat while every cut and cue rounds to a frame, up to half a frame away: put the sounds that must meet the picture on frame cues (`frame=frame_of(t, fps)`) and let the bed keep the beat.

Where the 2026-10-28 batch's 37 to 87 ms of SFX lateness came from (measured on the five samples): the mux and the AAC encode add 0.000 ms (the 1024-sample priming is trimmed by the mp4 edit list), the 2.1.0 alimiter delayed every sound by 4.0 ms, and the bulk was placement: slow attacks placed by their first sample (synth.pad's 0.25 s attack reaches -15 dB 44 ms in, a 0.9 s swell 272 ms in). Q903 and `qa.py calib` now hold the mux and the master at 0 ms; Q902 measures the placement (`qa-gates.md`, gate 9).
