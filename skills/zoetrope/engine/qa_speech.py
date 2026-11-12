# qa_speech.py : gate 8's speech check. A speech recognizer (faster-whisper base.en, offline, on the CPU) writes down
# what each narrated line says, and those words are held against the script: Q806 on the narration stem
# (narration.wav) against narration.json, Q807 on the finished file's sound against the stem. The reviewer cannot
# hear, so this is what the narration says, measured. The idea of checking speech by transcribing it is VoiceStudio's
# (debpalash/VoiceStudio docs/evaluation.md, AGPL-3.0, read 2026-11-03; no code taken).
#   python qa_speech.py fetch                 download the model (147.8 MB, MIT), pinned, each file checked
#   qa.py speech narration/narration.json     Q806 alone, right after voice.synthesize (exit 1 on a FIX)
import argparse
import difflib
import hashlib
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import urllib.request
from pathlib import Path

import contract as C
import numpy as np

ASR_DIR = Path(
    os.environ.get("ZOETROPE_ASR") or Path.home() / ".cache" / "zoetrope" / "asr"
)
MODEL = "faster-whisper-base.en"
REPO, COMMIT = (
    "Systran/faster-whisper-base.en",
    "3d3d5dee26484f91867d81cb899cfcf72b96be6c",
)
# (file, bytes, sha256), fetched 2026-11-03: each matched the size and the LFS sha256 or git blob Hugging Face lists
FILES = (
    ("config.json", 2227, "f3bc3821e9fc76a27bae538e11ae5b677dcdd352b4600429ce7951d398569aeb"),
    ("model.bin", 145216508, "2a166925539a16005f14ff328359f9b9adb9dc4fb631bb3b227526862e93e2ef"),
    ("tokenizer.json", 2128466, "929c5252409436dce1b38a75d1abbcb5e132d170d8e324e4e04ed915fa2d22df"),
    ("vocabulary.txt", 422309, "ff77588746d3a2595d32ab5b69ffd7b95ce2441ac57533cb66fc3eb575a115cf"),
)  # fmt: skip
# its own uv environment, like the voice engines: av 18, because faster-whisper 1.2.1 fails to open a file with av 19
# (SYSTRAN/faster-whisper#1589); clips go in as raw float32 anyway. Every package that changes the words is pinned.
PYTHON = "3.14"
PACKAGES = (
    "faster-whisper==1.2.1",
    "ctranslate2==4.8.5",
    "av==18.1.0",
    "onnxruntime==1.31.1",
    "tokenizers==0.23.3",
    "numpy==2.5.4",
)
VERSION = 1  # bump to transcribe again after a change the hashed worker cannot see
SR = 16000  # what the model hears
PAD = 0.3  # seconds of the timeline kept each side of a line's clip
NEAR = 0.6  # a changed word this close in letters (difflib ratio) is a NOTE: the voice or the model may be wrong
# so is a short word changed for a short word: connected speech reduces them (two British voices said "Two are
# square" with "are" as a schwa, and base.en wrote "to a")
SHORT = 3
MANY = 3  # more issues than this on one line become one row for the line
# the stem is found in the file by GCC-PHAT; under this peak prominence (peak minus mean, in standard deviations
# of the correlation) it is not there. Measured 2026-11-03 on a 7.5 s narrated build: the real mix 321, the same
# voice buried 24 dB under the bed 108, a stem from other lines 15
STALE_Z = 40
STEM_CACHE, MIX_CACHE = "speech.json", "speech_mix.json"  # beside narration.json


# ---- the model and the worker ----


def missing():
    """What is not ready, by name (empty when the check can run)."""
    miss = [] if shutil.which("uv") else ["uv (winget install astral-sh.uv)"]
    d = ASR_DIR / MODEL
    return miss + [
        f"{d / n} ({size} bytes)"
        for n, size, _ in FILES
        if not (d / n).is_file() or (d / n).stat().st_size != size
    ]


def fetch():
    """Download every model file that is missing or the wrong size into ASR_DIR, each kept only when its size and
    sha256 match. Exit 0 when all are there, 1 when one failed."""
    d, bad = ASR_DIR / MODEL, 0
    d.mkdir(parents=True, exist_ok=True)
    for n, size, sha in FILES:
        p = d / n
        if p.is_file() and p.stat().st_size == size:
            print(f"have {n}")
            continue
        url = f"https://huggingface.co/{REPO}/resolve/{COMMIT}/{n}"
        data = urllib.request.urlopen(url, timeout=120).read()
        got = hashlib.sha256(data).hexdigest()
        if len(data) != size or got != sha:
            print(
                f"FAIL {n}: {len(data)} bytes, sha256 {got[:12]}; want {size}, {sha[:12]}"
            )
            bad += 1
            continue
        tmp = p.with_suffix(p.suffix + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, p)
        print(f"got {n} ({size} bytes, sha256 {sha[:12]})")
    print(f"FETCH: {'FAIL' if bad else 'OK'} ({MODEL} at {COMMIT[:8]} in {d})")
    return 1 if bad else 0


def code_id():
    """What makes a transcript: the model's pinned files, the worker, its pins and VERSION."""
    parts = [
        MODEL,
        COMMIT,
        *(sha for _, _, sha in FILES),
        _WORKER,
        repr(PACKAGES),
        str(VERSION),
    ]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]


def hear(clips):
    """[{text, words: [{w, start, end, p}]}] for each clip (float32 at SR), seconds from the clip's start. Runs the
    worker once in its own uv environment; raises RuntimeError when it fails."""
    if not clips:
        return []
    with tempfile.TemporaryDirectory() as tmp:
        names = []
        for i, y in enumerate(clips):
            p = Path(tmp, f"{i}.f32")
            np.asarray(y, np.float32).tofile(p)
            names.append(str(p))
        py, jp, out = (
            Path(tmp, "speech_worker.py"),
            Path(tmp, "job.json"),
            Path(tmp, "out.json"),
        )
        py.write_text(_WORKER, encoding="utf-8")
        job = {
            "model": str(ASR_DIR / MODEL),
            "clips": names,
            "out": str(out),
            "threads": max(1, min(8, os.cpu_count() or 1)),
        }
        jp.write_text(json.dumps(job), encoding="utf-8")
        cmd = ["uv", "run", "--no-project", "--python", PYTHON]
        for p in PACKAGES:
            cmd += ["--with", p]
        r = subprocess.run(
            cmd + ["python", str(py), str(jp)],
            check=False,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            text=True,
            errors="replace",
        )
        if r.returncode:
            raise RuntimeError(
                f"speech worker failed ({r.returncode}): {(r.stderr or r.stdout).strip()[-600:]}"
            )
        return json.loads(out.read_text(encoding="utf-8"))


def heard(clips, cache, listen=None):
    """hear() through a cache file: a clip whose samples, model, worker and pins are unchanged is not heard again.
    The cache keeps exactly this call's clips. listen replaces hear (the selftest's canned transcripts); nothing is
    cached then."""
    if listen is not None:
        return listen(clips)
    cid = code_id()
    keys = [
        hashlib.sha256(cid.encode() + np.asarray(y, np.float32).tobytes()).hexdigest()
        for y in clips
    ]
    try:
        old = json.loads(Path(cache).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    todo = [i for i, k in enumerate(keys) if k not in old]
    got = dict(zip((keys[i] for i in todo), hear([clips[i] for i in todo])))
    have = old | got
    tmp = Path(f"{cache}.tmp")
    tmp.write_text(json.dumps({k: have[k] for k in keys}, indent=1), encoding="utf-8")
    os.replace(tmp, cache)
    return [have[k] for k in keys]


# ---- words: numbers written in digits, respellings and joined words compare as the same speech ----

ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
    "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen",
]  # fmt: skip
TENS = [
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
]
ORD = {
    "one": "first",
    "two": "second",
    "three": "third",
    "five": "fifth",
    "eight": "eighth",
    "nine": "ninth",
    "twelve": "twelfth",
}
CURRENCY = {"$": "dollars", "\u00a3": "pounds", "\u20ac": "euros", "\u20b9": "rupees"}
SAME = {"ok": "okay"}  # one word a model and a script spell two ways
NUMBER = re.compile(
    "^([$\u00a3\u20ac\u20b9])?" r"(\d[\d,]*)(?:\.(\d+))?(%|st|nd|rd|th|s)?$"
)
EDGE = ".,;:!?\"'()[]{}\u2018\u2019\u201c\u201d\u2026"  # taken off a token before it is read as a number
CLOCK = re.compile(r"^(\d{1,2}):(\d{2})$")
MIXED = re.compile(r"(?:\d+[A-Za-z]+|[A-Za-z]+\d+)[A-Za-z\d]*")


def cardinal(n):
    """English words for a whole number from 0 to under a trillion: 2026 is two thousand twenty six."""
    if n < 20:
        return [ONES[n]]
    if n < 100:
        return [TENS[n // 10]] + ([ONES[n % 10]] if n % 10 else [])
    if n < 1000:
        return [ONES[n // 100], "hundred"] + (cardinal(n % 100) if n % 100 else [])
    for size, name in ((10**9, "billion"), (10**6, "million"), (1000, "thousand")):
        if n >= size:
            return (
                cardinal(n // size) + [name] + (cardinal(n % size) if n % size else [])
            )
    raise ValueError(n)


def _readings(n):
    """Every common way to say the whole number n: plain, with "and" (two thousand and six), as a year (twenty twenty
    six, nineteen oh five), and "a hundred"."""
    out = [cardinal(n)]
    if n >= 100 and 0 < n % 100:
        out.append(cardinal(n - n % 100) + ["and"] + cardinal(n % 100))
    if 1000 <= n <= 2099 and n % 1000:
        hi, lo = divmod(n, 100)
        if lo == 0:
            out.append(cardinal(hi) + ["hundred"])
        elif hi % 10 or hi == 20:
            out.append(
                cardinal(hi) + (["oh"] + cardinal(lo) if lo < 10 else cardinal(lo))
            )
    if 100 <= n < 200:  # a hundred, a hundred and twenty
        out += [["a"] + r[1:] for r in out if r[:2] == ["one", "hundred"]]
    return out


def _ordinal(words):
    last = words[-1]
    end = ORD.get(last) or (last[:-1] + "ieth" if last.endswith("y") else last + "th")
    return words[:-1] + [end]


def _plural(words):
    last = words[-1]
    return words[:-1] + [last[:-1] + "ies" if last.endswith("y") else last + "s"]


def _number(tok):
    """The ways a number written as tok is said (a list of word lists), or None when tok is not a number."""
    m = CLOCK.match(tok)
    if m:
        h, mm = int(m.group(1)), int(m.group(2))
        if mm == 0:
            return [cardinal(h), cardinal(h) + ["o'clock"]]
        return [cardinal(h) + (["oh"] if mm < 10 else []) + cardinal(mm)]
    m = NUMBER.match(tok)
    if not m:
        return None
    cur, whole, frac, tail = m.groups()
    n = int(whole.replace(",", ""))
    if n >= 10**12 or (frac is not None and tail not in (None, "%")):
        return None
    if frac is not None:
        point = [ONES[int(d)] for d in frac]
        say = [r + ["point"] + point for r in _readings(n)] + (
            [["point"] + point] if n == 0 else []
        )
        if cur and len(frac) == 2:  # $5.99: five dollars ninety nine, five ninety nine
            name = CURRENCY[cur]
            cents = cardinal(int(frac))
            say = [r + [name] + cents for r in _readings(n)] + [
                r + cents for r in _readings(n)
            ]
            say += [r + [name, "and"] + cents + ["cents"] for r in _readings(n)]
    else:
        say = _readings(n)
    if tail == "%":
        say = [s + ["percent"] for s in say]
    elif tail in ("st", "nd", "rd", "th"):
        say = [_ordinal(s) for s in say]
    elif tail == "s":
        say = [_plural(s) for s in say]
    if cur and not (frac is not None and len(frac) == 2):
        name = CURRENCY[cur]
        say = [s + [name[:-1] if n == 1 else name] for s in say]
    return say


# British and American spellings fold to one, on both sides (harbour and harbor, colour, organise, centre); measured:
# a Kokoro calibration line said "harbour" and base.en wrote "harbor"
US = (
    # three letters first, so four, hour, your and flour never fold into for, hor, yor and flor
    (re.compile(r"(?<=[a-z]{3})our(s|ed|ing|ful|ite|ites)?$"), r"or\1"),
    (re.compile(r"(?<=[a-z])is(e|es|ed|ing|ation|ations)$"), r"iz\1"),
    (re.compile(r"(?<=[a-z])ys(e|es|ed|ing)$"), r"yz\1"),
    (re.compile(r"(?<=[^aeiou])re(s)?$"), r"er\1"),  # not -red: hundred, sacred
)
# a letter said alone is a word to a speech model: SAPI's "Two are square" came back as "2. R. Square"
LETTERS = {
    "b": ("be", "bee"),
    "c": ("see", "sea"),
    "i": ("eye",),
    "j": ("jay",),
    "k": ("kay",),
    "o": ("oh", "owe"),
    "p": ("pea", "pee"),
    "q": ("queue", "cue"),
    "r": ("are",),
    "t": ("tea", "tee"),
    "u": ("you",),
    "x": ("ex",),
    "y": ("why",),
}


# Words that sound the same are the same to a listener, so they are one word here: the model writes whichever its
# language model prefers. Measured 2026-11-03: four Kokoro voices said "Two are square" and base.en wrote "to our".
HOMOPHONES = (
    ("to", "two", "too"), ("for", "four", "fore"), ("are", "our", "hour"), ("one", "won"), ("eight", "ate"),
    ("there", "their", "they're"), ("your", "you're"), ("its", "it's"), ("whose", "who's"), ("right", "write", "rite"),
    ("no", "know"), ("new", "knew"), ("by", "buy", "bye"), ("hear", "here"), ("see", "sea"), ("be", "bee"),
    ("i", "eye"), ("weather", "whether"), ("peace", "piece"), ("wait", "weight"), ("week", "weak"), ("son", "sun"),
    ("where", "wear"), ("would", "wood"), ("through", "threw"), ("so", "sew", "sow"), ("meet", "meat"),
    ("pair", "pear"), ("plain", "plane"), ("road", "rode"), ("whole", "hole"), ("not", "knot"), ("night", "knight"),
    ("made", "maid"), ("male", "mail"), ("sale", "sail"), ("tale", "tail"), ("flour", "flower"),
    ("allowed", "aloud"), ("break", "brake"), ("sell", "cell"), ("die", "dye"), ("fair", "fare"), ("high", "hi"),
    ("lead", "led"), ("past", "passed"), ("rain", "reign", "rein"), ("seen", "scene"), ("some", "sum"),
    ("stair", "stare"), ("steel", "steal"), ("way", "weigh"), ("which", "witch"),
)  # fmt: skip
SOUND = {w: g[0] for g in HOMOPHONES for w in g}


def _plain(w):
    """A word as both sides compare it: voice._norm, the spellings in SAME, the US spelling fold, then one word for
    each group of homophones."""
    import voice as V

    k = V._norm(w)
    k = SAME.get(k, k)
    for pat, to in US:
        k = pat.sub(to, k)
    return SOUND.get(k, k)


def _said(tok):
    """_number(tok) with every word of every reading folded as _plain folds a script word, or None."""
    num = _number(tok)
    return [[_plain(w) for w in r] for r in num] if num else None


def _word_reads(p):
    """Readings of one plain word: itself, plus the words a lone letter sounds like."""
    return [[p]] + [[_plain(n)] for n in LETTERS.get(p, ())]


def atoms(text, lex=None):
    """[(index of the word in text, [reading, ...])] where a reading is a list of plain words; the index counts words
    as voice._words does, so it points into a narration line's words[]. A number in digits ($99, 20%, 2026, 3:45) is
    one atom with every common reading, a word the lexicon respells one atom read either way, and any other word one
    atom per hyphen or slash part."""
    import voice as V

    out, i = [], -1
    for tok in text.split():
        if all(unicodedata.category(ch)[0] in "PS" for ch in tok):
            continue  # voice._words skips a token of punctuation alone
        i += 1
        core = tok.strip(EDGE)
        num = _said(core)
        if num:
            out.append((i, num))
            continue
        if MIXED.fullmatch(
            core
        ):  # 2R, 4K, A4: each run of digits or letters on its own
            for run in re.findall(r"\d+|[A-Za-z]+", core):
                out.append((i, _said(run) or _word_reads(_plain(run))))
            continue
        pieces = [
            p for p in (_plain(x) for x in re.split("[-\u2010-\u2015/]", tok)) if p
        ]
        say = (lex or {}).get(V._norm(tok))
        if say:
            out.append(
                (i, [pieces, [p for p in (_plain(x) for x in V._words(say)) if p]])
            )
        else:
            out += [(i, _word_reads(p)) for p in pieces]
    return out


def _joins(block, cap=256):
    """Every way to spell a block of atoms as one string with no spaces (capped)."""
    combos = itertools.islice(itertools.product(*(a[1] for a in block)), cap)
    return {"".join(w for reading in c for w in reading) for c in combos}


def _key(atom):
    """The string an atom aligns by: its first reading, or a mark that matches nothing for a number."""
    r = atom[1]
    return "".join(r[0]) if len(r) == 1 else f"#{'|'.join(''.join(x) for x in r)}"


def compare(said, got):
    """Where got (atoms heard) differs from said (atoms of the script): [(kind, said block, got block)], kind one of
    missing, extra, near (a NOTE: close in letters) and wrong. Blocks that spell the same words, such as "2026" and
    "twenty twenty six" or "night time" and "nighttime", are not differences."""
    sm = difflib.SequenceMatcher(
        None, [_key(a) for a in said], [_key(a) for a in got], autojunk=False
    )
    out = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        s, g = said[i1:i2], got[j1:j2]
        if s and g and _joins(s) & _joins(g):
            continue
        if not g:
            out.append(("missing", s, g))
        elif not s:
            out.append(("extra", s, g))
        else:
            close = max(
                difflib.SequenceMatcher(None, a, b).ratio()
                for a, b in itertools.islice(
                    itertools.product(_joins(s), _joins(g)), 64
                )
            )
            short = max(len(x) for x in _joins(s) | _joins(g)) <= SHORT
            out.append(("near" if close >= NEAR or short else "wrong", s, g))
    return out


# ---- reading the narration ----


def _narration(ctx_or_path):
    """(narration dict, its folder) from a path, or from a Ctx (scenes.NARRATION, else narration/narration.json in the
    build folder); (None, path tried) when there is none."""
    if isinstance(ctx_or_path, (str, Path)):
        p = Path(ctx_or_path)
    else:
        rel = getattr(ctx_or_path.scenes, "NARRATION", "narration/narration.json")
        p = Path(ctx_or_path.workdir, rel)
    if not p.is_file():
        return None, p
    return json.loads(p.read_text(encoding="utf-8")), p.parent


def _clips(y, narr, at=0.0):
    """Each line's samples of y (at SR) with PAD each side, and the second of y each clip starts at; at moves the
    narration timeline into y's (the offset of the stem in the file)."""
    out = []
    for ln in narr["lines"]:
        a = max(0.0, at + ln["start"] - PAD)
        b = min(len(y) / SR, at + ln["end"] + PAD)
        out.append((y[C.sample_of(a, SR) : C.sample_of(b, SR)], a))
    return out


def _english(narr):
    return (narr.get("lang") or "en").lower().startswith("en")


def _spoken(h, a):
    """(text, times): what a transcript says, and each of its words' start on the timeline (a: the clip's start),
    one per word as atoms() counts them."""
    ws = [
        w
        for w in h["words"]
        if not all(unicodedata.category(ch)[0] in "PS" for ch in w["w"])
    ]
    return " ".join(w["w"] for w in ws), [round(a + w["start"], 3) for w in ws]


def _show(block, text):
    import voice as V

    words = V._words(text)
    return " ".join(words[i] for i in sorted({i for i, _ in block}) if i < len(words))


def _issue_rows(code, lid, issues, said, got, span, where, fix, status_of):
    """Rows for one line's issues, one per issue (one for the line when there are more than MANY). said and got are
    (text, times) of the two sides; span is the line's (t0, t1) on the timeline the row reports."""
    import voice as V

    (s_text, s_t), (g_text, g_t) = said, got
    n = len(V._words(s_text))
    t0, t1 = span
    if len(issues) > MANY:
        k = sum(len({i for i, _ in s}) or 1 for _, s, _ in issues)
        return [
            C.Row(
                C.FIX
                if any(status_of(kind) == C.FIX for kind, _, _ in issues)
                else C.NOTE,
                code,
                f"{lid}: {k} of {n} words not heard as written in {where} (heard {g_text!r})",
                fix,
                t0=t0,
                t1=t1,
                worst_t=t0,
                item=lid,
                metric=k,
                considered=n,
            )
        ]
    rows = []
    for kind, s, g in issues:
        a, b = _show(s, s_text), _show(g, g_text)
        if s and s[0][0] < len(s_t):
            t = s_t[s[0][0]]
        elif g and g[0][0] < len(g_t):
            t = g_t[g[0][0]]
        else:
            t = t0
        if kind == "missing":
            item, msg = f"{lid} missing {a!r}", f"{a!r} is not heard"
        elif kind == "extra":
            item, msg = (
                f"{lid} extra {b!r}",
                f"{b!r} is heard but not in the {'stem' if code == 'Q807' else 'script'}",
            )
        else:
            item, msg = f"{lid} {a!r} heard as {b!r}", f"{a!r} is heard as {b!r}"
        rows.append(
            C.Row(
                status_of(kind),
                code,
                f"{lid}: {msg} in {where} (heard {g_text!r})",
                fix,
                t0=t0,
                t1=t1,
                worst_t=t,
                item=item,
                metric=len({i for i, _ in s}) or len({i for i, _ in g}),
                considered=n,
            )
        )
    return rows


# ---- Q806: the stem against the script ----

FIX_806 = (
    "listen to the line; respell a misread word with synthesize(lexicon={word: respelling}), write numbers and names "
    "as they are said, and synthesize again"
)


def stem_rows(narration, listen=None, scenes=None, at=0.0):
    """Q806 for narration.json at a path (or a Ctx): each line's clip of narration.wav, transcribed, against its text.
    A missing, extra or different word is a FIX; one close in letters is a NOTE (the voice or the model may be wrong:
    listen). A narration that is not English is a NOTE: base.en hears English only. at moves the row times from the
    narration timeline to the file's (the stem's offset in the mix)."""
    narr, where = _narration(narration)
    if narr is None:
        if _card_audio(scenes) == "voice":
            return [
                C.not_checked(
                    "Q806",
                    f"the card is narrated but {where} is not here, so the speech check did not run",
                    "run voice.synthesize in the parent session and copy narration/ into the build",
                )
            ]
        return [
            C.row(
                True,
                "Q806",
                f"no narration in this build ({where} absent)",
                "",
                considered=0,
            )
        ]
    lines = narr["lines"]
    if not _english(narr):
        return [
            C.row(
                False,
                "Q806",
                f"{len(lines)} lines in {narr.get('lang')}: base.en hears English only, so what they say was not checked",
                "listen to the narration yourself",
                note=True,
                considered=0,
            )
        ]
    if listen is None and missing():
        return [
            C.not_checked(
                "Q806",
                f"the speech model is not ready ({'; '.join(missing())}), so what the narration says was not checked",
                f"python qa_speech.py fetch ({MODEL}, 147.8 MB, MIT)",
            )
        ]
    import voice as V

    y = V.dec(str(Path(where, narr.get("file", "narration.wav"))), sr=SR)
    clips = _clips(y, narr)
    try:
        got = heard([c for c, _ in clips], Path(where, STEM_CACHE), listen)
    except RuntimeError as e:
        return [
            C.not_checked(
                "Q806",
                f"the speech model did not run: {e}",
                "run `qa.py speech` alone and read the error",
            )
        ]
    lex = V._lexicon(narr.get("lexicon"))
    rows, words = [], 0
    for ln, (_, a), h in zip(lines, clips, got):
        words += len(V._words(ln["text"]))
        heard_text, heard_t = _spoken(h, at + a)
        rows += _issue_rows(
            "Q806",
            ln["id"],
            compare(atoms(ln["text"], lex), atoms(heard_text)),
            (ln["text"], [round(at + w["start"], 3) for w in ln.get("words") or []]),
            (heard_text, heard_t),
            (round(at + ln["start"], 3), round(at + ln["end"], 3)),
            "narration.wav",
            FIX_806,
            lambda kind: C.NOTE if kind == "near" else C.FIX,
        )
    if not rows:
        rows.append(
            C.row(
                True,
                "Q806",
                f"{len(lines)} narrated lines, {words} words: every word heard as written ({MODEL})",
                "",
                considered=words,
            )
        )
    return rows


def _card_audio(scenes):
    """The audio= of the style card scenes.CARD names (cards.py), or None."""
    name = getattr(scenes, "CARD", None)
    if not name:
        return None
    try:
        import cards

        return cards.spec(name).get("audio")
    except (ImportError, KeyError, ValueError, OSError):
        return None


# ---- Q807: the file's sound against the stem ----


def offset(mix, stem):
    """(second the stem starts at in mix, prominence z of that match). Both at SR; only starts inside mix. GCC-PHAT
    (the cross-spectrum whitened to its phase), so a loud bed with its own rhythm does not pull the match: plain
    correlation put a voice buried under the bed 0.87 s off, PHAT on it."""
    if not len(mix) or not len(stem):
        return 0.0, 0.0
    n = 1 << (len(mix) + len(stem) - 1).bit_length()
    x = np.fft.rfft(mix, n) * np.conj(np.fft.rfft(stem, n))
    xc = np.fft.irfft(x / (np.abs(x) + 1e-9), n)[: len(mix)]
    lag = int(np.argmax(xc))
    return lag / SR, float((xc[lag] - xc.mean()) / (xc.std() + 1e-12))


def _placed(ctx, narr, where):
    """(stem at SR, file's sound at SR, offset, r), worked out once per Ctx."""
    if getattr(ctx, "_qa_speech", None) is None:
        import voice as V

        stem = V.dec(str(Path(where, narr.get("file", "narration.wav"))), sr=SR)
        mix = ctx.audio(sr=SR)
        ctx._qa_speech = (stem, mix, *offset(mix, stem))
    return ctx._qa_speech


FIX_807 = (
    "if the music masks these words, duck it deeper under the voice (voice.duck_mix depth_db), lower the sounds "
    "placed there or lift the voice; if the file says other words, it was mixed from an older take: run_all.py audio"
)


def mix_rows(ctx, listen=None, listen_stem=None):
    """Q807 on the file: find narration.wav in the file's sound, transcribe each line there and compare it with the
    stem's own transcript. A word the stem says and the file loses is a NOTE (the music masks it); a file that does not
    carry the stem at all is a FIX."""
    narr, where = _narration(ctx)
    if (
        narr is None
        or not ctx.probe.get("acodec")
        or ctx.declared("SILENT")
        or not _english(narr)
    ):
        return []
    if (listen is None or listen_stem is None) and missing():
        return [
            C.not_checked(
                "Q807",
                f"the speech model is not ready ({'; '.join(missing())}), so the narration in the file was not heard",
                f"python qa_speech.py fetch ({MODEL}, 147.8 MB, MIT)",
            )
        ]
    stem, mix, at, z = _placed(ctx, narr, where)
    name = narr.get("file", "narration.wav")
    if z < STALE_Z:
        return [
            C.Row(
                C.FIX,
                "Q807",
                f"the file's sound does not carry {name} (best match z {z:.0f} at {at:+.2f} s, want {STALE_Z} or "
                f"more): mixed from another take, not mixed at all, or buried too deep under the music to find",
                "mix the current narration.wav (run_all.py audio after any new voice.synthesize)",
                item=name,
                metric=round(z, 1),
                limit=STALE_Z,
                considered=1,  # the one stem it looked for
            )
        ]
    lines = narr["lines"]
    s_clips, m_clips = _clips(stem, narr), _clips(mix, narr, at)
    try:
        h_stem = heard([c for c, _ in s_clips], Path(where, STEM_CACHE), listen_stem)
        h_mix = heard([c for c, _ in m_clips], Path(where, MIX_CACHE), listen)
    except RuntimeError as e:
        return [
            C.not_checked(
                "Q807",
                f"the speech model did not run: {e}",
                "run `qa.py speech` alone and read the error",
            )
        ]
    rows, words = [], 0
    for ln, (_, sa), (_, ma), hs, hm in zip(lines, s_clips, m_clips, h_stem, h_mix):
        said, got = _spoken(hs, at + sa), _spoken(hm, ma)
        words += len(atoms(said[0]))
        rows += _issue_rows(
            "Q807",
            ln["id"],
            compare(atoms(said[0]), atoms(got[0])),
            said,
            got,
            (round(at + ln["start"], 3), round(at + ln["end"], 3)),
            "the file",
            FIX_807,
            lambda kind: C.NOTE,
        )
    if not rows:
        rows.append(
            C.row(
                True,
                "Q807",
                f"{name} found at {at:+.3f} s in the file (z {z:.0f}); every word the stem says is heard there "
                f"({words} words, {len(lines)} lines)",
                "",
                considered=words,
                metric=round(at, 3),
            )
        )
    return rows


def check_rows(ctx):
    """Q806 and Q807 for qa.py check (only with --scenes: the narration lives in the build folder). Q806's times are
    moved to where the stem sits in the file."""
    if ctx.scenes is None:
        return []
    if ctx.declared("SILENT"):
        return [
            C.row(True, "Q806", "silent piece: no narration to check", "", considered=0)
        ]
    narr, where = _narration(ctx)
    at = 0.0
    if (
        narr is not None
        and ctx.probe.get("acodec")
        and _english(narr)
        and not missing()
    ):
        _, _, at, z = _placed(ctx, narr, where)
        at = at if z >= STALE_Z else 0.0
    return stem_rows(ctx, scenes=ctx.scenes, at=at) + mix_rows(ctx)


# ---- qa.py speech ----


def run(a):
    if a.fetch:
        return fetch()
    rows = stem_rows(a.narration)
    for r in rows:
        print(C.line(r))
    print(C.summary(rows, "SPEECH"))
    return C.exit_code(rows)


def add_cli(sub):
    s = sub.add_parser(
        "speech",
        help="Q806: what the narration says, transcribed by a speech model, against its script (exit 1 on a FIX)",
    )
    s.add_argument("narration", nargs="?", default="narration/narration.json")
    s.add_argument(
        "--fetch", action="store_true", help=f"download {MODEL} (147.8 MB) first"
    )
    s.set_defaults(func=run)


_WORKER = r"""# speech_worker.py : written and run by zoetrope qa_speech.py inside uv run --no-project --with <pins>
# One job file in (clips as raw float32 at 16 kHz); out.json out: the words heard in each clip, with times.
import json
import sys
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
m = WhisperModel(job["model"], device="cpu", compute_type="int8", cpu_threads=job["threads"])
out = []
for clip in job["clips"]:
    y = np.fromfile(clip, np.float32)
    segs, _ = m.transcribe(
        y,
        language="en",
        beam_size=5,
        temperature=0.0,
        condition_on_previous_text=False,
        word_timestamps=True,
        vad_filter=False,
    )
    words = [
        {"w": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3), "p": round(w.probability, 3)}
        for s in segs
        for w in s.words
    ]
    out.append({"text": " ".join(w["w"] for w in words), "words": words})
Path(job["out"]).write_text(json.dumps(out), encoding="utf-8")
"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="the speech model for Q806 and Q807")
    ap.add_argument("cmd", choices=["fetch", "missing"])
    a = ap.parse_args()
    if a.cmd == "fetch":
        sys.exit(fetch())
    miss = missing()
    print("\n".join(miss) or f"{MODEL}: ready in {ASR_DIR / MODEL}")
    sys.exit(1 if miss else 0)
