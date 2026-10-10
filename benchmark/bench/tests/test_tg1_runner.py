"""M62 scheduling, isolated dispatch and run integration."""

import json
import sys
import threading
import time
from pathlib import Path
import pytest
from bench import tg1_runner as runner
from bench import structured_grade as sg
from bench.token_turn_gate import TokenTurnGate, TransportAbort
from bench.tests.test_token_turn_gate import usage
from bench.tests.test_opencode_v2_probe import probe, fixture_probe, MODEL


def test_slow_grading_backlog_and_exit_during_grade(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "a").write_text("first")
    gate = TokenTurnGate(3)
    lock = threading.RLock()
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def grade(snap):
        calls.append(snap.boundary)
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)
        return (2, False)

    worker = runner.GradeWorker(gate, lock, work, tmp_path, grade)
    worker.start()
    try:
        with lock:
            worker.notify(1)
            gate.complete("one", usage(81920))
        assert entered.wait(3)
        (work / "a").write_text("second")
        with lock:
            for n in range(2, 6):
                worker.notify(n)
                gate.complete(str(n), usage(100))
        assert len(gate.request_usage) == 5 and gate.stop_reason is None
        release.set()
        worker.finish()
        assert gate.last_progress_boundary == 1 and gate.no_progress_tokens == 400
        assert calls == [1, 5] and not gate.pending
    finally:
        release.set()
        worker.finish()


@pytest.mark.parametrize("scaffold", ["opencode-v2", "opencode-v2-web"])
def test_legacy_never_constructs_tg1(probe, monkeypatch, tmp_path, scaffold):
    f = fixture_probe(probe, monkeypatch, tmp_path)
    monkeypatch.setattr(
        runner, "main", lambda *a: pytest.fail("legacy constructed tg1")
    )
    assert f["run"]("one", extra=["--scaffold", scaffold]) == 0
    assert not list(tmp_path.rglob("toolbounds.js"))


@pytest.mark.parametrize(
    "flag",
    [
        "--tick-s",
        "--first-write-tokens",
        "--hard-ceiling-s",
        "--stall-ticks",
        "--loop-repeats",
        "--poll-s",
    ],
)
def test_tg1_refuses_legacy_flags_before_decode_table(probe, monkeypatch, flag):
    monkeypatch.setattr(
        probe, "_gate_window", lambda *a, **k: pytest.fail("read decode rates")
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "probe",
            "--model",
            MODEL,
            "--items",
            "one",
            "--seed-base",
            "1",
            "--scaffold",
            "opencode-v2-web-tg1",
            flag,
            "1",
        ],
    )
    with pytest.raises(SystemExit, match="REFUSED"):
        probe.main()


def test_carrier_budget_context_and_metrics_refusal():
    model = {
        "body": {"thinking_budget": 81920, "max_tokens": 102400},
        "limit": {"context": 262144},
    }
    runner.validate_worker(
        model, {"configured_context_limit": 262144}, {"summary": {"in_flight": 0}}
    )
    for mutated in [
        {**model, "body": {"thinking_budget": 1, "max_tokens": 102400}},
        {**model, "limit": {"context": 1}},
    ]:
        with pytest.raises(TransportAbort):
            runner.validate_worker(
                mutated,
                {"configured_context_limit": 262144},
                {"summary": {"in_flight": 0}},
            )


def test_export_bounds_rejection_count_exact():
    export = {
        "messages": [
            {
                "content": [
                    {
                        "type": "tool",
                        "name": "shell",
                        "state": {
                            "status": "error",
                            "error": {"message": "M62_TOOL_BOUND: bound"},
                        },
                    },
                    {
                        "type": "tool",
                        "name": "shell",
                        "state": {"status": "completed", "content": "M62_TOOL_BOUND:"},
                    },
                    {
                        "type": "tool",
                        "name": "write",
                        "state": {
                            "status": "error",
                            "error": {"message": "M62_TOOL_BOUND:"},
                        },
                    },
                ]
            }
        ]
    }
    assert runner.tool_bounds_rejections(export) == 1


def test_k_and_ceiling_skip_unnecessary_grading(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "a").write_text("x")
    gate = TokenTurnGate(1)
    lock = threading.RLock()
    worker = runner.GradeWorker(
        gate, lock, work, tmp_path, lambda snap: pytest.fail("graded mandatory stop")
    )
    with lock:
        worker.notify(1)
        gate.complete("one", usage(327680))
        worker.start()
    worker.finish()
    assert gate.stop_reason == "hard_ceiling"


def test_f11_slow_grader_edits_every_request_still_stalls(tmp_path):
    work = tmp_path / 'work'
    work.mkdir()
    (work / 'a').write_text('first')
    gate = TokenTurnGate(3)
    lock = threading.RLock()
    entered = threading.Event()
    release = threading.Event()
    def grade(snap):
        entered.set()
        assert release.wait(3)
        return 3, False
    worker = runner.GradeWorker(gate, lock, work, tmp_path, grade)
    from bench.token_turn_gate import EventStream
    from bench.tests.test_token_turn_gate import request
    stream = EventStream(gate, worker.notify)
    worker.start()
    try:
        with lock:
            request(stream, output=81920)
        assert entered.wait(3)
        for j in range(2,10):
            (work / 'a').write_text(str(j))
            with lock:
                request(stream, str(j), output=1)
        assert gate.stop_reason is None
        release.set()
        worker.finish()
        assert gate.stop_reason == 'stalled'
        assert gate.first_crossing_request == 1 and gate.output_tokens < 327680
    finally:
        release.set()
        worker.finish()


def test_f2_ungradeable_manifest_retried(tmp_path):
    work = tmp_path / 'work'
    work.mkdir()
    (work / 'a').write_text('a')
    gate = TokenTurnGate(3)
    lock = threading.RLock()
    graded = threading.Event()
    calls = []
    def grade(snap):
        calls.append(snap.boundary)
        graded.set()
        return None, False
    worker = runner.GradeWorker(gate, lock, work, tmp_path, grade)
    from bench.token_turn_gate import EventStream
    from bench.tests.test_token_turn_gate import request
    stream = EventStream(gate, worker.notify)
    worker.start()
    try:
        with lock: request(stream)
        assert graded.wait(3)
        # Finish the first grade without changing the manifest.
        deadline = time.monotonic() + 3
        while gate.pending and time.monotonic() < deadline:
            time.sleep(0.001)
        assert not gate.pending and worker.last_manifest is None
        with lock: request(stream, 'm2')
        worker.finish()
        assert calls == [1,2]
    finally:
        worker.finish()


def test_f11_terminal_join_covers_active_plus_queued_grade(tmp_path, monkeypatch):
    """Spec rev 5 §2: grader timeouts are per grade; the frozen cohort is at most the active grade plus one queued
    capture, so the terminal join allows two full grades plus overhead (Python 300 s → 660 s)."""
    assert runner.grade_join_timeout_s() == 2 * max(sg.TIMEOUTS.values()) + runner.GRADE_JOIN_OVERHEAD_S == 660
    monkeypatch.setattr(sg, "TIMEOUTS", {"python": 0.3, "go": 0.3})
    monkeypatch.setattr(runner, "GRADE_JOIN_OVERHEAD_S", 0.3)
    work = tmp_path / "work"
    work.mkdir()
    (work / "a").write_text("first")
    gate = TokenTurnGate(3)
    lock = threading.RLock()
    entered = threading.Event()
    calls = []

    def grade(snap):
        calls.append(snap.boundary)
        entered.set()
        time.sleep(0.25)   # under one per-grade timeout; two in series exceed one timeout
        return (2, False)

    worker = runner.GradeWorker(gate, lock, work, tmp_path, grade)
    worker.start()
    with lock:
        worker.notify(1)
        gate.complete("one", usage(100))
    assert entered.wait(3)
    (work / "a").write_text("second")
    with lock:
        worker.notify(2)
        gate.complete("two", usage(100))
    worker.finish()   # active + queued = 0.5 s > one 0.3 s timeout, within 2 x 0.3 + 0.3
    assert calls == [1, 2]


def test_f11_terminal_join_still_aborts_a_hung_grader(tmp_path, monkeypatch):
    monkeypatch.setattr(sg, "TIMEOUTS", {"python": 0.1, "go": 0.1})
    monkeypatch.setattr(runner, "GRADE_JOIN_OVERHEAD_S", 0.1)
    work = tmp_path / "work"
    work.mkdir()
    (work / "a").write_text("x")
    gate = TokenTurnGate(3)
    lock = threading.RLock()
    release = threading.Event()
    worker = runner.GradeWorker(gate, lock, work, tmp_path, lambda snap: (release.wait(5), (2, False))[1])
    worker.start()
    with lock:
        worker.notify(1)
        gate.complete("one", usage(100))
    try:
        with pytest.raises(TransportAbort, match="did not finish"):
            worker.finish()
    finally:
        release.set()
