"""S27 §4.1 / §4.2 / §5.9: the kill-boundary race reconciled in either order (`kill_boundary_late_record`, the offset shape and
the v1.4 `unpublished` shape on the recorded D1 numbers) and the closed accounting / integrity table."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from bench import p426_reconcile as pr
from bench import token_turn_gate as tg

FIXTURE = Path(__file__).parent / "fixtures" / "s27_impl" / "sgf_parsing_d1.json"


def d1():
    return json.loads(FIXTURE.read_text())


def log_lines(doc, *, trailing_failed=False, session=None):
    out = []
    for gen, prompt in doc["requests"]:
        out.append("2026-11-19 18:07:24,284 INFO Request started: in_flight=1")
        out.append(f"2026-11-19 18:07:28,071 INFO Request completed: session={session or doc['session_id']} "
                   f"backend={pr.BACKEND} prompt_tokens={prompt} generated_tokens={gen} decode={gen / 3:.1f}")
    if trailing_failed:
        out.append("2026-11-19 18:07:29,000 INFO Request started: in_flight=1")
        out.append(f"2026-11-19 18:07:29,500 INFO Request failed: error={pr.STREAM_CLOSED} in_flight=0")
    return pr.parse_log(("\n".join(out) + "\n").encode())


def row_of(doc):
    usage = [[f"msg_{k:02d}", gen, prompt, 81920] for k, (gen, prompt) in enumerate(doc["requests"], 1)]
    return dict(session_id=doc["session_id"], request_usage=usage, gate=dict(doc["gate"]),
                termination=copy.deepcopy(doc["termination"]), reconciliation=dict(doc["reconciliation"]),
                event_types_seen=dict(doc["event_types_seen"]), requests_observed=doc["requests_observed"],
                nonconv_kind=doc["nonconv_kind"])


def after_with(doc, **delta):
    a = dict(doc["worker_after"])
    a.update(delta)
    return a


# -------------------------------------------------------------------------------- the recorded D1 case (v1.4 shape)
def test_the_recorded_sgf_parsing_numbers_are_a_kill_boundary_late_record_unpublished():
    doc = d1()
    report = pr.reconcile_item(row_of(doc), log_lines(doc), doc["worker_before"], doc["worker_after"])
    assert report.ok, report.problems
    assert report.case == pr.LATE_RECORD and report.order == "unpublished" and report.signal_order is None
    assert report.late_record["message_id"] == "msg_26" and report.late_record["in_flight_at_kill"] == 0
    assert pr.fault_class(report.checks) is None


def test_before_s27_the_same_numbers_were_a_boundary_count_mismatch():
    """Without the late-record facts (no row facts: a plain reconcile) the count mismatch is the item's accounting."""
    doc = d1()
    report = pr._reconcile(usage=row_of(doc)["request_usage"], session=doc["session_id"], lines=log_lines(doc),
                           before=doc["worker_before"], after=doc["worker_after"], kind="kill", killed=True, expected=25,
                           inflight_possible=False)
    assert not report.ok and report.case == "kill_boundary" and pr.fault_class(report.checks) == "accounting"


@pytest.mark.parametrize("edit", [
    lambda r: r["termination"].update(in_flight_at_kill=1),
    lambda r: r["termination"]["worker_summary_after"].update(in_flight=1),
    lambda r: r["reconciliation"].update(trailing="interrupted"),
    lambda r: r["reconciliation"].update(unmatched_export_messages=2),
    lambda r: r["event_types_seen"].update(step_finish=26),
    lambda r: r["event_types_seen"].update(error=2),
    lambda r: r.update(requests_observed=27),
    lambda r: r["termination"].update(last_step_start="msg_other"),
    lambda r: r["request_usage"][-1].__setitem__(1, 115),           # the 26th entry no longer pairs with the worker's 26th
])
def test_the_unpublished_shape_needs_every_one_of_its_facts(edit):
    doc = d1()
    row = row_of(doc)
    edit(row)
    report = pr.reconcile_item(row, log_lines(doc), doc["worker_before"], doc["worker_after"])
    assert report.case != pr.LATE_RECORD and not report.ok


def test_the_unpublished_shape_accepts_a_matching_last_step_start():
    doc = d1()
    row = row_of(doc)
    row["termination"]["last_step_start"] = "msg_26"
    assert pr.reconcile_item(row, log_lines(doc), doc["worker_before"], doc["worker_after"]).ok


# -------------------------------------------------------------------------------- the offset shape (§4.1 / §4.2)
def offset_row(doc, *, end, ingested, size=None, signal=None):
    row = row_of(doc)
    row["event_types_seen"]["step_finish"] = 26
    row["reconciliation"] = dict(unmatched_export_messages=0, trailing="none")
    ends = [1000 * k for k in range(1, 26)] + [end]
    row["termination"].update(step_end_offsets=ends, ingested_offset_at_count=ingested, events_size_at_count=size,
                              signal_offset=signal)
    return row


@pytest.mark.parametrize("signal, want", [(None, "no_signal"), (40000, "before_signal"), (30000, "after_signal")])
def test_the_ingest_lag_order_is_a_late_record_with_its_signal_order_recorded(signal, want):
    """The 26th step's bytes were written before the count (`events_size_at_count` past them) but ingested after it."""
    doc = d1()
    row = offset_row(doc, end=35000, ingested=25000, size=36000, signal=signal)
    report = pr.reconcile_item(row, log_lines(doc), doc["worker_before"], doc["worker_after"])
    assert report.ok, report.problems
    assert report.case == pr.LATE_RECORD and report.order == "step_after_count" and report.signal_order == want
    assert report.late_record["step_end_offset"] == 35000 and report.late_record["ingested_offset_at_count"] == 25000


def test_a_step_ingested_before_the_count_is_no_late_record():
    doc = d1()
    report = pr.reconcile_item(offset_row(doc, end=20000, ingested=25000), log_lines(doc), doc["worker_before"],
                               doc["worker_after"])
    assert not report.ok and report.case == "kill_boundary"


def test_the_trailing_failed_variant_is_a_late_record():
    """The client had started the next request: one trailing STREAM_CLOSED failed line, |S| = |C| + 1."""
    doc = d1()
    row = offset_row(doc, end=35000, ingested=25000, signal=40000)
    after = after_with(doc, requests_started=550, requests_failed=1)
    report = pr.reconcile_item(row, log_lines(doc, trailing_failed=True), doc["worker_before"], after)
    assert report.ok, report.problems
    assert report.case == pr.LATE_RECORD and report.late_record["trailing_failed"] is True


def test_the_existing_kill_boundary_records_step_before_count():
    doc = d1()
    row = row_of(doc)
    row["request_usage"] = row["request_usage"][:25]
    row["gate"]["requests_completed_at_kill"] = 25
    lines = log_lines(dict(doc, requests=doc["requests"][:25]))
    after = after_with(doc, requests_started=548, requests_completed=548, prompt_tokens_total=6432708 - 14579,
                       generated_tokens_total=338294 - 114)
    report = pr.reconcile_item(row, lines, doc["worker_before"], after)
    assert report.ok and report.case == "kill_boundary" and report.order == "step_before_count"


# -------------------------------------------------------------------------------- §5.9 the closed table
def test_a_genuine_count_mismatch_on_an_item_with_an_outcome_is_accounting():
    doc = d1()
    row = row_of(doc)
    row["termination"].update(in_flight_at_kill=1)                 # not the late-record race
    report = pr.reconcile_item(row, log_lines(doc), doc["worker_before"], doc["worker_after"])
    assert not report.ok and pr.fault_class(report.checks) == "accounting"


def test_a_worker_delta_mismatch_beyond_the_late_record_case_is_integrity():
    doc = d1()
    after = after_with(doc, generated_tokens_total=338294 + 7)
    report = pr.reconcile_item(row_of(doc), log_lines(doc), doc["worker_before"], after)
    assert not report.ok and pr.fault_class(report.checks) == "integrity"


@pytest.mark.parametrize("failed, want", [
    ({"boundary_count"}, "accounting"), ({"pairing", "unaccounted_count"}, "accounting"),
    ({"serial"}, "integrity"), ({"session_backend"}, "integrity"), ({"started_terminated"}, "integrity"),
    ({"failed_lines"}, "integrity"), ({"worker_deltas"}, "integrity"), ({"pairing", "worker_deltas"}, "integrity"),
    ({"preconditions"}, "integrity"), ({"something_new"}, "integrity"), (set(), None)])
def test_the_closed_accounting_integrity_table(failed, want):
    checks = {n: dict(ok=n not in failed) for n in {"boundary_count", "pairing", "serial"} | failed}
    assert pr.fault_class(checks) == want


# -------------------------------------------------------------------------------- §4.1 the step END offsets
def test_the_stream_records_each_step_finish_end_offset():
    gate = tg.TokenTurnGate(1)
    s = tg.EventStream(gate)
    tokens = dict(output=1, reasoning=0, input=10, cache=dict(read=0, write=0))
    lines = [dict(type="step_start", sessionID="s", part=dict(id="a", messageID="m1")),
             dict(type="step_finish", sessionID="s", part=dict(id="b", messageID="m1", tokens=tokens))]
    data = b"".join((json.dumps(x) + "\n").encode() for x in lines)
    s.feed(data)
    assert s.step_end_offsets == [len(data)] and s.offset == len(data)


def test_the_interrupt_stop_is_a_kill_outcome_and_never_a_nonconv_kind():
    assert "interrupt" in tg.KILL_OUTCOMES and "interrupt" not in tg.PRECEDENCE
