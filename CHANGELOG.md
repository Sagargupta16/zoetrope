# Changelog

Every change to this copy of the video-producer package it was adapted from. The version numbers are this copy's own; the package as received is 1.0.0. File and section names in 1.0.0 and 1.1.0 refer to the package's original layout (`references/01-producer-playbook.md` to `10-qa-and-house-rules.md`).

## 2.2.3 - 2026-10-29

- **Narration has a voice: Kokoro `af_heart`.** Sagar picked it by ear from `voice_samples.py`. On the engine's first real run it rendered the same three lines in af_heart, af_bella, am_michael and bf_emma, plus the two Windows SAPI voices: 6 of 6 samples, with word times on 3 of 3 lines each, matched to -21.0 LUFS for the audition. `voice.synthesize` now speaks as the narrator (`NARRATOR_ENGINE`, `NARRATOR_VOICE`: `kokoro-ts`, `af_heart`) when no engine is named, and SAPI stays as the timing fallback. The model (`onnx/model.onnx`, fp32, 325.5 MB) and the four voices (0.5 MB each) come from `onnx-community/Kokoro-82M-v1.0-ONNX-timestamped` at commit `dd4401a9`, sha256 checked, into `~/.cache/zoetrope/voices`. `kokoro-ts` is marked tested.
- **Kokoro's word clock moves 70 ms, not 50.** `onset_offsets` on 24 af_heart words that open a line or follow a pause read a median +22 ms late after showtime's 50 ms shift (p10 -11, p90 +56). At 70 ms they read +2 ms (p10 -31, p90 +51). The spread comes from the check itself: it waits for voicing, so a soft p, f or th reads early and a vowel start reads late.

## 2.2.2 - 2026-10-29

- **`qa.py look` shows the frame it is asked for.** It seeked with `-ss t`, and ffmpeg returns the first frame at or after that time, so a time just past a frame's start came back as the next frame. In the promo's final review, 2.467, 5.967 and 7.967 s returned the cut frame after them, and 8.367 and 8.467 s the next odometer value. Each time now goes onto the frame clock (`contract.frame_of`), and the decode seeks half a frame before that frame. On the promo, all five copies match their frame decoded by index, and each copy's label carries the frame number. The default set ends on the real last frame (the stream's frame count) instead of two frames before the end.
- **Proof key cells for text shown on one frame sit on that frame.** The middle of a one-frame rest span [a, b) falls on the half frame, which `frame_of` rounds into the next frame. So on the promo's sheet each odometer value was labelled on the frame after it: 15 of the 32 rest cells. The new `contract.mid_frame` gives the middle frame of such a span, never its end. `proof.py` now uses it for the rest cells (0 of 32 off on the same build), and `qa.py` for its contrast and hold samples, which already clamped this way in a private helper.

## 2.2.1 - 2026-10-29

- **README rebuilt around a flow diagram.** `docs/zoetrope-flow.svg` shows the whole flow, from brief to delivered file, across the main chat, both agents and the gates. It is a dual-theme SVG with no scripts and no external links. Its archify source, `docs/zoetrope-flow.workflow.json`, cites file and line ranges at commit `d664a97` and passes archify's validate, check and browser gates. The README adds how a video gets made in six steps, a table of what is in it and a table of the commands, and keeps every earlier section. CLAUDE.md says how to re-export the SVG when the flow changes.
- **A 15 s promo made with zoetrope heads the README.** `docs/zoetrope-promo.mp4` (1920x1080, 30 fps, 15.0 s, 5.1 MB, -14.1 LUFS, -1.9 dBTP) went through the whole workflow: the storyboard with `qa.py holds`, the proof, a fresh proof review, the render, `qa.py check` (QA: PASS, 44 checks, 0 FIX, 0 NOT CHECKED), a fresh final review and `qa.py approve`. The committed copy reads `VERIFY: SAME`. The rows on its gate wall are real `qa.py` output, and its count line reads "58 checks", because the 58 codes belong to 11 gates. `docs/zoetrope-promo.gif` is its silent preview and links to the MP4: 960 px, 15 fps, 64 colours with bayer scale 3, 6.3 MB, against 7.9 MB for the 128-colour rung c encode at a slightly lower PSNR (25.3 against 25.7 dB). `.gitignore` lets `docs/*.mp4` and `docs/*.gif` through; they are the only media committed.
- **LICENSE: all rights reserved.** It grants no license, names the adapted third-party parts as not owned, and lists the licenses of the dependencies it runs on. It is not an open-source license, because the package zoetrope is adapted from is not ours to license. `SKILL.md` declares it in its `license` field.

## 2.2.0 - 2026-10-29

Every finding of the 2026-10-28 research pass is applied: the 20 top ideas (Z01 to Z20), each with its verdict's corrections, plus the actionable "also worth noting" items. The research file is `outputs/research-2026-10-28/research.json`. Twelve lanes built it in parallel on one shared contract, each the only writer of its own files. Then seven fresh-eyes code reviewers raised 81 issues (13 high) with reproductions: 80 were fixed and one was rejected with its limit written down. Five calibration runs on the approved 2026-10-28 samples tuned the new gates against false positives.

**Shared pieces**
- **`engine/contract.py`** is what every module shares. It holds the frame clock (`frame_of`: nearest frame, the one rounding rule) and the QA `Row`, which still unpacks as the old 4-tuple. It also holds the file formats (frames.hash, thumbs.npy, cuesheet.json, review_times.json, build.json), the colour chain, the mux command and the Q code table `CODES` (58 codes with owner, gate and status). Finally there is `Ctx`, which decodes the file once (RGB, linear light, grey, audio) for every gate module. `qa.py check` loads the gate modules as plugins; a module that raises is one Q100 NOT CHECKED row, not a dead check.
- **NOT CHECKED** is a status of its own: exit code 2, and run_all rejects on it. It applies wherever something was declared but could not be checked. A scenes.py opts out with `NO_TEXT`, `NO_CUES` or `SILENT`, and `ALLOW = {code: [t or (t0, t1)]}` silences NOTE-level scans.

**Render and delivery**
- **Frames piped, never dumped (Z01).** `render.render_to_ffmpeg` sends raw frames through a shared-memory ring into one H.264 encode (`video.mp4`); each worker also returns the frame's digest and thumb.
  - Speed: a 2 ms flat style ran at 139 fps against 68 through PNG files, the template at 45 against 32, with no 1.3 GB of PNGs on disk.
  - The ring replaced 6.2 MB pipe messages. Those had failed with WinError 1450 under parallel builds: 7 of 45 renders at 5 builds x 5 workers, against 0 of 40 with the ring.
  - A wrong-size frame, or an error ffmpeg logs while exiting 0, fails the encode.
  - `STATIC` holds are drawn once (a 10 s hold rendered in 8.7 s against 13.3 s, byte-identical); `--keep-frames` and `--redraw T0-T1` re-render one passage.
- **Stages and flags.** `run_all.py proof | full | audio` with `--size`, `--fps`, `--ss` and `--budget-mb`; `build.json` records the size for every other CLI.
  - `audio` re-masters and re-muxes only (10 s against 20 s for the template's full build) and refuses a video.mp4 that predates scenes.py.
- **Delivery contract (Z10).** `full` and `audio` run `qa.check` and the thumb scans themselves.
  - Any FIX or NOT CHECKED renames the file `<name>.rejected.mp4`; a crash before the verdict leaves `<name>.unchecked.mp4`.
  - Approval state never rejects a file: it prints one `APPROVAL: none yet | current | stale: <reason> -> <next step>` line.
  - A clean pass ends with exactly one `DELIVERED <path> (<MB>, <s>, <LUFS>, <dBTP>)` line for the report to quote.
- **True peak after the encode (Z03).** run_all measures the MP4's true peak; over -1.3 dBTP it re-masters lower and muxes again, at most 3 times, and keeps the best clean master.
- **BT.709 tags (Z16).** The encode converts and tags bt709/bt709/bt709/tv. Untagged files had played up to 40 levels off on pure green.
- **Size budget and grain (Z14).** `BUDGET_MB` caps the picture through maxrate and bufsize. It is a cap, not a guarantee; Q1001 checks the file. `grain.grain` uses seeded tiles held for 2 frames. Cell size, not refresh rate, decides size under x264's MB-tree: on the lighthouse film the kit's 2 px grain costs 34.8 MB a minute, `grain.grain` 17.5 to 19.1, no grain 13.3. formats.md lists measured MB a minute by style class.

**Audio**
- **Landmark placement (Z02).** `synth.place` lands a sound's onset, peak (the middle of the loudest 50 ms for whooshes), end or pad point on its cue. Generators that know their ramp report it, so a pad's attack lands at 44.5 ms on every chord, where measuring read 29 to 118 ms. A head trimmed before 0 fades in over 3 ms, and rows record `audible_s` and `trim_s`.
- **True-peak master (Z03).** `audio.master` is one gain, a numpy 4x true-peak limiter and an ebur128 loop. It lands within 0.05 LU of -14 at or under -2.0 dBTP, with no added delay (alimiter added 4.0 ms). Its true peak agrees with ffmpeg's within 0.006 dB, EBU Tech 3341 signals 15 to 19 included. Q805 fails a master that missed its target or had to compress.
- **AAC 320k.** The mux encodes 320k instead of 192k. Over 9 mixes, 192k raised the decoded true peak by up to 1.23 dB and 320k by at most 0.45 dB.
- **Stems and a cue sheet (Z12, Z07).** `audio.render_audio(scenes)` writes mix_raw.wav, the SFX bus as sfx.wav, and cuesheet.json with cue_sounds.npz (every placed sound with its landmark, gain and bus). Every engine sound and every kit score now seeds its own noise, so adding one sound leaves the others bit-identical.

**Engine**
- **One frame clock (Z06).** `scene_at` decides on integer frames: at 72 BPM and 24 fps the float code opened 128 of 400 scenes a frame late, the new code 0.
- **Declared timelines (Z19).** `compile_schedule` builds SCHEDULE, DURATION, CUTS, WINDOWS and CUES from scene durations, transitions and scene-local cues in exact frame arithmetic. Straddle mode is the default; overlap mode is Remotion's. It raises on transitions under 2 frames or over half the shorter scene. `scenes_at` gives both scenes and the mix inside a window.
- **Other helpers.** `rng(*keys)` seeds per scene, element and frame (Z09). `transitions.py` has nine pure f(a, b, p) transitions with a flash-risk tag. `spring` and `settle_time` match Remotion's. `text_box(tracking=)` matches `text(tracking=)`. The template builds on all of these: one `layout(t)` drives both draw() and text_items().

**Gates**
- **Rows with frames (Z11).** Text gates give one row per defect with spans, `worst_t` and `considered`; `qa.py check --json` writes the rows and adds each finding's moment to review_times.json.
- **Reading pace (Z15).** `min_hold(text, profile)` adds a characters-per-second term: display 20 cps, caption 17, slow 15 cps + 1.0 s. On the five samples it adds 2 flags to 143 approved holds.
  - `ticker=True` exempts a counter's passing values.
  - New gates: Q403 (text that never settles), Q404 (incomplete reveal), Q207 (changeover gaps of 3 frames to 0.5 s).
- **Colour (Z16).** Q707 checks the tags; Q708 round-trips saturated swatches through the encode chain.
- **Flashes to WCAG 2.2.** The flash gate now uses linear light, a run accumulator and a sliding 1 s window, and counts a flash only when it covers a quarter of the frame or of a 10 degree window. Q601 is general flashes, Q602 red and Q603 the extended band. It catches a 3.4 Hz triangle with sub-20/255 steps and an equal-luminance red and green strobe, both of which the old rule passed, and no longer fails dark fades.
- **Frame scans (Z17).** Q1101 one-frame pops, Q1102 frozen runs, Q1103 unplanned hard cuts and Q1104 stalls, all NOTE. Calibration on the approved films cut the pops from 7 to 114 a minute (the published popscan rule) to 0 or 1 a minute; the one on the battle film is a real 1 px twitch no earlier gate pointed at. Q1105 FIXes a file that does not match its drawn frames.
- **Registry completeness (Z13).** Q204 to Q206, Q208 and Q209 compare what draw(t) really paints with what text_items(t) reports, through crops, pastes, blends and masks. Masked or clipped text reports its visible box.
- **Cue sync on stems (Z12, Z02).** Q902 finds each cue's own sound on sfx.wav and FIXes it when more than one frame late or more than 40 ms early. Q903 checks the mux against mix.wav and mix_raw.wav, and `qa.py calib` sends a white frame and a blip through the real chain.
  - Pain 3 measured: the mux adds 0.000 ms and AAC priming is trimmed. The lateness was slow attacks placed by their first sample; a pad put on a cue now reads FIX +44.5 ms.
- **True peak and stacking (Z07).** Q802 finds the moment inside ebur128's loudest frame, channel by channel, and names every sound present there with a cut order (a house heuristic). Q804 notes heavy sounds stacked within 3 frames.
- **Purity and lint (Z09, Z06, Z08).** `qa.py purity` draws up to 34 frames (cut edges first, always with interior picks) in order, reversed in a fresh `python -I` process and through a pool, and names the frame that poisons a mismatch. `qa.py lint` flags unseeded randomness, clocks and str `hash()` (FIX), and module state, shadowed helpers, stray text drawing, colour literals and off-grid times (NOTE).
- **Approval bound to hashes (Z04, Z10).** `qa.py approve --review <reply>` records the reviewed build atomically, with a sha256 of every file. `qa.py check` gives Q1301 STALE APPROVAL for the scenes that changed, and Q1304 when the environment moved pixels. With `--baseline`, Q1302 reports regressions.
  - `qa.py diff --expect` names changed spans frame by frame, with triptychs; a one-scene colour change came back as exactly its 71 frames. `qa.py verify` re-hashes the file.
- **Review sheets (Z11, Z17, Z19, Z20).**
  - `proof_keys.png` ranks numbered cells FIX first and never drops a FIX, split into pages of at most 2000 px.
  - `proof_strips.png` shows frames f-2 to f+2 around a pop, and `proof_gantt.png` puts scenes, windows, texts, cues and cells on one time axis.
  - `qa.py audiostrip` draws review/audio.png: a spectrogram, loudness, cue ticks coloured by their measured offset, and true peak over -1 dBTP in red.
- **Planted-fault selftest (Z18).** `qa.py selftest` ends `SELFTEST: PASS (144 fixtures, 58 of 58 codes covered, 0 expected gaps)` in 36 s, with the template at both sizes as controls. Three thresholds broken on purpose were each caught.

**Builder, voice and kits**
- **Token diet (Z08).** `python kit_index.py` lists the 533 public helpers without importing anything; `qa.py owner --t` names the scene function a finding belongs to. The builder edits one scene function after the first green proof, and environment failures stop under `blocked`.
- **Offline narration (Z05).** `voice.synthesize` caches one WAV per line and writes narration.json with word times; the cache key covers the engine's code and model files. `word_cue` resolves a word to its time. Only the Windows SAPI voices are tested, as plumbing. Kokoro and Piper are written but untested until their models are approved, and `voice_samples.py` renders the same lines with every ready engine.
- **Kit fixes.** The g29 kit seeded its lightning with `hash(name)`, which differs per process (26,820 px apart at 32.0 s); it now uses `zlib.crc32`. Copied as is, a kit fails proof until its text_items(t) registry is added (kits/README.md).
- **Docs.** references/, SKILL.md and both agents describe the new stages, gates, sheets and rules. README.md lists the modules, and CLAUDE.md the new gotchas and the verify list.

Not done, on purpose:
- The narration model downloads (Sagar picks from samples first).
- A 1 h prompt-cache TTL for the builder (a billing change).
- A two-pass encode at the size cap (a CRF run spends about 70 percent of the budget on heavy grain).
- The per-scene segment cache (deferred by the research).
- AV1 decode-side grain (probed only).

## 2.1.0 - 2026-10-28

- Moved to `C:\Code\GitHub\tools\zoetrope` and pushed as the private GitHub repo `Sagargupta16/zoetrope`; both junctions re-pointed. History squashed into one commit first, so no earlier text is on GitHub.
- Notes written for the agent platform the package targeted are rewritten for this engine: the SKILL.md tool map became a short Tools table, the cards' build-notes headings and fps notes no longer name a platform, the credits line left SKILL.md and the delivery report, and `voice.md` and `troubleshooting.md` describe any text-to-speech engine instead of one service's API.
- The deals card is `S-mobiles-deals` (`references/styles/mobiles-deals.md`).
- `CLAUDE.md` holds the build lessons and repo rules for Claude sessions in this folder.

## 2.0.0 - 2026-10-28

Renamed, and the lessons from the first five-video batch built in. The batch's measured pain points are in `outputs/samples-2026-10-28/BUILD-NOTES.md`.

- **Renamed to zoetrope** (invoke as `/zoetrope`). The repo moved to `C:\Code\GitHub\local\zoetrope`; the junctions are `~/.claude/skills/zoetrope` and `~/.claude/agents/zoetrope`; the agents are `zoetrope-builder` and `zoetrope-reviewer`. claude-home's `.gitignore`, the global CLAUDE.md skills table and the workspace memory were updated to match.
- **Text and cue registry.** `scenes.py` declares `text_items(t)`, `CUES`, `CUE_LAG` and `KEY_TIMES` (the template shows how, with one layout function for both drawing and the registry). `qa.py check --scenes .` now runs gates 2 to 4 on every frame (Q201 safe area, Q202 overlap at rest, Q203 overlap during a transition, Q301 contrast against a ring of real pixels around the text, Q401 reading hold, Q402 key text size) and Q902 cue sync (audio onset within one frame, picture change within the allowed lag). Before this, every builder wrote its own gate script, and crossfades in place slipped through.
- **Re-review rule.** Any change after a REVIEW PASS is listed with its times and re-reviewed with its neighbouring frames (SKILL.md, both agents). Two of the batch's three late faults came from such changes.
- **Key-times proof sheet.** `run_all.py proof` also writes `proof_keys.png` and `review_times.json`: both sides of every cut, every caption at rest and `KEY_TIMES`. The reviewer reads both sheets and checks the final file at those times.
- **Shared engine pieces.** `render.render_parallel` (Windows-safe worker start, `frames=` to re-render one passage, PNG compress level 1); `run_all.py` work under a main guard; `engine.text_box`, `fit_size`, `text_outline`, `text_halo`; `qa.flash_window` for one passage on drawn frames.
- **Scenario hold check.** `qa.py holds <scenario.md>` checks every storyboard line's slot against the reading-time rule before any build; on the batch's scenarios it flags 27 of 83 lines, including every one a builder had to re-time.
- **Audio and size.** `audio.master` targets TP -3.0 (the AAC encode adds 1 to 1.5 dB: -1.5 in the WAV became -0.4 in the MP4, and the template failed Q802 until this change); Q802 names the loudest moment; Q1002 notes bitrate over 12 Mb/s; `formats.md` has the batch's measured sizes and the grain rule (std 1.6 or less, CRF 20).
- **Style kits.** `kits/` holds working code from the five approved builds (g04, g11, g17, g29, bonus-rectangle) with a README each; the five cards and the router point to them.
- Template: 7.5 s (three 2.5 s scenes) so its own lines pass the reading-hold rule; the accent rule no longer paints a dot at zero width.

## 1.3.1 - 2026-10-28

- Videos are made inside the skill folder: the default working folder is `outputs/<slug>/` (was `~/Downloads/<project>/`), and `outputs/` is gitignored. A batch keeps `videos/`, `builds/<nn-slug>/`, its scenarios and build notes together in `outputs/<batch>/`. The 2026-10-28 samples moved there from `~/Downloads/video-producer-samples/`.

## 1.3.0 - 2026-10-28

Adopted the parts of the plugin blueprint (`~/Downloads/claude-plugin-blueprint.md`) that fit a local, user-level skill: a git source of truth, a fresh-eyes reviewer, scripted checks with codes, pinned setup. The plugin manifest, marketplace, release scripts and other channels were left out on purpose: own skills stay user-level, and this one is adapted from a package that is not ours to publish.

- Local git repo with no remote as the source of truth; `.gitattributes` keeps every file LF, as received.
- `agents/video-reviewer.md`: fresh-eyes review at the proof and final stages. It gets only the scenario and the folder, runs `qa.py check` and `qa.py look`, and replies REVIEW PASS or REVIEW FIX with at most ten coded findings (Q codes from the script, R codes for what it sees). SKILL.md steps 8 and 10 run it before the user sees anything, at most three rounds.
- `qa.py check`: every gate measurable on the finished file as PASS, FIX or NOTE rows with Q codes and a fix line, ending `QA: PASS` or `QA: FIX (n)`, exit 1 on any FIX. `qa.py look`: small frame copies and `review/look.jpg`, so a model never reads a full-size frame. Codes are listed in `references/qa-gates.md`.
- Pillow 13.0.0 and numpy 2.5.4 pinned with hashes in `engine/requirements.txt` (input `engine/requirements.in`); every command runs `uv run --no-project --with-requirements requirements.txt`.
- `setup.sh`: idempotent first-use check of uv, ffmpeg with libx264, ffprobe, the pinned packages and the default font, ending `SETUP: PASS` or `SETUP: FIX`.
- `run_all.py full` deletes the old `out.mp4` and `mix.wav` first and prints a `wrote` line per output, so a failed run cannot leave the last good file to be reviewed.
- This file replaces the README's customizations table.

## 1.2.0 - 2026-10-28

- One folder: the nested `video-producer/` moved up so the project folder is the skill; the skill junction re-pointed there. A folder inside a folder of the same name, with the agent beside it, read as two projects.
- References split into small files: 01 into `playbook.md`, `engine.md`, `formats.md`; 02 into `voice.md`, `music.md`, `mixing.md`, `beat-sync.md`; 10 into `house-rules.md`, `qa-gates.md` (gates renumbered 1 to 10), `pitfalls.md`, `delivery-report.md`, `troubleshooting.md`; 03 to 09 into one file per card in `styles/` plus `families.md`. The router links each card, so the agent reads one 40 to 60 line card instead of a 335-line family file.
- Engine code moved out of the markdown into `engine/*.py` (one `ruff format` pass): the 01 code blocks; the 02 synth kit as `synth.py` plus `put_peak`; the 10 gate snippets as `qa.py` functions; the 02 voice snippets as `voice.py` (`dec`, `span`, `section_beats`, `duck_mix`); and `audio.master` for the two-pass loudnorm that `run_all.py full` now uses (it used one pass). Measured on a test render: -14.0 LUFS, -2.1 dBTP, against -14.3 LUFS before.
- Voice measuring and ducking run at 44.1 kHz like the rest of the engine (the 02 snippets used 48 kHz, which drifts the timing when mixed sample by sample into a 44.1 kHz bed); `audio.master` still writes the final mix at 48 kHz.
- Deleted the original package zip. It also held an import JSON for the platform the package targeted and the package README, which nothing here uses. No copy of the original is kept.

## 1.1.0 - 2026-10-28

- `description` gained a "Not for" line naming `motion` and `social-post`, because "make a reel" and "launch video" matched this skill and `motion` alike.
- engine.py font lists start with `C:/Windows/Fonts/arialbd.ttf` and `arial.ttf`, and a missing font raises instead of `ImageFont.load_default()` (01 section 5.1, the SKILL.md tools table, 10 pitfall 18 and troubleshooting). Only Mac paths existed, so on Windows every 97 px headline silently rendered with Pillow's 10 px default font.
- `proof_times` spreads up to 12 stills over every scene, midpoints first (01 section 5.3). It sorted and cut at 12, so a 10-scene 30 s piece proofed only scenes 1 to 4.
- Frame 0 shows the hook fully drawn and the scenes.py template skips the first scene's entrance (01 sections 3 and 5.2). The playbook said "never frame 0" while the QA gate fails a dark frame 0; the template measured mean 26.2, std 6.7 against std > 12.
- One reading-hold rule, 0.5 s + 0.3 s per word and at least 1 s (SKILL.md defaults, 01 section 2, matching 10 section 2.4); safe-area gate 4 percent (10 section 2.2); loudnorm TP -1.5 in 10 section 2.8; working folder `~/Downloads/{slug}/` in 01 section 5; dead `ENGINE.md` and `build/audio_test.py` references pointed at 01 and 02. The files disagreed with each other and named files the package does not ship.
- Added the `video-builder` agent. SKILL.md steps 6 to 11 hand build, proof, render and QA to it and keep both approvals in the main chat, because a subagent cannot wait for "go" mid-run.

## 1.0.0 - 2026-10-28

- Adopted from a video-producer agent package zip (122 KB, 13 files: one `SKILL.md`, 10 reference docs, a platform import JSON, a README).
- `description` rewritten as a folded block scalar with the same words: the unquoted `: ` failed strict YAML (skillcheck SC004), and lenient clients cut the description, dropping its triggers.
