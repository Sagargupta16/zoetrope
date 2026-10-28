# engine.py : helpers shared by scenes.py (device Python: PIL + numpy)
import math, os
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
import numpy as np

W, H, FPS, SS = 1920, 1080, 30, 1  # override before use: engine.W, engine.H = ...
FONT_BOLD = [
    "C:/Windows/Fonts/arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial Bold.ttf",
]
FONT_REG = [
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
]


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def lerp(a, b, k):
    return a + (b - a) * k


def prog(t, t0, dur):
    return clamp((t - t0) / dur)  # 0..1 progress of a move that starts at t0


def linear(k):
    return k


def ease_out_cubic(k):
    return 1 - (1 - k) ** 3


def ease_in_cubic(k):
    return k**3


def ease_in_out_cubic(k):
    return 4 * k**3 if k < 0.5 else 1 - (-2 * k + 2) ** 3 / 2


def ease_out_expo(k):
    return 1.0 if k >= 1 else 1 - 2 ** (-10 * k)


def ease_out_back(k, s=1.70158):
    return 1 + (s + 1) * (k - 1) ** 3 + s * (k - 1) ** 2


_fc = {}


def font(size, bold=True):
    key = (int(size), bold)
    if key not in _fc:
        for p in FONT_BOLD if bold else FONT_REG:
            if os.path.exists(p):
                try:
                    _fc[key] = ImageFont.truetype(p, int(size))
                    break
                except Exception:
                    pass
        else:
            raise FileNotFoundError(
                f"no font found in {FONT_BOLD if bold else FONT_REG}; put an installed font path first"
            )
    return _fc[key]


def hexrgb(h, a=255):
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), a)


def canvas(color="#000000"):
    return Image.new("RGBA", (W * SS, H * SS), hexrgb(color))


def gradient(c1, c2, vertical=True):
    a, b = np.array(hexrgb(c1)[:3], float), np.array(hexrgb(c2)[:3], float)
    n = H * SS if vertical else W * SS
    ramp = (a + (b - a) * np.linspace(0, 1, n)[:, None]).astype(np.uint8)
    arr = (
        np.repeat(ramp[:, None, :], W * SS, 1)
        if vertical
        else np.repeat(ramp[None, :, :], H * SS, 0)
    )
    return Image.fromarray(arr, "RGB").convert("RGBA")


def rrect(img, box, r, fill, alpha=1.0):
    """Rounded rectangle composited with opacity. box in output pixels (x0,y0,x1,y1)."""
    if alpha <= 0:
        return
    x0, y0, x1, y1 = [v * SS for v in box]
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    c = hexrgb(fill) if isinstance(fill, str) else fill
    ImageDraw.Draw(lay).rounded_rectangle(
        (x0, y0, x1, y1), r * SS, fill=c[:3] + (int(c[3] * alpha),)
    )
    img.alpha_composite(lay)


def shadow(img, box, r, blur=24, dy=12, alpha=0.35):
    x0, y0, x1, y1 = [v * SS for v in box]
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(lay).rounded_rectangle(
        (x0, y0 + dy * SS, x1, y1 + dy * SS), r * SS, fill=(0, 0, 0, int(255 * alpha))
    )
    img.alpha_composite(lay.filter(ImageFilter.GaussianBlur(blur * SS)))


def text(
    img,
    s,
    xy,
    size,
    fill="#FFFFFF",
    anchor="la",
    alpha=1.0,
    bold=True,
    scale=1.0,
    tracking=0,
):
    """Draw text at xy (output px). anchor: PIL anchors (la, mm, ra ...). scale > 1 grows around the anchor."""
    if alpha <= 0:
        return
    f = font(size * scale * SS, bold)
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    c = hexrgb(fill) if isinstance(fill, str) else fill
    d = ImageDraw.Draw(lay)
    if tracking:  # manual letter-spacing, left anchored
        x = xy[0] * SS
        for ch in s:
            d.text(
                (x, xy[1] * SS),
                ch,
                font=f,
                fill=c[:3] + (int(255 * alpha),),
                anchor="ls" if anchor[1] == "s" else "la",
            )
            x += d.textlength(ch, font=f) + tracking * SS
    else:
        d.text(
            (xy[0] * SS, xy[1] * SS),
            s,
            font=f,
            fill=c[:3] + (int(255 * alpha),),
            anchor=anchor,
        )
    img.alpha_composite(lay)


def text_w(s, size, bold=True):
    return font(size * SS, bold).getlength(s) / SS


def wrap(s, size, maxw, bold=True):
    out, line = [], ""
    for w in s.split():
        t = (line + " " + w).strip()
        if text_w(t, size, bold) <= maxw or not line:
            line = t
        else:
            out.append(line)
            line = w
    return out + ([line] if line else [])


def finish(img):
    """Downscale supersampled canvas and return RGB at W x H."""
    if SS > 1:
        img = img.resize((W, H), Image.LANCZOS)
    return img.convert("RGB")


def scene_at(t, schedule):
    """Return (name, local_t, k) for the scene active at time t; k = 0..1 through the scene."""
    for name, (a, b) in schedule.items():
        if a <= t < b:
            return name, t - a, (t - a) / (b - a)
    n = list(schedule)[-1]
    a, b = schedule[n]
    return n, b - a, 1.0


def crossfade(a_img, b_img, k):
    return Image.blend(a_img, b_img, clamp(k))
