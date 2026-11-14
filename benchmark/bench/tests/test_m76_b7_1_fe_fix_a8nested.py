"""M76 B7.1 spec v1.1, erratum items "A8 nesting" and "A8 large-harm HOLD".

Nesting: the screen's 40 items are the decider's first 40 (m65 draw rule 2); the screen is its own k = 1 session, the
decider's s1 / s2 are separate sessions over all 80; one A8 item set per replication (item parameters shared), the screen
on its prefix, the decider on all items; no independence assumed between them. HOLD: no number pre-registered; the A8
path and the clean PASS are reported at {none, any language decider point < −25 pp, < −20 pp}.

Class (a): behaviour the erratum states, tested through the candidate's documented functions with deterministic stand-in
models (the prefix predicts the decider exactly). Class (b): my own independent nested simulation (separate code and RNG,
B7's accepted primitives only) vs the committed 20,000-replication report. Class (c): report layout of the candidate
(`joint.a8_nested.loss=<L>.paths.<option>.<hold>.{clean,trigger,decider_clean_given_trigger,…}`). Tolerance 3.5 σ_MC
(floor 0.01).
"""
import random

import pytest

from bench.tests.test_m76_b7_1_fe_support import (OPTIONS, _need, committed_report, mc_tol, screen_trigger_rate,
                                                  triggered)

HOLDS = {"none": None, "lt25": -25, "lt20": -20}


# ------------------------------------------------------------------------------------------------ HOLD predicate (a)
def test_hold_threshold_boundaries():  # (a)
    """Language decider point = Σ d / (20 items × 2 sessions) = Σ d / 40: < −20 pp ⇔ Σ ≤ −9; < −25 pp ⇔ Σ ≤ −11; exactly
    −20 pp / −25 pp does not fire; no threshold never fires."""
    from bench import m76_sim as M
    assert not M.hold_fires(-8, -20) and M.hold_fires(-9, -20)
    assert not M.hold_fires(-10, -25) and M.hold_fires(-11, -25)
    assert not M.hold_fires(-40, None)
    assert not M.hold_fires(0, -20) and not M.hold_fires(5, -25)


def test_hold_fires_through_the_path_on_a_constructed_histogram():  # (a)
    """No simulated scenario has a decider PASS coexisting with a language below −20 pp (the candidate says so), so the HOLD
    is exercised on a constructed histogram: 10 replications triggered (T0 bit) with decider PASS, no flag, and a language
    sum of −9 (−22.5 pp), 10 not triggered. HOLD none → 20 clean; HOLD < −25 pp → 20 (−22.5 pp is above); HOLD < −20 pp
    → the 10 triggered ones are held: 10 clean, `triggered_PASS_held` = 10 and the decider's clean rate given a trigger 0."""
    from bench import m76_sim as M
    hist = {"100|P|0|-9": 10, "000|U|0|0": 10}
    none = M.a8_path_from(hist, 20, "T0", "none")
    l25 = M.a8_path_from(hist, 20, "T0", "lt25")
    l20 = M.a8_path_from(hist, 20, "T0", "lt20")
    assert none["clean"]["k"] == 20 and l25["clean"]["k"] == 20 and l20["clean"]["k"] == 10
    assert l20["triggered_PASS_held"]["k"] == 10 and none["triggered_PASS_held"]["k"] == 0
    assert l20["decider_clean_given_trigger"]["k"] == 0 and none["decider_clean_given_trigger"]["k"] == 10
    flagged = M.a8_path_from({"100|P|1|0": 10, "000|P|0|0": 10}, 20, "T0", "none")
    assert flagged["clean"]["k"] == 10, "a flagged decider PASS is not clean"
    assert M.a8_path_from({"010|L|0|0": 20}, 20, "T0", "none")["clean"]["k"] == 20, "T1-only trigger: T0 reads bit 0"


def test_hold_thresholds_listed_in_the_report():  # (a)
    j = committed_report()["joint"]
    assert {h: v["pp"] for h, v in j["holds"].items()} == HOLDS
    assert j["headline"]["hold"] in HOLDS and "HOLD" in j["headline"]["hold_text"]
    # AMENDED (spec v1.4, C339): the HOLD is registered (any language's decider point < −20 pp), so the text no longer
    # defers to the operator; the other thresholds stay listed as context
    h = j["assumed"]["hold"]
    assert "−20 pp" in h and "C339" in h and "A8_HOLD_PP" in h and "context" in h
    from bench import m76_rule as R
    assert R.A8_HOLD_PP == -0.20 and j["holds"]["lt20"]["pp"] == -20


@pytest.mark.parametrize("loss", [0.0, 0.1])
@pytest.mark.parametrize("opt", ["T0", "T1", "T2"])
def test_hold_only_removes_clean_outcomes(loss, opt):  # (c)
    """Same replications: clean(none) ≥ clean(< −25 pp) ≥ clean(< −20 pp) (a stricter HOLD can only lose clean outcomes)."""
    p = _need(committed_report(), "joint", "a8_nested", f"loss={loss}", "paths", opt, what="A8 paths")
    k = {h: p[h]["clean"]["k"] for h in HOLDS}
    assert k["none"] >= k["lt25"] >= k["lt20"], k


# ------------------------------------------------------------------------------------- nesting through the API (a)
class _Fixed:
    """Stand-in language model: π_i from a fixed list (recorded call order), every discordance a loss (ω₀ = 1) or a gain."""

    def __init__(self, seq, omega0):
        self.seq, self.omega0, self.k = list(seq), omega0, 0

    def item_pi(self, rng):
        v = self.seq[self.k]
        self.k += 1
        return v


@pytest.mark.parametrize("omega0,val", [(1.0, -1), (0.0, 1)])
def test_screen_is_the_decider_prefix_and_prefix_predicts_decider(omega0, val):  # (a)
    """Items with π ∈ {0, 1} and ω₀ ∈ {0, 1} make every outcome deterministic: each language's screen sum is exactly the
    number of its first-10 discordant items (× val), and the decider rows for those same items carry the same outcome in
    BOTH sessions; items 10..19 (not in the screen) carry only decider outcomes. So the screen's prefix predicts the
    decider rows (no independence), and the screen is a separate k = 1 session (σ = 0 here, so sessions are identical)."""
    from bench import m76_sim as M
    seqs = [[1 if (i * 7 + li) % 3 == 0 else 0 for i in range(20)] for li in range(4)]
    models = [_Fixed(s, omega0) for s in seqs]
    screen, rows = M.a8_nested_draw(models, 0.0, random.Random(1))
    assert len(rows) == 80 and all(len(r) == 2 for r in rows)
    for li, s in enumerate(seqs):
        assert screen[li] == val * sum(s[:10]), (li, screen)
        for i in range(20):
            assert rows[li * 20 + i] == [val * s[i]] * 2, (li, i, rows[li * 20 + i])


def test_nested_draw_shares_item_parameters_not_session_effects():  # (a)
    """With σ > 0 the screen session and each decider session get their OWN session effect (separate load units) while the
    item parameters π_i are shared: items with π = 0 are silent in every session; items with π = 1 are discordant in every
    session, but their loss/gain split follows each session's ω (not a copy of the screen's)."""
    from bench import m76_sim as M

    class Mod(_Fixed):
        pass
    models = [Mod([1] * 10 + [0] * 10, 0.5) for _ in range(4)]
    rng = random.Random(3)
    splits = set()
    for _ in range(200):
        for m in models:
            m.k = 0
        screen, rows = M.a8_nested_draw(models, 1.0, rng)
        assert all(r == [0, 0] for li in range(4) for r in rows[li * 20 + 10:(li + 1) * 20])      # π = 0 items silent
        assert all(x in (-1, 1) for li in range(4) for r in rows[li * 20:li * 20 + 10] for x in r)  # π = 1 discordant
        # (losses among language 0's prefix in decider session 1, the screen's sum for language 0): independent sessions
        splits.add((sum(1 for r in rows[:10] if r[0] == -1), screen[0]))
    assert len(splits) > 20, "sessions must not be copies of one another"


# ------------------------------------------------------------------------------------------- independent simulation (b)
def my_nested(loss, reps, seed, d=0.182, m=0.5, kappa=4.0, sigma=0.25):
    """My own nested A8 simulation (separate code / RNG from the candidate's): 4 languages × 20 items with shared π_i; the
    screen = its own session on each language's first 10 items; the decider = s1, s2 over all 80, read at α* (B7 A8's
    planning α) with its interaction flag. Returns per replication tuples (trigger bits T0/T1/T2, code, flag, min language
    Σ d) aggregated into counters."""
    from bench import m76_rule as R
    from bench import m76_sim as M
    mod = M.Model("A8", d, loss, sigma, M.cell_beta(m, kappa))
    alpha = R.axis_plan("A8")["looks"][0]["alpha"]
    rng = random.Random(f"b71-fix-nested:{seed}:{loss!r}")
    rows_out = []
    for _ in range(reps):
        pis = [mod.item_pi(rng) for _ in range(80)]

        def sess(items):
            om = mod.unit_omega(rng)
            return [(-1 if rng.random() < om else 1) if rng.random() < pis[i] else 0 for i in items]
        scr = sess([li * 20 + i for li in range(4) for i in range(10)])
        sums = [sum(scr[li * 10:(li + 1) * 10]) for li in range(4)]
        bits = tuple(triggered(sums, 10, OPTIONS[o]) for o in ("T0", "T1", "T2"))
        s1, s2 = sess(range(80)), sess(range(80))
        dd = [[a, b] for a, b in zip(s1, s2)]
        code = M.verdict_vector([sum(r) for r in dd], 80, 2, any(x for r in dd for x in r), alphas=(alpha,))
        flag = code == "P" and rng.random() < M.fire_probability(M.interaction_exact_p([tuple(r) for r in dd]))
        mn = min(sum(sum(r) for r in dd[li * 20:(li + 1) * 20]) for li in range(4))
        rows_out.append((bits, code == "P" and not flag, mn))
    return rows_out


def _agg(rows_out, oi, hold_pp):
    n = len(rows_out)
    held = lambda mn: hold_pp is not None and 100 * mn < hold_pp * 40
    ok = [(b[oi], c and not held(mn)) for b, c, mn in rows_out]
    trig = sum(t for t, _ in ok)
    clean = sum((not t) or c for t, c in ok)
    dct = sum(c for t, c in ok if t)
    return dict(n=n, trigger=trig / n, clean=clean / n, dec_given_trig=dct / trig if trig else None, ntrig=trig)


@pytest.fixture(scope="module")
def mine():
    return {loss: my_nested(loss, 6000, 7) for loss in (0.0, 0.1)}


@pytest.mark.parametrize("loss", [0.0, 0.1])
@pytest.mark.parametrize("hold", ["none", "lt25", "lt20"])
def test_a8_nested_path_clean_matches_independent_nested_simulation(mine, loss, hold):  # (b)+(c)
    """A8 path clean (¬trigger ∨ (trigger ∧ decider PASS ∧ no flag ∧ no HOLD), T0) at every HOLD threshold vs my own
    6000-replication nested simulation; tolerance 3.5 σ_MC for estimates at 6000 and 20,000 replications."""
    got = _need(committed_report(), "joint", "a8_nested", f"loss={loss}", "paths", "T0", hold, "clean", "rate",
                what="A8 path clean")
    a = _agg(mine[loss], 0, HOLDS[hold])
    assert abs(got - a["clean"]) <= mc_tol(a["clean"], 6000, 20000), (loss, hold, got, a["clean"])


@pytest.mark.parametrize("opt,oi", [("T0", 0), ("T1", 1), ("T2", 2)])
def test_a8_nested_options_match_independent_simulation_at_no_loss(mine, opt, oi):  # (b)+(c)
    p = _need(committed_report(), "joint", "a8_nested", "loss=0.0", "paths", opt, "lt20", what="A8 path")
    a = _agg(mine[0.0], oi, -20)
    assert abs(p["clean"]["rate"] - a["clean"]) <= mc_tol(a["clean"], 6000, 20000)
    assert abs(p["trigger"]["rate"] - a["trigger"]) <= mc_tol(a["trigger"], 6000, 20000)


@pytest.mark.parametrize("loss", [0.0, 0.1])
def test_a8_nested_decider_given_trigger_matches_independent_simulation(mine, loss):  # (b)+(c)
    """The nesting's dependence readout: P(decider clean | screen triggered) from the report vs mine (the decider is read on
    every replication in the candidate, so the conditional is available); tolerance 3.5 σ_MC at the triggered counts."""
    p = _need(committed_report(), "joint", "a8_nested", f"loss={loss}", "paths", "T0", "none",
              "decider_clean_given_trigger", what="decider clean | trigger")
    a = _agg(mine[loss], 0, None)
    ref = a["dec_given_trig"]
    assert abs(p["rate"] - ref) <= mc_tol(ref, a["ntrig"], p["n"]), (p["rate"], ref)


def test_a8_nested_trigger_is_the_screen_blocks_trigger_and_the_exact_value():  # (c)
    rep = committed_report()
    t = rep["joint"]["a8_nested"]["loss=0.0"]["paths"]["T0"]["none"]["trigger"]["rate"]
    s = rep["joint"]["screen"]["planning"]["loss0"]["rates"]["T0"]["rate"]
    ex = screen_trigger_rate(0.0, 0.25, OPTIONS["T0"])
    assert abs(t - ex) <= mc_tol(ex, 20000, floor=0.005) and abs(s - ex) <= mc_tol(ex, 20000, floor=0.005)


def test_independence_formula_is_only_descriptive():  # (a)
    """The old independence formula 1 − t + t·q survives only as a descriptive key; the path itself is the nested one
    (its clean rate comes from the replication histogram, not from the formula)."""
    j = committed_report()["joint"]["a8_nested"]["loss=0.0"]
    p = j["paths"]["T0"]["none"]
    q_missing = j["independence_formula_T0_none"]
    assert 0.0 < q_missing < 1.0
    hist = j["hist"]
    n = sum(hist.values())
    clean = 0
    for key, c in hist.items():
        bits, v, fl, mn = key.split("|")
        clean += c * (bits[0] == "0" or (v == "P" and fl == "0"))
    assert clean == p["clean"]["k"] and n == p["clean"]["n"]
