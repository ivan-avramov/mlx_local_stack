"""M76 B7 criteria 2 / 5 / 6 / 7 / 8: the simulation's inputs, its bootstrap against `bench.stats`, the exact
interaction null, A5 sizing, `calibrate`, `recheck`, reproducibility, and the committed report."""
import json
import random
import time
from pathlib import Path

import pytest

import bench.stats as S
from bench import m76_rule as R
from bench import m76_sim as M

REPORT = Path(M.__file__).resolve().parent.parent / "results" / "m76" / "b7-simulation"
SMALL_GRID = dict(pass_rates=(0.5, 0.7), discordance=(0.10, 0.20), sigmas=(0.0,))


def test_loaders_match_p426_signals_counts():
    a1 = M.load_a1_n16()
    assert [(t, n, k) for t, n, k, _ in a1] == [("p426s2-on-b1", 50, 49), ("p426s2-on-b2", 50, 47)]
    per, paths = M.load_a7_n16()
    assert len(per) == 43 and paths
    assert sum(v["s1"] for v in per.values()) == 41 and sum(v["s2"] for v in per.values()) == 42
    b = M.beta_from_sessions(per)
    assert b["m"] == pytest.approx(83 / 86) and b["a"] is None
    assert M.find_tg2_pilot() == []


def test_beta_moment_fit():
    per = {i: {"s1": 1, "s2": 1} for i in range(18)}
    per.update({18: {"s1": 0, "s2": 0}, 19: {"s1": 0, "s2": 1}})
    b = M.beta_from_sessions(per)
    assert b["cov"] > 0 and b["a"] / (b["a"] + b["b"]) == pytest.approx(b["m"])
    var = b["a"] * b["b"] / ((b["a"] + b["b"]) ** 2 * (b["a"] + b["b"] + 1))
    assert var == pytest.approx(b["var_between"])


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_ideal_bootstrap_matches_paired_session_delta(seed):
    rng = random.Random(seed)
    a, b = {}, {}
    for i in range(43):
        a[i], b[i] = {}, {}
        for s in range(3):
            x = 1
            y = 1 if rng.random() > 0.15 else 0
            if rng.random() < 0.5:
                x, y = y, x
            a[i][s], b[i][s] = x, y
    r = S.paired_session_delta(a, b, iters=20000, seed=seed)
    d = {i: [a[i][s] - b[i][s] for s in range(3)] for i in a}
    _, delta, lo, hi = M.analyse(d, list(range(43)), list(range(3)), 0.025)
    assert delta == pytest.approx(r["delta"])
    step = 1 / (43 * 3)
    assert abs(lo - r["lo"]) <= step + 1e-9 and abs(hi - r["hi"]) <= step + 1e-9


def test_ideal_bootstrap_matches_stratified_paired_delta():
    rng = random.Random(9)
    n = 40
    d = {i: [(-1 if rng.random() < 0.6 else 1) if rng.random() < 0.15 else 0] for i in range(n)}
    a = {i: [1 if d[i][0] >= 0 else 0] for i in d}
    b = {i: [1 if d[i][0] <= 0 else 0] for i in d}
    half = n // 2
    strata = {i: (i < half, (i % half) % 3) for i in range(n)}
    r = S.paired_delta(a, b, iters=20000, seed=5, strata=strata)
    _, delta, lo, hi = M.analyse(d, list(range(n)), [0], 0.025, strata_of=lambda i: strata[i])
    assert delta == pytest.approx(r["delta"])
    assert abs(lo - r["lo"]) <= 1 / n + 1e-9 and abs(hi - r["hi"]) <= 1 / n + 1e-9


def test_verdict_vector_matches_analyse_and_is_monotone():
    rng = random.Random(4)
    for _ in range(30):
        d = [[(-1 if rng.random() < 0.8 else 1) if rng.random() < 0.15 else 0 for _ in range(2)] for _ in range(80)]
        vals = [sum(r) for r in d]
        anyd = any(x for r in d for x in r)
        vec = M.verdict_vector(vals, 80, 2, anyd)
        for j, a in enumerate(M.CANDIDATES):
            assert vec[j] == M._VCODE[M.analyse(d, range(80), range(2), a)[0]]
        p = vec.count("P")
        assert vec[:p] == "P" * p                               # PASS only at the larger alphas


@pytest.mark.parametrize("n,k,strat", [(80, 2, False), (43, 3, False), (100, 1, False), (60, 1, True)])
def test_stage_function_equals_simulator_decision_at_every_candidate_alpha(n, k, strat):
    """Finding 1: on randomized rows, `m76_rule.loss_bound` (the stage-3 path) gives the simulator's verdict, delta and
    interval (`analyse`, `verdict_vector`) at every candidate α and at the A1 / A7 OBF alphas."""
    rng = random.Random(100 * n + k)
    alphas = list(M.CANDIDATES) + [R.axis_plan("A1")["looks"][0]["alpha"], S.obf_alpha(2 / 3, 0.025)]
    for _ in range(25):
        disc, lossp = rng.choice((0.0, 0.05, 0.15, 0.3)), rng.random()
        a, b, d = {}, {}, {}
        for i in range(n):
            a[i], b[i], d[i] = {}, {}, []
            for s in range(k):
                y = int(rng.random() < 0.7)
                x = (1 - y) if (rng.random() < disc and (y == 1) == (rng.random() < lossp)) else y
                a[i][f"s{s}"], b[i][f"s{s}"] = x, y
                d[i].append(x - y)
        strata = {i: i % 4 for i in range(n)} if strat else None
        sof = (lambda i: strata[i]) if strat else None
        anyd = any(x for r in d.values() for x in r)
        vec = M.verdict_vector([sum(d[i]) for i in range(n)], n, k, anyd) if not strat else None
        for j, al in enumerate(alphas):
            lb = R.loss_bound(a, b, alpha=al, strata=strata)
            v, delta, lo, hi = M.analyse(d, list(range(n)), list(range(k)), al, strata_of=sof)
            assert (lb["verdict"], lb["delta"], lb["lo"], lb["hi"]) == (v, delta, lo, hi), (al, lb, v, lo, hi)
            if vec is not None and j < len(M.CANDIDATES):
                assert M._VCODE[lb["verdict"]] == vec[j]


def test_data_model_hits_planning_values():
    for loss in (0.0, 0.10):
        res = M.simulate_cell("A1", loss, 0.25, 300)
        assert res["realized_discordance"] == pytest.approx(max(0.06, loss), abs=0.01)
        assert res["realized_loss"] == pytest.approx(loss, abs=0.01)
        r8 = M.simulate_multi("A8", 0.5, 0.182, 0.25, loss, 300)["model"]
        assert r8["realized_discordance"] == pytest.approx(0.182, abs=0.01)
        assert r8["realized_loss"] == pytest.approx(loss, abs=0.01)
        r5 = M.simulate_a5(72, loss, 0.25, 500)
        assert r5["realized_loss"] == pytest.approx(loss, abs=0.01)


def test_calibrate_omega():
    for t in (0.5, 0.75, 0.9):
        w0 = M.calibrate_omega(t, 0.5)
        xs, ws = M._normal_grid()
        e = sum(w * M._expit(M._logit(w0) + 0.5 * x) for x, w in zip(xs, ws))
        assert e == pytest.approx(t, abs=1e-9)
    assert M.calibrate_omega(1.0, 0.5) == 1.0


def test_cell_feasibility():
    assert M.cell_feasibility(0.5, 0.3, 4.0) == []
    assert M.cell_feasibility(0.96, 0.10, 4.0)                  # D/2 = 0.05 > 1 − m = 0.04
    assert M.cell_feasibility(0.9, 0.3, 4.0)
    assert M.cell_feasibility(0.9, 0.2, 4.0) == []


# ------------------------------------------------------------------------------------------------ interaction
@pytest.mark.parametrize("k", [2, 3])
def test_interaction_exact_p_matches_monte_carlo(k):
    rng = random.Random(10 + k)
    a, b = {}, {}
    for i in range(30):
        a[i] = {s: int(rng.random() < 0.7) for s in range(k)}
        b[i] = {s: int(rng.random() < (0.9 if s == 0 else 0.6)) for s in range(k)}
    rows = [tuple(a[i][s] - b[i][s] for s in range(k)) for i in range(30)]
    p = M.interaction_exact_p(rows)
    mc = R.session_interaction(a, b, iters=40000, seed=1)["pvalue"]
    assert abs(p - mc) < 4 * (p * (1 - p) / 40000) ** 0.5 + 1e-3


def test_interaction_exact_p_small_enumeration():
    # two active items with d = (−1, 0): obs puts both −1 in session 0 → Q = 4; null: same column w.p. 1/2
    assert M.interaction_exact_p([(-1, 0), (-1, 0), (0, 0)]) == pytest.approx(0.5)
    assert M.interaction_exact_p([(0, 0), (1, 1)]) == 1.0


def test_fire_probability():
    assert M._mc_kmax(10000) == 499
    assert (1 + 499) / 10001 < 0.05 <= (1 + 500) / 10001
    assert M.fire_probability(0.0) == 1.0 and M.fire_probability(1.0) == 0.0
    assert M.fire_probability(0.03) > 0.999 and M.fire_probability(0.07) < 1e-6
    assert 0.4 < M.fire_probability(0.05) < 0.6


# ------------------------------------------------------------------------------------------------------- A5
def test_a5_table_matches_verdict_a5():
    n = 48
    t = M.a5_table(n)
    for b, c in [(0, 0), (1, 0), (2, 1), (3, 0), (6, 0), (9, 1), (12, 0), (0, 5), (5, 5)]:
        assert t[(b, c)] == R.verdict_a5(b, c, n).verdict[0], (b, c)


# ------------------------------------------------------------------------------------------------- calibrate
def test_calibrate_deterministic_and_criterion_5():
    c1 = M.calibrate("A8", reps=300, grid=SMALL_GRID)
    c2 = M.calibrate("A8", reps=300, grid=SMALL_GRID)
    assert json.dumps(c1, sort_keys=True) == json.dumps(c2, sort_keys=True)
    _check_criterion_5(c1)


def _check_criterion_5(cal):
    star = cal["alpha_star"]
    feas = [c for c in cal["cells"].values() if c["feasible"]]
    if star is None:
        return
    j = M.CANDIDATES.index(star)
    for c in feas:
        assert M._rate(M._single_counts(c["hist"], j), c["reps"])["hi"] <= 0.025
    if j > 0:
        bind = cal["cells"][cal["binding_cell"]]
        assert M._rate(M._single_counts(bind["hist"], j - 1), bind["reps"])["hi"] > 0.025


def test_v12_a8_grid_and_sensitivity_constants():
    assert M.CAL_GRID["A8"]["sigmas"] == (0.0, 0.25)
    assert M.SENSITIVITY_SIGMAS == {"A8": (0.5,)}
    assert M.CAL_GRID["A7"]["sigmas"] == (0.0, 0.25, 0.5) and M.DEFAULT_KAPPA == 4.0


def test_sensitivity_cells_never_set_alpha_star():
    base = M.calibrate("A8", reps=300, grid=SMALL_GRID)
    sens = M.calibrate("A8", reps=300, grid=dict(SMALL_GRID, sensitivity_sigmas=(0.5,)))
    assert "sensitivity" not in base
    for k in ("alpha_star", "binding_cell", "worst_hi_at_star", "next_larger_worst_hi", "skipped_cells"):
        assert sens[k] == base[k], k
    assert json.dumps(sens["cells"], sort_keys=True) == json.dumps(base["cells"], sort_keys=True)
    s = sens["sensitivity"]
    assert s["sets_alpha_star"] is False and s["sigmas"] == [0.5] and s["alpha_star"] == base["alpha_star"]
    assert set(s["cells"]) == {M._cell_key(m, d, 0.5) for m in (0.5, 0.7) for d in (0.10, 0.20)}
    assert not set(s["cells"]) & set(sens["cells"])
    for ck, c in s["cells"].items():
        his = [M._rate(M._single_counts(c["hist"], j), c["reps"])["hi"] for j in range(len(M.CANDIDATES))]
        safe = [a for a, h in zip(M.CANDIDATES, his) if h <= 0.025]
        assert c["safe_candidates"] == safe
        assert c["smallest_safe"] == (min(safe) if safe else None)
        assert c["largest_safe"] == (max(safe) if safe else None)
        if base["alpha_star"] is not None:
            assert c["hi_at_alpha_star"] == his[M.CANDIDATES.index(base["alpha_star"])]
        again = M.simulate_multi("A8", c["m"], c["D"], 0.5, 0.10, 300, kappa=c["kappa"])
        assert again["hist"] == c["hist"]


def test_calibrate_reuses_committed_cells():
    c1 = M.calibrate("A8", reps=200, grid=SMALL_GRID)
    marker = {k: dict(v) for k, v in c1["cells"].items()}
    c2 = M.calibrate("A8", reps=200, grid=dict(SMALL_GRID, pass_rates=(0.5, 0.7, 0.6)), committed=marker)
    for k in marker:
        assert c2["cells"][k] is marker[k]
    assert len(c2["cells"]) == 6


# --------------------------------------------------------------------------------------------------- recheck
@pytest.fixture(scope="module")
def small_report(tmp_path_factory):
    d = tmp_path_factory.mktemp("rep")
    cal = M.calibrate("A8", reps=300, grid=dict(SMALL_GRID, sensitivity_sigmas=(0.5,)))
    p = d / "report.json"
    p.write_text(json.dumps(M._round({"axes": {"A8": {"calibration": cal, "alpha_star_fixed": 0.001}}}),
                            sort_keys=True))
    return p


def _rows(n_items, m_pass, disc_items, loss_items, mixed):
    """N16 / X rows, two sessions. N16: `mixed` items pass exactly one session (alternating s1 / s2), P items pass
    both and the rest fail both, with 2P + mixed = 2 · m · n (so the moment-fit concentration is controlled by
    `mixed`). X = N16 with `disc_items` item-sessions flipped, `loss_items` of them losses (N16 pass → X fail)."""
    P = round(2 * m_pass * n_items - mixed) // 2
    assert 2 * P + mixed == round(2 * m_pass * n_items) and P + mixed <= n_items
    n16 = {}
    for i in range(n_items):
        if i < P:
            n16[i] = {"s1": 1, "s2": 1}
        elif i < P + mixed:
            n16[i] = {"s1": 1, "s2": 0} if (i - P) % 2 == 0 else {"s1": 0, "s2": 1}
        else:
            n16[i] = {"s1": 0, "s2": 0}
    x = {i: dict(v) for i, v in n16.items()}
    cells = [(i, s) for s in ("s1", "s2") for i in range(n_items)]
    passing = [c for c in cells if n16[c[0]][c[1]] == 1]
    failing = [c for c in cells if n16[c[0]][c[1]] == 0]
    for i, s in passing[:loss_items]:
        x[i][s] = 0
    for i, s in failing[:disc_items - loss_items]:
        x[i][s] = 1
    return n16, x


def test_recheck_rows_helper_controls_kappa():
    k_inside = M._estimate_nuisance(*_rows(80, 0.6, 24, 20, 32))["kappa"]
    k_low = M._estimate_nuisance(*_rows(80, 0.6, 24, 20, 16))["kappa"]
    assert k_inside == pytest.approx(4.93, abs=0.01) and k_low == pytest.approx(0.69, abs=0.01)


def test_recheck_inside_hull_keeps_alpha_and_ignores_arm_effect(tmp_path, small_report):
    n16, x_loss = _rows(80, 0.6, 24, 20, 32)                   # κ̂ 4.93 ≥ committed 4
    _, x_gain = _rows(80, 0.6, 24, 4, 32)
    r1 = M.recheck("A8", n16, x_loss, out=tmp_path / "a", report=small_report, reps=300)
    r2 = M.recheck("A8", n16, x_gain, out=tmp_path / "b", report=small_report, reps=300)
    assert r1 == r2
    assert (tmp_path / "a" / "recheck-A8.json").read_bytes() == (tmp_path / "b" / "recheck-A8.json").read_bytes()
    calibrated = json.loads(small_report.read_text())["axes"]["A8"]["calibration"]["alpha_star"]
    assert r1["inside"] is True and r1["alpha_star_applied"] == 0.001 and r1["committed_alpha_star"] == 0.001
    assert r1["calibrated_alpha_star"] == calibrated and r1["unsafe_on_extended_grid"] is False
    assert r1["observed_unrealisable"] is False and r1["operator_review"] is False and r1["outside_reasons"] == []
    assert r1["estimates"]["discordance"] == pytest.approx(24 / 160)
    assert r1["committed_kappa"] == 4.0 and r1["observed_kappa"] == pytest.approx(4.93, abs=0.01)
    assert "loss" not in json.dumps(r1["estimates"]) and "unsafe_at_observed" not in r1


def test_recheck_outside_hull_recalibrates_never_loosens(tmp_path, small_report):
    n16, x = _rows(80, 0.9, 30, 26, 12)                         # m 0.9 (outside 0.5–0.7), D 0.1875, κ̂ 4.93
    r = M.recheck("A8", n16, x, out=tmp_path, report=small_report, reps=300)
    assert r["inside"] is False and r["extended_grid"]["pass_rates"] == [0.5, 0.7, 0.9]
    assert r["extended_grid"]["sigmas"] == [0.0] and "sensitivity_sigmas" not in r["extended_grid"]   # v1.2 grid
    assert r["committed_alpha_star"] == 0.001 and r["alpha_star_applied"] == 0.001     # v1.3: never above 0.001
    assert r["recalibrated_all_cells"] is True and r["new_cells_kappa"] == r["observed_kappa"]
    if r["new_alpha_star"] is not None:
        assert r["alpha_star_applied"] == min(0.001, r["new_alpha_star"]) and r["unsafe_on_extended_grid"] is False
    else:
        assert r["unsafe_on_extended_grid"] is True and r["operator_review"] is True
    again = M.recheck("A8", n16, x, out=tmp_path / "again", report=small_report, reps=300)
    assert again == r


def test_recheck_dispersion_only_change_recalibrates_every_cell_at_observed_kappa(tmp_path, small_report,
                                                                                  monkeypatch):
    """Finding 3: (m̂, D̂) inside the hull, κ̂ below the committed 4 → outside; every cell recalibrated at κ̂ (no
    committed cell of κ 4 reused)."""
    n16, x = _rows(80, 0.6, 24, 20, 16)                        # m 0.6, D 0.15 (inside), κ̂ 0.69
    seen = {}
    real = M.calibrate

    def spy(axis, **kw):
        seen.update(kw)
        return real(axis, **kw)
    monkeypatch.setattr(M, "calibrate", spy)
    r = M.recheck("A8", n16, x, out=tmp_path, report=small_report, reps=200)
    assert r["inside"] is False and r["observed_unrealisable"] is False
    assert len(r["outside_reasons"]) == 1 and r["outside_reasons"][0].startswith("concentration")
    assert seen["committed"] is None and seen["kappa"] == r["observed_kappa"] == pytest.approx(0.69, abs=0.01)
    assert r["recalibrated_all_cells"] is True and r["alpha_star_applied"] <= 0.001
    assert r["extended_grid"]["pass_rates"] == [0.5, 0.6, 0.7] and r["extended_grid"]["discordance"] == [0.1, 0.15, 0.2]


def test_recheck_unrealisable_observed_nuisance_flags_operator(tmp_path, small_report, monkeypatch):
    """Finding 3: N16 sessions identical on every item → κ̂ ≈ 0 (all variance between items): the data model's π cap
    binds, so the observed (m̂, D̂, κ̂) is not realisable → outside, flagged for the operator."""
    n16, x = _rows(80, 0.6, 24, 20, 0)

    def never(axis, **kw):
        raise AssertionError("v1.4: no recalibration at an unrealisable observed nuisance")
    monkeypatch.setattr(M, "calibrate", never)
    r = M.recheck("A8", n16, x, out=tmp_path, report=small_report, reps=200)
    assert r["inside"] is False and r["observed_unrealisable"] is True and r["operator_review"] is True
    assert r["observed_infeasible_reasons"] and any("not realisable" in w for w in r["outside_reasons"])
    assert r["alpha_star_applied"] == 0.001 and r["unsafe_on_extended_grid"] is False
    assert r["recalibration_attempted"] is False and r["new_alpha_star"] is None and r["extended_grid"] is None
    on_disk = json.loads((tmp_path / "recheck-A8.json").read_text())
    assert on_disk["observed_unrealisable"] is True and on_disk["operator_review"] is True


@pytest.mark.parametrize("m_hat", [1, 0])
def test_recheck_degenerate_n16_pass_rate_returns_record(tmp_path, small_report, monkeypatch, m_hat):
    """v1.4: m̂ = 1 / m̂ = 0 (40 items × 2 sessions) → a record (no exception, no `calibrate` call) flagging
    `observed_unrealisable` / `operator_review`, with the fixed α* applied."""
    n16 = {i: {"s1": m_hat, "s2": m_hat} for i in range(40)}
    x = {i: dict(v) for i, v in n16.items()}
    for i in range(6):
        x[i]["s1"] = 1 - m_hat                                 # 6 discordant item-sessions (m̂ 1: losses; 0: gains)

    def never(axis, **kw):
        raise AssertionError("v1.4: no recalibration at an unrealisable observed nuisance")
    monkeypatch.setattr(M, "calibrate", never)
    r = M.recheck("A8", n16, x, out=tmp_path, report=small_report, reps=200)
    assert r["estimates"]["n16_mean"] == m_hat and r["observed_kappa"] is None
    assert r["inside"] is False and r["observed_unrealisable"] is True and r["operator_review"] is True
    assert r["alpha_star_applied"] == 0.001 == r["committed_alpha_star"] and r["recalibration_attempted"] is False
    assert r["new_alpha_star"] is None and r["unsafe_on_extended_grid"] is False
    assert json.loads((tmp_path / "recheck-A8.json").read_text()) == r


def test_recheck_v13_no_safe_candidate_flags_unsafe_on_extended_grid(tmp_path, small_report, monkeypatch):
    """v1.3 (C336): outside the hull with no safe candidate on the extended grid → α* 0.001 applied and
    `unsafe_on_extended_grid: true`."""
    def no_safe(axis, **kw):
        return dict(alpha_star=None, binding_cell="m=0.9|D=0.1875|sigma=0.0", skipped_cells=[])
    monkeypatch.setattr(M, "calibrate", no_safe)
    n16, x = _rows(80, 0.9, 30, 26, 12)
    r = M.recheck("A8", n16, x, out=tmp_path, report=small_report, reps=300)
    assert r["inside"] is False and r["new_alpha_star"] is None
    assert r["alpha_star_applied"] == 0.001 and r["unsafe_on_extended_grid"] is True and r["operator_review"] is True
    on_disk = json.loads((tmp_path / "recheck-A8.json").read_text())
    assert on_disk["alpha_star_applied"] == 0.001 and on_disk["unsafe_on_extended_grid"] is True


def test_recheck_v13_safe_recalibration_applies_min(tmp_path, small_report, monkeypatch):
    monkeypatch.setattr(M, "calibrate", lambda axis, **kw: dict(alpha_star=0.005, binding_cell=None, skipped_cells=[]))
    n16, x = _rows(80, 0.9, 30, 26, 12)
    r = M.recheck("A8", n16, x, out=tmp_path, report=small_report, reps=300)
    assert r["alpha_star_applied"] == 0.001 and r["unsafe_on_extended_grid"] is False and r["new_alpha_star"] == 0.005


# ------------------------------------------------------------------------------------------- reproducibility
def test_report_regenerates_byte_identically(tmp_path):
    t0 = time.monotonic()
    M.write_report(tmp_path / "a", reps=150, a5_ns=[42, 72])
    elapsed = time.monotonic() - t0
    M.write_report(tmp_path / "b", reps=150, a5_ns=[42, 72])
    for f in ("report.json", "REPORT.md"):
        assert (tmp_path / "a" / f).read_bytes() == (tmp_path / "b" / f).read_bytes()
    print(f"\n[m76_sim] 150-rep report: {elapsed:.1f} s")
    rep = json.loads((tmp_path / "a" / "report.json").read_text())
    assert set(rep["axes"]) == {"A1", "A7", "A5", "A8"}


# ------------------------------------------------------------------------------------------------ the committed report
def _committed():
    p = REPORT / "report.json"
    if not p.exists():
        pytest.fail(f"{p} missing: generate it with `python -m bench.m76_sim --out results/m76/b7-simulation/`")
    return json.loads(p.read_text())


def test_committed_report_is_full_size_and_seeded():
    rep = _committed()
    assert rep["header"]["reps"] >= 20000 and rep["header"]["seed"] == 426
    assert (REPORT / "REPORT.md").read_text() == M.render_md(rep)
    for ax in ("A7", "A8"):
        cal = rep["axes"][ax]["calibration"]
        assert all(c["reps"] >= 20000 for c in cal["cells"].values())


def test_committed_report_states_plan():
    rep = _committed()
    md = (REPORT / "REPORT.md").read_text()
    assert "## Final plan" in md and f"n = {rep['axes']['A5']['n']}" in md
    for ax in ("A7", "A8"):
        assert f"α* = {rep['axes'][ax]['calibration']['alpha_star']}" in md


def test_committed_a5_sizing_and_exact_size():
    a5 = _committed()["axes"]["A5"]
    ns = sorted(int(n) for n in a5["n_scan"])
    assert ns == list(range(42, 121, 6))
    passing = [n for n in ns if a5["n_scan"][str(n)]["pass0"]["rate"] >= 0.8]
    assert a5["n_target_met"] == bool(passing)
    if passing:
        assert a5["n"] == passing[0]
    for n in ns:
        assert a5["n_scan"][str(n)]["exact_size"] <= 0.025
    assert a5["exact_size"] == pytest.approx(R.a5_exact_size(a5["n"]), abs=1e-6)


def test_committed_calibration_criterion_5():
    rep = _committed()
    for ax in ("A7", "A8"):
        _check_criterion_5(rep["axes"][ax]["calibration"])


def test_committed_v13_a8_fixed_alpha_and_full_grid():
    rep = _committed()
    assert rep["header"]["spec"].endswith("v1.4")
    a8 = rep["axes"]["A8"]
    assert M.FIXED_ALPHA_STAR == {"A8": 0.001} and a8["alpha_star_fixed"] == 0.001
    assert R.axis_plan("A8")["alpha_star"] == 0.001 and a8["final_alpha"] == [0.001]
    cal = a8["calibration"]
    assert cal["alpha_star"] is not None                                    # v1.2 calibration kept as context
    j = M.CANDIDATES.index(0.001)
    assert a8["final_pass0"] == pytest.approx(a8["planning_pass0_by_alpha"]["0.001"], abs=1e-6)
    fg = a8["full_grid_at_fixed"]
    assert fg["alpha"] == 0.001 and fg["sigmas"] == [0.0, 0.25, 0.5] and len(fg["cells"]) == 36
    src = dict(cal["cells"], **cal["sensitivity"]["cells"])
    assert set(fg["cells"]) == set(src)
    for ck, c in fg["cells"].items():
        s = src[ck]
        assert c["hi"] == pytest.approx(M._rate(M._single_counts(s["hist"], j), s["reps"])["hi"], abs=1e-6)
        assert c["feasible"] == s["feasible"]
    over = sorted(ck for ck, c in fg["cells"].items() if c["hi"] > 0.025)
    assert sorted(fg["over_target_realisable"] + fg["over_target_unrealisable"]) == over
    assert all(fg["cells"][ck]["sigma"] == 0.5 for ck in fg["over_target_realisable"])   # v1.2 grid safe at 0.001
    md = (REPORT / "REPORT.md").read_text()
    assert "**Decider α* = 0.001**" in md and "Full grid at the decider α* 0.001" in md
    assert "A8 decider α* fixed at 0.001 (C336)" in md


def test_committed_report_labels_a8_residual_and_a7_extrapolation():
    """Finding 4: A8's residual cells and plan-row label; A7's unrealisable planning cell and its nearest realisable
    cell's PASS(0)."""
    rep = _committed()
    md = (REPORT / "REPORT.md").read_text()
    a8 = rep["axes"]["A8"]
    fg = a8["full_grid_at_fixed"]
    res = a8["residual_cells"]
    assert sorted(res) == sorted(fg["over_target_realisable"]) and len(res) == 3
    for ck, c in res.items():
        assert c["sigma"] == 0.5 and c["feasible"] and c["hi"] > 0.025 and c == fg["cells"][ck]
    row = next(line for line in md.splitlines() if line.startswith("| A8 |"))
    assert "safe on the v1.2 grid; 3 realisable SD 0.5 cells over 0.025 (operator-accepted residual, C336)" in row
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    assert cells[-1] == "yes (v1.2 grid)"                              # v1.4: never a bare "yes" for A8
    for ax in ("A1", "A7", "A5"):
        other = next(line for line in md.splitlines() if line.startswith(f"| {ax} |"))
        assert "(v1.2 grid)" not in other.strip().strip("|").split("|")[-1]
    a7 = rep["axes"]["A7"]
    pl = a7["planning"]
    assert pl["feasible"] is False and pl["pass0_extrapolated"] is True
    nr = pl["nearest_realisable"]
    cal = a7["calibration"]
    assert cal["cells"][M._cell_key(nr["m"], nr["D"], 0.0)]["feasible"]
    feas = {(c["m"], c["D"]) for c in cal["cells"].values() if c["feasible"]}
    assert min(((m - pl["m"]) ** 2 + (d - pl["D"]) ** 2) ** 0.5 for m, d in feas) == pytest.approx(nr["distance"], abs=1e-6)
    row7 = next(line for line in md.splitlines() if line.startswith("| A7 |"))
    assert "not realisable under the data model: extrapolated" in row7
    assert f"nearest realisable cell m {nr['m']:g}, D {nr['D']:g}, σ {nr['sigma']:g}:" in row7
    assert row7.count("|") == 7                                  # no cell key splits the table row
    assert "NOT realisable under the data model" in md and "(extrapolated); nearest realisable cell" in md
    again = M.simulate_multi("A7", nr["m"], nr["D"], nr["sigma"], 0.0, 20000, kappa=cal["kappa"])
    j = M.CANDIDATES.index(a7["final_alpha"][0])
    assert round(M._single_counts(again["hist"], j) / 20000, 6) == nr["pass0"]["rate"]


def test_committed_v12_a8_grid_sensitivity_and_plan():
    rep = _committed()
    cal = rep["axes"]["A8"]["calibration"]
    assert cal["grid"]["sigmas"] == [0.0, 0.25] and cal["grid"]["sensitivity_sigmas"] == [0.5]
    assert {c["sigma"] for c in cal["cells"].values()} == {0.0, 0.25}
    assert rep["axes"]["A7"]["calibration"]["grid"]["sigmas"] == [0.0, 0.25, 0.5]
    assert "sensitivity" not in rep["axes"]["A7"]["calibration"]
    s = cal["sensitivity"]
    assert s["sets_alpha_star"] is False and s["alpha_star"] == cal["alpha_star"]
    assert len(s["cells"]) == 12 and {c["sigma"] for c in s["cells"].values()} == {0.5}
    assert cal["alpha_star"] is not None and rep["axes"]["A8"]["final_safe"]
    assert R.axis_plan("A8")["calibrated_alpha_star"] == cal["alpha_star"]   # v1.3: context; the plan's α* is 0.001
    md = (REPORT / "REPORT.md").read_text()
    assert "A8 session SD [0.5] sensitivity (never sets α*)" in md
    assert "Sensitivity only (v1.2, C335; never sets α*)" in md


def test_committed_interaction_null_firing_at_most_005():
    rep = _committed()
    for ax in ("A7", "A8"):
        for loss in ("0.0", "0.1"):
            fl = rep["axes"][ax]["interaction"][f"sigma=0.0|loss={loss}"]["any"]
            assert fl["hi"] <= 0.05, (ax, loss, fl)


def test_committed_plan_final_looks_are_safe():
    """Every final look kept by the plan passes its safety check (A1: MC upper ≤ 0.025; A5: exact size ≤ 0.025;
    A7 / A8: MC upper ≤ 0.025 at every realisable cell at α*)."""
    rep = _committed()
    bad = {ax: a.get("final_false_pass10_hi") for ax, a in rep["axes"].items() if not a["final_safe"]}
    assert not bad, f"final looks failing the safety check: {bad}"


def test_final_look_false_pass_recomputed_from_code():
    """Recompute from the shipped code at 20,000 replications: A1's final look and A5's realised false-PASS(10)
    (primary σ), and A8's binding cell at α*."""
    rep = _committed()
    res = M.simulate_cell("A1", 0.10, M.PRIMARY_SIGMA, 20000)
    k = res["counts"]["two_PASS" if rep["axes"]["A1"]["final"] == "two_look" else "one_PASS"]
    assert round(S.wilson(k, 20000)[1], 6) == rep["axes"]["A1"]["final_false_pass10_hi"]
    a5 = rep["axes"]["A5"]
    r5 = M.simulate_a5(a5["n"], 0.10, M.PRIMARY_SIGMA, 20000)
    assert round(S.wilson(r5["counts"]["P"], 20000)[1], 6) == a5["final_false_pass10_hi"]
    cal = rep["axes"]["A8"]["calibration"]
    if cal["binding_cell"] is not None:
        c = cal["cells"][cal["binding_cell"]]
        again = M.simulate_multi("A8", c["m"], c["D"], c["sigma"], 0.10, c["reps"], kappa=c["kappa"])
        assert again["hist"] == c["hist"]
