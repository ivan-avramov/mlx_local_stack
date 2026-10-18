"""P371 review r4 F22: quarantine / archive repoint `progress.abort_evidence[].invocation` inside the SAME F4 move transaction (the
intent lists the repoints; recovery replays them), so evidence never points at a path the move left."""
from __future__ import annotations

import pytest

from bench import chain_core
from bench.tests.m64_support import SMOKE, Crash, chain_json, env, kill_probes, run      # noqa: F401  (fixture: env)
from bench.tests.test_p371_review_r3_f17 import crash_before_hydration
from bench.tests.test_p371_review_r1_f4 import MoveCrash

PLAN = {"oc": [{"abort_after": 1, "cause": "server_error", "tokens": 5, "evidence": "export"}, "normal"]}


def crashed_after_exit(env, monkeypatch):
    real = crash_before_hydration(monkeypatch)
    with pytest.raises(Crash):
        run(env, SMOKE, plan=PLAN)
    kill_probes(env)
    monkeypatch.setattr(chain_core.Chain, "hydrate_from_manifest", real)


def check(env):
    cj = chain_json(env)
    first = next(i for i in cj["progress"]["invocations"] if i["attempt"] == 1)
    (found,) = [r for r in cj["progress"]["abort_evidence"] if r["attempt"] == 1]
    assert first["status"] == "quarantined" and found["invocation"] == first["file"]
    assert (env["out"] / found["invocation"]).is_file()


def test_the_abort_evidence_reference_follows_the_quarantine_move(env, monkeypatch):
    crashed_after_exit(env, monkeypatch)
    assert run(env, SMOKE, plan={"oc": ["normal"]}) == 0
    check(env)


@pytest.mark.parametrize("n", [1, 3])
def test_a_crash_in_the_middle_of_the_move_replays_the_reference_repoint(env, monkeypatch, n):
    crashed_after_exit(env, monkeypatch)
    mover = MoveCrash(monkeypatch, n)
    with pytest.raises(Crash):
        run(env, SMOKE, plan={"oc": ["normal"]})
    monkeypatch.setattr(chain_core.shutil, "move", mover.real)
    assert run(env, SMOKE, plan={"oc": ["normal"]}) == 0
    check(env)
