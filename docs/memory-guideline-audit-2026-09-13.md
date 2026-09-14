# Memory guideline correction and session audit — 2026-09-13

**Operator ruling C79:** roughly 48 GB MLX prefill peak at 256K is a planning guideline, not a strict 46 GB or 48 GB cutoff. Small overruns alone do not disqualify a model/configuration. Weigh actual memory pressure/stability, quality and latency. This supersedes C75's automatic memory-based OFAT stop.

## Scope and findings

Reviewed this conversation's conclusions, stack changes since checkpoint `068bb4d`, current result/report drafts, and both parent/integration fork instruction files. Independent read-only review reached the same findings.

| Finding | Correction / consequence |
|---|---|
| M42 native16 at 47.1386 GB was rejected and the OFAT declared closed solely because it exceeded 46 GB. | Withdraw that conclusion. The request completed normally, within the rough 48 GB target; native16 remains a candidate for matched quality evaluation. Deployment remains KV4 pending evidence/approval, not because native16 is disqualified. |
| Earlier M41/M42 text predicted automatic rejection from approximately 12 GB additional cache storage. | Preserve as a superseded historical expectation. Actual largest-rung peak delta was 6.0358 GB. Cache backing arithmetic is not a difference-of-peaks predictor. Do not reject an unmeasured arm solely from this estimate. |
| M43 margins of 4.90/8.20 GB were described as headroom. | They are distances below the old 46 GB threshold, not free physical memory. Relative to the rough 48 GB guideline the distances are approximately 6.90/10.20 GB; these do not become hard pass/fail boundaries. |
| The live qualification playbook inherited blanket restrictions against native-KV arms and a narrowest-KV preference for headroom. | Remove those policy shortcuts. Compare approved modes at matched settings and choose using quality, usability and measured memory pressure. Preserve full-cap preallocation and one resident model. |
| Archived capacity tools still emit `fits`/gate flags and stop against numeric 46 GB defaults. | Preserve raw rows, manifests and archived code. Those flags describe the instrument used, not current eligibility. Review stopping behavior before future runs; merely changing46 to48 would still create an incorrect hard cutoff. |
| Earlier AC/battery wording discounted timing without evidence. | Already retracted: both energy profiles were the same and power source alone did not establish a performance confound. Battery endurance was a separate concern. Historical timing remains unpaired for independent reasons. |

No other model/configuration rejection or valid capacity test stopped early was found in the audited session. Both M43 KV4 ladders and the M42 native16 ladder completed all three rungs, without reported transport errors. No B/C order changed. Native16 quality testing never began and was not an already-authorized running study that got aborted. C77/C78 questions concern runtime quality/timing evidence and remain separate. C76's M41 draw-count discrepancy remains explicitly recorded; it was not a memory-based selection decision.

Neither sibling fork's `AGENTS.md` contains a numerical hard memory rule. Their standing quality-first upstream-integration rule remains in place. The stack's `AGENTS.md`, qualification playbook, current PLAN/spec, result interpretations and handoff now carry C79.

## What was actually compared

M42 used `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` with the same mixed-quantized weights, repaired MTP ON, deployed temperature0.5/medium effort, source `c5a6f97b`, MLX/Metal0.32.2, cap/preallocation262144 and prefill step512. Only the registry `kv_bits` field changed4→0. The memory instrument limited generation/thinking fields to 256 tokens; these were capacity/timing probes, not a matched quality study.

Three measured prompts per configuration:130783,196115 and261449 actual tokens (nominal131072/196608/262144), following one calibration per ladder. M43 additionally ran the same KV4 ladder on `Qwen3.8-27B-mlx-uniform-4bit`. The separate merge compatibility screen covered arithmetic, executable Python, exact JSON, native tools/continuation and vision on both picks, using their unchanged KV4 setting. It does not establish native16 quality equivalence.

| M42 largest-rung configuration | MLX peak GB | Prefill seconds | Decode tok/s |
|---|---:|---:|---:|
| 4-bit TurboQuant KV | 41.1029 | 1573.81 | 6.2750 |
| Unquantized native16 KV | 47.1386 | 1114.00 | 12.7848 |

KV stores attention keys and values from processed tokens for subsequent attention. TurboQuant is the quantization scheme;3-bit and4-bit are separate settings of that scheme. Both current picks explicitly specify `kv_quant_scheme: turboquant` and `kv_bits: 4`, confirmed by worker launch evidence and result manifests. No 3-bit arm ran in this session.

The native arm disables cache quantization; it does not convert the whole model to BF16. Read-only checkpoint inspection found `torch_dtype: bfloat16`, mixed 4/8-bit affine module settings, and four safetensor shards with 1349 BF16 tensors and 498 packed U32 tensors. BF16 cache is expected from checkpoint/code, but live KV dtype was not instrumented. On the target model the source selects 16 native full-attention caches versus 15 TurboQuant caches plus one native final layer; 48 recurrent states are separate and unchanged. [Cache arithmetic and limits](../benchmark/results/m42_cache_storage_analysis_2026-09-13.json).

Historical registry context: commit `76450fa` (2026-06-16) set `Qwen3.6-27B-UD-MLX-6bit` to 3-bit TurboQuant; `04afd70` (2026-06-17) changed it to 4-bit. This history does not establish a3-bit default for the present picks or a3-vs4-bit quality result on them.

[Measured results](campaign-results.md); [M42 raw/provenance record](../benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/capacity_retrieval.m42native16-20260913.provenance.json); [current plan](PLAN.md).
