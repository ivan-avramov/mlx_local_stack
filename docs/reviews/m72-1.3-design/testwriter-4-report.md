# Test-writer report, delivery 4 — candidate 2 (fixed)

Switch method: `git apply -R` candidate 1 (three repos), `git apply` candidate 2; later `-R` candidate 2 for the baseline run, candidate 2
re-applied last. The copies end on candidate 2 (`git status` lists: stack M provenance.py, 3 pinned tests, spike, 2 docs; fork 7 M + new
`tq4_attention.py`, `tq4_fast.py`, impl tests; serve 2 M). My frozen files were never touched by a patch. Only the new tests below were added
(to my own files); no existing frozen test was edited.

## Adopted findings and their reproducing tests

| # | test (my files) | candidate 1 | candidate 2 |
|---|---|---|---|
| 1 legacy flag only when production's parse enables it | frozen `test_tq4_m72_mode.py::test_require_environment_accepts_the_legacy_flag_spelled_off[0|false|no]` (`""` passed on both); the refusal rows for `1/true/TRUE/yes` stay green | FAIL ×3 (`Tq4AttentionError … is set`) | pass |
| 2 kernels assert `type(cache) is TurboQuantKVCache` | frozen `test_tq4_m72_kernels.py::test_kernels_refuse_a_batch_cache` | FAIL (DID NOT RAISE) | pass |
| 3 `kv_quant_mode` ≠ absent/`mse` refused | new fork `test_require_environment_refuses_a_non_mse_effective_key_codec[prod|PROD × 2 modes]` (worker, from `TQ_KV_QUANT_MODE`, `kv_quant_mode` not passed) + `test_require_environment_accepts_an_effective_mse_key_codec` (unset / mse / MSE); new serve `test_mode_refuses_a_non_mse_kv_quant_mode[prod|PROD|polar × 2]` + `test_mode_accepts_an_absent_or_mse_kv_quant_mode` | FAIL 4 (fork) + 6 (serve); accept rows pass | pass |
| 4 explicit non-mode `tq4_attention` refused | new serve `test_explicit_falsy_registry_value_is_not_absent[False|0|None|""|[]|{}]` (no companions, so the old "absent" reading cannot hide behind another rule) and `test_explicit_non_mode_registry_value_is_refused` (with companions; passed on candidate 1 only because the old fused_v1/kv_bits rule also mentions the key — the falsy test is the discriminating one) | FAIL 6 | pass |
| 5 counters at creation and at exit | new stack `test_counters_are_recorded_at_creation_and_at_exit` (gather under a mode with counters A; the exit check `assert_served_config_unchanged` with counters B; A found in the manifest and B in the exit block by content; fingerprint unchanged) | FAIL (no exit record) | pass |
| 6 four stack tests pinned to fingerprint 8 | inspection + run: `test_mtp_verify_scan_provenance.py`, `test_provenance_fingerprint.py`, `test_orphaned_manifest.py` all pass on candidate 2 (the patch edits only the pins/mocks: `_is_8`→`_is_9`, the controls table gains `tq4_attention: (9, "off")`, the `registry_tq4_attention`→`off` mock) | those 4 failed (delivery 2) | pass |
| 7 unregistered `slow` marks removed, instrument entry points documented | inspection: no `mark.slow` remains under `mlx_vlm/tests/` (grep: 0); `tq4_fast.py` docstring lists the four instrument knobs as test instruments; full fork run no longer lists the unknown-marker warning source | — | — |

## All my tests: outcomes

Tests now: fork 378 (6 files), mlx-serve 83 (`test_tq4_m72_config.py`), stack 36 (2 files). New in this delivery: fork +10 (finding 3), serve +26
(findings 3, 4: 8 + 2 + 6 + 6 + 4), stack +1 (finding 5).

| | baseline | candidate 1 | candidate 2 |
|---|---|---|---|
| fork | `106 failed, 19 passed, 253 errors` | `8 failed, 370 passed` | **`378 passed`** |
| mlx-serve | `78 failed, 5 passed` | `12 failed, 71 passed` | **`83 passed`** |
| stack | `27 failed, 9 passed` | `1 failed, 35 passed` | **`36 passed`** |

Candidate 1 failures, by id: fork — `test_kernels_refuse_a_batch_cache`; `test_require_environment_accepts_the_legacy_flag_spelled_off[0|false|no]`;
`test_require_environment_refuses_a_non_mse_effective_key_codec[prod-m72_v1|prod-m72_exact|PROD-m72_v1|PROD-m72_exact]`. serve — the 6 falsy-value rows and the
6 `test_mode_refuses_a_non_mse_kv_quant_mode[prod|PROD|…]` rows (the `polar` rows included, 12 in all after adding `[]`/`{}` to the falsy test);
stack — `test_counters_are_recorded_at_creation_and_at_exit`. No test is skipped. On candidate 2 every frozen test from deliveries 1–3 passes, including the
two kept frozen (legacy spellings, batch cache), the A4(c) seeded rows (equal to mode-absent MTP ON), the memory rows and the A3 goldens.

## Suites on candidate 2 (verbatim)

- `./fe_test.sh fork` (full): `10729 passed, 18 skipped, 22 xfailed, 11 warnings, 685 subtests passed in 511.81s (0:08:31)`, exit 0.
- `./fe_test.sh serve` (full): `1 failed, 347 passed, 1 warning in 1.31s`; the failure is the known `tests/test_config.py::test_golden_first_pick_command_is_what_main_builds_for_the_same_registry`.
- stack, the 9 files named in the brief (my 2, `test_mtp_verify_scan_provenance.py`, `test_provenance_fingerprint.py`, `test_orphaned_manifest.py`,
  `test_reasoning_persistence.py`, `test_reasoning_deep_design.py`, `test_m72_13_impl_e2e_spike.py`, `test_m72_13_impl_provenance.py`):
  `2 failed, 307 passed, 1 skipped in 32.63s` (my new finding-5 test included in the passes). Failures:
  `bench/tests/test_reasoning_persistence.py::test_cli_writes_partial_per_rung_and_resumes`,
  `bench/tests/test_reasoning_deep_design.py::test_cli_shallow_rows_resume_across_a_deep_redesign` (both: "C1 resume refused: the journal's manifest is not
  compatible with this run (sampling / KV / draft / serving controls / code differ)"). Skip: the implementer's spike test needs this copy's fork on the import path.

## Reasoning-resume experiment (the implementer's stated cause is REFUTED; the real cause found)

Scratch only (`../scratch/exp_pin_tq4.py`, `exp_stub_runtime.py`; nothing under `benchmark/` edited, run through `./fe_py.sh`).
1. Hypothesis from the fix report: `pin_mtp_scan` (`conftest.py:105`) does not pin `tq4_attention`. Experiment: a pytest plugin with an autouse fixture that
   wraps `registry_tq4_attention` and maps only the unresolved outcome to `off`, exactly the shape of `pin_mtp_scan`. Result: without the plugin 2 failed;
   with the plugin **2 failed** (same tests). Not the cause.
2. Trace: both tests call `stub_manifest_lite` (`bench/tests/test_run_reasoning.py:28-38`), which replaces `current_manifest_lite` with a hand-built manifest whose
   `runtime` has only `draft_kind, attention_policy, lazy_prompt_embeddings, mtp_verify_scan` ("v8 carries all 3") and `fingerprint_version = P.FINGERPRINT_VERSION`
   (9 now). The missing `tq4_attention` key reads `unknown` for a manifest at version ≥ 9, and `is_compatible` treats `unknown` as incompatible with everything,
   itself included (rule T2), so the journal written by the first CLI call cannot be resumed. Experiment: wrap `stub_manifest_lite` so the returned runtime also
   carries `tq4_attention: "off"`: without the wrap `2 failed`; with the wrap **`2 passed`**.
3. Conclusion: the cause is the runtime dict in `stub_manifest_lite`; the minimal fix is one key there (`"tq4_attention": "off"`), in `test_run_reasoning.py`
   (outside both the implementer's and my scope). Editing `pin_mtp_scan` would not fix these two tests.

## Review of the fix diff

Read: `tq4_attention.py` (`legacy_decode_enabled`, `effective_kv_quant_mode`, `key_codec_is_mse`, `require_environment`), `tq4_fast.py` (`_require_cache_class` at the head of
`_check_cache` and every entry point), the generation/loader hunk, mlx-serve `config.py` (`_registry_tq4_attention`, kv_quant_mode rule), stack `provenance.py` (exit snapshot).
- (1) `tq4_attention.py:102-104` parses `TQ_DECODE_2PASS_LEGACY` exactly as the cache constructor does (`"0"` default, lower-cased, `1/true/yes`); `""`, `0`, `false`, `no`, `off` accepted. Matches the finding; nothing broken.
- (2) `tq4_fast.py:122-136`: exact-class assertion, message names the class; batch and subclass caches refused by all 7 entry points; the served path is unaffected (`supports` gates first). Frozen kernel rows (167) and routing pass.
- (3) worker reads the codec mode through a probe `TurboQuantKVCache(bits=4)._kv_quant_mode` and asks `_build_codec` which codec results (`tq4_attention.py:107-124`); mlx-serve refuses a mode with `kv_quant_mode` other than ""/mse. Verified by my tests (refuse prod/PROD/polar; accept unset/mse/MSE). Minor: the probe constructs a throwaway cache per call (cheap, load-time only).
- (4) `config.py:59-71`: key present ⇒ the value must be the string `m72_v1` / `m72_exact`; `false/0/null/""/[]/{}/True/1/"off"/"M72_V1"` refused; key absent ⇒ absent. Behavioural change vs candidate 1: an explicit `tq4_attention: ""` is now refused (intended by the finding).
- (5) `provenance.py:1060-1075, 1548-1551, 1964-1975`: creation field renamed `tq4_route_counts_at_creation`; the exit block (`router_exit`) carries `tq4_route_counts_at_exit`, best-effort, only for a port a manifest of this process was gathered under a mode for; failures recorded, drift still refuses first. Findings: **minor** — `_TQ4_MANIFESTS` (`:1063`) is never cleared, so a later gather under another model or with the mode off on the same router port leaves the earlier entry and the exit snapshot is then taken for that stale (model, registry); **minor** — the exit snapshot exists only if the exit check runs in the process that called `gather` (the implementer's Q2); a driver that builds its manifest elsewhere gets none. Neither breaks the fingerprint (verified: counters outside it).
- (6) the four stack tests pass on candidate 2 except the two reasoning-resume tests above, which the fix report lists as outstanding and attributes to the wrong cause (see the experiment). **Major for the gate, not for the code**: with the version 9 bump, the repo's suite has 2 failing tests until `stub_manifest_lite` gets the key; they are copy-independent (they fail in the clean-clone gate too, since they read no `src/` file).
- (7) no `mark.slow` left; docstring lists the instrument knobs. Nothing renamed.
- Anything broken by the fix: nothing found in the fork (full suite green), mlx-serve (known failure only) or the stack files named; the only red are the two reasoning-resume tests.
- `./fe_test.sh fmt` was reported not clean by the implementer (mlx-serve `ruff format --check` on `tests/test_tq4_impl_config.py` and on my `tests/test_tq4_m72_config.py`; fork black cannot rewrite my read-only files). I did not run `fmt` (not in my command list); my serve test file was edited in this delivery, so its formatting is unverified.

## Verdict: **fix then merge**
Fix (one line, test-side, in a file outside both our scopes): add `"tq4_attention": "off"` to the runtime dict in `stub_manifest_lite` (`benchmark/bench/tests/test_run_reasoning.py:36-38`); then the two reasoning-resume tests pass (experiment 2). Do not change `pin_mtp_scan` for this. Optional minor: clear/overwrite `_TQ4_MANIFESTS[port]` on every `gather` for that port (so a mode-off or other-model gather does not leave a stale entry); run `ruff format` over the two mlx-serve test files. The source changes for findings 1–5 are verified by tests that fail on candidate 1 and pass on candidate 2; 6 and 7 by inspection and run.
