"""P371 review r3 F17 on the tg1 configuration (`restart_load`): the resume hydrates the crashed `running` invocation first."""
from __future__ import annotations

import pytest

from bench import chain_core
from bench.tests.test_c147_chain_runner import chain_json, env, run      # noqa: F401  (fixture: env)


class Crash(BaseException):
    pass


def test_tg1_resume_hydrates_a_running_invocation_before_archiving_it(env, monkeypatch):
    real = chain_core.Chain.hydrate_from_manifest
    state = {"n": 0}

    def hydrate(self, *a, **k):
        state["n"] += 1
        if state["n"] == 1:
            raise Crash()
        return real(self, *a, **k)
    monkeypatch.setattr(chain_core.Chain, "hydrate_from_manifest", hydrate)
    argv = ["chain", "reload", "--probe-code-sha", "9" * 64]
    with pytest.raises(Crash):
        run(env, argv, plan=["abort_after_n", "normal"], extra_env={"FAKE_N": "2"})
    monkeypatch.setattr(chain_core.Chain, "hydrate_from_manifest", real)
    assert chain_json(env)["attempts"][0]["cleanup_status"] is None
    assert run(env, argv, plan=["normal"]) == 0
    cj = chain_json(env)
    assert cj["attempts"][0]["cleanup_status"] is not None and cj["attempts"][0]["run_id"]
    assert len([r for r in cj["progress"]["abort_evidence"] if r["attempt"] == 1]) == 1
