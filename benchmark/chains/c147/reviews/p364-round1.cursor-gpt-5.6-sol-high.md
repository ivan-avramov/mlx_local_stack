D1 — HIGH — `docs/specs/p364-datefreeze.md:21-31,50-52`  
Failure: Replacing `"Today's date is now: …"` retains the extra midnight system message. A reference row without that message and a candidate row with it do not have identical prompts, despite sharing `prompt_date`; merely listing `prompt_date_changed` permits invalid pairing.  
Fix: At the structured context hook, replace the initial date but remove the entire midnight update message. Otherwise exclude every changed row from pairing.

D2 — HIGH — `docs/specs/p364-datefreeze.md:25-30`  
Failure: One first-request receipt does not prove every request was masked. Shared append-only receipts can also satisfy later items using stale records. `body_sha256_after` is self-attestation, not request correlation.  
Fix: Use a unique per-item receipt, recording `sessionID`, request sequence/kind, counts and hashes. Reconcile exactly against `requests_observed`; every request must contain and mask the expected date. No match must throw before transmission.

D3 — HIGH — `docs/specs/p364-datefreeze.md:13-25,40-45`  
Failure: Binary inspection confirms `http.request` covers the shared HTTP path for primary, compaction, generate, title and subagent sessions; SSE does not bypass it. WebSocket transport does bypass it through `experimental.ws.*`. Rebuilding JSON can also change serialization and retain an incorrect `Content-Length`; careless construction can lose authorization and `x-session-*` headers.  
Fix: Prefer the structured `context`/`compaction`/`generate`/`title` hooks, then retain real-server wire capture as verification. This is transport-neutral and preserves normal serialization, prompt-cache keys and headers. If retaining `http.request`, enforce HTTP transport, preserve all Request metadata, remove/recompute `Content-Length`, and test/refuse WebSocket routes.

D4 — MEDIUM — `docs/specs/p364-datefreeze.md:26,34-35`; `benchmark/bench/provenance.py:1910-1919`  
Failure: Writing receipts inside `OPENCODE_CONFIG_DIR` conflicts with M50’s exact directory inventory and mixes mutable evidence with hashed configuration. Post-item verification would reject the new file unless the guard is weakened.  
Fix: Store receipts under a unique run/item evidence path outside the config directory. M50 should permit only `datefreeze.js` there, pinned and activation-proven like the existing plugins.

D5 — MEDIUM — `docs/specs/p364-datefreeze.md:27-33`; `docs/specs/p311-identity-split.md:59-75`  
Failure: P311 deliberately keeps `prompt_date` in the row pairing key and outside the enumerated generation composite. Adding it to both is redundant and silently changes that contract. Also, defaulting each new chain to its current date would defeat reference reuse.  
Fix: Let the plugin SHA produce the one new tg1 epoch; retain the frozen date as row `prompt_date` plus immutable chain metadata imported from the reference epoch. If it enters the composite instead, explicitly amend P311 and its exact-field tests.

D6 — MEDIUM — `docs/specs/p364-datefreeze.md:21-48`  
Failure: The proposed tests do not cover hermetic env propagation, plugin activation, format drift before wire transmission, every multi-turn request, header/cache preservation, WebSocket refusal, second-item M50 behavior, receipt corruption, or opencode upgrades.  
Fix: Add real pinned-binary tests for those cases. Inject the required env value through `_opencode_env`, validate it both in probe and plugin setup, include the plugin in `GENERATION_DATA` and policy identity, and make hook/date-format revalidation a standing opencode-release check alongside C154.

The core objective is sound, and HTTP interception is valid for the current HTTP/SSE carrier. The safer design is structured prompt transformation plus final wire-capture verification. C172’s wash policy is unaffected.

VERDICT: AGREE WITH CHANGES D1 D2 D3 D4 D5 D6
