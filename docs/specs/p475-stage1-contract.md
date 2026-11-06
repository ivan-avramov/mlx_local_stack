# P475 stage 1 — build contract (v1.3, 2026-11-05 — v1.1 the ops interface; v1.2 the round-1 fix dispositions (`docs/reviews/p475s1/dispositions.md`); v1.3 C296 / C297 on-box fixes; operator Go C292; four-eyes light)

Refines `docs/specs/p475-kv-matrix.md` v4 for the build. Where this contract and the spec differ, this contract wins; where the spec's
v3 text and v4 differ, v4 wins (and both lose to this file). The lost candidate's code does not exist: R1–R22 are restated here as
behaviours, never as the lost functions.

## Goal (carry verbatim in every brief)

Ship `Qwen3.8-27B-mlx-uniform-4bit` in its ideal KV-cache format. Today it serves TurboQuant 4-bit KV (PROVISIONAL, C202) with MTP ON
(CERTIFIED C249); the alternatives were never measured against it on matched code, box and instrument. Solving it means: a matched,
order-balanced measurement of each candidate format for this pick, taken through the shipped stack (mlx-serve → mlx-vlm loading a
committed `main_models.yaml`, C218), each format proven engaged, reported as a generated tradeoff table (cumulative peak memory,
backend prefill tok/s, decode tok/s, MTP acceptance) that the operator weighs as a whole, with no pass line.

## Facts (v4.1 refresh, 2026-11-04)

- Base = the stack `main` commit that carries the accepted stage-1 code (v1.2, Sol P1: the arm worktrees run the instrument from the base; the P475a gitlink is in: fork `d94e38a9`, mlx-serve `1ddf6f84`; production `mlx_vlm/` byte-identical
  to S′ `1c7c8fa1`). `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` MTP is CERTIFIED P426 (C291).
- The committed entry (`main_models.yaml`): `kv_bits: 4`, `kv_quant_scheme: turboquant`, `quantized_kv_start: 0`,
  `max_kv_cache_size` = `kv_prealloc_tokens` = 262144, `draft_kind: mtp` + `draft_model`, no `mtp_verify_scan` (per_query), no
  `attention_policy` (auto).
- `KV cache resolved:` is logged once per load by the fork (`mlx_vlm/server/app.py`) to `MLX_VLM_LOG_FILE`
  (`<WT>/logs/mlx_vlm.log` under `ChainOps`): `kv_bits=%r kv_key_bits=%r kv_value_bits=%r kv_key_scheme=%r kv_value_scheme=%r
  kv_quant_scheme=%r kv_group_size=%r quantized_kv_start=%r TQ_KV_QUANT_MODE=%r` (`kv_bits` a float or `None`; split fields `None`
  when unset).
- The worker inherits the router's environment; its CLI sets `KV_BITS` / split vars only when the flag is given, so an inherited
  `KV_BITS` survives on an N16 arm. `ChainOps.env_base` overlays `<repo>/.env` and strips no KV variables.
- `bench.run_capacity` derives prefill from wall − decode and does not persist `prompt_ms`, `prompt_per_second`, `prompt_n`,
  `cache_n`, `predicted_n`; drafter counters are `draft_kind`, `draft_n`, `draft_n_accepted`, `draft_rounds` (may arrive as JSON
  `null` on OFF arms).

## Scope

This pick only (both blocks + any deciding block). The `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` half is out of scope (P628:
mlx-serve refuses `fused_v1` / `joint_v1` with `kv_bits` ≠ 0; operator's word needed). Stage 2 (quality) is its own spec.

## Arms (short pick label `u4`)

| Arm | Entry keys changed from the base (nothing else in the file) | Predictor |
|---|---|---|
| N16 | `kv_bits: 0` (the scheme line stays as in the base — the fork's `--kv-arm` gate and spec v4; v1.2, Sol P2) | ON |
| AF8 | `kv_bits: 8`, `kv_quant_scheme: uniform` | ON |
| TQ8 | `kv_bits: 8`, `kv_quant_scheme: turboquant` | ON |
| AF4 | `kv_bits: 4`, `kv_quant_scheme: uniform` | ON |
| TQ4 | none — the base commit itself | ON |
| TQ4-OFF | `draft_kind` and `draft_model` lines commented out | OFF |

Each non-base arm = one commit on local branch `p475-u4-<arm-lower>` off the base, adding a `# PROVISIONAL P475 arm <ARM>` comment
in the entry; one temporary worktree per arm under `$STACK_WORKDIR/worktrees/p475-u4-<arm-lower>`, prepared like the P426 arm
worktrees (submodules at the base gitlinks, `.venv` and `.venv-bench` via `uv sync --frozen`), removed after its legs are harvested.

## Components (new files unless marked)

1. `benchmark/bench/kv_line.py`: `parse_kv_line(text_or_lines) -> dict` (the LAST `KV cache resolved:` line; values as Python
   literals; refuses when absent or malformed); `expected_kv(arm) -> dict`; `kv_line_problems(parsed, arm) -> [str]`. Native (N16):
   `kv_bits` None or numeric 0, scheme not compared. Quantized: `kv_bits` numerically equal to the arm's bits, `kv_quant_scheme` equal,
   all four split fields None, `kv_group_size` 64, `quantized_kv_start` numerically 0 (R22, R2); TurboQuant arms `TQ_KV_QUANT_MODE`
   `'mse'`.
2. `bench.run_capacity` + `bench.capacity_ladder` (CHANGED, opt-in `--p475-strict`; without it every current output is byte-identical):
   - each measured row persists the backend's `prompt_ms`, `prompt_per_second`, `prompt_n`, `cache_n`, `predicted_n`,
     `predicted_per_second`, `peak_memory` (as `peak_memory_gb_cumulative`), the drafter counters and the request's `session_id`;
     the run requires `MLX_BENCH_SESSION_PREFIX` and a unique session id per request (calibration included);
   - the measured prompt = the rung's context + a fixed committed decode carrier `benchmark/bench/data/p475_decode_carrier.txt`
     (a code-continuation instruction) instead of the retrieval question; `max_tokens` = 256 with deployed sampling, thinking as deployed;
     `retrieval_acc` null;
   - `rung_problems(row, predictor) -> [str]` (R21): `peak_memory_gb_cumulative` and `predicted_per_second` finite and > 0 (v1.2, Sol P4); `completion_tokens == predicted_n == 256`, `finish_reason == "length"`,
     `cache_n` numerically 0 (int or float), `|prompt_per_second − prompt_n / (prompt_ms / 1000)| ≤ 2 %`, `prompt_n` == the row's prompt
     tokens; ON: `draft_kind == "mtp"`, `draft_n > 0`, `0 ≤ draft_n_accepted ≤ draft_n`, `draft_rounds > 0`; OFF: every drafter key
     absent or null. A rung with problems is recorded with them and the run exits nonzero.
3. `benchmark/m1/bench_watch.py` (CHANGED, additive): `--driver-create-time` binds (pid, create_time) in any mode (R12); capacity mode
   `--capacity-rows <ladder.jsonl> --expected-rung-seconds a,b,…` writing JSON ticks like the P426 mode (power, battery, driver alive)
   with RATE / ETA from `elapsed_s` against the expected durations (R9); a final exit line with the window. Existing modes unchanged.
4. `benchmark/bench/p475_kv.py` with subcommands `prepare`, `preflight`, `run`, `matrix`:
   - `prepare`: create / verify the arm branches and worktrees (idempotent; refuses a dirty or diverged arm).
   - `preflight --arm A`: the fork's `qualify.py --kv-arm --predictor off --entry <pick>` against the arm worktree (argv built as
     `p426_plan` builds its qualify argv, plus `--kv-arm`); PASS needs `report.json` status COMPLETED and `kv_arm.entry` == the pick;
     the record goes to `$STACK_WORKDIR/p475/preflight/<arm>.json`. A refusing arm is retried at most `--max-preflight` (default 2)
     times; then the arm is marked refused, the run continues with the others and exits nonzero (R15).
   - `run [--blocks 2] [--max-replacements 4] [--max-not-started 3] [--max-deciding 1] [--smoke]`: plan → legs → replacements → deciding
     block; resumable from `$STACK_WORKDIR/p475/state.json` (caps monotonic on resume, R13). The measurement-block count and the
     deciding block's identity / completion are persisted at the first leg; changing `--blocks` after any leg exists refuses (v1.2, Sol P7).
   - `matrix`: regenerate the table from harvested dossiers only.
   All side effects go through the ops object below (`p475_kv.RealOps` implements it; tests pass a fake). `run_leg(leg, arm, ops,
   cfg) -> receipt dict` and `run(args, ops) -> int` take it explicitly.

## Ops interface (`p475_kv.Ops`, a `typing.Protocol`; the test seam)

| Method | Returns / raises |
|---|---|
| `power()` | `{"watts": float, "volts": float, "battery": int}` |
| `port_listener(port)` | the listening pid or None |
| `busy()` | list of busy process descriptions (empty = quiet) |
| `lease()` | a context manager holding `p426_locks.acquire("chain", wd)`; raises `p426_locks.LockRefused` |
| `now()` / `monotonic()` / `sleep(s)` | epoch seconds / monotonic seconds / None |
| `worktree_state(wt)` | `{"head", "clean", "gitlinks"}` as `chain_ops.worktree_state` |
| `git(wt, *args)` | stdout str (e.g. `rev-parse`, `diff`); raises on rc ≠ 0 |
| `stack(wt, registry, predictor)` | a router handle with `start_router()`, `load(model) -> {pid, create_time, cmdline}`, `expected_worker_argv(registry, model) -> list`, `stop_stack() -> int`, `unload_ok() -> bool` |
| `proc_alive(pid, create_time)` | bool |
| `proc_env(pid)` | dict |
| `spawn(argv, env, cwd, session=True)` | `{"pid", "create_time"}` |
| `wait(proc, timeout)` | rc or None on timeout |
| `signal_group(proc, sig)` | None |
| `group_alive(pgid)` | bool — any live member of that process group (v1.2, Sol P5) |
| `start_watch(argv)` / `stop_watch(handle)` | handle / None |
| `read_text(path)` / `pmset_log(start, end)` | str / str |
| `run(argv, cwd, env, timeout)` | `subprocess.CompletedProcess` (preflight `qualify.py`) |

Fixed formats the fake reproduces: the `KV cache resolved:` line above; worker argv lists as `_build_command` emits them; capacity ladder
rows as `run_capacity --p475-strict` writes them; `bench_watch` capacity-mode JSON ticks; `pmset -g ac` / `pmset -g log` text as
`chain_ops.parse_power` / `p426_leg.battery_window` parse it.

## Leg lifecycle (`run_leg`)

1. Pre-check, any failure → receipt `NOT_STARTED`, nothing started: the arm worktree's instrument files (`bench/run_capacity.py`,
   `bench/capacity_ladder.py`, `bench/kv_line.py`, `bench/data/p475_decode_carrier.txt`, `m1/bench_watch.py`) byte-identical to the
   orchestrator checkout's (v1.2, Sol P1); power 140 W / 28 V / battery > 20 %; `:8000` free; no busy process
   (ChainOps `BUSY` + `run_capacity`); the lease `p426_locks.acquire("chain", wd)` (opposes the local gate) held to teardown (R4);
   ≥ 600 s since the later of `$STACK_WORKDIR/p475/LAST_LEG_END` and `$STACK_WORKDIR/p426/LAST_LEG_END`; destinations absent; the arm's
   preflight PASS; arm identity at entry (R1: worktree clean, HEAD == the arm commit, its parent == the base (TQ4: HEAD == base), diff
   of the arm commit ⊆ the arm's keys + comment, gitlinks == the base's).
2. Router: `ChainOps(repo=<arm WT>, overlay=<arm WT>/main_models.yaml, predictor="mtp"|"off")` with every `KV_*` / `TQ_*` name (and
   `p426_secrets.STACK_DEFINED_KV_TQ_NAMES`) removed from the router environment (R2); `start_router`; `load(model)`.
3. After load, before the driver (R5): worker argv == `ChainOps.expected_worker_argv(<arm registry>, model)` exactly (covers every KV
   flag, R3); worker environment carries no stripped name; `kv_line_problems` on the log text written since the load began;
   predictor state (ON: exact MTP flags; OFF: no draft flag) per `ChainOps.load`. Any failure → teardown, receipt INVALID.
4. Driver: `run_capacity --model <pick> --grid 8192,131072,196608,260096 (smoke: 8192) --sampling-profile deployed --seed 0
   --out-tag p475-<leg> --out-dir $STACK_WORKDIR/p475/legs/<leg>/capacity --p475-strict --expected-rung-seconds …` (C297: the
   leg writes nothing in its arm worktree; R1's "clean" holds at entry and exit) with the arm worktree's `.venv-bench` python, cwd the arm worktree's
   `benchmark/`, env: `MLX_SERVE_CONFIG` = the arm registry, `MLX_BENCH_SESSION_PREFIX=p475-<leg>`, KV names stripped. Own session;
   timeout derived from the expected durations × 3; on timeout or any exit path the driver's group is terminated, escalated, reaped and
   verified empty with `group_alive` (signalled while any member lives, also after a normal leader exit; v1.2) before the watcher stops and teardown starts (R6).
5. Watcher: `bench_watch` capacity mode bound by (pid, create_time), started right after the driver spawns. Its failures (no report,
   early exit, power-receipt failure, tick count < (driver interval − 600) // 300, a gap > 2 × interval, `pmset -g log` battery
   interval inside driver launch → driver exit) are `speed_problems` (SPEED_INVALID → replacement), never INVALID (R9–R11).
6. Teardown proven (R7): `ChainOps.stop_stack`; then the worker pid, the `:8000` listener, the router, its wrapper and the router's
   process group (`group_alive`) verified gone; an unload refusal or a survivor → INVALID. Arm identity re-read at exit (R1).
7. Receipt `$STACK_WORKDIR/p475/legs/<leg>/receipt.json`, written atomically, never overwritten (a second write goes to
   `receipt.refused-<ns>.json`; the canonical receipt wins on read, R17): verdict VALID / INVALID / NOT_STARTED, `speed_valid`,
   `problems`, `speed_problems`, arm identity entry + exit, worker argv, the parsed KV line, preflight ref, router / worker identity,
   driver interval, watcher verdict, power readings.
8. Harvest (VALID or INVALID legs): stage `benchmark/results/p475/<leg>.stage/` (receipt, ladder rows, manifest, watch ticks, KV line,
   worker argv), every file through `p426_harvest.Scrub`, piicheck and `p426_harvest.Gate.check(..., dest="main")` (credentials, foreign e-mail
   addresses; v1.2, Sol P6), verify, then rename to `benchmark/results/p475/<leg>/` (R18);
   scrubbed full worker / router logs to `$STACK_WORKDIR/p475/evidence-stage/<leg>/` (a destination like the others: absent at
   pre-check, never overwritten; v1.2, TW F2) (the designer commits them to `evidence`). Then
   write `LAST_LEG_END` (R8). Resume replays harvest for a receipt without its finalized dossier.

## Run control

- Order: block 1 N16 → AF8 → TQ8 → AF4 → TQ4 → TQ4-OFF; block 2 the reverse; leg name `u4-<arm-lower>-b<k>.a<n>`; smoke
  `u4-n16-smoke.a<n>` then `u4-tq4-smoke.a<n>` (`--smoke` runs both; v1.2).
- INVALID (smoke legs included) → the run stops (exit nonzero), and a resume stops again at a standing INVALID leg (v1.2, TW F1). SPEED_INVALID → a replacement of the same arm and block, queued after the block's ordered
  legs (block order preserved), bounded by `--max-replacements` (R13). NOT_STARTED → retried after its own 600 s idle, bounded by
  `--max-not-started`, never evidence (R14).
- Instability (per arm and rung, from the two blocks' ratios vs N16 for each metric): a direction reversal (one ratio > 1, the other
  < 1) or `|r1 − r2| > |mean − 1| / 2` triggers one deciding block (block-1 order) under `--max-deciding` (R16 reports it in its own
  column, never in the two-block mean). A flag left unresolved (cap spent or 0) exits nonzero and is labelled on the table (v1.2, TW F6).
- Resumed metrics come only from finalized, validated dossiers with exactly one ladder file each (R19), whose receipt's model, base,
  arm commit, gitlinks and leg identity equal the run's; a second usable dossier for the same arm / block / attempt slot refuses
  (v1.2, Sol P3).

## Output (`matrix`)

`benchmark/results/p475/MATRIX.Qwen3.8-27B-mlx-uniform-4bit.md` labelled "one pick (partial matrix, P475 v4)", generated, never
hand-edited: per arm × rung, block 1 / block 2 / mean (and deciding, own column) for cumulative peak GB, backend prefill tok/s, decode
tok/s, ON acceptance; the paired block ratios vs N16 and the instability flags; replaced, refused and NOT_STARTED legs listed;
"descriptive (two order-balanced speed-valid legs per arm, no interval claimed)". Written only when every arm has two speed-valid
legs with valid rungs; otherwise `MATRIX.Qwen3.8-27B-mlx-uniform-4bit.PARTIAL.md` and exit nonzero (R20). Exactly one of the two exists after any
  regeneration: writing one atomically removes the other (v1.2, Sol P8).

## Acceptance

1. Red-first tests, mocked ops, real argv / env / receipt / log formats: one per R1–R22 as restated above, plus: arm-commit checks,
   preflight refusal and retry cap, argv / KV-line / predictor checks, `--p475-strict` fields and every `rung_problems` refusal, the
   unchanged default `run_capacity` output, ABBA order, idle from harvest end, power / busy / lock refusals, replacement queue,
   instability trigger, harvest staging + resume, matrix completeness.
2. The existing suites touched (`run_capacity`, `capacity_*`, `bench_watch`, `chain_ops`, `p426_*`) pass unchanged.
3. After Accept (designer, on the box): `prepare`; one preflight per codec family (N16, AF8 / AF4, TQ8 / TQ4) passes; two smoke legs
   (N16 and TQ4, grid 8192; v1.2, GLM F1: the worker CLI sets `KV_BITS` only on a quantized arm) VALID with the live KV line, the
   worker environment, the backend telemetry identities (`prompt_n`, `prompt_per_second`) and the drafter-key shape recorded; then the full run.

## Non-goals

The `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` half; stage 2; changes to `chain_ops.py`, `p426_*` behaviour or the local gate; MTP-ON exactness of AF8 / TQ8 / AF4;
`quantized_kv_start` thresholds; TurboQuant widths other than 4 / 8.
