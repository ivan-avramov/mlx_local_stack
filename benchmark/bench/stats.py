"""Statistics core for every quality axis.

The campaign's early numbers were single-sample (k=1) point estimates with no intervals, so
published deltas sat inside the noise floor. Everything here exists to stop that recurring:

* ITEMS ARE THE UNIT OF ANALYSIS, never the pooled N*k trials. Two samples of one item are not
  two items — they are correlated. `pass_at_1` averages item means; `cluster_bootstrap` is
  two-stage precisely so that correlation is priced in.
* NO INTERVAL, NO CLAIM. A delta is reported with its CI and with the axis MDE, so "we cannot
  see an effect this small at N=15" is visible instead of inferred.
* FAILING TO REJECT IS NOT EQUIVALENCE. `paired_delta` says "wash" (P359): no shown difference, MDE alongside.

Stdlib at import, on purpose: this module is imported by tooling in several venvs, some without
numpy/scipy. The M76 B7 exact functions (`exact_paired_loss`, `exact_loss_region`,
`exact_loss_size`) import numpy lazily, inside the call; every other function is stdlib-only.
Every function is pure; every randomized function takes an explicit `seed` and is
byte-reproducible for it.

Minimum usable n, per metric (stated again on each function):
    wilson              n >= 1; below ~10 it is wide but honest (that is the point).
    pass_at_1           any n; meaningless as a comparison below ~15 items (see mde).
    cluster_bootstrap   >= ~10 items; below that the percentile CI is grid-coarse, not wrong.
    reliability         >= ~30 items for u_stats; all_k is display-only at any n.
    paired_delta        n >= n_for(delta_you_care_about); at 15 items the floor is ~32pp.
    time_to_success     >= ~5 successes and >= ~5 failures before the means mean anything.
"""
import math

# z-values, hardcoded because scipy is not importable in `.venv-bench` and a normal-quantile
# implementation would be more code than the three constants anyone actually uses. Two-sided
# alpha (z_{alpha/2}) and one-sided power (z_beta).
_Z_ALPHA_2 = {0.10: 1.644854, 0.05: 1.959964, 0.01: 2.575829}
_Z_POWER = {0.80: 0.841621, 0.90: 1.281552, 0.95: 1.644854}


# --------------------------------------------------------------------------------- intervals
def wilson(k, n, z=1.96):
    """Wilson score interval for a binomial proportion k/n. Returns (lo, hi) clamped to [0,1].

    Wilson, not Wald: Wald (p +- z*sqrt(p(1-p)/n)) collapses to a zero-width interval at p=0
    and p=1 — exactly the 0/15 and 15/15 cells a small coding axis produces — and under-covers
    badly below n~40. Wilson stays inside [0,1] and keeps nominal coverage at small n.

    The clamp is not cosmetic: the closed form floats to ~-2.8e-17 at p=0 and 1+2e-16 at p=1,
    which prints as a negative pass rate and destroys a reader's trust in the whole table.

    FAILURE MODE: this interval assumes n INDEPENDENT trials. Feeding it pooled N*k samples
    from N items is wrong by a factor of ~sqrt(1+(k-1)rho) — use cluster_bootstrap for k>1.
    MINIMUM USABLE n: 1. n=0 returns (None, None) rather than dividing by zero.
    """
    if n == 0:
        return (None, None)
    if n < 0 or k < 0 or k > n:
        raise ValueError(f"wilson: need 0 <= k <= n, got k={k}, n={n}")
    z2 = z * z
    denom = n + z2
    center = (k + z2 / 2) / denom
    half = (z / denom) * math.sqrt(k * (n - k) / n + z2 / 4)
    return (max(0.0, center - half), min(1.0, center + half))


# ---------------------------------------------------------------------------------- pass@1
def _draw_lists(per_item):
    """The non-empty score lists of a {item_id: [score, ...]} mapping, in item-id order.

    Items with no draws are DROPPED, not zeroed: an interrupted generate/resume routinely
    leaves items with zero rows, and scoring absent data as a failure fabricates results.
    Sorted by id so every derived statistic is order-independent w.r.t. dict insertion.
    """
    return [list(per_item[i]) for i in sorted(per_item) if len(per_item[i]) > 0]


def pass_at_1(per_item):
    """Mean over ITEMS of each item's mean score. None when no item has any draw.

    Scores are 0/1 or graded floats in [0,1]. {i1:[1,1,0], i2:[0,0,0]} -> 1/3.

    WHY not pool the trials: pooling weights each item by how many samples it happens to have,
    so a resumed run where one item got 4 samples and another got 1 silently reweights the
    benchmark ({i1:[1,1,1,1], i2:[0]} pools to 0.8, averages to 0.5). Items are the population
    we sample; k is only how precisely we measured each one.

    MINIMUM USABLE n: any n produces a number, but see mde() — below ~15 items no DIFFERENCE
    between two models is resolvable, so a bare pass@1 at n=5 is decoration.
    """
    items = _draw_lists(per_item)
    if not items:
        return None
    return sum(sum(d) / len(d) for d in items) / len(items)


def _mean_of_item_means(items):
    return sum(sum(d) / len(d) for d in items) / len(items)


def _percentile(sorted_vals, q):
    """Linear-interpolated quantile of an already-sorted list (numpy's default method)."""
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def cluster_bootstrap(per_item, iters=10000, seed=0, statistic=None, strata=None):
    """Two-stage (cluster) percentile bootstrap over {item_id: [score, ...]}.

    Stage 1 resamples ITEMS with replacement; stage 2 resamples the selected item's k draws
    with replacement. Returns {"point", "lo", "hi", "iters", "n_items"} with a 2.5/97.5
    percentile CI. `point` is the statistic on the OBSERVED data (not the bootstrap mean, which
    carries the resampling bias). `statistic` is a callable taking the resampled data as a
    list of per-item draw lists -> float; default = pass_at_1 semantics.

    WHY two stages: pooling N*k trials into one Wilson interval ignores item-level clustering.
    With k=5 and intra-item correlation rho~=0.7 the design effect is 1+(k-1)rho = 3.8, so the
    true SE is ~1.95x larger and the pooled interval is about TWICE too tight — which is how a
    "significant" 4pp coding delta happens. Stage 1 alone is not enough either: it reports a
    zero-width CI for a single item and ignores the fact that k draws are a sample too.

    `strata` (M12, pooling-for-power): optional {item_id: stratum_key} map. When given, stage 1
    resamples items INDEPENDENTLY WITHIN each stratum, preserving that stratum's own item count
    on every draw — e.g. pooling two benches, this keeps the bench mix fixed across the
    bootstrap instead of letting a lucky draw over- or under-represent one bench. `strata=None`
    (default) is the plain single-population resample above, and consumes the RNG in exactly
    the same sequence as before this parameter existed — a regression pin, not just a claim.

    FAILURE MODE: percentile bootstrap under-covers in the tails at small N and lands on a
    coarse 1/N grid (at N=15 the endpoints move in ~6.7pp steps, so it can disagree with
    wilson() by up to ~7pp). It is also useless for an unbounded ratio statistic — see
    time_to_success. MINIMUM USABLE n: ~10 items; below that report the histogram instead.
    """
    import random
    stat = statistic or _mean_of_item_means
    ids = sorted(i for i in per_item if len(per_item[i]) > 0)
    items = [list(per_item[i]) for i in ids]
    n = len(items)
    if n == 0:
        return {"point": None, "lo": None, "hi": None, "iters": iters, "n_items": 0}
    rng = random.Random(seed)
    strata_positions = None
    if strata is not None:
        groups = {}
        for pos, item_id in enumerate(ids):
            groups.setdefault(strata.get(item_id), []).append(pos)
        strata_positions = list(groups.values())
    reps = []
    for _ in range(iters):
        resampled = []
        if strata_positions is not None:
            for positions in strata_positions:
                gn = len(positions)
                for _ in range(gn):
                    pos = positions[rng.randrange(gn)]
                    draws = items[pos]
                    k = len(draws)
                    resampled.append([draws[rng.randrange(k)] for _ in range(k)])
        else:
            for _ in range(n):
                draws = items[rng.randrange(n)]
                k = len(draws)
                resampled.append([draws[rng.randrange(k)] for _ in range(k)])
        reps.append(stat(resampled))
    reps.sort()
    return {"point": stat(items), "lo": _percentile(reps, 0.025),
            "hi": _percentile(reps, 0.975), "iters": iters, "n_items": n}


# ------------------------------------------------------------------------------- reliability
def _successes(per_item):
    """Per-item success counts, validating that scores are binary."""
    items = _draw_lists(per_item)
    counts = []
    for draws in items:
        for s in draws:
            if s not in (0, 1, 0.0, 1.0, True, False):
                raise ValueError(
                    f"reliability: needs BINARY scores, got {s!r}. A fractional 'success' has "
                    f"no defined j-subset probability — grade to pass/fail first, or use "
                    f"pass_at_1/cluster_bootstrap for graded scores.")
        counts.append((sum(1 for s in draws if s), len(draws)))
    return counts


def reliability(per_item):
    """How CONSISTENTLY items pass across their k draws. Requires binary scores.

    Returns {"k", "histogram", "u_stats", "all_k"}:

    * `histogram`: {c: number of items with exactly c successes}. This is the SUFFICIENT
      STATISTIC for a per-item binomial — report it and NOTHING is lost; every scalar below is
      derivable from it. When in doubt, print the histogram.
    * `k`: the common draw count, or None if the run is RAGGED (items with differing k). Ragged
      is normal mid-resume; it makes the k-dependent scalars undefined rather than approximate.
    * `u_stats[j]` for j in (2,3): the UNBIASED estimate of P(a random j-subset of an item's k
      draws all succeed) = mean over items of C(c_i,j)/C(k,j). Defined only when every item has
      the same k >= j, else None for that j. This is the k-independent way to talk about
      reliability: u2 at k=3 and u2 at k=5 are on the same scale and comparable.
    * `all_k`: fraction of items that succeeded in ALL of their draws. DISPLAY ONLY. It uses
      only the extreme order statistic, so (a) it throws away everything the histogram knows,
      (b) it is NOT comparable across k — a genuinely p=0.9 item reads 0.9^3=0.729 at k=3 and
      0.9^5=0.590 at k=5, so the model that got more samples looks worse for free — and (c) at
      N=15 its own binomial noise is about +-25pp (wilson(9,15) spans 0.36..0.80). Never rank
      models on all_k; rank on u_stats or pass@1 with its CI.

    MINIMUM USABLE n: ~30 items for u_stats to be worth quoting; all_k never (display only).
    """
    counts = _successes(per_item)
    if not counts:
        return {"k": None, "histogram": {}, "u_stats": {2: None, 3: None}, "all_k": None}
    ks = {kk for _, kk in counts}
    k = ks.pop() if len(ks) == 1 else None
    histogram = {}
    for c, _ in counts:
        histogram[c] = histogram.get(c, 0) + 1
    u_stats = {}
    for j in (2, 3):
        if k is not None and k >= j:
            u_stats[j] = (sum(math.comb(c, j) / math.comb(k, j) for c, _ in counts)
                          / len(counts))
        else:
            u_stats[j] = None
    all_k = sum(1 for c, kk in counts if c == kk) / len(counts)
    return {"k": k, "histogram": histogram, "u_stats": u_stats, "all_k": all_k}


# ------------------------------------------------------------------------------ paired delta
def paired_delta(a_per_item, b_per_item, iters=10000, seed=0, margin=0.05, strata=None,
                 interval_alpha=0.05, exact_alpha=0.05):
    """Two-stage PAIRED bootstrap of pass@1(a) - pass@1(b) over the SHARED item set.

    M76 B7: `interval_alpha` (two-sided; percentiles interval_alpha/2 and 1 - interval_alpha/2) and `exact_alpha`
    (one-sided; zero-discordance bound 1 - exact_alpha^(1/n)). At the defaults (both 0.05) the output dict is
    byte-identical to the pre-B7 function. With any other value the dict additionally carries `discordance_upper` (the
    bound at `exact_alpha`), `interval_alpha` and `exact_alpha`; `discordance_upper95` keeps its meaning (the bound at
    0.05, None when `exact_alpha` differs).

    Returns {"delta", "lo", "hi", "verdict", "n_items", "mde"}. Stage 1 resamples item ids ONCE
    and applies the same ids to both runs (that is the pairing — item difficulty is the largest
    variance component and it cancels); stage 2 resamples each model's draws for that item
    INDEPENDENTLY, because model a's j-th sample and model b's j-th sample are independent
    runs, not a matched pair. Sharing draw indices would cancel real within-item noise and
    report a CI that is too tight.

    `strata` (M12, pooling-for-power): optional {item_id: stratum_key} map, e.g. a pooled
    cross-bench compare keyed by `(bench, item_id)` with `strata[k] = k[0]`. When given, stage 1
    resamples item ids INDEPENDENTLY WITHIN each stratum, preserving that stratum's own n on
    every draw (the bench mix stays fixed; only within-bench item/draw noise is resampled).
    `delta`/`n_items`/`mde` are still computed over the FULL pooled set either way. `strata=None`
    (default) is byte-identical to this function before the parameter existed.

    RAISES ValueError if the item-id sets differ, naming the symmetric difference. Comparing
    two differently-filtered item sets (one model's errored items quietly dropped) is the exact
    defect this function replaces — it is never a warning.

    `verdict` (P359 / C172 — no equivalence claims):
      "a_better"/"b_better"  the CI excludes 0;
      "wash"                 the CI includes 0: no shown difference. Always read it with `mde` and
                             the actual numbers; `directional` ("a"/"b"/"tie") is the point-estimate
                             pick — a directional pick, NOT a shown difference (exact tie: "tie").
    `margin` is accepted for API compatibility only: it is decision-inert here (no equivalence test).

    FAILURE MODE: a wash is a sample-size statement, not a model statement — at 15 items nothing
    under ~32pp is resolvable (`mde`). Lossy-lever decision code must apply the C173 observed-loss-bound
    guard itself (CI lower bound >= -10pp, or the exact discordance bound for a degenerate cell), never MDE.
    MINIMUM USABLE n: n_for(delta).
    """
    import random
    a_ids = {i for i, d in a_per_item.items() if len(d) > 0}
    b_ids = {i for i, d in b_per_item.items() if len(d) > 0}
    if a_ids != b_ids:
        only_a = sorted(a_ids - b_ids)
        only_b = sorted(b_ids - a_ids)
        raise ValueError(
            f"paired_delta: item sets differ — a-only={only_a}, b-only={only_b}. A paired "
            f"comparison needs the SAME items; intersect them explicitly and say so, or the "
            f"delta mixes a model effect with an item-selection effect.")
    ids = sorted(a_ids)
    n = len(ids)
    if n == 0:
        raise ValueError("paired_delta: no shared items with any draws")
    a_draws = [list(a_per_item[i]) for i in ids]
    b_draws = [list(b_per_item[i]) for i in ids]
    strata_positions = None
    if strata is not None:
        groups = {}
        for pos, item_id in enumerate(ids):
            groups.setdefault(strata.get(item_id), []).append(pos)
        strata_positions = list(groups.values())
    rng = random.Random(seed)
    reps = []
    for _ in range(iters):
        sa = sb = 0.0
        if strata_positions is not None:
            for positions in strata_positions:
                gn = len(positions)
                for _ in range(gn):
                    idx = positions[rng.randrange(gn)]    # ONE item index within its own
                    da, db = a_draws[idx], b_draws[idx]   # stratum, for both runs => paired
                    sa += sum(da[rng.randrange(len(da))] for _ in range(len(da))) / len(da)
                    sb += sum(db[rng.randrange(len(db))] for _ in range(len(db))) / len(db)
        else:
            for _ in range(n):
                idx = rng.randrange(n)              # ONE item index for both runs => paired
                da, db = a_draws[idx], b_draws[idx]
                sa += sum(da[rng.randrange(len(da))] for _ in range(len(da))) / len(da)
                sb += sum(db[rng.randrange(len(db))] for _ in range(len(db))) / len(db)
        reps.append((sa - sb) / n)
    reps.sort()
    defaults = interval_alpha == 0.05 and exact_alpha == 0.05
    if defaults:
        lo, hi = _percentile(reps, 0.025), _percentile(reps, 0.975)
    else:
        _check_alpha("paired_delta", interval_alpha, exact_alpha)
        lo, hi = _percentile(reps, interval_alpha / 2), _percentile(reps, 1 - interval_alpha / 2)
    delta = (pass_at_1({i: a_per_item[i] for i in ids})
             - pass_at_1({i: b_per_item[i] for i in ids}))
    if lo > 0:
        verdict = "a_better"
    elif hi < 0:
        verdict = "b_better"
    else:
        verdict = "wash"
    directional = "a" if delta > 1e-12 else ("b" if delta < -1e-12 else "tie")
    # P346 diagnostics (kept): a collapsed percentile interval (lo == hi, e.g. zero paired discordance) is flagged and
    # carries the exact one-sided 95% upper bound on the discordance rate (0 of n discordant).
    degenerate = lo == hi
    discordant = sum(sum(da) / len(da) != sum(db) / len(db) for da, db in zip(a_draws, b_draws))
    upper = (1 - 0.05 ** (1 / n)) if degenerate and discordant == 0 else None
    out = {"delta": delta, "lo": lo, "hi": hi, "verdict": verdict, "n_items": n,
           "mde": mde(n), "degenerate": degenerate, "discordance_upper95": upper,
           "directional": directional}
    if not defaults:
        if exact_alpha != 0.05:
            out["discordance_upper95"] = None
        out["discordance_upper"] = (1 - exact_alpha ** (1 / n)) if degenerate and discordant == 0 else None
        out["interval_alpha"] = interval_alpha
        out["exact_alpha"] = exact_alpha
    return out


def _check_alpha(fn, interval_alpha, exact_alpha):
    for name, a in (("interval_alpha", interval_alpha), ("exact_alpha", exact_alpha)):
        if not (isinstance(a, (int, float)) and 0.0 < a < 1.0):
            raise ValueError(f"{fn}: {name} must be in (0, 1), got {a!r}")


def paired_session_delta(a, b, *, iters=10000, seed=426, interval_alpha=0.05, exact_alpha=0.05, strata=None):
    """M76 B7 (C324): paired bootstrap of arm a − arm b over items that each carry several SESSIONS.

    `a` / `b` map item_id → {session_id: 0/1}. Both arms must hold the identical item set, and every item the identical
    session set in both arms and across items (else ValueError naming the difference). Stage 1 resamples ITEMS (within
    `strata` when given, {item_id: key}); each resampled item contributes its whole vector of per-session differences
    d_s = a_s − b_s — the arms' sessions are NEVER resampled independently, so a session's pairing survives. Statistic:
    mean over items of the mean over sessions of d_s. Percentile interval at 1 − interval_alpha (two-sided); the
    zero-discordance exact bound 1 − exact_alpha^(1/n_items) when the interval is degenerate and no item has any
    nonzero d_s. `per_session[s]` is `paired_delta` of that session alone (same iters / seed / strata, 95 %).

    Returns {delta, lo, hi, n_items, n_sessions, degenerate, discordant_items, discordance_upper, per_session}.
    """
    import random
    _check_alpha("paired_session_delta", interval_alpha, exact_alpha)
    a_ids, b_ids = set(a), set(b)
    if a_ids != b_ids:
        raise ValueError(f"paired_session_delta: item sets differ — a-only={sorted(a_ids - b_ids, key=str)}, "
                         f"b-only={sorted(b_ids - a_ids, key=str)}")
    ids = sorted(a_ids, key=str)
    if not ids:
        raise ValueError("paired_session_delta: no items")
    sessions = None
    for i in ids:
        sa, sb = set(a[i]), set(b[i])
        if sa != sb:
            raise ValueError(f"paired_session_delta: item {i!r}: session sets differ — a-only="
                             f"{sorted(sa - sb, key=str)}, b-only={sorted(sb - sa, key=str)}")
        if not sa:
            raise ValueError(f"paired_session_delta: item {i!r} has no sessions")
        if sessions is None:
            sessions, first = sa, i
        elif sa != sessions:
            raise ValueError(f"paired_session_delta: item {i!r} sessions {sorted(sa, key=str)} differ from item "
                             f"{first!r} sessions {sorted(sessions, key=str)}")
    sess = sorted(sessions, key=str)
    n, k = len(ids), len(sess)
    vals = [sum(a[i][s] - b[i][s] for s in sess) / k for i in ids]
    discordant = sum(1 for i in ids if any(a[i][s] != b[i][s] for s in sess))
    groups = None
    if strata is not None:
        g = {}
        for pos, i in enumerate(ids):
            g.setdefault(strata.get(i), []).append(pos)
        groups = list(g.values())
    rng = random.Random(seed)
    reps = []
    for _ in range(iters):
        t = 0.0
        if groups is not None:
            for positions in groups:
                gn = len(positions)
                for _ in range(gn):
                    t += vals[positions[rng.randrange(gn)]]
        else:
            for _ in range(n):
                t += vals[rng.randrange(n)]
        reps.append(t / n)
    reps.sort()
    lo, hi = _percentile(reps, interval_alpha / 2), _percentile(reps, 1 - interval_alpha / 2)
    degenerate = lo == hi
    upper = (1 - exact_alpha ** (1 / n)) if degenerate and discordant == 0 else None
    per_session = {s: paired_delta({i: [a[i][s]] for i in ids}, {i: [b[i][s]] for i in ids},
                                   iters=iters, seed=seed, strata=strata) for s in sess}
    return {"delta": sum(vals) / n, "lo": lo, "hi": hi, "n_items": n, "n_sessions": k, "degenerate": degenerate,
            "discordant_items": discordant, "discordance_upper": upper, "per_session": per_session}


# ------------------------------------------------------------------------------- alpha spending
def _phi(x):
    """Standard normal CDF."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def _phi_inv(p):
    """Standard normal quantile by bisection on `_phi` (stdlib only; |error| < 1e-14)."""
    if not (0.0 < p < 1.0):
        raise ValueError(f"_phi_inv: p must be in (0, 1), got {p!r}")
    lo, hi = -40.0, 40.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if _phi(mid) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-15:
            break
    return (lo + hi) / 2


def obf_alpha(t, alpha_total):
    """Lan–DeMets O'Brien–Fleming spending α(t) = 2 · (1 − Φ(z_{1−α/2} / √t)) for a one-sided total α at information
    fraction t ∈ (0, 1]; α(1) = α exactly."""
    if not (0.0 < alpha_total < 1.0):
        raise ValueError(f"obf_alpha: alpha_total must be in (0, 1), got {alpha_total!r}")
    if not (0.0 < t <= 1.0):
        raise ValueError(f"obf_alpha: t must be in (0, 1], got {t!r}")
    if t == 1:
        return alpha_total
    return 2.0 * (1.0 - _phi(_phi_inv(1.0 - alpha_total / 2.0) / math.sqrt(t)))


def obf_looks(fractions, alpha_total):
    """Per-look nominal one-sided alphas from O'Brien–Fleming spending: look k gets α(t_k) − α(t_{k−1}) (α(t_0) = 0).
    `fractions` strictly increasing in (0, 1]."""
    fr = list(fractions)
    if not fr:
        raise ValueError("obf_looks: need at least one information fraction")
    for x, y in zip(fr, fr[1:]):
        if not y > x:
            raise ValueError(f"obf_looks: fractions must be strictly increasing, got {fr}")
    out, spent = [], 0.0
    for t in fr:
        cum = obf_alpha(t, alpha_total)
        out.append(cum - spent)
        spent = cum
    return out


# ------------------------------------------------------------------ exact unconditional paired loss test (M76 B7 v1.1)
# numpy is imported lazily inside these functions only (it is in benchmark/requirements-bench.lock); importing
# bench.stats stays stdlib-only.
_TANGO_TOL = 1e-9            # |T − t_obs| ≤ tol counts as a tie (ties are ordered together)
_GRID_INTERIOR = 1000        # default nuisance grid: 1000 interior points plus both endpoints
_BOUND_STEP = 1000           # the reported bound lives on a 0.001 grid in [0, 1]
_LOG0 = -1e4                 # stands in for log(0): exp(k · _LOG0) is exactly 0.0 for k ≥ 1; 0 · _LOG0 = 0
_EXACT_TABLES = {}


def _np():
    import numpy
    return numpy


def _exact_table(n):
    """All (b, c) with b + c ≤ n and the log trinomial coefficients (cached per n)."""
    if n not in _EXACT_TABLES:
        np = _np()
        bs, cs = [], []
        for b in range(n + 1):
            for c in range(n - b + 1):
                bs.append(b)
                cs.append(c)
        b = np.array(bs, dtype=float)
        c = np.array(cs, dtype=float)
        r = n - b - c
        lg = np.array([math.lgamma(k + 1) for k in range(n + 1)])
        lc = lg[n] - lg[b.astype(int)] - lg[c.astype(int)] - lg[r.astype(int)]
        _EXACT_TABLES[n] = (b, c, r, lc)
    return _EXACT_TABLES[n]


def _tango(b, c, n, m):
    """Tango (1998) score statistic for H0 p_b − p_c = m at the constrained MLE (works on scalars and arrays).
    b ↔ Tango's x12 (N16 pass, X fail), c ↔ x21. Zero variance: T = 0 when the numerator is 0, else ±inf."""
    np = _np()
    b = np.asarray(b, dtype=float)
    c = np.asarray(c, dtype=float)
    A = 2.0 * n
    B = -b - c + (2.0 * n - b + c) * m
    C = -c * m * (1.0 - m)
    sq = np.sqrt(np.maximum(B * B - 4.0 * A * C, 0.0))
    with np.errstate(divide="ignore", invalid="ignore"):
        # the nonnegative root (−B + √disc) / 2A, in the cancellation-free form when B > 0
        p21 = np.where(B > 0, np.where(sq + B > 0, -2.0 * C / (sq + B), 0.0), (sq - B) / (2.0 * A))
        var = n * (2.0 * p21 + m * (1.0 - m))
        num = b - c - n * m
        t = np.where(var > 0, num / np.sqrt(np.where(var > 0, var, 1.0)), np.sign(num) * np.inf)
    return np.where(num == 0, 0.0, t)


def _nuisance_grid(margin, grid, grid_margin):
    """p_c values for the test at `margin`: the default grid (1000 interior points + endpoints of [0, (1 − m)/2]) or a
    user grid given for `grid_margin`, rescaled to [0, (1 − margin)/2] in proportion."""
    np = _np()
    hi = (1.0 - margin) / 2.0
    if grid is None:
        g = hi * np.arange(_GRID_INTERIOR + 2) / (_GRID_INTERIOR + 1)
    else:
        g = np.asarray(sorted(float(x) for x in grid), dtype=float)
        top = (1.0 - grid_margin) / 2.0
        if g.size == 0 or g[0] < -1e-15 or g[-1] > top + 1e-12:
            raise ValueError(f"exact_paired_loss: grid must be non-empty p_c values in [0, {top}] for margin "
                             f"{grid_margin}")
        g = np.clip(g, 0.0, top)
        g = g * (hi / top) if top > 0 else np.zeros_like(g)
    return g


def _exact_probs(n, margin, grid, grid_margin, cols):
    """Trinomial(n; p_b = p_c + margin, p_c) probabilities, rows = nuisance grid points, columns = table cells `cols`."""
    np = _np()
    b, c, r, lc = _exact_table(n)
    pc = _nuisance_grid(margin, grid, grid_margin)
    pb = pc + margin
    p0 = 1.0 - pb - pc
    with np.errstate(divide="ignore"):
        lp = np.stack([np.where(x > 0, np.log(np.where(x > 0, x, 1.0)), _LOG0) for x in (pb, pc, p0)], axis=1)
    counts = np.stack([b[cols], c[cols], r[cols]], axis=0)
    return np.exp(lp @ counts + lc[cols])


def _exact_pvalue(n, margin, t_thr, grid, grid_margin, extra=None):
    """sup over the nuisance grid of P(T ≤ t_thr [∧ extra]) at the H0 boundary p_b − p_c = margin."""
    np = _np()
    b, c, _, _ = _exact_table(n)
    t = _tango(b, c, n, margin)
    mask = t <= t_thr + _TANGO_TOL * (1.0 + abs(t_thr))
    if extra is not None:
        mask &= extra
    cols = np.nonzero(mask)[0]
    if cols.size == 0:
        return 0.0
    return float(min(1.0, _exact_probs(n, margin, grid, grid_margin, cols).sum(axis=1).max()))


def _check_exact(fn, b, c, n, margin, alpha):
    """Validate the exact-test arguments; returns (b, c, n) as Python ints (numpy integers accepted)."""
    import numbers
    for name, v in (("b", b), ("c", c), ("n", n)):
        if not isinstance(v, numbers.Integral) or isinstance(v, bool):
            raise ValueError(f"{fn}: {name} must be an int, got {v!r}")
    b, c, n = int(b), int(c), int(n)
    if n < 1 or b < 0 or c < 0 or b + c > n:
        raise ValueError(f"{fn}: need n ≥ 1, b, c ≥ 0 and b + c ≤ n, got b={b}, c={c}, n={n}")
    if not (0.0 <= margin <= 1.0):
        raise ValueError(f"{fn}: margin must be in [0, 1], got {margin!r}")
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"{fn}: alpha must be in (0, 1), got {alpha!r}")
    return b, c, n


def exact_paired_loss(b, c, n, *, margin=0.10, alpha=0.025, grid=None):
    """M76 B7 v1.1 (C331): exact unconditional test of a paired loss, H0: p_b − p_c ≥ margin vs H1: < margin.

    Per item d = X − N16 ∈ {−1, 0, +1}; `b` = #(d = −1) (N16 pass, X fail), `c` = #(d = +1), `n` items. Ordering
    statistic: Tango's score statistic at `margin` with the constrained MLE (Tango 1998, Statistics in Medicine 17:891); ties
    (|ΔT| ≤ 1e-9 relative) are ordered together. p-value = sup over p_c ∈ [0, (1 − margin)/2] (p_b = p_c + margin; the
    H0 boundary) of P(T ≤ t_obs) under trinomial(n; p_b, p_c), by exact enumeration of every (b, c) with b + c ≤ n.
    Nuisance grid: 1000 interior points plus both endpoints (default), or `grid` (p_c values for `margin`; rescaled
    in proportion to [0, (1 − m)/2] when the bound scan tests another margin m).

    Returns {pvalue, reject (pvalue ≤ alpha), bound, bound_attained, delta = (c − b)/n, b, c, n, margin, alpha}.
    `bound` = the smallest margin on the 0.001 grid in [0, 1] at which H0 is rejected (the loss bound; 1.0 with
    `bound_attained` False when no margin rejects). Margins m with b − c ≥ n·m and m < 1 − 2/n are skipped without
    evaluation when the default grid is used and alpha < 1/4: there t_obs ≥ 0, and at the endpoint p_c = (1 − m)/2,
    P(T ≤ 0) = P(Bin(n, (1 + m)/2) ≤ n(1 + m)/2) > 1/4 (Greenberg & Mohri 2014), so they cannot reject.
    """
    b, c, n = _check_exact("exact_paired_loss", b, c, n, margin, alpha)
    t_obs = float(_tango(b, c, n, margin))
    pvalue = _exact_pvalue(n, margin, t_obs, grid, margin)
    bound, attained = 1.0, False
    for j in range(_BOUND_STEP + 1):
        m = j / _BOUND_STEP
        if grid is None and alpha < 0.25 and _BOUND_STEP * (b - c) >= j * n and m < 1.0 - 2.0 / n:
            continue
        if _exact_pvalue(n, m, float(_tango(b, c, n, m)), grid, margin) <= alpha:
            bound, attained = m, True
            break
    return {"pvalue": pvalue, "reject": pvalue <= alpha, "bound": bound, "bound_attained": attained,
            "delta": (c - b) / n, "b": b, "c": c, "n": n, "margin": margin, "alpha": alpha}


def exact_loss_region(n, *, margin=0.10, alpha=0.025, grid=None):
    """The set of (b, c) (b + c ≤ n) that `exact_paired_loss` rejects at (margin, alpha, grid): a prefix of the
    T-ordering (the p-value is non-decreasing in t_obs), found by bisection over the distinct T values with the same
    p-value computation `exact_paired_loss` uses. Returns a frozenset of (b, c)."""
    _, _, n = _check_exact("exact_loss_region", 0, 0, n, margin, alpha)
    np = _np()
    b, c, _, _ = _exact_table(n)
    t = _tango(b, c, n, margin)
    levels = []
    for x in np.sort(t):
        if not levels or x > levels[-1] + _TANGO_TOL * (1.0 + abs(levels[-1])):
            levels.append(float(x))
    lo, hi = -1, len(levels) - 1          # invariant: levels[≤ lo] reject; levels[> hi] do not
    if _exact_pvalue(n, margin, levels[0], grid, margin) > alpha:
        return frozenset()
    lo = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _exact_pvalue(n, margin, levels[mid], grid, margin) <= alpha:
            lo = mid
        else:
            hi = mid - 1
    thr = levels[lo]
    mask = t <= thr + _TANGO_TOL * (1.0 + abs(thr))
    return frozenset((int(x), int(y)) for x, y, k in zip(b, c, mask) if k)


def exact_loss_size(n, region, *, margin=0.10, point_floor=-0.05, grid=None):
    """Exact size of the A5 PASS rule at the H0 boundary: max over the nuisance grid of
    P((b, c) ∈ region ∧ (c − b)/n ≥ point_floor) under trinomial(n; p_c + margin, p_c)."""
    np = _np()
    b, c, _, _ = _exact_table(n)
    keep = np.array([(int(x), int(y)) in region for x, y in zip(b, c)], dtype=bool)
    keep &= (c - b) >= point_floor * n - 1e-9
    cols = np.nonzero(keep)[0]
    if cols.size == 0:
        return 0.0
    return float(_exact_probs(n, margin, grid, margin, cols).sum(axis=1).max())


def verdict_label(d, a="A", b="B"):
    """P359 report label for a `paired_delta`-shaped dict: "<a> better" / "<b> better" (CI excludes 0) or
    "wash (MDE x pp; directional: <pick> (not a shown difference))" (exact tie: "directional: tie")."""
    v = d["verdict"]
    if v == "a_better":
        return f"{a} better"
    if v == "b_better":
        return f"{b} better"
    pick = d.get("directional", "tie")
    who = {"a": a, "b": b}.get(pick)
    tail = "tie" if who is None else f"{who} (not a shown difference)"
    return f"wash (MDE {d['mde'] * 100:.0f} pp; directional: {tail})"


# ------------------------------------------------------------------------ multiple comparisons
def holm(pvalues):
    """Holm-Bonferroni step-down adjusted p-values, in INPUT order, monotone, clamped to 1.0.

    WHY: 3 models x ~6 axes x a few metrics is ~30 tests. At alpha=.05 uncorrected that is
    P(>=1 false positive) = 1 - 0.95^30 = 79% — i.e. the campaign is guaranteed to "find"
    something. Holm controls the family-wise error rate like Bonferroni but is uniformly more
    powerful: the smallest p pays the full m penalty, the next pays m-1, and so on.

    The running max enforces monotonicity in rank (without it a later, larger raw p can come
    out with a SMALLER adjusted value, which is nonsense and reverses conclusions).

    FAILURE MODE: FWER control assumes the family is declared UP FRONT. Adjusting only the
    tests that happened to look interesting is not correction. MINIMUM USABLE n: 1 (a single
    p-value is returned unchanged).
    """
    for p in pvalues:
        if not (0.0 <= p <= 1.0):
            raise ValueError(f"holm: p-values must be in [0,1], got {p!r}")
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, pvalues[i] * (m - rank)))
        adjusted[i] = running
    return adjusted


# --------------------------------------------------------------------------- power / sizing
def _z_pair(alpha, power):
    if alpha not in _Z_ALPHA_2 or power not in _Z_POWER:
        raise ValueError(
            f"unsupported alpha/power ({alpha}, {power}); no scipy here, only tabulated "
            f"z-values: alpha in {sorted(_Z_ALPHA_2)}, power in {sorted(_Z_POWER)}")
    return _Z_ALPHA_2[alpha], _Z_POWER[power]


def mde(n, p_d=0.20, alpha=0.05, power=0.80):
    """Minimum detectable effect (in pass-rate points) for a PAIRED binary comparison on n
    items, via the McNemar normal approximation:

        n = (z_{alpha/2} + z_beta)^2 * p_d / delta^2   =>   delta_min = sqrt(7.849 * p_d / n)

    at the defaults ((1.959964 + 0.841621)^2 = 7.8489). `p_d` is the DISCORDANT-pair rate: the
    fraction of items where the two models disagree. Only discordant pairs carry information —
    items both models pass, or both fail, contribute nothing — so p_d, not the pass rate, sets
    the resolution.

    Report this next to every delta. At the campaign's usual N=15 the floor is 0.323: a 15-item
    axis CANNOT see a 10pp difference, so "no significant difference" there is a statement
    about the sample size and nothing else.

    FAILURE MODE: a normal approximation, so it is optimistic below ~20 discordant pairs, and
    it is only as good as the guessed p_d (default 0.20 is a mid-range guess; measure it from a
    pilot). MINIMUM USABLE n: n=0 returns inf (nothing is detectable), never a
    ZeroDivisionError.
    """
    if n < 0:
        raise ValueError(f"mde: n must be >= 0, got {n}")
    if not (0.0 < p_d <= 1.0):
        raise ValueError(f"mde: p_d must be in (0,1], got {p_d}")
    z_a, z_b = _z_pair(alpha, power)
    if n == 0:
        return math.inf
    return math.sqrt((z_a + z_b) ** 2 * p_d / n)


def n_for(delta, p_d=0.20, alpha=0.05, power=0.80):
    """Items needed to detect a paired difference of `delta` — the inverse of mde(), ROUNDED UP
    (a fractional item does not exist, and rounding down leaves the design underpowered).

    At the defaults: 0.20 -> 40, 0.15 -> 70, 0.10 -> 157, 0.05 -> 628. That last number is the
    honest cost of resolving a 5pp coding difference, and the reason the campaign reports
    intervals instead of claiming small wins.

    FAILURE MODE: same normal approximation and same dependence on the guessed p_d as mde().
    """
    if delta <= 0:
        raise ValueError(f"n_for: delta must be > 0, got {delta}")
    if not (0.0 < p_d <= 1.0):
        raise ValueError(f"n_for: p_d must be in (0,1], got {p_d}")
    z_a, z_b = _z_pair(alpha, power)
    return math.ceil((z_a + z_b) ** 2 * p_d / (delta * delta))


# ------------------------------------------------------------------------ paired significance
def mcnemar_exact(b: int, c: int) -> float:
    """Exact two-sided McNemar test on a paired binary comparison's DISCORDANT pairs: `b` is the
    count of items where A succeeded and B failed, `c` the count where B succeeded and A failed
    (concordant pairs -- both succeed, or both fail -- carry no information and are not passed
    in at all). This is the exact binomial form (Edwards 1948), preferred over the chi-squared
    approximation at the item counts this campaign runs (n < ~100): two-sided
    p = 2 * P(X <= min(b,c) | X ~ Binomial(b+c, 0.5)), clamped to 1.0.

    n=0 (no discordant pairs at all) returns 1.0 -- nothing to test, never a ZeroDivisionError.

    FAILURE MODE: like every binomial test, power is limited by `b+c`, not by the full item
    count -- two models that mostly agree (few discordant pairs) can never reach significance
    here regardless of n. Report `b+c` alongside the p-value so a reader can see this.
    """
    if b < 0 or c < 0:
        raise ValueError(f"mcnemar_exact: b and c must be >= 0, got b={b}, c={c}")
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


# --------------------------------------------------------------------------- throughput view
def time_to_success(t_success, t_fail, p):
    """Expected wall-clock to a FIRST success under independent retries, and its hourly rate.

        E[T] = mean(t_success) + ((1-p)/p) * mean(t_fail)

    `t_success` / `t_fail` are LISTS of observed per-attempt seconds; `p` is the success rate.
    Returns {"expected_s", "successes_per_hour"}.

    WHY this replaces `median_wall / pass_rate`: the Wald expectation of a geometric number of
    attempts multiplies the MEAN attempt time, not the median, and these runs are heavily
    right-tailed — a 14.5-minute median case sits in the same distribution as 2-hour
    degenerate-loop cases. Using the median therefore systematically FLATTERS exactly the
    loop-prone models this metric exists to punish, because the tail it hides IS the defect.
    Note also that failures and successes have different mean durations (a loop runs to the
    token cap; a success stops early), so they are charged separately.

    Prefer `successes_per_hour` for display: it is bounded, comparable, and stays finite as p
    falls. There is deliberately no CI here — the statistic is a ratio to a rate, and any
    bootstrap replicate that happens to contain zero successes sends expected_s to infinity, so
    the upper bound is unusable by construction. Report the components with their own
    intervals.

    FAILURE MODE: assumes attempts are INDEPENDENT and identically distributed — no warm cache,
    no retry that reuses the previous attempt's context. p=0 gives expected_s=inf and 0.0/hour.
    MINIMUM USABLE n: ~5 successes and ~5 failures; below that the two means are single-sample
    guesses and the whole number is a placeholder.
    """
    if not (0.0 <= p <= 1.0):
        raise ValueError(f"time_to_success: p must be in [0,1], got {p}")
    if not t_success:
        raise ValueError("time_to_success: need at least one observed success duration")
    if any(t < 0 for t in list(t_success) + list(t_fail)):
        raise ValueError("time_to_success: durations must be >= 0")
    if p == 0.0:
        return {"expected_s": math.inf, "successes_per_hour": 0.0}
    mean_s = sum(t_success) / len(t_success)
    # No observed failures with p<1 means the failures were dropped (timed out / errored).
    # Charge zero rather than crash: the caller gets an OPTIMISTIC bound, and a missing
    # t_fail is visible in the inputs.
    mean_f = sum(t_fail) / len(t_fail) if t_fail else 0.0
    expected = mean_s + ((1.0 - p) / p) * mean_f
    return {"expected_s": expected,
            "successes_per_hour": 3600.0 / expected if expected > 0 else math.inf}
