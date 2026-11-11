# Test-writer report, delivery 2 — candidate review, M72 1.3

Patches applied cleanly to the baseline copies (`git apply` ×3). My frozen files were untracked files the patches do not touch; their
set is unchanged (fork 6, mlx-serve 1, stack 2) and the same named tests ran: fork 363 = 363, mlx-serve 57 = 57, stack 35 = 35.
Raw output: `../scratch/cand_fork.txt`, `cand_serve.txt`, `cand_stack.txt`, `cand_serve_full.txt`, `cand_fork_full.txt`.
Device `applegpu_g17s`, MLX 0.32.4. Nothing fixed, committed or edited; the frozen tests are unchanged.

## 1. Frozen tests: baseline → candidate

| file | tests | baseline | candidate |
|---|---|---|---|
| fork `test_tq4_m72_support.py` (T) | 5 | 5 pass | 5 pass |
| fork `test_tq4_m72_kernels.py` | 167 | 1 pass, rest error/fail | 166 pass, 1 FAIL |
| fork `test_tq4_m72_mode.py` | 83 | 6 pass | 70 pass, 13 FAIL |
| fork `test_tq4_m72_routing.py` | 76 | 1 pass | 73 pass, 3 FAIL |
| fork `test_tq4_m72_memory.py` | 7 | 1 pass | 7 pass |
| fork `test_tq4_m72_generation.py` | 25 | 5 pass | 19 pass, 6 FAIL |
| mlx-serve `test_tq4_m72_config.py` | 57 | 5 pass, 52 fail | **57 pass** |
| stack `test_m72_13_provenance.py` | 22 | 2 pass | 22 pass |
| stack `test_m72_13_harness.py` | 13 | 7 pass | 12 pass, 1 FAIL |

Fork frozen total: `23 failed, 340 passed, 2 warnings in 28.24s` (baseline `105 failed, 19 passed, 239 errors`). No test is skipped.
The A3 byte-identity goldens (mode absent: TQ4 T=600, T=2300, native16, TQ4 MTP) pass on the candidate, as do the
memory tests (one chunk through 9 TQ4 layers ≤ 2 scratches, capacity-sized scratch, no piling in the buffer cache) and
all 167 kernel-level A1 rows except the batch-cache one below.

Failures, verbatim ids, with the reason traced for each (none is a defect of the candidate except where marked):

- `test_tq4_m72_kernels.py::test_kernels_refuse_a_batch_cache` — `DID NOT RAISE`. Candidate: see finding F3 (minor).
- `test_tq4_m72_mode.py::test_require_environment_accepts_the_legacy_flag_spelled_off[0|false|no]` — the candidate refuses whenever
  `TQ_DECODE_2PASS_LEGACY` is set to any non-empty string (F4, minor; my test assumed the cache's own off-spellings).
- `test_a7_q_norm_bound[1025.0-False]` — **test bug**: the model's `q_norm.weight` is bf16, 1025 rounds to 1024 (probe: `1025 → 1024.0`),
  which is exactly the accepted bound. `test_a7_codebook_bound[key_codec-1.5-False]`, `[value_codec-1.5-False]` — **test bug**: the real
  4-bit MSE codebook's max |c| is 0.1685; ×1.5 = 0.25 is far below 1.
- `test_load_order[m72_v1|m72_exact]`, `test_a_failing_mode_stage_aborts_the_load[ta.check_fp16_range|ta.apply_to_model|ta.self_test_model]`,
  `test_mtp_verify_accepts_quantized_kv_when_the_mode_resolved[m72_v1|m72_exact]` — the candidate adds `require_policy_stamps`
  (beyond the spec, disclosed), which refuses my loader fixture because the fixture stubs `ap.apply_to_model` / `mv.apply_to_model`.
  With that one call neutralised in a scratch runner (`../scratch/run_nostamp.py`) all 26 selected load tests pass: the order is
  resolve → require_environment → attention policy → MTP verify → check_fp16_range → apply → self_test, failures propagate, and
  `mtp_verify_scan.require_environment` accepts kv_bits 4 under both modes.
- `test_prefill_chunk_takes_p2s[m72_v1|m72_exact]` — routing and counters pass; my `near()` tolerance (5 % of max logit) is exceeded:
  max 1.39 on |logit| 23.75 = 5.9 %, but per row median 0.9 %, p90 1.6 %, 2 of 512 rows above 5 %, argmax equal on 503/512, rms 1.3 %
  (`../scratch/probe_rows.py`); mode-off chunk-order noise is 0.0, so this is p2s-vs-tiled rounding amplified by the synthetic
  model (norm ×12, bf16), consistent with the kernel-level A1 rows passing. **Test tolerance unsupported by the spec** (no model-level bound exists).
- `test_health_details_carry_the_route_counters` — the candidate reports the block from `runtime.response_generator.tq4_attention`
  (`server/app.py`), present only on a loaded server; my test has no loaded generator. Premise unsupported; the spec pins only "worker's /health details".
- `test_a4c_exact_mode_mtp_on_equals_mtp_off[3|5|7-accepting|rejecting-seeded]` (6) — seeded sampling diverges at token 89. **Control**
  (`../scratch/control_seeded.py`): with the mode ABSENT the same ON-vs-OFF seeded comparison diverges at token 93 (policies stamped) and 127
  (not stamped), so the divergence is not caused by the mode; all 6 greedy rows (`d2_verify` > 0, `mma` = 0) pass. **My seeded rows are
  unsupported on this synthetic model at n = 256**; they do not show `m72_exact` inexact.
- `test_m72_13_harness.py::test_docs_record_the_mode[box-notes.md]` — the candidate's `docs/box-notes.md` entry is the forced-fused SDPA fact
  (I2) and does not name `tq4_attention`; the spec requires "entries" without saying what they contain. Over-specific test.

Tests I now think the spec does not support (not edited): the three A7 rows above, the 5 % prefill logit tolerance, the `/health` test as
written, the six seeded A4(c) rows, the box-notes content assertion, the spelled-off legacy rows (spec says "is set"), and, arguably,
`test_kernels_refuse_a_batch_cache` (spec: "preconditions asserted" for batch 1; a one-row batch cache is batch 1). The load-order and
abort tests are supported by the spec; they fail only because of the candidate's extra check.

## 2. Suite results

- `./fe_test.sh fork` (full): `23 failed, 10666 passed, 18 skipped, 22 xfailed, 15 warnings, 685 subtests passed in 508.64s`. All 23 failures are my frozen tests listed in §1 (23 of 23 FAILED lines are in `test_tq4_m72_*`); no pre-existing fork test fails. The warnings include `PytestUnknownMarkWarning: Unknown pytest.mark.slow` from the implementer's `test_tq4_impl_kernels.py:49` and `test_tq4_impl_model.py:211` (marker unregistered).
- `./fe_test.sh serve` (full): `1 failed, 296 passed, 1 warning in 1.36s`; the failure is the known
  `tests/test_config.py::test_golden_first_pick_command_is_what_main_builds_for_the_same_registry`.
- stack (my 2 files + `test_mtp_verify_scan_provenance.py`, `test_provenance_fingerprint.py`, `test_orphaned_manifest.py`,
  `test_m72_13_impl_e2e_spike.py`, `test_m72_13_impl_provenance.py`): `5 failed, 287 passed, 1 skipped in 28.25s`. Failures:
  `test_m72_13_harness.py::test_docs_record_the_mode[box-notes.md]` (above);
  `test_mtp_verify_scan_provenance.py::test_ac10_fingerprint_version_is_8`, `::test_ac10_controls_carry_per_control_introduction_versions`,
  `test_provenance_fingerprint.py::test_m50_router_block_rides_the_manifest_but_not_the_fingerprint`,
  `test_orphaned_manifest.py::test_current_manifest_lite_INCLUDES_the_git_block` (the four I3 tests: the version pin, the control table, and two
  mocks that do not know the new control, which resolves to `unknown` for a model absent from the registry — the same behaviour as the
  three older controls). The skip is the implementer's spike test needing this copy's fork on the import path (`./fe_py.sh -m pytest` runs it, per the implementer; I did not re-run it that way).

## 3. Findings

Verdict basis: I read the whole of `tq4_fast.py`, `tq4_attention.py`, the base/language/verifier/loader/CLI/app/mtp_verify_scan hunks, both
other patches' source changes, and ran the probes named below. No blocker and no major found.

**F1 (positive evidence, I1 fix) — verified.** `tq4_fast.py:160-178, 200-235`: rows [T, round_up(T,128)) are zeroed and the scratch is
rounded up to 128 rows. Independent probe (`../scratch/probe_i1.py`): NaN, +Inf and −Inf buffers of the scratch's size freed into MLX's buffer
cache before each call, 15 (T, L) pairs including T = 1, 2, 31, 33, 127, 129, 4096, 4097, 4100, 4127, 8193, 8200 and L = 1…512: no non-finite
output. Control (`probe_i1_control.py`): the same poison on the unfixed prototype gives non-finite output at T = 4100, 4097 and 129, so the instrument can see the bug. The prototype in `dev/` still has it (left untouched, as instructed).

**F2 — minor (observation) — `tq4_attention.py:53-101` `require_environment` accepts nothing about `kv_quant_mode` except `None/""/"mse"`, read from `TQ_KV_QUANT_MODE`.** The registry's `kv_quant_mode` reaches the worker as `--kv-quant-mode`; whether that sets `TQ_KV_QUANT_MODE` in the worker is outside this diff. If it does not, a `prod` registry entry is caught only per call by `supports` (`fallback:codec`), not at load. Traced, not reproduced. Scenario: a registry with `tq4_attention: m72_v1` and `kv_quant_mode: prod` starts, then counts `fallback:codec` on every call (no wrong output, but the mode is silently inert). Spec scope predicate says per call, so this is a deviation in strictness only.

**F3 — minor — `tq4_fast.py:117-135` `_check_cache` does not assert the cache class.** `decode_attention` on a `BatchTurboQuantKVCache` with one row returns an output (frozen test `test_kernels_refuse_a_batch_cache`, reproduced). The dispatch gate (`supports` → `batch_cache`) prevents it in the served path; the kernel entry points are public. Scenario: a caller using `tq4_fast` directly on a left-padded batch cache reads padded rows as real tokens. Not reachable from the server.

**F4 — minor — `tq4_attention.py:98-102`.** `TQ_DECODE_2PASS_LEGACY` set to `"0"`, `"false"` or `"no"` is refused although the cache treats it as off (`turboquant.py` parses only 1/true/yes). Spec says "is set", so this is the literal reading and the safer one; an operator exporting `=0` gets a start-up error. Disclosed by the implementer.

**F5 — minor — `models/base.py:480-505`, `speculative_verifier.py:28-34, 133` (I4).** Verified: the separate entry point leaves `scaled_dot_product_attention` unchanged; `_singleton_attention(None)` returns the module's own function, so the mode-off verifier calls the same function object as before; the local rebinding is assigned before any use in `_attention` (no `UnboundLocalError`; the A3 goldens and the existing suites pass). Residual risk: the rebinding shadows an imported name inside a function, and a formatter/linter pass that drops the "unused" import was what hid it once already (it is now referenced in `_singleton_attention`). Not a defect today.

**F6 — minor — `provenance.py` `tq4_route_counts` is called from `gather` (`+1941`), i.e. once at manifest creation.** The manifest records the counters of that moment, not of the run; if `gather` runs at run start they are zeros. The spec says "exposed in … the manifest"; it does not say when. Scenario: a row's manifest shows `route_counts` all absent although the run used `d2`. Traced, not reproduced.

**F7 — minor — `server/app.py` `/health`** reports the block only when `runtime.response_generator.tq4_attention` is set (verified: mode off ⇒ key absent, matches the implementer's statement and the spec's "only when on"). The route counters are per process and never reset (verified by the monotone-counter test).

**F8 — minor (beyond the specification, all disclosed or visible in the diff).**
`require_policy_stamps` (load refusal when the native layer's `fused_v1` / `joint_v1` stamps are missing); `--tq4-attention off` CLI value; refusal of any set `TQ_DECODE_2PASS_LEGACY`; `fallback:mask` for multi-query calls with `mask=None`; production-module instrument knobs (`mma_attention`, `mq_decode_attention`, `block_tokens`, `_kv_head_shift`, `prefill_attention(_kv_head_shift=)`) that widen the public surface of `tq4_fast`; `pytest.mark.slow` used in the implementer's fork tests although the marker is not registered (confirmed: the full fork run warns `Unknown pytest.mark.slow`).

**Threat checklist (traced and exercised).**
- Mode-off numerics: A3 goldens (4) pass (the implementer's own A3 comparison was not re-run by me); no `tq4_*` import on the mode-absent request path (my import-guard test passes for TQ4 and native).
- `cache.offset` vs passed length: kernels take T / `lengths` (`tq4_fast.py:341-345, 559-585, 716-724`); planted-bait rows at k = 2, 3, 5 and the D2 decode row pass, and their leak/drop controls fail A1 as they must.
- `m72_exact` exactness: D2 multi-query bit-identical to the singleton for k = 2…5, T up to 260,096, tier straddles [65,535…65,538] etc.; routing `d2_verify` / `per_query:short` / `per_query:k_gt_5` rows pass bit-identically; greedy MTP ON = OFF at n = 256 for block 3, 5, 7. Seeded equality is not demonstrable on this synthetic model even with the mode absent (above), so it is neither confirmed nor refuted here; it remains the designer's stack-smoke item (A4c on the real model).
- Memory: one scratch per layer per chunk (`language.py` `mx.eval(output)` after each TQ4 layer's attention, `L > 1` and `type(cache) is TurboQuantKVCache`); frozen memory tests pass (9 TQ4 layers, capacity 65,536: ≤ 2 scratches; ≥ 0.9 scratch, i.e. capacity-sized; ≤ 3 cached after 4 chunks). Rounding the scratch to 128 rows is a ≤ 127-row increase, none at 262,144.
- Registry: mlx-serve validation matches the spec in every frozen row (57/57), including `fused_v1`/`joint_v1` + kv_bits 4 accepted only with a mode and both still refused without it. Observation: `tq4_attention: false/0/null` in YAML loads as absent (`entry.get(...) or ""`), not as an error.
- Load order and refusals: as in §1; every refusal I exercised stops the load before the later stages.
- Spec deviations: only those in F8; all counter names are the spec's; `native:*`, `mma_prefill`, `d2_verify`, `per_query:*`, `fallback:<reason>` as specified (`batch_cache` reason exact).

## 4. Not verified here
The implementer's own tests were not re-run beyond the stack files named; the real model (A4b, A5, A6, A7 real values) and the stack clean-clone gates are the designer's; the stack's full suite was not run (this copy's `src/` is empty).

## 5. Verdict: **merge** (after the designer's gates), with the minor items for the designer's choice.
No blocker or major finding. The failing frozen tests are, one by one, test-side premises the specification does not support (bf16 rounding of the planted γ, a codebook scale, a 5 % model-level logit tolerance, a seeded-equality row that fails with the mode absent, a loaded-server `/health`, a box-notes content assertion, legacy-flag spellings) or the candidate's disclosed extra checks; none shows a numerical, routing, exactness, memory or registry defect. The four I3 stack tests need their mocks/pins updated by the operator (outside the implementer's scope). If the designer wants the stricter reading, F2 (prod-key refusal at load from the registry) and F3 (batch-class assertion in the kernels) are the two small fixes worth considering; F4 is the designer's call.
