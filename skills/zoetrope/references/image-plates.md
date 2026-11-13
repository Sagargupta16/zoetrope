# Image plates

Photo-like pictures the 2D engine cannot draw (planets, landscapes, animals, food, a product on a table) made by an image model in the parent session, then animated, captioned and scored by the engine like any other build. The engine still draws every word, number, chart and icon; the plate is only the picture under them. This is the fastest route to a good-looking fact or explainer Reel: six plates took about 80 s on a laptop GPU, against hours of hand-drawing.

Read this when a brief needs real-looking imagery. For drawn looks (flat shapes, sketchbook, pixel art, diagrams) the engine alone is faster and keeps the style card's look; for a real 3D shot use `plates.md`.

## Who makes them

- **The parent session, never the builder.** The builder does not download or generate media; it uses only the files its brief names. Make the plates first, look at each one, then list them in `brief.md` with their path, size, scene and licence.
- **A local model through ComfyUI** (measured 2026-11-13): FLUX.1 schnell (Apache-2.0, commercial use allowed) through ComfyUI and Comfy's local MCP server `comfy-mcp`. `run_template("flux_schnell", params={"6.text": "<prompt>", "27.width": 1024, "27.height": 1088, "9.filename_prefix": "<slug>/p1-<name>"})` makes one 1024x1088 plate in 13 to 18 s on an RTX 4070 Laptop (8 GB VRAM, 32 GB RAM); the first one in a session loads the model. The fp8 checkpoint is 17.2 GB.
- **A hosted model** when there is no GPU: the Hugging Face MCP server runs community image Spaces (Z-Image Turbo, FLUX) on a daily free GPU quota (5 minutes on a free account). Record the Space and its model licence.
- Big model files: download them with resume and check the sha256 against the `X-Linked-ETag` header of the canonical repo path before the first render. A 17 GB file resumed across a network change came out the right size with the wrong hash, and rendered pure noise.

## Rules for every plate

1. **No text in the picture.** End every prompt with "no text"; image models misspell words and numbers. Captions, counters, labels and numbers are drawn by the engine, so the text registry and Q201 to Q209 still check them.
2. **Look at each plate at full size before the brief.** Reject and regenerate (about 15 s) rather than patch: man-made blocks in a natural scene, a notch or seam where two shapes meet, rings that pass behind the planet they circle. A tight crop that hides a fault also softens the plate; the reviewer will flag both.
3. **Honest scale.** A plate that shows two things together implies their sizes. Reject one that misleads (Earth drawn a seventh of the Sun's width when it is about 1/109) or drop the second object from the prompt. If a fact is about size, the engine draws the comparison to scale (bars, a dot) over a plate that shows one thing.
4. **The picture matches the fact.** Name the visible feature in the prompt ("rings crossing in front of the disc", "summit caldera"), then check that it is there. Change the storyboard's visual line when a plate shows something else.
5. **Size for the visible area.** Generate close to the area the plate fills after the header (for a 9:16 header layout, 1024x1088 scaled to 1080 wide) and keep the Ken Burns scale under about 1.3x; past that the plate goes soft.
6. **Licence and origin in the delivery report** (house rule 5): the model, its licence and "generated for this video" for each plate.

## AI video clips

- An image model does not make motion; the engine moves the plate with Ken Burns, parallax and drawn overlays, and that is usually enough.
- Local text-to-video on 8 GB (Wan 2.1 T2V 1.3B through ComfyUI, measured 2026-11-13): 49 frames at 832x480 in about 250 s, clean but nearly static, and it read "zoetrope drum" as a snare drum. Hosted image-to-video (Wan 2.2 14B on a Hugging Face Space) animated a plate in about a minute and looked better. Use either only as a short B-roll insert, never as the scene the facts sit on.

## The brief

List each plate as `plates/<scene>-<name>.png`, with its size, the scene it fills, any drawn overlay the scene needs (an axis, a bar pair, an icon), and its licence line. Tell the builder the plates are given and that it must not fetch or replace them. The builder's report says how each plate is framed (Ken Burns centre and scale); check that the subject stays inside the frame for the whole scene.
