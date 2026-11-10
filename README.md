# Zoetrope

A Claude Code skill that plans, scripts, animates, scores and renders short
videos end to end with Python, Pillow, numpy and ffmpeg (invoke as
`/zoetrope`): 34 style cards, a builder and a fresh-eyes reviewer agent, and
measured QA gates. Renamed from video-producer on 2026-10-28.

**Private.** Adapted 2026-10-28 from a video-producer agent package that is
not ours to publish. This repo stays private: never make it public, and never
copy it into claude-home, a public marketplace, plugin, portfolio or post.

[![The 15 s zoetrope promo: five jobs, one prompt, 58 checks, a delivered file](docs/zoetrope-promo.gif)](docs/zoetrope-promo.mp4)

The promo above was made with the skill itself, through the same storyboard, proof, two fresh-eyes reviews and gates as any other video. The GIF is a silent 960 px preview; it links to [the MP4](docs/zoetrope-promo.mp4) with sound (15 s, 1920x1080, -14.1 LUFS, 5.1 MB).

## How a video gets made

![How zoetrope makes a video: main chat, builder agent, reviewer agent and gates, from brief to delivered file](docs/zoetrope-flow.svg)

1. **Brief and style.** The main chat asks at most three questions (purpose, length and aspect, audio) and offers two or three of the 34 style cards.
2. **Storyboard gate.** A table of time, beat, visuals, text and audio. `qa.py holds` checks every line's reading time first; nothing is built until you approve it.
3. **Proof.** The `zoetrope-builder` agent copies `engine/`, writes `scenes.py` (one function per scene, a pure `draw(t)`, a registry of every text and cue) and runs `run_all.py proof`. The proof gates run on drawn frames: first frame, text registry, a purity check across processes and a lint. The run ends with one `PROOF:` line and the review sheets.
4. **Proof review.** The `zoetrope-reviewer` agent sees only the scenario and the sheets: numbered key cells, frame strips and the whole film as lanes on one time axis. `REVIEW FIX` goes back to the builder; `REVIEW PASS` goes to you for approval.
5. **Render.** `run_all.py full` pipes every frame into one H.264 encode, synthesizes and masters the sound, muxes, and runs every gate on the file. A clean file ends with an `APPROVAL:` line and one `DELIVERED` line; a failing one becomes `<name>.rejected.mp4`.
6. **Final review and approval.** A fresh reviewer checks the encoded file. `qa.py approve` binds that review to the file's content hashes, and `qa.py verify` must say `SAME` before delivery. Any later change reopens review by itself: `qa.py diff --expect` names exactly the frames and sound that changed.

The diagram's source is `docs/zoetrope-flow.workflow.json` (an archify workflow with source line references at commit `88153b5`).

## What is in it

| Part | What it does |
| --- | --- |
| Style cards | 34 tested looks in `references/styles/`, from 15 s product ads and logo stings to explainers, history films, game parodies, sketchbooks and one 3D character short. Six come with working code in `kits/`. |
| Builder agent | Builds, renders and checks one video in its own context, so the engine and the logs stay out of the main chat (`agents/zoetrope-builder.md`). |
| Reviewer agent | Fresh eyes on the sheets and the file, never the builder's report; findings ranked P0, P1, P2 (`agents/zoetrope-reviewer.md`). |
| Drawing | `engine.py` helpers with one integer frame clock, `compile_schedule` for scenes, transitions and cues, nine pure transitions, seeded randomness. |
| Sound | Numpy instruments and 14 recorded ones (`sampler.py`: glockenspiel, marimba, harp, strings, flute, horn, timpani and percussion, all CC0), placed by their perceptual landmark (onset, peak, end or pad), a cue sheet and stems, and a 4x true-peak master to -14 LUFS. |
| 3D plates | A card can render its picture in Blender (Cycles on the GPU) as a plate that `scenes.py` reads like footage: real light, depth of field and a small character rig, under the same gates and approval (`plate3d.py`, `stage3d.py`, `references/plates.md`). `run_all.py` refuses a stale, unfinished or draft-quality plate. |
| Render | Frames pass from worker processes through shared memory into ffmpeg; no PNGs on disk. 45 fps on the template, BT.709 tagged. |
| QA gates | 60 coded checks (`qa.py check`): safe area, overlap, contrast, reading holds, WCAG 2.2 flashes, pops and freezes, true peak, what the narration says, cue sync on the stems, the mux, colour tags, size. |
| Approval | `approved/` keeps the hashes of what the reviewer passed; stale approval, regressions and changed frames are found mechanically. |
| Selftest | `qa.py selftest` plants a fault for every one of the 60 codes (158 fixtures) and proves each gate still catches it. |
| Narration | Offline narration in Kokoro's `af_heart` voice, one cached file per part with word times for cues (`voice.py`): respellings for names (`lexicon=`), exact pauses inside a line (`[pause 300ms]`), and lines held to their storyboard time (`fit=`). A speech model checks what it says (Q806 on the stem, Q807 in the file). See Requirements for the model files. |

## Run it

In a Claude Code session, ask for a video: `/zoetrope a 30 second launch video for <product>`. The skill does the rest and stops at the storyboard and proof for your approval.

By hand, from a working folder that holds a copy of the engine (`cp -r engine/. <folder>/`), each command run as `uv run --no-project --with-requirements requirements.txt python <command>`:

| Command | Result |
| --- | --- |
| `run_all.py proof --size 1920x1080` | Proof gates and review sheets; ends `PROOF: PASS`, `FIX` or `NOT CHECKED`. |
| `run_all.py full --size 1920x1080` | Frames, sound, master, mux and every gate; ends with `APPROVAL:` and `DELIVERED`. |
| `run_all.py audio` | Re-master and re-mux only, on the same picture. |
| `qa.py check out.mp4 --scenes . --size 1920x1080 --fps 30 --bpm 120` | Every gate on a finished file, one coded row each. |
| `qa.py speech narration/narration.json` | Q806 alone, right after narrating: each line transcribed by a speech model and held against its script. |
| `qa.py audiostrip out.mp4 --scenes .` | `review/audio.png`: spectrogram, loudness and cue timing for a reviewer who cannot hear. |
| `qa.py approve --review <reply>`, `qa.py diff --expect 2.5-5`, `qa.py verify` | Bind a review to the file, name what changed since, re-hash before delivery. |
| `qa.py selftest` | Every gate against its planted fault: `SELFTEST: PASS (158 fixtures, 60 of 60 codes covered, 0 expected gaps)`. |
| `plate3d.py render stage.py [--quality proof]`, `plate3d.py check --final` | Render a 3D plate for a build (half size for the proof, full for delivery), and ask whether every plate is current and final. |
| `python engine/cards.py check` | The style router in SKILL.md, its kit list and every card count against the cards' `**Spec:**` lines: `CARDS: OK (34 cards ...)`. |

Each gate code, what it measures and its status on failure are in [references/qa-gates.md](references/qa-gates.md); the engine's files and stages are in [references/engine.md](references/engine.md).

## Layout

This folder is the skill: the junction `~/.claude/skills/zoetrope` points here.

| Path | What |
| --- | --- |
| `SKILL.md` | The skill: brief, style pick, storyboard and proof approvals, delivery, and the style router linking every card. |
| `setup.sh` | First-use check of uv, ffmpeg with libx264, ffprobe, the pinned Pillow and numpy, and the default font. Safe to run again. |
| `engine/` | The Python engine as real files. Drawing: `engine.py` (helpers, frame clock, `compile_schedule`), `scenes.py` (the per-video template), `transitions.py`, `grain.py`, `fonts.py` (the free fonts the cards name, by family), `plate3d.py` and `stage3d.py` (3D plates rendered by Blender). Sound: `audio.py` (template bed, cue sheet and stems, the true-peak master), `synth.py` (instruments, landmark placement), `sampler.py` (recorded CC0 instruments, fetched on demand), `voice.py` and `voice_samples.py` (offline narration). Build: `render.py` (frames piped into ffmpeg through shared memory), `run_all.py` (`proof`, `full`, `audio` stages), `proof.py` (review sheets). Checks: `qa.py` (the gate CLI: `check`, `look`, `holds`, `purity`, `lint`, `owner`, `approve`, `diff`, `verify`, `calib`, `speech`, `audiostrip`, `selftest`) with its gate modules `qa_scan.py`, `qa_stack.py`, `qa_sync.py`, `qa_speech.py`, `qa_registry.py`, `qa_approve.py`, `qa_purity.py`, `qa_lint.py`, `qa_audiostrip.py`, `qa_selftest.py` and `qa_fixtures/`. `cards.py` reads the style cards' spec lines and checks the router against them. `contract.py` is what they all share (frame clock, the QA row, file formats, the Q code table). `kit_index.py` lists every helper. `requirements.txt` pins Pillow and numpy with hashes; `requirements-voice.in` lists the pins of the narration and speech check environments. The builder copies the folder into each video's working folder. |
| `references/` | Small topic files (playbook, engine, formats, voice, music, instruments, plates, mixing, beat sync, house rules, QA gates, pitfalls, delivery report, troubleshooting). |
| `references/styles/` | One file per style card (34) plus `families.md`, the intro each family shares. |
| `kits/` | Working code from finished builds for six cards, one folder each with a README of what to reuse. |
| `agents/zoetrope-builder.md` | The agent the skill launches for build, proof sheet, render and the measured QA gates. |
| `agents/zoetrope-reviewer.md` | The fresh-eyes reviewer the skill launches after the proof and after the render: REVIEW PASS or REVIEW FIX with coded findings. |
| `docs/` | The flow diagram (`zoetrope-flow.svg`) and its archify source, and the 15 s promo made with the skill (`zoetrope-promo.mp4`) with its GIF preview. These two are the only media committed: `.gitignore` lets `docs/*.mp4` and `docs/*.gif` through. |
| `CHANGELOG.md` | Every change made to the package, with the reason. |
| `LICENSE` | All rights reserved; see License below. |
| `outputs/` | Every video made with the skill, gitignored (the promo in `docs/` is the one exception). One folder per batch: `videos/` (the finished files), `builds/<nn-slug>/` (each working folder: scenes.py, scripts, proof.png), the scenarios and the build notes. |

Both agents load through their own junction, `~/.claude/agents/zoetrope`, which points at `agents/`: Claude Code reads agents only from `~/.claude/agents/` (recursively), and pointing that junction at this whole folder would make it try every `.md` here as an agent. claude-home ignores both junctions (`~/.claude/.gitignore`, `/skills/zoetrope` and `/agents/zoetrope`).

This folder is the private GitHub repo `Sagargupta16/zoetrope`. No copy of the original package is kept (deleted 2026-10-28); `CHANGELOG.md` is the record of what changed from it. Build lessons and repo rules for Claude are in `CLAUDE.md`.

## Requirements on this PC

- Python with the pinned Pillow and numpy: run scripts from a video's working folder with `uv run --no-project --with-requirements requirements.txt python ...`, nothing installed globally. Check the whole toolchain from Git Bash with `bash setup.sh` (from PowerShell: `& "C:\Program Files\Git\bin\bash.exe" C:/Code/GitHub/tools/kinograph/setup.sh`).
- ffmpeg 9.0.2 (Gyan full build, winget `Gyan.FFmpeg`, installed 2026-10-28): libx264, libaom-av1, libsvtav1, libvpx-vp9, libopus, ebur128 and loudnorm all present. On PATH for shells opened after the install; a Claude session started earlier needs a restart to see it.
- Fonts: the 14 free families 21 style cards name (Inter, Nunito, IBM Plex Mono and 11 more, SIL OFL) were downloaded on 2026-10-31 to `%USERPROFILE%\.cache\zoetrope\fonts`, outside the repo: 23 files, 6.8 MB, pinned to one google/fonts commit and checked by sha256. On a new machine, `python engine/fonts.py fetch` gets them again; `setup.sh` says when any is missing.
- Voice: the narrator is Kokoro-82M's `af_heart`, which Sagar picked from `voice_samples.py` on 2026-10-29. The model (the timestamped ONNX export, fp32, 325.5 MB) and four voices (0.5 MB each) were downloaded that day to `%USERPROFILE%\.cache\zoetrope\voices`, outside the repo, with their sha256 checked. Its engine runs in a side Python 3.13 environment that uv sets up on first use. On 2026-11-03 every English male voice (nine American, four British) and the four Hindi ones followed, 16 files of 0.5 MB from the same commit, each checked against the size and sha256 Hugging Face lists; their samples wait in `outputs/voice-samples-2026-11-03/` for a second voice to be picked. The built-in Windows voices stay as a robotic timing fallback. The sherpa-onnx Kokoro build and Piper were removed in 2.3.0: neither held a job the others did not, and neither was ever run.
- Speech check: faster-whisper's `base.en` model (147.8 MB, MIT), downloaded on 2026-11-03 to `%USERPROFILE%\.cache\zoetrope\asr`, pinned to one commit and checked by sha256; it runs on the CPU in a side Python 3.14 environment. On a new machine, `python engine/qa_speech.py fetch` gets it again; `setup.sh` says when it is missing.
- Recorded instruments: 14 instruments from Versilian Studios' VSCO 2 CE and VCSL (CC0 1.0), downloaded on 2026-11-10 to `%USERPROFILE%\.cache\zoetrope\instruments`, outside the repo: 210 files, 232.8 MB, pinned to one commit per library and checked by sha256, each decoded once beside its original (199 MiB). On a new machine, `python engine/sampler.py fetch <names>` gets what a score plays; `setup.sh` says when any is missing.
- 3D plates: Blender 5.2.3 LTS as a Python module (the `bpy` wheel, 324 MB, GPL-3.0-or-later), fetched on 2026-11-10 into the uv cache with `python engine/plate3d.py fetch`; it runs in a side Python 3.13 environment and renders with Cycles on the RTX 4070 Laptop GPU through OptiX (0.42 s a frame at proof quality, about 3 s at final, 1920x1080). Only a 3D card needs it. `stage3d.py` and every stage script call Blender's API, so they could only ever be shared under GPL-compatible terms; this repo is private, so nothing changes.

## License

All rights reserved; see [LICENSE](LICENSE). No permission is granted to copy, publish or redistribute any part of this repo. It is adapted from a third-party package whose rights are not ours, so it carries no open-source license.

Every change made to the package, with its reason, is in [CHANGELOG.md](CHANGELOG.md).

Ideas parked for later: 13 of the 34 style cards name only Mac system fonts (the agent maps each to an installed font per build); the series spec and `render.py` from `brand/linkedin` as a LinkedIn 4:5 style; `motion` and `social-post` descriptions do not yet point back here.
