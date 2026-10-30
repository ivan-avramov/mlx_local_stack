P1 — Finding 1: Resolved. The registry is snapshotted immediately after locking and used for arm selection, derivation, hashing, and argv generation checks.

P2 — Finding 2: Resolved for safety. Certified argv is compared before launching the measurement. Refusal semantics remain incorrect; see P11.

P3 — Finding 3: Resolved. Both production references resolve to full commits, and realistic short/full combinations are tested.

P4 — Finding 4: Resolved. Derived files and job directories use sanitized, hashed components beneath `--out`.

P5 — Finding 5: Not fully resolved. Direct, quoted, and differently indented keys work, and flow mappings refuse clearly. YAML-merged keys remain unsupported; see P12.

P6 — Finding 6: Resolved. MTP-ON is derived from `expected_config()["drafter"]`; malformed draft blocks refuse.

P7 — Finding 7: Resolved. Restore requires the entry to be present in `registry_state`.

P8 — Finding 8: Resolved. FAILED records retain `arm` and `rates`, with a corresponding test.

P9 — Finding 9: Resolved. The formatter-visible spacing slip is repaired.

P10
- Location: `change.diff:490-499, 612-669, 1550-1552`; `qualify.py.txt:188-196, 228-238, 1059-1086`
- Severity: major
- Evidence: confirmed
- Problem: The amended existing tests were not updated for the repair’s mandatory `resolve` argument, three-argument `_production_matches`, unconditional production resolution, or required `manifest.json.picks[name].argv_on`.
- Failure scenario: `test_p415_qualify` calls `entry_problems()` without `resolve`, immediately raising `TypeError`; `test_p542_impl` calls `_production_matches()` with two arguments. Driver tests also lack certified argv. Therefore the claimed 705-pass result cannot correspond to the supplied material.
- Proposed change: Update all existing helpers and direct calls for the repaired API, create valid certified manifests, and rerun the stated suite.

P11
- Location: `qualify.py.txt:160-181`
- Severity: major
- Evidence: confirmed
- Problem: Named summaries cannot be parsed for registry names containing `/`, despite such names being supported elsewhere.
- Failure scenario: With entries `org/Model` and another model, `org/Model=/tmp/summary.json` is treated as a bare path and refused. Thus a multi-entry MTP-ON run cannot supply that entry’s evidence.
- Proposed change: Recognize `head in names` before applying the path heuristic, and add a multi-entry slash-name test.

P12
- Location: `qualify.py.txt:305-310, 1260-1265`; `tests-after.diff:740-749`
- Severity: minor
- Evidence: confirmed
- Problem: An argv certification mismatch becomes a per-entry `FAILED` result, not the required pre-run `SystemExit("refused: [...]")`. The test named “refuses” only checks that no job completed.
- Failure scenario: A manifest certifies a different `--draft-model`; an output report and monitor run are created, and the entry is marked FAILED rather than the invocation being refused.
- Proposed change: Derive and compare all MTP-ON argv before starting the run, then assert an actual refusal and absence of a report in the test.

P13
- Location: `qualify.py.txt:114-150`; `registry_states.py.txt:101-119, 176-196`
- Severity: major
- Evidence: confirmed
- Problem: Strict parsing supports YAML merge keys, but `mtp_off_registry()` scans only direct item pairs. Inherited MTP keys are missed, causing a generic refusal without the required key line.
- Failure scenario: A block using `<<: *draft` inherits `draft_kind` and `draft_model`. It is classified as MTP-ON, but `--predictor off` cannot derive its OFF registry even though the block is not flow-style.
- Proposed change: Define merged MTP keys explicitly. Either support source-node tracking safely, or amend the settled specification to refuse inherited/shared keys while naming each key and source line.
