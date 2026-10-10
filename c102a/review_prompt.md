You are a cold, adversarial code reviewer. You have NO prior context; read only what is on disk. Do not modify anything.

Scope: an uncommitted change across three repos under $HOME/ws:
- mlx-serve (router): `git -C $HOME/ws/mlx-serve diff` — files src/mlx_serve/router.py, tests/test_completions_proxy.py
- mlx-vlm (worker): `git -C $HOME/ws/mlx-vlm diff` — files mlx_vlm/server/session_manager.py, mlx_vlm/tests/test_session_cache.py
- mlx_local_stack: `git -C $STACK_REPO diff docker-compose.yml`, and the spec docs/specs/c102a-session-headers.md (read it first; it holds the pre-registered acceptance criteria A1–A7).

Task: verify the change against criteria A1, A2, A3 ONLY (unit/design criteria; A4–A7 are live checks run later). For each: PASS / FAIL / PARTIAL with the exact evidence (file:line). Then list findings ranked by severity: correctness bugs, security/PII leakage through the new allowlist (the repo is public; the worker logs the session id), precedence mistakes, case-sensitivity, empty/whitespace handling, interaction with the existing anonymous hash-chain routing in session_manager._resolve_session (read it), Starlette header semantics (Request.headers is case-insensitive; the tests use a helper — check the helper mirrors that), any way a per-user or per-request identifier could still be treated as a conversation key, and whether the streaming proxy path uses the same allowlist as the non-streaming path (grep _forward_headers call sites in router.py). Also judge whether the OpenWebUI compose flag has side effects beyond the chat-id header (it also forwards user name/email/role headers to the router; check whether the router could log or forward them).

Output format: a markdown report with sections: Verdict (PASS / PASS-WITH-GAPS / FAIL), Criteria table (A1–A3), Findings (numbered, severity, file:line, one-paragraph rationale, suggested fix), Non-findings you checked. Be terse and concrete; no praise.
