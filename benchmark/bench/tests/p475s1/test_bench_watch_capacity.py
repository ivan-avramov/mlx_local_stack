"""`benchmark/m1/bench_watch.py` (contract component 3): capacity mode (R9: elapsed_s vs expected rung seconds, RATE / ETA), the
`--driver-create-time` identity bind in any mode (R12); the existing modes unchanged."""
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "m1"))
import bench_watch as W  # noqa: E402

from bench import paths  # noqa: E402

REPO = paths.repo_root()
EXPECTED = "60,400,800,1500"
GOOD = {"watts": 140, "volts": 28, "battery": 80}


def create_time(pid):
    import psutil
    from bench import proc_guard
    return proc_guard.start_time(psutil.Process(pid))


@pytest.fixture
def driver():
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    yield p
    if p.poll() is None:
        p.kill()
    p.wait()


def rung(i, elapsed, status="completed"):
    return {"ctx": [8192, 131072, 196608, 260096][i], "execution_status": status, "elapsed_s": elapsed}


class Script:
    """Injected clock / sleep / power: step k of `plan` runs at the k-th sleep; `kill_at` ends the driver at that sleep."""
    def __init__(self, drv, rows_path, plan=(), kill_at=3, power=None):
        self.drv, self.rows, self.plan, self.kill_at, self.t, self.n = drv, rows_path, dict(plan), kill_at, 1_800_000_000.0, 0
        # an injected meter carries the battery-log proof (`on_battery_intervals`), as `run_p426` documents for injected sources
        self.power_fn = power or (lambda: dict(GOOD, on_battery_intervals=[]))

    def clock(self):
        return self.t

    def power(self):
        return self.power_fn()

    def sleep(self, s):
        self.n += 1
        self.t += s
        if self.n in self.plan:
            with open(self.rows, "a") as f:
                f.write(json.dumps(self.plan[self.n]) + "\n")
        if self.n >= self.kill_at and self.drv.poll() is None:
            self.drv.kill()
            self.drv.wait()


def run_capacity_mode(tmp_path, drv, script, *, ct="auto", extra=(), expected=EXPECTED):
    rows = tmp_path / "capacity_ladder.p475-x.jsonl"
    out = tmp_path / "watch.jsonl"
    argv = ["--capacity-rows", str(rows), "--expected-rung-seconds", expected, "--driver-pid", str(drv.pid),
            "--out", str(out), "--interval", "300", *extra]
    if ct is not None:
        argv += ["--driver-create-time", repr(create_time(drv.pid) if ct == "auto" else ct)]
    rc = W.main(argv, power=script.power, clock=script.clock, sleep=script.sleep)
    lines = [json.loads(x) for x in out.read_text().splitlines()] if out.exists() else []
    return rc, lines


def flat(d, prefix=""):
    """The tick's numbers by dotted path (the contract fixes no key names: the candidate nests `rate.ratio`, `eta.eta_s`)."""
    out = {}
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flat(v, key + "."))
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[key] = v
    return out


def nums(d, words):
    return [v for k, v in flat(d).items() if any(w in k.lower() for w in words)]


# ------------------------------------------------------------------------------------------- capacity mode
def test_capacity_mode_writes_json_ticks_and_a_final_exit_line(tmp_path, driver):
    # class: exercises new behaviour
    s = Script(driver, tmp_path / "capacity_ladder.p475-x.jsonl")
    rc, lines = run_capacity_mode(tmp_path, driver, s)
    assert rc == 0
    ticks = [x for x in lines if "exit_state" not in x]
    assert len(ticks) >= 2
    assert "exit_state" in lines[-1] and lines[-1]["exit_state"] == "driver_exited"
    assert sum("exit_state" in x for x in lines) == 1


def test_each_tick_records_power_battery_and_driver_alive(tmp_path, driver):
    # class: exercises new behaviour
    s = Script(driver, tmp_path / "capacity_ladder.p475-x.jsonl")
    _, lines = run_capacity_mode(tmp_path, driver, s)
    first = lines[0]
    assert (first["watts"], first["volts"], first["battery"]) == (140, 28, 80)
    assert first["driver_alive"] is True
    assert first["interval_s"] == 300.0
    assert first["t"] == 1_800_000_000.0


def test_a_power_failure_tick_is_recorded_as_not_ok(tmp_path, driver):
    # class: exercises new behaviour
    readings = iter([dict(GOOD), dict(GOOD, watts=96), dict(GOOD), dict(GOOD), dict(GOOD)])
    s = Script(driver, tmp_path / "capacity_ladder.p475-x.jsonl", power=lambda: next(readings))
    _, lines = run_capacity_mode(tmp_path, driver, s)
    bad = [x for x in lines if "exit_state" not in x and x.get("watts") == 96]
    assert bad and bad[0].get("power_ok") is False
    assert W.speed_verdict(tmp_path / "watch.jsonl")["valid"] is False


def test_rate_and_eta_come_from_elapsed_s_against_the_expected_rung_seconds(tmp_path, driver):
    # class: exercises new behaviour (R9). Rung 1 took 120 s against 60 expected: ratio 2.0; the remaining expected 2700 s scale
    # to 5400 s (90 min). Only `elapsed_s` is on the rows (no wall_s), so a watcher reading any other field sees nothing.
    rows = tmp_path / "capacity_ladder.p475-x.jsonl"
    s = Script(driver, rows, plan={1: rung(0, 120.0)}, kill_at=3)
    _, lines = run_capacity_mode(tmp_path, driver, s)
    after = [x for x in lines if "exit_state" not in x][1]           # the tick that follows the first completed rung
    rates = nums(after, ("rate", "ratio"))
    etas = nums(after, ("eta", "remaining"))
    assert any(math.isclose(r, 2.0, rel_tol=0.01) for r in rates), after
    assert any(math.isclose(e, 5400.0, rel_tol=0.02) or math.isclose(e, 90.0, rel_tol=0.02) for e in etas), after


def test_eta_tracks_two_completed_rungs(tmp_path, driver):
    # class: exercises new behaviour (R9). 120 + 800 s against 60 + 400 expected: ratio 2.0; remaining 2300 -> 4600 s.
    rows = tmp_path / "capacity_ladder.p475-x.jsonl"
    s = Script(driver, rows, plan={1: rung(0, 120.0), 2: rung(1, 800.0)}, kill_at=4)
    _, lines = run_capacity_mode(tmp_path, driver, s)
    last = [x for x in lines if "exit_state" not in x][2]            # the tick after both rungs landed
    assert any(math.isclose(e, 4600.0, rel_tol=0.02) or math.isclose(e, 76.7, rel_tol=0.02) for e in nums(last, ("eta", "remaining"))), last


def test_a_faster_than_expected_run_reports_a_rate_below_one(tmp_path, driver):
    # class: exercises new behaviour (R9): 60 + 200 s against 60 + 400 expected
    rows = tmp_path / "capacity_ladder.p475-x.jsonl"
    s = Script(driver, rows, plan={1: rung(0, 60.0), 2: rung(1, 200.0)}, kill_at=4)
    _, lines = run_capacity_mode(tmp_path, driver, s)
    last = [x for x in lines if "exit_state" not in x][2]
    assert any(math.isclose(r, 260 / 460, rel_tol=0.02) for r in nums(last, ("rate", "ratio"))), last


def test_ticks_before_any_rung_exist_do_not_crash_the_watcher(tmp_path, driver):
    # class: exercises new behaviour (the ladder file does not exist yet at the first tick)
    s = Script(driver, tmp_path / "capacity_ladder.p475-x.jsonl", kill_at=2)
    rc, lines = run_capacity_mode(tmp_path, driver, s)
    assert rc == 0 and lines


# ------------------------------------------------------------------------------------------- R12: (pid, create_time)
def test_the_right_create_time_binds_the_driver_alive(tmp_path, driver):
    # class: exercises new behaviour (R12)
    s = Script(driver, tmp_path / "capacity_ladder.p475-x.jsonl")
    _, lines = run_capacity_mode(tmp_path, driver, s, ct="auto")
    assert lines[0]["driver_alive"] is True
    assert W.speed_verdict(tmp_path / "watch.jsonl")["valid"] is True


def test_a_different_create_time_is_not_the_driver(tmp_path, driver):
    # class: reproduces a failure the contract fixes (R12: a pid alone cannot tell the driver from a process that reused it)
    s = Script(driver, tmp_path / "capacity_ladder.p475-x.jsonl", kill_at=99)
    rc, lines = run_capacity_mode(tmp_path, driver, s, ct=create_time(driver.pid) + 7.0)
    ticks = [x for x in lines if "exit_state" not in x]
    assert ticks and all(t["driver_alive"] is not True for t in ticks)
    assert s.n <= 1, "the watcher must stop at once: the bound driver does not exist"
    assert W.speed_verdict(tmp_path / "watch.jsonl")["valid"] is False


def _legacy(tmp_path, drv, ct_arg):
    rows = tmp_path / "rows.jsonl"
    rows.write_text("")
    out = tmp_path / "w.log"
    cmd = [sys.executable, str(REPO / "benchmark/m1/bench_watch.py"), "--models", "m", "--bench", "rows", "--total", "1",
           "--driver-pid", str(drv.pid), "--out", str(out), "--rows-file", str(rows), "--interval", "1", *ct_arg]
    t0 = time.monotonic()
    rc = subprocess.run(cmd, env={**os.environ, "PYTHONPATH": str(REPO / "benchmark")}, timeout=60).returncode
    return rc, out.read_text(), time.monotonic() - t0


def test_legacy_mode_binds_by_create_time_too(tmp_path):
    # class: exercises new behaviour (R12: "in any mode")
    drv = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(4)"])
    try:
        rc, log, _ = _legacy(tmp_path, drv, ["--driver-create-time", repr(create_time(drv.pid))])
    finally:
        drv.wait()
    assert rc == 0 and "driver=ALIVE" in log and "DRIVER EXITED" in log


def test_legacy_mode_a_wrong_create_time_reads_the_driver_as_gone(tmp_path):
    # class: reproduces a failure the contract fixes (R12)
    drv = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(25)"])
    try:
        rc, log, took = _legacy(tmp_path, drv, ["--driver-create-time", repr(create_time(drv.pid) + 9.0)])
    finally:
        drv.kill()
        drv.wait()
    assert rc == 0 and "driver=GONE" in log and "driver=ALIVE" not in log
    assert took < 15


def test_legacy_mode_without_create_time_is_unchanged(tmp_path):
    # class: preserves an invariant (the pid-only form)
    drv = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(3)"])
    try:
        rc, log, _ = _legacy(tmp_path, drv, [])
    finally:
        drv.wait()
    assert rc == 0 and "driver=ALIVE" in log and "DRIVER EXITED" in log


# ------------------------------------------------------------------------------------------- existing modes unchanged
def test_existing_power_gate_is_unchanged():
    # class: preserves an invariant
    legacy = {"watts": 140, "volts": 28, "batt": 80}
    assert W.power_ok(legacy | {"batt": 21}) is True
    assert W.power_ok(legacy | {"batt": 20}) is False
    assert W.power_ok(legacy | {"watts": 139}) is False


def test_existing_flags_still_parse_without_the_new_ones():
    # class: preserves an invariant
    a = W._parse_args(["--models", "m", "--bench", "rows", "--total", "1", "--driver-pid", "1", "--out", "o"])
    assert a.driver_pid == 1 and a.interval == 300.0
    assert getattr(a, "driver_create_time", None) is None
    assert getattr(a, "capacity_rows", None) is None


def test_the_p426_mode_journal_without_create_time_is_unchanged(tmp_path, driver):
    # class: preserves an invariant (a P426-mode run keeps writing its tick keys and one exit line)
    chain = tmp_path / "chain.json"
    chain.write_text(json.dumps({"status": "running", "slots": []}))
    s = Script(driver, tmp_path / "unused", kill_at=2)
    out = tmp_path / "watch.jsonl"
    rc = W.main(["--chain-json", str(chain), "--driver-pid", str(driver.pid), "--out", str(out), "--interval", "300"],
                power=s.power, clock=s.clock, sleep=s.sleep)
    lines = [json.loads(x) for x in out.read_text().splitlines()]
    assert rc == 0
    assert {"tick", "t", "at", "interval_s", "watts", "volts", "battery", "power_ok", "driver_alive", "driver"} <= set(lines[0])
    assert lines[-1]["exit_state"] == "driver_exited" and sum("exit_state" in x for x in lines) == 1
