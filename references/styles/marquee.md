# S-marquee · Logo sting or title card from flat parts (6 s)
**Source:** designed for this skill on 2026-10-31 and rewritten from the engine on 2026-11-01, no outside reference · our build: none yet (each beat map passes `qa.py holds` as written)
**Use when:** "title card", "short logo sting", "wordmark intro", "outro card"
**Defaults:** 6 s (4 to 10) · 16:9 1920x1080, also 9:16 and 1:1 · 30 fps · 120 BPM, music, no voice
**Spec:** family=logo length=4-10 size=1920x1080 fps=30 audio=music kit=-

A logo sting or title card: flat parts and letters that gather on the beat and lock into one mark, then hold.

## Use when

- 4 to 10 s to open or close another video, or to stand alone as a title card: a name, an emblem, at most a three-word tagline.
- The user's own mark only when they supply it (a PNG with transparency, at least twice its display size). Without one, the mark is a wordmark set in type beside an emblem of the style's own abstract parts.
- Not for: a launch with ideas (signal), lines of copy (pulse). Never trace, redraw or approximate a mark the user did not supply, theirs or anyone else's.

## Format

- Default 16:9, 1920x1080, 30 fps, 6 s: 3 bars at 120 BPM (a beat is 15 frames). Also 9:16 and 1:1.
- `HOLD_PROFILE = "display"`.

## Look

| Role | Hex | Use |
|---|---|---|
| STAGE_TOP | #33264A | top of the stage gradient, PIL grey 46 |
| STAGE_LOW | #1F1733 | bottom of the gradient, grey 29 |
| MARK | #F5C451 | the emblem's parts |
| TYPE | #FBF6EC | the wordmark |
| TAG | #CDBFE6 | the tagline |
| SPARK | #FF7A5C | one small part and the lock ring, shapes only |

| Text | On | WCAG ratio |
|---|---|---|
| TYPE | STAGE_TOP / STAGE_LOW | 12.85:1 / 15.87:1 |
| TAG | STAGE_TOP / STAGE_LOW | 8.04:1 / 9.92:1 |
| MARK (wordmark set in gold) | STAGE_TOP / STAGE_LOW | 8.50:1 / 10.50:1 |
| STAGE_LOW (text on a gold plate) | MARK | 10.50:1 |

Brand colours supplied with the mark replace MARK and TYPE only after `qa.contrast` clears 4.5:1 against both stage colours.

**Type.** Bold slot: Fraunces Bold (the wordmark). Regular slot: Outfit Regular (the tagline, in capitals, letter-spaced). SIL OFL 1.1, from Google Fonts, static files (families.md, Fonts for the six panel cards). Fallbacks: Windows Georgia Bold and Segoe UI, macOS Georgia Bold and Helvetica, Linux DejaVu Serif Bold and DejaVu Sans. Sizes at 1080: wordmark up to 200 (`fit_size` against 0.6 W, 0.8 W at 9:16), tagline 44 with `tracking=8`.

**Grid.** One centred lockup, inside the middle 70 percent of the width and 60 percent of the height. 16:9: emblem left (a square 0.28 of the short side), wordmark right, the group centred on y 0.46 H; the tagline 48 px under the wordmark's baseline.

## Motion

- Gather: four parts by default, three to five at most (rounded bars, a disc, a dot), sit scattered inside the frame at frame 0. Each moves with `spring(t, 300, 18)`, which first reaches its place 4.3 frames after release, overshoots 15 percent and is at rest in 0.53 s: release a part 5 frames before its beat, so the beat frame is its first frame on target.
- Lock on 2.1: the last part lands, the emblem kicks to scale 1.06 and back over 6 frames (`ease_out_cubic`), and one thin SPARK ring grows and fades over 0.3 s.
- Letters drop 40 px from alpha 0 over 12 frames (`ease_out_back`), one after another from 2.1, spaced so the last lands on 2.3: spacing 0.6 s / (letters - 1), at least 1 frame. From 2.3 the word is drawn whole.
- The tagline fades up over 0.4 s (`ease_out_expo`) on 2.4, at fixed tracking, one beat after the word is whole. Bar 3 is the hold; from 5.0 nothing moves.
- One continuous shot: the two scenes are phases with no visual cut, so motion reads absolute t, never a phase's local time.

## Sound

- 120 BPM. A sting needs no bed: score it with `synth.py` inside `synth.recording()` in place of `audio.render_audio` (references/beat-sync.md, Stems and the cue sheet).
- `synth.riser(2.0)` placed with `sound="riser"`, which lands its end on 2.0; `synth.tick` on each part's landing; `synth.boom` with its onset on the lock; a triad of `synth.pluck` summed into one buffer through `synth.reverb(x, 0.25)` and placed once on 3.0; a `synth.pad` from 3.0 to the end with `align="pad"`.
- Gains before `audio.master`: boom 0.5, riser 0.4, ticks 0.4, chord 0.35, pad 0.3.

## Beat map

| Time (s) | Bar.beat | Visuals | On-screen text | Audio |
|---|---|---|---|---|
| 0.0-2.0 | 1.1 | Gather: the parts scattered at frame 0; one lands on each of 1.2, 1.3 and 1.4 | none | riser over bar 1, ticks on 0.5, 1.0, 1.5 |
| 2.0-6.0 | 2.1 | Lock: the last part lands on 2.1 with the kick and ring; letters drop from 2.1, the word whole on 2.3; the tagline fades up under it on 2.4; bar 3 holds the lockup as the end card, still from 5.0 | "{brand}" (3.0-6.0), "{three word tagline}" (3.5-6.0) | boom on 2.0, plucked chord on 3.0, pad from 3.0 to the end |

## Build notes

- `TIMELINE = [Scene("gather", 4), Scene("lock", 8)]` in beats, `compile_schedule(TIMELINE, bpm=BPM)`: the one cut is the lock, a real moment, so no cue sits where nothing happens.
- Helpers: `gradient` (STAGE_TOP to STAGE_LOW), `rrect`, `shadow`, `text`, `text_box` (pass `tracking=` for the tagline), `text_w`, `fit_size`, `spring`, `settle_time`, `ease_out_back`, `ease_out_cubic`, `ease_out_expo`, `prog`, `lerp`.
- Letters: put letter i at `x0 + text_w(word[:i + 1]) - text_w(word[i])`, so the letters land where the whole word draws them. While they move, register each as its own item with `texture=True` (Q204 still needs them reported); from 3.0 register the word as one item.
- A supplied mark: load it once at import (`Image.open(...).convert("RGBA")`), resize once with `Image.LANCZOS`, and let it enter whole on the lock (scale 0.92 to 1 on the same spring, alpha 0 to 1) as the parts converge on it. Never stretch, recolour or cut it apart.
- Without one, the emblem is the gathered parts; if it reads as any known brand's logo, change the parts.
- CUES: the three landings (0.5, 1.0, 1.5), the lock as `{"t": 2.0, "label": "lock", "payoff": True}`, the word (3.0). KEY_TIMES: 2.0, 3.0, 5.5. `STATIC = [(5.0, 6.0)]`.
- Grain is off by default; if the dark gradient bands, add `grain.grain(img, t, std=1.2)` last and drop STATIC (grain moves every 2 frames).

## QA watch-outs

- Q501: frame 0 is the scattered parts on the stage (grey 46 to 29, mean about 37), never black. Offer the user a poster PNG of the final frame for platforms that pick their own thumbnail.
- Q204 and Q205: every flying letter is drawn text, so it is registered with its own box.
- Q401: the word rests 3 s and the tagline about 2.3 s, room for five words and 32 characters; keep it to three.
- Q601: the lock ring is a thin outline; no white frame, no full-frame flash on the boom.
- Q804: the chord is one placed sound, and no other sound sits within 3 frames of the payoff.
- Q803 and Q503: the pad rings to 6.0 while the picture holds still for the last second.
- Lettering inside a supplied PNG is invisible to the recorder: check its contrast on the proof with `qa.region_contrast`.

## Variations

- 9:16 and 1:1: emblem above the wordmark (0.36 W wide), wordmark fit to 0.8 W, tagline under it, the group centred on y 0.42 H.
- 4 s: 2 bars, parts on 1.2 to 1.4, the lock on 2.1, letters dropping from 1.4 so the word is whole on 2.2, no tagline.
