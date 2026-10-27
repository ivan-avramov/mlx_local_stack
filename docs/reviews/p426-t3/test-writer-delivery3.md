The amended set (138 tests) has run on both copies. On the candidate one test fails: a comment-only change to the seeding test in the ON commit is not refused (F1). Every other test passes there, and every baseline failure is behaviour the spec adds.

## 1. Amendments
Each amended or added test has a `# POST-REVEAL tw-3: <reason>` line above its `def`. Classes: [I] preserves an invariant, [N] new behaviour.

**Record field names (designer ruling)**
- `t3_frozen_support.py`: the record fixture now writes `uv_lock_sha256` and `bench_lock_sha256`. The full field list is pinned as `FROZEN_S2_FIELDS`. The other names already matched the ruling and the candidate's `p426_plan.py` (`build_pins` / `record_problems`).
- `test_t3_frozen_record.py::test_a_lock_sha_that_differs_from_the_record_is_refused` [N]: the parameters are now the ruled names.
- Added `test_t3_frozen_support_check.py::test_the_s2_record_carries_exactly_the_ruled_fields` [I]. It checks that the record's keys are exactly the ruled set and that every field matches the live world, including both venvs of both arms.

**The four support checks adopted as test defects**
- The three S-world sequencer calls now pass `--build s` when the sequencer offers it. A new helper, `s_build()`, reads the sequencer's own `--help`; B0 offers no `--build`, so nothing is passed there.
- `test_todays_gate_reads_each_sha_of_a_multi_commit_fork` no longer asserts how the gate reads the sha that holds both files; spec §3 behaviour is already asserted in `test_t3_frozen_gate`. It now checks:
  - which files each sha holds, read with git;
  - the workflow ref, the sync ref and the `AUDITS` list at that sha;
  - PASS at both shas;
  - the workflow ref and eight audits at the S-layout sha.

**Vacuous passes: a control twin on every refusal test**
- New helper `assert_twin_runs` (support file). It removes exactly the defect, points the run at a fresh `--out`, and requires the same world to run all 6 M1 legs VALID. So a refusal can only have come from the defect.
- Restore-diff cases (now 12): the twin re-makes the plain restore commit with `recommit_on`.
- Dirty tree (2): the twin reverts `README.md`.
- Head mismatch (2) and lock sha (2): the twin rewrites the record from the live state.
- Record tests outside the 17, to the same standard:
  - expected build (4): the twin moves both arms to S′'s pins;
  - copied `frozen.json`: it now also asserts that the refusal names S's `mlx_vlm` value;
  - missing record and wrong label: the twin writes the correct record;
  - venv differs (4): the twin restores the version.
- Out-marker refusals (3): the twin uses a fresh `--out`; the seeded out stays byte-unchanged.
- No new wording assertions beyond the copied-record one, which is a value the record itself carries.

**New case after the first candidate run**
- `seeding-comment-hunk` [N] in `test_an_on_arm_beyond_the_restore_is_refused_before_the_first_leg`. The existing `seeding-extra-hunk` case also adds an empty line. The candidate refuses that empty line as an added code line (diff lines 701–702), so that case never tested comment hunks. The new case edits one comment line and nothing else.

## 2. Counts and summary lines

| file | tests | baseline pass / fail | candidate pass / fail |
|---|---|---|---|
| support_check | 31 | 31 / 0 | 31 / 0 |
| label | 15 | 0 / 15 | 15 / 0 |
| names | 9 | 0 / 9 | 9 / 0 |
| arms | 28 | 0 / 28 | 27 / 1 |
| record | 17 | 0 / 17 | 17 / 0 |
| out | 7 | 0 / 7 | 7 / 0 |
| harvest | 20 | 12 / 8 | 20 / 0 |
| panel | 6 | 1 / 5 | 6 / 0 |
| gate | 5 | 1 / 4 | 5 / 0 |

- Baseline: `../bin/run_stack_tests.sh <9 files> -rA --tb=short` → `93 failed, 45 passed in 118.65s (0:01:58)`
- Candidate, after `../bin/sync_to_candidate.sh`: `../bin/run_candidate_tests.sh <9 files> -rA --tb=short` → `1 failed, 137 passed in 362.13s (0:06:02)`

An earlier run on each side, before the comment-hunk case was added, gave `92 failed, 45 passed in 79.27s (0:01:19)` on the baseline and `137 passed in 362.42s (0:06:02)` on the candidate.

## 3. Every failing test

**Baseline, all 93 are (b): behaviour the spec adds.** First failure lines:
- S′ sequencer tests (arms, record, out, names, the three full-run harvest tests, and the label grammar controls): `usage: … the following arguments are required: --stack-root, --registry-on`, from argparse.
- Leg-grammar tests, the leg default, and the three `--build s` byte-identity tests: `unrecognized arguments: --build s`.
- `test_the_sequencer_requires_build`: rc 0 without `--build`.
- Isolation: the first `--build s` run fails with the same usage error.
- Panel (5): `TypeError: … unexpected keyword argument 'build'`.
- Gate (4): `GateError: … upstream-parity.yml does not exist`, or `'952d4f6b' == 'aaaa1111'`.
- Harvest exemption (5): `model shorthand` violations on `wave1.<label>/` paths.

**Candidate, 1 failure: (a), a defect against spec v2.1.**
- `test_an_on_arm_beyond_the_restore_is_refused_before_the_first_leg[seeding-comment-hunk]` fails on its first assertion. The ON commit's seeding-test patch has one extra hunk that changes a comment line. The sequencer did not refuse; it launched and ran `m1-p426s2-off-smoke`, `m1-p426s2-on-smoke`, `m1-p426s2-off-b1` and onward.
- Spec §4 says the restore diff is asserted at patch level: "exactly the P426 plan's §11 changes in the seeding test … no other hunk".
- Code: `p426_plan.restore_diff_problems`, diff lines 695–703, drops comment lines from both the removed and added lists before checking.

## 4. New findings against the candidate
- **F1 is now shown by a test, Medium.** Scenario: a restore commit that also edits or deletes the seeding test's C177 comment lines (172–173), or adds any comment-only hunk to that file, is accepted, and Wave 1 starts on an ON arm that is not exactly the restore. F1's own fix applies; no new defect.
- **Not a candidate finding:** my earlier `seeding-extra-hunk` case passes on the candidate only because of the extra empty line, so it says nothing about comment hunks. The new case now covers them.
- **No other new findings.** On the candidate every refusal test's twin ran its 6 legs VALID. So the restore-diff (11 of 12 cases), dirty-tree, head, lock-sha, expected-build, record and out-marker refusals each fired for their own reason.
