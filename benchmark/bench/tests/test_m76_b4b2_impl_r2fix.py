"""M76 B4b-2 change review r2 (ledger `change-ledger-r2.md`): one red test per adopted finding (D1–D4)."""
from __future__ import annotations

import json

import pytest

from bench import p426_hooks as ph
from bench import p426_verify as V
from bench.tests import test_m76_b4b2_fe_support as W
from bench.tests.test_m76_b4b2_impl_r1fix import _rewrite_rows, a8, by_session, ids, world


def _side(slot, k=0):
    return f"items/{ph.record_name(slot, k, 'accounting.json')}"


def _acct_listed_world(tmp_path):
    """An accounting-fault row as the runner records it: slot state, ledger entry, sidecar and the chain list entry."""
    rid = ids("pilot")[1]
    w = world(tmp_path, accounting={("x", "pilot"): [rid]})
    slot = w.slot("pilot", rid)
    w.edit_chain("x", "pilot", lambda d: d.__setitem__("p426_accounting_faults", [dict(slot=slot, rerun_index=0,
                                                                                        sidecar=_side(slot))]))
    return w, rid, slot


def test_d1_control_the_runners_accounting_records_are_accepted(tmp_path):
    w, rid, _slot = _acct_listed_world(tmp_path)
    rec = by_session(a8(w))["pilot"]
    assert rec["accepted"] and rec["faults"]["x"]["accounting_faults"] == [rid], rec["reasons"]


def _dup_ledger(w, slot):
    def edit(chain):
        chain["p426_ledger"].append(dict(slot=slot, kind="row", invocation=None, index=len(chain["p426_ledger"])))
    return edit


def _drop_ledger(w, slot):
    def edit(chain):
        chain["p426_ledger"] = [e for e in chain["p426_ledger"] if e.get("slot") != slot]
    return edit


def _list(fn):
    def edit_for(w, slot):
        def edit(chain):
            chain["p426_accounting_faults"] = fn(chain["p426_accounting_faults"], slot)
        return edit
    return edit_for


@pytest.mark.parametrize("case,edit_for", [
    ("contradictory duplicate ledger entry", _dup_ledger),
    ("duplicate chain-list entry", _list(lambda lst, slot: lst + [dict(lst[0])])),
    ("non-object chain-list entry", _list(lambda lst, slot: lst + ["not an object"])),
    ("chain-list entry naming another sidecar", _list(lambda lst, slot: [dict(lst[0], sidecar="items/elsewhere.json")])),
    ("chain-list entry without a sidecar", _list(lambda lst, slot: [{k: v for k, v in lst[0].items() if k != "sidecar"}])),
])
def test_d1_accounting_records_bind_exactly(case, edit_for, tmp_path):
    w, _rid, slot = _acct_listed_world(tmp_path)
    w.edit_chain("x", "pilot", edit_for(w, slot))
    with pytest.raises(V.RefusalError, match="p426_ledger|p426_accounting_faults"):
        a8(w)


def test_d1_a_row_without_its_ledger_entry_refuses(tmp_path):
    w = world(tmp_path)
    w.edit_chain("x", "pilot", _drop_ledger(w, w.slot("pilot", ids("pilot")[2])))
    with pytest.raises(V.RefusalError, match="p426_ledger"):
        a8(w)


# ------------------------------------------------------------------------------------------------------------- D2
@pytest.mark.parametrize("t", ["1969-12-31T23:59:59Z", "1900-01-01T00:00:00+00:00", "0001-01-01T00:00:00+01:00"])
def test_d2_an_iso_time_before_the_epoch_is_not_a_utc_time(t, tmp_path):
    assert V.a8_utc_seconds(t) is None
    w = world(tmp_path)
    w.write_latency(rows=[dict(t=t, fresh_ms=120.0, repeat_ms=30.0, true_ms=25.0, threatlocker_cpu=1.5)])
    with pytest.raises(V.RefusalError, match="exec_latency"):
        a8(w)


# ------------------------------------------------------------------------------------------------------------- D3
def test_d3_the_model_is_bound_to_the_registry_pick_not_the_schedule(tmp_path):
    other = "another-model"
    w = world(tmp_path, manifest_hook=lambda arm, s, lang, m: dict(m, model=other))
    for arm in ("n16", "x"):                             # rows, manifests and the schedule agree with each other, not with ENTRY
        _rewrite_rows(w, arm, "pilot", lambda r: r.__setitem__("model", other))
        sched = w.adir(arm, "pilot", "schedule.json")
        doc = json.loads(sched.read_text())
        doc["picks"] = [other]
        sched.write_text(json.dumps(doc, sort_keys=True, indent=2))
    assert V.ENTRY == W.MODEL != other
    rec = by_session(a8(w))["pilot"]
    assert not rec["accepted"] and any("registry pick" in r for r in rec["reasons"]), rec["reasons"]


# ------------------------------------------------------------------------------------------------------------- D4
@pytest.mark.parametrize("bad", ["x", [0], 1.5, True, -1])
@pytest.mark.parametrize("where", ["ledger", "list"])
def test_d4_a_malformed_rerun_index_is_a_refusal(bad, where, tmp_path):
    w, _rid, slot = _acct_listed_world(tmp_path)

    def edit(chain):
        recs = chain["p426_ledger"] if where == "ledger" else chain["p426_accounting_faults"]
        for e in recs:
            if e.get("slot") == slot:
                e["rerun_index"] = bad
    w.edit_chain("x", "pilot", edit)
    with pytest.raises(V.RefusalError, match="rerun_index"):
        a8(w)
