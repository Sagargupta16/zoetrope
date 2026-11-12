# S-ledger · Sourced data story, counters and charts on the beat (48 s)
**Source:** designed for this skill on 2026-10-31 and rewritten from the engine on 2026-11-01, no outside reference · our build: none yet (each beat map passes `qa.py holds` as written)
**Use when:** "data story", "numbers video", "chart animation", "stats with sources"
**Defaults:** 48 s (30 to 60) · 16:9 1920x1080, 9:16 cut · 30 fps · 75 BPM, music, no voice
**Spec:** family=explainer length=30-60 size=1920x1080 fps=30 audio=music kit=-

A data story: numbers that count up, bars and lines that draw on the beat, and every figure tied on screen to a source the user supplied.

## Use when

- 30 to 60 s about two to four figures, each with a source the user gave (publisher, title or table, date, link).
- The point is a comparison or a change: how big, how many, what grew, what fell.
- Not for: a number with no source (ask for one, or leave it out), a single stat inside a launch (signal), a process (blueprint).

## Format

- Default 16:9, 1920x1080, 30 fps, 48 s: 15 bars at 75 BPM (a beat is 24 frames, a bar 3.2 s).
- `HOLD_PROFILE = "slow"`: dense figures and source lines get the slow reading pace.

## Look

| Role | Hex | Use |
|---|---|---|
| PAPER | #F4F1EA | background, PIL grey 241 |
| INK | #1C2430 | titles, figures, labels |
| SUB | #5A6372 | source lines, axis labels, subtitles |
| SERIES | #2B6A88 | bars, lines, dots: the data |
| KEY | #B53A26 | the one figure the story is about |
| RULE | #D6CFC0 | axes and gridlines, never text |

| Text | On | WCAG ratio |
|---|---|---|
| INK | PAPER | 13.85:1 |
| SUB | PAPER | 5.38:1 |
| SERIES / KEY | PAPER | 5.29:1 / 5.17:1 |
| PAPER (label inside a bar) | SERIES / KEY | 5.29:1 / 5.17:1 |

**Type.** Bold slot: Libre Franklin Bold (titles, figures). Regular slot: Libre Franklin Regular (labels, sources). SIL OFL 1.1, from Google Fonts, static files (families.md, Fonts for the six panel cards). Fallbacks: Windows Arial Bold and Arial, macOS Helvetica, Linux Liberation Sans. Sizes at 1080: headline figure 260, title and takeaway 72, figure label and chart title 56, values 40, axis labels, categories and source lines 36.

**Digits.** A count-up needs digits of one width, or the figure shivers as it counts. Check the face once in the build: `len({text_w(d, 260) for d in "0123456789"}) == 1`. Arial, Segoe UI and Consolas pass; Georgia Bold and Impact do not (checked 2026-10-31 on Pillow 13).

**Grid.** Margins 128 px left and right, 96 px top and bottom. Title band y 120 to 300; plot area x 200 to 1720, y 340 to 860; categories under the baseline; the source line set left with its baseline at y 990, in SUB. Axes are 2 px RULE, gridlines 1 px RULE.

## Motion

- Counts: `value = final * ease_out_expo(prog(lt, t0, 1.6))` over 2 beats, evaluated on twos (at `stepped(t, 15) / 15`, so each value holds 2 frames), right-aligned at its final right edge (anchor `"rs"`) so the unit never moves. It lands exactly on the source's figure, in the source's decimals and separators.
- Bars grow from the baseline, one a beat, 0.6 s each with `ease_out_cubic`; a value appears on the beat after its bar starts. The KEY bar changes colour on a downbeat, alone.
- Lines draw left to right at constant speed in x (`linear`) over 4 beats; the head is a 10 px dot; the end value lands with the head.
- Axes draw over 1 beat with `ease_in_out_cubic` before any data moves.
- No transitions: the paper is continuous. Old ink leaves in the last 0.25 s of its scene (`ease_in_cubic`), new ink starts on the cut.

## Sound

- 75 BPM, scored with `synth.py` inside `synth.recording()` in place of `audio.render_audio` (references/beat-sync.md, Stems and the cue sheet). Calm: nothing heavy under a figure.
- Bed: a `synth.pad` chord per bar (`align="pad"`), `synth.bass` on beat 1, a soft `synth.kick` (0.35) on beat 1 only, `synth.hat` on the eighths at 0.15.
- While a figure counts: `synth.tick` on every sixteenth (0.2 s) at 0.25; on the landing frame a `synth.pluck` (onset). Each bar's landing: a pluck one scale step above the last. The KEY change: a tick. The line's end: a pluck. Into the takeaway: one soft `synth.whoosh` at 0.25 peaking `audio.WHOOSH_LEAD` before the cut.

## Beat map

| Time (s) | Bar.beat | Visuals | On-screen text | Audio |
|---|---|---|---|---|
| 0.0-6.4 | 1.1 | Title set left at frame 0; a RULE line draws under it on 1.2; the subtitle fades up on 1.3 | "{the question this data answers}" (0.0-6.4), "{dataset, place and years}" (1.6-6.4) | pad on 1.1, soft kick |
| 6.4-16.0 | 3.1 | Figure 1: the number counts 3.1 to 3.3 and settles; its label on 3.3; the source line on 4.1 | "{12,345}" (8.0-16.0), "{what the number counts}" (8.0-16.0), "{Source: publisher, year}" (9.6-16.0) | ticks while it counts, pluck on 8.0 |
| 16.0-25.6 | 6.1 | Figure 2: axes and categories on 6.1; four bars grow on 6.2 to 7.1, values one beat behind each; KEY bar on 7.3; source on 7.4 | "{what the bars compare}" (16.0-25.6), "{category}" / "{category}" / "{category}" / "{category}" (16.8-25.6), "{value}" / "{value}" / "{value}" / "{value}" (20.0-25.6), "{Source: publisher, year}" (21.6-25.6) | rising pluck per bar, tick on 20.8 |
| 25.6-35.2 | 9.1 | Figure 3: axes on 9.1; the line draws 9.2 to 10.2; end dot and value on 10.2; source on 10.3 | "{what the line tracks}" (25.6-35.2), "{start year}" / "{end year}" (26.4-35.2), "{end value}" (29.6-35.2), "{Source: publisher, year}" (30.4-35.2) | pluck on 29.6 |
| 35.2-41.6 | 12.1 | Takeaway: one sentence set large; the key figure again, in KEY, on 12.3 | "{what it means, in one plain sentence}" (35.2-41.6), "{12,345}" (36.8-41.6) | soft whoosh into 35.2, pluck on 36.8 |
| 41.6-48.0 | 14.1 | End card: every source and the byline; still from 47.0 | "{Sources: publisher one, publisher two}" (41.6-48.0), "{byline or channel}" (42.4-48.0) | pad to the end |

## Build notes

- `TIMELINE = [Scene("title", 8), Scene("fig1", 12), Scene("fig2", 12), Scene("fig3", 12), Scene("takeaway", 8), Scene("end", 8)]` in beats, `compile_schedule(TIMELINE, bpm=BPM)`.
- Facts first: each figure is a line of the scenario's facts list (value as the source prints it, unit, source, table, date, link). A derived figure (a change, a share) lists its inputs and its formula there. Round only as the source does.
- Helpers: `canvas`, `rrect` (bars, radius 4), `text`, `text_box` (same anchor as the draw), `text_w`, `fit_size`, `wrap`, `prog`, `lerp`, `clamp`, `stepped`, `ease_out_expo`, `ease_out_cubic`, `ease_in_out_cubic`, `linear`. Lines and dots go through `ImageDraw.line` and `ellipse` with palette constants; run at `--ss 2` so 2 px rules and the line stay smooth.
- Registry: the counting figure is one item with `ticker=True`; titles, labels, categories, values, every source line and the byline are items. Bars, lines, dots and rules are shapes.
- CUES: each count landing (8.0, 36.8), each bar landing, the KEY change (20.8), the line's end (29.6), every cut. KEY_TIMES: 8.0, 20.8, 29.6, 36.8 and 47.5. `STATIC = [(47.0, 48.0)]`.

## QA watch-outs

- Q401: values on the way are ticker values and need no hold; the settled figure rests 1.5 s at least under slow (the map gives it 4.8 s or more).
- Q402: source lines and axis labels stay at 36 px; to fit, cut words, never the size, and never drop the source.
- Q301: a value inside a bar reads PAPER on SERIES or KEY; on a bar too short to hold it, set it above the bar in INK, so the ring Q301 samples is one colour.
- Q202: more than six categories collide at 16:9: switch to horizontal bars (9:16 layout) or merge categories in the facts list.
- Q207: the paper stays put; text replaced in place enters on its cut, one empty frame after the old text left.
- Q1104 does not count a figure stepped on twos; a count that stops short of the source's figure is a fact error, not a style choice.
- Every figure on screen has its source line on screen in the same scene.

## Variations

- 9:16: bars turn horizontal (category left, value at the bar's end), the line chart spans 88 percent of W, the headline figure drops to 220 px, the title band moves to y 220 to 520 and the bottom 400 px stays empty.
- 32 s: 10 bars, title (2), figure 1 (3), figure 2 (3), end card with the takeaway (2).
