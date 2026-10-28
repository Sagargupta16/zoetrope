# S-g11-movie-credits · Film-style opening credits
**Source:** @goodside, https://x.com/goodside/status/2102937913726235004 · our build: g11-movie-credits
**Use when:** "opening credits", "film title sequence", "movie intro about us", "end credits", "credits with made-up names", "cinematic title card"
**Defaults:** 75 s in the build (30 to 45 s is plenty for most asks) · 2.39:1 letterbox inside 16:9 1920x1080 · 24 fps · music-only
**Kit:** `kits/g11-movie-credits/` holds working code from the 2026-10-28 sample of this style (60 s, reviewed PASS); start from its README.

## The brief (reusable prompt)
Imagine there exists a really good movie about {subject}. Animate the opening credits to this film with made-up names in any style you like. Return the sequence as an mp4. Make each credit animate the way {subject} actually works, and give the film one recurring protagonist object instead of a face.

## Scene plan
| Time | Beat | What happens on screen |
|---|---|---|
| 0-7.6 | Studio card | Fade up from black. An amber cursor blinks, then types the studio name letter by letter (key clicks synced). "presents" blooms in below |
| 8-11.7 | "in association with" | Second studio generated one token at a time: under each slot an autocomplete dropdown shows candidates with probabilities and the picked one rises into the line (one quiet joke: a 0.31 candidate chosen over a 0.34 one, because sampling is not argmax) |
| 12-15.7 | Director card | "a [NAME] film" decoded the same way, glass tick per token commit |
| 16-31.7 | Starring | Dim page of drifting words behind; each lead name lands at a different spot and sends about 34 thin amber threads to words in the field, which light up when reached |
| 30.8-39.8 | Title | Field pushes in with a riser; on the downbeat at 32.0 s (sub boom, low piano cluster) about 1,700 letters from the field fly into the title shape; crisp title resolves over them; cursor blinks after the last letter |
| 40-60.4 | Crew | Left: a bracketed "context window" where lines are typed in, replies stream word by word, lines scroll up and decay into dots above the window. Right: eight crew credits at 2.5 s each |
| 60-68 | Written / directed | Field returns; "directed by" triggers a 170-thread bloom across the frame (climax), then dims |
| 68.5-74 | Film begins | Black. A line is typed ("hi. can I ask you something?"); amber cursor on next line ready to answer; piano plays D-A-F# (resolves to D major). Hard cut to black at 74.0 s on picture and sound together, then 1 s silence |

## Look
- Palette: cream (239,231,218) = #EFE7DA for text, amber (236,166,78) = #ECA64E for cursor and threads, ash (150,140,128) = #968C80 for secondary lines, warm near-black backgrounds (#17130f, #090807), dark halo behind credits (rgba 10,8,7). Word field kept at about 7-10 % opacity.
- Type: Cormorant Garamond 500 for names (tracking 0.22-0.34 em), Cormorant italic for role words, IBM Plex Mono for the machine layer (OFL; on a Mac use Georgia or Baskerville for the serif and Menlo or Courier New for mono if Cormorant is not installed). Main credits 46-188 px.
- Layout and texture: letterboxed 2.39:1, film grain (seeded noise tile scaled 2x, alpha 0.034, screen blend, new each frame), occasional dust specks, plus or minus 1.8 % exposure flicker and gate weave. Keep grain soft: full-resolution grain made a 490 MB master.

## Motion
Names enter with tracking pulling in, a blur that clears and a fade (ease_out_cubic); they leave with a slight widen and blur. Typed text at fixed per-character cadence synced to key clicks. Threads grow from the name to target words over a short ease_out_cubic draw. Particle title: letters sampled from the field fly to target positions on the downbeat. Cursor blinks on a fixed 1 Hz phase. The whole picture is one function of t with seeded random.

## Audio
D minor at 60 bpm (bar = 4 s, so every scene boundary is a bar line). Open-fifth drone, then sparse additive-synthesis piano, then an eighth-note ostinato over Dm, Bb, F, C. Low strings from 24 s, stepped-noise riser plus reversed piano into the title boom at 32.0, soft heartbeat from 48 s. Run-up to climax goes C then A, resolving to D major for the epilogue. SFX from the cue file: key clicks per typed character, glass ticks on token commits, pentatonic glints when threads fire, shimmer cluster for the bloom. Synthetic 3.2 s convolution reverb, look-ahead limiter at -1.8 dBFS. Master -15.3 LUFS in the build (use -14 here). Sync check: RMS jump at 32.0 s and a drop from -25 dB to silence at 74.0 s.

## Build notes
- Reduce to 30-45 s: studio card, one token-decode card, starring with threads, title, one crew block, final typed line.
- Draw each frame on a PIL canvas, crop with black bars to 2.39:1, overlay grain from a pre-generated seeded noise tile shifted per frame.
- Particle title: render the title text to a mask, sample points, and interpolate from field positions with ease_out_expo.
- All names must be made up (studios, director, cast, crew); say so in the delivery note, and note that real people may share them. Probabilities in dropdowns are fictional design, not model measurements. Show no real model or company names.
- Piano: sum of a few decaying sines with detuned partials; reverb by convolving with a decaying noise IR in numpy (check runtime).
- Keep the protagonist object (here a cursor) in every section.

## Pitfalls (from what went wrong in our build)
- Overlapping candidate dropdowns on adjacent tokens: stagger or stack them.
- The word field stayed 2.8x too bright after the title (a rush factor leaked past 32 s): reset effects at scene boundaries.
- A label collided with decaying lines: place labels outside the active area.
- A 0.3 s dead gap before the title hit: hand the field off directly to the particles.
- Oversized master (175 MB) from hard grain: soften grain; also check the encode size.
- Word field reads busy behind the starring names at full size, and dropdown probabilities (15-17 px) and the "context window" label (14 px) are too small on phones: keep the halo, enlarge small type.
- Crew section (8 x 2.5 s) is the most conventional stretch; 75 s is long for a web clip.
- Fonts missing at render time fall back to a system serif or mono: check font paths on the Mac.

## Style QA
- Cut to black and silence land on the same frame.
- Every credit is legible over the field (halo present).
- Cursor appears in every section; off-phase stills are fine.
- Grain changes every frame but stays soft; file size sane.
