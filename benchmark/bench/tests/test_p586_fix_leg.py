"""P586 fix round 1, X5 / X6 (red-first): `battery_window` resolves `subprocess.run` at call time; the leg stamps carry a UTC marker."""
from __future__ import annotations

import calendar
import subprocess
import time
from types import SimpleNamespace

import pytest

from bench import p426_leg as pl

EVENT = "2026-11-01 00:10:00 -0700 Assertions   Using AC (Charge:80%)"


# -- X5
def test_x5_battery_window_reaches_a_monkeypatched_subprocess_run(monkeypatch):
    ran = []

    def fake_run(argv, **kw):
        ran.append(argv)
        return SimpleNamespace(returncode=0, stdout=EVENT + "\n")

    def no_popen(*a, **k):
        raise AssertionError("a real process started")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(subprocess, "Popen", no_popen)
    qualify = SimpleNamespace(battery_intervals=lambda text, a, b: [])
    intervals, problems = pl.battery_window("2026-11-01T00:30:00Z", "2026-11-01T02:30:00Z", qualify=qualify)
    assert ran == [["pmset", "-g", "log"]] and intervals == []


def test_x5_an_explicit_run_still_wins(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("patched run used")))
    qualify = SimpleNamespace(battery_intervals=lambda text, a, b: [])
    run = lambda *a, **k: SimpleNamespace(returncode=0, stdout=EVENT + "\n")        # noqa: E731
    pl.battery_window(0, 1, qualify=qualify, run=run)


# -- X6
def test_x6_utc_stamp_carries_the_z_marker():
    assert pl.utc_stamp(0) == "1970-01-01T00:00:00Z"
    t = calendar.timegm(time.strptime("2026-11-01 09:00:05", "%Y-%m-%d %H:%M:%S"))
    assert pl.utc_stamp(t) == "2026-11-01T09:00:05Z" and pl.utc_stamp(t + 0.9) == "2026-11-01T09:00:05Z"


def test_x6_stamp_epoch_reads_the_marked_form_and_epoch_numbers():
    t = calendar.timegm(time.strptime("2026-11-01 09:00:00", "%Y-%m-%d %H:%M:%S"))
    assert pl.stamp_epoch("2026-11-01T09:00:00Z") == t
    assert pl.stamp_epoch(pl.utc_stamp(t)) == t
    assert pl.stamp_epoch(t) == t and pl.stamp_epoch(float(t)) == t


@pytest.mark.parametrize("text", ["2026-11-01 09:00:00", "2026-11-01T09:00:00", "2026-11-01 09:00:00Z", "2026-11-01T09:00:00+00:00",
                                  "", "nonsense"])
def test_x6_an_unmarked_or_malformed_stamp_raises(text):
    with pytest.raises(ValueError):
        pl.stamp_epoch(text)


def test_x6_a_bool_is_not_an_epoch():
    with pytest.raises(ValueError):
        pl.stamp_epoch(True)


def test_x6_watch_problems_and_battery_window_refuse_an_unmarked_stamp():
    with pytest.raises(ValueError):
        pl.watch_problems(dict(ticks=99), "2026-11-01 00:30:00", "2026-11-01T02:30:00Z")
    qualify = SimpleNamespace(battery_intervals=lambda text, a, b: [])
    run = lambda *a, **k: SimpleNamespace(returncode=0, stdout=EVENT + "\n")        # noqa: E731
    with pytest.raises(ValueError):
        pl.battery_window("2026-11-01 00:30:00", "2026-11-01T02:30:00Z", qualify=qualify, run=run)
    assert pl.watch_problems(dict(ticks=22), "2026-11-01T00:30:00Z", "2026-11-01T02:30:00Z") == []
