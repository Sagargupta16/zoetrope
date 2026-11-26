# {title} (script v1, {date})

Angle (three sentences): {what the film claims, what it shows, what it leaves the viewer with}.

Sent to: {who, and with what words}.

Promise: {the question the film opens, the line that opens it and the line that pays it}.

Screen hook (frame 0, six words or fewer): {HOOK WORDS}

Caption first line (one sentence under 125 characters, the surprise without the answer): {sentence}

Source keys: {F1 ... from facts.md}

## Script

The table is the script: one spoken line per row. `studio.py script <build>` reads the first table whose header has an `id` column, down to its last row, and ignores every other table (so a table of counts or notes goes after it, or has no `id` column). Keep the column names.

| id | beat | caption | spoken | facts | gap |
|---|---|---|---|---|---|
| L01 | hook | {what the viewer reads, digits for numbers} | {what the voice says, numbers as words} | F1 | |
| L02 | stake | | | | |
| L03 | stake | | | | |
| L04 | how | | | | |
| L05 | PAYOFF | | | | 0.5 |
| L06 | close | | | | |

Columns:

- `id`: L01, L02, ... in order.
- `beat`: hook, stake, how, why, proof, payoff, close, or your own short word. Write PAYOFF (capitals) on the
  one line that pays the film's question: it is the payoff marker, and after it every shot is a new picture
  or a device.
- `caption`: the words on screen. Digits for numbers and years.
- `spoken`: the words the voice reads. Numbers as words, never "point", names respelled only where a real read
  showed the voice gets them wrong. Same meaning as the caption.
- `facts`: fact ids from facts.md. Every number, name and date needs one.
- `gap`: seconds of silence after the line when it should differ from 0.2 (a breath before a turn 0.45 to 0.6,
  never more than 0.7). Empty means the default.

## Lexicon

A word the voice gets wrong in every line goes here, once: `studio.py script <build>` copies this table into
`script.json` as the lexicon, and the voice then says the word as the `say` column reads (the captions keep
the word as written). One word per row; add a row only after a real read showed the voice gets it wrong.
Leave the table empty when no word needs it.

| word | say |
|---|---|

## Size targets

- 27 to 32 lines; 285 to 315 spoken words; each line 18 words or fewer; one idea per line.
- Spoken hook eight words or fewer, its speech over by 3.0 s; the stake or the open question by line 3; the
  first complete fact by about 15 s; a fresh reason to stay every 15 to 20 s; the payoff at 70 to 85 percent
  of the runtime; the last line answers the first.
- The speech ends between 92 and 115 s and a 3 s end card follows, so the film runs 95 to 118 s.

## Re-hooks

- {line id}: {the fresh reason to stay}.

## On screen, not spoken

- {line id}: {the device or picture the line wants, in a few words, chosen from what the brief says is possible}.

## Counts and measured read

- Lines: {n}. Spoken words: {n}. Speech ends: {s}. Hook ends: {s}.

## Change log

- {date}: {what changed and why}.
