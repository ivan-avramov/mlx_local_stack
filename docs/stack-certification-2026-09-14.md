# Stack certification — 2026-09-14

**C84 runtime integration checks PASS; C85 continuation failure resolved.** Scope: C84 runtime integration and C85 cache retirement repair. This report supersedes earlier activation-pending statements in the September13 integration report.

## Installed and published state

Both parent forks were pushed to GitHub before their revisions were fetched through the stack submodule origins. The actual stack serves MLX-VLM `522671c4bebc5ff492d465a1d0e6a14251f18260` and MLX-Serve `b632280709f771972bffbaf3231e996e8a89f4e8`, with locked MLX/Metal 0.32.2. Serving imports resolve to the stack's `src` checkouts. Startup now retains committed gitlinks instead of advancing them with `--remote`. Stack publication has not been requested.

The upstream integration includes MLX-VLM through `434afb1a` and MLX-Serve through `a6f80eb`. The additional upstream changes after the first integration checkpoint add flattened OptiQ key mapping for Mage-VL and revert specialized MXFP4/Q3 verifier kernels. Generic fallbacks remain; affine4/5/8 specializations remain. No specific failure mechanism is asserted for upstream's revert. <!-- allow-shorthand -->

The maintenance review retired duplicate speculative serving/sampling and manual APC paths, adapted cache/snapshot interfaces, and retained the certified hybrid MTP path where its contract differs from upstream. Both forks' AGENTS files now require this quality-first disposition review on every sync. See [integration disposition](upstream-integration-2026-09-13.md#maintenance-disposition).

## Actual default and repaired failure

- `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`: native16 KV (`kv_bits: 0`), `cache_session_shrink: true`, repaired MTP ON, deployed t0.5/medium.
- `Qwen3.8-27B-mlx-uniform-4bit`: TQ4, unchanged retirement default, certified MTP ON, deployed t0.6/medium.
- Both retain cap/preallocation 262144, prefill 512, two retained sessions, and APC OFF. Weights and sampling did not change. Native16 describes unquantized attention KV; model weights remain quantized. This run does not newly instrument the native cache dtype.

The initial activated native16 worker OOMed on a tool continuation, including a fresh two-request reproduction. This was an actual failure, unrelated to treating 48GB as a strict cutoff. The work landed three cache repairs: discard an unusable prior cache before replacement; trim native preallocated caches logically without hiding their full backing behind short views; evaluate and synchronize compact buffers before retirement publishes them. The first repairs alone did not clear the live failure; their failed retests remain preserved.

Idle padding is compacted, and the configured full floor is restored before an active write. Regression tests cover immediate active-memory release without caller evaluation, exact prefix data, native/uniform/TurboQuant caches, external aliases, recurrent state and exception safety. Owned-buffer reduction is distinguished from memory still referenced by another owner. The final live tool continuation passes without reducing active context or switching cache mode.

## Validation in the stack

| Check | Result |
|---|---|
| Full MLX-VLM suite, actual final submodule | 5372 passed, 10 skipped, 149 passing subtests |
| Full MLX-Serve suite | 106 passed |
| Stack comparison/provenance guards | 119 passed |
| Client configuration generation check | Passed |
| Final live smokes, both deployed models | Five cases/six requests each pass: arithmetic, Python, JSON, native tool continuation, vision |
| Native16 fresh-worker tool pair | Pass; both requests re-prefill with zero cache reuse |
| Native16 three-turn conversation | READY/ORANGE/ORANGE; third turn reuses 1839 tokens plus 49 new prompt tokens |
| Independent reviews | Source/cache repairs, instruments, final17 serving requests,80 quality requests and prose reviewed |

Tool handoff uses `tool_calls`, with bounded handoff validation; final answers stop and converge. Do not label the handoff itself a normal stop completion. Vision coverage here is one fixed image; session reuse is a short-context integration check.

## Matched quality and task speed

The fresh paired screen used five frozen seeded items per axis/model: Math500, HumanEvalPlus, MBPPPlus and prose. All 80 responses converged. All 40 AFTER visible answers, reasoning hashes and token counts exactly match BEFORE. Mechanical scores are unchanged:

| Model | Math500 | HumanEvalPlus | MBPPPlus | Prose |
|---|---:|---:|---:|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | 5/5 | 4/5 | 5/5 | Five reviewed ties |
| Qwen3.8-27B-mlx-uniform-4bit | 5/5 | 5/5 | 5/5 | Five reviewed ties |

Accuracy equals strict accuracy here because all responses converge; nonconvergence counts are zero. The shared native16 HumanEval/141 failure includes the previously documented ASCII/Unicode prompt-reference mismatch; its official score is preserved. Prose review found shared factual and methodological weaknesses, including unsupported capability/partnership claims and research-design errors. Identical prose is not proof of factual correctness. The direct review was nonblinded and used one reviewer, not a mixed-family judge panel.

Five pairs per axis do not establish a 5pp quality-equivalence bound. Observed accuracy deltas are0pp; empirical bootstrap intervals collapse to [0,0] with zero discordance and cannot bound unseen failures. The approximate per-axis MDE is 56pp. This is a bounded regression screen, not complete all-axis native16 recertification or a ranking change.

The following ratios are AFTER/BEFORE with 95% paired bootstrap intervals, 10000 resamples, seed 84. Task latency includes request overhead; decode measures generation rate. Each axis remains separate. These intervals resample tasks, not repeated whole-machine sessions, and do not measure run-to-run timing drift.

| Model | Axis | Task-time ratio [95% interval] | Decode-rate ratio [95% interval] |
|---|---|---|---|
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | math500 | 1.022 [1.007, 1.031] | 0.986 [0.974, 0.996] |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | humanevalplus | 1.012 [1.008, 1.022] | 0.995 [0.977, 1.016] |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | mbppplus | 1.025 [1.014, 1.036] | 0.977 [0.962, 0.991] |
| Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed | cjudge | 1.018 [1.008, 1.031] | 0.983 [0.970, 0.994] |
| Qwen3.8-27B-mlx-uniform-4bit | math500 | 1.008 [1.002, 1.016] | 0.995 [0.987, 1.004] |
| Qwen3.8-27B-mlx-uniform-4bit | humanevalplus | 1.006 [0.995, 1.012] | 1.002 [0.993, 1.016] |
| Qwen3.8-27B-mlx-uniform-4bit | mbppplus | 1.001 [0.982, 1.012] | 1.003 [0.994, 1.020] |
| Qwen3.8-27B-mlx-uniform-4bit | cjudge | 1.000 [0.990, 1.008] | 1.002 [0.992, 1.014] |

Native16 total request time increased from 668.6 to 680.8s (+1.82%); token count stayed 23839. The second model increased from 821.4 to 822.9s (+0.18%); token count stayed 31682. Native16's per-axis latency increase is 1.2–2.5%, so speed is not described as unchanged. Accept this observed small cost for the repaired serving behavior; the combined experiment does not isolate how much comes from retirement versus other source changes or timing drift. No throughput-based model promotion follows.

The BEFORE source was the initially activated merged stack (`e3bffd9a`/`f8f1df4`), not the original pre-merge runtime. AFTER includes additional upstream commits, all C85 repairs, the Serve retirement option and native16 retirement policy. All 69 package versions, wire requests, weights, deployed sampling and active cache floors remain matched. Earlier M43 old/new compatibility screens cover the original merge separately; C77's original pre-merge-versus-integrated runtime-bundle comparison remains unarmed. Do not relabel this repair/bundle comparison as that missing study. Broad native16 depth/vision quality and the original integration's quality effects remain unmeasured by this paired screen.

[Complete quality analysis](../benchmark/results/m43_c84_quality_20260914.json); [semantic prose review](../benchmark/results/m43_c84_prose_review_20260914.json). The mechanical analyzer preserves its original prose-review-pending status; the separate completed semantic review supplies that subsequent evidence.

## Full-context memory and speed

| Metric at 261449 actual prompt tokens | BEFORE | AFTER | Observed change |
|---|---:|---:|---:|
| MLX prefill peak | 47.138620GB | 47.155397GB | +0.016777GB (+0.036%) |
| Prefill time | 1099.88s | 1165.33s | +5.95% |
| Decode rate | 11.9545tok/s | 11.5061tok/s | −3.75% |
| Completion tokens | 170 | 170 | Unchanged |
| Retrieval co-score | 1.0 | 1.0 | Unchanged |

Both main requests completed normally with byte-identical answers/reasoning, zero prefix reuse and positive MTP counters. The two-token calibration intentionally ends at its length cap without MTP. The final probe completed in 1185.9s including calibration and overhead. Peak increased by 0.036% in this pair; repeatability is unmeasured. Prefill and decode are slower observations and are retained explicitly. Existing system swap did not grow across the final probe (9017.88→8849.88MiB); that machine-wide snapshot is supporting context, not model allocation attribution.

[Matched capacity evidence](../benchmark/results/m43_c84_capacity_20260914.json); [failure and repair history](../benchmark/results/m43_c85_failure_history_20260914.json).

Short-task memory readings do not certify capacity. The capacity comparison uses the exact same calibration and 261449-token prompt, fresh workers, no prefix reuse, and positive main-request MTP counters. Rough 48GB is descriptive guidance, not a strict selection cutoff. One full-context observation per state cannot establish timing repeatability or isolate an allocation/kernel cause.

The capacity daemon provided real self-test, periodic and terminal records, but its generic monitor lacked a baseline-rate estimate and retained smoke-specific wording. This reporting limitation does not alter the independently validated raw measurements; correct it before reusing that wrapper.

## Recommendation and remaining queue

Certify the specified runtime integration and retain the operator-approved native16 default, retirement setting, MTP and B/C ordering. The known continuation OOM is resolved; sampled quality is preserved and full-context execution completes near 47.16GB. Accept the observed small task-latency increase and single-pair long-context slowdown for the repaired behavior. Their precise causes and repeatability remain unresolved; do not advertise the update as speed-neutral. A repeated timing/profile study can reshape C78 if that cost becomes the next priority.

Native16 remains provisional for broader depth/vision quality. C84 does not close the original pre-merge-versus-integrated quality comparison. The evidence supports this bounded runtime decision, not universal quality equivalence.

Next in PLAN is M44: audit every HuggingFace-published model/sidecar/vision artifact against its identified local source, then refresh model cards with applicable measurements, recommended parameters, MTP configuration and tested vision limits. Other open items are C83 capacity-policy reporting, C76's 39-versus-42 historical draw discrepancy, and broader native16 quality/depth coverage. Original C77/C78 proposals need reshaping before launch. The daily-driver stack remains stopped after certification work; starting it and pushing the stack are separate operator actions.
