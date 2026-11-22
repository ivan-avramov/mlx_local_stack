"""S26 frozen tests, fix round 2 (spec erratum v1.1d; ledger `.fe-material-tw/change-ledger-r2.md`): the adopted defects of change
verify round 2, each as a reproducible failing case. All [FIX]: they fail on candidate 2 (traces in the delivery report).

(a) erratum 11: v8 accepts DECLINED only with `declined_evidence.row_sha256` 64-hex AND equal to the entry's `row_sha256`;
(b) erratum 12: tg2's campaign-core closure includes `bench/tg2_gradle_home.py`, tg1's does not;
(c) erratum 14: the guard's Stop lines are flat fail-closed statements (no "operator decides" wording)."""
from __future__ import annotations

import json
import shutil

import pytest

from bench.tests.s26_frozen import s26_support as X
from bench.tests.s26_frozen import test_s26_positives as P
from bench.tests.s26_frozen import test_s26_sequencer as Q

GRADLE_SRC = "benchmark/bench/tg2_gradle_home.py"
GOOD = "ab" * 32


# ---------------------------------------------------------------------------------------------------- (a) v8 row hash
@pytest.fixture
def declined(tmp_path, monkeypatch):
    world = X.HostWorld(tmp_path / "host")
    rc, doc, _ = P.run_pos(tmp_path, monkeypatch, world, verdicts={("rust", "loop"): "not_observed:kill",
                                                                   ("cpp", "alloc"): "not_observed:kill"})
    assert rc == 0 and X.inject_of(doc, "rust", "loop")["verdict"] == "DECLINED"
    return doc


def test_fix_v8_accepts_a_declined_entry_whose_evidence_names_the_entrys_own_row_hash(declined):
    """[FIX] control: the evidence's `row_sha256` is the entry's own, 64-hex -> accepted (and recorded by the real run)."""
    for lang, kind in (("rust", "loop"), ("cpp", "alloc")):
        e = X.inject_of(declined, lang, kind)
        assert e["declined_evidence"]["row_sha256"] == e["row_sha256"]
    assert P.v8_problems(declined) == []


@pytest.mark.parametrize("bad", [
    pytest.param("missing", id="evidence-row-sha-missing"),
    pytest.param(None, id="evidence-row-sha-null"),
    pytest.param(12345, id="evidence-row-sha-not-a-string"),
    pytest.param("abc", id="short"),
    pytest.param("ab" * 31 + "a", id="63-hex"),
    pytest.param("ab" * 33, id="66-hex"),
    pytest.param("AB" * 32, id="upper-case-hex"),
    pytest.param("zz" * 32, id="64-non-hex"),
    pytest.param(GOOD, id="valid-hex-but-another-rows"),
])
def test_fix_v8_refuses_a_declined_entry_with_a_missing_malformed_or_foreign_row_hash(declined, bad):
    """[FIX] erratum 11: a resealed record whose DECLINED evidence lacks a valid, matching `row_sha256` is refused (a decline is
    only trustworthy when bound to the row the probe recorded)."""
    def edit(body):
        ev = P.entry_of(body, "rust", "loop")["declined_evidence"]
        if bad == "missing":
            ev.pop("row_sha256")
        else:
            ev["row_sha256"] = bad
    assert P.v8_problems(P.reseal(declined, edit))


def test_fix_v8_refuses_when_the_entrys_own_row_hash_differs_from_the_evidences(declined):
    """[FIX] erratum 11, the other direction: the entry's `row_sha256` altered (or removed) while the evidence keeps the original."""
    for new in ("c" * 64, None, "not-a-hash"):
        def edit(body, new=new):
            P.entry_of(body, "cpp", "alloc")["row_sha256"] = new
        assert P.v8_problems(P.reseal(declined, edit)), new

    def drop(body):
        P.entry_of(body, "cpp", "alloc").pop("row_sha256")
    assert P.v8_problems(P.reseal(declined, drop))


def test_fix_v8_row_hash_rule_does_not_touch_pass_entries(declined):
    """[FIX] scope: a PASS entry is judged as before (its own `row_sha256` may be anything)."""
    def edit(body):
        P.entry_of(body, "java", "stall")["row_sha256"] = "d" * 64
    assert P.v8_problems(P.reseal(declined, edit)) == []


# ---------------------------------------------------------------------------------------------------- (b) campaign-core closure
def test_fix_tg2_campaign_core_names_the_gradle_home_source_and_tg1_does_not():
    """[FIX] erratum 12: `CORE_SPECS["probe_data"]` of the tg2 chain holds `bench/tg2_gradle_home.py`; tg1's does not."""
    from bench.tests import test_m76_b4b1_fe_support as FS
    assert GRADLE_SRC in FS.chain_entry().CORE_SPECS["probe_data"]
    assert GRADLE_SRC not in FS.tg1_chain_entry().CORE_SPECS["probe_data"]


def test_fix_a_change_to_the_gradle_home_source_changes_tg2s_campaign_core_and_not_tg1s(tmp_path):
    """[FIX] erratum 12 (Sol P3): the tg2 prefill / check code is part of what a tg2 campaign core pins; editing it changes tg2's
    probe closure sha256 and leaves both of tg1's closure sha256s unchanged. (A copy of the closure files in a temp tree.)"""
    from bench import campaign_core
    from bench.tests import test_m76_b4b1_fe_support as FS
    specs = {"tg1": dict(FS.tg1_chain_entry().CORE_SPECS), "tg2": dict(FS.chain_entry().CORE_SPECS)}
    files = {GRADLE_SRC}
    for spec in specs.values():
        files |= set(campaign_core.members(X.REPO, spec["probe_entry"], spec["probe_data"]))
        files |= set(campaign_core.members(X.REPO, spec["chain_entry"], spec["chain_data"]))
    for rel in files:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(X.REPO / rel, tmp_path / rel)
    before = {k: campaign_core.closure_shas(tmp_path, **s) for k, s in specs.items()}
    with open(tmp_path / GRADLE_SRC, "a") as fh:
        fh.write("\n# a change to the Gradle home code\n")
    after = {k: campaign_core.closure_shas(tmp_path, **s) for k, s in specs.items()}
    assert after["tg2"]["probe_closure_sha256"] != before["tg2"]["probe_closure_sha256"]
    assert after["tg1"] == before["tg1"]


# ---------------------------------------------------------------------------------------------------- (c) flat Stop wording
def stop_lines(log):
    return [line for line in log.splitlines() if "STOP:" in line]


@pytest.mark.parametrize("content", ["{not json", ""], ids=["garbage", "empty"])
def test_fix_the_unreadable_baseline_stop_is_a_flat_fail_closed_statement(tmp_path, monkeypatch, content):
    """[FIX] erratum 14: an unreadable baseline is an automatic fail-closed stop; the line names it, not "the operator decides"."""
    def damaged(ops, clock):
        base = tmp_path / "wd/p426/wave2"
        base.mkdir(parents=True)
        (base / "host_env.json").write_text(content)
    r = X.drive(tmp_path, monkeypatch, "run", "--through", Q.OFF_PILOT, before=damaged)
    lines = stop_lines(X.seq_log(r))
    assert r["rc"] == 1 and lines and any("host_env.json" in line for line in lines)
    assert not [line for line in lines if "operator" in line.lower()], lines


def test_fix_the_host_invalid_leg_stop_is_a_flat_fail_closed_statement(tmp_path, monkeypatch):
    """[FIX] erratum 14: the stop for a leg the host change made INVALID states the fact (and the host change), no operator wording.
    S29 H2 (C384): changed — that stop no longer exists: the run goes on (rc 0), no STOP line, the change is logged."""
    r = X.drive(tmp_path, monkeypatch, "run", "--through", Q.ON_PILOT, before=Q.at("on_launch", Q.OFF_PILOT, Q.mutate))
    log = X.seq_log(r)
    assert r["rc"] == 0 and stop_lines(log) == []
    assert f"host environment changed during {Q.OFF_PILOT}.a1: {Q.ADDED}" in log


def test_fix_the_other_guard_stops_carry_no_operator_wording(tmp_path, monkeypatch):
    """[FIX] erratum 14: the pre-launch refusal and the end-of-run stop (already flat) stay flat. S29 H1 / H3 (C384): changed —
    neither stops any more (rc 0, no STOP line); each is a log line."""
    pre = X.drive(tmp_path / "pre", monkeypatch, "run", "--through", Q.ON_PILOT, before=Q.at("on_harvest", Q.OFF_PILOT, Q.mutate))
    end = X.drive(tmp_path / "end", monkeypatch, "run", "--through", Q.ON_PILOT, before=Q.at("on_harvest", Q.ON_PILOT, Q.mutate))
    for r, needle in ((pre, f"differs from the baseline before {Q.ON_PILOT}"), (end, "differs from the baseline after the last leg")):
        log = X.seq_log(r)
        assert r["rc"] == 0 and stop_lines(log) == [] and needle in log
