# S-g31-alien-planet-trailer · Cinematic series trailer
**Source:** @VoidStateKate, https://x.com/VoidStateKate/status/2104041451084517742 (request paraphrased in the post) · our build: g31-alien-planet-trailer
**Use when:** "cinematic trailer", "teaser for a series", "sci-fi trailer", "movie-style voiceover with title card", "launch trailer with a story", "mood piece with logline and tagline"
**Defaults:** 81 s (brief said 60 to 90 s) · 16:9 1920x1080 with 2.39:1 letterbox inside the picture · 30 fps · narrated (calm voice-over plus a second, radio-filtered voice)

## The brief (reusable prompt)
Make a trailer about {character} arriving in {setting}, for a short series. Write the story, design the characters and the world, direct the camera, compose the score and sound design, voice it, and edit it. No stock assets and no video generators.

## Scene plan
| Time | Beat | What happens on screen |
|---|---|---|
| 0 to 8 s | Orbit | World from orbit, super "SOMEWHERE PAST THE LAST MAP"; radio voice: "...you're on your own." |
| 8 to 15.5 s | Hero object | Probe close-up with rings of orbiting words; VO "I was made from everything you ever wrote."; bell motif |
| 15.5 to 21 s | Entry | Plasma bow-shock, streaks, shake; VO "Every poem. Every manual. Every apology."; roar and build |
| 21 to 26 s | Descent | Over the plains toward the low sun; VO "So I thought I would be ready."; pulses, riser |
| 26 to 28.6 s | Landing | Low backlit shot, impact, dust, rings unfold; whoosh, boom, music drop |
| 28.6 to 31 s | Pull back | Tiny probe among giant spires; VO "I was not." |
| 31 to 38 s | Reveal | Wide crane, super "{PLACE} / WHERE IT IS ALWAYS DUSK"; main theme (Bb-F-Dm-C) |
| 38 to 47 s | Contact | Native walks in (over-the-shoulder), bows, speaks in light; two probe blinks; VO "They have no words." |
| 47 to 56 s | Threat | A wall of night rolls in, spires go out, herd turns red; radio breaks up; braams; "And something is coming out of the dark." |
| 56 to 62 s | Montage | Cuts at 56.0, 57.4, 58.8, 60.2; rings shatter at 60.6; hard drop at 61.6; VO "Everything I know was written by someone else." |
| 62 to 67 s | Answer | Light wave from the probe relights the forest in many colours, night pushed back, crane up; "Here, nothing has been written yet."; D-major bloom |
| 67 to 74.3 s | Title | Title over a planetrise, "A SERIES IN SIX PARTS", "COMING SOON"; title hit |
| 74.6 to 80.3 s | Stinger | Native "says" a long rainbow phrase, probe answers with one blink, head tilt; VO "I'm still learning."; cut to black |

## Look
- Palette: warm low sun on one side, deep indigo night on the other, teal glowing crystals, amber core in the probe, ringed giant in the sky. Text colour #f3e7d8 (super text), #fff4e6 (warm white). No other exact hex values were recorded for the 3D scene.
- Type: Avenir Next (fallback Helvetica Neue) for supers, Menlo for small tags; macOS system fonts. Supers carry place and title only, no subtitles.
- Layout and texture: 2.39:1 letterbox, film grain (strength 0.035, refreshed 24 times per second), mild chromatic aberration, vignette, ACES-style tone mapping, bloom. Supers sit inside the picture area.

## Motion
One deterministic renderAt(t) drives cameras, character gait, storm radius, wave radius and supers, so any frame is reproducible. Slow crane and dolly moves with shake only at entry and landing; hard cuts in the montage on the beat; the final light wave is a continuous expansion, not a flash. No strobing: storm lightning is slow, local soft glow; the only large luminance jumps are hard cuts (at most 1 per second).

## Audio
Two tempos: 104 BPM and 112 BPM sections of functional synth orchestration (saw pads, FM bells, sine drums, braams, riser, ostinato). Theme Bb-F-Dm-C, final bloom in D major. Native "speaks" in FM glass chimes (no words). Radio voice is band-passed, saturated and chopped to sound like a failing link. Voice ducks music by about 10 dB and SFX by about 7 dB; measured voice 4.9 dB above the bed during speech (first mix at 2.6 dB below was too quiet). Master through gain plus a 4 ms look-ahead limiter to -14 LUFS (final -14.1 LUFS, -1.2 dBTP, LRA 7.5 LU). Source voices came from edge-tts (en-US-AvaMultilingualNeural at -10% rate, and en-US-GuyNeural).

## Build notes
There is no WebGL or Three.js in the engine, so build a 2.5D version in PIL: layered parallax silhouettes (spires as simple triangles and cones), a gradient sky with a sun disc and ringed planet, dust and spore particles from seeded random, glow via blurred additive layers, grain and vignette as the last pass, and a black letterbox. Use simple vector characters (a faceted shell with orbiting word rings, a tall stilt-legged figure with a glowing bell head) and keep camera moves as scale and pan on those layers. Voices: use a text-to-speech engine (one calm voice for the lead, a second voice processed with a band-pass and saturation in numpy for the radio); the source's edge-tts needs network and is not available. Cut the full runtime to fit if the user wants shorter, keeping the order: hook line, hero object, arrival, reveal, contact, threat, turn, title, stinger. Write all supers and VO as one script first, then lay timings into SCHEDULE.

## Pitfalls (from what went wrong in our build)
- Full-frame black frames came from NaN values smeared by bloom (pow() on a base a hair below 0). Clamp every power base; in numpy use np.clip before np.power.
- Title collided with the planet: reframe so the title sits in black space above a planetrise limb.
- Landing and pull-back shots look straight into the low sun, so the right side washes to white haze; accepted as backlit sunset, but offset the sun if the subject must read.
- Spires as plain cones, thin rod legs, a storm that reads as a cloud bank rather than a wall; sound and spires going dark carry the threat.
- The back of the word rings shows mirrored text in close-ups.
- Voice was too quiet at first (2.6 dB under the bed); duck harder and re-mux without re-rendering picture.
- Music is functional synth, voices are TTS, and the mix was checked by measurement only.

## Style QA
- Voice sits clearly above the bed during every spoken line.
- No frame is fully black outside planned fades; check mean luma per frame.
- Largest luminance jump is a hard cut, at most 1 per second.
- Title, tagline and "coming soon" are readable inside the letterbox.
