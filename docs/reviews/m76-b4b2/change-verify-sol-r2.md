B1–B16 verification:
- B1 resolved: default call hashes adjacent `B8.json`; missing file refuses.
- B2 resolved for specified cases: `load_slots` validates rows/reruns/harness DNFs; conflicting transport DNFs and unequal sidecars refuse.
- B3 resolved: exemption is bound through slot attempt → invocation → manifest run ID.
- B4 resolved: v8 pins, generation identity, images, model and rows are bound per attempt.
- B5 not fully resolved: P1.
- B6 resolved: `B8.json` is written before A8 verification.
- B7 not fully resolved: P2.
- B8 resolved: only 16 exact tg1 paths are allowed.
- B9 resolved: every confirmatory session must be accepted.
- B10 resolved: every row seed is derived from the registered session seed.
- B11 not yet resolved: P3.
- B12 not yet resolved: P3.
- B13 resolved by disposition; no behavioral defect.
- B14 resolved: repository root is explicit throughout both consumer chains.
- B15 resolved: applicability is corpus/lever; wrong arms become a recorded reason.
- B16 resolved: signals require the file-byte SHA; CLI and panel compute it from bytes.

P1
- Location: `benchmark/bench/p426_verify.py`, `_a8_accounting`
- Severity: major
- Evidence: confirmed, traced in source.
- Problem: contradictory accounting records can still be accepted. Ledger agreement uses `any(...)`, so duplicate entries `[accounting_fault=True, False]` pass. `p426_accounting_faults` is collapsed into a set, silently ignoring non-objects, duplicates, and incorrect `sidecar` fields.
- Failure scenario: append a contradictory duplicate ledger entry to an otherwise valid accounting-fault slot. Slot state, sidecar and chain-list membership remain true, so B8-A8 accepts an impossible chain record.
- Proposed change: require exactly one matching ledger row with `accounting_fault is True`; strictly validate every chain-list entry, uniqueness and expected sidecar path; refuse malformed or duplicate entries.

P2
- Location: `benchmark/bench/p426_verify.py`, `a8_utc_seconds`
- Severity: minor
- Evidence: confirmed, traced in source.
- Problem: numeric timestamps must be non-negative, but timezone-qualified strings are returned without the same check.
- Failure scenario: sealed `t: "1969-12-31T23:59:59Z"` is accepted as −1 and silently falls outside every latency window.
- Proposed change: validate the parsed timestamp with `math.isfinite(ts) and ts >= 0`; catch timestamp conversion errors.

P3
- Location: `benchmark/bench/tests/test_m76_b4b2_fe_panel.py`; `benchmark/bench/tests/test_m76_b4b2_impl_panel.py`; `benchmark/bench/tests/test_m76_b4b2_impl_golden.py`
- Severity: major
- Evidence: confirmed, traced in tests.
- Problem: B11/B12 remain unverified. The frozen panel test explicitly says `_a8_packet`/`kv_export` are not covered; the implementation export test monkeypatches `_a8_packet`; the real test checks only one arm’s prompt and may skip. No real packet or export traverses B8-A8 → rows → HARVEST/evidence → final-tree objects → frozen packets.
- Failure scenario: a real export-shape or final-tree mismatch first appears during panel freezing after the decider.
- Proposed change: add a frozen end-to-end packet/export scenario without replacing `_a8_packet`, then exercise real new-identity records before judge dispatch.

P4
- Location: `benchmark/bench/tests/test_m76_b4b2_fe_support.py`; `benchmark/bench/tests/test_m76_b4b2_fe_signals.py`
- Severity: blocker
- Evidence: confirmed by source and the supplied 35-failure report.
- Problem: frozen acceptance v2 still contains the known B2/B3/B4/B10-incompatible fixtures, so candidate 2 does not yet pass its frozen acceptance suite.
- Failure scenario: acceptance remains red despite the production fixes.
- Proposed change: complete the test-writer amendments—real identity fields, `rowschema.sample_seed`, invocation-bound discarded attempts, resealed edited rows, and the stronger B10 reload expectation—then rerun the frozen suite.
