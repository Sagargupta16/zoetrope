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

This folder is the `zoetrope` skill itself, not a copy: `~/.claude/skills/zoetrope` is a junction to it and `~/.claude/agents/zoetrope` is a junction to `agents/`. An edit here is live in the next session that loads the skill.

## Repo rules

- **Private, always.** It is adapted from a package that is not ours to publish. Never change the visibility, and never copy its files into claude-home, svg-forge, orrery, sagar-dev-skills, the portfolio or a post.
- **Keep the scrub clean.** The original platform's tool names, portal link, team, author and chat channel were rewritten out on 2026-10-28 and the history was squashed. Do not add them back. Before every push, run the identifier grep kept in `~/.claude/projects/c--Code-GitHub/memory/zoetrope-internal-skill.md`; the only hits allowed are the English word "quick".
- Every change gets a CHANGELOG line under a concrete version, and README wherever it describes the changed part.
- **The README diagram** `docs/zoetrope-flow.svg` is exported from `docs/zoetrope-flow.workflow.json` with the archify skill. When the flow changes, edit the JSON and set `meta.repository.revision` to the new commit, run archify `finalize workflow` with `--repo-root .`, open the HTML in a Chrome DevTools page (the browser pane cannot open `file://`), run `Archify.exportMenu.run('svg')` while catching the blob from `URL.createObjectURL`, replace its two non-ASCII separators (U+203A, U+00B7) with `&gt;` and `|`, and look at it at 880 px in both themes.
- Files are LF (`.gitattributes` sets `eol=lf`), unlike most Windows repos in this workspace. Check the bytes before assuming either way.
- Everything a build makes goes in `outputs/` (gitignored): videos, working folders, scratch scripts, history bundles. The one exception is the README's promo in `docs/` (`.gitignore` lets `docs/*.mp4` and `docs/*.gif` through).

## Loading and agents

- Claude Code reads agents from `~/.claude/agents/` recursively. The agents junction points at `agents/` only; pointed at the whole folder, every `.md` here would load as an agent.
- A new or renamed agent type does not appear in a session that was already running. There, launch a general-purpose agent and tell it to follow `agents/zoetrope-builder.md` or `agents/zoetrope-reviewer.md`.
- To prove a fresh load, run this in the Terminal panel (a Bash child cannot use the Desktop-managed Bedrock login):
  `claude -p "Without running any tools, answer two lines only. Line 1: the first 12 words of the description of the skill named zoetrope, or NOT FOUND. Line 2: the names of your custom subagent types, comma separated."`

## Engine gotchas (hit on 2026-10-28 and 2026-10-29)

- **Windows workers.** `run_all.py` work sits under `if __name__ == "__main__":`, and `render.py` imports `scenes` inside its functions, because each worker must set `E.W`, `E.H` before `scenes` reads them. A top-level import rendered a 9:16 piece at 16:9 size.
- **Fonts.** The cards name Mac fonts. `engine.py` lists Windows Arial first and raises on a missing font; before that, Pillow silently fell back to its 10 px default and every headline came out tiny. The 14 OFL families 20 cards name are cached by `fonts.py` (2.2.4) and drawn by name. A variable file is always set to the weight asked for, because their default instances differ: Nunito's is 200, Cormorant's 300, Fraunces' 900.
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

## Verify before a commit

- `bash setup.sh` ends `SETUP: PASS`, with the line that the 14 free font families are cached (`python engine/fonts.py fetch` when it says they are not).
- Smoke render: copy the engine with `cp -r engine/. outputs/smoke/` (so `qa_fixtures/` comes along), then at `--size 1920x1080` and again at `--size 1080x1920`: `run_all.py proof` ends `PROOF: PASS`, `run_all.py full` ends with its `APPROVAL` line and one `DELIVERED` line, and `qa.py check out.mp4 --scenes . --size WxH --fps 30 --bpm 120` ends `QA: PASS` with 0 FIX and 0 NOT CHECKED.
- `qa.py selftest` (from the same folder) ends `SELFTEST: PASS (144 fixtures, 58 of 58 codes covered, 0 expected gaps)`: every Q code fires on its planted fault with the right item, time and value, and the template passes `run_all.py proof` and `full` at 1920x1080 and 1080x1920 (36 s on 2026-10-29; `--quick` skips the two full renders, 28 s).
- `uvx ruff format --check engine` is clean. `uvx ruff check engine kits` is not (184 findings on 2026-10-29: the template's `from engine import *` by design, plus lint debt in the kits), so compare its count before and after a change instead of expecting zero.
- `node C:\Code\GitHub\community\skillcheck\dist\cli.js lint .` is clean.

## Open

- Voice: the narrator is settled, Kokoro `af_heart` through `kokoro-ts` (Sagar's pick from `voice_samples.py`, 2026-10-29; model and four voices in `~/.cache/zoetrope/voices`, 327.6 MB, sha256 checked). Still open: Piper and the sherpa-onnx Kokoro build are written but untested, and nothing for them is downloaded; a second voice for two-host videos needs its own pick.
- Builder prompt cache: a 1 h cache TTL for the builder agent (research Z08) changes billing; not added, waiting on Sagar.
- Size cap: under `BUDGET_MB` a CRF encode spends only about 70 percent of the budget on heavy grain; a two-pass encode at the cap is not built.
