# Kit: S-g11-movie-credits (Salt and Signal opening credits)

From the 2026-10-28 sample: 60 s, 1920x1080 with a 2.39:1 letterbox, 24 fps, D minor at 60 BPM, a film about a lighthouse with made-up names. Proof 42 min; render about 115 s for 1440 frames on 6 processes; 35.9 MB; final review PASS.

| File | What to reuse |
|---|---|
| `scenes.py` | Dusk sea and lighthouse; a beam clock that sweeps once per bar and reveals names only where it passes, with an afterglow; a Fresnel lens assembled from rings for the title; a lamp-room crew section where a band of lamp light reveals each credit in two alternating slots; soft grain, exposure flicker and whole-pixel gate weave; `HIT_LEAD` moves motion 1/48 s early so it lands on the beat frame. |
| `score.py` | The score from the same beam clock: open-fifth drone, sea wash, sparse piano, low strings, shimmer per beam pass, riser and foghorn on the title downbeat, D major resolve. |
| `grain_test.py` | Measures file size per grain setting on a 4 s slice. Its estimate for grain std 2.6 was 138 MB for the film (the real master was 140.2 MB); std 1.6 with CRF 20 gave 35.9 MB. Run it before rendering any grainy style. |
| `engine_used.py` | Its font lists (Palatino Linotype for names, Palatino Linotype Italic for role words). |

Lessons from its reviews: a dusk sky instead of black keeps frame 0 above the first-frame gate even with letterbox bars; keep small lamps fully inside the picture (one sat behind the bar); a 2 s credit slot cannot hold a 5-word credit, so credits stay about 3.2 s in two slots.
