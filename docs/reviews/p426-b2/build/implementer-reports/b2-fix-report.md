Every adopted finding is addressed except the three I left open below. Frozen s1–s5 went from 63 failed to 1 failed. That one failure, plus 3 more among the frozen `add_` files, I did not satisfy; I judge them unsupported or out of scope.

## Frozen s1–s5 before and after

Same five files, no `-q`:

```
before: 63 failed, 130 passed in 45.88s
after:   1 failed, 192 passed in 48.61s
```

- **Remaining s1–s5 failure:** `test_b2_frozen_s5_receipt.py::test_new_a_receipt_whose_seal_does_not_verify_is_a_problem` (see "Frozen tests I judge unsupported").
- **Frozen `add_` files:** I did not record a baseline summary for these. After: `3 failed, 47 passed in 16.36s` over `add_{argv,census,ledger,pair,record,a4,support_check}`.
- **Slice and fix tests:** `350 passed in 51.08s` over `test_b2_s1…s5`, `test_b2_fix_chain.py` and `test_b2_fix_goldens.py`.
- **Regression sweep:** every existing test file that imports a changed module passes. That covers `test_c147_chain_runner`, `m63`, `p279`, `p364`, `p311`, `p290`, `p276`, `chain_ops`, `c151`, `m64_*`, `p371_*`, the older `p426_*`, `local_gate`, `evidence_backfill` and `bootstrap_lock`. I did not run the full suite.

## Findings

Test-first: where a frozen test was red, that is the failing-first evidence. My own tests in `test_b2_fix_chain.py` and `test_b2_fix_goldens.py` were written alongside the fixes, so I did not observe them red separately.

**s1–s3 review**
- **R2 fixed.** `--frozen-record` is read at entry (`run_tg1_chain.check_frozen_record` via the new `p426_record.py`). It refuses a wrong kind, a bad self-hash, a missing file, and an amendment whose `v8_base_sha256` isn't its sibling's self-hash. Tests: frozen s1 `test_new_a_record_*`.
- **R3 fixed.** The DNF limit now counts the whole leg. Test: `test_the_dnf_limit_counts_the_whole_leg_across_languages_and_arms`.
- **R4 / P20 / P31 router identity fixed.** The chain records `(pid, create_time(pid))` from `start_router()` and compares it after load, before each invocation, at incidents, at exit, and in the hooks at every barrier. Tests: `test_a_router_replaced_after_load…`, `…between_two_barriers…`, `test_the_router_identity_is_the_pid_and_start_time_not_liveness_or_a_config_sha`.
- **R5 fixed.** The runner serves `ops.overlay`; receipt and pins use the ops' worktree. Test: `test_the_served_registry_is_the_ops_overlay_under_injected_ops`.
- **R6 fixed, already conformant.** The sidecar already used `slot_file`; I added a test. Test: `test_a_dnf_records_its_item_record_as_the_path_string_and_its_sidecar_by_slot_file`.
- **R7 fixed.** The base-bundle test needs the old goldens untouched, so the refresh is recorded in `golden_refresh_c221.json` with old and new hashes. The new `load_refreshed_golden` checks both hashes, and the in-test filter is gone. Tests: `test_b2_fix_goldens.py`.
- **§16 refusal format, `--rehearsal`, `--inject` fixed.** Every refusal, argparse's included, prints one `REFUSED:` line and exits 2. `--rehearsal` and `--inject` are parsed, and `--inject` needs `--rehearsal`; behaviour comes in s8. Entry-check failures also print `REFUSED:`. I did not verify the `REFUSED:` line on the other `run()` paths, which I did not change.
- **`generic_pred_s` recorded.** It is now the ChainConfig params key, renamed from `pred_default_s`, so the config hash changed; the s1 slice-test hash is updated. I first put it in `chain.json`, but that broke the legacy differential.
- **`p426_invalid` fixed.** It is now a list of records.

**s4 review**
- **P16 fixed.** Kills are read from the structured fields. A normal row's `termination` dict contains the key names `killed` and `in_flight_at_kill`, so the old string search flagged every row as a kill.
- **P17 fixed.** Test: `test_the_dnf_reconciliation_reads_the_abort_manifest_the_real_probe_writes`, run in-process through the real probe for both `drop` and `refuse`.
- **P18 fixed.** The settle bound comes from the amendment, else the v8 base, else 900 s. Test: `test_the_settle_bound_comes_from_the_frozen_record_amendment_else_v8_base`.
- **P19 fixed.** `a4_window_problems(lines, a4_receipt, a4_gate)` now runs in the chain after each A4 gate, before the first item. It reads `<STACK_WORKDIR>/c102a/gate.json`, which is the gate script's default workdir and which the chain doesn't pass. Test: `test_an_a4_window_that_differs_from_gate_json_stops_the_leg_before_item_one`.
- **P21 fixed.** The item record is written on every `done` outcome, including an invalidate. Tests: `test_an_invalidated_done_still_writes_its_item_record_before_the_answer`, `test_a_done_without_its_ready_record…`.
- **P22 / P23 fixed.** `ready_sha256` is the ready file's sha256; `item_record` is the path string.
- **P24 fixed.** `log_bounds.json` uses portable `<WT>/logs/…` paths and is finalized even when teardown raises. Test: `test_log_bounds_are_portable_and_finalized_even_when_the_teardown_raises`.
- **P25 / P26 / P27 fixed.** `P426Hooks` without a context raises `HookInfrastructureError`, log field values stay strings, and the `pairing` detail names a position only on failure.

**s5 review**
- **P29 fixed.** A missing seam in P426 mode is systemic with a `REFUSED` line naming it; there is no silent skip. The required seams are the ten the spec names (`create_time` in place of the two non-spec ones, plus `worktree_state`). `ChainOps.router_identity` and `identity_alive` are removed. I added a real `ChainOps.worktree_state()`.
- **P31 fixed.** Before every invocation the chain checks record kind and self-hash, worktree HEAD and cleanliness, registry sha, probe identity, and owned identities. Tests: the five parametrized `test_the_before_invocation_checks_stop_the_leg_before_item_one`.
- **P32 mostly already satisfied.** The probe launch environment is already `ops.env_base()` and the per-invocation keys travel in argv. I added a unit test showing the receipt reads the launch spec, not a process.
- **P33 fixed.** The worker argv must equal the expected argv exactly. Test: `test_the_worker_argv_must_equal_the_expected_argv_exactly`.
- **P34 fixed.** `pair_problems(first, second)`, `write_dossier(path, *, pair, off, on, differences, verdict)`, `{process, field, off, on}` difference entries, file-sha256 fields, and `<leg>.a<n>` attempt names. Test: `test_pair_problems_and_write_dossier_have_the_spec_16_7_signatures`.

## Frozen tests I judge unsupported or out of scope

1. **`test_b2_frozen_s5_receipt.py::test_new_a_receipt_whose_seal_does_not_verify_is_a_problem`** (§16 immutable records).
   - It "tampers" with `on["env"]["worker"]["PWD"] = "<volatile>"`, but the fixture's `PWD` is already `<volatile>`.
   - The edit changes nothing, so the seal still verifies and a correct `pair_problems` returns `[]`. The test cannot pass against the spec.
2. **`test_b2_frozen_add_pair.py::test_new_the_second_leg_of_a_pair_passes_the_gate_and_runs`** and **`…test_new_the_same_credential_keys_with_other_values_pass_the_gate`** (§16.7 tail, the P32 ruling).
   - They expect the probe environment to come from the shared `proc_environ` fake.
   - The ruling makes it the chain's probe launch environment (`ops.env_base()`). In the fake that environment carries the arm-specific `B2_DRAFT` and `FAKE_REGISTRY_SHA`, so the gate correctly reports a difference.
3. **`test_b2_frozen_add_ledger.py::test_new_a_dnf_is_ledgered_in_its_place_and_the_rest_in_the_next_invocation`** is red on a separate defect, which I did not fix.
   - `validate_partial` in the flat layout also runs `arm_row_problems`, which requires per-arm `arm` and `epoch_id` fields on rows and manifest. Flat tg1 rows from this fake probe carry none, so the DNF is refused as "rows do not validate".
   - It is not among the adopted findings. Per AGENTS.md it needs its own proposal. The likely fix is gating `arm_row_problems` on `per_arm`, but a real flat row may carry those fields, so I did not guess.

## Files changed

- **Source:** `benchmark/bench/{chain_core,chain_ops,p426_hooks,p426_receipt,p426_reconcile}.py`, `benchmark/chains/c147/run_tg1_chain.py`.
- **New source:** `benchmark/bench/p426_record.py`.
- **Edited tests:**
  - slice tests `test_b2_s1…s5` — I deleted superseded or obsolete tests: the P426 end-to-end tests (moved to `test_b2_fix_chain.py` on the frozen hermetic world), the s5 chain-wiring and old-dossier tests, and the identity-seam tests;
  - `test_c147_chain_runner.py` — served-registry stub;
  - `test_c151_start_time.py` — two allowlist entries for the `create_time` reads;
  - `test_p371_baseline.py` and `p371_baseline/runner.py` — the recorded refresh.
- **New test files:** `test_b2_fix_chain.py`, `test_b2_fix_goldens.py`, `p371_baseline/golden_refresh_c221.json`.

**Decisions for you**
- **Frozen s5 seal test:** is the no-op fixture edit a test bug to fix, or should the test be dropped?
- **Frozen `add_pair` probe-environment tests:** should the ruling or the tests change?
- **Flat-layout DNF defect:** do you want a proposal for the `validate_partial` fix?
