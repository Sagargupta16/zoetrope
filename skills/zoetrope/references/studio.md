# The studio engine

The second engine in this skill, in `<skill>/studio/`. It makes narrated films of about 60 to 180 s at 1080x1920 and 30 fps: every frame is an HTML page drawn in headless Chrome as a pure function of time, over pictures and clips made on a local ComfyUI, with captions lit word by word on the voice, a style lint that runs before any reader sees the film, and a per-still checklist. The Python engine in `engine/` (frames drawn with Pillow) is the other route; this one is for a film that is mostly generated pictures, drawn devices and a voice.

`studio-checklist.md` (beside this file) lists every rule below on one line, in the order a builder walks a film. The rules are tagged: `[lint Lxx]` is checked by `studio/lint.py`, `[check Cx]` is a question in `proof/checklist.md` that a person answers per generated still, `[qa Pxx]`, `[qa Fxx]` and `[qa Vxx]` are rows of `studio/qa.py`, and `[look]` is what only a person can judge. A rule applies to every shot of a film, not to the shots someone named.

## Set up a batch

A batch is a folder that holds one `batch.json`, a frozen copy of the studio and several films. Each batch copies the studio, so a kit change moves pixels only in new batches and a running film is never switched.

```text
python <skill>/studio/studio.py new-batch outputs/<batch> --config <skill>/studio/batch.example.json
```

`new-batch` copies every file of `studio/` (not `__pycache__`) into `<batch>/studio/`, copies the skill's `engine/` into `<batch>/engine/` (it says so when there is none), copies this manual and the rule list into `<batch>/docs/` (so a batch keeps the manual of the kit it holds, and the workflow scripts read it from there), copies the config to `batch.json`, makes `builds/` and `videos/`, and writes `SNAPSHOT.txt` (the sha256 of every copied file of `studio/`, `engine/` and `docs/`). It refuses to overwrite a batch (exit 3). Edit `batch.json` first (next section). Then, from the batch folder:

- Audio engine. `studio/audio.py` runs on the copy of the skill's audio engine in `<batch>/engine/` (the batch's `engine` key can name another folder) and needs its `voice.py`, `synth.py` and `audio.py`, with the voice's own environment (`voice.md`, beside this file).
- Python for the studio: `studio/requirements.in` pins playwright, pillow and numpy; `studio/requirements.txt` is its hashed lock. `python studio/studio.py <command>` (written `studio.py <command>` below) starts that environment itself: when `voice`, `render`, `sheet` or a check other than `plan`, `lint` and `stills` finds one of the three packages missing, it runs the same command again through `uv run --no-project --with-requirements studio/requirements.txt` (once; the child carries `ZOETROPE_STUDIO_ENV`). Without uv on the path it carries on in the interpreter it has, and a check that needs a missing package reads NOT CHECKED. The other commands need the standard library only. A script run on its own (`qa.py`, `render.py`, `sheet.py`) needs the environment spelled out. Chrome must be installed (`render.py` launches `channel="chrome"`), with ffmpeg and ffprobe on the path.
- Fonts. `stage.css` names Barlow Condensed (SemiBold, Bold, ExtraBold, Black), Poppins (SemiBold, Bold), Archivo Black, Inter and IBM Plex Mono (Regular, SemiBold) under `/studio/fonts/`. The renderer serves each file from `<batch>/studio/fonts/` when the batch keeps its own copy, else from the font cache that `engine/fonts.py fetch` fills (`~/.cache/zoetrope/fonts`, pinned and checked by sha256; Inter's file there is `Inter[opsz,wght].ttf`). A missing file is fetched once before Chrome starts; if it still is missing the command stops and names the file.
- Pictures and clips need a running ComfyUI (`comfy.url`) with comfy-cli, the Z-Image Turbo workflow for stills and LTX-2.5 image to video for clips (`studio/comfy/*.json`).
- Music: `music_dir` holds licensed tracks as `<theme>/<track>.mp3`; a film names one in `script.json`.

A batch keeps the engine it was made with. To give it a newer one, run the NEWER engine's command line: `python <newer>/studio/studio.py upgrade <batch> [--force]`. It replaces `studio/`, `engine/` and `docs/`, writes `SNAPSHOT.txt` again and prints every file that changed, was added or was removed (a tool's cache, `__pycache__`, a `.pyc` or a dot-folder such as `.ruff_cache`, is neither copied nor written into the snapshot, and such a line in a snapshot of an older engine is not read); `builds/`, `videos/` and `batch.json` are not touched, and the copy it replaced is kept in `<batch>/engine-before-upgrade/` (one generation). It refuses (exit 3) when it is run from the batch's own copy, when the batch has no `SNAPSHOT.txt` (`REFUSED no SNAPSHOT.txt: the copy cannot be checked for edits`), and when a file of the batch's copy was edited, added (a font put in `studio/fonts/`, say) or deleted since its snapshot: `REFUSED N file(s) of the batch's copy changed since its snapshot (<file> (changed|added|missing), up to five)`. `--force` goes ahead and prints `dropped a local edit`, `dropped an added file` (it stays in `engine-before-upgrade/` until the next upgrade) or `dropped a local deletion` for each, and with no snapshot `note: there was no SNAPSHOT.txt, so the copy was replaced without an edit check`. A file under a dot-folder (a tool's cache such as `studio/.ruff_cache/`), under `__pycache__` or ending `.pyc` is never an added file. The parts move by rename only, so an upgrade never leaves half an engine: when it cannot clear its own folders (an open file) it exits 2 with `NOT CHECKED upgrade did not start, the batch's copy was not touched`; when a move fails it puts the old parts back and exits 2 with `NOT CHECKED upgrade stopped, the batch's copy is as it was`, or, if putting one back fails too, names it and says to move its old copy in `engine-before-upgrade/` back by hand. A batch made when the engine still held a `studio/SNAPSHOT.txt` prints `removed: studio/SNAPSHOT.txt` at its next upgrade. Never upgrade while a builder is using the batch.

Check a change to the studio itself with `python -I studio/selftest.py --quick` (the lint rules, shotkit, the workflow scripts' syntax (and no `Date.now`, `new Date`, bare `Date(` or `Math.random` however spaced, which throw in a workflow), the film comparison's arithmetic and, with ffmpeg on the path, a moved cut on two test films and fine detail against a change on four, a drawn probe film's timeline and the command line's contract on a scratch batch made from the probe (`command line: stale, failed build, exit codes, script, slugs, dates, bare plate, keep, review, diff, upgrade`: refusals, a bare-plate run, `review save` and `answers`, `diff` and an `upgrade` that fails midway included), with no Chrome; it needs `node` on the path for the workflow scripts and ends `STUDIO SELFTEST: PASS (12 parts)`). `--render` (in the studio's environment) adds four rendered frames of the probe compared with `selftest/golden/<os>/frames.json`: by PNG digest first, and a frame whose digest differs by the mean colour of each 60 px block, within 0.25 of 255. Chrome's GPU rasteriser is not bit-stable (two runs of the same code differ by one or two levels on a few edge pixels of large type), so its line says how many frames matched by digest and how many by blocks. It also runs `look` on a test film built like a rendered one, and shoots a short film of the kit's carried overlays and end card options (`selftest/options/shots.json`) to check the boxes on the frames either side of each cut (15 parts in all). `--bless` rewrites the golden after you have looked at the frames.

## The pipeline, in order

| # | Stage | Command | Reads | Writes |
|---|---|---|---|---|
| 1 | New film | `studio.py new <batch> 01-slug --title T --topic X [--date D]` | `studio/templates/` | `builds/01-slug/` with `brief.md`, `script.md`, `shots.py`, `caption.md` |
| 2 | Brief and facts | by hand | the topic | `brief.md` (staging, who watches, picture limits), `facts.md` (every number, name and date with two sources) |
| 3 | Script | by hand | `brief.md`, `facts.md` | the table in `script.md`: one spoken line per row |
| 4 | Script file | `studio.py script <build> --theme T --track K` | the first table of `script.md` that has an `id` column, the batch's accent, tag and voice speed | `script.json` (with the music bed; `render` refuses a `script.json` that names none) |
| 5 | Voice | `studio.py voice <build>` | `script.json` | `narration/voice.wav`, `narration/layout.json` (every line, word and caption token with its time), `cues.txt`, `proof/qa_speech.log` (what a speech recogniser heard, against the script) |
| 6 | Cues | read `cues.txt` (`python studio/build.py cues <build>` prints it again) | `narration/layout.json` | each line with `index:word@seconds`, for writing cues |
| 7 | Shot list | edit `shots.py`, run `python -I shots.py` in the build folder | shotkit | `shots.json`, `proof/blocks.md` |
| 8 | Stills | `studio.py stills <build>` | `shots.json` | `media/<id>.png`, `media/state.json`, `proof/checklist.md` (written again by `build` and by `check frames`) |
| 9 | Clips | `studio.py clips <build>` | `shots.json`, the stills | `media/<id>.mp4`, `media/<id>/f0001.jpg` ..., `media/<id>.wav` |
| 10 | Timeline | `studio.py build <build>` | `shots.py`, `shots.json`, `script.json`, `narration/layout.json`, `media/` | `timeline.json` (none is left when the build fails), `proof/checklist.md`, `proof/shots_table.md`; prints the shot table and warnings |
| 11 | Checks | `studio.py check <build> all` (or one stage) | the timeline, the frames it shoots, the answers file | `proof/qa_<stage>.json`, `proof/frames/`, `proof/sheet_NN.png` |
| 12 | Look | `studio.py sheet <build> --times a,b,c` | `proof/frames/` | `proof/strip_times.png` and other strips |
| 13 | Render | `studio.py render <build>` | `timeline.json`, `script.json` (its music), `proof/qa_plan.json`, `proof/qa_lint.json`, `accept.json` if present | `out/video.mp4` (the picture), `out/<slug>.mp4` with the mix, then the file check and `proof/shots_table.md` |
| 14 | Review | readers use `studio/templates/readers/*.md`; `studio.py review save` and `answers` | the file, the sheets, the shot table | `proof/reviews/`, `proof/<stage>_answers.md` |
| 15 | Look, then package | `studio.py look <build>` (open every sheet), then `studio.py package <build>` | `proof/look/` sheets newer than the video, `post.json`, `out/<slug>.mp4`, and `proof/qa_plan.json`, `qa_lint.json`, `qa_frames.json`, `qa_lint_frames.json`, `qa_stills.json` and `qa_file.json`, each newer than what it checked | `videos/<slug>.mp4` and `videos/<slug>.json` |

`studio/workflows/film.js` runs stages 4 to 14 as one workflow with fresh agents (`args`: `batch`, `build` (or `film.build`: give either, or both with the same value, else it throws), `from` (one of `voice`, `build`, `prepare`, `review` or `fix`, default `voice`; any other value throws before an agent starts), `rounds`, `today`, `film` and optionally `clips` (`{min, max}`, default 8 to 12: how many stills the first builder plans motion for and the second turns into clips), `models` and `efforts` (one per stage: `voice`, `build`, `stillCheck`, `checks`, `prepare`, `gate`, `reader`, `fix`; by default the builders and readers run on `opus` at `high`; the voice, still check and gate steps run on `sonnet` (the still check at `medium`, the gate at `low`), and a second gate attempt runs as the `checks` stage, on `opus` at `high`); `film.music` is `{theme, track}`, which the voice step passes to `script` and without which a run from `voice` stops at once). Its build step runs `build`, `check plan`, `check lint` and `check frames` before the still check, so `proof/checklist.md` names the frames to open; its checks list adds `check lint-frames`; its gate runs `check all` and passes when the exit code is 0 and the closing line reads `check all: exit 0` (one retry), before the first readers on every run that reaches review, a resume from `review` included; a resume from `fix` starts with the fix builder, whose step G runs `check all`. A film is ready when all three readers returned, each says READY and none lists a P0 (a READY verdict over a P0 finding is not ready); a reader that did not return is asked once more, and a round in which one is still missing is not judged: the run stops (`stopped` is `readers<round>`), so no fix round is spent on it and no film passes with a lens unread, each review line of the log ends with the rule that decided, and the result carries `ready`. An agent that returns nothing stops the run before the next one, with `stopped` set to `voice`, `build`, `still-check`, `checks`, `prepare`, `gate` or `fix<N>`. `script-prep.js` (`args`: `batch`, `build`, `slug`, `topic`, `today`, and optionally `reference`, `readFiles`, `sourceNotes`, `factsExtra`, `draftRules`, `scroller`, `skeptic`, `researcher`) and `facts-fill.js` prepare a script and its fact table; `researcher` names a read-only web research agent type of your own for their fact lanes, which otherwise run as plain workflow agents; `script-prep.js` also takes `models` and `efforts` (`facts`, `draft`, `study`, `trace`, `keep`) and stops at the first step that returns nothing (`stopped` is `facts`, `draft`, `study (<missing lanes>)`, `revise` or `trace`, and the result keeps what the steps before it made); `facts-fill.js` takes `models: { facts }` (default `sonnet`). A research agent type that is read-only returns its text and writes no file, so in `script-prep.js` and `script-revise.js` every research lane is followed by a small agent (`keep`, by default `haiku` at `low`) that saves the lane's reply when its file is missing (`facts.md`, a `study_fact_trace_*.md`), or adds a fact lane's rows to `facts.md` when they are not in it, and changes nothing else. A trace row that says a source does not state something names the words it searched the saved page for. Every agent of these scripts names its model and its effort, because an agent that names neither runs on the session's model at the session's effort: on the first film the four building agents ran 418 minutes, of which their commands took 59, and script preparation took 173 minutes without a model or an effort on its writing agents and 47 with them (the same script, nine agents, on the next film). `script-revise.js` is for the step after `script-prep.js`, when the owner has read the script and ruled on its open points (`args`: `batch`, `build`, `slug`, `topic`, `today`, `rulings` (the decisions, as text) and optionally `lanes` (one research task each, for a fact a ruling needs; its rows go into `facts.md`), `version` (default 3), `researcher`, `readFiles`, `skeptic`, `models` and `efforts`). The fact lanes run first, one writer applies the rulings and keeps the script it replaces as `script_v<n>.md`, an editor for the ear, a skeptic and a fact tracer read the new version, the writer answers every P0 and P1 once, and a last trace checks the final lines. It stops, with `stopped` set, before the revision when a fact lane fails (`facts`, `missing` names the lanes), when the revision returns nothing (`revise`), when an ear, skeptic or fact-trace lane does not return (`study`, `missing` names it), when the writer returns nothing in the answer round (`answer`, and no final trace runs) and when the final trace returns nothing (`trace`). Both traces return a schema, `{ rows: [{ line, verdict (holds, fix or wrong), source, corrected }], single_source }`, so `trace` and `final_trace` in the result are that object, not text (the `study_fact_trace_v<n>.md` files are still written as tables); the answer round runs when there is a P0 or P1 or a line without a `holds` row. `polish.js` is for a film whose readers all said READY while findings are still worth mending (`args`: `batch`, `today`, `film` (`build`, `slug`, `seconds`, `topic`, `special`), `items` (each `id` (a number is read as its string), `where`, `problem` and `ruling`, the owner's decision the builder follows) and optionally `pass`, `pictures`, `clips` (how many new clips the builder may make, default none), `also`, `models` and `efforts` (`builder`, `checker`, `gate`) and `lenses` (one checker each; by default a viewer and design checker and an honesty checker)). One builder first keeps the film (`keep <build> polish<N>`), then makes only the named changes in one dated block, runs the checks, renders, gates and runs `changed`. Then, side by side, one agent runs `check all` again and one fresh checker per lens rules on every item from frames of the new file, runs `changed` itself (the old shot times come from `out/<slug>_before_polish<N>.timeline.json`), lists anything that moved in a shot no item names and any new P0 or P1 inside a touched shot. It returns `ok`, `fixed`, `open`, `regressions` and `new_findings`; for what is left, run it again with the next `pass` and those as its items. Use it in place of another fix round: a fix round sweeps the whole film and brings three readers back.

Order matters in five places:

- Edit `shots.py`, then `build`, then `check <build> plan` and `check <build> lint`, then `render`. One rule says when `timeline.json` is stale: any of `shots.py`, `shots.json`, `script.json`, `graphics.js`, `narration/layout.json` or the `media/<id>.png` or `.mp4` of a shot the timeline uses is newer than it. Every command that reads the timeline (`check` in every stage, `render`, `table`, `sheet --times`, `package`) then refuses with exit 3, prints `REFUSED timeline.json is older than <file>: run build again` and runs nothing; remaking a still makes the timeline stale too. A build that fails (in `shots.py`, or in `build.py` on a bad shot) leaves no `timeline.json` behind, so nothing downstream reads an old one.
- `render` also refuses (3) when `script.json` names no `music.theme` and `music.track` (`script <build> --theme T --track K` writes them), and when `proof/qa_plan.json` or `proof/qa_lint.json` is missing, older than `timeline.json` or holds a FIX row that `accept.json` does not name (below).
- The stills must be looked at, and `proof/checklist_answers.json` filled, before `check stills` can pass. A still remade after its answers were written (its `media/<id>.png` is newer than the answers file) counts as a FIX, so answer it again.
- A count needs frames at its own moments, 0.1 s before and after its landing. `check <build> frames` shoots them by itself for every `number` with a `landAt` and for the `until` of every `rail` and `years`, so `check <build> lint-frames` (the lint's frames tier on the frames that are there) has them. Frames shot before the last `build` count as missing: `check lint-frames` then prints `NOT CHECKED L00 proof/frames was shot from an older timeline.json` and exits 2 until `check frames` runs again. When L07 notes "no frame at N count moment(s)", its fix line is `python studio/studio.py check <build> frames`.
- `sheet --times` reads frames that `check frames` or `qa.py frames --times` has already shot into `proof/frames/`, and refuses (3) when the timeline is stale.

## Command line

`python <batch>/studio/studio.py <command>`, in the studio's environment (above). Every stage module is imported inside its handler, so one module that fails to import does not block the others. The narration, the mix and the file check run as their own processes, because the audio engine has its own `qa.py`, `audio.py` and `render.py`.

| Command | Arguments | What it does |
|---|---|---|
| `new-batch` | `<dir> --config <json>` | Makes a batch (above). |
| `new` | `<batch> <nn-slug> --title T --topic X [--date YYYY-MM-DD]` | Makes `builds/<nn-slug>/` from the templates, replacing `{title}`, `{topic}` and `{slug}`, and `{date}` in the heading with `--date` (by default today's local date, the day the workflows call `today`; a malformed one is 64: `argument --date: <text> is not a date like 2026-11-25`). The name must look like `01-some-name` (64 when it does not); an existing folder is refused (3), and so is a name whose slug (the name without its number) another build of the batch already has: `REFUSED 05-tables already has the slug tables`. |
| `status` | `<batch>` | One row per build and one column per stage (`script`, `voice`, `shots`, `stills`, `lint`, `frames`, `render`, `review`), each `missing`, `done` or `stale` from file existence and modification times (the stale test is the one above); `script` is `stale` only when `script.md` is the newer file and its table no longer holds the lines of `script.json` or its Lexicon table no longer matches the `lexicon` (the voice step writes its measured read under the table, which changes no line); `stills` reads the shot list and `media/state.json` instead: `done` when every shot that asks for a still has its picture drawn from its present prompt, `still_defaults` and look (the hash recorded beside it is the one `stills` computes now), `stale` while one has none or was drawn from an older prompt, `missing` when none is made; a shot adopted with a clip and no still counts as made. Exit 0; 2 when the batch or its `batch.json` is missing. It needs no `comfy` key. |
| `script` | `<build> [--theme T] [--track K] [--start S] [--fade-out F] [--duck-db D]` | Reads the first table of `script.md` whose header has an `id` column, down to that table's last row (every other table, before or after it, is ignored), into `script.json`: the lines, the title from the file's first heading, the batch's accent and tag, and the batch's voice speed. The `slug` is the build folder's name without its number (`02-blind-spot-test` gives `blind-spot-test`), or the slug an earlier `script.json` holds. The music flags fill `music`; run again with the flags you want to change, since an earlier `music` and `voice` in `script.json` are kept (the batch's `voice.speed` fills only a key the film's own `voice` lacks). A table of `script.md` whose header has a `word` and a `say` column (the template keeps one under `## Lexicon`) becomes the `lexicon`, and the closing line names its words; with no such table the `lexicon` of an earlier `script.json` is kept, as are its `lead` and `progress`. A word the table no longer lists is dropped with a `NOTE lexicon:` line, never silently. Without a theme and a track it ends with `(no music: render refuses until script <build> --theme <theme> --track <track>)`. |
| `voice` | `<build>` | Narrates `script.json` through the engine's voice and lays the lines out on one clock, writes `cues.txt`, then runs the engine's speech check (a recogniser writes down what each line says; `proof/qa_speech.log`). Exit 1 when a word is misheard: respell the `spoken` column of that line and run `script` and `voice` again. Exit 2 when the voice or the check could not run. |
| `stills`, `clips`, `adopt` | `<build> [--only s03,s07] [--reseed] [--source <path>]` | Calls `gen.py`. One shot at a time, each saved as it is made; a shot whose files exist and whose prompt is unchanged is skipped. `--only` names shots (for `stills` and `clips` a comma list); `--reseed` is read only together with `--only` and adds 1 to the seed of those shots. `stills` and `clips` need the batch's `comfy.home`. `adopt` takes the still and clip of one shot from another build's `media/`: `--only` names exactly one shot (a list or an unknown id is 64) and `--source builds/<probe>/media/<name>` has no suffix and must have a `.png` or an `.mp4` (else 2, nothing written); it needs no `comfy` key. A build with no `shots.json` is 2 (`no shots.json in <build>`) and no folder is created. After a `stills` run that passes, `proof/checklist.md` is written. |
| `build` | `<build>` | Deletes any old `timeline.json` first, then runs `shots.py` in the build folder (if present), writes a new timeline, the shot table and `proof/checklist.md` (each still's uses with the frame to open). A failed build leaves no `timeline.json`: `shots.py` failing prints `FIX shots.py failed` (1), a shot `build.py` refuses (a `number` whose `value`, `from` or `to` is not a number, a `tin` `d` that is not a number, a `bright` that is not a number above 0, a shot id used twice) prints `FIX timeline build failed: <message>` (1), and a missing build folder or a missing `script.json`, `narration/layout.json` or `shots.json` is 2. |
| `check` | `<build> plan\|lint\|frames\|lint-frames\|stills\|file\|all` | Runs the named check (the stage may come before the build). `lint` is the static tier; `lint-frames` is the lint's frames tier on the frames `frames` shot. `all` runs `plan`, `lint`, `frames`, `lint-frames`, `stills` and `file`, printing `check <stage>: exit <n>` for each and then `check all: exit <n>`, the worst one, which is also the exit code (the line a gate reads). A missing build folder is 2; an unknown stage is a usage error (64); a stale timeline is refused (3, above) before any stage runs. A check that cannot run, or that crashes (`NOT CHECKED <stage>: <error>`), exits 2 and deletes its older `proof/qa_<stage>.json`, and `all` goes on to the next stage. `check frames` shoots a frame 0.1 s before and after every count's landing and rewrites `proof/checklist.md` with the frames just shot. `check stills` needs the build folder and its `shots.json` (else 2, nothing created). Rows that `accept.json` names are printed as accepted and left out of the exit code (below). |
| `render` | `<build> [--workers N] [--maxrate K]` | Needs `timeline.json` (2 when missing). Refuses (3) when the timeline is stale, when `script.json` names no music (`REFUSED script.json names no music: run script <build> --theme <theme> --track <track>`) or when the plan and lint results are missing, older than the timeline or not at 0 FIX (a FIX row named in `accept.json` is printed as accepted and does not refuse); otherwise renders the frames to H.264 (`out/video.mp4`), mixes the sound into `out/<slug>.mp4`, runs the file check and writes the shot table. Exit 2 when the render or the mix fails. `--workers` and `--maxrate` override `render.workers` and `render.maxrate` of `batch.json`. |
| `sheet` | `<build> (--times a,b \| --clip id \| --media id,id) [--height 700]` | Joins pictures side by side into one strip in `proof/`: frames at times (cropped to y 250 to 1300), six frames of one clip, or named stills. `--times` refuses a stale timeline (3) and takes only numbers (64 otherwise). |
| `table` | `<build>` | Writes `proof/shots_table.md`: per shot its times, what is under it, the words spoken inside it and every on-screen text with the time it appears. Refuses a stale timeline (3). |
| `review` | `save <build> <file> --stage S`, `answers <build> --stage S` | `save` splits a readers' JSON file (a list of readers with a `key` or `reader`, an object keyed by reader, or the result file a finished `film.js` run leaves, of which it takes the last round of its history that has at least one reader) into `proof/reviews/<stage>_<reader>.json`; a second reader of the same name (after sanitising) is saved as `<stage>_<name>-2.json` with a `note:`, never over the first. A file with no reader (a run that stopped before its readers, a history with no round holding one, an empty list, an item that is not an object, an unknown shape) exits 1, writes nothing and prints `FIX nothing saved from <file>: <reason>`. `answers` writes each reader's verdict and findings as checkboxes with an `Answer:` line to `proof/<stage>_answers.md`; with no saved file for that `--stage` it exits 2 (`NOT CHECKED no proof/reviews/<stage>_*.json in <build>: run review save with that --stage first`) and writes nothing. Any other action is 64; a build folder that does not exist is 2 and is never created. |
| `look` | `<build> [--step 1.25]` | The owner's look at the finished film: one frame every `--step` seconds of `out/<slug>.mp4` and its last frame (of the picture: the sound of a finished film runs a little longer), each with its time, tiled five by three on `proof/look/look_NN.png` (the sheets of an earlier look are removed first). Exit 2 with no film, no ffmpeg or no Pillow, and when ffmpeg writes no frame for one of the times (an empty cell would pass for a dark frame). Every reader saying READY means no reader found a fault, not that the film is good, so `package` refuses a film whose sheets are missing or older than the video. |
| `package` | `<build>` | Ships only a checked film. Exit 2 with no `post.json`, `timeline.json` or `out/<slug>.mp4`; refuses (3) when the timeline is stale, when `out/<slug>.mp4` is older than `timeline.json` (`run render again`), or when `proof/qa_plan.json`, `qa_lint.json`, `qa_frames.json`, `qa_lint_frames.json`, `qa_stills.json` or `qa_file.json` is missing, older than what it checked (the timeline; the frames for `qa_lint_frames.json`; the video for `qa_file.json`), holds a NOT CHECKED row or holds a FIX row `accept.json` does not name, each named with the `check` to run; and when `proof/look/` holds no sheet newer than the video (run `look` and open every sheet). Then it checks the file and `post.json`, and copies the video and a JSON of the post to `videos/`. It prints the title, the caption's first line and the counts (caption characters, hashtags, sources): read them before an upload. Uploads nothing. |
| `keep` | `<build> <name>` | Copies `out/<slug>.mp4` and `timeline.json` to `out/<slug>_before_<name>.mp4` and `.timeline.json` before a pass changes them. A copy that exists is left alone (exit 0), so a pass that starts twice keeps the film from before its first start. Exit 3 when `timeline.json` is newer than the film (that film was not rendered from it), 2 when there is no film, 64 for a name with anything but letters, digits, `-` and `_`. |
| `changed` | `<build> [--before OLD.mp4] [--db 45]` | Compares every frame of `out/<slug>.mp4` with an older render of the film (by default the newest `out/<slug>_before_*.mp4`) and prints each run of frames that differs with the shots it falls in, then one closing line with the count and the shots. A re-encode of an unchanged frame stays far above 45 dB and a changed element drops well under it, so the runs are the places a pass changed the picture; a shot that became one frame longer shows as a run too, because its camera move re-times. Only the picture is compared: a change to sound alone (voice, music, a cue) shows no run. A run names every shot on screen during it: a shot starts on the first frame at or after its `t0`, as the renderer draws it, and an overlapping transition (whip, slide, zoom or fade, of length `d`) shows the incoming shot from `d`/2 before the cut and the outgoing one until `d`/2 after it, so a run inside one names both shots. Frames are paired by their number, not by their time, so a film whose timestamps run a fraction of a millisecond off is still compared frame for frame. Exit 0 when compared; 2 when a film, the timeline or ffmpeg is missing, when the build's `timeline.json` has a shot without an id, `t0` or `t1`, and when the shot-by-shot comparison compared no frame (`NOT CHECKED no frame compared: no shot of the kept timeline is in the new one under the same id`). When a cut moved (a gap grew, a shot was added) and the kept timeline lies beside the older film (`keep` puts it there), it compares shot by shot instead: each shot's frames against the same shot of the older film from the shot's own first frame, with the top 12 px (the progress bar, which runs on film time; the word captions run on film time too, as they follow the narration) left out, and it prints each shot whose length changed, each new shot and each shot that is gone. That needs a unique id per shot: when the cuts moved and either timeline uses an id twice it is `NOT CHECKED changed: the cuts moved, and a shot id is used twice (<id> in <file>)`, exit 2. A kept timeline that is not JSON, has no shots list or has a shot without a text id or a numeric `t0` or `t1` is not used: it prints `NOTE <file> cannot be read (<why>), so the films are compared frame by frame` and compares frame by frame. Without a readable kept timeline it says the films differ in length: from the first moved cut on every frame differs. After the closing line come up to three more: `changed shots` (the shots that hold a changed frame, each with its lowest value), `fine detail only, in clips` (shots whose changed frames all show a clip, their own or a neighbour's through an overlapping transition, and read 45 dB or more with both pictures scaled down 16 times and hold no block of 16 px that differs by 24 of 255 or more: a re-encoded clip reads so with nothing changed, so look at one frame of each) and `cuts next to a changed shot` (the cuts into and out of the changed shots and, when the cuts moved, every cut whose two shots did not follow each other in the older film, to look at as frame pairs: each cut is printed with the two times to give ffmpeg's `-ss` for the last frame before it and the first after it, as in `34.133 (s18 | s19: 34.083 and 34.117)`; `-ss` gives the first frame at or after its time, so each of the two lies half a frame before its frame). A clip that is new or changed its length is a changed shot, never fine detail. |
| `diff` | `<batch> [--against SNAPSHOT\|<folder>]` | Lists the files of `studio/`, `engine/` and `docs/` that changed or are missing since `SNAPSHOT.txt`, and those added since (`added: studio/extra_rule.py`; a file under a dot-folder, under `__pycache__` or ending `.pyc` is not one); with `--against <folder>` it diffs `studio/` against another studio folder (same filter on both sides) and counts every file only the other folder has (`only in <folder>: <name>`). Exit 0 when nothing differs, else 1; 2 when the batch has no `SNAPSHOT.txt` or the `--against` folder is missing. |

Exit codes: 0 PASS, 1 FIX, 2 NOT CHECKED or a missing file, folder or input, 3 refused because an input is stale or would be overwritten, 64 a wrong argument. No command creates a build folder it was not asked to create.

`accept.json` in a build folder is how the owner accepts a finding by name, so a film can be rendered with it: `[{"code": "L03", "t": 47.76, "why": "..."}]`. An entry names one FIX row of any `proof/qa_*.json` by its code and its time (within 0.05 s) and must say why. `check` (every stage and `all`), `render` and `package` read the file alike: a FIX row it names is printed as `accepted in accept.json: ...` and left out of the exit code, so the checks and the render agree on which rows block a film. A row of any `proof/qa_*.json` counts, and an entry that names no FIX row of the current results prints `NOTE accept.json names no finding: <code> at <t>`. A builder never writes this file.

The scripts underneath can be run alone, from the batch folder (a path argument may be relative to it):

| Script | Use |
|---|---|
| `python studio/build.py cues <build>` and `timeline <build>` | The cue list; the timeline with its shot table and `WARN` lines. `--batch <folder>` when the build is not under a folder that holds `batch.json`. |
| `uv run --no-project --with playwright --with pillow --with numpy python studio/qa.py frames <build> [--times 12.1,40.8]` | Shoots a frame at the start, middle and end of every shot, 0.7 s after every overlay lands, 0.1 s before and after every count's landing (a `number`'s `landAt`, the `until` of a `rail` or `years`) and at 0 s, plus the extra `--times`; reads every text box into `proof/frames/registry.json`; writes `proof/sheet_NN.png`. It first deletes the old frames. |
| `python studio/qa.py plan <build>`, `qa.py file <build> [--video <file>]` | The plan check (timeline and layout only) and the file check. |
| `python studio/lint.py <build> [static\|frames\|all]` | The style lint; `lint.py selftest` plants one fault and one clean control per rule, and one per regression case (`selftest/fixtures/L<code>-<name>.json`, with an optional `level` it must raise and `older_registry` to backdate the frames), and must end `LINT SELFTEST: PASS (21 of 21 cases fire for 18 rules, controls clean)`. Exit 0, 1 (a FIX), 2 (NOT CHECKED), 64. |
| `python studio/checklist.py <build> [write\|check]` | Writes `proof/checklist.md`, or checks `proof/checklist_answers.json` into `proof/qa_stills.json` (an answer older than its still's `media/<id>.png` is a FIX: the still was remade after it was answered). `build` and `check frames` write the checklist themselves. |
| `python studio/gen.py stills\|clips\|status\|adopt <build>` | The generator itself; `--batch <batch.json>` when it is not at `../batch.json`. `stills` and `clips` need `comfy.home`; `status` and `adopt` do not. |
| `python studio/render.py render\|stills\|bench --video <build>` | The renderer: the whole film, frames at `--times`, or a timing run of `--frames N`. |

Two of these write on every run: `lint` writes one file per tier, `proof/qa_lint.json` (static) and `proof/qa_lint_frames.json` (frames), so a run of one tier never drops the other's findings; a frames-tier finding the static tier already made about a shot is one row, in the static file; and `qa.py frames` rewrites `proof/frames/`.

### What each check reads

| Check | Reads | Needs |
|---|---|---|
| `plan` | `timeline.json`, `narration/layout.json` | nothing else |
| `lint` | the static tier: `timeline.json`, `narration/layout.json`, `script.json` (for the payoff) | nothing else |
| `frames` | shoots the frames (`qa.py frames`): a frame at the start, middle and end of every shot, 0.7 s after each overlay lands, 0.1 s before and after every count's landing and at 0 s; reads every text box into `proof/frames/registry.json`; rewrites `proof/checklist.md` | Chrome, playwright, Pillow, numpy |
| `lint-frames` | the lint's frames tier: `proof/frames/registry.json`, the PNGs and the caption pages the frame shoot records; runs inside `check all` after `frames`, or alone | `frames` first, shot from the current timeline (frames older than `timeline.json` give `NOT CHECKED L00`, exit 2) |
| `stills` | `proof/checklist_answers.json` against the stills of `shots.json`; a missing or failed answer, or one older than its still, is a FIX | the answers file |
| `file` | `out/<slug>.mp4` | ffprobe, ffmpeg, numpy, Pillow |

A row is `{code, level, t, what, fix}`. The level is `FIX` (the exit code is 1), `NOTE` (does not fail) or `NOT CHECKED`. A check that cannot run says so: it never passes by silence.

## batch.json

The one place an account's, a machine's and a look's settings live. Paths are relative to the folder holding `batch.json`. See `studio/batch.example.json`.

| Key | Required | Meaning |
|---|---|---|
| `root` | yes | The batch's working root; `builds/` and `videos/` sit in it. Only the batch folder itself is supported, so it must be `"."`: any other value stops with `key 'root' resolves to <path>; only the batch folder itself is supported`. |
| `accent` | yes | The one accent colour of the film (`#ffd60a` is the kit's default). |
| `tag` | yes | The short disclosure the kit prints on every shot that shows a generated picture. |
| `end` | yes | `handle`, `follow`, `ai_line`: the wording of the end card. The shot list's `end` overlay carries it (`handle`, `line`). |
| `music_dir` | yes | The folder of licensed tracks, `<theme>/<track>.mp3`. |
| `voice` | yes | `name` and `speed` of the narrator; `script.json` may override it per film. |
| `comfy` | no | `exe`, `home`, `url` of the ComfyUI that makes stills and clips. |
| `render` | no | `workers` and `maxrate` (kbit/s) for `render`. Defaults are 6 and 6500 when not set. |
| `readers` | no | `audience_file`: the text the reader prompts take as the audience. |
| `package` | no | `check`: an outside command that gets the `post.json` and the video path and must exit 0 before `package` copies anything. |
| `engine` | no | The folder of the audio engine; `<root>/engine` when absent. |

A missing required key stops with the key and file named.

## Build folder

```text
brief.md  facts.md  script.md  script.json  narration/  shots.py  shots.json
graphics.js  media/  timeline.json  post.json  caption.md  out/
proof/  qa_*.json  frames/  sheet_NN.png  checklist.md  checklist_answers.json
        blocks.md  shots_table.md  reviews/  *_answers.md  strip_*.png
```

- `narration/layout.json` holds each line's `id`, `t0`, `t1`, its `tokens` (each with `d`, `t0`, `t1`) and `speech_end`.
- `media/state.json` keeps what `gen.py` made, the prompt hash and each still's `check` features.
- `graphics.js` is optional: the film's own devices (below).
- `post.json` holds `title`, `caption`, `alt_text`, `sources` (`{title, url}`), `cover_ms` and optional `hashtags`; `templates/caption.md` has the rules for the text.

## script.md and script.json

`script.md` holds one table with the columns `id`, `beat`, `caption`, `spoken`, `facts`, `gap`. `caption` is what the viewer reads (digits for numbers), `spoken` what the voice says (numbers as words). A beat of `PAYOFF` marks the line that pays the film's question. `gap` is silence after the line in seconds (default 0.2).

`script.json` keys the engine reads:

| Key | Use |
|---|---|
| `slug`, `title` | Name the film in the timeline. |
| `accent`, `tag` | Override the batch's. |
| `progress` | `false` leaves out the progress bar. |
| `lines` | Rows with `id`, `caption`, `spoken` (or one `text` with `{shown\|spoken}`), `gap`, and `payoff: true` or `beat: "payoff"` on the payoff line. |
| `voice` | `{voice, speed}` for this film; `script` keeps what an earlier `script.json` holds and fills a missing `speed` from the batch. |
| `lexicon`, `lead` | Respellings for the voice (`{word: say}`; `script` writes them from the Lexicon table of `script.md`); seconds before the first word (default 0.12). `script` keeps the `lead` and the `progress` of an earlier `script.json`. |
| `music` | `{theme, track, start, end, fade_out, duck_db}`: the bed `audio.mix` lays under the voice. `studio.py script` writes `start` 0.0, `fade_out` 2.4 and `duck_db` 12 when you give a theme or track; a `script.json` without `fade_out` is mixed with 2.2 s. `render` refuses (3) a `script.json` whose `music` has no `theme` and `track`. |

## Shots

`shots.py` builds `shots.json`; write it with shotkit (below). A shot is a JSON object:

```json
{"id": "s03", "cue": "L02:0",
 "still": {"prompt": "...", "seed": 12, "check": ["one green stalk at one end"]},
 "clip": {"prompt": "...", "seconds": 4},
 "cam": {"from": 1.06, "to": 1.14},
 "tin": {"kind": "punch", "d": 0.35, "from": 1.06},
 "over": [{"type": "label", "text": "Fact"}]}
```

### Which picture a shot shows

| Key | Meaning |
|---|---|
| `still` | `{prompt, seed, check, shift_up}`. `check` lists what to look for in the made picture (kept in `media/state.json`); `shift_up` lifts the picture that many px and mirrors the freed band. |
| `clip` | `{prompt, seconds}`; the clip plays over the shot's still (4 s at 30 fps by default). |
| `from` | `"s01"`: the clip starts on that shot's last frame, one continuous move across a cut. |
| `use` | `"s01"`: keeps playing that shot's clip from where the cut lands (a cut-in). With `offset` (seconds) it names a point in it, and `offset` also lets a shot use a later shot's media. |
| `rate` | Playback speed of a clip; `-1` plays it backwards from `offset`. |
| `media` | `{"kind": "none", "graphic": "name"}`: a drawn card instead of a picture (a device named below); `"still"` forces the still when a clip exists. |
| `flip` | Mirrors the picture. |

### When a shot starts and ends

`cue` is when the shot starts; the first shot needs none and the last one needs `len` (seconds). Cue forms, also used by an overlay's `at` and `out` and by the cue keys of a drawn device:

| Form | Means |
|---|---|
| `"L04:3"` | token 3 of line L04, counted from 0 as `build.py cues` prints them (the cut lands 0.08 s before the word, an overlay 0.03 s before) |
| `"L04:end"` | the end of the line's speech |
| `"L12:0-0.4"`, `"L04:end+0.2"` | the same, shifted by seconds |
| `12.5` | absolute seconds |
| `"+0.4"` | seconds after the overlay's shot starts (overlays only) |

A drawn device may take cues in `aAt` to `mAt`, `failAt`, `moveAt`, `until`, `closeAt`, `offAt`, `linkAt`, `ringAt`, `ringOut`, `drawAt`, `labelAt`, `pulseAt` and `landAt` at the top of the overlay, and `at`, `t0`, `t1`, `failAt`, `moveAt`, `until`, `hotAt` inside its lists (`NESTED_CUES` and `TOP_CUES` in `build.py`).

### How a shot looks and arrives

| Key | Values |
|---|---|
| `cam` | `{from, to, x: [a, b], y: [a, b], shake, ease, pad}`. Scale and px drift across the shot. A still defaults to 1.06 to 1.16 with shake 4, a clip to 1.0 to 1.05; `ease` is `out` or `inout`. The shake path is seeded by the shot's id, the order of its characters included (`s01` and `s10` shake differently). |
| `tin` | How it arrives: `{"kind": "cut"}` (default); `punch` (`d`, `from` 1.12; with `picture: true` only the picture layer scales and type stands still); `flash` (`d`, `gain` 1.7); `whip` (`d`, `dir` left, right, up or down, `blur` 46); `slide` (`d`, `dir`); `zoom` (`d`; the incoming shot settles from 1.3, full bleed on every frame); `fade` (`d`). A `tin` without `d` gets its kind's length from `build.py`: punch 0.35, flash 0.3, whip 0.36, slide 0.36, zoom 0.5, fade 0.4. A `d` that is not a number is refused, naming the shot. |
| `grade` | `soft` (brightness 0.78), `dim` (0.5), `lift` (1.24), `past` (desaturated, for a flashback), `blur` (22 px blur at brightness `bright`, default 0.55). |
| `bright` | The brightness of the shot's still or clip, in place of its grade's own (blur 0.55, dim 0.5, soft 0.78, lift 1.24, past 1.08, no grade 1): a blurred picture as bright as the pictures around it, or a dark picture lifted to its neighbours. A number above 0; `build` refuses anything else (`shot <id>: bright <value> is not a brightness (a number above 0)`). A shot with no picture (`media` kind `none`) ignores it: the `plate` device takes `bright` inside its own `media` spec. |
| `shade` | `true` puts the kit's top shade over the picture and under the tag. |
| `floor`, `vignette` | `false` leaves out the bottom shade or the corner vignette. |
| `tag` | `false` takes the tag off a generated picture; `true` puts it on a drawn shot that shows one. |
| `captions` | `false` mutes captions for the shot; `"quiet"` shows whole sentences, small, dim and still (for a stretch where the viewer watches one mark). |
| `exempt` | `true` takes the shot out of the pace rules (a test card). |
| `long` | `true` marks a shot meant to run past 4.6 s. |
| `says` | `true`, or seconds: a device on the shot speaks the line, so caption pages that begin inside it are left out. Needs no overlay. |
| `amb` | `true` (or a level in dB, default -30) lets the clip's own sound in under the bed. |
| `sfx` | `[{"at": "+0.2", "kind": "riser"}]`; kinds `whoosh`, `impact`, `boom`, `riser`, `tick`, `pop`. `false` turns off the effect a transition would add. |

The mix adds effects by itself: `whoosh` on a whip, slide or zoom, `pop` on a punch and on a number, `impact` on a flash and a stamp, `boom` under a hook at time 0.

The timeline build warns (`WARN`) about a shot under 0.8 s, a shot over 4.6 s without `long`, a clip that runs out before its shot ends and an overlay that stands for less than its reading hold.

### Overlays

`over` is a list; each overlay has a `type`, an `at` and an `out` (default: the whole shot) and the settings of its type. Common to every type: `says` (as on a shot), `real: true` (it names a real person or place: L17 refuses it on a photoreal picture) and `standing: true` where a type has it (complete on the shot's first frame, for a shot that continues another). `*word*` in text lights the word in the accent. A text overlay stays up at least 0.5 s plus 0.3 s per word (the plan check, P07).

Built in (`kit.js`):

| Type | Settings (defaults) |
|---|---|
| `hook` | `lines`, `hot` (words to light), `y` 540, `size` 190, `width`, `step`. Stands complete on frame 0; its entrance only settles it. `standing`: in a shot that continues the hook's shot it stands settled from the first frame. |
| `title` | `lines`, `hot`, `y` 560, `size` 136 as the kit's own cap (shotkit's `title()` sets 150 and y 380), `standing`, `step` 0.075. Fitted to the width. |
| `label` | `text`, `y` 440, `x` 72, `tone: "accent"` for a yellow date chip, `standing`. |
| `number` | `value`, `from` 0 and `to` (all numbers: text such as `"1,492"` raises `TypeError` in shotkit and is refused by `build`, naming the shot, and the lint skips such a spec), `decimals`, `prefix`, `unit`, `group` (false for years), `size` 300, `y` 600, `tone`, `count` (seconds, default 1.1), `landAt` (the count ends on this cue and the last value shows only then), `sub`, `subY`, `subAt`, `hot`, `x` (a number: the left edge of the figure and of its second line; 70 by the kit), `align: "center"` (both centred on the frame; `x` is then not read), `standing` (the figure stands landed from the shot's first frame, for a count that landed on the shot before: `count` and `landAt` are then not read, and L07 takes it as the same number carried, a fault only when it stands whole before the first time its word is heard (the copies over the cuts are read as one stand, and a word spoken while the number is off the screen counts as heard); a standing number that the shot before does not show is judged as printed whole at its first frame). |
| `lower` | `text`, `y` 870, `size`, `hot`, `standing`. |
| `source` | `text`, `y` (default 1012 by the kit's CSS), `align: "center"`, `standing`. |
| `chapter` | `n`, `of`, `text`. |
| `stamp` | `text`, `who` (a small first line for the speaker or hedge: 62 px, never above 0.62 of smaller words, floor 32 px), `x` 540, `y` 760, `size`, `rot` -7, `tone`, `standing` (landed from the shot's first frame with no slam and no shake, for a stamp that landed on the shot before). |
| `callout` | `x`, `y` (the point), `dx` 70, `dy` -130 (where the leader ends), `text`, `hot`, `hang` (`left`, `up` or `left-up`), `standing`. |
| `compare` | `rows` of `{label, value, display, hot, at, tick, wait, fixed}`, `unit`, `max`, `decimals`, `size`, `step` 0.4, `y` 620. A row's `at` is a cue like any other: the absolute time `build.py` resolves it to (`+0.2` is 0.2 s after the shot starts, `L02:2` a word; a bare `0.2` is 0.2 s into the film). `build` prints a WARN for a bare number in any row's `at` that falls before its shot starts: that is almost always an offset written without its `+`. `fixed` shows `display` from the start; `wait` stands as a question mark until its time. |
| `rail` | `from`, `to`, `marks` of `{at, label}`, `until` (the count ends here and the last value shows only then), `y` 560. |
| `quote` | `lines`, `hot`, `y` 640, `size`, `step` 0.09. |
| `end` | `big` (two lines, default FOLLOW / FOR MORE; a line break inside one is kept), `chip` (a small dark chip under the big words, such as AS OF 2026 under a claim about today; L16 reads it), `handle` (without the @), `line` (a line break in it is kept; `*word*` lights words here and in `big`, a marked phrase also across the break), `lift`. |

Drawn devices (`kit_graphics.js`) are named by `type` on an overlay; one that fills a whole shot is named in `media` as `{"kind": "none", "graphic": "ground"}`. A device defined in the film's own `graphics.js` with the same name replaces the kit's for that film. That holds for drawn devices only: the kit looks a type up among its built-in types (the table above) first, so a film's device named `stamp` or `number` is never drawn as an overlay (as a shot's `media` graphic it is), and the lint refuses an overlay that asks for it `[lint L19]`. Give the device another name, or use the built-in type's settings. The lint reads a registration written as `graphic('name', ...)` or `Kit.graphic('name', ...)` outside a comment (a quote inside a regular expression literal on the same line can hide a comment from it).

| Device | Settings |
|---|---|
| `signal` | `y`, `h`, `standing`, `dataName`, `signalName`, `modes: [{at, mode, badge, tone}]`; modes `data`, `tone`, `noise`, `carrier`, `flat`; `tone` of a badge is red, green or accent. Use `standing` when the mode changes in the shot's first second. |
| `pulse` | `y`, `from`, `to`, `size`, `trips: [{t0, t1, dir, label}]`, `count: {to, unit, decimals, display, trip}`. |
| `disc` | `x`, `y`, `r`. |
| `blocks` | `y`, `cols`, `rows`, `code`, `bad`, `to`, `failAt`, `moveAt`. |
| `lamps` | `y`, `total`, `cols`, `keep`, `offAt`, `step`: every lamp lit, then all but `keep` go dark one by one. |
| `ladder` | `y`, `standing`, `plate` (a dark plate behind the rows; keep `y` at 352 or lower), `rows: [{label, value, state, at, hot, count}]`; `state` is `done`, `wait`, `count` or `reveal` (a question mark until `at`). A `reveal` row takes `hot: true` so the outcome lands in the accent. |
| `strip` | `y`, `from`, `to`, `marks: [{day, label, side, t0}]`. |
| `meter` | `y`, `label`, `from`, `to`, `note`: a bar that drains. |
| `route` | `x`, `y` 420, `h` 600, `standing`, `travel` 0.6 s, `big` (92 px names, note inline), `dashed: [i]` (the link after stop i is drawn dashed), `stops: [{name, date, note, at}]`: a journey as a rail of named stops, for films that may not show a map. |
| `punch` | `at`, `from` 1.06, `d` 0.35, `to` 1: a punch-in on the picture layer alone. |
| `hush` | none: carries `says` for a stretch in which a device says the line. |
| `plate` | `src`, `blur` 22 px, `bright` 0.8, `sat` 1: one of the build's pictures blurred past reading, as a shot's media. |
| `light` | `k` 0.16: a soft warm light on a blurred plate. |
| `topshade` | `k` 1: the top shade at a chosen strength, under the tag. |
| `ground` | `k` 0.17: a plain plate drawn by the stage, as a shot's media. It has no generated picture, so the kit puts no tag on it. |
| `veil` | `blur` 7, `soft` 12, `fog` 0.55, `tint` `[r, g, b]`, `spots: [{x, y, rx, ry, fog, blur, path}]`, `bands: [{y, h, feather}]`: mist or defocus over parts of the picture, following the camera. |
| `stepsrow` | `y` 380, `steps: [{text, at}]`: numbered step chips that light in turn. L11's 2 s rule holds a row whether it is written under `steps` or under `rows`. |
| `reasons` | `y`, `size` 150, `rows: [{text, at, hotAt}]`: the film's question as numbered answers at title size; a row with `at` shows a question mark until then. |
| `answers` | `y`, `part` (`who` or `what`), `ahead` (`dim`, `?` or `hide`), `standing`, `rows: [{who, what, at, hot, size}]`: answers at title size, each under a chip naming whose answer it is. |
| `words` | `y`, `size` 118, `gap` 34, `standing`, `rows: [{script, hot, latin, gloss, at}]`: words in their own script (set as type, never drawn by the image model) with their Roman spelling and meaning. |
| `document` | `y`, `book`, `aAt`, `script`, `latin`, `z` 1, `zoomFrom`, `standing`, `redrawn` (the line saying the card is ours; `false` leaves it out), `senses: [{n, text, at, hotAt}]`, `rows: [{script, latin, ours, gloss, extra, big, at}]`: a document redrawn on a paper card. |
| `years` | `y`, `from`, `to`, `until`, `size` 170, `prefix`, `marks: [{at, label}]`: a rail of years with a large counter that shows its last value only at `until`. The counter is clamped by its measured width (the wider of `from` and `to`, with its `prefix` and the landing pop) inside x 60 to 1020, so it stays in the safe box at the default `size`. |

A film's own devices go in `<build>/graphics.js` as `Kit.graphic(name, (wrap, spec, ctx) => update(t))`: a pure function of time, nothing from a timer, a clock or an unseeded random. It can load one of the build's pictures with `Stage.img(Kit.base() + 'media/p01.jpg')`. A drawing leaves the label row (y 282 to 345), the chip row (y 352 to 420) and the source line (from y 1012) clear at the largest camera scale of its shots, and its shots keep the camera at 1.04 or under. Its motion runs on its shot's clock or its own (`t - ctx.shot.t0`, `t - ctx.at`), never on bare film time: the kit's own camera shake and jitters do the same, so a shot looks the same wherever it stands in the film and `changed` can compare it after a cut moved. The one exception is a `standing` signal: it continues the signal of the shot before it, so its waves stay on film time and do not jump at the cut. A graphic is either the shot's media (`"media": {"kind": "none", "graphic": name}`, drawn on the kit's bare plate) or an overlay of a picture shot (`{"type": name}` in `over`). As a shot's media a graphic gets `ctx.at` = the shot's first shown frame (`t0`, less half the tin's `d` under a whip, slide, zoom or fade), so a device keyed on `ctx.at` is already drawn while the shot slides or fades in; an overlay's `ctx.at` is the shot's `t0`. A `graphic` name that nothing registers fails the page (`unknown graphic: <name> in shot <id>`), as an unknown overlay type does. `Stage.OVERLAP` lists the tin kinds that overlap (whip, slide, zoom, fade). Draw a drawing as an overlay of a blurred, slowly drifting picture, so that it never stands on a bare plate for long (P12), and draw it large enough to fill the band between the top rows and the captions.

`Kit.pages()` returns the caption pages, `[{t0, t1, text, line}]` (a quiet page adds `quiet: true`; a page that never shows, because it begins in a muted stretch or while a device says the line, adds `shown: false` with the times it would have had); the frame shoot writes them to the frame registry so L13 can check them.

### shotkit

`from shotkit import *` in `shots.py`. Overlay helpers return plain dicts.

| Helper | Gives |
|---|---|
| `label(text, y=282, **k)`, `date(text, **k)` | a chip; `date` is an accent label marked `past` (its shot needs the past grade) |
| `source(kind, name, year=None, **k)` | `"Fact from: PNAS, 2014"`; kinds `fact` ("Fact from"), `account` ("One account"), `visuals` ("Visuals and voice"); any other kind is used as typed |
| `title(*lines, at="+0.1", y=380, size=150, **k)`, `lower(text, y=352, **k)` | a title; a lower third |
| `number(value, land, **k)` | a count that lands on the cue `land` (sets `landAt`); y 352, size 300 |
| `stamp(text, who=None, **k)` | a stamp, size 100 |
| `ladder(rows)` | a ladder on its dark plate with every `reveal` row `hot` |
| `end_card(big, line=None, *, use, cue, seconds=3.0, chip=None, **k)` | the fields of the closing shot (`plan.shot("end", **end_card([...], "send line", use="s01", cue="L32:end"))`): the `end` overlay over a blurred earlier picture, with the handle and the AI line read from the batch's `end` settings (`batch_end()`), so no film types them again; without a `line` the batch's `follow` line stands. The closing shot shows its owner's still (`media: "still"`), never the owner's clip, so no clip plays past its end; if the owner has no `media/<use>.png`, `build` warns and draws the plain ground |
| `real(spec)` | marks a chip as naming a real person or place |
| `still(prompt, seed, check=())`, `clip(prompt, seconds=4)` | the media specs |
| `PUNCH`, `HELD`, `PLATE` | `{"kind": "punch", "d": 0.35, "from": 1.06}`; a camera that does not move under standing type (`from` 1, `to` 1, `shake` 0); `{"kind": "none", "graphic": "ground"}` as media: the plain plate the stage draws. For one of the build's pictures blurred past reading use the kit's `plate` device, which needs a `src`: `{"kind": "none", "graphic": "plate", "src": "media/p01.jpg"}` |
| `Plan(slug, look)` | `plan.shot(id, **fields)`, `plan.part(id, kind, i)`, `plan.after(id, new)`, `plan.drop(*ids)`, `plan.own_still(id, spec, **more)`, `plan.write(until=None)` |
| `@plan.block("YYYY-MM-DD fix 1: name")` | a function of the plan; blocks run in the order declared |

The `look` line is the film's palette and grain; end every still prompt with it. Fix blocks never edit an earlier block. `plan.write()` writes `shots.json` and `proof/blocks.md`, which lists the last block to touch each shot: those are the windows to look at again after a fix. `write(until="2026-11-25 fix 1")` rebuilds an earlier state. `python studio/shotkit.py --selftest` ends `SHOTKIT: PASS`.

## Making pictures and clips

Stills: Z-Image Turbo at 1088x1920 (about 25 s each). Clips: LTX-2.5 image to video, 4 s at 30 fps by default, frames saved at 1080x1920. A clip starts from the shot's still, or from the last frame of the shot named in `from`. `clips` refuses (exit 3, before any clip is made) when a wanted shot would be the third clip in a chain; give that shot a still of its own.

- A still prompt is one paragraph: "Cinematic photograph, vertical frame." then the subject, the setting, the light and time of day, the camera and lens feel, then the film's `look` line. Say what is in the foreground, the middle and the far distance; name one horizon and one sun; name the count of things ("a single dish"); say "no people" when none are wanted.
- A clip prompt is one flowing paragraph under 120 words: what moves (one or two motions), then the camera ("pushes in slowly", "holds still"), then the sound in a few words or "silent". Describe the look, not the term: "dark starspots" is drawn as black star-shaped marks.
- "Pushes in slowly" can come out as a strong zoom: check where the subject is at the clip's end.
- Gentle physical motion reads as real (water, cloud, dust, light, a slow orbit). Avoid new objects entering, crowds, fast action and anything rigid that must turn.
- Reject and reseed (`--only id --reseed`) a picture with garbled text or numerals, a wrong or doubled subject, impossible anatomy or physics, or a dark frame. After two reseeds, change the prompt or the device, not the seed. Screens in a picture draw garbled words: ask for "only one thin line on a dark grid, no interface panels, no words, no numbers".
- A shot whose subject landed too low is moved, not redrawn: `still.shift_up`, or the camera: `"cam": {"from": 1.28, "to": 1.38, "y": [-215, -240]}` lifts the picture about 220 px (the scale must cover the shift: 1 + 2 x shift / 1920). Keep clips at 1.25 or under, since they are 896 px wide before scaling.
- A shot that gains a still of its own through a fix block must lose its `use` and its drawn `media` (`plan.own_still` removes `use`, `media`, `offset`, `rate`, `amb`, `flip` and `tin`, then sets the still).
- ComfyUI answers an identical request (same prompt, seed and settings) from its cache and writes no new file, so asking again gives the same picture: change the seed (`--only <id> --reseed`) or the prompt. `gen.py` asks the history for the files of its own request, so a cached reply is never mistaken for the newest file under a prefix.

## The other checks

Besides the lint, `qa.py` gives rows with these codes.

| Code | Check | Level |
|---|---|---|
| P01 | the film runs 60 to 179 s | FIX |
| P02 | median shot over 2.9 s | FIX |
| P03 | fewer than three picture changes in the first 3.5 s | FIX |
| P04 | no hook standing on frame 0, or a hook over six words | FIX |
| P05 | the spoken hook ends after 3.5 s (NOTE after 3.05 s) | FIX |
| P06 | nothing new on screen for over 3.3 s | FIX |
| P07 | a text overlay stands less than its reading hold, 0.5 s plus 0.3 s a word (at most 4 s); the same words carried over consecutive shots count as one hold only while it is unbroken (this copy stands to the cut and its twin starts at it, within 0.01 s; a line that leaves and comes back is two stands, and a neighbour that carries the words twice counts once) | FIX |
| P08 | a shot holds the last frame of its clip for over 0.5 s | NOTE |
| P09 | speech covers under 86% of the narrated stretch | FIX |
| P10 | over 0.75 s of silence between lines | NOTE |
| P11 | the last shot has no `end` overlay, or it stands under 2.5 s | FIX |
| P12 | shots on the kit's bare plate (`media` kind `none`) run more than 10 s in a row; a graphic drawn as an overlay of a picture shot does not count, nor does a shot with the `plate` device as its media or a `plate` overlay that stands the whole shot (from its start, no `out` or an `out` at its end); a `ground` overlay that stands the whole shot makes a picture shot count as bare plate (one that flashes over a picture does not); an `exempt` bare shot keeps a run open but adds no seconds (the row then ends `exempt shots not counted`) | FIX |
| P13 | fewer clips than about 4 a minute of the film outside its `exempt` shots (8 in a two-minute film; the row says `outside the exempt shots` when there are any) | NOTE |
| F01 | text outside x 60 to 1020, y 270 to 1252 (a source line may go to 1340, the end card to 1500) | FIX |
| F02 | text under 32 px | FIX |
| F03 | two text boxes overlap | FIX |
| F04 | text separated from the picture only by its outline | NOTE |
| F05 | over 60% of a frame near black (NOTE over 42%) | FIX |
| F06 | frame 0 dark (mean under 40 of 255) or without a hook | FIX |
| F07 | text boxes cover over 45% of the frame (NOTE over 32%) | FIX |
| V01 | loudness off -14 LUFS by more than 1, true peak over -1 dBTP, a flash sequence, or black frames | FIX |
| V01 | the frames are not evenly timed (the average frame rate is not 30/1): a film rendered before `render.py` joined its parts by their exact lengths | NOTE |
| V02 | file over 95 MB | FIX |
| V03 | the picture does not change for 3 s | FIX |
| V00 | a check could not run | FIX |

`package` checks the delivered file: H.264 High yuv420p, 1080x1920 at 30 fps, an AAC stream, at most 100 MB, a lowercase slug, a title and a caption, no link in the caption, none of the characters that break a caption (non-breaking space, soft hyphen, zero-width characters, en and em dash), `cover_ms` inside the video, and at least one source with a title and an https address.

## House rules

Each rule is tagged. Where a lint id or a checklist id is given, the program checks it; where only `[look]` is given, a reader does.

### Pictures

- Every shot is full bleed: no header or footer band. Near-black fills under 40% of any shot except the end card. `[qa F05]`
- A clip stands on frame 0; stills between clips always move under a camera move (push, pull or pan, mixed; a hero push eases out). `[look]`
- One palette per film, written as a look line that ends every still prompt. `[look]`
- `grade` is none by default; `soft` under a dense overlay; `dim` or `blur` only under a full-screen device or the end card. `[look]`
- Six or more kinds of picture per film: generated clip, generated still on a camera move, counter, bars, timeline, callout, drawn device, stamp, quote card. `[look]`
- A generated picture is a generic scene. Under the name of a real place, object, person, document or event, the picture is our own drawing in the film's diagram style or type on a blurred plate. A photoreal picture under a real name is a P0, whatever the tag says. `[lint L17]`
- A chip that names a real thing is declared with `real()`; the lint never guesses proper nouns. `[lint L17]`
- A generated picture that carries a date chip shows nothing of today (no motor boats, wires, lit windows, plastic, modern coins or lettering) and is in the `past` grade. `[lint L01]`
- Look at the whole frame at full size, corners and bottom included, for anything later than the date: fenders, buoys, rivets, machine stitching, milled or lettered coins, wires, modern dress. `[check C2]`
- A specific day, a landing, a named building, a named person, a document or a recorded event is never a chip on a photoreal picture: it is type on a blurred plate (the date as a yellow chip, the place as a title), or our own drawing, or it moves into the source line. `[lint L17]`
- One still never carries two dates or two places. `[lint L14]`
- A dark chip that names a region or a kind of place may stand on a generated picture of a generic scene once the thing shown has been checked against the real thing. `[look]`
- A plant, animal or object named on screen is checked end to end against a description of the real thing before the still is used (leaf shape, fruit, a stalk at one end only, the right kind of whale). Put the checkable feature in `still.check` and in the prompt. If the model cannot draw it, show it small and soft, or not at all. `[check C1]`
- What the film says is built looks built, and what it says is grown looks grown: check every still for the thing that contradicts the line (planks and posts on a bridge said to be roots). `[check C3]`
- The subject of a picture sits in the visible band, y 400 to 1000. Nothing the shot is about lies at or under y 1074 (captions) or under y 1250 (the player's own text). Check with captions on; lift it with the camera or make a new still. `[check C4]`
- No identifiable real person's face, no logo, flag or badge, no readable invented text in any picture. `[check C5]`
- A picture does not say more than the words under it (a star close up under "over a light-year away"). `[check C6]`
- No picture is in the clear more than twice in a film, blurred uses included when they can be recognised, and never for two different things. A run of cut-ins on one picture counts as one use. `[lint L02]`
- After the payoff every shot is a new picture or a device. `[lint L02]`
- A real, specific object the model cannot know exactly (a named probe, a coin, a map) is not prompted as a close-up: prompt the setting and keep it small and far, or draw it. `[look]`
- When no honest picture exists for a data device, put it on a blurred plate (`grade: "blur"`, `cam: {"from": 1, "to": 1, "shake": 0}`): a readable picture under a named thing claims to be it. `[look]`
- A drawn diagram is as bright as the pictures around it (mean brightness 60 of 255 or more), with thin outlines and muted fills. What the voice names is the lightest and heaviest mark. `[lint L12]`
- A redrawn document stands on the stage's plain plate (`ground`), never on a generated picture, so the tag is not on the film's one real piece of evidence. `[lint L18]`
- Maps that touch India follow the Survey of India depiction; safest is relief with no political borders. `[look]`
- Time passing is drawn (a sapling that grows); a label never names something that has left the frame; a step chip is a verb. `[look]`

### Words on screen

- Safe box for all text: x 60 to 1020, y 270 to 1252. Nothing under 32 px. `[qa F01]` `[qa F02]`
- Roles: hook up to 190 and six words or fewer; hero number up to 300 with its unit at half size; title 150; lower third 70 and five words or fewer on one line; label chip 40; source line 32; captions 72. `[lint L15]` `[qa P04]`
- The top row (y 282 to 345) belongs to one chip on the left and the film's tag on the right; a chip there holds 30 characters at most and ends 16 px or more before the tag. Numbers, lists and lower thirds start at y 352 or lower; a title under a chip at y 380. A source line sits just above the captions (y 1012 to 1063), never below them. `[lint L10]`
- Words on screen never repeat the caption's words in the same frame. Where a title is the spoken line itself, give it `says: true` (the caption pages that would begin while it stands are left out) or give its shot `captions: false`; where a chip repeats the line, give it something the voice does not say (a date, a place, a source). `[lint L03]`
- A device that speaks the line (a title, a quote, an answer, a stamp, a hero number with its second line) takes `says: true`. `says` may be seconds: the pages left out are those that would begin within that long of the device landing. `[lint L03]`
- Hero text is five words or fewer and names the thing, the number or the turn. One hero element per shot. `[look]`
- A number is never on screen before its spoken word: not in a rail's end mark, not in a label. A count lands by the clock on its spoken word (`landAt`, `until`); an eased count would reach its last value a quarter second early, so the kit holds it back until the cue. Frames at 0.1 s before and after the word prove it. `[lint L07]`
- The words that qualify a number (AS REPORTED, IN ONE STUDY) stand from the page's first frame, and a comparison keeps its condition on screen (A YEAR OF RAIN, ALL AT ONCE). `[look]`
- A date chip is yellow, a label chip dark. A state that depends on a date keeps its date on screen for as long as it shows. `[look]`
- A present-day claim on a chip carries its year (2026: MOSTLY PEANUT). The lint reads label, callout and chip overlays and a card row's own notes (`ours`, `extra`). `[lint L16]`
- A source line on a generated picture says what it is ("Fact from: ...", "Journal: ...", "Source: ...", "..., translated by ..."), with the year of the source. A bare publication name under a photoreal picture reads as the picture's credit. `[lint L06]`
- A source line names only what it sources; when a list has rows from two sources it says which rows are whose. A row keeps the source's qualifier (TENDS TO RUST, not RUSTS). `[look]`
- Every stamp is in the accent; green reads as verified. A stamp carries its hedge or its speaker inside it (`who`: RESEARCHERS SAY). `[lint L04]`
- A list sits on a dark plate, and each outcome turns to the accent as it lands. On a card with several rows the accent marks the newest row. `[lint L05]`
- The words that mark one part of a row mark the same part in every row. `[look]`
- A relation between two words keeps the dictionary's own word: "akin to" is drawn dashed and labelled (`route.dashed`), "from" solid. `[look]`
- One family for display (Barlow Condensed, upper case), Poppins 700 for captions, Inter for the source line. White fill, a dark outline, one accent per film for the spoken word, hero units, marked words and bars. No glow, no gradient text, no emoji. `[look]`
- The tag is set like a label chip; a shot with a generated picture carries it unless the shot turns it off. `[look]`
- Where the viewer watches one mark (a test card), the accent belongs to that mark alone, from the first step of the test to the end of its hold, and nothing appears, moves or leaves anywhere else on the card. A list the viewer must read before acting is whole and white from its first frame. `[look]`

### Devices

- A word card prints every word of the card dim from its first frame and lights each row on its spoken word. No card opens on an empty plate. `[look]`
- Each row of a word card stands lit 2 s or more after it lights, and the row the film leads to 2.5 s or more. Buy the time with a pause after the line (`gap`), never by letting the card run under the next line. `[lint L11]`
- A redrawn document says so beside it ("Entry text: Gundert, 1872, redrawn. Dark chips are our notes"), keeps the source's own spelling in full, and looks like paper (square corners, a hairline border). `[lint L18]`
- The film's question and its answer are title size (150), not list size; a two-row comparison of sources puts each answer at title size under a small label naming the source. `[look]`
- A device drawn to scale names its scale and whose arithmetic it is, once per picture; a sketch that is not to scale says so when another picture in the film is. `[look]`
- A demonstration that could be taken for a test of the body says on screen that it is not one, from the first frame of the first test, and the caption's second line says it again. No line promises the viewer an outcome. `[look]`
- A measure the viewer must act on is given in units nobody can misread (about 10 cm, not "a hand's width"). `[look]`
- A film whose claim is that nothing on the card moves is rendered without the progress bar (`"progress": false` in `script.json`), and its hold starts on the word that starts the viewer's action. `[look]`

### Time and pace

- About 95 to 118 s (the speech ends between 92 and 115 s, then a 3 s end card), 285 to 315 spoken words, 45 to 55 shots, median shot near 2.2 s, none over 4 s unless marked `long`. The plan check fails a film outside 60 to 179 s or with a median shot over 2.9 s. `[qa P01]` `[qa P02]`
- The voice is the clock: every cut, overlay and reveal is cued to a word. A hard cut lands 0.08 s before a stressed word. `[look]`
- Something new on the picture layer at least every 3 s (captions do not count). `[qa P06]`
- The picture changes three times in the first 3.5 s; count the cuts and punch-ins before review. `[lint L08]`
- The hook stands complete on frame 0 over moving footage, its speech is over by 3 s, and the first six seconds say what the thing is. `[qa P04]` `[qa P05]`
- Beats: promise by 5 to 8 s; first complete fact by 15 s; a fresh reason to stay about every 15 to 20 s; payoff at 70 to 85% of the runtime; one consequence; a last line worth sending; an end card of 2.5 to 3 s over the opening picture, so the last frame loops into the first. `[qa P11]`
- A late payoff is promised early on screen (PROOF AT THE END: ITS NAME IN THREE LANGUAGES), and the stretch before it carries a lower third from its first frame, so the film never looks finished early. `[look]`
- At most three whips or zooms in a film, never two in a row; a punch-in refreshes a clip that runs long (`use`). A zoom punches the picture layer, never showing the incoming shot as a small inset. `[lint L09]`
- Entrances are springs that settle; landed text stays still; exits are cuts with the shot. No more than three large brightness swings in any second. `[qa V01]`
- What stands on both sides of a cut (a drawing, a plate, a rail, a label, a stamp, a number) stands in the same place and at the same size on both, or moves there in one visible move: it never jumps, dims or enters again. An overlay that goes on from the shot before is set `standing: true`. After a change to one shot, look at the frame before and the frame after each of its cuts (`changed` lists them). `[look]`
- Reading hold: 0.5 s plus 0.3 s per word, at most 4 s. `[qa P07]` The last line stands at least 2 s. `[look]`
- The voice at speed 1.0, lines 0.2 s apart, a breath of 0.45 to 0.6 s before a turn; speech on 88% or more of the narrated stretch. `[qa P09]`
- Master at -14 LUFS, true peak at or under -1 dBTP. `[qa V01]`
- Clips: 8 to 14 in a film where the story moves, at most two in a chain (`from`; `clips` refuses a third), 4 s at 30 fps. `[look, qa P13]`
- A drawing or a type card never stands on a bare plate for more than 10 s in a row: set drawings over a blurred, slowly drifting picture. `[qa P12]` Cut a picture in the clear between two drawn stretches. `[look]`
- A drawing fills the band between the top rows and the captions (about 900 px wide or 450 px tall); it is never a small figure on an empty frame. `[look]`

### Captions

- Captions stay inside x 190 to 890 and end at y 1252; a page holds at most three words or about 20 characters, the current word lit. `[qa F01]`
- A caption page never drops the NOT of its sentence: IT IS / NOT THE BRIDGE, never THE BRIDGE alone. A negator opens its page and keeps the words it negates (such a page holds up to 4 words and 22 characters): NOT, NO, NEVER, NOBODY, NOTHING, NONE and any word ending in N'T (DON'T, ISN'T). The pager in `kit.js` and the lint hold the same list, and `selftest.py` fails when they differ. When a negated page is muted its tail is muted too. `[lint L13]`
- A name and its number, a number and its unit (24 hours, 23 people, 1 pair) and a date in either order (November 19 2026, 29 February 2024) stay on one page; a page is never left with one short word. May and March count as months after a day only when a year follows. A hedge right before a negator opens the page with it (ALMOST NOBODY TAKES). A number alone on its page joins the page before it when it ends its clause or follows a determiner (A CLASS OF 60, THE OTHER 2, ANOTHER 100), and the page after it when it would stand under half a second (1 JOB, 11 OF 91 TRIES). What the pager cannot know is where a clause ends without a comma: where a page still reads wrong (NO STUDY WE READ / TESTED A / CINEMA MENU), give the shot `captions: "quiet"` or a device with `says`. `[look]`
- A quiet caption (a hold): 46 px, dim, still, a clause to a line, question marks kept; it stands until the next page or the cut, so a hold never leaves the viewer with nothing to read. A page that begins while captions are off never shows its tail afterwards. `[look]`
- A title that is the spoken line itself gets `captions: false` on its shot, with the cut on its first word, so that no page starts and vanishes. `[look]`

### The text under a film (`post.json`)

- The first line is one sentence under 125 characters that makes the claim without giving the payoff away. `[look]`
- The disclosure that the pictures and the voice are AI-generated is the second paragraph, not the last. `[look]`
- A universal negative ("nobody has published") is written as what we found ("we found no published test"). A figure with one source keeps the source's qualifier and says it has one source. `[look]`
- A source is named by its kind (a letter, a review, a dictionary, a journal paper); every url is one a row of `facts.md` cites. `[look]`
- The cover frame is one where the hook has settled and no caption page is up. `[look]`
- Every number, name and date on screen or in the voice has two sources in `facts.md`, with the sources' qualifiers kept (about, nearly, as of). A computed figure is labelled as ours or left out. `[look]`
- A statement about the present carries its date on screen ("AS OF 19 NOV 2026"). `[lint L16]`
- No em or en dashes, no emoji, no "did you know", no greeting. `[look]`

## Walking a film before review

`studio-checklist.md` is the walk. Run `studio.py check <build> all` until it exits 0 (every stage prints `check <stage>: exit 0`), then open every sheet in `proof/` as three readers will: a first-time viewer with the sound off, a design ruler and a fact checker. A rule that comes out of a review is applied to every shot of the film and to every later film, not only the shots the review named.
