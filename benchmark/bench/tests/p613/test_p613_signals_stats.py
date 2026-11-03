"""B6 statistics (bench.p426_signals): primitives on hand-computed fixtures, then the A7 quality block on synthetic trees.

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.
The sheet is read structurally (see sigview.py): numbers are matched by value inside a session's subtree.
"""
from __future__ import annotations

import math

import pytest

from bench import stats
from bench.tests.p613 import a7world as W
from bench.tests.p613 import sigview as V

S1 = W.DEFAULT_IDS["s1"]
IDS8 = ["python/a1", "python/a2", "python/a3", "python/a4", "python/a5", "go/g1", "go/g2", "go/g3"]


def rows(all_ids, passing, **extra):
    """Row patches: ids in `passing` pass, the rest fail; `extra` = {id: patch} merged on top."""
    out = {rid: {"passed": rid in passing, "converged": True} for rid in all_ids}
    for rid, patch in extra.items():
        out[rid].update(patch)
    return out


# --- scenario S (hand-computed): s1 OFF passes {a1,a2,a3,a4,g1}; ON passes {a1,a2,a3,a5,g1,g2,g3} with a2 NOT converged
# (budget hit) => lenient ON 7/8, OFF 5/8; strict ON {a1,a3,a5,g1,g2,g3} = 6/8, OFF 5/8.
# strict diffs (on - off): a2 -1, a4 -1, a5 +1, g2 +1, g3 +1  => delta +1/8; 5 discordant of 8.
S_OFF = rows(IDS8, {"python/a1", "python/a2", "python/a3", "python/a4", "go/g1"})
S_ON = rows(IDS8, {"python/a1", "python/a2", "python/a3", "python/a5", "go/g1", "go/g2", "go/g3"},
            **{"python/a2": {"passed": True, "converged": False, "nonconv_kind": "budget_hit", "nonconv_flags": ["budget_hit"]}})


def strict_vec(patches, ids=IDS8):
    return [1 if (patches[i]["passed"] and patches[i].get("converged", True)) else 0 for i in ids]


def lenient_vec(patches, ids=IDS8):
    return [1 if patches[i]["passed"] else 0 for i in ids]


@pytest.fixture
def scen_s(pipeline):
    return pipeline(rows={("off", "s1"): S_OFF, ("on", "s1"): S_ON})


# ===================================================================================================== oracle anchors
# class: invariant (the reference functions the sheet must reuse behave as the contract's hand values)
def test_anchor_holm_known_values():
    assert stats.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert stats.holm([0.5]) == [0.5]
    assert stats.holm([0.2, 0.01]) == pytest.approx([0.2, 0.02])


# class: invariant
def test_anchor_zero_discordance_bound_and_mde_default():
    from bench import compare_predictor as cp
    r = V.paired([1] * 8, [1] * 8)
    assert r["degenerate"] is True and r["delta"] == 0
    assert r["discordance_upper95"] == pytest.approx(1 - 0.05 ** (1 / 8))
    assert cp._loss_bound(r) == pytest.approx(0.3123, abs=1e-3)
    assert stats.mde(8) == pytest.approx(math.sqrt(7.8489 * 0.2 / 8), rel=1e-3)


# class: invariant (self-check of the oracle used below)
def test_anchor_exact_perm_tail():
    assert V.exact_perm_tail([1, 1, 1, 1, 1]) == pytest.approx(2 / 32)
    assert V.exact_perm_tail([1, -1]) == 1.0
    assert V.exact_perm_tail([0, 0, 0]) == 1.0


# ===================================================================================================== permutation_p
# class: new-behaviour (all-zero differences: every sign vector ties T = 0 -> p = 10001 / 10001 exactly)
def test_permutation_p_all_zero_is_one(signals):
    assert signals.permutation_p([0, 0, 0, 0, 0]) == 1.0


# class: new-behaviour (n = 0 -> 1.0)
def test_permutation_p_empty_is_one(signals):
    assert signals.permutation_p([]) == 1.0


# class: new-behaviour (a single nonzero difference: |s*d| = |T| for every sign vector -> p = 1.0)
def test_permutation_p_single_item_is_one(signals):
    assert signals.permutation_p([1]) == 1.0
    assert signals.permutation_p([-1]) == 1.0


# class: new-behaviour (hand-computed exact tails; the estimate is within 6 Monte-Carlo sd)
@pytest.mark.parametrize("diffs", [
    [1, 1, 1, 1, 1],                      # 2/32
    [1, 1, 1, 1, 1, 1, 1, 0],             # all same sign among 7 nonzero: 2/128
    [1, 1],                               # 2/4
    [1, 1, 1, -1, 0, 0, 1],               # mixed
    [1, 1, 1, 1, 1, 1, 1, -1],            # 6/8 of the mass on one side
    [0.5, 0.5, 0.5, 0.5],                 # non-integer differences: 2/16
])
def test_permutation_p_matches_exact_tail(signals, diffs):
    q = V.exact_perm_tail(diffs)
    p = signals.permutation_p(diffs)
    assert abs(p - (1 + 10000 * q) / 10001) <= V.perm_tolerance(q), (p, q)


# class: new-behaviour (two-sided: the sign of every difference can be flipped)
def test_permutation_p_is_sign_symmetric(signals):
    d = [1, 1, 1, 1, 1, 1, 1, 0]
    assert signals.permutation_p(d) == signals.permutation_p([-x for x in d])


# class: new-behaviour (deterministic: seed 426 default)
def test_permutation_p_is_deterministic(signals):
    d = [1, 1, -1, 1, 0, 1, 1, 1, -1]
    assert signals.permutation_p(d) == signals.permutation_p(list(d)) == signals.permutation_p(d, iters=10000, seed=426)


# class: new-behaviour (p is in (0, 1] and never 0: the +1 correction)
def test_permutation_p_never_zero(signals):
    assert 0 < signals.permutation_p([1] * 30) <= 1.0
    assert signals.permutation_p([1] * 30) >= 1 / 10001 - 1e-15


# ===================================================================================================== geomean_ratio_ci
# class: new-behaviour (hand-computed: two ratios 2 and 8 -> point 4; each end carries 25 % of the bootstrap mass -> 2, 8)
def test_geomean_ci_two_items(signals):
    r = signals.geomean_ratio_ci([2.0, 8.0])
    assert r["n"] == 2
    assert r["point"] == pytest.approx(4.0, rel=1e-12)
    assert r["lo"] == pytest.approx(2.0, rel=1e-9) and r["hi"] == pytest.approx(8.0, rel=1e-9)


# class: new-behaviour (identical ratios: a collapsed interval)
def test_geomean_ci_identical_ratios(signals):
    r = signals.geomean_ratio_ci([1.5] * 6)
    assert r["point"] == pytest.approx(1.5, rel=1e-12) and r["lo"] == pytest.approx(1.5) and r["hi"] == pytest.approx(1.5)
    assert r["n"] == 6


# class: new-behaviour (one item)
def test_geomean_ci_single_item(signals):
    r = signals.geomean_ratio_ci([0.7])
    assert (r["n"], r["point"], r["lo"], r["hi"]) == (1, pytest.approx(0.7), pytest.approx(0.7), pytest.approx(0.7))


# class: new-behaviour (the statistic is the geometric, not the arithmetic, mean)
def test_geomean_point_is_geometric(signals):
    ratios = [0.5, 2.0, 4.0, 1.0, 0.25, 8.0]
    assert signals.geomean_ratio_ci(ratios)["point"] == pytest.approx(math.exp(sum(map(math.log, ratios)) / 6), rel=1e-12)


# class: new-behaviour (interval brackets the point inside [min, max]; deterministic)
def test_geomean_ci_bounds_and_determinism(signals):
    ratios = [0.8, 1.1, 1.4, 1.9, 2.2, 0.9, 1.3]
    a, b = signals.geomean_ratio_ci(ratios), signals.geomean_ratio_ci(list(ratios), iters=10000, seed=426)
    assert a == b
    assert min(ratios) - 1e-12 <= a["lo"] <= a["point"] <= a["hi"] <= max(ratios) + 1e-12


# ===================================================================================================== strict scoring
# class: new-behaviour (strict = passed AND converged over ALL planned slots; lenient = passed)
def test_strict_and_lenient_accuracy_per_arm(scen_s):
    _, _, sig = scen_s
    s1 = V.scope(sig, "s1")
    assert V.has_num(sig, "s1", 6 / 8, sess_tree=s1), "ON strict 6/8"
    assert V.has_num(sig, "s1", 5 / 8, sess_tree=s1), "OFF strict / lenient 5/8"
    assert V.has_num(sig, "s1", 7 / 8, sess_tree=s1), "ON lenient 7/8 (the budget-hit pass still counts leniently)"


# class: new-behaviour (a budget-hit pass is not a strict success: strict ON must not read 7/8 as its own measure)
def test_budget_hit_pass_is_not_strict(pipeline):
    _, _, sig = pipeline(rows={("on", "s1"): {"python/a1": {"converged": False, "nonconv_kind": "budget_hit",
                                                             "nonconv_flags": ["budget_hit"]}}})
    s1 = V.scope(sig, "s1")
    assert V.has_num(sig, "s1", 7 / 8, sess_tree=s1)           # ON strict 7/8
    r = V.paired([0, 1, 1, 1, 1, 1, 1, 1], [1] * 8, IDS8)
    assert V.has_num(sig, "s1", r["delta"], sess_tree=s1) and V.has_num(sig, "s1", r["lo"], sess_tree=s1)


# class: new-behaviour (a failed-but-converged slot is not strict either)
def test_failed_converged_is_not_a_success(pipeline):
    _, _, sig = pipeline(rows={("off", "s2"): {"python/b1": {"passed": False}, "go/h2": {"passed": False}}})
    assert V.has_num(sig, "s2", 6 / 8)


# class: new-behaviour (strict paired delta: paired_delta at k = 1, only delta / lo / hi read)
def test_strict_paired_delta_matches_paired_delta_k1(scen_s):
    _, _, sig = scen_s
    on, off = strict_vec(S_ON), strict_vec(S_OFF)
    assert sum(a - b for a, b in zip(on, off)) == 1
    r = V.paired(on, off, IDS8)
    s1 = V.scope(sig, "s1")
    assert r["delta"] == pytest.approx(0.125)
    for key in ("delta", "lo", "hi"):
        assert V.has_num(sig, "s1", r[key], sess_tree=s1), key


# class: new-behaviour (the paired_delta result's own verdict / directional never reach the sheet)
def test_paired_delta_verdict_fields_do_not_leak(scen_s):
    _, _, sig = scen_s
    blob = V.text(sig)
    assert '"directional"' not in blob
    assert "a_better" not in blob and "b_better" not in blob


# class: new-behaviour (never a composite / successes_per_hour)
def test_no_composite_metrics(scen_s):
    blob = V.text(scen_s[2]).lower()
    assert "successes_per_hour" not in blob and "composite" not in blob


# ===================================================================================================== MDE
# class: new-behaviour (p_d = observed discordant fraction: 5 / 8)
def test_mde_uses_observed_discordance(scen_s):
    _, _, sig = scen_s
    m, disc = V.mde_of(strict_vec(S_ON), strict_vec(S_OFF))
    assert disc == 5
    assert V.has_num(sig, "s1", m, tol=1e-6, pct=True, sess_tree=V.scope(sig, "s1"))


# class: new-behaviour (zero discordance: the default 0.20 row, said so)
def test_mde_zero_discordance_reports_default_row(pipeline):
    _, _, sig = pipeline()
    s2 = V.scope(sig, "s2")
    assert V.has_num(sig, "s2", stats.mde(8), tol=1e-6, sess_tree=s2)
    assert any("default" in s.lower() for s in V.strings(s2)) or "default" in V.text(s2).lower()


# ===================================================================================================== labels (C172 / C173)
# class: new-behaviour (CI includes 0 -> WASH, directional label; never the shown-difference label)
def test_wash_label(scen_s):
    _, _, sig = scen_s
    r = V.paired(strict_vec(S_ON), strict_vec(S_OFF), IDS8)
    assert r["lo"] <= 0 <= r["hi"]
    strs = V.strings(V.scope(sig, "s1"))
    assert V.wash(strs)
    assert not V.shown(strs)


# class: new-behaviour (lo > 0 -> shown difference; ON all pass vs OFF all fail)
def test_shown_difference_gain(pipeline):
    _, _, sig = pipeline(rows={("off", "s1"): rows(IDS8, set()), ("on", "s1"): rows(IDS8, set(IDS8))})
    r = V.paired([1] * 8, [0] * 8)
    assert r["lo"] > 0
    strs = V.strings(V.scope(sig, "s1"))
    assert V.shown(strs) and not V.wash(strs)
    assert not any("loss not ruled out" in s for s in strs), "a shown gain has loss bound 0"


# class: new-behaviour (hi < 0 -> shown difference; ON all fail)
def test_shown_difference_loss(pipeline):
    _, _, sig = pipeline(rows={("off", "s1"): rows(IDS8, set(IDS8)), ("on", "s1"): rows(IDS8, set())})
    r = V.paired([0] * 8, [1] * 8)
    assert r["hi"] < 0
    strs = V.strings(V.scope(sig, "s1"))
    assert V.shown(strs) and not V.wash(strs)
    assert V.has_num(sig, "s1", V.loss_pp(r) / 100.0, tol=1e-9, sess_tree=V.scope(sig, "s1"))


# class: new-behaviour (zero discordance: loss bound = exact 1 - 0.05^(1/n) = 31.4 pp > 10 -> "loss not ruled out above X pp")
def test_zero_discordance_loss_bound_text(pipeline):
    _, _, sig = pipeline()
    s2 = V.scope(sig, "s2")
    assert V.has_num(sig, "s2", 1 - 0.05 ** (1 / 8), tol=1e-9, sess_tree=s2)
    hits = [s for s in V.strings(s2) if "loss not ruled out above" in s]
    assert hits, "loss bound > 10 pp must say so"
    assert any(abs(v - 31.23) < 0.6 for v in V.numbers([hits]))
    assert V.wash(V.strings(s2))


# class: new-behaviour (a wash whose loss bound is <= 10 pp carries no "loss not ruled out" text: n = 40, one OFF-better item)
def test_small_loss_bound_has_no_warning(pipeline):
    ids = [f"python/p{i}" for i in range(1, 26)] + [f"go/q{i}" for i in range(1, 16)]
    on = rows(ids, set(ids) - {"python/p1"})
    off = rows(ids, set(ids))
    _, _, sig = pipeline(ids={"s1": ids}, rows={("on", "s1"): on, ("off", "s1"): off})
    on_v, off_v = strict_vec(on, ids), strict_vec(off, ids)
    r = V.paired(on_v, off_v, ids)
    assert r["lo"] <= 0 <= r["hi"] and V.loss_pp(r) <= 10.0, r
    s1 = V.scope(sig, "s1")
    assert not any("loss not ruled out" in s for s in V.strings(s1))
    assert V.wash(V.strings(s1))
    assert V.has_num(sig, "s1", r["lo"], sess_tree=s1) and V.has_num(sig, "s1", r["delta"], sess_tree=s1)


# class: new-behaviour (the label follows the CI of THIS session, not another one)
def test_labels_are_per_session(pipeline):
    _, _, sig = pipeline(rows={("off", "s1"): rows(IDS8, set()), ("on", "s1"): rows(IDS8, set(IDS8))})
    assert V.shown(V.strings(V.scope(sig, "s1")))
    assert not V.shown(V.strings(V.scope(sig, "s2")))


# ===================================================================================================== exclusive solves / edit competence
# class: new-behaviour (strict exclusive solves: ON-only and OFF-only lists)
def test_exclusive_strict_solves(scen_s):
    _, _, sig = scen_s
    lists = V.id_lists(V.scope(sig, "s1"))
    assert frozenset({"python/a5", "go/g2", "go/g3"}) in lists, "ON-only strict solves"
    assert frozenset({"python/a2", "python/a4"}) in lists, "OFF-only strict solves (a2 is not strict in ON)"


# class: new-behaviour (no exclusive solves: empty lists)
def test_no_exclusive_solves_gives_empty_lists(pipeline):
    _, _, sig = pipeline()
    assert frozenset() in V.id_lists(V.scope(sig, "s2"))


# class: new-behaviour (edit competence per arm: file_changed, test_modified, tool_bounds_rejections)
def test_edit_competence_counts(pipeline):
    # ON: test_modified on 5 items, file_changed False on 1 (7 left), rejections 4 + 4 + 3 = 11 over 3 items;
    # OFF: file_changed False on 3 items (5 left), nothing else.
    on = {f"python/a{i}": {"test_modified": True} for i in range(1, 6)}
    on["go/g1"] = {"tool_bounds_rejections": 4, "file_changed": False}
    on["go/g2"] = {"tool_bounds_rejections": 4}
    on["go/g3"] = {"tool_bounds_rejections": 3}
    off = {rid: {"file_changed": False} for rid in ("python/a2", "python/a4", "python/a5")}
    _, _, sig = pipeline(rows={("on", "s1"): on, ("off", "s1"): off})
    pool = V.numbers(V.scope(sig, "s1"))
    for want in (7, 5):                        # ON file_changed 7; ON test_modified 5 and OFF file_changed 5
        assert want in pool, want
    assert 11 in pool or 3 in pool, "tool_bounds_rejections: the total (11) or the items with a rejection (3)"


# ===================================================================================================== DNF (C235 G1)
# class: new-behaviour (a DNF slot is a non-success for its arm only; denominator stays the planned slots; labelled)
def test_dnf_counts_as_nonsuccess_with_planned_denominator(pipeline):
    _, b8, sig = pipeline(dnf={("on", "s1"): ["go/g3"]})
    p = [x for x in b8["pairs"] if x["pair"] == "s1"][0]
    assert p["accepted"] is True
    s1 = V.scope(sig, "s1")
    assert V.has_num(sig, "s1", 7 / 8, sess_tree=s1), "ON strict 7/8 (g3 is a DNF), OFF 8/8"
    r = V.paired([1, 1, 1, 1, 1, 1, 1, 0], [1] * 8, IDS8)
    assert V.has_num(sig, "s1", r["delta"], sess_tree=s1) and V.has_num(sig, "s1", r["lo"], sess_tree=s1)
    assert "transport_dnf" in V.text(s1)


# class: new-behaviour (the DNF table by arm and cause comes from chain.json)
def test_dnf_table_by_arm_and_cause(pipeline):
    _, _, sig = pipeline(dnf={("on", "s1"): ["go/g3"]})
    s1 = V.scope(sig, "s1")
    assert 1 in V.counts_at(s1, "on", "transport") or "transport" in V.text(s1)
    assert not V.counts_at(s1, "off", "transport") or all(v == 0 for v in V.counts_at(s1, "off", "transport"))


# class: new-behaviour (without a make-up run the sheet says so)
def test_makeup_sensitivity_says_none_without_makeup(pipeline):
    _, _, sig = pipeline()
    assert "no make-up run" in V.text(sig).lower()


# ===================================================================================================== Holm (m = members present)
# class: new-behaviour (significant OFF-better member: adjusted p = m * p with m = 2 in step 1; the other member's stays 1.0)
@pytest.mark.parametrize("who", ["s1", "s2"])
def test_holm_two_member_family(pipeline, who):
    ids = W.DEFAULT_IDS[who]
    on, off = rows(ids, {ids[0]}), rows(ids, set(ids))             # ON passes 1 of 8, OFF 8 of 8: 7 equal-sign differences
    _, _, sig = pipeline(rows={("on", who): on, ("off", who): off})
    q = V.exact_perm_tail([-1] * 7 + [0])                          # 2 / 128
    tol = V.perm_tolerance(q)
    p_lo, p_hi = (1 + 10000 * q) / 10001 - tol, (1 + 10000 * q) / 10001 + tol
    mine = V.numbers(V.scope(sig, who))
    pairs = [(r_, a) for r_ in mine for a in mine if p_lo <= r_ <= p_hi and abs(a - 2 * r_) < 1e-9]
    assert pairs, f"raw p near {q:.4f} and adjusted = 2 x raw expected under {who}"


# class: new-behaviour (Holm m = the members PRESENT: one accepted pair -> adjusted == raw)
def test_holm_family_of_one_when_other_pair_rejected(pipeline):
    w_leg = {("on", "s2"): {"state": "INVALID"}}
    ids = W.DEFAULT_IDS["s1"]
    _, b8, sig = pipeline(legs=w_leg, rows={("on", "s1"): rows(ids, {ids[0]}), ("off", "s1"): rows(ids, set(ids))})
    assert [p["accepted"] for p in b8["pairs"] if p["pair"] == "s2"] == [False]
    q = V.exact_perm_tail([-1] * 7 + [0])
    tol = V.perm_tolerance(q)
    mine = V.numbers(V.scope(sig, "s1"))
    window = [v for v in mine if abs(v - (1 + 10000 * q) / 10001) <= tol]
    assert window, "the raw permutation p of s1"
    # m = 1: the adjusted p IS the raw p, so no number equals twice a raw p
    assert not any(abs(a - 2 * r_) < 1e-9 for r_ in window for a in mine)


# class: new-behaviour (the family is labelled provisional while A1 is pending)
def test_holm_family_label_in_sheet(scen_s, signals):
    _, _, sig = scen_s
    assert V.HOLM_NOTE in V.text(sig) or V.HOLM_NOTE in signals.render_md(sig)


# class: new-behaviour (zero differences contribute zero: S has 3 zero diffs; p = 1.0 for 5 same-parity nonzero differences)
def test_raw_p_for_scenario_s_is_one(scen_s):
    _, _, sig = scen_s
    assert V.exact_perm_tail([0, -1, 0, -1, 1, 0, 1, 1]) == 1.0
    assert 1.0 in V.numbers(V.scope(sig, "s1"))


# ===================================================================================================== rejected pairs never enter the numbers
# class: new-behaviour (computed only from pairs B8 accepted: a rejected s1 contributes no number, its reason is listed)
def test_rejected_pair_is_excluded_and_reason_listed(pipeline):
    _, b8, sig = pipeline(legs={("on", "s1"): {"state": "INVALID"}},
                          rows={("off", "s1"): S_OFF, ("on", "s1"): S_ON})
    reason = [p for p in b8["pairs"] if p["pair"] == "s1"][0]["reasons"][0]
    assert not V.wash(V.strings(V.scope(sig, "s1")))
    assert reason in V.text(sig)
    assert V.wash(V.strings(V.scope(sig, "s2")))


# class: new-behaviour (signals honour B8: a pair marked rejected in B8 is not computed even if the files are clean)
def test_b8_acceptance_is_authoritative(make_world, verify, signals):
    w = make_world(rows={("off", "s1"): S_OFF, ("on", "s1"): S_ON})
    b8 = verify.verify_a7(w.root)
    for p in b8["pairs"]:
        if p["pair"] == "s1":
            p["accepted"] = False
            p["reasons"] = ["operator-forced test rejection"]
    sig = signals.compute_a7(w.root, b8)
    assert not V.wash(V.strings(V.scope(sig, "s1")))
    assert "operator-forced test rejection" in V.text(sig)


# class: invariant (pilot / reload are never pooled into s1 / s2: changing them leaves the session numbers untouched)
def test_pilot_and_reload_are_not_pooled(pipeline):
    ids = W.DEFAULT_IDS["pilot"]
    _, _, a = pipeline()
    _, _, b = pipeline(rows={("on", "pilot"): rows(ids, set()), ("off", "reload"): rows(ids, set(ids[:2]))})
    assert V.text(V.scope(a, "s1")) == V.text(V.scope(b, "s1"))
    assert V.text(V.scope(a, "s2")) == V.text(V.scope(b, "s2"))
