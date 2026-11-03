# S-g13-steam-news-60s · Music-led news roundup
**Source:** @gigabit_million, https://x.com/gigabit_million/status/2104068536041959719 · our build: g13-steam-news-60s
**Use when:** "new releases news video", "60-second roundup", "top N things this week", "motion graphics news show", "what's new in {topic}"
**Defaults:** 60 s · 16:9 1920x1080 · 60 fps in the build (30 fps here) · music-only, no narration
**Spec:** family=music length=60 size=1920x1080 fps=30 audio=music kit=-

## The brief (reusable prompt)
Make a news-style video introducing {items released in this period}, from the viewer's point of view so the interesting points of each are clear, as an easy-to-watch motion graphics video about 60 seconds long. Facts (titles, dates, what each is) must come from real pages you fetch; list the sources. No key art or logos unless clearly licensed; describe each with type and abstract motion instead.

## Scene plan
120 BPM; 2-bar intro, six 4-bar stories, recap, end card.
| Time | Beat | What happens on screen |
|---|---|---|
| 0-4 | Intro | Show bug ("LAUNCH LOG · NEW ON STEAM" in the build, use a generic {show} name), dated header, headline count ("270+ new games in two days" in the build; a lower bound, label it as such) |
| 4-52 | Six stories, 8 s each | Per story: index, kicker ("The headliner", "The comeback"...), date chip, title, subtitle, credits, 3 tags, 3 numbered "why it's worth a look" lines at +1.65 / +3.05 / +4.45 s (each at least 3 s on screen), review meter at +5.75 s; abstract code-drawn visual explainer of the story's hook |
| 52-57 | Recap | Grid of all six, plus "Also out" ticker of five more |
| 57-60 | End card | Question ("Which one are you playing first?") and a sources and no-affiliation line |
Segment progress pips fill per story; a "JUST RELEASED" ticker runs along the bottom; an accent-coloured slanted wipe, beat-aligned, on every cut. Order alternates energy (action, cozy, action, cozy, immersive, builder).

## Look
- Palette: ink #090C14, ink2 #111726, text #F4F6FB, muted #9AA3B5, yellow #FFD23F; accents used in the build: #FF7EB6, #FF9F43, #FF4FD8, #6EE7B7 (per-story accent assignment not recorded).
- Type: Barlow Condensed (headlines, SemiBold to Black), Inter (body), JetBrains Mono (data); all SIL OFL. Mac substitutes: Helvetica Neue Condensed Bold or Arial Narrow Bold for headlines, SF Pro or Helvetica Neue for body, Menlo for data.
- Layout and texture: dark broadcast look, condensed headline, chips and tags, review meter bar, bottom ticker. Body copy was 30 px at 1080p.

## Motion
Cut wipe: slanted accent-colour panel sweeps across and holds full-frame for about 4 frames at 60 fps (about 2 frames at 30 fps), aligned to the beat. Lines slide in on ease_out_cubic; review bar fills on a rising sweep. Per-story hook visuals are pure functions of t, for example a jet silhouette banking through four parallax cloud layers with a HUD, a schedule board that fills then branches into five futures, 1,000 red units closing in with three shockwaves and a live KO counter that reaches 1000, notes that grow flowers on a staff, a striped accretion disk with a ring station and glitch slices, blueprint parts dropping into a hull with rising water.

## Audio
120 BPM, D-minor news-sport groove: kick, clap, hats, saw bass, supersaw stabs, pad. Lighter kit with bell arpeggios under the two cozy stories, war-drum fills under the musou story, disco open-hats under the horror story. A 4-note sting at every story, whooshes on every wipe, blips for each line, rising sweep for each review bar, plus per-story cues (lock tones, shockwave booms, one bell per note pitched to the staff, glitch stutters, clanks). Master about -14 LUFS (build measured -14.2 LUFS, peak -1.9 dBFS).

## Build notes
Fetch facts with web search and fetch (store pages and public APIs), keep a source list, and put the fetch date on every volatile number (review percentages drift). No third-party art: draw each hook in PIL with shapes. Pick items by objective criteria (most-reviewed or a platform "popular new" list) and say what you skipped and why (the build skipped mature-content and novelty titles). Keep one SCHEDULE for story starts so wipes, stings and text arrivals share it. Fictional show name only, and an explicit no-affiliation line.

## Pitfalls (from what went wrong in our build)
- Review numbers were a 2 Oct snapshot and go stale within days: label them with the date.
- One claim ("from the team behind ...") came from model knowledge, not the fetched page; only keep claims you can source.
- The jet silhouette was the least crafted shape; spend drawing effort on the headliner.
- "TIME ERR" glitch text briefly overlapped the station during three 0.2-0.3 s glitch hits.
- The shockwave story left its last 1.5 s sparse; add a closing element.
- A full-frame accent hold of about 4 frames per wipe can feel flashy; shorten it for sensitive viewers.
- Body copy at 30 px is small on a phone; use larger type for 9:16 or mobile.

## Style QA
- Every on-screen fact traces to a fetched source and every dated number shows its date.
- Each line is on screen at least 3 s.
- Wipes land on beats.
- Sources and no-affiliation line present on the end card.
