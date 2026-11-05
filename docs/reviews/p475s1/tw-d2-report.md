# Test-writer delivery 2: P475 stage 1

**Verdict: fix, then merge.** I found one candidate defect, and it needs a code fix (F1 below). No false-VALID path turned up. I could not re-run the amended tests on the baseline tree, because `git apply -R` and a baseline extract were both denied (details under baseline).

## Suite results (candidate applied)

- **Frozen directory (`p475s1`):** `1 failed, 433 passed in 75.28s (0:01:15)`. The one failure is a candidate defect (F1).
- **Implementer's tests:** `161 passed in 10.84s` (`bench/tests/test_p475_impl_*.py`).
- **Touched suites:** `557 passed in 35.71s`. This covers `test_run_capacity.py`, `test_capacity_*.py`, `test_agentbench_watch.py`, `test_bench_watch.py`, `test_chain_ops.py`, `test_m64_chain_ops.py` and `test_p426_*.py`.

## Per test file

All new tests are class "exercises new behaviour" unless stated.

| File | Passed on candidate | Baseline (delivery-1 run) |
|---|---|---|
| `test_kv_line.py` | 65 | all red (module missing) |
| `test_rung_problems.py` | 66 | all red |
| `test_run_capacity_strict.py` | 26 | 5 default-output invariants pass; the other 21 red |
| `test_bench_watch_capacity.py` | 15 | 4 existing-mode invariants pass; 11 red |
| `test_prepare_preflight.py` | 28 | red |
| `test_leg_precheck.py` | 52 | red |
| `test_leg_lifecycle.py` | 97 | red |
| `test_harvest.py` | 12 pass, 1 fail (F1) | red |
| `test_run_control.py` | 27 | red |
| `test_matrix.py` | 24 | red |
| `test_fixtures_selfcheck.py` | 21 | pass (checks the fake against real parsers) |

**Baseline.**
- The "Baseline" column is the delivery-1 run (`191 failed, 30 passed, 201 errors`). It was taken before the amendments, so it does not cover them.
- The amended tests all depend on the candidate's new surface. Without it they fail or error, apart from the invariant tests.
- A blocked-import plugin run failed at collection, so it gave no evidence. I deleted the plugin.

## Amendments (test, old reading, new reading, why)

**Interface adaptations** (the designer's P2–P8 and P10 resolutions):
- **`helpers.py`:** uses the candidate's `Config`, `parse_args`, `prepare(ops, cfg)` (returns a problem list), `preflight(arm, ops, cfg, max_retries)` (returns a record) and `matrix(cfg)`.
- **`fakes.py` git facts:** the fake now answers `rev-parse refs/heads/<branch>`, `diff --name-only`, `show <rev>:main_models.yaml` and `ls-tree <base>`. The arm registry is built independently of the candidate.
- **`fakes.py` other:** qualify-style `report.json` (no top-level status), `cmdline` as a list as `RealOps` returns it, `env_base()` on the stack handle, driver duration taken from `--expected-rung-seconds`, and a venv stub in each arm worktree.
- **`test_bench_watch_capacity.py`:** reads rate and ETA from the candidate's nested `rate.ratio` / `eta.eta_s`. The injected power meter now carries `on_battery_intervals`, so the battery window counts as proven. This fixed a test defect.
- **`test_leg_precheck.py`:** the R1 diff-text tampering became registry-text tampering. I added three new cases:
  - AF8 passing as TQ8 (scheme turboquant),
  - N16 with `kv_bits: 4`,
  - N16 keeping the turboquant scheme line.
- **`test_run_control.py`:** `legs()` is derived from receipts instead of driver tags. A leg that is INVALID before its driver has no driver. The 600 s check now measures from the previous stop, with 0.5 s slack for the fake's clock jitter.
- **Fake bugs fixed:**
  - `pmset` text no longer prints `140.0W`.
  - The smoke leg-name regex.
  - Setup events no longer pollute lease counts.
  - Preflight attempt directories are no longer counted as records.
  - Zip/gz evidence logs are read correctly.

**Behavioural amendments:**
- **P1 (env stripping):**
  - Removed the three `os.environ` router-side assertions.
  - Kept the worker-env refusal, now parametrized over `KV_BITS`, `KV_GROUP_SIZE`, `TQ_KV_QUANT_MODE`, `TQ_PREFILL_IMPL` and two prefix-only names.
  - Added a driver-env test for names the router handle hands out.
  - Added a `RealOps.stack` test that builds the stripped router environment, including a `.env` containing `KV_BITS`, with no live box.
- **P9 (preflight cap):**
  - Old: `--max-preflight N` meant N attempts.
  - New: 1+N attempts (default 3).
  - Why: the designer's resolution, and it is the contract's literal reading.
  - Removed my "final record is not redone" and "busy box" tests, which the contract doesn't support.
- **Matrix strengthening:**
  - Ratios are now exact: `0.950`, `0.952`, `0.500` and `0.524` for the clean run, `0.988` and `1.007` for the deciding run.
  - Instability is matched as `REVERSAL|SPREAD`. The old `instab|unstable` regex would match the always-present column header.
  - A clean run must print no flag.
  - "Descriptive" is compared case-insensitively.
- **Dossier tampering:** after each tamper I re-sign the dossier's `SCRUB_MANIFEST.json` hashes. Only the semantic rules (one ladder file, strict rung re-judging, receipt verdict and `speed_valid`) can then refuse the dossier. Without that, the integrity hash would refuse it first.
- **Dropped test:** a pre-existing `evidence-stage/<leg>` as a refused destination. The contract doesn't list it (F2).
- **Added tests (new coverage):**
  - Spawn failure tears down the stack.
  - An interrupt during the driver wait is receipted and re-raised after teardown, with the lease released.

## Findings

**Candidate defects**
- **F1 (must fix): an INVALID smoke leg is not terminal on resume.** `p475_kv.py:1487-1490` runs a new attempt whenever the smoke status isn't `valid`. In the failing test, an INVALID `u4-n16-smoke.a1` is followed by a VALID `.a2` and `run` exits 0. The INVALID evidence is superseded and the run exit hides it. The contract says INVALID stops the run, and the implementer's own P5 says a resume stops at a standing INVALID leg. The non-smoke path does this at `p475_kv.py:1392-1393`. Failing test: `test_harvest.py::test_an_invalid_canonical_receipt_wins_over_a_valid_variant`.

**Observations (no failing test, designer's call)**
- **F2:** `_destinations` (`p475_kv.py:591-594`) omits `evidence-stage/<leg>`, and `harvest` (lines 1064-1066) overwrites existing evidence logs with `exist_ok`/`write_bytes`. That is low risk, but AGENTS.md says never overwrite.
- **F3:** `_reap_driver` (`p475_kv.py:704-718`) only signals while the driver pid is alive. After a normal exit its grandchildren aren't group-killed. The `busy()` check (`run_capacity` pattern) is the only backstop.
- **F4 (operational):** arm worktrees are cut from `--base`. The candidate files (`p475_kv`, `bench_watch` capacity mode, `--p475-strict`) must be committed in that base before `prepare`. Otherwise the arm's driver and watcher lack them and the legs fail as INVALID (a safe failure, not a false VALID).
- **F5:** the NOT_STARTED cap is a single counter for the whole run (`p475_kv.py:1364-1366`), not per leg. Three isolated transient refusals on different legs stop the run.
- **F6:** a flagged instability with `--max-deciding 0` still exits 0. The table shows the flag.

## Threat review

- **False VALID:** guarded by exact worker argv equality, the KV line taken only from log text since the load, a worker-env check, strict per-rung re-judging (including session prefix and uniqueness), exit-identity re-read, and survivor checks. Every refusal path is tested.
- **Quantized arm passing as N16:** the N16 KV-line check compares only `kv_bits`, as the contract says. The defence is argv equality plus registry identity. Tested: an N16 registry with `kv_bits: 4`, or with the scheme kept, is NOT_STARTED.
- **Lease:** held across harvest and released on every path, including INVALID and an interrupt. A refused lease gives NOT_STARTED with nothing started.
- **Survivors:** worker, `:8000` listener, router and wrapper are each tested. The driver is bounded by TERM then KILL, and an unkillable driver is INVALID without an unbounded wait.
- **Receipt overwrite:** `os.link` means a second write goes to `receipt.refused-<ns>.json`. The canonical receipt wins, and `.refused-` variants never change the verdict.
- **PII:** a row containing a home-path string refuses the harvest. No final dossier appears, the receipt stays, and `LAST_LEG_END` is untouched. Resume replays the harvest.

## Deviations from the contract

- **Driver timeout:** the candidate uses 3 × expected + 900 s (stated, to cover preload and calibration).
- **Watcher tick count:** `(span − 2×interval) // interval`, which is identical at 300 s.
- **Preflight PASS:** read from `entries[<pick>].status`.
- **Dossiers:** an INVALID dossier may have zero ladder files.
- **Matrix:** always requires blocks 1 and 2.

## Not verified

`RealOps` I/O is untested beyond its stripped router environment. The worker-environment check assumes psutil doesn't see the fork's in-process `KV_BITS`. If it does, every quantized arm comes back INVALID at the smoke leg, so it fails safe.

**Fixes before merge:** F1. Decide F2, F3 and F5, and commit the candidate into the base before `prepare` (F4).
