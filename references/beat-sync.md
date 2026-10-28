# Beat sync

1. One grid: `t(bar, beat) = T0 + ((bar-1)*4 + (beat-1)) * B`. For our own synthesized music T0 is 0 and B is exact; every cut, scene start and SFX reads this function.
2. Cuts on beats: scene boundaries on beats (strong cuts on bar lines, small changes on beats 2 to 4). Hard cut times are `schedule` values, not hand-typed.
3. Drop on a bar line: the big visual change (logo, price, end card) lands on the first beat of a bar, with the riser filling the bar before. In a past build the last-bar-before-drop was the riser bar and the drop was the next bar.
4. SFX by measured peak: for each SFX, find its own peak (1 ms moving average of `abs(x)`, then `argmax`), and start it at `event_time - peak_offset`, so the loudest instant hits the event, not the file start. Whoosh peaks at the maximum speed of the move; chimes land on the beat after the dot lands (half a beat later in the past build).
   `synth.put_peak(bus, sfx, event_t)` does this placement.
5. SFX level: SFX sit well under music (past builds used about -17 to -31 dB per hit relative to full scale, tick -28 to -31, whoosh -18). Pan ticks slightly left or right (about +/-0.2).
6. Check kick alignment (if music was not made by us, or to prove ours): low-pass the music (35 to 140 Hz band), take the envelope, mark each kick onset as the first upward crossing of 25 percent of the maximum with a 300 ms refractory window (sub bass can enter about 45 ms after a kick and would otherwise be counted). Fit `t = t0 + n*period` to the onsets within 40 ms of the grid by least squares. Pass if the largest residual is only a few milliseconds and the fitted BPM matches the preset. Autocorrelation tempo can come out as half or double: fold into 90 to 180 BPM.
7. Frame check: convert each cut time to a frame (`round(t*fps)`) and confirm in the contact sheet that the frame at the cut shows the new scene and the frame before shows the old one.
8. Voice vs. beat: words that carry a cue (price, "now", brand name) have measured onsets in the voice file (find them with ASR if available, otherwise by RMS onset); convert each to video time with `t0 + (onset - trim) / TEMPO` and cue the visual to that time.
