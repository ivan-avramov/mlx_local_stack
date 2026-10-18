A1 — CRITICAL — `benchmark/bench/m64_schedule.py:24-29,68-90`; `benchmark/bench/arm_runner.py:502-518`; `benchmark/run_oc_probe.py:56-57`  
C175/C168 are not implemented. The runner remains hard-coded to the original Python/Go tg1, two-session-plus-reload schedule; it cannot run the ruled tg2 screen. Fix the spec/ruling record, four-language corpus handling, and screen schedule before measurement.

A2 — HIGH — `benchmark/bench/arm_opencode.py:418-449`; `benchmark/bench/token_turn_gate.py:20-30,445-469`; `benchmark/bench/tests/test_m64_arm_oc_adapter.py:477-484`  
`compaction.failed` deliberately aborts as unclassified. P370’s lead call is correct: this is a scaffold non-convergence, not transport corruption. Recognize the pinned error/export shape, add `compaction_failed` to precedence, emit a scored strict-fail row, and add an end-to-end test.

A3 — CRITICAL — `benchmark/bench/arm_runner.py:333-347`; `benchmark/bench/arm_opencode.py:433-443,480-484`  
Spec §7 worker receipts are absent. The runner passes `None` to reconciliation and substitutes date-freeze hook receipts, which cannot account for disconnected generations, admission sequence/fences, effective controls, tools hashes, or late tokens. Implement worker start/end fences and one-to-one request receipts; preserve post-hoc compaction tokens separately but include them in task totals.

A4 — HIGH — `benchmark/bench/arm_opencode.py:120-137`; `benchmark/bench/arm_runner.py:272-280`; `benchmark/bench/arm_watchdog.py:52-85`  
The watchdog learns opencode tool windows only after tool completion. A genuinely hung shell therefore has no open window and survives the 600-second limit. Completed-window overruns also do not make `tick()` truthy, so `exec_timeout` may remain unset. Add start-time instrumentation, flag `dog.exec_timeout`, perform a final tick, and test through the real pinned client.

A5 — HIGH — `benchmark/bench/arm_adapter.py:183-225`; `benchmark/bench/arm_runner.py:610-623`; `benchmark/chains/m64/run_m64_chain.py:170-186,706-718`  
`epoch_id()` is unused in production. Any 64-hex CLI value is accepted, and `snapshot_sha256` is not pinned across legs. Different snapshots can run under one epoch. Recompute the epoch from complete arm snapshots and freeze each arm’s exact snapshot SHA at entry, resume, every leg, and exit.

A6 — HIGH — `benchmark/chains/m64/run_m64_chain.py:630-647`  
Worker/router crashes become incidents only if the adapter first supplied another recognized cause. Otherwise the function returns before checking worker identity; `router_error` is never produced. Check router/worker state independently before returning “not transport.”

A7 — HIGH — `benchmark/chains/m64/run_m64_chain.py:644-658`; `benchmark/bench/chain_ops.py:838-930`  
Transport recovery accepts a missing cleanup receipt, and partial-row validation omits manifest/row `arm`, `epoch_id`, and `snapshot_sha256`. Require a complete clean receipt and apply `arm_row_problems`/arm validation before retrying.

A8 — HIGH — `benchmark/chains/m64/run_m64_chain.py:364-387,421-425,443-454`  
Mid-load resume is broken: it starts again at segment zero, counts unvalidated discovered rows as scored, and appends already-realized legs again. This ends in worker-manifest refusal or realized-order failure. Persist validated leg/segment state and resume with a fresh worker segment.

A9 — HIGH — `benchmark/chains/m64/run_m64_chain.py:443-454,510-515`  
There is no canonical reader/index for base rows, `.w<n>.jsonl`, `.dnf.jsonl`, and duplicated `chain.json["dnf"]`. A report reading the base drops recovered rows/DNFs; broad globbing can double-count DNFs. Add one ordered segment inventory and slot-deduplicating report loader.

A10 — HIGH — `benchmark/bench/chain_ops.py:243,577-598`; `benchmark/chains/m64/run_m64_chain.py:403-407,522-533`  
Every arm’s A4 result points at the mutable `a4_v2_latest.json`; later arms overwrite earlier receipts. Recovery also reuses the pre-reload receipt. Copy immutable per-arm/per-worker receipts and rerun A4 after every worker reload.

A11 — HIGH — `benchmark/bench/arm_runner.py:573-575,723-727`; `benchmark/bench/chain_ops.py:576-584`  
The “arm-neutral” runner hard-codes opencode carrier fields, `OPENCODE_CONFIG_CONTENT`, and the opencode A4 gate. Pi/dsh cannot satisfy this contract without impersonating opencode. Move these operations behind adapter/arm-ops methods.

A12 — HIGH — `benchmark/bench/arm_runner.py:323-431`; `benchmark/bench/arm_opencode.py:486-499`  
`web_evidence()` is never invoked, and its implementation records metadata rather than raw responses. Successful and failed attempts can therefore lack mandatory P201/search evidence. Persist and hash raw fetch/search/shell-network evidence on all outcomes.

A13 — HIGH — `benchmark/bench/tests/arm_contract_suite.py:121-178,314-327`; `benchmark/bench/tests/test_m64_arm_contract_suite_selftest.py:123-155`  
The 17 injected fake defects do each make their mapped check red. However, they mutate fabricated `ArmRun` summaries, while D2, infrastructure classification, and P201 checks explicitly skip; compaction requests are not checked for the complete control/tool contract. The real pinned-client suite exists but may skip when the binary is unavailable. This is not a complete §6 acceptance instrument.

A14 — NON-BLOCKING — `benchmark/bench/tests/test_m64_arm_oc_parity.py:20-55,106-125`; `benchmark/bench/arm_runner.py:42-465`  
No tg1 closure file, carrier, or plugin changed; source hashes confirm tg1 identity is unchanged, and valid old-schedule generation is deterministic with s2 reversed and the specified reload items. But “byte-identical” parity is overstated: tests exclude grade reports, run fields, generation identity, and wire headers. The duplicated ~750-line runner also lacks exceptional-path differential tests. Extract a shared lifecycle core or broaden parity tests.

Search-service refusal paths fail before model launch, and tg1 defaults in `chain_ops.py`/`session_pinning_gate.py` remain unchanged.

VERDICT: NOT CLEARED
