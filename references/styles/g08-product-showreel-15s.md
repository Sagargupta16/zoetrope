# S-g08-product-showreel-15s · Brand showreel, 7 chapters in 15 s
**Source:** @en______ra, https://x.com/en______ra/status/2104035188061986980 · our build: g08-product-showreel-15s
**Use when:** "motion reel for {brand}", "brand showreel", "feature montage in 15 s", "show what motion design can do for our product"
**Defaults:** 15 s · 16:9 1920x1080 · 60 fps · music-only
**Spec:** family=launch length=15 size=1920x1080 fps=60 audio=music kit=-

## The brief (reusable prompt)
Make a dynamic 15-second motion graphics video for {brand} that shows what an incredible motion designer you are, like a showreel for a résumé. Go all out.

## Scene plan
120 BPM: beat 0.5 s, bar 2 s, one chapter per bar. The brand's dot or mark is the thread: it is the ball, the drag finger, and lands in the logo at the end.
| Time | Beat | What happens on screen |
|---|---|---|
| 0.00-2.00 | 01 Timing and spacing | Ball drop with analytic gravity (first fall exactly one beat), squash and stretch from velocity, onion-skin ghosts, spacing chart, floor ripples scaled by impact speed; ball fills the frame |
| 2.00-3.95 | 02 Radial | 60 ticks spin in, ring draws with a knob, digit rollers land on 25:00, ring splits 25/5, timer starts; dial rushes the lens, iris opens |
| 3.95-5.95 | 03 Kinetic type | Masked rise, scale slam, letter-by-letter bounce drop, staggered spring cascade, swash, feature marquee; four tinted paper bands wipe in from the right |
| 5.95-7.98 | 04 UI | Bands fold into four task cards (scale, radius, tint morph), drag reorder with lift, tilt, shadow; two check-offs; counter rolls 4 to go to 2 to go; cards fly up |
| 7.98-10.00 | 05 Particles | 28 notifications pop on an accelerating 1/32-note grid and jitter; at 9.0 a switch flips, shockwave collapses each into a dot; dots fly to the calendar grid |
| 10.00-12.00 | 06 3D grid | Dots bloom into tiles (diagonal stagger), calendar tilts in 3D, focus days rise in a wave, 6-day streak highest and mint, counter 0 to 6; all converge into one tile |
| 12.00-15.00 | 07 Logo resolve | Tile lands with elastic squash, square pops, doorway carved, dot arcs in and hops into it with confetti, mark slides into lockup, wordmark rises letter by letter, tagline, slow push-in |

## Look
- Palette: plum #2b1b3f, cream #fff6ec, coral #ff6b4a (deeper #e5553a for big type), mint #6fd6b5, lilac #cfc4f2, tints #ffe4db, #efeafb, #ddf5ec.
- Type: rounded sans (build: Nunito); HUD with crop marks, chapter counter, timecode, 30-pip beat meter.

## Motion
Each chapter hands its main shape to the next (ball to plum frame, dial to iris, type to bands to cards, notifications to dots to tiles to logo). Ball impacts at 0.5, 1.0, 1.25, 1.375 s; word slams on 8ths; notification pops on 1/32 notes. Physics analytic, no state between frames.

## Audio
120 BPM, F major, one chord per bar (Fmaj7, Am7, Bbmaj7, Dm7, Bbmaj7, Gm7 to C7sus, Fmaj9). Bar 0 has no drums: shaker 8ths, a rising marimba note per bounce, whoosh. Groove (kick, off-beat hats, clap on 2 and 4, sub, sidechain) 2.0-9.0 and 10.0-11.5. At 9.0 s drums and bass stop for a low-passed pad and one bell. SFX on every pictured action; static gain to -14 LUFS.

## Build notes
900 frames at 60 fps is heavy in PIL: use 30 fps if short on time and say so. Replace CSS 3D with perspective warps.

## Pitfalls (from what went wrong in our build)
- Two seconds per chapter is too fast for small labels (26 px HUD unreadable): use 36 px or larger.
- Quiet dip was only 2 to 3 dB: go 6 dB or more. Use the final logo path from the start, not a circle swapped in one frame. Add frame blending for fast moves.

## Style QA
- Cuts land on the beat grid (bar every 2 s).
