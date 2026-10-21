# P415 — code review round 2 of 3 (Cursor gpt-5.6-sol-high, `--mode ask`), fork `p369-v13` `bbe7a8cd`

Production check passed: `git diff 7207179b bbe7a8cd -- mlx_vlm ':!mlx_vlm/tests'` is empty.

Round-1 findings

D1 — CLOSED — `dev/p369_phase2/qualify.py:142-151`  
The omitted/default per-query policy is now normalized to `None`, matching `served_state()`.

D2 — CLOSED — `dev/p369_phase2/worker.py:1275-1304`, `dev/p369_phase2/qualify.py:342-362`  
The producer and validator now use the same recorded memory fields, and wrappers are removed before measurement.

D3 — CLOSED — `dev/p369_phase2/qualify.py:306-327`, `dev/p369_phase2/worker.py:1418-1436`  
The measured cache is checked path-by-path against the independent registry-derived manifest, with exact capacities.

D4 — CLOSED by the stated design — `dev/p369_phase2/qualify.py:403-414,636-656`, `dev/p369_phase2/worker.py:1321-1343,1420`  
The stack command’s interpreter and registered `mlx_vlm.server:main` entry point are checked, while the worker proves the candidate tree’s `server.main → cli.main` path. Not requiring the pre-bump stack installation itself to resolve into the candidate tree is coherent with the qualification-before-submodule-bump workflow.

D5 — OPEN — High — `dev/p369_phase2/qualify.py:696-699,743-786,822-829`  
The reviewed fork ref, fork cleanliness, stack HEAD, registry, and mlx-serve submodule are rechecked. However, `console_script_info()` runs only once at startup; executable/interpreter/entry-point checks are not repeated after each job or at exit as D5 required. A mutation under the ignored stack `.venv` can therefore leave an entry COMPLETED. Re-run and compare the complete console-script attestation at every boundary and include it in the exit guard.

D6 — CLOSED — `dev/p369_phase2/qualify.py:798-821`  
All evidence and comparisons are finalized before the terminal status is applied and atomically written.

D7 — CLOSED — `dev/p369_phase2/worker.py:1523-1531`  
The MTP boundary now runs on entry to `run_speculative_rounds`, before its target-cache buffering and drafter setup.

D8 — CLOSED — `dev/p369_phase2/qualify.py:63-66`  
The default run now contains all seven entries; Qwen3.6 still requires its gate.

D9 — CLOSED — `dev/p369_phase2/qualify.py:356-400`, `dev/p369_phase2/worker.py:1413-1418`  
The expected cache limit is independently derived from the loaded head count and exact production formula.

D10 — OPEN — Medium — `dev/p369_phase2/qualify.py:69-94`  
The gate checks additional provenance fields, but they are only self-consistency assertions inside caller-supplied JSON. A minimal fabricated summary with `fork_head == reviewed_head == "fake"`, the production string, and two PASS fields is still accepted; I reproduced `entry_problems(...) == []`. Validate the complete P369 binding and pick evidence against a prescribed reviewed commit/artifact, and recompute the durable full-run outcome rather than trusting stored PASS strings.

D11 — OPEN — Medium — `dev/p369_phase2/qualify.py:448-503,909-939`  
An existing blob is required, but it is not proven to be the blob of the named source. The fingerprint still records neither weight-file hashes nor the reviewed fork revision—`harness="p415"` is only a constant. Carry the worker-verified full snapshot attestations, reviewed commit, and resolved source path/blob identity into the mandatory fingerprint.

D12 — OPEN — Medium — `dev/p369_phase2/qualify.py:433-440,794-797`, `dev/p369_phase2/orchestrate.py:1294-1338`  
A dead thread is detected, but a live thread blocked during its first scheduled tick remains acceptable for two full periods. I confirmed `alive=True, last_tick_age_s=599, period_s=300` returns no problem, so an eight-minute job can complete with only the startup tick. Record tick start/completion and exceptions, and reject after one period plus bounded scheduling slack.

D13 — OPEN — Low — `dev/p369_phase2/qualify.py:679-683,830-843`, `dev/p369_phase2/orchestrate.py:1331-1338`  
The initialization scope is now inside `try`, but lock release is still after fallible report writing and `monitor.__exit__()`, which itself performs another power tick. A startup/cleanup tick failure caught by an embedding caller can still bypass `release_lock()`. Put lock release in an outer, unconditional `finally`.

New findings

E1 — High — `dev/p369_phase2/qualify.py:774-777,926-928`; `dev/p369_phase2/worker.py:67-94,1588-1590`  
Problem: `check_snapshots()` returns `{flag: revision_string}`, but `fingerprint_of()` treats each value as a dictionary and calls `v.get("revision")`.  
Failure scenario: The first successful entry with a reference—Fable in default order—finishes its expensive GPU request, then raises `AttributeError: 'str' object has no attribute 'get'` during finalization. The driver aborts and marks the run NOT_RUN. The test hides this by fabricating nested dictionaries.  
Fix: Use the actual returned string shape or, preferably, return/carry the complete verified revision-plus-file-hash attestation. Add a lifecycle test using `check_snapshots()`’s real return schema.

E2 — Medium — `dev/p369_phase2/qualify.py:534-536,759-773`; `dev/p369_phase2/orchestrate.py:1341,1736-1742`  
Problem: The specified 600-second boot limit is dead configuration. `BOOT_S = 600` is never passed; `run_job()` uses the shared 900-second `BOOT_TIMEOUT_S`.  
Failure scenario: A worker taking 601–900 seconds to boot can still be marked COMPLETED despite violating the pre-registered qualification deadline.  
Fix: Make the qualification job pass or override a 600-second boot timeout and add a boundary test proving 600 seconds is enforced.

VERDICT: NOT CLEARED D5,D10,D11,D12,D13,E1,E2