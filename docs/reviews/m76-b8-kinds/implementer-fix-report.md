# Implementer report — M76 B8 kv fix round 1 (spec v1.1, F1–F5), 2026-11-16

## Fix round 2 (R1, 2026-11-17)

- **Change** (`benchmark/bench/p426_verify.py`): the new `KV_STAMPED_KINDS = ("reasoning", "longctx")`. `_kv_result_reasons` now requires both `result_file` and `result_sha256` on every manifest of those kinds, per arm and per A5 item. An absent stamp gives "rule 2d: `<arm>` `<leg>` [`<item>`] manifest has no `<stamp>`". The skip "when neither arm has a stamp" is removed. Math500, cjudge, vision and m1 stay unchecked, as before.
- **Tests** (`test_m76_b8_kinds_impl_fixround1.py`):
  - `test_r1_both_arms_stripped_of_their_stamps_are_rejected[reasoning, longctx]`: both arms' b2 stamps are stripped; the pair must be rejected with reasons naming each arm and each stamp, while b1 stays accepted.
  - `test_r1_unstamped_kinds_stay_unstamped`: a guard.
  - Red: 2 failed (`assert not True`: the stripped pairs were accepted), 1 passed (the guard). Output: `red_r1.txt`.
  - Green: the fix files give 38 passed / 0 failed (`green_r1.txt`; 24 + 14).
- **Fixture** (my `test_m76_b8_kinds_impl_planned.py`): `RealWorld.leg` now stamps reasoning and longctx manifests the way their runners do (new `RealWorld.stamp`; the old body moved to `_leg`).
- **Regression set** (`after_all_r2.txt`): 2,236 tests, 2,212 passed, 23 failed, 0 errors, 1 skipped. That is 12 as before (K1 plus the 11 F3 tests) plus **11 new failures in read-only files, all one cause**: the shared `World.leg` (`test_m76_b3_impl_verify.py:111`) writes A5 manifests without stamps, so every A5 pair it builds is now rejected.
  - `test_m76_b3_impl_verify.py`, 4 tests: `test_a_clean_kv_world_is_accepted`, `test_the_resolved_budget_of_the_196608_rung_is_the_prompts_own`, `test_a5_tier2_legs_are_verified_as_their_own_pairs`, `test_compute_kv_a5_two_looks_end_to_end`.
  - `test_m76_b3_impl_signals.py::test_compute_kv_on_the_verified_world`.
  - `test_m76_b3_impl_panel.py`, 6 tests: `export_freezes…`, `judge_seal_ingest…`, `a_complete_panel_has_no_incomplete_flag`, `a_missing_member_blocks…`, `unsealed_or_missing_verdict_slots_block`, `partial_ingestion_is_explicit_and_labelled`. These fail downstream of the rejected A5 pairs: A5 is pending, there is no A5 panel member or provenance, and the `looks` / `mode` keys are absent.
  - Recommended test-writer fix: in `World.leg`'s longctx branch, stamp each manifest with `result_file` = the result's name and `result_sha256` = sha256 of its bytes, as `RealWorld.stamp` does.

## Continuation (designer rulings: D1–D4 accepted; erratum v1.1a). Supersedes the Status / F3 / F4 / regression parts below.

- **F4, adapted.** `verify_all_kv(rows_root, repo, pair, kinds=None, build="s3")` keeps `kinds`; `None` means the planned kinds. A subset still records the build's `dropped` (from `kv_w1_dropped(build)`; a bad build refuses).
  - My F4 tests were replaced by 4 tests: the default is the planned kinds plus `dropped`; the CLI calls `verify_wave1_kv` with `kinds=None` (spy) and emits 10 planned pairs plus `dropped.m1`; a `kinds=("cjudge",)` record carries `dropped` and `compute_kv` flags the 8 absent planned pairs as blocking `wave1_incomplete`; `kinds=()` gives 10 flags.
  - **I did not run these 4 adapted tests red on candidate 1.** The two subset tests depend on F2's flag, whose own tests were red on candidate 1. The default and CLI tests are behaviour candidate 1 already had.
- **F3 data.** `../.venv-bench/bin/python -m bench.m76_ids` was run from `benchmark/` (`m76_ids_regen.txt`). The tokenizer printed its usual "incorrect regex pattern" warning, the same one as in the baseline's real-tokenizer test.
  - ids.json sha256: old `6c9455a25fcb375fc7e50ec9878ff676c3c3d110e2630ca487fbcce9156af85f`, new `57fce7c371ce46901cc1d22ff7b492c02db1dc36f9afca01a628129184fd6574`.
  - chars per token: 4.551045510455104 → 4.610591900311526.
  - `counter.template_kwargs` = `{"enable_thinking": true, "reasoning_effort": "medium"}`.
  - Diff check (`ids_diff.py` / `ids_diff.txt`): 432 differing leaves. They split into `budget` 284, `budget_inputs.prompt_tokens` 122, `budget_inputs.counter` 2 and `prompt_deviation` 24. **None fall outside the allowed regions.** A5 items, smoke items, blocks, tier1 and sampler seeds are equal to the old file, as are the Math500, cjudge, vision and reasoning axes.
  - `m76_ids.load` returns OK, and its band check holds.
  - Per rung (min/max): reasoning-131072 129130 → **130776** (the served value from K8); reasoning-159744 157344 → 159360; reasoning-196608 193619 → 196108; retrieval-131072 129131/129139 → 130776/130784; retrieval-159744 157342/157352 → 159357/159367; retrieval-196608 193619/193626 → 196108/196115; smoke reasoning 129130 → 130776; smoke retrieval 129137 → 130782.
  - Budgets: at 131072 and 159744, max_tokens stays 102400 and thinking stays 81920. At 196608, max_tokens goes 68525 → 66036 and thinking 54820 → 52828 (reasoning); retrieval goes 68518/68525 → 66029/66036 and 54814/54820 → 52823/52828.
  - Per-item deltas are 1,645 to 2,489 tokens.
  - `benchmark/results/m76/IDS_CHANGES.md` is written with these numbers.
- **Fix files.** `fixround1` plus `_impl_planned`: 35 passed / 0 failed (`green_fixround1_v2.txt`; 21 + 14).
- **Regression set** (same named files; `after_all_v2.txt`): 2,233 tests, 2,220 passed, 12 failed, 0 errors, 1 skipped. Against the baseline (2,212 tests: 2,210 passed / 1 failed / 1 skipped):
  - +21 new tests, all passing.
  - The 18 F4 errors/fails are gone.
  - What remains is K1 (as on the baseline) plus the 11 F3 tests left to the test-writer: 8 in `test_m76_b3_impl_counter.py` and 2 in `test_m76_b3_fe_fix_v15.py` (stand-ins without `**kwargs`), plus `test_the_real_tokenizer_count_equals_an_independent_input_ids_length` (510 vs 552).
  - No other outcome changed. The mtp golden passes.
- **Files changed this pass:** `benchmark/bench/p426_verify.py` (the `verify_all_kv` signature and `dropped`), `benchmark/bench/tests/test_m76_b8_kinds_impl_fixround1.py` (the F4 tests), `benchmark/results/m76/ids.json` (regenerated), `benchmark/results/m76/IDS_CHANGES.md` (new).

Copy: `fe-m76b8k/impl/stack` (baseline `3c199587` + candidate 1). Nothing committed. All test output: `../scratch/*.txt`.

## Status

- F1, F2, F4 and F5 are fixed, each red then green.
- F3's code is fixed, red then green on a fake tokenizer.
- F3's data step was **not done**. Every Python command outside `../fe_test.sh` was refused by the session's approval gate ("This command requires approval"), so I could not run the generator: `../.venv-bench/bin/python -m bench.m76_ids` from `benchmark/` (also tried with the absolute interpreter path). I did not work around the gate.
  - `benchmark/results/m76/ids.json` is unchanged (sha256 `6c9455a25fcb375fc7e50ec9878ff676c3c3d110e2630ca487fbcce9156af85f`).
  - `IDS_CHANGES.md` is **not written**: I have no new values, and a file holding only the old half would mislead.
  - So "the regenerated ids.json passes `m76_ids.load`" and "its diff confined" are not satisfied.
  - `test_f3_the_committed_ids_records_the_served_template_and_loads` stays red until the designer runs the generator.

## Per fix

All fix tests are in `benchmark/bench/tests/test_m76_b8_kinds_impl_fixround1.py`, on the real committed ids.json through `RealWorld`. Red run: `red_fixround1_v2.txt`, 15 failed / 4 passed. Green run: `green_fixround1_v1.txt`, the new file plus `_impl_planned`: 32 passed / 1 failed (the ids.json test).

The 4 tests green on candidate 1 are guards that already held there: a content hash compared across arms, a foreign `result_file`, a stamp absent on one arm, and subsets through `verify_wave1_kv`.

| Fix | Change | Tests (red → green) |
|---|---|---|
| F1.1 | `p426_verify.kv_provenance_problems`: each arm's string leaves normalised with its own `_kv_path_re(arm)` (`m76-f45-ARM` / `m76-q-ARM`) before the cross-arm diff. A leaf naming another arm's worktree gives "`<arm>` manifest names another arm's worktree" (a rule 2d reason via `_kv_manifest_reasons`; A7 shares the function). Helpers `_kv_strings`, `_kv_own_paths`. | `arm_local_corpus_path_is_accepted` and `arm_local_q_worktree…` red (runtime.corpus differs), then green. `a_corpus_path_naming_the_other_arm_is_rejected` red (was accepted), then green. `content_hash_beside_the_path_stays_compared` green both times. |
| F1.2 | `KV_PROVENANCE_EXCLUDED` += `result_file`, `result_sha256`. New `_kv_result_reasons(reader, kind, a, b)`, called in `verify_wave1_kv`: per arm (A5: per item), `result_file` must equal the basename of the result file B8 read and `result_sha256` must equal `reader.inputs[rel]` (the sha256 of the bytes read). Absent or unequal gives a rule 2d reason naming arm and leg. `load_kv_leg` / `_kv_longctx` now record the per-item `result_rels`. | `per_arm_result_file_and_sha_are_accepted` red (result_file differs), then green. `one_arms_altered_result_bytes_reject_naming_that_arm[reasoning, longctx]` red, then green. `result_file_naming_another_file` and `stamp_absent_on_one_arm` green both times (the old cross-arm diff also caught them). |
| F2 | `p426_signals.compute_kv`: dropped kinds (`wave1.dropped`) report `{"status": "not_run", "ruling": …}` for M1 and A2–A4. New `coverage.dropped` and `coverage.incomplete`. New `_kv_build_of` (build from the recorded `frozen.path`, else refuse) and `_kv_incomplete`: each planned pair (`kv_w1_kinds(build)` × b1, b2) rejected or absent becomes one entry. `kv_flags` emits one blocking `wave1_incomplete` per entry (`member` = `kind/label`; `text` = first 3 reasons, or "absent"). Tier-2 `not_run` is not flagged. | `complete_record…m1_is_not_run`, `rejected_planned_pair…`, `absent_planned_pair…` and `candidate_1_shape…` all red, then green. |
| F3 | `m76_ids.offline_counter`: passes `deployed_template_kwargs(entry)` to every `apply_chat_template` call, calibration included. The kwargs come from `params_for(entry, profile="deployed")`, `enable_thinking` and `reasoning_effort` only, each only when set. Meta gains `template_kwargs`. | `counter_passes_the_deployed_template_kwargs_to_every_call` and `unset_kwargs_are_omitted` red, then green. `committed_ids_records_the_served_template_and_loads` red, and still red (ids.json not regenerated). |
| F4 | `verify_all_kv(rows_root, repo, pair, build="s3")`: no `kinds`; it always calls `verify_wave1_kv(build=…)`. | `verify_all_kv_has_no_kinds` red, then green. `subsets_stay_on_verify_wave1_kv` green both times. |
| F5 | `KV_W1_KINDS` is defined in `p426_plan`. `p426_verify` imports it (`V.KV_W1_KINDS is P.KV_W1_KINDS`), and `kv_w1_kinds` no longer imports `p426_verify`. | `one_definition_of_the_kinds` red, then green. |

## Files changed (vs candidate 1)

- `benchmark/bench/p426_plan.py`: `KV_W1_KINDS` defined here (F5).
- `benchmark/bench/p426_verify.py`: F1.1, F1.2, F4, and the F5 import.
- `benchmark/bench/p426_signals.py`: F2, plus `import re`.
- `benchmark/bench/m76_ids.py`: F3 (`deployed_template_kwargs`, `TEMPLATE_KWARGS`).
- `benchmark/bench/tests/test_m76_b8_kinds_impl_fixround1.py`: new, 19 tests.
- `p426_wave1.py`, `docs/specs/…` and `test_m76_b8_kinds_impl_planned.py` are unchanged from candidate 1.

## ids.json

- Old: sha256 `6c9455a2…af85f`, `counter.chars_per_token` 4.551045510455104, transformers 5.15.0.
- New: not produced (blocked, see Status). The per-rung old/new counts are not produced either.

## Regression set: every test file importing `p426_plan`, `p426_verify`, `p426_wave1`, `p426_signals` or `m76_ids`

These are 35 files plus the directories `p613*` and `p586_frozen`. The command is in `baseline_before.txt` / `after_all.txt`.

- **Before** (candidate 1, recorded before my first code edit): 2,212 tests, 2,210 passed, 1 failed, 1 skipped. The failure is `test_m76_b3_impl_wave1::test_main_kv_refuses_v_before_anything_runs` (K1).
- **After:** 2,231 tests (+19 new), 2,199 passed, 15 failed, 16 errors, 1 skipped.

Outcome changes, all in read-only files:

1. **F4, intended by the spec: 18 tests** that call `verify_all_kv(…, kinds=("cjudge","longctx"))` now raise `TypeError`.
   - `test_m76_b3_impl_panel.py`: 16 ERRORs. The fixture calls it at line 128.
   - `test_m76_b3_impl_verify.py::test_compute_kv_a5_two_looks_end_to_end` and `test_m76_b3_impl_signals.py::test_compute_kv_on_the_verified_world`: 2 FAILs.
   - The test-writer needs to move these to `verify_wave1_kv(kinds=…)` wrapped into a B8 record, or onto a full planned world.
2. **F3, intended: 11 FAILs.** The tokenizer stand-ins take no `**kwargs`, so they raise `TypeError: … unexpected keyword argument 'enable_thinking'`.
   - `test_m76_b3_impl_counter.py`, 8 tests: `counts_input_ids_not_keys[batch, list, batched]`, `refuses_insane_calibration`, `records_transformers_version`, `main_refuses_on_calibration_error`, `e2e_stand_in_batch_encoding_within_band`, `e2e_stand_in_without_template_overhead…`.
   - `test_m76_b3_fe_fix_v15.py`, 2 tests: `counts_a_batchencoding_like_result_by_its_ids`, `refuses_the_two_keys_defect…`.
3. **F3, intended: 1 FAIL, on the real tokenizer.** `test_m76_b3_fe_fix_v15.py::test_the_real_tokenizer_count_equals_an_independent_input_ids_length` gives `510 == 552`. Its reference renders the template without kwargs, and the counter now renders the deployed ones. Real-cache fact: for that 50-sentence message, the deployed kwargs render **42 fewer** tokens than none.
4. **Unchanged:** the K1 failure is still red (test-writer delivery 3). The mtp golden and every other file pass as recorded.

## Deviations and judgement calls

- **D1, F1.2 "absent".** The stamp check applies only when either arm's manifest for that item records `result_file` or `result_sha256`. When it does, each arm must have both, and they must match. Code fact: only `run_reasoning.py` and `run_retrieval.py` write the stamps (grep). Requiring them on Math500 / cjudge / vision manifests would reject every pair of those kinds on the real harvest, which candidate 1 accepted.
- **D2, F3 kwargs vs the server.** The server's `to_template_kwargs` (`src/mlx-vlm/mlx_vlm/server/generation.py:1140`) always sends `enable_thinking`. When set, it also sends `reasoning`, `reasoning_strength` (an alias of `reasoning_effort`), `thinking_budget`, and the thinking start/end tokens. I followed the spec (`enable_thinking`, `reasoning_effort` only). If this entry's template reads `thinking_budget` or `reasoning_strength`, the count could still differ; the designer's 72/72 pre-check is the evidence that it doesn't.
- **D3, the ids.json diff will not be confined** as F3 states. `m76_ids.longctx()` derives `axes.longctx.prompt_deviation` from `prompt_tokens`, so that block changes with any new count. `budget_inputs.counter.chars_per_token` and `template_kwargs` sit inside `counter`, which the spec allows. Expect `prompt_deviation` in the diff too.
- **D4, F2 build source.** `compute_kv` takes the build from the recorded `wave1.frozen.path` (`m76/wave1/run/frozen.<build>.json`), a recorded fact. The record carries no `build` field and I didn't add one. A record without a parsable frozen path refuses.
- **D5, fixture.** My `real` fixture re-patches `bench.generate.results_root` to return a `Path`; the base `World` returns `str`, and A1's regrade needs a `Path`. It also writes each Math500 `score.json` from its regrade, so the signals don't refuse on regrade drift. This is test-only.
- **Incident.** Before the baseline run had gone far, I briefly applied the F5 edits (about a minute) and then reverted them. Its in-process modules had already loaded at collection, and the diffstat afterwards was identical to candidate 1's. The baseline matches candidate 1's report, except `test_local_gate`, which passes now that `.venv-bench` is linked.

## Not satisfied

- ids.json regeneration, its `m76_ids.load` check and its diff, and `IDS_CHANGES.md`: all blocked by the approval gate on running Python. To finish, from `benchmark/`, run `../.venv-bench/bin/python -m bench.m76_ids`. Then `shasum -a 256 results/m76/ids.json`, diff it against HEAD, write `IDS_CHANGES.md`, and re-run `test_m76_b8_kinds_impl_fixround1.py`.
- Acceptance 2–4 (real-data CLIs) are the designer's.
