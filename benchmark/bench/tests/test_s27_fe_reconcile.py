"""S27 (spec v1.4, section 4.1-4.2, 5.9) -- blind test-writer, delivery 1: order-tolerant per-item reconciliation.

Drives `p426_reconcile.reconcile_item(row, lines, before, after)` (the reconciler's public function) with the real row /
log / worker shapes.  The recorded `java/sgf-parsing` case (spec 10.2) is read from a sha-pinned fixture.

Class of each test: (a) reproduces a failure the spec fixes, (b) preserves an invariant, (c) exercises new behaviour.

Interface assumptions (the spec names the values, not every call shape):
  A1  the new case string is `ItemReport.case == "kill_boundary_late_record"`, and `ItemReport.order` carries the
      `order` value (`"unpublished"`, `"step_after_count"`, and for the old case `"step_before_count"`);
  A2  (v2, bound to the candidate) the relation to the SIGTERM is `ItemReport.signal_order`
      (`before_signal` / `after_signal` / `no_signal`);
  A3  (v2) the step END offsets are `row["termination"]["step_end_offsets"]` (one int per completed request, the byte just
      past the `step_finish` line), the count-time positions are `row["termination"]["ingested_offset_at_count"]`,
      `["events_size_at_count"]` and `["signal_offset"]` (names from spec 4.1);
  A4  a check that is not accepted is visible in `ItemReport.checks[name]["ok"]` under the baseline's check names.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from bench import p426_reconcile as pr
from bench.tests.test_b2_s4_reconcile import BEFORE, STREAM_CLOSED, completed, failed, lines_of, started

FIXTURE = Path(__file__).parent / "fixtures" / "s27_fe" / "sgf_parsing_d1.json"
FIXTURE_SHA256 = "73f1b2cf61c4d3532b4d3a9862bd2884e3660217fd558b6b5e95b7da917a3aa9"      # v3: + termination.last_step_start (X9)
LATE = "kill_boundary_late_record"


# ------------------------------------------------------------------------------------------------ helpers
def d1():
    data = FIXTURE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == FIXTURE_SHA256, "the pinned fixture changed"
    return json.loads(data)


def strings_in(obj):
    """Every string VALUE anywhere in a report (A2: the field that carries the signal relation is not named)."""
    doc = dataclasses.asdict(obj) if dataclasses.is_dataclass(obj) else obj
    out, stack = set(), [doc]
    while stack:
        x = stack.pop()
        if isinstance(x, str):
            out.add(x)
        elif isinstance(x, dict):
            stack.extend(x.values())
        elif isinstance(x, (list, tuple)):
            stack.extend(x)
    return out


def failed_checks(rep):
    return {name for name, c in rep.checks.items() if not c["ok"]}


def d1_inputs(fx=None, *, usage_edit=None, row_edit=None, after_edit=None, extra_lines=()):
    fx = fx or d1()
    pairs = [tuple(p) for p in fx["request_usage_prompt_generated"]]
    raw = []
    for prompt, gen in pairs:
        raw += [started(), completed(fx["session_id"], prompt, gen)]
    raw += list(extra_lines)
    lines = lines_of(*raw)
    usage = [[f"msg_{i + 1:02d}", g, p, 81920] for i, (p, g) in enumerate(pairs)]
    usage[-1][0] = fx["row"]["termination"]["last_step_start"]        # v3 (X9): the real open step's id from the recorded stream
    if usage_edit:
        usage_edit(usage)
    row = dict(id="java/sgf-parsing", session_id=fx["session_id"], request_usage=usage, **copy.deepcopy(fx["row"]))
    if row_edit:
        row_edit(row)
    after = dict(fx["worker_after"])
    if after_edit:
        after_edit(after)
    return row, lines, dict(fx["worker_before"]), after


def ingest_case(*, n=3, at_kill=None, tail=None, ends=None, ingested=250, events_size=350, signal=None,
                in_flight_at_kill=0, worker_over=None, kill=True):
    """The first shape (the n-th step_finish exists): n requests completed on the worker, the stream's count at the kill
    decision was `at_kill` (default n - 1), the n-th step ended at `ends[-1]`."""
    ends = list(ends or [100 * (i + 1) for i in range(n)])
    at_kill = n - 1 if at_kill is None else at_kill
    session = "ses_s27fe"
    raw = []
    for i in range(n):
        raw += [started(), completed(session, 1000 + i, 10 + i)]
    if tail == "failed":                                          # the client had started the next request: it failed on the kill
        raw += [started(), failed(STREAM_CLOSED)]
    elif tail == "failed_other_error":
        raw += [started(), failed("boom")]
    elif tail == "two_failed":
        raw += [started(), failed(STREAM_CLOSED), started(), failed(STREAM_CLOSED)]
    elif tail == "failed_not_last":
        raw += [started(), failed(STREAM_CLOSED), started(), completed(session, 5000, 5)]
    lines = lines_of(*raw)
    c = [x for x in lines if x.kind == "completed"]
    f = [x for x in lines if x.kind == "failed"]
    s = [x for x in lines if x.kind == "started"]
    before = dict(BEFORE)
    after = dict(before, requests_started=before["requests_started"] + len(s),
                 requests_completed=before["requests_completed"] + len(c),
                 requests_failed=before["requests_failed"] + len(f),
                 prompt_tokens_total=before["prompt_tokens_total"] + sum(int(x.fields["prompt_tokens"]) for x in c),
                 generated_tokens_total=before["generated_tokens_total"] + sum(int(x.fields["generated_tokens"]) for x in c))
    after.update(worker_over or {})
    usage = [[f"m{i + 1}", 10 + i, 1000 + i, 81920] for i in range(n)]
    term = dict(reason="looping" if kill else None, killed_verified=True, in_flight_at_kill=in_flight_at_kill,
                requests_at_kill=at_kill, ingested_offset_at_count=ingested, events_size_at_count=events_size,
                signal_offset=signal, step_end_offsets=ends)
    if not kill:
        term = {}                                   # no kill marker of any kind: the item is reconciled as a completed one
    row = dict(id="python/a", session_id=session, request_usage=usage, nonconv_kind="looping" if kill else None,
               gate=dict(requests_completed=n, requests_completed_at_kill=at_kill if kill else None),
               termination=term, reconciliation=dict(unmatched_export_messages=0, trailing="interrupted"))
    return row, lines, before, after


def reconcile(case):
    row, lines, before, after = case
    return pr.reconcile_item(row, lines, before, after)


# ------------------------------------------------------------------------------------------------ the recorded D1 case
def test_the_pinned_fixture_is_the_recorded_case():
    """(b) The fixture is the recorded item: 26 requests, the recorded totals, 25 step_finish lines, the kill count 25."""
    fx = d1()
    pairs = fx["request_usage_prompt_generated"]
    assert len(pairs) == 26 and sum(p for p, _ in pairs) == 265232 and sum(g for _, g in pairs) == 4117
    assert fx["row"]["event_types_seen"]["step_finish"] == 25 and fx["row"]["gate"]["requests_completed_at_kill"] == 25
    assert fx["worker_after"]["requests_started"] - fx["worker_before"]["requests_started"] == 26


def test_d1_the_recorded_numbers_are_a_late_record_of_the_unpublished_order():
    """(a) The baseline refuses these exact numbers with `boundary_count: |C|=26, len(request_usage)=26, the evidence states 25`."""
    rep = pr.reconcile_item(*d1_inputs())
    assert rep.ok, rep.problems
    assert rep.case == LATE and rep.order == "unpublished"
    assert rep.problems == [] and failed_checks(rep) == set()


@pytest.mark.parametrize("what, edit", [
    ("the trailing message was interrupted, not unpublished", dict(row_edit=lambda r: r["reconciliation"].update(trailing="interrupted"))),
    ("a second unmatched export message", dict(row_edit=lambda r: r["reconciliation"].update(unmatched_export_messages=2))),
    ("a request was in flight at the kill", dict(row_edit=lambda r: r["termination"].update(in_flight_at_kill=1))),
    ("the worker still shows a request in flight", dict(after_edit=lambda a: a.update(in_flight=1))),
    ("the trailing message is final, not unpublished", dict(row_edit=lambda r: r["reconciliation"].update(trailing="final"))),
])
def test_d1_variants_that_leave_the_late_record_explanation_are_still_refused(what, edit):
    """(b) No check that protects the measured outcome is weakened: each broken premise of the second shape is refused."""
    rep = pr.reconcile_item(*d1_inputs(**edit))
    assert not rep.ok and rep.case != LATE, what
    assert rep.problems, what


def test_d1_a_worker_that_completed_fewer_requests_than_the_log_is_an_integrity_fault():
    """(b) worker deltas beyond the late-record explanation: the counters disagree with the log."""
    rep = pr.reconcile_item(*d1_inputs(after_edit=lambda a: a.update(requests_completed=548)))
    assert not rep.ok and "worker_deltas" in failed_checks(rep)          # v2: the intent is the refusal, not the case label


def test_d1_a_worker_that_started_fewer_requests_than_the_log_is_an_integrity_fault():
    rep = pr.reconcile_item(*d1_inputs(after_edit=lambda a: a.update(requests_started=548)))
    assert not rep.ok and "worker_deltas" in failed_checks(rep)


@pytest.mark.parametrize("position", [0, 12, 25])
def test_d1_positional_pairing_must_hold_on_all_n_entries(position):
    """(b) The n-th entry pairs with the worker's n-th completion, and so does every other one."""
    def edit(usage):
        usage[position][1] += 1
    rep = pr.reconcile_item(*d1_inputs(usage_edit=edit))
    assert not rep.ok and "pairing" in failed_checks(rep) and rep.case != LATE


def test_d1_with_a_failed_line_and_a_started_next_request_is_not_the_unpublished_shape():
    """(b) The second shape needs |S| == |C| == n and no failed line; a failed 27th request is another story (and its
    n-th step_finish is absent, so the first shape cannot hold either)."""
    rep = pr.reconcile_item(*d1_inputs(extra_lines=[started(), failed(STREAM_CLOSED)],
                                       after_edit=lambda a: a.update(requests_started=550, requests_failed=1)))
    assert not rep.ok and rep.case != LATE


@pytest.mark.parametrize("what, edit", [
    ("the stream's last step_start id is missing", lambda r: r["termination"].pop("last_step_start")),
    ("the stream's last step_start id is null", lambda r: r["termination"].update(last_step_start=None)),
    ("the stream's last step_start id is another step's", lambda r: r["termination"].update(last_step_start="msg_1f6b55ed0001OTHER")),
    ("the stream's last step_start id is not a string", lambda r: r["termination"].update(last_step_start=26)),
])
def test_d1_the_unpublished_shape_needs_the_recovered_message_to_be_the_streams_open_step(what, edit):
    """(b) v3 (X9, spec 4.2 / C375): the n-th request_usage entry must be the stream's last `step_start`; a missing or differing
    id is not this case (it was waived in candidate 1 when the id was absent: checked by inspection of the fix diff)."""
    rep = pr.reconcile_item(*d1_inputs(row_edit=edit))
    assert not rep.ok and rep.case != LATE, what


def test_d1_the_offsets_are_recorded_but_not_required_for_the_unpublished_shape():
    """(c) spec 4.2: the second shape is accepted without any offset in the row (the recorded row has none)."""
    row, lines, before, after = d1_inputs()
    assert "step_end_offsets" not in row["termination"] and "ingested_offset_at_count" not in row["termination"]
    assert pr.reconcile_item(row, lines, before, after).ok


# ------------------------------------------------------------------------------------------------ the first shape (step_finish present)
def test_the_ingest_lag_order_is_a_late_record_step_bytes_before_the_count_ingested_after():
    """(a) The n-th step's bytes were already in the file when the count was read (events_size_at_count 350 >= end 300), but
    it was ingested after (end 300 > ingested 250): the baseline reports boundary_count |C|=3 != 2."""
    rep = reconcile(ingest_case(ends=[100, 200, 300], ingested=250, events_size=350))
    assert rep.ok, rep.problems
    assert rep.case == LATE and rep.order == "step_after_count"


def test_the_step_written_after_the_count_is_the_same_late_record():
    """(c) 'whether its bytes were written before or after': the file was still short of the step when the count was read."""
    rep = reconcile(ingest_case(ends=[100, 200, 300], ingested=250, events_size=260))
    assert rep.ok, rep.problems
    assert rep.case == LATE and rep.order == "step_after_count"


def test_the_signal_relation_is_recorded_from_signal_offset():
    """(c) A2: before_signal when the n-th step ended at or before the SIGTERM position, after_signal when past it, no_signal
    when no signal was delivered (signal_offset None)."""
    after_signal = reconcile(ingest_case(ends=[100, 200, 300], signal=290))
    before_signal = reconcile(ingest_case(ends=[100, 200, 300], signal=320))
    no_signal = reconcile(ingest_case(ends=[100, 200, 300], signal=None))
    assert after_signal.ok and after_signal.signal_order == "after_signal"
    assert before_signal.ok and before_signal.signal_order == "before_signal"
    assert no_signal.ok and no_signal.signal_order == "no_signal"


def test_a_step_already_ingested_when_the_count_was_read_is_a_genuine_mismatch():
    """(b) |C| == n == expected + 1 but the n-th step ended at or before the ingested position: the count should have
    included it, so the evidence disagrees with itself and the item is not accepted."""
    rep = reconcile(ingest_case(ends=[100, 200, 300], ingested=300))
    assert not rep.ok and "boundary_count" in failed_checks(rep) and rep.case != LATE
    rep = reconcile(ingest_case(ends=[100, 200, 300], ingested=999))
    assert not rep.ok and "boundary_count" in failed_checks(rep)


def test_without_the_recorded_step_offsets_the_first_shape_cannot_be_shown():
    """(b) Fail closed: no step end offsets in the row, nothing to prove the step was ingested after the count."""
    case = ingest_case()
    case[0]["termination"].pop("step_end_offsets")
    rep = reconcile(case)
    assert not rep.ok and rep.case != LATE


def test_the_trailing_failed_variant_is_a_late_record():
    """(a) exactly one trailing failed line (STREAM_CLOSED, last), |S| == |C| + 1: the client had started the next request."""
    rep = reconcile(ingest_case(tail="failed", in_flight_at_kill=1))
    assert rep.ok, rep.problems
    assert rep.case == LATE and rep.order == "step_after_count"


@pytest.mark.parametrize("tail", ["failed_other_error", "two_failed", "failed_not_last"])
def test_other_failed_line_shapes_are_not_late_records(tail):
    """(b) `failed_lines` beyond the allowed variants stay refused."""
    rep = reconcile(ingest_case(tail=tail, in_flight_at_kill=1))
    assert not rep.ok and rep.case != LATE


def test_a_late_record_with_a_worker_delta_mismatch_is_refused():
    """(b) 'worker deltas hold' is part of the late-record condition."""
    rep = reconcile(ingest_case(worker_over=dict(requests_completed=BEFORE["requests_completed"] + 2)))
    assert not rep.ok and "worker_deltas" in failed_checks(rep)


def test_a_late_record_needs_a_kill_a_completed_item_with_one_extra_completion_is_refused():
    """(b) Without a kill marker the item is reconciled as a completed one: |C| == n + 1 stays a count mismatch."""
    case = ingest_case(kill=False)
    case[0]["request_usage"] = case[0]["request_usage"][:-1]
    rep = reconcile(case)
    assert not rep.ok and rep.case != LATE and "boundary_count" in failed_checks(rep)


def test_the_late_record_cannot_excuse_more_than_one_extra_step():
    """(b) |C| == n == expected + 2 is not 'the step ingested after the count'."""
    rep = reconcile(ingest_case(n=3, at_kill=1, ends=[100, 200, 300], ingested=150))
    assert not rep.ok and rep.case != LATE


# ------------------------------------------------------------------------------------------------ the unchanged boundary case
def test_the_existing_kill_boundary_records_step_before_count():
    """(c) spec 4.2: `kill_boundary` (the count equals the stream's) records order step_before_count and stays that case."""
    rep = reconcile(ingest_case(at_kill=3, ends=[100, 200, 300], ingested=400, events_size=400))
    assert rep.ok, rep.problems
    assert rep.case == "kill_boundary" and rep.order == "step_before_count"


# ------------------------------------------------------------------------------------------------ the closed table (spec 5.9), reconciler side
def test_a_genuine_count_mismatch_fails_only_the_accounting_checks():
    """(b) |C| == n == 3 but the kill decision saw 1: boundary_count (an accounting check) and nothing of the integrity set."""
    rep = reconcile(ingest_case(n=3, at_kill=1, ends=[100, 200, 300], ingested=400))
    assert not rep.ok
    assert failed_checks(rep) == {"boundary_count"}


@pytest.mark.parametrize("mutation, check", [
    (lambda c: c[0].update(session_id="ses_other"), "session_backend"),
    (lambda c: c[3].update(requests_failed=c[3]["requests_failed"] + 1), "worker_deltas"),
])
def test_the_integrity_checks_still_fail_on_their_own(mutation, check):
    """(b) serial / session_backend / worker_deltas keep failing (the hook classifies them as integrity)."""
    case = list(ingest_case(n=3, at_kill=3, ends=[100, 200, 300], ingested=400))
    mutation(case)
    rep = reconcile(tuple(case))
    assert check in failed_checks(rep)
