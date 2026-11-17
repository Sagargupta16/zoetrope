# S-g04-best-launch · 50 s app launch film
**Source:** @SteeveDor7, https://x.com/SteeveDor7/status/2104027894217572848 · our build: g04-best-launch
**Use when:** "launch video", "app launch film", "best launch video for {product}", "feature tour with a story", "30 to 60 s product film"
**Defaults:** 50 s · 16:9 1920x1080 · 30 fps · music-only
**Spec:** family=launch length=50 size=1920x1080 fps=30 audio=music kit=g04-best-launch
**Kit:** `kits/g04-best-launch/` holds working code from the 2026-10-28 sample of this style (60 s, reviewed PASS); start from its README.

## The brief (reusable prompt)
Create the best launch video for {product}.

## Scene plan
Grid: 96 BPM, beat 0.625 s, bar 2.5 s.
| Time | Beat | What happens on screen |
|---|---|---|
| 0-7.5 | S1 Noise | "You sat down to do one thing." over one task card with blinking caret. From 1.6 s, 22 notification cards pop in faster and faster. "Then everything else showed up." All collapse into one coral point (reverse whoosh), then silence |
| 7.5-12.5 | S2 Reveal | Point becomes the tile, cream square pops in, dot bounces into the doorway (three wood toks), lockup slides over, wordmark wipes in, tagline. Camera zooms into the cream square (match cut into S3) |
| 12.5-20 | S3 Feature 1 | Ring draws "Focus for 25"; 25:00 runs sped up to 00:00 with ring depleting from the same clock function; ring turns mint "Breathe for 5"; chips adjust 25 to 30 |
| 20-27.5 | S4 Feature 2 | Task dragged bottom to top, others make room; two checked off; clock rolls 11:59 PM to 12:00 AM; done tasks leave, unfinished slide up tagged as carried over |
| 27.5-35 | S5 Feature 3 | Toggle switches on, dark circle wipes from the knob; notifications dissolve into specks before the nook; session card ticks 18:42 to 18:35; cream circle wipes back |
| 35-45 | S6-S7 Feature 4, devices | Six day tiles fill mint per beat, counter 1 to 6; dictionary card types the brand's coined word; desktop and phone screens rise in |
| 45-50 | S8 Payoff | The opening task is checked off with small confetti: "One thing. Done." Logo lockup, tagline, feature recap line, final chord |

## Look
- Palette: coral #ff6b4a, plum #2b1b3f, cream #fff6ec, mint #6fd6b5, lilac #cfc4f2. Small-text tints: coral #c9452a, mint #23966f; large display coral #ee5f3f.
- Type: rounded sans (build: Nunito); Mac system rounded sans.
- Layout and texture: dark plum for noise, cream for product, rounded cards.

## Motion
Expo and back eases with a single bounce; no shake or flash except the jitter in the chaos beat. The S2 zoom into the nook scales 1 to 34 in 0.7 s. Timer digits and ring read one clock function so they stay in sync.

## Audio
96 BPM lo-fi: FM Rhodes, sub bass, soft drums, bell, marimba, notification pings. Quiet mode: low-pass sweep 16 kHz to 600 Hz and thin drums, reopening on exit. Each streak day plays the next note of an ascending F-major pentatonic on marimba. -14 LUFS.

## Build notes
Template for any feature-per-scene launch: noise problem, reveal, one scene per real feature, payoff closing the opening. If the user has no screen images, draw device frames in PIL.

## Blocks

The 2.8.0 parts that fit this look (`blocks.md`); pass the card's own colours and fonts, never the module defaults. The kit already holds the noise pile-up, the zoom match cut and the streak tiles; reach for a block only where the kit has none.

- **Text:** `blocks_text.notification(title, body, t0=pop_time, ...)` for the 22 notification cards of S1, generic copy only.
- **Data:** `blocks_data.counter(value=6, start=1, ...)` for the streak counter in S6.
- **Transitions and camera:** `engine.motion_blur(draw, t, samples=6)` for a new fast move; `engine.wobble(t, amp=..., hz=..., seed=...)` only for the S1 jitter (the card allows no shake or flash elsewhere).
- **Gates:** `brand.json` with the product's palette and rounded sans, then `python brand.py check`.

## Pitfalls (from what went wrong in our build)
- Rolling numbers sat above the label baseline: align roll boxes to the text baseline.
- The panel looked empty after items left: add an "Add a task" row and footer.
- Zoom and card collapse looked steppy at 30 fps: blend frames (the kit does; `engine.motion_blur` is the engine's version). No call to action, as nothing real existed to point to.

## Style QA
- Every feature claim is one the user confirmed.
- Quiet-mode filter audibly muffles and then reopens.
