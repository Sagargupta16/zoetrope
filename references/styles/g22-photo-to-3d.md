# S-g22-photo-to-3d · Photo to cel-shaded 3D scene
**Source:** @ishuagra02, https://x.com/ishuagra02/status/2102543638689460488 · our build: g22-photo-to-3d
**Use when:** "turn this photo into a cartoon 3D scene", "cel-shaded", "camera flies through my picture", "before and after wipe", "illustrated version of a landscape"
**Defaults:** 19 s · 16:9 1920x1080 · 30 fps · music-only
**Spec:** family=handmade length=19 size=1920x1080 fps=30 audio=music kit=-

## The brief (reusable prompt)
Create a highly detailed 3D scenery that faithfully captures this photo in a cel-shaded cartoon art style. Show the photo first for comparison, then a camera move through the scene (about 15 to 20 s).

## Scene plan
| Time | Beat | What happens on screen |
|---|---|---|
| 0-2.2 | Source photo | Photo full frame with a slow Ken Burns push, label and credit |
| 2.2-5.8 | Wipe | A slider wipe replaces the photo with the stylised render from the photo's exact camera (half and half hold, then full) |
| 5.8-16.4 | Camera flight | Dolly past the main building, swing around it, rise over the lake toward the peak |
| 16.4-19 | End card | Photo and stylised scene side by side, title and photo credit |

## Look
- Palette: the scene takes its colours from the photo; UI uses cream #fffaf0 and dark blue-greys #1d2733, #0f1419; other greys in code: #b9c4cc, #8d99a3, #4a4c50; teal accent #6fd3c2.
- Type: Nunito (OFL). On a Mac use Avenir Next Rounded or Arial Rounded MT Bold.
- Layout and texture: flat cel shading with ink outlines (from normals and depth in the original), mist and cloud slabs, reflective lake.

## Motion
The photo gets a slow Ken Burns push. The wipe is a slider reveal (half and half hold, then full). The flight is a smooth camera path and every frame is a pure function of t. Easing values for the wipe and end card are not recorded in our notes: use ease_in_out_cubic for the wipe and ease_out_cubic for the end card.

## Audio
Music synthesised in numpy; mastered to -14.0 LUFS integrated. No other audio details are recorded in our notes: use a calm, light bed and a soft whoosh on the wipe.

## Build notes
The engine cannot run WebGL or Three.js, and we download nothing. A real 3D scene is out of reach. Workable substitute: use the user's own photo (never download one), make the stylised version in PIL by colour quantisation (posterise to 5 to 8 levels), edge-preserving smoothing with numpy, and ink outlines from a gradient threshold, then fake the camera move with a layered parallax: split the image into sky, far, mid and near bands by hand-tuned masks, scale and shift each band at different rates (near fastest). Keep the 4-beat structure above. Say plainly that this is a 2.5D approximation, not a true 3D scene. Credit the photo and licence on screen if it is not the user's own.

## Pitfalls (from what went wrong in our build)
- The summit stayed a broad rocky wall instead of the photo's sharp peak: check key silhouettes against the photo side by side.
- Rock shading was too realistic for cel style and noisy: flatten into few tones.
- Mist and cloud slabs read as gaps: keep them soft and low contrast.
- The build was cut off by a model connection failure before its own final frame review, so tuning of the summit and rock shading is unverified: always review a contact sheet before delivering.

## Style QA
- The first stylised frame matches the photo's camera, framing and horizon exactly.
- Outlines are consistent in weight and do not flicker between frames.
- The credit and licence appear on the opening label and the end card.
- The side-by-side end card shows the same crop for both images.
