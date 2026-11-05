"""`p475_kv matrix` (contract "Output", R16, R19, R20): generated from harvested dossiers only; canonical only when every arm has two
speed-valid legs with valid rungs; otherwise `.PARTIAL.md` and a nonzero exit; the deciding block in its own column."""
import json
import re
import shutil
from types import SimpleNamespace

import pytest

from . import helpers as H
from .fakes import ARMS, FakeOps, PICK, World

LABEL = "one pick (partial matrix, P475 v4)"
DESCRIPTIVE = "descriptive (two order-balanced speed-valid legs per arm, no interval claimed)"


def build(tmp_path_factory, label, setup=None, **run_kw):
    tmp = tmp_path_factory.mktemp(label)
    with pytest.MonkeyPatch.context() as mp:
        w = H.world(tmp, mp)
        H.ready(w)
        if setup:
            setup(w)
        rc = H.run_all(w, **run_kw)
        return SimpleNamespace(wd=w.wd, main=w.main, t=w.t, rc=rc)


@pytest.fixture(scope="module")
def finished(tmp_path_factory):
    return build(tmp_path_factory, "clean")


@pytest.fixture(scope="module")
def deciding(tmp_path_factory):
    def setup(w):
        w.metric_override = {("AF8", 1): {"dts": 39.5}, ("AF8", 2): {"dts": 42.3}, ("AF8", 3): {"dts": 29.6}}
    return build(tmp_path_factory, "deciding", setup)


@pytest.fixture
def cw(finished, tmp_path, monkeypatch):
    """A fresh world over a COPY of the finished run."""
    return H.clone(finished, tmp_path, monkeypatch)


def regen(w):
    return H.matrix_rc(w)


def text(w, partial=False):
    return H.matrix_path(w, partial).read_text()


# ------------------------------------------------------------------------------------------- the finished table
def test_the_clean_run_finished_and_wrote_the_canonical_table(finished):
    # class: exercises new behaviour
    assert finished.rc == 0
    assert (finished.main / "benchmark/results/p475" / f"MATRIX.{PICK}.md").is_file()


def test_the_table_is_labelled_one_pick_partial_and_descriptive(finished):
    # class: exercises new behaviour
    t = (finished.main / "benchmark/results/p475" / f"MATRIX.{PICK}.md").read_text()
    assert LABEL in t and DESCRIPTIVE in t.lower()


def test_every_arm_appears(finished):
    # class: exercises new behaviour
    t = (finished.main / "benchmark/results/p475" / f"MATRIX.{PICK}.md").read_text()
    for a in ARMS:
        assert a in t


def test_block_values_and_the_two_block_mean_are_in_the_table(finished):
    # class: exercises new behaviour. TQ4 at the 260096 rung: decode 34.0 / 36.0 (mean 35.0), prefill 220.0 / 230.0 (mean 225.0)
    t = (finished.main / "benchmark/results/p475" / f"MATRIX.{PICK}.md").read_text()
    for v in ("34.0", "36.0", "35.0", "220.0", "230.0", "225.0"):
        assert v in t, v


def test_the_table_names_the_four_metrics(finished):
    # class: exercises new behaviour (peak memory, prefill tok/s, decode tok/s, MTP acceptance)
    t = (finished.main / "benchmark/results/p475" / f"MATRIX.{PICK}.md").read_text().lower()
    assert "peak" in t and "prefill" in t and "decode" in t and "accept" in t


def test_the_table_shows_the_paired_ratios_against_n16(finished):
    # class: exercises new behaviour (AF8 decode 38.0 / 40.0 = 0.950 in block 1 and 40.0 / 42.0 = 0.952 in block 2; TQ4-OFF 20.0 / 40.0 =
    # 0.500 and 22.0 / 42.0 = 0.524 — exact values the fake's numbers imply, shown to three decimals)
    t = (finished.main / "benchmark/results/p475" / f"MATRIX.{PICK}.md").read_text()
    for v in ("0.950", "0.952", "0.500", "0.524"):
        assert v in t, v


# ------------------------------------------------------------------------------------------- generated from dossiers only
def test_the_table_regenerates_from_the_dossiers_alone(cw):
    # class: exercises new behaviour (matrix: "regenerate the table from harvested dossiers only")
    H.matrix_path(cw).unlink()
    shutil.rmtree(cw.wd / "worktrees")
    (cw.wd / "p475" / "state.json").unlink(missing_ok=True)
    shutil.rmtree(cw.wd / "p475" / "evidence-stage", ignore_errors=True)
    assert regen(cw) == 0
    t = text(cw)
    assert LABEL in t and "225.0" in t


def test_regeneration_changes_no_number(cw):
    # class: exercises new behaviour
    before = re.findall(r"\d+\.\d+", text(cw))
    H.matrix_path(cw).unlink()
    assert regen(cw) == 0
    assert re.findall(r"\d+\.\d+", text(cw)) == before


# ------------------------------------------------------------------------------------------- R20: complete or partial
def partial_expected(w):
    rc = regen(w)
    assert rc != 0
    assert H.matrix_path(w, partial=True).is_file()
    assert not H.matrix_path(w).exists(), "a canonical table is written only when complete"
    return text(w, partial=True)


def test_a_missing_leg_makes_the_table_partial_and_nonzero(cw):
    # class: exercises new behaviour (R20)
    shutil.rmtree(H.dossier(cw, "u4-tq8-b2.a1"))
    H.matrix_path(cw).unlink()
    assert "TQ8" in partial_expected(cw)


def test_an_arm_with_one_leg_only_is_partial(cw):
    # class: exercises new behaviour (every arm needs TWO speed-valid legs)
    for leg in ("u4-af4-b1.a1", "u4-af4-b2.a1"):
        shutil.rmtree(H.dossier(cw, leg))
    H.matrix_path(cw).unlink()
    partial_expected(cw)


# ------------------------------------------------------------------------------------------- R19: only finalized, validated dossiers
def ladder_files(d):
    return [p for p in d.rglob("*") if p.is_file() and "ladder" in p.name and p.suffix == ".jsonl"]


def test_a_dossier_with_two_ladder_files_is_not_trusted(cw):
    # class: reproduces a failure the contract fixes (R19: exactly one ladder file per dossier)
    d = H.dossier(cw, "u4-tq4-b1.a1")
    (src,) = ladder_files(d)
    shutil.copy(src, src.with_name(src.name.replace("ladder.", "ladder.copy.")))
    H.matrix_path(cw).unlink()
    partial_expected(cw)


def test_a_dossier_with_no_ladder_file_is_not_trusted(cw):
    # class: exercises new behaviour (R19)
    (src,) = ladder_files(H.dossier(cw, "u4-tq4-b1.a1"))
    src.unlink()
    H.resign(H.dossier(cw, "u4-tq4-b1.a1"))                  # only the semantic rule (one ladder file) can refuse it
    H.matrix_path(cw).unlink()
    partial_expected(cw)


def test_an_unfinalized_stage_directory_is_not_a_dossier(cw):
    # class: reproduces a failure the contract fixes (R18 / R19: metrics from finalized dossiers only)
    d = H.dossier(cw, "u4-tq4-b1.a1")
    d.rename(d.with_name(d.name + ".stage"))
    H.matrix_path(cw).unlink()
    partial_expected(cw)


def test_a_dossier_with_a_bad_rung_is_not_counted(cw):
    # class: exercises new behaviour (R19: validated: every rung is re-judged by the strict rule)
    (src,) = ladder_files(H.dossier(cw, "u4-tq4-b1.a1"))
    rows = [json.loads(x) for x in src.read_text().splitlines()]
    rows[1]["finish_reason"] = "stop"
    src.write_text("".join(json.dumps(r) + "\n" for r in rows))
    H.resign(H.dossier(cw, "u4-tq4-b1.a1"))                  # the integrity hash is consistent: only the strict re-judging refuses
    H.matrix_path(cw).unlink()
    partial_expected(cw)


def _edit_receipt(d, **kv):
    for p in d.rglob("*.json"):
        doc = json.loads(p.read_text())
        if isinstance(doc, dict) and "verdict" in doc and "speed_valid" in doc:
            doc.update(kv)
            p.write_text(json.dumps(doc))
            H.resign(d)                                      # the integrity hash is consistent: only the receipt's content refuses
            return
    raise AssertionError("no receipt in the dossier")


@pytest.mark.parametrize("kv", [dict(speed_valid=False), dict(verdict="INVALID"), dict(verdict="NOT_STARTED")])
def test_a_dossier_whose_receipt_is_not_a_speed_valid_valid_leg_is_not_counted(cw, kv):
    # class: exercises new behaviour (R19)
    _edit_receipt(H.dossier(cw, "u4-tq4-b1.a1"), **kv)
    H.matrix_path(cw).unlink()
    partial_expected(cw)


def test_metrics_come_from_the_dossier_not_from_the_arm_worktree(cw):
    # class: reproduces a failure the contract fixes (R19: a live worktree's file may differ from what was harvested)
    for p in (cw.wd / "worktrees").rglob("capacity_ladder.*.jsonl"):
        p.write_text("")
    H.matrix_path(cw).unlink()
    assert regen(cw) == 0
    assert "225.0" in text(cw)


# ------------------------------------------------------------------------------------------- R16: the deciding column
def dtext(deciding):
    return (deciding.main / "benchmark/results/p475" / f"MATRIX.{PICK}.md").read_text()


def test_a_deciding_run_finished(deciding):
    # class: exercises new behaviour
    assert deciding.rc == 0
    assert any((deciding.main / "benchmark/results/p475").glob("u4-*-b3.a1"))


def test_the_deciding_block_has_its_own_column(deciding):
    # class: exercises new behaviour (R16)
    t = dtext(deciding)
    assert "deciding" in t.lower() and "29.6" in t


def test_the_two_block_mean_excludes_the_deciding_block(deciding):
    # class: reproduces a failure the contract fixes (R16: AF8 decode (39.5 + 42.3) / 2 = 40.9; the three-block mean 37.13 must not appear)
    t = dtext(deciding)
    assert "40.9" in t
    assert "37.13" not in t


def test_the_instability_flag_is_reported(deciding):
    # class: exercises new behaviour (R16 / "the instability flags": the candidate prints REVERSAL / SPREAD per arm, rung and metric)
    assert re.search(r"REVERSAL|SPREAD", dtext(deciding))


def test_a_stable_run_prints_no_instability_flag(finished):
    # class: exercises new behaviour
    t = (finished.main / "benchmark/results/p475" / f"MATRIX.{PICK}.md").read_text()
    assert not re.search(r"REVERSAL|SPREAD", t)


def test_the_paired_block_ratios_are_those_of_blocks_one_and_two(deciding):
    # class: exercises new behaviour (R16: AF8 decode 39.5 / 40 = 0.9875 -> 0.988 and 42.3 / 42 = 1.00714 -> 1.007 side by side)
    t = dtext(deciding)
    assert "0.988" in t and "1.007" in t
