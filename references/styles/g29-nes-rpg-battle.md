# S-g29-nes-rpg-battle · Retro console RPG battle theme
**Source:** @gigabit_million, https://x.com/gigabit_million/status/2104048491295318358 · our build: g29-nes-rpg-battle
**Use when:** "8-bit game", "NES or Famicom style", "chiptune battle theme", "retro RPG battle animation", "pixel art game trailer", "tracker or DAW visual"
**Defaults:** 75.2 s · 16:9 1920x1080 (drawn at 320x180, nearest x6) · 60 fps in the source (use 30 fps here) · music-only (chiptune)
**Kit:** `kits/g29-nes-rpg-battle/` holds working code from the 2026-10-28 sample of this style (60 s, reviewed PASS); start from its README.

## The brief (reusable prompt)
Build a simple tracker, compose a retro 8-bit RPG battle theme with it, then, as a professional game artist, finish it as one art piece in motion-graphics animation set to that track. Original game world, original characters, on-screen text in English.

## Scene plan
Bar = 1.6 s at 150 BPM (46 bars plus ring-out = 75.2 s). Source bar numbers are 0-indexed.
| Time | Beat | What happens on screen |
|---|---|---|
| 0 to 12.8 s | Intro (bars 0 to 7) | Tracker screen: four channels (PULSE 1, PULSE 2, TRIANGLE, NOISE) with duty text and "BPM 150 BAR/ROW" readout; pulse 2 enters at bar 2, pulse 1 at bar 4 |
| about 12.8 s | Encounter | Wipe into the battle; message "THE OBSIDIAN WYRM RISES!" from bar 8 beat 2 |
| 12.8 to 38.4 s | Sections A and A' (bars 8 to 23) | Party (knight, mage, ranger) vs the boss under an ember eclipse; menu with FIGHT / MAGIC / SKILL / ITEM; message box lines per 1 to 2 bars; hits, arrows, slashes, damage numbers; screen shakes |
| 38.4 to 51.2 s | Section B, enraged (bars 24 to 31) | Palette flips to violet "rage"; "THE WYRM IS ENRAGED!", meteors and bolts, "STARFALL!", "ABYSSAL ROAR!" |
| 51.2 to 64.0 s | Section C, heroic (bars 32 to 39) | "DAWN STIRS BEHIND THE ECLIPSE...", "STRIKE AS ONE!", combo; "DAWNBREAKER!" lands on bar 39 (62.4 s) and breaks the eclipse (dawn palette) |
| 64.0 to 70.4 s | Fanfare (bars 40 to 43) | Victory fanfare in A major |
| 70.4 to 75.2 s | Outro and end card | Bars 44 to 45 plus ring-out |

## Look
- Palette (strict NES-like): black #000000, white #FCFCFC, greys #7C7C7C #BCBCBC #3C3C3C, navy #0000BC, blue #0058F8, sky #3CBCFC, pale #A4E4FC, violet #4428BC #6844FC #9878F8 #D8B8F8, dark violet #200838, magenta #D800CC, pink #F878F8, red #A81000, orange #F83800, gold #F8B800, peach #FCE0A8, green #00A800, lime-green #58D854. Three sky themes: calm (black, dark violet, rust, red, orange), rage (black to violet, magenta, pink), dawn (navy, blue, sky, pale, peach, sand).
- Type: custom 5x7 pixel font drawn in code (no fonts, no Nintendo or other game fonts). On a Mac, a bitmap font is easy to hand-code; do not substitute a smooth system font.
- Layout and texture: 320x180 canvas, Bayer 4x4 dithering for gradients and shading, auto-outlined sprites, battle menu and message box, HP numbers, boss HP max 9999.

## Motion
All animation is keyed to the sequencer's note events: kicks and snares drive flashes and shakes, hit frames land 2 to 4 frames after the note. At 150 BPM one 16th note is exactly 6 frames at 60 fps (3 frames at 30 fps). Screen shakes of 1 to 3 px repeat on boss attacks (bars 9, 17, 22). Flashes are limited to about one per few seconds. Hard integer pixel steps, no sub-pixel blending. Everything is a pure function of the frame number.

## Audio
Original piece "Clash at the Ember Gate", 150 BPM, 4/4, A minor, with a victory fanfare in A major. Chord plan: intro Am Am F G Am F E E; A: Am F G Am Am F Dm E; B: Dm Dm Am Am Bb Bb E E; C: F G Em Am F G E A; fanfare A D E A. Four 2A03-style channels: two pulse (duty 12.5, 25, 50, 75 percent), triangle, noise (drums), updated 60 times per second like a game sound driver. Section B has a chromatic climbing run; bar 38 is a rising arpeggio build into the final blow. Source mastering: raw -17.8 LUFS lifted +3.8 dB to -14.0 LUFS, true peak -2.2 dBTP.

## Build notes
Write a small numpy chip synth: pulse (with duty), triangle (32-step), noise (LFSR) voices, rendered per note with simple volume envelopes and vibrato, mixed to 48 kHz. Compose from a token list per bar like the source. Draw the 320x180 PIL frame with ImageDraw and sprite arrays, then resize x6 nearest. Render at 30 fps to keep the frame count near 2,256 (75.2 s); the source rendered 4,512 frames at 60 fps. Use the same SCHEDULE for note events and visuals so hits stay frame-exact. Keep the world original (no existing game characters, music or fonts).

## Pitfalls (from what went wrong in our build)
- The first agent hit its context limit mid-build: split the song, sprites and renderer into separate modules and verify early.
- Sprite and layout needed three rounds of stills before they were right; review proof frames at scene boundaries first.
- Large brightness jumps must stay rare: the final file had 1 large jump in 4,512 frames (max 1 per second).
- Raw synth level was low (-17.8 LUFS), so plan the gain step; check true peak after the lift.

## Style QA
- Only palette colours appear; no anti-aliased edges or smooth gradients (dither instead).
- Visual hit frames line up with kick/snare events.
- Final loudness near -14 LUFS, peak at or below -1 dBTP.
- No more than 1 big flash per second.
