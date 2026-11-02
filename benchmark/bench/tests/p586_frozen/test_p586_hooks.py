"""P586 / P593 / P589-R2 at the done-hook seam: `P426Hooks.after_attempt` builds the `ClientEvidence` itself (export from
`row.transcript_path`, its sha against `row.evidence_sha256.export`, the telemetry strictly inside the trailing request, the
close gap from the two lines' local stamps) and writes the item record (SPEC v1 §P586 hook paragraph, §P593, §P589).

The leg-3 item runs through the real hook with fake ops (`kit.run_fixture_item`): ready record at the log's end, the worker log
grows by the real window, `/metrics` moves to the real `worker_after`.

Classes: [R] reproduces the failure the spec fixes, [I] preserves an invariant, [N] exercises new behaviour."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from bench import p426_hooks as ph
from bench import p426_reconcile as pr


# =============================================================================================== criterion 1 at the hook
def test_c1_the_leg3_item_is_accepted_and_its_record_carries_the_client_abort_block(tmp_path, kit):
    """[R] criterion 1 / P593: accept; the item record is `reconciled`, case `kill_client_aborted`, with `client_abort` =
    {request_index, wall_s, generated_tokens_at_last_telemetry, decode_tok_s, rolling_tps, telemetry_elapsed_s, telemetry_lines,
    telemetry_interval_tokens, cap_s, cap_source}. `request_index` is read as the aborted request's position in the record's
    own `requests` table (the spec does not say 0- or 1-based; the table is the record's only request index)."""
    disp, rec, _ops = kit.run_fixture_item(tmp_path)
    assert disp.kind == "accept", rec["problems"]
    assert rec["verdict"] == "reconciled" and rec["case"] == "kill_client_aborted" and rec["problems"] == []
    assert ph.sealed_ok(rec)
    block = rec["client_abort"]
    assert set(block) == {"request_index", "wall_s", "generated_tokens_at_last_telemetry", "decode_tok_s", "rolling_tps",
                          "telemetry_elapsed_s", "telemetry_lines", "telemetry_interval_tokens", "cap_s", "cap_source"}
    assert rec["requests"][block["request_index"]]["error"] == kit.STREAM_CLOSED
    assert block["wall_s"] == pytest.approx((1793524622068 - 1793520977003) / 1000)       # the aborted message's created -> completed
    assert block["generated_tokens_at_last_telemetry"] == 77500
    assert block["decode_tok_s"] == pytest.approx(21.27) and block["rolling_tps"] == pytest.approx(18.88)
    assert block["telemetry_elapsed_s"] == pytest.approx(3643.5) and block["telemetry_lines"] == 155
    assert block["telemetry_interval_tokens"] == 500
    assert block["cap_s"] == 3600 and block["cap_source"] == kit.CAP_SOURCE
    assert rec["totals"]["decode_rate_source"] == kit.DECODE_RATE_SOURCE
    checks = {k: v for k, v in rec["checks"].items() if k.startswith("client_abort_")}
    assert checks and all(v["ok"] for v in checks.values())


def test_the_hook_resolves_a_portable_transcript_path_against_the_workdir(tmp_path, kit):
    """[N] `row.transcript_path` resolved like `chain_core.web_record` (`$STACK_WORKDIR/...` against the workdir; here the
    ops' `wd`, the seam `Chain.wd` is built from)."""
    ops_wd = Path(tmp_path) / "wd"
    rel = "opencode_transcripts/M/stem.run/go__crypto-square.json"
    kit.put(ops_wd / rel, kit.export_bytes())
    disp, rec, _ = kit.run_fixture_item(tmp_path, transcript="$STACK_WORKDIR/" + rel)
    assert disp.kind == "accept", rec["problems"]
    assert rec["case"] == "kill_client_aborted"


def test_the_completed_variant_through_the_hook(tmp_path, kit):
    """[R] the completed variant through the hook: accept, case `kill_client_aborted_completed_unaccounted`, with its block."""
    disp, rec, _ = kit.run_fixture_item(tmp_path, window=kit.completed_variant_window(), a=kit.completed_variant_after())
    assert disp.kind == "accept", rec["problems"]
    assert rec["case"] == "kill_client_aborted_completed_unaccounted" and rec["client_abort"]["cap_s"] == 3600
    assert rec["client_abort"]["generated_tokens_at_last_telemetry"] == 77500


# =============================================================================================== failure paths of the hook
@pytest.mark.parametrize("how", ["missing", "not_json", "sha_mismatch"])
def test_an_unreadable_or_changed_export_is_a_problem_never_an_exception(tmp_path, kit, how):
    """[N] an unreadable export (missing, not JSON) or one whose sha differs from `row.evidence_sha256.export`: the hook
    returns `invalidate` (systemic), writes the record, raises nothing. Only the sha mismatch is pinned to condition (a)'s
    check (`export_sha_ok` is part of (a)); for an unreadable export the spec fixes only "a problem", not which check."""
    r = kit.row()
    kw = {}
    if how == "missing":
        kw["transcript"] = str(Path(tmp_path) / "nowhere" / "go__crypto-square.json")
    elif how == "not_json":
        kw["export"] = b"{not json"
        r["evidence_sha256"]["export"] = hashlib.sha256(b"{not json").hexdigest()
    else:
        r["evidence_sha256"]["export"] = "0" * 64
    disp, rec, _ = kit.run_fixture_item(tmp_path, r=r, **kw)
    assert disp.kind == "invalidate" and rec["verdict"] == "invalid" and rec["problems"]
    failing = [k for k, v in rec["checks"].items() if not v["ok"]]
    assert failing, rec["checks"]
    assert "inflight_evidence" not in failing, "the P586 path must judge the export, not the probe-kill evidence"
    if how == "sha_mismatch":
        client_failing = [k for k in failing if k.startswith("client_abort_")]
        assert client_failing and kit.names_condition(client_failing, "a"), rec["checks"]


FAILED_LINE = b"2026-11-01 01:17:02,001 - mlx_vlm.server - WARNING - Request failed"


def _naive_plus(stamp, seconds):
    """A `YYYY-MM-DD HH:MM:SS,mmm` local stamp moved by `seconds` as naive wall-clock text (no zone)."""
    import datetime
    d = datetime.datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S,%f") + datetime.timedelta(seconds=seconds)
    return d.strftime("%Y-%m-%d %H:%M:%S,") + f"{d.microsecond // 1000:03d}"


def _fails_b(disp, rec, kit):
    assert disp.kind == "invalidate" and rec["verdict"] == "invalid"
    failing = [k for k, v in rec["checks"].items() if k.startswith("client_abort_") and not v["ok"]]
    assert failing and kit.names_condition(failing, "b"), rec["checks"]


def test_a_dst_fall_back_inside_the_close_gap_fails_safe(tmp_path, kit):
    """[N] P590 / (b), amended in delivery 3 for adopted finding X1 (the gap = the export's wall time minus the last telemetry
    elapsed; no local stamp enters): the worker's stream stops at its last line BEFORE the fall-back (01:5x PDT) and the client
    aborts after it (the real failed line, PST). That pause is detected from the epoch / monotonic evidence -> invalidate, and
    rewriting the failed line's local stamp to read 22 s after the last telemetry line (what a naive stamp difference would accept)
    changes nothing."""
    data = kit.window_bytes()
    tel = kit.telemetry(data)
    n = next(i for i in range(1, len(tel)) if tel[i].stamp[14:16] < tel[i - 1].stamp[14:16]
             and tel[i - 1].stamp[11:13] == tel[i].stamp[11:13] == "01")                 # tel[n-1]: the last line before the fall-back
    assert tel[n - 1].stamp[14:16] >= "55" and tel[n].stamp[14:16] <= "05", (tel[n - 1].stamp, tel[n].stamp)
    paused = kit.window_keeping_telemetry(n, data)
    assert kit.x1_gap_after_keeping(n) > 600                                             # ≈ a thousand seconds of real pause
    _fails_b(*kit.run_fixture_item(tmp_path / "a", window=paused)[:2], kit)
    restamped = kit.restamp(paused, FAILED_LINE, _naive_plus(tel[n - 1].stamp, 22))     # 22 s after 01:5x:yy PDT, as naive text
    assert restamped != paused
    _fails_b(*kit.run_fixture_item(tmp_path / "b", window=restamped)[:2], kit)


def test_local_stamps_rewritten_have_no_effect_on_an_unpaused_item(tmp_path, kit):
    """[N] delivery 3 (X1): the real item with its failed line's stamp rewritten across the fall-back (01:00:01,001, i.e. a naive
    gap of -16 minutes from the last telemetry line) is still accepted: the stamps are not evidence either way."""
    data = kit.restamp(kit.window_bytes(), FAILED_LINE, "2026-11-01 01:00:01,001")
    disp, rec, _ = kit.run_fixture_item(tmp_path, window=data)
    assert disp.kind == "accept", rec["problems"]
    assert rec["case"] == "kill_client_aborted"


def test_a_close_gap_over_the_bound_in_the_log_fails(tmp_path, kit):
    """[N] (b) at the hook, amended in delivery 3 for X1: the stream stops early enough that export wall time minus the last
    telemetry elapsed first exceeds 120 s -> invalidate; one more telemetry line (gap <= 120 s) -> accepted. The failed line's local
    stamp is then rewritten to 1 s after the last kept telemetry line: no effect."""
    tel = kit.telemetry()
    total = len(tel)
    n = max(k for k in range(1, total + 1) if kit.x1_gap_after_keeping(k) > 120.0)   # the most lines that still leave a gap > 120
    assert kit.x1_gap_after_keeping(n + 1) <= 120.0
    over, under = kit.window_keeping_telemetry(n), kit.window_keeping_telemetry(n + 1)
    _fails_b(*kit.run_fixture_item(tmp_path / "over", window=over)[:2], kit)
    disp, rec, _ = kit.run_fixture_item(tmp_path / "under", window=under)
    assert disp.kind == "accept", rec["problems"]
    near = _naive_plus(tel[n - 1].stamp, 1)
    _fails_b(*kit.run_fixture_item(tmp_path / "stamped", window=kit.restamp(over, FAILED_LINE, near))[:2], kit)


def test_only_the_telemetry_strictly_inside_the_trailing_request_counts(tmp_path, kit):
    """[N] the telemetry lines are those strictly between the trailing request's `Request started` line and its terminal line:
    a telemetry line of another uid during the SECOND request is not part of it -> still accepted with 155 lines."""
    data = kit.window_bytes()
    marker = b"Generation queued: request=1118d0770"
    at = data.index(marker)
    at = data.index(b"\n", at) + 1
    stray = (b"2026-11-01 01:16:12,000 - mlx_vlm.server - INFO - Stream Telemetry | uid=7 | tokens=500 | rolling_tps=1.00 | "
             b"avg_tps=1.00 | elapsed=0.5s | cached\n")
    disp, rec, _ = kit.run_fixture_item(tmp_path, window=data[:at] + stray + data[at:])
    assert disp.kind == "accept", rec["problems"]
    assert rec["client_abort"]["telemetry_lines"] == 155


def test_a_malformed_telemetry_line_in_the_window_is_systemic(tmp_path, kit):
    """[N] a `Stream Telemetry` line that does not parse (LogParseError) -> invalidate, never an exception."""
    data = kit.window_bytes()
    bad = b"2026-11-01 01:16:40,000 - mlx_vlm.server - INFO - Stream Telemetry | uid=x | tokens=? | cached\n"
    at = data.index(b"2026-11-01 01:16:59,758")
    disp, rec, _ = kit.run_fixture_item(tmp_path, window=data[:at] + bad + data[at:])
    assert disp.kind == "invalidate" and rec["verdict"] == "invalid"


# =============================================================================================== P593 on every item record
def _completed_item(tmp_path, kit, *, slot, lines_range, usage, k=0, hooks=None):
    """A normally completed item (one real request of the fixture window) through the hook."""
    data = kit.window_bytes().split(b"\n")
    window = b"\n".join(data[lines_range[0]:lines_range[1]]) + b"\n"
    ops, h, out = hooks
    assert h.before_attempt(slot, kit.ctx(slot=slot, k=k)).kind == "accept"
    ops.append(window)
    ls = pr.parse_log(window)
    c = [x for x in ls if x.kind == "completed"]
    s = copy.deepcopy(ops.summary)
    s.update(requests_started=s["requests_started"] + len(c), requests_completed=s["requests_completed"] + len(c),
             prompt_tokens_total=s["prompt_tokens_total"] + sum(int(x.fields["prompt_tokens"]) for x in c),
             generated_tokens_total=s["generated_tokens_total"] + sum(int(x.fields["generated_tokens"]) for x in c))
    ops.summary = s
    r = kit.row()
    r.update(nonconv_kind=None, nonconv_flags=[], converged=True, stop_reason="stop", request_usage=usage, requests_observed=len(c),
             id=f"{slot.split('|')[-2]}/{slot.split('|')[-1]}")
    r["gate"]["requests_completed"] = len(c)
    disp = h.after_attempt(slot, dict(id=r["id"]), kit.ctx(r, slot=slot, k=k))
    return disp, kit.item_record(out, slot)


PY = f"tg1-p426|oc|{'Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed'}|s1|python|beer-song"
GO = f"tg1-p426|oc|{'Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed'}|s1|go|crypto-square"
REQ1 = ((0, 23), [["msg_1962e0a81001wTZHT2gLtj1F4T", 125, 2951, 81920]])
REQ2 = ((23, 46), [["msg_1962e2fe00017iGrUFe9PHUxLQ", 71, 3991, 81920]])


def test_every_item_record_names_its_decode_rate_source_and_only_p586_cases_carry_client_abort(tmp_path, kit):
    """[N] P593: `totals.decode_rate_source = "completed requests (spec 8)"` on every item record (a normal completed item
    here); `client_abort` only on the two P586 cases."""
    hooks = kit.make_hooks(tmp_path)
    disp, rec = _completed_item(tmp_path, kit, slot=PY, lines_range=REQ1[0], usage=REQ1[1], hooks=hooks)
    assert disp.kind == "accept", rec["problems"]
    assert rec["case"] == "completed" and rec["totals"]["decode_rate_source"] == kit.DECODE_RATE_SOURCE
    assert not rec.get("client_abort")


# =============================================================================================== R2 on the first Go item
def test_r2_reconcile_mismatch_perturbs_the_first_go_item_not_the_first_item(tmp_path, kit):
    """[R] P589: with `inject="reconcile-mismatch"` the first `done` of a PYTHON item is accepted; the first `done` whose item
    is `go/*` is invalidated with the exact injected reason, its record written (baseline: the first item at all)."""
    hooks = kit.make_hooks(tmp_path, inject="reconcile-mismatch")
    disp, rec = _completed_item(tmp_path, kit, slot=PY, lines_range=REQ1[0], usage=REQ1[1], hooks=hooks)
    assert disp.kind == "accept", (disp, rec["checks"])
    disp, rec = _completed_item(tmp_path, kit, slot=GO, lines_range=REQ2[0], usage=REQ2[1], k=1, hooks=hooks)
    assert disp.kind == "invalidate" and disp.reason == ph.INJECTED_MISMATCH
    assert rec["verdict"] == "invalid" and any(ph.INJECTED_MISMATCH in p for p in rec["problems"])


def test_r2_without_injection_accepts_both(tmp_path, kit):
    """[I] the same two items without `--inject`: both accepted."""
    hooks = kit.make_hooks(tmp_path)
    assert _completed_item(tmp_path, kit, slot=PY, lines_range=REQ1[0], usage=REQ1[1], hooks=hooks)[0].kind == "accept"
    assert _completed_item(tmp_path, kit, slot=GO, lines_range=REQ2[0], usage=REQ2[1], k=1, hooks=hooks)[0].kind == "accept"


def test_r2_injects_once_on_the_first_go_item_only(tmp_path, kit):
    """[N] the injection fires on the FIRST go item: a Go item first is invalidated."""
    hooks = kit.make_hooks(tmp_path, inject="reconcile-mismatch")
    disp, _ = _completed_item(tmp_path, kit, slot=GO, lines_range=REQ2[0], usage=REQ2[1], hooks=hooks)
    assert disp.kind == "invalidate" and disp.reason == ph.INJECTED_MISMATCH


# =============================================================================================== the boundary case at the hook
def test_client_inactivity_at_a_boundary_through_the_hook_stays_kill_boundary(tmp_path, kit):
    """[I] a `client_inactivity` row whose window ends at a request boundary: `kill_boundary`, accepted (as on the baseline)."""
    ops, h, out = kit.make_hooks(tmp_path)
    assert h.before_attempt(kit.SLOT, kit.ctx()).kind == "accept"
    window = b"\n".join(kit.window_bytes().split(b"\n")[:46]) + b"\n"
    ops.append(window)
    s = kit.before()
    s.update(requests_started=s["requests_started"] + 2, requests_completed=s["requests_completed"] + 2,
             prompt_tokens_total=s["prompt_tokens_total"] + 6942, generated_tokens_total=s["generated_tokens_total"] + 196)
    ops.summary = s
    r = kit.row()
    r["requests_observed"] = 2
    ev = Path(tmp_path) / "ev"
    kit.put(ev / "go__crypto-square.json", kit.export_bytes())
    r["transcript_path"] = str(ev / "go__crypto-square.json")
    disp = h.after_attempt(kit.SLOT, dict(id="go/crypto-square"), kit.ctx(r))
    rec = kit.item_record(out)
    assert disp.kind == "accept", rec["problems"]
    assert rec["case"] == "kill_boundary"
