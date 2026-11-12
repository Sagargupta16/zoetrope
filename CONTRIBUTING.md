# Contributing to zoetrope

The most welcome changes make videos look or sound better, or make a gate catch a real fault it missed.

## Setup

```bash
git clone https://github.com/Sagargupta16/zoetrope
cd zoetrope
bash skills/zoetrope/setup.sh
```

`setup.sh` checks uv, ffmpeg with libx264, ffprobe, the Python pin, the pinned Pillow and numpy and a usable font, and ends `SETUP: PASS`. To try your clone as a plugin, add it as a local marketplace (`/plugin marketplace add <path to your clone>`) and install `zoetrope@zoetrope`.

## What a pull request must pass

- `python scripts/check.py`: no en or em dashes, no secrets, no absolute home paths, LF line ends, valid skill frontmatter, working relative links, valid JSON, and the versions in `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` equal to the `CHANGELOG.md` head.
- `python skills/zoetrope/engine/cards.py check` after any change to a card, the router or a kit.
- The engine self test, from a fresh copy of the engine so the hidden `.python-version` and `qa_fixtures/` come along:

  ```bash
  mkdir -p /tmp/zoetrope-selftest
  cp -r skills/zoetrope/engine/. /tmp/zoetrope-selftest/
  cd /tmp/zoetrope-selftest
  uv run --no-project --with-requirements requirements.txt python qa.py selftest
  ```

  It must end `SELFTEST: PASS` with every code covered and 0 expected gaps.
- A change to drawing, sound or a gate: render the template at 1920x1080 and at 1080x1920 (`run_all.py proof`, then `run_all.py full`, then `qa.py check out.mp4 --scenes . --size WxH --fps 30 --bpm 120`) and paste the `PROOF`, `DELIVERED` and `QA` lines into the pull request.

## Conventions

- Plain English, LF line ends, no en or em dashes, no emoji.
- Original work only: never paste text, code or style recipes from another video tool, style guide or course.
- Every change gets a `CHANGELOG.md` line under a concrete version; a release bumps the version in both `.claude-plugin` files.
