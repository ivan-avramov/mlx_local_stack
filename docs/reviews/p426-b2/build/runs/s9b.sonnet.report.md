All three rulings are in and their new tests pass, but one existing s4 test is now red and I left it that way (see the end). Nothing was committed or pushed.

## Files changed

- `benchmark/bench/chain_core.py`: new pure functions `portable_doc` and `expand_doc`. In P426 mode the chain now writes its records in portable form:
  - `chain.json`, the per-invocation `<stem>.json` and the DNF sidecar are written with `<OUT>`, `<WT>`, `$STACK_WORKDIR` and `$HOME` in place of absolute paths.
  - On resume, a P426 `chain.json` is expanded back to this box's paths.
  - **Legacy chain.json: I left it unchanged.** The spec's portable rule is P426-only and the legacy goldens must stay byte-identical; every non-P426 write path is unchanged.
- `benchmark/bench/p426_hooks.py`: the ready record's `log_cursor.path` is now `<WT>/logs/<name>` (via `portable_log`). The worktree path in it failed the scrub-identity rule. It goes beyond the ruling's wording ("chain.json"), so please confirm. The only reader of the cursor uses device, inode and offset, never the path.
- `benchmark/bench/p426_wave2.py`: `BoxSeqOps.launch` writes the launch stdout to `<out-base>/logs/<attempt>.stdout`.
- `benchmark/bench/p426_harvest.py`:
  - The launch log is inventoried as `record:logs/<attempt>.stdout` and routed to `evidence`; it is optional, and a symlink there is refused.
  - Foreign emails go to `$STACK_WORKDIR/p426/review/<attempt>.emails.json`, written only after a successful stage and never published. `HARVEST.json` carries `review.emails_count` and `review.emails_file`.
  - The real harness exposed three rule-table gaps, now fixed:
    - `.ACK` / `.CANCEL` match case-insensitively (the chain writes them uppercase);
    - evidence files may sit in per-item subdirectories, with plain `.jsonl` and `.xml` accepted;
    - `ready_sha256` may be either the ready file's sha256 (what the hooks write) or its self-hash.
- `benchmark/bench/tests/test_b2_s9_harvest.py`: +7 tests, one existing assertion rewritten, one test narrowed.
  - The review-email assertions were rewritten for the new J8 shape.
  - The "leg root never modified" snapshot now covers only the files the harvest reads, since its one write under the workdir is the review file.

## Red first

- `test_a_real_p426_leg_harvests_without_a_scrub_refusal` (U1): `HarvestError: leg:chain.json: the scrub would change this main record (not portable at creation)`. It first failed on unmatched layouts, which I fixed in the harvest. The ready-record failure was seen before the `p426_hooks` fix.
- `test_chain_core_portable_doc_round_trips_and_leaves_other_strings_alone`: `AttributeError: module 'bench.chain_core' has no attribute 'portable_doc'`.
- U2 tests:
  - `…write_each_launch_stdout_to_out_base_logs_attempt_stdout`: `FileNotFoundError` for the `logs/` path;
  - `…inventories_the_launch_log…`: `ValueError: not enough values to unpack (expected 1, got 0)`;
  - `…launch_log_is_optional_never_a_symlink…`: `Failed: DID NOT RAISE HarvestError`.
- J8: the rewritten `…operator_email_and_its_domain…` test and `…empty_review_file_and_a_zero_count` failed with `KeyError: 'emails_count'`.
- `test_a_refused_harvest_writes_no_review_file` passed on first run, so it is a guard rather than a red-first test.

## Test fixture artifacts

The real-leg test has two fixture-only steps:
- It clears host environment variables that contain the real home path before the leg runs.
- It re-canonicalizes `receipt.json` and re-seals it. The harness's fake environment has a placeholder `HOME` and its fake probe lives in this checkout, so host paths stay absolute there. Production's receipt canonicalizes `$HOME` from the real `HOME`, so I expect none of this in a real run.

The in-process harness also records pytest's `argv` in `chain.json`, so I assert on the launched probe command (`attempts[0].argv`) instead.

## Commands and summary lines

- `../bin/run_stack_tests.sh bench/tests/test_b2_s9_harvest.py` → `106 passed in 23.50s`
- First wide batch (the 13 files you named) → `3 failed, 828 passed in 303.39s (0:05:03)`. The 3 were DNF tests in s3 and `b2_fix_chain` whose stub chains lack `wd`/`repo`. I made `p426_roots` tolerate that, and the `-k dnf`, `real_p426` and `portable` subset then gave `25 passed, 156 deselected in 4.38s`.
- Final batch: your 13 files plus every non-frozen test importing a changed module. That adds the s2/s4/s5/s6/s7/s8-freeze tests, `test_evidence_backfill`, `test_c151_start_time`, `test_p311_closure`, `test_m64_chain` and the `test_p371_*` files. Result: `FAILED bench/tests/test_b2_s4_reconcile.py::test_ready_record_is_written_before_go_with_the_spec_fields_and_self_hash` / `1 failed, 1544 passed in 827.23s (0:13:47)`. I did not run the full suite or any frozen file.

## One red test left for you

`test_b2_s4_reconcile.py:372` asserts `rec["log_cursor"]["path"] == str(ops.log)`, the old absolute form. The portable `<WT>/logs/<name>` form is what lets a real leg's ready records pass the scrub-identity rule. I did not edit it because you restricted me to my own test files. If you confirm, the fix is that single assertion: `== ph.portable_log(ops.log)`. If you would rather keep the s4 assertion, the ready record would have to stay absolute and would fail the harvest's scrub check on a real leg.
