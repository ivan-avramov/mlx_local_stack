I recommend **fix, then merge**. Nothing in the candidate breaks evidence isolation, the expected-build binding or the local gate. But my set hasn't actually exercised its S′ behaviour yet: one record-field name difference refuses every S′ run before any leg starts. Code review found one real gap in the patch-level restore check (F1).

## 1. My frozen set on the candidate
`../bin/run_candidate_tests.sh <my 9 files> -rA --tb=short` → `47 failed, 89 passed in 104.20s (0:01:44)`.

The same 136 tests ran on both sides, with identical per-file counts: arms 27, gate 5, harvest 20, label 15, names 9, out 7, panel 6, record 17, support_check 30. My first report had `_record` as 16 and `_panel` as 7; the real counts are 17 and 6.

**4 failures are test defects (c).** They are support checks I wrote to validate fixtures on B0, so they pin behaviour the spec deliberately changes:
- `test_the_s_world_runs_every_leg_valid_through_todays_sequencer`, `test_a_receipt_refused_before_the_first_leg_is_visible_to_the_helpers` and `test_a_driver_hook_mutates_the_world_during_the_leg` call the sequencer without `--build`. The candidate correctly answers `--build <label> is required` with rc 2 (§4, `p426_wave1.py` diff 875–877).
- `test_todays_gate_reads_each_sha_of_a_multi_commit_fork` expects `952d4f6b` at a sha that has both files; the candidate returns `aaaa1111`, which is what §3 requires.

**The other 43 are a name the spec left open (d).** Every one fails on the same refusal: `STOP: build s2 refused, nothing launched: uv_lock_sha256 missing; bench_lock_sha256 missing`.
- My record (`t3_frozen_support.py`, `frozen_s2_doc`) uses `uv_lock_sha` and `bench_lock_sha`.
- The candidate (`p426_plan.record_problems`, diff 588–590; `build_pins`, 555) reads `uv_lock_sha256` and `bench_lock_sha256`.
- All other field names match.

The 43 are:
- label: 7 grammar cases — the bad label was refused correctly; the `s2` control is what fails.
- names: all 9.
- arms: 12 — the four "own worktree" tests, `--registry-on`, both `--stack-root-*`, untracked, 2 head-moved, drift, P504 overlay.
- record: 8 — leg reads only `frozen.s2.json`, 4 venv-differs, venv before leg, venv during leg, record harvested.
- out: 4 — marker written, empty out, resume, isolation.
- harvest: 3 — dossiers, run files, M1 overlay copy.

**17 of the passing tests passed only because of that same refusal.** The sequencer's record check (`record_problems`) returns first, so these never reached the per-arm comparison (`arm_problems`) or `restore_diff_problems`:
- the 11 restore-diff cases;
- the 2 dirty-tree cases;
- the 2 head-mismatch cases;
- the 2 lock-sha cases.

So most of the S′ path has not been run by my set. The record-level refusals passed on their own merits: the expected-build cases, failure path (1), the missing record, the wrong label and the three `--out` cases. So did every `s` byte-identity test, the gate, panel and naming tests, and `--build` being required.

## 2. Candidate full suite (one run)
`48 failed, 6923 passed, 12 skipped, 1 xfailed, 5 warnings in 2466.65s (0:41:06)`

- 47 of the failures are my set, as above.
- The 48th is `test_m64_arm_closure.py::test_the_tg1_carrier_and_plugins_the_arm_wraps_are_unedited_by_this_build`: `git merge-base HEAD main` printed nothing ("no merge base with main", line 51). The test reads git history, and that copy has no shared history with a `main` branch. The diff doesn't touch it. The implementer reports it passing in their copy (6835 passed, 0 failed).

## 3. Review against spec v2.1

**F1 — Medium, a candidate defect (a): the seeding-test half of the restore check is not patch-exact (§4 "no other hunk").**
- `restore_diff_problems` (diff 695–703) ignores every comment line in the seeding test, removed or added. It accepts up to two added code lines anywhere in the file, as long as each contains `joint_v1` or `registry`.
- Scenario: the ON commit also deletes or rewrites the C177 comment lines 172–173, or adds a comment hunk elsewhere. It is accepted. My `seeding-extra-hunk` case (a comment line appended) would pass the check; it only "passed" because of the field-name refusal. The candidate's own cases (`test_t3_wave1.py`, diff 1557–1558) cover only added code lines.
- Fix: compare the seeding test's `-U0` patch with exactly one removed line (line 174) and the pinned replacement, with no comment changes.

**F2 — Low: the `main_models.yaml` half is looser than "exactly".**
- `_key_value` (diff 626–629) strips trailing comments, so `draft_kind: mtp  # anything` passes.
- Removed and added lines are compared as sorted lists, not position by position.
- Any number of `PROVISIONAL P426` comment lines, anywhere in the entry, are accepted (`notes` is only checked to be non-zero, 682–694).
- Scenario: a restore commit adds notes outside `generation_defaults`, or moves the restored keys. Parsed YAML is unchanged, but the patch is not the §11 patch.

**F3 — Medium: the `new_side.py` exception (diff 1005–1006) effectively disables a check.**
- It accepts any change to `/runtime/policy/toolchain/lock_sha256` if the new value equals the live bench lock's sha. The new side computes that same value from that same file (`toolchain.lock_sha256()`, `toolchain.py:24`), so the comparison can't fail.
- The goldens keep `ecd97da3…` (`p371_baseline/golden/*.json`), and the helper's own docstring still says policy value changes are never accepted.
- Scenario: a later, unreviewed lock change passes the p371 differential silently.
- Fix: accept only the pair `ecd97da3…` → the committed S′ lock sha, or regenerate the goldens by their own procedure. The operator should rule on this.

**F4 — Medium, not verified: the bench lock may be internally inconsistent.**
- The implementer writes (report line 38) that `uv pip install` drifted `datasets`, `huggingface-hub`, `click` and `hf-xet`, and they pinned these back by hand before freezing. `uv pip sync` installs exactly what is listed without checking that requirements agree.
- Scenario: `datasets 5.0.1` (or what it pulls in) is installed beside pins it doesn't declare compatible. The suite would still pass, but the fork-suite environment (§2) and any code path that imports `datasets` could break.
- I did not run `uv pip check`; it needs to be run on a fresh `.venv-bench` built from the lock.

**F5 — Low: venv versions are read from `*.dist-info` directory names** (`venv_versions`, diff 520–529). If a stale second dist-info for the same package remains, whichever the glob returns last wins. Scenario: leftover `mlx-0.32.3.dist-info` beside 0.32.4 gives a nondeterministic K2 result.

**F6 — Info:** `claim_out` writes `.build` before the record is validated (diff 906 vs 970), so a refused first start leaves a marker and a `sequence.log`. A rerun under the same label is still allowed. No byte of S's files is involved.

**Checked and correct:**
- **Expected build:** in code, no fallback for unknown labels, and mlx/mlx-metal 0.32.4 required per arm and venv (`EXPECTED_BUILDS`, `record_problems`).
- **Record before harvest:** the record and both worktrees are validated before any run-file harvest, and refusal is rc 1 (diff 969–976).
- **Label paths:** per-label record path and the M1 directory per label.
- **Each leg from its arm's worktree:** cwd, the leg's `--stack-root`, the server log and harvest paths (`roots[arm]`, diff 925–950).
- **Isolation and resume:** separate stems and `wave1.<b>/` directories; resume reads only `wave1_dir(build)`.
- **Leg re-assertion:** entry and exit checks against its own arm's `stack_head_<arm>`, plus the locks and venvs.
- **P504:** the overlay sha256 check (diff 274–279).
- **`--registry-on`:** retired under a label.
- **`s` unchanged:** the `s` argv is unchanged and no marker is written under `s`, confirmed by my passing `s` tests.
- **Local gate:** `.upstream-sync-ref` first, `AUDITS` parsed with `ast` (never executed), and the audit list included in the policy digest.
- **Naming exemption:** an anchored regex.

## 4. Verdict
Fix, then merge:
1. Make the seeding-test restore check patch-exact (F1). This is the one confirmed spec violation.
2. Tighten the registry restore check: exact restored lines in place, and one note inside `generation_defaults` (F2).
3. Replace the `new_side.py` exception with the pinned old→new lock pair, or regenerate the goldens, with the operator's ruling (F3).
4. Run `uv pip check` on a fresh `.venv-bench` built from the new lock and record the result; fix the lock if it fails (F4).
5. Before merging, rerun my frozen set with `frozen.s2.json` written in the candidate's names (`uv_lock_sha256`, `bench_lock_sha256`). The 43 (d) failures and 17 vacuous passes mean most of the S′ path is unverified by my set. Getting that rerun needs either the designer's approved fixture change or a candidate that also accepts my names.
