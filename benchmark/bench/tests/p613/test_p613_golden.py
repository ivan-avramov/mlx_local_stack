"""Golden numbers on the COMMITTED data (benchmark/results/p426, read-only; every output goes to tmp_path).

Marked `p613_golden` (registered in this directory's conftest.py). Class of every test is stated above it.
The contract's golden counts (s1 OFF 42/43, ON 41/43; s2 OFF 41/43, ON 43/43, the 5 `L0.pilot.a1` rows included) are the
LENIENT `passed` counts of the committed rows. By the contract's own definition (strict = passed AND converged) s2 ON is
42/43: `python/book-store` passed with `converged` false (budget_hit). Both are asserted below, each under its own name.
Same-epoch noise floor 0 / 5 in both arms; B8 accepts the Wave 2 pairs. The raw counts are re-derived here straight from the
committed rows (independent of the code under test).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bench.tests.p613 import sigview as V
from bench.tests.p613.sigview import run_cli

pytestmark = pytest.mark.p613_golden

ROOT = Path(__file__).resolve().parents[3] / "results" / "p426"
LENIENT = {("s1", "off"): 42, ("s1", "on"): 41, ("s2", "off"): 41, ("s2", "on"): 43}     # the contract's golden numbers
STRICT = {("s1", "off"): 42, ("s1", "on"): 41, ("s2", "off"): 41, ("s2", "on"): 42}      # passed AND converged


def committed_rows(arm, session):
    att = ROOT / "wave2" / f"tg1-p426-{arm}-{session}.a1" / session
    rows = []
    for f in sorted(att.glob("*.jsonl")):
        rows += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
    return rows


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("golden")
    b8 = out / "B8.json"
    md, js = out / "SIGNALS.md", out / "SIGNALS.json"
    r1 = run_cli("bench.p426_verify", ["a7", "--results-root", ROOT, "--out", b8])
    r2 = run_cli("bench.p426_signals", ["a7", "--results-root", ROOT, "--b8", b8, "--out-md", md, "--out-json", js])
    return {"dir": out, "b8": b8, "md": md, "js": js, "r1": r1, "r2": r2}


# class: invariant (the committed rows give the contract's golden counts as lenient `passed`; 43 planned slots each)
@pytest.mark.parametrize("session,arm", sorted(LENIENT))
def test_committed_golden_pass_counts(session, arm):
    rows = committed_rows(arm, session)
    assert len(rows) == 43 and len({r["id"] for r in rows}) == 43
    assert sum(1 for r in rows if r["passed"] is True) == LENIENT[(session, arm)]


# class: invariant (strict by the contract's definition: passed AND converged; differs from the golden only for s2 ON)
@pytest.mark.parametrize("session,arm", sorted(STRICT))
def test_committed_strict_counts(session, arm):
    rows = committed_rows(arm, session)
    assert sum(1 for r in rows if r["passed"] is True and r["converged"] is True) == STRICT[(session, arm)]


# class: invariant (reload == pilot, 5 / 5 in both arms, straight from the committed rows)
@pytest.mark.parametrize("arm", ["off", "on"])
def test_committed_reload_equals_pilot(arm):
    def outcome(session):
        att = ROOT / "wave2" / f"tg1-p426-{arm}-{session}.a1" / session
        rows = [json.loads(l) for f in sorted(att.glob("*.jsonl")) for l in f.read_text().splitlines() if l.strip()]
        return {r["id"]: (r["passed"], r["converged"]) for r in rows}
    pilot, reload_ = outcome("pilot"), outcome("reload")
    assert len(pilot) == len(reload_) == 5
    assert pilot == reload_


# class: new-behaviour (B8 on the committed tree accepts s1 and s2 with all 43 keys; pilot / reload are diagnostic)
def test_b8_accepts_the_wave2_pairs(built):
    assert built["r1"].returncode == 0, built["r1"].stderr
    b8 = json.loads(built["b8"].read_text())
    by = {p["pair"]: p for p in b8["pairs"]}
    for s in ("s1", "s2"):
        assert by[s]["accepted"] is True, by[s]["reasons"]
        assert by[s]["keys_accepted"] == 43 and by[s]["keys_rejected"] == []
        assert by[s]["reasons"] == []
    for s in ("pilot", "reload"):
        assert by[s].get("role") == "diagnostic" and by[s]["accepted"] is True, by[s]["reasons"]
    assert b8["axis"] == "A7"
    assert all(not rel.startswith("/") for rel in b8["inputs"])


# class: new-behaviour (the sheet's strict and lenient accuracy per arm, each / 43)
@pytest.mark.parametrize("session,arm", sorted(STRICT))
def test_sheet_strict_and_lenient_accuracy(built, session, arm):
    assert built["r2"].returncode == 0, built["r2"].stderr
    sig = json.loads(built["js"].read_text())
    tree = V.scope(sig, session)
    assert V.has_num(sig, session, STRICT[(session, arm)] / 43, tol=1e-9, sess_tree=tree)
    assert V.has_num(sig, session, LENIENT[(session, arm)] / 43, tol=1e-9, sess_tree=tree)


# class: new-behaviour (paired strict deltas on the committed data: s1 -1/43, s2 +1/43 [lenient s2: +2/43])
@pytest.mark.parametrize("session,delta", [("s1", -1 / 43), ("s2", 1 / 43)])
def test_sheet_strict_delta(built, session, delta):
    sig = json.loads(built["js"].read_text())
    assert V.has_num(sig, session, delta, tol=1e-9, sess_tree=V.scope(sig, session))


# class: new-behaviour (same-epoch noise floor 0 / 5 in both arms; cross-epoch prints both v8_base sha256 values)
def test_sheet_noise_floor(built):
    sig = json.loads(built["js"].read_text())
    noise = V.subtree(sig, "noise")
    assert noise
    pool = V.numbers(noise)
    assert 0 in pool and 5 in pool
    blob = V.text(noise)
    for ns in ("wave2", "wave2.v8-4104c7fc"):
        sha = json.loads((ROOT / ns / "run" / "v8_base.json").read_text())["sha256"]
        assert sha in blob, ns


# class: new-behaviour (byte-identical regeneration on the committed data; no absolute path in any output)
def test_golden_regeneration_and_no_absolute_paths(built, tmp_path):
    again_md, again_js, again_b8 = tmp_path / "S.md", tmp_path / "S.json", tmp_path / "B8.json"
    assert run_cli("bench.p426_verify", ["a7", "--results-root", ROOT, "--out", again_b8]).returncode == 0
    r = run_cli("bench.p426_signals", ["a7", "--results-root", ROOT, "--b8", again_b8, "--out-md", again_md,
                                       "--out-json", again_js])
    assert r.returncode == 0, r.stderr
    assert again_b8.read_bytes() == built["b8"].read_bytes()
    assert again_md.read_bytes() == built["md"].read_bytes()
    assert again_js.read_bytes() == built["js"].read_bytes()
    for path in (built["b8"], built["md"], built["js"]):
        blob = path.read_text()
        assert "/Users/" not in blob and "$STACK_WORKDIR" not in blob and str(ROOT) not in blob


# class: new-behaviour (header on the committed data)
def test_golden_header(built):
    md = built["md"].read_text()
    assert "PROVISIONAL — A7 only" in md[:4000]
