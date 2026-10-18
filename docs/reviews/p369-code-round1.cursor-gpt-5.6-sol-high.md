1. F1 — high — `mlx_vlm/speculative/mtp.py:1291-1350`  
Lockstep B>1 MTP truncates emitted tokens but leaves full `accepted_list` commits. A qwen3_5 row stopping mid-block therefore retains un-emitted KV/recurrent/drafter state; terminal bonuses are not committed because the repair is restricted to `n_active == 1`. Fix by disabling lockstep B>1 speculation or implementing a transaction matching each emitted prefix.

2. F2 — medium — `mlx_vlm/generate/ar.py:2097-2123`  
A continuous-batch request stopping on its first token is marked finished before `_start_rounds`; that token is never written to cache, unlike plain decoding. Preflight first-token termination and fall back to `GenerationBatch`, or add a batch-aware terminal-token commit.

3. F3 — medium — `mlx_vlm/generate/ar.py:2084`; `mlx_vlm/speculative/mtp.py:1307-1321`  
The batch loop receives `max(self.max_tokens)`, so `_mtp_plain_emission` cannot see shorter rows’ individual length boundaries. Such rows emit the right count externally but can commit the remainder of the block internally. Pass per-row remaining budgets into `_mtp_rounds_batch`.

4. F4 — medium — `mlx_vlm/tests/test_mtp_batch_fallbacks.py:125-141`; `mlx_vlm/tests/test_mtp_thinking_budget.py:182-193`  
Tests only exercise B>1 when speculation is disabled and M3 at B==1. They miss F1–F3. Add speculative B>1 stop/unequal-length cases, including first-token and bonus termination, asserting target/recurrent/drafter state against plain decoding.

VERDICT: NOT CLEARED F1 F2 F3 F4
