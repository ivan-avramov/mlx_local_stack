"""P587 (implementer's red-first tests): the Go grader's stderr has a harvest rule; `--dry-run` collects every problem."""
from __future__ import annotations

from pathlib import Path

import pytest

from bench import p426_harvest as H
from bench.tests import test_b2_s9_harvest as T

TREE = Path(__file__).parent / "fixtures" / "p586" / "leg3_tree.tsv"


def _tree():
    return [line.split("\t", 1) for line in TREE.read_text().splitlines() if line.strip()]


def test_go_stderr_has_an_evidence_rule():
    assert H.classify("evidence", "go__crypto-square.grades/seq-0001/go.stderr") == ("evidence", None)


@pytest.mark.parametrize("rel", ["go.stderr", "x.grades/go.stderr", "x/seq-0001/go.stderr", "x.grades/seq-0001/deeper/go.stderr",
                                 "x.grades/seqx/go.stderr", "x.grades/seq-0001/other.stderr", "x.grades/seq-/go.stderr"])
def test_only_the_exact_go_stderr_shape_has_a_rule(rel):
    assert H.classify("evidence", rel) is None


def test_every_leg3_path_has_a_rule():
    missing = [(k, r) for k, r in _tree() if H.classify(k, r) is None]
    assert missing == []


def test_dry_run_reports_every_problem_and_writes_nothing(tmp_path):
    w = T.World(tmp_path)
    T.put(w.root / "stray-one.unknown-kind", "x")
    T.put(w.ev / "x.grades" / "seq-0001" / "unknown.bin", "x")
    T.put(w.run / "grading-private" / "keep" / "seq-1" / "mystery.bin", "x")
    with pytest.raises(H.HarvestError) as exc:
        w.harvest(dry_run=True)
    text = "\n".join(exc.value.problems)
    for name in ("stray-one.unknown-kind", "unknown.bin", "mystery.bin"):
        assert name in text
    T.nothing_published(w)
    assert not (w.wd / "p426" / "review").exists()


def test_dry_run_clean_tree_returns_and_writes_nothing(tmp_path):
    w = T.World(tmp_path)
    w.harvest(dry_run=True)
    T.nothing_published(w)
    assert not (w.wd / "p426" / "review").exists()


def test_dry_run_collects_scrub_and_secret_problems_with_inventory_ones(tmp_path):
    w = T.World(tmp_path)
    T.put(w.root / "stray.unknown-kind", "x")
    T.put(w.root / "extra.log", "token " + T.FAKE_HF + "\n")
    with pytest.raises(H.HarvestError) as exc:
        w.harvest(dry_run=True)
    text = "\n".join(exc.value.problems)
    assert "stray.unknown-kind" in text and "extra.log" in text


def test_cli_dry_run_exit_codes(tmp_path, capsys):
    w = T.World(tmp_path)
    env = dict(STACK_WORKDIR=str(w.wd))
    argv = ["wave2", "--leg-root", str(w.root), "--main-root", str(w.main), "--evidence-stage", str(w.stage), "--dry-run"]
    assert H.main(argv, environ=env, home=tmp_path / "home") == 0
    T.nothing_published(w)
    T.put(w.root / "stray-a.unknown-kind", "x")
    T.put(w.root / "stray-b.unknown-kind", "x")
    assert H.main(argv, environ=env, home=tmp_path / "home") == 4
    err = capsys.readouterr().err
    assert "stray-a.unknown-kind" in err and "stray-b.unknown-kind" in err
    T.nothing_published(w)
