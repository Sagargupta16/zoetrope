"""Read a batch's batch.json: the one place account and machine settings live.

  batch = load("outputs/my-batch/batch.json")   # or the batch folder itself

Keys: root, accent, tag, end {handle, follow, ai_line}, music_dir, voice {name, speed}; optional comfy {exe, home,
url}, render {workers, maxrate}, readers {audience_file}, package {check}, engine (folder). A missing required key raises
BatchError naming the key and the file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

REQUIRED = ("root", "accent", "tag", "end", "music_dir", "voice")
NESTED = {"end": ("handle", "follow", "ai_line"), "voice": ("name", "speed")}


class BatchError(ValueError):
    """batch.json is missing, unreadable or lacks a key."""


@dataclass
class Batch:
    path: Path  # folder holding batch.json
    root: Path  # the batch's working root: always the batch folder (root in batch.json must be ".")
    accent: str
    tag: str
    end: dict
    music_dir: Path
    voice: dict
    comfy: dict = field(default_factory=dict)
    render: dict = field(default_factory=dict)
    readers: dict = field(default_factory=dict)
    package: dict = field(default_factory=dict)
    engine: Path | None = None  # folder of the audio engine; None means <root>/engine

    def __getitem__(self, key: str):
        """The dict form gen.py and audio.py also read: batch["root"], batch["comfy"]["url"]."""
        if key not in self.__dataclass_fields__:
            raise KeyError(key)
        return getattr(self, key)

    def get(self, key: str, default=None):
        return (
            getattr(self, key, default) if key in self.__dataclass_fields__ else default
        )

    @property
    def builds(self) -> Path:
        return self.root / "builds"

    @property
    def videos(self) -> Path:
        return self.root / "videos"


def _resolve(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def load(path: str | Path) -> Batch:
    file = Path(path)
    if file.is_dir():
        file = file / "batch.json"
    if not file.is_file():
        raise BatchError(f"{file} not found (create the batch with new-batch)")
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise BatchError(f"{file} is not valid JSON: {error}") from error
    for key in REQUIRED:
        if key not in data:
            raise BatchError(f"{file}: missing key '{key}'")
    for key, inner in NESTED.items():
        if not isinstance(data[key], dict):
            raise BatchError(f"{file}: '{key}' must be an object")
        for name in inner:
            if name not in data[key]:
                raise BatchError(f"{file}: missing key '{key}.{name}'")
    base = file.parent.resolve()
    root = _resolve(base, data["root"]).resolve()
    if (
        root != base
    ):  # find() walks up from a build to batch.json, so builds must sit under the batch folder
        raise BatchError(
            f"{file}: key 'root' resolves to {root}; only the batch folder itself is supported (use \".\")"
        )
    return Batch(
        path=base,
        root=root,
        accent=data["accent"],
        tag=data["tag"],
        end=data["end"],
        music_dir=_resolve(base, data["music_dir"]),
        voice=data["voice"],
        comfy=data.get("comfy", {}),
        render=data.get("render", {}),
        readers=data.get("readers", {}),
        package=data.get("package", {}),
        engine=_resolve(base, data["engine"]) if data.get("engine") else None,
    )


def find(build_or_batch: str | Path) -> Batch:
    """The batch for a build folder (builds/<b>) or for the batch folder itself."""
    start = Path(build_or_batch).resolve()
    for folder in (start, *start.parents):
        if (folder / "batch.json").is_file():
            return load(folder)
    raise BatchError(f"no batch.json at or above {start}")


def selftest() -> int:
    """Both forms (attributes and a plain dict) must read the same in gen.py and audio.py."""
    import sys
    import tempfile

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sample = {
        "root": ".",
        "accent": "#fff",
        "tag": "T",
        "end": {"handle": "h", "follow": "f", "ai_line": "a"},
        "music_dir": "music",
        "voice": {"name": "af_heart", "speed": 1.0},
        "comfy": {"exe": "comfy", "home": "ComfyUI", "url": "http://127.0.0.1:8188"},
    }
    with tempfile.TemporaryDirectory() as folder:
        file = Path(folder) / "batch.json"
        file.write_text(json.dumps(sample), encoding="utf-8")
        made = load(file)
        import audio
        import gen

        left, right = gen.Comfy(made), gen.Comfy(sample)
        assert left.url == right.url and left.exe == right.exe, "gen: forms differ"
        assert left.root == Path(folder).resolve(), "gen: root"
        assert audio.get(made, "music_dir") == made.music_dir
        assert audio.get(made, "voice")["speed"] == audio.get(sample, "voice")["speed"]
        assert audio.get(made, "engine") is None and made["root"] == made.root
        assert audio.get(made, "comfy")["home"] == sample["comfy"]["home"]
        file.write_text(
            json.dumps({**sample, "root": "../elsewhere"}), encoding="utf-8"
        )
        try:
            load(file)
        except BatchError as error:
            assert "'root'" in str(error), "root: the error names another key"
        else:
            raise AssertionError("root: a root outside the batch folder loaded")
    print("BATCH SELFTEST: PASS")
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(selftest() if sys.argv[1:] == ["selftest"] else 2)
