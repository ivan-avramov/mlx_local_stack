"""B6 Wave 1 definitions on hand-computed fixtures (contract "B6 - Wave 1 definitions"): one scenario "S", expected values derived
here from the world's own rows (independent of the code under test) with `bench.stats` / `bench.compare_predictor` oracles.

Class of every test is stated in the comment above it: reproduces-failure | invariant | new-behaviour.
SIGNALS.json key names are not pinned: numbers are located by value inside the subtree under the axis key (`A1`, `A2`, ...).
"""
from __future__ import annotations

import math
import re

import pytest

from bench.tests.p613 import sigview as SV
from bench.tests.p613s2 import w1view as V
from bench.tests.p613s2 import wave1world as WW

D = WW.draft
NC = dict(WW.NONCONV)


def a(i):
    return f"test/algebra/{i}.json"


S_SPEC = dict(n_math=8, rows={
    ("math500", "off", "b1"): {a(7): {"ok": False}, a(8): {"ok": False}, a(5): {"decode_tps": None}},
    ("math500", "on", "b1"): {a(8): {"ok": False}, a(3): NC, a(1): {"draft": D("on", 200, 100), "decode_tps": 60.0},
                              a(2): {"decode_tps": 10.0, "content": "A different derivation. \\boxed{7}"}},
    ("math500", "off", "b2"): {a(16): {"ok": False}},
    ("math500", "on", "b2"): {a(14): {"ok": False}, a(15): {"ok": False}, a(16): {"ok": False}, a(9): {"draft": D("on", 50, 50)},
                              a(10): {"decode_tps": 24.0}, a(11): {"decode_tps": 40.0}, a(12): {"decode_tps": 0.0}},
    ("cjudge", "on", "b1"): {"dom-02": {"converged": False, "nonconv_kind": "max_tokens", "finish_reason": "length",
                                        "completion_tokens": 102400}},
    ("cjudge", "on", "b2"): {"dom-03": {"draft": D("on", 100, 40)}},
    ("vision", "on", "b1"): {"cocoval2017-000": {"verdict": "FAIL"}},
    ("vision", "on", "b2"): {"cocoval2017-002": {"draft": D("on", 100, 50)},
                             "cocoval2017-003": {"converged": False, "finish_reason": "length"}},
    ("reasoning", "on", "b1"): {128000000: {"draft": D("on", 200, 120)}, 128000001: {"content": "Tracing it differently."}},
    ("reasoning", "on", "b2"): {128000003: {"budget_hit": True, "score": 0.0}},
})


@pytest.fixture(scope="module")
def S(scenario):
    """A thunk: the scenario is built inside the test body, so a missing interface FAILS the test (not a fixture error)."""
    return lambda: scenario("S", **S_SPEC)


# --------------------------------------------------------------------------------------------------- oracles from the rows
def a1_scores(w, arm, block):
    out = {}
    for r in w.read_rows("math500", arm, block):
        ok = re.search(r"\\boxed\{([^}]*)\}", r["content"]).group(1) == r["answer_gold"]
        out[r["id"]] = (1.0 if ok else 0.0, 1.0 if ok and r["converged"] is True else 0.0)
    return out


def vecs(w, block, which):
    on, off = a1_scores(w, "on", block), a1_scores(w, "off", block)
    ids = sorted(on)
    return ids, [on[i][which] for i in ids], [off[i][which] for i in ids]


def both(w, which):
    i1, on1, off1 = vecs(w, "b1", which)
    i2, on2, off2 = vecs(w, "b2", which)
    return i1 + i2, on1 + on2, off1 + off2


def tps_ratios(w, kind, block, key=lambda r: r["id"]):
    on = {key(r): r for r in w.read_rows(kind, "on", block)}
    off = {key(r): r for r in w.read_rows(kind, "off", block)}
    out, dropped = [], []
    for k in sorted(on):
        a_, b_ = on[k]["decode_tps"], off[k]["decode_tps"]
        if not (isinstance(a_, (int, float)) and isinstance(b_, (int, float)) and a_ > 0 and b_ > 0):
            dropped.append(k)
            continue
        out.append(a_ / b_)
    return out, dropped


def accept(rows):
    n = sum(r["draft"]["draft_n"] for r in rows)
    k = sum(r["draft"]["draft_n_accepted"] for r in rows)
    return k / n, k, n


# ===================================================================================================================== A1
# class: new-behaviour (per arm and block: acc (lenient), acc_strict@81920 over the planned items, conv %; both blocks)
def test_a1_per_arm_accuracy_strict_and_conv(S):
    w, b8, sig = S()
    for block in ("b1", "b2"):
        for arm in WW.ARMS:
            sc = a1_scores(w, arm, block)
            for which in (0, 1):
                assert V.axis_has(sig, "A1", sum(v[which] for v in sc.values()) / 8), (block, arm, which)
    for arm in WW.ARMS:
        for which in (0, 1):
            tot = sum(v[which] for b in ("b1", "b2") for v in a1_scores(w, arm, b).values()) / 16
            assert V.axis_has(sig, "A1", tot), (arm, which, tot)
    assert V.axis_has(sig, "A1", 0.875)       # ON b1 conv 7 / 8 (item 3 is a budget hit)
    assert "budget_hit" in V.axis_text(sig, "A1")


# class: new-behaviour (strict != lenient when a correct answer is a budget hit: ON b1 lenient 7/8, strict 6/8; the DNF is not an exclusion)
def test_a1_strict_differs_from_lenient_on_a_budget_hit(S):
    w, _, _ = S()
    _, on_l, off_l = vecs(w, "b1", 0)
    _, on_s, off_s = vecs(w, "b1", 1)
    assert sum(on_l) == 7 and sum(on_s) == 6 and sum(off_l) == sum(off_s) == 6


# class: new-behaviour (paired ON - OFF per block and both blocks, strict and lenient, from stats.paired_delta at k = 1, dict inputs)
@pytest.mark.parametrize("which", (0, 1))
@pytest.mark.parametrize("block", ("b1", "b2", "both"))
def test_a1_paired_delta_matches_paired_delta_k1(S, block, which):
    w, _, sig = S()
    ids, on, off = both(w, which) if block == "both" else vecs(w, block, which)
    r = SV.paired(on, off, ids)
    for key in ("delta", "lo", "hi"):
        assert V.axis_has(sig, "A1", r[key]), (block, which, key, r[key])


# class: new-behaviour (labels C172: CI excludes 0 -> shown difference, else WASH directional; never the paired_delta verdict text)
def test_a1_labels_follow_the_ci(S):
    w, _, sig = S()
    strs = SV.strings(V.axis_tree(sig, "A1"))
    labels = set()
    for block in ("b1", "b2", "both"):
        for which in (0, 1):
            ids, on, off = both(w, which) if block == "both" else vecs(w, block, which)
            labels.add(SV.label_of(SV.paired(on, off, ids)))
    assert (SV.LABEL_WASH in labels) == SV.wash(strs)
    assert (SV.LABEL_SHOWN in labels) == SV.shown(strs)
    blob = V.sheet_text(sig)
    assert "a_better" not in blob and "b_better" not in blob and '"directional"' not in blob


# class: new-behaviour (loss bound = compare_predictor._loss_bound in pp; > 10 pp -> "loss not ruled out above X pp")
@pytest.mark.parametrize("block", ("b1", "b2", "both"))
def test_a1_loss_bound(S, block):
    w, _, sig = S()
    ids, on, off = both(w, 1) if block == "both" else vecs(w, block, 1)
    r = SV.paired(on, off, ids)
    pp = SV.loss_pp(r)
    assert V.axis_has(sig, "A1", pp / 100.0), (block, pp)
    if pp > 10.0:
        assert any("loss not ruled out above" in s for s in SV.strings(V.axis_tree(sig, "A1")))


# class: new-behaviour (MDE = stats.mde(n, observed discordance fraction); n is the block size or the both-block size)
@pytest.mark.parametrize("block", ("b1", "b2", "both"))
def test_a1_mde_uses_the_observed_discordance(S, block):
    w, _, sig = S()
    ids, on, off = both(w, 1) if block == "both" else vecs(w, block, 1)
    mde, disc = SV.mde_of(on, off)
    assert disc > 0
    assert V.axis_has(sig, "A1", mde, tol=2e-3), (block, mde)


# class: new-behaviour (exclusive solves: ON-only and OFF-only STRICT solves as id lists, per block)
def test_a1_exclusive_solves(S):
    w, _, sig = S()
    lists = SV.id_lists(V.axis_tree(sig, "A1"))
    assert frozenset({a(7)}) in lists                  # b1 ON-only (OFF wrong, ON right)
    assert frozenset({a(3)}) in lists                  # b1 OFF-only (ON's answer is a budget hit: not a strict solve)
    assert frozenset({a(14), a(15)}) in lists          # b2 OFF-only
    assert frozenset() in lists                        # b2 ON-only: none


# class: new-behaviour (permutation p = the step-1 permutation_p on the both-block STRICT differences sorted by (block, id))
def test_a1_permutation_p_on_both_block_strict_differences(S):
    w, _, sig = S()
    ids, on, off = both(w, 1)
    diffs = [x - y for x, y in zip(on, off)]
    assert V.axis_has(sig, "A1", V.perm_p(diffs), tol=1e-4)
    q = SV.exact_perm_tail(diffs) if len(diffs) <= 16 else None
    assert abs(V.perm_p(diffs) - q) <= SV.perm_tolerance(q)      # oracle sanity: MC estimate of the exact tail


# ===================================================================================================== family (Holm m = 3)
# class: new-behaviour (mechanical family {A1 both blocks, A7-s1, A7-s2}: stats.holm over the three raw p, m = 3, label "complete")
def test_family_is_complete_with_m_3(S):
    w, _, sig = S()
    ids, on, off = both(w, 1)
    p_a1 = V.perm_p([x - y for x, y in zip(on, off)])
    adj = V.holm([p_a1, 1.0, 1.0])
    fam = SV.subtree(sig, "family")
    pool = SV.numbers(fam)
    assert fam, "the sheet has a family section"
    assert V.has(pool, 3.0) and V.has(pool, p_a1, 1e-4)
    for x in adj:
        assert V.has(pool, x, 1e-4), (adj, pool)
    txt = SV.text(fam).lower()
    assert "complete" in txt and "incomplete" not in txt
    assert "a1" in txt and "s1" in txt and "s2" in txt


# class: new-behaviour (A2 / A3 / A4 / M1 are not family members: no panel-free test exists for them)
def test_family_has_exactly_three_members(S):
    _, _, sig = S()
    txt = SV.text(SV.subtree(sig, "family")).lower()
    for ax in ("a2", "a3", "a4", "m1"):
        assert f'"{ax}' not in txt and f" {ax}" not in txt and f"-{ax}" not in txt, ax


# class: new-behaviour (the A7 raw p in the family is the step-1 computation: compute_a7 on the A7 member of B8)
def test_family_a7_raw_p_is_the_step1_value(S, signals):
    w, b8, sig = S()
    a7 = signals.compute_a7(w.p426, b8["axes"]["A7"])
    raw = [a7["sessions"][s]["permutation_p"] for s in ("s1", "s2")]
    pool = SV.numbers(SV.subtree(sig, "family"))
    assert all(V.has(pool, p, 1e-9) for p in raw)


# ======================================================================================================================= speed
# class: new-behaviour (A1 decode ratio ON / OFF per key: geomean + item-bootstrap CI via geomean_ratio_ci, per block and both blocks;
#   keys sorted (block, key); a key with a missing / non-positive rate in either arm is dropped and listed)
def test_a1_speed_geomean_and_dropped_keys(S, signals):
    w, _, sig = S()
    r1, d1 = tps_ratios(w, "math500", "b1")
    r2, d2 = tps_ratios(w, "math500", "b2")
    assert d1 == [a(5)] and d2 == [a(12)]
    for ratios in (r1, r2, r1 + r2):
        ci = signals.geomean_ratio_ci(ratios)
        for k in ("point", "lo", "hi"):
            assert V.axis_has(sig, "A1", ci[k], tol=2e-3), (k, ci)
    txt = V.axis_text(sig, "A1")
    assert a(5) in txt and a(12) in txt, "the dropped keys are listed"


# class: new-behaviour (A1 acceptance = sum accepted / sum proposed over ON rows (ratio of sums), per block and both blocks)
def test_a1_acceptance_is_a_ratio_of_sums(S):
    w, _, sig = S()
    r1 = w.read_rows("math500", "on", "b1")
    r2 = w.read_rows("math500", "on", "b2")
    for rows in (r1, r2, r1 + r2):
        frac, _, _ = accept(rows)
        assert V.axis_has(sig, "A1", frac, tol=1e-4)
    mean_of_ratios = sum(r["draft"]["draft_n_accepted"] / r["draft"]["draft_n"] for r in r1) / len(r1)
    assert abs(mean_of_ratios - accept(r1)[0]) > 5e-3, "the fixture tells ratio-of-sums from mean-of-ratios"
    assert V.axis_has(sig, "A1", 660) and V.axis_has(sig, "A1", 900), "the counts are printed beside the fraction"


# class: new-behaviour (leg wall = ended - started seconds per leg (naive local), descriptive)
@pytest.mark.parametrize("kind", WW.KINDS)
def test_leg_wall_seconds(S, kind):
    _, _, sig = S()
    pool = SV.numbers([sig])
    for arm in WW.ARMS:
        for block in WW.BLOCKS:
            assert V.has(pool, float(WW.wall_seconds(kind, arm, block)), 1e-6), (kind, arm, block)


# ======================================================================================================================= A2
# class: new-behaviour (A2: mechanical quality is N/A, labelled "panel only (step 3)"; per arm conv %, nonconv_kinds, errors)
def test_a2_panel_only_and_convergence(S):
    _, _, sig = S()
    txt = V.axis_text(sig, "A2")
    assert "panel only (step 3)" in txt
    assert V.axis_has(sig, "A2", 2 / 3) and "max_tokens" in txt
    assert V.axis_has(sig, "A2", 1.0)          # OFF 100 % / ON b2 100 %


# class: new-behaviour (A2 has no mechanical accuracy and is never tested: no permutation / Holm / wash text)
def test_a2_is_never_tested(S):
    _, _, sig = S()
    txt = V.axis_text(sig, "A2").lower()
    for word in ("permutation", "holm", "wash", "shown difference", "acc_strict"):
        assert word not in txt, word


# class: new-behaviour (A2 acceptance per block and both blocks (ratio of sums); decode ratio per block)
def test_a2_acceptance_and_speed(S, signals):
    w, _, sig = S()
    r1, r2 = w.read_rows("cjudge", "on", "b1"), w.read_rows("cjudge", "on", "b2")
    for rows in (r1, r2, r1 + r2):
        assert V.axis_has(sig, "A2", accept(rows)[0], tol=1e-4)
    assert V.axis_has(sig, "A2", 1.5, tol=2e-3)         # every A2 ratio is 30 / 20


# ======================================================================================================================= A3
# class: new-behaviour (A3: self-pass counts per arm, labelled "self-check, lenient, descriptive"; conv % of turn 1)
def test_a3_self_pass_counts_and_label(S):
    w, _, sig = S()
    txt = V.axis_text(sig, "A3").lower()
    assert "self-check" in txt and "lenient" in txt and "descriptive" in txt
    pool = V.axis_pool(sig, "A3")
    assert V.has(pool, 1.0) and V.has(pool, 2.0)               # ON b1 1 / 2 self-PASS, the rest 2 / 2
    assert V.axis_has(sig, "A3", 0.5)                          # ON b2 conv 1 / 2


# class: new-behaviour (A3 acceptance counts turn 1 ONLY: b1 144/200, b2 122/200, both 266/400; turn 2 would give 224/400)
def test_a3_acceptance_is_turn_one_only(S):
    w, _, sig = S()
    r1, r2 = w.read_rows("vision", "on", "b1"), w.read_rows("vision", "on", "b2")
    for rows in (r1, r2, r1 + r2):
        assert V.axis_has(sig, "A3", accept(rows)[0], tol=1e-4)
    assert not V.axis_has(sig, "A3", (144 + 80) / 400, tol=1e-4)


# class: new-behaviour (A3 decode ratio uses the turn-1 decode_tps (the ratio is 30 / 20 on every row))
def test_a3_decode_ratio(S):
    _, _, sig = S()
    assert V.axis_has(sig, "A3", 1.5, tol=2e-3)


# ======================================================================================================================= A4
# class: new-behaviour (A4 descriptive: per arm and block the draws (task seed, score, budget_hit, finish_reason); strict draw count)
def test_a4_draws_and_strict_counts(S):
    w, _, sig = S()
    txt = V.axis_text(sig, "A4")
    for s in (128000000, 128000001, 128000002, 128000003):
        assert str(s) in txt
    assert "budget_hit" in txt and "stop" in txt
    pool = V.axis_pool(sig, "A4")
    assert V.has(pool, 1.0) and V.has(pool, 2.0)              # strict draws: ON b2 1 / 2, all others 2 / 2


# class: new-behaviour (A4 is never tested: no permutation / Holm / wash / shown-difference text, no family membership)
def test_a4_is_never_tested(S):
    _, _, sig = S()
    txt = V.axis_text(sig, "A4").lower()
    for word in ("permutation", "holm", "wash", "shown difference", "paired_delta"):
        assert word not in txt, word


# class: new-behaviour (A4 acceptance per block and both: b1 300/400, b2 360/400, both 660/800; equals the leg's acceptance_pooled)
def test_a4_acceptance(S):
    w, _, sig = S()
    r1, r2 = w.read_rows("reasoning", "on", "b1"), w.read_rows("reasoning", "on", "b2")
    for rows in (r1, r2, r1 + r2):
        assert V.axis_has(sig, "A4", accept(rows)[0], tol=1e-4)
    assert abs(accept(r1)[0] - 0.75) < 1e-12 and abs(accept(r2)[0] - 0.9) < 1e-12


# class: new-behaviour (A4 decode ratio per draw (keyed by task seed): geomean + CI per block and both blocks)
def test_a4_speed_per_draw(S, signals):
    w, _, sig = S()
    r1, _ = tps_ratios(w, "reasoning", "b1", key=lambda r: r["seed"])
    r2, _ = tps_ratios(w, "reasoning", "b2", key=lambda r: r["seed"])
    assert r1 == [1.5, 1.5] and r2 == [1.5, 1.5]
    ci = signals.geomean_ratio_ci(r1 + r2)
    assert V.axis_has(sig, "A4", ci["point"], tol=2e-3)


# ======================================================================================================================= M1
# class: new-behaviour (M1 per leg: the three peaks in bytes and GB (bytes / 1e9, 3 dp), and the rates)
def test_m1_peaks_bytes_and_gb(S):
    _, _, sig = S()
    pool = V.axis_pool(sig, "M1")
    for (arm, block), peaks in WW.M1_PEAKS.items():
        for v in peaks:
            assert any(abs(p - v) < 0.5 for p in pool), (arm, block, v)
            assert any(abs(p - round(v / 1e9, 3)) < 6e-4 for p in pool), (arm, block, v / 1e9)
    for rate in set(WW.M1_RATES.values()):
        assert any(abs(p - rate) < 1e-3 for p in pool), rate


# class: new-behaviour (M1 ON - OFF per block and the mean of both blocks, per peak)
def test_m1_on_minus_off(S):
    _, _, sig = S()
    pool = V.axis_pool(sig, "M1")
    off, on1, on2 = WW.M1_PEAKS[("off", "b1")], WW.M1_PEAKS[("on", "b1")], WW.M1_PEAKS[("on", "b2")]
    for i in range(3):
        d1, d2 = on1[i] - off[i], on2[i] - off[i]
        for d in (d1, d2, (d1 + d2) / 2):
            assert any(abs(p - d) < 0.51 for p in pool), (i, d)
    assert any(abs(p - 0.314) < 6e-4 for p in pool), "prefill ON - OFF 0.314 GB"


# class: new-behaviour (M1 decode ratio ON / OFF per block (descriptive); acceptance is "not recorded")
def test_m1_decode_ratio_and_acceptance_not_recorded(S):
    _, _, sig = S()
    pool = V.axis_pool(sig, "M1")
    for block in WW.BLOCKS:
        r = WW.M1_RATES[("on", block)] / WW.M1_RATES[("off", block)]
        assert any(abs(p - r) < 2e-3 for p in pool), (block, r)
    assert "not recorded" in V.axis_text(sig, "M1").lower()


# class: new-behaviour (M1 is never tested: no p-value, no family membership)
def test_m1_is_never_tested(S):
    _, _, sig = S()
    txt = V.axis_text(sig, "M1").lower()
    for word in ("permutation", "holm", "wash"):
        assert word not in txt, word


# =============================================================================================================== identity counts
# class: new-behaviour (identity, for step 3: per axis and block the count of `identical` keys over keys, printed)
def test_identity_counts_are_printed(S):
    w, b8, sig = S()
    exp = {}
    for kind in ("math500",):
        for block in ("b1", "b2"):
            on = {r["id"]: r["content"] for r in w.read_rows(kind, "on", block)}
            off = {r["id"]: r["content"] for r in w.read_rows(kind, "off", block)}
            exp[block] = sum(1 for k in on if on[k] == off[k])
    assert exp == {"b1": 6, "b2": 6}
    pool = V.axis_pool(sig, "A1")
    assert V.has(pool, 6.0) and V.has(pool, 12.0)
    # amended (delivery 3): the counts may sit in a top-level identity section ("per axis and block ... printed"), not inside each axis
    ident = SV.subtree(sig, "identity")
    assert ident, "the sheet has an identity section (or per-axis identity counts)"
    pool_i = SV.numbers(ident)
    assert V.has(pool_i, 6.0) and V.has(pool_i, 8.0)
    for axis in ("A1", "A2", "A3", "A4"):
        assert axis.lower() in SV.text(ident).lower() or "identical" in V.axis_text(sig, axis).lower(), axis


# =============================================================================================================== rejected pairs
# class: new-behaviour (only B8-accepted pairs enter the sheet: a rejected ON b1 pair contributes no number, and the sheet says so)
def test_rejected_pair_never_enters_the_sheet(scenario):
    # amended (delivery 3): n = 9 per block, so the rejected block's sentinels (ON 4/9 and the delta 4/9 - 1) cannot collide with a value of the
    # accepted block (OFF 8/9, ON 9/9, delta 1/9, CI ends at multiples of 1/9)
    spec = dict(n_math=9, rows={("math500", "on", "b1"): {a(i): {"ok": False} for i in (1, 2, 3, 4, 5)},
                                ("math500", "off", "b2"): {a(18): {"ok": False}}},
                legs={("math500", "on", "b1"): {"verdict": "INVALID", "problems": ["x"]}})
    w, b8, sig = scenario("rejected", **spec)
    assert [(p["kind"], V.digit(p["block"])) for p in V.rejected(b8)] == [("math500", "1")]
    txt = V.axis_text(sig, "A1")
    assert "rejected" in txt.lower()
    assert not V.axis_has(sig, "A1", 4 / 9, tol=1e-3), "ON b1 accuracy 4/9 comes from the rejected pair"
    assert not V.axis_has(sig, "A1", 4 / 9 - 1.0, tol=1e-3), "its paired delta -5/9 as well"
    assert V.axis_has(sig, "A1", 8 / 9, tol=1e-3)          # b2 (accepted) still enters: OFF 8/9


# class: new-behaviour (coverage lists excluded members: smoke legs, archive/ attempts (superseded), invalid legs)
def test_coverage_lists_smokes_archive_and_invalid(scenario):
    spec = dict(n_math=8, legs={("math500", "on", "b1"): {"verdict": "INVALID", "problems": ["x"]}})
    w, b8, sig = scenario("coverage", **spec)
    cov = SV.text(SV.subtree(sig, "coverage"))
    assert "math500-p426s2-on-smoke" in cov and "m1-p426s2-off-smoke" in cov
    assert "m1-p426s2-off-smoke.attempt1-fork-venv" in cov and "superseded" in cov.lower()
    assert "math500-p426s2-on-b1" in cov and "invalid" in cov.lower()
    assert "pending (step 2)" not in cov


# ===================================================================================================== rule 4 in the sheet
# class: new-behaviour (one power-invalid block: the pair stays in the sheet, labelled power-invalid, its speed is "descriptive, not order-balanced")
def test_single_valid_block_is_descriptive_not_order_balanced(scenario):
    w, b8, sig = scenario("PI", legs={("math500", "on", "b2"): {"speed_valid": False, "speed_problems": ["power"]}})
    txt = V.axis_text(sig, "A1").lower()
    assert "power-invalid" in txt and "not order-balanced" in txt
    assert "not order-balanced" not in V.axis_text(sig, "A2").lower()
    assert V.accepted_all(b8)


# class: new-behaviour (both blocks speed-valid: nothing is labelled power-invalid or not order-balanced in the A1 section)
def test_all_valid_blocks_are_not_labelled(S):
    _, _, sig = S()
    txt = V.axis_text(sig, "A1").lower()
    assert "power-invalid" not in txt and "not order-balanced" not in txt
