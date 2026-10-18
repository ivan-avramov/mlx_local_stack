"""P371 phase 1b (plan 4 A14): the isolated pre-P371 baseline harness, its JSON-pointer comparator and the pending
differential tests. Test-only: nothing under benchmark/ outside bench/tests may import `p371_baseline`.

Layers:
  (a) bundle: `git archive 0c9bd32a` minus benchmark/results + docs, sha256 manifest, session-cached.
  (b) import guard: a driver run that loads a current-tree module FAILS.
  (c) every scenario runs on the bundle (the bundle's own code and fakes) and equals its stored golden output.
  (d) `compare` unit tests: the plan's exact table.
  (e) `test_item_differential` / `test_chain_differential`: new side = `run_new_side` (phase 2/3), xfail(strict) now.
Regenerate goldens: `P371_REGEN_GOLDEN=1 ../.venv-bench/bin/python -m pytest bench/tests/test_p371_baseline.py -k golden`."""
from __future__ import annotations

import copy
import getpass
import json
import os
import re
import socket
import subprocess
from pathlib import Path

import pytest

from bench.tests.p371_baseline import bundle as bundle_mod
from bench.tests.p371_baseline import compare as cmp_mod
from bench.tests.p371_baseline import normalize as norm_mod
from bench.tests.p371_baseline import runner as run_mod

BENCH_DIR = Path(__file__).resolve().parents[2]            # .../benchmark
REPO = BENCH_DIR.parent
ITEM = ["item_normal_pass", "item_tamper", "item_client_inactivity", "item_stall_kill", "item_loop_kill",
        "item_hard_ceiling_kill", "item_cooperative_cancel", "item_grader_failure", "item_export_failure",
        "item_transport_abort", "item_resume_refusal"]
CHAIN = ["chain_shape_a_pilot", "chain_shape_a_reload", "chain_shape_bc_s1", "chain_shape_d_smoke",
         "chain_barrier_mismatch", "chain_block_restart", "chain_stop", "chain_idle_escalation"]
NO_HISTORY = os.environ.get("P371_NO_GIT_HISTORY") == "1"
_RUNS = {}


@pytest.fixture(scope="session")
def bundle(tmp_path_factory):
    try:
        bundle_mod.check_history()
    except bundle_mod.BundleError as exc:
        if NO_HISTORY:
            pytest.skip("P371_NO_GIT_HISTORY=1: " + str(exc))
        pytest.fail("git history for the baseline commit is missing (shallow clone?); set P371_NO_GIT_HISTORY=1 to "
                    "skip explicitly: " + str(exc))
    dest = tmp_path_factory.mktemp("p371-bundle") / "bundle"
    bundle_mod.make_bundle(dest)
    return dest


def old_run(bundle, name):
    if name not in _RUNS:
        _RUNS[name] = run_mod.run_old_side(bundle, run_mod.load_scenario(name))
    return _RUNS[name]


# ------------------------------------------------------------------------------------------------ (a) the bundle
def test_bundle_contents_and_exclusions(bundle):
    assert (bundle / "benchmark/bench/tg1_runner.py").is_file()
    assert (bundle / "benchmark/chains/c147/run_tg1_chain.py").is_file()
    assert (bundle / "benchmark/chains/c147/fake_probe.py").is_file()
    assert (bundle / "main_models.yaml").is_file() and (bundle / "scripts").is_dir()
    assert (bundle / "benchmark/m62/universe.json").is_file()
    assert (bundle / "benchmark/opencode_plugins/noretry.js").is_file()
    assert not (bundle / "benchmark/results").exists() and not (bundle / "docs").exists()
    assert not (bundle / ".venv-bench").exists() and not (bundle / "benchmark/bench/host.py").exists()


def test_bundle_manifest_is_complete_and_stable(bundle, tmp_path):
    man = json.loads((bundle / "BUNDLE_MANIFEST.json").read_text())
    assert man["commit"].startswith(bundle_mod.COMMIT) and len(man["commit"]) == 40
    assert man["excluded"] == ["benchmark/results", "docs"]
    files = man["files"]
    assert "benchmark/bench/tg1_runner.py" in files and "BUNDLE_MANIFEST.json" not in files
    assert not [f for f in files if f.startswith(("benchmark/results/", "docs/"))]
    for rel in ("benchmark/bench/tg1_runner.py", "main_models.yaml"):
        import hashlib
        assert files[rel] == hashlib.sha256((bundle / rel).read_bytes()).hexdigest()
    assert bundle_mod.verify_manifest(bundle) == []
    again = bundle_mod.make_bundle(tmp_path / "again")
    assert again == man                                          # byte-identical inputs -> identical manifest
    (bundle / "scratch-extra.txt").write_text("x")
    try:
        assert bundle_mod.verify_manifest(bundle) == ["unlisted file: scratch-extra.txt"]
    finally:
        (bundle / "scratch-extra.txt").unlink()


def test_missing_commit_or_shallow_history_raises_a_clear_error(tmp_path):
    with pytest.raises(bundle_mod.BundleError, match="not found|shallow"):
        bundle_mod.check_history(commit="0" * 40)
    with pytest.raises(bundle_mod.BundleError, match="not found|shallow"):
        bundle_mod.make_bundle(tmp_path / "nope", commit="0" * 40)
    calls = []

    def fake_git(args, cwd):
        calls.append(args)
        return "true" if args[:2] == ["rev-parse", "--is-shallow-repository"] else ""
    with pytest.raises(bundle_mod.BundleError, match="shallow"):
        bundle_mod.check_history(git=fake_git)


# ------------------------------------------------------------------------------------------------ (b) import guard
def test_a_planted_current_tree_import_fails_the_driver_run(bundle):
    plant = BENCH_DIR / "bench" / "host.py"                       # exists only in the current tree
    with pytest.raises(run_mod.DriverError, match="isolation"):
        run_mod.run_old_side(bundle, run_mod.load_scenario("item_normal_pass"), plant=str(plant))


def test_the_driver_audit_reports_modules_checked_and_no_foreign_module(bundle):
    result = old_run(bundle, "item_normal_pass")
    audit = result["_audit"]
    assert audit["foreign_modules"] == [] and audit["modules_checked"] > 100 and audit["bundle_modules"] > 20


def test_nothing_outside_bench_tests_imports_the_baseline_harness():
    offenders = []
    for path in BENCH_DIR.rglob("*.py"):
        rel = path.relative_to(BENCH_DIR).as_posix()
        if rel.startswith(("bench/tests/", "results/")) or "/.venv" in rel:
            continue
        if "p371_baseline" in path.read_text(errors="replace"):
            offenders.append(rel)
    assert offenders == []


# ------------------------------------------------------------------------------------------------ (c) scenarios
def test_scenario_set_is_complete():
    names = set(run_mod.scenario_names())
    assert set(ITEM) | set(CHAIN) <= names
    for name in names:
        s = run_mod.load_scenario(name)
        assert s["name"] == name and s["kind"] in ("item", "chain") and s["doc"]


@pytest.mark.parametrize("name", ITEM + CHAIN)
def test_scenario_runs_on_the_bundle_and_matches_its_golden(bundle, name):
    result = old_run(bundle, name)
    assert result and result["scenario"] == name
    clean = {k: v for k, v in result.items() if not k.startswith("_")}
    if run_mod.scenario_kind(name) == "item":
        assert clean["runs"] and all(r["outcome"] for r in clean["runs"])
    else:
        assert clean["chain_json"] and clean["files"] and isinstance(clean["rc"], int)
    if os.environ.get("P371_REGEN_GOLDEN") == "1":
        run_mod.write_golden(name, clean)
    assert run_mod.load_golden(name) == clean, "stored golden differs from the regenerated baseline"


def test_goldens_carry_no_pii_or_machine_paths():
    # machine-local identifiers come from the running environment, never literals in the repository (public repo)
    local = {getpass.getuser(), socket.gethostname().split(".")[0]}
    try:
        local.add(subprocess.run(["git", "config", "user.email"], capture_output=True, text=True).stdout.strip())
    except OSError:
        pass
    words = "|".join(re.escape(w) for w in sorted(local) if len(w) >= 3)
    bad = re.compile(r"/Users/|/private/var|/var/folders|/home/|\.local\b" + ("|" + words if words else ""))
    for name in run_mod.scenario_names():
        text = (run_mod.GOLDEN_DIR / f"{name}.json").read_text()
        assert not bad.search(text), (name, bad.search(text).group(0))


def test_item_scenarios_cover_the_planned_paths(bundle):
    seen = {}
    for name in ITEM:
        for run in old_run(bundle, name)["runs"]:
            outcome = run["outcome"]
            seen.setdefault(name, []).append(outcome.get("kind"))
    assert "refused" in seen["item_resume_refusal"] and "ok" in seen["item_normal_pass"]
    rows = lambda n: [r for run in old_run(bundle, n)["runs"] for r in run["rows"]]          # noqa: E731
    assert rows("item_normal_pass")[0]["passed"] is True
    assert rows("item_tamper")[0]["test_modified"] is True
    assert rows("item_client_inactivity")[0]["nonconv_kind"] == "client_inactivity"
    assert rows("item_stall_kill")[0]["nonconv_kind"] == "stalled"
    assert rows("item_loop_kill")[0]["nonconv_kind"] == "looping"
    assert rows("item_hard_ceiling_kill")[0]["nonconv_kind"] == "hard_ceiling"
    assert rows("item_cooperative_cancel") == []
    for name in ("item_grader_failure", "item_export_failure", "item_transport_abort"):
        assert rows(name) == [] and old_run(bundle, name)["runs"][0]["outcome"]["kind"] == "refused"


# ------------------------------------------------------------------------------------------------ (d) compare
def sample():
    row = {"id": "python/one", "passed": True, "generation_identity_sha256": "g" * 64,
           "gate": {"requests_completed": 2}, "evidence_sha256": {"events": "e" * 64}}
    man = {"model": "m", "runtime": {"scaffold": "opencode-v2-web-tg1", "probe_code_sha256": "p" * 64,
                                     "scaffold_policy_sha256": "s" * 64, "generation_identity_sha256": "g" * 64,
                                     "policy": {"gate": {"identical_calls": 8}, "scaffold": "x"}}}
    return {"scenario": "x", "kind": "item", "runs": [{"outcome": {"kind": "ok", "rc": 0}, "rows": [row],
                                                       "manifest": man, "client_calls": 1}]}


def plain(result):
    return copy.deepcopy(result)


def test_equal_results_pass():
    old = sample()
    res = cmp_mod.compare(old, plain(old), cmp_mod.TABLE)
    assert res.ok and res.failures == []


def test_a_planted_unlisted_difference_fails_and_names_the_pointer():
    old, new = sample(), sample()
    new["runs"][0]["rows"][0]["passed"] = False
    new["runs"][0]["rows"][0]["gate"]["requests_completed"] = 3
    res = cmp_mod.compare(old, new, cmp_mod.TABLE)
    assert not res.ok
    pointers = " ".join(res.failures)
    assert "/runs/0/rows/0/passed" in pointers and "/runs/0/rows/0/gate/requests_completed" in pointers


def test_an_unlisted_addition_and_a_removal_fail():
    old, new = sample(), sample()
    new["runs"][0]["rows"][0]["surprise"] = 1
    del new["runs"][0]["rows"][0]["evidence_sha256"]
    res = cmp_mod.compare(old, new, cmp_mod.TABLE)
    assert any("surprise" in f for f in res.failures) and any("evidence_sha256" in f for f in res.failures)


@pytest.mark.parametrize("pointer,value", [
    ("config_id", "tg1"), ("arm", None), ("epoch_id", "e1"), ("snapshot_sha256", "a" * 64),
    ("final_tree", {"files": 3}), ("token_accounting", {"x": 1})])
def test_allowed_row_additions_pass(pointer, value):
    old, new = sample(), sample()
    new["runs"][0]["rows"][0][pointer] = value
    assert cmp_mod.compare(old, new, cmp_mod.TABLE).ok


@pytest.mark.parametrize("key", ["config_id", "arm", "epoch_id", "snapshot_sha256", "snapshot_complete",
                                 "snapshot_fields", "evidence_policy"])
def test_allowed_manifest_runtime_additions_pass(key):
    old, new = sample(), sample()
    new["runs"][0]["manifest"]["runtime"][key] = "v"
    assert cmp_mod.compare(old, new, cmp_mod.TABLE).ok


def test_policy_additions_pass_but_a_changed_pre_p371_policy_key_fails():
    old, new = sample(), sample()
    new["runs"][0]["manifest"]["runtime"]["policy"]["watchdog"] = {"mode": "off"}
    assert cmp_mod.compare(old, new, cmp_mod.TABLE).ok
    new["runs"][0]["manifest"]["runtime"]["policy"]["gate"]["identical_calls"] = 9
    res = cmp_mod.compare(old, new, cmp_mod.TABLE)
    assert not res.ok and any("/runtime/policy/gate/identical_calls" in f for f in res.failures)


@pytest.mark.parametrize("where,key", [("runs/0/manifest/runtime", "probe_code_sha256"),
                                       ("runs/0/manifest/runtime", "scaffold_policy_sha256"),
                                       ("runs/0/manifest/runtime", "generation_identity_sha256"),
                                       ("runs/0/rows/0", "generation_identity_sha256")])
def test_allowed_value_changes_need_an_independent_rederivation(where, key):
    old, new = sample(), sample()
    node = new
    for part in where.split("/"):
        node = node[int(part)] if part.isdigit() else node[part]
    node[key] = "n" * 64
    assert not cmp_mod.compare(old, new, cmp_mod.TABLE).ok                     # no hook: not accepted
    seen = []
    ok = cmp_mod.compare(old, new, cmp_mod.TABLE, rederive=lambda ptr, o, n: seen.append(ptr) or n == "n" * 64)
    assert ok.ok and seen
    bad = cmp_mod.compare(old, new, cmp_mod.TABLE, rederive=lambda ptr, o, n: False)
    assert not bad.ok


def test_a_rederived_policy_value_change_passes_only_with_the_hook():
    old, new = sample(), sample()
    new["runs"][0]["manifest"]["runtime"]["policy"]["scaffold"] = "y"
    assert not cmp_mod.compare(old, new, cmp_mod.TABLE).ok
    assert cmp_mod.compare(old, new, cmp_mod.TABLE, rederive=lambda ptr, o, n: ptr.endswith("/policy/scaffold")).ok


@pytest.mark.parametrize("key", ["compaction", "receipts"])
def test_forbidden_keys_in_tg1_rows_fail_even_though_additions_may_be_hooked(key):
    old, new = sample(), sample()
    new["runs"][0]["rows"][0][key] = {"anything": 1}
    res = cmp_mod.compare(old, new, cmp_mod.TABLE, rederive=lambda *a: True)
    assert not res.ok and any("FORBIDDEN" in f and f"/{key}" in f for f in res.failures)


def chain_sample():
    leg = {"rows": [{"id": "python/a", "passed": True}, {"id": "python/b", "passed": True}],
           "manifests": {"pilot": {"run_id": "R1", "model": "m"}, "full": {"run_id": "R2", "model": "m"}},
           "attempts": [{"step": "pilot", "rc": 0}, {"step": "full", "rc": 0}]}
    return {"scenario": "c", "kind": "chain", "rc": 0, "shapes": ["b"],
            "chain_json": {"status": "finished", "rc": 0, "attempts": [], "restarts": [], "lifecycle": {"runner": "a"},
                           "sha256": {"runner": "a"}},
            "files": {}, "legs": {"s1/stem": leg}, "invocations": [], "ops_calls": []}


def test_chain_json_new_keys_are_listed_and_everything_else_is_compared():
    old, new = chain_sample(), chain_sample()
    for key in ("progress", "chain_config", "snapshots", "epoch_id", "artifacts"):
        new["chain_json"][key] = {"x": 1}
    new["chain_json"]["lifecycle"]["chain_core"] = "z"                         # a new lifecycle member
    assert cmp_mod.compare(old, new, cmp_mod.TABLE).ok
    new["chain_json"]["rc"] = 2
    res = cmp_mod.compare(old, new, cmp_mod.TABLE)
    assert not res.ok and any("/chain_json/rc" in f for f in res.failures)


def test_chain_lifecycle_and_sha256_value_changes_need_rederivation():
    old, new = chain_sample(), chain_sample()
    new["chain_json"]["lifecycle"]["runner"] = "b"
    new["chain_json"]["sha256"]["runner"] = "b"
    assert not cmp_mod.compare(old, new, cmp_mod.TABLE).ok
    assert cmp_mod.compare(old, new, cmp_mod.TABLE, rederive=lambda p, o, n: p.startswith(("/chain_json/lifecycle/", "/chain_json/sha256/"))).ok


SHAPES = ["a_pilot", "a_reload", "b", "c", "d_smoke"]


def layout_old(shape):
    """A synthetic OLD-layout chain result for one tg1 phase shape (files only; the shape table is under test)."""
    stem = "m.s1.opencode_python"
    rows = [{"id": f"python/{n}", "passed": True} for n in ("a", "b", "c")]
    man_full, man_pilot = {"run_id": "RF", "model": "m", "kind": "full"}, {"run_id": "RP", "model": "m", "kind": "pilot"}
    f = {}
    if shape in ("a_pilot", "a_reload"):
        f["s1/%s.jsonl" % stem] = {"kind": "rows", "rows": rows[:2]}
        f["s1/%s.manifest.json" % stem] = {"kind": "manifest", "doc": man_pilot}
        f["s1/%s.attempt1.json" % stem] = {"kind": "attempt_json", "doc": {"attempt": 1, "step": "pilot", "rc": 0}}
        f["s1/%s.attempt1.log" % stem] = {"kind": "attempt_log", "sha": "L1"}
        steps = ["pilot"]
    elif shape == "c":
        f["s1/%s.jsonl" % stem] = {"kind": "rows", "rows": rows}
        f["s1/%s.manifest.json" % stem] = {"kind": "manifest", "doc": man_full}
        f["s1/%s.attempt1.json" % stem] = {"kind": "attempt_json", "doc": {"attempt": 1, "step": "full", "rc": 0}}
        f["s1/%s.attempt1.log" % stem] = {"kind": "attempt_log", "sha": "L1"}
        steps = ["full"]
    else:                                                       # b and d: pilot then full, same rows file
        f["s1/%s.jsonl" % stem] = {"kind": "rows", "rows": rows}
        f["s1/%s.manifest.json" % stem] = {"kind": "manifest", "doc": man_full}     # last writer = the full step
        f["s1/%s.attempt1.json" % stem] = {"kind": "attempt_json", "doc": {"attempt": 1, "step": "pilot", "rc": 0}}
        f["s1/%s.attempt2.json" % stem] = {"kind": "attempt_json", "doc": {"attempt": 2, "step": "full", "rc": 0}}
        f["s1/%s.attempt1.log" % stem] = {"kind": "attempt_log", "sha": "L1"}
        f["s1/%s.attempt2.log" % stem] = {"kind": "attempt_log", "sha": "L2"}
        steps = ["pilot", "full"]
    result = {"scenario": "c", "kind": "chain", "rc": 0, "shapes": [shape],
              "chain_json": {"status": "finished", "rc": 0, "attempts": [], "restarts": []},
              "files": f, "invocations": [], "ops_calls": [], "step_manifests": {},
              "pilot_rows": 2 if len(steps) == 2 else None}
    if len(steps) == 2:
        result["step_manifests"]["s1/" + stem] = {"1": man_pilot, "2": man_full}
    if shape == "a_pilot" or shape == "a_reload":
        result["step_manifests"]["s1/" + stem] = {"1": man_pilot}
    if shape == "c":
        result["step_manifests"]["s1/" + stem] = {"1": man_full}
    return result


@pytest.mark.parametrize("shape", SHAPES)
def test_the_four_shape_file_layout_mapping_is_exact_and_bijective(shape):
    old = layout_old(shape)
    new = cmp_mod.to_new_layout(old)
    names = set(new["files"])
    assert not any(re.search(r"\.attempt\d+\.", n) for n in names)
    assert any(re.search(r"\.L1\.(pilot|full)\.a\d+\.jsonl$", n) for n in names)
    res = cmp_mod.compare(old, new, cmp_mod.TABLE)
    assert res.ok, res.failures
    a, b = cmp_mod.canonical(old, "old"), cmp_mod.canonical(new, "new")
    assert a == b and a["legs"]


def test_shape_b_splits_rows_pilot_then_full_and_maps_manifests_per_step():
    old = layout_old("b")
    new = cmp_mod.to_new_layout(old)
    pilot = [n for n in new["files"] if re.search(r"\.L1\.pilot\.a1\.jsonl$", n)]
    full = [n for n in new["files"] if re.search(r"\.L1\.full\.a2\.jsonl$", n)]
    assert len(pilot) == len(full) == 1
    assert [r["id"] for r in new["files"][pilot[0]]["rows"]] + [r["id"] for r in new["files"][full[0]]["rows"]] == [
        "python/a", "python/b", "python/c"]
    mp = [n for n in new["files"] if n.endswith(".L1.pilot.a1.manifest.json")]
    mf = [n for n in new["files"] if n.endswith(".L1.full.a2.manifest.json")]
    assert new["files"][mp[0]]["doc"]["kind"] == "pilot" and new["files"][mf[0]]["doc"]["kind"] == "full"


@pytest.mark.parametrize("shape", SHAPES)
def test_a_planted_layout_difference_fails(shape):
    old = layout_old(shape)
    new = cmp_mod.to_new_layout(old)
    rows_file = next(n for n in new["files"] if n.endswith(".jsonl"))
    new["files"][rows_file]["rows"][0]["passed"] = False
    assert not cmp_mod.compare(old, new, cmp_mod.TABLE).ok
    new2 = cmp_mod.to_new_layout(old)
    name = next(n for n in new2["files"] if n.endswith(".manifest.json"))
    new2["files"][name]["doc"] = {"run_id": "other"}
    assert not cmp_mod.compare(old, new2, cmp_mod.TABLE).ok
    new3 = cmp_mod.to_new_layout(old)
    new3["files"].pop(next(n for n in new3["files"] if n.endswith(".log")))
    assert not cmp_mod.compare(old, new3, cmp_mod.TABLE).ok


def test_normalizer_removes_clocks_uuids_run_ids_and_temp_paths():
    n = norm_mod.Normalizer(tmp_roots=["/tmp/abc/x", "/private/tmp/abc/x"])
    doc = {"started": "2026-10-17T10:11:12Z", "wall_s": 3.2, "pid": 1234, "probe_pid": 9,
           "p": "/tmp/abc/x/sub/file.jsonl", "q": "/private/tmp/abc/x/y", "run_id": "20261017T101112-0123456789ab",
           "again": "evidence/20261017T101112-0123456789ab/g", "other": "20261017T101113-ffffffffffff",
           "u": "7f0c1f9e-3c2b-4a7e-9f10-0123456789ab", "keep": "python/one", "n": 5}
    out = n.apply(doc)
    assert out["started"] == out["wall_s"] == out["probe_pid"] == norm_mod.VOLATILE
    assert out["p"] == "$TMP/sub/file.jsonl" and out["q"] == "$TMP/y"
    assert out["run_id"] == "<run-1>" and out["again"] == "evidence/<run-1>/g" and out["other"] == "<run-2>"
    assert out["u"] == "<uuid-1>" and out["keep"] == "python/one" and out["n"] == 5
    assert n.apply(doc) == out                                              # stable on the same normalizer


# ------------------------------------------------------------------------------------------------ (e) differential
@pytest.mark.xfail(strict=True, reason="P371 phase 2/3: new core not built")
@pytest.mark.parametrize("name", ITEM)
def test_item_differential(name):
    scenario = run_mod.load_scenario(name)
    new = run_mod.run_new_side(scenario)                 # phase 2: runs the same scenario on the new core
    old = run_mod.load_golden(name)
    res = cmp_mod.compare(old, new, cmp_mod.TABLE)
    assert res.ok, res.failures


@pytest.mark.xfail(strict=True, reason="P371 phase 2/3: new core not built")
@pytest.mark.parametrize("name", CHAIN)
def test_chain_differential(name):
    scenario = run_mod.load_scenario(name)
    new = run_mod.run_new_side(scenario)                 # phase 3: runs the same scenario on the new chain core
    old = run_mod.load_golden(name)
    res = cmp_mod.compare(old, new, cmp_mod.TABLE)
    assert res.ok, res.failures


def test_run_new_side_is_not_implemented_yet():
    with pytest.raises(NotImplementedError):
        run_mod.run_new_side(run_mod.load_scenario("item_normal_pass"))
