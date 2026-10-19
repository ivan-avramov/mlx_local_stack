F1 RESOLVED — continuous batching falls back to plain; lockstep B>1 refuses (`generate/ar.py:1489`, `speculative/utils.py:427`).

F2 RESOLVED — first-token stops use plain batching.

F3 RESOLVED — per-row budgets remain in `GenerationBatch`.

F4 RESOLVED — tests configure real MTP with B>1 and prohibit constructing `SpeculativeGenerationBatch` (`tests/test_mtp_batch_plain.py:97`). The spy is adequate for the chosen no-speculation policy.

F5 RESOLVED — current-epoch cancellation, close and exceptions clear cached sessions (`generate/dispatch.py:1576`).

F6 RESOLVED — speculative prefill outputs are requested only when speculation is effective (`generate/ar.py:2664`).

F7 RESOLVED — MTP fallback presents `(None, None)` to prefill/offload policy; other drafters pass through unchanged (`generate/ar.py:1465`, `2385`).

F8 PARTIAL — normal terminal-close drains and publishes exactly once, but F22 remains.

F9 RESOLVED for P369; quantized length-17 correctness remains explicitly P385. See F25.

F10 RESOLVED on `generate_step` and cached-session paths; batched public routes remain incomplete under F20/F21.

F11 RESOLVED — unused DFlash/Eagle captures are discarded before `finish()` (`generate/ar.py:2686`); no other speculative state is initialized.

F12 RESOLVED — public batched MTP entry points refuse centrally (`speculative/utils.py:104`, `188`).

F13 OUT OF SCOPE — quantized length-17 performs structural smoke only (`tests/test_models.py:2265`), as assigned to P385.

F14 RESOLVED — sampler `.seed` is optional (`generate/ar.py:1496`).

F15 RESOLVED — inline processor fallback precedes speculative setup (`generate/ar.py:471`).

F16 PARTIAL — `BatchGenerator` and server emission are zero-token, but F20/F21 remain.

F17 RESOLVED for positive budgets — batched MTP retains APC/logprobs (`generate/ar.py:3017`); F21 affects zero-budget logprobs.

F18 RESOLVED under the server’s serialized GPU-worker model (`server/generation.py:1762`). Sequential stale streams cannot publish or clear. See residual F23/F24.

F19 RESOLVED — `git diff --check` is clean.

Routes CLOSED — production cannot reach `_mtp_rounds_batch`; continuous MTP always decodes plainly, public server rounds refuse MTP, and `generate_step` refuses B>1. B==1 inline remains the sole MTP route. No new stop/length/bonus/next-turn state discrepancy found.

F20 MEDIUM, MERGE-BLOCKING — `generate/ar.py:4171-4182` — `batch_generate(max_tokens=0)` appends sentinel `None` and passes it to `detokenizer.add_token`; mixed `[0, N]` budgets also fail. Append only non-`None` tokens.

F21 MEDIUM, MERGE-BLOCKING — `server/generation.py:2958-3003`, `server/openai.py:2762-2775,3174-3177` — zero-budget sentinel becomes token `0` with logprob `0.0`; logprob responses therefore contain a fabricated token despite `token_count=0`. Gate logprob creation on positive `token_count`.

F22 MEDIUM, MERGE-BLOCKING — `generate/dispatch.py:1358-1569`, `server/generation.py:1721-1740,2018-2034` — the terminal chunk reaches the client before session publication. If publication raises, the iterator has already ended and silently ignores the queued exception while the wrapper clears the session. Buffer the terminal chunk until stream exhaustion/publication succeeds.

F23 MEDIUM, RESIDUAL — `server/openai.py:2528-2533` — concurrent requests sharing a chat mutate `is_asymmetric_rendering` before serialized GPU execution; request B can alter request A’s publication policy. Carry it in the queued request.

F24 LOW, RESIDUAL — `generate/dispatch.py:1592-1628` — epoch checks are not atomic for direct multi-threaded `stream_generate` callers. The deployed server is serialized; a session lock is needed if external concurrent use is supported.

F25 LOW, RESIDUAL — `tests/conftest.py:57-76` — per-function seeding changes every existing test’s random corpus but does not seed module/session fixture setup, so “every test” determinism is overstated.

F26 LOW, RESIDUAL — `server/generation.py:2675-2718` — zero-budget uncached requests still run GPU/vision embedding before retirement. Short-circuit before `_gpu_embed`.

VERDICT: NOT CLEARED F20-F22

[exited with code 0]
