"""M76 B7.1 spec v1.1, erratum item "A5 clean term includes the per-task point gates" (retrieval and chain-4 each ≥ −5 pp
besides the pooled exact test; only the absolute per-arm ≥ 0.85 gates stay an assumption; recompute the committed plan and
A5-2L).

Independent reference (class (b)): an EXACT calculation of P(pooled exact-test PASS ∧ both task gates) under B7's A5 data
model — homogeneous per-item discordance D = 0.05, one block effect per task u ~ N(0, σ²), ω_u = expit(logit ω₀ + u) with
B7's calibrated ω₀ (`m76_sim.Model`), task = item parity (B7's block unit; the specification does not name the assignment —
stated assumption, shared with the candidate). Given (u₀, u₁) the two tasks' (b, c) are independent trinomials of n/2 items;
the pooled PASS region is B7's `a5_pass_region(n)`; the u's are integrated by 40-node Gauss–Hermite quadrature.
Class (c) tests read the report through the candidate's layout (`joint.cells.<cell>.terms.loss=<L>.A5.clean`,
`variants.A5-2L.clean0`) of the COMMITTED 20,000-replication report; tolerance 3.5 σ_MC (floor 0.01).
"""
import functools
import math
import random

import numpy as np
import pytest

from bench.tests.test_m76_b7_1_fe_support import (_a5_masks, _need, _tri, committed_report, mc_tol, task_gates_ok)


@functools.lru_cache(maxsize=None)
def exact_a5(n, loss, sigma=0.25, gated=True):
    """Exact P(PASS ∧ both task gates) (gated=False: P(PASS), B7's A5 PASS rate)."""
    from numpy.lib.stride_tricks import sliding_window_view
    from bench import m76_rule as R
    from bench import m76_sim as M
    mod = M.Model("A5", M.PLANNING_D["A5"], loss, sigma, None)
    d, nt = mod.d_real, n // 2
    xs, ws = np.polynomial.hermite_e.hermegauss(40)
    ws = ws / ws.sum()
    passm = np.zeros((n + 1, n + 1))
    for b, c in R.a5_pass_region(n):
        passm[b, c] = 1.0
    mat = np.ascontiguousarray(sliding_window_view(passm, (nt + 1, nt + 1)).reshape((nt + 1) ** 2, (nt + 1) ** 2))
    gate = np.array([[0.0 if (100 * (c - b) < -5 * nt) else 1.0 for c in range(nt + 1)] for b in range(nt + 1)])
    g = []
    for x in xs:
        om = mod.omega0 if (sigma == 0 or mod.omega0 in (0.0, 1.0)) else M._expit(M._logit(mod.omega0) + sigma * x)
        pm = _tri(nt, d * om, d * (1 - om))
        g.append((pm * (gate if gated else 1.0)).ravel())
    G = np.array(g)
    return float(ws @ (G @ mat @ G.T) @ ws)


# ------------------------------------------------------------------------------------------------ instrument (b)
@pytest.mark.parametrize("loss", [0.0, 0.10])
def test_instrument_exact_ungated_pass_equals_b7_a5_pass_rate(loss):  # (b)
    """Validation of the reference without the gates: it reproduces B7's committed A5 PASS rate (20,000 replications) at
    loss 0 and 10 pp, n = 72, σ = 0.25."""
    rep = committed_report()
    got = rep["axes"]["A5"]["cells"][f"sigma=0.25|loss={loss}"]["single"]["PASS"]["rate"]
    ex = exact_a5(rep["axes"]["A5"]["n"], loss, gated=False)
    assert abs(got - ex) <= mc_tol(ex, 20000), (got, ex)


def test_instrument_gates_cost_a_few_points_of_pass():  # (b)
    """The gates matter: at loss 0 the exact gated term is strictly below the ungated PASS by more than 3 pp."""
    assert exact_a5(72, 0.0, gated=False) - exact_a5(72, 0.0, gated=True) > 0.03


def test_gate_predicate_boundaries_and_agreement_with_the_candidate():  # (b)
    """−5 pp is allowed (≥ −5 pp), below fails; per task of 36 items: Σd = −1 (−2.8 pp) passes, −2 (−5.6 pp) fails; per task
    of 60 (A5-2L's 120 items): −3 (−5 pp exactly) passes, −4 fails. The candidate's `a5_task_gates` agrees with mine on
    random rows."""
    from bench import m76_sim as M

    def rows(n, s0, s1):                      # parity 0 gets sum s0, parity 1 gets s1 (all −1 / 0 / +1 spread)
        out = [[0] for _ in range(n)]
        for t, s in ((0, s0), (1, s1)):
            idx = [i for i in range(n) if i % 2 == t]
            for k in range(abs(s)):
                out[idx[k]] = [-1 if s < 0 else 1]
        return out
    for n, ok_sum, bad_sum in ((72, -1, -2), (120, -3, -4)):
        assert task_gates_ok(rows(n, ok_sum, 0)) and M.a5_task_gates(rows(n, ok_sum, 0))
        assert task_gates_ok(rows(n, 0, ok_sum)) and M.a5_task_gates(rows(n, 0, ok_sum))
        assert not task_gates_ok(rows(n, bad_sum, 0)) and not M.a5_task_gates(rows(n, bad_sum, 0))
        assert not task_gates_ok(rows(n, 0, bad_sum)) and not M.a5_task_gates(rows(n, 0, bad_sum))
    rng = random.Random(77)
    for _ in range(3000):
        n = rng.choice((72, 120))
        d = [[rng.choice((-1, 0, 0, 0, 1))] for _ in range(n)]
        assert task_gates_ok(d) == M.a5_task_gates(d)


# ------------------------------------------------------------------------------------------------- report (c)
@pytest.mark.parametrize("loss", [0.0, 0.10])
@pytest.mark.parametrize("cell", ["planning", "nearest_realisable"])
def test_committed_a5_clean_term_matches_exact_gated_reference(cell, loss):  # (c)
    """The committed report's A5 clean term (PASS ∧ per-task gates) vs my exact calculation, in both A7 cells (the A5 term
    is the same in both)."""
    rep = committed_report()
    got = _need(rep, "joint", "cells", cell, "terms", f"loss={loss}", "A5", "clean", "rate", what="A5 clean term")
    ex = exact_a5(rep["axes"]["A5"]["n"], loss)
    assert abs(got - ex) <= mc_tol(ex, 20000, floor=0.005), (cell, loss, got, ex)


def test_committed_a5_term_keeps_pass_and_reports_gate_failures():  # (c)
    """The ungated PASS / UNDECIDED / LOSS stay B7's counts (same random stream); clean = PASS − PASS ∧ gate failed."""
    rep = committed_report()
    t = rep["joint"]["cells"]["nearest_realisable"]["terms"]["loss=0.0"]["A5"]
    b7 = rep["axes"]["A5"]["cells"]["sigma=0.25|loss=0.0"]["single"]
    for k in ("PASS", "LOSS", "UNDECIDED"):
        assert t[k]["k"] == b7[k]["k"], (k, t[k], b7[k])
    assert t["clean"]["k"] + t["pass_gate_failed"]["k"] == t["PASS"]["k"]


def test_committed_assumption_text_lists_only_the_absolute_gates():  # (a)
    """Spec v1.1: only the absolute per-arm ≥ 0.85 gates remain an assumption; the point gates are simulated."""
    a = _need(committed_report(), "joint", "assumed", "a5_task_gates", what="A5 gate assumption text")
    assert "0.85" in a and "assumed met" in a and "point gates" in a and "simulated" in a


# ------------------------------------------------------------------------------------------------- A5-2L (b)/(c)
def _a5_2l_clean(alphas, loss, reps, seed, sigma=0.25):
    """My simulation of A5-2L: look 1 on the first 72 items (PASS → stop; LOSS → stop; UNDECIDED → look 2 on all 120);
    clean = final PASS ∧ the per-task gates on the DECIDING look's items."""
    from bench import m76_sim as M
    p1, l1 = _a5_masks(72, alphas[0])
    p2, _ = _a5_masks(120, alphas[1])
    model = M.Model("A5", M.PLANNING_D["A5"], loss, sigma, None)
    rng = random.Random(f"b71-a5-2l-clean:{seed}:{loss!r}")
    clean = 0
    for _ in range(reps):
        d = M._gen(model, 120, 1, lambda i, s: i % 2, rng)
        b = sum(1 for r in d[:72] if r[0] == -1)
        c = sum(1 for r in d[:72] if r[0] == 1)
        if p1[b, c]:
            clean += task_gates_ok(d[:72])
        elif not l1[b, c]:
            b = sum(1 for r in d if r[0] == -1)
            c = sum(1 for r in d if r[0] == 1)
            clean += bool(p2[b, c]) and task_gates_ok(d)
    return clean / reps


def test_a5_two_look_clean_term_matches_independent_simulation():  # (b)+(c)
    """The report's A5-2L clean PASS(0) (final PASS ∧ per-task gates at the deciding look) vs my own 6000-replication
    simulation at the report's per-look alphas; tolerance 3.5 σ_MC for estimates at 6000 and 20,000 replications."""
    rep = committed_report()
    v = rep["variants"]["A5-2L"]
    alphas = [lk["alpha"] for lk in v["looks"]]
    got = v["clean0"]["rate"]
    mine = _a5_2l_clean(alphas, 0.0, 6000, 5)
    assert abs(got - mine) <= mc_tol(got, 6000, 20000), (got, mine)
    assert got < v["pass0"]["rate"] - 0.005, "the gates must cost some PASS in A5-2L too"
