# CLAUDE.md

> This file stacks on top of the workspace root at `C:\Code\GitHub\`:
> - Root [`CLAUDE.md`](../../CLAUDE.md) -- voice, rules, routing map, references, skills, slash commands, conventions.
> - Root [`MEMORY.md`](../../MEMORY.md) -- live facts across repos.
> - Root [`STATUS.md`](../../STATUS.md) -- live PR/CI/security dashboard.
> - [`.claude/resources/`](../../.claude/resources/README.md) -- deep reference for collaboration, workflow, git, OSS, debugging, voice.
>
> Read those first. The guidance below only adds **repo-specific context** -- it does not override anything in the root.

# CLAUDE.md

Guidance for Claude Code when working in this repository. What each file does is in [README.md](README.md); every change and its reason is in [CHANGELOG.md](CHANGELOG.md).

## What this is

This repo is the public `zoetrope` Claude Code plugin (`/plugin marketplace add Sagargupta16/zoetrope`, then `/plugin install zoetrope@zoetrope`). The skill lives in `skills/zoetrope/` (SKILL.md, `engine/`, `references/`, `kits/`, `setup.sh`), the agents in `agents/`, the manifests in `.claude-plugin/`. Locally, `~/.claude/skills/zoetrope` is a junction to `skills/zoetrope/` and `~/.claude/agents/zoetrope` a junction to `agents/`, so an edit here is live in the next session that loads the skill.

## Repo rules

- **One name, one repo.** The skill, the plugin, the marketplace, the folder and the repo are all `zoetrope`; never a copy under another name. Skill text names no user's home folder: `<skill>` (the skill folder as an absolute path, the base directory shown when the skill loads) or `~/.cache/zoetrope` instead, and `scripts/check.py` fails on a home path (ZC004).
- **Keep the scrub clean.** The original platform's tool names, portal link, team, author and chat channel were rewritten out on 2026-10-28 and the history was squashed. Do not add them back. Before every push, run the identifier grep kept in `~/.claude/projects/c--Code-GitHub/memory/zoetrope-internal-skill.md`; the only hits allowed are the English word "quick".
- Every change gets a CHANGELOG line under a concrete version, and README wherever it describes the changed part. A release bumps `version` in `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` to the CHANGELOG head (ZC007).
- **The README diagram** `docs/zoetrope-flow.svg` is exported from `docs/zoetrope-flow.workflow.json` with the archify skill. When the flow changes, edit the JSON and set `meta.repository.revision` to the new commit, run archify `finalize workflow` with `--repo-root .`, open the HTML in a Chrome DevTools page (the browser pane cannot open `file://`), run `Archify.exportMenu.run('svg')` while catching the blob from `URL.createObjectURL`, replace its two non-ASCII separators (U+203A, U+00B7) with `&gt;` and `|`, and look at it at 880 px in both themes.
- Files are LF (`.gitattributes` sets `eol=lf`), unlike most Windows repos in this workspace. Check the bytes before assuming either way.
- Everything a build makes goes in `outputs/` (gitignored): videos, working folders, scratch scripts, history bundles. The one exception is the README's promo in `docs/` (`.gitignore` lets `docs/*.mp4` and `docs/*.gif` through).

## Loading and agents

- Installed as a plugin, the agents are `zoetrope:zoetrope-builder` and `zoetrope:zoetrope-reviewer`. Through the local junctions they load as `zoetrope-builder` and `zoetrope-reviewer`: Claude Code reads agents from `~/.claude/agents/` recursively, and the agents junction points at `agents/` only; pointed at the whole folder, every `.md` here would load as an agent.
- A new or renamed agent type does not appear in a session that was already running. There, launch a general-purpose agent and tell it to follow `agents/zoetrope-builder.md` or `agents/zoetrope-reviewer.md`.
- To prove a fresh load, run this in the Terminal panel (a Bash child cannot use the Desktop-managed Bedrock login):
  `claude -p "Without running any tools, answer two lines only. Line 1: the first 12 words of the description of the skill named zoetrope, or NOT FOUND. Line 2: the names of your custom subagent types, comma separated."`

## Engine gotchas (hit on 2026-10-28 and 2026-10-29)

- **Windows workers.** `run_all.py` work sits under `if __name__ == "__main__":`, and `render.py` imports `scenes` inside its functions, because each worker must set `E.W`, `E.H` before `scenes` reads them. A top-level import rendered a 9:16 piece at 16:9 size.
- **Fonts.** The cards name Mac fonts. `engine.py` lists Windows Arial first and raises on a missing font; before that, Pillow silently fell back to its 10 px default and every headline came out tiny. The 14 OFL families 24 cards name are cached by `fonts.py` (2.2.4) and drawn by name. A variable file is always set to the weight asked for, because their default instances differ: Nunito's is 200, Cormorant's 300, Fraunces' 900.
- **OpenBLAS threads.** `contract.py` sets `OPENBLAS_NUM_THREADS=1` before numpy loads. Unset, one process that loaded numpy and ran a matrix product held 27 threads and 793 MB private, against 4 threads and 54 MB at 1; seven reel builds of eight workers ran out of memory on 2026-10-30.
- **Sleep.** The app holds the PC awake only while a session works, and on battery only with Keep awake on battery power on (turned on 2026-10-31). On 2026-10-29 the laptop went on battery at 07:19, idle-slept at 07:29 during the final review and woke only when plugged in at 13:59: 6.5 of the build's 8.4 hours. A closed lid sleeps whatever the setting.
- **9:16 text.** Size titles with `fit_size` against the short side (`min(W, H)`), or they overflow the safe area (Q201).
- **True peak.** The AAC encode adds true peak: up to 1.23 dB at 192k, at most 0.45 dB at 320k (9 mixes). So `audio.master` limits to -2.0 dBTP with a numpy 4x true-peak limiter, the mux encodes AAC 320k, and `run_all.py` re-masters lower when the decoded MP4 reads over -1.3. When Q802 still fails it names every sound present at that moment; lower the first one in its cut order.
- **Cue sync (Q902).** Q902 measures each cue's own sound on the lossless SFX stem from the cue sheet, not by guessing onsets in the mix. The 37 to 87 ms lateness of the first batch was placement: slow attacks placed by their first sample (a 0.25 s pad attack is heard 44 ms in). The mux adds 0.000 ms; the old alimiter added 4.0 ms. Place sounds with `synth.place` by their landmark.
- **Sample rates.** Every audio module runs at 44.1 kHz; only `audio.master` writes 48 kHz. Mixing 48 kHz voice sample by sample into a 44.1 kHz bed drifts the timing.
- **File size.** Film grain drives size: grain std 2.6 gave 140.2 MB for 60 s, std 1.6 at CRF 20 gave 35.9 MB. Q1002 notes bitrate over 12 Mb/s.
- **Parallel renders.** A raw 1080p frame is 6.2 MB. Sent back from render workers through a process pipe while five builds of 5 processes shared the machine, 7 of 45 renders died with WinError 1450 (2 of 6 at three builds of 8). `render.py` passes frames through a shared-memory ring instead: 0 of 40 and 0 of 6, byte-identical output (2026-10-29).
- **Console encoding.** A redirected Windows console is cp1252: printing a caption with an arrow crashed a passing build. Rows print ASCII (`contract.line`).
- **stdin.** An ffmpeg decode without `-nostdin` stops early with exit 0 when a key is waiting (a 60 s check read 200 of 1800 frames). Every decode closes stdin and checks its frame count.
- **str hash.** `hash("text")` changes in every process (PYTHONHASHSEED). A seed made from it gave each render worker different lightning in the g29 kit; seed from `zlib.crc32` or `engine.rng`.
- **Durations as quotients.** `5/30` is not exactly 5 frames as a float; `compile_schedule` reads floats as fractions with a denominator up to 10**6.
- **Windows locks.** A folder that is a process cwd or a watched folder cannot be moved or deleted. Move its contents instead, and keep shells out of `outputs/` subfolders.

## Lessons absorbed on 2026-11-12 (from the clean-room public version, written from this engine on 2026-11-01)

- **Refuse before you clean.** A stage that refuses (no ffmpeg, a stale picture for `audio`, a size budget with no video bitrate) must do it before `clean()` and before `build.json` is written. `audio` used to check `picture_is_current` after deleting `out.mp4` and the mixes, so a refused run with the wrong `--size` destroyed the last good build and rewrote `build.json`.
- **A cut file gets a verdict, not a traceback.** A copy cut to 35 to 50 percent of its bytes still has every frame counted by ffprobe (the moov box is in front), but its last frame does not decode: Q502 stopped `qa.py check` with `ValueError: cannot reshape array of size 0`. Q501 and Q502 now read NOT CHECKED there, like Q503, and `files.cut` plants it.
- **No ffmpeg means stop.** Every rung of the encode ladder needs ffmpeg (the master measures loudness with it too); only a build without libx264 drops to rung b or c.
- **`cp -r engine/*` drops the Python pin.** A glob skips the hidden `.python-version`, silently; copy with `engine/.`. Without the pin a proof and its render can land on different interpreters, and Q1304 sees the change.
- **Docs drift from code.** Rewriting the references from the code found docs that disagreed with the engine, among them the template bed's docstring (no bass or pad line: a tick and a tone), `render.CRF` (only `run_all.CRF` changes the build), a `qa_sync` comment (PAD_TOL, not 0.04 s), and a lint pointer to a table that did not exist. Every number in a reference names its constant or is dated to a run.

## 3D plates and recorded instruments (hit on 2026-11-10)

- **This folder is live while you edit it.** The junction makes every save the skill. On 2026-11-10 another session was building a reels batch from here while 2.4.0 was written: keep `engine/` runnable at every save, and add a card, its kit and its router row in one step.
- **Blender's view transform.** Its default (AgX) turned the card's palette pastel; `stage3d.py` uses Khronos PBR Neutral, which keeps hue and saturation and rolls the highlights off. Standard clipped a lit cream floor to flat white.
- **Paths into Blender.** A relative `render.filepath` is read from the drive root: the first test wrote four frames to `C:\plates`. `stage3d.run` resolves `--out`.
- **bpy first.** `bmesh`, `mathutils` and `bpy_extras` exist only after `import bpy`; an import sorter puts `bmesh` first and the stage dies. The two lines carry `# isort: skip`.
- **Samples.** 48, 64 and 160 paths a pixel look the same on a character close-up after the denoiser, at 2.6, 3.3 and 8.1 s a 1080p frame (RTX 4070 Laptop, OptiX): final quality is 64.
- **uv keeps no wheel an offline run can find.** `uv run --offline --with bpy==5.2.3` fails right after an online run that worked (uv 0.13.6), so `plate3d.missing()` reads a note that `fetch()` leaves in `~/.cache/zoetrope/blender/`, not the cache.
- **A cleaned uv cache.** Something outside the session cleaned uv's cache mid-build (`C:` went from 82 to 426 GB free): for a minute `import numpy` failed in the engine environment from a half-removed entry, and Blender (324 MB) downloaded again on the next render. Retry before debugging.
- **The lint follows imports.** Q1202 reads every local module `scenes.py` imports. `plate3d.py` timed its progress lines with `time.perf_counter()` and the proof failed on it: that file reads no clock.
- **Sample tuning.** `sampler.py`'s manifest holds each recording's measured root and cents (FFT peak, median over the loud frames): most VSCO 2 CE and VCSL file names put middle C at C3 (the harp's at C4), the glockenspiel is 8 to 25 cents sharp and four of the five timpani sit near quarter tones. Measure a new row the same way; autocorrelation cannot read the mallets or timpani (inharmonic). A second reader with a first-period autocorrelation put harp, strings, flute and horn within 3.1 cents.
- **Contact is placed from the rig and measured, not worked out.** The pilot's star was placed by arithmetic twice and two reviews each found a P0 at the catch (the head through the star, then the hand inside it for seven frames) while every gate passed. It now hangs at `S3.where(hand) + HOLD`, read from the rig posed as at the catch, and `python plate3d.py run stage.py contact` prints the hand-to-star gap per frame with no render. Do both for anything that is caught, held or handed over.
- **A re-render is not byte-identical.** The same frame rendered twice differed by 0.11 of 255 on average and 9 at most (GPU path tracing and the denoiser). Never render an approved plate again unless its stage changed: every frame would read as changed (Q1301).
- **Heredocs.** The Bash tool turned `"\n"` inside a Python heredoc into a real line break and broke `run_all.py` for a minute. Patch files that hold a backslash with the Edit tool.

## Process lessons

- **Fresh eyes find what self-checks miss.** Every builder reported its still-frame gates green; the reviewer still found a real visual fault in each first review. Keep the reviewer step even when the numbers pass.
- **Re-review after any change.** Two of the three late faults came from changes made after a REVIEW PASS (one: a line-height tweak grew a header and hid the top of a counted outline). List every change with its times and have a fresh reviewer check those frames and about 0.5 s either side.
- **Check holds before building.** `qa.py holds <scenario.md>` flagged 27 of the batch's 83 storyboard lines, including every one a builder later had to re-time.
- **Facts are checked in the main chat.** The builder cannot browse; put checked facts and sources into the scenario before the build.
- **Review the gates too.** In the 2.2.0 upgrade every lane's own planted faults passed, and seven fresh-eyes code reviewers still found 81 issues (13 high) with reproductions; 80 were fixed and one was rejected with its limit written down. Five calibration runs on the approved samples showed new scans raising up to 114 false pops a minute before tuning. Calibrate a new gate on the approved samples and have a reviewer reproduce its edge cases before trusting it.

## How long a video takes (5 videos of 60 s, built in parallel on 2026-10-28)

Machine: 32 logical cores, 32 GB RAM, ffmpeg 9.0.2, five builders sharing the CPU.

| Phase | Time per video |
| --- | --- |
| Scenarios (all five, with fact checks) | about 5 min in the main chat |
| Proof (engine copy, scenes.py, score, proof sheet, still gates) | 39 to 46 min of agent time, 270k to 390k tokens |
| Proof review, fix, re-review | 7 to 10 min, 3 to 6 min, 5 to 8 min |
| Render (frames, audio, master, encode, `qa.py check`) | 6.5 to 17 min per agent turn; the frames alone 14 to 150 s on 4 to 6 processes |
| Final review | 7 to 11 min |

All five went from launch to finished file in about 1 h 16 min. Writing `scenes.py` and the score is most of the time; frames are pure functions of t, so rendering is cheap. Per-frame cost ran from 3 ms (flat shapes) to about 360 ms.

A 3D card (one 16.5 s build at 24 fps, 2026-11-10, RTX 4070 Laptop): stills under a second each, the proof plate 3 min, a final plate 17 to 20 min, `run_all.py full` under a minute. The final plate was rendered four times, because each review changed the stage: budget an hour of GPU for the renders alone, and stage with stills until every scene reads before the first one.

## Verify before a commit

- `bash skills/zoetrope/setup.sh` ends `SETUP: PASS`, with the lines that the 14 free font families, the speech model and the 14 recorded instruments are cached and Blender is fetched (`python skills/zoetrope/engine/fonts.py fetch`, `qa_speech.py fetch`, `sampler.py fetch`, `plate3d.py fetch` when they are not).
- Smoke render: copy the engine with `cp -r skills/zoetrope/engine/. outputs/smoke/` (so `qa_fixtures/` comes along), then at `--size 1920x1080` and again at `--size 1080x1920`: `run_all.py proof` ends `PROOF: PASS`, `run_all.py full` ends with its `APPROVAL` line and one `DELIVERED` line, and `qa.py check out.mp4 --scenes . --size WxH --fps 30 --bpm 120` ends `QA: PASS` with 0 FIX and 0 NOT CHECKED.
- `qa.py selftest` (from the same folder) ends `SELFTEST: PASS (161 fixtures, 60 of 60 codes covered, 0 expected gaps)`: every Q code fires on its planted fault with the right item, time and value, and the template passes `run_all.py proof` and `full` at 1920x1080 and 1080x1920 (45.9 s on 2026-11-12; `--quick` skips the two full renders, about 28 s). The count is one per expected result, not per case: 85 cases.
- A change to `voice.py` or `qa_speech.py`: narrate a few lines and run `qa.py speech` on them (Q806 must read what the voice said), and run one narrated build to `DELIVERED` so Q807 finds the stem in the file. The calibration narrations are in `outputs/voice-samples-2026-11-03/` and `outputs/voice-samples-2026-10-29/`.
- A change to `plate3d.py` or `stage3d.py`: copy the engine and `skills/zoetrope/kits/toy-studio-3d/` into a scratch folder, render stills (`plate3d.py render stage.py --quality proof --stills 0,4.25,10.875`) and look at them, then the proof plate and `run_all.py proof --fps 24` to `PROOF: PASS`. `plate3d.py check` must name a missing frame, a `render.lock`, and a plate made stale by a touched `beats.py`. A change that could move pixels needs one final plate and `run_all.py full` to `DELIVERED` (about 20 minutes on the GPU).
- A change to `sampler.py`: `python skills/zoetrope/engine/sampler.py demo outputs/scratch/demo.wav` twice gives the same bytes; the pitch, onset and seam scripts are in `outputs/scratch/sampler/` and `outputs/scratch/refute/` (gitignored: they go when that folder is cleaned).
- `python skills/zoetrope/engine/cards.py check` ends `CARDS: OK (40 cards ...)` after any change to a card, the router or a kit.
- `python scripts/check.py` ends `<n> files checked, 0 problems` (dashes, secret-shaped strings, home paths, the SKILL.md frontmatter, broken Markdown links, JSON, manifest versions, CR bytes). CI runs it and the selftest on a fresh engine copy (`.github/workflows/ci.yml`).
- `claude plugin validate .` passes.
- `uvx ruff format --check skills/zoetrope/engine` is clean. `uvx ruff check skills/zoetrope/engine skills/zoetrope/kits` is not (184 findings on 2026-10-29: the template's `from engine import *` by design, plus lint debt in the kits), so compare its count before and after a change instead of expecting zero.
- `node ../../community/skillcheck/dist/cli.js lint skills/zoetrope` is clean (lint the folder by its own name: linted as `.`, a folder whose name is not `zoetrope` is an SC014 error against the skill name).

## Open

- Voice: the narrator is settled, Kokoro `af_heart` through `kokoro-ts` (Sagar's pick from `voice_samples.py`, 2026-10-29). Every English male and Hindi Kokoro voice is downloaded (2026-11-03) and sampled in `outputs/voice-samples-2026-11-03/`; a second voice for two-host videos waits for Sagar's pick by ear, and two-voice narration (two `voice.synthesize` calls on one timeline) is not built. Hindi narrates with word times, but Q806 cannot check it (base.en is English only; a multilingual model is a separate download).
- Builder prompt cache: a 1 h cache TTL for the builder agent (research Z08) changes billing; not added, waiting on Sagar.
- Size cap: under `BUDGET_MB` a CRF encode spends only about 70 percent of the budget on heavy grain; a two-pass encode at the cap is not built.
- 3D (2.4.0): one card and one build so far, 16:9 at 24 fps. Not built: motion blur, a 9:16 staging, a plate on twos in a delivered film, a second character rig, any model or texture from outside. Whether the look is what Sagar meant by "Pixar animated" is his call on `outputs/pip-star/pip-star_16x9_17s_v6.mp4` (2.4.1: the notes of the third and fourth reviews fixed, approved after a fifth review with five P2 notes left, which are in the kit README); more 3D cards wait for it.
- Recorded instruments (2.4.0): measured (pitch, onsets, loop seams, determinism), never heard. The score is mono like every bus here; stereo is not built.
- From the 2026-11-10 research, not built and waiting on Sagar: more 2D looks in the families lemo-opuscar has and we do not (print, painting, documentary); a multilingual speech model so Q806 can check Hindi (faster-whisper small, 0.49 GB, MIT); generated music on the GPU (ACE-Step 1.5, MIT, 8 GB of VRAM); stock media through an MCP server. No MCP server was added: none found does something the engine needs that it cannot do itself.
