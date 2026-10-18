"""P311-lite (vi): chain runner on the tg1 entry: composite and per-arm identity pins, lifecycle freeze (P24), the
fake probe contract (spec tests 5, 6, 10)."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from bench import chain_ops as co
from bench import tg1_runner
from bench.tests.test_c147_chain_runner import (    # noqa: F401  (fixtures: env)
    C147, CHAIN, FP, PICK1, PICK2, PILOT, R, REPO, chain_json, env, invocations, log_has, run)


def load_inject():
    spec = importlib.util.spec_from_file_location("run_inject_p311", C147 / "run_inject.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_inject_p311"] = module
    spec.loader.exec_module(module)
    return module


def test_default_probe_is_the_tg1_entry():
    assert Path(R.parse_args(CHAIN).probe) == REPO / "benchmark/run_tg1_probe.py"
    assert (REPO / "benchmark/run_tg1_probe.py").is_file()
    assert Path(R.parse_args(PILOT).probe).name == "run_tg1_probe.py"


def test_inject_driver_default_probe_is_the_tg1_entry():
    import argparse
    src = (C147 / "run_inject.py").read_text()
    assert 'benchmark/run_tg1_probe.py' in src and 'benchmark/run_opencode_probe_v2.py' not in src


def test_the_tg1_probe_process_counts_as_busy_and_as_generation():
    assert "run_tg1_probe" in co.BUSY
    from bench import workqueue
    assert "run_tg1_probe" in workqueue._GENERATIONISH


# ---------------------------------------------------------------- composite and arm identity in the contract
def test_composite_fields_and_recipe_equal_the_probes():
    assert co.GENERATION_FIELDS == tg1_runner.GENERATION_FIELDS
    rt = {k: f"v-{k}" for k in co.GENERATION_FIELDS}
    assert co.composite_sha(rt) == tg1_runner.generation_identity_sha256(rt)
    with pytest.raises(ValueError, match="polyglot_sha"):
        co.composite_sha({k: v for k, v in rt.items() if k != "polyglot_sha"})


WORKER = {"pid": 4242, "create_time": 1700000000.5, "model_path": "caslca/" + PICK1, "registry_sha256": "a" * 64}


@pytest.fixture
def leg_env(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    ids = ["python/alpha", "python/beta"]
    out = tmp_path / "c147/s1" / f"{PICK1}.s1.opencode_python.jsonl"
    FP.write_leg(out, PICK1, "python", 1001, ids, WORKER, tmp_path)
    pinned = {"scaffold_policy_sha256": FP.CAMPAIGN, "probe_code_sha256": "9" * 64,
              "serving_path": FP.SERVING, "registry_sha256": "a" * 64}
    leg = dict(session="s1", model=PICK1, lang="python", seed_base=1001, expected_ids=ids, out=str(out), rc=0)
    return leg, pinned, out, tmp_path


def mutate(out, *, manifest=None, rows=None):
    mp = out.with_suffix(".manifest.json")
    if manifest:
        man = json.loads(mp.read_text())
        manifest(man)
        mp.write_text(json.dumps(man))
    if rows:
        lines = [json.loads(line) for line in out.read_text().splitlines()]
        for row in lines:
            rows(row)
        out.write_text("".join(json.dumps(r) + "\n" for r in lines))


def test_fake_probe_emits_the_composite_the_arm_identity_and_the_spawn_date(leg_env):
    leg, pinned, out, wd = leg_env
    man = json.loads(out.with_suffix(".manifest.json").read_text())
    rt = man["runtime"]
    assert rt["generation_identity_sha256"] == co.composite_sha({**rt, "sampling_profile": "deployed"})
    assert len(rt["arm_identity_sha256"]) == 64 and rt["arm_identity_sha256"] != rt["generation_identity_sha256"]
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert all(r["generation_identity_sha256"] == rt["generation_identity_sha256"]
               and r["arm_identity_sha256"] == rt["arm_identity_sha256"] and r["prompt_date"] for r in rows)
    assert co.validate_leg(leg, pinned, wd) == []


@pytest.mark.parametrize("name,kwargs,code", [
    ("composite not hex", dict(manifest=lambda m: m["runtime"].update(generation_identity_sha256="zz")),
     "runtime_generation_identity_sha256_invalid"),
    ("composite tampered", dict(manifest=lambda m: m["runtime"].update(generation_identity_sha256="b" * 64)),
     "runtime_generation_identity_sha256_inconsistent_invalid"),
    ("field changed under an unchanged composite", dict(manifest=lambda m: m["runtime"].update(polyglot_sha="2" * 40)),
     "runtime_generation_identity_sha256_inconsistent_invalid"),
    ("arm absent", dict(manifest=lambda m: m["runtime"].pop("arm_identity_sha256")), "runtime_arm_identity_sha256_invalid"),
    ("arm malformed", dict(manifest=lambda m: m["runtime"].update(arm_identity_sha256="short")),
     "runtime_arm_identity_sha256_invalid"),
    ("row composite differs", dict(rows=lambda r: r.update(generation_identity_sha256="c" * 64)), "row_generation_identity"),
    ("row arm differs", dict(rows=lambda r: r.update(arm_identity_sha256="d" * 64)), "row_arm_identity"),
    ("row arm absent", dict(rows=lambda r: r.pop("arm_identity_sha256")), "row_arm_identity"),
    ("prompt_date absent", dict(rows=lambda r: r.pop("prompt_date")), "row_prompt_date"),
    ("prompt_date empty", dict(rows=lambda r: r.update(prompt_date="")), "row_prompt_date"),
    ("prompt_date not a string", dict(rows=lambda r: r.update(prompt_date=20261016)), "row_prompt_date"),
])
def test_malformed_identity_values_fail_closed_in_validate_leg(leg_env, name, kwargs, code):
    leg, pinned, out, wd = leg_env
    mutate(out, **kwargs)
    codes = {w.split(":")[0] for w in co.validate_leg(leg, pinned, wd)}
    assert code in codes, (name, codes)


def test_validate_leg_checks_the_frozen_arm_and_pinned_composite(leg_env):
    leg, pinned, out, wd = leg_env
    rt = json.loads(out.with_suffix(".manifest.json").read_text())["runtime"]
    assert co.validate_leg({**leg, "arm_identity_sha256": rt["arm_identity_sha256"]}, pinned, wd) == []
    assert any(w.startswith("runtime_arm_identity_sha256") for w in
               co.validate_leg({**leg, "arm_identity_sha256": "e" * 64}, pinned, wd))
    pinned = {**pinned, "generation_identity_sha256": rt["generation_identity_sha256"]}
    assert co.validate_leg(leg, pinned, wd) == []
    assert any(w.startswith("runtime_generation_identity_sha256") for w in
               co.validate_leg(leg, {**pinned, "generation_identity_sha256": "f" * 64}, wd))


# ---------------------------------------------------------------- the chain
def manifest_runtime(env, model, session="s1", lang="python"):
    """The runtime block of the leg's LAST invocation manifest (P371 A8: one manifest per leg attempt)."""
    paths = sorted((env["out"] / session).glob(f"{model}.{session}.opencode_{lang}.L*.manifest.json"),
                   key=lambda p: int(p.name.split(".a")[-1].split(".")[0]))
    return json.loads(paths[-1].read_text())["runtime"]


def test_chain_pins_the_composite_and_freezes_one_arm_identity_per_pick(env):
    assert run(env, CHAIN) == 0
    cj = chain_json(env)
    rt1, rt2 = manifest_runtime(env, PICK1), manifest_runtime(env, PICK2)
    assert cj["pinned"]["generation_identity_sha256"] == rt1["generation_identity_sha256"] == rt2["generation_identity_sha256"]
    assert cj["arms"] == {f"{PICK1}|off": rt1["arm_identity_sha256"], f"{PICK2}|off": rt2["arm_identity_sha256"]}
    assert rt1["arm_identity_sha256"] != rt2["arm_identity_sha256"]


def test_a_changed_arm_identity_on_the_second_pick_aborts(env):
    plan = [{}, {}, {}, {}, {}, {"runtime.arm_identity_sha256": "d" * 64}]     # the 2nd pick's go leg (6th launch)
    assert run(env, CHAIN, extra_env={"FAKE_MANIFEST_PLAN": json.dumps(plan)}) == 2
    assert log_has(env, "BARRIER MISMATCH") and log_has(env, "arm_identity_sha256")
    assert len(chain_json(env)["arms"]) == 2


def test_generation_drift_between_legs_aborts(env):
    plan = [{}, {}, {"runtime.carrier_source_sha256": "7" * 64}]                # recomputed composite follows the field
    assert run(env, CHAIN, extra_env={"FAKE_MANIFEST_PLAN": json.dumps(plan)}) == 2
    assert log_has(env, "BARRIER MISMATCH") and log_has(env, "generation_identity_sha256")


def test_scoring_drift_between_pilot_full_and_legs_is_accepted(env):
    plan = [{"runtime.scoring_code_sha256": f"{i:064x}"} for i in range(6)]
    assert run(env, CHAIN, extra_env={"FAKE_MANIFEST_PLAN": json.dumps(plan)}) == 0
    seen = {manifest_runtime(env, m, lang=lang).get("scoring_code_sha256")
            for m in (PICK1, PICK2) for lang in ("python", "go")}
    assert len(seen) == 4


def test_generation_sha_flag_pins_the_composite_upfront(env):
    assert run(env, CHAIN + ["--generation-sha", "0" * 64]) == 2
    assert log_has(env, "generation_identity_sha256")


def test_bad_generation_sha_flag_is_refused():
    with pytest.raises(SystemExit) as exc:
        R.parse_args(CHAIN + ["--generation-sha", "nothex"])
    assert exc.value.code == 2


# ---------------------------------------------------------------- lifecycle freeze (P24)
def lifecycle_copy(tmp_path):
    """Temp copies of every lifecycle member (P371 R15: the entry's import closure, gate, launchers), same relative paths."""
    directory = tmp_path / "lifecycle"
    files = {}
    for name, source in R.lifecycle_files(REPO).items():
        files[name] = directory / Path(source).relative_to(REPO)
        files[name].parent.mkdir(parents=True, exist_ok=True)
        files[name].write_bytes(Path(source).read_bytes())
    return files


def touch(path):
    path.write_bytes(path.read_bytes() + b"\n# drift\n")


def test_lifecycle_is_frozen_in_chain_json_and_an_unchanged_chain_completes(env):
    files = lifecycle_copy(env["wd"])
    assert run(env, CHAIN, lifecycle=files) == 0
    cj = chain_json(env)
    assert {"runner", "chain_ops", "gate", "launcher", "launch_tg1", "chain_config"} <= set(cj["lifecycle"])
    assert set(cj["lifecycle"]) == set(files) | {"chain_config"}         # P371 R15: + the entry's import closure members
    assert {k: v for k, v in cj["lifecycle"].items() if k != "chain_config"} == co.lifecycle_shas(files)
    assert all(len(cj["sha256"][k]) == 64 for k in ("runner", "chain_ops", "gate", "overlay", "launcher", "launch_tg1"))


@pytest.mark.parametrize("name", ["runner", "chain_ops", "gate", "launcher", "launch_tg1"])
def test_lifecycle_drift_between_legs_aborts_before_the_next_launch(env, name):
    files = lifecycle_copy(env["wd"])
    ops = env["ops"]
    original = ops.a4_gate

    def gate(model, tag):
        if model == PICK2:
            touch(files[name])
        return original(model, tag)
    ops.a4_gate = gate
    assert run(env, CHAIN, lifecycle=files) == 2
    assert log_has(env, "lifecycle drift") and log_has(env, name)
    assert len(invocations(env)) == 3                     # the first pick's three launches only


def test_lifecycle_drift_between_pilot_and_full_aborts_on_resume(env):
    files = lifecycle_copy(env["wd"])
    assert run(env, PILOT, lifecycle=files) == 0
    launched = len(invocations(env))
    touch(files["chain_ops"])
    assert run(env, CHAIN, lifecycle=files) == 2
    assert log_has(env, "lifecycle drift") and len(invocations(env)) == launched
    frozen = {k: v for k, v in chain_json(env)["lifecycle"].items() if k != "chain_config"}
    assert frozen != co.lifecycle_shas(files)                                           # never silently rewritten


def test_lifecycle_drift_at_exit_is_an_abort(env):
    files = lifecycle_copy(env["wd"])
    ops = env["ops"]
    ops.on_unload = lambda: touch(files["runner"]) if len(ops.names("unload")) >= 2 else None    # the final unload
    assert run(env, CHAIN, lifecycle=files) == 2
    assert log_has(env, "lifecycle drift")


def test_lifecycle_drift_names_exactly_the_changed_files(tmp_path):
    files = lifecycle_copy(tmp_path)
    frozen = co.lifecycle_shas(files)
    assert co.lifecycle_drift(frozen, files) == []
    touch(files["gate"])
    files["launcher"].unlink()                                    # a vanished file is drift too
    assert co.lifecycle_drift(frozen, files) == ["gate", "launcher"]


# ---------------------------------------------------------------- review L3: the active launcher is frozen
def test_the_launcher_the_operator_actually_uses_is_in_the_lifecycle():
    named = R.NAMED_LIFECYCLE
    assert named["launch_tg1"] == "benchmark/chains/c147/launchers/launch_tg1.sh"
    assert (REPO / named["launch_tg1"]).is_file() and (REPO / named["launcher"]).is_file()
    assert set(R.lifecycle_files(REPO)) >= {"launcher", "launch_tg1", "gate", "runner", "chain_ops"}


# ---------------------------------------------------------------- review L4: an existing chain.json must be complete
def valid_chain_json(env):
    files = lifecycle_copy(env["wd"])
    assert run(env, PILOT, lifecycle=files) == 0
    return files, env["out"] / "chain.json"


def _rewrite(path, fn):
    doc = json.loads(path.read_text())
    fn(doc)
    path.write_text(json.dumps(doc))


@pytest.mark.parametrize("name,damage", [
    ("not json", lambda path: path.write_text("{ torn")),
    ("binary", lambda path: path.write_bytes(b"\xff\xfe\x00")),
    ("empty object", lambda path: path.write_text("{}")),
    ("no lifecycle", lambda path: _rewrite(path, lambda d: d.pop("lifecycle"))),
    ("lifecycle null", lambda path: _rewrite(path, lambda d: d.update(lifecycle=None))),
    ("lifecycle missing a file", lambda path: _rewrite(path, lambda d: d["lifecycle"].pop("gate"))),
    ("lifecycle missing the chain_config sha", lambda path: _rewrite(path, lambda d: d["lifecycle"].pop("chain_config"))),
    ("lifecycle extra file", lambda path: _rewrite(path, lambda d: d["lifecycle"].update(other="a" * 64))),
    ("lifecycle not hex", lambda path: _rewrite(path, lambda d: d["lifecycle"].update(gate="nothex"))),
    ("arms absent", lambda path: _rewrite(path, lambda d: d.pop("arms"))),
    ("arm value not hex", lambda path: _rewrite(path, lambda d: d.update(arms={"m|off": "short"}))),
    ("pinned not a dict", lambda path: _rewrite(path, lambda d: d.update(pinned=[]))),
    ("pinned composite malformed", lambda path: _rewrite(path, lambda d: d["pinned"].update(generation_identity_sha256="x"))),
    ("policy absent", lambda path: _rewrite(path, lambda d: d.pop("policy_sha256"))),
    ("policy null", lambda path: _rewrite(path, lambda d: d.update(policy_sha256=None))),
    ("pinned policy missing", lambda path: _rewrite(path, lambda d: d["pinned"].pop("scaffold_policy_sha256"))),
    ("pinned policy differs", lambda path: _rewrite(path, lambda d: d["pinned"].update(scaffold_policy_sha256="9" * 64))),
    ("policy malformed", lambda path: _rewrite(path, lambda d: d.update(policy_sha256="x"))),
])
def test_an_existing_malformed_chain_json_refuses_and_is_never_overwritten(env, name, damage):
    files, path = valid_chain_json(env)
    damage(path)
    before, launched = path.read_bytes(), len(invocations(env))
    assert run(env, CHAIN, lifecycle=files) == 2
    assert log_has(env, "chain.json") and path.read_bytes() == before and len(invocations(env)) == launched


def test_a_valid_existing_chain_json_resumes(env):
    files, path = valid_chain_json(env)
    assert run(env, CHAIN, lifecycle=files) == 0


# ---------------------------------------------------------------- review L9 (P362): the expected policy comes from the probe
def identity_calls(env):
    path = env["ops"].state / "identity_calls.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_the_expected_policy_sha_is_derived_from_the_probes_print_identity_and_frozen(env):
    assert run(env, CHAIN) == 0
    cj = chain_json(env)
    assert cj["policy_sha256"] == FP.CAMPAIGN == cj["pinned"]["scaffold_policy_sha256"]
    calls = identity_calls(env)
    assert len(calls) == 2 and all("--universe" in c["argv"] for c in calls)        # entry + the A5 exit re-run (snapshot)
    assert calls[0]["argv"][calls[0]["argv"].index("--universe") + 1] == str(env["uni"].resolve())
    assert len(invocations(env)) == 6                               # print-identity is not a generation attempt


def test_a_supplied_policy_sha_is_only_an_assertion(env):
    assert run(env, CHAIN + ["--policy-sha", "5" * 64]) == 2
    assert log_has(env, "policy") and invocations(env) == []
    assert run(env, CHAIN + ["--policy-sha", FP.CAMPAIGN]) == 0


def test_resume_reverifies_the_frozen_policy_against_the_probe(env):
    files = lifecycle_copy(env["wd"])
    assert run(env, PILOT, lifecycle=files) == 0
    launched = len(invocations(env))
    assert run(env, CHAIN, lifecycle=files, extra_env={"FAKE_PRINT_POLICY_SHA": "4" * 64,
                                                       "FAKE_POLICY_SHA": "4" * 64}) == 2
    assert log_has(env, "policy") and len(invocations(env)) == launched
    assert chain_json(env)["policy_sha256"] == FP.CAMPAIGN


@pytest.mark.parametrize("mode", ["fail", "garbage", "malformed"])
def test_a_probe_that_cannot_print_its_identity_refuses(env, mode):
    assert run(env, CHAIN, extra_env={"FAKE_PRINT_MODE": mode}) == 2
    assert log_has(env, "print-identity") and invocations(env) == []


def test_no_policy_constant_survives():
    from bench import tg1_runner
    assert not hasattr(co, "CAMPAIGN_POLICY_SHA") and not hasattr(tg1_runner, "CAMPAIGN_POLICY_SHA256")


# ---------------------------------------------------------------- confirmation L4: no half-written record
def test_a_failed_policy_derivation_writes_no_chain_json(env):
    assert run(env, CHAIN, extra_env={"FAKE_PRINT_MODE": "fail"}) == 2
    assert not (env["out"] / "chain.json").exists()


def test_a_supplied_policy_mismatch_writes_no_chain_json(env):
    assert run(env, CHAIN + ["--policy-sha", "5" * 64]) == 2
    assert not (env["out"] / "chain.json").exists()


def test_resume_never_overwrites_a_frozen_policy(env):
    files = lifecycle_copy(env["wd"])
    assert run(env, PILOT, lifecycle=files) == 0
    path = env["out"] / "chain.json"
    before = path.read_bytes()
    assert run(env, CHAIN, lifecycle=files, extra_env={"FAKE_PRINT_POLICY_SHA": "4" * 64,
                                                       "FAKE_POLICY_SHA": "4" * 64}) == 2
    assert path.read_bytes() == before
