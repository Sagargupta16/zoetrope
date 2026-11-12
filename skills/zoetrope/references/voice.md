# Audio intake and voice

Everything here runs locally: numpy and ffmpeg/ffprobe through the pinned Python (no scipy; see `engine.md`), plus a text-to-speech engine through `voice.synthesize`. Nothing is downloaded at render time, and no model is downloaded without the user's yes.

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

The narrator is Kokoro `af_heart` (engine `kokoro-ts`), the default, picked by ear from samples on 2026-10-29; the robotic Windows SAPI voices stay for timing drafts. Always confirm the target length first: music length and voice length both drive the schedule.

## Narration: `voice.synthesize` (offline, one file per part)

```python
import voice as V
N = V.synthesize(lines, folder="narration")  # once, in the build step: the narrator, kokoro-ts af_heart
N = V.synthesize(lines, folder="narration", lexicon={"Kalchar": "Kul char"})  # say a name as respelled
N = V.synthesize(lines, engine="sapi", folder="narration")  # a robotic timing draft
```

Then check what it says before anything is built on it: `qa.py speech narration/narration.json` (Q806, below).

`lines` are strings (ids L01, L02 ...), `{id, text}` or `{id, text, fit}` dicts or `(id, text)` pairs; one voice per call.

- **Per part.** A line is one part, or several when it holds pause markers. Each part is synthesized alone and cached as `narration/<key>.wav`, key = sha256 of the engine, the model id (a hash of every model file the voice reads, or the SAPI voice id and Windows build), the code id (the engine's own code, its SAPI bridge or uv worker program and its package pins), the voice, the speed and the text spoken, as showtime caches per line. Editing one line synthesizes only that line's parts again; an unchanged re-run synthesizes nothing (on three SAPI lines: 0 of 3), so render never needs the engine; an edit to an engine, its pins or its model files synthesizes again. Each new file is checked (speech found, word times inside it) before it is cached; a bad one is deleted and the error names the line and the file. Word times are rebuilt from the engine's raw data at every run, so the trim tunables and the word mapping apply without new audio. Old part files stay when lines change: delete the folder to clear them.
- **Trim and join.** Each part is trimmed to its speech (10 ms windows, a peak above -48 dBFS is speech, 40 ms kept each side: explainroo's numbers, tunables `TRIM_DB`, `TRIM_KEEP`, `TRIM_WIN`) and placed by integer sample counts, never by summed durations. The timeline is `narration/narration.wav` (mono, 44.1 kHz, 16-bit); slots end on whole frames (`fps=`, default 30).
- **Slots** (`voice.slot`, our own rule): `max(0.35 + spoken + 0.7, qa.min_hold(text, profile))`. The speech starts 0.35 s into its slot and 0.7 s follow it, and the slot is never shorter than the reading hold of a caption with the same words (pass the card's hold `profile=`). `rule="showtime"` uses showtime's slot instead: from one line's start to the next line's start, the clip plus a 0.4 s gap, 0.8 s after the last line.
- **Pauses inside a line** (VoiceStudio's marker, our code): `"Wait for it. [pause 600ms] Now."`. `[pause]` alone is 0.35 s, `[pause 300ms]` and `[pause 1.5s]` name their length, up to `PAUSE_MAX` (5 s). The parts are spoken apart and joined with exactly that silence from one part's speech end to the next part's speech start (measured 0.600 s on 2026-11-03). A marker at the start or end of a line, two in a row, or any other bracket tag (`[laughs]`) raises: Kokoro has no reaction tags and would say the word. The line's `text` drops the markers, so captions, holds and word cues never see them.
- **Fit a line to its storyboard time** (VoiceStudio's Smart Fit, our numbers): `{"id": "L04", "text": "...", "fit": 4.0}` gives the line a slot of exactly 4.0 s. Speech that overruns it is spoken again faster, never slower, up to `FIT_FAST` (1.2, our cap, not a measurement: listen to a line near it). A line that would need more raises with the speed it would need and about how many words to cut, and so does a fit under the reading hold of its words. Measured 2026-11-03: a 10-word af_heart line at fit 4.0 went to speed 1.18 in one try; at fit 3.6 it needed 1.34 and raised "cut about 2 of its 10 words". SAPI's speed moves in whole rate steps, so its fit can take a few of the `FIT_ROUNDS` (6).
- **Lexicon** (VoiceStudio's pronunciation dictionary, our code): `lexicon={"Kalchar": "Kul char"}` makes the engine read the respelling, while the line's `text`, its `words[]` and `word_cue("Kalchar")` keep the script's word; a trailing 's is kept ("Kalchar's" is said "Kul char's" and stays one timed word). Keys are one word each, matched as `word_cue` matches. Listen, or run Q806, after a respelling: base.en heard "Kul char's" as "Call Char's" (a NOTE).
- **scenes.py reads, never synthesizes**: `N = V.load_narration("narration/narration.json")`. Render workers import scenes.py once each, and would each run the engine and rewrite narration.wav at the same time. Give each scene its line's `slot["duration"]` and cue reveals with `C.snap(V.word_cue(N, word), FPS)`.
- Mix with `V.duck_mix(bed, V.dec("narration/narration.wav"))` (`mixing.md`).

### narration.json

The shape of showtime's timeline.json. Times are seconds on the narration timeline.

| Key | Meaning |
|---|---|
| `engine`, `model`, `voice`, `lang`, `speed` | What spoke it, the language (`en-us`, `en-gb`, `hi`; Q806 checks English only) and the call's speed |
| `lexicon`, `fit_fast` | The respellings given, and the fit speed cap |
| `sr`, `fps`, `rule`, `profile`, `trim` | 44100; the slots' frame grid; the slot rule; the hold profile; the trim tunables |
| `duration`, `samples`, `file` | Length of `narration.wav` in seconds and samples, and its name |
| `lines[].id`, `text`, `script` | `L01`, `L02` ... (or the ids given), the line without pause markers, and the line as written |
| `lines[].spoken`, `pauses` | Each part as the engine read it (respellings in), and the silence after each part but the last |
| `lines[].speed`, `fit` | The speed it was spoken at (above the call's speed when fit sped it up) and its fit, or null |
| `lines[].start`, `end` | Where the trimmed clip sits (40 ms of margin around the speech) |
| `lines[].speech_start`, `speech_end` | The speech itself, pauses included |
| `lines[].slot` `{start, end, duration}` | The line's time on screen; slots tile the timeline |
| `lines[].parts[]` `{file, clip, start}` | Each part's cached engine file, the samples of it (decoded at 44.1 kHz) placed, and where they start |
| `lines[].timing` | `engine` (every word timed by the engine), `partial` (some times shared out, `est`) or `none` (`words` is empty) |
| `lines[].words[]` `{w, start, end}` | Each script word; `est: true` marks a time shared out between neighbours |

### Word cues

`V.word_cue(N, "square", n=1)` is the start of the n-th "square"; a phrase ("Vatican City") gives its first word. Case, punctuation, curly quotes and accents are ignored; letters and vowel signs of other scripts stay, so a Hindi word is cued by its own spelling (`word_cue(N, "कहानी")`). A missing word raises with the closest words; a word on a line whose engine gives no word times raises naming the line; a time that was shared out rather than heard (`est`, for example the "2026" in SAPI's single token "In 2026") raises unless `est=True`. Snap it before using it: `C.snap(V.word_cue(N, "square"), FPS)`, and trigger a reveal at the start of the word that names it.

SAPI reads numbers, dates and prices as several words and reports each with the text token it read, which can cover two script words ("In 2026", "3:45 pm"); voice.py groups those events back into one time per script word. `V.onset_offsets("narration/narration.json")` lists, for each word after a pause, its start minus the audio onset in ms: near 0 when an engine's word clock is right (SAPI: -10 to +7 ms over 7 words, 2026-10-28). Run it on an engine's first real narration. Kokoro's shift is 70 ms: showtime's 50 ms left af_heart's words a median 22 ms late over 24 words (2026-10-29), and at 70 ms they read +2 ms (p10 -31, p90 +51). The spread is the check itself: it waits for voicing, so a soft p, f or th reads early and a vowel start reads late. Hindi (hf_alpha, 6 words, 2026-11-03) read 8 to 54 ms late with the same 70 ms: the shift was set on English, so give a Hindi cue a frame of slack.

### What the narration says: Q806 and Q807 (`qa_speech.py`)

The reviewer cannot hear, so a speech model writes down what each line says: faster-whisper with the `base.en` model (147.8 MB, MIT, offline on the CPU, in its own uv environment; `python engine/qa_speech.py fetch`). Q806 holds each line of `narration.wav` against its text: a missing, added or changed word is a FIX, a word close in letters a NOTE (the voice or the model may be wrong: listen), a narration that is not English a NOTE (base.en hears English only). Q807 finds `narration.wav` in the finished file's sound and holds what the file says against what the stem says: a word the music loses is a NOTE, a file that does not carry the stem a FIX. Digits and the words for them compare equal ($99, 20%, 2026 as "twenty twenty six", 3:45, 21st, 1990s), so do joined and hyphenated spellings, British and American spellings, a lone letter and its sound ("R" for "are") and common homophones (two, to, too). Rows, numbers and calibration are in `qa-gates.md`.

### Engines

One engine per job (VoiceStudio's engine-acceptance rule, adopted 2026-11-03): an engine stays only while it holds a job nothing else does and has been run here. The sherpa-onnx Kokoro build and Piper held none and were never run, so 2.3.0 removed them.

| Engine | Job | Status | Word times | Download (the user's yes first) | Licence |
|---|---|---|---|---|---|
| `sapi` | timing drafts and plumbing, with nothing to download | tested 2026-10-28 on Windows 11 | SAPI's word events: starts within 10 ms of the onset after pauses; ends from the audio | none (the Windows David and Zira desktop voices) | part of Windows |
| `kokoro-ts` | the narrator, and every voice a piece needs | tested on Windows 11: af_heart, af_bella, am_michael, bf_emma (2026-10-29), every `am_`, `bm_` and `h` voice (2026-11-03); af_heart is the narrator | per-phoneme durations, moved 70 ms earlier | kokoro-onnx 0.6.1 in a side Python 3.13 env, about 40 MB of wheels; `onnx/model.onnx` 325.5 MB (or `model_fp16.onnx` 163.2 MB) and `voices/<name>.bin`, 0.5 MB each, from `onnx-community/Kokoro-82M-v1.0-ONNX-timestamped` at commit `dd4401a9`. Downloaded: the fp32 model and af_heart, af_bella, am_michael, bf_emma (2026-10-29); am_adam, am_echo, am_eric, am_fenrir, am_liam, am_onyx, am_puck, am_santa, bm_daniel, bm_fable, bm_george, bm_lewis, hf_alpha, hf_beta, hm_omega, hm_psi (2026-11-03), each checked against the size and sha256 Hugging Face lists | MIT code, Apache-2.0 weights; phonemizer and espeak-ng GPL-3.0 |

- `sapi` is a timing and plumbing fallback, not a quality option: it sounds robotic. It writes 16 kHz on purpose: at the default 22.05 kHz SAPI's word clock ran 1.378x fast. Its speed is SAPI's integer rate, so 0.95 to 1.05 all map to the normal rate.
- `kokoro-ts`: kokoro-onnx 0.6.1 declares Python below 3.14, so it runs in a side 3.13 environment; voice.py points it at the export's `durations` output, prefers the fp32 model and stops on NaN audio from the fp16 one. A voice's first letter picks the language its words are phonemized in (`KOKORO_LANGS`: a American English, b British English, h Hindi); a voice of another language raises until it is wired and tested.
- Model files live outside the repo in `~/.cache/zoetrope/voices/<engine folder>` (`ZOETROPE_VOICES` moves them), the speech model in `~/.cache/zoetrope/asr` (`ZOETROPE_ASR`). Packages never go into requirements.txt: each job runs in its own uv environment with the pins in `engine/requirements-voice.in`, which setup.sh does not install.
- Pick by listening: `python voice_samples.py [out_folder]` renders the same three lines with every ready engine and voice into `narration_samples/<engine>/<voice>/narration.wav` (a Hindi voice reads three Hindi lines), prints what each missing engine needs, and reports a failing voice while the others still render. The 2026-11-03 run: 22 samples, 0 failed, word times on every line, in `outputs/voice-samples-2026-11-03/`.

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

Voice lists do not rank voices by tone, so pick by audition, not by assumption: `voice_samples.py` renders the same lines with every ready voice (or generate a 1-line test per candidate, 2 or 3). For a two-host chat pick one male and one female voice so listeners can tell them apart. A slow voice works for a deliberate, spaced style (a 92 s mobiles-deals video ran a slow voice at 1.04x). Record the chosen voice ids in the plan. The narrator, af_heart, read the three sample lines at 3.19 words a second (af_bella 3.03, bf_emma 3.19, am_michael 2.83). A second voice is not picked yet: the 2026-11-03 samples hold every English male voice (nine American, four British) and the four Hindi ones for the user to hear. On those samples Q806 heard am_santa and bm_george say "Shrink" as "Drink" (a NOTE): listen to those two on words that start with shr.

### Script-writing rules for the ear

- Short sentences: about 8 to 14 words. One idea per sentence.
- Numbers spoken as words in the script: "ninety nine dollars", "twenty percent off", "one point five", so a caption made from the line says what the voice says.
- No symbols (%, $, &, /, #, arrows, emoji) and no abbreviations the voice may misread (spell out "versus", "per").
- Brand and product names: write as {brand}, {product} in plans; when the voice says one wrong, respell it in `lexicon=` (the script keeps the real spelling) and run Q806 again.
- Put commas and full stops where a breath is wanted, and `[pause 400ms]` where a beat of silence is; avoid long parentheses.
- Budget by the measured pace of the chosen voice, not by word count rules of thumb. Generate, measure, then size the scenes.
- One idea per line, and read it aloud once: if you run out of breath or trip, rewrite it. The slot grows with the speech, so long sentences make long scenes.
- Put the word that carries the moment (the number, the name, "now") where the voice can land on it, best after a short pause, so `word_cue` has a clean onset to hit. A word that must hit a beat exactly: cue a word the voice says on its own after a pause, and look for its onset in the spectrogram of `review/audio.png`.
- Never put an ellipsis on a line by itself: SAPI wrote silence for "..." (a finding of the public clean-room reference, not re-run on this engine), which fails the trim check. Use `[pause 400ms]` for a beat of silence.
- Keep the caption and the spoken line the same words when both appear, so the reading hold and the voice agree; a caption is on screen before its first word is heard.
- Leave the bed room: the music ducks 8 dB under speech, so a busy bed under a dense line still competes with it.

### Voice helpers

`voice.dec(path)` decodes any file to float32 mono at 44.1 kHz through ffmpeg run with `-nostdin`; `voice.span(y)` returns the speech start and end (10 ms RMS windows within 40 dB of the loudest); `voice.trim(y)` the trim bounds in samples; `voice.slot(line, rule, last, profile)` one slot. `voice.word_cue(narration, word, n=1, est=False)` finds the n-th time the word is spoken in line order. `voice.section_beats(speech_len, bpm, hold=0.5, lead=0.06, tempo=1.04, min_beats=2)` sizes a voiced section on the beat grid for a piece led by music: lead, plus `speech_len / tempo`, plus hold, rounded up to a whole number of beat pairs and at least `min_beats` (at 120 BPM: 6 beats for 2.3 s of speech, 2 beats for 0.4 s, from the clean-room page). `voice.synthesize` is run once, from the working folder, before the proof; scenes.py only reads `narration.json`. Q902 measures sound effects, not words: a word cue is only as good as the engine's word clock (above).
