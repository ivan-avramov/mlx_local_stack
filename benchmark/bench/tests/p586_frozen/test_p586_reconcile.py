"""P586 at the reconciliation seam: `reconcile_item(row, lines, before, after, *, client=ClientEvidence)`, `parse_telemetry`,
`TelemetryLine`, the case names, conditions (a)–(e), the completed variant and the boundaries (SPEC v1 §P586; criteria 1, 2).

Every negative flips exactly ONE fact of the real leg-3 item (`fixtures/p586/`) and expects `ok=False` with a failing
`client_abort_<x>` check whose name carries the condition's word from the spec (provenance / continuity / kill-marker /
accounting / ending): the spec fixes the `client_abort_` prefix, not the suffixes.

Classes: [R] reproduces the failure the spec fixes, [I] preserves an invariant, [N] exercises new behaviour."""
from __future__ import annotations

import copy
import dataclasses

import pytest

from bench import p426_reconcile as pr


def tl(line, **kw):
    """A changed copy of one TelemetryLine (a dataclass per the spec; a NamedTuple is tolerated)."""
    try:
        return dataclasses.replace(line, **kw)
    except TypeError:
        return line._replace(**kw)


def assert_fails(report, kit, cond):
    assert report.ok is False, report
    failing = kit.failing_client_checks(report)
    assert failing and kit.names_condition(failing, cond), (cond, failing, report.checks)
    assert report.problems                                     # the failed check is a problem (the hook turns it into `invalidate`)


def assert_accepted(report, kit, case="kill_client_aborted"):
    assert report.ok is True, (report.problems, report.checks)
    assert report.case == case and report.problems == []
    checks = kit.client_checks(report)
    assert checks and all(c["ok"] for c in checks.values()), checks
    for cond in "abcde":                                       # each condition is its own named check
        assert kit.names_condition(checks, cond), (cond, sorted(checks))


# =============================================================================================== criterion 1
def test_c1_the_leg3_item_reconciles_as_kill_client_aborted(kit):
    """[R] criterion 1: the real leg-3 window, row, worker snapshots and export reconcile ok=True, case
    `kill_client_aborted` (baseline: invalid, `inflight_evidence`)."""
    r = kit.reconcile_fixture()
    assert_accepted(r, kit)
    assert [q["error"] for q in r.requests] == [None, None, kit.STREAM_CLOSED]
    assert [q["generated_tokens"] for q in r.requests[:2]] == [125, 71]
    base = kit.item_record_baseline()["totals"]
    assert {k: r.totals[k] for k in ("requests", "prompt_tokens", "generated_tokens")} == \
        {k: base[k] for k in ("requests", "prompt_tokens", "generated_tokens")}


def test_c1_the_item_stays_a_scored_strict_fail_and_kill_cases_name_both(kit):
    """[N] the two P586 cases are kill cases (the item stays a `client_inactivity` scored strict fail)."""
    assert "kill_client_aborted" in pr.KILL_CASES and "kill_client_aborted_completed_unaccounted" in pr.KILL_CASES
    for old in ("kill_boundary", "kill_inflight_failed", "kill_completed_unaccounted"):
        assert old in pr.KILL_CASES


def test_the_spec_constants(kit):
    """[N] ABORT_MATCH_S 5.0, TELEMETRY_GAP_S 120.0 (named by the spec)."""
    assert pr.ABORT_MATCH_S == 5.0 and pr.TELEMETRY_GAP_S == 120.0


# =============================================================================================== parse_telemetry
def test_parse_telemetry_reads_every_stream_telemetry_line_of_the_real_window(kit):
    """[N] 155 `Stream Telemetry` lines, typed fields, the leading local stamp text, byte offsets of the line starts."""
    data = kit.window_bytes()
    lines = pr.parse_telemetry(data)
    assert len(lines) == 155
    first, last = lines[0], lines[-1]
    assert (first.uid, first.tokens, first.rolling_tps, first.avg_tps, first.elapsed_s) == (56491323616, 500, 22.25, 22.25, 22.5)
    assert (last.uid, last.tokens, last.rolling_tps, last.avg_tps, last.elapsed_s) == (56491323616, 77500, 18.88, 21.27, 3643.5)
    assert first.stamp == "2026-11-01 01:16:39,507" and last.stamp == "2026-11-01 01:17:00,708"
    for ln in (first, last, lines[77]):
        assert type(ln.uid) is int and type(ln.tokens) is int
        assert isinstance(ln.elapsed_s, float) and isinstance(ln.rolling_tps, float) and isinstance(ln.avg_tps, float)
        assert ln.offset == 0 or data[ln.offset - 1:ln.offset] == b"\n"
        assert data[ln.offset:].startswith(ln.stamp.encode()) and b"Stream Telemetry" in data[ln.offset:data.index(b"\n", ln.offset)]
    assert [x.tokens for x in lines] == list(range(500, 77501, 500))


def test_parse_telemetry_ignores_every_other_line(kit):
    """[N] request / prefix-cache / shrink lines are not telemetry."""
    data = b"\n".join(kit.window_bytes().split(b"\n")[:51]) + b"\n"    # up to the third request's Prefix Cache line
    assert pr.parse_telemetry(data) == []


@pytest.mark.parametrize("bad", [
    "Stream Telemetry | uid=abc | tokens=500 | rolling_tps=22.25 | avg_tps=22.25 | elapsed=22.5s | cached",
    "Stream Telemetry | uid=56491323616 | tokens=5x0 | rolling_tps=22.25 | avg_tps=22.25 | elapsed=22.5s | cached",
    "Stream Telemetry | uid=56491323616 | tokens=500 | rolling_tps=22.25 | avg_tps=22.25 | cached",
    "Stream Telemetry | uid=56491323616 | tokens=500 | rolling_tps=fast | avg_tps=22.25 | elapsed=22.5s | cached",
    "Stream Telemetry | garbage",
], ids=["uid", "tokens", "no-elapsed", "rolling", "garbage"])
def test_a_stream_telemetry_line_that_does_not_parse_raises_log_parse_error(kit, bad):
    """[N] a `Stream Telemetry` line that does not parse is `LogParseError` (systemic)."""
    data = kit.window_bytes() + f"2026-11-01 01:17:03,000 - mlx_vlm.server - INFO - {bad}\n".encode()
    with pytest.raises(pr.LogParseError):
        pr.parse_telemetry(data)


# =============================================================================================== (a) provenance
def _export_with(kit, **changes):
    doc = kit.export_doc()
    msg = kit.last_assistant(doc)
    for k, v in changes.items():
        if k == "completed_ms":
            msg["time"]["completed"] = v
        else:
            msg[k] = v
    return doc


@pytest.mark.parametrize("flip", ["sha", "error_type", "error_message", "finish", "completed_time", "not_last"])
def test_a_provenance_one_fact_flipped_fails(kit, flip):
    """[N] condition (a), each fact of the export alone: its sha, the aborted error (type, message), `finish`, the completion
    time, and that the aborted message is the LAST assistant message."""
    if flip == "sha":
        r = kit.reconcile_fixture(sha_ok=False)
    elif flip == "error_type":
        r = kit.reconcile_fixture(export=_export_with(kit, error={"type": "api", "message": "Step interrupted"}))
    elif flip == "error_message":
        r = kit.reconcile_fixture(export=_export_with(kit, error={"type": "aborted", "message": "Interrupted by the user"}))
    elif flip == "finish":
        r = kit.reconcile_fixture(export=_export_with(kit, finish="stop"))
    elif flip == "completed_time":
        r = kit.reconcile_fixture(export=_export_with(kit, completed_ms=1793524622068 + 6000))
    else:
        doc = kit.export_doc()
        later = copy.deepcopy(kit.last_assistant(doc))
        later.update(id="msg_later", finish="stop")
        later.pop("error")
        doc["messages"].insert(len(doc["messages"]) - 1, later)
        r = kit.reconcile_fixture(export=doc)
    assert_fails(r, kit, "a")


@pytest.mark.parametrize("flip", ["error_kind", "no_last_error"])
def test_a_the_failed_variants_t_is_the_workers_stream_closed_error(kit, flip):
    """[N] (a), failed variant: `T` is `after.last_error.timestamp_unix` only with `error == stream_closed_before_completion`."""
    a = kit.after()
    if flip == "error_kind":
        a["last_error"] = dict(a["last_error"], error="client_disconnected")
    else:
        a["last_error"] = None
    assert_fails(kit.reconcile_fixture(a=a), kit, "a")


def test_a_the_failed_variant_does_not_read_last_request_at(kit):
    """[N] (a), failed variant: `after.last_request_at` far off, `last_error` matching -> still accepted."""
    a = kit.after()
    a["last_request_at"] = a["last_request_at"] - 3600.0
    assert_accepted(kit.reconcile_fixture(a=a), kit)


@pytest.mark.parametrize("t, ok", [(1793524617.0, True), (1793524616.999, False), (1793524627.0, True), (1793524627.001, False)],
                         ids=["at-5.0-before", "over-before", "at-5.0-after", "over-after"])
def test_a_abort_match_boundary(kit, t, ok):
    """[N] |time.completed / 1000 - T| <= ABORT_MATCH_S (5.0): exactly 5.0 passes, 5.001 fails, both directions (values exact in
    binary floating point: completed = 1793524622000 ms)."""
    a = kit.after()
    a["last_error"] = dict(a["last_error"], timestamp_unix=t)
    r = kit.reconcile_fixture(export=_export_with(kit, completed_ms=1793524622000), a=a)
    if ok:
        assert_accepted(r, kit)
    else:
        assert_fails(r, kit, "a")


def test_a_no_local_log_timestamp_enters_provenance(kit):
    """[N] (a) reads no local stamp: every telemetry stamp moved by hours (a different zone), the close gap unchanged ->
    still accepted."""
    lines = [tl(x, stamp="2026-11-01 09" + x.stamp[13:]) for x in kit.telemetry()]
    assert_accepted(kit.reconcile_fixture(lines=lines), kit)


# =============================================================================================== (b) continuity
@pytest.mark.parametrize("flip", ["no_lines", "second_uid", "tokens_not_increasing", "elapsed_not_increasing",
                                  "close_gap_missing", "close_gap_negative", "close_gap_over"])
def test_b_continuity_one_fact_flipped_fails(kit, flip):
    """[N] condition (b): >= 1 line, one uid, tokens and elapsed strictly increasing, 0 <= close_gap_s <= 120 (a negative gap
    is what a DST fall-back inside the gap gives: it fails, systemic)."""
    lines = kit.telemetry()
    kw = {}
    if flip == "no_lines":
        kw["lines"] = []
    elif flip == "second_uid":
        kw["lines"] = lines[:-1] + [tl(lines[-1], uid=lines[-1].uid + 1)]
    elif flip == "tokens_not_increasing":
        kw["lines"] = lines[:10] + [tl(lines[10], tokens=lines[9].tokens)] + lines[11:]
    elif flip == "elapsed_not_increasing":
        kw["lines"] = lines[:10] + [tl(lines[10], elapsed_s=lines[9].elapsed_s)] + lines[11:]
    elif flip == "close_gap_missing":
        kw["close_gap_s"] = None
    elif flip == "close_gap_negative":
        kw["close_gap_s"] = -3598.707                           # 01:59:59,708 PDT -> 01:00:01,001 PST read as local stamps
    else:
        kw["close_gap_s"] = 120.001
    assert_fails(kit.reconcile_fixture(**kw), kit, "b")


def _regular(lines, step=20.0, start=None, jump_at=None, jump=0.0):
    """The real lines with exactly representable elapsed values: `start + i*step`, plus `jump` from index `jump_at` on."""
    start = step if start is None else start
    out = []
    for i, x in enumerate(lines):
        e = start + i * step + (jump if jump_at is not None and i >= jump_at else 0.0)
        out.append(tl(x, elapsed_s=e))
    return out


@pytest.mark.parametrize("jump, ok", [(0.0, True), (100.0, True), (100.001, False)], ids=["regular", "gap-at-120.0", "gap-120.001"])
def test_b_telemetry_gap_boundary(kit, jump, ok):
    """[N] every consecutive elapsed gap <= TELEMETRY_GAP_S (120.0): exactly 120.0 passes, 120.001 fails."""
    r = kit.reconcile_fixture(lines=_regular(kit.telemetry(), jump_at=50, jump=jump))
    if ok:
        assert_accepted(r, kit)
    else:
        assert_fails(r, kit, "b")


@pytest.mark.parametrize("gap, ok", [(0.0, True), (120.0, True), (120.001, False), (-5.0, True), (-5.001, False)])
def test_b_close_gap_boundary(kit, gap, ok):
    """[N] -ABORT_MATCH_S <= close_gap_s <= TELEMETRY_GAP_S (adopted finding X1: the gap is the export's wall time minus the last
    telemetry elapsed, two clocks, so a small negative value within ABORT_MATCH_S is clock skew, not a step; delivery 3 replaced
    the superseded `-0.001 fails` case with the -5.0 / -5.001 boundary)."""
    r = kit.reconcile_fixture(close_gap_s=gap)
    if ok:
        assert_accepted(r, kit)
    else:
        assert_fails(r, kit, "b")


def test_b_the_first_lines_elapsed_is_not_bounded(kit):
    """[N] the first line's elapsed includes prefill (residual R1): 500 s before the first line, 20 s steps after -> accepted."""
    assert_accepted(kit.reconcile_fixture(lines=_regular(kit.telemetry(), start=500.0)), kit)


def test_b_a_single_telemetry_line_is_enough(kit):
    """[N] `>= 1` telemetry line."""
    assert_accepted(kit.reconcile_fixture(lines=kit.telemetry()[-1:]), kit)


# =============================================================================================== (c) no kill marker
@pytest.mark.parametrize("flip", ["requests_completed_at_kill", "reason", "in_flight_at_kill", "killed_verified", "client_stop",
                                  "killed"])
def test_c_any_kill_marker_fails(kit, flip):
    """[N] condition (c): gate.requests_completed_at_kill, termination.{reason, in_flight_at_kill, killed_verified,
    client_stop} all null and termination.killed empty. (With in_flight_at_kill=1 the baseline ACCEPTS the item as
    `kill_inflight_failed`: P586 must not.)"""
    r = kit.row()
    if flip == "requests_completed_at_kill":
        r["gate"]["requests_completed_at_kill"] = 2
    elif flip == "killed":
        r["termination"]["killed"] = [dict(pid=4242)]
    else:
        r["termination"][flip] = dict(reason="x", in_flight_at_kill=1, killed_verified=True, client_stop="sigterm")[flip]
    assert_fails(kit.reconcile_fixture(r=r), kit, "c")


# =============================================================================================== (d) accounting
@pytest.mark.parametrize("flip", ["requests_observed", "gate_requests_completed", "request_usage"])
def test_d_accounting_one_fact_flipped_fails(kit, flip):
    """[N] condition (d), failed variant: requests_observed == |S|; |F| == 1; |C| == len(request_usage) == gate.requests_completed."""
    r = kit.row()
    if flip == "requests_observed":
        r["requests_observed"] = 4
    elif flip == "gate_requests_completed":
        r["gate"]["requests_completed"] = 3
    else:
        r["request_usage"] = r["request_usage"][:1]
    assert_fails(kit.reconcile_fixture(r=r), kit, "d")


@pytest.mark.parametrize("flip", ["worker_deltas", "foreign_session", "serial"])
def test_d_every_existing_check_still_applies(kit, flip):
    """[N] (d) "plus every existing check": a worker-delta mismatch, a foreign session on a completed line, a second start
    before a terminal line -> ok=False."""
    lines, a = None, None
    if flip == "worker_deltas":
        a = dict(kit.after(), requests_failed=2)
    else:
        data = kit.window_bytes()
        if flip == "foreign_session":
            data = data.replace(f"session={kit.SESSION} cached_tokens=0".encode(), b"session=ses_other cached_tokens=0", 1)
        else:
            data = data.replace(b"in_flight=1\n", b"in_flight=2\n", 1)
        lines = pr.parse_log(data)
    r = kit.reconcile_fixture(log_lines=lines, a=a)            # delivery 2c: the log lines by their own keyword
    assert r.ok is False and r.problems


# =============================================================================================== (e) normal client ending
@pytest.mark.parametrize("field, value", [("stop_reason", "error"), ("opencode_rc", 0), ("opencode_rc", 137),
                                          ("client_exit_hang", True), ("torn_tail", True), ("trailing", "complete")])
def test_e_normal_client_ending_one_fact_flipped_fails(kit, field, value):
    """[N] condition (e): stop_reason == completed, opencode_rc == 1, client_exit_hang is False, torn_tail is False,
    reconciliation.trailing == interrupted."""
    r = kit.row()
    if field == "trailing":
        r["reconciliation"]["trailing"] = value
    else:
        r[field] = value
    assert_fails(kit.reconcile_fixture(r=r), kit, "e")


@pytest.mark.parametrize("field, value", [("client_exit_hang", None), ("torn_tail", None)])
def test_e_is_false_is_identity_not_falsiness(kit, field, value):
    """[N] (e) says `is False`: a missing (null) flag is not a normal ending."""
    r = kit.row()
    r[field] = value
    assert_fails(kit.reconcile_fixture(r=r), kit, "e")


# =============================================================================================== the completed variant
def test_completed_variant_reconciles_as_kill_client_aborted_completed_unaccounted(kit):
    """[R] the server completed the request the client aborted: |F| == 0, |C| == len(request_usage) + 1, C[:-1] pairs, the
    trailing line's session == the row's, T = after.last_request_at (baseline: `unaccounted_inflight` fails)."""
    r = kit.reconcile_completed_variant()
    assert_accepted(r, kit, case="kill_client_aborted_completed_unaccounted")
    assert [q["error"] for q in r.requests] == [None, None, None]


def test_completed_variant_takes_t_from_last_request_at_not_last_error(kit):
    """[N] completed variant: a stale `last_error` does not matter; `last_request_at` does."""
    a = kit.completed_variant_after()
    a["last_error"] = dict(error=kit.STREAM_CLOSED, timestamp_unix=a["last_request_at"] - 3600.0)
    assert_accepted(kit.reconcile_completed_variant(a=a), kit, case="kill_client_aborted_completed_unaccounted")


@pytest.mark.parametrize("flip", ["last_request_at", "error_type", "sha"])
def test_completed_variant_fails_when_a_fails(kit, flip):
    """[N] criterion 2: the completed variant fails when (a) fails."""
    if flip == "last_request_at":
        a = kit.completed_variant_after()
        a["last_request_at"] += 5.001
        r = kit.reconcile_completed_variant(a=a)
    elif flip == "error_type":
        r = kit.reconcile_completed_variant(export=_export_with(kit, error={"type": "api", "message": "Step interrupted"}))
    else:
        r = kit.reconcile_completed_variant(sha_ok=False)
    assert_fails(r, kit, "a")


@pytest.mark.parametrize("flip", ["reason", "in_flight_at_kill", "killed"])
def test_completed_variant_fails_when_c_fails(kit, flip):
    """[N] criterion 2: the completed variant fails when (c) fails (with in_flight_at_kill=1 the baseline accepts it as
    `kill_completed_unaccounted`)."""
    r = kit.row()
    if flip == "killed":
        r["termination"]["killed"] = [dict(pid=4242)]
    else:
        r["termination"][flip] = dict(reason="x", in_flight_at_kill=1)[flip]
    assert_fails(kit.reconcile_completed_variant(r=r), kit, "c")


def test_completed_variant_with_a_foreign_trailing_session_fails(kit):
    """[N] (d), completed variant: the trailing completed line's session must be the row's."""
    data = kit.completed_variant_window().replace(f"session={kit.SESSION} cached_tokens=3990".encode(),
                                                  b"session=ses_other cached_tokens=3990")
    a = kit.completed_variant_after()
    r = pr.reconcile_item(kit.row(), pr.parse_log(data), kit.before(), a, client=kit.client(lines=pr.parse_telemetry(data)))
    assert r.ok is False and r.problems


# =============================================================================================== the boundary case stays
def _boundary(kit):
    data = b"\n".join(kit.window_bytes().split(b"\n")[:46]) + b"\n"
    lines = pr.parse_log(data)
    r = kit.row()
    r["requests_observed"] = 2
    a = kit.before()
    a.update(requests_started=a["requests_started"] + 2, requests_completed=a["requests_completed"] + 2,
             prompt_tokens_total=a["prompt_tokens_total"] + 6942, generated_tokens_total=a["generated_tokens_total"] + 196)
    return r, lines, a


def test_client_inactivity_at_a_request_boundary_stays_kill_boundary(kit):
    """[I] |F| == 0, |C| == len(request_usage): `kill_boundary`, ok (as on the baseline)."""
    r, lines, a = _boundary(kit)
    rep = pr.reconcile_item(r, lines, kit.before(), a)
    assert rep.ok and rep.case == "kill_boundary"


def test_client_inactivity_at_a_request_boundary_with_client_evidence_is_unchanged(kit):
    """[N] the same with the hook's ClientEvidence (no trailing request: no telemetry): the report equals the one without it."""
    r, lines, a = _boundary(kit)
    plain = pr.reconcile_item(r, lines, kit.before(), a)
    withc = pr.reconcile_item(r, lines, kit.before(), a, client=kit.client(lines=[], close_gap_s=None))
    assert withc.ok and withc.case == "kill_boundary"
    assert dataclasses.asdict(withc) == dataclasses.asdict(plain)
