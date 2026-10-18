"""P371 phase 1: `bench.chain_hooks` (plan 3.1, R13 R23): chain-owned hooks outside every probe closure."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from bench import chain_hooks as ch

REPO = Path(__file__).resolve().parents[3]


def test_default_hooks_are_no_op_accept():
    hooks = ch.ChainHooks()
    assert hooks.before_attempt("slot") == ch.Disposition.accept()
    assert hooks.after_attempt("slot", {"id": "x"}) == ch.Disposition.accept()
    assert hooks.run_before("slot").kind == "accept" and hooks.run_after("slot", {}).kind == "accept"


def test_disposition_constructors_and_validation():
    d = ch.Disposition
    assert d.accept().kind == "accept" and d.accept().stops_probe is False
    r = d.rerun_same_slot("p201 cheat")
    assert (r.kind, r.reason, r.stops_probe) == ("rerun_same_slot", "p201 cheat", True)
    b = d.block("p201 unclear")
    assert (b.kind, b.reason, b.stops_probe) == ("block", "p201 unclear", True)
    p = d.pre_spawn_incident("server_error")
    assert (p.kind, p.cause, p.stops_probe) == ("pre_spawn_incident", "server_error", True)
    for make in (lambda: d.rerun_same_slot(""), lambda: d.block(""), lambda: d.pre_spawn_incident(""),
                 lambda: ch.Disposition(kind="nope")):
        with pytest.raises(ValueError):
            make()


def test_dispositions_round_trip_through_the_persisted_record():
    for d in (ch.Disposition.accept(), ch.Disposition.rerun_same_slot("why"), ch.Disposition.block("why"),
              ch.Disposition.pre_spawn_incident("connection")):
        assert ch.Disposition.from_dict(d.as_dict()) == d
    with pytest.raises(ValueError):
        ch.Disposition.from_dict({"kind": "rerun_same_slot"})
    with pytest.raises(ValueError):
        ch.Disposition.from_dict({"kind": "bogus"})


def test_the_slot_disposition_vocabulary_of_chain_rows():
    assert ch.slot_disposition(ch.Disposition.accept()) == "accepted"
    assert ch.slot_disposition(ch.Disposition.rerun_same_slot("x")) == "cheat"
    assert ch.slot_disposition(ch.Disposition.block("x")) == "unclear"
    with pytest.raises(ValueError):
        ch.slot_disposition(ch.Disposition.pre_spawn_incident("x"))        # no attempt row exists yet


def test_a_before_hook_may_only_accept_or_stop_pre_spawn_and_an_after_hook_the_reverse():
    class Bad(ch.ChainHooks):
        def before_attempt(self, slot):
            return ch.Disposition.rerun_same_slot("x")

        def after_attempt(self, slot, done):
            return ch.Disposition.pre_spawn_incident("x")

    with pytest.raises(ValueError):
        Bad().run_before("s")
    with pytest.raises(ValueError):
        Bad().run_after("s", {})

    class NotADisposition(ch.ChainHooks):
        def before_attempt(self, slot):
            return "accept"
    with pytest.raises(TypeError):
        NotADisposition().run_before("s")


def test_an_infrastructure_failure_in_a_before_hook_becomes_a_pre_spawn_incident():
    class Health(ch.ChainHooks):
        def before_attempt(self, slot):
            raise ch.HookInfrastructureError("connection")
    d = Health().run_before("s")
    assert d == ch.Disposition.pre_spawn_incident("connection")

    class Boom(ch.ChainHooks):
        def before_attempt(self, slot):
            raise RuntimeError("bug")
    with pytest.raises(RuntimeError):
        Boom().run_before("s")                                            # a hook bug is never swallowed


def test_hooks_receive_the_slot_and_the_done_record():
    seen = []

    class Rec(ch.ChainHooks):
        def after_attempt(self, slot, done):
            seen.append((slot, done))
            return ch.Disposition.block("unclear")
    assert Rec().run_after("s2", {"id": "i"}).kind == "block" and seen == [("s2", {"id": "i"})]


def test_no_probe_entry_closure_contains_chain_hooks_or_web_evidence():
    code = ("import sys; sys.path.insert(0, '.'); from bench import identity_closure as ic; from pathlib import Path; "
            "R = Path('..').resolve(); "
            "names = {p.resolve().relative_to(R).as_posix() for e in ('benchmark/run_tg1_probe.py', "
            "'benchmark/run_oc_probe.py') for p in ic.python_closure(R / e, R)}; "
            "print(sorted(n for n in names if n.endswith(('chain_hooks.py', 'web_evidence.py'))))")
    out = subprocess.run([sys.executable, "-c", code], cwd=REPO / "benchmark", capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"
