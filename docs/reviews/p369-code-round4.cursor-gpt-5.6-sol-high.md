F1 PARTIALLY RESOLVED — supported dispatches refuse/fallback, but the exported batched helper remains unsafe (F12).

F2 RESOLVED — first-token stops use plain batching or commit the singleton token.

F3 RESOLVED — continuous batching uses each row’s plain budget.

F4 RESOLVED — tests drive the real `BatchGenerator`; the spy is adequate because the required invariant is that `SpeculativeGenerationBatch` is never constructed.

F5 PARTIALLY RESOLVED — close/cancel/exception paths clear state, but zero-token completion bypasses publication/retirement (F10). Retained, unclosed generators remain unobservable until close/GC; the server closes explicitly.

F6 RESOLVED for batched MTP — speculative final-prefill outputs are gated by `is_speculative` at `mlx_vlm/generate/ar.py:2643-2678`.

F7 RESOLVED for batched MTP and `batch_generate` — `_effective_prefill_draft` changes no non-MTP drafter (`mlx_vlm/generate/ar.py:1458-1467,2377-2402,4072-4095`). See F15 for inline fallback.

F8 RESOLVED — terminal close drains the inner generator once; publication exceptions leave `completed=False` and clear state. No double publication found (`mlx_vlm/generate/dispatch.py:1583-1606`). The second F8 test’s “on” arm omits the drafter at `mlx_vlm/tests/test_mtp_session_cancel.py:227-240`, but the preceding test covers both arms.

F9 PARTIALLY RESOLVED — deterministic cases use 64 seeds and separate evaluation, but branch coverage was removed and global seed-zero weakens unrelated parametrized tests (F13).

M2–M5 RESOLVED for positive-budget B==1 cached requests: stop, length, forced-budget sequence, bonus position, cache state and next-turn state are covered. F10 is the exception.

ROUTES PARTIAL — ordinary server, `stream_generate`, and `batch_generate` cannot reach batched MTP; exported lower-level server helpers still can (F12).

TESTS PARTIAL — production dispatch cores are exercised and would fail the round-1 implementation. Processor/seed tests using MTP never reach those named fallback branches because `mtp_batched` wins first.

F10 HIGH — `mlx_vlm/speculative/utils.py:398-404`, `mlx_vlm/generate/dispatch.py:1333-1350`, `mlx_vlm/server/schemas.py:743-746` — `max_tokens=0` is accepted: MTP emits/commits one token while plain emits none; plain also returns without publishing or clearing a mutated warm session. Fix: emit nothing for MTP at zero and retire or correctly publish the prompt-only session.

F11 HIGH — `mlx_vlm/generate/ar.py:2243,2570-2581,2643-2678`; `mlx_vlm/speculative/utils.py:151-157` — chunked DFlash/Eagle prefill captures hidden-state chunks, then processor/seed/plain-batch fallback omits captures on the final forward; `finish()` combines the chunks with missing `hidden_states` and crashes. Fix: determine effective speculation before chunking or explicitly discard captured chunks on fallback.

F12 MEDIUM — `mlx_vlm/speculative/utils.py:92-100,278-296`; `mlx_vlm/server/__init__.py:18` — `run_speculative_server_rounds(..., draft_kind="mtp")` and `get_speculative_rounds_batch("mtp")` still expose `_mtp_rounds_batch`, reopening F1–F3 to direct server-library callers. Fix: refuse MTP centrally in both batched entry points.

F13 MEDIUM — `mlx_vlm/tests/test_models.py:2224-2234`; `mlx_vlm/tests/conftest.py:52-68` — every quantized length-17 MoE case is skipped before model construction, removing even shape/dtype/crash coverage; every parametrized test also begins from identical seed-zero data. Fix: run a structural smoke check for the unstable branch and derive deterministic seeds from test node IDs.

F14 MEDIUM — `mlx_vlm/generate/ar.py:1486-1490,2951-2959` — a custom positioned sampler with `sample_target` but no `.seed` raises `AttributeError` during non-MTP per-request-seed fallback. Fix: compare against `getattr(sampler, "seed", None)`.

F15 MEDIUM — `mlx_vlm/generate/ar.py:465-488,591-603,833-856` — cached MTP requests falling back because of penalties still request speculative prefill captures and present MTP to the offload policy; explicit unchunked MoE offload can bypass its safety default. Fix: resolve the inline processor fallback before speculative prefill setup and pass the effective plain configuration to both policies.

VERDICT: NOT CLEARED F10 F11 F12 F13 F14 F15

[exited with code 0]
