# Producer playbook

How we make a video, start to finish, with the tools we really have (see `engine.md`: PIL frames, numpy audio, ffmpeg). Follow the order. Never skip an approval gate.

## 1. The workflow

1. **Brief (max 3 questions, one message).** (a) Purpose and audience: what must the viewer believe or do? (b) Length, aspect and where it plays (Slack, LinkedIn, deck, signage). (c) Audio: music only, voiceover (a text-to-speech voice, `voice.md`), both, or silent. If the user already answered something, do not ask it again. State any default we assume.
2. **Style pick.** Use the style router. Offer 2 to 3 styles with one line each (mood, palette, type), recommend one, and move on if the user says "you choose".
3. **One-sentence message.** Write the single sentence the viewer must believe, plus the before and after. If we cannot say it in one sentence, the brief is not ready.
4. **Script.** One idea per beat. English scenes carry about 3 to 7 words of on-screen text. Voiceover: write it to be spoken, numbers as spoken words. Muted test: the arc must read with sound off.
5. **Storyboard table + approval gate.** Run `qa.py holds <scenario.md>` first and fix every SHORT line, then show a beat sheet and wait for "go".

   | Time | On screen | Visual form | Purpose | Transition in |
   |---|---|---|---|---|

   Rules: every row names one purpose (cut or merge rows that cannot); every payload row names a visual form that passes the squint test (remove the words: does the shape still say something? a bar chart passes, three boxed stat cards fail); note what carries continuity across each cut. Never print internal phase names (hook, develop) in the table the user sees.
6. **Assets.** Palette and fonts from the style, shapes drawn in code, user-supplied images loaded from disk. No downloaded music or footage. Credit anything third party.
7. **Build.** Write `scenes.py` (`engine.md`). One `SCHEDULE`, one pure `draw(t)`.
8. **Audio.** Voice first (measure its length), then music on a BPM grid, SFX on the cuts, mix (`mixing.md`).
9. **Proof frames + approval gate.** Render 6 to 12 stills (scene midpoints and boundaries), show them as one contact sheet in a session tab, fix layout, then ask for approval. Fix before the full render, never after.
10. **Full render** of every frame, then encode (ladder in `engine.md`).
11. **QA.** Check frame count x fps = duration, spot-check 5+ frames (first, each cut, last), text not clipped, no element overlapping at rest, loudness and peak. Fix and re-render if any check fails.
12. **Deliver.** Report per `formats.md` and `delivery-report.md`.

## 2. Timing math

- **Voiceover pieces:** generate the voice first, measure its real length (ffprobe), then schedule. Scene length = spoken length of its line + a hold (about 0.4 to 0.8 s for breath and landing). Total = sum of scenes. Voices differ in pace (one voice speaks about half as fast as Matthew), so never guess duration from word count.
- **Music-only pieces:** pick a BPM, then everything snaps to the grid. Beat = 60 / BPM seconds. Bar = 4 beats. Cuts land on bars (downbeats), UI hits and text lands on beats. Worked example at 120 BPM: beat 0.5 s, bar 2.0 s, 10 bars = 20 s. Pick a BPM and a bar count whose product is the target length (at 120 BPM a 15 s piece is 7.5 bars, so use 8 bars = 16 s or trim the tail).
- **Reading time:** on-screen text holds at rest for at least 0.5 s + 0.3 s per word, and never under 1 s (the same rule gate 4 in `qa-gates.md` checks). A headline wants 1.5 to 2.5 s. A key element must stay readable at least 0.3 s. If copy does not fit the hold, cut copy.
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

- **Durations:** fast 0.15 to 0.3 s (energy), medium 0.3 to 0.5 s (most content), slow 0.5 to 0.8 s (gravity), very slow 0.8 to 2.0 s (cinematic). The slowest scene should be about 3x the fastest. Entrances are longer than exits (about 0.4 s in, 0.25 s out).
- **Vary on purpose:** no more than 2 independent moves with the same ease per scene; vary direction (left, right, scale, opacity only); vary stagger per scene.
- **Stagger:** between groups 0.15 to 0.4 s; inside a group 0.05 to 0.1 s; a single group's whole sequence under about 0.5 s. Stagger by importance and gaze path.
- **Scene shape:** build (first 30%), breathe (30 to 70%, one ambient motion), resolve (last 30%, decisive exit). Hold still after motion; stillness is powerful.
- **Camera:** push in 1.00 to 1.04 per shot, origin on the subject. Establish wide, then push in. Two-layer parallax (background slower than foreground) adds depth. Never reveal empty canvas at the edges.
- **Transitions are meaning.**
  - Text: never crossfade two strings in the same spot. Fade the old one out, then the new one in (gate Q203 catches it).
  - Cut: disruption, "wake up", a register shift. Land it on a downbeat.
  - Crossfade (0.3 to 0.5 s): "this continues".
  - Slow dissolve (0.8 s+): "drift with me".
  - Wipe: a reveal or a change of state (color wipe across a word).
  - Push: moves the next item in from the side the story is heading; good for stat sequences.
  - Zoom-through: scale the old scene up past the camera and land the new one from small; for entering a screen or a detail.
  - Match cut: carry one shape, color or position across the cut (a button center becomes the next scene's circle). Strongest transition; use it once or twice.
- **Don't:** same ease everywhere, same entrance on every item, ambient zoom on every scene, a static element beside animated ones.
