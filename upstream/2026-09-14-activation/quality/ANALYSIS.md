# C84 offline paired analysis

`analyze.py` is separate from the sealed generation/grading instruments. Run only after both models in both phases have20 finalized requests and completed canonical mechanical grades. It emits no prefix report and refuses missing, partial or changed evidence. No model, network, container or judge calls occur; the final audit recomputes canonical math equivalence locally.

```sh
PYTHONPATH=$STACK_REPO/benchmark \
TMPDIR=$STACK_WORKDIR/upstream/2026-09-14-activation/quality/tmp \
PYTHONDONTWRITEBYTECODE=1 \
$STACK_REPO/.venv-bench/bin/python -B \
$STACK_WORKDIR/upstream/2026-09-14-activation/quality/analyze.py \
  --before-sha 5716db4fc30e0ac458fa78b1aa8b6b006a0087f4bcf40e502f75a59c4daf3c11 \
  --after-sha "$C84_AFTER_PIN"
```

Outputs are exclusive-create `analysis/comparison.json` and `analysis/paired-prose-review.md`. Repeat the same command with `--check` for deterministic read-only verification. Do not edit the generated paired review document if future `--check` is required; record human/source judgements separately and cite the paired item.

The fixed treatment is MLX-VLM e3bffd9a25510d5ed2d27079ff0eb76f749c544f →5b43e5d934a423303b731d6847120a945a1c6a69, with unchanged Serve, all runtime pins, actual registry, deployed per-model cache modes, canonical builders, requests, item/sample seeds, tokenization and resolved81920 budget. A subsequent different repair needs a revised declared analysis treatment; do not relabel a source state to pass.

Reports are per-model/per-axis only: canonical ordinary/strict outcomes, convergence, exact exclusive solves and shared failures, output/reasoning equality, wall/token/decode ratios. Estimators match C82: paired two-stage item bootstrap, seed84,10000 replicates; deltas after−before and ratios after/before. Decode is a ratio of arithmetic mean per-request rates, not aggregate tokens divided by time. Missing metrics remain unavailable over the full selected cohort; the helper never silently intersects to an easier subset. Nominal intervals are exploratory and not familywise adjusted. Five pairs do not establish ±5pp equivalence; the raw helper's `equivalent` label is explicitly nonoperative.

Prose gets paired bodies and a human/source review prompt; its quality score stays null until separately reviewed. Hash equality is integrity/equality evidence only. Short-request memory telemetry is not capacity evidence; the root's matched capacity probes remain separate. No cross-model pooling, combined quality ranking, automatic certification, runtime change, or push is performed.
