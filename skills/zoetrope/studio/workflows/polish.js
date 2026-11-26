export const meta = {
  name: 'polish',
  description: 'Make a list of named changes to one finished film with one builder, re-render it, then have fresh checkers rule on every change from frames of the new file and on whether anything else moved',
  phases: [
    { title: 'Polish', detail: 'one builder: keep the old film, the named changes in one dated block, the checks, the render, the gate' },
    { title: 'Check', detail: 'the gate once more, and one fresh checker per lens: each change fixed or not, and nothing else moved' },
  ],
}

// args: { batch, today, pass, pictures, clips, also, models: { builder, checker, gate }, efforts: { builder, checker, gate }, lenses: [...], film: {...}, items: [...] }
// film: { build, slug, seconds, topic, special }
// items: [{ id, where, problem, ruling }]: id is a short label ("A"), where names the shots and their times,
// problem is what a reader saw, ruling is what the film's owner decided (the builder follows the ruling).
// Use it when every reader of film.js said READY and findings are still worth mending. A fix round of film.js
// sweeps the whole film and brings three readers back (hours); this pass changes only what `items` names and
// ends on a closed-list check (about an hour, measured on four films).
// pass numbers the block, the kept film and the answers file: "polish 1", <slug>_before_polish1.mp4 (with its
// timeline beside it, so `changed` can compare shot by shot when a cut moved) and proof/polish1_answers.md.
// pictures: true lets the builder remake or add stills. clips: N lets it make up to N new clips (default 0).
// also: one more sentence of work, for example "Take any P2 of the saved reviews that is a one-line change."
// lenses: [{ key, role, look }], one checker each; the default is a viewer and design checker and an honesty checker.
const BATCH = args.batch
const STUDIO = `${BATCH}/studio`
const CLI = `uv run --no-project --with-requirements ${STUDIO}/requirements.txt python ${STUDIO}/studio.py`
const f = args.film
const B = `${BATCH}/builds/${f.build}`
const TEMPLATES = `${STUDIO}/templates`
const DOC = args.reference || `${BATCH}/docs/studio.md`
const CHECKLIST = args.checklist || `${BATCH}/docs/studio-checklist.md`
const N = args.pass || 1
// ids are compared as strings: the checkers return them as strings (RULED), so an id given as 1 must match '1'
const ITEMS = (args.items || []).map(i => ({ ...i, id: String(i.id) }))
// A stage left out keeps its default. Without an effort an agent thinks at the session's, which is slow at the top one.
const MODELS = Object.assign({ builder: 'opus', checker: 'opus', gate: 'sonnet' }, args.models || {})
const EFFORTS = Object.assign({ builder: 'high', checker: 'high', gate: 'low' }, args.efforts || {})
const CLIPS = args.clips || 0
const FILM = `${B}/out/${f.slug}.mp4`
const BEFORE = `${B}/out/${f.slug}_before_polish${N}.mp4`
const LENSES = args.lenses || [
  {
    key: 'viewer',
    role: 'You watch as a first-time viewer on a phone with the sound off, and as the design ruler of the house rules.',
    look: 'What a viewer reads and in what order; whether each changed card, number and label holds long enough to be read; type inside the safe box and clear of the captions; one accent, one look; a picture that says what its line says; anything that reads as a glitch (a jump, a flash, a cut between two frames that look alike).',
  },
  {
    key: 'honesty',
    role: 'You check facts and honesty.',
    look: 'Every word, number, date, name and source that the pass put on screen or into post.json, against facts.md and the saved copies it cites; hedges and qualifiers kept as the source has them; a picture that claims more than its line; a source line that lends its source to a neighbouring claim.',
  },
]

if (!ITEMS.length) {
  log('polish: no items given, nothing to do')
  return { slug: f.slug, stopped: 'no items' }
}

const list = ITEMS.map(i => `${i.id}. ${i.where}. What a reader saw: ${i.problem} Ruling: ${i.ruling}`).join('\n')
const NOTE = f.special ? `\nNOTES FOR THIS FILM: ${f.special}\n` : ''
const ALSO = args.also ? `\nALSO: ${args.also} List what you took and what you left.\n` : ''

const RULES = `HARD RULES: never chain shell commands with && (use ; or separate calls). Never use an em dash or en dash in any text you write. The engine is the batch's own copy in ${STUDIO}: do not edit it; if you believe it has a bug, describe it in your report with the frame or the output that shows it and work around it in this build's own files. Never touch another build's files. No web fetches: every fact you need is in facts.md and the copies it cites. Do not package, upload or publish anything. Never write or edit accept.json in a build folder: only the owner accepts a finding. Report only what a command printed or a frame showed; if a step failed, say so with its output.`

const CHECKS = `Check, until each of these passes (exit code 0 and, for a check, its own closing line \`check <stage>: exit 0\`; read every FIX and NOTE row, never pipe the output through grep). Run them in this order, and run build again after any change to shots.py, shots.json, graphics.js, script.json or a picture: every check refuses with exit code 3 while timeline.json is older than one of them.
  ${CLI} build ${B}
  ${CLI} check ${B} plan
  ${CLI} check ${B} lint
  ${CLI} check ${B} frames
  ${CLI} check ${B} lint-frames
  ${CLI} check ${B} stills
Then open the proof frames of every shot you changed (${B}/proof/frames/ and the contact sheets) before you render. Exit codes: 0 PASS, 1 FIX, 2 NOT CHECKED or missing input, 3 refused because an input is stale (rebuild it), 64 usage error.`

const PICS = args.pictures
  ? `Pictures. An item may need a new still: give the shot its own still(...) with the checkable features in check=[...] in your block, run  ${CLI} stills ${B} --only <shot id>  (about 25 s on a local GPU that other jobs may share), build again and run  ${CLI} check ${B} frames. LOOK at every new picture at full size before you keep it and write its six answers (C1 to C6, as ${TEMPLATES}/readers/still-check.md describes) into proof/checklist_answers.json. At most three tries a picture, then restage the shot as type on a blurred plate or as a drawing. A real, named thing never gets a photoreal picture.`
  : 'Pictures. Do not make or remake any still in this pass. If an item cannot be met without a new picture, leave it and say so.'

const MOTION = CLIPS
  ? `Clips. You may make up to ${CLIPS} new clips where an item asks for motion (read the clip prompt rules in ${DOC} first): write the clip(...) prompt in your block and run  ${CLI} clips ${B} --only <shot id>  (about three minutes each on a shared GPU). Look at five frames spread over each clip at full size. Keep a clip only if the subject holds its shape, nothing new enters, no lettering appears and the last frame is still a good picture; otherwise try once more with a calmer prompt, then keep the still. A shot whose camera scale is above 1.25 gets it lowered when it becomes a clip.`
  : 'Clips. Make no clip in this pass.'

const polishBrief = `You are the builder of one narrated film (1080 x 1920, 30 fps, about ${f.seconds} s) on the studio pipeline. The film has been rendered and reviewed, and every reader said READY. Your job is polish pass ${N}: make the named changes below (${ITEMS.length} of them), re-render the film and prove every change on frames of the new file. Do not sweep or restyle what no item names: it passed. Today is ${args.today}.

THE FILM: ${f.topic}
Build folder: ${B} (work inside it; read access to the rest of ${BATCH}).

READ FIRST
1. ${DOC} (the pipeline, the commands, the shot JSON and every device with its settings) and ${CHECKLIST} (the house rules, one per line).
2. In ${B}: brief.md, shots.py (it writes shots.json; later blocks override earlier ones), graphics.js if present, script.json (never change a caption or a spoken word; a gap may change where an item says so), cues.txt, facts.md, post.json, proof/shots_table.md, proof/blocks.md, every proof/fix*_answers.md and proof/polish*_answers.md, and the reader files under proof/reviews/.
${NOTE}
THE CHANGES (follow each ruling; where a ruling leaves a choice, take the smallest change that meets it)
${list}
${ALSO}
THE WORK
A. Before you change anything, keep the film as it is:  ${CLI} keep ${B} polish${N}  (it copies the film and its timeline to out/${f.slug}_before_polish${N}.*; a copy that exists is left alone).
B. Write every change as ONE new dated @plan.block at the end of shots.py (a comment with today's date and "polish ${N}"); do not rewrite earlier blocks. Change graphics.js only where an item needs it, and post.json or facts.md only where an item names them (a facts.md row may be added only from a saved copy or from a page a row already cites). A motion you add to a drawing runs on its shot's or its own start time, never on bare film time, so the shot looks the same wherever it stands in the film.
C. ${PICS}
D. ${MOTION}
E. ${CHECKS}
F. Render:  ${CLI} render ${B}.
G. Gate:  ${CLI} check ${B} all  must exit 0 with every \`check <stage>: exit 0\` line printed (a FIX row that accept.json names is printed as accepted and does not count); quote those lines.
H. Prove it on the file: for every item pull single frames from the new film at the times that show it (for example  ffmpeg -v error -y -ss 12.4 -i ${FILM} -frames:v 1 ${B}/proof/polish${N}/f_12.4.png ; make the folder first), open each one, and keep the times. A change you cannot see on the new file is not done. Then run  ${CLI} changed ${B} --before ${BEFORE}  and read every line: each shot it names must be one an item names or one you can explain (a shot that only moved in time is not named).
I. Write ${B}/proof/polish${N}_answers.md: one entry per item (its id, what you did or why you could not with what you tried, and the times of the frames that show it), then every other thing you changed, one line each, then every shot \`changed\` named that no item names, with the reason.

${RULES}

Return the result in the given shape: gate_exit_code and gate_quote from step G, the film's length in seconds and size in bytes, one entry per item (id, done, what you did in one or two sentences, frame_times in seconds), other_changes (one line each, empty when none) and unsure (what you could not judge).`

const DONE = {
  type: 'object',
  properties: {
    gate_exit_code: { type: 'integer' },
    gate_quote: { type: 'string' },
    seconds: { type: 'number' },
    bytes: { type: 'integer' },
    items: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          done: { type: 'boolean' },
          what: { type: 'string' },
          frame_times: { type: 'array', items: { type: 'number' } },
        },
        required: ['id', 'done', 'what'],
      },
    },
    other_changes: { type: 'array', items: { type: 'string' } },
    unsure: { type: 'array', items: { type: 'string' } },
  },
  required: ['gate_exit_code', 'gate_quote', 'items'],
}

const gateBrief = `You run one command for a finished film and report what it printed. Build folder: ${B}.

Run  ${CLI} check ${B} all  (a few minutes) and put its exit code in "exit_code". Quote VERBATIM in "quote" (do not paraphrase) every FIX, NOTE and NOT CHECKED row it printed and its closing lines: one per stage (\`check plan: exit <n>\`, \`check lint: exit <n>\`, \`check frames: exit <n>\`, \`check lint-frames: exit <n>\`, \`check stills: exit <n>\`, \`check file: exit <n>\`) and the last one, \`check all: exit <n>\`. Change nothing: if a check fails, report it. Never chain shell commands with &&.`

const GATE = {
  type: 'object',
  properties: { exit_code: { type: 'integer' }, quote: { type: 'string' } },
  required: ['exit_code', 'quote'],
}

const checkBrief = (lens, built) => `You are a checker of one polish pass (pass ${N}) on a finished narrated film (1080 x 1920, 30 fps, about ${f.seconds} s). ${lens.role} A builder was given the named changes below and says what it did; you were not there. Rule on each change from frames of the new file, and on whether the pass broke anything. Do not take "done" on trust: look. Today is ${args.today}.

THE FILM: ${f.topic}
Build folder: ${B}. The new film is ${FILM}; the film before the pass is ${BEFORE}. The house rules are in ${DOC} and ${CHECKLIST}; the facts are in ${B}/facts.md with the saved copies it cites; the spoken lines and their times are in ${B}/script.json and ${B}/proof/shots_table.md (every shot with its times and on-screen text); the post text is ${B}/post.json; the builder's own account is ${B}/proof/polish${N}_answers.md.
${NOTE}
THE CHANGES THAT WERE ASKED
${list}

WHAT THE BUILDER SAYS (JSON): ${JSON.stringify(built.items || [])}
Its other changes: ${JSON.stringify(built.other_changes || [])}

YOUR LENS: ${lens.look}

THE WORK
1. Each item: pull single frames from the new film at the times that show it, the builder's times and times of your own inside the same shots, about every 0.3 to 0.5 s across a shot that changed (for example  ffmpeg -v error -y -ss 12.4 -i ${FILM} -frames:v 1 ${B}/proof/polish${N}/check/${lens.key}_12.4.png ; make the folder first), and open them at full size where type is small. Rule fixed: true only when the frames meet the ruling as it is written; say what the frame shows and its time. A change to post.json or facts.md is read in the file itself.
2. Nothing else moved: run  ${CLI} changed ${B} --before ${BEFORE}  (it compares the two films frame by frame, shot by shot when a cut moved, and prints each run of frames that differs with its shot, each shot whose length changed, each new shot and each shot that is gone). Every line must lie in a shot that an item names or that a line of the builder's other changes explains. For one that does not, pull a frame from the middle of the run from both films (the old one as ${lens.key}_old_<time>.png; in the old film the shot may stand at another time: the kept timeline ${B}/out/${f.slug}_before_polish${N}.timeline.json gives each shot's id with its t0 and t1 in the old film), say what differs, and list it as a regression. If the command cannot compare (exit code 2), compare by eye instead: eight times spread over the film outside the touched shots.
3. Inside every shot the pass touched: its first frame, a middle frame and its last frame, and the cut into it and out of it (the frame before and after each cut).
4. The opening and the close: the frames at 0.0, 1.0 and 3.0 s and across the last 4 s of the new film.
5. New findings: list only a P0 or a P1 that this pass introduced or left inside a shot it touched (P0: a false or misleading statement on screen or in the post text, a named real place, day or person on a photoreal picture, text outside the safe box or unreadable; P1: something a first-time viewer would trip over or leave at). Do not review the rest of the film again: it passed three readers.

HARD RULES: never chain shell commands with && (use ; or separate calls). Never write an em dash or en dash. No web fetches. Change no file of the film and run no build, render or check: you may only write frames under ${B}/proof/polish${N}/check/. Report only what a frame, a file or a command showed.

Return: one entry per item (id, fixed, saw, frame_time), regressions (empty when none), new_findings (each with severity, time, problem and fix; empty when none), could_not_check, and verdict: PASS when every item is fixed and there is no regression and no new P0 or P1, else FIX.`

const RULED = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['PASS', 'FIX'] },
    items: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          fixed: { type: 'boolean' },
          saw: { type: 'string' },
          frame_time: { type: 'number' },
        },
        required: ['id', 'fixed', 'saw'],
      },
    },
    regressions: { type: 'array', items: { type: 'string' } },
    new_findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          severity: { type: 'string', enum: ['P0', 'P1'] },
          time: { type: 'string' },
          problem: { type: 'string' },
          fix: { type: 'string' },
        },
        required: ['severity', 'time', 'problem', 'fix'],
      },
    },
    could_not_check: { type: 'array', items: { type: 'string' } },
  },
  required: ['verdict', 'items', 'regressions', 'new_findings'],
}

const out = { slug: f.slug, pass: N, asked: ITEMS.map(i => i.id) }

phase('Polish')
const built = await agent(polishBrief, { label: `polish${N}:${f.slug}`, phase: 'Polish', schema: DONE, model: MODELS.builder, effort: EFFORTS.builder })
out.built = built
if (!built) {
  log('polish: the builder returned nothing; no checker starts')
  out.stopped = 'builder'
  return out
}
// check all prints one `check <stage>: exit <n>` line per stage, then `check all: exit <n>` (the worst stage).
const gated = (code, quote) => code === 0 && /check all: exit 0/.test(quote || '')
if (!gated(built.gate_exit_code, built.gate_quote)) log(`polish: the builder's gate did not exit 0 (${built.gate_exit_code}); the gate runs again in the check`)

phase('Check')
// The gate writes proof files and the checkers only read the film and write their own frames, so they run side by side.
const [gate, ...got] = await parallel([
  () => agent(gateBrief, { label: `gate${N}:${f.slug}`, phase: 'Check', schema: GATE, model: MODELS.gate, effort: EFFORTS.gate }),
  ...LENSES.map(l => () =>
    agent(checkBrief(l, built), { label: `check${N}:${l.key}:${f.slug}`, phase: 'Check', schema: RULED, model: MODELS.checker, effort: EFFORTS.checker }).then(r => (r ? { key: l.key, ...r } : null))),
])
const checks = got.filter(Boolean)
if (checks.length < LENSES.length) log(`polish: only ${checks.length} of ${LENSES.length} checkers returned`)
out.gate = gate
out.checks = checks
// An item is fixed when every checker that returned says so; an item no checker ruled on is open.
const says = id => checks.map(c => (c.items.find(i => i.id === id) || {}).fixed)
out.fixed = ITEMS.filter(i => checks.length && says(i.id).every(v => v === true)).map(i => i.id)
out.open = ITEMS.filter(i => !out.fixed.includes(i.id)).map(i => i.id)
out.regressions = checks.flatMap(c => c.regressions.map(r => `${c.key}: ${r}`))
out.new_findings = checks.flatMap(c => c.new_findings.map(n => ({ key: c.key, ...n })))
// The gate agent's own run decides, never the builder's quote.
out.ok = checks.length === LENSES.length && checks.every(c => c.verdict === 'PASS') && Boolean(gate) && gated(gate.exit_code, gate.quote) && !out.open.length && !out.regressions.length && !out.new_findings.length
log(`polish ${N}: ${out.fixed.length}/${ITEMS.length} fixed, gate ${gate ? gate.exit_code : '?'}, ${out.regressions.length} regressions, ${out.new_findings.length} new findings, ${out.ok ? 'PASS' : 'FIX'}`)
return out
