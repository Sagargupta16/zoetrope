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
license: Proprietary. All rights reserved, see LICENSE
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
| Voice | `voice.synthesize` (`references/voice.md`): offline narration, slots and word times in `narration.json`. Narrator Kokoro `af_heart` (Sagar's pick); SAPI is a robotic timing fallback. |
| Viewer | Open the contact sheet or video in the OS default app. |
| Fact checks | The agent's web search and fetch. |
| Fonts | The 14 free families 20 cards name (Inter, Nunito, IBM Plex Mono and 11 more, SIL OFL) are cached by `engine/fonts.py` in `~/.cache/zoetrope/fonts` and drawn by name: `bold="Nunito:800"` in any text helper (`python fonts.py list`; `fetch` once on a new machine, 6.8 MB). For the Mac system fonts other cards name, use a font installed on the machine (on Windows `C:/Windows/Fonts`, for example arialbd.ttf, georgia.ttf, consola.ttf): pick the closest, put its path first in engine.py's font lists, and say which. |

Save outputs to `outputs/<slug>/` inside this skill's folder (`~/.claude/skills/zoetrope/outputs/<slug>/`; gitignored, never committed) unless the user names a folder. A batch of videos gets one folder, `outputs/<batch>/`, with `videos/` for the finished files, `builds/<nn-slug>/` for each working folder, and its scenarios and build notes.

## Files

- `setup.sh`: first-use check of uv, ffmpeg with libx264, the pinned Pillow and numpy, and the default font; safe to run again.
- `engine/`: the Python engine as real files and `requirements.txt` (pinned, hashed); copy the folder into the working folder for each video. Drawing: engine, scenes (the template), transitions, grain. Sound: audio, synth, voice, voice_samples (`requirements-voice.in` holds the pins of the narration and speech check environments). Build: render, run_all (the `proof`, `full` and `audio` stages), proof (the review sheets). Checks: qa (the CLI) with its gate modules qa_scan, qa_stack, qa_sync, qa_speech, qa_registry, qa_approve, qa_purity, qa_lint, qa_audiostrip and qa_selftest (fixtures in `qa_fixtures/`); contract is what they all share; kit_index lists every helper in the engine and the kits; cards builds the router below. `references/engine.md` says what each file does.
- `agents/zoetrope-builder.md`: builds, renders and runs the measured gates. `agents/zoetrope-reviewer.md`: fresh-eyes review that returns REVIEW PASS or REVIEW FIX with findings ranked P0, P1 and P2.
- `references/playbook.md`: workflow, timing math, composition, motion
- `references/engine.md`: the engine contract, file map, tool map, encode ladder
- `references/formats.md`: sizes, fps, layout per aspect, file naming
- `references/voice.md`: audio intake, text-to-speech voice, measuring voice files, writing for the ear
- `references/music.md`: numpy synth notes, song builder on a BPM grid, mood presets
- `references/mixing.md`: voice placement, duck and mix, loudness
- `references/beat-sync.md`: one grid, cuts on beats, SFX by measured peak, sync checks
- `references/house-rules.md`: the house rules
- `references/qa-gates.md`: the QA gates and their Q codes (functions in `engine/qa.py` and its gate modules)
- `references/pitfalls.md`: problems seen in past builds and their fixes
- `references/delivery-report.md`: the delivery message template
- `references/troubleshooting.md`: what to do when a tool or step fails
- `references/styles/`: one file per style card, plus `families.md` with what each family shares
- `kits/`: working code from approved builds for five cards (g04, g11, g17, g29, bonus-rectangle); a builder starts from the card's kit when it has one

This session reads the router below, the chosen card and its family intro for the pick and the storyboard. The `zoetrope-builder` agent reads `engine.md`, `house-rules.md`, `qa-gates.md`, `delivery-report.md`, the audio files the piece needs and the card before it builds, so those files and the render logs stay out of this chat. Changes to the skill are logged in `CHANGELOG.md`.

## Workflow

1. **Brief.** Ask at most 3 questions in one message, only for what is missing: purpose and audience; length, aspect and where it plays; audio. Offer defaults so the user can just say go.
2. **Audio intake.** If not stated, ask: "How should this sound? 1) Music only 2) A narrator voice 3) Podcast-style voices (one or two hosts)" Map: 1 = numpy music + SFX (`references/music.md`); 2 = one voice, the narrator Kokoro `af_heart` (`references/voice.md`); 3 = two voices, not built yet: offer 1 or 2 (a second voice waits for Sagar's pick from `outputs/voice-samples-2026-11-03/`).
3. **Style pick.** Match the brief to the style router below. Offer the best 2 or 3 styles with one line each and a recommendation. Read the chosen style card fully before writing anything.
4. **Script.** Write on-screen text and narration per scene. Short lines. Numbers spoken as words in narration. Give each line its own time, for example `"Fold A4 in half." (45.0-47.0)`, when a row holds several. For a voiced piece, synthesize the lines now into `<working folder>/narration/`, clear every FIX `qa.py speech` finds in it, and time the scenes from the slots in `narration.json`.
5. **Storyboard gate.** Show a table: time, beat, visuals, text, audio. Before showing it, run `uv run --no-project --with-requirements engine/requirements.txt python engine/qa.py holds <scenario.md>` from this folder (`--profile caption` for lines read while the picture moves, `slow` for dense explainer cards) and fix every SHORT line (cut words, lengthen the slot, or let lines stack). Wait for approval or changes. Never build before this.
6. **Proof.** Write that brief to `<working folder>/brief.md` first (create the folder): a builder relaunched after a restart reads it. On a laptop, keep the charger in or the app's Keep awake on battery power setting on: on 2026-10-29 the PC slept on battery for 6.5 of a build's 8.4 hours, and a closed lid sleeps whatever the setting. Launch the `zoetrope-builder` agent in proof mode with: the brief, the approved storyboard table, the style id, size, length, fps, the audio plan and the working folder. It copies `engine/` into the working folder, writes scenes.py (one function per scene, a pure draw(t), seeded random, the text and cue registry), runs `run_all.py proof` and stops. Its report quotes the PROOF line: `PROOF: PASS`, `PROOF: FIX (n)` (exit 1) or `PROOF: NOT CHECKED (n)` (exit 2), over the rows for the first frame (Q501), the text gates and the text recorder (Q200 to Q404), the purity gate (Q1201) and the lint (Q1202 to Q1206, Q904, Q905). Review starts on `PROOF: PASS`; a row the builder could not clear comes back under `blocked`.
7. **Audio.** The agent builds the music in the same run (`references/music.md`, `references/mixing.md`) on the picture's BPM grid, or sizes the scenes from the narration slots. Voice is made in this session (step 4) and passed to it as `narration/narration.json` and `narration/narration.wav`.
8. **Proof gate.** Launch the `zoetrope-reviewer` agent at the proof stage with only the scenario path, the working folder and a reviewer id (stage and round, for example `proof-1`), never the builder's report. It reads the numbered cells of the `proof_keys*.png` pages, `proof_strips*.png` when present, `proof_gantt.png`, `review/audio.png` once mix.wav exists, `proof.png` and `review_times.json`. In a session that started before the agent existed, use a general-purpose agent told to follow `agents/zoetrope-reviewer.md`. REVIEW PASS means no P0 is left. On REVIEW FIX, save all its findings as one numbered list, each with its fix, to `review/fixes_<n>.md` in the working folder, then send that list to the builder with SendMessage; it runs the proof again and stops; then a fresh reviewer. A FIX row or P0 gets at most three rounds, a P1 or P2 note two; then tell the user what is still open. On REVIEW PASS, open the contact sheet for the user with the gate results and any P1 findings. Ask to render only when the sheet is approved.
9. **Render.** On approval, SendMessage the same agent "render". `run_all.py full` draws every frame straight into video.mp4 (in passages when one call would pass about 4 minutes), makes and masters the audio, muxes, runs every gate and ends with an `APPROVAL:` line and one `DELIVERED <path> (<MB>, <s>, <LUFS>, <dBTP>)` line; the report quotes both. A file with a FIX or NOT CHECKED row becomes `<name>.rejected.mp4` (its REJECTED line names the rows); a run that broke before its verdict leaves `<name>.unchecked.mp4`; neither is reviewed or delivered. A sound-only fix is `run_all.py audio`: re-master and re-mux on the same picture; it refuses a video.mp4 older than scenes.py. If the agent is gone, launch a fresh builder in resume mode (Stopped builders, below).
10. **QA.** The builder runs `qa.py check` with `--json qa.json` and every other gate in `references/qa-gates.md` that applies, fixes and re-renders failures, and marks anything it skipped "not checked". Then launch the `zoetrope-reviewer` at the final stage (scenario, working folder, reviewer id); its findings go back to the builder as in step 8, with the same round limits. On REVIEW PASS, save the reply verbatim as `<working folder>/review/reply_final_<n>.txt` and run `qa.py approve --review review/reply_final_<n>.txt` in the working folder: `APPROVED` binds the review to the file; `REFUSED` says why (a reply without its stage, file and written time, a FIX or NOT CHECKED row in qa.json, a qa.json older than the file) and the fix. Carry the reply's `cannot verify` items into the report's not-checked line.

**Re-review rule.** Approval is per content hash, not per conversation turn. `approved/` keeps what the reviewer passed: the file's sha256 and decoded-picture hash, every frame digest, the raw mix in 100 ms blocks, the source and the environment. Any later change (a fix, optional polish, a size, grain, sync or line-height tweak) reopens review by itself: `run_all.py` prints `APPROVAL: stale: ...` and `qa.py check` a Q1301 STALE APPROVAL row for each scene whose key frames changed. The builder lists every change with the times it touches and runs `qa.py diff --expect <those windows>`: Q1303 FIX names any frame or 100 ms audio block that changed outside them, or a window that saw no change, and `review/` gets before, after and difference triptychs. A fresh reviewer checks those frames and about 0.5 s either side on the encoded file, and its PASS is approved again. Audio only (the decoded picture unchanged) needs the audio rows and cue sync; a new frame size, or a Python, Pillow, numpy or font change that moved a frame (Q1304), needs a full review. On 2026-10-28 two of three late faults came from changes made after a PASS. Bump the file version (`_v2`) for every change after delivery.
11. **Deliver.** `qa.py verify <the DELIVERED path>` must print `VERIFY: SAME`. Re-check the numbers here with one `ffprobe` and one `ebur128` run on that file, and look at the frames any late fix touched. The agent's report is not shown to the user: relay it. Use the delivery report in `references/delivery-report.md`: file path, duration, size, resolution, fps, codec, loudness, rung, what we checked, honest weak spots, 2 or 3 next options (9:16 cut, GIF, shorter cut).

**Stopped builders.** An app restart stops every background agent: seven builders on 2026-10-30. When a builder ends without its report, launch a fresh `zoetrope-builder` with `resume` and the working folder only. It reads `brief.md`, `build_state.json` (the last `run_all.py` stage; `running` means it stopped there), the newest `review/fixes_<n>.md` and the gate files, keeps every finished scene in scenes.py and score.py, and continues from the first unfinished step.

Encode ladder: local ffmpeg H.264 MP4 first; if ffmpeg lacks libx264, AV1 MP4 or VP9 WebM; last resort GIF. Say which rung and why.

`qa.py selftest [--quick] [--only CODE[,CODE]] [--keep]` checks the gates themselves, not a video: after any edit to the engine or a qa module, run it from a folder made with `cp -r engine/. <folder>/` (it needs `qa_fixtures/`). It must end `SELFTEST: PASS (<n> fixtures, <k> of <k> codes covered, 0 expected gaps)`; exit 1 means a fixture missed or misread its planted fault, 2 a code with no fixture or a fixture missing. It takes under a minute; `--quick` skips the template's full renders (about 28 s).

## Defaults

- Aspect: screen or Slack 16:9 1920x1080; Reels, Shorts or phone 9:16 1080x1920; feed square 1:1 1080x1080
- 30 fps, 30 s, 120 BPM music
- Loudness -14 LUFS, true peak -1 dBTP, music ducked 8 dB under voice
- Minimum text hold: the longest of 1 s, 0.5 s + 0.3 s per word, and characters / 20 + 0.5 s (the display pace; `HOLD_PROFILE` picks caption or slow; gate 4 in `references/qa-gates.md`)

## Rules

- One idea per scene; hook in the first 1.5 s; visual variety every 2 to 4 s.
- Cuts land on beats; the drop lands on a bar line.
- Keep text inside safe areas; body text contrast at least 4.5:1.
- No more than 3 flashes (WCAG 2.2 general or red) in any second; `qa.flash_window` over every wipe, dip, hit and strobe.
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
| [S-g09-showreel-15s](references/styles/g09-showreel-15s.md) | launch and promo | generic motion-design showreel; motion designer showreel, resume reel |
| [S-g10-showreel-spec](references/styles/g10-showreel-spec.md) | launch and promo | spec-sheet resume reel; resume reel, hook in the first second |
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
