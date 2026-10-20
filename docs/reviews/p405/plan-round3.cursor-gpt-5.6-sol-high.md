# P405 plan review — round 3 of 3 (Cursor gpt-5.6-sol-high, `--mode ask`), plan v3, fork `p405-kv-scheme` `0163f212`

Resolution check:
- T10: Resolved.
- T11: Resolved.
- T12: Resolved.
- Round-1 T4: Resolved.
- Round-1 T9: Resolved.

F1’s replacement mechanism is otherwise sound: no stale alias or pre-serve consumer defeats it, reload children inherit the finalized environment, and T1–T5 fail pre-fix for the intended reasons.

T13 — HIGH — The knob audit misses split-KV loss on cached-session generation. `ResponseGenerator` stores split bits/schemes, but `_process_cached_request` forwards only base bits, group, scheme and start. A CLI request for 3-bit keys/4-bit values can therefore serve default 4/4 on the session path while T2, T3 and `served_state` all report 3/4. Add split-field forwarding and an end-to-end asymmetric CLI/session regression test; update the audit from “correct via fallback” accordingly.

T14 — HIGH — APC’s disk namespace does not fingerprint split key/value schemes or `TQ_KV_QUANT_MODE`, while exact APC snapshots retain packed cache type and mode. A `prod` launch can write a packed snapshot that a later `mse` launch restores from the same namespace; F3 cannot detect this because P369 requires APC inactive. Include effective split schemes and quantization mode in the APC namespace/fingerprint, test namespace separation and add an APC-enabled restoration check. The immediate uniform→TurboQuant transition is separated by the existing base-scheme fingerprint, but the plan’s all-field guarantee is not.

T15 — HIGH — R3 specifies Qwen3.6’s harness `verify_policy` as `"per_query"`, but the runtime representation for the default per-query path is `None`: `_apply_mtp_verify_from_env` creates no policy object, `served_state` reports `None`, and the existing Qwen3.8 per-query pick uses `verify_policy=None`. Encoding `"per_query"` in `PICKS` makes the conformance check fail before exactness runs. Store `verify_policy=None` and separately assert that argv selects/defaults to `per_query`.

VERDICT: DISAGREE T13 T14 T15
