# S-g12-beat-sync-spec · Minimal beat-locked product spot
**Source:** @twoclipping, https://x.com/twoclipping/status/2102554209166000267 · our build: g12-beat-sync-spec
**Use when:** "beat-synced product ad", "high-end minimal promo", "10 bars at 120 BPM", "drop opens into the product", "cuts on the downbeat"
**Defaults:** 20 s · 16:9 1920x1080 · 60 fps in the build (30 fps here) · music-only

## The brief (reusable prompt)
High-end minimal spot for {product}: one idea per shot, lots of empty space, one accent colour, one clean sans with tight tracking, masked type reveals, match cuts, one smooth camera language. Real footage only (the user's own clips), never placeholder cards. No full stops in on-screen text. Banned: shockwave rings, particle bursts, RGB split, camera shake, lens flares, neon glows, grid floors, flashing backgrounds, bouncy easing. Structure: 10 bars at 120 BPM, 2 s each. Every cut on a downbeat, every UI hit on a beat. Show a storyboard with every timing on the beat grid before building. Ask for: product name and one-line promise, 3 to 5 UI moments, one accent colour, 10 to 20 clips the user owns, and a song with a clear drop (or synthesize one).

## Scene plan
Bar n starts at (n-1)*2 s; beat = 0.5 s.
| Time | Beat | What happens on screen |
|---|---|---|
| 0.00-1.50 | Hook (bar 1) | Cream background; hook words land one per beat, masked rise out of a line: "One" 0.0, "small" 0.5, "nook" 1.0; "nook" turns accent colour with a left-to-right wipe at 1.5 |
| 2.00-3.50 | Morph to UI (bar 2) | Other words mask out; the measured box of the key word morphs into the product card (match cut); cursor glides in and types (typing ends 3.31); click on button at 3.50, label turns "Starting" |
| 4.00-5.50 | The drop (bar 3) | Circle opens out of the button centre into a dark scene: 4x3 wall of real vertical clips; accent scan line sweeps left to right (4.25-5.75); winners framed at 4.5, 5.0, 5.5 |
| 6.00-7.50 | Key output (bar 4) | Big type "25 quiet" / "minutes" (6.5); accent rule wipes under the key word (7.0); type slides up out of its mask (7.5) |
| 8.00-9.80 | Carousel (bar 5) | 3D carousel of 8 real clips with floor reflections, slow orbit; motion-blurred whip at 9.5, lands on hero clip at 10.00 |
| 10.00-11.50 | Phone and panel (bar 6) | Hero rect shrinks into a phone screen (match cut); session panel slides in at 10.5; panel flips (rotateY, wrapper fades only) to results at 11.0; rows tick in at 11.5 |
| 12.00-13.50 | Stats (bar 7) | Push cuts every beat: "25" min focus, "5" min break, "0" pings, "1" nook, over a dimmed real clip |
| 14.00-15.50 | Ticker (bar 8) | 3-word slot ticks "Plan", "Focus", "Finish", then collapses to an accent bar |
| 16.00-18.00 | Logo (bar 9) | Bar morphs into the logo mark; wordmark reveals at 16.5; tagline at 17.0 |
| 18.00-20.00 | Tail (bar 10) | Hold with credit line; fade to black, black by 19.75 |

## Look
- Palette: cream #FFF6EC with plum ink #2B1B3F for bars 1-2; near-black #0E0B12 after the drop; one accent coral #FF6B4A. Streak chip goes mint (mint #6FD6B5 from the brand palette).
- Type: Inter variable, display tracking -0.045em. Mac substitute: SF Pro or Helvetica Neue from /System/Library/Fonts with the same tight tracking.
- Layout and texture: lots of empty space; vertical clips cropped to 9:16; floor reflections under the carousel; camera language is one slow push-in (scale 1.00 to 1.04 per shot), every entry moves upward or leftward.

## Motion
Easing: expo or quint out for entries, cubic in-out for travel; no bounce, no overshoot. Masked reveals: text rises from below a clip rectangle. Match cuts: measure the box of the outgoing element at draw time and interpolate its rect into the incoming one. Circle wipe: radius from 0 to full over the drop bar, centred on the button. The whip is a horizontal blur plus fast ease. Rotated panel: fade the wrapper, never the 3D element itself. Everything is a function of t.

## Audio
120 BPM 4/4, 10 bars. Bars 1-2 intro: soft pluck on every beat (octave up on the colour wipe), no kick, filtered pad, riser in bar 2, beat 4 of bar 2 pulls back to a gap so the click reads. Typing = key ticks on 32nds. Drop at 4.0: kick, sub, chord. Bars 3-8 full groove: kick 4/4, clap on 2 and 4, sub, offbeat hats. Whoosh with its measured peak at 9.80. Flip swish at 11.0, ticks on result rows. Bar 9: groove stops, final chord plus low hit at 16.0. Bar 10 reverb tail to silence by 20.0. Place each SFX so its measured peak, not its file start, lands on the event. Keep SFX quiet under the music. Master -14 LUFS (build measured -14.0).

## Build notes
Generate the track in numpy with the drop at bar 3, then run beat analysis on it and calibrate the grid to the kick peaks; write the grid to a small dict used by draw(t). The build used 14 licensed real clips (Wikimedia Commons, CC0/CC BY/CC BY-SA/CC BY 3.0) with a CREDITS file. We must use the user's own clips (extract frames with ffmpeg on the device, if present) or generated stills; it must not download footage it cannot license, and it must list credits for anything with an attribution licence. Motion blur: render 3 sub-frames around t (minus, at, plus 1/240 s) and average. 3D carousel: fake with scaled and offset clip frames sorted by depth plus a flipped, faded copy for the reflection.

## Pitfalls (from what went wrong in our build)
- The build session dropped before its own final QA; always run the check step yourself (duration, fps, loudness, contact sheet).
- No sound-on review by a person happened; ask the user to listen before sign-off.
- Never set opacity or a filter on a preserve-3d element (it flattens and both faces show); fade its wrapper.
- Measure element positions at runtime for match cuts instead of hard-coding them.
- Only use music and SFX whose licence allows commercial use; synthesised audio avoids the issue.
- Stay inside the ban list (no shake, glow, bounce): it is easy to add them by habit.

## Style QA
- Every cut is on a downbeat (multiples of 2 s) and every UI hit on a 0.5 s beat.
- On-screen text has no full stops.
- Only one accent colour appears.
- Footage credit line shown on the tail and loudness near -14 LUFS.
