#!/usr/bin/env bash
# setup.sh : first-use check for the zoetrope skill. Installs nothing globally; safe to run again at any time.
# Prints "ok" or "FIX <what> -> <how>" per dependency and exits 1 if anything needs fixing.
set -u
here="$(cd "$(dirname "$0")" && pwd)"
fail=0

if command -v uv >/dev/null 2>&1; then
  echo "ok   uv $(uv --version | cut -d' ' -f2)"
else
  echo "FIX  uv missing -> winget install astral-sh.uv, then open a new shell"
  fail=1
fi

# the same search as contract.find_ffmpeg: PATH, then Homebrew on Apple silicon, then /usr/local; ffprobe beside it
ff=$(type -P ffmpeg)
if [ -z "$ff" ]; then
  for p in /opt/homebrew/bin/ffmpeg /usr/local/bin/ffmpeg; do
    if [ -e "$p" ]; then ff="$p"; break; fi
  done
fi
if [ -n "$ff" ]; then
  if "$ff" -hide_banner -encoders 2>/dev/null | grep -Eq '^[[:space:]]*[A-Z.]{6}[[:space:]]+libx264[[:space:]]'; then
    echo "ok   ffmpeg $("$ff" -hide_banner -version | head -1 | cut -d' ' -f3) with libx264 at $ff"
  else
    echo "FIX  the ffmpeg at $ff has no libx264 (videos fall back to AV1, VP9 or GIF) -> winget install Gyan.FFmpeg"
    fail=1
  fi
  probe="${ff%/*}/$(basename "$ff" | sed 's/ffmpeg/ffprobe/')"
  if "$probe" -version >/dev/null 2>&1; then
    echo "ok   ffprobe at $probe"
  else
    echo "FIX  ffprobe missing or would not run at $probe, beside the ffmpeg -> it ships with ffmpeg; reinstall Gyan.FFmpeg"
    fail=1
  fi
else
  echo "FIX  ffmpeg not on PATH, in /opt/homebrew/bin or in /usr/local/bin -> winget install Gyan.FFmpeg, then open a new shell"
  fail=1
fi

# the engine pins its Python in engine/.python-version, so a proof and its render run on one interpreter (Q1304
# compares major.minor); no file means no pin, and this script does not guess one
pyver=""
if [ -f "$here/engine/.python-version" ]; then
  pyver=$(tr -d '[:space:]' < "$here/engine/.python-version")
fi
if [ -z "$pyver" ]; then
  echo "FIX  engine/.python-version is missing or empty -> git restore engine/.python-version"
  fail=1
fi

# the engine's own interpreter, run as every build runs it: from the engine folder, on the pin, on requirements.txt
engine_python() {
  (cd "$here/engine" && printf '%s\n' "$1" | PYTHONDONTWRITEBYTECODE=1 uv run --no-project --python "$pyver" \
    --with-requirements requirements.txt python -)
}

if [ "$fail" -eq 0 ]; then
  # first run downloads the pinned wheels into the uv cache; later runs are instant. Each requirements.in pin is
  # held against what requirements.txt really installs, so the two files cannot drift apart unseen
  pkg_out=$(engine_python 'import sys
from importlib import metadata
import numpy, PIL
print("py", sys.version.split()[0])
for line in open("requirements.in", encoding="utf-8"):
    pin = line.split("#")[0].strip()
    if "==" in pin:
        name, want = (p.strip() for p in pin.split("==", 1))
        print("pkg", name.lower(), want, metadata.version(name))' 2>&1 | tr -d '\r')
  if printf '%s\n' "$pkg_out" | grep -q "^py "; then
    echo "ok   python $(printf '%s\n' "$pkg_out" | sed -n 's/^py //p') (engine/.python-version says $pyver)"
    while read -r name want have; do
      [ -n "$name" ] || continue
      if [ "$have" = "$want" ]; then
        echo "ok   $name $have, equal to its requirements.in pin"
      else
        echo "FIX  $name $have installs from requirements.txt but requirements.in pins $want -> uv pip compile --generate-hashes requirements.in -o requirements.txt (in engine/)"
        fail=1
      fi
    done <<< "$(printf '%s\n' "$pkg_out" | sed -n 's/^pkg //p')"
  else
    echo "FIX  pinned Pillow and numpy did not install on Python $pyver ($(printf '%s\n' "$pkg_out" | tail -1)) -> check network once, or uv python install $pyver, then rerun setup.sh"
    fail=1
  fi
fi

# the default font, asked of the engine itself (engine.font tries FONT_BOLD in order)
if [ "$fail" -eq 0 ]; then
  font_out=$(engine_python 'import os, sys
sys.path.insert(0, os.getcwd())
import engine
try:
    print("font", getattr(engine.font(32), "path", "(path not reported)"))
except FileNotFoundError:
    print("font-missing")' 2>&1 | tr -d '\r')
  if printf '%s\n' "$font_out" | grep -q "^font "; then
    echo "ok   default font $(printf '%s\n' "$font_out" | sed -n 's/^font //p')"
  elif printf '%s\n' "$font_out" | grep -q "^font-missing"; then
    echo "FIX  none of engine.py's default fonts exist -> install Arial, or on Linux fonts-liberation / fonts-dejavu-core, or put an installed .ttf path first in FONT_BOLD and FONT_REG"
    fail=1
  else
    echo "FIX  importing the engine failed ($(printf '%s\n' "$font_out" | tail -1)) -> run python -c \"import engine\" in engine/ to see the traceback"
    fail=1
  fi
fi

# the free fonts the cards name (engine/fonts.py): a note, not a failure, since a card that names one says so itself
if [ "$fail" -eq 0 ]; then
  fonts_out=$(uv run --no-project --with-requirements "$here/engine/requirements.txt" python "$here/engine/fonts.py" list 2>&1)
  missing=$(printf '%s\n' "$fonts_out" | grep -c "(missing)")
  if ! printf '%s\n' "$fonts_out" | grep -q "^Inter "; then
    echo "NOTE could not list the font cache: $fonts_out"
  elif [ "$missing" -eq 0 ]; then
    echo "ok   the 14 free font families the cards name are cached (engine/fonts.py)"
  else
    echo "NOTE $missing font families not cached -> python engine/fonts.py fetch (6.8 MB, SIL OFL)"
  fi
fi

# the speech model (engine/qa_speech.py): a note, since only a narrated build needs it; there Q806 is NOT CHECKED
# without it, so the build is rejected until it is fetched
if [ "$fail" -eq 0 ]; then
  if speech_out=$(uv run --no-project --with-requirements "$here/engine/requirements.txt" python "$here/engine/qa_speech.py" missing 2>&1); then
    echo "ok   the speech model for Q806 and Q807 is cached (engine/qa_speech.py)"
  else
    echo "NOTE the speech model is not cached -> python engine/qa_speech.py fetch (147.8 MB, MIT; narrated builds need it)"
  fi
fi

# the recorded instruments (engine/sampler.py): a note, since a score fetches only what it plays
if [ "$fail" -eq 0 ]; then
  if uv run --no-project --with-requirements "$here/engine/requirements.txt" python "$here/engine/sampler.py" missing >/dev/null 2>&1; then
    echo "ok   the 14 recorded instruments are cached (engine/sampler.py)"
  else
    echo "NOTE not every recorded instrument is cached -> python engine/sampler.py fetch <names> (all 14: 232.8 MB, CC0)"
  fi
fi

# Blender for 3D plates (engine/plate3d.py): a note, since only a 3D card needs it
if [ "$fail" -eq 0 ]; then
  if uv run --no-project --with-requirements "$here/engine/requirements.txt" python "$here/engine/plate3d.py" missing >/dev/null 2>&1; then
    echo "ok   Blender for 3D plates has been fetched (engine/plate3d.py)"
  else
    echo "NOTE Blender for 3D plates is not fetched -> python engine/plate3d.py fetch (324 MB, GPL-3.0; a 3D card needs it)"
  fi
fi

if [ "$fail" -eq 0 ]; then echo "SETUP: PASS"; else echo "SETUP: FIX"; fi
exit "$fail"
