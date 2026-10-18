"""P371 phase 4 (A13, R8, P374): the chain verifies each arm's contract artifact (path + sha256 named in `ChainConfig`, frozen
in `chain.json.artifacts.contract`) at entry, resume, every launch / barrier / validation and exit. A non-smoke chain refuses
a missing, failed, incomplete (OWED), malformed or drifted artifact (a replacement mid-chain aborts rc 2); a smoke chain
allows `incomplete` only. The M64 entry against the fake arm probe and a fake ChainOps (`m64_support`); no router, worker or
GPU."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from bench import chain_hooks as ch
from bench import contract_artifact as ca
from bench.tests.m64_support import (  # noqa: F401  (fixture: env)
    FAP, SMOKE, Crash, calls, chain_json, env, kill_probes, log_has, run)

NONSMOKE = ["chain", "s1", "--arms", "oc", "--probe-code-sha", "oc=" + "9" * 64]


def snapshot_sha(arm="oc"):
    return FAP.snapshot_for(arm)["sha256"]


def artifact_doc(verdict="incomplete", *, snapshot=None, version="2.0.20"):
    outcomes = {n: ("pass", "") for n in ca.CHECKS}
    if verdict == "incomplete":
        outcomes.update({n: ("OWED", "owed") for n in ca.OWED_BY})
    elif verdict == "fail":
        outcomes["compaction"] = ("fail", "compaction tokens not counted")
    return ca.build("oc", snapshot or snapshot_sha(), version, outcomes)


def put(tmp_path, verdict="incomplete", name="contract_oc.json", **kw):
    path = tmp_path / name
    ca.write(path, artifact_doc(verdict, **kw))
    return path


def with_artifact(argv, path):
    return list(argv) + ["--contract-artifact", f"oc={path}"]


def nothing_started(env):
    return not (env["out"] / "chain.json").exists() and not calls(env, "start_router", "load", "a4_gate")


# ---------------------------------------------------------------- non-smoke entry refusals
def test_a_non_smoke_chain_with_no_contract_artifact_refuses_before_anything_starts(env):
    assert run(env, NONSMOKE) == 2
    assert log_has(env, "contract artifact") and log_has(env, "oc") and nothing_started(env)


def test_a_non_smoke_chain_refuses_an_incomplete_artifact_and_names_the_owed_checks(env, tmp_path):
    assert run(env, with_artifact(NONSMOKE, put(tmp_path, "incomplete"))) == 2
    assert log_has(env, "incomplete") and log_has(env, "shared_search_tool") and log_has(env, "p201_rerun")
    assert nothing_started(env)


def test_a_non_smoke_chain_refuses_a_failed_artifact(env, tmp_path):
    assert run(env, with_artifact(NONSMOKE, put(tmp_path, "fail"))) == 2
    assert log_has(env, "FAILED") and log_has(env, "compaction") and nothing_started(env)


def test_a_non_smoke_chain_refuses_an_artifact_of_another_snapshot(env, tmp_path):
    assert run(env, with_artifact(NONSMOKE, put(tmp_path, "pass", snapshot="6" * 64))) == 2
    assert log_has(env, "another snapshot") and nothing_started(env)


def test_a_non_smoke_chain_refuses_a_hand_edited_artifact(env, tmp_path):
    path = put(tmp_path, "incomplete")
    doc = json.loads(path.read_text())
    doc["verdict"] = "pass"                                             # the inner hash is now stale, the checks say OWED
    path.write_text(json.dumps(doc))
    assert run(env, with_artifact(NONSMOKE, path)) == 2
    assert log_has(env, "contradicts") or log_has(env, "does not match")


def test_a_non_smoke_chain_accepts_a_passing_artifact_and_freezes_it(env, tmp_path):
    path = put(tmp_path, "pass")
    (env["out"]).mkdir(parents=True)
    (env["out"] / "STOP").write_text("")                                # past the entry checks; nothing is to be launched
    assert run(env, with_artifact(NONSMOKE, path)) == 3
    cj = chain_json(env)
    assert cj["artifacts"]["contract"] == {"oc": dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())}
    assert not log_has(env, "contract artifact of")


def test_a_missing_artifact_file_is_refused_at_the_command_line(env, tmp_path):
    with pytest.raises(SystemExit):
        run(env, with_artifact(NONSMOKE, tmp_path / "gone.json"))


# ---------------------------------------------------------------- smoke
def test_a_smoke_chain_runs_with_an_incomplete_artifact_and_freezes_its_ref(env, tmp_path):
    path = put(tmp_path, "incomplete")
    assert run(env, with_artifact(SMOKE, path)) == 0
    assert chain_json(env)["artifacts"]["contract"]["oc"]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_a_smoke_chain_without_an_artifact_for_an_arm_still_runs(env):
    assert run(env, SMOKE) == 0 and chain_json(env)["artifacts"]["contract"] == {}


def test_a_smoke_chain_refuses_a_failed_artifact(env, tmp_path):
    assert run(env, with_artifact(SMOKE, put(tmp_path, "fail"))) == 2
    assert log_has(env, "FAILED") and nothing_started(env)


def test_a_smoke_chain_refuses_an_artifact_of_another_snapshot(env, tmp_path):
    assert run(env, with_artifact(SMOKE, put(tmp_path, "incomplete", snapshot="6" * 64))) == 2
    assert log_has(env, "another snapshot")


# ---------------------------------------------------------------- drift, replacement and removal while the chain runs
class AtCall:
    """Run `act` at the n-th `power_ok` call of the chain's ops (once per launch: after the launch verification, before the
    probe is spawned) - the moment between two contract verifications."""

    def __init__(self, ops, n, act):
        self.ops, self.n, self.count, self.act = ops, n, 0, act
        self.orig = ops.power_ok
        ops.power_ok = self

    def __call__(self):
        self.count += 1
        if self.count == self.n:
            self.act()
        return self.orig()


@pytest.mark.parametrize("smoke", [True, False])
def test_replacing_the_artifact_mid_chain_aborts_rc_2_even_with_another_valid_artifact(env, tmp_path, smoke):
    path = put(tmp_path, "incomplete" if smoke else "pass")
    other = put(tmp_path, "incomplete" if smoke else "pass", name="other.json", version="2.0.21")
    AtCall(env["ops"], 4, lambda: path.write_bytes(other.read_bytes()))
    rc = run(env, with_artifact(SMOKE if smoke else NONSMOKE, path))
    assert rc == 2 and log_has(env, "sha256 drift") and log_has(env, "contract artifact of oc")
    frozen = chain_json(env)["artifacts"]["contract"]["oc"]["sha256"]
    assert frozen != hashlib.sha256(path.read_bytes()).hexdigest()           # the record keeps the original ref


def test_a_change_between_the_launch_check_and_the_first_manifest_is_a_barrier_mismatch(env, tmp_path):
    path = put(tmp_path, "incomplete")
    AtCall(env["ops"], 1, lambda: path.write_bytes(path.read_bytes() + b" "))
    assert run(env, with_artifact(SMOKE, path)) == 2
    assert log_has(env, "BARRIER MISMATCH") and log_has(env, "contract artifact of oc")


def test_removing_the_artifact_mid_chain_aborts_even_in_smoke(env, tmp_path):
    path = put(tmp_path, "incomplete")
    AtCall(env["ops"], 3, lambda: path.unlink())
    assert run(env, with_artifact(SMOKE, path)) == 2
    assert log_has(env, "missing or unreadable")


def test_an_artifact_that_drifts_during_the_last_leg_aborts_at_exit(env, tmp_path):
    path = put(tmp_path, "incomplete")
    ops = env["ops"]
    ops.on_unload = lambda: path.write_bytes(path.read_bytes() + b"\n") if len(ops.names("unload")) >= 2 else None
    assert run(env, with_artifact(SMOKE, path)) == 2
    assert log_has(env, "exit") and log_has(env, "sha256 drift")


# ---------------------------------------------------------------- resume
class CrashAt(ch.ChainHooks):
    def __init__(self, at):
        self.at, self.n = at, 0

    def before_attempt(self, slot):
        self.n += 1
        if self.n == self.at:
            raise Crash()
        return ch.Disposition.accept()


def test_a_resume_with_the_artifact_replaced_is_refused_and_the_frozen_record_is_untouched(env, tmp_path):
    path = put(tmp_path, "incomplete")
    argv = with_artifact(SMOKE, path)
    with pytest.raises(Crash):
        run(env, argv, hooks=CrashAt(2))
    kill_probes(env)
    before = (env["out"] / "chain.json").read_bytes()
    path.write_bytes(put(tmp_path, "incomplete", name="other.json", version="2.0.21").read_bytes())
    assert run(env, argv) == 2
    assert log_has(env, "chain_config") or log_has(env, "contract artifact")
    assert (env["out"] / "chain.json").read_bytes() == before


def test_a_resume_with_the_artifact_unchanged_continues(env, tmp_path):
    path = put(tmp_path, "incomplete")
    argv = with_artifact(SMOKE, path)
    with pytest.raises(Crash):
        run(env, argv, hooks=CrashAt(2))
    kill_probes(env)
    assert run(env, argv) == 0


def test_a_resume_refuses_an_artifact_that_was_removed(env, tmp_path):
    path = put(tmp_path, "incomplete")
    argv = with_artifact(SMOKE, path)
    with pytest.raises(Crash):
        run(env, argv, hooks=CrashAt(2))
    kill_probes(env)
    path.unlink()
    with pytest.raises(SystemExit):                                      # the argument check (a readable file) refuses
        run(env, argv)


def test_the_tg1_chain_is_unaffected_by_the_contract_check():
    from bench import chain_core as core
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "run_tg1_chain_for_contract", Path(__file__).resolve().parents[2] / "chains/c147/run_tg1_chain.py")
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)
    assert entry.tg1_config(type("A", (), {"predictor": "off"})()).contract_artifacts == ()
    assert core.Chain.contract_problems is not None
