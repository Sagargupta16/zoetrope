# Formats and delivery

| Preset | Size | Use |
|---|---|---|
| 16:9 | 1920x1080 | default; decks, YouTube, desktop, embeds |
| 9:16 | 1080x1920 | phone vertical, Stories, Shorts, Reels |
| 1:1 | 1080x1080 | feeds |
| 4:5 | 1080x1350 | portrait feeds |

- **FPS:** 30 (default). Keep to one fps for the whole piece. Use even width and height (yuv420p needs it).
- **Default when unsure:** 16:9, 1920x1080, 30 fps, H.264 MP4.
- **Layout per aspect:** re-plan the layout for 9:16 and 1:1 (stack, bigger type), do not just crop a 16:9 design. Same `SCHEDULE`, different layout code keyed on `E.W < E.H`.
- **Naming:** `{slug}_{aspect}_{length}s_v{n}.mp4`, for example `{product}-launch_16x9_15s_v1.mp4`; lowercase, hyphens in the slug, bump `v` for every revision; GIF as `{same}_preview.gif`. Keep the working folder (scenes.py, audio.py, frames) so edits are cheap.
- **Report at the end (all of it):** file path, duration, resolution, fps, codec and container, file size, loudness (integrated LUFS and true peak), which encode rung was used and why, frames checked in QA (list the times), what the audio is (music BPM, voice name), any assumption made, and how to request changes (copy, color, timing, aspect). Show the final video or a frame in a session tab. Add credits for any third-party material; none for synthesized audio and drawn shapes.

## File size (measured on the 2026-10-28 samples, 60 s each, H.264)

| Sample | Look | Size | Bitrate |
|---|---|---|---|
| Derivative explainer | flat dark ink, thin lines | 3.4 MB | 0.45 Mb/s |
| Nook launch film | flat colour, 2x supersampled | 7.1 MB | 0.95 Mb/s |
| Tide serpent battle | pixel art, dithered | 17.9 MB | 2.4 Mb/s |
| Everything is a rectangle | dense dashed outlines, 9:16 | 19.6 MB | 2.6 Mb/s |
| Lighthouse credits, final | grain std 1.6, CRF 20 | 35.9 MB | 4.8 Mb/s |
| Lighthouse credits, first master | grain std 2.6, CRF 18 | 140.2 MB | 18.7 Mb/s |

Baked film grain is the size driver: keep it at std 1.6 grey levels or less and encode grainy styles at CRF 20 (`run_all.py` has `CRF`). Before rendering a grainy style, time a 4 s slice with `kits/g11-movie-credits/grain_test.py`. `qa.py check` notes anything over 12 Mb/s (Q1002).
