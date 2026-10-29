# B2 test-writer delivery 3a — baseline to S′ (P520), 2026-10-29

Moving the baseline to S′ took one constant change and one registry-audit fix. All support checks now pass (54), and the other 379 failures are slices not yet built on this baseline.

## 1. Base identity (rebase-amendment P520 (S′))

| Constant | Before (S) | After (S′, `61d31bcd`) |
|---|---|---|
| `b2_frozen_support.BASE_GITLINKS["src/mlx-vlm"]` | `c9543fc4bcd3111b738ba7a29ca772c2c6366817` | `1c7c8fa166582ac1a1c23ae9063527b2b5215b11` |
| `b2_frozen_support.BASE_GITLINKS["src/mlx-serve"]` | `86921f029d7e55b4d8b5882f2c05ed5e2ce31ef0` | `1ddf6f842f159a62d240f3ac6965fc33cbdb0b0d` |

The new values are what `git ls-files -s src/mlx-vlm src/mlx-serve` reports on this base, which is how the test reads them.

**Tests touched:** `test_b2_frozen_s0_support.py::test_the_frozen_runner_and_serving_pin_identities_of_the_base_commit` (it now passes). Everything else that uses `BASE_GITLINKS` reads the constant, so it follows automatically: the world's `worktree_state`, the receipt fixture's editable gitlink, and the s8 gitlink test.

**Base-derived constants checked and left unchanged** (the base change doesn't move them):
- `FROZEN_RUNNERS` (six runner sha256s): they still match this base; the s0 identity test checks them first.
- The legacy goldens `GOLDEN_P223_SCHEDULE_SHA`, `GOLDEN_M63_SCHEDULE_SHA`, `GOLDEN_CHAIN_ORDER_SHA`, `GOLDEN_PILOT_ORDER`, `GOLDEN_TG1_CONFIG_STATIC`: the s0 golden tests pass on this base. Their comment still says "recorded from 50ec18d1", which remains true.
- `PINS` (the fork's `dev/p369_phase2/pins.json`): read live from `src/mlx-vlm` at the S′ gitlink, never hard-coded. It holds the model's `{hf_path, revision, files}` entries; `pinned_snapshots` and the s0 check pass.
- `REAL_ROW` and `GOLDEN` (committed fixtures): not base identities.

## 2. Live-registry audit

| Hit | Finding | Fix |
|---|---|---|
| `b2_frozen_add_support.chain_ops` | Built a real `ChainOps(S.REPO, …)` without `registry=`, so `ChainOps.registry` defaulted to `<repo>/main_models.yaml`, the **live** registry (`chain_ops.py:239`). Used by add_record, add_support_check and the s7 lock tests. | `registry=ov`, the synthetic `registry_text` file, tagged rebase-amendment P520 (S′). New assertion in `test_b2_frozen_add_support_check.py::test_the_real_chain_ops_fixture_spawns_nothing`: `ops.registry == ops.overlay != REPO/main_models.yaml`. |

No other hits:
- Every other registry path in the set is synthetic: `<tmp>/WT/main_models.yaml` from `registry_text` (`make_ops`, `arm_receipt_doc`), or canonical `<WT>/main_models.yaml` strings in fake environments.
- The baseline runner never reads `main_models.yaml`; the legacy `FakeOps.ensure_overlay` only records the call. On the candidates, `served_registry` takes `ops.overlay`, which is synthetic in every fixture.
- The s9 scratch repo copies only the `bench` package.
- The fake probes use `FAKE_SERVED_REGISTRY`, always a synthetic file.

I didn't need `benchmark/bench/tests/fixtures/p426_off/main_models.yaml` anywhere.

**One thing I left as is:** `FakeOps.env_base()` copies `os.environ`. If your shell exports `MLX_SERVE_CONFIG`, that path lands in fake probe environments as a string. No test reads the registry through it. If you want it out anyway, `chain_env` can `delenv` it.

## 3. Whole set on this baseline
```
../bin/run_stack_tests.sh bench/tests/test_b2_frozen_s0_support.py bench/tests/test_b2_frozen_add_support_check.py
54 passed in 18.79s
../bin/run_stack_tests.sh <s1–s9, all add_ files, test_b2_frozen_fix_cases.py> --tb=no -rfp
379 failed, 10 passed in 8.66s
```
The 10 passes are the same `[INV]` tests as before. The 379 failures are the same count as the last baseline run (372) plus the 7 cases added in 2e. None of them comes from the base change: the only lines mentioning `mtp` are argparse usage text from the baseline refusing `--p426` (in `add_pair:111`).

| Slice / file | Failed | Expected cause on the baseline |
|---|---|---|
| s1 | 51 | no `--p426` or `--models` (s1) |
| s2 | 9 | no `--evidence p426` or `p426` arm mode (s2) |
| s3 | 7 | no `invalidate` or `slot_file` (s3) |
| s4 | 67 | no `p426_reconcile` / `p426_hooks` (s4) |
| s5 | 56 | no `p426_receipt` / `p426_secrets` (s5) |
| s6 | 3 | no P426 watch mode (s6) |
| s7 | 35 | no P426 chain checks or locks (s7) |
| s8 | 21 | no `p426_wave2` / `p426_freeze` (s8) |
| s9 | 25 | no `wave2` harvest or `publish_*` (s9) |
| add_sequencer 26, add_pair 16, add_argv 9, add_census 3, add_ledger 3, add_a4 7, add_record 4, add_scrub 3 | 71 | s3–s9 seams absent |
| fix_cases | 34 | the s1–s6 fixes absent; the P38 legacy invariant needs s1's `--models` |

Nothing was committed or pushed.
