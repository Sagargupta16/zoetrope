"""brand.py : a brand kit as brand.json in the working folder, loaded and checked before a build.

    python brand.py check [brand.json]    problems, one ASCII line each; exit 0 when there are none, 1 when there are

    {
      "palette": {"ink": "#14213D", "paper": "#FFF8EC", "accent": "#C2410C"},
      "fonts": {"bold": "Nunito:800", "regular": "Nunito:400"},
      "logo": "logo.png",
      "notes": "Warm paper ground, ink text, accent only on one word a scene.",
      "pairs": [["ink", "paper"], ["accent", "paper"]]
    }

palette: name -> "#RRGGBB". fonts: bold and regular, as the family strings engine.font() and every text helper take
(fonts.py: "Family:weight[:italic]"). logo: a path, relative to the kit's folder (optional). notes: free text for the
builder (optional). pairs: [text, background] couples, each a palette name or a hex, that must read at WCAG 4.5:1.
check() reads the font cache and never fetches; run `python fonts.py fetch` for a missing family.

    import brand
    kit = brand.load()                       # brand.json in the working folder
    INK, PAPER = kit.palette["ink"], kit.palette["paper"]
    engine.text(img, "Hello", (96, 120), 80, INK, bold=kit.fonts["bold"])
"""

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import fonts

MIN_CONTRAST = 4.5  # WCAG AA for body text
_HEX = re.compile(r"#[0-9A-Fa-f]{6}")
_FONT_KEYS = ("bold", "regular")


@dataclass
class Brand:
    """palette: name -> "#RRGGBB"; fonts: {"bold": ..., "regular": ...} family strings; logo: absolute path or None;
    notes: free text; pairs: [(text, background), ...] as written in the file; path: the file it came from."""

    palette: dict = field(default_factory=dict)
    fonts: dict = field(default_factory=dict)
    logo: str | None = None
    notes: str = ""
    pairs: list = field(default_factory=list)
    path: str = ""


def _read(path):
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(f"{p} not found") from None
    except (OSError, ValueError) as e:
        raise ValueError(f"{p} cannot be read as JSON: {e}") from None
    if not isinstance(data, dict):
        raise TypeError(f"{p}: the top level must be an object")
    return p, data


def load(path="brand.json"):
    """The kit in path as a Brand. Reads only; raises FileNotFoundError or ValueError when the file is missing or is
    not a JSON object. Use check() for what is wrong inside it."""
    p, d = _read(path)
    logo = d.get("logo")
    pal = d.get("palette")
    fnt = d.get("fonts")
    pairs = d.get("pairs")
    return Brand(
        palette=dict(pal) if isinstance(pal, dict) else {},
        fonts=dict(fnt) if isinstance(fnt, dict) else {},
        logo=str((p.parent / logo).resolve())
        if isinstance(logo, str) and logo
        else None,
        notes=str(d.get("notes") or ""),
        pairs=[tuple(x) for x in pairs if isinstance(x, (list, tuple))]
        if isinstance(pairs, list)
        else [],
        path=str(p.resolve()),
    )


def _lin(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hexcolour):
    """WCAG relative luminance of "#RRGGBB"."""
    h = hexcolour.lstrip("#")
    r, g, b = (_lin(int(h[i : i + 2], 16)) for i in (0, 2, 4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    """WCAG contrast ratio of two "#RRGGBB" colours, 1 to 21."""
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _ascii(v):
    if isinstance(v, str):
        return v.encode("ascii", "backslashreplace").decode()
    return ascii(v)


def check(path="brand.json"):
    """Problem lines for the kit in path, ASCII, [] when it is sound: a colour that is not "#RRGGBB", a font family
    fonts.py does not hold or has not cached, a logo file that is missing, and each listed pair under 4.5:1."""
    try:
        p, d = _read(path)
    except (FileNotFoundError, ValueError, TypeError) as e:
        return [_ascii(str(e))]
    out = []
    pal = d.get("palette")
    colours = {}
    if not isinstance(pal, dict) or not pal:
        out.append("palette: missing or empty, give name -> #RRGGBB")
    else:
        for name, v in pal.items():
            if isinstance(v, str) and _HEX.fullmatch(v):
                colours[name] = v
            else:
                out.append(f"palette {_ascii(name)}: {_ascii(v)} is not #RRGGBB")
    fnt = d.get("fonts")
    if not isinstance(fnt, dict):
        out.append(
            "fonts: missing, give bold and regular family strings such as Nunito:800"
        )
    else:
        for key in _FONT_KEYS:
            if key not in fnt:
                out.append(f"fonts {key}: missing")
        for key, spec in fnt.items():
            out.extend(_font_problems(key, spec))
    logo = d.get("logo")
    if logo is not None:
        if not isinstance(logo, str) or not logo:
            out.append(f"logo: {_ascii(logo)} is not a path")
        elif not (p.parent / logo).is_file():
            out.append(f"logo: {_ascii(logo)} not found next to {_ascii(p.name)}")
    pairs = d.get("pairs", [])
    if not isinstance(pairs, list):
        out.append("pairs: must be a list of [text, background]")
        pairs = []
    for pr in pairs:
        if not (isinstance(pr, (list, tuple)) and len(pr) == 2):
            out.append(f"pairs {_ascii(pr)}: want [text, background]")
            continue
        got = []
        for ref in pr:
            c = colours.get(
                ref, ref if isinstance(ref, str) and _HEX.fullmatch(ref) else None
            )
            if c is None:
                out.append(
                    f"pairs {_ascii(pr)}: {_ascii(ref)} is not a valid palette name or #RRGGBB"
                )
            got.append(c)
        if None in got:
            continue
        r = contrast(*got)
        if r < MIN_CONTRAST:
            out.append(
                f"pairs {_ascii(pr[0])} on {_ascii(pr[1])}: contrast {r:.2f}:1 is under {MIN_CONTRAST}:1"
            )
    return out


def _font_problems(key, spec):
    if not isinstance(spec, str):
        return [f"fonts {_ascii(key)}: {_ascii(spec)} is not a family string"]
    try:
        row = fonts.pick(*fonts.parse(spec))
    except ValueError as e:
        return [f"fonts {_ascii(key)}: {_ascii(str(e))}"]
    if not fonts.cached(row):
        return [
            f"fonts {_ascii(key)}: {_ascii(spec)} is not cached, run python fonts.py fetch"
        ]
    try:
        fonts.load(spec, 20)  # a variable file rejects a weight outside its axis
    except (ValueError, OSError) as e:
        return [f"fonts {_ascii(key)}: {_ascii(str(e))}"]
    return []


def main(argv):
    if argv[:1] != ["check"] or len(argv) > 2:
        print("usage: python brand.py check [brand.json]")
        return 2
    path = argv[1] if len(argv) > 1 else "brand.json"
    problems = check(path)
    for line in problems:
        print(f"BRAND: {line}")
    if problems:
        print(f"BRAND: {len(problems)} problem(s) in {_ascii(path)}")
        return 1
    print(f"BRAND: OK {_ascii(path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
