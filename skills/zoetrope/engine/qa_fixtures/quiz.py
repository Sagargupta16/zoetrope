# quiz.py : the quiz gate (Q210, qa_quiz.quiz_rows) on a tiny fake scenes and a quiz.json written into the case's
# folder: the answer on screen, only in the narration (spoken as words), nowhere, a malformed quiz.json, and none.
import json

import qa_quiz

from qa_fixtures import case, want
from qa_fixtures.fake import FPS, make

ASK = {
    "q": "How far is Mars?",
    "answer": "225 million km",
    "keys": ["225", "million", "km"],
}
CARD = {
    "s": "Mars is 225 million km away",
    "box": (100, 100, 500, 140),
    "t_in": 0,
    "t_out": 2.0,
}


def run(fx, quiz, texts=(), narration=None, raw=None):
    fx.tmp.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        (fx.tmp / "quiz.json").write_text(raw, encoding="utf-8")
    elif quiz is not None:
        (fx.tmp / "quiz.json").write_text(json.dumps(quiz), encoding="utf-8")
    if narration:
        (fx.tmp / "narration").mkdir(exist_ok=True)
        lines = [{"id": "L01", "text": narration}]
        (fx.tmp / "narration" / "narration.json").write_text(
            json.dumps({"lines": lines}), encoding="utf-8"
        )
    return qa_quiz.quiz_rows(fx.tmp, make(list(texts), 2.0), FPS)


def absent(fx):
    """No quiz.json: the gate gives no row at all. The case turns that into one PASS row the selftest can judge."""
    rows = run(fx, None, [CARD])
    return [qa_quiz.C.row(True, "Q210", "no rows", "")] if not rows else rows


CASES = [
    case(
        "quiz.on_screen",
        lambda fx: run(fx, {"questions": [ASK]}, [CARD]),
        [want("Q210", "PASS", "How far is Mars?")],
    ),
    case(
        "quiz.narration_only",
        lambda fx: run(
            fx,
            {"questions": [ASK]},
            [{**CARD, "s": "Mars"}],
            "Mars is two hundred twenty five million km away.",
        ),
        [want("Q210", "NOTE", "How far is Mars?", msg="narration")],
    ),
    case(
        "quiz.nowhere",
        lambda fx: run(fx, {"questions": [ASK]}, [{**CARD, "s": "Mars is 225 away"}]),
        [want("Q210", "FIX", "How far is Mars? (missing: million, km)")],
    ),
    case(
        "quiz.split_screens",
        lambda fx: run(
            fx,
            {"questions": [{"q": "What kind of star?", "answer": "red giant"}]},
            [
                {**CARD, "s": "a red car", "t_out": 1.0},
                {**CARD, "s": "a giant leap", "t_in": 1.0},
            ],
        ),
        [want("Q210", "FIX", "What kind of star? (missing: giant)")],
    ),
    case(
        "quiz.accent",
        lambda fx: run(
            fx,
            {"questions": [{"q": "Which city?", "answer": "Z\u00fcrich"}]},
            [{**CARD, "s": "Flights to Zurich"}],
        ),
        [want("Q210", "PASS", "Which city?")],
    ),
    case(
        "quiz.malformed",
        lambda fx: run(fx, None, raw='{"questions": [{"q": "Why?"}]}'),
        [want("Q210", "NOT CHECKED", msg="no text in 'answer'")],
    ),
    case(
        "quiz.unreadable",
        lambda fx: run(fx, None, raw="{not json"),
        [want("Q210", "NOT CHECKED", msg="cannot be used")],
    ),
    case(
        "quiz.absent",
        absent,
        [want("Q210", "PASS", msg="no rows", empty_ok=True)],
    ),
]
