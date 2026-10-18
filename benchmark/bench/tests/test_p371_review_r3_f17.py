"""P371 review r3 F17: a crash after the probe exited but before `attempt-ended` leaves a `running` invocation; the resume hydrates
it from its own final manifest (same validation as F16) BEFORE salvage / quarantine, so its cleanup receipt and abort evidence are
kept; hydrating twice does not duplicate the abort evidence."""
from __future__ import annotations

import pytest

from bench import chain_core
from bench.tests.m64_support import SMOKE, Crash, chain_json, env, kill_probes, run      # noqa: F401  (fixture: env)


def crash_before_hydration(monkeypatch):
    real = chain_core.Chain.hydrate_from_manifest
    state = {"n": 0}

    def hydrate(self, *a, **k):
        state["n"] += 1
        if state["n"] == 1:
            raise Crash()
        return real(self, *a, **k)
    monkeypatch.setattr(chain_core.Chain, "hydrate_from_manifest", hydrate)
    return real


def test_m64_resume_hydrates_a_running_invocation_before_quarantining_it(env, monkeypatch):
    plan = {"oc": [{"abort_after": 1, "cause": "server_error", "tokens": 5, "evidence": "export"}, "normal"]}
    real = crash_before_hydration(monkeypatch)
    with pytest.raises(Crash):
        run(env, SMOKE, plan=plan)
    kill_probes(env)
    monkeypatch.setattr(chain_core.Chain, "hydrate_from_manifest", real)
    assert chain_json(env)["attempts"][0]["cleanup_status"] is None            # the crash lost it
    assert run(env, SMOKE, plan={"oc": ["normal"]}) == 0
    cj = chain_json(env)
    att = cj["attempts"][0]
    assert att["cleanup_status"]["completed"] is True and att["run_id"] and att["abort_evidence"]["web_evidence"]["sha256"]
    first = cj["progress"]["invocations"][0]
    records = [r for r in cj["progress"]["abort_evidence"] if r["invocation"] == first["file"] or r["attempt"] == 1]
    assert len(records) == 1 and first["status"] == "quarantined"


def test_hydrating_twice_does_not_duplicate_the_abort_evidence(tmp_path):
    from bench.tests.test_p371_review_r3_f16 import build, hydrate
    chain, out, view, worker, good = build(tmp_path)
    good["transport_abort"] = {"error": "x", "evidence": None}
    att = hydrate(chain, out, view, worker, good)
    chain.seen_run_ids.discard("R-good")
    att["run_id"] = None
    chain.hydrate_from_manifest(att, view, out, {"expected_slots": ["e|oc|m|s1|python|a"], "nonce": "a" * 64})
    assert len([r for r in chain.progress["abort_evidence"] if r["attempt"] == 1]) == 1
