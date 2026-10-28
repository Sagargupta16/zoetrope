# Zoetrope

A Claude Code skill that plans, scripts, animates, scores and renders short
videos end to end with Python, Pillow, numpy and ffmpeg (invoke as
`/zoetrope`): 33 style cards, a builder and a fresh-eyes reviewer agent, and
measured QA gates. Renamed from video-producer on 2026-10-28.

**Private.** Adapted 2026-10-28 from a video-producer agent package that is
not ours to publish. This repo stays private: never make it public, and never
copy it into claude-home, a public marketplace, plugin, portfolio or post.

## Layout

This folder is the skill: the junction `~/.claude/skills/zoetrope` points here.

| Path | What |
| --- | --- |
| `SKILL.md` | The skill: brief, style pick, storyboard and proof approvals, delivery, and the style router linking every card. |
| `setup.sh` | First-use check of uv, ffmpeg with libx264, ffprobe, the pinned Pillow and numpy, and the default font. Safe to run again. |
| `engine/` | The Python engine as real files: `engine.py`, `scenes.py`, `proof.py`, `render.py`, `audio.py`, `synth.py`, `voice.py`, `qa.py` (also the `check`, `look` and `holds` CLI), `run_all.py`, and `requirements.txt` (pinned, hashed). The builder copies the folder into each video's working folder. |
| `references/` | Small topic files (playbook, engine, formats, voice, music, mixing, beat sync, house rules, QA gates, pitfalls, delivery report, troubleshooting). |
| `references/styles/` | One file per style card (33) plus `families.md`, the intro each family shares. |
| `kits/` | Working code from approved builds for five cards, one folder each with a README of what to reuse. |
| `agents/zoetrope-builder.md` | The agent the skill launches for build, proof sheet, render and the measured QA gates. |
| `agents/zoetrope-reviewer.md` | The fresh-eyes reviewer the skill launches after the proof and after the render: REVIEW PASS or REVIEW FIX with coded findings. |
| `CHANGELOG.md` | Every change made to the package, with the reason. |
| `outputs/` | Every video made with the skill, gitignored. One folder per batch: `videos/` (the finished files), `builds/<nn-slug>/` (each working folder: scenes.py, scripts, proof.png), the scenarios and the build notes. |

Both agents load through their own junction, `~/.claude/agents/zoetrope`, which points at `agents/`: Claude Code reads agents only from `~/.claude/agents/` (recursively), and pointing that junction at this whole folder would make it try every `.md` here as an agent. claude-home ignores both junctions (`~/.claude/.gitignore`, `/skills/zoetrope` and `/agents/zoetrope`).

This folder is the private GitHub repo `Sagargupta16/zoetrope`. No copy of the original package is kept (deleted 2026-10-28); `CHANGELOG.md` is the record of what changed from it. Build lessons and repo rules for Claude are in `CLAUDE.md`.

## Requirements on this PC

- Python with the pinned Pillow and numpy: run scripts from a video's working folder with `uv run --no-project --with-requirements requirements.txt python ...`, nothing installed globally. Check the whole toolchain from Git Bash with `bash setup.sh` (from PowerShell: `& "C:\Program Files\Git\bin\bash.exe" C:/Code/GitHub/tools/zoetrope/setup.sh`).
- ffmpeg 9.0.2 (Gyan full build, winget `Gyan.FFmpeg`, installed 2026-10-28): libx264, libaom-av1, libsvtav1, libvpx-vp9, libopus, ebur128 and loudnorm all present. On PATH for shells opened after the install; a Claude session started earlier needs a restart to see it.
- Voice: no text-to-speech is wired up yet (a natural-sounding one is being chosen), so videos are music plus captions.

Every change made to the package, with its reason, is in [CHANGELOG.md](CHANGELOG.md).

Ideas parked for later: the style cards still name Mac fonts (the agent maps each to an installed font per build); the series spec and `render.py` from `brand/linkedin` as a LinkedIn 4:5 style; `motion` and `social-post` descriptions do not yet point back here.
