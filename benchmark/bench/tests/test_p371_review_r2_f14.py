"""P371 review r2 F14: after the probe exits the chain always reads the invocation's own final manifest and hydrates the cleanup
receipt, the abort stamp / cancelled item and the abort evidence from it, whether or not the barrier ever observed it (a STOP
that lands before the first manifest is seen); a missing or invalid manifest is recorded explicitly."""
from __future__ import annotations

import json
import threading

from bench.tests.m64_support import SMOKE, chain_json, env, log_has, run      # noqa: F401  (fixture: env)


def stop_at_spawn(env):
    ops, real = env["ops"], env["ops"].create_time

    def create_time(pid):
        # the probe is past its start checks but still sleeping before its first manifest when STOP lands
        threading.Timer(0.8, lambda: (env["out"] / "STOP").write_text("stop\n")).start()
        return real(pid)
    ops.extra_env["FAKE_PRE_MANIFEST_S"] = "2.5"
    ops.create_time = create_time


def test_a_stop_before_the_first_manifest_is_observed_still_hydrates_the_attempt(env):
    stop_at_spawn(env)
    assert run(env, SMOKE, timers={"t_coop_scale": 0.05}) == 3
    att = chain_json(env)["attempts"][0]
    assert att["run_id"], "the final manifest's run id is recorded although the barrier never saw it"
    assert att["cleanup_status"] is not None and att["cleanup_status"]["completed"] is True
    assert att["transport_abort"] is not None and "abort_evidence" in att
    assert att["manifest_observed"] is False
    rec = chain_json(env)["progress"]["invocations"][0]
    assert rec["manifest_observed"] is False and rec["manifest_problem"] is None


def test_a_missing_invalid_or_foreign_manifest_after_exit_is_recorded_explicitly(env, tmp_path):
    from bench.tests.m64_support import FakeOps, M, SMOKE as ARGV
    a = M.parse_args(ARGV + ["--out-root", str(tmp_path / "o")])
    chain = M.build_chain(a, FakeOps(tmp_path), M.Timers(), lambda m: None, {"python": ["a"], "go": ["b"]}, tmp_path / "o", {})
    out = tmp_path / "o" / "s1" / "rows.a1.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    view = dict(out=str(out), slot_base="e|oc|m|s1|python", arm="oc", model="m", lang="python", seed_base=1,
                label=chain.label_of("oc"))
    worker = dict(pid=7, create_time=1.0)
    att = dict(attempt=1, worker=worker, run_id=None, transport_abort=None, cancelled_item=None, cleanup_status=None)
    chain.hydrate_from_manifest(att, view, out)
    assert att["manifest_problem"] == "missing" and att["cleanup_status"] is None and att["manifest_observed"] is False
    out.with_suffix(".manifest.json").write_text("{not json")
    att = dict(attempt=1, worker=worker, run_id=None, transport_abort=None, cancelled_item=None, cleanup_status=None)
    chain.hydrate_from_manifest(att, view, out)
    assert att["manifest_problem"] == "invalid"
    out.with_suffix(".manifest.json").write_text(json.dumps({"run_id": "other", "model": "m", "worker": worker, "cleanup_status": {},
                                                                   "runtime": {"lang": "python", "seed_base": 1, "scaffold": chain.label_of("oc"), "arm": "oc"}}))
    att = dict(attempt=1, worker=worker, run_id="mine", transport_abort=None, cancelled_item=None, cleanup_status=None)
    chain.hydrate_from_manifest(att, view, out)
    assert att["manifest_problem"] == "run_id differs" and att["cleanup_status"] is None
