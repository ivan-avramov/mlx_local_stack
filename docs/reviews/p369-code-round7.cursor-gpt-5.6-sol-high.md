F20 — RESOLVED.

F21 — RESOLVED.

F22 — RESOLVED; publication failures precede terminal delivery. F5/F8 correctness remains intact.

F23 — NOT RESOLVED, merge-blocking. `generate/dispatch.py:902-906`: explicit `False` falls back to the session’s legacy `True`, selecting asymmetric publication. Use a sentinel/`None` check so explicit `False` is authoritative.

F24 — RESOLVED as documentation-only.

F25 — RESOLVED for current module/session fixtures; see F30.

F26 — RESOLVED; uncached zero-budget requests skip embedding, prefill, and APC work.

F27 — Residual, `generate/dispatch.py:1630-1641`: breaking after the terminal chunk without closing leaves `_inflight_epoch` set; the next request clears a valid published cache. Clear the epoch before yielding terminal.

F28 — Residual, `generate/dispatch.py:1619-1631`: stateless streams now delay terminal delivery and cancellation through APC cleanup despite having no session publication. Restrict pre-terminal draining to session-backed streams.

F29 — Residual, `server/generation.py:2618-2639`: zero-budget requests log “Prefill started” although no prefill occurs. Move the shortcut before that log.

F30 — Residual, `tests/conftest.py:85-87`: declared `fixturedef.scope` misses fixtures whose effective scope is overridden by parametrization. Use `request.scope`.

VERDICT: NOT CLEARED F23
