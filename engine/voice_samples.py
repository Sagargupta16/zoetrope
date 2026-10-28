# voice_samples.py : render the same three lines with every voice engine that is ready, so Sagar can listen and pick
# Usage: python voice_samples.py [out_folder]   (default narration_samples: <engine>/<voice>/narration.wav each)
import hashlib
import re
import sys
from pathlib import Path

import voice as V

# Lines from the 2026-10-28 sample scenarios: a short hook, two proper names, and a slower explainer sentence.
LINES = [
    "You sat down to do one thing.",
    "Almost every national flag is a rectangle. Two are square: Switzerland and Vatican City.",
    "Shrink the gap, and the slope settles on one number. That number is the derivative.",
]

# Voices to audition per engine (references/voice.md: two or three per tone); None means every voice found. These
# are candidates for listening, not a choice: Sagar picks.
CANDIDATES = {
    "sapi": None,
    "kokoro": ["af_heart", "af_bella", "am_michael", "bf_emma"],
    "kokoro-ts": ["af_heart", "af_bella", "am_michael", "bf_emma"],
    "piper": None,
}


def main(out="narration_samples"):
    made, skipped, failed = [], [], []
    for name, eng in V.ENGINES.items():
        miss = eng.missing()
        if miss:
            skipped.append(name)
            print(f"SKIP {name}: {eng.status}")
            print(f"     missing: {'; '.join(miss)}")
            print(f"     needs:   {eng.needs}")
            print(f"     licence: {eng.licence}")
            continue
        have, used = eng.voices(), set()
        for v in CANDIDATES.get(name) or have:
            if v not in have:
                print(f"SKIP {name} {v}: no voice file for it in {V.VOICE_DIR}")
                continue
            slug = re.sub(r"[^0-9a-z]+", "-", v.lower()).strip("-")
            if (
                slug in used
            ):  # "Nova 1" and "nova-1" would share a folder and overwrite each other
                slug = f"{slug}-{hashlib.sha256(v.encode()).hexdigest()[:6]}"
            used.add(slug)
            folder = Path(out, name, slug)
            try:  # one voice that fails must not cost the samples of the others
                narr = V.synthesize(LINES, engine=name, voice=v, folder=folder)
            except (ValueError, RuntimeError, OSError) as e:
                failed.append((name, v))
                print(f"FAIL {name} {v}: {e}")
                continue
            timed = sum(ln["timing"] == "engine" for ln in narr["lines"])
            made.append((name, v, folder / "narration.wav", narr["duration"], timed))
    note = f" ({', '.join(skipped)} not ready)" if skipped else ""
    print(f"\n{len(made)} samples, {len(failed)} failed{note}:")
    for name, v, wav, dur, timed in made:
        print(
            f"  {name:<9} {v:<26} {dur:6.2f} s  word times on {timed}/{len(LINES)} lines  {wav}"
        )
    for name, v in failed:
        print(f"  {name:<9} {v:<26} FAILED (reason above)")
    print(f"  (sapi: {V.Sapi.use})")
    return 0 if made and not failed else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))
