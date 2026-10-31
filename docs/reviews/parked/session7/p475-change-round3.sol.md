1. Location: `benchmark/m1/bench_watch.py:218-246`; `benchmark/bench/tests/test_p475_bench_watch.py:21-48`  
Severity: blocker  
Problem: Capacity rows have `elapsed_s`, but the slowdown diagnostic still sorts and formats `wall_s`. Once `rate_hist` has three entries and a tick makes no progress, formatting `None` raises `TypeError`, killing the power watcher. Tests cover elapsed-time ETA but never this slowdown branch.  
Concrete failure scenario: During a 10+ minute 256K rung, two flat five-minute ticks trigger the exception. The leg becomes `SPEED_INVALID`; every replacement repeats the failure until its cap is exhausted.  
Proposed change: Use one `wall_s or elapsed_s` accessor throughout the diagnostic and add an elapsed-only flat-tick regression test.

2. Location: `benchmark/bench/capacity_ladder.py:44-86`  
Severity: major  
Problem: Strict validity reconciles `prompt_n` with its own rate and time but never with API `prompt_tokens`. Tests use internally consistent fake timings and miss contradictory usage/timing counts.  
Concrete failure scenario: A 131K request reports `prompt_tokens=131072`, `cache_n=0`, but `prompt_n=65536` with matching `prompt_ms` and rate. The rung passes and publishes a mislabeled prefill result.  
Proposed change: Require `prompt_n + cache_n == prompt_tokens`; therefore P475 requires `prompt_n == prompt_tokens`.

3. Location: `benchmark/bench/p475_kv.py:839-843, 1053-1064, 1424-1449`; `benchmark/bench/tests/test_p475_kv.py:255-259`  
Severity: major  
Problem: The orchestrator and dossier validator trust persisted `p475_valid: true` instead of revalidating strict fields. The standard `good_rows()` fixture omits `prompt_ms`, `prompt_n`, `predicted_n`, and `predicted_ms` yet is accepted.  
Concrete failure scenario: A mismatched or regressed driver writes `p475_valid=true` with missing backend telemetry; the leg becomes VALID and its dossier supplies canonical metrics.  
Proposed change: Persist sufficient raw telemetry and run one shared strict row validator in `run_leg`, resume validation, and matrix generation.

4. Location: `benchmark/bench/p475_kv.py:607-631, 1183-1199, 1424-1450, 1870-1877, 2020-2024`  
Severity: major  
Problem: Resume state comes from expendable local receipts, while completed dossier identities are not compared with the current base, production ref, or harness. Tests always retain a separate verdict source and never resume across changed campaign inputs.  
Concrete failure scenario: Deleting `--out/receipts` after ten harvested legs makes resume retry them and stop on existing destinations. Conversely, retaining receipts but changing `--base-commit` silently mixes old and new stack legs.  
Proposed change: Persist a campaign identity manifest and reconstruct resume state from validated harvested dossiers; reject any identity mismatch.

5. Location: `benchmark/bench/p475_kv.py:1483-1497, 1546-1556, 1638-1645`  
Severity: major  
Problem: Matrix generation bypasses `SCRUB_MANIFEST.json` hash validation. Tamper tests exercise `validated_dossier_metrics()` only; matrix tests use unmanifested synthetic dossiers.  
Concrete failure scenario: A harvested `predicted_per_second` is edited from 50 to 500 while its manifest retains the old SHA. `--matrix-only` publishes 500 successfully.  
Proposed change: Make matrix loading consume the same manifest-verified dossier validator and reject unlisted, missing, or hash-mismatched files.

6. Location: `benchmark/bench/p475_kv.py:552-603, 620-631, 1274-1298`  
Severity: major  
Problem: Power, busy-host, lock, missing-tool, and qualify-crash failures are counted as arm-format refusals. Tests collapse every `ok=False` result into one category.  
Concrete failure scenario: Two transient unreadable power checks permanently exclude AF4, after which the harness spends hours measuring the other arms and delivers an incomplete table. No KV mismatch was established.  
Proposed change: Separate environmental `NOT_STARTED`, harness failure, and actual engagement mismatch. Only the last may refuse an arm; exhausted infrastructure retries should stop the campaign.

7. Location: `benchmark/bench/p475_kv.py:79, 861-875`; specification `docs/specs/p475-kv-matrix.md:61-63`  
Severity: major  
Problem: The added 3% spread floor weakens the specified instability rule, which says any direction reversal triggers a deciding block. Round-3 tests explicitly preserve this extra behavior.  
Concrete failure scenario: Ratios 0.99 and 1.01 reverse direction but have only 2% spread, so no block 3 runs and a canonical matrix is published.  
Proposed change: Implement the specification literally, or amend and review the specification before introducing a noise floor.

8. Location: `benchmark/bench/p475_kv.py:1207-1213, 1529-1539, 1605-1613, 1852-1858`  
Severity: major  
Problem: An exhausted deciding cell is treated as complete and permits exit zero. Tests explicitly assert this behavior.  
Concrete failure scenario: AF8 triggers block 3, but AF8-b3 and both replacements are speed-invalid. `MATRIX.md` is still canonical although it lacks the comparison intended to resolve AF8’s instability.  
Proposed change: Continue other b3 cells if useful, but keep the pick incomplete/nonzero until the deciding cell has a speed-valid result or the operator explicitly waives it.

9. Location: `benchmark/bench/p475_kv.py:1833-1858, 2047-2053`  
Severity: major  
Problem: Exclusive per-pick matrices can become stale after recovery. Completeness checks only require that the old file exists. No test recovers an arm after an incomplete table was delivered.  
Concrete failure scenario: AF4 is initially refused, creating an incomplete `MATRIX.fable.md`. A later run raises the refusal cap, measures AF4, and creates a fresh combined matrix, but keeps the stale per-pick table and exits zero.  
Proposed change: Do not create canonical per-pick files for incomplete picks, or generate a numbered superseding table and verify current harvest identity before success.

10. Location: `benchmark/bench/p475_kv.py:1821-1824, 1906, 1938-1949, 2077-2083`  
Severity: major  
Problem: Normal `--picks` subsets and reordering are beyond the specification yet can exit successfully. Tests accept subset success and do not test reversed order.  
Concrete failure scenario: `--picks uniform4,fable` produces a successful combined campaign with Uniform4 first; `--picks fable` exits zero after only half the required matrix.   <!-- allow-shorthand: verbatim reviewer output -->
Proposed change: Require the exact ordered pair for campaign runs; reserve subsets for explicitly incomplete diagnostic/matrix-only operation.No further action required.Additional findings:

1. Location: `benchmark/bench/chain_ops.py:23-24,335-346`; `benchmark/bench/p475_kv.py:827-829`  
Severity: major  
Problem: Busy detection omits orphaned `qualify.py`, `bench.run_capacity`, and watcher processes.  
Concrete failure scenario: The orchestrator is killed; its detached qualification survives. Resume starts another GPU workload concurrently.  
Proposed change: Add P475 workloads to the busy gate or persist and verify their PID identities.

2. Location: `benchmark/bench/chain_ops.py:425-440`  
Severity: major  
Problem: Failed router startup cleanup stops when the wrapper PID exits, without proving its process group is gone.  
Concrete failure scenario: The wrapper exits on SIGTERM while a child ignores it and survives, retaining resources or later binding the port.  
Proposed change: Check group liveness independently, escalate with group SIGKILL, and verify termination.

3. Location: `benchmark/bench/p475_kv.py:1292-1298`  
Severity: major  
Problem: Preflight-refusal harvest failures are logged but do not stop the campaign or get replayed.  
Concrete failure scenario: Disk pressure prevents refusal evidence publication, yet remaining expensive legs run and resume counts the non-durable refusal.  
Proposed change: Stop immediately on harvest failure and replay unharvested refusal records before counting them.

4. Location: `benchmark/bench/p475_kv.py:1044-1050`; `benchmark/m1/bench_watch.py:310-329`  
Severity: major  
Problem: Power is sampled after the measured interval ends.  
Concrete failure scenario: Unplugging immediately after driver completion invalidates otherwise valid measurements and queues a replacement.  
Proposed change: Timestamp and evaluate samples only within the driver interval; skip power sampling once the driver is known gone.
