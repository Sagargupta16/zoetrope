"""Render a stage video: seek the page frame by frame in headless Chrome and pipe the frames to ffmpeg.

Run from anywhere. --video is the build folder (absolute, or relative to the working folder or to --batch).
The page is served from the studio folder (/studio/) and the build folder (/build/) where they really are:

  uv run --no-project --with playwright python studio/render.py render --video builds/01-slug --out out.mp4
  uv run --no-project --with playwright python studio/render.py stills --video builds/01-slug --times 0,1.5,3.3 --out dir
  uv run --no-project --with playwright python studio/render.py bench --video builds/01-slug --frames 60

From code: render(batch, build, workers=None, maxrate=None, out=...). Workers and maxrate come from the
batch config's "render" object (a dict or an object), then 6 and 6500; an argument overrides both.

Every frame is a pure function of its time (runtime.js), so frame ranges render in parallel
processes and the segments join without a seam.
"""

from __future__ import annotations

import argparse
import base64
import http.server
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path
from typing import ClassVar

STUDIO = Path(__file__).resolve().parent
WORKERS = 6
MAXRATE = 6500
CHROME_ARGS = [
    "--force-prefers-no-reduced-motion",
    "--hide-scrollbars",
    "--force-device-scale-factor=1",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--font-render-hinting=none",
]


# stage.css loads its fonts from /studio/fonts/. A batch may keep its own copies in studio/fonts/; otherwise
# they come from the font cache the skill's engine/fonts.py fills (pinned to one commit, each file checked by
# sha256), where Inter's file has another name.
FONT_ALIASES = {"Inter-Variable.ttf": "Inter[opsz,wght].ttf"}


def font_cache() -> Path:
    return Path(
        os.environ.get("ZOETROPE_FONTS")
        or Path.home() / ".cache" / "zoetrope" / "fonts"
    )


def font_file(name: str) -> Path | None:
    for path in (STUDIO / "fonts" / name, font_cache() / FONT_ALIASES.get(name, name)):
        if path.is_file():
            return path
    return None


def fonts_ready() -> None:
    """Every font stage.css names is on disk before Chrome starts: a missing one fails the page with nothing
    but "A network error occurred". What is missing is fetched once through the engine's fonts.py."""
    css = (STUDIO / "stage.css").read_text(encoding="utf-8")
    names = sorted(set(re.findall('url[(]"/studio/fonts/([^"]+)"[)]', css)))
    fetcher = STUDIO.parent / "engine" / "fonts.py"
    if any(font_file(name) is None for name in names) and fetcher.is_file():
        subprocess.run([sys.executable, str(fetcher), "fetch"], check=False)
    missing = [name for name in names if font_file(name) is None]
    if missing:
        raise SystemExit(
            f"stage fonts missing: {', '.join(missing)}. Run `python {fetcher} fetch` (it fills {font_cache()}), "
            f"or copy the files into {STUDIO / 'fonts'}"
        )


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(
        self, *args: object
    ) -> None:  # keep the console for the render's own lines
        return


class Routed(Quiet):
    """/studio/... comes from the studio folder, /build/... from the build folder; nothing else is served."""

    roots: ClassVar[dict[str, Path]] = {}

    def translate_path(self, path: str) -> str:
        clean = urllib.parse.unquote(path.split("?", 1)[0].split("#", 1)[0])
        name, _, rest = clean.lstrip("/").partition("/")
        root = self.roots.get(name)
        if root is None:
            return str(STUDIO / "__not_served__")
        if name == "studio" and rest.startswith("fonts/"):
            return str(font_file(Path(rest).name) or STUDIO / "__not_served__")
        target = (root / rest).resolve()
        if root.resolve() not in (target, *target.parents):
            return str(STUDIO / "__not_served__")
        return str(target)


def serve(build: Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    fonts_ready()
    handler = type(
        "Handler", (Routed,), {"roots": {"studio": STUDIO, "build": build.resolve()}}
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def open_page(play, url: str):
    browser = play.chromium.launch(channel="chrome", headless=True, args=CHROME_ARGS)
    page = browser.new_page(
        viewport={"width": 1080, "height": 1920}, device_scale_factor=1
    )
    page.goto(url)
    page.wait_for_function(
        "window.__ready === true || !!window.__error", timeout=180_000
    )
    error = page.evaluate("window.__error || null")
    if error:
        browser.close()
        raise SystemExit(f"stage error: {error}")
    return browser, page


def encoder(out: Path, fps: int, fmt: str, crf: int, maxrate: int) -> subprocess.Popen:
    if fmt == "jpeg":
        source = ["-c:v", "mjpeg"]
        scale = "scale=in_color_matrix=bt601:in_range=full:out_color_matrix=bt709:out_range=tv"
    else:
        source = ["-c:v", "png"]
        scale = "scale=out_color_matrix=bt709:out_range=tv"
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "image2pipe",
        "-framerate",
        str(fps),
        *source,
        "-i",
        "-",
        "-vf",
        f"{scale},format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        str(crf),
        "-maxrate",
        f"{maxrate}k",
        "-bufsize",
        f"{2 * maxrate}k",
        "-profile:v",
        "high",
        "-level",
        "4.2",
        "-g",
        str(2 * fps),
        "-threads",
        "4",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        "-color_range",
        "tv",
        "-r",
        str(fps),
        str(out),
    ]
    return subprocess.Popen(command, stdin=subprocess.PIPE)


def worker(args: argparse.Namespace) -> None:
    from playwright.sync_api import sync_playwright

    shot = {
        "format": args.format,
        "optimizeForSpeed": True,
        "captureBeyondViewport": False,
    }
    if args.format == "jpeg":
        shot["quality"] = args.quality
    with sync_playwright() as play:
        browser, page = open_page(play, args.url)
        cdp = page.context.new_cdp_session(page)
        sink = encoder(Path(args.out), args.fps, args.format, args.crf, args.maxrate)
        assert sink.stdin is not None
        seek_s = shot_s = 0.0
        for frame in range(args.first, args.last):
            start = time.perf_counter()
            page.evaluate("t => window.__seek(t)", frame / args.fps)
            middle = time.perf_counter()
            data = cdp.send("Page.captureScreenshot", shot)["data"]
            sink.stdin.write(base64.b64decode(data))
            seek_s += middle - start
            shot_s += time.perf_counter() - middle
        sink.stdin.close()
        code = sink.wait()
        browser.close()
    count = max(1, args.last - args.first)
    print(
        json.dumps(
            {
                "first": args.first,
                "last": args.last,
                "seek_ms": round(1000 * seek_s / count, 1),
                "shot_ms": round(1000 * shot_s / count, 1),
                "ffmpeg": code,
            }
        )
    )
    if code:
        raise SystemExit(code)


def stage_url(base: str) -> str:
    return f"{base}/studio/stage.html?video=build"


def setting(batch: object, key: str, default: object = None) -> object:
    """One key of the batch config, whether it is a dict or an object with attributes."""
    if batch is None:
        return default
    if isinstance(batch, dict):
        return batch.get(key, default)
    return getattr(batch, key, default)


def render_setting(batch: object, key: str, default: int) -> int:
    value = setting(setting(batch, "render", None), key, None)
    return default if value is None else int(value)


def batch_root(build: Path, given: str | None = None) -> Path | None:
    """The folder that holds batch.json: the one given, else the nearest parent of the build."""
    if given:
        return Path(given).resolve()
    for folder in [build.resolve(), *build.resolve().parents]:
        if (folder / "batch.json").exists():
            return folder
    return None


def meta_of(url: str) -> dict:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as play:
        browser, page = open_page(play, url)
        meta = page.evaluate("window.__meta")
        browser.close()
    return meta


def render(
    batch: object,
    build: Path,
    workers: int | None = None,
    maxrate: int | None = None,
    **options: object,
) -> None:
    """Render build to options["out"]; start, end, format, quality and crf are the other options."""
    args = argparse.Namespace(
        out=None, start=None, end=None, format="jpeg", quality=95, crf=18
    )
    for key, value in options.items():
        if value is not None or key == "out":
            setattr(args, key, value)
    if args.out is None:
        raise SystemExit("render needs out=<file.mp4>")
    args.workers = workers or render_setting(batch, "workers", WORKERS)
    args.maxrate = maxrate or render_setting(batch, "maxrate", MAXRATE)
    server, base = serve(build)
    url = stage_url(base)
    meta = meta_of(url)
    fps = int(meta["fps"])
    first = round((args.start or 0) * fps)
    last = round((args.end if args.end is not None else meta["duration"]) * fps)
    total = last - first
    workers = max(1, min(args.workers, total // 30 or 1))
    out = Path(args.out).resolve()
    parts_dir = out.parent / (out.stem + "_parts")
    parts_dir.mkdir(parents=True, exist_ok=True)
    edges = [first + round(total * index / workers) for index in range(workers + 1)]
    # A join between two parts is moved onto a shot cut when one is near: inside a still shot a join
    # shows as a one-frame change in the encoder's noise (video 2's test cards, 2026-11-24).
    plan = build / "timeline.json"
    if plan.exists() and workers > 1:
        cuts = sorted(
            {
                round(shot["t0"] * fps)
                for shot in json.loads(plan.read_text(encoding="utf-8"))["shots"]
            }
        )
        reach = total // workers // 2
        for index in range(1, workers):
            near = [
                cut
                for cut in cuts
                if abs(cut - edges[index]) <= reach
                and edges[index - 1] + 30 < cut < last - 30
            ]
            if near:
                edges[index] = min(near, key=lambda cut: abs(cut - edges[index]))
    began = time.perf_counter()
    jobs = []
    for index in range(workers):
        part = parts_dir / f"part{index:02d}.mp4"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "worker",
            "--url",
            url,
            "--out",
            str(part),
            "--first",
            str(edges[index]),
            "--last",
            str(edges[index + 1]),
            "--fps",
            str(fps),
            "--format",
            args.format,
            "--quality",
            str(args.quality),
            "--crf",
            str(args.crf),
            "--maxrate",
            str(args.maxrate),
        ]
        jobs.append(
            (part, subprocess.Popen(command, stdout=subprocess.PIPE, text=True))
        )
    stats = []
    failed = False
    for part, job in jobs:
        output, _ = job.communicate()
        failed = failed or job.returncode != 0
        for line in output.splitlines():
            if line.startswith("{"):
                stats.append(json.loads(line))
    server.shutdown()
    if failed:
        raise SystemExit("a render worker failed")
    listing = parts_dir / "parts.txt"
    # Each part is listed with its exact length. Without it the concat demuxer takes the length from the part's
    # container, which holds it in milliseconds, so a part of 76 frames (2.533333 s) pulled every later frame
    # of the film a third of a millisecond early; a comparison that pairs frames by time then pairs neighbours.
    listing.write_text(
        "".join(
            f"file '{part.as_posix()}'{chr(10)}duration {(edges[index + 1] - edges[index]) / fps:.6f}{chr(10)}"
            for index, (part, _) in enumerate(jobs)
        ),
        encoding="utf-8",
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(out),
        ],
        check=True,
    )
    took = time.perf_counter() - began
    print(
        json.dumps(
            {
                "out": str(out),
                "frames": total,
                "workers": workers,
                "seconds": round(took, 1),
                "fps": round(total / took, 1),
                "bytes": out.stat().st_size,
                "parts": stats,
            }
        )
    )


def stills(batch: object, build: Path, args: argparse.Namespace) -> None:
    from playwright.sync_api import sync_playwright

    server, base = serve(build)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    times = [float(value) for value in args.times.split(",") if value.strip()]
    registry = {}
    with sync_playwright() as play:
        browser, page = open_page(play, stage_url(base))
        cdp = page.context.new_cdp_session(page)
        for moment in times:
            page.evaluate("t => window.__seek(t)", moment)
            data = cdp.send(
                "Page.captureScreenshot",
                {"format": "png", "captureBeyondViewport": False},
            )["data"]
            (out / f"t{moment:07.2f}.png").write_bytes(base64.b64decode(data))
            registry[f"{moment:.2f}"] = page.evaluate("window.__registry()")
        meta = page.evaluate("window.__meta")
        pages = page.evaluate(
            "typeof Kit !== 'undefined' && Kit.pages ? Kit.pages() : null"
        )
        browser.close()
    server.shutdown()
    result = {"meta": meta, "frames": registry}
    if pages is not None:
        result["pages"] = pages
    (out / "registry.json").write_text(
        json.dumps(result, indent=1), encoding="utf-8", newline=chr(10)
    )
    print(json.dumps({"stills": len(times), "out": str(out)}))


def bench(batch: object, build: Path, args: argparse.Namespace) -> None:
    server, base = serve(build)
    url = stage_url(base)
    for fmt in ("jpeg", "png"):
        part = build / f"bench_{fmt}.mp4"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "worker",
            "--url",
            url,
            "--out",
            str(part),
            "--first",
            "0",
            "--last",
            str(args.frames),
            "--fps",
            "30",
            "--format",
            fmt,
            "--quality",
            "95",
            "--crf",
            "18",
            "--maxrate",
            "6500",
        ]
        began = time.perf_counter()
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        print(
            fmt,
            round(time.perf_counter() - began, 1),
            "s",
            result.stdout.strip(),
            result.stderr.strip()[-300:],
        )
    server.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    one = commands.add_parser("render")
    one.add_argument("--video", required=True)
    one.add_argument("--out", required=True)
    one.add_argument("--workers", type=int)
    one.add_argument("--start", type=float)
    one.add_argument("--end", type=float)
    one.add_argument("--format", default="jpeg", choices=["jpeg", "png"])
    one.add_argument("--quality", type=int, default=95)
    one.add_argument("--crf", type=int, default=18)
    one.add_argument("--maxrate", type=int)
    two = commands.add_parser("stills")
    two.add_argument("--video", required=True)
    two.add_argument("--times", required=True)
    two.add_argument("--out", required=True)
    three = commands.add_parser("bench")
    three.add_argument("--video", required=True)
    three.add_argument("--frames", type=int, default=60)
    for each in (one, two, three):
        each.add_argument(
            "--batch", help="the batch folder (default: found from the build path)"
        )
    four = commands.add_parser("worker")
    four.add_argument("--url", required=True)
    four.add_argument("--out", required=True)
    four.add_argument("--first", type=int, required=True)
    four.add_argument("--last", type=int, required=True)
    four.add_argument("--fps", type=int, default=30)
    four.add_argument("--format", default="jpeg")
    four.add_argument("--quality", type=int, default=95)
    four.add_argument("--crf", type=int, default=18)
    four.add_argument("--maxrate", type=int, default=6500)
    args = parser.parse_args()
    if args.command == "worker":
        worker(args)
        return
    build = Path(args.video)
    root = batch_root(build, args.batch)
    if not build.is_absolute() and not build.exists() and root is not None:
        build = root / build
    batch = None
    if root is not None and (root / "batch.json").exists():
        batch = json.loads((root / "batch.json").read_text(encoding="utf-8"))
    if args.command == "render":
        render(
            batch,
            build,
            args.workers,
            args.maxrate,
            out=args.out,
            start=args.start,
            end=args.end,
            format=args.format,
            quality=args.quality,
            crf=args.crf,
        )
    elif args.command == "stills":
        stills(batch, build, args)
    else:
        bench(batch, build, args)


if __name__ == "__main__":
    main()
