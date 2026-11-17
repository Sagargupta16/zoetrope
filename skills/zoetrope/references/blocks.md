# Block library, brand kits and motion helpers

Ready-made pieces a scene drops onto its canvas, so a builder does not hand-write a chart, a caption or a transition again. All of it is in `engine/` (copied with the rest), pure functions of t, nothing downloaded.

**Rule: search before you write.** Before hand-writing an effect or a helper, look here, in the gallery sheets (below) and in `python <skill>/engine/kit_index.py` (`kit_index.py show <name>` prints one signature; run the skill's copy, the working folder's finds no kits). Reuse, restyle with the card's palette and type, and keep the machinery.

## The gallery

`python blocks_preview.py <out folder> [--size WxH] [--kits]` writes `blocks_text.png`, `blocks_data.png`, `blocks_fx.png` and, with `--kits`, `kits.png` (a poster per kit), each at most 2000 px. Open them to see what a block looks like before choosing.

## The twin rule

Every text and data block `name(img, t, ...)` has a twin `name_items(t, ...)` that takes the same arguments without `img` and returns the text records for the scene's `text_items(t)`. Both come from one plan, so the registry cannot drift from the picture (Q204). Call both with the same arguments, in the same scene. Every block takes `t0` (when it starts), `dur` (how long its move lasts) and `alpha` (a scene fade) where it moves. `marker_items` returns `[]`: a mark is not text.

## blocks_text.py

Each caption word and each code token is its own record, so the reading holds apply to it (gate 4). Text swapped in one place leaves a gap: 5 to 9 empty frames is a Q207 NOTE, so overlap the two blocks or leave 0.5 s. Colour constants (`INK`, `PAPER`, `ACCENT`, `WHITE`, `SHADE`, `SOFT`, `MUTED`, `MUTED_DARK`, `PANEL`, `RED_TINT`, `GREEN_TINT`) are the defaults; pass the card's.

| Block | Signature (head) | For |
|---|---|---|
| `lower_third` | `(img, t, name, role='', style='clean_bar', t0, dur, ...)` | a name and role near the bottom left; `LOWER_THIRD_STYLES`: clean_bar, accent_underline, side_rule, soft_pill, kicker, stacked_bars |
| `captions` | `(img, t, words, style='pill', per_page=5, ...)` | word-synced captions; `CAPTION_STYLES`: pill, pop, highlight, karaoke; `words` is `[(word, start, end)]` or anything `caption_words(narration, line=None, offset=0.0)` reads (a narration.json path, the loaded dict, a list, one line) |
| `marker` | `(img, t, kind, box, t0, dur=0.7, ...)` | a hand-drawn mark that draws on; `MARKER_KINDS`: circle, underline, strike, cross, arrow (an arrow's box is tail x, tail y, head x, head y) |
| `end_card` | `(img, t, title, handle='', nudge='Follow for more', ...)` | the closing card; pass the handle as typed, `"@name"` |
| `chat_thread` | `(img, t, messages, step=1.3, ...)` | a generic chat revealed message by message; messages `[("them", "text"), ("me", "text")]` |
| `notification` | `(img, t, title, body='', ...)` | a generic notification card with an icon tile (1 to 2 characters) |
| `code_typing` | `(img, t, code, lang='python', ...)` | code typed in order with a caret; Python and JavaScript colouring |
| `code_diff` | `(img, t, old, new, lang='python', ...)` | the change between two versions (difflib, line by line) |

The code blocks draw in JetBrains Mono, which is in the `fonts.py` cache (`python fonts.py list`).

## blocks_data.py

| Block | Signature (head) | For |
|---|---|---|
| `bar_race` | `(img, t, keys, periods=None, ...)` | bars that grow, re-sort and slide; `keys = [(time, {name: value})]` |
| `line_draw` | `(img, t, values, xlabels=None, ...)` | a line chart that draws on, a value on its head |
| `pie` | `(img, t, parts, donut=True, ...)` | a pie or donut that sweeps in, a legend, a centre total |
| `counter` | `(img, t, value, start=0.0, ...)` | a number that rolls to a value, with prefix, suffix and separators |
| `stat_ring` | `(img, t, pct, label='', ...)` | a ring that fills to a percentage |
| `progress_bar` | `(img, t, pct, ...)` | a bar that fills to a percentage |
| `route_arc` | `(img, t, a, b, labels, bulge=0.25, head='arrow', halo=None, ...)` | a curved route between two points; `halo=` a colour for labels over an image plate |
| `audio_bars` | `(img, t, levels, style='bars', ...)` | `style` bars, mirror or wave, from `analyse_wav(path, fps, bands=32)` levels |

`analyse_wav` reads a WAV once: call it at import, not inside draw. `format_number(v, decimals, prefix, suffix, sep)` is the format every block uses. Colours default to `DATA_TEXT`, `DATA_MUTED`, `DATA_TRACK`, `DATA_ACCENT`, `DATA_HALO`, `DATA_SERIES`; text is never under `LABEL_MIN` (36 px, Q402).

Caveats:

- A moving number is a ticker (`ticker=True` in its record). Hold the first and last race key 1 s or more.
- A line chart's last-value label fades in at `t0 + dur`: hold the chart 1 s after.
- In portrait use short race names.
- One ticker block per scene is the safest.

## blocks_fx.py (`import blocks_fx as FX`)

- **Backgrounds** (`FX.BACKGROUNDS`, each `f(t, ...)` returning a full-frame RGB at `W*SS` x `H*SS`, 13 to 36 ms a 1080p frame): `mesh_gradient`, `aurora`, `noise_field`, `starfield`, `halftone_field`, `paper_texture`, `diagonal_stripes`.
- **Light:** `light_leak(img, t, t0, dur, ..., side='left')`, `vignette(img, strength=0.45, ...)`.
- **Transitions** (`FX.FX_MENU`, each `f(a, b, p)` exact at p=0 and p=1, tagged `flash_risk`): `glitch_slices` ("check": run `qa.flash_window` over it), `chromatic_split`, `noise_warp`, `whip_pan` and `zoom_through` (both ease themselves; low risk).
- **Camera:** `push_in(img, k, scale=1.2, ...)`, `pull_out`, `dolly_zoom(fg_rgba, bg, k)`, `rack_focus(fg_rgba, bg, k)`. Never reveal empty canvas at the edges.

## Brand kits (brand.py)

When the user has a brand, `brand.json` sits in the working folder:

```
{"palette": {"name": "#RRGGBB"}, "fonts": {"bold": "Nunito:800", "regular": "..."},
 "logo": "logo.png", "notes": "...", "pairs": [["text name or hex", "background name or hex"]]}
```

`python brand.py check [brand.json]` prints `BRAND:` lines and exits 0 or 1: a bad hex, a font family `fonts.py` does not cache, a missing logo, a listed pair under WCAG 4.5:1 (`MIN_CONTRAST`), an unknown pair name. It reads the font cache only and never fetches. In scenes.py, `brand.load()` returns the palette, fonts, absolute logo path and notes; `contrast(a, b)` and `luminance(hex)` are there too. The logo is only ever a file the user supplied.

## Motion helpers (engine.py)

- `motion_blur(draw, t, fps=None, samples=8, shutter=180.0)`: averages `draw(t + offset)` over sub-frame offsets across `shutter/360` of a frame, in linear light. `samples <= 1` or `shutter <= 0` returns `draw(t)`. It costs `samples` times a frame: use it on fast moves only (`pitfalls.md` item 15).
- `noise(x, y=0.0, z=0.0, seed=0)` is gradient noise in [-1, 1] (scalars or numpy arrays), and it is 0 at whole-number coordinate triples: pass a fractional `y` or `z`. `fbm(x, y, z, octaves=4, seed=0)` layers it. `wobble(t, amp=1.0, hz=1.0, seed=0)` returns `(dx, dy)` for hand wobble and camera shake. A seed is an int or a str, never `hash()`.
- Easings: `ease_in_quad`, `ease_out_quad`, `ease_in_out_quad`, `ease_in_out_sine`, `ease_in_out_expo`, `ease_out_elastic` (overshoots to 1.37), `ease_out_bounce`, `smoothstep`, `smootherstep`, `rush_into`, `rush_from`, `there_and_back` (0 at both ends, 1 at 0.5), `wiggle(k, wiggles=2)` (0 at both ends).

## Footage (footage.py)

Clips the brief lists, never fetched. `python footage.py prepare <name|all>` decodes `clips/<name>.mp4` once into `clips/<name>/` with a `clip.json`; `check` and `info` read it. A name has no suffix (`rain`, for `clips/rain.mp4`); a name with a video suffix or a folder part is a path from the working folder instead. Two videos with one stem (`a.mp4` and `a.mov`) would share a cache folder, so both are refused until one is renamed. In scenes.py, `footage.Clip(name, fit="cover"|"contain", mode="hold"|"loop"|"bounce", start=0.0, speed=1.0)` and `.frame(t, size=None)` give a pure, frame-exact RGB. `run_all.py` stops with `CLIP:` lines when a source is missing or its cache is stale.

## Sources

Ideas only, no code copied, read 2026-11-17: the block registry of heygen-com/hyperframes (Apache-2.0) and its motion doctrine (the seam law in `playbook.md`), Remotion Elements, Motion Canvas code diffs, editly, and Manim rate functions (the easings).
