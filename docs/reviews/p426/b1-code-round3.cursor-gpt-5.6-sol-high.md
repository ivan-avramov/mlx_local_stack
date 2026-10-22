D1 — CLOSED. The daemon processes cached requests synchronously at `generation.py:2677-2688`; `_step` runs only afterward at line 2811. Snapshot and diff occur inside that call at lines 1859-1870 and 1980-1983. Therefore no other drafted work can alter counters during a cached request, regardless of HTTP overlap.

D2 — CLOSED. The new streamed and non-streamed endpoint tests invoke the real `_process_cached_request`, exercise its lifetime-counter snapshot/diff, and verify ON→no-round log behavior. The bridge bypasses daemon submission, but D1 independently establishes the daemon dispatch invariant; continuous batching is excluded by the consumer gate.

E1 — CLOSED. `run_leg` takes a byte offset immediately before the driver, then requires that slice to contain exactly `expected_requests` starts and completions, zero failures, and `backend=cached_session` on every ON completion. Missing, extra, failed, or non-cached lifecycle records invalidate the leg.

G1 — MEDIUM — `benchmark/bench/p426_leg.py:219,235-249`  
Problem: Driver timeout exceptions escape `run_leg`; only `ChainAbort` is caught.  
Failure scenario: `_real_driver` reaches its six-hour timeout and raises `subprocess.TimeoutExpired`. Teardown runs, but log reconciliation, exit checks, battery checks, and the mandatory INVALID receipt are skipped.  
Fix: Catch timeout around the driver invocation, record it as a problem, and continue all post-driver checks and receipt writing.

G2 — MEDIUM — `benchmark/bench/p426_leg.py:237-248`; `benchmark/bench/chain_ops.py:623-656`  
Problem: `run_leg` ignores `stop_stack()` returning nonzero.  
Failure scenario: The router survives teardown or port 8000 remains bound; `stop_stack` returns 1, yet the leg can receive a VALID receipt.  
Fix: Capture the teardown result and append a leg problem when it is nonzero; also convert teardown exceptions into receipt problems.

G3 — HIGH — `benchmark/bench/p426_leg.py:238-240,274-294`  
Problem: Absence of a watcher power-failure receipt is treated as success without checking watcher health or exit status.  
Failure scenario: The watcher crashes early, misses an adverse-power interval, and leaves no receipt. Entry/exit power checks remain good, so the leg’s speed can be falsely certified valid.  
Fix: Make the watcher always write a completion receipt containing startup acknowledgement, tick coverage, and exit status; fail closed on premature/nonzero exit or insufficient coverage.

VERDICT: DISAGREE G1,G2,G3