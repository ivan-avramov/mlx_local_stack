"""Shared support for the M76 B7.1 (spec `docs/specs/m76-b7-1-joint-plan.md` v1) test-writer tests; no tests here.

Contents:
- `small_report()`: `bench.m76_sim.build_report` at REPORT_REPS replications (cached per process).
- report-key DISCOVERY (class (c)): the specification names only the top-level keys `joint` and `variants`; everything
  below them is found through the report's documented quantities (clean PASS, trigger rate, detection rate, exact size,
  per-look alpha …) by case-insensitive path tokens, a loss level parsed from the path, and the primary session SD.
  A quantity that cannot be found, or is found ambiguously, fails the test with the candidate paths listed.
- independent references (class (b)): the screen trigger rule (brute force at small n and an exact quadrature at the
  real n = 4 languages × 10), the exact size of the two-look A5 rule (enumeration), and a direct joint simulation.
"""
import functools
import itertools
import json
import math
import random
import re
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[2]             # .../benchmark
COMMITTED = BENCH / "results" / "m76" / "b7-simulation"
REPORT_REPS = 1000
PRIMARY_SIGMA = 0.25
NEW_KEYS = ("joint", "variants")


# ------------------------------------------------------------------------------------------------------ report access
@functools.lru_cache(maxsize=None)
def small_report():
    from bench import m76_sim as M
    # AMENDED (v1.1: `b71=False` is the default, so the B7.1 sections must be requested)
    return M.build_report(reps=REPORT_REPS, a5_ns=[72], b71=True)


def section(name):
    """`small_report()[name]` ('joint' / 'variants'), failing with an explicit message when the key is absent."""
    rep = small_report()
    if name not in rep:
        pytest.fail(f"report.json has no `{name}` key (spec: the report gains `joint` and `variants`); keys: {sorted(rep)}")
    return rep[name]


def _need(node, *keys, what):
    for k in keys:
        if not isinstance(node, dict) or k not in node:
            pytest.fail(f"candidate layout: no `{k}` while reading {what} (path so far: {keys})")
        node = node[k]
    return node


# The candidate's documented layout (delivery 2, replacing the token discovery for these quantities):
#   joint.cells.planning.scenarios.{all_loss0, all_loss10}.clean_pass          (rate dict)
#   joint.screen.planning.{loss0, macro10, concentrated10, one_language10}.rates.{T0,T1,T2}   (rate dict)
#   variants.A5-2L.{exact.size, looks[i].alpha, final_looks_false_pass10.exact_size}
#   variants.A7-2L.{available, safe, reason, calibration}
#   variants.screen_options.{T0,T1,T2}.{trigger0, detect_macro10, detect_concentrated10, detect_one_language10}
_SCEN = {0.0: "all_loss0", 0.10: "all_loss10"}
_SCR = {0.0: "loss0", 0.10: "macro10"}


def headline_cell(rep=None):
    """Key of the headline A7 cell (v1.1: the nearest realisable cell when the report has one, else the planning cell)."""
    j = section("joint") if rep is None else rep["joint"]
    return _need(j, "headline", "cell", what="headline cell")


def joint_clean(loss):
    """P(clean PASS) at the headline cell and headline HOLD threshold (v1.1)."""
    return _need(section("joint"), "cells", headline_cell(), "scenarios", _SCEN[loss], "clean_pass", "rate",
                 what=f"P(clean PASS) at loss {loss}")


def joint_trigger(loss, option="T0"):
    return _need(section("joint"), "screen", "planning", _SCR[loss], "rates", option, "rate",
                 what=f"screen trigger at loss {loss}")


def committed_report():
    return json.loads((COMMITTED / "report.json").read_text())


def canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# -------------------------------------------------------------------------------------------------------- discovery
def _is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def leaves(obj, path=()):
    """(path, value) for every numeric leaf; a dict carrying a numeric `rate` (the report's Wilson-rate dict) is one leaf
    whose value is the rate."""
    if isinstance(obj, dict):
        if _is_num(obj.get("rate")):
            yield path, obj["rate"]
            return
        for k, v in obj.items():
            yield from leaves(v, path + (str(k),))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from leaves(v, path + (str(i),))
    elif _is_num(obj):
        yield path, obj


def _squeeze(path):
    return re.sub(r"[^a-z0-9.]+", "", "/".join(path).lower())


def path_loss(path):
    """True-loss level (fraction) named by a path element ('loss=0.1', 'loss_10pp', '10 pp', 'no_loss'), else None."""
    for el in path:
        e = el.lower()
        flat = re.sub(r"[^a-z0-9]+", "", e)
        if flat in ("noloss", "zeroloss", "loss0pp"):
            return 0.0
        m = re.search(r"loss[^0-9a-z]*(\d+(?:\.\d+)?)", e) or re.search(r"(\d+(?:\.\d+)?)\s*_?\s*pp", e)
        if m:
            v = float(m.group(1))
            return v / 100 if v >= 1 else v
    return None


def _sigma_ok(path):
    for el in path:
        m = re.search(r"sigma[^0-9a-z]*(\d+(?:\.\d+)?)", el.lower())
        if m and abs(float(m.group(1)) - PRIMARY_SIGMA) > 1e-9:
            return False
    return True


def _has(sq, tok):
    return any(t in sq for t in tok.split("|"))


def find_all(section, must, none=(), loss=None):
    out = []
    for path, v in leaves(section):
        sq = _squeeze(path)
        if all(_has(sq, t) for t in must) and not any(_has(sq, t) for t in none) and _sigma_ok(path):
            if loss is None or (path_loss(path) is not None and abs(path_loss(path) - loss) < 1e-9):
                out.append((path, v))
    return out


def find_one(section, *alternatives, none=(), loss=None, what="quantity"):
    """The unique numeric leaf matching one of the token alternatives (each a tuple of tokens; 'a|b' = either)."""
    seen = []
    for must in alternatives:
        c = find_all(section, must, none=none, loss=loss)
        seen.append((must, [".".join(p) for p, _ in c]))
        if len(c) == 1:
            return c[0][1]
        if len(c) > 1:
            depth = min(len(p) for p, _ in c)
            top = [x for x in c if len(x[0]) == depth]
            if len(top) == 1:
                return top[0][1]
    pytest.fail(f"cannot discover the {what} in the report section (class (c): the specification does not name this "
                f"key); token alternatives tried and the leaf paths each matched: {seen}")


def subsection(section, *tokens, what="section"):
    """The dict/list node whose key path contains all tokens, shallowest-first; fails when absent or ambiguous."""
    found = []

    def walk(o, path):
        if isinstance(o, dict):
            for k, v in o.items():
                p = path + (str(k),)
                if isinstance(v, (dict, list)) and all(_has(re.sub(r"[^a-z0-9.]+", "", str(k).lower()), t)
                                                       for t in tokens):
                    found.append((p, v))
                walk(v, p)
    walk(section, ())
    if not found:
        pytest.fail(f"cannot discover {what} (tokens {tokens}) among the keys of the report section (class (c))")
    d = min(len(p) for p, _ in found)
    top = [x for x in found if len(x[0]) == d]
    if len(top) > 1:
        pytest.fail(f"{what} (tokens {tokens}) is ambiguous: {[list(p) for p, _ in top]} (class (c))")
    return top[0][1]


def rate_in_unit(v, name):
    assert 0.0 <= v <= 1.0, f"{name} = {v!r} is not a probability in [0, 1] (rates are fractions in the report)"
    return v


def mc_tol(p, *reps, z=3.5, floor=0.01):
    """z-sigma tolerance for the difference of independent Monte Carlo estimates of one probability near p."""
    p = min(max(p, 0.02), 0.98)
    return max(floor, z * math.sqrt(p * (1 - p) * sum(1.0 / r for r in reps)))


# ----------------------------------------------------------------------------------------- screen trigger: references
SCREEN_LANGS, SCREEN_PER = 4, 10                        # tg2 screen: 10 items per language, 4 languages, k = 1
OPTIONS = {"T0": dict(macro=-0.05, lang=-0.15), "T1": dict(macro=-0.05, lang=None),
           "T2": dict(macro=-0.05, lang=-0.25),
           # AMENDED (spec v1.2): T3 sensitive trigger, macro < 0 pp ∨ any language < −10 pp. TD (always the decider) is not a
           # threshold rule and is handled in test_m76_b7_1_fe_fix_v12.py.
           "T3": dict(macro=0.0, lang=-0.10)}


def triggered(lang_sums, per, rule):
    """Spec trigger on per-language sums of d (X − N16 per item ∈ {−1, 0, 1}): macro-average point estimate below
    `macro` (equal-size languages → the pooled mean) or any language point estimate below `lang` (strict)."""
    deltas = [s / per for s in lang_sums]
    if rule["macro"] is not None and sum(deltas) / len(deltas) < rule["macro"] - 1e-12:
        return True
    return rule["lang"] is not None and any(x < rule["lang"] - 1e-12 for x in deltas)


def trigger_prob_bruteforce(d, om, langs, per, rule):
    """P(trigger) by enumerating all 3^(langs·per) outcomes; items iid with P(−1) = d·om, P(0) = 1 − d, P(+1) = d(1 − om)."""
    pm = {-1: d * om, 0: 1.0 - d, 1: d * (1.0 - om)}
    tot = 0.0
    for combo in itertools.product((-1, 0, 1), repeat=langs * per):
        pr = 1.0
        for x in combo:
            pr *= pm[x]
        sums = [sum(combo[i * per:(i + 1) * per]) for i in range(langs)]
        if triggered(sums, per, rule):
            tot += pr
    return tot


def trigger_prob_dp(d, om, langs, per, rule):
    """The same probability by convolution (exact, any n)."""
    import numpy as np
    item = np.array([d * om, 1.0 - d, d * (1.0 - om)])          # values −1, 0, +1
    lang = np.array([1.0])
    for _ in range(per):
        lang = np.convolve(lang, item)                           # values −per … per
    vals = np.arange(-per, per + 1)
    if rule["lang"] is not None:
        keep = np.array([not (v / per < rule["lang"] - 1e-12) for v in vals])
        lang = np.where(keep, lang, 0.0)
    tot = np.array([1.0])
    for _ in range(langs):
        tot = np.convolve(tot, lang)
    tv = np.arange(-per * langs, per * langs + 1)
    ok = np.array([not (rule["macro"] is not None and (v / (per * langs)) < rule["macro"] - 1e-12) for v in tv])
    return 1.0 - float(tot[ok].sum())


def screen_trigger_rate(loss, sigma, rule, *, m=0.5, d_plan=0.182, kappa=4.0, langs=SCREEN_LANGS, per=SCREEN_PER):
    """Exact trigger rate of the screen under the pre-registered data model of the report (`bench.m76_sim.Model`
    calibration of the realised discordance and the loss-calibrated omega0; one unit effect u ~ N(0, sigma²) per load
    unit, here the single screen session; items iid given u): Gauss–Hermite quadrature over u of the exact DP."""
    import numpy as np
    from bench import m76_sim as M
    mod = M.Model("A8", d_plan, loss, sigma, M.cell_beta(m, kappa))
    d = mod.d_real
    if sigma == 0.0 or mod.omega0 in (0.0, 1.0):
        return trigger_prob_dp(d, mod.omega0, langs, per, rule)
    xs, ws = np.polynomial.hermite_e.hermegauss(80)
    ws = ws / ws.sum()
    return float(sum(w * trigger_prob_dp(d, M._expit(M._logit(mod.omega0) + sigma * x), langs, per, rule)
                     for x, w in zip(xs, ws)))


# ------------------------------------------------------------------------------------------- A5 two-look exact size
def _tri(n, pb, pc):
    """Trinomial(n; pb, pc, 1 − pb − pc) pmf over (b, c), shape (n+1, n+1), zero where b + c > n."""
    import numpy as np
    b = np.arange(n + 1)[:, None]
    c = np.arange(n + 1)[None, :]
    r = n - b - c
    ok = r >= 0
    lg = np.array([math.lgamma(k + 1) for k in range(n + 1)])
    p0 = max(1.0 - pb - pc, 1e-300)
    with np.errstate(all="ignore"):
        lp = (lg[n] - lg[b] - lg[c] - lg[np.where(ok, r, 0)] + b * math.log(max(pb, 1e-300))
              + c * math.log(max(pc, 1e-300)) + np.where(ok, r, 0) * math.log(p0))
    return np.where(ok, np.exp(lp), 0.0)


def _a5_masks(n, alpha):
    """(PASS, LOSS) boolean matrices over (b, c) of `verdict_a5`'s rule at n items and one-sided alpha."""
    import numpy as np
    from bench import m76_rule as R
    from bench import stats
    passm = np.zeros((n + 1, n + 1), dtype=bool)
    for b, c in R.a5_pass_region(n, alpha=alpha):
        passm[b, c] = True
    lossm = np.zeros((n + 1, n + 1), dtype=bool)
    for b in range(n + 1):
        for c in range(n - b + 1):
            if not passm[b, c] and b > c and (c - b) / n < R.POINT_FLOOR and stats.mcnemar_exact(b, c) <= R.LOSS_TEST_ALPHA:
                lossm[b, c] = True
    return passm, lossm


def a5_final_pass_prob(n1, n2, a1, a2, pcs, margin=0.10):
    """P(final PASS) of the A5 rule with look 1 on n1 items at one-sided alpha a1 and, when look 1 is UNDECIDED (neither
    PASS nor LOSS), n2 more items pooled at look 2 at alpha a2 — for each nuisance p_c in `pcs` on the H0 boundary
    p_b = p_c + margin. n2 = 0 → the single look at a1. Exact (enumeration of the trinomial outcomes)."""
    import numpy as np
    from numpy.lib.stride_tricks import sliding_window_view
    p1, l1 = _a5_masks(n1, a1)
    und1 = ~p1 & ~l1
    if n2:
        p2, _ = _a5_masks(n1 + n2, a2)
        win = sliding_window_view(p2.astype(float), (n1 + 1, n1 + 1))      # [b2, c2, b1, c1]
        mat = np.ascontiguousarray(win[:n2 + 1, :n2 + 1].reshape((n2 + 1) ** 2, (n1 + 1) ** 2))
    out = []
    for pc in pcs:
        f1 = _tri(n1, pc + margin, pc)
        tot = float((f1 * p1).sum())
        if n2:
            t = (mat @ (f1 * und1).ravel()).reshape(n2 + 1, n2 + 1)
            tot += float((_tri(n2, pc + margin, pc) * t).sum())
        out.append(tot)
    return out


def a5_two_look_size(n1=72, n2=48, alphas=None, step=0.002, margin=0.10):
    """(max over the nuisance grid of the final-PASS probability, argmax p_c). Default alphas: Lan–DeMets O'Brien–Fleming
    increments at t₁ = n1 / (n1 + n2). The grid is p_c = 0 … (1 − margin)/2 in `step` plus a 10× finer scan around the
    best point."""
    import numpy as np
    from bench import stats
    a = list(alphas) if alphas else stats.obf_looks([n1 / (n1 + n2), 1.0], 0.025)
    hi = (1 - margin) / 2
    grid = np.arange(0.0, hi + 1e-12, step)
    vals = a5_final_pass_prob(n1, n2, a[0], a[1], grid, margin)
    j = int(np.argmax(vals))
    fine = np.clip(grid[j] + np.arange(-10, 11) * step / 10, 0.0, hi)
    fv = a5_final_pass_prob(n1, n2, a[0], a[1], fine, margin)
    k = int(np.argmax(fv))
    return (max(vals[j], fv[k]), float(fine[k] if fv[k] > vals[j] else grid[j]))


# --------------------------------------------------------------------------------------------- direct joint simulation
def task_gates_ok(d):
    """A5 per-task point gates (spec v1.1): retrieval and chain-4 each ≥ −5 pp; task = item parity (B7's block unit; the
    specification does not name the assignment — assumption stated, as in the candidate)."""
    for t in (0, 1):
        vals = [r[0] for i, r in enumerate(d) if i % 2 == t]
        if 100 * sum(vals) < -5 * len(vals):
            return False
    return True


def direct_joint(rep, loss, reps, seed, sigma=PRIMARY_SIGMA, rule=None, hold_pp=-20, option="TD", a5_alphas=None):
    """My own replication-level simulation of the whole committed stage-3 plan at one true loss on every axis, built
    only from B7's accepted data-model primitives (`Model`, `_gen`, `analyse`, `verdict_vector`, `a5_table`,
    `interaction_exact_p`, `fire_probability`): per replication draw A1, A5 (PASS ∧ per-task point gates), A7 (at the
    report's headline cell), and A8 on ONE nested item set (the screen on the first 10 items of each language, the
    decider on all 80, HOLD at `hold_pp` — None = no HOLD), all from one stream, and AND the clean conditions. Returns
    dict(clean, a1, a5, a7_clean, a8_path, trigger) as fractions. Axes independent of each other (spec v1.1).
    AMENDED (v1.3 / v1.4): `option` defaults to "TD" (the committed A8 path, C338: the decider runs on every plan; "T0".."T3"
    still select a threshold trigger); `a5_alphas` = (α₁, α₂) runs A5 as the registered two-look plan A5-2L (72 items at α₁,
    UNDECIDED → the cumulative 120 at α₂, look-1 LOSS stops; the per-task gates at the deciding look)."""
    from bench import m76_rule as R
    from bench import m76_sim as M
    rng = random.Random(f"b71-direct:{seed}:{loss!r}")
    frng = random.Random(f"b71-direct-flag:{seed}:{loss!r}")
    ax = rep["axes"]
    # A1
    a1_des = M._design("A1")
    a1_model = M.Model("A1", M.PLANNING_D["A1"], loss, sigma, None)
    a1_alphas = [lk["alpha"] for lk in (ax["A1"]["plan_two_look"] if ax["A1"]["final"] == "two_look"
                                         else ax["A1"]["plan_single"])["looks"]]
    # A5
    n5 = ax["A5"]["n"]
    a5_model = M.Model("A5", M.PLANNING_D["A5"], loss, sigma, None)
    a5_tab = M.a5_table(n5)
    if a5_alphas is not None:
        a5p1, a5l1 = _a5_masks(72, a5_alphas[0])
        a5p2, _ = _a5_masks(120, a5_alphas[1])
    # A7
    pl7 = ax["A7"]["planning"]
    hc = rep["joint"]["headline"]["a7_cell"] if "joint" in rep else dict(m=pl7["m"], D=pl7["D"])   # v1.1 headline cell
    a7_model = M.Model("A7", hc["D"], loss, sigma, M.cell_beta(hc["m"], pl7["kappa"]))
    # the alpha the report's own cells use: the kept two-look alphas, else the single look's planning alpha (a report built
    # at reduced replications may have no safe calibrated alpha*, in which case `final_alpha` holds None)
    a7_alphas = (tuple(ax["A7"]["final_alpha"]) if ax["A7"]["final"] == "two_look"
                 else (ax["A7"]["planning_alpha"],))
    # A8
    pl8 = ax["A8"]["planning"]
    a8_model = M.Model("A8", pl8["D"], loss, sigma, M.cell_beta(pl8["m"], pl8["kappa"]))
    a8_alpha = ax["A8"]["planning_alpha"]
    cnt = dict(clean=0, a1=0, a5=0, a7_clean=0, a8_path=0, trigger=0)
    T0 = OPTIONS["T0"]
    for _ in range(reps):
        # A1
        d = M._gen(a1_model, 300, 1, a1_des["unit"], rng)
        if len(a1_alphas) == 2:
            v = M.analyse(d, range(100), range(1), a1_alphas[0], None)[0]
            if v == R.UNDECIDED:
                v = M.analyse(d, range(300), range(1), a1_alphas[1], None)[0]
        else:
            v = M.analyse(d, range(300), range(1), a1_alphas[0], None)[0]
        ok1 = v == R.PASS
        # A5
        if a5_alphas is None:
            d = M._gen(a5_model, n5, 1, lambda i, s: i % 2, rng)
            b = sum(1 for r in d if r[0] == -1)
            c = sum(1 for r in d if r[0] == 1)
            ok5 = a5_tab[(b, c)] == "P" and task_gates_ok(d)   # v1.1: PASS ∧ per-task point gates (task = item parity)
        else:
            d = M._gen(a5_model, 120, 1, lambda i, s: i % 2, rng)
            b = sum(1 for r in d[:72] if r[0] == -1)
            c = sum(1 for r in d[:72] if r[0] == 1)
            if a5p1[b, c]:
                ok5 = task_gates_ok(d[:72])
            elif a5l1[b, c]:
                ok5 = False
            else:
                b = sum(1 for r in d if r[0] == -1)
                c = sum(1 for r in d if r[0] == 1)
                ok5 = bool(a5p2[b, c]) and task_gates_ok(d)
        # A7 (3 sessions; single look at the committed alpha*, or the two-look rule when the report keeps look 1)
        d = M._gen(a7_model, 43, 3, lambda i, s: s, rng)
        anyd = any(x for r in d for x in r)
        if len(a7_alphas) == 2:
            any1 = any(x for r in d for x in r[:2])
            v1 = M.verdict_vector([sum(r[:2]) for r in d], 43, 2, any1, alphas=(a7_alphas[0],))
            vf = M.verdict_vector([sum(r) for r in d], 43, 3, anyd, alphas=(a7_alphas[1],))
            code = v1 if v1 != "U" else vf
        else:
            code = M.verdict_vector([sum(r) for r in d], 43, 3, anyd, alphas=(a7_alphas[0],))
        flag7 = frng.random() < M.fire_probability(M.interaction_exact_p([tuple(r) for r in d]))
        ok7 = code == "P" and not flag7
        # A8: screen (40 items, k = 1) then, on a trigger, the decider (80 items × 2 sessions, k = 2)
        # v1.1: ONE nested item set per replication — 80 items (4 languages × 20), item parameters shared; the screen is
        # its own k = 1 session on each language's first 10 items; the decider's s1 / s2 are further sessions over all 80
        pis = [a8_model.item_pi(rng) for _ in range(80)]

        def session_outcomes(items):
            om = a8_model.unit_omega(rng)
            return [(-1 if rng.random() < om else 1) if rng.random() < pis[i] else 0 for i in items]
        scr = session_outcomes([lang * 20 + i for lang in range(SCREEN_LANGS) for i in range(10)])
        sums = [sum(scr[lang * 10:(lang + 1) * 10]) for lang in range(SCREEN_LANGS)]
        screen_trig = triggered(sums, SCREEN_PER, T0) if option == "T0" else (
            True if option == "TD" else triggered(sums, SCREEN_PER, OPTIONS[option]))
        trig = screen_trig
        if not trig:
            ok8 = True
        else:
            s1, s2 = session_outcomes(range(80)), session_outcomes(range(80))
            d = [[a, b] for a, b in zip(s1, s2)]
            anyd = any(x for r in d for x in r)
            code = M.verdict_vector([sum(r) for r in d], 80, 2, anyd, alphas=(a8_alpha,))
            flag8 = code == "P" and frng.random() < M.fire_probability(M.interaction_exact_p([tuple(r) for r in d]))
            mn = min(sum(sum(r) for r in d[lang * 20:(lang + 1) * 20]) for lang in range(SCREEN_LANGS))
            held = hold_pp is not None and 100 * mn < hold_pp * 40          # language point < hold_pp (20 items × 2 sessions)
            ok8 = code == "P" and not flag8 and not held
        cnt["trigger"] += trig
        cnt["a1"] += ok1
        cnt["a5"] += ok5
        cnt["a7_clean"] += ok7
        cnt["a8_path"] += ok8
        cnt["clean"] += ok1 and ok5 and ok7 and ok8
    return {k: v / reps for k, v in cnt.items()}
