"""Shared seams of the S27 test-writer files (no tests here).

`ScriptedGrader` replaces `Tg1Corpus.grade` (the corpus contract's grade call, `corpus.Corpus.grade`) so that the composed runner
tests need no grader interpreter, container or docker: each call returns the next scripted `GradeOutcome`, raises the next
scripted exception, or blocks on an Event (the slow-grader seam).  A grader INFRASTRUCTURE fault is, by assumption G1, the
corpus contract's own typed value `GradeOutcome(outcome="infrastructure")` (`bench.corpus.OUTCOMES`): the one representation the
contract already has for 'a grade that is not a statement about the model's tree and must not be scored'.  If the implementation
signals the fault another way, `infra()` below is the single place to change.
"""
from __future__ import annotations

import threading

from bench.corpus import GradeOutcome
from bench.corpus_tg1 import Tg1Corpus

NO_RESOURCES = dict(grader_mem_kill=False, grader_oom=False)


def model(failing, *, mem_kill=False, oom=False, outcome="parsed"):
    resources = dict(grader_mem_kill=mem_kill, grader_oom=oom)
    return GradeOutcome(failing=failing, leaves=(), tampered=False, outcome="model", resources=resources,
                        phases=(dict(seq=0, boundary=0, final=False, outcome=outcome),), reports={})


def infra():
    """G1 (v2, bound to the candidate and to how the real graders fail): a grade that never measured the tree is a
    `TransportAbort` raised by the grader path whose text names a closed-list fault (here: the docker daemon is unreachable)."""
    try:
        from bench.token_turn_gate import GraderInfraError          # v3 (X6): typed at the source, never matched from text
    except ImportError:                                               # the baseline has no such class
        from bench.token_turn_gate import TransportAbort
        return TransportAbort("docker command failed: Cannot connect to the Docker daemon (grader infrastructure)")
    return GraderInfraError("the docker daemon is unreachable (grader infrastructure)", kind="transport")


class ScriptedGrader:
    """`script`: list of GradeOutcome / Exception / callable(final) for the INTERIM grades; `final_script` for the final grade.
    Past the end of a script the last entry repeats. `calls` records `(final, boundary)` in order."""

    def __init__(self, script=None, final_script=None):
        self.script = list(script or [model(1)])
        self.final_script = list(final_script or [model(0)])
        self.calls = []
        self.final_snaps = []                     # the snapshot object each final grade received
        self.lock = threading.Lock()
        self.entered = threading.Event()          # set when an interim grade has started

    def __call__(self, corpus, snap, prepared, private, guard, keep, seq, boundary, final):
        with self.lock:
            self.calls.append((bool(final), boundary))
            if final:
                self.final_snaps.append(snap)
            script = self.final_script if final else self.script
            index = sum(1 for f, _ in self.calls if f == bool(final)) - 1
            step = script[min(index, len(script) - 1)]
        if not final:
            self.entered.set()
        if callable(step) and not isinstance(step, GradeOutcome):
            step = step(final)
        if isinstance(step, BaseException):
            raise step
        return step

    @property
    def finals(self):
        return [c for c in self.calls if c[0]]

    @property
    def interims(self):
        return [c for c in self.calls if not c[0]]

    def install(self, monkeypatch):
        outer = self

        def grade(self, snap, prepared, private, guard, keep, seq, boundary, final):
            return outer(self, snap, prepared, private, guard, keep, seq, boundary, final)
        monkeypatch.setattr(Tg1Corpus, "grade", grade)
        return self
