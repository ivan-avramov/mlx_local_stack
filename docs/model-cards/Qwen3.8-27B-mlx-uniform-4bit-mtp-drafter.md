---
license: apache-2.0
base_model: caslca/Qwen3.8-27B-mlx-uniform-4bit
tags:
- mlx
- speculative-decoding
- mtp
library_name: mlx
---
# Qwen3.8-27B-mlx-uniform-4bit MTP drafter

A native multi-token-prediction (MTP) sidecar for
[Qwen3.8-27B-mlx-uniform-4bit](https://huggingface.co/caslca/Qwen3.8-27B-mlx-uniform-4bit),
which itself ships with [unsloth/Qwen3.8-27B](https://huggingface.co/unsloth/Qwen3.8-27B). <!-- allow-shorthand -->
This is a predictor, not a standalone language model.

## Status

**CERTIFIED (M6d, 2026-08-30) — serving-only, at xhigh reasoning effort.** The trunk's
reasoning-effort default later moved to medium (certified 2026-09-09); a 2026-09-09 speed
screen at medium (below) confirms the predictor still engages correctly there, but the paired
quality certification below was run at xhigh and has not been repeated at medium.

## Provenance

Standalone, servable extraction of the native MTP sidecar that ships inside the trunk
checkpoint (`optiq/mtp.safetensors`, 29 tensors, outside the weight index, inert at normal <!-- allow-shorthand -->
load), repackaged as a loadable drafter directory (`model_type: qwen3_5_mtp`, 1-layer head,
prequantized int4 group-size-64 affine, ~300 MB + tokenizer). Loaded as an external drafter it
speculates k=2 tokens per round against the trunk.

The trunk is bit-identical to
[mlx-community/Qwen3.8-27B-4bit](https://huggingface.co/mlx-community/Qwen3.8-27B-4bit)
(2179/2180 tensors md5-identical; the sole difference is the restored vision tower), so this
drafter pairs with either copy of the trunk.

## Measured evidence: xhigh quality certification (M6d, 2026-08-30)

Paired ON/OFF quality OFAT, HumanEvalPlus **n=164** (full corpus, seeded paired draws), deployed
config (turboquant 4-bit KV, temperature 0.6, xhigh reasoning effort, thinking ON, 81,920-token
thinking budget), arms separated by server restarts with draft state verified at the worker
command line both ways, EvalPlus docker grading, paired two-stage cluster bootstrap + TOST:

| metric | draft ON | draft OFF |
|---|---|---|
| accuracy (pass@1, plus tests) | 94.5% | 94.5% |
| accuracy, strict @81,920 budget | 93.9% | 92.7% |
| convergence | 99% (2 budget-length) | 98% (4 budget-length) |
| decode / corpus wall | 38.7 tok/s / 5.16 h | 24.0 tok/s / 10.52 h |

Delta **0.0pp**, discordants 3:3, 95% CI **[−3.0, +3.0pp] → TOST ±5pp verdict: EQUIVALENT**,
measured discordance p_d = 0.037 (powered at n_for=115 ≤ 164). Engagement 164/164 rows, mean
acceptance **0.674** (k=2 → 2.35 emitted tokens/round). Decode **1.60× paired mean** (median
1.58×, range 1.37–2.31×). An earlier n=63 stage was inconclusive (CI ±6.3pp against the ±5pp
gate) and was extended to the full corpus, not certified at n=63.

Earlier engaged-head speed probe (2026-08-23, two fixed coding prompts, admission gate only):
lru_cache 50.1 vs 31.6 tok/s (1.58×, acceptance 75.8%); token_bucket 45.8 vs 31.4 tok/s (1.46×,
acceptance 68.3%) — this cleared the ≥1.3× bar that admitted the n=164 OFAT above; it is not
itself a quality certification.

## Medium-effort three-task speed screen (2026-09-09) — not a quality certification

Known-positive instrument control after the trunk's certified default moved to medium
reasoning effort: 6 responses across 3 tasks, all converged, no errors. Median decode
28.713 → 51.245 tok/s, ratio **1.785×**; accepted **7,387/8,712 draft tokens (84.8%)**. This
validates that the serving instrument and the predictor still engage correctly at medium
effort — **it is not a powered quality result and is not evidence that speed improved over the
xhigh certification above**; no paired-quality OFAT at medium has been run for this drafter.

**Serving-only lever**: benchmark measurements for the trunk always run predictor-OFF
(speculative decoding is not bit-lossless on bf16 serving stacks); the xhigh certification
means quality is statistically equivalent within ±5pp on that workload, not that outputs are
identical. Re-certify on your own workload before production use, and treat the medium-effort
number above as a speed signal only.

## Usage

Serve with an MLX stack that supports external MTP drafters (our forks: `draft_kind: mtp` +
`draft_model: caslca/Qwen3.8-27B-mlx-uniform-4bit-mtp-drafter`). **Pairing rule**: use this
drafter only with the exact base checkpoint it was extracted from
(`caslca/Qwen3.8-27B-mlx-uniform-4bit`) or its bit-identical twin
(`mlx-community/Qwen3.8-27B-4bit`) — head/trunk acceptance is measured for this pairing only and
does not transfer to a different fine-tune or quantization of the base model. Methodology and
full campaign results:
[https://github.com/ivan-avramov/mlx_local_stack](https://github.com/ivan-avramov/mlx_local_stack).

Sibling certified drafters:
[caslca/Qwen3.6-27B-Opus-Distill-OptiQ-4bit-mtp-drafter](https://huggingface.co/caslca/Qwen3.6-27B-Opus-Distill-OptiQ-4bit-mtp-drafter)
(same `qwen3_5` head design, acceptance 0.923, 2.06×),
[caslca/Ornith-1.0-35B-mlx-uniform-4bit-mtp-drafter](https://huggingface.co/caslca/Ornith-1.0-35B-mlx-uniform-4bit-mtp-drafter)
(transplanted MoE head, acceptance 0.778, 1.56×),
[caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter](https://huggingface.co/caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter)
(repaired sidecar, acceptance 0.845, 1.836×).

<!-- ============================================================================
NOT PART OF THE CARD — SOURCES (strip before publishing to Hugging Face)
============================================================================

IMPORTANT DISCREPANCY WITH THE TASK BRIEF: the coordinator's brief for this card stated the live
`caslca/Qwen3.8-27B-mlx-uniform-4bit-mtp-drafter` README "still says PROBE-ONLY — UNCERTIFIED,
1.46x / 68.3%". This session fetched the live README fresh (force_download, pinned to the repo's
current HEAD sha `d53e8e6ab20259b9705d87c00ec98cb2d3e9a789`, `lastModified` 2026-09-01T01:16:04Z,
verified via HfApi.model_info this session) and it ALREADY carries a full
"## Certified (M6d, 2026-08-30) — serving-only" section with the exact n=164 table reproduced
above; "1.46x" / "68.3%" appear only inside that live card's own "History — engaged-head speed
probe (2026-08-23...)" subsection as a labelled pre-certification data point, not as the card's
current headline status. This card's content (provenance + xhigh certification table + usage +
sibling list) is therefore substantially a faithful copy of the ALREADY-CURRENT live card, not a
correction of a stale one. The one genuinely new content this draft adds beyond the live card is
the 2026-09-09 medium-effort speed-screen section (F1), which the live card does not yet carry.

Provenance / trunk identity / xhigh certification table / speed-probe history / usage / sibling
list: live HF README for caslca/Qwen3.8-27B-mlx-uniform-4bit-mtp-drafter, fetched this session
(force_download, sha d53e8e6ab20259b9705d87c00ec98cb2d3e9a789), reproduced near-verbatim.
Cross-checked against main_models.yaml:330-337 (registry comment block: n=164 EQUIVALENT, 1.60x,
acceptance 0.674, fork ab5708a5) and docs/campaign-results.md:1136-1157 ("M6d CERTIFIED" section,
2026-08-30, same table/CI/p_d/acceptance/decode numbers) and docs/PLAN.md:103 ("FIRST
CERTIFICATION LANDED 2026-08-30 ... n=164 EQUIVALENT, 1.60x, acceptance 0.674, `76dad59`").

Medium-effort three-task speed screen (ratio 1.785x, acceptance 84.8% = 7387/8712, 6 responses
over 3 tasks, median decode 28.713->51.245 tok/s): docs/campaign-results.md:227 ("M36
known-positive control passed", 2026-09-09) — the SAME source used for the F1 fix on the trunk's
own card; this is the only write-up found for a medium-effort probe of this drafter. The
"1.644x, acceptance 0.848" figure that appears only as a main_models.yaml:348 registry comment
was deliberately NOT reproduced here (no dedicated paired-quality write-up was found for it,
matching the F1 finding on the trunk card).

No benchmark/results/ upload manifest (sha256/revision record) exists for this drafter, unlike
the Fable-Distill sibling's benchmark/results/mtp_upload_manifest.json — checked via `find` and <!-- allow-shorthand -->
`grep` this session; revision facts above come only from the live HF card + HfApi.model_info.

Sibling drafter acceptance/speedup figures (Qwen3.6-27B-Opus-Distill-OptiQ-4bit-mtp-drafter
0.923/2.06x; Ornith-1.0-35B-mlx-uniform-4bit-mtp-drafter 0.778/1.56x;
Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter 0.845/1.836x): live HF README for this
drafter (sibling list, same fetch as above); the Fable-Distill sibling's 0.845/1.836x <!-- allow-shorthand -->
cross-checked against docs/model-cards/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter.md
("repaired sidecar 1.836x median decode ... draft acceptance 3843/4548 (84.5%)").

Style template: docs/model-cards/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter.md
(section order: title/one-line description, Status, provenance-equivalent section, Measured
evidence, closing caveat).
============================================================================ -->
