# speech.py : the speech check (Q806, Q807) on a synthetic narration in the case's temp folder. Each word is a burst
# of seeded noise shaped like a syllable, so the stem can be found in a mix by its own samples, and the speech model
# is replaced by canned transcripts (listen=): the selftest needs no model and no download. Q806: digits, hyphens and
# homophones heard for the script's words pass; a missing, a changed and an added word are FIX, a word close in
# letters a NOTE, a narration in Hindi a NOTE, no model NOT CHECKED. Q807: the stem placed 0.5 s into a mix is
# found there; a word the mix loses is a NOTE; a mix of another take is a FIX.
import json

import contract as C
import numpy as np
import qa_speech as S
import voice as V

from qa_fixtures import case, clean, media, want

SR = 44100
LINES = [
    ("L01", "It costs ninety nine dollars in twenty twenty six."),
    ("L02", "Almost every national flag is a rectangle."),
]
# L02's first word: L01 is a 0.35 s lead, 9 words of 0.35 s and a 0.7 s tail, then L02's own lead
L02_AT = 0.35 + 9 * 0.35 + 0.7 + 0.35


def speech(lines, seed, sr):
    """(samples at sr, lines as narration.json has them): each word 0.3 s of syllable-shaped noise, 0.05 s apart,
    each line in a 0.35 s lead and a 0.7 s tail."""
    rng = np.random.default_rng(seed)
    out, chunks, t = [], [], 0.0
    for lid, text in lines:
        words, body = [], []
        for i, w in enumerate(V._words(text)):
            n = round(0.3 * sr)
            env = np.sin(np.linspace(0, np.pi, n)) ** 2
            body += [rng.standard_normal(n) * 0.3 * env, np.zeros(round(0.05 * sr))]
            at = t + 0.35 + 0.35 * i
            words.append({"w": w, "start": round(at, 3), "end": round(at + 0.3, 3)})
        y = np.concatenate(
            [np.zeros(round(0.35 * sr)), *body, np.zeros(round(0.7 * sr))]
        )
        a, b = t + 0.35, t + 0.35 + 0.35 * len(words)
        out.append(
            {
                "id": lid,
                "text": text,
                "start": round(a, 6),
                "end": round(b, 6),
                "speech_start": round(a, 6),
                "speech_end": round(b - 0.05, 6),
                "words": words,
            }
        )
        chunks.append(y)
        t += len(y) / sr
    return np.concatenate(chunks).astype(np.float32), out


def narration(fx, lines=LINES, lang="en-us"):
    """narration/narration.json and narration.wav in fx.tmp."""
    y, out = speech(lines, 1, SR)
    folder = fx.tmp / "narration"
    folder.mkdir(parents=True, exist_ok=True)
    media.wav(folder / "narration.wav", y, SR)
    narr = {
        "lang": lang,
        "lexicon": {},
        "sr": SR,
        "file": "narration.wav",
        "lines": out,
    }
    (folder / "narration.json").write_text(json.dumps(narr), encoding="utf-8")
    return folder / "narration.json"


def says(*texts):
    """A listen= that hears texts, one per clip, each word 0.35 s after the one before from 0.3 s into the clip."""

    def listen(clips):
        assert len(clips) == len(texts), (len(clips), len(texts))
        return [
            {
                "text": t,
                "words": [
                    {"w": w, "start": 0.3 + 0.35 * i, "end": 0.6 + 0.35 * i}
                    for i, w in enumerate(t.split())
                ],
            }
            for t in texts
        ]

    return listen


def stem(heard, lines=LINES, lang="en-us"):
    def run(fx):
        return S.stem_rows(narration(fx, lines, lang), listen=says(*heard))

    return run


def no_model(fx):
    path = narration(fx)
    keep = S.ASR_DIR
    S.ASR_DIR = fx.tmp / "no-model-here"
    try:
        return S.stem_rows(path)
    finally:
        S.ASR_DIR = keep


def mix(heard, take=1):
    """Q807 on fx.tmp/mix.wav: take 1 is the stem itself 0.5 s in under quiet noise; another take is the same lines
    spoken by other samples."""

    def run(fx):
        narration(fx)
        y, _ = speech(LINES, take, SR)
        x = np.random.default_rng(99).standard_normal(len(y) + SR) * 0.01
        x[SR // 2 : SR // 2 + len(y)] += y
        path = media.wav(fx.tmp / "mix.wav", x, SR)
        probe = {"acodec": "pcm_f32le", "vcodec": None, "channels": 1, "frames": 0}
        ctx = C.Ctx(path, probe, 30, 320, 180, None, fx.tmp, ff=fx.ff)
        return S.mix_rows(
            ctx, listen=says(*heard), listen_stem=says(*(t for _, t in LINES))
        )

    return run


CASES = [
    case(
        "speech.stem_as_said",
        stem(["It costs $99 in 2026.", "Almost every national flag is a rectangle."]),
        [clean(), want("Q806", "PASS", msg="every word heard as written", n=1)],
    ),
    case(
        "speech.stem_homophones",
        stem(
            ["to our square, for rooms.", "It is night-time."],
            lines=[("L01", "Two are square, four rooms."), ("L02", "It is nighttime.")],
        ),
        [clean(), want("Q806", "PASS", msg="every word heard as written")],
    ),
    case(
        "speech.stem_missing",
        stem(["It costs $99 in 2026.", "Almost every flag is a rectangle."]),
        [
            want(
                "Q806",
                "FIX",
                "L02 missing 'national'",
                L02_AT + 2 * 0.35,
                tol=0.01,
                metric=1,
                mtol=0.1,
            )
        ],
    ),
    case(
        "speech.stem_changed",
        stem(["It costs $99 in 2026.", "Almost every national flag is a window."]),
        [
            want(
                "Q806",
                "FIX",
                "L02 'rectangle' heard as 'window'",
                L02_AT + 6 * 0.35,
                tol=0.01,
            )
        ],
    ),
    case(
        "speech.stem_added",
        stem(
            [
                "It costs $99 in 2026.",
                "Almost every single national flag is a rectangle.",
            ]
        ),
        [want("Q806", "FIX", "L02 extra 'single'", L02_AT + 2 * 0.35, tol=0.01)],
    ),
    case(
        "speech.stem_near",
        stem(["It costs $99 in 2026.", "Almost every nashional flag is a rectangle."]),
        [
            want(
                "Q806",
                "NOTE",
                "L02 'national' heard as 'nashional'",
                L02_AT + 2 * 0.35,
                tol=0.01,
            )
        ],
    ),
    case(
        "speech.stem_hindi",
        stem(["", ""], lang="hi"),
        [want("Q806", "NOTE", msg="English only", empty_ok=True)],
    ),
    case(
        "speech.stem_no_model", no_model, [want("Q806", "NOT CHECKED", msg="not ready")]
    ),
    case(
        "speech.mix_carried",
        mix([t for _, t in LINES]),
        [clean(), want("Q807", "PASS", metric=0.5, mtol=0.002)],
    ),
    case(
        "speech.mix_lost",
        mix([LINES[0][1], "Almost every national flag is."]),
        [
            want(
                "Q807",
                "NOTE",
                "L02 missing 'a rectangle'",
                0.5 + L02_AT + 5 * 0.35,
                tol=0.01,
            )
        ],
    ),
    case(
        "speech.mix_other_take",
        mix([t for _, t in LINES], take=5),
        [want("Q807", "FIX", msg="does not carry")],
    ),
]
