P1 — Frozen acceptance API is unusable  
- Location: `benchmark/bench/p426_verify.py:2864`; `benchmark/bench/tests/test_m76_b4b2_fe_b8.py:28`
- Severity: blocker
- Evidence: confirmed
- Status: not resolved
- Problem: The specification and frozen tests call `verify_a8_kv(results_root)`, but the candidate requires `base_b8_sha256`. Every frozen A8 call fails with `TypeError` before testing behavior; the implementer ran only its own replacement tests.
- Failure scenario: Any frozen B8, signals, or real-record fixture calls the one-argument API.
- Proposed change: Make the SHA optional and derive it fail-closed from `<results_root>/B8.json`; retain explicit injection only as a test seam. Run the frozen `test_m76_b4b2_fe_*.py` suite.

P2 — The candidate reconstructs slot accounting incompletely  
- Location: `benchmark/bench/p426_verify.py:2427-2616`, especially `load_dnf` use at 2647 and `_a8_slots`
- Severity: major
- Evidence: confirmed
- Status: not resolved
- Problem: The custom loader bypasses canonical `chain_rows.load_slots`. It therefore accepts several contradictory inventories:
  - A row plus a transport DNF: `load_dnf` silently drops the DNF when the row exists.
  - An accepted attempt with missing `invocation`: the source-file comparison runs only when it is a string.
  - Unregistered row files: all session JSONL files are consumed without checking `progress.invocations`.
  - A harness-DNF chain record is not self-seal checked or field-equal to its sidecar; only its SHA and kind are compared.
  Duplicate accepted attempts are correctly refused.
- Failure scenario: Remove `invocation` from an accepted slot attempt, move its row to an unregistered JSONL, or pair a slot-A chain record with a sealed slot-B harness sidecar while copying its SHA. The session can remain accepted.
- Proposed change: Use `chain_rows.load_slots` as the single inventory authority, then perform exact sidecar-to-chain equality and seal checks. Avoid the parallel `_a8_session_rows`/`_a8_slots` reconstruction.

P3 — A foreign final tree can evade the orphan check  
- Location: `benchmark/bench/p426_verify.py:2154-2199`
- Severity: major
- Evidence: confirmed
- Status: partially resolved
- Problem: Missing, duplicate, and SHA-mismatched final trees are rejected. However, `_discarded_run_ids` returns a global set of seen run IDs plus a set of discarded item IDs. `final_tree_reasons` accepts their Cartesian product rather than proving that this run ID was the discarded attempt for this item.
- Failure scenario: Item A has a rerun; run ID B belongs to another item/language but appears in `seen_run_ids`. An extra manifest for item A under run B is treated as an allowed discarded tree.
- Proposed change: Bind discarded run IDs per slot/item from the invocation and attempt records; exempt only `(item, run_id)` pairs actually belonging to that discarded attempt.

P4 — Legs are not bound to the full v8 identity  
- Location: `benchmark/bench/p426_verify.py:2662-2681`, `2747-2762`
- Severity: major
- Evidence: confirmed
- Status: partially resolved
- Problem: Schedule shape, arm commits, `chain.frozen_record.sha256`, cross-arm seeds, and pair plan equality are checked. The candidate does not compare:
  - `v8.tg2_draw_sha256` with the pinned draw;
  - v8 universe/image pins with their committed pins;
  - manifest model, generation identity, probe-code SHA, or scaffold-policy SHA with v8.
  `check_tg2_p426` derives the expected schedule using the schedule’s own model, so it does not establish the requested model.
- Failure scenario: Both arms’ schedules and manifests name another model or identity while retaining the v8 commits and equal provenance. The pair can be accepted.
- Proposed change: Add one v8-binding validator covering draw, universe, grader image, target model, generation identity, probe code, scaffold policy, and manifest/runtime values.

P5 — Accounting-fault consistency and tax aggregation are incomplete  
- Location: `benchmark/bench/p426_verify.py:2543-2616`; `benchmark/bench/p426_signals.py:1893-1901`, `2061-2077`
- Severity: major
- Evidence: confirmed
- Status: not resolved
- Problem: Accounting status is inferred with an OR over accepted-attempt and ledger markers. The row marker is ignored, marker disagreement is not rejected, and an unreferenced accounting sidecar is ignored. Such a row can enter decode/wall aggregates. The A8 section also has no runaway-tax aggregate at all, despite §9.4 requiring accounting-fault rows to leave token, latency, and tax aggregates.
- Failure scenario: Remove the chain/ledger markers while retaining `row.accounting_fault` and its sidecar. B8 treats it as ordinary, and signals includes its extreme token/wall values.
- Proposed change: Require exact agreement among canonical slot state, ledger, row annotation where present, and sidecar; reject orphan sidecars. Exclude these rows from decode, walls, and a separately reported runaway-tax aggregate.

P6 — The real packet-binding acceptance remains unverified  
- Location: `.panel/implementer-report.md:80-84`; frozen panel tests explicitly omit `_a8_packet`
- Severity: major
- Evidence: confirmed
- Status: not resolved
- Problem: The real prompt/export test skipped because the evidence objects were absent, and the available real pilot is the old identity. Frozen tests do not exercise A8 prompt, start-tree, final-tree, or export-level leak binding. Synthetic implementer tests do not replace §7.3’s real-path acceptance.
- Failure scenario: Evidence-ref path conventions differ from fixtures; the first real A8 export fails only after the decider is harvested.
- Proposed change: Run the packet/export acceptance against the harvested new-identity pilot and its evidence objects before acceptance; regrade only.

P7 — Malformed latency records are accepted as present  
- Location: `benchmark/bench/p426_verify.py:2841-2861`
- Severity: minor
- Evidence: confirmed
- Status: not resolved
- Problem: Validation checks only that fields exist, not that timestamps and measurements are valid numeric values. Signals silently drops malformed values.
- Failure scenario: A sealed row with `fresh_ms: "bad"` and an invalid timestamp yields `status: present` with empty summaries.
- Proposed change: Validate timestamp syntax, finite non-negative latency values, and numeric CPU before accepting the record.

P8 — The tg1 golden was broadly weakened  
- Location: `benchmark/bench/tests/test_m76_b4b1_impl_golden_tg1.py:228-235`
- Severity: minor
- Evidence: confirmed
- Status: not resolved
- Problem: The new exception ignores every `.b8.inputs.*.jsonl` SHA difference, not only the fixture rows changed by the final-tree addition.
- Failure scenario: An unrelated tg1 row mutation changes a B8 input SHA and the golden no longer catches it.
- Proposed change: Pin the exact expected changed paths or regenerate the golden; do not wildcard all JSONL input hashes.

P9 — Rejected confirmatory sessions still produce top-level `status: complete`  
- Location: `benchmark/bench/p426_verify.py:2907`
- Severity: minor
- Evidence: confirmed
- Status: not resolved
- Problem: “Complete” means merely “not incomplete”; a rejected s1 or s2 still yields a complete document. Signals defensively rechecks `accepted`, so the current verdict path does not consume it, but the B8-A8 contract is misleading.
- Failure scenario: A final-tree or plan mismatch rejects s1 while both sessions exist; `B8-A8.json.status` remains `complete`.
- Proposed change: Set complete only when every confirmatory session is accepted.

Resolved without a finding:
- The A8 verdict and sensitivity verdicts flow through `m76_rule.axis_verdict`; direct `loss_bound` calls are descriptive only.
- Valid harness DNFs score zero; two accepted attempts refuse; arm seeds and reload-control seeds are checked.
- `B8.json`, no-A8 signals, and the frozen stage-3 panel remain byte-identical by the traced branches and goldens.
- C362 arm/box leak checks are applied before packet writes.
- Structurally, `_a8_packet` binds both prompts, the prepared start tree, the B8-selected final manifest, evidence objects, and protected paths; P6 is the missing real-path verification.
