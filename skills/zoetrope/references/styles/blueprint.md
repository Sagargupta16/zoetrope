# S-blueprint · Technical explainer, a diagram that draws itself (60 s)
**Source:** designed for this skill on 2026-10-31 and rewritten from the engine on 2026-11-01, no outside reference · our build: none yet (each beat map passes `qa.py holds` as written)
**Use when:** "how it works", "architecture explainer", "pipeline diagram video", "system diagram that draws itself"
**Defaults:** 60 s (45 to 90) · 16:9 1920x1080, 9:16 cut · 30 fps · 100 BPM, music, no voice
**Spec:** family=explainer length=45-90 size=1920x1080 fps=30 audio=music kit=-

A technical explainer: a diagram that draws itself on a ruled sheet, one part per step, each step named in a caption.

## Use when

- 45 to 90 s on how a system, pipeline or process works: three to five parts and the connections between them.
- The scenario lists each part, what flows between them and one sentence per step.
- Not for: a feature pitch (signal), figures from sources (ledger), more than about eight parts (split it into two videos).

## Format

- Default 16:9, 1920x1080, 30 fps, 60 s: 25 bars at 100 BPM (a beat is 18 frames, a bar 2.4 s). A step is 4 bars.
- `HOLD_PROFILE = "slow"`: captions explain, so they get the slow pace.

## Look

| Role | Hex | Use |
|---|---|---|
| SHEET | #173E6E | the sheet, PIL grey 56; also every label's knockout plate |
| GRID | #24508A | minor grid, 1 px every 40 px |
| MAJOR | #3A69A6 | major grid, 2 px every 200 px |
| LINE | #EEF4FF | strokes, title, node names |
| LABEL | #9CD6FF | edge labels, captions, subtitles |
| LIVE | #FFCB5C | the part being explained, the moving packet |

| Text | On | WCAG ratio |
|---|---|---|
| LINE | SHEET / GRID | 9.75:1 / 7.35:1 |
| LABEL | SHEET / GRID | 6.91:1 / 5.20:1 |
| LIVE | SHEET | 7.15:1 |
| SHEET (on a LIVE tag) | LIVE | 7.15:1 |

**Type.** Bold slot: Space Grotesk Bold (title, node names). Regular slot: JetBrains Mono Regular (labels, captions). Both SIL OFL 1.1, from Google Fonts, static files (families.md, Fonts for the six panel cards). Fallbacks: Windows Segoe UI Bold and Consolas, macOS Helvetica Bold and Menlo, Linux DejaVu Sans Bold and DejaVu Sans Mono. Sizes at 1080: title 84, node names 44, captions and subtitles 40, edge labels 36.

**Grid.** Nodes snap to the 40 px grid: boxes 360x160, 3 px LINE strokes, radius 8. Diagram area x 120 to 1800, y 120 to 820. Caption band y 880 to 1000 on a SHEET plate. A ruled title block (560x160, bottom right) carries the title on the first and last scene. Every label sits on a SHEET plate with 12 px padding, so no grid line runs through text.

## Motion

- Strokes trace along their length: a node outline over 2 beats with `ease_in_out_cubic` on the whole progress, a connector over 1 beat, its arrowhead landing on the next beat with `ease_out_back` over 6 frames.
- Labels wipe in left to right over 1 beat through a mask, so `reveal_end` and its pluck land on the next beat; captions fade up over 0.4 s with `ease_out_expo`. Text never types letter by letter: each prefix would be a new string that needs its own hold.
- The packet is a 14 px LIVE dot: one hop a beat along the edges, `ease_in_out_cubic` per hop, with a short fading trail.
- Parts already explained stay; their strokes may dim to 60 percent, their labels never do.
- No camera moves on text: font sizes are whole px, so a zoom shimmers. Lay the whole diagram out once inside the safe area.
- Hard cut from the title to the empty sheet; steps then accumulate on one sheet with no transitions. The end card opens with `transitions.iris(a, b, ease_in_out_cubic(mix), center=node_d)` over 1 beat from the cut.

## Sound

- 100 BPM, scored with `synth.py` inside `synth.recording()` in place of `audio.render_audio` (references/beat-sync.md, Stems and the cue sheet). Soft and even under the captions.
- Bed: a `synth.pad` chord every two bars (`align="pad"`), `synth.bass` on beat 1, `synth.kick` on 1 and 3 at 0.4, `synth.hat` on the eighths at 0.12.
- SFX: `synth.tick` when a stroke completes (the pen lifts), `synth.pluck` on each label's `reveal_end`, one rising pluck per packet hop, a soft `synth.whoosh` (0.3) peaking `audio.WHOOSH_LEAD` before each step's cut. The end card resolves on the pad and a low `synth.bass` root; no boom.

## Beat map

| Time (s) | Bar.beat | Visuals | On-screen text | Audio |
|---|---|---|---|---|
| 0.0-4.8 | 1.1 | Title: sheet, grid and title block drawn at frame 0; a border traces round the sheet over bar 1; the subtitle wipes in on 1.2 | "{what this explains}" (0.0-4.8), "{system or version}" (0.6-4.8) | pad on 1.1 |
| 4.8-14.4 | 3.1 | Step 1: node A traces 3.1 to 3.3; its name wipes in on 3.3; the caption on 4.1 | "{node one}" (6.0-14.4), "{step one, said in eight words or fewer}" (7.2-14.4) | whoosh into 4.8, tick on 6.0, pluck on the name |
| 14.4-24.0 | 7.1 | Step 2: node B traces 7.1 to 7.3; connector A to B on 7.3, arrowhead on 7.4; B's name on 7.4; edge label and caption on 8.1 | "{node two}" (16.2-24.0), "{edge label}" (16.8-24.0), "{step two, said in eight words or fewer}" (16.8-24.0) | whoosh into 14.4, ticks, plucks |
| 24.0-33.6 | 11.1 | Step 3: node C and connector B to C as in step 2; the packet runs A to B to C from 12.1, one hop a beat | "{node three}" (25.8-33.6), "{edge label}" (26.4-33.6), "{step three, said in eight words or fewer}" (26.4-33.6) | rising pluck per hop |
| 33.6-43.2 | 15.1 | Step 4: node D (the result or a branch) and its connector; this step's parts turn LIVE | "{node four}" (35.4-43.2), "{edge label}" (36.0-43.2), "{step four, said in eight words or fewer}" (36.0-43.2) | whoosh into 33.6, ticks, plucks |
| 43.2-52.8 | 19.1 | Whole flow: every part at full weight; the LIVE path lights hop by hop and the packet runs end to end twice; the summary caption on 19.3 | "{the whole flow in one sentence}" (44.4-52.8) | pluck per hop, pad swells |
| 52.8-60.0 | 23.1 | End card: iris from node D onto a clean sheet with the title block; still from 59.0 | "{what this explains}" (53.4-60.0), "{where to read more}" (54.0-60.0) | pad resolves, low bass root |

## Build notes

- `TIMELINE = [Scene("title", 8), Scene("step1", 16), Scene("step2", 16), Scene("step3", 16), Scene("step4", 16), Scene("whole", 16), Transition("iris", 1, 0), Scene("end", 12)]` in beats, `compile_schedule(TIMELINE, bpm=BPM)`.
- The diagram is one table of parts (node, edge, label), each with the time it starts and its draw length; `draw(t)` paints every started part at its progress, so a part never depends on an earlier frame.
- Build the grid once at import, for `E.W` and `E.H`, as a module-level image, and start each frame from its `.copy()`. Run at `--ss 2`: 1 px grid lines and 3 px strokes alias at SS 1.
- Helpers: `canvas`, `rrect` (nodes, plates), `text`, `text_box`, `fit_size`, `wrap` (captions, two lines at most), `prog`, `lerp`, `clamp`, `ease_in_out_cubic`, `ease_out_back`, `ease_out_expo`, `scenes_at`, `transitions.iris`. Strokes and arrowheads go through `ImageDraw.line` and `polygon`; name your own trace function so it shadows no engine helper (Q1204).
- Registry: title, subtitle, node names, edge labels, captions, end card lines. A label mid-wipe reports the whole string, its box cut at the mask edge, and `reveal_end`.
- Time every exit to the cut in `CUTS`, not to the scene's `SCHEDULE` end: inside the iris window the outgoing scene is still drawn past its cut, and its text must already be gone.
- CUES: each stroke's end, each `reveal_end`, each packet hop, every cut (the 52.8 cut is inside the iris window: kind `audio`). KEY_TIMES: the last frame of each step (14.3, 23.9, 33.5, 43.1), 50.0 and 59.5. `STATIC = [(59.0, 60.0)]`.

## QA watch-outs

- Q301: a label without its plate picks up grid lines in the ring Q301 samples; keep every plate.
- Q404: clamp the eased wipe so it reaches 1.0 by `reveal_end` exactly; the box must be the whole string's `text_box`.
- Q206: route edges and the packet around label plates, and draw labels after strokes, so nothing covers text.
- Q401 under slow: a caption of eight words and 40 characters needs 3.7 s at rest; each step gives it about 7 s. Longer captions: cut words.
- Q402: edge labels stay at 36 px or more at 1080.
- Q207: the caption band stays empty for 1.2 s or more between captions, so no changeover falls between 3 frames and 0.5 s.
- Q503: the packet stops by 59.0.

## Variations

- 9:16: the flow runs top to bottom, nodes 600x140, the caption band at y 1380 to 1500, the top 200 px and bottom 400 px empty; the title block becomes a full-width band.
- 45.6 s: 19 bars, title (2), three steps (4 each), whole flow (3), end card (2).
