# voice_samples.py : render the same three lines with every voice engine that is ready, so Sagar can listen and pick
# Usage: python voice_samples.py [out_folder]   (default narration_samples: <engine>/<voice>/narration.wav each)
import hashlib
import re
import sys
from pathlib import Path

import voice as V

# Lines from the 2026-10-28 sample scenarios: a short hook, two proper names, and a slower explainer sentence. A voice
# that speaks another language reads that language's lines (by Engine.lang).
LINES = {
    "en": [
        "You sat down to do one thing.",
        "Almost every national flag is a rectangle. Two are square: Switzerland and Vatican City.",
        "Shrink the gap, and the slope settles on one number. That number is the derivative.",
    ],
    "hi": [
        "आप एक काम करने बैठे थे।",
        "लगभग हर देश का झंडा आयत होता है। दो झंडे वर्गाकार हैं: स्विट्ज़रलैंड और वेटिकन सिटी।",
        "फ़ासला घटाइए, और ढलान एक संख्या पर टिक जाती है। वही संख्या अवकलज है।",
    ],
}

# Voices to audition per engine (references/voice.md: two or three per tone); None means every voice found. These
# are candidates for listening, not a choice: Sagar picks.
CANDIDATES = {"sapi": None, "kokoro-ts": None}


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
            lines = LINES.get((eng.lang(v) or "en")[:2])
            if not lines:
                print(f"SKIP {name} {v}: no sample lines in {eng.lang(v)}")
                continue
            try:  # one voice that fails must not cost the samples of the others
                narr = V.synthesize(lines, engine=name, voice=v, folder=folder)
            except (ValueError, RuntimeError, OSError) as e:
                failed.append((name, v))
                print(f"FAIL {name} {v}: {e}")
                continue
            timed = sum(ln["timing"] == "engine" for ln in narr["lines"])
            made.append(
                (name, v, folder / "narration.wav", narr["duration"], timed, len(lines))
            )
    note = f" ({', '.join(skipped)} not ready)" if skipped else ""
    print(f"\n{len(made)} samples, {len(failed)} failed{note}:")
    for name, v, wav, dur, timed, n in made:
        print(
            f"  {name:<9} {v:<26} {dur:6.2f} s  word times on {timed}/{n} lines  {wav}"
        )
    for name, v in failed:
        print(f"  {name:<9} {v:<26} FAILED (reason above)")
    print(f"  (sapi: {V.Sapi.use})")
    return 0 if made and not failed else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:2]))
