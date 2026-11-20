"""S27 -- test-writer delivery 4: scenario tests for the adopted findings of change review round 2 (Y1, Y3, Y4) that the
implementer's `test_s27_impl_r2fix.py` does not already cover, plus the re-staged X10 tests (in `test_s27_fe_r1.py`).

Class (a) = reproduces a candidate-2 defect (checked by inspection of `../scratch/fix-2.patch`: candidate 2 cannot be run beside
candidate 3), (b) = preserves an invariant, (c) = new behaviour. Exact where data validity depends on it (the anchored-case
sample, the sidecar's binding); the rest is intent.
"""
from __future__ import annotations

import json
import os

import pytest

from bench import p426_hooks as ph
from bench import p426_reconcile as pr
from bench.tests.test_s27_fe_r1 import x2_case
from bench.tests.test_s27_impl_r2fix import acct_leg

DROP = object()


# ------------------------------------------------------------------------------------------------ Y1: the sample must have READ 0
def _anchored(value):
    def edit(row):
        if value is DROP:
            row["termination"].pop("in_flight_at_kill", None)
        else:
            row["termination"]["in_flight_at_kill"] = value
    return pr.reconcile_item(*x2_case(row_edit=edit))


def test_y1_the_anchored_case_still_holds_for_a_sample_that_read_integer_zero():
    """(b) the control: the same row with the recorded `/metrics` sample 0."""
    rep = _anchored(0)
    assert rep.ok and rep.late_record and rep.late_record.get("shape") == "open_step_at_signal"


@pytest.mark.parametrize("value", [DROP, None, False, True, "0", "", 0.0, [], {}, -1],
                         ids=["absent", "None", "False", "True", "str0", "empty-str", "float0", "list", "dict", "negative"])
def test_y1_an_absent_or_malformed_sample_never_enters_the_anchored_case(value):
    """(a) Y1: the anchored case replaces a sample that READ 0; it never stands in for a missing one (data validity): the
    kill is refused, whatever the stream, signal and worker facts say. Candidate 2 accepted any value that was not a positive
    integer (by inspection)."""
    rep = _anchored(value)
    assert not rep.ok, value
    assert not (rep.late_record and rep.late_record.get("shape") == "open_step_at_signal")


# ------------------------------------------------------------------------------------------------ Y4: the sidecar's binding
def _problems(root, chain):
    """Freeze's and harvest's problems about the accounting sidecar / its item record (inventory problems included)."""
    from bench import p426_freeze as fz
    from bench import p426_harvest as hv
    freeze = [p for p in fz.leg_items_problems(root, "off") if "accounting" in p.lower() or "item record" in p.lower()
              or "sidecar" in p.lower()]
    problems = []
    inv, roots = hv._inventory(root, root.parent, problems)
    hv._check_references(root, "VALID", chain, inv, roots, root.parent, problems)
    harvest = [p for p in problems if "accounting" in p.lower() or "sidecar" in p.lower() or "symlink" in p.lower()
               or "accounting" in p]
    return freeze, harvest


def test_y4_a_bound_sidecar_is_accepted_by_both_consumers(tmp_path):
    """(b) control for the refusals below."""
    root, chain, _ = acct_leg(tmp_path)
    freeze, harvest = _problems(root, chain)
    assert freeze == [] and harvest == []


def _tamper(root, slots, edit):
    path = ph.accounting_path(root, slots[0], 0)
    doc = json.loads(path.read_text())
    edit(doc)
    path.write_text(json.dumps(doc))                       # NOT re-sealed: the self-hash no longer matches


def _remove(root, slots):
    ph.accounting_path(root, slots[0], 0).unlink()


def _symlink(root, slots):
    path = ph.accounting_path(root, slots[0], 0)
    real = path.with_name("real-copy.json")
    real.write_text(path.read_text())
    path.unlink()
    path.symlink_to(real)


@pytest.mark.parametrize("what, act", [
    ("a field changed after sealing (the self-hash no longer verifies)", lambda r, s: _tamper(r, s, lambda d: d.update(failed_checks=["x"]))),
    ("the row digest changed after sealing", lambda r, s: _tamper(r, s, lambda d: d.update(row_sha256="0" * 64))),
    ("the sidecar is missing although the ledger flags the slot", _remove),
    ("the sidecar is a symlink to a valid copy (never followed)", _symlink),
], ids=["tampered-field", "tampered-row", "missing", "symlink"])
def test_y4_freeze_and_harvest_refuse_a_sidecar_that_is_not_what_the_chain_sealed(tmp_path, what, act):
    """(a) Y4 (data validity): both consumers take the ledger's `accounting_fault` flag only with the exact sealed sidecar of
    this slot; a forged, edited, absent or linked one is refused by BOTH (candidate 2's harvest only checked existence)."""
    root, chain, slots = acct_leg(tmp_path)
    act(root, slots)
    freeze, harvest = _problems(root, chain)
    assert freeze, f"freeze accepted: {what}"
    assert harvest, f"harvest accepted: {what}"


def test_y4_a_sidecar_of_the_other_slots_attempt_is_not_this_slots(tmp_path):
    """(b) the binding is per slot AND attempt: a sealed sidecar copied from slot 2 to slot 1's path is refused."""
    root, chain, slots = acct_leg(tmp_path)
    other = ph.accounting_path(root, slots[1], 0)
    ph.write_exclusive(other, dict(slot=slots[1], rerun_index=0, row_sha256=None, item_record_sha256=None,
                                   failed_checks=["x"], disposition="accounting_fault"))
    ph.accounting_path(root, slots[0], 0).unlink()
    ph.accounting_path(root, slots[0], 0).write_text(other.read_text())
    freeze, harvest = _problems(root, chain)
    assert freeze and harvest
