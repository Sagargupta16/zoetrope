# S-g03-15s-product-ad · 15 s paste-and-get product ad
**Source:** @tstfully, https://x.com/tstfully/status/2104033772949680192 · our build: g03-15s-product-ad
**Use when:** "15 second product ad", "tool explainer ad", "paste X get Y", "short SaaS ad", "yellow highlighter style ad"
**Defaults:** 15 s · 16:9 1920x1080 · 30 fps · music-only
**Spec:** family=launch length=15 size=1920x1080 fps=30 audio=music kit=-

## The brief (reusable prompt)
Make a 15-second motion graphics product ad: {one-line input to output promise, for example "paste a link, get every word"}.

## Scene plan
| Time | Beat | What happens on screen |
|---|---|---|
| 0.0-2.5 | Problem | Generic video player, playhead scrubs back and forth, timecode jumps, waveform reshuffles. "The good part is in there... somewhere." |
| 2.5-6.0 | Paste | "Paste a link." Input bar, Cmd V keycaps press, URL drops in with selection flash, "link found" chip, cursor clicks the button, yellow ripple floods the frame |
| 6.0-8.0 | Drop | Bass drop on a yellow field. Three-word slam on three 8th notes while a transcript card streams in word by word with timestamps |
| 8.0-10.0 | Payoff | Yellow wipes up, wall of timestamped lines rushes past, odometer rolls 0:00:00 to 1:12:48. "Timestamped, start to finish." |
| 10.0-12.0 | Use it | Three cards on the beat: Search (types a word, 3 hits highlighted), Copy (quote selected, Copied), Export (.txt .srt .md) |
| 12.0-15.0 | End card | Mark morphs play triangle to three text lines; "Paste a video. Get every word." with highlighter sweep; closing line |

## Look
- Palette: ink #0c0d11, highlighter yellow #ffe14d (only accent), panel #1d1f28, grey #8b8e9b, card cream #fffdf7, timestamp on cream #5f5845.
- Type: heavy display (Archivo Black), UI sans (Inter), mono for timestamps (IBM Plex Mono). On a Mac use installed substitutes (a black-weight grotesque, Helvetica Neue, Menlo).
- Layout and texture: dark calm field, one loud yellow moment at 6.0 s.

## Motion
Five beats on a 120 BPM grid (beat 0.5 s). Ripple: circle scaling to cover the frame (ease_in_cubic, 0.75 s, from 5.25 s so it lands on the 6.0 s drop). Word slam on three 8ths (0.25 s apart, 0.3 s each), ease_out_expo with no overshoot. Odometer is transform-only digit strips with an edge mask. Wall scrolls about 1,200 px/s, faded at 9.45 s.

## Audio
120 BPM, A minor lifting to C major on the end card. Muted pulse and tape-scrub swishes in the hook, groove from the paste, key clicks, paste pop, riser and snare roll into the 6.0 s drop (sub boom, crash), typing ticks, odometer ticks following the counter ease, plucks on the three cards, final chord. 0.6 s tail fade, -14 LUFS.

## Build notes
Pure PIL. Pre-build every changing text (timecodes, typed query) as a state function of t. Name the input platform in text only; never draw a real platform logo, use a neutral white play circle and a fake URL ID.

## Pitfalls (from what went wrong in our build)
- First frame was nearly black (hook fades in over about 0.3 s): fade in faster or pick a poster frame later.

## Style QA
- No clipped or overlapping text in frames at 0.5, 5.6, 6.2, 8.3, 10.7, 14.9 s.
