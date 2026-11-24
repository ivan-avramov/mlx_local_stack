"""S29 main-small K2 (spec `docs/specs/s29-main-small.md`): a re-check acknowledgement records and logs WHO acknowledged and on WHAT
ruling; an acknowledgement without an actor refuses; the legacy actor-less record (S29-P13) stays as recorded and resumes.

Outcome tests. The spec names no argument spelling, so the two inputs are the Sequencer args `recheck_ack_actor` /
`recheck_ack_ruling` (CLI guess `--recheck-ack-actor` / `--recheck-ack-ruling`) and the record keys are `rechecks.s1.ack.actor` /
`.ruling`; both guesses live in the three constants below and nowhere else.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from bench import p426_wave2 as W2
from bench import p426_freeze as fz
from bench.tests import test_m76_b4b1_impl_wave2 as T

ACTOR_ARG, RULING_ARG = "recheck_ack_by", "recheck_ack_ruling"
ACK_ACTOR_KEY, ACK_RULING_KEY = "actor", "ruling"
RULING = "C383"
UNREALISABLE = (lambda k: 0, lambda k: 0)                      # the all-fail pair: re-check 1 is outside -> rc 5 until acknowledged
REFUSES = (W2.Stop, fz.Refusal)


def _seq(tmp_path, roots, ack=None, actor=None, ruling=RULING):
    a = SimpleNamespace(cmd="run", lever="kv", corpus="tg2", arms=("n16", "x"), worktrees={"n16": tmp_path, "x": tmp_path},
                        out_base=str(tmp_path / "ob"), pause_file=None, record_dir=str(tmp_path / "ob" / "run"), rerun=[],
                        rerun_reason=None, through=None, recheck_ack=ack)
    if actor is not None:
        setattr(a, ACTOR_ARG, actor)
    if ruling is not None and actor is not None:
        setattr(a, RULING_ARG, ruling)
    seq = W2.Sequencer(a, T.RecheckOps(roots), lambda: 0.0, lambda s: None, tmp_path)
    for arm in ("n16", "x"):
        seq.seq["legs"].append(dict(leg=f"tg2-m76-{arm}-s1", attempt=1, state="VALID"))
        seq.seq["harvested"].append(dict(attempt=f"tg2-m76-{arm}-s1.a1", harvest_sha256="h"))
    return seq


@pytest.fixture
def stopped(tmp_path):
    """An outside re-check 1 that stopped with rc 5: (roots, the sealed record's sha256)."""
    roots = T._pair_roots(tmp_path, *UNREALISABLE)
    with pytest.raises(W2.Stop) as stop:
        _seq(tmp_path, roots).ensure_recheck("s1")
    assert stop.value.rc == 5
    return roots, json.loads((tmp_path / "ob" / "run" / "recheck-s1.json").read_text())["sha256"]


def _recorded(tmp_path):
    return W2.read_sequence(tmp_path / "ob")["rechecks"]["s1"]


def _log(tmp_path):
    p = tmp_path / "ob" / "sequence.log"
    return p.read_text() if p.exists() else ""


def _ack_lines(tmp_path):
    return [ln for ln in _log(tmp_path).splitlines() if "RE-CHECK s1" in ln and "acknowledged" in ln]


@pytest.mark.parametrize("actor", ["operator", "designer"])
def test_k2_an_acknowledgement_records_its_actor_and_ruling(tmp_path, stopped, actor):
    roots, sha = stopped
    _seq(tmp_path, roots, ack=sha, actor=actor).ensure_recheck("s1")          # no stop: acknowledged
    ack = _recorded(tmp_path)["ack"]
    assert ack["sha256"] == sha and ack["at"]
    assert ack[ACK_ACTOR_KEY] == actor
    assert ack[ACK_RULING_KEY] == RULING


@pytest.mark.parametrize("actor", ["operator", "designer"])
def test_k2_the_log_line_names_the_actor_and_ruling_and_only_that_actor(tmp_path, stopped, actor):
    roots, sha = stopped
    _seq(tmp_path, roots, ack=sha, actor=actor).ensure_recheck("s1")
    lines = _ack_lines(tmp_path)
    assert len(lines) == 1
    line = lines[0]
    assert actor in line and RULING in line and sha[:16] in line
    other = "designer" if actor == "operator" else "operator"
    assert other not in line


def test_k2_a_designer_acknowledgement_is_never_logged_as_the_operators(tmp_path, stopped):
    roots, sha = stopped
    _seq(tmp_path, roots, ack=sha, actor="designer").ensure_recheck("s1")
    assert "acknowledged by the operator" not in _log(tmp_path)


@pytest.mark.parametrize("actor", [None, "", "  ", "robot"], ids=["absent", "empty", "blank", "unknown-actor"])
def test_k2_an_acknowledgement_without_a_valid_actor_refuses_and_nothing_resumes(tmp_path, stopped, actor):
    roots, sha = stopped
    before = (tmp_path / "ob" / "sequence.json").read_text()
    seq = _seq(tmp_path, roots, ack=sha)
    if actor is not None:
        setattr(seq.a, ACTOR_ARG, actor)
        setattr(seq.a, RULING_ARG, RULING)
    with pytest.raises(REFUSES):
        seq.ensure_recheck("s1")
    assert "ack" not in _recorded(tmp_path)                                   # nothing recorded
    assert (tmp_path / "ob" / "sequence.json").read_text() == before          # state file untouched
    assert _ack_lines(tmp_path) == []                                          # and no acknowledgement logged
    with pytest.raises(W2.Stop) as again:                                      # still stopped on the next resume
        _seq(tmp_path, roots).ensure_recheck("s1")
    assert again.value.rc == 5


def test_k2_a_refused_acknowledgement_can_be_redone_with_an_actor(tmp_path, stopped):
    roots, sha = stopped
    with pytest.raises(REFUSES):
        _seq(tmp_path, roots, ack=sha).ensure_recheck("s1")
    _seq(tmp_path, roots, ack=sha, actor="designer").ensure_recheck("s1")
    assert _recorded(tmp_path)["ack"][ACK_ACTOR_KEY] == "designer"


def _legacy(tmp_path, sha):
    """The S29-P13 shape: `ack = {sha256, at}`, no actor, no ruling, written by the baseline sequencer."""
    path = tmp_path / "ob" / "sequence.json"
    doc = json.loads(path.read_text())
    doc["rechecks"]["s1"]["ack"] = dict(sha256=sha, at="2026-11-01T00:00:00Z")
    path.write_text(json.dumps(doc))
    return dict(sha256=sha, at="2026-11-01T00:00:00Z")


@pytest.mark.parametrize("resume", ["same-command-flag-only", "no-flag"])
def test_k2_the_legacy_actorless_record_is_accepted_on_resume_as_recorded(tmp_path, stopped, resume):
    roots, sha = stopped
    legacy = _legacy(tmp_path, sha)
    before_log = _log(tmp_path)
    seq = _seq(tmp_path, roots, ack=sha if resume == "same-command-flag-only" else None)    # no actor given: the old command
    seq.ensure_recheck("s1")                                                   # accepted: no stop, no refusal
    assert _recorded(tmp_path)["ack"] == legacy                                # stays exactly as recorded
    assert "designer" not in _log(tmp_path)[len(before_log):]
    assert "acknowledged by the operator" not in _log(tmp_path)[len(before_log):]   # an actor nobody stated is never asserted


def test_k2_the_legacy_record_is_not_rewritten_with_an_actor_on_a_later_resume(tmp_path, stopped):
    roots, sha = stopped
    legacy = _legacy(tmp_path, sha)
    _seq(tmp_path, roots, ack=sha, actor="designer").ensure_recheck("s1")
    assert _recorded(tmp_path)["ack"] == legacy


def test_k2_an_acknowledgement_of_the_wrong_sha_still_stops_with_rc_5(tmp_path, stopped):
    roots, _ = stopped
    with pytest.raises(W2.Stop) as stop:
        _seq(tmp_path, roots, ack="0" * 64, actor="operator").ensure_recheck("s1")
    assert stop.value.rc == 5 and "ack" not in _recorded(tmp_path)
