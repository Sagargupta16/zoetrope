# S-toy-studio-3d · Toy-studio 3D character short
**Source:** our own brief (no external author) · our build: pip-star (2026-11-10)
**Use when:** "3D animated character short", "Pixar-like cute 3D look", "a little mascot acts out the idea", "toy or clay world", "make it look like an animated film"
**Defaults:** 16 s (15 to 30) · 16:9 1920x1080 · 24 fps · music-only, a few short captions
**Spec:** family=game length=15-30 size=1920x1080 fps=24 audio=music kit=toy-studio-3d
**Kit:** `kits/toy-studio-3d/` holds the working code of the 2026-11-10 build of this style (16.5 s); start from its README and `plates.md`.

## The brief (reusable prompt)
Make a short 3D character film in a soft toy-studio look: one small rounded character with big eyes on a clean coloured studio sweep, lit like a toy photograph, shot with a real lens and shallow focus. The character wants one thing, fails once, has an idea and gets it. No dialogue: acting, a few short captions and a small score on real instruments carry it. End on one line the story has earned.

This is a stylised look in the direction of an animated feature, made from built shapes, soft light and clean colour. It is not a studio film: no hair, cloth, motion blur or modelled faces. Say so when the brief asks for more.

## Scene plan
The pilot, 120 BPM in three (a bar is 1.5 s, a scene is two bars). Swap the want, the obstacle and the helper for the user's idea; keep the five beats.
| Time | Beat | What happens on screen |
|---|---|---|
| 0.0-3.0 | Want | Wide two-shot: the character low left, what it wants high right. It looks up, reaches, hops because reaching is not enough. The line is on frame 0: "{Name} wants the {thing}." |
| 3.0-6.0 | Fail | Low camera from the side, so the thing looks far up. Crouch, a real jump with both arms up that stays well short, the landing, the slump. "Too high." |
| 6.0-9.0 | Idea | Close on the face: sad, a blink, a sound off screen, the look, the gasp. The helper slides in (a crate) and stops a little to one side of the thing, the camera at rest by then; the antenna lights; a smile that is already there when it does. "Idea!" |
| 9.0-12.0 | Reach | The camera follows the hop onto the crate and then tilts up with the second jump; the raised hand meets the thing at the top and it settles into the hand; sparks; the landing with it held; happy closed eyes that stay shut across the cut |
| 12.0-16.5 | End card | The character in the left third holding it high in the same hand, the other arm cheering, a small bounce on every bar, the camera easing back. The line holds to the end: "Small steps count." |

## Look
- Palette (the pilot): studio sweep periwinkle #9fb4ff with three soft hills behind (#8fa5f7, #b9c6ff, #c7b9ff), character coral #ff6b4a with indigo limbs #2b2850, helper teal #2fc4a8, the wanted thing gold #ffc21f, sky fill #e4e9ff. One warm subject on a cool ground; the thing it wants is the only yellow.
- Surfaces: `toy` (soft plastic with a clear coat and a little light under the skin) for the character and props, `matte` for the set, `eye` for the eyes.
- Light: `st.studio()` as it is (a 2.2 m warm key, a cool fill, a rim, a wash on the wall). A small `st.glow()` under anything that shines.
- Lens: 35 to 40 mm for the wide shots, 50 to 60 for the close ones, f/2.2 to f/4 focused on the character's head.
- Type: Nunito 800 (OFL, cached by `fonts.py`), white on an ink #1c1a3a pill with a soft shadow, 58 px captions and an 80 px end line at 1080. Captions sit on empty wall, never over the character: plan the camera round them.

## Motion
Everything is a function of t from `beats.py`. Eyes lead, then the body. Every jump has a crouch before it, stretch in the air and a squash on landing (`S3.jump`, crouch 0.2: 0.3 flattened the face; a hop under half a second in the air takes six frames over its crouch, or it dips in one), and the antenna swings after every stop (`S3.settle`). A blink is three frames, about every two seconds and before a change of mind. A breath of 1 percent on a slow sine keeps a held pose alive. The camera drifts in every scene and cuts on the beat; it follows the action across in the reach scene.

## Audio
A waltz on recorded instruments (`sampler.py`): plucked bass on one, harp on two and three, glockenspiel for the tune, marimba runs under the jumps, flute for the three falling notes of the slump, strings and horn under the end. Every cue is its own sound on its frame: landings (timpani and bass drum), the crate (bass drum and low marimba), the idea (triangle and a high glockenspiel note), the catch (a cymbal swell into a glockenspiel and harp chord with triangle, marked `payoff`, the loudest moment by measurement), bounces (plucked bass and tambourine). The music drops out twice: under the jump that misses, and before the crate arrives. The pilot's numbers are in the kit README.

## Build notes
Follow `plates.md`: `beats.py` first, stills, the proof plate, the proof, then the final plate in the background and `run_all.py full --fps 24`. Times on an RTX 4070 Laptop: proof plate about 3 minutes, final plate 17 to 20 minutes for 396 frames, and a change to the stage means the final plate again. For 9:16, set `SIZE = (1080, 1920)` in `beats.py` and restage every camera: the tall frame suits a reach upward, and the captions move to the top and bottom bands. For a brand, the character's colours and the thing it wants change; the rig is `Buddy`, and a logo is only ever an official file the user supplies, never rebuilt in 3D.

## Pitfalls (from what went wrong in our build)
- The character was a fifth of the frame height in three scenes of five: bring the camera in, or lower what it reaches for.
- Blender's default view (AgX) turned the palette pastel; the stage uses Khronos PBR Neutral.
- A glow of 1.2 washed the gold star to white, and a light in front of it did the same: keep the glow under 0.5 at rest and put the light under the thing. That light also turned the hand holding the thing gold: `st.unlit(light, hand, arm)` keeps it off them.
- A cream prop under the key light burned out to white: use a mid tone.
- Stood right under the star, the character put its head through it at the catch, and the star then jumped to the hand in one frame. Moved an arm's reach to the side by worked-out numbers, the hand was then inside the star for seven frames. The star now hangs where the rig's hand will be at the top of the jump, and `python plate3d.py run stage.py contact` measures the gap frame by frame. No gate sees any of this; two reviewers did.
- The first failed jump took the head level with the star, so "Too high." was not true, and from the side camera the reaching arm was behind the body: a lower jump, both arms up.
- Two hands raised either side of a held star touched nothing: one hand holds it, the other cheers.
- Bells alone made the catch all peak: the limiter took 6.5 dB and it still measured quieter than the cuts. A harp chord under them and thinner downbeats made it the loudest moment.
- One wash light left a visible beam on the wall from a side camera: the rig now has five.
- At the frame the idea lands the face was still frowning, and when the gasp ended early the frown came back for three frames: the gasp runs until just before the cue and the smile starts 0.3 s before it.
- A relative output path sent frames to the drive root: `stage3d.run` resolves it.
- A crate eased gently to rest was still two frames before its thud (Q902 NOTE): a prop that stops on a cue arrives moving, stops dead and rocks.

## Style QA
- `plates/main/plate.json` says `final` and every frame is there (`python plate3d.py check --final` prints `PLATES: ready`).
- The character fills a third of the frame height or more in each scene's key still.
- No caption touches the character; each line holds to its cut.
- Every landing in the picture has its sound within a frame (Q902), and the catch is the loudest moment (momentary loudness, measured on the master).
- Step through each jump and each catch frame by frame: nothing passes through anything, and a held thing touches the hand that holds it. `python plate3d.py run stage.py contact` shows no negative gap and no jump of the star on the catch frame.
- The end line is one the story has earned, and nothing in the film is a fact that needs a source.
