"""P371 review r1 F9: a crash after the chain persisted an `accepted` / `exhausted` slot disposition but before it linked the
item's `.continue` file. The persisted disposition + the rows file prove the prefix: the resume finalizes it (`hook_stopped`, or
`validated` when it is the whole invocation) instead of quarantining it and silently rerunning the slots."""
from __future__ import annotations

import pytest

from bench import chain_core
from bench import chain_rows as cr
from bench.tests.m64_support import (  # noqa: F401  (fixture: env)
    PICK1, SMOKE, Crash, arg, chain_json, env, invocations, kill_probes, log_has, run)
from bench.tests.test_p371_m64_hooks import Script, cell_items, cheat_on, slot


def crash_at_continue(monkeypatch, match):
    real = chain_core.barrier_signal

    def signal(path, payload=None):
        if str(path).endswith(".continue") and match(str(path)):
            raise Crash()
        return real(path, payload)
    monkeypatch.setattr(chain_core, "barrier_signal", signal)
    return real


def table(env):
    return cr.load_slots(chain_json(env), env["out"])


def test_a_crash_between_an_accepted_disposition_and_its_continue_finalizes_the_proven_prefix(env, monkeypatch):
    seen = {"n": 0}

    def second(path):
        seen["n"] += 1
        return seen["n"] == 2                                   # the continue of item 1 of the first block
    real = crash_at_continue(monkeypatch, second)
    with pytest.raises(Crash):
        run(env, SMOKE)
    kill_probes(env)
    monkeypatch.setattr(chain_core, "barrier_signal", real)
    cj = chain_json(env)
    items = cell_items(env)
    assert [a["disposition"] for a in cj["progress"]["slot_attempts"]] == ["accepted", "accepted"]
    assert run(env, SMOKE) == 0
    cj = chain_json(env)
    first = next(i for i in cj["progress"]["invocations"] if i["file"].endswith("L0.block.a1.jsonl"))
    assert first["status"] == "hook_stopped" and first["hook_stop"] == dict(after_slot=slot(items[1]), disposition="accepted")
    assert first["accepted_slots"] == [slot(items[0]), slot(items[1])]
    assert not (env["out"] / "quarantine").exists() and not any(i["status"] == "quarantined" for i in cj["progress"]["invocations"])
    assert all(a.get("status") != "archived" for a in cj["progress"]["slot_attempts"])
    resumed = [c for c in invocations(env) if arg(c["argv"], "--lang") == "python"][1]
    assert arg(resumed["argv"], "--items") == items[2]                 # only the unaccepted slot runs again
    assert len(table(env).scored) == 16


def test_a_crash_before_the_continue_of_an_exhausted_disposition_finalizes_the_invocation(env, monkeypatch):
    items = cell_items(env)
    target = slot(items[1])
    real = crash_at_continue(monkeypatch, lambda p: ".rerun." in p)
    with pytest.raises(Crash):
        run(env, SMOKE, hooks=Script(after=cheat_on(target, 3)))
    kill_probes(env)
    monkeypatch.setattr(chain_core, "barrier_signal", real)
    assert [a["disposition"] for a in chain_json(env)["progress"]["slot_attempts"]][-1] == "exhausted"
    assert run(env, SMOKE) == 0
    cj = chain_json(env)
    last = [i for i in cj["progress"]["invocations"] if i["phase"] == "rerun"][-1]
    assert last["status"] == "validated" and last["accepted_slots"] == [target]
    assert not (env["out"] / "quarantine").exists()
    t = table(env)
    assert t.scored[target].disposition == "exhausted" and t.scored[target].strict_fail and len(t.scored) == 16
