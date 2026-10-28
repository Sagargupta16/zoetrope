# S-g25-sand-us-history · Sand animation across 250 years
**Source:** @Michaelzsguo, https://x.com/Michaelzsguo/status/2102593579604377636 · our build: g25-sand-us-history
**Use when:** "sand animation", "history of {country} in 2 minutes", "tasteful, even-handed history", "anniversary video", "chapters by year with carved captions"
**Defaults:** 120 s · 16:9 1920x1080 · 30 fps (art animated "on twos" at 15 fps) · music and sound design only, no voice

## The brief (reusable prompt)
Make a 2-minute sand animation that tells the story of {N} years of {country} history. Keep it lively, engaging, and tasteful. Add appropriate background music and sound design. History must be accurate and even-handed.

## Scene plan
Bar = 2.222 s at 108 BPM, 54 bars = 120 s. Each scene change starts on a downbeat and lasts half a bar.
| Time | Beat | What happens on screen |
|---|---|---|
| 0-4.4 s | Title | Lightbox fades on, sand pours; title and span carved in |
| 4.4 s | 1776 | Declaration (scroll: "In Congress, July 4, 1776") |
| 11.1 s | 1787 | Constitution, "We the People" |
| 17.8 s | 1803 | Territory doubles; explorers cross the continent |
| 24.4 s | 1830 | Forced removal of Native people: blanket-wrapped figures walking west under bare trees |
| 31.1 s | 1860 | "Nearly 4 million people are held in slavery"; freedom seekers follow the North Star |
| 37.8 s | 1861-1865 | Civil War: quiet camp, a chain breaks into doves (no combat) |
| 44.4 s | 1869 | Transcontinental railroad, train and ship |
| 51.1 s | 1886 | Statue dedicated; Ellis Island, about 12 million immigrants by 1954 |
| 57.8 s | 1903 | First powered flight, 120 feet in 12 seconds |
| 64.4 s | 1920 | 19th Amendment, banner VOTES FOR WOMEN |
| 71.1 s | 1929 | Great Depression, breadline |
| 77.8 s | 1941-1945 | WWII convoy at dawn, formation overhead |
| 84.4 s | 1963 | March on Washington |
| 91.1 s | 1969 | Moon landing, Earthrise |
| 97.8 s | 1970s-2000s | Digital age |
| 104.4 s | 2001 | September 11: night skyline without towers, memorial light beams |
| 111.1-120 s | Finale | 50-star flag, fireworks, "and the story continues"; light dims |

## Look
- Palette: backlit sand. The gray value of each art frame is sand density (white = thick sand, black = clear glass). The compositor maps density to colour per channel: thin sand glows amber, thick sand goes dark brown. Exact hexes are not recorded in the build notes; tune by eye on a warm, vignetted lightbox.
- Type: Baskerville (large carved year), italic title line, Menlo for small detail; Snell Roundhand also used. All macOS system fonts.
- Layout and texture: captions carved into a dark ground band (year, title line, one detail line, 34 px), written on left to right like a finger drawing. Grain, clumps, sub-pixel edge warp, stray grains, uneven film, warm vignette.

## Motion
Art is stop-motion on twos (15 fps held to 30 fps). Things are drawn with soft directional or radial reveals and stroke draw-ons. Each scene change is a physical sand move at 30 fps, half a bar long: palm sweep (a sand ridge at the front, smear pushed ahead), granular dissolve, or radial throw (a ring of sand travels outward). Sweeps are panned the direction they travel. Lightbox fades on at 0 s and off at the end. Max frame-to-frame mean-luminance change was 11.6/255 (the fade-in); fireworks are local bursts, never full-screen.

## Audio
108 BPM, D major, all cut points on downbeats. Fife-like theme and light snare (1776), piano (1787), plucked banjo-like tone (West), somber minor pad with hum choir and sparse piano (1830, 1860), muffled timpani march resolving to major when the chain breaks, brush-shuffle train groove (1869), bells (Liberty), rising flute (flight), snare march and theme (suffrage), minor piano (1929), timpani and snare rolls (WWII), organ hymn (1963), bell shimmer (Moon), synth arpeggio (digital age), solo piano and choir (2001), full theme with cymbal swell ringing out as the light dims. Sound design stays subtle under the music: sand pour, sweep grains at every change, quill scratch, star chimes, wind, crickets, chain clink, locomotive chuffs, ship horn, propeller panned with the plane, marching steps, ticker, Apollo beeps at 2525 Hz, soft fireworks. Master -14 LUFS, true peak under -1.5 dBTP (build: -14.0 LUFS, -1.7 dBTP).

## Build notes
- Two stages: (1) draw a density image per frame in PIL (grayscale shapes with soft blurs, no colour); (2) a numpy "lightbox" pass converts density to colour with per-channel transmission exp(-density * K) (amber for thin, brown for thick), adds grain noise, clump noise, a vignette and slight edge warp. Draw on the Mac with PIL and numpy; do the blur with a small box or Gaussian written in numpy (no scipy in the sandbox; the device Python also has only PIL and numpy).
- Cost control: render the art at 15 fps and repeat frames; make transitions at 30 fps by blending two density frames with a moving sweep mask (ridge brighter at the front) or a noise threshold for the dissolve.
- Replace 16 chapters with the user's own list; keep 3 bars per chapter and 2 for the title and 4 for the finale.
- Tell hard chapters through symbols, no violence, no faces, no living politicians.
- Frame-time sanity: render proof stills of 6 to 12 chapters before the full run.

## Pitfalls (from what went wrong in our build)
- Figures were stylized silhouettes; the blanket-wrapped walkers looked blocky at small sizes. Draw them larger or fewer.
- Early reviews found wobbly small text, banner overflow, a ship off-screen, Earth reading as a moon, light beams reading as towers, skyline seams and sign overlaps. Review 4 rounds of stills.
- Sun rays in the WWII scene read as another nation's flag, so they were removed. Check every symbol for unintended meanings.
- The score was never auditioned by ear, only by meters; it sounds like a music box rather than a real ensemble, and was fairly compressed (LRA 2.7 LU).
- Radial-throw transitions made captions ragged for about half a second.
- 34 px detail lines were small on a phone; use 40 px or more for vertical or mobile delivery.
- Two images are symbolic: the memorial light beams (first lit March 2002) appear under 2001, and the 13-star arc in 1776 predates the flag adopted in 1777. Note such cases in the facts list.
- Recent decades get little time by design; tell the user.

## Style QA
- Each caption legible for most of its chapter; check the half-second after each transition.
- No full-screen flashes (check max frame-to-frame luminance change).
- Every chapter fact is on a checked list (the build web-checked the figures it was less sure of: census, immigration, flight, WWII service, removal numbers).
- Symbols reviewed for unintended readings.
