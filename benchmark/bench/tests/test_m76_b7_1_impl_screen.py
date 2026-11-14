"""M76 B7.1 (implementer): the A8 tg2 screen trigger, its exact computation and brute-force enumeration."""
import itertools
import math

import pytest

from bench import m76_sim as M


def test_screen_options_are_the_spec_options():
    assert M.SCREEN_OPTIONS == (("T0", -5, -15), ("T1", -5, None), ("T2", -5, -25), ("T3", 0, -10),
                                ("TD", None, None))
    assert (M.SCREEN_LANGUAGES, M.SCREEN_ITEMS_PER_LANGUAGE) == (4, 10)


@pytest.mark.parametrize("sums, expect", [
    ((0, 0, 0, 0), (False, False, False)),
    ((-1, -1, 0, 0), (False, False, False)),        # macro −5 pp exactly: not < −5
    ((-1, -1, -1, 0), (True, True, True)),          # macro −7.5 pp
    ((-2, 0, 0, 0), (True, False, False)),          # one language −20 pp: T0 only
    ((-2, 1, 0, 0), (True, False, False)),
    ((-3, 1, 1, 0), (True, False, True)),           # one language −30 pp, macro −2.5 pp
    ((-1, 0, 0, 0), (False, False, False)),         # −10 pp: no option
    ((-3, 2, 2, 2), (True, False, True)),
])
def test_screen_trigger_boundaries(sums, expect):
    got = tuple(M.screen_trigger(list(sums), 10, mp, lp) for _, mp, lp in M.SCREEN_OPTIONS[:3])
    assert got == expect


def _brute(models, sigma, n, option):
    """3^(L·n) enumeration of every outcome vector, integrated over the session effect by the same quadrature."""
    _, mp, lp = next(o for o in M.SCREEN_OPTIONS if o[0] == option)
    xs, ws = ([0.0], [1.0]) if sigma == 0 else M._normal_grid()
    # thin the quadrature for speed: it is exact for σ = 0; for σ > 0 compare at the same nodes
    tot = 0.0
    L = len(models)
    for x, w in zip(xs, ws):
        probs = []
        for mod in models:
            om, p = M._lang_omega(mod, sigma, x), mod.d_real
            probs.append({-1: p * om, 0: 1 - p, 1: p * (1 - om)})
        acc = 0.0
        for out in itertools.product((-1, 0, 1), repeat=L * n):
            pr = 1.0
            for li in range(L):
                for v in out[li * n:(li + 1) * n]:
                    pr *= probs[li][v]
            sums = [sum(out[li * n:(li + 1) * n]) for li in range(L)]
            if M.screen_trigger(sums, n, mp, lp):
                acc += pr
        tot += w * acc
    return tot


@pytest.mark.parametrize("option", ["T0", "T1", "T2"])
@pytest.mark.parametrize("losses", [(0.0, 0.0), (0.3, 0.0), (0.2, 0.2)])
def test_exact_trigger_matches_brute_force_enumeration_sigma0(option, losses):
    models = M._screen_models(None, 0.3, 0.0, losses, M.DEFAULT_KAPPA)
    ex = M._screen_exact_models(models, 0.0, 3, *next(o[1:] for o in M.SCREEN_OPTIONS if o[0] == option))
    assert ex == pytest.approx(_brute(models, 0.0, 3, option), abs=1e-12)


def test_exact_trigger_matches_brute_force_with_session_effect(monkeypatch):
    # a coarse quadrature makes brute force affordable; both use the same nodes
    xs = [-2.0, -0.5, 0.0, 0.7, 2.5]
    ws = [math.exp(-x * x / 2) for x in xs]
    s = sum(ws)
    monkeypatch.setattr(M, "_normal_grid", lambda: (xs, [w / s for w in ws]))
    models = M._screen_models(None, 0.3, 0.5, (0.1, 0.1), M.DEFAULT_KAPPA)
    for option in ("T0", "T1", "T2"):
        ex = M._screen_exact_models(models, 0.5, 3, *next(o[1:] for o in M.SCREEN_OPTIONS if o[0] == option))
        assert ex == pytest.approx(_brute(models, 0.5, 3, option), abs=1e-12)


@pytest.mark.parametrize("sigma", [0.0, 0.5])
def test_simulated_trigger_matches_brute_force_small_n(sigma):
    """Criterion 1 (screen): the simulated trigger rate matches the brute-force enumeration at small n (2 languages ×
    3 items, homogeneous π) within the MC interval."""
    reps = 20000
    losses = (0.2, 0.0)
    models = M._screen_models(None, 0.3, sigma, losses, M.DEFAULT_KAPPA)
    r = M.simulate_screen(None, 0.3, sigma, losses, reps, n_per_lang=3)
    rates = M.screen_rates(r["hist"], reps, 3)
    for option in ("T0", "T1", "T2"):
        bf = _brute(models, sigma, 3, option) if sigma == 0 else \
            M._screen_exact_models(models, sigma, 3, *next(o[1:] for o in M.SCREEN_OPTIONS if o[0] == option))
        se = math.sqrt(bf * (1 - bf) / reps)
        assert abs(rates[option]["rate"] - bf) <= 4 * se + 1e-9, (option, rates[option], bf)


def test_simulated_trigger_matches_exact_at_planning_cell():
    reps = 6000
    for name, losses in M.SCREEN_SCENARIOS:
        r = M.simulate_screen(0.5, 0.182, M.PRIMARY_SIGMA, losses, reps, kappa=M.DEFAULT_KAPPA)
        rates = M.screen_rates(r["hist"], reps, 10)
        for option in ("T0", "T1", "T2"):
            ex = M.screen_trigger_exact(0.5, 0.182, M.PRIMARY_SIGMA, losses, option)
            se = math.sqrt(max(ex * (1 - ex), 1e-6) / reps)
            assert abs(rates[option]["rate"] - ex) <= 4 * se + 2e-3, (name, option, rates[option]["rate"], ex)


def test_simulate_screen_deterministic_and_options_nested():
    a = M.simulate_screen(0.5, 0.182, 0.25, (0.0,) * 4, 500)
    b = M.simulate_screen(0.5, 0.182, 0.25, (0.0,) * 4, 500)
    assert a == b
    r = M.screen_rates(a["hist"], 500, 10)
    # T1 ⊂ T2 ⊂ T0 (thresholds nested)
    assert r["T1"]["k"] <= r["T2"]["k"] <= r["T0"]["k"]
