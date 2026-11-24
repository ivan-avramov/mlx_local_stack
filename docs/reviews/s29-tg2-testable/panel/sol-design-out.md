P1
- Location: `spec.md:33-35`, `spec.md:51-53`; `tg2_grade.py:72-76`, `tg2_grade.py:760-763`
- Severity: major
- Evidence: confirmed
- Problem: T1 requires “none skipped,” but the grader intentionally leaves two JavaScript `test.skip` cases skipped and excludes them through `OPTIONAL_LEAVES`. Literal compliance conflicts with grader parity.
- Failure scenario: An implementer enables `test.skip`; local counts exceed the unchanged grader and expensive optional tests may run. Leaving them skipped violates T1.
- Proposed change: Define the suite as all non-optional graded leaves and explicitly preserve frozen `OPTIONAL_LEAVES`.

P2
- Location: `spec.md:39-42`, `spec.md:54-56`; `carrier-tg2.json:41-135`
- Severity: major
- Evidence: hypothesis; the pattern gap is confirmed, but matcher normalization was not supplied
- Problem: T4’s negative test is under-specified, and command-string globs cannot reliably distinguish local `EXERCISM_RUN_ALL_TESTS` from network lookup. Existing lower/upper patterns omit mixed case and obfuscated or compound shell commands.
- Failure scenario: `https://Exercism.org/...` matches neither case pattern; alternatively an allow rule for `*EXERCISM_RUN_ALL_TESTS*` may allow `cmake ... -DEXERCISM_RUN_ALL_TESTS=ON; curl https://exercism.org/...`.
- Proposed change: Require network isolation for shell subprocesses, leaving mediated web fetch as the only external path. Canonicalize web-fetch URLs and redirects. Add mixed-case, compound-command, interpreter-based, redirect, and variable-concatenation negatives.

P3
- Location: `spec.md:24-29`, acceptance section; `corpus_tg2.py:33`, `corpus_tg2.py:438-442`
- Severity: major
- Evidence: confirmed
- Problem: The new, unpoolable tg2 identity is settled but has no acceptance criterion. Prompt and carrier changes are absent from `identity()`, and the current scaffold name remains `opencode-v2-web-tg2`.
- Failure scenario: Updating only `HINTS` and carrier permissions meets T1–T4 while producing the old identity, allowing new rows to pool with A8.
- Proposed change: Require a new scaffold/identity value, bind the carrier and prompt/materializer revision into it, and test that old/new rows cannot pool.

P4
- Location: `spec.md:42-45`, `spec.md:57-59`; `p426_reconcile.py:287-295`, `p426_reconcile.py:327-339`
- Severity: major
- Evidence: confirmed
- Problem: K1 treats unchanged prompt/completion totals as evidence that the failed request processed zero tokens, but those totals are derived from completed requests; failed requests expose no token counts.
- Failure scenario: A post-signal request generates tokens and then fails. Aggregate completed-token totals remain unchanged, so a literal implementation accepts a shape that does not meet K1’s stated zero-token condition.
- Proposed change: Either remove the zero-token condition as irrelevant to a provably post-signal request, or require direct per-request telemetry proving zero processing and add that evidence to acceptance.

P5
- Location: `spec.md:55-56`; `structured_grade.py:90-96`; `tg2_grade.py:957-989`
- Severity: minor
- Evidence: confirmed
- Problem: Acceptance 3 equates unchanged protected files with “no tampered,” but new forbidden files and structural Cargo changes can also trigger tampering.
- Failure scenario: An in-source CMake test command leaves unprotected generated files; protected hashes are unchanged, yet `tamper_reasons()` rejects the tree.
- Proposed change: Run the stated local command and assert the production tamper check returns no reasons, not merely that protected hashes are unchanged.

P6
- Location: `spec.md:19-22`, `spec.md:42-48`, `spec.md:57-64`
- Classification: scope request
- Evidence: confirmed
- Problem: K1, K2, V1, and phase-2 positive-record changes are beyond the test-before-ship request; V1 is explicitly main-side and independent.
- Failure scenario: An otherwise complete T1–T4 change is delayed or coupled to unrelated reconciliation, acknowledgement, and vision-rubric changes.
- Proposed change: Split K2 and V1 out. Retain K1 only with explicit operator approval for opportunistic identity-bound repair.

P7
- Location: `spec.md:33-36`, `spec.md:51-53`
- Classification: scope request
- Evidence: confirmed
- Problem: Requiring every item’s stub/broken solution to report failures “per test” exceeds the goal and is not generally satisfiable when a stub fails compilation or suite setup.
- Failure scenario: The full local suite is correctly enabled, but a C++ or Java stub cannot compile, yielding no per-test events and failing acceptance.
- Proposed change: Require reference count parity plus a language-specific compilable known negative; test discovery/non-skipping independently of arbitrary stub behavior.
