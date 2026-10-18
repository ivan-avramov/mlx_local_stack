"""P371 phase 3b part 5 (A8 `new_segment`): a resumed M64 chain takes a FRESH worker, continues at the progress cursor's leg and
phase with only the unaccepted slots, quarantines partial / never-validated invocation files (sha manifest first), appends the
realized order once per leg key and refuses a validated rows file that changed after validation. A chain process death is
simulated by a `Crash` raised from a chain hook while the probe waits at its item barrier (the probe is then killed)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench import chain_hooks as ch
from bench import chain_rows as cr
from bench import schedules
from bench.tests.m64_support import (  # noqa: F401  (fixture: env)
    FAP, PICK1, PICK2, SMOKE, Crash, arg, calls, chain_json, env, invocations, kill_probes, log_has, run, schedule)


class CrashAt(ch.ChainHooks):
    """Accepts every slot, raising `Crash` at the n-th `before_attempt` call (1-based) of THIS process."""

    def __init__(self, *at):
        self.at, self.n = set(at), 0

    def before_attempt(self, slot):
        self.n += 1
        if self.n in self.at:
            raise Crash()
        return ch.Disposition.accept()


def crash_run(env, hooks, argv=SMOKE, **kw):
    with pytest.raises(Crash):
        run(env, argv, hooks=hooks, **kw)
    kill_probes(env)


def table(env):
    return cr.load_slots(chain_json(env), env["out"])


def statuses(env):
    return [(i["phase"], i["status"]) for i in chain_json(env)["progress"]["invocations"]]


# leg order of load 0 (s1 / PICK1): python b0 (3 items), python b1 (1), go b0 (3), go b1 (1); before_attempt calls 1-3, 4, 5-7, 8
LEG3_SLOT2 = 6


def test_a_crash_mid_leg_leaves_a_running_invocation_and_the_cursor_at_that_leg(env):
    crash_run(env, CrashAt(LEG3_SLOT2))
    cj = chain_json(env)
    running = [i for i in cj["progress"]["invocations"] if i["status"] == "running"]
    assert len(running) == 1 and running[0]["leg_key"][1] == "go" and running[0]["phase"] == "block"
    load = cj["progress"]["loads"][0]
    assert load["status"] == "running" and load["cursor"] == {"leg_index": 2, "phase": "block"}
    assert len(table(env).scored) == 4 and table(env).running == running            # the two python legs, validated


def test_resume_quarantines_the_partial_file_takes_a_fresh_worker_and_reruns_only_the_unaccepted_slots(env):
    crash_run(env, CrashAt(LEG3_SLOT2))
    assert run(env, SMOKE) == 0
    cj = chain_json(env)
    assert [l["status"] for l in cj["progress"]["loads"]] == ["done", "done"] and cj["progress"]["loads"][0]["load_gen"] == 0
    assert not (env["out"] / "s1" / "incomplete").exists()                      # new_segment never archives a load
    quarantined = [i for i in cj["progress"]["invocations"] if i["status"] == "quarantined"]
    assert len(quarantined) == 1 and quarantined[0]["file"].startswith("quarantine/")
    qdir = (env["out"] / quarantined[0]["file"]).parent
    manifest = json.loads((qdir / "MANIFEST.json").read_text())
    name = Path(quarantined[0]["file"]).name
    assert name in manifest["files"] and (qdir / name).is_file() and len(manifest["files"][name]) == 64
    t = table(env)
    assert len(t.scored) == 16 and not t.running                                # each slot exactly once
    assert len(calls(env, "load")) == 3                                         # PICK1 (crashed), PICK1 (fresh), PICK2
    workers = cj["progress"]["loads"][0]["workers"]
    assert [w["n"] for w in workers] == [0, 1] and workers[0]["pid"] != workers[1]["pid"]
    resumed = [i for i in cj["progress"]["invocations"] if i["status"] == "validated" and i["worker_n"] == 1]
    assert [i["leg_key"][1] for i in resumed] == ["go", "go"]                   # only the legs that were not accepted
    assert arg(invocations(env)[-5]["argv"], "--lang") in ("go", "python")
    assert cj["realized"] == [schedules.leg_key(leg) for leg in schedules.legs(schedule(env))]


def test_the_realized_order_is_appended_once_per_leg_key_across_two_resumes(env):
    crash_run(env, CrashAt(LEG3_SLOT2))
    crash_run(env, CrashAt(2))                                                  # the resumed go leg crashes at its slot 2
    assert run(env, SMOKE) == 0
    cj = chain_json(env)
    legs = schedules.legs(schedule(env))
    assert cj["realized"] == [schedules.leg_key(leg) for leg in legs] and len(set(map(json.dumps, cj["realized"]))) == 8
    q = [i for i in cj["progress"]["invocations"] if i["status"] == "quarantined"]
    assert len(q) == 2 and len({Path(i["file"]).parent for i in q}) == 2        # two quarantines, two manifests
    for rec in q:
        d = (env["out"] / rec["file"]).parent
        assert (d / "MANIFEST.json").is_file() and Path(rec["file"]).name in json.loads((d / "MANIFEST.json").read_text())["files"]
    assert len(table(env).scored) == 16 and cj["progress"]["loads"][0]["load_gen"] == 0
    assert len(calls(env, "load")) == 4


def test_the_quarantine_manifest_is_written_before_any_file_moves(env, monkeypatch):
    from bench import chain_core
    crash_run(env, CrashAt(LEG3_SLOT2))
    seen = []
    real = chain_core.shutil.move

    def spy(src, dst):
        if not seen:
            manifests = list((env["out"] / "quarantine").glob("*/MANIFEST.json"))
            seen.append(len(manifests))
        return real(src, dst)
    monkeypatch.setattr(chain_core.shutil, "move", spy)
    assert run(env, SMOKE) == 0
    assert seen == [1]


def test_a_validated_rows_file_that_changed_after_validation_aborts_the_resume(env):
    crash_run(env, CrashAt(LEG3_SLOT2))
    rec = next(i for i in chain_json(env)["progress"]["invocations"] if i["status"] == "validated")
    path = env["out"] / rec["file"]
    path.write_text(path.read_text() + "\n")
    before = len(invocations(env))
    assert run(env, SMOKE) == 2
    assert log_has(env, "sha256 differs") and len(invocations(env)) == before


def test_a_resume_after_the_chain_finished_changes_nothing(env):
    assert run(env, SMOKE) == 0
    n, before = len(invocations(env)), (env["out"] / "chain.json").read_text()
    assert run(env, SMOKE) == 0
    assert len(invocations(env)) == n and len(calls(env, "load")) == 2
    assert chain_json(env)["realized"] == json.loads(before)["realized"]


def test_the_web_evidence_of_a_quarantined_partial_is_recorded_before_the_files_move(env):
    crash_run(env, CrashAt(LEG3_SLOT2))
    assert run(env, SMOKE) == 0
    archived = [a for a in chain_json(env)["progress"]["slot_attempts"] if a.get("status") == "archived"]
    assert archived and all(a["web_evidence"] for a in archived)


def test_a_slot_attempt_of_a_quarantined_invocation_is_not_scored_but_the_rerun_is(env):
    crash_run(env, CrashAt(LEG3_SLOT2))
    assert run(env, SMOKE) == 0
    cj = chain_json(env)
    live = [a for a in cj["progress"]["slot_attempts"] if a.get("status") != "archived"]
    slots = [a["slot"] for a in live]
    assert len(slots) == len(set(slots)) == 16 and all(a["disposition"] == "accepted" for a in live)


def test_the_progress_cursor_is_consistent_or_the_resume_refuses(env):
    crash_run(env, CrashAt(LEG3_SLOT2))
    path = env["out"] / "chain.json"
    doc = json.loads(path.read_text())
    doc["progress"]["loads"][0]["cursor"] = {"leg_index": 99, "phase": "block"}      # ahead of every scored slot
    path.write_text(json.dumps(doc))
    assert run(env, SMOKE) == 2 and log_has(env, "cursor")
