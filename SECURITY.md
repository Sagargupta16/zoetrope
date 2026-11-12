# Security Policy

## What this plugin is

zoetrope ships one Markdown skill, two subagent definitions, style cards, kits and a Python engine that runs on your machine. The engine draws video frames with Pillow and numpy and calls your local ffmpeg. When you choose them, it also runs offline narration and a speech check in their own uv environments, and Blender for 3D plates. It has no server and makes no network calls of its own: uv downloads the pinned Python packages from PyPI on first use, and fonts, voice and speech models, recorded instruments and Blender are downloaded only when you run their `fetch` command, each pinned and checked by sha256.

Realistic concerns:

1. **Generated code runs locally.** For each video the builder agent writes `scenes.py` and a score and runs them with Python in your working folder. A bad or injected instruction could make it run something harmful.
2. **Skill content** can instruct Claude to run commands. A tampered skill, agent, card or kit could steer Claude toward harmful actions.
3. **Media parsing.** ffmpeg and Pillow parse every image, video and audio file you hand the skill. Treat files from strangers as untrusted.
4. **Model files.** Narration and the speech check load model files. Fetch them only with the engine's own `fetch` commands, which check each file's hash.
5. **Manifests** (`.claude-plugin/*.json`) could declare unexpected components if the repo were compromised.

## Reporting a vulnerability

Do not open a public issue or pull request. Report it privately through GitHub's private vulnerability reporting at https://github.com/Sagargupta16/zoetrope/security/advisories/new, with what you found, how to reproduce it, the impact and any suggested fix. Expect a first response within 7 days; the fix and the disclosure date are agreed with you after that.

## In scope

- A skill, agent or card instruction that reliably steers Claude past the user's own approval steps (the storyboard and proof gates) or past its safety checks.
- An engine path that executes code taken from a media file, a scenario file or a downloaded model.
- A gate that reports PASS on a file that breaks a viewer-safety limit it claims to check, such as the flash limit.
- Secrets committed to the repo.

## Out of scope

- Vulnerabilities in ffmpeg, Pillow, numpy, Blender, onnxruntime or uv themselves: report those to their projects.
- What a user chooses to put in their own videos.
