# P400 — TurboQuant KV × width-2 MTP verify block: fix proposal — v1, 2026-10-19

Status: **v1, for operator approval** after a Cursor plan review (round 1 of 3, C186). Parent: `docs/open-questions.md` P400
(root cause confirmed), P369 phase 2 (`docs/specs/p369-phase2-run-plan.md` v9). Production code change in the fork
`../mlx-vlm` (never `src/*`), test-first.

## 1. Defect (measured)

- **Live** (GPU smoke 4, fork `8d1cf115`, production pin `4e6d0e03`): `Qwen3.8-27B-mlx-uniform-4bit` (TurboQuant 4-bit KV,
  `per_query` verification) — in 3 of 4 E1c cells MTP-ON vs plain decoding on the same loaded instance differed at exactly the
  length-terminal position (one row, same support, TV ≈ 0.009) and in the final commit's KV state, with the within-instance
  control (OFF1 vs OFF2) identical and every earlier row / commit bit-equal. The terminal verifier block had width 2.
  `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (native16 KV, `joint_v1`) was exact in every cell.
- **Fixture** (`test_mtp_exactness._quantized_pair` for `Qwen3.8-27B-mlx-uniform-4bit`: the bf16 uniform-affine 4-bit fixture pair + `kv_bits=4, kv_quant_scheme="turboquant",
  quantized_kv_start=0`, scripted full-accept drafter): the last position differs whenever the final round has one token of
  budget left (n = 14, 17, 20 … at block 3); with the MTP block forced to 2, 5–12 rows differ per request and MTP-ON EMITS
  DIFFERENT TOKENS than plain decoding (n = 15, 17); blocks 3 / 4 on TQ4 and every block size on the default KV are exact.

## 2. Root cause (confirmed)

`mlx_vlm/models/qwen3_5/speculative_verifier.py` `Qwen3_5BatchInvariantForward._attention` (inherited by
`Qwen4ExpBatchInvariantForward`): after the left-padded path and the verify policy (`joint_v1`) decline a block, a block of
**length 2** is served by ONE batched `scaled_dot_product_attention` call with an explicit causal mask, while **length > 2** uses
the per-query loop (one singleton SDPA per query over its own key prefix) that reproduces plain decoding. On a TurboQuant cache
the batched call routes into `TurboQuantKVCache.quantized_attention` with `L = 2`, whose multi-query path (prefill key chunking,
query blocks, `turboquant.py` `quantized_attention`) is not bit-identical to the `L == 1` decode path; on the default KV MLX's SDPA
happens to be exact for `L = 2`. Patching only that branch away (length 2 → the per-query loop) makes the fixture exact at
every block size and length (rows and tokens), so it is the whole defect. The branch is upstream code (upstream `bf4b8612`,
"Add GLM-5 Next support (#2127)"). `joint_v1` serves every block before the branch, so
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` does not reach it on eligible blocks; an ineligible (fallback) length-2 block on
its native16 KV was exact anyway (default-KV measurement).

## 3. Fix (recommended: A)

- **A (recommended):** delete the length-2 special case; every length > 1 block not served earlier takes the per-query loop.
  Exact by construction (the same singleton call plain decoding makes). Cost: one extra SDPA call per width-2 block (width-2
  blocks are the budget-terminal round and adaptive block-2 rounds only). Marked `# Fork (P400):` per the fork-marker audit;
  body-divergence / registry / call-argument audits re-run; an upstream issue with the fixture repro is offered to the operator.
- B: keep the fast path except on quantized caches (`hasattr(cache, "bits")`, the test `_qwen3_5_left_padded_attention` uses).
  Smaller blast radius, but keeps an exactness property that is measured, not guaranteed, on the default KV.
- C: make `quantized_attention(L = 2)` bit-identical to two decode steps. Fixes the root numerics for every caller, but it is a
  kernel-path change in TurboQuant with a far larger review surface; out of scope here (possible later, own proposal).

## 4. Tests (red first; Metal fixtures, both picks' deployed KV codecs)

1. **E1a / E1c with the deployed KV codec** — the gap that hid P400: the quantized E1a / E1c fixture tests gain the pick's KV
   (`Qwen3.8-27B-mlx-uniform-4bit`: TurboQuant 4-bit, `quantized_kv_start=0`; `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`:
   native16) and block sizes {2, 3, 4} × lengths covering the one-token-budget terminal round × 3 seeds: tokens equal plain,
   ON / OFF rows (forced positions per P398) and states equal. Red today for the TurboQuant cases at block 2 and the
   terminal width-2 round; green after A.
2. **Branch-level unit test:** a length-2 block on a TurboQuant cache through `_attention` equals two singleton calls bitwise
   (red today).
3. Existing suites unchanged; the phase-2 harness's `PRODUCTION` pin moves to the fix commit (its pin test updated).

## 5. Sequencing (the `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` full run is on the GPU now)

- Build in a NEW worktree / branch (`p400-tq-width2` off `p369-mtp`; tests with `PYTHONPATH=<new worktree>` so the production
  tree under test is the new one, never the running harness's); the P369 worktree is not touched while the run is live.
- During the run: implementation + the targeted Metal fixture tests only (tiny, seconds). After it ends: fork suite ×2 + the
  eight audits, Cursor code review (round 1 of 3), then the operator's approval of the production change.
- Then re-pin: `PRODUCTION` = the reviewed fix commit; P369 phase 2 for `Qwen3.8-27B-mlx-uniform-4bit` (smoke + full, ≈ 2.4 h
  projected from smoke 4's 1,468 s × 6) and a regression smoke for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` on the new
  pin (≈ 27 min; its full-run evidence carries over iff that smoke passes, since the fix only replaces a path its eligible
  blocks never take). Then the fork main merge + submodule bump, re-certification on real chains, MTP-ON restore (C177).
- Harness follow-ups that `Qwen3.8-27B-mlx-uniform-4bit` needs anyway: the `tq_norm` / `old_prefix_k` smoke positives never
  fired on its live cache (TurboQuant leaf detection) — fixed test-first before its smoke.

## 6. Acceptance

Red → green on §4 (1) and (2); fork suite 0 failed twice with identical skips (P401 must be root-caused or explicitly
excluded with the operator first); eight audits green; production diff = exactly the `_attention` change (+ marker);
`Qwen3.8-27B-mlx-uniform-4bit` phase-2 smoke then full run E1c PASS (or a bound) with C1 identical.

## 7. Operator decisions

(1) Approve A (vs B / C). (2) The re-certification scope in §5 (`Qwen3.8-27B-mlx-uniform-4bit` phase 2 full + `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` regression smoke on
the new pin). (3) Whether to file the upstream issue.
