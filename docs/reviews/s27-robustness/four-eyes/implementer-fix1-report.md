# S27 robustness bundle, review round 1 of 3: fix report

**Summary:** 18 of the 19 findings are fixed, each with a red test. X5 did not reproduce on candidate 1; I added a one-line hardening and say so below. The frozen set is at **202/209**. The 7 failures are frozen tests that conflict with adopted findings X3, X6 and X9, so I'm reporting them instead of satisfying them. For each, I show the scenario passes once only its fixture is updated. X19's cause is found and fixed: a leaked test patch of `ProcessGuard.__init__`. Nothing was committed, unstaged or reset.

Red tests are in the new file `benchmark/bench/tests/test_s27_impl_r1fix.py` unless named otherwise. "Before" means run with candidate 1's behaviour in place, by writing the test first or briefly reverting the line.

## Findings

| id | change (file) | red test | before → after |
|---|---|---|---|
| X1 | The three probe CLIs take their `--tg*-inject` choices from `rc.ALL_INJECT_KINDS`, reached through `tg1_runner.rc` / `tg2_runner.rc` / `arm_runner.rc` (the P311 entry-import pin forbids a new import). `inject_verify.KINDS` and `run_inject.KINDS` are that same tuple. | `test_x1_*`, through the real `_parser()` | `interrupt` rejected → pass |
| X2 | `p426_reconcile._open_step_at_signal`: when the `/metrics` sample read 0, the trailing failed line is accepted only on recorded evidence. That means a delivered signal, exactly one step open at the signal by END offsets, one more started than completed request, failed delta 1, and the failed line timed at or after `signal_at`. New probe fields: `step_start_offsets` (`token_turn_gate`), `signal_at` (`arm_runner`). The facts go in the item record's `late_record`. | `test_x2_*` (accepted; 5 variants each missing one anchor are refused) | accept case failed only on `inflight_evidence` → pass |
| X3 | `GradeWorker.finish()` returns an interim infra fault instead of raising. `_run_item` records it as `termination.interim_grade_fault` and the final grade decides. | `test_x3_*`, including the full probe run | SystemExit → row written, passed |
| X4 | `p426_hooks.accounting_sealed_for` treats the sidecar as "already sealed" only if it is a regular file (not a symlink) sealed for this slot, attempt and row. Otherwise the leg pauses. | frozen `…unwritable_sidecar_pauses_the_leg` plus 4 `test_x4_*` | 4 failed → pass |
| X5 | **Did not reproduce.** Candidate 1 already sets `stage="ready"` at the start of each item (`arm_runner.py:1342`). I added `ctx.update(id=None, stage=None)` at the item boundary so no stale `done` can survive. | `test_x5_*` (real probe, ready-barrier fault on item 2) | already passed on candidate 1 |
| X6 | New `tg.GraderInfraError(kind=spawn\|transport\|image\|connection)`, raised at the tg2_grade sites where the harness's own docker call fails. `grader_infra_fault` is now an `isinstance` check; the substring marker list is deleted. A stage failure counts as infra only at rc 125 (docker itself failed). | `test_x6_*` | agent text counted as infra → never |
| X7 | `bench_watch.BoxSampler._ours`: ours = the driver, its descendants, and the sessions *led* by a descendant. Never the driver's own (shell) session. | `test_x7_*` | shell session claimed → pass |
| X8 | `foreign_new` entries keep `argv` as only the scrubbed executable basename, plus `argc`. The chain scan's `path_only` list does the same. | `test_x8_*` | full argv stored → pass |
| X9 | The `unpublished` shape now requires `last_step_start` to be a string equal to the n-th message id; it is never waived. My impl D1 fixture gains `last_step_start: "msg_26"`. | `test_x9_*` | id missing was accepted → refused |
| X10 | Shared ownership helpers in proc_guard (`session_claim`, `env_claim`, `path_claim`, `hermetic_homes`) are used by both the guard and the chain scan. Session members must have started at or after the probe's recorded start (`probe_session.started`, passed through as `not_before`). Without a recorded start, the scan proves nothing. Unreadable processes are listed; a possible session member makes the scan uncertain. | `test_x10_*` | 5 failed → pass |
| X11 | Pids the scan can't construct, or whose `uids()` read is denied, are now kept (`_scan(…, denied)`, `_dropped`). `_claim_dropped` makes them a claimed obligation if tracked or in the probe session, otherwise counts them. | `test_x11_*` | 4 failed → pass |
| X12 | `p426_freeze.interrupt_ok` (verdict PASS, inject_verify PASS, rc 0, row sha) is required by v8's `positives_problems`. The writer fails any PASS whose row is missing or differs, for every kind. | `test_x12_*` | 5 failed → pass |
| X13 | One verification loop covers everything cleanup killed, including the tracked audit's last round. A survivor is only one not verified gone. | `test_x13_*` | CleanupUncertain → certain |
| X14 | Removed `Chain.__getattr__` and its class-level defaults. `paused_path` is now a property derived from `out_root`. Test builders set the state explicitly. | `test_x14_*` | 7 failed → pass |
| X15 | An unclaimed process provably older than the guard, with a denied cwd/argv/environ read, is counted. | `test_x15_*` | count 0 → 1 |
| X16 | `HookInfrastructureError(not_evaluated=…)`. The done hook names the checks it never reached (`DONE_CHECKS`), and the sidecar records `not_evaluated`. | `test_x16_*` | not run before the fix (the exception had no such attribute) → pass |
| X17 | Removed the `session_id` parameter from `ProcessGuard` and `_run_item`. Tests use the leader path instead (`getsid(0) == getpid()`). | `test_x17_*` in `test_s27_impl_guard.py` | not run before the fix → pass |
| X18 | Every frozen or existing test edit is listed in the next section. | — | — |
| X19 | See the X19 section. Regression test: `test_x19_no_test_module_patches_the_guards_init_beside_the_hermetic_scan`. | — | — |

One more fix from my own review: matching the environment against hermetic roots now accepts both the given and the resolved spelling. Otherwise `/var/…` vs `/private/var/…` on macOS would have broken matching. Test: `test_x10_the_shared_environment_rule_matches_either_spelling…`.

## Edits to frozen and existing tests

**Frozen files:**
- `test_b2_frozen_s4_reconcile.py::test_fix_the_done_hook_invalidates_a_server_count…` (X18, §5.3/§5.9): a pairing skew is now `accounting_fault`. The item record must still say `invalid` with `fault_class: accounting`, and the sidecar must name `pairing`.
- `b2_frozen_support.py`: added a new knob, `B2_FOREIGN_SESSION_ITEMS`. The server logs the item under another session, which fails `session_backend` (still integrity under §5.9). The existing skew knob is unchanged.
- Four frozen tests switched from the skew knob to the new knob, keeping their INVALID refusal (§5.9): `test_b2_frozen_fix_cases.py` (×2), `test_b2_frozen_s7_locks.py::test_new_a_failed_done_check…`, `test_b2_frozen_add_ledger.py::test_new_an_invalidated_item…`.
- `p586_frozen/conftest.py::bare_chain` (X14): sets the S27 chain state explicitly.

**Existing (non-frozen) tests:**
- `test_b2_s7_locks.py` and `test_b2_fix_chain.py`: same knob swap.
- `test_b2_s3_core.py`: `s27_state()` builder and `pending_reruns=[]` stubs (X14).
- `test_c157_proc_guard.py`: the fixture uses the leader path instead of wrapping `__init__` (X17/X19).
- `test_g1_round2_proc_guard.py::test_p13_a_denied_uid…`: the process is given a readable foreign session and the test asserts it is counted (X11).
- `test_m76_b4b1_impl_wave2.py`: the fake writes a real row with its sha and `rc=0` (X12).
- `p371_baseline/compare.py`: added the new termination keys to the additions table.
- Impl tests updated: `test_s27_impl_guard`, `_scan`, `_runner`, `_positives` (to the new interfaces).

## X19: what caused the broad-run failures
The conftest's hermetic scan replaces `ProcessGuard.__init__` itself and restores it after each test. Candidate 1's C157 fixture (also active in `test_g1_round2`) wrapped `__init__` again through `monkeypatch`. That monkeypatch is undone *after* the hermetic restore, so it puts the hermetic wrapper back for the rest of the run. Every later `real_process_scan` test then silently uses the family scan:
- **The p585 test:** the family scan uses `process_iter`'s cached objects, so the patched `create_time` is never read and this process stays in the list.
- **The rapid-fork test:** a setsid'd leak whose parent died early is a documented blind spot of the family scan.

I reproduced it with a temporary module (since deleted). With it run first, both tests failed and `__init__` remained `install.<locals>.__init__`; without it, they pass. Removing the fixture's wrapper (X17) fixes the cause. The regression test fails if any test module other than the conftest patches `__init__`.

## Commands and results
All via `../fe_test.sh stack …`:

| run | result |
|---|---|
| Frozen set (10 files) | **202 passed, 7 failed** (the conflicts below) |
| All impl tests plus `test_s27_p6` | 246 passed |
| A: b2 / c147 / watch / chain_ops, 41 files | 1958 passed, 4 failed → all 4 fixed by the knob swap; rerun with the support checks: 246 passed, 2 failed |
| B: p371, 49 files | 708 passed |
| C: m62–m76, 33 files | 842 passed, 5 failed |
| D: 49 files | 1778 passed, 1 failed (`test_p311_entries`, caused by my X1 import) → fixed; rerun with the identity/probe modules: 224 passed |
| E: `p586_frozen`, `s26_frozen`, `p475s1` | 1029 passed, 1 failed |
| proc_guard / scan / watch (final rerun) | 455 passed |

The remaining existing-test failures, none caused by this round:
- **`test_b2_frozen_s0_support` ×2:** they pin base-commit file hashes and schema-1 cleanup keys, which the §9 identity rotation changes. Both are in candidate 1's run (`scratch/final.txt`).
- **Family C ×5** (`test_m64_arm_closure`, `test_m76_b4b1_fe_golden_tg1`, `test_m76_b3_impl_golden_mtp` ×3): environmental. Commit `f2b61127…` is missing from this clone, and the canonical remote / `GATE_PUSHED_BASE` is absent. Two of these are in `final.txt`.
- **`s26_frozen::test_fix_an_exception_message_never_carries_the_absolute_home_path`:** pytest's tmp dir is under the home directory here. Also in `final.txt`.

I couldn't run the baseline commit itself; "also failing on candidate 1" comes from `final.txt`.

## Frozen tests that conflict with adopted findings (for the designer)

| frozen test | finding and context | recommendation and strongest counterpoint |
|---|---|---|
| `test_s27_fe_grader::test_an_interim_grader_infrastructure_fault_ends_the_probe…` | **X3.** The fake client exits before the interim fault surfaces, so the fault is first seen at `finish()`. X3 says the final grade then decides. | Change the test so the fault lands while the client is still running, or expect the X3 outcome. `test_x3_run_item_records…` shows the X3 outcome on the same scenario. Counterpoint: an interim fault during generation can starve the gate's progress signal, which might argue for a rerun after all. |
| `test_s27_fe_grader` ×3 final-grade tests | **X6.** The fixture `test_s27_fe_support.infra()` is a plain `TransportAbort` that only counted as infra because of its text. | Make `infra()` return `GraderInfraError(…, kind="transport")`. `test_x6_the_frozen_final_grade_scenarios_hold…` shows all three pass with only that change. Counterpoint: anchoring on a harness-composed message prefix would satisfy both without touching the fixture, but it is still text matching. |
| `test_s27_fe_reconcile` ×2 and `test_s27_fe_done_hook::…recorded_d1…` | **X9.** The recorded D1 row predates the `last_step_start` field, so X9 refuses it. | Add `last_step_start` to the fixture row; the designer check names the step's id. `test_x9_the_frozen_d1_cases_hold…` shows all three pass. Counterpoint: the historical row really did lack the field, so the fixture would no longer be the byte-recorded row. |

## Choices I made where the findings left room
- **X2:** a timing anchor (`signal_at`, taken just before the signal) compared with the worker's `last_error.timestamp_unix`.
- **X4:** a sidecar only counts as sealed when it is a regular file, not a symlink.
- **X6:** a stage failure is infra only at rc 125; a stage timeout is not, since an agent could cause one with many files. **Not achievable in scope:** tg1 Go's "Docker infrastructure failure" is decided inside `structured_grade.parse_go`, which isn't in the brief's file list. tg1 Go docker faults are therefore no longer regraded; they abort as they did before S27. Typing them needs `structured_grade` added to scope.
- **X8:** kept the `argv` key, holding only the basename, because the frozen ownership test requires the key.
- **X10:** a session scan with no recorded probe start is uncertain, not trusted. Existing manifests have no `started`, so a chain scan on them pauses.
- **X11:** a dropped pid with an unreadable session id is claimed, following the §3.2 "as today" rule.
- **X12:** I put the evidence requirement in v8 rather than in `inject_accepted`, because a frozen test pins `inject_accepted`'s entry rule.
- **X18:** for the skew-based tests, I swapped the stimulus to an integrity mismatch rather than relaxing their expected outcome, so they keep testing leg-INVALID behaviour.
- **Not done:** the conftest could be hardened to install its wrapper via `monkeypatch` (LIFO undo), which would prevent X19's class of leak in future. It's out of scope; tell me if you want it.

The change ledger row L1 (`change-ledger-impl.md`) is rewritten for X2. Scratch helper scripts I wrote (not runnable here without approval) remain at `../scratch/mk_cand1.sh` and `run_cand1.sh`.