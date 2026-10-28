# Mixing and mastering

### Voice placement from a schedule

Compute every section length from the real speech length, in beats:

```
need  = LEAD + speech_len / TEMPO + hold        # LEAD 0.06 s, TEMPO 1.04, hold 0.35 to 0.9 s (1.6 s on a long fill)
beats = max(min_beats, 2*ceil(need / B / 2))    # whole, even number of beats
```

`voice.section_beats(speech_len, bpm, hold)` computes `beats`. Then pad the sum so hard-cut sections start on a bar line (multiples of 4 beats). Start each voice file at `section_start*B + LEAD - 0.02` after trimming its leading silence (`atrim=start=speech_start-0.02`). Store `SCHEDULE` (section starts/ends in seconds) in one JSON; `scenes.py` and the audio build both read it.

Voice speed: keep within 0.95 to 1.05x using ffmpeg `atempo` (a single atempo accepts 0.5 to 2.0):

```
ffmpeg -v error -y -i vo/L01.mp3 -af "highpass=f=90,atrim=start=0.05,atempo=1.04" -ar 48000 vo/L01_t.wav
```

### Duck and mix (numpy)

`voice.duck_mix(bed, voice)` in `engine/voice.py` does this: voice peak 0.89, a -38 dB voice gate on 10 ms windows, fast attack (about 40 ms) and slow release (about 300 ms), the bed set to about -18 dBFS RMS before ducking, music ducked 8 dB while the voice speaks, and the voice lifted about 2 dB (x1.26).

The music-only version skips the duck and uses the sidechain-on-kick helper `duck()` in `engine/synth.py` (3 to 6 dB, release about 0.12 s).

### Loudness: -14 LUFS integrated, true peak <= -1 dBTP

Peak-limit first (stops the limiter-less overshoot), then loudnorm two-pass with linear=true. We target TP=-3.0: the AAC encode adds 1 to 1.5 dB of true peak, so -1.5 in the WAV landed at -0.4 in the MP4 (measured 2026-10-28). `audio.master(src, dst)` runs passes 0 to 2 below in one call; the commands are here for reference.

Pass 0 (limit): `ffmpeg -nostdin -v error -y -i mix_pre.wav -af "alimiter=limit=0.75:attack=4:release=60:level=false" -ar 48000 mix_lim.wav`

Pass 1 (measure):
```
ffmpeg -nostdin -hide_banner -i mix_lim.wav -af loudnorm=I=-14:TP=-3.0:LRA=11:print_format=json -f null - 2>&1
```
Read `input_i`, `input_tp`, `input_lra`, `input_thresh`, `target_offset` from the JSON block.

Pass 2 (apply):
```
ffmpeg -nostdin -v error -y -i mix_lim.wav -af "loudnorm=I=-14:TP=-3.0:LRA=11:measured_I=<input_i>:measured_TP=<input_tp>:measured_LRA=<input_lra>:measured_thresh=<input_thresh>:offset=<target_offset>:linear=true" -ar 48000 final.wav
```

Verify with ebur128 (look at `I:` and `Peak:` in the Summary):
```
ffmpeg -nostdin -hide_banner -i final.wav -af ebur128=peak=true -f null - 2>&1 | grep -A16 Summary
```
loudnorm's gate differs slightly from EBU R128, so `I:` may read a little off -14. Past builds trimmed the residual: `TRIM = -14.0 - I`, then `ffmpeg -i final.wav -af "volume=${TRIM}dB" final_trim.wav` and re-measured. Re-check that the peak is still <= -1 dBTP after trim. Report I, LRA and true peak in the delivery line.
