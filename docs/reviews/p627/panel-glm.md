Findings (cold review of the P627 candidate in `benchmark/bench/local_gate.py`).

---

**F1 — blocker (confirmed by static trace; the frozen test `test_a_live_file_named_after_the_class_does_not_allow_the_entry` asserts the opposite of what the candidate produces).**   <!-- allow-shorthand: verbatim reviewer output -->

- Location: `entry_test_file` (candidate.diff lines 1–14 / `local_gate.py:302–313`) and its caller in `run` (`local_gate.py:389–393`).
- Severity: blocker — the material fails its purpose: it lets a push through that the spec says must fail, and the frozen test that asserts the correct outcome fails on the candidate.
- Evidence: confirmed by trace (I could not execute the suite: the sandbox blocks `git init` from writing `.git/hooks/`, so every test errors out before exercising the candidate; the static trace is unambiguous).   <!-- allow-shorthand: verbatim reviewer output -->
- Problem: `entry_test_file` returns the longest dotted prefix that is a `.py` file under **any** of `roots`, and the caller then only checks `(scratch/f).is_file()` and `(live/f).is_file()`. For a class-method entry `pkg.tests.test_k.TestKlass::test_m`, if the live tree contains a decoy file `pkg/tests/test_k/TestKlass.py` (a *module* named `TestKlass`, not the class), the helper resolves the test file to `pkg/tests/test_k/TestKlass.py` (longest prefix wins), finds it absent in scratch and present in live, and records the entry as `baseline_skips_absent` → verdict PASS. But `TestKlass` is a class in module `pkg.tests.test_k`; the test file is `pkg/tests/test_k.py`, and a decoy module file does not make the baseline entry "added later."
- Failure scenario: baseline lists `pkg.tests.test_k.TestKlass::test_m`; the gated commit predates `pkg/tests/test_k.py` (so the test is neither skipped nor run there); the live tree happens to also contain an unrelated `pkg/tests/test_k/TestKlass.py` (e.g. a later refactor split the class into its own module). The gate prints PASS and the push proceeds, even though the baseline entry's real test file was never added to the gated tree for the reason P627 is supposed to cover — it is masked by an unrelated same-named module. The frozen test `test_a_live_file_named_after_the_class_does_not_allow_the_entry` constructs exactly this and asserts FAIL; the candidate yields PASS, so the test fails on the candidate.
- Proposed change: derive the test file from the entry's module part **without** letting a longer same-named-module file in either tree hijack the resolution. Either (a) resolve strictly against `live` and require the resolved path to be the one the spec names (`a.b.c::name` → `a/b/c.py`; `a.b.c.Class::name` → `a/b/c.py`, stripping only trailing components that are not the leaf module), rejecting any prefix where a *directory*＋`<component>.py` shadow exists; or (b) resolve the candidate file once per tree and only accept the absent-allowed verdict when the resolved path is the same in both trees. At minimum, when `entry_test_file` finds a longer prefix in `live` than in `scratch`, do not treat that longer path as the entry's test file for the absent check.

---

**F2 — blocker (hypothesis; the frozen tests miss it).**

- Location: same `entry_test_file` "any of roots" resolution.
- Severity: blocker — a push the spec must fail is let through, and no frozen test covers it.
- Evidence: hypothesis by trace (no execution, sandbox).
- Problem: because the longest prefix is taken across the union of the two trees, a longer decoy file present in `live` can shadow the real, shorter module file that is present in `scratch`. Entry `a.b.c.Class::name` (real file `a/b/c.py`); scratch has `a/b/c.py` (so the test file IS in the gated tree, it just wasn't collected); live has `a/b/c/Class.py` but not `a/b/c.py`. `entry_test_file` returns `a/b/c/Class.py` (longest, found in live); the absent check sees scratch lacks `a/b/c/Class.py` and live has it → ABSENT-ALLOWED → PASS. The spec says this is "present in gated but not collected" → FAIL (C277 invariant; the frozen test `test_present_in_gated_and_not_collected_fails` asserts this for the simple case).
- Failure scenario: as above. The gate hides a never-collected test whose file exists in the gated tree, by pointing the resolution at a different, live-only file.
- Proposed change: same as F1 — resolve the test file per tree (or resolve once against a single canonical tree) so a longer decoy in one tree cannot mask a shorter real file in the other.

---

**F3 — major (hypothesis; the frozen tests miss it). "Added later" is the only intended absent reason; the candidate accepts any live-only file that matches the dotted prefix.**

- Location: `run` absent check (`local_gate.py:389–393`).
- Severity: major — it materially weakens the protection the request asks for ("an entry absent from the gated tree for a reason other than 'added later'" must fail).
- Evidence: hypothesis by trace.
- Problem: the spec's goal is narrow: a baseline entry whose test file was *added later* (present in live, absent in the gated commit) is recorded, not failed. The candidate's only test is "file absent in scratch and present in live," which is necessary but not sufficient for "added later." A file can be absent from the gated tree because it was *deleted* between the gated commit and live-but-readded, or *renamed*, and still match. The gate cannot distinguish these from "added later" because it never compares the gated commit's tree to the live tree's history.
- Failure scenario: a test file `pkg/tests/test_x.py` exists at the gated commit, is deleted in a later commit (so the baseline entry `pkg.tests.test_x::test_one` is stale), and is then re-added in live with different content. The candidate sees the file absent in scratch (the gated commit predates the re-add? — no, scratch is at the gated commit which HAD the file) — actually scratch would have it. Reverse: the gated commit is AFTER the deletion but BEFORE the re-add; live has the re-added file. Then scratch lacks it, live has it → ABSENT-ALLOWED → PASS, masking a deletion the baseline never accounted for.
- Proposed change: this is partly out of scope for a path-only check, but the spec's "added later" framing could be enforced by requiring the file to be absent from the gated commit's tree AND present in live AND the gated commit to be an ancestor of the live commit that introduced the file (i.e. `git log --diff-filter=A --follow`). If that is too much, narrow the spec's claim in the receipt (label it "absent in gated, present in live" rather than "added later") so consumers do not over-trust it. Scope request: add a check that the file was added after the gated sha in live's history.

---

**F4 — minor (confirmed). The "skip list != baseline" message still lists absent-allowed entries as `‑missing`.**

- Location: `run` (`local_gate.py:384–385`): `if extra: receipt["problems"].append(f"skip list != baseline: +{extra} -{missing}")`.
- Severity: minor — cosmetic; no gate outcome changes.
- Evidence: confirmed by read.
- Problem: `missing` is computed before the absent filter, so when an unbaselined skip coexists with an absent-allowed entry, the message reports `‑[absent-allowed entry]` even though that entry is now accepted.
- Failure scenario: baseline `[A]` with A absent-allowed, plus an extra skip `B`; the message reads `+[B] -[A]`, implying A is a problem when it is recorded as allowed.
- Proposed change: recompute the message's `missing` after removing `absent` (and `ran`), or label it `-[unexplained]`.

---

**F5 — minor / hazard (hypothesis). `Path.is_file()` follows symlinks.**

- Location: `entry_test_file` and the absent check.
- Severity: minor.
- Evidence: hypothesis.
- Problem: a symlink in `live/<rel>` pointing to a file outside the tree makes `(live/f).is_file()` true, so an entry can be marked absent-allowed on the strength of a link that is not a real tree file. The reverse (symlink in scratch) pushes the verdict the safe way (toward FAIL).
- Failure scenario: an operator's live tree has a convenience symlink `tests/test_x.py -> /elsewhere/test_x.py`; the gated commit lacks the file; the entry is allowed on a non-tree file.
- Proposed change: use `(Path(r)/rel).is_file() and not (Path(r)/rel).is_symlink()` for the live check, or resolve and require the target to be inside the tree root.

---

**On "anything else in `run` that changed":** no. The diff only adds `entry_test_file`, the `baseline_skips_absent` initialization (placed before the `baseline is None`/junit-missing guards, so the key is always present — matches `test_the_key_is_present_when_an_earlier_step_fails`), the absent loop, and the `unexplained` reassignment. `check`, `policy_digest`, the digest recipe, the verdict line, and C277's multiset/duplicate/junit-missing rules are unchanged. The `baseline_skips_absent` key does not feed the verdict or the digest. That part is clean.

---

**What the frozen tests miss (summary):**
1. The cross-tree shadowing of F2 (decoy in live shadowing a real file in scratch) — the only class-decoy test puts the decoy in live with scratch empty, which is the F1 shape; the F2 shape is uncovered.
2. No test for a longer-prefix decoy in *scratch* masking the live module file (the safe direction is also untested, but it is safe).
3. No test that the "added later" rationale is actually "added later" vs. deleted-then-readded/renamed (F3).
4. No symlink test (F5).
5. No test that the `skip list != baseline` message excludes absent-allowed entries from `‑missing` (F4).

The candidate is not ready: F1 alone fails a frozen test, and F2 is a second reachable blocker the frozen suite does not exercise.
