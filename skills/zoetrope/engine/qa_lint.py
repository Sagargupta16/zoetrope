# qa_lint.py : static checks of scenes.py and the local modules it imports: unseeded randomness and clocks (Q1202),
# module state written inside functions (Q1203), engine helpers redefined (Q1204), text drawn outside the engine
# text helpers (Q1205), colour literals outside the palette block (Q1206), see-through colours drawn where ImageDraw
# does not blend them (Q1207: on an RGBA picture, through a plain ImageDraw on an RGB one, and text anywhere), and
# the frame-grid lint (Q904, Q905).
# Also owner(): the scene function(s) a time or a traceback belongs to, so a fix re-reads only those.
# CLI: `python qa.py lint [scenes.py]`, `python qa.py owner --t 12.5`, `python qa.py owner --traceback err.txt`.
# A finding that is meant (a memo dict, a mask, a typesetter) is silenced by a pragma on its line, on the def line of
# the function holding it, or (Q1203) on the line that binds the module-level name: `# zoetrope: state-ok` (Q1203),
# `rng-ok` (Q1202), `shadow-ok` (Q1204), `text-ok` (Q1205), `colour-ok` (Q1206), `blend-ok` (Q1207).
import ast
import math
import re
import sys
from pathlib import Path

import contract as C

# Engine files a working folder holds next to scenes.py: the engine, not the video, so never scanned.
ENGINE_FILES = {
    "engine",
    "contract",
    "audio",
    "synth",
    "voice",
    "voice_samples",
    "render",
    "run_all",
    "proof",
    "grain",
    "transitions",
    "kit_index",
}
TAGS = {
    "Q1202": {"rng-ok"},
    "Q1203": {"state-ok"},
    "Q1204": {"shadow-ok"},
    "Q1205": {"text-ok"},
    "Q1206": {"colour-ok", "color-ok"},
    "Q1207": {"blend-ok"},
}
# what scenes.py code can raise on import or in draw(t); anything else (KeyboardInterrupt, MemoryError) stops the run
USER_ERRORS = (
    ArithmeticError,
    AssertionError,
    AttributeError,
    ImportError,
    LookupError,
    NameError,
    OSError,
    RuntimeError,
    SyntaxError,
    TypeError,
    ValueError,
)
PRAGMA = re.compile(r"#\s*zoetrope:\s*([\w\- ,]+)")
HEX = re.compile(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})")
# reads that differ from run to run: the clock and the OS entropy pool
CLOCKS = {
    "time.time",
    "time.time_ns",
    "time.perf_counter",
    "time.perf_counter_ns",
    "time.monotonic",
    "time.monotonic_ns",
    "time.process_time",
    "time.process_time_ns",
    "datetime.datetime.now",
    "datetime.datetime.utcnow",
    "datetime.datetime.today",
    "datetime.date.today",
    "os.urandom",
    "os.getrandom",
    "os.getpid",
    "os.getppid",
    "os.times",
    "time.thread_time",
    "time.thread_time_ns",
    "time.clock_gettime",
    "time.clock_gettime_ns",
}
# these read the clock when called with at most this many positional arguments (no timestamp given)
CLOCK_NOW = {
    "time.localtime": 0,
    "time.gmtime": 0,
    "time.ctime": 0,
    "time.asctime": 0,
    "time.strftime": 1,
}
SEEDED_NP = {
    "default_rng",
    "RandomState",
    "Generator",
    "SeedSequence",
    "PCG64",
    "PCG64DXSM",
    "MT19937",
    "Philox",
    "SFC64",
}
RNG_MAKERS = {
    "random.Random",
    "numpy.random.default_rng",
    "numpy.random.RandomState",
    "numpy.random.Generator",
    "engine.rng",
}
DRAW_CALLS = {"PIL.ImageDraw.Draw", "PIL.ImageDraw.ImageDraw"}
MASK_MODES = {
    "1",
    "L",
    "I",
    "F",
}  # single-band images: text drawn there is a mask the caller composites
# Q1207. Image methods that give a picture as opaque or as clear as the one they are called on (point maps the
# alpha too, rotate and transform add clear corners: those are not read)
PIC_SAME = {"copy", "resize", "crop", "filter", "transpose", "reduce"}
# Image functions that mix two pictures: the result is read only when both are read as the same
PIC_MIX = {"PIL.Image.composite", "PIL.Image.blend"}
# Image methods that change what a picture holds: the first two can make a transparent layer an opaque picture
PIC_PAINTS = {"paste", "alpha_composite", "putalpha"}
# ImageDraw methods that take a colour, with the positions of fill and outline when they are passed by position
DRAW_FILLS = {
    "line": (1,),
    "point": (1,),
    "rectangle": (1, 2),
    "ellipse": (1, 2),
    "polygon": (1, 2),
    "circle": (2, 3),
    "rounded_rectangle": (2, 3),
    "regular_polygon": (3, 4),
    "arc": (3,),
    "chord": (3, 4),
    "pieslice": (3, 4),
    "text": (2,),
    "multiline_text": (2,),
    "bitmap": (2,),
}
# of those, the ones Pillow never blends, whatever the ImageDraw's mode (measured on Pillow 13.0.0, 2026-11-24)
DRAW_NEVER = {"text", "multiline_text", "bitmap"}
NUMERIC_CALLS = {"int", "float", "round", "len", "abs", "ord", "bool", "complex"}
MUTABLE_CALLS = {
    "dict",
    "list",
    "set",
    "defaultdict",
    "OrderedDict",
    "deque",
    "Counter",
    "bytearray",
}
# builtins that read a list or a dict they are handed and leave it as it is (Q1207: a table handed to any other
# call may come back changed)
READERS = {
    "len",
    "list",
    "tuple",
    "dict",
    "set",
    "frozenset",
    "sorted",
    "enumerate",
    "zip",
    "min",
    "max",
    "sum",
    "any",
    "all",
    "iter",
    "reversed",
    "str",
    "repr",
    "print",
    "isinstance",
    "type",
    "bool",
    "map",
    "filter",
    "id",
}
# methods that change their object in place (lists, dicts, sets, deques, numpy arrays, PIL images)
MUTATORS = {
    "append",
    "extend",
    "insert",
    "pop",
    "remove",
    "clear",
    "update",
    "setdefault",
    "add",
    "discard",
    "popitem",
    "sort",
    "reverse",
    "appendleft",
    "extendleft",
    "fill",
    "put",
    "paste",
    "alpha_composite",
    "putpixel",
    "putalpha",
    "putdata",
    "thumbnail",
    "__setitem__",
}
FONT_CALLS = {
    "PIL.ImageFont.truetype",
    "PIL.ImageFont.FreeTypeFont",
    "PIL.ImageFont.load_default",
    "PIL.ImageFont.load",
    "PIL.ImageFont.load_path",
}
COLOUR_ARGS = {
    "fill",
    "color",
    "colour",
    "outline",
    "stroke_fill",
    "background",
    "bg",
    "fg",
    "ink",
    "col",
    "tint",
    "halo",
}
FIXES = {
    "Q1202": "seed it per frame or element: engine.rng(scene, element, frame), or random.Random(seed) built inside "
    "draw; zlib.crc32(s.encode()) instead of hash(s); no clock, os.urandom or uuid in a frame",
    "Q1203": "compute it from t (or an lru_cache keyed by everything it depends on); a meant memo or QA log gets "
    "# zoetrope: state-ok",
    "Q1204": "rename yours (nook_text) or call the engine helper; a deliberate override gets # zoetrope: shadow-ok",
    "Q1205": "draw text with engine text/text_outline/text_halo and font(); a mask or a kit typesetter gets "
    "# zoetrope: text-ok",
    "Q1206": "name the colour in the palette block at the top of scenes.py (INK, PAPER, ACCENT) and use the name",
    "Q1207": "draw the see-through colour on a transparent layer and composite it (lay = Image.new('RGBA', img.size, "
    "(0, 0, 0, 0)), draw on lay, img.alpha_composite(lay)); a second see-through shape on the same layer replaces "
    "what is under it too, so composite between them; text takes its alpha through engine.text. "
    "ImageDraw.Draw(img, 'RGBA') blends shapes, never text, and only on an RGB working picture that no engine "
    "helper (text, rrect, shadow) is called on: those need an RGBA frame. A draw that is meant to replace the "
    "pixels gets # zoetrope: blend-ok",
}
MEANS = {
    "Q1202": "unseeded randomness, clock reads or str hashes",
    "Q1203": "module state written inside functions",
    "Q1204": "engine helpers redefined",
    "Q1205": "text drawn outside the engine text helpers",
    "Q1206": "colour literals inside functions",
    "Q1207": "see-through colours drawn where ImageDraw does not blend them",
}


def _names(t):
    """Names a binding target binds (x, (a, b), *rest); attribute and item targets bind none."""
    if isinstance(t, ast.Name):
        return [t.id]
    if isinstance(t, (ast.Tuple, ast.List)):
        return [n for e in t.elts for n in _names(e)]
    if isinstance(t, ast.Starred):
        return _names(t.value)
    return []


def _root(e):
    """The name an expression hangs from: cache[k].x -> cache; None for a call result or a literal."""
    while isinstance(e, (ast.Attribute, ast.Subscript)):
        e = e.value
    return e.id if isinstance(e, ast.Name) else None


def _chain(e):
    """The names on the way to what an expression changes: PAL and look for look.PAL["x"], cache for cache[k].x."""
    out = []
    while isinstance(e, (ast.Attribute, ast.Subscript)):
        if isinstance(e, ast.Attribute):
            out.append(e.attr)
        e = e.value
    if isinstance(e, ast.Name):
        out.append(e.id)
    return out


def _seeded(call):
    """True when a generator call gets a seed that is not None."""
    vals = list(call.args) + [
        k.value
        for k in call.keywords
        if k.arg in ("seed", "x", "a", "entropy", "bit_generator")
    ]
    return any(not (isinstance(v, ast.Constant) and v.value is None) for v in vals)


def _rgb_tuple(e):
    """A literal colour tuple: 3 or 4 int constants, each 0 to 255; fully transparent (alpha 0) is not a colour."""
    return (
        isinstance(e, ast.Tuple)
        and len(e.elts) in (3, 4)
        and not (len(e.elts) == 4 and getattr(e.elts[3], "value", None) == 0)
        and all(
            isinstance(x, ast.Constant) and type(x.value) is int and 0 <= x.value <= 255
            for x in e.elts
        )
    )


def _keyword(call, name):
    """The value a call passes by keyword, or None."""
    return next((k.value for k in call.keywords if k.arg == name), None)


def _mode_name(node):
    """A constant image mode as the lint names it: "MASK" for a single-band mode, "RGB", "RGBA", else None."""
    v = node.value if isinstance(node, ast.Constant) else None
    return "MASK" if v in MASK_MODES else v if v in ("RGB", "RGBA") else None


def _const_in(node, values):
    """True when node is a number constant equal to one of values."""
    return (
        isinstance(node, ast.Constant)
        and type(node.value) in (int, float)
        and node.value in values
    )


def _alpha_of(colour):
    """The alpha expression of a colour written out with one: the fourth item of a 4-item tuple, the last item of a
    tuple with a starred part ((*INK, 90)), or the item added in colour + (alpha,). None for anything else."""
    if isinstance(colour, ast.Tuple):
        starred = any(isinstance(x, ast.Starred) for x in colour.elts)
        if (len(colour.elts) == 4 and not starred) or (
            starred and len(colour.elts) > 1
        ):
            last = colour.elts[-1]
            return None if isinstance(last, ast.Starred) else last
    elif (
        isinstance(colour, ast.BinOp)
        and isinstance(colour.op, ast.Add)
        and isinstance(colour.right, ast.Tuple)
        and len(colour.right.elts) == 1
        and not isinstance(colour.right.elts[0], ast.Starred)
    ):
        return colour.right.elts[0]
    return None


def _hex_alpha(s):
    """How see-through a colour string is: "opaque" for #rgb, #rrggbb and a colour name; for #rgba and #rrggbbaa
    "clear" at alpha 00, "opaque" at ff, else "see"; None for anything else (rgb(...), hsl(...), a format string)."""
    if HEX.fullmatch(s):
        d = s[1:]
        if len(d) in (3, 6):
            return "opaque"
        alpha = (d[3] * 2 if len(d) == 4 else d[6:]).lower()
        return {"00": "clear", "ff": "opaque"}.get(alpha, "see")
    return "opaque" if s.isalpha() else None


def _alpha_class(n):
    """A read alpha (see _Pix.number) as a colour class: "clear" at 0, "opaque" from 255, "see" between them or
    when it is computed, "solid" when a choice gives 0 or 255, None when it was not read (also a parameter nothing
    hands a value)."""
    if n is None or n is OPEN:
        return None
    if n is VAR:
        return "see"
    kinds = {
        "clear" if v <= 0 else "opaque" if v >= 255 else "see"
        for v in (n if isinstance(n, frozenset) else (n,))
    }
    return "see" if "see" in kinds else kinds.pop() if len(kinds) == 1 else "solid"


def _one_of(a, b):
    """An alpha that is one of two read alphas: unread when either is, computed when either is, else the numbers
    it may be (one number when they agree; computed past six)."""
    if a is None or b is None:
        return None
    if a is VAR or b is VAR:
        return VAR
    if a is OPEN or b is OPEN:
        return OPEN
    both = frozenset().union(*(v if isinstance(v, frozenset) else (v,) for v in (a, b)))
    return next(iter(both)) if len(both) == 1 else both if len(both) <= 6 else VAR


def _varies(*vals):
    """True when alphas that go into a computation make its result a computed one: none of them unread, and at
    least one computed or a parameter nothing hands a value."""
    return not any(v is None for v in vals) and any(v is VAR or v is OPEN for v in vals)


def _spread(fn, *vals):
    """fn over read alphas: None when one is unread, VAR when one is computed, else fn of the numbers, for every
    choice when one of them is a choice of numbers (computed past 36 results; unread when fn cannot work them
    out)."""
    if any(v is None for v in vals):
        return None
    if any(v is VAR or v is OPEN for v in vals):
        return VAR
    out = [()]
    for v in vals:
        out = [
            row + (x,) for row in out for x in (v if isinstance(v, frozenset) else (v,))
        ]
        if len(out) > 36:
            return VAR
    try:
        got = {fn(*row) for row in out}
    except (ArithmeticError, ValueError, TypeError):
        return None  # constants the lint cannot work out: unread
    if any(type(x) not in (int, float) for x in got):
        return None
    return got.pop() if len(got) == 1 else frozenset(got)


def _same(a, b):
    """What two readings of one picture agree on: the reading when they are equal, tuples item by item, else None."""
    if a == b:
        return a
    if a and b and a[0] == b[0] == "tup" and len(a[1]) == len(b[1]):
        return ("tup", tuple(_same(x, y) for x, y in zip(a[1], b[1])))
    return None


def _either(a, b):
    """A colour that is one of two: see-through when either is, unread when either is unread, else what they share
    ("solid" for an opaque one and an erase)."""
    if "see" in (a, b):
        return "see"
    if a is None or b is None:
        return None
    return a if a == b else "solid"


def _pos(n):
    return (n.lineno, n.col_offset)


def _end(n):
    return (n.end_lineno, n.end_col_offset)


def header(fn):
    """Line range of a def's header (decorators to the line before its body): where a def-level pragma goes."""
    body = fn.body if isinstance(fn.body, list) else [fn.body]
    first = min([d.lineno for d in getattr(fn, "decorator_list", [])] + [fn.lineno])
    last = (
        body[0].lineno - 1
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        else fn.lineno
    )
    return range(first, max(fn.lineno, last) + 1)


def _in_scope(nodes):
    """Walk statements without entering nested function, lambda or class bodies (their own scopes)."""
    stack = list(nodes)
    while stack:
        n = stack.pop()
        yield n
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            stack.extend(n.decorator_list)
            continue
        if isinstance(n, ast.Lambda):
            continue
        stack.extend(ast.iter_child_nodes(n))


def _defaults(fn):
    """(arg, default) pairs of a def or lambda, positional and keyword-only."""
    a = fn.args
    pos = a.posonlyargs + a.args
    return list(zip(pos[len(pos) - len(a.defaults) :], a.defaults)) + [
        (k, d) for k, d in zip(a.kwonlyargs, a.kw_defaults) if d is not None
    ]


def _mutable(d):
    """A default made once when the def runs and shared by every call: a list, dict or set display or call."""
    return isinstance(
        d, (ast.Dict, ast.List, ast.Set, ast.DictComp, ast.ListComp, ast.SetComp)
    ) or (
        isinstance(d, ast.Call) and ast.unparse(d.func).split(".")[-1] in MUTABLE_CALLS
    )


def _bound_values(n):
    """(name, value) pairs a statement binds: x = v, x: T = v, a, b = v1, v2, with v as x."""
    if isinstance(n, ast.Assign):
        out = []
        for t in n.targets:
            if isinstance(t, ast.Name):
                out.append((t.id, n.value))
            elif (
                isinstance(t, (ast.Tuple, ast.List))
                and isinstance(n.value, (ast.Tuple, ast.List))
                and len(t.elts) == len(n.value.elts)
            ):
                out += [
                    (a.id, b)
                    for a, b in zip(t.elts, n.value.elts)
                    if isinstance(a, ast.Name)
                ]
        return out
    if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.value:
        return [(n.target.id, n.value)]
    if isinstance(n, (ast.With, ast.AsyncWith)):
        return [
            (it.optional_vars.id, it.context_expr)
            for it in n.items
            if isinstance(it.optional_vars, ast.Name)
        ]
    return []


def _hex_colour(s):
    """A colour literal: #rgb, #rgba, #rrggbb or #rrggbbaa. Three or four decimal digits that are not one repeated
    digit ("#404", "#100") read as a number or a tag, so they do not count; "#000" and "#333" do."""
    if not isinstance(s, str) or not HEX.fullmatch(s):
        return False
    d = s[1:]
    return not (len(d) <= 4 and d.isdigit() and len(set(d)) > 1)


def _number(e):
    """True when e can only be a number: a numeric literal, int(...), round(...) and the like, or arithmetic on
    those."""
    if isinstance(e, ast.Constant):
        return isinstance(e.value, (int, float)) and not isinstance(e.value, bool)
    if isinstance(e, ast.Call) and isinstance(e.func, ast.Name):
        return e.func.id in NUMERIC_CALLS
    if isinstance(e, ast.UnaryOp):
        return _number(e.operand)
    if isinstance(e, ast.BinOp):
        return _number(e.left) and _number(e.right)
    return False


def _maybe_str(e):
    """False when e cannot be a str or bytes (a number, or a tuple of numbers): only str and bytes hashes change
    from one process to the next."""
    if isinstance(e, (ast.Tuple, ast.List)):
        return any(_maybe_str(x) for x in e.elts)
    return not _number(e) and not (
        isinstance(e, ast.Constant) and not isinstance(e.value, (str, bytes))
    )


def star_exports(path, module):
    """{name: (dotted origin, is a variable)} of what `from <module> import *` binds: the module's own public
    imports (import numpy as np -> numpy) and its public top-level definitions (rng -> engine.rng; W, FONT_BOLD are
    variables). __all__ is honoured when the module sets one."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    out, only = {}, None
    for s in tree.body:
        if isinstance(s, ast.Import):
            for a in s.names:
                top = a.name.split(".")[0]
                out[a.asname or top] = (a.name if a.asname else top, False)
        elif isinstance(s, ast.ImportFrom) and s.module and not s.level:
            for a in s.names:
                if a.name != "*":
                    out[a.asname or a.name] = (f"{s.module}.{a.name}", False)
        elif isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[s.name] = (f"{module}.{s.name}", False)
        elif isinstance(s, (ast.Assign, ast.AnnAssign)):
            for t in s.targets if isinstance(s, ast.Assign) else [s.target]:
                for x in _names(t):
                    if x == "__all__" and isinstance(s.value, (ast.List, ast.Tuple)):
                        only = {
                            e.value for e in s.value.elts if isinstance(e, ast.Constant)
                        }
                    else:
                        out[x] = (f"{module}.{x}", True)
    return {
        k: v
        for k, v in out.items()
        if (k in only if only is not None else not k.startswith("_"))
    }


class _Scope:
    """One function's names: Python makes a name local when the function binds it, unless it says global. A name
    bound by an import inside the function is kept apart (imports): it still means that module. memo holds the
    parameters with a mutable default (one object for every call); aliases, draws, mask_draws and masks are filled by
    _Scan.facts (a name bound to a module path, to an ImageDraw, to an ImageDraw on a mask, to a mask image)."""

    def __init__(self, fn):
        self.name = getattr(fn, "name", "<lambda>")
        body = fn.body if isinstance(fn.body, list) else [fn.body]
        self.header = header(fn)
        self.glob, self.nonloc, self.loc, self.writes = set(), set(), set(), []
        self.imports, self.memo = set(), set()
        self.aliases, self.draws, self.mask_draws, self.masks = {}, set(), set(), set()
        self.import_time = False  # set by _Scan.visit: True when this body only runs while the module imports
        args = fn.args
        for x in (
            args.posonlyargs + args.args + args.kwonlyargs + [args.vararg, args.kwarg]
        ):
            if x:
                self.loc.add(x.arg)
        for arg, d in _defaults(fn):
            if _mutable(d):
                self.memo.add(arg.arg)
        for n in _in_scope(body):
            if isinstance(n, ast.Global):
                self.glob.update(n.names)
            elif isinstance(n, ast.Nonlocal):
                self.nonloc.update(n.names)
        for n in _in_scope(body):
            bound = []
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bound = [n.name]
            elif isinstance(n, ast.Assign):
                bound = [x for t in n.targets for x in _names(t)]
            elif isinstance(
                n,
                (
                    ast.AugAssign,
                    ast.AnnAssign,
                    ast.For,
                    ast.AsyncFor,
                    ast.comprehension,
                ),
            ):
                bound = _names(n.target)
            elif isinstance(n, (ast.With, ast.AsyncWith)):
                bound = [
                    x
                    for it in n.items
                    if it.optional_vars
                    for x in _names(it.optional_vars)
                ]
            elif isinstance(n, ast.ExceptHandler) and n.name:
                bound = [n.name]
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                self.imports.update(
                    (a.asname or a.name).split(".")[0] for a in n.names if a.name != "*"
                )
            elif isinstance(n, ast.NamedExpr):
                bound = _names(n.target)
            elif isinstance(n, ast.Delete):
                bound = [x for t in n.targets for x in _names(t)]
            for x in bound:
                if x in self.glob:
                    self.writes.append((x, n))
                else:
                    self.loc.add(x)


class _Scan:
    """The findings of one file. qual() resolves a call through the file's imports, through what a star import of a
    folder module brings (`from engine import *` gives np, os and rng), and through names bound to a module path
    (npr = np.random): np.random.rand -> numpy.random.rand, r.random -> random.random. Module state is a name bound
    at module level, an object reached through an imported module (E.FONT_BOLD, K.LOG), or a mutable default."""

    def __init__(self, path, folder_tops=None, import_time=(), folder_rngs=None):
        self.path = Path(path)
        # {module: rngs()} of the folder modules, each judged in its own file
        self.folder_rngs = folder_rngs or {}
        self.import_time = set(
            import_time
        )  # defs that only run while the module imports (table builders)
        self.src = self.path.read_text(encoding="utf-8")
        self.lines = self.src.splitlines()
        self.tree = ast.parse(self.src, filename=str(self.path))
        self.alias, self.state_alias, self.star = {}, set(), set()
        folder_tops = folder_tops or {}
        for n in ast.walk(self.tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    top = a.name.split(".")[0]
                    self.alias[a.asname or top] = a.name if a.asname else top
            elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
                for a in n.names:
                    if a.name != "*":
                        self.alias[a.asname or a.name] = f"{n.module}.{a.name}"
                        if a.name in folder_tops.get(
                            n.module, {}
                        ):  # from kit import LOG: kit's own state
                            self.state_alias.add(a.asname or a.name)
        for s in (
            self.tree.body
        ):  # what `from engine import *` (or a folder module's) brings
            if (
                isinstance(s, ast.ImportFrom)
                and s.module
                and not s.level
                and any(a.name == "*" for a in s.names)
            ):
                src = (
                    _engine_file(self.path.parent)
                    if s.module == "engine"
                    else self.path.parent / f"{s.module}.py"
                )
                if src.exists():
                    for name, (q, var) in star_exports(src, s.module).items():
                        if name not in self.alias:
                            self.alias[name] = q
                            self.star.add(name)
                            if var:
                                self.state_alias.add(name)
        self.top = {}  # module-level name -> (line, value node or None)
        self._bindings(self.tree.body)
        self.draws, self.mask_draws, self.masks = (
            set(),
            set(),
            set(),
        )  # module level, filled next
        al, self.draws, self.mask_draws, self.masks = self.facts(self.tree.body, [])
        for name, q in al.items():
            self.alias.setdefault(name, q)  # npr = np.random at module level
        self.found, self.calls, self.silenced = [], 0, 0

    def _bindings(self, body):
        for s in body:
            if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                self.top.setdefault(s.name, (s.lineno, None))
            elif isinstance(s, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                for t in s.targets if isinstance(s, ast.Assign) else [s.target]:
                    for x in _names(t):
                        self.top.setdefault(x, (s.lineno, s.value))
            elif isinstance(s, (ast.For, ast.AsyncFor)):
                for x in _names(s.target):
                    self.top.setdefault(x, (s.lineno, None))
                self._bindings(s.body + s.orelse)
            elif isinstance(s, (ast.If, ast.While)):
                self._bindings(s.body + s.orelse)
            elif isinstance(s, (ast.With, ast.AsyncWith)):
                self._bindings(s.body)
            elif isinstance(s, (ast.Try, ast.TryStar)):
                self._bindings(
                    s.body
                    + [x for h in s.handlers for x in h.body]
                    + s.orelse
                    + s.finalbody
                )

    def facts(self, nodes, stack):
        """(aliases, draws, mask_draws, masks) bound by one scope's own statements: names bound to a module path,
        to ImageDraw.Draw(...), to an ImageDraw on a mask, and to a mask image (Image.new or .convert in mode 1, L,
        I or F)."""
        pairs = [p for n in _in_scope(nodes) for p in _bound_values(n)]
        aliases, draws, mask_draws, masks = {}, set(), set(), set()
        for name, v in pairs:  # masks first, so a Draw on one is known as a mask
            if self.mask_expr(v, stack, masks):
                masks.add(name)
        for name, v in pairs:
            if isinstance(v, (ast.Name, ast.Attribute)):
                q = self.qual(v, stack)
                if q:
                    aliases[name] = q
            elif isinstance(v, ast.Call) and self.qual(v.func, stack) in DRAW_CALLS:
                draws.add(name)
                if v.args and self.mask_expr(v.args[0], stack, masks):
                    mask_draws.add(name)
        return aliases, draws, mask_draws, masks

    # ---- helpers ----

    def where(self, name, stack):
        """What name means inside the innermost function of stack: ("module", None) for a module-level or builtin
        name, ("import", None) for a module the function imports, ("alias", path), ("memo", scope) for a
        parameter with a mutable default, ("local", scope) for any other local or closure variable."""
        for sc in reversed(stack):
            if name in sc.glob:
                return "module", None
            if name in sc.imports:
                return "import", None
            if name in sc.aliases:
                return "alias", sc.aliases[name]
            if name in sc.memo:
                return "memo", sc
            if name in sc.loc or name in sc.nonloc:
                return "local", sc
        return "module", None

    def free(self, name, stack):
        """True when name, inside the innermost function of stack, means the module-level (or builtin) name or a
        module imported in the function; False for a local variable or a closure variable."""
        return self.where(name, stack)[0] in ("module", "import")

    def qual(self, e, stack):
        parts = []
        while isinstance(e, ast.Attribute):
            parts.append(e.attr)
            e = e.value
        if (  # getattr(random, "random") is random.random
            isinstance(e, ast.Call)
            and isinstance(e.func, ast.Name)
            and e.func.id == "getattr"
            and len(e.args) >= 2
            and isinstance(e.args[1], ast.Constant)
            and isinstance(e.args[1].value, str)
            and self.free("getattr", stack)
        ):
            base = self.qual(e.args[0], stack)
            return ".".join([base, e.args[1].value] + parts[::-1]) if base else None
        if (  # importlib.import_module("time") is time, __import__("os.path") is os
            isinstance(e, ast.Call)
            and e.args
            and isinstance(e.args[0], ast.Constant)
            and isinstance(e.args[0].value, str)
        ):
            if self.qual(e.func, stack) == "importlib.import_module":
                return ".".join([e.args[0].value] + parts[::-1])
            if (
                isinstance(e.func, ast.Name)
                and e.func.id == "__import__"
                and "__import__" not in self.top
                and self.free("__import__", stack)
            ):
                return ".".join([e.args[0].value.split(".")[0]] + parts[::-1])
        if not isinstance(e, ast.Name):
            return None
        kind, val = self.where(e.id, stack)
        if kind == "alias":
            base = val
        elif (
            kind in ("module", "import")
            and e.id in self.alias
            and not (
                e.id in self.star and e.id in self.top
            )  # a scenes.py def wins over a star import
        ):
            base = self.alias[e.id]
        else:
            return None
        return ".".join([base] + parts[::-1])

    def seg(self, n, width=60):
        s = " ".join((ast.get_source_segment(self.src, n) or ast.unparse(n)).split())
        return s if len(s) <= width else s[: width - 3] + "..."

    def state_root(self, e, stack):
        """The long-lived object e writes into, or None: a name bound at module level, an object inside an
        imported module (E.FONT_BOLD, sys.path), a variable imported from a local module, or a parameter's mutable
        default (def memo(x, _c={}): the same dict on every call)."""
        r = _root(e)
        if r is None:
            return None
        kind, _ = self.where(r, stack)
        if kind == "memo":
            return r
        if kind in ("local", "alias"):
            return None
        if r in self.alias:
            return (
                r
                if (e is not None and not isinstance(e, ast.Name))
                or r in self.state_alias
                else None
            )
        return r if r in self.top else None

    def state_desc(self, r, stack):
        return (
            f"the mutable default {r} (one object for every call)"
            if self.where(r, stack)[0] == "memo"
            else f"module state {r}"
        )

    def rng_kind(self, v):
        """ "gen" when a module-level value makes a generator (random.Random(7), np.random.default_rng(7)), "pool"
        when it is a list, tuple, set or dict of them (a display or a comprehension), else None."""
        if isinstance(v, ast.Call):
            return "gen" if self.qual(v.func, []) in RNG_MAKERS else None
        if isinstance(v, (ast.List, ast.Tuple, ast.Set)):
            items = v.elts
        elif isinstance(v, ast.Dict):
            items = v.values
        elif isinstance(v, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            items = [v.elt]
        elif isinstance(v, ast.DictComp):
            items = [v.value]
        else:
            return None
        return "pool" if any(self.rng_kind(x) == "gen" for x in items) else None

    def rngs(self):
        """{name: "gen" or "pool"} of this module's top-level generators: what findings() hands the files that
        import them."""
        return {
            x: k
            for x, (_, v) in self.top.items()
            if v is not None and (k := self.rng_kind(v))
        }

    def generator(self, e):
        """True when e, the object a method is called on, is a generator that lives at module level: a name bound
        to one here (RNG = random.Random(7)) or in a folder module it imports (from kit import RNG, kit.RNG), or an
        item of a module-level list, tuple or dict of them (POOL[0], kit.POOL[0])."""
        want = "gen"
        if isinstance(e, ast.Subscript):
            e, want = e.value, "pool"
        if isinstance(e, ast.Name) and e.id in self.top:
            return self.rng_kind(self.top[e.id][1]) == want
        mod, _, name = (self.qual(e, []) or "").rpartition(".")
        return self.folder_rngs.get(mod, {}).get(name) == want

    def mask_expr(self, v, stack, masks=()):
        """True when v is a mask image: Image.new or .convert in a single-band mode, or a name bound to one."""
        if isinstance(v, ast.Call) and v.args and isinstance(v.args[0], ast.Constant):
            mode = v.args[0].value
            if self.qual(v.func, stack) == "PIL.Image.new" or (
                isinstance(v.func, ast.Attribute) and v.func.attr == "convert"
            ):
                return mode in MASK_MODES
            return False
        if isinstance(v, ast.Name):
            if v.id in masks:
                return True
            for sc in reversed(stack):
                if v.id in sc.masks:
                    return True
                if v.id in sc.loc:
                    return False
            return v.id in self.masks
        return False

    def draw_kind(self, e, stack):
        """ "draw" for an ImageDraw, "mask" for an ImageDraw on a mask image, None for anything else (a module's own
        text helper, an object with its own text method, a parameter whose type is unknown)."""
        if isinstance(e, ast.Call):
            if self.qual(e.func, stack) in DRAW_CALLS:
                return "mask" if e.args and self.mask_expr(e.args[0], stack) else "draw"
            return None
        if not isinstance(e, ast.Name):
            return None
        for sc in reversed(stack):
            if e.id in sc.draws:
                return "mask" if e.id in sc.mask_draws else "draw"
            if e.id in sc.loc or e.id in sc.nonloc:
                return None
        if e.id in self.draws:
            return "mask" if e.id in self.mask_draws else "draw"
        return None

    def tagged(self, code, lines):
        for i in lines:
            if 0 < i <= len(self.lines):
                m = PRAGMA.search(self.lines[i - 1])
                if (
                    m
                    and {x.lower() for x in re.split(r"[ ,]+", m.group(1))} & TAGS[code]
                ):
                    return True
        return False

    def add(self, code, n, msg, stack, extra=(), func=None):
        if code == "Q1203" and any(sc.import_time for sc in stack):
            return  # state written while the module imports is a table, not frame state
        lines = list(range(n.lineno, (n.end_lineno or n.lineno) + 1)) + list(extra)
        lines += [i for sc in stack for i in sc.header]
        if self.tagged(code, lines):
            self.silenced += 1
            return
        self.found.append(
            {
                "code": code,
                "file": self.path.name,
                "line": n.lineno,
                "func": func or (stack[-1].name if stack else "<module>"),
                "text": self.seg(n),
                "msg": msg,
            }
        )

    # ---- the walk ----

    def scan(self):
        self.visit(self.tree, [])
        return self

    def visit(self, node, stack):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                for d in getattr(ch, "decorator_list", []):
                    self.check(d, stack)
                    self.visit(d, stack)
                self.defaults(ch, stack)
                sc = _Scope(ch)
                sc.import_time = (
                    any(s.import_time for s in stack)
                    if stack
                    else getattr(ch, "name", None) in self.import_time
                    or (
                        isinstance(ch, ast.Lambda)
                        and isinstance(node, (ast.Call, ast.keyword))
                    )
                )  # a def only called at import, or a lambda passed to a module-level call (a sort key)
                inner = stack + [sc]
                body = ch.body if isinstance(ch.body, list) else [ast.Expr(ch.body)]
                sc.aliases, sc.draws, sc.mask_draws, sc.masks = self.facts(body, inner)
                for x, w in sc.writes:
                    self.add(
                        "Q1203",
                        w,
                        f"global {x} written: the next frame sees what this one left",
                        inner,
                        extra=[self.top[x][0]] if x in self.top else (),
                    )
                # through the same dispatch, so a def directly in this body gets its own scope
                self.visit(ast.Module(body=body, type_ignores=[]), inner)
            else:
                self.check(ch, stack)
                self.visit(ch, stack)

    def defaults(self, fn, stack):
        """Parameter defaults run in the enclosing scope. Q1206 on them: a hex string anywhere, an RGB tuple on a
        colour-named parameter (color=(24, 12, 36))."""
        for arg, d in _defaults(fn):
            hexs = isinstance(d, ast.Constant) and _hex_colour(d.value)
            if hexs or (arg.arg in COLOUR_ARGS and _rgb_tuple(d)):
                self.add(
                    "Q1206",
                    d,
                    f"default colour {arg.arg}={self.seg(d)}",
                    stack,
                    extra=header(fn),
                    func=getattr(fn, "name", "<lambda>"),
                )
            else:
                self.check(d, stack)
                self.visit(d, stack)

    def check(self, n, stack):
        if isinstance(n, ast.Call):
            self.calls += 1
            self.rng_clock(n, stack)
            self.text_font(n, stack)
            if stack:
                self.mutating_call(n, stack)
                for k in n.keywords:
                    if k.arg in COLOUR_ARGS and _rgb_tuple(k.value):
                        self.add(
                            "Q1206",
                            k.value,
                            f"colour {k.arg}={self.seg(k.value)}",
                            stack,
                        )
        elif stack and isinstance(
            n, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)
        ):
            targets = (
                n.targets if isinstance(n, (ast.Assign, ast.Delete)) else [n.target]
            )
            todo = list(targets)
            while todo:
                t = todo.pop()
                if isinstance(t, (ast.Tuple, ast.List)):
                    todo.extend(t.elts)
                elif isinstance(t, (ast.Subscript, ast.Attribute)):
                    r = self.state_root(t, stack)
                    if r:
                        self.add(
                            "Q1203",
                            n,
                            f"{self.seg(t)} {'deleted' if isinstance(n, ast.Delete) else 'written'}: "
                            f"{self.state_desc(r, stack)} changes as frames are drawn",
                            stack,
                            extra=[self.top[r][0]] if r in self.top else (),
                        )
        elif stack and isinstance(n, ast.Constant) and _hex_colour(n.value):
            self.add("Q1206", n, f"colour {n.value!r}", stack)

    def rng_clock(self, n, stack):
        q = self.qual(n.func, stack)
        if q is None:
            if (
                isinstance(n.func, ast.Name)
                and n.func.id == "hash"
                and "hash" not in self.top
                and self.free("hash", stack)
                and n.args
                and _maybe_str(n.args[0])
            ):
                self.add(
                    "Q1202",
                    n,
                    "hash() of a str or bytes changes with every process (str hash seed), so each render worker "
                    "draws it differently",
                    stack,
                )
            return
        bad = None
        if (
            q in CLOCKS
            or (q in CLOCK_NOW and len(n.args) <= CLOCK_NOW[q] and not n.keywords)
            or q.startswith("secrets.")
            or (
                q.startswith("uuid.")
                and q not in ("uuid.uuid3", "uuid.uuid5", "uuid.UUID")
            )
        ):
            bad = "reads the clock, the process or the OS entropy pool: the frame changes from run to run"
        elif q.startswith("random.") and not (q == "random.Random" and _seeded(n)):
            bad = "uses the shared random stream (or an unseeded Random): the frame depends on draw order and process"
        elif q.startswith("numpy.random.") and not (
            q.split(".")[2] in SEEDED_NP and _seeded(n)
        ):
            bad = "uses numpy's global stream (or an unseeded generator): the frame depends on draw order and process"
        if bad:
            self.add("Q1202", n, f"{q} {bad}", stack)

    def text_font(self, n, stack):
        f = n.func
        if isinstance(f, ast.Attribute) and f.attr in ("text", "multiline_text"):
            fill = next((k.value for k in n.keywords if k.arg == "fill"), None)
            if fill is None and len(n.args) > 2:
                fill = n.args[2]
            # an ImageDraw only; text drawn into a mask (a single-band image, or a plain number as fill) is allowed
            if self.draw_kind(f.value, stack) == "draw" and not (
                fill is not None and _number(fill)
            ):
                self.add(
                    "Q1205",
                    n,
                    f".{f.attr}() draws text past the engine helpers: engine.text_box no longer describes it (Q205), and "
                    "supersampling, alpha and anchors are done by hand",
                    stack,
                )
        elif self.qual(f, stack) in FONT_CALLS:
            self.add(
                "Q1205",
                n,
                "loads a font outside engine.font(): the FONT_BOLD and FONT_REG lists and the missing-font error are bypassed",
                stack,
            )

    def mutating_call(self, n, stack):
        f = n.func
        if self.qual(f, stack) in DRAW_CALLS and n.args:
            r = self.state_root(n.args[0], stack)
            if r and r not in self.alias:
                self.add(
                    "Q1203",
                    n,
                    f"draws onto the module-level image {r}: every frame paints over the last",
                    stack,
                    extra=[self.top[r][0]] if r in self.top else (),
                )
            return
        if not isinstance(f, ast.Attribute):
            return
        r = self.state_root(f.value, stack)
        if r and f.attr in MUTATORS:
            self.add(
                "Q1203",
                n,
                f"{self.seg(f.value, 30)}.{f.attr}() changes {self.state_desc(r, stack)} as frames are drawn",
                stack,
                extra=[self.top[r][0]] if r in self.top else (),
            )
        elif r and self.generator(f.value):
            g = self.seg(f.value, 30)
            self.add(
                "Q1203",
                n,
                f"{g}.{f.attr}() draws from the module-level generator {g}: its stream advances with every frame, "
                "so frames depend on draw order",
                stack,
                extra=[self.top[r][0]] if r in self.top else (),
            )


def defined_names(path):
    """{name: line} of what a module itself defines at top level (defs, classes, assignments), underscores skipped.
    Imported names are not definitions."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    out = {}
    for s in tree.body:
        names = []
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names = [s.name]
        elif isinstance(s, (ast.Assign, ast.AnnAssign)):
            names = [
                x
                for t in (s.targets if isinstance(s, ast.Assign) else [s.target])
                for x in _names(t)
            ]
        for x in names:
            if not x.startswith("_"):
                out.setdefault(x, s.lineno)
    return out


def local_modules(path):
    """[Path] of scenes.py and every module file in its folder it imports, transitively; engine and qa_* skipped."""
    return C.local_imports(path, skip=lambda m: m in ENGINE_FILES or m.startswith("qa"))


def _engine_file(folder):
    p = Path(folder) / "engine.py"
    return p if p.exists() else Path(__file__).with_name("engine.py")


def shadow_findings(path):
    """Q1204: top-level defs and classes in scenes.py named like something engine.py defines or re-exports from its
    own folder (the contract clock), or a module scenes.py star-imports from its folder defines."""
    path = Path(path)
    sc = _Scan(path)
    eng = _engine_file(path.parent)
    owners = {n: ("engine.py", ln) for n, ln in defined_names(eng).items()}
    for s in ast.parse(eng.read_text(encoding="utf-8")).body:
        # engine.py re-exports the contract clock (frame_of, snap, stepped ...): its API too, unlike PIL's names
        if (
            isinstance(s, ast.ImportFrom)
            and s.module
            and eng.with_name(f"{s.module}.py").exists()
        ):
            for a in s.names:
                if a.name != "*" and not (a.asname or a.name).startswith("_"):
                    owners.setdefault(a.asname or a.name, ("engine.py", s.lineno))
    for n in sc.tree.body:
        if (
            isinstance(n, ast.ImportFrom)
            and n.module
            and any(a.name == "*" for a in n.names)
        ):
            q = path.parent / f"{n.module}.py"
            if n.module != "engine" and q.exists():
                for x, ln in defined_names(q).items():
                    owners.setdefault(x, (q.name, ln))
    defs = [
        s
        for s in sc.tree.body
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    out, silenced = [], 0
    for s in defs:
        if s.name not in owners:
            continue
        if sc.tagged("Q1204", header(s)):
            silenced += 1
            continue
        f, ln = owners[s.name]
        out.append(
            {
                "code": "Q1204",
                "file": path.name,
                "line": s.lineno,
                "func": s.name,
                "text": f"def {s.name}",
                "msg": f"{s.name} redefines {f[:-3]}.{s.name} ({f}:{ln}): two functions answer to one name, and "
                "engine code keeps calling its own",
            }
        )
    return out, len(defs), silenced


def import_time_defs(trees):
    """Names of top-level defs that only run while the modules import: called directly at module level, and never
    named anywhere else (not inside any function or lambda, not stored in a dispatch dict). cap() and ev() in the
    bonus-rectangle kit build their caption and event tables this way."""
    called, named, inside = set(), set(), set()

    def walk(n, infn, direct=False):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            for ch in ast.iter_child_nodes(n):
                walk(ch, True)
            return
        if isinstance(n, ast.Name):
            (inside if infn else called if direct else named).add(n.id)
        elif isinstance(n, ast.Attribute):
            (inside if infn else named).add(n.attr)
        for ch in ast.iter_child_nodes(n):
            walk(ch, infn, isinstance(n, ast.Call) and ch is n.func)

    for t in trees:
        walk(t, False)
    return called - named - inside


# ---- Q1207: see-through colours that ImageDraw does not blend ----
#
# Pillow blends a colour only through ImageDraw.Draw(img, "RGBA") on an RGB image, and never text or a bitmap. On an
# RGBA picture the colour replaces the pixel and its alpha; a plain ImageDraw on RGB drops the alpha. The rule fires
# only on what it has read. A picture's mode is read from how the picture is made, a colour's alpha from how it is
# written, and both are followed through the folder's defs one call at a time: a def is read again for each different
# set of pictures, ImageDraws, colours and alphas a call hands it (_Pix.run), so the colour of one call is never held
# against the picture of another. An unread picture or alpha says nothing, and neither does a draw on the opaque side
# of a test of its own alpha (if a >= 1: straight on, else through a layer) or under a test of its picture's mode
# (_Pix.guarded_off).

INF = (1 << 60, 0)  # after every line: how a body's names stand once it has run
VAR = "computed"  # an alpha worked out from other values (int(255 * t)): see-through
# a parameter that no call the lint follows hands a value: unread as an alpha by itself, computed once worked on
OPEN = "open"
_ON_OFF = frozenset((0, 1))  # what a comparison gives when it is used as a number
FREE = "free"  # what _reach says of a name the body never binds
PARAM = "param"  # and of a parameter that is still what the call handed in
STEPS = 20000  # readings of a def before the lint stops following calls; the Q1207 row says when that happened
DEEP = 60  # calls followed one inside another
# decorators under which a def still gets the arguments its callers write
_PLAIN = {"functools.lru_cache", "functools.cache"}


class _Bind:
    """One binding of a name: where it takes effect (vis), the block chain it sits in, the comprehension variables
    around it (shadow), and what it binds: value (an expression, None when the lint cannot read it), item (i, n) for
    item i of a value unpacked into n names, iter (the iterable, i) for a loop variable, fn for a def, imp for an
    import (src: what it imports, as module.name), aug for x += 1; body is the block of the loop a loop variable
    belongs to."""

    value = item = iter = fn = src = body = None
    imp = aug = False

    def __init__(self, vis, chain, shadow, **what):
        self.vis, self.chain, self.shadow = vis, chain, shadow
        self.__dict__.update(what)


class _Flow:
    """What one body binds, calls and returns, in source order: the body of a module, a class, a def or a lambda.
    A block chain names the branches a statement sits in (an if or else body, a loop body, a part of a try, a match
    case; a with body is the block of the with itself), so a use can tell a binding that encloses it from one in a
    sibling branch. calls holds (call, chain, shadow), events the pastes into a name, inner the defs, classes and
    lambdas written in the body, returns (value, chain), loops the blocks that are loop bodies."""

    def __init__(self, node):
        self.node = node
        self.binds, self.events = {}, {}
        self.calls, self.inner, self.returns = [], [], []
        self.loops, self.glob = set(), set()
        # a name this body or a def nested in it rebinds through `nonlocal` is unknown here
        self.nonloc = {
            x for n in ast.walk(node) if isinstance(n, ast.Nonlocal) for x in n.names
        }
        self.yields, self.plan = False, None
        # the test of each if and while block with the side it runs on, per block the ifs that leave early, and
        # the two sides of each conditional expression (from, to, test, side)
        self.tests, self.exits, self.sides = {}, {}, []
        # (place, module) for each `from module import *`, in source order
        self.stars = []
        # (place, chain, shadow, call) for each ImageDraw method that takes a colour
        self.draws = []
        a = getattr(node, "args", None)
        self.params = (
            {
                x.arg
                for x in a.posonlyargs + a.args + a.kwonlyargs + [a.vararg, a.kwarg]
                if x
            }
            if a
            else set()
        )
        if isinstance(node, ast.Lambda):
            self.returns.append((node.body, ()))
            self.expr(node.body, (), frozenset())
        else:
            self.block(node.body, ())
        self.calls.sort(key=lambda c: _pos(c[0]))
        for rows in self.events.values():
            rows.sort(key=lambda r: r[0])

    def bind(self, name, vis, chain, shadow=frozenset(), **what):
        self.binds.setdefault(name, []).append(_Bind(vis, chain, shadow, **what))

    def block(self, stmts, chain):
        for s in stmts:
            self.stmt(s, chain)
            if isinstance(s, ast.If) and isinstance(s.body[-1], _LEAVES):
                # what follows in this block runs only when the test did not hold
                self.exits.setdefault(chain, []).append((_end(s), s.test))

    def stmt(self, s, chain):
        none = frozenset()
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for e in s.decorator_list + [d for _, d in _defaults(s)]:
                self.expr(e, chain, none)
            self.bind(s.name, _end(s), chain, fn=s)
            self.inner.append((s, chain, none))
        elif isinstance(s, ast.ClassDef):
            for e in s.decorator_list + s.bases + [k.value for k in s.keywords]:
                self.expr(e, chain, none)
            self.bind(s.name, _end(s), chain)
            self.inner.append((s, chain, none))
        elif isinstance(s, ast.Return):
            self.returns.append((s.value, chain))
            self.expr(s.value, chain, none)
        elif isinstance(s, ast.Assign):
            self.expr(s.value, chain, none)
            for t in s.targets:
                self.expr(t, chain, none)
                self.target(t, s.value, _end(s), chain)
        elif isinstance(s, ast.AnnAssign):
            self.expr(s.value, chain, none)
            if isinstance(s.target, ast.Name) and s.value is not None:
                self.bind(s.target.id, _end(s), chain, value=s.value)
        elif isinstance(s, ast.AugAssign):
            self.expr(s.value, chain, none)
            for x in _names(s.target):
                self.bind(x, _end(s), chain, aug=True)
        elif isinstance(s, (ast.For, ast.AsyncFor)):
            self.expr(s.iter, chain, none)
            body = chain + ((id(s), "b"),)
            self.loops.add(body[-1])
            start = _pos(s.body[0])
            if isinstance(s.target, ast.Name):
                self.bind(s.target.id, start, chain, iter=(s.iter, None), body=body[-1])
            elif isinstance(s.target, (ast.Tuple, ast.List)):
                for i, x in enumerate(s.target.elts):
                    if isinstance(x, ast.Name):
                        self.bind(x.id, start, chain, iter=(s.iter, i), body=body[-1])
                    else:
                        for name in _names(x):
                            self.bind(name, start, chain)
            self.block(s.body, body)
            self.block(s.orelse, chain + ((id(s), "e"),))
        elif isinstance(s, ast.While):
            body = chain + ((id(s), "b"),)
            self.loops.add(body[-1])
            self.tests[body[-1]] = (s.test, True)
            # read again on every pass, so it sits inside the loop
            self.expr(s.test, body, none)
            self.block(s.body, body)
            self.block(s.orelse, chain + ((id(s), "e"),))
        elif isinstance(s, ast.If):
            self.expr(s.test, chain, none)
            self.tests[(id(s), "b")] = (s.test, True)
            self.tests[(id(s), "e")] = (s.test, False)
            self.block(s.body, chain + ((id(s), "b"),))
            self.block(s.orelse, chain + ((id(s), "e"),))
        elif isinstance(s, (ast.With, ast.AsyncWith)):
            for it in s.items:
                self.expr(it.context_expr, chain, none)
                if isinstance(it.optional_vars, ast.Name):
                    self.bind(
                        it.optional_vars.id,
                        _pos(s.body[0]),
                        chain,
                        value=it.context_expr,
                    )
                elif it.optional_vars is not None:
                    for name in _names(it.optional_vars):
                        self.bind(name, _pos(s.body[0]), chain)
            self.block(s.body, chain)
        elif isinstance(s, (ast.Try, ast.TryStar)):
            self.block(s.body, chain + ((id(s), "b"),))
            for i, h in enumerate(s.handlers):
                part = chain + ((id(s), i),)
                self.expr(h.type, chain, none)
                if h.name:
                    self.bind(h.name, _pos(h.body[0]), part)
                self.block(h.body, part)
            self.block(s.orelse, chain + ((id(s), "e"),))
            self.block(s.finalbody, chain + ((id(s), "f"),))
        elif isinstance(s, ast.Match):
            self.expr(s.subject, chain, none)
            for i, c in enumerate(s.cases):
                part = chain + ((id(s), i),)
                for n in ast.walk(c.pattern):
                    for name in (getattr(n, "name", None), getattr(n, "rest", None)):
                        if isinstance(name, str):
                            self.bind(name, _pos(c.body[0]), part)
                self.expr(c.guard, part, none)
                self.block(c.body, part)
        elif isinstance(s, ast.Global):
            self.glob.update(s.names)
        elif isinstance(s, (ast.Import, ast.ImportFrom)):
            plain = isinstance(s, ast.Import)
            frm = None if plain or s.level or not s.module else s.module
            for a in s.names:
                if a.name == "*":
                    if frm:
                        self.stars.append((_end(s), frm))
                    continue
                if plain:  # import a.b binds a, import a.b as c binds c to a.b
                    src = a.name if a.asname else a.name.split(".")[0]
                else:
                    src = frm and f"{frm}.{a.name}"
                name = (a.asname or a.name).split(".")[0]
                self.bind(name, _end(s), chain, imp=True, src=src)
        elif isinstance(s, ast.Delete):
            for t in s.targets:
                for name in _names(t):
                    self.bind(name, _end(s), chain)
        else:
            for e in ast.iter_child_nodes(s):
                if isinstance(e, ast.expr):
                    self.expr(e, chain, none)

    def target(self, t, value, vis, chain):
        """Bind what an assignment target names: x = v, the pairs of a, b = v1, v2, and the items of a, b = v."""
        if isinstance(t, ast.Name):
            self.bind(t.id, vis, chain, value=value)
        elif isinstance(t, (ast.Tuple, ast.List)):
            paired = (
                isinstance(value, (ast.Tuple, ast.List))
                and len(value.elts) == len(t.elts)
                and not any(isinstance(x, ast.Starred) for x in t.elts + value.elts)
            )
            flat = all(isinstance(x, ast.Name) for x in t.elts)
            for i, x in enumerate(t.elts):
                if paired:
                    self.target(x, value.elts[i], vis, chain)
                elif flat:
                    self.bind(x.id, vis, chain, value=value, item=(i, len(t.elts)))
                else:
                    for name in _names(x):
                        self.bind(name, vis, chain)
        elif isinstance(t, ast.Starred):
            for name in _names(t):
                self.bind(name, vis, chain)

    def expr(self, e, chain, shadow):
        """Note the calls, walrus bindings, lambdas and yields of one expression. The variables of a comprehension
        shadow the names of the body inside it (not in its first iterable, which the body around it reads)."""
        todo = [(e, shadow)] if e is not None else []
        while todo:
            n, sh = todo.pop()
            if isinstance(n, ast.Lambda):
                todo += [(d, sh) for _, d in _defaults(n)]
                self.inner.append((n, chain, sh))
                continue
            if isinstance(
                n, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
            ):
                inside = sh | {x for g in n.generators for x in _names(g.target)}
                for i, g in enumerate(n.generators):
                    todo.append((g.iter, inside if i else sh))
                    todo += [(c, inside) for c in g.ifs]
                parts = [n.key, n.value] if isinstance(n, ast.DictComp) else [n.elt]
                todo += [(x, inside) for x in parts]
                continue
            if isinstance(n, ast.Call):
                self.calls.append((n, chain, sh))
                f = n.func
                if (
                    isinstance(f, ast.Attribute)
                    and isinstance(f.value, ast.Name)
                    and f.attr in PIC_PAINTS
                ):
                    self.events.setdefault(f.value.id, []).append(
                        (_pos(n), chain, sh, n)
                    )
                if isinstance(f, ast.Attribute) and f.attr in DRAW_FILLS:
                    self.draws.append((_pos(n), chain, sh, n))
            elif isinstance(n, ast.NamedExpr) and isinstance(n.target, ast.Name):
                self.bind(n.target.id, _end(n), chain, sh, value=n.value)
            elif isinstance(n, (ast.Yield, ast.YieldFrom)):
                self.yields = True
            elif isinstance(n, ast.IfExp):
                self.sides.append((_pos(n.body), _end(n.body), n.test, True))
                self.sides.append((_pos(n.orelse), _end(n.orelse), n.test, False))
            todo += [
                (c, sh)
                for c in ast.iter_child_nodes(n)
                if isinstance(c, (ast.expr, ast.keyword))
            ]


def _encloses(outer, chain):
    """True when the block chain `outer` is `chain` or one of the blocks around it."""
    return chain[: len(outer)] == outer


def _reach(flow, name, pos, chain):
    """The binding of a name in force at pos, inside the block chain: a _Bind, PARAM, FREE when the body never binds
    it, or None when the lint cannot tell. A binding counts only when its block encloses the use; one in a sibling
    branch (also a branch that ends in return, raise, continue or break), a later one in a loop the use sits in, a
    loop variable read after its loop, or a use before any binding leaves the name unknown."""
    rows = flow.binds.get(name, ())
    base = None
    for b in rows:
        if (
            b.vis <= pos
            and _encloses(b.chain, chain)
            and (base is None or b.vis >= base.vis)
        ):
            base = b
    floor = base.vis if base else (-1, -1)
    for b in rows:
        if b is base:
            continue
        if floor < b.vis <= pos and not _encloses(b.chain, chain):
            return None
        if b.vis > pos and any(blk in flow.loops and blk in b.chain for blk in chain):
            return None
    if base is not None:
        # after its loop a loop variable holds the last item the loop reached: not read
        return None if base.body is not None and base.body not in chain else base
    if name in flow.params:
        return PARAM
    return None if rows else FREE


def _single(flow, name):
    """What a nested def or lambda reads for a name of the body around it, whenever it runs: the only binding of the
    name there, PARAM, FREE, or None when it is bound more than once."""
    rows = flow.binds.get(name, ())
    if name in flow.params:
        return None if rows else PARAM
    if not rows:
        return FREE
    return rows[0] if len(rows) == 1 else None


_LEAVES = (ast.Return, ast.Raise, ast.Continue, ast.Break)
# calls an alpha goes through and comes out full where it went in full: int(255 * a), min(a, 1.0), clamp(a)
_KEEPS = {"int", "round", "float", "min", "max", "abs", "clamp"}


def _behind(flow, nodes):
    """The names some expressions are worked out from, through the names the body binds."""
    seen, todo = set(), list(nodes)
    while todo:
        for n in ast.walk(todo.pop()):
            if isinstance(n, ast.Name) and n.id not in seen:
                seen.add(n.id)
                todo += [
                    b.value for b in flow.binds.get(n.id, ()) if b.value is not None
                ]
    return seen


def _feeds(flow, nodes):
    """The parameters of a def that some expressions are worked out from."""
    return _behind(flow, nodes) & flow.params


def _called(call):
    """The last name of what a call calls: clamp for clamp(a) and for E.clamp(a)."""
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)


def _carriers(e):
    """The names an alpha is full with, as written: a for a, int(255 * a), int(255 * a + 0.5), round(a * 255),
    a / 255, min(a, 1.0), clamp(a) and both sides of a choice. None for 0.75 * a, a * b, ease(a) and (t - T0) / D: full there is not
    full here, so a test of a, b or t says nothing about this alpha."""
    out, todo = [], [e]
    while todo:
        n = todo.pop()
        if isinstance(n, ast.Name):
            out.append(n)
        elif isinstance(n, ast.NamedExpr):
            todo.append(n.value)
        elif isinstance(n, ast.IfExp):
            todo += [n.body, n.orelse]
        elif isinstance(n, ast.Call):
            # one value that is not a constant: clamp(a), min(1.0, a), max(0, min(255, a))
            rest = [x for x in n.args if not isinstance(x, ast.Constant)]
            if _called(n) in _KEEPS and not n.keywords and len(rest) == 1:
                todo.append(rest[0])
        elif isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Mult, ast.Div)):
            # the step between 0 to 1 and 0 to 255 is the one scale that keeps full at full
            if _const_in(n.right, (255,)):
                todo.append(n.left)
            elif isinstance(n.op, ast.Mult) and _const_in(n.left, (255,)):
                todo.append(n.right)
        elif (
            isinstance(n, ast.BinOp)
            and isinstance(n.op, (ast.Add, ast.Sub))
            and _const_in(n.right, (0.5, 0.49, 0.499))
        ):
            todo.append(n.left)  # a rounding term: int(255 * a + 0.5)
    return out


def _near(flow, e, alpha=False):
    """The names a test has to read to say how see-through a colour is (or an alpha, with alpha=True): the colour
    itself, the alpha it is written out with ((*c, a): a alone), what the call that makes it is handed (rgba(c, a):
    c and a) and what a name among them is bound to in the body, each alpha through _carriers. A name that only
    reaches the colour through other work (t in rgba(c, ease(t)), out in (*c, int(191 * out))) is not among them."""
    seen, todo = set(), [(e, alpha)]
    while todo:
        n, num = todo.pop()
        if num:
            names = _carriers(n)
        elif _alpha_of(n) is not None:
            names = _carriers(_alpha_of(n))
            num = True
        elif isinstance(n, ast.IfExp):
            todo += [(n.body, False), (n.orelse, False)]
            continue
        elif isinstance(n, ast.NamedExpr):
            todo.append((n.value, False))
            continue
        elif isinstance(n, ast.Call):
            names = [c for x in n.args for c in _carriers(x)]
            names += [c for k in n.keywords for c in _carriers(k.value)]
            num = True
        else:
            names = [n] if isinstance(n, ast.Name) else []
        for name in names:
            if name.id not in seen:
                seen.add(name.id)
                todo += [
                    (b.value, num)
                    for b in flow.binds.get(name.id, ())
                    if b.value is not None
                ]
    return seen


def _first(call):
    """What x.paste(...), x.alpha_composite(...) or x.putalpha(...) is given: its first argument, also by keyword
    (im=, alpha=). None when it is starred or missing."""
    first = (
        call.args[0] if call.args else _keyword(call, "im") or _keyword(call, "alpha")
    )
    return None if isinstance(first, ast.Starred) else first


def _pictures(flow, e):
    """The names a picture goes by in a body, for an ImageDraw or a picture as written: the name itself, the first
    argument of the call that made the ImageDraw (ImageDraw.Draw(lay), pen(lay)) through the names bound to it, and
    every name bound to or from one of those by a plain assignment (tmp = lay). A copy is another picture."""
    out, todo = set(), [e]
    while todo:
        x = todo.pop()
        if isinstance(x, ast.Call):
            x = x.args[0] if x.args else _keyword(x, "im")
        if isinstance(x, ast.Name) and x.id not in out:
            out.add(x.id)
            todo += [
                b.value
                for b in flow.binds.get(x.id, ())
                if isinstance(b.value, (ast.Name, ast.Call))
            ]
    grew = True
    while grew:
        grew = False
        for name, rows in flow.binds.items():
            if name not in out and any(
                isinstance(b.value, ast.Name) and b.value.id in out for b in rows
            ):
                out.add(name)
                grew = True
    return out


def _guards(flow, pos, chain):
    """(test, side) for each if and while test a statement at pos runs under: side True in the body, False in the
    else branch and after an if of an enclosing block whose body ends in return, raise, continue or break. Also for
    the test of each conditional expression pos sits in a side of (x if test else y)."""
    out = [flow.tests[k] for k in chain if k in flow.tests]
    out += [(test, side) for a, b, test, side in flow.sides if a <= pos < b]
    for i in range(len(chain) + 1):
        out += [
            (test, False) for end, test in flow.exits.get(chain[:i], ()) if end <= pos
        ]
    return out


def _is_alpha(e, names):
    """True when an operand of a test is the alpha of the colour: one of its names as _carriers reads them
    (a, int(255 * a)), or the alpha item of the colour itself (c[3], c[-1])."""
    if isinstance(e, ast.Subscript):
        return (
            isinstance(e.value, ast.Name)
            and e.value.id in names
            and (_const_in(e.slice, (3,)) or _const_in(_negated(e.slice), (1,)))
        )
    return any(n.id in names for n in _carriers(e))


def _negated(e):
    """x for -x, else None."""
    if isinstance(e, ast.UnaryOp) and isinstance(e.op, ast.USub):
        return e.operand
    return None


def _confines(test, side, names, number):
    """True when a test, on the side a draw runs under, may hold the draw to opaque colours, so that a helper that
    draws straight on when its colour is opaque and through a layer when it is not is not flagged for the calls
    that take the layer. Two kinds of test do: the alpha against a full number (0.9 to 1, 250 to 255, written out
    or a constant the lint reads) on its full side (if a >= 1, if a == 255, the else of if a < 0.999, the lines
    after if a < 1: ... return), and a call the lint does not read that is handed the colour or its alpha
    (opaque(c), len(c) == 4, isinstance(c, str)). A check that the thing is there (if c, c is not None) or is
    visible (a > 0, a > 0.003), the see-through side of a test (if a < 1) and a test of anything else (if t < T0)
    hold nothing."""
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return _confines(test.operand, not side, names, number)
    if isinstance(test, ast.BoolOp):
        return any(_confines(v, side, names, number) for v in test.values)
    for n in ast.walk(test):
        if (
            isinstance(n, ast.Call)
            and _called(n) not in _KEEPS
            and any(isinstance(x, ast.Name) and x.id in names for x in n.args)
        ):
            return True
    if not isinstance(test, ast.Compare):
        return False
    left = test.left
    for op, right in zip(test.ops, test.comparators):
        pair, left = (left, right), right
        if not isinstance(op, (ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Eq, ast.NotEq)):
            continue
        for i in (0, 1):
            if not _is_alpha(pair[i], names):
                continue
            c = number(pair[1 - i])
            if type(c) not in (int, float) or not (0.9 <= c <= 1 or 250 <= c <= 255):
                continue
            up = isinstance(op, (ast.Lt, ast.LtE) if i else (ast.Gt, ast.GtE))
            if (up or isinstance(op, ast.Eq)) == side:
                return True
    return False


def _asks_mode(test, names):
    """True when a test reads the mode of one of the named pictures or ImageDraws (if img.mode == "RGB")."""
    return any(
        isinstance(n, ast.Attribute)
        and n.attr == "mode"
        and isinstance(n.value, ast.Name)
        and n.value.id in names
        for n in ast.walk(test)
    )


def _alpha_param(flow, colour):
    """The parameters of a def that feed the alpha of a colour it writes out and none of its other items: a in
    rgba(c, a) and hexrgb(h, a). An empty set for mix(c1, c2, k), dim(c, k) and a box helper, whose last item carries
    what the first three do: their colour is not read. None when the alpha reads no parameter at all."""
    rest = colour.elts[:-1] if isinstance(colour, ast.Tuple) else [colour.left]
    mine = _feeds(flow, [_alpha_of(colour)])
    return mine - _feeds(flow, rest) if mine else None


class _Arg:
    """What one call hands one parameter: the argument (or the default), read when the def asks for it, once per
    role, in the body that wrote it. Roles: "val" a picture or an ImageDraw, "col" a colour, "num" an alpha."""

    def __init__(self, pix, expr, at):
        self.pix, self.expr, self.at, self.got = pix, expr, at, {}

    def read(self, role):
        if role not in self.got:
            self.got[role] = None  # an argument that reads itself is unknown
            if not self.pix.guarded_off(self.expr, self.at, _pos(self.expr), role):
                self.got[role] = self.pix.read(self.expr, self.at, role)
        return self.got[role]


class _Open:
    """A parameter of a def that no call the lint follows hands a value (a def nothing in the folder calls, one
    under a decorator): no picture and no colour the lint can name, and as an alpha OPEN: unread by itself, also
    through int(), round(), min() and max(); computed, so see-through, once it is worked on (int(255 * t))."""

    @staticmethod
    def read(role):
        return OPEN if role == "num" else None


class _Env:
    """One body as it is read: its flow, its file, the scope stack qual() needs, the body around it, what the call
    handed its parameters (None when its callers are not followed), the reading it belongs to, and where it is
    written in the body around it (pos, chain, shadow)."""

    def __init__(
        self, kind, flow, scan, stack, outer=None, args=None, entry=None, site=None
    ):
        self.kind, self.flow, self.scan, self.stack = kind, flow, scan, stack
        self.outer, self.args, self.entry, self.site = outer, args, entry, site
        self.cache = {}

    def use(self, name, role):
        """A parameter in one role; the reading remembers it, so a call that hands the same is not read again."""
        a = self.args.get(name) if self.args else None
        v = a.read(role) if a is not None else None
        if self.entry is not None:
            self.entry.used[(name, role)] = v
        return v


class _Entry:
    """One reading of a def: the facts about its parameters it used, what it gave back, the calls that asked."""

    def __init__(self):
        self.used, self.out, self.sites = {}, None, set()


class _Pix:
    """Q1207 over one build folder. study() reads the module-level code of every file, then every def no call in the
    folder names, and from there each def a call reaches, once per different set of facts the calls hand it; rows()
    gives the findings. A position `at` is (env, block chain, comprehension variables)."""

    def __init__(self, scans, engine):
        # sorted, so the same folder gives the same findings whatever the order of its import lines
        self.scans = sorted(scans, key=lambda sc: sc.path.name)
        self.mods = {sc.path.stem: sc for sc in self.scans}
        # files read for what their defs return and never reported on: the engine
        self.readers = set()
        if engine.exists() and engine.stem not in self.mods:
            self.mods[engine.stem] = _Scan(engine)
            self.readers.add(engine.stem)
        self.defs, self.globs = {}, {}
        for stem, sc in self.mods.items():
            body = sc.tree.body
            for s in body:  # only a def written straight in the module is followed by name; the last one wins
                if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self.defs[(stem, s.name)] = (sc, s)
            self.globs[stem] = {
                x
                for n in ast.walk(sc.tree)
                if isinstance(n, ast.Global)
                for x in n.names
            }
        # what `from module import *` brings when the module names it: __all__ written out as a list or a tuple
        self.alls = {}
        for stem, sc in self.mods.items():
            for s in sc.tree.body:
                if (
                    isinstance(s, ast.Assign)
                    and any(
                        isinstance(x, ast.Name) and x.id == "__all__" for x in s.targets
                    )
                    and isinstance(s.value, (ast.List, ast.Tuple))
                ):
                    self.alls[stem] = {
                        x.value for x in s.value.elts if isinstance(x, ast.Constant)
                    }
        # module-level names another file assigns through the module (look.GLASS_A = 255)
        self.poked = set()
        for sc in self.mods.values():
            for n in ast.walk(sc.tree):
                if (
                    isinstance(n, ast.Attribute)
                    and not isinstance(n.ctx, ast.Load)
                    and isinstance(n.value, ast.Name)
                    and sc.alias.get(n.value.id) in self.mods
                ):
                    self.poked.add((sc.alias[n.value.id], n.attr))
        self.flows, self.scopes, self.modules, self.changed = {}, {}, {}, None
        self.shaky = {}
        self.memo, self.active, self.busy = {}, set(), set()
        self.left, self.depth, self.capped = STEPS, 0, False
        self.hits = {}

    # ---- bodies ----

    def flow(self, node):
        if id(node) not in self.flows:
            self.flows[id(node)] = _Flow(node)
        return self.flows[id(node)]

    def scope(self, scan, fn, stack):
        """The _Scope of a def or lambda, as _Scan.visit builds it: qual() and the pragma lines of add() need it."""
        if id(fn) not in self.scopes:
            sc = self.scopes[id(fn)] = _Scope(fn)
            body = fn.body if isinstance(fn.body, list) else [ast.Expr(fn.body)]
            sc.aliases, sc.draws, sc.mask_draws, sc.masks = scan.facts(
                body, stack + [sc]
            )
        return self.scopes[id(fn)]

    def module(self, scan):
        stem = scan.path.stem
        if stem not in self.modules:
            self.modules[stem] = _Env("module", self.flow(scan.tree), scan, [])
        return self.modules[stem]

    def nested(self, env, node, chain, shadow):
        """The body of a class, def or lambda written inside env. Its own parameters are not followed."""
        site = (_pos(node), chain, shadow)
        if isinstance(node, ast.ClassDef):
            return _Env("class", self.flow(node), env.scan, env.stack, env, site=site)
        stack = env.stack + [self.scope(env.scan, node, env.stack)]
        return _Env("def", self.flow(node), env.scan, stack, env, site=site)

    def top(self, env, node):
        """The (module, name) of a def written straight in its module, when calls are followed into it by name."""
        key = (env.scan.path.stem, getattr(node, "name", None))
        return (
            key
            if env.kind == "module" and self.defs.get(key, (None, None))[1] is node
            else None
        )

    # ---- names ----

    def qual(self, e, env):
        """scan.qual, then through what a folder module itself imports: E.ImageDraw.Draw is PIL.ImageDraw.Draw, and
        kit.canvas is engine.canvas when kit star-imports the engine. None for a path whose first name the module
        binds more than once (D = ImageDraw.Draw, then D = partial(...); an import that a def of the same name
        follows), unless every binding is the same import."""
        root = e
        while isinstance(root, ast.Attribute):
            root = root.value
        if isinstance(root, ast.Name):
            rows = self.module(env.scan).flow.binds.get(root.id, ())
            again = len(rows) > 1 and not (
                all(b.imp for b in rows) and len({b.src for b in rows}) == 1
            )
            if again:
                return None  # bound again in its module: not sure to be what its first binding names
        q = env.scan.qual(e, env.stack)
        for _ in range(4):
            parts = (q or "").split(".")
            sc = self.mods.get(parts[0])
            if (
                sc is None
                or len(parts) < 2
                or parts[1] in sc.top
                or parts[1] not in sc.alias
            ):
                break
            q = ".".join([sc.alias[parts[1]]] + parts[2:])
        return q

    def lookup(self, name, pos, at):
        """What a name stands for where it is used: ("bind", binding, env), ("arg", env, name) for a parameter, or
        None when the lint cannot tell. The body holding the use reads its names by position (_reach); a def or
        lambda nested in a body reads the names of that body whenever it runs (_single); a name of the module is
        read as the module leaves it, except by module-level code, which reads it at its own line."""
        env, chain, shadow = at
        if name in shadow:
            return None  # the variable of a comprehension
        here = True
        while env.kind != "module":
            flow = env.flow
            if name in flow.nonloc:
                return None
            if name in flow.glob:
                env, here = self.module(env.scan), False
                break
            if env.kind == "class" and not here:
                env = env.outer  # a method does not see the names of its class body
                continue
            got = _reach(flow, name, pos, chain) if here else _single(flow, name)
            if got is None:
                return None
            if got is PARAM:
                return ("arg", env, name)
            if got is not FREE:
                if got.imp:
                    return self.dotted(got.src)
                return ("bind", got, env)
            if env.site is None:
                here = False  # a def followed from a call: the module has run by then
            else:
                if name in env.site[2]:
                    return None
                if env.kind == "class":  # a class body runs where it is written
                    pos, chain = env.site[:2]
                else:
                    here = False
            env = env.outer
        return self.at_module(env, name, pos if here else INF, chain if here else (), 0)

    def at_module(self, env, name, pos, chain, depth):
        """A name of a module at pos: its binding there, or what a star import of a folder module brings under that
        name (also through a module that star-imports another); where both give the name, the later one wins, as
        in Python. Unknown: a name a function rebinds through `global`, one another file assigns through the module
        (look.GLASS_A = 255), and one the module binds again after its code made a call (unsettled)."""
        stem, flow = env.scan.path.stem, env.flow
        if name in self.globs[stem] or (stem, name) in self.poked:
            return None
        got = _reach(flow, name, pos, chain)
        if got is None or (pos == INF and self.unsettled(flow, name)):
            return None
        if not name.startswith("_"):
            for vis, mod in reversed(flow.stars):
                only = self.alls.get(
                    mod
                )  # a star import brings what __all__ names, when the module has one
                if only is not None and name not in only:
                    continue
                if vis <= pos and (got is FREE or got.vis < vis):
                    hit = self.dotted(f"{mod}.{name}", depth + 1)
                    if hit:
                        return hit
        if got is FREE:
            return None
        return self.dotted(got.src, depth + 1) if got.imp else ("bind", got, env)

    def unsettled(self, flow, name):
        """True when a module binds a name again after its code has called a def of the build (by name, or through
        something that is not a name): a def that ran at import (TILE = edged_tile()) read the earlier binding, so
        the name as the module leaves it is not what every def saw."""
        key = (id(flow), name)
        if key not in self.shaky:
            rows = sorted(b.vis for b in flow.binds.get(name, ()) if not b.chain)
            own = {k[1] for k in self.defs if k[0] not in self.readers}

            def runs(f):
                called = getattr(f, "id", getattr(f, "attr", None))
                return called is None or called in own

            self.shaky[key] = len(rows) > 1 and any(
                rows[0] <= _pos(c[0]) < rows[-1] and runs(c[0].func) for c in flow.calls
            )
        return self.shaky[key]

    def dotted(self, q, depth=0):
        """("bind", binding, env) for module.NAME when module is a folder module or the engine, following a name that
        module itself imports; None for any other path."""
        mod, _, name = (q or "").rpartition(".")
        scan = self.mods.get(mod)
        if scan is None or depth > 4:
            return None
        return self.at_module(self.module(scan), name, INF, (), depth)

    def bound(self, hit, role):
        """What lookup found, read in one role."""
        if hit is None:
            return None
        if hit[0] == "arg":
            return hit[1].use(hit[2], role)
        _, b, env = hit
        key = (id(b), role)
        if key not in env.cache:
            env.cache[key] = None  # a = b with b = a is unknown
            at = (env, b.chain, b.shadow)
            if b.value is None:
                out = self.loose(b, at) if role == "num" else None
            elif b.item is not None:
                out = self.item(b, at, role)
            else:
                out = self.read(b.value, at, role)
            env.cache[key] = out
        return env.cache[key]

    def item(self, b, at, role):
        """One name of an unpacking: a picture or an ImageDraw out of a tuple a def returns (img, d = stage(t)). As an
        alpha: the item of a tuple written out (lo, hi = ALPHAS), the alpha of a colour unpacked into four names
        (r, g, b, a = hexrgb(c)), and what a call worked out (a, xy = state(t)), which is computed."""
        i, n = b.item
        if role == "val":
            v = self.value(b.value, at)
            return v[1][i] if v and v[0] == "tup" and len(v[1]) == n else None
        if role != "num":
            return None
        shown = self.display(b.value, at)
        if (
            shown
            and isinstance(shown[0], (ast.Tuple, ast.List))
            and len(shown[0].elts) == n
        ):
            return self.number(shown[0].elts[i], shown[1])
        if (i, n) == (3, 4):
            alphas = {
                "opaque": 255,
                "clear": 0,
                "see": VAR,
                "solid": frozenset((0, 255)),
            }
            return alphas.get(self.colour(b.value, at))
        if isinstance(b.value, ast.Call):
            # what a call worked out: computed as soon as one argument is not a constant, whatever the others are
            # (name, lt, _ = scene_at(t, SCHEDULE)); unread when only constants go in (col, a = style())
            vals = [self.number(x, at) for x in b.value.args]
            vals += [self.number(k.value, at) for k in b.value.keywords]
            return VAR if any(v is VAR or v is OPEN for v in vals) else None
        return None

    def display(self, e, at, depth=0):
        """(display, where) for a tuple, a list or a dict written out (also dict(soft=...)), or a name bound to one,
        also in a folder module; else None. A list or a dict under a name whose object something in the folder may
        change after it is written (touched: a cache, a palette another file tunes) is not read."""
        if isinstance(e, (ast.Tuple, ast.List)):
            return None if any(isinstance(x, ast.Starred) for x in e.elts) else (e, at)
        if isinstance(e, ast.Dict):
            return (e, at) if all(isinstance(k, ast.Constant) for k in e.keys) else None
        if isinstance(e, ast.Call):
            f = e.func
            plain = isinstance(f, ast.Name) and f.id == "dict" and not e.args
            if (
                plain
                and all(k.arg for k in e.keywords)
                and self.lookup("dict", _pos(f), at) is None
            ):
                return (e, at)
            return None
        if depth < 3 and isinstance(e, (ast.Name, ast.Attribute)):
            hit = (
                self.lookup(e.id, _pos(e), at)
                if isinstance(e, ast.Name)
                else self.dotted(self.qual(e, at[0]))
            )
            if (
                hit
                and hit[0] == "bind"
                and hit[1].value is not None
                and hit[1].item is None
            ):
                where = (hit[2], hit[1].chain, hit[1].shadow)
                shown = self.display(hit[1].value, where, depth + 1)
                name = e.id if isinstance(e, ast.Name) else e.attr
                fixed = shown and isinstance(shown[0], ast.Tuple)
                return shown if fixed or name not in self.touched() else None
        return None

    def picked(self, e, at):
        """(item, where) for X[key] when X is a display (see display) and key a constant: the item at that place of
        a tuple or a list, the value under that key of a dict. None for any other subscript."""
        shown, key = self.display(e.value, at), e.slice
        if not shown or not isinstance(key, ast.Constant):
            return None
        node, k = shown[0], key.value
        if isinstance(node, ast.Dict):
            got = [v for x, v in zip(node.keys, node.values) if x.value == k]
        elif isinstance(node, ast.Call):
            got = [x.value for x in node.keywords if x.arg == k]
        else:
            n = len(node.elts)
            got = [node.elts[k]] if type(k) is int and -n <= k < n else []
        return (got[-1], shown[1]) if got else None

    def guarded(self, e, read, got):
        """read(*got), unless the reading of e is already under way (A = (A[0], 1)): then None."""
        if id(e) in self.busy:
            return None
        self.busy.add(id(e))
        try:
            return read(*got)
        finally:
            self.busy.discard(id(e))

    def read(self, e, at, role):
        if role == "val":
            return self.value(e, at)
        return self.colour(e, at) if role == "col" else self.number(e, at)

    # ---- pictures and ImageDraws ----

    def value(self, e, at):
        """What an expression is when it is a picture, an ImageDraw or a tuple holding one: ("pic", mode) with mode
        "RGB", "RGBA" (an RGBA picture read as opaque), "LAYER" (an RGBA picture that starts transparent or
        see-through) or "MASK"; ("pen", asked, mode) for an ImageDraw on a picture of that mode, asked True when it
        was made with the "RGBA" mode, False when plain, None when its mode cannot be read; ("tup", items); None for
        anything the lint cannot read (an opened file, an item of a cache, an attribute of an object)."""
        if isinstance(e, (ast.NamedExpr, ast.Await)):
            return self.value(e.value, at)
        if isinstance(e, ast.IfExp):
            return _same(self.value(e.body, at), self.value(e.orelse, at))
        if isinstance(e, ast.Name):
            hit = self.lookup(e.id, _pos(e), at)
            v = self.bound(hit, "val")
            if v and v[0] == "pic":
                # a parameter is in force from the top of its def
                home, since = (
                    (hit[2], hit[1].vis) if hit[0] == "bind" else (hit[1], (0, 0))
                )
                same = home is at[0]
                v = self.painted(
                    v,
                    e.id,
                    home,
                    since,
                    _pos(e) if same else INF,
                    at[1] if same else (),
                )
            return v
        if isinstance(e, ast.Attribute):
            return self.bound(self.dotted(self.qual(e, at[0])), "val")
        if isinstance(e, ast.Tuple):
            if any(isinstance(x, ast.Starred) for x in e.elts):
                return None
            return ("tup", tuple(self.value(x, at) for x in e.elts))
        if isinstance(e, ast.Subscript):
            v, i = self.value(e.value, at), e.slice
            if v and v[0] == "tup":  # stage(t)[0], pens[1]
                one = isinstance(i, ast.Constant) and type(i.value) is int
                return (
                    v[1][i.value] if one and -len(v[1]) <= i.value < len(v[1]) else None
                )
            # BASE[name], a table of pictures
            return self.guarded(e, self.shelved, (e, at))
        return self.made_by(e, at) if isinstance(e, ast.Call) else None

    def made_by(self, e, at):
        """The picture or ImageDraw a call makes."""
        env, f = at[0], e.func
        q = self.qual(f, env)
        if q == "PIL.Image.new":
            mode = self.new_mode(e, at)
            return ("pic", mode) if mode else None
        if q == "PIL.Image.fromarray":
            # the alpha channel of an array is not read, so only a mode without one says what the picture is
            mode = _mode_name(e.args[1] if len(e.args) > 1 else _keyword(e, "mode"))
            return ("pic", mode) if mode in ("RGB", "MASK") else None
        if q == "PIL.Image.alpha_composite" and len(e.args) == 2:
            a, b = self.value(e.args[0], at), self.value(e.args[1], at)
            if ("pic", "RGBA") in (a, b):
                return ("pic", "RGBA")  # opaque under or over: opaque
            return a if a == b == ("pic", "LAYER") else None
        if q in PIC_MIX and len(e.args) >= 2:
            a, b = self.value(e.args[0], at), self.value(e.args[1], at)
            return a if a == b and a and a[0] == "pic" else None
        if q in DRAW_CALLS:
            return self.pen(e, at)
        keys, whole = self.callees(f, at)
        if keys:
            outs = [self.enter(k, e, at, "val") for k in keys]
            out = outs[0]
            for o in outs[1:]:
                out = _same(out, o)
            return out if whole else None
        if isinstance(f, ast.Attribute):
            if f.attr == "convert":
                made = _mode_name(e.args[0] if e.args else _keyword(e, "mode"))
                if made != "RGBA":
                    return ("pic", made) if made else None
                # converting neither adds transparency nor takes it away
                under = self.value(f.value, at)
                if under and under[0] == "pic":
                    return under if under[1] == "LAYER" else ("pic", "RGBA")
                return None
            if f.attr in PIC_SAME:
                under = self.value(f.value, at)
                return under if under and under[0] == "pic" else None
        return None

    def new_mode(self, call, at):
        """What Image.new makes: "MASK", "RGB", "LAYER" (an RGBA picture that starts transparent or see-through: no
        colour given, or one read as clear or see-through) or "RGBA" (a start colour read as opaque). None when the
        mode or the start colour cannot be read (a parameter nobody passes, a subscript, an attribute of an object,
        arithmetic): a picture that may be a layer is never taken for an opaque one."""
        if any(isinstance(x, ast.Starred) for x in call.args) or any(
            k.arg is None for k in call.keywords
        ):
            return None
        mode = _mode_name(call.args[0] if call.args else _keyword(call, "mode"))
        if mode != "RGBA":
            return mode
        colour = call.args[2] if len(call.args) > 2 else _keyword(call, "color")
        if colour is None or (
            isinstance(colour, ast.Constant) and colour.value is None
        ):
            return "LAYER"
        return {"opaque": "RGBA", "clear": "LAYER", "see": "LAYER"}.get(
            self.colour(colour, at)
        )

    def pen(self, call, at):
        """("pen", asked, mode) for ImageDraw.Draw(img[, mode]) on a picture whose mode is read, else None."""
        pic = call.args[0] if call.args else _keyword(call, "im")
        if pic is None or isinstance(pic, ast.Starred):
            return None
        v = self.value(pic, at)
        if not v or v[0] != "pic":
            return None
        how = call.args[1] if len(call.args) > 1 else _keyword(call, "mode")
        if isinstance(
            how, ast.Name
        ):  # MODE = "RGBA" bound above; a loop variable or a parameter is unread
            got = self.fixed(how, at)
            how = ast.Constant(value=got[0]) if got else how
        if how is None:
            asked = False
        elif isinstance(how, ast.Constant):
            asked = how.value == "RGBA"
        elif isinstance(how, ast.Attribute) and how.attr == "mode":
            under = self.value(how.value, at)  # ImageDraw.Draw(img, img.mode)
            asked = (
                under[1] in ("RGBA", "LAYER") if under and under[0] == "pic" else None
            )
        else:
            asked = None
        return ("pen", asked, v[1])

    def painted(self, v, name, env, since, pos, chain):
        """A picture after what was done to it in place between its binding (or, for a parameter, the top of its
        def) and a use at pos (after() reads each paste, alpha_composite and putalpha). A change the use may or may
        not have run through (in a sibling branch, later in a loop the use sits in) leaves the picture unknown."""
        flow, mode = env.flow, v[1]
        for when, ch, sh, call in flow.events.get(name, ()):
            later = when >= pos
            if when < since or mode == "MASK":
                continue
            if later and not any(k in flow.loops and k in ch for k in chain):
                continue
            new = self.after(mode, call, (env, ch, sh))
            if new != mode:
                if new is None or later or not _encloses(ch, chain):
                    return None
                mode = new
        return ("pic", mode)

    def after(self, mode, call, at):
        """The mode of a LAYER, RGBA or RGB picture after one in-place change, None when it is unknown from there.
        putalpha(255) makes it opaque; any other putalpha leaves a picture that was opaque unknown. An opaque
        picture pasted or composited into a layer from its corner, with no box and no mask, makes the layer an
        opaque picture when it is read to cover it (covers) and leaves it unknown when it is not (a photo at the
        corner of a card); a layer pasted over an opaque picture that way goes by the same test. A colour read as
        clear or see-through pasted into a part of an opaque picture (paste(CLEAR, box)) leaves it unknown; any
        other paste into a part leaves the picture what it was."""
        what, first = call.func.attr, _first(call)
        # the alpha channel replaced; an RGB picture turns RGBA in place
        if what == "putalpha":
            if first is not None and _const_in(first, (255,)):
                return "RGBA"
            return mode if mode == "LAYER" else None
        if mode == "RGB" or id(call) in self.busy or first is None:
            return mode
        whole = self.whole(call)
        if not whole and (what == "alpha_composite" or mode == "LAYER"):
            return mode  # over a part of it: an opaque picture stays opaque, a layer stays read as a layer
        self.busy.add(id(call))
        try:
            src = self.value(first, at)
            if not whole:
                return None if self.clears(call, first, src, at) else mode
            opaque = src in (("pic", "RGBA"), ("pic", "RGB"), ("pic", "MASK"))
            if opaque:
                return "RGBA" if mode == "RGBA" or self.covers(call, at) else None
            if what == "paste" and src == ("pic", "LAYER"):
                return "LAYER" if mode == "LAYER" or self.covers(call, at) else None
        finally:
            self.busy.discard(id(call))
        # a layer or something unread over a layer; something unread pasted over an opaque picture
        return mode if what == "alpha_composite" or mode == "LAYER" else None

    def clears(self, call, first, src, at):
        """True when x.paste(first, ...) into a part of an opaque picture may leave clear pixels there: a colour read
        as clear or see-through, or a picture read as a layer pasted with no mask (with the layer as its own mask
        only its painted pixels go in)."""
        if src and src[0] == "pic":
            masked = len(call.args) > 2 or _keyword(call, "mask") is not None
            return src[1] == "LAYER" and not masked
        return self.colour(first, at) in ("clear", "see")

    def covers(self, call, at):
        """True when the picture x.paste(im) or x.alpha_composite(im) puts into x is read to cover it whole: the
        engine's own frame (what canvas() and gradient() return), or a picture as large as x as far as the lint
        reads sizes (span)."""
        src = self.span(_first(call), at, 0)
        return src is not None and (
            src == "frame" or src == self.span(call.func.value, at, 0)
        )

    def span(self, e, at, depth):
        """What says how large a picture is, to tell whether one covers another: "frame" for what the engine's
        canvas() and gradient() return, the size as written for Image.new(mode, size) and x.resize(size) (the
        other picture for other.size), the binding itself for a picture handed in or one made some other way;
        through names, copies, filters and converts. None when the lint cannot name it."""
        if depth > 6:
            return None
        if isinstance(e, ast.Name):
            hit = self.lookup(e.id, _pos(e), at)
            if not hit:
                return None
            if hit[0] == "arg":
                return ("arg", id(hit[1]), hit[2])
            b = hit[1]
            if b.value is None or b.item is not None:
                return ("bind", id(b))
            return self.span(b.value, (hit[2], b.chain, b.shadow), depth + 1) or (
                "bind",
                id(b),
            )
        if not isinstance(e, ast.Call):
            return None
        f = e.func
        if self.qual(f, at[0]) == "PIL.Image.new":
            size = e.args[1] if len(e.args) > 1 else _keyword(e, "size")
            return self.extent(size, at, depth)
        if isinstance(f, ast.Attribute) and f.attr == "resize":
            return self.extent(e.args[0] if e.args else _keyword(e, "size"), at, depth)
        if isinstance(f, ast.Attribute) and f.attr in ("copy", "filter", "convert"):
            return self.span(f.value, at, depth + 1)
        keys, whole = self.callees(f, at)
        if (
            whole
            and keys
            and all(
                k[0] in self.readers and k[1] in ("canvas", "gradient") for k in keys
            )
        ):
            return "frame"
        return None

    def extent(self, size, at, depth):
        """A size as span() names it: the picture for other.size, else the expression as it is written."""
        if size is None or isinstance(size, ast.Starred):
            return None
        if isinstance(size, ast.Attribute) and size.attr == "size":
            return self.span(size.value, at, depth + 1)
        names = []  # the same words are the same size only when each name in them is the same binding
        for n in ast.walk(size):
            if isinstance(n, ast.Name):
                hit = self.lookup(n.id, _pos(n), at)
                if not hit:
                    return None
                names.append(id(hit[1]) if hit[0] == "bind" else (id(hit[1]), hit[2]))
        return ("size", ast.dump(size), tuple(names))

    @staticmethod
    def whole(call):
        """True when x.paste(im) or x.alpha_composite(im) starts at the corner of x: no box (or (0, 0)), no mask."""
        if not call.args or call.keywords or isinstance(call.args[0], ast.Starred):
            return False
        rest = call.args[1:]
        return not rest or (
            len(rest) == 1
            and isinstance(rest[0], ast.Tuple)
            and len(rest[0].elts) == 2
            and all(_const_in(x, (0,)) for x in rest[0].elts)
        )

    # ---- colours and alphas ----

    def colour(self, e, at):
        """How see-through a colour is, as written: "see" (an alpha that is neither 0 nor 255, or is computed),
        "opaque", "clear" (alpha 0: an erase, or what a layer starts as), "solid" (opaque or clear by a choice), None
        when the lint cannot read it (an item it cannot place in a table, an attribute of an object, a format
        string)."""
        if isinstance(e, ast.NamedExpr):
            return self.colour(e.value, at)
        if isinstance(e, ast.Constant):
            if isinstance(e.value, str):
                return _hex_alpha(e.value)
            return "clear" if type(e.value) is int and e.value == 0 else None
        if isinstance(e, ast.IfExp):
            return _either(self.colour(e.body, at), self.colour(e.orelse, at))
        if isinstance(e, ast.Name):
            return self.bound(self.lookup(e.id, _pos(e), at), "col")
        if isinstance(e, ast.Attribute):
            return self.bound(self.dotted(self.qual(e, at[0])), "col")
        if isinstance(e, (ast.Tuple, ast.BinOp)):
            if isinstance(e, ast.Tuple) and len(e.elts) == 3:
                return (
                    None
                    if any(isinstance(x, ast.Starred) for x in e.elts)
                    else "opaque"
                )
            alpha = _alpha_of(e)
            if alpha is not None:
                n = self.arity(e, at)
                if n is not None and n != 4:
                    return (
                        "opaque" if n == 3 else None
                    )  # (*WARM, b) with WARM = (240, 120)
                return _alpha_class(self.number(alpha, at))
            if isinstance(e, ast.BinOp) and isinstance(e.op, ast.Mult):  # (0,) * 4
                one, n = (
                    (e.left, e.right)
                    if isinstance(e.left, ast.Tuple)
                    else (e.right, e.left)
                )
                if (
                    isinstance(one, ast.Tuple)
                    and len(one.elts) == 1
                    and not isinstance(one.elts[0], ast.Starred)
                    and isinstance(n, ast.Constant)
                    and n.value in (3, 4)
                ):
                    return (
                        "opaque"
                        if n.value == 3
                        else _alpha_class(self.number(one.elts[0], at))
                    )
            return None
        if isinstance(e, ast.Subscript):
            s = e.slice
            if (  # c[:3]: a colour without its alpha
                isinstance(s, ast.Slice)
                and s.step is None
                and (s.lower is None or _const_in(s.lower, (0,)))
                and _const_in(s.upper, (3,))
            ):
                return "opaque"
            # SHADES[0], PAL["soft"]: an item at a constant place of a table of colours written out
            got = self.picked(e, at)
            return self.guarded(e, self.colour, got) if got else None
        if isinstance(e, ast.Call):
            keys, whole = self.callees(e.func, at)
            if keys:
                out = None if not whole else self.enter(keys[0], e, at, "col")
                for k in keys[1:] if whole else keys:
                    out = _either(out, self.enter(k, e, at, "col"))
                return out
            # a helper the lint cannot read, given alpha 0 last (rgba(c, 0)): an erase
            last = (
                e.args[-1]
                if len(e.args) > 1
                else next(
                    (k.value for k in e.keywords if k.arg in ("a", "alpha", "opacity")),
                    None,
                )
            )
            return "clear" if last is not None and _const_in(last, (0,)) else None
        return None

    def arity(self, e, at):
        """How many items a colour written with a starred part or a concatenation has, when the lint reads each part:
        a tuple or a list written out, a name bound to one, c[:3]. None when a part is unread (then the colour is
        taken as written: four items, the last its alpha)."""

        def length(x):
            s = x.slice if isinstance(x, ast.Subscript) else None
            if (
                isinstance(s, ast.Slice)
                and s.step is None
                and (s.lower is None or _const_in(s.lower, (0,)))
                and _const_in(s.upper, (3,))
            ):
                return 3
            shown = self.display(x, at)
            ok = shown and isinstance(shown[0], (ast.Tuple, ast.List))
            return len(shown[0].elts) if ok else None

        if isinstance(e, ast.Tuple):
            parts = [
                length(x.value) if isinstance(x, ast.Starred) else 1 for x in e.elts
            ]
        else:
            parts = [length(e.left), length(e.right)]
        return None if None in parts else sum(parts)

    def number(self, e, at):
        """An alpha as written: the number it folds to (through names bound to constants, also in a folder module,
        what a call hands a parameter and what a folder def returns for its arguments), a frozenset of numbers when
        a choice picks one of them (255 if on else 0), VAR when it is computed from values that are not constants
        (int(255 * t)), None when the lint cannot read it (an item it cannot place in a table, an attribute of an
        object)."""
        if isinstance(e, ast.Constant):
            return e.value if type(e.value) in (int, float) else None
        if isinstance(e, ast.NamedExpr):
            return self.number(e.value, at)
        if isinstance(e, ast.Name):
            return self.bound(self.lookup(e.id, _pos(e), at), "num")
        if isinstance(e, ast.Attribute):
            q = self.qual(e, at[0])
            if type(_MATH.get(q)) is float:
                return _MATH[q]  # math.pi
            return self.bound(self.dotted(q), "num")
        if isinstance(e, ast.Subscript):
            # SHADE[3], PAL["a"]: an item at a constant place of a table written out; any other is unread
            got = self.picked(e, at)
            return self.guarded(e, self.number, got) if got else None
        if isinstance(e, ast.IfExp):
            return _one_of(self.number(e.body, at), self.number(e.orelse, at))
        if isinstance(e, ast.UnaryOp) and isinstance(e.op, (ast.USub, ast.UAdd)):
            sign = -1 if isinstance(e.op, ast.USub) else 1
            return _spread(lambda v: sign * v, self.number(e.operand, at))
        if isinstance(e, ast.Compare) or (
            isinstance(e, ast.UnaryOp) and isinstance(e.op, ast.Not)
        ):
            return _ON_OFF  # True or False: 255 * (i == active) is 0 or 255
        if isinstance(e, ast.BinOp):
            a, b = self.number(e.left, at), self.number(e.right, at)
            fold = _FOLDS.get(type(e.op))
            if fold:
                return _spread(fold, a, b)
            # an operator the lint does not fold: computed when a value that is not a constant goes in
            return VAR if _varies(a, b) else None
        if isinstance(e, ast.Call):
            f = e.func
            keys, whole = self.callees(f, at)
            # a def of the build or the engine: what it returns for these arguments
            if keys:
                out = self.enter(keys[0], e, at, "num") if whole else None
                for k in keys[1:]:
                    out = _one_of(out, self.enter(k, e, at, "num"))
                return out
            if any(isinstance(x, ast.Starred) for x in e.args):
                return None
            # int, round, min and bool as Python has them, not a name of the build
            builtin = isinstance(f, ast.Name) and self.lookup(f.id, _pos(f), at) is None
            if builtin and f.id == "bool":
                return _ON_OFF
            vals = [self.number(x, at) for x in e.args]
            vals += [self.number(k.value, at) for k in e.keywords]
            if builtin and f.id in _CALLS and vals and not e.keywords:
                if any(v is OPEN for v in vals) and all(
                    v is OPEN or type(v) in (int, float) for v in vals
                ):
                    return OPEN  # int(a), min(a, 255): still what the caller hands it
                return _spread(_CALLS[f.id], *vals)
            pure = _MATH.get(self.qual(f, at[0]))
            if callable(pure) and vals and not e.keywords:
                return _spread(pure, *vals)  # math.sqrt(2 * H / G), np.uint8(255)
            # any other call works its value out: computed when a value that is not a constant goes in
            # (ease(t)), unread when an argument is (lerp(c1[3], c2[3], k)) or when only constants go in
            # (math.floor(255.0), current_alpha())
            return VAR if _varies(*vals) else None
        return None

    def loose(self, b, at):
        """The alpha held by a name that no single expression is bound to: computed after x += 1 and for the counter
        of a loop over range() or enumerate(); one of the items for a loop over numbers written out; else unread."""
        if b.aug:
            return VAR
        if b.iter is None:
            return None
        it, pick = b.iter
        f = it.func if isinstance(it, ast.Call) else None
        if isinstance(f, ast.Name) and self.lookup(f.id, _pos(f), at) is None:
            if f.id == "range" and pick is None:
                return VAR
            if f.id == "enumerate" and it.args and pick in (0, 1):
                if pick == 0:
                    return VAR
                it, pick = it.args[0], None
        if pick is not None:
            return None
        shown = self.display(it, at)
        if (
            not shown
            or not isinstance(shown[0], (ast.Tuple, ast.List))
            or not shown[0].elts
        ):
            return None
        out = self.number(shown[0].elts[0], shown[1])
        for x in shown[0].elts[1:]:
            out = _one_of(out, self.number(x, shown[1]))
        return out

    # ---- calls ----

    def callees(self, f, at, depth=0):
        """([(module, def)], whole) for what a call names: a def written straight in this file, in a folder module or
        in the engine, by name, through a name bound to it (hud = scene_hud), or the defs a module-level table
        holds for TABLE[key](...), TABLE.get(key)(...) and a loop variable over the table: the one entry a constant
        key names, else every entry. whole is False when part of what the call may reach is unread (a lambda in the
        table, a callback handed in)."""
        if depth > 6:
            return [], False
        if isinstance(f, ast.Name):
            return self.held(self.lookup(f.id, _pos(f), at), depth)
        if isinstance(f, ast.Attribute):
            return self.held(self.dotted(self.qual(f, at[0])), depth)
        if isinstance(f, ast.Subscript):
            return self.table(f.value, at, None, depth + 1, self.keyed(f.slice, at))
        if (
            isinstance(f, ast.Call)
            and isinstance(f.func, ast.Attribute)
            and f.func.attr == "get"
            and f.args
            and not f.keywords
        ):
            key = self.keyed(f.args[0], at)
            keys, whole = self.table(f.func.value, at, None, depth + 1, key)
            if len(f.args) > 1 and not (
                isinstance(f.args[1], ast.Constant) and f.args[1].value is None
            ):
                more, sure = self.callees(f.args[1], at, depth + 1)
                keys, whole = keys + [k for k in more if k not in keys], whole and sure
            return keys, whole
        return [], False

    def held(self, hit, depth):
        """The defs a binding found by lookup or dotted holds."""
        if not hit or hit[0] != "bind":
            return [], False
        _, b, env = hit
        if b.fn is not None:
            key = self.top(env, b.fn)
            return ([key], True) if key and not self.wrapped(env, b.fn) else ([], False)
        at = (env, b.chain, b.shadow)
        if b.iter is not None:
            return self.table(b.iter[0], at, b.iter[1], depth + 1, loop=True)
        if b.value is not None and b.item is None:
            return self.callees(b.value, at, depth + 1)
        return [], False

    def wrapped(self, env, fn):
        """True when a def sits under a decorator that may hand it other arguments than the call's own (a wrapper
        that gives it a fresh layer and composites): any but functools.lru_cache and functools.cache. Calls are
        not followed into such a def; it is read like a def that nothing calls."""
        return any(
            self.qual(d.func if isinstance(d, ast.Call) else d, env) not in _PLAIN
            for d in fn.decorator_list
        )

    def table(self, e, at, pick, depth, key=None, loop=False):
        """The defs a table holds (see shelf), each as callees() names it."""
        items, where, whole = self.shelf(e, at, pick, depth, key, loop)
        keys = []
        for x in items:
            more, sure = self.callees(x, where, depth + 1)
            keys, whole = keys + [k for k in more if k not in keys], whole and sure
        return keys, whole

    def shelf(self, e, at, pick, depth, key=None, loop=False):
        """(items, where, whole) for what a table holds. e is the table as written or a name bound to it: a dict
        display or dict(...) call (its values), a list, tuple or set display (its items), X.values() and X.items()
        in a loop. pick is the place of a loop variable in each item (for name, fn in X.items(): 1); key is the
        subscript of X[key] or the argument of X.get(key), which names one entry when it and the keys of a dict
        display are constants (fixed). whole is False when the table may hold more than it shows: an item that is
        not written out. A list or a dict that something in the folder may have changed (touched) gives nothing:
        an entry may have been replaced."""
        none = ([], at, False)
        if depth > 6:
            return none
        if isinstance(e, (ast.Name, ast.Attribute)):
            hit = (
                self.lookup(e.id, _pos(e), at)
                if isinstance(e, ast.Name)
                else self.dotted(self.qual(e, at[0]))
            )
            if (
                not hit
                or hit[0] != "bind"
                or hit[1].value is None
                or hit[1].item is not None
            ):
                return none
            _, b, env = hit
            where = (env, b.chain, b.shadow)
            name = e.id if isinstance(e, ast.Name) else e.attr
            if not isinstance(b.value, ast.Tuple) and name in self.touched():
                return none  # an entry may have been replaced: nothing it shows is sure to be reached
            return self.shelf(b.value, where, pick, depth + 1, key, loop)
        if isinstance(e, ast.Call) and isinstance(e.func, ast.Attribute) and not e.args:
            attr = e.func.attr
            if (
                not loop
                or attr not in ("values", "items")
                or (attr == "items") != (pick == 1)
            ):
                return none
            return self.shelf(e.func.value, at, None, depth + 1)
        items, by_key = None, False
        if isinstance(e, ast.Dict) and None not in e.keys:
            ks = [self.fixed(k, at) for k in e.keys]
            one = isinstance(key, ast.Constant) and None not in ks
            items = [v for k, v in zip(ks, e.values) if not one or k[0] == key.value]
            by_key = True
        elif (
            isinstance(e, ast.Call)
            and isinstance(e.func, ast.Name)
            and e.func.id == "dict"
            and not e.args
            and all(k.arg for k in e.keywords)
            and self.lookup("dict", _pos(e.func), at) is None
        ):
            one = isinstance(key, ast.Constant)
            items = [k.value for k in e.keywords if not one or k.arg == key.value]
            by_key = True
        elif isinstance(e, (ast.List, ast.Tuple, ast.Set)) and not any(
            isinstance(x, ast.Starred) for x in e.elts
        ):
            items = list(e.elts)
        if items is None or (loop and by_key):  # a loop over a dict gives its keys
            return none
        if pick is None:
            return items, at, True
        picked = [
            x.elts[pick]
            for x in items
            if isinstance(x, ast.Tuple) and pick < len(x.elts)
        ]
        return picked, at, len(picked) == len(items)

    def shelved(self, e, at):
        """BASE[name], with BASE a table of pictures written out that nothing in the folder may have changed: what
        all its items are (or the one item a constant key names), when they read the same."""
        key = self.keyed(e.slice, at)
        items, where, whole = self.shelf(e.value, at, None, 0, key)
        if not items or not whole:
            return None
        out = self.value(items[0], where)
        for x in items[1:]:
            out = _same(out, self.value(x, where))
        return out

    def fixed(self, e, at, depth=0):
        """(value,) when an expression is a constant, as written or through a name bound to one (GRID = "grid",
        also GLOW, GRID = "glow", "grid"); None for anything else."""
        if isinstance(e, ast.Constant):
            return (e.value,)
        if depth > 3 or not isinstance(e, (ast.Name, ast.Attribute)):
            return None
        hit = (
            self.lookup(e.id, _pos(e), at)
            if isinstance(e, ast.Name)
            else self.dotted(self.qual(e, at[0]))
        )
        if not hit or hit[0] != "bind" or hit[1].value is None:
            return None
        b, where = hit[1], (hit[2], hit[1].chain, hit[1].shadow)
        if b.item is None:
            return self.fixed(b.value, where, depth + 1)
        shown, (i, n) = self.display(b.value, where), b.item
        if (
            shown
            and isinstance(shown[0], (ast.Tuple, ast.List))
            and len(shown[0].elts) == n
        ):
            return self.fixed(shown[0].elts[i], shown[1], depth + 1)
        return None

    def keyed(self, key, at):
        """The key of X[key] or X.get(key) as a constant when it is one, also through a name; else as written."""
        got = self.fixed(key, at)
        return ast.Constant(value=got[0]) if got else key

    def touched(self):
        """The names whose object may be changed after it is written, anywhere in the folder: one with an item or
        an attribute assigned or deleted or a changing method called (append, update, pop), and each name on the
        way to it (look.PAL["x"] = c touches PAL); one stored in an item, an attribute or a display, returned, or
        handed to a call that is not a builtin reading it (READERS); and a name that one of those is bound from
        (ALIAS = KEEP touches KEEP when ALIAS is). A list or a dict under such a name may not hold what its display
        shows, so it is not read; a tuple cannot be changed."""
        if self.changed is None:
            names, alias = set(), []
            for sc in self.mods.values():
                up = {
                    id(c): n for n in ast.walk(sc.tree) for c in ast.iter_child_nodes(n)
                }
                for n in ast.walk(sc.tree):
                    if isinstance(
                        n, (ast.Assign, ast.AugAssign, ast.AnnAssign, ast.Delete)
                    ):
                        targets = (
                            n.targets
                            if isinstance(n, (ast.Assign, ast.Delete))
                            else [n.target]
                        )
                        for x in targets:
                            if isinstance(x, (ast.Subscript, ast.Attribute)):
                                names.update(_chain(x))
                    elif (
                        isinstance(n, ast.Call)
                        and isinstance(n.func, ast.Attribute)
                        and n.func.attr in MUTATORS
                    ):
                        names.update(_chain(n.func.value))
                    if not isinstance(n, (ast.Name, ast.Attribute)) or not isinstance(
                        n.ctx, ast.Load
                    ):
                        continue
                    name, over = (
                        getattr(n, "id", getattr(n, "attr", None)),
                        up.get(id(n)),
                    )
                    if (
                        isinstance(over, (ast.Assign, ast.AnnAssign, ast.NamedExpr))
                        and over.value is n
                    ):
                        to = (
                            over.targets
                            if isinstance(over, ast.Assign)
                            else [over.target]
                        )
                        if all(isinstance(x, ast.Name) for x in to):
                            alias += [(x.id, name) for x in to]
                        else:
                            names.add(name)
                    elif isinstance(over, ast.Call):
                        f = over.func
                        if f is not n and getattr(f, "id", None) not in READERS:
                            names.add(name)
                    elif isinstance(over, ast.keyword):
                        if over.arg is not None:
                            names.add(name)
                    elif isinstance(over, ast.Dict):
                        if any(
                            v is n and k is not None
                            for k, v in zip(over.keys, over.values)
                        ):
                            names.add(name)
                    elif isinstance(
                        over,
                        (
                            ast.Return,
                            ast.Yield,
                            ast.YieldFrom,
                            ast.Lambda,
                            ast.List,
                            ast.Set,
                            ast.Tuple,
                        ),
                    ):
                        names.add(name)
            grew = True
            while grew:
                grew = False
                for to, name in alias:
                    if to in names and name not in names:
                        names.add(name)
                        grew = True
            self.changed = names
        return self.changed

    def handed(self, scan, fn, call, at):
        """{parameter: _Arg} for one call: its arguments by position and by keyword, then the defaults of the rest,
        read at the def. A parameter the call may fill through *args or **kwargs is left out (unread)."""
        a = fn.args
        pos = [x.arg for x in a.posonlyargs + a.args]
        named = set(pos[len(a.posonlyargs) :]) | {x.arg for x in a.kwonlyargs}
        out, star = {}, False
        for name, arg in zip(pos, call.args):
            if isinstance(arg, ast.Starred):
                star = True
                break
            out[name] = _Arg(self, arg, at)
        for k in call.keywords:
            if k.arg is None:
                star = True
            elif k.arg in named:
                out[k.arg] = _Arg(self, k.value, at)
        if not star:
            home = (self.module(scan), (), frozenset())
            for arg, d in _defaults(fn):
                if arg.arg not in out:
                    out[arg.arg] = _Arg(self, d, home)
        return out

    def enter(self, key, call, at, role):
        """Read the def a call names, for that call: "walk" judges its body; "val", "col" and "num" give what it
        returns as a picture or an ImageDraw, as a colour and as an alpha."""
        scan, fn = self.defs[key]
        if role == "walk" and key[0] in self.readers:
            return None
        site = (at[0].scan.path.name, call.lineno)
        return self.run(key, self.handed(scan, fn, call, at), role, site)

    def run(self, key, args, role, site):
        """One reading of a def in one role, or the earlier reading whose every used fact this call hands it again.
        A def that is being read (recursion) and a call past the limits give nothing."""
        rows = self.memo.setdefault((key, role), [])
        for ent in rows:
            if all(
                (args[p].read(r) if p in args else None) == v
                for (p, r), v in ent.used.items()
            ):
                if site:
                    ent.sites.add(site)
                return ent.out
        if (key, role) in self.active:
            return None
        if self.left <= 0 or self.depth >= DEEP:
            self.capped = True
            return None
        scan, fn = self.defs[key]
        ent = _Entry()
        if site:
            ent.sites.add(site)
        flow = self.flow(fn)
        env = _Env(
            "def", flow, scan, [self.scope(scan, fn, [])], self.module(scan), args, ent
        )
        self.active.add((key, role))
        self.left, self.depth = self.left - 1, self.depth + 1
        try:
            if role == "walk":
                self.walk(env)
            elif flow.returns and not flow.yields:
                outs = [
                    self.returned(r, (env, chain, frozenset()), role)
                    for r, chain in flow.returns
                ]
                join = {"val": _same, "col": _either, "num": _one_of}[role]
                ent.out = outs[0]
                for o in outs[1:]:
                    ent.out = join(ent.out, o)
        except RecursionError:
            # nested deeper than Python follows: stop as at the limit, and keep no half-made reading
            self.capped = True
            return None
        finally:
            self.active.discard((key, role))
            self.depth -= 1
        rows.append(ent)
        return ent.out

    def returned(self, e, at, role):
        """What one return statement gives. A colour written out with an alpha is read only when that alpha is the
        def's own to give (_alpha_param): mix(c1, c2, k) hands back what it was given, which says nothing here."""
        if e is None:
            return None
        if role != "col":
            return self.value(e, at) if role == "val" else self.number(e, at)
        seen = e
        for _ in range(3):  # return out, with out = (r, g, b, a) bound above
            b = (
                _reach(at[0].flow, seen.id, _pos(seen), at[1])
                if isinstance(seen, ast.Name)
                else None
            )
            if not isinstance(b, _Bind) or b.value is None or b.item is not None:
                break
            seen = b.value
        if _alpha_of(seen) is not None and _alpha_param(at[0].flow, seen) == set():
            return None
        return self.colour(e, at)

    # ---- findings ----

    def plan(self, env):
        """What each call of a body is, read once: "make" where an ImageDraw is made, "fill" where a method that
        takes a colour is called, and the folder defs the call names."""
        flow = env.flow
        if flow.plan is None:
            flow.plan = []
            for call, chain, shadow in flow.calls:
                f, kind = call.func, None
                if self.qual(f, env) in DRAW_CALLS:
                    kind = "make"
                elif isinstance(f, ast.Attribute) and f.attr in DRAW_FILLS:
                    kind = "fill"
                keys, _ = self.callees(f, (env, chain, shadow))
                if kind or keys:
                    flow.plan.append((call, chain, shadow, kind, keys))
        return flow.plan

    def walk(self, env):
        """Judge one body: each ImageDraw it makes and each colour it draws, then the defs it calls, each read for
        the arguments of that call, and the bodies written inside it."""
        for call, chain, shadow, kind, keys in self.plan(env):
            at = (env, chain, shadow)
            if kind == "make":
                self.made(call, at)
            elif kind == "fill":
                self.drawn(call, at)
            for key in keys:
                self.enter(key, call, at, "walk")
        for node, chain, shadow in env.flow.inner:
            # a def written straight in the module is read for its callers
            if not self.top(env, node):
                self.walk(self.nested(env, node, chain, shadow))

    def made(self, call, at):
        """Q1207 where an ImageDraw is made: ImageDraw.Draw(img, "RGBA") on an RGBA picture read as opaque. The
        mode asks Pillow to blend, and Pillow blends only on an RGB image, so nothing drawn through it can blend."""
        p = self.pen(call, at)
        if p and p[1] is True and p[2] == "RGBA":
            pic, pos = call.args[0] if call.args else _keyword(call, "im"), _pos(call)
            if not self.guarded_off(pic, at, pos, "val") and not self.cleared(
                pic, at, pos, call
            ):
                self.report(call, at, ("asked",), self.origin(pic, at, "RGBA"))

    def drawn(self, call, at):
        """Q1207 where a colour is drawn: a see-through fill, outline or stroke_fill through an ImageDraw the lint
        has read (made in the call, bound to a name, handed in, or returned by a folder def, alone or in a tuple).
        Through a plain ImageDraw it replaces the pixel and its alpha on an RGBA picture and loses its alpha on an
        RGB one; text and a bitmap never blend, whatever the mode. An ImageDraw made with "RGBA" on an RGBA
        picture is reported where it is made. An outline is judged only when it is drawn (its width is not read as
        0), a stroke_fill only with a stroke_width that is."""
        f = call.func
        p = self.value(f.value, at)
        if not p or p[0] != "pen" or p[2] not in ("RGBA", "RGB"):
            return
        _, asked, mode = p
        never = f.attr in DRAW_NEVER
        if (mode == "RGBA" and asked is True) or (
            mode == "RGB" and not never and asked is not False
        ):
            return
        pos = _pos(call)
        if self.guarded_off(f.value, at, pos, "val"):
            return
        named = {k.arg: k.value for k in call.keywords if k.arg}
        args = [] if any(isinstance(x, ast.Starred) for x in call.args) else call.args
        spots = DRAW_FILLS[f.attr]
        fill = [named.get("fill")] + [args[i] for i in spots[:1] if i < len(args)]
        if never:
            colours = fill
            if self.wide(named.get("stroke_width"), at, False):
                colours = fill + [named.get("stroke_fill")]
        elif f.attr == "point":
            colours = fill
        else:
            # the width comes right after the last colour: of the outline for a shape, of the stroke itself for a
            # line and an arc; at width 0 Pillow draws neither
            edge = spots[-1] + 1
            width = named.get("width", args[edge] if edge < len(args) else None)
            last = [named.get("outline")] if len(spots) > 1 else []
            last += [args[i] for i in spots[1:] if i < len(args)]
            if len(spots) == 1:
                fill, last = [], fill
            colours = fill + (last if self.wide(width, at, True) else [])
        if any(
            c is not None
            and self.colour(c, at) == "see"
            and not self.guarded_off(c, at, pos, "col")
            for c in colours
        ) and not (mode == "RGBA" and self.cleared(f.value, at, pos, call)):
            self.report(
                call, at, (f.attr, mode, never), self.pen_origin(f.value, at, mode)
            )

    def wide(self, width, at, default):
        """True unless a width is read to draw nothing: not given, it is the default (1 for an outline, a line and
        an arc, 0 for the stroke of text); given, it draws unless the lint reads it as 0 (or as a choice of numbers
        none of which is above 0)."""
        if width is None:
            return default
        n = self.number(width, at)
        if isinstance(n, frozenset):
            return any(x > 0 for x in n)
        return type(n) not in (int, float) or n > 0

    def cleared(self, e, at, pos, this):
        """True when the opaque picture a draw at pos lands on may have been cleared before it, in the same body or
        in a def of the folder the body hands it to. e is the ImageDraw or the picture as written; the picture is
        told by its name (_pictures). A change counts when it comes before pos or sits in a loop around pos: a
        putalpha other than putalpha(255), a paste of a colour read as clear or see-through, an area filled with
        alpha 0 through an ImageDraw on the same picture (a rectangle, an ellipse, a polygon: an erase)."""
        env, chain = at[0], at[1]
        flow = env.flow

        def live(when, ch):
            return when < pos or any(k in flow.loops and k in ch for k in chain)

        return self.wiped(env, _pictures(flow, e), live, this, 0)

    def wiped(self, env, names, live, this, depth):
        """cleared() for one body and the pictures it knows by these names: the changes the body makes itself,
        then, two calls deep, those a def of the folder makes to a picture one of the body's calls hands it."""
        flow = env.flow
        for name in names:
            for when, ch, sh, call in flow.events.get(name, ()):
                first = _first(call)
                if not live(when, ch) or first is None:
                    continue
                what, where = call.func.attr, (env, ch, sh)
                if what == "putalpha":
                    if not _const_in(first, (255,)):
                        return True
                elif what == "paste" and self.clears(
                    call, first, self.value(first, where), where
                ):
                    return True
        if depth < 2:
            # a def or a lambda written in this body that changes the picture through the name it shares with it
            for node, ch, sh in flow.inner:
                if isinstance(node, ast.ClassDef):
                    continue
                inner = self.nested(env, node, ch, sh)
                free = {n for n in names if _single(inner.flow, n) is FREE}
                if free and self.wiped(
                    inner, free, lambda when, ch: True, None, depth + 1
                ):
                    return True
        for when, ch, sh, call in flow.draws:
            if call is this or not live(when, ch):
                continue
            if not names & _pictures(flow, call.func.value):
                continue
            where, spots = (env, ch, sh), DRAW_FILLS[call.func.attr]
            if len(spots) < 2:
                continue  # a line, a point, an arc or text clears no area
            fills = [k.value for k in call.keywords if k.arg == "fill"]
            if not any(isinstance(x, ast.Starred) for x in call.args):
                fills += [call.args[i] for i in spots[:1] if i < len(call.args)]
            if any(self.colour(c, where) == "clear" for c in fills):
                return True
        if depth > 1:
            return False
        for call, ch, sh in flow.calls:
            if call is this or not live(_pos(call), ch):
                continue
            keys = None
            for i, x in enumerate(call.args + [k.value for k in call.keywords]):
                if not isinstance(x, ast.Name) or x.id not in names:
                    continue
                if keys is None:
                    keys = self.callees(call.func, (env, ch, sh))[0]
                for key in keys:
                    scan, fn = self.defs[key]
                    order = [a.arg for a in fn.args.posonlyargs + fn.args.args]
                    if i < len(call.args):
                        param = order[i] if i < len(order) else None
                    else:
                        param = call.keywords[i - len(call.args)].arg
                    if param is None:
                        continue
                    inner = _Env(
                        "def",
                        self.flow(fn),
                        scan,
                        [self.scope(scan, fn, [])],
                        self.module(scan),
                    )
                    theirs = _pictures(inner.flow, ast.Name(id=param, ctx=ast.Load()))
                    if self.wiped(
                        inner, theirs, lambda when, ch: True, None, depth + 1
                    ):
                        return True
        return False

    def guarded_off(self, e, at, pos, role):
        """True when the statement at pos runs under a test the lint does not see past. For a colour ("col") or an
        alpha ("num"): a test that may hold it to its opaque side (_confines), as in a helper that draws straight
        on when its colour is opaque and through a layer when it is not. For a picture or an ImageDraw ("val"): a
        test of its mode (if img.mode == "RGB")."""
        flow = at[0].flow
        tests = _guards(flow, pos, at[1])
        if not tests:
            return False
        if role == "val":
            names = _behind(flow, [e])
            return any(_asks_mode(test, names) for test, _ in tests)
        names = _near(flow, e, role == "num")
        return bool(names) and any(
            _confines(test, side, names, lambda x: self.number(x, at))
            for test, side in tests
        )

    def origin(self, e, at, what):
        """(reading, parameter, what it is) when a picture came in as a parameter of a def read for a call."""
        hit = self.lookup(e.id, _pos(e), at) if isinstance(e, ast.Name) else None
        if hit and hit[0] == "arg" and hit[1].entry is not None:
            return (hit[1].entry, e.id, what)
        return None

    def pen_origin(self, e, at, mode):
        """The same for the ImageDraw of a draw call: handed in, or made on a picture that was handed in."""
        if isinstance(e, ast.Name):
            hit = self.lookup(e.id, _pos(e), at)
            if hit and hit[0] == "arg":
                what = f"an ImageDraw on an {mode} picture"
                return (hit[1].entry, e.id, what) if hit[1].entry is not None else None
            if (
                hit
                and hit[0] == "bind"
                and hit[1].value is not None
                and hit[1].item is None
            ):
                e, at = hit[1].value, (hit[2], hit[1].chain, hit[1].shadow)
        if isinstance(e, ast.Call) and self.qual(e.func, at[0]) in DRAW_CALLS:
            pic = e.args[0] if e.args else _keyword(e, "im")
            return self.origin(pic, at, mode)
        return None

    def report(self, call, at, what, note):
        """Keep one finding per call, however many readings reach it, with the calls that handed it its picture."""
        env = at[0]
        if env.scan.path.stem in self.readers:
            return
        hit = self.hits.setdefault(
            id(call), {"call": call, "env": env, "what": what, "notes": []}
        )
        if what == hit["what"]:
            hit["notes"].append(note)

    def rows(self):
        """[(scan, call, message, scope stack)] of the findings, sorted: scenes.py first, then by file and line."""
        out = []
        for hit in self.hits.values():
            where = ""
            if all(hit["notes"]):
                sites = sorted(
                    (s[0] != "scenes.py", s, name, what)
                    for ent, name, what in hit["notes"]
                    for s in ent.sites
                )
                if sites:
                    _, (file, line), name, what = sites[0]
                    where = f" ({name} is {what} when called at {file}:{line})"
            env, call = hit["env"], hit["call"]
            out.append((env.scan, call, _blend_msg(hit["what"], where), env.stack))
        return sorted(
            out,
            key=lambda r: (r[0].path.name != "scenes.py", r[0].path.name, _pos(r[1])),
        )

    def study(self):
        """Read the folder: the module-level code of each file with the classes, methods and nested bodies in it,
        then each def that no call in the folder names, as an outside caller would call it (its defaults in place,
        its other parameters _Open; a def under a decorator is one of them, see wrapped), then any def still
        unread: one reached only from defs that nothing reaches, whose parameters stay unread."""
        called = set()

        def survey(env, owner):
            for *_, keys in self.plan(env):
                called.update(k for k in keys if k != owner)
            for node, chain, shadow in env.flow.inner:
                key = self.top(env, node)
                if key:
                    stack = [self.scope(env.scan, node, [])]
                    survey(_Env("def", self.flow(node), env.scan, stack, env), key)
                else:
                    survey(self.nested(env, node, chain, shadow), owner)

        for sc in self.scans:
            survey(self.module(sc), None)
        for sc in self.scans:
            self.walk(self.module(sc))
        keys = sorted(k for k in self.defs if k[0] not in self.readers)
        for key in [k for k in keys if k not in called] + keys:
            if not self.memo.get((key, "walk")):
                scan, fn = self.defs[key]
                home = (self.module(scan), (), frozenset())
                args = {} if key in called else {x: _Open for x in self.flow(fn).params}
                args.update({arg.arg: _Arg(self, d, home) for arg, d in _defaults(fn)})
                self.run(key, args, "walk", None)
        return self


def _power(a, b):
    """a ** b for small exponents; ValueError past them (then the alpha is unread)."""
    if abs(b) > 64:
        raise ValueError(b)
    return a**b


_FOLDS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.FloorDiv: lambda a, b: a // b,
    ast.Mod: lambda a, b: a % b,
    ast.Pow: lambda a, b: _power(a, b),
    ast.LShift: lambda a, b: a * _power(2, b) if type(a) is int else a << b,
    ast.RShift: lambda a, b: a >> b,
    ast.BitAnd: lambda a, b: a & b,
    ast.BitOr: lambda a, b: a | b,
    ast.BitXor: lambda a, b: a ^ b,
}
# functions of constants the lint works out, by the name they are imported under, and three constants
_MATH = {
    f"math.{name}": getattr(math, name)
    for name in (
        "sqrt",
        "floor",
        "ceil",
        "trunc",
        "fabs",
        "sin",
        "cos",
        "tan",
        "atan2",
        "hypot",
        "exp",
        "log",
        "log2",
        "log10",
        "pow",
        "radians",
        "degrees",
        "pi",
        "tau",
        "e",
    )
}
_MATH.update(
    {
        "numpy.uint8": int,
        "numpy.int32": int,
        "numpy.int64": int,
        "numpy.float32": float,
        "numpy.float64": float,
        "numpy.sqrt": math.sqrt,
        "numpy.floor": math.floor,
        "numpy.ceil": math.ceil,
        "numpy.sin": math.sin,
        "numpy.cos": math.cos,
        "numpy.pi": math.pi,
        "numpy.clip": lambda x, lo, hi: min(max(x, lo), hi),
    }
)
_CALLS = {
    "int": int,
    "float": float,
    "round": round,
    "abs": abs,
    "min": min,
    "max": max,
}


def _blend_msg(what, where):
    """The message of one Q1207 finding; where names the call that handed the def its picture."""
    if what[0] == "asked":
        return (
            f'ImageDraw.Draw(img, "RGBA") is made on an RGBA picture{where}: Pillow blends only on an RGB image, so '
            "nothing drawn through it can blend, with the mode or without it (a see-through colour would replace "
            "the pixel and its alpha)"
        )
    attr, mode, never = what
    if never:
        kind = "a bitmap" if attr == "bitmap" else "text"
        lost = (
            "it replaces the pixel and its alpha"
            if mode == "RGBA"
            else "the alpha is dropped and the colour goes on at full strength"
        )
        return (
            f".{attr}() gives a see-through colour to an ImageDraw on an {mode} picture{where}: Pillow never blends "
            f"{kind}, whatever the mode of the ImageDraw, so {lost} (engine.text takes an alpha; or draw on a "
            "transparent layer and composite it)"
        )
    if mode == "RGBA":
        return (
            f".{attr}() draws a see-through colour straight onto an RGBA picture{where}: ImageDraw replaces the "
            "pixel and its alpha there instead of blending, so it shows at full strength, or black, once the frame "
            "is flattened"
        )
    return (
        f".{attr}() gives a see-through colour to a plain ImageDraw on an RGB picture{where}: the alpha is dropped "
        'and the colour goes on at full strength (ImageDraw.Draw(img, "RGBA") blends shapes there)'
    )


def _learn_pictures(scans, engine):
    """Q1207 for a folder: read it (_Pix.study) and add each finding to the scan of its file, through add(), so the
    blend-ok pragma and the silenced count work as for the other codes. True when a limit stopped the reading."""
    pix = _Pix(scans, engine)
    try:
        pix.study()
    except RecursionError:
        pix.capped = (
            True  # nested deeper than Python follows: what was read so far stands
        )
    for scan, call, msg, stack in pix.rows():
        scan.add("Q1207", call, msg, stack)
    return pix.capped


def findings(path="scenes.py"):
    """Every static finding in scenes.py and the local modules it imports, as dicts {code, file, line, func, text,
    msg}, plus counts {files, calls, defs, silenced, capped} for the rows. Q1207 comes last, in one order (scenes.py,
    then by file and line) whatever order the files were found in."""
    files = local_modules(path)
    trees = {p: ast.parse(p.read_text(encoding="utf-8")) for p in files}
    plain = {p.stem: _Scan(p) for p in files}
    tops = {k: s.top for k, s in plain.items()}
    rngs = {k: s.rngs() for k, s in plain.items()}
    early = import_time_defs(trees.values())
    out, calls, silenced = [], 0, 0
    scans = [_Scan(p, tops, early, rngs).scan() for p in files]
    capped = _learn_pictures(scans, _engine_file(Path(path).parent))
    for sc in scans:
        out += sc.found
        calls += sc.calls
        silenced += sc.silenced
    first = Path(path).name
    out.sort(
        key=lambda d: (
            (1, d["file"] != first, d["file"], d["line"])
            if d["code"] == "Q1207"
            else (0,)
        )
    )
    sh, ndefs, s2 = shadow_findings(path)
    out += sh
    return out, {
        "files": [p.name for p in files],
        "calls": calls,
        "defs": ndefs,
        "silenced": silenced + s2,
        "capped": capped,
    }


# ---- build settings and the scenes module (Q904, Q905 and owner need SCHEDULE, CUES and BPM values) ----


def _assigned(path, prefix=""):
    """{W, H, FPS, SS: value} from constant assignments in a file: `E.W, E.H, E.FPS, E.SS = 1920, 1080, 30, 1` in
    run_all.py (prefix "E."), or the defaults line in engine.py."""
    out = {}
    if not Path(path).exists():
        return out
    for s in ast.walk(ast.parse(Path(path).read_text(encoding="utf-8"))):
        if not isinstance(s, ast.Assign) or len(s.targets) != 1:
            continue
        t, v = s.targets[0], s.value
        pairs = (
            zip(t.elts, v.elts)
            if isinstance(t, ast.Tuple)
            and isinstance(v, ast.Tuple)
            and len(t.elts) == len(v.elts)
            else [(t, v)]
        )
        for a, b in pairs:
            name = ast.unparse(a)
            key = name[len(prefix) :]
            constant = isinstance(b, ast.Constant) and isinstance(b.value, (int, float))
            if name.startswith(prefix) and key in ("W", "H", "FPS", "SS") and constant:
                out.setdefault(key, b.value)
    return out


def settings(folder="."):
    """The build's frame size, fps and supersampling as {W, H, FPS, SS, src}: the engine already set up in this
    process when scenes is imported; else build.json (run_all.py writes it at every stage, after --size, --fps and
    scenes.py); else the last render's frames.hash (W, H, FPS) over the constants in the folder's run_all.py, over
    engine.py's defaults."""
    folder = Path(folder).resolve()
    m = sys.modules.get("scenes")
    if (
        m is not None
        and Path(m.__file__).resolve().parent == folder
        and "engine" in sys.modules
    ):
        E = sys.modules["engine"]
        return {"W": E.W, "H": E.H, "FPS": E.FPS, "SS": E.SS, "src": "this process"}
    b = C.read_build(folder)
    if b:
        return dict(zip(("W", "H", "FPS", "SS"), b), src=C.BUILD)
    d = {"W": 1920, "H": 1080, "FPS": 30, "SS": 1, "src": "engine defaults"}
    d.update(_assigned(_engine_file(folder)))
    got = _assigned(folder / "run_all.py", "E.")
    if got:
        d.update(got, src="run_all.py")
    man = C.read_frame_manifest(folder)
    if man:
        d.update(
            W=man["w"],
            H=man["h"],
            FPS=man["fps"],
            src=f"{C.FRAMES_HASH} and run_all.py",
        )
    return d


def load_scenes(folder=".", fps=None, size=None, ss=None):
    """The folder's scenes module, imported once with E.W, E.H, E.FPS, E.SS set first (from settings() unless
    given). Returns (scenes, settings)."""
    folder = Path(folder).resolve()
    st = settings(folder)
    m = sys.modules.get("scenes")
    if m is not None and Path(m.__file__).resolve().parent == folder:
        return m, st
    if m is not None:
        raise RuntimeError(f"another scenes module is already imported ({m.__file__})")
    if size:
        st["W"], st["H"] = size
    if fps:
        st["FPS"] = fps
    if ss:
        st["SS"] = ss
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    import engine as E

    E.W, E.H, E.FPS, E.SS = st["W"], st["H"], st["FPS"], st["SS"]
    import scenes

    return scenes, st


def window_span(w):
    """(t0, t1, label) of one WINDOWS entry, or None when it holds no two times: a tuple (t0, t1, out, in) as
    compile_schedule writes it, (t0, t1), (name, t0, t1), a dict with t0/t1 (or start/end), or an object with
    t0/t1 (or start/end)."""
    try:
        if isinstance(w, dict):
            a, b, lab = (
                w.get("t0", w.get("start")),
                w.get("t1", w.get("end")),
                w.get("name", ""),
            )
        elif hasattr(w, "t0") or hasattr(w, "start"):
            a = getattr(w, "t0", getattr(w, "start", None))
            b = getattr(w, "t1", getattr(w, "end", None))
            lab = getattr(w, "name", "")
        else:
            nums = [
                v for v in w if isinstance(v, (int, float)) and not isinstance(v, bool)
            ]
            a, b = (nums + [None, None])[:2]
            lab = ">".join(
                v for v in w if isinstance(v, str)
            )  # (t0, t1, out, in) -> "out>in"
        return None if a is None or b is None else (float(a), float(b), str(lab))
    except (TypeError, ValueError):  # not a window at all: skipped
        return None


def window_spans(scn):
    """scenes.WINDOWS as [(t0, t1, label)]; WINDOWS may also be a dict of name to (t0, t1)."""
    w = getattr(scn, "WINDOWS", None) or []
    items = list(w.items()) if isinstance(w, dict) else [(None, x) for x in w]
    out = []
    for name, x in items:
        span = window_span(x)
        if span:
            out.append((span[0], span[1], span[2] if name is None else str(name)))
    return out


def windows(scn):
    """scenes.WINDOWS as [(t0, t1)]."""
    return [(a, b) for a, b, _ in window_spans(scn)]


def cut_list(scn):
    """scenes.CUTS as sorted seconds: numbers, or (t, label) entries as proof.py accepts; anything else skipped."""
    out = []
    for c in getattr(scn, "CUTS", None) or []:
        v = c[0] if isinstance(c, (tuple, list)) and c else c
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out.append(float(v))
    return sorted(out)


def cut_times(scn):
    """Every cut: SCHEDULE starts and ends inside the piece, plus scenes.CUTS; sorted seconds."""
    dur = float(getattr(scn, "DURATION", 0) or 0)
    ts = {float(v) for a, b in getattr(scn, "SCHEDULE", {}).values() for v in (a, b)}
    ts |= set(cut_list(scn))
    return sorted(t for t in ts if 0 < t < dur)


def grid_rows(scn, fps):
    """Q904: SCHEDULE, DURATION and CUES times more than 1e-3 frame off the grid; Q905: a beat that is not a
    whole number of frames. Both NOTE: kits and style cards use 66 or 96 BPM on purpose."""
    times = []
    for name, (a, b) in getattr(scn, "SCHEDULE", {}).items():
        times += [(float(a), f"{name} start"), (float(b), f"{name} end")]
    if getattr(scn, "DURATION", None) is not None:
        times.append((float(scn.DURATION), "DURATION"))
    rows = []
    try:
        times += [(c["t"], f"cue {c['label'] or c['t']}") for c in C.cues(scn)]
    except (TypeError, ValueError, KeyError, IndexError) as e:
        rows.append(
            C.not_checked(
                "Q904",
                f"CUES is not in the registry form [(t, label, kind)], so its times were not read ({type(e).__name__})",
                "write CUES as (t, label, kind) entries (engine/scenes.py shows the form)",
            )
        )
    seen, off = set(), []
    for t, why in times:
        k = round(t, 9)
        if k in seen:
            continue
        seen.add(k)
        if not C.on_grid(t, fps) and not C.allowed(scn, "Q904", t, 0.5 / fps):
            off.append((abs(t * fps - round(t * fps)), t, why))
    off.sort(reverse=True)
    rows.append(
        C.row(
            not off,
            "Q904",
            f"{len(off)} of {len(seen)} times off the {fps:g} fps grid: "
            + "; ".join(f"{why} {t:.4f} s ({d:.2f} frame)" for d, t, why in off[:6])
            + (f" (+{len(off) - 6} more)" if len(off) > 6 else "")
            if off
            else f"SCHEDULE, DURATION and CUES on the {fps:g} fps grid ({len(seen)} times)",
            "write times as frame / FPS or snap them (contract.snap); a planned off-grid time goes in "
            "ALLOW['Q904']",
            note=True,
            worst_t=off[0][1] if off else None,
            item=off[0][2] if off else None,
            metric=round(off[0][0], 4) if off else None,
            limit=1e-3,
            spans=[(t, t) for _, t, _ in sorted(off, key=lambda x: x[1])],
            considered=len(seen),
        )
    )
    bpm = getattr(scn, "BPM", None)
    if not bpm:
        rows.append(
            C.row(True, "Q905", "no BPM in scenes.py: no beat grid to check", "")
        )
    else:
        whole = [b for b in range(60, 201) if (60 * fps) % b == 0]
        fpb = 60 / bpm * fps
        rows.append(
            C.row(
                C.whole_frame_beat(bpm, fps),
                "Q905",
                f"one beat at {bpm:g} BPM is {fpb:.4g} frames at {fps:g} fps"
                + (
                    ""
                    if C.whole_frame_beat(bpm, fps)
                    else ": beats drift across frames"
                ),
                f"a whole-frame BPM at {fps:g} fps: {', '.join(map(str, whole))}; or keep it and snap each hit to "
                "its nearest frame",
                note=True,
                item=f"{bpm:g} BPM",
                metric=round(fpb, 4),
                considered=1,
            )
        )
    return rows


def run(path="scenes.py", fps=None):
    """Rows for run_all.py proof and `qa.py lint`: Q1202 to Q1207 from the ast of scenes.py and its local modules
    (FIX for Q1202 and Q1207, NOTE for the rest), then Q904 and Q905 from the imported module."""
    path = Path(path)
    found, n = findings(path)
    where = ", ".join(n["files"])
    rows = []
    for code in ("Q1202", "Q1203", "Q1204", "Q1205", "Q1206", "Q1207"):
        hits = [d for d in found if d["code"] == code]
        # Q1207 follows calls up to a limit: past it defs go unread, and the row says so
        cut = (
            f" (the lint stopped following calls at its limit, {STEPS} readings of a def or {DEEP} calls deep: "
            "the defs past it were not read)"
            if code == "Q1207" and n["capped"]
            else ""
        )
        seen = (
            n["defs"] if code == "Q1204" else n["calls"]
        )  # [N checked]: top-level defs for Q1204, else calls
        if not hits:
            rows.append(
                C.row(
                    True, code, f"no {MEANS[code]} in {where}{cut}", "", considered=seen
                )
            )
            continue
        listed = "; ".join(
            f"{d['file']}:{d['line']} {d['text']}"
            + ("" if code == "Q1204" else f" in {d['func']}")
            for d in hits[:5]
        )
        more = f" (+{len(hits) - 5} more: qa.py lint --all)" if len(hits) > 5 else ""
        why = "" if code == "Q1206" else f" ({hits[0]['msg']})"
        rows.append(
            C.row(
                False,
                code,
                f"{MEANS[code]}: {len(hits)} found: {listed}{more}{why}{cut}",
                FIXES[code],
                note=code not in ("Q1202", "Q1207"),
                item=f"{hits[0]['file']}:{hits[0]['line']} {hits[0]['text']}",
                considered=seen,
            )
        )
    try:
        scn, st = load_scenes(path.parent, fps)
        rows += grid_rows(scn, fps or st["FPS"])
    except (
        USER_ERRORS
    ) as e:  # scenes.py itself failed to import: the static rows above still stand
        for code in ("Q904", "Q905"):
            rows.append(
                C.not_checked(
                    code,
                    f"scenes.py did not import ({type(e).__name__}: {e}), so SCHEDULE, CUES and BPM were not read",
                    "fix the import error (qa.py owner --traceback), then rerun qa.py lint",
                )
            )
    return rows


# ---- owner: which scene function a finding belongs to (Z08 routing) ----


def scene_functions(path="scenes.py", names=()):
    """{scene name: def node} for the scene functions of scenes.py, from the ast: a module-level dict of name ->
    function (SCENES = dict(hook=scene_hook, ...)), then defs named scene_<name>, draw_<name>, <name>_scene or
    <name>, then any other def named scene_*."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    defs = {
        s.name: s
        for s in tree.body
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    out = {}
    for s in tree.body:
        v = s.value if isinstance(s, ast.Assign) else None
        pairs = []
        if isinstance(v, ast.Dict):
            pairs = [
                (k.value, x.id)
                for k, x in zip(v.keys, v.values)
                if isinstance(k, ast.Constant) and isinstance(x, ast.Name)
            ]
        elif isinstance(v, ast.Call) and ast.unparse(v.func) == "dict":
            pairs = [
                (k.arg, k.value.id)
                for k in v.keywords
                if k.arg and isinstance(k.value, ast.Name)
            ]
        if pairs and all(x in defs for _, x in pairs):
            out.update({k: defs[x] for k, x in pairs})
    for nm in names:
        for cand in (f"scene_{nm}", f"draw_{nm}", f"{nm}_scene", nm):
            if nm not in out and cand in defs:
                out[nm] = defs[cand]
    for x, s in defs.items():
        if x.startswith("scene_") and s not in out.values():
            out[x[6:]] = s
    return out, defs


def _span(path, s):
    return f"{Path(path).name}:{s.lineno}-{s.end_lineno}"


def owner(t=None, traceback_text=None, path="scenes.py", fps=None):
    """The scene function(s) to re-read for a finding. For a time: the scene that owns it, both scenes within one
    frame of a cut or inside a WINDOWS overlap. For a traceback: the innermost scenes.py frame, mapped to its
    enclosing def through end_lineno; a shared helper (bg, title_state) is not a scene function, so it routes to
    the scene functions that call it, else all of them. Returns {why, functions: [(name, file:a-b)], error}."""
    path = Path(path)
    try:
        scn, st = load_scenes(path.parent, fps)
    except USER_ERRORS:  # an import-time crash still routes by the ast alone
        scn = st = None
    sched = getattr(scn, "SCHEDULE", {}) if scn is not None else {}
    sfun, defs = scene_functions(path, list(sched))
    every = sorted({s.name: s for s in sfun.values()}.values(), key=lambda s: s.lineno)
    if not every:
        every = [defs["draw"]] if "draw" in defs else []
    out = {"error": None}
    if traceback_text is not None:
        frames = re.findall(r'File "([^"]+)", line (\d+), in (\S+)', traceback_text)
        last = [ln for ln in traceback_text.strip().splitlines() if ln.strip()][-1:]
        out["error"] = last[0].strip() if last else None
        mine = [(int(ln), fn) for f, ln, fn in frames if Path(f).name == path.name]
        if not mine:
            where = (
                f"{Path(frames[-1][0]).name}:{frames[-1][1]}"
                if frames
                else "no Python frame"
            )
            out.update(
                why=f"no {path.name} frame in the traceback (innermost: {where}): an engine or kit module, or the "
                "environment (see references/troubleshooting.md)",
                functions=[],
            )
            return out
        line = mine[-1][0]
        top = next(
            (
                s
                for s in ast.parse(path.read_text(encoding="utf-8")).body
                if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and s.lineno <= line <= s.end_lineno
            ),
            None,
        )
        if top is None:
            out.update(
                why=f"{path.name}:{line} is module-level code (runs at import)",
                functions=[],
            )
        elif top in sfun.values() or (top.name == "draw" and every == [top]):
            out.update(
                why=f"{path.name}:{line} is inside scene function {top.name}",
                functions=[top],
            )
        else:
            calls = [
                s
                for s in defs.values()
                if s is not top
                and any(
                    isinstance(x, ast.Name) and x.id == top.name for x in ast.walk(s)
                )
            ]
            callers = [s for s in calls if s in every]
            out.update(
                why=f"{path.name}:{line} is inside {top.name} ({_span(path, top)}), a shared helper: "
                + (
                    "the scene functions that call it"
                    if callers
                    else "the functions that call it, and every scene function, may reach it"
                ),
                functions=[top] + (callers or list(dict.fromkeys(calls + every))),
            )
    else:
        fps = fps or (st["FPS"] if st else 30)
        f = C.frame_of(t, fps)
        hit = [nm for nm, (a, b) in sched.items() if a <= t < b] or (
            list(sched)[-1:] if sched else []
        )
        cuts = (
            [c for c in cut_times(scn) if abs(C.frame_of(c, fps) - f) <= 1]
            if scn is not None
            else []
        )
        for c in cuts:
            hit += [nm for nm, (a, b) in sched.items() if a == c or b == c]
        win = [
            w for w in (windows(scn) if scn is not None else []) if w[0] <= t <= w[1]
        ]
        for a0, b0 in win:
            hit += [nm for nm, (a, b) in sched.items() if a < b0 and b > a0]
        hit = list(dict.fromkeys(hit))
        fns = list(dict.fromkeys(sfun[nm] for nm in hit if nm in sfun))
        shared = [nm for nm in hit if nm not in sfun]
        why = f"t={t:.3f} s is frame {f} at {fps:g} fps, in " + (
            " and ".join(hit) or "no scene"
        )
        if cuts:
            why += f" (within 1 frame of the cut at {cuts[0]:.3f} s)"
        if win:
            why += f" (inside the overlap {win[0][0]:.3f} to {win[0][1]:.3f} s)"
        if not sfun:
            why += "; scenes.py has no per-scene functions, so draw(t) and what it calls own every moment"
        elif shared:
            one = len(shared) == 1
            why += (
                f"; {' and '.join(shared)} {'has' if one else 'have'} no scene function of {'its' if one else 'their'}"
                " own, so every scene function may draw it"
            )
        if shared or not fns:
            fns = list(dict.fromkeys(fns + every))
        out.update(why=why, functions=fns, scenes=hit, frame=f)
    out["functions"] = [(s.name, _span(path, s)) for s in out["functions"]]
    return out


# ---- CLI (qa.py calls add_cli) ----


def _lint_cli(a):
    rows = run(a.path, a.fps)
    for r in rows:
        print(C.line(r))
    if a.all:
        found, _ = findings(a.path)
        for d in sorted(found, key=lambda d: (d["code"], d["file"], d["line"])):
            print(
                f"  {d['code']} {d['file']}:{d['line']} in {d['func']}: {d['text']}  ({d['msg']})"
            )
    if a.json:
        C.write_rows(rows, a.json)
    print(C.summary(rows, "LINT"))
    return C.exit_code(rows)


def _owner_cli(a):
    if (a.t is None) == (a.traceback is None):
        print("owner: give --t SECONDS or --traceback FILE")
        return 2
    tb = Path(a.traceback).read_text(encoding="utf-8") if a.traceback else None
    o = owner(a.t, tb, a.path, a.fps)
    print(f"owner: {o['why']}")
    if o["error"]:
        print(f"error: {o['error']}")
    for name, span in o["functions"]:
        print(f"  {name:<24} {span}")
    if o["functions"]:
        print(
            "re-read only these, their text_items rows and the finding; fix with Edit, not a rewrite"
        )
    return 0


def add_cli(sub):
    p = sub.add_parser(
        "lint",
        help="static checks of scenes.py and its local modules (Q1202 to Q1207) and the frame grid (Q904, Q905)",
    )
    p.add_argument("path", nargs="?", default="scenes.py")
    p.add_argument(
        "--fps", type=int, help="the build's fps (default: build.json, else 30)"
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="also list every site, not the first 5 per code",
    )
    p.add_argument("--json", help="also write the rows as JSON to this path")
    p.set_defaults(func=_lint_cli)
    o = sub.add_parser(
        "owner",
        help="the scene function(s) a time or a traceback belongs to, so a fix re-reads only those",
    )
    o.add_argument("--t", type=float, help="seconds")
    o.add_argument("--traceback", help="a file holding a Python traceback")
    o.add_argument("--path", default="scenes.py")
    o.add_argument("--fps", type=int)
    o.set_defaults(func=_owner_cli)
