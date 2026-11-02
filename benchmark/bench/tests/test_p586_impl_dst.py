"""P590 (implementer's red-first tests): no B2 logic orders or windows by local timestamps (the 2026-11-01 fall-back hour)."""
from __future__ import annotations

import calendar
import time
from types import SimpleNamespace

import pytest

from bench import p426_leg as pl


@pytest.fixture
def la_time(monkeypatch):
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def epoch(text):
    return float(calendar.timegm(time.strptime(text, "%Y-%m-%d %H:%M:%S")))


# 2026-11-01: 02:00 PDT falls back to 01:00 PST at 09:00 UTC. The stamps are UTC: a leg 00:30Z -> 02:30Z lasts exactly two hours,
# whatever the box's zone (read as local time it would span the fall-back and last three).
START, END = "2026-11-01T00:30:00Z", "2026-11-01T02:30:00Z"                              # X6: the marked UTC form
# the leg of the brief: 01:30 PDT (08:30Z) to the second 01:30, in PST (09:30Z): one hour of wall clock, 01:00-02:00 local twice
AMBIGUOUS = (epoch("2026-11-01 08:30:00"), epoch("2026-11-01 09:30:00"))


def test_watcher_ticks_needed_are_counted_on_the_real_span_across_the_fall_back_hour(la_time):
    assert pl.watch_problems(dict(ticks=22), START, END) == []                      # (7200 - 600) // 300
    (p,) = pl.watch_problems(dict(ticks=21), START, END)
    assert "22" in p and "7200" in p


def test_a_leg_inside_the_repeated_local_hour_has_its_real_span(la_time):
    assert pl.watch_problems(dict(ticks=10), *AMBIGUOUS) == []                      # (3600 - 600) // 300
    (p,) = pl.watch_problems(dict(ticks=9), *AMBIGUOUS)
    assert "10" in p and "3600" in p
    assert pl.watch_problems(dict(ticks=10), pl.utc_stamp(AMBIGUOUS[0]), pl.utc_stamp(AMBIGUOUS[1])) == []


def test_watcher_ticks_accept_epoch_stamps(la_time):
    assert pl.watch_problems(dict(ticks=22), pl.stamp_epoch(START), pl.stamp_epoch(END)) == []
    assert pl.watch_problems(dict(ticks=21), pl.stamp_epoch(START), pl.stamp_epoch(END))


def test_the_default_clock_is_utc_and_round_trips_through_stamp_epoch(la_time):
    t = epoch("2026-11-01 09:00:00")                                            # the fall-back instant
    assert pl.utc_stamp(t) == "2026-11-01T09:00:00Z" and pl.stamp_epoch(pl.utc_stamp(t)) == t
    assert pl.stamp_epoch(t) == t


def test_the_battery_window_is_the_utc_epoch_of_the_legs_stamps(la_time):
    seen = {}
    qualify = SimpleNamespace(battery_intervals=lambda text, a, b: seen.update(window=(a, b)) or [])
    event = "2026-11-01 00:10:00 -0700 Assertions   Using AC (Charge:80%)"          # a well-formed power-source event
    run = lambda *a, **k: SimpleNamespace(returncode=0, stdout=event + "\n")        # noqa: E731
    intervals, problems = pl.battery_window(START, END, qualify=qualify, run=run)
    assert seen["window"] == (pl.stamp_epoch(START), pl.stamp_epoch(END))
    assert intervals == []
    _ = problems
