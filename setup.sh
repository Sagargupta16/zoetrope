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

if command -v ffmpeg >/dev/null 2>&1; then
  if ffmpeg -hide_banner -encoders 2>/dev/null | grep -q libx264; then
    echo "ok   ffmpeg $(ffmpeg -hide_banner -version | head -1 | cut -d' ' -f3) with libx264"
  else
    echo "FIX  ffmpeg has no libx264 (videos fall back to AV1, VP9 or GIF) -> winget install Gyan.FFmpeg"
    fail=1
  fi
else
  echo "FIX  ffmpeg missing -> winget install Gyan.FFmpeg, then open a new shell"
  fail=1
fi

if command -v ffprobe >/dev/null 2>&1; then
  echo "ok   ffprobe"
else
  echo "FIX  ffprobe missing -> it ships with ffmpeg; reinstall Gyan.FFmpeg"
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  # first run downloads the pinned wheels into the uv cache; later runs are instant
  if uv run --no-project --with-requirements "$here/engine/requirements.txt" python -c "import PIL, numpy; print('ok   pillow', PIL.__version__, '| numpy', numpy.__version__)"; then
    :
  else
    echo "FIX  pinned Pillow and numpy did not install -> check network once, then rerun setup.sh"
    fail=1
  fi
fi

found=""
for f in "C:/Windows/Fonts/arialbd.ttf" "/System/Library/Fonts/Supplemental/Arial Bold.ttf" "/Library/Fonts/Arial Bold.ttf"; do
  if [ -f "$f" ]; then found="$f"; break; fi
done
if [ -n "$found" ]; then
  echo "ok   default font $found"
else
  echo "FIX  none of engine.py's default fonts exist -> put an installed .ttf path first in FONT_BOLD and FONT_REG"
  fail=1
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

if [ "$fail" -eq 0 ]; then echo "SETUP: PASS"; else echo "SETUP: FIX"; fi
exit "$fail"
