"""S27 (spec v1.4, sections 5.2-5.8, 8.2, acceptance 10.1) -- blind test-writer, delivery 1: the chain side of harness faults.

Method-level, on the bare `Chain` of `test_b2_s3_core.bare` (no ops, no probe), through the chain's own entry points:
`pump_barrier` (the item barrier), `handle_incomplete` (the abort route), `check_realized` (the ledger), `record_layout` /
`load_record` (chain.json), `chain_rows.load_slots` (the slot table) and `Sequencer.supervise` (the outer deadline).

Class of each test: (a) reproduces a failure the spec fixes, (b) preserves an invariant, (c) exercises new behaviour.

Interface assumptions (the spec names the values, not every field; each guess is isolated in a helper below):
  C1  dispositions: `chain_hooks.Disposition(kind, reason=...)` with kinds `harness_fault`, `accounting_fault`, `hold`
      (spec 5.7); their `.stop` payload is `{"disposition": <kind>}`; a ready-stage hook infrastructure error is turned into
      `harness_fault` by the chain itself (the hook only raised `HookInfrastructureError`); at `done` it is `accounting_fault`;
  C2  `slot_attempts` records get `disposition: "harness_fault"` (and the rerun index of the attempt); the new DNF list is
      `chain.p426_harness_dnf` (spec 5.7), each record `{slot, kind, ...}` with `kind` in `harness_fault_dnf | grade_fault`,
      sealed sidecar `<out_root>/items/<slot_file>.harness_dnf.json`; the ledger entry kind is `dnf`;
  C3  the accounting sidecar of the chain (done-stage infrastructure error) is `<out_root>/items/<slot_file>.accounting.json`;
  C4  a hold / pause episode is recorded in any chain attribute (or `progress` key) whose name contains `hold` or `pause`,
      as a non-empty value; the chain's PAUSE file is `<out_root>/PAUSE` or `<out_root>/../PAUSE` (and `a.pause_file`);
  C5  the abort stamp's stage is `transport_abort["stage"]` in `ready | generation | final_grade | done` (spec 5.8);
  C6  the chain's second scan is the ops seam `ops.second_scan(**kw)` returning an object with `.certain` (bool) and `.evidence`
      (spec 5.8 names the inputs - probe session id, hermetic roots, container prefix, 60 s - not the call);
  C7  the outer deadline reads open / closed episodes from `<root>/chain.json["holds"]` = `[{start, end|None, reason}]` in the
      sequencer's clock (spec 8.2: 'reads the open episode and subtracts it').
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import chain_core as core
from bench import chain_hooks as ch
from bench import chain_ops as co
from bench import chain_rows as cr
from bench import p426_hooks as ph
from bench.tests.test_b2_s3_core import BASE, GOOD_CLEANUP, WORKER, bare as _bare, scenario

RUN_ID = "20261120T120000-aaaaaaaaaaaa"
SLOT_A = f"{BASE}|a"
SLOT_FILE_A = cr.slot_file(SLOT_A)
LEDGER_ROW = dict(kind="row", invocation="s1/o.jsonl")


def bare(tmp_path, **kw):
    c = _bare(tmp_path, **kw)
    # the new per-leg state (spec 5.7 / 8.2); `bare` builds the chain without `__init__`, and (v3, X14) a Chain no longer
    # defaults any attribute, so the test builds it properly
    c.p426_harness_dnf, c.p426_faults, c.p426_accounting, c.p426_holds = [], [], [], []
    c.p426_pending_hold, c.pause_path = None, None
    return c


class Broken(ch.ChainHooks):
    def __init__(self, ready=None, done=None):
        self.ready, self.done = ready, done

    def before_attempt(self, slot, context=None):
        if self.ready:
            raise ch.HookInfrastructureError(self.ready)
        return ch.Disposition.accept()

    def after_attempt(self, slot, done, context=None):
        if self.done is None:
            return ch.Disposition.accept()
        if isinstance(self.done, ch.Disposition):
            return self.done
        raise ch.HookInfrastructureError(self.done)


def barrier(tmp_path, c, *, rindex=0, names=("a",)):
    rec = dict(file="s1/o.jsonl", load_gen=0, manifest="m")
    view = dict(slot_base=BASE, lang="python", arm="A", model="M", session="s1", out=str(tmp_path / "o.jsonl"))
    load = dict(idx=0, rec=dict(load_gen=0), worker=dict(WORKER))
    inv = dict(names=list(names), expect=[f"python/{n}" for n in names], rerun_index=rindex)
    return c.new_barrier(rec, inv, tmp_path / "b", view, load)


def stop_of(tmp_path, k=0):
    p = tmp_path / f"b.item{k}.stop"
    return json.loads(p.read_text()) if p.exists() else None


def hold_state(c):
    found = {}
    for k, v in vars(c).items():
        if ("hold" in k.lower() or "pause" in k.lower()) and v:
            found[k] = v
    for k, v in (c.progress or {}).items():
        if ("hold" in k.lower() or "pause" in k.lower()) and v:
            found["progress." + k] = v
    return found


def at_ready(tmp_path, c, bar):
    (tmp_path / "b.item0.ready").write_text("{}")
    c.pump_barrier(bar)


def to_done(tmp_path, monkeypatch, c, bar):
    c.hooks = Broken()
    at_ready(tmp_path, c, bar)
    assert (tmp_path / "b.item0.go").exists()
    (tmp_path / "b.item0.done").write_text(json.dumps({"id": "python/a"}))
    monkeypatch.setattr(core.cr, "read_rows", lambda p: [{"id": "python/a", "gate": {}}])
    c.web_record, c.web_rules = (lambda *a, **k: {}), (lambda arm: None)


# ------------------------------------------------------------------------------------------------ vocabulary
@pytest.mark.parametrize("kind", ["harness_fault", "accounting_fault", "hold"])
def test_the_new_disposition_kinds_exist_and_are_after_kinds(kind):
    """(c) spec 5.7: `chain_hooks.KINDS` / `AFTER_KINDS` gain them."""
    assert kind in ch.KINDS and kind in ch.AFTER_KINDS
    d = ch.Disposition(kind, reason="why")
    assert d.kind == kind and ch.Disposition.from_dict(json.loads(json.dumps(d.as_dict()))) == d


@pytest.mark.parametrize("kind", ["harness_fault", "hold"])
def test_a_harness_fault_or_a_hold_stops_the_probe(kind):
    """(c)"""
    assert ch.Disposition(kind, reason="why").stops_probe


def test_the_slot_vocabulary_gains_harness_fault():
    """(c) `chain_rows.SLOT_DISPOSITIONS` and the hook-to-attempt mapping."""
    assert "harness_fault" in cr.SLOT_DISPOSITIONS
    assert ch.slot_disposition(ch.Disposition("harness_fault", reason="why")) == "harness_fault"


def test_the_slot_table_queues_the_same_item_once_more_after_a_harness_fault(tmp_path):
    """(a) The baseline refuses the record (`slot attempt record malformed`); the spec: `slot_table` queues `(slot, 1)`."""
    doc = dict(p426=True, progress=dict(slot_attempts=[dict(slot=SLOT_A, rerun_index=0, disposition="harness_fault", load_gen=0,
                                                            reason="hook infrastructure error: metrics_unreadable")]))
    table = cr.load_slots(doc, tmp_path)
    assert table.pending_reruns == [(SLOT_A, 1)]
    assert SLOT_A not in table.scored and SLOT_A not in table.blocked


def test_cheat_reruns_keep_their_own_budget_on_the_slot_table(tmp_path):
    """(b) a cheat still queues the next index and is bounded by MAX_RERUNS (P202): harness faults do not touch it."""
    doc = dict(progress=dict(slot_attempts=[dict(slot=SLOT_A, rerun_index=0, disposition="cheat", load_gen=0)]))
    assert cr.load_slots(doc, tmp_path).pending_reruns == [(SLOT_A, 1)]
    doc = dict(progress=dict(slot_attempts=[dict(slot=SLOT_A, rerun_index=cr.MAX_RERUNS, disposition="cheat", load_gen=0)]))
    with pytest.raises(cr.ChainRowsError):
        cr.load_slots(doc, tmp_path)


# ------------------------------------------------------------------------------------------------ a ready-stage fault (5.2)
def test_a_hook_infrastructure_error_at_ready_reruns_the_same_item_once_and_never_invalidates(tmp_path):
    """(a) The baseline invalidates the leg (`p426_invalidate`). The spec: `harness_fault`, persisted before the `.stop`."""
    c = bare(tmp_path)
    c.hooks = Broken(ready="metrics_unreadable")
    bar = barrier(tmp_path, c)
    order = []
    c.write_json = lambda status=None: order.append((status, (tmp_path / "b.item0.stop").exists()))
    at_ready(tmp_path, c, bar)
    assert c.p426_invalid == [] and c.progress["pre_spawn"] == [] and c.incidents == []
    assert stop_of(tmp_path) == {"disposition": "harness_fault"}
    assert bar["stage"] == "stopped" and bar["stop"]["disposition"] == "harness_fault" and bar["stop"]["kind"] == "before"
    attempts = [a for a in c.progress["slot_attempts"] if a["slot"] == SLOT_A]
    assert [(a["rerun_index"], a["disposition"]) for a in attempts] == [(0, "harness_fault")]
    assert order and all(not stopped for _, stopped in order), "persisted BEFORE the .stop"
    assert c.p426_harness_dnf == [] and c.p426_ledger == []


def test_the_second_ready_fault_of_the_same_item_is_a_harness_fault_dnf_and_the_leg_continues(tmp_path):
    """(a) 1 rerun per item; a second pre-outcome fault is a recorded `harness_fault_dnf` (strict fail), never INVALID."""
    c = bare(tmp_path)
    c.hooks = Broken(ready="metrics_unreadable")
    bar = barrier(tmp_path, c, rindex=1)
    at_ready(tmp_path, c, bar)
    assert c.p426_invalid == []
    (d,) = c.p426_harness_dnf
    assert d["slot"] == SLOT_A and d["kind"] == "harness_fault_dnf"
    assert [(e["slot"], e["kind"]) for e in c.p426_ledger] == [(SLOT_A, "dnf")]       # v2: intent; extra keys are the candidate's
    assert c.p426_dnf == []                                      # separate from the transport DNFs


def test_the_harness_dnf_is_a_sealed_exclusive_sidecar_beside_the_item_records(tmp_path):
    """(c) spec 5.7: `items/<slot>.harness_dnf.json`, immutable like the other item records."""
    c = bare(tmp_path)
    c.hooks = Broken(ready="metrics_unreadable")
    at_ready(tmp_path, c, barrier(tmp_path, c, rindex=1))
    side = tmp_path / "items" / f"{SLOT_FILE_A}.harness_dnf.json"
    doc = json.loads(side.read_text())
    assert ph.sealed_ok(doc) and doc["slot"] == SLOT_A


def test_p426_accounted_counts_a_harness_dnf_slot_as_done_so_the_leg_moves_on(tmp_path):
    """(a) `run_p426_leg` derives the unaccounted slots from the slot table: a harness DNF must be a scored strict fail there
    (v2: through the real `chain_rows` table, not a stub)."""
    doc = dict(p426=True, progress=dict(slot_attempts=[
        dict(slot=SLOT_A, rerun_index=0, disposition="harness_fault", load_gen=0, reason="hook infrastructure error: x")]),
        p426_harness_dnf=[dict(slot=SLOT_A, kind="harness_fault_dnf", reason="hook infrastructure error: x", rerun_index=1)])
    table = cr.load_slots(doc, tmp_path)
    assert SLOT_A in table.scored and table.scored[SLOT_A].strict_fail is True
    assert table.pending_reruns == []


# ------------------------------------------------------------------------------------------------ the ledger and chain.json (5.7)
def _ledger_chain(tmp_path):
    c = bare(tmp_path)
    leg = dict(slot_base=BASE, lang="python", arm="A", model="M", session="s1", stem="M.s1.A_python", li=0, pos=0,
               realized_key=[0, "python"],
               invocations=[dict(phase="pilot", names=["a", "b", "c"], expect=["python/a", "python/b", "python/c"])])
    c.loads, c.realized = [dict(legs=[leg])], [[0, "python"]]
    return c


def _entry(n, kind="row"):
    return dict(slot=f"{BASE}|{n}", kind=kind, invocation="i", index=0)


def test_harness_dnfs_pass_the_ledger_check_beside_a_transport_dnf(tmp_path):
    """(a) 'the harness DNFs live in `p426_harness_dnf` and pass the ledger check beside a transport DNF'."""
    c = _ledger_chain(tmp_path)
    c.p426_dnf = [dict(slot=f"{BASE}|b")]
    c.p426_harness_dnf = [dict(slot=f"{BASE}|c", kind="grade_fault")]
    c.p426_ledger = [_entry("a"), _entry("b", "dnf"), _entry("c", "dnf")]
    c.check_realized()


def test_a_ledger_dnf_that_is_in_neither_list_is_still_refused(tmp_path):
    """(b) the ledger / DNF equality is not weakened."""
    c = _ledger_chain(tmp_path)
    c.p426_dnf = [dict(slot=f"{BASE}|b")]
    c.p426_ledger = [_entry("a"), _entry("b", "dnf"), _entry("c", "dnf")]
    with pytest.raises(co.ChainAbort, match="ledger"):
        c.check_realized()
    c.p426_dnf, c.p426_harness_dnf = [], [dict(slot=f"{BASE}|c", kind="grade_fault"), dict(slot=f"{BASE}|a", kind="grade_fault")]
    with pytest.raises(co.ChainAbort, match="ledger"):
        c.check_realized()


def test_chain_json_carries_and_restores_the_harness_dnf_list(tmp_path):
    """(c)"""
    c = bare(tmp_path)
    c.expected_policy, c.pinned, c.schedule_sha, c.probe = "p", {}, "s", Path("probe.py")
    c.p426_harness_dnf = [dict(slot="x", kind="grade_fault")]
    assert c.record_layout()["p426_harness_dnf"] == [dict(slot="x", kind="grade_fault")]
    prev = dict(progress=dict(loads=[], invocations=[]), snapshots={}, epoch_id=None, pinned={}, schedule_sha256="s",
                realized=[], p426_dnf=[], p426_ledger=[], p426_harness_dnf=[dict(slot="y", kind="grade_fault")])
    d = bare(tmp_path)
    d.attempt_no = {}
    d.load_record(prev)
    assert d.p426_harness_dnf == [dict(slot="y", kind="grade_fault")]
    old = dict(prev)
    old.pop("p426_harness_dnf")
    e = bare(tmp_path)
    e.attempt_no = {}
    e.load_record(old)                                           # a chain.json of an older identity has no such key
    assert e.p426_harness_dnf == []


def test_the_fourth_harness_dnf_of_a_leg_holds_atomically(tmp_path):
    """(a) cap 3 per leg, enforced at the item barrier before `.continue`: the 4th persists the DNF and the hold episode in ONE
    chain.json write, then holds (`.stop` disposition `hold`)."""
    c = bare(tmp_path)
    c.p426_harness_dnf = [dict(slot=f"{BASE}|{n}", kind="harness_fault_dnf") for n in "xyz"]
    c.hooks = Broken(ready="metrics_unreadable")
    bar = barrier(tmp_path, c, rindex=1)
    snaps = []
    c.write_json = lambda status=None: snaps.append((len(c.p426_harness_dnf), bool(hold_state(c)), (tmp_path / "b.item0.stop").exists()))
    at_ready(tmp_path, c, bar)
    assert len(c.p426_harness_dnf) == 4
    assert stop_of(tmp_path) is not None and bar["stage"] == "stopped"     # v2: the probe is stopped and the chain holds
    assert hold_state(c), "the leg is held / paused until the designer's release"
    assert any(n == 4 and held and not stopped for n, held, stopped in snaps), snaps
    assert not any(n == 4 and not held for n, held, _ in snaps), "the 4th DNF is never persisted without its hold episode"
    assert c.p426_invalid == []


def test_the_third_harness_dnf_does_not_hold(tmp_path):
    """(b) 'per leg <= 3'."""
    c = bare(tmp_path)
    c.p426_harness_dnf = [dict(slot=f"{BASE}|{n}", kind="harness_fault_dnf") for n in "xy"]
    c.hooks = Broken(ready="metrics_unreadable")
    at_ready(tmp_path, c, barrier(tmp_path, c, rindex=1))
    assert len(c.p426_harness_dnf) == 3 and not hold_state(c)
    assert stop_of(tmp_path) != {"disposition": "hold"}


# ------------------------------------------------------------------------------------------------ a done-stage fault (5.3)
def test_a_done_hook_infrastructure_error_is_an_accounting_fault_with_a_sidecar_and_the_leg_goes_on(tmp_path, monkeypatch):
    """(a) The baseline invalidates. The spec: the row exists, so the outcome is kept, the sidecar persisted, no rerun."""
    c = bare(tmp_path)
    bar = barrier(tmp_path, c)
    to_done(tmp_path, monkeypatch, c, bar)
    c.hooks = Broken(done="record_write_failed")
    c.pump_barrier(bar)
    assert c.p426_invalid == [] and stop_of(tmp_path) is None
    assert (tmp_path / "b.item0.continue").exists()
    side = json.loads((tmp_path / "items" / f"{SLOT_FILE_A}.accounting.json").read_text())
    assert ph.sealed_ok(side) and side["slot"] == SLOT_A
    assert [(e["slot"], e["kind"]) for e in c.p426_ledger] == [(SLOT_A, "row")]
    assert not [a for a in c.progress["slot_attempts"] if a["disposition"] in ("harness_fault", "cheat")]


def test_a_done_hook_infrastructure_error_with_an_unwritable_sidecar_pauses_the_leg(tmp_path, monkeypatch):
    """(a) 'if it cannot [be persisted], the leg is PAUSED': no `.continue`, no INVALID, a recorded pause."""
    c = bare(tmp_path)
    bar = barrier(tmp_path, c)
    to_done(tmp_path, monkeypatch, c, bar)
    (tmp_path / "items").write_text("a file where the items directory must be")
    c.hooks = Broken(done="record_write_failed")
    c.pump_barrier(bar)
    assert not (tmp_path / "b.item0.continue").exists()
    assert c.p426_invalid == []
    assert hold_state(c) or stop_of(tmp_path) == {"disposition": "hold"}


def test_a_done_hook_infrastructure_error_with_a_read_only_items_dir_pauses_the_leg(tmp_path, monkeypatch):
    """(a) v2 sibling of the test above, same intent with an unwritable (not file-shadowed) items directory."""
    import os
    c = bare(tmp_path)
    bar = barrier(tmp_path, c)
    to_done(tmp_path, monkeypatch, c, bar)
    items = tmp_path / "items"
    items.mkdir()
    items.chmod(0o555)
    try:
        c.hooks = Broken(done="record_write_failed")
        c.pump_barrier(bar)
    finally:
        items.chmod(0o755)
    assert not (tmp_path / "b.item0.continue").exists() and c.p426_invalid == []
    assert hold_state(c) or stop_of(tmp_path) == {"disposition": "hold"}


def test_an_accounting_fault_disposition_keeps_the_outcome_and_continues(tmp_path, monkeypatch):
    """(a) The done hook's `accounting_fault`: the item is ledgered as an accepted row and the probe is answered `.continue`."""
    c = bare(tmp_path)
    bar = barrier(tmp_path, c)
    to_done(tmp_path, monkeypatch, c, bar)
    c.hooks = Broken(done=ch.Disposition("accounting_fault", reason="boundary_count"))
    c.pump_barrier(bar)
    assert (tmp_path / "b.item0.continue").exists() and stop_of(tmp_path) is None
    assert c.p426_invalid == [] and [(e["slot"], e["kind"]) for e in c.p426_ledger] == [(SLOT_A, "row")]
    (att,) = [a for a in c.progress["slot_attempts"] if a["slot"] == SLOT_A]
    assert att["disposition"] == "accepted" and att["rerun_index"] == 0


def test_an_accounting_fault_with_a_worker_that_does_not_settle_holds_instead_of_continuing(tmp_path, monkeypatch):
    """(a) 5.3: 'continues after the settle check (worker in_flight == 0, same identity, :8000 owner); a failed settle ->
    integrity, HOLD'."""
    c = bare(tmp_path)
    c.ops.worker_metrics = lambda: {"summary": {"in_flight": 1}}
    bar = barrier(tmp_path, c)
    to_done(tmp_path, monkeypatch, c, bar)
    c.hooks = Broken(done=ch.Disposition("accounting_fault", reason="boundary_count"))
    c.pump_barrier(bar)
    assert not (tmp_path / "b.item0.continue").exists()
    assert stop_of(tmp_path) is not None or hold_state(c)


def test_an_accounting_fault_with_a_changed_worker_identity_is_not_continued(tmp_path, monkeypatch):
    """(b) integrity faults (worker identity drift) still invalidate or hold: never a silent continue."""
    c = bare(tmp_path)
    c.ops.worker_ident = lambda model: dict(pid=99, create_time=1)
    bar = barrier(tmp_path, c)
    to_done(tmp_path, monkeypatch, c, bar)
    c.hooks = Broken(done=ch.Disposition("accounting_fault", reason="boundary_count"))
    c.pump_barrier(bar)
    assert not (tmp_path / "b.item0.continue").exists()


def test_an_integrity_invalidate_at_done_is_still_leg_invalid_after_an_earlier_harness_fault(tmp_path, monkeypatch):
    """(b) 'an integrity fault -> leg INVALID': a rerun attempt that then fails an integrity check does not become a DNF."""
    c = bare(tmp_path)
    bar = barrier(tmp_path, c, rindex=1)
    to_done(tmp_path, monkeypatch, c, bar)
    c.hooks = Broken(done=ch.Disposition.invalidate("worker_deltas: the counters disagree"))
    c.pump_barrier(bar)
    assert c.p426_invalid and c.p426_invalid[0]["stage"] == "done"
    assert stop_of(tmp_path) == {"disposition": "invalidate"} and c.p426_harness_dnf == []
    assert not (tmp_path / "b.item0.continue").exists()


# ------------------------------------------------------------------------------------------------ the abort route (5.8)
def route(c, tmp_path, *, cause, stage, cleanup=GOOD_CLEANUP, ids=("python/a",)):
    load, leg, inv, rec, att, ids = scenario(tmp_path, cause=cause, ids=ids, cleanup=cleanup)
    att["transport_abort"]["stage"] = stage
    att["transport_abort"]["cleanup_status"] = cleanup          # v2: the probe's stamp carries its receipt (arm_runner)
    att["run_id"] = RUN_ID
    c.wd = tmp_path
    c._manifest = lambda view: dict(run_id=RUN_ID, probe_session=dict(sid=61000, leader=True, run_dir="$STACK_WORKDIR/run"))
    c.partial_ids = lambda out: ids
    c.validate_partial = lambda *a, **k: None
    c.after_invocation = lambda *a, **k: None
    c.progress["invocations"].append(rec)
    try:
        return "returned", c.handle_incomplete(load, leg, inv, rec, att, ["rc"], sup=dict(state="exited"), view=leg)
    except co.ChainAbort as exc:
        return "aborted", str(exc)
    except Exception as exc:  # noqa: BLE001  (a typed pause exception, whatever its name)
        return "raised", f"{type(exc).__name__}: {exc}"


def paused(result, c):
    kind, value = result
    return "paus" in str(value).lower() or bool(hold_state(c))


@pytest.mark.parametrize("stage", ["ready", "generation"])
@pytest.mark.parametrize("cause", ["grader_infra", "hook_infra"])
def test_a_typed_pre_outcome_abort_is_a_harness_fault_rerun_not_a_systemic_stop(tmp_path, cause, stage):
    """(a) routed BEFORE the DNF-cause check: the baseline aborts with 'an abort without a DNF cause is systemic'."""
    c = bare(tmp_path)
    result = route(c, tmp_path, cause=cause, stage=stage)
    assert result[0] == "returned", result
    attempts = [a for a in c.progress["slot_attempts"] if a["slot"] == f"{BASE}|b"]
    assert [(a["rerun_index"], a["disposition"]) for a in attempts] == [(0, "harness_fault")]
    assert c.p426_harness_dnf == [] and c.p426_dnf == []


def test_a_final_grade_infrastructure_abort_is_the_grade_fault_dnf_and_the_leg_continues(tmp_path):
    """(a) the in-probe regrades are exhausted: `grade_fault` (strict fail, tokens kept), counted under the cap, leg continues."""
    c = bare(tmp_path)
    result = route(c, tmp_path, cause="grader_infra", stage="final_grade")
    assert result[0] == "returned", result
    (d,) = c.p426_harness_dnf
    assert d["slot"] == f"{BASE}|b" and d["kind"] == "grade_fault" and c.p426_dnf == []
    assert [e["kind"] for e in c.p426_ledger] == ["dnf"]


def test_the_transport_dnf_causes_still_route_to_the_transport_dnf_list(tmp_path):
    """(b) an ordinary timeout stays a `p426_dnf` (MAX_P426_DNF's list), separate from the harness DNFs."""
    c = bare(tmp_path)
    result = route(c, tmp_path, cause="timeout", stage="generation")
    assert result == ("returned", "dnf") and len(c.p426_dnf) == 1 and c.p426_harness_dnf == []


def test_an_uncertain_cleanup_abort_runs_the_chains_second_scan_and_reruns_when_it_proves_certain(tmp_path):
    """(a) the CHAIN scans (probe session id, hermetic roots, container prefix; deadline 60 s), then requires worker
    in_flight == 0 and an unchanged identity -> `harness_fault` rerun."""
    c = bare(tmp_path)
    seen = []

    def second_scan(**kw):
        seen.append(kw)
        return dict(certain=True, killed=[dict(pid=4242, create_time=1.0)], problems=[])
    c.ops.owned_scan = second_scan                              # v2: the candidate's seam (`chain_ops.owned_scan`)
    result = route(c, tmp_path, cause="cleanup_uncertain", stage="generation",
                   cleanup=dict(GOOD_CLEANUP, uncertain=True, survivors=[4242]))
    assert seen, "the chain must run the second scan itself"
    assert result[0] == "returned", result
    assert [a["disposition"] for a in c.progress["slot_attempts"] if a["slot"] == f"{BASE}|b"] == ["harness_fault"]
    assert not paused(result, c)


def test_an_uncertain_cleanup_that_stays_uncertain_pauses_the_leg_and_never_reruns(tmp_path):
    """(a) 5.4: never continues on a possibly live owned process."""
    c = bare(tmp_path)
    c.ops.owned_scan = lambda **kw: dict(certain=False, killed=[], problems=["pid 4242: an owned process could not be killed"])
    result = route(c, tmp_path, cause="cleanup_uncertain", stage="generation",
                   cleanup=dict(GOOD_CLEANUP, uncertain=True, survivors=[4242]))
    assert paused(result, c), result
    assert not [a for a in c.progress["slot_attempts"] if a["disposition"] == "harness_fault"]
    assert c.p426_harness_dnf == [] and c.p426_dnf == []


@pytest.mark.parametrize("what, patch", [
    ("the worker still shows a request in flight", lambda c: setattr(c.ops, "worker_metrics", lambda: {"summary": {"in_flight": 1}})),
    ("the worker identity changed", lambda c: setattr(c.ops, "worker_ident", lambda model: dict(pid=9, create_time=1))),
])
def test_a_certain_second_scan_is_not_enough_without_a_settled_unchanged_worker(tmp_path, what, patch):
    """(b) 'then requires worker in_flight == 0 and an unchanged identity' (identity drift is an integrity fault)."""
    c = bare(tmp_path)
    c.ops.owned_scan = lambda **kw: dict(certain=True, killed=[], problems=[])
    patch(c)
    result = route(c, tmp_path, cause="cleanup_uncertain", stage="generation",
                   cleanup=dict(GOOD_CLEANUP, uncertain=True, survivors=[4242]))
    assert not [a for a in c.progress["slot_attempts"] if a["disposition"] == "harness_fault"], what


def test_the_pause_needs_no_live_probe(tmp_path):
    """(c) 'resumes only on the designer's release (no live probe is needed for a pause)': pausing never calls the probe path."""
    c = bare(tmp_path)
    c.ops.owned_scan = lambda **kw: dict(certain=False, killed=[], problems=["unverified"])
    c.ops.launch = lambda *a, **k: pytest.fail("a paused leg launches nothing")
    result = route(c, tmp_path, cause="cleanup_uncertain", stage="generation",
                   cleanup=dict(GOOD_CLEANUP, uncertain=True, survivors=[4242]))
    assert paused(result, c)


# ------------------------------------------------------------------------------------------------ HOLD (8.2)
def test_a_hold_at_an_accepted_done_withholds_the_continue_and_records_the_episode(tmp_path, monkeypatch):
    """(a) 'Hold = the existing PAUSE file, extended to item boundaries: checked at each accepted done (before `.continue`),
    writes `.stop` disposition hold, records the episode (start, end, reason), waits'."""
    c = bare(tmp_path)
    c.out_root = tmp_path / "leg"                               # the chain's root; its parent is the sequencer's out dir
    c.out_root.mkdir()
    c.a = SimpleNamespace(predictor="off", pause_file=str(tmp_path / "PAUSE"))
    c.pause_path = tmp_path / "PAUSE"                           # v2: the candidate's attribute (`--pause-file`)
    bar = barrier(tmp_path, c)
    to_done(tmp_path, monkeypatch, c, bar)
    c.pause_path.write_text("")
    c.pump_barrier(bar)
    assert stop_of(tmp_path) == {"disposition": "hold"}
    assert not (tmp_path / "b.item0.continue").exists()
    assert [(e["slot"], e["kind"]) for e in c.p426_ledger] == [(SLOT_A, "row")], "the accepted item is ledgered first"
    (episode,) = c.p426_holds
    assert episode["kind"] == "hold" and episode.get("end") is None, "the hold episode is open until the release"


def test_without_a_pause_file_an_accepted_done_continues_as_before(tmp_path, monkeypatch):
    """(b)"""
    c = bare(tmp_path)
    bar = barrier(tmp_path, c)
    to_done(tmp_path, monkeypatch, c, bar)
    c.pump_barrier(bar)
    assert (tmp_path / "b.item0.continue").exists() and stop_of(tmp_path) is None and not hold_state(c)


def _supervise(tmp_path, holds, *, polls, deadline=100.0):
    """`Sequencer.supervise` over a fake chain that stays alive for `polls` poll intervals; returns (overrun flag, OVERRUN file)."""
    from bench import p426_wave2 as W2
    t0 = 1_800_000_000.0
    clock = SimpleNamespace(t=t0)
    seq = W2.Sequencer.__new__(W2.Sequencer)
    seq.clock = lambda: clock.t
    seq.sleep = lambda s: setattr(clock, "t", clock.t + s)
    seq.out, seq.log = tmp_path, lambda msg: None
    seq.deadline = lambda spec: deadline
    seq.start_watcher = lambda spec, root, handle: SimpleNamespace(pid=2, start=2.0)
    left = {"n": polls}

    def alive(pid, start):
        if pid == 2:
            return True
        left["n"] -= 1
        return left["n"] >= 0
    seq.ops = SimpleNamespace(alive=alive, wait=lambda handle: 0)
    root = tmp_path / "leg.a1"
    root.mkdir()
    (root / "chain.json").write_text(json.dumps(dict(p426_holds=[
        dict(kind="hold", reason=h["reason"], start_t=t0 + h["start"], end_t=None if h["end"] is None else t0 + h["end"])
        for h in holds])))                                  # v2: the candidate's episode record (`start_t` / `end_t`)
    rc, started, watcher, watcher_dead, overrun = seq.supervise(dict(name="leg"), 1, root, SimpleNamespace(pid=1, start=1.0))
    return overrun, (tmp_path / W2.OVERRUN_FILE).exists()


def test_the_outer_deadline_is_suspended_for_a_closed_hold_episode(tmp_path):
    """(a) spec 8.2: the leg's deadline is suspended for the held interval in `Sequencer.supervise` (C7). 150 s of wall time, 90
    of them held, against a 100 s deadline: no overrun."""
    from bench import p426_wave2 as W2
    polls = int(150 / W2.POLL_S)
    overrun, written = _supervise(tmp_path, [dict(start=20.0, end=110.0, reason="operator")], polls=polls)
    assert overrun is False and not written


def test_the_outer_deadline_is_suspended_while_an_episode_is_still_open(tmp_path):
    """(a) the open episode is read and subtracted up to now."""
    from bench import p426_wave2 as W2
    polls = int(150 / W2.POLL_S)
    overrun, written = _supervise(tmp_path, [dict(start=20.0, end=None, reason="operator")], polls=polls)
    assert overrun is False and not written


def test_the_outer_deadline_still_fires_without_a_hold(tmp_path):
    """(b) the same 150 s with no episode overruns a 100 s deadline: the suspension is not a loosening of the bound."""
    from bench import p426_wave2 as W2
    polls = int(150 / W2.POLL_S)
    overrun, written = _supervise(tmp_path, [], polls=polls)
    assert overrun is True and written
