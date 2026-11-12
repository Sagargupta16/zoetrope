# S-g07-research-40s · Product showreel with technique HUD
**Source:** @ajith_io, https://x.com/ajith_io/status/2103469807375208546 · our build: g07-research-40s
**Use when:** "research the brand and make a 40-second motion graphics video", "showreel for our product", "go all out", "show every feature in motion", "dynamic product film with no voice"
**Defaults:** 40 s · 16:9 1920x1080 · 60 fps in the original (30 fps is fine here) · music-only
**Spec:** family=explainer length=40 size=1920x1080 fps=30 audio=music kit=-

## The brief (reusable prompt)
Research {brand} (read the brand folder or the user's material, do not invent facts). Make a dynamic 40-second motion graphics video on {brand} that shows what an incredible motion designer you are, like a showreel. Go all out. Use only real features and sample content from the brand material.

## Scene plan
| Time | Beat | What happens on screen |
|---|---|---|
| 0-3.9 | 01 Construction | Blueprint on a drafting-paper grid: guides, tile, corner arcs, dot, dimension lines and anchor points draw on; fills snap in; the dot drops with squash and stretch on the first downbeat; wordmark letters spring up. Hand-off: camera rushes into the dot (scale x72) |
| 3.9-8.0 | 02 Kinetic type | Tagline on the beat with scale contrast (huge word, tiny word), letters drop and bounce, a sun arcs over the line and lands as the full stop. Hand-off: full stop opens as a colour iris |
| 8.0-13.4 | 03 Feature A (timer) | Ring draws on, countdown as a true odometer (each column rolls with carry), comet sparks off the ring head, pulse at zero, ring splits into two arcs, four taps change a value |
| 13.4-20.1 | 04 Feature B (calm mode) | 18 generic notification cards pile up faster and faster with a jitter; a toggle flips and a shockwave blows them off; calm breathing rings and dust. Music goes muffled |
| 20.1-26.1 | 05 Feature C (list) | Cards drop in, a cursor drags two to reorder with spring physics, one is checked off with confetti, midnight rolls over, unfinished cards flip and return labelled as carried over |
| 26.1-31.8 | 06 Feature D (streak) | 4-week calendar cascades in, days fill in date order with a marimba note each, counter climbs and gently rolls back on rest days |
| 31.8-36.6 | 07 Coined word | Perspective wall of the real UI screens scrolls in alternating rows, dims, then the brand word and its definition set word by word |
| 36.6-40.0 | End card | Mark springs in, dot drops again, wordmark, tagline, four feature pills, slow push-in, final chord |

## Look
- Palette: coral #FF6B4A, plum #2B1B3F, cream #FFF6EC, paper #FFFCF7, mint #6FD6B5, lilac #CFC4F2, soft tints #FFE4DB, #DDF5EC, #EFEAFB, text tones #C9452A, #1F7F60, #6E5F80. Swap for {brand} colours.
- Type: one rounded sans (the build used Nunito, wordmark weight 800, tracking -16/1000). Mac substitute: Avenir Next Rounded or Arial Rounded MT Bold.
- Layout and texture: small HUD frame (crop marks, chapter roll such as "03 / 07 FEATURE NAME · technique", live timecode, 16-step beat meter), colour-matched to each background. HUD captions were 15 px: texture only.

## Motion
Every chapter is one skill and one feature. Every cut is a designed hand-off built from the logo's own shapes (dot, circle, rounded square): zoom into the dot, iris open from the full stop, shrink to a point then iris, a tile grows to fill the frame, tiles flip in diagonally, camera flies through the cutout. Use springy back and bounce eases (ease_out_back) and squash and stretch on the dot. No flashes or camera shake except the deliberate jitter while notifications pile up. Odometers and counters are pure functions of t (digits roll with carry). Particles from a seeded RNG.

## Audio
120 BPM (beat 0.5 s, bar 2 s, 20 bars = 40.0 s), F major, chords F, Dm9, Bbmaj9, C6/9. FM Rhodes, sub bass, soft house kit (kick, clap, shaker, hats), marimba motifs, bells, plucks, reverb, kick sidechain on the music bus. Cue-locked SFX: pencil ticks per drawn line, a drop on the dot landing, pitched toks per letter bounce, a sun glissando, minute ticks computed from the same curve as the odometer, panned notification pings, a sub whoomp plus low-pass on the music for the calm section, a two-note midnight bell, one marimba note per streak day (pitch rises with the run), final chord on the end-card dot landing. No voice. Target -14 LUFS, true peak under -1 dBTP (original reached -14.1 LUFS, -2.6 dBTP).

## Build notes
Draw each chapter as a function of t in PIL with a SCHEDULE of the eight times above. Hand-offs need a shared shape: render the next scene full-frame and mask it with a growing circle or rounded rectangle. Odometer: draw each digit column with a vertical offset. The 3D wall and 3D card flip are hard: use a pseudo-3D horizontal squash (scale x by cos of angle) and skewed rows. Supersample 2x for thin construction lines. Only use features and sample content the user supplied; if no brand folder exists, ask the user or use clearly generic placeholder content. Notification apps stay generic (Group chat, Mail, Shop), never real brands. Recommend 30 fps.

## Pitfalls (from what went wrong in our build)
- 3D card flip around 24.9 s looked warped in stills (perspective stacked on the card y-offset). Keep flips simple and test mid-flip frames.
- Mask-roll headline swaps and odometer rolls show half-cut words or digits in stills (about 11.4 s and 12.4 s). Judge them in motion, not in a single proof frame.
- The calm section is intentionally 5 to 8 dB lower and the 36 s riser is quiet; check overall level.
- HUD captions at 15 px are unreadable on a phone. Use 24 px or more if the target is mobile.
- Audio was mixed by meters, not by ear; say so.

## Style QA
- Every on-screen number is a real feature fact or the user's sample data; no invented counts, ratings, prices or awards.
- Each hand-off uses a brand shape and lands on a beat.
- Resting frames at each chapter midpoint show no clipped or overlapping text.
