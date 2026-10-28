# S-g17-manim-derivative · Dark-ink math explainer with think pauses
**Source:** @LinearUncle, https://x.com/LinearUncle/status/2103128559174971663 · our build: g17-manim-derivative
**Use when:** "teach {math concept} with graphs", "Manim-style explainer", "make people think", "easy to understand with examples", "narrated lesson"
**Defaults:** 225 s in the original (we recommend 60 to 120 s for chat, 3 to 5 sections) · 16:9 1920x1080 · 30 fps · narrated with burned-in captions and a quiet music bed
**Kit:** `kits/g17-manim-derivative/` holds working code from the 2026-10-28 sample of this style (60 s, reviewed PASS); start from its README.

## The brief (reusable prompt)
Make a video that teaches the concept of {concept} using animated graphs. It should be easy to understand, have examples and make people think. Add a voice-over.

## Scene plan
Eleven scenes cued to narration word times (the original gave no per-scene start times, so schedule from your real voice durations).
| Order | Beat | What happens on screen |
|---|---|---|
| 1 | Hook | Speedometer reads 60 km/h but in one frozen instant the car moves 0 km in 0 h: what is 60 measuring? Pause to think, then title |
| 2 | Average speed | Distance-time graph, slope of the secant |
| 3 | Shrink h | Live readout of h and secant slope converging (0.62 to 1.160); secant becomes tangent |
| 4 | Definition | Limit definition with rise (coral) and run (blue) colour-coded, mini graph |
| 5 | Worked example | f(x) = x^2: expand, cancel, divide, h to 0, f'(x) = 2x |
| 6 | Check on graph | Tangents at x = 1, 2, -1 (slopes 2, 4, -2) plot points; sweep traces 2x |
| 7 | Think pause | "Where is the slope exactly zero?" (2.4 s ring), then x^3 - 3x hill and valley |
| 8 | Sine | "Make a guess" pause, slope at 0, pi/2, pi, 3pi/2 traces cos |
| 9 | Local linearity | Zoom x1 to x1000, curve becomes its tangent line |
| 10 | Counter-example | |x| at x1000 stays a corner; slopes -1 and +1; no single tangent |
| 11 | Close | position to velocity to acceleration; open question (3.2 s pause) then end card |

## Look
- Palette: background #0D1117, ink #E8ECF3, muted #7D8597, grid #2A3140, blue #58C4DD (the function and the run), coral #FF7A59 (secant and rise), gold #FFD166 (tangent, the derivative moment), green #7EE081 (derivative graph), violet #B39DFF. One colour per role held across all scenes, so viewers learn the code once.
- Type: STIX Two Text for formulas (italic variables, Unicode primes, Delta, pi), Avenir Next for UI text. Both are Mac system fonts. Fractions and limit blocks built by hand.
- Layout and texture: dark canvas, thin grid, readouts that never cover the curve, caption strip at the bottom.

## Motion
Every animation is cued to a spoken word and run-times are whole frames. Secant to tangent: animate h from large to small with ease_in_out_cubic while a live readout updates. Zoom scenes are drawn analytically each frame (re-sample the curve in the visible window, cross-fade grid levels per decade) instead of scaling a bitmap, so x1000 stays exact. Think pauses: 2 to 3.2 s of silence with a filling ring before the answer.

## Audio
Voice: calm male (original en-US-AndrewMultilingualNeural, rate -4%); here use a text-to-speech voice (`voice.md`). Music: ambient bed in D major at 66 BPM (detuned pad, sub root, sparse bell arpeggio, convolution reverb), sidechain-ducked under the voice. Two-pass loudnorm to -14 LUFS, true peak -1.5 dBTP target (original -14.1 LUFS, -1.2 dBTP).

## Build notes
No LaTeX or Manim in the engine: draw graphs in PIL by sampling the function (numpy) to a polyline, with 2x supersampling. Formulas as text in STIX Two Text (check it exists in /System/Library/Fonts or /Library/Fonts, else a serif italic). Compute every number shown (slopes, readouts) from code, not by hand. Generate narration per line, measure durations, then lay out the scenes and the SCHEDULE from them; assert that each scene ends on its audio length. Burn captions in PIL. A 60 to 120 s cut keeping hook, secant to tangent, one worked example, one think pause and the close is realistic.

## Pitfalls (from what went wrong in our build)
- 0.3 to 0.4 s of empty frame at the start of each scene read as a cut to black; start the first cue at once or design a transition.
- Captions drawn inside the animation engine doubled up (stale cache); draw captions as a separate post pass.
- A readout covering the parabola, a speedometer needle hiding the "60" tick, a "-0.00" readout, and a flat ending that looked like f'(0) = 0: review stills for all of these.
- Mini graph labels were about 15 px; keep them readable.
- Pronunciation ("f prime of x") and music balance were checked only by numbers, not by ear.

## Style QA
- All maths is correct (for example d/dx x^2 = 2x, (sin x)' = cos x, |x| has no derivative at 0) and numbers come from code.
- Same colour means the same role in every scene.
- Each think pause is silent and long enough (2 to 3.2 s) before the answer appears.
