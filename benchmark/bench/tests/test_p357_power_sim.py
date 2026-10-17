"""P357: the power sim's paired outcomes must come from a FEASIBLE joint table with E[delta] = true delta.

The old `sim_cell` flipped a fixed high-accuracy reference symmetrically, so its "delta = 0" scenario had
E[delta] = p_d(1 - 2r) (about -3.7 pp at r .955, p_d .041).
"""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

_SPEC = importlib.util.spec_from_file_location(
    "power_sim", Path(__file__).resolve().parents[2] / "m64" / "power_sim.py")
PS = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(PS)


def _draw(seed, n, r, delta, pd, reps):
    rng = np.random.default_rng(seed)
    return [PS.sim_pairs(rng, n, r, delta, pd) for _ in range(reps)]


def test_mean_delta_is_true_delta_at_zero():
    pairs = _draw(1, 22, 0.955, 0.0, 0.041, 4000)
    mean = np.mean([(ch - ref).mean() for ref, ch in pairs])
    assert abs(mean) < 0.005


@pytest.mark.parametrize("delta", [-0.05, 0.02])
def test_mean_delta_tracks_true_delta(delta):
    pairs = _draw(2, 40, 0.80, delta, 0.15, 4000)
    mean = np.mean([(ch - ref).mean() for ref, ch in pairs])
    assert abs(mean - delta) < 0.005


def test_discordant_pair_probabilities():
    pd, delta = 0.20, -0.06
    pairs = _draw(3, 50, 0.7, delta, pd, 2000)
    ref = np.concatenate([p[0] for p in pairs])
    ch = np.concatenate([p[1] for p in pairs])
    d = ch - ref
    assert abs((d == 1).mean() - (pd + delta) / 2) < 0.006
    assert abs((d == -1).mean() - (pd - delta) / 2) < 0.006


def test_joint_table_sums_to_one_and_marginals():
    t = PS.joint_table(0.9, 0.1, -0.04)
    assert abs(sum(t.values()) - 1) < 1e-12
    assert abs(t["11"] + t["10"] - 0.9) < 1e-12          # reference accuracy
    assert abs(t["11"] + t["01"] - 0.86) < 1e-12         # challenger accuracy = r + delta


def test_infeasible_refused():
    with pytest.raises(ValueError):
        PS.joint_table(0.9, 0.03, 0.05)                  # |delta| > p_d
    with pytest.raises(ValueError):
        PS.joint_table(0.99, 0.10, 0.08)                 # challenger accuracy > 1 (needs P(01) .09 > 1 - r)
    with pytest.raises(ValueError):
        PS.joint_table(0.02, 0.10, -0.08)                # P(10) .09 > r
    with pytest.raises(ValueError):
        PS.joint_table(1.2, 0.1, 0.0)                    # marginal outside [0, 1]


def test_ceiling_reference_is_shrunk_to_feasible():
    # reference observed at 100 %: a symmetric discordance of .041 is impossible there, so the cell
    # reference accuracy is clamped to the nearest feasible value, never silently biased.
    assert abs(PS.feasible_ref(1.0, 0.041, 0.0) - (1 - 0.041 / 2)) < 1e-12
    assert PS.feasible_ref(0.955, 0.041, 0.0) == 0.955
    pairs = _draw(4, 22, PS.feasible_ref(1.0, 0.041, 0.0), 0.0, 0.041, 4000)
    assert abs(np.mean([(ch - ref).mean() for ref, ch in pairs])) < 0.005
