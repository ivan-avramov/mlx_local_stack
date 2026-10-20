# P400 — TurboQuant KV × width-2 verify block: fix proposal — v4, 2026-10-19

Status: **v4** = v3 + plan-review round 3's only finding T10 (the memory gate measures the decode phase; T4 T8 T9 resolved,
T6 completed by T10) — rounds exhausted (C186), to the operator. **v3** = v2 + plan-review round 2 (T4 T6 T8 T9, `docs/reviews/p400/plan-round2…`; T1 T2 T3 T5 T7 resolved) — for
round 3 of 3, then operator approval. **v2** = v1 + every Cursor plan-review round-1 finding (T1–T7, `docs/reviews/p400/plan-round1…`) + the operator's
answers (fix **A**, "the quality-maximizing option"; no upstream issue; the re-certification scope of §5) + P401's hardening
(bundled: one production review, one re-pin). For plan review round 2 of 3, then operator approval. Production change in the
fork `../mlx-vlm` (never `src/*`), test-first.

## 1. Defect (measured)

- **Live** (GPU smoke 4, fork `8d1cf115`, production pin `4e6d0e03`): `Qwen3.8-27B-mlx-uniform-4bit` (TurboQuant 4-bit KV,
  `per_query`) — in 3 of 4 E1c cells MTP-ON vs plain decoding on the same loaded instance differed at exactly the
  length-terminal position (one row, same support, TV ≈ 0.009) and in the final commit's KV state; the within-instance control
  (OFF1 vs OFF2) identical; every earlier row / commit bit-equal; the terminal verifier block had width 2.
  `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (native16 KV, `joint_v1`) exact in every cell.
- **Fixture** (`test_mtp_exactness._quantized_pair` for `Qwen3.8-27B-mlx-uniform-4bit` — the bf16 uniform-affine 4-bit pair —
  + `kv_bits=4, kv_quant_scheme="turboquant", quantized_kv_start=0`, scripted full-accept drafter): the last position differs
  whenever the final round has one token of budget left (block 3: n = 14, 17, 20 …); with the block forced to 2, 5–12 rows per
  request differ and MTP-ON EMITS DIFFERENT TOKENS (n = 15, 17); blocks 3 / 4 on TQ4 and every block on the default KV exact.

## 2. Root cause (confirmed) and dispatch map (T5)

`mlx_vlm/models/qwen3_5/speculative_verifier.py` `Qwen3_5BatchInvariantForward._attention`: after the left-padded path and the
verify policy decline a block, **length 2** is ONE batched `scaled_dot_product_attention` with an explicit causal mask, while
**length > 2** is the per-query loop (one singleton SDPA per query over its own key prefix = plain decoding's call). On a
TurboQuant cache the batched call is `TurboQuantKVCache.quantized_attention(L = 2)` — the multi-query (prefill-style) path, not
the `L == 1` decode path — so it is not bit-identical; MLX's own SDPA happens to be exact for `L = 2` on the default KV.
Removing the branch alone makes the fixture exact at every block size and length (rows and tokens). Upstream code (upstream
`bf4b8612`).

Dispatch map (who reaches the changed branch):
- **Qwen3.5 family** (`model_type qwen3_5`; both P369 picks): every speculative verifier that calls the exact verifier — MTP,
  DFlash, EAGLE and suffix verification — reaches `_attention`; the change is therefore not MTP-only, and the route-level tests
  below cover all of them (the exact verifier is drafter-agnostic).
- **Qwen4Exp** (`Qwen4ExpBatchInvariantForward` subclass): inherits `_attention`; its sparse QSA width-2 path dispatches
  through `dispatch_qsa_attention` and does not reach the branch; TurboQuant is unsupported for QSA auxiliary state. Its
  existing block-2 / sparse-boundary exactness test runs as a regression.
- **Gemma4 / Nemotron-H**: own verifiers (`gemma4/speculative_verifier.py:58`, `nemotron_h/speculative_verifier.py:351`) that
  ALREADY use the per-query loop for every length > 1 — no width-2 shortcut; unaffected. Fix A aligns Qwen3.5 with them.
- `joint_v1` (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`): serves eligible blocks before the branch; its `per_query`
  FALLBACK decisions return `None` and DO reach it (T3, §5).

## 3. Fix — A (operator-chosen)

Delete the length-2 special case: every length > 1 block not served earlier takes the per-query loop. Marked
`# Fork (P400):`; body-divergence / registry / call-argument audits re-run. **Scope (T1):** exactness is restored by
construction for UNPADDED single-sequence verification (B = 1 — the cached-session path both picks serve; EpiCacheKVCache is
single-sequence). Batched B > 1 LEFT-PADDED TurboQuant verification has a separate candidate defect (plain singleton decoding
turns `"left_padded_decode"` into `mask=None` and the ragged helper declines caches with `bits`, so quantized fallback
attention may attend padded keys, while a multi-token verifier keeps slices of `BatchTurboQuantKVCache.make_mask`): it is
CHARACTERIZED in this round (a B = 2, one-row-left-padded TurboQuant ON vs OFF test, recorded as `xfail(strict=True)` with the
measured divergence if real) and filed as its own open question — not fixed here. B / C were rejected (B keeps an accidental
default-KV property; C changes TurboQuant's prefill numerics for every model).

**P401 hardening (bundled; round 2 T8):** in `qwen3_5` `LanguageModel.__call__`, on the scalar-offset path only (the
per-row batched-offset path does not slice and is unchanged), with `L` = the chunk length and `P = position_ids.shape[-1]`:

```python
if P < L:
    raise ValueError("position_ids shorter than the chunk")          # never valid
if P > L:                                                            # a full-prompt buffer: slice at the cache offset
    position_ids = position_ids[..., cache_offset : cache_offset + L]
    if position_ids.shape[-1] != L:
        raise ValueError("position_ids do not cover the chunk at the cache offset")  # an unprimed / short buffer (P401)
# P == L: already block-local (e.g. Qwen4 speculative verify) — not sliced, not checked
```

Every production warm prefill primes absolute full-prompt positions (`dispatch.py` session reuse, APC, canonical prefill), so
the check can only fire on an unprimed caller. **EpiCache is excluded (round 2 T9):** with `EpiCacheKVCache` the slice start
is the PHYSICAL retained length, not the logical `rope_offset = evicted + offset`, so after an eviction a full-length but WRONG
slice would pass any shape check; EpiCache is opt-in (`MLX_EPICACHE_BUDGET` > 0), set nowhere in the stack, and stripped by
the P369 worker env allowlist — filed separately as P402 (logical-offset slicing + a value-level test), not fixed here.

## 4. Tests (red first; T2, T7)

1. **E1a — deterministic joint law** on the quantized fixture with the pick's deployed KV codec (`Qwen3.8-27B-mlx-uniform-4bit`:
   TurboQuant 4-bit, `quantized_kv_start=0`; `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`: native16) with an ASSERTED
   width-2 verifier round (red today for TQ4).
2. **E1b — paired token identity** ON vs plain across 3 seeds × block sizes {2, 3, 4} × lengths covering the one-token-budget
   terminal round (red today for TQ4 at block 2 / the terminal round).
3. **E1c — rows + complete logical state** (P398 forced positions excluded, forcing schedules compared) on selected lengths
   / seeds; the E1c helpers learn TurboQuant: `_kv_leaf` and the packed-state corruption positive handle `TurboQuantKVCache`
   (today they find only a literal `KVCache` and would raise `StopIteration`).
4. Every case ASSERTS the actual cache class, codec, bit width and the observed verifier widths, so a plumbing fallback to
   native KV cannot pass silently.
5. **Route-level unit test:** a length-2 block through `_attention` on a TurboQuant cache vs two sequential singleton calls on
   an INDEPENDENT cache — outputs and the final cache state bitwise; a spy proves that pre-fix `L = 2` reached
   `quantized_attention` with `L = 2` and post-fix only singleton calls (red today).
6. **B = 2 left-padded characterization** (§3, T1): recorded result, `xfail(strict=True)` iff it diverges.
7. **P401:** the warm-session lazy-embedding test primes absolute positions as production does; a new deterministic test: an
   unprimed warm suffix call raises (red today: it silently reads garbage). Positive matrix (round 2 T8) — each must NOT
   raise and must keep today's positions bitwise: a 2-D full-prompt buffer sliced at a warm offset; a 3-D mRoPE full-prompt
   buffer (ellipsis slice, `shape[-1]`); equal-length warm block-local positions; the Qwen4 speculative-verify call (block-local
   `[B, L]` on a non-empty cache); the per-row batched-offset path; APC and canonical prefill (primed).
8. **Regression:** the Qwen4Exp block-2 / sparse-boundary exactness test; the existing suites.
9. **Hygiene (T7):** the pinned formatting hooks (black / isort / autoflake per pre-commit) on touched files; `pytest
   --collect-only` counts before and after match the expected additions; the phase-2 harness `PRODUCTION` pin moves to the fix
   commit (its pin test updated).

## 5. Sequencing and re-certification

- **No GPU overlap (T4):** while any GPU run is live, only implementation, CPU and static checks; Metal fixture tests, suites
  and audits run only on an idle box. **Smoke 8 (`3a92943d`) is CONTAMINATED as timing / memory evidence** (round 2 T4): the
  lead ran CPU-load probes for P401 and one ≈ 30 s tiny-fixture Metal check during it; its timing is never cited (interference
  is not directionally guaranteed). Its correctness gate is unaffected (separate processes share no state; its E1c / E2 / E7b
  verdicts match smokes 6 / 7 on the same tuple). The new-pin smokes of §5 supersede it; no old-pin rerun.
- Build in a NEW worktree / branch `p400-tq-width2` off `p369-mtp`; tests with `PYTHONPATH=<new worktree>` so the production
  tree under test is the new one; the P369 worktree is not touched while its run is live.
- Gate: red → green on §4; fork suite 0 failed twice with identical skips; eight audits green; production diff = exactly the
  `_attention` change + the P401 check (+ markers); Cursor code review (≤ 3 rounds); operator approval of the production change.
- **Re-pin and re-certify:**
  1. P369 phase 2 for `Qwen3.8-27B-mlx-uniform-4bit` on the new pin: harness fix first (its TurboQuant smoke positives
     `tq_norm` / `old_prefix_k` never fired — leaf detection), then smoke + full (≈ 2.4 h + 27 min).
  2. `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (T3): its full-run evidence on `4e6d0e03` carries over ONLY if that run's
     per-request telemetry shows `verify_blocks_per_query == 0` on every ON request (no fallback block can have reached the
     changed branch) — then a regression smoke on the new pin; otherwise its full phase 2 reruns (or an explicit operator waiver
     backed by targeted fallback-width-2 correctness + performance evidence).
  3. **Performance (T6, pre-registered):** a width-2-heavy probe — the deployed tuple of `Qwen3.8-27B-mlx-uniform-4bit`
     (TurboQuant 4-bit) and of `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (native16) with the MTP block forced to 2, a fixed
     8,192-token prefix and 256 decoded tokens, fixed seeds; old pin vs new pin, order-balanced (ABBA), 3 warmup + 10 measured
     repetitions per arm on an idle box at 140 W, ≥ 10 min idle between arms (AGENTS.md). Per measured repetition (round 3
     T10): run and synchronize the identical prefill, `mx.reset_peak_memory()`, run and synchronize all 256 decoded tokens,
     then record the DECODE-PHASE peak (`mx.get_peak_memory`) and decode tok/s. ABBA = two legs per arm, each 3 warmup + 5
     measured; the 10 measured repetitions of an arm are pooled across its two legs. Statistic per arm: the median of the 10
     (decode tok/s; decode-phase peak), with the per-arm maximum peak also reported. **Bounds:** median decode tok/s regression
     ≤ 3 % and median decode-phase peak increase ≤ 1 % (> either → back to the operator with the numbers); the regression smokes only confirm, never decide; the
     end-to-end speed is re-measured by M6d.
  4. Then the fork main merge + submodule bump (suites in both repos) → M6d re-certification on real router chains for both
     picks (≥ 1.3× speed, ±5 pp quality; own plan, Cursor review, operator GPU go) → MTP-ON restore (C177 lines, CERTIFIED
     notes, client-config audit).

## 6. Acceptance

§4 red → green; suites ×2 0 failed, identical skips; audits green; production diff exactly §3; Cursor code review CLEARED (or
the operator's ruling after round 3); `Qwen3.8-27B-mlx-uniform-4bit` phase-2 smoke then full run E1c PASS with C1 identical;
§5.2 carry-over decided on telemetry; §5.3 performance within the bound.

## 7. Operator decisions

(1) Approve this plan (A + the P401 hardening bundled, EpiCache excluded → P402). (2) The §5.3 performance bounds (lead
proposal: ≤ 3 % median decode tok/s, ≤ 1 % peak memory).
