# Troubleshooting

| Problem | What to do |
|---|---|
| No ffmpeg on the machine (`shutil.which("ffmpeg")` is None) | Do not stop. Write the frames and audio to a folder and offer to install ffmpeg (Windows: `winget install Gyan.FFmpeg`; Mac: `brew install ffmpeg`). If the installed build has no libx264, use rung b (AV1 MP4 or VP9 WebM with AAC or Opus); make a GIF preview (rung c) if nothing else works. Tell the user which rung and that older QuickTime may not play AV1 or VP9. |
| A fact or a media file is needed mid-build | Render scripts download nothing. Fetch facts with the agent's web tools first and ask the user for any media, then pass the files in. Everything else (frames, synthesized audio, encode) works offline. |
| A text-to-speech download link expired | Generate the line again and save the file to the working folder as soon as it is ready. |
| No text-to-speech is available (none wired up yet, or no access) | Fall back: (1) music-only, with synthesized music on the beat grid, or (2) on-screen captions timed for reading (`qa-gates.md` gate 4). Say plainly that there is no voice-over and why. Offer to add a voice once one is set up. |
| The voice reads names wrongly | Respell phonetically in the voice text only; keep the correct spelling on screen; ask the user to check those lines. |
| A font is missing on the device | List C:/Windows/Fonts (Windows) or /System/Library/Fonts and /Library/Fonts (Mac), pick the nearest installed font, tell the user which one we used. Never silently fall back to the PIL default font. |
| Render is slow | First make a fast preview: 15 fps, half size (960x540), or fewer frames (a 5 s slice of the riskiest scene) and check that. Then render the full file once. Also: render only changed scenes and reuse the others, cache static backgrounds as images, draw at 1x and supersample 2x only the scenes with thin lines, cut grain and blur from the preview. |
| Run times out | Render in batches (for example 100 frames per call, frame names `f_00000.png`), skip frames that already exist, and encode when the last batch ends. |
| Out of disk or memory | Check `shutil.disk_usage`, write JPEG-quality PNG at final size only, delete frame folders after encode, process frames one at a time (no list of all frames in memory). |
| Encode result fails a gate | Change one thing at a time: loudness (loudnorm two-pass), size (CRF or resolution), duration (trim audio), then probe and measure again. Do not deliver a file that failed a gate without telling the user. |
| Session tab does not show the video | Share the file path, and show the poster PNG and contact sheet instead. |
| Time is running out | Deliver what is verified (a shorter cut or the GIF preview), and list what is still open in "Known weak spots". |
