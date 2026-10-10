# M58 spec review 1 (Claude, cold) — `docs/specs/m58-joint-verification-scan.md`

**Verdict: REVISE.** The kernel premise is right *except at key-length thresholds*. There, the joint call is **not** bit-identical, and the gates as designed would not reliably see it (S1, VERIFIED on this box). One test cannot pass as written (S3, VERIFIED). Instrument and provenance gaps: S4, S5.

Method note: read-only on repo and forks. Besides reading, I ran two tiny identity checks with no timing and no model: CPU, and GPU on a quiet box (no mlx/bench process; :8000 free). Scripts: `$STACK_WORKDIR/m58/tmp/claude_review/{cpu_ac3.py,gpu_straddle.py,gpu_straddle_l2.py}`. Shape: GQA 6 (24/4 heads), D 256, bf16, random tensors. Comparison: per-query sliced qL=1 calls vs one joint call, bitwise via a `uint16` view.

---

**S1 — BLOCKING — P89 rules 1–4, STEP 1, G1a/G1b, "identity replaces quality" (spec:16-26, 52-57, 96-102, 116).**
The kernel is chosen by key length N, and this rule set ignores that.
- MLX picks one-pass vs two-pass and the 2-pass `blocks` count **per call from N**. The fork mirrors this logic (`../mlx-vlm/mlx_vlm/models/qwen3_5/language.py:498-534`). On this device class, blocks change at N>1024, >8192, >32768 and >65536, and the pass switches at N≥1024. The class is `applegpu_g17s`, from `mx.device_info()` (VERIFIED).
- The 2-pass kernel strides keys by `blocks` and stores bf16 partials (`.venv/.../mlx/include/mlx/backend/metal/kernels/sdpa_vector.h:263,299,316`). So a different `blocks` value means a different summation order. The fork's own test says so: `../mlx-vlm/mlx_vlm/tests/test_model_ops.py:282-283`.
- Per-query calls use N = prefix+1 … K. The joint call uses N = K. So any block whose range [K−length+1, K] crosses a threshold gives different bits.

GPU check, VERIFIED (`X` = differs, `=` = identical):

| length | K = 1024 | 1025 | 1026 | 8193 | 8194 | 32769 | 32770 | 65537 | 65538 |
|---|---|---|---|---|---|---|---|---|---|
| 3 | `XX=` | `XX=` | `X==` | `XX=` | `X==` | `XX=` | `X==` | `XX=` | `X==` |
| 5 | `XXXX=` | `XXXX=` | `XXX==` | `XXXX=` | `XXX==` | `XXXX=` | `XXX==` | `XXXX=` | `XXX==` |

- Every other cell was identical: 512, 1022, 1023, 1029, 4096, 8192, 8195/8197, 32768, 65536, 65539/65541, 70000, 131072.
- `"causal"` and the boolean step mask give the same pattern.
- E8's cells (65536/131072/262144; `docs/proposal-flash-attention.md:419-422`) are all threshold-free, so E8's identity claim is true but does not cover this.

Why the gates miss it:
- G1a's 128K/256K rungs and the 128K continuation sit above every threshold. The 8K/64K rungs only hit one if the decode happens to cross 8193 or 65537.
- G1b's C84 set tops out at about 4.4K completion tokens (`$STACK_WORKDIR/m48/parity/{before_on,after_on}.json`: 20 rows, max 4358). It does cross 1024/1025, but a 1-ulp difference changes `content_sha256` only by chance. So G1b passes or fails by luck.
- The daily driver does cross these thresholds (E9 contexts 14–28K; `docs/proposal-flash-attention.md:423-428`). As written, the lever is a small numerics change. Under AGENTS.md ("never assume bf16 speculation lossless"; lossy-lever rules) it would then need quality evidence.

Rewrites:
- Add **rule 5**: joint only if `_qwen3_5_sdpa_vector_plan(prefix_length + 1, nq, nkv) == _qwen3_5_sdpa_vector_plan(key_length, nq, nkv)` (both mode and blocks). Otherwise run per-query and count `verify_scan_straddle`.
- Refuse `joint_v1` at load if `MLX_SDPA_BLOCKS` is set. libmlx reads that variable (`strings libmlx.dylib`, VERIFIED), and the mirror ignores it.
- The thresholds belong to `joint_v1` + MLX 0.32.2. Any MLX bump re-runs the STEP 1 sweep.
- **STEP 1:** add a key-length sweep around each threshold: 1018–1030, 8188–8200, 32764–32776, 65532–65544, qL 3–5. Decision rule: the mirror predicts **exactly** the mismatching cells, with no mismatch anywhere else.
- **G1a:** place rung prompts so the 256-token decode crosses 1024, 8192, 32768 and 65536 (prompt ≈ T−64). Under AB, shadow-compute straddle blocks into `verify_ab_straddle_mismatch`. That count must be > 0: it is the live known positive (AGENTS "validate instruments against known positives"). `verify_ab_mismatch` over eligible blocks must be 0.
- Cost of the fallback: at most length−1 rounds per threshold per request. Negligible.

**S2 — MAJOR — R2 / the length-2 claim (spec:13, 26, 132-133).**
- The shipped `length == 2` joint branch (`speculative_verifier.py:114-129`) is **already** non-identical to per-query/plain decode at thresholds. GPU check, VERIFIED: L=2 gives `X=` at K = 1024, 1025, 8193, 65537. So "identity at 3–5 is expected" rests on a branch that was never exact.
- That is a pre-existing exactness bug. Per AGENTS it needs its own proposal. Recommendation: let rule 5 cover length 2 under the same version name, with operator approval, rather than leave lengths 1–2 "untouched".
- Also, "identical to the length == 2 branch" holds only for the step-mask formula. Length 2 converts only `"causal"` and passes `None` or 4-D masks unchanged (`:115-129`). Per-query treats `None` as causal-by-slicing (`:136-147`). Rewrite: "the step mask is the per-query slice set expressed as a mask".

**S3 — MAJOR — AC3 cannot pass (spec:68-70).**
- CPU check, VERIFIED: `mx.array_equal(joint, per_query)` is **False in 16/16 cells** (bf16/fp16 × K 64/1024 × L 3/5 × bool/causal). Max abs difference up to 9.8e-4 bf16, 2.4e-4 fp16.
- Cause (ASSUMPTION, compiled code): the CPU fallback's matmul/softmax reductions depend on shape (qL 1 vs L, N′ vs N).
- Rewrite AC3 as two parts:
  - (a) Bitwise test of the **mask**: the step mask's true-set equals the per-query key prefixes for every row, including None/causal/4-D-bool. This part is exact.
  - (b) Joint vs per-query `allclose` against an fp32 reference, with a stated tolerance. Bit-identity is GPU-only: STEP 1 and G1.

**S4 — MAJOR — G1b instrument (spec:99-101).**
- `bench/parity_replay.py:105-111` rows do not carry `draft_rounds`/`draft_n`/`draft_n_accepted`, the new counters, or the worker cmdline/runtime slice (VERIFIED). So "MTP counters identical per request" cannot be checked without a code change, which needs an AC. Nothing proves the joint path ran, and nothing proves which arm was served.
- Rewrite:
  - New AC: `parity_replay` persists `timings` draft counters, `verify_scan_*`, and the v8 runtime slice/worker cmdline.
  - G1b PASS also requires `verify_scan_joint > 0` on ≥ 18/20 rows.
  - On any failure, run a per_query→per_query reload control before reading it as a kernel effect. C84 cross-load identity (`docs/stack-certification-2026-09-14.md:40`) is the prior.
- Cost estimate VERIFIED as plausible: the m48 first-pick arms took 10.1–10.7 min with MTP ON.

**S5 — MAJOR — Provenance v8 vs existing v7 rows (spec:44-48, AC9).**
- `provenance.control_of` reads "unknown" for a v7 manifest that lacks a later key. The docstring (`benchmark/bench/provenance.py:565-566`) says "no v7 manifest exists on disk yet". That is now false: the M57 qualification rows are v7.
- `is_compatible` returns False on "unknown" (`:417-420`). Adding `mtp_verify_scan` to `_SERVING_CONTROLS` (`:557`) the obvious way therefore makes **every v7 row incompatible**: refused resumes, and `--clean-stale` archiving them.
- Rewrite: each control gets its own introduction version, e.g. `{"attention_policy": (7, "auto"), "lazy_prompt_embeddings": (7, False), "mtp_verify_scan": (8, "per_query")}`. `control_of` returns `(default, "default-pre-v<N>")` when `fingerprint_version < N`.
- AC9 must name a **v7** manifest (`fused_v1`, no `mtp_verify_scan`) as compatible with a v8 `per_query` row, and incompatible with a v8 `joint_v1` row.
- `compare_predictor._MUST_DIFFER_KEYS` (`benchmark/bench/compare_predictor.py:57`) gains the key.
- Other models under the default read `per_query` when the worker flag is absent: correct as specified.

**S6 — MAJOR — Rule 4 bound `V` (spec:22-23, 52) — challenge 3.**
- The kernel header *is* local: `.venv/lib/python3.12/site-packages/mlx/include/mlx/backend/metal/kernels/sdpa_vector.h`. The 2-pass threadgroup is (32 lanes, `gqa_factor`, `q_seq_len`) (`:202-227`). So the kernel's own bound is **32·gqa·qL ≤ the pipeline's max threads per threadgroup**: V = 32 at a 1024 limit, giving qL ≤ 5 at GQA 6 (VERIFIED from the header). The one-pass kernel (`:43-99`) has no qL bound.
- The pipeline limit can be below 1024 at D 256: the fork's test records 896 on an affected GPU (`../mlx-vlm/mlx_vlm/tests/test_model_ops.py:286-289`, VERIFIED). That would make V = 28.
- The host-side dispatch/fallback bound is compiled (`libmlx.dylib`). It cannot be verified locally. Upstream sources (ASSUMPTION paths): `mlx/backend/metal/scaled_dot_product_attention.cpp` (`sdpa_vector_2pass` dispatch, blocks) and `mlx/fast.cpp` (`ScaledDotProductAttention::use_fallback`), tag v0.32.2.
- Above the bound, X3 says `auto` silently falls back to the unfused path for qL 6–8 (`docs/proposal-flash-attention.md:301-303`): no raise, just non-identical. The spec's per-query fallback for lengths above V is correct, because it is today's code.
- The `sdpa_vector_2pass_1_gqa` variant (`sdpa_vector.h:320-324`) is instantiated only for D 64/128 with G 8 (metallib strings, VERIFIED), so it never applies here. Rule 2/4 must not be generalised.
- Rewrite:
  - V is derived as `floor(pipeline_max_threads / 32)` from the source, recorded in the spec.
  - A **load-time self-test**, M57-style (`../mlx-vlm/mlx_vlm/attention_policy.py:173-228`): one joint vs per-query call at the largest eligible length and 2048 keys on the GPU, compared bitwise. It refuses before READY on a mismatch or a raise, within the readiness timeout.

**S7 — MAJOR — Latency/adoption design (spec:104-117).**
- The decode instrument is fine *if* G1 holds: identical tokens and acceptance make tok/s a paired round-time measure. But 256 tokens is about 98 rounds (E11: 2.61 tokens/round; `docs/proposal-flash-attention.md:467-471`), roughly 6 s at 8K.
- "Any rung slower by > 3 %" has no stated noise basis. M57 used a 5 % decode red flag (`docs/specs/m57-qualification.md:68-69`), and leftover 5 shows 1.4–3.6 % branch drift (`docs/handoff.md:46-49`).
- Rewrite:
  - Slowdown counts only if it appears in **both** sessions at the same rung.
  - Use the 2000-token continuations at 65K/128K as the primary decode rows.
  - Add one non-latency session with `MLX_VLM_MTP_PROFILE=1` to record verify ms/round per arm. That is the direct mechanism test against E11's 120 ms → ≈104 ms.
  - The +5…8 % (64K) and ±3 % (8K) predictions are not in E8/E11/P69: state their basis or mark them ASSUMPTION. +14 % at 128K and +15 % at 256K match E11/P69 (VERIFIED).

**S8 — MINOR — Rule 3 mask dtype (spec:20-21).**
ANDing works only for `mx.bool_`. A float additive mask goes through the kernel's `float_mask` path (`sdpa_vector.h:105-106,120-121`), with different semantics. Rewrite: "`mx.array`, `ndim >= 4`, `dtype == mx.bool_`, last dim ≥ key_length". Everything else runs per-query.

**S9 — MINOR — Counters (spec:35-37).**
- The verifier is a module singleton (`language.py:25`; dispatch `:1872-1873`). Define the unit: per (layer, block) call, and separately blocks per path.
- State whether lengths 1/2 are counted.
- Use the snapshot/since pattern (`attention_policy.py:83-89`) for per-request scoping.
- Persist `verify_ab_*` and `verify_scan_straddle` in capacity/generate rows as well, not only `verify_scan_*`.
- Stamp the policy on the `attention` module passed to `_attention` (as M57 stamps `Qwen3_5Attention`), not on "the model instance".

**S10 — MINOR — AB instrument mechanics (spec:38-41, AC7).**
- Compare bitwise (`a.view(mx.uint16)`). `array_equal` treats −0 == +0, and NaN ≠ NaN.
- Accumulate mismatches lazily and read them once per round, not with an `.item()` per layer.
- AC7 asserts that the AB joint call is the *same function* as the production joint call.
- AB is env-only, so the worker cmdline cannot show it. Latency rows must assert that `verify_ab_*` keys are absent, or AB becomes a CLI flag.
- Under AB the served path is per-query. By induction, per-layer identity on identical inputs gives end-to-end identity for the blocks seen (sound). Production-path effects are G1b's job.

**S11 — MINOR — Scope enforcement (spec:33, AC6).**
The same verifier serves suffix-decoding and other speculative verification (`language.py:1476`). The worker must also refuse `joint_v1` without `--draft-kind mtp`; today AC6 covers the router only.

**S12 — MINOR — Claims (challenge 7).**
- "same reads of the cache once instead of `length` times" (spec:13-14) contradicts E8 (joint with 3 queries = 1.9× one query; `proposal:420`), P69 ("a single-pass kernel that reads keys and values once … would save about twice that", `:446`) and the spec's own P97. Rewrite: "one launch per layer instead of `length`; still about one K/V pass per query (L2-shared)".
- E8, E11, P69 and X9 quotes otherwise accurate (VERIFIED `proposal:314-315,419-422,444-447,467-471`). P60's ≈2× is superseded by P69, and the spec should cite P69 only.

**S13 — MINOR — AGENTS.md compliance (challenge 8).**
- No daemon monitor per run (AGENTS "Every run needs a daemon"). M57 qualification had one (`m57-qualification.md:27`).
- Worker cmdline recording (`--model`/`--draft-kind`/new flag) is not stated.
- "Persist counters the way they persist `sdpa_*`" depends on the **uncommitted** working-tree changes (`git status`: `benchmark/bench/capacity_ladder.py` adds `_sdpa_from_raw`; `provenance.py` modified). The build base commit must be pinned.
- Naming, M50/C106, `MLX_VLM_CACHE_SESSION_MAX=1`, power/idle protocol and order balance are compliant.

**S14 — MINOR — Cost labels (spec:119-126).**
The heading says "sized from the seeded pilot; lower bounds", but the pilot has not run. Label the G1a and latency figures as priors, with their basis: the M57 ladder ≈ 4.7 h over 8 arm-sessions ≈ 35 min each (`m57-qualification.md:47`). G1b ≈ 30 min is VERIFIED plausible (S4).

**Challenge 1 residuals (VERIFIED):**
- The verifier passes no `policy`, so M57 rules 3–4 and `force_fused` never reach it (`speculative_verifier.py:122-161`, `base.py:434-454`). Even if passed, `fused_v1` never forces qL ≤ 8 (`attention_policy.py:68-69`).
- Same dtype and GQA mapping on both paths (`sdpa_vector.h:217-227`).
- The cache is updated before attention (`language.py:1038`), so `prefix_length = key_length − length` holds.
- Quantized/TurboQuant caches are routed before the native branch (`base.py:379-432`). The left-padded path returns first when padding exists (`speculative_verifier.py:104-112`; `language.py:764-774`).
- Drafter/acceptance/rollback read hidden states, logits and the cache, never attention outputs directly (`../mlx-vlm/mlx_vlm/speculative/mtp.py:75-125,694-699,764`). AC10 is a valid wiring tautology.
