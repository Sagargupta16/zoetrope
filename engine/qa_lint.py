# qa_lint.py : static checks of scenes.py and the local modules it imports: unseeded randomness and clocks (Q1202),
# module state written inside functions (Q1203), engine helpers redefined (Q1204), text drawn outside the engine
# text helpers (Q1205), colour literals outside the palette block (Q1206), and the frame-grid lint (Q904, Q905).
# Also owner(): the scene function(s) a time or a traceback belongs to, so a fix re-reads only those.
# CLI: `python qa.py lint [scenes.py]`, `python qa.py owner --t 12.5`, `python qa.py owner --traceback err.txt`.
# A finding that is meant (a memo dict, a mask, a typesetter) is silenced by a pragma on its line, on the def line of
# the function holding it, or (Q1203) on the line that binds the module-level name: `# zoetrope: state-ok` (Q1203),
# `rng-ok` (Q1202), `shadow-ok` (Q1204), `text-ok` (Q1205), `colour-ok` (Q1206).
import ast
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
}
MEANS = {
    "Q1202": "unseeded randomness, clock reads or str hashes",
    "Q1203": "module state written inside functions",
    "Q1204": "engine helpers redefined",
    "Q1205": "text drawn outside the engine text helpers",
    "Q1206": "colour literals inside functions",
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

    def __init__(self, path, folder_tops=None, import_time=()):
        self.path = Path(path)
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

    def is_rng(self, name):
        v = self.top.get(name, (0, None))[1]
        return isinstance(v, ast.Call) and self.qual(v.func, []) in RNG_MAKERS

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
        elif r and isinstance(f.value, ast.Name) and self.is_rng(r):
            self.add(
                "Q1203",
                n,
                f"{r}.{f.attr}() draws from the module-level generator {r}: its stream advances with every frame, "
                "so frames depend on draw order",
                stack,
                extra=[self.top[r][0]],
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
    path = Path(path)
    out, todo = [], [path]
    while todo:
        p = todo.pop(0)
        if p in out:
            continue
        out.append(p)
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
            mods = []
            if isinstance(n, ast.Import):
                mods = [a.name.split(".")[0] for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module and not n.level:
                mods = [n.module.split(".")[0]]
            for m in mods:
                q = path.parent / f"{m}.py"
                if q.exists() and m not in ENGINE_FILES and not m.startswith("qa"):
                    todo.append(q)
    return out


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


def findings(path="scenes.py"):
    """Every static finding in scenes.py and the local modules it imports, as dicts {code, file, line, func, text,
    msg}, plus counts {files, calls, defs, silenced} for the PASS rows."""
    files = local_modules(path)
    trees = {p: ast.parse(p.read_text(encoding="utf-8")) for p in files}
    tops = {p.stem: _Scan(p).top for p in files}
    early = import_time_defs(trees.values())
    out, calls, silenced = [], 0, 0
    for p in files:
        sc = _Scan(p, tops, early).scan()
        out += sc.found
        calls += sc.calls
        silenced += sc.silenced
    sh, ndefs, s2 = shadow_findings(path)
    out += sh
    return out, {
        "files": [p.name for p in files],
        "calls": calls,
        "defs": ndefs,
        "silenced": silenced + s2,
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
    """Rows for run_all.py proof and `qa.py lint`: Q1202 to Q1206 from the ast of scenes.py and its local modules
    (FIX for Q1202, NOTE for the rest), then Q904 and Q905 from the imported module."""
    path = Path(path)
    found, n = findings(path)
    where = ", ".join(n["files"])
    rows = []
    for code in ("Q1202", "Q1203", "Q1204", "Q1205", "Q1206"):
        hits = [d for d in found if d["code"] == code]
        seen = (
            n["defs"] if code == "Q1204" else n["calls"]
        )  # [N checked]: top-level defs for Q1204, else calls
        if not hits:
            rows.append(
                C.row(True, code, f"no {MEANS[code]} in {where}", "", considered=seen)
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
                f"{MEANS[code]}: {len(hits)} found: {listed}{more}{why}",
                FIXES[code],
                note=code != "Q1202",
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
                "environment (see the builder's environment table)",
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
        help="static checks of scenes.py and its local modules (Q1202 to Q1206) and the frame grid (Q904, Q905)",
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
