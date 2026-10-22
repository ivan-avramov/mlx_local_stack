"""P426 Wave-1 sequencer (`docs/specs/p426-fable-mtp-recert.md` §3–§4): the 30-leg order, the exact leg argv, the idle gap, the
pause hold, resume and the stop rules — all with a fake clock and a fake launcher (no process, no GPU)."""

import json
import subprocess

import pytest

from bench import p426_wave1 as W

AXES = ("math500", "cjudge", "vision", "reasoning", "m1")


def test_schedule_is_ten_smokes_then_twenty_order_balanced_legs():
    legs = W.schedule()
    assert len(legs) == 30
    assert legs[:10] == [(a, arm, "smoke") for a in AXES for arm in ("off", "on")]
    assert legs[10:] == [leg for a in AXES for leg in ((a, "off", 1), (a, "on", 1), (a, "on", 2), (a, "off", 2))]


def test_leg_names_are_the_wrappers_receipt_names():
    assert W.leg_name("math500", "off", "smoke") == "math500-p426-off-smoke"
    assert W.leg_name("m1", "on", 2) == "m1-p426-on-b2"


def test_leg_argv_is_exact(tmp_path):
    root, wd, on, rd = tmp_path / "frozen", tmp_path / "wd", tmp_path / "on.yaml", tmp_path / "r"
    assert W.leg_argv(root, wd, on, rd, "vision", "on", 1) == [
        str(root / ".venv-bench" / "bin" / "python"), "-m", "bench.p426_leg", "--axis", "vision", "--arm", "on",
        "--block", "1", "--stack-root", str(root), "--workdir", str(wd), "--registry-on", str(on), "--receipt-dir", str(rd)]
    smoke = W.leg_argv(root, wd, on, rd, "m1", "off", "smoke")
    assert smoke[smoke.index("--arm") + 2] == "--smoke" and "--block" not in smoke


def _receipt(d, name, verdict, suffix=""):
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}{suffix}.receipt.json").write_text(json.dumps(dict(name=name, verdict=verdict,
                                                                     started="2026-10-22 10:00:00",
                                                                     ended="2026-10-22 10:30:00")))


def test_receipt_verdict_reads_published_and_refused_receipts(tmp_path):
    assert W.receipt_verdict(tmp_path, "a") is None
    _receipt(tmp_path, "a", "VALID")
    assert W.receipt_verdict(tmp_path, "a") == "VALID"
    _receipt(tmp_path, "b", "NOT_STARTED", suffix=".refused-1")
    assert W.receipt_verdict(tmp_path, "b") == "NOT_STARTED"  # a refusal beside no published receipt still counts
    _receipt(tmp_path, "a", "NOT_STARTED", suffix=".refused-2")
    assert W.receipt_verdict(tmp_path, "a") == "NOT_STARTED"  # any non-VALID receipt wins over a VALID one
    (tmp_path / "c.receipt.json").write_text("{not json")
    assert W.receipt_verdict(tmp_path, "c") == "UNREADABLE"


class Box:
    """Fake clock + launcher: each launch takes `wall` seconds and publishes the scripted verdict."""

    def __init__(self, tmp_path, verdicts=None, rcs=None, wall=1800.0):
        self.t, self.dir, self.verdicts, self.rcs, self.wall = 0.0, tmp_path / "receipts", verdicts or {}, rcs or {}, wall
        self.launched, self.launch_times, self.pause_until = [], [], None
        self.harvested, self.harvest_fails = [], set()

    def clock(self):
        return self.t

    def sleep(self, s):
        assert s > 0
        self.t += s

    def paused(self):
        return self.pause_until is not None and self.t < self.pause_until

    def launch(self, leg):
        name = W.leg_name(*leg)
        self.launched.append(name)
        self.launch_times.append(self.t)
        self.t += self.wall
        verdict = self.verdicts.get(name, "VALID")
        if verdict is not None:
            _receipt(self.dir, name, verdict)
        return self.rcs.get(name, 0 if verdict == "VALID" else 1)

    def harvest(self, leg):
        name = W.leg_name(*leg)
        if name in self.harvest_fails:
            raise W.HarvestError(f"{name}: PII after scrub")
        self.harvested.append(name)

    def run(self, legs=None, idle_s=600.0):
        self.log = []
        return W.run(legs or W.schedule(), launch=self.launch, read_verdict=lambda n: W.receipt_verdict(self.dir, n),
                     sleep=self.sleep, clock=self.clock, paused=self.paused, log=self.log.append, idle_s=idle_s,
                     harvest=self.harvest, harvested=lambda n: n in self.harvested)


def test_all_valid_runs_thirty_legs_with_the_idle_gap_before_each(tmp_path):
    box = Box(tmp_path)
    assert box.run() == 0
    assert box.launched == [W.leg_name(*leg) for leg in W.schedule()]
    assert box.launch_times[0] >= 600  # idle before the first leg too (a test window may have just ended)
    gaps = [b - (a + box.wall) for a, b in zip(box.launch_times, box.launch_times[1:])]
    assert min(gaps) >= 600


def test_stops_on_the_first_smoke_that_is_not_valid(tmp_path):
    box = Box(tmp_path, verdicts={"cjudge-p426-off-smoke": "INVALID"})
    assert box.run() == 1
    assert box.launched[-1] == "cjudge-p426-off-smoke" and len(box.launched) == 3


def test_stops_on_a_full_leg_that_is_not_valid(tmp_path):
    box = Box(tmp_path, verdicts={"math500-p426-on-b1": "NOT_STARTED"})
    assert box.run() == 1
    assert box.launched[-1] == "math500-p426-on-b1" and len(box.launched) == 12


@pytest.mark.parametrize("verdicts, rcs", [({}, {"vision-p426-off-smoke": 1}),  # VALID receipt, nonzero exit
                                           ({"vision-p426-off-smoke": "INVALID"}, {"vision-p426-off-smoke": 0}),
                                           ({"vision-p426-off-smoke": None}, {})])  # no receipt at all
def test_exit_code_and_receipt_must_agree(tmp_path, verdicts, rcs):
    box = Box(tmp_path, verdicts=verdicts, rcs=rcs)
    assert box.run() == 1
    assert box.launched[-1] == "vision-p426-off-smoke"


def test_every_launched_leg_is_harvested_before_the_verdict_decides(tmp_path):
    box = Box(tmp_path, verdicts={"cjudge-p426-on-smoke": "INVALID"})
    assert box.run() == 1
    assert box.harvested == box.launched  # the failing leg's evidence too


def test_a_harvest_failure_stops_the_run(tmp_path):
    box = Box(tmp_path)
    box.harvest_fails.add("math500-p426-on-smoke")
    assert box.run() == 4
    assert box.launched[-1] == "math500-p426-on-smoke" and len(box.launched) == 2
    assert any("HARVEST" in line for line in box.log)


def test_resume_skips_valid_legs_and_refuses_on_any_other_receipt(tmp_path):
    box = Box(tmp_path)
    for leg in W.schedule()[:4]:
        _receipt(box.dir, W.leg_name(*leg), "VALID")
        box.harvested.append(W.leg_name(*leg))
    assert box.run() == 0
    assert box.launched[0] == "vision-p426-off-smoke" and len(box.launched) == 26
    box3 = Box(tmp_path / "three")
    _receipt(box3.dir, "math500-p426-off-smoke", "VALID")  # VALID but never harvested: the evidence is not in the repo
    assert box3.run() == 1 and box3.launched == []
    box2 = Box(tmp_path / "two")
    _receipt(box2.dir, "math500-p426-off-smoke", "VALID")
    _receipt(box2.dir, "math500-p426-on-smoke", "INVALID")
    assert box2.run() == 1 and box2.launched == []  # a rerun is the operator's decision


def test_pause_holds_at_the_boundary_and_the_idle_gap_restarts_after_it(tmp_path):
    box = Box(tmp_path)
    box.pause_until = 5000.0  # a test window opened before / during the first gap
    assert box.run(legs=W.schedule()[:2]) == 0
    assert box.launch_times[0] >= 5000 + 600
    assert any("PAUSE" in line for line in box.log)


def test_a_leg_that_overruns_is_not_killed(tmp_path):
    class Proc:
        pid, killed = 4242, False

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("leg", timeout)

        def kill(self):
            Proc.killed = True

        terminate = kill

    with pytest.raises(W.LegOverrun) as exc:
        W.wait_leg(Proc(), timeout_s=10)
    assert "4242" in str(exc.value) and not Proc.killed


def test_main_refuses_a_workdir_that_is_not_stack_workdir(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_WORKDIR", str(tmp_path / "elsewhere"))
    rc = W.main(["--stack-root", str(tmp_path), "--main-root", str(tmp_path / "main"), "--workdir", str(tmp_path), "--registry-on", str(tmp_path / "on.yaml"),
                 "--out", str(tmp_path / "out")])
    assert rc == 2


def test_an_axes_filter_keeps_the_order_and_drops_the_rest():
    """P452: M1 (in-process qualify) cannot run inside the wrapper on S; A1–A4 run on their own (per-axis smoke gate, §4)."""
    legs = W.schedule(axes=("math500", "cjudge", "vision", "reasoning"))
    assert len(legs) == 24 and all(a != "m1" for a, _, _ in legs)
    assert legs == [leg for leg in W.schedule() if leg[0] != "m1"]
    with pytest.raises(ValueError, match="unknown axis"):
        W.schedule(axes=("math500", "nope"))
