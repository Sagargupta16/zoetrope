# S-deep-dive · Narrated deep dive over photo plates
**Source:** our own card, written 2026-11-16 from the facts.in.motion Reel batches · no kit yet
**Use when:** "documentary deep dive for Reels", "narrated vertical film over one minute", "long narrated fact Reel with real-looking pictures", "explain one big fact over photos and maps", "realistic pictures with drawn graphics on top"
**Defaults:** 60 to 90 s for a first cut, up to 180 s · 9:16 1080x1920 · 30 fps · Kokoro narration over a recorded-instrument score and ambience
**Spec:** family=explainer length=60-180 size=1080x1920 fps=30 audio=voice kit=-

## The brief (reusable prompt)
Make a narrated documentary deep dive about {one surprising fact}, as a vertical Reel of {60 to 90} seconds. Open on the surprise already drawn on frame 0. Then tell it in 8 to 12 spoken lines, one scene per line, each scene showing what its line says: a photo-like picture underneath, with maps, gauges, counters, timelines and labels drawn on top. Every number is checked against two independent sources before anything is filmed, and a number or name appears on screen at the moment the voice says it. End on a payoff line and a held end card that says "Follow Facts in Motion."

## Scene plan
| Time | Beat | What happens on screen |
|---|---|---|
| 0.0-3.0 | Hook | The surprise drawn on frame 0 (the number, the odd picture, the question); the voice starts inside the first second and its hook line is over by 3.0 s (about eight words: write and screen it with `hooks.md`; batch 6's hooks ran 11 to 21 words and ended at 3.7 to 6.9 s) |
| 3.0-end-3 | Lines 1 to N | One scene per spoken line, 8 to 12 lines, 4 to 8 s each. Each scene shows what its line explains: a new plate, a drawn element or a reveal |
| last line | Payoff | The line that answers the hook, on the strongest plate, with the single biggest reveal |
| last 3 s or more | End card | "Follow Facts in Motion." or the series line, held at least 3 s, never cut short |

Total 60 to 90 s for a first cut; go longer (up to 180 s) only when the facts hold it, adding lines and not slowing them. Scene lengths come from each line's narration slot (`voice.md`), not from a fixed grid.

## Look
- A photo plate under every scene (`image-plates.md`); drawn graphics over it: maps, gauges, counters, timelines, labels. The engine draws every word and number; no text inside any plate.
- On-plate labels in a corner of the scene: "AI ILLUSTRATION" on a generated picture, "SIMPLIFIED DIAGRAM" or "SIMPLIFIED MAP" on a drawn one.
- Keep the caption band and the platform margins clear (`formats.md`). Type in one sans, large, with a halo or a dark band where the plate is bright, so every text pair keeps 4.5:1 on the real pixels (Q301).

## Motion
- Each scene is a `plates.Shot`: Ken Burns within 1.0 to 1.3 zoom (more raises a ValueError, and the plate goes soft past it).
- Parallax for depth: a background-removed cutout as the `fg` shot drifting faster than its plate, and `dof` of 2 to 6 px on the background behind it.
- `haze` for atmosphere and depth, and `vignette` about 0.2 to 0.35.
- Something visibly changes every 3 to 5 s: a new shot, a drawn element, a reveal. Cut on the beat; `plates.sequence(..., xf=0.5)` dissolves between shots.

## Type
A caption per spoken line in the caption band. A number or name reveals on its spoken word (`voice.word_cue`, snapped to a frame), never seconds before the voice says it.

## Audio
- Kokoro af_heart narration (`voice.md`), mixed with `voice.duck_mix(bed, voice, polish=True)` for the broadcast polish (high-pass, presence lift, 3:1 compressor).
- A score from the recorded CC0 instruments (`instruments.md`, `sampler.py`) on the beat grid.
- One ambience bed per scene from `synth.py` at a low level under the voice: `wind`, `ocean`, `rumble`, `deep_water` or `space_hum`, placed on the music bus.
- A whoosh on plate changes, and `synth.impact` on the single biggest reveal (place it with `sound="impact"` so Q804 counts it).
- Master -14 LUFS (`mixing.md`).

## Facts
- Every number is checked against two independent sources before the storyboard; film only what both support. Numbers are spoken as words, and the sources are named in the caption.
- The caption carries "Pictures: AI-generated illustrations." and "Narration: AI-generated voice."
- Maps that touch India's borders follow India's official depiction (Survey of India): Aksai Chin, the Shaksgam valley and all of Jammu and Kashmir are never inside China or Pakistan, and Arunachal Pradesh is never inside China.

## Build notes
- Frame cost at 1080x1920: a plain window is about 17 to 32 ms, a parallax frame about 64 ms when the machine is quiet and up to about 150 ms when other renders share it. A 90 s video is 2,700 frames.
- Set `OPENBLAS_NUM_THREADS=1` when several builds share the machine.
- Import the module (`import plates as PL`), not `from plates import *`: a build that also defines its own `view`, `window`, `load`, `cover` or `sequence` trips Q1204.
- Q806 tips: write numbers as words, "one thousand" and not "a thousand", and put hard names on screen rather than in the voice.
- Measure each plate's lit share before giving it to the builder (`image-plates.md`).

## Blocks

The 2.8.0 parts that fit this look (`blocks.md`); pass the card's own colours and fonts, never the module defaults.

- **Text:** `blocks_text.captions(img, t, N, style="pill")` for the caption band, `N` the loaded narration (`caption_words(N, line="L03")` for one line), with `HOLD_PROFILE = "caption"`; `blocks_text.lower_third(name, role=..., style="kicker")` for a place or name label in a corner; `blocks_text.end_card(img, t, title, nudge="Follow Facts in Motion.")` for the end card, held at least 3 s.
- **Data:** `blocks_data.counter(value, start=0, suffix=..., t0=<the word's cue>, dur=1.6)` for a number that counts up on its spoken word (`voice.word_cue`, snapped to a frame), the one ticker in its scene; `blocks_data.stat_ring(pct, label=...)` for a share; `blocks_data.route_arc(a, b, labels, halo=<the plate's dark>)` for a route or a distance over a plate, where `halo` keeps its labels readable on the photo; `blocks_data.line_draw(values, xlabels)` for a change over time, held 1 s after it lands.
- **Transitions and camera:** none from `blocks_fx`. The plate moves with its own `plates.Shot` and `parallax`, and shots dissolve with `plates.sequence(..., xf=0.5)`; a `push_in` or `rack_focus` on the whole frame would move or blur the drawn type with it, and `parallax` already has its own vignette.
- **Gates:** write `quiz.json` (Q210) from the two-source facts list, each answer's keys on one frame and in its narration line.

## Style QA
- Every number on screen and in the voice is in the facts list with two sources.
- Every reveal lands on its spoken word (check with `qa.py speech` and the cue times).
- Every generated picture carries "AI ILLUSTRATION"; every drawn map or diagram carries its "SIMPLIFIED" label.
- A visible change at least every 5 s; the end card holds at least 3 s.
- Loudness near -14 LUFS, peak under -1 dBTP.
