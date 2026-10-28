# The engine

Contract: one Python module per video, `scenes.py`, with `draw(t) -> PIL.Image`, pure and deterministic (seeded random: `rng(scene, element, frame)`, never one stream advanced frame to frame; no state across frames), and all timing from one `TIMELINE` (or a hand-written `SCHEDULE` dict). `run_all.py proof` checks it: the purity gate (Q1201) draws up to 34 frames (24 on the template) in order, reversed in a fresh `python -I` process and through the render pool, and needs identical digests; `qa.py lint` (Q1202 to Q1206) flags unseeded randomness, clocks and `hash()` of a str, module state written inside functions, redefined engine helpers, text drawn past the engine text helpers and colour literals inside functions. Proof first, then every frame piped into the encode, then the audio, the master, the mux and every QA gate.

The code is real files in the skill's `engine/` folder (`~/.claude/skills/zoetrope/engine/`). Copy the whole folder into the video's working folder (`cp -r engine/. outputs/{slug}/`, so `qa_fixtures/` comes along; `outputs/{slug}/` in the skill folder unless the user names one; `outputs/` is gitignored) and edit `scenes.py` there; never edit the skill's own copies for one video. Run every script from the working folder with `uv run --no-project --with-requirements requirements.txt python <script>` (Pillow and numpy pinned and hashed in `requirements.txt`; `setup.sh` in the skill folder checks the whole toolchain once).

| File | What it does |
|---|---|
| `engine.py` | Helpers shared by scenes.py: size and fps globals, easing, fonts (Windows Arial first; a missing font raises), colours, gradient, rounded rects, shadow, text (`tracking=` for letter spacing), wrap, supersample `finish`, and the text helpers every build needs: `text_box` (the box to report in the registry, same `tracking=`), `fit_size` (shrink to fit, never under 36 px), `text_outline`, `text_halo`. Timing: `scene_at` (decided on integer frames, nearest frame), `scenes_at` (both scenes and a 0 to 1 mix inside a transition window), `compile_schedule` with `Scene` and `Transition`, and the frame clock re-exported from contract.py (`frame_of`, `snap`, `stepped`, `sample_of`, `frame_sample`, `on_grid`). Also `rng(*keys)` (a numpy Generator seeded by what is drawn) and `spring`, `settle_time` (Remotion's spring and measureSpring) |
| `scenes.py` | The per-video template: palette, `LINES`, `TIMELINE` (scenes as durations, compiled by `compile_schedule` into `SCHEDULE`, `DURATION`, `CUTS`, `WINDOWS`, `CUES`), `BPM`, `draw(t)`, and the registry: `text_items(t)`, `CUES`, `CUE_LAG`, `KEY_TIMES` (`qa-gates.md`). One `layout(t)` drives both `draw()` and `text_items()`: every scene active at t (both inside a transition window, crossfaded by their share), each with its `title_state()`. The first scene starts fully drawn (frame 0 is the thumbnail), the last holds to the end (the end card), the others enter on their cut (one empty frame per changeover) |
| `transitions.py` | Scene transitions as pure `f(a, b, p)`: `crossfade`, `wipe`, `push`, `slide`, `iris`, `clock`, `blinds`, `dip`, `luma` (ideas from gl-transitions). p = 0 is a and p = 1 is b exactly; `MENU[name].flash_risk` is "check" for dip (run `qa.flash_window` over its window) |
| `grain.py` | `grain(img, t, std=1.6, hz=None, tiles=4, seed=0)`: film grain from 4 seeded 256 px tiles, picked and offset by whole pixels per step (default fps / 2: every grain held 2 frames), pure in t, on PIL images or float arrays. Call it after any weave shift; sizes in `formats.md` |
| `proof.py` | The review sheets: `contact_sheet` (`proof.png`), `key_sheet(findings=rows)` (`review_times.json` afresh, keeping `qa.py diff`'s changes; then `proof_keys.png`, `proof_strips.png`, `proof_gantt.png`) and `keys(rows=)` (the last three again from the file). `python proof.py keys [--size WxH --fps N]` redraws them at the size in `build.json`. Each frame is drawn once per run. A registry older than 2.2 (items without `s`) reads as none (`qa-gates.md`, gate 1) |
| `render.py` | `render_to_ffmpeg`: every frame drawn in a pool of spawned processes into a shared-memory ring and piped raw, in order, into one H.264 encode (`video.mp4`), writing each frame's digest and grey thumb (`frames.hash`, `thumbs.npy`); `scenes.STATIC` holds drawn once. `encode_cmd` is its ffmpeg argv. `render_parallel` and `render_frames` write PNG frames (rung b, debugging; `frames=range(a, b)` for one passage). scenes is imported inside the functions, because each Windows worker must set the frame size first |
| `run_all.py` | The stages: `proof`, `full [procs]`, `audio` (below). Every stage takes `--size WxH`, `--fps N` and `--ss N`, read at the top of the file before scenes is imported (every render worker runs the top again with the same argv); everything else is under `if __name__ == "__main__":` |
| `audio.py` | The template score (`bed`, `music`), `render_audio(scenes)` (mix_raw.wav, the sfx.wav stem, the cue sheet), `write_wav`, and `master`: one gain to -14 LUFS plus a 4x true-peak limiter at -2.0 dBTP, checked with ebur128 (`measure`), written at 48 kHz, with Q805 (`mixing.md`) |
| `synth.py` | The numpy instrument kit for scored pieces (kick, snare, hat, clap, bass, pad, pluck, riser, boom, whoosh, tick, reverb, sidechain `duck`), every sound seeded from its own arguments (`rng_for`, `noise`), `landmarks`, and the one placement path: `place` (onset, peak, end or pad on the cue), `put` (first sample), `put_peak`, recorded on the cue sheet inside `with synth.recording():` (`beat-sync.md`, `music.md`). `python synth.py demo.wav` writes a 4 s 120 BPM demo |
| `voice.py` | `synthesize` narrates lines offline into `narration.wav` and `narration.json` (one cached file per line), `word_cue`, `onset_offsets`, `slot`, `load_narration`, `ENGINES` (sapi tested; kokoro, kokoro-ts and piper untested), plus `dec`, `span`, `section_beats`, `duck_mix` (`voice.md`) |
| `voice_samples.py` | The same three lines with every ready voice engine and voice, for listening |
| `requirements-voice.in` | Optional text-to-speech pins per engine; not installed by setup.sh, not compiled |
| `qa.py` | The gate CLI and the core gates (`qa-gates.md`): `check`, `look`, `holds`, plus the subcommands the gate modules add (`purity`, `lint`, `owner`, `approve`, `diff`, `verify`, `calib`, `audiostrip`, `selftest`). Functions: `text_gates`, `registry_rows`, `proof_rows`, `min_hold(text, profile)`, `slot_budget`, `HOLD_PROFILES`, `flash_report`, `flash_window`, `flash_report_file` (Q601 to Q603 rows by default, `rows=False` the older list), `probe`, `loud`, `colour_round_trip`, `frame_grey`, `grid_rows`, `cut_times`, `snap_ok`, `review_entries`, `look`; `check`, `probe`, `look` and `frame_grey` take `ff=` |
| `qa_scan.py` | Gate 6 flashes to WCAG 2.2 (Q601 general, Q602 red, Q603 extended band) on the linear-light decode, the frame scans (Q1101 pops, Q1102 frozen runs, Q1103 unplanned cuts, Q1104 stalls) on the 192x108 grey decode, and Q1105 (the file against thumbs.npy); `flash_rows(None, fps, aspect, t0, lin=...)` for drawn frames, `scan_thumbs(folder)` on thumbs.npy |
| `qa_stack.py` | Q802 (true peak, its moment and the sounds there) and Q804 (the stack guard) from the cue sheet |
| `qa_sync.py` | Q902 (cue sync on the SFX stem), Q903 (the mux), Q906 (`qa.py calib`); `cue_offsets(ctx)` for the audio strip |
| `qa_registry.py` | The text recorder: Q204, Q205, Q206, Q208, Q209 (what draw(t) paints against what text_items(t) reports), in `qa.py check` and `run_all.py proof`; `--registry-procs N` |
| `qa_purity.py` | The purity gate Q1201 (`qa.py purity [--n 16] [--t T] [--grid S]`): on a FIX the worst frame, the pixels that differ and the frame that poisons it |
| `qa_lint.py` | Static checks of scenes.py and the modules it imports from its folder (`qa.py lint [scenes.py] [--all]`): Q1202 FIX, Q1203 to Q1206 NOTE, Q904 and Q905; pragmas `# zoetrope: state-ok`, `rng-ok`, `shadow-ok`, `text-ok`, `colour-ok`. `qa.py owner --t S` or `--traceback FILE` names the scene function(s) a finding belongs to |
| `qa_approve.py` | `approve`, `diff`, `verify` and the approval rows Q1301 to Q1304; `approved/` holds the approved build (approval.json, frames.hash, thumbs.npy, qa.json, mix_raw.hash, mix_raw.wav, src/) |
| `qa_audiostrip.py` | `qa.py audiostrip`: `review/audio.png` (spectrogram, cues, loudness, true peak on one axis) |
| `qa_selftest.py`, `qa_fixtures/` | `qa.py selftest [--quick] [--only CODE[,CODE]] [--keep]`: 73 cases in `qa_fixtures/` (text, registry, source, files, sound, scans, approval; `fake.py` and `media.py` make the inputs) plus the template controls; each case says with `want(code, status, item, t, tol, metric, ...)` what its gate must report, and `EXPECTED_GAPS` in qa_selftest.py names any code no fixture can reach. Copy the engine with `cp -r engine/. <folder>/` so `qa_fixtures/` comes along (`qa-gates.md`) |
| `contract.py` | What every module shares and nothing else defines: the frame clock (`frame_of` nearest frame, `snap`, `sample_of`, `frame_sample`, `stepped`, `on_grid`, `whole_frame_beat`), the QA row (`Row`, `row`, `not_checked`, `exit_code`, `line`, `summary`), the Q code table `CODES`, the files a build writes and their readers (below), the colour chain (`COLOR_VF`, `COLOR_FLAGS`, `DECODE_709`, `DECODE_LINEAR`), `AAC_ARGS` and `mux_cmd` (the one mux), `find_ffmpeg`, and `Ctx`, which decodes the file once for every gate module. It imports neither scenes nor engine, so anything can import it first |
| `kit_index.py` | `python kit_index.py [folder ...]`: every public function, class and namedtuple in the engine (gate internals left out) and the kits, with its signature, first docstring line and file:line, from the ast alone (534 helpers on 2026-10-29); `python kit_index.py show <name>` (or `g04:text`) prints one. Read it before writing a helper |
| `requirements.txt` | Pillow 13.0.0 and numpy 2.5.4, pinned with hashes (`requirements.in` is the input to `uv pip compile --generate-hashes --universal`) |

All audio modules run at 44.1 kHz; `audio.master` resamples the final mix to 48 kHz.

**Before a build**
- Everything runs in one working folder on this machine: proof sheets, frames, synthesized audio, local ffmpeg.
- `run_all.py` finds ffmpeg on PATH, else in `/opt/homebrew/bin` or `/usr/local/bin`, and prints `NO_FFMPEG` when there is none (`troubleshooting.md`).
- Size: `run_all.py <stage> --size WxH --fps N --ss N` sets `E.W, E.H, E.FPS, E.SS` before scenes is imported, so a 9:16 build needs no edit; a scenes.py that sets its own size wins, and run_all says so. Every stage writes `build.json` (`{"w", "h", "fps", "ss"}`, the size the build really uses), which `qa.py check` (for SS), `purity`, `lint`, `owner`, `approve`, `diff` and `proof.py keys` read instead of guessing. Set the size by hand only in a runner of your own: `import engine as E; E.W, E.H, E.FPS, E.SS = 1920, 1080, 30, 1` before `import scenes`. Use `SS = 2` for thin lines and small text (4x the pixels, slower).

## scenes.py

Replace the palette, `LINES` and the draw functions per video. Keep `TIMELINE`, `draw(t)` and the purity rule. Lengthen a scene in `TIMELINE` and every later cut, window and scene cue moves with it.

- **Transitions.** A `Transition(kind, dur)` between two scenes makes a window where both are drawn. In straddle mode (the default) the cut stays where the durations put it, on the bar line, and the window spans it; with `mode="overlap"` the next scene starts `dur` early, as in Remotion (60 + 60 - 15 = 105 frames). `compile_schedule` raises on a transition under 2 frames (no frame of it would blend) or over half the shorter scene, a scene shorter than half a frame, and a scene cue at or past its scene's end (put that cue on the next scene at 0). Durations may be in beats (`bpm=`) or a function (`lambda: max(hold, measured)`); floats are read as the nearest fraction with a denominator up to 10**6, so `5 / 30` is exactly 5 frames.
- Draw a window with `scenes_at(t, SCHEDULE)` and a `transitions.py` function; another kind than a crossfade needs its own shares in `layout()`, or the registry drifts. Keep text out of the window (its scene's solo span), or Q203 fires; a window under 0.5 s then leaves a Q207 gap, so put the incoming text in another place (`qa-gates.md`, gate 2).
- **Voice piece:** each scene's length is its narrated line's slot (`voice.md`; `N["lines"][i]["slot"]["duration"]`), cues from `C.snap(voice.word_cue(N, word), FPS)`. scenes.py reads `narration.json` and never calls `voice.synthesize`: every render worker imports scenes.py.
- **Music piece:** durations in beats on the grid (`bpm=BPM`); hard cuts on bar lines (`beat-sync.md`).
- **Holds that never move:** `STATIC = [(t0, t1), ...]` (seconds, end exclusive like SCHEDULE) are drawn once when their sampled frames match (both ends, the middle, about one a second): a 10 s hold in a 20 s piece rendered in 8.7 s against 13.3 s, byte-identical. A change between the samples is not seen, so declare only frames that truly hold; a moving span prints a warning and is drawn in full. Q1102 does not read STATIC.

**Springs.** `spring(t, stiffness, damping, mass)` is Remotion's spring: damping at or over critical moves as critically damped, so `damping=200` is a fast ease with no bounce. `settle_time(...)` gives the seconds until it is at rest (Remotion's measureSpring, 0.005 held for 20 frames). Report a springing item at rest only from then.

## Stages: proof, full, audio

- `python run_all.py proof`: the proof gates (Q501 on frame 0, the registry gates, the text recorder, purity, lint), then `proof.png`, `proof_keys.png`, `proof_gantt.png` (`proof_strips.png` when an entry asks for one), `review_times.json` and `qa_proof.json`. It prints every row and ends `PROOF: PASS (23 checks, 0 FIX, 0 NOTE, 0 NOT CHECKED)` on the template; exit 1 on any FIX, 2 on any NOT CHECKED. Show `proof.png` and `proof_keys.png`, get approval, then render.
- `python run_all.py full [procs] [--budget-mb N] [--keep-frames [--redraw T0-T1]]`: deletes the old outputs first (out.mp4, video.mp4, frames.hash, thumbs.npy, the mixes, the cue sheet, every `*.rejected.mp4` and `*.unchecked.mp4`), renders `video.mp4`, then makes the audio (`audio.render_audio`), masters it, muxes with `contract.mux_cmd`, runs the true-peak loop, the frame scans on thumbs.npy and `qa.check`, and redraws the review sheets with the verdict's rows.
- `python run_all.py audio`: the same without drawing a frame, on the same `video.mp4` (10 s against 20 s for the template's full build, video.mp4 byte-identical). It refuses a `video.mp4` drawn at another size, fps or SS, or from another state of scenes.py: it redraws the first, middle and last frame of every scene (at most 12) and compares them with frames.hash. Give it the same flags as `full`.

How each run ends (the template, 2026-10-29):

```
master: ceiling -2.00 dBTP, mix.wav -14.0 LUFS at -2.00 dBTP (Q805 PASS) -> out.mp4 -14.0 LUFS at -1.90 dBTP
...
QA: PASS (49 checks, 0 FIX, 0 NOTE, 0 NOT CHECKED)
APPROVAL: none yet -> final review, then qa.py approve
DELIVERED C:/.../out.mp4 (0.4 MB, 7.50 s, -14.0 LUFS, -1.9 dBTP)
```

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
| `review_times.json`, `qa_proof.json`, `qa.json` | proof, full, `qa.py check --json` | Moments to review, and the rows (`qa-gates.md`) |
| `proof*.png`, `review/` | proof.py, `qa.py look`, `diff`, `audiostrip` | The sheets, look copies, triptychs and `review/audio.png` |
| `approved/` | `qa.py approve` | The approved build |

## Audio

`run_all.py full` and `audio` call `audio.render_audio(scenes)` (the template score: DURATION, BPM, and the cuts from `CUTS` or every SCHEDULE start; each cut hit carries its CUES label) and then `audio.master(C.MIX_RAW, C.MIX)`. Cuts get a whoosh whose apex leads the cut by 80 ms and a hit on it; a kick within 3 frames of a cut is left out; music ducks about 8 dB under the voice. For a scored piece build the bed with `synth.py` (`music.md`) inside `with synth.recording() as sheet:` and write the sheet and the stems the way `render_audio` does, then replace the `render_audio` call in `run_all.deliver` with your score: Q902 and Q804 measure from that sheet. Voice comes from `voice.synthesize` (`voice.md`): mix `voice.dec("narration/narration.wav")` with `voice.duck_mix`.

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

**Rung c, GIF preview for Slack (15 s max, 960 px wide max, 15 fps):**
```
ffmpeg -y -i out.mp4 -vf "fps=15,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer" preview.gif
```
(Use the frames or any rung's output as input; GIF has no audio.) Tested locally with palettegen on the frame sequence: works.
