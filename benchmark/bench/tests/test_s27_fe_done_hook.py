"""S27 (spec v1.4, sections 5.3, 5.9, acceptance 10.1) -- blind test-writer, delivery 1: the `done` hook's accounting / integrity
split.  `P426Hooks.after_attempt(slot, done, context)` is driven with a real log, real worker counters and the item record it
writes (`test_b2_s4_reconcile.make_hooks` / `LogOps`).

Class of each test: (a) reproduces a failure the spec fixes, (b) preserves an invariant, (c) exercises new behaviour.

Interface assumptions:
  H1  the new disposition is `chain_hooks.Disposition("accounting_fault", reason=<text>)` (kind named in spec 5.3 / 5.7), and
      `kind` is what the tests compare;
  H2  the sealed sidecar is `<out_root>/items/<slot_file>.accounting.json`, written by the hook before it returns (spec 5.3),
      with the slot, the sha256 of the row, the sha256 of the item record, and the failed checks, found by value: the field
      names are not given, so the tests look for the slot string, a 64-hex row digest under a key mentioning `row`, the item
      record's own `sha256`, and the failed check names;
  H3  the item record carries the late record's `order` (`rec["order"]`) as the report does.
"""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from bench import chain_hooks as ch
from bench import p426_hooks as ph
from bench.tests.test_b2_s4_reconcile import (MODEL, ON_DRAFT, SLOT, SLOT_FILE, completed, make_hooks, req, row_of, started,
                                              ctx)
from bench.tests.test_s27_fe_reconcile import d1, d1_inputs

ACCOUNTING = "accounting_fault"
HEX64 = set("0123456789abcdef")


def item_record(out):
    return json.loads((out / "items" / f"{SLOT_FILE}.json").read_text())


def sidecar_path(out):
    return out / "items" / f"{SLOT_FILE}.accounting.json"


def done(hooks, row, **kw):
    return hooks.after_attempt(SLOT, dict(id="python/a"), ctx(row))


def is_hex64(x):
    return isinstance(x, str) and len(x) == 64 and set(x) <= HEX64


def count_mismatch(tmp_path, arm="ON", **kw):
    """The log holds three completed requests, the row (and the client) two: boundary_count fails, nothing else."""
    ops, hooks, out = make_hooks(tmp_path, arm=arm)
    hooks.before_attempt(SLOT, ctx())
    draft = ON_DRAFT if arm == "ON" else None
    ops.serve(*req(prompt=100, gen=10, draft=draft), *req(prompt=200, gen=5, draft=draft), *req(prompt=300, gen=7, draft=draft))
    return ops, hooks, out


# ------------------------------------------------------------------------------------------------ accounting faults (5.3)
def test_a_genuine_count_mismatch_on_an_item_with_an_outcome_is_an_accounting_fault_and_never_a_rerun(tmp_path):
    """(a) The baseline answers `invalidate` (the leg is INVALID); the spec: outcome kept, no rerun, the leg continues."""
    ops, hooks, out = count_mismatch(tmp_path)
    row = row_of([(100, 10), (200, 5)])
    before = copy.deepcopy(row)
    d = done(hooks, row)
    assert d.kind == ACCOUNTING, d
    assert d.kind not in ("rerun_same_slot", "harness_fault", "invalidate")
    assert row == before, "the outcome (the row) is never touched"
    rec = item_record(out)
    assert rec["verdict"] == "invalid" and any("boundary_count" in p for p in rec["problems"])     # the record keeps the facts


def test_the_accounting_fault_writes_a_sealed_sidecar_naming_the_slot_the_row_the_item_record_and_the_failed_check(tmp_path):
    """(a) H2"""
    ops, hooks, out = count_mismatch(tmp_path)
    row = row_of([(100, 10), (200, 5)])
    done(hooks, row)
    side = json.loads(sidecar_path(out).read_text())
    assert ph.sealed_ok(side), "the sidecar is sealed (self-hash)"
    # v2: bound to the candidate's sidecar (`p426_hooks.write_accounting`): exact where data validity depends on it
    assert side["slot"] == SLOT and side["disposition"] == "accounting_fault"
    assert any("boundary_count" in c for c in side["failed_checks"])
    assert side["item_record_sha256"] == item_record(out)["sha256"]            # the item record's digest
    assert side["row_sha256"] == hashlib.sha256(ph.canonical(row)).hexdigest()    # the row's canonical digest


def test_an_accounting_fault_item_record_is_written_before_the_disposition_and_is_not_overwritten(tmp_path):
    """(b) Immutable records (spec 16): the record exists exclusive-created, a second `done` for the slot cannot replace it."""
    ops, hooks, out = count_mismatch(tmp_path)
    row = row_of([(100, 10), (200, 5)])
    done(hooks, row)
    first = (out / "items" / f"{SLOT_FILE}.json").read_bytes()
    with pytest.raises((FileExistsError, ch.HookInfrastructureError, OSError)):
        done(hooks, row)
    assert (out / "items" / f"{SLOT_FILE}.json").read_bytes() == first


def test_a_token_pairing_mismatch_is_also_an_accounting_fault(tmp_path):
    """(a) spec 5.9: `pairing` -> accounting."""
    ops, hooks, out = make_hooks(tmp_path, arm="ON")
    hooks.before_attempt(SLOT, ctx())
    ops.serve(*req(prompt=100, gen=10, draft=ON_DRAFT))
    d = done(hooks, row_of([(100, 11)]))
    assert d.kind == ACCOUNTING
    assert "pairing" in sidecar_path(out).read_text()


def test_a_settle_failure_stays_integrity_even_beside_a_count_mismatch(tmp_path):
    """(b) 5.3: a failed settle (worker in_flight not 0) -> integrity, HOLD: never an accounting fault."""
    ops, hooks, out = make_hooks(tmp_path, bound=6.0)
    hooks.before_attempt(SLOT, ctx())
    ops.serve(*req(prompt=100, gen=10, draft=ON_DRAFT), started())              # a started line that never terminates
    ops.summary["in_flight"] = 1
    d = done(hooks, row_of([(100, 10), (200, 5)]))
    assert d.kind == "invalidate" and "settle" in d.reason
    assert not sidecar_path(out).exists()


# ------------------------------------------------------------------------------------------------ integrity faults still invalidate (5.5, 5.9)
def test_a_worker_delta_mismatch_beyond_the_late_record_case_is_integrity(tmp_path):
    """(b) The counters of the worker disagree with the log of the same item: INVALID, not an accounting fault."""
    ops, hooks, out = make_hooks(tmp_path, arm="ON")
    hooks.before_attempt(SLOT, ctx())
    ops.serve(*req(prompt=100, gen=10, draft=ON_DRAFT), *req(prompt=200, gen=5, draft=ON_DRAFT))
    ops.summary["requests_completed"] += 1                                       # the worker counted a request the log never shows
    d = done(hooks, row_of([(100, 10), (200, 5)]))
    assert d.kind == "invalidate" and "worker_deltas" in d.reason
    assert not sidecar_path(out).exists()


def test_a_session_backend_mismatch_is_integrity(tmp_path):
    """(b)"""
    ops, hooks, out = make_hooks(tmp_path, arm="ON")
    hooks.before_attempt(SLOT, ctx())
    ops.serve(*req(session="ses_other", prompt=100, gen=10, draft=ON_DRAFT))
    d = done(hooks, row_of([(100, 10)], session="ses_1"))
    assert d.kind == "invalidate" and "session_backend" in d.reason


def test_a_serial_violation_is_integrity(tmp_path):
    """(b) two requests in flight at once."""
    ops, hooks, out = make_hooks(tmp_path, arm="ON")
    hooks.before_attempt(SLOT, ctx())
    from bench.tests.test_b2_s4_reconcile import completed as c
    ops.serve(started(in_flight=2), c(prompt=100, gen=10, draft=ON_DRAFT))
    d = done(hooks, row_of([(100, 10)]))
    assert d.kind == "invalidate" and "serial" in d.reason


def test_an_engagement_failure_is_integrity_because_it_is_not_in_the_accounting_table(tmp_path):
    """(b) 5.9: 'any check not in this table -> integrity'."""
    ops, hooks, out = make_hooks(tmp_path, arm="OFF")
    hooks.before_attempt(SLOT, ctx())
    ops.serve(*req(prompt=100, gen=10, draft=ON_DRAFT))                          # an OFF arm that carries draft counters
    d = done(hooks, row_of([(100, 10)]))
    assert d.kind == "invalidate" and "engagement" in d.reason


def test_a_count_mismatch_beside_an_integrity_failure_is_integrity(tmp_path):
    """(b) The accounting classification needs EVERY failed check to be an accounting check."""
    ops, hooks, out = count_mismatch(tmp_path)
    ops.summary["requests_completed"] += 1
    d = done(hooks, row_of([(100, 10), (200, 5)]))
    assert d.kind == "invalidate"
    assert not sidecar_path(out).exists()


def test_an_unreadable_window_or_a_replaced_log_stays_integrity(tmp_path):
    """(b) preconditions: a missing ready record."""
    ops, hooks, out = make_hooks(tmp_path)
    d = done(hooks, row_of([(100, 10)]))
    assert d.kind == "invalidate" and "ready record" in d.reason


# ------------------------------------------------------------------------------------------------ the recorded D1 case through the hook
def test_the_recorded_d1_item_is_reconciled_by_the_hook_and_the_item_record_carries_the_late_record(tmp_path):
    """(a) The recorded numbers, through the whole done hook (log window, worker counters, record): accepted; the item record is
    `kill_boundary_late_record` of order `unpublished` (H3)."""
    fx = d1()
    row, lines, before, after = d1_inputs(fx)
    ops, hooks, out = make_hooks(tmp_path, arm="OFF")
    ops.summary = dict(before)
    hooks.before_attempt(SLOT, ctx())
    raw = []
    for prompt, gen in fx["request_usage_prompt_generated"]:
        raw += [started(), completed(fx["session_id"], prompt, gen)]
    ops.serve(*raw)
    d = hooks.after_attempt(SLOT, dict(id="java/sgf-parsing"), ctx(row))
    assert d.kind == "accept", d
    rec = item_record(out)
    assert rec["verdict"] == "reconciled" and rec["case"] == "kill_boundary_late_record"
    assert rec.get("order") == "unpublished"
    assert rec["totals"]["requests"] == 26 and rec["totals"]["generated_tokens"] == 4117
    assert not sidecar_path(out).exists()
