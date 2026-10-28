# qa_selftest.py : `qa.py selftest`, planted-defect fixtures that prove every gate can still fail (Z18). Each case in
# qa_fixtures/ feeds one gate a known input and states what the gate must report (code, status, item, time and the
# measured value, numbers within a stated tolerance); the template at 1920x1080 and 1080x1920 must pass run_all.py
# proof and full with no FIX and no NOT CHECKED. Exit 0 all held; 1 a gate missed or misreported a planted fault (or a
# control failed); 2 the selftest could not prove a code: no fixture and no EXPECTED_GAPS entry, a fixture file
# missing, a gate that considered 0 items, a case that raised. 1 wins over 2, as FIX wins over NOT CHECKED.
import contextlib
import hashlib
import importlib
import io
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import types
from pathlib import Path

import contract as C

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "qa_fixtures"
SIZES = (
    "1920x1080",
    "1080x1920",
)  # the two known-good controls: the template at 16:9 and 9:16
# a code no fixture can make fire on this machine, with the reason; every other code must have a fixture
EXPECTED_GAPS = {}
SUMMARY = re.compile(
    r"^(PROOF|QA): (.+?) \((\d+) checks, (\d+) FIX, (\d+) NOTE, (\d+) NOT CHECKED\)$",
    re.MULTILINE,
)


def _txt(s):
    return str(s).encode("ascii", "backslashreplace").decode("ascii")


# ---- judging one want against a case's rows ----


def _fits(w, r):
    """Why r does not hold want w ('' when it does): item substring, worst_t within tol, metric within mtol, msg."""
    bad = []
    if w["item"] is not None and w["item"] not in (r.item or ""):
        bad.append(f"item {r.item!r} (want {w['item']!r})")
    if w["t"] is not None and (r.worst_t is None or abs(r.worst_t - w["t"]) > w["tol"]):
        bad.append(f"worst_t {r.worst_t} (want {w['t']:g} +- {w['tol']:g})")
    if w["metric"] is not None and (
        r.metric is None or abs(float(r.metric) - w["metric"]) > w["mtol"]
    ):
        bad.append(f"metric {r.metric} (want {w['metric']:g} +- {w['mtol']:g})")
    if w["msg"] is not None and w["msg"] not in r.msg:
        bad.append(f"message lacks {w['msg']!r}")
    return "; ".join(bad)


def _said(r):
    """What a row said, short: item (a long path as its file name), time and measured value."""
    item = r.item
    if item and len(item) > 60 and ("/" in item or "\\" in item):
        item = Path(item).name
    parts = [f"{item!r}"] if item else []
    if r.worst_t is not None:
        parts.append(f"at {r.worst_t:.3f} s")
    if r.metric is not None:
        parts.append(
            f"metric {r.metric:g}"
            if isinstance(r.metric, (int, float))
            else f"metric {r.metric}"
        )
    if r.considered is not None:
        parts.append(f"{r.considered} considered")
    return ", ".join(parts) or r.msg[:90]


def judge(w, rows):
    """(outcome, detail) of want w on rows: ok, MISSED (the planted fault did not fire), WRONG (it fired with the
    wrong item, time, value or count, or a known-good input fired) or EMPTY (the gate considered 0 items)."""
    if w["code"] == "*":
        bad = [r for r in rows if r.status in (C.FIX, C.NOT_CHECKED)]
        if bad:
            return "WRONG", "; ".join(
                f"{r.status} {r.code} {r.msg[:80]}" for r in bad[:3]
            )
        return "ok", f"{len(rows)} rows, 0 FIX, 0 NOT CHECKED"
    mine = [r for r in rows if r.code == w["code"]]
    if not mine:
        return "MISSED", "no row of this code"
    alarm = [r for r in mine if r.status in (C.FIX, C.NOT_CHECKED)]
    if (
        w["status"] == C.PASS and alarm
    ):  # a known-good input: no row of the code may fail, not just one pass
        return "WRONG", f"got {alarm[0].status}: {alarm[0].msg[:110]}"
    same = [r for r in mine if r.status == w["status"]]
    if not same:
        got = ", ".join(sorted({r.status for r in mine}))
        how = "WRONG" if w["status"] == C.PASS else "MISSED"
        return how, f"got {got}: {mine[0].msg[:110]}"
    if w["n"] is not None and len(same) != w["n"]:
        return "WRONG", f"{len(same)} {w['status']} rows (want {w['n']}): " + "; ".join(
            _said(r) for r in same[:3]
        )
    why = [(_fits(w, r), r) for r in same]
    good = [r for b, r in why if not b]
    if not good:
        return "WRONG", why[0][0] + f" [{_said(why[0][1])}]"
    r = good[0]
    if r.considered == 0 and w["status"] != C.NOT_CHECKED and not w["empty_ok"]:
        return "EMPTY", f"the gate considered 0 items: {r.msg[:100]}"
    return "ok", _said(r)


# ---- the template controls (run_all.py proof and full in a fresh copy, at each size) ----
# The template is the scenes.py beside this file: run the selftest from a fresh copy of engine/ (the smoke folder is
# one; nothing is written there). The run prints which scenes.py it rendered, so a copy that holds a video's own
# scenes.py shows up.


def _copy_engine(dst):
    dst.mkdir(parents=True)
    for p in HERE.glob("*.py"):
        shutil.copy2(p, dst / p.name)
    if (HERE / "requirements.txt").exists():
        shutil.copy2(HERE / "requirements.txt", dst / "requirements.txt")


def _stage(folder, stage, size):
    """One run_all.py stage in folder: (exit code, stdout and stderr, seconds). Its log is kept beside it."""
    t0 = time.perf_counter()
    r = subprocess.run(
        [sys.executable, "run_all.py", stage, "--size", size],
        cwd=folder,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        check=False,
    )
    out = r.stdout + r.stderr
    (folder / f"{stage}.log").write_text(out, encoding="utf-8")
    return r.returncode, out, time.perf_counter() - t0


def _control(size, root, quick, results):
    """The template at size through run_all.py proof, then full (unless quick): each must end with no FIX and no
    NOT CHECKED, and full with its DELIVERED line."""
    folder = root / f"template_{size}"
    try:
        _copy_engine(folder)
        for stage in ("proof",) if quick else ("proof", "full"):
            rc, out, s = _stage(folder, stage, size)
            m = SUMMARY.findall(out)
            label, state, n, fix, note, nc = (
                m[-1] if m else ("", "no summary line", 0, 0, 0, 0)
            )
            fix, nc = int(fix), int(nc)
            done = stage == "proof" or any(
                ln.startswith("DELIVERED ") for ln in out.splitlines()
            )
            ok = rc == 0 and bool(m) and fix == 0 and nc == 0 and done
            say = (
                f"{label}: {state} ({n} checks, {fix} FIX, {note} NOTE, {nc} NOT CHECKED), exit {rc}"
                if m
                else f"exit {rc}, no summary line"
            )
            if stage == "full":
                say += ", DELIVERED" if done else ", no DELIVERED line"
            tail = "" if ok else f" (log {folder / (stage + '.log')})"
            results.append(
                (
                    "ok" if ok else "WRONG",
                    f"template {size} {stage}",
                    f"{say} in {s:.1f} s{tail}",
                )
            )
            if not ok:
                break
    except Exception as e:  # noqa: BLE001 (a control that cannot run is reported, never a crash of the selftest)
        results.append(("ERROR", f"template {size}", f"{type(e).__name__}: {e}"))


# ---- running the cases ----


def _load():
    """(cases, problems): every qa_fixtures module's CASES; a module that is missing or does not import is a
    problem (the selftest cannot vouch for its codes)."""
    cases, problems = [], []
    sys.path.insert(0, str(HERE))  # qa_fixtures is a package beside this file
    importlib.import_module(
        "engine"
    )  # first, so each case's frame size is put back after it
    try:
        names = importlib.import_module("qa_fixtures").MODULES
    except Exception as e:  # noqa: BLE001 (no fixture folder: every code is unproven, said once)
        return [], [f"qa_fixtures/__init__.py: {type(e).__name__}: {e}"]
    for name in names:
        try:
            mod = importlib.import_module(f"qa_fixtures.{name}")
        except Exception as e:  # noqa: BLE001 (a broken fixture module is a finding, not a crash)
            problems.append(f"qa_fixtures/{name}.py: {type(e).__name__}: {e}")
            continue
        cases += [dict(c, module=name) for c in mod.CASES]
    return cases, problems


def _restore(path, mods, engine):
    """Undo what a case left in this process: sys.path, any scenes module it imported, the engine's frame size."""
    sys.path[:] = path
    for k in [k for k in sys.modules if k not in mods]:
        if k == "scenes" or k.startswith(("zt_case_", "_qa_registry_scenes")):
            sys.modules.pop(k, None)
    E = sys.modules.get("engine")
    if E is not None and engine is not None:
        E.W, E.H, E.FPS, E.SS = engine


_SHARED = {}  # key -> (value, error): a setup several cases share is made once a run (the approval build)


def _shared(root, key, make):
    """make(folder)'s value, made once per selftest run in root/shared_<key>; a setup that failed fails every case
    that needs it, with its own error."""
    if key not in _SHARED:
        folder = root / f"shared_{key}"
        folder.mkdir(parents=True, exist_ok=True)
        try:
            _SHARED[key] = (make(folder), None)
        except Exception as e:  # noqa: BLE001 (kept and raised again in every case that shares it)
            _SHARED[key] = (None, e)
    value, err = _SHARED[key]
    if err is not None:
        raise RuntimeError(
            f"the shared {key} setup failed: {type(err).__name__}: {err}"
        )
    return value


def _run_case(c, root, ff):
    """(rows, problem, seconds) for one case; problem is MISSING or ERROR text."""
    missing = [f for f in c["files"] if not (FIXTURES / f).exists()]
    if missing:
        return [], ("MISSING", f"qa_fixtures/{', '.join(missing)} not found"), 0.0
    fx = types.SimpleNamespace(
        tmp=root / c["name"].replace(".", "_"),
        ff=ff,
        engine=HERE,
        shared=lambda key, make: _shared(root, key, make),
    )
    fx.tmp.mkdir(parents=True, exist_ok=True)
    E = sys.modules.get("engine")
    keep = (list(sys.path), set(sys.modules), (E.W, E.H, E.FPS, E.SS) if E else None)
    t0, log = time.perf_counter(), io.StringIO()
    try:
        # what the gates print goes to the case's own log, so the selftest prints one line per fixture
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            rows = list(c["run"](fx))
    except Exception as e:  # noqa: BLE001 (a case that raises cannot prove its codes: exit 2, with where it raised)
        tb = traceback.extract_tb(e.__traceback__)
        own = [f for f in tb if Path(f.filename).resolve().is_relative_to(HERE)] or tb
        where = f" at {Path(own[-1].filename).name}:{own[-1].lineno}" if own else ""
        return (
            [],
            ("ERROR", f"raised {type(e).__name__}{where}: {e}"),
            time.perf_counter() - t0,
        )
    finally:
        _restore(*keep)
        (fx.tmp / "case.log").write_text(log.getvalue(), encoding="utf-8")
    C.write_rows(rows, fx.tmp / "rows.json")  # what the gate said, for a --keep look
    return rows, None, time.perf_counter() - t0


def run(a):
    """qa.py selftest: the template controls start in two threads (subprocesses), every case runs here meanwhile,
    then the coverage of contract.CODES is checked. Prints one line per fixture and the SELFTEST line."""
    clock = time.perf_counter()
    only = {s.strip().upper() for s in (a.only or "").split(",") if s.strip()}
    scope = only or set(C.CODES)
    unknown = sorted(only - set(C.CODES))
    ff = C.find_ffmpeg()
    root = Path(tempfile.mkdtemp(prefix="zoetrope_selftest_"))
    print(f"selftest: fixtures in {FIXTURES}, temp folder {root}")
    lines, controls, threads = [], [], []
    if not only:
        tpl = HERE / "scenes.py"
        if tpl.exists():
            sha = hashlib.sha256(tpl.read_bytes()).hexdigest()[:12]
            print(f"selftest: the template is {tpl} (sha256 {sha})")
        if ff is None:
            controls.append(
                (
                    "ERROR",
                    "template",
                    "no ffmpeg on PATH: the template cannot be rendered",
                )
            )
        else:
            for size in SIZES:
                th = threading.Thread(
                    target=_control, args=(size, root, a.quick, controls)
                )
                th.start()
                threads.append(th)
    cases, problems = _load()
    for p in problems:
        lines.append(("MISSING", "-", "-", "module", p))
        print(_txt(f"MISSING {p}"))
    planned = {}  # code -> wants at the code's failure status, so a code with no fixture at all is seen
    for c in cases:
        for w in c["wants"]:
            if w["code"] in C.CODES and w["status"] == C.CODES[w["code"]][2]:
                planned.setdefault(w["code"], []).append(c["name"])
    chosen = [
        c for c in cases if not only or any(w["code"] in only for w in c["wants"])
    ]
    t_cases = time.perf_counter()
    covered, slow = set(), []
    for c in chosen:
        rows, problem, secs = _run_case(c, root, ff)
        slow.append((secs, c["name"]))
        for w in c["wants"]:
            if only and w["code"] not in only:
                continue
            if w["code"] != "*" and w["code"] not in C.CODES:
                out, detail = "MISSING", f"{w['code']} is not in contract.CODES"
            elif problem:
                out, detail = problem
            else:
                out, detail = judge(w, rows)
            if (
                out == "ok"
                and w["code"] in C.CODES
                and w["status"] == C.CODES[w["code"]][2]
            ):
                covered.add(w["code"])
            lines.append((out, w["code"], w["status"], c["name"], detail))
            print(
                _txt(
                    f"{out:<7} {w['code']:<5} {w['status']:<11} {c['name']:<26} {detail}"
                )
            )
    t_cases = time.perf_counter() - t_cases
    for th in threads:
        th.join()
    for out, name, detail in controls:
        lines.append((out, "-", "PASS", name, detail))
        print(_txt(f"{out:<7} {'-':<5} {'PASS':<11} {name:<26} {detail}"))
    gaps = {k: v for k, v in EXPECTED_GAPS.items() if k in scope}
    for code in sorted(scope - set(planned) - set(gaps)):
        if code in C.CODES:
            lines.append(
                (
                    "UNCOVERED",
                    code,
                    C.CODES[code][2],
                    "-",
                    "no fixture and no EXPECTED_GAPS entry",
                )
            )
            print(
                f"UNCOVERED {code} ({C.CODES[code][0]}, {C.CODES[code][2]}): no fixture makes it fire, and EXPECTED_GAPS has no reason"
            )
    for code in sorted(set(gaps) & set(planned)):
        lines.append(
            ("STALE", code, "-", "-", "in EXPECTED_GAPS but a fixture covers it")
        )
        print(
            f"STALE   {code}: in EXPECTED_GAPS, but {planned[code][0]} makes it fire: drop the gap"
        )
    for code, why in sorted(gaps.items()):
        print(f"gap     {code}: {why}")
    for code in unknown:
        lines.append(("MISSING", code, "-", "-", "not a contract code"))
        print(f"MISSING {code}: --only names a code contract.CODES does not have")
    outcomes = [x[0] for x in lines]
    bad1 = sum(o in ("MISSED", "WRONG") for o in outcomes)
    bad2 = sum(
        o in ("MISSING", "ERROR", "EMPTY", "UNCOVERED", "STALE") for o in outcomes
    )
    code = 1 if bad1 else 2 if bad2 else 0
    k = len(covered & scope)
    slow.sort(reverse=True)
    print(
        f"selftest took {time.perf_counter() - clock:.1f} s ({'quick: no full renders; ' if a.quick else ''}"
        f"cases {t_cases:.1f} s, slowest {', '.join(f'{n} {s:.1f} s' for s, n in slow[:3])})"
    )
    if a.keep or code:
        print(f"kept {root}")
    else:
        shutil.rmtree(root, ignore_errors=True)
    n = len(lines) - outcomes.count("UNCOVERED") - outcomes.count("STALE")
    state = "PASS" if code == 0 else f"FAIL ({bad1} missed or wrong, {bad2} not proven)"
    print(
        f"SELFTEST: {state} ({n} fixtures, {k} of {len(scope)} codes covered, {len(gaps)} expected gaps)"
    )
    return code


def add_cli(sub):
    """qa.py selftest: every gate fed its planted faults and the template controls (Z18)."""
    p = sub.add_parser(
        "selftest",
        help="planted-defect fixtures for every Q code plus the template at both sizes; exit 1 when a gate misses "
        "or misreports one, 2 when a code is unproven",
    )
    p.add_argument(
        "--quick",
        action="store_true",
        help="skip the template's run_all.py full renders (proof only)",
    )
    p.add_argument(
        "--only",
        help="CODE[,CODE]: only the fixtures that check these codes (no template controls)",
    )
    p.add_argument(
        "--keep",
        action="store_true",
        help="keep the temp folder even on a PASS (a failing run always keeps it; its path is printed)",
    )
    p.set_defaults(func=run)
