"""Narration and the final mix for a build, on a copy of zoetrope's audio engine (<batch>/engine).

Run from the engine folder so its pinned environment is used:

  cd <batch>/engine
  uv run --no-project --with-requirements requirements.txt python ../studio/audio.py narrate ../builds/01-slug
  uv run --no-project --with-requirements requirements.txt python ../studio/audio.py mix ../builds/01-slug

From code: audio.narrate(batch, build) and audio.mix(batch, build, video). `batch` is the batch config (a
batch.Batch or a plain dict): `music_dir` is the folder of the licensed tracks (<theme>/<track>.mp3, named by
script.json "music"), `voice` is {name, speed} (script.json "voice" overrides it per film) and `root` holds
engine/. Pass --batch <batch.json> on the command line (default: ../batch.json). Importing this file loads
nothing heavy: numpy and the engine come in when narrate or mix runs.

narrate: speaks script.json line by line (the batch voice through voice.synthesize, cached per line), then
lays the lines out tightly on one clock: narration/voice.wav and narration/layout.json (every line, word
and caption token with its time). A line's text may hold {shown|spoken} so the caption shows "1883" while
the voice says "eighteen eighty-three".

mix: voice (polished) over the licensed music bed, ducked while it speaks, plus the clips' own sound where
a shot asks for it and effects on cuts and reveals; mastered to -14 LUFS, then muxed into the video.
"""

from __future__ import annotations

import argparse
import difflib
import json
import subprocess
import sys
from pathlib import Path

A = S = V = np = (
    None  # the engine's audio, synth and voice modules and numpy, loaded by engine()
)
SR = 24000  # replaced by the engine's own rate in engine()
LEAD = 0.12  # the voice starts this long after frame 0
GAP = 0.2  # silence between lines unless a line names its own gap


def get(source, key, default=None):
    """A key of the batch config, whether it is a dict or a batch.Batch."""
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def engine_dir(batch) -> Path:
    """The folder of the audio engine: the batch's `engine` key, else <root>/engine."""
    return Path(
        str(get(batch, "engine") or Path(str(get(batch, "root") or ".")) / "engine")
    ).resolve()


def engine(batch) -> None:
    """Load numpy and the engine (engine_dir) once. The engine has its own audio.py, so it is loaded by path
    under another name and never as `audio`."""
    global A, S, V, np, SR
    if V is not None:
        return
    import importlib.util

    import numpy

    np = numpy
    folder = engine_dir(batch)
    if not (folder / "voice.py").exists():
        raise SystemExit(f"no audio engine at {folder} (voice.py is missing)")
    sys.path.insert(0, str(folder))
    loaded = {}
    for name in ("audio", "synth", "voice"):
        spec = importlib.util.spec_from_file_location(
            f"zoetrope_engine_{name}", folder / f"{name}.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded[name] = module
    A, S, V = loaded["audio"], loaded["synth"], loaded["voice"]
    SR = V.SR


def parse(text: str) -> tuple[str, list[tuple[list[str], int]]]:
    """The spoken sentence, and units of (caption tokens, how many spoken words they cover)."""
    units: list[tuple[list[str], int]] = []
    said: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char == "{":
            close = text.index("}", index)
            shown, _, spoken = text[index + 1 : close].partition("|")
            end = close + 1
            while end < len(text) and not text[end].isspace():
                end += 1
            tail = text[close + 1 : end]
            units.append(((shown + tail).split(), len(V._words(spoken))))
            said.append(spoken + tail)
            index = end
            continue
        end = index
        while end < len(text) and not text[end].isspace() and text[end] != "{":
            end += 1
        word = text[index:end]
        count = len(V._words(word))
        if count:
            units.append(([word], count))
        elif units:  # stray punctuation joins the token before it
            units[-1][0][-1] += word
        said.append(word)
        index = end
    return " ".join(said), units


def align(caption: str, spoken: str) -> list[tuple[list[str], int]]:
    """Units of (caption tokens, spoken words they cover) from a caption and its spoken form: equal words pair
    one to one, and a stretch that differs (1883 against eighteen eighty-three) becomes one unit."""
    shown = caption.split()
    keys = [(V._words(token) or [""])[0].lower() for token in shown]
    said = [word.lower() for word in V._words(spoken)]
    units: list[tuple[list[str], int]] = []
    carry = 0
    for tag, a0, a1, b0, b1 in difflib.SequenceMatcher(
        a=keys, b=said, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            for index in range(a0, a1):
                units.append(([shown[index]], 1 + carry))
                carry = 0
        elif tag == "replace":
            units.append((shown[a0:a1], b1 - b0 + carry))
            carry = 0
        elif (
            tag == "delete"
        ):  # caption tokens no word is spoken for join the unit before them
            if units:
                units[-1] = (units[-1][0] + shown[a0:a1], units[-1][1])
            else:
                units.append((shown[a0:a1], 0))
        elif units:  # spoken words with no caption token ride on the unit before them
            units[-1] = (units[-1][0], units[-1][1] + b1 - b0)
        else:
            carry += b1 - b0
    merged: list[tuple[list[str], int]] = []
    for tokens, count in units:  # a unit with no spoken word joins its neighbour
        if count == 0 and merged:
            merged[-1] = (merged[-1][0] + tokens, merged[-1][1])
        elif merged and merged[-1][1] == 0:
            merged[-1] = (merged[-1][0] + tokens, count)
        else:
            merged.append((tokens, count))
    return merged


def write_mono(path: Path, samples) -> None:
    import wave

    pcm = np.clip(samples * 32767, -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SR)
        out.writeframes(pcm.tobytes())


def narrate(batch, build: Path) -> None:
    engine(batch)
    build = Path(build)
    script = json.loads((build / "script.json").read_text(encoding="utf-8"))
    folder = build / "narration"
    # A line is {"text": "In {1883|eighteen eighty-three} ..."} or {"caption": "In 1883 ...", "spoken": "In eighteen ..."}.
    parsed = [
        (line, line["spoken"], align(line["caption"], line["spoken"]))
        if "spoken" in line
        else (line, *parse(line["text"]))
        for line in script["lines"]
    ]
    settings = get(batch, "voice") or {}
    voice = {
        "voice": get(settings, "name"),
        "speed": get(settings, "speed", 1.0),
        **script.get("voice", {}),
    }
    narration = V.synthesize(
        [{"id": line["id"], "text": spoken} for line, spoken, _ in parsed],
        folder=str(folder),
        lexicon=script.get("lexicon"),
        speed=voice.get("speed", 1.0),
        voice=voice.get("voice"),
    )
    cursor = float(script.get("lead", LEAD))
    pieces = []
    lines = []
    for (line, spoken, units), made in zip(parsed, narration["lines"], strict=True):
        ref = made["parts"][0]["start"]
        length = 0
        chunks = []
        for part in made["parts"]:
            wave_data = V.dec(str(folder / part["file"]))[
                part["clip"][0] : part["clip"][1]
            ]
            offset = int(round((part["start"] - ref) * SR))
            chunks.append((offset, wave_data))
            length = max(length, offset + len(wave_data))
        speech = np.zeros(length)
        for offset, wave_data in chunks:
            speech[offset : offset + len(wave_data)] += wave_data
        words = [
            {
                "w": word["w"],
                "t0": round(cursor + word["start"] - ref, 3),
                "t1": round(cursor + word["end"] - ref, 3),
            }
            for word in made["words"]
        ]
        expected = sum(count for _, count in units)
        tokens = []
        if words and expected == len(words):
            position = 0
            for shown, count in units:
                group = words[position : position + count]
                position += count
                t0, t1 = group[0]["t0"], group[-1]["t1"]
                step = (t1 - t0) / len(shown)
                for number, item in enumerate(shown):
                    tokens.append(
                        {
                            "d": item,
                            "t0": round(t0 + number * step, 3),
                            "t1": round(t0 + (number + 1) * step, 3),
                        }
                    )
        else:  # the engine split the words another way: spread the tokens by their length
            flat = [item for shown, _ in units for item in shown]
            t0 = cursor + made["speech_start"] - ref
            t1 = cursor + made["speech_end"] - ref
            total = sum(len(item) for item in flat) or 1
            done = 0
            for item in flat:
                tokens.append(
                    {
                        "d": item,
                        "t0": round(t0 + (t1 - t0) * done / total, 3),
                        "t1": round(t0 + (t1 - t0) * (done + len(item)) / total, 3),
                    }
                )
                done += len(item)
            print(
                f"note {line['id']}: {len(words)} spoken words against {expected} expected; caption times are spread evenly"
            )
        t0 = round(cursor + made["speech_start"] - ref, 3)
        t1 = round(cursor + made["speech_end"] - ref, 3)
        lines.append(
            {
                "id": line["id"],
                "text": " ".join(item for shown, _ in units for item in shown),
                "spoken": spoken,
                "t0": t0,
                "t1": t1,
                "speed": made["speed"],
                "words": words,
                "tokens": tokens,
            }
        )
        pieces.append((int(round(cursor * SR)), speech))
        rate = len(words) / max(0.01, t1 - t0)
        print(
            f"{line['id']} {t0:7.2f}-{t1:7.2f} {t1 - t0:5.2f} s {rate:4.1f} w/s  {lines[-1]['text']}"
        )
        cursor += length / SR + float(line.get("gap", script.get("gap", GAP)))
    total = max(start + len(speech) for start, speech in pieces)
    track = np.zeros(total)
    for start, speech in pieces:
        track[start : start + len(speech)] += speech
    write_mono(folder / "voice.wav", track)
    speech_end = lines[-1]["t1"]
    (folder / "layout.json").write_text(
        json.dumps(
            {
                "sr": SR,
                "speech_end": speech_end,
                "voice": narration.get("voice"),
                "lines": lines,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    count = sum(len(line["words"]) for line in lines)
    print(
        f"{len(lines)} lines, {count} words, speech ends {speech_end:.2f} s; the hook's speech is over at {lines[0]['t1']:.2f} s"
    )


def looped(path: Path, seconds: float, start: float = 0.0, end: float | None = None):
    """The track from `start` (to `end`, to leave out a fade the track ends on), repeated with a 2.5 s
    crossfade when it is shorter than the video."""
    track = A._decode_mono(str(path))[int(start * SR) : int(end * SR) if end else None]
    need = int(seconds * SR)
    fade = int(2.5 * SR)
    out = track.copy()
    while len(out) < need:
        ramp = np.linspace(0.0, 1.0, fade)
        joined = out[-fade:] * np.sqrt(1 - ramp) + track[:fade] * np.sqrt(ramp)
        out = np.concatenate([out[:-fade], joined, track[fade:]])
    return out[:need]


def envelope(length: int, fade_in: float, fade_out: float):
    shape = np.ones(length)
    first, last = min(length, int(fade_in * SR)), min(length, int(fade_out * SR))
    if first:
        shape[:first] = np.linspace(0.0, 1.0, first)
    if last:
        shape[length - last :] *= np.linspace(1.0, 0.0, last)
    return shape


def add(bus, sound, at: float, gain: float) -> None:
    start = max(0, int(at * SR))
    stop = min(len(bus), start + len(sound))
    if stop > start:
        bus[start:stop] += sound[: stop - start] * gain


def effect(kind: str, seed: int) -> tuple:
    """The sound, its default gain, and how long before the picture it starts."""
    if kind == "whoosh":
        return S.whoosh(0.45, seed=seed), 0.11, 0.22
    if kind == "impact":
        return S.impact(1.0, seed=seed), 0.5, 0.0
    if kind == "boom":
        return S.boom(1.1), 0.42, 0.0
    if kind == "riser":
        return S.riser(1.6, seed=seed), 0.16, 1.6
    if kind == "tick":
        return S.tick(seed=seed), 0.5, 0.0
    if kind == "pop":
        return S.tick(2600, seed=seed), 0.6, 0.0
    raise SystemExit(f"unknown effect {kind}")


def mix(batch, build: Path, video: str | None = None) -> None:
    engine(batch)
    build = Path(build)
    script = json.loads((build / "script.json").read_text(encoding="utf-8"))
    timeline = json.loads((build / "timeline.json").read_text(encoding="utf-8"))
    plan = {
        shot["id"]: shot
        for shot in json.loads((build / "shots.json").read_text(encoding="utf-8"))[
            "shots"
        ]
    }
    seconds = timeline["duration"]
    total = int(round(seconds * SR))
    voice = np.zeros(total)
    spoken = V.dec(str(build / "narration" / "voice.wav"))[:total]
    voice[: len(spoken)] = spoken

    music = script["music"]
    music_dir = get(batch, "music_dir")
    if not music_dir:
        raise SystemExit(
            "the batch config has no music_dir (the folder of the licensed tracks)"
        )
    bed = looped(
        Path(str(music_dir)) / music["theme"] / f"{music['track']}.mp3",
        seconds,
        float(music.get("start", 0.0)),
        music.get("end"),
    )
    bed = np.pad(bed, (0, max(0, total - len(bed))))[
        :total
    ]  # looped() cuts at int(), total is rounded
    bed = bed * envelope(total, 0.3, float(music.get("fade_out", 2.2)))
    ambience = np.zeros(total)
    effects = np.zeros(total)
    cues = []
    for number, shot in enumerate(timeline["shots"]):
        spec = plan[shot["id"]]
        media = shot["media"]
        level = spec.get("amb")
        if level and media["kind"] == "clip":
            sound_file = build / (media["dir"] + ".wav")
            if sound_file.exists():
                start = int(media.get("offset", 0.0) * SR)
                sound = V.dec(str(sound_file))[
                    start : start + int((shot["t1"] - shot["t0"]) * SR)
                ]
                if len(sound):
                    loud = np.sqrt((sound**2).mean()) + 1e-9
                    gain = 10 ** (float(-30 if level is True else level) / 20) / loud
                    add(
                        ambience,
                        sound * envelope(len(sound), 0.12, 0.2),
                        shot["t0"],
                        gain,
                    )
        kind = shot.get("tin", {}).get("kind", "cut")
        auto = {
            "whip": "whoosh",
            "slide": "whoosh",
            "zoom": "whoosh",
            "punch": "pop",
            "flash": "impact",
        }.get(kind)
        if auto and spec.get("sfx") is not False:
            cues.append((auto, shot["t0"], None, number))
        for item in shot["over"]:
            auto = {
                "stamp": "impact",
                "number": "pop",
                "hook": "boom" if shot["t0"] == 0 else None,
            }.get(item["type"])
            if auto and item.get("sfx") is not False:
                cues.append((auto, item["at"], None, number))
        for extra in spec.get("sfx") or []:
            at = (
                extra["at"]
                if isinstance(extra["at"], (int, float))
                else shot["t0"] + float(str(extra["at"]).lstrip("+"))
            )
            cues.append((extra["kind"], at, extra.get("gain"), number))
    for kind, at, gain, seed in cues:
        sound, default, lead = effect(kind, seed)
        add(effects, sound, at - lead + 1 / 30, default if gain is None else gain)

    # The bed (music and clip sound) sits about 12 dB under itself while the voice speaks.
    under = V.duck_mix(
        bed + ambience * (10 ** (-18 / 20) / (np.sqrt((bed**2).mean()) + 1e-9)) ** -1,
        voice,
        depth_db=float(music.get("duck_db", 12)),
        polish=True,
    )
    raw = under[:total] + effects
    out = build / "out"
    out.mkdir(exist_ok=True)
    A.write_wav(out / "mix_raw.wav", raw)
    result = A.master(str(out / "mix_raw.wav"), str(out / "mix.wav"))
    print(
        json.dumps(
            {
                "I": result["I"],
                "tp": result["tp"],
                "LRA": result.get("LRA"),
                "effects": len(cues),
                "seconds": seconds,
            }
        )
    )
    if video:
        source = Path(video)
        final = out / f"{script['slug']}.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-i",
                str(out / "mix.wav"),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-b:a",
                "256k",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-shortest",
                "-movflags",
                "+faststart",
                str(final),
            ],
            check=True,
        )
        print(str(final))


def load_batch(path: str | None):
    """The batch config: batch.load(path) when batch.py is beside this file, else the JSON as a dict."""
    here = Path(__file__).resolve().parent
    file = Path(path) if path else here.parent / "batch.json"
    if not file.exists():
        raise SystemExit(f"no batch config at {file} (pass --batch)")
    sys.path.insert(0, str(here))
    try:
        from batch import load as load_config  # noqa: PLC0415 - not imported at module import time
    except ImportError:
        return json.loads(file.read_text(encoding="utf-8"))
    finally:
        sys.path.remove(str(here))
    return load_config(file)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["narrate", "mix"])
    parser.add_argument("build")
    parser.add_argument("--batch")
    parser.add_argument("--video")
    args = parser.parse_args()
    batch = load_batch(args.batch)
    build = Path(args.build).resolve()
    if args.command == "narrate":
        narrate(batch, build)
    else:
        mix(batch, build, args.video)


if __name__ == "__main__":
    main()
