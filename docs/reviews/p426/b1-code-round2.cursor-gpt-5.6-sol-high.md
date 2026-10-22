Round 2 of 3.

D1 — OPEN. The limitation is documented, and with complete balanced logs any overlap’s later request must start at `in_flight >= 2`. However, the enforcement fails open when start records are absent or unparseable; see E1.

D2 — OPEN. The added endpoint tests still inject terminal counters through `_fake_generator` (`mlx_vlm/tests/test_p426_draft_counters_log.py:92-284`). The existing cached-path test (`mlx_vlm/tests/test_server.py:9145-9255`) validates one worker seam, but there remains no real endpoint-to-worker integration, continuous `_step` snapshot/diff test, overlap test, or streaming cancellation/disconnect test. A continuous-path terminal-counter regression could therefore pass all cited tests. Fix: exercise cached and continuous `ResponseGenerator` output through an endpoint and log, including cancellation/disconnect and ON→no-round sequencing.

E1 — HIGH — `benchmark/bench/p426_leg.py:147-153,217-219`  
Problem: The attribution gate treats an absent log, zero parseable `Request started` records, and missing or duplicated records as clean. It only counts parseable records whose `in_flight > 1`; it does not reconcile starts and terminal records against expected requests.  
Failure scenario: The log path is wrong, logging is disabled, timestamps change format, or the relevant section is truncated. Rows still contain plausible response telemetry, engagement passes, `in_flight_problems([])` returns no problem, and contaminated counters are certified.  
Fix: Capture a fresh per-leg log slice and fail closed unless start and terminal records reconcile exactly with expected requests, with no missing, malformed, or duplicate records. Then require every start to report `in_flight == 1` and final in-flight state zero.

No generation, sampling, or API-response change was found in the production diff; it only extends metrics and completion logging.

VERDICT: DISAGREE D1,D2,E1