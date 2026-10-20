# P405 — the server honours `--kv-quant-scheme` (plan v4, 2026-10-20)

Status: v4 after Cursor plan round 3 of 3 (DISAGREE T13 T14 T15; T10–T12 and round-1 T4 / T9 confirmed resolved) — escalated
to the operator (lead rec: accept v4 without a fourth round). T15 applied; T13 / T14 are latent defects outside every served
configuration, recorded as P407 / P408 with their own proposals (not P405 scope). v3 resolved round 2, v2 round 1. F1 / F2 and T1–T5 are implemented red-first on `p405-kv-scheme` (`ad36e941` red, `0163f212` green). Defect, mechanism and affected entries: `docs/open-questions.md` P405.

## 1. Decision (C189, operator 2026-10-20)

"let's fix this … rerun if needed": fix the precedence so the registry's `kv_quant_scheme: turboquant` engages; re-measure
whatever the codec change invalidates. Not chosen: relabel the six entries `uniform` (no serving change).

Lead counterpoint (recorded): fixing the precedence changes the served KV codec of two main picks
(`Qwen3.8-27B-mlx-uniform-4bit`, B 2nd; `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, B 4th — both called "main" below) whose certifications since 2026-08-23 describe affine
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

F3. The P369 harness (`dev/p369_phase2/worker.py`) fails closed on the served codec (round 1 T4, round 2 T10):
`served_state` records EVERY resolved `ResponseGenerator` KV field (`kv_bits`, `kv_key_bits`, `kv_value_bits`,
`kv_key_scheme`, `kv_value_scheme`, `kv_quant_scheme`, `kv_group_size`, `quantized_kv_start`) plus `TQ_KV_QUANT_MODE` (pure module
`dev/p369_phase2/kvmanifest.py`);
`assert_served` requires each to equal what the argv resolves to (the CLI's own defaults where a flag is absent; native when
bits are absent / 0), as the P400 perf probe does for bits / scheme (`ce04439b`, extended to the same field set). The smoke
gate requires an EXACT leaf manifest, ordered by layer path (not aggregate class counts): the expected entry per attention
layer — class, and for TurboQuant leaves the key / value bit widths and the quantization mode — is derived from the model
cache template (`make_cache()`), the argv's KV flags, and the SERVED path's policy (`generate/common.py`
`maybe_quantize_kv_cache`: the TurboQuant branch keeps the last top-level cache entry native when there are more than two;
the uniform branch converts every KV layer; `models/cache.py` `should_quantize_kv_layer` is APC's, not the served path's).
Only `quantized_kv_start` 0 is modelled (every registry entry); anything else is refused. Any `QuantizedKVCache` leaf under
`turboquant`, a missing / extra leaf, a wrong width (so a lost split key / value width, P407, fails closed), mode or
exempt-layer placement fails.

Rejected alternative: a `None` default for `kv_quant_scheme` with an env fallback in `app.py`. Narrower — leaves
`--vision-cache-size` (also frozen: CLI writes `MLX_VLM_VISION_CACHE_SIZE` after import) and the `replace` restore point stale.

Audit of every `RuntimeConfig.from_env` knob against the CLI's env writes (`cli.py` 743–811):

| knob | CLI writes env after import | import-time default | effect today |
|---|---|---|---|
| `kv_quant_scheme` | yes | `"uniform"` (truthy) | **ignored** (P405) |
| `vision_cache_size` | yes | `20` | **ignored** (latent; the stack never sets it) |
| `kv_bits`, `kv_group_size`, `quantized_kv_start` | yes | `None` | correct via `app.py` env fallbacks |
| `kv_key_bits`, `kv_value_bits`, `kv_key_scheme`, `kv_value_scheme` | yes | `None` | reach the generator via fallbacks, but the cached-session path does not forward them (P407, latent: no registry entry sets them) |
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
- T6. F3: `assert_served` refuses any resolved KV field that differs from the argv (the P405 shape: argv TurboQuant, served
  uniform; and each other field singly); the manifest check refuses, by layer path, a mixed census (TurboQuant + affine), a
  missing / extra leaf, a wrong key or value width, a wrong mode, a wrong start, and a misplaced exempt layer.

## 5. Rollout and re-measurement

R1. Fork: suites ×2 + 8 audits; Cursor code review (≤ 3 rounds); merge `p400-tq-width2` then `p405-kv-scheme` into fork
main (push approval). Stack: the submodule bump lands on a CANDIDATE branch in its own stack worktree
(`$STACK_WORKDIR/worktrees/stack-p405`, own venv via `scripts/bootstrap_machine.sh`); every R2–R6 run is launched from that
worktree (driver and router registry paths match, M50). Stack `main` — and so the daily driver — keeps the pre-fix submodule
until R6 passes; the promotion commit bumps `main` and updates the CERTIFIED notes together. (Alternative, operator's call:
accept TurboQuant serving on `main` during the window, both main picks marked PROVISIONAL.)

R2. Live engagement (GPU, inside R3's smoke): F3's exact leaf manifest and served-codec assertion pass for
`Qwen3.8-27B-mlx-uniform-4bit`, and the `tq_norm` positive fires.

R3. MTP exactness on the chosen codec for EVERY affected MTP-enabled main pick (round 2 T11): P369 phase 2 (smoke, then
the full run on a reviewed head; acceptance = `docs/specs/p369-phase2-run-plan.md` v9 — E1c every cell PASS incl. C1 / C2,
E2 PASS, E7a / E7b reported) on P400 + P401 + P405 for `Qwen3.8-27B-mlx-uniform-4bit` (replaces the planned affine run) and
for `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (added to the harness `PICKS` with its registry tuple: `--draft-kind mtp`, its
extracted drafter, `verify_policy=None` — the runtime form of the default per-query path, as for
`Qwen3.8-27B-mlx-uniform-4bit` — plus a separate check that its argv selects / defaults to `per_query`; round 3 T15). Run on TurboQuant first; if R6 chooses affine for a pick, its R3 reruns on
affine. M63 (MTP-ON tg1 arm) waits for R3 + R6 and runs on the chosen codec.

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

R8. Evidence classification (round 1 T9, round 2 T12), never by date alone: a resolved-codec log line (F2) or a leaf manifest
(F3) is authoritative where present. Otherwise each result row / doc claim for the six entries is classified from its
recorded launcher, worker argv and submodule revision: `affine` = router- or CLI-served `--kv-quant-scheme turboquant` on a
stack revision from bump `111bb538` up to, NOT including, the first stack bump containing P405; `turboquant` = such serving
before `111bb538` or from the P405 bump on, or a direct-generation path that passed the scheme explicitly; `unknown` = no
authoritative evidence and no unambiguous bounded revision.
Annotated in docs; affine, TurboQuant and unknown rows are never pooled. `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`
(`kv_bits: 0`) is unaffected.

## 6. Out of scope (latent; own proposals)

- P407 (round 3 T13): `_process_cached_request` forwards base bits / group / scheme / start but not the split key / value
  bits and schemes; an asymmetric launch would serve symmetric widths on the session path. No registry entry sets split
  fields; F3's manifest check fails closed if one ever does.
- P408 (round 3 T14): the APC disk namespace does not fingerprint split schemes or `TQ_KV_QUANT_MODE`, so snapshots could
  cross modes. APC is disabled stack-wide (`APC_ENABLED` absent, AGENTS.md); the base scheme IS fingerprinted, so the
  affine → TurboQuant transition is separated.

## 7. Acceptance

T1–T6 red on `ce04439b` (T1–T4 behavioural; T5 / T6 helper absent or behavioural as stated), green on the fix; suites ×2
identical + 8 audits; R2 live; promotion to stack `main` only after R6 (or the operator's R1 alternative).
