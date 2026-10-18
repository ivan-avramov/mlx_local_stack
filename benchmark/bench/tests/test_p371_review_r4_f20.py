"""P371 review r4 F20: `manifest_hydrated: true` is persisted on the invocation record only AFTER hydration (cleanup, abort stamp,
evidence extraction with the transcript sha check) completed; a crash in the middle leaves it unset so the resume retries
idempotently; an extraction failure is recorded as `hydration_failure`, never silently skipped."""
from __future__ import annotations

import pytest

from bench import chain_core
from bench.tests.m64_support import SMOKE, Crash, chain_json, env, kill_probes, log_has, run      # noqa: F401  (fixture: env)

PLAN = {"oc": [{"abort_after": 1, "cause": "server_error", "tokens": 5, "evidence": "export"}, "normal"]}


def test_a_crash_after_the_problem_is_known_but_before_the_evidence_is_written_is_retried_at_resume(env, monkeypatch):
    real = chain_core.Chain._record_abort_evidence
    state = {"n": 0}

    def boom(self, *a, **k):
        state["n"] += 1
        if state["n"] == 1:
            raise Crash()
        return real(self, *a, **k)
    monkeypatch.setattr(chain_core.Chain, "_record_abort_evidence", boom)
    with pytest.raises(Crash):
        run(env, SMOKE, plan=PLAN)
    kill_probes(env)
    monkeypatch.setattr(chain_core.Chain, "_record_abort_evidence", real)
    first = chain_json(env)["progress"]["invocations"][0]
    assert first["status"] == "running" and not first.get("manifest_hydrated")
    assert run(env, SMOKE, plan={"oc": ["normal"]}) == 0
    cj = chain_json(env)
    records = [r for r in cj["progress"]["abort_evidence"] if r["attempt"] == 1]
    assert len(records) == 1 and records[0]["web_evidence"]["sha256"]
    assert next(i for i in cj["progress"]["invocations"] if i["attempt"] == 1).get("manifest_hydrated") is True


def test_a_failed_extraction_is_recorded_not_skipped(env):
    plan = {"oc": [{"abort_after": 1, "cause": "server_error", "tokens": 5, "evidence": "export_badsha"}, "normal"]}
    assert run(env, SMOKE, plan=plan) == 2
    first = chain_json(env)["progress"]["invocations"][0]
    assert "sha256" in first["hydration_failure"] and not first.get("manifest_hydrated")
    assert not chain_json(env)["progress"]["abort_evidence"]


def test_a_completed_hydration_sets_the_flag_on_every_path(env):
    assert run(env, SMOKE, plan=PLAN) == 0
    assert all(i.get("manifest_hydrated") is True for i in chain_json(env)["progress"]["invocations"]
               if i["status"] != "running")
