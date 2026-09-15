# Shipped native16 depth qualification — 2026-09-14

**C89 PASS; results and final review complete.** `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` recovered all 125 embedded codes across 25 retrieval prompts through the nominal 128,000-token rung and answered all 39 chain-4 variable-tracking prompts correctly through the nominal 156,000-token rung. All 64 scored responses converged within the full resolved thinking budget, with positive MTP activity and zero cached prefix tokens. The final independent data audit passed.

Retain the approved native16 configuration and default ordering. Both completed depth axes support the selected configuration at the tested scope. Recommend closing Phase 2 at that approved measured scope. The [approved protocol](specs/native16-depth-qualification.md) defines the scope; earlier runtime, capacity and bounded quality evidence remains in the [stack certification report](stack-certification-2026-09-14.md).

## Tested model, configuration and source

Only `caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` is tested, with the repaired `caslca/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed-mtp-drafter`. Target and drafter weights are unchanged. Requests use the actual registry's deployed settings on the M5 Max 64 GB machine; private local weight paths are retained in the original evidence.

| Setting | Tested value |
|---|---|
| KV format | Native16, `kv_bits: 0`; declared `kv_quant_scheme: turboquant` inactive at zero bits; `quantized_kv_start: 0` |
| Context cap / active preallocation | 262,144 / 262,144 tokens |
| Prefill step / idle retirement | 512 tokens / `cache_session_shrink: true` |
| Predictor / retained sessions / APC | Repaired MTP ON / 2 / APC environment flag absent |
| Sampling | Temperature 0.5, top_p 0.95, top_k 20, min_p 0.0, presence_penalty 0.0 |
| Thinking / generation allowance | Enabled, medium effort, 81,920 thinking tokens; 102,400 maximum generated tokens |
| Runtime | MLX/Metal 0.32.2; MLX-VLM `522671c4bebc5ff492d465a1d0e6a14251f18260`; MLX-Serve `b632280709f771972bffbaf3231e996e8a89f4e8` |
| Recorded stack source | `bc66da863c2ac279aee2ce981f8bb0d9caa60d74` |

The fixed prompt allowance is 159,744 tokens, leaving the full 102,400-token output allowance within the total cap. Offline checks covered all 64 planned prompts; the largest was 155,628 tokens. Every scored request on both axes retained the full resolved 81,920-token thinking budget. Independent prompt and sampler seeds were frozen before generation. The included five-prompt pilots consumed scheduled trials; they added no cases and replaced none. Only one model was resident, and the worker was unloaded between axes.

C89 is a qualification of this shipped configuration. It includes no predictor-OFF, alternate-KV, second-model or historical-runtime comparison. The [client configuration audit](client-config-audit-2026-09-14.md) separately verified all five shipped carriers and corrected OpenCode attachment, modality and context-limit semantics. It did not change registry sampling or constitute a new end-to-end client benchmark.

## Retrieval — complete

Each prompt contains five codes at 10%, 30%, 50%, 70% and 90% depths. All five independently seeded prompts passed at each rung. Ordinary accuracy scores recovered codes; strict accuracy additionally requires resolved-budget convergence. Every prompt also recovered all five codes.

| Nominal prompt tokens | Actual prompt tokens | Fully correct prompts | Recovered codes | Ordinary / strict accuracy | Converged | Budget hits / errors |
|---|---|---|---|---|---|---|
| 8,000 | 8,089–8,095 | 5/5 | 25/25 | 1.00 / 1.00 | 5/5 | 0 / 0 |
| 32,000 | 32,012–32,017 | 5/5 | 25/25 | 1.00 / 1.00 | 5/5 | 0 / 0 |
| 64,000 | 63,913–63,919 | 5/5 | 25/25 | 1.00 / 1.00 | 5/5 | 0 / 0 |
| 96,000 | 95,814–95,818 | 5/5 | 25/25 | 1.00 / 1.00 | 5/5 | 0 / 0 |
| 128,000 | 127,716–127,723 | 5/5 | 25/25 | 1.00 / 1.00 | 5/5 | 0 / 0 |

At **each** of the five rungs, accuracy at the five individual depths was **1.00 / 1.00 / 1.00 / 1.00 / 1.00** (five observations per depth per rung). All 25 responses stopped normally, reported positive MTP activity and accepted draft tokens, and reported zero cached prefix tokens. No nonconvergence kinds were recorded. Reported completion lengths ranged from 157 to 228 tokens.

The observed effective retrieval context is the largest tested nominal rung, **128,000 tokens**, under the existing 0.85 threshold. This is bounded evidence from five prompts per rung and repetitive filler. It does not establish a population-equivalence result, arbitrary-document recall, difficult reasoning or repository-editing quality, nor locate a failure boundary beyond the grid.

| Nominal prompt tokens | Mean server prefill (s) | Mean reported decode (tokens/s) | Mean request wall (s) | Maximum request wall (s) |
|---|---:|---:|---:|---:|
| 8,000 | 11.41 | 45.05 | 15.95 | 16.66 |
| 32,000 | 56.21 | 33.21 | 62.13 | 66.82 |
| 64,000 | 141.48 | 24.74 | 148.66 | 152.61 |
| 96,000 | 245.95 | 21.04 | 255.55 | 260.79 |
| 128,000 | 376.08 | 18.98 | 386.39 | 394.09 |

The 25 scored requests totalled **4,343.43 seconds** of request wall time (72.39 minutes), including **4,155.63 seconds** of server-reported prefill and **183.73 seconds** of reported decode time. These are sums over scored requests, excluding calibration, loading and orchestration gaps. Decode rates above are arithmetic means of per-request rates. Server `prompt_ms` measures prefill, not independently observed time to first token. Prefill dominates wall time, while reported decode throughput decreases as prompt length increases; this describes the observed scaling without isolating a hardware cause.

Historical M41 TQ4/older-runtime timings were planning inputs only. There is no matched timing comparison here, so these numbers establish neither a native16 speedup nor a regression. Short generations and retained peak-memory counters from these depth requests supply no new capacity or memory-peak certification. The separate C84 largest-context measurement remains the capacity evidence; the roughly 48 GB guideline is not a hard selection cutoff.

## Chain-4 variable tracking — complete

Each prompt follows four linked variable assignments distributed through filler and asks for the final numeric value. All 39 prompts were exact-match correct and converged. This reasoning-depth curve remains separate from retrieval of embedded codes.

| Nominal prompt tokens | Actual prompt-token range | Scored prompts | Ordinary / strict accuracy | Converged | Budget hits / errors |
|---|---|---:|---|---|---|
| 8,000 | 8,087–8,087 | 5 | 1.00 / 1.00 | 5/5 | 0 / 0 |
| 16,000 | 16,062–16,062 | 5 | 1.00 / 1.00 | 5/5 | 0 / 0 |
| 24,000 | 24,037–24,037 | 5 | 1.00 / 1.00 | 5/5 | 0 / 0 |
| 32,000 | 32,012–32,012 | 5 | 1.00 / 1.00 | 5/5 | 0 / 0 |
| 48,000 | 47,962–47,962 | 5 | 1.00 / 1.00 | 5/5 | 0 / 0 |
| 64,000 | 63,912–63,912 | 5 | 1.00 / 1.00 | 5/5 | 0 / 0 |
| 96,000 | 95,814–95,814 | 3 | 1.00 / 1.00 | 3/3 | 0 / 0 |
| 128,000 | 127,714–127,714 | 3 | 1.00 / 1.00 | 3/3 | 0 / 0 |
| 156,000 | 155,628–155,628 | 3 | 1.00 / 1.00 | 3/3 | 0 / 0 |

All 39 responses stopped normally, reported positive MTP activity and accepted draft tokens, and reported zero cached prefix tokens. Each received a 102,400-token generation allowance and retained the full resolved 81,920-token thinking budget. Reported completion lengths ranged from 269 to 403 tokens, totalling 12,529 tokens. There were no budget hits, errors or nonconvergence kinds. Actual prompt lengths are equal across trials within each reasoning rung, hence the repeated range endpoints.

The observed effective reasoning context is the largest tested nominal rung, **156,000 tokens** (155,628 actual prompt tokens), under the 0.85 threshold. Five prompts per lower rung and three per upper rung provide bounded evidence for simple four-step tracking through filler. They do not certify difficult reasoning, long-session repository editing, arbitrary prompt distributions, or equivalence to another KV configuration.

| Nominal prompt tokens | Mean server prefill (s) | Mean reported decode (tokens/s) | Mean request wall (s) | Maximum request wall (s) |
|---|---:|---:|---:|---:|
| 8,000 | 11.93 | 45.72 | 19.09 | 20.06 |
| 16,000 | 27.34 | 37.65 | 36.25 | 39.51 |
| 24,000 | 45.38 | 33.22 | 55.68 | 57.45 |
| 32,000 | 63.24 | 30.78 | 73.23 | 74.28 |
| 48,000 | 103.08 | 27.68 | 114.51 | 115.56 |
| 64,000 | 149.17 | 24.98 | 162.44 | 163.24 |
| 96,000 | 258.58 | 21.64 | 273.31 | 276.04 |
| 128,000 | 366.84 | 20.63 | 382.25 | 405.74 |
| 156,000 | 490.32 | 17.99 | 508.32 | 516.84 |

The 39 reasoning requests totalled **5,797.63 seconds** of request wall time (96.63 minutes), **5,347.91 seconds** of server-reported prefill and **444.53 seconds** of reported decode time. Prefill again dominated request time; decode throughput decreased with longer prompts. The same timing definitions and limits as retrieval apply: arithmetic mean per-request decode rates, no independent TTFT measurement, no matched historical timing comparison and no new memory-capacity inference.

Across both completed axes, the 64 scored requests totalled **10,141.06 seconds** of request wall time (169.02 minutes). This excludes calibration, loading and orchestration gaps. All 66 authorized calls were accounted for: 64 scored requests and two excluded calibrations, including the adopted original retrieval calibration.

## Calibration amendment and validation

The first retrieval calibration requested one generated token. It returned 3,210 prompt tokens, matching the offline tokenizer, with null final-answer content, reasoning text, length termination and two reported completion tokens. The initial validator rejected that response shape before any scored request ran. The immutable failed instrument run and original wire response remain preserved; this was not a failed quality case.

The reviewed v2 instrument adopted that already-spent calibration by verifying its original request, response, protocol and registry bindings and the absence of prior scored rows. It issued no replacement retrieval calibration. Completed call accounting is **25 retrieval + 39 reasoning + 2 calibrations = 66 calls**, including the adopted call; the authorized ceiling was not exceeded. The only registry amendment redirected monitoring logs to the private work directory; all other parsed values, source runtime, weights, prompts, seeds, sampling and requested budgets remained fixed.

Source inspection identified the existing C91 length-terminal accounting issue: the cached finalization chunk carries a default one-token count that the endpoint sums. Calibration therefore accepts one or two reported completion tokens and null final content, while remaining excluded from quality. For scored responses, a valid length-terminated null answer remains an empty-answer, nonconverged measurement. A reported 102,401 tokens is accepted only for length termination, explicitly annotated and retained as a budget failure. Raw counts are never rewritten, no universal subtraction is applied, and the requested budget is not raised. Other malformed, transport and provenance failures abort unscored without retries. The [C91 reporting repair](specs/c91-terminal-token-accounting.md) remains deferred; it was not applied during qualification.

Before v2 launch, **79 fake-only instrument tests and 54 canonical tests passed**, followed by independent cold review. The runner uses exclusive outputs, frozen provenance, a known-positive daemon, 300-second critical assessments and recorded exits. Root and independent retrieval reviews regraded every retrieval request and verified prompt, response and configuration bindings. The final exporter verified the complete call ledger, raw regrades and frozen bindings across both axes. The independent final audit verified all 39 raw four-assignment chains against their gold values and explicit answers, all nine reasoning rungs, all seven exported artifacts and the 1,781 pinned files. Router records contained 65 unique successful HTTP requests; adding the original adopted calibration gives the authorized total of 66. Owned model, router, driver and reader processes were stopped after completion; serving ports were idle.

Retrieval evidence is available as [canonical rows and summary](../benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/retrieval.c89-shipped-20260914.json), [manifest](../benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/retrieval.c89-shipped-20260914.manifest.json) and [provenance](../benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/retrieval.c89-shipped-20260914.provenance.json). Their bytes match the verified retrieval export. Completed reasoning has separate [canonical rows and summary](../benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/reasoning.c89-shipped-20260914.json), [manifest](../benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/reasoning.c89-shipped-20260914.manifest.json) and [provenance](../benchmark/results/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed/reasoning.c89-shipped-20260914.provenance.json). The [global qualification bundle](../benchmark/results/m43_c89_depth_20260914.json) records both axis summaries, runtime attestation, frozen bindings and the calibration amendment. Wire hashes refer to original private request/response bytes; export paths are redacted.

| Binding | SHA-256 |
|---|---|
| Retrieval data | `8a4d016946d3f7c3fa2bbfeae4ff750406f9a2885834e92bb8a98d93a42ea2eb` |
| Reasoning data | `145ead79ca6d8905ae13da61773bc459a1d95c7fa62af5552888d2ad2e537dd2` |
| Global qualification bundle | `5c00a95a54e7078333e6240383c9e20e89dad418d2a2ef2048083349ad5be74a` |
| v2 freeze | `0a2e1f9d8987c91cb72339ca8cee4bc45e5b3a5ae66b8703b20cf790267e12b1` |
| Runner | `a05f928643952da670c528d5909efb12c909b72c8c7c966b625b1354ce57913e` |
| Protocol | `1b255de6c06735a300d29639b03809c363041f1fa3f88af0d66f886583788b5b` |
| Tested registry snapshot | `22b6d91fa9f883484884c46f3d19502cc0c8c6b02e162d8f00933df77eb051b6` |

## Recommendation at this stage

Keep `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` as the first approved B/C pick with native16 KV, repaired MTP and its existing tune; keep `Qwen3.8-27B-mlx-uniform-4bit` second with its unchanged TQ4/MTP configuration. Both completed depth axes strengthen the first pick's shipped-depth evidence but supply no cross-model ranking comparison. No configuration change or ladder movement follows from these results. Recommend closing Phase 2 at the approved measured scope, with final independent review complete. This is not universal native16 quality or equivalence certification. Historical C77/C78 comparisons remain deferred and are not closure blockers.
