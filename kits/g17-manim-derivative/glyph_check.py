# glyph_check.py : does each font really have the glyphs we need? A missing glyph renders as .notdef.
from PIL import ImageFont

FONTS = {
    "Cambria": ("C:/Windows/Fonts/cambria.ttc", 0),
    "Cambria Math": ("C:/Windows/Fonts/cambria.ttc", 1),
    "Cambria Italic": ("C:/Windows/Fonts/cambriai.ttf", 0),
    "Segoe UI": ("C:/Windows/Fonts/segoeui.ttf", 0),
    "Segoe UI Semibold": ("C:/Windows/Fonts/seguisb.ttf", 0),
}
NEED = {
    "prime U+2032": "\u2032",
    "minus U+2212": "\u2212",
    "arrow U+2192": "\u2192",
    "sup two U+00B2": "\u00b2",
    "middot U+00B7": "\u00b7",
    "x": "x",
    "h": "h",
}
for name, (path, idx) in FONTS.items():
    f = ImageFont.truetype(path, 80, index=idx)
    nd = bytes(f.getmask("\U0010fffd"))
    fam = " ".join(f.getname())
    row = []
    for label, ch in NEED.items():
        m = f.getmask(ch)
        ok = m.size != (0, 0) and bytes(m) != nd
        row.append(f"{label}={'ok' if ok else 'MISSING'}")
    print(f"{name} [{fam}]: " + ", ".join(row))
