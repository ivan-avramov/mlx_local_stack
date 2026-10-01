"""M54 watcher daemon (bench/agentbench_watch.py): AGENTS.md's four standing questions, answered
from rows on disk only (read-only, never perturbs the run), plus the known-positive self-test.
No docker, no network, no real sleeping -- `--once` and injectable pid/router-activity functions
make every branch testable synchronously."""
import json
import os
import time

import pytest

import bench.agentbench_watch as W


def _row(id_, group=1, passed=True, outcome="solved", turns=1, answer="42", wall_s=2.0,
        completion_tokens_total=50, exec_timeout=False, shell_died=False, setup_error=False,
        converged=True, budget_hits=0, gold_prepare=None, gold_live=None):
    return {"id": id_, "group": group, "passed": passed, "outcome": outcome, "turns": turns,
           "answer": answer, "wall_s": wall_s, "completion_tokens_total": completion_tokens_total,
           "exec_timeout": exec_timeout, "shell_died": shell_died, "setup_error": setup_error,
           "converged": converged, "budget_hits": budget_hits, "gold_prepare": gold_prepare,
           "gold_live": gold_live}


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


# --------------------------------------------------------------------------- rate / ETA (mean, not median)
def test_eta_uses_the_mean_not_the_median():
    rows = [_row("a", wall_s=1.0), _row("b", wall_s=1.0), _row("c", wall_s=100.0)]
    stats = W.rate_stats(rows)
    assert stats["mean_wall_s"] == pytest.approx(34.0)   # (1+1+100)/3, NOT the median (1.0)
    eta = W.eta_seconds(total=10, done=3, mean_wall_s=stats["mean_wall_s"])
    assert eta == pytest.approx(7 * 34.0)


def test_eta_none_without_any_completed_rows():
    assert W.eta_seconds(total=10, done=0, mean_wall_s=None) is None
    assert W.rate_stats([])["mean_wall_s"] is None


def test_rate_stats_reports_max_wall_seen():
    rows = [_row("a", wall_s=5.0), _row("b", wall_s=40.0)]
    assert W.rate_stats(rows)["max_wall_s"] == 40.0


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


# --------------------------------------------------------------------------- stall / wedge classification
def test_classify_stall_none_when_within_threshold():
    assert W.classify_stall(100.0, stall_s=2700.0, driver_pid=1, router_log_path="x") is None


def test_classify_stall_driver_dead():
    label = W.classify_stall(3000.0, stall_s=2700.0, driver_pid=999999, router_log_path="x",
                             pid_alive_fn=lambda pid: False)
    assert label == "DRIVER DEAD"


def test_classify_stall_runaway_suspect_when_router_busy():
    label = W.classify_stall(3000.0, stall_s=2700.0, driver_pid=1, router_log_path="x",
                             pid_alive_fn=lambda pid: True, router_active_fn=lambda *a, **k: True)
    assert label == "RUNAWAY-SUSPECT (busy)"


def test_classify_stall_wedge_when_router_idle():
    label = W.classify_stall(3000.0, stall_s=2700.0, driver_pid=1, router_log_path="x",
                             pid_alive_fn=lambda pid: True, router_active_fn=lambda *a, **k: False)
    assert label == "WEDGE (idle)"


def test_pid_alive_true_for_self():
    assert W.pid_alive(os.getpid()) is True


def test_pid_alive_false_for_a_pid_that_does_not_exist():
    assert W.pid_alive(2**30) is False


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


def test_router_recently_active_false_when_log_missing(tmp_path):
    assert W.router_recently_active(tmp_path / "nope.log", window_s=600, now=time.time()) is False


# --------------------------------------------------------------------------- build_assessment / tick
def test_build_assessment_progressing_true_when_rows_grew():
    now = time.time()
    rows = [_row("a"), _row("b")]
    block = W.build_assessment(rows, prev_rows_count=1, total=10, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               last_row_mtime=now, now=now)
    assert "(1) PROGRESSING: yes" in block
    assert "rows 1 -> 2" in block


def test_build_assessment_not_progressing_when_rows_flat():
    now = time.time()
    rows = [_row("a")]
    block = W.build_assessment(rows, prev_rows_count=1, total=10, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               last_row_mtime=now, now=now)
    assert "(1) PROGRESSING: NO" in block


def test_build_assessment_includes_eta_from_mean():
    now = time.time()
    rows = [_row("a", wall_s=10.0), _row("b", wall_s=10.0)]
    block = W.build_assessment(rows, prev_rows_count=0, total=4, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               last_row_mtime=now, now=now)
    assert "ETA=0.3 min" in block   # (4-2)*10s = 20s = 0.33 min
    assert "from the MEAN, never the median" in block


def test_build_assessment_stall_section_none_when_recent():
    now = time.time()
    rows = [_row("a")]
    block = W.build_assessment(rows, prev_rows_count=0, total=10, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               last_row_mtime=now, now=now)
    assert "(4) STALL: none" in block


def test_build_assessment_stall_section_reports_wedge():
    now = time.time()
    rows = [_row("a")]
    block = W.build_assessment(rows, prev_rows_count=0, total=10, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=100.0,
                               last_row_mtime=now - 500, now=now,
                               pid_alive_fn=lambda pid: True, router_active_fn=lambda *a, **k: False)
    assert "(4) STALL: WEDGE (idle)" in block
    assert "NEVER killing anything" in block


def test_build_assessment_emits_a_grep_friendly_summary_line():
    now = time.time()
    rows = [_row("a", passed=True), _row("b", passed=False)]
    block = W.build_assessment(rows, prev_rows_count=0, total=5, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               last_row_mtime=now, now=now)
    summary_lines = [l for l in block.splitlines() if l.startswith("SUMMARY")]
    assert len(summary_lines) == 1
    assert "done=2/5" in summary_lines[0]
    assert "passed=1" in summary_lines[0] and "failed=1" in summary_lines[0]


def test_build_assessment_sanity_line_mentions_all_required_counters():
    now = time.time()
    block = W.build_assessment([_row("a")], prev_rows_count=0, total=5, driver_pid=os.getpid(),
                               router_log_path="/nonexistent", stall_s=2700.0,
                               last_row_mtime=now, now=now)
    for key in ("outcome_counts", "exec_timeout", "shell_died", "setup_error",
               "gold_prepare_differs", "converged_false", "budget_hits_total", "turns_histogram",
               "completion_tokens_mean", "empty_answers", "long_answers",
               "same_as_previous_answer", "per_group_pass_rate"):
        assert key in block, key


# --------------------------------------------------------------------------- self-test (known-positive)
def test_self_test_runs_without_touching_disk_and_mentions_itself():
    out = W.self_test()
    assert "SELF-TEST" in out
    assert "done=3/3" in out   # SUMMARY line, from the 3-row fixture
    assert "PROGRESSING" in out


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
    assert content.count("PROGRESSING") == 2   # one self-test block + one real tick


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
