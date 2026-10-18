"""P371 phase 1: `bench.run_config` (plan 3.2): GenerationPolicy / EvidencePolicy / ChainConfig as pure frozen data."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import run_config as rc
from bench import identity_closure, tg1_runner
from bench import toolchain as toolchain_mod

REPO = Path(__file__).resolve().parents[3]
TOOLCHAIN = dict(lock_sha256="1" * 64, interpreter="3.12.1", grader_image_id="sha256:" + "2" * 64)
CORPUS_ID = dict(corpus_id="tg1", universe_sha256="u" * 8, grader_version="g1", grader_timeout_s={"python": 300, "go": 180})


def host():
    return SimpleNamespace(
        _sha_of=lambda path: "sha-" + Path(path).name,
        NORETRY_PLUGIN=REPO / "benchmark/opencode_plugins/noretry.js",
        SCAFFOLD_ENV_POLICY_V2={"PATH": "/usr/bin", "TERM": "dumb"},
        __file__=str(REPO / "benchmark/run_tg1_probe.py"))


def old_identity(monkeypatch, inject=None, toolchain=None):
    monkeypatch.setattr(identity_closure, "closure_sha256", lambda *a, **k: "c" * 64)
    monkeypatch.setattr(toolchain_mod, "current", lambda: dict(toolchain or TOOLCHAIN))
    p = host()
    selection = {"fields": {"opencode_bench_config_sha256": "b" * 64}}
    return tg1_runner.identity(p, selection, "u" * 64, "2.0.20", Path("/nonexistent/opencode"), inject=inject)


def new_policy(inject=None, toolchain=None, **over):
    p = host()
    kw = dict(config_id="tg1", scaffold=tg1_runner.inject_label(inject) if inject else tg1_runner.SCAFFOLD,
              corpus_id="tg1", corpus_identity=CORPUS_ID, langs=("python", "go"),
              toolbounds_sha256=p._sha_of(tg1_runner.PLUGIN), noretry_sha256=p._sha_of(p.NORETRY_PLUGIN),
              datefreeze_sha256=p._sha_of(tg1_runner.DATEFREEZE_PLUGIN), carrier_sha256="b" * 64,
              universe_sha256="u" * 64, env=p.SCAFFOLD_ENV_POLICY_V2, toolchain=dict(toolchain or TOOLCHAIN),
              inject=inject, inject_addendum_sha256=(tg1_runner.inject_addendum_sha256(inject)
                                      if inject in tg1_runner.INJECT_ADDENDA else "x" if inject else None))
    kw.update(over)
    return rc.tg1_generation_policy(**kw)


# ---------------------------------------------------------------- superset of today's policy recipe
@pytest.mark.parametrize("inject", [None, "stall", "loop", "alloc"])
def test_every_key_of_the_pre_p371_recipe_is_present_with_its_pre_p371_derivation(monkeypatch, inject):
    old = old_identity(monkeypatch, inject=inject)["policy"]
    new = new_policy(inject=inject).as_dict()
    for key, value in old.items():
        assert key in new, key
        assert new[key] == json.loads(json.dumps(value)), key
    assert set(new) > set(old)


def test_the_new_keys_are_present_and_the_inject_key_only_in_inject_mode():
    plain = new_policy().as_dict()
    for key in ("config_id", "corpus_id", "corpus_identity", "langs", "inject_allowed", "budgets", "watchdog",
                "compaction"):
        assert key in plain, key
    assert "inject" not in plain
    assert new_policy(inject="loop").as_dict()["inject"] == dict(
        kind="loop", prompt_addendum_sha256=hashlib.sha256(tg1_runner.INJECT_ADDENDA["loop"].encode()).hexdigest())


def test_tg1_has_watchdog_off_compaction_off_and_budgets_from_the_plan():
    d = new_policy().as_dict()
    assert d["watchdog"] == {"mode": "off"} and d["compaction"] == "off"
    assert d["budgets"]["thinking_budget"] == 81920 and d["budgets"]["max_tokens"] == 102400
    assert d["langs"] == ["python", "go"]
    assert d["config_id"] == "tg1" and d["corpus_id"] == "tg1"


def test_m64_oc_tg1_has_watchdog_on_and_compaction_accounted():
    d = new_policy(config_id="m64-oc-tg1", scaffold="opencode-v2-web-tg1c",
                   watchdog=rc.watchdog_on(limit_s=3600, grace_s=60, toolwindows_sha256="w" * 64),
                   compaction="on_accounted", arm=dict(arm_id="oc")).as_dict()
    assert d["watchdog"] == dict(mode="on", limit_s=3600, grace_s=60, toolwindows_sha256="w" * 64)
    assert d["compaction"] == "on_accounted" and d["arm"] == {"arm_id": "oc"}


def test_inject_policy_table_equals_tg1_runners():
    assert rc.INJECT_POLICY == tg1_runner.INJECT_POLICY
    assert rc.effective_policy_overrides("stall") == tg1_runner.INJECT_POLICY["stall"]


def test_gate_and_hygiene_are_derived_like_effective_policy():
    for kind in (None, "stall", "loop", "alloc"):
        gate, hygiene = tg1_runner.effective_policy(kind)
        d = new_policy(inject=kind).as_dict()
        assert d["gate"] == gate and d["hygiene"] == hygiene


def test_a_drift_of_each_input_changes_the_sha(monkeypatch):
    base = new_policy().sha256()
    assert new_policy().sha256() == base                          # deterministic
    drifts = [dict(toolbounds_sha256="x"), dict(noretry_sha256="x"), dict(datefreeze_sha256="x"),
              dict(carrier_sha256="x"), dict(universe_sha256="x"), dict(env={"PATH": "/x"}),
              dict(toolchain=dict(TOOLCHAIN, lock_sha256="9" * 64)),
              dict(toolchain=dict(TOOLCHAIN, interpreter="3.13.0")),
              dict(toolchain=dict(TOOLCHAIN, grader_image_id="sha256:" + "9" * 64)),
              dict(config_id="other"), dict(langs=("python",)), dict(compaction="on_accounted"),
              dict(corpus_identity=dict(CORPUS_ID, grader_version="g2")),
              dict(watchdog=rc.watchdog_on(limit_s=1, grace_s=1, toolwindows_sha256="w")),
              dict(grader_version="other"), dict(grader_timeout_s={"python": 1}), dict(grade_join_timeout_s=1),
              dict(plugin_proof="x"), dict(budgets=dict(thinking_budget=1, max_tokens=102400, context="carrier"))]
    seen = {base}
    for over in drifts:
        sha = new_policy(**over).sha256()
        assert sha not in seen, over
        seen.add(sha)
    for kind in ("stall", "loop", "alloc"):
        assert new_policy(inject=kind).sha256() not in seen


def test_the_policy_is_frozen_and_isolated_from_the_callers_dicts():
    env = {"PATH": "/usr/bin"}
    policy = new_policy(env=env)
    env["PATH"] = "/evil"
    assert policy.as_dict()["env"] == {"PATH": "/usr/bin"}
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.config_id = "x"
    out = policy.as_dict()
    out["env"]["PATH"] = "/mutated"
    assert policy.as_dict()["env"] == {"PATH": "/usr/bin"}


def test_as_dict_is_canonical_json():
    d = new_policy().as_dict()
    assert json.loads(json.dumps(d)) == d                           # only JSON-native values (tuples became lists)
    assert new_policy().canonical_json() == json.dumps(d, sort_keys=True, separators=(",", ":"))


def test_invalid_policy_values_refuse():
    with pytest.raises(ValueError):
        new_policy(compaction="maybe")
    with pytest.raises(ValueError):
        new_policy(watchdog={"mode": "on"})                          # an on-watchdog needs its limits and plugin sha
    with pytest.raises(ValueError):
        new_policy(langs=())
    with pytest.raises(ValueError):
        new_policy(config_id="")
    with pytest.raises(ValueError):
        new_policy(inject="bogus")


def test_the_module_is_pure_no_corpus_adapter_or_client_imports():
    code = ("import sys; import bench.run_config; bad = [m for m in sys.modules if m.startswith('bench.') and "
            "m.split('.')[1] in ('corpus_tg1','arm_opencode','arm_runner','tg1_runner','structured_grade',"
            "'proc_guard','opencode_v2_core','arm_adapter')]; print(bad)")
    import subprocess
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO / "benchmark", capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]", out.stdout


# ---------------------------------------------------------------- EvidencePolicy
def test_evidence_policy_values_and_canonical_dict():
    tg1 = rc.EvidencePolicy(namespace="opencode_transcripts", web_evidence=True, final_tree=True,
                            worker_receipts="absent", item_barrier="off")
    m64 = rc.EvidencePolicy(namespace="transcripts/oc", web_evidence=True, final_tree=True,
                            worker_receipts="required", item_barrier="on")
    assert tg1.as_dict() == dict(namespace="opencode_transcripts", web_evidence=True, final_tree=True,
                                 worker_receipts="absent", item_barrier="off")
    assert m64.as_dict()["worker_receipts"] == "required" and m64.as_dict()["item_barrier"] == "on"
    assert tg1.sha256() != m64.sha256()


@pytest.mark.parametrize("bad", [dict(namespace="/abs"), dict(namespace="../up"), dict(namespace=""),
                                 dict(worker_receipts="maybe"), dict(item_barrier="sometimes"),
                                 dict(web_evidence=False)])
def test_evidence_policy_refuses_bad_values(bad):
    kw = dict(namespace="opencode_transcripts", web_evidence=True, final_tree=True, worker_receipts="absent",
              item_barrier="off")
    kw.update(bad)
    with pytest.raises(ValueError):
        rc.EvidencePolicy(**kw)


def test_the_evidence_policy_is_not_part_of_the_generation_policy():
    assert "evidence_policy" not in new_policy().as_dict()


# ---------------------------------------------------------------- ChainConfig
def chain_config(**over):
    kw = dict(
        config_id="tg1",
        arms=(rc.ArmBinding(arm="oc", probe="benchmark/run_tg1_probe.py", label="opencode-v2-web-tg1",
                            arm_spec="oc"),),
        schedule=dict(builder="tg1", params=dict(mode="chain", sessions=["s1", "s2", "reload"], smoke=False)),
        out_root_family="c147", predictor="off", arm_switch_ops=(), transport_policy="abort_restart",
        resume_policy="restart_load", snapshot_complete_required=False, contract_artifacts=())
    kw.update(over)
    return rc.ChainConfig(**kw)


def test_chain_config_canonical_serialization_and_sha():
    a, b = chain_config(), chain_config()
    assert a.canonical_json() == b.canonical_json() and a.sha256() == b.sha256()
    assert a.sha256() == hashlib.sha256(a.canonical_json().encode()).hexdigest()
    d = a.as_dict()
    assert json.loads(json.dumps(d)) == d
    assert d["arms"][0] == dict(arm="oc", probe="benchmark/run_tg1_probe.py", label="opencode-v2-web-tg1",
                                arm_spec="oc", probe_data=[])
    assert d["transport_policy"] == "abort_restart" and d["resume_policy"] == "restart_load"


def test_chain_config_drift_changes_the_sha_and_key_order_does_not():
    base = chain_config().sha256()
    for over in (dict(predictor="mtp"), dict(transport_policy="incident_retry"), dict(resume_policy="new_segment"),
                 dict(snapshot_complete_required=True), dict(arm_switch_ops=("search_restart",)),
                 dict(out_root_family="m63"), dict(config_id="x"),
                 dict(schedule=dict(builder="tg1", params=dict(mode="pilot")))):
        assert chain_config(**over).sha256() != base, over
    reordered = dict(builder="tg1", params=dict(smoke=False, sessions=["s1", "s2", "reload"], mode="chain"))
    assert chain_config(schedule=reordered).sha256() == base


def test_chain_config_m64_shape_with_draw_artifact_and_contract_artifacts():
    cfg = chain_config(
        config_id="m64-oc-tg2",
        schedule=dict(builder="blocks", params=dict(picks=["a", "b"]), draw_sha256="d" * 64, tier="screen"),
        arm_switch_ops=("search_restart", "cache_reset", "warmup"), transport_policy="incident_retry",
        resume_policy="new_segment", snapshot_complete_required=True,
        contract_artifacts=(rc.ContractArtifact(arm="oc", path="m64/contract_oc.json", sha256="e" * 64),))
    d = cfg.as_dict()
    assert d["schedule"]["draw_sha256"] == "d" * 64 and d["schedule"]["tier"] == "screen"
    assert d["contract_artifacts"] == [dict(arm="oc", path="m64/contract_oc.json", sha256="e" * 64)]


@pytest.mark.parametrize("bad", [dict(transport_policy="shrug"), dict(resume_policy="never"), dict(arms=()),
                                 dict(config_id=""), dict(arm_switch_ops=("explode",)),
                                 dict(contract_artifacts=(rc.ContractArtifact(arm="zz", path="p", sha256="x" * 64),)),
                                 dict(schedule={"params": {}})])
def test_chain_config_refuses_bad_values(bad):
    with pytest.raises(ValueError):
        chain_config(**bad)


def test_chain_config_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        chain_config().predictor = "mtp"


# ---------------------------------------------------------------- P371 phase 2a: the policy template the entries bind
def test_policy_template_is_frozen_data_with_the_static_part_of_the_policy():
    t = rc.PolicyTemplate(config_id="tg1", langs=["python", "go"])
    assert t.langs == ("python", "go") and t.inject_allowed == rc.INJECT_KINDS and t.compaction == "off"
    assert t.watchdog == {"mode": "off"} and t.budgets == rc.DEFAULT_BUDGETS
    with pytest.raises(dataclasses.FrozenInstanceError):
        t.config_id = "x"
    for bad in (dict(config_id=""), dict(langs=()), dict(compaction="bogus"),
                dict(watchdog=dict(mode="on")), dict(inject_allowed=("nope",))):
        with pytest.raises(ValueError):
            rc.PolicyTemplate(**{**dict(config_id="tg1", langs=("python",)), **bad})


def test_policy_template_build_equals_the_direct_constructor():
    t = rc.PolicyTemplate(config_id="tg1", langs=("python", "go"))
    p = host()
    kw = dict(scaffold=tg1_runner.SCAFFOLD, corpus_id="tg1", corpus_identity=CORPUS_ID,
              toolbounds_sha256=p._sha_of(tg1_runner.PLUGIN), noretry_sha256=p._sha_of(p.NORETRY_PLUGIN),
              datefreeze_sha256=p._sha_of(tg1_runner.DATEFREEZE_PLUGIN), carrier_sha256="b" * 64,
              universe_sha256="u" * 64, env=p.SCAFFOLD_ENV_POLICY_V2, toolchain=dict(TOOLCHAIN))
    assert t.build(**kw).sha256() == new_policy().sha256()
