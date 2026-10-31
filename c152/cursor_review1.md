T1 — HIGH — `benchmark/bench/tg1_runner.py:856-879`, `benchmark/m62/inject_verify.py:220-240`  
Alloc can falsely PASS. `_link_mem_kills` assigns the sole shell call without argv correlation, while the verifier fully checks only `kills[0]`. A killed git/LSP process can therefore be attributed to an unrelated errored shell call; later collateral kills are never linkage-checked. Require argv/command correlation and validate every kill, with at least one satisfying the complete positive chain.

T2 — MEDIUM — `benchmark/bench/proc_guard.py:393-426`  
The 24 MiB limit covers every model→model child, including `opencode serve` infrastructure such as git or an LSP. Current measurements reduce the likelihood but do not enforce safety. `serve`, client, worker, and router are protected under the current tree; campaign mode also remains unaffected. Add actual tool-call attribution before applying the limit, or explicitly reject unlinked collateral kills.

T3 — MEDIUM — `benchmark/bench/opencode_export.py:24-31`  
The retry is not bounded to 10 seconds. A failure just before the deadline sleeps past it and starts another attempt, which can run for the callers’ 120-second timeout. Recheck before spawning and cap each retry to the remaining deadline. Add a test where sleep crosses the deadline.

T4 — MEDIUM — `docs/specs/c147-tg1-chain-clearance.md:72,322-324`  
The authoritative predicate and acceptance criteria still require exactly one 512 MiB `bytearray` kill, contradicting C152’s implemented ≥1 tool-scoped kill contract. Update these sections; retain the bytearray case only as synthetic V2 coverage.

T5 — LOW — `docs/open-questions.md:18`  
C152 still recommends waiver A and says option C requires new harness surface, although the operator selected and implemented that surface. Record the ruling and close/update C152.

Campaign policy hash, absence of `tool_per_process` from `pg.POLICY`, and campaign interval 0.5 are correctly pinned. P273 otherwise preserves stdout parsing, uses an environment copy, and only retries nonzero exits containing the lock text.

The new tests bite old code, but they do not cover T1 or T3. I did not execute pytest.

not cleared
