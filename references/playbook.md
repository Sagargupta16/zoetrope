# Producer playbook

How we make a video, start to finish, with the tools we really have (see `engine.md`: PIL frames, numpy audio, ffmpeg). Follow the order. Never skip an approval gate.

## 1. The workflow

1. **Brief (max 3 questions, one message).** (a) Purpose and audience: what must the viewer believe or do? (b) Length, aspect and where it plays (Slack, LinkedIn, deck, signage). (c) Audio: music only, voiceover (a text-to-speech voice, `voice.md`), both, or silent. If the user already answered something, do not ask it again. State any default we assume.
2. **Style pick.** Use the style router. Offer 2 to 3 styles with one line each (mood, palette, type), recommend one, and move on if the user says "you choose".
3. **One-sentence message.** Write the single sentence the viewer must believe, plus the before and after. If we cannot say it in one sentence, the brief is not ready.
4. **Script.** One idea per beat. English scenes carry about 3 to 7 words of on-screen text. Voiceover: write it to be spoken, numbers as spoken words. Muted test: the arc must read with sound off.
5. **Storyboard table + approval gate.** Run `qa.py holds <scenario.md>` first (with `--profile caption` or `slow` when the card reads at that pace) and fix every SHORT line, then show a beat sheet and wait for "go".

   | Time | On screen | Visual form | Purpose | Transition in |
   |---|---|---|---|---|

   Rules: every row names one purpose (cut or merge rows that cannot); every payload row names a visual form that passes the squint test (remove the words: does the shape still say something? a bar chart passes, three boxed stat cards fail); note what carries continuity across each cut. For a piece with a camera or a character, Visual form also names the framing and the move (section 5). Never print internal phase names (hook, develop) in the table the user sees.
6. **Assets.** Palette and fonts from the style, shapes drawn in code, user-supplied images loaded from disk. No downloaded music or footage. Credit anything third party.
7. **Build.** Write `scenes.py` (`engine.md`). One `TIMELINE`, one pure `draw(t)`, and the registry: `text_items(t)` for every text drawn and `CUES` for every moment sound and picture share (`qa-gates.md`). Read `python kit_index.py` before writing a helper.
8. **Audio.** Voice first (`voice.synthesize`; the slots in `narration.json` size the scenes), then music on a BPM grid, SFX on the cuts placed by their landmark inside `synth.recording()`, mix (`mixing.md`, `beat-sync.md`).
9. **Proof frames + approval gate.** `run_all.py proof` runs the proof gates and writes `proof.png` (up to 12 stills) and `proof_keys.png` (every moment a reviewer must see). Fix every FIX and NOT CHECKED row, show the sheets in a session tab, fix layout, then ask for approval. Fix before the full render, never after.
10. **Full render.** `run_all.py full` draws every frame into the encode, makes and masters the audio, muxes and runs every gate (ladder in `engine.md`).
11. **QA.** The run ends with one `DELIVERED` line, or a `<name>.rejected.mp4` and the rows that failed. Spot-check the frames in `review_times.json` (first, each cut, last, every finding), text not clipped, no element overlapping at rest, loudness and peak. Fix and run again: an audio-only fix is `run_all.py audio` (no frame redrawn); a visual fix redraws every frame unless the build kept them (`--keep-frames --redraw T0-T1`).
12. **Deliver.** Report per `formats.md` and `delivery-report.md`, quoting the `DELIVERED` and `APPROVAL` lines. After the final REVIEW PASS, save the reviewer's reply to a file and run `qa.py approve --review <reply file>`; before delivering, `qa.py verify <the DELIVERED path>` must say SAME. A change after that: `qa.py diff --expect <its windows>` names every frame it touched, for the re-review.

## 2. Timing math

- **Voiceover pieces:** run `voice.synthesize` first; `narration.json` gives each line's measured slot (the speech plus 0.35 s before and 0.7 s after, never under the reading hold, on whole frames). Scene length = its line's slot; total = sum of slots. Voices differ a lot in pace, so never guess duration from word count.
- **Music-only pieces:** pick a BPM, then everything snaps to the grid. Beat = 60 / BPM seconds. Bar = 4 beats. Cuts land on bars (downbeats), UI hits and text lands on beats. Worked example at 120 BPM: beat 0.5 s, bar 2.0 s, 10 bars = 20 s. Pick a BPM and a bar count whose product is the target length (at 120 BPM a 15 s piece is 7.5 bars, so use 8 bars = 16 s or trim the tail).
- **Reading time:** on-screen text holds at rest for at least 0.5 s + 0.3 s per word, or its characters at the card's pace plus a pad when that is longer (display 20 a second, caption 17, slow 15; `house-rules.md` rule 8), and never under 1 s: the rule gate 4 in `qa-gates.md` checks. A headline wants 1.5 to 2.5 s. A key element must stay readable at least 0.3 s. If copy does not fit the hold, cut copy.
- **Pacing:** pattern-interrupt (change exactly one thing) if a shot runs longer than about 2.5 s. Keep something always moving (slow drift) so holds do not look frozen.
- **Length presets (guide, not law; about 3 s per scene):**

  | Length | Scenes | Shape |
  |---|---|---|
  | 6 s | 2 to 3 | hook, one payload, sign-off |
  | 15 s | 4 to 6 | hook, setup, 2 payload, close |
  | 30 s | 8 to 10 | hook, setup, 3 to 5 payload, payoff, close |
  | 60 s | 15 to 20 | full arc, one section per sentence of the message |
  | 90 s | 25 to 30 | full arc; add a recap beat; voiceover strongly advised |

  Density curve: sparse at the edges, richest in the middle (largest share of time on the payload), calm close.

## 3. Scene planning and composition

- **Hook in the first 1.5 s.** Frame 0 is the thumbnail: the hook line or main visual is already fully drawn on it and only the extras animate in (gate 5 in `qa-gates.md` fails a dark or empty frame 0). First motion by about 0.5 s. Lead with the claim, the pain or the surprising number, never a logo.
- **One idea per scene.** If a scene needs a sentence to explain it, split it. A beat that could be a bullet is not shown yet: make it a chart, a mockup in a device frame, or a diagram that builds.
- **Visual variety.** Pick the form from the shape of the idea: compare = bars; part of whole = segmented bar or ring; change = old value, arrow, new value; progress = gauge; trend = sparkline; process = connected nodes; product = UI mockup; one claim = big type. Do not use the same layout twice in a row.
- **Build, then reveal.** Establish the container (frame, axes, panel) first, then fill it. Connectors draw in. A label animates with or after its anchor, never before. Every meaningful element gets an entrance; the only static element is the deliberate anchor.
- **Gaze path.** Reveal in the order the eye should travel; group what is read together and land the group as one; stagger between groups.
- **Frame.** At least 2 focal points, 3 layers (background treatment, content, accents such as rules). No empty flat black. Hero text 60 to 80% of width. Pick one alignment system per scene (centered, left, or split). Elements never overlap at rest.
- **Safe areas.** Keep text at least 4% of the width from every edge (one preset in our library uses a 4% edge pad; a tight poster style uses 3%). 9:16: platform buttons and captions sit near the bottom and right edges and the top bar covers the top, so keep key text in the middle band and away from those edges. 16:9: keep titles and logos off the outer margin. Check on the proof sheet.
- **Type sizes at 1080p.** Think poster, not web page: a past news layout used a 96 px headline, about 38 px supporting line and about 30 px date, and treated about 30 px as the smallest text. Small text vanishes in motion and in screen recordings, so cut copy rather than shrink it. Scale sizes by frame height for other presets.
- **Contrast.** Big confident type, high contrast, a scrim or vignette behind text over busy imagery. One accent color, used sparingly. Never mid-tone text on a mid-tone background.
- **Palette example from past work (swap for the style router's palette):** cream #FFF6EC with plum ink #2B1B3F and accent #FF6B4A; near-black #0E0B12 for the dark world; highlighter #FFE14D on near-black ink for a loud single moment.

## 4. Motion principles

Easing is the adverb: the same move reads confident (expo out), dreamy (sine in-out) or playful (back/elastic). Direction rule: **out to enter, in to leave, in-out to travel between positions.**

| Use | Easing function | Feel |
|---|---|---|
| Enter, default | `ease_out_cubic` | responsive |
| Enter, hero or confident | `ease_out_expo` | fast then settles |
| Enter, playful | `ease_out_back` | small overshoot |
| Travel, camera, morph | `ease_in_out_cubic` | smooth |
| Exit | `ease_in_cubic` | accelerates away |
| Mechanical (progress, scrub) | `linear` | neutral |
| Physical settle | `spring(t, stiffness, damping, mass)` | Remotion's spring: the default overshoots to 1.163; `damping=200` settles with no bounce; `settle_time()` says when it is at rest |

- **Durations:** fast 0.15 to 0.3 s (energy), medium 0.3 to 0.5 s (most content), slow 0.5 to 0.8 s (gravity), very slow 0.8 to 2.0 s (cinematic). The slowest scene should be about 3x the fastest. Entrances are longer than exits (about 0.4 s in, 0.25 s out).
- **Vary on purpose:** no more than 2 independent moves with the same ease per scene; vary direction (left, right, scale, opacity only); vary stagger per scene.
- **Stagger:** between groups 0.15 to 0.4 s; inside a group 0.05 to 0.1 s; a single group's whole sequence under about 0.5 s. Stagger by importance and gaze path.
- **Scene shape:** build (first 30%), breathe (30 to 70%, one ambient motion), resolve (last 30%, decisive exit). Hold still after motion; stillness is powerful.
- **Camera:** push in 1.00 to 1.04 per shot, origin on the subject. Establish wide, then push in. Two-layer parallax (background slower than foreground) adds depth. Never reveal empty canvas at the edges.
- **Transitions are meaning.** Declare one as `Transition(kind, dur)` between two scenes in `TIMELINE` and draw its window with a `transitions.py` function (crossfade, wipe, push, slide, iris, clock, blinds, dip, luma); a dip is flash_risk "check", so run `qa.flash_window` over it.
  - Text: never crossfade two strings in the same spot. Fade the old one out, then the new one in (gate Q203 catches it). A text replaced in one place leaves 1 empty frame, or 0.5 s or more (Q207, Q1104): a title kept out of a 0.4 s transition leaves 13 frames, so with a transition under 0.5 s put the incoming title in another place, or keep the place clear for 0.5 s.
  - Cut: disruption, "wake up", a register shift. Land it on a downbeat.
  - Crossfade (0.3 to 0.5 s): "this continues".
  - Slow dissolve (0.8 s+): "drift with me".
  - Wipe: a reveal or a change of state (color wipe across a word).
  - Push: moves the next item in from the side the story is heading; good for stat sequences.
  - Zoom-through: scale the old scene up past the camera and land the new one from small; for entering a screen or a detail.
  - Match cut: carry one shape, color or position across the cut (a button center becomes the next scene's circle). Strongest transition; use it once or twice.
- **Don't:** same ease everywhere, same entrance on every item, ambient zoom on every scene, a static element beside animated ones.

## 5. Directing

A piece is judged in this order: sound, rhythm, camera, performance. A good-looking frame is only where it starts. These came from lemo-opuscar's director guide (MIT, read 2026-11-10), put in our words and measured against our own builds.

- **Three shapes before one.** Before the storyboard, write three candidate structures in a line each (a journey, a before and after, a countdown, a list that turns, a question and its answer), pick one and say why. The first idea for a style is usually its cliché.
- **One subject, one want, one turn.** Someone or something wants something, it changes, and the end answers the opening: the same frame changed, the scale revealed, the thing done right the second time.
- **A benchmark.** Name one or two works that set the bar for this style and this topic. Write what to learn from them (framing, pace, colour logic, how the score is built) and what not to take (characters, designs, melodies, shots, logos, type).
- **One move only this style can make,** at the peak: the fold that becomes the cut, the counter that glitches, the star that lights the face that catches it.
- **Every shot has a reason.** Each storyboard row names its framing (wide, full, medium, close, insert) and its camera move, and what that says. A piece over 20 s uses four or more different moves and has one shot people remember. 2D has a camera too: push, pull, parallax, a frame inside a frame.
- **The subject is big.** At a key moment it fills a third of the frame height or more, with a clear silhouette, away from the edges. The first staging of the 3D pilot had its character at a fifth in three scenes of five.
- **A sound table.** Per scene: the bed (room, air, a drone), the sound of each visible action, and what the music does. Every action the viewer sees has a sound, in the material it is made of, and each is a `CUES` entry so Q902 measures it.
- **Two silences.** Take the music away, or nearly, before the turn and before the peak. The first sound after a silence is one of the most important in the piece. Once at least, let the next scene's sound start before its picture.
- **Pace changes.** One clear speed-up or slow-down and one breath (a held shot). Fast means fewer words on screen, never a line cut before it is read.
- **Performance.** Eyes first, then the body. Anticipation, the action, follow-through. Blend between poses with an ease; never switch one inside an `if`. Check faces at final size: worried and angry are one eyebrow apart.
- **What follows a subject uses one world-to-screen function** (a 3D plate's `PLATE.at`, or the scene's own layout function), never coordinates typed by hand, so a label stays on its subject when the camera moves.
- **One fix round.** Fix everything a review found in one round, then check once. Notes after delivery are new rounds: change only what was asked.

Seen most often: the subject too small or against an edge; a colour on the same colour; a caption over the subject; a gag too quick to read; an empty frame inside a transition.
