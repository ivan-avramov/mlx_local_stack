"""S29 K1 (spec docs/specs/s29-tg2-testable.md v1.1, acceptance 4): the recorded S29-P16 shape (`tg2-m76-n16-s2.a1`
javascript/zebra-puzzle: a harness kill whose client had opened its next request between the pre-signal `/metrics` sample and
the SIGTERM, the step never published) is the item's own accounting — recorded (`accounting_fault`, the sealed sidecar), the
leg not INVALID; a shape outside K1 keeps today's class."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from bench import p426_reconcile as pr
from bench.tests.test_b2_s4_reconcile import (BEFORE, SLOT, SLOT_FILE, after_of, completed, ctx, failed, lines_of, make_hooks,
                                              req, started)

# The recorded shape (`.fe-material/s29-p16-shape.json`: the row's termination, its reconciliation and request_usage; the
# killed client's argv and the message ids omitted, ids below are synthetic in order). Numbers verbatim.
USAGE = [(72, 3452), (1614, 3878), (246, 5517), (65, 5788), (151, 5994), (52, 6170), (64, 6260), (91, 6660), (376, 7011),
         (124, 7412), (62, 7677), (1025, 8143), (1127, 11262), (954, 12585), (622, 13560), (268, 14206), (276, 14492),
         (146, 14784), (668, 14992), (125, 15678), (2097, 15913), (2646, 18035), (564, 20706), (1166, 21295), (275, 22486),
         (139, 22903), (406, 23070), (85, 23494), (116, 23610), (408, 23761), (280, 24187), (483, 24578), (1156, 27500),
         (714, 28915), (544, 29707), (601, 30286), (167, 30906), (683, 31098), (595, 32157), (778, 32849)]       # (gen, prompt)
ENDS = [4116, 16659, 19025, 21243, 24071, 25616, 29042, 32097, 36632, 38838, 42945, 57079, 60841, 66951, 70759, 73381, 75988,
        78143, 81035, 83190, 86273, 101218, 105288, 115868, 118078, 120115, 123732, 125448, 126829, 129898, 132877, 149425,
        153949, 160210, 164756, 169370, 171411, 178442, 183439, 185310]
STARTS = [304] + [e + 304 for e in ENDS[:-1]]
SUMMARY_BEFORE = {"uptime_s": 9721.78071808815, "requests_started": 596, "requests_completed": 596, "requests_failed": 0,
                  "streaming_requests": 593, "in_flight": 0, "prompt_tokens_total": 6420256, "completion_tokens_total": 276099,
                  "generated_tokens_total": 276099, "avg_request_time_s": 13.671078897051625,
                  "avg_request_tok_s": 33.88564715288166, "avg_decode_tok_s": 39.669751368324185,
                  "last_request_at": 1795415045.4665978, "last_error": None}
SUMMARY_AFTER = dict(SUMMARY_BEFORE, uptime_s=9722.197005987167, requests_started=597, requests_failed=1, streaming_requests=594,
                     last_request_at=1795415046.1079528,
                     last_error={"timestamp_unix": 1795415046.1079528, "endpoint": "/chat/completions",
                                 "model": "caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "stream": True,
                                 "error": pr.STREAM_CLOSED})
TERMINATION = {"reason": "stalled", "killed_verified": True, "cancel_wait_s": 0.009632583940401673, "in_flight_at_kill": 0,
               "worker_summary_before": SUMMARY_BEFORE, "worker_summary_after": SUMMARY_AFTER, "client_stop": "sigterm",
               "graceful_wait_s": 0.31906679179519415, "ingested_offset_at_count": 185310, "events_size_at_count": 185310,
               "signal_offset": 185310, "requests_at_kill": 40, "inflight_s_at_stop": None, "signal_at": 1795415046.025801,
               "final_grade_faults": [], "final_regrades": 0, "step_end_offsets": ENDS, "step_start_offsets": STARTS,
               "last_step_start": "msg_40"}


def p16_row(**term):
    usage = [[f"msg_{k:02d}" if k < 40 else "msg_40", gen, prompt, 81920] for k, (gen, prompt) in enumerate(USAGE, 1)]
    termination = copy.deepcopy(TERMINATION)
    termination.update(term)
    return dict(id="javascript/zebra-puzzle", session_id="ses_1", request_usage=usage,
                gate=dict(stop_reason="stalled", requests_completed=40, requests_completed_at_kill=40), nonconv_kind="stalled",
                termination=termination, reconciliation={"unmatched_export_messages": 1, "trailing": "interrupted"},
                event_types_seen=dict(step_start=40, step_finish=40), requests_observed=40)


def with_fields(line, **fields):
    """`line` (a b2 test log line) with `fields` added before its `in_flight=` / `error=` tail."""
    head, sep, tail = line.rpartition("Request ")
    kind, colon, rest = tail.partition(": ")
    return head + sep + kind + colon + "".join(f"{k}={v} " for k, v in fields.items()) + rest


def p16_raw(trailing=True, start_uid="41", fail_uid="41", **extra):
    raw = [x for gen, prompt in USAGE for x in req(prompt=prompt, gen=gen)]
    s = {} if start_uid is None else dict(uid=start_uid)
    f = {} if fail_uid is None else dict(uid=fail_uid)
    return raw + ([with_fields(started(), **s, **extra), with_fields(failed(), **f, **extra)] if trailing else [])


def reconcile(row, raw, **after_over):
    ls = lines_of(*raw)
    return pr.reconcile_item(row, ls, dict(BEFORE), after_of(ls, **after_over))


def failed_checks(report):
    return {n for n, c in report.checks.items() if not c["ok"]}


# ----------------------------------------------------------------------------------------------- the recorded shape
def test_the_recorded_p16_shape_is_the_items_own_accounting():
    report = reconcile(p16_row(), p16_raw())
    assert report.case == "kill_inflight_failed" and not report.ok
    assert pr.fault_class(report.checks) == "accounting"
    assert failed_checks(report) == {pr.K1_CHECK}
    assert report.checks["inflight_evidence"]["ok"] and report.checks["failed_line"]["ok"]
    assert report.late_record["shape"] == pr.K1_SHAPE
    assert report.late_record["worker_delta_at_kill"] == dict(requests_started=1, requests_completed=0, requests_failed=1)
    assert report.late_record["failed_at"] >= report.late_record["signal_at"]
    assert report.totals["requests"] == 40 and report.totals["generated_tokens"] == sum(g for g, _ in USAGE)


def test_the_recorded_p16_shape_through_the_done_hook_is_an_accounting_fault_never_invalidate(tmp_path):
    ops, hooks, out = make_hooks(tmp_path, arm="OFF")
    hooks.before_attempt(SLOT, ctx())
    ops.serve(*p16_raw())
    d = hooks.after_attempt(SLOT, dict(id="javascript/zebra-puzzle"), ctx(p16_row()))
    assert d.kind == "accounting_fault", d.reason
    rec = json.loads((out / "items" / f"{SLOT_FILE}.json").read_text())
    assert rec["verdict"] == "invalid" and rec["fault_class"] == "accounting" and rec["case"] == "kill_inflight_failed"
    assert rec["late_record"]["shape"] == pr.K1_SHAPE
    side = json.loads((out / "items" / f"{SLOT_FILE}.accounting.json").read_text())
    assert side["failed_checks"] == [pr.K1_CHECK] and side["disposition"] == "accounting_fault"


def test_k1_is_in_the_closed_accounting_table():
    assert pr.K1_CHECK in pr.ACCOUNTING_CHECKS
    assert pr.fault_class({pr.K1_CHECK: dict(ok=False), "serial": dict(ok=True)}) == "accounting"
    assert pr.fault_class({pr.K1_CHECK: dict(ok=False), "inflight_evidence": dict(ok=False)}) == "integrity"


# ----------------------------------------------------------------------------------------------- outside K1: today's class
@pytest.mark.parametrize("name, edit", [
    ("a failed request with nothing started", lambda t: t["worker_summary_after"].update(requests_started=596)),
    ("a completed-count change", lambda t: t["worker_summary_after"].update(requests_completed=597)),
    ("two failures", lambda t: t["worker_summary_after"].update(requests_failed=2)),
    ("in flight at the pre-signal sample", lambda t: t["worker_summary_before"].update(in_flight=1)),
    ("no pre-signal sample", lambda t: t.pop("worker_summary_before")),
    ("no post-kill sample", lambda t: t.pop("worker_summary_after")),
    ("a failure before the signal", lambda t: t["worker_summary_after"]["last_error"].update(timestamp_unix=1795415045.9)),
    ("a failure of another kind", lambda t: t["worker_summary_after"]["last_error"].update(error="oom")),
    ("no signal recorded", lambda t: t.update(signal_at=None)),
    ("no in-flight sample at the kill", lambda t: t.update(in_flight_at_kill=None, reason=None)),
])
def test_a_shape_outside_k1_keeps_todays_integrity_class(name, edit):
    row = p16_row()
    edit(row["termination"])
    report = reconcile(row, p16_raw())
    assert not report.ok and pr.fault_class(report.checks) == "integrity", name
    assert pr.K1_CHECK not in report.checks


def test_a_trailing_failed_line_that_is_not_the_windows_last_keeps_todays_class():
    raw = p16_raw(trailing=False)
    raw = raw[:-2] + [started(), failed()] + raw[-2:]           # the failed request is not the item's trailing one
    row = p16_row()
    report = reconcile(row, raw)
    assert not report.ok and pr.fault_class(report.checks) == "integrity"


# ----------------------------------------------------------------- Sol P9: the trailing failure is bound to its own request
def test_the_k1_facts_record_the_bound_request_uid_and_session():
    report = reconcile(p16_row(), p16_raw())
    assert report.late_record["request_uid"] == "41" and report.late_record["session"] == "ses_1"


@pytest.mark.parametrize("name, raw", [
    ("a mismatched uid (orphan failure of another request)", dict(start_uid="41", fail_uid="99")),
    ("no uid on the failed line", dict(fail_uid=None)),
    ("no uid on the started line", dict(start_uid=None)),
    ("the trailing pair belongs to another session", dict(session="ses_other")),
    ("no uid, the trailing pair names another session", dict(start_uid=None, fail_uid=None, session="ses_other")),
])
def test_a_trailing_failure_not_bound_to_the_items_own_request_stays_integrity(name, raw):
    report = reconcile(p16_row(), p16_raw(**raw))
    assert not report.ok and pr.fault_class(report.checks) == "integrity", name
    assert pr.K1_CHECK not in report.checks


def test_a_row_without_a_session_id_cannot_bind_and_stays_integrity():
    row = p16_row()
    row.pop("session_id")
    report = reconcile(row, p16_raw())
    assert not report.ok and pr.fault_class(report.checks) == "integrity"


def test_the_bound_pair_with_a_matching_session_field_is_k1():
    report = reconcile(p16_row(), p16_raw(session="ses_1"))
    assert pr.fault_class(report.checks) == "accounting" and report.late_record["shape"] == pr.K1_SHAPE


def test_the_x2_shape_with_its_published_step_keeps_its_own_clean_class():
    """S27 X2 (the open step published before the signal) still reconciles clean; K1 never replaces it."""
    row = p16_row(step_start_offsets=STARTS + [185400], signal_offset=185500)
    report = reconcile(row, p16_raw(), last_error=SUMMARY_AFTER["last_error"])
    assert report.ok and report.late_record["shape"] == "open_step_at_signal"
    assert pr.fault_class(report.checks) is None


# --------------------------------------- the fork's real log format: no uid / session on `Request started` / `Request failed`
# Binding without a uid = the single-session worker's serial in-flight evidence: the window's last `Request completed` names the
# item's session and leaves in_flight 0, the next lifecycle line is `Request started` in_flight=1, then `Request failed`
# (stream_closed_before_completion) in_flight=0, nothing between them; the failure at / after the signal; started +1 / failed +1 /
# completed +0. Anything else stays INTEGRITY.
WINDOW = Path(__file__).resolve().parent / "fixtures" / "s29c_p16_worker_window.log"
REAL_SES = "ses_df8f707b0ffeUkNCqiP31QY1xq"   # the item's session as the window's completed lines name it


def no_uid_raw():
    return p16_raw(start_uid=None, fail_uid=None)


def _strip_in_flight(line):
    head, sep, rest = line.partition(" in_flight=")
    assert sep
    _value, space, tail = rest.partition(" ")
    return head + space + tail


def real_reconcile(data=None, **term):
    """The reconciler on the real n16 s2 a1 window (`.fe-material/p16-worker-log.log`, from the line after the previous item's
    last request to the end: the item's 41 starts, 40 completions, 1 failure), the row as recorded in the shape. ASSUMED (not
    in the recorded shape): the row's `session_id` = the session the window's completed lines name, `gate` / `event_types_seen`
    counts 40, and the per-item `before` snapshot = the kill-time `after` summary minus the window's own requests / tokens."""
    data = WINDOW.read_bytes() if data is None else data
    lines = pr.parse_log(data)
    row = p16_row(**term)
    row["session_id"] = REAL_SES
    after = copy.deepcopy(row["termination"]["worker_summary_after"])
    C = [x for x in lines if x.kind == "completed"]
    before = dict(after, requests_started=after["requests_started"] - sum(x.kind == "started" for x in lines),
                  requests_completed=after["requests_completed"] - len(C),
                  requests_failed=after["requests_failed"] - sum(x.kind == "failed" for x in lines), in_flight=0,
                  prompt_tokens_total=after["prompt_tokens_total"] - sum(int(x.fields["prompt_tokens"]) for x in C),
                  generated_tokens_total=after["generated_tokens_total"] - sum(int(x.fields["generated_tokens"]) for x in C))
    return pr.reconcile_item(row, lines, before, after), lines


def test_instrument_the_real_window_is_the_recorded_items_request_lifecycle():
    """[INV] the fixture is the real format (no uid, no session on start / failure) and the recorded item's requests."""
    data = WINDOW.read_bytes()
    lines = pr.parse_log(data)
    C = [x for x in lines if x.kind == "completed"]
    assert [x.kind for x in lines].count("started") == 41 and len(C) == 40 and lines[-1].kind == "failed"
    assert [(int(x.fields["generated_tokens"]), int(x.fields["prompt_tokens"])) for x in C] == [tuple(u) for u in USAGE]
    assert {x.fields["session"] for x in C} == {REAL_SES}
    assert not any(k in x.fields for x in lines if x.kind != "completed" for k in ("uid", "session"))
    assert [x.fields["in_flight"] for x in lines[-3:]] == ["0", "1", "0"]
    assert b"Prompt Delta: 842" in data.split(b"Request failed")[-1]        # the dead request was still prefilled


def test_the_real_p16_window_is_the_items_own_accounting():
    """[FIX] acceptance 4 on the real worker log: K1 binds by the serial in-flight evidence and the class is `accounting`."""
    report, _ = real_reconcile()
    assert pr.fault_class(report.checks) == "accounting", (report.case, report.problems)
    assert failed_checks(report) == {pr.K1_CHECK}
    assert report.late_record["shape"] == pr.K1_SHAPE and report.late_record["binding"] == "serial_in_flight"
    assert report.late_record["session"] == REAL_SES and report.late_record["request_uid"] is None
    assert report.late_record["failed_at"] >= report.late_record["signal_at"]


def test_the_trailing_requests_processing_is_recorded_descriptive_never_zero():
    """[FIX] the worker queued / prefilled the dead request after its failure line: K1 records its processing as descriptive
    accounting and never states it as zero; the item's totals hold only the completed requests."""
    report, _ = real_reconcile()
    assert report.late_record["trailing_processing"] == "descriptive"
    assert "zero" not in json.dumps(report.late_record).lower()
    assert report.totals["requests"] == 40 and report.totals["generated_tokens"] == sum(g for g, _ in USAGE)


def test_the_synthetic_no_uid_shape_is_k1_by_serial_evidence():
    report = reconcile(p16_row(), no_uid_raw())
    assert pr.fault_class(report.checks) == "accounting" and report.late_record["binding"] == "serial_in_flight"


def test_the_uid_binding_is_recorded_as_such():
    report = reconcile(p16_row(), p16_raw())
    assert report.late_record["binding"] == "uid"


def _set(raw, k, line):
    raw = list(raw)
    raw[k] = line
    return raw


_LAST_GEN, _LAST_PROMPT = USAGE[-1]


@pytest.mark.parametrize("name, raw", [
    ("the last completed line names a foreign session",
     lambda r: _set(r, -3, completed("ses_other", _LAST_PROMPT, _LAST_GEN))),
    ("the last completed line leaves a request in flight",
     lambda r: _set(r, -3, completed("ses_1", _LAST_PROMPT, _LAST_GEN, in_flight=1))),
    ("the last completed line has no in_flight", lambda r: _set(r, -3, _strip_in_flight(r[-3]))),
    ("the failed line leaves a request in flight", lambda r: _set(r, -1, failed(in_flight=1))),
    ("the trailing start shows another request in flight", lambda r: _set(r, -2, started(in_flight=2))),
    ("an interleaved foreign request between the last completion and the trailing start",
     lambda r: r[:-2] + req(session="anon:x", prompt=10, gen=1) + r[-2:]),
    ("an interleaved start between the trailing start and its failure", lambda r: r[:-1] + [started()] + r[-1:]),
    ("no completed line before the trailing pair", lambda r: r[-2:]),
])
def test_a_no_uid_trailing_failure_without_the_serial_evidence_stays_integrity(name, raw):
    report = reconcile(p16_row(), raw(no_uid_raw()))
    assert not report.ok and pr.fault_class(report.checks) == "integrity", name
    assert pr.K1_CHECK not in report.checks, name


@pytest.mark.parametrize("name, edit", [
    ("started +2", lambda t: t["worker_summary_after"].update(requests_started=598)),
    ("failed +2", lambda t: t["worker_summary_after"].update(requests_failed=2)),
    ("completed +1", lambda t: t["worker_summary_after"].update(requests_completed=597)),
    ("the failure before the signal", lambda t: t["worker_summary_after"]["last_error"].update(timestamp_unix=1795415045.9)),
    ("in flight at the pre-signal sample (summary only)", lambda t: t["worker_summary_before"].update(in_flight=1)),
])
def test_a_no_uid_count_or_signal_mismatch_stays_integrity(name, edit):
    row = p16_row()
    edit(row["termination"])
    report = reconcile(row, no_uid_raw())
    assert not report.ok and pr.fault_class(report.checks) == "integrity", name
    assert pr.K1_CHECK not in report.checks, name


def _fail_in_flight_1(d):
    k = d.rindex(b"in_flight=0")
    return d[:k] + b"in_flight=1" + d[k + len(b"in_flight=0"):]


_TRAILING_START = b"\n2026-11-22 22:24:06,079"


@pytest.mark.parametrize("name, edit", [
    ("the failed line leaves a request in flight", _fail_in_flight_1),
    ("the last completed line names a foreign session", lambda d: d.replace(
        b"session=" + REAL_SES.encode() + b" cached_tokens=32156", b"session=ses_foreign cached_tokens=32156")),
    ("an interleaved foreign request before the trailing start", lambda d: d.replace(
        _TRAILING_START, b"\n" + (started() + "\n" + completed("anon:x", 10, 1)).encode() + _TRAILING_START)),
])
def test_the_real_window_with_the_serial_evidence_broken_stays_integrity(name, edit):
    data = WINDOW.read_bytes()
    changed = edit(data)
    assert changed != data, name                            # the edit really applied
    report, _ = real_reconcile(changed)
    assert not report.ok and pr.fault_class(report.checks) == "integrity", (name, report.problems)
    assert pr.K1_CHECK not in report.checks, name
