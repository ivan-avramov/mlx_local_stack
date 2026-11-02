"""P586 / P593 (implementer's red-first tests): `kill_client_aborted` (+ `..._completed_unaccounted`) on leg 3's real records."""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from bench import p426_reconcile as pr

FIX = Path(__file__).parent / "fixtures" / "p586"
FAILED_CASE, COMPLETED_CASE = "kill_client_aborted", "kill_client_aborted_completed_unaccounted"


def load(name):
    return json.loads((FIX / name).read_text())


ROW = load("row.json")
REC = load("item_record_baseline.json")
BEFORE, AFTER = REC["worker_before"], REC["worker_after"]
EXPORT = load("export.json")
DATA = (FIX / "window.log").read_bytes()


def evidence(*, row=ROW, export=EXPORT, data=DATA, sha_ok=True):
    return pr.client_evidence(export, sha_ok, pr.parse_log(data), data)


def run(*, row=None, data=DATA, before=BEFORE, after=AFTER, client="auto", export=None, sha_ok=True):
    row = copy.deepcopy(ROW) if row is None else row
    lines = pr.parse_log(data)
    if client == "auto":
        client = pr.client_evidence(copy.deepcopy(EXPORT) if export is None else export, sha_ok, lines, data)
    return pr.reconcile_item(row, lines, before, after, client=client)


def completed_variant():
    """The synthetic shape: the server completed the request the client aborted (the failed line becomes a completed one)."""
    text = DATA.decode()
    head, last = text.rstrip("\n").rsplit("\n", 1)
    stamp = last[:23]
    done = (f"{stamp} - mlx_vlm.server - INFO - Request completed: endpoint=/chat/completions model=m stream=True backend=cached_session "
            f"session={ROW['session_id']} cached_tokens=3990 prompt_tokens=3992 generated_tokens=77510 elapsed=3645.0s "
            f"prefill=900.0 tok/s decode=21.2 tok/s finish_reason=length in_flight=0")
    data = (head + "\n" + done + "\n").encode()
    after = dict(AFTER, requests_completed=BEFORE["requests_completed"] + 3, requests_failed=0,
                 prompt_tokens_total=BEFORE["prompt_tokens_total"] + 6942 + 3992,
                 generated_tokens_total=BEFORE["generated_tokens_total"] + 196 + 77510, last_error=None,
                 last_request_at=AFTER["last_request_at"])
    return data, after


# -- parse_telemetry
def test_parse_telemetry_reads_the_workers_lines():
    tel = pr.parse_telemetry(DATA)
    assert len(tel) == 155
    last = tel[-1]
    assert (last.uid, last.tokens, last.rolling_tps, last.avg_tps, last.elapsed_s) == (56491323616, 77500, 18.88, 21.27, 3643.5)
    assert last.stamp == "2026-11-01 01:17:00,708" and DATA[last.offset:].startswith(b"2026-11-01 01:17:00,708")


def test_a_telemetry_line_that_does_not_parse_raises():
    bad = DATA + b"2026-11-01 01:17:03,000 - mlx_vlm.server - INFO - Stream Telemetry | uid=x | tokens=5\n"
    with pytest.raises(pr.LogParseError):
        pr.parse_telemetry(bad)


def test_parse_telemetry_ignores_an_unterminated_final_segment_and_other_lines():
    assert pr.parse_telemetry(b"noise\n2026-11-01 01:17:03,000 - x - INFO - Stream Telemetry | uid=1") == []


# -- the fixture
def test_the_leg3_item_reconciles_as_a_client_abort_with_its_provenance_block():
    r = run()
    assert r.ok, r.problems
    assert r.case == FAILED_CASE
    for name in ("provenance", "continuity", "no_kill_marker", "accounting", "ending"):
        assert r.checks[f"client_abort_{name}"]["ok"] is True, name
    assert "inflight_evidence" not in r.checks
    b = r.client_abort
    assert b["request_index"] == 2 and b["wall_s"] == pytest.approx(3645.065)
    assert (b["generated_tokens_at_last_telemetry"], b["decode_tok_s"], b["rolling_tps"], b["telemetry_elapsed_s"]) == (77500, 21.27, 18.88, 3643.5)
    assert b["telemetry_lines"] == 155 and b["telemetry_interval_tokens"] == 500 and b["cap_s"] == 3600
    assert b["cap_source"] == "opencode 2.0.20 LocationActivity timeToLive default (C154); not configurable"


def test_the_client_evidence_is_ignored_for_a_row_that_is_not_client_inactivity():
    row = copy.deepcopy(ROW)
    row["nonconv_kind"] = "budget_hit_kill"
    row["gate"]["requests_completed_at_kill"] = 2
    with_client = run(row=row)
    without = run(row=copy.deepcopy(row), client=None)
    assert (with_client.ok, with_client.case, with_client.problems, with_client.checks) == (without.ok, without.case, without.problems, without.checks)
    assert not with_client.ok and with_client.client_abort is None


def test_client_none_keeps_todays_verdict_for_the_same_row():
    r = run(client=None)
    assert not r.ok and "inflight_evidence" in r.checks and r.client_abort is None


def test_client_inactivity_at_a_request_boundary_stays_kill_boundary():
    lines_text = DATA.decode().split("\n")
    keep = "\n".join(lines_text[:47]) + "\n"          # up to the second request's completed line
    data = keep.encode()
    after = dict(AFTER, requests_completed=BEFORE["requests_completed"] + 2, requests_started=BEFORE["requests_started"] + 2,
                 requests_failed=0, prompt_tokens_total=BEFORE["prompt_tokens_total"] + 6942,
                 generated_tokens_total=BEFORE["generated_tokens_total"] + 196)
    row = copy.deepcopy(ROW)
    row["requests_observed"] = 2
    r = run(row=row, data=data, after=after, client=None)
    assert r.ok and r.case == "kill_boundary"
    r2 = run(row=row, data=data, after=after)
    assert r2.ok and r2.case == "kill_boundary" and r2.client_abort is None


# -- one negative per condition, each flipping one fact
def flip_export(**kw):
    ex = copy.deepcopy(EXPORT)
    msg = [m for m in ex["messages"] if m["type"] == "assistant"][-1]
    for k, v in kw.items():
        msg[k] = v
    return ex


def not_ok(r, check):
    assert not r.ok and r.case in (FAILED_CASE, COMPLETED_CASE, "kill_inflight_failed", "kill_completed_unaccounted")
    assert check in r.checks and r.checks[check]["ok"] is False, (check, r.checks)
    assert any(p.startswith(check) for p in r.problems)


def test_a_provenance_export_sha_mismatch_fails():
    not_ok(run(sha_ok=False), "client_abort_provenance")


@pytest.mark.parametrize("kw", [dict(error=None), dict(error={"type": "aborted", "message": "other"}), dict(finish="stop"),
                                dict(error={"type": "aborted", "message": "Step interrupted", "x": 1})])
def test_a_provenance_export_message_fact_fails(kw):
    not_ok(run(export=flip_export(**kw)), "client_abort_provenance")


def test_a_provenance_export_time_outside_the_match_window_fails():
    ex = flip_export()
    msg = [m for m in ex["messages"] if m["type"] == "assistant"][-1]
    msg["time"] = dict(msg["time"], completed=msg["time"]["completed"] + 6000)
    not_ok(run(export=ex), "client_abort_provenance")
    ex2 = flip_export()
    m2 = [m for m in ex2["messages"] if m["type"] == "assistant"][-1]
    m2["time"] = dict(m2["time"], completed=m2["time"]["completed"] + 4000)               # 4 s: inside ABORT_MATCH_S
    assert run(export=ex2).ok


def test_a_provenance_last_error_must_be_the_stream_closed_one():
    after = copy.deepcopy(AFTER)
    after["last_error"]["error"] = "other"
    not_ok(run(after=after), "client_abort_provenance")


def test_a_provenance_without_a_readable_export_is_a_problem_not_an_exception():
    not_ok(run(export={}), "client_abort_provenance")
    not_ok(run(export=None, client=pr.ClientEvidence(export=None, export_sha_ok=True, telemetry=pr.parse_telemetry(DATA), close_gap_s=1.0)),
           "client_abort_provenance")


def drop_telemetry(pred):
    out = []
    for ln in DATA.decode().split("\n"):
        if "Stream Telemetry" in ln and pred(ln):
            continue
        out.append(ln)
    return "\n".join(out).encode()


def test_continuity_needs_a_telemetry_line():
    data = drop_telemetry(lambda ln: True)
    not_ok(run(data=data), "client_abort_continuity")


def test_continuity_refuses_a_gap_over_120_s():
    data = drop_telemetry(lambda ln: 3000 < float(ln.split("elapsed=")[1].split("s")[0]) < 3200)
    not_ok(run(data=data), "client_abort_continuity")


def test_continuity_refuses_a_second_uid_or_non_increasing_tokens_or_elapsed():
    text = DATA.decode()
    not_ok(run(data=text.replace("uid=56491323616 | tokens=77500", "uid=1 | tokens=77500").encode()), "client_abort_continuity")
    not_ok(run(data=text.replace("tokens=77500", "tokens=77000").encode()), "client_abort_continuity")
    not_ok(run(data=text.replace("elapsed=3643.5s", "elapsed=3617.1s").encode()), "client_abort_continuity")


def test_continuity_close_gap_bounds_and_dst():
    # X1 (fix round 1): the gap is the export's wall_s - the last telemetry elapsed; local log stamps no longer enter it
    ev = pr.client_evidence(EXPORT, True, pr.parse_log(DATA), DATA)
    assert ev.close_gap_s == pytest.approx(1.565)
    not_ok(run(client=dataclasses.replace(ev, close_gap_s=121.0)), "client_abort_continuity")
    not_ok(run(client=dataclasses.replace(ev, close_gap_s=-5.1)), "client_abort_continuity")
    stamps = DATA.replace(b"01:17:02,001 - mlx_vlm.server - WARNING", b"01:00:02,001 - mlx_vlm.server - WARNING")
    assert run(data=stamps).ok                                              # a changed local stamp is not evidence either way


@pytest.mark.parametrize("path,value", [(("gate", "requests_completed_at_kill"), 2), (("termination", "reason"), "x"),
                                        (("termination", "in_flight_at_kill"), 1), (("termination", "killed_verified"), True),
                                        (("termination", "client_stop"), {"a": 1}), (("termination", "killed"), [{"pid": 1}])])
def test_a_kill_marker_fails_no_kill_marker(path, value):
    row = copy.deepcopy(ROW)
    row[path[0]][path[1]] = value
    not_ok(run(row=row), "client_abort_no_kill_marker")


def test_accounting_row_requests_observed_and_usage_count():
    row = copy.deepcopy(ROW)
    row["requests_observed"] = 4
    not_ok(run(row=row), "client_abort_accounting")
    row = copy.deepcopy(ROW)
    row["gate"]["requests_completed"] = 1
    not_ok(run(row=row), "client_abort_accounting")


@pytest.mark.parametrize("key,value", [("stop_reason", "stalled"), ("opencode_rc", 0), ("client_exit_hang", True), ("torn_tail", True)])
def test_a_not_normal_client_ending_fails(key, value):
    row = copy.deepcopy(ROW)
    row[key] = value
    not_ok(run(row=row), "client_abort_ending")


def test_ending_needs_the_interrupted_trailing():
    row = copy.deepcopy(ROW)
    row["reconciliation"]["trailing"] = "complete"
    not_ok(run(row=row), "client_abort_ending")


# -- the completed variant
def test_the_completed_variant_passes_on_its_synthetic_shape():
    data, after = completed_variant()
    r = run(data=data, after=after)
    assert r.ok, r.problems
    assert r.case == COMPLETED_CASE and r.client_abort["request_index"] == 2


def test_the_completed_variant_fails_when_a_or_c_fails():
    data, after = completed_variant()
    not_ok(run(data=data, after=after, sha_ok=False), "client_abort_provenance")
    row = copy.deepcopy(ROW)
    row["termination"]["reason"] = "x"
    not_ok(run(row=row, data=data, after=after), "client_abort_no_kill_marker")
    # T for the completed variant is `last_request_at`, not `last_error`
    late = dict(after, last_request_at=after["last_request_at"] + 60)
    not_ok(run(data=data, after=late), "client_abort_provenance")


def test_the_completed_variants_trailing_session_must_be_the_rows():
    data, after = completed_variant()
    r = run(data=data.replace(ROW["session_id"].encode() + b" cached_tokens=3990", b"ses_other cached_tokens=3990"), after=after)
    assert not r.ok


# -- the item record
def test_decode_rate_source_is_recorded_per_item_and_client_abort_only_for_the_two_cases():
    from bench import p426_hooks as ph
    assert ph.DECODE_RATE_SOURCE == "completed requests (spec 8)"
    assert ph.CLIENT_STEP_CAP_SOURCE == "opencode 2.0.20 LocationActivity timeToLive default (C154); not configurable"
    _ = hashlib  # (the hook-level record is covered in test_p586_impl_hooks)
