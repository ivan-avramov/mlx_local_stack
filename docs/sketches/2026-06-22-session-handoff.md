# Session handoff — suffix root-cause → 256K daily-driver bake-off + speed levers (2026-06-22)

## How this session started vs where it went

Started as a **single bug**: drafter-free **suffix speculative decoding is non-lossless** on
`gemma-4-26b-a4b-it-8bit` (temp=0 greedy: suffix-on 3984 tok vs suffix-off 1792 tok, different
output). It expanded into resolving that root cause, shipping the real 256K serving fixes, running
the **daily-driver bake-off** suffix-off, and prototyping two **speed levers** (MTP, EpiCache).

Two machines, **strictly one model resident per machine**: **M2** = local 68.7 GB
(`$HOME/...`, co-resident with the Claude session ~22 GB → unreliable >192 K capacity),
**M5 Max** = 64 GB target box (`ssh $REMOTE_HOST`, user `ivan`, repo `$REMOTE_REPO/../`, bare PATH
→ `export PATH=/opt/homebrew/bin:$HOME/.local/bin:$PATH`).

## 1. Resolved: suffix decoding is INHERENT bf16, not a logic bug

Proven (standalone `benchmark/diag_*.py` + codex reconcile + the decisive disambiguator): a
**full-fp32 forward with the same rollback/trim/mask code is bit-identical (KV 2e-6) and lossless
(0/140)**. The non-losslessness is bf16 batched-vs-sequential kernel numerics — MLX
`scaled_dot_product_attention` (sliding 0.0117) + MoE `gather_qmm` (0.0039) differ between the
multi-token verify and single-token decode in bf16, flipping greedy argmaxes → gemma cascades into
rambling. **Not** rollback (the earlier guess). **MTP and draft-model share the same verify
framework → same wall.** EpiCache is orthogonal. Full detail: memory `project-suffix-decoding-nonlossless`.
**Decision: park lossless-suffix; run the bake-off suffix-OFF** (all 10 registry models, committed).

## 2. Shipped + validated + pushed (the real 256K serving fixes)

- **Penalties-drop fix** (`mlx-vlm` `5a23df5`): suffix path dropped rep/presence/freq penalties;
  `_suffix_structured_fallback` now falls back to plain decode on any active processor.
- **L1 — prefill-step threading** (`mlx-vlm` `dce5178`): `_process_cached_request` + `BatchGenerator`
  didn't pass `prefill_step_size`, so generation used `DEFAULT=2048` instead of the configured 512 →
  4× QK² scratch → 256K OOM. Validated: gemma-8bit @212 K (M2) + Qwen-6bit @201 K (M5) complete, no OOM.
- **L2 — orphan-disconnect cancel** (`dce5178`): `is_disconnected()` in both `openai.py` streaming
  loops. **L2 memory-pressure eviction DEFERRED** (evidence: 4-session probe = flat RSS; the OOM was
  L1 scratch, not KV accumulation).
- Stack at `50aff5b` (suffix-off registry + diags + submodule bump to `dce5178`). Both routers synced.

## 3. Bake-off — candidate comparison (suffix-off; all axes profiled except coding)

| candidate | converge | recall (gate ≤46 GB) | 256K fit | synthetic reasoning | decode tps | verdict |
|---|---|---|---|---|---|---|
| **gemma-OptiQ-4bit** (MoE, ~4 B active) | 1.0 | 1.0 @192/224/256K (160 K=0.20 noise) | ✅ 30 GB peak (most headroom) | var-track 1.0/64K, latent 1.0/128K, **0 errors** | **24-35** | **fast daily-driver front-runner** |
| **OptiQ-distill-4bit** (dense, Opus-distill) | accurate; coding 1.0 | 1.0 (0.80@224K dip) | ✅ 42 GB peak | **over-thinks** (49 K = budget cap; coding normal 1.9 K) | 10-13 | **dense 256K reasoner — the gap-filler** |
| Qwen-6bit-UD (dense) | 1.0 | 1.0 →224 K | ❌ **192 K-capped** | effective 32 K (1 error@48K under mem pressure) | 15 | **SUPERSEDED by the distill** |
| vanilla `mlx-community` gemma-4bit | ✗ (rambles, acc 0.4) | — | — | — | — | **dropped** (quant-level non-converger) |

Key findings:
- **gemma recall is QUANT-sensitive, not architectural**: OptiQ-4bit recalls 1.0 where QAT-4bit
  was 0.6-0.8 (same MoE arch) — OptiQ protects the 5 full-attn layers.
- The conversion delivered the goal: **`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (optiq_mixed, 3.97 bpw,
  ~13-18 GB) fits FULL 256K @ ≤46 GB with recall + accuracy** — what Qwen-6bit couldn't (192 K cap).
  Built with `mlx-optiq` (`optiq convert TeichAI/Qwen3.6-27B-Claude-Opus-Reasoning-Distill-v2`).
- **Synthetic reasoning axes ceiling** (gemma aces them) → the only thing left that can separate the
  4 B-active MoE from the dense distill is **coding** (LCB / BFCL / SWE) — not yet run.

## 4. Speed levers

- **MTP self-speculative decode** — enabled end-to-end (drafter built via `split_qwen3_5_mtp` →
  `~/.cache/mlx_drafters/Qwen3.6-27B-OptiQ-4bit-mtp`; loads + "speculative decoding enabled"), then
  **measured a NET SLOWDOWN (~0.5×, ~4.7 vs ~9.3 tps)** — the 1-layer head's accept rate doesn't beat
  the verify overhead, and it's non-lossless. **Dead end; don't deploy.** Plumbing retained.
- **EpiCache** (Apple arXiv:2509.17396) — **Phase-A core implemented + 5/5 unit tests**
  (`mlx_vlm/models/epicache.py`: `EpiCacheKVCache` + gather-based `evict_to_budget`). **Integration
  pending** (the real work): block-local attention-mass scoring, the **RoPE-position-after-eviction
  fix** (kept keys keep store-time rope; query must stay at TRUE abs position, not the shrunk offset),
  the wiring (`common.py` wrap skipping RotatingKVCache/SSM + `ar.py` per-chunk hook + flag
  threading), and ≤5% validation on the needle harness. Phase B (multi-episode routing) deferred.

## 5. Loader fixes (committed this handoff) — generally useful beyond this campaign

Three small `mlx-vlm` `load_model` fixes make converted / MTP-packaged quants loadable:
- **mtp-strip**: drop `mtp.*` before strict load (the in-checkpoint MTP head; the serving model has
  no mtp submodule — the drafter is split-then-borrow). Fixes `Received 29 parameters not in model`.
- **vision-tolerance**: text-only VLM quants (mlx-optiq drops the vision tower) → load non-strict so
  the absent, never-called towers don't fail strict load.

## Proposed plan forward (next session)

1. **Coding head-to-head (decisive, do first)** — `gemma-OptiQ-4bit` vs `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`
   on LCB / BFCL / SWE (the `run_aider`/`run_bfcl`/`run_swebench` adapters; M5 has `.venv-bench`). This
   is the only axis that can separate the fast 4 B-MoE from the dense-27B distill. Resolves the
   daily-driver pick (likely: gemma-OptiQ for fast routine, distill for hard coding).
2. **EpiCache integration** — solve the RoPE-after-eviction problem first (the make-or-break), then
   wire `maybe_epicache_wrap`/per-chunk hook + flags, validate ≤5% on the needle harness. Speeds the
   256K OptiQ variants.
3. **Distill over-thinking** — confirm with n>1; consider a tighter `thinking_budget` for the distill,
   or a non-reasoning-distill variant, since it rambles reasoning to the cap (coding is fine).
4. **Decide on the loader fixes / MTP plumbing** — now committed; keep (they're benign + useful) or
   revert MTP (dead end).

## Gotchas / state for the new session

- **Routers**: launch offline-safe; M5 has no `.env` (cached models load without `HF_TOKEN`), but
  gemma-OptiQ-4bit was NOT fully cached on M5 → needed `HF_HUB_OFFLINE` unset to fetch.
- **M2 capacity unreliable >192 K** (co-resident Claude ~22 GB → memory backstop kills the subprocess).
  Run high-context capacity on the clean M5. The gate metric (`mx.get_peak_memory`) is process-local
  so it's still valid; it's total-system pressure that crashes.
- **Degraded-router gotcha**: after a crash, the router can report a model "ready" but have no live
  subprocess → requests 500. Restart the router to clear (hit firsthand).
- **M5 local-only**: `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` lives at
  `$DISTILL_MODEL_PATH` with an
  **uncommitted** registry entry in M5's `main_models.yaml` (local hf_path — do NOT commit the path
  to the shared repo). M5's submodule had the loader fixes scp'd in for validation; after pushing,
  M5 needs `git pull && git submodule update` to replace the temp copy with the committed version.
- Diag harnesses in `benchmark/diag_*.py`; the convergence/capacity/reasoning/latent runners in
  `benchmark/bench/run_*.py`; suffix is OFF on all 10 registry models.
