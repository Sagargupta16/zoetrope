# Delivery report template

Keep the message short and in this order. Fill every field from a real tool result; write "not checked" when we did not run a gate. The first line is the `DELIVERED` line, quoted exactly as `run_all.py` printed it, and the `APPROVAL` line follows it. A file that has no DELIVERED line (`<name>.rejected.mp4`, `<name>.unchecked.mp4`, or rung b and c) is not reported as delivered: say what failed or what was checked by hand instead.

```
DELIVERED {absolute path} ({MB} MB, {s} s, {LUFS} LUFS, {dBTP} dBTP)
APPROVAL: {none yet | current | stale: ...} -> {next step}

Your video is ready: {title}

File: {full path}   (also shown in the side tab; qa.py verify: {SAME | not run})
Length: {mm:ss} | Size: {resolution} at {fps} fps | Codec: {video codec} + {audio codec} | File size: {MB}
Encode rung used: {a: H.264 MP4, frames piped into the encode / b: AV1 MP4 or VP9 WebM from PNG frames / c: GIF preview}
Why this rung: {for example "ffmpeg with libx264 was found on this machine"}
Plays in: {what we know, for example "Chrome and Slack web; older QuickTime may not play AV1/VP9"}
Extra files: {GIF preview for Slack, poster PNG, 720p cut, none}

What is in it: {one line per scene, with start time}
Audio: {music synthesized by us | music supplied by you | voice: {engine} {voice name}} | Loudness {x} LUFS, true peak {y} dBTP
Master: {the master line as printed, and any re-master lines}

QA run: {the QA: line as printed, for example "QA: PASS (49 checks, 0 FIX, 0 NOTE, 0 NOT CHECKED)"}
- Proof sheets: {n} stills on proof.png; proof_keys.png {shown} of {n} moments, {p} pages; strips {k | none}; gantt
- Text inside safe area, no overlaps, registry complete (Q201 to Q209): {pass / list}
- Contrast (Q301, 4.5:1 body text): {pass, lowest ratio and its text / list with values}
- Reading holds (Q401, {profile} profile): {tightest hold and its line}
- First and last frame (Q501, Q502): {grey means}
- Flashes (Q601 to Q603, WCAG 2.2, 3 a second at most): {worst a second / passages that need care}
- Purity and lint (Q1201 to Q1206): {frames checked / findings}
- Audio and video sync at hits (Q902, Q903): {worst ms on the stem, mux ms / list}
- Loudness and true peak (Q801, Q802, Q805): {values}
- What the narration says (Q806, Q807): {words heard as written / each NOTE and what listening found / no narration}
- Frame scans (Q1101 to Q1105): {NOTEs and what each turned out to be / none}
- Not checked: {every NOT CHECKED row and anything skipped, and listening by ear: checked by measurement only, not by ear}

Facts used (checked {date}):
- {claim} -> {source}
Media and credits: {file, source, licence, attribution card yes/no | "no third-party media"}{; recorded instruments: the lines `sampler.credits(names)` prints, CC0}
Known weak spots: {honest list, for example "small labels on a phone", "mix checked by measurement, not by ear"}

Want changes? Tell us the scene and the time (for example "scene 3, 0:12") and we will rebuild only what changes.
```

## Before the report

Every value in the message is copied from a tool's output in this session, never retyped from memory or taken from an agent's summary; anything that was not run is listed as not checked.

1. The run ended with an `APPROVAL` line and one `DELIVERED` line. A `REJECTED` or `UNCHECKED` line means there is nothing to deliver: a `<name>.rejected.mp4` or `<name>.unchecked.mp4` is never sent, shown as finished or described as a result.
2. The final reviewer replied REVIEW PASS, and `qa.py approve --review <reply file>` recorded it.
3. `python qa.py verify <file>` printed `VERIFY: SAME`: the file is byte for byte the approved one.
4. One ffprobe run and one ebur128 run on the file give the numbers; they agree with the `DELIVERED` line to its rounding (I and Peak from the ebur128 Summary):
   ```
   ffprobe -v error -show_entries format=duration,size:stream=codec_name,width,height,r_frame_rate -of default=nw=1 <file>
   ffmpeg -nostdin -hide_banner -i <file> -af ebur128=peak=true -f null -
   ```

## Filling the fields

| Field | Where it comes from |
|---|---|
| File name | `<slug>_<aspect>_<length>s_v<n>.mp4` (`formats.md`) |
| Length, size, resolution, fps, codec | The `DELIVERED` line and ffprobe's `duration`, `size`, `width`, `height`, `r_frame_rate`, `codec_name` (rung a is h264 with aac) |
| Loudness | The `DELIVERED` line and the ebur128 Summary. A silent piece says `silent` there and in the report |
| Encode rung | Which rung of the ladder made the file and why, every time, even rung a: rung a needs only "libx264 present"; rung b names the missing libx264 and the encoder used; rung c says the GIF is a preview |
| QA run | The `PROOF:` and `QA:` summary lines as printed; every reviewer id with its verdict (for example proof-1 REVIEW PASS, final-1 REVIEW FIX, final-2 REVIEW PASS) |
| Not checked | Always two lines: how it looks and sounds to a person (no script listens or watches; the reviewer read the sheets and frames) and photosensitivity (the flash gates measure WCAG 2.2 limits, but no tool certifies compliance). Then every `NOT CHECKED` row (on rung b, Q705, Q707 and Q708 by design) and anything skipped, such as a platform's own overlay zones or a voice engine's word clock on a voice nobody measured |
| Known weak spots | Every NOTE row in the final check and why it stays (an `ALLOW` entry says it was designed), every reviewer P1 or P2 left open with its time, anything close to a limit, and a true peak inside -1 dBTP but within the meter tolerance (run_all prints a `note:` line for that) |
| Facts used | The scenario's Facts table: each claim on screen, its source and the date it was read. A claim with no source is not on screen |
| Media and credits | The font files `engine.font()` used; the music (made in code by `audio.py` or `synth.py`, recorded instruments with the `sampler.credits` lines, or the user's own track and its licence); the voice engine, voice and weights licence (`voice.md`); every image, logo or clip the user supplied, with its source |
| Next options | Two or three concrete follow-ups that fit the brief: a 9:16 cut (`--size 1080x1920`), a GIF preview (rung c), a shorter cut, a 720p cut for email, a poster PNG of the strongest frame, another voice from `voice_samples.py` |

## Rules

- Quote the lines exactly as the tools printed them; never round or retype a number.
- Never claim a check, a render or a review that did not run. A check that could not run is listed under Not checked with its reason, not left out.
- Never deliver past a size limit the user gave: the file must pass Q1001 against that limit (`--budget-mb` or `BUDGET_MB`, `formats.md`).
- When time runs out, deliver what is verified (a shorter cut, or the GIF preview made from a verified file) and list everything still open under Known weak spots.
- A change after the approval reopens review: `qa.py diff --expect <windows>`, a fresh final reviewer, a new approval, then a new report.
