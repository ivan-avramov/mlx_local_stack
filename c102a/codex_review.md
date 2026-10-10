## Verdict

**P1 — PASS-WITH-GAPS.** The normal forwarding and resolution paths implement the specification. Broader identifier validation and privacy guarantees remain incomplete.

Router tests: **6 passed**. Another **65 in-memory checks** passed using the actual resolver/filter functions and installed Starlette `Request`/`Headers`. No files changed. A4–A7 were not evaluated.

## Criteria table

| ID | Criterion | Result | Evidence |
|---|---|---|---|
| P2 | A1 | **PASS** | All nine session headers plus the original four are allowed; names are matched case-insensitively; Cookie, incoming Host and OpenWebUI user headers are excluded: [router.py:102]($HOME/ws/mlx-serve/src/mlx_serve/router.py:102). Both endpoints share dispatch, and streaming/non-streaming apply the same filter: [router.py:477]($HOME/ws/mlx-serve/src/mlx_serve/router.py:477), [533]($HOME/ws/mlx-serve/src/mlx_serve/router.py:533), [593]($HOME/ws/mlx-serve/src/mlx_serve/router.py:593). |
| P3 | A2 | **PARTIAL** | Exact specified precedence and blank-string skipping are implemented: [session_manager.py:208]($HOME/ws/mlx-vlm/mlx_vlm/server/session_manager.py:208), [246]($HOME/ws/mlx-vlm/mlx_vlm/server/session_manager.py:246). Named per-user/per-request fields are ignored under the default configuration. Existing resolution tests remain unchanged: [test_session_cache.py:310]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_session_cache.py:310). However, accepted fields can still supply shared user keys or malformed values; see P5–P6. |
| P4 | A3 | **PASS** | Diffs contain no sampling, serving-parameter, KV implementation or predictor changes. `_resolve_session` is unchanged: explicit keys synchronize hashes, otherwise anonymous matching remains the fallback: [session_manager.py:522]($HOME/ws/mlx-vlm/mlx_vlm/server/session_manager.py:522), [529]($HOME/ws/mlx-vlm/mlx_vlm/server/session_manager.py:529). |

## Findings

1. **P5 — Medium — Malformed identifiers become shared cache keys and raw log content.** [session_manager.py:208]($HOME/ws/mlx-vlm/mlx_vlm/server/session_manager.py:208), [226]($HOME/ws/mlx-vlm/mlx_vlm/server/session_manager.py:226). `_clean_id` stringifies arbitrary JSON values. Reproduced: nested `session_id: {}`, `[]`, and `false` resolve to `"{}"`, `"[]"`, and `"False"`; an object containing an email becomes the entire stringified object. These bypass anonymous matching and select a shared cache entry. Embedded newlines also survive trimming and reach the existing raw session logger at [generation.py:582]($HOME/ws/mlx-vlm/mlx_vlm/server/generation.py:582). **Fix:** accept bounded, nonblank string identifiers; reject containers, booleans and control characters; escape logged values. Add malformed-value tests.

2. **P6 — Medium — A generic cache-routing key can override an actual conversation identifier.** [session_manager.py:263]($HOME/ws/mlx-vlm/mlx_vlm/server/session_manager.py:263). Reproduced: `prompt_cache_key="account-42"` with `metadata.session_id="conversation-7"` resolves to `"account-42"`. A client sharing that key across conversations makes them share mutable cache state; a rotating key prevents reuse. `_resolve_session` does not consult conversation hashes once an explicit key wins ([line 523]($HOME/ws/mlx-vlm/mlx_vlm/server/session_manager.py:523)). This follows the written precedence but exposes a **specification gap**: cache affinity is assumed to mean conversation identity. **Fix:** make this mapping an explicit client compatibility option, and amend the spec to prioritize genuine conversation identifiers.

3. **P7 — Medium — The compose privacy claim is conditional, not enforced.** [docker-compose.yml:39]($STACK_REPO/docker-compose.yml:39). The flag enables user name/email/role forwarding globally. The inspected router drops those headers and contains no incoming-header logging, but OpenWebUI also has a direct task-model connection ([init.py:66]($STACK_REPO/openwebui-init/init.py:66)); reconciliation preserves additional existing provider URLs ([reconcile_models.py:108]($STACK_REPO/openwebui-init/reconcile_models.py:108)). Consequently, another configured provider can receive user information without passing through this allowlist. No actual external transmission was established. **Fix:** scope chat-ID forwarding to approved local connections, or enforce local-only destinations while this flag is enabled; qualify “User info stays on this box.”

4. **P8 — Low — Committed tests do not fully guard the acceptance contract.** [test_completions_proxy.py:130]($HOME/ws/mlx-serve/tests/test_completions_proxy.py:130) omits the role header, value-preservation assertions and streaming forwarding; [test_session_cache.py:385]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_session_cache.py:385) tests only one alias-precedence pair. The helper correctly mirrors ordinary case-insensitive lookup, but collapses case-variant duplicates last-wins ([line 62]($HOME/ws/mlx-vlm/mlx_vlm/tests/test_session_cache.py:62)); installed Starlette returns the first occurrence ([datastructures.py:544]($HOME/ws/mlx-vlm/.venv/lib/python3.12/site-packages/starlette/datastructures.py:544)). **Fix:** use real `Headers`, define duplicate handling, and parameterize precedence, blanks and both streaming modes.

## Non-findings you checked

**P9**

- No ordinary header case-sensitivity or precedence implementation error. Whitespace-only strings fall through.
- `x-parent-session-id` is forwarded but deliberately absent from worker aliases; it cannot independently select the parent conversation.
- `user`, `safety_identifier`, opaque `metadata.user_id`, and request-ID headers do not select sessions under the default configuration. An explicitly reconfigured `_chat_id_header` can override that policy.
- The allowlist does **not** forward OpenWebUI email/name/role headers to the worker. Allowed session-header **values** remain unvalidated; their names alone cannot guarantee absence of PII.
- Anonymous matching still searches explicit sessions too, requiring two matching turn hashes. Explicit-ID disappearance can recover through that existing mechanism; conflicting explicit IDs cannot. This behavior predates the patch.