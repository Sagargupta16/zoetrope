# Formats and delivery

| Preset | Size | Use |
|---|---|---|
| 16:9 | 1920x1080 | default; decks, YouTube, desktop, embeds |
| 9:16 | 1080x1920 | phone vertical, Stories, Shorts, Reels |
| 1:1 | 1080x1080 | feeds |
| 4:5 | 1080x1350 | portrait feeds |

- **FPS:** 30 (default). Keep to one fps for the whole piece. Use even width and height (yuv420p needs it).
- **Default when unsure:** 16:9, 1920x1080, 30 fps, H.264 MP4.
- **Size and fps per run:** `run_all.py <stage> --size 1080x1920 --fps 24 --ss 2` sets `E.W`, `E.H`, `E.FPS` and `E.SS` before scenes.py is imported, so a 9:16 or 1:1 build needs no file edit (a scenes.py that sets its own size wins, and run_all says so). Give `audio` the same flags as `full`: it refuses a `video.mp4` drawn at another size, fps or SS, or from an older scenes.py.
- **Layout per aspect:** re-plan the layout for 9:16 and 1:1 (stack, bigger type), do not just crop a 16:9 design. Same `SCHEDULE`, different layout code keyed on `E.W < E.H`.
- **Naming:** `{slug}_{aspect}_{length}s_v{n}.mp4` (set `OUT` in the working folder's run_all.py), for example `{product}-launch_16x9_15s_v1.mp4`; lowercase, hyphens in the slug, bump `v` for every revision; GIF as `{same}_preview.gif`. Keep the working folder (scenes.py, `video.mp4`, the audio files): an audio fix is `run_all.py audio` (audio, master and mux again, no frame redrawn), while a visual fix draws every frame again unless the build kept its frames (`run_all.py full --keep-frames`, then `--keep-frames --redraw T0-T1` for one passage).
- **Report at the end (all of it):** the `DELIVERED <path> (<MB>, <s>, <LUFS>, <dBTP>)` line `run_all.py` prints after a clean QA pass, quoted as printed, and the `APPROVAL` line above it (a file that failed is renamed `<name>.rejected.mp4`, one from a run that broke before its verdict `<name>.unchecked.mp4`, and neither gets a DELIVERED line; `delivery-report.md`), then resolution, fps, codec and container, which encode rung was used and why, frames checked in QA (list the times), what the audio is (music BPM, voice name), any assumption made, and how to request changes (copy, color, timing, aspect). Show the final video or a frame in a session tab. Add credits for any third-party material; none for synthesized audio and drawn shapes.

## File size

No platform upload limit is quoted here: none was checked, and limits change by plan and workspace (`qa-gates.md`, gate 10). When a file has a limit, ask where it goes, read the limit from that platform's own current page, and give it to the build as a budget (below).

### Measured MB per minute, by style class

The five 2026-10-28 samples, 60 s each, H.264 with AAC at 192k (about 1.4 MB a minute of the total; the mux now encodes AAC at 320k, about 2.4 MB a minute). Picture only is the video stream's own bitrate.

| Style class (sample) | Look | File, 60 s | Picture only |
|---|---|---|---|
| Explainer (derivative) | flat dark ink, thin lines | 3.4 MB | 1.8 MB a minute (0.24 Mb/s) |
| Product launch (Nook) | flat colour, 2x supersampled | 7.1 MB | 5.6 MB a minute (0.74 Mb/s) |
| Game parody (tide serpent battle) | pixel art, dithered | 17.9 MB | 16.3 MB a minute (2.17 Mb/s) |
| Dense line art (everything is a rectangle, 9:16) | dashed outlines | 19.6 MB | 18.1 MB a minute (2.41 Mb/s) |
| Film credits (lighthouse) | grain std 1.6 in 2 px cells, CRF 20 | 35.9 MB | 34.4 MB a minute (4.59 Mb/s) |
| Film credits, first master | grain std 2.6 in 2 px cells, CRF 18 | 140.2 MB | not kept |

### Grain (the lighthouse film, all 60 s, picture only, CRF 20, BT.709 encode)

`kits/g11-movie-credits/grain_test.py 20 60`, 2026-10-28. "Grain left" is the std, in grey levels, of the decoded file minus the decoded no-grain file over the sky: how much of the drawn grain survives the encode.

| Grain | MB a minute | Mb/s | Grain left (of 1.6 drawn) |
|---|---|---|---|
| none | 13.3 | 1.78 | 0 |
| the kit's own: 2 px cells, new every frame, before the weave | 34.8 | 4.64 | 1.28 |
| `grain.grain`, 1 px, new every frame (`hz=fps`) | 17.5 | 2.33 | 1.09 |
| `grain.grain`, held 2 frames (`hz=fps/2`, the default) | 19.1 | 2.55 | 1.13 |
| `grain.grain`, one grain for the whole film (`hz=0`) | 15.9 | 2.12 | 1.48 |

- **The cell size is the size lever, not the refresh rate.** At the same std, 1 px tile grain costs 4 to 6 MB a minute over no grain; the kit's 2 px cells cost 21.5. It is finer, and about 0.15 levels weaker after the encode, so it is not a drop-in for that look: check it on a still.
- **Holding grain for 2 frames does not shrink the file with x264's defaults.** x264's MB-tree spends bits on detail the next frame reuses, so held grain is coded better and kept: on the 4 s slice at std 2.6, new every frame 43.8 MB a minute (1.66 levels left), held 2 frames 63.1 (2.07 left), static 30.2 (2.62 left). With `mbtree=0` the order flips (171.7, 125.6, 43.6), which is where the "a slower grain is smaller" advice comes from. Choose the cadence by look; `hz=0` reads as a dirty screen, not grain.
- **Before rendering a grainy style:** run `grain_test.py` (the 4 s slice, about a minute; it is one x264 GOP long, so it overstates static grain) and `grain_test.py 20 60` for the real per-minute figure (about 9 min for this film on 6 processes). Keep grain at std 1.6 or less and encode grainy styles at CRF 20 (`run_all.py` has `CRF`). `qa.py check` notes anything over 12 Mb/s (Q1002).
- **Apply grain last:** `grain.grain(img, t)` after any whole-pixel weave shift, so the grain stays put while the picture weaves.

### Safe boxes, flash windows and frame rates

| Aspect | `--size` | 4 percent safe box (px, Q201) | 10 degree flash window (share of width x height) |
|---|---|---|---|
| 16:9 | `1920x1080` | x 76.8 to 1843.2, y 43.2 to 1036.8 | 0.33 x 0.44 |
| 9:16 | `1080x1920` | x 43.2 to 1036.8, y 76.8 to 1843.2 | 0.79 x 0.33 |
| 1:1 | `1080x1080` | x 43.2 to 1036.8, y 43.2 to 1036.8 | 0.44 x 0.33 |
| 4:5 | `1080x1350` | x 43.2 to 1036.8, y 54.0 to 1296.0 | 0.56 x 0.33 |

(Computed with `qa_scan._window` on the 192x108 decode and `qa.inside` on 2026-11-12.) The window is WCAG's 341 x 256 field on a 1024 x 768 view with the frame fitted into it. The short side is 1080 px in all four, and the text gates scale every size rule by `1080 / min(W, H)`: at 1280x720 a 24 px font counts as 36 px. `--ss 2` draws at twice the size and scales down in `finish()`: four times the pixels, for thin lines and small text. Vertical platforms draw their own buttons, captions and progress bars over the lower part and the right edge; their size changes, so no gate measures them: keep key text, faces and the logo clear of the bottom and right of a 9:16 frame and check the platform's current guide when the brief names one.

`--fps` takes any whole number; one frame lasts `1 / fps` (33.3 ms at 30, 41.7 at 24, 16.7 at 60). Tempos whose beat is a whole number of frames (`contract.whole_frame_beat`, 60 to 200 BPM, computed 2026-11-12), the list Q905's fix names:

| fps | Whole-frame BPM |
|---|---|
| 24 | 60, 72, 80, 90, 96, 120, 144, 160, 180 |
| 25 | 60, 75, 100, 125, 150 |
| 30 | 60, 72, 75, 90, 100, 120, 150, 180, 200 |
| 50 | 60, 75, 100, 120, 125, 150, 200 |
| 60 | 60, 72, 75, 80, 90, 100, 120, 144, 150, 180, 200 |

The rate also sets Q902's late limit (one frame, never over 60 ms) and grain is held for 2 frames at any rate (`grain.grain` steps at fps / 2).

### The encode, exactly

Rung a is `render.encode_cmd`: libx264, preset medium, CRF 18, yuv420p, converted to BT.709 limited range and tagged so (`contract.COLOR_VF`, `COLOR_FLAGS`). The CRF the full run uses is `CRF` in `run_all.py` (it passes it to the encode); `render.CRF` is only the default for code that calls `render.render_to_ffmpeg` itself. For a grain-heavy style set `CRF = 20` in the working copy of `run_all.py`. The mux (`contract.mux_cmd`) copies the picture, encodes AAC at 320 kb/s (`contract.AAC_ARGS`), cuts to the shorter stream and sets `+faststart`; a silent piece muxes the picture alone. The engine always encodes with libx264; hardware encoders (NVENC) are not wired in, and a GPU encoder would save file size, not time, next to drawing the frames. When a size cap is tight, AV1 buys the most room, at the price of players that cannot open it; say so when the file is AV1 or VP9 (older QuickTime and some company players fail). Rung b gates Q705, Q707 and Q708 read NOT CHECKED by design. Rung c is a GIF of at most 15 s, at most 960 px wide, at 15 fps, with no sound.

### Hand-over by destination

| Destination | Hand over |
|---|---|
| Slack or another chat app | The MP4, and the GIF preview (rung c) beside it |
| Email | The MP4 only when it is small; otherwise a link, with a 720p cut and a poster PNG on offer |
| A site, an intranet, a wiki | H.264 MP4 (rung a) |
| Reels, Shorts, TikTok | 9:16 at 1080x1920, H.264 MP4 |

Ask where the file goes and what its limit is; do not quote a platform limit that was not checked.

### A size budget

Set `BUDGET_MB` in scenes.py, or pass `--budget-mb N`, and `run_all.py full` caps the picture encode:

- maxrate (kb/s) = 0.95 x budget x 8000 / duration - the audio's kb/s (from `contract.AAC_ARGS`); bufsize = maxrate for a film under 30 s, else twice it. A budget that leaves no video bitrate is refused before any frame is drawn.
- It is a cap, not a guarantee: x264's VBV can pass the total by up to about 0.9 x bufsize. `qa.py check` gets the budget as `max_mb`, and Q1001 fails a file over it.
- Measured: the lighthouse film with a 20 MB budget came to 11.5 MB of picture (uncapped: 34.8 MB), so about 13.9 MB with the audio at its nominal 320k. Under the cap, CRF 20 spent about 70 percent of the 16.6 MB the picture was allowed, so a tight budget on heavy grain costs more quality than it has to; less grain is the better fix.

Caps from `run_all.caps` (computed 2026-11-12; the audio term is 320 kb/s, 0 for a `SILENT` piece):

| Budget | Length | maxrate / bufsize (kb/s) | Silent |
|---|---|---|---|
| 4 MB | 15 s | 1707 / 1707 | 2027 / 2027 |
| 8 MB | 30 s | 1707 / 3413 | 2027 / 4053 |
| 10 MB | 60 s | 947 / 1893 | 1267 / 2533 |
| 25 MB | 60 s | 2847 / 5693 | 3167 / 6333 |

A budget too small for the audio alone stops the build before any frame is drawn (`a 0.05 MB budget leaves no video bitrate for 7.5 s with 320 kb/s of audio`). Q1001 checks the finished file against the budget (or `qa.py check --max-mb`); Q1002 notes any bitrate over 12 Mb/s (flat graphics land at 1 to 5). To shrink a file, in order: lower the grain's std or drop it and the vignette, raise CRF to 20, drop to 720p (`--size 1280x720`), drop to 24 fps, shorten the cut.

File names: a file that failed a gate becomes `<name>.rejected.mp4`, one from a run that broke before its verdict `<name>.unchecked.mp4`; neither is ever delivered, and the next `run_all.py full` or `audio` deletes both before it starts. The by-hand rungs write `out_av1.mp4`, `out.webm` and `preview.gif` (commands in `engine.md`); rename them to the same pattern before delivery. The build's own files (`video.mp4`, `mix.wav`, `frames.hash` and the rest) keep the names `contract.py` gives them: the gates find them by those names. Write the aspect with an `x` (`launch_9x16_15s_v2.mp4`): Windows does not allow `:` in a file name.
