# S-g30-structured-self-intro · Structured 15-second self-introduction reel
**Source:** @tanabe_fragm, https://x.com/tanabe_fragm/status/2103802156675706979 · our build: g30-structured-self-intro
**Use when:** "15-second self intro", "resume reel", "personal intro video", "team intro", "motion design showreel", "introduce me / us in a quick animation"
**Defaults:** 15 s · 16:9 1920x1080 · 60 fps in the build (30 fps here) · music-only (120 BPM)

## The brief (reusable prompt)
You are a top motion designer. Make a self-introduction video so a hiring manager, after 15 seconds, thinks "I want this person to work for me". The star is {person or brand}. Process, in order: (1) state the idea in one sentence; (2) pick 3-4 colours and at most 2 typefaces, one line of reason each; (3) show a storyboard table every 0.5 s (time, on screen, technique, purpose); (4) build; (5) self-check against the pass criteria and fix. Structure: 0-2 s hook (grab in the first 0.5 s); 2-10 s showcase, change technique every 1.5-2 s; 10-13 s densest build-up; 13-15 s the name lands cleanly. Use at least 6 techniques: per-letter text, shape morph, mask transitions, depth (parallax, 3D rotation), particle gather and scatter, count-ups or line drawing. Pass criteria: no constant-speed motion; overlap scenes; main moves on the 0.5 s beat (120 BPM); a 0.3-0.5 s anticipation before each highlight; every paused frame looks good; avoid clichés (all fade-ins, rainbow colours, meaningless spin). Deliver at exactly 15 s with the name as the final beat.

## Scene plan
| Time | Beat | What happens on screen |
|---|---|---|
| 0.0 | Hook | Clay dot springs in with a ripple ring; beat ticks draw in |
| 0.5 | Line | Dot shoots into a horizon line (fast in, soft stop); first words rise from behind it |
| 1.0 | Voice | "Let me think." lands letter by letter (last word in accent colour); mono caption types "A 15-SECOND INTRODUCTION" |
| 1.5-2.0 | Anticipation | Letters sink behind the line; line contracts and slides left |
| 2.0 / 2.5 / 3.0 | Morph | Line opens into circle, then rounded square, then triangle; labels 01 LISTEN, 02 STRUCTURE, 03 BUILD roll in with a scramble |
| 3.5 | Mask | Triangle squeezes, then explodes outward as a clip-path revealing the paper world |
| 4.0-5.0 | Depth | Three cards swing in edge-on; camera orbits through three Z depths (parallax); text bars draw |
| 5.5-6.5 | Slot | Cards flip away; "I write" then slot word flips per-letter: code, essays, plans |
| 7.0-7.25 | Decompose | Line breaks into 3D-scattered letters, turns edge-on, reassembles as "on the beat." |
| 7.5 | Iris | Accent period swells; ink iris opens from it; text changes colour exactly at the iris edge |
| 8.0-9.0 | Count | Odometer 000 to 120 (expo-out) with "BPM"; pulse line draws one spike per beat; final digit rolls to 120 on beat at 9.0; riser starts |
| 9.5 | Anticipation | Drums out; everything grows slightly then collapses to one dot |
| 10.0 | Climax | Dot bursts into 1,700 particles, accent shock ring, camera shake spring; "Ask." rises |
| 10.5-11.5 | Density | "Think.", "Make.", "Refine." one per beat; circle, square, triangle orbit in depth (120 degrees per beat, spring steps); word ring counter-rotates; particles punch on kick |
| 12.0-12.5 | Gather | Orbits fold into centre (back-ease); particles gather left to right into letterforms; shimmer, reverse swell |
| 13.0 | Name | Mask wipe turns particles into solid serif {brand}; bell chord in F major |
| 13.5 | Full stop | Accent dot drops in as the period with a bounce; underline draws back from it |
| 14.0-14.5 | Close | Role line types; invite line rises; REPLAY pill springs in at 14.5; audio fades over the last 0.28 s |

## Look
- Palette: Ink #191817, Paper #F2EEE6, Clay #D97757 (single accent, always marks "the point": dot, vertex, slot word, period, underline), Ash #8C877C. Only two full-frame colour changes (ink to paper about 3.5-4.1 s, paper to ink 7.5-8.05 s), both wipes.
- Type: Fraunces (display serif) and JetBrains Mono (labels, numbers). On a Mac substitute Georgia or Baskerville and Menlo if these are not installed.
- Layout and texture: flat paper world, 3D cards with three Z depths, shock rings as strokes (not fills).

## Motion
No linear motion anywhere: expo-out, cubic or back easing, or damped springs. Main moves start on 0.5 s multiples; letter staggers and card cascades at 0.25 s or smaller. Anticipation windows: 1.5-2.0, 3.25-3.5, 9.5-10.0 (riser cut 30 ms before the hit), 12.5-13.0. Overlap: line hands off to morph (same 360 points); mask reveals the paper world while still growing; cards leave as letters arrive. Count-up ticks computed from the inverse of the easing curve. Digits snap and roll only in the last 40 % of each unit.

## Audio
120 BPM (beat 0.5 s), final bell chord in F major at 13.0. Kick, boom and bell on the first frame; timer ticks on the count-up; drums drop at 9.5 and 12.5 (contrast comes from drop-outs); riser into 10.0; reversed swell before the name. Compressor plus limiter then master gain, tuned to -14.0 LUFS (build: -14.0 LUFS, -2.3 dBFS true peak). Synthesize in numpy on the beat grid.

## Build notes
- Name goes last: ask the user for the name, role line and 3 capabilities; do not assume.
- The 3D card swings and per-letter rotateX flips are CSS 3D in the build: in PIL fake them by scaling card width with cos(angle) (edge-on at 0) and letters by scaling height.
- Particles: 1,700 seeded points; target positions from a text mask; use ease_out_expo from the burst to the letterforms. Reduce to about 900 points if frames are slow.
- Use the 0.5 s storyboard as SCHEDULE; draw mask transitions with PIL ImageDraw ellipse/polygon masks and Image.composite.
- Output English on-screen text unless the user supplies a font that has the glyphs (a font limit of two blocked Japanese text in the build).
- Any maker line (for example "made by {maker}") must be a true statement the user supplied.

## Pitfalls (from what went wrong in our build)
- Mid-transition stills show partial or edge-on glyphs (flips, masked rises, odometer, decompose), so not every frame is a finished picture.
- About 3.9 s was a nearly blank paper frame for roughly 0.1 s between the triangle wipe and the first card: start the first card earlier.
- Flat dynamics (LRA 0.9 LU); contrast only came from drop-outs. Add level changes.
- Ring words at the back of the orbit (10-12 s) were 16-20 px: use 28 px or larger if they must be read.
- Particle name looked grey and thin just before the 13.0 hit: use larger dots or brighter colour.
- Fixed in the build and worth remembering: labels overlapping mid-swap (exit fully before entry), slot words overlapping (old flips out first), spaces collapsing in letter spans (use non-breaking spaces), a stray accent dot left on the end card, the right card cut off by the camera orbit, orbiting shapes colliding with the centre word, a half-rolled odometer still, and a jump at the 2.0 s handoff.

## Style QA
- Storyboard table delivered with the video and the pass criteria checked off.
- Pause at 7 random times: each still reads as a composed picture.
- Name lands exactly at 13.0 s on the bell chord; dot full stop follows at 13.5.
- Beat ticks line up with the 0.5 s grid.
