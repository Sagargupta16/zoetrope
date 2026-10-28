# Delivery report template

Keep the message short and in this order. Fill every field from a real tool result; write "not checked" when we did not run a gate.

```
Your video is ready: {title}

File: {full path}   (also shown in the side tab)
Length: {mm:ss} | Size: {resolution} at {fps} fps | Codec: {video codec} + {audio codec} | File size: {MB}
Encode rung used: {a: H.264 MP4 on your device / b: AV1 MP4 or VP9 WebM from the sandbox / c: GIF preview}
Why this rung: {for example "ffmpeg was found on your Mac" or "no ffmpeg on your device, so we encoded in the sandbox"}
Plays in: {what we know, for example "Chrome and Slack web; older QuickTime may not play AV1/VP9"}
Extra files: {GIF preview for Slack, poster PNG, 720p cut, none}

What is in it: {one line per scene, with start time}
Audio: {music synthesized by us | music supplied by you | voice: {voice name}} | Loudness {x} LUFS, true peak {y} dBTP

QA run:
- Frames checked: {n} stills (scene boundaries and midpoints), contact sheet shown
- Text inside safe area, no overlaps: {pass / list}
- Contrast (4.5:1 body text): {pass / list with values}
- Reading holds: {shortest hold and its scene}
- First frame not blank: {pass / fix}
- Flash check (3 per second at most): {pass / passages that need care}
- Audio and video sync at hits: {within n ms / list}
- Not checked: {anything skipped, and listening by ear}

Facts used (checked {date}):
- {claim} -> {source} 
Media and credits: {file, source, licence, attribution card yes/no | "no third-party media"}
Known weak spots: {honest list, for example "small labels on a phone", "mix checked by measurement, not by ear"}

Want changes? Tell us the scene and the time (for example "scene 3, 0:12") and we will rebuild only what changes.
```
