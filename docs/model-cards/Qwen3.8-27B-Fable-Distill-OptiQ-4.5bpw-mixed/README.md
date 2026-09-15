---
base_model: TeichAI/Qwen3.8-27B-Fable-Distill
tags:
- text-generation-inference
- transformers
- unsloth
- qwen3_5
- mlx
- optiq
license: apache-2.0
language:
- en
datasets:
- armand0e/claude-fable-5-claude-code
- armand0e/Fable-5-Chat
library_name: mlx
pipeline_tag: image-text-to-text
---
# Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed

Model-card update:2026-09-14.

## Status

First operator-approved choice for agentic coding and research/design assistance (B1/C1), at temperature 0.5, medium reasoning effort and repaired MTP ON. The current runtime uses native16 KV and idle session-cache retirement. It passed the existing 20-image vision smoke in C88 (20 PASS, 0 FAIL, 0 null), and C89 retrieval (25/25 prompts through128K) and chain-4 variable tracking (39/39 through156K). These bounded checks do not establish broad native16 quality equivalence.

## Conversion and attribution

MLX OptiQ sensitivity-mixed conversion of [TeichAI/Qwen3.8-27B-Fable-Distill](https://huggingface.co/TeichAI/Qwen3.8-27B-Fable-Distill). The conversion assigns 4/8-bit precision by KL sensitivity. The recorded M36/M40 and C84 serving manifests report4.983526659518471 effective bits/weight (about 4.98),152 eight-bit and 346 four-bit quantized modules, and 18.44 GB of text shards. This is serving-manifest accounting, not a fresh tensor-weighted precision measurement; it corrects the previous card’s unsupported4.67/150 figures. A BF16 vision sidecar is stored at `optiq/optiq_vision.safetensors`; conversion provenance is in `optiq/metadata.json` and `optiq/sensitivity.json`. The uniform conversion remains a separate sibling, [caslca/Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit](https://huggingface.co/caslca/Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit).

Packed low-bit tensor counts can understate true parameter counts in hub badges. Weight-file sizes, effective bits/weight and total MLX runtime peak are different measurements.

### M36 repaired predictor, 2026-09-10 — historical TQ4 configuration

Medium reasoning effort, temperature 0.5, fixed 102400 output cap/81920 thinking budget, paired seeds, M5 Max 64 GB. Serving sources were MLX-VLM `420c01e1` and MLX-Serve `0ccc684`. Native ARM64 EvalPlus graded the code.

| Dataset | Tasks × draws per state | OFF strict | Repaired ON strict | ON−OFF,95% paired interval |
|---|---:|---:|---:|---|
| HumanEvalPlus |50×3|92.0%|90.67%|−1.33 pp[−5.33,+2.0]|
| MBPPPlus |50×3|84.67%|85.33%|+0.67 pp[−2.0,+4.67]|
| Equal-item pooled diagnostic |100×3|88.33%|88.0%|−0.33 pp[−3.0,+2.33]|

All 600 responses converged, so ordinary and strict accuracy coincide. HumanEvalPlus alone remains inconclusive; the pooled interval supports the historical±5 pp decision without erasing that axis. Nominal MDE 17.7 pp per dataset/12.5 pp pooled; intervals are descriptive before campaign-wide multiplicity adjustment. Three-task decode screen 1.836×, acceptance 84.5%; full generation 1.123 h ON versus 2.691 h OFF, wall ratio 0.417[0.238,0.603], token ratio 0.778[0.463,1.082]. Changed output lengths and a long OFF tail contribute to wall savings; this is not pure kernel acceleration.

### M40 predictor-ON certification, 2026-09-13 — historical TQ4 configuration

These ON/OFF comparisons used the same deployed tune, matched seeds, cap 262144 and resolved thinking budget 81920. Both predictor states remain recorded; new optimization work runs in the shipped ON state. This supersedes earlier blanket statements that every benchmark always runs predictor-OFF.

| Axis and sample size | OFF | ON | Paired interpretation |
|---|---:|---:|---|
|Math500,100|97%|99%|+2 pp[0,+5]; operator PASS, raw helper inconclusive at the edge|
|Research prose, 40 pairs|—|—|OFF preference 0.40[0.29,0.53], Holm p=.099; underpowered|
|128K chain-4,3 draws|3/3|3/3|No budget hits|
|20-photo vision gate|20/20|20/20|Limited photo-description gate|

Operator-approved state is MTP ON. Per-axis limits remain: a zero-discordance empirical interval is not proof of universal equivalence; n 100 nominal MDE is 12.5 pp and n 40 is 20 pp. Vision and depth drivers verified the worker flag but did not expose per-request draft counters. Those small gates do not certify arbitrary images, OCR, complex diagrams, or full-context reasoning. The photo gate uses description followed by a ground-truth-caption self-check; it is a lenient capability screen, not a ranked vision benchmark.
The M40 evidence used TQ4 and cannot silently become broad native16 quality certification.

### C84 actual-runtime regression screen, 2026-09-14

M5 Max 64 GB, MLX/Metal 0.32.2. BEFORE was the initially merged runtime `e3bffd9a`/`f8f1df4`. AFTER combines later upstream changes, cache lifetime/logical-trim/eager-retirement repairs, and the per-model retirement option; retirement is enabled only for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`. This is not an isolated retirement/kernel effect or the original pre-merge/upstream comparison.

Five frozen seeded tasks per axis, 20 requests in each state for this model. All 20 pairs have identical visible answers, reasoning and completion-token counts; all 40 responses converge. Ordinary accuracy equals strict accuracy. No exclusive solves or new nonconvergence were observed.

| Axis | AFTER score | Task-time AFTER/BEFORE[95% interval] | Mean per-request decode ratio[95% interval] |
|---|---:|---:|---:|
|math500|5/5|1.022[1.007,1.031]|0.986[0.974,0.996]|
|humanevalplus|4/5|1.012[1.008,1.022]|0.995[0.977,1.016]|
|mbppplus|5/5|1.025[1.014,1.036]|0.977[0.962,0.991]|
|cjudge|5 reviewed ties|1.018[1.008,1.031]|0.983[0.970,0.994]|

Intervals use 10000 paired two-stage task-bootstrap resamples, seed 84; they are nominal exploratory intervals, not multiplicity-adjusted or repeated-session uncertainty. Five items per axis have nominal MDE 56 pp; empirical quality intervals[0,0] with zero discordance do not establish±5 pp equivalence. The prose review was nonblinded, one reviewer, and found shared factual/methodological weaknesses; matching answers are not proof of correctness. This bounded screen does not rerank models or replace broad native16 depth/vision certification.

Final runtime smoke covers arithmetic, Python, JSON, native tool continuation and one fixed image, five cases/six requests. It passed for both current picks. Only `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` received the additional fresh tool-pair and three-turn prefix-reuse checks.

The shared HumanEval/141 failure is retained under official EvalPlus grading; it includes the documented ASCII-versus-Unicode prompt/reference edge case. Total short-task time 668.6→680.8 s: a small observed slowdown, not speed neutrality.

#### Full-context native16 execution, same final runtime

| Metric, 261449 actual prompt tokens | BEFORE | AFTER |
|---|---:|---:|
|MLX prefill peak|47.138620 GB|47.155397 GB|
|Prefill|1099.88 s|1165.33 s|
|Decode|11.9545tok/s|11.5061tok/s|

Both produced 170 completion tokens, identical answers/reasoning, all five retrieval codes and no prefix reuse; MTP 67 rounds/134 proposed/104 accepted. One observation per state: peak+0.036%, prefill+5.95%, decode−3.75%; repeatability and isolated causes are unresolved. Peak is `mx.get_peak_memory`, including prefill scratch, not weight size or RSS. Rough 48 GB is guidance, not a strict 46/48 GB rejection rule. The five-code co-score is not general 256K reasoning quality. Idle cache retirement resolves the observed tool-continuation OOM while retaining full active preallocation.

Historical TQ4 M41 measured retrieval through 128K and chain-4 reasoning through 156K. Those ladders are not native16 measurements. C76 corrected the earlier 42-draw summaries to the verified 39 stored reasoning draws; the underlying results are unchanged.

## MTP companion

Use [caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter](https://huggingface.co/caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter), captured revision `74bb2bc1feb60dbb8302bc8e6021d0be01f8f18d`, with `draft_kind: mtp`. This is the repaired head; the original bundled head is not the recommendation.

### C88 shipped-configuration vision qualification, 2026-09-14

**20 PASS, 0 FAIL, 0 null** on the existing 20-image smoke. Each image receives two turns: describe the image, then receive its human ground-truth captions and return the model's own PASS/FAIL verdict. All 40 turns converged below the resolved 81920-token thinking budget, with MTP engaged and no runtime errors.

This used the deployed native16 configuration unchanged: repaired MTP ON, temperature 0.5, medium effort, context/preallocation 262144, prefill 512 and idle cache retirement enabled, on the final MLX-VLM522671c4 / MLX-Serveb632280 runtime with MLX/Metal0.32.2. No TQ4 comparison, manual extraction-quality grading or external judge was used. This qualifies the existing image smoke; the separate C89 depth results follow below.

See the [C88 evidence](evaluation/C88-evidence-2026-09-14.json) and [published canonical results](https://github.com/ivan-avramov/mlx_local_stack/blob/2f0c7ad2a9a790a5041e84a78dd5124c74a61476/benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/vision_gate.c88-shipped-20260914.summary.json).

### C89 shipped-configuration depth qualification, 2026-09-14

The target with this repaired MTP companion passed both separate depth axes at the shipped native16 configuration:

| Axis | Scored prompts | Result | Largest nominal prompt rung |
|---|---:|---|---:|
| Five-code retrieval | 25 | 25/25 fully correct; 125/125 codes | 128,000 tokens |
| Chain-4 variable tracking | 39 | 39/39 correct | 156,000 tokens |

Every rung has ordinary and strict accuracy 1.0. All 64 responses converged within the full resolved 81,920-token thinking budget, reported positive MTP activity and zero cached prefix tokens, with no budget hits or runtime errors. The largest actual prompt was 155,628 tokens. Five-prompt pilots were included in these counts; exactly 66 actual HTTP calls include two calibrations. The original interrupted calibration was retained and adopted without replay.

Settings were unchanged: native16 `kv_bits: 0` (the declared TurboQuant scheme is inactive), repaired MTP ON, temperature 0.5, medium effort, context and active preallocation 262,144, prefill step 512, idle cache retirement enabled, two retained sessions and APC absent. Runtime: MLX-VLM `522671c4`, MLX-Serve `b632280`, MLX/Metal 0.32.2 on M5 Max 64 GB.

Scored requests took 72.39 minutes for retrieval and 96.63 minutes for chain tracking. Prefill accounted for about 93.7% of total request wall time; at the 156K rung, mean server prefill was 490.32 seconds and mean reported decode was 17.99 tokens/s. These are current measurements, not a matched cache/runtime speed comparison. C89 supplies no new capacity measurement; C84's peak and observed timing costs above remain the relevant separate evidence.

This qualifies the tested retrieval and simple variable-tracking grids with repetitive filler. Three to five prompts per rung do not establish general quality equivalence, difficult long-context reasoning, arbitrary-document recall, repository-editing quality or a failure boundary beyond the tested grid. The earlier broad M40 evidence remains historical TQ4 evidence. C91 separately records a length-finalization token-reporting issue exposed by calibration; raw counts are preserved, and every scored C89 response ended normally by stop.

See [C89 evidence](evaluation/C89-evidence-2026-09-14.json), the [full report](https://github.com/ivan-avramov/mlx_local_stack/blob/4fb84256fe97df1b0e0dd69208f2cee647d36f2d/docs/native16-depth-qualification-2026-09-14.md), and [audited result bindings](https://github.com/ivan-avramov/mlx_local_stack/blob/4fb84256fe97df1b0e0dd69208f2cee647d36f2d/benchmark/results/c89_export_20260914.provenance.json).

## Recommended current setting

Save this as `models.yaml` in an environment with the compatible fork revisions described below. The IDs name the target and, where configured, its exact companion; weight quantization and attention-KV precision are separate settings.

```yaml
manager_port: 8000
mlx_port: 8091
startup_timeout_seconds: 300
models:
- name: Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed
  type: vision
  hf_path: caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed
  max_kv_cache_size: 262144
  kv_prealloc_tokens: 262144
  cache_session_shrink: true
  kv_quant_scheme: turboquant
  kv_bits: 0
  quantized_kv_start: 0
  prefill_step_size: 512
  generation_defaults:
    temperature: 0.5
    top_p: 0.95
    top_k: 20
    min_p: 0.0
    presence_penalty: 0.0
    max_tokens: 102400
    thinking_budget: 81920
    enable_thinking: true
    reasoning_effort: medium
  draft_kind: mtp
  draft_model: caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter
  on_demand: true
```

Start from the compatible installed fork environment without additional worker overrides. This command clears cache/predictor environment overrides, disables APC and selects two retained sessions with one resident model:

```sh
env -u APC_ENABLED -u KV_BITS -u KV_QUANT_SCHEME -u KV_GROUP_SIZE \
  -u KV_KEY_BITS -u KV_VALUE_BITS -u KV_KEY_SCHEME -u KV_VALUE_SCHEME \
  -u QUANTIZED_KV_START -u MLX_VLM_SESSION_SHRINK_ON_RETIRE \
  -u MLX_VLM_DRAFT_KIND -u MLX_VLM_DRAFT_MODEL -u MLX_VLM_DRAFT_BLOCK_SIZE \
  MLX_VLM_CACHE_SESSION_MAX=2 MLX_SERVE_CONFIG=models.yaml mlx-serve start
```

The model loads on demand. An OpenAI-compatible client sends requests to `http://localhost:8000/v1` with model ID `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`. Omitted sampling fields inherit `generation_defaults`; thinking is enabled. The output cap is 102400 and thinking budget 81920. Near the context limit the server resolves a smaller budget from remaining space; a configured 262144 cap does not imply 262144 input tokens plus another 102400 output tokens.

The full active KV floor equals the context cap; keep prefill 512. `kv_bits: 0` means unquantized native16 attention KV, not unquantized model weights or a newly measured IEEE-FP16 dtype. TurboQuant is inactive when bits are 0 even if its scheme name remains configured. Idle retirement is explicitly true only on `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`; omitted `cache_session_shrink` preserves the worker default OFF only when `MLX_VLM_SESSION_SHRINK_ON_RETIRE` is absent, as in the command above. Suffix decoding stays OFF. These structural settings target the 64 GB evaluation machine, not arbitrary hardware.

## Runtime and evidence scope

The final C84 environment uses [MLX-VLM `522671c4bebc5ff492d465a1d0e6a14251f18260`](https://github.com/ivan-avramov/mlx-vlm/commit/522671c4bebc5ff492d465a1d0e6a14251f18260), [MLX-Serve `b632280709f771972bffbaf3231e996e8a89f4e8`](https://github.com/ivan-avramov/mlx-serve/commit/b632280709f771972bffbaf3231e996e8a89f4e8), and MLX/Metal 0.32.2. Those fork commits are published. Live validation of this exact final bundle covers the two current picks only; other cards retain historical model evidence and source-level compatible configuration, not a newly run model smoke. Older experiments used their recorded earlier runtime and cache mode.

Dates, original source revisions, per-axis observations and evidence-file hashes are recorded in [the accompanying evaluation evidence](evaluation/M44-evidence-2026-09-14.json) alongside this card. The tables here are self-contained: they do not rely on unpublished stack commits or links to future GitHub `main` content. Speculative decoding can change BF16 outputs; favorable task-specific intervals do not imply byte-lossless inference. Historical and current measurements are not pooled across cache modes, predictor states, budgets, corpora or runtimes.

## Artifact integrity audit, 2026-09-14

All 14 audited model and support files match the corresponding local artifact by full-byte cryptographic hashing, including weights and applicable configuration/tokenizer/vision files. README, license and repository-attribute files are tracked separately from inference artifacts. This publication changes the card and its dated evidence only; model artifacts remain unchanged. [Per-file hashes, audited revision and scope](evaluation/M44-evidence-2026-09-14.json).
