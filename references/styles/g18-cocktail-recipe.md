# S-g18-cocktail-recipe · Recipe explainer with live measurements
**Source:** @Ror_Fly, https://x.com/Ror_Fly/status/2102853258582880547 · our build: g18-cocktail-recipe
**Use when:** "recipe video", "step by step how-to", "show the ingredients and amounts as they go in", "empty to finished", "explainer with a count-up"
**Defaults:** 30 s · 16:9 1920x1080 · 30 fps · music-only (no narration unless asked)

## The brief (reusable prompt)
Render a recipe motion graphic that shows the full recipe from start to finish (empty glass to completed {product}), explainer-video style, showing each ingredient and its measurement as it goes into the glass. 30 seconds.

## Scene plan
| Time | Beat | What happens on screen |
|---|---|---|
| 0.0-2.5 | Title | Empty glass on a dark bar top; title letters rise in, then the title shrinks into a top-left header |
| 2.5-5.0 | Step 1, ice | Ingredient list slides in (left), step card (right). 8 cubes drop with a small bounce; card counts 0 to 8 |
| 5.0-10.0 | Step 2, spirit 45 ml | Bottle swings in, tilts, pours. A dashed "+45 ml" fill line appears first, liquid rises to it while the card counts 0 to 45 with a measuring bar |
| 10.0-15.6 | Step 3, juice 90 ml | Second bottle pours, drink turns orange, "+90 ml" line, count 0 to 90 |
| 15.6-21.25 | Step 4, syrup 15 ml | Thin red stream, red drops sink and a red layer rises from the bottom. Handwritten "don't stir!". Sky warms to dawn and a sun rises behind the bar top |
| 21.25-25.0 | Step 5, garnish | Half orange wheel tumbles onto the rim, sparkle. Every list row is now ticked |
| 25.0-30.0 | Finished drink | UI clears, hero glass in front of the sun, big title, spec line, tagline |

## Look
- Palette: night-to-dawn. Pale gold #FFE6A8, amber #FFC060, grenadine reds #B5122F and #D41F3B, label ink #2A1A40, label rule #C9893A. Base is indigo night with cream type (indigo and cream hexes are not recorded in our notes: choose close values).
- Type: Bodoni Moda italic for titles and ingredient names (menu feel), Inter for numbers and labels, Caveat for the one handwritten note. All free (OFL). On a Mac use Didot or Bodoni 72 for the serif, Helvetica Neue for numbers, Bradley Hand or Noteworthy for the note.
- Layout and texture: ingredient list left, step card right, hero glass centre. Vector glass, liquid and bottles. Generic bottle labels ("TEQUILA", "ORANGE JUICE", "GRENADINE"), set on one line along the bottle so they read when tilted.

## Motion
Every step change lands on a beat. Each measurement is shown three ways at once: a count-up number on the card, a measuring bar under it, and a dashed fill line plus "+N ml" tag on the glass that appears just before the pour. The count-up and the liquid level share one easing, so they stay in sync. Liquid height is proportional to volume (2.9 px per ml over the ice; 45, then 135, then 150 ml total). Cubes fall with an ease-in (k ** 2), then a hand-built bounce: up 14 px over 0.09 s (ease-out), back down over 0.14 s (ease-in). Bottles pivot around the bottle mouth so the pour stream stays fixed. Everything is a pure function of t: seeded random for sparkle, no state between frames.

## Audio
96 BPM lounge/bossa bed in D, chords D, Bm, G, A (FM electric piano, bass, soft kick, rim, shaker). 12 bars at 96 BPM equal exactly 30 s, so cuts at 2.5, 5.0, 10.0, 15.625, 21.25 and 25.0 s fall on beats. A bell arpeggio rises through the sunrise; a Dmaj9 chord plus chime lands on the final reveal. SFX locked to the timeline: ice clinks on each cube landing, pours as tiny bubble chirps whose pitch rises as the glass fills, a glass tap when each bottle reaches the pour position, ticks on check marks, soft whooshes on card changes, a "pat" and glitter when the garnish lands. Pours sit 6 to 9 dB under the music. Master to -14 LUFS.

## Build notes
Draw with PIL: glass as polygons with alpha, liquid as a clipped rectangle whose top is `base - ml * px_per_ml * ease(t)`, grenadine as a vertical gradient layer growing from the bottom, ice as rounded rectangles with a light stroke. Put all cue times in one SCHEDULE dict and generate the audio from the same dict so picture and sound cannot drift. Check the recipe against a reliable spec before drawing it (our build used the IBA specification: 45 ml tequila, 90 ml fresh orange juice, 15 ml grenadine poured last and not stirred, half orange slice). Show imperial conversions with "approx": 45 ml is about 1.5 oz, 90 ml about 3 oz, 15 ml about 0.5 oz. Supersample 2x for glass edges.

## Pitfalls (from what went wrong in our build)
- Title-to-header morph showed a 3-4 frame soft double image near 2.85 s because the two sizes differ in width: crossfade over more frames or match widths.
- Final title crossfaded over the fading header at 25.0-25.5 s: clear the header first.
- The "+15 ml" tag sits at the top although the syrup sinks; a viewer can read it as "on top". Label it "sinks" or place the tag with care.
- Liquid stays level while pouring (no splash); the stream passes behind the ice; pale spirit reads grey on a dark background. Tint it slightly.
- A synthetic pour can sound "fizzy" instead of real; keep it quiet under the music.
- Tags of 21-26 px are small on a phone: use 32 px or more for a 9:16 version.

## Style QA
- Every ingredient shows its amount in at least two places (card and glass tag).
- The level on the glass matches the count-up at the end of each pour.
- Each step change lands on a beat of the music.
- The ingredient list is fully ticked before the finished-drink shot.
