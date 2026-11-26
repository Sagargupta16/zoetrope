"""Helpers for a film's shot list, so no make_shots.py re-declares them, and the layered fix blocks.

A film's shots.py looks like:

    from shotkit import *
    plan = Plan("chilli-came-by-ship", "deep navy and warm amber grade, soft film grain")
    plan.shot("s01", still=still("A bowl of red chillies ...", 11, check=["one bowl, centred"]),
              over=[label("First grown in the Americas", standing=True), source("fact", "PNAS", 2014)])

    @plan.block("2026-11-25 fix 1: reading holds")
    def fix1(p):
        p.part("s01", "label")["at"] = "+0.2"
        p.after("s01", {"id": "s01b", "cue": "L01:3", "use": "s01", "tin": PUNCH, "over": []})

    plan.write()                # shots.json and proof/blocks.md next to this file
    plan.write(until="2026-11-25 fix 1")   # the state as it was after that block (a prefix of its name)

Blocks run in the order they were declared, on a copy of what was declared outside them, so write() can
be called again with another `until`. proof/blocks.md lists the last block to touch each shot: those are
the windows a reviewer looks at again after a fix.

Overlay helpers return plain dicts. Two extra keys are for the engine and not for the stage: `past` on a
date chip (the shot needs the past grade, which the lint checks) and `real` on a chip that names a real
person or place (a photoreal picture under it is a P0).

  python shotkit.py --selftest
"""

from __future__ import annotations

import copy
import inspect
import json
import sys
from pathlib import Path

PUNCH = {"kind": "punch", "d": 0.35, "from": 1.06}  # a cut-in settles from 1.06
HELD = {
    "from": 1.0,
    "to": 1.0,
    "shake": 0,
}  # the camera under a card: nothing drifts behind standing type
# media of a plain plate the stage draws (the kit's `ground`); the kit's `plate` is a blurred picture and needs a src
PLATE = {"kind": "none", "graphic": "ground"}

SOURCES = {
    "fact": "Fact from",
    "account": "One account",
    "visuals": "Visuals and voice",
}


def label(text: str, y: int = 282, **k) -> dict:
    return {"type": "label", "text": text, "y": y, **k}


def date(text: str, **k) -> dict:
    """An accent label for a date. The shot it stands in needs the past grade (`past`)."""
    return label(text, tone="accent", past=True, **k)


def source(kind: str, name: str, year: int | str | None = None, **k) -> dict:
    """A source line: source("fact", "BBC News", 2011) reads "Fact from: BBC News, 2011". An unknown kind
    is used as the lead-in as it is ("One veteran's account")."""
    text = f"{SOURCES.get(kind, kind)}: {name}" + (
        f", {year}" if year is not None else ""
    )
    return {"type": "source", "text": text, **k}


def title(*lines: str, at: str = "+0.1", y: int = 380, size: int = 150, **k) -> dict:
    return {"type": "title", "lines": list(lines), "y": y, "size": size, "at": at, **k}


def lower(text: str, y: int = 352, **k) -> dict:
    return {"type": "lower", "text": text, "y": y, **k}


def number(value: float, land: str | float, **k) -> dict:
    """A count that ends on the spoken number: `land` is the cue of the word (landAt). `value` (and a `from`
    or `to`) is an int or a float: the stage counts it, so text ("1,492") would draw NaN."""
    for key, given in {"value": value, **k}.items():
        if key in ("value", "from", "to") and (
            isinstance(given, bool) or not isinstance(given, (int, float))
        ):
            raise TypeError(f"number {key} must be an int or a float, not {given!r}")
    return {
        "type": "number",
        "value": value,
        "y": 352,
        "size": 300,
        **k,
        "landAt": land,
    }


def stamp(text: str, who: str | None = None, **k) -> dict:
    spec = {"type": "stamp", "text": text, "size": 100, **k}
    if who:
        spec["who"] = who
    return spec


def ladder(rows: list[dict]) -> dict:
    """Rows of {label, value, state, at}: on a plate, and a revealed row lands in the accent (hot)."""
    shown = [
        {**row, "hot": row.get("hot", True)}
        if row.get("state") == "reveal"
        else dict(row)
        for row in rows
    ]
    return {"type": "ladder", "y": 352, "plate": True, "rows": shown}


def real(spec: dict) -> dict:
    """Mark a chip as naming a real person or place: the lint refuses it on a photoreal picture."""
    return {**spec, "real": True}


def still(prompt: str, seed: int, check: list[str] | tuple[str, ...] = ()) -> dict:
    """A still. `check` lists the features to look for in the made picture; gen.py keeps it in state.json."""
    spec = {"prompt": prompt, "seed": seed}
    if check:
        spec["check"] = list(check)
    return spec


def clip(prompt: str, seconds: int = 4) -> dict:
    return {"prompt": prompt, "seconds": seconds}


def batch_end(start: str | Path | None = None) -> dict:
    """The `end` object (handle, follow, ai_line) of the nearest batch.json at or above `start`; without a
    `start`, above the script that is running (a film's shots.py). Empty when there is none."""
    folder = Path(start or sys.argv[0] or ".").resolve()
    for parent in (folder, *folder.parents):
        file = parent / "batch.json"
        if file.is_file():
            try:
                return dict(
                    json.loads(file.read_text(encoding="utf-8")).get("end") or {}
                )
            except ValueError:
                return {}
    return {}


def end_card(
    big: list[str],
    line: str | None = None,
    *,
    use: str,
    cue: str,
    seconds: float = 3.0,
    end: dict | None = None,
    chip: str | None = None,
    **k,
) -> dict:
    """The fields of the closing shot: the end overlay over a blurred earlier picture, with the handle and the
    AI line the batch names (batch.json `end`), so no film types them again. `line` is this film's send line
    (a line break in it is kept); without one the batch's `follow` line stands. `chip` is a small dark chip
    under the big words (AS OF 2026 under a claim about today).

        plan.shot("end", **end_card(["IT CAME", "BY SHIP"], "Send this to someone who loves chilli",
                                    use="s01", cue="L32:end"))
    """
    end = batch_end() if end is None else end
    card = {
        "type": "end",
        "big": list(big),
        "line": line or str(end.get("follow") or ""),
        "lift": 80,
    }
    if chip:
        card["chip"] = chip
    handle = str(end.get("handle") or "").lstrip("@")  # the kit writes the @ itself
    if handle:
        card["handle"] = handle
    over = [card]
    if end.get("ai_line"):
        over.append(
            {
                "type": "source",
                "text": str(end["ai_line"]),
                "y": 1070,
                "standing": True,
                "align": "center",
            }
        )
    return {
        "cue": cue,
        "len": seconds,
        "use": use,
        "media": "still",  # the owner's still, never its clip played on past its end
        "grade": "blur",
        "captions": False,
        "tin": {"kind": "fade", "d": 0.4},
        "over": over,
        **k,
    }


def _fingerprint(shot: dict) -> str:
    return json.dumps(shot, sort_keys=True, ensure_ascii=False)


class Plan:
    """The shots of one film, the layered blocks that fix them, and the files they write."""

    def __init__(self, slug: str, look: str):
        self.slug = slug
        self.look = look
        self.shots: list[dict] = []
        self.blocks: list[tuple[str, object]] = []

    @property
    def by_id(self) -> dict[str, dict]:
        return {shot["id"]: shot for shot in self.shots}

    def shot(self, id: str, **fields) -> dict:
        """Add a shot at the end; `id` and fields as in shots.json (cue, still, use, cam, over ...)."""
        shot = copy.deepcopy({"id": id, **fields})
        shot.setdefault("over", [])
        self.shots.append(shot)
        return shot

    def part(self, id: str, kind: str, i: int = 0) -> dict:
        """The i-th overlay of a kind in a shot, to change in place."""
        found = [item for item in self.by_id[id]["over"] if item.get("type") == kind]
        if i >= len(found):
            raise KeyError(
                f"shot {id} has {len(found)} {kind} overlay(s), asked for index {i}"
            )
        return found[i]

    def after(self, id: str, new: dict) -> dict:
        """Put a new shot right after an existing one."""
        at = next(n for n, shot in enumerate(self.shots) if shot["id"] == id)
        new = copy.deepcopy(new)
        new.setdefault("over", [])
        self.shots.insert(at + 1, new)
        return new

    def drop(self, *ids: str) -> None:
        known = self.by_id
        for shot_id in ids:
            self.shots.remove(known[shot_id])

    def own_still(self, id: str, spec: dict, **more) -> dict:
        """A shot that gains a still of its own loses its `use`, its drawn `media` and what belonged to the
        picture it used."""
        shot = self.by_id[id]
        for key in ("use", "media", "offset", "rate", "amb", "flip", "tin", "still"):
            shot.pop(key, None)
        shot["still"] = spec
        shot.update(more)
        return shot

    def block(self, name: str):
        """Decorator: a named fix block, a function of one argument (the plan). Blocks run in the order they were declared."""

        def register(fn):
            self.blocks.append((name, fn))
            return fn

        return register

    def _resolve(self, until: str | int | None) -> int:
        if until is None:
            return len(self.blocks)
        if isinstance(until, int):
            return until
        for n, (name, _) in enumerate(self.blocks):
            if name.startswith(until):
                return n + 1
        raise SystemExit(
            f"no block starts with {until!r}: {[name for name, _ in self.blocks]}"
        )

    def build(self, until: str | int | None = None) -> tuple[dict, dict[str, str]]:
        """Run the blocks on a copy of the declared shots. Returns the plan and, per shot, the last block
        to touch it ("base" when none did; "dropped by <block>" for a shot that is gone)."""
        base = copy.deepcopy(self.shots)
        last = {shot["id"]: "base" for shot in self.shots}
        try:
            for name, fn in self.blocks[: self._resolve(until)]:
                before = {shot["id"]: _fingerprint(shot) for shot in self.shots}
                order = [shot["id"] for shot in self.shots]
                fn(self)
                after = {shot["id"]: _fingerprint(shot) for shot in self.shots}
                for shot_id, print_ in after.items():
                    if before.get(shot_id) != print_:
                        last[shot_id] = name
                for shot_id in before.keys() - after.keys():
                    last[shot_id] = f"dropped by {name}"
                if [i for i in order if i in after] != [
                    i for i in after if i in before
                ]:
                    for shot_id in after:  # a shot that moved counts as touched
                        if shot_id in before and order.index(shot_id) != list(
                            after
                        ).index(shot_id):
                            last[shot_id] = name
            result = {
                "slug": self.slug,
                "look": self.look,
                "shots": copy.deepcopy(self.shots),
            }
        finally:
            self.shots = base
        return result, last

    def write(
        self, until: str | int | None = None, folder: Path | str | None = None
    ) -> dict:
        """Write shots.json and proof/blocks.md into `folder` (default: the folder of the calling script)."""
        if folder is None:
            folder = Path(inspect.stack()[1].filename).resolve().parent
        folder = Path(folder)
        result, last = self.build(until)
        (folder / "proof").mkdir(parents=True, exist_ok=True)
        text = json.dumps(result, indent=1, ensure_ascii=False) + "\n"
        (folder / "shots.json").write_bytes(text.encode("utf-8"))
        ran = self.blocks[: self._resolve(until)]
        lines = [
            f"# Blocks of {self.slug}",
            "",
            "Last block to touch each shot (windows to review again).",
            "",
        ]
        lines += [f"- block {n}: {name}" for n, (name, _) in enumerate(ran, 1)] or [
            "- no blocks"
        ]
        lines += ["", "| shot | last block |", "|---|---|"]
        lines += [f"| {shot_id} | {name} |" for shot_id, name in last.items()]
        (folder / "proof" / "blocks.md").write_bytes(
            ("\n".join(lines) + "\n").encode("utf-8")
        )
        print(f"{len(result['shots'])} shots written ({len(ran)} blocks run)")
        return result


GOLDEN = '{"look":"warm light","shots":[{"id":"s01","over":[{"at":"+0.2","text":"Before","type":"label","y":282},{"past":true,"text":"1492","tone":"accent","type":"label","y":282},{"real":true,"text":"Fact from: TIME, 2017","type":"source"}],"still":{"check":["one bowl"],"prompt":"A red bowl on a table.","seed":7}},{"cue":"L00:5","id":"s01b","over":[{"says":true,"size":100,"text":"LIKELY","type":"stamp","who":"Researchers say"}],"use":"s01"},{"cam":{"from":1.0,"shake":0,"to":1.0},"cue":"L02:0","id":"s03","over":[{"plate":true,"rows":[{"at":"L02:1","hot":true,"label":"A","state":"reveal","value":"NO"}],"type":"ladder","y":352}],"still":{"prompt":"A bare table.","seed":9}}],"slug":"sample"}'


def _sample() -> Plan:
    plan = Plan("sample", "warm light")
    plan.shot(
        "s01",
        still=still("A red bowl on a table.", 7, check=["one bowl"]),
        over=[label("Before"), date("1492"), source("fact", "PNAS", 2014)],
    )
    plan.shot(
        "s02",
        cue="L01:0",
        use="s01",
        tin=PUNCH,
        over=[number(1492, "L01:3", group=False)],
    )
    plan.shot(
        "s03",
        cue="L02:0",
        media=PLATE,
        cam=HELD,
        over=[
            ladder([{"label": "A", "value": "NO", "state": "reveal", "at": "L02:1"}])
        ],
    )

    @plan.block("2026-11-25 fix 1: reading holds")
    def one(p):
        p.part("s01", "label")["at"] = "+0.2"
        p.after(
            "s01",
            {
                "id": "s01b",
                "cue": "L00:5",
                "use": "s01",
                "over": [stamp("LIKELY", who="Researchers say")],
            },
        )

    @plan.block("2026-11-25 fix 2: reviews final")
    def two(p):
        p.part("s01b", "stamp")["says"] = True
        p.drop("s02")
        p.own_still("s03", still("A bare table.", 9))
        p.part("s01", "source").update(real(source("fact", "TIME", 2017)))

    return plan


def selftest() -> None:
    import tempfile

    plan = _sample()
    with tempfile.TemporaryDirectory() as tmp:
        result = plan.write(folder=tmp)
        blocks = (Path(tmp) / "proof" / "blocks.md").read_text(encoding="utf-8")
        early = plan.write(until="2026-11-25 fix 1", folder=tmp)
    got = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    problems = []
    if got != GOLDEN:
        problems.append(f"golden differs:\n{got}")
    if (
        "| s01 | 2026-11-25 fix 2: reviews final |" not in blocks
        or "| s01b | 2026-11-25 fix 2: reviews final |" not in blocks
    ):
        problems.append("blocks.md misses the last block of s01 or s01b")
    if "| s02 | dropped by 2026-11-25 fix 2: reviews final |" not in blocks:
        problems.append("blocks.md misses the drop of s02")
    if [shot["id"] for shot in early["shots"]] != ["s01", "s01b", "s02", "s03"]:
        problems.append("until did not rebuild the earlier state")
    if "S02" in blocks and "| s03 | base |" in blocks:
        problems.append("s03 was touched by block 2")
    try:
        number("1,492", "L01:3")
        problems.append("number took a text value")
    except TypeError:
        pass
    card = end_card(["END"], "Send it", use="s01", cue="L02:end", end={})
    if card.get("media") != "still":
        problems.append("end_card would play its owner's clip past its end")
    if problems:
        print("\n".join(problems))
        print("SHOTKIT: FAIL")
        raise SystemExit(1)
    print("SHOTKIT: PASS")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        print(__doc__)
