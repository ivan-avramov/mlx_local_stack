"""A14 NEW side for ITEM scenarios (plan 4 A14, phase 2): the same scenario file, driven through the CURRENT tree's
entry (`run_tg1_probe` -> the shared core) with the current tree's equivalent fakes (`tg_fixture`).

Besides the normalized result (same schema as the golden) the result carries `_raw`, per run the UNNORMALIZED manifest
and rows, and `_expected`, the independently re-derived values (P311 recipes, never the core's own functions) of the
fields the table allows to change or that the normalizer marks volatile:

  * `probe_code_sha256`: the import closure of the entry + the four generation data files (hard-coded here);
  * `scaffold_policy_sha256`: sha256 of the manifest policy dict;
  * `generation_identity_sha256` (row and manifest): sha256 of the nine P311 composite fields of the manifest runtime;
  * `opencode_exe_sha256`: sha256 of the fake client binary.

CHAIN scenarios (phase 3): the same scenario file drives the CURRENT tree's chain entry (`run_tg1_chain.main`, the shared
chain core) through the same fake `ChainOps` + `fake_probe.py` the bundle side uses (`test_c147_chain_runner`), in a fresh
pytest process; `chain_rederive()` is the chain-document hook (lifecycle member shas re-derived from the files).

`rederive(result)` returns the hook `compare()` takes. The volatile fields are checked inside `run` (an AssertionError
fails the scenario) because both sides' normalized values are the `<volatile>` marker and never reach the comparator."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from . import normalize as norm_mod
from . import scenario as scn

REPO = Path(__file__).resolve().parents[4]
GENERATION_DATA = ("benchmark/opencode_plugins/toolbounds.js", "benchmark/opencode_plugins/noretry.js",
                   "benchmark/opencode_plugins/datefreeze.js", "benchmark/opencode_bench_v2_web_tg1.json")
COMPOSITE = ("probe_code_sha256", "scaffold_policy_sha256", "opencode_version", "opencode_exe_sha256",
             "opencode_bench_config_sha256", "carrier_source_sha256", "agent_system_sha256", "polyglot_sha",
             "sampling_profile")
ENTRY = "benchmark/run_tg1_probe.py"


def _read_rows(path):
    path = Path(path)
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()] if path.exists() else []


def _read_doc(path):
    path = Path(path)
    return json.loads(path.read_text()) if path.exists() else None


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def derive(manifest, binary):
    """Independent re-derivation from one raw manifest (P311 recipes)."""
    from bench import identity_closure as ic
    rt = manifest["runtime"]
    out = dict(
        probe_code_sha256=ic.closure_sha256(ENTRY, REPO, data=GENERATION_DATA),
        scaffold_policy_sha256=_sha(json.dumps(rt["policy"], sort_keys=True).encode()),
        opencode_exe_sha256=_sha(Path(binary).read_bytes()))
    fields = {k: rt[k] for k in COMPOSITE}
    out["generation_identity_sha256"] = _sha(json.dumps(fields, sort_keys=True, separators=(",", ":")).encode())
    return out


def _run_item_scenario(sc, tmp_path, monkeypatch):
    from bench import structured_grade as sg, token_turn_gate as tg
    from bench.tests.p371_baseline import driver
    from bench.tests.test_tg1_integration import fake_receipts, tg_fixture
    from bench.tests.test_token_turn_gate import event, tool_state, usage
    import importlib

    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    monkeypatch.delenv("MLX_SERVE_CONFIG", raising=False)
    probe = importlib.import_module("run_tg1_probe")
    f = tg_fixture(probe, monkeypatch, tmp_path)
    client = scn.client_of(sc)
    for key, value in (sc.get("gate_policy") or {}).items():
        monkeypatch.setitem(tg.POLICY, key, value)
    n_starts = driver._stream_files(sc, tmp_path, f, usage, event, tool_state)
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
    tmp = {str(tmp_path), os.path.realpath(str(tmp_path))}
    roots = [(str(REPO), "$BUNDLE"), (str(Path(sys.executable).parent), "$PYBIN"), (os.path.realpath(str(REPO)), "$BUNDLE")]
    norm = norm_mod.Normalizer(tmp_roots=tmp, roots=roots, volatile_under={("evidence_sha256", "export")},
                               extra_volatile={"generation_identity_sha256"})
    runs, raw = [], []
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
        root = tmp_path / "opencode_transcripts"
        evidence = sorted(str(p.relative_to(tmp_path)) for p in root.rglob("*")
                          if p.is_file() and "grades" not in p.parts
                          and not any(part.endswith(".final_tree") for part in p.parts)) if root.exists() else []
        rows, manifest = _read_rows(f["out"]), _read_doc(f["mp"])
        runs.append({"outcome": outcome, "rows": rows, "manifest": manifest,
                     "client_calls": len(f["calls"].read_text().splitlines()) if f["calls"].exists() else 0,
                     "evidence": evidence})
        raw.append(json.loads(json.dumps({"rows": rows, "manifest": manifest})))
        _check_fields(rows, manifest, binary, tmp_path, root)
    return {"scenario": sc["name"], "kind": "item", "runs": norm.apply(runs)}, raw


def _check_fields(rows, manifest, binary, tmp_path, root):
    """The new-contract fields every row / manifest must carry, and the volatile fields re-derived independently."""
    assert manifest is not None, "no manifest written"
    rt = manifest["runtime"]
    for key in ("config_id", "arm", "epoch_id", "snapshot_sha256", "snapshot_complete", "snapshot_fields",
                "evidence_policy"):
        assert key in rt, "manifest runtime lacks " + key
    want = derive(manifest, binary)
    assert rt["generation_identity_sha256"] == want["generation_identity_sha256"], "composite does not re-derive"
    assert rt["opencode_exe_sha256"] == want["opencode_exe_sha256"], "exe sha does not re-derive"
    for row in rows:
        for key in ("config_id", "arm", "epoch_id", "snapshot_sha256", "final_tree", "token_accounting"):
            assert key in row, "row lacks " + key
        assert "compaction" not in row and "receipts" not in row
        assert row["generation_identity_sha256"] == want["generation_identity_sha256"]
        tree = row["final_tree"]
        man = Path(str(tree["manifest"]).replace("$STACK_WORKDIR", str(tmp_path)))
        assert man.is_file() and _sha(man.read_bytes()) == tree["manifest_sha256"], "final tree manifest sha"


def run_in_pytest(tmp_path, monkeypatch, scenario):
    """Runs INSIDE a pytest process (so the repository conftest guards apply, as for the bundle side): the scenario on
    the current tree, plus `_raw` and `_expected` (see the module docstring)."""
    result, raw = _run_item_scenario(scenario, tmp_path, monkeypatch)
    binary = Path(os.environ.get("OPENCODE_PROBE_BIN", ""))
    result["_raw"] = raw
    result["_expected"] = [derive(r["manifest"], binary) if r["manifest"] else None for r in raw]
    return result


def run_item_new_side(scenario, timeout=170):
    """Execute `scenario` on the current tree in a fresh pytest subprocess (cwd = benchmark/) and return its result."""
    import subprocess
    driver = REPO / "benchmark/bench/tests/p371_baseline/new_side_driver.py"
    with tempfile.TemporaryDirectory(prefix="p371-new-") as scratch:
        sfile, rfile = Path(scratch) / "scenario.json", Path(scratch) / "result.json"
        sfile.write_text(json.dumps(scenario))
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST", "P371_"))}
        env.update(P371_SCENARIO=str(sfile), P371_RESULT=str(rfile))
        got = subprocess.run([sys.executable, "-m", "pytest", str(driver), "-p", "no:cacheprovider", "-q", "-x", "-s",
                              "-o", "addopts=", "-k", "test_run_scenario"], cwd=str(REPO / "benchmark"), env=env,
                             capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        if got.returncode:
            raise RuntimeError("new-side scenario %s failed (rc %d)\n%s" % (scenario.get("name"), got.returncode,
                                                                           (got.stdout + got.stderr)[-3000:]))
        return json.loads(rfile.read_text())


# ---------------------------------------------------------------------------------------------------- chain scenarios
NEW_ATTEMPT_JSON = re.compile(r"\.a\d+\.json$")
MILESTONE_MARKS = ("START chain", "START pilot", "BARRIER MISMATCH", "BARRIER ok", "RESTART block", "STOP latched",
                   "STOP honoured", "CHAIN ABORT", "ALL LEGS DONE", "ESCALATE", "INCOMPLETE", "CANCEL file written")


def _run_chain_scenario(sc, tmp_path, monkeypatch):
    """The bundle driver's `run_chain_scenario`, on the current tree (same fakes, same result schema)."""
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
    tmp = {str(tmp_path), os.path.realpath(str(tmp_path))}
    roots = [(str(REPO), "$BUNDLE"), (str(Path(sys.executable).parent), "$PYBIN"), (os.path.realpath(str(REPO)), "$BUNDLE")]
    norm = norm_mod.Normalizer(tmp_roots=tmp, roots=roots, volatile_under={("evidence_sha256", "events")})
    files = {}
    for path in sorted(out_root.rglob("*")) if out_root.exists() else []:
        if not path.is_file() or path.name in ("chain.json", "RUNLOG.md"):
            continue
        rel = path.relative_to(out_root).as_posix()
        name = path.name
        if name.endswith(".manifest.json"):
            files[rel] = {"kind": "manifest", "doc": json.loads(path.read_text())}
        elif (".attempt" in name or NEW_ATTEMPT_JSON.search(name)) and name.endswith(".json"):
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
    milestones = []
    for raw in lines:
        ln = raw.split(" ", 1)[-1]            # RunLog prefixes a UTC stamp
        if ln.startswith(("START ",)) and " attempt " in ln:
            ln = ln.split(": ", 1)[0]          # START <stem> attempt n (step, k items)
        elif not ln.startswith(MILESTONE_MARKS):
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


def run_chain_in_pytest(tmp_path, monkeypatch, scenario):
    return _run_chain_scenario(scenario, tmp_path, monkeypatch)


def run_chain_new_side(scenario, timeout=170):
    """Execute a CHAIN `scenario` on the current tree in a fresh pytest subprocess and return its normalized result."""
    import subprocess
    driver = Path(__file__).resolve().parent / "new_side_driver.py"
    with tempfile.TemporaryDirectory(prefix="p371-newc-") as scratch:
        sfile, rfile = Path(scratch) / "scenario.json", Path(scratch) / "result.json"
        sfile.write_text(json.dumps(scenario))
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTEST", "P371_"))}
        env.update(P371_SCENARIO=str(sfile), P371_RESULT=str(rfile))
        got = subprocess.run([sys.executable, "-m", "pytest", str(driver), "-p", "no:cacheprovider", "-q", "-x", "-s",
                              "-o", "addopts=", "-k", "test_run_chain_scenario"], cwd=str(REPO / "benchmark"), env=env,
                             capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        if got.returncode:
            raise RuntimeError("new-side chain scenario %s failed (rc %d)\n%s" % (
                scenario.get("name"), got.returncode, (got.stdout + got.stderr)[-3000:]))
        return json.loads(rfile.read_text())


# independent of the core: the repo files each named lifecycle member of the pre-P371 chain.json stands for
LIFECYCLE_NAMED = {"runner": "benchmark/chains/c147/run_tg1_chain.py", "chain_ops": "benchmark/bench/chain_ops.py",
                   "gate": "scripts/session_pinning_gate.py", "launcher": "benchmark/chains/c147/drive_chain.sh",
                   "launch_tg1": "benchmark/chains/c147/launchers/launch_tg1.sh"}


def chain_rederive(result=None):
    """The hook for `compare(..., rederive=)` on CHAIN results. A changed `/chain_json/lifecycle/<name>` or
    `/chain_json/sha256/<name>` value is accepted only when it equals the sha256 of that repo file NOW (read here, never
    through the core). F8: a NEW `/chain_json/lifecycle/<member>` is accepted only when it is re-derived too: a repo-relative
    member of the runner's static import closure whose value is that file's sha256 now, or `chain_config` whose value is the
    sha256 of the canonical JSON of the result's own `chain_config` document. Every other chain value change (policy, pinned
    identities, rc, attempts ...) is refused."""
    def hook(ptr, old, new):
        m = re.match(r"^/chain_json/(?:lifecycle|sha256)/(?P<name>[a-z_0-9]+)$", ptr)
        if m and m["name"] in LIFECYCLE_NAMED:
            return new == _sha((REPO / LIFECYCLE_NAMED[m["name"]]).read_bytes())
        added = re.match(r"^/chain_json/lifecycle/(?P<name>[^/]+)$", ptr)
        if old is not None or not added:
            return False
        name = added["name"].replace("~1", "/").replace("~0", "~")
        if name == "chain_config":
            cfg = ((result or {}).get("chain_json") or {}).get("chain_config")
            return cfg is not None and new == _sha(json.dumps(cfg, sort_keys=True, separators=(",", ":")).encode())
        if name in _closure_members():
            return new == _sha((REPO / name).read_bytes())
        return False
    return hook


def _closure_members():
    """Repo-relative paths of the runner entry's static import closure (`identity_closure`, the definition of the lifecycle)."""
    from bench import identity_closure as ic
    return {p.resolve().relative_to(REPO.resolve()).as_posix()
            for p in ic.python_closure(REPO / LIFECYCLE_NAMED["runner"], REPO)}


TOOLCHAIN_LOCK_OLD = "ecd97da3ba64b482fda9e8bc91e36794231d34d9bfe63af84b1c2f7f20e73bcf"  # the value the goldens hold
TOOLCHAIN_LOCK_NEW = "46612efe44cdbf4563479cfedadcd943d2320a97a7c4fe2801d253335adfb380"  # sha256 of the S′ bench lock
POINTERS = {"/probe_code_sha256": "probe_code_sha256", "/scaffold_policy_sha256": "scaffold_policy_sha256",
            "/generation_identity_sha256": "generation_identity_sha256"}


def rederive(result):
    """The hook for `compare(..., rederive=)`: a changed value is accepted only when it equals the independently
    re-derived one of the same run. Policy VALUE changes (`/runtime/policy/*`) are never accepted — except the toolchain's
    lock hash, for exactly one pinned pair (P426 T3 / P507): the goldens' `ecd97da3…` (`TOOLCHAIN_LOCK_OLD`) → the sha256 of
    the committed S′ `benchmark/requirements-bench.lock` (`TOOLCHAIN_LOCK_NEW`, `46612efe…`), both literals; any other old or
    new value is a difference, and a later lock change fails here until a reviewed pair replaces this one."""
    import re

    def hook(ptr, old, new):
        if re.match(r"^/runs/\d+/manifest/runtime/policy/toolchain/lock_sha256$", ptr):
            return (old, new) == (TOOLCHAIN_LOCK_OLD, TOOLCHAIN_LOCK_NEW)
        m = re.match(r"^/runs/(\d+)/(?:rows/\d+|manifest/runtime)/(?P<key>[a-z_0-9]+)$", ptr)
        if not m or m["key"] not in POINTERS.values():
            return False
        expected = result["_expected"][int(m.group(1))]
        return expected is not None and new == expected[m["key"]]
    return hook
