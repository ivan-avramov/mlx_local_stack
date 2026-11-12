# M77 (= M76 B0) — serve `tq4_attention` with MTP OFF — SPEC v1, 2026-11-11 (four-eyes light; C323 S22-P10, C325)

## Goal

M72 1.3 made the production TQ4 attention mode `tq4_attention: m72_v1 | m72_exact` (fork `mlx_vlm/tq4_attention.py`, `tq4_fast.py`)
reachable only together with MTP: mlx-serve requires `mtp_verify_scan: joint_v1` for a mode and `draft_kind: mtp` for `joint_v1`,
and the fork's `tq4_attention.require_environment` and `require_policy_stamps` require `joint_v1` on every full-attention module.
So a TurboQuant 4 entry with the mode and MTP OFF cannot be served; dropping the mode for OFF falls back to the pre-1.3 TQ4 path
(≈ 0.35× native16 prefill), which is not the OFF state of the configuration M76 certifies. Make the mode servable with the
drafter OFF — prefill `p2s` / `mma_prefill`, plain decode `d2` / `single_pass`, the native last layer through `fused_v1` prefill and
SDPA decode — while every MTP-ON configuration keeps exactly today's requirements and behaviour. Solving it means: a registry entry
with `kv_bits: 4`, `kv_quant_scheme: turboquant`, `attention_policy: fused_v1`, a `tq4_attention` mode, no `draft_kind` and no
`mtp_verify_scan` validates in mlx-serve, builds a worker argv with `--tq4-attention` and without `--mtp-verify-scan` /
`--draft-*`, loads in the fork with the mode applied, and decodes through the mode's routes; every configuration accepted or refused
today is accepted or refused exactly as today.

## Scope (files)

- Fork `../mlx-vlm`: `mlx_vlm/tq4_attention.py` (`require_environment`, `require_policy_stamps`), `mlx_vlm/server/generation.py`
  (`_resolve_tq4_mode_from_env`, `_apply_tq4_attention_from_env`, their call site in `_initialize_model`); tests.
- Fork `../mlx-serve`: `src/mlx_serve/config.py` (`_validate_tq4_attention`); tests. `process_manager.py` needs no change (it
  already passes `--tq4-attention` for a vision entry and `--mtp-verify-scan` / `--draft-kind` only when set) — tests pin it.
- Every changed definition in an upstream-shared fork file keeps or gains a `# Fork` marker (`dev/check_fork_markers.py`).

## Settled constraints

- (operator, C323 / C325) The fix is production code in both forks; failing tests first; four-eyes light; gates and push asks per
  repository; the stack gitlink bump with its companions follows (designer).
- (C319) `m72_exact` ON ≡ OFF is the property M76 certifies; this change must not alter any MTP-ON path.
- (AGENTS.md) Edit the parent forks, never the stack's `src/*`; mode absent ⇒ byte-identical behaviour.

## Interfaces

**The configured drafter state.** `configured_draft_kind` = the worker's effective configured drafter kind before any drafter is
loaded: `self.draft_kind_override or os.environ.get("MLX_VLM_DRAFT_KIND")` (the value `_initialize_model` already passes to
`_apply_mtp_verify_from_env`); "MTP ON" ⇔ it equals `"mtp"`; "OFF" ⇔ it is `None` or `""`. Any other kind (`suffix`, `dflash`,
`eagle3`) with a mode ⇒ refused (the mode's verify routes are MTP-scoped).

**Fork `tq4_attention.require_environment(mode, *, kv_bits, kv_quant_scheme, attention_policy, mtp_verify_scan, kv_quant_mode=None,
draft_kind=<sentinel>)`.**
- `mode` None ⇒ no-op (today).
- `draft_kind` omitted (the sentinel) ⇒ exactly today's checks (existing callers and tests unchanged).
- `draft_kind == "mtp"` ⇒ today's checks (including `mtp_verify_scan == "joint_v1"`).
- `draft_kind` None / `""` ⇒ today's checks except the scan check, which becomes: `mtp_verify_scan` must be `"per_query"`, `""` or
  None (no joint scan configured); `"joint_v1"` with no drafter ⇒ refused ("joint_v1 requires a drafter").
- any other `draft_kind` ⇒ refused.
- Refusals go through `_fail` (the module's existing error type and message style).

**Fork `tq4_attention.require_policy_stamps(model, *, draft_kind=<sentinel>)`.** Every full-attention module must carry the
`fused_v1` attention policy (always). Verify stamp: sentinel or `"mtp"` ⇒ `joint_v1` required on every module (today); None / `""`
⇒ no module may carry a verify stamp (`mtp_verify_policy` absent or None) — a stamp present with no drafter is refused.

**Fork `server/generation.py`.** `_resolve_tq4_mode_from_env(*, kv_bits, kv_quant_scheme, draft_kind)` passes `draft_kind` to
`require_environment`; `_apply_tq4_attention_from_env(model, mode, *, draft_kind)` passes it to `require_policy_stamps`;
`_initialize_model` computes `configured_draft_kind` once and passes the same value to the TQ4 calls and to
`_apply_mtp_verify_from_env` (today's argument). After the drafter is resolved and loaded (where `require_loaded_mtp_drafter` runs
today), when a mode is set: configured MTP ON with no loaded MTP drafter is already refused by `require_loaded_mtp_drafter` for
`joint_v1` (unchanged); configured OFF with a loaded drafter ⇒ refused (the invariant re-asserted after load).

**mlx-serve `ModelConfig._validate_tq4_attention`.** Today's checks except the scan check, which becomes: `draft_kind == "mtp"` ⇒
`mtp_verify_scan` must be `"joint_v1"` (today); `draft_kind == ""` ⇒ `mtp_verify_scan` must be `""` or `"per_query"` and
`mtp_verify_ab` false; any other `draft_kind` with a mode ⇒ refused. `_validate_attention_policy` / `_validate_mtp_verify_scan`
unchanged (`fused_v1` with kv_bits 4 already accepts any mode via `_tq4_kv`; `joint_v1` still requires `draft_kind: mtp`).

**Success path (traced):** entry `{type: vision, kv_bits: 4, kv_quant_scheme: turboquant, attention_policy: fused_v1,
tq4_attention: m72_exact}` (no draft keys, no scan) → mlx-serve validates → argv contains `--kv-bits 4 --kv-quant-scheme turboquant
--attention-policy fused_v1 --tq4-attention m72_exact`, no `--mtp-verify-scan`, no `--draft-kind`, no `--draft-model` → worker:
mode resolved with `draft_kind` None, scan `per_query` → `_apply_mtp_verify_from_env` returns None (no stamp) → stamps check: all
`fused_v1`, none verify-stamped → mode applied, self-test runs → a request prefills via `p2s` and decodes via `d2` (> 2,048 keys)
or `single_pass`; layer 63 `native:prefill` / `native:decode`; `fallback:*` 0.
**Failure path (traced):** the same entry plus `draft_kind: mtp` and no scan → mlx-serve refuses (today's message); if forced past
mlx-serve (env set directly), the worker's `require_environment` with `draft_kind "mtp"` refuses the missing `joint_v1`.

## Acceptance criteria

1. mlx-serve: the success entry validates and its argv is exactly as traced (with `m72_v1` too); refused: mode + `draft_kind: mtp`
   without `joint_v1`; mode + no drafter + `joint_v1` (refused by `_validate_mtp_verify_scan`, today); mode + no drafter +
   `mtp_verify_ab: true`; mode + `draft_kind: suffix` / `dflash` / `eagle3`; every configuration accepted or refused today keeps its
   outcome and message (existing tests unchanged).
2. Fork `require_environment` / `require_policy_stamps`: each row of the interface tables, both modes, including the sentinel
   (omitted `draft_kind` ⇒ today) and a stamp present with no drafter refused.
3. Fork load order (synthetic tiny Qwen3.5-family model, existing fixtures): with `MLX_VLM_TQ4_ATTENTION` set, no drafter and no scan,
   the worker initialises with the mode applied and no verify stamp; decode on a TQ4 cache moves `d2` (prefix > 2,048) / `single_pass`
   and never `fallback:*`; with a drafter configured and no scan it refuses; with a drafter configured and `joint_v1`, today's
   behaviour (existing tests unchanged); configured OFF with a loaded drafter refused.
4. Greedy identity on the synthetic model: TQ4 mode `m72_exact` MTP OFF (this change) emits the same tokens as TQ4 mode `m72_exact`
   MTP ON on the same prompt and cache configuration (temperature 0.0; a repeat control of each arm first).
5. Mode absent: byte-identical behaviour (existing suites pass unchanged); fork suite and mlx-serve suite pass or fail only as on the
   baseline; fork markers audit clean; formatters clean.
6. (Designer, real model, after Accept) a lean router serving the M76 XO arm loads to READY, a 32K and an 8K request complete with the
   route counters as traced, and greedy XO = greedy X MTP ON on the 1.3 A4 (c) prompts.

## Non-goals

Any MTP-ON behaviour change; continuous batching; other drafter kinds with the mode; stack code (the bump companions are the
designer's).

## Errata (change review, 2026-11-11)

- The two `server/generation.py` helpers take `draft_kind` with a sentinel default meaning MTP ON (as `require_environment` /
  `require_policy_stamps`), and `_initialize_model` omits it on the apply call when the configured kind is `mtp` (identical
  behaviour; existing fakes unchanged). The `--tq4-attention` help text states the OFF configuration.

## Open questions

None.
