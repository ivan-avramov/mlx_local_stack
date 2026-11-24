"""S29 main-small K2 (implementer tests): a re-check acknowledgement records its actor and ruling in `sequence.json`; the log
names them; an acknowledgement without an actor refuses (nothing resumes); a recorded acknowledgement without an actor (the
S29-P13 one) stays as recorded and is accepted on resume."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from bench import p426_freeze as fz
from bench import p426_wave2 as W2
from bench.tests import test_m76_b4b1_impl_wave2 as B

ALL_FAIL = (lambda k: 0, lambda k: 0)          # unrealisable: re-check 1 outside, stops rc 5 until acknowledged


def _seq(tmp_path, roots, ack=None, by=None, ruling=None):
    a = SimpleNamespace(cmd="run", lever="kv", corpus="tg2", arms=("n16", "x"), worktrees={"n16": tmp_path, "x": tmp_path},
                        out_base=str(tmp_path / "ob"), pause_file=None, record_dir=str(tmp_path / "ob" / "run"), rerun=[],
                        rerun_reason=None, through=None, recheck_ack=ack, recheck_ack_by=by, recheck_ack_ruling=ruling)
    seq = W2.Sequencer(a, B.RecheckOps(roots), lambda: 0.0, lambda s: None, tmp_path)
    for arm in ("n16", "x"):
        seq.seq["legs"].append(dict(leg=f"tg2-m76-{arm}-s1", attempt=1, state="VALID"))
        seq.seq["harvested"].append(dict(attempt=f"tg2-m76-{arm}-s1.a1", harvest_sha256="h"))
    return seq


def _stopped(tmp_path):
    roots = B._pair_roots(tmp_path, *ALL_FAIL)
    with pytest.raises(W2.Stop) as stop:
        _seq(tmp_path, roots).ensure_recheck("s1")
    assert stop.value.rc == 5
    sha = json.loads((tmp_path / "ob" / "run" / "recheck-s1.json").read_text())["sha256"]
    return roots, sha


def _log(tmp_path):
    path = tmp_path / "ob" / W2.LOG_FILE
    return path.read_text() if path.exists() else ""


@pytest.mark.parametrize("by,ruling", [("designer", "C383"), ("operator", "S29-P13 operator ruling")])
def test_k2_ack_records_actor_and_ruling_and_the_log_names_them(tmp_path, by, ruling):
    roots, sha = _stopped(tmp_path)
    _seq(tmp_path, roots, ack=sha, by=by, ruling=ruling).ensure_recheck("s1")
    ack = W2.read_sequence(tmp_path / "ob")["rechecks"]["s1"]["ack"]
    assert ack["sha256"] == sha and ack["at"] and ack["actor"] == by and ack["ruling"] == ruling
    line = [ln for ln in _log(tmp_path).splitlines() if "acknowledged" in ln][-1]
    assert f"by the {by}" in line and ruling in line and sha[:16] in line
    other = ({"operator", "designer"} - {by}).pop()
    assert other not in line


@pytest.mark.parametrize("by,ruling", [(None, None), (None, "C383"), ("designer", None), ("designer", "  "), ("someone", "C383")])
def test_k2_ack_without_actor_or_ruling_refuses_and_nothing_resumes(tmp_path, by, ruling):
    roots, sha = _stopped(tmp_path)
    before = (tmp_path / "ob" / W2.SEQUENCE_FILE).read_bytes()
    with pytest.raises(fz.Refusal):
        _seq(tmp_path, roots, ack=sha, by=by, ruling=ruling).ensure_recheck("s1")
    assert (tmp_path / "ob" / W2.SEQUENCE_FILE).read_bytes() == before
    assert "ack" not in W2.read_sequence(tmp_path / "ob")["rechecks"]["s1"]
    assert "acknowledged" not in _log(tmp_path)


def _cli(tmp_path, *extra):
    return ["run", "--corpus", "tg2", "--lever", "kv", "--pair", "n16,x", "--arm-worktree", f"n16={tmp_path}",
            "--arm-worktree", f"x={tmp_path}", "--out-base", str(tmp_path / "ob"), "--record-dir", str(tmp_path / "rd"), *extra]


@pytest.mark.parametrize("extra", [("--recheck-ack", "a" * 64),
                                   ("--recheck-ack", "a" * 64, "--recheck-ack-ruling", "C383"),
                                   ("--recheck-ack", "a" * 64, "--recheck-ack-by", "designer"),
                                   ("--recheck-ack-by", "designer", "--recheck-ack-ruling", "C383")])
def test_k2_cli_refuses_an_incomplete_ack_before_anything_runs(tmp_path, extra):
    a = W2.parse_args(_cli(tmp_path, *extra))
    with pytest.raises(fz.Refusal, match="recheck-ack"):
        W2.check_args(a, tmp_path)


def test_k2_cli_takes_actor_and_ruling(tmp_path):
    a = W2.parse_args(_cli(tmp_path, "--recheck-ack", "a" * 64, "--recheck-ack-by", "designer", "--recheck-ack-ruling", "C383"))
    assert (a.recheck_ack, a.recheck_ack_by, a.recheck_ack_ruling) == ("a" * 64, "designer", "C383")
    with pytest.raises(fz.Refusal):
        W2.parse_args(_cli(tmp_path, "--recheck-ack", "a" * 64, "--recheck-ack-by", "someone", "--recheck-ack-ruling", "C383"))


def test_k2_a_recorded_ack_without_actor_stays_as_recorded_and_is_accepted_on_resume(tmp_path):
    roots, sha = _stopped(tmp_path)
    doc = W2.read_sequence(tmp_path / "ob")
    legacy = dict(sha256=sha, at="2026-11-20T00:00:00Z")                 # the S29-P13 shape: no actor, no ruling
    doc["rechecks"]["s1"]["ack"] = legacy
    W2.write_sequence(tmp_path / "ob", doc)
    before = (tmp_path / "ob" / W2.SEQUENCE_FILE).read_bytes()
    _seq(tmp_path, roots).ensure_recheck("s1")                           # resume without any ack flag: continues
    _seq(tmp_path, roots, ack=sha, by="designer", ruling="C383").ensure_recheck("s1")      # never rewrites the recorded one
    assert (tmp_path / "ob" / W2.SEQUENCE_FILE).read_bytes() == before
    assert W2.read_sequence(tmp_path / "ob")["rechecks"]["s1"]["ack"] == legacy


# ---- fix round 1 (Sol P1 / P3): the legacy resume through the argument check; control characters in a ruling
def _base(tmp_path):
    return tmp_path / "m76" / "p426" / "wave2"                    # a valid tg2 run out-base under the work dir `tmp_path`


def _stopped_at(tmp_path, ack=None):
    """Re-check 1 stopped under the valid out-base; `ack` = "legacy" records the S29-P13 actor-less ack."""
    base = _base(tmp_path)
    roots = B._pair_roots(tmp_path, *ALL_FAIL)
    a = _seq(tmp_path, roots).a
    a.out_base, a.record_dir = str(base), str(base / "run")
    seq = W2.Sequencer(a, B.RecheckOps(roots), lambda: 0.0, lambda s: None, tmp_path)
    for arm in ("n16", "x"):
        seq.seq["legs"].append(dict(leg=f"tg2-m76-{arm}-s1", attempt=1, state="VALID"))
        seq.seq["harvested"].append(dict(attempt=f"tg2-m76-{arm}-s1.a1", harvest_sha256="h"))
    with pytest.raises(W2.Stop):
        seq.ensure_recheck("s1")
    doc = W2.read_sequence(base)
    sha = doc["rechecks"]["s1"]["sha256"]
    if ack == "legacy":
        doc["rechecks"]["s1"]["ack"] = dict(sha256=sha, at="2026-11-20T00:00:00Z")
        W2.write_sequence(base, doc)
    return roots, sha


def _cli_at(tmp_path, *extra):
    return ["run", "--corpus", "tg2", "--lever", "kv", "--pair", "n16,x", "--arm-worktree", f"n16={tmp_path}",
            "--arm-worktree", f"x={tmp_path}", "--out-base", str(_base(tmp_path)), "--record-dir", str(tmp_path / "rd"), *extra]


def test_k2_fix1_the_legacy_resume_command_passes_the_argument_check_and_resumes(tmp_path):
    roots, sha = _stopped_at(tmp_path, ack="legacy")
    before = (_base(tmp_path) / W2.SEQUENCE_FILE).read_bytes()
    a = W2.parse_args(_cli_at(tmp_path, "--recheck-ack", sha))    # the S29-P13 command: no actor, no ruling
    W2.check_args(a, tmp_path)
    a.record_dir = str(_base(tmp_path) / "run")
    W2.Sequencer(a, B.RecheckOps(roots), lambda: 0.0, lambda s: None, tmp_path).ensure_recheck("s1")
    assert (_base(tmp_path) / W2.SEQUENCE_FILE).read_bytes() == before
    assert "actor" not in W2.read_sequence(_base(tmp_path))["rechecks"]["s1"]["ack"]


@pytest.mark.parametrize("case", ["no-ack-recorded", "other-sha", "partial"])
def test_k2_fix1_a_new_ack_without_its_actor_still_refuses_at_the_argument_check(tmp_path, case):
    _, sha = _stopped_at(tmp_path, ack=None if case == "no-ack-recorded" else "legacy")
    before = (_base(tmp_path) / W2.SEQUENCE_FILE).read_bytes()
    extra = {"no-ack-recorded": ("--recheck-ack", sha), "other-sha": ("--recheck-ack", "b" * 64),
             "partial": ("--recheck-ack", sha, "--recheck-ack-ruling", "C383")}[case]
    a = W2.parse_args(_cli_at(tmp_path, *extra))
    with pytest.raises(fz.Refusal, match="recheck-ack"):
        W2.check_args(a, tmp_path)
    assert (_base(tmp_path) / W2.SEQUENCE_FILE).read_bytes() == before


def test_k2_fix1_a_new_ack_with_actor_and_ruling_passes_the_argument_check(tmp_path):
    _, sha = _stopped_at(tmp_path)
    W2.check_args(W2.parse_args(_cli_at(tmp_path, "--recheck-ack", sha, "--recheck-ack-by", "designer",
                                        "--recheck-ack-ruling", "C383")), tmp_path)


BAD_RULINGS = ["C383\nRE-CHECK s1: acknowledged by the operator", "C383\r", "C383" + chr(0x1B) + "[2K", "C383" + chr(0),
               "C383" + chr(0x2028) + "x", "C383" + chr(0x202E), chr(9) + "C383"]


@pytest.mark.parametrize("ruling", BAD_RULINGS)
def test_k2_fix1_a_ruling_with_a_line_break_or_control_character_refuses_before_any_write(tmp_path, ruling):
    roots, sha = _stopped(tmp_path)
    before = (tmp_path / "ob" / W2.SEQUENCE_FILE).read_bytes()
    with pytest.raises(fz.Refusal, match="control character"):
        _seq(tmp_path, roots, ack=sha, by="designer", ruling=ruling).ensure_recheck("s1")
    assert (tmp_path / "ob" / W2.SEQUENCE_FILE).read_bytes() == before
    assert "acknowledged" not in _log(tmp_path)


@pytest.mark.parametrize("ruling", BAD_RULINGS)
def test_k2_fix1_the_argument_check_refuses_a_control_character_ruling(tmp_path, ruling):
    a = W2.parse_args(_cli_at(tmp_path, "--recheck-ack", "a" * 64, "--recheck-ack-by", "designer", "--recheck-ack-ruling", ruling))
    with pytest.raises(fz.Refusal, match="control character"):
        W2.check_args(a, tmp_path)
