# QA gates

Read this before the final render and again before the delivery message. Every gate below runs inside the engine: Python with PIL and numpy, plus the ffmpeg and ffprobe the build found. No gate needs a network.

Run all gates on the final file, not only on stills. `run_all.py full` and `run_all.py audio` run them on the file they make and say what happened; `qa.py check` runs them again on any file.

## Automated check: `qa.py check`

`python qa.py check <video> --scenes . --size WxH --fps N [--bpm N] [--max-mb N] [--silent] [--json qa.json] [--baseline approved/qa.json] [--registry-procs N]` runs every gate that can be measured on the finished file. It first prints `qa check: <file> (written YYYY-MM-DD HH:MM:SS, <MB> MB)` (the reviewer quotes that time), then one row per finding, for example:

```
NOT CHECKED Q902  scenes.py has no CUES, so cue sync did not run [0 checked] -> list every moment sound and picture share in CUES = [(t, label, kind)], or set NO_CUES = True
```

Each row is the status, the code, the message, the worst moment (`[worst 2.07 s]`, the frame to open first), how many items the gate looked at, and the fix after `->`. A defect seen on many frames is one row with its spans. At most 10 rows a code are printed; `--json` writes every row with its fields (`t0`, `t1`, `worst_t`, `item`, `metric`, `limit`, `spans`, `considered`). The last line reads `QA: PASS`, `QA: FIX (n)` or `QA: NOT CHECKED (n)` with the counts. Exit code: 1 on any FIX, else 2 on any NOT CHECKED, else 0.

- **PASS**: measured and inside the limit. "None by design" is a PASS that says so.
- **FIX**: fix it before delivery.
- **NOTE**: needs a look but may be intended (a planned silence, a designed one-frame accent). List an intended one in `ALLOW` (below).
- **NOT CHECKED**: the gate had nothing to look at where something was declared or expected: text drawn with no registry, no `CUES`, a cue sheet without its stems, a gate module that raised (one `Q100` row naming the module and the line; the other modules still run). It is not a pass: `run_all.py` rejects a file with any NOT CHECKED row, as it does a FIX.

`--scenes .` loads the build's scenes.py and the supersampling in its `build.json`, so the registry gates, cue sync and the scans that compare with SCHEDULE run (the approval rows read `approved/` in the build folder, or beside the video without it); with `--json` it also adds every finding's `worst_t` to that folder's `review_times.json`. Without `--scenes` the check prints `not checked here: safe area, overlap, contrast, reading holds and cue sync (...)` and writes nothing beside the video. Every check ends `not checked by any script: how it looks and sounds to a person`. `SILENT = True` in scenes.py counts as `--silent`.

qa.py runs the ffmpeg on PATH, else `/opt/homebrew/bin` or `/usr/local/bin` (`contract.find_ffmpeg`), and the ffprobe beside it. Output is ASCII, other characters as `\u` escapes: a redirected Windows console is cp1252, and an arrow in a caption once crashed a passing build. Every decode closes stdin and checks its frame count against ffprobe's (within 1), so a short decode raises instead of passing on part of the film.

The same gates run inside the build:

- `run_all.py proof`: Q501 on drawn frame 0, gates 2 to 4 from the registry, the text recorder (Q204 to Q209), the purity gate (Q1201) and the lint (Q1202 to Q1206, Q904, Q905). Rows go to `qa_proof.json`; the last line is `PROOF: PASS` (or FIX, NOT CHECKED); exit 1 on FIX, 2 on NOT CHECKED.
- `run_all.py full` and `audio`: the master's Q805, the frame scans on `thumbs.npy` (Q1101 to Q1104, every drawn frame), then `qa.check` on the file. Any FIX or NOT CHECKED row, the approval codes aside, renames the file `<name>.rejected.mp4`; a clean run ends with the `APPROVAL` line and one `DELIVERED` line (`engine.md`).

### Codes

`contract.CODES` is the one table of codes (owner module, gate, status on failure, meaning); `qa.py selftest` reads it too. Gate 0 is the check itself. Gate 1 also holds the pointers that send the reviewer to frames (Q11xx), purity and lint (Q12xx) and the approval (Q13xx). "On failure" is the code's status in `contract.CODES`; where a code can also be NOTE or NOT CHECKED, its text says when.

| Code | Gate | Owner | On failure | What it flags |
|---|---|---|---|---|
| Q100 | 0 | `qa` | NOT CHECKED | A gate module raised, so its gates did not run; the row names the module and the engine line, and the other modules still run |
| Q200 | 2 | `qa` | NOT CHECKED | No `text_items(t)` and no `NO_TEXT`: gates 2 to 4 did not run. Also when `text_items(t)` reports nothing readable on any frame, or only the older kit form (items without `s` and `box`) |
| Q201 | 2 | `qa` | FIX | Text at rest (alpha 0.98) outside the 4 percent safe area, on any frame; worst_t at the largest overflow |
| Q202 | 2 | `qa` | FIX | Two texts overlapping at rest (boxes shrunk 1 px); one row per pair, worst_t at the largest shared area |
| Q203 | 2 | `qa` | FIX | Two different texts overlapping while either fades (alpha over 0.05): a crossfade in one place |
| Q204 | 2 | `qa_registry` | FIX | Text `draw(t)` paints that `text_items(t)` does not report, recorded while draw runs; FIX at alpha 0.5 or more and 24 px or more at 1080, else NOTE (symbols alone are always NOTE) |
| Q205 | 2 | `qa_registry` | FIX | Registry box more than 2 px from the drawn glyph box (`engine.text_box` boxes; a hand box must hold the glyphs and reach at most 0.6 em past them). NOTE when no position can be compared (numpy composites, rotations); NOT CHECKED for a registry with no box |
| Q206 | 2 | `qa_registry` | FIX | Registered text covered by something drawn after it: under 0.7 of its ink changes when the frame is drawn without it, where Q202, Q203 and Q301 look. NOTE when under half the tests could be measured; NOT CHECKED when draw(t) is impure inside a tested text |
| Q207 | 2 | `qa` | NOTE | Text replaced in one place leaves a gap of 3 frames to under 0.5 s (the Netflix gap rule: 2 frames or less, or 0.5 s or more) |
| Q208 | 2 | `qa_registry` | NOT CHECKED | The text recorder saw no `ImageDraw.text` call while text is reported (bitmap fonts, `getmask` plus paste), or could not run |
| Q209 | 2 | `qa_registry` | NOTE | `text_items(t)` reports text at alpha 0.5 or more that nothing draws (a stale registry); one row per moment, one in all when the items give no alpha |
| Q301 | 3 | `qa` | FIX | Contrast against a ring of real pixels at the first, middle and last frame of every rest: 4.5:1, or 3:1 for large text (36 px, or 24 px bold, at 1080). NOT CHECKED for text with no `fg` |
| Q401 | 4 | `qa` | FIX | Longest rest under max(floor, 0.5 s + 0.3 s per word, characters / cps + pad) for the card's `HOLD_PROFILE` or the item's `profile`; a `ticker=True` item only on the value it settles on |
| Q402 | 4 | `qa` | NOTE | Key text under 36 px at 1080 (mark decoration `texture=True`) |
| Q403 | 4 | `qa` | FIX | A registered text that never reaches rest (alpha 0.98) |
| Q404 | 4 | `qa` | FIX | An item with `reveal_end`: at that time its ink must reach both ends of its box within 3 px and be 0.98 of its rest-frame ink |
| Q501 | 5 | `qa` | FIX | First frame, decoded at full size as a player shows it: grey mean 25 or less, or std 12 or less |
| Q502 | 5 | `qa` | FIX | Last frame, decoded the same way: grey mean 25 or less (a fade to black) |
| Q503 | 5 | `qa` | NOTE | The last second changes 10/255 or more (64x36 grey): no 1 s end card hold |
| Q601 | 6 | `qa_scan` | FIX | More than 3 general flashes in any sliding second (WCAG 2.2): linear relative luminance, transitions of 0.1 with the darker state under 0.8, over a quarter of the frame or of a 10 degree window |
| Q602 | 6 | `qa_scan` | FIX | More than 3 red flashes in any sliding second (WCAG 2.2 note 3: one state R/(R+G+B) of 0.8 or more, the two states over 0.2 apart in CIE 1976 u'v'), same area rule |
| Q603 | 6 | `qa_scan` | NOTE | Extended band (IRIS): 4 to 6 transitions a second held for 4 s of any 5 s; one `ALLOW` entry must hold the whole passage (1 s slack) |
| Q701 | 7 | `qa` | FIX | Duration more than 0.1 s off `--duration` or `DURATION` |
| Q702 | 7 | `qa` | FIX | Frame rate not `--fps` |
| Q703 | 7 | `qa` | FIX | Resolution not `--size` |
| Q704 | 7 | `qa` | FIX | Frame count more than 1 off duration x fps |
| Q705 | 7 | `qa` | FIX | Pixel format not `yuv420p` (H.264 only: another codec gives NOT CHECKED) |
| Q706 | 7 | `qa` | FIX | No audio stream (skip with `--silent` or `SILENT = True`) |
| Q707 | 7 | `qa` | FIX | Colour tags not bt709 / bt709 / bt709 / tv (space, primaries, transfer, range; H.264 only) |
| Q708 | 7 | `qa` | FIX | Saturated swatches through `contract.COLOR_VF` and `COLOR_FLAGS` with libx264 and back through `DECODE_709` more than 8 levels off: the chain on this ffmpeg, not the file. NOT CHECKED when the swatch encode cannot run |
| Q801 | 8 | `qa` | FIX | Integrated loudness more than 1 LU off -14 LUFS (ebur128) |
| Q802 | 8 | `qa_stack` | FIX | True peak over -1 dBTP; the FIX names the moment, every cue sheet sound sounding within 50 ms of it, the music bed's level there, every 100 ms frame over -1 and a cut order |
| Q803 | 8 | `qa` | NOTE | A near-silent second (under -60 dBFS) inside the piece (seconds 1 to n - 2; a piece under 3 s has none). NOT CHECKED when the audio decodes to no samples |
| Q804 | 8 | `qa_stack` | NOTE | Stacked sounds in `cuesheet.json`: 2 or more heavy sounds within 3 frames, a second sound on a payoff cue, more than 2 sounds in any 100 ms (a taste rule). No cue sheet is one NOTE; an unreadable one NOT CHECKED |
| Q805 | 8 | `audio` | FIX | `audio.master` missed -14 LUFS by over 0.1 LU or its ceiling by over 0.05 dB, or its limiter took over 0.5 LU or over 6 dB at one moment (worst_t: the deepest cut). Printed by `run_all.py`, not by `qa.py check` |
| Q901 | 9 | `qa` | NOTE | A cut (`CUTS`, else every `SCHEDULE` start after 0) more than 1 frame off the BPM grid |
| Q902 | 9 | `qa_sync` | FIX | A cue's own sound, found on the SFX stem from the cue sheet, late by more than 1 frame (never over 60 ms) or early by more than 40 ms; NOTE outside -5..+15 ms and for the picture side. NOT CHECKED without `CUES` (and no `NO_CUES`), for a sheet without its buffers or stems, or a twin it cannot tell apart |
| Q903 | 9 | `qa_sync` | FIX | Decoded mp4 audio more than 1 ms off `mix.wav` (and `mix_raw.wav` when there) in three 2 s windows, or the audio and video streams starting more than 1 ms apart |
| Q904 | 9 | `qa_lint` | NOTE | A `SCHEDULE`, `DURATION` or `CUES` time more than 1e-3 frame off the frame grid |
| Q905 | 9 | `qa_lint` | NOTE | One beat is not a whole number of frames (the fix lists the BPMs that are) |
| Q906 | 9 | `qa_sync` | FIX | `qa.py calib`: one white frame and a one-frame 1 kHz blip through `audio.master` and the mux come back more than 1 ms apart, or the stream start times differ |
| Q1001 | 10 | `qa` | FIX | File over `--max-mb`, else over `BUDGET_MB` in scenes.py (the row says which); no cap is a PASS that says so |
| Q1002 | 10 | `qa` | NOTE | Bitrate over 12 Mb/s (flat graphics land at 1 to 5; baked grain is the usual cause) |
| Q1101 | 1 | `qa_scan` | NOTE | One-frame pop: a frame unlike both neighbours while they agree, in still context, at least 0.2 percent of the frame 12 levels off; each pop gets an f-2..f+2 strip |
| Q1102 | 1 | `qa_scan` | NOTE | Frozen run of 3 s or more outside text holds (the registry or `scenes.HOLDS`), near-black runs and the last 2 s |
| Q1103 | 1 | `qa_scan` | NOTE | Hard cut (bright, or between dark frames) not on a `SCHEDULE` start, a `CUTS` time, a `CUES` entry (allowing `CUE_LAG`) or inside `WINDOWS` |
| Q1104 | 1 | `qa_scan` | NOTE | Stall: one frame repeats the one before between moves over 0.8 levels (not on twos, not a held flash, not inside `WINDOWS` or the 2 frames after a cut) |
| Q1105 | 1 | `qa_scan` | FIX | The decoded file against `thumbs.npy`: a frame whose mean grey differs by over 4 levels, or a different frame count. NOT CHECKED with `frames.hash` but no `thumbs.npy` |
| Q1201 | 1 | `qa_purity` | FIX | `draw(t)` not pure: a sampled frame hashes differently drawn in order, reversed in a fresh `python -I` process, or through a spawn pool. NOT CHECKED when a sampled frame raises or a fresh process cannot run |
| Q1202 | 1 | `qa_lint` | FIX | Unseeded randomness, clock reads, the process id or `hash()` of a str in scenes.py or its local modules |
| Q1203 | 1 | `qa_lint` | NOTE | Module state written inside a function (a counter, a cache, a mutable default) |
| Q1204 | 1 | `qa_lint` | NOTE | scenes.py redefines an engine helper, or the contract clock engine.py re-exports |
| Q1205 | 1 | `qa_lint` | NOTE | Text drawn outside the engine text helpers (text into a mask image is allowed) |
| Q1206 | 1 | `qa_lint` | NOTE | A colour literal inside a function instead of the palette block |
| Q1301 | 1 | `qa_approve` | FIX | With an approval in `approved/`: the approved key frames redrawn now differ, or the file is not the approved one (NOTE: only the audio changed, or an override is recorded) |
| Q1302 | 1 | `qa_approve` | FIX | With `--baseline approved/qa.json`: a gate went from PASS to FIX. NOT CHECKED when baseline gates made no row in this run |
| Q1303 | 1 | `qa_approve` | FIX | `qa.py diff`: frames or 100 ms audio blocks changed since the approval outside `--expect` (NOTE inside it), or an `--expect` window that saw no change |
| Q1304 | 1 | `qa_approve` | NOT CHECKED | The frame size changed since the approval, or Python (major.minor), Pillow, numpy or a font file changed and a frame moved (NOTE: it changed and every frame redraws the same) |

### What scenes.py declares

The gates read these names from the build's scenes.py; `engine/scenes.py` shows each one. Compute each text's layout in one function that both `draw()` and `text_items()` call (the template's `layout(t)`), or the registry drifts from the picture; Q204 catches that drift from the drawn side.

| Name | What |
|---|---|
| `text_items(t)` | Every text drawn at t, as dicts (keys below) |
| `CUES` | Every moment sound and picture share (forms below). The name is `CUES`: a build that keeps its cues in `CUE` gets Q902 NOT CHECKED |
| `CUE_LAG` | Frames the picture may trail a cue by design (2 for the pixel-art battle style) |
| `KEY_TIMES` | Extra moments for the key sheet: `t` or `(t, why)` |
| `CUTS`, `WINDOWS` | Scene changes, and transition windows `(t0, t1, out, in)`, from `compile_schedule`. Q901 and Q1103 read `CUTS`; the scans and the recorder read `WINDOWS` |
| `HOLDS` | `[(text, drawn at, exit at), ...]`, the 2.1.0 hold table some kits ship; Q1102 exempts its spans |
| `HOLD_PROFILE` | The card's reading pace for Q401: `display` (default), `caption`, `slow` (any case), or a dict of `cps`, `pad`, `floor` |
| `BUDGET_MB` | The size budget: caps the encode, and is Q1001's cap when `--max-mb` is not given |
| `NO_TEXT`, `NO_CUES`, `SILENT` | None by design: the text gates, cue sync or the audio gates are a PASS that says so, not NOT CHECKED |
| `ALLOW` | `{code: [t or (t0, t1)]}`: designed moments a NOTE-level scan lets through (below) |

`text_items(t)` items:

| Key | Meaning |
|---|---|
| `s` | The string as drawn |
| `box` | (l, t, r, b) in output px, from `engine.text_box` with the font, xy, anchor and `tracking=` the draw uses. Masked or clipped text reports its visible box: its text_box cut by the clip, the mask edge or the frame edge, as a viewer sees it (hidden ink never counts for overlap or the safe area); inside a wipe, iris, clock, blinds or luma transition that is the part the mask shows. Report alpha 0, or leave the item out, while a text is fully hidden |
| `fg` | Its colour (Q301, Q404) |
| `alpha` | 0 to 1: 0.98 or more is at rest, over 0.05 is on screen |
| `px`, `bold` | Font size in output px and weight (Q301's large text, Q402) |
| `texture` | True for decoration nobody must read: gates 2 to 4 skip it |
| `profile` | Optional: this item's reading pace, as `HOLD_PROFILE`; None takes the card's |
| `reveal_end` | Optional: when its reveal must be complete. Q404 checks it on pixels against the box, so the box must be the whole string's |
| `ticker` | True for a counter or a clock: its values on the way need no reading hold (Q401) and are not sampled for contrast (Q301); the value a run settles on is held to both |

`CUES` entries, read by `contract.cues(scenes)` and sorted by time:

- `(t, label)` or `(t, label, kind)`, kind `both` (default), `audio` or `picture`. A cut inside a transition window has no hard picture change: give its cue kind `audio`.
- A dict `{"t": ..., "label": ..., "kind": ...}` that keeps its other keys: `payoff=True` (Q804 keeps other sounds off it), `band=(lo, hi)` in Hz and `region=(x0, y0, x1, y1)` in output px (they aim the no-cue-sheet detector, gate 9).
- One dict of label to a time or a list of times: `CUES = dict(bell=[1.0, 8.6], warm=12.0)`.

**Registry completeness.** While draw(t) runs, `qa_registry` records every `ImageDraw.text` call (the class attribute, so `from engine import *` cannot bypass it) and follows each record through crops, pastes, resizes, blends and composites to where it lands on the frame, so text on a tile, a cached sprite or a window layer is found at its real place and opacity. Every frame of a transition or caption changeover is drawn, plus one every 0.25 s. Text drawn but not reported is Q204; a registry box off the drawn one is Q205; registered text covered by something drawn after it is Q206 (OVH textcheck's differential: the frame drawn without that text, 0.7 of its ink must change); registered text that nothing draws is Q209. Text that never passes through `ImageDraw.text` (a bitmap font, `font.getmask` plus paste, numpy glyphs) cannot be seen: when that is all the text, Q208 is NOT CHECKED. Heavy pieces use up to 8 worker processes when one would take over 20 s; `--registry-procs N` sets it.

**ALLOW.** `ALLOW = {"Q1101": [16.0], "Q1102": [(20.0, 26.0)]}` lists times or spans, matched within about a frame (Q803 within its second, Q603 within 1 s). It clears NOTE rows only, never a FIX: Q204 (its NOTE rows), Q207, Q209, Q402, Q603 (one entry must hold the whole passage), Q803, Q804, Q901, Q902 (NOTE rows), Q904 and Q1101 to Q1104.

### Review times (`review_times.json`)

One list, in the working folder, of every moment a sheet or a reviewer must see. Each entry: `t` (seconds, 3 decimals; one entry per time), `why` (every reason there, joined with "; "; a finding's starts with its code and status), `kinds` (finding, changed, pop, cut, window, key, audio, rest, in that rank order) and `kind` (the highest of them), `code`, `status` (the most severe seen there: FIX over NOT CHECKED over NOTE), `strip` (true asks `proof_strips.png` for frames f-2 to f+2) and `n` (the cell number on `proof_keys.png`, null when the cap left it off). `run_all.py proof` starts the file afresh but keeps `qa.py diff`'s changed entries with their code and status; `full` and `audio` add every finding of their verdict; `qa.py check --json --scenes .` adds the findings of the codes qa_scan does not record itself; the frame scans add `pop` entries with strips; `qa.py diff` adds `changed` ones. No module writes kind `audio` yet. `python proof.py keys` redraws the sheets from the file.

### Other subcommands

Sizes come from `build.json` (run_all.py writes it in every stage), else `frames.hash`, else run_all.py's constants, else 1920x1080 at 30 fps.

| Command | What it does |
|---|---|
| `qa.py look <video> [--times t,...] [--width 480]` | Small JPEG copies of frames and `review/look.jpg` (default every 5 s plus the last frame), so a model never reads a full-size frame |
| `qa.py holds <scenario.md> [--section N] [--profile display\|caption\|slow]` | Storyboard check before any build: each line's slot against its reading hold, with the words and characters the slot fits; exit 1 on any SHORT |
| `qa.py purity [--n 16] [--t T1,T2] [--grid S]` | Q1201 alone |
| `qa.py lint [scenes.py] [--all]` | Q1202 to Q1206, Q904 and Q905 |
| `qa.py owner --t S` or `--traceback FILE` | The scene function(s) a moment or a crash belongs to: both at a cut or inside a window; a shared helper routes to the scene functions that call it |
| `qa.py approve --review <reply> [--override WHY]` | Records the reviewed build in `approved/` |
| `qa.py diff [--expect t0-t1,...]` | What changed since the approval (Q1303, Q1304), with triptychs in `review/` |
| `qa.py verify [file]` | Re-hashes a file (for example the DELIVERED path) against the approval: exit 0 same, 1 differs, 2 no approval |
| `qa.py calib [--fps N] [--size WxH] [--out calib]` | Q906; it refuses a folder that holds a build |
| `qa.py audiostrip <video or mix.wav> --scenes .` | `review/audio.png` (below) |
| `qa.py selftest [--quick] [--only CODE[,CODE]] [--keep]` | Every gate against its planted faults (below) |

**`qa.py selftest`** proves the gates can still fail; it says nothing about a particular video. Run it from a fresh engine copy made with `cp -r engine/. <folder>/` (a `cp engine/*.py` copy leaves `qa_fixtures/` out, and every fixture module then reads MISSING).

- Each of the 73 cases in `engine/qa_fixtures/` feeds one gate a planted fault or a known-good input (fake registries, 640x360 scenes files, synthetic MP4s and WAVs, one 2 s build for the approval gates, all in a temp folder) and states the code, status, item, time and value the gate must report, within a tolerance. The template must pass `run_all.py proof` and `full` at 1920x1080 and 1080x1920 with no FIX and no NOT CHECKED.
- Every code in `contract.CODES` needs a fixture at its failure status, or an `EXPECTED_GAPS` entry with its reason (none today). Second statuses with no fixture yet: Q204 NOTE, Q1301 NOTE, Q803 and Q1105 NOT CHECKED, the Q902 NOT CHECKED family, Q1302 NOT CHECKED, and Q100 for a module that fails to import.
- One line per fixture (`ok`, `MISSED`, `WRONG`, `EMPTY`, `MISSING`, `ERROR`, `UNCOVERED`, with code, item, time and value), then `SELFTEST: PASS (144 fixtures, 58 of 58 codes covered, 0 expected gaps)`: 36 to 50 s on 2026-10-29, about 28 s with `--quick` (no full renders). `--only` runs the fixtures of the codes named; `--keep` keeps the temp folder (a failing run keeps it anyway).
- Exit 1 when a gate missed or misreported a planted fault, or a control failed; 2 when a code is unproven (no fixture, a fixture file missing, a gate that considered 0 items, a case that raised).
- Two fixtures are the ones the 2.1.0 flash gate passed: a 3.4 Hz luminance triangle with every step under 20/255 (Q601 FIX at 3.5 flashes) and an equal-luminance red and green strobe (Q602 FIX at 5).

### Approval (Q1301 to Q1304)

`qa.py approve --review <reply file>` records what the reviewer passed in `approved/`:

- `approval.json`: the file's sha256 and decoded-picture streamhash, LUFS and true peak, a hash per scene of the key frames the reviewer saw, the reply verbatim (reviewer, stage, file, written time) and the environment (Python, Pillow, numpy, ffmpeg, font files, size, module hashes);
- the render's `frames.hash` and `thumbs.npy`, `qa.json`, one hash per 100 ms block of `mix_raw.wav` with a copy of it, and `src/` (scenes.py and every local module it imports).

It refuses (exit 1) a missing review, REVIEW FIX, a proof-stage review, a review of another file or of a file written at another time, and a `qa.json` with FIX or NOT CHECKED rows or older than the file. `--override "<why>"` approves anyway, and every later check shows the override. It writes `approved.new/` and swaps it in, so an approve that stops leaves the last approval whole; every reader checks `approved/` against the sha256s in `approval.json` and says NOT CHECKED when they differ.

After it:

- `qa.py check` gives Q1301 for each scene whose key frames now differ, and says what the file is: the approved one; the approved picture with new audio (a NOTE: only the audio gates and cue sync matter); the same frames re-encoded; or another picture. Q1304 when the frame size changed, or Python (major.minor), Pillow, numpy or a font file changed and moved a frame. With `--baseline approved/qa.json`, Q1302 for each gate that went from PASS to FIX.
- `qa.py diff --expect 2.5-5` redraws every frame in worker processes and names the frames and 100 ms audio blocks that changed: NOTE inside the windows, FIX outside them, FIX for a window that saw no change. A window holds frames like a scene (2.5-5 is frames 75 to 149 at 30 fps). Triptychs (before | after | difference, every changed pixel magenta) go to `review/diff_t*.jpg`; a change over 30 percent of the frames and more than one scene (any scene of a one-scene film) gives sampled sheets `review/diff_global_*.jpg`. The raw mix is peak-normalised, so diff takes one overall gain out before it compares audio. Exit 0 same or every change declared, 1 an undeclared change, 2 could not compare.
- In `run_all.py` the approval rows never reject a file: they give the `APPROVAL` line.

### Frame scans (Q1101 to Q1105)

Q1101 to Q1104 point the reviewer at moments to look at; they never fail a build. Each finding is a NOTE row with its time, and its moment goes into `review_times.json` (every Q1101 pop with an f-2..f+2 strip). They run on the 192x108 grey decode in `qa.py check` and, before the encode, on `thumbs.npy` (`qa_scan.scan_thumbs`).

- Pops follow anidoodle's popscan on a 12 x 12 tile grid and on each tile's 3x3 neighbourhood, with a strength floor a stale 36 px caption clears. A tile that pops on two frames in a row is animation, and so are camera shake and a fast mover.
- Stillness is measured against each pixel's 3x3 neighbourhood, so a 1-pixel gate weave is not motion.
- A cut must dominate its neighbouring steps: dissolves, fast moves and flashes are not cuts. No source compares cuts with a schedule; cinetic's cues are the nearest.
- A stall is found under film grain by the pixels that move on both sides of it.
- A scan gives at most 5 rows; the rest fold into one row that points at the strongest of them.

On the five approved 2026-10-28 samples they gave 0 to 4 NOTE rows a film: the battle's one real defect (a one-frame head twitch at 11.97 s), a one-frame weave toggle, a fast zoom, three object swaps the build did not declare, and a ticking timer the stillness test reads as still.

Q1105 (FIX) is not a pointer: it compares the decoded file with `thumbs.npy`, the frames draw(t) made. The template differs by under 0.5 levels; one frame of the wrong size shears every later frame by about 20.

### Purity and lint (Q1201 to Q1206, Q904, Q905)

The purity gate draws at most 2 + 2n frames (n is 16): the first and last, both sides of the cuts (at most n), then window and scene midpoints, cues and key times and even steps (n). Each is drawn in order here, reversed in a fresh `python -I` process (a new str hash seed) and through a spawn pool, and the digests must be identical. A FIX names the worst frame, how many pixels differ and the diagnosis: a cold draw that changes with the clock or the str hash seed, a second draw in one process that differs (state written and read back), or the earlier frame that poisons it. The PASS row says when a line the lint flags as Q1202 ran on none of the sampled frames; check those moments with `--t` or `--grid 0.25`. Pragmas silence a lint NOTE on purpose (`# zoetrope: state-ok`, `rng-ok`, `shadow-ok`, `text-ok`, `colour-ok`, on the line or the def line), never Q1201. The lint follows `from engine import *`, aliases (`npr = np.random`) and the modules scenes.py imports from its folder.

### Audio strip

`python qa.py audiostrip out.mp4 --scenes .` (or `mix.wav` before the render) writes `review/audio.png`, 1600 px wide, for a reviewer who cannot hear: scenes and cuts, a log-frequency spectrogram (30 Hz to 16 kHz), the CUES ticks coloured by their measured offset (green within 1 frame, amber within 100 ms, red missing, grey not measured), momentary and short-term loudness with the integrated line, the true peak per 100 ms with every frame over -1 dBTP in red (ebur128 FTPK), and the proof key cells by number. It reads every CUES form `contract.cues` reads. On the template: `wrote review/audio.png (1600x656) in 1.0 s: I -14.0 LUFS, TP -1.9 dBTP, 0 of 75 frames over -1 dBTP; sync: 2 within 1 frame (of 2 audio cues)` (2026-10-29).

### Known limits

No gate certifies photosensitivity compliance, and none listens. These limits were measured or read in the code on 2026-10-28 and 2026-10-29:

- **Text.** Q301 samples the first, middle and last frame of each rest; a background that changes between them is missed. Q404 matches ink within 24 levels of the item's fg, so a background of that colour inside the box skews it. Q207 sees a changeover only where the old and new boxes overlap. A counter registered as readable text without `ticker=True` gives one Q401 row per value.
- **Recorder.** Text drawn without `ImageDraw.text` gets no row when other text exists (Q1205 is the guard). Opacity is followed through blend and composite only (not `putalpha`, a partial paste mask or numpy fades), so a faint unregistered text can be a FIX instead of a NOTE. Rotated or transformed text is matched by string only. Between transitions the grid is 0.25 s, so unregistered text shown for less can be missed. Q206 tests the middle frame of each rest and the first frame of each overlapping pair.
- **Flashes.** The 10 degree window assumes the frame shown fitted to WCAG's 1024 x 768 view. Two areas far apart flashing in turn are judged apart, as WCAG judges any one field. Area is counted in 4x4-pixel cells of the 192x108 decode, so a flash within a cell of a quarter of a window can go either way (toward FIX: a 22 percent square fails). Untagged pre-2.2 files read as BT.709 carry up to 40 levels of error on saturated green.
- **Scans.** Q1101 misses an overlap on the changeover frame itself (Q203's job), a one-frame stale caption under about 36 px (28 px is not caught), a one-frame fault under camera shake, beside content moving into its tile neighbourhood, or among 3 or more pop frames within 3 frames. Q1102 reads a thin change within one decode pixel of its background as still (a ticking timer), takes holds only from a 2.2 registry or `HOLDS`, and does not read `STATIC`. Q1103 counts CUES of every kind as planned; a cut spread over two frames with no dominant step reads as a fast move. Q1104 needs 0.5 percent of the frame moving on both sides; below that only an exact repeat counts, which grain hides. Q1105 trusts the `thumbs.npy` in the folder: one left by another render gives a false FIX.
- **Sync.** Q902 can FIX only when the score records its placements (`synth.recording()`); without a cue sheet its row is a guess. A sound placed by its start without `audible_s` gets an estimated attack (a 0.25 s pad reads 21 to 86 ms by chord; the ramp says 44.5). A sound that is not on the sheet but loud over a cue can bury it (voice is in `mix_raw.wav`, not `sfx.wav`). A twin moved by more than half its spacing reads ambiguous (NOT CHECKED). Q903 is NOT CHECKED when `--scenes` is given and `mix.wav` is not in the folder. Q804 sees only sounds placed through `synth.place`.
- **Purity and lint.** Q1201 checks the sampled frames only, on one machine; impurity elsewhere needs `--t`, `--grid` or the lint. The lint is heuristic: Q1205 cannot see `.text(` on a draw handle passed in as a parameter (its type is unknown), Q1206 can read a hashtag such as "#bad" or "#fade" as a colour, Q1203 cannot see a mutation through a call result, `getattr` with a computed name is not followed, and `hash()` of a plain variable is flagged even when it holds an int (`# zoetrope: rng-ok`).
- **Approval.** Data files scenes.py reads (json, png) are not snapshotted; when the before frames cannot be redrawn as approved, the triptych caption says so. Q1301 compares key frames only; `qa.py diff` is the complete check. diff reads `mix_raw.wav` as the last render wrote it, so run it after the re-render for audio. Only the latest approval can be diffed. A shell whose working folder is inside `approved/` blocks the swap on Windows (CANNOT APPROVE; the old approval stays). It is tamper evidence for one local user, not security.
- **ffmpeg by name.** `qa.py approve`, `verify`, `audiostrip` and Q903's stream start times call ffmpeg or ffprobe by name, so they need it on PATH; `run_all.py` puts its fallback folder on PATH first.

## 1. Frame checks and proof sheets

`run_all.py proof` draws the review sheets from the same `draw(t)` and `SCHEDULE` as the real render, each frame once per run:

- `proof.png`: up to 12 stills on the frame grid: scene midpoints first, then the first and last frame of every transition window, then scene boundaries.
- `proof_keys.png` (pages `_2`, `_3` ... past 2000 px; a 9:16 film gets standing tiles): every moment in `review_times.json`, ranked FIX, NOT CHECKED, changed, pop, NOTE, cut, window, KEY_TIMES, audio, caption at rest, numbered `#n` and merged per frame. Line 1 of a cell is `#n | scene | t s fN | rank` (`out>in` inside a window); the lines under it give every reason. The cap (40) drops captions at rest first and never a FIX. Page 1 also lists the FIX and NOT CHECKED rows that name no moment (a lint FIX, a gate that could not run).
- `proof_strips.png`: frames f-2 to f+2 of every entry that asks for a strip (at most 24), the event frame boxed.
- `proof_gantt.png`: scenes, transition windows, texts (light at rest, dark while fading), cues by kind and the `#n` cells on one time axis, with bar lines on the BPM grid. A lane that says "none" is empty by design; "no text registry" or "text registry unreadable" means its gates did not run.

`python proof.py keys` redraws the last three after `qa.py check`, the scans or `qa.py diff` add times, at the size in `build.json`; `run_all.py full` does it after its verdict. `qa.contact_sheet(draw, SCHEDULE)` still builds the older sheet of scene boundaries and midpoints.

Look at the sheets for: empty frames, half-drawn text, cards stuck over each other, a different font, wrong colours. Fix before the full render. Frames that look odd for 1 or 2 frames mid-transition (a letter mid-rise, a half-closed iris) are acceptable if they read as motion; a stuck overlap on a hold frame is not.

## 2. Clipped or overlapping text, safe areas

Measured from the registry on every frame, never by eye. `qa.text_box(font, text, xy)` returns (l, t, r, b); `qa.inside(box, W, H)` checks the 4 percent edge pad (the safe area in `playbook.md`); `qa.overlap(a, b)` checks two boxes. `qa.text_gates(scenes, W, H, FPS)` runs gates 2 to 4: Q201 safe area at rest, Q202 overlap at rest, Q203 overlap while either fades, Q207 changeover gap, then the contrast and hold codes. Each defect is one row with its frames, worst_t at the largest overflow or shared area.

- Never crossfade two strings in the same spot: fade the old one out, then the new one in (Q203).
- **Changeover gaps (Q207, Q1104).** A text replaced in one place should leave a gap of 2 frames or less, or 0.5 s or more. A 2-frame gap passes Q207 but repeats a frame between two moves (a Q1104 NOTE), so a 1-frame gap is the only short gap that passes both; the template's titles enter on their cut for that reason. A title kept out of a 0.4 s transition window leaves a 13-frame gap, a Q207 NOTE: with a transition under 0.5 s, put the incoming title in another place, or keep the place empty for 0.5 s.
- No word split into a one-word orphan line, no text under a fixed overlay (a HUD, a logo corner, a caption bar). For wrapped text, test the widest line. For vertical formats keep text away from the bottom area where a platform draws its own controls.

## 3. Contrast

Body text must reach WCAG 4.5:1; large text (36 px, or 24 px bold, at 1080) may use 3:1. Q301 computes it from the real pixels behind the text, not the palette: a ring of pixels just outside the box (`qa.ring_bg`), at the first, middle and last frame of every rest, so a sky that brightens late in a hold fails. worst_t is the sampled frame with the lowest ratio against its minimum. `qa.region_contrast(frame, box, fg)`, `qa.contrast` and `qa.lum` are the WCAG formulas for a one-off check.

If a brand colour fails (a coral or mint on cream is a known case), darken the text tint and note it in the report. Do not use blend modes (difference, overlay) for text that must be read; they drop to mid-contrast on some backgrounds.

## 4. Minimum hold for reading

Every text block must stay fully visible long enough to read. Q401 measures each string's longest rest (alpha 0.98) on the registry's frames.

- **Rule:** hold >= max(floor, 0.5 s + 0.3 s per word, characters / cps + pad), characters counted with spaces (`qa.min_hold(text, profile)`; `qa.min_hold(words)` is the word rule alone). Profiles (`qa.HOLD_PROFILES`): display (default) 20 cps, 0.5 s, at least 1 s; caption 17 cps, 0.5 s, at least 1 s; slow 15 cps, 1.0 s, at least 1.5 s. On ordinary 5-letter words display equals the word rule; long words, numbers and URLs get more (a 34-character URL needs 2.2 s, not 1 s). The card sets `HOLD_PROFILE`; an item may carry its own `profile`; an unknown name is one NOT CHECKED row. On the five 2026-10-28 samples the character term added 2 flags to 143 approved holds, both long-word lines.
- **Plan it:** `qa.py holds <scenario.md> [--profile caption]` prints each storyboard line's time on screen, its need and the words and characters its slot fits (entrance 0.4 s taken off). On the 2026-10-28 scenarios it flags 28 of 83 lines SHORT with display, 33 with caption. To fit a slot, cut words, not reading time.
- **Counters and clocks:** mark them `ticker=True`. Their values on the way need no hold; the value a run settles on does, and its row says so.
- Q402 notes key text under 36 px at 1080; text below 24 px (HUD labels, tags, footnotes) is texture: nothing the viewer must learn may live there. Q403 fails text that never reaches rest (an eased fade that stops short). Q404 fails a reveal that is not complete at its declared `reveal_end`.
- With no voice-over, time every caption for reading; with voice-over, the line must be on screen before the word is spoken.

## 5. First frame and thumbnail

Frame 0 is what many platforms use as the thumbnail. It must not be black or empty. `qa.first_frame(draw)` returns (ok, mean, std) for the drawn frame 0 (Q501 at proof); on the file, Q501 and Q502 decode the first and last frame at full size as a player shows them (`contract.DECODE_709`, rounding) into the same grey scale. Frame 0 fails when its grey mean is 25 or less or its std is 12 or less; the last frame fails at a mean of 25 or less. The template reads 31.9 drawn and 31.8 encoded at frame 0, and 32.3 at its last frame (2026-10-29).

Fix: draw the hook (headline or main visual) fully at t=0 and animate only the extras, or add a poster frame (export a PNG from the strongest frame at the end of scene 1 and give it to the user). The last frame should hold the end card, not fade to black, for at least 1 s (Q503).

## 6. Flashes and photosensitivity

WCAG 2.2 success criterion 2.3.1 (Three Flashes or Below Threshold): nothing may flash more than three times in any one second unless the flashing stays under the general flash and red flash thresholds. `qa.py check` measures it on the finished file (Q601, Q602, Q603) with `qa_scan.flash_rows` on the linear-light decode (`Ctx.lin()`). `qa.flash_window(draw, t0, t1)` (one passage) and `qa.flash_report(draw, dur)` (the whole film) run the same test on drawn frames before the render, through `contract.lin_thumb`: run `flash_window` over every wipe, dip, hit and strobe. `qa.flash_report_file(path)` runs it on any file. Each returns the Q601 to Q603 rows on the film's clock; `rows=False` gives the older `[(second, flashes)]` list from the whole-frame mean, which has no area or red test, so an empty list proves nothing.

- A general flash is a pair of opposing changes in relative luminance (linear light, the WCAG formula) of 0.1 or more, with the darker state below 0.80. A red flash is a pair of opposing transitions to or from saturated red: one state with R/(R+G+B) of 0.8 or more, the two states more than 0.2 apart in CIE 1976 u'v' (WCAG 2.2 note 3).
- Transitions run peak to valley, not frame to frame (the IRIS run accumulator). A ramp of small steps counts once it has moved 0.1 within a second, and a slow fade counts once: one 0.5 s dip to white between dark scenes is one flash, four dips in one second fail.
- Only flashes over a quarter of the frame, or of a 10 degree window, count, at every window position. The window is WCAG's 341 x 256 on a 1024 x 768 view with the frame fitted into it: a third of the width by 0.44 of the height at 16:9, 0.79 of the width by a third of the height at 9:16. The cells must change together, so moving edges and texture do not count. Sparse content counts at its true area: white lines 1 px in 10 flashing 4 times a second fail.
- The count is a sliding second: more than 6 transitions (3 flashes) in any second is Q601 or Q602 (FIX). 4 to 6 transitions a second held for 4 s of any 5 s is Q603 (NOTE); list a designed passage in `ALLOW["Q603"]` as one (t0, t1) entry that holds it.
- Dark flicker under 0.1 of linear luminance (grey 10 to 45, for example) is not a flash.

Typical sources of trouble: full-frame colour wipes held a few frames, a background flipping on every half-beat (4 to 5 flips a second), inverted impact frames, strobing glitch hits, a sprite blinking white on several hits within one second (three in a second is the limit even when the sprite is small), red alternating with another colour at equal brightness. Fix: at most 3 flips a second, a smaller flashing area, a softer swing (under 0.1 of luminance, or both states above 0.8), a flash stretched over more frames, or no flash. On the five approved samples the gate reads 0 to 3 flashes a second (the battle's triple shot sits at exactly 3). No tool certifies compliance; tell the user when a video has a deliberate fast passage.

## 7. Duration, resolution, fps, codec, colour

`qa.probe(path)` returns duration, size_mb, w, h, fps, frames, vcodec, pix, acodec, channels and the four colour tags from ffprobe (an untagged key reads "unknown"). Expect the size and fps the build asked for, `yuv420p` H.264, an audio stream, a duration within 0.1 s of `DURATION`, and a frame count within 1 of duration x fps (Q701 to Q706).

Colour: `run_all.py` encodes through `contract.COLOR_VF` and `COLOR_FLAGS`, which convert and tag BT.709 limited range. Q707 fails an H.264 file whose tags are not bt709 / bt709 / bt709 / tv: an untagged file decoded as HD came back up to 40 levels off on pure green (2026-10-28), four of the five samples were untagged, and the flags without setparams leave primaries and transfer unknown. Q708 round-trips five swatches (four saturated, one grey) through the encode chain on this ffmpeg: 1 level (2026-10-29). A non-H.264 file gets NOT CHECKED for Q705, Q707 and Q708. If the audio is longer or shorter than the video, the mux cuts to the shorter stream; never ship a mismatch.

## 8. Loudness and true peak

Target -14 LUFS integrated, true peak at or below -1 dBTP. `qa.loud(path)` returns I (LUFS), LRA (LU), the true peak and every 100 ms ebur128 frame of the same run; silence reads `-inf`.

- **Master:** `audio.master` (Q805, in `mixing.md`) applies one gain to -14 LUFS and a 4x oversampled true-peak limiter at -2.0 dBTP, checked with ebur128. Q805 fails a master that missed -14 by over 0.1 LU or its ceiling by over 0.05 dB, or whose limiter took over 0.5 LU of loudness or over 6 dB at one moment: lower the raw level of the loudest stacked hits at the time it names instead of letting the limiter work. The AAC encode adds up to 0.45 dB of true peak at 320k (1.23 dB at 192k), so `run_all.py` measures the decoded mp4 and re-masters lower, at most 3 times, while it reads over -1.3 dBTP (the gate less the 0.3 dB R128 meter tolerance).
- **Q802** reads the true peak from ebur128 and finds its moment on the file itself, channel by channel: every 10 ms block of ebur128's loudest 100 ms frames is upsampled 4x (numpy, within 0.02 dB of EBU Tech 3341 signals 15 to 19), and the row spans every frame over the limit. On a FIX it reads `cuesheet.json` and names every sound sounding within 50 ms of the moment (a ringing bell, a riser into it, a hit just after it) with its span, gain, peak plus gain and its level there on the stems' scale, plus the music bed's level (`mix_raw.wav` minus `sfx.wav`), and gives a cut order: impact, then chime or bell, then press or drop (a house heuristic). After a peak limiter the encode decides which limited peak overshoots, so only the final file can say where it is.
- **Q804** (after cinetic's stack_guard) counts every SFX-bus sound and any music-bus sound that serves a cue: 2 or more heavy sounds (kick, hit, boom, impact, drop) within 3 frames, a payoff cue (`{"t": ..., "label": ..., "payoff": True}` in CUES) with a second sound within 3 frames or a lead-in still sounding 0.1 s before it, or more than 2 sounds in any 100 ms (a taste rule). A riser or whoosh whose climax or end lands within 3 frames or 100 ms of a heavy sound is one gesture with it and never counts; the bed's own kick under a cut hit is not a stack. Declare a designed stack in `ALLOW["Q804"]`. Without a cue sheet Q804 is one NOTE: place sounds with `audio.place` or `synth.place`.
- Q803 notes a near-silent second inside the piece (fine if planned: a glitch, a think pause; list it in ALLOW). Voice must stay clearly above the music (music ducked about 8 dB under speech).

## 9. Audio and video sync at hits

Every cut, hit and whoosh must land on the beat grid and on the frame where the picture changes.

- **Grid (Q901, Q904, Q905).** Q901 notes a cut (`CUTS`, else every SCHEDULE start after 0) more than one frame off the `BPM` grid (`qa.snap_ok(t_cut, bpm)`); it runs with `--bpm` or `BPM` in scenes.py. Q904 notes a SCHEDULE, DURATION or CUES time off the frame grid, Q905 a beat that is not a whole number of frames (at 30 fps 60, 72, 75, 90, 100, 120, 150, 180 and 200 BPM are; its fix lists them for the build's fps).
- **Cues (Q902).** `qa.py check` finds each cue's own sound on the lossless SFX stem (`sfx.wav`) from the cue sheet (`cuesheet.json` and `cue_sounds.npz`, which `audio.render_audio` writes; every sound placed with `synth.place` inside `synth.recording()` is on it) by band-limited cross-correlation over +-250 ms, and compares the instant it is heard with the cue time: its landmark, or its audible attack (the sheet's `audible_s`) for a sound placed by its start or onset, so a slow pad put on a cue shows up. Late by more than one frame (33 ms at 30 fps, 42 ms at 24, never over 60 ms) or early by more than 40 ms is a FIX; outside -5..+15 ms is a NOTE. Give the sound that serves a cue its CUES label. Identical sounds placed close together are measured as a group; a copy that cannot be told from its twins is NOT CHECKED, and so is a sheet without its buffers or stems. The picture must change within `CUE_LAG` + 1 frames, in the cue's `region` or its registry text when it has one (NOTE; "not measurable" when only the whole frame was there). The decoded file is a confirm only (NOTE when it moves confirmed cues by over 2 ms).
- **No cue sheet.** A score that places sounds another way gets Q902 from an onset detector, one NOTE that says it is a guess and reports misses without offsets. Give a hard cue `band=(lo, hi)` (Hz) and `region=(x0, y0, x1, y1)` (output px) in a CUES dict entry to aim it. The lasting fix is to record the placements.
- **Mux (Q903) and calibration (Q906).** Q903 holds the decoded mp4 audio against `mix.wav` (the mux) and, when it is there, `mix_raw.wav` (the master and the mux) in three 2 s windows at 12, 45 and 85 percent: FIX past 1 ms, and a lag past 0.1 s is found over +-1 s. A second row holds the audio and video stream start times within 1 ms. `qa.py calib` pushes one white frame and a one-frame 1 kHz blip through `audio.master` and the mux after any ffmpeg or master change and must read 0 ms. Never correct a measured offset in the mixer: fix the stage that moved it.

Measured 2026-10-28 on the five samples: the mux adds 0.000 ms, the 1024-sample AAC priming (21.3 ms) is trimmed by the mp4 edit list, and the 2.1.0 alimiter delayed every sound by 4.0 ms. The batch's 37 to 87 ms lateness was placement: slow-attack sounds placed by their first sample (a 0.25 s pad attack is heard 44 ms in). The house rule for lead and trail is in `beat-sync.md`. Voice lines: compare the time each line starts with its caption (voice length from the audio, `voice.md`).

## 10. File size

Ask the user where the video goes and what the limit is, because limits change by workspace and by plan; we do not quote numbers we have not checked. Give the limit to the build as `BUDGET_MB` in scenes.py or `run_all.py full --budget-mb N`: it caps the encode (`formats.md`), and Q1001 compares the file with it (`--max-mb` wins in a standalone check; the row says which cap it used). Q1002 notes bitrate over 12 Mb/s.

- Slack: a short GIF preview (15 s at most, 960 px wide at most, 15 fps) or an MP4. Offer the GIF as a preview next to the MP4.
- Email: attach only if small; otherwise share a link. Offer a 720p cut and a poster PNG.
- Intranet or wiki: MP4 H.264 plays everywhere; AV1 or VP9 may not play in older QuickTime or some corporate players, so say so.

To shrink: raise CRF (20 instead of 18 for grainy or textured scenes), drop grain and vignette or make the grain finer (`grain.grain`'s 1 px tiles cost about half the kit's 2 px cells: `formats.md`), lower to 720p, lower fps to 24, shorten the cut. Dense textures (grain, halftone, particles, fine paper) cost bitrate; keep them out if there is a size limit.
