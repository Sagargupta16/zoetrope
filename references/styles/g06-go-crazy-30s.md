# S-g06-go-crazy-30s · Sound-as-picture motion showcase
**Source:** @macrohou, https://x.com/macrohou/status/2103545787875733862 · our build: g06-go-crazy-30s
**Use when:** "go crazy", "show off motion and sound design", "dynamic 30-second motion graphics", "app launch with a beat", "every sound has a visible cause"
**Defaults:** 30 s · 16:9 1920x1080 · 60 fps in the build (30 fps is the default; use 60 only if the machine renders fast enough) · music-only, no voice
**Spec:** family=music length=30 size=1920x1080 fps=30 audio=music kit=-

## The brief (reusable prompt)
Make a dynamic 30-second motion graphics video for {brand} that shows off your motion and sound design. Go crazy. Use only the brand folder (colours, font, logo, real feature list).

## Scene plan
Grid: 120 BPM (beat 0.5 s). One mascot dot (from the logo) is the count-in ball, playhead, cursor, calendar hopper and toggle knob.
| Time | Beat | What happens on screen |
|---|---|---|
| 0-2 | Count-in | Dot bounces 1-2-3-4 with squash/stretch, numerals pop, floor ripples; dot flies at camera and fills the frame (impact at 2.000 s) |
| 2-8 | Timer as step sequencer | 3D-tilting timer ring; dot orbits once per bar past 3 concentric step rings that light when hit; ring 2 joins at 4 s, ring 3 at 6 s; 25:00 counts down as time-lapse, flips to BREAK 05:00 |
| 8-14 | Task list as pads | Ring shrinks into first card checkbox (match cut); cards drop in, drag, 4-card swap, two check-offs with confetti; moon arcs over, night tint, unfinished cards flip to "carried over" |
| 13.5-20 | Streak calendar as melody | 4 cards slice into 7 tiles each and become a 28-day calendar (match cut); dot hops days in date order on 16th notes; focus days flip mint, streak days solid mint, rest days stay dim; streak wave at 18 s |
| 19.5-24 | Other apps as noise | Notification pill crashes in (impact at 19.75 s), tiles scatter; 72 generic notification pills at accelerating rate, kinetic "ping / buzz / ding" slams, RGB split, glitch bars, screen shake, badge counter; toggle rises out of the chaos |
| 24-26 | Quiet mode hush | At 24.000 s the knob lands and the whole mix is hard-muted on that frame, reverb tails included; calm wave turns each pill to dust; "other apps wait while you focus"; cream iris from the knob |
| 26-30 | Lockup | Dot drops into the logo doorway with three settling bounces (impact at 27.000 s); tile pops, wordmark letters rise one by one, tagline, slow push-in; final tick echoes the count-in with a small wink-hop |
A small HUD labels each section (for example "02 · focus timer") so the sound-to-feature mapping reads on first view.

## Look
- Palette: coral #FF6B4A, plum #2B1B3F (ink), cream #FFF6EC (background), mint #6FD6B5, lilac #CFC4F2. Other-app icons use deliberately off-brand saturated colours (the build used #4A7BFF, #FFC94A, #FF4D8D, #7A62C9, #2E9C7B) so the noise reads as "not {brand}". Replace with the user's own brand colours.
- Type: the brand's rounded sans (build used Nunito, SIL OFL). On a Mac use the closest installed rounded sans (for example Arial Rounded MT Bold in /System/Library/Fonts or /Library/Fonts) if Nunito is not present. HUD labels 24 px.
- Layout and texture: cream and plum fields, hard cuts between them (a crossfade looked muddy grey), notification pills with generic copy ("New message", "Battery low", "Sale ends soon"), no real brands.

## Motion
Every sound has a visible cause. Squash/stretch bounces on the count-in; the dot orbits the ring once per bar; cards drop with ease_out_back; drag, swap and check-off are single quick moves; the calendar dot hops one day per 16th note; pills spawn at an accelerating rate with a shake and glitch. The mute at 24 s is a hard cut, not a fade. Match cuts: ring into checkbox, cards into calendar tiles, knob into iris. Keep every function of t only: spawn times, positions and pitches come from one schedule built with a seeded random.

## Audio
120 BPM, F major pentatonic. Count-in: marimba F-A-C-F plus woodblock, whoosh, impact as the colour fills the frame. Rings: ticks, then kick (ring thumps), then clap. One blip per minute change in the countdown, chime on BREAK. Card drops are ascending marimba; drag is a 13-note marimba glissando; swaps are tik-tok pairs; check is clap plus bright chord. Calendar plays the melody: each focus day is a kalimba note pitched by weekday, rest days are literal rests (a tiny tap), streak days add a bell octave. Noise section: each pill gets its own ping/ding/buzz at a dissonant pitch panned to where it appears, riser, bit-crushed drums. Hush: toggle click, then a soft pad and three music-box notes. Lockup: Fmaj9 resolve, 6-note kalimba run for the wordmark letters. Master about -14 LUFS (build measured -14.1 LUFS, true peak -2.4 dBTP).

## Build notes
Write one SCHEDULE (hop times, pill spawn times and pitches) and feed both the numpy score and the PIL draw(t). Use numpy for all sounds (sine/FM for marimba and e-piano, filtered noise for whooshes, short decaying sines for kalimba). Fake the 3D-tilting ring by scaling the ellipse's vertical axis and skewing text. Draw pills, glitch bars and RGB split as per-frame channel offsets. Hard-mute by zeroing the mix buffer from the exact sample of 24.000 s. Only real features may appear; no invented metrics.

## Pitfalls (from what went wrong in our build)
- The mix was balanced by meters, not by ear; the chaos section was denser but not louder than the groove. Push the noise section harder with a final listening pass if the user can listen.
- Busy 1-2 frame transitions look messy as stills (cards overlapping mid-drop, the reorder, the mute frame); judge them at speed, not as stills.
- Sections are 4-6 s and HUD and pill text is small, so some details need a second watch; keep key text larger.
- The cursor dot was hidden behind the cards and the strike-through ran past the titles: check layer order and clip text masks.
- Crossfading plum and cream looked muddy grey: use a hard cut on a hit.
- Cream-on-coral badge numerals measured 2.6:1 contrast (below 3:1); use plum on coral if contrast matters.
- Timer ring tilted in 3D made the "25 min focus" line read at an angle; keep key labels flat.

## Style QA
- Every audible hit has a visible cause within one frame.
- The mute lands on the frame the knob lands (RMS should drop sharply there).
- Impacts measured in the final audio sit at 2.000, 19.75 and 27.000 s.
- Loudness near -14 LUFS, true peak at or below -1 dBTP.
