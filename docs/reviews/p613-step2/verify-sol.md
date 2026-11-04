Verification ledger:
- Sol P1, P2, P4, P7–P12, P14, P16, P17: resolved by source trace.
- Sol P3, P5, P13: only partially resolved; detailed below.
- Sol P6: unchanged, but not a defect under the settled fail-closed torn-file interpretation.
- Sol P15: unchanged, but not a defect under the settled “every eligible request” interpretation.
- GLM M1: resolved; rejected keys now retain the axis’s three-part shape.
- GLM M2: unchanged report-only wording; no candidate defect.
- GLM G1/G2: resolved/covered; rejected A7 sessions and single accepted Wave-1 blocks degrade cleanly.
- GLM S1–S3: retained scope notes, not defects.

P3 — own-arm worktree is still not required
- Location: `benchmark/bench/p426_verify.py:582-586,869-934`
- Severity: major
- Evidence: confirmed by source trace.
- Status: partially resolved.
- Problem: foreign-arm paths are rejected, but each leg is never required to name its own `stack-p426-s2-<arm>` component.
- Failure scenario: both OFF and ON argv use the same unrelated `stack-shared` path. Neither triggers `_foreign_arm_items`; their normalized base argv matches, and the expected MTP delta passes. Router and M1 pairs are accepted without arm-specific worktrees.
- Proposed change: before normalization, require at least one own-arm worktree component in each leg’s argv.

P5 — `all` can still read and publish external noise-floor inputs
- Location: `benchmark/bench/p426_verify.py:70-95,1333-1351`; `benchmark/bench/p426_signals.py:337-382,566-610,858-889`
- Severity: major
- Evidence: confirmed by source trace.
- Status: partially resolved.
- Problem: Wave-1 and B8-union inputs are confined, but A7 verification reads before its final confinement check. More materially, `_noise_floor` uses an unconfined reader and its inputs are added directly to `SIGNALS.json`.
- Failure scenario: a file beneath `p426/wave2.v8-4104c7fc/` is a symlink to valid external mutable data. `compute_all` reads it and includes its hash/outcomes in the sheet, violating committed-only inputs and environment independence.
- Proposed change: propagate an all-mode confinement requirement through A7/noise-floor loading and validate resolved directories and files before access.

P13 — path masking does not cover copied evidence fields
- Location: `benchmark/bench/p426_verify.py:52-57,1117-1123,1205-1206`
- Severity: major
- Evidence: confirmed by source trace.
- Status: partially resolved.
- Problem: rejection reasons are path-masked, but `speed_problems` and `log` are copied verbatim into B8.
- Failure scenario: a power-invalid but accepted receipt has `speed_problems=["worker failed under /Users/operator/work"]`; the absolute path enters `B8.json`. <!-- allow-pii-pattern -->
- Proposed change: recursively sanitize all free-text evidence fields before serialization, or omit these non-contracted fields; then fail closed on residual PII patterns.

P18 — key-rejection reasons omit contracted context
- Location: `benchmark/bench/p426_verify.py:1094-1108,1191-1194`
- Severity: minor
- Evidence: confirmed by source trace.
- Problem: `keys_rejected` reasons omit `rule 3` and pair identity; an A4 one-arm mismatch also omits the other arm’s explicit value.
- Failure scenario: an ON A4 request-seed mismatch reports only ON and the expected seed, contrary to “each rejection names the pair, rule and both values.”
- Proposed change: format key reasons through the pair-reason helper with explicit OFF, ON, and expected values.
