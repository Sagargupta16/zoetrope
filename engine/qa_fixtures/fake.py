# fake.py : tiny fake scenes for the registry gates: texts with a box, timing, fades and colours, drawn on a flat
# background (or by a draw given). No render and no file; each fixture is a few lines. Lifted from lane Q's fx.py.
import importlib.util
import types
from pathlib import Path

from PIL import Image

W, H, FPS = 640, 360, 30  # short side 360, so the 1080 size rules scale by 3
R = W * 0.96  # the safe area's right edge


def _clamp(x):
    return min(1.0, max(0.0, x))


def alpha(x, t):
    """Alpha of text spec x at t: fade in over fade_in from t_in, fade out over fade_out to t_out, times peak."""
    if not x["t_in"] <= t < x["t_out"]:
        return 0.0
    fi, fo = x.get("fade_in", 0.0), x.get("fade_out", 0.0)
    a = 1.0 if fi <= 0 else _clamp((t - x["t_in"]) / fi)
    b = 1.0 if fo <= 0 else 1 - _clamp((t - (x["t_out"] - fo)) / fo)
    return a * b * x.get("peak", 1.0)


def make(texts, duration, bg=(16, 16, 16), draw=None, **extra):
    """A scenes-like object: DURATION, SCHEDULE, text_items(t), draw(t), plus extra attributes (ALLOW, NO_TEXT,
    HOLD_PROFILE, SCHEDULE ...). texts: dicts {s, box (a tuple or f(t)), t_in, t_out, fade_in, fade_out, peak, fg,
    px, bold, and optional texture, profile, reveal_end, no_fg}."""

    def text_items(t):
        out = []
        for x in texts:
            a = alpha(x, t)
            if a <= 0:
                continue
            box = x["box"](t) if callable(x["box"]) else x["box"]
            it = {
                "s": x["s"],
                "box": tuple(box),
                "alpha": a,
                "fg": x.get("fg", "#FFFFFF"),
                "px": x.get("px", 40),
                "bold": x.get("bold", True),
            }
            for k in ("texture", "profile", "reveal_end"):
                if k in x:
                    it[k] = x[k]
            if x.get("no_fg"):
                del it["fg"]
            out.append(it)
        return out

    def flat(t):
        return Image.new("RGB", (W, H), bg(t) if callable(bg) else bg)

    base = {
        "DURATION": duration,
        "SCHEDULE": {"all": (0.0, duration)},
        "text_items": text_items,
        "draw": draw or flat,
    }
    return types.SimpleNamespace(**{**base, **extra})


def scenes_file(name, w, h, fps=30, ss=1):
    """A scenes file of this folder imported as its own module (zt_case_<stem>, not put in sys.modules, so no case
    sees another's) after the engine is set to w x h at fps and ss, as qa.check sets it before `import scenes`."""
    import engine as E

    E.W, E.H, E.FPS, E.SS = w, h, fps, ss
    path = Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location(f"zt_case_{path.stem}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
