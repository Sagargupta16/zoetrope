# Kit: S-toy-studio-3d (Pip wants the star)

From the 2026-11-10 build, fourth version: 16.5 s, 1920x1080, 24 fps, a waltz at 120 BPM on recorded instruments. The picture is a 3D plate (`references/plates.md`). Proof plate 155 to 175 s (396 frames at half size); final plate 16.6 to 19.7 min over four renders (2.52 to 2.98 s a frame, Cycles on an RTX 4070 Laptop through OptiX, 64 paths a pixel, 67 MB of frames); `run_all.py full` drew and encoded the 396 frames in 6 to 14 s and made the score in 4 to 22 s (the first run decodes the instruments). 4.7 MB, -14.0 LUFS at -1.9 dBTP, `QA: PASS (50 checks, 0 FIX, 0 NOTE, 0 NOT CHECKED)`, all 13 cues within 5.7 ms on the stem and on their frame in the picture, the catch the loudest moment (momentary -9.1 LUFS, 1.1 LU over the next, the limiter taking 2.6 dB there).

Unlike the older kits, this one carries the registry (`text_items`, `CUES`, `KEY_TIMES`) and passes the gates as it is. Copied onto the engine in a fresh folder it refused to draw before a render (`PLATE: plates/main is not rendered`), passed the proof on the proof plate, and refused `full` on that plate.

| File | What to reuse |
|---|---|
| `beats.py` | The one timeline both worlds read: fps, size, scene lengths, every moment the picture and the sound hit (each a whole frame), how long each jump is in the air, the captions. Start a new film here |
| `stage.py` | `build(st)`: the studio sweep, three out-of-focus hills, the `Buddy`, a prop, and the thing it wants hung where the rig's raised hand will be at the catch (`home = S3.where(hand) + HOLD`), with its own small light and two screen tracks. `pose(t)`: one dict of pose values with defaults, one branch per scene that changes only what that scene needs, then the held prop on the hand and the camera focused on the head. Jumps land on their cue with `S3.jump(t, B.LAND, air)`; a prop that stops on a cue arrives moving, stops dead and rocks; the blink list and the happy eyes; the breath. `contact()` measures the hand-to-star gap frame by frame with no render: `python plate3d.py run stage.py contact` |
| `scenes.py` | `PLATE.frame(t)` as the canvas; `captions(t)` shared by `draw()` and `text_items()`; a caption placed once from a track (`PLATE.at("pip", 8.625)`) so it sits by the character and holds still; sparks that leave from the tracked star every frame, away from the character's face and lamp; the cue list built from `beats.py` |
| `score.py` | `render_audio(scenes, folder, fps)`, which `run_all.py` calls in place of the template score: a waltz bar (`waltz`), tunes and runs on `sampler.py` instruments, one distinct recorded sound per cue label (`cue_sounds`) placed on the SFX bus inside `synth.recording()`, a payoff made loud by held strings under its bells, and the `BED` and `CUE` gains |

To start a film from it: change `beats.py` first (the story's times), restage with stills (`python plate3d.py render stage.py --name look --quality proof --stills T,T`), place anything caught or held from the rig and run the contact measure, step through every jump and catch frame by frame, and keep one sound per cue in `score.py`. A change to `stage.py`, `beats.py` or the engine's `stage3d.py` makes the plate stale, and `run_all.py` says so.

How it got here (every version passed every measured gate):

- **v1** went to a fresh reviewer and came back REVIEW FIX with ten findings. Standing right under the star, Pip's head rose through it at the catch and the star then jumped 177 px to the hand in one frame. The failed jump took the head level with the star, so "Too high." was not true. Two hands raised either side of the star touched nothing. The catch was not the loudest moment. Poses switched across two cuts, and the eyes shut in one frame.
- **v2** fixed all ten in one round. Q902 then noted the crate's picture two frames before its thud: eased gently to rest, a stop has no frame.
- **v3** had the crate arrive still moving, stop dead and rock, and no NOTE was left. A second fresh reviewer found the catch still wrong: moved an arm's reach to the side by worked-out numbers, the hand was inside the star for seven frames before the catch and the star then shifted 46 px onto it. It also found a frown for three frames between the gasp and the smile, takeoffs that snapped, and the crate on screen for only four frames before it stopped.
- **v4** hangs the star where the rig's own hand will be, and measures it: the gap falls from 70.9 cm to 0.3 cm on the frame before the catch, is 0.1 cm from the catch on, is never negative, and the star moves 0.2 cm on the catch frame. The gasp runs into the smile, takeoffs have a push (`stage3d.hop`), and the camera has pulled back before the crate comes in. A third fresh reviewer returned REVIEW PASS on v4, and `qa.py approve` bound it to the file (`VERIFY: SAME`). These files are that build.

What that review still noted on v4 (one P1, eight P2), for whoever builds from this kit next:

- P1, fixed in the engine since: four landings (2.25, 4.25, 9.875, 11.25 s) drew no squash on their landing frame. `stage3d.hop` took a landing frame whose time fell a float rounding short of the boundary for a frame still in the air. With today's `stage3d.py` these files give the squash, so a plate rendered from them now differs from v4's at those frames.
- Also fixed in the engine since: the mouth line and the open mouth both showed for one frame (a dot on the line at 7.0 and 7.667 s), and the small hop and the bounces left the ground in one frame (a hop under half a second in the air now spends more of its crouch on the push).
- Still in these files: the sparks start one frame after the catch (`sparkles()` skips k = 0: use `0 <= k`); the antenna goes from straight to its full bend in one frame at 4.25, 7.75 and 11.25 s (multiply each `settle` by `min(1, (t - cue) / 0.084)`); the `shine` lamp sits 12 cm from the holding hand and turns it gold (move it to the star's far side); the crate is cut by the bottom edge on the end card (start that camera at y -5.9, z 1.45); the hop's landing at 2.25 s is soft in the mix (gain 0.4 to 0.55); the catch is the loudest moment by 0.6 LU on its own window, 1.1 LU with the landing (raise the held strings from 0.28 to about 0.34 and re-measure for 1.5 LU).

Other lessons:

- The first staging had the character at a fifth of the frame height in three scenes; the camera came in and the star came down.
- A glow of 1.2 on the star and a light in front of it washed the gold to white: the glow is 0.15 at rest, 2.0 for the flash, and the light sits under the star.
- Bells alone are all peak: at the gain that made the catch loudest, the limiter took 6.5 dB (Q805 FIX), and more plucked notes on top raised the peak again. Held violins and cellos under the bells made it the loudest moment with the limiter at 2.6 dB.
- A stretch of 0.22 on the reach jump lifted the hand to the star's height three frames early: that jump uses 0.1.
- Sustained strings, flute and horn swell in: they are placed by their first sample here as a bed, which is fine under a tune, but a string note that must hit a cue needs `align="pad"` (`references/instruments.md`).
- Nobody has listened to this score. Its balance was set by measurement.
- Not built: motion blur, a 9:16 staging (the same stage renders at 1080x1920 but crops the character in two scenes), a second character on screen.
