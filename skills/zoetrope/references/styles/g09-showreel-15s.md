# S-g09-showreel-15s · Generic motion-design showreel (128 BPM)
**Source:** @tonytonggg, https://x.com/tonytonggg/status/2104021942638674231 · our build: g09-showreel-15s
**Use when:** "motion designer showreel", "résumé reel", "go all out 15 s", "show range and taste", "portfolio opener"
**Defaults:** 15 s · 16:9 1920x1080 · 60 fps · music-only
**Spec:** family=launch length=15 size=1920x1080 fps=60 audio=music kit=-

## The brief (reusable prompt)
Make a dynamic 15-second motion graphics video that shows what an incredible motion designer you are, like a showreel for a résumé. Go all out.

## Scene plan
128 BPM: 8 bars equal 15.000 s, one bar is 1.875 s. One orange ball runs through and lands as the dot of the final title.
| Time | Beat | What happens on screen |
|---|---|---|
| 0.00-1.88 | 01 Timing and spacing | Ball drop with squash and stretch from real velocity, anticipation, onion-skin ghosts, arc trace, spacing chart (12 fps ticks), live graph editor with playhead; ball fills frame orange |
| 1.88-3.75 | 02 Kinetic type | MAKE (masked rise), it (serif italic slam), MOVE. (letters from different directions; period is the ball), then 7 alternating solid/outline marquee rows; rows close like blinds |
| 3.75-5.63 | 03 Shape morph | 240-point path morph circle, square, triangle, star with time-echo trails and tool-UI anchors; star becomes a frame that blows past the lens |
| 5.63-7.50 | 04 Depth | 30-frame perspective tunnel, twisting, rails, fog, beat-pulsed line weight; whites out to bone |
| 7.50-9.38 | 05 Particles | 3,200 seeded particles burst, swirl, converge into the word CRAFT, then explode as streaks; caption "every frame, on purpose." |
| 9.38-11.25 | 06 Generative grid | 11x6 Truchet tiles, diagonal rotate waves per beat, weight morph, colour inversion |
| 11.25-13.13 | 07 Dimensional type | 3D cylinder of 12 skill words around the ball; collapses into it |
| 13.13-15.00 | End card | Ball jumps in an arc, lands with squash as the dot of the title, eyebrow, rule, "MOTION DESIGN · SHOWREEL 2026", slow push-in |

## Look
- Palette: ink #0b0b0e, bone #efebe3, orange #ff4f1f, lime #d7ff3a, blues #2b4bff, #5470ff, #6f86ff.
- Type: Helvetica Neue Condensed Black (display), Didot Italic (contrast), Menlo (HUD); all macOS system fonts.
- Layout and texture: film grain, vignette, HUD in a difference blend.

## Motion
Ball physics are piecewise parabolas. Morphs 0.3 s expo in-out; draw-ons 0.32 s. Pure function of t, seeded random. Circle Bezier handle length 0.5523 times radius. Fake the tunnel with scaled concentric rectangles.

## Audio
D minor (Dm, Dm, Bb, C, Dm, Bb, C, Dm add9). Bar 0 has no kick: ticking clock and three rising glass blips on the ball impacts. The drop lands as the ball fills the frame (1.875 s). Supersaw stabs on MAKE / it / MOVE, a zip on every morph, snare roll and riser through the tunnel, wooden plucks on tile waves, bell as the ball lands. Kick sidechain, 0.35 s tail fade, -14 LUFS.

## Build notes
Pick 4 to 5 chapters if time is limited rather than all 7. On-screen labels must be literally true (BPM, point counts, focal values); an earlier "fov 62" label was wrong and was replaced.

## Pitfalls (from what went wrong in our build)
- 19 px HUD labels are unreadable at 1.875 s per chapter: go larger.
- Grain pushed bitrate to about 18.9 Mb/s (35.5 MB): CRF 20 roughly halves it.

## Style QA
- Ball is the continuous thread and lands as the title dot.
