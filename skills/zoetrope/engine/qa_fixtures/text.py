# text.py : gates 2 to 4 and the beat grid on tiny fake scenes (qa.text_gates, qa.registry_rows, qa.grid_rows), no
# render: a crossfade overlap, 8 px out of the safe area, a 0.6 s hold on 6 words, contrast near 3:1, a ghost that
# never rests, a typewriter short at its reveal_end, a changeover gap, small key text, an empty registry, a cut off
# the BPM grid, and a clean card. Lifted from lane Q's p_text.py and p_grid.py (outputs/batchA/notes/q.md).
import math

import qa
from PIL import Image, ImageDraw

from qa_fixtures import case, clean, want
from qa_fixtures.fake import FPS, H, R, W, make


def gates(sc):
    return qa.text_gates(sc, W, H, FPS)


def crossfade(fx):
    """Two captions crossfading in one box (the overlap Q203 exists for)."""
    box = (120, 280, 520, 320)
    return gates(
        make(
            [
                {
                    "s": "First caption",
                    "box": box,
                    "t_in": 0,
                    "t_out": 2.0,
                    "fade_out": 0.4,
                },
                {
                    "s": "Second caption",
                    "box": box,
                    "t_in": 1.6,
                    "t_out": 4.0,
                    "fade_in": 0.4,
                },
            ],
            4.0,
        )
    )


def safe_area(fx):
    """A caption at rest 8 px past the 4 percent safe area's right edge."""
    return gates(
        make(
            [
                {
                    "s": "Call to action",
                    "box": (300, 160, R + 8, 200),
                    "t_in": 1.0,
                    "t_out": 3.0,
                }
            ],
            4.0,
        )
    )


def short_hold(fx):
    """Six words held 0.6 s: the floor is 0.5 + 0.3 x 6 = 2.3 s."""
    s = "one two three four five six"
    return gates(
        make([{"s": s, "box": (100, 150, 500, 190), "t_in": 1.0, "t_out": 1.6}], 3.0)
    )


def ghost(fx):
    """A caption whose fade stops at alpha 0.9, so it never reaches rest (Q403); a title holds the frame."""
    return gates(
        make(
            [
                {
                    "s": "Ghost caption",
                    "box": (100, 280, 500, 320),
                    "t_in": 1.0,
                    "t_out": 3.0,
                    "fade_in": 0.5,
                    "peak": 0.9,
                },
                {"s": "Title", "box": (100, 40, 300, 80), "t_in": 0, "t_out": 3.0},
            ],
            3.0,
        )
    )


TYPED = "Typed line here"


def typewriter(fx, reveal_end):
    """A 10 characters a second typewriter from 1.0 s (complete at 2.4 s) that declares reveal_end."""
    import engine as E

    f = E.font(32)
    box = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((100, 150), TYPED, font=f)

    def draw(t):
        im = Image.new("RGB", (W, H), (20, 20, 20))
        if t >= 1.0:
            n = min(len(TYPED), 1 + math.floor((t - 1.0) * 10 + 1e-6))
            ImageDraw.Draw(im).text((100, 150), TYPED[:n], font=f, fill=(240, 240, 240))
        return im

    spec = {
        "s": TYPED,
        "box": box,
        "t_in": 1.0,
        "t_out": 4.0,
        "fg": "#F0F0F0",
        "px": 32,
        "reveal_end": reveal_end,
    }
    return gates(make([spec], 4.0, draw=draw))


def changeover(fx):
    """A caption replaced in the same place after 5 empty frames (Q207: 3 frames to 0.5 s is a NOTE)."""
    return gates(
        make(
            [
                {"s": "Old line", "box": (100, 280, 400, 320), "t_in": 0, "t_out": 2.0},
                {
                    "s": "New line",
                    "box": (100, 280, 400, 320),
                    "t_in": 65 / 30,
                    "t_out": 4.0,
                },
            ],
            4.0,
        )
    )


def overlap_rest(fx):
    """Two labels at rest, one sliding into the other (largest overlap at 2.0 s)."""

    def moving(t):
        left = 320 - 60 * max(0.0, 1 - abs(t - 2.0))
        return (left, 100, left + 200, 140)

    return gates(
        make(
            [
                {
                    "s": "Left label",
                    "box": (100, 100, 300, 140),
                    "t_in": 0,
                    "t_out": 3.0,
                },
                {"s": "Right label", "box": moving, "t_in": 0, "t_out": 3.0},
            ],
            3.0,
        )
    )


def contrast_late(fx):
    """White body text whose background brightens late in its rest: only the last sampled frame fails."""

    def bg(t):
        g = round(200 * min(1.0, max(0.0, (t - 1.0) / 2.0)))
        return (g, g, g)

    spec = {
        "s": "White on a brightening sky",
        "box": (100, 150, 500, 180),
        "t_in": 1.0,
        "t_out": 3.0,
    }
    return gates(make([{**spec, "px": 12}], 3.0, bg=bg))


def contrast_3to1(fx):
    """Grey #5F5F5F body text on (16, 16, 16): 2.98:1 where small text needs 4.5:1."""
    spec = {
        "s": "Grey on charcoal",
        "box": (100, 150, 400, 170),
        "t_in": 0.5,
        "t_out": 2.5,
        "fg": "#5F5F5F",
        "px": 6,
    }
    return gates(make([spec], 3.0))


def small_text(fx):
    """Key text 8 px at a 360 px short side: 24 px at 1080, under the 36 px key size."""
    spec = {
        "s": "tiny footnote",
        "box": (100, 300, 220, 312),
        "t_in": 1.0,
        "t_out": 3.0,
        "px": 8,
    }
    return gates(make([spec], 3.0))


def empty_registry(fx):
    return gates(make([], 2.0))


def no_text_declared(fx):
    return gates(make([], 2.0, NO_TEXT=True))


def clean_card(fx):
    """A known-good card: a title held over two captions that change over in one place with 1 empty frame, the
    second fading in under the title. Every text gate looks at something and none may fire."""
    texts = [
        {"s": "Title line", "box": (120, 40, 520, 90), "t_in": 0, "t_out": 4.0},
        {"s": "First caption", "box": (120, 280, 520, 320), "t_in": 0, "t_out": 2.0},
        {
            "s": "Second caption",
            "box": (120, 280, 520, 320),
            "t_in": 61 / 30,
            "t_out": 4.0,
            "fade_in": 0.3,
        },
    ]
    return gates(make(texts, 4.0))


def off_grid(fx):
    """A cut at 2.1 s at 120 BPM: 3 frames off the nearest beat (Q901 NOTE)."""
    sc = make([], 4.0, SCHEDULE={"a": (0.0, 2.1), "b": (2.1, 4.0)})
    return qa.grid_rows(sc, 120, FPS)


def on_grid(fx):
    sc = make([], 4.0, SCHEDULE={"a": (0.0, 2.0), "b": (2.0, 4.0)})
    return qa.grid_rows(sc, 120, FPS)


CASES = [
    case(
        "text.crossfade",
        crossfade,
        [
            want(
                "Q203",
                "FIX",
                "First caption / Second caption",
                1.8,
                metric=15124,
                mtol=1000,
            )
        ],
    ),
    case(
        "text.safe_area",
        safe_area,
        [want("Q201", "FIX", "Call to action", 2.0, metric=8.0, mtol=0.5, n=1)],
    ),
    case(
        "text.short_hold",
        short_hold,
        [
            want(
                "Q401", "FIX", "one two three four five six", 1.3, metric=0.6, mtol=0.04
            )
        ],
    ),
    case(
        "text.ghost",
        ghost,
        [want("Q403", "FIX", "Ghost caption", 1.5, metric=0.9, mtol=0.01)],
    ),
    case(
        "text.typewriter_short",
        lambda fx: typewriter(fx, 1.8),
        [want("Q404", "FIX", TYPED, 1.8, metric=0.61, mtol=0.1)],
    ),
    case(
        "text.typewriter_done",
        lambda fx: typewriter(fx, 2.5),
        [want("Q404", "PASS")],
    ),
    case(
        "text.changeover",
        changeover,
        [want("Q207", "NOTE", "Old line -> New line", 2.067, metric=0.167, mtol=0.01)],
    ),
    case(
        "text.overlap_rest",
        overlap_rest,
        [want("Q202", "FIX", "Left label / Right label", 2.0, metric=1444, mtol=100)],
    ),
    case(
        "text.contrast_late",
        contrast_late,
        [
            want(
                "Q301", "FIX", "White on a brightening sky", 2.933, metric=1.8, mtol=0.3
            )
        ],
    ),
    case(
        "text.contrast_3to1",
        contrast_3to1,
        [
            # every sampled frame reads the same 2.98:1, so the worst is the first sampled rest frame, 16 / 30 s
            want("Q301", "FIX", "Grey on charcoal", 0.533, metric=2.98, mtol=0.05)
        ],
    ),
    case(
        "text.small",
        small_text,
        [want("Q402", "NOTE", "tiny footnote", 2.0, metric=24.0, mtol=0.5)],
    ),
    case("text.empty_registry", empty_registry, [want("Q200", "NOT CHECKED")]),
    case(
        "text.no_text_declared",
        no_text_declared,
        [want("Q200", "PASS", msg="NO_TEXT", empty_ok=True)],
    ),
    case(
        "text.clean_card",
        clean_card,
        [
            clean(),
            want("Q201", "PASS"),
            want("Q202", "PASS"),
            want("Q203", "PASS"),
            want("Q207", "PASS"),
            want("Q301", "PASS"),
            want("Q401", "PASS"),
            want("Q402", "PASS"),
            want("Q403", "PASS"),
        ],
    ),
    case(
        "text.off_grid",
        off_grid,
        [want("Q901", "NOTE", "b", 2.1, metric=3.0, mtol=0.1)],
    ),
    case("text.on_grid", on_grid, [want("Q901", "PASS")]),
]
