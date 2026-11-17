# qa_quiz.py : does the video carry the facts it is meant to teach? (Q210). The scenario's facts are written as
# quiz.json in the working folder; every answer must be on screen (text_items, alpha 0.5 or more) or in the
# narration. An answer only in the narration is a NOTE (a muted autoplay viewer misses it), one found nowhere a FIX.
# The gate is opt-in: no quiz.json, no rows. Idea from Code2Video's TeachQuiz and Paper2Video's PresentQuiz.
#   python qa_quiz.py [folder]   the rows, then the questions without answers for the reviewer to answer from frames
# quiz.json: {"questions": [{"q": "How far is Mars?", "answer": "225 million km", "keys": ["225", "million", "km"]}]}
# keys is optional (the words of answer); all keys must be found together on one frame (or in one narration line),
# case-insensitive and accent-blind, a number in digits or words.
import importlib.util
import json
import re
import sys
import unicodedata
from pathlib import Path

import contract as C

QUIZ = "quiz.json"
READ_ALPHA = 0.5  # on-screen text counts from this opacity up, as Q209's
TOKEN = re.compile(r"[^\W_]+(?:[.'][^\W_]+)*")  # letters and digits of any script
GAP = "\x00"  # between two strings in a token list: never a token, so a phrase key cannot span two strings


def _norm(s):
    """Lower-case words of s: accents folded (an accented letter matches its plain one), thousands commas dropped
    (1,000 is 1000), punctuation a space."""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = re.sub(r"(?<=\d),(?=\d{3})", "", s)
    return TOKEN.findall(s)


def _joined(strings):
    """One token list for several strings, with GAP between them."""
    out = []
    for s in strings:
        if out:
            out.append(GAP)
        out += _norm(s)
    return out


def _has(hay, run):
    n = len(run)
    return n > 0 and any(hay[i : i + n] == run for i in range(len(hay) - n + 1))


def _readings(tok):
    """The ways a number in digits is said (word lists), through qa_speech when it imports, else none."""
    if not tok.isdigit():
        return []
    try:
        import qa_speech

        return qa_speech._number(tok) or []
    except Exception:  # noqa: BLE001 (qa_speech needs numpy, envs and voice: without them digits match as digits only)
        return []


def _found(hay, key):
    run = _norm(key)
    if _has(hay, run):
        return True
    return len(run) == 1 and any(_has(hay, r) for r in _readings(run[0]))


def _problem(data):
    """Why quiz.json cannot be used, or None."""
    qs = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(qs, list) or not qs:
        return 'it needs {"questions": [...]} with at least one question'
    for i, q in enumerate(qs, 1):
        if not isinstance(q, dict):
            return f"question {i} is not an object"
        for k in ("q", "answer"):
            if not isinstance(q.get(k), str) or not q[k].strip():
                return f"question {i} has no text in {k!r}"
        if "keys" not in q and not _norm(q["answer"]):
            return f"question {i}: its answer has no letter or digit to look for; give keys"
        keys = q.get("keys", _norm(q["answer"]))
        if not isinstance(keys, list) or not keys:
            return f"question {i}: keys must be a non-empty list"
        if not all(isinstance(k, str) and _norm(k) for k in keys):
            return f"question {i}: every key must be a string with a letter or digit"
    return None


def _load_scenes(folder):
    """scenes.py of the folder, imported at the build's size; None when there is none or it does not import."""
    p = Path(folder, "scenes.py")
    if not p.is_file():
        return None
    try:
        import engine as E

        b = C.read_build(folder)
        if b:
            E.W, E.H, E.FPS, E.SS = b
        spec = importlib.util.spec_from_file_location("zt_quiz_scenes", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:  # noqa: BLE001 (a scenes.py that fails here is reported by the gates that need it)
        return None


def _screen(scenes, fps):
    """(frames, why): one token list per distinct screen, the strings text_items(t) reports at alpha READ_ALPHA or
    more on one frame (GAP between strings), and why the screen could not be read in full (None when it was). What
    was read before a failure still counts for an answer it shows; one it does not show is then not known missing."""
    if scenes is None:
        return [], "scenes.py is missing or did not import"
    if not hasattr(scenes, "text_items"):
        return [], "scenes.py has no text_items(t)"
    seen, why = {}, None
    try:
        for i in range(C.frame_of(scenes.DURATION, fps)):
            now = []
            for it in scenes.text_items(i / fps) or []:
                s = it.get("s", it.get("text"))
                if s is not None and float(it.get("alpha", 1.0)) >= READ_ALPHA:
                    now.append(str(s))
            seen.setdefault(tuple(sorted(set(now))), None)
    except Exception as e:  # noqa: BLE001 (any raise in a build's own code: the rest of the screen is unknown)
        why = f"text_items raised {type(e).__name__}: {e}"
    return [_joined(f) for f in seen if f], why


def _narration(folder, scenes):
    """The narration's words as token lists, one per line: every line's text in narration.json (scenes.NARRATION or
    narration/) and its script, else none."""
    rel = getattr(scenes, "NARRATION", None) or "narration/narration.json"
    p = Path(folder, rel)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    lines = data.get("lines", []) if isinstance(data, dict) else data
    bits = []
    for ln in lines if isinstance(lines, list) else []:
        if isinstance(ln, dict) and isinstance(ln.get("text"), str):
            bits.append(ln["text"])
        elif isinstance(ln, str):
            bits.append(ln)
    if isinstance(data, dict) and isinstance(data.get("script"), str):
        bits.append(data["script"])
    return [_norm(b) for b in bits]


def _best(hays, keys):
    """The keys found together in the one token list (a screen or a narration line) that holds the most of them."""
    best = []
    for hay in hays:
        got = [k for k in keys if _found(hay, k)]
        if len(got) > len(best):
            best = got
            if len(best) == len(keys):
                break
    return best


def _read(folder):
    """(questions, None) or (None, the NOT CHECKED row) for quiz.json; (None, None) when there is none."""
    p = Path(folder, QUIZ)
    if not p.is_file():
        return None, None
    fix = f'write {QUIZ} as {{"questions": [{{"q": "...", "answer": "...", "keys": ["..."]}}]}}'
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        why = f"{type(e).__name__}: {e}"
    else:
        why = _problem(data)
        if why is None:
            return data["questions"], None
    return None, C.not_checked("Q210", f"{QUIZ} cannot be used: {why}", fix)


def quiz_rows(folder=".", scenes=None, fps=None):
    """Q210 rows for the quiz.json in folder: one row a question. scenes: the scenes module (None: scenes.py in
    folder, imported at build.json's size); fps: its frame rate (None: build.json's, else 30)."""
    qs, bad = _read(folder)
    if bad:
        return [bad]
    if qs is None:
        return []
    if scenes is None:
        scenes = _load_scenes(folder)
    if fps is None:
        b = C.read_build(folder) if Path(folder, C.BUILD).is_file() else None
        fps = b[2] if b else 30
    (screen, unread), spoken = _screen(scenes, fps), _narration(folder, scenes)
    out = []
    for q in qs:
        keys = q.get("keys", _norm(q["answer"]))
        on = _best(screen, keys)  # together on one frame
        off = [k for k in keys if k not in on]
        heard = _best(spoken, off)  # the rest together in one narration line
        lost = [k for k in off if k not in heard]
        what = f"{q['q']!r} answered {q['answer']!r}"
        if not off:
            out.append(
                C.row(True, "Q210", f"{what}: on screen", "", item=q["q"], considered=1)
            )
        elif unread:
            out.append(
                C.not_checked(
                    "Q210",
                    f"{what}: the on-screen text could not be read ({unread})",
                    "fix scenes.py so it imports and text_items(t) runs for every frame, then run the quiz again",
                    item=q["q"],
                )
            )
        elif not lost:
            out.append(
                C.row(
                    False,
                    "Q210",
                    f"{what}: only the narration carries {', '.join(map(repr, off))}",
                    "show the answer in a text_items(t) string too; a muted autoplay viewer never hears it",
                    note=True,
                    item=q["q"],
                    considered=1,
                )
            )
        else:
            out.append(
                C.row(
                    False,
                    "Q210",
                    f"{what}: {', '.join(map(repr, lost))} on no frame and in no narration line",
                    "put the answer on screen (text_items(t)) or in the narration, or drop the question",
                    item=f"{q['q']} (missing: {', '.join(lost)})",
                    considered=1,
                )
            )
    return out


def check_rows(ctx):
    """Q210 for qa.py check, only with --scenes: quiz.json lives in the build folder (no quiz.json, no rows)."""
    if ctx.scenes is None:
        return []
    return quiz_rows(ctx.workdir, scenes=ctx.scenes, fps=ctx.fps)


def main(argv):
    folder = argv[1] if len(argv) > 1 else "."
    rows = quiz_rows(folder)
    if not rows:
        print(f"no {QUIZ} in {folder}: the quiz gate is opt-in")
        return 0
    for r in rows:
        print(C.line(r))
    qs, _ = _read(folder)
    if qs:
        print("\nAnswer from the frames, without the script:")
        for i, q in enumerate(qs, 1):
            print(f"{i}. {q['q']}".encode("ascii", "backslashreplace").decode("ascii"))
    return C.exit_code(rows)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
