# Hooks and retention for Reels and Shorts

What keeps a viewer past the first seconds of a vertical video: the two hooks (the line the voice says first and the line frame 0 shows), the screen every hook passes before the storyboard, and the beat shape that holds the viewer after it. Read it at Workflow step 4 for any Reel, Short or TikTok, beside the chosen card. On a new fact account's first 14 Reels (made by an earlier generator, read 2026-10-24), 80.4 percent of viewers left within 3 s (view-weighted over 1,058 views) and the median average watch was 3.06 s, so whatever came after the third second reached about a fifth of the viewers.

## Two hooks at once

- **The spoken hook** is narration line L01: the surprise in about eight words, its speech over by 3.0 s, the moment a platform's skip rate counts to. Our 16 narrated Reels (the batches of 2026-11-10, 2026-11-15 and 2026-11-16, all Kokoro af_heart at speed 1.0, measured 2026-11-20 from each `narration.json`) read their hook lines at a median 3.2 words a second (2.7 to 4.1) after the slot's 0.35 s lead, so eight words end near 2.9 s. Only 4 of the 16 ended by 3.0 s (median 3.9 s); the six deep dives took 11 to 21 words and ended at 3.7 to 6.9 s.
- **The on-screen hook** is the headline on frame 0: six words or fewer, the blunt version of the spoken line, readable with the sound off in about a second and drawn in full on frame 0 (`playbook.md` section 3, the 1.5 s rule in SKILL.md). It sits above the caption band, in the middle of the frame (`formats.md`: platforms draw over the bottom and the right edge). A card that captions every spoken line still captions L01 (`voice.md`); the headline is the bigger, shorter line above it.
- **The picture** is the subject itself on frame 0, never a title card or a logo, and something on it moves by 0.5 s.

Q501 checks only that frame 0 is not dark or flat; no gate reads what it says. The screen below and a look at the proof sheet do.

## Write three, from three formulas

Before the storyboard, write three candidates from three different formulas, not three wordings of one. The shapes below are 13 of the source's 26 formulas (`hooks.json`, number in the last column), reworked for third-person fact Reels. Every slot in braces is filled from the scenario's facts list, two sources each (house rule 3), never from memory. The source's first-person creator formulas (a cost confession, a receipt, years inside an industry) fit a product or personal piece only with numbers the user gives (house rule 2).

| Formula | Spoken shape | On screen | Fits | The trap | # |
|---|---|---|---|---|---|
| Wrong picture | "Your map makes {Greenland} {as big as Africa}." | {GREENLAND IS NOT THAT BIG} | myths about something everyone has seen | a myth nobody holds; the stake line says why the picture misleads, so the viewer is not the one who is wrong | 7 |
| The flip | a belief people repeat, turned round and true as stated | the same words | sayings people quote | a pun instead of a fact; a saying nobody uses | 22 |
| Head to head | "{A} or {B}: one is {N times} {bigger}." | {A} VS {B} | sizes, ages, speeds | an ending that does not pick; draw the two to scale (`image-plates.md` rule 3) | 17 |
| The superlative | "The {biggest desert} is not {the Sahara}." | THE {BIGGEST} {THING} | one claim, no story | a record that moved or is disputed: keep the source's own qualifier ("often called", "about") and date a record that can change | 26 |
| The statistic | "{Nine in ten} {of something} {surprising fact}." | {9 IN 10} {...} | a figure people repeat | the figure the payoff counts up to: keep that one for the payoff | 23 |
| Then and now | "In {year}, {it} took {long}. Now it takes {short}." | {3 MONTHS} TO {9 HOURS} | change over time | a change that sounds false (name the source on screen); generated plates as the evidence: an AI picture illustrates, so draw the change as a SIMPLIFIED map or chart from the sourced numbers | 5, 13 |
| A list with a favourite | "{Five} {places} {where X}. The {fourth} is {in India}." | {5} {PLACES}. THE {4TH} IS {X} | lists; naming one early gives a reason to stay past the third | more than about seven, or a bare count ("Five facts about Mars" is a lesson title) | 11 |
| Cold open | frame 0 already mid-action, and the voice names it: "Watch {Greenland} shrink {as it moves south}." | the action and a 2 to 4 word label | a process with a visible result | a result that takes long to arrive: cut to it, explain after | 18 |
| Mid-story | "That is when {the turn}." | {THE TURN} | history stories | the setup never comes: give it by about 8 s; no leading ellipsis (`voice.md`) | 21 |
| A named result | "{Named person} {did the surprising thing} in {checked time}." | {RESULT} IN {TIME} | people in history and science | an unnamed miracle: the name and two sources, or drop it; a real person's photo or likeness follows house rule 6 | 25 |
| The question | a question about a surprise that names the thing: "Why does {Greenland} look as big as {Africa}?" | the question, in six words | everyday confusions | a lesson title in question form ("How does HTTPS work?"): four explainers that announced a lesson lost a median 83 percent within 3 s (2026-10-24); answer part of it before the halfway mark | 16 |
| A real date | "In {year}, {checked event}." | {DATE}: {EVENT} | real dated events (an eclipse, a rule that changes) | urgency that is not real; a spoken full date is long (the 2027 eclipse hook took 17 words and 5.6 s), so the full date goes on screen and the voice says the year | 19 |
| The cost | "{One small cause} cost {who} {checked amount}." | {CAUSE} COST {AMOUNT} | famous mistakes | a cost story that is a legend: two sources, or drop it | 1 |

## The hook screen

Every candidate passes every row before it goes into the storyboard. The screen is pass or fail on purpose, with no score out of 100. The source tested its own five-property score on 74 YouTube Shorts hooks: it told deliberately bad hooks from real ones well (AUC 0.83) but a creator's hits from the same creator's misses barely at all (AUC 0.56, where 0.50 is a coin flip), and only its concreteness check separated the two. The same author's YouTube scorer, run on 11 of the fact account's Reels with 20 or more views on 2026-10-24, ranked them against the share still watching at 3 s at Spearman +0.04 (recomputed 2026-11-20 from that run's files). So the screen keeps what catches bad hooks, adds the facts rule, and leaves the choice between good hooks to the picture and the account's own numbers.

| Check | Passes when | How |
|---|---|---|
| Facts | every number, name, place and date in both hook lines is a row of the facts list with two sources | the facts list; a hook that needs an invented figure, a deadline that is not real or more than the sources say is rewritten to the checked fact or dropped |
| Opener | none of the openers below | the first four words of both lines |
| Spoken time | L01's speech is over by 3.0 s | `lines[0].speech_end` in `narration/narration.json` after step 4's synthesis; before it, eight words or fewer. Cut words first; a hook a word over can take `{"id": "L01", "text": ..., "fit": 3.7}`, which speeds it up to 1.2x at most and raises with the words to cut when that is not enough (`voice.md`) |
| On screen | six words or fewer, drawn in full on frame 0, above the caption band | `qa.py holds` on the storyboard; `(0.0, "hook")` in `KEY_TIMES` asks `proof_keys.png` for frame 0 |
| Concrete | a checked name, place, date or number in the spoken hook | "a lot", "huge" and "so much" are not concrete, and neither is a line any fact page could post |
| Front | the surprise itself (what makes the fact worth watching) starts within the first four words | a setup clause first ("About six million years ago, ...") pushes it to word nine, even with a number at word two |
| Picture | the subject on frame 0, moving by 0.5 s | `(0.5, "first motion")` in `KEY_TIMES` beside the frame 0 entry |
| Payoff kept | the hook does not spend the answer or the figure the payoff reveals | three stat Reels whose caption's first line gave the figure away lost 87.5, 96 and 100 percent within 3 s (11 to 113 views each, 2026-10-24) |

Openers that fail (the source's dealbreakers and weak openers, plus our own measurement):

- a greeting, a name or a welcome;
- talk about the video: "in this video", "today we", "let me show you", "here is";
- a call for attention with nothing in it: "stop scrolling", "wait for it", "watch till the end" ("Watch Greenland shrink" carries its payload and passes);
- a preamble question: "did you know", "have you ever wondered";
- filler first: "so", "okay", "basically", "actually", "there is", "it is", "one of the";
- a lesson title or a bare count: "How DNS works", "Five facts about Mars";
- a series label: "Map myth number one" moved the fact's first word from 0.35 s to 1.74 to 1.89 s in the five map-myth Reels (the 2026-11-15 batch). Put the label on screen as a small kicker and open the voice on the fact;
- a hashtag, an emoji, a logo or a title card.

Picking among the hooks that pass:

1. The one frame 0 can show best: with the words removed, the picture still says it (the squint test, `playbook.md` section 1).
2. The one a viewer believes on first read. A true fact that sounds false names its source in the stake line or on screen.
3. Then the account's own numbers: the share still watching at 3 s, per formula, over five or more Reels. At about 100 viewers one Reel's skip rate is good to about 8.5 points either way (95 percent, binomial at 75 percent skip), so one Reel never settles it.

## The beat shape

| Beat | When | What it does |
|---|---|---|
| Hook | 0 to 3 s | both hooks and the subject; the voice starts at 0.35 s, the slot's lead |
| Stake | line 2, right after the hook | why it matters to the person watching, or what the hook left out: the setup, the qualifier, why the common picture is wrong |
| Body | line 3 to the payoff | one checked fact per line and one scene per line; a visible change at the card's pace (every 3 to 5 s on the deep dive), cued on its word (`voice.word_cue`); never three lines in a row without a name, place, date or number |
| First answer | before the halfway mark | pay part of the promise (a first figure, half the answer); the source pays all of it by then, we keep the card's biggest reveal for the payoff |
| Payoff | the last spoken line before the end card | answers the hook and repeats its key word, on the strongest picture with the biggest reveal, so the end of the story answers its start |
| End card | the last 3 s or more | one ask (follow, or the series line), held (the card) |

Measured on the same 16 Reels: Australia's payoff "Wider than the Moon." answered and echoed its hook, but four of the six deep dives ended on a side fact (seafloor mapping, a later collapse, a heritage listing, the Sun's age), and one had spent its answer in the hook: "... and its peak would still be more than two kilometers underwater" (21 words, over at 6.94 s).

Through the middle:

- One idea per Reel. A script with two surprises is two Reels.
- A list names its favourite early (the formula above).
- One clear change of pace and one held breath (`playbook.md` section 5).

## A rewrite, from our builds

The Mediterranean deep dive (2026-11-16) opened "About six million years ago, the Mediterranean Sea almost dried up.": 11 words, the surprise at word nine, speech over at 4.38 s. In the shape above:

- Spoken hook: "The Mediterranean Sea almost dried up." (6 words; about 2.2 s at the measured pace, an estimate until it is synthesized)
- On screen: THE SEA THAT ALMOST DRIED UP (the qualifier stays: the facts say almost)
- Line 2 takes the setup clause: "About six million years ago, ..."
- The payoff it already had, "... the buried salt shows the sea once mostly dried out.", echoes "dried".

## In the storyboard

Put the three candidates, their screen results and the pick above the storyboard table (step 5), and keep the pick in the scenario:

```
HOOKS
1 {formula}  spoken "{about 8 words}"  on screen {SIX WORDS OR FEWER}
  facts {F1, F2}  screen PASS (L01 over at {2.6} s)
2 {formula}  spoken "..."  on screen ...
  facts {F3}  screen FIX facts ({F3} has one source)
3 {formula}  spoken "..."  on screen ...
  facts {F1}  screen FIX spoken time (L01 over at {3.4} s)
PICK 1: {what frame 0 shows, and why this one}
```

## Not taken from the source

- The 0 to 100 score and its STRONG, OK and WEAK bands (the measurements above).
- Timing by word count at 165 words a minute: ours comes from `narration.json`.
- The 15 to 45 s working range: the card's length stands (deep dives run 60 to 90 s).
- Its safe box in pixels: `formats.md` sends the brief to the platform's current guide.
- Asking the user for a number or for three of their own videos: facts come from the research step, two sources each.
- The classifier regexes, the voice profile, the swipe file, the log, the humanizer and the caption step: account research and captions are not this skill's job.
- "Comment a keyword" as the closing ask: the end card's line is the one ask.

Sources (read 2026-11-20; ideas paraphrased in our words, no text copied): Jakeschincariol/instagram-agent-skill `skills/ig-reel/SKILL.md`, `hooks.json`, `hookscore.py`, `beats.py` and `README.md` (MIT, d03c56b); Jakeschincariol/youtube-agent-skill `skills/yt-script/hookscore.py` (MIT, a2feb21), only the scores it gave on 2026-10-24; our 16 narrated Reel builds of 2026-11-10 to 2026-11-16 (`narration.json`, measured 2026-11-20); the fact account's Reel insights of 2026-10-24.
