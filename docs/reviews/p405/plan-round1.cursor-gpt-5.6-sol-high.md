# P405 plan review — round 1 of 3 (Cursor gpt-5.6-sol-high, `--mode ask`), plan v1, fork `p400-tq-width2` `78c9f99d`

F1 is the right minimal fix. No other `RuntimeConfig` snapshot or pre-serve reader defeats it; reload children inherit the finalized environment, and APC is built later from the refreshed config. The knob table is complete for `RuntimeConfig`.

T1 — BLOCKER — T4 uses the wrong HTTP method. `/v1/settings` is registered with `PATCH`, not `POST` (`app.py:1281`). The proposed test receives 405 both before and after F1, so it is red for the wrong reason and never greens. Change T4 to `PATCH`, first mutate the scheme to `uniform`, then send `{"op":"replace","values":{}}` and assert restoration to `turboquant`.

T2 — HIGH — T5 can already pass while the defect remains. `lifespan` currently logs `KV_QUANT_SCHEME` directly from the environment after loading (`app.py:437–440`), producing `scheme=turboquant` even when `ResponseGenerator` received stale `uniform`. Change F2 to emit a uniquely identifiable log inside `get_cached_model` from the same resolved values passed to `ResponseGenerator`; T5 must require that new message and cross-check the captured constructor arguments. Remove or reword the existing env-derived line.

T3 — MEDIUM — T2’s expected red set is incorrect. Today no CLI-written field lands in the already-created `runtime.config`; the `None` fields only work through downstream environment fallbacks. Therefore `kv_bits`, split bits/schemes, group size, start, max size and draft settings are red too—not green guards. Update the plan accordingly and clear all relevant environment variables before each case so ambient values cannot mask the failure.

T4 — HIGH — R2 does not fail closed on partial engagement. The existing smoke gate accepts a census containing any TurboQuant leaf, even if affine leaves coexist; `tq_norm` only proves one TurboQuant state participates in hashing. Require an exact live manifest: resolved `ResponseGenerator` settings, expected counts/classes for all quantization-eligible leaves, no `QuantizedKVCache` leaves, expected key/value widths, mode and quantization start, while allowing the intentionally unquantized final layer.

T5 — HIGH — The rollout promotes changed serving numerics before re-certification. A `PROVISIONAL` comment does not prevent either main pick from serving TurboQuant between R1 and R6. Build a candidate stack bump and complete R2–R6 before production promotion, or require an explicit operator decision accepting that exposure window.

T6 — HIGH — P405’s performance impact is not measured. R4 correctly puts P405 in both arms to isolate P400, but that cancels the affine→TurboQuant change. R3 is primarily conformance, and R5 measures only prefill memory. Add a codec-only ABBA on fixed P400+P401 code for both affected main picks, measuring prefill throughput, decode throughput and peak memory at representative short and 256K contexts.

T7 — HIGH — R6 cannot attribute or statistically gate codec quality. It compares final P400+P401+P405 results against historical affine evidence, so any delta is confounded, and a ±5-point point-estimate rule provides no uncertainty bound. Require matched affine-versus-TurboQuant arms on identical final code, models, seeds and conditions, with pre-registered per-axis non-inferiority such as a lower confidence bound of −5 pp. Enumerate the axes supporting each pick’s current status.

T8 — MEDIUM — Four affected on-demand entries receive no operational qualification. Deferring comparative quality is reasonable, but they remain selectable with 256K caps and could encounter a codec-specific load, decode or memory failure. Require at least a load–256K-prefill–short-decode peak gate for all six, or keep the four explicitly unavailable/affine until tested.

T9 — MEDIUM — Date-wide evidence relabelling can create false provenance. P405 affects the server CLI path; a post-2026-08-23 direct generation run that explicitly supplied TurboQuant genuinely used it, while an artifact lacking launch evidence is unknown. Classify rows from recorded launcher, argv and runtime census as `affine`, `turboquant` or `unknown`; do not relabel solely by date.

VERDICT: DISAGREE T1 T2 T4 T5 T6 T7
