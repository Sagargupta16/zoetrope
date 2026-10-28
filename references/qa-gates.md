# QA gates

Read this before the final render and again before the delivery message. Every gate below runs inside the engine: Python with PIL and numpy on the device or in the sandbox, plus ffmpeg and ffprobe where they exist (check `shutil.which("ffmpeg")`). No gate needs a network.

Run all gates on the final file, not only on stills. Keep every check as a small function that returns pass or fail plus the numbers, and print a table at the end.

## Automated check: `qa.py check`

`python qa.py check <video> --scenes . --size WxH --fps N [--bpm N] [--max-mb N] [--silent]` runs every gate that can be measured on the finished file and prints one row per check as `PASS`, `FIX` or `NOTE`, with the fix after `->`. It ends with `QA: PASS` or `QA: FIX (n)` and exits 1 on any FIX. A NOTE needs a look but may be intended (a planned silence, a cut off the grid on purpose).

| Code | Gate | What it measures | On failure |
|---|---|---|---|
| Q501 | 5 | First frame grey mean above 25 and std above 12 | FIX |
| Q502 | 5 | Last frame grey mean above 25 (no fade to black) | FIX |
| Q503 | 5 | End card held: last 1 s changes less than 10/255 | NOTE |
| Q601 | 6 | No second with more than 3 flashes | FIX |
| Q701 | 7 | Duration within 0.1 s of `--duration` or `DURATION` | FIX |
| Q702 | 7 | Frame rate equals `--fps` | FIX |
| Q703 | 7 | Resolution equals `--size` | FIX |
| Q704 | 7 | Frame count within 1 of duration x fps | FIX |
| Q705 | 7 | `yuv420p` for H.264 | FIX |
| Q706 | 7 | An audio stream is present (skip with `--silent`) | FIX |
| Q801 | 8 | Integrated loudness within 1 LU of -14 LUFS | FIX |
| Q802 | 8 | True peak at or below -1 dBTP, with the time of the loudest moment | FIX |
| Q803 | 8 | No near-silent second (below -60 dBFS) inside the piece | NOTE |
| Q901 | 9 | Scene starts in `SCHEDULE` on the `BPM` grid, within one frame | NOTE |
| Q1001 | 10 | File size, against `--max-mb` when given | FIX only with a limit |
| Q1002 | 10 | Bitrate at or below 12 Mb/s (flat graphics land at 1 to 5; baked grain is the usual cause above) | NOTE |
| Q201 | 2 | Every text at rest inside the 4 percent safe area (registry, every frame) | FIX |
| Q202 | 2 | No two texts overlapping at rest | FIX |
| Q203 | 2 | No two different texts overlapping while either is fading (crossfades in place) | FIX |
| Q301 | 3 | Contrast against a ring of real pixels around each text: 4.5:1, or 3:1 for large text (36 px, or 24 px bold, at 1080) | FIX |
| Q401 | 4 | Each text's longest rest at least 0.5 s + 0.3 s per word, never under 1 s | FIX |
| Q402 | 4 | Key text at least 36 px at 1080 (mark decoration `texture=True`) | NOTE |
| Q902 | 9 | Each entry in `CUES` has its audio onset within one frame and its picture change within `CUE_LAG` + 1 frames | NOTE |
| Q200 | 2 to 4 | `scenes.py` has no registry, so gates 2 to 4 did not run | NOTE |

Gates 2 to 4 and Q902 run from the registry in `scenes.py`:

- `text_items(t)` returns every text drawn at time t as dicts: `s` (the string), `box` (l, t, r, b in output pixels; `engine.text_box` gives it), `fg` (colour), `alpha` (0 to 1), `px` (font size), `bold`, and `texture=True` for decoration nobody must read. At or above alpha 0.98 counts as at rest.
- `CUES` lists every moment sound and picture must share: `(t, label)` or `(t, label, kind)` with kind `both`, `audio` or `picture`. `CUE_LAG` is how many frames the picture may trail by design (2 for the pixel-art battle style).
- `KEY_TIMES` lists extra moments the proof key sheet must show: `(t, why)`.

Compute each text's layout in one function that both `draw()` and `text_items()` call (the template's `title_state()`), or the registry drifts from the picture. The builder runs `qa.text_gates(scenes, W, H, FPS)` at proof time; the `zoetrope-reviewer` agent still checks by eye what no number can (its R codes). `python qa.py look <video>` writes small frame copies and `review/look.jpg` so a model never reads a full-size frame.

## 1. Frame checks and contact sheet
Render stills at every scene boundary (one frame before and one after the cut) and every scene midpoint, using the same `draw(t)` and `SCHEDULE` as the real render. Build a contact sheet and open it in the OS viewer before the full render.

`qa.contact_sheet(draw, SCHEDULE)` builds this sheet: every scene boundary (one frame before and one after the cut) and every midpoint, each labelled with its time.
Look at the sheet for: empty frames, half-drawn text, cards stuck over each other, a different font, wrong colours. Then render a 6 to 12 frame proof, fix, and only then render everything. Frames that look odd for 1 or 2 frames mid-transition (a letter mid-rise, a half-closed iris) are acceptable if they read as motion; a stuck overlap on a hold frame is not.

## 2. Clipped or overlapping text, safe areas
Measure with PIL, do not eyeball. For each text item use `ImageDraw.textbbox` at the final font size.
`qa.text_box(font, text, xy)` returns (l, t, r, b); `qa.inside(box, W, H)` checks the 4 percent edge pad (the safe area in `playbook.md`); `qa.overlap(a, b)` checks two boxes.
Check at each hold frame (not mid-transition): every text box inside the safe area, no two text boxes overlap, no word split into a one-word orphan line, no text under a fixed overlay (a HUD, a logo corner, a caption bar). For wrapped text, test the widest line. For vertical formats keep text away from the bottom area where a platform draws its own controls.

## 3. Contrast
Body text must reach WCAG 4.5:1 (large text, 24 px and up at 1080p bold or 36 px regular, may use 3:1). Compute it from the real pixels behind the text, not from the palette alone.
`qa.region_contrast(frame, box, fg)` measures it against the median colour of the real pixels in the box (`qa.contrast` and `qa.lum` are the WCAG formulas).
If a brand colour fails (a coral or mint on cream is a known case), darken the text tint and note it in the report. Do not use blend modes (difference, overlay) for text that must be read; they drop to mid-contrast on some backgrounds.

## 4. Minimum hold for reading
Every text block must stay fully visible long enough to read. Compute from `SCHEDULE`: hold = time from fully drawn to start of exit.
- Rule of thumb we use: hold >= 0.5 s + 0.3 s per word for body lines, and at least 1 s for a single short label (`qa.min_hold(words)`). Raise it for non-native readers and for small type.
- Flag any block under that. The fix is to cut words, lengthen the scene, or split the scene, never to shrink the type.
- Text below 24 px at 1080p (HUD labels, tags, footnotes) counts as texture: nothing the viewer must learn may live there. For phone viewing keep the lines that matter at 36 px or larger.
- With no voice-over, time every caption for reading; with voice-over, the line must be on screen before the word is spoken.

## 5. First frame and thumbnail
Frame 0 is what many platforms use as the thumbnail. It must not be black or empty.
`qa.first_frame(draw)` returns (ok, mean, std); frame 0 fails when its grey mean is 25 or less or its std is 12 or less.
Fix: draw the hook (headline or main visual) fully at t=0 and animate only the extras, or add a poster frame (export a PNG from the strongest frame at the end of scene 1 as the cover image and give it to the user). Also check the last frame: it should hold the end card, not fade to black, for at least 1 s.

## 6. Flashes and photosensitivity
No more than 3 flashes in any one second. Count a flash as a pair of large, fast luminance swings (full-frame or more than about a quarter of the frame).
`qa.flash_report(draw, dur)` returns each second that breaks the rule as (second, flashes): a flash is a pair of frame-to-frame jumps over 20/255 in the mean grey of a 64x36 frame.
`qa.flash_report_file(path)` runs the same test on an encoded file (frames read with ffmpeg at 64x36 grey). Typical sources of trouble: full-frame colour wipes held a few frames, background colour flipping on every half-beat (4 to 5 flips per second), inverted impact frames, strobing glitch hits. Fix: fewer flips, soften the swing (lower the contrast between the two colours), stretch a flash over more frames, or drop it. Tell the user when a video has a deliberate fast passage.

## 7. Duration, resolution, fps, codec
`qa.probe(path)` returns duration, size_mb, w, h, fps, frames, vcodec, pix and acodec from ffprobe.
Expect 1920x1080 (or the vertical size the user asked for), 30 fps, the codec of the rung used (see the encode ladder in `engine.md`), `yuv420p` for H.264, an audio stream present, and duration within 0.1 s of the planned `SCHEDULE` end. Check the frame count equals `round(duration*fps)`. If the audio is longer or shorter than the video, trim with `-shortest` or pad with silence; never ship a mismatch.

## 8. Loudness and true peak
Target -14 LUFS integrated, true peak at or below -1 dBTP.
`qa.loud(path)` returns I (LUFS), LRA (LU) and the true peak (dBFS) from ebur128.
Fix with loudnorm two-pass: measure with `loudnorm=I=-14:TP=-3.0:LRA=11:print_format=json` (TP -3.0 because the AAC encode adds 1 to 1.5 dB of true peak, as in `mixing.md`; `audio.master` runs both passes), then run again with `measured_I`, `measured_TP`, `measured_LRA`, `measured_thresh` and `linear=true`. If ffmpeg is not available, normalise in numpy: measure, apply gain, then soft-limit. Accept within about 1 LU of target. Also check per-second RMS for dead silence in the middle, and that voice stays clearly above the music (music ducked about 8 dB under speech). A hard limiter that removes more than about 3 dB on many hits makes the mix pump; if the limiter works that hard, lower the raw level of the loudest stacked hits instead.

## 9. Audio and video sync at hits
Every cut, hit and whoosh must land on the beat grid and on the frame where the picture changes.
`qa.snap_ok(t_cut, bpm)` passes when a cut is within one frame of the nearest beat (use the BPM written in SCHEDULE).
Check that each cut time in `SCHEDULE` is a multiple of a beat (or half-beat), and that each SFX start sample = `round(t*sr)` of the same time. Then verify on the file: detect onsets in the audio (energy jump per 10 ms window) and compare with the frame where the picture changes (frame difference spike). Differences over one frame (33 ms at 30 fps) are a fail. Voice lines: compare the time each line starts with the caption that goes with it (voice length from the audio file, not from a guess; some voices speak at about half the speed of others, so always measure).

## 10. File size
Ask the user where the video goes and what the limit is, because limits change by workspace and by plan; we do not quote numbers we have not checked. Then compare `probe(path)["size_mb"]` with that limit.
- Slack: a short GIF preview (15 s at most, 960 px wide at most, 15 fps) or an MP4. Offer the GIF as a preview next to the MP4.
- Email: attach only if small; otherwise share a link. Offer a 720p cut and a poster PNG.
- Intranet or wiki: MP4 H.264 plays everywhere; AV1 or VP9 may not play in older QuickTime or some corporate players, so say so.
To shrink: raise CRF (CRF 20 instead of 18 roughly halves the size on grainy or textured scenes), drop grain and vignette, lower to 720p, lower fps to 24, shorten the cut. Dense textures (grain, halftone, particles, fine paper) cost bitrate; keep them out if there is a size limit.
