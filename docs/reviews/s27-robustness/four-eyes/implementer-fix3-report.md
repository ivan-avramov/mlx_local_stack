# S27 robustness bundle — implementer fix round 3 report (Z1–Z6, Z8, Z9)

Working tree = candidate 3 (index) + these edits. Nothing staged, committed, reset or pushed. Frozen v4 files untouched.

## Per finding

| id | change (file:line) | red test(s) in `test_s27_impl_r3fix.py` | before (candidate 3) | after |
|---|---|---|---|---|
| Z1 | `structured_grade.py:411-426`: the `finally` is replaced by `except BaseException as primary` (removal tried, its failure added as a `__notes__` entry on the primary, the primary re-raised) plus a success-path removal whose failure is raised as `GraderInfraError(kind="transport")` chained from it. The OOM / mem-kill early `return` inside the `try` became an assignment so the success-path removal always runs; parsing moved unchanged into `_parse_outputs` (`structured_grade.py:428`). | `test_z1_a_cleanup_failure_never_replaces_the_typed_primary_fault[uncertain,oserror,timeout]`, `test_z1_a_cleanup_failure_never_replaces_a_typed_docker_status_fault`, `test_z1_the_primary_exception_of_an_abort_propagates_past_a_cleanup_failure`, `test_z1_a_cleanup_failure_that_is_the_primary_failure_is_a_typed_grader_infrastructure_fault[uncertain,oserror,timeout]` | 8 FAILED | 8 passed |
| Z2 (+Z7) | `chain_ops.py:979-1095` `owned_scan`: the process snapshot (`[(pid, Process or None)]`) is taken first (`:1011`); the leader is the snapshot's own entry for `pid == sid`, its start read from that object. Absent from the snapshot → it exited, members are bounded by the probe's start. Unreadable → problem, no session claim. Start ≠ `not_before` → `session_reused`, no session claim, `reused_sid` kept. For a reused id, each other process is checked against it (`:1058`): an unreadable sid or uid/process → listed with a problem (Z7); a member left unclaimed after the environment check → problem `a member of the reused session id … left unclaimed` (`:1093`). No session claim comes from a read taken before the snapshot. | `test_z2_a_leader_pid_reused_after_an_earlier_leader_check_is_never_claimed`, `test_z2_a_reused_sessions_unclaimed_member_leaves_the_scan_uncertain`, `test_z2_z7_a_reused_sessions_unreadable_would_be_member_leaves_the_scan_uncertain`; controls `…_reused_leader_alone_…_certain`, `…_unreadable_leader_in_the_snapshot_claims_nothing`, `…_without_its_leader_still_claims_its_members`, `…_recorded_probe_leading_its_session_is_claimed_with_its_member` | 3 FAILED (4 controls passed) | 7 passed |
| Z3 | `p426_hooks.py:92-160`: `read_item_record(path)` (`:95`) returns None only when nothing exists at the path (`lstat` → `FileNotFoundError`), the parsed document of a regular file, else `ITEM_RECORD_UNREADABLE`. `accounting_problems` (`:113`) no longer takes `recorded`. It applies one rule: no item record ⇒ the sidecar must name none; an existing one must be a self-sealed dict (`sealed_ok`) and named by its sha256. `recorded_accounting` removed (no caller is left). Callers: `chain_core.py:3266` (no `recorded`), `p426_freeze.py:414,429-431,455-466` (reads the record through `read_item_record`, so a symlinked record is refused), `p426_harvest.py:701-721` (record existence read on disk beside the sidecar, not inferred from the inventory, which drops symlinks). | `test_z3_a_sidecar_naming_no_record_is_refused_when_the_item_record_exists_whatever_is_recorded`, `test_z3_a_sidecar_naming_no_record_is_accepted_when_the_item_record_does_not_exist`, `test_z3_the_shared_validator_takes_record_existence_not_a_recorded_reason`, `test_z3_z9_the_chain_reads_the_item_record_regular_only_never_through_a_symlink`, `test_z3_freeze_refuses_a_symlinked_item_record_of_an_accounting_slot`; controls `test_z3_the_chain_refuses_a_null_sidecar_when_the_item_record_exists`, `test_z3_the_chain_accepts_its_sidecar_naming_its_regular_sealed_item_record` | 5 FAILED (2 controls passed) | 7 passed |
| Z4 | `proc_guard.py:958-1003`: `_ancestry` returns `{pid: {starts, parent, proc}}`. A seed keeps the start it was read with, or (read failed) the tracked starts of its pid. A child keeps its start or None. An unreadable seed's tracked start is now the parent start for the child's younger-than check. `_ancestry_holds` (`:991`) walks the node's path to its seed, re-reading each start. A readable start outside the recorded `starts`, or (for a node claimed unreadable) older than its parent's recorded start, means the claim does not hold. `_classify` (`:1023-1024`) then falls through to the session / environment rules, so the process is foreign, or uncertain when its reads are denied. | `test_z4_a_tracked_pid_reused_after_an_unreadable_seed_read_is_never_killed_nor_its_children`; control `test_z4_the_exact_tracked_identity_and_its_child_are_still_owned_by_ancestry` | 1 FAILED (control passed) | 2 passed |
| Z5 | `proc_guard.py:67-96` `exe_identity(p)` → (basename of `Process.exe()` capped at `FOREIGN_ARGV0_CAP`, or `"unknown"` when unreadable; argc or None). Used by `foreign_new` (`proc_guard.py:939-947`) and the chain scan's `path_only` (`chain_ops.py:1081-1084`). See choice C1 for the argv[0]-alias rule and C2 for test fakes. | `test_z5_the_chain_scans_path_only_identity_is_the_executable_never_the_title`, `test_z5_foreign_new_identity_is_the_executable_never_the_title`, `test_z5_an_unreadable_executable_is_unknown_never_argv0`, `test_z5_the_executable_basename_is_capped`, `test_z5_argv0_names_the_process_only_as_an_absolute_alias_of_its_own_executable` | 4 FAILED (the 5th was added after the fix, see "could not satisfy" 2) | 5 passed |
| Z6 | `m1/bench_watch.py:560-567`: each `top_cpu` entry carries `exe` (from `exe_identity`, then scrubbed) and `argc`; the `argv` field is gone. Alert text (`:597-598`) names `exe` and `argc`. Class docstring (`:490-492`) updated to spec v1.5 §8.1. | `test_z6_the_watchers_top_cpu_records_executable_and_argc_never_arguments`, `test_z6_a_foreign_alert_names_the_executable_and_argc` | 2 FAILED | 2 passed |
| Z8 | `arm_runner.py:318-328` `GradeWorker.finish()`: with a returned interim infra fault, both `self.grading` and `self.queued` are discharged from `gate.pending` / `gate.stall_wait`, and both are cleared. | `test_z8_finish_with_an_interim_infra_fault_also_discharges_a_capture_queued_after_the_worker_died` | 1 FAILED | 1 passed |
| Z9 | `chain_ops.py:990-1001` docstring: the snapshot-first rule. It states that the reuse branch rests on the kernel not reassigning a pid while a session / process group of that id has a member, and that the leader start is compared exactly with no tolerance: both values are the same unadjusted kernel read (`proc_guard.start_time`), and a tolerance could admit a different process. The code comparison stays `!=`. The item record read has the same `lstat` / regular-file guard as the sidecar: `p426_hooks.read_item_record`, used by `accounting_sealed_for` (`p426_hooks.py:163-176`). | `test_z9_owned_scan_documents_the_kernel_reservation_and_the_exact_leader_comparison`, `test_z9_the_leader_start_comparison_is_exact_to_the_recorded_value`, plus `test_z3_z9_…symlink` above | 1 FAILED (the exact-compare test passed: already exact) | 2 passed |

Before/after counts for `test_s27_impl_r3fix.py`: first run on candidate 3 had 33 tests, 25 FAILED / 8 passed (controls plus the already-exact Z9 compare). After the fixes the file has 34 tests (the Z5 alias test was added), 34 passed.

## Files changed (vs candidate 3 / the index)

- `benchmark/bench/structured_grade.py` — Z1: the cleanup failure is kept as evidence on the primary; a cleanup failure that is the only failure is a typed `transport` fault; `_parse_outputs` extracted.
- `benchmark/bench/chain_ops.py` — Z2/Z7/Z5/Z9: snapshot-first leader validation, reused-id members leave the scan uncertain, `path_only` via `exe_identity`, docstring.
- `benchmark/bench/proc_guard.py` — Z4/Z5: `exe_identity`; ancestry closure keeps identities; `_ancestry_holds`; `foreign_new` via `exe_identity`.
- `benchmark/bench/p426_hooks.py` — Z3/Z9: `read_item_record`, `ITEM_RECORD_UNREADABLE`, the record-existence rule, `recorded` removed, `recorded_accounting` removed.
- `benchmark/bench/chain_core.py` — Z3: `p426_write_accounting` calls `accounting_sealed_for` without `recorded`.
- `benchmark/bench/p426_freeze.py` — Z3: `_accounting_problems` reads the item record through `read_item_record` (drops its `rec` parameter).
- `benchmark/bench/p426_harvest.py` — Z3: `_accounting_problems` reads the item record on disk via `read_item_record`.
- `benchmark/m1/bench_watch.py` — Z6: `exe` + `argc`, no `argv`; alert text; docstring.
- `benchmark/bench/tests/test_s27_impl_r3fix.py` — new: the red tests above.
- `benchmark/bench/tests/test_s27_impl_r2fix.py` — 5 tests updated (below).

## Edits to existing tests (all in `test_s27_impl_r2fix.py`; no frozen file touched)

1. `test_y3_an_unreadable_session_leader_leaves_the_scan_uncertain_and_claims_nothing`: `psutil.pids` now lists 5150 (it was `[]`). Z2: the leader is validated inside the snapshot. A leader absent from the snapshot has exited and is not "unreadable".
2. `test_y4_a_sidecar_bound_…_is_accepted…` parametrization: `record-unnamed-recorded-failure` removed (it is now refused) and `no-record-unrecorded` added (it is now accepted). Z3: a sidecar may name no record iff no record exists.
3. `test_y4_freeze_and_harvest_refuse_…` parametrization: `no-record-unrecorded` replaced by `unnamed-recorded` (`dict(named=False)`). Z3, same clause.
4. `test_y4_the_chain_counts_an_existing_sidecar_…`: the `recorded=` arguments are dropped (Z3 removes the parameter). It now asserts that the null sidecar stands while no record exists, that another row is refused, and that once an item record exists the null sidecar is refused.
5. `test_y6_the_chain_scans_path_only_basename_is_capped_at_64_characters`: the expected identity is the executable's basename, not the title, and the title text is asserted absent (Z5). The cap is covered by `test_z5_the_executable_basename_is_capped`.

## Commands and results (`../fe_test.sh stack <files>`, paths relative to `benchmark/`)

- `bench/tests/test_s27_impl_r3fix.py` on candidate 3: 25 FAILED, 8 passed (33 tests). After the fixes: 34 passed.
- Frozen v4 (`test_s27_fe_{grader,ownership,harvest_view,push_binding,r2,support,done_hook,chain,positives,offsets,r1,reconcile}.py`):
  - Mid-way run, before choice C1: `1 failed, 287 passed`. Failure verbatim: `FAILED bench/tests/test_s27_fe_r1.py::test_x10_the_scan_kills_a_process_that_carries_the_runs_home_and_leaves_a_bystander_and_a_path_only_match` — `AssertionError: assert ([{'pid': 38277, 'argv': ['python3.12'], 'argc': 3}] and ['python3.12'] == ['python']`.
  - Final run: **288 passed**.
- All `test_s27_impl_*` (gate, watch, chain, harvest, reconcile, runner, positives, guard, scan, r1fix, r2fix, r3fix):
  - Before the r2fix edits: `5 failed, 274 passed`. The 5 failures were exactly the 5 tests listed above.
  - Final run: **279 passed**.
- proc_guard + chain_ops family (`test_proc_guard`, `test_c157_proc_guard`, `test_g1_round2_proc_guard`, `test_c151_start_time`, `test_p585_proc_guard_systemerror`, `test_chain_ops`, `test_m64_chain_ops`): **292 passed**.
- structured_grade + arm_runner family (`test_structured_grade`, `test_c147_grade_reports`, `test_m62_revision5`, `test_p604_go_package_load`, `test_p607_p371_grader_pair`, `test_m62_safety`, `test_m62_tools`, `test_c147_tmp_escape`, `test_tg1_runner`, `test_c147_cancel`, `test_m62_v5a`, `test_m62_v5a_identity`, `test_tg1_integration`, `test_m63_predictor`): **354 passed, 8 skipped**.
- bench_watch family (`p475s1/test_bench_watch_capacity`, `test_p475_impl_watch`, `test_p475_impl_fixes`, `test_p475_impl_fixes2`): **134 passed**.
- p426 hooks / freeze / harvest / chain_core family (`p586_frozen/`, `test_b2_*` (all), `test_p426_*` (all), `test_p586_*` (all), `test_m76_b4b1_*` (all), `test_c147_chain_runner`, `test_m64_chain`, `test_p371_chain_core`): **1 failed, 2689 passed, 85 skipped**. Failure verbatim:
  `FAILED bench/tests/test_m76_b4b1_fe_golden_tg1.py::test_b8_regenerates_byte_identical` — `AssertionError: REFUSED: frozen
  stack_head_on f2b61127c55f0436b6c6c777bec5384ce004d62d does not resolve: git rev-parse failed`. That commit is not in this copy
  (`git cat-file -t f2b61127…` → `fatal: git cat-file: could not get object info`, rc 128). The refusal happens before any code this
  round touched. It was not re-run on candidate 3, because that needs a reset I may not do (see "could not satisfy" 3).

## Could not satisfy / caveats

1. **Frozen-test conflict (Z5 vs frozen `test_s27_fe_r1.py::test_x10_…path_only_match`).** The frozen test expects `Path(sys.executable).name` (`python`, the venv link). `Process.exe()` returns the resolved binary (`python3.12`), so a strict exe() basename fails it (output above). I resolved it with choice C1 rather than leave it failing. If the designer rejects C1, the strict form fails this one frozen test.
2. The first red run of `test_z5_foreign_new_…` failed for a test-construction reason: the process was spawned before the guard, so it was "older" and never listed (`ValueError: not enough values to unpack`). After the fix to the test (the guard starts first), it was not re-run against candidate 3: I may not reset the working tree. By inspection, candidate 3's `_record_foreign` takes `Path(cmdline()[0]).name` = the title (no `/`) capped at 64, so `argv == [exe basename]` and `"indexing" not in …` both fail there. `test_z5_argv0_names_…alias…` was written after the fix and was likewise never run on candidate 3.

3. `test_m76_b4b1_fe_golden_tg1.py::test_b8_regenerates_byte_identical` fails because the frozen commit `f2b61127…` is absent
   from this copy. I could not show it failing on candidate 3 (no reset allowed). The cause is the missing commit object, not a
   changed module.

## Choices made

- **C1 (Z5)**: `exe_identity` names argv[0]'s basename only when argv[0] is an absolute path whose `realpath` equals the executable's `realpath` (an alias such as a venv's `python` link: a filesystem name of the same binary, not free text). A title, a relative name or a path to another file gives the `exe()` basename. Reason: it satisfies both Z5's intent (no free argv text) and the frozen x10 test. Residual: a process could only get a chosen word recorded by creating a symlink of that name to its own executable and running through it. The name is still capped, and scrubbed in `foreign_new`. Strict alternative: always the `exe()` basename, which fails frozen x10.
- **C2 (Z5)**: objects that are neither a `psutil.Process` nor have an `exe()` method (the frozen scripted fakes, e.g. `test_s27_fe_r1.py::test_x8_…`, which expects `["some-daemon"]` from argv `"/usr/libexec/some-daemon"`) fall back to their argv[0] basename. This follows `start_time`'s precedent ("objects without a psutil implementation (test fakes) keep their own create_time()"). Production always passes `psutil.Process`, so the fallback is unreachable there.
- **C3 (Z5)**: an unreadable executable gives `argv == ["unknown"]`. `foreign_new` for an unreadable process object (`p is None`) now records `["unknown"]` with argc None; it previously recorded `[]` with argc 0.
- **C4 (Z1)**: the success-path cleanup failure is typed `kind="transport"` (a failure of the harness's own docker CLI step). Only `Exception` is typed; a `BaseException` from cleanup (e.g. `KeyboardInterrupt`) propagates unchanged. The cleanup failure beside a primary is recorded with `add_note`, the mechanism `tg2_grade` already uses. Because the receipt index was written `parsed` before cleanup, `grade()`'s existing handler rewrites it as `infrastructure` before the typed fault propagates.
- **C5 (Z2)**: with a reused leader, the reused leader itself is never flagged (it is the recorded reuse). Every OTHER process of that session id is flagged when left unclaimed, and so is one whose session id, uid or process object is unreadable. A process of that id claimed by the environment rule is still killed. A leader that exits between the snapshot and its start read (`NoSuchProcess`) is treated as absent.
- **C6 (Z3)**: the record-existence rule replaces the "recorded done-step failure" authorization; I did not keep both together, because the ledger says "null allowed iff the item record does not exist". `recorded_accounting` and the `recorded` parameters are removed, not left in place unused. Harvest reads existence on disk (`read_item_record` beside the sidecar), because its inventory drops symlinks outside final trees, and an inventory miss would otherwise read as "absent".
- **C7 (Z4)**: a claim that fails `_ancestry_holds` falls through to the session and environment rules. A reused pid that legitimately is in the probe's session after the guard started is still owned by the session rule, never by ancestry. An ancestor whose start is unreadable both at closure time and now keeps the claim, as before; the claimed process itself still goes uncertain when its own key is unreadable.
- **C8 (Z6)**: the field names are `exe` and `argc` (the `argv` key is dropped rather than renamed in place). The basename goes through the sampler's existing scrubber.

## Questions

- Q1: Is C1 (the absolute-alias rule) acceptable to the designer, or should Z5 be strict and the frozen x10 conflict go to the operator?
- Q2: Is C5's rule right, that a reused session's unclaimed members make the scan uncertain? It PAUSES the leg. The kernel guarantee (Z9 docstring) implies those members belong to the new session, so this is fail-closed beyond what the guarantee needs.

## Clarification (gate)

The copy is candidate 4. Nothing was staged, committed, reset or pushed. No frozen file was touched.

### 1. `test_m76_b4b1_fe_golden_tg1.py::test_tg1_identity_unchanged_except_the_closure_fields`

Change (`test_m76_b4b1_fe_golden_tg1.py:182-200, 216-245`):
- `scaffold_policy_sha256` is removed from `INVARIANT_FIELDS`; the remaining fields (`arm`, `config_id`, `scaffold`, `polyglot_sha`) stay exact.
- It is named as the S27 §4.5 / §9 difference (`S27_POLICY_FIELD`), with a comment naming the clause.
- The test now asserts two things. The field differs from the golden. Recomputed with the baseline's `inject_allowed` (`PRE_S27_INJECT_ALLOWED = ("stall", "loop", "alloc")`), it equals the golden exactly. So the exemption is checked, not just declared.
- `_identity` gains an `inject_allowed=` option. It runs the same `run_tg1_probe.py --print-identity` in a subprocess, with only `tg1_runner.TG1_POLICY.inject_allowed` replaced (`dataclasses.replace`).

Verification (`../scratch/verify_policy_rotation.py`, run with the bench interpreter, CPython 3.12.15):
- This session has no `docker` CLI (`which docker` → `docker not found`), and the brief excludes docker. So the script supplies the golden's recorded `grader_image_id` in place of the `docker inspect` read; every other identity input is computed live. `toolchain_matches_golden: true` confirms the substitution reproduces the golden's toolchain.
- Output, verbatim:
  - `current_inject_allowed: ["stall","loop","alloc","interrupt"]`
  - `current_policy_sha: 16a948bef2f238a74c0399e033f8b12ca280f037336fea403c2e5062c57b12b5` (the gate's value)
  - `pre_s27_policy_sha: f56705f93546d0c3b310e3414b3442f0dc9f2a08f1a412523ca1a2138a581e33`
  - `golden_policy_sha: f56705f93546d0c3b310e3414b3442f0dc9f2a08f1a412523ca1a2138a581e33`
  - `pre_reproduces_golden: true`
  - `identity_keys_differing_current_vs_pre: ["generation_identity_sha256", "scaffold_policy_sha256"]`
- Conclusion: the rotation is caused only by `inject_allowed`. The second key, `generation_identity_sha256`, is derived from the policy sha.
- The pre-S27 identity still differs from the golden in other keys: `generation_identity_sha256`, `opencode_exe_sha256`, `probe_code_sha256`, `scoring_code_sha256` and the `snapshot_*` fields. These are the closure-derived and box-bound fields the test already excludes.
- Caveat: the edited test itself needs docker. In this session it fails with `bench.toolchain.ToolchainError: cannot inspect grader image aider-benchmark: FileNotFoundError` before reaching its assertions, so it has not passed here. It is expected to pass on the gate box, which has docker; that is not yet observed.

### 2. `test_m81_gate_pairing.py::test_a_branch_push_that_bumps_mlx_serve_needs_a_fork_receipt_paired_with_it`

Change (`test_m81_gate_pairing.py:75-79`):
- The stack PASS receipt now carries `pushed_base=base`. `base` is the commit already pushed to `origin/main`, so the protected paths are unchanged since it and the §12 binding passes.
- A comment names S27 §12.
- The refusal assertion for the unpaired fork receipt (`"not paired with src/mlx-serve"`) and the acceptance once a paired receipt exists are unchanged.
- Result: it passes in the run below.

### 3. One invocation of the requested families

Files: `test_local_gate*`, `test_m76_b4b1_*`, `test_m80_*` / `test_m81_*` (the `test_m8*` matches), `test_p541*`, `test_s25_p10*`, all `test_s27_impl_*`, and the frozen `test_s27_fe_*`. Run with `-rfEs`. Result: **5 failed, 1418 passed in 1331.53s**, no tests skipped. Failures, verbatim:

```
FAILED bench/tests/test_m76_b4b1_fe_corpus.py::test_probe_without_universe_defaults_to_the_tg2_universe
FAILED bench/tests/test_m76_b4b1_fe_corpus.py::test_probe_identity_with_an_inject_kind
FAILED bench/tests/test_m76_b4b1_fe_golden_tg1.py::test_b8_regenerates_byte_identical
FAILED bench/tests/test_m76_b4b1_fe_golden_tg1.py::test_tg1_identity_unchanged_except_the_closure_fields
FAILED bench/tests/test_m76_b4b1_fe_golden_tg1.py::test_tg1_probe_closure_identity_rotates
```

Causes:
- **`test_b8_regenerates_byte_identical`:** `AssertionError: REFUSED: frozen stack_head_on f2b61127c55f0436b6c6c777bec5384ce004d62d does not resolve: git rev-parse failed`. The commit is absent from this copy. Same as round 3, caveat 3.
- **The other four** (re-run singly; all four tracebacks identical): `bench.toolchain.ToolchainError: cannot inspect grader image aider-benchmark: FileNotFoundError`. There is no `docker` CLI in this session, and `--print-identity` reads the grader image id through it.
  - These are missing-tool failures, not skips. The tests do not skip when docker is absent.
  - Three of the four are tests I did not edit.
  - The gate's run (with docker) reported only items 1 and 2 as failing, which suggests these four depend only on the environment.

Still skipping for a missing corpus or tool: none (0 skipped). The polyglot corpus is present, and nothing in this set skipped for it.

Files changed in this clarification:
- `benchmark/bench/tests/test_m76_b4b1_fe_golden_tg1.py` — item 1.
- `benchmark/bench/tests/test_m81_gate_pairing.py` — item 2.
- `../scratch/verify_policy_rotation.py` — the verification script; not in the repo.
