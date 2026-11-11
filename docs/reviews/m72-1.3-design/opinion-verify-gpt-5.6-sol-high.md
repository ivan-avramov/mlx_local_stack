P1 — Ledger #1: Resolved. `stack/benchmark/spikes/m72_e2e_prefill.py` gives every leg an independent `--capacity`, records it, and computes the layer-63 allowance from actual cache shapes. Both A5 legs can therefore use capacity 262,144. The real A5 measurement remains unrun; see P16.

P2 — Ledger #2: Resolved. `mlx-serve/src/mlx_serve/config.py` permits `fused_v1` and `joint_v1` with `kv_bits: 4` only when either TQ4 mode is selected, while retaining the old refusal without a mode.

P3 — Ledger #3: Resolved. `mlx_vlm/mtp_verify_scan.py::require_environment` accepts TurboQuant 4 only for `m72_v1` or `m72_exact`; `mlx_vlm/server/generation.py` passes the resolved mode before applying the MTP policy. Mode-absent refusal remains unchanged.

P4 — Ledger #4: Resolved. `mlx_vlm/tq4_attention.py::attend` and `::verify` derive T from the passed key state. Per-query fallback slices keys and values to each query’s own length before re-entering D2.

P5 — Ledger #5: Resolved. `mlx_vlm/tq4_attention.py::require_environment` refuses a set legacy environment flag, and `mlx_vlm/tq4_fast.py::supports` rejects both legacy cache mode and block-count overrides.

P6 — Ledger #6: Resolved. `tq4_fast.supports` checks exact cache class, codecs, bit widths, rotation, batch and head shapes, dtype, mask, sinks, legacy mode, and block overrides, with counted fallback reasons.

P7 — Ledger #7: Resolved. Batch cache classes route to `fallback:batch_cache`; the mode is wired into the inline cached-session loader and `/health` counters. Continuous-batching speculation remains untouched as required. The real served-path smoke is unrun; see P16.

P8 — Ledger #8: Resolved. Long-context kernel tests cover 65,537, 131,072, and 260,096 with capacity 262,144; D2 additionally covers lower lengths and tier boundaries.

P9 — Ledger #9: Resolved. Distinct `p2s`, `mma_prefill`, `mma`, `d2_verify`, `native:*`, `per_query:*`, and `fallback:*` counters make fallback and routing outcomes unambiguous.

P10 — Ledger #10: Resolved. Candidate A4(a) tests perform mode-off prefill, clone the state, then compare mode-off and mode-on decode in one process.

P11 — Ledger #11: Resolved. `tq4_attention.check_fp16_range` checks the query RMSNorm bound and both key/value MSE codebook bounds at load.

P12 — Ledger #12: Resolved. The matrix kernel fixes its production plan at 512 tokens per block, and A1 is rerun at target context lengths.

P13 — Ledger #13: Resolved. Width-one commit-pending verification reaches the ordinary base-attention hook and routes through `d2` or `single_pass`, rather than being treated as a normal MTP block.

P14 — Ledger #14: Resolved. `fused_v1` stamps remain on every full-attention module; the TQ4 hook executes before the native policy path.

P15 — Ledger #15: Resolved. Load checks require both policy stamps, and native layer-63 calls are counted and retain `fused_v1` prefill, `joint_v1` verify, and ordinary decode.

P16 — Acceptance coverage is incomplete  
Location: `mlx_vlm/tests/test_tq4_impl_model.py`; `stack/benchmark/spikes/m72_e2e_prefill.py`; `IMPLEMENTER-REPORT.md`; `TEST-WRITER-REPORT.md`  
Severity: major  
Evidence: confirmed coverage trace  
Problem: No test executed the real-model A4(a)/(b), A5, A6, or A7 gates. More importantly, both candidate and frozen seeded A4(c) tests use the superseded ON-vs-OFF comparison; no test enforces v1.1b’s `m72_exact` MTP-ON versus mode-absent TQ4 MTP-ON comparison from the same snapshot.  
Concrete failure scenario: The real 27B model exceeds the memory bound, silently falls back on the served chat path, or exact seeded verification diverges, while every currently successful candidate test remains green.  
Proposed change: Run the pre-registered real-model gates and add the corrected v1.1b seeded synthetic comparison before accepting the production candidate.

P17 — The worker refuses a registry combination the specification allows to fall back  
Location: `mlx_vlm/tq4_attention.py::require_environment`; `mlx_vlm/server/generation.py::_resolve_tq4_mode_from_env`  
Severity: minor  
Evidence: confirmed source trace  
Problem: `kv_quant_mode: prod` is accepted by mlx-serve with either mode but then refused during worker load. The specification places unsupported codecs behind `supports(...)=False`, requiring today’s path with `fallback:codec`, not a startup refusal.  
Concrete failure scenario: A valid registry arm using `kv_bits: 4`, TurboQuant, all required policies, `m72_v1`, and `kv_quant_mode: prod` passes router validation but the worker never becomes ready.  
Proposed change: Remove the load-time codec refusal and let `supports` perform the specified per-call fallback, or amend the specification and wrapper validation to refuse this combination consistently.

P18 — Invalid registry values are normalized to “absent”  
Location: `mlx-serve/src/mlx_serve/config.py::_load`  
Severity: minor  
Evidence: confirmed source trace  
Problem: `entry.get("tq4_attention") or ""` accepts explicit YAML `false`, `0`, `null`, empty lists, and similar falsey values as mode-off. The specified domain is absent, `m72_v1`, or `m72_exact`.  
Concrete failure scenario: A typo such as `tq4_attention: false` starts silently without the requested production mode instead of failing configuration validation.  
Proposed change: Preserve an explicitly supplied value and validate its type/value; default to `""` only when the key is absent.

P19 — Public kernels do not assert the cache-class precondition  
Location: `mlx_vlm/tq4_fast.py::_check_cache`  
Severity: minor  
Evidence: confirmed; reproduced by the frozen batch-cache test  
Problem: A one-row `BatchTurboQuantKVCache` passes `_check_cache`, despite the interface promising asserted preconditions. Served dispatch is safe because `supports` rejects it, but direct kernel calls are not.  
Concrete failure scenario: A direct caller passes a left-padded one-row batch cache; D2 treats padded rows as real tokens and can return a wrong result.  
Proposed change: Assert `type(cache) is TurboQuantKVCache` in `_check_cache`.

P20 — L=6–8 p2s calls do not guarantee fused SDPA  
Location: `mlx_vlm/tq4_fast.py::_fused_kwargs`  
Severity: minor  
Evidence: confirmed source trace  
Problem: For GQA 6 and query lengths 6–8, the candidate omits `force_fused=True`, although the routing specification says p2s uses MLX fused SDPA. Existing tests check routing and numerics but not this dispatch property.  
Concrete failure scenario: A 6–8-token non-verify chunk uses MLX’s non-forced fallback, adding score-materialization memory and losing the specified fused path.  
Proposed change: Either define these lengths as an explicit auto-dispatch exception in the specification or provide a supported fused implementation.

P21 — The stack’s clean gate is left red  
Location: stack provenance tests affected by `stack/benchmark/bench/provenance.py` fingerprint v9  
Severity: minor  
Evidence: confirmed test results  
Problem: Four existing tests still pin fingerprint v8 or mock only the prior three serving controls, violating A8’s clean-clone gate.  
Concrete failure scenario: The stack suite fails on every candidate checkout despite correct runtime behavior.  
Proposed change: Update the version/control expectations and add `registry_tq4_attention` returning `off` to the two affected mocks.

P22 — Beyond-specification surface  
Location: `mlx_vlm/models/base.py`; `mlx_vlm/tq4_fast.py`; `mlx_vlm/server/cli.py`; `mlx_vlm/tq4_attention.py`  
Severity: minor  
Evidence: confirmed source trace  
Problem: The candidate adds a separate base attention entry point, CLI value `off`, public kernel instrumentation functions/kwargs, an extra non-causal multi-query fallback rule, and unregistered `pytest.mark.slow` markers. The scratch-tail zero-fill and 128-row rounding are also additional, but correctly repair the confirmed NaN hazard.  
Concrete failure scenario: The public instrumentation API becomes accidentally relied upon, while test selection using `-m slow` remains unreliable because the marker is unregistered.  
Proposed change: Keep the scratch repair; register the marker and either internalize or explicitly document the added instrumentation and dispatch surface.

No confirmed supported-path wrong output, routing hole, mode-off numerical change, memory-bound violation, or load-order hole was traced. P16 leaves those real-model outcomes unverified.
