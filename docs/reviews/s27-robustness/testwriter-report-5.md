# Test-writer report, delivery 5 (the last): S27 bundle, fix round 3 (candidate 4)

**Verdict: merge.** Z1–Z6, Z8 and Z9 are resolved as far as I could check. My whole set (299 tests) and `test_s27_impl_*` (279) pass on candidate 4, and I found no defect. One limit applies: spec v1.5 is not in my copy (section 3).

## 1. New tests (`test_s27_fe_r3.py`, 11 tests)

I read `test_s27_impl_r3fix.py` first. It already has real-process tests for Z5 and a real `BoxSampler` test for Z6. I wrote different angles and left out what it covers (Z4, Z8 and Z9 are the implementer's alone).

Candidate 3 cannot be run beside candidate 4, so "candidate 3 failed" below is by inspection of the fix description and `fix-3.patch`, not by a run. The baseline column is a real run.

| finding | test | class | what it states | baseline | cand. 4 |
|---|---|---|---|---|---|
| Z6 | `test_z6_a_real_boxsampler_tick_carries_the_marker_of_a_busy_process_nowhere` | (a) | a real busy process has a marker string as two of its arguments; a real `BoxSampler` ticks until the process is in the top five (the test fails if it never is); the marker appears nowhere in the whole tick (JSON-dumped) nor in the alerts raised from it; no row has an `argv` key | not collectable | pass |
| Z5 | `test_z5_a_real_foreign_process_with_a_title_and_secret_arguments_is_recorded_by_its_executable_only` | (a) | a real process with title-style argv[0] and a marker argument, listed through the real guard: `foreign_new` has the executable basename and `argc` 4, the marker and the title are nowhere in the status, and the process is not killed | not collectable | pass |
| Z2 | `test_z2_a_live_leader_that_is_not_the_recorded_probe_claims_nothing_and_its_other_members_leave_the_scan_uncertain` | (a) | real processes: a live session leader whose start is not the recorded probe's: `session_reused` records it, `killed == []`, both the leader and its member are alive, and `certain` is False (designer ruling C5) | not collectable | pass |
| Z2 | `test_z2_the_recorded_probe_session_is_still_claimed_and_certain_after_the_snapshot_first_rule` | (b) | the recorded probe leading its session: its member is killed, `session_reused` is None | not collectable | pass |
| Z3 | `test_z3_freeze_and_harvest_take_a_null_item_record_only_when_the_record_is_absent` ×6 | (a), (b) | through the real freeze and harvest checks on a synthetic leg: accepted when the record is absent and the sidecar names none (with or without a recorded failure) and when the sidecar names the existing record; refused when the record exists but the sidecar names none (with or without a recorded failure) and when the sidecar names a record that does not exist; the two consumers agree in all six | not collectable | pass |
| Z1 | `test_z1_a_docker_status_fault_whose_container_removal_also_fails_is_still_regraded_inside_the_probe` | (a) | through the probe's own `final_grade` loop: the first attempt's `docker run` fails with status 125 and its container removal also fails; the typed fault survives, the same snapshot is regraded once, and the second attempt passes (`final_regrades == 1`) | not collectable | pass |

Baseline note: `test_s27_fe_r2.py` and `test_s27_fe_r3.py` import helpers from the implementer's test files, which do not exist in the baseline copy. They cannot be collected there.

## 2. Runs

All through `../fe_test.sh stack …`.

| run | result |
|---|---|
| my whole set on candidate 4 (12 files: reconcile, ownership, offsets, positives, done_hook, chain, grader, harvest_view, push_binding, r1, r2, r3) | **299 passed** |
| `test_s27_fe_r3.py` alone on candidate 4 | 11 passed |
| `test_s27_impl_*` on candidate 4 | **279 passed** |
| the ten collectable files on the baseline copy (r1 refreshed there; r2 and r3 not collectable) | 157 failed, 114 passed |

No failures to quote verbatim. The v4 set passes unchanged (288), so the implementer's C1 alias rule keeps my earlier `test_x10_the_scan_kills_a_process_that_carries_the_runs_home…` green.

## 3. Review of fix 3 against Z1–Z9

| id | verdict | evidence |
|---|---|---|
| Z1 | resolved | the primary typed fault now survives a failing removal (the cleanup failure rides on it as a note); a cleanup failure that is the only failure is a typed `transport` fault; confirmed through my `final_grade` regrade test, and the implementer's eight tests pass |
| Z2 / Z7 | resolved | the leader is validated inside the process snapshot; a leader that is not the recorded probe claims nothing, and a reused session's other members make the scan uncertain; my two real-process tests pass |
| Z3 | resolved | a sidecar may name no item record only when none exists at the path; freeze and harvest agree in all six of my cases, and the item-record read refuses symlinks |
| Z4 | resolved per the implementer's tests; I read `_ancestry` / `_ancestry_holds` and found the walk sound | a claim whose readable start differs from the claimed one falls through to the session and environment rules |
| Z5 | resolved | identity is the executable basename (capped) plus `argc`, "unknown" when unreadable; my real-process test shows a title and a secret argument are never recorded |
| Z6 | resolved | the watcher's `top_cpu` rows carry `exe` and `argc`, and `bench_watch.py` has no remaining `argv` / `cmdline` use; my whole-tick leak test passes |
| Z8 | resolved per the implementer's test | not independently tested |
| Z9 | resolved | docstring, exact start comparison, regular-file guard on the item-record read |

Observations, none blocking:

1. **C1, accepted by the designer.** An absolute argv[0] that resolves to the process's own executable may name it, so a process can get a chosen word recorded only by creating a symlink of that name to its own binary and running through it. The name stays capped, and in `foreign_new` also scrubbed. This is residual and not a leak of arguments.
2. **Spec v1.5 is not in my copy.** `docs/specs/s27-harness-robustness.md` in my copy is still v1.4, with no `argc` and no §8.1 change. I checked Z6 against the brief's statement of §8.1 (executable basename plus argc, never argument text), not against the spec text.
3. **Z8, Z9 and Z4.** I did not write new tests for them, since the implementer's tests cover them and I found no gap while reading the code.

Nothing was committed, pushed, reset or reverted; no environment variables or credentials were read or printed.
