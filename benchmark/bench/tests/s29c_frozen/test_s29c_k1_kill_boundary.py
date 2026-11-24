"""S29c K1 (acceptance 4): the kill-boundary race is the item's own accounting, not an INTEGRITY fault.

The recorded shape is S29-P16 `tg2-m76-n16-s2.a1` javascript/zebra-puzzle (`fixtures/s29_p16_shape.json`: the row's `termination`,
`reconciliation` and `request_usage`, copied from `.fe-material/s29-p16-shape.json`): 40 completed requests, the harness SIGTERMs the
client at `signal_at`, the worker's kill-time summaries read started +1 / failed +1 / completed +0, nothing in flight at the
pre-signal sample, the failure (`stream_closed_before_completion`) recorded at / after the signal.

What the tests run: `p426_reconcile.reconcile_item(row, lines, before, after)` - the per-item reconciliation `p426_hooks` runs at
every item's end - over a server-log window built from the recorded request_usage and the item-window worker snapshots derived
from the recorded kill-time summaries; the verdict is read through `p426_reconcile.fault_class` (the function the hook uses to pick
`Disposition.accounting_fault` vs `invalidate`). The hook's own disposition path (sidecar writing) is not run here.
Not in the recorded shape and therefore ASSUMED by the fixture: the row's `session_id` ("ses_k1"), `gate.requests_completed(_at_kill)`
= 40, `event_types_seen` step_start / step_finish = 40, and the per-item `before` snapshot (the kill-time `after` summary minus the
window's own 41 starts / 40 completions / their tokens).
Classes: [FIX] fails on the baseline (class `integrity`); [INV] holds on the baseline; the shapes outside K1 must keep today's class."""
from __future__ import annotations

import copy
import json

import pytest

from bench import p426_reconcile as pr
from bench.tests.s29c_frozen import s29c_support as S

SES = "ses_k1"
SHAPE = json.loads(S.SHAPE.read_text())
USAGE = SHAPE["request_usage"]
N = len(USAGE)


def _text(kind, **fields):
    body = " ".join(f"{k}={v}" for k, v in fields.items())
    return f"2026-11-14 10:00:00,000 INFO mlx_vlm.server Request {kind}: {body}"


def _log(*, started_last=True, extra_completed=False, failed=True, failed_uid=1):
    lines = []
    for _id, gen, prompt, _budget in USAGE:
        lines.append(_text("started", uid=1, in_flight=1))
        lines.append(_text("completed", session=SES, backend="cached_session", prompt_tokens=prompt, generated_tokens=gen,
                           cached_tokens=0, decode=30.0, elapsed="2.0s", in_flight=0))
    if extra_completed:
        lines.append(_text("started", uid=1, in_flight=1))
        lines.append(_text("completed", session=SES, backend="cached_session", prompt_tokens=100, generated_tokens=100,
                           cached_tokens=0, decode=30.0, elapsed="2.0s", in_flight=0))
    else:
        if started_last:
            lines.append(_text("started", uid=1, in_flight=1))
        if failed:
            lines.append(_text("failed", uid=failed_uid, error=pr.STREAM_CLOSED, in_flight=0))
    return pr.parse_log(("\n".join(lines) + "\n").encode())


def build(*, kill_started=1, kill_failed=1, kill_completed=0, in_flight_at_kill=0, failed_before_signal=False,
          extra_completed=False, started_last=True, failed=True, failed_uid=1):
    """(row, lines, before, after) of the recorded shape, with the kill-time worker deltas and the log window parameterised."""
    term = copy.deepcopy(SHAPE["termination"])
    b, a = term["worker_summary_before"], term["worker_summary_after"]
    a["requests_started"] = b["requests_started"] + kill_started
    a["requests_failed"] = b["requests_failed"] + kill_failed
    a["requests_completed"] = b["requests_completed"] + kill_completed
    if kill_failed == 0:
        a["last_error"] = None
    if failed_before_signal:
        a["last_error"] = dict(a["last_error"], timestamp_unix=term["signal_at"] - 3.0)
    term["in_flight_at_kill"] = in_flight_at_kill
    b["in_flight"] = in_flight_at_kill
    row = dict(session_id=SES, request_usage=copy.deepcopy(USAGE), gate=dict(requests_completed=N, requests_completed_at_kill=N),
               termination=term, reconciliation=copy.deepcopy(SHAPE["reconciliation"]),
               event_types_seen=dict(step_start=N, step_finish=N))
    lines = _log(started_last=started_last, extra_completed=extra_completed, failed=failed, failed_uid=failed_uid)
    # the item window's own deltas: the kill-time `after` summary minus this window's starts / completions / tokens
    before = dict(a)
    n_started = sum(1 for x in lines if x.kind == "started")
    n_completed = sum(1 for x in lines if x.kind == "completed")
    n_failed = sum(1 for x in lines if x.kind == "failed")
    done = [x for x in lines if x.kind == "completed"]
    before.update(requests_started=a["requests_started"] - n_started, requests_completed=a["requests_completed"] - n_completed,
                  requests_failed=a["requests_failed"] - n_failed, in_flight=0,
                  prompt_tokens_total=a["prompt_tokens_total"] - sum(int(x.fields["prompt_tokens"]) for x in done),
                  generated_tokens_total=a["generated_tokens_total"] - sum(int(x.fields["generated_tokens"]) for x in done))
    return row, lines, before, a


def verdict(**kw):
    row, lines, before, after = build(**kw)
    report = pr.reconcile_item(row, lines, before, after)
    return report, pr.fault_class(report.checks)


def test_instrument_the_fixture_is_the_recorded_shape():
    """[INV] the fixture matches what the shape file records (so the verdicts below are about THAT shape)."""
    term = SHAPE["termination"]
    b, a = term["worker_summary_before"], term["worker_summary_after"]
    assert N == 40 == term["requests_at_kill"] and term["in_flight_at_kill"] == 0 and term["reason"] == "stalled"
    assert (a["requests_started"] - b["requests_started"], a["requests_failed"] - b["requests_failed"],
            a["requests_completed"] - b["requests_completed"]) == (1, 1, 0)
    assert a["last_error"]["error"] == pr.STREAM_CLOSED and a["last_error"]["timestamp_unix"] >= term["signal_at"]
    row, lines, before, after = build()
    assert [x.kind for x in lines].count("completed") == N and lines[-1].kind == "failed"
    report = pr.reconcile_item(row, lines, before, after)
    assert report.checks["worker_deltas"]["ok"] and report.checks["pairing"]["ok"] and report.checks["serial"]["ok"], report.problems


def test_k1_the_recorded_shape_is_the_items_own_accounting():
    """[FIX] acceptance 4: a kill with exactly one trailing failed request of the item's own session (started +1, failed +1,
    completed +0, nothing in flight at the pre-signal sample, failure at / after the signal) is the `accounting` class - recorded,
    never `integrity` - and is not reconciled silently either."""
    report, klass = verdict()
    assert klass == "accounting", (klass, report.problems, sorted(report.checks))
    assert report.ok is False, "the item's own accounting is RECORDED (the accounting_fault class), not reconciled as clean"


def test_k1_only_accounting_checks_fail_for_the_recorded_shape():
    """[FIX] ... and what fails is an accounting check of the closed table (`ACCOUNTING_CHECKS`), nothing else."""
    report, _ = verdict()
    failed = {n for n, c in report.checks.items() if not c["ok"]}
    assert failed and failed <= set(pr.ACCOUNTING_CHECKS), failed


@pytest.mark.parametrize("name,kw", [
    ("a failed request with nothing started (started +0, no start line)", dict(kill_started=0, started_last=False)),
    ("a completed-count change (a 41st completed request, no failed one)", dict(kill_started=1, kill_failed=0, kill_completed=1,
                                                                              extra_completed=True)),
    ("the failure recorded before the signal", dict(failed_before_signal=True)),
    ("two failed requests", dict(kill_failed=2)),
])
def test_k1_shapes_outside_k1_keep_todays_integrity_class(name, kw):
    """[INV] a shape outside K1 stays INTEGRITY (the baseline class), however it is reached."""
    row, lines, before, after = build(**kw)
    report = pr.reconcile_item(row, lines, before, after)
    assert pr.fault_class(report.checks) == "integrity", (name, report.problems)


def test_k1_a_request_in_flight_at_the_pre_signal_sample_is_todays_accepted_case():
    """[INV] with a request in flight at the pre-signal sample the trailing failure is that request's: reconciled as today (the
    existing `kill_inflight_failed` case), neither integrity nor the new class."""
    report, klass = verdict(in_flight_at_kill=1)
    assert klass is None and report.ok and report.case == "kill_inflight_failed", (report.case, klass, report.problems)


def test_k1_a_failed_request_without_the_kill_markers_is_not_a_kill():
    """[INV] the same window on a row with no kill marker (a completed item with a failed request) is not K1: integrity."""
    row, lines, before, after = build()
    for key in ("in_flight_at_kill", "reason"):
        row["termination"].pop(key, None)
    row["gate"].pop("requests_completed_at_kill")
    report = pr.reconcile_item(row, lines, before, after)
    assert pr.fault_class(report.checks) == "integrity", report.problems


def test_k1_a_failed_line_of_another_stream_than_the_final_start_stays_integrity():
    """[INV on the baseline; adopted defect of candidate 1, delivery 3] the one trailing failure must be the failure of the request the final
    `Request started` line opened (same uid): a mismatched uid between the final started and the failed line is NOT the item's own
    race, whatever the worker counters say - it keeps today's class (integrity)."""
    row, lines, before, after = build(failed_uid=2)
    assert [x.fields.get("uid") for x in lines[-2:]] == ["1", "2"]          # the fixture really has the mismatch
    report = pr.reconcile_item(row, lines, before, after)
    assert pr.fault_class(report.checks) == "integrity", (report.case, report.problems)
