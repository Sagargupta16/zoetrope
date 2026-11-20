# blocks_preview.py : the gallery of the block library and the style kits, so a person or a builder sees every block
# before choosing one. `python blocks_preview.py <out folder> [--size WxH] [--kits]` writes blocks_text.png,
# blocks_data.png and blocks_fx.png (one labelled cell per block or style, drawn at the moment it reads best) and, with
# --kits, kits.png (one poster per kit in ../kits, each drawn in its own process). A sheet is at most 2000 px on a side;
# more cells than a page holds go to <name>_2.png, <name>_3.png. Real data in every cell, nothing downloaded.
import argparse
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import engine as E
import numpy as np
from PIL import Image, ImageDraw

LIMIT = 2000  # px: the longest side of any sheet page
GAP = 4  # px between cells
CAP_H = 34  # px of caption under each cell
CAP_SIZE = 22
CELL_LONG = 640  # px: the long side of a cell's picture
SHEET_BG = "#0A0D14"
CELL_BG = "#161B26"
CAP_INK = "#F2F4F8"
CAP_MUTED = "#9AA6BD"
FAIL_INK = "#FF8A80"
POSTER_LONG = 960  # px: a kit poster is shrunk to this before it is handed back
KIT_TIMEOUT = 600  # s a kit gets to import and draw one frame
WORDS = [
    "Build",
    "it",
    "first",
    "then",
    "make",
    "it",
    "good",
]  # the caption demo: 0.4 s a word
SUBJECT_BG = ("#35507F", "#0E1424")
DATA_BG = "#101828"
LABEL_INK = "#FFFFFF"
SUBJECT_INK = "#FF6B4A"
CODE_OLD = (
    "def total(items):\n"
    "    s = 0\n"
    "    for i in items:\n"
    "        s = s + i.price\n"
    "    return s\n"
)
CODE_NEW = "def total(items):\n    return sum(i.price for i in items)\n"
CODE_TYPED = (
    'def greet(name):\n    # say hello\n    msg = "hello " + name\n    return msg, 3\n'
)
RACE_KEYS = [
    (0.0, {"Ada": 30, "Bo": 22, "Cy": 15}),
    (1.0, {"Ada": 38, "Bo": 52, "Cy": 41}),
    (2.0, {"Ada": 61, "Bo": 58, "Cy": 74}),
]
PIE_PARTS = [("Rent", 42), ("Food", 23), ("Travel", 15), ("Other", 20)]
LINE_VALUES = [12, 18, 15, 27, 24, 38, 45]
LINE_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
CHAT = [
    ("them", "Is the proof sheet ready?"),
    ("me", "Yes, every cell is labelled"),
    ("them", "Great, ship it"),
]


# ---------------------------------------------------------------- cell pictures


def _w():
    return E.W * E.SS


def _h():
    return E.H * E.SS


def _photo():
    """A dark blue ground that stands in for a picture under a text block."""
    return E.gradient(*SUBJECT_BG)


def _flat(colour=DATA_BG):
    return E.canvas(colour)


def _subject():
    """A frame with something in it to push in on, vignette or mark: a grid, a disc and a word."""
    img = _photo()
    d = ImageDraw.Draw(img)
    w, h = img.size
    for i in range(1, 8):
        d.line((w * i / 8, 0, w * i / 8, h), fill="#FFFFFF28", width=2)
        d.line((0, h * i / 8, w, h * i / 8), fill="#FFFFFF28", width=2)
    r = h * 0.22
    d.ellipse((w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r), fill=SUBJECT_INK)
    E.text(img, "Subject", (w / 2 / E.SS, h / 2 / E.SS), E.H * 0.1, LABEL_INK, "mm")
    return img


def _layers():
    """(fg RGBA with a rounded subject on transparency, bg RGB with a grid) for dolly_zoom and rack_focus."""
    w, h = _w(), _h()
    fg = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(fg)
    d.rounded_rectangle(
        (w * 0.36, h * 0.3, w * 0.64, h * 0.7), h * 0.04, fill=SUBJECT_INK
    )
    E.text(fg, "Front", (w / 2 / E.SS, h / 2 / E.SS), E.H * 0.07, LABEL_INK, "mm")
    bg = _photo()
    d = ImageDraw.Draw(bg)
    for i in range(17):
        d.line((w * i / 16, 0, w * i / 16, h), fill="#FFFFFF50", width=3)
        d.line((0, h * i / 16, w, h * i / 16), fill="#FFFFFF50", width=3)
    E.text(bg, "Back", (w * 0.2 / E.SS, h * 0.2 / E.SS), E.H * 0.07, LABEL_INK, "mm")
    E.text(bg, "Back", (w * 0.8 / E.SS, h * 0.8 / E.SS), E.H * 0.07, LABEL_INK, "mm")
    return fg, bg.convert("RGB")


def _plate(bg, letter):
    """A background with one big letter, as an RGB frame a transition can start from or end on."""
    img = bg.convert("RGBA")
    E.text(img, letter, (E.W / 2, E.H / 2), E.H * 0.6, LABEL_INK, "mm")
    return img.convert("RGB")


def _marked():
    """(image, box) of a word to mark."""
    img = _photo()
    xy = (E.W / 2, E.H / 2)
    size = E.H * 0.14
    E.text(img, "Zoetrope", xy, size, LABEL_INK, "mm")
    return img, E.text_box("Zoetrope", xy, size, "mm")


def _wav(path, seconds=3.0, rate=44100):
    """A WAV written locally: three tones that sweep, with a beat, so the bands move."""
    t = np.arange(int(seconds * rate)) / rate
    sweep = 200 * 2 ** (t * 2.5)
    sig = 0.5 * np.sin(2 * np.pi * np.cumsum(sweep) / rate)
    sig += 0.3 * np.sin(2 * np.pi * 880 * t) * (np.sin(2 * np.pi * 2 * t) > 0)
    sig += 0.2 * np.sin(2 * np.pi * 90 * t)
    data = (np.clip(sig, -1, 1) * 32000).astype("<i2")
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(data.tobytes())
    return path


# ---------------------------------------------------------------- the cell lists


def text_cells():
    """[(caption, draw)] for blocks_text: every style and kind."""
    import blocks_text as T

    cells = []
    for style in T.LOWER_THIRD_STYLES:
        cells.append(
            (
                f"lower_third  style={style}",
                lambda s=style: T.lower_third(
                    _photo(), 2.0, "Alex Rivera", "Product lead", s, 0.0, 4.0
                ),
            )
        )
    words = [(w, 0.4 * i, 0.4 * i + 0.36) for i, w in enumerate(WORDS)]
    for style in T.CAPTION_STYLES:
        cells.append(
            (
                f"captions  style={style}",
                lambda s=style: T.captions(_photo(), 1.0, words, s),
            )
        )

    def marker(kind):
        img, (l, t, r, b) = _marked()
        box = (l, t, r, b)
        if kind == "arrow":
            box = (l - E.W * 0.15, t - E.H * 0.2, l - 20, (t + b) / 2)
        return T.marker(img, 1.2, kind, box)

    for kind in T.MARKER_KINDS:
        cells.append((f"marker  kind={kind}", lambda k=kind: marker(k)))
    cells.append(
        (
            "end_card",
            lambda: T.end_card(_photo(), 2.0, "Thanks for watching", "@zoetrope"),
        )
    )
    cells.append(("chat_thread", lambda: T.chat_thread(_photo(), 4.5, CHAT)))
    cells.append(
        (
            "notification",
            lambda: T.notification(
                _photo(), 1.5, "Render finished", "All 20 cells drawn, no gate failed."
            ),
        )
    )
    cells.append(
        ("code_typing  lang=python", lambda: T.code_typing(_photo(), 3.6, CODE_TYPED))
    )
    cells.append(
        (
            "code_diff  lang=python",
            lambda: T.code_diff(_photo(), 2.3, CODE_OLD, CODE_NEW, "python"),
        )
    )
    return cells


def data_cells(tmp):
    """[(caption, draw)] for blocks_data: every chart, counter, ring, bar, route and audio style."""
    import blocks_data as D

    levels = D.analyse_wav(_wav(Path(tmp) / "gallery.wav"), E.FPS, 32)
    cells = [
        (
            "bar_race  3 rows",
            lambda: D.bar_race(_flat(), 2.4, RACE_KEYS, ["2022", "2023", "2024"]),
        ),
        (
            "line_draw",
            lambda: D.line_draw(_flat(), 2.4, LINE_VALUES, LINE_LABELS),
        ),
        (
            "pie  donut=False",
            lambda: D.pie(_flat(), 2.4, PIE_PARTS, donut=False),
        ),
        (
            "pie  donut=True",
            lambda: D.pie(_flat(), 2.4, PIE_PARTS, donut=True, total_label="Spend"),
        ),
        (
            "counter",
            lambda: D.counter(_flat(), 2.0, 12840, 0, suffix=" views"),
        ),
        ("stat_ring", lambda: D.stat_ring(_flat(), 2.0, 72, "Done")),
        ("progress_bar", lambda: D.progress_bar(_flat(), 2.0, 64, "Upload")),
        (
            "route_arc",
            lambda: D.route_arc(
                _flat(),
                2.6,
                (E.W * 0.2, E.H * 0.72),
                (E.W * 0.8, E.H * 0.3),
                ("Delhi", "Mumbai"),
            ),
        ),
    ]
    for style in ("bars", "mirror", "wave"):
        cells.append(
            (
                f"audio_bars  style={style}",
                lambda s=style: D.audio_bars(_flat(), 1.7, levels, s, color2="#4AA3FF"),
            )
        )
    return cells


def fx_cells():
    """[(caption, draw)] for blocks_fx: backgrounds, the light leak, transitions and camera moves."""
    import blocks_fx as X

    cells = [
        (f"background  {name}", lambda f=fn: f(1.5).convert("RGB"))
        for name, fn in X.BACKGROUNDS.items()
    ]
    cells.append(
        (
            "light_leak  side=left",
            lambda: X.light_leak(_subject(), 0.6, 0.0, 1.2, side="left"),
        )
    )
    for name, fn in X.FX_MENU.items():
        cells.append(
            (
                f"transition  {name}  p=0.4",
                lambda f=fn: f(
                    _plate(X.mesh_gradient(1.0), "A"),
                    _plate(X.aurora(1.0), "B"),
                    0.4,
                ),
            )
        )
    cells.append(("camera  push_in k=0.8", lambda: X.push_in(_subject(), 0.8, 1.5)))
    cells.append(("camera  pull_out k=0.2", lambda: X.pull_out(_subject(), 0.2, 1.5)))
    cells.append(
        (
            "camera  dolly_zoom k=0.7",
            lambda: X.dolly_zoom(*_layers(), 0.7, 0.4),
        )
    )
    cells.append(
        (
            "camera  rack_focus k=0.3",
            lambda: X.rack_focus(*_layers(), 0.3),
        )
    )
    cells.append(("vignette  strength=0.7", lambda: X.vignette(_subject(), 0.7)))
    return cells


# ---------------------------------------------------------------- kit posters


def _poster(out, size):
    """Run in a child process, from a folder with the engine and one kit's files: draw the kit's key frame to out."""
    E.W, E.H = size  # before scenes is imported: a kit reads the size when it loads
    import scenes

    keys = getattr(scenes, "KEY_TIMES", None)
    if keys:
        first = keys[0]
        t = float(first["t"] if isinstance(first, dict) else first[0])
    else:
        t = 0.4 * float(scenes.DURATION)
    img = scenes.draw(t).convert("RGB")
    k = POSTER_LONG / max(img.size)
    if k < 1:
        img = img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)
    img.save(out)
    print(f"t={t:.2f}")


def _reason(proc):
    """The last line a failed child said, in ASCII."""
    lines = [x.strip() for x in (proc.stderr or "").splitlines() if x.strip()]
    msg = lines[-1] if lines else f"exit {proc.returncode} with no message"
    return msg.encode("ascii", "replace").decode()


def kit_cell(kit, size):
    """(caption, picture or None, why) for one kit folder: drawn in a copy of the engine beside the kit's files."""
    here = Path(__file__).resolve().parent
    tmp = Path(tempfile.mkdtemp(prefix="gallery-kit-"))
    try:
        eng = tmp / "engine"
        eng.mkdir()
        for f in list(here.glob("*.py")) + [here / ".python-version"]:
            if f.is_file():
                shutil.copy2(f, eng / f.name)
        for f in kit.iterdir():
            if f.is_file() and f.suffix != ".md":
                shutil.copy2(f, eng / f.name)
        why = ""
        for w, h in (size, size[::-1]):  # a kit built for 9:16 refuses 16:9
            out = tmp / "poster.png"
            try:
                proc = subprocess.run(
                    [
                        sys.executable,
                        "blocks_preview.py",
                        "--poster",
                        str(out),
                        "--size",
                        f"{w}x{h}",
                    ],
                    cwd=eng,
                    capture_output=True,
                    text=True,
                    timeout=KIT_TIMEOUT,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                why = why or f"timed out after {KIT_TIMEOUT} s"
                continue
            if proc.returncode == 0 and out.exists():
                with Image.open(out) as im:
                    pic = im.convert("RGB")
                return f"kit  {kit.name}  {proc.stdout.strip()} s", pic, ""
            why = why or _reason(proc)
        return f"kit  {kit.name}", None, why
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- the sheets


def _tile():
    """(w, h) of a cell's picture, in the film's aspect."""
    if E.W >= E.H:
        return CELL_LONG, round(CELL_LONG * E.H / E.W)
    return round(CELL_LONG * E.W / E.H), CELL_LONG


def _caption(sheet, text, x, y, w):
    size = CAP_SIZE
    while size > 12 and E.text_w(text, size) > w - 12:
        size -= 1
    E.text(sheet, text, (x + 6, y + CAP_H / 2), size, CAP_INK, "lm")


def _picture(draw, tw, th):
    """(tile, why): the cell drawn at the full size, shrunk into the tile; a failed draw gives (None, why)."""
    try:
        img = draw()
    except Exception as e:  # noqa: BLE001 (a block that fails gets a cell that says so; the gallery goes on)
        return None, f"{type(e).__name__}: {e}".encode("ascii", "replace").decode()
    img = img.convert("RGB")
    k = min(tw / img.width, th / img.height)
    return img.resize(
        (max(1, round(img.width * k)), max(1, round(img.height * k))), Image.LANCZOS
    ), ""


def write_sheet(out, name, cells, tile=None):
    """cells: [(caption, draw)] where draw() returns a picture, or [(caption, picture, why)]. Writes name.png and, past a
    page, name_2.png ...; returns [(path, w, h, n)]. A cell that fails says why instead of a picture."""
    tw, th = tile or _tile()
    cols = max(1, (LIMIT - GAP) // (tw + GAP))
    rows = max(1, (LIMIT - GAP) // (th + CAP_H + GAP))
    per = cols * rows
    pages = []
    for p0 in range(0, len(cells), per):
        chunk = cells[p0 : p0 + per]
        ncols = min(cols, len(chunk))
        nrows = -(-len(chunk) // cols)
        wid = GAP + ncols * (tw + GAP)
        hei = GAP + nrows * (th + CAP_H + GAP)
        sheet = Image.new("RGBA", (wid, hei), E.hexrgb(SHEET_BG))
        d = ImageDraw.Draw(sheet)
        for i, cell in enumerate(chunk):
            x = GAP + (i % cols) * (tw + GAP)
            y = GAP + (i // cols) * (th + CAP_H + GAP)
            d.rectangle((x, y, x + tw - 1, y + th + CAP_H - 1), fill=CELL_BG)
            if len(cell) == 3:
                cap, pic, why = cell
                if pic is not None:
                    k = min(tw / pic.width, th / pic.height)
                    pic = pic.resize(
                        (max(1, round(pic.width * k)), max(1, round(pic.height * k))),
                        Image.LANCZOS,
                    )
            else:
                cap, draw = cell
                pic, why = _picture(draw, tw, th)
            if pic is not None:
                sheet.paste(
                    pic, (x + (tw - pic.width) // 2, y + (th - pic.height) // 2)
                )
            else:
                lines = E.wrap(f"did not draw: {why}", 20, tw - 24, False)[:8]
                for j, line in enumerate(lines):
                    E.text(
                        sheet,
                        line,
                        (x + 12, y + 14 + j * 28),
                        20,
                        FAIL_INK,
                        "la",
                        bold=False,
                    )
            _caption(sheet, cap, x, y + th, tw)
        path = Path(out) / (
            f"{name}.png" if not pages else f"{name}_{len(pages) + 1}.png"
        )
        sheet.convert("RGB").save(path)
        pages.append((path, wid, hei, len(chunk)))
    for old in Path(out).glob(f"{name}_*.png"):  # a page left by a longer run
        if old not in [p[0] for p in pages] and old.stem[len(name) + 1 :].isdigit():
            old.unlink()
    return pages


def main(argv=None):
    ap = argparse.ArgumentParser(description="Gallery of the zoetrope blocks and kits.")
    ap.add_argument("out", nargs="?", help="folder the sheets are written to")
    ap.add_argument("--size", default="1920x1080", help="WxH the blocks are drawn at")
    ap.add_argument(
        "--kits", action="store_true", help="also draw kits.png, a poster per kit"
    )
    ap.add_argument("--poster", help="(internal) draw one kit's key frame to this file")
    a = ap.parse_args(argv)
    try:
        w, h = (int(x) for x in a.size.lower().split("x"))
    except ValueError:
        ap.error("--size is WxH, for example 1920x1080")
    if a.poster:
        _poster(a.poster, (w, h))
        return 0
    if not a.out:
        ap.error("an output folder is needed")
    E.W, E.H = w, h
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gallery-") as tmp:
        sets = [
            ("blocks_text", text_cells()),
            ("blocks_data", data_cells(tmp)),
            ("blocks_fx", fx_cells()),
        ]
        if a.kits:
            kits = Path(__file__).resolve().parent.parent / "kits"
            folders = sorted(p for p in kits.iterdir() if p.is_dir())
            sets.append(("kits", [kit_cell(k, (w, h)) for k in folders]))
        for name, cells in sets:
            for path, pw, ph, n in write_sheet(out, name, cells):
                print(f"{path.name}: {pw}x{ph} px, {n} cells")
    return 0


if __name__ == "__main__":
    sys.exit(main())
