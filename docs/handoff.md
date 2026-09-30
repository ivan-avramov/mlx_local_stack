# Handoff — 2026-09-29 (late session): M51/M50 LIVE-VERIFIED; M46 live; D12 columns + M53/M52 landed; opencode pin 1.18.30

THE one handoff (AGENTS.md: rewritten in place each session; there is no per-feature handoff). Read this,
then `docs/PLAN.md` (the only queue) and `docs/open-questions.md` (decisions). Specs for queued work live in
`docs/specs/`; history in `docs/lab-notebook.md`.

## State of the world

- **Git: stack main pushed through 13b0b66** (P86–P88); the M52 commit after it is UNPUSHED. Forks `../mlx-vlm`
  `1bd249d3` and mlx-serve `6602ae5` unchanged.
- **Stack is UP on the NEW `runserver.sh`** (M51 script): shell pid 36341, router pid 36401 on :8000,
  `MLX_SERVE_CONFIG=main_models.yaml`, sessions 2, APC absent (verified `ps -Eww`), compose healthy. Resident model:
  `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (worker `--draft-kind mtp`, native16 KV per C81). `kill -TERM 36341`
  now tears the whole stack down (verified live today); `scripts/stack_stop.sh` remains the stop for stale shells.
- **Picks unchanged**: B/C 1st `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` t0.5 medium, native16 KV (C81
  provisional), repaired MTP. No serving config changed this session.
- Bench suite: **1889 passed / 3 skipped** (M53, D12 and M52 tests added).

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
- **M53 DONE** (P86): `_stack_workdir()` at entry before M50, env else `config.sh` fallback (no shell executed); live-verified
  both ways with zero router requests. **D12 row columns DONE** (P87): `traffic{...}` per row, validated on the five live
  transcripts. **Pin bumped** to opencode 1.18.30 (P88).
- **M52 DONE**: `vision_gate` writes a manifest beside its rows (router block, deployed profile, corpus sha,
  `router_history` on rerun, refusal on a different served config); live one-item PASS on the daily driver.

## Rules learned this session

- Against the daily driver a probe launch needs NEITHER export: `MLX_SERVE_CONFIG` defaults to `main_models.yaml` and
  `STACK_WORKDIR` falls back to `config.sh` (M53). `MLX_SERVE_CONFIG` is mandatory only when a lean router serves an
  overlay. Neither guard exists outside the bench drivers — daily opencode/OpenWebUI use is untouched.
- The router metrics log's `TTFT`/`tok/s` fields appear only on some requests and the `tok/s` on long completions is
  not the decode rate; derive D12 rates from a fit over (incremental prompt, completion, ms).
- `kv_bits: 0` in the registry means NO `--kv-bits` flag on the worker cmdline (mlx-serve emits it only for >0); the
  `--kv-quant-scheme turboquant` flag still appears and is inert. Read both before calling a worker "quantized".

## Pending (reconciled)

1. **P89 (unruled)**: `vision_gate`'s image cache resolves `STACK_WORKDIR` from the env only (falls back to the HF
   cache with a warning); move the probe's `_stack_workdir()` resolver to `bench/paths.py` and use it in both.
2. **D12 report side**: wall-clock cost per task from the row's `traffic` × rates fitted on the router metrics log
   (script in `$STACK_WORKDIR/m50/`); lands with the next agentic run's report.
3. **Deferred**: C106 router-side config hash; frontier-driver composition (switchyard doc §8); S1 NVSY (parked);
   C77/C78/C87; C96; C104 open (fork test-suite sync policy).
4. **D7** and **D5** remain driver-side backlog.

## Resume discipline

One resident model; APC absent; retained sessions 2; full active preallocation; deployed sampling; explicit
served-overlay environment on every OVERLAY driver (M50 refuses a mismatch; the probe resolves `STACK_WORKDIR` itself). Never alter source/config during a live run. Commit coherent units; push only on explicit
current-turn instruction (forks before stack). Next decision id C107; discussion ids continue from P89.
