# proof.py : contact sheet of stills at scene midpoints and boundaries, plus a key-times sheet for review
import json
from PIL import Image, ImageDraw
import scenes
import engine as E


def spread(xs, k):  # k evenly spaced items, first and last kept
    return (
        xs
        if len(xs) <= k
        else [xs[round(i * (len(xs) - 1) / max(1, k - 1))] for i in range(k)]
    )


def proof_times(sch, eps=0.05, n=12):
    """Up to n stills across the whole video: every scene midpoint first, then scene boundaries."""
    ts = spread([(a + b) / 2 for a, b in sch.values()], n)
    ts += spread([t for a, b in sch.values() for t in (a + eps, b - eps)], n - len(ts))
    return sorted(set(round(t, 3) for t in ts))


def sheet(times, out, cols=3, tw=640, labels=None):
    th = int(tw * E.H / E.W)
    rows = -(-len(times) // cols)
    img = Image.new("RGB", (cols * tw, rows * (th + 24)), "#222")
    d = ImageDraw.Draw(img)
    for i, t in enumerate(times):
        im = scenes.draw(t).resize((tw, th))
        x, y = (i % cols) * tw, (i // cols) * (th + 24)
        img.paste(im, (x, y + 24))
        tag = f"t={t:.2f}s" + (f"  {labels[i]}" if labels else "")
        d.text((x + 6, y + 6), tag[:90], fill="#fff")
    img.save(out)
    return out


def contact_sheet(out, cols=3, tw=640):
    return sheet(proof_times(scenes.SCHEDULE), out, cols, tw)


def key_times(fps=None):
    """The moments a reviewer must see, as [(t, why)]: one frame each side of every cut, every caption at rest
    (from the text registry), and scenes.KEY_TIMES (punchlines, reveals)."""
    fps = fps or E.FPS
    keys = []
    for name, (a, b) in scenes.SCHEDULE.items():
        if a > 0:
            keys += [
                (round(a - 1 / fps, 3), f"before cut to {name}"),
                (round(a, 3), f"cut to {name}"),
            ]
    if hasattr(scenes, "text_items"):
        import qa

        for s, sp in qa.text_spans(qa.text_frames(scenes, fps)).items():
            a, b = max(sp, key=lambda x: x[1] - x[0])
            keys.append(
                (round(round((a + b) / 2 * fps) / fps, 3), f"at rest: {s[:40]}")
            )
    keys += [(round(t, 3), why) for t, why in getattr(scenes, "KEY_TIMES", [])]
    seen, out = set(), []
    for t, why in sorted(keys):
        if 0 <= t < scenes.DURATION and t not in seen:
            seen.add(t)
            out.append((t, why))
    return out


def key_sheet(
    out="proof_keys.png", times_json="review_times.json", cols=4, tw=480, cap=40
):
    """Sheet of the key times (at most cap, spread evenly; the JSON keeps them all) for the reviewer."""
    keys = key_times()
    with open(times_json, "w", encoding="utf-8") as f:
        json.dump([{"t": t, "why": why} for t, why in keys], f, indent=1)
    shown = spread(keys, cap)
    sheet([t for t, _ in shown], out, cols, tw, [why for _, why in shown])
    return out, len(keys), len(shown)
