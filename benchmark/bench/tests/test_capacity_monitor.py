import threading

from bench.capacity_monitor import CapacityMonitor, assess


def test_baseline_eta_uses_measured_mean_ratio_and_names_flat_progress():
    rows = [{"execution_status": "completed", "elapsed_s": 20, "retrieval_acc": 1.},
            {"execution_status": "completed", "elapsed_s": 60, "retrieval_acc": 1.}]
    result = assess(rows, [10, 30, 60], total=3, previous=2,
                    stage="rung 300", stage_elapsed=15)
    assert result["completed_rungs"] == 2
    assert result["progress_delta"] == 0
    assert result["mean_rung_s"] == 40
    assert result["max_rung_s"] == 60
    assert result["observed_to_baseline_ratio"] == 2
    assert result["remaining_s_estimate"] == 105
    assert "non-streaming" in result["progress_note"]
    assert "five-item" not in str(result)


def test_unknown_forecast_and_failure_not_called_healthy():
    result = assess([], None, total=3, previous=0, stage="calibration", stage_elapsed=300)
    assert result["remaining_s_estimate"] is None
    assert result["observed_to_baseline_ratio"] is None
    assert "unavailable" in result["rate_note"]
    result = assess([{"execution_status": "error", "error": "timeout", "elapsed_s": 100}],
                    [10, 20], total=2, previous=0, stage="rung 100", stage_elapsed=100)
    assert result["errors"] == 1
    assert result["completed_rungs"] == 0
    assert result["correction"].startswith("STOP")


def test_real_daemon_selftest_periodic_and_terminal_events():
    events = []
    periodic = threading.Event()
    def sink(event):
        events.append(event)
        if event["event"] == "periodic":
            periodic.set()
    monitor = CapacityMonitor(1, [10], emit=sink, interval=.01)
    with monitor:
        monitor.stage("rung 100")
        assert periodic.wait(1), "daemon never produced periodic assessment"
        monitor.record({"execution_status": "completed", "elapsed_s": 10, "retrieval_acc": 1.})
        monitor.exit_code = 0
    assert events[0]["event"] == "SELFTEST"
    assert events[0]["known_positive"]["completed_rungs"] == 1
    assert events[-1]["event"] == "runner-exit"
    assert events[-1]["exit_code"] == 0
    assert events[-1]["completed_rungs"] == 1
    assert not monitor.thread.is_alive()


def test_exception_produces_failed_terminal_event():
    events = []
    try:
        with CapacityMonitor(1, [10], emit=events.append):
            raise RuntimeError("broken")
    except RuntimeError:
        pass
    assert events[-1]["event"] == "runner-exit"
    assert events[-1]["exit_code"] != 0


def test_failed_periodic_sink_cannot_report_success():
    import pytest
    events = []
    def sink(event):
        if event['event'] == 'periodic':
            raise OSError('log sink failed')
        events.append(event)
    monitor = CapacityMonitor(1, [10], emit=sink, interval=.01)
    with pytest.raises(RuntimeError, match='monitor failed'):
        with monitor:
            assert monitor.failed.wait(1)
            monitor.exit_code = 0
    assert events[-1]['exit_code'] != 0


def test_overdue_rung_does_not_promise_zero_remaining_time():
    result = assess([], [10], total=1, previous=0, stage='rung 100', stage_elapsed=100)
    assert result['remaining_s_estimate'] is None
    assert result['correction'].startswith('REVIEW')


def test_error_attempt_is_not_completed_progress():
    result = assess([{'execution_status': 'error', 'error': 'HTTP500'}], [10],
                    total=1, previous=0, stage='between rungs', stage_elapsed=0)
    assert result['progress_delta'] == 0
    assert result['attempted_rungs'] == 1
