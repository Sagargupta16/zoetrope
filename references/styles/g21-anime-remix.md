# S-g21-anime-remix · Anime-style compressed-learning short
**Source:** @emollick, https://x.com/emollick/status/2103272686570918334 · our build: g21-anime-remix
**Use when:** "anime style explainer", "make it interesting for a social audience", "compressed learning", "TikTok or Reels short", "mascot character teaches a concept", "manga panels recap"
**Defaults:** 46.5 s · 9:16 1080x1920 · 30 fps (character drawn on twos, 12 drawings/s) · music-only (no narration unless asked; big type carries every idea)

## The brief (reusable prompt)
Take {topic} and make the same message much more interesting to a social media audience that loves anime, quick clips and compressed learning. Use an original anime-inspired style only: no existing characters, logos or catchphrases.

## Scene plan
Episode map at 160 BPM (beat 0.375 s, bar 1.5 s). The worked example was recursion; replace the content, keep the structure.
| Time | Beat | What happens on screen |
|---|---|---|
| 0 to 2.25 s | Cold open hook | Eye close-up snaps open at 0.375 s; three slammed lines; impact frame at 1.125 s; chip "{TOPIC} · UNDER 1 MINUTE" |
| 2.25 to 4.5 s | Title card | Episode stamp (e.g. "Episode 1"), big title word, ribbon subtitle, mascot pops up and winks |
| 4.5 to 9.0 s | Lesson 1 | First genre world (battle): problem posed, "secret technique", the rule on screen; portal opens at 7.5 s, zoom in at 8.625 s |
| 9.0 to 15.0 s | Genre dive | One genre per step, 1.5 s each (magical, mecha, slice-of-life), last two at 0.75 s (horror, isekai status window) |
| 15.0 to 16.5 s | Runaway | Nested panels zoom ever faster (capped near 6 levels/s), counter and stack HUD fill |
| 16.5 to 18.0 s | Crash | Impact frame, error banner, vertical katakana word, "what went wrong" line, screen cracks, blackout |
| 18.0 to 19.5 s | Eyecatch | Title card, mascot wink, "LESSON 2", "rewind" |
| 19.5 to 24.0 s | Lesson 2 | Rewind, the fix shown on screen with the key line highlighted and labelled |
| 24.0 to 31.5 s | Lesson 3 | Answers flow back up through each genre by zooming out; combo hits; key change on the final answer |
| 31.5 to 39.0 s | Recap | "{TOPIC} IN 3 MOVES": three manga panels in the three genre palettes, red stamp (stamp hit at 36.75 s) |
| 39.0 to 46.5 s | Next episode | Preview card whose next episode is this episode; card switches to the cold open, camera dives in; last 0.75 s equals frame 0 (loop) |

## Look
- Palette: ink #14101a, bg #07060c, hero cloth #ff5a1f, cream #fff0e0, impact yellow #ffe14a, SFX red #ff2a3c, badge red #e8202c, sunset gradient #170a3c to #7a1a7a to #ff4f5a to #ffb347. Each genre world gets its own palette (pink on pink was unreadable until restyled).
- Type: heavy condensed italic (Avenir Next Condensed Heavy Italic) with thick black outline and red drop shadow for the battle voice; Hiragino Maru Gothic for magical and slice-of-life; Menlo Bold for code and HUD; Hiragino Mincho for horror; Hiragino Sans W9 for kanji and katakana. All are macOS system fonts; elsewhere pick the closest installed font and say which. Main lines 120 to 200 px, subs 44 to 60 px.
- Layout and texture: focus lines, inverted impact frames, halftone screentone, katakana SFX (ドン, キラッ, ガシャン, ゾッ). Keep key text inside y 230 to 1530 and x 60 to 1020 (clear of platform header, caption and action-bar zones). Thin progress bar with 4 lesson ticks near y 200, lesson chip, call-stack style HUD on the left edge.

## Motion
Text slams in with a fast scale overshoot (ease_out_back) and settles; camera moves and speed lines run at full 30 fps; the mascot idle bob and blink are held on twos. Portals use a Droste zoom: fixed point F = (c - s*C)/(1 - s), scale in log space, so repeated zooms stay smooth. Zoom-ins pair with whooshes, zoom-outs with reverse swells. Impact frames (inverted, 1 to 2 frames) only at 1.125, 16.5, 28.5 and 29.25 s, never more than 2 per second. Pure function of t, seeded noise only.

## Audio
160 BPM J-rock anime opening: distorted saw power chords (palm-muted 8ths), 8-beat drums, saw/sine bass, square/saw lead with delayed vibrato, plus a genre layer per world. Harmony IV-maj7, V7, iii7, vi7 (the "royal road"). One four-bar hook; each step down the dive transposes up a semitone (D, Eb, E, F, F#, G); in the runaway the hook's first bar replays at 2x, 4x, 8x, 16x speed; the unwind steps back down and the final answer lands on a whole-step key change up. Outro plays the hook on a music box, ending near silence so the loop restarts on the eye "shing". SFX on the beat grid: shing, impacts, text thumps, whooshes, risers, sparkles, error buzzer, glitch stutters, glass shatter, rewind chirp, jingle, bell, combo hits. Measured sync was within about 2 ms. Master -14 LUFS (final -14.1 LUFS, -2.0 dBTP).

## Build notes
Draw 1080x1920 frames in PIL on the Mac using the system fonts above; keep a helper layer for outlined text, focus lines, halftone and impact inversion (ImageOps.invert). Make the mascot procedurally (a chibi head with simple cel shading and one-weight ink), with one original outfit accent per genre. Keep it original: generic devices only, no known characters. Score as numpy synth with a limiter written in numpy. Use a text-to-speech voice only if the user asks for narration (a narrated version probably teaches better, but was not requested). Use the encode ladder in `engine.md` at 1080x1920; the source file was 56.8 MB, so a CRF 20 to 23 encode is fine for sharing.

## Pitfalls (from what went wrong in our build)
- Pace is aggressive by design: 0.75 to 1.5 s beats make some lines glimpses, and 44 to 56 px subs and 26 to 32 px HUD text are hard to read on a phone. Give every teaching line at least 1.5 to 3 s and use larger type.
- Panel borders were stroked along the focus-line path and covered the page in black wedges: stroke borders as separate rectangles.
- Stack chips stayed scattered after the crash because scatter progress never reset; the HUD also showed during blackout.
- Labels covered key code, and sound-effect words sat on the hero or ran off the right edge: reserve zones before placing SFX words.
- Mouth shapes bulged below the chin; the character is vector only, with no real in-betweens.
- The limiter worked hard to reach -14 LUFS (hits squashed, some pumping). The mix was set by numbers, not by ear.
- Exponential on-screen counters and capped visual zoom do not match number for number; do not claim they do.

## Style QA
- First text and first motion appear inside 1 second; hook reads by 2 s.
- Every impact frame is 1 to 2 frames and no more than 2 per second.
- Last frame matches frame 0 if a loop is promised (source measured 0.08/255 mean difference).
- Check text on every genre background for contrast.
