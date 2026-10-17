"""M64 spec §12 step 2: power simulation for the pre-registered accuracy claim (spec §10) BEFORE any build.

Inputs: paired run-to-run discordance of the same model on the same seeds (c144-base vs P223, both picks, both
languages, both sessions) — the realistic noise floor of a challenger arm that is truly equal to the reference.
Simulated: a challenger whose true strict-accuracy difference to opencode is delta (0, -0.05, -0.10), with paired
discordance p_d; pairs come from a feasible joint table (P357) so E[delta] equals the true delta. Tests:
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
RES = REPO / "benchmark/results"
P1, P2 = "Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed", "Qwen3.8-27B-mlx-uniform-4bit"
LANGS, SESS = ("python", "go"), ("s1", "s2")
INVALID = {"go/counter"}
MARGIN, ALPHA, B, SIMS = 0.05, 0.05, 2000, 400


def strict(r):
    return int(bool(r.get("passed")) and r.get("nonconv_kind") is None)


def load(model, lang, tag, sess):
    f = RES / model / f"opencode_v2_{lang}.{tag}.{sess}.jsonl"
    return {r["id"]: strict(r) for r in map(json.loads, f.read_text().splitlines()) if r["id"] not in INVALID}


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


def joint_table(r, pd, delta):
    """Joint (reference, challenger) outcome probabilities with reference accuracy r, discordance pd and true
    delta = challenger - reference: P(D=+1) = (pd+delta)/2, P(D=-1) = (pd-delta)/2. Infeasible → ValueError."""
    up, down = (pd + delta) / 2, (pd - delta) / 2
    if not (0 <= r <= 1 and 0 <= pd <= 1 and 0 <= r + delta <= 1):
        raise ValueError(f"marginal accuracy outside [0,1]: r={r}, delta={delta}, pd={pd}")
    if abs(delta) > pd + 1e-12:
        raise ValueError(f"|delta|={abs(delta)} exceeds discordance pd={pd}")
    if up > 1 - r + 1e-12 or down > r + 1e-12:
        raise ValueError(f"no joint table: P(D=+1)={up:.4f} vs 1-r={1 - r:.4f}, P(D=-1)={down:.4f} vs r={r:.4f}")
    up, down = min(up, 1 - r), min(down, r)
    return {"11": r - down, "10": down, "01": up, "00": 1 - r - up}


def feasible_ref(r, pd, delta):
    """Observed reference accuracy r clamped into the window where a joint table exists (a reference at 100 %
    cannot have symmetric discordance). Least shrinkage; r is returned unchanged when already feasible."""
    return min(max(r, (pd - delta) / 2), 1 - (pd + delta) / 2)


def sim_pairs(rng, n, r, delta, pd):
    """n paired (reference, challenger) outcomes drawn iid from joint_table(r, pd, delta)."""
    t = joint_table(r, pd, delta)
    cell = rng.choice(4, size=n, p=[t["11"], t["10"], t["01"], t["00"]])
    return (cell < 2).astype(float), ((cell == 0) | (cell == 2)).astype(float)


def run(pd, delta, rng, refs):
    """refs: {(lang, sess): observed reference array; only its length and mean are used}. Returns (spec claim passes, pooled claim passes)."""
    diffs = {}
    for key, ref in refs.items():
        r, ch = sim_pairs(rng, len(ref), feasible_ref(ref.mean(), pd, delta), delta, pd)
        diffs[key] = ch - r
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


def main():
    rate, disc, tot, cells = observed_discordance()
    rng = np.random.default_rng(64)
    out = ["# M64 power simulation (spec §12 step 2)\n",
           f"Observed run-to-run paired discordance (same model, same seeds; c144-base vs P223): {disc}/{tot} = "
           f"{rate:.3f}. Margin ±{MARGIN}, alpha {ALPHA}, bootstrap B = {B}, {SIMS} simulated chains per scenario. "
           "Pair outcomes are drawn from a feasible joint table (P(D=+1) = (p_d+delta)/2, P(D=-1) = (p_d-delta)/2; E[delta] = true "
           "delta); each cell's reference accuracy is its observed c144-base strict rate, clamped to the feasible window "
           "(a 100 % reference becomes 1 - p_d/2 at delta = 0). Extra p_d rows: .182 (M55 same-model s1 vs s2, 24/132) and "
           ".303 (between picks, 40/132) from the P356 review.\n",
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
    out += ["", "Rows at delta = 0 are POWER (want ≥ 0.80); rows at delta = −0.05 are the type-I error at the margin "
            "(want ≤ alpha); delta = −0.10 should almost never pass.", "",
            "Per-cell inputs (pick, language, session, discordant, n, c144-base strict rate):"]
    out += [f"- {m} {lang} {s}: {d}/{n}, ref {acc:.3f}" for m, lang, s, d, n, acc in cells]
    Path(__file__).with_name("POWER_SIM.md").write_text("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    sys.exit(main())
