F1 — blocker — `benchmark/bench/campaign_core.py:77-83`  
`at_ref()` exits `TemporaryDirectory` before computing closures, so every real `--campaign-core` invocation reads a deleted tree and refuses. Fix: compute `closure_shas()` inside the `with` block.

F2 — high — `benchmark/bench/arm_opencode.py:100-105`; `benchmark/run_oc_probe.py:107-108`; `benchmark/bench/arm_specs.py:68-69`  
A3 exists only behind test injection. Production M64 sets receipts `absent`, supplies no `HttpReceiptSource`, and therefore neither refuses pending P372 nor records worker receipts. Fix: configure `required` and wire the HTTP source; unavailable endpoint must refuse before spawn.

F3 — high — `benchmark/bench/arm_runner.py:760-766`; `benchmark/bench/worker_receipts.py:462-465`  
With receipts enabled, `task_tokens.completion_tokens` still uses client-visible gate tokens. Disconnected task generations appear only in the nested diagnostic, violating A3’s receipt-owned task total. Fix: use `joined.task_tokens` for task totals; retain gate totals separately.

F4 — high — `benchmark/bench/chain_core.py:1194-1200,1233-1240`  
Archive/quarantine manifests precede moves, but progress paths are updated only afterward. A crash during `shutil.move` leaves `chain.json` pointing at missing files and resume cannot replay the transaction. Fix: persist a two-phase move transaction and recover it idempotently.

F5 — high — `benchmark/bench/chain_core.py:1569-1592,1675-1681`  
The fallback restart path does not use A7’s exact cleanup validator. A healthy router/worker plus `completed:false`, nonempty `unknown`, or extra keys can still archive and retry. Fix: call `cleanup_problems()` before every retry/restart path.

F6 — high — `benchmark/bench/chain_core.py:1469-1489,1718-1748`  
A12 records evidence only for rows already written. An incident/cancel on the current item before row commit leaves neither raw web evidence nor `unavailable` plus reason in the incident record. Fix: persist abort artifact paths/hashes and extract—or explicitly mark unavailable—for the failing slot.

F7 — high — `benchmark/bench/chain_core.py:300-304`; `benchmark/chains/c147/run_tg1_chain.py:56-63,72-80`; `benchmark/chains/m64/run_m64_chain.py:41-47,61-75`  
`--probe` overrides are executed but excluded from `ChainConfig`, lifecycle membership, and campaign closure specifications. A resumed campaign can therefore launch an unpinned probe. Fix: freeze the resolved probe entry/data in all three identities or prohibit overrides for recorded campaigns.

F8 — medium — `benchmark/bench/tests/p371_baseline/normalize.py:13-17`; `benchmark/bench/tests/p371_baseline/compare.py:37-50`  
A14 globally normalizes `interpreter`, hiding changes to the pre-P371 policy’s toolchain interpreter. New lifecycle members are also accepted by prefix without independent hash derivation. Fix: normalize only runtime noise and rederive every policy/lifecycle member explicitly.

F9 — medium — `benchmark/bench/chain_core.py:1821-1835,1853-1902`; `benchmark/bench/chain_core.py:1264-1269`  
Crash after persisting `accepted`/`exhausted` but before linking `.continue` is not salvageable; resume quarantines the row and silently reruns the slot. Fix: replay `.continue` or finalize the proven prefix during resume.

F10 — medium — `benchmark/bench/chain_core.py:1045-1071,1085-1096`  
A crash after an immutable A4 receipt is created but before its worker record is fsynced leaves an unregistered receipt; resume reuses the filename and aborts as stale. Fix: durably reserve/persist each worker receipt before creation or recover and validate orphaned receipts.

VERDICT: NOT CLEARED F1 F2 F3 F4 F5 F6 F7 F8 F9 F10
