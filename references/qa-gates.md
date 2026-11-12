# QA gates

Read this before the final render and again before the delivery message. Every gate below runs inside the engine: Python with PIL and numpy, plus the ffmpeg and ffprobe the build found. No gate needs a network.

Run all gates on the final file, not only on stills. `run_all.py full` and `run_all.py audio` run them on the file they make and say what happened; `qa.py check` runs them again on any file.

## Where the gates run

Every gate runs on this machine, with Python, Pillow, numpy and the ffmpeg and ffprobe the engine finds. Only the speech gates (Q806, Q807) start a second uv environment, to run a speech model that `python qa_speech.py fetch` put in the cache (the first run of that environment may fetch its pinned wheels, as uv does); no gate module itself opens a network connection.

| Step | What it reads | Codes it makes |
|---|---|---|
| `run_all.py proof` | Drawn frames only, before any encode (`qa.proof_rows`, `qa_purity.run`, `qa_lint.run`) | Q501, Q200 to Q209, Q301, Q401 to Q404, Q1201 to Q1206, Q904, Q905 |
| `run_all.py full` and `audio` | The master, then `thumbs.npy` (every drawn frame, before the encode), then the finished file through `qa.check` | Q805, Q1101 to Q1104 on `thumbs.npy`, then every `qa.py check` code |
| `qa.py check <file>` | The file, and with `--scenes` its scenes.py and the build files | 49 of the 60 codes: all but Q805, Q904, Q905, Q906, Q1201 to Q1206 and Q1303 |
| `qa.py purity`, `qa.py lint` | The proof gates on their own | Q1201; Q1202 to Q1206, Q904, Q905 |
| `qa.py speech` | The narration stem against its script | Q806 |
| `qa.py calib` | A 4 s test clip through the master and the mux | Q906 |
| `qa.py diff` | Every frame and every 100 ms audio block against the approval | Q1303, Q1304 |

### The verdict

- `run_all.py proof` prints every row and a `PROOF:` line, and exits 0 when clear, 1 on any FIX, else 2 on any NOT CHECKED.
- `run_all.py full` and `run_all.py audio` collect the master's Q805 row, the scans of `thumbs.npy` and every `qa.check` row. Any FIX or NOT CHECKED row outside the approval codes moves the file to `<name>.rejected.mp4` and prints `REJECTED <path>: <code> <status>, ...`; a run that breaks before the verdict leaves `<name>.unchecked.mp4`. Neither is delivered.
- The approval codes (Q1301 to Q1304, and a Q100 row raised by `qa_approve`) are a review state, never a defect of the file (`run_all.is_approval`). They print as `approval current|note|stale|unknown: <code> <message> -> <fix>` and decide the APPROVAL line: `APPROVAL: none yet -> final review, then qa.py approve`, `APPROVAL: current -> ...` or `APPROVAL: stale: <code> <item> -> re-review the changed scenes, then qa.py approve`. A clean run then ends with one `DELIVERED <path> (<MB> MB, <s> s, <LUFS> LUFS, <dBTP> dBTP)` line.
- `qa.py approve` refuses a build whose `qa.json` holds a FIX or NOT CHECKED row outside the approval codes (see Approval).

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

### Arguments

| Flag | What it does |
|---|---|
| `video` | The file to check |
| `--scenes <folder>` | The working folder: imports its scenes.py, reads its build files, and lets the gates write `review_times.json` there |
| `--size WxH` | Q703 against it |
| `--fps N` | Q702 against it |
| `--duration S` | Q701 against it; with `--scenes` and no `--duration`, `DURATION` is used |
| `--bpm N` | The beat grid for Q901; with `--scenes` and no `--bpm`, `scenes.BPM` is used |
| `--max-mb N` | The Q1001 cap; without it, `scenes.BUDGET_MB` |
| `--silent` | The piece has no audio on purpose; `scenes.SILENT` counts the same |
| `--json <path>` | Also writes every row as JSON, and with `--scenes` adds each finding's moment to `review_times.json` |
| `--registry-procs N` | Processes for the text recorder's sampling pass (from `qa_registry.add_check_args`; 1 or less means none). Default: up to 8, and only when one process would take over 20 s |
| `--baseline <qa.json>` | The `qa.json` the approval kept (`approved/qa.json`): Q1302 against it (from `qa_approve.add_check_args`) |

### The four statuses and the exit code

| Status | Means | For delivery |
|---|---|---|
| PASS | The gate measured and the value is inside its limit | Nothing to do |
| NOTE | A pointer for the reviewer: something to look at, a taste rule, or a value inside a soft window | Never blocks; goes into the delivery report as a weak spot |
| FIX | A measured defect | Blocks: the build is rejected and `qa.py approve` refuses it |
| NOT CHECKED | The gate could not run, or had nothing to look at and nothing declared it so (`considered` 0 with no opt-out) | Blocks like a FIX: the build is rejected, and the run cannot be called clean |

`contract.exit_code`: 0 when no row is FIX or NOT CHECKED (NOTE rows allowed), 1 when any row is FIX, 2 when some row is NOT CHECKED and none is FIX. With no ffmpeg, check and look stop with `qa.py: no ffmpeg on PATH (nor in /opt/homebrew/bin or /usr/local/bin)` and exit 1. The summary reads `QA: PASS (45 checks, 0 FIX, 0 NOTE, 0 NOT CHECKED)` on the template at 640x360 (2026-11-12); the state is `FIX (<n>)` when any row is FIX, else `NOT CHECKED (<n>)` when any is, else `PASS`. Progress lines from the text recorder come first, for example `qa_registry: drew 55 of 225 frames (28 in transitions and changeovers, 27 more on the 0.25 s grid) in 0.3 s on 1 process; 53 text calls, 53 records on frames`.

### --json

`--json <path>` writes a list with one object per row (`contract.write_rows`), with these keys: `status`, `code`, `msg`, `fix` (empty on a PASS), `t0` and `t1` (the first and last second the finding covers), `worst_t` (the moment to open first), `item` (the string, cue label, scene or file that failed), `metric` (the measured number), `limit` (what it was held to), `spans` (merged runs of frames as `[t0, t1]` pairs) and `considered` (how many items the gate looked at). The builder writes it to `qa.json`; `qa.py approve` keeps that file as the baseline.

### What --scenes adds

With `--scenes <folder>`, check sets `engine.W`, `engine.H` and `engine.FPS` from the file and `engine.SS` from `build.json`, then imports the folder's scenes.py. It reads `SCHEDULE`, `DURATION`, `BPM`, `SILENT` and `BUDGET_MB`, and runs:

- Q901 (when there is a BPM) and the text gates Q200 to Q207, Q301 and Q401 to Q404 on every frame;
- the text recorder (Q204 to Q206, Q208, Q209);
- Q902, Q903's NOT CHECKED row when the folder has no `mix.wav`, and the speech gates Q806 and Q807 (the narration lives in the build folder);
- Q1103, and the `ALLOW`, `CUE_LAG`, `WINDOWS`, `HOLDS` and `STATIC` declarations every scan reads;
- the `payoff` cues of Q804.

Without it those rows are missing, not NOT CHECKED, and the extra line under the summary says so. Q1105, Q802's cue names, Q804, Q903's mux rows and the approval rows still read build files from the file's own folder when they are there: `contract.Ctx` uses that folder as the working folder.

### What check adds to review_times.json

Only into a folder named with `--scenes` (`Ctx.record`):

- `qa_scan` adds its own findings on every check: kind `pop` with a strip for Q1101 (the strongest pop and each pop of the row, folded ones included), kind `finding` for the rest, and for Q601 and Q602 the middle of every passage too.
- With `--json` as well, every other row that is not PASS and names a `worst_t` becomes a `finding` entry: reason `<code> <status> <item>` (the message when there is no item), its status, and a strip for Q203, Q207 and Q404 (`qa.STRIP`). Codes owned by `qa_scan` are left to it (`qa.RECORDS_OWN`).

### ffmpeg and the decode

`contract.find_ffmpeg` takes the ffmpeg on PATH, else `/opt/homebrew/bin/ffmpeg`, else `/usr/local/bin/ffmpeg`, and ffprobe is the file beside it with the same name pattern. `run_all.py` has its own finder with the same places, and puts that folder on PATH. Every gate module reads the file through one `contract.Ctx`, decoded once per need with stdin closed: RGB at 192x108 as a player shows it (`DECODE_709`), linear light at 192x108 for the flash gate (`DECODE_LINEAR`), grey from that RGB, and the audio at the rate a gate asks for. Each picture decode must hold every frame ffprobe counts, within 1 (`Ctx._counted`): a short decode raises, so the gate module that asked reports Q100, or Q503 reads NOT CHECKED, rather than a gate passing on part of the film. The full-size decodes of frame 0 and the last frame for Q501 and Q502 (`qa.frame_grey`) say NOT CHECKED when they fail, so a file whose last second will not decode ends with a NOT CHECKED verdict, not a traceback.

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
| Q502 | 5 | `qa` | FIX | Last frame, decoded the same way: grey mean 25 or less (a fade to black). Q501 and Q502 read NOT CHECKED when their frame does not decode (a cut or damaged file), as Q503 does: `files.cut` plants it |
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
| Q806 | 8 | `qa_speech` | FIX | The narration stem (`narration/narration.wav`) does not say its script: a speech model (faster-whisper base.en) transcribes each line, and a missing, added or changed word is a FIX naming the line, the word and its time; a word close in letters (difflib ratio 0.6 or more) or a short word changed for a short one is a NOTE. A narration that is not English is a NOTE. No narration is a PASS, unless `CARD` names a narrated card (NOT CHECKED); no speech model, NOT CHECKED. `qa.py speech` runs it alone |
| Q807 | 8 | `qa_speech` | NOTE | A word the narration stem says that the file's sound loses (the music masks it, or the file holds an older take), line by line against the stem's own transcript. FIX when the file does not carry the stem at all: GCC-PHAT peak prominence under 40 |
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
| `draw(t)` | The frame at t, a pure function of t. Read by Q1201, the text recorder, Q301, Q404, Q501 at the proof, approval and diff |
| `text_items(t)` | Every text drawn at t, as dicts (keys below). Read by Q200 to Q209, Q301, Q401 to Q404, Q1102's holds, Q902's picture boxes and the proof sheets |
| `SCHEDULE`, `DURATION` | `{name: (start, end)}` and the length, in seconds. SCHEDULE: Q901, Q904, Q1103, Q1104, Q1201, approval's key frames, the sheets. DURATION: Q701, Q904, the frame count of the text gates and Q1201 |
| `BPM` | Beats a minute. Q901 when `--bpm` is not given, Q905, the Gantt bar lines |
| `STATIC` | `[(t0, t1), ...]` spans drawn once by design (end exclusive). Q1102, and the render reuses the frame |
| `CARD` | The style card the video follows; a narrated card's build must carry `narration/` or Q806 is NOT CHECKED |
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
| `qa.py look <video> [--times t,...] [--width 480]` | Small JPEG copies of the frames the film shows at those times and `review/look.jpg` (default every 5 s plus the last frame), so a model never reads a full-size frame. Each time goes onto the frame clock first, and each copy is labelled with its time and frame number |
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
| `qa.py speech [narration/narration.json] [--fetch]` | Q806 alone: the narration stem against its script. `--fetch` downloads the speech model (147.8 MB) first; exit 1 on a FIX |

Flags, as the parsers have them (read 2026-11-12):

| Command | Flags |
|---|---|
| `look` | `video`, `--times T,T` (default every 5 s and the last frame), `--width 480`, `--out review` |
| `holds` | `scenario`, `--section S` (the section whose heading starts with it), `--profile display\|caption\|slow`; one `OK` or `SHORT` line per quoted on-screen line with the time it has, the time it needs and the words and characters the slot fits, then `HOLDS: OK` or `HOLDS: SHORT (<n>)` with the profile's numbers; needs no ffmpeg |
| `purity` | `--scenes .`, `--n 16`, `--fps`, `--size`, `--ss` (these three default to `build.json`, else 30 fps, 1920x1080, SS 1), `--t T,T`, `--grid S`, `--procs` (pool size, default 2 to 4), `--json` |
| `lint` | `path` (default `scenes.py`), `--fps`, `--all` (every site, not the first 5 per code), `--json` |
| `owner` | `--t S` or `--traceback FILE` (exactly one, else exit 2), `--path scenes.py`, `--fps`; prints `owner: <why>`, `error: <last line>` for a traceback, and one line per function with its `file:first-last` lines |
| `approve` | `--scenes .`, `--review FILE`, `--video FILE`, `--reviewer ID`, `--override WHY`, `--procs` |
| `diff` | `--scenes .`, `--expect t0-t1[,t0-t1 ...]`, `--procs` (default a quarter of the cores, at most 8) |
| `verify` | `[video]` (default the approved file), `--scenes .`; `VERIFY: SAME` exits 0, `VERIFY: DIFFERS` 1, `VERIFY: NOT CHECKED` 2, and any error reads as 2, never 1 |
| `calib` | `--fps 30`, `--size 320x180`, `--out calib`; writes `video.mp4`, `mix_raw.wav`, `mix.wav` and `calib.mp4` there and refuses a folder that holds a build (`refused: <folder> holds a build (...)`) |
| `audiostrip` | `video` (or `mix.wav` at the proof stage), `--scenes`, `--out review/audio.png`; exit 2 with no audio (0 when `SILENT`) or no ebur128 summary |
| `selftest` | `--quick`, `--only CODE[,CODE]`, `--keep`; exit 1 means a fixture missed or misread its planted fault, 2 a code with no fixture or a fixture missing |

Template runs in a scratch copy, 2026-11-12: `qa.py audiostrip out.mp4 --scenes .` printed `wrote review/audio.png (1600x656) in 0.5 s: I -14.0 LUFS, TP -2.0 dBTP, 0 of 75 frames over -1 dBTP; sync: 2 within 1 frame (of 2 audio cues)`; `qa.py look out.mp4` wrote 3 frames at 480 px (`review\look.jpg` on Windows); `qa.py lint` gave `LINT: PASS (7 checks, 0 FIX, 0 NOTE, 0 NOT CHECKED)`; `qa.py owner --t 2.5` routed to `draw` (`scenes.py:102-111`, the template has no per-scene functions).

**`qa.py selftest`** proves the gates can still fail; it says nothing about a particular video. Run it from a fresh engine copy made with `cp -r engine/. <folder>/` (a `cp engine/*.py` copy leaves `qa_fixtures/` out, and every fixture module then reads MISSING).

- Each of the 85 cases in `engine/qa_fixtures/` feeds one gate a planted fault or a known-good input (fake registries, 640x360 scenes files, synthetic MP4s and WAVs, one 2 s build for the approval gates, a synthetic narration with canned transcripts for the speech gates, all in a temp folder) and states the code, status, item, time and value the gate must report, within a tolerance. The template must pass `run_all.py proof` and `full` at 1920x1080 and 1080x1920 with no FIX and no NOT CHECKED.
- Every code in `contract.CODES` needs a fixture at its failure status, or an `EXPECTED_GAPS` entry with its reason (none today). Second statuses with no fixture yet: Q204 NOTE, Q1301 NOTE, Q803 and Q1105 NOT CHECKED, the Q902 NOT CHECKED family, Q1302 NOT CHECKED, and Q100 for a module that fails to import.
- One line per fixture (`ok`, `MISSED`, `WRONG`, `EMPTY`, `MISSING`, `ERROR`, `UNCOVERED`, with code, item, time and value), then `SELFTEST: PASS (161 fixtures, 60 of 60 codes covered, 0 expected gaps)`: 45.9 s on 2026-11-12 (45 s on 2026-11-03, 36 to 50 s on 2026-10-29), about 28 s with `--quick` (no full renders). `--only` runs the fixtures of the codes named; `--keep` keeps the temp folder (a failing run keeps it anyway).
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
- **Scans.** Q1101 misses an overlap on the changeover frame itself (Q203's job), a one-frame stale caption under about 36 px (28 px is not caught), a one-frame fault under camera shake, beside content moving into its tile neighbourhood, or among 3 or more pop frames within 3 frames. Q1102 reads a thin change within one decode pixel of its background as still (a ticking timer), takes holds from a 2.2 registry, `HOLDS` and `STATIC` spans only. Q1103 counts CUES of every kind as planned; a cut spread over two frames with no dominant step reads as a fast move. Q1104 needs 0.5 percent of the frame moving on both sides; below that only an exact repeat counts, which grain hides. Q1105 trusts the `thumbs.npy` in the folder: one left by another render gives a false FIX.
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

- **What the narration says (Q806, Q807).** The reviewer cannot hear, so `qa_speech.py` has a speech model write down each narrated line: faster-whisper 1.2.1 with `base.en` (147.8 MB, MIT, int8 on the CPU, its own uv environment; `python qa_speech.py fetch`, pinned to commit `3d3d5dee` with each file's sha256). Each line's clip (0.3 s each side) is transcribed once and cached in `narration/speech.json` by its samples, the model and the worker; 14.6 s of narration took 0.8 s plus 0.5 s to load. Q806 aligns the words heard with the line's text (difflib on words). Digits and the words for them compare equal ($99, 20%, 2026 as "twenty twenty six" or "two thousand and twenty six", 3:45, 21st, 1990s, 1.5, $5.99), so do joined and hyphenated spellings (night time, nighttime), British and American spellings (harbour, harbor), a lone letter and its sound (R, are) and 53 groups of homophones (two, to, too; four, for), since a listener cannot tell them apart either. Q806 holds the stem against its script, so a misread word is found before anything is built on it: run `qa.py speech narration/narration.json` right after `voice.synthesize`. Q807 finds the stem in the file's sound by GCC-PHAT (plain correlation put a voice buried under a rhythmic bed 0.87 s off) and holds what the file says against what the stem says, so a word the music takes shows up; a file mixed from another take reads a prominence near 15 and is a FIX. In `qa.py check`, Q806's times are moved to where the stem sits in the file.
- **Calibrated 2026-11-03.** On 26 real-voice English narrations (85 lines from 16 Kokoro voices and 2 SAPI voices), Q806 raised 0 FIX after the folds above; its NOTEs were two male voices saying "Shrink" so it reads "Drink" and two British voices reducing "are" in "Two are square". In the 2026-10-28 voice lanes it passed all 27 SAPI narrations and raised a FIX on every line of the 11 made by fake models (no speech in them). On a 7.5 s narrated template build, Q806 and Q807 passed (the stem found at +0.000 s, prominence 321); with white noise over the voice, every word was still heard at 0 and -6 dB, Q807 named the lost words at -12 dB, and at -18 dB the stem could not be found (prominence 23, FIX). The template's own bed did not mask a voice 24 dB under it: its tones and kicks sit below the speech band.

## 10. File size

Ask the user where the video goes and what the limit is, because limits change by workspace and by plan; we do not quote numbers we have not checked. Give the limit to the build as `BUDGET_MB` in scenes.py or `run_all.py full --budget-mb N`: it caps the encode (`formats.md`), and Q1001 compares the file with it (`--max-mb` wins in a standalone check; the row says which cap it used). Q1002 notes bitrate over 12 Mb/s.

- Slack: a short GIF preview (15 s at most, 960 px wide at most, 15 fps) or an MP4. Offer the GIF as a preview next to the MP4.
- Email: attach only if small; otherwise share a link. Offer a 720p cut and a poster PNG.
- Intranet or wiki: MP4 H.264 plays everywhere; AV1 or VP9 may not play in older QuickTime or some corporate players, so say so.

To shrink: raise CRF (20 instead of 18 for grainy or textured scenes), drop grain and vignette or make the grain finer (`grain.grain`'s 1 px tiles cost about half the kit's 2 px cells: `formats.md`), lower to 720p, lower fps to 24, shorten the cut. Dense textures (grain, halftone, particles, fine paper) cost bitrate; keep them out if there is a size limit.

## Gate details

What the sections above leave out: the measurements behind each code, from the gate modules (constants named, checked against the engine on 2026-11-12). The overview of each gate stays in its numbered section.

### Frame scans, in numbers

Q1101 to Q1104 read 192x108 grey frames (PIL luma), are pointers for the reviewer (all NOTE, all honour `ALLOW`), and run twice in a full build: on `thumbs.npy` before the encode (`qa_scan.scan_thumbs`) and on the decoded file. Each scan keeps its 5 strongest rows (`MAX_ROWS`) and folds the rest into one row that lists their times.

- **Q1101** (`qa_scan._pops`, `POP`, `STRONG`): on a 12 x 12 tile grid, a tile pops when 0.004 or more of its pixels change by more than 4 levels both into and out of the frame while the change across it (f - 1 to f + 1) is at most 0.35 of the smaller step, and the same holds on its 3 x 3 tile neighbourhood at 0.5. The pop is strong enough to report when 0.2 percent of all pixels or more sit 12 levels off both neighbours on the popping tiles. A tile that also pops on a neighbouring frame is alternation, and one whose steps either side change by 0.25 of its pop step or more is motion passing through; neither counts. Three or more pop frames within 3 frames are one fast mover, not pops. Pops under 1 s apart make one row. The message says "whole-frame" when over 1 percent of all pixels sit 12 levels off both neighbours, else "local", with the tile rows and columns.
- **Q1102** (`_frozen`, `STILL`): still means under 0.2 percent of pixels leave the 3 x 3 range of the other frame by 6 levels, frame to frame and against the run's first frame, so a slow draw-on is not frozen. A run of 3 s or more is reported. Not counted: near-black runs (the median share of pixels above 25/255 is under 2 percent), registry rests, `HOLDS` and `STATIC` spans with 2 frames either side, the last 2 s plus a frame (the end card), and `ALLOW` spans.
- **Q1103** (`_cut_frames`, `CUT`, `DARK_CUT`): a hard cut is a step where over 30 percent of pixels change by more than 12 levels with a mean change over 18 levels and over 3 times the median of the 5 steps either side, or a dark cut (over 30 percent by more than 6 levels, mean over 6, over 4 times the median); either must be at least twice its larger neighbouring step. A cut answered within 3 frames by a cut back to the picture before it is a flash (Q601's), not a cut. A cut passes when it is within 1 frame of a SCHEDULE start or CUTS time, between 1 frame before a cue and `CUE_LAG` + 1 frames after it, inside a `WINDOWS` span (1 frame slack) or in `ALLOW`. Cut frames within 2 frames of each other are one row. With a scenes.py that has no SCHEDULE, CUTS or CUES the row is NOT CHECKED; without `--scenes` there is no row.
- **Q1104** (`_stalls`, `STALL`): the pixels that move more than 4 levels in both neighbouring steps (at least 0.5 percent of the frame) move into the frame under 5 percent of the time, or the step into it changes under 0.05 levels on average (an exact repeat); both neighbouring steps move over 0.8 levels on average; and no other repeat sits within 6 frames, so animation on twos is not a stall. Not counted: a held flash (the frame after returns to the one 2 before), inside a transition window, up to 2 frames after a SCHEDULE start or CUTS time, and `ALLOW`.
- **Q1105** (`match_rows`): no `thumbs.npy` and no `frames.hash` gives no row (not a build); `frames.hash` without `thumbs.npy` is NOT CHECKED; a frame of the file whose mean grey differs from its drawn thumb by more than 4 levels (`MATCH`), or a different frame count, is a FIX. The template read worst 1.00 levels mean at 1920x1080 and 1.05 at 1080x1920, 0 of 240 frames over 4 (source measurement, 2026-11-01, an earlier template).

### Flash gate, in numbers

`qa_scan.flash_rows` implements WCAG 2.2 success criterion 2.3.1 on the linear-light decode:

- **Luminance.** The file's RGB is read as sRGB code values, turned to linear light and only then averaged down to 192x108 (`DECODE_LINEAR`), so sparse bright lines are not underrated. Relative luminance uses the WCAG weights 0.2126, 0.7152, 0.0722 (`Y_W`).
- **General transition.** A swing of relative luminance by 0.1 or more (`STEP`), where the darker of its two states is under 0.8 (`DARK`). A flash is a pair of opposing transitions, so the limit is more than 6 transitions in any sliding 1 s window (`MAX_T`); the row reports flashes as transitions / 2.
- **Red transition.** One state has R / (R + G + B) of 0.8 or more and the two states are more than 0.2 apart in CIE 1976 u'v' (`RED_UV`); a state too dark for a chromaticity (luminance under 0.005, `DARK_Y`) counts against a lit one. The saturated-red measure (R - G - B) x 320 must also move by 1.0 or more (`RED_STEP`), which keeps noise out.
- **Area.** A transition counts where the cells that moved together cover a quarter of the frame or of one 10 degree window (`AREA`). Cells are 4 x 4 pixels of the 192x108 decode (`CELLS`, 48 across). Every window position one cell apart is judged on its own, as is the whole frame.
- **Runs.** A window's mean is split into runs at its extremes; a reversal smaller than 0.005 in luminance or 1.0 in the red measure (`HYST`) does not end a run, so shimmer does not count.
- **Q603** (`EXT`) is 4 to 6 transitions in the trailing second held for 4 s of any 5 s; an `ALLOW` span holding the whole passage within 1 s (`ALLOW_SLACK`) clears it. A FIX row names the worst second, the window position as percentages of the frame and how many passages are over the limit. Fewer than 2 frames makes all three NOT CHECKED.

### The text gates, in numbers

The text gates read `text_items(t)` on every frame of `DURATION`. An item is at rest at alpha 0.98 or more (`qa.FULL`) and on screen above 0.05 (`qa.VISIBLE`); `texture=True` items are skipped. Sizes are scaled by 1080 / min(W, H), so the rules read as written at any aspect. One row per string or pair that fails, with every frame it fails on as spans; one PASS row per clean code.

- **Q207** (`qa._changeover_rows`): for each run of a string on screen, the next run of a different string whose first box overlaps its last box is a changeover; the gap is the empty frames between them, a NOTE when it is over 2 frames and under fps / 2 (3 to 14 frames at 30 fps). `ALLOW['Q207']` lists the gap's middle.
- **Q205** accepts a box from a textbbox (as tall as a drawn copy within 2 px) when every edge is within 2 px (`BOX_PX`); any other box is hand-made and must hold the glyphs within 2 px and reach no more than 0.6 em past them (`HAND_EM`), because Q201 and Q202 judge the text by that box.
- **Q206** tests the middle frame of every rest and the first frame of every pair of overlapping registered texts (where Q301, Q202 and Q203 look); a pixel is the text's when drawing the frame without it moves a channel by 8 levels (`CHANGED`). A text with under 12 ink px, drawn where its place is unknown, or that cannot be drawn without is not measurable; when under half the tests can be measured (`MEASURED`) the row is a NOTE, and when draw(t) gives other pixels on a second call inside a tested text it is NOT CHECKED.
- **Q209** makes one NOTE per moment, and one more for items that give no alpha, where being off screen may be right.
- **Q301** (`qa._contrast_rows`) draws each rest at its second, middle (`contract.mid_frame`) and second-to-last frame, every frame of a rest 3 frames or shorter, at the build's supersampling. The background is the median colour of a ring 6 px wide just outside the box (`qa.ring_bg`), since the box itself is mostly glyph ink; the ratio is `qa.contrast`, the WCAG formula. A string that fails gets one row, at its lowest ratio against its minimum. A string at rest with no `fg` gives a NOT CHECKED row; values a ticker passes on the way are not sampled, and when only those ever rest the row is NOT CHECKED.
- **Q401** profiles (`qa.HOLD_PROFILES`), with need = max(floor, 0.5 s + 0.3 s per word, characters / cps + pad), characters counting spaces and a run of white space counting once:

| Profile | Characters a second | Pad | Floor | For |
|---|---|---|---|---|
| display | 20 | 0.5 s | 1.0 s | Titles, labels, end cards (the default) |
| caption | 17 | 0.5 s | 1.0 s | Lines read while the picture moves |
| slow | 15 | 1.0 s | 1.5 s | Dense explainers |

  The profile is the item's `profile`, else `HOLD_PROFILE`, else display. A dict as `HOLD_PROFILE` overrides display's numbers and reads as "custom"; an unknown name gives one NOT CHECKED row naming the profiles, and the other strings go on. Tickers (`ticker=True`, `qa._ticker_passing`): a value whose every run hands over to another ticker value in the same place within 2 frames is on the way; it needs no hold and no contrast. The value a ticker settles on needs both. Q402 applies to every value. The template read lowest contrast `'{one idea}' 13.38:1 against 3:1` and tightest hold `'{call to action}' 2.20/1.40 s` (2026-11-12, 640x360).
- **Q404** counts as ink the pixels within 24 levels of `fg` inside the box padded by 2 px (`INK_SLACK` 3 px at the ends). It is NOT CHECKED when the item has no `fg`, `reveal_end` is outside the piece, the string never rests after `reveal_end`, or no pixel of its `fg` is in its box at rest.

### Frame 0 and the file, in numbers

At the proof Q501 reads the drawn frame 0 (`qa.first_frame`); on the file it decodes frame 0 at full size as a player shows it (`qa.frame_grey`, grey 0.299 R + 0.587 G + 0.114 B). Q502 decodes the last frame from the final second. Q503 compares the last frame with the one `round(fps)` frames before it on the 64x36 block grey of the decode, and is NOT CHECKED when that decode fails or comes back short. A file cut to 35 percent of its bytes (selftest case `files.cut`) keeps Q501 PASS and reads Q502 and Q503 NOT CHECKED. Template at 640x360, 2026-11-12: frame 0 mean 34.8 and std 18.3 drawn (Q501 row).

Gate 7 comes from one ffprobe run (`qa.probe`), except Q708. Q708 (`qa.colour_round_trip`) encodes five flat swatches, (40, 180, 60), (192, 32, 32), (0, 255, 0), (30, 60, 200) and (128, 128, 128), through `contract.COLOR_VF` and `COLOR_FLAGS` with libx264 at CRF 18, decodes them with `DECODE_709` and takes the median of each swatch's core; it is NOT CHECKED when the encode or decode fails (an ffmpeg without libx264). It tests this machine's ffmpeg chain, not the file's own pixels.

### Loudness and the stack, in numbers

- **Q801** comes from one ffmpeg `ebur128=peak=true` pass (`qa.loud`), which also keeps every 100 ms line for Q802. It runs only when the file has audio and the piece is not silent.
- **Q802** reads the true peak from the ebur128 Summary. The loudest moment is found channel by channel on the 4x oversampled 48 kHz decode, inside the loudest 100 ms frames (`qa_stack.moment`, `peak_moment`). A FIX row spans every 100 ms frame over -1 dBTP, names up to 8 cue sheet sounds sounding within 50 ms (span, gain, peak plus gain, level there, bus), the music bed and SFX bus levels there from `mix_raw.wav` and `sfx.wav`, and an order to cut the designed sounds within 20 dB of the loudest: impact, then chime or bell, then press or drop (`CUT_ORDER`, a house heuristic). `SILENT` makes it PASS; no loudness measured makes it NOT CHECKED.
- **Q803** decodes the audio at 8 kHz mono and takes the RMS of each whole second; seconds 1 to n - 2 are inside. One NOTE per run of quiet seconds; `ALLOW` lists a time in the second. A piece under 3 s passes with nothing to measure; a stream that decodes to nothing is NOT CHECKED.
- **Q804** (`qa_stack.stack_rows`) counts every SFX-bus sound on the cue sheet and a music-bus sound only when it serves a CUES label; a muted sound counts for nothing. Heavy is the sheet's `heavy` flag, else a name with kick, hit, boom, impact or drop (`HEAVY`). A riser, swell, suck, reverse or whoosh (`LEAD_IN`) whose end or landmark lands within 3 frames or 100 ms (whichever is longer) of a heavy sound is one gesture with it and does not count. NOTE for: 2 or more heavy sounds within 3 frames; 2 or more sounds on a `payoff=True` cue, counting those within 3 frames of it and a lead-in still sounding 0.1 s before it; more than 2 sounds in any 100 ms (a taste rule). No cue sheet is one NOTE; a sheet that cannot be read is NOT CHECKED; `ALLOW['Q804']` and `SILENT` clear it. Template: `no stacked sounds: 2 placed sounds checked ...; 19 music-bed or muted sounds not counted` with a custom score (2026-11-12).
- **Q805** is made by `audio.master` inside `run_all.py full` and `audio`, not by `qa.py check`. The master applies one static gain to -14 LUFS and a 4x true-peak limiter at the ceiling (default `audio.CEILING`, -2.0 dBTP, with no added delay), then measures and nudges for up to 6 passes. `run_all.master_and_mux` then measures the muxed file and masters again, at most 3 times, while its true peak is over -1.3 dBTP, and keeps the clean master with the lowest peak (`engine.md`, Sound in a build, in detail).

### Sync, in numbers

- **Q901** (`qa.grid_rows`) needs a SCHEDULE and a BPM (`--bpm` or `scenes.BPM`). The cuts are `CUTS` when scenes.py has it, else every SCHEDULE start after 0. The beat is 60 / BPM; `ALLOW` lists a planned off-grid cut. Without `--scenes` there is no row.
- **Q902** (`qa_sync.cue_rows`) has three modes.
  - With a cue sheet (`cuesheet.json`, `cue_sounds.npz` and the stems `sfx.wav` or `mix_raw.wav`), each cue is matched to its sheet entries by label (nearest in time when a label repeats), else to unlabelled entries within 100 ms (`NEAR`), SFX bus first. Each entry is found where it really sits on its stem by normalised cross-correlation in 250 Hz to 9 kHz (from 20 Hz on a lossless stem when the band misses), within 250 ms of the sheet's place, at a match of 0.7 or more (`MATCH`); overlapping recorded neighbours are fitted out by least squares, and copies of one sound close together (a match of 0.9, `TWIN`) are measured as a group. The instant heard is the sound's landmark, or its audible attack at -15 dB when it was placed by its start or onset and the attack comes 5 ms or more later. Late past one frame (`late_limit`: 1000 / fps, at most 60 ms) or early past -40 ms is a FIX, outside -5 to +15 ms a NOTE; a cue no sound serves is a FIX, and a copy that cannot be told from its twins is NOT CHECKED. The picture side looks for the strong change nearest the cue frame (0.2 percent or more of pixels moving over 12 levels on the 192x108 grey), from 4 frames before to `CUE_LAG` + 2 after, inside the cue's `region=` box, else the box of the registry text that changes across the cue, else the whole frame; outside -1 to `CUE_LAG` + 1 frames, or no change, is a NOTE, and a whole frame where under 0.2 percent moves is "not measurable" (a NOTE). The decoded file confirms each sound within 20 ms; one NOTE when it moves confirmed cues by more than 2 ms. Template with a custom score: `all 2 cues land: audio worst +0.0 ms on sfx.wav; the decoded file confirms 2 of 2 within 2 ms` (2026-11-12).
  - With no cue sheet, one NOTE row from an onset detector (a 3 dB rise in 10 ms windows within 100 ms of the cue, on the whole mix or above 2 kHz, or in the cue's own `band=`): a guess, not a measurement. It passes only when it finds every cue.
  - A silent piece, or CUES with picture cues only, measures the picture side alone.
  - `NO_CUES` makes it PASS. Empty or missing CUES is NOT CHECKED (a PASS for a silent piece), as are CUES in a form `contract.cues` cannot read, a sheet without its buffers or stems, and a sheet row with no `i`, `t` or `landmark_s`. NOTE rows honour `ALLOW['Q902']`. Without `--scenes` there is no row.
- **Q903** (`qa_sync.mux_rows`) needs both streams and a piece that is not silent. Rows: the audio and video `start_time` within 1 ms (a NOTE when ffprobe reports none); the decoded audio against `mix.wav` in three 2 s windows at 12, 45 and 85 percent, searched +/- 0.1 s after a 500 Hz high-pass, FIX past 1 ms, searched again over +/- 1 s at a match of 0.8 or more when no window matches, NOT CHECKED when none does; and the same against `mix_raw.wav`, which catches a delay in the master, a NOTE when unmatched. A build folder without `mix.wav` is NOT CHECKED. Template: `+0.00 ms at 12%, +0.00 ms at 45%, +0.00 ms at 85%` against both (2026-11-12).
- **Q904** and **Q905** run at the proof and in `qa.py lint` (`qa_lint.grid_rows`). Q904 reads every SCHEDULE start and end, `DURATION` and every cue time; `ALLOW['Q904']` within half a frame clears a planned one, and CUES it cannot read make it NOT CHECKED. Q905 passes when there is no BPM, and its fix lists the whole-frame tempos from 60 to 200 BPM at the build's rate (60, 72, 75, 90, 100, 120, 150, 180 and 200 at 30 fps). Template: `one beat at 120 BPM is 15 frames at 30 fps`.
- **Q906** is `qa.py calib` (`qa_sync.calib`): a 4 s clip, black but for one white frame at 2 s and quiet but for a one-frame 1 kHz blip on that frame over a 3 to 6 kHz noise bed, through `audio.master` and `contract.mux_cmd` (the mux `run_all.py` runs), read back as qa.py check reads a file. Three rows: the white frame comes back on its own frame; the blip lands within 1 ms of it (the row splits the offset into the master's part and the mux and AAC part); the two streams' `start_time` are within 1 ms. It reports where an offset entered and never writes one for the mixer to subtract.

### Purity and lint, in numbers

**Q1201** (`qa_purity.run`) picks at most 2 + 2n frames (n is `--n`, default 16): the first and last frame; both sides of the cuts (SCHEDULE starts and ends, CUTS, the edges of WINDOWS), spread over at most n / 2 cuts, then the frame after some of them; the midpoints of every window and scene, the CUES and KEY_TIMES, then even steps; plus every `--t` second and one frame every `--grid` seconds. It draws them three ways: in order in this process, reversed in a fresh `python -I` process (a new string hash seed, no PYTHON variables) at the same time, and through a spawn pool (2 to 4 processes) as the render does. Digests (`contract.frame_digest`) must match exactly. A FIX names how many frames differ, the worst frame, how many pixels differ, a diagnosis from fresh processes (drawn cold twice with one hash seed, cold with a second seed, twice in one process, and behind each of its 8 nearest samples, `NEAREST`) and the owning scene function. It is NOT CHECKED when scenes.py does not import, has no DURATION, a fresh process cannot draw it, a pass hangs for 240 s (`TIMEOUT`), or draw(t) raises. That holds for `qa.py purity`; inside `run_all.py proof` the text gates and the recorder draw first and are not guarded, so a draw(t) that raises stops the proof with its traceback and no `PROOF:` line. The row also says whether the lines the lint flags as Q1202 ran on any sampled frame. Template at the proof: `draw(t) pure: 24 frames (8 ends and cuts, 16 scene midpoints and even steps) ... at 640x360, 30 fps, SS 1 (0.8 s)` (2026-11-12).

**Q1202 to Q1206** (`qa_lint.run`) read the syntax trees of scenes.py and every local module it imports, skipping the engine's own files and `qa*` modules. Each row lists the first 5 sites as `file:line text in function`; `qa.py lint --all` lists every one.

- Q1202: `time.time`, `perf_counter`, `monotonic` and their kin, `datetime.now`, `today` and `utcnow`, `os.urandom`, `os.getpid`, `time.localtime` and the like called with no timestamp, `secrets.*`, `uuid.*` except `uuid3`, `uuid5` and `UUID`, the shared `random` stream or an unseeded `random.Random`, numpy's global stream or an unseeded generator, and `hash()` of a str or bytes (the hash seed changes per process).
- Q1203: a `global` written, an item or attribute of a module-level object written or deleted, a mutating method (`append`, `update`, `paste`, `putpixel` and others) on one, drawing onto a module-level image, drawing from a module-level random generator, and a mutable default argument. Code that runs only while the module imports is skipped.
- Q1204: a top-level def or class named like something `engine.py` defines or re-exports from its folder, or like something a star-imported local module defines.
- Q1205: `.text()` or `.multiline_text()` on an ImageDraw (a single-band mask image, or a number as the fill, is allowed), and loading a font with `ImageFont.truetype`, `FreeTypeFont`, `load_default`, `load` or `load_path` instead of `engine.font()`.
- Q1206: a hex colour string (`#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa`) inside a function or as a parameter default, or an RGB or RGBA tuple of ints from 0 to 255 passed to a colour keyword (`fill`, `color`, `colour`, `outline`, `stroke_fill`, `background`, `bg`, `fg`, `ink`, `col`, `tint`, `halo`) or used as a colour parameter's default. A fully transparent tuple, and three or four mixed decimal digits such as `#404`, do not count.

The pragma `# zoetrope: <tag>` goes on the finding's line, on the def line of the function holding it, or for Q1203 on the line that binds the module-level name:

| Tag | Clears |
|---|---|
| `rng-ok` | Q1202 |
| `state-ok` | Q1203 |
| `shadow-ok` | Q1204 |
| `text-ok` | Q1205 |
| `colour-ok` or `color-ok` | Q1206 |

Several tags may share one comment, separated by commas or spaces. Template: `LINT: PASS (7 checks, 0 FIX, 0 NOTE, 0 NOT CHECKED)` (2026-11-12).

### Size, in numbers

Q1001 compares the file in MB of 1,000,000 bytes with `--max-mb`, else `scenes.BUDGET_MB`; `run_all.py full --budget-mb` passes its budget the same way. Q1002 is size x 8 / duration over 12 Mb/s. Template: 0.3 MB (2026-11-12). The budget's bitrate cap is in `formats.md`.

### What ALLOW can clear

`ALLOW` lists times or spans for NOTE-level findings only (`contract.allowed`); it clears no FIX and no NOT CHECKED. The tolerance is 1 frame unless the table says otherwise.

| Code | What an entry matches |
|---|---|
| Q204 | An unreported string too faint, small or symbol-only to be a FIX |
| Q207 | The middle of a changeover gap, within half the gap plus a frame |
| Q209 | A moment where registered text is not drawn |
| Q402 | The middle of the small text's longest rest |
| Q603 | A span holding the whole passage, with 1 s of slack at either end |
| Q803 | A time inside the quiet second (0.5 s tolerance around its middle) |
| Q804 | The stack's time, within 3 frames |
| Q901 | The cut time |
| Q902 | A cue time, for its NOTE rows and the onset detector's cues |
| Q904 | The off-grid time, within half a frame |
| Q1101 | The pop frame |
| Q1102 | A span covering the frozen run (a frame of slack at either end) |
| Q1103 | The cut frame |
| Q1104 | The stalled frame |

### The text recorder, in detail

`qa_registry` holds `text_items(t)` to what `draw(t)` really paints. It runs at the proof and inside `qa.py check --scenes`.

**What it records.** While one `draw(t)` runs, it wraps the PIL entry points and logs every `ImageDraw.text` call: the string, its ink box with any stroke, its glyph box, the fill's alpha, the font and size, the stroke width, the image drawn on, and the pixels the call changed. It imports a private copy of scenes.py with the hooks on, so tiles and sprites cached before the gate ran are made again and recorded. Labels qa.py and proof.py draw on their sheets are drawn outside it.

**How it follows text to the frame.** `copy`, `convert`, `filter`, `point`, `getchannel`, `split`, `crop`, `resize`, `reduce`, `paste`, `alpha_composite` (method and function), `putalpha`, `Image.blend`, `Image.composite`, `Image.merge` and the `ImageChops` operations carry each record to where it lands, with its new place, clip and opacity: a blend keeps its weight, and a composite clips the text to the part its mask shows. A record that reaches an image the size of the frame (or SS times it) has landed. When the returned frame still carries records, exactly what reached it counts; when the chain broke (the frame came back through numpy), every record that reached a frame-sized image counts, and so does every call that never did. Letters drawn one call at a time on one baseline join into their words; copies of one string at one place (a halo, a glow, a shadow, motion-blur sub-frames) count once, and a stroked copy is never the fill.

**Which frames.** Every frame inside a `WINDOWS` span (with a frame either side) and every caption changeover (a registered alpha between 0.05 and 0.98, or the set of shown strings changing), one frame every 0.25 s elsewhere (`GRID`), and the last frame. Q204 then walks the span edges of up to 20 unreported strings a frame at a time (`REFINE`). It times 6 frames first and uses worker processes only when the rest would take over 20 s, or when `--registry-procs` asks. A drawn box with under a quarter of its area on the frame (`SEEN`) is not counted.

**Matching.** A drawn item matches a registry item with the same string near it (within half an em, at least 8 px), or as part of a registered string (a typewriter, one line of a wrapped block), or as a set of registered words, or with spaces taken out. Strings are compared with white space collapsed and case folded.

**Where it is blind.**

- Text that never goes through `ImageDraw.text`: glyphs pasted as images, text masks built in numpy, a pre-rendered bitmap. Q208 is NOT CHECKED when it sees no call at all; otherwise such text is simply missing from Q204.
- Text that was rotated or transformed: the record goes along but its place is lost, so it is matched by its string alone, its box is not compared (Q205) and its cover is not measured (Q206).
- Text whose layer reaches the frame through numpy: it still counts, but by its string alone, with no box to compare.
- Frames it did not sample: between grid frames outside windows and changeovers.

### The proof sheets and review_times.json

`review_times.json` entries are rounded to 3 decimals; kinds, highest rank first (`contract.KINDS`): `finding`, `changed`, `pop`, `cut`, `window`, `key`, `audio`, `rest`.

| Step | What it does to the file |
|---|---|
| `run_all.py proof` | Starts it afresh: both sides of every cut (`cut`), the first and last frame of every window (`window`), the middle of each string's longest rest (`rest`), `KEY_TIMES` (`key`), and a `finding` for every FIX, NOT CHECKED and NOTE row of the proof that names a moment. It keeps the `changed` entries of the last `qa.py diff` |
| `run_all.py full`, `audio` | The scans add theirs; then a `finding` for every row that is not PASS and names a moment (`<code> <status> <item>: <meaning>`); then the sheets are redrawn and `n` written back |
| `qa.py check --scenes` | The scans add theirs; with `--json`, every other finding too |
| `qa.py diff` | Takes out what the last diff added, then adds `changed` entries: status FIX for an undeclared change, NOTE for a declared one or a sampled unchanged frame |
| `qa.py approve` | Retires the `changed` entries the review covered, and pins every time in the file as a key frame |
| `python proof.py keys` | Redraws the sheets from the file and writes `n` back |

A file that does not parse is moved to `review_times.json.bad` with a warning, and a new one is started. `qa.py audiostrip` draws the numbered cells on its keys lane.

| Sheet | What it shows | Drawn by |
|---|---|---|
| `proof.png` | Up to 12 stills: every scene midpoint, then the first and last frame of each window, then scene boundaries | `run_all.py proof` |
| `proof_keys.png` (and `_2`, `_3` pages) | One cell per frame of `review_times.json`, most urgent first: FIX, NOT CHECKED, changed, pop, NOTE, cut, window, key, audio, rest. A cap of 40 cells drops captions at rest first and never a FIX | `run_all.py proof`, again at the end of `full` and `audio`, and `python proof.py keys` |
| `proof_strips.png` | Frames f-2 to f+2 from draw(t) for every entry with a strip (Q1101 pops; Q203, Q207 and Q404 from `check --json`), at most 24 | The same steps |
| `proof_gantt.png` | Scenes, windows, texts (solid at rest, dim while fading), cues and the numbered cells on one time axis, with bar lines on the BPM grid; at most 2000 px wide | The same steps |
| `review/audio.png` | The sound as a picture | `qa.py audiostrip` |
| `review/look.jpg` | Frames of the encoded file | `qa.py look` |
| `review/diff_*.jpg` | Before, after and difference of each changed passage | `qa.py diff` |

On the template at 640x360 the proof wrote `proof_keys.png: 7 of 7 key moments`, `proof_gantt.png (1920x252)` and no strip sheet (2026-11-12).

### Approval, in detail

**`qa.py approve`** flags: `--scenes` (the working folder, default `.`), `--review <file>` (the reviewer's reply, verbatim), `--video` (default: `OUT` in `run_all.py`, else `out.mp4`), `--reviewer <id>` (when the reply has no `reviewer:` line), `--override "<why>"` and `--procs`.

It stores, in `approved/`: `approval.json`; `frames.hash` and `thumbs.npy` of the last render; `qa.json` when there is one (the `--baseline` for Q1302); `mix_raw.hash` (one digest per 100 ms block of the pre-master mix) with a copy of `mix_raw.wav`; and `src/`, a copy of scenes.py and every local module it imports. `approval.json` holds the time, the file (path, sha256, size, written time, the sha256 of its decoded picture, duration, fps, size, frame count, loudness, true peak), the digests of each scene's key frames (its first, middle and last frame, plus every `review_times.json` time and every `qa.py look` copy made after the file was written), the reply (verbatim, with its sha256 and the verdict, reviewer, stage, file, written time and `frames seen:` line read from it), any overrides, the environment (Python, Pillow, numpy, ffmpeg version, the sha256 of each font file the drawing opened, the frame size, the sha256 of each local module), the sha256 of every file in `approved/` and the history of earlier approvals. It writes everything into `approved.new/` and swaps it in with two renames, so a run that stops on the way leaves the previous approval whole.

It **refuses** (exit 1, `REFUSED: ...` lines) when the reply is missing, is not REVIEW PASS, names no stage or a stage other than final, names no file or another file, gives no written time or one more than 1 s from the file's; when `qa.json` has a FIX or NOT CHECKED row outside the approval codes (`REFUSED: qa.json has NOT CHECKED rows: Q705, Q707, Q708` on a rung b file); or when `qa.json` is older than the file. `--override "<why>"` approves anyway and records each refusal with the reason and the time; qa.py check then shows it as a Q1301 NOTE until a clean review is approved. It **cannot approve** (exit 2, `CANNOT APPROVE: ...`) when scenes.py, the file, `frames.hash` and `thumbs.npy`, or the review file is missing; when the file's size, rate or frame count, or `frames.hash`, does not match the build; when scenes.py does not draw; or when `frames.hash` no longer matches draw(t) at the key frames (scenes.py changed after the render). With no `qa.json` it only prints a note. Success reads `APPROVED out.mp4 (sha256 <12 hex>, <n> frames, <k> scenes, <m> key frames; REVIEW PASS by <reviewer>)`; with no reply, `REFUSED: no reviewer verdict: pass --review <file holding the reviewer's reply>`.

**`qa.py check` afterwards** (`qa_approve.check_rows`, only when the working folder holds an approval):

1. A changed frame size (E.W, E.H, E.FPS or E.SS, or the file's own size and rate) is Q1304 NOT CHECKED, and nothing else is compared.
2. The approved key frames are redrawn now, in worker processes. A change in Python (major.minor), Pillow, numpy or a font file is Q1304 NOT CHECKED when a key frame moved, and a Q1304 NOTE when none did.
3. Q1301 FIX when any scene's key frames differ, or a scene was added or removed (a scene renamed in its old time slot is matched). Its fix names the windows for `qa.py diff --expect`.
4. Otherwise Q1301 PASS, `approval current`, or a NOTE when an override is recorded. Then, when the file is not the approved one: its decoded picture the same as approved is a NOTE (`only the audio changed`); a different picture is a FIX, saying whether only the encode changed (the last render's `frames.hash` matches the approved one) or which frames differ.
5. With `--baseline`, Q1302 compares this run's rows with the baseline's, and is NOT CHECKED for gates that passed there and made no row now (a flag the baseline run had is missing).

An `approved/` whose files do not match the hashes `approval.json` recorded makes Q1301 NOT CHECKED. After a change to the end card's ground colour the row reads `FIX Q1301 STALE APPROVAL: scenes end changed since the approval ...`.

**`qa.py diff`** (flags in the table above) draws every frame of the current source at the approved size and compares it with the approved `frames.hash`, and compares `mix_raw.wav` with the approved blocks after taking out one overall gain (the median of the per-block gains, as the pre-master mix is peak-normalised); a block changed when what is left is over 2 steps of 16 bit RMS. It uses `mix_raw.wav` as the last render wrote it, and never rebuilds the mix. Rows: Q1303 FIX for a change outside every `--expect` window, NOTE inside one, FIX for a window that saw no change, PASS when nothing changed; Q1304 when the size or environment changed and frames moved; NOT CHECKED when there is no approval or the frames cannot be drawn. A window holds frames `frame_of(t0)` to `frame_of(t1) - 1`, like a scene. It writes `review/diff_tSSS.SS.jpg` triptychs (before, after and the difference in magenta) at the first, middle and last frame of each changed span; a change over 30 percent of the film and more than one scene (or of a one-scene film) is global, sampled at about twelve even steps plus both sides of every cut, on `review/diff_global_NN.jpg` pages. The last line is `DIFF: SAME as the approval`, `DIFF: CHANGED, every change declared with --expect (re-review each NOTE above)`, `DIFF: FIX (...)` or `DIFF: NOT CHECKED (...)`; exit 0, 0, 1 or 2.

**What approval protects against.** It is per hash, not per conversation turn: a changed source that moves a key frame, a re-rendered or re-encoded picture, a new mix, a new environment that moves pixels, a new frame size and an edit inside `approved/` all show up in check, and `diff` names every changed frame and audio block.

**What it does not protect against.** `qa.py check` redraws key frames only; a change between them shows through the file's picture hash once the film is rendered again, or in `diff`, which draws every frame. The ffmpeg version is recorded but not compared (Q708 covers the colour chain), and a Python patch release is ignored. Approve reads only the reply's verdict, stage, file name and written time, so the reply's care is the reviewer's; it approves with no `qa.json` at all (a note only); and an `--override` approves on the record.

### The self test, in detail

**How to run it.** From a full copy of the engine: `cp -r engine/. <folder>/`, then `python qa.py selftest` in that folder. The fixtures are the `qa_fixtures/` package beside `qa_selftest.py`; a copy of only the `.py` files has none, so the run prints `MISSING qa_fixtures/__init__.py: ModuleNotFoundError: No module named 'qa_fixtures'`, marks every code it was asked to prove UNCOVERED and exits 2. The template control renders the `scenes.py` beside `qa_selftest.py`, so a copy holding a video's own scenes.py controls that instead; the run prints the template's path and sha256 to show which. Meanwhile, in two threads, the template is copied to temp folders and run through `run_all.py proof` and `full` at 1920x1080 and 1080x1920; each must end with 0 FIX, 0 NOT CHECKED and, after `full`, a DELIVERED line.

**What it prints.** One line per judged want: `<outcome> <code> <status> <case> <detail>`, where the outcome is `ok`, `MISSED` (the planted fault did not fire), `WRONG` (it fired with the wrong item, time, value or count, or a known-good input fired), `EMPTY` (the gate looked at 0 items), `MISSING` (a fixture file or module is missing) or `ERROR` (the case raised; the line says where). Then one line per template run, `UNCOVERED` for a code no fixture makes fire at its failure status, `STALE` for an `EXPECTED_GAPS` entry a fixture now covers, `gap` lines, `selftest took ...`, `kept <folder>` when it failed or `--keep` was given, and the last line, `SELFTEST: PASS|FAIL (<missed or wrong>, <not proven>) (<n> fixtures, <k> of <K> codes covered, <g> expected gaps)`. A code counts as covered only when a want at its failure status in `contract.CODES` held. The count of fixtures is the judged lines: every want of every case plus the four template runs.

**What it proves, and what it does not.** It proves that every code can still fire on the right item, time and value, that its known-good inputs stay clean, and that the template passes at 16:9 and 9:16 on this machine's ffmpeg, fonts and libraries. It does not prove that a gate catches a fault unlike its fixtures, how often a gate flags a real film by mistake, or anything about how a video looks or sounds. `--quick` skips the `full` renders, and `--only` runs no template control at all.

### More known limits

- The flash gate measures WCAG 2.2's thresholds on a 192x108 decode with 4 x 4 pixel cells; area is counted in whole cells, so a flash of exactly a quarter of a window can go either way.
- Q201 measures the 4 percent pad only. Platform overlays on 9:16 (buttons, captions, progress bars) are measured by no gate (`formats.md`).
- Q501 and Q502 read only the grey mean and spread of one frame. Q708 tests this machine's colour chain on swatches, not the file's own colours; Q1105 compares grey means, so an error that shifts colour but keeps grey passes it.
- Q803 looks at whole seconds; a gap shorter than a second is not seen.
- Q902 measures sound effects placed with a cue sheet, on the lossless stems; without a sheet its detector is a guess. It does not measure narrated words (Q806 and Q807 do, by transcript, `voice.md`). A small moving part on a large still frame needs `region=` or registry text, or the picture side is not measurable.
- Q903 looks at three 2 s windows; Q906 runs on its own test clip, not the film.
- Q1201 draws at most 2 + 2n sampled frames plus `--t` and `--grid`; a state leak that shows only on other frames is not seen. The lint reads syntax: it cannot follow a name whose type it does not know, such as an object passed in with its own `text` method.

### Template numbers, 2026-11-12

The shipped template (7.5 s, 120 BPM, 225 frames) at 640x360 on this machine's ffmpeg, in a scratch copy of the engine:

```
PROOF: PASS (23 checks, 0 FIX, 0 NOTE, 0 NOT CHECKED)
master: ceiling -2.00 dBTP, mix.wav -14.0 LUFS at -2.00 dBTP (Q805 PASS) -> out.mp4 -14.0 LUFS at -1.90 dBTP
QA: PASS (50 checks, 0 FIX, 0 NOTE, 0 NOT CHECKED)
APPROVAL: none yet -> final review, then qa.py approve
DELIVERED <working folder>/out.mp4 (0.3 MB, 7.50 s, -14.0 LUFS, -1.9 dBTP)
QA: PASS (45 checks, 0 FIX, 0 NOTE, 0 NOT CHECKED)
wrote review/audio.png (1600x656) in 0.5 s: I -14.0 LUFS, TP -2.0 dBTP, 0 of 75 frames over -1 dBTP; sync: 2 within 1 frame (of 2 audio cues)
```

The first five lines are `run_all.py proof` and `full`; the 50 rows of `full` are the 45 of `qa.py check` plus Q805 and the four scans of `thumbs.npy`. The sixth is `qa.py check out.mp4 --scenes . --size 640x360 --fps 30 --bpm 120`, the seventh `qa.py audiostrip out.mp4 --scenes .`. The proof's 23 rows are Q501, nine text gates, the five recorder codes, Q1201 and the seven lint rows. The last selftest figure on record is in the self test section above.
