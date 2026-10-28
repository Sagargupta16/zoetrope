# kit_index.py : the helper index a builder reads instead of paging through code: every top-level public function,
# class and namedtuple in the engine modules next to this file, in ../kits/*/ when that folder exists, and in any
# folder given, with its signature, the first docstring line and file:line. ast only: importing a module runs its
# top-level code (font loading), and inspect.signature evaluates annotations.
#   python kit_index.py [folder ...]            the index
#   python kit_index.py show <name> [folder ...] the source of each top-level def, class or namedtuple called name
#                                                (path:name picks one, for example g04:text)
import ast
import copy
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# the video itself, the runner, and the gate, proof and render internals a scene builder never calls; engine.py
# still lists the contract clock it re-exports (frame_of, snap, stepped ...)
SKIP_HERE = {
    "kit_index.py",
    "scenes.py",
    "run_all.py",
    "proof.py",
    "render.py",
    "contract.py",
}
SKIP_KIT = {"engine_used.py"}  # a build's copy of engine.py, kept only to diff against
RECORDS = {"namedtuple", "NamedTuple", "TypedDict"}


def files(extra=()):
    """[(label, path)] in index order: the engine folder (without the qa_* gate modules), then every kit, then the
    folders given."""
    out = [
        (p.name, p)
        for p in sorted(HERE.glob("*.py"))
        if p.name not in SKIP_HERE and not p.name.startswith("qa_")
    ]
    kits = HERE.parent / "kits"
    folders = sorted(d for d in kits.iterdir() if d.is_dir()) if kits.is_dir() else []
    for d in folders + [Path(x) for x in extra]:
        for p in sorted(d.glob("*.py")):
            if p.name not in SKIP_KIT:
                out.append((f"{d.name}/{p.name}", p))
    return out


def _record(s):
    """(name, call) when s is `Name = namedtuple("Name", ...)` (also NamedTuple and TypedDict calls), else None."""
    if (
        isinstance(s, ast.Assign)
        and len(s.targets) == 1
        and isinstance(s.targets[0], ast.Name)
        and isinstance(s.value, ast.Call)
        and ast.unparse(s.value.func).split(".")[-1] in RECORDS
    ):
        return s.targets[0].id, s.value
    return None


def _fields(call):
    """The field list of a namedtuple-style call as text: "name dur cues=()" (defaults on the last fields)."""
    spec = call.args[1] if len(call.args) > 1 else None
    if isinstance(spec, ast.Constant) and isinstance(spec.value, str):
        names = spec.value.replace(",", " ").split()
    elif isinstance(spec, (ast.List, ast.Tuple)):
        names = [
            e.value if isinstance(e, ast.Constant) else ast.unparse(e.elts[0])
            for e in spec.elts
        ]
    else:
        names = []
    dflt = next((k.value for k in call.keywords if k.arg == "defaults"), None)
    vals = (
        [ast.unparse(e) for e in dflt.elts]
        if isinstance(dflt, (ast.Tuple, ast.List))
        else []
    )
    first = len(names) - len(vals)
    return ", ".join(
        n if i < first else f"{n}={vals[i - first]}" for i, n in enumerate(names)
    )


def entries(path):
    """([{name, line, sig, doc, node}, ...], source): every top-level public def, class and namedtuple in one file,
    plus the names it imports from a skipped module beside it (engine.py's `from contract import frame_of, ...`)."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))
    docs = {}  # Name.__doc__ = "..." set after a namedtuple
    for s in tree.body:
        if (
            isinstance(s, ast.Assign)
            and len(s.targets) == 1
            and isinstance(s.targets[0], ast.Attribute)
            and s.targets[0].attr == "__doc__"
            and isinstance(s.targets[0].value, ast.Name)
            and isinstance(s.value, ast.Constant)
        ):
            docs[s.targets[0].value.id] = str(s.value.value)
    out = []
    for s in tree.body:
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not s.name.startswith("_"):
                out.append(
                    {
                        "name": s.name,
                        "line": s.lineno,
                        "sig": signature(s),
                        "doc": ast.get_docstring(s) or "",
                        "node": s,
                    }
                )
        elif _record(s) and not _record(s)[0].startswith("_"):
            name, call = _record(s)
            out.append(
                {
                    "name": name,
                    "line": s.lineno,
                    "sig": f"{name}({_fields(call)})",
                    "doc": docs.get(name, ""),
                    "node": s,
                }
            )
        elif isinstance(s, ast.ImportFrom) and s.module and not s.level:
            beside = path.with_name(f"{s.module}.py")
            if (
                beside.exists() and beside.name in SKIP_HERE
            ):  # only what the index does not list itself
                there = {e["name"]: e for e in entries(beside)[0]}
                for a in s.names:
                    e = there.get(a.name)
                    if e and not (a.asname or a.name).startswith("_"):
                        out.append(
                            {
                                **e,
                                "name": a.asname or a.name,
                                "line": s.lineno,
                                "doc": f"(from {beside.name}:{e['line']}) {e['doc']}",
                                "from": beside,
                            }
                        )
    return out, src


def signature(n):
    """name(args) for a def; class name(args of __init__ without self) for a class."""
    if not isinstance(n, ast.ClassDef):
        return f"{n.name}({ast.unparse(n.args)})"
    init = next(
        (b for b in n.body if isinstance(b, ast.FunctionDef) and b.name == "__init__"),
        None,
    )
    if init is None:
        return f"class {n.name}"
    a = copy.copy(init.args)
    a.args = a.args[1:]  # without self
    return f"class {n.name}({ast.unparse(a)})"


def index(extra=()):
    total = 0
    for label, p in files(extra):
        ents, _ = entries(p)
        if not ents:
            continue
        print(f"== {label} ({len(ents)})")
        for e in ents:
            doc = e["doc"].strip().splitlines()
            print(
                f"{label}:{e['line']}  {e['sig']}"
                + (f"  # {doc[0][:110]}" if doc else "")
            )
        total += len(ents)
    print(f"{total} helpers; source of one: python kit_index.py show <name>")


def show(name, extra=()):
    where, _, name = name.rpartition(":")
    hits = 0
    for label, p in files(extra):
        if where and where not in label:
            continue
        ents, src = entries(p)
        for e in ents:
            if e["name"] != name:
                continue
            if "from" in e:  # a re-export: the source lives in the module beside it
                src_e = e["from"].read_text(encoding="utf-8")
                label_e = f"{label} -> {e['from'].name}"
            else:
                src_e, label_e = src, label
            n = e["node"]
            lines = src_e.splitlines()
            first = min(
                [d.lineno for d in getattr(n, "decorator_list", [])] + [n.lineno]
            )
            print(f"# {label_e}:{first}-{n.end_lineno}")
            if first < n.lineno:  # decorators sit above the node's own first line
                print("\n".join(lines[first - 1 : n.lineno - 1]))
            print(ast.get_source_segment(src_e, n, padded=True))
            hits += 1
    if not hits:
        print(
            f"no top-level def, class or namedtuple named {name!r}"
            + (f" in {where}" if where else "")
        )
    return 0 if hits else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["show"] and len(args) > 1:
        sys.exit(show(args[1], args[2:]))
    index(args)
