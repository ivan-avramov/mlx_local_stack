Both frozen-test defects are amended; the amended tests' results are reported on the baseline only, as you asked. For s5 I recommend **fix then merge**. Its biggest problem is the self-reported silent skip: it switched off every s5 check in 13 of the 14 chain-level frozen tests that reach it. The snapshot re-hash, by contrast, is what the spec asks for.

## Part 1 (delivery 1h): the two class-(c) defects

| Defect | Change | Tests touched |
|---|---|---|
| s1: unresolvable `--campaign-core` and no fake campaign | `b2_frozen_support.main_refusal(argv, ops, *, campaign=None)` passes `campaign=` to `run_tg1_chain.main` only when given. s1's `refusal()` passes `S.fake_campaign(CAMPAIGN)`, the same fake `run_p426` already uses. | Every s1 test that goes through `refusal()`: `…retired_flag…` (4), `…c147_overlay…`, `…missing_required_flag` (7), `…out_root_that_exists`, `…leg_dot_a_n` (4), `…more_than_one_model`, `…rehearsal_injections…` (2), `…wrong_kind…` (5), `…bad_self_hash…`, `…missing_record_file…`, `…amendment…sibling…`, `test_fix_models_is_required…` (2), `…duplicates_and_empty_names` (4), `…not_an_entry_of_the_served_registry…` |
| s4: hook fixture without `log_bounds.json` | New `open_log_bounds(env)` in the s4 file, called by `hooks()`. It writes `<out>/log_bounds.json` the way the chain does before the router: §16.1 two-phase shape, `offset_end` and `finalized` null, both log files. | Every test using `hooks()` / `_ready_then_done`: `ready_hook…accepts`, `…without_a_context…` [before, after], `done_hook_reconciles…`, `done_hook_invalidates_a_server_count…`, `…on_item_without_drafter_counters`, `done_hook_accepts_an_engaged_on_item`, `unreadable_metrics…`, `missing_ready_record_at_done…` |

**Your decision (s4 fixture paths):** my fixture writes `log_bounds.json` paths in the portable form `<WT>/logs/…`, following [d2] §11.2 and my own s7 test. The s4 candidate matches the path exactly as an absolute string (`p426_hooks.log_bounds_problems`). Once re-installed, the s4 hook tests will therefore still fail, now on a (b) [d2] point instead of a missing file. If you rule that `log_bounds.json` is not a record for `main`, the fixture should write absolute paths.

**Baseline:**
```
../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s0_support.py bench/tests/test_b2_frozen_add_support_check.py
52 passed in 16.43s
../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s1_cli.py bench/tests/test_b2_frozen_s4_reconcile.py
118 failed in 2.37s
```
None of the 118 failures comes from the amendments:
- s1: 39 fail at the refusal assertion (`s1_cli.py:55`); the baseline lacks `--p426`. Another 12 end in argparse `SystemExit: 2`.
- s4: 67 are `ImportError`, because `p426_reconcile` and `p426_hooks` are absent.
- No `TypeError` from the `campaign=` keyword, no `FileExistsError`.

Not run on the candidates, as briefed.

## Part 2: run on the s5 candidate (`eval-s5`, holding `frozen4`)

```
../bin/run_candidate_s5_tests.sh bench/tests/test_b2_frozen_s5_receipt.py bench/tests/test_b2_frozen_add_pair.py bench/tests/test_b2_frozen_add_record.py bench/tests/test_b2_frozen_add_argv.py --tb=no -rfp
28 failed, 41 passed in 5.89s
../bin/run_candidate_s5_tests.sh bench/tests/test_b2_frozen_add_census.py
2 failed, 1 passed in 2.24s
../bin/run_candidate_s5_tests.sh bench/tests/test_b2_s5_receipt.py bench/tests/test_b2_s4_reconcile.py bench/tests/test_b2_s1_cli.py bench/tests/test_c147_chain_runner.py
393 passed in 90.12s
```
The third run is the candidate's own tests plus the legacy chain tests: no regression there.

### Classification

**s5 unit file (16 failed)**

| Tests | Class | Evidence |
|---|---|---|
| `…pair_differing_only_in_the_allowed_items_passes` | **(c) mine** | `snapshots.drafter: the ON worker's --draft-model is not the drafter snapshot that was hashed`. My `arm_receipt_doc` (`b2_frozen_support.py:897–898`) has snapshots `{revision, files}` with no `hf_path`. The real `pins.json` shape is `{hf_path, revision, files}`, and so is the candidate's `snapshot_hashes` (diff 337). |
| `volatile_keys_never_count…` ×7, `…problem_names_the_differing_process_and_field`, `…credential_key_missing_from_one_process…` | **(c) mine** | `receipt.second: the receipt's sha256 does not verify`. My tests change a self-hashed receipt without re-sealing it, and the candidate verifies seals first (diff 559–567), which receipts as immutable records support. |
| `pair_dossier_is_self_hashed…`, `pair_dossier_is_immutable` | (b) | `write_dossier() got an unexpected keyword argument 'off'`: the §16.7 signature isn't built. |
| `…canonicalizes_the_roots…`, `volatile_keys_are_recorded_as_keys_only`, `credential_keys_are_recorded_per_process…`, `…one_build_pass_the_pair_gate` | **(c) mine** | `ReceiptError: the worker did not load mlx.metallib`. My world's `loaded_images` (`b2_frozen_support.py:1018`) lists only `libmlx.dylib`; §6.4 names both libraries. |
| **False passes:** `test_fix_any_other_difference_between_the_arms_refuses` ×8, `…interpreter_inventory_difference…`, `…env_difference_outside_the_closed_list…` | **(c) mine** | Same un-re-sealed mutation: they pass on the seal problem, not the difference under test. |

**`add_` files**

| Tests | Class | Evidence |
|---|---|---|
| add_pair: `second_leg…passes`, `credential_key_in_one_process…`, `same_credential_keys_with_other_values…`, `environment_difference…`, `loaded_library_difference…` (5) | **(a) high** | The first leg finishes rc 0 with **no `receipt.json`**, so the second is refused at entry: `REFUSED: --pair-receipt receipt.json is missing`, or rc 2 before any `load`. Cause: P29. |
| add_pair `rehearsal_leg…` | (a), inherited s1 | `unrecognized arguments: --rehearsal` |
| add_argv `on_worker…` ×3 | (a), inherited R5 | `REFUSED: --predictor mtp … lacks ['draft_kind', 'draft_model', 'mtp_verify_scan']`, with the served registry carrying the keys. |
| add_argv `off_worker_with_an_extra_flag`, `off_worker_with_drafter_flags`, `snapshot_that_differs_from_the_worktrees_pins…` | **(a)**, P29 | rc 0 where 2 is expected: the worker argv and entry snapshot checks never ran. |
| add_census `foreign_model_worker…`, `foreign_benchmark_driver…` | **(a)**, P29 | rc 0 where 2 is expected. |
| add_census `owned_router_worker…exempt` (passes) | vacuous | The census never ran. |
| add_record ×4 (pass) | — | `interpreter_inventory`'s RECORD verification works against the real RECORD format. |

On top of the two amended in part 1, I found **three more class-(c) defects of mine** in `frozen4`. I haven't fixed them, since this brief didn't ask:
1. `arm_receipt_doc`'s snapshot shape.
2. Re-sealing after a mutation in s5 (`_mutate` and the in-place edits).
3. `mlx.metallib` missing from the world's `loaded_images`.

Item 2 also produces 10 false passes.

## Review of the s5 diff

| Id | File:line (diff) | Severity | Finding and failure scenario |
|---|---|---|---|
| P29 | `chain_core.py` 9–27, 43, 75, 114 | **High** | **The self-reported silent skip: I judge it should not stay.** If `ops` lacks any name in `P426_RECEIPT_SEAMS`, the entry snapshot check, the after-load census, the worker argv check, the receipt, the pair gate and the before-invocation checks are all skipped, with one log line, and the leg can end VALID. Two of the required names are not spec seams: `router_identity` and `identity_alive`. §16.6 line 587 names `create_time(pid)`, and the §16.2 list (511–514) has neither. So the frozen world, which implements the named seams, skips every check: 13 of the 14 chain-level failures above. In P426 mode a missing seam must refuse, or be systemic (`ChainAbort`), and the census must use the named `create_time`. |
| P30 | `chain_core.py` 111–119 | — | **The self-reported snapshot re-hash: I judge it correct.** §3 line 101 requires, before every invocation, "the entry checks except router absence, the idle gap and power", and the entry checks include hashing the snapshots against the pins. Cost: at least 3 full hashes per leg (entry, receipt, each invocation), about 16 GB each for this target, which also displaces page cache while the model is resident. This is operational, not a defect; I recommend logging the hash time per checkpoint in the pilot. |
| P31 | `chain_core.py` 111–119 | Medium | **Before-invocation checks are incomplete against §3.** The re-verification of the record kind and self-hash, worktree HEAD and cleanliness, the registry sha and the probe identity are absent. The router check is `router_ok()` (the config sha), not the owned `(pid, start)`: R4 is still open. A restarted router or a changed worktree between invocations goes undetected. |
| P32 | `chain_core.py` 88–91; `p426_receipt.py` 455–474 | Medium / (d) | **The receipt records a stand-in probe.** At after load, no probe exists; the receipt records `{argv: [py, probe], env: ops.env_base()}`. The real probe's environment (the per-invocation additions) is never receipted, so a probe-environment difference between arms passes. The spec asks for the probe "resolved from their pids", but there is no probe pid before item one. I recommend you rule on this. |
| P33 | `p426_receipt.py` 491–500 | Low | `worker_argv_problems` accepts up to two extra leading tokens (shebang tolerance), where §6.3 says "the complete argv equals". An argv with an injected `-X …` prefix passes. | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| P34 | `p426_receipt.py` 563, 627–666 | Low (b) | `pair_problems` still takes `allowed` / `volatile` keywords (§16.7: module constants). `write_dossier` keeps the old `attempts`/`receipts`/`harvests` signature with integer attempts. `differences` are strings, not `{process, field, off, on}`. `receipt_sha256` is the self-hash field. | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| P35 | `run_tg1_chain.py` 1831–1842, 1869–1870 | — | Sound: `--pair-receipt` is checked at entry (exists, parses, self-hash verifies) before anything is written. The `add_pair` missing-receipt test passes on this. |

Sound as built:
- Credential keys are dropped from `env` and recorded per process.
- `pair_problems` messages never carry values.
- The closed volatile list with the `__CF*` prefix.
- The OFF/ON argv rule: OFF's tokens in order plus exactly the three pairs, with their values.
- Snapshots compared against the pins, with the drafter ON only and matching `--draft-model`.
- RECORD re-verification, editables at the gitlink and clean, `vmmap`-based loaded images.
- `p426_secrets`: the classifier, `usable`, the sources, `scan`, `exact_hits`. No value enters a finding.
- The receipt is exclusive-created; the log line shows key counts only.

## Verdict for s5: fix then merge
1. **P29:** remove the silent skip. In P426 mode a missing seam is a refusal or systemic. Use the spec's `create_time(pid)` instead of `identity_alive` / `router_identity`.
2. **P31:** complete the before-invocation checks per §3, including the router `(pid, start)` (R4).
3. **P34:** the §16.7 `pair_problems` / `write_dossier` forms and the `differences` entry format.
4. Your ruling on P32 (the probe environment in the receipt).
5. Inherited items still open: R5 (served registry), `--rehearsal` / `--inject` in s1.

**On my side:** the three new class-(c) defects should be fixed before s5 is judged against `frozen4` again: the drafter snapshot `hf_path`, re-sealing in s5 (removes 10 false passes), and `mlx.metallib` in the world's `loaded_images`.
