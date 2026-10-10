Reviewed the specified tips, using `ced1cae` for the stack. Findings are from static inspection.

**W1 — High — Stack: refusal errors are swallowed.**  
`benchmark/bench/provenance.py:625` raises ordinary `RuntimeError` for worker/registry disagreement; ambiguity does likewise at line 604. But `benchmark/bench/generate.py:321` catches these during precheck, and line 281 catches them during manifest stamping. Both continue. A worker serving `auto` against a `fused_v1` registry can therefore generate additional rows under an existing, incorrect manifest. This also defeats the new lazy-flag mismatch refusal. **Fix:** introduce a fatal provenance exception, propagate it through both callers, and test `generate.run` refusing before its first request.

**W2 — Medium — Fork: streaming tool calls lose counters.**  
[mlx_vlm/server/openai.py:2536]($HOME/ws/mlx-vlm/mlx_vlm/server/openai.py:2536) constructs the terminal tool-call chunk with only `predicted_per_second`. Setting `terminal_emitted=True` bypasses `_final_chat_chunk`, which contains the new counters. With the default `include_usage=False`, a cached-session request ending in tool calls returns no SDPA counters anywhere, despite logging them. **Fix:** populate both counters in this terminal shape and test streaming tool calls without a usage chunk. The corresponding fallback terminal construction at line 2677 should use the same helper.

**W3 — Medium — Fork: suspension is shared across threads.**  
[mlx_vlm/attention_policy.py:44]($HOME/ws/mlx-vlm/mlx_vlm/attention_policy.py:44) uses an instance-wide integer. `finally` makes exception recovery correct, and nesting separate context-manager invocations works. However, while thread A processes a padded row, thread B using the same model sees `_suspended > 0` and silently stops forcing otherwise eligible attention. Global counter differences also cannot isolate overlapping requests. The current server serializes model forwards on one generation thread, so this is **not an established HTTP race** in that path. **Fix:** use execution-context-local suspension, with exception, nesting and two-thread tests; preserve explicit serialization for counters or make them request-local.

**W4 — Medium — Stack: the “same run” exception is not enforced.**  
`benchmark/bench/provenance.py:430` accepts equal `unknown` values without checking run identity or receiving an explicit resume context. Two independent v7 manifests with matching fingerprint fields and unresolved policies return compatible; differing timestamps or run identifiers do not prevent this. Comparison refusal is implemented, but the compatibility predicate does not satisfy S1’s restricted exception. **Fix:** require verified same-run identity/context for unresolved-value compatibility; otherwise refuse. Apply this to lazy embeddings too.

**W5 — Medium — Stack: worker matching discards argument boundaries.**  
`benchmark/bench/provenance.py:96` joins `psutil`’s argument list into text; line 600 then reads the model using `\S+`. For a supported local model path containing spaces, the observed model value is truncated, no worker matches, and provenance silently falls back to the registry—even when the live worker disagrees. **Fix:** retain argv lists and parse exact argument tokens, including `--model=value`; distinguish failed observation from confirmed worker absence.

Amendment assessment below uses fork paths relative to `mlx_vlm/` and stack paths relative to `benchmark/bench/`.

| Item | Assessment and evidence |
|---|---|
| Rule 5 | **Satisfied for the serialized worker.** `attention_policy.py:56` rejects B≠1 and non-null padding metadata; `models/qwen3_5/language.py:1314,1381` suspend row recursion. Shared-instance concurrency limitation: W3. |
| Rule 6 | **Satisfied.** `attention_policy.py:61` rejects causal-string forcing when qL exceeds key length; native-branch test covers propagation. |
| Non-GPU refusal | **Satisfied.** `server/generation.py:195` calls `require_gpu` before stamping/self-test; `attention_policy.py:152` raises rather than skips. |
| F1 | **Not satisfied: W2.** Auto omission is implemented by both timing serializers (`server/schemas.py:490,553`), including nested OpenAI timing shapes. Anthropic responses gain no SDPA/null fields. Non-streaming cached endpoint coverage exists. |
| F2 | **Satisfied.** `tests/test_attention_policy_r1.py:93,112` execute real padded batches and verify actual B=1 recursion receives no forcing. |
| F3 | **Satisfied for the reviewed bf16 path.** `attention_policy.py:238` probes real embedding→q_proj→q_norm computation; subsequent RoPE preserves query dtype. Lines 206–224 select at max-KV, execute at 4096, reject zero calls; readiness timeout is documented. At 24 heads/bf16/262144 keys, 22—not 9—is the short-region threshold. |
| F4 | **Satisfied.** `tests/test_attention_policy_r1.py:377,386` exercise generator readiness and application lifespan failure; `server/app.py:445` propagates preload failure. |
| F5 | **Satisfied.** `server/cli.py:725` overwrites the handoff; load resolves once; `models/qwen3_5/qwen3_5.py:95` returns immediately when disabled. The existing eager embedding path remains selected by default. |
| F6 | **Satisfied within the accepted scope.** `tests/test_lazy_embeddings.py:422–483` cover raw logits, cache arrays/offsets, warm offset, landing/retention boundaries and real multimodal merge. |
| Router | **Satisfied.** `src/mlx_serve/config.py:120` validates bool/null and vision type; `process_manager.py:145` emits the flag only for `True`. Default-command tests cover omission. |
| S1 | **Not satisfied: W4.** `compare.py:311` does refuse unresolved controls, but compatibility lacks the same-run restriction. |
| S2 | **Satisfied.** `provenance.py:430` normalizes controls before the v1 early return; `test_attention_policy_review1.py` parametrizes v1–v6. |
| S3 | **Satisfied.** `compare_predictor.py:112,187` requires all three controls known, exactly the selected control differing, and the others matching. |
| S4 | **Not satisfied: W1, W5.** Multiple matches are detected locally, but refusal does not survive the driver and matching loses argv boundaries. |
| S5 | **Not satisfied: W1, W4, W5.** Fingerprinting, pre-v7 false normalization and comparison selection exist; attribution/refusal guarantees remain incomplete. |

**Verdicts:** Fork **FIX-THEN-SHIP** · Router **SHIP** · Stack **FIX-THEN-SHIP**.