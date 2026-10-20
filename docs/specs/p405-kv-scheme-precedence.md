# P405 — the server honours `--kv-quant-scheme` (plan v1, 2026-10-20)

Status: DRAFT for Cursor plan review (round 1 of 3). Defect, mechanism and affected entries: `docs/open-questions.md` P405.

## 1. Decision (C189, operator 2026-10-20)

"let's fix this … rerun if needed": fix the precedence so the registry's `kv_quant_scheme: turboquant` engages; re-measure
whatever the codec change invalidates. Not chosen: relabel the six entries `uniform` (no serving change).

Lead counterpoint (recorded): fixing the precedence changes the served KV codec of two main picks
(`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, `Qwen3.8-27B-mlx-uniform-4bit`) whose certifications since 2026-08-23 describe affine
4-bit KV. They are PROVISIONAL from the bump until they re-certify on TurboQuant (§5).

## 2. Defect window

The stack has served affine KV for the six entries since its submodule bump `111bb538` (2026-08-23, first bump containing the
fork's upstream merge `83e2aadb`). Measurements before it ran TurboQuant.

## 3. Fork change (branch `p405-kv-scheme`, off `p400-tq-width2` `78c9f99d`; merges after P400)

F1. `mlx_vlm/server/cli.py` `main()`: immediately before `uvicorn.run`, after every `os.environ` write,
`runtime.config = RuntimeConfig.from_env()` (`# Fork (P405)`). Rebuilds every knob AND `_env_defaults` (the
`/v1/settings` `op=replace` restore point) from the final environment. With `--reload`, uvicorn's child re-imports with that
environment, so its import-time `from_env` is already correct.

F2. The model-load path in `app.py` logs the resolved KV configuration it passes to `ResponseGenerator` (bits, key/value
bits, scheme, group size, start) — the log states the effective codec, not the CLI argument.

Rejected alternative: a `None` default for `kv_quant_scheme` with an env fallback in `app.py`. Narrower — leaves
`--vision-cache-size` (also frozen: CLI writes `MLX_VLM_VISION_CACHE_SIZE` after import) and the `replace` restore point stale.

Audit of every `RuntimeConfig.from_env` knob against the CLI's env writes (`cli.py` 743–811):

| knob | CLI writes env after import | import-time default | effect today |
|---|---|---|---|
| `kv_quant_scheme` | yes | `"uniform"` (truthy) | **ignored** (P405) |
| `vision_cache_size` | yes | `20` | **ignored** (latent; the stack never sets it) |
| `kv_bits`, `kv_key_bits`, `kv_value_bits`, `kv_key_scheme`, `kv_value_scheme`, `kv_group_size`, `quantized_kv_start` | yes | `None` | correct via `app.py` env fallbacks |
| `max_kv_size` | yes | `None` | correct via `generation.py` fallback |
| `spec_draft_model`, `spec_draft_kind` | yes | `None` | correct via `ResponseGenerator` env fallback |
| `apc_*`, `token_queue_timeout` | no | — | unaffected |

Every row's `/v1/settings` `replace` restore point is the import-time value today; F1 fixes all of them.

## 4. Tests (red first, on `78c9f99d`, behavioural)

Fixture: a fresh import-time `RuntimeConfig.from_env()` built with the KV / vision env vars absent (what the server package
import sees), `cli.uvicorn.run` patched, `sys.argv` set; env restored at teardown.

- T1. `cli.main` with `--kv-bits 4 --kv-quant-scheme turboquant` → `runtime.config.kv_quant_scheme == "turboquant"`.
- T2. Parametrized over every row of the §3 table that the CLI writes: the CLI value lands in `runtime.config` (red for
  `kv_quant_scheme` and `vision_cache_size`; green guards for the rest).
- T3. The load path (`ResponseGenerator` patched to capture kwargs) receives `kv_quant_scheme="turboquant"` after `cli.main`.
- T4. `POST /v1/settings` with `op=replace` restores the CLI's scheme, not `"uniform"`.
- T5. F2: the load log line carries the resolved scheme (`caplog`).

## 5. Rollout and re-measurement

R1. Fork: suites ×2 + 8 audits; Cursor code review (≤ 3 rounds); merge `p400-tq-width2` then `p405-kv-scheme` into fork
main (push approval); stack submodule bump (push approval) in the same commit that marks both main picks'
`generation_defaults` `PROVISIONAL (P405 codec change)` until R6 re-certifies them. R2–R4 run before the merge from the
worktree as the fork root (as the P369 phase-2 runs already do).

R2. Live engagement check (GPU, part of R3's smoke): the leaf census for `Qwen3.8-27B-mlx-uniform-4bit` shows
`TurboQuantKVCache` leaves and the `tq_norm` smoke positive fires.

R3. `Qwen3.8-27B-mlx-uniform-4bit` P369 phase 2 on P400 + P405 (smoke, then the full run on a reviewed head). Replaces the
planned affine run.

R4. P404 re-measured: the P400 ABBA probe for `Qwen3.8-27B-mlx-uniform-4bit` with P405 in BOTH arms (arm A = `p369-mtp` +
the P405 commit cherry-picked on a dev branch; arm B = P400 + P405), so only the verifier change varies. The −3.93 % affine
result is superseded; the P404 decision waits for this number.

R5. Capacity: the 256K prefill peak (`mx.get_peak_memory`, quiet box) for both main picks on TurboQuant, against the
registry's recorded peaks.

R6. M6d re-certification of both main picks on the new bump (its own plan, Cursor review, operator GPU go): P400 + P401 +
P405 together. If a pick's TurboQuant certification is worse than its affine evidence beyond ±5 pp on any axis, the codec
choice goes to the operator (affine = `kv_quant_scheme: uniform`, a registry change).

R7. Evidence labels: every result row / doc claim for the six entries dated 2026-08-23 or later that says TurboQuant is
annotated "served affine 4-bit KV (P405)"; affine and TurboQuant rows are never pooled. The four non-pick entries are
re-measured only if they return to contention. `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (`kv_bits: 0`) is unaffected.

## 6. Acceptance

T1–T5 red on `78c9f99d` (T1–T4 behavioural, T5 helper absent), green on the fix; suites ×2 identical + 8 audits; R2 live.
