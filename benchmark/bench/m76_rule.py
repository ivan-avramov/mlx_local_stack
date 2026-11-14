"""M76 §8 decision rule (B7, spec v1.4): per-axis verdicts, the session × arm interaction flag, and the
pre-registered look plans (A7 / A8 α* and A5 n read from the committed simulation report).

Verdicts are mutually exclusive, tested in order: PASS (point ≥ floor AND loss bound −lo ≤ margin; annotated
"loss_shown_within_tolerance" when hi < 0), LOSS (hi < 0 AND point < floor), else UNDECIDED. Stage 3 / 4 calls
`axis_verdict`: A1 / A7 / A8 through `loss_bound` → `exact_interval_values` (the exact item bootstrap the simulation
certifies), A5 through `verdict_a5` (exact unconditional test). Stdlib at import; the exact functions lazily import
numpy.
"""
import bisect
import hashlib
import json
from fractions import Fraction
from pathlib import Path

from bench import stats

ALPHA_TOTAL = 0.025          # one-sided α per axis (§8)
POINT_FLOOR = -0.05
LOSS_MARGIN = 0.10
PER_SESSION_ALPHA = 0.025    # v1.4: descriptive per-session results beside an agentic verdict (95 % two-sided)
_EPS = 1e-12                 # float slack on the two PASS boundaries (a computed −0.05 may read −0.05000000000000001)

PASS, LOSS, UNDECIDED = "PASS", "LOSS", "UNDECIDED"
LOSS_SHOWN = "loss_shown_within_tolerance"


class Verdict(str):
    """The verdict string ("PASS" / "LOSS" / "UNDECIDED") carrying its context: `.annotation` (None or
    "loss_shown_within_tolerance"), `.loss_bound` (−lo), `.delta`, `.lo`, `.hi`, `.label`. Also readable as a mapping
    (`v["verdict"]`, `v["annotation"]`, …) and via `.as_dict()`."""

    _FIELDS = ("verdict", "annotation", "loss_bound", "delta", "lo", "hi", "label")

    def __new__(cls, verdict, *, annotation, loss_bound, delta, lo, hi, label):
        obj = super().__new__(cls, verdict)
        obj.verdict, obj.annotation, obj.loss_bound = verdict, annotation, loss_bound
        obj.delta, obj.lo, obj.hi, obj.label = delta, lo, hi, label
        return obj

    def __getitem__(self, key):
        if isinstance(key, str):
            if key not in self._FIELDS:
                raise KeyError(key)
            return getattr(self, key)
        return str.__getitem__(self, key)

    def get(self, key, default=None):
        return getattr(self, key) if key in self._FIELDS else default

    def as_dict(self):
        return {k: getattr(self, k) for k in self._FIELDS}


def _pp(x):
    return f"{x * 100:.1f} pp"


def verdict(delta, lo, hi, *, point_floor=POINT_FLOOR, loss_margin=LOSS_MARGIN):
    """§8 verdict at one look from the point estimate and the look's two-sided interval [lo, hi] (X − N16)."""
    if lo > hi:
        raise ValueError(f"verdict: lo {lo!r} > hi {hi!r}")
    loss_bound = -lo
    if delta >= point_floor - _EPS and loss_bound <= loss_margin + _EPS:
        if hi < 0:
            return Verdict(PASS, annotation=LOSS_SHOWN, loss_bound=loss_bound, delta=delta, lo=lo, hi=hi,
                           label=f"PASS — loss shown, within tolerance ({_pp(loss_bound)})")
        return Verdict(PASS, annotation=None, loss_bound=loss_bound, delta=delta, lo=lo, hi=hi,
                       label=f"PASS (loss bound {_pp(loss_bound)})")
    if hi < 0 and delta < point_floor:
        return Verdict(LOSS, annotation=None, loss_bound=loss_bound, delta=delta, lo=lo, hi=hi,
                       label=f"LOSS (point {_pp(delta)}, interval excludes 0)")
    tail = "; directional (not a shown difference)" if lo <= 0 <= hi else ""
    return Verdict(UNDECIDED, annotation=None, loss_bound=loss_bound, delta=delta, lo=lo, hi=hi,
                   label=f"UNDECIDED — loss not ruled out above {_pp(max(loss_bound, 0.0))}{tail}")


def loss_interval(result, *, exact_alpha=None):
    """(delta, lo, hi) of a `paired_delta` / `paired_session_delta` result, with §8's zero-discordance substitution:
    a degenerate interval with no discordant item uses lo = −(1 − α^(1/n_items)) at the look's one-sided α.

    The α is required: `exact_alpha`, or the result's own `exact_alpha` metadata (present only on non-default
    `paired_delta` calls). Neither → ValueError (never the 0.05 `discordance_upper95`); both and different →
    ValueError. Descriptive only: the M76 verdict path is `loss_bound` / `axis_verdict` (exact bootstrap)."""
    meta = result.get("exact_alpha")
    if exact_alpha is None and meta is None:
        raise ValueError("loss_interval: the look's one-sided exact_alpha is required (the result carries no "
                         "alpha metadata; the default 0.05 bound is never used)")
    if exact_alpha is not None and meta is not None and meta != exact_alpha:
        raise ValueError(f"loss_interval: exact_alpha {exact_alpha!r} differs from the result's {meta!r}")
    alpha = exact_alpha if exact_alpha is not None else meta
    if not (isinstance(alpha, (int, float)) and 0.0 < alpha < 1.0):
        raise ValueError(f"loss_interval: exact_alpha must be in (0, 1), got {alpha!r}")
    if "discordant_items" in result:
        no_disc = result["discordant_items"] == 0
    else:
        no_disc = result.get("discordance_upper") is not None or result.get("discordance_upper95") is not None
    lo = result["lo"]
    if result.get("degenerate") and no_disc:
        lo = min(lo, -(1 - alpha ** (1 / result["n_items"])))
    return result["delta"], lo, result["hi"]


def verdict_of(result, *, exact_alpha=None, **kw):
    """`verdict` applied to a stats result dict (zero-discordance cells use the exact bound at the required α; see
    `loss_interval`)."""
    return verdict(*loss_interval(result, exact_alpha=exact_alpha), **kw)


# ------------------------------------------------------------------- exact item bootstrap (the M76 loss bound)
_PRUNE = 1e-18


def _np():
    import numpy
    return numpy


def _conv(a, b):
    np = _np()
    (oa, pa), (ob, pb) = a, b
    out = np.convolve(pa, pb)
    nz = np.nonzero(out >= _PRUNE)[0]
    if nz.size == 0:
        return (oa + ob, out[:1])
    lo, hi = int(nz[0]), int(nz[-1]) + 1
    return (oa + ob + lo, out[lo:hi])


_NFOLD = {}


def _nfold(hist, n):
    """Distribution (offset, probs) of the sum of n iid draws from the empirical integer distribution `hist`
    (tuple of (value, count), counts summing to n)."""
    key = (hist, n)
    if key in _NFOLD:
        return _NFOLD[key]
    np = _np()
    vmin = min(v for v, _ in hist)
    vmax = max(v for v, _ in hist)
    base = np.zeros(vmax - vmin + 1)
    for v, c in hist:
        base[v - vmin] += c / n
    result, power, e = (0, np.ones(1)), (vmin, base), n
    while e:
        if e & 1:
            result = _conv(result, power)
        e >>= 1
        if e:
            power = _conv(power, power)
    _NFOLD[key] = result
    return result


def _hist_key(strata_vals):
    hists = []
    for vals in strata_vals:
        if any(vals):
            c = {}
            for v in vals:
                c[v] = c.get(v, 0) + 1
            hists.append((tuple(sorted(c.items())), len(vals)))
    return tuple(sorted(hists))


_CDF = {}


def _ideal_cdf(key):
    """(offset, cumulative list) of the ideal item bootstrap of Σ v for a `_hist_key`."""
    if key not in _CDF:
        np = _np()
        dist = (0, np.ones(1))
        for h, n in key:
            dist = _conv(dist, _nfold(h, n))
        off, probs = dist
        cum = np.cumsum(probs / probs.sum())
        _CDF[key] = (off, cum.tolist())
    return _CDF[key]


def _quantiles(cdf, q):
    """(lo_x, hi_x) integer sums: lo = F⁻¹(q), hi = F⁻¹(1 − q) (first index with cum ≥ level − 1e-12)."""
    off, cum = cdf
    last = len(cum) - 1
    lo = min(bisect.bisect_left(cum, q - 1e-12), last)
    hi = min(bisect.bisect_left(cum, 1 - q - 1e-12), last)
    return off + lo, off + hi


def _check_one_sided(fn, alpha):
    if isinstance(alpha, bool) or not (isinstance(alpha, (int, float)) and 0.0 < alpha < 0.5):
        raise ValueError(f"{fn}: alpha must be a one-sided level in (0, 0.5), got {alpha!r}")


def exact_interval_values(groups, n_sessions, alphas, *, any_discordant):
    """THE M76 loss-bound computation for A1 / A7 / A8 (shared by `loss_bound` and `bench.m76_sim`).

    `groups`: per-stratum lists of integer item values v_i = Σ_s d_s (d_s = X_s − N16_s over `n_sessions` sessions;
    an item's sessions stay together). The exact (infinite-resample) item bootstrap, items resampled within strata,
    of the statistic Σ v / (n_items · n_sessions); per one-sided α in `alphas`: lo = F⁻¹(α), hi = F⁻¹(1 − α) (the
    two-sided 1 − 2α interval). A degenerate interval (lo == hi) with no discordant item-session
    (`any_discordant` False) uses lo = min(lo, −(1 − α^(1/n_items))). Returns one dict per α: {alpha, delta, lo, hi,
    loss_bound (= −lo), degenerate, exact_bound_used, verdict (`Verdict`)}."""
    n = sum(len(g) for g in groups)
    if n == 0 or n_sessions < 1:
        raise ValueError("exact_interval_values: need ≥ 1 item and ≥ 1 session")
    denom = n * n_sessions
    tot = sum(sum(g) for g in groups)
    if not any_discordant and any(any(g) for g in groups):
        raise ValueError("exact_interval_values: nonzero item values with any_discordant=False")
    cdf = _ideal_cdf(_hist_key(groups))
    delta = tot / denom
    out = []
    for a in alphas:
        _check_one_sided("exact_interval_values", a)
        lo_x, hi_x = _quantiles(cdf, a)
        lo, hi = lo_x / denom, hi_x / denom
        degenerate = lo == hi
        used = degenerate and not any_discordant
        if used:
            lo = min(lo, -(1 - a ** (1 / n)))
        out.append(dict(alpha=a, delta=delta, lo=lo, hi=hi, loss_bound=-lo, degenerate=degenerate,
                        exact_bound_used=used, verdict=verdict(delta, lo, hi)))
    return out


def loss_bound(a, b, *, alpha, strata=None):
    """The M76 loss bound and verdict of X (`a`) vs N16 (`b`) at one look, from real rows.

    `a` / `b` map item_id → {session_id: 0/1} (identical item and session sets, else ValueError); `alpha` = the
    look's one-sided α (from `axis_plan`; required); `strata` = optional {item_id: key} (items resampled within
    strata). Computed by `exact_interval_values` (the same function the simulation uses). Returns {alpha, delta, lo,
    hi, loss_bound, degenerate, exact_bound_used, verdict, n_items, n_sessions, discordant_items}."""
    _check_one_sided("loss_bound", alpha)
    ids, sess, d = _session_rows("loss_bound", a, b)
    vals = [sum(row) for row in d]
    if strata is None:
        groups = [vals]
    else:
        missing = [i for i in ids if i not in strata]
        if missing:
            raise ValueError(f"loss_bound: items without a stratum: {missing[:10]}")
        g = {}
        for i, v in zip(ids, vals):
            g.setdefault(strata[i], []).append(v)
        groups = [g[k] for k in sorted(g, key=repr)]
    disc = sum(1 for row in d if any(row))
    (r,) = exact_interval_values(groups, len(sess), [alpha], any_discordant=disc > 0)
    r.update(n_items=len(ids), n_sessions=len(sess), discordant_items=disc)
    return r


def session_disagreement(per_session):
    """DESCRIPTIVE per-session listing only (v1.1, C331: not a flag; the rule's flag is `session_interaction`).
    Pairs (s, t), s < t in sorted order, whose point estimates have strictly opposite signs AND each session's 95 %
    interval excludes the other's point. `per_session` maps session → dict with delta / lo / hi."""
    keys = sorted(per_session, key=str)
    out = []
    for x, s in enumerate(keys):
        for t in keys[x + 1:]:
            ds, dt = per_session[s], per_session[t]
            if not (ds["delta"] * dt["delta"] < 0):
                continue
            s_excl = dt["delta"] < ds["lo"] or dt["delta"] > ds["hi"]
            t_excl = ds["delta"] < dt["lo"] or ds["delta"] > dt["hi"]
            if s_excl and t_excl:
                out.append((s, t))
    return out


# ------------------------------------------------------------------------------------------- A5 exact rule (v1.1)
A5_N_RANGE = (42, 120)
A5_N_STEP = 6                # two tasks × three rungs, equal cells
LOSS_TEST_ALPHA = 0.05       # two-sided exact binomial on b | b + c for A5 LOSS
A5_TASK_GATE = Fraction(-5, 100)   # per-task point gate (retrieval, chain-4): each task's point ≥ −5 pp (M76 §8)


class A5Verdict(tuple):
    """`(verdict, bound)` from `verdict_a5`; also `.verdict`, `.bound`, `.annotation`, `.delta`, `.pvalue`,
    `.loss_pvalue`, `.b`, `.c`, `.n`, `.label`, and mapping access (`v["verdict"]`, `v["bound"]`, …)."""

    _FIELDS = ("verdict", "bound", "bound_attained", "annotation", "delta", "pvalue", "reject", "loss_pvalue", "b",
               "c", "n", "label")

    def __new__(cls, **kw):
        obj = super().__new__(cls, (kw["verdict"], kw["bound"]))
        for k in cls._FIELDS:
            setattr(obj, k, kw[k])
        return obj

    def __getitem__(self, key):
        if isinstance(key, str):
            if key not in self._FIELDS:
                raise KeyError(key)
            return getattr(self, key)
        return tuple.__getitem__(self, key)

    def get(self, key, default=None):
        return getattr(self, key) if key in self._FIELDS else default

    def as_dict(self):
        return {k: getattr(self, k) for k in self._FIELDS}


def verdict_a5(b, c, n, *, point_floor=POINT_FLOOR, loss_margin=LOSS_MARGIN, alpha=ALPHA_TOTAL):
    """A5 verdict (v1.1): `b` = #(N16 pass, X fail), `c` = #(X pass, N16 fail) over all `n` A5 items pooled.
    PASS ⇔ delta = (c − b)/n ≥ floor AND `stats.exact_paired_loss` rejects H0 (loss ≥ margin) at `alpha` (annotated
    "loss_shown_within_tolerance" when the two-sided exact binomial also shows b > c); LOSS ⇔ delta < floor AND the
    two-sided exact binomial of b | b + c (α 0.05) rejects with b > c; else UNDECIDED. Returns `A5Verdict`
    (unpacks as `(verdict, bound)`)."""
    r = stats.exact_paired_loss(b, c, n, margin=loss_margin, alpha=alpha)
    delta, bound = r["delta"], r["bound"]
    p_loss = stats.mcnemar_exact(b, c)
    shown = b > c and p_loss <= LOSS_TEST_ALPHA
    if delta >= point_floor - _EPS and r["reject"]:
        v, ann = PASS, (LOSS_SHOWN if shown else None)
        label = (f"PASS — loss shown, within tolerance ({_pp(bound)})" if shown else f"PASS (loss bound {_pp(bound)})")
    elif delta < point_floor and shown:
        v, ann, label = LOSS, None, f"LOSS (point {_pp(delta)}, exact binomial p {p_loss:.4g})"
    else:
        v, ann = UNDECIDED, None
        label = f"UNDECIDED — loss not ruled out above {_pp(bound)}"
    return A5Verdict(verdict=v, bound=bound, bound_attained=r["bound_attained"], annotation=ann, delta=delta,
                     pvalue=r["pvalue"], reject=r["reject"], loss_pvalue=p_loss, b=b, c=c, n=n, label=label)


_A5_REGIONS = {}


def a5_rejection_region(n, *, loss_margin=LOSS_MARGIN, alpha=ALPHA_TOTAL):
    """(cached) frozenset of the (b, c), b + c ≤ n, at which `exact_paired_loss` rejects H0 at the margin (default
    grid)."""
    key = (n, loss_margin, alpha)
    if key not in _A5_REGIONS:
        _A5_REGIONS[key] = stats.exact_loss_region(n, margin=loss_margin, alpha=alpha)
    return _A5_REGIONS[key]


def a5_pass_region(n, *, point_floor=POINT_FLOOR, loss_margin=LOSS_MARGIN, alpha=ALPHA_TOTAL):
    """(b, c) at which `verdict_a5` gives PASS: the rejection region ∩ {(c − b)/n ≥ floor}."""
    return frozenset((b, c) for b, c in a5_rejection_region(n, loss_margin=loss_margin, alpha=alpha)
                     if (c - b) / n >= point_floor - _EPS)


def a5_exact_size(n, *, point_floor=POINT_FLOOR, loss_margin=LOSS_MARGIN, alpha=ALPHA_TOTAL):
    """max over the nuisance grid of P(rejection region ∧ delta ≥ floor) at the H0 boundary (margin)."""
    return stats.exact_loss_size(n, a5_rejection_region(n, loss_margin=loss_margin, alpha=alpha),
                                 margin=loss_margin, point_floor=point_floor)


# ------------------------------------------------------------------------------------ session × arm interaction
INTERACTION_ALPHA = 0.05


def _session_rows(fn, a, b):
    """Validated (ids, sessions, d) with d[i] = tuple of a_s − b_s over the sorted sessions."""
    a_ids, b_ids = set(a), set(b)
    if a_ids != b_ids:
        raise ValueError(f"{fn}: item sets differ — a-only={sorted(a_ids - b_ids, key=str)}, "
                         f"b-only={sorted(b_ids - a_ids, key=str)}")
    ids = sorted(a_ids, key=str)
    if not ids:
        raise ValueError(f"{fn}: no items")
    sessions = first = None
    for i in ids:
        sa, sb = set(a[i]), set(b[i])
        if sa != sb:
            raise ValueError(f"{fn}: item {i!r}: session sets differ — a-only={sorted(sa - sb, key=str)}, "
                             f"b-only={sorted(sb - sa, key=str)}")
        if not sa:
            raise ValueError(f"{fn}: item {i!r} has no sessions")
        if sessions is None:
            sessions, first = sa, i
        elif sa != sessions:
            raise ValueError(f"{fn}: item {i!r} sessions {sorted(sa, key=str)} differ from item {first!r} "
                             f"sessions {sorted(sessions, key=str)}")
    sess = sorted(sessions, key=str)
    return ids, sess, [tuple(a[i][s] - b[i][s] for s in sess) for i in ids]


def _sumsq(cols):
    return sum(x * x for x in cols)


def session_interaction(a, b, *, iters=10000, seed=426):
    """Session × arm interaction permutation test (v1.1, P26; replaces `session_disagreement` as the rule's flag).

    `a` / `b` map item_id → {session_id: 0/1} (identical item and session sets, else ValueError). d_s = a_s − b_s.
    Statistic: the (population) variance across sessions of the per-session mean difference. Null: within each item
    independently, a uniformly random permutation of which session each d_s belongs to. p = (1 + #{perm ≥ obs}) /
    (1 + iters); `flag` = p < 0.05 (blocks a ship recommendation → the operator). Comparisons are exact (integer
    per-session sums; the variance is monotone in Σ_s S_s² because Σ_s S_s is permutation-invariant).
    Returns {statistic, pvalue, flag, iters, seed, n_items, n_sessions, per_session_delta}."""
    import random
    if not (isinstance(iters, int) and iters >= 1):
        raise ValueError(f"session_interaction: iters must be a positive int, got {iters!r}")
    ids, sess, d = _session_rows("session_interaction", a, b)
    n, k = len(ids), len(sess)
    sums = [sum(row[s] for row in d) for s in range(k)]
    obs = _sumsq(sums)
    mean = sum(sums) / (k * n)
    stat = sum((x / n - mean) ** 2 for x in sums) / k
    fixed = [0] * k
    active = []
    for row in d:
        if len(set(row)) > 1:
            active.append(list(row))
        else:
            for s in range(k):
                fixed[s] += row[s]
    rng = random.Random(seed)
    ge = 0
    if active:
        for _ in range(iters):
            tot = list(fixed)
            for row in active:
                rng.shuffle(row)
                for s in range(k):
                    tot[s] += row[s]
            if _sumsq(tot) >= obs:
                ge += 1
    else:
        ge = iters                     # every permutation reproduces the observed arrangement
    p = (1 + ge) / (1 + iters)
    return {"statistic": stat, "pvalue": p, "flag": p < INTERACTION_ALPHA, "iters": iters, "seed": seed,
            "n_items": n, "n_sessions": k, "per_session_delta": {s: sums[j] / n for j, s in enumerate(sess)}}


# ------------------------------------------------------------------------------------------------ pre-registered plans
# v1.4: the decision statistic (paired_delta / paired_session_delta stay descriptive only).
_EXACT_STAT = "exact item bootstrap (m76_rule.exact_interval_values via axis_verdict)"
_A5_STAT = "exact_paired_loss"  # via m76_rule.verdict_a5
_AXES = {
    "A1": dict(name="Math500", statistic=_EXACT_STAT, unit="items", sizes=(100, 300), fractions=(1 / 3, 1.0),
               items=300, sessions=1, strata=None),
    "A7": dict(name="tg1", statistic=_EXACT_STAT, unit="sessions", sizes=(2, 3), fractions=(2 / 3, 1.0),
               items=43, sessions=3, strata=None),
    "A5": dict(name="long context (retrieval + chain-4)", statistic=_A5_STAT, unit="items",
               sizes=(None,), fractions=(1.0,), items=None, sessions=1, strata="task x rung", n_range=A5_N_RANGE),
    "A8": dict(name="tg2 decider", statistic=_EXACT_STAT, unit="items", sizes=(80,), fractions=(1.0,),
               items=80, sessions=2, strata=None),
}

REPORT_JSON = Path(__file__).resolve().parent.parent / "results" / "m76" / "b7-simulation" / "report.json"


def load_report(path=None):
    """(report dict, sha256 of its bytes) of the committed B7 simulation report, or (None, None) when absent."""
    p = Path(path) if path is not None else REPORT_JSON
    if not p.exists():
        return None, None
    raw = p.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _check_a5_n(n):
    lo, hi = A5_N_RANGE
    if not (isinstance(n, int) and lo <= n <= hi):
        raise ValueError(f"axis_plan: A5 n must be an int in {A5_N_RANGE}, got {n!r}")


def axis_plan(axis, *, keep_look1=None, n=None, calibrated=True, report=None):
    """The pre-registered looks of `axis` ("A1", "A7", "A5", "A8") and their nominal one-sided alphas.

    Each look: {look, fraction, size, unit, alpha, interval_alpha (= 2α, two-sided), exact_alpha (= α)}.
    - A1 (v1 rule, unchanged): O'Brien–Fleming looks at n 100 / 300; `keep_look1=False` → one look at 300, α 0.025.
    - A5 (v1.1): one look, `exact_paired_loss` at α 0.025, margin 0.10; n = `n` or, by default, the committed
      report's sized n (42 ≤ n ≤ 120).
    - A5 (B7.1 v1.4, C339): by default (`n` None, `calibrated`), when the report carries B7.1's `variants`, the
      registered A5-2L plan: two looks with the sizes / α of `variants.A5-2L.looks` (O'Brien–Fleming at t₁ = n₁ / n₂);
      look-1 LOSS stops (`look1_loss_stops`); refuses a missing / unavailable / unsafe variant. A B7-only report
      (no `variants`), an explicit `n` or `calibrated=False` keep B7's single look.
    - A7 / A8 (v1.1): calibrated (default) → the least-favourable α* of the committed report (`report`: a path,
      default `REPORT_JSON`); A7 has two looks only when the report keeps look 1 (`keep_look1=True` otherwise raises;
      `keep_look1=False` forces the single look). `calibrated=False` → the v1 O'Brien–Fleming nominal plan
      (`keep_look1` default True), as the simulation's uncalibrated reference.
    Calibrated plans carry `calibrated`, `alpha_star`, `binding_cell`, `report_sha256`.
    - v1.3 (C336): when the committed report fixes an axis's α* (`alpha_star_fixed`, A8: 0.001), that α* is the plan's
      (one look); the plan also carries `alpha_star_source` and the context `calibrated_alpha_star`.
    """
    if axis not in _AXES:
        raise ValueError(f"axis_plan: unknown axis {axis!r}; pre-registered: {sorted(_AXES)}")
    spec = _AXES[axis]
    sizes, fractions = spec["sizes"], spec["fractions"]
    rep = sha = None
    if axis == "A5" and n is None and calibrated:
        rep, sha = load_report(report)
        if rep is not None and "variants" in rep:
            return _a5_registered_plan(spec, rep, sha, report)
        n = rep["axes"]["A5"]["n"] if rep is not None and "A5" in rep.get("axes", {}) else None
    if axis == "A5" and n is not None:
        _check_a5_n(n)
    if axis == "A5":
        sizes = (n,)
    if axis in ("A7", "A8") and calibrated:
        return _calibrated_plan(axis, spec, keep_look1, report)
    if keep_look1 is None:
        keep_look1 = True
    if not keep_look1 and len(sizes) > 1:
        sizes, fractions = sizes[-1:], (1.0,)
    alphas = stats.obf_looks(fractions, ALPHA_TOTAL)
    looks = [dict(look=k + 1, fraction=t, size=sz, unit=spec["unit"], alpha=a, interval_alpha=2 * a, exact_alpha=a)
             for k, (t, sz, a) in enumerate(zip(fractions, sizes, alphas))]
    out = dict(axis=axis, name=spec["name"], statistic=spec["statistic"], alpha_total=ALPHA_TOTAL,
               two_look=len(looks) == 2, looks=looks, strata=spec["strata"], items=spec["items"],
               sessions=spec["sessions"], calibrated=False)
    if axis == "A5":
        out.update(n_range=A5_N_RANGE, n_step=A5_N_STEP, items=n, loss_margin=LOSS_MARGIN, point_floor=POINT_FLOOR,
                   loss_test="two-sided exact binomial on b | b + c, alpha 0.05, b > c", report_sha256=sha)
        for lk in looks:
            lk.pop("interval_alpha")
            lk["test"] = "exact_paired_loss"
    return out


def _a5_registered_plan(spec, rep, sha, report):
    """v1.4 (C339): A5-2L's two looks, sizes and α read from the committed report's `variants.A5-2L` (never retyped);
    refuses when the variant is missing, unavailable, unsafe or not two looks."""
    v = rep["variants"].get("A5-2L")
    src = report if report is not None else REPORT_JSON
    if not v or not v.get("available") or v.get("safe") is not True or len(v.get("looks") or ()) != 2:
        raise ValueError(f"axis_plan: the registered A5-2L plan (C339) is missing, unavailable, unsafe or not two "
                         f"looks in {src} (run `python -m bench.m76_sim`)")
    looks = []
    for k, w in enumerate(v["looks"]):
        _check_a5_n(w["size"])
        looks.append(dict(look=k + 1, fraction=w["fraction"], size=w["size"], unit=spec["unit"], alpha=w["alpha"],
                          exact_alpha=w["alpha"], test="exact_paired_loss"))
    return dict(axis="A5", name=spec["name"], statistic=spec["statistic"], alpha_total=ALPHA_TOTAL, two_look=True,
                looks=looks, strata=spec["strata"], items=looks[-1]["size"], sessions=spec["sessions"],
                calibrated=False, n_range=A5_N_RANGE, n_step=A5_N_STEP, loss_margin=LOSS_MARGIN,
                point_floor=POINT_FLOOR, loss_test="two-sided exact binomial on b | b + c, alpha 0.05, b > c",
                look1_loss_stops=True, task_gate=float(A5_TASK_GATE), plan_source="variants.A5-2L",
                exact_size=(v.get("exact") or {}).get("size"), decision="C339", report_sha256=sha)


def _calibrated_plan(axis, spec, keep_look1, report):
    rep, sha = load_report(report)
    ax = (rep or {}).get("axes", {}).get(axis, {})
    cal = ax.get("calibration") if rep is not None else None
    fixed = ax.get("alpha_star_fixed")
    if fixed is not None and cal is not None:
        # v1.3 (C336): operator-fixed α*; the committed calibration is context only
        if keep_look1 is True:
            raise ValueError(f"axis_plan: {axis} has one look at the fixed α* {fixed}")
        looks =[dict(look=1, fraction=1.0, size=spec["sizes"][-1], unit=spec["unit"], alpha=fixed,
                      interval_alpha=2 * fixed, exact_alpha=fixed)]
        return dict(axis=axis, name=spec["name"], statistic=spec["statistic"], alpha_total=ALPHA_TOTAL,
                    two_look=False, looks=looks, strata=spec["strata"], items=spec["items"],
                    sessions=spec["sessions"], calibrated=True, alpha_star=fixed,
                    alpha_star_source=ax.get("alpha_star_source", "fixed"),
                    calibrated_alpha_star=cal.get("alpha_star"), binding_cell=cal.get("binding_cell"),
                    report_sha256=sha)
    if cal is None or cal.get("alpha_star") is None:
        raise ValueError(f"axis_plan: no committed calibrated α* for {axis} in "
                         f"{report if report is not None else REPORT_JSON} (run `python -m bench.m76_sim`)")
    a1 = cal.get("look1") or {}
    kept = bool(a1.get("keep"))
    if keep_look1 is True and not kept:
        raise ValueError(f"axis_plan: the committed report does not keep {axis}'s look 1")
    two = kept and keep_look1 is not False
    if two:
        alphas, sizes, fractions = [a1["alpha_star"], a1["alpha_star_look2"]], spec["sizes"], spec["fractions"]
    else:
        alphas, sizes, fractions = [cal["alpha_star"]], spec["sizes"][-1:], (1.0,)
    looks = [dict(look=k + 1, fraction=t, size=sz, unit=spec["unit"], alpha=a, interval_alpha=2 * a, exact_alpha=a)
             for k, (t, sz, a) in enumerate(zip(fractions, sizes, alphas))]
    return dict(axis=axis, name=spec["name"], statistic=spec["statistic"], alpha_total=ALPHA_TOTAL, two_look=two,
                looks=looks, strata=spec["strata"], items=spec["items"], sessions=spec["sessions"], calibrated=True,
                alpha_star=cal["alpha_star"], binding_cell=cal["binding_cell"], report_sha256=sha)


# ------------------------------------------------------------------------------------------------- A8 HOLD (v1.4)
A8_HOLD_PP = -0.20           # C339: any language's decider point estimate < −20 pp → HOLD (blocking)
_A8_HOLD = Fraction(-20, 100)


def _below(x, threshold):
    """x < threshold, exact for int / Fraction; floats with `_EPS` slack (a computed −0.2 may read −0.20000000000000004)."""
    if isinstance(x, (int, Fraction)) and not isinstance(x, bool):
        return Fraction(x) < threshold
    return float(x) < float(threshold) - _EPS


def a8_hold(per_language):
    """Large-harm HOLD (C339): `per_language` maps language → the decider's point estimate (float / Fraction, or a
    dict with "delta"). HOLD ⇔ some language's point < `A8_HOLD_PP` (−20 pp exactly does not fire); blocking.
    Returns {hold, blocking, threshold, languages (sorted, firing), per_language (floats)}."""
    if not per_language:
        raise ValueError("a8_hold: no per-language decider estimates")
    pts = {k: (v["delta"] if isinstance(v, dict) else v) for k, v in per_language.items()}
    fired = sorted((k for k, x in pts.items() if _below(x, _A8_HOLD)), key=str)
    return dict(hold=bool(fired), blocking=bool(fired), threshold=A8_HOLD_PP, languages=fired,
                per_language={k: float(x) for k, x in pts.items()})


def _groups_of(fn, what, mapping, ids):
    missing = [i for i in ids if i not in mapping]
    if missing:
        raise ValueError(f"{fn}: items without a {what}: {missing[:10]}")
    g = {}
    for i in ids:
        g.setdefault(mapping[i], []).append(i)
    return g


def _a5_task_gates(ids, d, tasks):
    """{task: {n, delta, pass}} on this look's items: each task's point (c − b) / n_t ≥ −5 pp (exact)."""
    row = dict(zip(ids, d))
    out = {}
    for t, items in sorted(_groups_of("axis_verdict", "task", tasks, ids).items(), key=lambda kv: repr(kv[0])):
        s = Fraction(sum(row[i][0] for i in items), len(items))
        out[t] = dict(n=len(items), delta=float(s), **{"pass": s >= A5_TASK_GATE})
    return out


# ------------------------------------------------------------------------------------------- stage-3 / 4 verdict
def axis_verdict(axis, look, a, b, *, strata=None, report=None, interaction_iters=10000, seed=426, tasks=None,
                 languages=None):
    """The §8 verdict of X (`a`) vs N16 (`b`) on `axis` at `look` (1-based), from real rows.

    `a` / `b` map item_id → {session_id: 0/1}; A1 and A5 hold a single session. α = `axis_plan(axis,
    report=report)["looks"][look − 1]["alpha"]` (the committed plan; never a default). A1 / A7 / A8: `loss_bound`
    (exact item bootstrap, the simulation's computation) on all sessions at α; per session descriptive only, at
    one-sided `PER_SESSION_ALPHA` 0.025 (95 % two-sided, v1.4; independent of α); and `session_interaction` (k ≥ 2;
    its flag blocks a ship recommendation). A5: `verdict_a5` on the pooled (b, c, n).
    Item / session counts that differ from the plan's are listed in `size_warnings` (→ the operator).
    v1.4 (C339): A5 runs the registered two looks at the look's α (look 2 on the cumulative rows); `stop` / `next_look`
    say whether the look decides (PASS or LOSS, or the final look) or UNDECIDED goes on to look 2. `tasks` = optional
    {item_id: task}: the per-task point gates (each ≥ −5 pp) on this look's items → `task_gates`, `task_gates_pass`
    and `clean` (PASS ∧ gates; a gate failure never triggers look 2); None when `tasks` is not given. A8: `languages`
    = optional {item_id: language} → `hold` = `a8_hold` of each language's point over all sessions (None without it);
    `blocking` = interaction flag ∨ HOLD.
    Returns {axis, look, alpha, verdict, annotation, label, delta, lo, hi, loss_bound, n_items, n_sessions,
    discordant_items, exact_bound_used, per_session, per_session_alpha (A1 / A7 / A8), interaction, interaction_flag,
    expected_items, expected_sessions, size_warnings, report_sha256, blocking; A5: a5, stop, next_look, task_gates,
    task_gates_pass, clean; A8: hold}."""
    if tasks is not None and axis != "A5":
        raise ValueError(f"axis_verdict: `tasks` (per-task gates) applies to A5 only, not {axis}")
    if languages is not None and axis != "A8":
        raise ValueError(f"axis_verdict: `languages` (the HOLD) applies to A8 only, not {axis}")
    plan = axis_plan(axis, report=report)
    looks = plan["looks"]
    if isinstance(look, bool) or not (isinstance(look, int) and 1 <= look <= len(looks)):
        raise ValueError(f"axis_verdict: {axis} has looks 1..{len(looks)}, got {look!r}")
    lk = looks[look - 1]
    alpha = lk["alpha"]
    ids, sess, d = _session_rows("axis_verdict", a, b)
    n, k = len(ids), len(sess)
    if axis in ("A1", "A5") and k != 1:
        raise ValueError(f"axis_verdict: {axis} rows must hold a single session, got {k}: {sess}")
    exp_sessions = lk["size"] if lk["unit"] == "sessions" else plan["sessions"]
    exp_items = lk["size"] if lk["unit"] == "items" else plan["items"]
    warn = []
    if exp_items is not None and n != exp_items:
        warn.append(f"{n} items, plan look {look} expects {exp_items}")
    if exp_sessions is not None and k != exp_sessions:
        warn.append(f"{k} sessions, plan look {look} expects {exp_sessions}")
    out = dict(axis=axis, look=look, alpha=alpha, n_items=n, n_sessions=k, expected_items=exp_items,
               expected_sessions=exp_sessions, size_warnings=warn, report_sha256=plan.get("report_sha256"))
    if axis == "A5":
        bb = sum(1 for row in d if row[0] == -1)
        cc = sum(1 for row in d if row[0] == 1)
        v = verdict_a5(bb, cc, n, alpha=alpha)
        res = dict(verdict=v.verdict, annotation=v.annotation, label=v.label, delta=v.delta, loss_bound=v.bound)
        gates = _a5_task_gates(ids, d, tasks) if tasks is not None else None
        gp = None if gates is None else all(g["pass"] for g in gates.values())
        stop = v.verdict != UNDECIDED or look == len(looks)
        out.update(res, lo=None, hi=None, discordant_items=bb + cc, exact_bound_used=False,
                   per_session={sess[0]: dict(res, b=bb, c=cc)}, interaction=None, interaction_flag=False,
                   a5=v.as_dict(), stop=stop, next_look=None if stop else look + 1, task_gates=gates,
                   task_gates_pass=gp, clean=None if gp is None else (v.verdict == PASS and gp), blocking=False)
        return out
    r = loss_bound(a, b, alpha=alpha, strata=strata)
    v = r["verdict"]
    per = {}
    for s in sess:
        rs = loss_bound({i: {s: a[i][s]} for i in ids}, {i: {s: b[i][s]} for i in ids}, alpha=PER_SESSION_ALPHA,
                        strata=strata)
        per[s] = dict(delta=rs["delta"], lo=rs["lo"], hi=rs["hi"], loss_bound=rs["loss_bound"],
                      verdict=str(rs["verdict"]), label=rs["verdict"].label)
    inter = session_interaction(a, b, iters=interaction_iters, seed=seed) if k >= 2 else None
    hold = None
    if axis == "A8" and languages is not None:
        rows = dict(zip(ids, d))
        hold = a8_hold({ln: Fraction(sum(sum(rows[i]) for i in items), len(items) * k)
                        for ln, items in _groups_of("axis_verdict", "language", languages, ids).items()})
    flag = bool(inter and inter["flag"])
    out.update(verdict=str(v), annotation=v.annotation, label=v.label, delta=r["delta"], lo=r["lo"], hi=r["hi"],
               loss_bound=r["loss_bound"], discordant_items=r["discordant_items"],
               exact_bound_used=r["exact_bound_used"], per_session=per, per_session_alpha=PER_SESSION_ALPHA,
               interaction=inter,
               interaction_flag=flag, blocking=flag or bool(hold and hold["hold"]))
    if axis == "A8":
        out["hold"] = hold
    return out
