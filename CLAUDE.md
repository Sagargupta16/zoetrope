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
- Files are LF (`.gitattributes` sets `eol=lf`), unlike most Windows repos in this workspace. Check the bytes before assuming either way.
- Everything a build makes goes in `outputs/` (gitignored): videos, working folders, scratch scripts, history bundles.

## Loading and agents

- Claude Code reads agents from `~/.claude/agents/` recursively. The agents junction points at `agents/` only; pointed at the whole folder, every `.md` here would load as an agent.
- A new or renamed agent type does not appear in a session that was already running. There, launch a general-purpose agent and tell it to follow `agents/zoetrope-builder.md` or `agents/zoetrope-reviewer.md`.
- To prove a fresh load, run this in the Terminal panel (a Bash child cannot use the Desktop-managed Bedrock login):
  `claude -p "Without running any tools, answer two lines only. Line 1: the first 12 words of the description of the skill named zoetrope, or NOT FOUND. Line 2: the names of your custom subagent types, comma separated."`

## Engine gotchas (all hit on 2026-10-28)

- **Windows workers.** `run_all.py` work sits under `if __name__ == "__main__":`, and `render.py` imports `scenes` inside its functions, because each worker must set `E.W`, `E.H` before `scenes` reads them. A top-level import rendered a 9:16 piece at 16:9 size.
- **Fonts.** The cards name Mac fonts. `engine.py` lists Windows Arial first and raises on a missing font; before that, Pillow silently fell back to its 10 px default and every headline came out tiny.
- **9:16 text.** Size titles with `fit_size` against the short side (`min(W, H)`), or they overflow the safe area (Q201).
- **True peak.** The AAC encode adds 1 to 1.5 dB of true peak, so `audio.master` targets TP -3.0: -1.5 in the WAV measured -0.4 in the MP4. One stacked SFX hit can still fail Q802; it names the loudest moment, so lower that one gain.
- **Cue sync (Q902).** The detector takes the nearest strong onset with a rise over the previous 30 ms; the older one locked onto a whoosh's noisy rise and reported false lag.
- **Sample rates.** Every audio module runs at 44.1 kHz; only `audio.master` writes 48 kHz. Mixing 48 kHz voice sample by sample into a 44.1 kHz bed drifts the timing.
- **File size.** Film grain drives size: grain std 2.6 gave 140.2 MB for 60 s, std 1.6 at CRF 20 gave 35.9 MB. Q1002 notes bitrate over 12 Mb/s.
- **Windows locks.** A folder that is a process cwd or a watched folder cannot be moved or deleted. Move its contents instead, and keep shells out of `outputs/` subfolders.

## Process lessons

- **Fresh eyes find what self-checks miss.** Every builder reported its still-frame gates green; the reviewer still found a real visual fault in each first review. Keep the reviewer step even when the numbers pass.
- **Re-review after any change.** Two of the three late faults came from changes made after a REVIEW PASS (one: a line-height tweak grew a header and hid the top of a counted outline). List every change with its times and have a fresh reviewer check those frames and about 0.5 s either side.
- **Check holds before building.** `qa.py holds <scenario.md>` flagged 27 of the batch's 83 storyboard lines, including every one a builder later had to re-time.
- **Facts are checked in the main chat.** The builder cannot browse; put checked facts and sources into the scenario before the build.

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

- `bash setup.sh` ends `SETUP: PASS`.
- Smoke render: copy `engine/` into `outputs/smoke/`, run `run_all.py proof` and `run_all.py full`, then `qa.py check out.mp4 --scenes . --size 1920x1080 --fps 30 --bpm 120` ends `QA: PASS`. Repeat at 1080x1920 when text layout changed.
- `uvx ruff format --check engine` is clean. `uvx ruff check engine kits` is not (204 findings on 2026-10-28: the template's `from engine import *` by design, plus lint debt in the kits), so compare its count before and after a change instead of expecting zero.
- `node C:\Code\GitHub\community\skillcheck\dist\cli.js lint .` is clean.

## Open

- Voice: no text-to-speech yet. Natural-sounding candidates were researched on 2026-10-28 (local: Kokoro, Chatterbox, Pocket TTS; hosted: Polly generative, ElevenLabs, Gemini TTS); Sagar picks from samples before any is added. Until then, music plus captions.
