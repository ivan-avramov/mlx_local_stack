M1 — low — stochastic acceptance is exact, but not via `p/q`.  
`mlx_vlm/speculative/common.py:173-196`, `mlx_vlm/speculative/mtp.py:244-286,458-492,721-746`. At `T>0`, verification samples an actual target token `X ~ p`; the implementation emits `X` whether it matches the draft or not. Matching only determines whether verification may continue. Inductively, accepted prefixes have the correct context, so arbitrary stochastic `q` affects acceleration, not output distribution. The premise that all equality acceptance is lossy is therefore too broad; comparing against target argmax would be lossy, but comparing against an independent target sample and emitting it is exact.  
Test: a small Markov model with deliberately different `p` and `q`; compare exact sequence probabilities or large-sample ON/OFF frequencies.

M2 — blocker outside registry defaults — continuous-batch MTP drops logits processors after token one.  
Plain batching applies repetition/presence/frequency penalties, logit bias and grammar processors at `mlx_vlm/generate/ar.py:1598-1627`. Prompt processing applies them to the first token at `ar.py:2611-2623`, but then constructs `SpeculativeGenerationBatch` without processor state at `ar.py:2664-2688`. Inline/cached MTP correctly falls back to plain decoding through `ar.py:220-251,827-849`. The deployed profile has `presence_penalty: 0.0` and no other processors (`mlx_vlm/tests/fixtures/stack_registry_golden.yaml:529-548`), so this does not affect default M63-style requests, but any request override makes ON non-neutral.  
Test: continuous-batch MTP with a forced repetition penalty or logit bias that changes the second token; compare with plain batching.

M3 — blocker — thinking-budget forcing is not equivalent.  
Plain decoding checks after every token and replaces the immediate next token at `mlx_vlm/generate/ar.py:868-872`. MTP checks only at round boundaries at `mlx_vlm/speculative/mtp.py:656-692`; tokens already accepted in the current block continue through `mtp.py:775-783`. The overshoot is intentional and documented in `mlx_vlm/tests/test_mtp_thinking_budget.py:1-14`, but it changes the output whenever the deployed 81,920-token budget is crossed.  
Test: make the budget trip after the first token of a fully accepted block; OFF must force the closer next, while current ON emits the block remainder first.

M4 — blocker — inline EOS/stop can persist state beyond the emitted sequence.  
MTP commits the entire accepted prefix before yielding at `mlx_vlm/speculative/mtp.py:749-764`. Inline stopping occurs later, outside the round loop, at `mlx_vlm/generate/dispatch.py:1290-1300`. If an accepted draft token is EOS before the end of `new_tokens`, later accepted positions have already entered KV and Qwen recurrent state although they are never emitted. `PromptCacheState.update()` then labels that state with the shorter emitted token history at `dispatch.py:1550-1553` and `generate/common.py:774-823`. Qwen `ArraysCache` commits recurrent snapshots through the retained position at `models/cache.py:1153-1173`; trimming token-counted KV later cannot reconstruct the correct recurrent state.  
Test: force EOS as the first accepted draft followed by another accepted token, close the stream, then compare cache state and next-turn output against plain decoding.

M5 — medium — RNG bookkeeping is sound, but ON is not seed-identical in every server path.  
The unseeded cached path uses separate target/draft MLX RNG states (`speculative/common.py:84-149`), with tests at `tests/test_speculative.py:136-206`. The positioned sampler makes Qwen MTP drafts deterministic through `speculative/mtp.py:848-856` and `speculative/drafters/qwen3_5_mtp/qwen3_5_mtp.py:403-437`. Continuous-batch speculative generation does not carry per-request seed overrides—the code explicitly limits them to plain generation at `generate/ar.py:2625-2634`. This changes reproducibility and cross-row coupling, not individual token marginals.  
Test: same-seed ON/OFF for cached B=1 and continuous batching, including requests admitted after the first batch row.

M6 — low for deployed Qwen; medium exception-path caveat — normal rollback is exact.  
Qwen verification starts a cache transaction at `models/qwen3_5/speculative_verifier.py:29-38`. Commit retains exactly `accepted + 1` verified inputs, while rotating, append-only, quantized and recurrent caches are restored through `speculative/cache_state.py:107-138,156-183,216-288` and `models/cache.py:971-1189`. The emitted mismatch/full-accept bonus is correctly left uncached until the next forward. Existing tests cover commit-before-yield, transaction abort and recurrent restoration.  
Caveat: `abort_speculative_round()` only handles `SpeculativeCacheTransaction` (`cache_state.py:210-214`); legacy snapshot-list recurrent targets such as Nemotron can remain mutated after an exception. This is not the deployed Fable/Qwen path.  
Test: inject a sampling exception into Nemotron verification and compare every recurrent/KV state with the pre-round snapshot.

M7 — medium — verifier numerics are designed to match decode, with a narrow threshold exception.  
Dense and quantized projections are executed singleton/timewise at `models/exact_speculative_verify.py:170-204`, `models/quantized_verifier.py:365-388`, and `speculative/ops/linear.py:61-126`. Numerous tests assert bit equality or decode argmax equality, including `tests/test_speculative.py:540-710,805-853`. Default serving remains `per_query`. However, verify length 2 still uses a joint SDPA call at `models/qwen3_5/speculative_verifier.py:126-143`; M58 established representation-level differences when crossing MLX key-length thresholds. This is a sparse accumulation-order/near-tie divergence class, not evidence of systematic bias.  
Test: ON/OFF prompts crossing 1,024/8,192/32,768/65,536 with adversarial near-tie logits; compare target logits and emitted tokens.

M8 — high evidence gap — existing tests and M63 do not prove the full claim.  
Greedy end-to-end parity exists for real suffix models and one GLM MTP loop (`tests/test_speculative_transactions.py:835-872`), plus strong verifier/rollback unit coverage. There is no end-to-end `T>0` ON-vs-OFF distribution test. M63 is reassuring but coarse: Fable recorded 43/43 vs 42/43 and 42/43 vs 42/43 strict totals with roughly 2.2× wall speed-up (`../mlx_local_stack/benchmark/results/m63_mtp/M63_REPORT.md:103-109`), while its MDE was about 27–28 percentage points. It cannot exclude subtle distribution changes or the boundary defects above.

Layer 2’s 50-prompt greedy identity test and one layer-3 agentic screen are not sufficient. Add targeted budget-boundary and EOS-next-turn cache tests first, then a deployed-temperature same-seed B=1 test and a small-model stochastic distribution test. M63 already approximates the proposed agentic screen and did not exercise those failure mechanisms.

VERDICT: NOT NEUTRAL M3 M4
