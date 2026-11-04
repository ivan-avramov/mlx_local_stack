"""Fix round 2 (operator-approved, C283): one `reproduces-failure` test per verify finding, plus a strengthened fix-10 variant.

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.

* v-P1  `a7-seal` seals only the Claude judge (client `claude-code:blind-judge`) and normalises `client_version`.
* v-P2  A1 eligibility is LENIENT correctness (a pair correct in both arms but not converged is eligible).
* v-P3  A4 eligibility = the strict-draw predicate (`score == 1.0`, `budget_hit` false, `finish_reason` stop).
* v-P4  `a7_select(results_root, b8)` has exactly the contract signature.
Verdicts are produced by the code under test (see sigview.write_verdicts); nothing here hand-writes provenance except the one
pre-sealed forged verdict, which is the case under test.
"""
from __future__ import annotations

import inspect
import json

import pytest

from bench.tests.p613s3 import s3world as S
from bench.tests.p613s3 import sigview as V

A1_ID = "test/algebra/1.json"
A4_SEED = 128000000
PLAN = {**V.PLAN_S1, **V.PLAN_S2_OFF}


@pytest.fixture(scope="module")
def panel():
    import importlib
    return importlib.import_module("bench.p426_panel")


@pytest.fixture(scope="module")
def case(tmp_path_factory):
    return S.A7Case(tmp_path_factory.mktemp("fr2case"), with_rejected=False)


@pytest.fixture(scope="module")
def w1case(tmp_path_factory):
    """A case whose Wave 1 has (a) one A1 key correct in BOTH arms but NOT converged (budget hit), (b) one A4 draw with
    `budget_hit` true and score 1.0 in both arms (identical outputs in both, so B8 sees identical pairs)."""
    from _pytest.monkeypatch import MonkeyPatch

    from bench.tests.p613s2 import wave1world as WW
    rows = {("math500", arm, "b1"): {A1_ID: dict(WW.NONCONV)} for arm in ("off", "on")}
    rows.update({("reasoning", arm, "b1"): {A4_SEED: {"budget_hit": True}} for arm in ("off", "on")})
    orig = WW.Wave1World.__init__

    def init(self, base, mp, **kw):
        kw.setdefault("rows", rows)
        orig(self, base, mp, **kw)
    with MonkeyPatch.context() as mp:
        mp.setattr(WW.Wave1World, "__init__", init)
        return S.A7Case(tmp_path_factory.mktemp("fr2w1"), with_rejected=False)


def one_packet(out, judge):
    row = next(r for r in S.manifest_of(out) if r["judge"] == judge)
    packet = V.packet_of(out, row)
    return row, packet, packet.with_name(row["pkt"] + ".verdict.json")


# ------------------------------------------------------------------------------------------------------------- v-P1
# class: reproduces-failure (`a7-seal` with the Cursor judge's label refuses: a bare verdict is never sealed under another family)
def test_vp1_seal_refuses_the_cursor_judge_label(case, tmp_path):
    out = tmp_path / "panel"
    assert case.export(out).returncode == 0
    row, packet, verdict = one_packet(out, V.CUR)
    verdict.write_text(json.dumps({"choice": "A", "rationale": "forged second-family verdict"}) + "\n")
    proc = S.run_cli("bench.p426_panel", ["a7-seal", "--out", out, "--judge", V.CUR, "--client-version", "9.9.9"], home=tmp_path)
    S.refused_cli(proc)
    assert "packet_sha" not in json.loads(verdict.read_text()), "the bare Cursor verdict was sealed"


# class: reproduces-failure (a pre-sealed Claude verdict with another client version is normalised to --client-version, or refused)
def test_vp1_pre_sealed_verdict_with_another_client_version(case, panel, tmp_path):
    out = tmp_path / "panel"
    assert case.export(out).returncode == 0
    row, packet, verdict = one_packet(out, V.CLA)
    fsha = S.sha_file(out / "FROZEN.json")
    j = S.CLAUDE_JUDGE
    verdict.write_text(json.dumps(dict(choice="A", rationale="r", judge=j["label"], family=j["family"], client=j["client"],
                                       model=j["model"], client_version="forged-9", packet_sha=S.sha_file(packet),
                                       attachment_sha=None, prompt_sha=panel.rubric_sha("code"), frozen_sha256=fsha)) + "\n")
    proc = S.run_cli("bench.p426_panel", ["a7-seal", "--out", out, "--judge", V.CLA, "--client-version", "2.3.4"], home=tmp_path)
    if proc.returncode != 0:
        S.refused_cli(proc)
        return
    marker = packet.with_name(row["pkt"] + ".failed.txt")
    if not marker.exists():
        assert json.loads(verdict.read_text())["client_version"] == "2.3.4", "a forged client version survived sealing"


# ------------------------------------------------------------------------------------------------------------- v-P2
# class: reproduces-failure (A1 eligibility is lenient: correct in both arms but not converged -> still panel-eligible)
def test_vp2_a1_pair_correct_but_not_converged_is_eligible(w1case, tmp_path):
    out = tmp_path / "panel"
    proc = w1case.export(out)
    assert proc.returncode == 0, proc.stderr[-400:]
    _, bad = w1case.a1_eligible()                         # math500 keys wrong in an arm (lenient correctness, synthetic rows)
    a1 = json.loads((out / "FROZEN.json").read_text())["wave1"]["per_axis"]["A1"]
    assert A1_ID not in [k[1] for k in a1["not_both_correct_keys"]], "the non-converged but correct pair was excluded"
    assert a1["not_both_correct"] == bad and a1["eligible"] == a1["keys"] - bad, (a1["eligible"], a1["keys"], bad)


# ------------------------------------------------------------------------------------------------------------- v-P3
# class: reproduces-failure (A4: a draw with budget_hit true is not a strict draw -> not eligible, counted not both correct)
def test_vp3_a4_budget_hit_draw_is_not_eligible(w1case, tmp_path):
    out = tmp_path / "panel"
    assert w1case.export(out).returncode == 0
    a4 = json.loads((out / "FROZEN.json").read_text())["wave1"]["per_axis"]["A4"]
    assert a4["keys"] == 4
    assert a4["eligible"] == 3 and a4["not_both_correct"] == 1, a4
    assert [k[1] for k in a4["not_both_correct_keys"]] == [A4_SEED]


# ------------------------------------------------------------------------------------------------------------- v-P4
# class: reproduces-failure (`a7_select` has exactly the contract signature, as `a7_packet` does)
def test_vp4_a7_select_signature_is_exact(panel):
    assert list(inspect.signature(panel.a7_select).parameters) == ["results_root", "b8"]


# ----------------------------------------------------------------------------------------------------------- fix 10 (strengthened)
# class: invariant (the per-item cap, without the duplicated-manifest refusal: the ingest hands the sheet a duplicated verdict row)
def test_fix10_cap_with_a_duplicated_ingest_row(case, panel, tmp_path, monkeypatch):
    from bench import generate
    from bench import p426_signals as SIG

    out = tmp_path / "panel"
    assert case.export(out).returncode == 0
    V.write_verdicts(out, PLAN, panel)                                          # a COMPLETE panel: nothing is missing
    real = panel.a7_ingest

    def duplicated(o):
        frozen, rows, report = real(o)
        first = next(r for r in rows if r["item_id"].startswith("s1/"))
        return frozen, rows + [dict(first)], report
    monkeypatch.setattr(panel, "a7_ingest", duplicated)
    monkeypatch.setattr(generate, "RESULTS", case.rows_root)
    sig = SIG.compute_all(case.results_root, case.rows_root, case.b8, b8_sha256=S.sha_file(case.b8_path), panel=out)
    members = sig["subjective"]["members"]
    for name, m in members.items():
        assert m["missing_verdicts"] >= 0, f"{name}: negative missing_verdicts {m['missing_verdicts']}"
    s1 = members["A7-s1"]
    assert s1["missing_verdicts"] == 0 and s1["duplicate_verdicts"] == 1
    assert members["A7-s2"]["missing_verdicts"] == 0 and members["A7-s2"]["duplicate_verdicts"] == 0
