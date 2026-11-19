Round-1 adopted findings:
- Sol P1 and alloc scope extension: resolved.
- Sol P17: partially resolved; generation checks the row hash, but v8 does not (P2).
- Sol P18, P19, P20, P21, P22: resolved.
- GLM F5: not resolved in this checkout; its three test defects remain (P1).

P1
- Location: `benchmark/bench/tests/s26_frozen/test_s26_arm_identity.py:177-186`, `test_s26_host_env.py:241-249`, `test_s26_sequencer.py:290-320`
- Severity: minor
- Evidence: confirmed; the files retain exactly the three defects identified in the test-writer report.
- Problem: the claimed amendments are absent, leaving the reported suite at 3 failures.
- Failure scenario: T1 parses undrained `capsys`; T2 makes the tool non-executable instead of unreadable; T3 writes an unsealed baseline.
- Proposed change: drain `capsys` after `check()`, use mode `0111`, create the baseline with `ph.write_exclusive`, then rerun frozen and full suites.

P2
- Location: `benchmark/bench/p426_freeze.py:81-91,769-774`
- Severity: major
- Evidence: confirmed; `declined_ok()` never checks `declined_evidence.row_sha256` or its equality with the entry’s `row_sha256`.
- Problem: Sol P17 is not enforced by the v8 record validator.
- Failure scenario: remove or alter both row hashes in a valid DECLINED entry, reseal the record, and `positives_problems()` still accepts it.
- Proposed change: require a 64-hex evidence row hash equal to the entry’s row hash; add a resealed-record rejection test.

P3
- Location: `benchmark/bench/arm_opencode.py:282-285,368-372`; `benchmark/chains/c147/run_tg2_chain.py:41-46,75-83`
- Severity: major
- Evidence: confirmed; tg2’s `probe_code_sha256` includes `tg2_gradle_home.py`, while the campaign-core and `ArmBinding.probe_data` recipes omit it.
- Problem: the change breaks the existing invariant that campaign core freezes the same probe closure as `probe_code_sha256`.
- Failure scenario: after establishing a campaign-core commit, change `tg2_gradle_home.py`; campaign-core comparison remains equal even though execution-relevant Gradle checking and identity code changed.
- Proposed change: add `benchmark/bench/tg2_gradle_home.py` to tg2 `CORE_SPECS["probe_data"]` and test that such drift invalidates campaign core.
