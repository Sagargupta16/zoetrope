# S-signal · Product or feature launch on interface panels (20 s)
**Source:** designed for this skill on 2026-10-31 and rewritten from the engine on 2026-11-01, no outside reference · our build: none yet (each beat map passes `qa.py holds` as written)
**Use when:** "launch video", "feature launch", "announce a release", "product panels with one accent colour"
**Defaults:** 20 s (15 to 30) · 16:9 1920x1080 or 9:16 · 30 fps · 120 BPM, music and sound design, no voice
**Spec:** family=launch length=15-30 size=1920x1080 fps=30 audio=music kit=-

A product or feature launch: one idea per story beat, each shown on an interface-like panel, with one accent colour.

## Use when

- Announcing a product, a release or one feature in 15 to 30 s, with at most three ideas.
- The scenario gives a name, a one-line promise, up to three things it does and where to go next.
- Not for: figures that need sources (ledger), how the thing works inside (blueprint), a mark alone (marquee), a reel cut to a beat (pulse).

## Format

- Default 16:9, 1920x1080, 30 fps, 20 s: 10 bars at 120 BPM (a beat is 15 frames, a bar 2 s). One story beat is two bars.
- 9:16 at 1080x1920 runs the same beat map (Variations). `HOLD_PROFILE = "display"`.

## Look

| Role | Hex | Use |
|---|---|---|
| CANVAS | #1F2633 | background, PIL grey 37 |
| PANEL | #2B3445 | panels and chips, grey 51 |
| LINE | #3C475C | panel borders and dividers, never text |
| TEXT | #F3F5F8 | headlines, panel copy |
| MUTED | #AEB8C8 | secondary labels |
| ACCENT | #FF9A4D | the one accent: active state, cursor, one key word, the call to action |

| Text | On | WCAG ratio |
|---|---|---|
| TEXT | CANVAS / PANEL | 13.90:1 / 11.45:1 |
| MUTED | CANVAS / PANEL | 7.58:1 / 6.24:1 |
| ACCENT | CANVAS / PANEL | 7.22:1 / 5.94:1 |
| CANVAS (button label) | ACCENT | 7.22:1 |

Every pair clears 4.5:1, so any pair may carry text at any size. A brand colour may replace ACCENT only if it also clears 4.5:1 on CANVAS and PANEL (`qa.contrast`); otherwise it colours shapes and the words stay TEXT.

**Type.** Bold slot: Inter Bold (headlines, product name). Regular slot: Inter Regular (panel copy, labels). SIL OFL 1.1, from Google Fonts, static files (families.md, Fonts for the six panel cards). Fallbacks: Windows Segoe UI Bold and Segoe UI, macOS Helvetica Neue, Linux DejaVu Sans. Sizes at 1080 on the short side, scaled by `min(W, H) / 1080`: product name 120, headline 88 (two lines at most), panel title 44, panel copy 40, labels 36 and never less.

**Grid.** 12 columns, 120 px outer margin left and right, 96 px top and bottom (the gate is 77 and 43 px), 24 px gutters. Headline block: columns 1 to 7 from y 140. Panel: columns 2 to 11, y 360 to 940, radius 20, a 2 px LINE border (a LINE `rrect` 2 px larger under it) and `shadow(img, box, 20, blur=24, dy=12, alpha=0.35)`.

## Motion

- Entrances 0.4 s `ease_out_expo`, rising 32 px from alpha 0; start one frame before the beat so the first visible change lands on it. Exits 0.25 s `ease_in_cubic`, ending on the cut.
- Each idea has exactly one interface moment, on beat 1 of its second bar: a toggle slides, a bar fills, a row appears. Move it with `spring(t, 220, 28)`: no overshoot, at rest in 0.43 s, inside one beat.
- Stagger inside a panel: frame, then rows, 2 frames apart. Text enters as whole lines, never letter by letter.
- The cursor is an ACCENT bar, on for the first 8 frames of every beat. The canvas never drifts; only panels move.
- Hard cuts on bar lines between ideas, the incoming headline entering on its cut (one empty frame). Into the end card, `transitions.push(a, b, ease_in_out_cubic(mix), "up")` over a one-beat window that straddles the cut.

## Sound

- 120 BPM, scored with `synth.py` inside `synth.recording()` in place of `audio.render_audio` (references/beat-sync.md, Stems and the cue sheet).
- Bed: `synth.kick` on beats 1 and 3, `synth.hat` on the offbeats, `synth.bass` on the bar's root, a `synth.pad` chord every two bars placed with `align="pad"`.
- Cuts: `synth.whoosh` peaking `audio.WHOOSH_LEAD` (80 ms) before the cut, `synth.pluck` with its onset on the cut. Interface moments: `synth.tick` on the frame the state changes. End card: `synth.boom` on the cut with the bed's kick left out there, then the pad to the end.
- SFX sit under the music: tick 0.5, pluck 0.3, whoosh 0.4, boom 0.5 gain before `audio.master` takes the mix to -14 LUFS.

## Beat map

| Time (s) | Bar.beat | Visuals | On-screen text | Audio |
|---|---|---|---|---|
| 0.0-4.0 | 1.1 | Hook: the name and the first panel fully drawn at frame 0; the promise rises in on 1.2; the cursor blinks on every beat | "{product name}" (0.0-4.0), "{the promise in five words}" (0.5-4.0) | bed starts; pluck on 1.1 |
| 4.0-8.0 | 3.1 | Idea 1: hard cut; panel A rises in; its one moment lands on 4.1 | "{first idea, four words}" (4.0-8.0), "{panel label}" (4.5-8.0) | whoosh into 4.0, pluck on 4.0, tick on 6.0 |
| 8.0-12.0 | 5.1 | Idea 2: panel B, moment on 6.1 | "{second idea, four words}" (8.0-12.0), "{panel label}" (8.5-12.0) | whoosh into 8.0, pluck, tick on 10.0 |
| 12.0-16.0 | 7.1 | Idea 3: panel C, moment on 8.1; all text gone by 15.5 | "{third idea, four words}" (12.0-15.5), "{panel label}" (12.5-15.5) | whoosh into 12.0, pluck, tick on 14.0 |
| 16.0-20.0 | 9.1 | End card: push up (15.75 to 16.25); name, call to action and address; still from 19.0 | "{product name}" (16.5-20.0), "{call to action}" (17.0-20.0), "{product.example/start}" (17.0-20.0) | boom on 16.0, pad to the end |

## Build notes

- `TIMELINE = [Scene("hook", 8), Scene("idea1", 8), Scene("idea2", 8), Scene("idea3", 8), Transition("push", 1), Scene("end", 8)]` in beats, `compile_schedule(TIMELINE, bpm=BPM)`.
- Fonts: at the top of scenes.py, `FONT_BOLD[:0] = [...]` and `FONT_REG[:0] = [...]` with the Inter files first, then the fallbacks.
- Helpers: `canvas`, `rrect`, `shadow`, `text`, `text_box`, `fit_size` (headline against `W * 0.52`, `W * 0.84` at 9:16), `wrap`, `prog`, `lerp`, `ease_out_expo`, `ease_in_cubic`, `ease_in_out_cubic`, `spring`, `scenes_at`, `transitions.push`.
- Time exits to the cut in `CUTS`, not to the scene's `SCHEDULE` end: inside the push window idea 3 is still drawn past 16.0, so its text leaves by 15.5.
- One `layout(t)` feeds `draw()` and `text_items()`. Register the name, promise, headlines, panel labels, call to action and address. Filler copy inside a mock panel is `texture=True` and under 24 px at 1080; the cursor and toggles are shapes.
- CUES: every cut (the 16.0 cut sits inside the push window, so kind `audio`), each interface moment (`both`). KEY_TIMES: each moment plus 2 frames, and 19.5. `STATIC = [(19.0, 20.0)]`.

## QA watch-outs

- Q501: frame 0 is the thumbnail; draw the name and panel A fully there. CANVAS alone reads grey 37, so the floor of 25 holds.
- Q207: a headline replaced in place enters on its cut (one empty frame); a fade-out that leaves 3 frames to 0.5 s empty is a NOTE.
- Q203: nothing readable inside the push window; the end card enters at 16.5.
- Q402: panel copy a viewer must read is 36 px or more at 1080; smaller copy is texture and says nothing new.
- Q503: stop the cursor and every move by 19.0, so the last second holds still.
- Q601: blink only the cursor; never flash a panel or the canvas.
- Every claim in a headline (faster, cheaper, first) comes from the scenario's facts list.

## Variations

- 9:16: the same 10 bars. Headline block at y 240 to 560 (two lines via `wrap`), panel at y 620 to 1360 and 88 percent of W, the bottom 400 px left empty for app controls; sizes from `min(W, H)`.
- 16 s: drop idea 3 (8 bars). 24 s: add a proof beat after idea 3, one number or quote from the facts list on its own panel.
