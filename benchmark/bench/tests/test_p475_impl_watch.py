"""P475 stage 1 (implementer tests): bench_watch capacity mode (R9) and the (pid, create_time) binding (R12)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "m1"))
import bench_watch as W  # noqa: E402


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def _rows(path, elapsed):
    path.write_text("".join(json.dumps(dict(ctx=c, elapsed_s=e, execution_status="completed", rung_problems=[])) + "\n"
                            for c, e in zip((8192, 131072, 196608, 260096), elapsed)))


def _lines(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines()]


def test_capacity_mode_needs_its_inputs(tmp_path):
    with pytest.raises(SystemExit):
        W._parse_args(["--capacity-rows", "x", "--out", "o", "--expected-rung-seconds", "1,2"])          # no --driver-pid
    with pytest.raises(SystemExit):
        W._parse_args(["--capacity-rows", "x", "--out", "o", "--driver-pid", "1"])                        # no expectations
    with pytest.raises(SystemExit):
        W._parse_args(["--capacity-rows", "x", "--out", "o", "--driver-pid", "1", "--expected-rung-seconds", "1,-2"])
    with pytest.raises(SystemExit):
        W._parse_args(["--models", "m", "--bench", "b", "--total", "1", "--out", "o", "--driver-create-time", "5"])


def test_capacity_view_rate_and_eta_from_elapsed(tmp_path):
    rows = tmp_path / "ladder.jsonl"
    _rows(rows, [20.0, 400.0])
    v = W.capacity_view(rows, [10.0, 200.0, 300.0, 400.0], since_start_s=500.0)
    assert v["progress"] == dict(done=2, planned=4)
    assert v["rate"]["ratio"] == pytest.approx(420 / 210)
    assert v["rungs"][1]["ratio"] == pytest.approx(2.0)
    assert v["eta"]["pred_eta_s"] == 700.0 and v["eta"]["eta_s"] >= 1400.0 - 1e-9
    assert v["current_rung"] == dict(index=2, expected_s=300.0, elapsed_s=80.0)
    assert v["correction"] is True and "CORRECTION?" in v["note"] and "x2.00" in v["note"]


def test_capacity_view_on_track_and_overrunning_current_rung(tmp_path):
    rows = tmp_path / "ladder.jsonl"
    _rows(rows, [10.0])
    ok = W.capacity_view(rows, [10.0, 100.0], since_start_s=50.0)
    assert ok["correction"] is False and ok["note"].startswith("finish:")
    late = W.capacity_view(rows, [10.0, 100.0], since_start_s=10.0 + 200.0)
    assert late["correction"] is True and "current rung" in late["note"]
    assert W.capacity_view(tmp_path / "missing.jsonl", [5.0], since_start_s=1.0)["progress"] == dict(done=0, planned=1)


def test_capacity_mode_writes_json_ticks_and_an_exit_line(tmp_path, monkeypatch):
    rows, out = tmp_path / "ladder.jsonl", tmp_path / "watch.jsonl"
    _rows(rows, [5.0])
    clock = Clock()
    states = iter(["alive", "alive", "gone"])
    monkeypatch.setattr(W, "_driver_state", lambda pid, bound: (next(states), bound))
    monkeypatch.setattr(W, "_pid_start", lambda pid: (_ for _ in ()).throw(AssertionError("bound by the given create time")))
    rc = W.main(["--capacity-rows", str(rows), "--expected-rung-seconds", "10,20", "--driver-pid", "42",
                 "--driver-create-time", "123.5", "--out", str(out), "--interval", "300"],
                power=lambda: dict(watts=140, volts=28, battery=80, on_battery_intervals=[]), clock=clock, sleep=clock.sleep)
    assert rc == 0
    lines = _lines(out)
    assert [x.get("tick") for x in lines[:-1]] == [0, 1, 2]
    assert all(x["driver"] == dict(pid=42, start=123.5) and x["power_ok"] and x["mode"] == "capacity" for x in lines[:-1])
    assert lines[0]["progress"] == dict(done=1, planned=2) and "eta" in lines[0] and "note" in lines[0]
    end = lines[-1]
    assert end["exit_state"] == "driver_exited" and end["window"] == dict(start=1000.0, end=1600.0) and end["ticks"] == 3
    assert end["battery_intervals"] == []
    assert W.speed_verdict(out)["valid"] is True


def test_capacity_mode_power_failure_is_a_speed_verdict(tmp_path, monkeypatch):
    rows, out = tmp_path / "ladder.jsonl", tmp_path / "watch.jsonl"
    _rows(rows, [])
    clock = Clock()
    states = iter(["alive", "gone"])
    monkeypatch.setattr(W, "_driver_state", lambda pid, bound: (next(states), bound))
    W.main(["--capacity-rows", str(rows), "--expected-rung-seconds", "10", "--driver-pid", "42", "--driver-create-time", "1",
            "--out", str(out)], power=lambda: dict(watts=96, volts=20, battery=80, on_battery_intervals=[]), clock=clock,
           sleep=clock.sleep)
    assert W.speed_verdict(out)["valid"] is False


def test_the_given_create_time_binds_the_driver(monkeypatch):
    """R12: a reused pid (another start time) reads as gone, in the legacy mode too."""
    monkeypatch.setattr(W, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(W, "_pid_start", lambda pid: 999.0)
    assert W._driver_state(42, 123.5) == ("gone", 123.5)
    args = W._parse_args(["--chain-json", "c.json", "--driver-pid", "42", "--driver-create-time", "123.5", "--out", "o"])
    assert W._initial_bound(args) == 123.5
    args = W._parse_args(["--chain-json", "c.json", "--driver-pid", "42", "--out", "o"])
    assert W._initial_bound(args) == 999.0


def test_legacy_mode_with_a_create_time_stops_on_a_reused_pid(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "_pid_alive", lambda pid: True)              # the pid exists …
    monkeypatch.setattr(W, "_pid_start", lambda pid: 999.0)            # … but it is another process
    monkeypatch.setattr(W, "read_power", lambda: dict(watts=140, volts=28, batt=80))
    monkeypatch.setattr(W.time, "sleep", lambda s: (_ for _ in ()).throw(AssertionError("must not tick on")))
    out = tmp_path / "w.log"
    assert W.main(["--models", "m", "--bench", "b", "--total", "1", "--driver-pid", "42", "--driver-create-time", "123.5",
                   "--rows-file", str(tmp_path / "none.jsonl"), "--out", str(out)]) == 0
    assert "driver=GONE" in out.read_text()
