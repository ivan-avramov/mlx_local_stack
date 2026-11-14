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


def build_report(reps=REPS, seed=SEED, results=_RESULTS, a5_ns=None):
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
    return _round(dict(header=header, data=data, axes=axes))


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
    L.append("")
    return "\n".join(L)


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


def write_report(out,reps=REPS, seed=SEED, results=_RESULTS, a5_ns=None):
    rep = build_report(reps=reps, seed=seed, results=results, a5_ns=a5_ns)
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
    rep = write_report(args.out, reps=args.reps, seed=args.seed)
    print(f"m76_sim: wrote {os.path.join(args.out, 'report.json')} and REPORT.md; reps {args.reps}; "
          f"{time.monotonic() - t0:.1f} s", file=sys.stderr)
    for ax, a in rep["axes"].items():
        print(f"{ax}: final {a['final']} PASS(0) {a['final_pass0']} false-PASS(10) upper {a['final_false_pass10_hi']} "
              f"safe {a['final_safe']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
