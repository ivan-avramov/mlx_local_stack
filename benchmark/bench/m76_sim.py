"""M76 B7: pre-registered CPU simulation of the whole §8 rule, per axis and look (`docs/specs/m76-b7-statistics.md`
v1.4: the A1 / A7 / A8 decision statistic is the exact item bootstrap `m76_rule.exact_interval_values`, never a
finite-resample percentile; v1.3: A8's decider α* is fixed at 0.001 (C336); its v1.2 capped-grid calibration (session SD {0, 0.25}) is reported as
context, beside a full-grid (session SD 0, 0.25, 0.5) false-PASS(10) table at 0.001).

    cd benchmark && python -m bench.m76_sim --out results/m76/b7-simulation/

Writes `report.json` and `REPORT.md` (generated; never hand-edited). Byte-reproducible for a seed on one interpreter
(numpy is imported lazily for the exact enumerations / convolutions).

Data model (per replication, per axis; accepted in v1.1):
- item i: N16 pass probability p_i ~ Beta (A1: only the mean is identified; A7 / A8 calibration cells: the cell's mean
  with the stored rows' dispersion where identified, else Beta(2, 2)-shaped, i.e. a + b = 4; A5 p = 1.0);
- each (item, session) pair is discordant with probability π_i = D · w_i / E[w], w_i = p_i (1 − p_i) (capped at 1;
  homogeneous π_i = D when p is fixed or unidentified), D = max(cell / planning discordance, loss);
- a discordant pair is a TQ4 loss (X 0, N16 1) with probability ω_u = expit(logit ω₀ + u), u ~ N(0, σ²) one per load
  unit (session; Math500 / A5: block), ω₀ calibrated so E[ω_u] = (D + L) / (2 D): mean loss L, discordance D exactly.
A1 / A7 / A8 decide on the exact item bootstrap (enumerated / convolved; strata honoured; an item's session vector
kept together) of Σ (X − N16) / (items · sessions), computed by `m76_rule.exact_interval_values` — the function stage 3 calls through
`m76_rule.loss_bound` / `axis_verdict`; A5 uses `exact_paired_loss`'s rejection region; the session × arm interaction flag
uses the exact permutation null with the Monte Carlo count K ~ Binomial(iters, p_exact) of `session_interaction`.
"""
import argparse
import bisect
import hashlib
import itertools
import json
import math
import os
import platform
import random
import sys
from pathlib import Path

from bench import m76_rule as R
from bench import stats

SEED = 426
REPS = 20000
SIGMAS = (0.25, 0.0, 0.5)          # primary first; sensitivity 0 and 0.5
PRIMARY_SIGMA = 0.25
LOSSES = (0.0, 0.05, 0.10, 0.12)
PLANNING_D = {"A1": 0.06, "A7": 0.10, "A5": 0.05, "A8": 0.182}
A5_PASS0_TARGET = 0.8
KEEP_PASS0 = 0.5
SAFE_LOSS = 0.10
CANDIDATES = (0.025, 0.02, 0.015, 0.0125, 0.01, 0.0075, 0.005, 0.0035, 0.0025, 0.001)
CAL_GRID = {
    "A8": dict(pass_rates=(0.3, 0.5, 0.7, 0.9), discordance=(0.10, 0.20, 0.30), sigmas=(0.0, 0.25)),   # v1.2 C335
    "A7": dict(pass_rates=(0.8, 0.9, 0.96), discordance=(0.05, 0.10, 0.20), sigmas=(0.0, 0.25, 0.5)),
}
SENSITIVITY_SIGMAS = {"A8": (0.5,)}  # v1.2 (C335): simulated and reported only; never set α*
FIXED_ALPHA_STAR = {"A8": 0.001}  # v1.3 (C336): operator-fixed decider α*; the calibration is context only
DEFAULT_KAPPA = 4.0               # Beta(2, 2)-shaped: a + b = 4 at the cell's mean
INTERACTION_ITERS = 10000
MODEL = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed"
_RESULTS = Path(__file__).resolve().parent.parent / "results"
OUT_DIR = _RESULTS / "m76" / "b7-simulation"
_CAL_DRAWS = 200000
_CAP_TOL = 1e-3


def _np():
    import numpy
    return numpy


# ------------------------------------------------------------------------------------------------------------ inputs
def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _rel(path, root):
    return Path(path).resolve().relative_to(root.resolve().parent.parent).as_posix()


def load_a1_n16(results=_RESULTS):
    """P426 S′ Math500 N16 (MTP ON) blocks: [(tune, n, strict_correct, path)]."""
    out = []
    for b in ("b1", "b2"):
        p = results / MODEL / f"math500.p426s2-on-{b}.score.json"
        s = json.loads(p.read_text())
        n = int(s["n"])
        k = round(float(s["acc_strict"]) * n)
        out.append((f"p426s2-on-{b}", n, k, p))
    return out


def load_a7_n16(results=_RESULTS):
    """P426 S′ tg1 N16 (MTP ON) sessions s1 and s2: ({item: {session: strict 0/1}}, [paths]); strict = passed AND
    converged (P426 `_strict`); duplicate item rows within a session are refused."""
    per, paths = {}, []
    for s in ("s1", "s2"):
        d = results / "p426" / "wave2" / f"tg1-p426-on-{s}.a1" / s
        seen = {}
        for p in sorted(d.glob("*.jsonl")):
            paths.append(p)
            for line in p.read_text().splitlines():
                if not line.strip():
                    continue
                r = json.loads(line)
                if r["id"] in seen:
                    raise ValueError(f"load_a7_n16: duplicate row for {r['id']} in session {s} ({p.name})")
                seen[r["id"]] = 1 if (r.get("passed") is True and r.get("converged") is True) else 0
        for i, v in seen.items():
            per.setdefault(i, {})[s] = v
    ragged = sorted(i for i, v in per.items() if len(v) != 2)
    if ragged:
        raise ValueError(f"load_a7_n16: items missing a session: {ragged}")
    return per, paths


def find_tg2_pilot(results=_RESULTS):
    """tg2 pilot rows under `m65_pilot/` (jsonl rows carrying `passed`), or [] when none are stored."""
    d = results / "m65_pilot"
    if not d.is_dir():
        return []
    return [p for p in sorted(d.rglob("*.jsonl")) if '"passed"' in p.read_text()]


def beta_from_sessions(per):
    """Moment fit: mean m over item × session; between-item variance = mean pairwise sample covariance of the
    sessions' outcomes across items. Returns dict(m, cov, var_between, a, b) with a = b = None when the covariance is
    ≤ 0 or m ∈ {0, 1} (dispersion not identified → homogeneous)."""
    ids = sorted(per, key=str)
    ss = sorted({s for v in per.values() for s in v}, key=str)
    n = len(ids)
    cols = [[per[i][s] for i in ids] for s in ss]
    m = sum(sum(c) for c in cols) / (len(ss) * n)
    covs = []
    for x, y in itertools.combinations(cols, 2):
        mx, my = sum(x) / n, sum(y) / n
        covs.append(sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / (n - 1))
    cov = sum(covs) / len(covs) if covs else 0.0
    out = dict(n_items=n, sessions=ss, m=m, cov=cov)
    if cov <= 0 or m in (0.0, 1.0):
        out.update(var_between=0.0, a=None, b=None)
        return out
    var = min(cov, m * (1 - m) * (1 - 1e-6))
    c = m * (1 - m) / var - 1
    out.update(var_between=var, a=m * c, b=(1 - m) * c)
    return out


# ------------------------------------------------------------------------------------------------------- data model
def _expit(x):
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def _logit(p):
    return math.log(p / (1 - p))


_GH = None


def _normal_grid():
    """Fixed quadrature for E over u ~ N(0, 1): midpoints on [−8, 8], 4001 nodes, normalized weights."""
    global _GH
    if _GH is None:
        k = 4001
        xs = [-8 + 16 * (j + 0.5) / k for j in range(k)]
        ws = [math.exp(-x * x / 2) for x in xs]
        s = sum(ws)
        _GH = (xs, [w / s for w in ws])
    return _GH


def calibrate_omega(target, sigma):
    """ω₀ with E[expit(logit ω₀ + σ Z)] = target (bisection on the logit)."""
    if target <= 0.0 or target >= 1.0 or sigma == 0.0:
        return target
    xs, ws = _normal_grid()
    lo, hi = -40.0, 40.0
    for _ in range(200):
        mid = (lo + hi) / 2
        e = sum(w * _expit(mid + sigma * x) for x, w in zip(xs, ws))
        if e < target:
            lo = mid
        else:
            hi = mid
    return _expit((lo + hi) / 2)


_DREAL = {}
_WDRAWS = {}


class Model:
    """The pre-registered data model for one axis at (loss, σ); `d_plan` is the planning or cell discordance."""

    def __init__(self, axis, d_plan, loss, sigma, beta=None):
        self.axis, self.loss, self.sigma, self.beta = axis, loss, sigma, beta
        self.d_eff = max(d_plan, loss)
        if beta is not None and beta.get("a") is not None:
            a, b = beta["a"], beta["b"]
            self.ew = a * b / ((a + b) * (a + b + 1))
            key = (a, b, self.d_eff)
            if key not in _DREAL:
                if (a, b) not in _WDRAWS:
                    cal = random.Random(f"m76-b7:cal:{a!r}:{b!r}")
                    _WDRAWS[(a, b)] = [p * (1 - p) for p in (cal.betavariate(a, b) for _ in range(_CAL_DRAWS))]
                _DREAL[key] = sum(min(1.0, self.d_eff * w / self.ew) for w in _WDRAWS[(a, b)]) / _CAL_DRAWS
            self.d_real = _DREAL[key]
        else:
            self.ew = None
            self.d_real = self.d_eff
        self.omega_target = min(1.0, (self.d_real + loss) / (2 * self.d_real)) if self.d_real > 0 else 0.5
        self.loss_real = self.d_real * (2 * self.omega_target - 1)
        self.omega0 = calibrate_omega(self.omega_target, sigma)

    def item_pi(self, rng):
        if self.ew is None:
            return self.d_eff
        p = rng.betavariate(self.beta["a"], self.beta["b"])
        return min(1.0, self.d_eff * p * (1 - p) / self.ew)

    def unit_omega(self, rng):
        if self.sigma == 0.0 or self.omega0 in (0.0, 1.0):
            return self.omega0
        return _expit(_logit(self.omega0) + rng.normalvariate(0.0, self.sigma))


def cell_beta(m, kappa):
    """Beta with mean m and concentration a + b = kappa."""
    return dict(a=m * kappa, b=(1 - m) * kappa)


def cell_feasibility(m, d, kappa, loss=SAFE_LOSS):
    """Reasons the data model cannot realise the cell (empty when realisable): at no loss the discordant pairs split
    evenly, so D/2 ≤ min(m, 1 − m); at the safety loss L (D_eff = max(D, L)) the N16-pass/X-fail mass (D_eff + L)/2 ≤ m
    and the reverse (D_eff − L)/2 ≤ 1 − m; and the π cap must not bind (realised D within 0.001 of D_eff)."""
    why = []
    if not 0.0 < m < 1.0 or not kappa > 0:
        return [f"pass rate {m:g} / concentration {kappa!r} outside the Beta model (0 < m < 1, kappa > 0)"]
    if d / 2 > min(m, 1 - m) + 1e-12:
        why.append(f"D/2 = {d / 2:g} > min(m, 1 - m) = {min(m, 1 - m):g} at no loss")
    de = max(d, loss)
    if (de + loss) / 2 > m + 1e-12:
        why.append(f"(D_eff + L)/2 = {(de + loss) / 2:g} > m at loss {loss:g}")
    if (de - loss) / 2 > 1 - m + 1e-12:
        why.append(f"(D_eff - L)/2 = {(de - loss) / 2:g} > 1 - m at loss {loss:g}")
    for lo in (0.0, loss):
        mod = Model("cap", d, lo, 0.0, cell_beta(m, kappa))
        if abs(mod.d_real - mod.d_eff) > _CAP_TOL:
            why.append(f"pi cap binds at loss {lo:g}: realised D {mod.d_real:.4f} < {mod.d_eff:g}")
    return why


# ----------------------------------------------------------------------------------------------- ideal bootstrap
# The exact bootstrap lives in `bench.m76_rule` (finding A1 / A7 / A8: the simulated bound is the shipped bound);
# these names are kept as aliases of the rule's implementation.
_conv, _nfold, _hist_key, _ideal_cdf, _quantiles = R._conv, R._nfold, R._hist_key, R._ideal_cdf, R._quantiles


def ideal_quantiles(strata_vals, denom, q):
    """(lo, hi) of the ideal item bootstrap of Σ v / denom, items resampled within strata; `strata_vals` is a list of
    per-stratum lists of integer item values; lo = F⁻¹(q), hi = F⁻¹(1 − q)."""
    lo_x, hi_x = _quantiles(_ideal_cdf(_hist_key(strata_vals)), q)
    return lo_x / denom, hi_x / denom


def analyse(d, items, sessions, alpha, strata_of=None):
    """§8 at one look on simulated differences d[i][s] ∈ {−1, 0, 1}: (verdict, delta, lo, hi), computed by
    `m76_rule.exact_interval_values` (the stage-3 `loss_bound` / `axis_verdict` computation)."""
    k = len(sessions)
    vals = [sum(d[i][s] for s in sessions) for i in items]
    if strata_of is None:
        groups = [vals]
    else:
        g = {}
        for i, v in zip(items, vals):
            g.setdefault(strata_of(i), []).append(v)
        groups = [g[key] for key in sorted(g)]
    any_disc = any(d[i][s] for i in items for s in sessions)
    (r,) = R.exact_interval_values(groups, k, [alpha], any_discordant=bool(any_disc))
    return r["verdict"], r["delta"], r["lo"], r["hi"]


_VCODE = {R.PASS: "P", R.LOSS: "L", R.UNDECIDED: "U"}
_VVEC = {}


def verdict_vector(vals, n, k, any_disc, alphas=CANDIDATES):
    """§8 verdict code ("P" / "L" / "U") at each nominal one-sided α of `alphas` for one look whose per-item values are
    `vals` (Σ_s d over k sessions); one exact bootstrap (`m76_rule.exact_interval_values`) read at every α. Returns a
    string, one code per α."""
    if len(vals) != n:
        raise ValueError(f"verdict_vector: {len(vals)} values for n = {n}")
    hk = _hist_key([vals])
    tot = sum(vals)
    key = (hk, tot, n, k, any_disc, alphas)
    if key not in _VVEC:
        rs = R.exact_interval_values([vals], k, list(alphas), any_discordant=bool(any_disc))
        _VVEC[key] = "".join(_VCODE[r["verdict"]] for r in rs)
    return _VVEC[key]


# ------------------------------------------------------------------------------------------- interaction (exact null)
_KERNELS = {}
_QGRID = {}


def _kernel(ms):
    """Uniform arrangements of an item's multiset of d values: list of (shift of sessions 1..k−1, weight)."""
    if ms not in _KERNELS:
        perms = list(itertools.permutations(ms))
        acc = {}
        for p in perms:
            acc[p[:-1]] = acc.get(p[:-1], 0.0) + 1.0 / len(perms)
        _KERNELS[ms] = sorted(acc.items())
    return _KERNELS[ms]


_NULL = {}


def interaction_exact_p(rows):
    """Exact permutation p-value P(Σ_s S_s² ≥ obs) of `session_interaction`'s statistic under within-item uniform
    session permutation; `rows` = per-item tuples of d_s (k ≥ 2)."""
    np = _np()
    k = len(rows[0])
    active = [r for r in rows if len(set(r)) > 1]
    if not active:
        return 1.0
    obs_v = [sum(r[s] for r in active) for s in range(k)]
    obs = sum(x * x for x in obs_v)
    key = tuple(sorted(tuple(sorted(r)) for r in active))
    if key not in _NULL:
        a = len(active)
        size = 2 * a + 1
        dist = np.zeros((size,) * (k - 1))
        dist[(a,) * (k - 1)] = 1.0
        for ms in key:
            new = np.zeros_like(dist)
            for shift, w in _kernel(ms):
                new += w * np.roll(dist, shift, axis=tuple(range(k - 1)))
            dist = new
        total = sum(sum(ms) for ms in key)
        qk = (a, k, total)
        if qk not in _QGRID:
            idx = np.indices((size,) * (k - 1)) - a
            last = total - idx.sum(axis=0)
            _QGRID[qk] = (idx ** 2).sum(axis=0) + last ** 2
        q = _QGRID[qk]
        flat_q, flat_p = q.ravel(), dist.ravel()
        order = np.argsort(flat_q, kind="stable")
        asc, ps = flat_q[order], flat_p[order]
        tail = np.cumsum(ps[::-1])[::-1]               # tail[i] = P(Q ≥ asc[i])
        _NULL[key] = (asc.tolist(), tail.tolist())
    asc, tail = _NULL[key]
    i = bisect.bisect_left(asc, obs)
    return 1.0 if i == 0 else min(1.0, tail[i])


def _mc_kmax(iters, alpha=R.INTERACTION_ALPHA):
    """Largest K with (1 + K)/(1 + iters) < alpha (the MC count at which `session_interaction` flags)."""
    k = math.ceil(alpha * (1 + iters) - 1) - 1
    while (2 + k) / (1 + iters) < alpha:
        k += 1
    while k >= 0 and (1 + k) / (1 + iters) >= alpha:
        k -= 1
    return k


_FIRE = {}


def fire_probability(p, iters=INTERACTION_ITERS):
    """P(session_interaction flags | exact p) = P(Binomial(iters, p) ≤ kmax)."""
    key = (p, iters)
    if key not in _FIRE:
        kmax = _mc_kmax(iters)
        if kmax < 0:
            v = 0.0
        elif p <= 0.0:
            v = 1.0
        elif p >= 1.0:
            v = 0.0
        else:
            lr = math.log(p) - math.log1p(-p)
            t = iters * math.log1p(-p)                 # log P(K = 0)
            terms = [t]
            for j in range(kmax):
                t += math.log((iters - j) / (j + 1)) + lr
                terms.append(t)
            mx = max(terms)
            v = min(1.0, math.exp(mx) * sum(math.exp(t - mx) for t in terms))
        _FIRE[key] = v
    return _FIRE[key]


# ------------------------------------------------------------------------------------------------------------ designs
def _design(axis, n=None):
    if axis == "A1":
        return dict(items=300, sessions=1, unit=lambda i, s: i // 50, strata=None,
                    looks=[(100, 1), (300, 1)], single=(300, 1), plan=R.axis_plan("A1"))
    if axis == "A7":
        return dict(items=43, sessions=3, look1_sessions=2)
    if axis == "A8":
        return dict(items=80, sessions=2, look1_sessions=None)
    raise ValueError(axis)


def _gen(model, n_items, n_sess, unit, rng):
    omegas = {}
    d = []
    for i in range(n_items):
        pi = model.item_pi(rng)
        row = []
        for s in range(n_sess):
            u = unit(i, s)
            if u not in omegas:
                omegas[u] = model.unit_omega(rng)
            if rng.random() < pi:
                row.append(-1 if rng.random() < omegas[u] else 1)
            else:
                row.append(0)
        d.append(row)
    return d


def simulate_cell(axis, loss, sigma, reps, *, seed=SEED, beta=None):
    """A1 (v1 rule): `reps` replications at true loss `loss` and block SD `sigma`. Returns counts."""
    des = _design(axis)
    model = Model(axis, PLANNING_D[axis], loss, sigma, beta)
    rng = random.Random(f"m76-b7:{seed}:{axis}:None:{sigma!r}:{loss!r}")
    alphas = [lk["alpha"] for lk in des["plan"]["looks"]]
    c = {key: 0 for key in ("l1_PASS", "l1_LOSS", "l1_UNDECIDED", "two_PASS", "two_LOSS", "two_UNDECIDED",
                            "one_PASS", "one_LOSS", "one_UNDECIDED")}
    disc_sum = loss_sum = 0.0
    n_items, n_sess = des["items"], des["sessions"]
    for _ in range(reps):
        d = _gen(model, n_items, n_sess, des["unit"], rng)
        cells = n_items * n_sess
        disc_sum += sum(1 for row in d for x in row if x) / cells
        loss_sum += -sum(x for row in d for x in row) / cells
        ni1, ns1 = des["looks"][0]
        v1 = analyse(d, range(ni1), range(ns1), alphas[0], des["strata"])[0]
        c["l1_" + v1] += 1
        if v1 == R.UNDECIDED:
            ni2, ns2 = des["looks"][1]
            c["two_" + analyse(d, range(ni2), range(ns2), alphas[1], des["strata"])[0]] += 1
        else:
            c["two_" + v1] += 1
        ni, ns = des["single"]
        c["one_" + analyse(d, range(ni), range(ns), R.ALPHA_TOTAL, des["strata"])[0]] += 1
    return dict(counts=c, reps=reps, d_eff=model.d_eff, d_model=model.d_real, loss_model=model.loss_real,
                omega0=model.omega0, realized_discordance=disc_sum / reps, realized_loss=loss_sum / reps)


# ---------------------------------------------------------------------------------------------------------- A5
_A5_TABLE = {}


def a5_table(n):
    """(b, c) → verdict code under `verdict_a5`'s rule (region membership; LOSS by the exact binomial)."""
    if n not in _A5_TABLE:
        region = R.a5_pass_region(n)
        t = {}
        for b in range(n + 1):
            for c in range(n - b + 1):
                if (b, c) in region:
                    t[(b, c)] = "P"
                elif (c - b) / n < R.POINT_FLOOR and b > c and stats.mcnemar_exact(b, c) <= R.LOSS_TEST_ALPHA:
                    t[(b, c)] = "L"
                else:
                    t[(b, c)] = "U"
        _A5_TABLE[n] = t
    return _A5_TABLE[n]


def simulate_a5(n, loss, sigma, reps, *, seed=SEED):
    """A5 (v1.1 exact rule) at n items, true loss, block SD. Returns counts of P / L / U and realised D / loss."""
    model = Model("A5", PLANNING_D["A5"], loss, sigma, None)
    rng = random.Random(f"m76-b7:{seed}:A5:{n}:{sigma!r}:{loss!r}")
    table = a5_table(n)
    cnt = {"P": 0, "L": 0, "U": 0}
    disc = net = 0
    for _ in range(reps):
        d = _gen(model, n, 1, lambda i, s: i % 2, rng)
        b = sum(1 for row in d if row[0] == -1)
        c = sum(1 for row in d if row[0] == 1)
        cnt[table[(b, c)]] += 1
        disc += b + c
        net += b - c
    return dict(counts=cnt, reps=reps, d_eff=model.d_eff, omega0=model.omega0,
                realized_discordance=disc / (reps * n), realized_loss=net / (reps * n))


# -------------------------------------------------------------------------------------------- A7 / A8 calibration
def _cell_key(m, d, sigma):
    return f"m={float(m)!r}|D={float(d)!r}|sigma={float(sigma)!r}"


def simulate_multi(axis, m, d, sigma, loss, reps, *, seed=SEED, kappa=DEFAULT_KAPPA, flags=False):
    """A7 / A8 at nuisance (m, D, σ), true loss: per replication one ideal bootstrap per look, read at every candidate
    α. Returns {hist: {verdict-vector key: count}, reps, model, flags}. A7 keys are "<look 1>|<full>", A8 "<full>"."""
    des = _design(axis)
    model = Model(axis, d, loss, sigma, cell_beta(m, kappa))
    rng = random.Random(f"m76-b7:{seed}:{axis}:{_cell_key(m, d, sigma)}:kappa={float(kappa)!r}:loss={loss!r}")
    frng = random.Random(f"m76-b7:flag:{seed}:{axis}:{_cell_key(m, d, sigma)}:kappa={float(kappa)!r}:loss={loss!r}")
    n, k, k1 = des["items"], des["sessions"], des["look1_sessions"]
    hist, fhist = {}, {}
    disc = net = 0
    for _ in range(reps):
        d_rows = _gen(model, n, k, lambda i, s: s, rng)
        any_full = any(x for row in d_rows for x in row)
        vfull = verdict_vector([sum(row) for row in d_rows], n, k, any_full)
        if k1 is not None:
            any1 = any(x for row in d_rows for x in row[:k1])
            key = verdict_vector([sum(row[:k1]) for row in d_rows], n, k1, any1) + "|" + vfull
        else:
            key = vfull
        hist[key] = hist.get(key, 0) + 1
        disc += sum(1 for row in d_rows for x in row if x)
        net += -sum(x for row in d_rows for x in row)
        if flags:
            p = interaction_exact_p([tuple(r) for r in d_rows])
            if frng.random() < fire_probability(p):
                fhist[key] = fhist.get(key, 0) + 1
    out = dict(hist=dict(sorted(hist.items())), reps=reps,
               model=dict(d_eff=model.d_eff, d_model=model.d_real, loss_model=model.loss_real, omega0=model.omega0,
                          realized_discordance=disc / (reps * n * k), realized_loss=net / (reps * n * k)))
    if flags:
        out["flag_hist"] = dict(sorted(fhist.items()))
    return out


def _rate(k, n):
    lo, hi = stats.wilson(k, n)
    return dict(k=k, n=n, rate=k / n, lo=lo, hi=hi)


def _single_counts(hist, j, code="P"):
    return sum(c for key, c in hist.items() if key.split("|")[-1][j] == code)


def _look1_counts(hist, j, code="P"):
    return sum(c for key, c in hist.items() if key.split("|")[0][j] == code)


def _two_look_counts(hist, j1, j2):
    """{P, L, U} counts of the two-look rule: look 1 at α_j1 decides unless UNDECIDED, then the full look at α_j2."""
    out = {"P": 0, "L": 0, "U": 0}
    for key, c in hist.items():
        v1, v2 = key.split("|")
        out[v1[j1] if v1[j1] != "U" else v2[j2]] += c
    return out


def calibrate(axis, *, reps=REPS, seed=SEED, grid=None, kappa=None, committed=None):
    """Least-favourable α* for `axis` ("A7" / "A8"): the largest candidate α (one-sided nominal, `CANDIDATES`) such
    that at every realisable nuisance cell of the pre-registered grid (or `grid`: dict of pass_rates / discordance /
    sigmas) the Wilson 95 % upper MC bound of false-PASS at loss 10 pp ≤ 0.025. One bootstrap per replication, every
    candidate read from it. `kappa`: Beta concentration of the cells (default: the stored rows' where identified,
    else 4 = Beta(2, 2)-shaped). `committed`: {cell key: cell result} reused verbatim (same seeds → same result).
    A7 also calibrates look 1 (2 sessions) to the O'Brien–Fleming spend α(2/3) and the two-look rule to 0.025."""
    if axis not in CAL_GRID:
        raise ValueError(f"calibrate: axis must be one of {sorted(CAL_GRID)}, got {axis!r}")
    g = dict(CAL_GRID[axis]) if grid is None else dict(grid)
    kap, ksrc = _axis_kappa(axis) if kappa is None else (float(kappa), "given")
    cells = {}
    for m in g["pass_rates"]:
        for dd in g["discordance"]:
            for s in g["sigmas"]:
                ck = _cell_key(m, dd, s)
                if committed is not None and ck in committed:
                    cells[ck] = committed[ck]
                    continue
                why = cell_feasibility(m, dd, kap)
                res = simulate_multi(axis, m, dd, s, SAFE_LOSS, reps, seed=seed, kappa=kap)
                cells[ck] = dict(m=m, D=dd, sigma=s, kappa=kap, feasible=not why, infeasible_reasons=why,
                                 hist=res["hist"], reps=reps, model=res["model"])
    out = dict(axis=axis, candidates=list(CANDIDATES), grid={k: list(v) for k, v in g.items()}, kappa=kap,
               kappa_source=ksrc, safe_loss=SAFE_LOSS, target=R.ALPHA_TOTAL, reps=reps, seed=seed, cells=cells)
    out.update(_choose(cells, lambda h, j: _single_counts(h, j), R.ALPHA_TOTAL))
    out["alpha_star_incl_infeasible"] = _choose(cells, lambda h, j: _single_counts(h, j), R.ALPHA_TOTAL,
                                                feasible_only=False)["alpha_star"]
    out["skipped_cells"] = sorted(ck for ck, c in cells.items() if not c["feasible"])
    sens_sigmas = tuple(g.get("sensitivity_sigmas", SENSITIVITY_SIGMAS.get(axis, ()) if grid is None else ()))
    if sens_sigmas:
        out["grid"]["sensitivity_sigmas"] = list(sens_sigmas)
        out["sensitivity"] = _sensitivity(axis, g, sens_sigmas, kap, reps, seed, out["alpha_star"])
    else:
        smax = max(g["sigmas"])
        sub = {ck: c for ck, c in cells.items() if c["sigma"] < smax}
        out["sensitivity_without_max_sigma"] = dict(
            sigma_excluded=smax,
            alpha_star=_choose(sub, lambda h, j: _single_counts(h, j), R.ALPHA_TOTAL)["alpha_star"] if sub else None)
    if axis == "A7":
        t1 = stats.obf_alpha(2 / 3, R.ALPHA_TOTAL)
        l1 = _choose(cells, lambda h, j: _look1_counts(h, j), t1)
        look1 = dict(target=t1, alpha_star=l1["alpha_star"], binding_cell=l1["binding_cell"])
        if l1["alpha_star"] is not None:
            j1 = CANDIDATES.index(l1["alpha_star"])
            l2 = _choose(cells, lambda h, j: _two_look_counts(h, j1, j)["P"], R.ALPHA_TOTAL)
            look1.update(alpha_star_look2=l2["alpha_star"], binding_cell_look2=l2["binding_cell"])
        else:
            look1.update(alpha_star_look2=None, binding_cell_look2=None)
        out["look1"] = look1
    return out


def _sensitivity(axis, g, sens_sigmas, kap, reps, seed, alpha_star):
    """v1.2 (C335): the sensitivity session SDs' cells, simulated and reported; they never set α*. Per cell: the
    false-PASS(10) upper bound at the chosen α*, the candidates safe there (upper ≤ 0.025) and the smallest / largest
    of them (None = "none")."""
    j_star = CANDIDATES.index(alpha_star) if alpha_star is not None else None
    cells = {}
    for m in g["pass_rates"]:
        for dd in g["discordance"]:
            for s in sens_sigmas:
                why = cell_feasibility(m, dd, kap)
                res = simulate_multi(axis, m, dd, s, SAFE_LOSS, reps, seed=seed, kappa=kap)
                his = [_rate(_single_counts(res["hist"], j), reps)["hi"] for j in range(len(CANDIDATES))]
                safe = [a for a, hi in zip(CANDIDATES, his) if hi <= R.ALPHA_TOTAL]
                cells[_cell_key(m, dd, s)] = dict(
                    m=m, D=dd, sigma=s, kappa=kap, feasible=not why, infeasible_reasons=why, hist=res["hist"],
                    reps=reps, model=res["model"], hi_at_alpha_star=his[j_star] if j_star is not None else None,
                    safe_candidates=safe, smallest_safe=min(safe) if safe else None,
                    largest_safe=max(safe) if safe else None)
    feas = {ck: c for ck, c in cells.items() if c["feasible"]}
    worst = None
    if j_star is not None and feas:
        worst = max(feas, key=lambda ck: (feas[ck]["hi_at_alpha_star"], ck))
    return dict(sigmas=list(sens_sigmas), sets_alpha_star=False, alpha_star=alpha_star, cells=cells,
                worst_cell_at_alpha_star=worst,
                worst_hi_at_alpha_star=feas[worst]["hi_at_alpha_star"] if worst is not None else None,
                unsafe_at_alpha_star=sorted(ck for ck, c in feas.items()
                                            if j_star is not None and c["hi_at_alpha_star"] > R.ALPHA_TOTAL))


def _choose(cells, count, target, feasible_only=True):
    """Largest candidate whose false-PASS upper bound ≤ target at every (feasible) cell; binding cell = where the next
    larger candidate is worst (or, at the largest candidate, the worst cell at α*)."""
    use = {ck: c for ck, c in cells.items() if c["feasible"] or not feasible_only}
    his = {}
    for j in range(len(CANDIDATES)):
        his[j] = {ck: _rate(count(c["hist"], j), c["reps"])["hi"] for ck, c in use.items()}
    star = None
    for j in range(len(CANDIDATES)):
        if all(h <= target for h in his[j].values()):
            star = j
            break
    if not use:
        return dict(alpha_star=None, binding_cell=None, worst_hi_at_star=None, next_larger_worst_hi=None)
    if star is None:
        jb = len(CANDIDATES) - 1
        worst = max(his[jb], key=lambda ck: (his[jb][ck], ck))
        return dict(alpha_star=None, binding_cell=worst, worst_hi_at_star=None, next_larger_worst_hi=his[jb][worst])
    ref = star - 1 if star > 0 else star
    bind = max(his[ref], key=lambda ck: (his[ref][ck], ck))
    worst_star = max(his[star].values())
    return dict(alpha_star=CANDIDATES[star], binding_cell=bind, worst_hi_at_star=worst_star,
                next_larger_worst_hi=his[ref][bind] if star > 0 else None)


def _axis_kappa(axis, results=_RESULTS):
    if axis == "A7":
        b = beta_from_sessions(load_a7_n16(results)[0])
        if b["a"] is not None:
            return b["a"] + b["b"], "P426 S′ A7 N16 rows (moment fit)"
        return DEFAULT_KAPPA, "not identified in P426 S′ A7 N16 rows (covariance ≤ 0) → Beta(2, 2)-shaped"
    return DEFAULT_KAPPA, "no tg2 rows stored → Beta(2, 2)-shaped"


def planning_values(axis, results=_RESULTS):
    if axis == "A7":
        return beta_from_sessions(load_a7_n16(results)[0])["m"], PLANNING_D["A7"]
    return 0.5, PLANNING_D["A8"]


# ------------------------------------------------------------------------------------------------------------ recheck
def _estimate_nuisance(n16_rows, x_rows):
    ids, sess, d = R._session_rows("recheck", x_rows, n16_rows)
    n, k = len(ids), len(sess)
    b = beta_from_sessions(n16_rows) if k >= 2 else dict(m=sum(n16_rows[i][sess[0]] for i in ids) / n, cov=None,
                                                         var_between=0.0, a=None, b=None)
    disc = sum(1 for row in d for x in row if x) / (n * k)
    kappa = (b["a"] + b["b"]) if b["a"] is not None else None
    return dict(n_items=n, n_sessions=k, n16_mean=b["m"], n16_cov=b["cov"], var_between=b["var_between"],
                kappa=kappa, discordance=disc)


def recheck(axis, n16_rows, x_rows, *, out=None, report=None, reps=REPS, seed=SEED):
    """Pre-registered nuisance re-check on real rows (`item_id → {session_id: 0/1}`, the tg2 SCREEN's): estimates the
    N16 mean pass rate m̂, its Beta concentration κ̂ (moment fit; None when not identified) and the discordance rate
    D̂ (discordant item-sessions / all, sign ignored) — never the arm effect.

    Inside ⇔ (m̂, D̂) lies in the committed grid's (pass rate × discordance) hull AND κ̂ is not below the committed
    concentration (the single κ every committed cell used, i.e. its least-favourable value; κ̂ None counts as not
    below) AND the data model realises (m̂, D̂, κ̂) (`cell_feasibility`, κ̂ or the committed κ when not identified).
    Inside: the committed α* stands. Outside because the data model cannot realise the observed nuisance (e.g. m̂ 0
    or 1): no recalibration is attempted (`recalibration_attempted` False); the committed / fixed α* is applied and
    `observed_unrealisable` / `operator_review` are set (v1.4). Otherwise outside: `calibrate` re-runs on the grid extended by (m̂, D̂); when κ̂ is
    identified and differs from the committed κ every cell is recalibrated at κ̂ (no committed cell of another
    concentration is reused), else committed cells are reused; α* = min(committed, new).
    v1.3 (C336), an axis with a fixed α* (A8): the committed α* is the fixed one and α* = min(fixed, new); when no
    candidate is safe on the extended grid the fixed α* is applied.
    Flags (→ the operator): `unsafe_on_extended_grid` — true iff the re-calibration found no candidate α whose
    false-PASS(10) upper MC bound is ≤ 0.025 at every realisable cell of the extended grid (so the applied α* is
    unsafe at ≥ 1 such cell; not specific to the observed cell; false when inside); `observed_unrealisable` — the data
    model cannot realise the observed nuisance, so its own cell is skipped and cannot inform α*. `operator_review` =
    either flag. Writes `recheck-<axis>.json` under `out` (default the B7 report directory); returns the record."""
    rep, sha = R.load_report(report)
    if rep is None:
        raise ValueError(f"recheck: no committed report at {report if report is not None else R.REPORT_JSON}")
    cal = rep["axes"][axis]["calibration"]
    fixed = rep["axes"][axis].get("alpha_star_fixed", FIXED_ALPHA_STAR.get(axis))
    committed_star = fixed if fixed is not None else cal["alpha_star"]
    est = _estimate_nuisance(n16_rows, x_rows)
    g = cal["grid"]
    m_hat, d_hat = round(est["n16_mean"], 6), round(est["discordance"], 6)
    kap_c = cal["kappa"]
    kap_hat = round(est["kappa"], 6) if est["kappa"] is not None else None
    kap_obs = kap_hat if kap_hat is not None else kap_c
    why = []
    if not min(g["pass_rates"]) <= m_hat <= max(g["pass_rates"]):
        why.append(f"pass rate {m_hat:g} outside [{min(g['pass_rates']):g}, {max(g['pass_rates']):g}]")
    if not min(g["discordance"]) <= d_hat <= max(g["discordance"]):
        why.append(f"discordance {d_hat:g} outside [{min(g['discordance']):g}, {max(g['discordance']):g}]")
    if kap_hat is not None and kap_hat < kap_c:
        why.append(f"concentration {kap_hat:g} below the committed {kap_c:g}")
    unreal = cell_feasibility(m_hat, d_hat, kap_obs)
    if unreal:
        why.append("observed nuisance not realisable by the data model: " + "; ".join(unreal))
    inside = not why
    rec = dict(axis=axis, estimates=est, grid_hull=dict(pass_rates=[min(g["pass_rates"]), max(g["pass_rates"])],
                                                        discordance=[min(g["discordance"]), max(g["discordance"])]),
               committed_kappa=kap_c, observed_kappa=kap_hat, inside=inside, outside_reasons=why,
               observed_unrealisable=bool(unreal), observed_infeasible_reasons=unreal,
               committed_alpha_star=committed_star, report_sha256=sha, seed=seed, unsafe_on_extended_grid=False)
    if fixed is not None:
        rec.update(alpha_star_fixed=fixed, calibrated_alpha_star=cal["alpha_star"])
    if inside:
        rec.update(new_alpha_star=None, alpha_star_applied=committed_star, extended_grid=None)
    elif unreal:
        # v1.4: the data model cannot realise the observed nuisance → no recalibration; committed / fixed α* applied
        rec.update(new_alpha_star=None, alpha_star_applied=committed_star, extended_grid=None,
                   recalibration_attempted=False, recalibrated_all_cells=False)
    else:
        ext = dict(pass_rates=sorted(set(g["pass_rates"]) | {m_hat}),
                   discordance=sorted(set(g["discordance"]) | {d_hat}), sigmas=list(g["sigmas"]))
        recal_all = kap_hat is not None and kap_hat != kap_c
        committed = None if recal_all else {ck: c for ck, c in cal["cells"].items()}
        new = calibrate(axis, reps=reps, seed=seed, grid=ext, kappa=kap_obs, committed=committed)
        rec["unsafe_on_extended_grid"] = new["alpha_star"] is None
        if fixed is not None:
            # v1.3 (C336): min(fixed, re-calibrated); no safe candidate on the extended grid → fixed, flagged
            applied = min(fixed, new["alpha_star"]) if new["alpha_star"] is not None else fixed
        else:
            cands = [a for a in (cal["alpha_star"], new["alpha_star"]) if a is not None]
            applied = min(cands) if len(cands) == 2 else None
        rec.update(new_alpha_star=new["alpha_star"], alpha_star_applied=applied, extended_grid=ext,
                   recalibration_attempted=True, new_cells_kappa=kap_obs, recalibrated_all_cells=recal_all,
                   new_binding_cell=new["binding_cell"], reps=reps, skipped_cells=new["skipped_cells"])
    rec["operator_review"] = rec["unsafe_on_extended_grid"] or rec["observed_unrealisable"]
    rec = _round(rec)
    path = Path(out) if out is not None else OUT_DIR
    path.mkdir(parents=True, exist_ok=True)
    (path / f"recheck-{axis}.json").write_text(json.dumps(rec, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    return rec


# ------------------------------------------------------------------------------------------------------------ report
def _round(o):
    if isinstance(o, float):
        return round(o, 6)
    if isinstance(o, dict):
        return {str(k): _round(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_round(v) for v in o]
    return o


def _summary3(cnt, n):
    return {name: _rate(cnt[code], n) for name, code in (("PASS", "P"), ("LOSS", "L"), ("UNDECIDED", "U"))}


def _a1_summary(res):
    c, n = res["counts"], res["reps"]
    return dict(model=dict(d_eff=res["d_eff"], d_model=res["d_model"], loss_model=res["loss_model"],
                           omega0=res["omega0"], realized_discordance=res["realized_discordance"],
                           realized_loss=res["realized_loss"]),
                single=dict(PASS=_rate(c["one_PASS"], n), LOSS=_rate(c["one_LOSS"], n),
                            UNDECIDED=_rate(c["one_UNDECIDED"], n)),
                look1=dict(PASS=_rate(c["l1_PASS"], n), LOSS=_rate(c["l1_LOSS"], n),
                           UNDECIDED=_rate(c["l1_UNDECIDED"], n)),
                two_look=dict(PASS=_rate(c["two_PASS"], n), LOSS=_rate(c["two_LOSS"], n),
                              UNDECIDED=_rate(c["two_UNDECIDED"], n)),
                expected_size_two_look=100 + 200 * c["l1_UNDECIDED"] / n)


def _axis_a1(reps, seed):
    cells = {}
    for sigma in SIGMAS:
        for loss in LOSSES:
            cells[f"sigma={sigma}|loss={loss}"] = _a1_summary(simulate_cell("A1", loss, sigma, reps, seed=seed))
    prim = {loss: cells[f"sigma={PRIMARY_SIGMA}|loss={loss}"] for loss in LOSSES}
    pass0_l1 = prim[0.0]["look1"]["PASS"]["rate"]
    fp10_two_hi = prim[0.10]["two_look"]["PASS"]["hi"]
    keep = pass0_l1 >= KEEP_PASS0 and fp10_two_hi <= R.ALPHA_TOTAL
    final = "two_look" if keep else "single"
    return dict(rule="v1.4 exact item bootstrap (m76_rule.exact_interval_values) at the O'Brien–Fleming nominal alphas",
                plan_two_look=R.axis_plan("A1"), plan_single=R.axis_plan("A1", keep_look1=False), cells=cells,
                keep_look1=keep, keep_rule=dict(pass0_look1=pass0_l1, false_pass10_two_look_hi=fp10_two_hi),
                final=final, final_false_pass10_hi=prim[0.10][final]["PASS"]["hi"],
                final_false_pass10=prim[0.10][final]["PASS"]["rate"],
                final_false_pass12=prim[0.12][final]["PASS"]["rate"],
                final_pass0=prim[0.0][final]["PASS"]["rate"])


def _axis_a5(reps, seed, a5_ns):
    lo, hi = R.A5_N_RANGE
    ns = list(a5_ns) if a5_ns is not None else list(range(lo, hi + 1, R.A5_N_STEP))
    scan, chosen = {}, None
    for n in ns:
        p0 = simulate_a5(n, 0.0, PRIMARY_SIGMA, reps, seed=seed)
        f10 = simulate_a5(n, SAFE_LOSS, PRIMARY_SIGMA, reps, seed=seed)
        scan[str(n)] = dict(pass0=_rate(p0["counts"]["P"], reps), false_pass10=_rate(f10["counts"]["P"], reps),
                            exact_size=R.a5_exact_size(n), region_size=len(R.a5_rejection_region(n)))
        if chosen is None and scan[str(n)]["pass0"]["rate"] >= A5_PASS0_TARGET:
            chosen = n
    met = chosen is not None
    if chosen is None:
        chosen = ns[-1]
    cells = {}
    for sigma in SIGMAS:
        for loss in LOSSES:
            r = simulate_a5(chosen, loss, sigma, reps, seed=seed)
            cells[f"sigma={sigma}|loss={loss}"] = dict(
                single=_summary3(r["counts"], reps),
                model=dict(d_eff=r["d_eff"], omega0=r["omega0"], realized_discordance=r["realized_discordance"],
                           realized_loss=r["realized_loss"]))
    prim = {loss: cells[f"sigma={PRIMARY_SIGMA}|loss={loss}"] for loss in LOSSES}
    worst_sigma_fp10_hi = max(cells[f"sigma={s}|loss=0.1"]["single"]["PASS"]["hi"] for s in SIGMAS)
    return dict(rule="v1.1 exact unconditional test (Tango score order, sup over nuisance) + exact binomial LOSS",
                plan=R.axis_plan("A5", n=chosen, calibrated=False), n=chosen, n_target_met=met, n_scan=scan,
                cells=cells, final="single", exact_size=R.a5_exact_size(chosen),
                final_pass0=prim[0.0]["single"]["PASS"]["rate"],
                final_false_pass10=prim[0.10]["single"]["PASS"]["rate"],
                final_false_pass10_hi=prim[0.10]["single"]["PASS"]["hi"],
                final_false_pass12=prim[0.12]["single"]["PASS"]["rate"],
                realised_false_pass10_hi_worst_sigma=worst_sigma_fp10_hi)


def _planning_summary(axis, res, j_star, look1):
    n = res["reps"]
    h = res["hist"]
    single = {code: _single_counts(h, j_star, code) for code in "PLU"}
    out = dict(model=res["model"], single=_summary3(single, n))
    if axis == "A7" and look1 is not None and look1.get("alpha_star") is not None:
        j1 = CANDIDATES.index(look1["alpha_star"])
        out["look1"] = _summary3({code: _look1_counts(h, j1, code) for code in "PLU"}, n)
        if look1.get("alpha_star_look2") is not None:
            j2 = CANDIDATES.index(look1["alpha_star_look2"])
            two = _two_look_counts(h, j1, j2)
            out["two_look"] = _summary3(two, n)
            und1 = _look1_counts(h, j1, "U")
            out["expected_sessions_two_look"] = 2 + und1 / n
    if "flag_hist" in res:
        fh = res["flag_hist"]
        out["flag"] = dict(any=_rate(sum(fh.values()), n), pass_with_flag=_rate(_single_counts(fh, j_star), n))
    return out


def _axis_multi(axis, reps, seed):
    cal = calibrate(axis, reps=reps, seed=seed)
    m_plan, d_plan = planning_values(axis)
    kap = cal["kappa"]
    fixed = FIXED_ALPHA_STAR.get(axis)
    star = fixed if fixed is not None else cal["alpha_star"]
    look1 = cal.get("look1")
    plan_why = cell_feasibility(m_plan, d_plan, kap)
    j_star = CANDIDATES.index(star) if star is not None else len(CANDIDATES) - 1
    cells = {}
    pass0_by_alpha = None
    for sigma in SIGMAS:
        for loss in LOSSES:
            res = simulate_multi(axis, m_plan, d_plan, sigma, loss, reps, seed=seed, kappa=kap,
                                 flags=loss in (0.0, SAFE_LOSS))
            cells[f"sigma={sigma}|loss={loss}"] = _planning_summary(axis, res, j_star, look1)
            if sigma == PRIMARY_SIGMA and loss == 0.0:
                pass0_by_alpha = {str(a): _single_counts(res["hist"], j) / reps for j, a in enumerate(CANDIDATES)}
    prim = {loss: cells[f"sigma={PRIMARY_SIGMA}|loss={loss}"] for loss in LOSSES}
    keep = False
    if axis == "A7" and look1 is not None and look1["alpha_star"] is not None and look1["alpha_star_look2"] is not None:
        keep = prim[0.0]["look1"]["PASS"]["rate"] >= KEEP_PASS0
    if look1 is not None:
        look1["pass0_look1_planning"] = (prim[0.0]["look1"]["PASS"]["rate"] if "look1" in prim[0.0] else None)
        look1["keep"] = keep
    final = "two_look" if keep else "single"
    worst = None
    if star is not None:
        if final == "single":
            worst = max(_rate(_single_counts(c["hist"], j_star), c["reps"])["hi"]
                        for c in cal["cells"].values() if c["feasible"])
        else:
            j1, j2 = CANDIDATES.index(look1["alpha_star"]), CANDIDATES.index(look1["alpha_star_look2"])
            worst = max(_rate(_two_look_counts(c["hist"], j1, j2)["P"], c["reps"])["hi"]
                        for c in cal["cells"].values() if c["feasible"])
    interaction = {}
    for sigma in SIGMAS:
        for loss in (0.0, SAFE_LOSS):
            interaction[f"sigma={sigma}|loss={loss}"] = cells[f"sigma={sigma}|loss={loss}"]["flag"]
    extra = {}
    if fixed is not None:
        fg = _full_grid_at(cal, fixed)
        extra = dict(alpha_star_fixed=fixed, alpha_star_source="fixed by operator ruling C336 (spec v1.3)",
                     full_grid_at_fixed=fg,
                     residual_cells={ck: dict(fg["cells"][ck]) for ck in fg["over_target_realisable"]},
                     residual_note="realisable full-grid cells whose false-PASS(10) upper MC bound exceeds 0.025 at "
                                   "the fixed alpha*: operator-accepted residual (C336)")
    nearest = None
    if plan_why and star is not None:
        nearest = _nearest_realisable(axis, cal, m_plan, d_plan, kap, reps, seed, j_star, look1, final)
    rule = ("v1.4 exact item bootstrap (m76_rule.exact_interval_values) at the operator-fixed nominal one-sided "
            "alpha* (C336)" if fixed is not None else
            "v1.4 exact item bootstrap (m76_rule.exact_interval_values) at the calibrated nominal one-sided alpha*")
    return dict(rule=rule, **extra,
                calibration=cal, planning=dict(m=m_plan, D=d_plan, kappa=kap, feasible=not plan_why,
                                               infeasible_reasons=plan_why, pass0_extrapolated=bool(plan_why),
                                               nearest_realisable=nearest),
                plan_uncalibrated=R.axis_plan(axis, calibrated=False), cells=cells, final=final,
                planning_alpha=CANDIDATES[j_star], planning_pass0_by_alpha=pass0_by_alpha,
                final_alpha=([look1["alpha_star"], look1["alpha_star_look2"]] if keep else [star]),
                final_pass0=prim[0.0][final]["PASS"]["rate"] if star is not None else None,
                final_false_pass10_planning=prim[0.10][final]["PASS"]["rate"] if star is not None else None,
                final_false_pass12_planning=prim[0.12][final]["PASS"]["rate"] if star is not None else None,
                final_false_pass10_hi=worst, interaction=interaction)


def _nearest_realisable(axis, cal, m_plan, d_plan, kap, reps, seed, j_star, look1, final):
    """For an unrealisable planning cell: the realisable (pass rate, discordance) point of the axis's calibration grid
    nearest to it (Euclidean in (m, D); ties by cell key), at the primary σ, and the final rule's PASS(0) there
    (simulated at loss 0, same seed scheme)."""
    pts = sorted({(c["m"], c["D"]) for c in cal["cells"].values() if c["feasible"]})
    if not pts:
        return None
    m, dd = min(pts, key=lambda p: (math.hypot(p[0] - m_plan, p[1] - d_plan), _cell_key(p[0], p[1], PRIMARY_SIGMA)))
    res = simulate_multi(axis, m, dd, PRIMARY_SIGMA, 0.0, reps, seed=seed, kappa=kap)
    summ = _planning_summary(axis, res, j_star, look1)
    return dict(cell=_cell_key(m, dd, PRIMARY_SIGMA), m=m, D=dd, sigma=PRIMARY_SIGMA,
                distance=math.hypot(m - m_plan, dd - d_plan), rule=final, pass0=summ[final]["PASS"])


def _full_grid_at(cal, alpha):
    """v1.3 (C336): per cell of the full grid (calibration cells + sensitivity cells), the false-PASS(10) rate and its
    Wilson 95 % upper MC bound at `alpha`, read from the committed replications; the cells whose upper bound > 0.025."""
    j = CANDIDATES.index(alpha)
    allc = dict(cal["cells"])
    allc.update((cal.get("sensitivity") or {}).get("cells", {}))
    cells = {}
    for ck, c in allc.items():
        r = _rate(_single_counts(c["hist"], j), c["reps"])
        cells[ck] = dict(m=c["m"], D=c["D"], sigma=c["sigma"], feasible=c["feasible"], rate=r["rate"], hi=r["hi"])
    over = sorted(ck for ck, c in cells.items() if c["hi"] > R.ALPHA_TOTAL)
    feas = [ck for ck, c in cells.items() if c["feasible"]]
    worst = max(feas, key=lambda ck: (cells[ck]["hi"], ck)) if feas else None
    return dict(alpha=alpha, sigmas=sorted({c["sigma"] for c in cells.values()}), target=R.ALPHA_TOTAL, cells=cells,
                over_target_realisable=[ck for ck in over if cells[ck]["feasible"]],
                over_target_unrealisable=[ck for ck in over if not cells[ck]["feasible"]],
                worst_realisable_cell=worst, worst_realisable_hi=cells[worst]["hi"] if worst is not None else None)


# ================================================================== B7.1: joint plan and pre-registered follow-up looks
# `docs/specs/m76-b7-1-joint-plan.md` v1.3 (C337 (2), C338: TD is the committed A8 path). Additive: B7's axes, numbers and RNG streams are untouched; the
# joint section reads B7's per-axis results and adds the A8 screen / decider on one nested item set, A5's per-task
# gates, a direct joint simulation and the variants.
B71_SPEC = "docs/specs/m76-b7-1-joint-plan.md v1.4"
SCREEN_LANGUAGES = 4
SCREEN_ITEMS_PER_LANGUAGE = 10          # tg2 SCREEN 40 = 10 items / language, k = 1 (one load unit)
A8_ITEMS_PER_LANGUAGE = 20              # DECIDER 80 = 20 / language; the screen's items are each language's first 10
A8_DECIDER_SESSIONS = 2                 # s1 / s2 (the same-seed reload is a control, not read by the rule)
# A8 large-harm HOLD (m65 / M76 name it, no number pre-registered; the operator's at the stage-3 Go, S23-P63):
# (key, any-language decider point threshold pp or None); HOLD ⇔ some language's point < threshold
HOLD_THRESHOLDS = (("none", None), ("lt25", -25), ("lt20", round(R.A8_HOLD_PP * 100)))   # lt20: C339, registered
HOLD_TEXT = {"none": "no large-harm HOLD", "lt25": "HOLD at any language's decider point < −25 pp",
             "lt20": "HOLD at any language's decider point < −20 pp"}
HEADLINE_HOLD = "lt20"                  # the most conservative listed threshold; every threshold is reported
HEADLINE_CELL = "nearest_realisable"    # A7's nearest realisable cell (the planning cell is extrapolated)
A5_TASK_GATE_PP = -5                    # A5 per-task point gate: each task's point estimate ≥ −5 pp (M76 §8)
# (name, macro-average threshold pp, any-language threshold pp or None); trigger ⇔ point estimate < threshold;
# macro None (TD) ⇔ always triggers (v1.2: the screen runs as a diagnostic, the decider on every plan)
SCREEN_OPTIONS = (("T0", -5, -15), ("T1", -5, None), ("T2", -5, -25), ("T3", 0, -10), ("TD", None, None))
SCREEN_OPTION_TEXT = {"T0": "today's trigger (C324): macro < −5 pp ∨ any language < −15 pp",
                      "T1": "macro < −5 pp only",
                      "T2": "macro < −5 pp ∨ any language < −25 pp",
                      "T3": "sensitive trigger: macro < 0 pp ∨ any language < −10 pp",
                      "TD": "always the decider (the screen still runs, diagnostic, C168)"}
COMMITTED_OPTION = "TD"                # v1.3 (C338): the decider always runs; T0–T3 are superseded alternatives
SUPERSEDED_TEXT = "not adopted: alternative only (superseded by C338: the committed plan runs the decider always, TD)"
NOTE_5S = "clean PASS not estimated (interaction flag unsimulated)"
SCREEN_SCENARIOS = (("loss0", (0.0, 0.0, 0.0, 0.0)), ("macro10", (0.10, 0.10, 0.10, 0.10)),
                    ("concentrated10", (0.40, 0.0, 0.0, 0.0)), ("one_language10", (0.10, 0.0, 0.0, 0.0)))
SCREEN_SCENARIO_TEXT = {"loss0": "no loss", "macro10": "10 pp loss in every language (macro 10 pp)",
                        "concentrated10": "macro 10 pp concentrated in one language (that language 40 pp)",
                        "one_language10": "one language at 10 pp, others 0 (macro 2.5 pp; descriptive)"}
A7_2L = dict(sessions=(3, 5), fraction=3 / 5, seeds=(4004, 5005))
A7_5S = dict(sessions=5, seeds=(1001, 2002, 3003, 4004, 5005))
FLAG_5S = "five-session interaction flag not simulated"
A5_2L = dict(sizes=(72, 120))
JOINT_LOSSES = (0.0, SAFE_LOSS)
JOINT_AXES = ("A1", "A5", "A7", "A8")
Z_CONSISTENT = 3.0                      # |direct − product| / SE ≤ 3 → consistent within MC error
PANEL_FWER = 0.05
ARMS = 2
GPU_HOURS = {                            # per arm; replaced by the timed smokes before the Go
    "wave1": (3.3, "M76 spec §9 stage-3 tier-1 row (Wave 1, incl. A1 tier 1)"),
    "a5_per_72": (4.0, "M76 spec §9 (A5 ≈ 4 h, unmeasured); scaled linearly in items"),
    "tg1_session": (2.7, "M76 spec §9 dropped-looks row (tg1 ≈ 2.7 h per session)"),
    "a1_tier2": (2.5, "M76 spec §9 dropped-looks row (Math500 +200 ≈ 2.5 h)"),
    "tg2_screen": (3.0, "M76 spec §9 (tg2 screen ≈ 3 h, unmeasured)"),
    "tg2_decider": (12.0, "M76 spec §9 tier-2 row (tg2 decider ≈ 12 h, unmeasured; its same-seed reload taken as "
                          "included)"),
}
STAGE_OVERHEAD = {                       # mandatory stage-3 work outside the modelled comparison legs
    "tg1_pilot_reload_per_arm": (0.3, "M76 spec §9 tier-1 row: tg1 ≈ 5.7 h per arm = s1 + s2 (2 × 2.7 h) + pilot / "
                                      "reload ≈ 0.3 h"),
    "smokes_idles_total": (5.0, "M76 spec §9 tier-1 row: ≈ 37 h total − modelled tier-1 legs (3.3 + 4 + 5.7 + 3) × 2 "
                                "= 32 h → ≈ 5 h of stage-3 smokes and idles (both arms)"),
}


# ---------------------------------------------------------------------------------------------------- A8 screen
def screen_trigger(sums, n_per_lang, macro_pp, lang_pp):
    """True iff the screen triggers the decider: macro-average point estimate < macro_pp OR (lang_pp not None) any
    language's point estimate < lang_pp. `sums` = per-language Σ (X − N16) over `n_per_lang` items; exact integer
    comparisons (100 · s < pp · n). `macro_pp` None (TD) → always True."""
    if macro_pp is None:
        return True
    n_tot = n_per_lang * len(sums)
    if 100 * sum(sums) < macro_pp * n_tot:
        return True
    return lang_pp is not None and any(100 * s < lang_pp * n_per_lang for s in sums)


def _screen_models(m, d, sigma, lang_losses, kappa):
    beta = cell_beta(m, kappa) if m is not None else None
    return [Model("A8", d, L, sigma, beta) for L in lang_losses]


def _lang_omega(mod, sigma, z):
    if sigma == 0.0 or mod.omega0 in (0.0, 1.0):
        return mod.omega0
    return _expit(_logit(mod.omega0) + sigma * z)


def _screen_draw(models, sigma, n_per_lang, rng):
    """One screen: one load unit (k = 1) → one session effect z shared by every language."""
    z = rng.normalvariate(0.0, 1.0) if sigma > 0 else 0.0
    sums = []
    for mod in models:
        om = _lang_omega(mod, sigma, z)
        s = 0
        for _ in range(n_per_lang):
            if rng.random() < mod.item_pi(rng):
                s += -1 if rng.random() < om else 1
        sums.append(s)
    return sums


def simulate_screen(m, d, sigma, lang_losses, reps, *, seed=SEED, kappa=DEFAULT_KAPPA,
                    n_per_lang=SCREEN_ITEMS_PER_LANGUAGE):
    """The tg2 SCREEN under the A8 data model at nuisance (m, D, σ) with a per-language true loss: `reps`
    replications. `m` None → homogeneous π = D_eff (no Beta). Returns {hist: {sorted per-language sums "s,s,…":
    count}, reps, n_per_lang, lang_loss_model}. Every option reads the same replications (`screen_rates`)."""
    models = _screen_models(m, d, sigma, lang_losses, kappa)
    rng = random.Random(f"m76-b7.1:screen:{seed}:m={m!r}|D={float(d)!r}|sigma={float(sigma)!r}:"
                        f"kappa={float(kappa)!r}:losses={tuple(float(x) for x in lang_losses)!r}:n={n_per_lang}")
    hist = {}
    for _ in range(reps):
        key = ",".join(str(s) for s in sorted(_screen_draw(models, sigma, n_per_lang, rng)))
        hist[key] = hist.get(key, 0) + 1
    return dict(hist=dict(sorted(hist.items())), reps=reps, n_per_lang=n_per_lang,
                lang_loss_model=[mod.loss_real for mod in models], lang_d_model=[mod.d_real for mod in models])


def screen_rates(hist, reps, n_per_lang, options=SCREEN_OPTIONS):
    """{option: Wilson rate of triggering} from a `simulate_screen` histogram."""
    out = {}
    for name, mp, lp in options:
        k = sum(c for key, c in hist.items()
                if screen_trigger([int(x) for x in key.split(",")], n_per_lang, mp, lp))
        out[name] = _rate(k, reps)
    return out


def _screen_exact_models(models, sigma, n_per_lang, macro_pp, lang_pp):
    if macro_pp is None:                # TD: always triggers
        return 1.0
    np = _np()
    xs, ws = ([0.0], [1.0]) if sigma == 0.0 else _normal_grid()
    n_tot = n_per_lang * len(models)
    vals_l = np.arange(-n_per_lang, n_per_lang + 1)
    total = 0.0
    for x, w in zip(xs, ws):
        dist, off = np.ones(1), 0
        for mod in models:
            om, p = _lang_omega(mod, sigma, x), mod.d_real
            q = np.array([p * om, 1.0 - p, p * (1.0 - om)])
            dl = np.ones(1)
            for _ in range(n_per_lang):
                dl = np.convolve(dl, q)
            if lang_pp is not None:
                dl = np.where(100 * vals_l < lang_pp * n_per_lang, 0.0, dl)
            dist, off = np.convolve(dist, dl), off - n_per_lang
        vals = np.arange(dist.size) + off
        total += w * (1.0 - float(dist[~(100 * vals < macro_pp * n_tot)].sum()))
    return min(1.0, max(0.0, total))


def screen_trigger_exact(m, d, sigma, lang_losses, option, *, kappa=DEFAULT_KAPPA,
                         n_per_lang=SCREEN_ITEMS_PER_LANGUAGE):
    """Semi-analytic trigger probability of `option` (a `SCREEN_OPTIONS` name): given the session effect the items are
    independent trinomials (P(−1) = E[π]·ω, P(+1) = E[π]·(1 − ω), E[π] = the model's realised D), so the per-language
    sums are exact convolutions; the session effect is integrated by the fixed normal quadrature."""
    _, mp, lp = next(o for o in SCREEN_OPTIONS if o[0] == option)
    return _screen_exact_models(_screen_models(m, d, sigma, lang_losses, kappa), sigma, n_per_lang, mp, lp)


def _screen_block(reps, seed, m_plan, d_plan, kap):
    """Screen trigger / detection: every scenario at A8's planning cell (σ primary), and loss 0 / macro 10 pp at
    every cell of the v1.2 grid (σ 0, 0.25)."""
    plan = {}
    for name, losses in SCREEN_SCENARIOS:
        r = simulate_screen(m_plan, d_plan, PRIMARY_SIGMA, losses, reps, seed=seed, kappa=kap)
        rates = screen_rates(r["hist"], reps, r["n_per_lang"])
        exact = {o[0]: screen_trigger_exact(m_plan, d_plan, PRIMARY_SIGMA, losses, o[0], kappa=kap)
                 for o in SCREEN_OPTIONS}
        plan[name] = dict(lang_losses=list(losses), lang_loss_model=r["lang_loss_model"],
                          lang_d_model=r["lang_d_model"], rates=rates, exact=exact, text=SCREEN_SCENARIO_TEXT[name])
    g = CAL_GRID["A8"]
    grid = {}
    for mm in g["pass_rates"]:
        for dd in g["discordance"]:
            for s in g["sigmas"]:
                why = cell_feasibility(mm, dd, kap)
                cell = dict(m=mm, D=dd, sigma=s, feasible=not why)
                for name in ("loss0", "macro10"):
                    losses = dict(SCREEN_SCENARIOS)[name]
                    r = simulate_screen(mm, dd, s, losses, reps, seed=seed, kappa=kap)
                    cell[name] = screen_rates(r["hist"], reps, r["n_per_lang"])
                grid[_cell_key(mm, dd, s)] = cell
    ranges = {}
    feas = [c for c in grid.values() if c["feasible"]]
    for name in ("loss0", "macro10"):
        ranges[name] = {o[0]: dict(min=min(c[name][o[0]]["rate"] for c in feas),
                                   max=max(c[name][o[0]]["rate"] for c in feas)) for o in SCREEN_OPTIONS}
    return dict(planning_cell=dict(m=m_plan, D=d_plan, sigma=PRIMARY_SIGMA, kappa=kap), planning=plan,
                grid=grid, grid_ranges_realisable=ranges, n_per_lang=SCREEN_ITEMS_PER_LANGUAGE,
                languages=SCREEN_LANGUAGES, options={o[0]: dict(macro_pp=o[1], language_pp=o[2],
                                                                 text=SCREEN_OPTION_TEXT[o[0]])
                                                     for o in SCREEN_OPTIONS})


# --------------------------------------------------------------------------------------------- joint product
def _cnt(r):
    return dict(k=r["k"], n=r["n"])


def _term_from(block, flag=None):
    """{PASS, LOSS, UNDECIDED, clean} Wilson rates from a per-axis summary block; `clean` = PASS ∧ no interaction
    flag (`flag` = the summary's flag dict, or None for a single-session axis)."""
    out = {v: block[v] for v in ("PASS", "LOSS", "UNDECIDED")}
    if flag is None:
        out["clean"] = block["PASS"]
    else:
        out["clean"] = _rate(block["PASS"]["k"] - flag["pass_with_flag"]["k"], block["PASS"]["n"])
    return out


# ------------------------------------------------------------------------------- A8: screen and decider, nested
def a8_nested_draw(models, sigma, rng, n_lang=A8_ITEMS_PER_LANGUAGE, n_screen=SCREEN_ITEMS_PER_LANGUAGE,
                   dec_sessions=A8_DECIDER_SESSIONS):
    """One A8 replication on ONE item set (m65 draw rule 2: the screen's items are the first `n_screen` of each
    language's `n_lang` decider items; item parameters shared). The screen is its own k = 1 session (one session
    effect shared by every language); the decider's s1 / s2 are further sessions over all items. `models`: one per
    language (duck-typed: `item_pi(rng)`, `omega0`). Returns (screen per-language Σ d, decider rows: per item
    [d_s1, d_s2], language-major, each language's first `n_screen` items = the screen's)."""
    pis = [[mod.item_pi(rng) for _ in range(n_lang)] for mod in models]

    def session():
        z = rng.normalvariate(0.0, 1.0) if sigma > 0 else 0.0
        return [_lang_omega(mod, sigma, z) for mod in models]

    def outcome(pi, om):
        if rng.random() < pi:
            return -1 if rng.random() < om else 1
        return 0
    oms = session()
    screen = [sum(outcome(pis[li][i], oms[li]) for i in range(n_screen)) for li in range(len(models))]
    rows = [[0] * dec_sessions for _ in models for _ in range(n_lang)]
    for s in range(dec_sessions):
        oms = session()
        for li in range(len(models)):
            for i in range(n_lang):
                rows[li * n_lang + i][s] = outcome(pis[li][i], oms[li])
    return screen, rows


def a8_decider_read(rows, j, rng, n_lang=A8_ITEMS_PER_LANGUAGE):
    """The decider's reading of `rows` at candidate index `j`: (verdict code, interaction flag, the smallest
    per-language Σ d over its items × sessions). The flag is drawn only for a PASS (as `simulate_multi`'s
    `pass_with_flag`)."""
    n, k = len(rows), len(rows[0])
    v = verdict_vector([sum(r) for r in rows], n, k, any(x for r in rows for x in r))[j]
    flag = v == "P" and rng.random() < fire_probability(interaction_exact_p([tuple(r) for r in rows]))
    lang = [sum(sum(r) for r in rows[li * n_lang:(li + 1) * n_lang]) for li in range(n // n_lang)]
    return v, flag, min(lang)


def hold_fires(min_lang_sum, hold_pp, n_lang=A8_ITEMS_PER_LANGUAGE, k=A8_DECIDER_SESSIONS):
    """Large-harm HOLD: some language's decider point Σ d / (n_lang · k) < hold_pp (exact integer comparison)."""
    return hold_pp is not None and 100 * min_lang_sum < hold_pp * n_lang * k


def simulate_a8_nested(m, d, sigma, lang_losses, reps, *, seed=SEED, kappa=DEFAULT_KAPPA, alpha=None, models=None):
    """The A8 path on one nested item set per replication (`a8_nested_draw`): the screen on the prefix, the decider
    on all items at `alpha` (default the decider α*, `axis_plan("A8")`), read every replication (whether or not the
    screen triggers, so conditional rates are available). `models` overrides the per-language models (tests). Returns
    {hist: {"<one trigger bit per SCREEN_OPTIONS entry, in order>|<code>|<flag 0/1>|<min language Σ d>": count}, reps, ...}."""
    alpha = R.axis_plan("A8")["looks"][0]["alpha"] if alpha is None else alpha
    j = CANDIDATES.index(alpha)
    if models is None:
        models = _screen_models(m, d, sigma, lang_losses, kappa)
    rng = random.Random(f"m76-b7.1:A8-nested:{seed}:m={m!r}|D={float(d)!r}|sigma={float(sigma)!r}:"
                        f"kappa={float(kappa)!r}:losses={tuple(float(x) for x in lang_losses)!r}:alpha={alpha!r}")
    hist = {}
    for _ in range(reps):
        screen, rows = a8_nested_draw(models, sigma, rng)
        bits = "".join("1" if screen_trigger(screen, SCREEN_ITEMS_PER_LANGUAGE, mp, lp) else "0"
                       for _, mp, lp in SCREEN_OPTIONS)
        v, flag, mn = a8_decider_read(rows, j, rng)
        key = f"{bits}|{v}|{int(flag)}|{mn}"
        hist[key] = hist.get(key, 0) + 1
    return dict(hist=dict(sorted(hist.items())), reps=reps, alpha=alpha, lang_losses=list(lang_losses),
                lang_loss_model=[getattr(mod, "loss_real", None) for mod in models])


def a8_path_from(hist, reps, option=COMMITTED_OPTION, hold="none"):
    """A8 path rates from a `simulate_a8_nested` histogram: clean = ¬trigger ∨ (trigger ∧ decider PASS ∧ no flag ∧ no
    HOLD); plus the trigger rate, the triggered decider outcomes and the decider's clean rate given / not given a
    trigger (the nesting's dependence)."""
    oi = [o[0] for o in SCREEN_OPTIONS].index(option)
    hp = dict(HOLD_THRESHOLDS)[hold]
    c = dict(trig=0, clean=0, P=0, L=0, U=0, P_flag=0, P_held=0, dec_clean=0, dec_clean_trig=0, dec_clean_notrig=0)
    for key, n in hist.items():
        bits, v, fl, mn = key.split("|")
        trig, fl, held = bits[oi] == "1", fl == "1", hold_fires(int(mn), hp)
        ok = v == "P" and not fl and not held
        c["dec_clean"] += n * ok
        if trig:
            c["trig"] += n
            c[v] += n
            c["P_flag"] += n * (v == "P" and fl)
            c["P_held"] += n * (v == "P" and not fl and held)
            c["dec_clean_trig"] += n * ok
        else:
            c["dec_clean_notrig"] += n * ok
        c["clean"] += n * ((not trig) or ok)
    nt = reps - c["trig"]
    return dict(clean=_rate(c["clean"], reps), trigger=_rate(c["trig"], reps),
                triggered_PASS=_rate(c["P"], reps), triggered_UNDECIDED=_rate(c["U"], reps),
                triggered_LOSS=_rate(c["L"], reps), triggered_PASS_flagged=_rate(c["P_flag"], reps),
                triggered_PASS_held=_rate(c["P_held"], reps), decider_clean=_rate(c["dec_clean"], reps),
                decider_clean_given_trigger=_rate(c["dec_clean_trig"], c["trig"]) if c["trig"] else None,
                decider_clean_given_no_trigger=_rate(c["dec_clean_notrig"], nt) if nt else None,
                option=option, hold=hold)


def _a8_nested_block(axes, reps, seed):
    """`simulate_a8_nested` at A8's planning cell (σ primary): loss 0 and macro 10 pp (JOINT_LOSSES), every option
    and HOLD threshold; plus, descriptively, the independence formula 1 − t + t · q with B7's unconditional decider."""
    pl8 = axes["A8"]["planning"]
    out = {}
    for L in JOINT_LOSSES:
        r = simulate_a8_nested(pl8["m"], pl8["D"], PRIMARY_SIGMA, (L,) * SCREEN_LANGUAGES, reps, seed=seed,
                               kappa=pl8["kappa"], alpha=axes["A8"]["planning_alpha"])
        paths = {o[0]: {h: a8_path_from(r["hist"], reps, o[0], h) for h, _ in HOLD_THRESHOLDS} for o in SCREEN_OPTIONS}
        c8 = axes["A8"]["cells"][f"sigma={PRIMARY_SIGMA}|loss={L}"]
        q = _term_from(c8["single"], c8["flag"])["clean"]["rate"]
        t = paths["T0"]["none"]["trigger"]["rate"]
        out[f"loss={L}"] = dict(hist=r["hist"], reps=reps, alpha=r["alpha"], paths=paths,
                                independence_formula_T0_none=1.0 - t + t * q)
    return out


def _product(terms):
    """P(clean PASS) = Π of independent per-axis clean terms; conservative interval [Π lo, Π hi] and a delta-method
    standard error (from the Wilson half-widths / 1.96)."""
    rate = lo = hi = 1.0
    rel = 0.0
    for t in terms:
        rate, lo, hi = rate * t["rate"], lo * t["lo"], hi * t["hi"]
        se = (t["hi"] - t["lo"]) / (2 * 1.96)
        rel += (se / t["rate"]) ** 2 if t["rate"] > 0 else 0.0
    return dict(rate=rate, lo=lo, hi=hi, se=rate * math.sqrt(rel))


def a5_task_gates(rows):
    """A5 per-task point gates on simulated rows (d per item, one session): items of parity 0 = retrieval, 1 =
    chain-4 (B7's task / block unit, `i % 2`); True iff each task's point estimate (c − b) / n_t ≥ −5 pp (exact)."""
    for t in (0, 1):
        vals = [r[0] for i, r in enumerate(rows) if i % 2 == t]
        if 100 * sum(vals) < A5_TASK_GATE_PP * len(vals):
            return False
    return True


def simulate_a5_gates(n, loss, sigma, reps, *, seed=SEED):
    """As `simulate_a5` (the same RNG stream: its P / L / U counts equal B7's) plus PASS ∧ both per-task point gates
    ("G") and PASS ∧ a gate failed ("F")."""
    model = Model("A5", PLANNING_D["A5"], loss, sigma, None)
    rng = random.Random(f"m76-b7:{seed}:A5:{n}:{sigma!r}:{loss!r}")
    table = a5_table(n)
    cnt = {"P": 0, "L": 0, "U": 0, "G": 0, "F": 0}
    for _ in range(reps):
        d = _gen(model, n, 1, lambda i, s: i % 2, rng)
        b = sum(1 for row in d if row[0] == -1)
        c = sum(1 for row in d if row[0] == 1)
        v = table[(b, c)]
        cnt[v] += 1
        if v == "P":
            cnt["G" if a5_task_gates(d) else "F"] += 1
    return dict(counts=cnt, reps=reps, n=n, loss=loss, sigma=sigma)


def _a5_gate_block(axes, reps, seed):
    n = axes["A5"]["n"]
    return {L: simulate_a5_gates(n, L, PRIMARY_SIGMA, reps, seed=seed) for L in JOINT_LOSSES}


def _a5_term(res):
    c, n = res["counts"], res["reps"]
    return dict(PASS=_rate(c["P"], n), LOSS=_rate(c["L"], n), UNDECIDED=_rate(c["U"], n),
                clean=_rate(c["G"], n), pass_gate_failed=_rate(c["F"], n))


def _axis_terms(axes, loss, a5_gates, a8_nested, a7_block=None):
    """Per-axis terms of the committed plan at the primary σ, true loss `loss` (0 or 10 pp): A1 (B7), A5 (PASS ∧
    per-task gates), A7 (B7's planning cell, or `a7_block` at another cell; PASS ∧ no flag), the A8 decider if run
    (B7's unconditional cell; descriptive) and the A8 path (nested; the committed option, TD) at every HOLD
    threshold."""
    key = f"sigma={PRIMARY_SIGMA}|loss={loss}"
    a1 = axes["A1"]["cells"][key][axes["A1"]["final"]]
    c7 = a7_block if a7_block is not None else axes["A7"]["cells"][key]
    c8 = axes["A8"]["cells"][key]
    by_hold = a8_nested[f"loss={loss}"]["paths"][COMMITTED_OPTION]
    return dict(A1=_term_from(a1), A5=_a5_term(a5_gates[loss]), A7=_term_from(c7["single"], c7["flag"]),
                A8_decider=_term_from(c8["single"], c8["flag"]), A8_path=by_hold[HEADLINE_HOLD],
                A8_path_by_hold=by_hold)


def _clean_by_hold(a1, a5, a7, paths):
    """{hold: P(clean PASS)} = Π of independent axis terms (A1, A5, A7 clean, A8 path clean at the hold)."""
    return {h: _product([a1, a5, a7, paths[h]["clean"]]) for h, _ in HOLD_THRESHOLDS}


def _joint_scenario(terms_by_loss, axis_loss):
    """P(clean PASS) when axis `ax` has true loss axis_loss[ax] (0 or 10 pp), at every HOLD threshold; `clean_pass`
    is the headline threshold's."""
    t = {ax: terms_by_loss[axis_loss[ax]] for ax in JOINT_AXES}
    paths = t["A8"]["A8_path_by_hold"]
    by = _clean_by_hold(t["A1"]["A1"]["clean"], t["A5"]["A5"]["clean"], t["A7"]["A7"]["clean"], paths)
    prod = by[HEADLINE_HOLD]
    return dict(axis_loss=dict(axis_loss), clean_pass=prod, clean_pass_by_hold=by, hold=HEADLINE_HOLD,
                a8_path=paths[HEADLINE_HOLD], panel_bound=max(0.0, prod["rate"] - PANEL_FWER))


def _plan_hours(p_a1_und, a5_sizes, p_a5_und, a7_sessions, p_a7_und, p_trig):
    """Per-arm GPU hours (× ARMS) of a stage-3 plan: expected = Σ P(path) · hours(path) at loss 0, which equals the
    sum of each step's hours times its probability (steps are additive); worst = every follow-up. `expected` /
    `worst` / `best` = the modelled comparison legs; `whole_stage_*` add the mandatory tg1 pilot / reload and the
    stage-3 smokes and idles (`STAGE_OVERHEAD`)."""
    h = {k: v[0] for k, v in GPU_HOURS.items()}
    n1, n2 = a5_sizes[0], a5_sizes[-1]
    s1, s2 = a7_sessions[0], a7_sessions[-1]

    def per_arm(pa1, pa5, pa7, pt):
        return (h["wave1"] + h["a1_tier2"] * pa1 + h["a5_per_72"] * (n1 + (n2 - n1) * pa5) / 72
                + h["tg1_session"] * (s1 + (s2 - s1) * pa7) + h["tg2_screen"] + h["tg2_decider"] * pt)
    # p_a1_und None: A1 has one look at 300 (the +200 always runs in tier 1)
    pa1 = 1.0 if p_a1_und is None else p_a1_und
    out = dict(expected=ARMS * per_arm(pa1, p_a5_und, p_a7_und, p_trig),
               worst=ARMS * per_arm(1.0, 1.0, 1.0, 1.0),
               best=ARMS * per_arm(1.0 if p_a1_und is None else 0.0, 0.0, 0.0, 0.0))
    over = ARMS * STAGE_OVERHEAD["tg1_pilot_reload_per_arm"][0] + STAGE_OVERHEAD["smokes_idles_total"][0]
    out.update(overhead=over, **{f"whole_stage_{k}": out[k] + over for k in ("expected", "worst", "best")})
    return out


# --------------------------------------------------------------------------------------- direct joint simulation
def simulate_joint(axes, loss, reps, *, seed=SEED, option=COMMITTED_OPTION, a7_cell=None):
    """Direct joint simulation of the committed stage-3 plan: per replication every axis (A1 two looks, A5 n with its
    per-task gates, A7 over its sessions at α* — at its planning cell or `a7_cell` = (m, D) — and A8 on one nested
    item set: the screen on the prefix → the decider on all items at α*, with every HOLD threshold) and the
    interaction flags, all at true loss `loss`; one RNG stream, independent of B7's. Returns counts; `clean|<hold>`
    = every axis clean at that HOLD threshold."""
    a1p = axes["A1"]["plan_two_look"] if axes["A1"]["final"] == "two_look" else axes["A1"]["plan_single"]
    a1_looks = [(lk["size"], lk["alpha"]) for lk in a1p["looks"]]
    m1 = Model("A1", PLANNING_D["A1"], loss, PRIMARY_SIGMA, None)
    n5 = axes["A5"]["n"]
    m5, t5 = Model("A5", PLANNING_D["A5"], loss, PRIMARY_SIGMA, None), a5_table(n5)
    pl7, pl8 = axes["A7"]["planning"], axes["A8"]["planning"]
    if axes["A7"]["final"] != "single":
        raise NotImplementedError("simulate_joint: A7 two-look plan")
    m7_, d7_ = (pl7["m"], pl7["D"]) if a7_cell is None else a7_cell
    m7 = Model("A7", d7_, loss, PRIMARY_SIGMA, cell_beta(m7_, pl7["kappa"]))
    # the α the per-axis summaries use (B7's `planning_alpha`: α*, or the smallest candidate when none is safe)
    j7, j8 = CANDIDATES.index(axes["A7"]["planning_alpha"]), CANDIDATES.index(axes["A8"]["planning_alpha"])
    d7 = _design("A7")
    scr = _screen_models(pl8["m"], pl8["D"], PRIMARY_SIGMA, (loss,) * SCREEN_LANGUAGES, pl8["kappa"])
    _, mp, lp = next(o for o in SCREEN_OPTIONS if o[0] == option)
    cell_tag = "" if a7_cell is None else f":a7={float(m7_)!r},{float(d7_)!r}"
    rng = random.Random(f"m76-b7.1:joint:{seed}:loss={loss!r}:option={option}{cell_tag}")
    c = dict(A1_P=0, A5_P=0, A5_clean=0, A7_P=0, A7_clean=0, trig=0, A8_decider_clean_given_trig=0)
    for h, _ in HOLD_THRESHOLDS:
        c[f"clean|{h}"] = c[f"A8_path_clean|{h}"] = 0
    for _ in range(reps):
        d1 = _gen(m1, a1_looks[-1][0], 1, lambda i, s: i // 50, rng)
        v1 = R.UNDECIDED
        for size, alpha in a1_looks:
            v1 = analyse(d1, range(size), range(1), alpha)[0]
            if v1 != R.UNDECIDED:
                break
        d5 = _gen(m5, n5, 1, lambda i, s: i % 2, rng)
        v5 = t5[(sum(1 for r in d5 if r[0] == -1), sum(1 for r in d5 if r[0] == 1))]
        ok5 = v5 == "P" and a5_task_gates(d5)
        r7 = _gen(m7, d7["items"], d7["sessions"], lambda i, s: s, rng)
        v7 = verdict_vector([sum(r) for r in r7], d7["items"], d7["sessions"], any(x for r in r7 for x in r))[j7]
        f7 = v7 == "P" and rng.random() < fire_probability(interaction_exact_p([tuple(r) for r in r7]))
        screen, rows8 = a8_nested_draw(scr, PRIMARY_SIGMA, rng)
        trig = screen_trigger(screen, SCREEN_ITEMS_PER_LANGUAGE, mp, lp)
        mech = v1 == R.PASS and ok5 and v7 == "P" and not f7
        if trig:
            v8, f8, mn = a8_decider_read(rows8, j8, rng)
            c["trig"] += 1
            c["A8_decider_clean_given_trig"] += v8 == "P" and not f8
        for h, hp in HOLD_THRESHOLDS:
            a8_ok = (not trig) or (v8 == "P" and not f8 and not hold_fires(mn, hp))
            c[f"A8_path_clean|{h}"] += a8_ok
            c[f"clean|{h}"] += mech and a8_ok
        c["A1_P"] += v1 == R.PASS
        c["A5_P"] += v5 == "P"
        c["A5_clean"] += ok5
        c["A7_P"] += v7 == "P"
        c["A7_clean"] += v7 == "P" and not f7
    return dict(counts=c, reps=reps, loss=loss, option=option, a7_cell=[m7_, d7_])


def _joint_check(direct, product, hold=HEADLINE_HOLD):
    r = _rate(direct["counts"][f"clean|{hold}"], direct["reps"])
    # under "direct = product" the direct count is Binomial(reps, p_product): its SE uses the product's rate (stable
    # at rates near 0 or 1, where the direct rate's own plug-in SE degenerates)
    p0 = min(max(product["rate"], 0.0), 1.0)
    se_d = math.sqrt(max(p0 * (1 - p0), 1.0 / direct["reps"] ** 2) / direct["reps"])
    z = (r["rate"] - product["rate"]) / math.sqrt(se_d ** 2 + product["se"] ** 2)
    return dict(direct=r, product=dict(rate=product["rate"], se=product["se"]), z=z, hold=hold,
                consistent=abs(z) <= Z_CONSISTENT,
                direct_terms={k: _rate(v, direct["reps"]) for k, v in sorted(direct["counts"].items())
                              if not k.startswith("clean|") and k != "A8_decider_clean_given_trig"})


def require_consistent(checks):
    """Fail closed: raise when any direct joint simulation disagrees with the product (|z| > Z_CONSISTENT)."""
    bad = sorted(k for k, c in checks.items() if not c["consistent"])
    if bad:
        raise RuntimeError("B7.1: the direct joint simulation disagrees with the product of the per-axis terms "
                           f"(|z| > {Z_CONSISTENT:g}) at " + ", ".join(f"{k} (z {checks[k]['z']:.2f})" for k in bad))


def _joint(axes, reps, seed):
    a7 = axes["A7"]
    if a7["final"] != "single" or axes["A8"]["final"] != "single":
        raise NotImplementedError("_joint: A7 / A8 two-look plans are not modelled in B7.1")
    j7 = CANDIDATES.index(a7["planning_alpha"])
    a5g = _a5_gate_block(axes, reps, seed)
    a8n = _a8_nested_block(axes, reps, seed)
    variants_a7 = {"planning": None}
    nr = a7["planning"].get("nearest_realisable")
    if nr is not None:
        blk = {}
        for L in JOINT_LOSSES:
            res = simulate_multi("A7", nr["m"], nr["D"], nr["sigma"], L, reps, seed=seed,
                                 kappa=a7["planning"]["kappa"], flags=True)
            blk[L] = _planning_summary("A7", res, j7, a7["calibration"].get("look1"))
        variants_a7["nearest_realisable"] = blk
    out = {}
    for label, blk in variants_a7.items():
        terms = {L: _axis_terms(axes, L, a5g, a8n, None if blk is None else blk[L]) for L in JOINT_LOSSES}
        scen = {"all_loss0": _joint_scenario(terms, {ax: 0.0 for ax in JOINT_AXES}),
                "all_loss10": _joint_scenario(terms, {ax: SAFE_LOSS for ax in JOINT_AXES})}
        for ax in JOINT_AXES:
            scen[f"only_{ax}_loss10"] = _joint_scenario(terms, {a: (SAFE_LOSS if a == ax else 0.0)
                                                                for a in JOINT_AXES})
        out[label] = dict(terms={f"loss={L}": terms[L] for L in JOINT_LOSSES}, scenarios=scen,
                          a7_cell=(dict(m=a7["planning"]["m"], D=a7["planning"]["D"],
                                        extrapolated=bool(a7["planning"]["pass0_extrapolated"]))
                                   if blk is None else dict(m=nr["m"], D=nr["D"], extrapolated=False)),
                          role=("headline (decision-relevant)" if label == HEADLINE_CELL else
                                "secondary (extrapolated planning cell)" if blk is None else "secondary"))
    check = {}
    for label, blk in out.items():
        cell = None if label == "planning" else (nr["m"], nr["D"])
        for L in JOINT_LOSSES:
            sc = blk["scenarios"]["all_loss0" if L == 0.0 else "all_loss10"]
            direct = simulate_joint(axes, L, reps, seed=seed, a7_cell=cell)
            for h, _ in HOLD_THRESHOLDS:
                check[f"{label}|loss={L}|{h}"] = _joint_check(direct, sc["clean_pass_by_hold"][h], hold=h)
    require_consistent(check)
    p0 = out["planning"]["terms"]["loss=0.0"]
    hours = _plan_hours(axes["A1"]["cells"][f"sigma={PRIMARY_SIGMA}|loss=0.0"]["look1"]["UNDECIDED"]["rate"]
                        if axes["A1"]["final"] == "two_look" else None,
                        (axes["A5"]["n"],), 0.0, (A7_2L["sessions"][0],), 0.0, p0["A8_path"]["trigger"]["rate"])
    head = HEADLINE_CELL if HEADLINE_CELL in out else "planning"
    return dict(spec=B71_SPEC,
                independence="axes independent of each other (separate items and sessions); A8's screen and decider "
                             "simulated on one nested item set per replication (m65 draw rule 2: the screen's 40 items "
                             "are the decider's first 40; the screen its own k = 1 session, the decider s1 / s2 over "
                             "all 80), no independence assumed between them",
                assumed=dict(a5_task_gates="A5 per-task absolute gates (each arm ≥ 0.85): assumed met (not "
                                           "simulated); the per-task point gates (retrieval, chain-4 each ≥ −5 pp) "
                                           "are simulated (task = item parity)",
                             panel=f"panel Holm flag: family-wise ≤ {PANEL_FWER} at no difference; P(clean PASS ∧ "
                                   f"no panel flag) ≥ P(clean PASS) − {PANEL_FWER} (reported as panel_bound)",
                             hold="A8 large-harm HOLD: any language's decider point < −20 pp (C339; registered as "
                                  "m76_rule.A8_HOLD_PP / a8_hold); the other listed thresholds are context"),
                sigma=PRIMARY_SIGMA, option=COMMITTED_OPTION, holds={h: dict(pp=pp, text=HOLD_TEXT[h]) for h, pp in HOLD_THRESHOLDS},
                headline=dict(cell=head, hold=HEADLINE_HOLD, hold_text=HOLD_TEXT[HEADLINE_HOLD],
                              a7_cell=out[head]["a7_cell"],
                              clean_pass=out[head]["scenarios"]["all_loss0"]["clean_pass"]),
                cells=out, direct_check=check, a8_nested=a8n, a5_gates={f"loss={L}": a5g[L] for L in JOINT_LOSSES},
                hours=hours, gpu_hours_inputs={k: dict(hours=v[0], source=v[1]) for k, v in GPU_HOURS.items()},
                stage_overhead_inputs={k: dict(hours=v[0], source=v[1]) for k, v in STAGE_OVERHEAD.items()},
                arms=ARMS)


# -------------------------------------------------------------------------------------------------- A5-2L
_A5_TABLE_AT = {}


def a5_verdict_table(n, alpha):
    """(b, c) → "P" / "L" / "U" under `verdict_a5`'s rule at one-sided `alpha` (PASS region at alpha; LOSS by the
    two-sided exact binomial, α 0.05, unchanged)."""
    key = (n, alpha)
    if key not in _A5_TABLE_AT:
        region = R.a5_pass_region(n, alpha=alpha)
        t = {}
        for b in range(n + 1):
            for c in range(n - b + 1):
                if (b, c) in region:
                    t[(b, c)] = "P"
                elif (c - b) / n < R.POINT_FLOOR and b > c and stats.mcnemar_exact(b, c) <= R.LOSS_TEST_ALPHA:
                    t[(b, c)] = "L"
                else:
                    t[(b, c)] = "U"
        _A5_TABLE_AT[key] = t
    return _A5_TABLE_AT[key]


def a5_2l_alphas(sizes=A5_2L["sizes"]):
    return stats.obf_looks((sizes[0] / sizes[1], 1.0), R.ALPHA_TOTAL)


def a5_two_look_size(n1, n2, a1, a2, *, margin=R.LOSS_MARGIN, chunk=128):
    """Exact size of the two-look A5 rule at the H0 boundary p_b = p_c + margin: max over B7's nuisance grid (1000
    interior points + endpoints of p_c ∈ [0, (1 − margin)/2]) of P(PASS at look 1) + P(UNDECIDED at look 1 ∧ PASS at
    look 2 on the cumulative (b, c)), by enumeration (look-1 trinomial(n1) × increment trinomial(n2 − n1)). Returns
    {size, size_look1, argmax_pc, union_bound}."""
    np = _np()
    t1, t2 = a5_verdict_table(n1, a1), a5_verdict_table(n2, a2)
    inc = n2 - n1
    pc = stats._nuisance_grid(margin, None, margin)

    def pmf(n):
        b, c, _, _ = stats._exact_table(n)
        p = stats._exact_probs(n, margin, None, margin, np.arange(b.size))
        mat = np.zeros((p.shape[0], n + 1, n + 1))
        mat[:, b.astype(int), c.astype(int)] = p
        return mat

    def mask(t, n, code):
        mk = np.zeros((n + 1, n + 1))
        for (b, c), v in t.items():
            if v == code:
                mk[b, c] = 1.0
        return mk
    m1, k2 = pmf(n1), pmf(inc)
    p1, u1, p2 = mask(t1, n1, "P"), mask(t1, n1, "U"), mask(t2, n2, "P")
    size1 = (m1 * p1).sum(axis=(1, 2))
    size2 = np.zeros_like(size1)
    shape = (n2 + 1, n2 + 1)
    for s in range(0, m1.shape[0], chunk):
        f = np.fft.rfft2(m1[s:s + chunk] * u1, s=shape) * np.fft.rfft2(k2[s:s + chunk], s=shape)
        conv = np.clip(np.fft.irfft2(f, s=shape), 0.0, None)
        size2[s:s + chunk] = (conv * p2).sum(axis=(1, 2))
    tot = size1 + size2
    j = int(np.argmax(tot))
    return dict(size=float(tot[j]), size_look1=float(size1.max()), argmax_pc=float(pc[j]), union_bound=a1 + a2)


def simulate_a5_2l(loss, sigma, reps, *, seed=SEED, sizes=A5_2L["sizes"]):
    """A5-2L at true loss / block SD: n1 items, then (UNDECIDED) + n2 − n1; verdict_a5's rule at the OBF-spent α of
    each look on the cumulative (b, c). Returns counts of look-1 and final P / L / U, and `final_clean` = final PASS
    ∧ the per-task point gates on the deciding look's items (gate failures never trigger look 2)."""
    n1, n2 = sizes
    a1, a2 = a5_2l_alphas(sizes)
    t1, t2 = a5_verdict_table(n1, a1), a5_verdict_table(n2, a2)
    model = Model("A5", PLANNING_D["A5"], loss, sigma, None)
    rng = random.Random(f"m76-b7.1:A5-2L:{seed}:{n1}-{n2}:{sigma!r}:{loss!r}")
    look1, final = {"P": 0, "L": 0, "U": 0}, {"P": 0, "L": 0, "U": 0}
    clean = 0
    for _ in range(reps):
        d = _gen(model, n2, 1, lambda i, s: i % 2, rng)
        b1 = sum(1 for r in d[:n1] if r[0] == -1)
        c1 = sum(1 for r in d[:n1] if r[0] == 1)
        v = t1[(b1, c1)]
        look1[v] += 1
        used = d[:n1]
        if v == "U":
            v = t2[(sum(1 for r in d if r[0] == -1), sum(1 for r in d if r[0] == 1))]
            used = d
        final[v] += 1
        clean += v == "P" and a5_task_gates(used)
    return dict(look1=look1, final=final, final_clean=clean, reps=reps)


def _variant_a5_2l(axes, reps, seed):
    n1, n2 = A5_2L["sizes"]
    a1, a2 = a5_2l_alphas()
    cells = {}
    for sigma in SIGMAS:
        for L in JOINT_LOSSES:
            r = simulate_a5_2l(L, sigma, reps, seed=seed)
            cells[f"sigma={sigma}|loss={L}"] = dict(look1=_summary3(r["look1"], reps),
                                                    two_look=_summary3(r["final"], reps),
                                                    two_look_clean=_rate(r["final_clean"], reps),
                                                    expected_items=n1 + (n2 - n1) * r["look1"]["U"] / reps)
    ex = a5_two_look_size(n1, n2, a1, a2)
    prim = {L: cells[f"sigma={PRIMARY_SIGMA}|loss={L}"] for L in JOINT_LOSSES}
    worst_sigma = max(cells[f"sigma={s}|loss={SAFE_LOSS}"]["two_look"]["PASS"]["hi"] for s in SIGMAS)
    return dict(name="A5-2L", available=True,
                looks=[dict(look=1, size=n1, alpha=a1, fraction=n1 / n2), dict(look=2, size=n2, alpha=a2, fraction=1.0)],
                exact=ex, cells=cells, pass0=prim[0.0]["two_look"]["PASS"], look1_pass0=prim[0.0]["look1"]["PASS"],
                clean0=prim[0.0]["two_look_clean"],
                undecided0=prim[0.0]["two_look"]["UNDECIDED"],
                false_pass10=prim[SAFE_LOSS]["two_look"]["PASS"], realised_false_pass10_hi_worst_sigma=worst_sigma,
                final_looks_false_pass10=dict(exact_size=ex["size"], realised_hi=prim[SAFE_LOSS]["two_look"]["PASS"]["hi"],
                                              realised_hi_worst_sigma=worst_sigma),
                safe=ex["size"] <= R.ALPHA_TOTAL,                     # B7.1 criterion 2: exact enumeration
                realised_safe=worst_sigma <= R.ALPHA_TOTAL,           # heterogeneous model, worst σ (reported)
                p_undecided_look1=prim[0.0]["look1"]["UNDECIDED"]["rate"])


# -------------------------------------------------------------------------------------------------- A7-2L
def simulate_multi_k(m, d, sigma, loss, reps, *, n_items, sessions, look1_sessions, seed=SEED,
                     kappa=DEFAULT_KAPPA, tag="A7-2L"):
    """As `simulate_multi` (no flags) with an explicit design: `sessions` in total, look 1 over the first
    `look1_sessions`; keys "<look 1>|<full>" of verdict codes at every candidate α. Own RNG stream (`tag`)."""
    model = Model("A7", d, loss, sigma, cell_beta(m, kappa))
    rng = random.Random(f"m76-b7.1:{tag}:{seed}:{_cell_key(m, d, sigma)}:kappa={float(kappa)!r}:loss={loss!r}:"
                        f"k={sessions}:k1={look1_sessions}")
    hist = {}
    for _ in range(reps):
        rows = _gen(model, n_items, sessions, lambda i, s: s, rng)
        any1 = any(x for r in rows for x in r[:look1_sessions])
        anyf = any(x for r in rows for x in r)
        key = (verdict_vector([sum(r[:look1_sessions]) for r in rows], n_items, look1_sessions, any1) + "|" +
               verdict_vector([sum(r) for r in rows], n_items, sessions, anyf))
        hist[key] = hist.get(key, 0) + 1
    return dict(hist=dict(sorted(hist.items())), reps=reps, model=dict(d_eff=model.d_eff, d_model=model.d_real,
                                                                       loss_model=model.loss_real))


def calibrate_a7_2l(reps=REPS, seed=SEED):
    """A7-2L (B7's `calibrate` method on A7's grid): look 1 = s1 + s2 + s3 against the O'Brien–Fleming spend
    α(3/5); the two-look rule (+ s4 + s5 on UNDECIDED) against 0.025; both least-favourable over every realisable
    cell. Also per candidate the worst look-1 upper bound (realisable cells)."""
    k1, k = A7_2L["sessions"]
    g = CAL_GRID["A7"]
    kap, _ = _axis_kappa("A7")
    n = _design("A7")["items"]
    cells = {}
    for m in g["pass_rates"]:
        for dd in g["discordance"]:
            for s in g["sigmas"]:
                why = cell_feasibility(m, dd, kap)
                res = simulate_multi_k(m, dd, s, SAFE_LOSS, reps, n_items=n, sessions=k, look1_sessions=k1,
                                       seed=seed, kappa=kap)
                cells[_cell_key(m, dd, s)] = dict(m=m, D=dd, sigma=s, kappa=kap, feasible=not why, hist=res["hist"],
                                                  reps=reps, model=res["model"])
    t1 = stats.obf_alpha(A7_2L["fraction"], R.ALPHA_TOTAL)
    l1 = _choose(cells, lambda h, j: _look1_counts(h, j), t1)
    out = dict(target_look1=t1, alpha_star_look1=l1["alpha_star"], binding_cell_look1=l1["binding_cell"],
               kappa=kap, reps=reps, cells=cells, grid={kk: list(v) for kk, v in g.items()})
    feas = {ck: c for ck, c in cells.items() if c["feasible"]}
    out["look1_worst_hi_by_alpha"] = {
        str(a): max(_rate(_look1_counts(c["hist"], j), c["reps"])["hi"] for c in feas.values())
        for j, a in enumerate(CANDIDATES)}
    if l1["alpha_star"] is not None:
        j1 = CANDIDATES.index(l1["alpha_star"])
        l2 = _choose(cells, lambda h, j: _two_look_counts(h, j1, j)["P"], R.ALPHA_TOTAL)
        out.update(alpha_star_look2=l2["alpha_star"], binding_cell_look2=l2["binding_cell"])
    else:
        out.update(alpha_star_look2=None, binding_cell_look2=None)
    # A7-5S: one look over all five sessions, B7's `calibrate` method on the same cells (the full-key verdicts)
    s5 = _choose(cells, lambda h, j: _single_counts(h, j), R.ALPHA_TOTAL)
    out.update(alpha_star_5s=s5["alpha_star"], binding_cell_5s=s5["binding_cell"], worst_hi_5s=s5["worst_hi_at_star"])
    return out


def _worst_feasible(cal, count):
    return max(_rate(count(c["hist"]), c["reps"])["hi"] for c in cal["cells"].values() if c["feasible"])


def _a7_variant_cells(axes, reps, seed):
    """Five-session histograms (look 1 = s1 … s3) at loss 0 at A7's planning cell and its nearest realisable cell."""
    pl = axes["A7"]["planning"]
    k1, k = A7_2L["sessions"]
    pts = {"planning": (pl["m"], pl["D"])}
    if pl.get("nearest_realisable") is not None:
        pts["nearest_realisable"] = (pl["nearest_realisable"]["m"], pl["nearest_realisable"]["D"])
    return {lab: dict(m=m, D=dd, extrapolated=lab == "planning" and bool(pl["pass0_extrapolated"]),
                      res=simulate_multi_k(m, dd, PRIMARY_SIGMA, 0.0, reps, n_items=_design("A7")["items"], sessions=k,
                                           look1_sessions=k1, seed=seed, kappa=pl["kappa"]))
            for lab, (m, dd) in pts.items()}


def _variants_a7(axes, reps, seed):
    """A7-2L and A7-5S from one calibration (`calibrate_a7_2l`, looked up at call time) and one set of five-session
    loss-0 histograms. The five-session interaction flag is not simulated: the A7 term is PASS (an upper bound on
    PASS ∧ no flag) and the variant carries `flag`."""
    cal = calibrate_a7_2l(reps, seed)
    k1, k = A7_2L["sessions"]
    cells = _a7_variant_cells(axes, reps, seed)
    pl_hist = cells["planning"]["res"]["hist"]
    look1_pass0 = {str(a): _look1_counts(pl_hist, j) / reps for j, a in enumerate(CANDIDATES)}
    available = cal["alpha_star_look1"] is not None and cal["alpha_star_look2"] is not None
    a2 = dict(name="A7-2L", available=available,
              looks=[dict(look=1, sessions=k1, fraction=A7_2L["fraction"], alpha=cal["alpha_star_look1"],
                          target=cal["target_look1"]),
                     dict(look=2, sessions=k, fraction=1.0, alpha=cal["alpha_star_look2"], target=R.ALPHA_TOTAL)],
              seeds=list(A7_2L["seeds"]), calibration=cal, look1_pass0_planning_by_alpha=look1_pass0)
    if not available:
        a2.update(safe=None, reason=(
            f"no candidate α is safe for look 1 against the O'Brien–Fleming spend {cal['target_look1']:.6f}: "
            f"at the smallest candidate {CANDIDATES[-1]} the worst realisable upper bound is "
            f"{cal['look1_worst_hi_by_alpha'][str(CANDIDATES[-1])]:.6f} (binding `{cal['binding_cell_look1']}`)"
            if cal["alpha_star_look1"] is None else
            "look 1 is safe but no candidate α is safe for the two-look rule against 0.025"))
    else:
        j1, j2 = CANDIDATES.index(cal["alpha_star_look1"]), CANDIDATES.index(cal["alpha_star_look2"])
        by = {}
        for lab, c in cells.items():
            h = c["res"]["hist"]
            two = _summary3(_two_look_counts(h, j1, j2), reps)
            und1 = _rate(_look1_counts(h, j1, "U"), reps)
            by[lab] = dict(m=c["m"], D=c["D"], extrapolated=c["extrapolated"], look1=_summary3(
                {code: _look1_counts(h, j1, code) for code in "PLU"}, reps), two_look=two, look1_undecided=und1,
                term=dict(two, clean=two["PASS"]), expected_sessions=k1 + (k - k1) * und1["rate"])
        worst = _worst_feasible(cal, lambda h: _two_look_counts(h, j1, j2)["P"])
        a2.update(safe=worst <= R.ALPHA_TOTAL, flag=FLAG_5S, by_cell=by, final_false_pass10_hi=worst)
    j5 = CANDIDATES.index(cal["alpha_star_5s"]) if cal["alpha_star_5s"] is not None else None
    a5s = dict(name="A7-5S", available=j5 is not None, sessions=k, seeds=list(A7_5S["seeds"]),
               looks=[dict(look=1, sessions=k, fraction=1.0, alpha=cal["alpha_star_5s"], target=R.ALPHA_TOTAL)],
               binding_cell=cal["binding_cell_5s"], calibration_ref="variants.A7-2L.calibration (same cells)")
    if j5 is None:
        a5s.update(safe=None, reason="no candidate α is safe for the five-session look against 0.025 (binding "
                                     f"`{cal['binding_cell_5s']}`)")
    else:
        by = {}
        for lab, c in cells.items():
            s = _summary3({code: _single_counts(c["res"]["hist"], j5, code) for code in "PLU"}, reps)
            by[lab] = dict(m=c["m"], D=c["D"], extrapolated=c["extrapolated"], single=s, term=dict(s, clean=s["PASS"]),
                           expected_sessions=k)
        worst = cal["worst_hi_5s"]
        a5s.update(safe=worst <= R.ALPHA_TOTAL, flag=FLAG_5S, by_cell=by, final_false_pass10_hi=worst)
    return a2, a5s


# --------------------------------------------------------------------------------------------------- variants
def _clean_grid(joint, a5=None, a7=None, paths=None):
    """{A7 cell: {hold: P(clean PASS) at loss 0}} of the committed plan with A5's clean term replaced by `a5`, A7's by
    `a7[cell]` and the A8 path's by `paths` ({hold: path})."""
    out = {}
    for cell, blk in joint["cells"].items():
        t = blk["terms"]["loss=0.0"]
        out[cell] = _clean_by_hold(t["A1"]["clean"], a5 if a5 is not None else t["A5"]["clean"],
                                   a7[cell] if a7 is not None else t["A7"]["clean"],
                                   paths if paths is not None else t["A8_path_by_hold"])
    return out


def _with_axis(worst, ax, hi):
    """The worst final-look false-PASS(10) upper bound with axis `ax`'s replaced by `hi`."""
    vals = dict(worst["by_axis"], **{ax: hi})
    w = max(vals, key=lambda a: (vals[a], a))
    return dict(axis=w, hi=vals[w], by_axis=vals, grid=worst["grid"], a8_residual=worst["a8_residual"])


PAYS_RULE = ("pays iff every final look is safe AND the replaced axis term's clean PASS(0) lower MC bound exceeds the "
             "committed plan's upper MC bound at the headline A7 cell (the other terms are shared); a variant whose "
             "interaction flag is not simulated reads 'undetermined' (None) where the bounds alone would say it pays")


def _pays(safe, lo, committed_hi, flag_simulated=True):
    if not safe or lo <= committed_hi:
        return False
    return True if flag_simulated else None


def _finish_variant(v, joint, grid, hours):
    head = joint["headline"]["cell"]
    v["clean_pass0_by_cell"] = grid
    v["clean_pass0"] = grid[head][HEADLINE_HOLD] if grid is not None else None
    v["hours"] = hours
    v["delta_clean_pass0"] = (v["clean_pass0"]["rate"] - joint["headline"]["clean_pass"]["rate"]
                              if grid is not None else None)
    v["delta_hours_expected"] = hours["expected"] - joint["hours"]["expected"]
    v["pays_rule"] = PAYS_RULE


def _variants(axes, joint, screen, reps, seed):
    head = joint["headline"]["cell"]
    t0h = joint["cells"][head]["terms"]["loss=0.0"]
    p_trig0 = t0h["A8_path"]["trigger"]["rate"]
    p_a1_und = (axes["A1"]["cells"][f"sigma={PRIMARY_SIGMA}|loss=0.0"]["look1"]["UNDECIDED"]["rate"]
                if axes["A1"]["final"] == "two_look" else None)
    worst = joint["worst_final_false_pass10"]
    s3 = (A7_2L["sessions"][0],)
    # A5-2L: replace the A5 term (PASS ∧ per-task gates at the deciding look)
    a5 = _variant_a5_2l(axes, reps, seed)
    _finish_variant(a5, joint, _clean_grid(joint, a5=a5["clean0"]),
                    _plan_hours(p_a1_und, A5_2L["sizes"], a5["p_undecided_look1"], s3, 0.0, p_trig0))
    a5["worst_final_false_pass10"] = _with_axis(worst, "A5", max(a5["final_looks_false_pass10"]["exact_size"],
                                                                 a5["final_looks_false_pass10"]["realised_hi_worst_sigma"]))
    a5["pays"] = _pays(a5["safe"], a5["clean0"]["lo"], t0h["A5"]["clean"]["hi"])
    a5["status"] = "adopted (C339)"
    # A7-2L / A7-5S: replace the A7 term at each cell
    a72, a75 = _variants_a7(axes, reps, seed)
    a72["status"] = "not adopted" + ("" if a72["available"] else " (unavailable: no safe look-1 α*)")
    a75["status"] = "not adopted (C339)"
    for v, sess in ((a72, A7_2L["sessions"]), (a75, (A7_5S["sessions"],))):
        if not v["available"] or not v.get("safe"):
            v["pays"] = False
            continue
        cells = {c: v["by_cell"][c]["term"]["clean"] for c in joint["cells"]}
        p_und = v["by_cell"][head]["look1_undecided"]["rate"] if len(sess) == 2 else 0.0
        hours = _plan_hours(p_a1_und, (axes["A5"]["n"],), 0.0, sess, p_und, p_trig0)
        v["worst_final_false_pass10"] = _with_axis(worst, "A7", v["final_false_pass10_hi"])
        if v["name"] == "A7-5S":
            # v1.3: the five-session interaction flag is not simulated → no clean-PASS estimate; own PASS + safety only
            _finish_variant(v, joint, None, hours)
            v.update(clean_pass_note=NOTE_5S, pass0_by_cell={c: v["by_cell"][c]["single"]["PASS"] for c in joint["cells"]},
                     pays=None)
            continue
        _finish_variant(v, joint, _clean_grid(joint, a7=cells), hours)
        v["pays"] = _pays(v["safe"], cells[head]["lo"], t0h["A7"]["clean"]["hi"], flag_simulated=False)
    # screen options in the committed plan (C324 amendment candidates; reported only); A8 path from the nested sim
    a8n = joint["a8_nested"]
    opts = {}
    for name, _, _ in SCREEN_OPTIONS:
        p0, p10 = a8n["loss=0.0"]["paths"][name], a8n[f"loss={SAFE_LOSS}"]["paths"][name]
        grid = _clean_grid(joint, paths=p0)
        grid_a5 = _clean_grid(joint, a5=a5["clean0"], paths=p0)
        t_rate = p0[HEADLINE_HOLD]["trigger"]["rate"]
        opts[name] = dict(text=SCREEN_OPTION_TEXT[name], committed=name == COMMITTED_OPTION,
                          status=("committed (C338)" if name == COMMITTED_OPTION else SUPERSEDED_TEXT),
                          trigger0=screen["planning"]["loss0"]["rates"][name],
                          detect_macro10=screen["planning"]["macro10"]["rates"][name],
                          detect_concentrated10=screen["planning"]["concentrated10"]["rates"][name],
                          detect_one_language10=screen["planning"]["one_language10"]["rates"][name],
                          grid_trigger0=screen["grid_ranges_realisable"]["loss0"][name],
                          grid_detect_macro10=screen["grid_ranges_realisable"]["macro10"][name],
                          trigger0_nested=p0[HEADLINE_HOLD]["trigger"],
                          a8_path_clean0=p0[HEADLINE_HOLD]["clean"], a8_path_clean_at_loss10=p10[HEADLINE_HOLD]["clean"],
                          a8_path_clean0_by_hold={h: p0[h]["clean"] for h, _ in HOLD_THRESHOLDS},
                          a8_path_clean_at_loss10_by_hold={h: p10[h]["clean"] for h, _ in HOLD_THRESHOLDS},
                          clean_pass0=grid[head][HEADLINE_HOLD], clean_pass0_by_cell=grid,
                          clean_pass0_a5_2l=grid_a5[head][HEADLINE_HOLD], clean_pass0_a5_2l_by_cell=grid_a5,
                          hours=_plan_hours(p_a1_und, (axes["A5"]["n"],), 0.0, s3, 0.0, t_rate),
                          hours_a5_2l=_plan_hours(p_a1_und, A5_2L["sizes"], a5["p_undecided_look1"], s3, 0.0,
                                                  t_rate))
    return {"A5-2L": a5, "A7-2L": a72, "A7-5S": a75, "screen_options": opts,
            "note": "the committed plan is TD + A5-2L (C338, C339): A5-2L adopted (C339); A7-5S and A7-2L not "
                    "adopted; the committed A8 path is TD (C338); T0–T3 not adopted, alternatives only, superseded "
                    "by C338"}


def _plan_worst_fp10(axes):
    """Worst final-look false-PASS(10) upper bound across the committed plan's mechanical axes (A5: the larger of
    the exact size and the realised upper bound; A7 / A8: worst realisable grid cell)."""
    # None (no safe α*) counts as 1.0: the worst possible
    vals = {ax: (a["final_false_pass10_hi"] if a["final_false_pass10_hi"] is not None else 1.0)
            for ax, a in axes.items() if ax != "A5"}
    vals["A5"] = max(axes["A5"]["exact_size"], axes["A5"]["final_false_pass10_hi"])
    worst = max(vals, key=lambda ax: (vals[ax], ax))
    return dict(axis=worst, hi=vals[worst], by_axis=vals, grid="committed", a8_residual=_a8_residual(axes))


def _a8_residual(axes):
    """v1.3: the C336 operator-accepted residual beside every plan with A8 — A8's realisable sensitivity cells (outside
    the committed v1.2 grid) whose false-PASS(10) upper MC bound exceeds 0.025 at the fixed decider α*."""
    res = axes["A8"].get("residual_cells") or {}
    sds = sorted({c["sigma"] for c in res.values()})
    mx = max((c["hi"] for c in res.values()), default=None)
    return dict(cells=len(res), max_hi=mx, sigmas=sds,
                text=(f"C336 residual: {len(res)} realisable SD {', '.join(f'{x:g}' for x in sds)} cells, up to "
                      f"{mx * 100:.2f} %" if res else "C336 residual: none"))


def _b71(axes, reps, seed):
    pl8 = axes["A8"]["planning"]
    screen = _screen_block(reps, seed, pl8["m"], pl8["D"], pl8["kappa"])
    joint = _joint(axes, reps, seed)
    joint["screen"] = screen
    joint["worst_final_false_pass10"] = _plan_worst_fp10(axes)
    variants = _variants(axes, joint, screen, reps, seed)
    joint["committed_plan"] = _committed_plan(joint, variants, axes["A5"]["n"])
    return joint, variants


COMMITTED_PLAN = "TD + A5-2L"


def _committed_plan(joint, variants, a5_n):
    """v1.4 (C338 + C339): the committed stage-3 plan = the TD A8 path + A5-2L (A1 / A7 / A8 rules unchanged, HOLD
    < −20 pp); its quantities are A5-2L's variant row; `reference` = the single-look A5 plan (B7's n at α 0.025)."""
    a5 = variants["A5-2L"]
    if not (a5["available"] and a5["safe"]):
        raise RuntimeError("committed plan: A5-2L is not available / safe")
    return dict(name=COMMITTED_PLAN, decisions=["C338", "C339"], a8_option=COMMITTED_OPTION, a5="A5-2L",
                a5_looks=a5["looks"], hold=HEADLINE_HOLD, a8_hold_pp=dict(HOLD_THRESHOLDS)[HEADLINE_HOLD],
                registered="m76_rule.axis_plan('A5') (two looks read from variants.A5-2L), m76_rule.A8_HOLD_PP / "
                           "a8_hold",
                not_adopted=dict(A7_5S=variants["A7-5S"]["status"], A7_2L=variants["A7-2L"]["status"],
                                 screen_triggers="T0–T3: " + SUPERSEDED_TEXT),
                clean_pass0=a5["clean_pass0"], clean_pass0_by_cell=a5["clean_pass0_by_cell"],
                a5_undecided0=a5["undecided0"], hours=a5["hours"],
                worst_final_false_pass10=a5["worst_final_false_pass10"],
                reference=dict(name=f"single-look A5 (B7: n {a5_n} at α {R.ALPHA_TOTAL}) with TD",
                               clean_pass0=joint["headline"]["clean_pass"], hours=joint["hours"]))


def build_report(reps=REPS, seed=SEED, results=_RESULTS, a5_ns=None, b71=False):
    """The report dict; `b71=True` (the CLI) adds B7.1's `joint` / `variants` keys; `b71=False` is B7's report
    exactly."""
    root = Path(results)
    a1 = load_a1_n16(root)
    a7_rows, a7_paths = load_a7_n16(root)
    beta7 = beta_from_sessions(a7_rows)
    tg2 = find_tg2_pilot(root)
    if tg2:
        raise NotImplementedError("tg2 pilot rows present: the A8 fit from rows is not implemented in B7")
    inputs = {_rel(p, root): _sha(p) for p in [x[3] for x in a1] + a7_paths + tg2}
    a1_n, a1_k = sum(x[1] for x in a1), sum(x[2] for x in a1)
    data = dict(
        A1=dict(source="P426 S′ Math500 N16 (MTP ON) blocks b1 + b2 (score.json acc_strict)", n_items=a1_n,
                strict=a1_k, m=a1_k / a1_n, beta=None,
                note="single draw per item: only the mean is identified; with k = 1 per item the per-item propensity "
                     "is marginally Bernoulli(D), so π_i = D"),
        A7=dict(source="P426 S′ tg1 N16 (MTP ON) sessions s1 + s2 (rows: passed AND converged)",
                strict={s: sum(v[s] for v in a7_rows.values()) for s in ("s1", "s2")}, beta=beta7),
        A5=dict(source="fixed p = 1.0 (planning discordance only)", beta=None),
        A8=dict(source="no tg2 pilot rows under benchmark/results/m65_pilot/ (M65_PILOT_REPORT.md only) → planning "
                       "cell p = 0.5 with the planning discordance; calibration over the pre-registered grid",
                beta=None),
    )
    axes = dict(A1=_axis_a1(reps, seed), A7=_axis_multi("A7", reps, seed), A5=_axis_a5(reps, seed, a5_ns),
                A8=_axis_multi("A8", reps, seed))
    for ax, a in axes.items():
        if ax == "A5":
            a["final_safe"] = a["exact_size"] <= R.ALPHA_TOTAL
            a["realised_safe"] = a["final_false_pass10_hi"] <= R.ALPHA_TOTAL
        else:
            a["final_safe"] = a["final_false_pass10_hi"] is not None and a["final_false_pass10_hi"] <= R.ALPHA_TOTAL
    joint = variants = None
    if b71:
        joint, variants = _b71(axes, reps, seed)
    import numpy
    header = dict(generator="bench.m76_sim", spec="docs/specs/m76-b7-statistics.md v1.4", seed=seed, reps=reps,
                  sigmas=list(SIGMAS), primary_sigma=PRIMARY_SIGMA, losses=list(LOSSES), planning_discordance=PLANNING_D,
                  alpha_total=R.ALPHA_TOTAL, point_floor=R.POINT_FLOOR, loss_margin=R.LOSS_MARGIN,
                  candidates=list(CANDIDATES), default_kappa=DEFAULT_KAPPA, interaction_iters=INTERACTION_ITERS,
                  keep_rule_a1="keep look 1 iff PASS(0) at look 1 >= 0.5 AND the Wilson 95 % upper bound of the "
                               "two-look false-PASS at loss 10 pp <= 0.025 (primary sigma)",
                  keep_rule_a7="keep look 1 iff look 1 (2 sessions) has a calibrated alpha*_1 safe at every realisable "
                               "cell against the O'Brien–Fleming spend alpha(2/3), the two-look rule has a calibrated "
                               "alpha*_2 safe at every realisable cell against 0.025, and look-1 PASS(0) at the "
                               "planning cell >= 0.5",
                  bootstrap="exact item bootstrap (m76_rule.exact_interval_values: enumerated / convolved, strata "
                            "honoured, per-item session vectors kept together); no finite resampling",
                  python=platform.python_version(), numpy=numpy.__version__, inputs_sha256=inputs, model=MODEL)
    rep = dict(header=header, data=data, axes=axes)
    if b71:
        rep.update(joint=joint, variants=variants)
    return _round(rep)


def _pct(r):
    return f"{r['rate'] * 100:.2f} % [{r['lo'] * 100:.2f}, {r['hi'] * 100:.2f}]"


def _p(x, nd=2):
    return "—" if x is None else f"{x * 100:.{nd}f} %"


AXIS_ORDER = ("A1", "A7", "A5", "A8")


def _ordered(d):
    """Items of a per-axis dict in AXIS_ORDER (independent of the JSON key order)."""
    return [(ax, d[ax]) for ax in AXIS_ORDER if ax in d]


def _ordered_cells(cells, h):
    out = []
    for sigma in h["sigmas"]:
        for loss in h["losses"]:
            key = f"sigma={float(sigma)}|loss={float(loss)}"
            out.append((key, cells[key]))
    return out


def _plan_text(ax, a):
    if ax == "A1":
        return "two looks (n 100 → 300; look 1 kept)" if a["keep_look1"] else "one look at n 300"
    if ax == "A5":
        return (f"one look, n = {a['n']} (exact test)" +
                ("" if a["n_target_met"] else " — PASS(0) ≥ 0.8 NOT reached in 42…120 → operator"))
    cal = a["calibration"]
    if a.get("alpha_star_fixed") is not None:
        return (f"one look (decider, 80 items × 2 sessions), α* {a['alpha_star_fixed']} (fixed, C336; calibrated "
                f"context α* {cal['alpha_star']})")
    if cal["alpha_star"] is None:
        return "NO candidate α* is safe → operator"
    if a["final"] == "two_look":
        return (f"two looks (sessions 2 → 3), α*₁ {a['final_alpha'][0]}, α*₂ {a['final_alpha'][1]}")
    if ax == "A7":
        return f"one look over s1 + s2 + s3, α* {cal['alpha_star']}"
    return f"one look (decider, 80 items × 2 sessions), α* {cal['alpha_star']}"


def render_md(rep):
    """REPORT.md from a report dict; output depends only on its content, never on key order."""
    h = rep["header"]
    L = ["# M76 B7 — simulation of the §8 rule (generated)", "",
         f"Generated by `{h['generator']}` (spec `{h['spec']}`); never hand-edited. Model "
         f"`{h['model']}`. Seed {h['seed']}, {h['reps']} replications per cell, Python {h['python']}, numpy "
         f"{h['numpy']}. Rates are percent with Wilson 95 % Monte Carlo intervals.", "",
         f"- Rule: PASS = point ≥ {h['point_floor'] * 100:.0f} pp AND loss bound ≤ {h['loss_margin'] * 100:.0f} pp; "
         f"LOSS = loss shown AND point < {h['point_floor'] * 100:.0f} pp; else UNDECIDED. One-sided α "
         f"{h['alpha_total']} per axis.",
         "- A1: exact item bootstrap (`m76_rule.exact_interval_values`) lower bound at the O'Brien–Fleming nominal "
         "alphas. A5: exact unconditional test (Tango score order; sup over the nuisance; exact size below). A7 / A8: "
         "exact item bootstrap lower bound at a least-favourable calibrated nominal one-sided α* (A8: fixed, C336; "
         "candidates " + ", ".join(str(c) for c in h["candidates"]) +
         ").",
         f"- A1 look rule: {h['keep_rule_a1']}.",
         f"- A7 look rule: {h['keep_rule_a7']}.",
         f"- Bootstrap: {h['bootstrap']}.",
         f"- Session SD (logit): primary {h['primary_sigma']}, sensitivity "
         f"{', '.join(str(s) for s in h['sigmas'] if s != h['primary_sigma'])}.",
         "- Planning discordance: " + ", ".join(f"{k} {v}" for k, v in _ordered(h["planning_discordance"])) +
         " (raised to the loss where the loss exceeds it).",
         f"- Session × arm interaction flag: permutation test, {h['interaction_iters']} permutations, flag p < 0.05 "
         "(simulated exactly: exact permutation null, MC count drawn as Binomial(iters, p)).", "",
         "## Inputs", ""]
    for k, v in sorted(h["inputs_sha256"].items()):
        L.append(f"- `{k}` sha256 `{v}`")
    L += ["", "## Data model fits", ""]
    for ax, d in _ordered(rep["data"]):
        extra = ""
        if ax == "A1":
            extra = f": {d['strict']}/{d['n_items']} strict (m {d['m']}); {d['note']}"
        if ax == "A7":
            b = d["beta"]
            extra = (f": strict {d['strict']}; m {b['m']}, across-session covariance {b['cov']}, Beta "
                     f"a {b['a']}, b {b['b']}" if b["a"] is not None else
                     f": strict {d['strict']}; m {b['m']}, across-session covariance {b['cov']} (≤ 0 → dispersion not "
                     "identified)")
        L.append(f"- {ax}: {d['source']}{extra}")
    ax_ = rep["axes"]
    L += ["", "## Final plan", "",
          "| axis | plan | PASS(0) | false-PASS(10) | safety check | safe |", "|---|---|---|---|---|---|"]
    for ax, a in _ordered(ax_):
        if ax == "A5":
            fp = (f"realised {_p(a['final_false_pass10'])} (upper {_p(a['final_false_pass10_hi'])}; worst σ upper "
                  f"{_p(a['realised_false_pass10_hi_worst_sigma'])})")
            chk = f"exact size {_p(a['exact_size'], 3)} ≤ 2.5 %"
        elif ax == "A1":
            fp = f"{_p(a['final_false_pass10'])} (upper {_p(a['final_false_pass10_hi'])})"
            chk = "upper MC bound ≤ 2.5 % (primary σ)"
        else:
            fp = (f"planning cell {_p(a['final_false_pass10_planning'])}; worst realisable cell upper "
                  f"{_p(a['final_false_pass10_hi'])}")
            chk = "upper MC bound ≤ 2.5 % at every realisable grid cell"
            if a.get("alpha_star_fixed") is not None:
                res = a.get("residual_cells") or {}
                sds = sorted({c["sigma"] for c in res.values()})
                sd = ", ".join(f"{s:g}" for s in sds)
                chk = (f"{'safe' if a['final_safe'] else 'NOT safe'} on the v1.2 grid; {len(res)} realisable SD "
                       f"{sd} cells over 0.025 (operator-accepted residual, C336)" if res else
                       f"{'safe' if a['final_safe'] else 'NOT safe'} on the v1.2 grid; no realisable full-grid cell "
                       "over 0.025")
        p0 = _p(a["final_pass0"])
        pl = a.get("planning") or {}
        if pl.get("pass0_extrapolated"):
            nr = pl.get("nearest_realisable")
            p0 += (" (planning cell not realisable under the data model: extrapolated" +
                   (f"; nearest realisable cell m {nr['m']:g}, D {nr['D']:g}, σ {nr['sigma']:g}: "
                    f"{_p(nr['pass0']['rate'])})" if nr else ")"))
        safe = "yes" if a["final_safe"] else "NO"
        if a.get("alpha_star_fixed") is not None:
            safe += " (v1.2 grid)"            # v1.4 (C336): safe on the v1.2 grid; residual cells in the check cell
        L.append(f"| {ax} | {_plan_text(ax, a)} | {p0} | {fp} | {chk} | {safe} |")
    unsafe = [ax for ax, a in _ordered(ax_) if not a["final_safe"]]
    if unsafe:
        L += ["", f"**Final looks failing the safety check: {', '.join(unsafe)}** — never kept as is: the operator "
                  "decides."]
    for ax in ("A7", "A8"):
        sens = ax_.get(ax, {}).get("calibration", {}).get("sensitivity")
        if sens:
            L += ["", f"- {ax} session SD {sens['sigmas']} sensitivity (never sets α*): at α* {sens['alpha_star']} "
                      f"worst realisable upper {_p(sens['worst_hi_at_alpha_star'], 3)} "
                      f"(`{sens['worst_cell_at_alpha_star']}`); unsafe at α*: "
                      f"{', '.join('`' + c + '`' for c in sens['unsafe_at_alpha_star']) or 'none'}."]
    for ax in ("A7", "A8"):
        fg = ax_.get(ax, {}).get("full_grid_at_fixed")
        if fg:
            L += ["", f"- {ax} decider α* fixed at {fg['alpha']} (C336). Full grid (σ {fg['sigmas']}) at {fg['alpha']}: "
                      f"worst realisable upper {_p(fg['worst_realisable_hi'], 3)} (`{fg['worst_realisable_cell']}`); "
                      f"realisable cells over 2.5 %: "
                      f"{', '.join('`' + c + '`' for c in fg['over_target_realisable']) or 'none'}."]
    for ax in ("A7", "A8"):
        if ax in ax_:
            fl = ax_[ax]["interaction"]
            L.append("")
            L.append(f"- {ax} interaction flag firing at the planning cell: " + "; ".join(
                f"σ {float(k.split('|')[0].split('=')[1])}, loss {float(k.split('|')[1].split('=')[1]) * 100:.0f} pp "
                f"{_pct(fl[k]['any'])}" for k in sorted(fl, key=lambda s: (float(s.split('|')[0].split('=')[1]),
                                                                           float(s.split('|')[1].split('=')[1])))))
    for ax, a in _ordered(ax_):
        L += ["", f"## {ax}", "", f"- Rule: {a['rule']}."]
        if ax == "A1":
            p = a["plan_two_look"]
            L.append("- Two-look plan: " + "; ".join(
                f"look {lk['look']} t {lk['fraction']} size {lk['size']} {lk['unit']} α {lk['alpha']} "
                f"(interval {100 * (1 - lk['interval_alpha']):.4f} %)" for lk in p["looks"]))
            k = a["keep_rule"]
            L.append(f"- Keep rule (σ {h['primary_sigma']}): PASS(0) at look 1 {k['pass0_look1'] * 100:.2f} %; "
                     f"two-look false-PASS(10) upper {k['false_pass10_two_look_hi'] * 100:.2f} % → "
                     f"{'KEEP look 1' if a['keep_look1'] else 'DROP look 1'}; false-PASS(12) "
                     f"{_p(a['final_false_pass12'])}")
            L += ["", "| σ | loss | look-1 PASS | look-1 LOSS | look-1 UND | two-look PASS | two-look LOSS | "
                      "two-look UND | exp. size | single PASS | single LOSS | single UND | realized D / loss |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
            for key, c in _ordered_cells(a["cells"], h):
                sig, loss = key.split("|")
                row = [sig.split("=")[1], f"{float(loss.split('=')[1]) * 100:.0f} pp"]
                for blk in ("look1", "two_look", None, "single"):
                    if blk is None:
                        row.append(f"{c['expected_size_two_look']:.3f}")
                        continue
                    row += [_pct(c[blk][v]) for v in ("PASS", "LOSS", "UNDECIDED")]
                m = c["model"]
                row.append(f"{m['realized_discordance']:.4f} / {m['realized_loss']:.4f}")
                L.append("| " + " | ".join(row) + " |")
        if ax == "A5":
            L += [f"- n = smallest multiple of 6 in 42…120 with PASS(0) ≥ 0.8 (σ {h['primary_sigma']}, planning "
                  f"discordance 0.05): **{a['n']}**" + ("" if a["n_target_met"] else " (target NOT reached; largest n "
                                                        "reported → operator)"),
                  f"- Exact size at n = {a['n']} (max over the nuisance grid of P(region ∧ δ ≥ −5 pp) at margin "
                  f"10 pp): {_p(a['exact_size'], 3)}; realised false-PASS(10) under the heterogeneous (block-effect) "
                  f"model: {_p(a['final_false_pass10'], 3)} (upper {_p(a['final_false_pass10_hi'], 3)}); "
                  f"false-PASS(12) {_p(a['final_false_pass12'], 3)}.",
                  "", "| n | PASS(0) | realised false-PASS(10) | exact size | region cells |", "|---|---|---|---|---|"]
            L += [f"| {n} | {_pct(r['pass0'])} | {_pct(r['false_pass10'])} | {_p(r['exact_size'], 3)} | "
                  f"{r['region_size']} |" for n, r in sorted(a["n_scan"].items(), key=lambda kv: int(kv[0]))]
            L += ["", f"Grid at n = {a['n']}:", "", "| σ | loss | PASS | LOSS | UNDECIDED | realized D / loss |",
                  "|---|---|---|---|---|---|"]
            for key, c in _ordered_cells(a["cells"], h):
                sig, loss = key.split("|")
                m = c["model"]
                L.append(f"| {sig.split('=')[1]} | {float(loss.split('=')[1]) * 100:.0f} pp | "
                         + " | ".join(_pct(c["single"][v]) for v in ("PASS", "LOSS", "UNDECIDED"))
                         + f" | {m['realized_discordance']:.4f} / {m['realized_loss']:.4f} |")
        if ax in ("A7", "A8"):
            L += _render_multi(ax, a, h)
    if "joint" in rep:
        L += _render_joint(rep)
    L.append("")
    return "\n".join(L)


def _rng3(r):
    """'x.xx % [lo, hi]' for a rate dict carrying lo / hi."""
    return f"{r['rate'] * 100:.2f} % [{r['lo'] * 100:.2f}, {r['hi'] * 100:.2f}]"


def _pvu(t):
    return " / ".join(f"{t[v]['rate'] * 100:.2f}" for v in ("PASS", "UNDECIDED", "LOSS"))


_CELL_ORDER = ("nearest_realisable", "planning")


def _cells_of(j):
    return [c for c in _CELL_ORDER if c in j["cells"]]


def _cell_label(j, c):
    a = j["cells"][c]["a7_cell"]
    return (f"A7 nearest realisable cell m {a['m']:g}, D {a['D']:g} (headline)" if c == "nearest_realisable" else
            f"A7 planning cell m {a['m']:g}, D {a['D']:g} ({'extrapolated; ' if a['extrapolated'] else ''}secondary)")


def _render_joint(rep):
    """B7.1 "Joint plan" section (appended after B7's sections, which stay byte-identical)."""
    j, v = rep["joint"], rep["variants"]
    cp = j["committed_plan"]
    sc = j["screen"]
    cells = _cells_of(j)
    hd = j["headline"]
    head = hd["cell"]
    th = j["cells"][head]["terms"]["loss=0.0"]
    wf = j["worst_final_false_pass10"]
    holds = [h for h, _ in HOLD_THRESHOLDS]
    hold_short = {"none": "no HOLD", "lt25": "HOLD < −25 pp", "lt20": "HOLD < −20 pp"}
    a5, a72, a75 = v["A5-2L"], v["A7-2L"], v["A7-5S"]
    L = ["", "## Joint plan (B7.1)", "",
         f"Spec `{j['spec']}`. Ship recommendation needs every mechanical axis PASS, no interaction flag and the A8 "
         "path clean at once: P(clean PASS) = P(A1 PASS) × P(A5 PASS ∧ per-task point gates) × P(A7 PASS ∧ no flag) × "
         "P(A8 path clean). The committed A8 path is TD (C338): the decider always runs (the screen still runs, a "
         "diagnostic), so A8 path clean = decider PASS ∧ no decider flag ∧ no large-harm HOLD; the screen triggers T0–"
         "T3 (A8 path clean = screen not triggered ∨ (triggered ∧ decider clean)) are alternatives only, superseded by "
         f"C338. Assumptions: {j['independence']}; {j['assumed']['a5_task_gates']}; "
         f"{j['assumed']['panel']}; {j['assumed']['hold']}. Primary session SD {j['sigma']}; A8 path "
         f"{j['option']}; product intervals are conservative ([Π lo, Π hi] of the Wilson 95 % terms). The committed "
         f"plan is {cp['name']} ({', '.join(cp['decisions'])}): A5 runs A5-2L (n {cp['a5_looks'][0]['size']} at α "
         f"{cp['a5_looks'][0]['alpha']:.6f}, then n {cp['a5_looks'][1]['size']} at α {cp['a5_looks'][1]['alpha']:.6f}; "
         "a look-1 LOSS stops; registered in `m76_rule.axis_plan('A5')`, read from this report), A8 runs TD with the "
         "HOLD at any language's decider point < −20 pp (`m76_rule.A8_HOLD_PP`); A1 / A7 / A8 rules unchanged. "
         "A7-5S, A7-2L and T0–T3 are not adopted.", "",
         f"**Headline: P(clean PASS) at loss 0 = {_rng3(cp['clean_pass0'])}** — committed plan {cp['name']}; "
         f"{_cell_label(j, head)}; {hd['hold_text']} (C339). Single-look A5 reference (TD): "
         f"{_rng3(hd['clean_pass'])}. The planning-cell column is "
         "secondary: that cell is not realisable under the data model.", "",
         "| plan / variant | " + " | ".join(f"clean PASS at loss 0, {_cell_label(j, c)}, {hold_short[h]}"
                                         for c in cells for h in holds) +
         " | A1 UND | A5 UND | A7 UND (" + " / ".join("nearest" if c == "nearest_realisable" else "planning"
                                                     for c in cells) +
         ") | A8 decider UND (TD: always run) | false-PASS(10) upper, worst on the committed grid (+ the C336 A8 "
         "residual) | GPU h modelled legs, expected / "
         "worst (both arms) | GPU h whole stage, expected / worst | pays |",
         "|---|" + "---|" * (len(cells) * len(holds) + 8)]

    def cp_cells(grid):
        out = []
        for c in cells:
            for h in holds:
                s = _rng3(grid[c][h])
                out.append(f"**{s}**" if (c, h) == (head, HEADLINE_HOLD) else s)
        return out

    def row(label, grid, und, worst, hours, pays, cp=None):
        ws = f"{worst['hi'] * 100:.2f} % ({worst['axis']}); {worst['a8_residual']['text']}"
        hm = f"{hours['expected']:.1f} / {hours['worst']:.1f}"
        hw = f"{hours['whole_stage_expected']:.1f} / {hours['whole_stage_worst']:.1f}"
        p = "—" if pays == "—" else ("yes" if pays is True else "no" if pays is False else
                                     "undetermined (flag not simulated) → operator")
        return "| " + " | ".join([label] + (cp_cells(grid) if cp is None else cp) + und + [ws, hm, hw, p]) + " |"

    def pc(r):
        return f"{r['rate'] * 100:.2f} %"
    a8u = pc(th["A8_path"]["triggered_UNDECIDED"])        # TD: trigger ≡ 1 → the decider's UNDECIDED rate
    base_grid = {c: j["cells"][c]["scenarios"]["all_loss0"]["clean_pass_by_hold"] for c in cells}
    a7u = " / ".join(pc(j["cells"][c]["terms"]["loss=0.0"]["A7"]["UNDECIDED"]) for c in cells)
    L.append(row(f"committed plan ({cp['name']}; {', '.join(cp['decisions'])})", cp["clean_pass0_by_cell"],
                 [pc(th["A1"]["UNDECIDED"]), pc(cp["a5_undecided0"]), a7u, a8u], cp["worst_final_false_pass10"],
                 cp["hours"], "—"))
    L.append(row(f"single-look A5 reference (TD; B7's A5 n {rep['axes']['A5']['n']} at α {R.ALPHA_TOTAL}; replaced "
                 "by A5-2L, C339)", base_grid, [pc(th["A1"]["UNDECIDED"]), pc(th["A5"]["UNDECIDED"]), a7u, a8u],
                 wf, j["hours"], "—"))
    L.append(row(f"A5-2L (n {a5['looks'][0]['size']} → {a5['looks'][1]['size']}, α {a5['looks'][0]['alpha']:.6f} / "
                 f"{a5['looks'][1]['alpha']:.6f}; {a5['status']}; pays vs the single-look reference)",
                 a5["clean_pass0_by_cell"],
                 [pc(th["A1"]["UNDECIDED"]), pc(a5["undecided0"]), a7u, a8u], a5["worst_final_false_pass10"],
                 a5["hours"], a5["pays"]))
    for var, label, blk in ((a72, "A7-2L (s1–s3 → + s4 + s5)", "two_look"), (a75, "A7-5S (s1 … s5, one look)",
                                                                           "single")):
        if var["available"] and var.get("safe") and var.get("clean_pass_note"):
            # v1.3 (A7-5S): no clean-PASS estimate; the row shows the variant's own A7 PASS(0) and its safety
            u = " / ".join(pc(var["by_cell"][c][blk]["UNDECIDED"]) for c in cells)
            lab = (f"{label}, α {' / '.join(str(lk['alpha']) for lk in var['looks'])}; {var['status']}; "
                   f"{var['clean_pass_note']}; "
                   "A7-5S's own A7 PASS at loss 0 per cell: " + "; ".join(
                       f"{'nearest' if c == 'nearest_realisable' else 'planning'} {_rng3(var['pass0_by_cell'][c])}"
                       for c in cells) + f"; final look {'safe' if var['safe'] else 'NOT safe'}")
            L.append(row(lab, None, [pc(th["A1"]["UNDECIDED"]), pc(th["A5"]["UNDECIDED"]), u, a8u],
                         var["worst_final_false_pass10"], var["hours"], var["pays"],
                         cp=["not estimated"] * (len(cells) * len(holds))))
        elif var["available"] and var.get("safe"):
            u = " / ".join(pc(var["by_cell"][c][blk]["UNDECIDED"]) for c in cells)
            lab = (f"{label}, α {' / '.join(str(lk['alpha']) for lk in var['looks'])}; {var['status']}; {var['flag']} (A7 term = "
                   "PASS, an upper bound)")
            L.append(row(lab, var["clean_pass0_by_cell"], [pc(th["A1"]["UNDECIDED"]), pc(th["A5"]["UNDECIDED"]), u,
                                                           a8u], var["worst_final_false_pass10"], var["hours"],
                         var["pays"]))
        else:
            why = "no safe look-1 α*" if var["name"] == "A7-2L" and var["looks"][0]["alpha"] is None else \
                "no safe α*" if not var["available"] else "a final look is not safe"
            L.append(f"| {label} ({var['status']}) | not available: {why} | " +
                     " | ".join(["—"] * (len(cells) * len(holds) + 7)) +
                     " |")
    L += [""]
    for c in cells:
        for L_key, label in (("loss=0.0", "loss 0"), ("loss=0.1", "loss 10 pp")):
            t = j["cells"][c]["terms"][L_key]
            p = t["A8_path"]
            L.append(f"- Per axis at {label} ({_cell_label(j, c)}; PASS / UND / LOSS %): A1 {_pvu(t['A1'])}; A5 "
                     f"{_pvu(t['A5'])} (PASS ∧ per-task gates {t['A5']['clean']['rate'] * 100:.2f}; PASS with a gate "
                     f"failed {t['A5']['pass_gate_failed']['rate'] * 100:.2f}); A7 {_pvu(t['A7'])} (PASS ∧ no flag "
                     f"{t['A7']['clean']['rate'] * 100:.2f}); A8 decider if run {_pvu(t['A8_decider'])} (PASS ∧ no "
                     f"flag {t['A8_decider']['clean']['rate'] * 100:.2f}); screen trigger {_rng3(p['trigger'])}; A8 "
                     f"path clean ({hold_short[HEADLINE_HOLD]}) {_rng3(p['clean'])}.")
    for L_key, label in (("loss=0.0", "loss 0"), (f"loss={SAFE_LOSS}", "macro 10 pp")):
        n8 = j["a8_nested"][L_key]
        p = n8["paths"]["T0"]
        gt, gn = p["none"]["decider_clean_given_trigger"], p["none"]["decider_clean_given_no_trigger"]
        L.append(f"- A8 nested (one item set; {label}; under the superseded T0 trigger, descriptive of the nesting): "
                 "decider PASS ∧ no flag given the screen triggered "
                 f"{_rng3(gt) if gt else '—'} vs not triggered {_rng3(gn) if gn else '—'}; A8 path clean by HOLD: " +
                 "; ".join(f"{hold_short[h]} {_rng3(p[h]['clean'])}" for h in holds) +
                 f" (the independence formula 1 − t + t · q with B7's unconditional decider would read "
                 f"{n8['independence_formula_T0_none'] * 100:.2f} % at no HOLD).")
    for c in cells:
        s = j["cells"][c]["scenarios"]
        L.append(f"- P(clean PASS) by true loss ({_cell_label(j, c)}; {hold_short[HEADLINE_HOLD]}): every axis 0 → "
                 f"{_rng3(s['all_loss0']['clean_pass'])}; every axis 10 pp → {_rng3(s['all_loss10']['clean_pass'])}; "
                 "10 pp on one axis at a time (descriptive): " +
                 "; ".join(f"{ax} {_rng3(s[f'only_{ax}_loss10']['clean_pass'])}" for ax in JOINT_AXES) +
                 f". With the panel's Holm flag (family-wise ≤ {PANEL_FWER}): P(clean PASS ∧ no panel flag) ≥ "
                 f"{s['all_loss0']['panel_bound'] * 100:.2f} % at loss 0 (bound, not simulated).")
    zs = j["direct_check"]
    worst_z = max(zs, key=lambda k: (abs(zs[k]["z"]), k))
    L.append(f"- Direct joint simulation vs product (on the single-look A5 reference; A5-2L replaces an independent "
             f"axis term; {len(zs)} checks: each A7 cell × loss 0 / 10 pp × HOLD "
             f"threshold; the build fails closed at |z| > {Z_CONSISTENT:g}): largest |z| {abs(zs[worst_z]['z']):.2f} "
             f"(`{worst_z}`). " + "; ".join(
                 f"`{k}` direct {_rng3(zs[k]['direct'])} vs product {zs[k]['product']['rate'] * 100:.2f} % (z "
                 f"{zs[k]['z']:.2f})" for k in sorted(zs) if k.endswith("|" + HEADLINE_HOLD)) + ".")
    h = j["hours"]
    ch = cp["hours"]
    L.append("- GPU hours (both arms; expected at loss 0 = Σ P(path) × hours(path)): committed plan "
             f"({cp['name']}) modelled comparison legs {ch['expected']:.1f} expected / {ch['worst']:.1f} worst; whole "
             f"stage {ch['whole_stage_expected']:.1f} / {ch['whole_stage_worst']:.1f}; single-look A5 reference legs "
             f"{h['expected']:.1f} expected / {h['worst']:.1f} worst; whole stage {h['whole_stage_expected']:.1f} / "
             f"{h['whole_stage_worst']:.1f} (+ {h['overhead']:.1f} h mandatory). Leg inputs per arm: " + "; ".join(
                 f"{k} {x['hours']:g} h ({x['source']})" for k, x in sorted(j["gpu_hours_inputs"].items())) +
             ". Mandatory work outside the legs: " + "; ".join(
                 f"{k} {x['hours']:g} h ({x['source']})" for k, x in sorted(j["stage_overhead_inputs"].items())) +
             ". The panel is not GPU work here; added legs carry no added idles in this model.")
    ex = a5["exact"]
    L.append(f"- A5-2L: look 1 n {a5['looks'][0]['size']} at α {a5['looks'][0]['alpha']:.6f}, look 2 n "
             f"{a5['looks'][1]['size']} at α {a5['looks'][1]['alpha']:.6f} (O'Brien–Fleming, t₁ "
             f"{a5['looks'][0]['fraction']:g}); exact two-look size {ex['size'] * 100:.3f} % (look 1 alone "
             f"{ex['size_look1'] * 100:.3f} %; at p_c {ex['argmax_pc']:g}; union bound {ex['union_bound'] * 100:.3f} %); "
             f"realised false-PASS(10) {_rng3(a5['false_pass10'])}, worst σ upper "
             f"{a5['realised_false_pass10_hi_worst_sigma'] * 100:.2f} %; PASS(0) look 1 {_rng3(a5['look1_pass0'])}, "
             f"two-look {_rng3(a5['pass0'])}, two-look PASS ∧ per-task gates {_rng3(a5['clean0'])} (single-look "
             f"reference {_rng3(th['A5']['clean'])}); {'safe' if a5['safe'] else 'NOT safe'} by exact size (realised worst "
             f"σ {'within' if a5['realised_safe'] else 'OVER'} 2.5 %); {a5['status']}; Δ clean PASS vs the single-look reference "
             f"{a5['delta_clean_pass0'] * 100:+.2f} pp for {a5['delta_hours_expected']:+.1f} expected GPU h → "
             f"**{'pays' if a5['pays'] else 'does not pay'}**.")
    cal = a72["calibration"]
    L.append(f"- A7-2L: look 1 (s1 + s2 + s3) target = O'Brien–Fleming spend {cal['target_look1']:.6f} at t₁ "
             f"{A7_2L['fraction']:g}; worst realisable look-1 false-PASS(10) upper by candidate α: " + ", ".join(
                 f"{a} → {cal['look1_worst_hi_by_alpha'][str(a)] * 100:.2f} %" for a in CANDIDATES) +
             f"; look-1 PASS(0) at the planning cell at {CANDIDATES[-1]}: "
             f"{a72['look1_pass0_planning_by_alpha'][str(CANDIDATES[-1])] * 100:.2f} %. " +
             (f"**Not available**: {a72['reason']} → does not pay as specified (→ the operator)."
              if not a72["available"] else
              f"Available ({a72['flag']}); final looks {'safe' if a72['safe'] else 'NOT safe'} (worst realisable "
              f"upper {a72['final_false_pass10_hi'] * 100:.2f} %)."))
    if a75["available"]:
        L.append(f"- A7-5S: one look over s1 … s5 (seeds {', '.join(str(s) for s in a75['seeds'])}) at calibrated α* "
                 f"{a75['looks'][0]['alpha']} (B7's `calibrate` method on A7's grid; binding `{a75['binding_cell']}`; "
                 f"worst realisable false-PASS(10) upper {a75['final_false_pass10_hi'] * 100:.2f} %); PASS(0) " +
                 "; ".join(f"{_cell_label(j, c)} {_rng3(a75['by_cell'][c]['single']['PASS'])}" for c in cells) +
                 f" (committed 3-session PASS ∧ no flag at the headline cell {_rng3(th['A7']['clean'])}); {a75['flag']}: "
                 f"{a75['clean_pass_note']}; pays undetermined (→ the operator); 5 sessions per arm always.")
    else:
        L.append(f"- A7-5S: **not available**: {a75['reason']}.")
    L += ["", f"Screen options (C324 amendment candidates; reported only, never applied; TD (C338) is the committed "
              "A8 path, T0–T3 are alternatives only, superseded by C338). Screen: "
              f"{sc['languages']} languages × {sc['n_per_lang']} items, k = 1; planning cell m {sc['planning_cell']['m']:g}, "
              f"D {sc['planning_cell']['D']:g}, σ {sc['planning_cell']['sigma']:g}; grid = A8's v1.2 grid "
              "(realisable cells, min – max). Concentrated: data-model loss in that language "
              f"{sc['planning']['concentrated10']['lang_loss_model'][0] * 100:.1f} pp. \"A8 path clean at macro 10 "
              "pp\" is the A8 path's false-clean rate (screen missed, or decider PASS without flag or HOLD); it and the "
              f"clean PASS come from the nested A8 simulation ({hold_short[HEADLINE_HOLD]}; headline A7 cell in "
              "bold).", "",
          "| option | trigger at loss 0 | trigger at loss 0, grid | detection, macro 10 pp | detection, macro 10 pp, "
          "grid | detection, 10 pp in one language (40 pp there) | one language at 10 pp | A8 path clean at macro "
          "10 pp | " + " | ".join(f"clean PASS at loss 0, {_cell_label(j, c)}{a}" for a in ("", ", with A5-2L")
                                  for c in cells) +
          " | GPU h modelled legs expected (with A5-2L) | GPU h whole stage expected (with A5-2L) |",
          "|---|" + "---|" * (9 + 2 * len(cells))]
    for name, _, _ in SCREEN_OPTIONS:
        o = v["screen_options"][name]
        cp = []
        for key in ("clean_pass0_by_cell", "clean_pass0_a5_2l_by_cell"):
            for c in cells:
                s = _rng3(o[key][c][HEADLINE_HOLD])
                cp.append(f"**{s}**" if c == head else s)
        h, h5 = o["hours"], o["hours_a5_2l"]
        L.append(f"| {name}: {o['text']} — {o['status']} | {_rng3(o['trigger0'])} | {o['grid_trigger0']['min'] * 100:.2f} – "
                 f"{o['grid_trigger0']['max'] * 100:.2f} % | {_rng3(o['detect_macro10'])} | "
                 f"{o['grid_detect_macro10']['min'] * 100:.2f} – {o['grid_detect_macro10']['max'] * 100:.2f} % | "
                 f"{_rng3(o['detect_concentrated10'])} | {_rng3(o['detect_one_language10'])} | "
                 f"{_rng3(o['a8_path_clean_at_loss10'])} | " + " | ".join(cp) +
                 f" | {h['expected']:.1f} ({h5['expected']:.1f}) | {h['whole_stage_expected']:.1f} "
                 f"({h5['whole_stage_expected']:.1f}) |")
    L += ["", "TD runs the decider on every plan (trigger 100 % by construction); its A8 path clean at macro 10 pp is the "
              "decider's PASS ∧ no flag ∧ no HOLD rate. Columns with A5-2L replace the committed A5 term by A5-2L's; "
              f"clean PASS cells use {hold_short[HEADLINE_HOLD]}."]
    return L


def _render_multi(ax, a, h):
    cal = a["calibration"]
    pl = a["planning"]
    g = cal["grid"]
    fixed = a.get("alpha_star_fixed")
    L = []
    if fixed is not None:
        L.append(f"- **Decider α* = {fixed}** ({a['alpha_star_source']}); the calibration below is context only "
                 "and does not set it.")
    L += [f"- Calibration grid: pass rate {g['pass_rates']} × discordance {g['discordance']} × session SD "
         f"{g['sigmas']}; per-item Beta concentration {cal['kappa']} ({cal['kappa_source']}); {cal['reps']} "
         f"replications per cell at loss {cal['safe_loss'] * 100:.0f} pp.",
         ("- Calibrated (context only) " if fixed is not None else "- ") +
         f"**α* = {cal['alpha_star']}** (largest candidate with upper MC bound of false-PASS(10) ≤ {cal['target']} "
         f"at every realisable cell); binding cell `{cal['binding_cell']}`; worst upper at α* "
         f"{_p(cal['worst_hi_at_star'], 3)}; next larger candidate's worst upper "
         f"{_p(cal['next_larger_worst_hi'], 3)}. Including the unrealisable cells: α* "
         f"{cal['alpha_star_incl_infeasible']}." + (
             f" Sensitivity (not the rule): without the σ {cal['sensitivity_without_max_sigma']['sigma_excluded']} "
             f"cells, α* {cal['sensitivity_without_max_sigma']['alpha_star']}."
             if "sensitivity_without_max_sigma" in cal else ""),
         f"- PASS(0) at the planning cell (σ {h['primary_sigma']}) by candidate α: " + ", ".join(
             f"{al} → {_p(a['planning_pass0_by_alpha'][str(al)], 1)}" for al in cal["candidates"]) + ".",
         f"- Skipped (unrealisable) cells: {', '.join('`' + c + '`' for c in cal['skipped_cells']) or 'none'}.",
         f"- Planning cell m {pl['m']}, D {pl['D']}, κ {pl['kappa']}: "
         + ("realisable" if pl["feasible"] else "NOT realisable under the data model (" +
            "; ".join(pl["infeasible_reasons"]) + ") — simulated regardless, not used for α*") +
         f". PASS(0) at " + (f"the decider α* {fixed}" if fixed is not None else "α*") +
         f" (σ {h['primary_sigma']}): **{_p(a['final_pass0'])}**" +
         ("" if pl["feasible"] else " (extrapolated)" + (
             f"; nearest realisable cell `{pl['nearest_realisable']['cell']}` (distance "
             f"{pl['nearest_realisable']['distance']:.4f} in (m, D)): PASS(0) "
             f"{_pct(pl['nearest_realisable']['pass0'])}" if pl.get("nearest_realisable") else "")) + ".",
         f"- Uncalibrated v1 reference (nominal OBF α 0.025, read from the same replications): see the α = 0.025 "
         "column below."]
    if ax == "A7":
        l1 = cal["look1"]
        L.append(f"- Look 1 (s1 + s2): α*₁ = {l1['alpha_star']} against the O'Brien–Fleming spend "
                 f"{l1['target']:.6f} (binding `{l1['binding_cell']}`); two-look α*₂ = {l1.get('alpha_star_look2')} "
                 f"(binding `{l1.get('binding_cell_look2')}`); look-1 PASS(0) at the planning cell "
                 f"{_p(l1.get('pass0_look1_planning'))} → {'KEEP' if l1.get('keep') else 'DROP'} look 1.")
    cands = cal["candidates"]
    L += ["", "False-PASS(10) by cell and candidate α (rate %; ✗ = upper MC bound > 2.5 %):", "",
          "| cell | realisable | " + " | ".join(str(c) for c in cands) + " |",
          "|---|---|" + "---|" * len(cands)]
    for ck in sorted(cal["cells"], key=lambda s: tuple(float(x.split("=")[1]) for x in s.split("|"))):
        c = cal["cells"][ck]
        row = [f"`{ck}`", "yes" if c["feasible"] else "no"]
        for j in range(len(cands)):
            r = _rate(_single_counts(c["hist"], j), c["reps"])
            row.append(f"{r['rate'] * 100:.2f}{' ✗' if r['hi'] > cal['target'] else ''}")
        L.append("| " + " | ".join(row) + " |")
    if "sensitivity" in cal:
        L += _render_sensitivity(cal["sensitivity"], cands, cal["target"])
    if a.get("full_grid_at_fixed"):
        L += _render_full_grid(a["full_grid_at_fixed"])
    blocks = ["single"] + (["look1", "two_look"] if any("two_look" in c for c in a["cells"].values()) else [])
    cap = (f"Planning cell at the final α (σ × loss):" if cal["alpha_star"] is not None else
           f"Planning cell at the smallest candidate α {a['planning_alpha']} (no α* is safe; informational):")
    L += ["", cap, "",
          "| σ | loss | " + " | ".join(f"{b} PASS | {b} LOSS | {b} UND" for b in blocks) +
          " | interaction flag | realized D / loss |",
          "|---|---|" + "---|---|---|" * len(blocks) + "---|---|"]
    for key, c in _ordered_cells(a["cells"], h):
        sig, loss = key.split("|")
        row = [sig.split("=")[1], f"{float(loss.split('=')[1]) * 100:.0f} pp"]
        for b in blocks:
            row += [_pct(c[b][v]) if b in c else "—" for v in ("PASS", "LOSS", "UNDECIDED")]
        row.append(_pct(c["flag"]["any"]) if "flag" in c else "—")
        m = c["model"]
        row.append(f"{m['realized_discordance']:.4f} / {m['realized_loss']:.4f}")
        L.append("| " + " | ".join(row) + " |")
    return L


def _render_sensitivity(sens, cands, target):
    star = sens["alpha_star"]
    L = ["", f"Sensitivity only (v1.2, C335; never sets α*): session SD {sens['sigmas']} cells. At α* {star}: worst "
             f"upper bound {_p(sens['worst_hi_at_alpha_star'], 3)} (`{sens['worst_cell_at_alpha_star']}`); realisable "
             f"cells unsafe at α*: {', '.join('`' + c + '`' for c in sens['unsafe_at_alpha_star']) or 'none'}.", "",
         "| cell | realisable | upper at α* | smallest safe candidate | largest safe candidate | "
         + " | ".join(str(c) for c in cands) + " |",
         "|---|---|---|---|---|" + "---|" * len(cands)]
    for ck in sorted(sens["cells"], key=lambda s: tuple(float(x.split("=")[1]) for x in s.split("|"))):
        c = sens["cells"][ck]
        row = [f"`{ck}`", "yes" if c["feasible"] else "no", _p(c["hi_at_alpha_star"], 3),
               str(c["smallest_safe"]) if c["smallest_safe"] is not None else "none",
               str(c["largest_safe"]) if c["largest_safe"] is not None else "none"]
        for j in range(len(cands)):
            r = _rate(_single_counts(c["hist"], j), c["reps"])
            row.append(f"{r['rate'] * 100:.2f}{' ✗' if r['hi'] > target else ''}")
        L.append("| " + " | ".join(row) + " |")
    return L


def _render_full_grid(fg):
    over = fg["over_target_realisable"]
    L = ["", f"Full grid at the decider α* {fg['alpha']} (v1.3, C336; session SD {fg['sigmas']}): false-PASS(10) and its "
             f"upper MC bound per cell. Realisable cells over {_p(fg['target'], 1)}: "
             f"{', '.join('`' + c + '`' for c in over) or 'none'}; unrealisable cells over: "
             f"{', '.join('`' + c + '`' for c in fg['over_target_unrealisable']) or 'none'}.", "",
         "| cell | realisable | false-PASS(10) | upper | over 2.5 % |", "|---|---|---|---|---|"]
    for ck in sorted(fg["cells"], key=lambda s: tuple(float(x.split("=")[1]) for x in s.split("|"))):
        c = fg["cells"][ck]
        L.append(f"| `{ck}` | {'yes' if c['feasible'] else 'no'} | {_p(c['rate'], 3)} | {_p(c['hi'], 3)} | "
                 f"{'✗' if c['hi'] > fg['target'] else ''} |")
    return L


def write_report(out,reps=REPS, seed=SEED, results=_RESULTS, a5_ns=None, b71=False):
    rep = build_report(reps=reps, seed=seed, results=results, a5_ns=a5_ns, b71=b71)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(rep, indent=1, sort_keys=True, ensure_ascii=False) + "\n"
    rep = json.loads(text)                      # render from exactly what report.json holds
    (out / "report.json").write_text(text)
    (out / "REPORT.md").write_text(render_md(rep))
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser(prog="bench.m76_sim", description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--reps", type=int, default=REPS)
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args(argv)
    import time
    t0 = time.monotonic()
    rep = write_report(args.out, reps=args.reps, seed=args.seed, b71=True)
    print(f"m76_sim: wrote {os.path.join(args.out, 'report.json')} and REPORT.md; reps {args.reps}; "
          f"{time.monotonic() - t0:.1f} s", file=sys.stderr)
    for ax, a in rep["axes"].items():
        print(f"{ax}: final {a['final']} PASS(0) {a['final_pass0']} false-PASS(10) upper {a['final_false_pass10_hi']} "
              f"safe {a['final_safe']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
