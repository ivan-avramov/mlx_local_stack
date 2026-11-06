"""Delivery 4 (operator C294, second fix round): one failing-case test per adopted verify finding vP1, vP3, vP4. Each is red on
`candidate-fix.diff` and green on `candidate-fix2.diff` (the header says so). vP2 (`RealOps.spawn` cleanup) is not reachable through the
Ops seam: checked by inspection, see the report."""
import json
import re
import shutil
from types import SimpleNamespace

import pytest

from . import helpers as H
from .fakes import FakeOps, PICK, strict_row

SMOKE = "u4-n16-smoke.a1"
INVENTORY = ("capacity_ladder.p475-{leg}.jsonl", "capacity_ladder.p475-{leg}.manifest.json", "watch.jsonl", "kv_line.json",
             "worker_argv.json")


@pytest.fixture
def w(tmp_path, monkeypatch):
    w = H.world(tmp_path, monkeypatch)
    H.ready(w)
    return w


def matrix_cli(w):
    """`python -m bench.p475_kv matrix` through the candidate's own CLI (it reads the saved block plan)."""
    argv = ["--workdir", str(w.wd), "--repo", str(w.main), "--base", w.base, "matrix"]
    return H.K().main(argv, ops=FakeOps(w))


# ------------------------------------------------------------------------------------------- vP1: the VALID inventory at harvest
def _failed_n16_smoke_harvest(w):
    """An N16 smoke leg whose harvest was refused (a PII row): receipt VALID + speed-valid, no dossier; then its rows repaired."""
    w.row_mutate = lambda r, i, a, n: dict(r, note="/Users/jdoe/project/x.py") if (i == 0 and a == "N16") else r   # allow-pii-pattern
    try:
        H.run_leg(w, "N16", smoke=True)
    except Exception:           # noqa: BLE001
        pass
    assert not H.dossier(w, SMOKE).exists()
    out = w.wd / "p475/legs" / SMOKE / "capacity" / f"capacity_ladder.p475-{SMOKE}.jsonl"   # C297: the leg dir, not the worktree
    out.write_text(json.dumps(strict_row("N16", 8192, prefix=f"p475-{SMOKE}")) + "\n")
    w.row_mutate = None


SOURCES = {
    "watch_journal": lambda w: (w.wd / "p475/legs" / SMOKE / "watch.jsonl"),
    "capacity_manifest": lambda w: (w.wd / "p475/legs" / SMOKE / "capacity" / f"capacity_ladder.p475-{SMOKE}.manifest.json"),  # C297
}


@pytest.mark.parametrize("which", list(SOURCES))
def test_a_replayed_valid_leg_whose_source_file_vanished_is_not_published(w, which):
    # class: reproduces a failure the contract fixes (vP1; run on candidate-fix.diff: red -- the replay published a usable dossier
    # without the watcher journal / the capacity manifest)
    _failed_n16_smoke_harvest(w)
    SOURCES[which](w).unlink()
    before = (w.wd / "p475" / "LAST_LEG_END").read_text()
    assert H.run_all(w, smoke=True) != 0
    assert not H.dossier(w, SMOKE).exists()
    assert not (H.dossier(w, SMOKE).parent / f"{SMOKE}.stage").exists()
    assert (w.wd / "p475" / "LAST_LEG_END").read_text() == before


def test_a_forged_no_watcher_report_on_a_speed_valid_receipt_is_not_published(w):
    # class: reproduces a failure the contract fixes (vP1: the journal may be absent only when the receipt records "no watcher report"
    # AND the leg is not speed-valid; red on candidate-fix.diff)
    _failed_n16_smoke_harvest(w)
    p = H.receipt_path(w, SMOKE)
    doc = json.loads(p.read_text())
    assert doc["speed_valid"] is True
    doc["speed_problems"] = ["no watcher report"]
    p.write_text(json.dumps(doc))
    SOURCES["watch_journal"](w).unlink()
    assert H.run_all(w, smoke=True) != 0
    assert not H.dossier(w, SMOKE).exists()


def test_a_leg_whose_watcher_wrote_nothing_is_harvested_and_replaced(w):
    # class: preserves an invariant (R11: SPEED_INVALID, never INVALID; the dossier exists as evidence, the leg is replaceable)
    w.watch_mode = lambda arm, n: "missing" if (arm == "AF4" and n == 4) else "ok"
    assert H.run_all(w) == 0
    rcs = H.receipts(w)
    assert rcs["u4-af4-b1.a1"]["verdict"] == "VALID" and rcs["u4-af4-b1.a1"]["speed_valid"] is False
    assert any("no watcher report" in s for s in rcs["u4-af4-b1.a1"]["speed_problems"])
    assert H.dossier(w, "u4-af4-b1.a1").is_dir()
    assert rcs["u4-af4-b1.a2"]["speed_valid"] is True
    assert H.matrix_path(w).is_file()


def test_the_dossier_of_a_leg_without_a_watcher_report_is_never_used(w):
    # class: preserves an invariant (vP1 reading: such a dossier is never usable; the replacement carries the table)
    w.watch_mode = lambda arm, n: "missing" if (arm == "AF4" and n == 4) else "ok"
    H.run_all(w)
    assert "u4-af4-b1.a1" in H.matrix_path(w).read_text()           # listed as replaced
    t = H.matrix_path(w).read_text()
    assert re.search(r"used[^\n]*u4-af4-b1\.a2", t) and not re.search(r"used[^\n]*u4-af4-b1\.a1", t)


# ------------------------------------------------------------------------------------------- vP1: the VALID inventory at load
@pytest.fixture(scope="module")
def finished(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("v14clean")
    with pytest.MonkeyPatch.context() as mp:
        w = H.world(tmp, mp)
        H.ready(w)
        rc = H.run_all(w, max_deciding=0)
        return SimpleNamespace(wd=w.wd, main=w.main, t=w.t, rc=rc)


@pytest.fixture(scope="module")
def deciding(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("v14deciding")
    with pytest.MonkeyPatch.context() as mp:
        w = H.world(tmp, mp)
        H.ready(w)
        w.metric_override = {("AF8", 1): {"dts": 39.5}, ("AF8", 2): {"dts": 42.3}, ("AF8", 3): {"dts": 29.6}}
        rc = H.run_all(w)
        return SimpleNamespace(wd=w.wd, main=w.main, t=w.t, rc=rc)


@pytest.fixture
def cw(finished, tmp_path, monkeypatch):
    return H.clone(finished, tmp_path, monkeypatch)


@pytest.fixture
def dw(deciding, tmp_path, monkeypatch):
    return H.clone(deciding, tmp_path, monkeypatch)


def test_the_fixtures_finished_complete(finished, deciding):
    # class: preserves an invariant (stable run with a zero deciding cap; instability run settled by its deciding block)
    assert finished.rc == 0 and deciding.rc == 0


LEG = "u4-tq4-b1.a1"


@pytest.mark.parametrize("name", INVENTORY)
def test_a_valid_dossier_missing_an_inventory_file_is_not_counted(cw, name):
    # class: reproduces a failure the contract fixes (vP1; red on candidate-fix.diff: only the receipt and one ladder were required)
    d = H.dossier(cw, LEG)
    (d / name.format(leg=LEG)).unlink()
    H.resign(d)                                  # the manifest no longer lists it either: only the inventory rule can refuse
    H.matrix_path(cw).unlink()
    assert H.matrix_rc(cw) != 0
    assert H.matrix_path(cw, partial=True).is_file() and not H.matrix_path(cw).exists()


@pytest.mark.parametrize("name", INVENTORY)
def test_a_valid_dossier_whose_manifest_omits_an_inventory_file_is_not_counted(cw, name):
    # class: reproduces a failure the contract fixes (vP1: every expected file represented in SCRUB_MANIFEST.json; red on candidate-fix.diff)
    d = H.dossier(cw, LEG)
    man = json.loads((d / "SCRUB_MANIFEST.json").read_text())
    del man["files"][name.format(leg=LEG)]
    (d / "SCRUB_MANIFEST.json").write_text(json.dumps(man))
    H.matrix_path(cw).unlink()
    assert H.matrix_rc(cw) != 0


def test_a_forged_no_watcher_report_does_not_excuse_a_speed_valid_dossier(cw):
    # class: reproduces a failure the contract fixes (vP1)
    d = H.dossier(cw, LEG)
    doc = json.loads((d / "receipt.json").read_text())
    doc["speed_problems"] = ["no watcher report"]
    (d / "receipt.json").write_text(json.dumps(doc))
    (d / "watch.jsonl").unlink()
    H.resign(d)
    H.matrix_path(cw).unlink()
    assert H.matrix_rc(cw) != 0


# ------------------------------------------------------------------------------------------- vP3: only recorded blocks
def slot_dossier(w, src_leg, new_leg):
    """A self-consistent, re-signed copy of `src_leg`'s dossier under another leg name (a stale block's dossier)."""
    src, dst = H.dossier(w, src_leg), H.dossier(w, new_leg)
    shutil.copytree(src, dst)
    for p in list(dst.iterdir()):
        if p.name == "SCRUB_MANIFEST.json":
            continue
        if p.suffix in (".jsonl", ".json"):
            p.write_text(p.read_text().replace(src_leg, new_leg))
        if src_leg in p.name:
            p.rename(dst / p.name.replace(src_leg, new_leg))
    man = json.loads((dst / "SCRUB_MANIFEST.json").read_text())
    man["files"] = {k.replace(src_leg, new_leg): v for k, v in man["files"].items()}
    (dst / "SCRUB_MANIFEST.json").write_text(json.dumps(man))
    m = re.match(r"u4-(.+?)-b(\d+)\.a(\d+)$", new_leg)
    doc = json.loads((dst / "receipt.json").read_text())
    doc.update(leg=new_leg, block=int(m.group(2)), attempt=int(m.group(3)))
    (dst / "receipt.json").write_text(json.dumps(doc))
    H.resign(dst)


def test_a_stale_block_four_dossier_in_a_two_block_run_is_refused(cw):
    # class: reproduces a failure the contract fixes (vP3; red on candidate-fix.diff: every usable block > blocks was a deciding block)
    slot_dossier(cw, LEG, "u4-tq4-b4.a1")
    H.matrix_path(cw).unlink()
    assert H.matrix_rc(cw) != 0
    assert H.matrix_path(cw, partial=True).is_file() and not H.matrix_path(cw).exists()


def test_a_block_three_dossier_when_no_deciding_block_was_started_is_refused(cw):
    # class: reproduces a failure the contract fixes (vP3: the deciding data only from the recorded deciding-block identity)
    slot_dossier(cw, LEG, "u4-tq4-b3.a1")
    H.matrix_path(cw).unlink()
    assert H.matrix_rc(cw) != 0


def test_a_stale_block_four_beside_the_recorded_deciding_block_is_refused_and_block_three_stays(dw):
    # class: reproduces a failure the contract fixes (vP3; red on candidate-fix.diff: b4 was shown beside b3 and the run stayed complete)
    assert H.matrix_path(dw).is_file()
    slot_dossier(dw, "u4-tq4-b3.a1", "u4-tq4-b4.a1")
    assert H.matrix_rc(dw) != 0
    t = H.matrix_path(dw, partial=True).read_text()
    assert "29.6" in t, "the recorded deciding block b3 is still shown"
    assert not H.matrix_path(dw).exists()


def test_the_recorded_deciding_block_alone_is_accepted(dw):
    # class: preserves an invariant (regeneration of a settled deciding run stays complete)
    H.matrix_path(dw).unlink()
    assert H.matrix_rc(dw) == 0
    assert "29.6" in H.matrix_path(dw).read_text()


# ------------------------------------------------------------------------------------------- vP4: standalone matrix exit code
def test_standalone_matrix_exits_nonzero_on_an_unresolved_flag_but_still_writes_the_labelled_table(tmp_path, monkeypatch):
    # class: reproduces a failure the contract fixes (vP4; red on candidate-fix.diff: matrix returned 0 while `run` returned 1)
    w = H.world(tmp_path, monkeypatch)
    H.ready(w)
    w.metric_override = {("AF8", 1): {"dts": 39.9}, ("AF8", 2): {"dts": 42.1}}
    assert H.run_all(w, max_deciding=0) != 0
    assert matrix_cli(w) != 0
    assert H.matrix_path(w).is_file() and not H.matrix_path(w, partial=True).exists(), "canonical vs PARTIAL naming is unchanged"
    assert "UNRESOLVED" in H.matrix_path(w).read_text()


def test_standalone_matrix_exits_zero_for_a_settled_run(dw):
    # class: preserves an invariant
    assert matrix_cli(dw) == 0


def test_standalone_matrix_exits_zero_for_a_stable_run(cw):
    # class: preserves an invariant
    assert matrix_cli(cw) == 0
