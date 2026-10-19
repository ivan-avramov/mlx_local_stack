F1 RESOLVED — continuous batching uses `GenerationBatch`; lockstep B>1 refuses.

F2 RESOLVED — plain batching commits first-token stops.

F3 RESOLVED — plain batching honors per-row budgets.

F4 RESOLVED — tests exercise production `BatchGenerator`; the spy is adequate because “never construct `SpeculativeGenerationBatch`” is the required invariant.

F5 PARTIAL — server cancellation closes immediately, but retained unclosed public streams remain unsafe; see F18.

F6 RESOLVED — speculative final-prefill kwargs are gated on effective speculation.

F7 RESOLVED — MTP fallback presents `(None, None)` to both batch prefill policies; non-MTP kinds are unchanged (`mlx_vlm/generate/ar.py:1465-1474`).

F8 RESOLVED — terminal close drains only publication; publication runs once, and publication exceptions clear the session (`mlx_vlm/generate/dispatch.py:1593-1611`).

F9 RESOLVED — parametrizations now receive stable, distinct seeds. Existing unseeded tests now prove one fixed nodeid-derived corpus rather than varying across runs.

F10 PARTIAL — inline zero-budget generation is correct; continuous batching is not. See F16.

F11 RESOLVED — `SpeculativePrefill` owns only `kwargs` and `chunks`; clearing captured chunks leaves no drafter state half-built (`mlx_vlm/speculative/utils.py:146-170`). Test coverage does not prove capture occurred or cover `plain_batch_active`.

F12 RESOLVED — both public batched entry points refuse MTP. No production caller reaches `_mtp_rounds_batch`; only direct private/test calls remain (`mlx_vlm/speculative/utils.py:104-112,290-292`).

F13 PARTIAL — distinct seeds and branch execution are restored, but quantized length-17 output correctness and even finiteness remain untested.

F14 RESOLVED — seedless positioned samplers no longer raise.

F15 RESOLVED — fallback removes `draft_model` before prefill setup; all current model policies treat `draft_model=None` as plain. The test’s `seen["chunked"]` assertion is vacuous if the hook is never called.

B==1 cached MTP — seeded/positioned token law, stop/length/thinking cuts, cache state and next-turn state are covered and consistent. Seedless MTP consumes RNG differently, but this changes deterministic coupling—not the stated distributional law.

F16 HIGH — `mlx_vlm/generate/ar.py:3423-3425,1897-1922`: continuous-batch `max_tokens=0` is broken. Integer zero becomes the server default via `max_tokens or self.max_tokens`; list-form zero still emits one token before checking the budget. The public schemas permit zero. Fix explicit `None` handling and retire zero-budget rows before sampling/prefill; test plain/MTP and mixed `(0,N)` rows.

F17 MEDIUM — `mlx_vlm/generate/ar.py:3013-3024`: batched MTP decodes plainly but still disables logprobs and APC merely because a drafter is configured. MTP-ON returns fabricated `0.0` logprobs (`ar.py:1931-1937`) while MTP-OFF returns real values, and loses prefix reuse. Apply these restrictions only to batches that actually speculate.

F18 MEDIUM — `mlx_vlm/generate/dispatch.py:1588-1611`: retaining an abandoned generator without closing it leaves its shared `PromptCacheState` mutated under the old label. Reusing that state is incorrect, and later closing the old stream can clear newer publication. Add an in-flight generation epoch, reject concurrent reuse, and prevent stale streams from publishing or clearing newer state.

F19 LOW — formatting CI will fail: top-level declarations lack Black’s required separation at `mlx_vlm/speculative/common.py:10-14` and `mlx_vlm/tests/conftest.py:47-49`. Run the pinned formatter.

VERDICT: NOT CLEARED F5 F10 F13 F16 F17 F18 F19

[exited with code 0]
