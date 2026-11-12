# Style families

Read the family intro for the chosen card before building; it says what every card in the family shares.

## Launch, product and promo videos

Pick a style from this family to sell, announce or show off a product, app, deal or brand: launch film, 15 s ad, "make it stunning" promo, deals roundup, brand vision piece or showreel. Use the 15 s cards for social and ad slots, the 48 to 55 s cards for a full launch or brand story, and the 9:16 card for deal lists. We never invent metrics, prices or ratings.

Cards: S-g02-promo-any-tools, S-g03-15s-product-ad, S-g04-best-launch, S-g08-product-showreel-15s, S-g09-showreel-15s, S-g10-showreel-spec, S-g23-brand-future-55s, S-mobiles-deals, S-signal.

## Logos, intros, titles and credits

Pick a style from this family when the user wants a brand moment rather than a story: a product or brand intro with music, a short logo sting, film-style opening credits, or a personal or team self-introduction reel. All four are music-led (no narration), so the agent must plan the cue sheet first, then draw frames and synthesize audio from the same numbers. Every beat below is placed on a beat grid; keep that grid when adapting.

Cards: S-g01-intro-masterpiece, S-g05-logo-animation, S-g11-movie-credits, S-g30-structured-self-intro, S-marquee.

## Music-driven, beat-sync and kinetic

Pick a style from this family when the music is the structure: cuts, hits and UI moments must land on a beat grid, or when the piece is a showcase of motion and sound design rather than a talking explainer. The four cards run from a 20 s beat-locked product spot, to a 30 s sound-as-feature piece, to a 60 s news roundup, to an 80 s abstract film. In all four, write the music and the picture from one shared schedule so sound and image cannot drift. In the engine, synthesize the score in numpy on the beat grid and draw every frame in PIL; the HTML/GSAP/WebGL tools named below were used in our builds and are not available in the engine.

Cards: S-g06-go-crazy-30s, S-g12-beat-sync-spec, S-g13-steam-news-60s, S-g27-mosaic-film, S-pulse.

## Explainers and education

Pick a style from this family when the viewer must learn or understand something: a product walkthrough that doubles as a showreel, a beginner topic explained with metaphors, a concept told through contrasting visual styles, a maths idea with a voice-over, or a fun fact film for Reels and Shorts. Each card says how to build it inside the engine contract. For long originals we recommend a shorter cut of the same structure.

Cards: S-g07-research-40s, S-g14-what-is-git, S-g15-recursion-styles, S-g17-manim-derivative, S-bonus-rectangle, S-ledger, S-blueprint.

## Story, history and journeys

Pick a style from this family when the user wants to tell a story across time or place: a deep-time or history explainer, a travel or city introduction, or a short "evolution of X" milestone piece. All four share one backbone: a clear timeline or chapter list, an always-visible "where are we" device (counter, ruler, year, rail), and music that changes mood per chapter on a bar grid. Check the "Build notes" in each card before promising it: the footage-based style needs the user's own media, and the 3D or data-driven looks need a simpler PIL substitute.

Cards: S-g16-dinosaurs-to-jomon, S-g24-new-york-5min, S-g25-sand-us-history, S-g28-camera-evolution.

## Characters, games and cinematic trailers

Pick a style from this family when the user wants a world, a character or a story told through picture and a composed score: a pixel-art scene, an anime-flavoured short, a retro game battle, or a cinematic trailer for a series or product. These are the most music-led and craft-heavy styles we have. They have no spoken facts to check, so the work is in design, timing on a beat grid and a clean mix. Swap every story name below for {brand} / {product} or the user's own idea, and keep all characters original.

One card here is true 3D: S-toy-studio-3d renders its picture in Blender as a plate (`plates.md`), for a small character acting out one idea on a studio sweep; offer it when the brief asks for a 3D or animated-film look, and say what it takes (a GPU, and about 3.5 s a frame at 1080p).

Cards: S-g19-neon-knight, S-g21-anime-remix, S-g29-nes-rpg-battle, S-g31-alien-planet-trailer, S-toy-studio-3d, S-cartridge.

## Handmade, craft and personal looks

Pick a style from this family when the user wants something that feels made by a person or a studio rather than a template: a recipe or how-to explainer with liquid and measurements, an abstract motion showreel about a feeling, a photo turned into a cartoon 3D scene, or a hand-drawn sketchbook flip-through. These are the most demanding looks in the library. Each card notes what the original build used (real 3D, HTML, WebGL) and the workable substitute in the engine (PIL frames, numpy audio, ffmpeg). When in doubt, simplify the look and keep the timing and audio sync.

Cards: S-g18-cocktail-recipe, S-g20-overthinking, S-g22-photo-to-3d, S-g26-claude-sketchbook.

## The six panel cards (signal, ledger, blueprint, marquee, pulse, cartridge)

These six were designed here from the engine, not from an outside build (2026-10-31, rewritten from the code on 2026-11-01), and share one card layout: Use when, Format, Look (colour roles with every text pair's WCAG ratio), Motion, Sound, a bar-by-bar Beat map with placeholder text, Build notes, QA watch-outs and Variations. None has a kit yet: the first build of each is its proof. What they share:

- **Contrast.** Every pair in a card's table was computed with the WCAG 2.x formula (`qa.contrast`, the one Q301 applies to real pixels) and clears 4.5:1, so any pair may carry text at any size. A brand colour that replaces a card colour is checked against every background the card names; under 4.5:1 it colours shapes, never words.
- **First and last frame.** Each background lists its PIL grey (0.299 R + 0.587 G + 0.114 B): Q501 and Q502 need a frame mean over 25, so every card opens on its hook fully drawn and ends on a held end card, never on black.
- **Tempo.** Every default tempo (75, 100, 120, 150 BPM) has a whole number of frames per beat at 30 fps (`formats.md`). Scenes are declared in beats, and every time in a beat map sits on its grid.
- **Placeholders.** A quoted placeholder in a beat map is as long, in words and characters, as the longest line its slot is built for. Replace it with a line no longer than it, then run `qa.py holds` on the scenario with the card's profile; a SHORT line loses words, never reading time. The six beat maps printed `HOLDS: OK` as written (2026-11-01).
- **9:16 margins.** These cards keep the bottom 400 to 440 px of a 9:16 frame, and a strip down its right side, empty. That margin is this set's own: platforms draw their controls in places that differ and change, and no gate measures them (`formats.md`).
- **Originality.** No card imitates a named film, show, game, brand or product, and none uses a third-party logo or character. A mark appears only when the user supplies it.
- **How to pick among them.** Start from the one thing the viewer must take away: something new to try, signal; a number with a source, ledger; how something works, blueprint; a name to remember, marquee; a line or a feeling for a phone feed, pulse; a story told for fun, cartridge. When two fit, prefer the card whose material the user already has (sourced figures, a product interface, a mark, a list of parts and flows). A number with no source never goes on screen.

### Fonts for the six panel cards

Each card names two SIL OFL families, one per engine slot: `FONT_BOLD` (`bold=True`) and `FONT_REG` (`bold=False`). Inter, JetBrains Mono and Fraunces are in `fonts.py`'s cache, so draw them by name (`bold="Inter:700"`, `bold="JetBrains Mono:400"`, `bold="Fraunces:700"`). For the others, put their paths first at the top of scenes.py, at import time, which the lint passes: `FONT_BOLD[:0] = [...]` and `FONT_REG[:0] = [...]`, followed by the card's fallbacks for the OS. Use one static file per weight: a variable file put in those lists opens at its default instance (Windows' variable `bahnschrift.ttf` drew the same ink as its Regular instance on Pillow 13.0.0, checked 2026-10-31). Static files, checked 2026-11-01:

| Family | Card | Static files |
|---|---|---|
| Inter | signal | cached by `fonts.py` |
| Libre Franklin | ledger | impallari/Libre-Franklin, `fonts/TTF/LibreFranklin-Bold.ttf`, `-Regular.ttf` |
| Space Grotesk | blueprint | floriankarsten/space-grotesk, `fonts/ttf/static/SpaceGrotesk-Bold.ttf` |
| JetBrains Mono | blueprint | cached by `fonts.py` |
| Fraunces | marquee | cached by `fonts.py` |
| Outfit | marquee | Outfitio/Outfit-Fonts, `fonts/ttf/Outfit-Regular.ttf` |
| Anton | pulse | google/fonts, `ofl/anton/Anton-Regular.ttf` (one weight) |
| Barlow | pulse | google/fonts, `ofl/barlow/Barlow-SemiBold.ttf` |

Downloading a font is the user's call: ask before fetching one. With no file at hand, the card's fallback draws the build. cartridge needs no font file: its grid font is part of the build.
