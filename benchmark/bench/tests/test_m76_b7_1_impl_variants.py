"""M76 B7.1 (implementer): pre-registered follow-up variants (criterion 2) — A5-2L by exact enumeration, A7-2L by
B7's calibrate method — and the screen options."""
import itertools
import json
import math
from pathlib import Path

import pytest

from bench import m76_rule as R
from bench import m76_sim as M
from bench import stats

REPORT = Path(M.__file__).resolve().parent.parent / "results" / "m76" / "b7-simulation"


def _committed():
    return json.loads((REPORT / "report.json").read_text())


# ------------------------------------------------------------------------------------------------- A5-2L
def test_a5_2l_alphas_are_obf_at_three_fifths():
    a1, a2 = M.a5_2l_alphas()
    assert a1 == pytest.approx(stats.obf_alpha(0.6, 0.025)) and a1 + a2 == pytest.approx(0.025)
    assert M.A5_2L["sizes"] == (72, 120)


def test_a5_verdict_table_default_alpha_equals_b7_table():
    assert M.a5_verdict_table(42, R.ALPHA_TOTAL) == M.a5_table(42)


def _trinom(n, pb, pc):
    out = {}
    lg = [math.lgamma(k + 1) for k in range(n + 1)]
    for b in range(n + 1):
        for c in range(n - b + 1):
            r = n - b - c
            lp = lg[n] - lg[b] - lg[c] - lg[r]
            for k, p in ((b, pb), (c, pc), (r, 1 - pb - pc)):
                if k:
                    lp += k * math.log(p) if p > 0 else -math.inf
            out[(b, c)] = math.exp(lp) if lp > -math.inf else 0.0
    return out


def _brute_two_look_size(n1, n2, a1, a2, grid):
    t1, t2 = M.a5_verdict_table(n1, a1), M.a5_verdict_table(n2, a2)
    best = 0.0
    for pc in grid:
        pb = pc + 0.10
        p1, pinc = _trinom(n1, pb, pc), _trinom(n2 - n1, pb, pc)
        s = 0.0
        for (b1, c1), w in p1.items():
            v = t1[(b1, c1)]
            if v == "P":
                s += w
            elif v == "U":
                s += w * sum(w2 for (b2, c2), w2 in pinc.items() if t2[(b1 + b2, c1 + c2)] == "P")
        best = max(best, s)
    return best


def test_a5_two_look_size_matches_brute_enumeration_small_n(monkeypatch):
    """The FFT convolution of the two-look size equals a direct double enumeration (small n; the size's nuisance
    grid made coarse by monkeypatching; the verdict tables are built first, on the default grid)."""
    import numpy as np
    n1, n2, a1, a2 = 30, 48, 0.01, 0.2
    M.a5_verdict_table(n1, a1), M.a5_verdict_table(n2, a2)          # cache the tables on the default grid
    grid = [0.45 * j / 40 for j in range(41)]
    monkeypatch.setattr(stats, "_nuisance_grid", lambda margin, g, gm: np.array(grid))
    got = M.a5_two_look_size(n1, n2, a1, a2)["size"]
    monkeypatch.undo()
    assert got == pytest.approx(_brute_two_look_size(n1, n2, a1, a2, grid), abs=1e-10)


def test_a5_2l_exact_size_at_most_alpha():
    """Criterion 2 (A5-2L, exact enumeration): the two-look rule's size ≤ 0.025 at the H0 boundary."""
    a1, a2 = M.a5_2l_alphas()
    ex = M.a5_two_look_size(72, 120, a1, a2)
    assert ex["size"] <= 0.025
    assert ex["size_look1"] <= a1 + 1e-12
    assert ex["size"] <= ex["union_bound"] + 1e-12


def test_committed_a5_2l_every_final_look_safe():
    v = _committed()["variants"]["A5-2L"]
    assert v["available"] and v["safe"]
    f = v["final_looks_false_pass10"]
    assert f["exact_size"] <= 0.025
    assert v["realised_safe"] == (f["realised_hi_worst_sigma"] <= 0.025)
    a1, a2 = M.a5_2l_alphas()
    assert f["exact_size"] == pytest.approx(M.a5_two_look_size(72, 120, a1, a2)["size"], abs=1e-6)
    assert [lk["size"] for lk in v["looks"]] == [72, 120]
    assert v["pass0"]["rate"] >= v["look1_pass0"]["rate"]
    assert set(v) >= {"clean_pass0", "clean0", "clean_pass0_by_cell", "hours", "pays", "undecided0",
                      "delta_clean_pass0", "worst_final_false_pass10"}
    assert v["worst_final_false_pass10"]["by_axis"]["A5"] == pytest.approx(
        max(f["exact_size"], f["realised_hi_worst_sigma"]), abs=1e-6)


def test_simulate_a5_2l_look1_never_exceeds_final_pass_and_is_deterministic():
    a = M.simulate_a5_2l(0.0, 0.25, 400)
    assert a == M.simulate_a5_2l(0.0, 0.25, 400)
    assert a["final"]["P"] >= a["look1"]["P"]
    assert a["final"]["P"] - a["look1"]["P"] <= a["look1"]["U"]


# ------------------------------------------------------------------------------------------------- A7-2L
def test_committed_a7_2l_calibration_is_b7_method_and_reports_unavailable():
    """Criterion 2 (A7-2L): the look-1 α* is the largest candidate safe against the O'Brien–Fleming spend α(3/5) at
    every realisable cell of A7's grid; when none is, the variant is reported unavailable (no final look adopted)."""
    v = _committed()["variants"]["A7-2L"]
    cal = v["calibration"]
    assert cal["target_look1"] == pytest.approx(stats.obf_alpha(0.6, 0.025), abs=1e-6)
    assert cal["reps"] >= 20000 and len(cal["cells"]) == 27
    feas = {ck: c for ck, c in cal["cells"].items() if c["feasible"]}
    safe = []
    for j, a in enumerate(M.CANDIDATES):
        worst = max(M._rate(M._look1_counts(c["hist"], j), c["reps"])["hi"] for c in feas.values())
        assert worst == pytest.approx(cal["look1_worst_hi_by_alpha"][str(a)], abs=1e-6)
        if worst <= cal["target_look1"]:
            safe.append(a)
    assert cal["alpha_star_look1"] == (max(safe) if safe else None)
    if not v["available"]:
        assert v["safe"] is None and "no candidate" in v["reason"]
    else:                                           # every final look safe
        j1 = M.CANDIDATES.index(cal["alpha_star_look1"])
        j2 = M.CANDIDATES.index(cal["alpha_star_look2"])
        for c in feas.values():
            assert M._rate(M._two_look_counts(c["hist"], j1, j2)["P"], c["reps"])["hi"] <= 0.025


def test_a7_2l_binding_cell_recomputes_from_code():
    v = _committed()["variants"]["A7-2L"]
    cal = v["calibration"]
    c = cal["cells"][cal["binding_cell_look1"]]
    again = M.simulate_multi_k(c["m"], c["D"], c["sigma"], 0.10, c["reps"], n_items=43, sessions=5, look1_sessions=3,
                               kappa=c["kappa"])
    assert again["hist"] == c["hist"]


def test_simulate_multi_k_look1_equals_first_sessions():
    r = M.simulate_multi_k(0.9, 0.1, 0.25, 0.0, 50, n_items=43, sessions=5, look1_sessions=3)
    assert sum(r["hist"].values()) == 50
    assert all(len(k.split("|")[0]) == len(M.CANDIDATES) == len(k.split("|")[1]) for k in r["hist"])


# ------------------------------------------------------------------------------------------- screen options
def test_committed_screen_options_reported_not_applied():
    rep = _committed()
    opts = rep["variants"]["screen_options"]
    assert set(opts) == {"T0", "T1", "T2", "T3", "TD"}
    s = rep["joint"]["screen"]["planning"]
    for o, x in opts.items():
        assert x["trigger0"] == s["loss0"]["rates"][o]
        assert x["detect_macro10"] == s["macro10"]["rates"][o]
        assert x["detect_concentrated10"] == s["concentrated10"]["rates"][o]
    # v1.3 (C338): TD is the committed plan's A8 path
    assert opts["TD"]["clean_pass0"]["rate"] == pytest.approx(rep["joint"]["headline"]["clean_pass"]["rate"], abs=1e-6)
    assert opts["TD"]["clean_pass0_by_cell"] == {
        c: rep["joint"]["cells"][c]["scenarios"]["all_loss0"]["clean_pass_by_hold"] for c in rep["joint"]["cells"]}
    assert opts["T1"]["trigger0"]["k"] <= opts["T2"]["trigger0"]["k"] <= opts["T0"]["trigger0"]["k"]
    assert R.axis_plan("A8")["looks"][0]["alpha"] == 0.001          # nothing adopted
