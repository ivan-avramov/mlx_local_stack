"""P590 (criterion 7): with TZ=America/Los_Angeles, a leg that runs from 2026-11-01 01:14:12 PDT (08:14:12Z) to 01:30:00 PST
(09:30:00Z) — across the fall-back, local wall clock 01:00–02:00 both times — must get the watcher-ticks need and the battery
window of its REAL span (4548 s: need 13 ticks; window [08:14:12Z, 09:30:00Z]).

Seam (the spec names none): `p426_leg.main` is driven with fakes up to its `run_leg(...)` call, which is captured; that yields
the PRODUCTION `clock` and `battery_intervals` exactly as the leg wires them (no source inspection). The clock's stamp
representation is discovered by calling it once now (epoch number, naive UTC, naive local, ISO); the two instants are then
rendered in that same representation and fed to the captured `battery_intervals` (its `pmset` output and the fork's `qualify`
are fakes recording the epoch window) and to `p426_leg.watch_problems`. On the baseline the clock is naive LOCAL and both
consumers `time.mktime` it: the repeated hour collapses the 76-minute leg to 16 minutes (red).

Classes: [R] reproduces the failure the spec fixes, [I] preserves an invariant."""
from __future__ import annotations

import calendar
import datetime
import sys
import time
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from bench import chain_ops
from bench import p426_leg
from bench import p426_plan

FMT = "%Y-%m-%d %H:%M:%S"
START = calendar.timegm(time.strptime("2026-11-01 08:14:12", FMT))      # 01:14:12 PDT
END = calendar.timegm(time.strptime("2026-11-01 09:30:00", FMT))        # 01:30:00 PST
SUMMER_START = calendar.timegm(time.strptime("2026-07-01 08:14:12", FMT))
SUMMER_END = SUMMER_START + (END - START)
NEED = int(((END - START) - 2 * p426_leg.TICK_S) // p426_leg.TICK_S)    # 13
PMSET = "2026-11-01 00:30:00 -0700 Assertions          \tSummary- [System: PrevIdle DeclUser kDisp] Using AC(Charge: 100)\n"


def _capture_leg_main(tmp_path, monkeypatch):
    """Run `p426_leg.main` (build s, OFF arm) with fakes for the plan, the ops, the fork's harness; return the kwargs it
    passes to `run_leg` (the production `clock` and `battery_intervals`) and the fake qualify's recorded windows."""
    wd, repo = Path(tmp_path) / "wd", Path(tmp_path) / "repo"
    (repo / "logs").mkdir(parents=True)
    (repo / "main_models.yaml").write_text("models: {}\n")
    frozen = p426_plan.frozen_path(wd, "s")
    frozen.parent.mkdir(parents=True)
    frozen.write_text("{}")
    monkeypatch.setenv("STACK_WORKDIR", str(wd))
    monkeypatch.setattr(p426_plan, "plan_leg", lambda *a, **k: dict(
        entry="Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", driver_argv=["true"], rows_path=None, planned=[],
        row_key="id", expected_requests=0, expected_extra=0, seeds={}, cwd=str(repo), kind="rows"))
    monkeypatch.setattr(p426_plan, "existing_outputs", lambda plan: [])
    monkeypatch.setattr(chain_ops, "ChainOps", lambda *a, **k: SimpleNamespace(wd=wd))
    windows = []
    pkg = types.ModuleType("p369_phase2")
    pkg.__path__ = []
    qualify = types.ModuleType("p369_phase2.qualify")
    qualify.battery_intervals = lambda text, t0, t1: windows.append((t0, t1)) or []
    orchestrate = types.ModuleType("p369_phase2.orchestrate")
    orchestrate.load_pins = lambda: {}
    pkg.qualify, pkg.orchestrate = qualify, orchestrate
    for name, mod in (("p369_phase2", pkg), ("p369_phase2.qualify", qualify), ("p369_phase2.orchestrate", orchestrate)):
        monkeypatch.setitem(sys.modules, name, mod)
    captured = {}

    def run_leg(spec, ops, **kw):
        captured.update(kw)
        return dict(name=spec.name, verdict="VALID", speed_valid=True, problems=[], speed_problems=[])
    monkeypatch.setattr(p426_leg, "run_leg", run_leg)
    monkeypatch.setattr(p426_leg, "run_qualify_leg", lambda spec, ops, **kw: run_leg(spec, ops, **kw))
    rc = p426_leg.main(["--axis", "tg1", "--arm", "off", "--block", "1", "--stack-root", str(repo), "--workdir", str(wd),
                        "--registry-on", str(repo / "main_models.yaml"), "--receipt-dir", str(Path(tmp_path) / "receipts")])
    assert rc == 0 and "clock" in captured and "battery_intervals" in captured, (rc, sorted(captured))
    monkeypatch.setattr(p426_leg.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=PMSET, stderr=""))
    return captured, windows


def _representation(stamp, now):
    """How the leg's clock writes an instant: 'epoch' | 'utc' | 'local' (naive `%Y-%m-%d %H:%M:%S`) | 'iso_z' | 'iso'."""
    if isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
        assert abs(float(stamp) - now) < 300
        return "epoch"
    assert isinstance(stamp, str), repr(stamp)
    try:
        st = time.strptime(stamp, FMT)
    except ValueError:
        pass
    else:
        if abs(calendar.timegm(st) - now) < 300:
            return "utc"
        if abs(time.mktime(st) - now) < 300:
            return "local"
        raise AssertionError(f"clock stamp {stamp!r} is neither UTC nor local now")
    try:
        if abs(calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")) - now) < 300:
            return "iso_z"
    except ValueError:
        pass
    d = datetime.datetime.fromisoformat(stamp)
    assert d.tzinfo is not None and abs(d.timestamp() - now) < 300, stamp
    return "iso"


def _render(rep, t):
    return {"epoch": lambda: float(t), "utc": lambda: time.strftime(FMT, time.gmtime(t)),
            "local": lambda: time.strftime(FMT, time.localtime(t)),
            "iso_z": lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t)),
            "iso": lambda: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat()}[rep]()


def _stamps(captured, t0, t1):
    now = time.time()
    rep = _representation(captured["clock"](), now)
    return rep, _render(rep, t0), _render(rep, t1)


def _tick_problems(start, end, ticks):
    probs = p426_leg.watch_problems(dict(ticks=ticks, power_failure=None, exited_early=False), start, end)
    return [p for p in probs if "tick" in p]


def test_dst_watcher_ticks_need_is_the_real_span(tmp_path, monkeypatch, los_angeles, no_path_leak):
    """[R] criterion 7: across the fall-back the leg needs 13 ticks: 12 is a speed problem, 13 is not (baseline: the naive
    local stamps give a 948 s span, need 1, so 12 ticks pass)."""
    captured, _ = _capture_leg_main(tmp_path, monkeypatch)
    rep, s, e = _stamps(captured, START, END)
    assert NEED == 13
    assert _tick_problems(s, e, NEED - 1), (rep, s, e)
    assert _tick_problems(s, e, NEED) == [], (rep, s, e)


def test_dst_battery_window_is_the_real_span(tmp_path, monkeypatch, los_angeles, no_path_leak):
    """[R] criterion 7: the battery window handed to the fork's `battery_intervals` is [08:14:12Z, 09:30:00Z] (baseline: one
    end is an hour off — `time.mktime` of the repeated local hour)."""
    captured, windows = _capture_leg_main(tmp_path, monkeypatch)
    rep, s, e = _stamps(captured, START, END)
    _intervals, problems = captured["battery_intervals"](s, e)
    assert problems == [] and len(windows) == 1, (problems, windows)
    t0, t1 = windows[0]
    assert abs(t0 - START) < 1 and abs(t1 - END) < 1, (rep, s, e, t0 - START, t1 - END)


def test_outside_dst_the_need_and_window_are_unchanged(tmp_path, monkeypatch, los_angeles, no_path_leak):
    """[I] the same 4548 s leg in July: need 13 and the exact window, as on the baseline."""
    captured, windows = _capture_leg_main(tmp_path, monkeypatch)
    rep, s, e = _stamps(captured, SUMMER_START, SUMMER_END)
    assert _tick_problems(s, e, NEED - 1) and _tick_problems(s, e, NEED) == []
    captured["battery_intervals"](s, e)
    t0, t1 = windows[-1]
    assert abs(t0 - SUMMER_START) < 1 and abs(t1 - SUMMER_END) < 1
