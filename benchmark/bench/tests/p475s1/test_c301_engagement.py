"""C301 (S18-P10): the ON engagement record of every MTP-ON arm (`qualify --kv-arm --predictor on --engagement-only`, fork
P658 (a)); the leg pre-check needs it; S18-P3: a record taken on another base is neither final nor accepted; the fork's quiet-box
scan exempts this orchestrator as a launcher ancestor."""
import json
import sys
from pathlib import Path

import pytest

from . import helpers as H
from .fakes import ARMS, FakeOps

ON = ("N16", "AF8", "TQ8", "AF4", "TQ4")


@pytest.fixture
def w(tmp_path, monkeypatch):
    return H.world(tmp_path, monkeypatch)


def engage(w, arm, ops=None, **kw):
    return H.K().preflight(arm, ops or FakeOps(w), H.cfg(w), kind="engagement", **kw)


def off_and_engage_all(w):
    ops = FakeOps(w)
    assert H.prepare(w, ops) == []
    for a in ARMS:
        assert H.preflight_ok(w, a, ops=ops)
    return ops


# ------------------------------------------------------------------------------------------- the engagement check
def test_the_on_arms_are_the_five_mtp_on_arms():
    assert tuple(a for a in ARMS if H.K().predictor_of(a) == "on") == ON


@pytest.mark.parametrize("arm", ON)
def test_engagement_runs_qualify_predictor_on_engagement_only_and_records_under_engagement(w, arm):
    rec = engage(w, arm)
    assert rec["status"] == "PASS"
    (call,) = w.run_calls
    a = call.argv
    assert a[a.index("--predictor") + 1] == "on"
    assert "--engagement-only" in a and "--kv-arm" in a
    assert a[a.index("--entry") + 1] == H.K().PICK
    assert a[a.index("--out") + 1] == str(w.wd / "p475" / "engagement" / f"{arm}.a1")
    disk = json.loads((w.wd / "p475" / "engagement" / f"{arm}.json").read_text())
    assert disk["status"] == "PASS" and disk["base"] == w.base
    assert not (w.wd / "p475" / "preflight" / f"{arm}.json").exists()      # never the OFF record


def test_tq4_off_has_no_engagement_check(w):
    with pytest.raises(H.K().P475Error):
        engage(w, "TQ4-OFF")
    assert w.run_calls == []


@pytest.mark.parametrize("mode", ["certifies", "no_flag", "predictor_off", "refuse"])
def test_an_engagement_report_that_is_not_uncertified_engagement_evidence_does_not_pass(w, mode):
    w.engagement_plan["AF8"] = [mode] * 5
    rec = engage(w, "AF8")
    assert rec["status"] == "REFUSED"
    assert len(rec["attempts"]) == 3


def test_engagement_environmental_refusal_is_not_started(w):
    w.lease_refuse = True
    rec = engage(w, "TQ8")
    assert rec["status"] == "NOT_STARTED" and rec["attempts"] == []


def test_the_cli_runs_the_engagement_check(w, capsys):
    rc = H.K().main(["--workdir", str(w.wd), "--repo", str(w.main), "--base", w.base, "preflight", "--arm", "N16",
                     "--engagement"], ops=FakeOps(w))
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["status"] == "PASS" and out.get("kind") == "engagement"


# ------------------------------------------------------------------------------------------- the leg pre-check
def test_an_on_arm_leg_without_its_engagement_pass_is_not_started(w):
    off_and_engage_all(w)
    r = H.run_leg(w, "AF4")
    assert r["verdict"] == "NOT_STARTED"
    assert any("engagement" in p for p in r["problems"])
    assert w.spawns == []


def test_an_on_arm_leg_with_both_passes_runs(w):
    ops = H.ready(w)
    r = H.run_leg(w, "AF4", ops=ops)
    assert r["verdict"] == "VALID", r["problems"]
    assert r["engagement"]["status"] == "PASS"


def test_the_tq4_off_leg_needs_only_its_off_preflight(w):
    off_and_engage_all(w)
    r = H.run_leg(w, "TQ4-OFF")
    assert r["verdict"] == "VALID", r["problems"]


# ------------------------------------------------------------------------------------------- S18-P3: records bound to the base
def _rebase_record(w, rel, other):
    p = w.wd / "p475" / rel
    doc = json.loads(p.read_text())
    doc["base"] = other
    p.write_text(json.dumps(doc))


@pytest.mark.parametrize("rel", ["preflight/AF8.json", "engagement/AF8.json"])
def test_a_leg_refuses_a_record_taken_on_another_base(w, rel):
    ops = H.ready(w)
    _rebase_record(w, rel, "c" * 40)
    r = H.run_leg(w, "AF8", ops=ops)
    assert r["verdict"] == "NOT_STARTED"
    assert any("base" in p for p in r["problems"])


@pytest.mark.parametrize("kind,rel", [("off", "preflight/TQ8.json"), ("engagement", "engagement/TQ8.json")])
def test_a_final_record_of_another_base_is_not_final_and_is_kept(w, kind, rel):
    ops = H.ready(w)
    _rebase_record(w, rel, "c" * 40)
    before = (w.wd / "p475" / rel).read_text()
    w.run_calls.clear()
    rec = H.K().preflight("TQ8", ops, H.cfg(w), kind=kind)
    assert rec["status"] == "NOT_STARTED"
    assert "base" in rec["not_started"][-1]["reason"]
    assert w.run_calls == []                                   # no qualify on a stale record
    assert (w.wd / "p475" / rel).read_text() == before         # the old record is evidence, never overwritten


def test_run_stops_on_a_stale_record_without_refusing_the_arm(w):
    ops = H.ready(w)
    _rebase_record(w, "engagement/N16.json", "c" * 40)
    assert H.run_all(w, ops=ops, smoke=True) != 0
    st = json.loads((w.wd / "p475" / "state.json").read_text())
    assert st["refused_arms"] == []
    assert w.spawns == []


# ------------------------------------------------------------------------------------------- the run
def test_the_smoke_run_takes_the_engagement_checks_of_its_on_arms_then_runs_valid(w):
    ops = FakeOps(w)
    assert H.prepare(w, ops) == []
    assert H.run_all(w, ops=ops, smoke=True) == 0
    for arm in ("N16", "TQ4"):
        assert json.loads((w.wd / "p475" / "engagement" / f"{arm}.json").read_text())["status"] == "PASS"
    kinds = [("--engagement-only" in c.argv) for c in w.run_calls if "--stack-root" in c.argv]
    assert kinds == [False, True, False, True]                 # per arm: the OFF preflight, then its engagement check


def test_a_refused_engagement_refuses_the_arm(w):
    ops = FakeOps(w)
    assert H.prepare(w, ops) == []
    w.engagement_plan["N16"] = ["refuse"] * 5
    rc = H.run_all(w, ops=ops, smoke=True)
    assert rc != 0
    assert not any(s.argv for s in w.spawns if "u4-n16" in " ".join(s.argv))


# ------------------------------------------------------------------------------------------- the fork's quiet-box scan (P656 6)
def _fork_orchestrate():
    dev = Path(H.K().__file__).resolve().parents[2] / "src" / "mlx-vlm" / "dev"
    if not (dev / "p369_phase2" / "orchestrate.py").exists():
        pytest.skip("src/mlx-vlm is not checked out (submodule absent)")
    sys.path.insert(0, str(dev))
    try:
        from p369_phase2 import orchestrate
    except ImportError as exc:  # a heavy dependency the bench venv lacks
        pytest.skip(f"the fork's orchestrate does not import here: {exc}")
    finally:
        sys.path.remove(str(dev))
    return orchestrate


def test_the_gitlinked_fork_exempts_this_orchestrator_as_a_launcher_ancestor():
    orch = _fork_orchestrate()
    me = H.K().__name__                                         # the module the CLI launches qualify from
    assert me in orch.LAUNCHER_MODULES
    argv = [sys.executable, "-m", me, "preflight", "--arm", "N16"]
    assert orch.foreign_process_problems([(4242, argv)], 1, {4242}) == []       # an ancestor: exempt
    assert orch.foreign_process_problems([(4243, argv)], 1, {4242})              # not an ancestor: refused
