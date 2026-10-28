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
- Frame scans (Q1101 to Q1105): {NOTEs and what each turned out to be / none}
- Not checked: {every NOT CHECKED row and anything skipped, and listening by ear: checked by measurement only, not by ear}

Facts used (checked {date}):
- {claim} -> {source}
Media and credits: {file, source, licence, attribution card yes/no | "no third-party media"}
Known weak spots: {honest list, for example "small labels on a phone", "mix checked by measurement, not by ear"}

Want changes? Tell us the scene and the time (for example "scene 3, 0:12") and we will rebuild only what changes.
```
