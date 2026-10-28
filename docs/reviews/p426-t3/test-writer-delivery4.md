success False 33.235118400000005
I recommend **merge**. The fix closes V1–V4 and V6 as dispositioned, and V5 holds by inspection. I found no new defect, and the fixed candidate passes my whole amended set and its own full suite with no failures.

## 1. Amendments
Every amended or added test has a `# POST-REVEAL tw-4: <reason>` line above its `def` (or its dict entry). Classes: [R] reproduces a failure the spec fixes, [N] new behaviour, [I] invariant, [c] fixing my own test.

**Fixture moved to P511 (`t3_frozen_support.py`)**
- `SEEDING_OFF` / `SEEDING_ON` are now C177's seeding hunk and its exact reverse, copied byte for byte from `78a730fe`.
- `restored_registry` is the fork's `overlay_on(OFF)` plus one `# PROVISIONAL P426` note as the first child of `generation_defaults:`. The note text is a parameter, since its free text is optional.
- `fork_overlay_on` loads the fork's rule from this copy's `src/mlx-vlm` through `bench.p426_overlay.load_registry_states`.
- Every fake fork now holds a byte copy of the real `dev/p369_phase2/registry_states.py` and `mlx_vlm/tests/fixtures/stack_registry_golden.yaml` (`FORK_OVERLAY_FILES`). That is how each arm worktree's fork can run the B4 rule.

**Support checks**
- The restored-registry check now asserts the P511 seeding bytes (no tuple form, no C177 comment).
- New `test_the_p511_restore_bytes_come_from_the_forks_rule_in_each_worktree` [I]. It checks that the fork's rule agrees with my S overlay helper, that it loads from both arm worktrees, and that the ON files are exactly the pinned bytes.

**Arms tests**
- The restore-diff test runs on P511 bytes. Its tw-3 comment-only case moved to the new V test, now editing another comment, because the C177 comment is gone after P511.
- New `test_the_restore_is_exactly_the_p511_bytes` [R], 9 cases, each with a twin that re-makes the exact restore:
  - V1: a comment-only hunk; the C177 comment kept; an extra code line containing `joint_v1`; the pre-P511 tuple form.
  - V2: a trailing comment on a restored line; a restored line moved; two notes; a note outside `generation_defaults`; a note that is not the first child.
- New `test_a_correct_restore_with_or_without_free_text_runs` [N], 2 cases: a correct restore with or without free text is not refused.

**New file `test_t3_frozen_fix.py`**
- V3 [R], 5 cases: other new value, other old value, reversed pair, golden unchanged, near-miss. Each must fail the p371 `rederive` hook. The twin is the pinned pair: the goldens' value → the sha256 of this tree's committed bench lock, which must be accepted.
- V4 [R]:
  - At the sequencer (`.venv` on the OFF arm, `.venv-bench` on the ON arm): a second `mlx` dist-info refuses before launch. The twin removes it.
  - At leg entry: the dist-info appears after the sequencer's check, so that leg is NOT_STARTED while the OFF smoke before it is VALID. The twin is a fresh world of the same shape that runs the leg VALID.
  - [c] My first version of the leg-entry twin reused the defect's `before_leg` hook, which fired again (`FileExistsError`, `test_t3_frozen_fix.py:78`). It now clears the hook first.
- I: the goldens hold exactly one lock value.

**V5 and V6, by inspection only.**
- V6: the fix adds `--build s` to the existing test (fix diff 243), as spec §4 [r2] directs. My `test_the_sequencer_requires_build` already covers `--build` being required.
- V5: the three S-era §2 bullets are marked superseded, and the M1 row names the label's head, production ref and out directory (fix diff 664–686).

## 2. Runs

| file | tests | baseline pass / fail | fixed candidate |
|---|---|---|---|
| support_check | 32 | 32 / 0 | 32 / 0 |
| label | 15 | 0 / 15 | 15 / 0 |
| names | 9 | 0 / 9 | 9 / 0 |
| arms | 38 | 0 / 38 | 38 / 0 |
| record | 17 | 0 / 17 | 17 / 0 |
| out | 7 | 0 / 7 | 7 / 0 |
| harvest | 20 | 12 / 8 | 20 / 0 |
| panel | 6 | 1 / 5 | 6 / 0 |
| gate | 5 | 1 / 4 | 5 / 0 |
| fix | 9 | 1 / 8 | 9 / 0 |

- **Baseline:** `../bin/run_stack_tests.sh <10 files> -rA --tb=short` → `111 failed, 47 passed in 120.88s (0:02:00)`. After the [c] correction I reran the fix file there: `8 failed, 1 passed in 3.87s`, the same outcome.
- **Fixed candidate,** after `../bin/sync_to_candidate.sh` (11 files): `../bin/run_candidate_tests.sh <10 files> -rA --tb=short` → `158 passed in 284.36s (0:04:44)`. The run before the [c] correction gave `1 failed, 157 passed in 392.92s (0:06:32)`; the failure was the reused hook.
- **Fixed candidate's full suite:** `7015 passed, 12 skipped, 1 xfailed, 4 warnings in 2395.48s (0:39:55)`. Nothing failed outside my set. The two failures the implementer reported (`test_m64_arm_closure…`, `test_m64_arm_oc_contract…`) passed in this copy.

## 3. Class of every failing test
- **Baseline, all 111 are (b): behaviour the spec adds.** First failure lines:
  - S′ sequencer tests: `usage: … required: --stack-root, --registry-on`.
  - Leg grammar, leg default and the `s` byte-identity tests: `unrecognized arguments: --build s`.
  - `requires_build`: rc 0 without `--build`.
  - Panel: `TypeError … 'build'`.
  - Gate: `GateError … upstream-parity.yml does not exist`, or `'952d4f6b' == 'aaaa1111'`.
  - Exemption: `model shorthand` on `wave1.<label>/` paths.
  - V3: `control twin: the pinned pair must be accepted` — B0's hook rejects every lock change.
  - V4: the usage error.
- **Fixed candidate:** nothing fails. The one earlier failure was (c), corrected as above.

## 4. Review of the fix (against spec v2.1, the dispositions and C241)
No new findings. Each threat the brief names:

- **An ON commit beyond the restore being accepted — closed.**
  - The registry check (`p426_plan._registry_problems`, fix diff 93–121) compares the whole file, byte for byte, against the fork's `overlay_on(OFF)` with the note inserted.
  - The seeding check (124–128) compares against OFF with `SEEDING_C177` replaced by `SEEDING_RESTORED`. Both constants match `78a730fe` exactly.
  - All 9 V1/V2 cases are refused, and each twin runs.
- **A correct restore being refused — not observed.**
  - The note may have free text or none: the regex is `# PROVISIONAL P426(?: [^\r]*)?` at the first child's indentation. Both forms run.
  - The sequencer checks tree cleanliness and the fork head before the restore diff (candidate diff 834–836). So the fork code it loads from the OFF worktree is the pinned one.
- **A wrong venv being accepted — closed.** Two dist-infos of a checked package read as `more than one dist-info: …`, which never equals a recorded version (fix diff 24–38), and `record_problems` refuses a record holding it (46–47). This is confirmed at the sequencer and at leg entry.
- **The p371 exception — closed per C241.**
  - The hook accepts only the literal pair `ecd97da3…` → `46612efe…` (fix diff 211–230).
  - My twin derives the new value from the candidate's committed bench lock and is accepted there, so the literal equals that lock's sha.
  - A later lock change fails p371 until a reviewed pair replaces this one, as C241 intends.
- **Beyond the findings:** `_entry_block` now splits on `"\n"`, which is harmless. The hunk-matching helpers are removed, and `test_t3_wave1.py` is rewritten to the P511 bytes and the real fork files. The spec-doc edits are V5. Nothing else is touched.
