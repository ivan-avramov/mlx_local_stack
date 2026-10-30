All 12 items are fixed, test-first, with new tests in `test_b2_fix3.py`. Both check batches exit with code 0 and no failures. I did not run the frozen tests, and I expect some of them to fail against the new behaviour (below). Nothing is committed or pushed.

## Per item

Each item had a red-first test; the line is the failure I saw, then the change.

1. **`p426_dnf` `load` / `attempt`**. Red: `assert (1 == 2)` on a `.a2` out-root.
   - Moved `load=load["idx"]` out of the comment.
   - `attempt` is now parsed from `<leg>.a<n>` in the out-root name, with a fallback to the per-stem counter for bare test chains with no such name.
   - I did **not** change the invocation records' `attempt`. It names their immutable rows files and restores the counters on resume, so changing it would collide rows file names.
2. **Dossier on resume**. Red: rc `0 == 1` after tampering with an existing dossier.
   - `ensure_dossier` now always recomputes problems, differences and verdict from the current receipts and harvest files.
   - An existing dossier is verified through a new `verify_dossier`: self-hash, pair, attempts, receipt and harvest hashes, differences, verdict.
   - The first mismatch stops with rc 1 and names the field. The stored verdict is never used.
3. **Credential keys**. Red: `is_credential_key("KV_API_KEY")` was False.
   - The `KV_` / `TQ_` prefix exemption is replaced by `STACK_DEFINED_KV_TQ_NAMES`: `KV_BITS`, `KV_GROUP_SIZE`, `KV_KEY_BITS`, `KV_VALUE_BITS`, `KV_KEY_SCHEME`, `KV_VALUE_SCHEME`, `KV_QUANT_SCHEME`, `KV_PREALLOC_TOKENS`, `TQ_KV_QUANT_MODE`, `TQ_PREFILL_IMPL`, `TQ_FUSED_PREFILL`, `TQ_DECODE_2PASS_LEGACY`.
   - These come from the `src/mlx-vlm` server files and `kvmanifest.py`. `TQ_KEY_BITS` is not among them, so it is now a credential, and I removed it from one old test's allowlist.
4. **Engagement on DNF and degenerate ON items**. Red: no `engagement` check in a `.dnf.json`, and `engagement_problems(..., item=True)` did not exist.
   - `dnf_problems` runs engagement on the DNF's completed requests and persists it.
   - `engagement_problems(item=True)` flags `unengaged` for an ON item with no request of at least 2 generated tokens.
   - `leg_items_problems` re-validates DNF item records (sealed, reconciled, engagement) and flags an unengaged ON leg.
   - DNF items have no per-item floor; only the leg-level one applies to them.
5. **In-flight cases**. Red: a DNF boundary abort with a trailing failed line was accepted.
   - Added an `inflight_evidence` check: `*_inflight_failed` now needs the structured marker, so a boundary abort with a trailing failed line is systemic.
   - Kill reconciliation uses `termination.in_flight_at_kill >= 1`, not `True`.
   - For a DNF the marker is `in_flight.in_flight is True` or a message id.
   - I updated two older s4 tests that passed `termination="killed"` as a string.
6. **Pilot gate in the amendment**. Red: `write_amendment` accepted a speed-invalid pilot.
   - `write_amendment` now runs the whole gate (`pilot_gate_problems`) plus a check that the pilot pair dossier is a sealed PASS naming these attempts and receipts.
   - The amendment records `pilot_dossier_sha256`.
   - The sequencer's `ensure_amendment` re-verifies an existing amendment (self-hash, kind, `v8_base_sha256`, selected PASS dossier, recorded sha256). A failure stops with rc 1.
   - The record loader at sequencer start already refuses some tampered amendments with rc 2, so tests accept 1 or 2 for those cases.
7. **Rehearsal binding**. Red: `KeyError: 'frozen_record'`, and v8 accepted legs from another manifest.
   - `chain.json` now records `frozen_record {path, sha256}` and `inject` in P426 mode.
   - `binding_problems` in `rehearsal_problems` checks, for R1-off, R1-on, R2 and R3, the manifest path and sha256, the expected leg name, and the expected `--inject` (R2 `reconcile-mismatch`, R3 `stall-kill`, R1 none).
   - The manifest's commits are not compared with the v8 arms; a test confirms this.
8. **Harvest self-hash**. Red: `DID NOT RAISE` for every record missing its `sha256`.
   - The leg record, receipt, `items/*` and `p426_dnf` sidecars must carry a present `sha256` equal to their self-hash.
   - The `chain.json` `p426_dnf` entries must equal their sidecars.
   - I updated the s9 fixture to seal `leg.json` and the DNF sidecar.
9. **Run-file publication**. Red: rc `0 == 4`.
   - Publication now runs inside `run()` before `DONE` or the `--through` line; a failure is `Stop(4)`.
   - It is published once, and the exit path does not retry.
10. **Run directories**. Red: `DID NOT RAISE`.
    - A manifest run id resolving to no run and no evidence directory, or to more than one of either, fails the harvest.
11. **`ready_sha256`**. Red: the item record held the file hash.
    - It now stores the ready record's self-hash, and the harvest compares one value.
    - I removed `ready_file_sha256` and updated three older assertions.
12. **Secrets parsing**. Red: the shell-style, bearer and lossy-decode tests all failed.
    - `parse_assignments` uses `shlex.split(comments=True)` and takes the first token. An unparseable credential-keyed line raises `SecretsError` naming the key, never the value.
    - The `bearer` pattern also matches the JSON and quoted header forms.
    - A non-UTF-8 evidence file is scrubbed and scanned through surrogateescape. Its HARVEST entry gets `lossy_decode: "surrogateescape"`.
    - The post-scrub marker check now looks at the scrubbed bytes, so a lossy file containing a workdir path is scrubbed, not refused.

## Conflicts with frozen tests

These are my reading of the frozen tests; I did not run them.
- **Item 11.** `test_b2_frozen_s4_reconcile.py:529` and `test_b2_frozen_fix_cases.py:210` assert `ready_sha256` equals the ready file's sha256. Item 11 says the opposite, so those two will fail.
- **Item 6.** Any frozen `amend` fixture without a pilot pair dossier under `<out-base>/pairs/` will now be refused.
- **Item 7.** Frozen rehearsal-leg fixtures without a `frozen_record` / `inject` block in `chain.json` will be refused by v8.
- **Item 10.** A frozen manifest whose run id resolves to no directory now fails the harvest.

## Files changed in this round

Source:
- `benchmark/bench/chain_core.py`: DNF `load` / `attempt`, `frozen_record` / `inject` in `chain.json`.
- `benchmark/bench/p426_freeze.py`: pilot gate, dossier check, `pilot_dossier_sha256`, rehearsal binding, DNF re-validation and the unengaged leg.
- `benchmark/bench/p426_harvest.py`: the self-hash rule, DNF entry equals sidecar, run-dir resolution, lossy decode, `ready_sha256` compare.
- `benchmark/bench/p426_hooks.py`: DNF engagement, item-level `unengaged`, `ready_sha256` as the self-hash.
- `benchmark/bench/p426_reconcile.py`: in-flight evidence, `engagement_problems(item=)`.
- `benchmark/bench/p426_secrets.py`: allowlist, shell-style parsing, bearer pattern.
- `benchmark/bench/p426_wave2.py`: dossier verification, amendment verification, run-file stop, `planned_slots` and `pilot_gate` delegate to `p426_freeze`.

Tests:
- `benchmark/bench/tests/test_b2_fix3.py` (new): all item tests.
- `benchmark/bench/tests/b2_s8_support.py`: leg fixture takes `frozen_record` and `inject`.
- `benchmark/bench/tests/test_b2_s4_reconcile.py`: in-flight evidence, `ready_sha256`.
- `benchmark/bench/tests/test_b2_s5_receipt.py`: allowlist name.
- `benchmark/bench/tests/test_b2_s8_freeze.py`: pilot dossier helper, bound rehearsal legs.
- `benchmark/bench/tests/test_b2_s9_harvest.py`: sealed `leg.json` and sidecar.
- `benchmark/bench/tests/test_b2_fix_chain.py`: `ready_sha256` assertion.

`docs/specs/p426-b2-tg1-wave2.md` was already modified before this round and I did not touch it.

## Runs

The wrapper prints only dots, so I report exit codes.
- **Batch A:** `test_b2_fix3.py`, `test_b2_fix2.py`, all `test_b2_s*.py`, `test_b2_fix_chain.py`, `test_b2_fix_goldens.py`, `test_c147_chain_runner.py`, `test_p311_chain.py`, `test_p364_chain.py`, `test_local_gate.py`, `test_p426_wave1.py`, `test_p426_harvest.py`, `test_t3_wave1.py` with `-q --tb=short -p no:cacheprovider`. Exit code 0.
- **Batch B:** `test_p371_*.py`, `test_work_queue.py`, `test_status.py`, `test_m63_predictor.py`, `test_p279_smoke.py`, `test_c151_start_time.py`, `test_tune_provenance.py`, `test_samples_resume.py`, `test_p426_watcher.py`, `test_p426_session_ids.py`, `test_p426_leg.py`, `test_p426_bench_watch.py`, `test_p311_closure.py`, `test_p276_real_manifest.py`, `test_m64_chain_ops.py`, `test_m64_chain.py`, `test_m64_arm_closure.py`, `test_generate_run.py`, `test_evidence_backfill.py`, `test_conftest_fakes.py`, `test_chain_ops.py`, `test_bootstrap_lock.py`, `test_bench_watch.py`, `test_agentbench_watch.py`, same flags. Exit code 0.
- **Not run:** the full suite and the frozen tests. The legacy goldens in the b2 and p371 files above passed unmoved.
- `benchmark/control/` is absent after the runs.
