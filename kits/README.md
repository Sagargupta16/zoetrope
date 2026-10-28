# Style kits

Working code from approved builds, one folder per style card. A builder making that style copies the engine as usual, then the kit modules its README lists, and replaces the content while keeping the machinery. Each kit comes from the 2026-10-28 sample batch (60 s, reviewed PASS at the proof and final stages); the finished videos are in `outputs/samples-2026-10-28/videos/` (gitignored, local only).

| Kit | Card | Reusable machinery | Sample made with it |
|---|---|---|---|
| [g04-best-launch](g04-best-launch/README.md) | S-g04-best-launch | 2x-supersampled launch-film scenes: noise pile-up and collapse, frame-blended zoom match cut, phone and desktop mockups, streak tiles; the lo-fi score | Nook launch film, 16:9 |
| [g17-manim-derivative](g17-manim-derivative/README.md) | S-g17-manim-derivative | `kit.py`: a small math typesetter (fractions, limits, superscripts, primes), axes, plotted curves and tangents with numbers computed in code; glyph check | The derivative, explained, 16:9 |
| [g11-movie-credits](g11-movie-credits/README.md) | S-g11-movie-credits | Letterboxed 2.39:1 scenes, a rotating beam that reveals names as it passes, film grain and gate weave, a score cued to a beam clock; a grain size test | Salt and Signal credits, 24 fps |
| [g29-nes-rpg-battle](g29-nes-rpg-battle/README.md) | S-g29-nes-rpg-battle | `chip.py` 2A03-style synth (pulse with duty, 32-step triangle, LFSR noise, 60 Hz driver), `font5x7.py` bitmap font, `pix.py` palette-index canvas with Bayer dithering and outlining, `sprites.py`, a tracker screen driven by the same note table as the audio | Storm over Saltmere, 320x180 x6 |
| [bonus-rectangle](bonus-rectangle/README.md) | S-bonus-rectangle | An honest counter driven by one event list (outlines, boops and digits from the same data), dashed snap outlines, a stacked caption system for 9:16 | Everything is a rectangle, 9:16 |

What every kit has in common:

- `scenes.py` is the full worked example: read it for structure, then write your own content. It predates the text and cue registry: add `text_items(t)`, `CUES` and `KEY_TIMES` (see `engine/scenes.py`) when you reuse it, or `qa.py check` cannot run gates 2 to 4 and Q902 on it.
- `engine_used.py` is the build's own copy of `engine.py`, kept to diff against `engine/engine.py`. Carry over only its font lists (and the Nook kit's extra font weights); use the current engine for everything else.
- Superseded scripts were left out on purpose: each build's own gate, sync and parallel-render scripts are now `qa.py check`, `qa.text_gates`, Q902 and `render.render_parallel`.
