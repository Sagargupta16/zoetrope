# cards.py : the style cards as data. Each card in references/styles/ carries one **Spec:** line under its Defaults
# (family, length in seconds, size, fps, audio, kit), and this file reads it, so the router in SKILL.md, the kit list
# and the card counts in README.md and SKILL.md are checked against the cards instead of kept by hand. The idea of a
# catalog that is the one source of truth comes from wide-trace/open-higgsfield (no licence, read 2026-11-03; no
# code taken).
#   python cards.py check            every spec valid; router, kit list and counts agree with the cards (exit 1 if not)
#   python cards.py router [--write] the router table built from the cards (--write puts it into SKILL.md)
#   python cards.py spec <card>      one card's spec
import os
import re
import sys
import unicodedata
from pathlib import Path

# the cards: beside this file in the skill, or (from a build folder's copy of the engine) the skill named by
# ZOETROPE_SKILL, a user-level install, or the newest installed copy of the plugin
_HERE = Path(__file__).resolve().parent
_CLAUDE = Path.home() / ".claude"
ROOT = next(
    (
        p
        for p in (
            Path(os.environ["ZOETROPE_SKILL"])
            if os.environ.get("ZOETROPE_SKILL")
            else None,
            _HERE.parent,
            _CLAUDE / "skills" / "zoetrope",
            *sorted(
                (_CLAUDE / "plugins" / "cache").glob("*/zoetrope/*/skills/zoetrope"),
                key=lambda d: d.stat().st_mtime,
                reverse=True,
            ),
        )
        if p is not None and (p / "references" / "styles").is_dir()
    ),
    _HERE.parent,
)
STYLES = ROOT / "references" / "styles"
# spec family: the router's name for it, in the router's order
FAMILIES = {
    "launch": "launch and promo",
    "logo": "logo and titles",
    "music": "music-driven",
    "explainer": "explainer",
    "story": "story and journey",
    "game": "character and game",
    "handmade": "handmade",
}
AUDIO = (
    "music",
    "voice",
)  # voice: narrated over music (Q806 then expects narration/narration.json)
KEYS = ("family", "length", "size", "fps", "audio", "kit")
SPEC = re.compile(r"^\*\*Spec:\*\* (.+)$", re.MULTILINE)
TITLE = re.compile(
    r"^# S-(\S+) \S (.+)$", re.MULTILINE
)  # name, the middle dot, the title
USE = re.compile(r"^\*\*Use when:\*\* (.+)$", re.MULTILINE)


def _length(v):
    """(low, high) seconds from "45" or "60-90"."""
    a, _, b = v.partition("-")
    lo, hi = float(a), float(b or a)
    if not 0 < lo <= hi:
        raise ValueError(f"length {v!r}: seconds, or low-high")
    return lo, hi


def parse(path):
    """One card: {name, title, use, family, length, size, fps, audio, kit}. Raises ValueError naming what is wrong."""
    text = Path(path).read_text(encoding="utf-8")
    name = Path(path).stem
    m, s, u = TITLE.search(text), SPEC.search(text), USE.search(text)
    if not (m and s and u):
        missing = [
            k
            for k, v in (("title", m), ("**Spec:**", s), ("**Use when:**", u))
            if not v
        ]
        raise ValueError(f"{name}: no {', '.join(missing)} line")
    if m.group(1) != name:
        raise ValueError(f"{name}: title names S-{m.group(1)}, the file is {name}.md")
    kv = dict(p.split("=", 1) for p in s.group(1).split())
    if set(kv) != set(KEYS):
        raise ValueError(f"{name}: spec keys {sorted(kv)}, want {list(KEYS)}")
    if kv["family"] not in FAMILIES:
        raise ValueError(
            f"{name}: family {kv['family']!r}, want one of {list(FAMILIES)}"
        )
    if kv["audio"] not in AUDIO:
        raise ValueError(f"{name}: audio {kv['audio']!r}, want one of {list(AUDIO)}")
    if not re.fullmatch(r"\d+x\d+", kv["size"]):
        raise ValueError(f"{name}: size {kv['size']!r}, want WxH")
    use = [p.strip().strip('"') for p in re.findall(r'"[^"]*"', u.group(1))]
    return {
        "name": name,
        "title": m.group(2).strip(),
        "use": use,
        "family": kv["family"],
        "length": _length(kv["length"]),
        "size": kv["size"],
        "fps": int(kv["fps"]),
        "audio": kv["audio"],
        "kit": None if kv["kit"] == "-" else kv["kit"],
    }


def cards():
    """Every card in STYLES (families.md is the families' intro, not a card), by name."""
    return {
        p.stem: parse(p) for p in sorted(STYLES.glob("*.md")) if p.stem != "families"
    }


def spec(name):
    """One card's spec by its name, with or without the S- prefix."""
    name = name.removeprefix("S-")
    path = STYLES / f"{name}.md"
    if not path.is_file():
        raise KeyError(f"no style card {name!r} in {STYLES}")
    return parse(path)


def _plain(s):
    """Router text: accents folded to ASCII (resume, not the accented spelling), quotes and placeholder braces
    dropped."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[{}\"]", "", s)


def _row(c):
    """The card's router row: its title without a closing (48 s) or (128 BPM), then its first two use-when phrases."""
    title = re.sub(r"\s*\([^)]*\)$", "", c["title"])
    title = _plain(title[0].lower() + title[1:])
    use = ", ".join(_plain(p) for p in c["use"][:2])
    return f"| [S-{c['name']}](references/styles/{c['name']}.md) | {FAMILIES[c['family']]} | {title}; {use} |"


def router(cs=None):
    """The router table's rows, family by family in FAMILIES order, then in SKILL.md's own order within a family."""
    cs = cs or cards()
    order = {f: i for i, f in enumerate(FAMILIES)}
    now = [_card_of(r) for r in _table(_skill())[1]]
    rank = {n: i for i, n in enumerate(now)}
    keyed = sorted(
        cs.values(),
        key=lambda c: (order[c["family"]], rank.get(c["name"], 999), c["name"]),
    )
    return [_row(c) for c in keyed]


def _skill():
    return (ROOT / "SKILL.md").read_text(encoding="utf-8")


def _table(text):
    """(index of the header line, the router's rows) in SKILL.md's text."""
    lines = text.splitlines()
    head = next(
        i
        for i, ln in enumerate(lines)
        if ln.startswith("| Style card | Family | Use when |")
    )
    rows = []
    for ln in lines[head + 2 :]:
        if not ln.startswith("| [S-"):
            break
        rows.append(ln)
    return head, rows


def _card_of(row):
    return re.match(r"\| \[S-([^\]]+)\]", row).group(1)


def check():
    """Problems, as lines: a card that does not parse, a router row that is not the card's, a kit list or a count
    that disagrees with the cards. Empty when all agree."""
    out, cs = [], {}
    for p in sorted(STYLES.glob("*.md")):
        if p.stem == "families":
            continue
        try:
            cs[p.stem] = parse(p)
        except ValueError as e:
            out.append(f"card: {e}")
    text = _skill()
    rows = _table(text)[1]
    have = {_card_of(r): r for r in rows}
    for n in sorted(set(cs) - set(have)):
        out.append(f"router: S-{n} has no row in SKILL.md")
    for n in sorted(set(have) - set(cs)):
        out.append(f"router: S-{n} has a row in SKILL.md but no card")
    for n in sorted(set(cs) & set(have)):
        if have[n] != _row(cs[n]):
            out.append(
                f"router: S-{n} row is not built from its card:\n  have {have[n]}\n  want {_row(cs[n])}"
            )
    kits = (
        {p.name for p in (ROOT / "kits").iterdir() if p.is_dir()}
        if (ROOT / "kits").is_dir()
        else set()
    )
    named = {c["kit"] for c in cs.values() if c["kit"]}
    m = re.search(r"Cards with a kit in `kits/`[^:]*: (.+)$", text, re.MULTILINE)
    listed = (
        {x.strip().rstrip(".").removeprefix("S-") for x in m.group(1).split(",")}
        if m
        else set()
    )
    for what, got in (("kits/ folders", kits), ("SKILL.md kit list", listed)):
        if got != named:
            out.append(
                f"kits: the cards name {sorted(named)}, {what} has {sorted(got)}"
            )
    # SKILL.md beside the cards, and the plugin's README two folders up when this is the plugin layout
    repo = ROOT.parent.parent
    docs = [ROOT / "SKILL.md"]
    if (repo / ".claude-plugin" / "plugin.json").is_file():
        docs.append(repo / "README.md")
    for path in (d for d in docs if d.is_file()):
        doc = path.name
        body = path.read_text(encoding="utf-8")
        # a count of all the cards follows "the ", ": ", "| " or ". " ("20 style cards name a font" is a part)
        for m in re.finditer(
            r"(?:\bthe |: |\| |\. )(\d+)(?= (?:style cards|tested styles|tested looks)\b)",
            body,
        ):
            if int(m.group(1)) != len(cs):
                ln = body.count("\n", 0, m.start()) + 1
                out.append(
                    f"count: {doc}:{ln} says {m.group(1)}, there are {len(cs)} cards"
                )
    return out


def main(argv):
    cmd = argv[0] if argv else "check"
    if cmd == "check":
        bad = check()
        print("\n".join(bad))
        print(
            f"CARDS: {'FAIL (' + str(len(bad)) + ')' if bad else 'OK'} ({len(cards()) if not bad else '?'} cards in {STYLES})"
        )
        return 1 if bad else 0
    if cmd == "router":
        rows = router()
        if "--write" in argv:
            path = ROOT / "SKILL.md"
            text = path.read_bytes().decode("utf-8")
            lines = text.split("\n")
            head, old = _table(text)
            lines[head + 2 : head + 2 + len(old)] = rows
            path.write_bytes("\n".join(lines).encode("utf-8"))
            print(f"router: wrote {len(rows)} rows into {path}")
        else:
            print("\n".join(rows))
        return 0
    if cmd == "spec" and len(argv) > 1:
        c = spec(argv[1])
        print(" ".join(f"{k}={c[k]}" for k in ("name", *KEYS)))
        return 0
    print("usage: python cards.py check | router [--write] | spec <card>")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
