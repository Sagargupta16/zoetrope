# Kit: S-g29-nes-rpg-battle (Storm over Saltmere)

From the 2026-10-28 sample: 60 s, drawn at 320x180 and scaled x6 nearest to 1920x1080, 30 fps, an original 150 BPM chiptune. Proof 41 min; render 17 s for 1800 frames on 6 processes; 17.9 MB; final review PASS.

| File | What to reuse |
|---|---|
| `chip.py` | A 2A03-style chip synth in numpy: two polyBLEP pulse channels with duty 12.5, 25, 50 and 75 percent, a 32-step triangle, 15-bit LFSR noise, a 60 Hz driver and the 2A03 mixer formulas. |
| `song.py` | The one note table: every note event drives both the audio and the picture (hits land 2 frames after their drum, the tracker rows show the notes playing). |
| `pix.py` | A palette-index canvas (22 colours), Bayer 4x4 dithering, auto-outlined sprites, x6 nearest upscale. Every pixel stays a palette colour. |
| `font5x7.py` | A hand-coded 5x7 bitmap font; no system font on screen. |
| `sprites.py` | Party sprites (knight, mage, ranger, with raised-weapon victory frames) and the serpent. |
| `scenes.py` | Tracker intro, dither wipe, battle with menu and message box, rage and dawn palettes, damage numbers that add up to the boss HP, end card. |
| `engine_used.py` | Unchanged font lists (the font is the bitmap one). |

Lessons from its reviews: set `CUE_LAG = 2` for this style (hits trail their drums by design, so Q902 must allow it); keep HP text 1 px clear of its box border; one hurt blink per hit, not alternate-frame flicker on the main subject; after moving any overlay, check it against the hero on every frame of the climax.
