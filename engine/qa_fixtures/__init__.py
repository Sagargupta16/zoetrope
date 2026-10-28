# qa_fixtures : the planted-defect fixtures `qa.py selftest` runs (Z18). Each module below holds CASES: one input
# (a tiny fake scenes, a scenes file in this folder, a short synthetic WAV or MP4 made at run time in a temp folder),
# the gate it goes through, and what the gate must say about it (code, status, item, time and measured value).
# fake.py and media.py are the shared makers. Nothing here reads outputs/ or downloads anything.

MODULES = ("text", "registry", "source", "files", "sound", "scans", "approval")


def want(
    code,
    status,
    item=None,
    t=None,
    tol=0.05,
    metric=None,
    mtol=None,
    msg=None,
    n=None,
    empty_ok=False,
):
    """What one gate must say about a case: a row of `code` with `status`, its item holding `item` (a substring),
    worst_t within tol seconds of t, metric within mtol of metric (default 5 percent, at least 0.1), msg a substring
    of the message, and exactly n rows of that code and status when n is given. A PASS row that considered 0 items
    fails as EMPTY unless empty_ok (a gate that passes on nothing proves nothing)."""
    if metric is not None and mtol is None:
        mtol = max(0.1, abs(metric) * 0.05)
    return {
        "code": code,
        "status": status,
        "item": item,
        "t": t,
        "tol": tol,
        "metric": metric,
        "mtol": mtol,
        "msg": msg,
        "n": n,
        "empty_ok": empty_ok,
    }


def clean():
    """Every row of the case is PASS or NOTE: no FIX and no NOT CHECKED (a known-good input)."""
    return {"code": "*", "status": "PASS"}


def case(name, run, wants, files=()):
    """One input and its gate: run(fx) returns the rows; fx carries tmp (the case's own temp folder), ff (the ffmpeg
    to run), engine (the engine folder, copied into a temp build folder by the cases that need one) and
    shared(key, make) (a setup made once a run, the approval build). wants lists what the rows must hold; files names
    the scenes files in this folder the case needs (one missing fails the selftest with exit 2)."""
    return {"name": name, "run": run, "wants": list(wants), "files": tuple(files)}
