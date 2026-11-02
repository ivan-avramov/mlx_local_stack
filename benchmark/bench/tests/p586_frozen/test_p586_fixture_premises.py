"""The premises the P586 tests take from the real leg-3 records, checked WITHOUT the new interface (plain JSON and a local
regex), so that a red acceptance test can never be blamed on the fixture: the fixture item satisfies (a)–(e) as the spec states
them. Class: [I] (fixture invariants; they pass on the baseline by construction)."""
from __future__ import annotations

import hashlib
import re

TELEMETRY = re.compile(rb"^(?P<stamp>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3}) - mlx_vlm\.server - INFO - Stream Telemetry \| uid=(?P<uid>\d+) "
                       rb"\| tokens=(?P<tokens>\d+) \| rolling_tps=(?P<r>[\d.]+) \| avg_tps=(?P<a>[\d.]+) \| elapsed=(?P<e>[\d.]+)s \| cached$")


def _telemetry(kit):
    out = []
    for line in kit.window_bytes().split(b"\n"):
        if b"Stream Telemetry" in line:
            m = TELEMETRY.match(line)
            assert m, line
            out.append(m)
    return out


def test_the_window_is_the_item_records_log_range(kit):
    data = kit.window_bytes()
    rec = kit.item_record_baseline()
    assert hashlib.sha256(data).hexdigest() == rec["log_range"]["sha256"]
    assert len(data) == rec["log_range"]["end"] - rec["log_range"]["start"]
    assert data.count(b"\n") == 207


def test_a_provenance_holds_on_the_fixture(kit):
    r, doc, a = kit.row(), kit.export_doc(), kit.after()
    assert hashlib.sha256(kit.export_bytes()).hexdigest() == r["evidence_sha256"]["export"]
    msg = kit.last_assistant(doc)
    assert msg["error"] == kit.ABORT_ERROR and msg["finish"] == "error"
    assert a["last_error"]["error"] == kit.STREAM_CLOSED
    assert abs(msg["time"]["completed"] / 1000 - a["last_error"]["timestamp_unix"]) <= 5.0


def test_b_continuity_holds_on_the_fixture(kit):
    t = _telemetry(kit)
    assert len(t) == 155 and len({m["uid"] for m in t}) == 1
    tokens = [int(m["tokens"]) for m in t]
    elapsed = [float(m["e"]) for m in t]
    assert all(b > a for a, b in zip(tokens, tokens[1:])) and all(b > a for a, b in zip(elapsed, elapsed[1:]))
    assert max(b - a for a, b in zip(elapsed, elapsed[1:])) <= 120.0
    failed = [ln for ln in kit.window_bytes().split(b"\n") if b"Request failed" in ln]
    assert len(failed) == 1
    gap = kit.stamp_epoch_local_naive(failed[0][:23].decode()) - kit.stamp_epoch_local_naive(t[-1]["stamp"].decode())
    assert abs(gap - kit.FIXTURE_CLOSE_GAP_S) < 1e-6 and 0 <= gap <= 120.0


def test_b_the_fixture_crosses_the_fall_back_inside_the_request(kit):
    """The telemetry's local stamps go 01:59 -> 01:00 inside the trailing request (why no B2 logic may order by them)."""
    stamps = [m["stamp"].decode() for m in _telemetry(kit)]
    assert any(a[11:13] == "01" and a[14:16] >= "55" and b[14:16] <= "05" for a, b in zip(stamps, stamps[1:]))


def test_c_no_kill_marker_on_the_fixture(kit):
    r = kit.row()
    t = r["termination"]
    assert r["gate"]["requests_completed_at_kill"] is None
    assert (t["reason"], t["in_flight_at_kill"], t["killed_verified"], t["client_stop"], t["killed"]) == (None, None, None, None, [])


def test_d_accounting_holds_on_the_fixture(kit):
    r, lines = kit.row(), kit.window_lines()
    S = [x for x in lines if x.kind == "started"]
    C = [x for x in lines if x.kind == "completed"]
    F = [x for x in lines if x.kind == "failed"]
    assert r["requests_observed"] == len(S) == 3 and len(F) == 1
    assert len(C) == len(r["request_usage"]) == r["gate"]["requests_completed"] == 2
    assert [(int(x.fields["generated_tokens"]), int(x.fields["prompt_tokens"])) for x in C] == [(u[1], u[2]) for u in r["request_usage"]]


def test_e_normal_client_ending_on_the_fixture(kit):
    r = kit.row()
    assert r["nonconv_kind"] == "client_inactivity" and r["stop_reason"] == "completed" and r["opencode_rc"] == 1
    assert r["client_exit_hang"] is False and r["torn_tail"] is False and r["reconciliation"]["trailing"] == "interrupted"


def test_the_baseline_record_is_the_leg3_failure(kit):
    """What the baseline wrote for leg 3 (the failure P586 fixes)."""
    rec = kit.item_record_baseline()
    assert rec["verdict"] == "invalid" and rec["case"] == "kill_inflight_failed"
    assert [k for k, v in rec["checks"].items() if not v["ok"]] == ["inflight_evidence"]
