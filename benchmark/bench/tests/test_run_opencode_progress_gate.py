"""D7 part 2 integration: run_opencode_probe.py wires bench/progress_gate.py into a real subprocess
session, replacing the flat 900 s timeout. Nothing here spawns opencode or talks to a model --
`subprocess.Popen` is monkeypatched to a fake, and grading uses trivial in-process functions.
"""
import importlib.util
import time
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "run_opencode_probe", Path(__file__).resolve().parents[2] / "run_opencode_probe.py")
ROP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ROP)


# --------------------------------------------------------------------------- _tick_snapshot_fn
def _mkfiles(tmp_path, sol_text="before", test_text="def test_x(): pass\n"):
    work = tmp_path / "work"
    work.mkdir()
    sol = work / "sol.py"
    test = work / "sol_test.py"
    sol.write_text(sol_text)
    test.write_text(test_text)
    log = work / ".opencode_probe_log.txt"
    log.write_text("")
    return work, sol, test, log


def test_first_tick_unchanged_file_is_flat_and_never_grades(tmp_path):
    work, sol, test, log = _mkfiles(tmp_path)

    def grade(w, t):
        raise AssertionError("grade must not run when the solution file has not changed")

    snap = ROP._tick_snapshot_fn(work, sol, test, "before", grade, log)
    tick = snap(300.0)
    assert tick.file_changed is False
    assert tick.n_failing is None
    assert tick.elapsed_s == 300.0


def test_changed_file_triggers_a_grade_call_and_records_the_result(tmp_path):
    work, sol, test, log = _mkfiles(tmp_path)
    calls = []

    def grade(w, t):
        calls.append((w, t))
        return True, "1 passed"

    snap = ROP._tick_snapshot_fn(work, sol, test, "before", grade, log)
    sol.write_text("after")   # the model "edits" the file between ticks
    tick = snap(300.0)
    assert tick.file_changed is True
    assert tick.n_failing == 0
    assert len(calls) == 1
    # grade was called on a SNAPSHOT COPY, never the live work dir -- the whole point of the design
    # ("never race a live write" / never corrupt an in-progress session).
    w_arg, t_arg = calls[0]
    assert w_arg != work and t_arg != test


def test_grade_failure_records_n_failing_one(tmp_path):
    work, sol, test, log = _mkfiles(tmp_path)

    def grade(w, t):
        return False, "1 failed"

    snap = ROP._tick_snapshot_fn(work, sol, test, "before", grade, log)
    sol.write_text("after")
    tick = snap(300.0)
    assert tick.n_failing == 1


def test_second_tick_with_no_further_change_does_not_re_grade(tmp_path):
    work, sol, test, log = _mkfiles(tmp_path)
    calls = []

    def grade(w, t):
        calls.append(1)
        return True, "ok"

    snap = ROP._tick_snapshot_fn(work, sol, test, "before", grade, log)
    sol.write_text("after")
    t1 = snap(300.0)
    assert t1.file_changed is True and len(calls) == 1
    t2 = snap(600.0)   # nothing edited since t1
    assert t2.file_changed is False
    assert t2.n_failing is None       # neutral -- the gate carries the last known count forward
    assert len(calls) == 1            # NOT re-graded


def test_signature_reflects_the_captured_log_tail(tmp_path):
    work, sol, test, log = _mkfiles(tmp_path)
    snap = ROP._tick_snapshot_fn(work, sol, test, "before", lambda w, t: (True, ""), log)
    t1 = snap(300.0)
    log.write_text("some new tool-call output\n")
    t2 = snap(600.0)
    assert t1.signature != t2.signature


# --------------------------------------------------------------------------- _run_opencode (Popen fake)
class _FakePopenCompletesImmediately:
    """Simulates a session that finishes before the first tick is ever due."""
    def __init__(self, cmd, cwd=None, stdout=None, stderr=None, text=None):
        self.cmd, self.cwd = cmd, cwd
        if stdout is not None:
            stdout.write("fake opencode ran and exited\n")
            stdout.flush()
        self.returncode = None

    def poll(self):
        self.returncode = 0
        return self.returncode

    def kill(self):
        raise AssertionError("must not be killed -- it already completed")

    def wait(self):
        return self.returncode


class _FakePopenNeverExits:
    """Simulates a wedged session: never exits on its own, must be killed."""
    def __init__(self, cmd, cwd=None, stdout=None, stderr=None, text=None):
        self.cmd, self.cwd = cmd, cwd
        self.returncode = None
        self.killed = False
        if stdout is not None:
            stdout.write("fake opencode still running...\n")
            stdout.flush()

    def poll(self):
        return self.returncode   # stays None until killed

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self):
        return self.returncode


def test_run_opencode_reports_completed_and_captures_the_log(tmp_path, monkeypatch):
    work, sol, test, _log = _mkfiles(tmp_path)
    monkeypatch.setattr(ROP.subprocess, "Popen", _FakePopenCompletesImmediately)
    rc, log, dur, result = ROP._run_opencode(
        "some-model", work, "do the thing", sol, test, lambda w, t: (True, ""), "before",
        tick_s=300, hard_ceiling_s=3600, poll_s=1.0, stall_ticks=2, loop_repeats=3, pure=True)
    assert rc == 0
    assert "fake opencode ran and exited" in log
    assert result.stop_reason == "completed"
    assert result.ticks == []


def test_run_opencode_stalls_and_kills_a_wedged_session(tmp_path, monkeypatch):
    """The solution file never changes (nothing edits it -- the fake process just sits there), so
    every tick is flat; with tiny tick_s/poll_s this must stop on 'stalled' well inside the test's
    own timeout, proving the process gets killed rather than running to hard_ceiling_s."""
    work, sol, test, _log = _mkfiles(tmp_path)
    monkeypatch.setattr(ROP.subprocess, "Popen", _FakePopenNeverExits)

    def grade(w, t):
        raise AssertionError("nothing ever changes in this test -- grade must not be called")

    t0 = time.time()
    rc, log, dur, result = ROP._run_opencode(
        "some-model", work, "do the thing", sol, test, grade, "before",
        tick_s=0.05, hard_ceiling_s=5.0, poll_s=0.01, stall_ticks=2, loop_repeats=3, pure=False)
    wall = time.time() - t0
    assert result.stop_reason == "stalled"
    assert rc == -9   # killed
    assert wall < 3.0   # nowhere near the 5 s hard ceiling -- the stall fired first
    assert len(result.ticks) == 2


def test_run_opencode_hard_ceiling_backstops_endless_progress(tmp_path, monkeypatch):
    """A session that keeps 'progressing' forever (file changes + grade always fails, but nothing
    ever repeats) is only stopped by the hard ceiling -- the generous backstop."""
    work, sol, test, _log = _mkfiles(tmp_path)
    monkeypatch.setattr(ROP.subprocess, "Popen", _FakePopenNeverExits)

    counter = {"n": 0}

    def _touch_and_grade_fail(w, t):
        return False, "still failing"

    # Monkeypatch _tick_snapshot_fn's file-change detection indirectly by editing the real file
    # before each grade call is possible; simplest reliable way here is to edit `sol` on disk from
    # a wrapped grade() call, so the NEXT tick sees a changed file.
    real_snapshot_fn = ROP._tick_snapshot_fn

    def _snapshot_fn_that_keeps_editing(cwd, sol_path, test_path, before_sol, grade, log_path):
        inner = real_snapshot_fn(cwd, sol_path, test_path, before_sol, grade, log_path)

        def _wrapped(elapsed_s):
            counter["n"] += 1
            sol_path.write_text(f"edit {counter['n']}")
            # Also keep the transcript changing each tick, so the LOOP detector (identical
            # signature 3x) never fires -- this scenario is specifically testing that the HARD
            # CEILING, not the loop guard, is what ends an endlessly-but-genuinely-progressing run.
            with log_path.open("a") as f:
                f.write(f"tool call {counter['n']}\n")
            return inner(elapsed_s)
        return _wrapped

    monkeypatch.setattr(ROP, "_tick_snapshot_fn", _snapshot_fn_that_keeps_editing)

    rc, log, dur, result = ROP._run_opencode(
        "some-model", work, "do the thing", sol, test, _touch_and_grade_fail, "before",
        tick_s=0.05, hard_ceiling_s=0.2, poll_s=0.01, stall_ticks=2, loop_repeats=3, pure=False)
    assert result.stop_reason == "hard_ceiling"
    assert rc == -9
