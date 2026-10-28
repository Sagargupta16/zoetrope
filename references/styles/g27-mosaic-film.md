# S-g27-mosaic-film · Glass and gold-leaf mosaic film
**Source:** @LCSlates, https://x.com/LCSlates/status/2102503028859211905 · our build: g27-mosaic-film
**Use when:** "abstract art film", "mosaic or tile animation", "figures made of particles", "ambient generative film with sound", "square animated short"
**Defaults:** 80 s · 1:1 1080x1080 · 60 fps in the build (30 fps here) · music-only (generated score)

## The brief (reusable prompt)
Make an 80 second square animated film that looks like a glass and gold leaf wall mosaic whose tiles were never glued down, so they can lift, flip, fly and click back into place. Figures are flocks of tiles, so a fish swims by its tiles swimming. (The original text stops mid-sentence; we carried the rule through every scene: no figure is ever redrawn, every figure is the wall's own tiles leaving their sockets and coming back.)

## Scene plan
| Time | Beat | What happens on screen |
|---|---|---|
| 0-8 | Gold ground | Fade up on bare gold; one tile lifts, turns and clicks; six more; a ripple; a title flips in letter by letter |
| 8-22 | Sea | Diagonal flip-wave to an underwater picture; a fish peels out head first leaving a fish-shaped hole, swims as a spine of tiles, U-turns through depth, loops, re-enters its socket; a school of 7 silver fish does the same |
| 22-37 | Dawn | Flip-wave radiating from the sun; a crane lifts out, flaps (wing tiles rotate about the body axis), dissolves into a murmuration with small dark birds, re-forms, flies home |
| 37-52 | Tree on gold | Grows up by flip; leaves flip to autumn; wind takes them in a tumbling swirl; they flip to blossom mid-air and return |
| 52-66 | Night / unsetting | Night falls top-down; stars twinkle; the whole wall lifts into a turning galaxy disc, folds into a globe that flips from lapis to gold in the air; camera pulls back to the empty bed |
| 66-80 | Return | Globe bursts home, inner tiles first (long rattle of clicks); final panel: title plus a small fish with a wagging tail whose eye is missing; the eye tile drifts in and clicks in last at 77.5 s with a solo bell; push-in, glint, fade |

## Look
- Palette: gold and silver leaf, lapis blue, smalti glass tones, combed lime-mortar plaster for empty sockets. No hex codes were recorded in the build.
- Type: none; the title uses a hand-coded 5x7 bitmap font made of tiles. In PIL, draw the title from a 5x7 bitmap the same way.
- Layout and texture: 72x72 grid (5184 tiles), each with its own size, lay angle, tilt and tone jitter; bevelled edges; soft shadows under lifted tiles; bloom, vignette, light grain.

## Motion
Pictures change by flips: each tile carries the old picture on one face and the new one on the other, and only tiles whose colour changes flip (so the title appears by letter tiles alone flipping). Flip waves travel diagonally or radially from a source. Flip axes are tile-local x/y (random axes landed squares as diamonds). Fish tiles follow the head's path at their own body distance plus tail undulation in depth, so a turn goes edge-on in perspective. Everything is a pure function of t with no simulation state, so seeking is exact.

## Audio
Synthesized in code: inharmonic glass-bell partials, additive pads, plucked strings (Karplus-Strong), a low drone, reverb, a filtered-air layer driven by measured tile speed, and one click per tile landing (about 30,000 landings) taken from the same schedule that drives the picture, density-compensated so a 5000-tile wave is a rattle, not a roar. Solo bell for the last eye tile at 77.5 s. Loudness: raw mix about -24 LUFS; gentle compressor, +4.1 dB, limiter to -14.0 LUFS (peak -0.9 dBFS).

## Build notes
The build was WebGL2 with 3D shading, MSAA and bloom; none of that exists in PIL. Workable substitute: a smaller grid (for example 48x48 or 72x72) of rotated rectangles drawn with PIL, flip simulated by scaling the tile width with cos(angle) and switching colour at 90 degrees, gold glitter by a per-tile tone jitter plus a moving sweep highlight, shadows as offset dark rectangles. Pre-compute figure masks as arrays and a per-tile path by a seeded function of t. Reduce scope for time: 3 to 4 scenes instead of 6, 30 to 45 s. Use numpy for the bell, pad and click layers; scale the click density by tile count. No third-party media is needed.

## Pitfalls (from what went wrong in our build)
- At 72x72 the figures look like chunky pixel art; the crane's body was a blob and night houses were simple. Use a finer grid for important figures.
- The payoff eye tile was only 20-30 px and visible about 1.5 s; make the payoff larger or longer.
- The murmuration was a parametric swirl, not real flocking; say so or avoid claiming flocking.
- The first ~0.8 s of the globe burst is subtle; start the inner tiles earlier or add a cue.
- The final push-in crops the edge of the title's first letter; leave a margin.
- Audio was checked by measurement only, not by ear.
- Flash safety: the build checked mean-luma deltas over all frames (max 2.7/255 per frame); repeat this check for flip-wave scenes.

## Style QA
- Every figure leaves a visible hole in the wall and refills it.
- Click count and density match landing times (no roar on large waves).
- Frame-to-frame luma change stays small (no flashing).
- Title and payoff fully inside the frame.
