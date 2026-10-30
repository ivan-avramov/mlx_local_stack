# Fix round 5: report

All five items are fixed test-first. Both check batches exit with code 0 with no failures. I did not run the frozen tests, I touched none of them, and nothing is committed or pushed.

## Item 1: republication and the amendment re-verify the dossier

- **Files:** `benchmark/bench/p426_wave2.py`, `benchmark/bench/tests/test_b2_fix5.py`.
- **New tests (5):**
  - `test_1_a_receipt_changed_after_the_pair_was_recorded_makes_makeup_refuse_publishing_nothing`, run for an unpublished and for an already-published pair record.
  - `test_1_the_amendment_check_needs_the_freshly_verified_dossier_not_only_its_file_hash`.
  - `test_1_republication_re_verifies_before_publishing_even_without_the_amendment_check`, with `verify_existing_amendment` patched out.
  - `test_1_an_untouched_recorded_dossier_is_still_republished_and_the_amendment_accepted`, a regression guard.
- **Red first:**
  - The `makeup` tests failed with `assert 0 == 1`: `makeup` ran although a pilot receipt had changed.
  - The republication test failed with `assert [PosixPath('…pilot__off-a1__on-a1.json')] == []`: the stale dossier was published.
  - The "published" variant's `makeup` test failed, and one guard test (republished and accepted) already passed.
- **Fix:**
  - New `reverify_recorded_dossier(record)` runs `verify_dossier` against the current receipts and harvest files of the record's two attempts. It recomputes the verdict and returns it.
  - `republish_dossiers` calls it before any publication.
  - `verify_amendment`, used by `run` and `makeup`, calls it on the selected pilot pair and requires the recomputed verdict to be PASS. It no longer relies on the file hash and the stored verdict alone.
  - On a changed receipt, `makeup` stops with rc 1 naming `receipt_sha256`, publishes nothing and launches no leg.

## Item 2: a ready record for every ledger entry, DNF included

- **Files:** `benchmark/bench/p426_freeze.py` (`leg_items_problems`, so `classify_leg` too), `benchmark/bench/p426_harvest.py` (`_check_references`), `benchmark/bench/tests/test_b2_fix5.py`.
- **Fixtures updated so a good DNF leg carries a sealed ready record and matching `ready_sha256`:** `b2_s8_support.py`, `test_b2_s9_harvest.py`, and the round-3 fixture `_leg_with_records` in `test_b2_fix3.py`.
- **New tests (6):**
  - A good DNF leg is VALID_WITH_DNF (guard).
  - A DNF with no ready record.
  - A DNF with a wrong `ready_sha256`.
  - A DNF with a ready record whose self-hash is wrong.
  - A row with a wrong `ready_sha256`.
  - The harvest fails a DNF with no ready record, and one with a wrong `ready_sha256`.
- **Red first:**
  - `AssertionError: assert ('VALID_WITH_DNF' == 'INVALID'` in four classification tests.
  - `Failed: DID NOT RAISE HarvestError` for the harvest tests.
- **Fix:**
  - Every ledger entry needs `items/<slot>.ready.json` with a valid self-hash.
  - The item or `.dnf.json` record's `ready_sha256` must equal that self-hash, in both classification and the harvest.
  - I applied the same rule to rows, which the brief's "every ledger entry" covers.

## Item 3: staging never follows a link

- **Files:** `benchmark/bench/p426_harvest.py` (`_publish_records`), `benchmark/bench/tests/test_b2_fix5.py`.
- **New tests (5):**
  - A stage symlink: the target stays untouched and the destination is not a link.
  - An existing regular stage file is refused and left in place.
  - A dangling stage symlink is refused and its target is not created.
  - A destination swapped for a link at rename time is refused.
  - A normal publication leaves a regular file and no stage.
- **Red first:** `Failed: DID NOT RAISE HarvestError` in the first four.
- **Fix:**
  - A stage is created with `O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW`.
  - Any existing stage path of any type refuses; it is never followed, reused or deleted.
  - A stage created in the same call is removed again if a later step fails.
  - After each rename the destination is `lstat`ed and refused unless it is a regular file.

## Item 4: exit code 4 whatever stopped the sequence

- **Files:** `benchmark/bench/p426_wave2.py` (`main`, a new `run_files_failed` flag), `benchmark/bench/tests/test_b2_fix5.py`.
- **New tests (3):**
  - A pair-gate stop (rc 1) plus a failing run-file publication gives rc 4, with both reasons in the log.
  - A failing publication at a clean `--through` end gives rc 4 and no `DONE` line.
  - Without a publication failure the original stop code stays rc 1 (guard).
- **Red first:** `assert 1 == 4` in the first.
- **Fix:** a failed attempted publication, whether raised inside `run()` or in the exit path, forces rc 4. The log keeps the original `STOP` line and adds `run files NOT published: …`.

## Item 5: credential sources from the frozen record

- **Files:** `benchmark/bench/p426_wave2.py` (new `frozen_env_files` and `build_box_ops`, used by `main`), `benchmark/bench/tests/test_b2_fix5.py`.
- **New tests (3):**
  - With `--worktree-*` pointing elsewhere, only the frozen worktree's `.env` is a source. A secret only there, placed in `sequence.json`, is refused and nothing is published.
  - A rehearsal takes the paths from its manifest.
  - An unreadable record gives no env files.
- **Red first:** `AttributeError: module 'bench.p426_wave2' has no attribute 'build_box_ops'` and `'frozen_env_files'`.
- **Fix:** `.env` paths come from the `off_worktree` / `on_worktree` of `v8_base.json` in `--record-dir` (the manifest for a rehearsal).

## Suites and counts

The wrapper prints only dots and the exit code, so counts are the dots of each output file. Both ran with `-q --tb=short -p no:cacheprovider`.

- **Batch A:** `../bin/run_stack_tests.sh bench/tests/test_b2_fix5.py bench/tests/test_b2_fix4.py bench/tests/test_b2_fix3.py bench/tests/test_b2_fix2.py bench/tests/test_b2_s1_cli.py bench/tests/test_b2_s2_probe.py bench/tests/test_b2_s3_core.py bench/tests/test_b2_s4_reconcile.py bench/tests/test_b2_s5_receipt.py bench/tests/test_b2_s6_watch.py bench/tests/test_b2_s7_locks.py bench/tests/test_b2_s8_freeze.py bench/tests/test_b2_s8_wave2.py bench/tests/test_b2_s8c_chain.py bench/tests/test_b2_s9_harvest.py bench/tests/test_b2_fix_chain.py bench/tests/test_b2_fix_goldens.py bench/tests/test_c147_chain_runner.py bench/tests/test_p311_chain.py bench/tests/test_p364_chain.py bench/tests/test_local_gate.py bench/tests/test_p426_wave1.py bench/tests/test_p426_harvest.py bench/tests/test_t3_wave1.py -q --tb=short -p no:cacheprovider`. Result: `[exited with code 0]`, 1359 passed, none failed or skipped.
- **Batch B:** `../bin/run_stack_tests.sh $STACK_WORKDIR/b2/arm-rebased/mlx_local_stack/benchmark/bench/tests/test_p371_*.py bench/tests/test_work_queue.py bench/tests/test_status.py bench/tests/test_m63_predictor.py bench/tests/test_p279_smoke.py bench/tests/test_c151_start_time.py bench/tests/test_tune_provenance.py bench/tests/test_samples_resume.py bench/tests/test_p426_watcher.py bench/tests/test_p426_session_ids.py bench/tests/test_p426_leg.py bench/tests/test_p426_bench_watch.py bench/tests/test_p311_closure.py bench/tests/test_p276_real_manifest.py bench/tests/test_m64_chain_ops.py bench/tests/test_m64_chain.py bench/tests/test_m64_arm_closure.py bench/tests/test_generate_run.py bench/tests/test_evidence_backfill.py bench/tests/test_conftest_fakes.py bench/tests/test_chain_ops.py bench/tests/test_bootstrap_lock.py bench/tests/test_bench_watch.py bench/tests/test_agentbench_watch.py -q --tb=short -p no:cacheprovider`. Result: `[exited with code 0]`, 1595 passed, 1 skipped (the `s` in row 12), none failed.
- **Correction:** I did not identify the skipped test; the wrapper hides the reason and I did not run with `-rs`. In my round 1–4 batch-B reports I said "no F/E/s/x". That was based on grepping for failure lines and was not verified against the dots, so the same skip may have been present then.
- `test_b2_fix5.py` alone: 22 tests, split 5 / 6 / 5 / 3 / 3 over items 1–5.

## Judged differently or not done

- **Weak tests tightened.** My first draft of the item 4 tests included one with an `or True` assertion and a `3 or 4` exit check. I replaced it with a test that asserts rc 4 and no `DONE` line.
- **Item 1.**
  - The order inside `run()` is: amendment verification, then republication, then the legs. The amendment check therefore often fires before the republication check; I patched it out in one test to cover republication on its own.
  - A tampered pilot dossier is now reported through whichever check runs first.
- **Item 2.** The brief names classification and the harvest. I put the logic in `p426_freeze.leg_items_problems`, which `classify_leg` and the pilot gate both use.
- **Item 3.** An existing stage path now blocks publication until the operator removes it, as specified. I did not add cleanup of stale stages. The `os.replace` / `_rename` step itself still has a theoretical race; the post-rename `lstat` detects the result but cannot prevent it.
- **Frozen tests.**
  - Not run, as instructed.
  - They may conflict where their fixtures have DNF legs without a ready record or `ready_sha256`, rely on a pre-existing `.stage` path, or publish unsealed records. This is carried over from rounds 3–5 and is unverified.
- **Left untouched:** `docs/specs/p426-b2-tg1-wave2.md` (it was already modified before this work), `src/`, and the frozen files.
