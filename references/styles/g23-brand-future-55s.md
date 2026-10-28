# S-g23-brand-future-55s · Brand vision film with archive and 3D (55 s)
**Source:** @notdwd, https://x.com/notdwd/status/2103995183255998633 · our build: g23-brand-future-55s
**Use when:** "brand vision film", "explain our coined word", "five-year vision video", "old footage meets modern 3D", "narrated brand story"
**Defaults:** 55 s · 16:9 1920x1080 · 30 fps · narrated (eight lines) plus music

## The brief (reusable prompt)
Collect {brand}, its logo, its five-year vision, a coined concept word the film explains, old archive footage, roughly 100 to 120 BPM music and voiceover material; then make a 55-second film combining 3D animation, footage, narration and sound effects.

## Scene plan
110 BPM, one bar is 2.182 s; every section starts on a bar line.
| Time | Beat | What happens on screen |
|---|---|---|
| 0-8.73 | The noise | 8-shot archive montage in a two-colour duotone (clock, switchboard, typing hands, phone, memo, commuters); captions "the bell / the call / the memo" land on the voice |
| 8.73-15.27 | The storm | Last archive frame becomes a 3D plane that flies back into a print; nine more prints and 96 notification chips swirl in an accelerating vortex |
| 15.27-19.64 | The nook | On the drop the extruded 3D mark slams in, ring shockwave pushes the storm away, concept word titles in, camera dollies into the mark's face |
| 19.64-26.18 | The word | Cream card: word, "rhymes with ..." respelling, definition words light up as spoken; logo holds a silhouette in its doorway |
| 26.18-34.91 | The practice | A 9-to-5 row of hour blocks cracked by falling chips; one block merges, turns coral, spins into the mark; phone rises; quiet dome deflects chips |
| 34.91-45.82 | The vision | Night wall of 3,600 windows lighting in a wave; camera cranes back; lit windows recolour into a mosaic of the mark; vision line word-synced |
| 45.82-55 | The brand | Mosaic becomes solid mark, plum turns to cream ("dawn"), mark spins into lockup beside the wordmark, tagline, footer, fade |

## Look
- Palette: plum #2b1b3f, coral #ff6b4a, cream #fff6ec, lilac #cfc4f2.
- Type: one rounded sans (build used Nunito). Respell pronunciation ("rhymes with booking") because the font lacks IPA glyphs.
- Layout and texture: footage graded plum and cream; captions only where words matter.

## Motion
Hand-off: the first 3D frame is a plane textured with the exact last footage frame, filling the frame. In PIL fake 3D with perspective-warped planes and stacked offset copies for extrusion. The window wall is 3,600 rects lit by a wave function of t.

## Audio
110 BPM. Cold open: tick-tock woodblock, pizzicato bass, projector flutter, typewriter clacks, bell, phone ring. Storm: four-on-floor pulse and a ping per chip. Drop: sub boom, silence, warm F major chord. Then soft groove (e-piano F, Am7, Bbmaj7), clap groove, bell melody and tom fill, final swell and Fmaj9. Narration: text-to-speech, eight lines, duck music about 12 dB under speech.

## Build notes
The build used five public-domain archive films. We cannot download or license footage: use the user's own clips or generated stills graded to the palette with grain. Keep narration at least 6.5 dB over the bed. Use only a vision and concept word the user supplied.

## Pitfalls (from what went wrong in our build)
- Vision wall opened very close and dark (34.9 to 35.8 s) and read as a dip: light some windows from frame 0.
- Three narration lines first sat at or below 0 dB over the bed: deepen the duck.

## Style QA
- Per-frame luma scan: no strobing.
