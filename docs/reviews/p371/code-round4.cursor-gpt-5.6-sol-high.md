F6 — resolved.

F14 — partially resolved — crash/foreign-manifest safety remains incomplete through F16/F20 (`benchmark/bench/chain_core.py:1038-1049,1553-1619`).

F15 — partially resolved — crash recovery can still lose abort evidence through F20/F22 (`benchmark/bench/chain_core.py:1038-1049,1578-1619`).

F16 — partially resolved — stable fields and in-chain run-ID reuse are checked, but no chain-issued invocation nonce binds the manifest; a fresh-ID foreign manifest with matching worker/config still passes (`benchmark/bench/chain_core.py:1553-1576`).

F17 — partially resolved — hydration precedes salvage, but its completion test is unsafe and moved records become dangling (`benchmark/bench/chain_core.py:1038-1049`).

F18 — partially resolved — true pre-manifest exits work, but all unusable manifests are attributed to the head slot (`benchmark/bench/chain_core.py:1599-1607`).

F19 — resolved.

Hermetic scan — no uncovered production-path blocker: it hides the known unobserved `setsid` escape from ordinary tests, while the production-relevant test explicitly opts out (`benchmark/bench/tests/test_proc_guard.py:264`); A14 remains parity coverage, not full-box-sweep coverage.

F20 — high — `benchmark/bench/chain_core.py:935-940,1038-1049,1595-1619` — interruption or evidence-extraction failure after `manifest_problem` is set can persist partial hydration; resume skips it merely because the key exists, silently bypassing missing evidence or transcript-integrity failure. Fix: persist an explicit `manifest_hydrated` flag only after hydration completes; otherwise retry idempotently.

F21 — medium — `benchmark/bench/chain_core.py:1599-1607` — a missing/invalid/foreign final manifest after rows exist records unavailable evidence against the first slot, even when that slot was committed and a later slot failed. Fix: validate the row prefix and select the first uncommitted slot; use null when attribution cannot be proven.

F22 — medium — `benchmark/bench/chain_core.py:1246-1254,1296-1304,1364-1385,1578-1584` — quarantine/archive repoints invocation records but not `progress.abort_evidence[].invocation`, leaving recovered evidence bound to a vanished path. Fix: repoint abort-evidence references in the same file-move transaction.

VERDICT: NOT CLEARED F16 F20 F21 F22

[exited with code 0]
