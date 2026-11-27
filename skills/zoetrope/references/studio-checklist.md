# Studio checklist

One line per rule of `studio.md` (beside this file), in the order a builder walks a film before review. The mark says who checks it: `[lint Lxx]` is a rule of `studio/lint.py`, `[check Cx]` is a question of `proof/checklist.md` answered per generated still, `[qa Pxx]`, `[qa Fxx]` and `[qa Vxx]` are rows of `studio/qa.py`, and `[look]` is only a person's judgement. Apply every line to every shot, not to the shots a review named. Done means `studio.py check <build> all` exits 0 (every stage prints `check <stage>: exit 0`; a FIX row the owner named in `accept.json` is printed as accepted and does not count) and every `[look]` line has been looked at on the sheets.

## 1. Before the shot list: brief, facts and script

- [look] Every number, name and date has two sources in `facts.md`, with the sources' qualifiers kept; a computed figure is labelled as ours or left out.
- [look] The film is about 95 to 118 s (the speech ends between 92 and 115 s, then a 3 s end card), 285 to 315 spoken words, and the last line answers the first.
- [qa P01] The film runs 60 to 179 s.
- [qa P05] The spoken hook is over by 3 s; the first six seconds say what the thing is.
- [qa P09] Speech covers 88% or more of the narrated stretch; a breath of 0.45 to 0.6 s only before a turn.
- [look] A fresh reason to stay about every 15 to 20 s; the payoff at 70 to 85% of the runtime, marked `PAYOFF` in the script table.
- [look] A late payoff is promised early on screen, and the stretch before it carries a lower third from its first frame.
- [look] The film's question and its answer are title size, not list size.
- [look] No em or en dashes, no emoji, no greeting, no "did you know".

## 2. The shot list (`shots.py`), then `studio.py build`

Run `build` again after any change to `shots.py`, `shots.json`, `script.json`, `graphics.js` or a picture: every check, `render`, `table`, `sheet --times` and `package` refuse (exit 3) while `timeline.json` is older than one of them. A failed build leaves no timeline.

- [qa P02] The median shot is near 2.2 s (a FIX over 2.9 s); no shot over 4 s unless marked `long`.
- [lint L08] The picture changes three times in the first 3.5 s.
- [qa P04] The hook stands on frame 0 with no cue, six words or fewer.
- [qa P06] Something new on the picture layer at least every 3 s.
- [lint L09] At most three whips or zooms in a film, never two in a row.
- [look] Every cut, overlay and reveal is cued to a word; a hard cut lands 0.08 s before a stressed word.
- [look] Six or more kinds of picture in the film; a clip on frame 0; stills always on a camera move.
- [look] One palette per film (the look line ends every still prompt); `grade` is none, `soft` under a dense overlay, `dim` or `blur` only under a full-screen device or the end card.
- [look] Clips: 8 to 14 where the story moves, at most two in a chain, 4 s at 30 fps (qa P13 notes fewer than 4 a minute, not counting `exempt` shots).
- [qa P12] A drawing or a type card never stands on a bare plate for more than 10 s in a row: drawings go over a blurred, slowly drifting picture.
- [look] A picture in the clear comes between two drawn stretches (P12 does not measure it).
- [look] A drawing fills the band between the top rows and the captions (about 900 px wide or 450 px tall); it is never a small figure on an empty frame.
- [lint L02] No picture is in the clear more than twice in a film, and after the payoff every shot is a new picture or a device.
- [lint L14] One still never carries two dates or two places.
- [lint L01] A date chip stands only on a picture in the `past` grade with nothing of today in it.
- [lint L17] A real name, a specific day, a document or a recorded event is never a chip on a photoreal picture: type on a blurred plate, our own drawing, or the source line. Declare a chip's real name with `real()`.
- [lint L18] A redrawn document stands on the stage's plain plate (`ground`), never on a generated picture.
- [lint L19] A film's own device in `graphics.js` never takes the name of a built-in overlay type (`stamp`, `number`, `end` and the rest): an overlay of that type is drawn by the kit's own.
- [look] A data device with no honest picture goes on a blurred plate with a still camera.

## 3. Words and devices (the static lint)

- [lint L03] Words on screen never repeat the caption's words in the same frame; a device that speaks the line takes `says: true`.
- [lint L04] Every stamp is in the accent.
- [lint L05] A list sits on a dark plate, and each outcome turns to the accent as it lands.
- [lint L06] A source line on a generated picture says what it is, with the source's year.
- [lint L07] A number is never on screen before its spoken word: a `number` has `landAt`, a `rail` or `years` has `until`, within 0.1 s of the word.
- [lint L10] The top row (y 282 to 345) holds one chip on the left and the tag, when the batch sets one, on the right: 30 characters or fewer in the chip (not linted when the tag is empty).
- [lint L11] A row of a word card stands lit 2 s or more after it lights (a `stepsrow`'s `steps` count like `rows`).
- [lint L15] A lower third is five words or fewer on one line.
- [lint L16] A present-day claim on a chip carries its year.
- [qa P07] A text overlay stands its reading hold: 0.5 s plus 0.3 s per word, at most 4 s; the same words carried over a cut count as one hold only while it is unbroken.
- [look] What stands on both sides of a cut (a drawing, a plate, a rail, a label, a stamp, a number) stands in the same place and at the same size on both, or moves there in one visible move; an overlay that goes on from the shot before is set `standing: true`.
- [look] Hero text is five words or fewer; one hero element per shot.
- [look] A date chip is yellow, a label chip dark; the words that mark one part of a row mark it in every row.
- [look] A source line names only what it sources, and keeps the source's qualifier on screen (TENDS TO RUST, not RUSTS).
- [look] A word card prints every word dim from its first frame; no card opens on an empty plate.
- [look] A device drawn to scale names its scale and whose arithmetic it is, once per picture.
- [look] A demonstration that could pass for a test of the body says on screen that it is not one; no line promises an outcome.
- [look] While the viewer watches one mark, nothing else appears, moves or leaves, and the accent belongs to that mark alone.
- [look] Maps that touch India follow the Survey of India depiction.

## 4. Every generated still (`proof/checklist.md`, answered in `proof/checklist_answers.json`)

Open each frame the checklist names at full size with the captions on, corners and bottom included, and answer each item per still. A missing or failed answer, or an answer older than its still (the still was remade after it was answered), is a FIX in `check stills`. `build` and `check frames` rewrite `proof/checklist.md`, so it names a frame for every use.

- [check C1] The wrong object: is it the thing the film names, checked end to end against `still.check` and the real thing?
- [check C2] Later than the date: nothing in the frame is later than the date it stands under (fenders, buoys, rivets, machine stitching, milled coins, wires, modern dress).
- [check C3] Built against grown: nothing contradicts the line over it (planks and posts on a thing said to be grown).
- [check C4] The subject under y 1074: what the shot is about sits in the band y 400 to 1000, nothing at or under the captions.
- [check C5] A face, lettering or a badge: no identifiable face, readable invented text, logo, flag or badge.
- [check C6] A picture that says more than the words: it does not claim more than the line under it.
- [look] Reseed or reprompt a still that fails; after two reseeds change the prompt or the device, not the seed.

## 5. Plan check, then frames

- [qa P03] Three picture changes before 3.5 s (the plan check's own count).
- [qa P11] The last shot is an end card of 2.5 s or more over the opening picture.
- Shoot the frames with `studio.py check <build> frames`, then run `studio.py check <build> lint-frames`. A count needs frames at its own moments: `check frames` shoots 0.1 s before and after every count's landing (a `number`'s `landAt`, the `until` of a `rail` or `years`) by itself, and L07's fix line is `python studio/studio.py check <build> frames`. Frames shot before the last `build` count as missing: `check lint-frames` gives `NOT CHECKED L00` (exit 2) until `check frames` runs again.
- [qa F01] Every text box is inside x 60 to 1020, y 270 to 1252.
- [qa F02] No text under 32 px.
- [qa F03] No two text boxes overlap.
- [qa F05] Under 60% of a frame near black.
- [qa F06] Frame 0 is lit and has the hook on it.
- [qa F07] Text boxes cover under 45% of a frame.
- [lint L07] On the frames, a count shows its last value only from its word on.
- [lint L10] On the frames, a chip in the top row ends 16 px or more before the tag, where the film has one.
- [lint L12] A drawn diagram or plate has a mean brightness of 60 of 255 or more.
- [lint L13] A caption page never drops the NOT of its sentence; the negator opens its page.
- [look] Open every `proof/sheet_NN.png` at phone size: text does not fight the picture (F04 notes it), every label reads.

## 6. The file

- [qa V01] Loudness -14 LUFS within 1, true peak at or under -1 dBTP, no flash sequence, no black frame.
- [qa V01] The frames are evenly timed: the file's average frame rate is exactly 30/1 (`package` refuses a file that is not).
- [qa V02] The file is under 95 MB.
- [qa V03] The picture changes at least every 3 s on the file itself.
- [look] Watch it once with the sound off and once with it on, as a first-time viewer.
- [look] Before `package`: `studio.py look <build>` and open every sheet of `proof/look/` (a frame every 1.25 s of the file). Every reader saying READY is not the bar; `package` refuses a film nobody looked at since its last render.

## 7. The text under the film (`post.json`)

- [look] The first line is one sentence under 125 characters that does not give the payoff away.
- [look] The second paragraph says the pictures are illustrations, not photographs of the real things or places, and that diagrams and cards are drawn or redrawn by us.
- [look] The AI disclosure follows the batch: `tag` or `end.ai_line` set, that paragraph also says pictures and voice are AI-generated and the alt text that the pictures are; both empty, nothing in the caption, the alt text or the hashtags says that the pictures or the voice are AI-made.
- [look] A negative is written as what we found; a one-source figure says so.
- [look] Sources are named by kind and every url is one `facts.md` cites.
- [look] `cover_ms` lands where the hook has settled and no caption page is up.
- [look] No link in the caption, no stray non-breaking space or zero-width character.

## 8. After a review

- [look] Apply every finding to every shot, not only the named one; put each fix in its own dated `@plan.block` and re-review the shots `proof/blocks.md` lists.
- [look] Run `studio.py check <build> all` again; a rule that came out of the review is now on this list for every later film.
