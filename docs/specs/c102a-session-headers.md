# C102(a) — client session identifiers reach the worker (2026-09-27)

Status: IMPLEMENTED in the parent forks; cold review DONE 2026-09-27 (Codex `gpt-6-astra`,
read-only: PASS-WITH-GAPS, four findings — P5 malformed values, P6 cache-key precedence, P7
compose flag scope, P8 test fidelity — all addressed below); live validation pending. Ruling: operator
2026-09-24 ("sounds good", extended to the client survey); go 2026-09-27.

## Problem (measured, M45 2026-09-23)

Every request in the worker log was `session=anon:*`. The mlx-serve router forwarded only
`content-type, authorization, accept, x-request-id`, so the worker's `X-MLX-VLM-Chat-Id` and every
client's own session header were dropped. Anonymous hash-chain routing then carried all traffic:
it needs ≥2 matching turn hashes and hashes the assistant turn over verbatim content, so a
single-message opener cannot match until its second turn and any non-verbatim echo (or a
regenerate/edit in OpenWebUI) silently forks the session. Client survey (2026-09-24, verified on
the wire for opencode 1.18.30): opencode sends `x-session-id` + `x-session-affinity` on every
request; Claude Code `x-claude-code-session-id` (+ `session_id` in JSON `metadata.user_id`); Codex
`session-id` (+ body `prompt_cache_key`); OpenWebUI `X-OpenWebUI-Chat-Id` only with
`ENABLE_FORWARD_USER_INFO_HEADERS=true` (body metadata is stripped before forwarding); Zed body
`prompt_cache_key`; Switchyard `x-switchyard-session-id`.

## Change

1. `mlx-serve` `router.py`: `_FORWARDED_HEADERS` gains `_SESSION_HEADERS` = {x-mlx-vlm-chat-id,
   x-session-id, x-session-affinity, x-parent-session-id, x-claude-code-session-id,
   x-openwebui-chat-id, session-id, session_id, x-switchyard-session-id}. Still an allowlist.
2. `mlx-vlm` `session_manager._resolve_chat_id`: precedence = configured header →
   `_CHAT_ID_HEADER_ALIASES` (x-session-id, x-session-affinity, x-claude-code-session-id,
   x-openwebui-chat-id, session-id, session_id, x-switchyard-session-id) → body `chat_id` →
   `metadata.chat_id` → `metadata.session_id` → `session_id` parsed from a JSON
   `metadata.user_id` → body `prompt_cache_key` LAST (a cache-affinity hint some clients share
   across conversations; cold review P6). Values must be non-blank printable strings (or ints)
   ≤256 chars; containers, booleans, control characters and oversized values are rejected, not
   stringified (cold review P5). NOT accepted: `user`,
   `safety_identifier`, opaque `metadata.user_id` (per-user keys → two parallel chats of one
   user trim each other's cache), `x-request-id` / `x-client-request-id` / `x-interaction-id`
   (rotate per request).
3. `docker-compose.yml`: `ENABLE_FORWARD_USER_INFO_HEADERS=true` on the OpenWebUI service.
   The flag is global: OpenWebUI then sends user name/email/role headers to EVERY model
   connection it has, not only the router (cold review P7). Today every connection is local
   (router :8000, task model :8092, both owned by `init.py`); the router drops those headers
   and the worker never sees them. Adding a non-local OpenWebUI connection later must revisit
   this flag or use the JWT mode.

## Pre-registered acceptance criteria

- A1 Router unit: session headers (all nine, any case) are forwarded; `Cookie`, `Host`,
  `X-OpenWebUI-User-Email/-Name/-Role` are NOT; `content-type`/`authorization`/`x-request-id`
  behaviour unchanged. Both proxy paths (`/v1/chat/completions`, `/v1/completions`) use the
  same allowlist.
- A2 Worker unit: precedence exactly as listed; case-insensitive header lookup; blanks skipped;
  per-user and per-request identifiers ignored; existing header/body/metadata tests unchanged.
- A3 No serving-parameter, sampling, KV or predictor change; anonymous hash-chain routing is
  untouched and remains the fallback when nothing explicit is present.
- A4 Live, opencode: one `opencode run` turn through the router → worker log line carries
  `session=<opencode session id>` (not `anon:`); a `--continue` turn reuses the prefix
  (`cached_tokens` ≥ the system-prompt length).
- A5 Live, OpenWebUI: one chat turn → worker log `session=<owui chat id>`; a second turn in the
  same chat reuses; the task-model (:8092) path is unaffected.
- A6 Live, no client id: a bare curl conversation still routes anonymously and reuses on its
  third request as in M45 (fallback intact).
- A7 Full fork suites pass (mlx-serve `tests/`, mlx-vlm `mlx_vlm/tests/test_session_cache.py`,
  `test_server.py`); stack `test_provenance_fingerprint.py` and configgen checks pass after the
  submodule bump.

## Review protocol

Cold review by Codex (`gpt-6-astra`, read-only sandbox, fresh context) against A1–A3 and the
diff, before the fork commits land; findings recorded in the lab notebook; blocking findings
fixed with a failing test first. Live A4–A6 after the submodule bump on a fresh stack start.
