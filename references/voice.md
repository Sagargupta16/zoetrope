# Audio intake and voice

Everything here runs locally: numpy and ffmpeg/ffprobe through the pinned Python (no scipy; see `engine.md`), plus a text-to-speech engine for voice once one is set up. Nothing is downloaded at render time.

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

Always confirm the target length first: music length and voice length both drive the schedule.

## Voice with a text-to-speech engine

No engine is wired up yet: until one is chosen, videos are music plus captions. Whatever engine is used, the steps are the same.

### Steps

1. List the engine's voices and audition 2 or 3 (below) before writing the speakers list.
2. Generate one file per section (one hook line, one feature line, and so on) into the working folder, for example `vo/L01.wav`: each file's length can then be measured and the section sized to it. One long file gives one blob whose internal timings we cannot place cuts against without extra analysis.
3. For a two-voice chat, one file with alternating lines is fine; measure the whole file and split by silence if cuts must follow lines.
4. Measure with ffprobe (below), then build the schedule.

Rules and pitfalls (seen with an earlier engine):
- Speed differs a lot between voices. Generate each line, measure its real duration, and time sections from that; never guess.
- A service may answer a bad request with an error payload instead of raising: check for it before using the file.
- A signed download link may expire within an hour: save the file to the working folder as soon as it is ready.

### Measure duration

```
ffprobe -v error -show_entries format=duration -of csv=p=0 vo/L01.mp3
```

Measure the speech itself (leading and trailing silence trimmed) for tight cuts: decode to float, take 10 ms RMS windows, and keep windows within 40 dB of the loudest one; first and last such window = speech start and end.

`voice.dec(path)` decodes any file to float and `voice.span(y)` returns the speech start and end in seconds (both in `engine/voice.py`, 44.1 kHz).

### Voice picks by tone

Voice lists do not rank voices by tone, so pick by audition, not by assumption: filter the engine's voices to the language and generate a 1-line test per candidate (2 or 3). For a two-host chat pick one male and one female voice so listeners can tell them apart. A slow voice works for a deliberate, spaced style (a 92 s mobiles-deals video ran a slow voice at 1.04x). Record the chosen voice ids in the plan.

### Script-writing rules for the ear

- Short sentences: about 8 to 14 words. One idea per sentence.
- Numbers spoken as words in the script: "ninety nine dollars", "twenty percent off", "one point five".
- No symbols (%, $, &, /, #, arrows, emoji) and no abbreviations the voice may misread (spell out "versus", "per").
- Brand and product names: write as {brand}, {product} in plans; in the final script spell phonetically if the voice mispronounces it (test one line).
- Put commas and full stops where a breath is wanted; avoid long parentheses.
- Budget by the measured pace of the chosen voice, not by word count rules of thumb. Generate, measure, then size the scenes.
