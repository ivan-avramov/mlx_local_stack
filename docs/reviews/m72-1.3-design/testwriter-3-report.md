# Test-writer report, delivery 3 — amended frozen tests

Only the six items of the brief were changed (plus the helper parameters they need). The two tests the designer kept frozen are untouched.
Candidate patches were reversed (`git apply -R` ×3), the amended tests run on baseline + frozen tests, the patches re-applied; `git status`
and `git diff --stat` of all three copies were identical before the reversal and after the re-application (4+7+2 tracked files, same
insert/delete counts, same untracked set). A re-run after re-application gave the same candidate results as before.

## Amended tests

1. **A7 (`test_tq4_m72_mode.py`).** `test_a7_q_norm_bound`: violations now γ = 2048 and 4096 (exactly representable in bf16; the test also
   asserts the planted value survived storage); passes at 1000 and 1024 (inclusive bound). `test_a7_codebook_bound`: rows are now
   `None` (today's 0.17 values), `1.0` (inclusive limit) → pass, and an ABSOLUTE entry `1.5` planted in entry 0 → refuse, for the key and the
   value codec (6 rows instead of 4). "Passes on today's values" rows kept (`test_a7_check_fp16_range_passes_and_records_values`).
   Baseline: error (module absent). Candidate: all pass.
2. **A4(c) seeded (`test_tq4_m72_generation.py`).** The six seeded rows of `test_a4c_exact_mode_mtp_on_equals_mtp_off` are replaced by
   `test_a4c_exact_mode_seeded_mtp_on_equals_mode_absent_mtp_on` (block 3/5/7 × accepting/rejecting = 6 rows): both runs decode n = 256 seeded
   tokens from the same snapshot (a MODE-OFF prefill of the first T − 1 = 2099 prompt tokens, the mode applied only afterwards, through
   `generate_step` with that prefilled cache and the last prompt token), same scripted proposals; `m72_exact` ON must equal mode-absent
   (policies stamped) TQ4 MTP ON; also asserts `mma` = 0 and `d2_verify` > 0 (`per_query:k_gt_5` for k = 7). The greedy rows (MTP ON = MTP OFF, 6 rows)
   are kept as they were. Baseline: fail (module absent). Candidate: 6 of 6 pass — so `m72_exact` seeded MTP ON equals mode-absent seeded MTP ON on the synthetic model at n = 256.
3. **p2s prefill-logit rows (`test_tq4_m72_routing.py::test_prefill_chunk_takes_p2s[m72_v1|m72_exact]`).** The 5 % tolerance is replaced by
   the 2× rule on the chunk's last-token logits: d_on = max rel diff (mode-on TQ4 vs mode-off TQ4) ≤ 2 × d_floor (mode-off TQ4 vs the same
   weights with native16 caches, same prompt, same 2100 + 512 tokens). Recorded on the candidate (printed by the test): **d_on = 0.01156, d_floor = 0.04971, bound 2×d_floor = 0.09942** (identical for both modes: prefill is mode-independent). Baseline: fail (module absent; the routing assertion comes first). Candidate: pass.
4. **`/health` (`test_tq4_m72_routing.py`).** `test_health_details_carry_the_route_counters` now drives `GET /health` through the app with
   `runtime.response_generator` monkeypatched to a stub carrying a mode object (name + `counters()` = `route_counts()`), no model loaded; it
   finds a dict holding the counters (by value) and the mode name in the body. New `test_health_details_are_absent_with_the_mode_off`: a stub
   with the mode `None` → no counter dict, no `m72` / `tq4` text in the body. The stub's attribute name (`tq4_attention`) is the candidate's own, as the brief allows.
   Baseline: both fail (module absent). Candidate: both pass.
5. **Load-order tests (`test_tq4_m72_mode.py`).** The loader fixture now runs the real `ap.apply_to_model` and `mv.apply_to_model` (so `fused_v1` and
   `joint_v1` are stamped on the native layer); a `no_stamp=` option leaves one of them a recording no-op. Order, abort and acceptance assertions are unchanged
   (`test_load_order` ×2, `test_a_failing_mode_stage_aborts_the_load` ×3, `test_mtp_verify_accepts_quantized_kv_when_the_mode_resolved` ×2 = the seven).
   New `test_load_refuses_when_a_policy_stamp_is_missing[no-fused_v1-stamp|no-joint_v1-stamp]`: refused, none of check / apply / self-test runs.
   Baseline: error (module absent). Candidate: the seven and both new rows pass; the candidate's message names the missing stamp.
6. **Docs (`test_m72_13_harness.py`).** `test_docs_record_the_mode[...]` is replaced by `test_serving_path_documents_the_registry_key_and_values`
   (`tq4_attention`, `m72_v1`, `m72_exact` in `docs/serving-path.md`) and `test_box_notes_has_an_m72_1_3_entry` (`"M72 1.3"` in `docs/box-notes.md`).
   Baseline: both fail. Candidate: both pass.

Also changed for these: `routing.build(..., kv=)` (a native-cache option, default unchanged), a `max_rel` helper, imports in the generation file.

## Frozen tests on the candidate

- fork (6 files, 368 tests): `4 failed, 364 passed, 2 warnings in 29.05s`. On the baseline (frozen + amended): `106 failed, 19 passed, 243 errors`.
  The 4 failures are exactly the two tests the designer kept frozen: `test_tq4_m72_kernels.py::test_kernels_refuse_a_batch_cache`;
  `test_tq4_m72_mode.py::test_require_environment_accepts_the_legacy_flag_spelled_off[0]`, `[false]`, `[no]`.
  Everything else passes (per-file split derived from the earlier per-file totals plus the added rows, summing to 364): support 5, kernels 166,
  mode 84, routing 77, memory 7, generation 25.
- mlx-serve `tests/test_tq4_m72_config.py`: `57 passed` (baseline: 52 failed, 5 passed).
- stack `test_m72_13_provenance.py` + `test_m72_13_harness.py`: `35 passed` (baseline: 6 failed in the harness file alone, plus the provenance failures as in delivery 1).
- Nothing skipped. The full-suite results of delivery 2 were not re-run (only test files changed; the candidate source is unchanged).

## Notes
- The seeded rows depend on `generate_step` accepting a pre-filled `prompt_cache` plus the last prompt token; that works on this code (mode-absent control and the candidate both ran). If the designer's fix changes the mode's behaviour after a mode-off prefill, these six rows are the ones that will notice.
- The two kept-frozen tests will pass only after the candidate asserts batch-1 `TurboQuantKVCache` preconditions in the kernels and refuses `TQ_DECODE_2PASS_LEGACY` only when production's own parse treats it as on (1 / true / yes).
