# Judge-panel reliability instrumentation (D2)

Status: SPEC ONLY (architect, 2026-08-17). Per operator ruling, execution waits until the
B queue drains — tuning goal C against an unreliable instrument is noise. This spec exists so
the build is mechanical when its turn comes.

## Why

Goal C (daily-driver pick) is blocked on INSTRUMENTATION, not worker time: `acc` measures
only "provided tests pass"; maintainability, idiom, diff surgicality and review-acceptability
belong to a blind mixed-family judge panel over **execution-PASSING outputs only** — which is
built (`benchmark/m1/judge_extract.py` + panel driver) and has NEVER RUN, because nothing
established that its verdicts are more than noise. This spec defines the reliability gate the
panel must pass before any of its rankings are admissible, and the design that gives it a
chance to pass.

## Design principles

1. **The panel judges STYLE among correct answers, never correctness.** Inputs are
   execution-passing outputs only. A judge that flags a correctness issue is evidence of
   contamination in the item, not a verdict.
2. **Blind + mixed-family.** Judges never see model names; candidate outputs are
   whitespace-normalized and comment-stripped of self-identifying strings. The panel spans
   ≥2 model families, neither sharing a family with both candidates under comparison —
   family-preference bias is documented in the literature and unmeasurable with a
   single-family panel.
3. **Pairwise forced-choice with position counterbalancing**, not absolute scores. Absolute
   1-10 scores drift per judge; pairwise A/B with the SAME pair presented in BOTH orders
   (A,B) and (B,A) yields a position-bias measurement for free. A judge whose verdict flips
   with position on >30% of pairs is dropped.
4. **Verdict = majority over judges x orders**, tie -> "no preference". Per-item, never
   pooled prose.

## The reliability gate (run FIRST, on anchors — no candidate rankings until it passes)

Anchor set: ~30 pairs with a KNOWN quality ordering, built from the existing corpus three ways:
(a) a model's output vs the same output mechanically degraded (dead code injected, names
mangled, comments stripped) — the panel must prefer the original ≥90%; (b) same-item outputs
where one is 3x the length for the same function (verbosity anchor); (c) identical-output
pairs (A==B) — the panel must say "no preference" ≥80%, measuring forced-choice invention.

Gate metrics, all computed by the harness, thresholds pre-registered here:
- **Anchor accuracy ≥ 0.85** on (a)-pairs (same threshold family as eff-ctx).
- **Position-consistency**: per-judge flip rate ≤ 0.30; panel-level Cohen's kappa between
  the two orders ≥ 0.6.
- **Inter-judge agreement**: Krippendorff's alpha ≥ 0.5 across the panel on anchors. Below
  that, disagreement dominates signal and no candidate ranking is admissible at any n.
- **Length-bias check**: on (b)-pairs, preference for the shorter output must not exceed
  preference on (a)-pairs (a panel that just rewards brevity fails).
- **Identity check**: (c)-pairs "no preference" ≥ 0.80.

FAIL any gate -> record in the ledger, do NOT rank; iterate on prompt/panel composition and
re-run the gate. The gate run costs judge inference only (driver-side if judges are local
small models, or API) — zero candidate worker time.

## Candidate comparisons (only after the gate)

- Unit = (item, candidate-A output, candidate-B output), items from the shared
  execution-PASSING intersection (paired, same items — the compare.py discipline).
- Endpoint = paired preference rate with a cluster bootstrap CI (`stats.cluster_bootstrap`
  over items); "inconclusive" is an expected verdict; Holm across the axes family.
- Power note before anyone over-reads: at the winners' he+ intersection (~85 shared passing
  items) a 0.5 +/- 0.11 preference CI is the best case; do not promise finer.
- Every panel row carries provenance: judge model + version, prompt sha, order, and the
  candidates' row keys — same manifest machinery as every other axis.

## Open decisions for the operator (when execution is scheduled, not now)

1. Judge inventory: local-only (e.g. small fast instruct models resident on the box between
   campaign runs) vs API judges (cost, but stronger and family-independent). The gate design
   is judge-source-agnostic.
2. Whether "no preference" verdicts count toward the denominator in the preference rate
   (recommended: yes, as 0.5) — affects power arithmetic.
