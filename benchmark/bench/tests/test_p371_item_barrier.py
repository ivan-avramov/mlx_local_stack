"""P371 phase 1: `bench.item_barrier` (plan 3.1, R23): the generation-neutral per-item file barrier in the probe."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from bench import item_barrier as ib
from bench import arm_runner
from bench import token_turn_gate as tg


class Clock:
    """Deterministic time: `sleep` advances it and runs the scripted action at that moment."""

    def __init__(self, actions=()):
        self.t, self.actions = 0.0, list(actions)

    def clock(self):
        return self.t

    def sleep(self, s):
        self.t += s
        while self.actions and self.actions[0][0] <= self.t:
            self.actions.pop(0)[1]()


def barrier(tmp_path, *, enabled=True, timeout_s=10.0, cancel=None, clock=None, **kw):
    clock = clock or Clock()
    return ib.ItemBarrier(tmp_path / "run", enabled, timeout_s, cancel, clock=clock.clock, sleep=clock.sleep,
                          poll_s=0.5, **kw), clock


def touch(path):
    Path(path).write_text("")


def test_the_timing_constants_are_the_manifest_acks():
    assert ib.ACK_TIMEOUT_S == arm_runner.ACK_TIMEOUT_S and ib.ACK_POLL_S == arm_runner.ACK_POLL_S


def test_disabled_writes_no_files_and_never_waits(tmp_path):
    b, clock = barrier(tmp_path, enabled=False)
    assert b.ready(1) == "go" and b.done(1, dict(id="python/foo")) == "continue"
    assert clock.t == 0.0 and list(tmp_path.iterdir()) == []


def test_ready_writes_its_file_and_returns_go_when_the_chain_acks(tmp_path):
    clock = Clock()
    b, _ = barrier(tmp_path, clock=clock)
    clock.actions = [(1.0, lambda: touch(tmp_path / "run.item3.go"))]
    assert b.ready(3) == "go"
    assert (tmp_path / "run.item3.ready").exists() and clock.t == 1.0


def test_a_stop_file_at_ready_returns_stop_and_wins_over_go(tmp_path):
    b, clock = barrier(tmp_path)
    clock.actions = [(0.5, lambda: (touch(tmp_path / "run.item1.go"), touch(tmp_path / "run.item1.stop")))]
    assert b.ready(1) == "stop"


def test_done_writes_the_record_then_waits_for_continue_or_stop(tmp_path):
    b, clock = barrier(tmp_path)
    clock.actions = [(0.5, lambda: touch(tmp_path / "run.item1.continue"))]
    record = dict(id="python/foo", row_key=["python/foo", 0], evidence={"transcript": dict(path="p", sha256="a" * 64)})
    assert b.done(1, record) == "continue"
    assert json.loads((tmp_path / "run.item1.done").read_text()) == record
    b2, clock2 = barrier(tmp_path)
    clock2.actions = [(0.5, lambda: touch(tmp_path / "run.item2.stop"))]
    assert b2.done(2, record) == "stop"


def test_files_are_exclusive_create_and_leave_no_temp_files(tmp_path):
    b, clock = barrier(tmp_path)
    touch(tmp_path / "run.item1.go")
    assert b.ready(1) == "go"
    with pytest.raises(ib.BarrierError):
        b.ready(1)                                            # a second `ready` for the same item must not overwrite
    assert sorted(p.name for p in tmp_path.iterdir()) == ["run.item1.go", "run.item1.ready"]
    touch(tmp_path / "run.item1.continue")
    b.done(1, {"a": 1})
    with pytest.raises(ib.BarrierError):
        b.done(1, {"a": 2})
    assert json.loads((tmp_path / "run.item1.done").read_text()) == {"a": 1}


def test_a_missing_ack_times_out_with_a_transport_abort(tmp_path):
    b, clock = barrier(tmp_path, timeout_s=3.0)
    with pytest.raises(ib.BarrierTimeout, match="not acknowledged") as exc:
        b.ready(1)
    assert isinstance(exc.value, tg.TransportAbort) and clock.t >= 3.0
    b2, _ = barrier(tmp_path, timeout_s=1.0)
    with pytest.raises(ib.BarrierTimeout):
        b2.done(2, {})


def test_cancel_is_honoured_while_waiting_and_the_exception_is_injectable(tmp_path):
    state = {"cancel": False}
    clock = Clock([(1.0, lambda: state.update(cancel=True))])
    b, _ = barrier(tmp_path, cancel=lambda: state["cancel"], clock=clock)
    with pytest.raises(ib.BarrierCancelled):
        b.ready(1)
    state["cancel"] = True

    class Mine(Exception):
        pass
    b2, _ = barrier(tmp_path, cancel=lambda: state["cancel"], cancel_exc=Mine)
    with pytest.raises(Mine):
        b2.done(5, {})


def test_an_ack_already_present_wins_over_a_pending_cancel(tmp_path):
    touch(tmp_path / "run.item1.go")                          # as `_wait_for_ack`: existence is checked first
    b, _ = barrier(tmp_path, cancel=lambda: True)
    assert b.ready(1) == "go"


def test_item_indexes_are_validated(tmp_path):
    b, _ = barrier(tmp_path)
    for bad in (-1, "1", True, 1.5):
        with pytest.raises(ValueError):
            b.ready(bad)


def test_a_real_threaded_ack_with_the_wall_clock(tmp_path):
    b = ib.ItemBarrier(tmp_path / "wall", True, 5.0, None, poll_s=0.01)
    threading.Timer(0.1, lambda: touch(tmp_path / "wall.item0.go")).start()
    assert b.ready(0) == "go"
    assert tmp_path.joinpath("wall.item0.ready").exists()
