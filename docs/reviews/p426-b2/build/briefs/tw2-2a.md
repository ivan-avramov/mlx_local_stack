# Second delivery, part a (same session): run and review the s1–s3 candidate

The designer froze your set at 2026-10-27T17:09:59Z (all 21 files). The candidate for slices s1, s2 and s3 is now revealed: `.b2-candidate-s1-s3.diff` in this directory (baseline `f1e47df9` → candidate, `benchmark/` only). It was built from the specification before v3.2's §16, so some of §16's rules (e.g. the `REFUSED:` format, `slot_file`) are expected to be missing; later slices and a fix round will add them. A clean copy of the candidate with your frozen set installed exists; run tests there with `../bin/run_candidate_tests.sh <paths relative to its benchmark/>` (no arguments = its full suite). Do not edit any test and do not fix the candidate.

Do:
1. Run the frozen s1, s2 and s3 files (and the `add_` tests that need only s1–s3, if any) on the candidate. For EVERY failing test, classify it: (a) candidate defect — the candidate does not do what the specification (v3.2, incl. §16) requires; (b) §16 not yet built — the rule came with v3.2's §16 or later; (c) test defect — the test asserts something the specification does not support, or fails for a fixture reason; (d) unclear. Give the evidence (file:line in the candidate or the test, and the spec section).
2. Review the candidate diff against the specification for correctness and the threats it touches (§2 refusals, C221 for every tg1 mode, the probe edits, `p426_continue`, `invalidate`, the per-item ledger): findings with file and line, severity, and a concrete failure scenario.
3. Run the candidate's full suite once and report the summary line verbatim (the s0 file is expected to fail where it runs legacy argv without `--models`).
4. Verdict for this partial candidate: merge as the s1–s3 reference, fix then merge (list the fixes), or reject.

Report facts only; never report a test as passed that did not run.
