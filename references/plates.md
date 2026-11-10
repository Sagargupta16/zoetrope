# 3D plates

True 3D for a video, kept apart from the 2D engine. Blender renders the 3D picture once, one image per frame (the plate), in its own uv environment; `scenes.py` then reads those frames like footage and draws the type and the graphics over them. `draw(t)` stays pure, so every gate, the proof sheets and the approval work as they do for a 2D build. Read this for a card whose Spec names a 3D kit (S-toy-studio-3d) or when a brief needs a real 3D shot; for anything else the 2D engine is faster.

## What it needs

- **Blender as a Python module**: `python plate3d.py fetch` once per machine (bpy 5.2.3 LTS, 324 MB, GPL-3.0-or-later, into the uv cache; nothing is installed globally). `python plate3d.py missing` says whether it is there, and `setup.sh` prints the same as a note.
- **A GPU** for a sensible wait. Measured on an RTX 4070 Laptop (OptiX), 1920x1080: proof quality 0.42 s a frame (396 frames in 168 s), final quality 2.6 to 3.0 s a frame over a whole plate (17 to 20 minutes for 396 frames; a single still takes 3.3 to 3.6 s, the first one more). Without a GPU Cycles falls back to the CPU and is many times slower: say so before starting.
- Nothing else is downloaded. Every shape is built in code; we bring in no models, textures or HDRIs.

## Files in the working folder

| File | Runs in | What it is |
|---|---|---|
| `beats.py` | both | The times both worlds share: fps, size, the scene lengths, every moment the picture and the sound hit, the captions. Plain numbers and no imports |
| `stage.py` | Blender's Python | The 3D scene: `build(st)` makes the set, the lights, the camera and the characters with `stage3d.py`, and returns `pose(t)` |
| `scenes.py` | the engine | `PLATE = plate3d.Plate("main")`, then `PLATE.frame(t)` in `draw(t)`, with the captions, the registry and `CUES` as in any build |
| `score.py` | the engine | `render_audio(scenes, folder=".", fps=None)`: `run_all.py` uses it instead of the template score when the file defines it |

`scenes.py` never imports `stage.py` or `stage3d.py` (they need Blender), and `stage.py` never imports the engine (it needs Pillow). Both import `beats.py`.

## Order of work

1. **Stills first.** `python plate3d.py render stage.py --quality proof --stills 0,2.5,6` renders only those moments (under a second each). Tile them, look, fix the staging and the light. Do this until every scene reads.
2. **Proof plate.** `python plate3d.py render stage.py --quality proof`: every frame at half size. Then `python run_all.py proof --fps N` as usual. The proof sheets show the real 3D picture.
3. **Approval** of the sheet, as for any build.
4. **Final plate.** `python plate3d.py render stage.py` (no `--quality`). Run it in the background: a 16.5 s film at 24 fps is about 20 minutes. A stopped render picks up where it stopped.
5. **Full.** `python run_all.py full --fps N`, then the final review.

`run_all.py proof` and `full` ask `plate3d.check()` before they draw, and stop with a `PLATE:` line and the command that clears it when a plate that `scenes.py` names is not rendered, is being rendered, is older than its stage script (or `beats.py`, or `stage3d.py`), has a frame missing, or, for `full`, is still of proof quality. Plates under other names (stills to look at) are left alone. A draft plate cannot reach a delivered file. `python plate3d.py info` lists the plates of a build.

## stage3d.py

`python kit_index.py show Stage` (or `Buddy`, `jump`, `settle`) prints the source with its docstrings; the `st.` helpers are methods of `Stage`.

| Need | Helper |
|---|---|
| Set | `st.backdrop(color)` (a floor that curves up into a wall: no horizon), `st.sky(color, strength)` |
| Light | `st.studio()` (key, fill, rim and a wash on the wall), `st.lamp()` (one soft box), `st.glow()` (a small light inside something that shines) |
| Surfaces | `st.mat(name, "#hex", kind)`: clay, toy, plastic, matte, metal, eye, glass; `glow=` lights it from inside |
| Shapes | `st.ball`, `st.pill`, `st.box` (rounded edges), `st.cyl` (and cones), `st.ring`, `st.slab(outline)` with `star()`, `st.tube(points)` with `bend()`, `st.text` (solid type), `st.empty` |
| Camera | `st.camera(at, look, lens, fstop, focus)`: call it in `pose(t)` to move it; `aim()` |
| Character | `st.buddy(name, color)` returns a `Buddy`; `buddy.pose(...)` sets its place, height, turn, lean, squash, eyes, blink, mouth, arms and feet |
| Motion | `prog`, `lerp`, `ease_in`, `ease_out`, `ease_in_out`, `ease_back`, `settle` (the wobble after a stop), `squash`, `hop`, `jump` (a hop that lands on a given second), `walk` |
| 2D over 3D | `st.track(name, object)` records where it is on screen each frame; `PLATE.at(name, t)` in `scenes.py` gives the canvas point, so a caption, an arrow or a spark follows a 3D object |
| Held props | `where(object)`: its place in the world after everything `pose(t)` has set so far |
| Measuring | `python plate3d.py run stage.py <args>` runs the stage script in Blender's Python with your own arguments and no render: for a check on the rig, like the kit's `contact` |

Units are metres and Z is up. A character faces -Y, toward a camera at negative Y; sides in `Buddy.pose` are the camera's.

## Rules

- **pose(t) is pure.** It sets everything for time t from t alone, as `draw(t)` does. No state from the frame before, no clock, no unseeded random. Any frame then renders alone and a stopped render resumes.
- **A plate is rendered once.** Rendering the same frame again gives the same picture but not the same bytes: three frames of the pilot rendered twice differed by 0.11 of 255 on average and 9 at most (the GPU path tracer and the denoiser are not bit-exact). To the eye that is nothing; to the approval it is a changed frame (Q1301). So never render an approved plate again unless the stage changed, and expect a re-review of every scene when it does.
- **One render per plate.** `render` holds `plates/<name>/render.lock` while it writes, and a second render of that plate is refused; a frame is written beside its place and moved in when whole, so a killed render leaves no half frame. `--stills` on a plate that is already complete replaces nothing unless the stage or the quality changed, and then it replaces everything: use `--name look` for stills of another quality.
- **One timeline.** Every time in `stage.py` comes from `beats.py`. A landing is `S3.jump(t, B.LAND, air)` so the feet meet the floor on the frame the thud is on, and the same constant is a `CUES` entry and a placed sound.
- **Moments sit on frames.** At 24 fps every time in `beats.py` is a multiple of 1/24 s (Q904 notes one that is not).
- **Type stays in 2D.** Captions and titles go through the engine's text helpers in `scenes.py`, so the text gates measure them. Solid type in the plate (`st.text`) is scenery: report it in `text_items(t)` with `texture=True`, or as a normal item when the viewer must read it.
- **Sizes agree.** The stage script's `size`, `fps` and `dur` are the video's (`beats.py` holds them). `Plate` refuses a plate of another shape, and `PLATE.need(DURATION)` one that is too short. A plate at half the video's fps is allowed: each frame is held for two video frames, from the frame its pose is for (on twos), right for a stop-motion look with a still camera. Not tried in a delivered build yet.
- **Colour.** Give materials the card's hex colours: the scene is shown through the Khronos PBR Neutral view, which keeps hue and saturation (Blender's default AgX turned the same palette pastel, 2026-11-10). A strong `glow=` washes a colour to white: keep it under 0.5 at rest and raise it only for a flash.

## What makes it look good (from the first build)

- **Light.** The key is a 2.2 m soft box: a bigger one flattened every shadow. The wash on the wall keeps the background a clean colour from any camera side; without it the wall went dull grey-brown.
- **The subject is big.** At a key moment the character fills a third of the frame height or more. The first staging had it at a fifth in three scenes. Bring the camera in or lower what it reaches for.
- **Lens and focus.** 35 to 40 mm for a wide shot, 50 to 60 for a close one. `fstop` 2.2 to 4 with the focus on the character's head throws the set soft and gives depth at once.
- **A low camera makes a small thing far away.** The failed jump is shot from 0.4 m up, tilting with the jump.
- **Acting, in this order:** the eyes move first, then the body. Anticipation before every jump (the crouch), stretch in the air, squash on landing, then `settle` on the antenna or anything loose. A blink is three frames. A pose never switches inside an `if`: blend to it with `prog` and an ease.
- **Something always moves:** a breath (1 percent squash on a slow sine), the star's bob, a slow camera drift.
- **The hand reaches, not the head.** Stand the character to one side of what it reaches for, by the reach of its arm (0.38 m for a `Buddy` of 1 m with the arm up). Stood right under the star, the pilot's character put its head through it, and every gate passed.
- **Place what is caught from the rig, never from worked-out numbers.** Pose the character as it will be at the catch, read the hand (`S3.where`), and hang the thing there (`home = hand + HOLD`). The pilot's star was placed by arithmetic twice and was wrong twice: first the head went through it, then the hand was inside it for seven frames. Then measure it with no render: the kit's `python plate3d.py run stage.py contact` prints the gap from the hand to the star's outline for every frame round the catch (it must stay positive before the catch and the star must not move on the catch frame).
- **A held thing does not jump.** If it hangs where the hand will be, it does not move when it is caught. Where it must travel, blend it over three frames; switched in one frame the pilot's star jumped 177 px. Hold it by a part the hand can meet: the star rests on the hand by its lower left edge, the hand touching and not inside it, the star clear of the head and the antenna.
- **Stretch reaches early.** A stretch of 0.22 lifted the hand to the star's height three frames before the top of the jump: a jump that ends in a catch uses 0.1.
- **A miss must be far.** The first failed jump took the head level with the star: lower the jump until the gap is seen, and raise the arm the camera can see.
- **A stop you can see.** Something that stops on a cue arrives still moving, stops dead and rocks (`settle`). Eased gently to rest, the pilot's crate was still two frames before its thud and Q902 noted the picture early.
- **The same pose crosses a cut.** End a scene in the pose the next one starts in, or bring the arm down before the cut.
- **Leave room for the caption.** Decide where each line sits before placing the camera: the pilot kept the top left wall empty for two lines and the right two thirds for the end card.

## What it cannot do yet

- Motion blur (each frame is posed and rendered alone), hair, cloth or fluid.
- Models, textures or HDRIs from outside: we download nothing, so the look is built shapes, soft light and clean colour.
- A character beyond `Buddy`: a new one is new rig code in the stage script. Keep it to rounded shapes and tubes.
- Speed for long pieces: a 60 s film at 30 fps is 1,800 frames, about 1 h 20 min to 1 h 30 min of final render on the machine above. Offer 24 fps, a shorter cut, or a plate on twos.

## When it breaks

| Symptom | Cause and fix |
|---|---|
| `PLATE: plates/main is older than stage.py` | The stage, `beats.py`, `stage3d.py` or another local module it imports changed after the render: run the command the line gives. A font or data file the stage reads is not watched: render again yourself after changing one |
| `PLATE: plates/main is being rendered` | A render holds `render.lock`. If none is running (it was killed), delete that file and render again: it resumes |
| `PLATE: plates/main lacks N of M frames` | A stills render or a stopped one: run the command the line gives |
| A traceback ending `plates/main has no plate.json` | Nothing has been rendered for this build yet: `python plate3d.py render stage.py --quality proof` |
| `not ready: Blender as a Python module` | `python plate3d.py fetch` (324 MB, once) |
| The render re-downloads Blender | The uv cache was cleaned; the fetch note in `~/.cache/zoetrope/blender/` only says it once imported here. Let it download |
| `ModuleNotFoundError: bmesh` | Something imported before `bpy`: Blender's other modules exist only after it |
| A frame file appears in `C:\plates` | A relative path reached Blender, which reads it from the drive root. `stage3d.run` resolves `--out`; do the same for any path you pass it |
| Device `CPU` in `plate.json` | No GPU backend was found: the render is right but slow |
| Q1202 on `plate3d.py` | A clock or random call was added to it: `scenes.py` imports that file, so the lint reads it |
