# Mixing and mastering

### Voice placement from a schedule

`voice.synthesize` lays narrated lines out itself (the slot rule in `voice.md`: 0.35 s before the speech, 0.7 s after it, never under the reading hold, slots on whole frames) and writes `narration/narration.wav`; give each scene its line's slot. The section math below is for music-led pieces sized in beats, or a voice file from elsewhere.

Compute every section length from the real speech length, in beats:

```
need  = LEAD + speech_len / TEMPO + hold        # LEAD 0.06 s, TEMPO 1.04, hold 0.35 to 0.9 s (1.6 s on a long fill)
beats = max(min_beats, 2*ceil(need / B / 2))    # whole, even number of beats
```

`voice.section_beats(speech_len, bpm, hold)` computes `beats`. Then pad the sum so hard-cut sections start on a bar line (multiples of 4 beats). Start each voice file at `section_start*B + LEAD - 0.02` after trimming its leading silence (`atrim=start=speech_start-0.02`). Keep the section lengths in `TIMELINE` (in beats, `bpm=BPM`); `scenes.py` and the audio build both read it.

Voice speed: keep within 0.95 to 1.05x using ffmpeg `atempo` (a single atempo accepts 0.5 to 2.0):

```
ffmpeg -v error -y -i vo/L01.mp3 -af "highpass=f=90,atrim=start=0.05,atempo=1.04" -ar 48000 vo/L01_t.wav
```

### Duck and mix (numpy)

`voice.duck_mix(bed, voice)` in `engine/voice.py` does this: voice peak 0.89, a -38 dB voice gate on 10 ms windows, fast attack (about 40 ms) and slow release (about 300 ms), the bed set to about -18 dBFS RMS before ducking, music ducked 8 dB while the voice speaks, and the voice lifted about 2 dB (x1.26).

The music-only version skips the duck and uses the sidechain-on-kick helper `duck()` in `engine/synth.py` (3 to 6 dB, release about 0.12 s).

Stacks: one sound per visible event. `qa.py check` notes heavy sounds (kick, hit, boom, impact, drop) within 3 frames of each other, anything else on a payoff cue, and more than 2 sounds in any 100 ms (Q804). A riser or whoosh that lands on its heavy sound is one gesture with it, and the bed's own kick under a cut hit is not a stack: the template leaves out any kick within 3 frames of a cut, so the hit carries that beat.

### Loudness: -14 LUFS integrated, true peak <= -1 dBTP

`audio.master(src, dst)` does the whole master in one call (`run_all.py` runs it on `mix_raw.wav` into `mix.wav`):

1. Decode src to float, 48 kHz stereo, and measure it with ffmpeg ebur128 (the meter `qa.loud` reads; `audio.measure` takes its values at 3 decimals from the filter's metadata).
2. Apply one static gain to -14 LUFS.
3. Limit the true peak to the ceiling, default -2.0 dBTP (`audio.CEILING`): 4x oversampled (a 129-tap Kaiser-windowed sinc, so phase 0 is the samples themselves), 3 ms lookahead, 100 ms release, and no delay added. Our true peak agrees with ffmpeg's to 0.006 dB on 18 signals, EBU Tech 3341 signals 15 to 19 included (2026-10-28).
4. Measure again and nudge the gain until it is within 0.05 LU, at most 6 passes; write 16-bit stereo 48 kHz.

It returns I, LRA, the true peak measured on dst, the gain, the passes, how deep and when the limiter cut, and its Q805 row. Q805 is a FIX when the master missed -14 by over 0.1 LU or the ceiling by over 0.05 dB, or when it could not stay linear: the limiter took over 0.5 LU of loudness or over 6 dB at one moment. Then lower the hits at the time it names in the raw mix, not the ceiling (on the five approved samples the limiter took 0.00 to 0.02 LU and at most 1.5 dB; the 2.1.0 template bed took 1.43 LU, 6.2 dB). The template and five sample mixes land within 0.05 LU of -14 at or under -2.0 dBTP in 1 or 2 passes.

Why -2.0: the AAC encode raises the true peak. Over 9 mixes it added up to 1.23 dB at 192k and at most 0.45 dB at 320k (2026-10-28), so the mux encodes AAC at 320k (`contract.AAC_ARGS`) and -2.0 keeps 0.55 dB under the -1 dBTP gate. `run_all.py` then measures the decoded mp4; while it reads over -1.3 dBTP (the gate less the 0.3 dB EBU R128 meter tolerance) it re-masters at most 3 times, each ceiling min(ceiling, the mix's own true peak) minus (excess + 0.2 dB) over the measured slope, and stops when the peak does not follow the ceiling. It keeps the cleanest master (Q805 clean, file inside -1 dBTP), so a lower ceiling that fails Q805 never turns a passing file into a reject. One line per master goes into the delivery report.

This replaced 2.1.0's alimiter plus two-pass loudnorm. That chain went dynamic on the template and on the Nook sample (missing -14 by up to 0.7 LU) and delayed the whole mix by 4.0 ms (alimiter attack 4 ms, latency off; measured 2026-10-28); Q903 against `mix_raw.wav` and `qa.py calib` read the master's delay and must show 0 ms.

Verify with ebur128 (look at `I:` and `Peak:` in the Summary), or `qa.loud(path)`:
```
ffmpeg -nostdin -hide_banner -i out.mp4 -af ebur128=peak=true -f null - 2>&1 | grep -A16 Summary
```
Report I and true peak in the delivery line (the DELIVERED line carries both); LRA is in `qa.loud` and on `review/audio.png`.

### Levels, stacks and the master in detail

- **Levels.** The master brings the mix to -14 LUFS whatever its level, so a bus's absolute gain does not decide loudness: it decides the balance and how hard the limiter must work on the peaks, which Q805 judges. The template's gains are in `music.md`; each style card gives its own. A whoosh at 0.4 instead of 0.2 over a quiet bed failed Q805 on the clean-room template (2026-11-01): the limiter took 0.90 LU, at most 2.8 dB, at the second whoosh's apex. Q805's fix names the moment to lower.
- **One sound per moment (Q804, `qa_stack.stack_rows`, a NOTE).** It counts the SFX-bus rows of the cue sheet and the music-bus rows that carry a label; unlabelled bed rows and rows at a gain of 0 or less are left out. It notes two heavy sounds (the sheet's `heavy` flag) within 3 frames; two or more sounds on a `payoff=True` cue (those within 3 frames of it, and a lead-in still sounding 0.1 s before it); and more than 2 sounds in any 100 ms (a taste rule). A lead-in (a name that holds riser, swell, suck, reverse or whoosh) whose landmark or end falls within 3 frames or 100 ms, whichever is longer, of a heavy sound is one gesture with it and is not counted. A designed stack goes in `ALLOW["Q804"]`.
- **When the peak is over (Q802).** A FIX names every sheet sound sounding within 50 ms of the loudest moment, the bed and SFX levels there, and the order to cut the designed sounds: impact (impact, hit, boom, kick, slam, thud, crash), then chime or bell, then press or drop (`qa_stack.CUT_ORDER`, a house heuristic).
- **Pumping.** `synth.duck(bus, times, ...)` dips a whole bus under a list of times; `synth.build` ducks its music 3 dB under each kick. Keep it on the music bus.
- **Under narration.** `voice.duck_mix(bed, voice, sr=SR, depth_db=8)` pads both to the longer one, sets the bed to -18 dBFS RMS over the whole bed, pulls it down depth_db while the voice speaks and lays the voice on top at a peak of 0.89, times 1.26. The voice peaks above 1.0 afterwards, so the sum goes through a shared `write_wav` scale like any mix (2026-11-01 probe: voice peak 1.121, sum 1.196). `audio.bed(..., voice_spans=[(a, b), ...])` steps the template's music bus down 8 dB (times 0.398) inside each span with no ramp and leaves the SFX bus alone. The voice goes into `mix_raw.wav`, never into `sfx.wav`: Q902 searches `sfx.wav` for each cue's own sound, and speech there would bury it.
- **Master return and edge cases.** `audio.master(src, dst, ff="ffmpeg", I=-14, TP=CEILING, passes=6, tol=0.05)` returns `I`, `LRA`, `tp` (measured on `dst`), `gain_db`, `passes`, `ceiling`, `limit_db` (deepest gain reduction), `limit_t`, `limited_s` (seconds under more than 1 dB of it), `cost_db`, `input` (the source measured) and `rows` (its one Q805 row). A mix under -60 LUFS is written out as it is, with a Q805 FIX that calls it silent. `audio.tp_limit(mix, ceiling_db, sr=SR_MASTER, look=0.003, release=0.1)` is the same limiter for a buffer of your own; it returns the limited mix and the gain per sample.
- **After the encode.** `run_all.master_and_mux` re-masters while the muxed file's true peak is over -1.3 dBTP (`TP_MAX` -1.0 less `TP_TOL` 0.3), at most `RETRIES` (3) times, and stops early when the peak does not follow the ceiling (a slope under 0.1). The slope is held between 0.25 and 1. It then keeps the clean try (Q805 clean and the file inside -1 dBTP) with the lowest peak, else the try with the lowest peak, and masters and muxes again if that was not the last. If the peak is still over -1 it prints `true peak still over -1 dBTP after N re-masters: lower the hits Q802 names`.

The gates on the finished file, besides Q805 (which comes from the build's master; `qa.py check` alone does not make it):

| Code | Checks |
|---|---|
| Q801 | integrated loudness within -14 +/- 1 LUFS (`qa.loud`) |
| Q802 | true peak at or under -1 dBTP, read channel by channel |
| Q903 | audio and video streams start together; the decoded audio lines up with `mix.wav` and `mix_raw.wav` within 1 ms |

`python qa.py calib` sends one white frame and a one-frame 1 kHz blip through `audio.master` and the mux and reads both back (Q906); the blip must land +0.00 ms from the white frame.

To make and master the sound without drawing a frame (the builder does this at the proof, so the reviewer can read the sound), run from the working folder with `--size` matching the build:

```
python -c "import run_all, audio, contract as C; audio.render_audio(run_all.scenes); m = audio.master(C.MIX_RAW, C.MIX); print(C.line(m['rows'][0]))" --size 1920x1080
```

With a score of your own, call it in place of `audio.render_audio`. For a change to the sound alone, `python run_all.py audio --size WxH` makes, masters and checks the sound again on the same `video.mp4`.

### What no gate hears

The gates measure loudness, peaks, the limiter's work, the timing of the sheet's cue sounds, stacks and the mux. Nobody listens, and none of this is checked:

- whether the music is good: key and harmony, notes that clash with a pluck or a chord, a grating timbre, a sound that does not suit its picture;
- the balance of bed, effects and voice beyond what the limiter reports, and whether narration stays clear over the bed (Q806 and Q807 check the words, not the balance);
- a gap shorter than a second, since Q803 averages whole seconds: a mix can fall to -111 dBFS RMS for 180 ms (clean-room scratch score, 2026-11-01) while its quietest whole second reads -26 dBFS and Q803 passes;
- the timing of anything not in CUES, and the bed's own beats against the picture: Q901 holds the cuts to the grid, not the sounds;
- stereo: every mix is the same mono in both channels (`audio.write_wav`);
- whether the last sound ends with the film: the mux cuts the longer stream to the shorter (`-shortest`).

The reviewer cannot hear either. `python qa.py audiostrip mix.wav --scenes .` (at the proof) or `python qa.py audiostrip out.mp4 --scenes .` (after the render) draws the sound on one time axis into `review/audio.png`, 1600 px wide: the scenes, a log-frequency spectrogram, one tick per cue coloured by its measured offset, momentary and short-term loudness with the integrated level, the true peak per 100 ms with every frame over -1 dBTP in red, and the numbered cells of the key sheet. A gap shows as a dark column no row names. It exits 2 on a file with no audio stream, and 0 when the piece declares `SILENT`.

### Silent pieces

A piece with no sound on purpose says `SILENT = True` in `scenes.py` (or `--silent` on `qa.py check`). `run_all.deliver` then makes no score and no master and muxes the picture alone (`contract.mux_cmd` with no mix). Q706, Q801, Q803, Q805 and Q903 give no rows, Q802 and Q804 pass with `no audio by design (SILENT)`, Q902 measures only the picture side of each cue, and a size budget counts no audio bitrate (`run_all.caps`). Declare it only when the storyboard has no sound; it is not a way to quiet a fault.

### Narrated pieces

A voiced piece runs `voice.synthesize` once before the proof and takes each scene's length from its line's slot (`voice.md`). `render_audio` takes no voice, so a voiced piece has a `score.py` of its own: it decodes `narration/narration.wav` with `voice.dec`, ducks the bed under it, adds it into `mix_raw.wav` and keeps it out of `sfx.wav` (`engine.md`). `audio.write_wav(path, mono, voice=v, scale=...)` adds the voice as it writes and keeps the mix's length, so a longer voice is cut at the end of the mix. A sound on a spoken word goes on the frame of `C.snap(voice.word_cue(N, word), FPS)`, as a frame cue that carries the word's CUES label.
