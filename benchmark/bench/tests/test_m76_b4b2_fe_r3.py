"""M76 B4b-2 change review r3 (E1, E2) and delivery 5 — scenario tests beside the implementer's `test_m76_b4b2_impl_r3fix.py`, on the
frozen `World`, plus the new-identity real-record facts the synthetic world could not know:

* E2 on the runner's own branch shape (`chain_core.p426_abort_route`, stage `done`, slot already ledgered): the accounting fault is
  recorded only by the chain's list entry + the sealed sidecar — also on an accepted RERUN (index 1) and without an item record;
  a marker True on the ROW alone refuses; an explicit False marker beside no record stands.
* E1: exactly one ledger entry per scored slot over ALL kinds — transport DNF, harness DNF, a missing entry, a DNF entry whose
  (present) rerun index is not the scored attempt's.
* the new-identity records: the real N16 s1 attempt (80 rows) loads and satisfies every per-attempt binding (inventory, ledger,
  accounting, identity, seeds, final trees) — the runner's real record shapes under E1 / E2.
* per-invocation provenance keys of the new identity (`probe_session.{run_dir,sid,started}`) are normalised, not "differences".

Class: (a) reproduces a failure the spec fixes · (b) preserves an invariant · (c) new behaviour.
"""
from __future__ import annotations

import json

import pytest

from bench import chain_rows as cr
from bench import p426_hooks as ph
from bench import p426_verify as V
from bench.tests import test_m76_b4b2_fe_support as W
from bench.tests.p613.a7world import dumps


def by_session(doc):
    return {p["pair"]: p for p in doc["pairs"]}


def a8(w):
    return V.verify_a8_kv(w.root, w.base_b8_sha())


def side(slot, k):
    return f"items/{ph.record_name(slot, k, 'accounting.json')}"


def unmark(w, arm, session, rid, slot):
    """The abort route's record: no marker on the accepted slot attempt, the ledger entry or the row."""
    def edit(chain):
        for e in chain["p426_ledger"]:
            if e.get("slot") == slot:
                e.pop("accounting_fault", None)
        for a in chain["progress"]["slot_attempts"]:
            if a.get("slot") == slot:
                a.pop("accounting_fault", None)
    w.edit_chain(arm, session, edit)
    for f in sorted(w.adir(arm, session, session).glob("*.jsonl")):          # drop the row's marker and re-hash its invocation
        rows = [json.loads(x) for x in f.read_text().splitlines() if x.strip()]
        hit = [r for r in rows if r.get("id") == rid]
        if not hit:
            continue
        hit[0].pop("accounting_fault", None)
        f.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
        w._rehash_invocation(arm, session, f, rid, hit[0])


def abort_route_world(tmp_path, rerun=False, session="pilot"):
    rid = W.schedule_ids(W.tg2_schedule(session))[0 if rerun else 1]
    kw = dict(corpus="tg2", sessions=(session,), accounting={("x", session): [rid]})
    if rerun:
        kw["reruns"] = {("x", session): [rid]}
    w = W.World(tmp_path, **kw)
    slot = w.slot(session, rid)
    k = 1 if rerun else 0
    unmark(w, "x", session, rid, slot)
    w.edit_chain("x", session, lambda d: d.__setitem__("p426_accounting_faults",
                                                        [dict(slot=slot, rerun_index=k, reason="hook_infra at done", sidecar=side(slot, k))]))
    return w, rid, slot, k


# ------------------------------------------------------------------------------------------------------------------ E2
# (c) the abort route's shape on an accepted RERUN (index 1): unmarked attempt / ledger / row + list entry + sidecar `.r1` = a fault
def test_e2_the_abort_routes_record_on_an_accepted_rerun_is_an_accounting_fault(tmp_path):
    w, rid, slot, k = abort_route_world(tmp_path, rerun=True, session="reload")
    rec = by_session(a8(w))["reload"]
    assert rec["accepted"], rec["reasons"]
    assert rec["faults"]["x"]["accounting_faults"] == [rid] and rid in rec["faults"]["x"]["reruns"]


# (c) the real abort route passes no item record to the sidecar (`item_record_sha256` None): a row with no item record stands
def test_e2_the_abort_routes_record_stands_without_an_item_record(tmp_path):
    w, rid, slot, k = abort_route_world(tmp_path)
    item = w.adir("x", "pilot", "items", ph.record_name(slot, k, "json"))
    item.unlink()
    sc = w.adir("x", "pilot", *side(slot, k).split("/"))
    doc = json.loads(sc.read_text())
    doc["item_record_sha256"] = None
    sc.write_text(dumps(ph.seal(doc)))
    rec = by_session(a8(w))["pilot"]
    assert rec["accepted"], rec["reasons"]
    assert rec["faults"]["x"]["accounting_faults"] == [rid]


# (a) a True marker on the ROW alone, with neither the chain's list entry nor a sidecar, refuses
def test_e2_a_true_row_marker_without_the_record_refuses(tmp_path):
    w = W.World(tmp_path, corpus="tg2", sessions=("pilot",))
    rid = W.schedule_ids(W.tg2_schedule("pilot"))[1]
    w.edit_chain("x", "pilot", lambda d: d.__setitem__("p426_accounting_faults", []))
    w.edit_row("x", "pilot", rid, accounting_fault=True)
    with pytest.raises(V.RefusalError, match="marker disagrees"):
        a8(w)


# (b) an explicit False marker on a row beside no record stands (a marker is checked only against the record)
def test_e2_an_explicit_false_marker_beside_no_record_stands(tmp_path):
    w = W.World(tmp_path, corpus="tg2", sessions=("pilot",))
    rid = W.schedule_ids(W.tg2_schedule("pilot"))[1]
    w.edit_chain("x", "pilot", lambda d: d.__setitem__("p426_accounting_faults", []))
    w.edit_row("x", "pilot", rid, accounting_fault=False)
    rec = by_session(a8(w))["pilot"]
    assert rec["accepted"] and rec["faults"]["x"]["accounting_faults"] == []


# (c) downstream: the fault the abort route recorded leaves the decode aggregate like a marked one (the slot table carries the fact)
def test_e2_the_recorded_fault_is_what_the_slot_table_and_the_listing_carry(tmp_path):
    w, rid, slot, k = abort_route_world(tmp_path)
    doc = a8(w)
    rec = by_session(doc)["pilot"]
    assert rec["faults"]["x"]["accounting_faults"] == [rid] and rec["faults"]["n16"]["accounting_faults"] == []
    reader = V.Reader(w.root)
    att = V._a8_load_attempt(reader, "tg2-m76-x-pilot.a1", "pilot", "x")
    assert att["slots"][rid]["accounting_fault"] is True and list(att["accounting"]) == [rid]


# ------------------------------------------------------------------------------------------------------------------ E1
def hdnf_world(tmp_path, kind="harness_fault_dnf"):
    rid = W.schedule_ids(W.tg2_schedule("reload"))[2]
    return W.World(tmp_path, corpus="tg2", sessions=("reload",), hdnf={("x", "reload"): {rid: kind}}), rid


def tdnf_world(tmp_path):
    rid = W.schedule_ids(W.tg2_schedule("reload"))[2]
    return W.World(tmp_path, corpus="tg2", sessions=("reload",), dnf={("x", "reload"): [rid]}), rid


# (b) controls: harness and transport DNF slots, each with its one `dnf` ledger entry, are accepted
@pytest.mark.parametrize("maker", [hdnf_world, tdnf_world])
def test_e1_control_dnf_slots_with_their_one_dnf_entry_are_accepted(maker, tmp_path):
    w, rid = maker(tmp_path)
    assert by_session(a8(w))["reload"]["accepted"]


# (a) a TRANSPORT DNF slot: a second ledger entry refuses; a `row` entry refuses; a missing entry refuses
def test_e1_a_second_entry_for_a_transport_dnf_slot_refuses(tmp_path):
    w, rid = tdnf_world(tmp_path)
    slot = w.slot("reload", rid)
    w.edit_chain("x", "reload", lambda d: d["p426_ledger"].append(dict(slot=slot, kind="dnf", invocation=None, index=len(d["p426_ledger"]))))
    with pytest.raises(V.RefusalError, match="p426_ledger"):
        a8(w)


def test_e1_a_transport_dnf_slot_ledgered_as_a_row_refuses(tmp_path):
    w, rid = tdnf_world(tmp_path)
    slot = w.slot("reload", rid)

    def edit(chain):
        for e in chain["p426_ledger"]:
            if e.get("slot") == slot:
                e["kind"] = "row"
    w.edit_chain("x", "reload", edit)
    with pytest.raises(V.RefusalError, match="p426_ledger"):
        a8(w)


@pytest.mark.parametrize("maker", [hdnf_world, tdnf_world])
def test_e1_a_dnf_slot_without_any_ledger_entry_refuses(maker, tmp_path):
    w, rid = maker(tmp_path)
    slot = w.slot("reload", rid)
    w.edit_chain("x", "reload", lambda d: d.__setitem__("p426_ledger", [e for e in d["p426_ledger"] if e.get("slot") != slot]))
    with pytest.raises(V.RefusalError, match="p426_ledger"):
        a8(w)


# (a) a DNF ledger entry that carries a rerun index which is not the scored attempt's refuses; one that carries none stands (runner)
def test_e1_a_dnf_entry_with_a_foreign_rerun_index_refuses(tmp_path):
    w, rid = tdnf_world(tmp_path)
    slot = w.slot("reload", rid)

    def edit(chain):
        for e in chain["p426_ledger"]:
            if e.get("slot") == slot:
                e["rerun_index"] = 3
    w.edit_chain("x", "reload", edit)
    with pytest.raises(V.RefusalError, match="p426_ledger|rerun"):
        a8(w)


# (a) a row slot with two `row` entries at DIFFERENT rerun indices refuses (exactly one per slot, not one per index)
def test_e1_two_row_entries_at_different_rerun_indices_refuse(tmp_path):
    w = W.World(tmp_path, corpus="tg2", sessions=("pilot",))
    slot = w.slot("pilot", W.schedule_ids(W.tg2_schedule("pilot"))[2])
    w.edit_chain("x", "pilot", lambda d: d["p426_ledger"].append(dict(slot=slot, kind="row", invocation=None, rerun_index=1,
                                                                       index=len(d["p426_ledger"]))))
    with pytest.raises(V.RefusalError, match="p426_ledger"):
        a8(w)


# (a) a ledger entry that is not a list element of objects: the ledger itself not a list refuses
@pytest.mark.parametrize("bad", [{}, "x", 3])
def test_e1_a_ledger_that_is_not_a_list_refuses(bad, tmp_path):
    w = W.World(tmp_path, corpus="tg2", sessions=("pilot",))
    w.edit_chain("x", "pilot", lambda d: d.__setitem__("p426_ledger", bad))
    with pytest.raises(V.RefusalError, match="p426_ledger"):
        a8(w)


# ------------------------------------------------------------------------------------------------------------------ the new identity
# (a) the new identity's invocation manifests carry a `probe_session` block (run directory, session id, start time) that differs
# between the arms by construction: per-invocation identity, normalised like `run_id` / `worker` — never a provenance difference
def test_the_new_identity_probe_session_block_is_per_invocation_not_provenance(tmp_path):
    def hook(arm, session, lang, man):
        man = json.loads(json.dumps(man))
        man["probe_session"] = dict(run_dir=f"$STACK_WORKDIR/opencode-probe-v2/run-{arm}-{lang}", sid=100 + len(arm) + len(lang),
                                    started=1795255600.0 + (7 if arm == "x" else 0))
        return man
    w = W.World(tmp_path, corpus="tg2", sessions=("pilot",), manifest_hook=hook)
    rec = by_session(a8(w))["pilot"]
    assert rec["accepted"], rec["reasons"]


# (b) ... while a real provenance key still differs: the same world with a changed sampling key is rejected
def test_a_real_provenance_difference_beside_probe_session_still_rejects(tmp_path):
    def hook(arm, session, lang, man):
        man = json.loads(json.dumps(man))
        man["probe_session"] = dict(run_dir=f"r-{arm}", sid=1 if arm == "n16" else 2, started=1.0 if arm == "n16" else 2.0)
        if arm == "x" and lang == "java":
            man["sampling"]["temperature"] = 0.9
        return man
    w = W.World(tmp_path, corpus="tg2", sessions=("pilot",), manifest_hook=hook)
    rec = by_session(a8(w))["pilot"]
    assert not rec["accepted"] and any("temperature" in r for r in rec["reasons"]), rec["reasons"]


M76 = W.BENCH / "results" / "m76"


# (c) the real N16 s1 attempt (VALID, 80 items, new identity) satisfies every per-attempt binding the A8 verifier makes: inventory
# (`load_slots`), ledger (one entry per slot), accounting, v8 identity, plan seeds, final trees
def test_the_real_n16_s1_attempt_satisfies_every_per_attempt_binding():
    reader = V.Reader(M76)
    att = V._a8_load_attempt(reader, "tg2-m76-n16-s1.a1", "s1", "n16")
    v8 = json.loads((M76 / "wave2.tg2" / "run" / "v8_base.json").read_text())
    assert len(att["rows"]) + len(att["dnf"]) == 80 and att["planned"] == 80
    assert att["slot_reasons"] == [] and V.a8_seed_reasons("n16", att, "s1") == []
    assert V.a8_v8_identity_reasons(reader, "n16", att, "s1", v8) == []
    assert V.final_tree_reasons("n16", att, V.KV_REPO_PREFIX, V.A8_NS) == []
    from bench import schedules
    schedules.check_tg2_p426(att["schedule"], W.draw_doc(), "s1")
    assert att["leg"]["state"] == "VALID"
