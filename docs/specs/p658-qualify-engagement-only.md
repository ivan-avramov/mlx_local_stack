# P658 (a) — fork `qualify --kv-arm --predictor on --engagement-only` + P656 item 6 — SPEC v1, 2026-11-05 (four-eyes light; C296 (2))

## Goal

P475 stage 1 measures `Qwen3.8-27B-mlx-uniform-4bit` in six KV-format arms. Five are served MTP-ON (N16, AF8, TQ8, AF4, TQ4), but each
arm's live-cache engagement proof (the fork's `dev/p369_phase2/qualify.py --kv-arm`) is taken `--predictor off`. The served MTP-ON
path, the target cache built for speculation plus the drafter's own cache, is therefore never observed on N16 / AF8 / TQ8 / AF4.
`qualify` refuses `--kv-arm --predictor on` with a non-empty KV delta ("an MTP-ON KV arm is uncertified"). Its MTP-ON path also
requires a P369 full-run summary and binds the served argv to the certified one (C199), and no such summary exists on this box.
Engagement is a different question from certification. Solving it means: `qualify`, when explicitly asked with
`--engagement-only`, serves an arm registry's MTP-ON entry exactly as committed. It runs today's one qualification request
unchanged and checks the target cache's per-layer manifest against the arm's expected manifest, as today. It also checks the
drafter's cache manifest against the drafter's own template, and records the result as engagement evidence that certifies nothing.
Separately, the quiet-box scan stops refusing the P475 orchestrator that launched it. Without the new flag, behaviour is unchanged.

## Scope

Fork `../mlx-vlm`, `dev/p369_phase2/` only: `qualify.py`, `worker.py` (the qualification request only), `orchestrate.py`
(`LAUNCHER_MODULES` only); new tests under `mlx_vlm/tests/`. Production `mlx_vlm/` outside `mlx_vlm/tests/` byte-identical.

## Settled constraints

- C296 (2) (operator): engagement-only, `dev/` only, four-eyes light; fork gate `dev/ci.py`; the fork push needs its own ask.
- C218 / C230 / C203: the golden fixture, the 16 accepted states and `classify_kv_arm` are unchanged.
- P452 F2 (code round 1, accepted): only named launcher modules are exempt as refused ancestors; any other refused ancestor still
  refuses. P656 item 6 is met within that rule (designer, this spec): `bench.p475_kv` joins `LAUNCHER_MODULES`.
- Test-first; full registry names; no push without approval.

## Interfaces

1. **CLI.** `qualify.py … --kv-arm --predictor on --engagement-only`. `--engagement-only` without both `--kv-arm` and `--predictor on`
   refuses before the lock: `refused: ['--engagement-only needs --kv-arm --predictor on']`. With `--engagement-only`, a
   `--p369-summary` argument refuses: `refused: ['--engagement-only takes no --p369-summary']`.
2. **Gate** (`kv_arm_gate` or its caller). Under `--engagement-only`, everything `--kv-arm` checks today is kept: one `--entry`, a
   P475 pick, `classify_kv_arm` not `None`. The entry must be served MTP-ON by the snapshot (not in `classify_kv_arm`'s `off` set);
   otherwise it refuses with today's message, "the registry serves … MTP-OFF (no overlay is built)". The refusal of a non-empty
   delta under `--predictor on` does not apply. Any delta that `classify_kv_arm` accepts is served, including the empty one (TQ4).
3. **C199 gate.** Under `--engagement-only`, `entry_problems` does not require a P369 summary for the entry. No certified argv is
   read, and `argv_binding_problems` is not applied. The served argv is still bound before and after the job by today's
   `command_problems(expected, cmd, …)` (mlx-serve's own `_build_command` on the committed arm registry vs `expected_config`) and
   `binding_problems`. The arm is `served_on`, with no overlay.
4. **Request.** The worker's qualification request is today's: the same sized prompt, chunks, peaks, rates and boundary. When the
   job carries `drafter_manifest: true` (set only under `--engagement-only`), the record gains
   `drafter_manifest = {observed: kvmanifest.manifest(rg.draft_model._cache or []), template:
   kvmanifest.manifest(rg.draft_model.make_cache())}`. It is read after the response completes and before the session is released.
   Without the job field, the record is byte-for-byte today's.
5. **Judging.** `request_problems` is unchanged (target manifest vs the arm's expected manifest, prealloc capacities, the attention
   rule, `drafter_live_checks`, …). Under `--engagement-only`, the entry's problems additionally include
   `kvmanifest.drafter_problems(observed, template)` (K3: the drafter cache never quantized, no continuous-batching leaves), plus
   `"no drafter cache manifest"` when `drafter_manifest` is absent, or its `observed` or `template` is empty or not a list.
6. **Report.** Under `--engagement-only`, `report.json` gains top-level `engagement_only: true` and `certifies: false`. Each entry's
   `reference` is `None` (no capacity comparison is made). `kv_arm` is recorded as today. Each entry's final state carries
   `drafter_manifest` when recorded. Status rules are unchanged: COMPLETED only with no problems.
7. **Launcher.** `orchestrate.LAUNCHER_MODULES` = `("bench.p426_leg", "bench.p426_wave1", "bench.p475_kv")`. An ancestor
   `python -m bench.p475_kv …` is not a foreign process; a non-ancestor `bench.p475_kv`, or any other `bench.*` ancestor, still
   refuses (P452 F2).

**Success path (TQ8 ON):** the arm registry has `kv_bits: 8`, `kv_quant_scheme: turboquant` and the MTP keys. The gate gives delta
`{kv_bits: (4, 8)}` with the entry not in `off`. No summary is needed, and the argv equals `_build_command`'s. The job runs with
`drafter_manifest: true`: the target manifest has 15 TurboQuant 8-bit leaves plus layer 63 native, and the drafter's observed
manifest equals its template. The entry is COMPLETED, with `engagement_only: true` and `certifies: false`.

**Failure path:** the drafter cache shows a quantized leaf, or no `drafter_manifest` was recorded. The entry is not COMPLETED, its
problems name the drafter manifest, and the exit code is nonzero.

## Supported conditions

The two P475 picks, through `classify_kv_arm`, on the stack worktree layout P475 uses. MTP drafters with `make_cache()` and `_cache`
(the `mtp_base` family that both picks use). One `--entry` per run.

## Acceptance criteria

1. Red first. The `--engagement-only` CLI refusals: no `--kv-arm`; `--predictor off` or unset; with `--p369-summary`; on an arm
   registry that serves the entry MTP-OFF (TQ4-OFF).
2. Each of N16 / AF8 / TQ8 / AF4 / TQ4 for `Qwen3.8-27B-mlx-uniform-4bit` (and one non-empty delta for
   `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`) passes the gate and `entry_problems` with no P369 summary. The served argv carries
   the MTP flags and the arm's KV flags. `command_problems` still refuses a tampered argv.
3. `request_problems` plus the drafter check: a K3-conforming drafter manifest gives no problem. A quantized drafter leaf, an empty
   or absent `drafter_manifest`, or a template mismatch each give a problem under `--engagement-only`. Without the flag the drafter
   manifest is not judged.
4. The worker records `drafter_manifest` only when the job asks for it (a test with a fake `rg.draft_model`); without the field the
   record keys are exactly today's.
5. The report fields `engagement_only` / `certifies` / `reference: None` appear under the flag only; a no-flag `--kv-arm` report is
   unchanged (existing P475a tests pass unmodified).
6. `foreign_process_problems`: a `bench.p475_kv` ancestor is exempt; a `bench.p475_kv` non-ancestor and a `bench.other` ancestor
   refuse (unmocked topology test as P452's, psutil `importorskip`).
7. The fork suite passes twice with identical skip lists and 0 failed; the audits are green; the production diff is empty.

## Non-goals

- No MTP-ON exactness, E1c / E2, or certification of any KV arm; no change to C199 for runs without the flag.
- No prompt-length option (the request stays the 256K-class qualification request).
- No stack change: the stack's `p475_kv` wiring and gitlink bump are the next step (C296 (2) / handoff step 2).

## Open questions (with recommendation)

- O1: should a drafter manifest also be recorded, unjudged, on ordinary MTP-ON qualify runs? Rec: no; keep the no-flag path
  byte-identical (C203 / P475a pinned it).
- O2: must the target manifest under MTP-ON also be checked against an MTP-specific expectation? Rec: no. The target cache is built
  through the same `make_cache` (`make_speculative_prompt_cache` returns `make_cache(lm, left_padding)`), and C249 proved TQ4 ON with
  today's check.
