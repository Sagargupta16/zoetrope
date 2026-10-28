# Changelog

Every change to this copy of the video-producer package it was adapted from. The version numbers are this copy's own; the package as received is 1.0.0. File and section names in 1.0.0 and 1.1.0 refer to the package's original layout (`references/01-producer-playbook.md` to `10-qa-and-house-rules.md`).

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
