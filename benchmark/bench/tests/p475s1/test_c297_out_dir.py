"""C297 (S18-P1 (c)): `run_capacity --out-dir`; the P475 legs write their capacity outputs under the leg dir, never into the arm
worktree, so R1 stays strict "clean" at entry and exit and an arm's later legs are not refused (P659)."""
import pytest

from . import helpers as H
from .fakes import PICK
from . import test_run_capacity_strict as S

pytestmark = pytest.mark.usefixtures("pin_mtp_scan")


@pytest.fixture
def w(tmp_path, monkeypatch):
    return H.world(tmp_path, monkeypatch)


def idle(w):
    w.t += H.K().IDLE_S + 60


# ------------------------------------------------------------------------------------------- run_capacity --out-dir
def test_out_dir_receives_the_three_outputs_and_the_default_dir_none(tmp_path, monkeypatch):
    default = S.setup(tmp_path, monkeypatch, S.Driver())
    target = tmp_path / "leg" / "capacity"
    assert S.go(["--p475-strict", "--out-dir", str(target)]) == 0
    names = sorted(p.name for p in target.iterdir())
    assert names == ["capacity_ladder.p475-t.jsonl", "capacity_ladder.p475-t.manifest.json", "capacity_retrieval.p475-t.json"]
    assert not default.exists() or list(default.iterdir()) == []


def test_out_dir_refuses_an_existing_output_like_the_default(tmp_path, monkeypatch, capsys):
    S.setup(tmp_path, monkeypatch, S.Driver())
    target = tmp_path / "leg" / "capacity"
    target.mkdir(parents=True)
    (target / "capacity_ladder.p475-t.jsonl").write_text("")
    with pytest.raises(SystemExit):
        S.go(["--p475-strict", "--out-dir", str(target)])
    assert "capacity output already exists" in capsys.readouterr().err


def test_without_out_dir_the_default_location_is_unchanged(tmp_path, monkeypatch):
    default = S.setup(tmp_path, monkeypatch, S.Driver())
    assert S.go(["--p475-strict"]) == 0
    assert (default / "capacity_ladder.p475-t.jsonl").exists()


# ------------------------------------------------------------------------------------------- the orchestrator
def test_the_leg_points_the_driver_at_the_leg_dir(w):
    ops = H.ready(w)
    leg = "u4-n16-b1.a1"
    r = H.run_leg(w, "N16", ops=ops)
    a = r["driver_argv"]
    want = w.wd / "p475" / "legs" / leg / "capacity"
    assert a[a.index("--out-dir") + 1] == str(want)
    assert r["paths"]["rows"] == str(want / f"capacity_ladder.p475-{leg}.jsonl")
    assert r["paths"]["manifest"] == str(want / f"capacity_ladder.p475-{leg}.manifest.json")


def test_a_leg_leaves_its_arm_worktree_clean_and_is_valid(w):
    ops = H.ready(w)
    r = H.run_leg(w, "N16", ops=ops)
    assert r["verdict"] == "VALID", r["problems"]
    assert w.untracked.get("N16") in (None, set())
    assert r["identity_exit"]["clean"] is True


def test_two_legs_on_one_arm_are_both_valid(w):
    ops = H.ready(w)
    first = H.run_leg(w, "N16", block=1, ops=ops)
    idle(w)
    second = H.run_leg(w, "N16", block=2, ops=ops)
    assert (first["verdict"], second["verdict"]) == ("VALID", "VALID"), (first["problems"], second["problems"])


def test_a_driver_that_writes_into_the_worktree_is_still_invalid(w):
    ops = H.ready(w)
    w.driver_ignores_out_dir = True
    r = H.run_leg(w, "AF8", ops=ops)
    assert r["verdict"] == "INVALID"
    assert any("worktree not clean" in p for p in r["problems"])


def test_the_full_smoke_run_completes_with_clean_worktrees(w):
    ops = H.ready(w)
    assert H.run_all(w, ops=ops, smoke=True) == 0
    assert all(not v for v in w.untracked.values())


# ------------------------------------------------------------------------------------------- C298: archived dossiers
def test_dossiers_archived_under_results_archive_are_not_loaded(w):
    import shutil
    ops = H.ready(w)
    assert H.run_all(w, ops=ops, smoke=True) == 0
    live = w.main / "benchmark/results/p475"
    loaded, _ = H.K().load_dossiers(H.cfg(w))
    assert sorted(r["leg"] for r in loaded) == ["u4-n16-smoke.a1", "u4-tq4-smoke.a1"]
    arch = live / "archive" / ("e" * 12)
    arch.mkdir(parents=True)
    shutil.move(str(live / "u4-n16-smoke.a1"), str(arch / "u4-n16-smoke.a1"))
    loaded, problems = H.K().load_dossiers(H.cfg(w))
    assert [r["leg"] for r in loaded] == ["u4-tq4-smoke.a1"]
    assert not any("archive" in p for p in problems)
