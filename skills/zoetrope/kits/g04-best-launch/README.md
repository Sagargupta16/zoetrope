# Kit: S-g04-best-launch (Nook launch film)

From the 2026-10-28 sample: 60 s, 1920x1080, 30 fps, 96 BPM lo-fi in F major, a fictional focus app "Nook". Proof 40 min; render 150 s for 1800 frames on 6 processes at 2x supersampling; 7.1 MB; final review PASS.

| File | What to reuse |
|---|---|
| `scenes.py` | Nine scenes on a 2.5 s bar grid. Reusable pieces: notification pile-up with accelerating spawn and jitter, collapse to a point (8 blended sub-frames), the 1-to-34 zoom match cut (16 sub-frames) that lands cream on cream, the timer ring and odometer from one clock function, drag-reorder with lift, quiet-mode circle wipes, streak tiles, desktop and phone mockups, the lockup push-in. |
| `build_audio.py` | The 96 BPM lo-fi score: FM Rhodes, sub, soft kit, marimba and bell motifs, quiet-mode low-pass sweep on the music bus, SFX placed per cue. |
| `engine_used.py` | Its font lists: Segoe UI Bold, Regular, Black (`FONT_BLACK`) and Semibold (`FONT_SEMI`), with `font()` extended to pick a weight. Carry this over if you keep the four weights. |

Lessons from its reviews: the timer background must ease in from flat cream at the match cut (12.5 s) or the corner tints pop; the reveal wipe needs 1.0 s, not 0.8 s, to stay under 3 flashes in a second; small coral and mint text needs the darker tints (#c9452a, #23966f).
