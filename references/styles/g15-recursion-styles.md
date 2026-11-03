# S-g15-recursion-styles · Self-referential Droste dive through nine styles
**Source:** @emollick, https://x.com/emollick/status/2103688362960019567 · our build: g15-recursion-styles
**Use when:** "explain {concept} where every explanation has a different video style", "self-referential", "clever and fast moving", "style showcase that teaches", "loops into itself"
**Defaults:** 69 s · 16:9 1920x1080 · 30 fps (60 fps would be smoother for the fast zooms) · music-only, all explanation as on-screen text
**Spec:** family=explainer length=69 size=1920x1080 fps=30 audio=music kit=-

## The brief (reusable prompt)
A video explaining {concept}, where every explanation of it has a radically different video style. Make it self-referential, clever and fast moving.

## Scene plan
Pacing at 144 BPM (beat 0.4167 s): intro 8 beats; each dive level 12 beats (5.0 s, last 2 beats are the zoom); base case 16 beats; each return 4 beats (1 beat zoom out, 3 beats for the return line); keynote finale 8 beats; outro 8 beats; 0.67 s hold on the loop frame. Total 69.0 s.

| Depth | Style | What it explains | Return value on the way out |
|---|---|---|---|
| 0 | Bare call on black | explain("recursion"); the parentheses open into a window | loop target |
| 1 | Product keynote (white, Helvetica) | dictionary line "defined in terms of itself"; footer "Slide 1 of 1 of 1 of 1 ..." | "Got it. If not, see Recursion." |
| 2 | Silent film (sepia, 16 fps, grain, scratches) | "To understand recursion, one must first understand recursion." | iris out on "The End (of Chapter the Second)" |
| 3 | 8-bit platformer (320x180 canvas scaled x6) | "Every level contains a smaller level." | "LEVEL CLEAR!" |
| 4 | Green-phosphor terminal | real Python explain(topic, depth) with base case depth == 9 | depth 4 returned "got it" |
| 5 | Nature documentary (2.39 letterbox) | fractal tree: "A tree is a trunk, holding two smaller trees." | blossoms, "the tree is complete" |
| 6 | Late-night infomercial | "BUT WAIT! There's a smaller one inside!"; TV shows the ad 3 levels deep | "PROBLEM SOLVED! (by solving a smaller one)" |
| 7 | Chalkboard | 4! = 4 x 3! down to 1! = 1 base case | results written bottom-up: 2, 6, 24 |
| 8 | Film noir | "Inside it was a smaller case ... I needed the one that doesn't open." | "Case closed." |
| 9 | Picture book, nesting dolls | "This one doesn't open. That's the base case." | dolls nest back in reverse |
| - | Outro | "To understand this video, watch this video." | last shot zooms into frame 0, so the video loops |

A call-stack panel bottom-left (debugger overlay) pushes one line per level and shows the return as each pops; it is the one constant across all styles.

## Look
- Palette: varies per style by design. Values used in the build include #1a0a00, #3b2a26, #ffffff, #f2f2f2, #e6d6b4 (sepia), #ffe600 and #ffe14a (infomercial yellows), #42ff7b (terminal green), #111216, #fffaf0.
- Type: per style, all Mac system fonts: Helvetica Neue (keynote), American Typewriter (noir), Chalkduster (chalkboard), Impact (infomercial), Big Caslon, Didot and Bodoni 72 (serif styles), Copperplate, Avenir Next, plus a hand-made 5x7 pixel font for the 8-bit level.
- Layout and texture: per-style texture (grain at 24 fps, scratches, flicker, letterbox, rain and smoke for noir).

## Motion
Each scene declares a portal (centre, scale s, rect or circle). During a zoom the parent scales by k = (1/s)^z about the fixed point F = (c - s*C)/(1 - s), and the child sits at k*s so at z = 1 it is exactly full frame. Interpolate z in log space with an ease-in-out for constant-speed travel. Zoom in 0.83 s, out 0.42 s. Circular portals expand the clip from the inscribed circle to the frame diagonal. Unwind is the same maths reversed. Silent film clock is quantised to 16 fps. All randomness seeded.

## Audio
144 BPM. One theme built from itself: motif 1-3-5-3, bar k starts on note k of the motif, chords I, iii, V, then V7 of the key a semitone up. Each level transposes up a semitone (C major at depth 1 to Ab major at depth 9) and re-orchestrates in that genre (e-piano and kick, honky-tonk stride, chiptune, synthwave saw bass, string pad and marimba, slap bass and brass stabs, pizzicato and glockenspiel, walking bass and brushes in minor, music box). On the way out the motif plays backwards (5-3-1), a semitone lower each time, ending in C. SFX: rising whoosh in, falling whoosh out, arrival thumps, blips, key clicks, slams, cash-register ding, static, chalk scratches, typewriter, door thud, wooden doll toks. Original: -14.0 LUFS, -1.9 dBTP, mastered with a look-ahead limiter. No voice.

## Build notes
This is the hardest style. Render each level as its own PIL layer (draw_level(n, t) returns an image), then compose the camera by scaling and cropping the parent image with the formulas above; use LANCZOS resize and render big enough that zoomed layers stay sharp (the portal zooms about x9 in places). Keep levels simple: a 3-5 level cut with 4 to 5 distinct styles is a realistic scope for the engine; keep the base case, the stack HUD, the unwind and the loop. Only simple additive synthesis in numpy is needed for the genre cues. Use only on-screen text, so no TTS.

## Pitfalls (from what went wrong in our build)
- 30 fps made the fast log-space zooms judder; use 60 fps if size allows, or lengthen zooms.
- Reading time is tight: main line 2 to 4 s, return line about 1 s. Terminal code (33 px) and the HUD (17 px) are hard to read on a phone.
- The HUD covered up to about 330x280 px at depth 9; keep layouts clear of it.
- The 60 px dew-drop portal (x9 zoom) is easy to miss; make portals larger.
- The infomercial TV copies were static and the channel-change static lasted only about 0.3 s.
- An un-normalised reverb impulse once made the mix about 14 dB reverb: normalise impulses and meter the result. Mix was checked by meters only.

## Style QA
- Frame at the end equals frame 0 (loop check).
- The code on screen actually runs and prints what the screen says.
- Each return line matches its level, and the stack HUD is empty at the end.
