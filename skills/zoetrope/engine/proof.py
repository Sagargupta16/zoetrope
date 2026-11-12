# proof.py : the proof sheets. proof.png: stills over every scene. proof_keys.png: every moment a reviewer must see,
# most urgent first and numbered. proof_strips.png: frames f-2..f+2 around each one-frame event. proof_gantt.png: the
# film as lanes on one time axis. `python proof.py keys` redraws the last three from review_times.json.
import re
import sys
from pathlib import Path

import contract as C
from PIL import Image, ImageDraw

import engine as E

# What the key sheet shows first and its cap drops last (a FIX finding is never dropped): contract.KINDS in its
# order, with a finding split by its status. One colour per rank for the cell borders, strip captions and Gantt ticks.
RANKS = (
    "FIX",
    "NOT CHECKED",
    "changed",
    "pop",
    "NOTE",
    "cut",
    "window",
    "key",
    "audio",
    "rest",
)
COLOUR = {
    "FIX": "#ff5a5a",
    "NOT CHECKED": "#c39bff",
    "changed": "#ff9f1a",
    "pop": "#ff5aff",
    "NOTE": "#ffd84d",
    "cut": "#ffffff",
    "window": "#6b9fff",
    "key": "#7dff7d",
    "audio": "#4dd2ff",
    "rest": "#a0a0a0",
}
STRIPS = "proof_strips.png"
STRIP_CAP = 24  # most strips drawn, in rank order; review_times.json keeps the rest
CACHE_W = 640  # frames are kept this wide: the widest tile any sheet draws
PAGE_H = 2000  # tallest page of a sheet: a taller image is shrunk when it is read, and its captions blur
PANEL_ROWS = (
    8  # most timeless FIX and NOT CHECKED rows listed above the cells of proof_keys.png
)
_drawn, _texts = (
    {},
    {},
)  # per run: (fps, frame index) -> still, fps -> (registry frames, spans, why none)


def _scenes():
    import scenes  # late: the caller sets E.W, E.H, E.FPS and E.SS first (run_all.py, or main below)

    return scenes


def spread(xs, k):  # k evenly spaced items, first and last kept
    return (
        xs
        if len(xs) <= k
        else [xs[round(i * (len(xs) - 1) / max(1, k - 1))] for i in range(k)]
    )


def frame_count(fps=None):
    """Frames in the film, as render.py writes them (contract.frame_of: round() puts half a frame the other way)."""
    return C.frame_of(_scenes().DURATION, fps or E.FPS)


def still(t, tw, th=None, fps=None):
    """The frame the film shows at t (the nearest frame) at tw x th. draw(t) runs once per frame per run, whichever
    sheet asks first, so overlapping sheets cost no extra draws."""
    fps = fps or E.FPS
    i = min(max(C.frame_of(t, fps), 0), frame_count(fps) - 1)
    im = _drawn.get((fps, i))
    if im is None or im.width < tw:
        im = _scenes().draw(i / fps)
        w = max(tw, CACHE_W)
        if im.width > w:
            im = im.resize((w, round(w * im.height / im.width)))
        _drawn[(fps, i)] = im
    th = th or round(tw * im.height / im.width)
    return im if im.size == (tw, th) else im.resize((tw, th))


def proof_times(sch, eps=0.05, n=12, fps=None):
    """Up to n stills across the whole video: every scene midpoint first, then the first and last frame of every
    transition window (scenes.WINDOWS), then the scene boundaries more than 2 frames from those edges. Each sits on
    the frame grid, so a still is a frame the film really shows."""
    fps = fps or E.FPS
    ts = spread([(a + b) / 2 for a, b in sch.values()], n)
    edges = [t for t0, t1, _, _ in windows() for t in (t0, t1 - 1 / fps)]
    ts += spread(edges, n - len(ts))
    bounds = [t for a, b in sch.values() for t in (a + eps, b - eps)]
    bounds = [t for t in bounds if all(abs(t - e) * fps > 2 for e in edges)]
    ts += spread(bounds, n - len(ts))
    return sorted({round(C.snap(t, fps), 3) for t in ts})


def sheet(times, out, cols=3, tw=640, labels=None):
    th = int(tw * E.H / E.W)
    rows = -(-len(times) // cols)
    img = Image.new("RGB", (cols * tw, rows * (th + 24)), "#222")
    d = ImageDraw.Draw(img)
    for i, t in enumerate(times):
        x, y = (i % cols) * tw, (i // cols) * (th + 24)
        img.paste(still(t, tw, th), (x, y + 24))
        tag = f"t={t:.2f}s" + (f"  {labels[i]}" if labels else "")
        d.text((x + 6, y + 6), tag[:90], fill="#fff")
    img.save(out)
    return out


def contact_sheet(out, cols=3, tw=640):
    return sheet(proof_times(_scenes().SCHEDULE), out, cols, tw)


# ---- the moments a reviewer must see ----


def windows():
    """scenes.WINDOWS as [(t0, t1, out, in)], the transition overlaps engine.compile_schedule writes ([] when every
    change is a cut). t1 is the outgoing scene's end, so the last frame inside is t1 minus one frame."""
    return [tuple(w[:4]) for w in getattr(_scenes(), "WINDOWS", None) or []]


def scene_label(t):
    """The scene shown at t, or 'out>in' inside a transition window."""
    for t0, t1, a, b in windows():
        if t0 <= t < t1:
            return f"{a}>{b}"
    return E.scene_at(t, _scenes().SCHEDULE)[0]


def _registry(fps):
    """(frames, at-rest spans, why there are none) from the text registry, once per run: the key times and the Gantt
    both read it. A registry older than 2.2 (items with no "s", box or alpha) reads as none, as qa_scan._holds does,
    so it cannot stop the proof; qa.py's Q200 row says what it means for the text gates."""
    sc = _scenes()
    if fps not in _texts:
        got = [], {}, "no text registry (text_items)"
        if hasattr(sc, "text_items"):
            import qa

            try:
                frames = qa.text_frames(sc, fps)
                got = frames, qa.text_spans(frames), ""
            except (KeyError, TypeError, AttributeError, IndexError) as e:
                got = [], {}, f"text registry unreadable ({type(e).__name__} {e})"
        _texts[fps] = got
    return _texts[fps]


def text_frames(fps=None):
    """qa.text_frames once per run; [] without a readable text registry."""
    return _registry(fps or E.FPS)[0]


def key_entries(fps=None):
    """Every moment a reviewer must see, one entry {t, why, kind} per reason: both sides of every cut (scene starts
    and scenes.CUTS), both edges of every transition window (a crossfade starts before its cut, and the scene start
    it rides on is not a cut), every caption at rest (the middle of its longest hold, from the text registry) and
    scenes.KEY_TIMES. Times sit on the frame grid."""
    sc = _scenes()
    fps = fps or E.FPS
    out = []

    def add(t, why, kind):
        if 0 <= t < sc.DURATION:
            out.append({"t": round(C.snap(t, fps), 3), "why": why, "kind": kind})

    wins = windows()
    rides = {C.frame_of(w[0], fps) for w in wins}  # scene starts that open a window
    cuts = {}
    for name, (a, _) in sc.SCHEDULE.items():
        if a > 0 and C.frame_of(a, fps) not in rides:
            cuts.setdefault(C.frame_of(a, fps), name)
    # scenes.CUTS: a list from engine.compile_schedule, a set of plain times in older builds. A cut inside a
    # window leads into the window's incoming scene (scene_at there still answers the outgoing one).
    for c in getattr(sc, "CUTS", None) or []:
        t = float(c[0] if isinstance(c, (tuple, list)) else c)
        into = [b for t0, t1, _, b in wins if t0 <= t < t1]
        if 0 < t < sc.DURATION:
            cuts.setdefault(
                C.frame_of(t, fps), into[0] if into else E.scene_at(t, sc.SCHEDULE)[0]
            )
    for f, name in sorted(cuts.items()):
        add((f - 1) / fps, f"before cut to {name}", "cut")
        add(f / fps, f"cut to {name}", "cut")
    for t0, t1, a, b in wins:
        add(t0, f"window start {a}>{b}", "window")
        add(t1 - 1 / fps, f"window end {a}>{b}", "window")
    for s, sp in _registry(fps)[1].items():
        a, b = max(sp, key=lambda x: x[1] - x[0])
        add(C.mid_frame(a, b, fps) / fps, f"at rest: {s[:40]}", "rest")
    for k in getattr(sc, "KEY_TIMES", None) or []:
        t, why = (k, "key time") if isinstance(k, (int, float)) else k
        add(t, why, "key")
    return out


def key_times(fps=None):
    """[(t, why)] sorted, one per frame, every reason at that frame joined with '; ' (the 2.1.0 shape; key_entries
    keeps the kinds)."""
    by = {}
    for e in key_entries(fps):
        by.setdefault(e["t"], []).append(e["why"])
    return [(t, "; ".join(dict.fromkeys(w))) for t, w in sorted(by.items())]


def finding_entries(rows):
    """A 'finding' entry for every FIX, NOT CHECKED and NOTE row that names a moment: its worst_t, else the middle
    of its longest span, else t0, with the row's status (the rows that name none go on the panel, see timeless).
    The reason reads '<code> <status> <item>: <meaning>'."""
    out = []
    for r in rows or []:
        t = r.worst_t
        t = C.worst_of(r.spans) if t is None else t
        t = r.t0 if t is None else t
        if r.status in (C.FIX, C.NOT_CHECKED, C.NOTE) and t is not None:
            meaning = C.CODES[r.code][3] if r.code in C.CODES else r.msg
            why = f"{r.code} {r.status} " + (
                f"{r.item}: {meaning}" if r.item else r.msg
            )
            out.append(
                {
                    "t": t,
                    "why": why,
                    "kind": "finding",
                    "code": r.code,
                    "status": r.status,
                }
            )
    return out


def _rank(e):
    """Index in RANKS of an entry. A time whose status (the most severe at that time) is FIX or NOT CHECKED ranks
    so, whatever its kinds: a FIX finding, or a change qa.py diff found undeclared. Otherwise its most urgent kind
    (contract.add_review_times keeps them all in `kinds`), a finding counting as NOTE. A finding with no status
    falls back on its code's status on failure in contract.CODES."""
    kinds = e.get("kinds") or [e.get("kind", "key")]
    st = e.get("status")
    if st is None and "finding" in kinds:
        st = C.CODES.get(e.get("code"), ("", 0, C.NOTE))[2]
    if st in (C.FIX, C.NOT_CHECKED):
        return RANKS.index(st)
    return min(
        RANKS.index("NOTE" if k == "finding" else k if k in RANKS else "key")
        for k in kinds
    )


def cells_of(entries, known, fps=None):
    """Review entries grouped by frame, most urgent first: one cell per frame with its reasons, its rank (its most
    urgent entry), whether any entry asks for a strip, and the entry times (to write n back). Reasons sort by
    `known` (the reasons proof.py wrote, with their ranks); another lane's reason takes its entry's rank."""
    fps = fps or E.FPS
    last = frame_count(fps) - 1
    by = {}
    for e in entries:
        f = min(max(C.frame_of(e["t"], fps), 0), last)
        c = by.setdefault(
            f, {"f": f, "t": f / fps, "ts": [], "why": {}, "rank": len(RANKS)}
        )
        base = _rank(e)
        for seg in filter(None, e["why"].split("; ")):
            r = known.get(seg, base)
            c["why"][seg] = min(r, c["why"].get(seg, r))
        c["rank"] = min(c["rank"], base)
        if e.get("strip"):
            c["rank"] = min(c["rank"], RANKS.index("pop"))
            c["strip"] = True
        c["ts"].append(e["t"])
    for c in by.values():
        c["reasons"] = sorted(c["why"], key=c["why"].get)
    return sorted(by.values(), key=lambda c: (c["rank"], c["f"]))


def pick(cells, cap):
    """The cells a sheet shows, in rank order: every FIX cell, then rank by rank until cap; a rank that only partly
    fits is thinned evenly. The cap so drops captions at rest first and never a FIX frame."""
    fix = RANKS.index("FIX")
    shown = [c for c in cells if c["rank"] == fix]
    room = cap - len(shown)
    for r in range(fix + 1, len(RANKS)):
        grp = [c for c in cells if c["rank"] == r]
        take = grp if len(grp) <= room else spread(grp, max(room, 0))
        shown += take
        room -= len(take)
    return shown


# ---- drawing ----


def _n(k, word):
    return f"{k} {word}{'s' * (k != 1)}"


def _fit(s, f, w):
    """s cut to fit w px in font f, ending '..' when cut."""
    if f.getlength(s) <= w:
        return s
    lo, hi = 0, len(s)  # the longest prefix that fits with '..', by halving
    while lo < hi:
        m = (lo + hi + 1) // 2
        lo, hi = (m, hi) if f.getlength(s[:m] + "..") <= w else (lo, m - 1)
    return s[:lo] + ".."


def _wrap(s, f, w, k=2):
    """s on at most k lines of w px in font f; the last line ends '..' when the rest does not fit."""
    lines = [""]
    for word in s.split():
        t = f"{lines[-1]} {word}".strip()
        if f.getlength(t) <= w or not lines[-1] or len(lines) == k:
            lines[-1] = t
        else:
            lines.append(word)
    return [_fit(x, f, w) for x in lines]


def _caption(c):
    n = c.get("n")
    return f"#{n if n else '-'} | {scene_label(c['t'])} | {c['t']:.2f} s f{c['f']} | {RANKS[c['rank']]}"


def _tile(long):
    """(w, h) of a frame tile whose long side is `long` px, in the film's aspect (a 9:16 tile stands up)."""
    if E.W >= E.H:
        return long, round(long * E.H / E.W)
    return round(long * E.W / E.H), long


def _pages(out, n):
    """Names of n pages of one sheet: out, then out_2, out_3 ... Pages left from a longer run are removed, so every
    page on disk belongs to this run."""
    p = Path(out)
    names = [p] + [p.with_name(f"{p.stem}_{k}{p.suffix}") for k in range(2, n + 1)]
    for old in p.parent.glob(f"{p.stem}_*{p.suffix}"):
        if re.fullmatch(rf"{re.escape(p.stem)}_\d+", old.stem) and old not in names:
            old.unlink()
    return names


def _head(d, text, w, f):
    """Two header lines: what the page is, then the colour of every rank."""
    d.text((8, 6), _fit(text, f, w - 16), font=f, fill="#e8e8e8")
    x = 8
    for r in RANKS:
        d.text((x, 28), r, font=f, fill=COLOUR[r])
        x += f.getlength(r) + 14


def timeless(rows):
    """The FIX and NOT CHECKED rows that name no moment (no worst_t, spans or t0): a lint FIX or a gate that could
    not run has no frame to show, so it gets no cell; the panel on proof_keys.png lists them instead."""
    return [
        r
        for r in rows or []
        if r.status in (C.FIX, C.NOT_CHECKED)
        and r.worst_t is None
        and not r.spans
        and r.t0 is None
    ]


def _panel(d, rows, source, y, w, f):
    """The timeless FIX and NOT CHECKED rows, one line each in its status colour, at y; returns the height used."""
    if not rows:
        return 0
    head = f"No moment, so no cell: {_n(len(rows), 'FIX or NOT CHECKED row')} from {source}"
    d.text((8, y), _fit(head, f, w - 16), font=f, fill="#e8e8e8")
    for j, r in enumerate(rows[:PANEL_ROWS], 1):
        col = COLOUR["FIX" if r.status == C.FIX else "NOT CHECKED"]
        s = f"{r.status} {r.code} {r.msg}" + (f" -> {r.fix}" if r.fix else "")
        d.text((8, y + 18 * j), _fit(s, f, w - 16), font=f, fill=col)
    if len(rows) > PANEL_ROWS:
        more = f"and {len(rows) - PANEL_ROWS} more in {source}"
        d.text((8, y + 18 * (PANEL_ROWS + 1)), more, font=f, fill="#e8e8e8")
    return 18 * (min(len(rows), PANEL_ROWS) + 1 + (len(rows) > PANEL_ROWS)) + 10


def _key_png(shown, out, cols, tw, total, cap, panel=(), source=""):
    """proof_keys.png: a cell per shown moment (frame, number, scene, time, rank, every reason) under a legend, and
    on page 1 the panel of rows that name no moment. Cells that do not fit one page of PAGE_H px go on
    proof_keys_2.png and on: a taller image is shrunk when it is read, and its captions blur. tw is a tile's long
    side; a 9:16 film gets standing tiles in more columns."""
    w, h = _tile(tw)
    cols = cols if E.W >= E.H else max(1, cols * tw // w)
    f1, f2 = E.font(17, True), E.font(15, False)
    text = [
        (_wrap(_caption(c), f1, w - 16), _wrap("; ".join(c["reasons"]), f2, w - 16, 3))
        for c in shown
    ]
    hh = 12 + 18 * max((len(a) + len(b) for a, b in text), default=2)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    ph = _panel(
        probe, panel, source, 0, cols * w, f2
    )  # the panel's height, on page 1 only
    chunks, i = [], 0
    while i < len(shown) or not chunks:
        k = cols * max(1, (PAGE_H - 52 - (0 if chunks else ph)) // (hh + h))
        chunks.append(range(i, min(i + k, len(shown))))
        i += k
    names = _pages(out, len(chunks))
    for p, (name, idx) in enumerate(zip(names, chunks), 1):
        top = 52 + (ph if p == 1 else 0)
        rows = max(1, -(-len(idx) // cols))
        img = Image.new("RGB", (cols * w, top + rows * (hh + h)), "#1c1c1c")
        d = ImageDraw.Draw(img)
        what = f"cells {idx.start + 1} to {idx.stop}" if shown else "no cells"
        _head(
            d,
            f"{name.name} (page {p} of {len(names)}): {what} of {len(shown)} shown, {total} moments, most urgent "
            f"first; the cap {cap} drops captions at rest first and never a FIX. #n is n in review_times.json and "
            "the tick in proof_gantt.png.",
            img.width,
            f2,
        )
        if p == 1:
            _panel(d, panel, source, 52, img.width, f2)
        for k, i in enumerate(idx):
            c, (l1, l2) = shown[i], text[i]
            x, y = (k % cols) * w, top + (k // cols) * (hh + h)
            col = COLOUR[RANKS[c["rank"]]]
            img.paste(still(c["t"], w, h), (x, y + hh))
            d.rectangle((x + 1, y + 1, x + w - 2, y + hh + h - 2), outline=col, width=3)
            for j, ln in enumerate(l1):
                d.text((x + 8, y + 6 + j * 18), ln, font=f1, fill=col)
            for j, ln in enumerate(l2):
                d.text((x + 8, y + 8 + (len(l1) + j) * 18), ln, font=f2, fill="#e8e8e8")
        img.save(name)
    return names


def _strip_png(cells, out, fps):
    """proof_strips.png: frames f-2 .. f+2 of every cell that asks for a strip (a one-frame pop is invisible on one
    still), the event frame boxed in its colour, paged like the key sheet. Returns the pages written."""
    sel = pick([c for c in cells if c.get("strip")], STRIP_CAP)
    if not sel:
        _pages(out, 1)
        Path(out).unlink(missing_ok=True)  # a stale sheet must not outlive its entries
        return []
    w, h = _tile(380)
    gap, hh, top = 4, 50, 52
    f1, f2 = E.font(17, True), E.font(15, False)
    last = frame_count(fps) - 1
    per = max(1, (PAGE_H - top) // (hh + h + gap))
    names = _pages(out, -(-len(sel) // per))
    for p, name in enumerate(names, 1):
        chunk = sel[(p - 1) * per : p * per]
        img = Image.new(
            "RGB", (5 * w + 4 * gap, top + len(chunk) * (hh + h + gap)), "#1c1c1c"
        )
        d = ImageDraw.Draw(img)
        _head(
            d,
            f"{name.name} ({p} of {len(names)}): frames f-2 to f+2 from draw(t), the event boxed. A pop that is not "
            "here came from the render or encode: see qa.py look.",
            img.width,
            f2,
        )
        for r, c in enumerate(chunk):
            y = top + r * (hh + h + gap)
            col = COLOUR[RANKS[c["rank"]]]
            d.text((8, y + 6), _fit(_caption(c), f1, img.width - 16), font=f1, fill=col)
            d.text(
                (8, y + 27),
                _fit("; ".join(c["reasons"]), f2, img.width - 16),
                font=f2,
                fill="#e8e8e8",
            )
            for j, k in enumerate(range(c["f"] - 2, c["f"] + 3)):
                x = j * (w + gap)
                if 0 <= k <= last:
                    img.paste(still(k / fps, w, h), (x, y + hh))
                    tag = f"f{k} {k / fps:.3f} s" + (" event" if k == c["f"] else "")
                else:
                    tag = f"f{k}: outside the film"
                d.rectangle(
                    (x, y + hh, x + f2.getlength(tag) + 10, y + hh + 20), fill="#000000"
                )
                d.text(
                    (x + 5, y + hh + 2),
                    tag,
                    font=f2,
                    fill=col if k == c["f"] else "#ffffff",
                )
                if k == c["f"]:
                    d.rectangle(
                        (x, y + hh, x + w - 1, y + hh + h - 1), outline=col, width=4
                    )
        img.save(name)
    return names


def _text_rows(fps):
    """[(row, string, visible runs, rest runs)] from the registry: rest runs from qa.text_spans, visible runs where
    alpha is over 0.05, so a fade is visible but not at rest. Strings share a row when they never overlap."""
    frames, rest, _ = _registry(fps)
    seen = {}
    for t, items in frames:
        for it in items:
            if it.get("alpha", 1) > 0.05 and not it.get("texture"):
                seen.setdefault(it["s"], []).append(t)
    out, ends = [], []
    for s, ts in sorted(seen.items(), key=lambda kv: kv[1][0]):
        vis = [(a, b + 1 / fps) for a, b in C.merge_spans(ts, fps, 1)]
        r = next((i for i, e in enumerate(ends) if e <= vis[0][0]), len(ends))
        if r == len(ends):
            ends.append(0.0)
        ends[r] = vis[-1][1]
        out.append((min(r, 11), s, vis, rest.get(s, [])))
    return out


def _stagger(d, marks, y0, rows, f, xmax):
    """Tick labels (x, text, colour), in the order given (most urgent first, so a crowded spot drops the least
    urgent label), each in the first of `rows` sub-rows where it clears every label already there. A label that
    would pass xmax ends at its tick instead. Returns the placed labels as (left, right, row, text)."""
    placed = []
    for x, s, col in marks:
        w = f.getlength(s)
        a = x + 3 if x + 3 + w <= xmax else x - 3 - w
        free = (
            i
            for i in range(rows)
            if all(a + w + 4 <= p or a >= q + 4 for p, q, r, _ in placed if r == i)
        )
        r = next(free, None)
        if r is not None:
            d.text((a, y0 + r * 17), s, font=f, fill=col)
            placed.append((a, a + w, r, s))
    return placed


def gantt(shown=(), out=C.GANTT, width=1920, fps=None):
    """proof_gantt.png, at most 2000 px wide: scenes (SCHEDULE), transition windows, texts (solid at rest, dim
    while fading, from the registry alpha), cues and the numbered key cells on one time axis in seconds, with bar
    lines on the BPM grid. The reviewer sees where qa.py and the sheets look."""
    sc = _scenes()
    fps = fps or E.FPS
    dur, width = sc.DURATION, min(width, 2000)
    f, fb = E.font(14, False), E.font(14, True)
    left, pw = 104, width - 104 - 12

    def X(t):
        return left + max(0.0, min(t, dur)) / dur * pw

    wins, texts = windows(), _text_rows(fps)
    try:
        cues = C.cues(sc)
    except (TypeError, ValueError, KeyError, IndexError):
        cues = (
            None  # CUES in a pre-registry shape: some 2.1.0 builds keep a dict of lists
        )
    lanes = {
        "time (s)": 26,
        "scenes": 42,
        "windows": 24,
        "texts": max(1, 1 + max((r for r, *_ in texts), default=0)) * 18 + 6,
        "cues": 44,
        "key #n": 60,
    }
    ys, y = {}, 26
    for name, h in lanes.items():
        ys[name] = (y, y + h)
        y += h
    img = Image.new("RGB", (width, y + 6), "#161616")
    d = ImageDraw.Draw(img)
    bpm = getattr(sc, "BPM", None)
    bar = 4 * 60 / bpm if bpm else None
    d.text(
        (8, 5),
        f"proof_gantt.png: {dur:g} s at {fps:g} fps, "
        + (f"{bpm:g} BPM (bar lines every {bar:g} s)" if bpm else "no BPM")
        + f" | {_n(len(sc.SCHEDULE), 'scene')}, {_n(len(wins), 'window')}, {_n(len(texts), 'text')}, "
        + (_n(len(cues), "cue") if cues is not None else "CUES unreadable")
        + f", {_n(len(shown), 'key cell')}",
        font=f,
        fill="#e8e8e8",
    )
    for name, (y0, y1) in ys.items():
        d.line((0, y0, width, y0), fill="#383838")
        d.text((8, (y0 + y1) / 2), name, font=fb, fill="#b8b8b8", anchor="lm")
    y_axis, y_end = ys["time (s)"], img.height - 6
    if bar:  # bar lines under everything, beat ticks on the axis
        for k in range(int(dur / bar + 1e-6) + 1):
            d.line((X(k * bar), y_axis[1], X(k * bar), y_end), fill="#2c2c2c", width=2)
        for k in range(int(dur * bpm / 60 + 1e-6) + 1):
            d.line(
                (X(k * 60 / bpm), y_axis[1] - 5, X(k * 60 / bpm), y_axis[1]),
                fill="#707070",
            )
    step = next(
        (s for s in (0.25, 0.5, 1, 2, 5, 10, 15, 30, 60) if s / dur * pw >= 56), 120
    )
    for k in range(int(dur / step + 1e-6) + 1):
        x = X(k * step)
        d.line((x, y_axis[0] + 18, x, y_axis[1]), fill="#d0d0d0")
        d.text((x, y_axis[0] + 3), f"{k * step:g}", font=f, fill="#d0d0d0", anchor="ma")
    y0, _ = ys["scenes"]
    for i, (name, (a, b)) in enumerate(sc.SCHEDULE.items()):
        top = y0 + 4 + (i % 2) * 18  # alternate rows, so overlapping scenes both show
        d.rectangle((X(a), top, X(b) - 1, top + 15), fill=("#35577a", "#66457f")[i % 2])
        d.text(
            (X(a) + 4, top + 8),
            _fit(name, f, X(b) - X(a) - 8),
            font=f,
            fill="#ffffff",
            anchor="lm",
        )
    y0, y1 = ys["windows"]
    for t0, t1, a, b in wins:
        d.rectangle(
            (X(t0), y0 + 4, max(X(t1) - 1, X(t0) + 2), y1 - 4), fill=COLOUR["window"]
        )
        s = f"{a}>{b}"  # after the bar, or before it where it would pass the right edge
        x = X(t1) + 4 if X(t1) + 4 + f.getlength(s) <= width - 4 else X(t0) - 4
        d.text(
            (x, (y0 + y1) / 2),
            s,
            font=f,
            fill=COLOUR["window"],
            anchor="lm" if x > X(t0) else "rm",
        )
    if not wins:
        d.text(
            (left + 4, (y0 + y1) / 2),
            "none: every change is a cut",
            font=f,
            fill="#808080",
            anchor="lm",
        )
    y0, y1 = ys["texts"]
    for r, s, vis, rest in texts:
        top = y0 + 4 + r * 18
        for a, b in vis:
            d.rectangle((X(a), top, max(X(b) - 1, X(a) + 1), top + 14), fill="#4a4a4a")
        for a, b in rest:
            d.rectangle((X(a), top, max(X(b) - 1, X(a) + 1), top + 14), fill="#d8d8d8")
        a0 = rest[0][0] if rest else vis[0][0]
        d.text(
            (X(a0) + 3, top + 7),
            _fit(s, f, X(vis[-1][1]) - X(a0) - 6),
            font=f,
            fill="#101010",
            anchor="lm",
        )
    if not texts:
        why = _registry(fps)[2] or "the registry reports no text"
        d.text((left + 4, (y0 + y1) / 2), why, font=f, fill="#808080", anchor="lm")
    y0, y1 = ys["cues"]
    kinds = {"both": "#ffffff", "audio": "#4dd2ff", "picture": "#ff9f1a"}
    for c in cues or []:
        d.line(
            (X(c["t"]), y0 + 2, X(c["t"]), y1 - 2),
            fill=kinds.get(c["kind"], "#ffffff"),
            width=2,
        )
    cue_marks = [
        (X(c["t"]), c["label"][:18], kinds.get(c["kind"], "#ffffff"))
        for c in sorted(cues or [], key=lambda c: c["t"])
    ]
    _stagger(d, cue_marks, y0 + 4, 2, f, width - 4)
    if cues is None:
        d.text(
            (left + 4, (y0 + y1) / 2),
            "CUES is not a list of (t, label, kind)",
            font=f,
            fill=COLOUR["changed"],
            anchor="lm",
        )
    elif not cues:
        d.text(
            (left + 4, (y0 + y1) / 2), "no CUES", font=f, fill="#808080", anchor="lm"
        )
    y0, y1 = ys["key #n"]
    for c in shown:
        d.line(
            (X(c["t"]), y0 + 2, X(c["t"]), y1 - 2),
            fill=COLOUR[RANKS[c["rank"]]],
            width=2,
        )
    # shown is in rank order, so where labels crowd the least urgent one is dropped (its tick stays)
    key_marks = [(X(c["t"]), f"#{c['n']}", COLOUR[RANKS[c["rank"]]]) for c in shown]
    _stagger(d, key_marks, y0 + 4, 3, fb, width - 4)
    img.save(out)
    return img.size


def draw_sheets(out, times_json, cols, tw, cap, mine, panel=(), source=""):
    """The three review sheets from review_times.json, with the rows in `panel` (timeless FIX and NOT CHECKED, from
    `source`) listed on page 1. Each shown cell's number n is written back (null when the cap left a time off the
    sheet), so review/audio.png can draw matching ticks."""
    fps = E.FPS
    known = {e["why"]: _rank(e) for e in mine}
    cells = cells_of(C.read_review_times(times_json), known, fps)
    shown = pick(cells, cap)
    for n, c in enumerate(shown, 1):
        c["n"] = n
    C.add_review_times(
        [{"t": t, "n": c.get("n")} for c in cells for t in c["ts"]], times_json
    )
    pages = _key_png(shown, out, cols, tw, len(cells), cap, panel, source)
    if panel:
        print(f"listed {len(panel)} rows with no moment on {Path(out).name}")
    strips = _strip_png(cells, STRIPS, fps)
    w, h = gantt(shown, C.GANTT, fps=fps)
    n = sum(1 for c in cells if c.get("strip"))
    print(
        f"wrote {', '.join(p.name for p in pages)}, {C.GANTT} ({w}x{h}) and "
        + (
            f"{', '.join(p.name for p in strips)} ({min(n, STRIP_CAP)} of {n} strips)"
            if strips
            else "no strip sheet (no entry asks for one)"
        )
    )
    return out, len(cells), len(shown)


def key_sheet(
    out="proof_keys.png",
    times_json=C.REVIEW_TIMES,
    cols=4,
    tw=480,
    cap=40,
    findings=None,
):
    """Proof stage: start review_times.json afresh with the key times plus a 'finding' entry at the worst moment of
    every FIX and NOTE row (qa.py diff's 'changed' times stay: they hold until the next approval), then draw
    proof_keys.png, proof_strips.png and proof_gantt.png from it. Returns (out, moments, moments shown)."""
    mine = finding_entries(findings) + key_entries()
    keep = _changed(C.read_review_times(times_json))
    Path(times_json).write_text("[]", encoding="utf-8")
    C.add_review_times(_order(keep + mine), times_json)
    panel = timeless(findings)
    return draw_sheets(out, times_json, cols, tw, cap, mine, panel, "the proof gates")


def _order(entries):
    """Most urgent first, so the reasons merged at one time read most urgent first in the file too."""
    return sorted(entries, key=_rank)


def _changed(entries):
    """qa.py diff's times, kept across a new proof with their code and status, so an undeclared change stays FIX
    until the next diff: every entry whose kinds hold 'changed'. Of its reasons it keeps qa.py diff's own (led by a
    qa_approve code such as 'Q1303 ', or by 'changed'), or all of them when none is; the others are this proof's
    to remake."""
    lead = (*(f"{c} " for c, v in C.CODES.items() if v[0] == "qa_approve"), "changed")
    out = []
    for e in entries:
        if "changed" in e["kinds"]:
            segs = [s for s in e["why"].split("; ") if s.startswith(lead)]
            out.append(
                {
                    "t": e["t"],
                    "why": "; ".join(segs) or e["why"],
                    "kind": "changed",
                    "code": e["code"],
                    "status": e["status"],
                }
            )
    return out


def keys(
    times_json=C.REVIEW_TIMES, out="proof_keys.png", cols=4, tw=480, cap=40, rows=None
):
    """Redraw proof_keys.png, proof_strips.png and proof_gantt.png from review_times.json as it stands (after qa.py
    check, qa.py diff or the scans added to it); proof.png is not touched. With no file yet, start one from the key
    times. The panel of timeless rows lists `rows` (run_all.py deliver passes the file's), else those in
    qa_proof.json and qa.json."""
    mine = key_entries()
    if not C.read_review_times(times_json):
        C.add_review_times(_order(mine), times_json)
    source = "this run"
    if rows is None:
        rows, found = [], []
        for name in (C.QA_PROOF, C.QA_JSON):
            try:  # best effort: the panel must never stop the sheets
                rows += C.read_rows(name)
                found.append(name)
            except (OSError, ValueError, TypeError):
                pass
        source = " and ".join(found)
    panel = list({(r.status, r.code, r.msg): r for r in timeless(rows)}.values())
    return draw_sheets(out, times_json, cols, tw, cap, mine, panel, source)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="the review sheets of a build")
    sub = ap.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser(
        "keys",
        help="redraw proof_keys.png, proof_strips.png and proof_gantt.png from review_times.json (proof.png untouched)",
    )
    k.add_argument("--times", default=C.REVIEW_TIMES, help="the review times file")
    k.add_argument(
        "--cap",
        type=int,
        default=40,
        help="most cells on proof_keys.png; FIX cells are never dropped",
    )
    k.add_argument(
        "--size", help="WxH (default: build.json, else frames.hash, else run_all.py)"
    )
    k.add_argument("--fps", type=int, help="frames per second (default: as --size)")
    a = ap.parse_args()
    b = C.read_build()  # run_all.py records the frame size in every stage
    m = C.read_frame_manifest()  # the render's own record, once a render ran
    if b:
        E.W, E.H, E.FPS, E.SS = b
        if a.size:
            E.W, E.H = (int(v) for v in a.size.lower().split("x"))
        E.FPS = a.fps or E.FPS
        src = C.BUILD
    else:  # no build.json yet: run_all.py sets E.W, E.H, E.FPS and E.SS (from --size and --fps) as it imports
        if m and not a.size:
            sys.argv += ["--size", f"{m['w']}x{m['h']}"]
        if m and not a.fps:
            sys.argv += ["--fps", str(m["fps"])]
        import run_all  # noqa: F401

        src = "run_all.py"
    print(f"drawing at {E.W}x{E.H}, {E.FPS} fps, supersampling {E.SS} (from {src})")
    if m and (m["w"], m["h"], m["fps"]) != (E.W, E.H, E.FPS):
        print(f"note: frames.hash says {m['w']}x{m['h']} at {m['fps']} fps")
    out, n_keys, n_shown = keys(a.times, cap=a.cap)
    print(f"wrote {out} ({n_shown} of {n_keys} key times) and {a.times}")
