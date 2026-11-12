# Kit: S-bonus-rectangle (Everything is a rectangle)

From the 2026-10-28 sample: 60 s, 1080x1920 (9:16), 30 fps, 120 BPM groove in C, Am, F, G. Proof 39 min; render 13 s for 1800 frames on 4 processes; 19.6 MB (v2); final review PASS.

| File | What to reuse |
|---|---|
| `scenes.py` | The honest counter: one `EVENTS` list of (time, rectangle) drives the dashed snap outlines, the counter digits and the boop times, so counter and picture cannot drift (573 outlines, final counter 0573). Glitch passages that scramble the digits without a +1, a stacked caption system that keeps text clear of the bottom 22 percent and right 12 percent, top-down place scenes, camera push-ins with an edge check that keeps every counted outline fully on screen and below the header. |
| `music.py` | The groove, one pentatonic boop per outline capped at 16 per second, near-silence on the glitches, tape-stop, a ducked thunk and an end ding. |
| `engine_used.py` | Its font lists (the build used Segoe UI Bold and Semibold through its scenes). |

Lessons from its reviews: a waiting caret on the counter reads as a fifth digit on the thumbnail; any layout change after review (a 1.05 em line height) can push a counted outline under the header, so recheck every outline against the header; duck the bed under a big hit instead of raising the hit into the true-peak limit.
