# Handoff — 2026-08-31 morning (M11 DONE, C40 owed; box FREE for M14) <!-- allow-shorthand -->

Single box (M5 Max 64 GB). **No run is live.** M11 finished 08:02 2026-08-31 (v4 orchestrator
`M11 ALL 4 MODELS DONE`, rc=0 every leg, errors=0 every rung). Router :8000 still serves the
draft-OFF bench overlay (`$STACK_WORKDIR/m6b/bench_overlay_draft_off.yaml`, SESSION_MAX=2,
APC absent) with the LAST worker resident: `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`
(pid 39929). **Unload it (`POST /v1/models/unload` + pgrep-verify) before any other model
work; one resident model.** The v4 watch daemon self-stops on orchestrator exit.

## M11 result (campaign-results 2026-08-31; lab-notebook 2026-08-31)

Lenient `reasoning_effective_ctx` **156K / 156K / 156K** for `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`,
`Ornith-1.0-35B-mlx-uniform-4bit`, `Qwen3.8-27B-mlx-uniform-4bit`; **16K** for
`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` (cliff at 24K = 3/5 runaways at t1.0). Every
strict dip (0.33–0.8) is ONE runaway draw of 3–5 — draw-dependent, no depth trend. Runaway
wall share 37 % / ~55 % / 89 % / 96 % — set by decode speed (2.5 h per runaway on a dense 27B
at 9 tok/s vs ~19 min on `Ornith-1.0-35B-mlx-uniform-4bit`). Reasoning depth does not separate the B menu.

## Operator decisions owed

- **C40** — the strict single-number `reasoning_effective_ctx` definition (rec: largest
  passing rung on the strict curve, with runaway rate + wall share reported separately).
  Not blocking the box queue.
- Follow-up owed before ANY ladder rerun: persist per-sample rows (score, completion_tokens,
  budget_hit) in `bench/reasoning.py` (C39). Sizing rule for budget-hitting designs: bound =
  draws × (budget ÷ floor decode), never converged-draw pace (lab-notebook 2026-08-31).
- Standing debt: the `caslca/Qwen3.8-27B-mlx-uniform-4bit-mtp-drafter` HF card still says
  PROBE-ONLY (outward-facing update, do deliberately). C31 deferred. Next O/C number: **C41**.

## THE BOX QUEUE (all operator-approved 2026-08-30) — start here

1. **M14 `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` predictor** — fork branch `nemotron-h-rollback` (`../mlx-vlm`, PUSHED;
   head `d1d57955` = `58cac341` impl + `86f352b6` verifier fixes + black; verifier verdict
   SHIP; GPU-kernel exactness is the one thing CPU tests could not cover).
   Steps: (a) `split_mtp` the downloaded BF16 source (hub
   `nvidia/NVIDIA-Nemotron-3.5-Lightning-30B-A3B-BF16` <!-- hub repo id, allow-shorthand -->, in the HF cache, MTP
   shard fetched) into an int4 sidecar dir under `$STACK_WORKDIR/scratch/m6a/` using the fork
   branch (`PYTHONPATH=../mlx-vlm`); (b) Metal load smoke: serve
   `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` with `--draft-kind mtp --draft-model <dir>`
   via the fork branch on PYTHONPATH, verify flags at the worker cmdline, one request must
   complete with non-null draft counters and coherent text; (c) `m1.mtp_probe --draft-model
   <dir>` (it starts its own router — stop :8000 first, kill by PID, verify 0 listeners)
   against the 1.3× bar; (d) on a passing smoke: merge branch → fork main, push fork, bump
   `src/mlx-vlm` in the stack (`chore(stack): bump src/mlx-vlm -> <sha>`), `git submodule
   update --force` — all pre-approved; (e) ≥1.3× → M6b/M6d-style quality OFAT n=164 →
   CERTIFIED registry flip. Note from M11: at its registry t1.0 this model runs away on 4 of
   15 reasoning draws — a temperature-ladder pass belongs before any quality OFAT.
2. **M27 `Ornith-1.0-35B-mlx-uniform-4bit` MTP transplant** — base shards 13–14/14 of hub `Qwen/Qwen3.5-35B-A3B` are in
   the HF cache; `split_mtp` (the `qwen3_5_mtp` splitter stacks MoE experts) → sidecar dir →
   load smoke → `m1.mtp_probe --draft-model` (1.3× bar) → OFAT if it clears. M28 (head
   fine-tune) gated on M27's acceptance (< ~0.8 triggers it).
3. Then M21 int8 causal test → M12 d128k cliff check (pre-registered, PLAN M12) → M17/D11.

## Standing state

- **PUSHED through `3c81c8d`**. LOCAL, not push-approved: `fc70784`, `0f48921`, and this
  session's M11 close-out commit. Never push without in-turn approval.
- Working tree: the **FIVE** intentional `main_models.yaml` local-path overrides (NEVER
  commit; clean-checkout + re-apply procedure in lab-notebook 2026-08-30 asserts all five)
  + old untracked m23-era files + untracked M6b/M6d OFAT rows under `benchmark/results/`.
  Live `~/.config/opencode/opencode.json` = BENCH carrier on :8000.
- Data: M11 `benchmark/results/<model>/reasoning.json` + `reasoning.partial.jsonl`
  (committed), logs/orchestrators `$STACK_WORKDIR/m11/`; M26 `$STACK_WORKDIR/m9/`; M6d
  `$STACK_WORKDIR/m6b/q38_*`; M6c `$STACK_WORKDIR/m6c/`; downloads `$STACK_WORKDIR/m14/`,
  `$STACK_WORKDIR/m27/`.
- Bench-router invariants: draft-OFF overlay + SESSION_MAX=2 + APC absent; C35 tripwire
  live. HF cache 253G + ~20 GB of deliberate MTP-source fetches — don't "fix" it.
- **Monitors on this box: use `/usr/bin/tail -F` and `/usr/bin/grep --line-buffered`** —
  the shell hook rewrites bare `grep` to a proxy that buffers to EOF; arm nothing without a
  known-positive self-test line (lab-notebook 2026-08-30 night).

## Closed 2026-08-30/31

M11 DONE; C39 RULED (lenient climb stood for the run, both curves reported, strict ranks);
orchestrator v3→v4 swap (12 h bound would have killed the 156K sample); M6d CERTIFIED
(`Qwen3.8-27B-mlx-uniform-4bit` `draft_kind: mtp`, 1.60×, n=164 EQUIVALENT); M6c suffix
leg CLOSED (1.20×); C38 (B menu of three); C30 bound; M26 closed unresolved (20:8 p=.036 vs
Holm .025). Bench suite GREEN (1243).

**Order of resumption: this file → `docs/PLAN.md` → `docs/open-questions.md`.**
