"""D7 part 2: progress-gated bound for opencode sessions, replacing the flat 900 s timeout.

Design recovered from `docs/handoff-2026-08-16.md` Phase H (git show f774e88^:docs/handoff-2026-08-16.md),
quoted in `bench/progress_gate.py`'s module docstring. Nothing here invokes a real subprocess, opencode,
or a model -- `ProgressGate` is pure, and `run_progress_gated` is driven entirely by fakes.
"""
import pytest

from bench import progress_gate as PG


def _tick(elapsed=0.0, n_failing=None, sol_hash="h", signature="s", file_changed=False):
    return PG.Tick(elapsed_s=elapsed, n_failing=n_failing, solution_hash=sol_hash,
                   signature=signature, file_changed=file_changed)


# --------------------------------------------------------------------------- ProgressGate (pure policy)
def test_decreasing_failures_is_progress_and_never_stalls():
    gate = PG.ProgressGate(stall_ticks=2, loop_repeats=3)
    for i, n in enumerate([10, 7, 4, 2, 0]):
        reason = gate.observe(_tick(elapsed=i, n_failing=n, signature=f"sig{i}"))
        assert reason is None
    assert len(gate.history) == 5


def test_file_changed_without_failures_increasing_counts_as_progress():
    gate = PG.ProgressGate(stall_ticks=2, loop_repeats=3)
    # failing count stays flat, but the file keeps changing each tick with a distinct signature.
    assert gate.observe(_tick(elapsed=1, n_failing=3, signature="a", file_changed=True)) is None
    assert gate.observe(_tick(elapsed=2, n_failing=3, signature="b", file_changed=True)) is None
    assert gate.observe(_tick(elapsed=3, n_failing=3, signature="c", file_changed=True)) is None


def test_two_consecutive_flat_ticks_stall():
    """No failure decrease, no file change -> flat. The SECOND flat tick (stall_ticks=2) stops."""
    gate = PG.ProgressGate(stall_ticks=2, loop_repeats=3)
    r1 = gate.observe(_tick(elapsed=1, n_failing=5, signature="s1", file_changed=False))
    assert r1 is None
    r2 = gate.observe(_tick(elapsed=2, n_failing=5, signature="s2", file_changed=False))
    assert r2 == "stalled"


def test_failures_increasing_does_not_count_as_progress_even_if_file_changed():
    gate = PG.ProgressGate(stall_ticks=2, loop_repeats=5)
    # tick 1 establishes a baseline (5 failing) with progress (file changed, no prior count to
    # compare against yet), so it does not itself count as flat.
    r1 = gate.observe(_tick(elapsed=1, n_failing=5, signature="s1", file_changed=True))
    assert r1 is None
    # tick 2: failures ROSE (5 -> 8) even though the file changed again -> not progress -> flat 1.
    r2 = gate.observe(_tick(elapsed=2, n_failing=8, signature="s2", file_changed=True))
    assert r2 is None
    # tick 3: still not decreasing and unchanged -> flat 2 -> stalled.
    r3 = gate.observe(_tick(elapsed=3, n_failing=8, signature="s3", file_changed=False))
    assert r3 == "stalled"


def test_same_signature_three_times_loops_even_while_nominally_progressing():
    """The file "changing" every tick without failures rising reads as progress under the flat-run
    counter alone -- the signature check is the independent guard against exactly that."""
    gate = PG.ProgressGate(stall_ticks=2, loop_repeats=3)
    assert gate.observe(_tick(elapsed=1, n_failing=3, signature="REPEAT", file_changed=True)) is None
    assert gate.observe(_tick(elapsed=2, n_failing=3, signature="REPEAT", file_changed=True)) is None
    assert gate.observe(_tick(elapsed=3, n_failing=3, signature="REPEAT", file_changed=True)) == "looping"


def test_signature_run_resets_on_a_new_signature():
    gate = PG.ProgressGate(stall_ticks=5, loop_repeats=3)
    gate.observe(_tick(elapsed=1, n_failing=3, signature="A"))
    gate.observe(_tick(elapsed=2, n_failing=3, signature="A"))
    r = gate.observe(_tick(elapsed=3, n_failing=3, signature="B"))
    assert r is None   # signature changed -> run resets, no loop despite 2 flat ticks < stall_ticks=5


def test_undeterminable_n_failing_is_not_treated_as_a_decrease():
    """n_failing=None (grade could not run) must never be read as progress via a false 'decrease'."""
    gate = PG.ProgressGate(stall_ticks=2, loop_repeats=5)
    # tick 1: file changed -> counts as progress, establishing a real (non-None) baseline.
    r0 = gate.observe(_tick(elapsed=0, n_failing=5, signature="s0", file_changed=True))
    assert r0 is None
    # tick 2: ungradeable (None) and no file change -> flat 1 (must not read as a "decrease").
    r1 = gate.observe(_tick(elapsed=1, n_failing=None, signature="s1"))
    assert r1 is None
    # tick 3: still ungradeable -> flat 2 -> stalled.
    r2 = gate.observe(_tick(elapsed=2, n_failing=None, signature="s2"))
    assert r2 == "stalled"


# --------------------------------------------------------------------------- run_progress_gated (orchestrator)
class FakeProc:
    """Mirrors the subprocess.Popen surface the orchestrator needs. Never spawns anything real."""
    def __init__(self, finish_at_poll=None):
        self.polls = 0
        self.killed = False
        self.waited = False
        self.returncode = None
        self._finish_at_poll = finish_at_poll

    def poll(self):
        self.polls += 1
        if self._finish_at_poll is not None and self.polls >= self._finish_at_poll:
            self.returncode = 0
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self):
        self.waited = True
        return self.returncode


class _Clock:
    def __init__(self, t0=1_000_000.0):
        self.t = t0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


def _script_snapshot(script):
    """A snapshot_fn fed from a pre-built list of Ticks. Raises if the run polls it more times
    than the test scripted -- silent exhaustion would let a test pass on a shorter run than it
    thinks it verified (same convention as benchmark/bench/tests/conftest.py's fakes)."""
    it = iter(script)

    def _fn(elapsed_s):
        try:
            return next(it)
        except StopIteration:
            raise AssertionError("snapshot_fn called more times than the test scripted")
    return _fn


def test_process_completing_before_any_tick_reports_completed_with_no_ticks():
    proc = FakeProc(finish_at_poll=1)
    clock = _Clock()
    result = PG.run_progress_gated(proc, _script_snapshot([]), tick_s=300, hard_ceiling_s=3600,
                                   now_fn=clock.now, sleep_fn=clock.sleep)
    assert result.stop_reason == "completed"
    assert result.ticks == []
    assert not proc.killed
    assert proc.waited


def test_hard_ceiling_fires_when_ticks_keep_reporting_progress_forever():
    proc = FakeProc(finish_at_poll=None)   # never exits on its own
    clock = _Clock()
    # Every tick shows the failing count decreasing -- always "progress" -- so only the hard
    # ceiling can end this run.
    script = [_tick(elapsed=100, n_failing=100), _tick(elapsed=200, n_failing=90),
              _tick(elapsed=300, n_failing=80), _tick(elapsed=400, n_failing=70)]
    result = PG.run_progress_gated(proc, _script_snapshot(script), tick_s=100,
                                   hard_ceiling_s=250, poll_s=10,
                                   now_fn=clock.now, sleep_fn=clock.sleep)
    assert result.stop_reason == "hard_ceiling"
    assert proc.killed
    assert result.elapsed_s == pytest.approx(250, abs=1e-6)
    # Two ticks (at elapsed 100 and 200) land before the ceiling at 250; the script's later
    # entries are never consumed, proving the ceiling pre-empts before a 3rd tick is due (300).
    assert len(result.ticks) == 2


def test_stall_kills_the_process_and_reports_stalled():
    proc = FakeProc(finish_at_poll=None)
    clock = _Clock()
    script = [_tick(elapsed=300, n_failing=5, signature="s1", file_changed=False),
              _tick(elapsed=600, n_failing=5, signature="s2", file_changed=False)]
    result = PG.run_progress_gated(proc, _script_snapshot(script), tick_s=300,
                                   hard_ceiling_s=3600, poll_s=50, stall_ticks=2,
                                   now_fn=clock.now, sleep_fn=clock.sleep)
    assert result.stop_reason == "stalled"
    assert proc.killed
    assert len(result.ticks) == 2


def test_loop_kills_the_process_and_reports_looping():
    proc = FakeProc(finish_at_poll=None)
    clock = _Clock()
    script = [_tick(elapsed=300, n_failing=3, signature="X", file_changed=True),
              _tick(elapsed=600, n_failing=3, signature="X", file_changed=True),
              _tick(elapsed=900, n_failing=3, signature="X", file_changed=True)]
    result = PG.run_progress_gated(proc, _script_snapshot(script), tick_s=300,
                                   hard_ceiling_s=3600, poll_s=50, loop_repeats=3,
                                   now_fn=clock.now, sleep_fn=clock.sleep)
    assert result.stop_reason == "looping"
    assert proc.killed
    assert len(result.ticks) == 3


def test_completed_wins_even_if_a_tick_was_due_at_the_same_moment():
    """The process exiting naturally is ALWAYS reported as completed -- proc.poll() is consulted
    before any tick/ceiling logic on every loop iteration."""
    proc = FakeProc(finish_at_poll=2)
    clock = _Clock()
    result = PG.run_progress_gated(proc, _script_snapshot([_tick(elapsed=300, n_failing=1)]),
                                   tick_s=1, hard_ceiling_s=3600, poll_s=1,
                                   now_fn=clock.now, sleep_fn=clock.sleep)
    assert result.stop_reason == "completed"


def test_policy_defaults_match_the_recovered_design():
    assert PG.DEFAULT_TICK_S == 300
    assert PG.DEFAULT_STALL_TICKS == 2
    assert PG.DEFAULT_LOOP_REPEATS == 3
