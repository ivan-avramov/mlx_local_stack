"""The monitor must EVALUATE, not just report — the cadence has to survive without an agent present.

Two hour-long reporting gaps happened because the agent driving the run only executes when the operator
sends a message. So the four AGENTS.md questions are answered by the daemon, and these tests pin the
parts that make a tick actionable rather than decorative.
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "bench_watch", Path(__file__).resolve().parents[2] / "m1" / "bench_watch.py")
BW = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BW)


def _row(wall=25.0, ct=2000, conv=True, err=None, degen=False):
    r = {"id": 1, "wall_s": wall, "completion_tokens": ct, "converged": conv,
         "finish_reason": "stop", "thinking_budget": 81920}
    if err:
        r["error"] = err
    r["reasoning_stats"] = ({"chars": 170000, "lines": 22, "unique_line_ratio": 1.0,
                             "max_line_repeat": 1, "ngram8_unique": 0.01} if degen else
                            {"chars": 30000, "lines": 400, "unique_line_ratio": 0.9,
                             "max_line_repeat": 2, "ngram8_unique": 0.75})
    return r


def _assess(rows, prev, flat=0, rates=None, total=100, monkeypatch=None):
    BW._rows = lambda m, b: rows
    return BW.assess("M", "ifeval", total, prev, flat, rates or [])


def test_progress_is_measured_against_the_counters_OWN_previous_value():
    rep, n, flat, _ = _assess([_row()] * 10, prev=7)
    assert "+3 since last tick" in rep and n == 10 and flat == 0


def test_a_flat_tick_is_NAMED_not_glossed():
    rep, _, flat, _ = _assess([_row()] * 10, prev=10)
    assert "FLAT for 1 tick" in rep and flat == 1


def test_repeated_flat_ticks_ESCALATE_with_how_to_tell_stall_from_long_tail():
    rep, _, flat, _ = _assess([_row()] * 10, prev=10, flat=2)
    assert flat == 3
    assert "INVESTIGATE" in rep
    assert "long-tail" in rep and "stall" in rep
    assert "worker busy" in rep, "must warn against reading busyness as progress"


def test_eta_uses_the_MEAN_not_the_median():
    """Right-tailed: one 400s item among 25s items. A median ETA would understate by ~2x."""
    rows = [_row(wall=25.0)] * 9 + [_row(wall=400.0)]
    rep, *_ = _assess(rows, prev=9, total=110)
    mean_eta = 100 * ((9 * 25 + 400) / 10) / 3600
    assert f"ETA {mean_eta:.1f}h" in rep
    assert "median 25.0s" in rep, "the median is still shown, just not used for the ETA"


def test_a_rate_COLLAPSE_is_flagged_with_a_likely_cause():
    rows = [_row(wall=25.0)] * 20 + [_row(wall=450.0, ct=52409)]
    rep, *_ = _assess(rows, prev=20, rates=[10, 11, 9], total=200)
    assert "rate 1/tick" in rep
    assert "right-tail item likely" in rep
    assert "52409 tok" in rep, "name the suspect item, not just the symptom"


def test_a_high_error_share_demands_ACTION_not_investigation():
    rows = [_row(err="boom")] * 5 + [_row()] * 5
    rep, *_ = _assess(rows, prev=0)
    assert "ACT:" in rep and "harness errors" in rep


def test_degenerate_loops_are_surfaced_by_WALL_SHARE_not_just_count():
    """1 loop in 10 rows is 4% of rows but can be a third of the wall-clock."""
    rows = [_row(wall=25.0)] * 9 + [_row(wall=450.0, degen=True)]
    rep, *_ = _assess(rows, prev=9)
    assert "degen=1" in rep
    assert "wall 67%" in rep


def test_a_healthy_tick_says_correction_none_explicitly():
    rep, *_ = _assess([_row()] * 10, prev=5)
    assert "4 CORRECTION none" in rep


def test_error_rows_are_excluded_from_the_rate_and_wall_statistics():
    """An error row has no wall_s to contribute; including it would distort the ETA."""
    rows = [_row()] * 5 + [_row(err="x")] * 5
    rep, n, *_ = _assess(rows, prev=0)
    assert n == 10, "n counts all rows, matching the file"
    assert "errors=5" in rep


# ------------------------------------------------------------ queued != stalled (false-alarm fix)
def test_a_model_that_has_not_STARTED_is_queued_not_stalled():
    """Shipped with a false positive: the driver runs models sequentially, so the second sits at n=0
    for hours and escalated to INVESTIGATE every tick while the first was progressing normally. An
    alert that fires on healthy state trains the reader to ignore it — which defeats the whole point
    of putting the cadence in a daemon.
    """
    BW._rows = lambda m, b: []
    rep, n, flat, _ = BW.assess("M", "ifeval", 100, 0, 8, [], started=False)
    assert n == 0
    assert "QUEUED" in rep, "a not-yet-started model must say so"
    assert "INVESTIGATE" not in rep, "and must not escalate"


def test_a_started_model_that_goes_flat_STILL_escalates():
    """The fix must not silence the real signal."""
    BW._rows = lambda m, b: [_row()] * 10
    rep, _, flat, _ = BW.assess("M", "ifeval", 100, 10, 2, [], started=True)
    assert flat == 3 and "INVESTIGATE" in rep


def test_a_model_at_zero_rows_is_treated_as_started_once_it_has_ever_had_rows():
    """started=True with n=0 would mean rows VANISHED — that is a real problem, not a queue."""
    BW._rows = lambda m, b: []
    rep, *_ = BW.assess("M", "ifeval", 100, 5, 0, [], started=True)
    assert "QUEUED" not in rep
