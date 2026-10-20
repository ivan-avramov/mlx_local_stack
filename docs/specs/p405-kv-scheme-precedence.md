# P405 — the server honours `--kv-quant-scheme` (plan v2, 2026-10-20)

Status: v2 after Cursor plan round 1 of 3 (DISAGREE T1 T2 T4 T5 T6 T7; all nine findings accepted —
`docs/reviews/p405/plan-round1.*`). Defect, mechanism and affected entries: `docs/open-questions.md` P405.

## 1. Decision (C189, operator 2026-10-20)

"let's fix this … rerun if needed": fix the precedence so the registry's `kv_quant_scheme: turboquant` engages; re-measure
whatever the codec change invalidates. Not chosen: relabel the six entries `uniform` (no serving change).

Lead counterpoint (recorded): fixing the precedence changes the served KV codec of two main picks
(`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, `Qwen3.8-27B-mlx-uniform-4bit`) whose certifications since 2026-08-23 describe affine
4-bit KV. No TurboQuant serving reaches stack `main` (the daily driver) before they re-certify (§5 R1, plan round 1 T5).

## 2. Defect window

The stack has served affine KV for the six entries since its submodule bump `111bb538` (2026-08-23, first bump containing the
fork's upstream merge `83e2aadb`). Measurements before it ran TurboQuant.

## 3. Fork change (branch `p405-kv-scheme`, off `p400-tq-width2` `ce04439b`; merges after P400)

F1. `mlx_vlm/server/cli.py` `main()`: immediately before `uvicorn.run`, after every `os.environ` write,
`runtime.config = RuntimeConfig.from_env()` (`# Fork (P405)`). Rebuilds every knob AND `_env_defaults` (the
`/v1/settings` `op=replace` restore point) from the final environment. With `--reload`, uvicorn's child re-imports with that
environment, so its import-time `from_env` is already correct.

F2. The effective codec is logged where it is resolved: `get_cached_model` logs one line with a unique prefix
(`KV cache resolved:` bits, key/value bits and schemes, scheme, group size, start, `TQ_KV_QUANT_MODE`) from exactly the values
it passes to `ResponseGenerator`. The `lifespan` line that reads `KV_BITS` / `KV_QUANT_SCHEME` from the environment
(`app.py` ~437–440 — the line that printed `scheme=turboquant` while affine was served) is removed.

F3. The P369 harness (`dev/p369_phase2/worker.py`) fails closed on the served codec: `served_state` records the
`ResponseGenerator`'s resolved KV fields; `assert_served` requires them to equal the argv's (`--kv-bits`, `--kv-quant-scheme`;
native when bits are absent / 0), as the P400 perf probe now does (`ce04439b`). The smoke gate requires an EXACT leaf
manifest (round 1 T4): the expected class per attention layer is derived from the model config's layer types, the argv's
`--quantized-kv-start`, and the documented last-full-attention-layer exemption (`models/cache.py` ~17–23); for
`kv_quant_scheme: turboquant` every eligible leaf is TurboQuant, the exempt layer native, and any `QuantizedKVCache` leaf is a
failure (a census containing ANY TurboQuant leaf no longer suffices).

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

## 4. Tests (red first, on `ce04439b`)

Fixture: a fresh import-time `RuntimeConfig.from_env()` built with EVERY env var of the §3 table cleared (what the server
package import sees; no ambient value can mask a failure), `cli.uvicorn.run` patched, `sys.argv` set; env restored at teardown.

- T1. `cli.main` with `--kv-bits 4 --kv-quant-scheme turboquant` → `runtime.config.kv_quant_scheme == "turboquant"`.
- T2. Parametrized over every §3 row the CLI writes: the CLI value lands in `runtime.config`. ALL rows are red today
  (round 1 T3: no CLI-written field reaches the already-built config; the `None` rows only work through downstream env
  fallbacks).
- T3. The load path (`ResponseGenerator` patched to capture kwargs) receives `kv_quant_scheme="turboquant"` after `cli.main`.
- T4. `PATCH /v1/settings` (the registered method): first set `kv_quant_scheme` to `uniform`, then
  `{"op": "replace", "values": {}}` → the scheme is restored to the CLI's `turboquant`.
- T5. F2: the `KV cache resolved:` line exists and equals T3's captured constructor arguments; the env-derived `lifespan` line
  is gone (red today: helper absent).
- T6. F3: `assert_served` refuses a served codec that differs from the argv (the P405 shape: argv TurboQuant, served
  uniform); the smoke gate refuses a mixed census (TurboQuant + affine leaves), a missing TurboQuant leaf, and a wrong
  exempt-layer class.

## 5. Rollout and re-measurement

R1. Fork: suites ×2 + 8 audits; Cursor code review (≤ 3 rounds); merge `p400-tq-width2` then `p405-kv-scheme` into fork
main (push approval). Stack: the submodule bump lands on a CANDIDATE branch in its own stack worktree
(`$STACK_WORKDIR/worktrees/stack-p405`, own venv via `scripts/bootstrap_machine.sh`); every R2–R6 run is launched from that
worktree (driver and router registry paths match, M50). Stack `main` — and so the daily driver — keeps the pre-fix submodule
until R6 passes; the promotion commit bumps `main` and updates the CERTIFIED notes together. (Alternative, operator's call:
accept TurboQuant serving on `main` during the window, both main picks marked PROVISIONAL.)

R2. Live engagement (GPU, inside R3's smoke): F3's exact leaf manifest and served-codec assertion pass for
`Qwen3.8-27B-mlx-uniform-4bit`, and the `tq_norm` positive fires.

R3. `Qwen3.8-27B-mlx-uniform-4bit` P369 phase 2 on P400 + P401 + P405 (smoke, then the full run on a reviewed head).
Replaces the planned affine run.

R4. P404 re-measured: the P400 ABBA probe for `Qwen3.8-27B-mlx-uniform-4bit` with P405 in BOTH arms (arm A = `p369-mtp` +
the P405 commit cherry-picked on a dev branch; arm B = P400 + P401 + P405), so only the verifier change varies, against the
C188 bounds. The −3.93 % affine result is superseded; the P404 decision waits for this number.

R5. Codec-only performance (round 1 T6): on the final fork code (P400 + P401 + P405), ABBA with arm A = affine
(`kv_quant_scheme: uniform` overlay) and arm B = TurboQuant, deployed MTP-ON tuple, both affected main picks: (a) 8K prompt +
256 decoded tokens, 3 warmup + 5 measured per leg — decode tok/s, prefill tok/s, decode-phase peak; (b) a 256K prompt
(quiet box) + 64 decoded tokens, 0 warmup + 2 measured per leg — prefill tok/s, prefill peak (`mx.get_peak_memory`), decode
tok/s. Descriptive (medians + per-arm ranges); an input to the codec decision, not a gate. ≥ 10 min idle between legs, power
logged per leg.

R6. Quality (round 1 T7): for each affected main pick, MATCHED affine and TurboQuant arms on identical final code, model,
seeds and conditions (paired schedules via `rowschema.sample_seed`) on every axis that supports the pick's current status
(enumerated per pick from README / campaign-results in R6's own plan, with run sizes and wall-clock). Decision rule = the
lossy-lever rules: two-stage cluster bootstrap per axis, Holm across axes; affine → TurboQuant is the lever (the certified
state is affine). TurboQuant ships if no axis shows a loss and, on a wash, the observed loss bound is ≤ 10 pp (C172 / C173);
otherwise "loss not ruled out above X pp" → the operator chooses the codec (affine = `kv_quant_scheme: uniform`, a registry
change). The M6d predictor re-certification (MTP-ON) follows on the chosen codec. R6 gets its own plan, Cursor review and
operator GPU go.

R7. Operational qualification of all six entries (round 1 T8): on TurboQuant, load + 256K prefill + 32-token decode, recording
the prefill peak against the registry's recorded peak and the ≈ 48 GB guidance. The four non-pick entries that fail, or are
not run, get `kv_quant_scheme: uniform` at promotion (their evidence is affine) — operator call per entry.

R8. Evidence classification (round 1 T9), never by date alone: each result row / doc claim for the six entries is classified
from its recorded launcher, worker argv and (where present) runtime / leaf census as `affine` (router- or CLI-served
`--kv-quant-scheme turboquant` on a fork containing `83e2aadb`, i.e. stack bump `111bb538` or later), `turboquant`
(direct-generation paths that passed the scheme explicitly, or pre-`111bb538` serving) or `unknown` (no launch evidence).
Annotated in docs; affine, TurboQuant and unknown rows are never pooled. `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`
(`kv_bits: 0`) is unaffected.

## 6. Acceptance

T1–T6 red on `ce04439b` (T1–T4 behavioural; T5 / T6 helper absent or behavioural as stated), green on the fix; suites ×2
identical + 8 audits; R2 live; promotion to stack `main` only after R6 (or the operator's R1 alternative).
