# S-g01-intro-masterpiece · Brand intro, "a loud day, then a quiet nook"
**Source:** @BogdanDragomir, https://x.com/BogdanDragomir/status/2104045641538412658 · our build: g01-intro-masterpiece
**Use when:** "intro for our product", "show what it does", "portfolio masterpiece", "music-synced brand film", "feature tour with a logo reveal"
**Defaults:** 45 s · 16:9 1920x1080 · 60 fps in the build (use 30 fps here) · music-only, type does the talking
**Spec:** family=logo length=45 size=1920x1080 fps=30 audio=music kit=-

## The brief (reusable prompt)
Create an intro for {product} highlighting what it does. Create the music too and make sure the video is synced with it. Give your best, as if it is your portfolio masterpiece. Keep on-screen claims to the facts the user supplies (features, tagline); no metrics, prices or ratings unless given.

## Scene plan
| Time | Beat | What happens on screen |
|---|---|---|
| 0.0-5.0 | Noise | Headline "Your day gets loud." 18 generic notification cards pop in (one per beat, then 8ths, then 16ths); buzz cards shake, a counter climbs, camera pushes in and jitters |
| 5.0 | Hush | Logo tile lands with the mark dot on it; every card blows outward; all sound cuts |
| 5.6 | Promise | "Find your nook." (replace with the product promise) |
| 7.5 / 8.1 / 8.75 / 9.4 | Mark builds | Square pops in, doorway carves open, dot hops into it, lands with a squash |
| 10.0 | Drop | Mark snaps into the lockup; wordmark letters spring up on 8th notes |
| 11.25 / 12.5-13.4 | Tagline, chips | Tagline word by word; four feature chips pop on 8ths |
| 14.4-15.0 | Dive | Camera dives into the logo shape |
| 15.0-20.0 | Feature 01 | Live demo of the feature (a ring time-lapse); at 17.5 colour shifts to mint with a one-line caption; two option chips tapped at 18.75 and 19.06 |
| 20.0-25.0 | Feature 02 | Four list rows land on 8ths; one row lifted at 21.9 and dropped on top at 22.5; two ticked at 23.1 and 23.4; clock flips at 23.75; done rows fold away, others slide up tagged "Carried over" |
| 25.0-30.0 | Feature 03 | Six day tiles fill on 8ths, counter rises to 6; pops with sparkles at 27.5 |
| 29.4-35.0 | Feature 04 | Plum wipe; mark in a halo; five notifications fly in and are hushed into small lilac dots that orbit; caption line |
| 35.0-39.4 | Montage | Dive out into real UI screens on a 3D tilted wall: four short lines, cut every half bar |
| 40.0-45.0 | End card | Lockup lands, letters on 16ths, tagline at 40.6, dot hops at 41.25 and lands at 41.56, four feature labels at 42.5, fade to cream from 44.4 |

## Look
- Palette: coral #FF6B4A (primary), plum #2B1B3F (ink), cream #FFF6EC (background), mint #6FD6B5 (success), lilac #CFC4F2 (secondary). The "other apps" notifications use muted generic tones (#8FA3C7, #7FB0A0, #D8B25A, #D88C7A, #9A8CC8, #8C9AA8) and generic copy, so the brand colours belong to the product only.
- Type: Nunito 800 for the wordmark (OFL; use any rounded sans on a Mac, for example Arial Rounded MT Bold from /System/Library/Fonts or /Library/Fonts) and a plain sans for captions.
- Layout and texture: flat colour fields, one soft colour glow behind each feature card (coral, mint, lilac, mint). Secondary labels were 21-25 px and too small on phones: use 32 px or larger.

## Motion
Springy overshoot (ease_out_back) for anything the brand touches; ease_out_expo for camera moves; accelerating power-in for exits. Jitter only in the chaos section. The camera flies through the logo shape twice (14.4 s and 34.4 s) so each new section starts inside it: scale the shape up to roughly 34x to 46x (the build needed 46x to hide a coral edge on the last frames). Each feature gets two bars (5 s). All cue times come from one dict; no state between frames, seeded random for jitter.

## Audio
96 BPM, F major, 18 bars = exactly 45.000 s (beat 0.625 s, bar 2.5 s). Chord loop Fmaj9, Dm9, Bbmaj9, C9sus4. Instruments: electric piano, warm pad, round sine bass, soft kick with sidechain duck on the music bus, clap, swung shaker, hats, kalimba and marimba melodies, bells. SFX on the same cue as the picture: ping or phone buzz per card, clock tick per beat, riser into 5.0, then total silence and a low wooden thock plus one warm Fmaj9 chord at the hush; pops, scoops, whooshes before cuts. Breakdown at 29.4-35.0: drums out, low-passed keys, heartbeat kick, one muffled thup per hushed notification, snare build. Final chord Fmaj9 with added 9/13 and impact, fade-out from 43.6. Master to -14 LUFS (build measured -14.0 LUFS, -3.0 dBTP).

## Build notes
- Write a `CUES` dict first (hush 5.0, drop 10.0, feature changes 15/20/25/29.4, montage 35, end 40) and drive both `draw(t)` and the numpy audio from it.
- Draw the mark with PIL polygons and ellipses (tile, quarter-circle cut, dot). Draw notification cards as rounded rectangles with generic text.
- The 3D tilted wall is hard: fake it with a perspective transform (PIL Image.transform with QUAD) on the user's own screenshots, or use a flat slide with parallax. If no UI screenshots exist, draw simple card mockups.
- No narration, so no voice is needed.
- Use only facts the user supplied; do not add sync, availability, price or user-count claims.

## Pitfalls (from what went wrong in our build)
- Music was mixed by meters only: it came out slightly bass-heavy (most energy under 120 Hz) and the synth keys sounded simple. Cut kick and bass by 1-2 dB and brighten the keys.
- At 5.0-5.3 s the tile popped in over the fading headline for about 0.3 s: fade the headline out before the tile lands.
- At 8.9-9.3 s the dot overlapped the doorway edge mid-hop; at 38.8-39.2 s the 3D wall screens overlapped semi-transparently. Check those frames.
- Headline was hidden under notification cards (stacking order) and two cards overlapped the counter pill: draw the headline last and keep cards off the counter.
- Late body lines in each feature were on screen only 1-2.5 s: bring them in earlier.

## Style QA
- Silence at 5.0 s is real (audio cut to zero) and the tile lands on that exact frame.
- Every cue in the dict has a matching audio onset within about 2 frames.
- Only the user's claims appear on screen; no metrics or prices.
- Contact-sheet check at 5, 10, 15.5, 22.3, 27.6, 32, 36.8, 41.4 s.
