F1 — RESOLVED by avoidance: batched MTP always selects plain `GenerationBatch` (`mlx_vlm/generate/ar.py:1470-1471,2623-2635,2750-2765`); direct lockstep B>1 is refused (`mlx_vlm/speculative/utils.py:423-434`). `_mtp_rounds_batch` itself remains unsafe if directly invoked.

F2 — RESOLVED by the same plain fallback; inline first-token termination is committed (`mlx_vlm/speculative/utils.py:396-404`).

F3 — RESOLVED: plain `GenerationBatch` enforces each row’s own budget; speculative `max(max_tokens)` is unreachable for MTP.

F4 — RESOLVED: tests use the real `BatchGenerator` and real model/drafter. The refusal spy (`mlx_vlm/tests/test_mtp_batch_plain.py:97-102,118-138`) is adequate for the chosen dispatch policy and would fail the round-1 code. It proves route closure, not `_mtp_rounds_batch` correctness.

2 — CLOSED for normal production entry points. Server continuous batching (`mlx_vlm/server/generation.py:2623-2654`) and `batch_generate` (`mlx_vlm/generate/ar.py:4075-4082`) pass through the fallback. `stream_generate` B>1 reaches the refusal. `_mtp_rounds_batch` remains directly callable through `run_speculative_server_rounds` (`mlx_vlm/speculative/utils.py:176-195,278-296`) but no standard MTP request reaches it.

3 — PARTIAL. Normal B==1 stop, length, bonus, thinking-budget and next-turn paths retain M2–M5 (`mlx_vlm/generate/dispatch.py:1172-1182`; `mlx_vlm/speculative/mtp.py:731-755,816-908`). Abnormal stream termination fails exact state parity; see F5.

4 — PARTIAL. Normal production dispatch is exercised, including `_process_cached_request`. The suite would fail on F1–F4, but it has no warm-session cancellation case. Also, the server test records cache snapshots but compares only tokens (`mlx_vlm/tests/test_mtp_stop_state.py:307-309`).

5 — No normal-path MTP-OFF or suffix regression found. Other drafter kinds retain their existing speculative path. F6 is an avoidable fallback overhead.

F5 — HIGH — `mlx_vlm/speculative/mtp.py:852-868`; `mlx_vlm/server/generation.py:1885-1891,2011-2026`; `mlx_vlm/generate/dispatch.py:1075-1078,1409-1564`. MTP commits a verified block before yielding. Cancelling/disconnecting a warm cached request returns before session publication or cleanup, leaving old `token_ids` over an in-place cache containing prompt and potentially un-emitted tokens. MTP-ON and plain commit different ahead-state, especially corrupting hybrid recurrent next turns. Fix: clear `PromptCacheState` on every abnormal cached-request exit, or transactionally rewind it; add warm-session cancellation tests at every block position.

F6 — MEDIUM — `mlx_vlm/generate/ar.py:1470-1471,2637-2640,2750-2765`. Although batched MTP always falls back, prefill still requests speculative hidden/shared-KV outputs and then discards them. Gate speculative prefill kwargs on effective `is_speculative`.

VERDICT: NOT CLEARED F5

[exited with code 0]
