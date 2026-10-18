"""M64 spec §12 step 2: power simulation for the pre-registered accuracy claim (spec §10) BEFORE any build.

Inputs: paired run-to-run discordance of the same model on the same seeds (c144-base vs P223, both picks, both
languages, both sessions) — the realistic noise floor of a challenger arm that is truly equal to the reference.
Simulated: a challenger whose true strict-accuracy difference to opencode is delta (0, -0.05, -0.10), with paired
discordance p_d; each pair difference is sampled directly in {-1, 0, +1} with probabilities ((p_d-delta)/2,
1-p_d, (p_d+delta)/2) (P357), so E[delta] equals the true delta. Tests:
  (a) the spec's claim — cell TOST ±5 pp by an item bootstrap (shift method; a degenerate bootstrap → p = 1) in each
      of the 4 cells (2 sessions × 2 languages), claim p = max cell p (intersection-union);
  (b) a pooled alternative — one TOST over all 86 item-sessions of a pick (two-stage bootstrap: sessions, then items).
Reports P(claim p < alpha) per scenario: power at delta = 0, type-I error at delta = -0.05 (boundary).
Usage: power_sim.py (writes POWER_SIM.md beside itself)."""
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "benchmark"))
from bench import chain_rows  # noqa: E402
RES = REPO / "benchmark/results"
P1, P2 = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "Qwen3.8-27B-mlx-uniform-4bit"
LANGS, SESS = ("python", "go"), ("s1", "s2")
INVALID = {"go/counter"}
MARGIN, ALPHA, B, SIMS = 0.05, 0.05, 2000, 400


def strict(r):
    return int(bool(r.get("passed")) and r.get("nonconv_kind") is None)


def load(model, lang, tag, sess):
    rows = chain_rows.read_rows(chain_rows.stored_path(RES / model, lang, tag, sess))      # P371 R7
    return {r["id"]: strict(r) for r in rows if r["id"] not in INVALID}


def observed_discordance():
    disc = tot = 0
    cells = []
    for m in (P1, P2):
        for lang in LANGS:
            for s in SESS:
                a, b = load(m, lang, "c144base", s), load(m, lang, "p223", s)
                ids = sorted(set(a) & set(b))
                d = sum(a[i] != b[i] for i in ids)
                disc += d
                tot += len(ids)
                cells.append((m, lang, s, d, len(ids), sum(a[i] for i in ids) / len(ids)))
    return disc / tot, disc, tot, cells


def p_tost(est, reps):
    """Shift-method TOST p (spec §10); degenerate bootstrap → 1."""
    if np.std(reps) == 0:
        return 1.0
    lo = (1 + np.sum(reps - est >= est + MARGIN)) / (len(reps) + 1)
    hi = (1 + np.sum(est - reps >= MARGIN - est)) / (len(reps) + 1)
    return max(lo, hi)


def sim_diffs(rng, n, delta, pd):
    """n paired differences D = challenger - reference in {-1, 0, +1}, iid with P(D=-1) = (pd-delta)/2,
    P(D=0) = 1-pd, P(D=+1) = (pd+delta)/2, so E[D] = delta. The reference accuracy does not enter the statistic
    (P357 round 2). |delta| > pd is infeasible → ValueError."""
    if not (0 <= pd <= 1) or abs(delta) > pd + 1e-12:
        raise ValueError(f"infeasible: |delta|={abs(delta)} exceeds discordance pd={pd}")
    return rng.choice([-1.0, 0.0, 1.0], size=n, p=[(pd - delta) / 2, 1 - pd, (pd + delta) / 2])


def gen_cells(rng, refs, delta, pd):
    """Per-cell difference arrays (exact cell sizes from the observed references)."""
    return {key: sim_diffs(rng, len(ref), delta, pd) for key, ref in refs.items()}


def run(pd, delta, rng, refs, capture=None):
    """refs: {(lang, sess): observed reference array; only its length is used}. Returns (spec claim passes,
    pooled claim passes). capture (dict) receives the generated per-cell differences (test seam)."""
    diffs = gen_cells(rng, refs, delta, pd)
    if capture is not None:
        capture.update(diffs)
    cell_p = []
    for d in diffs.values():
        est = d.mean()
        idx = rng.integers(0, len(d), size=(B, len(d)))
        cell_p.append(p_tost(est, d[idx].mean(axis=1)))
    spec_pass = max(cell_p) < ALPHA
    # pooled: two-stage bootstrap over sessions, then items within the resampled sessions (languages kept)
    sess_keys = [[k for k in diffs if k[1] == s] for s in SESS]
    allv = np.concatenate(list(diffs.values()))
    est = allv.mean()
    reps = np.empty(B)
    for b in range(B):
        parts = []
        for si in rng.integers(0, len(SESS), size=len(SESS)):
            for k in sess_keys[si]:
                d = diffs[k]
                parts.append(d[rng.integers(0, len(d), size=len(d))])
        reps[b] = np.concatenate(parts).mean()
    return spec_pass, p_tost(est, reps) < ALPHA


def main(out_path=None):
    rate, disc, tot, cells = observed_discordance()
    rng = np.random.default_rng(64)
    out = ["# M64 power simulation (spec §12 step 2)\n",
           f"Observed run-to-run paired discordance (same model, same seeds; c144-base vs P223): {disc}/{tot} = "
           f"{rate:.3f}. Margin ±{MARGIN}, alpha {ALPHA}, bootstrap B = {B}, {SIMS} simulated chains per scenario. "
           "Per-cell paired differences are drawn directly: P(D=+1) = (p_d+delta)/2, P(D=-1) = (p_d-delta)/2, P(D=0) = "
           "1-p_d (E[delta] = true delta; reference accuracy is irrelevant to the statistic); cell sizes are the observed "
           "ones. Extra p_d rows: .182 (M55 same-model s1 vs s2, 24/132) and .303 (between picks, 40/132) from the P356 "
           "review. Scenarios with |delta| > p_d are infeasible and not simulated.\n",
           "| pick | p_d | true delta | spec claim (4-cell intersection) passes | pooled 86-item claim passes |",
           "|---|---|---|---|---|"]
    for m in (P1, P2):
        refs = {(lang, s): np.array([v for _, v in sorted(load(m, lang, "c144base", s).items())], dtype=float)
                for lang in LANGS for s in SESS}
        for pd in sorted({round(rate, 3), 0.05, 0.10, 0.182, 0.303}):
            for delta in (0.0, -0.05, -0.10):
                if abs(delta) > pd:                      # infeasible: discordance cannot carry the shift
                    out.append(f"| {m} | {pd:.3f} | {delta:+.2f} | infeasible (delta beyond p_d) | infeasible |")
                    continue
                res = [run(pd, delta, rng, refs) for _ in range(SIMS)]
                a = sum(r[0] for r in res) / SIMS
                b = sum(r[1] for r in res) / SIMS
                out.append(f"| {m} | {pd:.3f} | {delta:+.2f} | {a:.3f} | {b:.3f} |")
    out += ["", "Rows at delta = 0 are POWER (want ≥ 0.80); rows at delta = −0.05 are the false-pass rate at the margin "
            "(want ≤ alpha); delta = −0.10 should almost never pass. Monte Carlo uncertainty: each entry is a proportion "
            f"of {SIMS} chains (SE ≤ {0.5 / SIMS ** 0.5:.3f}); an entry of 0.000 means 0/{SIMS}, one-sided 95 % upper "
            f"bound {1 - 0.05 ** (1 / SIMS):.4f}.", "",
            "**The pooled rule is INVALID** (P358): it fails calibration at the margin — at p_d = |delta| = .05 the "
            "false-pass rate is ≈ 0.178 = P(K ∈ {1, 2}) for K ~ Binomial(86, .05) (exact; the shift bootstrap passes "
            "when 1 or 2 of 86 pairs are discordant), far above alpha. Its power rows are therefore not evidence for "
            "a usable claim. The 4-cell rule's 0.000 is bounded by discreteness (cells of 21–22 cannot bound ±5 pp).",
            "",
            "Owed (not built): a session-level random-effect / correlation sensitivity — cells here are generated "
            "independently, so shared loaded-instance effects are not simulated.", "",
            "Per-cell inputs (pick, language, session, discordant, n, c144-base strict rate):"]
    out += [f"- {m} {lang} {s}: {d}/{n}, ref {acc:.3f}" for m, lang, s, d, n, acc in cells]
    (Path(out_path) if out_path else Path(__file__).with_name("POWER_SIM.md")).write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    sys.exit(main())
