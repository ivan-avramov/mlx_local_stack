"""S27 §8.1 / §8.3: the watcher measures the box (swap, pressure, top CPU with ownership, launch latency) and ALERTs — record
only; an ALERT or a hold in the leg makes it speed-invalid (quality kept)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "m1"))
import bench_watch as bw                                   # noqa: E402


def sample(swap=1000.0, pressure="normal", top=(), fresh=0.2):
    return dict(swap_used_mb=swap, pressure=pressure, top_cpu=list(top), launch=dict(fresh_median_s=fresh, fresh_s=[fresh]))


def proc(pid, cpu, ownership="foreign"):
    return dict(pid=pid, sid=7, start=1.0, argv=["x"], cpu_pct=cpu, ownership=ownership)


def test_swap_growth_above_two_gb_in_a_tick_alerts():
    assert bw.box_alerts(sample(swap=4000), sample(swap=1000), {})
    assert not bw.box_alerts(sample(swap=2900), sample(swap=1000), {})


def test_critical_pressure_alerts():
    assert any("pressure" in a for a in bw.box_alerts(sample(pressure="critical"), None, {}))


def test_a_foreign_process_above_150_percent_for_two_ticks_alerts_and_unknown_never_does():
    streak = {}
    assert not bw.box_alerts(sample(top=[proc(5, 160)]), None, streak)
    assert any("pid 5" in a for a in bw.box_alerts(sample(top=[proc(5, 170)]), None, streak))
    streak2 = {}
    for _ in range(3):
        assert not bw.box_alerts(sample(top=[proc(6, 400, "unknown"), proc(7, 300, "ours")]), None, streak2)


def test_a_broken_streak_restarts():
    streak = {}
    bw.box_alerts(sample(top=[proc(5, 160)]), None, streak)
    bw.box_alerts(sample(top=[]), None, streak)
    assert not bw.box_alerts(sample(top=[proc(5, 160)]), None, streak)


def test_a_fresh_exec_median_above_one_second_alerts():
    assert any("fresh-exec" in a for a in bw.box_alerts(sample(fresh=1.4), None, {}))
    assert not bw.box_alerts(sample(fresh=0.4), None, {})


def tick(n, **kw):
    return dict(tick=n, t=float(n * 300), interval_s=300.0, watts=140, volts=28, battery=90, driver_alive=True,
                driver=dict(pid=1, start=1.0), **kw)


def finished(ticks):
    return ticks + [dict(exit_state="driver_exited", t=float(len(ticks) * 300), interval_s=300.0, battery_intervals=[])]


def test_an_alert_in_the_leg_is_speed_invalid():
    assert bw._verdict(finished([tick(0), tick(1)]))["valid"] is True
    v = bw._verdict(finished([tick(0), tick(1, alerts=["memory pressure critical"])]))
    assert v["valid"] is False and "ALERT" in v["reason"]


def test_a_hold_in_the_leg_is_speed_invalid():
    v = bw._verdict(finished([tick(0), tick(1, holds=1)]))
    assert v["valid"] is False and "hold" in v["reason"]


def test_the_tick_loop_records_the_box_sample_and_its_alerts(tmp_path, monkeypatch):
    chain = tmp_path / "chain.json"
    chain.write_text(json.dumps(dict(status="running", p426_holds=[], p426_ledger=[], progress=dict(invocations=[]))))
    samples = iter([sample(swap=100), sample(swap=4000)])
    clock = iter(float(x) for x in range(100))
    args = SimpleNamespace(out=str(tmp_path / "watch.jsonl"), driver_pid=999999999, driver_create_time=None, interval=300.0,
                           chain_json=str(chain), planned=None, pred_s=None)
    states = iter(["alive", "gone"])
    monkeypatch.setattr(bw, "_driver_state", lambda pid, bound: (next(states), bound))
    monkeypatch.setattr(bw, "_initial_bound", lambda a: 1.0)
    bw.run_p426(args, power=lambda: dict(watts=140, volts=28, battery=90), clock=lambda: next(clock), sleep=lambda s: None,
                box=lambda: next(samples))
    lines = [json.loads(x) for x in (tmp_path / "watch.jsonl").read_text().splitlines()]
    assert lines[0]["box"]["swap_used_mb"] == 100 and lines[0]["alerts"] == []
    assert lines[1]["swap_growth_mb"] == 3900 and lines[1]["alerts"] and lines[1]["holds"] == 0


def test_the_fresh_exec_probe_measures_fresh_scripts(tmp_path):
    out = bw._fresh_exec_s(tmp_path, runs=2)
    assert len(out["fresh_s"]) == 2 and out["fresh_median_s"] is not None and not list(tmp_path.iterdir())


def test_swap_usage_parsing():
    assert bw._swap_used_mb("vm.swapusage: total = 2048.00M  used = 1.50G  free = 512.00M  (encrypted)") == 1536.0
