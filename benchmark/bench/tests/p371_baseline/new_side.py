"""A14 NEW side for ITEM scenarios (plan 4 A14, phase 2): the same scenario file, driven through the CURRENT tree's
entry (`run_tg1_probe` -> the shared core) with the current tree's equivalent fakes (`tg_fixture`).

Besides the normalized result (same schema as the golden) the result carries `_raw`, per run the UNNORMALIZED manifest
and rows, and `_expected`, the independently re-derived values (P311 recipes, never the core's own functions) of the
fields the table allows to change or that the normalizer marks volatile:

  * `probe_code_sha256`: the import closure of the entry + the four generation data files (hard-coded here);
  * `scaffold_policy_sha256`: sha256 of the manifest policy dict;
  * `generation_identity_sha256` (row and manifest): sha256 of the nine P311 composite fields of the manifest runtime;
  * `opencode_exe_sha256`: sha256 of the fake client binary.

`rederive(result)` returns the hook `compare()` takes. The volatile fields are checked inside `run` (an AssertionError
fails the scenario) because both sides' normalized values are the `<volatile>` marker and never reach the comparator."""
from __future__ import annotations

import hashlib
import json
import os
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


def run_item_new_side(scenario):
    with pytest.MonkeyPatch.context() as mp, tempfile.TemporaryDirectory(prefix="p371-new-") as tmp:
        tmp_path = Path(tmp).resolve()
        result, raw = _run_item_scenario(scenario, tmp_path, mp)
        binary = Path(os.environ.get("OPENCODE_PROBE_BIN", ""))
        result["_raw"] = raw
        result["_expected"] = [derive(r["manifest"], binary) if r["manifest"] else None for r in raw]
    return result


POINTERS = {"/probe_code_sha256": "probe_code_sha256", "/scaffold_policy_sha256": "scaffold_policy_sha256",
            "/generation_identity_sha256": "generation_identity_sha256"}


def rederive(result):
    """The hook for `compare(..., rederive=)`: a changed value is accepted only when it equals the independently
    re-derived one of the same run. Policy VALUE changes (`/runtime/policy/*`) are never accepted."""
    import re

    def hook(ptr, old, new):
        m = re.match(r"^/runs/(\d+)/(?:rows/\d+|manifest/runtime)/(?P<key>[a-z_0-9]+)$", ptr)
        if not m or m["key"] not in POINTERS.values():
            return False
        expected = result["_expected"][int(m.group(1))]
        return expected is not None and new == expected[m["key"]]
    return hook
