"""S27 §5 / §8.2: harness faults rerun before the outcome and are flagged after it; typed abort stamps; the chain's second scan;
the harness DNFs and their cap; hold / pause episodes; the P426 slot table (`chain_rows`)."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from bench import chain_core as core
from bench import chain_hooks as ch
from bench import chain_ops as co
from bench import chain_rows as cr
from bench import p426_hooks as ph
from bench import p426_wave2 as w2
from bench.tests.test_b2_s3_core import BASE, GOOD_CLEANUP, barrier, bare, incomplete, scenario  # noqa: F401
from bench.tests import test_b2_s4_reconcile as R4

SLOT_A = f"{BASE}|a"
CLEAN2 = dict(GOOD_CLEANUP, schema=2, foreign_new=[], foreign_new_count=0, unreadable_count=0)


class Broken(ch.ChainHooks):
    def before_attempt(self, slot, context=None):
        raise ch.HookInfrastructureError("metrics_unreadable")

    def after_attempt(self, slot, done, context=None):
        raise ch.HookInfrastructureError("record_write_failed")


class Accounting(ch.ChainHooks):
    def after_attempt(self, slot, done, context=None):
        return ch.Disposition.accounting_fault("boundary_count: |C|=3, len(request_usage)=2, the evidence states 2")


def chain(tmp_path, **kw):
    c = bare(tmp_path, **kw)
    c.ops.reset_cache_session = lambda model: c.logged.append(f"reset {model}")
    c.ops.power_ok = lambda: True
    c.ops.busy_procs = lambda: []
    c.ops.descendants = lambda pid: []
    return c


def to_done(c, tmp_path, monkeypatch, bar):
    (tmp_path / "b.item0.ready").write_text("{}")
    hooks = c.hooks
    c.hooks = ch.ChainHooks()
    c.pump_barrier(bar)
    c.hooks = hooks
    (tmp_path / "b.item0.done").write_text(json.dumps({"id": "python/a"}))
    monkeypatch.setattr(core.cr, "read_rows", lambda p: [{"id": "python/a", "gate": {}}])
    c.web_record, c.web_rules = (lambda *a, **k: {}), (lambda arm: None)


# -------------------------------------------------------------------------------- §5.2 ready: rerun once, twice = DNF
def test_a_hook_infrastructure_fault_at_ready_reruns_the_item_once(tmp_path):
    c = chain(tmp_path)
    c.hooks = Broken()
    bar = barrier(tmp_path, c)
    (tmp_path / "b.item0.ready").write_text("{}")
    c.pump_barrier(bar)
    att, = c.progress["slot_attempts"]
    assert att["disposition"] == "harness_fault" and att["rerun_index"] == 0 and att["stage"] == "ready"
    assert json.loads((tmp_path / "b.item0.stop").read_text()) == {"disposition": "harness_fault"}
    assert c.p426_faults and c.p426_invalid == [] and c.p426_harness_dnf == []
    table = cr.load_slots(c.chain_doc(), tmp_path)
    assert table.pending_reruns == [(SLOT_A, 1)] and SLOT_A not in table.scored


def test_a_second_fault_on_the_rerun_is_a_harness_fault_dnf_and_the_leg_continues(tmp_path):
    c = chain(tmp_path)
    c.hooks = Broken()
    bar = barrier(tmp_path, c)
    bar["rindex"] = 1                                             # the rerun of the item
    (tmp_path / "b.item0.ready").write_text("{}")
    c.pump_barrier(bar)
    d, = c.p426_harness_dnf
    assert d["kind"] == "harness_fault_dnf" and d["slot"] == SLOT_A and ph.sealed_ok(d)
    assert c.p426_ledger == [dict(slot=SLOT_A, kind="dnf", dnf_kind="harness_fault_dnf", invocation="s1/o.jsonl", index=0)]
    side = json.loads((tmp_path / "items" / f"{cr.slot_file(SLOT_A)}.harness_dnf.json").read_text())
    assert side == d and c.p426_pending_hold is None              # under the cap: the leg continues
    table = cr.load_slots(c.chain_doc(), tmp_path)
    assert table.scored[SLOT_A].source == "harness_dnf" and table.scored[SLOT_A].strict_fail is True


def test_the_fourth_harness_dnf_persists_the_dnf_and_the_hold_episode_together_and_holds(tmp_path):
    c = chain(tmp_path)
    saved = []
    c.write_json = lambda status=None: saved.append((status, len(c.p426_harness_dnf), len(c.p426_holds)))
    c.p426_harness_dnf = [dict(slot=f"{BASE}|{x}", kind="grade_fault", reason="r", sha256="0" * 64) for x in "xyz"]
    rec = dict(file="s1/o.jsonl", load_gen=0)
    c.p426_harness_dnf_record(SLOT_A, "harness_fault_dnf", "second ready fault", rec, stage="ready", rindex=1)
    assert ("harness-dnf", 4, 1) in saved                         # one write: the 4th DNF AND the hold episode
    assert c.p426_pending_hold["kind"] == "paused" and "cap" in c.p426_pending_hold["reason"]
    assert (tmp_path / "PAUSED").exists()


def test_the_leg_loop_runs_the_rerun_step_with_its_rerun_index_after_the_cache_reset(tmp_path):
    c = chain(tmp_path)
    c.check_stop = lambda where: None
    c.progress["slot_attempts"].append(dict(slot=SLOT_A, rerun_index=0, disposition="harness_fault", reason="r",
                                            stage="ready", load_gen=0, invocation="s1/x.jsonl"))
    c.p426_faults.append(dict(slot=SLOT_A, rerun_index=0, stage="ready", reason="r"))
    calls = []

    def run_invocation(load, leg, step):
        calls.append((step["phase"], step.get("rerun_index"), list(step["expect"])))
        c.slot_table = lambda: SimpleNamespace(scored={SLOT_A: 1, f"{BASE}|b": 1}, pending_reruns=[], blocked=[])
        return "ok"
    c.run_invocation = run_invocation
    c.slot_table = lambda: cr.load_slots(c.chain_doc(), tmp_path)
    load = dict(rec=dict(cursor=None), worker=dict(core.Chain.__dict__ and {"pid": 1, "create_time": 10}), model="M")
    leg = dict(slot_base=BASE, lang="python", arm="A", model="M", session="s1", stem="M.s1.A_python", li=0,
               invocations=[dict(phase="pilot", names=["a", "b"], expect=["python/a", "python/b"])])
    assert c.run_p426_leg(load, leg) == "ok"
    assert calls[0] == ("rerun", 1, ["python/a"]) and "reset M" in c.logged


# -------------------------------------------------------------------------------- §5.3 done: accounting, never rerun
def test_a_count_mismatch_with_an_outcome_is_an_accounting_fault_outcome_kept_settled_and_continued(tmp_path, monkeypatch):
    c = chain(tmp_path)
    c.hooks = Accounting()
    bar = barrier(tmp_path, c)
    to_done(c, tmp_path, monkeypatch, bar)
    c.pump_barrier(bar)
    att, = c.progress["slot_attempts"]
    assert att["disposition"] == "accepted" and att["accounting_fault"] is True and att["rerun_index"] == 0
    assert c.p426_ledger[-1] == dict(slot=SLOT_A, kind="row", invocation="s1/o.jsonl", index=0, accounting_fault=True)
    assert (tmp_path / "b.item0.continue").exists() and c.p426_invalid == [] and c.p426_accounting[0]["slot"] == SLOT_A
    assert not any(a["disposition"] == "harness_fault" for a in c.progress["slot_attempts"])   # no rerun after an outcome


def test_an_accounting_fault_whose_settle_check_fails_is_paused_not_continued(tmp_path, monkeypatch):
    c = chain(tmp_path)
    c.ops.worker_metrics = lambda: {"summary": {"in_flight": 1}}
    c.hooks = Accounting()
    bar = barrier(tmp_path, c)
    to_done(c, tmp_path, monkeypatch, bar)
    c.pump_barrier(bar)
    assert not (tmp_path / "b.item0.continue").exists()
    assert json.loads((tmp_path / "b.item0.stop").read_text()) == {"disposition": "hold"}
    assert c.p426_pending_hold["kind"] == "paused" and "settle" in c.p426_pending_hold["reason"]


def test_a_done_hook_infrastructure_fault_is_an_accounting_fault_with_a_chain_sealed_sidecar(tmp_path, monkeypatch):
    c = chain(tmp_path)
    c.hooks = Broken()
    bar = barrier(tmp_path, c)
    to_done(c, tmp_path, monkeypatch, bar)
    c.pump_barrier(bar)
    side = json.loads((tmp_path / "items" / f"{cr.slot_file(SLOT_A)}.accounting.json").read_text())
    assert ph.sealed_ok(side) and side["failed_checks"][0].startswith("hook infrastructure error at done")
    assert (tmp_path / "b.item0.continue").exists() and c.progress["slot_attempts"][0]["accounting_fault"] is True


def test_a_done_hook_fault_whose_sidecar_cannot_be_written_pauses_the_leg(tmp_path, monkeypatch):
    c = chain(tmp_path)
    c.hooks = Broken()
    monkeypatch.setattr(ph, "write_accounting", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    bar = barrier(tmp_path, c)
    to_done(c, tmp_path, monkeypatch, bar)
    c.pump_barrier(bar)
    assert c.p426_pending_hold["kind"] == "paused" and "cannot be written" in c.p426_pending_hold["reason"]
    assert not (tmp_path / "b.item0.continue").exists() and (tmp_path / "PAUSED").exists()


def test_the_done_hook_returns_accounting_for_a_pairing_mismatch_and_invalidate_for_integrity(tmp_path):
    ops, hooks, out = R4.make_hooks(tmp_path)
    hooks.before_attempt(R4.SLOT, R4.ctx())
    ops.serve(*R4.req(prompt=100, gen=10, draft=R4.ON_DRAFT))
    d = hooks.after_attempt(R4.SLOT, dict(id="python/a"), R4.ctx(R4.row_of([(100, 11)])))
    assert d.kind == "accounting_fault"
    ops2, hooks2, out2 = R4.make_hooks(tmp_path / "x")
    hooks2.before_attempt(R4.SLOT, R4.ctx())
    ops2.serve(*R4.req(prompt=100, gen=10, draft=R4.ON_DRAFT), generated_tokens_total=999999)
    d2 = hooks2.after_attempt(R4.SLOT, dict(id="python/a"), R4.ctx(R4.row_of([(100, 10)])))
    assert d2.kind == "invalidate" and "worker_deltas" in d2.reason          # §5.5 / §5.9: an integrity fault


def test_the_done_hook_reads_the_rows_cleanup_status(tmp_path):
    """§3.6: `row.cleanup_status` (schema 2: foreign_new + killed escapees) is recorded by the done hook; a certain receipt with
    foreign processes never refuses, an uncertain one is an integrity problem."""
    ops, hooks, out = R4.make_hooks(tmp_path)
    hooks.before_attempt(R4.SLOT, R4.ctx())
    ops.serve(*R4.req(prompt=100, gen=10, draft=R4.ON_DRAFT))
    row = dict(R4.row_of([(100, 10)]), cleanup_status=dict(CLEAN2, foreign_new=[dict(pid=7)], foreign_new_count=1,
                                                           orphans_unattributed=[dict(pid=8, claim="session")]))
    assert hooks.after_attempt(R4.SLOT, dict(id="python/a"), R4.ctx(row)).kind == "accept"
    rec = json.loads((out / "items" / f"{R4.SLOT_FILE}.json").read_text())
    assert rec["checks"]["cleanup"]["ok"] is True and "foreign_new=1" in rec["checks"]["cleanup"]["detail"]
    ops2, hooks2, _ = R4.make_hooks(tmp_path / "u")
    hooks2.before_attempt(R4.SLOT, R4.ctx())
    ops2.serve(*R4.req(prompt=100, gen=10, draft=R4.ON_DRAFT))
    bad = dict(R4.row_of([(100, 10)]), cleanup_status=dict(CLEAN2, uncertain=True))
    assert hooks2.after_attempt(R4.SLOT, dict(id="python/a"), R4.ctx(bad)).kind == "invalidate"


def test_item_records_are_keyed_by_the_rerun_index(tmp_path):
    ops, hooks, out = R4.make_hooks(tmp_path)
    context = dict(R4.ctx(), rerun_index=1)
    assert hooks.before_attempt(R4.SLOT, context).kind == "accept"
    assert (out / "items" / f"{R4.SLOT_FILE}.r1.ready.json").exists()
    assert not (out / "items" / f"{R4.SLOT_FILE}.ready.json").exists()


# -------------------------------------------------------------------------------- §5.8 the abort route
def route(c, tmp_path, cause, stage, *, ids=("python/a",), scan=None, cleanup=CLEAN2):
    load, leg, inv, rec, att, _ = scenario(tmp_path, ids=ids, cleanup=cleanup)
    att["transport_abort"] = dict(cause=cause, stage=stage, outcome_present=stage == "done", error="boom",
                                  cleanup_status=cleanup)
    att["run_id"] = "20261120T000000-abcdefabcdef"
    c.partial_ids = lambda out: list(ids)
    c.validate_partial = lambda *a, **k: None
    c.after_invocation = lambda *a, **k: None
    c._manifest = lambda view: dict(probe_session=dict(sid=4242, leader=True, run_dir="$STACK_WORKDIR/opencode-probe-v2/run-x"))
    c.wd = tmp_path
    c.ops.owned_scan = scan or (lambda **k: dict(certain=True, killed=[dict(pid=9, create_time=1.0)], problems=[]))
    c.progress["invocations"].append(rec)
    return c.handle_incomplete(load, leg, inv, rec, att, ["rc"], sup=dict(state="exited"), view=leg), rec


def test_cleanup_uncertain_then_the_chain_scan_kills_and_verifies_then_the_item_reruns(tmp_path):
    c = chain(tmp_path)
    seen = []
    res, rec = route(c, tmp_path, "cleanup_uncertain", "final_grade",
                     scan=lambda **k: seen.append(k) or dict(certain=True, killed=[dict(pid=9, create_time=1.0)], problems=[]))
    assert res == "harness_fault" and rec["status"] == "partial_incident" and rec["accepted_slots"] == [SLOT_A]
    assert seen[0]["sid"] == 4242 and seen[0]["deadline_s"] == 60.0
    assert any(p.startswith("mlxbench-20261120T000000-abcdefabcdef-") for p in seen[0]["container_prefixes"])
    assert c.p426_faults[-1]["slot"] == f"{BASE}|b" and c.p426_pending_hold is None and c.p426_dnf == []


def test_cleanup_uncertain_that_the_chain_scan_cannot_prove_pauses_with_no_live_probe(tmp_path):
    c = chain(tmp_path)
    res, _ = route(c, tmp_path, "cleanup_uncertain", "generation",
                   scan=lambda **k: dict(certain=False, unverified=[dict(pid=9)], problems=[]))
    assert res == "paused" and c.p426_pending_hold["kind"] == "paused" and (tmp_path / "PAUSED").exists()
    assert c.p426_faults == [] and c.p426_harness_dnf == []
    assert list((tmp_path / "harness_faults").glob("*.json"))                  # the evidence is persisted


def test_a_grader_infrastructure_fault_after_the_in_probe_regrades_is_a_grade_fault_dnf(tmp_path):
    c = chain(tmp_path)
    res, _ = route(c, tmp_path, "grader_infra", "final_grade")
    assert res == "dnf" and c.p426_harness_dnf[-1]["kind"] == "grade_fault" and c.p426_harness_dnf[-1]["slot"] == f"{BASE}|b"


def test_an_interim_grader_fault_and_a_ready_hook_fault_are_pre_outcome_and_rerun(tmp_path):
    for cause, stage in (("grader_infra", "generation"), ("hook_infra", "ready")):
        c = chain(tmp_path / cause)
        res, _ = route(c, tmp_path / cause, cause, stage)
        assert res == "harness_fault" and c.p426_faults[-1]["stage"] == stage


def test_a_hook_fault_at_done_keeps_the_outcome_as_an_accounting_fault(tmp_path):
    c = chain(tmp_path)
    res, rec = route(c, tmp_path, "hook_infra", "done")
    assert res == "harness_fault" and rec["accepted_slots"] == [SLOT_A]
    assert c.p426_ledger[-1]["accounting_fault"] is True and c.p426_accounting[-1]["slot"] == SLOT_A


def test_a_harness_fault_with_an_uncertain_cleanup_receipt_pauses(tmp_path):
    c = chain(tmp_path)
    res, _ = route(c, tmp_path, "grader_infra", "generation", cleanup=dict(CLEAN2, uncertain=True))
    assert res == "paused"


def test_an_integrity_fault_still_invalidates_the_leg(tmp_path):
    c = chain(tmp_path, worker=dict(pid=2, create_time=10))       # the worker changed at the incident
    with pytest.raises(co.ChainAbort, match="identity"):
        route(c, tmp_path, "grader_infra", "generation")


# -------------------------------------------------------------------------------- §5.7 the ledger: both DNF lists
def test_the_harness_dnfs_pass_the_ledger_check_beside_a_transport_dnf(tmp_path):
    c = chain(tmp_path)
    leg = dict(slot_base=BASE, invocations=[dict(expect=["python/a", "python/b", "python/c"])])
    c.loads = [dict(legs=[leg])]
    c.per_arm = False
    c.p426_dnf = [dict(slot=f"{BASE}|b")]
    c.p426_harness_dnf = [dict(slot=f"{BASE}|c", kind="harness_fault_dnf", reason="r")]
    c.p426_faults = [dict(slot=f"{BASE}|a", rerun_index=0), dict(slot=f"{BASE}|c", rerun_index=0)]
    c.p426_ledger = [dict(slot=f"{BASE}|a", kind="row", rerun_index=1), dict(slot=f"{BASE}|b", kind="dnf"),
                     dict(slot=f"{BASE}|c", kind="dnf")]
    c.check_p426_ledger()
    c.p426_ledger[0] = dict(slot=f"{BASE}|a", kind="row")         # accepted at index 0 although it faulted: refused
    with pytest.raises(co.ChainAbort, match="rerun"):
        c.check_p426_ledger()


def test_the_p426_slot_table_bounds_and_flags():
    doc = dict(p426=True, progress=dict(loads=[], invocations=[], pre_spawn=[], slot_attempts=[
        dict(slot="s", rerun_index=2, disposition="accepted", load_gen=0)]))
    with pytest.raises(cr.ChainRowsError, match="exceeds"):
        cr.validate_progress(doc)
    doc["progress"]["slot_attempts"] = [dict(slot="s", rerun_index=0, disposition="cheat", load_gen=0)]
    with pytest.raises(cr.ChainRowsError, match="no cheat"):
        cr.validate_progress(doc)
    flat = dict(progress=dict(slot_attempts=[dict(slot="s", rerun_index=0, disposition="harness_fault", load_gen=0)]))
    with pytest.raises(cr.ChainRowsError, match="P426"):
        cr.validate_progress(flat)
    no_reason = dict(p426=True, progress=dict(slot_attempts=[dict(slot="s", rerun_index=0, disposition="harness_fault",
                                                                  load_gen=0)]))
    with pytest.raises(cr.ChainRowsError, match="reason"):
        cr.load_slots(no_reason, "/nonexistent-root")


def test_the_cheat_rerun_cap_of_per_arm_legs_is_unchanged():
    assert cr.MAX_RERUNS == 2 and cr.MAX_P426_RERUN_INDEX == 1


# -------------------------------------------------------------------------------- §8.2 the HOLD round trip
def test_the_pause_file_at_an_accepted_boundary_holds_and_the_release_resumes(tmp_path, monkeypatch):
    c = chain(tmp_path)
    pause = tmp_path / "PAUSE"
    pause.write_text("")
    c.pause_path = pause
    bar = barrier(tmp_path, c)
    to_done(c, tmp_path, monkeypatch, bar)
    c.pump_barrier(bar)
    assert json.loads((tmp_path / "b.item0.stop").read_text()) == {"disposition": "hold"}
    assert c.p426_ledger[-1]["slot"] == SLOT_A                     # the boundary item was accepted first
    ep = c.p426_pending_hold
    assert ep["kind"] == "hold" and ep["end"] is None
    c.stop_requested = lambda: False
    c.tm = SimpleNamespace(poll_s=0.0)
    c.ops.sleep = lambda s: pause.unlink()                         # the designer removes PAUSE
    c.p426_census = lambda where, load=None: c.logged.append(where)
    load = dict(model="M", worker=dict(pid=1, create_time=10))
    c.p426_wait_release(load)
    assert ep["end"] is not None and c.p426_pending_hold is None and "at resume" in c.logged


def test_a_stop_while_held_ends_the_chain_and_the_leg_stays_paused(tmp_path):
    c = chain(tmp_path)
    c.p426_open_hold("paused", "designer", write=False)
    c.stop_requested = lambda: True
    c.stop_info = {}
    with pytest.raises(core.Stopped):
        c.p426_wait_release(dict(model="M", worker=dict(pid=1, create_time=10)))
    doc = dict(p426_holds=c.p426_holds, p426_invalid=[], status="finished")
    (tmp_path / "chain.json").write_text(json.dumps(doc))
    assert w2.classify_leg(tmp_path, 3, arm="n16")["state"] == "PAUSED"


def test_the_outer_deadline_is_suspended_for_the_held_interval(tmp_path):
    (tmp_path / "chain.json").write_text(json.dumps(dict(p426_holds=[dict(start_t=100.0, end_t=400.0),
                                                                      dict(start_t=1000.0, end_t=None)])))
    assert w2.held_s(tmp_path, 1600.0) == 300.0 + 600.0
    assert w2.held_s(tmp_path / "missing", 5.0) == 0.0


def test_the_sequencer_forwards_its_pause_file_to_the_chain():
    import inspect
    assert '"--pause-file", str(self.pause)' in inspect.getsource(w2.Sequencer.run_leg)
    assert "held_s(root" in inspect.getsource(w2.Sequencer.supervise)
