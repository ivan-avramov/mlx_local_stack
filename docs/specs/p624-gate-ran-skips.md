# P624 — the local gate accepts a baseline skip that ran and passed (spec v1, 2026-11-04; C277)

## Goal (verbatim in every brief)

A push means "passed the advertised level" (P541): every code push carries a full-level PASS receipt from `bench.local_gate run` for
its exact sha. The gate compares the pytest skip list against the CURRENT policy's `benchmark/gate/<repo>.skips.txt` and fails on any
difference. An older commit (here the Wave 1 ON head `f2b61127` + its test fix, `8055b219`) legitimately RUNS tests the current
baseline lists as skipped (they skip only on later trees), and they pass — yet no PASS receipt can exist for it. Solving it means: a
baseline-listed test that ran and passed in the gated tree no longer fails the gate, and is recorded in the receipt; every other skip
difference fails exactly as today.

## Rule (in `benchmark/bench/local_gate.py` `run`, after the pytest step succeeded)

- S = the skipped testcases from `.gate-junit.xml` (`classname::name`, as `skipped_from_junit`); W = the baseline entries (non-blank
  lines). P = the testcases in the junit that ran and passed: a `<testcase>` with none of `<skipped>`, `<failure>`, `<error>` children.
- `S − W` non-empty → problem `skip list != baseline: +[S − W] -[W − S]` (today's message, unchanged).
- Each `w ∈ W − S`: `w ∈ P` → allowed; else → problem `baseline skip neither skipped nor passed: [<sorted such w>]` (not collected,
  renamed, failed or errored).
- Receipt gains `baseline_skips_ran`: sorted `W − S ∩ P` (always present; `[]` when S == W). `skipped_tests` unchanged.
- No baseline file → today's problem, unchanged. Everything else in `run`, `check`, `policy_digest` and the pre-push hook unchanged
  (the gate source is part of the digest, so existing receipts are superseded by policy as with any gate change).

## Interfaces

- New helper `ran_and_passed_from_junit(path) -> list[str] | None` (sorted `classname::name`; None when the file is absent), beside
  `skipped_from_junit`.

## Acceptance

- Tests in `benchmark/bench/tests/test_local_gate.py` (or a new `test_local_gate_ran_skips.py`), hermetic with the existing fakes
  (`Runner` writes the junit; extend it to write passed / failed / errored testcases): S == W → PASS, `baseline_skips_ran == []`;
  W − S all passed → PASS, listed; one of W − S absent from the junit → FAIL with the new problem; one with `<failure>` or `<error>`
  (rc 0 fake) → FAIL; S − W non-empty → FAIL as today (existing test stays green); helper on absent / mixed junit.
- The full suite passes at the change's commit (the gate on its own commit is the acceptance run), then the gate on `8055b219` PASSes
  with `baseline_skips_ran` = the two `test_b2_frozen_s0_support` entries.
