"""Style lint: the house rules of STYLE.md that a program can check, before any reader sees the film.

  python studio/lint.py builds/01-slug [static|frames|all]
      static  timeline.json plus narration/layout.json (and script.json for the payoff), in seconds
      frames  the frame registry, its caption pages and the PNGs in proof/frames (after `studio.py check
              <build> frames`; a registry older than timeline.json counts as missing)
  python studio/lint.py selftest
      one planted-fault fixture and one clean control per rule, from selftest/fixtures/

From code: run(build, tier) -> the number of FIX rows; the rows go to proof/qa_lint.json (static) and
proof/qa_lint_frames.json (frames), one file per tier.
A row is {code, level, t, what, fix}: the rule, FIX or NOTE (or NOT CHECKED when an input is missing),
the moment, the shot and what is wrong, and the change that clears it. Exit 0 PASS, 1 any FIX,
2 NOT CHECKED or a missing input, 64 a usage error.

Every rule quotes the STYLE.md line it enforces (RULES below). A rule never guesses what only a look can
tell (the wrong object, a face, a picture that says more than the words): those go to checklist.py.
Keys a timeline may lack (owner, generated, real, payoff, pages) are derived from what it has, or the
rule is skipped with a NOTE, so the lint also runs on films built before the keys existed.
"""

from __future__ import annotations

import datetime
import json
import os
import re
import struct
import sys
import tempfile
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "selftest" / "fixtures"

RULES = {
    "L01": "A date chip stands only on a picture with nothing of today in it",
    "L02": "no picture is in the clear more than twice in a film / after the payoff every shot is a new picture or a device",
    "L03": "Words on screen never repeat the caption's words in the same frame.",
    "L04": "Every stamp is in the accent",
    "L05": "A list sits on a dark plate, and each outcome turns to the accent as it lands.",
    "L06": "A source line on a generated picture says what it is",
    "L07": "A number is never on screen before its spoken word / A count lands by the clock on its spoken word.",
    "L08": "The picture changes three times in the first 3.5 s: count the cuts and punch-ins before review.",
    "L09": "At most three whips or zooms in a film / never two in a row",
    "L10": "The top row (y 282 to 345) belongs to one chip on the left and the film's tag on the right.",
    "L11": "A row of a word card stands lit 2 s or more",
    "L12": "A drawn diagram is as bright as the pictures around it (mean brightness 60 of 255 or more)",
    "L13": "A caption page never drops the NOT of its sentence",
    "L14": "One still never carries two dates or two places.",
    "L15": "lower third 70, five words or fewer on one line",
    "L16": "A present-day claim on a chip carries its year",
    "L17": "A photoreal picture under a real name is a P0, whatever the tag says.",
    "L18": "A redrawn document stands on a plain plate drawn by the stage",
}
TIERS = {"static", "frames", "all"}

# A date within this many years of today needs no period look: a chip that says when a claim holds
# (AS OF 19 NOV 2026, the 2023 fault of a spacecraft still flying) is not a flashback (film 01).
RECENT_YEARS = 5
# words that make a chip a claim about the present; NOW only as a date word (NOW: X, AS OF NOW), never in
# an instruction (TRY IT NOW, film 02)
PRESENT = r"\b(today|nowadays|currently|current)\b|^\s*now\b\s*[:,]|\b(as of|until|by|right|up to) now\b"
TOP_ROW = (270, 345)  # y of a chip in the top row
LIT_MIN = 2.0  # L11: seconds a word-card row stands after it lights
BRIGHT_MIN = 60.0  # L12: mean luma of a drawn diagram or a plate
FILM_DARKER = 8.0  # L12: and this much under the median frame of the film ("the pictures around it")
LAND_TOL = 0.1  # L07: seconds a count may land from its word
SOURCE_KINDS = re.compile(
    r"\b(fact from|sources?|journals?|study|studies|data|translated|translation|quoted|redrawn)\b",
    re.IGNORECASE,
)
# small words a credit line may hold in lower case (book 12, page 204, and, of)
CREDIT_SMALL = {
    "book",
    "page",
    "p",
    "pp",
    "vol",
    "no",
    "and",
    "of",
    "the",
    "by",
    "in",
    "on",
    "for",
    "ed",
    "eds",
    "et",
    "al",
}
# the caption pager in kit.js opens a page on the same words (and on any word ending in n't); selftest.py compares the lists
NEGATORS = {"not", "no", "never", "nobody", "nothing", "none"}
# "no longer", "not yet": the second word belongs to the negator, so a page ending on it drops the NOT too
NEGATOR_TAILS = {"longer", "yet", "one", "more", "even", "again"}
MONTHS = (
    "january february march april may june july august september october november december "
    "jan feb mar apr jun jul aug sep sept oct nov dec"
).split()
STOP = set(
    """a an the of to in on at for and or but nor is are was were be been being it its it's this that these those
    with by from as so do does did has have had you your we our us they their them he she his her i me my what which
    who whom how why when where there here then than also just only very can could will would should may might
    must not no never one ones into onto out up down over about all any each every some more most such own same
    still yet again now if into off too it is let lets""".split()
)
TEXT_SKIP = {
    "source",
    "end",
    "punch",
    "hush",
    "light",
    "topshade",
    "ground",
    "plate",
    "veil",
    "iris",
    "steady",
}
# Overlays that are type on a picture, not a drawn device (after the payoff a reused picture needs a device).
TYPE_ONLY = {
    "label",
    "source",
    "title",
    "hook",
    "lower",
    "lowerstand",
    "callout",
    "stamp",
    "number",
    "quote",
    "chip",
    "note",
    "hedge",
    "notice",
    "end",
} | TEXT_SKIP
WORD_CARDS = {
    "ladder",
    "answers",
    "words",
    "reasons",
    "steps",
    "stepsrow",
    "stack",
    "tests",
    "suspects",
    "lawlist",
    "ledger",
}


def row(
    rows: list[dict], code: str, level: str, when: float | None, what: str, fix: str
) -> None:
    rows.append(
        {
            "code": code,
            "level": level,
            "t": None if when is None else round(when, 2),
            "what": what,
            "fix": fix,
        }
    )


def load_json(path: Path) -> object | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---- reading a timeline


class Film:
    """A timeline with the keys the rules read, derived when an older timeline lacks them."""

    def __init__(self, build: Path):
        self.build = build
        self.tl = load_json(build / "timeline.json")
        self.layout = load_json(build / "narration" / "layout.json")
        self.script = load_json(build / "script.json") or {}
        if not isinstance(self.tl, dict):
            return
        self.shots = self.tl["shots"]
        self.tokens = self.tl.get("tokens") or []
        self.silent = (self.tl.get("mute") or []) + (self.tl.get("says") or [])
        self.exempt = self.tl.get("exempt") or []
        self.today = self._today()
        for index, shot in enumerate(self.shots):
            shot["_i"] = index

    def _today(self) -> int:
        stamp = str(self.tl.get("today") or "")
        return (
            int(stamp[:4])
            if re.fullmatch(r"\d{4}.*", stamp)
            else datetime.date.today().year
        )

    def kind(self, shot: dict) -> str:
        return (shot.get("media") or {}).get("kind", "none")

    def generated(self, shot: dict) -> bool:
        if "generated" in shot:
            return bool(shot["generated"])
        return self.kind(shot) in ("clip", "still")

    def owner(self, shot: dict) -> str:
        if shot.get("owner"):
            return shot["owner"]
        media = shot.get("media") or {}
        found = re.search(
            r"media/([^/.]+)", str(media.get("dir") or media.get("src") or "")
        )
        return found.group(1) if found else shot["id"]

    def blurred(self, shot: dict) -> bool:
        return shot.get("grade") == "blur"

    def clear(self, shot: dict) -> bool:
        return self.generated(shot) and not self.blurred(shot)

    def endcard(self, shot: dict) -> bool:
        return any(o.get("type") == "end" for o in shot.get("over", []))

    def tagged(self, shot: dict) -> bool:
        if not self.tl.get("tag") or shot.get("tag") is False:
            return False
        return self.generated(shot) or shot.get("tag") is True

    def free(self, moment: float) -> bool:
        return any(a - 0.01 <= moment < b for a, b in self.exempt)

    def test_card(self, moment: float) -> bool:
        """Inside a test (an exempt shot) or a quiet-caption hold."""
        spans = self.exempt + (self.tl.get("quiet") or [])
        return any(a - 0.01 <= moment < b for a, b in spans)

    def end_of(self, shot: dict, spec: dict) -> float:
        return spec["out"] if spec.get("out") is not None else shot["t1"]

    def shown(self, token: dict) -> bool:
        """Whether a caption page carries this spoken word (pages beginning in a muted or 'says' span never show)."""
        return not any(a - 0.05 <= token["t0"] < b for a, b in self.silent)

    def payoff(self) -> float | None:
        found = self.tl.get("payoff")
        if isinstance(found, dict) and isinstance(found.get("t"), (int, float)):
            return float(found["t"])
        for line in self.script.get("lines", []):
            if line.get("payoff") or line.get("beat") == "payoff":
                for spoken in (self.layout or {}).get("lines", []):
                    if spoken["id"] == line["id"]:
                        return float(spoken["t0"])
        return None

    def line_at(self, t0: float, t1: float) -> str:
        ids = []
        for token in self.tokens:
            if t0 <= token["t0"] < t1 and token["line"] not in ids:
                ids.append(token["line"])
        return ",".join(ids)


def plain(text: object) -> str:
    return re.sub(r"[*\[\]]", "", str(text or ""))


def text_of(spec: dict) -> str:
    parts = [plain(line) for line in spec.get("lines") or [] if isinstance(line, str)]
    for key in ("prefix", "text", "who", "sub", "unit", "say"):
        if isinstance(spec.get(key), str):
            parts.append(plain(spec[key]))
    if spec.get("type") == "number" and isinstance(spec.get("value"), (int, float)):
        parts.append(number_text(spec["value"], spec.get("decimals", 0)))
    return " ".join(parts)


def number_text(value: float, decimals: int = 0) -> str:
    return f"{value:.{decimals}f}"


def words(text: str) -> list[str]:
    return re.findall(
        r"[a-z0-9]+(?:[.,'][a-z0-9]+)*", text.lower().replace("\u2019", "'")
    )


SHORT_MONTHS = {
    "jan": "january",
    "feb": "february",
    "mar": "march",
    "apr": "april",
    "jun": "june",
    "jul": "july",
    "aug": "august",
    "sep": "september",
    "sept": "september",
    "oct": "october",
    "nov": "november",
    "dec": "december",
}


def norm(word: str) -> str:
    word = word.replace(",", "")
    if re.fullmatch(r"\d+(\.\d+)?", word):
        return word
    word = SHORT_MONTHS.get(word, word.split("'")[0])
    return (
        word[:-1]
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss")
        else word
    )


def content(text: str) -> set[str]:
    return {norm(w) for w in words(text) if w not in STOP and norm(w) not in STOP}


def numbers(found: set[str]) -> set[str]:
    """Figures that identify a fact on their own: two digits or more, or a decimal."""
    return {w for w in found if re.fullmatch(r"\d{2,}|\d+\.\d+", w)}


def years(text: str) -> list[int]:
    return [int(y) for y in re.findall(r"(?<!\d)(\d{4})(?!\d)", text)]


def recent(text: str, today: int) -> bool:
    found = years(text)
    return bool(found) and min(found) >= today - RECENT_YEARS


DAY_DATE = re.compile(
    r"\b(\d{1,2})\s+("
    + "|".join(MONTHS)
    + r")\.?,?\s+(\d{3,4})\b|\b("
    + "|".join(MONTHS)
    + r")\.?\s+(\d{1,2}),?\s+(\d{3,4})\b",
    re.IGNORECASE,
)


def date_marks(text: str) -> frozenset[str]:
    """The dates a chip states, with the word that qualifies them (UNTIL 1492 is not 1492)."""
    low = plain(text).lower()
    marks = re.findall(
        r"(?:(until|before|after|by|from|since|about|circa|c\.)\s+(?:the\s+)?)?"
        r"(\d{1,4}(?:st|nd|rd|th)?\s+century(?:\s+bce|\s+ce|\s+bc|\s+ad)?|\d{1,4}s?(?:\s+bce|\s+ce|\s+bc|\s+ad)?)",
        low,
    )
    found = {
        f"{q} {d}".strip() for q, d in marks if re.search(r"\d{3,4}|century|\d0s", d)
    }
    found |= {m for m in MONTHS[:12] if re.search(rf"\b{m}\b", low)}
    return frozenset(found)


# ---- static rules


def l01(film: Film, rows: list[dict]) -> None:
    for shot in film.shots:
        if not film.clear(shot) or film.endcard(shot) or shot.get("grade") == "past":
            continue
        for spec in shot["over"]:
            if (
                spec.get("type") == "label"
                and spec.get("tone") == "accent"
                and not recent(spec.get("text", ""), film.today)
            ):
                row(
                    rows,
                    "L01",
                    "FIX",
                    spec["at"],
                    f'{shot["id"]}: date chip "{plain(spec.get("text"))}" on a generated picture in grade {shot.get("grade", "none")}',
                    'set "grade": "past" on a picture with nothing of today in it, or blur the plate and set the date as type',
                )


def l02(film: Film, rows: list[dict]) -> None:
    runs: list[dict] = []  # a run of cut-ins on one picture is one use
    for shot in film.shots:
        if not film.generated(shot) or film.endcard(shot):
            continue
        owner = film.owner(shot)
        last = runs[-1] if runs else None
        if last and last["owner"] == owner and last["end"] == shot["_i"] - 1:
            last["end"] = shot["_i"]
            last["clear"] = last["clear"] or film.clear(shot)
            last["device"] = last["device"] and has_device(shot)
            continue
        runs.append(
            {
                "owner": owner,
                "start": shot["_i"],
                "end": shot["_i"],
                "clear": film.clear(shot),
                "device": has_device(shot),
                "t": shot["t0"],
                "id": shot["id"],
            }
        )
    by_owner: dict[str, list[dict]] = {}
    for run in runs:
        by_owner.setdefault(run["owner"], []).append(run)
    for owner, uses in by_owner.items():
        clear = [u for u in uses if u["clear"]]
        if len(clear) > 2:
            row(
                rows,
                "L02",
                "FIX",
                clear[2]["t"],
                f"picture {owner} is in the clear {len(clear)} times ({', '.join(u['id'] for u in clear)})",
                "a new picture or a device for every use after the second",
            )
        elif len(uses) > 2:
            row(
                rows,
                "L02",
                "NOTE",
                uses[2]["t"],
                f"picture {owner} is used {len(uses)} times, {len(uses) - len(clear)} of them blurred ({', '.join(u['id'] for u in uses)})",
                "fine when the blur cannot be recognised; otherwise a new picture",
            )
    payoff = film.payoff()
    if payoff is None:
        row(
            rows,
            "L02",
            "NOTE",
            None,
            "no payoff line is marked, so the after-the-payoff rule is not checked",
            'mark the payoff line in script.json ("payoff": true)',
        )
        return
    opening = runs[0]["owner"] if runs else None
    for owner, uses in by_owner.items():
        for index, run in enumerate(uses):
            if run["t"] < payoff - 0.01 or not index:
                continue
            if owner == opening and run is runs[-1]:
                continue  # the close returns to the opening picture so the last frame loops into the first
            seen = [u for u in uses[:index] if u["clear"]]
            if not seen or run["device"]:
                continue  # a drawn device over the picture is new on screen
            level = "FIX" if run["clear"] else "NOTE"
            row(
                rows,
                "L02",
                level,
                run["t"],
                f"{run['id']} after the payoff ({payoff:.2f} s) shows picture {owner} again (first at {seen[0]['id']})",
                "after the payoff every shot is a new picture or a device",
            )


def window(film: Film, t0: float, t1: float) -> list[dict]:
    return [
        token
        for token in film.tokens
        if t0 - 0.03 <= token["t0"] < t1 and film.shown(token)
    ]


def l03(film: Film, rows: list[dict]) -> None:
    for shot in film.shots:
        if shot.get("captions") is False:
            continue
        for spec in shot["over"]:
            kind = spec.get("type")
            if kind in TEXT_SKIP or spec.get("says"):
                continue
            mine = content(text_of(spec))
            if not mine:
                continue
            spoken = window(film, spec["at"], film.end_of(shot, spec))
            heard = content(" ".join(token["d"] for token in spoken))
            if (
                kind
                in ("label", "lower", "lowerstand", "callout", "chip", "note", "hedge")
                and mine - heard
            ):
                continue  # the chip adds what the voice does not say (a date, a place, a source)
            if kind == "stamp" and any(re.fullmatch(r"\d+", w) for w in mine - heard):
                continue  # a stamp that adds a figure or a day the voice does not say
            hit = None
            for index in range(len(spoken)):
                page = content(
                    " ".join(token["d"] for token in spoken[index : index + 4])
                )
                shared = mine & page
                if len(shared) >= 2 or numbers(shared):
                    hit = (spoken[index]["t0"], shared)
                    break
            if hit:
                # On a test card the list is whole from its first frame and the voice reads it (STYLE: "A list
                # the viewer must read before acting is whole and white"): a NOTE there (film 02, READY).
                quiet = film.test_card(hit[0])
                row(
                    rows,
                    "L03",
                    "NOTE" if quiet else "FIX",
                    hit[0],
                    f'{shot["id"]} {kind} "{text_of(spec)[:40]}" repeats the caption ({", ".join(sorted(hit[1]))})',
                    'give the overlay "says": true (the caption page is left out), or reword it to add a date, place or source',
                )


def l04(film: Film, rows: list[dict]) -> None:
    for shot in film.shots:
        for spec in shot["over"]:
            if spec.get("type") == "stamp" and spec.get("tone") not in (None, "accent"):
                row(
                    rows,
                    "L04",
                    "NOTE" if film.free(spec["at"]) else "FIX",
                    spec["at"],
                    f'{shot["id"]}: stamp "{plain(spec.get("text"))}" is {spec["tone"]}',
                    "drop the tone: a stamp is in the accent (green reads as verified)",
                )


def has_device(shot: dict) -> bool:
    return any(o.get("type") not in TYPE_ONLY for o in shot.get("over", []))


def on_ground(shot: dict) -> bool:
    media = shot.get("media") or {}
    return media.get("graphic") == "ground" or any(
        o.get("type") == "ground" for o in shot.get("over", [])
    )


def l05(film: Film, rows: list[dict]) -> None:
    for shot in film.shots:
        for spec in shot["over"]:
            if spec.get("type") != "ladder":
                continue
            if not spec.get("plate"):
                row(
                    rows,
                    "L05",
                    "NOTE" if on_ground(shot) else "FIX",
                    spec["at"],
                    f"{shot['id']}: ladder without its dark plate",
                    'add "plate": true',
                )
            for item in spec.get("rows") or []:
                if item.get("state") == "reveal" and not item.get("hot"):
                    row(
                        rows,
                        "L05",
                        "FIX",
                        item.get("at", spec["at"]),
                        f'{shot["id"]}: ladder row "{plain(item.get("label"))}" lands in white',
                        'add "hot": true so the outcome turns to the accent as it lands',
                    )


def l06(film: Film, rows: list[dict]) -> None:
    for shot in film.shots:
        if not film.clear(shot) or film.endcard(shot):
            continue
        for spec in shot["over"]:
            if (
                spec.get("type") != "source"
                or spec.get("standing")
                and _carried(film, shot, spec)
            ):
                continue
            text = plain(spec.get("text"))
            if not SOURCE_KINDS.search(text) and credit_like(text):
                row(
                    rows,
                    "L06",
                    "FIX",
                    spec["at"],
                    f'{shot["id"]}: source line "{text}" does not say what it is',
                    "say its kind: 'Fact from: ...', 'Journal: ...', 'Source: ...', '..., translated by ...'",
                )
            elif not years(text) and (SOURCE_KINDS.search(text) or credit_like(text)):
                row(
                    rows,
                    "L06",
                    "NOTE",
                    spec["at"],
                    f'{shot["id"]}: source line "{text}" has no year',
                    "add the year of the source",
                )


def credit_like(text: str) -> bool:
    """A line of names (Pliny, Natural History, book 12) reads as the picture's credit; a line that describes a
    figure in plain words (Gap roughly 5.5 degrees wide; to scale, our arithmetic) does not."""
    if re.search(r"\b(our|ours|we)\b", text, re.IGNORECASE):
        return False
    names = [
        w
        for w in re.findall(r"[A-Za-z][A-Za-z'.&-]*", text)
        if w.lower() not in CREDIT_SMALL
    ]
    return bool(names) and all(w[0].isupper() for w in names)


def _carried(film: Film, shot: dict, spec: dict) -> bool:
    """A standing overlay that continues the same one on the shot before (reported once, on its first shot)."""
    if not shot["_i"]:
        return False
    before = film.shots[shot["_i"] - 1]
    return any(
        o.get("type") == spec.get("type") and text_of(o) == text_of(spec)
        for o in before["over"]
    )


def outexpo_hit(span: float, step: float) -> float:
    """The share of an outExpo count at which the shown value first rounds to the last one."""
    if span <= 0:
        return 0.0
    need = max(0.0, 1 - (step / 2) / span)
    if need >= 1:
        return 1.0
    import math

    return min(1.0, -math.log2(1 - need) / 10)


def matching(film: Film, value: float, t0: float, t1: float) -> dict | None:
    for token in film.tokens:
        if t0 - 0.5 <= token["t0"] < t1:
            try:
                said = float(token["d"].replace(",", ""))
            except ValueError:
                continue
            if abs(said - value) < 1e-6:
                return token
    return None


def counted(spec: dict) -> bool:
    """A count whose value, from, to and landAt are numbers: build refuses any other, the lint skips it."""
    return isinstance(spec.get("value"), (int, float)) and all(
        isinstance(spec[key], (int, float))
        for key in ("from", "to", "landAt")
        if spec.get(key) is not None
    )


def l07(film: Film, rows: list[dict]) -> None:
    for shot in film.shots:
        for spec in shot["over"]:
            kind = spec.get("type")
            end = film.end_of(shot, spec)
            if kind == "number" and counted(spec):
                value, dec = float(spec["value"]), int(spec.get("decimals") or 0)
                word = matching(film, value, spec["at"], end)
                if word is None:
                    continue  # never spoken while it stands (or said before it): nothing to land on
                dur = spec.get("count", 1.1)
                if "landAt" in spec:
                    shows = float(spec["landAt"])
                    why = f"lands at {shows:.2f}"
                elif not dur:
                    shows = spec["at"]
                    why = f"is printed whole at {shows:.2f}"
                else:
                    span = abs(value - float(spec.get("from") or 0))
                    shows = spec["at"] + 0.05 + dur * outexpo_hit(span, 10.0**-dec)
                    why = f"has no landAt and its eased count shows {number_text(value, dec)} at {shows:.2f}"
                if abs(shows - word["t0"]) > LAND_TOL:
                    row(
                        rows,
                        "L07",
                        "FIX" if shows < word["t0"] else "NOTE",
                        shows,
                        f"{shot['id']}: number {number_text(value, dec)} {why}; the word is spoken at {word['t0']:.2f}",
                        f'set "landAt" to the word\'s cue (it lands by the clock, within {LAND_TOL} s)',
                    )
            elif kind in ("rail", "years") and isinstance(spec.get("to"), (int, float)):
                word = matching(film, float(spec["to"]), spec["at"], end)
                if word is None:
                    continue
                if not isinstance(spec.get("until"), (int, float)):
                    row(
                        rows,
                        "L07",
                        "FIX",
                        spec["at"],
                        f'{shot["id"]}: {kind} ends on {spec["to"]} with no "until"; the word is at {word["t0"]:.2f}',
                        'set "until" to the word\'s cue',
                    )
                elif abs(spec["until"] - word["t0"]) > LAND_TOL:
                    row(
                        rows,
                        "L07",
                        "FIX" if spec["until"] < word["t0"] else "NOTE",
                        spec["until"],
                        f"{shot['id']}: {kind} lands {spec['to']} at {spec['until']:.2f}, the word at {word['t0']:.2f}",
                        'set "until" to the word\'s cue',
                    )


def l08(film: Film, rows: list[dict]) -> None:
    if not film.shots or film.free(0.0):
        return
    changes = {round(shot["t0"], 2) for shot in film.shots if 0 < shot["t0"] <= 3.5}
    for shot in film.shots:
        for spec in shot["over"]:
            if spec.get("type") == "punch" and 0 < spec["at"] <= 3.5:
                changes.add(round(spec["at"], 2))
    if len(changes) < 3:
        row(
            rows,
            "L08",
            "FIX",
            0.0,
            f"{len(changes)} picture change(s) in the first 3.5 s",
            "three or more cuts or punch-ins before 3.5 s",
        )


def l09(film: Film, rows: list[dict]) -> None:
    big = [
        shot
        for shot in film.shots
        if (shot.get("tin") or {}).get("kind") in ("whip", "zoom")
    ]
    if len(big) > 3:
        row(
            rows,
            "L09",
            "FIX",
            big[3]["t0"],
            f"{len(big)} whips or zooms ({', '.join(s['id'] for s in big)})",
            "three at most: make the rest hard cuts",
        )
    for before, after in zip(film.shots, film.shots[1:]):
        if before in big and after in big:
            row(
                rows,
                "L09",
                "FIX",
                after["t0"],
                f"{before['id']} and {after['id']} are two whips or zooms in a row",
                "a hard cut between them",
            )


def l10(film: Film, rows: list[dict]) -> None:
    for shot in film.shots:
        if not film.tagged(shot):
            continue
        for spec in shot["over"]:
            if (
                spec.get("type") != "label"
                or not TOP_ROW[0] <= spec.get("y", 440) <= TOP_ROW[1]
            ):
                continue
            text = plain(spec.get("text"))
            if len(text) > 30 and not _carried(film, shot, spec):
                row(
                    rows,
                    "L10",
                    "FIX",
                    spec["at"],
                    f'{shot["id"]}: top-row chip "{text}" has {len(text)} characters beside the tag',
                    "30 characters or fewer in the top row, or move the chip to y 352",
                )


def l11(film: Film, rows: list[dict]) -> None:
    for shot in film.shots:
        for spec in shot["over"]:
            if spec.get("type") not in WORD_CARDS and not (
                isinstance(spec.get("rows"), list)
                and spec.get("type") not in ("compare", "strip", "tiles")
            ):
                continue
            if _carried(film, shot, spec) and spec.get("standing"):
                continue
            end = film.end_of(shot, spec)
            nxt = shot["_i"] + 1
            while nxt < len(film.shots):
                twin = next(
                    (o for o in film.shots[nxt]["over"] if same_card(o, spec)), None
                )
                if twin is None or twin["at"] > film.shots[nxt]["t0"] + 0.05:
                    break
                end = film.end_of(film.shots[nxt], twin)
                nxt += 1
            for item in spec.get("rows") or spec.get("steps") or []:
                if not isinstance(item, dict):
                    continue
                lit = item.get("hotAt", item.get("at"))
                if not isinstance(lit, (int, float)) or lit < spec["at"] - 0.01:
                    continue  # no cue, or a time relative to the device
                if lit >= film.end_of(shot, spec) - 0.01:
                    continue  # it lights on a later shot (or never): judged there
                if end - lit < LIT_MIN - 0.05:
                    name = plain(
                        item.get("text")
                        or item.get("latin")
                        or item.get("label")
                        or item.get("what")
                        or ""
                    )
                    row(
                        rows,
                        "L11",
                        "FIX",
                        lit,
                        f'{shot["id"]} {spec["type"]}: row "{name[:30]}" stands lit {end - lit:.2f} s',
                        f"{LIT_MIN:.0f} s or more: lengthen the pause after the line, never run the card under the next line",
                    )


def card_rows(spec: dict) -> list[str]:
    return [
        plain(
            r.get("text")
            or r.get("latin")
            or r.get("label")
            or r.get("what")
            or r.get("script")
            or ""
        )
        for r in spec.get("rows") or spec.get("steps") or []
        if isinstance(r, dict)
    ]


def same_card(other: dict, spec: dict) -> bool:
    return other.get("type") == spec.get("type") and card_rows(other) == card_rows(spec)


def l14(film: Film, rows: list[dict]) -> None:
    dates: dict[str, dict] = {}
    lines: dict[str, set] = {}
    for shot in film.shots:
        if not film.clear(shot) or film.endcard(shot):
            continue  # a blurred plate under type is no longer the picture
        owner = film.owner(shot)
        for spec in shot["over"]:
            if spec.get("type") == "label" and spec.get("tone") == "accent":
                # the day and month only make a date more precise (1498, then 20 MAY 1498)
                marks = frozenset(
                    m for m in date_marks(spec.get("text", "")) if m not in MONTHS
                )
                if marks:
                    dates.setdefault(owner, {}).setdefault(
                        marks, (shot["id"], plain(spec.get("text")), spec["at"])
                    )
        lines.setdefault(owner, set()).add(film.line_at(shot["t0"], shot["t1"]))
    for owner, found in dates.items():
        if len(found) > 1:
            first, second = list(found.values())[:2]
            row(
                rows,
                "L14",
                "FIX",
                second[2],
                f'picture {owner} carries two dates: "{first[1]}" ({first[0]}) and "{second[1]}" ({second[0]})',
                "one picture, one date: a new picture or the past grade for the other",
            )


def l15(film: Film, rows: list[dict]) -> None:
    for shot in film.shots:
        for spec in shot["over"]:
            if spec.get("type") in ("lower", "lowerstand"):
                count = len(plain(spec.get("text")).split())
                if count > 5 and not _carried(film, shot, spec):
                    row(
                        rows,
                        "L15",
                        "FIX",
                        spec["at"],
                        f'{shot["id"]}: lower third "{plain(spec.get("text"))}" has {count} words',
                        "five words or fewer on one line",
                    )


def chips_of(shot: dict) -> list[tuple[str, float]]:
    """Every chip of a shot with the time it lands: label, callout and chip overlays, and a row's `ours` and
    `extra`, our own notes on a word card or a redrawn document (film 04 before its third pass: a reader
    found TODAY: MOSTLY PEANUT on the dictionary card)."""
    chips = []
    for spec in shot["over"]:
        if spec.get("type") in ("label", "callout", "chip"):
            chips.append((plain(spec.get("text")), spec["at"]))
        listed = spec.get(
            "rows"
        )  # a list of rows on a card; a count on some devices (film 01)
        for item in listed if isinstance(listed, list) else []:
            if not isinstance(item, dict):
                continue
            at = item.get("at")
            when = (
                at if isinstance(at, (int, float)) and at >= shot["t0"] else spec["at"]
            )
            chips += [
                (plain(item[key]), when)
                for key in ("ours", "extra")
                if isinstance(item.get(key), str)
            ]
    return chips


def l16(film: Film, rows: list[dict]) -> None:
    for shot in film.shots:
        # a standing chip that continues from the shot before is reported once, on its first shot
        before = (
            {text for text, _ in chips_of(film.shots[shot["_i"] - 1])}
            if shot["_i"]
            else set()
        )
        for text, when in chips_of(shot):
            if (
                re.search(PRESENT, text, re.IGNORECASE)
                and not years(text)
                and text not in before
            ):
                row(
                    rows,
                    "L16",
                    "FIX",
                    when,
                    f'{shot["id"]}: present-day chip "{text}" has no year',
                    f"add the year ({film.today}: ...)",
                )


def l17(film: Film, rows: list[dict]) -> None:
    for shot in film.shots:
        if not film.clear(shot) or film.endcard(shot):
            continue
        if shot.get("real") or any(o.get("real") is True for o in shot["over"]):
            row(
                rows,
                "L17",
                "FIX",
                shot["t0"],
                f"{shot['id']}: a generated picture in the clear under a real name",
                "our own drawing, or type on a blurred plate",
            )
            continue
        for spec in shot["over"]:
            if spec.get("type") not in (
                "label",
                "lower",
                "lowerstand",
                "callout",
                "title",
            ):
                continue
            text = text_of(spec)
            if (
                DAY_DATE.search(text)
                and not recent(text, film.today)
                and not _carried(film, shot, spec)
            ):
                row(
                    rows,
                    "L17",
                    "FIX",
                    spec["at"],
                    f'{shot["id"]}: the day "{text}" stands on a generated picture in the clear',
                    "type on a blurred plate, our own drawing, or the day in the source line",
                )


def l18(film: Film, rows: list[dict]) -> None:
    for shot in film.shots:
        under = (
            film.generated(shot)
            or bool((shot.get("media") or {}).get("src"))
            or any(o.get("type") == "plate" for o in shot["over"])
        )
        for spec in shot["over"]:
            if spec.get("type") in ("document", "dict") and under:
                row(
                    rows,
                    "L18",
                    "FIX",
                    spec["at"],
                    f"{shot['id']}: a redrawn document over a generated picture",
                    'stand it on the stage\'s plain plate ("media": {"kind": "none", "graphic": "ground"})',
                )


STATIC = (
    l01,
    l02,
    l03,
    l04,
    l05,
    l06,
    l07,
    l08,
    l09,
    l10,
    l11,
    l14,
    l15,
    l16,
    l17,
    l18,
)


# ---- frames rules


def stale_frames(build: Path) -> bool:
    path, timeline = (
        build / "proof" / "frames" / "registry.json",
        build / "timeline.json",
    )
    return (
        path.exists()
        and timeline.exists()
        and path.stat().st_mtime < timeline.stat().st_mtime
    )


def registry_of(build: Path) -> dict | None:
    """The frame registry, or None when it is missing or older than timeline.json (shot from another timeline)."""
    path = build / "proof" / "frames" / "registry.json"
    if stale_frames(build):
        return None
    found = load_json(path)
    return (
        found
        if isinstance(found, dict) and isinstance(found.get("frames"), dict)
        else None
    )


def shot_at(film: Film, moment: float) -> dict | None:
    for shot in film.shots:
        if shot["t0"] - 0.001 <= moment < shot["t1"]:
            return shot
    return film.shots[-1] if film.shots and moment >= film.shots[-1]["t0"] else None


def tag_box(film: Film, boxes: list[dict]) -> dict | None:
    tag = str(film.tl.get("tag") or "")
    return next(
        (b for b in boxes if tag and b.get("text", "").strip().lower() == tag.lower()),
        None,
    )


def letters(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def caption_words(film: Film, text: str, moment: float) -> str:
    """A caption box's text with its spaces back: the registry joins the word spans without them
    (Itcomesfrom), so the run of spoken tokens it spells gives the words."""
    target = letters(text)
    near = [t for t in film.tokens if moment - 4 <= t["t0"] <= moment + 2.5]
    for start in range(len(near)):
        joined = ""
        for end in range(start, len(near)):
            joined += letters(near[end]["d"])
            if joined == target:
                return " ".join(t["d"] for t in near[start : end + 1])
            if not target.startswith(joined):
                break
    return text


def inside(said: set[str], text: str) -> set[str]:
    """Caption words found in a box whose lines the registry joined without a space: figures whole, words
    of four letters or more inside the run of letters."""
    figures = set(re.findall(r"\d+(?:\.\d+)?", text.replace(",", "")))
    run = letters(text)
    return {
        w
        for w in said
        if (w in figures if w[0].isdigit() else len(w) >= 4 and w in run)
    }


def f03(film: Film, registry: dict, rows: list[dict]) -> None:
    """L03 on the frames: a caption box against the type standing beside it (labels are judged in the static tier)."""
    seen = set()
    for key, boxes in sorted(registry["frames"].items(), key=lambda kv: float(kv[0])):
        moment = float(key)
        shot = shot_at(film, moment)
        captions = [
            b for b in boxes if b.get("role") == "caption" and b.get("opacity", 1) > 0.5
        ]
        if not captions or shot is None:
            continue
        said = content(
            " ".join(caption_words(film, b.get("text", ""), moment) for b in captions)
        )
        for box in boxes:
            if (
                box.get("role") not in ("hook", "headline", "stamp", "number")
                or box.get("opacity", 1) <= 0.5
            ):
                continue  # chips and lower thirds are judged in the static tier, list rows light on their word
            shared = inside(said, box.get("text", ""))
            figures = set(re.findall(r"\d+", box.get("text", "").replace(",", "")))
            if box["role"] == "stamp" and figures - said:
                continue  # a stamp that adds a day or a figure the caption does not say
            mark = (shot["id"], box.get("text"))
            if (len(shared) >= 2 or numbers(shared)) and mark not in seen:
                seen.add(mark)
                row(
                    rows,
                    "L03",
                    "NOTE" if film.test_card(moment) else "FIX",
                    moment,
                    f'{shot["id"]} {box["role"]} "{box.get("text", "")[:40]}" stands over the caption ({", ".join(sorted(shared))})',
                    'give the device "says": true, or reword it',
                )


def f07(film: Film, registry: dict, rows: list[dict]) -> None:
    keys = {round(float(k), 2): k for k in registry["frames"]}
    missing = []
    for shot in film.shots:
        for spec in shot["over"]:
            if spec.get("type") != "number" or "landAt" not in spec:
                continue
            if not counted(spec):
                continue  # a text value or landAt: build refuses it, the lint never crashes on it
            land, final = (
                float(spec["landAt"]),
                number_text(float(spec["value"]), int(spec.get("decimals") or 0)),
            )
            for moment, want in ((land - 0.1, False), (land + 0.1, True)):
                key = next((keys[k] for k in keys if abs(k - moment) <= 0.02), None)
                if key is None:
                    missing.append(f"{moment:.2f}")
                    continue
                shown = " ".join(
                    b.get("text", "")
                    for b in registry["frames"][key]
                    if b.get("role") == "number"
                )
                has = final.replace(",", "") in shown.replace(",", "")
                if has != want:
                    row(
                        rows,
                        "L07",
                        "FIX",
                        moment,
                        f'{shot["id"]}: number reads "{shown}" {"before" if not want else "after"} its word ({land:.2f})',
                        "the last value shows from the word on, never before it",
                    )
    if missing:
        row(
            rows,
            "L07",
            "NOTE",
            None,
            f"no frame at {len(missing)} count moment(s), so the landing is not looked at",
            "python studio/studio.py check <build> frames",
        )


def f10(film: Film, registry: dict, rows: list[dict]) -> None:
    seen = set()
    for key, boxes in sorted(registry["frames"].items(), key=lambda kv: float(kv[0])):
        tag = tag_box(film, boxes)
        shot = shot_at(film, float(key))
        if tag is None or shot is None:
            continue
        for box in boxes:
            if (
                box is tag
                or box.get("role") != "label"
                or box["y"] > TOP_ROW[1]
                or box["y"] + box["h"] < TOP_ROW[0]
            ):
                continue
            if (
                box["x"] + box["w"] > tag["x"] - 16
                and (shot["id"], box.get("text")) not in seen
            ):
                seen.add((shot["id"], box.get("text")))
                row(
                    rows,
                    "L10",
                    "FIX",
                    float(key),
                    f'{shot["id"]}: top-row chip "{box.get("text", "")[:30]}" ends at x {box["x"] + box["w"]:.0f}, the tag starts at {tag["x"]:.0f}',
                    "16 px or more between the chip and the tag: shorten the chip or move it to y 352",
                )


def mean_luma(path: Path) -> float:
    try:
        import numpy as np
        from PIL import Image

        with Image.open(path) as image:
            pixels = np.asarray(image.convert("RGB"), dtype=float)
        return float(
            (
                0.2126 * pixels[..., 0]
                + 0.7152 * pixels[..., 1]
                + 0.0722 * pixels[..., 2]
            ).mean()
        )
    except ImportError:
        width, height, channels, data = read_png(path)
        total = 0.0
        for y in range(height):
            line = data[y]
            for x in range(0, width * channels, channels):
                if channels >= 3:
                    total += (
                        0.2126 * line[x] + 0.7152 * line[x + 1] + 0.0722 * line[x + 2]
                    )
                else:
                    total += line[x]
        return total / (width * height)


def read_png(path: Path) -> tuple[int, int, int, list[bytes]]:
    """A small PNG reader (8-bit grey, RGB or RGBA, not interlaced), for runs without Pillow."""
    blob = path.read_bytes()
    pos, idat, width, height, channels = 8, b"", 0, 0, 3
    while pos < len(blob):
        size, kind = struct.unpack(">I4s", blob[pos : pos + 8])
        chunk = blob[pos + 8 : pos + 8 + size]
        if kind == b"IHDR":
            width, height, depth, colour = struct.unpack(">IIBB", chunk[:10])
            if depth != 8 or chunk[12]:
                raise ValueError(
                    f"{path}: only 8-bit, non-interlaced PNGs are read without Pillow"
                )
            channels = {0: 1, 2: 3, 4: 2, 6: 4}[colour]
        elif kind == b"IDAT":
            idat += chunk
        pos += 12 + size
    raw = zlib.decompress(idat)
    stride = width * channels
    out: list[bytes] = []
    prev = bytearray(stride)
    for y in range(height):
        kind = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1 : (y + 1) * (stride + 1)])
        for x in range(stride):
            left = line[x - channels] if x >= channels else 0
            up = prev[x]
            corner = prev[x - channels] if x >= channels else 0
            if kind == 1:
                line[x] = (line[x] + left) & 255
            elif kind == 2:
                line[x] = (line[x] + up) & 255
            elif kind == 3:
                line[x] = (line[x] + (left + up) // 2) & 255
            elif kind == 4:
                guess = left + up - corner
                near = min(
                    (abs(guess - left), 0, left),
                    (abs(guess - up), 1, up),
                    (abs(guess - corner), 2, corner),
                )
                line[x] = (line[x] + near[2]) & 255
        out.append(bytes(line))
        prev = line
    return width, height, channels, out


def write_png(path: Path, grey: int, width: int = 18, height: int = 32) -> None:
    raw = b"".join(b"\x00" + bytes([grey]) * (width * 3) for _ in range(height))

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def f12(film: Film, registry: dict, rows: list[dict]) -> None:
    """A drawn picture or plate under 60 that is also darker than the film around it. A film drawn on dark
    cards throughout (02, READY) is as bright as itself; a plate at 47 among photos at 70 to 86 (03) is not."""
    folder = film.build / "proof" / "frames"
    last = film.shots[-1]["id"] if film.shots else None
    level = []
    for key in registry["frames"]:
        path = folder / f"t{float(key):07.2f}.png"
        shot = shot_at(film, float(key))
        if (
            path.exists()
            and shot is not None
            and shot["id"] != last
            and not film.endcard(shot)
        ):
            level.append(mean_luma(path))
    film_level = sorted(level)[len(level) // 2] if level else 0.0
    for shot in film.shots:
        drawn = film.kind(shot) == "none" or film.blurred(shot) or on_ground(shot)
        if (
            not drawn
            or film.endcard(shot)
            or film.free(shot["t0"])
            or shot.get("grade") == "dim"
        ):
            continue
        values = []
        for key in registry["frames"]:
            moment = float(key)
            path = folder / f"t{moment:07.2f}.png"
            if shot["t0"] + 0.05 <= moment < shot["t1"] - 0.05 and path.exists():
                values.append((moment, mean_luma(path)))
        if values:
            mean = sum(v for _, v in values) / len(values)
            if mean < BRIGHT_MIN and mean < film_level - FILM_DARKER:
                row(
                    rows,
                    "L12",
                    "FIX",
                    values[0][0],
                    f"{shot['id']}: the drawn picture or plate has a mean brightness of {mean:.0f} of 255, the film {film_level:.0f}",
                    f"{BRIGHT_MIN:.0f} or more: a lighter plate (graphics.js light) or lighter fills",
                )


def pages_of(film: Film, registry: dict) -> tuple[list[dict], str]:
    """Caption pages: the kit's own list when the registry has it, else read from the caption boxes of the frames."""
    found = registry.get("pages")
    if not isinstance(found, list):
        found = load_json(film.build / "proof" / "frames" / "pages.json")
    if isinstance(found, list):
        return [
            p for p in found if isinstance(p, dict) and "text" in p
        ], "the kit's page list"
    pages: list[dict] = []
    for key, boxes in sorted(registry["frames"].items(), key=lambda kv: float(kv[0])):
        text = " ".join(
            caption_words(film, b.get("text", ""), float(key))
            for b in boxes
            if b.get("role") == "caption" and b.get("opacity", 1) > 0.5
        )
        if not text:
            continue
        if pages and letters(pages[-1]["text"]) == letters(text):
            pages[-1]["t1"] = float(key)
        else:
            pages.append({"t0": float(key), "t1": float(key), "text": text})
    return pages, "caption boxes of the sampled frames"


def sentence_of(film: Film, moment: float) -> int | None:
    index, best = 0, None
    for token in film.tokens:
        if (
            abs(token["t0"] - 0.03 - moment) < 0.08
            or token["t0"] - 0.1 <= moment <= token["t1"]
        ):
            best = index
            break
        if token.get("end"):
            index += 1
    if best is None:  # a page read from a frame: the last token spoken before it
        index = 0
        for token in film.tokens:
            if token["t0"] > moment + 0.05:
                break
            best = index
            if token.get("end"):
                index += 1
    return best


def f13(film: Film, registry: dict, rows: list[dict]) -> None:
    pages, origin = pages_of(film, registry)
    if not pages:
        row(
            rows,
            "L13",
            "NOTE",
            None,
            "no caption pages found, so the NOT rule is not checked",
            "run qa.py frames with a kit that records Kit.pages()",
        )
        return
    for page in pages:
        page["_s"] = sentence_of(film, float(page.get("t0") or 0))
        page["_on"] = (
            page.get("t0") is not None
            and float(page["t0"]) < 1e8
            and page.get("shown", True) is not False
        )
    for index, page in enumerate(pages):
        said = words(plain(page["text"]))
        hits = [i for i, w in enumerate(said) if w in NEGATORS or w.endswith("n't")]
        if not hits:
            continue
        last = hits[-1]
        while last + 1 < len(said) and said[last + 1] in NEGATOR_TAILS:
            last += 1
        tail = [p for p in pages[index + 1 :] if p["_s"] == page["_s"]]
        if not tail:
            continue
        moment = float(tail[0]["t0"]) if tail[0]["_on"] else None
        if last == len(said) - 1 and tail[0]["_on"]:
            row(
                rows,
                "L13",
                "FIX",
                moment,
                f'caption page "{page["text"]}" ends on its negator, so "{tail[0]["text"]}" stands alone',
                "the negator opens its page (IT IS / NOT THE BRIDGE): reword, or switch captions off and stand the line as a title",
            )
        elif not page["_on"] and any(p["_on"] for p in tail):
            row(
                rows,
                "L13",
                "FIX",
                moment,
                f'caption page "{page["text"]}" never shows but "{tail[0]["text"]}" does',
                "mute the whole sentence, or none of it",
            )
        far = [p for p in tail[2:] if p["_on"]]
        if far:
            row(
                rows,
                "L13",
                "NOTE",
                float(far[0]["t0"]),
                f'"{far[0]["text"]}" stands three or more pages after the negator of "{page["text"]}" ({origin})',
                "look at the page alone: does it read as the opposite?",
            )


FRAMES = (f03, f07, f10, f12, f13)


# ---- running


def lint(build: Path, tier: str) -> list[dict]:
    rows: list[dict] = []
    film = Film(build)
    if not isinstance(film.tl, dict):
        row(
            rows,
            "L00",
            "NOT CHECKED",
            None,
            f"no readable timeline.json in {build}",
            "python studio/build.py timeline <build>",
        )
        return rows
    if tier in ("static", "all"):
        if not isinstance(film.layout, dict):
            row(
                rows,
                "L00",
                "NOT CHECKED",
                None,
                "no narration/layout.json",
                "voice the build first",
            )
        for rule in STATIC:
            rule(film, rows)
    if tier in ("frames", "all"):
        registry = registry_of(build)
        if registry is None:
            row(
                rows,
                "L00",
                "NOT CHECKED",
                None,
                "proof/frames was shot from an older timeline.json: the frames tier is not checked"
                if stale_frames(build)
                else "no proof/frames/registry.json: the frames tier is not checked",
                "python studio/studio.py check <build> frames",
            )
        else:
            for rule in FRAMES:
                rule(film, registry, rows)
    # one row per finding: the frames tier does not repeat what the static tier said about a shot
    said = {
        (r["code"], r["what"].split(" ", 1)[0])
        for r in rows
        if r["code"] == "L03" and "repeats" in r["what"]
    }
    unique, seen = [], set()
    for item in rows:
        key = (item["code"], item["t"], item["what"])
        if key in seen or (
            "stands over" in item["what"]
            and (item["code"], item["what"].split(" ", 1)[0]) in said
        ):
            continue
        seen.add(key)
        unique.append(item)
    return unique


def run(build: Path | str, tier: str = "all") -> int:
    """Lint a build at one tier (static, frames or all); print the rows, write proof/qa_lint.json, return the FIX count."""
    return sum(1 for item in report(Path(build), tier) if item["level"] == "FIX")


def report(build: Path, tier: str) -> list[dict]:
    """lint(), printed and written; returns the rows. Each tier has its own file, so a run of one never drops
    the other's findings: proof/qa_lint.json (static) and proof/qa_lint_frames.json (frames)."""
    rows = lint(build, tier)
    if tier == "frames":
        # a finding the static tier already made about a shot is one row (and one accept.json entry), not two
        merged = lint(build, "all")
        rows = [item for item in rows if item in merged]
    files = {
        "static": {"qa_lint.json": rows},
        "frames": {"qa_lint_frames.json": rows},
    }.get(tier)
    if files is None:  # all: the merged rows, split back into the two files
        static_rows = lint(build, "static")
        files = {
            "qa_lint.json": static_rows,
            "qa_lint_frames.json": [item for item in rows if item not in static_rows],
        }
    proof = build / "proof"
    if (build / "timeline.json").exists():
        proof.mkdir(exist_ok=True)
        for name, held in files.items():
            (proof / name).write_text(
                json.dumps(held, indent=1), encoding="utf-8", newline="\n"
            )
    for item in sorted(
        rows, key=lambda r: (r["level"] != "FIX", r["t"] if r["t"] is not None else -1)
    ):
        when = "      " if item["t"] is None else f"{item['t']:6.2f}"
        print(
            f"{item['level']:4} {item['code']} {when}  {item['what']}  ->  {item['fix']}"
        )
    fixes = sum(1 for item in rows if item["level"] == "FIX")
    unchecked = sum(1 for item in rows if item["level"] == "NOT CHECKED")
    print(
        f"lint {tier}: {fixes} FIX, {len(rows) - fixes - unchecked} NOTE, {unchecked} NOT CHECKED"
    )
    return rows


def exit_code(rows: list[dict]) -> int:
    if any(r["level"] == "FIX" for r in rows):
        return 1
    return 2 if any(r["level"] == "NOT CHECKED" for r in rows) else 0


# ---- selftest


def expand(case: dict) -> dict:
    """A fixture's compact build: shots with defaults filled in, speech as [line, start, text] spaced 0.3 s a word."""
    tl = dict(case.get("timeline") or {})
    tl.setdefault("slug", "fixture")
    tl.setdefault("fps", 30)
    tl.setdefault("accent", "#ffd60a")
    tl.setdefault("tag", "AI-generated")
    for key in ("mute", "says", "exempt", "quiet"):
        tl.setdefault(key, [])
    shots = []
    for shot in tl.get("shots") or []:
        shot = dict(shot)
        shot.setdefault("media", {"kind": "still", "src": f"media/{shot['id']}.jpg"})
        shot["over"] = [
            {"at": shot["t0"], "out": None, **spec} for spec in shot.get("over") or []
        ]
        shots.append(shot)
    tl["shots"] = shots
    tl.setdefault("duration", shots[-1]["t1"] if shots else 0)
    lines, tokens = [], []
    for line_id, start, text in case.get("speech") or []:
        found = []
        for index, word in enumerate(text.split()):
            t0 = round(start + 0.3 * index, 3)
            found.append({"d": word, "t0": t0, "t1": round(t0 + 0.25, 3)})
            tokens.append(
                {
                    "d": word.strip(",.;:?!"),
                    "t0": t0,
                    "t1": round(t0 + 0.25, 3),
                    "stop": word[-1] in ",.;:?!",
                    "end": word[-1] in ".?!",
                    "p": "",
                    "line": line_id,
                }
            )
        lines.append(
            {
                "id": line_id,
                "text": text,
                "t0": found[0]["t0"],
                "t1": found[-1]["t1"],
                "tokens": found,
                "words": [{"w": w["d"], "t0": w["t0"], "t1": w["t1"]} for w in found],
            }
        )
    tl.setdefault("tokens", tokens)
    layout = {"lines": lines, "speech_end": lines[-1]["t1"] if lines else 0}
    return {
        "timeline": tl,
        "layout": layout,
        "script": case.get("script") or {},
        "registry": case.get("registry"),
        "older_registry": bool(case.get("older_registry")),
        "pngs": case.get("pngs") or {},
    }


def plant(folder: Path, case: dict) -> None:
    built = expand(case)
    (folder / "narration").mkdir(parents=True)
    (folder / "proof" / "frames").mkdir(parents=True)
    (folder / "timeline.json").write_text(
        json.dumps(built["timeline"]), encoding="utf-8"
    )
    (folder / "narration" / "layout.json").write_text(
        json.dumps(built["layout"]), encoding="utf-8"
    )
    (folder / "script.json").write_text(json.dumps(built["script"]), encoding="utf-8")
    if built["registry"] is not None:
        registry = folder / "proof" / "frames" / "registry.json"
        registry.write_text(json.dumps(built["registry"]), encoding="utf-8")
        if built[
            "older_registry"
        ]:  # frames shot from the timeline before the last build
            then = (folder / "timeline.json").stat().st_mtime - 60
            os.utime(registry, (then, then))
    for moment, grey in built["pngs"].items():
        write_png(
            folder / "proof" / "frames" / f"t{float(moment):07.2f}.png", int(grey)
        )


def selftest() -> int:
    """One fixture per rule (selftest/fixtures/L07.json), then the regression cases beside it (L07-text-value.json).

    A case may name the "level" it must raise (FIX by default; L00 cases say NOT CHECKED)."""
    fired, clean, problems = 0, 0, []
    cases = [FIXTURES / f"{code}.json" for code in RULES] + sorted(
        FIXTURES.glob("L*-*.json")
    )
    with tempfile.TemporaryDirectory(prefix="lint-selftest-") as scratch:
        for path in cases:
            code = path.stem.split("-", 1)[0]
            spec = load_json(path)
            if not isinstance(spec, dict):
                problems.append(f"{path.stem}: no fixture at {path}")
                continue
            tier, level = spec.get("tier", "static"), spec.get("level", "FIX")
            results = {}
            for name in ("fault", "control"):
                folder = Path(scratch) / f"{path.stem}-{name}"
                plant(folder, spec[name])
                results[name] = [
                    r
                    for r in lint(folder, tier)
                    if r["code"] == code and r["level"] == level
                ]
            want = spec.get("t")
            hit = [
                r
                for r in results["fault"]
                if want is None or (r["t"] is not None and abs(r["t"] - want) <= 0.05)
            ]
            if hit:
                fired += 1
            else:
                problems.append(
                    f"{path.stem}: the planted fault did not fire at t {want} (got {[r['t'] for r in results['fault']]})"
                )
            if results["control"]:
                problems.append(
                    f"{path.stem}: the clean control fired: {results['control'][0]['what']}"
                )
            else:
                clean += 1
            print(
                f"{path.stem} {'fires' if hit else 'MISSED'} at {want}; control {'clean' if not results['control'] else 'FIRED'}"
            )
    for problem in problems:
        print("FAIL " + problem)
    if problems:
        print(
            f"LINT SELFTEST: FAIL ({fired} of {len(cases)} cases fire, {clean} controls clean)"
        )
        return 1
    print(
        f"LINT SELFTEST: PASS ({fired} of {len(cases)} cases fire for {len(RULES)} rules, controls clean)"
    )
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["selftest"]:
        return selftest()
    if not argv or len(argv) > 2 or (len(argv) == 2 and argv[1] not in TIERS):
        print(
            "usage: lint.py <build> [static|frames|all]  |  lint.py selftest",
            file=sys.stderr,
        )
        return 64
    tier = argv[1] if len(argv) == 2 else "all"
    return exit_code(report(Path(argv[0]), tier))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
