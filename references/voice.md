# Audio intake and voice

Everything here runs locally: numpy and ffmpeg/ffprobe through the pinned Python (no scipy; see `engine.md`), plus a text-to-speech engine through `voice.synthesize`. Nothing is downloaded at render time, and no model is downloaded without Sagar's yes.

## Audio intake: how to ask

Ask one short question, then lock the answer into the plan before any build:

1. "What should the audio be?" Options: (a) music only, (b) one voice narrator over music, (c) podcast-style, two voices talking, over light music.
2. If voice: "Do you have a script, or should we write it?" and "Which tone: warm, energetic, calm, or conversational?"
3. If music: "Which mood?" (offer the presets in `music.md`) and "Any hard sync moments (logo reveal, price drop)?"

Defaults when the user says "you choose" (our suggestions, state them out loud):

| Style family | Audio default |
|---|---|
| Product promo / ad | Voice narrator + tech pulse 120 BPM bed, SFX on every cut |
| Explainer / how-to | Voice narrator + ambient 70 or lo-fi 84 bed, few SFX |
| Cinematic / brand film | Music only or sparse voice, cinematic swell 80 |
| Social / retro / game | Music only, chiptune 140 or upbeat pop 112 |
| Interview / chat explainer | Two voices (host A, host B) + very quiet ambient bed |

The narrator is Kokoro `af_heart` (engine `kokoro-ts`), Sagar's pick from samples on 2026-10-29; the robotic Windows SAPI voices stay for timing drafts. Always confirm the target length first: music length and voice length both drive the schedule.

## Narration: `voice.synthesize` (offline, one file per line)

```python
import voice as V
N = V.synthesize(lines, folder="narration")  # once, in the build step: the narrator, kokoro-ts af_heart
N = V.synthesize(lines, engine="sapi", folder="narration")  # a robotic timing draft
```

`lines` are strings (ids L01, L02 ...), `{id, text}` dicts or `(id, text)` pairs; one voice per call.

- **Per line.** Each line is synthesized alone and cached as `narration/<key>.wav`, key = sha256 of the engine, the model id (a hash of every model file the voice reads, or the SAPI voice id and Windows build), the code id (the engine's own code, its SAPI bridge or uv worker program and its package pins), the voice, the speed and the text, as showtime caches. Editing one line synthesizes only that line again; an unchanged re-run synthesizes nothing (on three SAPI lines: 0 of 3), so render never needs the engine; an edit to an engine, its pins or its model files synthesizes again. Each new file is checked (speech found, word times inside it) before it is cached; a bad one is deleted and the error names the line and the file. Word times are rebuilt from the engine's raw data at every run, so the trim tunables and the word mapping apply without new audio. Old line files stay when lines change: delete the folder to clear them.
- **Trim and join.** Each line is trimmed to its speech (10 ms windows, a peak above -48 dBFS is speech, 40 ms kept each side: explainroo's numbers, tunables `TRIM_DB`, `TRIM_KEEP`, `TRIM_WIN`) and placed in its slot by integer sample counts, never by summed durations. The timeline is `narration/narration.wav` (mono, 44.1 kHz, 16-bit); slots end on whole frames (`fps=`, default 30).
- **Slots** (`voice.slot`, our own rule): `max(0.35 + spoken + 0.7, qa.min_hold(text, profile))`. The speech starts 0.35 s into its slot and 0.7 s follow it, and the slot is never shorter than the reading hold of a caption with the same words (pass the card's hold `profile=`). `rule="showtime"` uses showtime's slot instead: from one line's start to the next line's start, the clip plus a 0.4 s gap, 0.8 s after the last line.
- **scenes.py reads, never synthesizes**: `N = V.load_narration("narration/narration.json")`. Render workers import scenes.py once each, and would each run the engine and rewrite narration.wav at the same time. Give each scene its line's `slot["duration"]` and cue reveals with `C.snap(V.word_cue(N, word), FPS)`.
- Mix with `V.duck_mix(bed, V.dec("narration/narration.wav"))` (`mixing.md`).

### narration.json

The shape of showtime's timeline.json. Times are seconds on the narration timeline.

| Key | Meaning |
|---|---|
| `engine`, `model`, `voice`, `speed` | What spoke it |
| `sr`, `fps`, `rule`, `profile`, `trim` | 44100; the slots' frame grid; the slot rule; the hold profile; the trim tunables |
| `duration`, `samples`, `file` | Length of `narration.wav` in seconds and samples, and its name |
| `lines[].id`, `text` | `L01`, `L02` ... (or the ids given) and the line as written |
| `lines[].start`, `end` | Where the trimmed clip sits (40 ms of margin around the speech) |
| `lines[].speech_start`, `speech_end` | The speech itself |
| `lines[].slot` `{start, end, duration}` | The line's time on screen; slots tile the timeline |
| `lines[].file`, `clip` | The cached engine file and the samples of it (decoded at 44.1 kHz) placed at `start` |
| `lines[].timing` | `engine` (every word timed by the engine), `partial` (some times shared out, `est`) or `none` (`words` is empty) |
| `lines[].words[]` `{w, start, end}` | Each spoken word; `est: true` marks a time shared out between neighbours |

### Word cues

`V.word_cue(N, "square", n=1)` is the start of the n-th "square"; a phrase ("Vatican City") gives its first word. Case, punctuation, curly quotes and accents are ignored. A missing word raises with the closest words; a word on a line whose engine gives no word times raises naming the line; a time that was shared out rather than heard (`est`, for example the "2026" in SAPI's single token "In 2026") raises unless `est=True`. Snap it before using it: `C.snap(V.word_cue(N, "square"), FPS)`, and trigger a reveal at the start of the word that names it.

SAPI reads numbers, dates and prices as several words and reports each with the text token it read, which can cover two script words ("In 2026", "3:45 pm"); voice.py groups those events back into one time per script word. `V.onset_offsets("narration/narration.json")` lists, for each word after a pause, its start minus the audio onset in ms: near 0 when an engine's word clock is right (SAPI: -10 to +7 ms over 7 words, 2026-10-28). Run it on an engine's first real narration. Kokoro's shift is 70 ms: showtime's 50 ms left af_heart's words a median 22 ms late over 24 words (2026-10-29), and at 70 ms they read +2 ms (p10 -31, p90 +51). The spread is the check itself: it waits for voicing, so a soft p, f or th reads early and a vowel start reads late.

### Engines

| Engine | Status | Word times | Download (Sagar's yes first) | Licence |
|---|---|---|---|---|
| `sapi` | tested 2026-10-28 on Windows 11, as a timing and plumbing fallback only | SAPI's word events: starts within 10 ms of the onset after pauses; ends from the audio | none (the Windows David and Zira desktop voices) | part of Windows |
| `kokoro` | UNTESTED | none | sherpa-onnx 2.0.1, about 19 MB of wheels; `kokoro-int8-multi-lang-v1_0.tar.bz2`, 132 MB | Apache-2.0 (code and weights) |
| `kokoro-ts` | tested 2026-10-29 on Windows 11 (af_heart, af_bella, am_michael, bf_emma); af_heart is the narrator | per-phoneme durations, moved 70 ms earlier | kokoro-onnx 0.6.1 in a side Python 3.13 env, about 40 MB of wheels; `onnx/model.onnx` 325.5 MB (or `model_fp16.onnx` 163.2 MB) and `voices/<name>.bin`, 0.5 MB each. Downloaded 2026-10-29 from `onnx-community/Kokoro-82M-v1.0-ONNX-timestamped` at commit `dd4401a9`: the fp32 model and the four voices above, sha256 checked | MIT code, Apache-2.0 weights; phonemizer and espeak-ng GPL-3.0 |
| `piper` | UNTESTED | none | piper-tts 1.8.0, about 65 MB of wheels; a voice, 63 to 114 MB | GPL-3.0-or-later; voices: ljspeech, john, kristin, norman public domain, lessac Blizzard 2013 |

- `sapi` is a timing and plumbing fallback, not a quality option: it sounds robotic. It writes 16 kHz on purpose: at the default 22.05 kHz SAPI's word clock ran 1.378x fast. Its speed is SAPI's integer rate, so 0.95 to 1.05 all map to the normal rate.
- `kokoro` and `piper` are written to their APIs and their plumbing ran on fake models; they stay untested until Sagar approves their downloads, and `synthesize` prints when an untested engine speaks. Each needs a named voice; `kokoro-ts` defaults to the narrator, af_heart.
- `kokoro` (sherpa-onnx 2.0) has no espeak-ng fallback: a word missing from its lexicon is skipped without a sound, so synthesize refuses such lines first and lists the words. Write numbers as words, spell names as they sound, or add the word to the lexicon file.
- `kokoro-ts`: kokoro-onnx 0.6.1 declares Python below 3.14, so it runs in a side 3.13 environment; voice.py points it at the export's `durations` output, prefers the fp32 model and stops on NaN audio from the fp16 one.
- Model files live outside the repo in `%USERPROFILE%\.cache\zoetrope\voices\<engine folder>` (`ZOETROPE_VOICES` moves them). Packages never go into requirements.txt: each engine runs in its own uv environment with the pins in `engine/requirements-voice.in`, which setup.sh does not install.
- Pick by listening: `python voice_samples.py [out_folder]` renders the same three lines with every ready engine and voice into `narration_samples/<engine>/<voice>/narration.wav`, prints what each missing engine needs, and reports a failing voice while the others still render.

### Measure duration

For a voice file from elsewhere (the user's own, or an engine not wired in):

```
ffprobe -v error -show_entries format=duration -of csv=p=0 vo/L01.mp3
```

Measure the speech itself (leading and trailing silence trimmed) for tight cuts: decode to float, take 10 ms RMS windows, and keep windows within 40 dB of the loudest one; first and last such window = speech start and end.

`voice.dec(path)` decodes any file to float (it passes `-nostdin`: a "q" waiting on stdin once cut an 1800 s decode to 157 s with exit code 0) and `voice.span(y)` returns the speech start and end in seconds (both in `engine/voice.py`, 44.1 kHz).

Rules and pitfalls with any engine:
- Speed differs a lot between voices. Generate each line, measure its real duration, and time sections from that; never guess.
- A service may answer a bad request with an error payload instead of raising: check for it before using the file.
- A signed download link may expire within an hour: save the file to the working folder as soon as it is ready.

### Voice picks by tone

Voice lists do not rank voices by tone, so pick by audition, not by assumption: `voice_samples.py` renders the same lines with every ready voice (or generate a 1-line test per candidate, 2 or 3). For a two-host chat pick one male and one female voice so listeners can tell them apart. A slow voice works for a deliberate, spaced style (a 92 s mobiles-deals video ran a slow voice at 1.04x). Record the chosen voice ids in the plan. The narrator, af_heart, read the three sample lines at 3.19 words a second (af_bella 3.03, bf_emma 3.19, am_michael 2.83).

### Script-writing rules for the ear

- Short sentences: about 8 to 14 words. One idea per sentence.
- Numbers spoken as words in the script: "ninety nine dollars", "twenty percent off", "one point five" (the kokoro engine refuses digits it has no word for).
- No symbols (%, $, &, /, #, arrows, emoji) and no abbreviations the voice may misread (spell out "versus", "per").
- Brand and product names: write as {brand}, {product} in plans; in the final script spell phonetically if the voice mispronounces it (test one line).
- Put commas and full stops where a breath is wanted; avoid long parentheses.
- Budget by the measured pace of the chosen voice, not by word count rules of thumb. Generate, measure, then size the scenes.
