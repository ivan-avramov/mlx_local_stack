---
license: apache-2.0
base_model: unsloth/Qwen3.8-27B  # allow-shorthand
library_name: mlx
tags:
- mlx
- unsloth
- qwen3_5
pipeline_tag: image-text-to-text
---
# Qwen3.8-27B-mlx-uniform-4bit

> **Identity note (2026-08-26): the language trunk of this model is bit-identical to
> [mlx-community/Qwen3.8-27B-4bit](https://huggingface.co/mlx-community/Qwen3.8-27B-4bit).**
> A full-tensor md5 sweep over both repos shows 2179 of 2180 tensors identical; the single
> differing tensor is `vision_tower.patch_embed.proj.weight`, because this copy carries the
> restored bf16 vision tower while the mlx-community upload keeps the original. MLX uniform
> 4-bit (group size 64) quantization is deterministic, so two independent conversions of the
> same bf16 base produce the same weights. Text results measured against either repo apply to
> both; prefer this copy if you want the vision path.

**27B parameters, vision tower included** (restored 2026-08-23, see below) — note: Hugging
Face's size badge undercounts packed 4-bit MLX weights (it counts the packed uint32 tensors),
so the number shown beside this repo is wrong; the figure here is the true parameter count.

MLX **uniform 4-bit** quant of [unsloth/Qwen3.8-27B](https://huggingface.co/unsloth/Qwen3.8-27B). <!-- allow-shorthand -->

| measured | value |
|---|---|
| effective bits/weight | **4.0** (uniform; all 498 quantized layers at 4-bit) |
| weights footprint | 15.13 GB |
| quantized-layer bit histogram | 4-bit: 498 |

## Capacity gate + retrieval ladder (256K context)

Gate metric is `mx.get_peak_memory` (the prefill spike) against a 46 GB hard gate; retrieval is
a needle-style accuracy check at each rung — both measured, not assumed.

| context | peak (server) | retrieval acc | prefill | decode |
|---|---|---|---|---|
| 160K | 32.91 GB | 1.00 | 802 s (196 tok/s) | 14.73 tok/s |
| 192K | 33.24 GB | 1.00 | 1,161 s (163 tok/s) | 13.31 tok/s |
| 224K | 33.56 GB | 1.00 | 1,539 s (143 tok/s) | 12.13 tok/s |
| 256K | 33.88 GB | 1.00 | 1,968 s ≈ 33 min (128 tok/s) | 11.08 tok/s |

**Capacity gate: PASS** (33.88 GB peak at 256K, well inside the 46 GB gate). **Retrieval
effective context: 256K** — accuracy stays 1.00 at every rung; the low, flat memory footprint <!-- allow-shorthand -->
(hybrid attention: 16 of 64 layers are full-attention) is a co-residency convenience, not a
quality edge — the cost that scales with depth is speed (below).

## Stage-1 screening and Stage-2 convergence-gated pass@1

**Stage-1** (2026-08-17, capped temperature scan then an n=15 confirmation rung): certified
operating temperature 0.6; convergence 15/15, pass@1 **1.00**, median 528 reasoning tokens
(n=15, nominal MDE ±32pp — this establishes "no dramatic problem," not a ranking).

**Stage-2**, HumanEvalPlus / MBPPPlus at the certified tune, thinking ON, budget 81,920,
predictor OFF, `acc_strict@81920` as the ranking key:

| bench | reasoning effort | n | acc | acc_strict@81920 | convergence | nominal MDE |
|---|---|---|---|---|---|---|
| HumanEvalPlus | xhigh (former default) | 164 | 94.51% | 92.68% | 97.6% (4 meanders) | ±9.8pp |
| MBPPPlus (k=3) | xhigh (former default) | 50 | 80.0% | 80.0% | 99.3% (1 meander) | ±17.7pp |
| HumanEvalPlus | **medium (certified default)** | 164 | 93.9% | **93.9%** | 100% (0 loops) | ±9.8pp |
| MBPPPlus (k=3) | **medium (certified default)** | 50 | 80.67% | **80.67%** | 100% (0 loops) | ±17.7pp |

Pooled HumanEvalPlus+MBPPPlus (n=214, stratified two-stage cluster bootstrap): medium vs xhigh
**+1.1pp CI [−1.7, +4.0], EQUIVALENT** (TOST ±5pp, MDE ±8.6pp), at token-ratio
**0.142 CI [0.10, 0.22]** on HumanEvalPlus and **0.123 CI [0.08, 0.24]** on MBPPPlus, with **0
convergence loops at medium versus 5 at xhigh across the 314 rows** (4 on
HumanEvalPlus, 1 on MBPPPlus). Medium was promoted from diagnostic reference to the certified
default on this evidence (2026-09-07/09, decision C51).

## Agentic (opencode, 22-item Python/Go sets, predictor OFF)

| language | xhigh | medium (certified) |
|---|---|---|
| Python | 20/22, 2 stalls (also 18/22 in a separate session) | 19/22, 3 stall-kills |
| Go | 16/22, 6 stalls | 16/22, 6 stall-kills |

Broader 5-language screen at xhigh (Python/Go/Rust/Java/JavaScript, n=22 each, predictor OFF):
80/110 pooled, leading 3 of 5 languages point estimates — nothing survives Holm correction at
this sample size, so this is direction, not a resolved ranking.

## Recommended sampling (certified)

| param | value |
|---|---|
| temperature | **0.6** |
| top_p / top_k / min_p | 0.95 / 20 / 0.0 |
| presence_penalty | 0.0 |
| reasoning_effort | **medium** (certified 2026-09-09) |
| max_tokens / thinking_budget | 102400 / 81920 (thinking ON) |

Serving: MLX (`mlx-lm` / `mlx-vlm`). Quantized on-device with `mlx_lm.convert` (uniform) or
`mlx_optiq` (mixed-precision KL-sensitivity recipes).

## Predictor (MTP sidecar)

This checkpoint ships a native multi-token-prediction sidecar (`optiq/mtp.safetensors`, 29 <!-- allow-shorthand -->
tensors, outside the weight index — inert at normal load). `draft_kind: mtp`, certified. Public
sidecar:
[caslca/Qwen3.8-27B-mlx-uniform-4bit-mtp-drafter](https://huggingface.co/caslca/Qwen3.8-27B-mlx-uniform-4bit-mtp-drafter).

- **Quality certification, xhigh reasoning effort** (2026-08-30): n=164 HumanEvalPlus, acc
  94.5% both arms, delta 0.0pp CI [−3.0, +3.0], TOST EQUIVALENT; acceptance 0.674 (k=2); decode
  **1.60×** paired mean (38.7 vs 24.0 tok/s).
- **Medium-effort three-task speed screen** (2026-09-09): decode ratio **1.785×**, acceptance
  **84.8% (7,387/8,712 draft tokens)** over 6 responses across 3 tasks. This is an instrument
  check confirming the serving path still engages the predictor at medium effort — it is not a
  powered quality certification at medium. The paired-quality certification above (n=164, TOST
  equivalent, acceptance 0.674, 1.60×) was run at xhigh; a medium-effort quality OFAT of the same
  size has not been published.

Measurement is always predictor-OFF; the predictor is a serving-only lever and does not change
any of the accuracy numbers above.

## Serving caveat: decode speed is architecture, not quant

Shallow decode holds at **~24–26 tok/s** across every sampled temperature and both this
family's quant recipes (median 26.0 tok/s measured here vs 23.3 tok/s on the
structurally-identical `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` and 76.2 tok/s on
`Ornith-1.0-35B-mlx-uniform-4bit`). A supervised `powermetrics` probe, run on a sibling recipe
of this family during decode, found the GPU 95% active (not dispatch-starved), so the cost is
serialized per-token kernel overhead across 64 hybrid attention/linear-attention layers —
**architecture, not quantization**. At 256K context this also shows up in prefill: **~33
minutes (1,968 s) to first token**, with decode falling to 11.1 tok/s. A full-context agentic
turn on this model pays roughly half an hour of prefill before the first output token, on top
of the per-token decode cost above.

## Vision tower restored (2026-08-23)

The original conversion was language-model-only. This revision grafts the vision tower back
from the upstream base (`unsloth` repackaging of the family release): 333 `vision_tower.*`
tensors kept **bf16** (exactly what the vision-retaining `mlx_vlm` convert produces for this
family), +0.92 GB.

**The text trunk is bit-identical to the evaluated artifact**: the trunk shards are
byte-copies (md5-verified), and a fixed-token forward pass through the language model produces
bit-identical logits pre/post graft. Every benchmark number on this card measures exactly the
weights this revision serves for text. One-image smoke passed post-graft.

## Status

B-menu rank 2 (approved, provisional trend-based ranking, 2026-09-09) and C research shortlist
(not yet a promoted C pick). Methodology and full results:
[https://github.com/ivan-avramov/mlx_local_stack](https://github.com/ivan-avramov/mlx_local_stack).

<!-- ============================================================================
NOT PART OF THE CARD — SOURCES (strip before publishing to Hugging Face)
============================================================================

Identity note / footprint / bpw / quant table: current live HF README for
caslca/Qwen3.8-27B-mlx-uniform-4bit (fetched 2026-09-11 via huggingface_hub,
cached at models--caslca--Qwen3.8-27B-mlx-uniform-4bit/snapshots/cb23081e253ee.../README.md).

Capacity gate + retrieval ladder table: benchmark/results/Qwen3.8-27B-mlx-uniform-4bit/capacity_retrieval.json
(records array, ctx 160000/192000/224000/256000; server_peak_gb, retrieval_acc, prefill_s,
prefill_tps, decode_tps fields verbatim); gate_gb 46.0, capacity_gate_pass true,
retrieval_effective_ctx 256000 (same file, top-level fields).

Stage-1 screening (n=15, t0.6, conv 15/15, pass@1 1.00, median 528 tokens, MDE ±32pp):
docs/model-ledger.md:206.

Stage-2 xhigh HumanEvalPlus (n=164, acc 94.51%, acc_strict 92.68%, conv_rate 97.56%,
4 meanders, mde 9.78pp): benchmark/results/Qwen3.8-27B-mlx-uniform-4bit/humanevalplus.m32b.score.json.
Stage-2 xhigh MBPPPlus (n=50 k=3, acc/acc_strict 80.0%, 1 meander, mde 17.72pp):
benchmark/results/Qwen3.8-27B-mlx-uniform-4bit/mbppplus.m24x.score.json.
Stage-2 medium HumanEvalPlus (n=164, acc/acc_strict 93.9%, 0 loops, mde 9.78pp):
benchmark/results/Qwen3.8-27B-mlx-uniform-4bit-MED/humanevalplus.m24.score.json.
Stage-2 medium MBPPPlus (n=50 k=3, acc/acc_strict 80.67%, 0 loops, mde 17.72pp):
benchmark/results/Qwen3.8-27B-mlx-uniform-4bit-MED/mbppplus.m24.score.json.
Pooled n=214 medium-vs-xhigh EQUIVALENT +1.1pp CI[-1.7,+4.0], MDE +-8.6pp, token-ratio intervals
0.142 CI[0.10,0.22] (hep) / 0.123 CI[0.08,0.24] (mbpp), 0 loops medium vs 5 xhigh (4 hep + 1
mbpp) across 314 rows: docs/campaign-results.md:817-823 (M24 table, hep/mbpp rows + pooled row),
docs/campaign-results.md:830 (the "4 + 1 loops at xhigh, 0 at medium across 314 rows" sentence).

Agentic opencode: xhigh Python 20/22 with 2 stalls and xhigh Go 16/22 with 6 stalls:
docs/campaign-results.md:843-844 (M32b table, the base `Qwen3.8-27B-mlx-uniform-4bit @t0.6 (B
3rd)` column). Medium Python 19/22, 3 stall-kills: docs/campaign-results.md:824 (M24 table).
Medium Go 16/22, 6 stall-kills, 2.039h: docs/campaign-results.md:230-236 (M24g table) and
README.md:25. The historical second Python session (18/22, no stall count on file):
README.md:25. 5-language pooled 80/110 table: docs/campaign-results.md:1231-1235 (M9 block,
2026-08-29).

Recommended sampling table: main_models.yaml:339-348 (generation_defaults block for
`Qwen3.8-27B-mlx-uniform-4bit`), temperature comment "CERTIFIED 2026-08-17", reasoning_effort
comment "CERTIFIED C51 2026-09-09".

Predictor: draft_kind field main_models.yaml:337-338. xhigh quality certification numbers
(n=164 EQUIVALENT, 1.60x, acceptance 0.674): main_models.yaml:330-336 comment block, corroborated
docs/PLAN.md:103 ("FIRST CERTIFICATION LANDED 2026-08-30 ... 76dad59") and
docs/campaign-results.md:1136-1157 (M6d CERTIFIED section). Medium-effort three-task speed
screen (decode ratio 1.785x, acceptance 84.8% = 7387/8712, 6 responses over 3 tasks):
docs/campaign-results.md:227 ("M36 known-positive control passed", 2026-09-09) — this is the
ONLY write-up found for the medium arm; the "1.644x, acceptance 0.848" figure in
main_models.yaml:348's comment is a separate registry note this session could not find a
dedicated paired-quality table for (checked docs/campaign-results.md and docs/PLAN.md in full;
docs/PLAN.md:102's M6c closure cites "C51/M36" as settled without reproducing numbers) — omitted
from the card body per F1, kept here for the record. Public drafter repo existence/visibility
verified live via HF API this session (caslca/Qwen3.8-27B-mlx-uniform-4bit-mtp-drafter, private:
False).

Serving caveat (shallow ~24-26 tok/s, mechanism, powermetrics probe run on
`Qwen3.8-27B-static-mixed-4bit` (a sibling recipe of this family) during decode, 33 min prefill
@256K): docs/model-ledger.md:206 (full paragraph, includes the 26.0/23.3/76.2 tok/s comparison
and the GPU-active-95% probe result, explicitly run "during a live `Qwen3.8-27B-static-mixed-4bit`
t0.4-rung decode"); prefill/decode numbers cross-checked against
benchmark/results/Qwen3.8-27B-mlx-uniform-4bit/capacity_retrieval.json (same source as the
capacity table above).

Vision tower restored section: current live HF README for caslca/Qwen3.8-27B-mlx-uniform-4bit
(same snapshot cited above), "## Vision tower restored (2026-08-23)" section, reproduced
verbatim.

Serving:/Quantized-on-device template line: same live HF README, end of its "Recommended
sampling" section.

Tags (mlx, unsloth, qwen3_5): live HF README front matter (mlx, unsloth) plus this repo's
config.json `model_type` field ("qwen3_5", `architectures: ["Qwen3_5ForConditionalGeneration"]`),
fetched via huggingface_hub this session.

Status / ranking: README.md:10 (B rank 2), README.md:25 (B evidence row), README.md:44 (C
shortlist, not ranked).
============================================================================ -->
