F2 — partially resolved — production wiring is correct, but the availability probe accepts every non-404 HTTP failure; see F11 (`benchmark/bench/worker_receipts.py:263-277`).

F3 — resolved — task totals now use receipt-owned tokens; gate totals remain separate (`benchmark/bench/arm_runner.py:769-778`).

F4 — resolved — move intents are durable and idempotently rolled forward before inventory reads (`benchmark/bench/chain_core.py:1221-1293`).

F5 — resolved under the lead call — exact validation covers all `incident_retry` paths; tg1 retains C147 semantics (`benchmark/bench/chain_core.py:1720-1739`).

F6 — partially resolved — M64 post-barrier aborts work, but early cancellation and tg1 aborts still lose A12 evidence; see F14–F15 (`benchmark/bench/chain_core.py:1483-1489`).

F7 — partially resolved — identity stores the resolved entry, but execution still uses the raw CLI path; see F12 (`benchmark/bench/chain_core.py:314-316`).

F8 — resolved — interpreter differences remain visible and lifecycle additions require re-derivation (`benchmark/bench/tests/p371_baseline/compare.py:40-57,130-138`).

F9 — resolved — persisted accepted/exhausted prefixes are salvaged (`benchmark/bench/chain_core.py:2009-2071`); tg1 has no item barrier or `.continue` state.

F10 — partially resolved — complete orphan receipts are adopted, but a crash during publication leaves an unrecoverable torn destination; see F13 (`benchmark/bench/chain_core.py:1096-1143`).

F11 — high — `benchmark/bench/worker_receipts.py:263-277` — GET/405 correctly proves a POST-only route, but 401/403/5xx also pass; discovery then spawns before POST fails. Fix: accept only 2xx/405 and treat every other status as unavailable.

F12 — high — `benchmark/bench/chain_core.py:314-316` — a repository symlink passed via `--probe` is resolved into the frozen config but the raw symlink is executed; retargeting it after initialization launches code outside the frozen closure. Fix: always execute `repo / ArmBinding.probe`.

F13 — medium — `benchmark/bench/chain_core.py:1102-1114,1136-1143` — death after `O_EXCL` creation but before complete fsync leaves an unreadable reserved receipt that resume permanently refuses. Fix: fsync a temporary file, then atomically link it into the reserved destination.

F14 — high — `benchmark/bench/chain_core.py:1483-1489,2284-2290` — if STOP/cancellation begins before the supervisor observes the manifest, later manifest hydration is skipped because `att.run_id` remains null; cleanup and abort evidence are lost. Fix: validate and hydrate from the invocation’s final manifest after exit.

F15 — high — `benchmark/bench/arm_runner.py:1240-1248`; `benchmark/bench/arm_opencode.py:239-241`; `benchmark/bench/chain_core.py:1620-1630` — tg1 suppresses abort evidence, while fallback extraction covers only committed rows; a pre-row transport abort has neither raw web evidence nor explicit unavailable evidence, contrary to A12. Fix: stamp evidence independently of gate-token reporting and amend A14 for the intentional manifest addition.

VERDICT: NOT CLEARED F11 F12 F13 F14 F15
