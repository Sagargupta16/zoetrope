# S-g02-promo-any-tools · Noise-to-calm app promo (48 s)
**Source:** @feiflow, https://x.com/feiflow/status/2104039666093572362 · our build: g02-promo-any-tools
**Use when:** "promote my app", "make it stunning", "animated promo with sound effects and music", "show the problem then the product"
**Defaults:** 48 s · 16:9 1920x1080 · 30 fps · music and SFX only (no voice)

## The brief (reusable prompt)
I need to promote {product}. Make me an animated video, including sound effects and music, to promote it. Use any technique that works and make it the best, most stunning result possible.

## Scene plan
| Time | Beat | What happens on screen |
|---|---|---|
| 0.0-4.8 | Noise | 16 notification cards pop in faster and faster, each shaking. Words "ping.", "buzz.", "ding.", then "Your day is loud." (the word loud rattles) |
| 4.1-6.2 | The nook | Cards are sucked to the centre, the mark pops in, its dot hops, camera dives 48x into the mark's cream square, which becomes the world. Audio near-silent |
| 6.2-11.8 | Brand | "Find your nook." then logo builds (mark slides, letters rise), tagline. Groove drops at 9.6 |
| 11.5-20.5 | Feature 1 (list) | One persistent phone rises in; tasks drop in, one is dragged to second place; clock flips 11:59 PM to 12:00 AM, date flips, unfinished tasks get a carry-over tag |
| 20.5-28.2 | Feature 2 (timer) | Phone glides left, tab switches, time-lapse 25:00 to 18:42 with ring draining |
| 28.2-33.3 | Feature 3 (quiet) | Dark circle floods from the phone; six notifications dissolve into sparks before reaching it. "Let the world wait." |
| 33.3-38.2 | Feature 4 (streak) | Back to light, calendar ripples in, run lights day by day (badge 1 to 6), final burst |
| 38.0-48.0 | Everywhere, end card | Phone shrinks right, desktop rises; mark pops, dot bounces into the doorway, lockup builds, tagline, four feature pills, final chord |

## Look
- Palette: plum #2b1b3f, coral #ff6b4a, cream #fff6ec, lilac #cfc4f2, mint #6fd6b5 (swap in user brand colours).
- Type: rounded sans (build: Nunito 800); use a Mac system rounded sans. Dark room for noise, cream for product, film grain.
- Layout and texture: one phone mock-up travels between beats; soft blobs, grain.

## Motion
One phone object glides left and right between beats (about 0.6 to 1 s, ease_in_out_cubic); copy alternates sides. Notifications pop with ease_out_back and shake. The dive scales 1 to 48 about a pivot inside the cream square so the coral edge leaves frame. Timer, dates and badge are pre-drawn states chosen by t.

## Audio
100 BPM (beat 0.6 s, bar 2.4 s), F major. 0 to 4.8 s no song: out-of-key chimes, phone buzzes, tick, rising drone and riser, reverse suck, then near-silence. 6.2 s warm Fmaj9 pad and a three-note bell motif. Groove 9.6 to 43.2 s: soft kick, rim, shaker, sine bass, electric piano, pluck arpeggio over F, Am, Dm, Bb. In the quiet beat sweep the music bus to a 550 Hz low-pass and thin the drums, then reopen with a riser. SFX on every UI action (tap, drag, tick, chime, rising pluck per streak day, dot-bounce boop). Master -14 LUFS, true peak under -1 dBTP.

## Build notes
Draw the phone UI in PIL as layered states, not screenshots. The 48x dive is the signature: render the mark large and crop-scale it.

## Pitfalls (from what went wrong in our build)
- Brand coral and mint fail contrast for small text on cream: darker shades for small labels, exact colours for logo and big shapes.
- Do not claim device sync, prices or user counts the user did not supply.

## Style QA
- The quiet beat is audibly muffled (music low-passed near 550 Hz).
