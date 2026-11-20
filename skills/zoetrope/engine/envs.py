# envs.py : the engine's Python environments, each a venv in which every wheel matched the sha256 its lock records.
# uv run --with-requirements installs a package whose --hash line is wrong (uv 0.13.8, 2026-11-16: a zeroed hash for
# six installed with exit 0), and no uv setting changes that; uv pip install --require-hashes refuses it. So each
# environment is a venv that uv pip install --require-hashes fills from its lock, and it counts only once that passed:
#   uv run --no-project python envs.py            this folder's .venv, from requirements.txt on .python-version
#   uv run --no-project python envs.py --cache .  the same lock's venv in ~/.cache/zoetrope/envs (setup.sh's check)
# The build command, uv run --no-project --with-requirements requirements.txt python <script>, finds that .venv,
# sees every pin met and runs in it with nothing added (without a .venv it falls back to an unchecked overlay). The
# side environments (qa_speech.py, voice.py, plate3d.py) call side() for theirs: one folder per lock in the cache, so
# a changed lock builds a new venv and never touches the one an older lock made.
# Standard library only: it runs before any environment exists.
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ENV_DIR = Path(
    os.environ.get("ZOETROPE_ENVS") or Path.home() / ".cache" / "zoetrope" / "envs"
)
STAMP = "zoetrope-lock.txt"  # in a finished venv: the sha256 of the lock that filled it


class EnvError(RuntimeError):
    """uv could not make the environment: a wheel whose sha256 did not match, a failed download, no such Python."""


def python_in(venv):
    """The interpreter of a venv folder."""
    venv = Path(venv)
    return (
        venv / "Scripts" / "python.exe" if os.name == "nt" else venv / "bin" / "python"
    )


def _digest(lock):
    return hashlib.sha256(Path(lock).read_bytes()).hexdigest()


def ready(venv, lock):
    """True when venv was filled from this exact lock (its stamp holds the lock's sha256) and has its interpreter."""
    stamp = Path(venv, STAMP)
    return (
        stamp.is_file()
        and stamp.read_text(encoding="utf-8").strip() == _digest(lock)
        and python_in(venv).is_file()
    )


def _uv(*args):
    r = subprocess.run(
        ["uv", *args],
        capture_output=True,
        text=True,
        errors="replace",
        stdin=subprocess.DEVNULL,
        check=False,
    )
    if r.returncode:
        # uv's first lines say what failed (error, cause), its last ones what it computed; a hash list in between
        said = [x.strip() for x in (r.stderr or r.stdout).splitlines() if x.strip()]
        if len(said) > 6:
            said = said[:3] + ["..."] + said[-2:]
        raise EnvError(
            f"uv {' '.join(args[:2])} failed ({r.returncode}): {' | '.join(said)}"
        )


def build(lock, venv, python=None):
    """Make venv hold the packages of lock, every wheel checked against its sha256 (uv pip install --require-hashes),
    on python (a version such as "3.13"; None lets uv choose). Nothing is done when venv already holds this lock.
    A failed build leaves venv as it was. Returns venv's interpreter; raises EnvError."""
    lock, venv = Path(lock).resolve(), Path(venv).absolute()
    if ready(venv, lock):
        return python_in(venv)
    if venv.exists() and not Path(venv, STAMP).is_file():
        raise EnvError(
            f"{venv} is there and envs.py did not make it: move it away, or build in another folder"
        )
    if venv.exists() and Path(sys.prefix).resolve() == venv.resolve():
        raise EnvError(
            f"{venv} holds an older {lock.name} and runs this script: delete {venv.name}, then run again"
        )
    if not shutil.which("uv"):
        raise EnvError("uv is not on PATH (winget install astral-sh.uv)")
    venv.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f"{venv.name}.partial-", dir=venv.parent))
    new = tmp / "venv"
    try:
        _uv(
            "venv",
            "--quiet",
            "--relocatable",
            *(["--python", python] if python else []),
            str(new),
        )
        _uv(
            "pip",
            "install",
            "--quiet",
            "--python",
            str(python_in(new)),
            "--require-hashes",
            "-r",
            str(lock),
        )
        Path(new, STAMP).write_text(_digest(lock) + "\n", encoding="utf-8")
        try:
            if venv.exists():
                shutil.rmtree(
                    venv
                )  # an older lock's venv: its stamp says envs.py made it
            new.rename(venv)
        except OSError as e:
            if not ready(
                venv, lock
            ):  # another process may have finished the same venv first
                raise EnvError(
                    f"could not put the new environment at {venv} (is a process running in it?): {e}"
                ) from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return python_in(venv)


def side_dir(lock, python):
    """Where side() keeps lock's venv: one folder per lock name, Python version and lock sha256."""
    lock = Path(lock)
    return ENV_DIR / f"{lock.stem}-py{python}-{_digest(lock)[:12]}"


def side(lock, python):
    """The interpreter of lock's environment in ENV_DIR, built on first use (a side environment: speech, Kokoro,
    Blender). Raises EnvError."""
    return build(lock, side_dir(lock, python), python)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Build the engine's environment from requirements.txt, every wheel checked against its sha256."
    )
    ap.add_argument(
        "folder",
        nargs="?",
        default=".",
        help="the folder that holds requirements.txt and .python-version (default: here)",
    )
    ap.add_argument(
        "--cache",
        action="store_true",
        help="build in ~/.cache/zoetrope/envs instead of <folder>/.venv, and print its interpreter",
    )
    a = ap.parse_args(argv)
    folder = Path(a.folder)
    lock, pin = folder / "requirements.txt", folder / ".python-version"
    if not lock.is_file():
        print(
            f"ENV: FIX no {lock}: copy the whole engine folder (cp -r <skill>/engine/. .)"
        )
        return 1
    version = pin.read_text(encoding="utf-8").strip() if pin.is_file() else None
    try:
        py = side(lock, version) if a.cache else build(lock, folder / ".venv", version)
    except EnvError as e:
        print(f"ENV: FIX {e}")
        return 1
    if a.cache:
        print(f"python {py.as_posix()}")
    print(f"ENV: OK {py.parent.parent}: every wheel matched its sha256 in {lock.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
