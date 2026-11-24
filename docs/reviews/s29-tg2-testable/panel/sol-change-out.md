P1 — Resolved. Optional JavaScript leaves remain skipped both locally and by the grader; all other graded leaves are enabled. The rewrite preserves grader semantics.

P2 — Not resolved. See open finding P8.

P3 — Resolved. The carrier hash and workspace identity—including preparation version, helper text, and commands—change the policy and generation identities. Compatibility and pairing paths reject old/new pooling.

P4 — Resolved. K1 no longer requires unavailable token evidence. Failed-request tokens remain descriptive only. See P9 for a new boundary defect.

P5 — Resolved. Production `tamper_reasons` is exercised after canonical and variant commands; rewritten tests become the protected baseline.

P6 — Resolved. K2 and V1 are absent from this candidate; K1 is intentionally retained in reviewed v1.1.

P7 — Resolved. Acceptance uses reference parity and one compilable known negative per language rather than arbitrary stubs.

P8
- Location: `candidate-1.configgen.diff`, `TG2_LOOKUP_FORMS` / `TG2_SHELL_ONLY`; generated `new-carrier-permissions.json`
- Severity: major
- Evidence: confirmed; the generated matcher allows `npx degit exercism/rust` and `npm install github:exercism/rust`. Implementer finding F4 also acknowledges the former.
- Problem: A cooperative agent can fetch an Exercism repository through common package-manager repository shorthands. T4 therefore does not keep solution lookup denied.
- Concrete failure scenario: The agent runs `npx degit exercism/rust /tmp/r`, then reads the exercise’s example solution before submitting.
- Proposed change: Deny common repository shorthand resolvers, including `degit` and npm/pnpm/yarn GitHub forms targeting the Exercism organization, with mixed-case variants and compound-command tests.

P9
- Location: `candidate-1.diff`, `p426_reconcile.py::_trailing_failed_at_kill`, lines 135–163 of the diff
- Severity: major
- Evidence: confirmed by source trace
- Problem: K1 requires the trailing failure to belong to its preceding request, but the implementation checks only adjacency and counts. It never compares the `uid` fields of the final `Request started` and `Request failed` records or otherwise binds them to the item’s session.
- Concrete failure scenario: A window ends with `started uid=41` followed by an orphan `failed uid=99`; worker totals still move by started +1, failed +1, completed +0. All K1 predicates can hold and the genuine correlation fault becomes `accounting` instead of `integrity`.
- Proposed change: Require matching request identifiers between the trailing start and failure and affirmative item/session ownership. If telemetry cannot establish that binding, retain the integrity classification.

P10
- Location: `candidate-1.configgen.diff`, broad shell rule generated from `"problem-specifications"`; `frozen-tests/test_s29c_t3_t4_permissions.py:38-45`
- Severity: minor
- Evidence: confirmed; the generated matcher denies `ls problem-specifications-notes` and `cat ~/problem-specifications/README.md`.
- Problem: The carrier still blocks harmless local paths containing `problem-specifications`, contrary to T4’s explicit local-word exception and the frozen tests.
- Concrete failure scenario: An agent tries to inspect a local notes file whose path contains that phrase and the shell call is denied despite making no external lookup.
- Proposed change: Replace the broad shell token rule with URL-, repository-, and fetch-command-specific patterns. Keep the broad rule for `webfetch`, where the resource is necessarily external.
