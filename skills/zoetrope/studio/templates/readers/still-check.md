# Reader: still check

Placeholders: `{film}` is the film's topic. Replace it before you start.

You check the generated still pictures of one film ({film}) before anything is rendered. You change no still
and no shot: you look, and you write answers.

## What you have

`proof/checklist.md` in the build folder: for each generated still its prompt, its `still.check` features,
every use with the line spoken over it and its chips, and one frame path per use with captions on. Open every
frame path at full size with your image-reading tool, corners and bottom too. A frame the file says is "not shot yet" is one you open from the
media folder instead, and say so in its note.

## The six items, for every still and every use

- C1 wrong object: the thing is not what the line names (two stalks on a chilli, the wrong leaf, the wrong
  animal). Check each `still.check` feature one by one.
- C2 later than the date: anything newer than a date chip in the frame (boat fenders, buoys, rivets, machine
  stitching, milled coins, wires, lit windows, plastic, modern dress, motor boats).
- C3 built against grown: the picture contradicts how the line says the thing was made (planks and posts on a
  bridge said to be roots).
- C4 low subject: the subject sits at or under y 1074, where captions stand, or under y 1250.
- C5 face, lettering or badge: an identifiable face, readable or garbled lettering, a logo, a flag, a badge.
- C6 says more than the words: the picture shows more than the line under it (a star close up under "over a
  light-year away").

## Return

Write `proof/checklist_answers.json`: a JSON list of `{"still": id, "item": "C1".."C6", "ok": true|false,
"frame": the frame path you looked at, "note": one line of what you see}`. Give one answer for every still
and every item; a missing answer counts as a fault. `ok: false` needs a note that names the fault and a
concrete fix (re-prompt with what, or restage as type on a plate or as a drawing). Then return the count of
`ok: false` answers and the list of stills they belong to.

## Severity

- P0: misleads, or puts a named real place, day, person, object, building or document on a photoreal
  generated picture.
- P1: breaks a written house rule in a way a viewer can see.
- P2: polish.

Mark `ok: false` for P0 and P1; mention P2 in a note only.
