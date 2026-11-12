# The engine

Contract: one Python module per video, `scenes.py`, with `draw(t) -> PIL.Image`, pure and deterministic (seeded random: `rng(scene, element, frame)`, never one stream advanced frame to frame; no state across frames), and all timing from one `TIMELINE` (or a hand-written `SCHEDULE` dict). `run_all.py proof` checks it: the purity gate (Q1201) draws up to 34 frames (24 on the template) in order, reversed in a fresh `python -I` process and through the render pool, and needs identical digests; `qa.py lint` (Q1202 to Q1206) flags unseeded randomness, clocks and `hash()` of a str, module state written inside functions, redefined engine helpers, text drawn past the engine text helpers and colour literals inside functions. Proof first, then every frame piped into the encode, then the audio, the master, the mux and every QA gate.

The code is real files in the skill's `engine/` folder (`<skill>/engine/`, where `<skill>` is the skill folder as an absolute path). Copy the whole folder into the video's working folder (`cp -r <skill>/engine/. outputs/{slug}/`, so `qa_fixtures/` comes along; `outputs/{slug}/` under the current folder unless the user names one, never inside `<skill>`) and edit `scenes.py` there; never edit the skill's own copies for one video. Run every script from the working folder with `uv run --no-project --with-requirements requirements.txt python <script>` (Pillow and numpy pinned and hashed in `requirements.txt`; `bash <skill>/setup.sh` checks the whole toolchain once).

| File | What it does |
|---|---|
| `engine.py` | Helpers shared by scenes.py: size and fps globals, easing, fonts (Windows Arial first; a missing font raises; `bold="Nunito:800"` names one of the free families in fonts.py), colours, gradient, rounded rects, shadow, text (`tracking=` for letter spacing), wrap, supersample `finish`, and the text helpers every build needs: `text_box` (the box to report in the registry, same `tracking=`), `fit_size` (shrink to fit, never under 36 px), `text_outline`, `text_halo`. Timing: `scene_at` (decided on integer frames, nearest frame), `scenes_at` (both scenes and a 0 to 1 mix inside a transition window), `compile_schedule` with `Scene` and `Transition`, and the frame clock re-exported from contract.py (`frame_of`, `snap`, `stepped`, `sample_of`, `frame_sample`, `on_grid`). Also `rng(*keys)` (a numpy Generator seeded by what is drawn) and `spring`, `settle_time` (Remotion's spring and measureSpring) |
| `scenes.py` | The per-video template: palette, `LINES`, `TIMELINE` (scenes as durations, compiled by `compile_schedule` into `SCHEDULE`, `DURATION`, `CUTS`, `WINDOWS`, `CUES`), `BPM`, `CARD` (the style card it follows), `draw(t)`, and the registry: `text_items(t)`, `CUES`, `CUE_LAG`, `KEY_TIMES` (`qa-gates.md`). One `layout(t)` drives both `draw()` and `text_items()`: every scene active at t (both inside a transition window, crossfaded by their share), each with its `title_state()`. The first scene starts fully drawn (frame 0 is the thumbnail), the last holds to the end (the end card), the others enter on their cut (one empty frame per changeover) |
| `transitions.py` | Scene transitions as pure `f(a, b, p)`: `crossfade`, `wipe`, `push`, `slide`, `iris`, `clock`, `blinds`, `dip`, `luma` (ideas from gl-transitions). p = 0 is a and p = 1 is b exactly; `MENU[name].flash_risk` is "check" for dip (run `qa.flash_window` over its window) |
| `fonts.py` | The 14 free families 21 style cards name (SIL OFL: Inter, Nunito, IBM Plex Mono, Poppins, Archivo Black, Barlow Condensed, Cormorant, Cormorant Garamond, JetBrains Mono, Sora, Caveat, Bodoni Moda, Fraunces, STIX Two Text), pinned to one google/fonts commit with each file's size and sha256, cached in `~/.cache/zoetrope/fonts` (`ZOETROPE_FONTS` moves it). `python fonts.py fetch` downloads what is missing (6.8 MB), `list` shows the cache. `engine.font(size, "Family:weight[:italic]")` loads one: a variable file is set to the weight and its optical size to the output size; a weight or italic the cache does not hold raises |
| `grain.py` | `grain(img, t, std=1.6, hz=None, tiles=4, seed=0)`: film grain from 4 seeded 256 px tiles, picked and offset by whole pixels per step (default fps / 2: every grain held 2 frames), pure in t, on PIL images or float arrays. Call it after any weave shift; sizes in `formats.md` |
| `proof.py` | The review sheets: `contact_sheet` (`proof.png`), `key_sheet(findings=rows)` (`review_times.json` afresh, keeping `qa.py diff`'s changes; then `proof_keys.png`, `proof_strips.png`, `proof_gantt.png`) and `keys(rows=)` (the last three again from the file). `python proof.py keys [--size WxH --fps N]` redraws them at the size in `build.json`. Each frame is drawn once per run. A registry older than 2.2 (items without `s`) reads as none (`qa-gates.md`, gate 1) |
| `render.py` | `render_to_ffmpeg`: every frame drawn in a pool of spawned processes into a shared-memory ring and piped raw, in order, into one H.264 encode (`video.mp4`), writing each frame's digest and grey thumb (`frames.hash`, `thumbs.npy`); `scenes.STATIC` holds drawn once. `encode_cmd` is its ffmpeg argv. `render_parallel` and `render_frames` write PNG frames (rung b, debugging; `frames=range(a, b)` for one passage). scenes is imported inside the functions, because each Windows worker must set the frame size first |
| `run_all.py` | The stages: `proof`, `full [procs]`, `audio` (below). Every stage takes `--size WxH`, `--fps N` and `--ss N`, read at the top of the file before scenes is imported (every render worker runs the top again with the same argv); everything else is under `if __name__ == "__main__":` |
| `audio.py` | The template score (`bed`, `music`), `render_audio(scenes)` (mix_raw.wav, the sfx.wav stem, the cue sheet), `write_wav`, and `master`: one gain to -14 LUFS plus a 4x true-peak limiter at -2.0 dBTP, checked with ebur128 (`measure`), written at 48 kHz, with Q805 (`mixing.md`) |
| `synth.py` | The numpy instrument kit for scored pieces (kick, snare, hat, clap, bass, pad, pluck, riser, boom, whoosh, tick, reverb, sidechain `duck`), every sound seeded from its own arguments (`rng_for`, `noise`), `landmarks`, and the one placement path: `place` (onset, peak, end or pad on the cue), `put` (first sample), `put_peak`, recorded on the cue sheet inside `with synth.recording():` (`beat-sync.md`, `music.md`). `python synth.py demo.wav` writes a 4 s 120 BPM demo |
| `sampler.py` | Recorded instruments for a score (14, CC0, from Versilian Studios' VSCO 2 CE and VCSL): `note`, `chord` and `hit` return mono arrays at `synth.SR` with the attack at sample 0, for `synth.place` beside the synth kit. Fetched on demand into `~/.cache/zoetrope/instruments` (`python sampler.py fetch <names>`, pinned commits, sha256 per file), decoded once with ffmpeg; `credits(names)` gives the delivery report's line (`instruments.md`) |
| `plate3d.py` | True 3D as a plate (`plates.md`): `python plate3d.py render stage.py [--quality proof]` runs a stage script in Blender (the bpy 5.2.3 wheel, its own Python 3.13 uv environment, Cycles on the GPU) and writes one image per frame to `plates/<name>/`; `Plate(name).frame(t)` reads them in scenes.py, `Plate.at(track, t)` gives the canvas point of a tracked 3D object, and `check()` is what `run_all.py` asks before it draws (a stale, unfinished or, for `full`, proof-quality plate stops the run). `fetch`, `missing`, `info`, and `run stage.py <args>` for a measurement on the rig with no render |
| `stage3d.py` | The 3D side of a plate, run inside Blender's Python only (scenes.py never imports it): `Stage` (set, studio light, materials, rounded shapes, tubes, solid type, camera with depth of field, screen tracks), the `Buddy` character, and the motion helpers (`jump`, `hop`, `settle`, `squash`, `walk`, the eases). `run(build, fps, dur, size)` renders the frames |
| `voice.py` | `synthesize` narrates lines offline into `narration.wav` and `narration.json` (one cached file per part; `lexicon=` respellings, `[pause 300ms]` markers, `fit=` per line), `word_cue`, `onset_offsets`, `slot`, `load_narration`, `ENGINES` (sapi and kokoro-ts, both tested), `KOKORO_LANGS`, plus `dec`, `span`, `section_beats`, `duck_mix` (`voice.md`) |
| `voice_samples.py` | The same three lines with every ready voice engine and voice (three Hindi lines for a Hindi voice), for listening |
| `requirements-voice.in` | The pins of the side environments (kokoro-ts, the speech check); not installed by setup.sh, not compiled |
| `qa.py` | The gate CLI and the core gates (`qa-gates.md`): `check`, `look`, `holds`, plus the subcommands the gate modules add (`purity`, `lint`, `owner`, `approve`, `diff`, `verify`, `calib`, `audiostrip`, `selftest`). Functions: `text_gates`, `registry_rows`, `proof_rows`, `min_hold(text, profile)`, `slot_budget`, `HOLD_PROFILES`, `flash_report`, `flash_window`, `flash_report_file` (Q601 to Q603 rows by default, `rows=False` the older list), `probe`, `loud`, `colour_round_trip`, `frame_grey`, `grid_rows`, `cut_times`, `snap_ok`, `review_entries`, `look`; `check`, `probe`, `look` and `frame_grey` take `ff=` |
| `qa_scan.py` | Gate 6 flashes to WCAG 2.2 (Q601 general, Q602 red, Q603 extended band) on the linear-light decode, the frame scans (Q1101 pops, Q1102 frozen runs, Q1103 unplanned cuts, Q1104 stalls) on the 192x108 grey decode, and Q1105 (the file against thumbs.npy); `flash_rows(None, fps, aspect, t0, lin=...)` for drawn frames, `scan_thumbs(folder)` on thumbs.npy |
| `qa_stack.py` | Q802 (true peak, its moment and the sounds there) and Q804 (the stack guard) from the cue sheet |
| `qa_sync.py` | Q902 (cue sync on the SFX stem), Q903 (the mux), Q906 (`qa.py calib`); `cue_offsets(ctx)` for the audio strip |
| `qa_speech.py` | Q806 (what the narration stem says against its script) and Q807 (what the file says against the stem), from a speech model in its own uv environment (faster-whisper base.en); `qa.py speech [narration.json]` runs Q806 alone, `python qa_speech.py fetch` gets the model (147.8 MB), `missing` says whether it is there. `atoms` and `compare` hold the word rules (digits, homophones, spellings) (`qa-gates.md`) |
| `cards.py` | The style cards as data: each card's `**Spec:**` line (family, length, size, fps, audio, kit). `python cards.py check` holds the SKILL.md router, its kit list and the card counts in README.md and SKILL.md against the cards; `router [--write]` rebuilds the router; `spec <card>` prints one. A build's copy finds the cards through the skill junction |
| `qa_registry.py` | The text recorder: Q204, Q205, Q206, Q208, Q209 (what draw(t) paints against what text_items(t) reports), in `qa.py check` and `run_all.py proof`; `--registry-procs N` |
| `qa_purity.py` | The purity gate Q1201 (`qa.py purity [--n 16] [--t T] [--grid S]`): on a FIX the worst frame, the pixels that differ and the frame that poisons it |
| `qa_lint.py` | Static checks of scenes.py and the modules it imports from its folder (`qa.py lint [scenes.py] [--all]`): Q1202 FIX, Q1203 to Q1206 NOTE, Q904 and Q905; pragmas `# zoetrope: state-ok`, `rng-ok`, `shadow-ok`, `text-ok`, `colour-ok`. `qa.py owner --t S` or `--traceback FILE` names the scene function(s) a finding belongs to |
| `qa_approve.py` | `approve`, `diff`, `verify` and the approval rows Q1301 to Q1304; `approved/` holds the approved build (approval.json, frames.hash, thumbs.npy, qa.json, mix_raw.hash, mix_raw.wav, src/) |
| `qa_audiostrip.py` | `qa.py audiostrip`: `review/audio.png` (spectrogram, cues, loudness, true peak on one axis) |
| `qa_selftest.py`, `qa_fixtures/` | `qa.py selftest [--quick] [--only CODE[,CODE]] [--keep]`: 85 cases in `qa_fixtures/` (text, registry, source, files, sound, speech, scans, approval; `fake.py` and `media.py` make the inputs) plus the template controls; each case says with `want(code, status, item, t, tol, metric, ...)` what its gate must report, and `EXPECTED_GAPS` in qa_selftest.py names any code no fixture can reach. Copy the engine with `cp -r <skill>/engine/. <folder>/` so `qa_fixtures/` comes along (`qa-gates.md`) |
| `contract.py` | What every module shares and nothing else defines: the frame clock (`frame_of` nearest frame, `snap`, `sample_of`, `frame_sample`, `stepped`, `on_grid`, `whole_frame_beat`), the QA row (`Row`, `row`, `not_checked`, `exit_code`, `line`, `summary`), the Q code table `CODES`, the files a build writes and their readers (below), the colour chain (`COLOR_VF`, `COLOR_FLAGS`, `DECODE_709`, `DECODE_LINEAR`), `AAC_ARGS` and `mux_cmd` (the one mux), `find_ffmpeg`, and `Ctx`, which decodes the file once for every gate module. It imports neither scenes nor engine, so anything can import it first |
| `kit_index.py` | `python kit_index.py [folder ...]`: every public function, class and namedtuple in the engine (gate internals left out) and the kits, with its signature, first docstring line and file:line, from the ast alone (534 helpers on 2026-10-29); `python kit_index.py show <name>` (or `g04:text`) prints one. Read it before writing a helper |
| `requirements.txt` | Pillow 13.0.0 and numpy 2.5.4, pinned with hashes (`requirements.in` is the input to `uv pip compile --generate-hashes --universal`) |

All audio modules run at 44.1 kHz; `audio.master` resamples the final mix to 48 kHz.

**Before a build**
- Everything runs in one working folder on this machine: proof sheets, frames, synthesized audio, local ffmpeg.
- Pins: the `cp -r <skill>/engine/. <working folder>/` copy brings `requirements.in` (`pillow==13.0.0`, `numpy==2.5.4`), `requirements.txt` (the same two with sha256 hashes) and `requirements-voice.in` (the optional speech and voice environments; nothing installs it). `--no-project` stops uv from looking for a project file, and the hashed pins mean a proof and its render in one folder run on the same Pillow and numpy. This engine folder has no `.python-version`, so uv uses the Python it resolves on the machine. `bash setup.sh` in the skill folder checks the machine and installs nothing system-wide (its first uv run may fetch the pinned wheels into uv's cache): it prints `ok` or `FIX <what> -> <how>` for uv, ffmpeg with libx264, ffprobe, Pillow and numpy, and the default bold font, then notes the font families, the speech model and the instruments, and exits 1 when something needs fixing.
- `run_all.py` finds ffmpeg on PATH, else in `/opt/homebrew/bin` or `/usr/local/bin`, and prints `NO_FFMPEG` when there is none (`troubleshooting.md`).
- Size: `run_all.py <stage> --size WxH --fps N --ss N` sets `E.W, E.H, E.FPS, E.SS` before scenes is imported, so a 9:16 build needs no edit; a scenes.py that sets its own size wins, and run_all says so. Every stage writes `build.json` (`{"w", "h", "fps", "ss"}`, the size the build really uses), which `qa.py check` (for SS), `purity`, `lint`, `owner`, `approve`, `diff` and `proof.py keys` read instead of guessing. Set the size by hand only in a runner of your own: `import engine as E; E.W, E.H, E.FPS, E.SS = 1920, 1080, 30, 1` before `import scenes`. Use `SS = 2` for thin lines and small text (4x the pixels, slower).

## scenes.py

Replace the palette, `LINES` and the draw functions per video. Keep `TIMELINE`, `draw(t)` and the purity rule. Lengthen a scene in `TIMELINE` and every later cut, window and scene cue moves with it.

- **Transitions.** A `Transition(kind, dur)` between two scenes makes a window where both are drawn. In straddle mode (the default) the cut stays where the durations put it, on the bar line, and the window spans it; with `mode="overlap"` the next scene starts `dur` early, as in Remotion (60 + 60 - 15 = 105 frames). `compile_schedule` raises on a transition under 2 frames (no frame of it would blend) or over half the shorter scene, a scene shorter than half a frame, and a scene cue at or past its scene's end (put that cue on the next scene at 0). Durations may be in beats (`bpm=`) or a function (`lambda: max(hold, measured)`); floats are read as the nearest fraction with a denominator up to 10**6, so `5 / 30` is exactly 5 frames.
- Draw a window with `scenes_at(t, SCHEDULE)` and a `transitions.py` function; another kind than a crossfade needs its own shares in `layout()`, or the registry drifts. Keep text out of the window (its scene's solo span), or Q203 fires; a window under 0.5 s then leaves a Q207 gap, so put the incoming text in another place (`qa-gates.md`, gate 2).
- **Voice piece:** each scene's length is its narrated line's slot (`voice.md`; `N["lines"][i]["slot"]["duration"]`), cues from `C.snap(voice.word_cue(N, word), FPS)`. scenes.py reads `narration.json` and never calls `voice.synthesize`: every render worker imports scenes.py.
- **Music piece:** durations in beats on the grid (`bpm=BPM`); hard cuts on bar lines (`beat-sync.md`).
- **Holds that never move:** `STATIC = [(t0, t1), ...]` (seconds, end exclusive like SCHEDULE) are drawn once when their sampled frames match (both ends, the middle, about one a second): a 10 s hold in a 20 s piece rendered in 8.7 s against 13.3 s, byte-identical. A change between the samples is not seen, so declare only frames that truly hold; a moving span prints a warning and is drawn in full. Q1102 does read STATIC (`qa_scan._holds` marks each span, with 2 frames of slack either side, as frozen by design).

### The purity rule in detail

`draw(t)` takes a time in seconds and returns a PIL image of exactly `W x H`; the template ends every draw with `finish(img)`, which scales a supersampled canvas down (Lanczos) and converts it to RGB. The render checks every frame's size and stops at the first wrong one (`render.checked`: `frame 12 (t 0.400 s) is 640x362; the build is 640x360`), because in a raw pipe one frame of another size shears every frame after it.

The same `t` must give the same pixels whatever was drawn before it, in whichever process, in whichever order. The render draws out of order in a pool of fresh processes, the purity gate and the text recorder draw single frames on their own, and `qa.py approve` and `run_all.py audio` draw key frames again and compare them with the render. In practice:

- Carry no state from one call to the next. A cache is fine when it holds only what a pure function would give anyway (a font, a background built once at import).
- Read no clock, no process id, no unseeded random source and no `hash()` of a string. For randomness use `rng(*keys)`: a numpy Generator seeded from the keys. Strings go through `zlib.crc32`, whole numbers from 0 to 2**32 - 1 are used as they are, and the key count leads the seed (numpy pads a seed with zeros, so `[5]` and `[5, 0]` would otherwise be one stream). A float key raises TypeError (`for a time pass frame_of(t, FPS), not t`), and an int outside the range raises ValueError. Seed each element from its own keys, for example `rng("dust", i, frame_of(t, FPS))`, never one stream advanced frame after frame. Sounds have their own seeding, `synth.rng_for(name, *args)`.
- Take every time from `TIMELINE`, compiled by `compile_schedule` into `SCHEDULE`, `DURATION`, `CUTS`, `WINDOWS` and `CUES`. A hand-written `SCHEDULE = {name: (start, end)}` with a `DURATION` still works; the engine then takes the cuts from every scene start after 0.

What enforces it, all in the proof stage (codes in `qa-gates.md`):

- Q1201 (FIX): frames at the ends, both sides of the cuts, cues, key times and an even spread are hashed in order in this process, in reverse order in a fresh `python -I` process, and through a spawn pool, and must match exactly. 24 frames on the template.
- The lint of `scenes.py` and the local modules it imports: Q1202 (FIX) for unseeded randomness, clock reads and hashes of strings; Q1203 to Q1206 (NOTE) for module state written inside a function, an engine helper defined again, text drawn outside the engine's text helpers and a colour literal outside the palette block; Q904 and Q905 (NOTE) for a time off the frame grid and a beat that is not a whole number of frames. A finding that is meant is silenced with a pragma comment on its line: `# zoetrope: rng-ok`, `state-ok`, `shadow-ok`, `text-ok` or `colour-ok`.

### The names a scenes.py declares

| Name | When | Read by |
|---|---|---|
| `draw(t)` | always | the render, the proof sheets, every gate that draws |
| `SCHEDULE`, `DURATION` | always | the frame count (`frame_of(DURATION, FPS)`), the proof sheets, the score, the gates |
| `CUTS`, `WINDOWS`, `CUES` | made by `compile_schedule`; `CUES` may be extended (the template adds one cue per cut) | the template score (one hit per cut, labelled from `CUES`), the key sheet, Q901, Q902 |
| `text_items(t)`, or `NO_TEXT` | one of the two | the text gates and the text recorder |
| `NO_CUES` | a piece with no shared sound and picture moment | Q902 |
| `BPM` | music pieces | the template score's tempo (120 when absent), Q901, Q905, the Gantt strip |
| `KEY_TIMES` | optional | the key sheet |
| `CUE_LAG` | optional, in frames | the picture side of Q902, the hard-cut scan |
| `STATIC` | optional | the render (see Held frames above) |
| `BUDGET_MB` | optional | the bitrate cap and Q1001 |
| `SILENT` | optional | the mux (no audio track), the audio gates |
| `ALLOW` | optional | the NOTE-level scans |
| `HOLD_PROFILE` | optional | Q401 |
| `CARD` | optional; the template sets None | a narrated card's build must carry `narration/` (Q806 is NOT CHECKED without it) |

### Writing scenes.py from the template

The template is 7.5 s at 120 BPM: three 2.5 s scenes (`hook`, `point`, `cta`) with hard cuts at 2.5 s and 5 s and a cue on each (`cut to point`, `cut to cta`). On 2026-11-12 it passed `run_all.py proof` (23 checks) and `run_all.py full` (50 checks, one DELIVERED line) at 640x360, 225 frames.

Replace for each video:

- the palette block (`INK`, `PAPER`, `ACCENT`, `WHITE`, `NIGHT`, `DAY`) with the style card's colours, used by name only;
- every placeholder in `LINES`, word for word from the storyboard;
- `TIMELINE` (scenes, lengths, transitions and cues), `BPM`, `CARD` and `KEY_TIMES`;
- the drawing in `bg`, `title` and `title_state`.

Keep:

- `from engine import *` at the top and the palette at module level;
- the line `SCHEDULE, DURATION, CUTS, WINDOWS, CUES = compile_schedule(TIMELINE)`; add `bpm=BPM` to give the lengths in beats;
- one layout function that both `draw` and `text_items` read (the template's `layout(t)`), so the registry cannot drift from the picture. It returns each scene on screen with its weight, one scene or the outgoing then the incoming one inside a transition window;
- `text_items(t)` returning one dict per text, with `s`, `box` (from `text_box` with the same arguments as the draw), `fg`, `alpha`, `px` and `bold`;
- `draw(t)` ending in `finish(...)`;
- a first scene fully in place on frame 0 and a last scene that never leaves: the template's `title_state` skips the entrance of a scene that starts at 0 and the exit of one that ends at `DURATION`.

### Scene, Transition and compile_schedule

`Scene(name, dur, cues=())`. `dur` is a number, or a function that returns one (`lambda: max(2.0, narration_s)`), in seconds, or in beats when `compile_schedule` is given `bpm`. `cues` is a list of `(t, label)` or `(t, label, kind)`, a list of dicts, or one dict `{label: t}`. Cue times count from the scene's first drawn frame; kind is `"both"` (the default), `"audio"` or `"picture"`.

`Transition(kind, dur, split=0.5)` is a window between the scenes on either side of it. `kind` is a name for your own draw code (the `transitions.py` names), `dur` is in seconds or beats, and `split` is the share of the window that lies before the cut: 0.5 centres it on the cut and 0 starts it there.

`compile_schedule(items, mode="straddle", bpm=None, fps=None)` returns `Timeline(schedule, duration, cuts, windows, cues)`; `fps` defaults to `engine.FPS`. In `"straddle"` mode the scenes run cut to cut, so `DURATION` is their sum, and a window spans its cut with both scenes drawn inside it. In `"overlap"` mode each scene after the first starts the transition's `dur` before the previous one ends, so `DURATION` loses every transition, and the cut sits `split` of the way into the overlap. A plain tuple such as `("intro", 2)` is read as a Scene. Results at 30 fps (run on 2026-11-12):

| Items | Mode | SCHEDULE (s) | DURATION | CUTS | WINDOWS |
|---|---|---|---|---|---|
| `Scene("a", 2)`, `Transition("crossfade", 0.5)`, `Scene("b", 2)` | straddle | a 0 to 2.267, b 1.767 to 4.0 | 4.0 | 2.0 | 1.767 to 2.267 |
| the same | overlap | a 0 to 2.0, b 1.5 to 3.5 | 3.5 | 1.767 | 1.5 to 2.0 |
| `Scene("a", 4)`, `Scene("b", 6)` with `bpm=120` | straddle | a 0 to 2.0, b 2.0 to 5.0 | 5.0 | 2.0 | none |
| `Scene("a", lambda: max(2.0, 1.234))`, `Scene("b", 5 / 30)` | straddle | a 0 to 2.0, b 2.0 to 2.167 | 2.167 | 2.0 | none |

How the numbers are made: each length becomes an exact fraction (`_exact`: ints and Fractions as they are, any other number as its nearest fraction with a denominator up to 10**6, so 0.1 reads as 1/10 and 5 / 30 as 1/6), is multiplied by the frames per unit (fps, or 60 x fps / bpm), and is summed exactly. Each instant is then rounded once to its nearest frame, halves up, as `frame_of` does. So `5 / 30` s is exactly 5 frames. A 0.5 s window centred on a cut at frame 60 spans frames 52.5 to 67.5, which round to 53 and 68; that is why the outgoing scene above is drawn to 2.267 s.

A cue at 0 lands on its scene's first drawn frame. For a scene entered through a window, that is the window's start, not the cut: scene b's cue at 0 behind the 0.5 s crossfade above landed at 1.767 s. A sound meant for the cut itself goes on the outgoing scene at the cut time with kind `"audio"`: `Scene("a", 2, cues=[(2.0, "cut", "audio")])` followed by the 0.5 s crossfade gave a cue at 2.0 s. With no window after it, the same cue is an error (the scene ends at 2.0), so the cue belongs to the next scene at 0. A cut inside a window has no hard picture change, so kind `"audio"` is the honest one.

Every error `compile_schedule` raises is a ValueError. The messages below are the real ones:

| Cause | Message |
|---|---|
| an unknown mode | `mode 'cut': use "straddle" or "overlap"` |
| a Transition first, or two in a row | `Transition(kind='crossfade', dur=0.2, split=0.5) must sit between two scenes` |
| no scene, or a Transition last | `a timeline needs a scene and must not end on a Transition` |
| a name used twice | `scene 'a' is declared twice` |
| a length of 0 or less | `scene 'a' lasts 0 s: it must be over 0` |
| a split outside 0 to 1 | `Transition(kind='x', dur=0.2, split=1.5): split must be 0 to 1` |
| a window under 2 frames | `'x' transition of 0.05 s (1.5 frames) between 'a' (1.000 s) and 'b' (1.000 s) is under 2 frames at 30 fps, so no frame of it is blended: make it at least 0.067 s, or use a hard cut` |
| a window over half the shorter scene | `'x' transition of 0.6 s (18.0 frames) between 'a' (1.000 s) and 'b' (3.000 s) is over half the shorter scene, 'a' (0.500 s): shorten it or lengthen 'a'` |
| a scene that rounds to no frame | `scene 'b' lasts 0.01 s (0.30 frames) and rounds to no frame at 30 fps: lengthen it to at least one frame or drop it` |
| a cue off its scene's frames | `cue 'end' at 1 s does not land on a frame of scene 'a' (0 to 0.966667 s); a cue at the scene's end belongs to the next scene at 0` |

### Drawing inside a transition window

`scenes_at(t, SCHEDULE)` returns `([(name, local_t, k), ...], mix)`. Outside a window that is one scene and a mix of 0. Inside one it is the outgoing scene, then the incoming one, and a mix that is 0 on the window's first frame and grows from there; at the cut of the first row above (t = 2.0) it read 0.467. `local_t` counts from each scene's first drawn frame, and `k` runs from 0 to 1 over the scene's drawn span. `scene_at` answers the outgoing scene inside a window. Both decide on whole frames, through `frame_of`.

The template's `layout(t)` turns that into the weights `[1 - mix, mix]`. `draw` blends the two pictures with `transitions.crossfade`, and `text_items` multiplies each text's alpha by its scene's weight. For another kind, call `transitions.MENU[kind](a, b, p)`, or a named one such as `transitions.wipe(a, b, ease_in_out_cubic(mix), direction="left")`. Every transition is pure: p = 0 returns a, p = 1 returns b, the inputs are never changed, and both frames must share one size and mode. Ease p yourself, and give `text_items` the same weights `draw` uses. `dip` carries `flash_risk = "check"`: run `qa.flash_window(draw, t0, t1, fps=FPS)` over its window before the render. The craft rules for transitions and springs are in `playbook.md`.

**Springs.** `spring(t, stiffness, damping, mass)` is Remotion's spring: damping at or over critical moves as critically damped, so `damping=200` is a fast ease with no bounce. `settle_time(...)` gives the seconds until it is at rest (Remotion's measureSpring, 0.005 held for 20 frames). Report a springing item at rest only from then. Damping under `2 * sqrt(stiffness * mass)` overshoots and settles. The spring is 0 for t <= 0 and raises ValueError for a damping of 0 or less; `settle_time` defaults `fps` to `engine.FPS` and raises for a spring not at rest within 10 minutes. At 30 fps the default spring peaked at 1.163 and `settle_time()` gave 0.933 s; `settle_time(100, 200, 1)` gave 0.767 s (2026-11-12).

## Stages: proof, full, audio

- `python run_all.py proof`: the proof gates (Q501 on frame 0, the registry gates, the text recorder, purity, lint), then `proof.png`, `proof_keys.png`, `proof_gantt.png` (`proof_strips.png` when an entry asks for one), `review_times.json` and `qa_proof.json`. It prints every row and ends `PROOF: PASS (23 checks, 0 FIX, 0 NOTE, 0 NOT CHECKED)` on the template; exit 1 on any FIX, 2 on any NOT CHECKED. Show `proof.png` and `proof_keys.png`, get approval, then render.
- `python run_all.py full [procs] [--budget-mb N] [--keep-frames [--redraw T0-T1]]`: deletes the old outputs first (out.mp4, video.mp4, frames.hash, thumbs.npy, the mixes, the cue sheet, every `*.rejected.mp4` and `*.unchecked.mp4`), renders `video.mp4`, then makes the audio (`audio.render_audio`), masters it, muxes with `contract.mux_cmd`, runs the true-peak loop, the frame scans on thumbs.npy and `qa.check`, and redraws the review sheets with the verdict's rows.
- `python run_all.py audio`: the same without drawing a frame, on the same `video.mp4` (10 s against 20 s for the template's full build, video.mp4 byte-identical). It refuses a `video.mp4` drawn at another size, fps or SS, or from another state of scenes.py: it redraws the first, middle and last frame of every scene (at most 12) and compares them with frames.hash. Give it the same flags as `full`.

How each run ends (the template, 2026-10-29):

```
master: ceiling -2.00 dBTP, mix.wav -14.0 LUFS at -2.00 dBTP (Q805 PASS) -> out.mp4 -14.0 LUFS at -1.90 dBTP
...
QA: PASS (50 checks, 0 FIX, 0 NOTE, 0 NOT CHECKED)
APPROVAL: none yet -> final review, then qa.py approve
DELIVERED C:/.../out.mp4 (0.4 MB, 7.50 s, -14.0 LUFS, -1.9 dBTP)
```

The `QA:` count was 49 on 2026-10-29 and is 50 since Q806 (the narration check, a PASS row with no narration) joined `qa.py check`; run alone, `qa.py check out.mp4 --scenes . --size WxH --fps 30 --bpm 120` counts 45 on the same file (it adds no Q805 row and no thumbs scans). Both counts were read on 2026-11-12 at 640x360.

### Stage reference

| Stage | Command | Needs | Ends with |
|---|---|---|---|
| proof | `python run_all.py proof --size 1920x1080` | no ffmpeg | a `PROOF:` line |
| full | `python run_all.py full --size 1920x1080` | ffmpeg with libx264 | an `APPROVAL:` line and one `DELIVERED` line, or a `REJECTED` or `UNCHECKED` line |
| audio | `python run_all.py audio --size 1920x1080` | `video.mp4` from `full`, with the same flags | the same as full |

In the commands, `python` stands for `uv run --no-project --with-requirements requirements.txt python`, run from the working folder. Every stage writes `build.json` (after its refusals) and `build_state.json` (`{"stage", "status", "verdict", "at"}`: `running` while it works, `done` with its verdict lines). Both ffmpeg stages look for ffmpeg on PATH, then in `/opt/homebrew/bin` and `/usr/local/bin`; a folder found that way is put on PATH, so the gates' own ffmpeg and ffprobe calls find it too. With none at all they print `NO_FFMPEG: no ffmpeg on this machine. Every rung of the encode ladder needs one: install an ffmpeg with libx264, then check it with setup.sh` and exit 1, with the folder left as it was. Before anything else, `run_all.py` asks `plate3d.check` about a 3D plate: a stale, unfinished or (for `full`) proof-quality plate prints `PLATE: <why>` lines and exits 1 (`plates.md`).

**proof.** It runs the gates that need no file: `qa.proof_rows` (Q501 on frame 0, the text gates on the registry and the text recorder), `qa_purity.run` (Q1201) and `qa_lint.run("scenes.py")`, and writes their rows to `qa_proof.json`. Then it draws `proof.png` (up to 12 stills: scene middles first, then window edges, then scene bounds; 9 on the template) and starts `review_times.json` afresh with this proof's moments, carrying over only the `changed` entries `qa.py diff` left. From it the stage draws `proof_keys.png` (more pages when the cells do not fit), `proof_strips.png` (only when an entry asks for a strip) and `proof_gantt.png`. It prints every row and the summary, and exits 0 when all pass, 1 on any FIX, and 2 on a NOT CHECKED with no FIX. A `draw(t)` that raises stops the stage with its traceback before any row is printed, since the text gates draw first and are not guarded (`troubleshooting.md`).

**full** options:

- `procs`: render processes; the default is a quarter of the logical CPUs, at most 8 (`render.default_procs`);
- `--budget-mb N` (or `BUDGET_MB` in `scenes.py`): a bitrate cap from a size budget (`run_all.caps`: 95 percent of the budget over the duration, less the audio; bufsize equal to maxrate under 30 s, else twice it; the formula is in `formats.md`). It prints `size budget 2 MB for 8 s: maxrate ... kb/s, bufsize ... kb/s (a cap, not a guarantee: Q1001 checks the file)`, and the budget reaches `qa.check` as `max_mb`, so the Q1001 row says where its cap came from. A budget too small for the audio stops the run (`a 0.1 MB budget leaves no video bitrate for ...`);
- `--keep-frames`: every frame is also kept as PNG in `frames/`;
- `--redraw T0-T1[,T0-T1]`: only with `--keep-frames`; it draws those passages again and reads the rest back from `frames/`. Without `--keep-frames` argparse stops with `--redraw needs --keep-frames (and frames/ from an earlier --keep-frames run)` (exit 2).

Once past the ffmpeg check, `full` deletes `mix_raw.wav`, `sfx.wav`, `cuesheet.json`, `cue_sounds.npz`, `mix.wav`, `OUT`, `video.mp4`, `video.mp4.log`, `frames.hash`, `thumbs.npy` and every `*.rejected.mp4` and `*.unchecked.mp4`, so a failed run never leaves an older file to be reviewed. `frames/` is left alone; `--keep-frames` without `--redraw` empties it. Then it renders `video.mp4` and delivers:

1. The sound: with `SILENT` declared, the picture is muxed with no audio; otherwise the score (`score.py`'s `render_audio` when the folder has one, else `audio.render_audio`), then the master and mux loop (see Audio below).
2. Q1101 to Q1104 on `thumbs.npy`, every drawn frame before the encode (`qa_scan.scan_thumbs`).
3. `qa.check` on `OUT` with the build folder as `--scenes`: every gate on the file.
4. The approval rows (Q1301 to Q1304) are set apart. They describe the review state, not the file, so they never reject it.
5. Every other row is printed, then the `QA:` summary. Any FIX or NOT CHECKED row moves the file to `<name>.rejected.mp4`.
6. The moment of every row that did not pass goes into `review_times.json`, and `proof_keys.png`, `proof_strips.png` and `proof_gantt.png` are drawn again with those rows.
7. A clean run prints the `APPROVAL:` line and one `DELIVERED` line.

**audio** makes the sound again, then masters, muxes and runs every gate on the `video.mp4` already there, without drawing the film. It refuses, with exit code 1:

- when there is no `video.mp4`: `` no video.mp4 here: run `run_all.py full` first `` (before any clean-up);
- when the picture no longer matches the flags or the source (`picture_is_current`). Either `frames.hash` records another size, rate, SS or frame count (`video.mp4 was rendered at 640x360, 30 fps, SS 1, 225 frames; this run is 1920x1080, 30 fps, SS 1, 225 frames: pass the same --size, --fps and --ss, or run run_all.py full`), or up to 12 frames (the first, middle and last of every `SCHEDULE` span) drawn again do not hash as `frames.hash` says (`video.mp4 predates scenes.py: frame <i> (<t> s) and <n> more of <m> checked differ from frames.hash (or its size, fps, SS or length): run run_all.py full`).

Every refusal (no ffmpeg, no `video.mp4`, a stale picture, and for `full` a size budget that leaves no video bitrate) comes before the stage's clean-up and before `build.json` is written, so a refused run leaves the last build as it was (2.5.0). Before 2.5.0 the stale-picture refusal came after the clean-up: an audio run at 1920x1080 on a 640x360 build deleted `out.mp4` and the mixes and rewrote `build.json` while refusing.

### The lines a stage prints

| Line | When | Form (real lines from 2026-11-12 unless marked) |
|---|---|---|
| `PROOF:` | end of proof | `PROOF: PASS (23 checks, 0 FIX, 0 NOTE, 0 NOT CHECKED)`; otherwise `PROOF: FIX (n) (...)` or `PROOF: NOT CHECKED (n) (...)` (`contract.summary`) |
| `wrote video.mp4` | full, after the picture | `wrote video.mp4 (225 frames, 640x360 at 30 fps, SS 1, 0.1 MB) in 1.9 s` |
| `wrote mix_raw.wav, ...` | the sound step | `wrote mix_raw.wav, sfx.wav, cuesheet.json, cue_sounds.npz in 0.1 s` |
| `master:` | the first master | `master: ceiling -2.00 dBTP, mix.wav -14.0 LUFS at -2.00 dBTP (Q805 PASS) -> out.mp4 -14.0 LUFS at -1.90 dBTP` |
| `re-master k of 3:` | out.mp4's true peak over -1.3 dBTP | the same shape with a lower ceiling (from the code; not seen on the template). The next ceiling is `min(ceiling, the mix's own peak) - (excess + 0.2 dB margin) / slope`, with slope the file's measured peak movement per dB of ceiling (1 at first, kept between 0.25 and 1). It may be followed by `kept the cleanest master: ...` or `kept the least limited master: ...`, by a `note:` when the peak ends inside -1 dBTP but within 0.3 dB of it, by `true peak still over -1 dBTP after N re-masters: lower the hits Q802 names`, or by `the file's peak did not follow the ceiling (...): no lower ceiling will help` |
| `QA:` | after every gate | `QA: PASS (50 checks, 0 FIX, 0 NOTE, 0 NOT CHECKED)`; with a planted fault, `QA: FIX (1) (50 checks, 1 FIX, 0 NOTE, 0 NOT CHECKED)` (form from `contract.summary`) |
| `APPROVAL:` | a clean run | `APPROVAL: none yet -> final review, then qa.py approve`; with an approval, `APPROVAL: current -> ...` or `APPROVAL: stale: <code> <item> -> re-review the changed scenes, then qa.py approve`. A stale approval does not stop delivery; each approval row is also printed as `approval <state>: <code> <message>` |
| `DELIVERED` | a clean run, last line | `DELIVERED <working folder>/out.mp4 (0.3 MB, 7.50 s, -14.0 LUFS, -1.9 dBTP)`, with the absolute path; a silent piece shows `silent` in place of the loudness. Exit 0 |
| `REJECTED` | any FIX or NOT CHECKED row | `REJECTED out.rejected.mp4: Q502 FIX` (every failing code and status). No APPROVAL or DELIVERED line follows. Exit 1 on a FIX, 2 when every bad row is NOT CHECKED |
| `UNCHECKED` | an error after the mux and before the verdict | `UNCHECKED out.unchecked.mp4: the run broke before the QA verdict (the error follows)`, then the traceback. An error before the mux (in the render, the score or the master) leaves no file, so only the traceback is printed |

Each row prints as `STATUS CODE message`, then `[worst T s]` when a row that did not pass names a moment, `[n checked]` when it counted items, and `-> fix` when it failed (`contract.line`, ASCII only).

- **DELIVERED** is printed once, last, only after a clean QA pass: `DELIVERED <absolute path> (<MB> MB, <s> s, <LUFS> LUFS, <dBTP> dBTP)`, or `(..., silent)` for a SILENT piece. The report quotes it as printed (`delivery-report.md`).
- **APPROVAL** sits just above it: `none yet -> final review, then qa.py approve`; `current -> nothing to do: the approval covers this build` (or the NOTE's own next step, such as re-approving after an audio-only change); `stale: Q1301 point -> re-review the changed scenes, then qa.py approve`. The approval rows (Q1301 to Q1304) are a review state: printed as `approval <current|note|stale|unknown>: ...`, kept out of the summary, and they never reject the file.
- **REJECTED**: any other FIX or NOT CHECKED row renames the file `<name>.rejected.mp4` and prints `REJECTED out.rejected.mp4: Q502 FIX` (every failing code and status). There is no DELIVERED line, and the file is never delivered.
- **UNCHECKED**: a run that breaks before its verdict (a crash in any step, an interrupt) moves the file to `<name>.unchecked.mp4`, prints `UNCHECKED ...: the run broke before the QA verdict` and lets the error stand. A crash is not a verdict.
- Every master prints one line: `master: ceiling ...` and, when the decoded mp4 reads over -1.3 dBTP, `re-master k of 3: ...` lines (gate 8 in `qa-gates.md`).

### The render

`render.render_to_ffmpeg` (called by `run_all.py full`) keeps frames off the disk: the pool (cores / 4 processes, at most 8; or `procs`) draws each frame into its own slot of a shared-memory ring (2 slots a process) and returns only the frame's digest and grey thumb, and the parent writes the frames to ffmpeg's stdin in order:

```
ffmpeg -y -v error -f rawvideo -pixel_format rgb24 -video_size WxH -framerate FPS -i - -an -c:v libx264 -preset medium -crf 18 -vf <contract.COLOR_VF> <contract.COLOR_FLAGS> -pix_fmt yuv420p [-maxrate Mk -bufsize Bk] video.mp4
```

- **Why a ring.** A raw 1080p frame is 6.2 MB. Sent back through a process pipe while five builds of 5 processes shared the machine, 7 of 45 renders died with WinError 1450 (insufficient system resources); with the ring 0 of 40 did, and 0 of 6 at three builds of 8 processes (2 of 6 before), with byte-identical output and the same speed alone (2026-10-29).
- stdin is written in 256 KiB slices; a slice Windows refuses while ffmpeg runs is retried with growing sleeps (40 tries, about 41 s), and only a dead ffmpeg is blamed, with its own exit code and log. A frame whose result the system refused (WinError 1450) or that hit a memory squeeze is drawn again, up to 6 draws in all: `draw(t)` is pure. Workers are spawned on every platform (a forked one kept ffmpeg's stdin open and hung its end). It runs on Python 3.13 and 3.14.
- ffmpeg's stderr goes to a file (an unread pipe can hang ffmpeg on Windows). A frame of the wrong size fails the render, naming the frame (one frame 2 px too wide sheared every frame after it), and so does any error ffmpeg logs on a clean exit. Any failure kills ffmpeg and deletes the partial `video.mp4`.
- Colour: `COLOR_VF` converts to BT.709 limited range and `COLOR_FLAGS` tags it; ffprobe reads bt709 / bt709 / bt709 / tv on video.mp4 and on the muxed file. Decodes read the file as a player does (`DECODE_709`, which rounds: without `accurate_rnd` a dark end card decoded 1 to 2 levels low and flipped the template's Q502 to FIX). Q707 and Q708 check the chain.
- `frames.hash` (JSON: w, h, fps, ss, n, algo, one blake2b-8 digest per drawn frame) and `thumbs.npy` (uint8, one 192x108 grey copy per drawn frame) are written after a good encode. They are what `qa.py approve` and `diff`, the frame scans before the encode and Q1105 read; the gates on the final file still decode the file.

**The one-passage trade-off.** `video.mp4` cannot be patched in place, so a visual fix to one passage draws every frame again (14 to 150 s of frames for a 60 s film on this machine), unless the build kept its frames: `run_all.py full --keep-frames` keeps every frame as PNG in `frames/` (19 MB for the 7.5 s template; the 2026-10-28 batch wrote about 1.3 GB per 60 s video), then `run_all.py full --keep-frames --redraw 12-14.5` draws only that passage, reads the rest back and encodes everything again (its frames.hash equals a full redraw's). It trusts `frames/` outside the passage. An audio-only fix (an SFX, a gain, a re-master) is `run_all.py audio`: no frame is drawn.

**The argv.** Print the two ffmpeg lines from the engine's own builders (here at 640x360; values read 2026-11-12):

```
python -c "import render, contract as C; print(*render.encode_cmd('ffmpeg', 'video.mp4', 640, 360, 30)); print(*C.mux_cmd('ffmpeg', 'video.mp4', 'mix.wav', 'out.mp4'))"
```

```
ffmpeg -y -v error -f rawvideo -pixel_format rgb24 -video_size 640x360 -framerate 30 -i - -an -c:v libx264 -preset medium -crf 18 -vf scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv -pix_fmt yuv420p video.mp4
ffmpeg -y -v error -i video.mp4 -i mix.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 320k -shortest -movflags +faststart out.mp4
```

With a size budget, `-maxrate` and `-bufsize` (kb/s) are added; x264 ignores a maxrate given without a bufsize. The colour chain:

- `contract.COLOR_VF` converts the RGB frames with the BT.709 matrix to limited range, makes them yuv420p and stamps the stream with BT.709 and tv range;
- `contract.COLOR_FLAGS` writes the same four tags into the container;
- `contract.DECODE_709` is put in front of every RGB decode a gate makes (BT.709, limited range, accurate rounding and full chroma interpolation), so the gates see the frames a player shows;
- `contract.DECODE_LINEAR` decodes to linear light for the flash gate.

Q707 checks the four tags and Q708 encodes five saturated swatches through `COLOR_VF` and reads them back through `DECODE_709` against a limit of 8 levels.

**frames.hash and thumbs.npy** are made from the same frames that go to the encoder. `frames.hash` is JSON with `w`, `h`, `fps`, `ss`, `n`, `algo` (`blake2b-8`) and `hash`: one 8-byte blake2b of each frame's mode, size and raw bytes. `thumbs.npy` is a uint8 array `(n, 108, 192)`, each frame in PIL grey, box-filtered to 192 x 108 whatever its aspect (a 9:16 build gives the same shape). For the 225 template frames at 640x360 they were 4,581 and 4,665,728 bytes. Q1105 compares the decoded file with `thumbs.npy`. The audio stage, `render.stale` and `qa.py approve` draw frames again and compare them with `frames.hash`. `qa.py approve` copies both files into `approved/`, and `qa.py diff` reads them against that copy.

**--keep-frames and --redraw.** `--keep-frames` saves each frame as `frames/f00000.png`, `f00001.png` and on (PNG compression level 1) while it renders, and turns STATIC off (`note: STATIC is not used with keep_frames: every frame is drawn or read`). `--redraw T0-T1` then draws only the frames from `frame_of(T0)` up to `frame_of(T1)` and reads the rest back. It stops when a PNG it needs is missing: `frames/ lacks N of the frames to reuse (first ...): run once with keep_frames and no redraw`. The frames it reads back are checked for size only, not against `draw(t)`. A PNG left from an older `scenes.py` goes into the film unnoticed until `qa.py approve` or `run_all.py audio` draws its key frames again.

**Size, rate and supersampling in detail.** `run_all.py` reads `--size`, `--fps` and `--ss` at the very top of the file (`size_flags`, which ignores every other argument) and only then imports `scenes`. The order matters because `scenes.py` reads `W`, `H`, `FPS` and `SS` once, when it is imported (`from engine import *` copies them), and lays everything out from them. It matters again in the render: the pool starts fresh spawned processes, each one runs the top of `run_all.py` again with the same arguments, and `render._start` sets the size before it imports `scenes` too. That is why the stage code sits under `if __name__ == "__main__":`, and why any script of your own that starts a pool needs the same guard. With `--ss 2` each frame is drawn at twice the width and height and `finish()` brings it down. A `scenes.py` can fix its own size: assign `engine.W` and `engine.H` (or `FPS`, `SS`) after `import engine` and before `from engine import *`; it then wins over the flags, and the stage says so: `note: scenes.py sets 640x360 at 30 fps, SS 1 itself, which wins over --size, --fps and --ss`. After `scenes` is imported, every stage writes `build.json` with the size the build really uses; it is written there and not at the top of the file because every render worker runs the top again. Pass the same flags to every stage of one build: the audio stage refuses a picture rendered at another size. Sizes per aspect, safe areas and frame rates are in `formats.md`.

### Files a build writes

All in the working folder; the names are constants in `contract.py`.

| File | Written by | What |
|---|---|---|
| `video.mp4`, `frames.hash`, `thumbs.npy` | `full` | The silent picture encode, one digest and one grey thumb per drawn frame |
| `mix_raw.wav`, `sfx.wav` | `audio.render_audio` | The pre-master mix and the SFX bus alone, same scale and rate (44.1 kHz, 16-bit) |
| `cuesheet.json`, `cue_sounds.npz` | `audio.render_audio` (`synth.recording`) | Every placed sound (label, sound, t, align, landmark_s, start_s, gain, peak_dbfs, heavy, bus, trim_s, audible_s, landmark_tol) and its own buffer |
| `mix.wav` | `audio.master` | The mastered mix, 16-bit stereo 48 kHz |
| `out.mp4` (or the slug name in `OUT`) | the mux | The deliverable; `<name>.rejected.mp4` or `<name>.unchecked.mp4` when it is not one |
| `build.json` | every stage | `{"w", "h", "fps", "ss"}` for the standalone CLIs |
| `build_state.json` | every stage | `{"stage", "status", "verdict", "at"}`: the stage running, or done with its verdict lines, for a builder that resumes a stopped build |
| `review_times.json`, `qa_proof.json`, `qa.json` | proof, full, `qa.py check --json` | Moments to review, and the rows (`qa-gates.md`) |
| `proof*.png`, `review/` | proof.py, `qa.py look`, `diff`, `audiostrip` | The sheets, look copies, triptychs and `review/audio.png` |
| `approved/` | `qa.py approve` | The approved build |

Who finds which file by which name (`contract.py` constant, or the module that owns the name):

| File | Name | Read by |
|---|---|---|
| `build.json` | `BUILD` | `qa.py check` (SS), purity, lint, owner, approve, diff, `proof.py keys` |
| `build_state.json` | `BUILD_STATE` | a builder resuming a stopped build |
| `qa_proof.json` | `QA_PROOF` | `proof.py keys` (the panel of rows with no moment) |
| `proof.png` | none (`run_all.proof_stage`) | the reviewer |
| `proof_keys.png`, `proof_keys_2.png`, ... | none (`proof.key_sheet`) | the reviewer |
| `proof_strips.png` | none (`proof.STRIPS`); written when an entry asks for a strip, and a stale one is deleted | the reviewer |
| `proof_gantt.png` | `GANTT` | the reviewer |
| `review_times.json` | `REVIEW_TIMES` | the key sheets, `review/audio.png`; proof starts it, full, audio, `qa.py check --json` with `--scenes`, `qa.py diff` and the scans add to it |
| `video.mp4` | `VIDEO` | the mux, the audio stage |
| `video.mp4.log` | none (`f"{out}.log"`) | you, after a failed encode; deleted after a good one |
| `frames.hash` | `FRAMES_HASH` | audio stage, `render.stale`, approve, diff, lint (size), `proof.py keys` (size) |
| `thumbs.npy` | `THUMBS` | Q1101 to Q1104 before the encode, Q1105, approve, diff |
| `frames/` | none (`render.FRAMES`) | `--redraw`, rung b |
| `mix_raw.wav` | `MIX_RAW` | the master, Q802, Q903, approve (audio hash) |
| `sfx.wav` | `SFX` | Q902 (each cue's sound is found here), Q802 |
| `cuesheet.json`, `cue_sounds.npz` | `CUESHEET`, `CUE_SOUNDS` | Q802, Q804, Q902 |
| `mix.wav` | `MIX` | the mux, Q903 |
| `out.mp4` | none (`run_all.OUT`; rename it per video) | `qa.py check`, the reviewer, delivery |
| `<name>.rejected.mp4`, `<name>.unchecked.mp4` | none (`run_all.set_aside`) | nobody: never delivered; the next full or audio deletes them |
| `qa.json` | `QA_JSON` | `qa.py approve` (the baseline), `proof.py keys` |
| `approved/`, `approved/approval.json` | `APPROVED`, `APPROVAL` | `qa.py check` (Q1301 to Q1304), `diff`, `verify` |
| `review/audio.png` | `AUDIO_PNG` | the reviewer |
| `review/look.jpg` and its stills | none (`qa.look`) | the reviewer |

## Audio

`run_all.py full` and `audio` call `audio.render_audio(scenes)` (the template score: DURATION, BPM, and the cuts from `CUTS` or every SCHEDULE start; each cut hit carries its CUES label) and then `audio.master(C.MIX_RAW, C.MIX)`. Cuts get a whoosh whose apex leads the cut by 80 ms and a hit on it; a kick within 3 frames of a cut is left out; music ducks about 8 dB under the voice. For a scored piece build the bed with `synth.py` (`music.md`) inside `with synth.recording() as sheet:` and write the sheet and the stems the way `render_audio` does, and put it in the working folder as `score.py` with `render_audio(scenes, folder=".", fps=None)`: `run_all.py` calls that in place of the template's when the file defines it (2.4.0; before that the call in `run_all.deliver` was edited by hand). Q902 and Q804 measure from that sheet. Voice comes from `voice.synthesize` (`voice.md`): mix `voice.dec("narration/narration.wav")` with `voice.duck_mix`.

### Sound in a build, in detail

In `full` and `audio`, `run_all.deliver` calls the score (`run_all.scorer()`: `score.py`'s `render_audio` when the folder has one, else `audio.render_audio`) as `render_audio(scenes, fps=E.FPS)`. That writes `mix_raw.wav` (music plus effects), `sfx.wav` (the effects bus alone, at the same scale) and the cue sheet (`cuesheet.json` with `cue_sounds.npz`). Then `master_and_mux` runs `audio.master(mix_raw.wav, mix.wav, TP=ceiling)` and the mux, and measures the true peak of the decoded `out.mp4` with `qa.loud`. While that peak is over -1.3 dBTP (`TP_MAX` -1.0 less `TP_TOL` 0.3), it masters again at a lower ceiling, at most 3 times (`RETRIES`, `MARGIN` 0.2 dB). It keeps the try with the lowest peak among those that are Q805 clean and inside -1 dBTP, or among all tries when none is, and masters and muxes that one again if it was not the last.

The template score (`audio.bed`): a kick on beats 1 and 3, a tick on every off-beat, and one sine `tone` on every beat, its pitch changing each bar (220, 261.63, 196, 246.94 Hz), all on the music bus. On the effects bus, at each cut, a whoosh whose placement leads the cut by `WHOOSH_LEAD` (0.08 s) and a hit whose onset is on the cut's frame, labelled with the cue at that time. A kick within 3 frames of a cut is left out, so two heavy sounds never stack. The cuts come from `scenes.CUTS`, or from every scene start after 0. `voice_spans=[(a, b)]` ducks the music bus 8 dB in those spans.

| Where | Sample rate |
|---|---|
| `audio.SR`, `synth.SR`, `voice.SR`: the buses, `mix_raw.wav`, `sfx.wav`, `narration.wav` | 44,100 Hz |
| `audio.SR_MASTER`: the master resamples to it, limits there and writes `mix.wav` (16-bit stereo) | 48,000 Hz |
| the gates' decodes of the file | 48,000 Hz (true peak, and the check that confirms each cue on the file), 8,000 Hz (silence, and the onset detector used when there is no cue sheet); with a cue sheet, Q902 searches the 44.1 kHz stems |

The master (`audio.master`) applies one static gain to -14 LUFS, then the true-peak limiter: 4x oversampled through Kaiser-windowed sinc filters (`OS`, `TAPS` 32 a phase), 3 ms lookahead and 100 ms release, with no delay added. It measures again with ffmpeg's ebur128 and nudges the gain (by the measured slope, 1 to 3 dB per LU), up to 6 passes, until it is within 0.05 LU of the target and at or under the ceiling. The first ceiling is `audio.CEILING`, -2.0 dBTP, which leaves room for the peak the AAC encode adds: on the template the encode raised the peak from -2.00 to -1.90 dBTP (2026-11-12). Q805 fails a master that missed by more than 0.1 LU or 0.05 dB, or whose limiter took more than 0.5 LU off the programme (`LINEAR_COST`) or more than 6 dB at any moment (`LINEAR_DEPTH`). On the template at 640x360 (2026-11-12): gain +0.52 dB in 2 passes, 0.16 LU taken, at most 1.1 dB.

### Your own score

The sync and stack gates measure what the cue sheet and `sfx.wav` say, so a score of your own must write the same four files the same way. Save it as `score.py` in the working folder with a top-level `render_audio(scenes, folder=".", fps=None)`: `run_all.py` parses the file (never runs it to find out) and uses that function in place of the template's, with no edit to `run_all.py`. Place every sound with `synth.place`, `put` or `put_peak` (or `audio.place`) inside `with synth.recording() as sheet:`. Build both buses at `synth.SR`, write them with `audio.write_wav` at one shared scale, and let `sheet.write(folder, scale)` fold that scale into every row's gain. Give each cue's sound its `CUES` label. A frame cue (`frame=`, `fps=`) puts the sound's landmark on the frame's first sample. This example was run in a scratch copy of the engine:

```python
# score.py : this video's own score, in place of audio.render_audio
from pathlib import Path

import audio
import contract as C
import numpy as np
import synth as S


def render_audio(scenes, folder=".", fps=None):
    """A pad on every bar, a hat on every off-beat, a clap on every cue that has
    sound. Writes the same four files as audio.render_audio and returns their paths."""
    fps = fps or scenes.FPS
    n = C.sample_of(scenes.DURATION, S.SR)
    music, sfx = np.zeros(n), np.zeros(n)
    beat = 60 / scenes.BPM
    chord = [57, 60, 64]
    # every place() inside this block becomes a row of the cue sheet
    with S.recording() as sheet:
        for bar in range(round(scenes.DURATION / (4 * beat))):
            pad = S.pad(chord, 4 * beat)
            S.place(music, pad, bar * 4 * beat, 0.6, sound="pad", stem="music")
        for i in range(round(scenes.DURATION / beat)):
            at = (i + 0.5) * beat
            S.place(music, S.hat(), at, 0.3, sound="hat", stem="music")
        for c in C.cues(scenes):
            if c["kind"] == "picture":
                continue
            # a frame cue: the clap's onset lands on the cue frame's first sample
            f = C.frame_of(c["t"], fps)
            S.place(
                sfx, S.clap(), frame=f, fps=fps, g=0.8, sound="clap", label=c["label"]
            )
    # one scale for both files, so sfx.wav lines up with mix_raw.wav sample for sample
    scale = 0.85 / max(np.abs(music + sfx).max(), np.abs(sfx).max(), 1e-9)
    out = {k: str(Path(folder, getattr(C, k.upper()))) for k in ("mix_raw", "sfx")}
    audio.write_wav(out["mix_raw"], music + sfx, scale=scale)
    audio.write_wav(out["sfx"], sfx, scale=scale)
    out["cuesheet"], out["cue_sounds"] = sheet.write(folder, scale)
    return out
```

With the template's scenes at 640x360 (7.5 s, 225 frames), `python run_all.py full --size 640x360` then gave `QA: PASS (50 checks, 0 FIX, 0 NOTE, 0 NOT CHECKED)` and a DELIVERED line (-14.0 LUFS, -2.0 dBTP): Q902 found both claps on their cues (worst +0.0 ms), Q804 counted 2 placed sounds and set 19 music-bus sounds aside (2026-11-12). Recorded instruments from `sampler.py` go in the same way, through `synth.place` (`instruments.md`).

### Narration in the mix

The template score takes no voice, so a voiced piece needs a score of its own that adds `narration/narration.wav` to the mix. The engine has three pieces for it:

- `voice.dec(path)` decodes it to float32 mono at 44.1 kHz.
- `audio.write_wav(path, mono, voice=v, scale=...)` adds the voice into the mix it writes.
- `voice.duck_mix(bed, voice, depth_db=8)` sets the bed to about -18 dBFS RMS, pulls it down 8 dB while the voice speaks (a -38 dB gate on 10 ms windows, a 40 ms attack and a 300 ms release) and lays the voice over it at a peak of 0.89 times 1.26 (plus 2 dB).

Keep the voice out of `sfx.wav`: Q902 finds each cue's own sound there by cross-correlation. Levels and practice are in `mixing.md` and `voice.md`.

## Encode ladder (always say which rung was used and why)

Master loudness to -14 LUFS integrated, true peak at or below -1 dBTP: `audio.master` does it (gate 8). Verify afterwards with `qa.loud("out.mp4")`, or `ffmpeg -i out.mp4 -af ebur128=peak=true -f null -` and read I and Peak in the Summary.

**Rung a, ffmpeg with libx264 (best, plays everywhere):** `run_all.py full` pipes the frames into the H.264 encode above, then muxes with `contract.mux_cmd`:
```
ffmpeg -y -v error -i video.mp4 -i mix.wav -map 0:v -map 1:a -c:v copy -c:a aac -b:a 320k -shortest -movflags +faststart out.mp4
```
A silent piece (`SILENT = True`) muxes the picture alone. The true-peak loop measures the decoded mp4 and re-masters (at most 3 times) until it reads -1.3 dBTP or under.

**Rung b, ffmpeg without libx264.** The pipe needs libx264, so write PNG frames and make the audio by hand from the working folder (run_all's top reads the size flags; checked 2026-10-29 at 640x360: 225 frames, master -2.0 dBTP):
```
python -c "import run_all, render; render.render_parallel('frames')" --size WxH
python -c "import run_all, audio, contract as C, scenes; audio.render_audio(scenes); audio.master(C.MIX_RAW, C.MIX)" --size WxH
```
Then encode with the colour chain:
```
VF=$(python -c "import contract as C; print(C.COLOR_VF)")
ffmpeg -y -framerate 30 -i frames/f%05d.png -i mix.wav -vf "$VF" -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv -c:v libaom-av1 -crf 30 -b:v 0 -cpu-used 6 -pix_fmt yuv420p -c:a aac -b:a 320k -shortest -movflags +faststart out_av1.mp4
ffmpeg -y -framerate 30 -i frames/f%05d.png -i mix.wav -vf "$VF" -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv -c:v libvpx-vp9 -crf 32 -b:v 0 -pix_fmt yuv420p -c:a libopus -b:a 160k -shortest out.webm
```
Both read back bt709 / tv on ffmpeg 9.0.2 (2026-10-29). Use AV1 MP4 if the encoder exists (plays in Chrome and Slack web; may not play in older QuickTime), else VP9 WebM; check `ffmpeg -encoders | grep -E "av1|vp9"` first. There is no DELIVERED line on this rung: run `qa.py check` by hand. It ends `QA: NOT CHECKED (3)` by design, because Q705, Q707 and Q708 are for the H.264 deliverable; say so in the report.

**Back on rung a: checking by hand.** After muxing again by hand (the mux line above returns exit 0 and a file with h264 and aac), run `python qa.py check out.mp4 --scenes . --size WxH --fps N --bpm 120 --json qa.json`. On the template at 640x360 it ended `QA: PASS (45 checks, 0 FIX, 0 NOTE, 0 NOT CHECKED)` (2026-11-12).

**Rung b in full: frames, their records and the sound.** The two `python -c` lines above leave `frames.hash` and `thumbs.npy` as an earlier render left them. Save this as `ladder_b.py` in the working folder and run it with the build's flags instead: it draws every frame as PNG in parallel (`render.render_parallel`), writes `frames.hash` and `thumbs.npy` from those PNGs exactly as the render would, then makes the sound with the folder's own score (`run_all.scorer()`) and masters it. Run on 2026-11-12:

```python
# ladder_b.py : rung b of the encode ladder, the steps before ffmpeg. Run it like run_all.py, with the same
# --size, --fps and --ss: PNG frames in frames/, frames.hash and thumbs.npy rebuilt from them, then the mastered mix.
import numpy as np
from PIL import Image

import run_all  # reads --size, --fps and --ss, then imports scenes at that size
import audio
import contract as C
import render

if __name__ == "__main__":
    E, scenes = run_all.E, run_all.scenes
    C.write_build(E.W, E.H, E.FPS, E.SS)
    n = render.render_parallel()  # every frame as frames/f00000.png, f00001.png, ...
    digests, thumbs = [], []
    for i in range(n):
        with Image.open(render.png_path(i)) as im:
            frame = im.convert("RGB")
        digests.append(C.frame_digest(frame))
        thumbs.append(C.thumb(frame))
    C.write_frame_manifest(digests, E.W, E.H, E.FPS, ss=E.SS)
    np.save(C.THUMBS, np.stack(thumbs))
    run_all.scorer()(scenes, fps=E.FPS)
    m = audio.master(C.MIX_RAW, C.MIX)
    print(
        f"{n} frames in {render.FRAMES}/; {C.MIX} {m['I']:.1f} LUFS at {m['tp']:.2f} dBTP"
    )
    for r in m["rows"]:
        print(C.line(r))
```

```
python ladder_b.py --size 640x360
```

It printed `225 frames in frames/; mix.wav -14.0 LUFS at -2.00 dBTP` and a PASS Q805 row. On a machine where the process pool cannot start, `render.render_frames()` writes the same PNGs in one process, more slowly (not run here).

**What to do with an earlier render's frames.hash and thumbs.npy.** They describe the frames that render drew. Q1105 compares the file under check with `thumbs.npy`: it fails when they differ, reads NOT CHECKED when only `frames.hash` is there, and gives no row when neither is. `qa.py approve` needs both, and the audio stage trusts `frames.hash`. So do not check a rung b file against a pair from another state of `scenes.py`; let `ladder_b.py` rewrite both from the PNGs you are about to encode. Deleting both also clears Q1105, but leaves nothing to approve against.

**Rung b, encode and check.** The lines in the colour-chain form (`contract.COLOR_VF` and `COLOR_FLAGS`, spelled out), in order of preference: SVT-AV1, then libaom AV1, then VP9 in WebM. Set `-framerate` to the build's fps. All three files read back yuv420p, tagged BT.709 and tv range; the MP4 lines use the engine's AAC settings (`contract.AAC_ARGS`), WebM carries Opus. SVT-AV1 prints its own banner of `Svt[info]` lines even under `-v error`; that is not an error.

```
ffmpeg -y -v error -framerate 30 -i frames/f%05d.png -i mix.wav -map 0:v -map 1:a -vf "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv" -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv -c:v libsvtav1 -preset 8 -crf 35 -c:a aac -b:a 320k -shortest -movflags +faststart out_av1.mp4
ffmpeg -y -v error -framerate 30 -i frames/f%05d.png -i mix.wav -map 0:v -map 1:a -vf "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv" -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv -c:v libaom-av1 -cpu-used 6 -row-mt 1 -crf 30 -b:v 0 -c:a aac -b:a 320k -shortest -movflags +faststart out_av1.mp4
ffmpeg -y -v error -framerate 30 -i frames/f%05d.png -i mix.wav -map 0:v -map 1:a -vf "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p,setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv" -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv -c:v libvpx-vp9 -row-mt 1 -crf 32 -b:v 0 -c:a libopus -b:a 160k -shortest out.webm
```

The SVT-AV1 and VP9 lines were run on 2026-11-12 at 640x360 on the 7.5 s template: `out_av1.mp4` 271,556 bytes, `out.webm` 194,418 bytes (the libaom line is the engine's earlier-tested form, not re-run). See what your ffmpeg has with `ffmpeg -hide_banner -encoders`; this machine listed libx264, libsvtav1, libaom-av1, libvpx-vp9 and libopus.

```
python qa.py check out_av1.mp4 --scenes . --size 640x360 --fps 30 --bpm 120
```

`qa.py check` holds the pixel format and the BT.709 chain to the H.264 deliverable only. On any other codec it gives Q705, Q707 and Q708 as NOT CHECKED rows (`av1 file: the yuv420p check is for the H.264 deliverable`, and so on) and runs every other gate. Both files ended `QA: NOT CHECKED (3)` (45 checks for the AV1 file, 44 for the WebM, which has no frame count for Q704). Those three rows are expected on rung b: the delivery report lists them under Not checked (`delivery-report.md`). They also stop `qa.py approve`, which refuses a `qa.json` with NOT CHECKED rows: `--override "<why>"` keeps the reason in `approval.json`, and `--video` names the file, because `qa.py approve` otherwise takes `OUT` from `run_all.py`.

**Rung c, a GIF preview, from a finished MP4 or from rung b's frames.** At most 15 s, at most 960 px wide, 15 fps and no sound (`formats.md`); a preview, never the deliverable. From a finished MP4, decoded as BT.709 limited range through `contract.DECODE_709` before the palette is made (tested 2026-11-12: 640x360, 113 frames, 1,744,941 bytes for the 7.5 s template):

```
ffmpeg -y -v error -t 15 -i out.mp4 -vf "fps=15,scale=in_color_matrix=bt709:in_range=tv:flags=accurate_rnd+full_chroma_int,format=rgb24,scale='min(960,iw)':-2:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse" -an -loop 0 preview.gif
```

From rung b's PNG frames, which are already RGB (set `-framerate` to the build's fps; 555,373 bytes):

```
ffmpeg -y -v error -framerate 30 -t 15 -i frames/f%05d.png -vf "fps=15,scale='min(960,iw)':-2:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse" -loop 0 preview.gif
```

`qa.py check` is not run on a GIF.

**No ffmpeg at all.** No rung finishes without ffmpeg. The master decodes and measures loudness through ffmpeg, and every encode and every gate on a file runs ffmpeg. What still runs is the whole proof stage, the PNG frames (`render.render_parallel`) and the raw mix (the score step). Install ffmpeg with libx264, check it with `setup.sh`, and run `full`.

**Rung c, GIF preview for Slack (15 s max, 960 px wide max, 15 fps), the earlier one-liner:**
```
ffmpeg -y -i out.mp4 -vf "fps=15,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer" preview.gif
```
(Use the frames or any rung's output as input; GIF has no audio.) Tested locally with palettegen on the frame sequence: works.
