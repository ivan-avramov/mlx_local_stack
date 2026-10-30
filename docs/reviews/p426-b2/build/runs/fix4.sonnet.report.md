All five items are fixed test-first. Both check batches exit with code 0 and no failures on the final state. I did not run the frozen tests, and nothing is committed or pushed.

## Per item

Failure lines are from the first run of `test_b2_fix4.py`.

1. **Publication credentials.** Red: `TypeError: publish_run_files() got an unexpected keyword argument 'secrets'` (the first draft of the test), then `DID NOT RAISE` once the values travelled on the `Scrub`.
   - I kept the pinned `publish_dossier` / `publish_run_files` signatures. The exact credential values now ride on `Scrub` as a non-repr, non-compared `secrets` field.
   - `_publish_records` builds its gate from `scrub.secrets`, the same exact-match gate as the leg harvest.
   - New `p426_harvest.load_credentials` reads the same sources as the harvest CLI. An unreadable or unparseable source raises `HarvestError`, so a publication is never unscanned.
   - `BoxSeqOps` passes the values for both dossier and run-file publication. `main` also hands it the two worktrees' `.env` files as a source.
   - A configured secret value in `sequence.json` (for example in a `--rerun-reason`) is refused and nothing is published.
2. **Self-hash on run files.** Red: `DID NOT RAISE HarvestError`, for a missing hash and for a stale one, on `v8_base`, `amendment`, manifest and dossier names.
   - `publish_run_files` now requires a valid self-hash for every file except `sequence.json`.
   - I sealed the frozen-record fixtures in three older s9 tests (they published unsealed records).
3. **Amendment re-verified on `run` and `makeup`.** Red: `assert (0 in (1, 2))` for the `makeup` cases with another dossier hash and with none; the `run` case and the wrong-kind case already refused.
   - `Sequencer.run` calls a new `verify_existing_amendment` before any leg, for `run` and `makeup`.
   - It checks self-hash, kind, `v8_base_sha256`, and that `pilot_dossier_sha256` equals the selected pilots' PASS dossier.
   - A tampered pilot dossier is now caught by this check before the dossier check, still with rc 1. I relaxed one round-3 assertion to accept that wording.
4. **Dossier publication order.** Red: `OSError: disk full` escaping, and `KeyError: 'published'`.
   - A dossier is now published before its pair record is saved. A failure is exit 4 and leaves no pair record.
   - Pair records carry `published`.
   - On resume, `republish_dossiers` publishes any recorded dossier lacking the flag, idempotently, and a failure there is also exit 4. A published record is not published again.
   - A rehearsal publishes nothing, so its records get `published: false`.
5. **`$` and backtick.** Red: `DID NOT RAISE SecretsError` for five values.
   - New `_expands` refuses an unquoted `$` or backtick in a credential-keyed value, including inside double quotes.
   - It leaves single-quoted values and backslash-escaped ones literal. A non-credential key is never refused.
   - The error names the key and never the value.

## Files changed

- `benchmark/bench/p426_harvest.py`: `Scrub.secrets`, `load_credentials`, publication gate and self-hash rule.
- `benchmark/bench/p426_secrets.py`: `_expands` and the refusal.
- `benchmark/bench/p426_wave2.py`: box ops credentials, amendment re-verification, dossier publish order and resume.
- `benchmark/bench/tests/test_b2_fix4.py` (new): the item tests.
- `benchmark/bench/tests/test_b2_fix3.py`: one assertion accepts the amendment check's message.
- `benchmark/bench/tests/test_b2_s9_harvest.py`: sealed frozen-record fixtures.

`docs/specs/p426-b2-tg1-wave2.md` was already modified and I did not touch it.

## Runs

The wrapper prints only dots, so I report exit codes. Both ran with `-q --tb=short -p no:cacheprovider`.
- **Batch A:** `test_b2_fix4.py`, `test_b2_fix3.py`, `test_b2_fix2.py`, all `test_b2_s*.py`, `test_b2_fix_chain.py`, `test_b2_fix_goldens.py`, `test_c147_chain_runner.py`, `test_p311_chain.py`, `test_p364_chain.py`, `test_local_gate.py`, `test_p426_wave1.py`, `test_p426_harvest.py`, `test_t3_wave1.py`. Exit code 0.
- **Batch B:** `test_p371_*.py` plus the same importer list as round 3 (`test_work_queue.py` through `test_agentbench_watch.py`). Exit code 0.
- The earlier Batch A run exited 1 on three s9 tests: one pinned the old signature, two published unsealed records. Both are fixed above.

**Possible frozen-test conflict:** frozen s9 tests that publish unsealed frozen records will now be refused.
