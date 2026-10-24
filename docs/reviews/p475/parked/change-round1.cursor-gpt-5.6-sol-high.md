1. Location: `benchmark/bench/p475_kv.py:94-163, 468-480, 830-863`  
Severity: blocker  
Problem: Arm commit/build state is trusted from `arms.json`; it is never read from Git. There is no enforcement of a common P476 base, reviewed mlx-vlm/mlx-serve revisions, clean worktrees, or unchanged build at exit. The capacity manifest describes the instrument checkout, not necessarily the arm worktree that launched the router.  
Concrete failure scenario: `arms.json` says an arm is clean and based on P476, but its worktree has an uncommitted server change or different submodule revision. That code serves the leg while provenance records the unchanged instrument checkout, producing a falsely “matched” matrix.  
Proposed change: Derive all arm metadata from each worktree at entry and exit; pin one common base and the specified serving revisions; verify clean state, parent/diff, submodule commits, and record those identities in the receipt and harvest.

2. Location: `benchmark/bench/p475_kv.py:303-315, 487`  
Severity: major  
Problem: The gate lock is sampled and immediately released; the orchestrator never owns a lease during the leg.  
Concrete failure scenario: Two orchestrators both observe an unlocked gate and empty port, then race to start routers. Ownership checks prevent silent reuse but abort a leg after idle and setup, potentially disturbing the competing run.  
Proposed change: Acquire a nonblocking shared/exclusive flock atomically and hold its file descriptor through driver completion and teardown.

3. Location: `benchmark/bench/p475_kv.py:329-361`; `benchmark/m1/bench_watch.py:197-214`  
Severity: major  
Problem: The independent watcher cannot produce the required mean-rate/ETA assessment. It reads `wall_s`, while capacity rows contain `elapsed_s`; no expected-duration baseline is supplied either. Tests verify only argv and PID binding.  
Concrete failure scenario: An 80-minute TQ leg emits progress and power ticks but no RATE/ETA section, so a severe slowdown is not evaluated unattended.  
Proposed change: Teach the watcher’s capacity mode to use `elapsed_s` and pass matched expected rung durations for prediction comparison; test actual report content.

4. Location: `benchmark/bench/p475_kv.py:350-361, 565-571`  
Severity: major  
Problem: Any nonzero tick count is accepted as a valid watcher/power receipt, regardless of leg duration.  
Concrete failure scenario: The watcher writes its initial tick and is then stopped or hung without exiting. A two-hour leg is accepted as speed-valid despite having no subsequent five-minute power observations.  
Proposed change: Validate tick count and cadence against the measured leg span, failing speed validity when expected ticks are missing; also reconcile `pmset` power-source history to catch gaps between ticks.

5. Location: `benchmark/bench/p475_kv.py:367-371, 516-526, 557-562`  
Severity: major  
Problem: A timed-out capacity driver is neither terminated nor reaped. It is also not started in its own process group.  
Concrete failure scenario: A 256K request exceeds the seven-hour wrapper timeout. The router is stopped while `bench.run_capacity` remains alive; it may continue writing artifacts or interact with the next router, and `busy_procs()` does not identify it.  
Proposed change: Launch the driver in its own session; on timeout terminate, escalate to kill, wait, and verify it is gone before watcher shutdown and stack teardown.

6. Location: `benchmark/bench/p475_kv.py:621-640, 663-699`  
Severity: major  
Problem: The 600-second idle clock starts before harvest. Scrubbing, hashing, and possible LZMA compression count as “idle.” The idle test does not advance time during harvest.  
Concrete failure scenario: Harvesting a large worker log consumes several CPU-heavy minutes, after which only the remaining portion of 600 seconds is quiet; the next speed leg starts thermally unmatched.  
Proposed change: Set `last_end` after harvest completes, then require a full 600 seconds of quiet time before the next leg.

7. Location: `benchmark/bench/p475_kv.py:50, 591-640`  
Severity: major  
Problem: The candidate adds an unspecified two-replacement cap and runs replacements immediately rather than as a queue after the ordered block. Once `r1` and `r2` are speed-invalid, resume can never create `r3` without altering evidence or code.  
Concrete failure scenario: Three transient power failures on one arm permanently stop the campaign, and adjacent reruns distort the specified block ordering.  
Proposed change: Preserve the planned block order, queue speed-invalid cells for later replacement, and make any retry limit an explicit operator option that can continue monotonically on resume.

8. Location: `benchmark/bench/p475_kv.py:723-783, 793-798, 897-903`  
Severity: blocker  
Problem: `MATRIX.md` has no completeness validation and is written even when the run returns failure. Its header unconditionally claims two order-balanced speed-valid legs per arm.  
Concrete failure scenario: The third leg is INVALID; `main()` returns nonzero but overwrites the canonical matrix with two partial cells labelled as a complete descriptive screen. `--matrix-only` can do the same from an incomplete harvest.  
Proposed change: Refuse canonical matrix generation unless every requested pick/arm/block has complete valid rungs and required replacements. On failed runs, emit only a clearly labelled partial diagnostic at a separate path.
