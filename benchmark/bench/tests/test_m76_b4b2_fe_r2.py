"""M76 B4b-2 change review r2 (D1–D4) — scenario tests beside the implementer's `test_m76_b4b2_impl_r2fix.py`, on the frozen `World`:
the accounting records bind exactly also on a RERUN slot (rerun index 1), a list that is not a list or disagrees with the accepted
attempt refuses; zoned ISO times at the epoch boundary and with an offset; the registry pick bound arm by arm and in the schedule;
a malformed rerun index is a refusal (never a traceback), in the string form too.

Class: (a) reproduces a failure the spec fixes · (b) preserves an invariant · (c) new behaviour.
"""
from __future__ import annotations

import json

import pytest

from bench import p426_hooks as ph
from bench import p426_verify as V
from bench.tests import test_m76_b4b2_fe_support as W
from bench.tests.p613.a7world import dumps


def by_session(doc):
    return {p["pair"]: p for p in doc["pairs"]}


def a8(w):
    return V.verify_a8_kv(w.root, w.base_b8_sha())


def reload_ids():
    return W.schedule_ids(W.tg2_schedule("reload"))


def side(slot, k):
    return f"items/{ph.record_name(slot, k, 'accounting.json')}"


def rerun_accounting_world(tmp_path, listed=True):
    """A rerun slot whose ACCEPTED attempt (index 1) is an accounting fault: slot state, ledger (rerun 1), sidecar `.r1`, chain list."""
    rid = reload_ids()[0]
    w = W.World(tmp_path, corpus="tg2", sessions=("reload",), reruns={("x", "reload"): [rid]}, accounting={("x", "reload"): [rid]})
    slot = w.slot("reload", rid)
    if listed:
        w.edit_chain("x", "reload", lambda d: d.__setitem__("p426_accounting_faults",
                                                             [dict(slot=slot, rerun_index=1, sidecar=side(slot, 1))]))
    return w, rid, slot


# (a) B2 (kept here because the v3 `World.edit_row` re-hashes): a rows file changed after its invocation record was validated refuses
def test_b2_a_rows_file_changed_behind_its_invocation_record_refuses(tmp_path):
    w = W.World(tmp_path, corpus="tg2", sessions=("pilot",))
    f = next(w.adir("x", "pilot", "pilot").glob("*.jsonl"))
    f.write_text(f.read_text().replace('"wall_s": ', '"wall_s": 1', 1))          # bytes change, the recorded sha256 does not
    with pytest.raises(V.RefusalError, match="sha256 differs"):
        a8(w)


# ------------------------------------------------------------------------------------------------------------------ D1
# (b) control: an accounting fault on an accepted RERUN (index 1) with all four records agreeing is accepted and listed
def test_d1_control_a_rerun_accounting_fault_with_agreeing_records_is_accepted(tmp_path):
    w, rid, _ = rerun_accounting_world(tmp_path)
    rec = by_session(a8(w))["reload"]
    assert rec["accepted"], rec["reasons"]
    assert rec["faults"]["x"]["accounting_faults"] == [rid] and rid in rec["faults"]["x"]["reruns"]


# (a) exactly one ledger entry at the ACCEPTED rerun index: a second, contradicting one at rerun 1 refuses
def test_d1_a_contradictory_second_ledger_entry_at_the_accepted_rerun_refuses(tmp_path):
    w, rid, slot = rerun_accounting_world(tmp_path)
    w.edit_chain("x", "reload", lambda d: d["p426_ledger"].append(dict(slot=slot, kind="row", invocation=None, rerun_index=1,
                                                                        index=len(d["p426_ledger"]))))
    with pytest.raises(V.RefusalError, match="p426_ledger"):
        a8(w)


# (a) the ledger entry of an accepted rerun names rerun 0 (the faulted attempt's index): there is none at the accepted index
def test_d1_a_ledger_entry_at_the_wrong_rerun_index_refuses(tmp_path):
    w, rid, slot = rerun_accounting_world(tmp_path)

    def edit(chain):
        for e in chain["p426_ledger"]:
            if e.get("slot") == slot and e.get("kind") == "row":
                e["rerun_index"] = 0
    w.edit_chain("x", "reload", edit)
    with pytest.raises(V.RefusalError, match="p426_ledger"):
        a8(w)


# (a) the chain list names the faulted attempt's index while the accepted attempt is rerun 1: the records disagree
def test_d1_a_list_entry_at_another_rerun_index_refuses(tmp_path):
    w, rid, slot = rerun_accounting_world(tmp_path, listed=False)
    w.edit_chain("x", "reload", lambda d: d.__setitem__("p426_accounting_faults",
                                                         [dict(slot=slot, rerun_index=0, sidecar=side(slot, 0))]))
    with pytest.raises(V.RefusalError):
        a8(w)


# (a) a chain list that is not a list refuses (never read as empty)
@pytest.mark.parametrize("bad", [{}, "none", 0])
def test_d1_a_chain_list_that_is_not_a_list_refuses(bad, tmp_path):
    w, rid, slot = rerun_accounting_world(tmp_path)
    w.edit_chain("x", "reload", lambda d: d.__setitem__("p426_accounting_faults", bad))
    with pytest.raises(V.RefusalError, match="p426_accounting_faults"):
        a8(w)


# (a) a list entry for a row that is no accounting fault refuses
def test_d1_a_list_entry_for_a_row_without_a_fault_refuses(tmp_path):
    rid = W.schedule_ids(W.tg2_schedule("pilot"))[2]
    w = W.World(tmp_path, corpus="tg2", sessions=("pilot",))
    slot = w.slot("pilot", rid)
    w.edit_chain("x", "pilot", lambda d: d.__setitem__("p426_accounting_faults", [dict(slot=slot, rerun_index=0, sidecar=side(slot, 0))]))
    with pytest.raises(V.RefusalError):
        a8(w)


# (b) an empty chain list on an attempt without accounting faults stands
def test_d1_an_empty_list_with_no_fault_stands(tmp_path):
    w = W.World(tmp_path, corpus="tg2", sessions=("pilot",))
    w.edit_chain("x", "pilot", lambda d: d.__setitem__("p426_accounting_faults", []))
    assert by_session(a8(w))["pilot"]["accepted"]


# ------------------------------------------------------------------------------------------------------------------ D2
def _latency_world(tmp_path, t):
    w = W.World(tmp_path, corpus="tg2", sessions=("pilot",))
    w.write_latency(rows=[dict(t=t, fresh_ms=120.0, repeat_ms=30.0, true_ms=25.0, threatlocker_cpu=1.5)])
    return w


# (b) the epoch itself and a zoned time with an offset are valid UTC times (the rule is "finite and non-negative")
@pytest.mark.parametrize("t,want", [("1970-01-01T00:00:00Z", 0.0), ("1970-01-01T01:00:00+01:00", 0.0),
                                    ("2026-11-20T09:00:00+02:00", 1795158000.0)])
def test_d2_a_valid_zoned_time_is_utc_seconds(t, want, tmp_path):
    assert V.a8_utc_seconds(t) == want
    doc = a8(_latency_world(tmp_path, t))
    assert doc["latency"]["status"] == "present" and len(doc["latency"]["rows"]) == 1


# (a) a time before the epoch in UTC (whatever its written offset) is refused
@pytest.mark.parametrize("t", ["1969-12-31T18:59:59-05:00", "1969-12-31T23:59:59.999Z", "1970-01-01T00:59:59+01:00"])
def test_d2_a_time_before_the_epoch_in_utc_refuses(t, tmp_path):
    assert V.a8_utc_seconds(t) is None
    with pytest.raises(V.RefusalError, match="exec_latency"):
        a8(_latency_world(tmp_path, t))


# (b) a numeric `t` follows the same rule: negative refuses, zero stands
def test_d2_numeric_t_follows_the_same_rule(tmp_path):
    assert V.a8_utc_seconds(0) == 0.0 and V.a8_utc_seconds(-1) is None and V.a8_utc_seconds(float("nan")) is None
    with pytest.raises(V.RefusalError, match="exec_latency"):
        a8(_latency_world(tmp_path, -5))


# ------------------------------------------------------------------------------------------------------------------ D3
# (a) one arm alone naming another model than the registry pick is rejected
def test_d3_one_arms_model_off_the_registry_pick_rejects_the_session(tmp_path):
    w = W.World(tmp_path, corpus="tg2", sessions=("pilot",),
                manifest_hook=lambda arm, s, lang, m: dict(m, model="another-model") if arm == "x" else m)
    rec = by_session(a8(w))["pilot"]
    assert not rec["accepted"] and any("registry pick" in r for r in rec["reasons"]), rec["reasons"]


# (a) a schedule whose first pick is not the registry pick (manifests and rows on the registry pick) is rejected by its picks
def test_d3_a_schedule_naming_another_pick_is_rejected(tmp_path):
    w = W.World(tmp_path, corpus="tg2", sessions=("pilot",))
    for arm in ("n16", "x"):
        path = w.adir(arm, "pilot", "schedule.json")
        doc = json.loads(path.read_text())
        doc["picks"] = ["another-model"]
        path.write_text(dumps(doc))
    rec = by_session(a8(w))["pilot"]
    assert not rec["accepted"] and any("registry pick" in r or "picks" in r for r in rec["reasons"]), rec["reasons"]


# (b) the registry pick everywhere is accepted
def test_d3_the_registry_pick_is_accepted(tmp_path):
    assert V.ENTRY == W.MODEL
    assert by_session(a8(W.World(tmp_path, corpus="tg2", sessions=("pilot",))))["pilot"]["accepted"]


# ------------------------------------------------------------------------------------------------------------------ D4
# (a) a malformed rerun index is a REFUSAL (RefusalError), never a ValueError / TypeError traceback — the numeric-string form too
@pytest.mark.parametrize("bad", ["0", "1", None, {}, float("nan")])
@pytest.mark.parametrize("where", ["ledger", "list"])
def test_d4_other_malformed_rerun_indices_refuse_cleanly(bad, where, tmp_path):
    rid = W.schedule_ids(W.tg2_schedule("pilot"))[1]
    w = W.World(tmp_path, corpus="tg2", sessions=("pilot",), accounting={("x", "pilot"): [rid]})
    slot = w.slot("pilot", rid)
    w.edit_chain("x", "pilot", lambda d: d.__setitem__("p426_accounting_faults", [dict(slot=slot, rerun_index=0, sidecar=side(slot, 0))]))

    def edit(chain):
        recs = chain["p426_ledger"] if where == "ledger" else chain["p426_accounting_faults"]
        for e in recs:
            if e.get("slot") == slot:
                e["rerun_index"] = bad
    w.edit_chain("x", "pilot", edit)
    try:
        a8(w)
    except V.RefusalError:
        return
    except Exception as exc:                                   # noqa: BLE001 — the point of the test
        pytest.fail(f"a malformed rerun_index {bad!r} in the {where} raised {type(exc).__name__}, not a RefusalError")
    pytest.fail(f"a malformed rerun_index {bad!r} in the {where} was accepted")


# (b) a ledger entry that omits `rerun_index` means rerun 0 (the runner omits it there); an explicit integer 0 is the same
@pytest.mark.parametrize("form", ["omitted", "zero"])
def test_d4_a_ledger_entry_without_or_with_zero_rerun_index_is_rerun_zero(form, tmp_path):
    w = W.World(tmp_path, corpus="tg2", sessions=("pilot",))

    def edit(chain):
        for e in chain["p426_ledger"]:
            if e.get("kind") == "row":
                if form == "omitted":
                    e.pop("rerun_index", None)
                else:
                    e["rerun_index"] = 0
    w.edit_chain("x", "pilot", edit)
    assert by_session(a8(w))["pilot"]["accepted"]
