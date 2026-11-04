Prior findings: Sol P2, P3, P4 and GLM F2/F5 are resolved. Sol P1/GLM F1 is not resolved as originally stated—the revised spec deliberately accepts the single-prefix ambiguity. Sol P5/GLM F3 is only partially resolved; GLM F4 is intentionally unchanged.

P1
- Location: `benchmark/bench/local_gate.py:325-330`
- Severity: blocker
- Evidence: confirmed
- Problem: The ancestry hardening rejects the motivating `8055b219` archive commit.
- Concrete failure scenario: the live file’s adding commit is `97db61da`, but `git merge-base --is-ancestor 8055b219 97db61da` returns 1. They are divergent descendants of `10014b4a`. `_absent_allowed` therefore returns false, so the required re-gate still fails.
- Proposed change: support related divergent histories. Require one common merge base between the gated SHA and live HEAD, then require the adding commit to be a strict descendant of that merge base. Add a test using the actual divergent graph shape.

P2
- Location: `benchmark/bench/local_gate.py:78-85, 295-299, 429-438`
- Severity: major
- Evidence: confirmed
- Problem: The new decision depends on live HEAD and its history, but neither is bound into the policy digest or revalidated when consuming a receipt.
- Concrete failure scenario: mint a PASS while live HEAD satisfies the addition rule, then move live HEAD to a state where it does not. If gate source and baseline remain unchanged, `check` accepts the stale receipt under the same digest.
- Proposed change: bind the relevant live-tree provenance to the digest/receipt, or revalidate every `baseline_skips_absent` entry against current live HEAD during `check`.
