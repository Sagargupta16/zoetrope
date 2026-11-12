# S-g05-logo-animation · Elastic logo sting with shape morphing
**Source:** @mr_igor_sanz, https://x.com/mr_igor_sanz/status/2104000986981486650 · our build: g05-logo-animation
**Use when:** "logo animation", "logo sting", "animate our logo", "elastic bounce", "morphing shapes", "logo reveal with tagline"
**Defaults:** 8.5 s · 16:9 1920x1080 · 60 fps in the build (30 fps here) · music and sound design, no voice
**Spec:** family=logo length=8.5 size=1920x1080 fps=30 audio=music kit=-

## The brief (reusable prompt)
Build me a good logo animation with {brand}. Use cool motion, shapes, morphing and elastic easing. The mark is a tile with a cut corner and a dot (swap for the user's own mark); the animation is the dot's story: it drops in, the world shapes itself around it, it carves its own nook, spells the name, and comes home.

## Scene plan
| Time | Beat | What happens on screen |
|---|---|---|
| 0.00-0.53 | Drop | Dot falls (gravity ease, velocity stretch), squashes on landing, crouches |
| 0.50-0.95 | Bloom | Mint circle springs out from under the dot (elastic out) and catapults it off-screen |
| 0.95-1.85 | Morph chain | Circle, rounded triangle, 6-lobe flower, rounded tile, each with a 120, 60, 90 degree twist; colour mint, lilac, plum, coral. Each hit throws brand-shape confetti and a shock ring |
| 1.85-2.40 | World | Four soft background blobs pop in and keep morphing slowly; cream square grows inside the tile |
| 2.50-2.95 | Carve | Dot falls back in an arc and hits the square corner; impact morphs the corner into a quarter-circle doorway; tile squishes (damped spring); a ring ripples |
| 3.45-4.40 | Lockup | Anticipation (lean right, swell), then an elastic whip left and down to the lockup position with a hop arc |
| 4.05-5.12 | Spell | Dot hops across the baseline; each letter springs up out of the floor to meet it (stretch tall, then settle) and squashes as the dot lands |
| 5.12-5.74 | Home | Big slide-whistle arc back into the doorway, squash, tile squish, small confetti burst upward |
| 5.90-6.60 | Tagline | Words rise with a calm power3-out ease (no elastic on text) |
| 6.60-8.50 | Hold | Slow 2.2 % push-in, blobs breathing, one small hop of the dot at 7.3 s |

## Look
- Palette: cream #FFF6EC background, plum #2B1B3F, coral #FF6B4A, mint #6FD6B5, lilac #CFC4F2, soft tints (#FFFCF7, #FFE4DB, #FCEBDC, #EFEAFB, #DDF5EC). Tagline accent word uses deeper coral #E5553A (3.45:1 on cream) because #FF6B4A is only 2.6:1 and fails large-text contrast; shapes keep the true coral.
- Type: Nunito 800, tracking -16/1000, one baseline (rounded sans substitute on a Mac). Tagline in the same family.
- Layout and texture: centred lockup, soft blobs behind, no grain. The final frame must match the brand's own logo file.

## Motion
Every move is a spring. Morphing: resample each shape to 480 points by arc length, start at 12 o'clock, wind clockwise, then interpolate; elastic easing extrapolates past the target so shapes overshoot like jelly instead of cross-fading. Overlapping morphs hand off from the live interpolated shape (no pop). Elastic settles: out(1, 0.35) to out(1.15, 0.32) style spring (overshoot about 1.0-1.15, period about 0.3-0.4). Dot stretch follows measured velocity (finite difference of the position function); squash is a damped spring at each contact; crouch before take-off. Elastic everywhere except text and colour: elastic colour overshoots into off-palette hues, elastic text looks frantic. Every pixel is a pure function of t.

## Audio
Sound follows the picture from one cue sheet. Morph hits are boings whose pitch wobble mimics the elastic settle; the six letter landings play a rising C major pentatonic marimba line (C5 D5 E5 G5 A5 C6), panned to each letter's position; home lands on a C add9 bell chord over a pad moving Cmaj9, F/A, C add9. Slide-whistle on the home arc. Master -14.6 LUFS, -1.8 dBTP (build, tanh saturation and static gain, no limiter).

## Build notes
- Draw shapes as polygons from the 480-point arrays with PIL ImageDraw at 2x supersample, then downscale.
- Build a `spring(t, overshoot, period)` easing helper in numpy and use it for scale, position and morph progress.
- Per-letter animation: render each glyph with ImageFont to its own RGBA layer, then scale Y and X independently (stretch tall, squash wide).
- Confetti: seeded random, positions computed from t only.
- If the user has no logo file, ask for it or draw a simple mark from shapes; keep the final frame equal to the supplied mark.
- Synthesize boings (sine with falling pitch plus wobble), marimba (sine with fast decay) and a whistle (swept sine) in numpy.

## Pitfalls (from what went wrong in our build)
- Cartoony boings and slide whistle may feel too cute for a calm brand: lower the boing gains.
- Letters are thin slivers for 1-2 frames as they start (a speck at 4.20 s); the dot is a wide ellipse when squashing into the doorway; mint-to-lilac blend reads dusty blue for about 0.1 s at 1.0 s. Acceptable in motion; hold min letter height or blend in a better colour space if stills matter.
- Confetti passed behind the tile and looked like bumps (coral pieces especially); plum and mint bits still crossed the tile top edge around 5.9-6.1 s. Skip coral confetti and keep pieces off the tile.
- Two waits felt static: the mint circle at 0.6-0.95 s and the empty cream square at 2.4-2.5 s. Add a ring or secondary motion.
- Small background pebbles wobbled enough to look like rocks: keep wobble gentle or make them larger.
- Mixed by meters, not by ear.

## Style QA
- Final frame matches the supplied logo exactly (geometry, colour, wordmark).
- No elastic on tagline or colour; tagline contrast passes for large text.
- Sample stills at 1.0, 3.0, 6.0 s and a few between each hit.
- Letter landings line up with the marimba notes.
