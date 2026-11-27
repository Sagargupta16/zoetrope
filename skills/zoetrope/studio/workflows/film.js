export const meta = {
  name: 'film',
  description: 'Take one film from its studied script to a reviewed file: voice, shot list and stills, a still check, checks to 0 FIX, clips, render and caption text, a gate, three readers, then fix rounds until no P0 is left',
  phases: [
    { title: 'Voice', detail: 'script table to script.json, narration, speech check, cues' },
    { title: 'Build', detail: 'one builder: shot list, drawn devices, stills, first checks' },
    { title: 'Still check', detail: 'a checker looks at every generated still on every use and fills the checklist answers' },
    { title: 'Checks', detail: 'one builder: plan, lint, frames, lint-frames and stills checks to exit 0' },
    { title: 'Prepare', detail: 'one builder: style sweep, clips, render, caption text' },
    { title: 'Gate', detail: 'the builder quotes check all, exit 0 on every stage, before any reader starts' },
    { title: 'Readers', detail: 'a viewer and editor, a design ruler and an honesty checker read the file' },
    { title: 'Fix', detail: 'one builder applies every finding and re-renders' },
  ],
}

// args: { batch, build, from: 'voice' | 'build' | 'prepare' | 'review' | 'fix', rounds, today, film: {...} }
// film: { build, slug, title, topic, seconds, music: { theme, track }, special, note, voiceNote, viewerExtra, designExtra, honestyExtra }
// The build folder (<batch>/builds/<build>) is args.build or film.build: give either, or both with the same value.
// from defaults to 'voice'; any other value than the five above stops the run before an agent starts.
// The gate (check all at exit 0) runs before the first readers, so also on a resume from 'review'.
// clips: { min, max } is how many moving clips the film gets (default 8 to 12, the rule list's count for a two-minute
// film; about three minutes of GPU each). The first run of this script said "up to five" and its film came back with
// five clips and a minute of drawings on bare plates.
// film.music names the bed under the voice (<music_dir>/<theme>/<track>.mp3); the voice step needs it, and render refuses a script.json without it.
// `from: 'fix'` starts at fix round 1 with the reviews already saved under <build>/proof/reviews/.
const BATCH = args.batch
const STUDIO = `${BATCH}/studio`
// studio.py runs in the studio's own environment (playwright, pillow, numpy as requirements.txt pins them):
// plain python lacks them, and every check that needs one would read NOT CHECKED.
const CLI = `uv run --no-project --with-requirements ${STUDIO}/requirements.txt python ${STUDIO}/studio.py`
const f = args.film
if (args.build && f.build && args.build !== f.build) throw new Error(`args.build (${args.build}) and film.build (${f.build}) name different build folders: give one, or both the same`)
const BUILD = args.build || f.build
if (!BUILD) throw new Error('the build folder is missing: give args.build or film.build (the folder name under <batch>/builds/)')
const B = `${BATCH}/builds/${BUILD}`
const TEMPLATES = `${STUDIO}/templates`
// new-batch copies the manual and the rule list into <batch>/docs/, so they describe the kit the batch holds
const DOC = args.reference || `${BATCH}/docs/studio.md`
const CHECKLIST = args.checklist || `${BATCH}/docs/studio-checklist.md`
const STAGES = ['voice', 'build', 'prepare', 'review', 'fix']
const START = STAGES.indexOf(args.from || 'voice')
if (START < 0) throw new Error(`from must be one of ${STAGES.join(', ')} (got ${JSON.stringify(args.from)})`)
const runs = stage => STAGES.indexOf(stage) >= START
if (runs('voice') && !(f.music && f.music.theme && f.music.track)) throw new Error('film.music is missing: give film: { music: { theme, track } } (a folder and a track under the batch music_dir, <theme>/<track>.mp3); the voice step writes it into script.json and render refuses a film without it')
const x = v => (v ? `${v} ` : '')
const CLIPS = Object.assign({ min: 8, max: 12 }, args.clips || {})
// models and efforts: one per stage ({ voice, build, stillCheck, checks, prepare, gate, reader, fix }); a stage left
// out keeps its default. Without them every agent runs on the session's model at the session's effort: on the first
// film the four building agents ran 418 minutes, of which their commands took 59 (measured 2026-11-25).
const MODEL = Object.assign({ voice: 'sonnet', build: 'opus', stillCheck: 'sonnet', checks: 'opus', prepare: 'opus', gate: 'sonnet', reader: 'opus', fix: 'opus' }, args.models || {})
const EFFORT = Object.assign({ voice: 'high', build: 'high', stillCheck: 'medium', checks: 'high', prepare: 'high', gate: 'low', reader: 'high', fix: 'high' }, args.efforts || {})
const on = stage => ({ model: MODEL[stage], effort: EFFORT[stage] })
// The one length target of a film (templates/script.md says the same); every brief that names a length uses it.
const LENGTH = 'the speech ends between 92 and 115 s and a 3 s end card follows, so the film runs 95 to 118 s'

const WHO = `Viewers are on phones and most leave within seconds, so every shot must earn its place and every word on screen must be true. The viewer is described in ${B}/brief.md (section "Who watches"). Today is ${args.today}. The batch decides the AI disclosure: read "tag" and "end"."ai_line" in ${BATCH}/batch.json. Each surface follows its own key: the chip on generated pictures follows "tag" (the kit draws the copy the script step wrote into script.json; if \`build\` warns that the two differ, say so in your report), the end card line follows "ai_line". A surface whose own key is empty carries no AI wording. When either is set, the caption's second paragraph says that the pictures and the voice are AI-generated and the alt text says that the pictures are (${TEMPLATES}/caption.md). When both are empty the film carries no AI disclosure anywhere: no chip, no end card line, and nothing in post.json that says the pictures or the voice are AI-made (a film whose subject is AI still names its subject). Either way the caption's second paragraph says what the pictures are, as ${TEMPLATES}/caption.md words it.`

const READ = `READ FIRST, in this order (they are rules, not suggestions):
1. ${DOC}: the pipeline, the commands, the shot JSON and every device with its settings. Its rules are tagged (L01 to L18 are linted, C1 to C6 are looked at); ${CHECKLIST} lists them one per line. A rule is applied to EVERY shot of the film, not only to the shots someone names.
2. In the build folder ${B}: brief.md (staging rules for this film), script.md and script.json (the final lines: never change a caption or a spoken word), cues.txt (every word's time; cue "L12:3" is the fourth word of line 12), shots.py (it writes shots.json; later blocks override earlier ones), graphics.js (this film's own drawn devices, if present), facts.md and any fact trace beside it (what each line rests on), proof/shots_table.md and proof/blocks.md (which block touched each shot), and proof/build_report.md once a builder has written it.`

const RULES = `HARD RULES: never chain shell commands with && (use ; or separate calls). Never use an em dash or en dash in any text you write. The engine is the batch's own copy in ${STUDIO}: do not edit it; if you believe it has a bug, describe it in your report with the frame or the output that shows it and work around it in this build's own files. Never touch another build's files. No web fetches: every fact you need is in facts.md and the copies it cites. Do not package, upload or publish anything. Never write or edit accept.json in a build folder: only the owner accepts a finding. Report only what a command printed or a frame showed; if a step failed, say so with its output. In script.json you may change only "gap" values; after a gap change run \`${CLI} voice ${B}\` again.`

const CHECKS = `Check, until each of these passes (exit code 0 and, for a check, its own closing line \`check <stage>: exit 0\`; read every FIX and NOTE row, never pipe the output through grep). Run them in this order, and run build again after any change to shots.py, shots.json, graphics.js, script.json or a picture: every check refuses with exit code 3 while timeline.json is older than one of them. A FIX row that the owner named in accept.json is printed as accepted and does not count.
  ${CLI} build ${B}
  ${CLI} check ${B} plan
  ${CLI} check ${B} lint
  ${CLI} check ${B} frames
  ${CLI} check ${B} lint-frames
  ${CLI} check ${B} stills
Then open EVERY contact sheet in ${B}/proof/ and judge it as three readers will (a first-time viewer with the sound off, a design ruler, a fact and honesty checker); fix what you see and run the checks again. Exit codes: 0 PASS, 1 FIX, 2 NOT CHECKED or missing input, 3 refused because an input is stale (rebuild it), 64 usage error.`

const PICS = `Pictures. To remake a still, give the shot its own still(...) with the checkable features in check=[...] in your block, then run  ${CLI} stills ${B} --only <shot id>  (about 25 s on a local GPU that other jobs may share), then build again (the new picture makes timeline.json stale) and  ${CLI} check ${B} frames  (it rewrites proof/checklist.md with the new frame). LOOK at every new picture at full size, corners and bottom too, before you keep it, and write its six answers (C1 to C6, as ${TEMPLATES}/readers/still-check.md describes) into proof/checklist_answers.json: check stills counts an answer older than its picture as a FIX. At most three tries, then restage the shot as type on a blurred plate or as a drawing. Never keep a picture that shows something later than its date, the wrong object, a face, a badge or flag, or lettering. A real, named thing never gets a photoreal picture.`

const NOTE = f.special ? `\nNOTES FOR THIS FILM: ${f.special}\n` : ''

const voiceBrief = `You are preparing the voice of one narrated film on the studio pipeline. Its script has been drafted, read by independent readers, revised and traced against its sources; your job is to turn it into the final script file, narrate it, and prove every word is heard right. ${WHO}

THE FILM: ${f.topic}
Build folder: ${B} (work inside it; read access to the rest of ${BATCH}).

READ FIRST: ${B}/script.md, all of it (the table under "## Script" is the script: id, beat, caption, spoken, facts, gap; read the size targets too), any fact trace in the build folder (the last fact check: its column of corrected wordings), and ${B}/brief.md. For the commands see ${DOC}.

THE WORK
1. If a fact trace exists, apply its corrected wordings, and only those, to the rows of the script table: the caption column (digits for numbers) and the spoken column (numbers as words, the respellings the script already uses for names). Change nothing else: the script has been studied. Add one line at the end of script.md saying which lines you changed and why. A corrected wording that makes a line longer than 18 spoken words is kept: say so in your report.
2. Run  ${CLI} script ${B} --theme ${f.music && f.music.theme} --track ${f.music && f.music.track}  (it reads the first table with an id column, takes the batch's accent, tag and voice speed, and writes script.json with the music bed; a script.json that names no music makes render refuse, so check that its last line has no "no music" note).
3. Run  ${CLI} voice ${B}  (it narrates, writes cues.txt and runs the speech check; about two minutes; exit code 1 means a misheard word). If the speech check reports a misheard word, listen to its evidence: when the voice really misreads a word (a name, a number, a heteronym such as read or lead), respell ONLY the spoken field of that line in script.md (the caption keeps the correct spelling), or, when the word is wrong in more than one line, add it once to the table under "## Lexicon" of script.md (columns word and say; the script command copies it into script.json), and run step 2 and 3 again. Extra words reported after the end of a line are the recogniser hearing silence, not a fault. Stop after four rounds and report.
4. Read cues.txt: every line must have its words with times.
${f.voiceNote ? 'NOTE FOR THIS FILM: ' + f.voiceNote + '\n' : ''}5. Check the size against script.md's targets: 27 to 32 lines; ${LENGTH}; the hook's speech is over by 3.0 s. If the speech runs long or short, do NOT rewrite lines: report it.

${RULES}

REPORT (plain text, under 400 words): the lines you changed from the trace, with old and new wording; the last lines of the voice command (lines, words, speech end, hook end) and of the speech check; every respelling you made; anything you could not do.`

const buildBrief = `You are building the shot list of one narrated film (1080 x 1920, 30 fps, about ${f.seconds} s) on the studio pipeline. The script is final and narrated; your job is everything between the narration and the first render: the shots, the on-screen devices, the still pictures, and the first checks. ${WHO}

THE FILM: ${f.topic}
Build folder: ${B} (work only inside it, plus read access to the rest of ${BATCH}).

${READ}
3. ${TEMPLATES}/shots.py: the skeleton of a shot list (shotkit helpers, a Plan, shots, one @plan.block, plan.write()). If ${B}/shots.py is still the skeleton, replace its placeholders; copy the structure of any finished build in ${BATCH}/builds/ for devices the kit lacks.

WHAT TO MAKE (all inside your build folder):
- shots.py that writes shots.json when built, and graphics.js for devices the kit lacks (a pure function of time registered with Kit.graphic; never ask the image model for lettering, digits, maps, flags, badges, documents, diagrams or named real things: those are type or our own drawings).
- Stills for the shots that carry a picture, with each still's check=[...] features written from the brief's "check before any still is used" list:  ${CLI} stills ${B}  (about 25 s each). LOOK at every still at full size and reject any that breaks the picture rules. Re-prompt at most twice per still; then restage the shot as type on a blurred plate or as a drawing.
- Do NOT make clips: list instead, in your report, ${CLIPS.min} to ${CLIPS.max} stills that deserve motion (the first frame among them) with the motion you would ask for, and write their clip(...) prompts into shots.py so the next builder can run them. Plan the pictures for that count: the rule list asks for ${CLIPS.min} or more clips where the story moves.
- A drawing or a type card never stands on a bare plate for more than 10 s in a row (check plan, P12): set a drawing over a blurred, slowly drifting picture (a picture shot with grade blur and the graphic as one of its overlays), draw it large enough to fill the band between the top row and the captions, and cut a picture in the clear between two drawn stretches.
${NOTE}
THEN run the first checks and read every row (build first, then the frames, so that proof/checklist.md names the frame to open for every use of every still):
  ${CLI} build ${B}
  ${CLI} check ${B} plan
  ${CLI} check ${B} lint
  ${CLI} check ${B} frames
(check stills fails until the still checker has answered; that is expected here). Save your report as ${B}/proof/build_report.md as well as returning it. The next two steps (the still check and the checks to 0 FIX) are done by others.

${RULES}

REPORT (plain text): the last line of each command; the number of shots and the film length; every still with kept or restaged and why; the clip candidates with their motion; every on-screen string that states a fact, with its facts.md row; the three shots you are least sure of and why; anything in the staging notes you could not do.`

const stillCheckBrief = `You are the still checker of one film. Read ${TEMPLATES}/readers/still-check.md and do exactly what it says. {film} is: ${f.topic}. The build folder is ${B}; the checklist is ${B}/proof/checklist.md (written by build and rewritten by \`${CLI} check ${B} frames\`: each still's uses with the line spoken over it and the frame to open). Write ${B}/proof/checklist_answers.json as that file describes. Change nothing else. Never use an em dash or en dash. Report the count of ok:false answers and each still with its fault and fix.`

const checksBrief = `You are the builder of one narrated film (about ${f.seconds} s). The shot list and stills exist and a still checker has answered ${B}/proof/checklist_answers.json (every ok:false is a FIX). Your job: bring every check to 0 FIX. ${WHO}

THE FILM: ${f.topic}
Build folder: ${B} (work inside it; read access to the rest of ${BATCH}).

${READ}
3. ${B}/proof/checklist.md and ${B}/proof/checklist_answers.json (what the still checker found).
${NOTE}
THE WORK
A. Fix every FIX and every ok:false: all of them in ONE new dated @plan.block at the end of shots.py (a comment with today's date, ${args.today}); do not rewrite earlier blocks. Change graphics.js where a drawn device must change. Read every NOTE row too and fix what a viewer would see.
B. ${PICS}
C. ${CHECKS}
D. Append what you changed to ${B}/proof/build_report.md.

${RULES}

REPORT (plain text, under 500 words): the last line of each check; what you changed per rule id; every still remade; the three shots you are least sure of.`

const prepareBrief = `You are the builder of one narrated film (about ${f.seconds} s). Another builder made its shot list and stills and brought the checks to 0 FIX; nothing has been rendered. Your job is to take it to a finished file that is ready for its first outside review. ${WHO}

THE FILM: ${f.topic}
Build folder: ${B} (work inside it; read access to the rest of ${BATCH}).

${READ}
${NOTE}
THE WORK
A. Sweep. Walk ${CHECKLIST} down proof/shots_table.md and the contact sheets and list every shot that breaks a rule, whether or not the lint caught it (the rules marked [look] are only found by looking). Take up what the first builder was least sure of. Fix all of it in ONE new dated @plan.block at the end of shots.py; change graphics.js where a drawn device must change.
B. ${PICS}
C. Clips: motion for ${CLIPS.min} to ${CLIPS.max} stills where the story moves, the first frame of the film among them (read the clip prompt rules in ${DOC} first). Go on through the candidates until ${CLIPS.min} clips are kept or no still is left that deserves motion, and say in your notes how many are kept. Run  ${CLI} clips ${B} --only <shot id>  (two to three minutes each on a shared GPU). The frames land in media/<shot id>/ ; look at five frames spread over each clip at full size. Keep a clip only if the subject holds its shape, nothing new enters, no lettering appears and the last frame is still a good picture; otherwise try once more with a calmer prompt, then keep the still. A shot whose camera scale is above 1.25 gets it lowered when it becomes a clip.
D. ${CHECKS}
E. Write post.json, the text that goes under the film, from ${TEMPLATES}/post.json, following ${TEMPLATES}/caption.md rule by rule (the second paragraph says what the pictures are; when batch.json sets "tag" or "end"."ai_line" it must also say that the pictures and the voice are AI-generated, and the alt text that the pictures are; when both are empty post.json does not say that they are AI-made; a negative is written as what we found; sources by kind; a cover_ms frame you have looked at). No em or en dashes, no emoji.
F. Render:  ${CLI} render ${B}  (about two minutes; it refuses with exit code 3 when timeline.json is stale, when script.json names no music, and when plan or lint is missing, older than timeline.json or holds a FIX that accept.json does not name; it renders, mixes and checks the file). Then pull single frames from the file in ${B}/out/ into ${B}/proof/ at the moments that matter (for a count: 0.1 s before and after its spoken word; the first frame; each payoff) and look at them.
G. Write ${B}/proof/prepare_notes.md: what your sweep found and changed, every picture and clip you made (kept or dropped, and why), and what you are still unsure of.

${RULES}

REPORT (plain text, under 800 words): the last line of each check and the film's length, size and loudness from the render output; what the sweep changed; clips kept and dropped; stills remade; the three things you are least sure of.`

const GATE = {
  type: 'object',
  properties: {
    exit_code: { type: 'integer' },
    fix_count: { type: 'integer' },
    quote: { type: 'string' },
  },
  required: ['exit_code', 'fix_count', 'quote'],
}
const gateBrief = (again) => `You are the builder of one narrated film. ${again ? 'The last gate run still had FIX rows; this is the one more round you get. ' : ''}No reader starts until this gate shows 0 FIX. Build folder: ${B}.

Run  ${CLI} check ${B} all  and quote VERBATIM in "quote" (do not paraphrase) every row it printed and its closing lines: one per stage (\`check plan: exit <n>\`, \`check lint: exit <n>\`, \`check frames: exit <n>\`, \`check lint-frames: exit <n>\`, \`check stills: exit <n>\`, \`check file: exit <n>\`) and the last one, \`check all: exit <n>\`. Put the command's exit code in "exit_code" and the number of FIX rows that are not printed as accepted in "fix_count". If it prints any FIX, fix them (in ONE new dated @plan.block at the end of shots.py, ${args.today}; rebuild; render again with  ${CLI} render ${B} ), then run  ${CLI} check ${B} all  once more and quote that run instead. A NOT CHECKED (exit code 2) is not a pass: say which check did not run and why.

${READ}
${RULES}`

const FINDINGS = {
  type: 'object',
  properties: {
    verdict: { type: 'string' },
    answered: { type: 'array', items: { type: 'string' } },
    still_open: { type: 'array', items: { type: 'string' } },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          shot: { type: 'string' },
          time: { type: 'string' },
          severity: { type: 'string', enum: ['P0', 'P1', 'P2'] },
          problem: { type: 'string' },
          fix: { type: 'string' },
        },
        required: ['shot', 'time', 'severity', 'problem', 'fix'],
      },
    },
    could_not_check: { type: 'array', items: { type: 'string' } },
  },
  required: ['verdict', 'findings'],
}

const readerBrief = (key, round, extra) => `You are a reader of one finished film. Read ${TEMPLATES}/readers/${key}.md and do exactly what it says: it holds your role, what you have, what to judge, the severity definition and the return format.
In that file {audience} is the text of the file named by "readers.audience_file" in ${BATCH}/batch.json (read that file); {film} is: ${f.topic} (about ${f.seconds} s). The build folder is ${B}; the finished file is in ${B}/out/. The house rules are in ${DOC} and ${CHECKLIST}. Whether the film carries an AI disclosure follows "tag" and "end"."ai_line" in that batch.json, each surface by its own key: the chip follows "tag", the end card line follows "ai_line", and a surface whose own key is empty carries no AI wording. When either is set, the caption's second paragraph says that the pictures and the voice are AI-generated and the alt text says that the pictures are. With both empty, a missing chip, end card line or caption sentence is not a finding, and wording on the film or in post.json that says the pictures or the voice are AI-made is one (a film whose subject is AI may name its subject). Today is ${args.today}. ${round === 0 ? 'The film has just been rendered and nobody outside its makers has seen it.' : `The film has been reviewed by three readers and changed; the makers have just finished fix pass ${round}. Read ${B}/proof/fix${round}_answers.md: every finding of the last review with what the makers say they did. Do not take "done" on trust: look.`}
Before you return, write the JSON you return to ${B}/proof/reviews/review${round}_${key}.json (make the folder if it is missing), so the film keeps this review when no fix round follows it.
${x(f.note)}${x(extra)}`

const lenses = [
  { key: 'viewer-editor', extra: f.viewerExtra },
  { key: 'design', extra: f.designExtra },
  { key: 'honesty', extra: f.honestyExtra },
]
const check = async round => {
  const read = (l, again) => agent(readerBrief(l.key, round, l.extra), { label: `readers${round}${again}:${l.key}`, phase: 'Readers', schema: FINDINGS, ...on('reader') }).then(r => ({ key: l.key, r }))
  let got = (await parallel(lenses.map(l => () => read(l, '')))).filter(Boolean).filter(r => r.r)
  // A reader that did not return is asked once more: a film is never called ready with a lens unread.
  const lost = lenses.filter(l => !got.some(g => g.key === l.key))
  if (lost.length) {
    log(`readers: ${lost.map(l => l.key).join(', ')} did not return; one more try`)
    got = got.concat((await parallel(lost.map(l => () => read(l, 'b')))).filter(Boolean).filter(r => r.r))
  }
  return got.map(r => ({ key: r.key, verdict: r.r.verdict, answered: r.r.answered || [], still_open: r.r.still_open || [], findings: r.r.findings, could_not_check: r.r.could_not_check || [] }))
}

const fixBrief = (round, inline) => `You are the builder of one narrated film (about ${f.seconds} s). The film has been rendered and reviewed by three readers; your job is fix pass ${round}: apply every finding, sweep the whole film against the house rules again, re-render it and prove what you did. ${WHO}

THE FILM: ${f.topic}
Build folder: ${B} (work inside it; read access to the rest of ${BATCH}).

${READ}
3. proof/prepare_notes.md and any proof/fix*_answers.md from earlier passes.
4. The findings to answer: ${inline ? 'the JSON at the end of this message (three readers; read all of it)' : `the reader files saved under ${B}/proof/reviews/ (read them all)`}.
${NOTE}
THE WORK
A. ${inline ? `Save the readers' findings: write the JSON below to ${B}/proof/reviews/run_${round}.json exactly as given, then run  ${CLI} review save ${B} ${B}/proof/reviews/run_${round}.json --stage fix${round}  and  ${CLI} review answers ${B} --stage fix${round}  (it writes the answers skeleton proof/fix${round}_answers.md, one entry per finding, which step H fills in).` : `The readers' findings are already saved under ${B}/proof/reviews/ (each file name starts with the stage it was saved under). Run  ${CLI} review answers ${B} --stage <that stage>  for the answers skeleton and copy it to proof/fix${round}_answers.md, which step H fills in.`}
B. Sweep again: walk ${CHECKLIST} down proof/shots_table.md and the sheets and list every shot that breaks a rule, whether or not a reader named it.
C. Fix everything: every finding of every reader (P0, P1 and P2) and every item of your sweep, in ONE new dated @plan.block at the end of shots.py (a comment with today's date, ${args.today}, and "fix ${round}"); do not rewrite earlier blocks. Change graphics.js where a drawn device must change, and post.json and facts.md where the honesty reader asks (a facts.md row may be added only from a saved copy or from a page a row already cites). Where two readers ask for opposite things, follow the house rules and say so.
D. ${PICS} Do not make new clips unless a finding asks for one.
E. ${CHECKS}
F. Keep the old file: copy it in ${B}/out/ to <name>_before_fix${round}.mp4 if that name does not exist yet. Then render with  ${CLI} render ${B}  and look at frames from the new file at the moments the findings name.
G. Gate:  ${CLI} check ${B} all  must exit 0 with every \`check <stage>: exit 0\` line printed (a FIX row accept.json names is printed as accepted and does not count); quote those lines in your report.
H. Write ${B}/proof/fix${round}_answers.md: for every finding of every reader and every item of your sweep, one entry: the reader and the finding's shot and time, the problem in one line, what you did (or why you did not, with what you tried), and the time of the frame that shows it.

${RULES}

REPORT (plain text, under 800 words): the last line of each check and the film's length, size and loudness; the count of findings fixed against the count asked, and every finding you did NOT fix with the reason; every still you remade; the three things you are least sure of.
${inline ? '\nFINDINGS TO ANSWER (JSON):\n' + inline : ''}`

const rounds = args.rounds || 2
const out = { slug: f.slug }
// The film is ready when all three readers returned, each says READY and none lists a P0 (a verdict word never
// outweighs a P0 finding). A reader that did not return, after its second try, is not a NOT READY and not a
// READY: the round is not judged and the run stops, so no fix round is spent on it and no film passes with a
// lens unread. `why` says which rule decided.
const judge = list => {
  const word = list.filter(r => !/^\s*READY/i.test(r.verdict)).map(r => r.key)
  const p0 = list.filter(r => r.findings.some(x => x.severity === 'P0')).map(r => r.key)
  const missing = lenses.filter(l => !list.some(r => r.key === l.key)).map(l => l.key)
  const why = missing.length ? `not judged: ${missing.join(', ')} did not return, twice, so the run stops`
    : word.length ? `not ready: the verdict of ${word.join(', ')} is not READY`
    : p0.length ? `not ready: ${p0.join(', ')} list a P0 under a READY verdict`
    : 'ready: every reader says READY and lists no P0'
  return { ready: !missing.length && !word.length && !p0.length, missing, why }
}
// An agent that returns nothing stops the run: the next agent would work on missing input.
const stop = name => {
  log(`${name}: the agent returned nothing; the run stops before the next agent`)
  out.stopped = name
  return out
}

phase('Voice')
if (runs('voice')) {
  out.voice = await agent(voiceBrief, { label: `voice:${f.slug}`, phase: 'Voice', ...on('voice') })
  if (!out.voice) return stop('voice')
}

phase('Build')
if (runs('build')) {
  out.built = await agent(buildBrief, { label: `build:${f.slug}`, phase: 'Build', ...on('build') })
  if (!out.built) return stop('build')
  phase('Still check')
  out.stillCheck = await agent(stillCheckBrief, { label: `still-check:${f.slug}`, phase: 'Still check', ...on('stillCheck') })
  if (!out.stillCheck) return stop('still-check')
  phase('Checks')
  out.checked = await agent(checksBrief, { label: `checks:${f.slug}`, phase: 'Checks', ...on('checks') })
  if (!out.checked) return stop('checks')
}

phase('Prepare')
if (runs('prepare')) {
  out.prepared = await agent(prepareBrief, { label: `prepare:${f.slug}`, phase: 'Prepare', ...on('prepare') })
  if (!out.prepared) return stop('prepare')
}

// The gate runs before the first readers, so a resume from 'review' gets it too ('fix' starts with a builder whose
// own step G runs check all).
if (runs('review')) {
  phase('Gate')
  let gate = await agent(gateBrief(false), { label: `gate:${f.slug}`, phase: 'Gate', schema: GATE, ...on('gate') })
  // check all prints one `check <stage>: exit <n>` line per stage, then `check all: exit <n>` (the worst stage; a
  // FIX row that accept.json names does not count). The gate passes on exit code 0 and that closing line.
  const passed = g => g && g.exit_code === 0 && /check all: exit 0/.test(g.quote || '')
  if (!passed(gate)) {
    log(`gate: not clean (${gate ? gate.fix_count : '?'} FIX), one more round`)
    gate = await agent(gateBrief(true), { label: `gate2:${f.slug}`, phase: 'Gate', schema: GATE, ...on('checks') })
  }
  out.gate = gate
  if (!passed(gate)) {
    log('gate: check all did not exit 0 on every stage; no reader starts')
    out.stopped = 'gate'
    return out
  }
}

const history = []
const reports = []
out.reports = reports
out.history = history
let last = []
let verdict = null
const review = async round => {
  last = await check(round)
  history.push({ round, checks: last })
  verdict = judge(last)
  log(`${round ? `round ${round}` : 'first review'}: ${last.length}/3 readers, ${verdict.why}`)
  out.ready = verdict.ready
  if (verdict.missing.length) out.stopped = `readers${round}`
}
if (runs('review')) {
  phase('Readers')
  await review(0)
}
phase('Fix')
for (let round = 1; round <= rounds && !out.stopped; round++) {
  if (verdict && verdict.ready) break
  const inline = last.length ? JSON.stringify(last.map(r => ({ reader: r.key, verdict: r.verdict, still_open: r.still_open, findings: r.findings }))) : ''
  const report = await agent(fixBrief(round, inline), { label: `fix${round}:${f.slug}`, phase: 'Fix', ...on('fix') })
  reports.push({ round, report })
  if (!report) return stop(`fix${round}`)
  await review(round)
}
return out
