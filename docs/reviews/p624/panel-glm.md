Findings below. I read the candidate at `benchmark/bench/local_gate.py:113-118` and `:349-362`, the spec at `docs/specs/p624-gate-ran-skips.md`, and the frozen tests at `.p624-material/test_local_gate_ran_skips.py`. Evidence is confirmed unless labelled hypothesis.

---

**F1 — duplicate / cardinality-only skip differences now pass (major)**
- Location: `benchmark/bench/local_gate.py:356-358` (the `set(skipped) - set(want)` check) vs. the prior `skipped != want` list comparison.
- Severity: major.
- Evidence: confirmed. Today's check compares sorted *lists*, so a count-only difference (baseline `A\nA\n` vs. skipped `[A]`, or junit emitting two `<testcase>` rows for the same id vs. one baseline line) fails. The candidate collapses both sides to sets and lets the difference through silently.
- Problem: the spec's "every other skip difference fails exactly as today" is violated for the one class of difference today catches that sets do not — multiplicity. The implementer flagged this as P3 ambiguity; the frozen tests do not pin it down either way.
- Failure scenario: a baseline file accidentally gains a duplicated line (or pytest emits a duplicate testcase row, e.g. a parametrised id colliding with a non-parametrised one). Today the gate FAILs on the next push; after the candidate it PASSES, and `baseline_skips_ran`/`skipped_tests` silently drop the duplicate.
- Proposed change: keep the set-based W−S/P logic but re-introduce a list-equality guard for the multiplicity-only case, e.g. compute `S_list = skipped_from_junit(...) or []` and `W_list = want`, and if `S_list != W_list` and the set diffs are both empty, append `skip list != baseline: +[] -[] (cardinality)` (or reuse today's message with the empty set diffs). Decide deliberately and add a frozen test for `baseline=[A,A], skipped=[A]` and `skipped=[A,A], baseline=[A]`. If the operator confirms duplicates should be allowed, say so in the spec and add a test asserting it.

---

**F2 — missing-junit-after-rc-0 changes today's failure message (minor)**
- Location: `benchmark/bench/local_gate.py:349-361`.
- Severity: minor.
- Evidence: confirmed. If the junit file is absent after a successful pytest step, `skipped_from_junit` returns None → `skipped = []`, and `ran_and_passed_from_junit` returns None → `passed = set()`. With a non-empty baseline, today fails with `skip list != baseline: +[] -[W]`; the candidate fails with `baseline skip neither skipped nor passed: [W]` (no S−W problem since S−W is empty). Both FAIL, so protection holds, but the message differs from today's and obscures the real cause (missing junit).
- Failure scenario: a future pytest/junitxml regression writes no file on rc 0; the operator misreads the new-message FAIL as "tests didn't collect" rather than "junit missing".
- Proposed change: when `ran_and_passed_from_junit` returns None (file absent) and the pytest step reported rc 0, append a distinct problem like `pytest junit not written` and skip the skip-list checks, rather than folding the absence into the "neither skipped nor passed" message.

---

**F3 — `baseline_skips_ran` is written even when `baseline is None` (minor / scope request)**
- Location: `benchmark/bench/local_gate.py:354`.
- Severity: minor.
- Evidence: confirmed. `want` is `[]` when `baseline is None`, so `missing = []` and `baseline_skips_ran = []`. The spec says the key is "always present; `[]` when S == W" — it is silent on the no-baseline case. Writing `[]` there is a reasonable extension but not specified.
- Problem: a consumer reading a receipt with `baseline_skips_ran: []` cannot tell "S == W" from "no baseline file existed" without also checking `problems`. Minor information leak / ambiguity.
- Proposed change: either leave as-is and add a spec line clarifying the no-baseline value, or omit the key when `baseline is None`. Add a frozen test asserting the no-baseline receipt's `baseline_skips_ran`.

---

**F4 — both-problems-at-onus unverified (minor, test gap)**
- Location: `.p624-material/test_local_gate_ran_skips.py`.
- Severity: minor.
- Evidence: confirmed. No frozen test exercises S−W non-empty *and* a W−S entry that did not pass simultaneously. The implementer's P1 reading (both problems appended, order S−W then unexplained) is plausible but unasserted; a future refactor could drop one without a test failing.
- Failure scenario: a tree adds an unbaselined skip *and* drops a baseline test that doesn't run; the gate should FAIL with both problems but a regression silently drops one.
- Proposed change: add a test with `baseline=[A,B]`, `skipped=[C]`, `passed=[]` asserting both `skip list != baseline: +['C'] -['A','B']` and `baseline skip neither skipped nor passed: ['A','B']` appear, in that order.

---

**F5 — the `-[W−S]` part of today's message is not asserted to include passed entries (minor, test gap)**
- Location: `.p624-material/test_local_gate_ran_skips.py:215-225` (`test_an_unbaselined_skip_fails_even_if_a_baseline_entry_ran_and_passed`).
- Severity: minor.
- Evidence: confirmed. The test asserts `+['{A}']` is present but not the `-[...]` tail. The implementer's P2 reading ("today's message, unchanged" → `-[W−S]` lists all of W−S, including ran-and-passed entries) is what the candidate does (`-{missing}` where `missing = W−S`), but no test pins it. A future change to exclude passed entries from the `-[...]` tail would pass the frozen suite.
- Proposed change: add an assertion that the message is exactly `skip list != baseline: +['C'] -['A','B']` for a case where `B` ran and passed.

---

**F6 — testcase with multiple outcome children untested (minor, test gap)**
- Location: `.p624-material/test_local_gate_ran_skips.py`.
- Severity: minor.
- Evidence: hypothesis (the helper logic is confirmed, the test gap is confirmed). A `<testcase>` carrying both `<skipped>` and `<failure>` (or `<skipped>` and `<error>`) is counted by `skipped_from_junit` (skipped) and excluded from `ran_and_passed_from_junit` (not passed). That is the safe resolution, but no test covers it; pytest itself never emits such a combo, but a hand-written or future junit might.
- Failure scenario: a malformed junit with a skipped+failure testcase in W: today counts it as skipped (in S, so S∩W, no problem); the candidate also counts it as not-passed, which is harmless only because it's already in S. A future refactor that swaps the order of the two checks could regress.
- Proposed change: add a helper-level test with a multi-child testcase asserting it is in `skipped_from_junit` and not in `ran_and_passed_from_junit`.

---

**F7 — parametrised-id collision untested (minor, test gap)**
- Location: `.p624-material/test_local_gate_ran_skips.py`.
- Severity: minor.
- Evidence: hypothesis. The id format `classname::name` is shared with `skipped_from_junit`, so parametrised ids like `tests.test_x::test_y[param1]` are consistent across S and P. But no frozen test uses a bracketed name, so a regression that, e.g., strips brackets in one helper but not the other would pass.
- Proposed change: add one frozen test with a parametrised-style id in W, S, and P.

---

**What the frozen tests do well**: helper None/empty/sorted, id format parity with `skipped_from_junit`, the key PASS transition (W−S all passed), partial overlap, blank-line baseline, same-name-different-class, failed/errored baseline entries, S−W invariant, no-baseline invariant, failing-pytest-step invariant, full step list on PASS, scratch removal, and policy-digest independence from junit content. The candidate satisfies all of these.

**Nothing else of substance** in `check`, `policy_digest`, or the pre-push hook — the candidate touches only the helper and the skip-check block; the digest automatically supersedes existing receipts because `_gate_source()` changes, as the spec requires.
