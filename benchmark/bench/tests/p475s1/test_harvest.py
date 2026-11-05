"""Harvest (contract step 8, R18): staged, scrubbed, verified, renamed; evidence logs to the workdir stage; resume replays a harvest
for a receipt without its finalized dossier; the canonical receipt wins over `.refused-*` variants (R17)."""
import json
import shutil

import pytest

from . import helpers as H
from .fakes import PICK, leg_name, strict_row

LEG = leg_name("AF8", 1)
SMOKE = "u4-n16-smoke.a1"


@pytest.fixture
def w(tmp_path, monkeypatch):
    w = H.world(tmp_path, monkeypatch)
    H.ready(w)
    return w


def files(d):
    return sorted(p for p in d.rglob("*") if p.is_file())


def text_of(d):
    import gzip
    return "\n".join((gzip.decompress(p.read_bytes()).decode(errors="replace") if p.suffix == ".gz"
                      else p.read_text(errors="replace")) for p in files(d))


# ------------------------------------------------------------------------------------------- the finalized dossier
def test_the_dossier_exists_and_no_stage_remains(w):
    # class: exercises new behaviour
    H.run_leg(w, "AF8")
    d = H.dossier(w, LEG)
    assert d.is_dir()
    assert not (d.parent / f"{LEG}.stage").exists()


def test_the_dossier_holds_exactly_one_ladder_file(w):
    # class: exercises new behaviour (R19)
    H.run_leg(w, "AF8")
    ladders = [p for p in files(H.dossier(w, LEG)) if "ladder" in p.name and p.suffix == ".jsonl"]
    assert len(ladders) == 1
    rows = [json.loads(x) for x in ladders[0].read_text().splitlines()]
    assert [r["ctx"] for r in rows] == [8192, 131072, 196608, 260096]


def test_the_dossier_carries_receipt_manifest_ticks_kv_line_and_argv(w):
    # class: exercises new behaviour (step 8 list)
    H.run_leg(w, "AF8")
    d = H.dossier(w, LEG)
    t = text_of(d)
    assert '"verdict"' in t                                   # the receipt
    assert "capacity_ladder" in t or any("manifest" in p.name for p in files(d))
    assert any("manifest" in p.name for p in files(d))
    assert '"exit_state"' in t                                # the watch ticks
    assert "kv_quant_scheme" in t and "uniform" in t          # the KV line
    assert "--kv-bits" in t                                   # the worker argv


def test_dossier_files_are_scrubbed_of_workdir_and_repo_paths(w):
    # class: exercises new behaviour (public repo: no absolute paths)
    H.run_leg(w, "AF8")
    t = text_of(H.dossier(w, LEG))
    assert str(w.wd) not in t and str(w.main) not in t
    assert "$STACK_WORKDIR" in t                              # the worker argv's worktree path, scrubbed to the token


def test_evidence_logs_are_staged_in_the_workdir_scrubbed(w):
    # class: exercises new behaviour
    H.run_leg(w, "AF8")
    d = w.wd / "p475" / "evidence-stage" / LEG
    fs = files(d)
    assert fs, "scrubbed worker / router logs go to the evidence stage"
    t = text_of(d)
    assert "loading model" in t and "router starting" in t
    assert str(w.wd) not in t


def test_an_invalid_leg_is_harvested_too(w):
    # class: exercises new behaviour (step 8: VALID or INVALID)
    w.row_mutate = lambda r, i, a, n: dict(r, finish_reason="stop") if i == 0 else r
    assert H.run_leg(w, "AF8")["verdict"] == "INVALID"
    assert H.dossier(w, LEG).is_dir() and files(w.wd / "p475" / "evidence-stage" / LEG)


# ------------------------------------------------------------------------------------------- R18: nothing half-final
def pii_row(r, i, a, n):
    # scoped to the leg under test (the N16 smoke leg): under v1.2 a smoke run continues with TQ4, whose rows must stay clean
    return dict(r, note="/Users/jdoe/project/x.py") if (i == 0 and a == "N16") else r        # allow-pii-pattern


def run_failing_harvest(w):
    w.row_mutate = pii_row
    try:
        H.run_leg(w, "N16", smoke=True)
    except Exception:           # noqa: BLE001 — a refused harvest may raise or return; either way nothing is final
        pass


def test_a_harvest_refused_by_the_pii_check_leaves_no_final_dossier(w):
    # class: exercises new behaviour (R18: staged, verified, THEN renamed)
    run_failing_harvest(w)
    assert not H.dossier(w, SMOKE).exists()


def test_a_refused_harvest_keeps_the_receipt_and_does_not_start_the_idle_clock(w):
    # class: exercises new behaviour (R8 + R18: the idle starts after a harvest COMPLETES)
    before = (w.wd / "p475" / "LAST_LEG_END").read_text()
    run_failing_harvest(w)
    assert H.receipt_path(w, SMOKE).exists()
    assert (w.wd / "p475" / "LAST_LEG_END").read_text() == before


def fix_source_rows(w):
    out = w.wt("N16") / "benchmark/results" / PICK / f"capacity_ladder.p475-{SMOKE}.jsonl"
    out.write_text(json.dumps(strict_row("N16", 8192, prefix=f"p475-{SMOKE}")) + "\n")


def test_resume_replays_the_harvest_of_a_receipt_without_a_dossier(w):
    # class: exercises new behaviour (R18: the receipt exists, the dossier does not)
    run_failing_harvest(w)
    fix_source_rows(w)
    n16_starts = [s.arm for s in w.stacks].count("N16")
    assert H.run_all(w, smoke=True) == 0               # v1.2: the replay finalizes the N16 smoke, then the TQ4 smoke runs
    assert [s.arm for s in w.stacks].count("N16") == n16_starts, "the N16 leg is not re-run: its receipt stands"
    assert H.dossier(w, SMOKE).is_dir() and not (H.dossier(w, SMOKE).parent / f"{SMOKE}.stage").exists()
    assert float((w.wd / "p475" / "LAST_LEG_END").read_text()) > w.epoch0 - 7200


def test_a_stale_stage_directory_from_a_crash_is_replaced_not_merged(w):
    # class: exercises new behaviour (R18)
    run_failing_harvest(w)
    stage = H.dossier(w, SMOKE).parent / f"{SMOKE}.stage"
    stage.mkdir(parents=True, exist_ok=True)
    (stage / "stale.txt").write_text("leftover")
    fix_source_rows(w)
    assert H.run_all(w, smoke=True) == 0
    assert not (H.dossier(w, SMOKE) / "stale.txt").exists()


# ------------------------------------------------------------------------------------------- resume with a finished leg
def test_a_finished_smoke_run_is_not_run_again(w):
    # class: exercises new behaviour (resume)
    assert H.run_all(w, smoke=True) == 0
    n = len(w.stacks)
    assert H.run_all(w, smoke=True) == 0
    assert len(w.stacks) == n


# ------------------------------------------------------------------------------------------- R17: canonical receipt wins
def test_a_refused_variant_beside_a_valid_canonical_receipt_changes_nothing(w):
    # class: exercises new behaviour (R17)
    assert H.run_all(w, smoke=True) == 0
    n = len(w.stacks)
    d = w.wd / "p475/legs" / SMOKE
    (d / "receipt.refused-1.json").write_text(json.dumps({"verdict": "INVALID", "problems": ["x"], "speed_valid": False}))
    assert H.run_all(w, smoke=True) == 0
    assert len(w.stacks) == n


def test_an_invalid_canonical_receipt_wins_over_a_valid_variant(w):
    # class: exercises new behaviour (R17: the canonical verdict decides, in either direction)
    w.row_mutate = lambda r, i, a, n: dict(r, finish_reason="stop")
    assert H.run_all(w, smoke=True) != 0
    n = len(w.stacks)
    d = w.wd / "p475/legs" / SMOKE
    assert json.loads((d / "receipt.json").read_text())["verdict"] == "INVALID"
    (d / "receipt.refused-1.json").write_text(json.dumps({"verdict": "VALID", "problems": [], "speed_valid": True}))
    w.row_mutate = None
    assert H.run_all(w, smoke=True) != 0
    assert len(w.stacks) == n
