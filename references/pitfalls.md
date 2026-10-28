# Common pitfalls (problem -> fix)

1. Mix judged by meters only, never heard -> say so in the report; ask the user to listen once on speakers and tell us what to change (kick and bass 1 to 2 dB down was the typical fix).
2. Bass-heavy synthesized groove, most energy under 120 Hz -> high-pass the master slightly, lower kick and bass, add brighter keys.
3. Music is a short loop with no arc (LRA 0.9 to 2.7 LU) -> add a build, a drop-out of one 16th note before the drop, an end chord; do not rely on level changes after normalising.
4. Limiter squashes hits when the mix is pushed to -14 LUFS (up to 9 or 10 dB on the biggest impacts) -> lower the stacked kick, stab and clap gains before the limiter, then normalise.
5. Final chord or end hit is much louder than the average (about -11 LUFS short-term against -14 integrated) -> lower the last chord a few dB, or accept and tell the user.
6. Reverb impulse not normalised, so the mix turned into reverb -> normalise the impulse response and check wet/dry level.
7. First frame nearly black or an empty paper frame, so the thumbnail is weak -> draw the hook at t=0 and export a separate poster PNG.
8. Empty frame at the start of each scene (lead silence, 0.3 to 0.4 s) that reads as a cut to black -> start the next scene's picture before the previous one ends, or trim the lead silence in the audio.
9. Text too small: 14 to 26 px labels are unreadable on a phone -> keep key lines at 36 px or more; treat smaller type as decoration only.
10. Text on screen for only 1 to 2.5 s because late-appearing body lines get the short end of a scene -> bring the body line in earlier, or extend the scene, using the reading-hold rule (`qa-gates.md` gate 4).
11. Too many items per second (2 s per chapter, 0.75 s for key lines) -> fewer items per video or a longer cut; a 15 s brief with many milestones needs about 20 to 24 s to read well.
12. Brand colour fails contrast (cream on coral badge at 2.6:1; small coral or mint text) -> use a darker tint for small text and report the deviation.
13. Difference blend mode on a HUD turns cyan on red and low contrast -> no blend modes on readable text.
14. Strobe-like passages (background flipping 4 to 5 times per second, full-frame accent wipes held 4 frames, inverted impact frames) -> run the flash test (`qa-gates.md` gate 6), reduce, and warn.
15. Fast moves look steppy or strobe at 30 fps (zoom from scale 1 to 34 in 0.7 s, scrolls near 1,200 px/s) -> add motion blur (average 3 to 5 sub-frames per frame), slow the move, or render 60 fps if the size limit allows.
16. Mid-transition stills look broken (letters as slivers, half-masked words, translucent stacked cards, mid-flip warping) -> accepted only if 1 to 3 frames; check them in the contact sheet and fix any that stay over 0.3 s.
17. Cards or elements overlapping on hold frames (a label over a flag, call-stack HUD over layout, a title crossfade over a fading header) -> use the overlap test (`qa-gates.md` gate 2) and move elements or stagger the exit.
18. Fonts fall back to a system font when the file is rendered elsewhere -> use fonts found on the device (list C:/Windows/Fonts on Windows, /System/Library/Fonts and /Library/Fonts on a Mac), load by absolute path, and fail loudly if a font is missing.
19. Hand-built maps or sprites look rough (coarse land mask, blocky figures, crude letters) -> say it is a schematic in a note on screen; do not call it accurate.
20. Stale facts (review counts, prices, rankings) -> put the date on screen and in the report ("as of ..."), or leave the number out.
21. A simplified story presented as one real session (a git or code walkthrough that jumps between states) -> add a line like "a little later" or a note that it is simplified.
22. Text-to-speech mispronounces names and acronyms (a short word read as "it", brand names, years) -> spell it phonetically in the voice text, keep the on-screen text correct, and ask the user to listen to those lines.
23. Voice speed differs between voices -> measure each line's real length before fixing the schedule; do not assume one speed.
24. Footage or photos upscaled from low resolution look soft at 1080p -> use only for a deliberate archive look (add grain, duotone) or ask for a better file.
25. Footage with third-party signage or logos visible -> crop or blur, or tell the user; we do not show third-party logos.
26. Several seconds of a scene go sparse after a big effect (a shockwave that clears the stage by 6.5 s of an 8 s story) -> shorten that scene or add a second beat.
27. Audio and caption sync only approximate because shots were chosen from low-resolution previews -> check at least 40 frames against the script lines and fix the ones that show the wrong thing.
28. Large files for short videos (grain, halftone, petals, paper texture; 56.8 MB for 46 s, 15.8 Mbps) -> CRF 20, no grain, or 720p when the destination has a limit.
29. Render stopped by low disk space -> check free space first (`shutil.disk_usage`), delete intermediate PNG frames and raw WAV once the file is verified, and say what was removed.
30. Layout drift in a still between sampled frames (cursor blink shows off at some times) -> this is correct motion, not a bug; do not "fix" it.
31. Session ended before the final QA -> run the gates in `qa-gates.md` anyway after the build; never report "checked" for something we did not run.
32. A claim in the report that is not backed by a tool result ("looks great", "plays everywhere") -> write only what we measured, and mark the rest unverified.
33. Two strings crossfading in the same spot read as garbage for 10 to 15 frames ("h =>0.001") -> fade the old one out, then the new one in; Q203 catches it from the registry.
34. A fix or an optional tweak made after a REVIEW PASS breaks something next to it (a damage plate moved onto the hero; a line-height change hid a counted outline under a header) -> list every post-PASS change with its times and review those frames and their neighbours again.
35. The AAC encode adds 1 to 1.5 dB of true peak (-1.5 in the WAV became -0.4 in the MP4) -> master at TP -3.0 (`audio.master` default); Q802 names the loudest moment.
36. Storyboard slots shorter than the reading time force the builder to re-time captions (27 of 83 lines in one batch) -> run `qa.py holds` on the scenario before any build.
