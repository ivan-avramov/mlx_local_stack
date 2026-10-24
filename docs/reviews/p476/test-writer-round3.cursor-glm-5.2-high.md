All checks complete. Here is my report.

## Second delivery review — candidate4 (round-3 fix)

### Step 1 — apply
- `git -C mlx_local_stack apply ../candidate4.stack.diff` → clean, rc 0
- `git -C mlx-vlm apply ../candidate4.fork.diff` → clean, rc 0
- `rsync -a --delete --exclude .git mlx-vlm/ mlx_local_stack/src/mlx-vlm/` → done

### Step 2 — frozen tests (same named tests ran)

Stack `bench/tests/test_p476_frozen.py` — 18 collected, 18 ran:
- `TestRegistryNames` (3): `test_models_entry_names_are_exactly_the_five`, `test_no_pruned_entry_remains_in_models`, `test_task_model_is_not_a_models_entry`
- `TestRemainingEntriesMatchBaseline` (2): `test_every_remaining_entry_parsed_settings_equal_baseline`, `test_every_top_level_key_equals_baseline`
- `TestRegistryDiffIsDeletionsOnly` (2): `test_diff_against_baseline_is_deletions_only`, `test_no_orphan_comment_block_is_dropped`
- `TestConfiggenCheck` (1): `test_configgen_check_rc_zero`
- `TestCarrierIds` (2): `test_every_carrier_id_is_in_registry_or_task_model`, `test_no_carrier_names_a_pruned_entry`
- `TestOwuiMenu` (1): `test_owui_menu_equals_openwebui_models`
- `TestUntouchedPath` (6): benchmark_results / model_params / configgen_code / scripts / readme / docs
- `TestModelParamsRetained` (1): `test_model_params_still_has_the_six_entries`

Fork `mlx_vlm/tests/test_p476_frozen.py` — 9 collected, 9 ran:
- `TestQualifyEntries` (3), `TestLoadReferencesReal` (2), `TestGoldenFixture` (2), `TestOptInLiveClassification` (1), `TestProductionCodeUnchanged` (1)

### Step 3 — results verbatim

| Run | Summary line (verbatim) | Failing ids |
|---|---|---|
| Stack frozen | `18 passed in 17.61s` | none |
| Fork frozen | `9 passed, 2 warnings in 2.35s` | none |
| `run_configgen.sh check` | (no output) rc 0 | none |
| `run_configgen.sh test` | `89 passed in 2.16s` | none |
| Fork three-file (`test_p415_qualify.py test_mtp_verify_scan.py test_p426_qualify_predictor.py`) | `280 passed, 1 skipped, 2 warnings in 6.37s` | none; the 1 skip is `test_mtp_verify_scan.py:1818` opt-in live-registry check (`MLX_REQUIRE_STACK_REGISTRY=1`), expected |
| `fork_live_check.sh` | `268 passed, 2 warnings in 6.10s` | none |
| Full stack suite `run_stack_tests.sh` | `7317 passed, 6 skipped, 1 xfailed, 5 warnings in 2112.86s (0:35:12)` | none |

`grep -cE "^(FAILED|ERROR)" /tmp/stack_suite.log` → 0. Fork production diff `git -C mlx-vlm diff --stat HEAD -- mlx_vlm ':(exclude)mlx_vlm/tests'` → empty (AC5 holds).

### Step 4 — review against spec v3.1

**Round-3 fixes — all three resolved:**

1. **P371 tests mutate a throwaway clone, never a tracked file, with a guard on tracked carriers' bytes** — resolved.
   - `benchmark/bench/tests/p371_baseline/bundle.py:36-44,89-103` — `OVERLAY_SOURCES`/`OVERLAY_SHA256` overlay committed pinned carriers (sha asserted) onto the archived tree; manifest records `overlaid_files`.
   - `test_p371_baseline.py:76-92` `test_a_mutated_live_carrier_is_not_absorbed_into_the_bundle` — `git clone --shared --no-checkout` to `tmp_path/clone`, mutates carriers there, `make_bundle(root=clone)`; asserts pins not absorbed.
   - `test_p371_baseline.py:585-607` `test_a_later_carrier_change_fails_the_item_differential_on_purpose` — `_tree_copy` to `tmp_path/tree`, `monkeypatch.setattr(new_side, "REPO", copy)`, mutates the carrier in the copy only.
   - `test_p371_baseline.py:641-645` `test_the_tracked_carriers_are_unchanged_after_the_p371_tests_run` — guard: `TRACKED_CARRIERS` sha at import == sha at module end.
   - `new_side.py:193` driver path now `REPO / "benchmark/bench/tests/p371_baseline/new_side_driver.py"` so it follows the monkeypatched `REPO`.

2. **`m59_policy.json` / answer-key README record the carrier's real source** — resolved.
   - `fixtures/m59_policy.json:2-5` — `identity_code_commit: 22288fc`, `carrier_source_commit`, `carrier_source_file: benchmark/opencode_bench_v2.json`; `baseline_commit` removed; pin recomputed.
   - `fixtures/answer_key/README.md:16-19` — documents the carrier source distinct from the identity-code commit.
   - `test_m61_web_audit.py:43-51` `test_m59_fixture_carrier_pin_equals_the_live_carrier_and_records_its_source` — asserts the pin equals the live carrier bytes and that `identity_code_commit != carrier_source_commit`.

3. **`configgen/source.py` refuses a `retired_model_ids` name that is a live model** — resolved.
   - `configgen/source.py:99-104` — `live = {models names} | {task_model name}`; raises `ValueError` on clash. Router-only entries (in `models:`) and the task model are covered.
   - `configgen/tests/test_source.py:155-170` — `test_retired_ids_naming_only_pruned_models_are_accepted` and parametrized `test_retired_id_that_is_a_live_model_is_refused` over `Qwen-A` / `Task-T` / `Router-Only`.

**Spec compliance of the rest:**
- S1 `main_models.yaml`: six blocks deleted, `openwebui.retired_model_ids` (the six, in registry order) added; orphan `RETIRED 2026-08-26 (C33 …)` comment retained. Frozen `TestRegistryDiffIsDeletionsOnly` confirms additions are solely that list.
- S2/S2b: `configgen/emitters/owui.py:87-90` folds retired ids into `excluded_model_ids` after surviving non-menu ids, dedup; `openwebui-init/model_settings.json` reordered to `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` + six retired (registry order), matching AC2 v3.1. Reconcile tests `test_unmanaged_saved_registration_of_a_retired_id_is_flagged_stale` and `test_shipped_policy_flags_every_retired_id_when_saved_unmanaged` confirm dry-run lists + `--apply` refuses.
- S3: `test_deployed_profile.py` retargets gemma to `fixtures/gemma_31b_qat_registry.yaml` (verbatim baseline block, asserted by `test_gemma_fixture_is_the_verbatim_baseline_block`); new `test_registry_published_set.py` implements S3 (a)/(b) + OWUI menu.
- S3b: P371 goldens move only carrier-derived fields (`carrier_source_sha256`/`opencode_bench_config_sha256`/`carrier_sha256`/`probe_code_sha256`/`scaffold_policy_sha256`); old→new recorded in `bundle.py:26-34` and `test_m61_web_audit.py:21-25`; `test_c147_inject.py` `OLD_CAMPAIGN_HASH` refreshed with old→new comment.
- S4 fork: `qualify.ENTRIES` → three MTP; docstrings "three"; `p415_reference_peaks.json` four rows removed; fixture regenerated with prune + `retired_model_ids`; `test_p415_qualify.py`/`test_p426_qualify_predictor.py` use synthetic served entry via `_with_served`; new `test_p476_the_real_reference_table_loads_against_the_real_entries`.
- AC3 untouched paths verified by frozen `TestUntouchedPath` and `git diff --name-only` (only spec + configgen source/emitter/tests + carriers + tests/fixtures).

**Findings (observations, not blockers):**
- `benchmark/bench/tests/test_m61_web_audit.py:26` — `fixture =json.loads(...)` missing space after `=`. Cosmetic, valid Python.
- `benchmark/bench/tests/p371_baseline/new_side.py:325` — `run_chain_new_side` still resolves the driver via `Path(__file__).resolve().parent` (does not follow `REPO`), unlike `run_item_new_side:193`. Inconsistent but harmless: chain scenarios do not read the carrier and are not monkeypatched by the new hermeticity tests.
- Placeholder `P476-STACK-COMMIT` in `fixtures/m59_policy.json:3` (`carrier_source_commit`), `mlx_vlm/tests/test_mtp_verify_scan.py:1735` (`FIXTURE_SOURCE`), and the fixture header comment. These are intentional markers for the not-yet-created stack commit (spec S5 sequences the bump after the stack commit is published); the frozen tests pin content sha256, not these labels, so they pass. They must be substituted with the real SHA when the stack commit is made — a commit-time hygiene step, not a code fix.

**Deviations:** None material. All changes map to S1/S2/S2b/S3/S3b/S4; no scope creep into `benchmark/results/`, `model_params.py`, `scripts/`, `README.md`, or non-allowed `configgen/` code. No secrets, no env-var logging, no path traversal; `_tree_copy`/`git clone --shared` operate under `tmp_path`; overlay pins are sha-asserted.

### Verdict: **merge**

All three round-3 fixes are resolved; every frozen test (27), configgen (89), the fork suites (280 + 268), the live check, and the full stack suite (7317 passed, 0 failed) pass; fork production diff is empty; the OWUI tombstone ordering and the P371 hermeticity guard behave per spec v3.1. The `P476-STACK-COMMIT` labels are the intended pre-commit state (substituted when the stack commit is finalized, per S5), not a defect requiring a fix before merge.
