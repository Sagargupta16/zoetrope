"""Package a finished build: videos/<slug>.mp4 and videos/<slug>.json, from post.json and out/<slug>.mp4.

  python studio/studio.py package builds/01-slug

post.json holds title, caption, alt_text, sources and cover_ms (hashtags optional). The checks here are about the
file and about plain text hygiene only; a batch's own caption and account rules live in an outside command named
by batch.json package.check, which gets the post.json and the video path and must exit 0. Uploads nothing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

BAD = {0xA0, 0xAD, 0x200B, 0x200C, 0x200D, 0x2013, 0x2014, 0x202F, 0x2060, 0xFEFF}


def probe(path: Path) -> dict:
    done = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_entries",
            "stream=codec_type,codec_name,profile,pix_fmt,width,height,r_frame_rate,avg_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(done.stdout)


def package(batch, build: Path) -> int:
    post = json.loads((build / "post.json").read_text(encoding="utf-8"))
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    slug = timeline["slug"]
    video = build / "out" / f"{slug}.mp4"
    if not video.is_file():
        print(f"missing {video}")
        return 2
    info = probe(video)
    streams = {stream["codec_type"]: stream for stream in info["streams"]}
    seconds = float(info["format"]["duration"])
    size = int(info["format"]["size"])
    picture = streams.get("video", {})
    problems = []
    if (picture.get("codec_name"), picture.get("profile"), picture.get("pix_fmt")) != (
        "h264",
        "High",
        "yuv420p",
    ):
        problems.append(
            f"video is {picture.get('codec_name')} {picture.get('profile')} {picture.get('pix_fmt')}, not H.264 High yuv420p"
        )
    if (picture.get("width"), picture.get("height"), picture.get("r_frame_rate")) != (
        1080,
        1920,
        "30/1",
    ):
        problems.append(
            f"video is {picture.get('width')}x{picture.get('height')} at {picture.get('r_frame_rate')}, not 1080x1920 at 30"
        )
    # The average rate as well: a file with one frame a few ticks short still reads r_frame_rate 30/1, its
    # average reads 30.0001, and a publisher that asks for exactly 30/1 refuses it (qa.py V01 says the same).
    average = picture.get("avg_frame_rate")
    if picture.get("r_frame_rate") == "30/1" and average in (None, "", "0/0"):
        problems.append(
            "ffprobe gave no average frame rate: the timing of the frames is not checked"
        )
    elif picture.get("r_frame_rate") == "30/1" and average != "30/1":
        problems.append(
            f"the frames are not evenly timed (average rate {average}, not 30/1): render again with render.py, "
            "or for a file this engine did not render use the ffmpeg line in the manual (studio.md, V01)"
        )
    if streams.get("audio", {}).get("codec_name") != "aac":
        problems.append("no AAC audio stream")
    if size > 100_000_000:
        problems.append(f"{size / 1e6:.1f} MB is over 100 MB")
    if not slug.replace("-", "").isalnum() or slug != slug.lower():
        problems.append(f"slug {slug} must be lowercase letters, digits and hyphens")
    caption = post.get("caption", "")
    if not post.get("title") or not caption:
        problems.append("post.json needs a title and a caption")
    flagged = sorted(
        {
            hex(ord(char))
            for char in caption + post.get("title", "") + post.get("alt_text", "")
            if ord(char) in BAD
        }
    )
    if flagged:
        problems.append(f"characters to remove: {flagged}")
    if "http://" in caption or "https://" in caption:
        problems.append(
            "a link in the caption is not clickable: name the source instead"
        )
    cover = int(post.get("cover_ms", 0))
    if not 0 <= cover < seconds * 1000:
        problems.append(f"cover_ms {cover} is outside the video")
    for source in post.get("sources", []):
        if not source.get("title") or not source.get("url", "").startswith("https://"):
            problems.append(f"source needs a title and an https url: {source}")
    if not post.get("sources"):
        problems.append("no sources listed")
    command = (batch.package.get("check") or "").strip()
    if not problems and command:
        done = subprocess.run(
            [*command.split(), str(build / "post.json"), str(video)],
            capture_output=True,
            text=True,
            check=False,
        )
        if done.returncode != 0:
            problems.append(
                f"package.check exited {done.returncode}: {(done.stdout + done.stderr).strip()}"
            )
    if problems:
        for problem in problems:
            print("FIX " + problem)
        return 1
    entry = {**post, "audio": True, "duration_s": round(seconds, 1), "cover_ms": cover}
    out = batch.videos
    out.mkdir(exist_ok=True)
    shutil.copyfile(video, out / f"{slug}.mp4")
    (out / f"{slug}.json").write_text(
        json.dumps(entry, indent=2, ensure_ascii=False) + chr(10),
        encoding="utf-8",
        newline="",
    )
    print(f"{slug}: {seconds:.1f} s, {size / 1e6:.1f} MB, cover {cover} ms")
    # What the owner reads before an upload: the two lines a viewer meets first, and the counts. (A title lost
    # a word between the script and post.json on one film, and only the caption had been read.) Printed in
    # ASCII, so a console that cannot show a letter never stops a package that is already written.
    first = next((row for row in caption.splitlines() if row.strip()), "")
    tags = str(post.get("hashtags") or "")
    for text in (
        f"title: {post['title']}",
        f"first line ({len(first)} characters): {first}",
        f"caption {len(caption)} characters, {len(tags.split())} hashtags ({len(tags)} characters),"
        f" {len(post['sources'])} sources",
    ):
        print(text.encode("ascii", "backslashreplace").decode("ascii"))
    print(out / f"{slug}.mp4")
    return 0
