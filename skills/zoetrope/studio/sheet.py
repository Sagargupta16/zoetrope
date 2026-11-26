"""Tile frames into one labelled contact sheet.

uv run --no-project --with pillow python studio/sheet.py OUT.png FRAME [FRAME ...] [--cols 6] [--width 300]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def strip(
    paths: list[Path],
    out: Path,
    height: int,
    crop: tuple[int, int, int, int] | None = None,
) -> Path:
    """Join pictures side by side at one height (optionally cropped first) into out."""
    pics = []
    for path in paths:
        with Image.open(path) as image:
            frame = image.convert("RGB")
        if crop:
            frame = frame.crop(crop)
        pics.append(
            frame.resize(
                (round(frame.width * height / frame.height), height), Image.LANCZOS
            )
        )
    sheet = Image.new(
        "RGB",
        (sum(pic.width for pic in pics) + 8 * (len(pics) - 1), height),
        (20, 20, 20),
    )
    x = 0
    for pic in pics:
        sheet.paste(pic, (x, 0))
        x += pic.width + 8
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def look(
    film: Path,
    out: Path,
    step: float = 1.25,
    cols: int = 5,
    rows: int = 3,
    width: int = 432,
) -> tuple[list[Path], int]:
    """The owner's look at a finished film: one frame every `step` seconds (and the last one), tiled on sheets
    of cols x rows with each frame's time on it. Sheets already in `out` are removed first, so the folder shows
    one film. Returns the sheets and the number of frames; raises RuntimeError when ffmpeg or ffprobe is
    missing or fails. Three readers saying READY is not the bar: a film is looked at before it is packaged."""
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("look needs ffmpeg and ffprobe on PATH")
    # the length of the picture, not of the file: an audio tail is longer than the last frame
    length = None
    for entry in ("stream=duration", "format=duration"):
        probe = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                entry,
                "-of",
                "csv=p=0",
                str(film),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            length = float(probe.stdout.strip().splitlines()[0])
            break
        except (ValueError, IndexError):
            continue
    if length is None:
        raise RuntimeError(
            f"ffprobe gave no length for {film}: {probe.stderr.strip()[:200]}"
        )
    if step <= 0:
        raise RuntimeError("the step must be more than 0 seconds")
    times = [
        round(index * step, 2)
        for index in range(int(length / step) + 1)
        if index * step < length - 0.05
    ]
    if not times or length - 0.1 - times[-1] > 0.3:
        times.append(round(max(0.0, length - 0.1), 2))
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("look_*.png"):
        old.unlink()
    tall = round(width * 1920 / 1080)
    font = ImageFont.load_default(30)
    per = cols * rows
    sheets = []
    frame = out / "frame.png"
    for first in range(0, len(times), per):
        chunk = times[first : first + per]
        page = Image.new(
            "RGB", (cols * width, -(-len(chunk) // cols) * tall), (20, 20, 20)
        )
        draw = ImageDraw.Draw(page)
        for index, at in enumerate(chunk):
            frame.unlink(missing_ok=True)
            subprocess.run(
                [
                    ffmpeg,
                    "-v",
                    "error",
                    "-y",
                    "-ss",
                    f"{at:.3f}",
                    "-i",
                    str(film),
                    "-frames:v",
                    "1",
                    "-vf",
                    f"scale={width}:{tall}",
                    str(frame),
                ],
                capture_output=True,
                check=False,
            )
            x, y = (index % cols) * width, (index // cols) * tall
            if frame.is_file():
                with Image.open(frame) as picture:
                    page.paste(picture.convert("RGB"), (x, y))
            draw.rectangle((x, y, x + 118, y + 40), fill=(0, 0, 0))
            draw.text((x + 6, y + 3), f"{at:.2f}", font=font, fill=(255, 230, 0))
        name = out / f"look_{len(sheets) + 1:02d}.png"
        page.save(name)
        sheets.append(name)
    frame.unlink(missing_ok=True)
    return sheets, len(times)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("out")
    parser.add_argument("frames", nargs="+")
    parser.add_argument("--cols", type=int, default=6)
    parser.add_argument("--width", type=int, default=300)
    args = parser.parse_args()
    paths = [Path(item) for item in args.frames]
    cells = []
    for path in paths:
        with Image.open(path) as image:
            frame = image.convert("RGB")
        height = round(frame.height * args.width / frame.width)
        cells.append((path.stem, frame.resize((args.width, height), Image.LANCZOS)))
    cell_h = max(cell.height for _, cell in cells)
    label_h, pad = 22, 8
    cols = min(args.cols, len(cells))
    rows = -(-len(cells) // cols)
    sheet = Image.new(
        "RGB",
        (pad + cols * (args.width + pad), pad + rows * (cell_h + label_h + pad)),
        (24, 24, 24),
    )
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, (name, cell) in enumerate(cells):
        x = pad + (index % cols) * (args.width + pad)
        y = pad + (index // cols) * (cell_h + label_h + pad)
        draw.text((x + 2, y + 4), name, fill=(235, 235, 235), font=font)
        sheet.paste(cell, (x, y + label_h))
    sheet.save(args.out)
    print(args.out, sheet.size)


if __name__ == "__main__":
    main()
