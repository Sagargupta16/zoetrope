# S-g10-showreel-spec · Spec-sheet résumé reel (96 BPM)
**Source:** @darel023, https://x.com/darel023/status/2103424524297420829 · our build: g10-showreel-spec
**Use when:** "résumé reel", "hook in the first second", "cut to music", "typography, shape, camera, colour chapters", "self-aware spec-sheet reel"
**Defaults:** 15 s · 16:9 1920x1080 · 60 fps · music-only

## The brief (reusable prompt)
You're a world-class motion designer and this is your 15-second résumé reel. Make it dynamic and confident: open with a striking hook in the first second, build through distinct techniques (typography, shape play, camera moves, colour shifts), and land on a clean, memorable final frame. Pacing should feel cut to music. Go crazy.

## Scene plan
96 BPM, 6 bars of 2.5 s. A HUD shows chapter, countdown "seconds left" (15 minus t), technique name and a progress bar with chapter ticks.
| Time | Beat | What happens on screen |
|---|---|---|
| 0.00-2.50 | 01 TYPE (hook) | Seven words on 8ths (0.3125 s): "15 / SECONDS. / 900 / FRAMES. / EVERY / ONE / ON PURPOSE." Each word has its own move (slam with ghost split, masked rise, outline echo, zoom punch); background colour flips each word; letters fall and the period stays |
| 2.50-5.00 | 02 SHAPE | Period pops into a circle; square drops, triangle springs; squash on kicks; bounding boxes with live values; 360-point morph waves; cobalt circle wipe |
| 5.00-7.50 | 03 CAMERA | Push-in through six frames, whip pan with roll and blur, orbit and crane around extruded "DEPTH", true dolly zoom, crash zoom into the D, pink flash |
| 7.50-10.00 | 04 COLOUR | Gradient field, palette swap every 8th by radial wipes (8 palettes), italic serif "colour", posterizes into grid |
| 10.00-12.50 | 05 LAYOUT | Six cells re-flow through 7 layouts on a 12-column grid, guides flash per snap, live W/H labels, last cell full bleed |
| 12.50-13.75 | 06 ALL OF IT | 16th-note recap: TYPE / SHAPE / CAMERA / colour / LAYOUT / TIMING / taste., then one 16th of black |
| 13.75-15.00 | End card | Name rises in, red dot falls and squashes into the full stop, rule draws, "MOTION DESIGNER / SHOWREEL 2026" |

## Look
- Palette: ink #0d0d0f, paper #f2eee4, signal red #ff3a1d, cobalt #2236ff, lime #c6ff2e, pink #ff5fa8, sun #ffb400.
- Type: Avenir Next Condensed Heavy (display), Bodoni 72 Book Italic (contrast), mono HUD (Menlo declared; the delivered render fell back to JetBrains Mono, so either is faithful); all macOS system fonts.
- Layout and texture: 12-column grid, true live numeric annotations.

## Motion
Cuts and palette swaps on 8ths; shapes squash on kicks. Dolly zoom: focal length scales with camera distance (approximate with a scaled background layer). Masked reveals start further below so tops do not show early.

## Audio
96 BPM, A minor. Boom, crash and stab at 0.0 s; stab and kick per 8th; 32nd snare fill into bar 2; bloops on shapes; whoosh per camera move; chord stab and pluck per palette swap; woodblock per layout snap; riser in the recap; one 16th of hard mute before the drop; kick, boom, crash on the end card; bells on the subline. -14.1 LUFS.

## Build notes
Use 4 chapters if time is short. On-screen numbers must be literally true (15 s x 60 fps = 900 frames). Put the user's name or {brand} on the end card.

## Pitfalls (from what went wrong in our build)
- Difference-blend HUD reads mid-contrast on red and some gradients: use solid colour chosen per scene.
- Masked letter rise shows tops as short bars for 2 to 3 frames (13.8 to 13.9 s): start the mask lower.

## Style QA
- Hook word lands on frame 0.
- A true silent 16th precedes the end-card drop.
