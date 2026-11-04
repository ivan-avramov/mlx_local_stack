# P627 — the local gate records a baseline skip whose test file the gated tree does not have (spec v1.2, 2026-11-04; C283; v1.1 = gated tree first (test-writer F1); v1.2 = the panel's hardening)

## Goal (verbatim in every brief)

A push means "passed the advertised level" (P541). The gate compares the pytest skip list against the CURRENT policy's
`benchmark/gate/<repo>.skips.txt`; C277 already accepts a baseline-listed test that ran and passed. An older commit (the Wave 1 ON
archive tip `8055b219`) predates the test FILE of two baseline entries (`benchmark/bench/tests/test_b2_frozen_s0_support.py`, added
in `97db61da`), so those entries are neither skipped nor run there and the gate fails with pytest 7,663 passed / 0 failed. Solving
it means: a baseline entry whose test file is absent from the gated tree but present in the policy (live) tree is recorded, not a
failure; every other skip difference fails exactly as today (C277 included).

## Rule (in `benchmark/bench/local_gate.py` `run`, inside the existing skip check, after C277's)

- For each `w` in `W − S` that is not in P (C277's unexplained list): its test file is the path derived from the entry's module part
  (`a.b.c::name` or `a.b.c.Class::name` → the longest dotted prefix that is a `.py` file: `a/b/c.py`), relative to the repo top.
- **v1.1 gated tree first:** if ANY dotted prefix of the entry's module part is a `.py` file in the gated scratch tree, `w` is not
  absent-allowed (the module exists there and the test simply was not collected). Only otherwise:
- `w` is ABSENT-ALLOWED iff that file does NOT exist in the gated scratch tree AND DOES exist in the live tree (`live`, the policy tree
  the baseline comes from). Then `w` goes to `receipt["baseline_skips_absent"]` (sorted; always present, `[]` otherwise) and is not
  in the "neither skipped nor passed" problem.
- **v1.2 hardening** (each failure keeps the entry in the existing problem): the entry id appears nowhere in the junit; exactly ONE
  dotted prefix is a `.py` file in the live tree (two or more = ambiguous class / module → not allowed); that file is TRACKED at the live
  `HEAD` as a regular file (`git ls-tree HEAD -- <rel>` mode 100644 / 100755, not 120000) — the on-disk working tree is not consulted;
  and the commit that added it (`git log --diff-filter=A --format=%H -1 HEAD -- <rel>` in live) has the gated sha as an ancestor
  (`git merge-base --is-ancestor <gated sha> <adding commit>`): the file was added after the gated commit.
- A file absent in both trees, present in both, or an entry whose path cannot be derived → stays in the existing problem (unchanged).
- Nothing else changes (C277's multiset / duplicate / junit-missing rules, `check`, the digest recipe).

## Acceptance

Tests in a NEW `benchmark/bench/tests/test_local_gate_absent_skips.py` (hermetic, the existing fakes; the scratch and live trees are
`tmp_path` directories): absent in gated + present in live → PASS, listed; absent in both → FAIL with today's problem; present in
gated but not collected → FAIL; class-method entries resolve to the module file; an entry with no `::` → FAIL; C277 cases unchanged
(their tests stay green). Then the full gate on the change's commit, and the re-gate of `8055b219` PASSes with
`baseline_skips_absent` = the two `test_b2_frozen_s0_support` entries.
