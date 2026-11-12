# S-cartridge · Retro 8-bit side-scroller parody with chip music (32 s)
**Source:** designed for this skill on 2026-10-31 and rewritten from the engine on 2026-11-01, no outside reference · our build: none yet (each beat map passes `qa.py holds` as written)
**Use when:** "8-bit video", "retro game parody", "pixel art side-scroller", "chiptune promo"
**Defaults:** 32 s (20 to 40) · 16:9 1920x1080, 9:16 cut · 30 fps · 150 BPM, chip music, no voice
**Spec:** family=game length=20-40 size=1920x1080 fps=30 audio=music kit=-

A retro 8-bit game parody: a tiny side-scroller drawn in code pixel by pixel, a font drawn from a grid, and chip music made from plain waveforms.

## Use when

- 20 to 40 s, light in tone: a product, a team or a launch told as a game. A title screen, a stage where the hero collects the features, a boss that is the problem, a stage clear and an end card.
- Everything is drawn in code from grids: sprites, tiles and the font. Nothing comes from a real game, no sprite, tile, font, sound, character or catchphrase. If a viewer could name the game a frame came from, redraw it.
- Not for: serious or sensitive subjects, long copy (about 12 words on a screen at most), sourced figures (ledger).

## Format

- Default 16:9, 1920x1080, 30 fps, 32 s: 20 bars at 150 BPM (a beat is 12 frames, a bar 1.6 s).
- Drawn on a virtual screen of 320x180, one art pixel each, then scaled up by `k = min(E.W, E.H) // 180` (6 at 1080) with `Image.NEAREST`. 9:16 uses 180x320 and 1:1 180x180. Run at SS 1: supersampling blurs the pixels.
- `HOLD_PROFILE = "display"`.

## Look

| Role | Hex | Use |
|---|---|---|
| SKY | #2E3F73 | the sky behind every screen, PIL grey 64 |
| NIGHT | #151A2B | outlines, soil, text panels; grey 26, so panels only, never a whole frame |
| TURF | #4DB548 | grass, pickups |
| HERO | #F6D55C | the hero, title letters, coins |
| FOE | #E8604C | the boss, damage, the HP bar |
| CHALK | #F8F4E3 | text, stars, highlights |

| Text | On | WCAG ratio |
|---|---|---|
| CHALK | SKY / NIGHT | 9.18:1 / 15.68:1 |
| HERO | SKY / NIGHT | 7.03:1 / 12.01:1 |
| FOE | NIGHT | 5.11:1 |
| NIGHT (on a HERO banner) | HERO | 12.01:1 |
| NIGHT (on a TURF sign) | TURF | 6.60:1 |

These six colours and no others: no gradients, no anti-aliasing, no blur, no grain.

**Type.** No font file. A 5x7 font of the build's own, drawn as grids in a local `pixfont.py`: A to Z, 0 to 9 and `. , ! ? : - + ' / %`, each glyph in a 6x8 cell (1 px gap on the right, 1 px under the baseline). Make it a PIL bitmap font once per process: write the glyphs as BDF text, save them with `BdfFontFile.BdfFontFile(io.BytesIO(bdf)).save(folder + "/pix")` into a `tempfile.mkdtemp()` folder, then `ImageFont.load(folder + "/pix.pil")`. `ImageDraw.text` with that font keeps every string visible to the text recorder. Glyphs pasted as rectangles are not, and with no other text Q208 is NOT CHECKED and the build is rejected. Checked 2026-11-01 on Pillow 13.0.0: a probe built this way (a 1x line on the virtual screen, a 2x title pasted from a layer) passed `run_all.py proof` at 1920x1080 and 1080x1920, Q204 to Q209 all PASS, one Q1205 NOTE. Capitals only. 1x text is one cell, 48 px at 1080 and the smallest the style allows; titles are 2x: drawn on a small layer, scaled 2x with NEAREST and pasted onto the virtual screen.

**Grid.** Virtual 16:9: HUD band y 8 to 16 (banner, score), playfield y 24 to 150, ground y 150 to 180. Text keeps 16 virtual px from the sides and 10 from the top and bottom (the gate is 12.8 and 7.2). Everything sits on whole virtual pixels. Sprites are lists of strings, one character per pixel and `.` for clear: hero 16x16 (four run drawings, one jump), items 8x8, boss 32x32, tiles 16x16. Text panels are NIGHT boxes with a 1 px CHALK border.

## Motion

- Everything animates on 10 Hz steps (`stepped(t, 10)`): sprite drawings, positions in whole virtual px, the scroll. A drawing holds exactly 3 frames, which Q1104 reads as held animation, not a stall. Beats at 150 BPM fall on step boundaries (0.4 s is 4 steps), so a move that starts on its beat changes on the beat frame.
- The hero runs through four drawings and jumps on a parabola sampled at the steps: it takes off half a beat before a grab and touches the item at the top, on the beat.
- A grab: the item bursts into four CHALK pixels for 3 steps, and the HUD banner swaps to the new feature on the same frame. Pixel text appears and goes in one frame, never by fading.
- A hit: the boss sprite turns CHALK for 2 frames on its beat, one HP segment goes, and the screen shakes 2 virtual px for one step (offset from `rng("shake", step)`).
- The KO: the boss breaks into 16 squares that fly out under gravity (each from `rng("ko", i)`), gone by 24.0. Title stars twinkle one at a time (`rng("star", i, step)`), never together.
- Transitions run on the virtual screens before the upscale, so their edges step in art pixels too: `transitions.wipe(a, b, mix, "right")` into the stage and `transitions.iris(a, b, mix, center=hero_xy)` into the clear, each 1 beat from its cut.

## Sound

- 150 BPM chip score, dry. `synth.py` has no square or triangle wave, so the build's own score file writes two small numpy functions: `square(f, n, duty)` from `(synth.tt(n) * f) % 1 < duty`, and `triangle(f, n)` as `2 * abs(2 * phase - 1) - 1`. Notes come from `synth.hz(m)`, envelopes from `synth.ex(n, tau)`, drums from `synth.noise(name, n, ...)` shaped with `synth.lp` and `synth.hp`: short and bright for the hat, longer and darker for the snare, a square falling in pitch for the kick.
- Voices: a 25 percent square lead in sixteenth-note arpeggios, a triangle bass on the eighths, drums on the beat. Score inside `synth.recording()` in place of `audio.render_audio` (references/beat-sync.md, Stems and the cue sheet).
- SFX: a grab is a rising three-note square blip, its onset on the grab frame; a hit is a noise burst with a falling blip, onset on the beat; the KO a falling square run over one beat and a long noise burst; the clear a one-bar fanfare. Place each with `synth.place(..., label=...)` for its cue; unnamed sounds align by onset.
- Squares are loud for their level: lead 0.15, bass 0.25, drums 0.2, SFX 0.3 before `audio.master`.

## Beat map

| Time (s) | Bar.beat | Visuals | On-screen text | Audio |
|---|---|---|---|---|
| 0.0-4.8 | 1.1 | Title screen: SKY with stars, ground tiles, the hero idling; the 2x title set at frame 0; PRESS START steady under it, an arrow sprite beside it blinking on beats | "{GAME TITLE}" (0.0-4.8), "PRESS START" (0.8-4.8) | fanfare: arpeggio over bars 1 and 2, a held chord on bar 3 |
| 4.8-14.4 | 4.1 | Stage: wipe right from the cut; the hero runs and grabs on 5.1, 6.3 and 8.1; each grab swaps the HUD banner | "{FEATURE ONE}" (6.4-8.8), "{FEATURE TWO}" (8.8-11.2), "{FEATURE THREE}" (11.2-14.4) | lead and bass from 4.1, a blip on each grab |
| 14.4-24.0 | 10.1 | Boss: lands with a shake on 10.1, its name and a 5-segment HP bar above it; hits on beat 1 of bars 11 to 15, the fifth (15.1) the KO; pixel burst to 24.0 | "{THE PROBLEM}" (14.4-22.4) | a hit sound on each hit, the KO run on 22.4 |
| 24.0-28.8 | 16.1 | Clear: iris on the hero from the cut onto SKY with a NIGHT panel; STAGE CLEAR on 16.2; the score counts 17.1 to 17.3 and settles | "STAGE CLEAR" (24.4-28.8), "SCORE" (25.6-28.8), "{123450}" (26.4-28.8) | clear fanfare, a blip each step while the score counts |
| 28.8-32.0 | 19.1 | End card: product, call to action and address on the NIGHT panel; still from 31.0 | "{PRODUCT}" (28.8-32.0), "{CALL TO ACTION}" (29.2-32.0), "{SITE.EXAMPLE}" (29.6-32.0) | a closing chord held to the end |

## Build notes

- `TIMELINE = [Scene("title", 12), Transition("wipe", 1, 0), Scene("stage", 24), Scene("boss", 24), Transition("iris", 1, 0), Scene("clear", 12), Scene("end", 8)]` in beats, `compile_schedule(TIMELINE, bpm=BPM)`.
- Each frame: draw both scenes of a window on the virtual screen (`Image.new("RGB", (E.W // k, E.H // k))`, ImageDraw rectangles, points and text), blend them with the transition there, then `.resize((E.W, E.H), Image.NEAREST)`. Palette colours as RGB tuples, `hexrgb(...)[:3]`, made at module level.
- Registry: each string's `box` is its virtual `ImageDraw.textbbox`, times the layer scale plus the layer's offset, times k; `px` is 8 x k x the layer scale; `bold` False; `fg` its palette colour. The score is `ticker=True`.
- Lint: each `ImageDraw.text` call and the `ImageFont.load` line is a Q1205 NOTE by design; silence each with the text-ok pragma the lint names in its fix.
- Helpers: `stepped`, `rng`, `prog`, `lerp`, `clamp`, `hexrgb`, `scenes_at`, `transitions.wipe`, `transitions.iris`.
- CUES: the grabs (6.4, 8.8, 11.2), the hits (16.0, 17.6, 19.2, 20.8) and the KO as `{"t": 22.4, "label": "ko", "payoff": True}`, STAGE CLEAR (24.4), the score landing (26.4), every cut (4.8 and 24.0 sit inside windows: kind `audio`). `CUE_LAG = 0`. KEY_TIMES: 6.4, 16.0, 22.4, 24.4, 26.4 and 31.5. `STATIC = [(31.0, 32.0)]`.

## QA watch-outs

- Q208: keep every string on the bitmap-font route; one pasted-rectangle title is text the gates never see.
- Q205: report the scaled `textbbox` of the very call that draws; a hand box drifts.
- Q601: the hit flash is the boss sprite alone (192x192 px at 1080), here once a bar and never more than 3 in any second; no full-screen white on the KO or the clear.
- Q401: the HUD banner swaps in one frame, and each feature holds 2.4 s or more.
- Q501 and Q502: SKY carries every screen (grey 64); a NIGHT frame would sit one level over the floor of 25.
- Q402: 1x text is 48 px at 1080, the floor; nothing smaller.
- Q503: the arrow and the stars stop by 31.0.

## Variations

- 9:16: virtual 180x320, HUD at the top, the playfield a band at y 110 to 230 with ground under it, text panels in the lower third and the bottom 70 virtual px (420 px) kept clear; a 2x title fits 12 characters a line.
- 22.4 s: 14 bars, title (2), stage with two grabs (4), boss with three hits (4), clear (2), end card (2).
