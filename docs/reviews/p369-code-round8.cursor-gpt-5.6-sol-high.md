P1 — Findings

- F23 — RESOLVED. `dispatch.py:903-908` uses `None` as the absence sentinel; explicit `False` no longer falls back to session state.
- F27 — RESOLVED. `dispatch.py:1638-1644` drains publication and clears `_inflight_epoch` before yielding terminal. Breaking without closing therefore preserves the published cache.
- F28 — RESOLVED. `dispatch.py:1626-1629` holds terminal only when `state is not None`; stateless streams pass terminal before post-terminal cleanup.
- F29 — RESOLVED. The uncached zero-budget shortcut at `server/generation.py:2608-2636` precedes `_log_prefill_started` at `2648-2650`. Cached zero-budget requests intentionally follow `2643-2667`; their prefill log is truthful because `dispatch.py:1335-1357` performs prefill and retires the session.
- F30 — RESOLVED. `tests/conftest.py:84-89` consistently uses effective `request.scope` for both gating and seed construction.

P2 — Interaction checks

The F5/F8/F18/F22 guarantees remain intact:

- Abnormal session exit clears at `dispatch.py:1650-1654`.
- Publication occurs while draining at `1638`, before terminal yield at `1644`; failure therefore clears the session and suppresses terminal.
- Stale streams return without publishing or clearing newer state at `1636-1637`, `1647-1648`, and the guarded finalizer.
- Close or break after session terminal keeps the published state because completion and `_inflight_epoch` are settled before delivery.
- Stateless cancellation/terminal ordering now matches upstream.
- Server cached-stream cleanup still closes in `server/generation.py:2033-2041`.
- No production regression found in either zero-budget path or fixture seeding.

P3 — Red-test quality

F23, F27, F28, and F29 deterministically fail for their stated mechanisms before their fixes. F27 explicitly retains the abandoned generator, avoiding garbage-collection dependence.

F30 exercises the correct defect, but its red-state proof has the weakness below.

P4 — F31 LOW — `tests/test_test_determinism.py:71-85` — non-blocking

Before the fix, `_scope_overridden_draw` samples ambient, unseeded MLX state and compares it with the desired fixed stream. It overwhelmingly fails for the intended reason, but that red outcome is not strictly order-independent or guaranteed: prior RNG state can vary and could theoretically equal the expected stream. The fixed test is deterministic; this is only a weakness in the red-proof construction.

VERDICT: CLEARED
