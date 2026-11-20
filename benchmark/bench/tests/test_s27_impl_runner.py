"""S27 §5.1 (the final grade is regraded in the probe on the kept snapshot), §6 / C365 (an abort never turns an in-flight grade
into a fault that replaces the original exception), §5.8 (the typed abort causes), §3.1 / §3.2 (c) (the hermetic markers)."""
from __future__ import annotations

import threading
import time

import pytest

from bench import arm_runner as ar
from bench import item_barrier as ib
from bench import proc_guard as pg
from bench import token_turn_gate as tg


class Outcome:
    def __init__(self, failing=0, outcome="parsed"):
        self.failing, self.tampered, self.outcome = failing, False, outcome
        self.resources = dict(grader_mem_kill=outcome == "mem_kill", grader_oom=False)


class Corpus:
    def __init__(self, script):
        self.script, self.calls, self.snaps = list(script), [], []

    def grade(self, snap, prepared, private, guard, keep, seq, boundary, final):
        self.calls.append((snap, seq, final))
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


class Guard:
    def __init__(self):
        self.killed = []

    def kill_role(self, role=None):
        self.killed.append(role)
        return []


def seqs():
    n = iter(range(1, 100))
    return lambda: next(n)


INFRA = tg.GraderInfraError("docker command failed (run): Cannot connect to the Docker daemon", kind="transport")   # X6: typed


def test_a_grader_transport_fault_on_a_finished_item_is_regraded_and_accepted():
    corpus, guard, term = Corpus([INFRA, Outcome(0)]), Guard(), {}
    final = ar.final_grade(corpus, "SNAP", None, None, guard, None, seqs(), 7, term)
    assert final.failing == 0 and len(corpus.calls) == 2 and term["final_regrades"] == 1 and guard.killed == ["grader"]


def test_two_faults_then_a_pass_is_accepted_on_the_one_kept_snapshot():
    corpus, term = Corpus([INFRA, INFRA, Outcome(0)]), {}
    ar.final_grade(corpus, "SNAP", None, None, Guard(), None, seqs(), 7, term)
    assert [c[0] for c in corpus.calls] == ["SNAP"] * 3 and [c[1] for c in corpus.calls] == [1, 2, 3]
    assert all(c[2] is True for c in corpus.calls) and term["final_regrades"] == 2


def test_three_faults_raise_the_final_grade_infrastructure_abort():
    corpus, term = Corpus([INFRA, INFRA, INFRA]), {}
    with pytest.raises(tg.GraderInfraAbort) as err:
        ar.final_grade(corpus, "SNAP", None, None, Guard(), None, seqs(), 7, term)
    assert err.value.stage == "final_grade" and len(err.value.faults) == 3 and len(term["final_grade_faults"]) == 3
    assert ar.harness_fault_cause(err.value) == ("grader_infra", "final_grade")


@pytest.mark.parametrize("outcome", ["timeout", "mem_kill", "oom", "tampered"])
def test_a_grader_timeout_or_mem_kill_is_the_outcome_and_never_regraded(outcome):
    corpus, term = Corpus([Outcome(3, outcome)]), {}
    final = ar.final_grade(corpus, "SNAP", None, None, Guard(), None, seqs(), 7, term)
    assert final.outcome == outcome and len(corpus.calls) == 1 and term["final_regrades"] == 0


def test_a_fault_outside_the_closed_list_propagates_unregraded():
    corpus = Corpus([tg.TransportAbort("unreadable Python report: no test events")])
    with pytest.raises(tg.TransportAbort) as err:
        ar.final_grade(corpus, "SNAP", None, None, Guard(), None, seqs(), 7, {})
    assert not isinstance(err.value, tg.GraderInfraAbort) and len(corpus.calls) == 1


def test_the_closed_infrastructure_list():
    # X6: typed at the source (`GraderInfraError.kind` on the closed list); the message text is never consulted
    for kind in tg.GraderInfraError.KINDS:
        assert tg.grader_infra_fault(tg.GraderInfraError("x", kind=kind)), kind
    with pytest.raises(ValueError):
        tg.GraderInfraError("x", kind="timeout")
    for text in ("missing docker runtime: x", "tg2 stage failed (rc=125 timeout=False): x", "Docker infrastructure failure: x",
                 "tg2 image x does not match the pinned id", "missing grader interpreter/runtime: x", "malformed Go report"):
        assert not tg.grader_infra_fault(tg.TransportAbort(text)), text
    assert not tg.grader_infra_fault(ValueError("docker command failed"))


# -------------------------------------------------------------------------------- the grade worker: interim faults, C365
class Gate:
    def __init__(self):
        self.pending, self.stall_wait, self.stop_reason, self.request_usage, self.grades = set(), None, None, [], []

    def on_capture(self, boundary):
        self.pending.add(boundary)

    def on_grade(self, *a):
        self.grades.append(a)


class Snap:
    manifest = {"a": "1"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class SnapCorpus:
    def manifest(self, work):
        return {"x": str(time.time_ns())}

    def snapshot(self, work, private, boundary):
        return Snap()


def worker(grade):
    lock = threading.RLock()
    w = ar.GradeWorker(Gate(), lock, "work", "private", grade, join_timeout_s=5, corpus=SnapCorpus())
    w.start()
    return w


def test_an_interim_grader_infrastructure_fault_is_a_pre_outcome_harness_fault():
    def grade(snap):
        raise INFRA
    w = worker(grade)
    w.notify(1)
    deadline = time.monotonic() + 5
    while w.failure is None and time.monotonic() < deadline:
        time.sleep(0.01)
    with pytest.raises(tg.GraderInfraAbort) as err:
        w.check()
    assert err.value.stage == "generation" and ar.harness_fault_cause(err.value) == ("grader_infra", "generation")


def test_the_c365_slow_grader_a_grade_failing_after_the_abort_mark_is_cancelled_never_raised():
    started, release = threading.Event(), threading.Event()

    def grade(snap):                      # the slow-grader seam: in flight when the abort lands
        started.set()
        release.wait(5)
        raise tg.TransportAbort("unreadable Python report (the grader was SIGKILLed)")
    w = worker(grade)
    w.notify(1)
    assert started.wait(5)
    w.cancel()                            # the abort path marks the worker BEFORE it kills the grader role
    release.set()                         # ... the killed grade now fails
    assert w.abort_join(ar.ABORT_GRADE_JOIN_S) is None
    assert w.failure is None and w.grade_cancelled and "unreadable Python report" in w.grade_cancelled
    w.check()                             # never raised: the original exception (SystemExit 143) propagates
    w.notify(2)
    assert w.queued is None               # nothing more is queued or dequeued after the mark


def test_a_grade_failure_stored_before_the_mark_stays_a_fault():
    def grade(snap):
        raise tg.TransportAbort("malformed Go report")
    w = worker(grade)
    w.notify(1)
    deadline = time.monotonic() + 5
    while w.failure is None and time.monotonic() < deadline:
        time.sleep(0.01)
    w.cancel()
    fault = w.abort_join(1)
    assert isinstance(fault, tg.TransportAbort) and w.grade_cancelled is None


def test_the_abort_join_is_bounded_on_the_graceful_client_scale():
    assert ar.ABORT_GRADE_JOIN_S == 2 * ar.GRACEFUL_CLIENT_S


# -------------------------------------------------------------------------------- §5.8 the typed causes; §3 markers
def test_the_typed_abort_causes():
    assert ar.harness_fault_cause(pg.CleanupUncertain("x")) == ("cleanup_uncertain", None)
    assert ar.harness_fault_cause(ib.BarrierTimeout("not acknowledged")) == ("hook_infra", None)
    assert ar.harness_fault_cause(tg.TransportAbort("connection")) is None


def test_the_hermetic_markers_are_the_runs_own_home_and_xdg_only(tmp_path):
    run = tmp_path / "run-x"
    env = dict(HOME=str(run / "home"), XDG_CONFIG_HOME=str(run / "cfg"), XDG_DATA_HOME="/elsewhere/data", PATH="/usr/bin")
    assert ar.hermetic_markers(env, run) == dict(HOME=str(run / "home"), XDG_CONFIG_HOME=str(run / "cfg"))


def test_the_runner_records_the_kill_time_offsets_and_the_row_carries_the_cleanup_status():
    import inspect
    src = inspect.getsource(ar._run_item)
    assert "ingested_offset_at_count=getattr(stream, \"offset\", None)" in src and 'termination["signal_offset"] = size' in src
    assert 'termination_out["step_end_offsets"]' in src and 'termination_out["last_step_start"]' in src
    assert 'cleanup_status=ctx.get("cleanup_status")' in inspect.getsource(ar._main)
    assert 'man["probe_session"]' in inspect.getsource(ar._main)


def test_the_interrupt_positive_polls_for_a_generation_in_flight_through_the_same_stop_path():
    import inspect
    src = inspect.getsource(ar._run_item)
    assert 'reason = "interrupt"' in src and "INTERRUPT_DEADLINE_S" in src and "terminate_client(reason)" in src
    assert ar.INTERRUPT_DEADLINE_S == 120.0
    from bench import run_config as rc, tg1_runner, tg2_runner
    assert "interrupt" in tg1_runner.TG1_POLICY.inject_allowed and "interrupt" in tg2_runner.TG2_POLICY.inject_allowed
    assert rc.INJECT_POLICY["interrupt"] == {"gate": {}, "hygiene": {}} and rc.INJECT_KINDS == ("stall", "loop", "alloc")
