1. Location: `benchmark/bench/p475_kv.py:253-313, 529-533`; `benchmark/bench/chain_ops.py:253-267`; `mlx-vlm/mlx_vlm/server/runtime_config.py:327-336`  
Severity: blocker  
Problem: The router inherits `.env` KV overrides, but validation checks only global bits, scheme, and start. Split key/value bits and schemes, group size, and `TQ_KV_QUANT_MODE` can change the actual format unnoticed. The qualify subprocess does not source the arm `.env`, so its passed manifest does not protect router legs from this difference.  
Concrete failure scenario: `.env` contains `KV_VALUE_BITS=3`. An AF8 worker actually serves K8/V3, while argv and `KV cache resolved` checks accept it as AF8. Its measurements enter the canonical matrix under the wrong format.  
Proposed change: Strip all KV-related environment overrides from router and driver environments, and validate every resolved KV field—including split bits/schemes, group size, and TurboQuant mode.

2. Location: `benchmark/bench/p475_kv.py:902-910, 983-1027`  
Severity: major  
Problem: A watcher that exits early or records no tick adds an ordinary `problem`, making the leg `INVALID`. Watcher/power instrumentation failure should make it `SPEED_INVALID` and queue a replacement.  
Concrete failure scenario: The watcher crashes after an hour of an otherwise valid leg. Instead of preserving the leg and rerunning that cell, the entire campaign stops.  
Proposed change: Put watcher lifecycle and coverage failures in `speed_problems`; reserve `INVALID` for measurement/engagement failures.

3. Location: `benchmark/bench/p475_kv.py:819-841, 569-585, 912-917`  
Severity: major  
Problem: Watcher coverage and power-history windows are not bound to the measured driver interval. `t_start`/`e_start` are captured before router startup and model loading, while watcher ticks begin after driver launch; power history ends after teardown.  
Concrete failure scenario: A slow five-minute model load makes a fully functioning watcher appear to stop early. Conversely, unplugging after the driver finishes but during teardown invalidates valid speed data.  
Proposed change: Capture measurement start immediately before driver launch and end immediately after driver completion; use that exact interval for watcher coverage and `pmset` reconciliation.

4. Location: `benchmark/bench/p475_kv.py:961-967, 1070-1117`  
Severity: major  
Problem: A crash or write failure after the durable receipt but before completed harvest is unrecoverable. Resume stops when it finds a receipt without `SCRUB_MANIFEST.json`; a partial dossier also blocks re-harvest.  
Concrete failure scenario: Disk pressure interrupts publication of leg 14. All measurements remain available, but every resume stops on leg 14 and no CLI can safely complete its harvest.  
Proposed change: Stage each dossier in a temporary directory and atomically rename it after verification. On resume, replay harvest when a receipt exists but the finalized dossier does not.

5. Location: `benchmark/bench/p475_kv.py:952-969, 1049-1057, 1513-1516`  
Severity: major  
Problem: Resume reconstructs instability inputs from expendable instrument outputs rather than harvested rows.  
Concrete failure scenario: After block 2, the operator cleans original result files because they were harvested. Resume records empty metrics, fails to detect instability, skips block 3, and declares the sequencer done.  
Proposed change: Reconstruct resumed metrics exclusively from validated harvested dossiers.

6. Location: `benchmark/bench/p475_kv.py:1351-1370, 1543-1549`  
Severity: major  
Problem: Normal orchestration suppresses every matrix-generation failure and still returns the sequencer’s success status. It also returns zero when `_write_matrix` produces only `MATRIX.PARTIAL.md`. `--regenerate-matrix` is ignored outside matrix-only mode.  
Concrete failure scenario: Twenty legs succeed, but an existing `MATRIX.md`, missing harvested row, or filesystem error prevents the new canonical table. The process exits zero and logs `DONE` despite not delivering its required output.  
Proposed change: Make canonical matrix creation part of successful completion; propagate failures or partial output as nonzero, and honor explicit regeneration during normal runs.

7. Location: `benchmark/bench/p475_kv.py:1410, 1431-1436`; `benchmark/bench/tests/test_p475_fix_round.py:827-833`  
Severity: major  
Problem: The candidate adds `--picks` semantics that allow a subset—or even an empty list—to produce canonical `MATRIX.md`, although the Goal requires both picks. Duplicate picks also reuse cells while inflating planned counts.  
Concrete failure scenario: `--picks fable` produces a canonical matrix containing only one pick; `--picks ''` can produce an empty canonical matrix with exit zero.   <!-- allow-shorthand: verbatim reviewer output -->
Proposed change: Require the exact two-pick set for canonical output. Treat subset runs as explicitly named partial diagnostics, and reject empty or duplicate lists.

8. Location: `benchmark/bench/chain_ops.py:540-572, 622-655`; `benchmark/bench/p475_kv.py:888-893`  
Severity: major  
Problem: The candidate trusts `stop_stack()` as proof of complete teardown, but it ignores a failed `unload()` and returns success solely when port 8000 is free. It does not prove the worker or router process group is gone.  
Concrete failure scenario: Unload times out, the router releases port 8000, but `mlx_vlm.server` survives. The completed leg remains VALID; subsequent legs spend repeated idle/retry cycles refusing the busy box.  
Proposed change: Fail teardown unless the loaded worker, listener, spawned wrapper, and owned process group are all verified gone; propagate unload failure.

9. Location: `benchmark/bench/capacity_ladder.py:20-53, 212-231`  
Severity: major  
Problem: Strict validity accepts backend telemetry without reconciling it. It does not require `predicted_n == 256`, verify `prompt_per_second == prompt_n / prompt_ms`, or reject draft-key presence when counters are zero.  
Concrete failure scenario: Usage reports 256 tokens while backend timings report `predicted_n=128`; the matrix still publishes that backend decode rate as a 256-token carrier result.  
Proposed change: Persist and validate `predicted_n`, reconcile timing arithmetic and token counts, and reject draft telemetry by key presence. Keep these checks opt-in so non-P475 callers remain unchanged.

10. Location: `benchmark/bench/p475_kv.py:823-837`  
Severity: major  
Problem: Router-config, worker-argv, and KV-line failures are recorded but do not prevent launching the expensive capacity driver. This violates the specified pre-driver check order.  
Concrete failure scenario: The first TQ8 leg resolves AF8. The mismatch is known immediately after model load, but the harness still runs the full long ladder before marking it INVALID and stopping.  
Proposed change: After load, abort and tear down before driver launch if any config, argv, KV-line, or predictor precondition fails.
