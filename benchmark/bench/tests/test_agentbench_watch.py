"""M54 watcher daemon (bench/agentbench_watch.py): AGENTS.md's four standing questions, answered
from rows on disk only (read-only, never perturbs the run), plus the known-positive/known-negative
self-test (6th cold review round 6 P25/addendum F). No docker, no network, no real sleeping --
`--once` and injectable pid/busy/router-activity functions make every branch testable
synchronously."""
import json
import os
import time

import pytest

import bench.agentbench_watch as W


def _row(id_, group=1, passed=True, outcome="solved", turns=1, answer="42", wall_s=2.0,
        wall_total_s=None, completion_tokens_total=50, exec_timeout=False, shell_died=False,
        setup_error=False, converged=True, budget_hits=0, gold_prepare=None, gold_live=None,
        nonconv_kinds=None, per_turn_finish_reasons=None, per_turn_completion_tokens=None):
    return {"id": id_, "group": group, "passed": passed, "outcome": outcome, "turns": turns,
           "answer": answer, "wall_s": wall_s,
           "wall_total_s": wall_total_s if wall_total_s is not None else wall_s + 1.0,
           "completion_tokens_total": completion_tokens_total,
           "exec_timeout": exec_timeout, "shell_died": shell_died, "setup_error": setup_error,
           "converged": converged, "budget_hits": budget_hits, "gold_prepare": gold_prepare,
           "gold_live": gold_live, "nonconv_kinds": nonconv_kinds or [],
           "per_turn_finish_reasons": per_turn_finish_reasons or [],
           "per_turn_completion_tokens": per_turn_completion_tokens or []}


# --------------------------------------------------------------------------- read_rows / read_manifest
def test_read_rows_missing_file_returns_empty_list(tmp_path):
    assert W.read_rows(tmp_path / "nope.jsonl") == []


def test_read_rows_tolerates_a_torn_final_line(tmp_path):
    p = tmp_path / "rows.jsonl"
    p.write_text(json.dumps(_row("a")) + "\n" + '{"id": "b", "torn', encoding="utf-8")
    rows = W.read_rows(p)
    assert [r["id"] for r in rows] == ["a"]


def test_read_manifest_missing_file_returns_empty_dict(tmp_path):
    assert W.read_manifest(tmp_path / "nope.json") == {}


# --------------------------------------------------------------------------- reference_timestamp (P25)
def test_reference_timestamp_uses_rows_file_mtime_when_rows_exist(tmp_path):
    p = tmp_path / "rows.jsonl"
    p.write_text(json.dumps(_row("a")) + "\n", encoding="utf-8")
    os.utime(p, (1000.0, 1000.0))
    rows = W.read_rows(p)
    assert W.reference_timestamp(rows, {}, p) == 1000.0


def test_reference_timestamp_uses_manifest_started_at_when_no_rows_yet():
    """P25: 'time first-item silence from the manifest's started_at' -- with zero rows, the
    reference is the RUN's start time, not None (which would silently reset the stall clock)."""
    manifest = {"segments": [{"started_at": 500.0}]}
    assert W.reference_timestamp([], manifest, "/nonexistent") == 500.0


def test_reference_timestamp_falls_back_to_manifest_timestamp_field():
    manifest = {"timestamp": 700}
    assert W.reference_timestamp([], manifest, "/nonexistent") == 700


def test_reference_timestamp_none_when_truly_no_evidence():
    assert W.reference_timestamp([], {}, "/nonexistent") is None


# --------------------------------------------------------------------------- rate / ETA (mean, not median)
def test_eta_uses_the_mean_not_the_median():
    rows = [_row("a", wall_total_s=1.0), _row("b", wall_total_s=1.0), _row("c", wall_total_s=100.0)]
    stats = W.rate_stats(rows)
    assert stats["mean_wall_s"] == pytest.approx(34.0)   # (1+1+100)/3, NOT the median (1.0)
    eta = W.eta_seconds(total=10, done=3, mean_wall_s=stats["mean_wall_s"])
    assert eta == pytest.approx(7 * 34.0)


def test_eta_none_without_any_completed_rows():
    assert W.eta_seconds(total=10, done=0, mean_wall_s=None) is None
    assert W.rate_stats([])["mean_wall_s"] is None


def test_rate_stats_reports_max_wall_seen():
    rows = [_row("a", wall_total_s=5.0), _row("b", wall_total_s=40.0)]
    assert W.rate_stats(rows)["max_wall_s"] == 40.0


def test_rate_stats_uses_wall_total_s_not_wall_s_P32():
    """P32: rate/ETA must use the FULL task cost (container create -> verified removal), not just
    the agent-loop time -- a row where these differ proves the right field is read."""
    rows = [_row("a", wall_s=1.0, wall_total_s=100.0)]
    assert W.rate_stats(rows)["mean_wall_s"] == 100.0


def test_rate_stats_falls_back_to_wall_s_for_rows_missing_wall_total_s():
    row = _row("a", wall_s=5.0)
    del row["wall_total_s"]
    assert W.rate_stats([row])["mean_wall_s"] == 5.0


# --------------------------------------------------------------------------- sanity stats
def test_sanity_stats_counts_outcome_and_flag_kinds():
    rows = [
        _row("a", passed=True, outcome="solved"),
        _row("b", passed=False, outcome="turn_cap", exec_timeout=True),
        _row("c", passed=False, outcome="failed_tests", shell_died=True, converged=False, budget_hits=2),
        _row("d", passed=False, outcome="server_error", setup_error=True),
    ]
    s = W.sanity_stats(rows)
    assert s["outcome_counts"] == {"solved": 1, "turn_cap": 1, "failed_tests": 1, "server_error": 1}
    assert s["passed"] == 1 and s["failed"] == 3
    assert s["exec_timeout"] == 1 and s["shell_died"] == 1 and s["setup_error"] == 1
    assert s["converged_false"] == 1 and s["budget_hits_total"] == 2


def test_sanity_stats_gold_prepare_differs_only_when_both_known():
    rows = [_row("a", gold_prepare="3", gold_live="4"),    # differs
           _row("b", gold_prepare="3", gold_live="3"),     # agrees
           _row("c", gold_prepare="3", gold_live=None)]    # unknown -- not counted
    assert W.sanity_stats(rows)["gold_prepare_differs"] == 1


def test_sanity_stats_turns_histogram():
    rows = [_row("a", turns=1), _row("b", turns=1), _row("c", turns=8)]
    assert W.sanity_stats(rows)["turns_histogram"] == {1: 2, 8: 1}


def test_sanity_stats_completion_token_mean_and_max():
    rows = [_row("a", completion_tokens_total=100), _row("b", completion_tokens_total=300)]
    s = W.sanity_stats(rows)
    assert s["completion_tokens_mean"] == 200.0 and s["completion_tokens_max"] == 300


def test_sanity_stats_flags_empty_and_long_answers():
    rows = [_row("a", answer=""), _row("b", answer=None), _row("c", answer="x" * 201),
           _row("d", answer="short")]
    s = W.sanity_stats(rows)
    assert s["empty_answers"] == 2 and s["long_answers"] == 1


def test_sanity_stats_same_as_previous_answer_degeneracy_hint():
    rows = [_row("a", answer="7"), _row("b", answer="7"), _row("c", answer="9"), _row("d", answer="9")]
    assert W.sanity_stats(rows)["same_as_previous_answer"] == 2


def test_sanity_stats_same_as_previous_ignores_empty_answers():
    rows = [_row("a", answer=""), _row("b", answer="")]
    assert W.sanity_stats(rows)["same_as_previous_answer"] == 0


def test_sanity_stats_per_group_pass_rate():
    rows = [_row("a", group=1, passed=True), _row("b", group=1, passed=False),
           _row("c", group=2, passed=True)]
    assert W.sanity_stats(rows)["per_group_pass_rate"] == {1: 0.5, 2: 1.0}


def test_sanity_stats_nonconv_kind_counts_P32():
    rows = [_row("a", nonconv_kinds=["budget_hit"]),
           _row("b", nonconv_kinds=["budget_hit", "bad_finish_reason"])]
    assert W.sanity_stats(rows)["nonconv_kind_counts"] == {"budget_hit": 2, "bad_finish_reason": 1}


def test_sanity_stats_degenerate_eos_count_P32():
    """P32: a 'stop' finish with suspiciously few completion tokens (<5) is a distinct degenerate
    pattern from a budget hit or a loop -- flagged separately."""
    rows = [_row("a", per_turn_finish_reasons=["stop"], per_turn_completion_tokens=[2]),
           _row("b", per_turn_finish_reasons=["stop"], per_turn_completion_tokens=[500]),
           _row("c", per_turn_finish_reasons=["tool_calls"], per_turn_completion_tokens=[2])]
    assert W.sanity_stats(rows)["degenerate_eos"] == 1


def test_sanity_stats_degenerate_eos_pairs_by_turn_not_independently_P43c():
    """7th cold review round 7 P43(c), reproduced: ["tool_calls","stop"] paired with [1,100] used
    to falsely count as degenerate EOS (turn 1's small token count checked independently of turn
    2's "stop", which itself used 100 tokens and is not degenerate). finish_reason and
    completion_tokens must be paired BY TURN INDEX."""
    rows = [_row("a", per_turn_finish_reasons=["tool_calls", "stop"],
                per_turn_completion_tokens=[1, 100])]
    assert W.sanity_stats(rows)["degenerate_eos"] == 0


def test_sanity_stats_degenerate_eos_true_positive_when_stop_turn_itself_has_few_tokens():
    rows = [_row("a", per_turn_finish_reasons=["tool_calls", "stop"],
                per_turn_completion_tokens=[100, 1])]
    assert W.sanity_stats(rows)["degenerate_eos"] == 1


# --------------------------------------------------------------------------- stall / wedge classification (P25)
def test_classify_stall_none_when_within_threshold_and_driver_alive():
    assert W.classify_stall(100.0, stall_s=2700.0, driver_pid=os.getpid()) is None


def test_classify_stall_driver_dead_checked_first_even_within_threshold_addendum_E():
    """6th cold review round 6, addendum E: driver liveness is checked on EVERY tick,
    INDEPENDENT of the stall threshold -- a crashed driver is reported even if we have not yet
    reached the stall timer."""
    label = W.classify_stall(10.0, stall_s=2700.0, driver_pid=999999,
                             pid_alive_fn=lambda pid: False)
    assert label == "DRIVER DEAD"


def test_classify_stall_driver_dead_past_threshold_too():
    label = W.classify_stall(3000.0, stall_s=2700.0, driver_pid=999999,
                             pid_alive_fn=lambda pid: False)
    assert label == "DRIVER DEAD"


def test_classify_stall_unknown_when_no_reference_evidence_P25():
    """P25 reproduction: missing rows file + dead-but-reported-alive driver used to read
    'STALL: none' indefinitely -- a missing reference timestamp must be UNKNOWN, never silently
    'not stalled'."""
    label = W.classify_stall(None, stall_s=2700.0, driver_pid=os.getpid())
    assert label is not None and label.startswith("UNKNOWN")


def test_classify_stall_runaway_suspect_when_worker_busy():
    label = W.classify_stall(3000.0, stall_s=2700.0, driver_pid=os.getpid(),
                             busy_check_fn=lambda: True)
    assert label == "RUNAWAY-SUSPECT (busy)"


def test_classify_stall_wedge_when_worker_idle():
    label = W.classify_stall(3000.0, stall_s=2700.0, driver_pid=os.getpid(),
                             busy_check_fn=lambda: False)
    assert label == "WEDGE (idle)"


def test_classify_stall_unknown_when_no_worker_found_P25():
    """P25 reproduction: missing busy/idle evidence (no worker process) used to read
    'WEDGE (idle)' -- that is an unsupported conclusion, not a true idle observation."""
    label = W.classify_stall(3000.0, stall_s=2700.0, driver_pid=os.getpid(),
                             busy_check_fn=lambda: None)
    assert label is not None and label.startswith("UNKNOWN")


def test_pid_alive_true_for_self():
    assert W.pid_alive(os.getpid()) is True


def test_pid_alive_false_for_a_pid_that_does_not_exist():
    assert W.pid_alive(2**30) is False


# --------------------------------------------------------------------------- worker busy/idle (P25/P38)
ROUTER_PID = 4242


def _run_fn(pgrep_out=None, pgrep_rc=0, ppid_out=None, ppid_rc=0, cpu_out=None, cpu_rc=0,
           pgrep_raises=False):
    """A fake `subprocess.run`-shaped callable for find_worker_pids/worker_busy, keyed by argv
    shape (macOS `pgrep -fl` / `ps -o ppid=` / `ps -o %cpu=`)."""
    def run_fn(argv):
        if pgrep_raises and argv[:2] == ["pgrep", "-fl"]:
            return None
        if argv[:2] == ["pgrep", "-fl"]:
            return W._FakeCompletedProcess(pgrep_out or "", pgrep_rc)
        if argv[:2] == ["ps", "-o"] and "ppid=" in argv[2]:
            return W._FakeCompletedProcess(ppid_out or "", ppid_rc)
        if argv[:2] == ["ps", "-o"] and "%cpu=" in argv[2]:
            return W._FakeCompletedProcess(cpu_out or "", cpu_rc)
        return W._FakeCompletedProcess("", 1)
    return run_fn


def test_find_worker_pids_macos_pgrep_fl_format_pid_plus_full_cmdline():
    """7th cold review round 7 P38 (HIGH), reproduced on macOS: `pgrep -af` returned ONLY the pid
    (BSD pgrep does not support `-a` as a listing flag the way GNU pgrep does) -- `pgrep -fl` is
    the correct BSD "long format" flag and is what this function must use."""
    run_fn = _run_fn(pgrep_out="111 /path/python -m mlx_vlm.server --port 8000\n"
                              "222 /path/python -m mlx_vlm.server --port 8092\n",
                     ppid_out=f"{ROUTER_PID}\n")
    pids = W.find_worker_pids(ROUTER_PID, run_fn=run_fn)
    assert pids == [111]   # 222 excluded (the :8092 task model)


def test_find_worker_pids_filters_by_ppid_chain_to_the_router():
    """P38: a worker process NOT descended from the recorded router pid must be excluded -- it
    belongs to some other experiment/box state, not THIS run."""
    run_fn = _run_fn(pgrep_out="111 /path/python -m mlx_vlm.server --port 8000\n",
                     ppid_out="99999\n")   # NOT the router pid
    pids = W.find_worker_pids(ROUTER_PID, run_fn=run_fn)
    assert pids == []


def test_find_worker_pids_none_when_pgrep_itself_fails():
    """P38: a discovery FAILURE (pgrep launch error, or an unexpected exit code) is UNKNOWN,
    never indistinguishable from a legitimate 'no match' (empty list)."""
    assert W.find_worker_pids(ROUTER_PID, run_fn=_run_fn(pgrep_raises=True)) is None
    assert W.find_worker_pids(ROUTER_PID, run_fn=_run_fn(pgrep_out="", pgrep_rc=2)) is None


def test_find_worker_pids_empty_list_when_pgrep_finds_no_match():
    """pgrep rc=1 ('no processes matched') is a LEGITIMATE empty result, not a failure."""
    assert W.find_worker_pids(ROUTER_PID, run_fn=_run_fn(pgrep_out="", pgrep_rc=1)) == []


def test_worker_busy_none_when_no_worker_pid():
    assert W.worker_busy(ROUTER_PID, run_fn=_run_fn(pgrep_out="", pgrep_rc=1)) is None


def test_worker_busy_true_when_either_sample_exceeds_threshold():
    samples = iter(["5.0\n", "99.0\n"])
    run_fn = _run_fn(pgrep_out="111 mlx_vlm.server --port 8000\n", ppid_out=f"{ROUTER_PID}\n")

    def run_fn_cycling(argv):
        if argv[:2] == ["ps", "-o"] and "%cpu=" in argv[2]:
            return W._FakeCompletedProcess(next(samples), 0)
        return run_fn(argv)
    busy = W.worker_busy(ROUTER_PID, run_fn=run_fn_cycling, sleep_fn=lambda s: None)
    assert busy is True


def test_worker_busy_false_when_both_samples_below_threshold():
    samples = iter(["1.0\n", "2.0\n"])
    run_fn = _run_fn(pgrep_out="111 mlx_vlm.server --port 8000\n", ppid_out=f"{ROUTER_PID}\n")

    def run_fn_cycling(argv):
        if argv[:2] == ["ps", "-o"] and "%cpu=" in argv[2]:
            return W._FakeCompletedProcess(next(samples), 0)
        return run_fn(argv)
    busy = W.worker_busy(ROUTER_PID, run_fn=run_fn_cycling, sleep_fn=lambda s: None)
    assert busy is False


def test_worker_busy_samples_twice_with_the_configured_gap():
    gaps = []
    run_fn = _run_fn(pgrep_out="111 x --port 8000\n", ppid_out=f"{ROUTER_PID}\n", cpu_out="1.0\n")
    W.worker_busy(ROUTER_PID, run_fn=run_fn, sleep_fn=lambda s: gaps.append(s))
    assert gaps == [W.WORKER_SAMPLE_GAP_S]


def test_worker_busy_none_when_cpu_sample_itself_fails_P38():
    """P38 reproduction: a failed `ps` call used to return 0.0 (read as a genuine idle
    observation, producing WEDGE); it must propagate as UNKNOWN instead."""
    run_fn = _run_fn(pgrep_out="111 x --port 8000\n", ppid_out=f"{ROUTER_PID}\n", cpu_rc=1)
    assert W.worker_busy(ROUTER_PID, run_fn=run_fn, sleep_fn=lambda s: None) is None


# --------------------------------------------------------------------------- _ppid_chain_contains (P38)
def test_ppid_chain_contains_direct_parent():
    run_fn = _run_fn(ppid_out=f"{ROUTER_PID}\n")
    assert W._ppid_chain_contains(111, ROUTER_PID, run_fn) is True


def test_ppid_chain_contains_walks_multiple_hops():
    chain = iter([9000, ROUTER_PID])   # pid -> 9000 -> router_pid

    def run_fn(argv):
        return W._FakeCompletedProcess(f"{next(chain)}\n", 0)
    assert W._ppid_chain_contains(111, ROUTER_PID, run_fn) is True


def test_ppid_chain_contains_false_when_chain_terminates_at_init():
    run_fn = _run_fn(ppid_out="1\n")
    assert W._ppid_chain_contains(111, ROUTER_PID, run_fn) is False


def test_ppid_chain_contains_none_when_ps_fails_mid_walk():
    run_fn = _run_fn(ppid_rc=1)
    assert W._ppid_chain_contains(111, ROUTER_PID, run_fn) is None


# --------------------------------------------------------------------------- --calibrate (P38)
def test_run_calibrate_refuses_without_a_router_pid_in_manifest(tmp_path, capsys):
    import argparse
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({}), encoding="utf-8")
    args = argparse.Namespace(manifest=str(manifest_path))
    rc = W.run_calibrate(args, run_fn=lambda argv: None)
    assert rc == 2
    assert "router pid" in capsys.readouterr().err


def test_run_calibrate_refuses_when_discovery_fails(tmp_path, capsys):
    import argparse
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"router": {"pid": ROUTER_PID}}), encoding="utf-8")
    args = argparse.Namespace(manifest=str(manifest_path))
    rc = W.run_calibrate(args, run_fn=lambda argv: None)
    assert rc == 2
    assert "DISCOVERY FAILED" in capsys.readouterr().err


def test_run_calibrate_samples_and_prints_for_the_configured_duration(tmp_path, capsys):
    import argparse
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"router": {"pid": ROUTER_PID}}), encoding="utf-8")
    args = argparse.Namespace(manifest=str(manifest_path))
    run_fn = _run_fn(pgrep_out="111 x --port 8000\n", ppid_out=f"{ROUTER_PID}\n", cpu_out="42.0\n")
    slept = []
    rc = W.run_calibrate(args, run_fn=run_fn, sleep_fn=lambda s: slept.append(s), duration_s=3.0)
    assert rc == 0
    assert len(slept) == 3
    out = capsys.readouterr().out
    assert "42.0" in out and "max=42.0" in out


def test_run_calibrate_returns_1_when_no_valid_cpu_sample_is_ever_obtained_P52b(tmp_path, capsys):
    """8th cold review round 8 P52(b): if every single %cpu sample fails across the whole
    calibration window, the run produced NO evidence at all -- it must not silently "succeed"
    with rc 0 and an empty-looking samples list."""
    import argparse
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"router": {"pid": ROUTER_PID}}), encoding="utf-8")
    args = argparse.Namespace(manifest=str(manifest_path))
    # discovery succeeds (worker pid found), but every %cpu sample itself fails.
    run_fn = _run_fn(pgrep_out="111 x --port 8000\n", ppid_out=f"{ROUTER_PID}\n", cpu_rc=1)
    rc = W.run_calibrate(args, run_fn=run_fn, sleep_fn=lambda s: None, duration_s=3.0)
    assert rc == 1
    assert "FAILED" in capsys.readouterr().err


# --------------------------------------------------------------------------- router log (SUPPORTING diagnostic only)
def test_router_recently_active_true_with_fresh_log_and_marker(tmp_path):
    log = tmp_path / "main_model.log"
    log.write_text('127.0.0.1 - - "POST /v1/chat/completions HTTP/1.1" 200\n', encoding="utf-8")
    assert W.router_recently_active(log, window_s=600, now=time.time()) is True


def test_router_recently_active_false_when_log_is_stale(tmp_path):
    log = tmp_path / "main_model.log"
    log.write_text('"POST /v1/chat/completions HTTP/1.1" 200\n', encoding="utf-8")
    old_time = os.path.getmtime(log) - 9999
    os.utime(log, (old_time, old_time))
    assert W.router_recently_active(log, window_s=600, now=time.time()) is False


def test_router_recently_active_false_without_the_marker(tmp_path):
    log = tmp_path / "main_model.log"
    log.write_text("router started\n", encoding="utf-8")
    assert W.router_recently_active(log, window_s=600, now=time.time()) is False


def test_router_recently_active_none_when_log_missing_P25():
    """P25: a missing router log is UNOBSERVABLE evidence, not a confident 'False' (which this
    purely-diagnostic signal used to return, conflating 'absent' with 'checked and idle')."""
    assert W.router_recently_active("/nonexistent-path", window_s=600, now=time.time()) is None


# --------------------------------------------------------------------------- build_assessment / tick
def test_build_assessment_progressing_true_when_rows_grew():
    now = time.time()
    rows = [_row("a"), _row("b")]
    block = W.build_assessment(rows, prev_rows_count=1, total=10, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               reference_ts=now, now=now)
    assert "(1) PROGRESSING: yes" in block
    assert "rows 1 -> 2" in block


def test_build_assessment_not_progressing_when_rows_flat():
    now = time.time()
    rows = [_row("a")]
    block = W.build_assessment(rows, prev_rows_count=1, total=10, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               reference_ts=now, now=now)
    assert "(1) PROGRESSING: NO" in block


def test_build_assessment_includes_eta_from_mean():
    now = time.time()
    rows = [_row("a", wall_total_s=10.0), _row("b", wall_total_s=10.0)]
    block = W.build_assessment(rows, prev_rows_count=0, total=4, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               reference_ts=now, now=now)
    assert "ETA=0.3 min" in block   # (4-2)*10s = 20s = 0.33 min
    assert "from the MEAN wall_total_s, never the median" in block


def test_build_assessment_stall_section_none_when_recent():
    now = time.time()
    rows = [_row("a")]
    block = W.build_assessment(rows, prev_rows_count=0, total=10, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               reference_ts=now, now=now)
    assert "(4) STALL: none" in block


def test_build_assessment_stall_section_reports_wedge():
    now = time.time()
    rows = [_row("a")]
    block = W.build_assessment(rows, prev_rows_count=0, total=10, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=100.0,
                               reference_ts=now - 500, now=now,
                               busy_check_fn=lambda: False)
    assert "(4) STALL: WEDGE (idle)" in block
    assert "NEVER killing anything" in block


def test_build_assessment_evidence_missing_section_when_rows_file_absent_P25():
    now = time.time()
    block = W.build_assessment([], prev_rows_count=0, total=10, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               reference_ts=None, now=now, rows_evidence=False,
                               manifest_evidence=False)
    assert "(0) EVIDENCE MISSING" in block
    assert "rows file missing" in block
    assert "manifest missing" in block
    assert "UNKNOWN" in block   # the stall line must not silently read "none"


def test_build_assessment_correct_vs_finish_line_P32(tmp_path):
    now = time.time()
    rows = [_row("a", wall_total_s=10.0), _row("b", wall_total_s=10.0)]
    block = W.build_assessment(rows, prev_rows_count=0, total=4, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               reference_ts=now, now=now, elapsed_s=120.0)
    assert "CORRECT-vs-FINISH" in block
    assert "elapsed=2.0min" in block


# --------------------------------------------------------------------------- CORRECT-vs-FINISH (P43d)
def test_correct_vs_finish_recommends_finish_by_default():
    now = time.time()
    rows = [_row("a", wall_total_s=10.0, converged=True)]
    block = W.build_assessment(rows, prev_rows_count=0, total=10, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               reference_ts=now, now=now)
    assert "-> FINISH" in block


def test_correct_vs_finish_recommends_correct_when_ratio_exceeds_2x():
    """7th cold review round 7 P43(d): the observed mean running >2x the PREDICTED (pilot) mean
    is a correction signal."""
    now = time.time()
    rows = [_row("a", wall_total_s=100.0, converged=True)]
    block = W.build_assessment(rows, prev_rows_count=0, total=10, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               reference_ts=now, now=now, predicted_mean_s=10.0)
    assert "ratio=10.0" in block
    assert "-> CORRECT" in block


def test_correct_vs_finish_recommends_correct_when_nonconv_share_exceeds_30pct():
    now = time.time()
    rows = [_row("a", wall_total_s=10.0, converged=False), _row("b", wall_total_s=10.0, converged=False),
           _row("c", wall_total_s=10.0, converged=True)]
    block = W.build_assessment(rows, prev_rows_count=0, total=10, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               reference_ts=now, now=now)
    assert "-> CORRECT" in block


def test_correct_vs_finish_recommends_correct_on_setup_error_in_last_5():
    now = time.time()
    rows = [_row(f"r{i}", wall_total_s=10.0, converged=True) for i in range(10)]
    rows[-1]["setup_error"] = True
    block = W.build_assessment(rows, prev_rows_count=0, total=20, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               reference_ts=now, now=now)
    assert "-> CORRECT" in block


def test_correct_vs_finish_ignores_setup_error_outside_last_5():
    now = time.time()
    rows = [_row(f"r{i}", wall_total_s=10.0, converged=True) for i in range(10)]
    rows[0]["setup_error"] = True   # well outside the last 5
    block = W.build_assessment(rows, prev_rows_count=0, total=20, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               reference_ts=now, now=now)
    assert "-> FINISH" in block


def test_build_assessment_emits_a_grep_friendly_summary_line():
    now = time.time()
    rows = [_row("a", passed=True), _row("b", passed=False)]
    block = W.build_assessment(rows, prev_rows_count=0, total=5, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               reference_ts=now, now=now)
    summary_lines = [l for l in block.splitlines() if l.startswith("SUMMARY")]
    assert len(summary_lines) == 1
    assert "done=2/5" in summary_lines[0]
    assert "passed=1" in summary_lines[0] and "failed=1" in summary_lines[0]


def test_build_assessment_sanity_line_mentions_all_required_counters():
    now = time.time()
    block = W.build_assessment([_row("a")], prev_rows_count=0, total=5, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               reference_ts=now, now=now)
    for key in ("outcome_counts", "exec_timeout", "shell_died", "setup_error",
               "gold_prepare_differs", "converged_false", "budget_hits_total",
               "nonconv_kind_counts", "degenerate_eos", "turns_histogram",
               "completion_tokens_mean", "empty_answers", "long_answers",
               "same_as_previous_answer", "per_group_pass_rate"):
        assert key in block, key


# --------------------------------------------------------------------------- self-test (P25/addendum F)
def test_self_test_exercises_real_file_io_for_every_known_case(tmp_path):
    """6th cold review round 6 P25/addendum F: the self-test must exercise the REAL
    read_rows/classify_stall path (not an in-memory shortcut) for EVERY known-positive and
    known-negative case, and pass."""
    out = W.self_test(tmp_dir=tmp_path)
    assert "SELF-TEST" in out
    for case in W._SELFTEST_CASES:
        assert f"[OK] {case}" in out, out


def test_self_test_raises_when_a_case_would_misclassify(tmp_path, monkeypatch):
    """Mutation-sensitive: if classify_stall regressed (e.g. busy/idle swapped), the self-test
    must FAIL CLOSED and raise, never silently report all-OK."""
    orig = W.classify_stall

    def _broken(*a, **k):
        r = orig(*a, **k)
        # flip RUNAWAY-SUSPECT <-> WEDGE to simulate a regression
        if r == "RUNAWAY-SUSPECT (busy)":
            return "WEDGE (idle)"
        if r == "WEDGE (idle)":
            return "RUNAWAY-SUSPECT (busy)"
        return r
    monkeypatch.setattr(W, "classify_stall", _broken)
    with pytest.raises(W.SelfTestFailure):
        W.self_test(tmp_dir=tmp_path)


def test_self_test_runs_without_a_tmp_dir_argument_and_cleans_up(tmp_path, monkeypatch):
    """P42: the default (no explicit tmp_dir) path writes under $STACK_WORKDIR/m54/tmp."""
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    out = W.self_test()
    assert "SELF-TEST" in out
    assert "[OK] progressing" in out
    assert not list(tmp_path.glob("m54/tmp/*"))   # cleaned up after self_test() returns


def test_selftest_rows_fixture_is_exactly_three_rows():
    assert len(W.SELFTEST_ROWS) == 3


# --------------------------------------------------------------------------- CLI / run_watch loop
def _write_rows(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_run_watch_once_appends_selftest_and_one_tick(tmp_path):
    rows_path = tmp_path / "rows.jsonl"
    _write_rows(rows_path, [_row("a")])
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"model": "m"}), encoding="utf-8")
    out_path = tmp_path / "watch.log"
    import argparse
    args = argparse.Namespace(rows=str(rows_path), manifest=str(manifest_path), total=5,
                              driver_pid=os.getpid(), router_log=str(tmp_path / "router.log"),
                              out=str(out_path), interval=300.0, stall_s=2700.0, once=True)
    rc = W.run_watch(args)
    assert rc == 0
    content = out_path.read_text(encoding="utf-8")
    assert "SELF-TEST" in content
    assert "model=m" in content
    assert content.count("PROGRESSING") == 2   # one self-test bundled-fixture block + one real tick


def test_run_watch_prints_a_calibration_line_on_the_first_tick_P52c(tmp_path):
    """8th cold review round 8 P52(c): the first tick of a live run must print a CALIBRATION line
    (worker CPU, ideally during an in-flight request) -- a `calibrate_fn` is injected via `args`
    to avoid the real ~3s worker_busy() subprocess/sleep cost in this unit test."""
    rows_path = tmp_path / "rows.jsonl"
    _write_rows(rows_path, [_row("a")])
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"model": "m", "router": {"pid": ROUTER_PID}}), encoding="utf-8")
    out_path = tmp_path / "watch.log"
    import argparse
    args = argparse.Namespace(rows=str(rows_path), manifest=str(manifest_path), total=5,
                              driver_pid=os.getpid(), router_log=str(tmp_path / "router.log"),
                              out=str(out_path), interval=300.0, stall_s=2700.0, once=True,
                              calibrate_fn=lambda router_pid: True)
    rc = W.run_watch(args)
    assert rc == 0
    content = out_path.read_text(encoding="utf-8")
    assert f"CALIBRATION (tick 1): worker_busy=True (router_pid={ROUTER_PID})" in content


def test_run_watch_prints_a_calibration_line_with_no_router_pid_yet_P52c(tmp_path):
    rows_path = tmp_path / "rows.jsonl"
    _write_rows(rows_path, [_row("a")])
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"model": "m"}), encoding="utf-8")   # no router pid
    out_path = tmp_path / "watch.log"
    import argparse
    args = argparse.Namespace(rows=str(rows_path), manifest=str(manifest_path), total=5,
                              driver_pid=os.getpid(), router_log=str(tmp_path / "router.log"),
                              out=str(out_path), interval=300.0, stall_s=2700.0, once=True)
    rc = W.run_watch(args)
    assert rc == 0
    content = out_path.read_text(encoding="utf-8")
    assert "CALIBRATION (tick 1): no router pid recorded" in content


def test_run_watch_survives_an_unreadable_rows_file_P52a(tmp_path):
    """8th cold review round 8 P52(a): a permission-denied rows file must produce an UNKNOWN/
    evidence-missing block, NEVER crash the watcher daemon."""
    rows_path = tmp_path / "rows.jsonl"
    _write_rows(rows_path, [_row("a")])
    os.chmod(rows_path, 0)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"model": "m"}), encoding="utf-8")
    out_path = tmp_path / "watch.log"
    import argparse
    args = argparse.Namespace(rows=str(rows_path), manifest=str(manifest_path), total=5,
                              driver_pid=os.getpid(), router_log=str(tmp_path / "router.log"),
                              out=str(out_path), interval=300.0, stall_s=2700.0, once=True)
    try:
        rc = W.run_watch(args)   # must not raise
    finally:
        os.chmod(rows_path, 0o644)   # restore so tmp_path cleanup can remove it
    assert rc == 0
    content = out_path.read_text(encoding="utf-8")
    assert "EVIDENCE MISSING" in content
    assert "rows file missing/unreadable" in content


def test_readable_false_for_a_permission_denied_file(tmp_path):
    p = tmp_path / "secret.jsonl"
    p.write_text("x", encoding="utf-8")
    os.chmod(p, 0)
    try:
        assert W._readable(p) is False
    finally:
        os.chmod(p, 0o644)


def test_readable_true_for_a_normal_file(tmp_path):
    p = tmp_path / "ok.jsonl"
    p.write_text("x", encoding="utf-8")
    assert W._readable(p) is True


def test_read_rows_does_not_raise_on_a_permission_denied_file_P52a(tmp_path):
    p = tmp_path / "secret.jsonl"
    _write_rows(p, [_row("a")])
    os.chmod(p, 0)
    try:
        assert W.read_rows(p) == []   # degrades, never raises
    finally:
        os.chmod(p, 0o644)


# --------------------------------------------------------------------------- P52(d) calibration gate
def test_classify_stall_refuses_to_label_wedge_when_not_calibrated_this_run():
    """8th cold review round 8 P52(d): an idle busy-check with NO prior BUSY sample observed in
    this run must NOT be labelled WEDGE -- the busy-detection mechanism itself is unproven and
    could be silently broken, which would otherwise manufacture a false kill recommendation every
    single time."""
    label = W.classify_stall(3000.0, 2700.0, os.getpid(), busy_check_fn=lambda: False,
                             calibrated=False)
    assert label is not None and label.startswith("UNKNOWN") and "not yet calibrated" in label


def test_classify_stall_labels_wedge_once_calibrated():
    label = W.classify_stall(3000.0, 2700.0, os.getpid(), busy_check_fn=lambda: False,
                             calibrated=True)
    assert label == "WEDGE (idle)"


def test_classify_stall_calibrated_default_preserves_prior_behaviour():
    """The default `calibrated=True` means every PRE-EXISTING caller that doesn't pass this new
    parameter keeps the exact prior WEDGE behaviour."""
    label = W.classify_stall(3000.0, 2700.0, os.getpid(), busy_check_fn=lambda: False)
    assert label == "WEDGE (idle)"


def test_build_assessment_busy_observed_box_gates_wedge_across_ticks_P52d():
    """An idle verdict on tick 1 (box empty -- never calibrated) must NOT read WEDGE; a BUSY
    sample on tick 2 calibrates the box; an idle verdict on tick 3 (now calibrated) DOES read
    WEDGE."""
    now = time.time()
    rows = [_row("a", wall_total_s=10.0)]
    box = {}
    busy_sequence = iter([False, True, False])
    block1 = W.build_assessment(rows, 0, 10, os.getpid(), "/nonexistent", stall_s=0.0,
                                reference_ts=now - 5000, now=now,
                                busy_check_fn=lambda: next(busy_sequence), busy_observed_box=box)
    assert "WEDGE (idle)" not in block1 and "UNKNOWN (busy-detection not yet calibrated" in block1
    block2 = W.build_assessment(rows, 0, 10, os.getpid(), "/nonexistent", stall_s=0.0,
                                reference_ts=now - 5000, now=now,
                                busy_check_fn=lambda: next(busy_sequence), busy_observed_box=box)
    assert "RUNAWAY-SUSPECT (busy)" in block2
    assert box["seen"] is True
    block3 = W.build_assessment(rows, 0, 10, os.getpid(), "/nonexistent", stall_s=0.0,
                                reference_ts=now - 5000, now=now,
                                busy_check_fn=lambda: next(busy_sequence), busy_observed_box=box)
    assert "WEDGE (idle)" in block3


def test_run_watch_exits_when_driver_dead_and_rows_complete(tmp_path):
    rows_path = tmp_path / "rows.jsonl"
    _write_rows(rows_path, [_row("a"), _row("b")])
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    out_path = tmp_path / "watch.log"
    import argparse
    args = argparse.Namespace(rows=str(rows_path), manifest=str(manifest_path), total=2,
                              driver_pid=2**30, router_log=str(tmp_path / "router.log"),
                              out=str(out_path), interval=0.01, stall_s=2700.0, once=False)
    rc = W.run_watch(args)
    assert rc == 0   # returned on its own (driver dead + rows==total), not via --once


def test_run_watch_exits_immediately_when_driver_dead_even_with_rows_incomplete_addendum_E(tmp_path):
    """Addendum E: a driver that crashed EARLY (rows < total) must not be watched forever -- the
    watcher exits after reporting the DRIVER DEAD tick, regardless of row count."""
    rows_path = tmp_path / "rows.jsonl"
    _write_rows(rows_path, [_row("a")])
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    out_path = tmp_path / "watch.log"
    import argparse
    args = argparse.Namespace(rows=str(rows_path), manifest=str(manifest_path), total=144,
                              driver_pid=2**30, router_log=str(tmp_path / "router.log"),
                              out=str(out_path), interval=0.01, stall_s=2700.0, once=False)
    rc = W.run_watch(args)
    assert rc == 0
    content = out_path.read_text(encoding="utf-8")
    assert "DRIVER DEAD" in content


def test_run_watch_refuses_when_self_test_fails(tmp_path, monkeypatch):
    rows_path = tmp_path / "rows.jsonl"
    manifest_path = tmp_path / "manifest.json"
    out_path = tmp_path / "watch.log"

    def _boom(*a, **k):
        raise W.SelfTestFailure("fake failure")
    monkeypatch.setattr(W, "self_test", _boom)
    import argparse
    args = argparse.Namespace(rows=str(rows_path), manifest=str(manifest_path), total=5,
                              driver_pid=os.getpid(), router_log=str(tmp_path / "router.log"),
                              out=str(out_path), interval=300.0, stall_s=2700.0, once=True)
    rc = W.run_watch(args)
    assert rc == 2


# --------------------------------------------------------------------------- P31 path confinement
def test_main_refuses_out_outside_confined_roots(tmp_path, monkeypatch):
    """7th cold review round 7 addendum R7: `--once` is MANDATORY here, not cosmetic -- without
    it, a MUTANT that removed/weakened the confine_path() refusal would fall through into
    run_watch()'s tick loop with `--driver-pid` pointing at THIS live pytest process (never dies)
    and `total=1` never satisfied (no rows file), so the test would hang at the 300s default
    --interval FOREVER instead of failing fast. `--once` bounds run_watch to a single tick
    regardless of what the mutant did, so a weakened check still shows up as `rc == 0` (wrong),
    not a wedged test run."""
    monkeypatch.delenv("STACK_WORKDIR", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "empty-xdg"))
    rc = W.main(["--rows", str(tmp_path / "rows.jsonl"), "--manifest", str(tmp_path / "m.json"),
               "--total", "1", "--driver-pid", str(os.getpid()),
               "--router-log", str(tmp_path / "r.log"), "--out", str(tmp_path / "watch.log"),
               "--once"])
    assert rc == 2


def test_main_accepts_out_under_stack_workdir(tmp_path, monkeypatch):
    """R7: `--once` added for the same reason/symmetry as the refusal test above, even though
    this one's dead --driver-pid already bounds it to one tick today -- a future change to the
    dead-driver exit condition must not silently reintroduce a hang here too."""
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path))
    rows_path = tmp_path / "rows.jsonl"
    _write_rows(rows_path, [_row("a")])
    rc = W.main(["--rows", str(rows_path), "--manifest", str(tmp_path / "m.json"),
               "--total", "1", "--driver-pid", str(2 ** 30),
               "--router-log", str(tmp_path / "r.log"), "--out", str(tmp_path / "watch.log"),
               "--once"])
    assert rc == 0
