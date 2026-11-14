"""M76 B7 (spec v1.3) — adopted finding 3: `recheck` includes dispersion in the inside / outside decision, never mixes cells
of different concentration, flags an unrealisable observed nuisance, and the flag `unsafe_at_observed` is renamed
`unsafe_on_extended_grid`; plus the v1.3 rule that A8's applied alpha* is min(0.001, re-calibrated).

Reduced replications (reps=60) for the re-calibration: only the record's logic is asserted, never a safety rate.
Class: (a) specification / docstring-stated behaviour; (c) record keys are not in the specification (read by name from
the candidate's documented record).
"""
import inspect
import json
import random
import re

import pytest

REPS = 60


def _recheck(n16, x, out, axis="A8"):
    from bench import m76_sim
    sig = inspect.signature(m76_sim.recheck)
    kw = {}
    for name in sig.parameters:
        if re.fullmatch(r"(n_?)?rep(lication)?s?|n_?reps?|replications", name):
            kw[name] = REPS
        if re.fullmatch(r"out(_?dir)?|output(_?dir)?", name):
            kw[name] = str(out)
    return m76_sim.recheck(axis, n16, x, **kw)


def _rows(m_cells, disc, *, correlated, n=80, sessions=("s1", "s2"), seed=7):
    """N16 rows with pass rate m_cells (fraction of item-sessions) and X rows with `disc` of item-sessions discordant
    (drawn from the N16-pass cells, X worse). `correlated`: item-level propensity 0.05 / 0.95 (sessions agree);
    otherwise sessions are independent."""
    rng = random.Random(seed)
    n16 = {}
    for i in range(n):
        if correlated:
            p = 0.95 if i % 2 == 0 else 0.05
        else:
            p = m_cells
        n16[i] = {s: int(rng.random() < p) for s in sessions}
    ones = [(i, s) for i in n16 for s in sessions if n16[i][s] == 1]
    rng.shuffle(ones)
    x = {i: dict(n16[i]) for i in n16}
    for (i, s) in ones[:int(round(disc * n * len(sessions)))]:
        x[i][s] = 0
    return n16, x


def _nuisance(n16, x):
    ids = sorted(n16)
    cells = [(i, s) for i in ids for s in n16[i]]
    m = sum(n16[i][s] for i, s in cells) / len(cells)
    d = sum(n16[i][s] != x[i][s] for i, s in cells) / len(cells)
    return m, d


# DELIVERY 6: `test_dispersion_only_case_is_outside_and_reports_concentration` and
# `test_dispersion_only_case_recalibrates_every_cell_at_the_observed_concentration` were DELETED: their rows (item propensity
# 0.95 / 0.05, kappa-hat 0.19) are unrealisable under the data model, which spec v1.4 routes to the flags without
# recalibration. Every assertion they made (inside False, a "concentration" reason, kappa-hat below the committed 4,
# extended grid present, recalibrated_all_cells True, new_cells_kappa == observed kappa) is made, on realisable rows
# (propensity 0.75 / 0.25), by `test_m76_b7_fe_fix_final.py::test_moderate_dispersion_is_outside_and_recalibrates_every_cell_at_the_observed_kappa`.


def _moderate_rows(seed=7, n=80, disc=0.20):
    """Dispersed but realisable: item propensity 0.75 / 0.25 (kappa-hat about 1-3, below the committed 4)."""
    rng = random.Random(seed)
    n16 = {i: {s: int(rng.random() < (0.75 if i % 2 == 0 else 0.25)) for s in ("s1", "s2")} for i in range(n)}
    ones = [(i, s) for i in n16 for s in n16[i] if n16[i][s] == 1]
    rng.shuffle(ones)
    x = {i: dict(n16[i]) for i in n16}
    for (i, s) in ones[:int(round(disc * n * 2))]:
        x[i][s] = 0
    return n16, x


def test_dispersion_only_case_never_loosens_a8_alpha(tmp_path):  # (a) v1.3: applied = min(0.001, new); never above 0.001
    """AMENDED (delivery 6): rows are now the realisable dispersion case (propensity 0.75 / 0.25) so recalibration runs."""
    n16, x = _moderate_rows()
    rec = _recheck(n16, x, tmp_path)
    assert rec["inside"] is False and rec["observed_unrealisable"] is False and rec["recalibration_attempted"] is True
    assert rec["alpha_star_applied"] is not None and rec["alpha_star_applied"] <= 0.001 + 1e-12
    new = rec["new_alpha_star"]
    if new is not None:
        assert rec["alpha_star_applied"] == pytest.approx(min(0.001, new))
    else:
        assert rec["alpha_star_applied"] == pytest.approx(0.001) and rec["unsafe_on_extended_grid"] is True


def test_homogeneous_rows_inside_keep_the_committed_alpha(tmp_path):  # (a) control: nothing outside
    n16, x = _rows(0.5, 0.20, correlated=False)
    m, d = _nuisance(n16, x)
    assert 0.3 <= m <= 0.9 and 0.10 <= d <= 0.30, (m, d)
    rec = _recheck(n16, x, tmp_path)
    assert rec["inside"] is True and rec["outside_reasons"] == []
    from bench.m76_rule import axis_plan
    assert rec["alpha_star_applied"] == pytest.approx(axis_plan("A8")["alpha_star"]) == pytest.approx(0.001)
    assert rec["unsafe_on_extended_grid"] is False and rec["operator_review"] is False


def test_unrealisable_observed_nuisance_is_flagged_for_the_operator(tmp_path):  # (c)
    """Pass rate ~0.88 with 30 % discordance: D/2 = 0.15 exceeds min(m, 1 - m), so the data model cannot realise it; its own
    cell is skipped and cannot inform alpha*, so the record must say so."""
    rng = random.Random(9)
    n = 80
    n16 = {i: {s: int(rng.random() < 0.88) for s in ("s1", "s2")} for i in range(n)}
    x = {i: dict(n16[i]) for i in n16}
    ones = [(i, s) for i in n16 for s in n16[i] if n16[i][s] == 1]
    rng.shuffle(ones)
    for (i, s) in ones[:int(0.30 * n * 2)]:
        x[i][s] = 0
    m, d = _nuisance(n16, x)
    assert 0.3 <= m <= 0.9 and 0.10 <= d <= 0.30 and d / 2 > min(m, 1 - m), (m, d)
    rec = _recheck(n16, x, tmp_path)
    assert rec["observed_unrealisable"] is True
    assert rec["operator_review"] is True
    assert rec["inside"] is False
    assert rec["observed_infeasible_reasons"]


def test_record_uses_the_renamed_flag_and_never_the_old_one(tmp_path):  # (a) finding 3 rename
    n16, x = _rows(0.5, 0.20, correlated=False)
    rec = _recheck(n16, x, tmp_path)
    assert "unsafe_on_extended_grid" in rec
    assert "unsafe_at_observed" not in rec
    files = list(tmp_path.glob("recheck-*.json"))
    assert files
    on_disk = json.loads(files[0].read_text())
    assert "unsafe_on_extended_grid" in on_disk and "unsafe_at_observed" not in on_disk


def test_recheck_record_identical_for_opposite_arm_effects_with_dispersion_logic(tmp_path):  # (a) never reads the arm effect
    rng = random.Random(7)
    n = 80
    n16 = {i: {s: int(rng.random() < (0.95 if i % 2 == 0 else 0.05)) for s in ("s1", "s2")} for i in range(n)}
    ones = [(i, s) for i in n16 for s in n16[i] if n16[i][s] == 1]
    zeros = [(i, s) for i in n16 for s in n16[i] if n16[i][s] == 0]
    k = 32
    x_loss = {i: dict(n16[i]) for i in n16}
    x_gain = {i: dict(n16[i]) for i in n16}
    for (i, s) in ones[:k]:
        x_loss[i][s] = 0
    for (i, s) in zeros[:k]:
        x_gain[i][s] = 1
    ra = _recheck(n16, x_loss, tmp_path / "a")
    rb = _recheck(n16, x_gain, tmp_path / "b")
    assert ra == rb
