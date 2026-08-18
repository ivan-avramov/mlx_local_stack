# H1 — the reference-model harness smoke (claude-haiku-4-5), design

**Status: Tier 1 RUNNING 2026-08-18. Operator-approved ("let's run T1 and we'll decide after
how to proceed").** Positioning ruled by the operator: a HARNESS SMOKE TEST, not a candidate —
B/C are local-model slots and a cloud model can never fill them.

## Why a reference model, and why small n is enough

The three validation questions need DIFFERENT kinds of evidence, mostly not large n:

1. **Is the harness mechanically correct?** Known-answer probes per SEAM. Statistical power is
   only expensive when estimating an unknown; a smoke checks outcomes known in advance. On items
   where the reference model's expected pass rate is ~99%, 5/5 says little (expected) but ONE
   unexpected failure is a ~100:1 likelihood-ratio signal of a harness bug (prompt assembly,
   extraction, grading). A reference model removes the confound that makes local-model failures
   ambiguous (bug vs weak model) — it mechanizes the "suspect our harness first" rule.
2. **Are we measuring the right things?** ORDER ANCHORS: does the instrument rank a model of
   known public standing where expected vs the local field? Order checks on LARGE gaps resolve
   at moderate n (n=40 ≈ ±20pp MDE — coarse is fine, the anchor question is coarse). The other
   half — agreement with the operator's daily-driver experience — cannot be outsourced to any
   reference model.
3. **Are we evaluating/aggregating correctly for B/C?** Mostly NOT the reference model's job
   (guard-parity tests + adversarial verification own it). What it adds: a metric-sanity
   fixture — a well-behaved fast-converging model must produce boring numbers (conv ~100%,
   ~zero degeneracy/runaway tax); weird numbers on a boring model = metric-pipeline bug.

## Mechanics (all driver-side, zero worker time, no dollars — plan-usage tokens only)

- Prompts built by the REAL harness path (`benchmarks.build_messages`, `depth.wrap_messages`),
  written to `$STACK_WORKDIR/scratch/h1_t1/prompt_*.txt`.
- claude-haiku-4-5 subagents answer each item INDEPENDENTLY, writing `answer_*.txt`.
- Rows assembled under an ISOLATED `MLX_BENCH_RESULTS` root
  (`$STACK_WORKDIR/scratch/h1_results/ref-claude-haiku-4-5/`), `runtime.client:
  claude-subagent` in the manifest so `compare` mechanically refuses pooling with local rows.
  NEVER in the repo results tree; published only as a clearly-marked reference table.
- Grading via the real graders (docker evalplus for coding; local for reasoning/ifeval).
- Item easiness prior = items BOTH winners pass (from evalplus per-problem artifacts +
  in-memory regrades).

## Tiers

- **T1 — known-answer seam smoke (RUNNING).** 5 easy items × {humanevalplus, mbppplus,
  math500, ifeval} + 3 humanevalplus items depth-wrapped at 12K (exercises D9). Expect ≈100%.
  PLUS free negative controls (no model calls): deliberately-wrong solutions, an
  empty-content row, an error-stub row — the graders must FAIL these (a grader that never
  fails anything also "passes" the positive smoke). Metric-sanity assertions over the batch.
  ~25 subagent calls ≈ 1.3M plan tokens.
- **T2 — order anchor (DECIDE AFTER T1).** n=40 humanevalplus on seeded items the winners
  already cover; one coarse question — is the ordering vs the local field sane? ~2M tokens.
- **T3 — depth-axis anchor (gate before M12).** n=10 at d64k: claude-haiku-4-5 holds 200K
  context comfortably, so if the D9 axis shows IT collapsing at 64K depth, the axis
  construction is suspect, not the models. ~0.7M tokens. Run BEFORE M12 spends worker hours.

## Validation criteria

T1 passes iff: every positive item passes its real grader (any miss → named-seam
investigation before anything else runs); every negative control fails; metric vector sane
(conv 100%, degeneracy 0, errors counted per O31). Findings recorded in the lab notebook;
verdicts in PLAN H1 row.
