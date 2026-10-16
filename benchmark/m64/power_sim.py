"""M64 spec §12 step 2: power simulation for the pre-registered accuracy claim (spec §10) BEFORE any build.

Inputs: paired run-to-run discordance of the same model on the same seeds (c144-base vs P223, both picks, both
languages, both sessions) — the realistic noise floor of a challenger arm that is truly equal to the reference.
Simulated: a challenger whose true strict-accuracy difference to opencode is delta (0, -0.05, -0.10), with paired
discordance p_d. Tests:
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


def sim_cell(rng, ref, delta, pd):
    """Challenger outcomes for one cell: symmetric flips at rate pd, plus a shift of -delta·n extra failures."""
    n = len(ref)
    ch = ref.copy()
    flip = rng.random(n) < pd
    ch[flip] = 1 - ch[flip]
    k = int(round(-delta * n))                       # delta < 0 → k extra failures among challenger passes
    if k > 0:
        idx = np.flatnonzero(ch == 1)
        if len(idx):
            ch[rng.choice(idx, size=min(k, len(idx)), replace=False)] = 0
    return ch


def run(pd, delta, rng, refs):
    """refs: {(lang, sess): ref array}. Returns (spec claim passes, pooled claim passes)."""
    diffs = {key: sim_cell(rng, ref, delta, pd) - ref for key, ref in refs.items()}
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
           "References = the c144-base strict outcomes of each pick.\n",
           "| pick | p_d | true delta | spec claim (4-cell intersection) passes | pooled 86-item claim passes |",
           "|---|---|---|---|---|"]
    for m in (P1, P2):
        refs = {(lang, s): np.array([v for _, v in sorted(load(m, lang, "c144base", s).items())], dtype=float)
                for lang in LANGS for s in SESS}
        for pd in sorted({round(rate, 3), 0.05, 0.10}):
            for delta in (0.0, -0.05, -0.10):
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
