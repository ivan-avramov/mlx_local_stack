"""B2 slice s3 (spec v3.1 sections 2, 3, 5.1-5.3, 7): the chain-core P426 mechanics, tested at method level."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import chain_core as core
from bench import chain_hooks as ch
from bench import chain_incident as ci
from bench import chain_ops as co
from bench import run_config as rc


# -- chain_hooks: `invalidate`
def test_invalidate_is_a_disposition_kind_for_both_barriers_and_round_trips():
    d = ch.Disposition.invalidate("registry sha drifted")
    assert d.kind == "invalidate" and d.reason == "registry sha drifted" and d.stops_probe
    assert "invalidate" in ch.KINDS and "invalidate" in ch.BEFORE_KINDS and "invalidate" in ch.AFTER_KINDS
    assert ch.Disposition.from_dict(d.as_dict()) == d
    with pytest.raises(ValueError):
        ch.Disposition("invalidate")                         # a reason is required


def test_hooks_get_a_context_only_when_the_chain_passes_one_and_legacy_hooks_are_unchanged():
    class Legacy(ch.ChainHooks):
        def before_attempt(self, slot):
            return ch.Disposition.accept()

        def after_attempt(self, slot, done):
            return ch.Disposition.accept()

    assert Legacy().run_before("s").kind == "accept" and Legacy().run_after("s", {}).kind == "accept"

    seen = []

    class New(ch.ChainHooks):
        def before_attempt(self, slot, context=None):
            seen.append(("before", slot, context))
            return ch.Disposition.invalidate("ready check failed")

        def after_attempt(self, slot, done, context=None):
            seen.append(("after", slot, context))
            return ch.Disposition.invalidate("done check failed")

    assert New().run_before("s", context={"ready": 1}).kind == "invalidate"
    assert New().run_after("s", {"id": "x"}, context={"row": 2}).kind == "invalidate"
    assert seen == [("before", "s", {"ready": 1}), ("after", "s", {"row": 2})]


def test_a_hook_infrastructure_error_is_a_pre_spawn_incident_by_default_and_raised_when_systemic():
    class Broken(ch.ChainHooks):
        def before_attempt(self, slot, context=None):
            raise ch.HookInfrastructureError("metrics_unreadable")

    assert Broken().run_before("s").kind == "pre_spawn_incident"
    with pytest.raises(ch.HookInfrastructureError):
        Broken().run_before("s", context={}, systemic=True)


# -- run_config / chain_incident
def test_p426_continue_is_a_transport_policy_and_the_p426_config_may_use_it():
    assert "p426_continue" in rc.TRANSPORT_POLICIES
    assert ci.P426_DNF_CAUSES == ("connection", "dropped_stream", "timeout", "client_timeout")


def test_the_p426_dnf_cause_needs_a_stamp_cause_in_the_dnf_set_and_unchanged_identities():
    f = ci.classify_p426_dnf_cause
    assert f(stamp_cause="timeout", worker_ok=True, router_ok=True) == "timeout"
    assert f(stamp_cause="connection", worker_ok=False, router_ok=True) is None       # changed worker: systemic
    assert f(stamp_cause="connection", worker_ok=True, router_ok=False) is None
    assert f(stamp_cause="server_error", worker_ok=True, router_ok=True) is None      # not a DNF cause
    assert f(stamp_cause=None, worker_ok=True, router_ok=True) is None                # an abort without a cause
    assert f(stamp_cause="worker_crash", worker_ok=True, router_ok=True) is None


# -- chain_core: a bare Chain (no ops, no probe) driven at method level
BASE = "E|A|M|s1|python"
GOOD_CLEANUP = dict(survivors=[], containers_remaining=[], uncertain=False, orphans_unattributed=[], unknown=[],
                    completed=True)
WORKER = dict(pid=1, create_time=10)


def bare(tmp_path, policy="p426_continue", worker=WORKER, router_ok=True):
    c = core.Chain.__new__(core.Chain)
    c.config = SimpleNamespace(transport_policy=policy,
                               config_id=rc.P426_CONFIG_ID if policy == "p426_continue" else "tg1")
    c.builder, c.per_arm = "tg1", False
    c.a = SimpleNamespace(predictor="off")                  # the leg's predictor arm (`p426_dnf.arm` is `off` / `on`, spec 16.8)
    c.progress = dict(loads=[], invocations=[], slot_attempts=[], pre_spawn=[], txns=[], abort_evidence=[])
    c.incidents, c.dnf, c.realized, c.p426_dnf, c.p426_ledger, c.p426_invalid = [], [], [], [], [], []
    c.hooks = ch.ChainHooks()
    c.out_root = tmp_path
    c.saved, c.logged = [], []
    c.log = c.logged.append
    c.write_json = lambda status=None: c.saved.append(status)
    c.p426_router = dict(pid=1, start=5.0)                  # the owned router's identity `(pid, create_time(pid))`
    c.ops = SimpleNamespace(worker_ident=lambda model: dict(worker) if worker else None,
                            create_time=lambda pid: 5.0 if router_ok else 6.0,
                            worker_metrics=lambda: {"summary": {"in_flight": 0}})
    c.listing = lambda *a, **k: None
    c.loads = []
    return c


def scenario(tmp_path, *, cause="timeout", ids=("python/a",), cleanup=GOOD_CLEANUP):
    expect = ["python/a", "python/b", "python/c"]
    load = dict(worker=dict(WORKER), idx=0, rec=dict(load_gen=0), session="s1", model="M")
    leg = dict(slot_base=BASE, lang="python", arm="A", label="x", model="M", session="s1", seed_base=1001,
               out=str(tmp_path / "o.jsonl"), stem="M.s1.A_python", li=0)
    inv = dict(phase="pilot", expect=expect, names=["a", "b", "c"])
    rec = dict(slot_base=BASE, manifest="s1/o.manifest.json", file="s1/o.jsonl", status="running", accepted_slots=[],
               expected_slots=[f"{BASE}|{n}" for n in "abc"], load_gen=0)
    att = dict(attempt=1, log="l", cleanup_status=cleanup, worker_full=dict(WORKER),
               transport_abort=dict(cause=cause, error="boom"),
               abort_evidence=dict(evidence=[dict(path="x.json", sha256="0" * 64)]))
    return load, leg, inv, rec, att, list(ids)


def incomplete(c, tmp_path, **kw):
    load, leg, inv, rec, att, ids = scenario(tmp_path, **kw)
    c.partial_ids = lambda out: ids
    c.validate_partial = lambda *a, **k: None
    c.after_invocation = lambda *a, **k: None
    c.progress["invocations"].append(rec)                    # `register_invocation` does this before the probe starts
    return c.handle_incomplete(load, leg, inv, rec, att, ["rc"], sup=dict(state="exited"), view=leg), rec


def test_a_dnf_class_abort_writes_the_p426_dnf_record_chain_json_first_then_the_sidecar(tmp_path):
    c = bare(tmp_path)
    order = []
    c.write_json = lambda status=None: order.append((status, any(tmp_path.rglob("*.json"))))
    out, rec = incomplete(c, tmp_path)
    assert out == "dnf" and rec["status"] == "partial_incident" and rec["accepted_slots"] == [f"{BASE}|a"]
    d, = c.p426_dnf
    assert d["slot"] == f"{BASE}|b" and d["item"] == "b" and d["session"] == "s1" and d["language"] == "python"
    assert d["seed"] == 1001 and d["arm"] == "off" and d["abort"]["cause"] == "timeout"
    assert d["abort"]["evidence"] == [dict(path="x.json", sha256="0" * 64)]
    assert d["owned_at_incident"] == d["owned_after"] and d["settle"] and "item_record" in d
    assert ("p426-dnf", False) in order                       # chain.json was written while no sidecar existed
    assert len(list(tmp_path.rglob("*.json"))) == 1           # then exactly one sidecar
    assert c.dnf == [] and c.incidents == []                  # never a row, never an M64 incident


@pytest.mark.parametrize("kw, ctor", [
    (dict(cause="server_error"), {}), (dict(cause=None), {}), (dict(cause="worker_crash"), {}),
    (dict(cleanup=dict(GOOD_CLEANUP, survivors=["p"])), {}), (dict(cleanup=None), {}),
    (dict(), dict(worker=dict(pid=2, create_time=10))), (dict(), dict(worker=None)), (dict(), dict(router_ok=False))])
def test_everything_but_a_clean_dnf_class_abort_on_unchanged_identities_is_systemic(tmp_path, kw, ctor):
    c = bare(tmp_path, **ctor)
    with pytest.raises(co.ChainAbort):
        incomplete(c, tmp_path, **kw)
    assert c.p426_dnf == []


def test_the_third_dnf_of_a_leg_is_systemic_and_the_second_is_not(tmp_path):
    c = bare(tmp_path)
    old = dict(slot=f"{BASE}|x", session="s1", language="python", arm="A")
    c.p426_dnf = [old]
    assert incomplete(c, tmp_path)[0] == "dnf" and len(c.p426_dnf) == 2
    c.p426_dnf = [old, dict(old, slot=f"{BASE}|y")]
    with pytest.raises(co.ChainAbort, match="DNF"):
        incomplete(c, tmp_path)


def test_the_dnf_eligibility_check_is_injectable_and_defaults_to_eligible(tmp_path):
    c = bare(tmp_path)
    c.p426_dnf_eligible = lambda *a, **k: "section 4.3 DNF row does not hold"
    with pytest.raises(co.ChainAbort, match="4.3"):
        incomplete(c, tmp_path)
    load, leg, _inv, _rec, att, _ids = scenario(tmp_path)
    assert core.Chain.p426_dnf_eligible(bare(tmp_path), att, load, leg, "timeout") is None
    assert core.Chain.p426_dnf_eligible(bare(tmp_path, worker=dict(pid=9, create_time=1)), att, load, leg, "timeout")


def leg_with(invs):
    return dict(slot_base=BASE, lang="python", arm="A", model="M", session="s1", stem="M.s1.A_python", li=0, pos=0,
                invocations=[dict(phase=ph, names=[i.split("/")[1] for i in ex], expect=list(ex)) for ph, ex in invs])


def test_after_a_dnf_the_remaining_items_run_in_order_on_the_same_loaded_instance(tmp_path):
    c = bare(tmp_path)
    scored, calls = set(), []
    c.check_stop = lambda where: None
    c.slot_table = lambda: SimpleNamespace(scored=set(scored), blocked=set())
    load = dict(rec=dict(cursor=None), worker=dict(WORKER))

    def run_invocation(ld, leg, inv):
        assert ld is load and ld["worker"] == WORKER                       # the same loaded instance, no reload
        calls.append((inv["phase"], list(inv["expect"])))
        if len(calls) == 1:                                               # the head item DNFs
            c.p426_dnf.append(dict(slot=f"{BASE}|a", session="s1", language="python", arm="A"))
            return "dnf"
        scored.update(f"{BASE}|{e.split('/')[1]}" for e in inv["expect"])
        return "ok"

    c.run_invocation = run_invocation
    leg = leg_with([("pilot", ["python/a", "python/b"]), ("full", ["python/c", "python/d"])])
    assert c.run_p426_leg(load, leg) == "ok"
    assert calls == [("pilot", ["python/a", "python/b"]), ("pilot", ["python/b"]), ("full", ["python/c", "python/d"])]


def test_a_p426_leg_that_makes_no_progress_aborts_instead_of_looping(tmp_path):
    c = bare(tmp_path)
    c.check_stop = lambda where: None
    c.slot_table = lambda: SimpleNamespace(scored=set(), blocked=set())
    c.run_invocation = lambda *a: "ok"
    with pytest.raises(co.ChainAbort):
        c.run_p426_leg(dict(rec=dict(cursor=None)), leg_with([("pilot", ["python/a"])]))


# -- the item barrier: invalidate, the hook context, systemic hook errors, the ledger
def barrier(tmp_path, c, names=("a",)):
    rec = dict(file="s1/o.jsonl", load_gen=0, manifest="m")
    view = dict(slot_base=BASE, lang="python", arm="A", model="M", session="s1", out=str(tmp_path / "o.jsonl"))
    load = dict(idx=0, rec=dict(load_gen=0), worker=dict(WORKER))
    bar = c.new_barrier(rec, dict(names=list(names), expect=[f"python/{n}" for n in names]), tmp_path / "b", view, load)
    return bar


class Invalidating(ch.ChainHooks):
    def __init__(self, where):
        self.where, self.seen = where, []

    def before_attempt(self, slot, context=None):
        self.seen.append(("before", slot, context))
        return ch.Disposition.invalidate("ready check") if self.where == "before" else ch.Disposition.accept()

    def after_attempt(self, slot, done, context=None):
        self.seen.append(("after", slot, done, context))
        return ch.Disposition.invalidate("done check") if self.where == "after" else ch.Disposition.accept()


def test_invalidate_at_ready_is_persisted_before_the_stop_and_stops_the_leg(tmp_path):
    c = bare(tmp_path)
    c.hooks = Invalidating("before")
    bar = barrier(tmp_path, c)
    (tmp_path / "b.item0.ready").write_text("{}")
    seen_stop = []
    c.write_json = lambda status=None: seen_stop.append((status, (tmp_path / "b.item0.stop").exists()))
    c.pump_barrier(bar)
    assert c.p426_invalid == [dict(stage="ready", slot=f"{BASE}|a", reason="ready check", at=c.p426_invalid[0]["at"])]
    assert ("invalidated", False) in seen_stop                      # persisted BEFORE the .stop
    assert json.loads((tmp_path / "b.item0.stop").read_text()) == {"disposition": "invalidate"}
    assert bar["stage"] == "stopped" and bar["stop"]["disposition"] == "invalidate" and bar["stop"]["kind"] == "before"
    assert c.progress["pre_spawn"] == [] and c.incidents == []
    assert c.hooks.seen[0][2]["slot"] == f"{BASE}|a" and "load" in c.hooks.seen[0][2]


def test_invalidate_at_done_is_persisted_before_the_stop_and_the_hook_gets_row_ready_record_and_load(tmp_path, monkeypatch):
    c = bare(tmp_path)
    c.hooks = Invalidating("after")
    bar = barrier(tmp_path, c)
    (tmp_path / "b.item0.ready").write_text(json.dumps({"ready": "record"}))
    c.pump_barrier(bar)                                             # ready: accepted, `.go`
    assert (tmp_path / "b.item0.go").exists() and bar["stage"] == "done"
    (tmp_path / "b.item0.done").write_text(json.dumps({"id": "python/a"}))
    monkeypatch.setattr(core.cr, "read_rows", lambda p: [{"id": "python/a", "gate": {}}])
    c.web_record, c.web_rules = (lambda *a, **k: {"web": 1}), (lambda arm: None)
    seen_stop = []
    c.write_json = lambda status=None: seen_stop.append((status, (tmp_path / "b.item0.stop").exists()))
    c.pump_barrier(bar)
    assert c.p426_invalid[0]["stage"] == "done" and c.p426_invalid[0]["reason"] == "done check"
    assert ("invalidated", False) in seen_stop
    assert json.loads((tmp_path / "b.item0.stop").read_text()) == {"disposition": "invalidate"}
    assert bar["stop"]["kind"] == "after" and bar["stop"]["disposition"] == "invalidate"
    _, slot, done, ctx = c.hooks.seen[-1]
    assert slot == f"{BASE}|a" and done["id"] == "python/a"
    assert ctx["row"]["id"] == "python/a" and ctx["ready"] == {"ready": "record"} and ctx["load"]["worker"] == WORKER
    assert not (tmp_path / "b.item0.continue").exists() and c.p426_ledger == []


def test_an_accepted_item_is_ledgered_before_the_continue_answer(tmp_path, monkeypatch):
    c = bare(tmp_path)
    bar = barrier(tmp_path, c)
    (tmp_path / "b.item0.ready").write_text("{}")
    c.pump_barrier(bar)
    (tmp_path / "b.item0.done").write_text(json.dumps({"id": "python/a"}))
    monkeypatch.setattr(core.cr, "read_rows", lambda p: [{"id": "python/a", "gate": {}}])
    c.web_record, c.web_rules = (lambda *a, **k: {}), (lambda arm: None)
    c.write_json = lambda status=None: c.saved.append((status, (tmp_path / "b.item0.continue").exists()))
    c.pump_barrier(bar)
    assert c.p426_ledger == [dict(slot=f"{BASE}|a", kind="row", invocation="s1/o.jsonl", index=0)]
    assert ("ledger", False) in c.saved and (tmp_path / "b.item0.continue").exists()


@pytest.mark.parametrize("where", ["before", "after"])
def test_a_p426_hook_infrastructure_error_is_systemic_never_a_pre_spawn_incident(tmp_path, monkeypatch, where):
    class Broken(ch.ChainHooks):
        def before_attempt(self, slot, context=None):
            raise ch.HookInfrastructureError("metrics_unreadable")

        def after_attempt(self, slot, done, context=None):
            raise ch.HookInfrastructureError("record_write_failed")

    c = bare(tmp_path)
    c.hooks = Broken()
    bar = barrier(tmp_path, c)
    (tmp_path / "b.item0.ready").write_text("{}")
    if where == "after":
        c.hooks = Invalidating("accept")
        c.pump_barrier(bar)
        c.hooks = Broken()
        (tmp_path / "b.item0.done").write_text(json.dumps({"id": "python/a"}))
        monkeypatch.setattr(core.cr, "read_rows", lambda p: [{"id": "python/a", "gate": {}}])
        c.web_record, c.web_rules = (lambda *a, **k: {}), (lambda arm: None)
    c.pump_barrier(bar)
    assert c.progress["pre_spawn"] == [] and c.incidents == []
    assert c.p426_invalid[0]["stage"] == ("ready" if where == "before" else "done")
    assert c.p426_invalid[0]["reason"].startswith("hook infrastructure error")
    assert json.loads((tmp_path / "b.item0.stop").read_text()) == {"disposition": "invalidate"}


def test_a_legacy_chain_still_turns_a_hook_infrastructure_error_into_a_pre_spawn_incident(tmp_path):
    class Broken(ch.ChainHooks):
        def before_attempt(self, slot):
            raise ch.HookInfrastructureError("metrics_unreadable")

    c = bare(tmp_path, policy="abort_restart")
    c.hooks = Broken()
    bar = barrier(tmp_path, c)
    (tmp_path / "b.item0.ready").write_text("{}")
    c.pump_barrier(bar)
    assert c.progress["pre_spawn"][0]["cause"] == "metrics_unreadable" and bar["stop"]["cause"] == "metrics_unreadable"


@pytest.mark.parametrize("kind", ["before", "after"])
def test_an_invalidated_invocation_is_accepted_for_its_prefix_then_the_leg_is_invalid_rc_2(tmp_path, monkeypatch, kind):
    c = bare(tmp_path)
    load, leg, inv, rec, att, _ = scenario(tmp_path)
    monkeypatch.setattr(core.cr, "rows_if_present", lambda p: [])
    c.after_invocation = lambda *a, **k: None
    cleaned = []
    c.require_certain_cleanup = lambda *a: cleaned.append(a[2])
    hook = dict(kind=kind, k=0, name="a", slot=f"{BASE}|a", disposition="invalidate", reason="check failed")
    with pytest.raises(core.LegInvalid) as exc:
        c.accept_invocation(load, leg, inv, rec, tmp_path / "o.jsonl", hook, att=att, view=leg)
    assert exc.value.code == 2 and "check failed" in str(exc.value) and isinstance(exc.value, co.ChainAbort)
    assert rec["status"] == "hook_stopped" and cleaned                    # cleanup verified before the leg is INVALID


def test_invalidate_with_a_disposition_record_round_trips_through_the_persisted_dict():
    d = ch.Disposition.invalidate("x")
    assert ch.Disposition.from_dict(json.loads(json.dumps(d.as_dict()))) == d


def test_the_per_item_ledger_equals_the_plan_slot_for_slot_in_order(tmp_path):
    c = bare(tmp_path)
    leg = leg_with([("pilot", ["python/a", "python/b"]), ("full", ["python/c"])])
    leg["realized_key"] = [0, "python"]
    c.loads, c.realized = [dict(legs=[leg])], [[0, "python"]]
    row = lambda n, kind="row": dict(slot=f"{BASE}|{n}", kind=kind, invocation="i", index=0)       # noqa: E731
    c.p426_dnf = [dict(slot=f"{BASE}|b")]
    c.p426_ledger = [row("a"), row("b", "dnf"), row("c")]                  # a DNF slot is a ledger slot
    c.check_realized()
    for bad in ([row("b"), row("a"), row("c")], [row("a"), row("c")], [row("a"), row("a"), row("b"), row("c")],
                [row("a"), row("b"), row("c"), row("c")], []):
        c.p426_ledger = bad
        with pytest.raises(co.ChainAbort, match="ledger"):
            c.check_realized()


def test_a_legacy_chain_has_no_ledger_check(tmp_path):
    c = bare(tmp_path, policy="abort_restart")
    c.p426_ledger = [dict(slot="junk", kind="row")]
    c.check_realized()                                                    # freezes_schedule is false: nothing to check


# -- the manifest's evidence policy
def test_the_chains_expected_evidence_policy_is_the_probes_p426_policy():
    from bench import tg1_runner
    assert core.P426_EVIDENCE_POLICY == tg1_runner.TG1_P426_EVIDENCE.as_dict()
    assert core.P426_EVIDENCE_POLICY != tg1_runner.TG1_EVIDENCE.as_dict()


def test_a_manifest_without_the_p426_evidence_policy_is_refused_in_tg1_p426_only(tmp_path):
    from bench import tg1_runner
    c = bare(tmp_path)
    good = {"runtime": {"evidence_policy": tg1_runner.TG1_P426_EVIDENCE.as_dict()}}
    old = {"runtime": {"evidence_policy": tg1_runner.TG1_EVIDENCE.as_dict()}}
    assert c.evidence_policy_problems(good) == []
    assert c.evidence_policy_problems(old) and c.evidence_policy_problems({"runtime": {}}) and \
        c.evidence_policy_problems({})
    legacy = bare(tmp_path, policy="abort_restart")
    assert legacy.evidence_policy_problems(old) == [] and legacy.evidence_policy_problems({}) == []


def test_verify_manifest_asks_for_the_evidence_policy_check_of_the_chain(tmp_path):
    c = bare(tmp_path)
    c.lifecycle_problems = lambda: []
    c.campaign_core = None
    c.contract_problems = lambda: []
    c.arms, c.snapshots, c.pinned, c.frozen, c.expected_policy = {}, {}, {}, None, None
    c.arm_ids, c.specs, c.bindings = ["A"], {}, {"A": SimpleNamespace(label="x")}
    c.ops.overlay_sha = lambda: "r"
    c.a = SimpleNamespace(probe_code_sha=None)
    c.runtime_pinned = lambda arm: ()
    c.evidence_policy_problems = lambda man: ["evidence_policy: marker"]
    leg = dict(model="M", lang="python", seed_base=1, draft_kind="off", arm="A")
    why = c.verify_manifest({"runtime": {}, "worker": None, "registry": {}}, leg, dict(worker=dict(WORKER)), nonce="0" * 64)
    assert "evidence_policy: marker" in why


# -- one test per `transport_policy` branch site (spec 2: none falls through to the abort_restart side)
def test_site_load_record_p426_restores_the_dnf_and_ledger_state_and_the_others_do_not(tmp_path):
    prev = dict(progress=dict(loads=[], invocations=[]), snapshots={}, epoch_id=None, pinned={},
                schedule_sha256="s", realized=[], p426_dnf=[dict(slot="x")], p426_ledger=[dict(slot="y")],
                incidents=[dict(slot="i")], dnf=[dict(slot="d")])
    c = bare(tmp_path)
    c.attempt_no = {}
    c.load_record(prev)
    assert c.p426_dnf == [dict(slot="x")] and c.p426_ledger == [dict(slot="y")] and c.incidents == [] and c.dnf == []
    legacy = bare(tmp_path, policy="abort_restart")
    legacy.attempt_no = {}
    legacy.load_record(prev)
    assert legacy.p426_dnf == [] and legacy.p426_ledger == []


def test_site_archive_load_is_refused_under_p426_continue_there_is_no_reload(tmp_path):
    c = bare(tmp_path)
    with pytest.raises(co.ChainAbort, match="p426_continue"):
        c.archive_load(dict(rec=dict(load_gen=0), session="s1", model="M", idx=0))


def test_site_the_advance_load_op_never_carries_dnf_slots_under_p426_continue(tmp_path):
    c = bare(tmp_path)
    c.progress["loads"] = [dict(load=0, load_gen=0, status="running", cursor=None)]
    with pytest.raises(co.ChainAbort, match="p426_continue"):
        c.apply_txn_op(dict(op="advance_load", load=0, gen=0, dnf_slots=["x"], sched_idx=0))


def test_site_a_before_slot_pre_spawn_hook_stop_cannot_occur_under_p426_continue(tmp_path, monkeypatch):
    c = bare(tmp_path)
    load, leg, inv, rec, att, _ = scenario(tmp_path)
    monkeypatch.setattr(core.cr, "rows_if_present", lambda p: [])
    c.after_invocation = lambda *a, **k: None
    hook = dict(kind="before", k=0, name="a", slot=f"{BASE}|a", cause="metrics_unreadable")
    with pytest.raises(co.ChainAbort, match="p426_continue"):
        c.accept_invocation(load, leg, inv, rec, tmp_path / "o.jsonl", hook, att=att, view=leg)


@pytest.mark.parametrize("policy, raises", [("p426_continue", True), ("incident_retry", True), ("abort_restart", False)])
def test_site_restart_eligibility_takes_the_exact_cleanup_receipt_under_p426_continue(tmp_path, policy, raises):
    c = bare(tmp_path, policy=policy)
    att = dict(rc=1, outcome="exited", cleanup_status=dict(GOOD_CLEANUP, orphans_unattributed=["x"]))
    block = dict(worker=dict(WORKER))
    if raises:
        with pytest.raises(co.ChainAbort, match="exact"):
            c.check_restart_eligible(att, dict(model="M"), block)
    else:
        c.check_restart_eligible(att, dict(model="M"), block)


def test_site_handle_incomplete_keeps_abort_restart_and_incident_retry_behaviour(tmp_path):
    for policy in ("abort_restart", "incident_retry"):
        c = bare(tmp_path, policy=policy)
        eligible = []
        c.check_restart_eligible = lambda att, leg, block: eligible.append(1)
        c.classify_incident = lambda *a: None
        load, leg, inv, rec, att, _ = scenario(tmp_path)
        assert c.handle_incomplete(load, leg, inv, rec, att, ["why"], sup={}, view=leg) == "incomplete"
        assert eligible == [1] and c.p426_dnf == []


def test_p426_dnf_records_survive_in_chain_json_layout(tmp_path):
    c = bare(tmp_path)
    c.expected_policy, c.pinned, c.schedule_sha, c.probe = "p", {}, "s", Path("probe.py")
    c.p426_dnf, c.p426_invalid = [dict(slot="x")], [dict(stage="ready")]
    c.p426_ledger = [dict(slot="y")]
    out = c.record_layout()
    assert out["p426_dnf"] == [dict(slot="x")] and out["p426_ledger"] == [dict(slot="y")]
    assert out["p426_invalid"] == [dict(stage="ready")]
    legacy = bare(tmp_path, policy="abort_restart")
    legacy.expected_policy, legacy.pinned, legacy.probe = "p", {}, Path("probe.py")
    assert "p426_dnf" not in legacy.record_layout()
