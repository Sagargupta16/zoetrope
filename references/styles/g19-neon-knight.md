# S-g19-neon-knight · Pixel-art neon city reveal
**Source:** @SpikeRiser, https://x.com/SpikeRiser/status/2104019121377583446 · our build: g19-neon-knight
**Use when:** "pixel art animation", "neon city at night", "synthwave scene", "one continuous shot reveal", "colossal figure watching over a city", "atmospheric title sting"
**Defaults:** 26 s · 16:9 1920x1080 (drawn at 480x270, scaled x4 nearest-neighbour) · 30 fps · music-only (original synthwave, no voice)
**Spec:** family=game length=26 size=1920x1080 fps=30 audio=music kit=-

## The brief (reusable prompt)
A colossal {character} on a throne watches over a neon city at night, with waterfalls pouring down the steps and a crowd gathered in the plaza below. Real pixel art, one continuous camera move, original synthwave score, title in pixel neon.

## Scene plan
| Time | Beat | What happens on screen |
|---|---|---|
| 0 to 1.4 s | Dither in | Ordered-dither (Bayer 4x4) dissolve in from black; dark pad swells |
| 1.2 to 5.0 s | Title | Title letters flicker on one by one (one letter keeps misfiring), then the title flickers off; neon buzz follows the same flicker |
| 5.2 to 12.6 s | Tilt down | Sine-eased tilt from sky, moon and crowned helm down to the full figure, waterfalls and crowd, with parallax on 7 depth planes. Arp enters at bar 2, bass at bar 4 |
| 13.0 to 15.6 s | Build | Eyes brighten, phones light up in the crowd; riser and snare roll |
| 15.6 s | Climax | Visor flash, anamorphic streak, shockwave ring, 2 px camera shake; sub boom, crash, bright "shing"; drums start |
| 15.6 to 17.4 s | Wake-up | Halo ring ignites from the top (15.6 to 16.3), light runs down the sword channel (to 16.2), neon trims on six steps light top to bottom (16.2 to 17.4) with six descending glass plucks (A5 to C5) |
| 16.0 to 19.0 s | City answers | Windows surge on in a wave from the throne (16.0 to 18.0); lightsticks rise from the crowd centre outward and people bounce (17.0 to 19.0); crowd cheer swell |
| 19 to 24.2 s | Hold | Living wide shot, full groove, lands on Dm at 23.4 s |
| 24.2 to 26.0 s | Out | Dither dissolve to black except the eyes (24.2 to 25.4), eyes fade last (25.3 to 26.0), low hum fades |

## Look
- Palette (neon): pink #ff3fb4 (core #ffc2ec), cyan #29e8ff (core #c8fbff), violet #9d63ff, amber #ffb13b, red #ff3346, white #ffffff. Night base: #24123f sky dark, #7a5aa8 near the moon, #06040c silhouettes, #071a30 basin water, crown #ffd36a.
- Type: pixel-neon title in English only; shop signs HOTEL / BAR / 24 (the T in HOTEL is a broken tube). Neon glyph signs are deliberately abstract, never a real script.
- Layout and texture: indigo-to-magenta sky; rim light magenta on left edges, cyan on right, highlights on top, dark outline underneath; bloom = emissive layer blurred twice (about 7 px glow, 30 px haze) and screen-blended so pixels stay crisp.

## Motion
One continuous shot, no cuts. The tilt is a sine ease over 7.4 s; seven depth planes move at different rates for parallax. Sprite animation (water texture, crowd bob, twinkle) steps at 15 fps on purpose; camera, cars, airship and light sweeps run at 30 fps. Ambient life: twinkling stars, clouds across the moon, two searchlights, 16 flying cars with trails, an airship with marquee, blinking antenna lights, a pulsing billboard crown, rising embers. Climax effects fire together on one beat (15.6 s). Every pixel is a pure function of t with a seeded hash, no carried state.

## Audio
92.3 BPM (1 bar = 2.6 s, 10 bars), D natural minor, progressions i-VI-VII and i-VI-III-VII (Dm, Bb, F, C). Dark pad, neon buzz, arp from bar 2, bass from bar 4, riser and snare roll into a sub boom plus crash at 15.6 s, drums from there, glass plucks on the steps, filtered-noise crowd cheer, low hum tail. Master -14 LUFS integrated (final file measured -14.0 LUFS, -3.1 dBTP). RMS arc: about -17 dB under the title, about -8 dB at the climax, then a long ring-out.

## Build notes
Draw a 480x270 PIL frame per t, then resize x4 with Image.NEAREST. Build the figure from z-ordered shapes, then run a resolve pass that dithers each shading ramp (Bayer 4x4) and adds the rim light, instead of hand-placing pixels. Bloom: blur a copy of the emissive layer with ImageFilter.GaussianBlur twice and add it (ImageChops.screen). Water: scrolling streak noise on the risers, calmer noise on the treads. Keep crowd as dark silhouettes (head plus shoulders, about 330 figures) with a lighter wet plaza behind. Write a single SCHEDULE with the timings above and derive both picture and score from it. Score in numpy only (no scipy): saw/square arp, sine sub, noise for crash and cheer. Render at 30 fps; the build took 3 to 5 ms per frame in a browser, PIL will be slower, so render proof frames at 3, 9, 16, 20, 25 s first.

## Pitfalls (from what went wrong in our build)
- First layout had skyscrapers taller than the figure: lower the skyline so the figure rises above it.
- 1,100 coloured 3 px people read as confetti: use about 330 dark silhouettes against a lit plaza.
- Foreground heads were cut off at the frame edge: raise them.
- The dissolve looked like a screen door until it also dimmed the remaining pixels.
- Armour dithering gives a speckled chain-mail look; the body never moves (life comes from eyes, cape, halo, runes). A 1 px head shift looked glitchy, so skip it.
- At 30 fps on a x4 grid each 1 px camera step is a visible 4 px jump: authentic, not silky.
- Stray 1x2 white "phone" pixels can look like specks near the basin. The mix was checked by meters, not by ear.

## Style QA
- Pixels stay hard-edged (nearest-neighbour) while glow is soft; no blurry sprites.
- The figure is taller than every building; crowd reads as people, not confetti.
- Climax effects all land on 15.6 s, the audio hit matches the flash frame.
- Final loudness near -14 LUFS, peak at or below -1 dBTP.
