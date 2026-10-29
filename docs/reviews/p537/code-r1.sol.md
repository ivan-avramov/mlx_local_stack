P1 — `orchestrate.py.txt:2263-2281, 2511-2533, 2662-2671`  
Severity: major  
Evidence: confirmed  
Problem: successful non-64 E1c prompts remain local to `e1c`; `run_pick` later passes the original T−64 prompts to E2.  
Failure scenario: T=8192 succeeds only at offset 65, but E2 still runs its purported T8192 “straddle” with the known-invalid offset-64 prompt and can pass without checking a straddle.  
Proposed change: return/store each accepted prompt and offset from E1c, pass those prompts to E2, and add a regression test covering this handoff.

P2 — `orchestrate.py.txt:1886-1904`  
Severity: major  
Evidence: confirmed  
Problem: full-run projection assumes one E1c attempt per threshold. Smoke covers only 1024 and 65536, so threshold-specific retries at 8192 or 32768 are invisible.  
Failure scenario: smoke needs no retries, while full T8192 runs five offset-64 attempts before offset 65 succeeds. The projected runtime omits those attempts and may incorrectly authorize a run exceeding the estimate limit.  
Proposed change: make projection schedule-aware, conservatively accounting for all pre-registered attempts, or include every threshold in smoke and project from per-cell attempt timings.

P3 — `test_p369_phase2_orchestrate.py.txt:2733-2737`  
Severity: minor  
Evidence: confirmed  
Problem: `test_a_pick_that_is_on_in_the_stack_root_registry_is_refused` tests only the helper’s returned list; it never verifies that `Campaign.prepare` raises `Refused`.  
Failure scenario: the call at `orchestrate.py.txt:2169-2171` is removed or misplaced and this test still passes.  
Proposed change: construct a minimal campaign with an ON registry and assert `prepare()` raises `Refused` before argv generation.
