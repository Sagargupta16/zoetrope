# voice.py : offline narration (one cached TTS file per line, narration.json word times, word cues, voice-first slots),
# plus measuring voice files, sizing voiced sections in beats and ducking the music bed under speech (numpy + ffmpeg)
import difflib
import hashlib
import inspect
import json
import math
import os
import platform
import re
import shutil
import subprocess
import tempfile
import unicodedata
import wave
from pathlib import Path

import contract as C
import numpy as np

SR = 44100  # same rate as audio.py and synth.py; audio.master writes the final 48 kHz mix


def dec(path, af=None, ch=1, sr=SR):
    """Decode any audio file to float32 with ffmpeg, optionally through a filter chain af. -nostdin: without it a
    "q" waiting on stdin ended a 1800 s decode at 999 s with exit code 0 (seen 2026-10-28)."""
    cmd = (
        [C.find_ffmpeg() or "ffmpeg", "-nostdin", "-v", "error", "-i", path]
        + (["-af", af] if af else [])
        + ["-f", "f32le", "-ac", str(ch), "-ar", str(sr), "-"]
    )
    return np.frombuffer(
        subprocess.run(cmd, capture_output=True, check=True).stdout, np.float32
    )


def span(y, sr=SR):
    """Speech start and end in seconds: 10 ms RMS windows within 40 dB of the loudest one."""
    w = sr // 100
    m = len(y) // w
    db = 20 * np.log10(np.sqrt((y[: m * w].reshape(m, w) ** 2).mean(1)) + 1e-9)
    on = np.where(db > db.max() - 40)[0]
    return on[0] * 0.01, (on[-1] + 1) * 0.01


def section_beats(speech_len, bpm, hold=0.5, lead=0.06, tempo=1.04, min_beats=2):
    """Whole, even number of beats a voiced section needs (mixing.md, voice placement)."""
    need = lead + speech_len / tempo + hold
    return max(min_beats, 2 * math.ceil(need / (60 / bpm) / 2))


def duck_mix(bed, voice, sr=SR, depth_db=8):
    """Voice over the bed: bed at about -18 dBFS RMS, ducked depth_db while the voice speaks (fast attack, slow release)."""
    n = max(len(bed), len(voice))
    bed = np.pad(np.asarray(bed, float), (0, n - len(bed)))
    voice = np.pad(np.asarray(voice, float), (0, n - len(voice)))
    voice = voice * 0.89 / (np.abs(voice).max() + 1e-9)  # voice peak 0.89
    w = sr // 100
    m = n // w  # 10 ms windows
    act = (
        np.sqrt((voice[: m * w].reshape(m, w) ** 2).mean(1)) > 10 ** (-38 / 20)
    ).astype(float)  # voice gate -38 dB
    env = np.zeros(m)
    g = 0.0
    for i in range(m):  # fast attack, slow release
        c = 0.01 / (0.04 if act[i] > g else 0.30)
        g += (act[i] - g) * min(1, c * 3)
        env[i] = g
    env = np.repeat(env, w)
    env = np.concatenate([env, np.full(n - len(env), env[-1])])
    bed = (
        bed / (np.sqrt((bed**2).mean()) + 1e-9) * 10 ** (-18 / 20)
    )  # bed about -18 dBFS RMS before ducking
    return (
        bed * 10 ** (-depth_db * env / 20) + voice * 1.26
    )  # music ducks depth_db while voice speaks


# ---- narration (Z05): one cached file per line, laid out by decoded sample count ----

# Tunables, not measurements of ours. The trim is explainroo's (10 ms windows, a peak above about -48 dBFS counts as
# speech, 40 ms kept each side); change them if a line loses a breath or keeps a click.
TRIM_DB = -48.0
TRIM_KEEP = 0.04
TRIM_WIN = 0.01
# rule "ours" (our own design): silence before and after the speech in a slot
LEAD, TAIL = 0.35, 0.7
# rule "showtime": silence after each line, and after the last line
GAP, END_TAIL = 0.4, 0.8
WORD_MIN = 0.02  # shortest word when an engine reports only word starts
# [pause], [pause 300ms], [pause 1.5s] inside a line: exact silence from the end of one part's speech to the start of
# the next. A bare [pause] is 0.35 s, VoiceStudio's default for its marker; PAUSE_MAX is our cap.
PAUSE = re.compile(r"\[\s*pause(?:\s+(\d+(?:\.\d+)?)\s*(ms|s))?\s*\]", re.IGNORECASE)
TAG = re.compile(
    r"\[[^\]]*\]"
)  # any other bracket tag: an engine would say it as words
PAUSE_DEFAULT, PAUSE_MAX = 0.35, 5.0
# a line given fit= is spoken faster, never slower, until its speech fits its slot. 1.2 is our cap, not a measured
# limit (VoiceStudio's dubbing allows up to 1.5 by default): listen to a line spoken near it.
FIT_FAST = 1.2
FIT_ROUNDS = 6  # SAPI's rate moves in whole steps, so its speed can take a few rounds to change at all
# showtime measured Kokoro's duration-grid times about 50 ms late against acoustic onsets and a CTC aligner (6 voices,
# 3 speeds) and its code moves them 50 ms earlier, as _phoneme_words does; its comment words the direction the other
# way round. Measured by us on 2026-10-29 (onset_offsets, after that 50 ms): af_heart, 24 words that open a line or
# follow a pause on 12 lines, median +22 ms late (p10 -11, p90 +56; vowel onsets run later, unvoiced consonants read
# early because the onset check waits for voicing); af_bella, am_michael and bf_emma medians +19 to +45 ms on 7 to 10
# words each. So 70 ms: the same 24 words then read median +2 ms (p10 -31, p90 +51).
KOKORO_LAG = 0.07
# The narration voice, picked by ear from voice_samples.py on 2026-10-29: synthesize uses it when no engine is
# named. Another voice is named with engine= and voice=; sapi stays the timing fallback.
NARRATOR_ENGINE, NARRATOR_VOICE = "kokoro-ts", "af_heart"
# bump when the sidecar format changes; engine code, programs, pins and model files are hashed into the key anyway
CACHE_VERSION = 2
# model and voice files, one folder per engine; never inside the repo
VOICE_DIR = Path(
    os.environ.get("ZOETROPE_VOICES") or Path.home() / ".cache" / "zoetrope" / "voices"
)


def synthesize(
    lines,
    engine=NARRATOR_ENGINE,
    voice=None,
    speed=1.0,
    folder="narration",
    fps=30,
    rule="ours",
    profile=None,
    lexicon=None,
):
    """Narrate lines (strings, or dicts with id, text and an optional fit) offline and lay them out on one timeline.
    Each part of a line is cached as folder/<key>.wav, key = sha256 of engine, model id (every model file it reads),
    code id (the engine's code, its bridge or worker program and package pins), voice, speed and the text spoken: per
    part, as showtime caches per line. A re-run synthesizes nothing and render needs no engine. A new file is checked
    (speech found, word times inside it) before it is cached; a bad one is deleted and named. Writes
    folder/narration.wav (mono, 44.1 kHz, each line in its slot) and folder/narration.json, and returns the
    narration dict. Slots end on whole frames when fps is set; rule and profile size them (see slot). With no engine
    named it speaks as the narrator (NARRATOR_ENGINE, NARRATOR_VOICE).
    lexicon {word: respelling} makes the engine say a word as the respelling reads ("Kalchar": "Kul char"), while
    captions, holds and word_cue keep the script's word. A line may hold [pause], [pause 300ms] or [pause 1.5s]: its
    parts are spoken apart and joined with exactly that silence between their speech. A line {id, text, fit} gets a
    slot of exactly fit seconds; speech that overruns it is spoken faster, up to FIT_FAST, and a line that would need
    more raises with how many words to cut."""
    eng = get_engine(engine)
    eng.require()
    if speed <= 0 or rule not in ("ours", "showtime"):
        raise ValueError(
            f"need speed above 0 and rule 'ours' or 'showtime', got {speed}, {rule!r}"
        )
    items = _lines(lines, _lexicon(lexicon))
    voice = voice or eng.default_voice()
    if voice is None:
        raise ValueError(
            f"{engine}: name a voice; the user picks it from voice_samples.py. Voices here: "
            f"{', '.join(eng.voices()) or 'none downloaded'}"
        )
    if voice not in eng.voices():
        close = difflib.get_close_matches(voice, eng.voices(), n=3, cutoff=0.4)
        raise ValueError(
            f"{engine}: no voice {voice!r}; close: {', '.join(close) or 'none'}"
        )
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    job = {
        "eng": eng,
        "model": eng.model_id(voice),
        "code": eng.code_id(),
        "voice": voice,
        "folder": folder,
        "units": {},
    }
    speeds = {ln["id"]: speed for ln in items}
    made = set()
    for _ in range(FIT_ROUNDS):
        made |= _make(job, items, speeds)
        refit = _refit(job, items, speeds, rule, profile)
        if not refit:
            break
        speeds |= refit
    else:
        raise ValueError(
            f"fit did not settle in {FIT_ROUNDS} rounds on {', '.join(refit)}: give those lines more time"
        )
    narr = _layout(job, items, speeds, speed, fps, rule, profile, lexicon)
    (folder / "narration.json").write_text(json.dumps(narr, indent=1), encoding="utf-8")
    untimed = [ln["id"] for ln in narr["lines"] if ln["timing"] == "none"]
    partial = [ln["id"] for ln in narr["lines"] if ln["timing"] == "partial"]
    final = {_part_key(job, ln, p, speeds) for ln in items for p in ln["parts"]}
    tries = len(made - final)
    print(
        f"voice: {engine} ({voice}): synthesized {len(made & final)} of {len(final)} parts "
        f"({len(items)} lines), {len(final - made)} from cache"
        + (f", {tries} fit tries" if tries else "")
        + f" -> {folder / 'narration.json'} ({narr['duration']:.2f} s)"
    )
    print(
        f"voice: check what it says with: qa.py speech {folder / 'narration.json'} (Q806)"
    )
    if untimed:
        print(
            f"voice: {engine} gives no word times, so words[] is empty on {', '.join(untimed)} and word_cue "
            f"cannot use them (sapi and kokoro-ts give word times)"
        )
    if partial:
        print(
            f"voice: some word times on {', '.join(partial)} are shared out, not heard (est: the engine read "
            f"several words as one, such as a number); word_cue refuses those unless est=True"
        )
    return narr


def _lines(lines, lex=None):
    """[{id, script, text, fit, parts}] from strings (ids L01, L02, ...), dicts {id, text[, fit]} or (id, text) pairs.
    text is the script without pause markers: what captions, holds and word_cue read. Each part {spoken, own, pause}
    is the text between two markers as the engine says it (lexicon respellings in), the script word each spoken word
    says, and the silence after it."""
    out = []
    for i, ln in enumerate(lines):
        fit = None
        if isinstance(ln, str):
            lid, script = f"L{i + 1:02d}", ln
        elif isinstance(ln, dict):
            lid, script = ln.get("id") or f"L{i + 1:02d}", ln["text"]
            fit = ln.get("fit")
        else:
            lid, script = ln
        lid, script = str(lid), str(script).strip()
        if not script:
            raise ValueError(f"line {lid} has no text")
        if fit is not None and not float(fit) > 0:
            raise ValueError(f"line {lid}: fit is seconds above 0, got {fit!r}")
        out.append(
            {
                "id": lid,
                "script": script,
                "fit": None if fit is None else float(fit),
            }
            | _parts(lid, script, lex or {})
        )
    ids = [ln["id"] for ln in out]
    if not out or len(set(ids)) != len(ids):
        raise ValueError(f"need at least one line and unique ids, got {ids}")
    return out


def _parts(lid, script, lex):
    """{text, parts} of one line: split at its pause markers, each piece respelled from the lexicon."""
    bits, pauses, at = [], [], 0
    for m in PAUSE.finditer(script):
        bits.append(script[at : m.start()])
        at = m.end()
        unit = 1 if (m.group(2) or "s").lower() == "s" else 1000
        n = PAUSE_DEFAULT if m.group(1) is None else float(m.group(1)) / unit
        if not 0 < n <= PAUSE_MAX:
            raise ValueError(f"{lid}: {m.group()} is outside 0 to {PAUSE_MAX:g} s")
        pauses.append(n)
    bits = [" ".join(b.split()) for b in bits + [script[at:]]]
    for b in bits:
        tag = TAG.search(b)
        if tag:
            raise ValueError(
                f"{lid}: {tag.group()} is not a marker voice.py reads ([pause], [pause 300ms], [pause 1.5s]); "
                f"the engine would say it as words"
            )
    if not all(_words(b) for b in bits):
        raise ValueError(
            f"{lid}: a pause marker at the start or end of the line, or two in a row: a pause goes between words "
            f"(the slot already holds silence before and after a line)"
        )
    parts, k = [], 0
    for b, p in zip(bits, pauses + [0.0]):
        spoken, own = _respell(lid, b, lex, k)
        parts.append({"spoken": spoken, "own": own, "pause": p})
        k += len(_words(b))
    return {"text": " ".join(bits), "parts": parts}


def _lexicon(lexicon):
    """{word as word_cue compares it: respelling} from {word: respelling}."""
    lex = {}
    for w, say in (lexicon or {}).items():
        k, say = _norm(w), " ".join(str(say).split())
        if not k or len(str(w).split()) != 1 or not _words(say) or TAG.search(say):
            raise ValueError(
                f"lexicon {w!r}: {say!r}: each entry is one word and the respelling the engine reads for it"
            )
        lex[k] = say
    return lex


def _respell(lid, text, lex, base=0):
    """(spoken, own): text with every word the lexicon names said as its respelling (a trailing 's kept), and for each
    spoken word the index (from base) of the script word it says."""
    out, own, at = [], [], 0
    for i, (w, a, b) in enumerate(_word_spans(text)):
        k = _norm(w)
        tail = "'s" if k.endswith("'s") and k[:-2] in lex and k not in lex else ""
        say = lex.get(k[: len(k) - len(tail)])
        if say:
            out += [text[at:a], say + tail]
            at = b
        own += [base + i] * (len(_words(say + tail)) if say else 1)
    spoken = "".join(out) + text[at:]
    if len(_words(spoken)) != len(own):
        raise ValueError(
            f"{lid}: the respelled text {spoken!r} does not split into the words it says: check the lexicon entries"
        )
    return spoken, own


def _part_key(job, ln, part, speeds):
    return _key(
        job["eng"].name,
        job["model"],
        job["code"],
        job["voice"],
        speeds[ln["id"]],
        part["spoken"],
    )


def _make(job, items, speeds):
    """Synthesize and cache every part not cached yet, one engine run per speed; returns the keys made. A part said
    twice is made once."""
    eng, folder = job["eng"], job["folder"]
    todo = {}  # key -> (spoken, speed, line id)
    for ln in items:
        for p in ln["parts"]:
            k = _part_key(job, ln, p, speeds)
            if not _cached(folder, k):
                todo.setdefault(k, (p["spoken"], speeds[ln["id"]], ln["id"]))
    bad = []
    for s in sorted({v[1] for v in todo.values()}):
        ks = [k for k, v in todo.items() if v[1] == s]
        got = eng.synth(
            [todo[k][0] for k in ks], job["voice"], s, [folder / f"{k}.wav" for k in ks]
        )
        for k, raw in zip(ks, got):
            spoken, _, lid = todo[k]
            wav = folder / f"{k}.wav"
            try:  # check before caching: a bad file left in the cache would fail every later run
                _timed(eng, raw, spoken, dec(str(wav)))
            except (ValueError, KeyError, subprocess.CalledProcessError) as e:
                wav.unlink(missing_ok=True)
                bad.append(f"{lid} ({wav}, deleted, not cached): {e}")
                continue
            side = {
                "v": CACHE_VERSION,
                "engine": eng.name,
                "model": job["model"],
                "code": job["code"],
                "voice": job["voice"],
                "speed": s,
                "text": spoken,
                "raw": raw,  # the engine's own timing data, turned into words at every layout
            }
            # written last and whole (temp file, then rename): a part counts as cached only once this exists
            tmp = folder / f"{k}.json.tmp"
            tmp.write_text(json.dumps(side, indent=1), encoding="utf-8")
            os.replace(tmp, folder / f"{k}.json")
    if bad:
        raise ValueError(f"{eng.name} wrote unusable audio: {'; '.join(bad)}")
    return set(todo)


def _refit(job, items, speeds, rule, profile):
    """{line id: new speed} for each line with fit whose speech overruns its slot. Raises when the reading hold of its
    words is over fit, or when it would need a speed over FIT_FAST, with about how many words to cut."""
    out = {}
    for i, ln in enumerate(items):
        if not ln["fit"]:
            continue
        rel = _assemble(job, ln, speeds)[1]
        if rule == "ours":
            hold = _hold(ln["text"], profile)
            if hold > ln["fit"] + 1e-6:
                raise ValueError(
                    f"{ln['id']}: fit {ln['fit']:g} s is under the reading hold of its words ({hold:.2f} s, profile "
                    f"{profile or 'display'}): give it more time or fewer words"
                )
        need = _need(rel, rule, last=i == len(items) - 1)
        if need <= ln["fit"] + 1e-6:
            continue
        pauses = sum(p["pause"] for p in ln["parts"][:-1])
        spoken = rel["speech_end"] - rel["speech_start"]
        room = ln["fit"] - (need - spoken) - pauses  # what the voiced speech may take
        s = speeds[ln["id"]]
        new = (
            math.ceil(s * (spoken - pauses) / room * 101) / 100
            if room > 0
            else math.inf
        )
        if new > FIT_FAST:
            n = len(_words(ln["text"]))
            cut = math.ceil(n * (1 - FIT_FAST / new))
            raise ValueError(
                f"{ln['id']}: {spoken:.2f} s of speech at speed {s:g} would need speed {new:.2f} to fit "
                f"{ln['fit']:g} s (FIT_FAST {FIT_FAST:g}): cut about {cut} of its {n} words, or give it more time"
            )
        out[ln["id"]] = max(new, round(s + 0.01, 2))
    return out


def _cached(folder, k):
    """True when line k's file is there and its sidecar is whole and of this CACHE_VERSION."""
    try:
        side = json.loads((folder / f"{k}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return side.get("v") == CACHE_VERSION and (folder / f"{k}.wav").exists()


def _key(engine, model, code, voice, speed, text):
    return hashlib.sha256(
        json.dumps(
            [CACHE_VERSION, engine, model, code, voice, float(speed), text]
        ).encode()
    ).hexdigest()


def _voiced(y, sr=SR, db=None, win=None):
    """(mask, w): True for each win-long window whose peak is above db dBFS, and the window length in samples.
    None reads the TRIM_ tunable when called, so setting voice.TRIM_DB in a build script takes effect."""
    db, win = TRIM_DB if db is None else db, TRIM_WIN if win is None else win
    w = max(1, C.sample_of(win, sr))
    m = len(y) // w
    pk = np.abs(y[: m * w]).reshape(m, w).max(1)
    return pk > 10 ** (db / 20), w


def trim(y, sr=SR, db=None, keep=None, win=None):
    """(c0, c1, s0, s1) in samples: the speech [s0, s1) from the first to the last voiced window, and the clip [c0, c1)
    that keeps `keep` seconds each side (inside the file; None: TRIM_KEEP). A silent file raises: the engine wrote
    nothing to hear."""
    on, w = _voiced(y, sr, db, win)
    idx = np.flatnonzero(on)
    if not len(idx):
        raise ValueError(
            f"no speech above {TRIM_DB if db is None else db} dBFS: the engine wrote silence"
        )
    s0, s1 = int(idx[0]) * w, (int(idx[-1]) + 1) * w
    k = C.sample_of(TRIM_KEEP if keep is None else keep, sr)
    return max(0, s0 - k), min(len(y), s1 + k), s0, s1


def _timed(eng, raw, text, y):
    """(trim bounds, words in seconds of the engine's file or None) for one line. Raises when the file holds no
    speech or a word starts past its end (an engine clock that runs fast, as SAPI's does at 22.05 kHz)."""
    bounds = trim(y)
    words = eng.words(raw, text, bounds[3] / SR)
    if words and max(w["start"] for w in words) > len(y) / SR + 0.05:
        raise ValueError(
            f"word times run past the end of the audio ({len(y) / SR:.2f} s): the engine's clock is off"
        )
    return bounds, words


def slot(line, rule="ours", last=False, profile=None):
    """Seconds a narrated line holds the screen; line has text, start, end, speech_start and speech_end.
    "ours" (our own design, no source behind it): max(LEAD + spoken + TAIL, qa.min_hold(text, profile)), so the voice
    gets 0.35 s before and 0.7 s after it and a caption of the same words still meets its reading hold (profile as
    in qa.HOLD_PROFILES; None is display). "showtime": the clip plus GAP (0.4 s), plus END_TAIL (0.8 s) on the last
    line; a slot then runs from one line's start to the next line's start, pause included."""
    need = _need(line, rule, last)
    return need if rule == "showtime" else max(need, _hold(line["text"], profile))


def _need(line, rule="ours", last=False):
    """The slot the speech itself takes, before any reading hold: LEAD + spoken + TAIL, or showtime's clip + gap."""
    if rule == "showtime":
        return (line["end"] - line["start"]) + (END_TAIL if last else GAP)
    if rule != "ours":
        raise ValueError(f"rule is 'ours' or 'showtime', got {rule!r}")
    return LEAD + (line["speech_end"] - line["speech_start"]) + TAIL


def _hold(text, profile=None):
    """qa.min_hold of the line: since Z15 it takes the text and a card profile; the 2.1 rule took a word count."""
    import qa  # here, not at the top: qa pulls in the gates, which narration does not need

    if "profile" in inspect.signature(qa.min_hold).parameters:
        return qa.min_hold(text, profile)
    return qa.min_hold(len(text.split()))


def _unit(job, lid, k, spoken):
    """(y, (c0, c1, s0, s1), words) of one cached part: its samples, trim bounds and word times in seconds of its
    file (ends filled in). Decoded once per synthesize call."""
    if k not in job["units"]:
        path = job["folder"] / f"{k}.wav"
        try:
            y = dec(str(path))
            side = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
            bounds, words = _timed(job["eng"], side["raw"], spoken, y)
        except (ValueError, KeyError, subprocess.CalledProcessError) as e:
            raise ValueError(f"{lid} ({path}): {e}") from None
        if words:
            _ends(y, words, bounds[3])
        job["units"][k] = (y, bounds, words)
    return job["units"][k]


def _assemble(job, ln, speeds):
    """One line as a clip: its parts with exactly their pause between one part's speech end and the next one's speech
    start. Returns (clip, rel, words, placed): rel has the times slot() reads, words are the script's words in seconds
    of the clip (None when the engine gives no word times), placed is [(key, c0, c1, at)] with at in clip samples."""
    placed, heard, timed = [], [], True
    first = end = gap = (
        0  # clip samples: speech start of part 1, speech end so far; the pause that follows it
    )
    for i, p in enumerate(ln["parts"]):
        k = _part_key(job, ln, p, speeds)
        _, (c0, c1, s0, s1), ws = _unit(job, ln["id"], k, p["spoken"])
        at = max(0, end + gap - (s0 - c0)) if i else 0
        first = first if i else s0 - c0
        placed.append((k, c0, c1, at))
        timed = timed and ws is not None
        if ws:
            off = (at - c0) / SR
            heard += [
                w | {"start": w["start"] + off, "end": w["end"] + off} for w in ws
            ]
        end, gap = at + (s1 - c0), C.sample_of(p["pause"], SR)
    clip = np.zeros(max(at + c1 - c0 for _, c0, c1, at in placed), np.float32)
    for k, c0, c1, at in placed:
        clip[at : at + c1 - c0] += job["units"][k][0][c0:c1]
    rel = {
        "text": ln["text"],
        "start": 0.0,
        "end": len(clip) / SR,
        "speech_start": first / SR,
        "speech_end": end / SR,
    }
    words = None
    if timed:
        own = [o for p in ln["parts"] for o in p["own"]]
        words = []
        for j, w in enumerate(_words(ln["text"])):
            mine = [h for h, o in zip(heard, own) if o == j]
            words.append(
                {
                    "w": w,
                    "start": min(h["start"] for h in mine),
                    "end": max(h["end"] for h in mine),
                }
                | ({"est": True} if any(h.get("est") for h in mine) else {})
            )
    return clip, rel, words, placed


def _layout(job, items, speeds, speed, fps, rule, profile, lexicon):
    """Assemble each line from its cached parts, size its slot (fit when given) and place it by integer sample
    counts; write narration.wav. Word times are rebuilt here on every run, so a fix to that code needs no new audio."""
    eng, chunks, out, pos, frames = job["eng"], [], [], 0, 0
    for i, ln in enumerate(items):
        clip, rel, words, placed = _assemble(job, ln, speeds)
        need = ln["fit"] or slot(rel, rule, last=i == len(items) - 1, profile=profile)
        if fps:
            frames += math.ceil(need * fps - 1e-6)
            end = C.frame_sample(frames, fps, SR)
        else:
            end = pos + C.sample_of(need, SR)
        first = C.sample_of(rel["speech_start"], SR)
        pre = C.sample_of(LEAD, SR) - first if rule == "ours" else 0
        at = pos + max(0, pre)  # first sample of the clip on the timeline
        post = end - at - len(clip)
        chunks += [np.zeros(at - pos, np.float32), clip, np.zeros(post, np.float32)]
        if words:
            lo, hi = at / SR, (at + len(clip)) / SR
            words = [
                w
                | {
                    "start": round(min(max(w["start"] + lo, lo), hi), 3),
                    "end": round(min(max(w["end"] + lo, lo), hi), 3),
                }
                for w in words
            ]
        out.append(
            {
                "id": ln["id"],
                "text": ln["text"],
                "script": ln["script"],
                "spoken": [p["spoken"] for p in ln["parts"]],
                "pauses": [p["pause"] for p in ln["parts"][:-1]],
                "speed": speeds[ln["id"]],
                "fit": ln["fit"],
                "start": round(at / SR, 6),
                "end": round((at + len(clip)) / SR, 6),
                "speech_start": round(at / SR + rel["speech_start"], 6),
                "speech_end": round(at / SR + rel["speech_end"], 6),
                "slot": {
                    "start": round(pos / SR, 6),
                    "end": round(end / SR, 6),
                    "duration": round((end - pos) / SR, 6),
                },
                # each part's cached file, the samples of it (decoded to 44.1 kHz mono) placed, and where they start
                "parts": [
                    {
                        "file": f"{k}.wav",
                        "clip": [c0, c1],
                        "start": round((at + a) / SR, 6),
                    }
                    for k, c0, c1, a in placed
                ],
                "timing": "none"
                if words is None
                else "partial"
                if any(w.get("est") for w in words)
                else "engine",
                "words": words or [],
            }
        )
        pos = end
    y = np.concatenate(chunks)
    _write_wav(job["folder"] / "narration.wav", y)
    return {
        "engine": eng.name,
        "model": job["model"],
        "voice": job["voice"],
        "lang": eng.lang(job["voice"]),
        "speed": speed,
        "fit_fast": FIT_FAST,
        "lexicon": dict(lexicon or {}),
        "sr": SR,
        "fps": fps,
        "rule": rule,
        "profile": profile,
        "trim": {"db": TRIM_DB, "keep": TRIM_KEEP, "win": TRIM_WIN},
        "duration": round(len(y) / SR, 6),
        "samples": len(y),
        "file": "narration.wav",
        "lines": out,
    }


def _ends(y, words, s1, sr=SR):
    """Fill missing word ends (SAPI reports starts only): the end of the last voiced window before the next word
    starts, or before the speech ends, so a pause after a word is not counted as the word."""
    on, w = _voiced(y, sr)
    for i, wd in enumerate(words):
        if wd.get("end") is not None:
            continue
        nxt = words[i + 1]["start"] if i + 1 < len(words) else s1 / sr
        a, b = C.sample_of(wd["start"], sr) // w, C.sample_of(nxt, sr) // w
        hit = np.flatnonzero(on[a:b])
        end = (a + int(hit[-1]) + 1) * w / sr if len(hit) else nxt
        wd["end"] = max(wd["start"], min(max(end, wd["start"] + WORD_MIN), nxt))


def _write_wav(path, y, sr=SR):
    """Mono 16-bit PCM."""
    pcm = np.round(np.clip(y, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(pcm.tobytes())


def load_narration(narration):
    """A narration dict from a narration.json path, the dict itself, or a bare list of lines."""
    if isinstance(narration, (str, Path)):
        narration = json.loads(Path(narration).read_text(encoding="utf-8"))
    return {"lines": narration} if isinstance(narration, list) else narration


def _runs(seq, key):
    """Indexes where the list `key` starts in the list `seq` (none for an empty key)."""
    n = len(key)
    return [i for i in range(len(seq) - n + 1) if n and seq[i : i + n] == key]


def _norm(w):
    """A word as word_cue compares it: lower case, curly quotes as ', accents and other punctuation dropped. Letters,
    digits and marks of any script stay, so a Hindi word keeps its vowel signs (only marks that combine, such as
    accents and the virama, go)."""
    w = unicodedata.normalize(
        "NFKD", w.lower().replace("\u2018", "'").replace("\u2019", "'")
    )
    keep = (
        ch
        for ch in w
        if not unicodedata.combining(ch)
        and (ch == "'" or unicodedata.category(ch)[0] in "LNM")
    )
    return "".join(keep).strip("'")


def word_cue(narration, word, n=1, est=False):
    """Start in seconds of the n-th spoken `word`, or of a phrase's first word ("Vatican City"), in line order; case,
    punctuation, curly quotes and accents are ignored. Fails loudly with the closest words when it is not there
    (explainroo's cue), and on a time that was shared out rather than heard (est) unless est=True. Snap it with
    contract.snap before using it as a cue."""
    if n < 1:
        raise ValueError(f"word_cue: n counts occurrences from 1, got {n}")
    lines = load_narration(narration)["lines"]
    key = [k for k in (_norm(t) for t in str(word).split()) if k]
    flat = [w for ln in lines for w in ln["words"]]
    seen = [_norm(w["w"]) for w in flat]
    hits = _runs(seen, key)
    if len(hits) >= n:
        w = flat[hits[n - 1]]
        if w.get("est") and not est:
            raise ValueError(
                f"word_cue: {word!r} (occurrence {n}) has a time shared out between its neighbours, not heard "
                f"({w['start']} s; the engine read it inside a longer token); pass est=True to use it, or cue a word "
                f"it says alone"
            )
        return w["start"]
    untimed = [
        ln["id"]
        for ln in lines
        if not ln["words"] and _runs([_norm(t) for t in _words(ln["text"])], key)
    ]
    if untimed:
        raise ValueError(
            f"word_cue: {word!r} is in {', '.join(untimed)}, which has no word times (its engine gives none); "
            f"use sapi or kokoro-ts for word cues, or cue the line start"
        )
    close = difflib.get_close_matches(" ".join(key), sorted(set(seen)), n=5, cutoff=0.6)
    raise ValueError(
        f"word_cue: {word!r} (occurrence {n}) is not in the narration ({len(hits)} found); "
        f"close words: {', '.join(close) or 'none'}"
    )


def onset_offsets(narration, folder=None, gap=0.1):
    """[(line id, word, ms)] for each heard word that opens a line or follows a pause over `gap` s: its start minus
    the first voiced window of narration.wav from 50 ms before it. Near 0 when an engine's word clock is right; run
    it on an engine's first real narration (KOKORO_LAG was set from it on 2026-10-29)."""
    narr = load_narration(narration)
    if folder is None:
        folder = Path(narration).parent if isinstance(narration, (str, Path)) else "."
    y = dec(str(Path(folder, narr.get("file", "narration.wav"))))
    on, w = _voiced(y)
    out = []
    for ln in narr["lines"]:
        ws = ln["words"]
        for i, wd in enumerate(ws):
            if wd.get("est") or (i and wd["start"] - ws[i - 1]["end"] <= gap):
                continue
            k = C.sample_of(max(0.0, wd["start"] - 0.05), SR) // w
            hit = np.flatnonzero(on[k:])
            if len(hit):
                ms = (wd["start"] - (k + int(hit[0])) * w / SR) * 1000
                out.append((ln["id"], wd["w"], round(ms)))
    return out


def _word_spans(text):
    """[(word, first char, end char)]: the script's words with outer punctuation and symbols removed, and where they
    sit. Only punctuation and symbols are taken off, so a Hindi word keeps the vowel sign it ends on."""
    out = []
    for m in re.finditer(r"\S+", text):
        tok, a, b = m.group(), 0, len(m.group())
        while a < b and unicodedata.category(tok[a])[0] in "PS":
            a += 1
        while b > a and unicodedata.category(tok[b - 1])[0] in "PS":
            b -= 1
        if a < b:
            out.append((tok[a:b], m.start() + a, m.start() + b))
    return out


def _words(text):
    """The script's words with outer punctuation removed: what words[] lists."""
    return [w for w, _, _ in _word_spans(text)]


def _sapi_words(events, text, total):
    """Script words timed from SAPI's word events {w, start, char, n}. SAPI says a number, a date or a price as several
    words and reports each with the span of the text token it read, and a token can cover more than one script word
    ("In 2026", "3:45 pm"). So events are grouped by span and each group goes to the script words it overlaps: one
    word takes the group's first event; in a group that covers several, each later word takes the event at its share
    of the group's characters, marked est. A word no event reached shares out the gap around it (est)."""
    spans = _word_spans(text)
    groups = {}
    for e in sorted(events, key=lambda e: e["start"]):
        groups.setdefault((e["char"], e["n"]), []).append(e["start"])
    out = [{"w": w, "start": None, "end": None} for w, _, _ in spans]
    for (c, n), starts in sorted(groups.items(), key=lambda g: g[1][0]):
        cover = [i for i, (_, a, b) in enumerate(spans) if a < c + n and c < b]
        size = [spans[i][2] - spans[i][1] for i in cover]
        prev = -1
        for j, i in enumerate(cover):
            k = max(prev + 1, round(len(starts) * sum(size[:j]) / sum(size)))
            prev = k
            if out[i]["start"] is None and k < len(starts):
                out[i]["start"] = starts[k]
                if j:
                    out[i]["est"] = True
    i = 0
    # words no event reached: spread between the timed starts around them
    while i < len(out):
        if out[i]["start"] is not None:
            i += 1
            continue
        j = i
        while j < len(out) and out[j]["start"] is None:
            j += 1
        lo = out[i - 1]["start"] if i else 0.0
        hi = out[j]["start"] if j < len(out) else total
        for k in range(i, j):
            out[k].update(start=lo + (k - i + 1) * (hi - lo) / (j - i + 1), est=True)
        i = j
    return out


def _letter(ch):
    # IPA stress and length marks (U+02C8, U+02CC, U+02D0) count as letters to Python but are not sounds
    return ch.isalpha() and ch not in "\u02c8\u02cc\u02d0"


def _phoneme_words(phonemes, word_phonemes, words, total, lag=None):
    """Word times from per-phoneme times [(phoneme, start, end)] (kokoro-ts). The line's phonemes split at spaces
    into chunks, and _owners gives each letter its word: espeak-ng merges some words in context ("of the" is one
    chunk) and splits others ("A4" is two), so chunks and words need not pair up. Times move `lag` (None:
    KOKORO_LAG) earlier; a word left with no letter shares its neighbours' gap and is marked est."""
    lag = KOKORO_LAG if lag is None else lag
    chunks, cur = [], []
    for ch, a, b in phonemes:
        if ch.isspace():
            chunks.append(cur)
            cur = []
        elif _letter(ch):
            cur.append((ch, a, b))
    chunks = [c for c in chunks + [cur] if c]
    owners = _owners(chunks, word_phonemes, len(words))
    spans = {}
    for c, own in zip(chunks, owners):
        for (_, a, b), o in zip(c, own):
            lo, hi = spans.get(o, (a, b))
            spans[o] = (min(lo, a), max(hi, b))
    out = [
        {
            "w": w,
            "start": max(0.0, spans[i][0] - lag),
            "end": max(0.0, spans[i][1] - lag),
        }
        if i in spans
        else {"w": w, "start": None, "end": None}
        for i, w in enumerate(words)
    ]
    i = 0
    while i < len(out):  # interpolate the words that got no letter
        if out[i]["start"] is not None:
            i += 1
            continue
        j = i
        while j < len(out) and out[j]["start"] is None:
            j += 1
        lo = out[i - 1]["end"] if i else 0.0
        hi = out[j]["start"] if j < len(out) else total
        step = max(0.0, hi - lo) / (j - i)
        for k in range(i, j):
            out[k].update(
                start=lo + (k - i) * step, end=lo + (k - i + 1) * step, est=True
            )
        i = j
    return out


def _owners(chunks, word_phonemes, n):
    """Word index of every letter of every chunk. The letters are matched (difflib) against each word phonemized
    alone; an unmatched letter takes the owner before it in its chunk (after it, at the chunk start); a chunk with
    no match at all (context "a" is not the "a" said alone) goes to the first word between its neighbours that has
    no letter yet, else to the word before it."""
    ref = [(ch, i) for i, ph in enumerate(word_phonemes) for ch in ph if _letter(ch)]
    flat = [ch for c in chunks for ch, _, _ in c]
    own = [None] * len(flat)
    sm = difflib.SequenceMatcher(None, flat, [ch for ch, _ in ref], autojunk=False)
    for a, b, size in sm.get_matching_blocks():
        own[a : a + size] = [i for _, i in ref[b : b + size]]
    out, k = [], 0
    for c in chunks:
        out.append(own[k : k + len(c)])
        k += len(c)
    taken = {o for c in out for o in c if o is not None}
    prev = -1
    for ci, c in enumerate(out):
        hits = [o for o in c if o is not None]
        if hits:
            last = hits[0]
            for j, o in enumerate(c):
                last = last if o is None else o
                c[j] = last
        else:
            nxt = next((o for cc in out[ci + 1 :] for o in cc if o is not None), n)
            free = [i for i in range(prev + 1, nxt) if i not in taken]
            o = free[0] if free else max(prev, 0)
            taken.add(o)
            out[ci] = [o] * len(c)
        prev = max(prev, max(out[ci]))
    return out


# ---- engines: one small interface, so synthesize does not care which one speaks ----


class Engine:
    """missing() lists what is not installed or downloaded (empty when ready), voices() the voice names here,
    model_id(voice) every model file that voice reads (hashed), synth(texts, voice, speed, paths) writes one WAV per
    text and returns each one's raw timing data (JSON-ready, or None), and words(raw, text, total) turns that into
    word times [{w, start, end}] in seconds of the file, or None when the engine gives none. code_id() hashes what
    makes the file, so editing it synthesizes again."""

    name = status = use = licence = needs = ""
    packages = ()  # pins of the environment the engine runs in
    version = 1  # bump to synthesize again after a change the hashed code cannot see

    def missing(self):
        return []

    def voices(self):
        return []

    def default_voice(self):
        return None  # the user picks; only SAPI falls back to the system voice

    def lang(self, voice):
        """The language the voice speaks, as a BCP 47 tag ("en-us", "hi"), or None: qa_speech checks English only."""

    def program(self):
        """Text of the program the engine runs outside this module (bridge or worker)."""
        return ""

    def code_id(self):
        """Hash of the engine's classes, its program, its pins and its version. Without it the 16 kHz SAPI clock fix,
        which moved every word time, would have reused files made before it (review R3, finding 1)."""
        parts = [str(self.version), self.program(), repr(self.packages)]
        for c in type(self).__mro__[:-1]:
            try:
                parts.append(inspect.getsource(c))
            except (OSError, TypeError):
                parts.append(c.__qualname__)
        return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]

    def words(self, raw, text, total):
        """Word times from synth's raw data; for an engine whose synth returns [{w, start, end}] already."""
        return None if raw is None else [dict(w) for w in raw]

    def require(self):
        miss = self.missing()
        if miss:
            raise RuntimeError(
                f"voice engine {self.name} is not ready ({self.status}). Missing: {'; '.join(miss)}. "
                f"Needs: {self.needs}"
            )


class Sapi(Engine):
    name = "sapi"
    status = "tested 2026-10-28 on Windows 11 (Microsoft David and Zira desktop voices)"
    use = "a timing and plumbing fallback, not a quality option: the built-in Windows voices sound robotic"
    licence = "part of Windows"
    needs = "Windows PowerShell 5.1 with System.Speech (built into Windows); nothing to download"

    def __init__(self):
        self._list = None

    def missing(self):
        return (
            [] if shutil.which("powershell") else ["Windows PowerShell (Windows only)"]
        )

    def _voices(self):
        if self._list is None:
            with tempfile.TemporaryDirectory() as tmp:
                self._ps(tmp, "list", Path(tmp, "voices.json"))
                v = json.loads(Path(tmp, "voices.json").read_text(encoding="utf-8-sig"))
            self._list = [
                x for x in (v if isinstance(v, list) else [v]) if x["enabled"]
            ]
        return self._list

    def voices(self):
        return [v["name"] for v in self._voices()]

    def default_voice(self):
        return next((v["name"] for v in self._voices() if v["default"]), None)

    def model_id(self, voice):
        v = next(v for v in self._voices() if v["name"] == voice)
        return f"{v['id']} (Windows {platform.version()})"

    def lang(self, voice):
        v = next((v for v in self._voices() if v["name"] == voice), {})
        return (v.get("culture") or "").lower() or None

    def program(self):
        return _SAPI_PS1

    def words(self, raw, text, total):
        return _sapi_words(raw, text, total)

    def synth(self, texts, voice, speed, paths):
        # SAPI Rate is an integer -10..10, about 3x faster per 10 steps
        rate = max(-10, min(10, round(10 * math.log(speed, 3))))
        with tempfile.TemporaryDirectory() as tmp:
            ev = [Path(tmp, f"{i}.json") for i in range(len(texts))]
            job = {
                "voice": voice,
                "rate": rate,
                "lines": [
                    {"text": t, "wav": str(Path(p).resolve()), "events": str(e)}
                    for t, p, e in zip(texts, paths, ev)
                ],
            }
            Path(tmp, "job.json").write_text(json.dumps(job), encoding="utf-8")
            self._ps(tmp, "speak", Path(tmp, "job.json"))
            out = []
            for e in ev:  # raw word events {w, start, char, n}, kept whole: words() groups them by char and n
                got = json.loads(e.read_text(encoding="utf-8-sig") or "[]")
                out.append(
                    sorted(
                        got if isinstance(got, list) else [got],
                        key=lambda g: g["start"],
                    )
                )
        return out

    def _ps(self, tmp, mode, arg):
        """Run the System.Speech bridge: a .ps1 written here, run with -File (never inline $-heavy PowerShell)."""
        ps1 = Path(tmp, "sapi.ps1")
        ps1.write_text(_SAPI_PS1, encoding="ascii")
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ps1),
                mode,
                str(arg),
            ],
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
        )
        if r.returncode:
            raise RuntimeError(
                f"sapi {mode} failed ({r.returncode}): {(r.stderr or r.stdout).strip()[-600:]}"
            )


class _Worker(Engine):
    """An engine that runs in its own uv environment (uv run --no-project --with ...), so engine/requirements.txt
    stays Pillow and numpy only. The pins match requirements-voice.in. uv fetches the wheels on first use."""

    python = "3.14"
    packages = ()
    folder = ""

    def dir(self):
        return VOICE_DIR / self.folder

    def missing(self):
        miss = [] if shutil.which("uv") else ["uv (winget install astral-sh.uv)"]
        return miss + [f"{f} in {self.dir()}" for f in self.files() if f]

    def files(self):
        return []  # what is missing from dir(), by name

    def program(self):
        # the worker, plus _words: the job hands the worker the words it phonemizes
        return _WORKER + inspect.getsource(_words) + inspect.getsource(_word_spans)

    def _file_id(self, p):
        with open(p, "rb") as f:
            h = hashlib.file_digest(f, "sha256").hexdigest()[:16]
        return f"{p.name}:{p.stat().st_size}:{h}"

    def run(self, job):
        """Write the worker and its job into a temp folder, run it, and return its out.json."""
        with tempfile.TemporaryDirectory() as tmp:
            py, jp = Path(tmp, "voice_worker.py"), Path(tmp, "job.json")
            py.write_text(_WORKER, encoding="utf-8")
            jp.write_text(
                json.dumps(job | {"out": str(Path(tmp, "out.json"))}), encoding="utf-8"
            )
            cmd = ["uv", "run", "--no-project", "--python", self.python]
            for p in self.packages:
                cmd += ["--with", p]
            r = subprocess.run(
                cmd + ["python", str(py), str(jp)],
                check=False,
                capture_output=True,
                text=True,
                errors="replace",
            )
            if r.returncode:
                raise RuntimeError(
                    f"{self.name} worker failed ({r.returncode}): {(r.stderr or r.stdout).strip()[-800:]}"
                )
            return json.loads(Path(tmp, "out.json").read_text(encoding="utf-8"))

    def _job(self, texts, voice, speed, paths, **kw):
        lines = [
            {"text": t, "wav": str(Path(p).resolve()), "words": _words(t)}
            for t, p in zip(texts, paths)
        ]
        return {
            "engine": self.name,
            "voice": voice,
            "speed": speed,
            "lines": lines,
        } | kw


# Kokoro voice name's first letter: the espeak-ng language its words are phonemized in (hexgrad/Kokoro-82M VOICES.md
# names a American, b British, h Hindi). Other languages Kokoro has are not wired or tested here.
KOKORO_LANGS = {"a": "en-us", "b": "en-gb", "h": "hi"}


class KokoroTs(_Worker):
    name = "kokoro-ts"
    status = (
        "tested on Windows 11: af_heart, af_bella, am_michael, bf_emma (2026-10-29), every am_, bm_ and h voice "
        "(2026-11-03); af_heart is the narrator"
    )
    use = "Kokoro-82M timestamped export through kokoro-onnx: word times from its per-phoneme durations"
    licence = "kokoro-onnx MIT, onnxruntime MIT, phonemizer and espeak-ng GPL-3.0; Kokoro-82M weights Apache-2.0"
    folder = "kokoro-82m-v1.0-onnx-timestamped"
    # kokoro-onnx 0.6.1 declares requires-python <3.14, so it gets a side 3.13 environment
    python = "3.13"
    # every package that changes the sound or the phonemes, pinned (espeak-ng comes in espeakng-loader)
    packages = (
        "kokoro-onnx==0.6.1",
        "onnxruntime==1.31.1",
        "phonemizer==3.4.0",
        "espeakng-loader==0.2.4",
        "numpy==2.5.4",
    )
    needs = (
        "Python 3.13 (uv fetches it) with kokoro-onnx 0.6.1, onnxruntime 1.31.1, phonemizer 3.4.0 and espeakng-loader "
        "0.2.4 (about 40 MB of wheels, fetched by uv on first use), and from "
        "https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX-timestamped (Apache-2.0): onnx/model.onnx (fp32, "
        "325.5 MB; or onnx/model_fp16.onnx, 163.2 MB, which can turn out NaN) plus voices/<name>.bin (0.5 MB each), "
        f"into {VOICE_DIR / 'kokoro-82m-v1.0-onnx-timestamped'} keeping the onnx/ and voices/ folders"
    )

    def _model(self):
        # fp32 first: the fp16 export can give NaN (0/0 into atan) and silence a line (showtime)
        return next(
            (
                self.dir() / "onnx" / m
                for m in ("model.onnx", "model_fp16.onnx")
                if (self.dir() / "onnx" / m).exists()
            ),
            None,
        )

    def files(self):
        return [
            None if self._model() else "onnx/model.onnx",
            None if self.voices_found() else "voices/<name>.bin",
        ]

    def voices_found(self):
        return sorted(p.stem for p in (self.dir() / "voices").glob("*.bin"))

    def voices(self):
        return self.voices_found() if not self.missing() else []

    def default_voice(self):
        return NARRATOR_VOICE

    def lang(self, voice):
        return KOKORO_LANGS.get(voice[:1])

    def model_id(self, voice):
        return f"{self._file_id(self._model())} {self._file_id(self.dir() / 'voices' / f'{voice}.bin')}"

    def synth(self, texts, voice, speed, paths):
        if not 0.5 <= speed <= 2.0:
            raise ValueError(f"kokoro-ts speed is 0.5 to 2.0, got {speed}")
        if not self.lang(voice):
            raise ValueError(
                f"kokoro-ts: {voice} speaks a language not wired here; voices starting "
                f"{', '.join(KOKORO_LANGS)} are ({', '.join(KOKORO_LANGS.values())})"
            )
        job = self._job(
            texts,
            voice,
            speed,
            paths,
            model=str(self._model()),
            style=str(self.dir() / "voices" / f"{voice}.bin"),
            lang=self.lang(voice),
        )
        out = []
        for line, got in zip(job["lines"], self.run(job)):
            if not got["phonemes"]:
                raise RuntimeError(
                    f"kokoro-ts: {self._model().name} reported no durations, so no word times; use the timestamped export"
                )
            out.append(
                got | {"words": line["words"]}
            )  # raw phoneme times; words() maps them
        return out

    def words(self, raw, text, total):
        p = raw["phonemes"], raw["word_phonemes"], raw["words"], raw["seconds"]
        return _phoneme_words(*p)


ENGINES = {e.name: e for e in (Sapi(), KokoroTs())}


def get_engine(name):
    if name not in ENGINES:
        raise ValueError(
            f"unknown voice engine {name!r}; engines: {', '.join(ENGINES)}"
        )
    return ENGINES[name]


# ---- the two programs voice.py writes and runs: the SAPI bridge and the worker for the uv-run engines ----

# AudioPosition counts bytes as if the stream were 16 kHz 16-bit mono (probed 2026-10-28: with the default 22.05 kHz
# file every word time ran 1.378x late, at 44.1 kHz 2.756x), so the bridge writes exactly that format.
_SAPI_PS1 = r"""# sapi.ps1 : written and run by zoetrope voice.py: powershell -NoProfile -ExecutionPolicy Bypass -File sapi.ps1 <mode> <json>
param([string]$Mode, [string]$Json)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$utf8 = New-Object System.Text.UTF8Encoding $false
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($Mode -eq "list") {
    $out = @()
    foreach ($v in $s.GetInstalledVoices()) {
        $i = $v.VoiceInfo
        $out += [ordered]@{ name = $i.Name; id = $i.Id; culture = "$($i.Culture)"; gender = "$($i.Gender)"; age = "$($i.Age)"; enabled = $v.Enabled; default = ($i.Name -eq $s.Voice.Name) }
    }
    [IO.File]::WriteAllText($Json, (ConvertTo-Json -InputObject @($out) -Depth 3), $utf8)
    exit 0
}
$job = Get-Content -Raw -Encoding UTF8 -Path $Json | ConvertFrom-Json
$s.SelectVoice($job.voice)
$s.Rate = [int]$job.rate
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
$null = Register-ObjectEvent -InputObject $s -EventName SpeakProgress -SourceIdentifier zsp
$null = Register-ObjectEvent -InputObject $s -EventName SpeakCompleted -SourceIdentifier zdone
foreach ($line in $job.lines) {
    $s.SetOutputToWaveFile($line.wav, $fmt)
    $null = $s.SpeakAsync([string]$line.text)
    $done = Wait-Event -SourceIdentifier zdone -Timeout 300
    if (-not $done) { throw "SAPI did not finish within 300 s: $($line.text)" }
    Remove-Event -SourceIdentifier zdone
    $s.SetOutputToNull()
    Start-Sleep -Milliseconds 50
    $words = @()
    foreach ($e in @(Get-Event -SourceIdentifier zsp -ErrorAction SilentlyContinue)) {
        $a = $e.SourceEventArgs
        $words += [ordered]@{ w = $a.Text; start = $a.AudioPosition.TotalSeconds; char = $a.CharacterPosition; n = $a.CharacterCount }
        Remove-Event -EventIdentifier $e.EventIdentifier
    }
    [IO.File]::WriteAllText($line.events, (ConvertTo-Json -InputObject @($words) -Depth 3), $utf8)
}
# a subscription still live at exit makes powershell.exe return 2 after a clean run (seen 2026-10-28)
Unregister-Event -SourceIdentifier zsp
Unregister-Event -SourceIdentifier zdone
$s.Dispose()
"""

_WORKER = r'''# voice_worker.py : written and run by zoetrope voice.py inside uv run --no-project --with <engine packages>
# One job file in; one WAV per line plus out.json out.
import json
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np


def write(path, y, sr):
    pcm = np.round(np.clip(np.asarray(y, np.float32), -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(pcm.tobytes())


def kokoro_ts(job):
    """Kokoro timestamped export through kokoro-onnx 0.6.1: per-phoneme times from the "durations" output."""
    from kokoro_onnx import Kokoro

    style = np.fromfile(job["style"], np.float32).reshape(-1, 1, 256)
    with tempfile.TemporaryDirectory() as tmp:
        npz = str(Path(tmp, "voices.npz"))
        np.savez(
            npz, **{job["voice"]: style}
        )  # kokoro-onnx loads a voices npz; the export ships one .bin per voice
        k = Kokoro(job["model"], npz)
        k.voices.close()  # np.load keeps the npz open, which blocks the temp folder's removal on Windows
    # 0.6.1 sets has_timings only for an output named "duration"; the timestamped export names it "durations"
    k.has_timings = bool(
        {o.name for o in k.sess.get_outputs()} & {"duration", "durations"}
    )
    out = []
    for line in job["lines"]:
        audio, sr, timings = k.create_timed(
            line["text"], style, speed=job["speed"], lang=job["lang"]
        )
        if np.isnan(audio).any():
            raise SystemExit(
                f"NaN audio for {line['text'][:40]!r}: the fp16 export did it; use onnx/model.onnx (fp32)"
            )
        write(line["wav"], audio, sr)
        out.append(
            {
                "sr": sr,
                "seconds": len(audio) / sr,
                "phonemes": [[t.phoneme, t.start, t.end] for t in timings],
                "word_phonemes": [
                    k.tokenizer.phonemize(w, job["lang"]) for w in line["words"]
                ],
            }
        )
    return out


if __name__ == "__main__":
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    res = {"kokoro-ts": kokoro_ts}[job["engine"]](job)
    Path(job["out"]).write_text(json.dumps(res), encoding="utf-8")
'''
