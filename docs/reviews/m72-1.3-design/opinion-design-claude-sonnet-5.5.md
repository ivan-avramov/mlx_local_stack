Eight findings. I traced all of them in the snapshot source except F7, which is a hypothesis, and I did not run any GPU code.

**F1 — Layer 63's `fused_v1` prefill is unreachable through the registry and has no fork-side opt-in (major, confirmed)**
- Location: SPEC "Settled constraints" (last bullet), routing row "native layer 63", Scope 2.
- Problem: The spec gives layer 63 "`fused_v1` prefill (the attention policy, already per-cache)". But `mlx-serve/src/mlx_serve/config.py:170-179` rejects `attention_policy: fused_v1` unless `kv_bits == 0`. Scope 2 relaxes only `mtp_verify_scan: joint_v1`.
- On the fork side, the policy comes from `MLX_VLM_ATTENTION_POLICY` via `_apply_attention_policy_from_env` (`generation.py:181`). `MLX_VLM_ATTENTION_POLICY` is outside this spec's flag and env list. The policy's own load-time checks live in the `attention_policy` module, which is not in the snapshot. I could not confirm whether they refuse `kv_bits` set.
- Failure scenario: An implementer follows the spec to the letter. The registry entry `kv_bits: 4, tq4_attention: m72_v1, attention_policy: fused_v1` is refused at registry load. Dropping `attention_policy` leaves layer 63 on the default SDPA prefill, which is not "the shipped native16 pick". A2 and A4 then cannot hold as written.
- Fix: Say explicitly whether `m72_v1` implies `fused_v1` stamping on the native layers, or relax the `fused_v1`/`kv_bits` rule alongside `joint_v1`. Add a test that layer 63's prefill goes through `force_fused`.

**F2 — The fork's own `mtp_verify_scan.require_environment` still refuses `kv_bits` (major, confirmed)**
- Location: SPEC Scope 1 (file list) and "Interfaces".
- Problem: `mtp_verify_scan.py:521-524` fails whenever `kv_bits` is set. The spec lists no modification of `mtp_verify_scan.py` or `_apply_mtp_verify_from_env` (`generation.py:204-222`). It says only that mlx-serve accepts the combination.
- Failure scenario: With mlx-serve accepting `joint_v1` + `kv_bits: 4` + `m72_v1`, the worker exits at load. The implementer must invent where to relax the check. Two implementers will choose differently, for example a bypass when `MLX_VLM_TQ4_ATTENTION` is set versus a parameter on the function.
- Fix: Specify the edit to `mtp_verify_scan.py` and `generation.py`. Also specify the order of `_apply_tq4_attention` relative to `_apply_mtp_verify_from_env`, and state that `joint_v1` still refuses `kv_bits` when the mode is absent (A3).

**F3 — A5 compares peak memory at different capacities (major, confirmed)**
- Location: A5, A6, and "Scratch size = the state's capacity".
- Problem: The dev harness sets `max_kv_size = prealloc_tokens = N`, the prompt length (`m72_e2e_prefill.py:61,72`). At 131,072 tokens the scratch is about 0.54 GB and the packed state is sized for 131K. Production capacity is `max_kv_cache_size: 262144` (registry excerpt line 5), and the settled constraints say capacity equals the maximum context.
- Impact: A "production" run at 262,144 capacity adds about 0.54 GB of scratch plus about 2 GB of preallocated packed K/V (my estimate). That exceeds the A5 budget, which is the 4.30 GB baseline plus 0.40 plus 0.25. Running A5 with capacity 131,072 passes but does not test the served configuration. A6 has the same capacity ambiguity.
- Fix: State the capacity for A5 and A6. Either measure both arms at capacity 262,144, adding a dev-harness baseline at that capacity, or re-derive the budget as dev-harness peak plus (262,144 − 131,072) × bytes per token for scratch and cache, plus the layer-63 delta.

**F4 — A4 is internally contradictory (major, confirmed by design)**
- Location: A4.
- Problem: A4 asks for token-identical greedy decode "after an identical prefill state". But `m72_v1` prefill (p2s) is only within tolerance of today's prefill, so layers 17 onward receive different activations. The quantized K/V in the cache therefore differ. The mode is stamped at load, so it cannot be toggled between prefill and decode within one process.
- Failure scenario: A real-model run with the mode on has a different cache from the mode-off run, and greedy tokens may diverge legitimately. A tester then either cannot satisfy A4 or "satisfies" it by decoding a hand-copied cache. The test has no defined construction and is vacuous or flaky.
- Fix: Define A4 as a unit-level test. Build the cache with today's path, then run decode D2 versus the unmodified singleton on that same cache, using a test-only per-call switch. Keep the real-model 8K/32K check as logit tolerance only.

**F5 — `supports()` and `prefill_attention` ignore the mask (major, confirmed)**
- Location: Interfaces (`prefill_attention`, `supports`), routing row "prefill chunk".
- Problem: p2s hard-codes `mask="causal"` (`dev/m72_scratch_prefill.py:153`). The routing condition is only L > 1. Qwen3.5 prefill passes the mask from `create_attention_mask(h, cache[fa_idx])` (`language.py:1475`, `223-237`), and that function can return an array. `base.py` hands the mask to today's TQ path, which honours it. The spec does not require that the mask equal plain causal on bottom-right alignment.
- Failure scenario: A non-causal or array mask is silently ignored. Examples are padded rows, EpiCache-evicted caches where physical offset differs from RoPE offset, and a prefill continuing a prefix. The output is wrong with no error and no fallback count.
- Fix: Add `mask` to `supports()` and route anything other than `None` or `"causal"` to today's path. Add a test and a fallback-counter reason for that case.

**F6 — Decode and prefill `supports()` omit today's kernel switches and the TQ cache flags (major, hypothesis)**
- Location: "plain decode" rows, R4, `supports()`.
- Problem: Today's decode block count depends on `_decode_2pass_use_legacy`, `_decode_2pass_num_blocks`, and `TQ_DECODE_2PASS_LEGACY` (`turboquant.py:6313-6339`). Production also takes the single-pass or 2-pass path only when the mask is `None` or `"causal"`, and `sinks` is `None` (`base.py:406`; `turboquant.py:6258`). The spec says D2 "keeps `production_num_blocks`" and is "bit-identical" but does not say it must reproduce those overrides or reject them.
- Failure scenario: A run with the legacy flag or a block override produces different bits, and the A1 and A4 identity claims fail only in that configuration. A non-`None` decode mask or `sinks` would also be misrouted.
- Fix: `supports()` must return False when the cache has `_decode_2pass_use_legacy` or `_decode_2pass_num_blocks` set, when the mask is neither `None` nor `"causal"`, or when `sinks` is not `None`. Test each.

**F7 — No Python-level kv_bits guard for TQ4 without the mode on the worker (minor, hypothesis)**
- Location: SPEC "Interfaces", `require_environment`.
- Problem: With `m72_v1` on and `kv_bits` of 4 but layer 63 not given the `joint_v1` or `fused_v1` stamp (F1/F2), layer 63 silently falls to the per-query loop. This is allowed by the spec text, which only forbids the converse. The counter would show nothing wrong because layer 63 is a native cache.
- Fix: Make `m72_v1` require `joint_v1` and `fused_v1` at load, or document that layer 63 may fall back. Add a counter for layer-63 routes.

**F8 — Short-prompt cost of the capacity-sized scratch (scope request)**
- Location: "Scratch size = the state's capacity".
- Request: With capacity 262,144, every prefill chunk, including a 3-token tail or a short prompt, allocates a 1.07 GB scratch and dequantizes `[0, T)`. For L in 2…5 at large T this is far slower than today's path. Consider a threshold, or reuse of the verify path for L ≤ 5, with a counter. No speed bar is in 1.3, so I list this only as a request.