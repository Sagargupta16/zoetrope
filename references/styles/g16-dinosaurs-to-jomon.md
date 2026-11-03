# S-g16-dinosaurs-to-jomon · Deep-time globe and map explainer
**Source:** @mellow_neet2000, https://x.com/mellow_neet2000/status/2103487198758834408 · our build: g16-dinosaurs-to-jomon
**Use when:** "educational motion graphics", "how the Earth changed over millions of years", "timeline from X to Y", "museum-style science explainer", "no narration, on-screen text only"
**Defaults:** 128 s (a 60 to 90 s cut works by trimming chapters) · 16:9 1920x1080 · 30 fps · music-only (no narration; all teaching is on-screen text)
**Spec:** family=story length=60-128 size=1920x1080 fps=30 audio=music kit=-

## The brief (reusable prompt)
Using motion graphics, show how {subject} changed from {start era} to {end era}, both as an educational explanation and as visual expression. Language: English. One continuous camera, not a slideshow: start wide (the planet), end close (the people), so the frame shrinks as the story nears us. Keep two instruments on screen the whole time: a years-ago counter and a timeline ruler. Split the story into numbered chapters of about 8 to 21 s, each with a kicker, a name, a date range and up to three short facts that build in on the beat. Include one dramatic event beat and a closing "if the whole span were one day" clock.

## Scene plan
| Time | Beat | What happens on screen |
|---|---|---|
| 0-8 s | Title | Title over a globe at the start era (252 Ma) |
| 8-21.3 s | 01 Triassic | Supercontinent, ocean names, two animals, a 1.7 m human silhouette for scale |
| 21.3-34.7 s | 02 Jurassic | Continents split in two; three animal silhouettes at shared scale |
| 34.7-48 s | 03 Cretaceous | A subcontinent heads north; a location pin on the edge of Asia; three animals |
| 48-56 s | 04 The Impact | Incoming streak, white flash at 49.33 s, shockwave, dust veil darkens the globe, a 100-dot grid where about 75 go dark |
| 56-66.7 s | 05 Paleogene | Collision and polar ice; two animals |
| 66.7-77.3 s | 06 Neogene | Zoom from globe to a relief map; two land blocks swing open to form a sea (schematic, labelled as such) |
| 77.3-93.3 s | 07 Ice Ages | Sea level falls to -120 m on the map, land bridges appear, arrival-route arrows |
| 93.3-114.7 s | 08 Final era | Sea rises to +3 m, a patterned pot is "rolled" on by an animated cord next to the kanji, sites and animals |
| 114.7-124.6 s | Outro clock | Span compressed to 24 h; ticks resolve to a major chord; last era fits in the final 5 s before midnight |
| 124.6-128 s | End card | Credits |

## Look
- Palette: ground #05070D (deep navy night); text and cream tones #F2ECDF, #C9C1B2, #B9B2A4; warm accents #F0A27C, #FF8A55, #FFD27A; highlights #FFE85C, #F9F97F; cool tones #BFE4FF, #BFD8EA, #9AA3B4, #8FA6BC; violet #C27AD6. Land on the early globe is warm sand, shifting to green as life spreads. Ruler segments use the official geologic period colours.
- Type: a classical serif for display (build used Cormorant; on a Mac use Baskerville or Hoefler Text), a clean sans for body (Inter; use Helvetica Neue or SF), a mono for numbers and labels (IBM Plex Mono; use Menlo). Kanji from Hiragino Mincho ProN.
- Layout and texture: counter top right, ruler along the bottom (it rescales twice, and says so), kicker plus title plus facts on the left, atmosphere glow on the globe, lit orthographic sphere.

## Motion
Chapter text builds in on the beat: each fact slides up a short distance and fades in (ease_out_cubic), staggered per line. The globe turns slowly and continuously (time drives rotation and keyframe blend, nothing stored). Chapter changes are short cross-fades or a zoom (ease_in_out_cubic) from globe to map. The impact is a hard sequence: streak, white flash, expanding ring (ease_out_expo), dark veil fading in. Text stays on screen long enough to read at normal speed. Everything is a pure function of t with seeded noise.

## Audio
Original score at 90 BPM in D, one bar = 2.667 s, every chapter starts on a bar line. Each era has its own colour: arid heartbeat (Triassic), lush arpeggio (Jurassic), fuller and brighter (Cretaceous), whistle then boom then dark drone with music ducked (Impact), e-piano rebirth (Paleogene), pulsing bass plus tectonic rumble (Neogene), glassy and sparse (Ice Ages), Yo-pentatonic koto with breathy flute and taiko (final era), clock ticks resolving to D major (outro). Synthesize in numpy; master -14 LUFS (the build measured -14.1 LUFS, sample peak -1.2 dBFS). No voice by default; if the user wants narration, allow a few extra seconds per chapter and use a text-to-speech voice (`voice.md`).

## Build notes
- Do not try a real plate-tectonics model (the build used a scientific model and a GIS library, not available here). Substitute: a PIL orthographic globe from a handful of hand-authored continent polygons per era (5 to 8 keyframes) with linear interpolation of points, a lit shading gradient and a glow ring. State on screen that continents are schematic.
- Relief maps need elevation data; the sandbox has no network. Substitute: a procedural noise heightmap (seeded) for a generic coast and a sea-level threshold that moves with t, or ask the user for an elevation image.
- Animal silhouettes: draw simple vector shapes in PIL, or ask the user for their own. Never download images.
- Draw the two instruments (counter, ruler) first; they carry the whole structure. Render 2x supersampled for thin ruler ticks.
- Keep chapters in a SCHEDULE dict; shorten by dropping chapters, not by speeding them up.
- Fact-check every date against a source the user trusts; the build kept a "facts checked" list with rounded on-screen values (for example 252 / 201 / 143 / 66 / 23 / 2.6 Ma).

## Pitfalls (from what went wrong in our build)
- The basin-opening map was a schematic (two rigid blocks rotating on today's relief); label any simplification on screen.
- Ice-age and later coastlines used today's topography with sea level shifted, which ignores uplift and sediment; say "approximate".
- Early continents kept today's coastline shapes while moving, which is standard but not true ancient shorelines.
- A stand-in silhouette was used for an animal with no image available; state substitutions in the credits.
- Small layout collisions: the counter overlapped an island chain on one map and a route label sat close to the bottom ruler. Reserve safe zones for the counter and ruler in every map composition.
- No narration means all learning is reading; keep each fact short and on screen long enough.

## Style QA
- Counter and ruler visible and correct in every proof frame, including at chapter boundaries.
- Every date matches the facts list; no text collides with the counter or ruler.
- Impact beat reads clearly: flash is local or brief, no repeated full-screen flashing.
- Loudness near -14 LUFS, peak under -1 dBTP.
