"""M64 step 4a -> P371 phase 3b: the M64 chain is a THIN ENTRY of the shared chain core (`bench.chain_core`): arguments, the
ChainConfig (`blocks` schedule, `incident_retry` / `new_segment`, arm switches, per-arm specs), out-root rules. Everything
here runs the entry end to end against the fake arm probe and a fake ChainOps (`m64_support`); no router, worker or GPU.
Incidents / resume / hooks / A10 live in `test_p371_m64_*.py`."""
from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path

import pytest

from bench import arm_adapter as aa
from bench import arm_specs
from bench import chain_core as core
from bench import chain_ops as co
from bench import chain_rows as cr
from bench import contract_artifact as ca
from bench import schedules
from bench.tests.m64_support import (  # noqa: F401  (fixture: env)
    FAP, FROZEN, LABELS, M, PICK1, PICK2, REPO, SMOKE, SMOKE3, arg, calls, chain_json, env, invocations, log_has, run,
    schedule)


def epoch(arms):
    return FAP.epoch_for(arms)


# ---------------------------------------------------------------- arguments and the thin entry
def test_arguments_need_arms_probe_code_and_a_valid_epoch_assertion():
    p = M.parse_args(SMOKE + ["--epoch-id", "e" * 64])
    assert p.arms == ["oc"] and p.sessions == ["s1"] and p.smoke is True and p.epoch_id == "e" * 64
    assert p.probe_code_sha == {"oc": "9" * 64}
    assert M.parse_args(SMOKE).epoch_id is None                                  # A5: --epoch-id is only an assertion
    with pytest.raises(SystemExit):
        M.parse_args(["chain", "--arms", "oc"])                                  # probe code sha required per arm
    with pytest.raises(SystemExit):
        M.parse_args(SMOKE + ["--epoch-id", "short"])
    with pytest.raises(SystemExit):
        M.parse_args(["chain", "--arms", "oc,oc", "--probe-code-sha", "oc=" + "9" * 64])
    with pytest.raises(SystemExit):
        M.parse_args(["chain", "--arms", "oc,pi", "--probe-code-sha", "oc=" + "9" * 64])


def test_the_entry_keeps_every_cli_flag():
    flags = {a.option_strings[0] for a in M.build_parser()._actions if a.option_strings}
    assert {"--arms", "--probe-code-sha", "--probe", "--policy-sha", "--epoch-id", "--pred-s", "--arm-idle-s", "--smoke",
            "--out-root", "--python", "--universe", "--frozen-prompt-date", "--frozen-date-from",
            "--contract-artifact"} <= flags


def test_the_entry_is_thin_no_chain_logic_no_base_inheritance_no_reexports():
    text = (REPO / "benchmark/chains/m64/run_m64_chain.py").read_text()
    assert "base.Chain" not in text and "ArmChain" not in text and "lifecycle_files_" not in text
    assert "run_tg1_chain" not in text and "m64_schedule" not in text
    assert len(text.splitlines()) < 420
    cfg = M.m64_config(M.parse_args(SMOKE))
    assert (cfg.transport_policy, cfg.resume_policy, cfg.predictor) == ("incident_retry", "new_segment", "off")
    assert cfg.arm_switch_ops == ("search_restart", "cache_reset", "warmup") and cfg.schedule["builder"] == "blocks"
    assert cfg.snapshot_complete_required is False                                # --smoke
    assert M.m64_config(M.parse_args(["chain", "--arms", "oc", "--probe-code-sha", "oc=" + "9" * 64])
                        ).snapshot_complete_required is True


def test_the_chain_config_excludes_run_selection_but_not_the_arms(env):
    base = M.m64_config(M.parse_args(SMOKE)).as_dict()
    assert M.m64_config(M.parse_args(["chain", "s1", "s2", "--smoke", "--arms", "oc", "--probe-code-sha",
                                      "oc=" + "9" * 64])).as_dict() == base
    two = M.m64_config(M.parse_args(SMOKE3)).as_dict()
    assert [a["arm"] for a in two["arms"]] == ["oc", "pi", "dsh"] and two != base


def test_an_arm_without_an_adapter_refuses_before_anything_starts(env, monkeypatch):
    monkeypatch.delitem(arm_specs.SPECS, "pi")
    rc = run(env, ["chain", "s1", "--smoke", "--arms", "oc,pi", "--probe-code-sha", "oc=" + "9" * 64,
                   "--probe-code-sha", "pi=" + "9" * 64])
    assert rc == 2 and log_has(env, "no chain spec") and env["ops"].calls == [] and not (env["out"] / "chain.json").exists()


# ---------------------------------------------------------------- end to end, one arm
def test_smoke_chain_with_one_arm_runs_every_leg_and_freezes_the_identities(env):
    assert run(env, SMOKE) == 0
    cj = chain_json(env)
    assert cj["rc"] == 0 and cj["status"] == "finished" and cj["epoch_id"] == epoch(["oc"])
    assert set(cj["arm_generations"]) == {"oc"} and len(cj["arm_generations"]["oc"]) == 64
    assert cj["schedule_sha256"] == schedules.schedule_sha256(schedule(env))
    assert cj["policies"] == {"oc": "d" * 64}
    inv = invocations(env)
    legs = [leg for leg in schedules.legs(schedule(env)) if leg["session"] == "s1"]
    assert len(inv) == len(legs) == 2 * 4                                        # 2 picks x (python, go) x blocks [3, 1]
    for call, leg in zip(inv, legs):
        a = call["argv"]
        assert arg(a, "--items").split(",") == leg["items"] and arg(a, "--lang") == leg["lang"]
        assert arg(a, "--scaffold") == arm_specs.OC.label and arg(a, "--epoch-id") == epoch(["oc"])
        assert arg(a, "--seed-base") == "1001" and arg(a, "--frozen-prompt-date") == FROZEN
        assert arg(a, "--attempt-rerun-index") == "0" and arg(a, "--expect-items") == ",".join(
            f"{leg['lang']}/{x}" for x in leg["items"])
    names = sorted(p.name for p in (env["out"] / "s1").glob("*.jsonl"))
    assert names == sorted(f"{pick}.s1.oc_{lang}.L{b}.block.a{b + 1}.jsonl" for pick in (PICK1, PICK2)
                           for lang in ("python", "go") for b in (0, 1))
    assert "chain_config" in cj and cj["chain_config"] == M.m64_config(M.parse_args(SMOKE)).as_dict()


def test_every_leg_is_one_immutable_invocation_with_its_own_expect_items(env):
    assert run(env, SMOKE) == 0
    prog = chain_json(env)["progress"]
    assert [i["phase"] for i in prog["invocations"]] == ["block"] * 8
    assert all(i["status"] == "validated" and i["accepted_slots"] == i["expected_slots"] for i in prog["invocations"])
    sizes = sorted(len(i["expected_slots"]) for i in prog["invocations"])
    assert sizes == [1, 1, 1, 1, 3, 3, 3, 3]
    table = cr.load_slots(chain_json(env), env["out"])
    assert len(table.scored) == 16 and not table.running
    first = prog["invocations"][0]
    assert first["slot_base"] == f"{epoch(['oc'])}|oc|{PICK1}|s1|python" and first["leg_key"][:3] == [0, "python", 0]
    assert all(s.startswith(first["slot_base"]) for s in first["expected_slots"])


def test_every_leg_restarts_the_search_service_and_each_arm_switch_resets_the_cache_and_warms_up(env):
    assert run(env, SMOKE3) == 0
    names = [c[0] for c in env["ops"].calls if c[0] in ("search_restart", "reset_cache_session", "warmup", "load", "a4_gate")]
    legs = [leg for leg in schedules.legs(schedule(env)) if leg["session"] == "s1"]
    assert names.count("search_restart") == len(legs)
    switches, last = 0, None
    for leg in legs:
        if last is None or leg["load"] != last["load"] or leg["arm"] != last["arm"]:
            switches += 1
        last = leg
    assert names.count("reset_cache_session") == names.count("warmup") == switches
    assert {c[2] for c in calls(env, "a4_gate")} == {LABELS["oc"], LABELS["pi"], LABELS["dsh"]}


def test_a_worker_is_loaded_once_per_pick_and_session_and_shared_by_every_arm(env):
    assert run(env, SMOKE3) == 0
    assert [c[1] for c in calls(env, "load")] == [PICK1, PICK2]
    cj = chain_json(env)
    assert len(cj["block_workers"]) == 2 and {i["arm"] for i in invocations(env)} == {"oc", "pi", "dsh"}
    assert [l["status"] for l in cj["progress"]["loads"]] == ["done", "done"]


def test_permutation_order_of_the_arms_follows_the_frozen_schedule_and_the_realized_order_is_checked(env):
    assert run(env, SMOKE3) == 0
    legs = [leg for leg in schedules.legs(schedule(env)) if leg["session"] == "s1"]
    assert [inv["arm"] for inv in invocations(env)] == [leg["arm"] for leg in legs]
    assert chain_json(env)["realized"] == [schedules.leg_key(leg) for leg in legs]


def test_the_evidence_namespace_and_stems_are_per_arm(env):
    assert run(env, SMOKE3) == 0
    wd = env["wd"]
    for arm in ("oc", "pi", "dsh"):
        assert (wd / "transcripts" / arm / PICK1).is_dir()
    assert not (wd / "opencode_transcripts").exists()
    stems = {p.name.split(".L")[0] for p in (env["out"] / "s1").glob("*.jsonl")}
    assert stems == {f"{pick}.s1.{arm}_{lang}" for pick in (PICK1, PICK2) for arm in ("oc", "pi", "dsh")
                     for lang in ("python", "go")}


def test_the_web_evidence_rules_come_from_each_arms_spec(env, monkeypatch):
    seen = []
    from bench import web_evidence as we
    real = we.extract

    def spy(rules, path, sha, dest):
        seen.append((rules, str(dest)))
        return real(rules, path, sha, dest)
    monkeypatch.setattr(we, "extract", spy)
    assert run(env, SMOKE3) == 0
    assert seen and all(r == arm_specs.OC.web_evidence_rules for r, _ in seen)
    assert {d.split("transcripts/")[1].split("/")[0] for _, d in seen} == {"oc", "pi", "dsh"}


# ---------------------------------------------------------------- identities (spec 4)
def test_the_chain_freezes_one_generation_composite_per_arm_and_one_worker_identity_for_all(env):
    assert run(env, SMOKE3) == 0
    cj = chain_json(env)
    assert set(cj["arm_generations"]) == {"oc", "pi", "dsh"} and len(set(cj["arm_generations"].values())) == 3
    assert set(cj["arms"]) == {f"{PICK1}|off", f"{PICK2}|off"}               # one worker identity per (model, predictor)
    assert set(cj["policies"]) == {"oc", "pi", "dsh"} and set(cj["pinned"]) == {"oc", "pi", "dsh", "shared"}
    assert cj["pinned"]["shared"]["registry_sha256"] == "a" * 64 and "serving_path" in cj["pinned"]["shared"]
    for arm in ("oc", "pi", "dsh"):
        assert cj["pinned"][arm]["probe_code_sha256"] == "9" * 64 and cj["pinned"][arm]["generation_identity_sha256"] == \
            cj["arm_generations"][arm]
    assert set(cj["snapshots"]) == {"oc", "pi", "dsh"} and cj["epoch_id"] == epoch(["oc", "pi", "dsh"])
    assert cj["snapshots"]["oc"] == dict(sha256=FAP.snapshot_for("oc")["sha256"], complete=True)
    assert cj["artifacts"]["campaign_core"] is None and cj["artifacts"]["contract"] == {}


def test_a_manifest_that_disagrees_with_the_frozen_arm_generation_is_a_barrier_mismatch(env):
    plan = [{}, {"runtime.opencode_exe_sha256": "f" * 64}]
    rc = run(env, SMOKE, extra_env={"FAKE_MANIFEST_PLAN": json.dumps(plan)})
    assert rc == 2 and log_has(env, "BARRIER MISMATCH") and log_has(env, "opencode_exe_sha256")
    assert chain_json(env)["arm_generations"]["oc"]


def test_every_manifest_must_name_its_arm_and_the_chains_epoch(env):
    rc = run(env, SMOKE, extra_env={"FAKE_MANIFEST_OVERRIDE": json.dumps({"runtime.arm": "pi"})})
    assert rc == 2 and log_has(env, "arm: 'pi' != 'oc'")


def test_every_manifest_must_carry_the_arms_evidence_policy(env):
    rc = run(env, SMOKE, extra_env={"FAKE_MANIFEST_OVERRIDE": json.dumps({"runtime.evidence_policy.worker_receipts":
                                                                          "required"})})
    assert rc == 2 and log_has(env, "evidence_policy")


# ---------------------------------------------------------------- A5: the epoch, the snapshots
def test_the_chain_computes_the_epoch_from_every_arms_snapshot_and_epoch_id_is_an_assertion(env):
    assert run(env, SMOKE3, epoch=epoch(["oc", "pi", "dsh"])) == 0
    assert chain_json(env)["epoch_id"] == epoch(["oc", "pi", "dsh"]) != epoch(["oc"])
    assert all(arg(c["argv"], "--epoch-id") == epoch(["oc", "pi", "dsh"]) for c in invocations(env))


def test_a_cli_epoch_that_differs_from_the_computed_one_is_refused_before_anything_is_written(env):
    assert run(env, SMOKE, epoch="f" * 64) == 2
    assert log_has(env, "epoch") and invocations(env) == [] and not (env["out"] / "chain.json").exists()


def test_the_probes_print_identity_is_asked_for_every_arm_and_never_for_a_generation(env):
    assert run(env, SMOKE3) == 0
    ident = [json.loads(x) for x in (env["ops"].state / "identity_calls.jsonl").read_text().splitlines()]
    assert {i["arm"] for i in ident} == {"oc", "pi", "dsh"} and len(ident) >= 6      # entry + exit, per arm


def test_an_incomplete_snapshot_is_refused_outside_smoke_at_entry_and_allowed_in_smoke(env, tmp_path):
    assert run(env, SMOKE, extra_env={"FAKE_SNAPSHOT_COMPLETE": "0"}) == 0
    assert chain_json(env)["snapshots"]["oc"]["complete"] is False
    env2 = dict(env, out=tmp_path / "m64", lines=[])
    routers = len(calls(env, "start_router"))
    rc = run(env2, ["chain", "s1", "--arms", "oc", "--probe-code-sha", "oc=" + "9" * 64],
             extra_env={"FAKE_SNAPSHOT_COMPLETE": "0"})
    assert rc == 2 and any("snapshot" in ln and "incomplete" in ln for ln in env2["lines"])
    assert not (tmp_path / "m64" / "chain.json").exists() and len(calls(env, "start_router")) == routers
    assert not list((tmp_path / "m64").glob("s1/*"))


def test_a_snapshot_that_changes_between_legs_is_a_barrier_mismatch(env):
    other = "b" * 64
    plan = [{}, {"runtime.snapshot_sha256": other}]
    rc = run(env, SMOKE, extra_env={"FAKE_MANIFEST_PLAN": json.dumps(plan)})
    assert rc == 2 and log_has(env, "BARRIER MISMATCH") and log_has(env, "snapshot_sha256")


def test_a_snapshot_that_changed_since_the_chain_was_created_refuses_the_resume(env):
    assert run(env, SMOKE) == 0
    before = (env["out"] / "chain.json").read_bytes()
    rc = run(env, SMOKE, extra_env={"FAKE_SNAPSHOT_SALT_OC": "drift"})
    assert rc == 2 and log_has(env, "snapshot") and "changed" in " ".join(env["lines"])
    assert (env["out"] / "chain.json").read_bytes() == before                     # the frozen record is never rewritten


def test_a_snapshot_that_changes_during_the_chain_aborts_at_exit(env):
    ops = env["ops"]
    ops.on_unload = lambda: ops.extra_env.update(FAKE_SNAPSHOT_SALT_OC="late") if len(ops.names("unload")) >= 2 else None
    assert run(env, SMOKE) == 2
    assert log_has(env, "snapshot") and log_has(env, "exit")


def test_the_lifecycle_closure_names_the_core_and_drift_aborts_and_leaves_the_record_frozen(env, tmp_path):
    files = {}
    for name, src in M.lifecycle_files(REPO).items():
        dst = tmp_path / "lifecycle" / Path(src).relative_to(REPO)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(Path(src).read_bytes())
        files[name] = dst
    assert {"runner", "chain_ops", "gate", "benchmark/bench/chain_core.py", "benchmark/bench/schedules.py",
            "benchmark/bench/arm_specs.py", "benchmark/bench/arm_ops.py", "benchmark/bench/chain_rows.py"} <= set(files)
    ops = env["ops"]
    original = ops.a4_gate

    def gate(model, tag, scaffold=None):
        if model == PICK2:
            files["benchmark/bench/schedules.py"].write_bytes(files["benchmark/bench/schedules.py"].read_bytes() + b"\n#")
        return original(model, tag, scaffold)
    ops.a4_gate = gate
    rc = run(env, SMOKE, lifecycle=files)
    assert rc == 2 and log_has(env, "lifecycle drift") and log_has(env, "benchmark/bench/schedules.py")
    lc = chain_json(env)["lifecycle"]
    assert lc["runner"] == hashlib.sha256(files["runner"].read_bytes()).hexdigest()
    assert lc["benchmark/bench/schedules.py"] != hashlib.sha256(files["benchmark/bench/schedules.py"].read_bytes()).hexdigest()


def test_the_contract_artifact_refs_are_frozen_in_the_config_and_in_chain_json(env, tmp_path):
    art = tmp_path / "contract_oc.json"
    # P371 phase 4: the chain verifies the artifact's content, so it must be a real (incomplete: smoke) artifact of the
    # arm's snapshot; this test is about the frozen refs
    ca.write(art, ca.build("oc", FAP.snapshot_for("oc")["sha256"], "2.0.20",
                           {n: (("OWED", "owed") if n in ca.OWED_BY else ("pass", "")) for n in ca.CHECKS}))
    argv = SMOKE + ["--contract-artifact", f"oc={art}"]
    cfg = M.m64_config(M.parse_args(argv))
    assert [a.as_dict() for a in cfg.contract_artifacts] == [dict(arm="oc", path=str(art),
                                                                   sha256=hashlib.sha256(art.read_bytes()).hexdigest())]
    assert run(env, argv) == 0
    cj = chain_json(env)
    assert cj["artifacts"]["contract"] == {"oc": dict(path=str(art), sha256=hashlib.sha256(art.read_bytes()).hexdigest())}
    assert cj["chain_config"]["contract_artifacts"] == [cfg.contract_artifacts[0].as_dict()]
    with pytest.raises(SystemExit):
        M.parse_args(SMOKE + ["--contract-artifact", f"pi={art}"])                # not an arm of this chain


# ---------------------------------------------------------------- out-root, ops
def test_out_roots_default_to_m64_and_m64_smoke_and_refuse_other_chains(tmp_path):
    a = M.parse_args(SMOKE)
    assert M.resolve_out_root(a, tmp_path) == tmp_path / "m64-smoke"
    real = M.parse_args(["chain", "--arms", "oc", "--probe-code-sha", "oc=" + "9" * 64])
    assert M.resolve_out_root(real, tmp_path) == tmp_path / "m64"
    bad = M.parse_args(SMOKE + ["--out-root", str(tmp_path / "m64")])
    with pytest.raises(M.Refused, match="smoke"):
        M.resolve_out_root(bad, tmp_path)
    for d in ("c147", "m63", "c147-smoke"):
        other = M.parse_args(SMOKE + ["--out-root", str(tmp_path / d / "x")])
        with pytest.raises(M.Refused, match="must not write"):
            M.resolve_out_root(other, tmp_path)
    rel = M.parse_args(SMOKE + ["--out-root", "rel/out"])
    assert M.resolve_out_root(rel, tmp_path).is_absolute()                       # P340


def test_the_real_ops_refuse_without_the_search_service_and_the_cache_reset_endpoint(tmp_path):
    from bench import arm_ops
    ops = arm_ops.M64ChainOps(REPO, tmp_path, tmp_path / "o.yaml", lambda m: None, out_root=tmp_path / "m64")
    for call in (ops.require_arm_ops, lambda: ops.search_restart({}), lambda: ops.reset_cache_session("m"),
                 lambda: ops.warmup("m")):
        with pytest.raises(arm_ops.ArmOpsUnavailable, match="search_restart"):
            call()


def test_a_stop_latch_exits_3_and_a_rerun_resumes_at_the_first_load_not_completed(env):
    env["out"].mkdir(parents=True, exist_ok=True)
    stop_after = {"n": 0}
    ops = env["ops"]
    orig = ops.unload

    def unload(model):
        stop_after["n"] += 1
        if stop_after["n"] == 1:                                     # the first load finished: latch STOP at the boundary
            (env["out"] / "STOP").write_text("x")
        return orig(model)

    ops.unload = unload
    assert run(env, SMOKE) == 3
    cj = chain_json(env)
    assert [l["status"] for l in cj["progress"]["loads"]] == ["done", "pending"] and cj["stop"]["where"]    # STOP at the boundary
    (env["out"] / "STOP").unlink()
    ops.unload = orig
    before = len(invocations(env))
    assert run(env, SMOKE) == 0
    cj2 = chain_json(env)
    assert [l["status"] for l in cj2["progress"]["loads"]] == ["done", "done"] and cj2["epoch_id"] == epoch(["oc"])
    legs = schedules.legs(schedule(env))
    assert len(invocations(env)) - before == len([leg for leg in legs if leg["load"] == 1])     # load 0 not redone
    assert cj2["realized"] == [schedules.leg_key(leg) for leg in legs]


def test_the_exit_check_names_a_realized_order_that_differs_from_the_schedule(env, monkeypatch):
    real = schedules.check_realized
    monkeypatch.setattr(schedules, "check_realized", lambda s, r: real(s, list(r)[:-1]))
    assert run(env, SMOKE) == 2 and log_has(env, "realized order differs")


def test_the_real_entry_closure_uses_no_probe_or_adapter_module():
    from bench import identity_closure as ic
    closure = {p.name for p in ic.python_closure(REPO / "benchmark/chains/m64/run_m64_chain.py", REPO)}
    assert "chain_core.py" in closure and "schedules.py" in closure
    assert not closure & {"arm_runner.py", "arm_opencode.py", "tg1_runner.py", "m64_schedule.py", "run_tg1_chain.py"}
