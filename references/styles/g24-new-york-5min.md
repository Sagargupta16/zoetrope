# S-g24-new-york-5min · Narrated city tour over footage
**Source:** @LinearUncle, https://x.com/LinearUncle/status/2103705625075331442 · our build: g24-new-york-5min
**Use when:** "travel promo", "introduce a city or destination", "tourism video for {audience}", "5 minute narrated tour", "city intro with captions"
**Defaults:** about 5 min (the build ran 5:29.27 including 13 s of credits) · 16:9 1920x1080 · 30 fps · narrated (male English voice) with captions and music

## The brief (reusable prompt)
Make a video introducing {city}. Use only footage that the user owns or has licensed, a synthesized original music bed, a male English voiceover, and English subtitles, about 5 minutes long, to attract people from {origin city or country} to travel there. Facts must be accurate. Leave out prices, visa rules, flight times and opening hours unless verified and dated, and tell viewers to check official sources.

## Scene plan
| Time | Beat | What happens on screen |
|---|---|---|
| 0-4.6 s | Cold open | Title over a night aerial of the main square |
| 4.6-26.2 s | Intro | "Half a world away..." welcome line, resident count, the five boroughs |
| 26.2 s | 01 Midtown | Numbered chapter title middle-left, dark glass fact card top right |
| 48.7 s | 02 The Skyline | Towers and observation decks (no prices or hours) |
| 72.6 s | 03 Central Park | Size-bar comparison with the viewer's home park |
| 94.7 s | 04 Four Seasons | Month card, labelled northern hemisphere |
| 116.9 s | 05 Lower Manhattan | Statue, memorial, tallest tower (quiet pad under the memorial line) |
| 162.2 s | 06 Brooklyn | Bridge, promenade, waterfront district |
| 191.8 s | 07 Neighbourhoods | Village, arch, street food |
| 216.6 s | 08 The West Side | Elevated park, island park, new district |
| 236.2 s | 09 Getting Around | Subway 24/7, tap-to-pay "just like at home" |
| 256.7 s | 10 Always Something On | Parade, ship week, festivals with months |
| 280 s | 11 Good to Know | Time-difference card (home time vs local), practical notes |
| 301.1 s | End title | "See you in {city}" |
| about 316-329.3 s | Credits | 13 s attribution card |

## Look
- Palette: taxi yellow #FFC72C as the accent (spoken-word highlight, chapter numbers); the viewer's national red #EF3340 only on the home side of comparisons; dark glass cards; a soft dark radial pool behind titles over bright footage.
- Type: Avenir Next (Mac system font) for titles, cards and captions. Long card values (over 12 characters) set smaller (58 px instead of 78 px) so they stay on one line.
- Layout and texture: chapter titles middle-left, fact cards top right, captions bottom in a soft pill with the current spoken word highlighted in yellow; graded footage (slight contrast and saturation, vignette). Every caption is a single line (max 1544 px wide).

## Motion
Cuts and 0.1 to 0.6 s fades only (crossfade 0.6 s between shots); no full-screen flashes. Chapter changes cut 0.5 s before the first spoken line so the picture lands first. Captions fade only at real pauses and swap instantly when sentences run back to back (a 0.1 s dip at every hand-over looked like blinking). Cards slide in with ease_out_cubic. Word highlight is driven by word start times.

## Audio
Voice: one TTS call per sentence, male English voice, rate +4% in the build (voice was en-US-AndrewMultilingualNeural; here use a text-to-speech voice, see `voice.md`). Music: 96 BPM in D major, I-V-vi-IV in bright chapters and vi-IV-I-V in soft ones; detuned pad, plucked arpeggio, pulsing bass, kick, clap and hats, kick sidechain on pad and bass, reverb; layers fade per chapter; strip to pad under the solemn line. Mix: voice -16 LUFS, music -18 LUFS, music ducked 12 dB under speech (150 ms look-ahead, 400 ms hold), limiter at -3.5 dBFS, then two-pass loudnorm to -14 LUFS / -1.5 dBTP (build: -14.0 LUFS integrated, LRA 4.7 LU).

## Build notes
- The build used about 34 licensed stock clips downloaded from a public archive. We download nothing: the agent must ask the user for their own or licensed footage (upload or folder), or generate stills (Ken Burns pans on PIL-drawn skyline illustrations or user photos). Never download media it cannot licence, and always output a credits card for every clip used.
- Plan with a script first: write the narration per chapter, generate voice per sentence, read durations, then build the timeline from actual voice lengths. Captions come from the sentence text split into one-line chunks with word timings estimated from voice duration.
- Frames: draw cards and captions as PIL RGBA layers, composite over user footage frames. Without ffmpeg on the Mac, stills with Ken Burns motion are the fallback.
- Include a "home angle" device (size-bar comparison, time-difference card, "just like at home" tap-to-pay) in 3 or 4 chapters to make it personal.
- A 60 to 90 s cut: keep the cold open, 3 chapters, and the end title.

## Pitfalls (from what went wrong in our build)
- Picture-to-word sync was approximate: shots chosen from low-resolution previews; some lines played over a related view, not the exact place named. Check each shot against its line at full size.
- Titles were hard to read over bright night footage: add a dark radial pool and heavier text shadow.
- Long card values wrapped onto two lines: shrink over 12 characters.
- Captions blinked at hand-overs: swap instantly, fade only at pauses.
- Some stock clips open on a creator's thank-you intro card: never start such a clip in the first ~10 s of source, and scan 3 frames per shot for card-like frames.
- Real advertising signage shows in aerials as filmed; be aware of it.
- Runtime overshot (5:29 vs about 5 min) because of 13 s of credits; budget credits into the target.
- The music was loop-based and not listened to by a human, balanced by numbers only.

## Style QA
- Every claim in the narration is on the facts list; no prices, visa rules, flight times or hours.
- Every caption fits on one line; the highlighted word matches the spoken word.
- Every clip is credited with author and licence.
- Voice about -16 LUFS, music about -18 LUFS before duck; final -14 LUFS.
