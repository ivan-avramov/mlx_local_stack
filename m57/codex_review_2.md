**R1 — High: the global handle contaminates concurrent requests.**  
[PrefillProfiler.active:57]($HOME/ws/mlx-vlm/mlx_vlm/prefill_profile.py:57), [begin_chunk:80]($HOME/ws/mlx-vlm/mlx_vlm/prefill_profile.py:80), [language.py:1001]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:1001).

- **Scenario:** request A publishes its profiler while request B executes decode, batched attention, or MTP verification. B’s `_prepare_projected_qkv` reads A’s handle and evaluates/synchronizes into A’s totals. Two profiled requests can overwrite each other’s handle; finishing one can leave the other unprofiled.
- **Consequence:** request isolation and inactive-path inertness break; timings mix requests. The docstring’s “not thread-safe” warning does not enforce single-request execution.
- **Fix:** use request-local state with a token-restored chunk scope and ownership checks. Non-owning decode/verifier calls must see `None`. Test concurrent threads and nested/interleaved generations.

**R2 — High: profiling evaluates substantial work that normal prefill discards.**  
[ar.py:704]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:704), [language.py:1870]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:1870), [mtp_profile.py:35]($HOME/ws/mlx-vlm/mlx_vlm/speculative/mtp_profile.py:35).

- **Scenario:** `other_fence` receives the entire `LanguageModelOutput`; the inherited collector recursively evaluates its logits. This language model does not implement `logits_to_keep`: it constructs logits for every chunk position. Ordinary chunked prefill discards those logits. For MTP, `SpeculativePrefill.append` also does not retain chunk outputs.
- **Consequence:** profiling adds full chunk vocabulary projections and allocations, inflating `other`, wall time and memory. Layer-output fences likewise force otherwise-dead terminal-layer work. This changes the measured workload, beyond merely removing overlap; reporting shares cannot repair it.
- **Fix:** fence the graph actually consumed by production prefill—cache updates and genuinely retained captures. Exclude discarded logits and account explicitly for otherwise-dead terminal-layer outputs. Add a lazy sentinel output proving discarded work is never evaluated.

**R3 — High: the tests do not reliably enforce CPU-only execution.**  
[test_prefill_profile.py:45]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_prefill_profile.py:45), [generate/audio.py:12]($HOME/ws/mlx-vlm/mlx_vlm/generate/audio.py:12), [generate/common.py:70]($HOME/ws/mlx-vlm/mlx_vlm/generate/common.py:70), [speculative/common.py:10]($HOME/ws/mlx-vlm/mlx_vlm/speculative/common.py:10).

- **Scenario:** package imports during collection resolve/cache generation streams before the fixtures call `mx.set_default_device(mx.cpu)`. Entering `mx.stream(cached_stream)` can restore the GPU device. The existing MTP tests also use a stream constructed at import time.
- **Consequence:** the CPU-only rule and claimed CPU equivalence coverage are not established. I discovered this after executing the requested command; device placement was not recorded, so I cannot certify that the run avoided Metal.
- **Fix:** fixtures must bind and restore the actual streams used by generation and MTP, not just the default device. Assert CPU placement inside the model/verifier calls.

**R4 — High: `gdn` does not fence all work performed by `linear_attn`.**  
[language.py:1216]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:1216), [language.py:1132]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:1132), [cache.py:954]($HOME/ws/mlx-vlm/mlx_vlm/models/cache.py:954).

- **Scenario:** the mark evaluates only `r`. `ArraysCache.update_window` separately constructs a contiguous trailing-window copy, or a lengths-dependent gather. That stored state is not a dependency of `r`.
- **Consequence:** this part of GDN remains lazy until the chunk’s cache-state evaluation, charging GDN work to `cache_post`. Synchronization cannot execute an unevaluated graph.
- **Fix:** close `gdn` with both its output and the state arrays it updates. Test an independent lazy cache-state branch and verify that it executes before the GDN timestamp.

**R5 — High: phase entry boundaries misattribute embeddings and preparation work.**  
[ar.py:555]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:555), [ar.py:691]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:691), [language.py:1214]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:1214), [language.py:1003]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:1003).

- **Scenario:** embeddings are constructed before `begin_chunk`, which synchronizes but does not evaluate them. Their lazy computation is pulled into the first layer’s `gdn` or `attn_prep` mark. Lazy vision dependencies can follow the same path. Model setup and input normalization also fall into those intervals. Meanwhile, `attn_prep` omits its returned array mask, allowing mask preparation to execute during SDPA.
- **Consequence:** named phases include work assigned elsewhere by the spec. The first GDN layer can appear expensive because it pays for embeddings; SDPA can include unfinished mask preparation.
- **Fix:** establish explicit entry fences for the specified components, assigning embedding/model setup to `other`; include all preparation outputs, including array masks, at the preparation boundary. Do this only when profiling.

**R6 — Medium: eviction work escapes `cache_post`.**  
[ar.py:709]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:709), [ar.py:720]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:720), [epicache.py:250]($HOME/ws/mlx-vlm/mlx_vlm/models/epicache.py:250).

- **Scenario:** cache state is evaluated **before** eviction. Eviction then replaces keys and values with lazy `mx.take` results. The following `safe_mark("cache_post")` receives no arrays.
- **Consequence:** eviction computation runs during a later consumer—another chunk or a capture—and is charged there instead. The profiler documentation also claims EpiCache observation belongs to SDPA, although its lazy scores are independent of the SDPA output.
- **Fix:** evaluate post-eviction cache state before closing `cache_post`. Define and fence observation’s intended attribution explicitly; do not describe it as part of “SDPA call only.”

**R7 — Medium: the final report changes from window means to cumulative means.**  
[prefill_profile.py:132]($HOME/ws/mlx-vlm/mlx_vlm/prefill_profile.py:132), [test_prefill_profile.py:198]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_prefill_profile.py:198).

- **Scenario:** after 33 chunks, the periodic line describes chunks 1–32, but the final line describes 1–33 instead of the remaining window.
- **Consequence:** the final line overlaps previous windows and dilutes late-context costs. This conflicts with the spec’s window-based report contract; the test explicitly enshrines cumulative final reporting.
- **Fix:** report the remaining window consistently, defining the exact-multiple-of-32 case. If a generation-wide summary is desired, distinguish it explicitly and revise the spec. Test unequal synthetic durations across multiple windows.

**R8 — Medium: a profiler failure can produce an apparently complete partial report.**  
[prefill_profile.py:104]($HOME/ws/mlx-vlm/mlx_vlm/prefill_profile.py:104), [prefill_profile.py:122]($HOME/ws/mlx-vlm/mlx_vlm/prefill_profile.py:122), [ar.py:773]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:773).

- **Scenario:** chunk 1 completes, then a mark fails during chunk 2. Generation continues, subsequent chunks are omitted, and `finish()` prints the old records with `final=1`. A model exception instead bypasses `finish()` entirely.
- **Consequence:** incomplete measurements can look like a normal final result; exceptional completion has no final-report lifecycle.
- **Fix:** invalidate or explicitly label incomplete measurements. Finalize from an outer `finally` without masking the original exception. Test failures after at least one recorded chunk.

**Spec-test coverage**

| Requirement | Genuinely covered | Only nominally covered / missing |
|---|---|---|
| 1. Switch unset | Zero explicit synchronization calls, no report, inactive handle for one isolated tiny-model run ([155]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_prefill_profile.py:155)). | No assertions against extra evaluation/timers; no concurrent, verifier, batched, padded or vision paths. |
| 2. Three chunks and reporting | Field presence, cold-start counts and keys, finite/nonnegative printed values; one shortened periodic window ([166]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_prefill_profile.py:166)). | No deterministic timing oracle, multiple-window means, warm-cache offsets or unequal chunks. Hook counts do not prove attribution. Clamping `other` masks negative residuals. |
| 3. Exact logits/cache equality | Exact first-token, **log-probability**, and flattened cache-array equality ([246]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_prefill_profile.py:246)). | Raw logits are not compared. CPU execution is not assured. No preallocation, MTP, session reuse, snapshots, retention or multimodal coverage. |
| 4. Raising mark | An immediately raising mark leaves generation operational and clears the handle ([260]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_prefill_profile.py:260)). | Cache equality is not asserted in this test; no failure after successful records or partial-report validation. |
| 5. Handle cleanup | Normal completion/close after first yield, and an exception entering the second chunk ([288]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_prefill_profile.py:288)). | No concurrent ownership, nested generation, or failure after partial layer/cache work. |

The “other family” test hides `active()` while running the same model; it does not exercise another family. The inherited timer tests verify eval-before-sync ordering, not whether these hooks supply the correct arrays.

For this prefill loop, bare `mx.synchronize()` is inside the generation stream context, which sets the default stream/device. I found no separate wrong-stream defect there. Ordinary non-evicting cache `keys=` accounting includes the initial offset; the tests verify only offset zero.

Executed exactly:

```sh
cd ../mlx-vlm && TMPDIR=$TMPDIR PYTHONPATH=$PWD .venv/bin/python -m pytest mlx_vlm/tests/test_prefill_profile.py mlx_vlm/tests/test_mtp_profile.py -q -p no:cacheprovider
```

Result: **24 passed, 2 warnings in 0.80s**. The initial sandboxed attempt failed before collection because pytest could not create temporary capture files. No source files were modified.

**Verdict: FIX-THEN-SHIP.** The current timings cannot support optimization decisions, and request isolation is not enforced.