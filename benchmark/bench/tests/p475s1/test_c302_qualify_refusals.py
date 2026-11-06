"""C302 (S18-P12): the preflight checks power among its NOT_STARTED pre-checks, and a qualify that refused before its measurement
loop (no `started`, every entry NOT_RUN) is NOT_STARTED, never an attempt; a qualify that started still counts."""
import json

import pytest

from . import helpers as H
from .fakes import FakeOps

BATTERY = {"watts": None, "volts": None, "battery": 84}


@pytest.fixture
def w(tmp_path, monkeypatch):
    return H.world(tmp_path, monkeypatch)


def run(w, arm="AF8", kind="off", **kw):
    return H.K().preflight(arm, FakeOps(w), H.cfg(w), kind=kind, **kw)


@pytest.mark.parametrize("kind", ["off", "engagement"])
@pytest.mark.parametrize("power", [BATTERY, {"watts": 96, "volts": 20, "battery": 80}, {"watts": 140, "volts": 28, "battery": 15}])
def test_bad_power_is_not_started_and_runs_no_qualify(w, kind, power):
    w.power_val = power
    rec = run(w, kind=kind)
    assert rec["status"] == "NOT_STARTED" and rec["attempts"] == []
    assert "power" in rec["not_started"][-1]["reason"]
    assert w.run_calls == []


@pytest.mark.parametrize("kind", ["off", "engagement"])
def test_a_qualify_refusal_before_its_measurement_loop_is_not_started(w, kind):
    plan = w.engagement_plan if kind == "engagement" else w.preflight_plan
    plan["AF8"] = ["env_refused", "pass"]
    rec = run(w, kind=kind)
    assert rec["status"] == "NOT_STARTED" and rec["attempts"] == []
    assert "power" in rec["not_started"][-1]["reason"]              # qualify's own refused: line
    rec = run(w, kind=kind)                                          # never final: the next call runs again
    assert rec["status"] == "PASS" and len(rec["attempts"]) == 1


def test_repeated_qualify_refusals_never_finalise(w):
    w.preflight_plan["AF8"] = ["env_refused"] * 9
    for _ in range(5):
        assert run(w)["status"] == "NOT_STARTED"
    rec = json.loads((w.wd / "p475" / "preflight" / "AF8.json").read_text())
    assert rec["status"] == "NOT_STARTED" and rec["attempts"] == [] and len(rec["not_started"]) == 5


def test_a_qualify_that_started_its_loop_still_counts_as_an_attempt(w):
    w.preflight_plan["AF8"] = ["started_not_run"] * 9
    rec = run(w)
    assert rec["status"] == "REFUSED" and len(rec["attempts"]) == 3


def test_a_qualify_refusal_without_any_report_still_counts_as_an_attempt(w):
    w.preflight_plan["AF8"] = ["no_report"] * 9                     # a configuration refusal: before its out dir report
    rec = run(w)
    assert rec["status"] == "REFUSED" and len(rec["attempts"]) == 3


def test_the_attempt_record_keeps_whether_qualify_started(w):
    w.preflight_plan["AF8"] = ["started_not_run", "pass"]
    rec = run(w)
    assert rec["attempts"][0]["report"]["started"] == "2026-11-06T11:43:00"


def test_run_stops_on_a_qualify_refusal_without_refusing_the_arm(w):
    ops = FakeOps(w)
    assert H.prepare(w, ops) == []
    w.preflight_plan["N16"] = ["env_refused"] * 9
    assert H.run_all(w, ops=ops, smoke=True) != 0
    st = json.loads((w.wd / "p475" / "state.json").read_text())
    assert st["refused_arms"] == []
    assert w.spawns == []
