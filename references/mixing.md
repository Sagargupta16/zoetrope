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
