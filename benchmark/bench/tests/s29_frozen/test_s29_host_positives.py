"""S29 frozen tests, the tg2 positives record records a host change and does not fail for it (spec H4; C384).

Classes: [FIX] reproduces a failure the spec fixes (today a host change before / after the positives session is appended to the
record's `problems`, the verdict is FAIL and the command exits 1); [INV] preserves an invariant; [NEW] new behaviour. Fixtures: the
`s26_support.PosOps` positives seam (real-shaped inject rows) over a temp `HostWorld` that the real `host_env.fingerprint()` /
`diff()` read.

ASSUMPTION (mechanism free): "recorded where a reader sees it" = the change text `host_env.diff` produces appears in the sealed
record OUTSIDE its two raw fingerprints (`host_env`, `host_env_after`, which a reader would have to diff by hand) and outside
`problems` (a host change is not a problem); the field name is not pinned."""
from __future__ import annotations

import json

import pytest

from bench import p426_hooks as ph
from bench.tests.s26_frozen import s26_support as X
from bench.tests.s29_frozen import s29_support as S

ADDED, JEST, JDK = S.ADDED, S.JEST, S.JDK
RAW = ("host_env", "host_env_after", "problems")


@pytest.fixture
def world(tmp_path):
    return X.HostWorld(tmp_path / "host")


def run_pos(tmp_path, monkeypatch, world, **kw):
    ops = X.PosOps(tmp_path, world, **kw)
    rc, out = X.positives(tmp_path, monkeypatch, ops)
    return rc, X.record(out), ops


def beside(doc):
    """The record without its raw fingerprints and its problems."""
    return {k: v for k, v in doc.items() if k not in RAW}


HOOKS = {"grade": lambda world: (lambda lang, variant: S.add_jdk(world)),
         "inject": lambda world: (lambda lang, kind: S.add_jdk(world)),
         "session_exit": lambda world: (lambda: S.add_jdk(world))}


@pytest.mark.parametrize("where", ["grade", "inject", "session_exit"])
def test_fix_h4_a_host_change_during_the_positives_is_recorded_and_the_record_passes(tmp_path, monkeypatch, world, where):
    """[FIX] H4: the host gains a formula (a) while the grades run (the first fingerprint is stale before the session opens), (b)
    inside an inject, (c) as the serving session closes: the sealed record is still PASS, `problems` is empty, rc 0, the change is
    in the record beside the fingerprints."""
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, hooks={where: HOOKS[where](world)})
    assert rc == 0 and doc["verdict"] == "PASS" and doc["problems"] == [] and ph.sealed_ok(doc)
    assert JDK in json.dumps(beside(doc)), f"the change is nowhere in the record outside the raw fingerprints (keys {sorted(doc)})"
    assert doc["host_env"] != doc["host_env_after"]                    # the raw fingerprints are still carried


def test_fix_h4_the_v8_freeze_accepts_a_positives_record_that_carries_a_host_change(tmp_path, monkeypatch, world):
    """[FIX] the consumer of the record (`p426_freeze.positives_problems`, what `v8` runs on `positives.json`): a PASS record with a
    host change beside it is accepted (identity, coverage and verdict are what it checks)."""
    from bench import p426_freeze as fz
    from bench import tg2_grade
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, hooks={"session_exit": lambda: S.add_jdk(world)})
    assert rc == 0 and JDK in json.dumps(beside(doc))
    assert fz.positives_problems(doc, arm="n16", commit=X.COMMIT, identity=X.IDENT, frozen_prompt_date=X.DATE,
                                 image_id=tg2_grade.pinned_image_id()) == []


def test_inv_h4_the_v8_check_used_above_accepts_a_clean_record(tmp_path, monkeypatch, world):
    """[INV] instrument control for the test above: the same `positives_problems` call accepts a clean record."""
    from bench import p426_freeze as fz
    from bench import tg2_grade
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world)
    assert rc == 0
    assert fz.positives_problems(doc, arm="n16", commit=X.COMMIT, identity=X.IDENT, frozen_prompt_date=X.DATE,
                                 image_id=tg2_grade.pinned_image_id()) == []


def test_fix_h4_each_host_change_is_recorded(tmp_path, monkeypatch, world):
    def both():
        S.add_jdk(world)
        S.add_jest(world)
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, hooks={"session_exit": both})
    assert rc == 0 and doc["verdict"] == "PASS" and doc["problems"] == []
    text = json.dumps(beside(doc))
    assert JDK in text and JEST in text


def test_fix_h4_an_exception_and_a_host_change_the_exception_alone_fails_the_record(tmp_path, monkeypatch, world):
    """[FIX] H4 + "failure path kept": the exception is still the record's problem (FAIL, rc 1); the host change is recorded beside
    it, not as a second problem."""
    def boom(lang, kind):
        S.add_jdk(world)
        raise RuntimeError("kaboom")
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world, hooks={"inject": boom})
    assert rc == 1 and doc["verdict"] == "FAIL" and ph.sealed_ok(doc)
    assert doc["problems"] == ["exception: RuntimeError: kaboom"]
    assert JDK in json.dumps(beside(doc))


def test_fix_h4_a_failed_positive_still_fails_the_record_with_a_host_change_beside_it(tmp_path, monkeypatch, world):
    """[FIX] (+ INV: the real failure still fails) a positive that really failed (here: a stall inject the verifier rejects) keeps FAIL / rc 1 whether or not the host
    changed; the host change is not what decides (the problems are those of the run on an unchanged host)."""
    bad = {(X.LANGS[0], "stall"): "FAIL:rss"}
    plain_world = X.HostWorld(tmp_path / "plain" / "host")
    rc0, doc0, _ = run_pos(tmp_path / "plain", monkeypatch, plain_world, verdicts=bad)
    changed_world = X.HostWorld(tmp_path / "changed" / "host")
    rc, doc, _ = run_pos(tmp_path / "changed", monkeypatch, changed_world, verdicts=bad,
                         hooks={"session_exit": lambda: S.add_jdk(changed_world)})
    assert rc0 == 1 and doc0["verdict"] == "FAIL" and rc == 1 and doc["verdict"] == "FAIL"
    assert doc0["problems"] and doc["problems"] == doc0["problems"]
    assert JDK in json.dumps(beside(doc))


def test_inv_h4_an_unchanged_host_passes_with_no_host_change_recorded(tmp_path, monkeypatch, world):
    """[INV] no false positive: an unchanged host leaves no change text beside the fingerprints."""
    rc, doc, _ = run_pos(tmp_path, monkeypatch, world)
    assert rc == 0 and doc["verdict"] == "PASS" and doc["problems"] == [] and ph.sealed_ok(doc)
    assert doc["host_env"] == doc["host_env_after"] == world.fingerprint()
    assert "Homebrew" not in json.dumps(beside(doc))
