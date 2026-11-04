I amended the one test, ran the three files, and reviewed the candidate. Verdict: fix then merge.

**Test amendment.** `test_a_live_file_named_after_the_class_does_not_allow_the_entry` is now `test_a_live_only_file_named_after_the_class_is_the_longest_prefix_and_allows_the_entry` (new-behaviour). A live-only `pkg/tests/test_k/TestKlass.py` makes the class-method entry allowed, and the test asserts PASS plus the entry in `baseline_skips_absent`. I amended nothing else.

**Run.** The command was `../.venv-bench/bin/python -m pytest -q -p no:cacheprovider bench/tests/test_local_gate_absent_skips.py bench/tests/test_local_gate_ran_skips.py bench/tests/test_local_gate.py`, from `benchmark/`. Summary verbatim: `1 failed, 106 passed in 35.61s`.

The one failure is `test_the_key_is_present_when_an_earlier_step_fails` (`KeyError: 'baseline_skips_absent'`). The candidate diff only sets the key inside the skip-check branch, so it is missing when an earlier step fails. That is the fix round you said is under way (both keys set at receipt creation). The diff I reviewed does not contain it yet.

**Review against the spec.** The candidate matches the rule:
- It runs after C277's list and only looks at the unexplained entries.
- An entry is allowed only if the derived file is missing in scratch and present in live.
- Entries with no `::`, or with a dotted part that is empty, `.`, `..` or has a slash, are not derivable and stay in the problem.
- The list is sorted.
- The extra-skip, duplicate-entry, junit-missing and no-baseline rules are untouched.

**Push-safety: what it lets through that today refuses.**
- **Intended:** a baseline entry that is neither skipped nor passed, whose test file is absent in the gated tree and present in live. That includes a gated commit that deleted the file. The receipt records it, which I think is acceptable.
- **Unintended hole (F1, probed):** `entry_test_file` picks the longest prefix that is a file in either root. Take a baseline entry `pkg.tests.test_k.TestKlass::test_m` where the gated tree has `pkg/tests/test_k.py`, but the entry was not collected, so it is a real missing test. If live also has a file `pkg/tests/test_k/TestKlass.py`, the longest prefix resolves to that live-only file. I ran this scenario in a throwaway script (not added to the repo), and the gate returned PASS with the entry listed as absent. Today this fails.
  - It needs an odd live layout, so the risk is small, but a push gate should not depend on that.
  - **Recommended fix:** resolve against the gated tree first. If any dotted prefix of the entry is a file in scratch, the entry is not absent-allowed. Only when no prefix exists in scratch should the live lookup apply.
  - **Cost:** this contradicts my amended test's literal premise only when the gated tree also holds a shorter prefix file. The amended test has no gated file, so it still passes.
  - **Strongest counterpoint:** the spec says "longest prefix", and the designer ruled that way. A scratch-first check is a small spec change, so the designer should decide.

**Minor.**
- `is_file()` follows symlinks, so a live symlink counts as present.
- `baseline_skips_absent` is filled even when the verdict is FAIL. That matches my earlier assumption and the mixed-entry test.

**Verdict: fix then merge.** Both fixes are for the implementer. Set both receipt keys at creation (this should turn the last failing test green). Close F1 with scratch-first resolution, or have the designer accept the hole explicitly. If F1 is accepted, I'd still add a pinning test for it. I did not fix the candidate.
