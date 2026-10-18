"""A14 baseline driver. Copied INTO the extracted pre-P371 bundle and run as a subprocess:

    <venv>/bin/python -I -B <bundle>/benchmark/bench/tests/p371_driver_run.py --bundle B --scenario S.json --out R.json

`sys.path` = the bundle only (`<bundle>/benchmark`, `.../chains/c147`, `.../bench/tests`) plus the interpreter's own stdlib
and site-packages. A `sys.meta_path` finder REFUSES every import resolved outside those roots, and a post-run
`sys.modules` audit repeats the check (`isolation violation`, exit 3). The scenario then runs under pytest (so the
bundle's own conftest autouse fixtures apply) using the BUNDLE's own `tg_fixture` / `FakeOps` / `fake_probe`.
Stdlib-only at import time; every bundle import happens after the guard is installed."""
from __future__ import annotations

import argparse
import importlib
import importlib.machinery
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------------------------------- guard
STARTUP_PATH = [p for p in sys.path if p]          # stdlib + site-packages (+ .pth entries) of the interpreter, as started


class IsolationViolation(ImportError):
    pass


class Guard:
    """Meta-path finder: first in line, never resolves a module itself; raises when the normal path machinery would
    resolve one to a file outside the allowed roots (the bundle, the stdlib, the interpreter's site-packages)."""

    def __init__(self, bundle, extra_allowed=()):
        import sysconfig
        self.bundle = Path(bundle).resolve()
        roots = [self.bundle, Path(sys.prefix).resolve()]
        roots += [Path(p).resolve() for p in STARTUP_PATH]
        roots += [Path(sysconfig.get_paths()[k]).resolve() for k in ("stdlib", "platstdlib")]
        roots += [Path(p).resolve() for p in extra_allowed]
        self.roots = roots
        self.violations = []

    def allowed(self, path):
        try:
            p = Path(path).resolve()
        except OSError:
            return False
        return any(p == r or r in p.parents for r in self.roots)

    def find_spec(self, name, path=None, target=None):
        spec = importlib.machinery.PathFinder.find_spec(name, path)
        if spec is None:
            return None
        places = [spec.origin] if spec.origin and spec.has_location else list(spec.submodule_search_locations or [])
        for place in places:
            if place and not self.allowed(place):
                self.violations.append("%s -> %s" % (name, place))
                raise IsolationViolation("P371 isolation violation: module %r resolves outside the bundle: %s"
                                         % (name, place))
        return None

    def audit(self):
        foreign, checked, in_bundle = [], 0, 0
        for name, module in list(sys.modules.items()):
            file = getattr(module, "__file__", None)
            if not file:
                continue
            checked += 1
            if self.bundle in Path(file).resolve().parents:
                in_bundle += 1
            if not self.allowed(file):
                foreign.append("%s -> %s" % (name, file))
        return {"modules_checked": checked, "bundle_modules": in_bundle,
                "foreign_modules": sorted(set(foreign + self.violations))}


def set_paths(bundle):
    bundle = Path(bundle).resolve()
    ours = [bundle / "benchmark", bundle / "benchmark/chains/c147", bundle / "benchmark/bench/tests"]
    sys.path[:] = [str(p) for p in ours] + [p for p in STARTUP_PATH]
    return bundle


# ---------------------------------------------------------------------------------------------------- scenario code
# (runs under pytest inside the bundle; imports only after the guard is installed)
def _normalizer(bundle, tmp_path, volatile_under=(), extra_volatile=()):
    from bench.tests import p371_normalize as norm
    roots = [(str(bundle), "$BUNDLE"), (str(Path(sys.executable).parent), "$PYBIN"), (os.path.realpath(str(bundle)), "$BUNDLE")]
    tmp = {str(tmp_path), os.path.realpath(str(tmp_path))}
    return norm.Normalizer(tmp_roots=tmp, roots=roots, volatile_under=volatile_under,
                           extra_volatile=extra_volatile)


def _read_rows(path):
    path = Path(path)
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def _read_doc(path):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else None


def _stream_files(sc, tmp_path, f, usage, event, tool_state):
    """events.jsonl + export.json from the scenario's `stream` (null keeps tg_fixture's own defaults)."""
    stream = sc.get("stream")
    n_starts = 2
    if stream is not None:
        if stream.get("raw") is not None:
            events = stream["raw"]
            n_starts = sum(1 for e in events if e.get("type") == "step_start")
            messages = None
        else:
            events, messages = [], []
            reqs = stream.get("requests") or []
            for k, req in enumerate(reqs, 1):
                mid = "m%d" % k
                events.append(event("step_start", mid))
                for j, call in enumerate(req.get("calls") or []):
                    events.append(event("tool_use", mid, partID="%s-%d" % (mid, j), tool="shell", state=tool_state(call)))
                events.append(event("step_finish", mid, tokens=usage(req.get("output", 10), req.get("input", 100))))
                messages.append(dict(id=mid, type="assistant", tokens=usage(req.get("output", 10), req.get("input", 100)),
                                     finish="stop", content=[]))
            if stream.get("open_request"):
                mid = "m%d" % (len(reqs) + 1)
                events.append(event("step_start", mid))
                messages.append(dict(id=mid, type="assistant", error=dict(type="aborted"), content=[]))
            n_starts = len(reqs) + (1 if stream.get("open_request") else 0)
        (tmp_path / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
        if messages is not None:
            f["export"].write_text(json.dumps(dict(info=dict(id="s1"), messages=messages)))
    exp = sc.get("export")
    if exp and exp.get("patch_last"):
        doc = json.loads(f["export"].read_text())
        doc["messages"][-1].update(exp["patch_last"])
        f["export"].write_text(json.dumps(doc))
    return n_starts


def run_item_scenario(sc, tmp_path, monkeypatch, bundle):
    import threading
    import time
    from bench import tg1_runner as runner, structured_grade as sg, token_turn_gate as tg
    from bench.tests import p371_scenario as scn
    from bench.tests.test_tg1_integration import tg_fixture, fake_receipts
    from bench.tests.test_token_turn_gate import event, usage, tool_state

    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    monkeypatch.delenv("MLX_SERVE_CONFIG", raising=False)
    probe = importlib.import_module("run_tg1_probe")
    f = tg_fixture(probe, monkeypatch, tmp_path)
    client = scn.client_of(sc)
    for key, value in (sc.get("gate_policy") or {}).items():
        monkeypatch.setitem(tg.POLICY, key, value)
    n_starts = _stream_files(sc, tmp_path, f, usage, event, tool_state)
    binary = Path(os.environ["OPENCODE_PROBE_BIN"])
    text = binary.read_text()
    marker = tmp_path / "client.started"
    if n_starts != 2:
        text = text.replace(fake_receipts([("s1", 2)]), fake_receipts([("s1", n_starts)]))
    if not client["writes_solution"]:
        text = text.replace('printf "answer = 42\\n" > solution.py', ":")
    if client["edits_protected_test"]:
        text = text.replace("run)\n", "run)\necho hacked > solution_test.py\n", 1)
    if client["linger_s"]:
        text = text.replace('\nexit "$(cat ', "\ntouch %s\nsleep %s\nexit \"$(cat " % (marker, client["linger_s"]), 1)
    if client["export_rc"]:
        text = text.replace("session) cat ", "session) echo export-boom >&2; exit %d;; session_unused) cat " % client["export_rc"], 1)
    elif client["export_stdout"] is not None:
        text = text.replace("session) cat ", "session) echo %s;; session_unused) cat " % client["export_stdout"], 1)
    binary.write_text(text)
    (tmp_path / "rc").write_text(str(client["rc"]))
    if sc.get("grade") == "transport_abort":
        def boom(*a, **k):
            raise tg.TransportAbort("grader infrastructure down")
        monkeypatch.setattr(sg, "grade", boom)
    # The fixture's fake client binary and export embed the per-test temp path, so the exe hash, the export hash and the
    # generation composite (which includes the exe hash) are machine data here, not scenario data.
    norm = _normalizer(bundle, tmp_path, volatile_under={("evidence_sha256", "export")},
                       extra_volatile={"generation_identity_sha256"})
    runs = []
    cancel = tmp_path / "leg.CANCEL"
    for spec in sc["runs"]:
        extra = list(spec.get("extra") or [])
        for step in spec.get("before") or []:
            if step == "identity_change":
                f["identity"]["create_time"] += 1
        trigger = spec.get("cancel")
        if trigger:
            extra += ["--cancel-file", str(cancel)]
        if trigger == "client_started":
            def watch():
                end = time.time() + 30
                while time.time() < end and not marker.exists():
                    time.sleep(0.02)
                cancel.write_text("")
            threading.Thread(target=watch, daemon=True).start()
        elif trigger == "final_grade":
            real = sg.grade

            def grade(*a, _real=real, **k):
                if k.get("final"):
                    cancel.write_text("")
                return _real(*a, **k)
            monkeypatch.setattr(sg, "grade", grade)
        started = time.time()
        try:
            rc = f["run"](spec["items"], extra=extra, frozen=sc.get("frozen_date") or "Mon Jan 05 2026")
            outcome = {"kind": "ok", "rc": rc}
        except SystemExit as exc:
            code = exc.code
            outcome = {"kind": "refused" if isinstance(code, str) and code.startswith("REFUSED") else "exit",
                       "code": code if not isinstance(code, str) else code[:300]}
        if time.time() - started > 55:
            raise AssertionError("scenario step too slow")
        evidence = sorted(str(p.relative_to(tmp_path)) for p in (tmp_path / "opencode_transcripts").rglob("*")
                          if p.is_file() and "grades" not in p.parts) if (tmp_path / "opencode_transcripts").exists() else []
        runs.append({"outcome": outcome, "rows": _read_rows(f["out"]), "manifest": _read_doc(f["mp"]),
                     "client_calls": len(f["calls"].read_text().splitlines()) if f["calls"].exists() else 0,
                     "evidence": evidence})
    return {"scenario": sc["name"], "kind": "item", "runs": norm.apply(runs)}


def run_chain_scenario(sc, tmp_path, monkeypatch, bundle):
    import threading
    import time
    from bench.tests import test_c147_chain_runner as T

    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    out_root = tmp_path / ("c147-smoke" if "--smoke" in sc["argv"] else "c147")    # a smoke run refuses the real dir
    state = {"snapshots": {}, "last": {}}

    def attempts_launched():
        p = tmp_path / "fakestate" / "invocations.jsonl"
        return len(p.read_text().splitlines()) if p.exists() else 0

    def snap():
        k = attempts_launched()
        if not out_root.exists():
            return
        for path in sorted(out_root.glob("*/*.manifest.json")):
            try:
                doc = json.loads(path.read_text())
            except ValueError:
                continue
            blob = json.dumps(doc, sort_keys=True)
            if state["last"].get(str(path)) != blob and doc.get("run_id"):
                state["last"][str(path)] = blob
                stem = path.parent.name + "/" + path.name[:-len(".manifest.json")]
                state["snapshots"].setdefault(stem, {})[str(k)] = doc

    class Ops(T.FakeOps):
        def power_ok(self):
            snap()
            return super().power_ok()

    uni = tmp_path / "universe.json"
    uni.write_text(json.dumps({"items": {**{"python/p%d" % i: {} for i in range(1, 7)},
                                         **{"go/g%d" % i: {} for i in range(1, 7)}}}))
    ops = Ops(tmp_path)
    if sc.get("metrics") is not None:
        ops.metrics = sc["metrics"]
    lines = []
    env = dict(wd=tmp_path, ops=ops, uni=uni, lines=lines, out=out_root)
    extra_env = dict(sc.get("extra_env") or {})
    if sc.get("manifest_override"):
        extra_env["FAKE_MANIFEST_OVERRIDE"] = json.dumps(sc["manifest_override"])
    helper = None
    spec = sc.get("helper")
    if spec:
        def helper():
            end = time.time() + 60
            while time.time() < end and not any(spec["stop_after_log"] in ln for ln in lines):
                time.sleep(0.02)
            time.sleep(spec.get("delay_s", 0))
            (out_root / "STOP").write_text("")
    monkeypatch.setattr(sys, "argv", ["run_tg1_chain.py"] + list(sc["argv"]))
    try:
        rc = T.run(env, list(sc["argv"]), timers=sc.get("timers"), plan=sc.get("plan"), behaviour=sc.get("behaviour"),
                   extra_env=extra_env, helper=helper, timeout=100)
    finally:
        ops.cancel()
    snap()
    # the fake probe appends a timing-dependent number of filler lines to events.jsonl: its hash is not scenario data
    norm = _normalizer(bundle, tmp_path, volatile_under={("evidence_sha256", "events")})
    files = {}
    for path in sorted(out_root.rglob("*")) if out_root.exists() else []:
        if not path.is_file() or path.name in ("chain.json", "RUNLOG.md"):
            continue
        rel = path.relative_to(out_root).as_posix()
        name = path.name
        if name.endswith(".manifest.json"):
            files[rel] = {"kind": "manifest", "doc": json.loads(path.read_text())}
        elif ".attempt" in name and name.endswith(".json"):
            files[rel] = {"kind": "attempt_json", "doc": json.loads(path.read_text())}
        elif name.endswith(".jsonl"):
            files[rel] = {"kind": "rows", "rows": _read_rows(path)}
        elif name.endswith(".log"):
            files[rel] = {"kind": "attempt_log", "lines": [ln for ln in path.read_text(errors="replace").splitlines()
                                                           if ln and not ln.startswith("{")]}
        elif name.endswith((".CANCEL", ".ACK")) or name == "STOP":
            files[rel] = {"kind": "cancel" if name.endswith(".CANCEL") else "ack" if name.endswith(".ACK") else "stop",
                          "text": path.read_text().strip()}
        else:
            files[rel] = {"kind": "other", "size": path.stat().st_size}
    inv = tmp_path / "fakestate" / "invocations.jsonl"
    invocations = [json.loads(x)["argv"] for x in inv.read_text().splitlines()] if inv.exists() else []
    import re
    marks = ("START chain", "START pilot", "BARRIER MISMATCH", "BARRIER ok", "RESTART block", "STOP latched",
             "STOP honoured", "CHAIN ABORT", "ALL LEGS DONE", "ESCALATE", "INCOMPLETE", "CANCEL file written")
    milestones = []
    for raw in lines:
        ln = raw.split(" ", 1)[-1]            # RunLog prefixes a UTC stamp
        if ln.startswith(("START ",)) and " attempt " in ln:
            ln = ln.split(": ", 1)[0]          # START <stem> attempt n (step, k items)
        elif not ln.startswith(marks):
            continue
        short = re.sub(r"pid \d+", "pid <pid>", ln.split(";")[0] if ln.startswith("CANCEL file") else ln)
        short = re.sub(r"T_coop=.*", "", short)
        if not milestones or milestones[-1] != short:
            milestones.append(short)
    result = {"scenario": sc["name"], "kind": "chain", "rc": rc, "shapes": sc.get("shapes") or [],
              "chain_json": json.loads((out_root / "chain.json").read_text()), "files": files,
              "invocations": invocations, "ops_calls": [list(c) for c in ops.calls],
              "step_manifests": state["snapshots"], "milestones": milestones}
    if rc != sc["expect_rc"]:
        raise AssertionError("chain rc %r != expected %r; log tail: %s" % (rc, sc["expect_rc"], lines[-8:]))
    return norm.apply(result)


def test_run_scenario(tmp_path, monkeypatch):
    """Entry used by `main` through pytest: scenario path and result path come from the environment."""
    from bench.tests import p371_scenario as scn
    sc = scn.load(os.environ["P371_SCENARIO"])
    bundle = Path(os.environ["P371_BUNDLE"])
    fn = run_item_scenario if sc["kind"] == "item" else run_chain_scenario
    from bench import proc_guard
    from bench.tests import p371_hermetic_scan
    undo = p371_hermetic_scan.install(proc_guard, os.getpid())      # the OLD guard sees only this process's family
    try:
        result = fn(sc, tmp_path, monkeypatch, bundle)
    finally:
        undo()
    Path(os.environ["P371_RESULT"]).write_text(json.dumps(result, indent=1, sort_keys=True))


# ---------------------------------------------------------------------------------------------------- entry
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--plant", help="TEST ONLY: import this file's module from outside the bundle to prove the guard fires")
    a = ap.parse_args(argv)
    sys.dont_write_bytecode = True
    bundle = set_paths(a.bundle)
    guard = Guard(bundle)
    sys.meta_path.insert(0, guard)
    os.chdir(bundle)
    os.environ.pop("PYTHONPATH", None)
    os.environ.update(P371_SCENARIO=str(Path(a.scenario).resolve()), P371_BUNDLE=str(bundle), P371_RESULT=str(a.out))
    if a.plant:
        plant = Path(a.plant)
        sys.path.append(str(plant.parent))
        try:
            importlib.import_module(plant.stem)
        except IsolationViolation as exc:
            print(str(exc), file=sys.stderr)
            print("isolation violation: planted import refused", file=sys.stderr)
            return 3
    import pytest
    here = Path(__file__).resolve()
    rc = pytest.main([str(here), "-p", "no:cacheprovider", "-q", "-x", "-s", "--rootdir", str(bundle / "benchmark"),
                      "-o", "addopts=", "--import-mode=prepend", "-k", "test_run_scenario"])
    audit = guard.audit()
    if audit["foreign_modules"]:
        print("isolation violation: modules loaded from outside the bundle: %s" % audit["foreign_modules"][:10],
              file=sys.stderr)
        return 3
    if rc != 0:
        print("scenario run failed (pytest rc %s)" % int(rc), file=sys.stderr)
        return 1
    out = Path(a.out)
    doc = json.loads(out.read_text())
    doc["_audit"] = audit
    out.write_text(json.dumps(doc, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
