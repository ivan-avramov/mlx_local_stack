"""M76 B4b-2 change review r3 (ledger `change-ledger-r3.md`): one red test per finding (E1–E3)."""
from __future__ import annotations

import json

import pytest

from bench import p426_hooks as ph
from bench import p426_verify as V
from bench.tests import test_m76_b4b2_fe_support as W
from bench.tests.test_m76_b4b2_impl_r1fix import _rewrite_rows, a8, by_session, ids, world


def _side(slot, k=0):
    return f"items/{ph.record_name(slot, k, 'accounting.json')}"


def _strip_markers(w, session, slot, rid, *, row=True):
    def edit(chain):
        for e in chain["p426_ledger"]:
            if e.get("slot") == slot:
                e.pop("accounting_fault", None)
        for a in chain["progress"]["slot_attempts"]:
            if a.get("slot") == slot:
                a.pop("accounting_fault", None)
    w.edit_chain("x", session, edit)
    if row:
        _rewrite_rows(w, "x", session, lambda r: r.pop("accounting_fault", None) if r["id"] == rid else None)


def _abort_route_world(tmp_path):
    """`chain_core.p426_abort_route`, stage `done` on a slot already ledgered at its barrier answer: the accepted slot attempt
    and the ledger entry stay unmarked, the row carries no marker; the fault is recorded only in `p426_accounting_faults` plus
    the sealed sidecar."""
    rid = ids("pilot")[1]
    w = world(tmp_path, accounting={("x", "pilot"): [rid]})
    slot = w.slot("pilot", rid)
    _strip_markers(w, "pilot", slot, rid)
    w.edit_chain("x", "pilot", lambda d: d.__setitem__("p426_accounting_faults", [dict(slot=slot, rerun_index=0,
                                                                                        reason="hook_infra at done: x",
                                                                                        sidecar=_side(slot))]))
    return w, rid, slot


def _side_path(w, slot, k=0):
    return w.adir("x", "pilot", *_side(slot, k).split("/"))


# ------------------------------------------------------------------------------------------------------------- E2
def test_e2_the_abort_routes_record_on_an_unmarked_ledgered_slot_is_an_accounting_fault(tmp_path):
    w, rid, _slot = _abort_route_world(tmp_path)
    rec = by_session(a8(w))["pilot"]
    assert rec["accepted"], rec["reasons"]
    assert rec["faults"]["x"]["accounting_faults"] == [rid]


@pytest.mark.parametrize("where", ["slot_attempt", "ledger"])
def test_e2_a_true_marker_without_the_chains_record_refuses(where, tmp_path):
    w, rid, slot = _abort_route_world(tmp_path)
    _side_path(w, slot).unlink()

    def edit(chain):
        chain["p426_accounting_faults"] = []
        recs = chain["p426_ledger"] if where == "ledger" else chain["progress"]["slot_attempts"]
        for e in recs:
            if e.get("slot") == slot:
                e["accounting_fault"] = True
    w.edit_chain("x", "pilot", edit)
    with pytest.raises(V.RefusalError, match="marker disagrees"):
        a8(w)


def test_e2_a_list_entry_without_its_sidecar_refuses(tmp_path):
    w, _rid, slot = _abort_route_world(tmp_path)
    _side_path(w, slot).unlink()
    with pytest.raises(V.RefusalError, match="accounting record is incomplete"):
        a8(w)


def test_e2_a_sidecar_without_its_list_entry_refuses(tmp_path):
    w, _rid, _slot = _abort_route_world(tmp_path)
    w.edit_chain("x", "pilot", lambda d: d.__setitem__("p426_accounting_faults", []))
    with pytest.raises(V.RefusalError, match="accounting record is incomplete"):
        a8(w)


def test_e2_a_false_marker_beside_the_chains_record_refuses(tmp_path):
    w, _rid, slot = _abort_route_world(tmp_path)

    def edit(chain):
        for a in chain["progress"]["slot_attempts"]:
            if a.get("slot") == slot:
                a["accounting_fault"] = False
    w.edit_chain("x", "pilot", edit)
    with pytest.raises(V.RefusalError, match="marker disagrees"):
        a8(w)


# ------------------------------------------------------------------------------------------------------------- E1
def _hdnf_world(tmp_path):
    rid = ids("reload")[2]
    return world(tmp_path, sessions=("reload",), hdnf={("x", "reload"): {rid: "harness_fault_dnf"}}), rid


def _append(session_slot_kind):
    def edit(chain):
        slot, kind = session_slot_kind
        chain["p426_ledger"].append(dict(slot=slot, kind=kind, invocation=None, index=len(chain["p426_ledger"])))
    return edit


def test_e1_control_a_harness_dnf_world_is_accepted(tmp_path):
    w, _rid = _hdnf_world(tmp_path)
    assert by_session(a8(w))["reload"]["accepted"]


def test_e1_a_second_entry_of_another_kind_for_a_row_slot_refuses(tmp_path):
    w = world(tmp_path)
    w.edit_chain("x", "pilot", _append((w.slot("pilot", ids("pilot")[2]), "dnf")))
    with pytest.raises(V.RefusalError, match="p426_ledger"):
        a8(w)


def test_e1_a_second_entry_for_a_dnf_slot_refuses(tmp_path):
    w, rid = _hdnf_world(tmp_path)
    w.edit_chain("x", "reload", _append((w.slot("reload", rid), "dnf")))
    with pytest.raises(V.RefusalError, match="p426_ledger"):
        a8(w)


def test_e1_a_dnf_slot_ledgered_as_a_row_refuses(tmp_path):
    w, rid = _hdnf_world(tmp_path)
    slot = w.slot("reload", rid)

    def edit(chain):
        for e in chain["p426_ledger"]:
            if e.get("slot") == slot:
                e["kind"] = "row"
    w.edit_chain("x", "reload", edit)
    with pytest.raises(V.RefusalError, match="p426_ledger entry has kind"):
        a8(w)


def test_e1_a_row_slot_ledgered_as_a_dnf_refuses(tmp_path):
    w = world(tmp_path)
    slot = w.slot("pilot", ids("pilot")[2])

    def edit(chain):
        for e in chain["p426_ledger"]:
            if e.get("slot") == slot:
                e["kind"] = "dnf"
    w.edit_chain("x", "pilot", edit)
    with pytest.raises(V.RefusalError, match="p426_ledger entry has kind"):
        a8(w)


@pytest.mark.parametrize("bad", ["bogus", None, 1, "ROW"])
def test_e1_a_malformed_kind_refuses(bad, tmp_path):
    w = world(tmp_path)
    slot = w.slot("pilot", ids("pilot")[3])

    def edit(chain):
        for e in chain["p426_ledger"]:
            if e.get("slot") == slot:
                if bad is None:
                    e.pop("kind")
                else:
                    e["kind"] = bad
    w.edit_chain("x", "pilot", edit)
    with pytest.raises(V.RefusalError, match="p426_ledger entry"):
        a8(w)


def test_e1_a_malformed_entry_of_an_unscored_slot_refuses(tmp_path):
    w = world(tmp_path)
    w.edit_chain("x", "pilot", lambda d: d["p426_ledger"].append("not an object"))
    with pytest.raises(V.RefusalError, match="p426_ledger entry"):
        a8(w)


# ------------------------------------------------------------------------------------------------------------- E3
def test_e3_the_frozen_support_edit_row_re_hashes_its_invocation_record(tmp_path):
    """The mechanism of E3: `World.edit_row` re-hashes the invocation record (v3 support), so an edited row is a consistent
    record — a test of a rows file changed AFTER validation must change the bytes itself."""
    w = world(tmp_path)
    w.edit_row("x", "pilot", ids("pilot")[1], wall_s=1.0)
    chain = json.loads(w.adir("x", "pilot", "chain.json").read_text())
    for inv in chain["progress"]["invocations"]:
        assert inv["sha256"] == W.sha_bytes(w.adir("x", "pilot", *inv["file"].split("/")).read_bytes())
