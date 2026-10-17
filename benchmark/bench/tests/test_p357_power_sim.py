"""P357: the power sim's paired outcomes must have E[delta] = the requested true delta (through `run()`).

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


def old_sim_cell(rng, ref, delta, pd):
    """Verbatim copy of the pre-P357 generator (kept only to prove the tests detect it)."""
    n = len(ref)
    ch = ref.copy()
    flip = rng.random(n) < pd
    ch[flip] = 1 - ch[flip]
    k = int(round(-delta * n))
    if k > 0:
        idx = np.flatnonzero(ch == 1)
        if len(idx):
            ch[rng.choice(idx, size=min(k, len(idx)), replace=False)] = 0
    return ch


def old_gen_cells(rng, refs, delta, pd):
    return {k: old_sim_cell(rng, ref, delta, pd) - ref for k, ref in refs.items()}


REFS = {("python", "s1"): np.array([1.0] * 21 + [0.0]),     # r = .955
        ("python", "s2"): np.array([1.0] * 21 + [0.0]),
        ("go", "s1"): np.ones(21), ("go", "s2"): np.ones(21)}  # r = 1


def _collect(monkeypatch, pd, delta, reps, gen=None):
    monkeypatch.setattr(PS, "B", 10)                       # bootstrap is irrelevant to generation; keep it fast
    if gen is not None:
        monkeypatch.setattr(PS, "gen_cells", gen)
    rng = np.random.default_rng(7)
    got = []
    for _ in range(reps):
        cap = {}
        PS.run(pd, delta, rng, REFS, capture=cap)
        got.append(cap)
    return got


def _assert_unbiased(got, pd, delta, tol=0.009):
    for key in REFS:
        d = np.concatenate([g[key] for g in got])
        assert abs(d.mean() - delta) < tol, (key, d.mean())
        assert abs((d == 1).mean() - (pd + delta) / 2) < tol
        assert abs((d == -1).mean() - (pd - delta) / 2) < tol


@pytest.mark.parametrize("pd,delta", [(0.041, 0.0), (0.182, -0.05), (0.10, 0.03)])
def test_run_generates_requested_delta_and_split(monkeypatch, pd, delta):
    got = _collect(monkeypatch, pd, delta, 600)
    _assert_unbiased(got, pd, delta)
    assert all(len(g[k]) == len(REFS[k]) for g in got for k in REFS)      # exact cell n
    assert all(set(np.unique(g[k])) <= {-1.0, 0.0, 1.0} for g in got for k in REFS)


def test_old_generator_is_detected_through_run(monkeypatch):
    """Red against the pre-P357 behaviour: at delta = 0, r near 1, E[delta] was about -3.7 pp / -4.1 pp."""
    got = _collect(monkeypatch, 0.041, 0.0, 600, gen=old_gen_cells)
    d = np.concatenate([g[("go", "s1")] for g in got])
    assert d.mean() < -0.03                                            # the old bias is real
    with pytest.raises(AssertionError):
        _assert_unbiased(got, 0.041, 0.0)                              # and the behavioural check catches it


def test_infeasible_refused():
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError):
        PS.sim_diffs(rng, 20, -0.05, 0.041)                # |delta| > p_d
    with pytest.raises(ValueError):
        PS.sim_diffs(rng, 20, 0.0, 1.2)


def test_report_wiring(monkeypatch, tmp_path):
    monkeypatch.setattr(PS, "SIMS", 2)
    monkeypatch.setattr(PS, "B", 10)
    monkeypatch.setattr(PS, "observed_discordance",
                        lambda: (0.041, 7, 172, [("m", "python", "s1", 1, 22, 0.955)]))
    monkeypatch.setattr(PS, "load", lambda model, lang, tag, sess: {f"i{i}": 1 for i in range(21)})
    out = tmp_path / "ps.md"
    PS.main(out_path=out)
    text = out.read_text()
    assert "7/172 = 0.041" in text and "INVALID" in text and "Owed" in text
    assert "| 0.182 | +0.00 |" in text and "| 0.303 | -0.10 |" in text
    assert "infeasible (delta beyond p_d)" in text
