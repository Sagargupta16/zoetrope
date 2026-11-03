# S-g28-camera-evolution · Futuristic hologram milestones
**Source:** @sachingmt, https://x.com/sachingmt/status/2104077647206821899 · our build: g28-camera-evolution
**Use when:** "evolution of {thing}", "futuristic motion graphics", "short history in 15 seconds", "tech timeline", "holographic HUD look"
**Defaults:** 15 s · 16:9 1920x1080 · 60 fps in the build (30 fps is fine here) · music-only
**Spec:** family=story length=15 size=1920x1080 fps=30 audio=music kit=-

## The brief (reusable prompt)
Futuristic motion graphics about the evolution of {product category}. About 15 s, correct dates, generic objects (no logos or trademarks), soundtrack synthesized, loudness -14 LUFS, no fast full-screen flashing.

## Scene plan
Bar = 1.4 s (171.43 BPM); one milestone per bar.
| Time | Beat | What happens on screen |
|---|---|---|
| 0.00-1.40 s | Intro (bar 0) | Fade from black; 9-blade aperture iris opens; "THE EVOLUTION / OF THE {THING}" decodes; first hologram scanned in |
| 1.40-12.60 s | Bars 1-8 | Eight milestones, 1.4 s each: index, year (slide swap, never an in-between year), title (decode), one-line fact, medium chip; callouts point at the model; bottom rail 1820 to 2030 to scale with a playhead gliding to each year |
| 12.20-12.60 s | Last scan-out | The final model is scanned away |
| 12.60-15.00 s | Outro | Iris closes around a glowing lens ("what will it see next?"), end title with the span (1827 to 2026), iris closes, fade to black |

Milestones used (camera example, checked): 1827 first surviving photograph; 1839 daguerreotype goes public; 1888 roll-film box camera (100 exposures); 1925 35 mm goes pocket-size (24 x 36 mm frame); 1948 instant camera; 1975 digital prototype (100 x 100 pixels, saved to cassette); 2000 camera phone (0.11 MP sensor; avoid claiming "first"); 2026 computational photography.

## Look
- Palette: void navy #03050a, hologram cyan #5AE4FF, amber #FFB84D (lenses, years), white-hot for freshly printed lines, red only for a tiny REC dot.
- Type: Avenir Next Condensed DemiBold or Heavy (titles), DIN Alternate Bold (years), Menlo (HUD). All system fonts.
- Layout and texture: wireframe model on a projector platform, perspective grid floor, drifting dust, dashed aperture rings, scanlines, vignette; info panel on the right.

## Motion
Each model is a wireframe (boxes, cylinders, rounded prisms) rotating with perspective and additive glow. Era changes: a horizontal scan plane sweeps down; the old model dissolves below it while the new one prints above (newest lines white, cut points sparkle). On each downbeat a capture snap and a short local brightening of the hologram (8 times in 11 s, never full-screen). Year changes by slide swap, not a counting roll (a roll showed false years). Text decodes via scrambled glyphs that settle into the final letters. REC dot blinks at 1 Hz. HUD values are real (segment count, live yaw, scan %, timecode). Everything is a pure function of t with seeded randomness.

## Audio
171.43 BPM, A minor: Am F C G Am F Dm E, then Am(add9) on the outro. Half-time kick and snare, 8th hats (16th ghost hats from bar 5), 8th-note saw plus sine sub bass, square/saw 16th arpeggio whose filter opens era by era, soft saw pad, kick sidechain ducking. Sound design on the picture grid: sub boom, iris ratchet clicks, decode blips and riser in the intro; a down-sweeping band-pass zap during every scan; two-stage shutter (mirror slap, curtain, ping) on each downbeat; swell, impact, chord and bells at 12.6 s; iris ratchets and a low thud at the close. Noise-IR stereo reverb, gentle tanh saturation, master -4.6 dB gave -14.1 LUFS, true peak -1.2 dBTP.

## Build notes
- 3D is the hard part: write a tiny line engine in PIL: define each model as a list of 3D segments, rotate by yaw, tilt by 0.3 rad, perspective divide, draw lines with ImageDraw at 2x supersample, then add glow by blurring a copy and adding it (numpy). Keep models to boxes, cylinders (as polylines) and prisms.
- Scan plane: for a given y, draw old segments clipped below it and new segments above; brighten segments within a band of the plane.
- Use the SCHEDULE dict: bar = 1.4 s, milestone i starts at 1.4 * i.
- Aperture iris: nine rotated polygon blades; animate the open radius with ease_in_out_cubic.
- With 30 fps, 450 frames at 1080p is quick on the Mac.
- A longer cut (20 to 24 s) reads better; recommend it if the user wants readable facts.

## Pitfalls (from what went wrong in our build)
- 1.4 s per milestone is fast: year and title read once, the fact line and callouts are fully visible for about 0.8 s. Offer 20 to 24 s.
- Wireframes are stylized, not accurate replicas (deliberately generic); the 1975 prototype and 2026 phone silhouettes are the least distinctive.
- Callout labels sometimes crossed model lines; place callouts outside the model bounds.
- Decoding text shows scrambled glyphs in a still frame; check proof frames at settled times, not mid-decode.
- The scan plane looks like a floating sheet in a still frame at its brightest.
- A hard cut from black caused a 23/255 luminance jump; a 0.25 s fade cut it to 4.8/255.
- Year slide-swap, not a counting roll, to avoid showing false years.
- Audio was balanced by meters, not by ear.

## Style QA
- Every year and claim matches the checked milestone table; avoid "first" unless sourced.
- Max frame-to-frame mean-luma change stays under about 5/255.
- No logos or brand names on any model.
- Downbeat shutter click lines up with each capture snap and year swap.
