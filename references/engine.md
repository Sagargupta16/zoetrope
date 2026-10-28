# The engine

Contract: one Python module per video, `scenes.py`, `draw(t) -> PIL.Image`, pure and deterministic (seeded random, no state across frames), all timing from one `SCHEDULE` dict. Proof frames first, then every frame at 30 fps, then the encode ladder, then QA.

The code is real files in the skill's `engine/` folder (`~/.claude/skills/zoetrope/engine/`). Copy the whole folder into the video's working folder (`outputs/{slug}/` in the skill folder unless the user names one; `outputs/` is gitignored) and edit `scenes.py` there; never edit the skill's own copies for one video. Run every script from the working folder with `uv run --no-project --with-requirements requirements.txt python <script>` (Pillow and numpy pinned and hashed in `requirements.txt`; `setup.sh` in the skill folder checks the whole toolchain once).

| File | What it does |
|---|---|
| `engine.py` | Helpers shared by scenes.py: size and fps globals, easing functions, fonts (Windows Arial first; a missing font raises), colours, gradient, rounded rects, shadow, text, wrap, supersample `finish`, `scene_at`, `crossfade`, and the text helpers every build needs: `text_box` (the box to report in the registry), `fit_size` (shrink to fit, never under 36 px), `text_outline`, `text_halo` (soft dark halo for text over pictures) |
| `scenes.py` | The per-video template: palette, `LINES`, `SCHEDULE`, `DURATION`, `BPM`, `draw(t)`, and the registry: `text_items(t)` (every text drawn at t, with box, colour, alpha, size, `texture` flag), `CUES` (every sound the picture must hit), `CUE_LAG`, `KEY_TIMES`. One `title_state()` drives both `draw()` and `text_items()`, so the registry cannot drift from the picture. The first scene starts fully drawn (frame 0 is the thumbnail) |
| `proof.py` | `contact_sheet` (`proof.png`: up to 12 stills over every scene, midpoints first) and `key_sheet` (`proof_keys.png` plus `review_times.json`: both sides of every cut, every caption at rest from the registry, and `KEY_TIMES`) |
| `render.py` | `render_frames` (one process) and `render_parallel` (several processes; `frames=range(a, b)` re-renders one passage, `skip_existing` resumes); PNGs at compress level 1. scenes is imported inside the functions because each Windows worker must set the frame size first |
| `audio.py` | Simple bed and SFX on a BPM grid (`music`), `write_wav`, and `master`: limiter plus two-pass loudnorm to -14 LUFS, TP -3.0 (the AAC encode adds 1 to 1.5 dB of true peak, so -1.5 in the WAV landed at -0.4 in the MP4), written at 48 kHz |
| `synth.py` | The full numpy instrument kit for scored pieces (kick, snare, hat, clap, bass, pad, pluck, riser, boom, whoosh, tick, reverb, sidechain `duck`, `put`, `put_peak`); `python synth.py demo.wav` writes a 4 s 120 BPM demo |
| `voice.py` | `dec` and `span` to decode and measure voice files, `section_beats` to size a voiced section, `duck_mix` to duck the bed under speech |
| `qa.py` | The gates in `qa-gates.md` as functions (`contact_sheet`, `text_box`, `inside`, `overlap`, `region_contrast`, `ring_bg`, `min_hold`, `first_frame`, `flash_report`, `flash_window` for one passage on drawn frames, `flash_report_file`, `probe`, `loud`, `snap_ok`, `text_gates` and `cue_gates` from the registry). CLI: `qa.py check <video> --scenes . --size WxH --fps N [--bpm N]` (every gate, coded rows, exit 1 on any FIX), `qa.py look <video> [--times ...]` (small frame copies and `review/look.jpg`), `qa.py holds <scenario.md>` (storyboard reading-time check before any build) |
| `run_all.py` | `python run_all.py proof` (`proof.png`, `proof_keys.png`, `review_times.json`), then after approval `python run_all.py full [procs]`: frames in parallel, audio, master, H.264 at `CRF` (18, or 20 for grainy styles) to `OUT`. Deletes the old output first and prints a `wrote` line per output. Its work sits under `if __name__ == "__main__":`, which Windows render workers need |
| `requirements.txt` | Pillow 13.0.0 and numpy 2.5.4, pinned with hashes (`requirements.in` is the input to `uv pip compile --generate-hashes --universal`) |

All audio modules run at 44.1 kHz; `audio.master` resamples the final mix to 48 kHz.

**Before a build**
- Everything runs in one working folder on this machine: proof sheet, frames, synthesized audio, local ffmpeg.
- Check first: `import shutil; shutil.which("ffmpeg")` (on a Mac also try `/opt/homebrew/bin/ffmpeg`, `/usr/local/bin/ffmpeg`).
- Set size once at the top of each runner: `import engine as E; E.W, E.H, E.FPS, E.SS = 1920, 1080, 30, 1` BEFORE `import scenes`. Use `SS = 2` for thin lines and small text (renders 4x the pixels, slower).

The original package ran this code end to end (2 s, 640x360, device Python plus ffmpeg: proof sheet, 60 frames, audio, H.264 + AAC, ffprobe confirmed h264 yuv420p + aac). On Windows on 2026-10-28 it ran at 1920x1080 at about 62 ms per frame.

## scenes.py

Replace palette, `LINES` and the draw functions per video. Keep `SCHEDULE`, `DURATION`, `draw(t)` and the purity rule.

For a voiceover piece, fill `SCHEDULE` from the measured voice lengths (`playbook.md`, timing math; `mixing.md`, voice placement). For a music piece, fill it from the grid: `bar = 4 * 60 / BPM`, scene n runs `(n * bar, (n + 1) * bar)`.

## Proof and render

Show the sheet: write `proof.png`, then open it in the OS viewer. Run `proof.contact_sheet("proof.png")`, show it, get approval, then `render.render_frames("frames")`. Render in chunks if a single call may time out (loop `range(a, b)` over frame indexes per call; frames are independent because `draw` is pure).

## Audio

Usage: `audio.write_wav("mix_raw.wav", audio.music(DURATION, 120, cuts=[...], voice_spans=[(a, b)]), voice=voice_array)`, then `audio.master("mix_raw.wav", "mix.wav")`. Voice comes from one text-to-speech file per line (`voice.md`; decode with `voice.dec("v.mp3")`, 44.1 kHz mono float). Cuts get a whoosh just before and a hit on the cut. Music ducks about 8 dB under the voice. Place one SFX per cut at most; do not stack. For a scored piece build the bed with `synth.py` instead (`music.md`).

## Encode ladder (always say which rung was used and why)

Master loudness to -14 LUFS integrated, true peak at or below -1 dBTP: `audio.master` measures, then applies (two pass). The same thing by hand:
```
ffmpeg -hide_banner -i mix_raw.wav -af loudnorm=I=-14:TP=-3.0:LRA=11:print_format=json -f null -
ffmpeg -y -i mix_raw.wav -af loudnorm=I=-14:TP=-3.0:LRA=11:measured_I=<in>:measured_TP=<in>:measured_LRA=<in>:measured_thresh=<in>:linear=true -ar 48000 mix.wav
```
(`<in>` = values printed by pass 1. Verify afterward with `qa.loud("out.mp4")`, or `ffmpeg -i out.mp4 -af ebur128=peak=true -f null -` and read I and Peak.)

**Rung a, device ffmpeg exists (best, plays everywhere):**
```
ffmpeg -y -framerate 30 -i frames/f%05d.png -i mix.wav -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -r 30 -c:a aac -b:a 192k -shortest -movflags +faststart out.mp4
```
Silent piece: drop `-i mix.wav` and the audio flags. `run_all.py` runs this rung from Python with `subprocess.run([...], check=True, capture_output=True)`.

**Rung b, ffmpeg without libx264.** Same `frames/` and `mix.wav`, then:
```
ffmpeg -y -framerate 30 -i frames/f%05d.png -i mix.wav -c:v libaom-av1 -crf 30 -b:v 0 -cpu-used 6 -pix_fmt yuv420p -c:a aac -b:a 192k -shortest -movflags +faststart out_av1.mp4
ffmpeg -y -framerate 30 -i frames/f%05d.png -i mix.wav -c:v libvpx-vp9 -crf 32 -b:v 0 -pix_fmt yuv420p -c:a libopus -b:a 160k -shortest out.webm
```
Use AV1 MP4 if the encoder exists (plays in Chrome and Slack web; may not play in older QuickTime), else VP9 WebM. Check `ffmpeg -encoders | grep -E "av1|vp9"` first; encoder names differ per build (both commands above ran cleanly on a Mac ffmpeg build).

**Rung c, GIF preview for Slack (15 s max, 960 px wide max, 15 fps):**
```
ffmpeg -y -i out.mp4 -vf "fps=15,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer" preview.gif
```
(Use the frames or any rung's output as input; GIF has no audio.) Tested locally with palettegen on the frame sequence: works.
