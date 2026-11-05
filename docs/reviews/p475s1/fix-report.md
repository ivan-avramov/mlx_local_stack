All 12 fixes are in, each with red-first tests. The one problem is that the unmodified frozen suite fails wholesale (210 errors + 4 failures), because its v1.1 fixture can't satisfy fixes 1, 2 and 5. When I updated the fixture to just those three v1.2 facts, 430 of 434 frozen tests pass, and TW F1's test, which failed on the round-1 candidate, now passes. Nothing is committed or pushed.

## Per fix

| # | Change (file → function) | Showing test (`test_p475_impl_fixes.py` unless noted) |
|---|---|---|
| 1 Sol P1 / TW F4 | `p475_kv`: `INSTRUMENT_FILES` (the contract's five), `instrument_shas`, `instrument_problems`. Pre-check compares the bytes of each file in `cfg.repo/benchmark/` and in the arm worktree; a file missing on either side refuses. The shas go in the receipt (`instrument`). `--base` and prepare defaults are unchanged. | `test_an_arm_instrument_file_differing…` (×5), `test_a_missing_instrument_file_on_either_side…` (×2), `test_the_receipt_records_the_instrument_shas` |
| 2 Sol P2 | `ARM_EDITS["N16"] = {"kv_bits": "0"}`; the scheme line stays. | `test_n16_changes_only_kv_bits…`, `test_an_n16_commit_that_removes_the_scheme_line_is_refused`, plus the fork's real `classify_kv_arm` accepting all 5 KV arms and refusing the old N16 shape |
| 3 Sol P3 | `dossier_binding_problems`: each receipt's leg, arm, block, attempt, model, base and entry/exit identity must match the run. `load_dossiers` also requires one arm commit per arm and one gitlink set, matching what `state.json` recorded, and refuses both dossiers when one slot has two usable ones. `_attempt` records the arm commits and gitlinks; `recorded_identity_problems` makes the pre-check refuse an arm re-committed mid-run. | `test_a_dossier_not_bound_to_this_run…` (×7), `…another_base…without_state`, `test_arm_commits_disagreeing…`, `test_the_run_records…`, `test_an_arm_recommitted_mid_run…`, `test_a_second_usable_dossier…` |
| 4 Sol P4 | `capacity_ladder.rung_problems`: `peak_memory_gb_cumulative` and `predicted_per_second` must be finite and > 0. `matrix` also checks every metric cell. | `test_rung_problems_needs_finite_positive…` (×16), `…absent_peak`, `test_a_leg_whose_backend_omits_peak_memory_is_invalid` |
| 5 Sol P5 / TW F3 | `Ops.group_alive` is in the protocol. `RealOps.group_alive` reads `ps -axo pid=,pgid=,stat=`, ignores zombies and raises if `ps` fails. `RealOps.signal_group` also signals a live group whose leader has exited. `_reap_driver` signals while any group member lives (also after a normal exit), escalates TERM → KILL and checks the group is empty; if the state can't be read, the leg is INVALID. `_teardown` checks the router's group (the wrapper pid) is empty. | `test_a_lingering_driver_child…`, `…survives_sigkill_is_invalid`, `test_an_empty_driver_group…not_signalled`, `test_an_unreadable_group_state…`, `test_a_surviving_router_group_member…`, the two `test_realops_group_alive…` tests |
| 6 Sol P6 | `_gate` / `_publish`: every dossier file goes through `p426_harvest.Gate(scrub, secrets).check(rel, original, "main")`, and the evidence logs with `"evidence"`. `default_scrub` now sets `emails`: `--operator-email` (new CLI flag), else `git config user.email` of the main checkout; an empty set refuses, as in P426. Foreign addresses in evidence go to `$STACK_WORKDIR/p475/review/<leg>.emails.json`. | `test_a_foreign_email_address…`, `test_a_reserved_example_address_is_allowed`, `test_the_operator_address_in_an_evidence_log…`, `test_a_credential_in_the_original_bytes…` |
| 7 Sol P7 / GLM F5 | `state["plan"] = {blocks, deciding_block}` is saved before the first measured leg. A changed `--blocks` then refuses (rc 2), and `blocks` is no longer in `CAP_NAMES`. `_deciding_step` saves `state["deciding"] = {block, started, complete}`, and a completed deciding block is never re-entered. The `matrix` CLI reads the saved plan. | `test_the_block_plan_is_persisted…`, `test_no_plan_is_recorded_before_any_leg`, `test_legs_without_a_recorded_plan_refuse`, `test_a_completed_deciding_block_is_not_re_entered`, `test_the_matrix_cli_reads…` |
| 8 Sol P8 | `matrix`: after the atomic write of one file, the other is unlinked. | `test_complete_then_partial…`, `test_partial_then_complete…` |
| 9 TW F1 | `_run_smoke`: a standing INVALID smoke leg stops the run, also on resume. | `test_an_invalid_smoke_leg_stops_on_resume`, `…tq4_smoke…`, frozen `test_an_invalid_canonical_receipt_wins_over_a_valid_variant` (now passes) |
| 10 TW F2 | `_destinations` includes `evidence-stage/<leg>`. `harvest` writes it through a temp dir and a rename and never overwrites it. On replay, byte-identical existing evidence is accepted; different content refuses. | `test_an_existing_evidence_stage_is_a_destination`, `…never_overwrites_differing_evidence`, `…accepts_byte_identical_evidence` |
| 11 TW F6 | `unresolved_flags`: a flagged cell with no deciding-block value is labelled `UNRESOLVED` (in the row and a header line), and the run exits 1. | `test_an_unresolved_instability…`, `test_a_resolved_flag_is_not_labelled_unresolved` |
| 12 Smoke | `SMOKE_ARMS = ("N16", "TQ4")`; `leg_name` now carries the arm (`u4-tq4-smoke.a1`). Every receipt records `worker_env` (all variable names, values only for KV/TQ names), `telemetry` (`prompt_n` vs `prompt_tokens`, `prompt_per_second` vs the value derived from `prompt_ms`, and their relative difference) and `drafter_keys`. | `test_the_smoke_run_is_n16_then_tq4…`, `test_the_smoke_leg_names_carry_the_arm`, `test_each_smoke_receipt_records…` (also checks no credential value leaks), `test_the_worker_env_record_keeps_kv_values…` |

Test-support changes: the implementer fake gained `group_alive` and lingering-member knobs and installs the instrument files. Four of my round-1 tests encoded the old rules and were updated to v1.2: N16 dropping the scheme, smoke being one leg, a zero deciding cap exiting 0, and one harvest-replay test that now seeds the plan.

## Commands and summary lines (from `benchmark/`)

- **Red baseline** (only the `INSTRUMENT_FILES` constant added): `test_p475_impl_fixes.py` → `64 failed, 13 passed in 5.04s`. The 13 were already-true regression guards.
- **Frozen + implementer, unmodified** (`… -m pytest -q -p no:cacheprovider bench/tests/p475s1 bench/tests/test_p475_impl_*.py`) → `4 failed, 458 passed, 210 errors in 87.07s (0:01:27)`. Every error and failure comes from `H.ready()` asserting `prepare == []`: the frozen fake writes N16 *without* the scheme line, which fix 2 now refuses.
- **Frozen with the v1.2 fixture plugin** (`-p bench.tests.test_p475_impl_v12_fixture bench/tests/p475s1`) → `4 failed, 430 passed in 82.15s (0:01:22)`.
- **Implementer suites** → `238 passed in 20.56s`, then `238 passed in 20.88s` on a second run (no flakes).
- **Touched suites** (`test_run_capacity`, `test_capacity_*`, and every `bench_watch` / `chain_ops` / `p426` file) → `557 passed in 35.92s`, unchanged.

The plugin is `bench/tests/test_p475_impl_v12_fixture.py`, a new file next to my tests (still inside the test scope). It is inert unless loaded with `-p` and patches only three things: N16 keeps the scheme line, the fake worktrees hold the instrument files, and `FakeOps.group_alive` exists. It's diagnostic only; the d3 test-writer should fold these facts into `fakes.py` itself.

## Frozen tests I judge unsupported by v1.2

1. `test_leg_precheck.py::test_n16_must_drop_the_scheme_key_not_keep_turboquant` — the old N16 rule; fails by design, as the brief anticipated.
2. `test_run_control.py::test_the_smoke_run_is_one_n16_leg_and_writes_no_matrix` — v1.2 smoke is N16 then TQ4.
3. `test_harvest.py::test_resume_replays_the_harvest_of_a_receipt_without_a_dossier` and
4. `test_harvest.py::test_a_stale_stage_directory_from_a_crash_is_replaced_not_merged` — both leave the PII row injection on and repair only the N16 smoke's rows. Under v1.2 the TQ4 smoke inherits the injection, its harvest is correctly refused, and the run exits 1. The first also asserts no new stack starts, which the TQ4 smoke contradicts.
5. Beyond those four, the whole frozen fixture is pre-v1.2 (N16 registry, no `group_alive`, no instrument files). That is the source of the 210 setup errors in the unmodified run.

## Judgement calls and gaps for you or the designer

- **Production stays fail-closed.** I added no compatibility shim for old ops objects: a missing `group_alive` or instrument file refuses.
- **Extra refusal beyond the brief.** If measured legs exist but `state.json` records no block plan, `run` refuses (rc 2). Otherwise losing `state.json` would silently reset `--blocks` and the monotonic caps.
- **Dossier problems stop the run** before the instability rule is applied (`_Stop`), so instability is never computed on inconsistent data.
- **Router group is checked, not signalled.** Contract step 6 says only "verified"; signalling it would sit in `chain_ops`, which is out of scope.
- **Operator email comes from `git config user.email`** when `--operator-email` isn't given. The frozen tests use the default scrub, so they now depend on that git setting, like the existing hostname, user and credential reads.
- **Unchanged on purpose:** a VALID but speed-invalid smoke leg is still re-attempted on the next invocation, as in round 1.
- **Still unproven on the live box** (only recorded, per the dispositions): GLM F1 (whether `psutil` shows the worker's in-process `KV_BITS`) and GLM F3 (the two telemetry identities). The TQ4 smoke receipt's `worker_env.kv_tq` and `telemetry` fields answer both.
- **Not satisfied:** nothing in the adopted list.

The copied frozen tests sit untracked in `bench/tests/p475s1/`, with permissions as copied, never edited.
Every leg receipt now records the watcher's argv, and a watcher pointed at any rows file other than the leg's own is a speed problem (SPEED_INVALID, replaced per R11), never INVALID. The new tests were red first and now pass, and the other suites give the same results as before.

## Change
- **`benchmark/bench/p475_kv.py`, new `watch_rows_problems(argv, rows_path)`:** the `--capacity-rows` values in the watcher argv must equal exactly `[str(cfg.capacity_outputs(arm, leg)["rows"])]`. A different path, a missing flag or the flag given twice each produce one entry in `speed_problems`.
- **`run_leg`:** builds the watcher argv once and stores it in the receipt as `watcher_argv`. It runs the check before `ops.start_watch` and passes that same argv to the watcher. A leg with no driver has no watcher, so it has no `watcher_argv`.

## Tests (`benchmark/bench/tests/test_p475_impl_fixes.py`, new "P651 / C293" section)
- `test_the_receipt_carries_the_watcher_argv_and_a_matching_rows_path_is_no_problem`: with the matching path the leg is VALID and speed-valid with no such problem. `watcher_argv` equals the argv `start_watch` received, in both the returned and the on-disk receipt.
- `test_a_watcher_on_another_rows_file_is_speed_invalid[other_rows_file | no_capacity_rows]`: with `watch_argv` monkeypatched, the leg is VALID, `speed_valid` is false, the problem is in `speed_problems`, and the receipt carries the argv the watcher was started with.
- `test_a_watcher_on_another_rows_file_is_replaced`: in a full run, the affected leg `u4-af8-b1.a1` gets its replacement `u4-af8-b1.a2` and the run exits 0.

## Commands (from `benchmark/`) and summary lines
- **Red first** (`-k "watcher_argv or another_rows_file"`): `4 failed, 77 deselected in 0.87s`
- **Implementer suites** (`bench/tests/test_p475_impl_*.py`): `242 passed in 18.29s`
- **Frozen + implementer, unmodified** (the brief's command): `4 failed, 462 passed, 210 errors in 87.60s (0:01:27)`. This is the same pre-v1.2 fixture breakage I reported last round; the 4 extra passes are the new tests.
- **Frozen with the v1.2 fixture plugin** (`-p bench.tests.test_p475_impl_v12_fixture bench/tests/p475s1`): `4 failed, 430 passed in 82.61s (0:01:22)`. These are the same four frozen tests I judged unsupported by v1.2 last round.
- **Touched suites:** `557 passed in 33.76s`, unchanged.

Nothing is committed or pushed.
