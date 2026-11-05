All 14 files are in `benchmark/bench/tests/p475s1/`, covering acceptance item 1. On the baseline, 30 tests pass, 191 fail and 201 error, as expected before the candidate exists.

Only the KV-line and `rung_problems` tests (131) were checked as satisfiable, using a throwaway stub that I deleted afterwards. The leg, run, harvest, matrix and preflight tests have never run against any implementation. They will probably show test bugs once the candidate exists. I also couldn't run `git status`, so I haven't confirmed that nothing outside the test directory changed.

## Files

| File | What it covers |
|---|---|
| `fakes.py` | The fake `Ops` and `World`, plus the fixed formats: KV line, worker argv, `pmset` text, ladder rows, watcher journal. |
| `helpers.py` | Every call into `bench.p475_kv` goes through here. |
| `test_kv_line.py` (62 collected) | R22 and R2: parsing a string or a list, the last line, absent or malformed lines, per-arm checks. |
| `test_rung_problems.py` (66) | R21: 255/256/257 tokens, `cache_n` 0 vs 0.0 vs 1, the 2 % edge (408.0 passes, 409.0 fails), ON and OFF drafter shapes. |
| `test_run_capacity_strict.py` (26) | `--p475-strict`: persisted fields, session ids, decode carrier, 256-token cap, rung problems give nonzero exit. Five tests check the default output is unchanged. |
| `test_bench_watch_capacity.py` (15) | R9 rate/ETA from `elapsed_s`, R12 `--driver-create-time` in capacity and legacy modes, existing modes unchanged. |
| `test_leg_precheck.py` (~72) | Power, port, busy, lease (R4), 600 s idle (599 vs 601, later of the two `LAST_LEG_END` files), destinations, preflight PASS, R1 identity. |
| `test_leg_lifecycle.py` (~100) | R2, R3, R5–R7, R9–R12, R17: argv, KV line, teardown, speed problems, receipt. |
| `test_prepare_preflight.py` (26) | `prepare` idempotent and refuses dirty or diverged arms; `preflight` argv, PASS rule, retry cap (R15). |
| `test_harvest.py` (13) | R8, R17, R18: staging, scrub, PII refusal leaves no dossier, resume replays the harvest. |
| `test_run_control.py` (27) | ABBA, 600 s idle gap, INVALID stops the run, replacements (R13), NOT_STARTED (R14), refused arm (R15), instability, resume. |
| `test_matrix.py` (21) | R16, R19, R20: canonical vs PARTIAL, one ladder file per dossier, validated dossiers only, deciding column. |
| `test_fixtures_selfcheck.py` (21) | Checks the fake against the real code: `parse_power`, the `pmset` readers, the server's log-field order, the `_build_command` flags, and `bench_watch.speed_verdict` on the journals. |

Counts per class by test function: 209 exercise new behaviour, 21 reproduce a failure the contract fixes, 20 preserve an invariant.

## Baseline run

```
191 failed, 30 passed, 201 errors in 22.18s
```

- **Passed (30):**
  - 21 fixture self-checks.
  - 5 default `run_capacity` invariants.
  - 4 existing `bench_watch` invariants.
- **Errors (201):** every one is the `w` fixture failing on `ModuleNotFoundError: bench.p475_kv`.
- **Failed (191):**
  - 66: `capacity_ladder.rung_problems` missing.
  - 65: `ModuleNotFoundError: bench.kv_line`.
  - 28: `ModuleNotFoundError: bench.p475_kv`, raised in the test body (26 in `test_prepare_preflight.py`, 2 elsewhere).
  - 20: argparse rejects `--p475-strict`.
  - 11: argparse rejects `--capacity-rows` / `--driver-create-time`.
  - 1: the decode carrier file is missing.

One false green turned up and is fixed. The "requires a session prefix" test passed on baseline only because argparse exits 2 on an unknown flag, so it now first proves the flag is accepted.

## Ambiguities and the reading I took

The designer needs to resolve these before the candidate is revealed. The first two are the biggest.

- **P1 — Router environment stripping can't be observed.** `Ops.stack(wt, registry, predictor)` has no `env` parameter. I assert that `os.environ` has no `KV_*`/`TQ_*` name at the `stack()`, `start_router()` and `load()` calls. If stripping happens inside `RealOps.stack`, those three tests fail wrongly. Recommendation: add `env` to `stack()`.
- **P2 — Call shapes the contract doesn't give.**
  - Leg and arm: `run_leg(leg, arm, ops, cfg)` takes `leg` as the leg-name string (`u4-af8-b1.a1`) and `arm` as `"AF8"`.
  - Config: `cfg` is a dict with attribute access, carrying `wd`, `main_root`, `model`, `base`, `arm_commits`, `smoke`, `grid` and `expected_rung_seconds`.
  - Run args: `run(args, ops)` takes a list of tokens that also carries the parsed attributes.
  - Other entry points: I assume `prepare(args, ops)`, `preflight(args, ops)` with `args.arm`, and `matrix(args, ops)`.
  - Roots: the workdir comes from `STACK_WORKDIR`, and the results root from `bench.paths.REPO_ROOT`/`BENCHMARK_DIR`.
  - Adapting: all of this sits in `helpers.py` and `fakes.Cfg`.
- **P3 — Worker command line.** `load()["cmdline"]` is a string, `"<pid> " + shlex.join(argv)`, following `ChainOps`. `expected_worker_argv` is a list whose `--generation-defaults` JSON contains spaces, so a naive `split()` can't compare them. The contract should say which form to use.
- **P4 — Teardown identities.** The router pid comes from `start_router()`'s return value and the handle's `.router` dict, as in `ChainOps`. The interface table lists neither. My `proc_alive(pid, None)` means "any create time".
- **P5 — `git()` and arm discovery.** The fake dispatches by heuristics on `rev-parse` (HEAD, parent, branch, base), `diff`/`show`, `ls-tree` and `status`. How the code learns the base and arm commits is unspecified. I assume `prepare` verifies them.
- **P6 — Receipt and dossier shape.**
  - Only `verdict`, `speed_valid`, `problems` and `speed_problems` are named, so everything else is checked by content: the arm sha appearing at least twice, argv tokens, and so on.
  - A "ladder file" is any `*ladder*.jsonl`.
  - A dossier's receipt is the JSON with `verdict` and `speed_valid`.
  - A row's recorded problems sit under any key containing `problem`.
  - The preflight record's filename contains the arm label (case-insensitive).
- **P7 — Strict predictor source.** In `run_capacity --p475-strict`, ON vs OFF comes from the served registry's `draft_kind`, via `paths.registry_path()` and `MLX_SERVE_CONFIG`. `rung_problems` takes `"mtp"`/`"off"`. A missing session prefix refuses the run (SystemExit or nonzero), and duplicate or missing session ids give nonzero exit.
- **P8 — Capacity-mode watcher.**
  - `main(argv, power=, clock=, sleep=)` takes injected power, clock and sleep like `run_p426`.
  - Rate is the sum of elapsed over the sum of expected for completed rungs. ETA is the remaining expected time times that rate.
  - The key names aren't fixed. I look for any key containing `rate`/`ratio` and `eta`/`remaining`, with the ETA in seconds or minutes.
  - `--driver-create-time` takes `proc_guard.start_time` as a repr float.
  - Each tick's `driver_alive` and the driver-exit line follow the P426 journal.
- **P9 — Retry caps.**
  - `--max-preflight 2` means two qualify runs in total. "Retried at most 2 times" could instead mean three, so a candidate reading it as three would fail the cap tests.
  - `--max-not-started` is tested loosely, at between N and N+1 receipts.
- **P10 — Attempt numbering and idle.**
  - A replacement or NOT_STARTED retry increments `.a<n>` for the same arm and block.
  - The clean-run test requires exactly twelve `.a1` legs, so `run` must wait the 600 s idle through `ops.sleep` rather than get refused and retry.
  - The idle is measured from `stop_stack`; the fake's clock moves only through `sleep`/`wait`.
- **P11 — INVALID vs SPEED_INVALID.**
  - INVALID: a driver exit other than 0, an error row, an unkillable driver, an unload refusal, a survivor, and any argv, KV-line or environment failure.
  - SPEED_INVALID (verdict VALID, `speed_valid` false, `problems` empty):
    - a missing journal;
    - a journal with no `driver_exited` line or an early exit;
    - a power failure;
    - too few ticks, or a gap over 2× the interval counted to the exit line;
    - a battery interval inside launch→exit;
    - an unreadable `pmset` log (my reading, from `_speed_from_power`).
  - Tick-count boundary: 7 ticks pass and 6 fail for the fake's 2760 s driver, which is `(2760−600)//300 = 7`.
  - `pmset_log(start, end)` may receive epoch seconds or UTC stamps. I accept both, within ±2 s of the driver's launch and exit.
- **P12 — Deciding block.** It is the whole block (all arms) in block-1 order. I assert N16 and AF8 are present, in order. One block only, and `--max-deciding 0` forbids it.
- **P13 — Run behaviour after a cap or refusal is reached.** The contract says only that a refused preflight lets the rest run with a nonzero exit. For an exhausted replacement cap I assert only a nonzero exit and a PARTIAL table.
- **P14 — Matrix content.**
  - Values are checked as substrings with at least one decimal (for example `225.0`).
  - I look for the words `deciding`, `accept`, and `instab|unstable`, and for the label and "descriptive" strings verbatim.
  - The N16 comparison is a case-insensitive `0.95` check, which is weak.
- **P15 — Smaller readings.**
  - `quantized_kv_start` as `None` or `"0"` is a problem.
  - The TurboQuant mode `'mse'` is required only on TQ arms.
  - Preflight uses `--predictor off` for all six arms.
  - The `prepare` mutation test treats `commit`/`checkout`/`reset`/`worktree add` and similar as mutating.

One finding for the designer: `_build_command` never emits `--kv-group-size` (pinned by a self-check test). R3's "every KV flag incl. `--kv-group-size`" therefore only works through exact argv equality, and my group-size test is "an extra flag appears".
