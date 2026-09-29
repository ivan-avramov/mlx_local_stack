# Handoff — 2026-09-29 (late session): M51 and M50 LIVE-VERIFIED on the real stack; M46 live; first D12 accounting

THE one handoff (AGENTS.md: rewritten in place each session; there is no per-feature handoff). Read this,
then `docs/PLAN.md` (the only queue) and `docs/open-questions.md` (decisions). Specs for queued work live in
`docs/specs/`; history in `docs/lab-notebook.md`.

## State of the world

- **Git: stack main has UNPUSHED commits** on top of `a4ded14` (M51 live result 5d84b35 + this session's second
  commit); forks `../mlx-vlm` `1bd249d3` and mlx-serve `6602ae5` unchanged. Push only on explicit instruction.
- **Stack is UP on the NEW `runserver.sh`** (M51 script): shell pid 36341, router pid 36401 on :8000,
  `MLX_SERVE_CONFIG=main_models.yaml`, sessions 2, APC absent (verified `ps -Eww`), compose healthy. Resident model:
  `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (worker `--draft-kind mtp`, native16 KV per C81). `kill -TERM 36341`
  now tears the whole stack down (verified live today); `scripts/stack_stop.sh` remains the stop for stale shells.
- **Picks unchanged**: B/C 1st `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` t0.5 medium, native16 KV (C81
  provisional), repaired MTP. No serving config changed this session.
- Bench suite unchanged (1878 passed / 3 skipped at the start of the session; no code touched).

## DONE this session (notebook 2026-09-29, two entries; PLAN M50/M51/M46/D12/M52/M53; open-questions C106)

- **M51 live PASS**: old shell (pid 96728) cleared by `stack_stop.sh`; fresh bring-up in 10 s; ONE `kill -TERM` on the
  shell exited shell, both server trees, log tail and compose in 3.1 s, `Cleaned up (:8000 free)`, 0 listeners.
  Side finding: four `docker compose logs -f` orphans (ppid 1, 1–2 days old) from OLD-script shells had survived every
  stop; killed by pid. The new script kills its own tail; `stack_stop.sh` does not sweep that pattern (one-liner if needed).
- **M50 opencode path live PASS** (5 seeded python items, `$STACK_WORKDIR/m50/opencode_live_check.*`): the
  `M50 served-config OK: opencode -> http://localhost:8000/v1 …` line before any request; manifest `router` block
  scrubbed; `skill_policy` + `opencode_config_sha256` recorded. 5/5 passed, no stalls/loops.
- **M46 live PASS**: one transcript per row under `$STACK_WORKDIR/opencode_transcripts/`, `loop_metrics` populated.
- **D12 first accounting** by hand (`$STACK_WORKDIR/m50/d12_accounting.py`): session cache turns 569K cumulative input
  into 79K incremental prefill; fit ~873 tok/s incremental prefill, ~42 tok/s decode; prefill 18 % / decode 82 % of
  router wall at ≤19.5K context. Transcript `tokens.input` = incremental, `reasoning` = 0 (router reports no split).
  The two report columns are still to land in the probe (D12 stays queued with a definition note).
- **Rulings**: P81 → **M52** queued (`vision_gate` manifest); P82 → **C106 DEFERRED** (router-side config hash);
  P83 → opencode child proxy rule unchanged.
- **New**: **M53** queued (P84) — the probe checks `STACK_WORKDIR` only at transcript-export time; attempt 1 ran a whole
  item (~1.5 min worker time) before exiting. Move the check to entry beside M50; audit other late preconditions.

## Rules learned this session

- A driver launch must carry `STACK_WORKDIR` (source `config.sh`) as well as `MLX_SERVE_CONFIG`; the probe refuses
  late without it. Until M53 lands, verify both on the driver pid (`ps -Eww`) before the first item.
- The router metrics log's `TTFT`/`tok/s` fields appear only on some requests and the `tok/s` on long completions is
  not the decode rate; derive D12 rates from a fit over (incremental prompt, completion, ms).
- `kv_bits: 0` in the registry means NO `--kv-bits` flag on the worker cmdline (mlx-serve emits it only for >0); the
  `--kv-quant-scheme turboquant` flag still appears and is inert. Read both before calling a worker "quantized".

## Pending (reconciled)

1. **M53** fail-fast `STACK_WORKDIR` check in `run_opencode_probe` (small, TDD).
2. **D12** columns in the probe (`input_tokens_total` cumulative AND incremental, `turns`, `max_context`), rates from
   the fit; lands with the next agentic run or as its own small unit.
3. **M52** `vision_gate` manifest (small, CPU-only).
4. **Deferred**: C106 router-side config hash; frontier-driver composition (switchyard doc §8); S1 NVSY (parked);
   C77/C78/C87; C96; C104 open (fork test-suite sync policy).
5. **D7** and **D5** remain driver-side backlog.

## Resume discipline

One resident model; APC absent; retained sessions 2; full active preallocation; deployed sampling; explicit
served-overlay environment AND `STACK_WORKDIR` on every driver (M50 refuses a served-config mismatch; the probe
refuses a missing workdir). Never alter source/config during a live run. Commit coherent units; push only on explicit
current-turn instruction (forks before stack). Next decision id C107; discussion ids continue from P84.
