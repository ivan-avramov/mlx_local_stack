# M72 1.3: implementation report

**The mode is built end to end, but four things need your attention first.**
- I found and fixed a real NaN bug inherited from the p2s prototype.
- Three existing stack tests now fail because the spec requires the fingerprint bump to v9; they need updating, and their files are outside my scope.
- I couldn't add a `tq4` keyword to `base.scaled_dot_product_attention`, so `base.py` has a separate entry point instead.
- The full stack suite never finished.

Nothing is committed.

## Issues for the designer

- **I1, p2s NaN bug (fixed).** MLX's fused SDPA reads masked key/value rows past the sliced key length, up to its 32-row key-block boundary. If a recycled scratch buffer holds NaN or ±Inf there, 0 × NaN makes the whole output non-finite.
  - It showed up at T = 4,100 only after other tests had run. A probe that fills freed buffers with NaN gave non-finite output at T = 4,100 and clean output at 4,096 and 4,128.
  - The prototype's stale-scratch test only used finite garbage, so it never saw this. `dev/m72_scratch_prefill.py` still has the bug (I left `dev/` untouched as instructed).
  - Fix: the dequantize kernel writes zeros for rows [T, round_up(T, 128)), and the scratch is allocated at capacity rounded up to 128. That is still one size per cache, and it is unchanged at 262,144. 28 regression tests cover it.
- **I2, forced fused kernel (fixed).** MLX has no forced fused SDPA for chunks of 6–8 queries at GQA 6, and `force_fused=True` raises there. p2s now forces only where a kernel exists and lets MLX choose for L 6–8. I recorded this in `docs/box-notes.md`.
- **I3, existing tests that conflict with the spec.** The spec requires the fingerprint bump to v9, so these three stack tests fail:
  - `test_mtp_verify_scan_provenance.py::test_ac10_fingerprint_version_is_8`
  - `test_mtp_verify_scan_provenance.py::test_ac10_controls_carry_per_control_introduction_versions`
  - `test_provenance_fingerprint.py::test_m50_router_block_rides_the_manifest_but_not_the_fingerprint`. It mocks only the three older controls, so the new one resolves to "unknown", which the existing T2 rule makes incompatible with everything.

  All three need edits in files I'm not allowed to change.
- **I4, signature pin.** An existing M57 test pins `base.scaled_dot_product_attention`'s exact signature. I added a separate `base.tq4_scaled_dot_product_attention` instead. Only stamped modules call it, and a None from the mode falls through to the unchanged function with the same arguments. Two existing source-scanning tests also constrain this: one requires a single policy-passing call site, and one counts exactly two `scaled_dot_product_attention(` calls in the verifier. Both still pass.
  - The verifier rebinds `scaled_dot_product_attention` locally to keep those two literal call sites. The pre-commit autoflake hook had silently removed its import, which would have broken the mode-off verifier. I restored a static reference and re-ran everything.

## Files changed

**Fork (`../mlx-vlm`)**
- `mlx_vlm/tq4_fast.py` (new): the three promoted kernels (p2s dequantize, matrix-unit verify with the TQ4 loader on the 512-token block plan, D2 pass 1), `supports`, route counters, `self_test`.
- `mlx_vlm/tq4_attention.py` (new): `MODES`, `resolve_mode`, `require_environment`, `check_fp16_range`, `apply_to_model`, `self_test_model`, the `Tq4Mode` hook, `require_policy_stamps`.
- `models/base.py`: new `tq4_scaled_dot_product_attention`; the existing function is unchanged.
- `models/qwen3_5/language.py`: `tq4_attention` stamp; the stamped call; `mx.eval(output)` once per TQ4 layer per prefill chunk.
- `models/qwen3_5/speculative_verifier.py`: the mode's verify hook runs before `joint_v1`; width-1 and per-query singleton calls route through the mode when stamped.
- `mtp_verify_scan.py`: `require_environment(..., tq4_mode=None)` accepts TurboQuant kv_bits 4 only with a mode.
- `server/cli.py`: `--tq4-attention off|m72_v1|m72_exact`, with `MLX_VLM_TQ4_ATTENTION` always written.
- `server/generation.py`: load order is resolve → environment check → `fused_v1` → `joint_v1` (with `tq4_mode`) → stamp check → `check_fp16_range` → `apply_to_model` → `self_test_model`.
- `server/app.py`: `/health` adds `tq4_attention: {mode, route_counts}` only when the mode is on.
- Tests: `test_tq4_impl_support.py`, `_kernels.py`, `_routing.py`, `_model.py`, `_wiring.py`.

**mlx-serve (`../mlx-serve`)**
- `config.py`: `tq4_attention` key and its four-way validation; `fused_v1` / `joint_v1` accept kv_bits 4 only with a mode.
- `process_manager.py`: `--tq4-attention` pass-through.
- `tests/test_tq4_impl_config.py`.

**Stack**
- `benchmark/bench/provenance.py`: fingerprint v9; `tq4_attention` serving control (values off/m72_v1/m72_exact); `registry_tq4_attention`; `tq4_route_counts`; manifest field `tq4_route_counts`, outside the fingerprint.
- `benchmark/spikes/m72_e2e_prefill.py`: `--capacity` (default `--tokens`) and the `tq4_m72` variant. The variant records cache classes, R1 values, route counts and A5's layer-63 allowance from the cache shapes.
- `docs/serving-path.md` and `docs/box-notes.md`: one entry each.
- Tests: `test_m72_13_impl_provenance.py`, `test_m72_13_impl_e2e_spike.py`.
- `compare.py`: unchanged; it already iterates the serving controls generically.

## Commands and results

- **`./fe_test.sh fork` (the whole suite):** exit code 0. It ran before the I1 fix and two comment/log-string edits. After those, I re-ran all my fork test files on the final code, slow rows included: 321 passed.
- **`./fe_test.sh serve`:** 239 passed, 1 failed. The failure is the known baseline `test_golden_first_pick_command_is_what_main_builds_for_the_same_registry`.
- **Stack, touched-provenance subset (11 files):** only the three I3 failures. One other failure from my change (`test_worker_serving_facts_...`) went away when I reverted an unneeded key.
- **Stack, my own tests:** `test_m72_13_impl_provenance.py` 36 passed. The spike test file: 7 passed and 1 skipped in the stack venv (no MLX); 8 passed via `./fe_py.sh -m pytest`.
- **Full `./fe_test.sh stack`:** never completed. The first run was killed at its time limit, and the restart was at 13% when I wrote this.
  - It collects with two errors: `test_t3_wave1.py` and `lcb_budget_test.py`.
  - It showed nine failures in `p475s1/test_fixtures_selfcheck.py`. They read files from the empty `src/` submodules, so they are copy-layout baseline. I didn't run the bench suite before my edits, so the two collection errors are baseline by inference only.
- **`./fe_test.sh fmt`:** clean (pre-commit rc 0, ruff rc 0).
- **Naming check:** I replaced the "N-bit" shorthands and the short model name I found in my new lines.

## Acceptance criteria

| | What ran | Outcome |
|---|---|---|
| A1 | `tq4_fast` on caches preallocated to 262,144. p2s and matrix-unit verify on the prototype sweeps and at 65,537 / 131,072 / 260,096 (heads 0/6/12/18; k = 2, 3, 5; L = 512 and 37). Negative controls: p2s N1; verify N1/N2/N3, consecutive and gapped. D2 at 2,049 … 260,096 and on a state sliced below the offset. D2 multi-query at k = 2…5 and across the 8,192 / 32,768 / 65,536 tiers. R2 fully masked blocks. | All pass; every negative control fails A1. D2 is bit-identical to today's singleton in every row. |
| A2 | One test per routing row; spies on the kernels plus counter and output checks. Includes k = 6, gapped lengths, width-1 commit-pending, `per_query:short`, every fallback reason, the 3-token chunk at T > 2048, and layer 63 (forced fused prefill, `joint_v1` verify). | 51 pass. |
| A3 | Fresh interpreters: the parent tree (via `git archive` of HEAD, since my change is uncommitted) vs this tree with the mode absent. Covers manual TQ4 and native16 decode, `generate_step` TQ4 MTP OFF/ON, and native16 MTP ON. | Tokens and logits byte-identical; no `mlx_vlm.tq4_*` modules imported; refusals unchanged. |
| A4 (a) | Synthetic model, both modes: two identical mode-off prefills (checked bitwise; this is my snapshot), 64 greedy tokens each. | Tokens and logits identical; counters show `d2` 64, `native:decode` 64. |
| A4 (c) | `m72_exact`, n = 256: greedy and seeded, real and scripted drafter, blocks of 3 and 4. | MTP ON tokens equal MTP OFF; `d2_verify` > 0, `mma` = 0, no `fallback:*`. |
| A4 (b) and real-model parts of A4 | — | The designer's. |
| A5, A6 | — | The designer's; the `tq4_m72` spike variant is ready for A5. |
| A7 | Synthetic model passes; planted violations of each bound are refused. | Pass. The real-model values are the designer's; the spike leg records them. |
| A8 | mlx-serve key, validation and pass-through; worker env and load order; `/health`; manifest and fingerprint. | Pass, apart from I3. The clean-clone gates are the designer's. |

## Route-counter names

`p2s`, `mma_prefill`, `d2`, `single_pass`, `mma`, `d2_verify`, `per_query:short`, `per_query:k_gt_5`, `per_query:gapped`, `native:prefill`, `native:verify`, `native:decode`.

Fallback reasons: `fallback:batch_cache`, `cache_class`, `codec`, `bits`, `rotation`, `batch`, `shape`, `dtype`, `mask`, `sinks`, `legacy`, `block_override`.

## Where I had to choose or depart from the spec

- **kv_bits 4 relaxation:** `mtp_verify_scan` accepts kv_bits 4 for both `m72_v1` and `m72_exact`, not only `m72_v1` as the load-order line says. The two modes share the same native layer 63, so limiting it to `m72_v1` looked like an oversight.
- **Load-time refusals beyond the spec:**
  - `TQ_DECODE_2PASS_LEGACY` is refused whenever it's set, even to "0".
  - The prod key codec is refused.
  - Missing `fused_v1` / `joint_v1` stamps are refused, checked in the server loader rather than `apply_to_model`.
  - A model with no 24/4/256 attention module is refused, checked in `self_test_model`.
- **Non-causal prefill:** a multi-query call with `mask=None` counts as `fallback:mask`, because p2s is always causal.
- **Gapped lengths:** the verifier only produces consecutive lengths, so `per_query:gapped` is reachable only through `Tq4Mode.verify_block` / `verify_lengths`.
- **First served chunk:** with `quantized_kv_start` 0, the server's first prefill chunk runs on native caches before conversion (today's behaviour), so it counts `native:prefill` on every full-attention layer.
- **Free choices:**
  - The per-layer prefill evaluation sits in `Qwen3_5Attention`.
  - The manifest field name is `tq4_route_counts`.
  - The CLI value `off` means absent.
  - I added two instrument entry points, `mma_attention` and `mq_decode_attention`, for the A1 controls.
  - The A4 snapshot is a twin mode-off prefill, verified bit-identical.
- **Slow marker:** long-context tests carry `pytest.mark.slow`. It isn't registered in the fork's conftest, which I can't edit, so pytest warns about it. They do run in the gate.


---


## Update: the full stack suite finished, with four failures from my change

The restarted full `./fe_test.sh stack` run completed with exit code 1. One of the failures caused by my change wasn't in my earlier report.

**Four failures come from my change, not three.** Add this one to I3:
- `test_orphaned_manifest.py::test_current_manifest_lite_INCLUDES_the_git_block`

It fails the same way as the router-block test. It mocks only the three older serving controls, so the new `tq4_attention` control resolves to "unknown" for its model, which isn't in the registry. The existing T2 rule then makes the manifest incompatible with everything.

Here is the corrected list of tests that need editing outside my file scope:
- `test_mtp_verify_scan_provenance.py::test_ac10_fingerprint_version_is_8`: the version pin needs to become 9.
- `test_mtp_verify_scan_provenance.py::test_ac10_controls_carry_per_control_introduction_versions`: the expected set needs `tq4_attention: (9, "off")`.
- `test_provenance_fingerprint.py::test_m50_router_block_rides_the_manifest_but_not_the_fingerprint`: needs a mocked `registry_tq4_attention` returning "off".
- `test_orphaned_manifest.py::test_current_manifest_lite_INCLUDES_the_git_block`: the same mock.

**The other failures and errors are copy layout.**
- 415 of the 419 error lines in the run point at files under `src/mlx-vlm` or `src/mlx-serve`, which are empty in this copy. They come from the `b2_*`, `t3_frozen_*` and `p475s1/test_fixtures_selfcheck.py` files.
- The two collection errors are `test_t3_wave1.py` and `lcb_budget_test.py`.
- No failure outside the four above mentions provenance, the fingerprint or `tq4`.
- I didn't run the suite before my edits, so "copy layout, not mine" is an inference from the error paths.

**Fork gate.** The full `./fe_test.sh fork` exited 0. That run predates the I1 scratch fix. Everything else from the earlier report stands, including the 321 passing tests of my fork test files on the final code.
