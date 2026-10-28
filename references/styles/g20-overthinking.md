# S-g20-overthinking · Abstract motion-design showreel
**Source:** @gizakdag, https://x.com/gizakdag/status/2103566030916239768 · our build: g20-overthinking
**Use when:** "motion graphics showreel", "show off motion design", "abstract video about a feeling or concept", "kinetic type piece", "typography-led reel"
**Defaults:** 15 s · 16:9 1920x1080 · 60 fps in our build (30 fps is fine here) · music and sound design only, no voice

## The brief (reusable prompt)
Make a dynamic 15-second motion graphics video that shows what an incredible motion designer you are, like a showreel exploring the concept of "{concept}".

## Scene plan
| Time | Beat | What happens on screen |
|---|---|---|
| 0.00-2.55 | 01 The thought | A sent chat bubble pops in (back ease); "DELIVERED" rolls to "READ 9:41" on the first heartbeat; an inner voice types itself in serif italic ("...wait. was that too short?", red "?"). Whip-zoom x30 into the dot of the "?" |
| 2.55-5.10 | 02 Branching | Radial decision tree grows 3, 9, 27, 81 branches, one level per beat, labelled with escalating doubts. Outer branches twist further than inner, turning it into a spiral galaxy, then a dive into the centre |
| 5.10-7.15 | 03 The loop | 24 rings of kinetic type on circular paths, alternating rotation, log-scale zoom that kicks on each beat. Flash to red on the beat |
| 7.15-10.00 | 04 Overload | 12 word slams on half-beats with colour flips, outline echoes, chromatic offset and rising shake; a feed of the same bubble multiplies 1 to 324 copies; from 8.05 s a pen scribble (2,600-point seeded walk) tangles over everything, then contracts into a knot |
| 10.00-15.00 | 05 Release | Hard cut to silence. The knot is pulled straight and vibrates like a plucked string, retracts to a baseline with red end caps. The reply arrives ("perfect, see you at 7!"), the title rises out of the line, tagline "it was fine." with the red dot as the full stop. Slow push-in end hold |

## Look
- Palette: paper #EDE9E0, ink #121212, alarm red #FF3B24 (the thought), muted #8B857A, reply grey #D7D1C5.
- Type: Helvetica Neue Condensed Black (slams, rings, title), Hoefler Text Italic (inner voice), Helvetica Neue Medium (chat UI), Menlo (HUD). All are Mac system fonts.
- Layout and texture: editorial paper and ink with one red; crop marks, live timecode, chapter roll, a THOUGHTS counter and a BPM readout drawn in difference blend so one white HUD reads on paper, ink and red. Seeded film grain, vignette on dark chapters.

## Motion
One idea grows from one red dot, driven by one heartbeat that speeds up: tempo accelerates exponentially from 72 BPM at t = 1.0 s to 168 BPM at t = 10.0 s, with t_k = 1 + (9/ln r) * ln(1 + k * ln r / 10.8), r = 168/72. Every cut, slam and pulse sits on that grid; the 18th beat cuts to silence. Each chapter hands its main element to the next (dot, tree centre, flash, knot). Camera work: the dot travels to frame centre while scaling x30. Tree branches draw on with split curves; ring zoom is logarithmic and eased up. Everything is a pure function of t with seeded random (scribble, grain, tree), so any frame can be rendered alone. The THOUGHTS counter counts drawn tree nodes (1+3+9+27+81 = 121), then runs to 9,999 and drops to 0001 after the snap.

## Audio
Heartbeat lub-dub on every beat (72 to 168 BPM), clock ticks on half-beats, key clicks under the typing, a whoosh into the "?". Chapter 02: a bell triad per tree level climbing in D minor, soft plucks for labels. From 2.5 s a Shepard-tone riser (the illusion of an endlessly rising pitch) until the cut. Chapter 03: low saw drone with an opening filter, hats on half-beats. Chapter 04: kick on each beat, distorted stab on each slam (up a semitone every two slams), noise hits, a stutter, snare roll and riser into the knot; pads duck under hits. At 10.0 s everything cuts in 5 ms; a Karplus-Strong plucked low D string (73.4 Hz plus octave) is the line being pulled straight. Ending: D major add9 pad, reply "ding" (A5 to D6), three quiet 60 BPM heartbeats, pentatonic plucks under the title letters, a chime on "it was fine." Master: high-pass 28 Hz, synthetic reverb, lookahead limiter, -14 LUFS, true peak -1 dBTP.

## Build notes
Fully doable with PIL plus numpy; no footage needed. Draw each chapter as a function of local time and share one beat-time table between picture and audio. Supersample 2x for thin lines and type. The tree, rings and scribble are the heaviest parts: precompute their geometry once with a seeded RNG, then draw by progress. Karplus-Strong and the Shepard riser are short numpy loops. Use the engine's mac system fonts as listed. For 30 fps keep the same beat grid and snap cuts to the nearest frame.

## Pitfalls (from what went wrong in our build)
- The zoom into the "?" did not centre the dot at first and a translucent disc showed off-centre: make the tree root start at exactly the dot's final size.
- Two HUD chapter labels overlapped mid-roll: mask the roll tightly.
- Tree labels were struck through by their own child branches: draw a paper-coloured halo behind label text.
- The overload chapter flips background colour 4-5 times a second, a strobe-like passage that could bother photosensitive viewers: warn the user or soften it.
- First 0.5 s is an almost empty paper frame (weak thumbnail); 16 px HUD text is too small on a phone and low contrast on red frames; level-3 tree labels (21 px, about 0.7 s) read as texture.
- The mix was set by meters, not by ear; the limiter can take up to about 9 dB off the loudest hits and may sound squashed.

## Style QA
- Every cut and slam lands on the beat table, and the snap is silent before it.
- Only one accent colour (red) plus paper and ink appear.
- The dot is dead centre at the end of the zoom and the same size as the tree root.
- No label is crossed by a line; HUD text stays legible on all three backgrounds.
