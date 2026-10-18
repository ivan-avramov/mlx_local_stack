"""P371 phase 3b part 7 (R13, R23, R25, R29): `ChainHooks` at the item barrier of the shared chain core. The chain answers the
probe's `.ready` with `.go` after `run_before(slot)` (a pre-spawn incident persists its record, THEN `.stop`) and its `.done`
with `.continue` after the web evidence of the finished item was extracted and `run_after(slot, done)` decided (a rerun or a
block persists its disposition, THEN `.stop` with `{disposition}`). The default hooks are the no-op `accept`. Scored attempt
per slot = the latest non-cheat attempt; a re-run is a one-slot `rerun` invocation with `--attempt-rerun-index` + 1 (max 2)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench import arm_specs
from bench import chain_core as core
from bench import chain_hooks as ch
from bench import chain_rows as cr
from bench.tests.m64_support import (  # noqa: F401  (fixture: env)
    FAP, PICK1, PICK2, SMOKE, Crash, arg, calls, chain_json, env, invocations, kill_probes, log_has, run, schedule)

EPOCH = FAP.epoch_for(["oc"])


def cell_items(env, lang="python", pick=PICK1, block=0):
    s = schedule(env)
    load = next(l for l in s["loads"] if l["pick"] == pick and l["session"] == "s1")
    return next(c for c in load["cells"] if c["lang"] == lang)["blocks"][block]["items"]


def slot(item, lang="python", pick=PICK1, arm="oc"):
    return f"{EPOCH}|{arm}|{pick}|s1|{lang}|{item}"


class Script(ch.ChainHooks):
    """before(slot, n) / after(slot, done, n) callbacks; every call is recorded."""

    def __init__(self, before=None, after=None):
        self.before, self.after = before, after
        self.before_calls, self.after_calls = [], []

    def before_attempt(self, slot):
        self.before_calls.append(slot)
        return self.before(slot, len(self.before_calls)) if self.before else ch.Disposition.accept()

    def after_attempt(self, slot, done):
        self.after_calls.append((slot, done))
        return self.after(slot, done, len(self.after_calls)) if self.after else ch.Disposition.accept()


def cheat_on(target, times):
    """`rerun_same_slot` the first `times` decisions about `target` (the third re-run index exhausts)."""
    seen = {"n": 0}

    def after(sl, done, n):
        if sl == target and seen["n"] < times:
            seen["n"] += 1
            return ch.Disposition.rerun_same_slot("planted cheat")
        return ch.Disposition.accept()
    return after


def table(env):
    return cr.load_slots(chain_json(env), env["out"])


def records(env, file_part):
    return [i for i in chain_json(env)["progress"]["invocations"] if file_part in i["file"]]


# ---------------------------------------------------------------- the barrier protocol, default hooks
def test_the_default_hooks_accept_every_item_and_the_chain_answers_every_barrier_file(env):
    assert run(env, SMOKE) == 0
    rec = chain_json(env)["progress"]["invocations"][0]
    base = str(env["out"] / rec["file"])[:-len(".jsonl")]
    for k in range(3):
        for kind in ("ready", "go", "done", "continue"):
            assert Path(f"{base}.item{k}.{kind}").is_file(), (k, kind)
        assert not Path(f"{base}.item{k}.stop").exists()
    done = json.loads(Path(f"{base}.item0.done").read_text())
    assert done["id"] == "python/" + cell_items(env)[0] and done["attempt_id"].endswith("#a1.r0")
    t = table(env)
    assert len(t.scored) == 16 and not t.pending_reruns and not t.blocked


def test_before_and_after_hooks_see_every_slot_in_order_with_the_done_record(env):
    hooks = Script()
    assert run(env, SMOKE, hooks=hooks) == 0
    first = [slot(x) for x in cell_items(env)]
    assert hooks.before_calls[:3] == first and [s for s, _ in hooks.after_calls[:3]] == first
    assert len(hooks.before_calls) == len(hooks.after_calls) == 16
    assert all(d["id"].startswith("python/") for _, d in hooks.after_calls[:3])


def test_the_item_barrier_is_answered_only_when_the_manifest_says_it_is_on(env, monkeypatch):
    import dataclasses
    off = dict(arm_specs.OC.evidence_policy, item_barrier="off")
    monkeypatch.setitem(arm_specs.SPECS, "pi", dataclasses.replace(arm_specs.SPECS["pi"], evidence_policy=off))
    hooks = Script()
    argv = ["chain", "s1", "--smoke", "--arms", "pi", "--probe-code-sha", "pi=" + "9" * 64]
    assert run(env, argv, hooks=hooks, extra_env={"FAKE_ITEM_BARRIER": "off"}) == 0
    assert hooks.before_calls == [] and hooks.after_calls == []                    # no barrier: the hooks never run
    assert not list(env["out"].rglob("*.item*.ready"))
    atts = chain_json(env)["progress"]["slot_attempts"]
    assert len(atts) == 16 and all(a["disposition"] == "accepted" and a["web_evidence"]["sha256"] for a in atts)


def test_a_manifest_whose_barrier_policy_differs_from_the_arm_spec_is_a_barrier_mismatch(env):
    rc = run(env, SMOKE, extra_env={"FAKE_ITEM_BARRIER": "off"})
    assert rc == 2 and log_has(env, "BARRIER MISMATCH") and log_has(env, "evidence_policy")


# ---------------------------------------------------------------- R29 / A12: web evidence at the done barrier
def test_web_evidence_is_extracted_before_the_after_hook_decides(env):
    seen = []

    def after(sl, done, n):
        w = done["web_evidence"]
        seen.append((sl, Path(w["path"].replace("$STACK_WORKDIR", str(env["wd"]))).is_file(), len(w["sha256"])))
        return ch.Disposition.accept()
    assert run(env, SMOKE, hooks=Script(after=after)) == 0
    assert len(seen) == 16 and all(ok and n == 64 for _, ok, n in seen)


def test_every_disposition_is_persisted_before_its_barrier_file_is_written(env, monkeypatch):
    checks = []
    real = core.barrier_signal

    def spy(path, payload=None):
        name = Path(path).name
        doc = json.loads((env["out"] / "chain.json").read_text())
        atts = {(a["slot"], a["rerun_index"]): a["disposition"] for a in doc["progress"]["slot_attempts"]}
        checks.append((name, dict(atts), list(doc["progress"]["pre_spawn"])))
        return real(path, payload)
    monkeypatch.setattr(core, "barrier_signal", spy)
    target = slot(cell_items(env)[1])
    hooks = Script(after=cheat_on(target, 1))
    assert run(env, SMOKE, hooks=hooks) == 0
    stop = [c for c in checks if c[0].endswith(".stop")]
    assert len(stop) == 1 and stop[0][1][(target, 0)] == "cheat"
    first_continue = next(c for c in checks if c[0].endswith(".item0.continue"))
    assert any(k[0] == slot(cell_items(env)[0]) and v == "accepted" for k, v in first_continue[1].items())


# ---------------------------------------------------------------- R25: rerun_same_slot
def test_a_cheat_at_slot_two_of_three_reruns_slot_two_with_index_one_then_slot_three(env):
    items = cell_items(env)
    target = slot(items[1])
    assert run(env, SMOKE, hooks=Script(after=cheat_on(target, 1))) == 0
    cj = chain_json(env)
    first = records(env, "L0.block.a1")[0]
    assert first["status"] == "hook_stopped" and first["accepted_slots"] == [slot(items[0]), target]
    assert first["hook_stop"] == dict(after_slot=target, disposition="cheat")
    rerun = records(env, "L0.rerun.a2")[0]
    assert rerun["phase"] == "rerun" and rerun["rerun_index"] == 1 and rerun["expected_slots"] == [target]
    tail = records(env, "L0.block.a3")[0]
    assert tail["expected_slots"] == [slot(items[2])] and tail["status"] == "validated"
    argv = invocations(env)[1]["argv"]
    assert arg(argv, "--items") == items[1] and arg(argv, "--attempt-rerun-index") == "1" and arg(argv, "--expect-items") == \
        "python/" + items[1]
    names = [c[0] for c in env["ops"].calls]
    spawn_second = names.index("search_restart", names.index("search_restart") + 1)
    assert names[spawn_second:spawn_second + 3] == ["search_restart", "reset_cache_session", "warmup"]   # before the rerun
    t = table(env)
    sc = t.scored[target]
    assert sc.rerun_index == 1 and sc.disposition == "accepted" and not sc.strict_fail
    assert [a.disposition for a in t.attempts[target]] == ["cheat", "accepted"]
    assert t.scored[slot(items[0])].rerun_index == 0 and len(t.attempts[slot(items[0])]) == 1       # slot 1 never rerun
    cheat = next(a for a in cj["progress"]["slot_attempts"] if a["slot"] == target and a["rerun_index"] == 0)
    assert cheat["output_tokens"] == 1000 and core.slot_tokens(cj, target) == 1000
    assert len(invocations(env)) == 8 + 2


def test_the_cheat_attempts_row_is_an_attempt_record_never_a_scored_row(env):
    items = cell_items(env)
    target = slot(items[1])
    assert run(env, SMOKE, hooks=Script(after=cheat_on(target, 1))) == 0
    t = table(env)
    assert t.scored[target].file.endswith("L0.rerun.a2.jsonl")
    assert t.attempts[target][0].row is not None and t.attempts[target][0].file.endswith("L0.block.a1.jsonl")
    assert sum(1 for s in t.scored.values() if s.file and "L0.block.a1" in s.file) == 1          # only slot 1 from the stopped file


def test_two_further_cheats_exhaust_the_slot_and_score_its_latest_attempt_as_a_strict_fail(env):
    items = cell_items(env)
    target = slot(items[1])
    hooks = Script(after=cheat_on(target, 3))
    assert run(env, SMOKE, hooks=hooks) == 0
    t = table(env)
    sc = t.scored[target]
    assert sc.rerun_index == 2 and sc.disposition == "exhausted" and sc.strict_fail is True
    assert [a.disposition for a in t.attempts[target]] == ["cheat", "cheat", "exhausted"]
    assert len([c for s, c in hooks.after_calls if s == target]) == 3                              # never a fourth attempt
    assert [r["phase"] for r in chain_json(env)["progress"]["invocations"][:5]] == ["block", "rerun", "rerun", "block", "block"]
    assert core.slot_tokens(chain_json(env), target) == 2000                                       # the two cheat attempts


def test_a_block_disposition_persists_unclear_stops_the_probe_and_stops_the_chain_for_the_operator(env):
    items = cell_items(env)
    target = slot(items[1])
    after = lambda sl, d, n: ch.Disposition.block("needs a human") if sl == target else ch.Disposition.accept()   # noqa: E731
    assert run(env, SMOKE, hooks=Script(after=after)) == 2
    assert log_has(env, "blocked") and log_has(env, "needs a human")
    first = records(env, "L0.block.a1")[0]
    assert first["status"] == "hook_stopped" and first["hook_stop"] == dict(after_slot=target, disposition="unclear")
    t = table(env)
    assert t.blocked == [target] and target not in t.scored
    man = json.loads((env["out"] / first["manifest"]).read_text())
    assert man["hook_stop"] == dict(after_slot="python/" + items[1], disposition="unclear")
    assert run(env, SMOKE) == 2 and log_has(env, "blocked")                                         # still blocked on resume


# ---------------------------------------------------------------- crash-resume replays persisted dispositions
def test_a_crash_between_the_persisted_cheat_and_the_rerun_reruns_slot_two_once_with_the_cheat_tokens_kept(env):
    items = cell_items(env)
    target = slot(items[1])
    ops = env["ops"]
    armed = {"on": False}
    inner = cheat_on(target, 1)

    def after(sl, done, n):
        out = inner(sl, done, n)
        armed["on"] = armed["on"] or out.kind == "rerun_same_slot"
        return out
    real = ops.reset_cache_session

    def reset(model):
        if armed["on"] and not env.get("crashed"):
            env["crashed"] = True
            raise Crash()
        return real(model)
    ops.reset_cache_session = reset
    with pytest.raises(Crash):
        run(env, SMOKE, hooks=Script(after=after))
    kill_probes(env)
    first = records(env, "L0.block.a1")[0]
    assert first["status"] == "hook_stopped"                                                       # finalized before the crash
    assert run(env, SMOKE, hooks=Script()) == 0
    t = table(env)
    assert [a.disposition for a in t.attempts[target]] == ["cheat", "accepted"] and t.scored[target].rerun_index == 1
    assert len(t.attempts[slot(items[0])]) == 1 and len(t.scored) == 16
    assert core.slot_tokens(chain_json(env), target) == 1000
    reruns = [i for i in chain_json(env)["progress"]["invocations"] if i["phase"] == "rerun"]
    assert len(reruns) == 1 and reruns[0]["status"] == "validated"


def test_a_crash_after_the_cheat_is_persisted_but_before_the_stop_file_is_written_is_replayed_on_resume(env, monkeypatch):
    items = cell_items(env)
    target = slot(items[1])
    real = core.barrier_signal

    def die_on_stop(path, payload=None):
        if str(path).endswith(".stop"):
            raise Crash()
        return real(path, payload)
    monkeypatch.setattr(core, "barrier_signal", die_on_stop)
    with pytest.raises(Crash):
        run(env, SMOKE, hooks=Script(after=cheat_on(target, 1)))
    kill_probes(env)
    monkeypatch.setattr(core, "barrier_signal", real)
    cj = chain_json(env)
    assert [i["status"] for i in cj["progress"]["invocations"]] == ["running"]                      # the stop never landed
    assert any(a["slot"] == target and a["disposition"] == "cheat" for a in cj["progress"]["slot_attempts"])
    assert run(env, SMOKE, hooks=Script()) == 0
    t = table(env)
    assert [a.disposition for a in t.attempts[target]] == ["cheat", "accepted"]
    assert len(t.attempts[slot(items[0])]) == 1 and len(t.scored) == 16
    first = [i for i in chain_json(env)["progress"]["invocations"] if i["file"].endswith("L0.block.a1.jsonl")][0]
    assert first["status"] == "hook_stopped" and first["accepted_slots"] == [slot(items[0]), target]
    assert sum(1 for c in invocations(env) if arg(c["argv"], "--attempt-rerun-index") == "1") == 1


# ---------------------------------------------------------------- R13: before_attempt, pre-spawn incidents
def pre_spawn_on(target, times, cause="d2_health"):
    seen = {"n": 0}

    def before(sl, n):
        if sl == target and seen["n"] < times:
            seen["n"] += 1
            return ch.Disposition.pre_spawn_incident(cause)
        return ch.Disposition.accept()
    return before


def test_a_before_attempt_failure_at_slot_two_is_a_pre_spawn_incident_with_a_same_slot_retry(env):
    items = cell_items(env)
    target = slot(items[1])
    hooks = Script(before=pre_spawn_on(target, 1))
    assert run(env, SMOKE, hooks=hooks) == 0
    cj = chain_json(env)
    first = records(env, "L0.block.a1")[0]
    assert first["status"] == "hook_stopped" and first["accepted_slots"] == [slot(items[0])]
    assert first["hook_stop"] == dict(before_slot=target)
    assert [p["slot"] for p in cj["progress"]["pre_spawn"]] == [target] and cj["progress"]["pre_spawn"][0]["cause"] == "d2_health"
    assert [(i["slot"], i["cause"], i["attempt"], i["output_tokens"]) for i in cj["incidents"]] == [(target, "d2_health", 1, 0)]
    retry = records(env, "L0.retry.a2")[0]
    assert retry["phase"] == "retry" and retry["expected_slots"] == [target, slot(items[2])] and retry["status"] == "validated"
    names = [c[0] for c in env["ops"].calls]
    i = names.index("unload")
    assert names[i:i + 5] == ["unload", "load", "a4_gate", "reset_cache_session", "warmup"]
    t = table(env)
    assert len(t.scored) == 16 and t.open_pre_spawn == [] and len(t.attempts[slot(items[0])]) == 1
    man = json.loads((env["out"] / first["manifest"]).read_text())
    assert man["hook_stop"] == dict(before_slot="python/" + items[1]) and man["cleanup_status"]["completed"] is True
    assert hooks.before_calls.count(target) == 2


def test_a_hook_infrastructure_error_is_the_same_pre_spawn_incident(env):
    items = cell_items(env)
    target = slot(items[0])
    seen = {"n": 0}

    def before(sl, n):
        if sl == target and not seen["n"]:
            seen["n"] += 1
            raise ch.HookInfrastructureError("d2_unreachable")
        return ch.Disposition.accept()
    assert run(env, SMOKE, hooks=Script(before=before)) == 0
    assert [i["cause"] for i in chain_json(env)["incidents"]] == ["d2_unreachable"]
    first = records(env, "L0.block.a1")[0]
    assert first["status"] == "hook_stopped" and first["accepted_slots"] == [] and first["sha256"] is None


def test_a_pre_spawn_incident_twice_in_one_slot_is_a_transport_dnf_row(env):
    items = cell_items(env)
    target = slot(items[1])
    assert run(env, SMOKE, hooks=Script(before=pre_spawn_on(target, 2))) == 0
    cj = chain_json(env)
    assert len(cj["dnf"]) == 1 and cj["dnf"][0]["slot"] == target and cj["dnf"][0]["failed_attempt_output_tokens"] == 0
    assert [i["attempt"] for i in cj["incidents"]] == [1, 2]
    t = table(env)
    assert t.scored[target].source == "dnf" and len(t.scored) == 16 and t.open_pre_spawn == []
    assert [r["phase"] for r in cj["progress"]["invocations"][:3]] == ["block", "retry", "retry"]


def test_a_crash_after_the_pre_spawn_record_is_persisted_replays_the_retry_once(env, monkeypatch):
    items = cell_items(env)
    target = slot(items[1])
    real = core.barrier_signal

    def die_on_stop(path, payload=None):
        if str(path).endswith(".stop"):
            raise Crash()
        return real(path, payload)
    monkeypatch.setattr(core, "barrier_signal", die_on_stop)
    with pytest.raises(Crash):
        run(env, SMOKE, hooks=Script(before=pre_spawn_on(target, 1)))
    kill_probes(env)
    monkeypatch.setattr(core, "barrier_signal", real)
    cj = chain_json(env)
    assert [p["slot"] for p in cj["progress"]["pre_spawn"]] == [target] and len(cj["incidents"]) == 1
    assert run(env, SMOKE, hooks=Script()) == 0
    cj = chain_json(env)
    assert len(cj["incidents"]) == 1 and cj["dnf"] == []                                           # the incident counted once
    t = table(env)
    assert len(t.scored) == 16 and t.open_pre_spawn == [] and len(t.attempts[slot(items[0])]) == 1
    retries = [i for i in cj["progress"]["invocations"] if i["phase"] == "retry"]
    assert len(retries) == 1 and retries[0]["expected_slots"][0] == target and retries[0]["status"] == "validated"
