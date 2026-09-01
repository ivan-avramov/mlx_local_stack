"""Statistics core for every quality axis.

The campaign's early numbers were single-sample (k=1) point estimates with no intervals, so
published deltas sat inside the noise floor. Everything here exists to stop that recurring:

* ITEMS ARE THE UNIT OF ANALYSIS, never the pooled N*k trials. Two samples of one item are not
  two items — they are correlated. `pass_at_1` averages item means; `cluster_bootstrap` is
  two-stage precisely so that correlation is priced in.
* NO INTERVAL, NO CLAIM. A delta is reported with its CI and with the axis MDE, so "we cannot
  see an effect this small at N=15" is visible instead of inferred.
* FAILING TO REJECT IS NOT EQUIVALENCE. `paired_delta` says "inconclusive" and means it.

Stdlib only, on purpose: this module is imported by tooling that runs in `.venv-bench` (no
numpy/scipy) as well as in the full venvs. Every function is pure; every randomized function
takes an explicit `seed` and is byte-reproducible for it.

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
def paired_delta(a_per_item, b_per_item, iters=10000, seed=0, margin=0.05, strata=None):
    """Two-stage PAIRED bootstrap of pass@1(a) - pass@1(b) over the SHARED item set.

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

    `verdict` (TOST-style):
      "a_better"/"b_better"  the CI excludes 0;
      "equivalent"           the CI lies entirely inside (-margin, +margin) — a POSITIVE claim
                             of practical equivalence, only makeable when the interval is
                             tighter than the margin;
      "inconclusive"         everything else. Deliberately NOT "indistinguishable": failing to
                             reject is not evidence of equivalence, it is usually just a small
                             n, and `mde` in the result says how small.

    FAILURE MODE: `margin` is a judgment call about what difference matters — an "equivalent"
    verdict is only as meaningful as the margin it was declared against, so report the margin.
    MINIMUM USABLE n: n_for(delta) — at 15 items nothing under ~32pp is resolvable, so most
    "inconclusive" verdicts are a sample-size statement, not a model statement.
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
    lo, hi = _percentile(reps, 0.025), _percentile(reps, 0.975)
    delta = (pass_at_1({i: a_per_item[i] for i in ids})
             - pass_at_1({i: b_per_item[i] for i in ids}))
    if lo > 0:
        verdict = "a_better"
    elif hi < 0:
        verdict = "b_better"
    elif -margin < lo and hi < margin:
        verdict = "equivalent"
    else:
        verdict = "inconclusive"
    return {"delta": delta, "lo": lo, "hi": hi, "verdict": verdict, "n_items": n,
            "mde": mde(n)}


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
