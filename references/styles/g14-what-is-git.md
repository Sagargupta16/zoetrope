# S-g14-what-is-git · Warm-paper beginner explainer with narration
**Source:** @Yunn260414, https://x.com/Yunn260414/status/2104044910769016888 · our build: g14-what-is-git
**Use when:** "explain {topic} to someone with zero background", "what is X in simple terms", "beginner tutorial with common commands or terms", "narrated explainer with captions", "use metaphors"
**Defaults:** 3:30 in the original (we recommend 60 to 90 s for chat, fewer concepts) · 16:9 1920x1080 · 30 fps · narrated with always-on captions

## The brief (reusable prompt)
Make a video on the topic: What is {topic}. Explain it simply so someone with zero background can understand, then introduce the common commands or terms and what each means. It must have sound, narrated in English.

## Scene plan
| Time | Beat | What happens on screen |
|---|---|---|
| 0:00 | 01 The problem | A "Documents" window fills with essay_final, essay_final_2, essay_final_REALLY_final files; rows shuffle; handwritten "which one is the latest?" and a big "?" |
| 0:14 | 02 What is it | Title plus three fact chips; "time machine" metaphor: folder, time line, four snapshot polaroids with camera flashes, a "you are here" pin travels back |
| 0:37 | 03 Save points | Tiny platformer: character reaches a flag (GAME SAVED), falls on spikes, rewinds (RELOADED); flags become commit dots |
| 0:51 | 04 Two words | Repository card and commit card whose receipt fills in on the narrated words |
| 1:10 | 05 Staging | Three edited files, two go into a cardboard box, one stays out; stamp, tape, label; box flies into a new commit dot |
| 1:26 | 06 Branches | Main line, a blue branch splits, gets commits, merges; a purple failed branch is deleted, "main is untouched" |
| 1:49 | 07 Sharing | Your laptop, a teammate's laptop and an online copy; orange commit pushed up, blue commit pulled down |
| 2:06 | 08 The commands | Terminal plus a plain-English card per command with a progress rail of 11 (init, status, add, commit, log, branch, switch, merge, clone, push, pull); commands typed character by character |
| 3:12 | 09 Recap | The everyday loop, then end card "a time machine for your work, so you can experiment without fear" with command chips |

## Look
- Palette: accent orange #F05133, ink #1F1B2D, blue #3B6FE0, paper #F4EFE6, red #E5484D, green #1F9D57. Warm paper, not a dark hacker look, so it feels friendly.
- Type: Sora (headings), Inter (body), IBM Plex Mono (terminal, 24 px), Caveat 700 (handwritten notes). All free Google fonts; on a Mac use Avenir Next, Helvetica Neue, Menlo and Bradley Hand as substitutes.
- Layout and texture: chapter pill top-left, one-line word-highlight captions at the bottom (current word in orange).

## Motion
One metaphor per idea, then reuse it: snapshots for commits, a game save point for "why", a parcel box for staging, train-line style lines for branches, a cloud for the remote. Command cards reuse the same drawings. Every cue is keyed to narration word times: card fills, highlight, typing. Use ease-out quad (1 - (1 - k) ** 2) for most entrances and ease_out_cubic for the bigger ones, ease_out_back for stamps and pins, linear for typing (about one character per frame group). Pure function of t.

## Audio
Narration: calm, clear male voice (original: en-US-AndrewMultilingualNeural at -4% rate). Here use a text-to-speech voice (`voice.md`; audition 2 or 3 voices and measure their pace). Quiet synthesized music bed, about 150 sound effects (clicks, whooshes, camera shutter, stamp). Duck music about 7 dB under speech. Target -14 LUFS, true peak under -1 dBTP (original -14.0 LUFS, -1.3 dBTP). Last seconds: a single fading chord.

## Build notes
Generate the voice per scene, measure each mp3 with ffprobe, and build SCHEDULE from the real durations plus gaps; approximate word times by splitting each line's duration by character count (most text-to-speech engines give no word timestamps). Draw captions in PIL from those times. Terminal text must be real output: run the tool in the sandbox if available, otherwise only show output we are certain of. Use a fictional user and placeholder URL. For a chat-sized cut, keep 3 to 4 metaphors and 4 to 5 commands. Omit logos; draw a simple glyph instead.

## Pitfalls (from what went wrong in our build)
- TTS may read "git" as "get": listen to or transcribe those lines and respell phonetically if needed.
- Terminal text at 24 px is small on a phone; use 32 px or more for mobile targets.
- Some scenes had too much empty space (top half of the branch scene); use a denser layout for small screens.
- Do not reuse state across frames; flashes and tints that start "visible" before their cue stay stuck. Compute them purely from t.

## Style QA
- Each narrated sentence has its own visual beat; no sentence plays over an unchanged screen.
- Caption highlight stays within 0.2 s of the spoken word.
- Every fact on screen is checked (for example creation year, licence) and terminal output is real.
