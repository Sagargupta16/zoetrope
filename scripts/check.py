#!/usr/bin/env python3
"""Deterministic repo gate, no LLM: run before every commit (python scripts/check.py).

ZC001 en or em dash             ZC005 broken relative link in Markdown
ZC002 secret-shaped string      ZC006 JSON file does not parse
ZC003 skill frontmatter         ZC007 plugin manifests disagree with the CHANGELOG head
ZC004 absolute home path        ZC008 CR line end (every text file is LF)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_NAME = "zoetrope"

DASHES = (chr(0x2013), chr(0x2014))
TEXT = {".md", ".py", ".sh", ".json", ".yml", ".yaml", ".toml", ".txt", ".svg", ".in"}
TEXT_NAMES = {"LICENSE", ".gitignore", ".gitattributes", ".python-version"}
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".ruff_cache",
    "videos",
    "outputs",
    "frames",
    "review",
}
SECRETS = [
    ("aws access key", re.compile(r"\bA(?:KIA|SIA)[0-9A-Z]{16}\b")),
    (
        "github token",
        re.compile(r"\b(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{30,}|\bgithub_pat_\w{40,}"),
    ),
    ("api key", re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{24,}")),
]
# a real user's home folder; placeholders such as C:/Users/... or /home/<name>/ do not match
HOME_PATH = re.compile(
    r"\b[A-Za-z]:[\\/]+Users[\\/]+(?!\.\.\.)[\w.-]+|/c/Users/(?!\.\.\.)[\w.-]+"
    r"|/home/(?!runner\b)[a-z][\w.-]*/|/Users/(?!Shared\b)[A-Z][\w.-]+/"
)
CHANGELOG_HEAD = re.compile(r"^## (\d+\.\d+\.\d+)\b", re.MULTILINE)
MD_LINK = re.compile(r"\]\((?!https?:|mailto:|#|\{\{)([^)\s]+)\)")
INLINE_CODE = re.compile(r"`[^`]*`")
HTML_REF = re.compile(r"\b(?:src|srcset|href)=\"(?!https?:|mailto:|#|data:)([^\"]+)\"")


def files() -> list[Path]:
    out = []
    for p in ROOT.rglob("*"):
        rel = p.relative_to(ROOT).parts
        textual = p.suffix in TEXT or p.name in TEXT_NAMES
        if p.is_file() and not SKIP_DIRS.intersection(rel) and textual:
            out.append(p)
    return sorted(out)


def frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Flat key: value frontmatter with folded (>-) values joined; returns (meta, raw head)."""
    if not text.startswith("---"):
        return {}, ""
    lines = text.splitlines()
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return {}, ""
    meta: dict[str, str] = {}
    key = None
    for raw in lines[1:end]:
        if key and raw.startswith((" ", "\t")):
            meta[key] = f"{meta[key]} {raw.strip()}".strip()
            continue
        key = None
        name, sep, value = raw.partition(":")
        if not sep or raw.startswith((" ", "\t", "#")):
            continue
        name, value = name.strip(), value.strip()
        meta[name] = "" if value in (">", ">-", "|", "|-") else value.strip("\"'")
        if value in (">", ">-", "|", "|-", ""):
            key = name
    return meta, "\n".join(lines[1:end])


def check_skill(p: Path, rel: str, text: str) -> list[str]:
    meta, head = frontmatter(text)
    problems = []
    if meta.get("name") != SKILL_NAME:
        problems.append(
            f"{rel}:1 ZC003 name {meta.get('name')!r} must be {SKILL_NAME!r}"
        )
    desc = meta.get("description", "")
    if not desc:
        problems.append(f"{rel}:1 ZC003 missing description")
        return problems
    if not re.search(r"^description:\s*>-?\s*$", head, re.MULTILINE):
        problems.append(f"{rel}:1 ZC003 description must be a folded block scalar (>-)")
    if len(desc) > 1024:
        problems.append(f"{rel}:1 ZC003 description is {len(desc)} chars (max 1024)")
    if "Use when" not in desc:
        problems.append(
            f'{rel}:1 ZC003 description needs "Use when ..." trigger phrases'
        )
    return problems


def check_links(p: Path, rel: str, n: int, line: str) -> list[str]:
    problems = []
    for target in MD_LINK.findall(line) + HTML_REF.findall(line):
        clean = target.split("#", 1)[0].split("?", 1)[0]
        if not clean:
            continue
        resolved = (p.parent / clean).resolve()
        if not resolved.is_relative_to(ROOT):
            continue  # workspace stacking links point outside the repo; not checkable here
        if not resolved.exists():
            problems.append(f"{rel}:{n} ZC005 broken link {target}")
    return problems


def check_manifests() -> list[str]:
    """plugin.json and every marketplace.json plugin entry: name zoetrope, version = the CHANGELOG head."""
    head = CHANGELOG_HEAD.search((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    if not head:
        return ["CHANGELOG.md:1 ZC007 no '## X.Y.Z' version heading"]
    want = head.group(1)
    problems = []
    found: list[tuple[str, dict]] = []
    for name in ("plugin.json", "marketplace.json"):
        p = ROOT / ".claude-plugin" / name
        rel = f".claude-plugin/{name}"
        if not p.is_file():
            problems.append(f"{rel}:1 ZC007 missing")
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue  # ZC006 reports it
        if name == "plugin.json":
            found.append((rel, data))
        else:
            if data.get("name") != SKILL_NAME:
                problems.append(
                    f"{rel}:1 ZC007 marketplace name {data.get('name')!r} must be {SKILL_NAME!r}"
                )
            found += [
                (f"{rel} plugins[{i}]", e)
                for i, e in enumerate(data.get("plugins", []))
            ]
    for rel, entry in found:
        if entry.get("name") != SKILL_NAME:
            problems.append(
                f"{rel} ZC007 name {entry.get('name')!r} must be {SKILL_NAME!r}"
            )
        if entry.get("version") != want:
            problems.append(
                f"{rel} ZC007 version {entry.get('version')!r}, CHANGELOG head is {want}"
            )
    return problems


def main() -> int:
    problems: list[str] = []
    checked = files()
    me = Path(__file__).resolve()
    for p in checked:
        rel = p.relative_to(ROOT).as_posix()
        raw = p.read_bytes()
        if b"\r" in raw:
            problems.append(f"{rel}:1 ZC008 {raw.count(b'\r')} CR bytes; files are LF")
        text = raw.decode("utf-8", errors="replace")
        fenced = False
        for n, line in enumerate(text.splitlines(), 1):
            if p.suffix == ".md" and line.lstrip().startswith(("```", "~~~")):
                fenced = not fenced
            elif p.suffix == ".md" and not fenced:
                # snippets in inline code are examples, not links
                problems += check_links(p, rel, n, INLINE_CODE.sub("", line))
            if any(d in line for d in DASHES):
                problems.append(f"{rel}:{n} ZC001 en or em dash; use - or --")
            for label, rx in SECRETS:
                if rx.search(line):
                    problems.append(f"{rel}:{n} ZC002 looks like a {label}")
            home = HOME_PATH.search(line) if p.resolve() != me else None
            if home:
                problems.append(f"{rel}:{n} ZC004 absolute home path {home.group(0)!r}")
        if p.suffix == ".json":
            try:
                json.loads(text)
            except json.JSONDecodeError as exc:
                problems.append(f"{rel}:{exc.lineno} ZC006 invalid JSON: {exc.msg}")
        if p.name == "SKILL.md":
            problems += check_skill(p, rel, text)
    problems += check_manifests()
    for line in problems:
        print(line)
    print(f"{len(checked)} files checked, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
