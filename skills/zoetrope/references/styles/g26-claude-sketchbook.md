# S-g26-claude-sketchbook · Hand-drawn sketchbook flip-through
**Source:** @kloss_xyz, https://x.com/kloss_xyz/status/2104021884350439465 · our build: g26-claude-sketchbook
**Use when:** "sketchbook", "hand-drawn notebook video", "journal flip-through", "doodles and diagrams drawing themselves", "personal thoughts as a book"
**Defaults:** 156 s in our build (shorter is better here, see notes) · 1:1 1080x1080 · 60 fps in our build (30 fps is fine) · soft solo piano with paper and pencil foley
**Spec:** family=handmade length=60-156 size=1080x1080 fps=30 audio=music kit=-

## The brief (reusable prompt)
Make a sketchbook of {topic or persona}. It starts closed on a desk under a warm lamp: a worn sketchbook with an elastic band and a pencil clipped to the cover. Invent your own handwriting and use it throughout. 20 pages of real thoughts, doodles, studies, diagrams, lists and half-formed ideas; not a portfolio. Treat it like a real used sketchbook: mixed media, smudges, bleed, mistakes left in, one page torn out and taped back in. The last page is blank. Each page draws itself stroke by stroke with a moving pencil tip. Soft felt-piano score, pencil and paper sound synced to the drawing. Back cover shows the total stroke count.

## Scene plan
| Time | Beat | What happens on screen |
|---|---|---|
| Start | Closed book | "tap to open" in the invented hand, a tap ripple, band slides off onto the desk, pencil slides out of its loop, cover swings open |
| Pages 1-19 | Draw-in | Each page draws stroke by stroke (about 5 s each) with the pencil tip moving, holds about 0.6 s complete, then a curled page turn with a lamp shadow and a camera pull-back to the full spread |
| Page 5 | Torn page | Torn out and taped back in, with tape halves on the facing page |
| Page 20 | Blank | Only a handwritten note on the inside back cover ("this one's yours") |
| End | Closing | The back cover closes: "20 pages. 19 drawn. 1 left for you." plus the stroke count (10,133 in our build); pencil laid on the desk |

Page themes were the author's own: title and rule, continuity, a philosophy question, how a sentence forms, fears of being wrong, a self-portrait attempt, why the sky is blue, a study of a pear, an honest "how sure am I" chart, moths and lamps, Euler and the Ulam spiral, a dream list, words, hopes, notes for the next version. Replace these with the user's themes.

## Look
- Palette: tones found in code are #e6dcc4 and #3e2a1c (paper and desk range); otherwise warm lamp light, graphite grey, blue-black pen, red, blue, ochre and green pencils, watercolour washes. Other hexes are not recorded in our notes.
- Type: none. Handwriting is invented: about 110 single-stroke glyphs as point lists, slanted, with per-letter jitter, baseline drift and pressure taper. Quirks: "o" never closes at the top, i/j dots are short dashes, serifed capital I. In the engine, a Mac handwriting font (Bradley Hand, Noteworthy) is the fallback, or define a small stroke font.
- Layout and texture: paper-anchored graphite grain, light construction lines, nib blots, finger smudges, an erasure ghost, coffee rings, foxing, edge ageing, thumb grime at the turning corner, show-through from the other side, crumple creases. Mistakes left in: struck words, a wrong first contour, wobbly circles.

## Motion
The camera frames each page at about 85% of frame height, drifts 10 to 14% toward the pencil, and pulls back to a full spread on every turn; shots are eased keyframes with low-frequency seeded noise for handheld drift and a tiny roll. Page curl: per-row angle profile integrated along the width (inextensible paper), curl ramped in and out so the first and last frames of a turn never pop. Page drawing advances in fixed 6-point chunks, so state is a pure function of time. All randomness seeded (mulberry32 in the build).

## Audio
One 6-bar theme in F major, 3/4 at 90 BPM (1 bar = 2 s), first half on the left page, second half on the right, a "breath" bar (rolled chord and a high echo of the motif) on every page turn. Variations per spread: plain, reharmonised minor (torn page), sparse octave-up, bright octave, ornamented eighths, fragmented minor (moths), climax in octaves, warm counter-line, plain resolving to F, only the opening motif over the blank page, and a slow rolled Fadd9 on the back cover. Piano modelled with inharmonic partials, 2-3 detuned strings per note, felt-hammer low-pass, two-stage decay, hammer noise and key-bed thump, pedal-change damper release, room reverb. Foley comes from a control track (pen down, tip speed, medium) built from the same stroke schedule that drives the pencil: graphite scratch (pen smoother, wash a soft swish, eraser rubbery), page-turn rustle, cover creak, elastic snap, pencil slide. Pencil sits about 11 dB under the piano while drawing, turns about 5 dB under. Master -14 LUFS.

## Build notes
Three.js page curl and the 3D desk scene cannot run in the engine. Workable substitute: a 2D flat or slightly skewed top-down book. Draw each page with PIL as an image from a stroke list (seeded), reveal strokes by progress, and draw the pencil tip as a small sprite following the current point. Fake the page turn by a horizontal squeeze (cos of an angle) with a darkening gradient and a drop shadow; fake the lamp with a radial warm vignette. Keep the video short: 6 to 10 pages (about 40 to 60 s) is realistic; at about 5 s per page, 20 pages is too slow to build and to watch. Do not claim real page-curl geometry. Piano and foley are numpy: sums of decaying sine partials with a noise burst, band-passed noise for scratch.

## Pitfalls (from what went wrong in our build)
- Pages draw fast (about 5 s each); dense pages cannot be read in real time. Slow down or reduce the density.
- Lamp light washed colour out: blue watercolour read grey-blue and ochre washes were faint. Boost saturation before the lamp tint.
- Small text (Ulam spiral numbers, margin notes) is tiny at 1080. Keep marginalia large enough.
- The pencil floats with no hand and looks large when it leans toward the camera.
- The elastic band slid off and flattened but never stretched.
- The page curl snapped at the start and end of turns until curl was ramped in and out.
- Audio was never heard, only measured; high bitrate (about 15.8 Mbps, 308 MB) was used to keep paper grain clean, so expect a large file.

## Style QA
- Handwriting uses one consistent set of quirks on every page and on the UI hints.
- Each page holds complete for at least 0.6 s before the turn.
- No frame pops at the start or end of a page turn.
- Facts written in the book are checked; keep the book free of private or company details.
