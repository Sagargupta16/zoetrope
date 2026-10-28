# Kit: S-g17-manim-derivative (The derivative, explained)

From the 2026-10-28 sample: 60 s, 1920x1080, 30 fps, captions instead of narration, 66 BPM ambient bed in D major. Proof 45 min; render 45 to 53 s for 1800 frames on 6 processes; 3.4 MB (v2); final review PASS.

| File | What to reuse |
|---|---|
| `kit.py` | Fonts (Cambria for formulas, Cambria Italic for variables, Cambria Math index 1, Segoe UI for captions), a small math typesetter (fractions, limits, superscripts, primes, true minus signs), axes with ticks and titles, curve plotting by sampling, secant and tangent drawing, number formatting that never shows "-0" (`fmt`, `fmt_trim`). |
| `scenes.py` | Eight scenes snapped to the 66 BPM grid: speedometer hook, secant shrinking to a tangent with a live readout, a definition built term by term with colour-coded rise and run, a worked example, a think pause with a filling ring, position-velocity-acceleration close. Every number comes from code. |
| `music.py` | The ambient bed: detuned additive pad, sub root, sparse bell arpeggio, cue bells, the pad-alone think pause. |
| `glyph_check.py` | Checks that a font really has the glyphs you need (prime, minus, arrow, superscript two) by comparing each against .notdef. Run it before trusting a math font. |
| `engine_used.py` | Its font lists (Segoe UI Semibold first in FONT_BOLD, Segoe UI first in FONT_REG). |

Lessons from its reviews: a dark-ink style sits close to the first-frame and last-frame gates (fill the dial face; put the end card on GRID panels); never crossfade two readouts in one spot (fade out, then in); compute every number on screen, even a "1" in a label.
