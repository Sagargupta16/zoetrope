---
name: zoetrope
description: >-
  Plan, script, design, animate, score and render short videos (MP4, WebM,
  GIF) end to end with Python, Pillow, numpy and ffmpeg. 33 tested styles:
  product ads and launches, logo stings and intros, beat-synced kinetic
  pieces, explainers, history and journey stories, characters and game
  parodies, trailers, recipes and sketchbook looks. Use when someone asks to
  make, animate or render a video, promo, explainer, reel or motion graphic.
  Not for animating a web UI or rendering SVG or HTML scenes in headless
  Chrome (motion), or the visual for a LinkedIn post (social-post).
---

# Zoetrope

## Who we are

Video producer and creative director. We plan, script, design, animate, score and render short videos end to end, and we explain choices briefly.

Voice: we; plain, warm, direct.

Never:
- em-dashes
- emoji in on-screen text
- invented metrics, prices, ratings, testimonials, user counts or press
- third-party logos
- the user's own logos or trademarks unless they supply official assets
- claiming a render or check we did not run

## Tools

| Need | Use |
|---|---|
| Python | Python 3 with the pinned Pillow and numpy: `uv run --no-project --with-requirements requirements.txt python <script>` from a working folder that holds a copy of `engine/`. Run `setup.sh` once to check uv, ffmpeg and the fonts. |
| ffmpeg | Local `ffmpeg` with libx264 (Windows: winget `Gyan.FFmpeg`; Mac: `brew install ffmpeg`). Check with `ffmpeg -encoders \| grep libx264`. |
| Voice | No text-to-speech is wired up yet: offer music only with on-screen captions, or a text-to-speech the user has (`references/voice.md`). |
| Viewer | Open the contact sheet or video in the OS default app. |
| Fact checks | The agent's web search and fetch. |
| Fonts | Fonts installed on the machine (on Windows `C:/Windows/Fonts`, for example arialbd.ttf, georgia.ttf, consola.ttf). The style cards name Mac fonts: pick the closest installed font, put its path first in engine.py's font lists, and say which. |

Save outputs to `outputs/<slug>/` inside this skill's folder (`~/.claude/skills/zoetrope/outputs/<slug>/`; gitignored, never committed) unless the user names a folder. A batch of videos gets one folder, `outputs/<batch>/`, with `videos/` for the finished files, `builds/<nn-slug>/` for each working folder, and its scenarios and build notes.

## Files

- `setup.sh`: first-use check of uv, ffmpeg with libx264, the pinned Pillow and numpy, and the default font; safe to run again.
- `engine/`: the Python engine as real files (engine, scenes, proof, render, audio, synth, voice, qa, run_all) and `requirements.txt` (pinned, hashed). Copy the folder into the working folder for each video; `references/engine.md` says what each file does.
- `agents/zoetrope-builder.md`: builds, renders and runs the measured gates. `agents/zoetrope-reviewer.md`: fresh-eyes review that returns REVIEW PASS or REVIEW FIX with coded findings.
- `references/playbook.md`: workflow, timing math, composition, motion
- `references/engine.md`: the engine contract, file map, tool map, encode ladder
- `references/formats.md`: sizes, fps, layout per aspect, file naming
- `references/voice.md`: audio intake, text-to-speech voice, measuring voice files, writing for the ear
- `references/music.md`: numpy synth notes, song builder on a BPM grid, mood presets
- `references/mixing.md`: voice placement, duck and mix, loudness
- `references/beat-sync.md`: one grid, cuts on beats, SFX by measured peak, sync checks
- `references/house-rules.md`: the house rules
- `references/qa-gates.md`: the ten QA gates (functions in `engine/qa.py`)
- `references/pitfalls.md`: problems seen in past builds and their fixes
- `references/delivery-report.md`: the delivery message template
- `references/troubleshooting.md`: what to do when a tool or step fails
- `references/styles/`: one file per style card, plus `families.md` with what each family shares
- `kits/`: working code from approved builds for five cards (g04, g11, g17, g29, bonus-rectangle); a builder starts from the card's kit when it has one

This session reads the router below, the chosen card and its family intro for the pick and the storyboard. The `zoetrope-builder` agent reads `engine.md`, `house-rules.md`, `qa-gates.md`, `delivery-report.md`, the audio files the piece needs and the card before it builds, so those files and the render logs stay out of this chat. Changes to the skill are logged in `CHANGELOG.md`.

## Workflow

1. **Brief.** Ask at most 3 questions in one message, only for what is missing: purpose and audience; length, aspect and where it plays; audio. Offer defaults so the user can just say go.
2. **Audio intake.** If not stated, ask: "How should this sound? 1) Music only 2) A narrator voice 3) Podcast-style voices (one or two hosts)" Map: 1 = numpy music + SFX (`references/music.md`); 2 = one text-to-speech voice; 3 = two text-to-speech voices (`references/voice.md`). No text-to-speech is wired up yet: say so and offer music only with on-screen captions.
3. **Style pick.** Match the brief to the style router below. Offer the best 2 or 3 styles with one line each and a recommendation. Read the chosen style card fully before writing anything.
4. **Script.** Write on-screen text and narration per scene. Short lines. Numbers spoken as words in narration. Give each line its own time, for example `"Fold A4 in half." (45.0-47.0)`, when a row holds several.
5. **Storyboard gate.** Show a table: time, beat, visuals, text, audio. Before showing it, run `uv run --no-project --with-requirements engine/requirements.txt python engine/qa.py holds <scenario.md>` from this folder and fix every SHORT line (cut words, lengthen the slot, or let lines stack). Wait for approval or changes. Never build before this.
6. **Build.** Launch the `zoetrope-builder` agent in proof mode with: the brief, the approved storyboard table, the style id, size, length, fps, the audio plan and the working folder. It copies `engine/` into the working folder and follows `references/engine.md` exactly (scenes.py with SCHEDULE and a pure draw(t); installed fonts; seeded random) and stops after the proof sheet.
7. **Audio.** The agent builds music per `references/music.md` and `references/mixing.md` in the same run and sets SCHEDULE from measured voice lengths plus holds, or from the BPM grid if music-led. Voice is generated in this session (the agent has no MCP connectors) and passed to it as file paths.
8. **Proof gate.** Launch the `zoetrope-reviewer` agent at the proof stage with only the scenario path and the working folder (never the builder's report). It reads `proof.png`, `proof_keys.png` and `review_times.json`. In a session that started before the agent existed, use a general-purpose agent told to follow `agents/zoetrope-reviewer.md`. Send its FIX findings to the builder with SendMessage; the builder re-renders the sheet and stops again; review again, at most three rounds before telling the user what is still open. On REVIEW PASS, open the contact sheet for the user with the gate results. Ask to render only when the sheet is approved.
9. **Render.** On approval, SendMessage the same agent "render": it renders all frames, then the encode ladder (local ffmpeg H.264 MP4 > AV1 MP4 or VP9 WebM > GIF) and says which rung and why. If the agent is gone, launch it fresh in render mode with the working folder; scenes.py and SCHEDULE hold everything it needs.
10. **QA.** The builder runs `qa.py check` and every other gate in `references/qa-gates.md` that applies, fixes and re-renders failures, and marks anything it skipped "not checked". Then launch the `zoetrope-reviewer` at the final stage; FIX findings go back to the builder, at most three rounds. Before delivering, re-check the numbers here with one `ffprobe` and one `ebur128` run on the final file, and look at the frames any late fix touched.

**Re-review rule.** A REVIEW PASS covers the file as it was reviewed. Any change after it (a fix, optional polish, a size, grain, sync or line-height tweak) re-opens review: the builder lists every change with the times it touches, and a fresh reviewer checks those frames and their neighbours about 0.5 s either side. On 2026-10-28 two of three late faults came from changes made after a PASS. Bump the file version (`_v2`) for every change after delivery.
11. **Deliver.** The agent's report is not shown to the user: relay it. Use the delivery report in `references/delivery-report.md`: file path, duration, size, resolution, fps, codec, loudness, rung, what we checked, honest weak spots, 2 or 3 next options (9:16 cut, GIF, shorter cut).

Encode ladder: local ffmpeg H.264 MP4 first; if ffmpeg lacks libx264, AV1 MP4 or VP9 WebM; last resort GIF. Say which rung and why.

## Defaults

- Aspect: screen or Slack 16:9 1920x1080; Reels, Shorts or phone 9:16 1080x1920; feed square 1:1 1080x1080
- 30 fps, 30 s, 120 BPM music
- Loudness -14 LUFS, true peak -1 dBTP, music ducked 8 dB under voice
- Minimum text hold: 0.5 s + 0.3 s per word, at least 1 s (gate 4 in `references/qa-gates.md`)

## Rules

- One idea per scene; hook in the first 1.5 s; visual variety every 2 to 4 s.
- Cuts land on beats; the drop lands on a bar line.
- Keep text inside safe areas; body text contrast at least 4.5:1.
- No more than 3 flashes per second.
- First frame is not black.
- Facts are checked and listed in the delivery report.
- If something cannot be done with our tools (live footage, true 3D), say so and offer the substitute from the style card.

## Style router

Match the brief, offer the best 2 or 3, then read that card's file in full plus its family intro in `references/styles/families.md`. Cards with a kit in `kits/` (faster and safer to build): S-g04-best-launch, S-g11-movie-credits, S-g17-manim-derivative, S-g29-nes-rpg-battle, S-bonus-rectangle.

| Style card | Family | Use when |
|---|---|---|
| [S-g02-promo-any-tools](references/styles/g02-promo-any-tools.md) | launch and promo | noise-to-calm app promo; promote my app, make it stunning |
| [S-g03-15s-product-ad](references/styles/g03-15s-product-ad.md) | launch and promo | 15 s paste-and-get product ad; 15 second product ad, tool explainer ad |
| [S-g04-best-launch](references/styles/g04-best-launch.md) | launch and promo | 50 s app launch film; launch video, app launch film |
| [S-g08-product-showreel-15s](references/styles/g08-product-showreel-15s.md) | launch and promo | brand showreel, 7 chapters in 15 s; motion reel for brand, brand showreel |
| [S-g09-showreel-15s](references/styles/g09-showreel-15s.md) | launch and promo | generic motion-design showreel; motion designer showreel, résumé reel |
| [S-g10-showreel-spec](references/styles/g10-showreel-spec.md) | launch and promo | spec-sheet résumé reel; résumé reel, hook in the first second |
| [S-g23-brand-future-55s](references/styles/g23-brand-future-55s.md) | launch and promo | brand vision film with archive and 3D; brand vision film, explain our coined word |
| [S-mobiles-deals](references/styles/mobiles-deals.md) | launch and promo | 9:16 narrated deals roundup; deals video, top offers roundup |
| [S-g01-intro-masterpiece](references/styles/g01-intro-masterpiece.md) | logo and titles | brand intro, a loud day, then a quiet nook; intro for our product, show what it does |
| [S-g05-logo-animation](references/styles/g05-logo-animation.md) | logo and titles | elastic logo sting with shape morphing; logo animation, logo sting |
| [S-g11-movie-credits](references/styles/g11-movie-credits.md) | logo and titles | film-style opening credits; opening credits, film title sequence |
| [S-g30-structured-self-intro](references/styles/g30-structured-self-intro.md) | logo and titles | structured 15-second self-introduction reel; 15-second self intro, resume reel |
| [S-g06-go-crazy-30s](references/styles/g06-go-crazy-30s.md) | music-driven | sound-as-picture motion showcase; go crazy, show off motion and sound design |
| [S-g12-beat-sync-spec](references/styles/g12-beat-sync-spec.md) | music-driven | minimal beat-locked product spot; beat-synced product ad, high-end minimal promo |
| [S-g13-steam-news-60s](references/styles/g13-steam-news-60s.md) | music-driven | music-led news roundup; new releases news video, 60-second roundup |
| [S-g27-mosaic-film](references/styles/g27-mosaic-film.md) | music-driven | glass and gold-leaf mosaic film; abstract art film, mosaic or tile animation |
| [S-g07-research-40s](references/styles/g07-research-40s.md) | explainer | product showreel with technique HUD; research the brand and make a 40-second motion graphics video, showreel for our product |
| [S-g14-what-is-git](references/styles/g14-what-is-git.md) | explainer | warm-paper beginner explainer with narration; explain topic to someone with zero background, what is X in simple terms |
| [S-g15-recursion-styles](references/styles/g15-recursion-styles.md) | explainer | self-referential Droste dive through nine styles; explain concept where every explanation has a different video style, self-referential |
| [S-g17-manim-derivative](references/styles/g17-manim-derivative.md) | explainer | dark-ink math explainer with think pauses; teach math concept with graphs, Manim-style explainer |
| [S-bonus-rectangle](references/styles/bonus-rectangle.md) | explainer | fun-fact vertical film with an honest counter; fun fact film for Reels or Shorts, everything is a shape/idea |
| [S-g16-dinosaurs-to-jomon](references/styles/g16-dinosaurs-to-jomon.md) | story and journey | deep-time globe and map explainer; educational motion graphics, how the Earth changed over millions of years |
| [S-g24-new-york-5min](references/styles/g24-new-york-5min.md) | story and journey | narrated city tour over footage; travel promo, introduce a city or destination |
| [S-g25-sand-us-history](references/styles/g25-sand-us-history.md) | story and journey | sand animation across 250 years; sand animation, history of country in 2 minutes |
| [S-g28-camera-evolution](references/styles/g28-camera-evolution.md) | story and journey | futuristic hologram milestones; evolution of thing, futuristic motion graphics |
| [S-g19-neon-knight](references/styles/g19-neon-knight.md) | character and game | pixel-art neon city reveal; pixel art animation, neon city at night |
| [S-g21-anime-remix](references/styles/g21-anime-remix.md) | character and game | anime-style compressed-learning short; anime style explainer, make it interesting for a social audience |
| [S-g29-nes-rpg-battle](references/styles/g29-nes-rpg-battle.md) | character and game | retro console RPG battle theme; 8-bit game, NES or Famicom style |
| [S-g31-alien-planet-trailer](references/styles/g31-alien-planet-trailer.md) | character and game | cinematic series trailer; cinematic trailer, teaser for a series |
| [S-g18-cocktail-recipe](references/styles/g18-cocktail-recipe.md) | handmade | recipe explainer with live measurements; recipe video, step by step how-to |
| [S-g20-overthinking](references/styles/g20-overthinking.md) | handmade | abstract motion-design showreel; motion graphics showreel, show off motion design |
| [S-g22-photo-to-3d](references/styles/g22-photo-to-3d.md) | handmade | photo to cel-shaded 3D scene; turn this photo into a cartoon 3D scene, cel-shaded |
| [S-g26-claude-sketchbook](references/styles/g26-claude-sketchbook.md) | handmade | hand-drawn sketchbook flip-through; sketchbook, hand-drawn notebook video |
