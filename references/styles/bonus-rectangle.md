# S-bonus-rectangle · Fun-fact vertical film with an honest counter
**Source:** our own brief (no external author) · our build: bonus-rectangle
**Use when:** "fun fact film for Reels or Shorts", "everything is a {shape/idea}", "world tour with captions only", "running counter gag", "vertical caption-led short with no voice"
**Defaults:** 45 s (about 40 to 45) · 9:16 1080x1920 · 30 fps · music-only, captions are the only storytelling layer
**Spec:** family=explainer length=40-45 size=1080x1920 fps=30 audio=music kit=bonus-rectangle
**Kit:** `kits/bonus-rectangle/` holds working code from the 2026-10-28 sample of this style (60 s, reviewed PASS); start from its README.

## The brief (reusable prompt)
Make a fun, generic, global vertical video called "Everything is a {shape}". Every shape on screen is built from that one shape. A thin dashed outline snaps around each one on the beat with a tiny boop, and a counter "{SHAPES} SPOTTED" counts what is really outlined. Only two or three deliberate non-matching objects are allowed, and each is a punchline that glitches the counter. No voice, no branding.

## Scene plan
Music is 120 BPM (beat 0.5 s, bar 2 s).
| Time | Beat | What happens on screen |
|---|---|---|
| 0.0-3.0 | Hook | Empty paper, counter at 0000. "Look around. / Count the rectangles. / We'll wait." |
| 3.0-7.0 | Objects | Phone, laptop, door, bed (top-down), one per 2 beats, outlined on 16ths |
| 7.0-9.0 | Zoom out | Pull up off the bed to a square-pixel world map; pin drops. "Now zoom out." |
| 9.0-13.0 | Place 1 | Cricket ground from above. "The cricket pitch." |
| 13.5-16.5 | Place 2 | Tatami room. "Tatami mats. / Twice as long as they are wide." |
| 17.0-19.5 | Place 3 | Tulip field stripes. "Tulip fields. / In stripes." |
| 20.0-22.5 | Place 4 | City grid, about 80 blocks; counter runs fast. "City blocks." |
| 23.0-26.0 | Place 5 | Container port; containers drop in; counter runs fastest. "Shipping containers. / Stacked to the sky." |
| 26.0-30.5 | Flags | Wall of plain-stripe flags, each outlined; two square ones lifted. "Almost every national flag is a rectangle." / "Two are square. Still counts." |
| 30.5-32.5 | Glitch 1 | Nepal's flag drops in; outline jitters; counter shows "????" and recovers with no +1. Music cuts. "Only Nepal said no." |
| 32.5-35.5 | Fold | A4 folds to A5, A6, A7. "Fold A4 in half. / Same rectangle. Just smaller." |
| 35.5-37.5 | Glitch 2 | A pizza (circle); outline fails; glitch. "Finally, something round." |
| 37.5-39.0 | Lid | Square lid flips shut at 38.0, +1 with thunk. "We put it in a square box." |
| 39.0-43.5 | Pull back | Whole film shrinks into a phone in a hand; hand outline fails, then at "(Yet.)" (42.2 s) it squares off and its 6 parts count. "Even this video is a rectangle. On a rectangle. In your hand." |
| 43.5-45.0 | End card | "Everything is a rectangle." ding at 43.6, final frame outline |
Between places the map pin hops over a 0.5 s beat. Adapt places and facts to the user's shape and verify each.

## Look
- Palette: paper #F4F1EA, ink #141414, one accent electric blue #2B59FF (outlines, counter, pin only). Each place gets its own 3 to 4 colour palette (greens and clay for cricket, straw and dark border for tatami, red/yellow/pink/purple for tulips, greys and yellow cabs for the city, rust/navy/ochre/teal for containers). Keep it cohesive.
- Type: Poppins Bold (big lines 110 to 150 px, tracking -0.035em) and Poppins SemiBold (small lines 46 px). Mac substitute: Avenir Next Bold or Helvetica Neue Bold.
- Layout and texture: counter top-left at (64,64), location label (square pin plus city) under it, left-aligned captions at x=72, max 860 px wide, above y=1498. Safe area: keep text out of the bottom 22% and right 12%. Paper header panel with an ink rule; the aerial view fills the frame below it.

## Motion
Masked line-by-line slide-up reveals with ease_out_expo. Outlines snap on the beat in sequence. The counter is honest: +1 for each dashed outline at the moment it appears (752 in total in the original, ending at 0752), computed from one event list that also drives the boops, so counter, outlines and sound cannot drift. Decorative boxes are drawn but not counted. Glitch: digits scramble to "????" in ink, the counter shakes, the outline jitters, then the true count returns (Nepal 30.95 to 31.85 s, pizza 36.05 to 36.95 s).

## Audio
120 BPM groove in C, Am, F, G: marimba lead, sub bass, kick, clap, shaker, soft pad. Cuts and caption hits land on the half-second grid. Each outline gets a boop on a pentatonic pitch, quiet, capped at 14 to 20 per second and shorter in dense scenes so city and port scenes become a tick texture. Music drops to near silence for both glitches. Also: tape-stop on the pizza, cardboard thunk on the lid, page-flip swishes, a small ding on the end card. Original -14.0 LUFS, -3.9 dBTP.

## Build notes
Build one scene-data list of (time, rectangle) events in Python; derive the counter, the outlines and the boop times from it. Draw top-down worlds as filled boxes with PIL.rectangle (supersample not needed for axis-aligned boxes). The pixel-map is a hand-built land mask of squares at 5 degree cells (72x26); keep it rough. Flags: only draw ones that are plain stripes or blocks, with correct colours and proportions. Nepal's double-pennon needs a polygon and counts as a deliberate exception. Sound is pure numpy.

## Pitfalls (from what went wrong in our build)
- The world map coastlines are rough; keep it stylised.
- The A4 fold read as flaps flipping over and the nested-ratio diagram was faint (35% ink); make the fold a clear hinge.
- The 4-bar music loop has little arc (LRA 2.3 LU); add a variation at each section change.
- Above about 14 events per second the boops do not match each outline 1:1; that is by design, say so.

## Style QA
- Final counter equals the number of outline events; no fake numbers.
- No non-matching shape outside the planned punchlines.
- Text is inside the safe area and every caption is spelled exactly as scripted.
