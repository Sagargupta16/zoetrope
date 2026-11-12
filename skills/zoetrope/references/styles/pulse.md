# S-pulse · Beat-locked kinetic type reel (20 s)
**Source:** designed for this skill on 2026-10-31 and rewritten from the engine on 2026-11-01, no outside reference · our build: none yet (each beat map passes `qa.py holds` as written)
**Use when:** "kinetic type reel", "words on the beat", "text reel for instagram", "lyric style captions"
**Defaults:** 20 s (15 to 30) · 9:16 1080x1920, 1:1 cut · 30 fps · 120 BPM, music, no voice
**Spec:** family=music length=15-30 size=1080x1920 fps=30 audio=music kit=-

Beat-locked kinetic type for 9:16 social reels: words land on the beat, build into short phrases, drop on one payoff word and end on a handle.

## Use when

- A 15 to 30 s vertical reel where the words are the picture: a hook, two or three short phrases, one payoff word, a call to action.
- About 14 words in all, one idea per phrase, each word worth a beat.
- Not for: explaining how something works (blueprint), figures (ledger), showing an interface (signal), anything a viewer must read in long lines.

## Format

- Default 9:16, 1080x1920, 30 fps, 20 s: 10 bars at 120 BPM (a beat is 15 frames, a bar 2 s). A phrase is 2 bars.
- `HOLD_PROFILE = "display"`. A 1:1 cut is in Variations.

## Look

| Role | Hex | Use |
|---|---|---|
| FIELD_A | #221C4A | field for odd phrases, PIL grey 35, luminance 0.017 |
| FIELD_B | #3B1747 | field for even phrases and the end card, grey 39, luminance 0.020 |
| FLARE | #FFF3D6 | the drop's field, once per reel |
| TYPE | #FFF8EC | words |
| HOT | #FF5C93 | the one stressed word of a phrase |
| ZEST | #C8F24A | the handle, small accents |

| Text | On | WCAG ratio |
|---|---|---|
| TYPE | FIELD_A / FIELD_B | 14.92:1 / 14.21:1 |
| HOT | FIELD_A / FIELD_B | 5.40:1 / 5.15:1 |
| ZEST | FIELD_A / FIELD_B | 12.19:1 / 11.62:1 |
| FIELD_A (the payoff word) | FLARE | 14.29:1 |

**Flashes, by design.** FIELD_A and FIELD_B differ by 0.003 in relative luminance, far under the 0.1 that makes a flash transition, so a swap on a bar line is not a flash. FLARE is entered once and left once, 4 s apart. HOT's red share R/(R+G+B) is 0.52, under the 0.8 of a red flash.

**Type.** Bold slot: Anton Regular (the words; a single heavy weight, shipped as a static file). Regular slot: Barlow SemiBold (handle, call to action). SIL OFL 1.1, from Google Fonts (families.md, Fonts for the six panel cards). Fallbacks: Windows Impact and Segoe UI Semibold, macOS Impact and Helvetica Neue, Linux DejaVu Sans Condensed Bold and DejaVu Sans. Words in capitals, 200 to 300 px at 1080 on the short side; payoff word up to 0.84 W; handle 64; call to action 56.

**Grid.** Text column x 96 to 940, live band y 260 to 1480. The bottom 440 px, and the right 140 px below y 1000, stay empty for app controls. Words stack left-aligned, one or two to a line, each line pitched at its tallest box plus 16 px; the phrase block centres in the band.

## Motion

- A word lands on its beat frame at scale 1.25 and settles to 1.0 over 4 frames (`ease_out_cubic`), drawn with `text(img, word, xy, size, TYPE, anchor, scale=k)` and boxed with `text_box(word, xy, size * k, anchor)`.
- Phrases accumulate: a word stays until its phrase clears on the next bar line. Never swap one word for another on each beat; every word rests 1.0 s or more.
- On each beat of a phrase's second bar the whole block bumps to 1.04 and back over 6 frames (`ease_out_cubic`) around its centre.
- Fields change on bar lines only, A and B in turn; hard cuts, no transitions. The drop cuts to FLARE on 7.1 and back to FIELD_B on 9.1.
- No shake or jitter on text; the energy comes from the landings and the bumps.

## Sound

- 120 BPM, scored with `synth.py` inside `synth.recording()` in place of `audio.render_audio` (references/beat-sync.md, Stems and the cue sheet).
- Bed: `synth.kick` on every beat, `synth.clap` on 2 and 4, `synth.hat` on the offbeats, `synth.bass` on the eighths along the root.
- Each landing: `synth.pluck` on the SFX stem, one scale step higher per word, its onset on the word's frame and its CUES label on it.
- Bar 6 strips back to the kick and a `synth.riser(2.0)` (`sound="riser"`, end on 12.0). The drop: `synth.boom` on 12.0 with the bed's kick left out there, then full drums. On 16.0 the drums stop; a `synth.pad` chord and one pluck carry the end card.

## Beat map

| Time (s) | Bar.beat | Visuals | On-screen text | Audio |
|---|---|---|---|---|
| 0.0-4.0 | 1.1 | Phrase 1 on FIELD_A: the first word set at frame 0; the next land on 1.2 and 1.3; bumps on bar 2 | "{first}" (0.0-4.0), "{second}" (0.5-4.0), "{third}" (1.0-4.0) | bed from 1.1, pluck per word |
| 4.0-8.0 | 3.1 | Phrase 2 on FIELD_B: four words land on 3.1 to 3.4 | "{word}" (4.0-8.0), "{word}" (4.5-8.0), "{word}" (5.0-8.0), "{word}" (5.5-8.0) | plucks rising |
| 8.0-12.0 | 5.1 | Phrase 3 on FIELD_A: four words on 5.1 to 5.4; bar 6 strips back | "{word}" (8.0-12.0), "{word}" (8.5-12.0), "{word}" (9.0-12.0), "{word}" (9.5-12.0) | riser over bar 6, end on 12.0 |
| 12.0-16.0 | 7.1 | Drop: FLARE, the payoff word across 0.84 W in FIELD_A ink, bumping on every beat | "{payoff}" (12.0-16.0) | boom on 12.0, full drums |
| 16.0-20.0 | 9.1 | End card on FIELD_B: handle in ZEST, call to action under it; still from 19.0 | "{@handle}" (16.0-20.0), "{call to action}" (16.5-20.0) | drums out, pad and one pluck |

## Build notes

- `TIMELINE = [Scene("phrase1", 8), Scene("phrase2", 8), Scene("phrase3", 8), Scene("drop", 8), Scene("end", 8)]` in beats, `compile_schedule(TIMELINE, bpm=BPM)`.
- Keep the copy as data: each phrase a list of (word, beat it lands on), its stressed word marked. `layout(t)` places every landed word and feeds both `draw()` and `text_items()`.
- Register each word as its own item, in capitals as drawn, with its scaled box: its rest then runs from its landing to the clear. A phrase registered as one growing string gives every partial phrase a hold it cannot meet.
- Size each word with `fit_size(word, 300, 844, floor=120)`; a word that needs less than 120 px is too long for this style, so change the word.
- Helpers: `canvas` (fields), `text`, `text_box`, `text_w`, `fit_size`, `prog`, `lerp`, `clamp`, `ease_out_cubic`.
- CUES: every landing (kind `both`), the drop as `{"t": 12.0, "label": "drop", "payoff": True}`, the end card (16.0). KEY_TIMES: the frame after each phrase's last word settles (1.2, 5.7, 9.7), 12.2 and 19.5. `STATIC = [(19.0, 20.0)]`.

## QA watch-outs

- Q401: every word here rests 2.5 s or more, because words land in a phrase's first bar and stay through its second; land none later than beat 1 of the second bar.
- Q202: words on one line keep a space of 0.25 em between their boxes; lines never touch.
- Q207: a phrase clears on the bar line and the next phrase's first word lands on that frame, so the changeover gap is 0 or 1 frame.
- Q601 and Q603: only the A and B swap on bar lines and the one FLARE drop; never flip the field on beats, and never strobe a word.
- Q501: frame 0 is the first word on FIELD_A, the reel's cover.
- Safe area: the bottom 440 px stays empty even though the gate only asks for 4 percent.

## Variations

- 16 s: 8 bars, phrase 1, phrase 2, drop, end card.
- 1:1 at 1080x1080: live band y 120 to 960, words 180 to 240 px, three words at most a phrase, handle under the block, nothing reserved at the bottom.
