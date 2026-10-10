# M41 runner spec — capacity + depth ladders on pick A, predictor-ON (agent-facing; rules, not rationale)

Dir: `$STACK_WORKDIR/queue/m41_ladders/` (this file, `run.py`, `helpers.py` = copied from `queue/m40_mtp/helpers.py`
unchanged, `on_Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed.yaml` = the M40 ON overlay, `README.md`). Repo `$STACK_REPO`;
bench venv `$STACK_REPO/.venv-bench/bin/python`; results `$STACK_REPO/benchmark/results/<model>/`. Read
`queue/m40_mtp/run.py` first and reuse its patterns verbatim where named below (`router_start`/`router_stop`,
`worker_cmdline_for_check`, `_force_load`, `draft_counter_probe`, `run_depth`'s heartbeat/bound/provenance block,
`idle_precheck`, `parse_args --dry-run/--from-step`, logging grammar). Do NOT commit. Do NOT modify anything under
`$STACK_REPO` (the tooling flags used below are delivered by `TOOLING.md`; if a flag is missing at `--dry-run` time,
FATAL with the missing flag named — never work around it).

## 1. Pick, state, tune label
- ONE pick: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`. State: predictor-ON (registry `draft_kind: mtp`, M40-certified).
- Overlay: `on_Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed.yaml` in this dir; log its sha256 at start; every driver runs
  with `MLX_SERVE_CONFIG=<overlay abs path>` in its env and `APC_ENABLED` absent; `MLX_VLM_CACHE_SESSION_MAX=2` on the
  router (helpers.start_router already does this — verify on the router pid with `ps -Eww`, log the line).
- Tune label / out-tag for ALL three ladders: `m41on`. Sampling profile: `deployed` on every driver.
- Worker cmdline check before every ladder (`worker_cmdline_for_check`): `--draft-kind mtp` MUST be present, else FATAL.

## 2. Order and arms (one router session; the worker stays loaded across the three ladders)
1. **Capacity** (gate): `python -m bench.run_capacity --model <pick> --grid 131072,196608,262144 --gate-gb 46
   --sampling-profile deployed --out-tag m41on` (cwd `$STACK_REPO/benchmark`, `PYTHONPATH=$STACK_REPO/benchmark`).
   Bound 2 h. Before launch log `idle_precheck` + system-used GB (quiet-box record). After: parse
   `capacity_retrieval.m41on.json`; log `RESULT capacity m41on max_fitting_ctx=<> capacity_gate_pass=<> peaks=<[(ctx, server_peak_gb, fits, prefill_s, decode_tps, acceptance)]>`.
   If `capacity_gate_pass` is false → log `GATE-FAIL capacity` and CONTINUE (the depth ladders still run; the gate
   verdict is the operator's).
2. **Retrieval depth**: `python -m bench.run_retrieval --model <pick> --grid 8000,32000,64000,96000,128000 --samples 5
   --threshold 0.85 --sampling-profile deployed --out-tag m41on --request-timeout 9600`. Bound 5 h. After: log
   `RESULT retrieval m41on retrieval_effective_ctx=<> rungs=<[(ctx, accuracy, errors, decode_tps_mean, prefill_s_mean, acceptance_pooled)]>`.
3. **Reasoning depth** (M11 design): `python -m bench.run_reasoning --model <pick> --grid
   8000,16000,24000,32000,48000,64000,96000,128000,156000 --samples 5 --deep-from 96000 --deep-samples 3 --chain-len 4
   --threshold 0.85 --sampling-profile deployed --out-tag m41on --request-timeout 9600`. Bound 10 h. After: log
   `RESULT reasoning m41on reasoning_effective_ctx=<> rungs=<[(ctx, accuracy, budget_hits, samples, decode_tps_mean, prefill_s_mean, acceptance_pooled)]>`
   plus `RUNAWAY draws=<n budget_hit rows> tokens=<sum completion_tokens of budget-hit rows>`.
4. Unload (`helpers.unload`, pgrep-verified) → stop router (0 listeners) → `=== M41 DONE ===`.

## 3. Per-ladder mechanics (copy `run_depth`)
- Launch with `Popen` (stdout+stderr → `<dir>/<tag>.log`, stdin DEVNULL), write `<tag>.pid`, 5-min HEARTBEAT thread
  logging the partial/ladder file size (`capacity_ladder.m41on.jsonl`, `retrieval.m41on.json` absent-until-end → log
  the driver log's byte size instead, `reasoning.m41on.partial.jsonl`), `worker_cmdline_present`, `driver_alive`.
- Bound: kill+wait at the bound, log `TIMEOUT <tag>`, FATAL.
- rc≠0 → FATAL (state preserved; the reasoning ladder is resumable with `--resume`, say so in the FATAL line).
- `draft_counter_probe()` before/after; when both None log the known WARN line verbatim from M40.
- Write `<out>.m41on.provenance.json` per ladder: overlay path + sha, worker cmdline, started/finished, draft counters,
  `router_pid`, `idle_system_used_gb` (capacity only).
- Every log line timestamped as in M40 (`helpers.log`).

## 4. Invariants
- ONE resident model; `idle_precheck` at start FATALs if any `mlx_vlm.server`/`mlx-serve`/`run.py generate`/
  `bench.run_*` process exists.
- Never change serving config mid-run; never lower a budget; never disable thinking.
- `--dry-run` prints every command, env, bound and check without launching anything (and without starting the router).
- `--from-step {capacity,retrieval,reasoning}` skips completed ladders (a ladder counts as complete only if its
  `<out>.m41on.json` AND `.provenance.json` exist).

## 5. Acceptance (the reviewer checks these)
- `run.py --dry-run` output shows the three exact commands above with `--sampling-profile deployed`, `--out-tag m41on`,
  the env `MLX_SERVE_CONFIG=<abs overlay>`, `APC_ENABLED` absent, bounds 2/5/10 h, and the worker-cmdline expectation.
- The reasoning command carries `--deep-from 96000 --deep-samples 3` and the nine-rung grid.
- FATAL paths preserve state; nothing in `$STACK_REPO` is modified by the runner (results files excepted).
- Log grammar: RUN / worker cmdline / HEARTBEAT / END / RESULT / WARN / TIMEOUT / FATAL / GATE-FAIL / `=== M41 DONE ===`.
