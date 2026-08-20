# Handoff — rewritten 2026-08-20 ~00:15 (pre-compaction checkpoint, session continuing)

Single box (M5 Max 64 GB). Stack pushed through `549f1e8`; local-only commits after: `9f34887`
(incumbent hep t0.3 arm). Fork pushed through `d06ed84e` (M14); F1 branch `sync/upstream-v0.6.15`
at `c1975b4c` (8/8 parity green, 93/93 test files) awaits post-D10 landing. Intentional dirt:
`main_models.yaml` (six candidate entries now — three `Qwen3.8-27B` recipes + three distill conversions with <!-- allow-shorthand -->
$HOME-local hf_paths) + live tune-stamped jsonls.

## Live right now

- **`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` mbppplus t0.3 5-item pilot** (fresh-cap-262144 arms
  for the head-to-head; hep arm DONE n=50, committed `9f34887`). Waiter armed → on completion:
  size and launch **mbppplus n=50 (`--tune t0.3`)** → morning: grade the pair (docker) →
  `compare --models Qwen3.6-27B-Opus-Distill-OptiQ-4bit@t0.3,Qwen3.8-27B-OptiQ-4.5bpw-mixed@t0.6
  --benches humanevalplus,mbppplus --intersect` = the FIRST admissible head-to-head, plus
  distill-vs-base paired reads (M15/M16 rungs vs `Qwen3.8-27B-mlx-uniform-4bit@t0.6`).
- Campaign lean router UP (:8000, MLX_VLM_CACHE_SESSION_MAX=2, APC absent, suffix off).

## Today's results (2026-08-19; details in notebook/ledger/queue)

1. **Stage-2 CLOSED for the `Qwen3.8-27B` family** <!-- allow-shorthand -->: acc_strict@81920
   uniform 84/76 vs OptiQ-mixed 84/80 (hep/mbpp, n=50, t0.6/xhigh per O33); within-family paired
   verdicts INCONCLUSIVE (±19pp MDE); runaway split 9-vs-2 DNFs → **representative =
   `Qwen3.8-27B-OptiQ-4.5bpw-mixed`**.
2. **Runaway tax is CROSS-FAMILY**: the incumbent's fresh hep arm (n=50, t0.3, cap 262144) has
   2 timeout-DNFs incl. `HumanEval/32` — the same item `Qwen3.8-27B-mlx-uniform-4bit` DNF'd.
   Rate-matched to the challenger (2/50). Fold into the ledger with the morning verdicts.
3. **M6a CLOSED: STOP (0.99×)** on `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (engagement proven by
   ON/OFF textual divergence); `Qwen3.8-27B-OptiQ-4.5bpw-mixed` probe inconclusive-by-meander;
   family-level close. M6b not triggered. **Negative control caught a fork defect**: missing MTP
   sidecar silently serves plain decode (F2 queued — fail-loud fix, ride the F1 landing).
4. **M15/M16/M17 Stage-0+1 in one evening**: conversions real (8-s walls verified by working
   models), all rungs conv 15/15, ZERO DNFs; pass@1 `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`
   **1.00**, `Qwen3.8-27B-Opus-Distill-v2-mlx-uniform-4bit` 0.867 (max 734 tok — tightest traces
   in corpus), `Qwen3.6-35B-A3B-Fable-5-Distill-mlx-uniform-4bit` **1.00** at ~72 tok/s.
   Operator's distillation hypothesis holding strongly. Next: Stage-2 screens vs the family
   representative; M17 also NVSY-relevant someday (see below).
5. **Harness fixes shipped (TDD)**: `compare` gained `Model@tune` addressing (Stage-2 verdicts
   were unaddressable without it); evalplus grading REUSES fresh eval_results (docker eval is
   flaky under rosetta — crash/hang/success on identical input; the hang sat on a PADDING dummy
   `Mbpp/255`; deleting good results to re-roll destroyed the same artifact 3×). Plus earlier:
   test_bfcl import fix (re-armed the M18-critical assertions), modelnames hook exempts result-row
   jsonl (model output ≠ prose), manifests must be PII-sanitized ($HOME) when hf_path is local.
6. **NVSY UNTRACKED** (operator): S1 shelved, O32 closed, `docs/switchyard-plan.md` kept for a
   post-campaign revisit. **Open-questions queue is EMPTY.**

## Queue after the incumbent pair (GPU-serial)

Stage-2 screens for the three new distill conversions <!-- allow-shorthand --> (paired vs representative, n≈30–50) → M3/M4 (opencode runs) → M5 DNF
re-runs (now includes the fresh-arm scope) → M18 (first BFCL) → M7 → D10 submodule bump
(`ab5273f`+`07ed59e`+M14 `d06ed84e`, features off) → F1 landing + F2 → M11/M12 → D11 flip
(cards) once Stage-2 numbers finalize → D6 enablement probe (script ready) → M14 `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` MTP
probe (post-D10; `mtp_probe.py` ready, sidecar at `$STACK_WORKDIR/scratch/m14/`).

## Standing traps refreshed today

Verify every commit with `git log` (rtk prints "ok N files changed" even when the commit-msg hook
REJECTS); never overlap two grades of one arm (container-name collision); a watcher without a
timeout is not a watcher (3-h hung container); `bench_watch.py` needs cwd=benchmark AND
PYTHONPATH=benchmark (silent nohup death otherwise — verify process + output file after EVERY
detached launch); cwd resets between tool calls — use absolute paths; probe workers at deployed
sampling outrun "1–3K token" item estimates (xhigh thinking) — size request timeouts accordingly.

**Order of resumption if context is lost: this file → `docs/PLAN.md` → `docs/work-queue.json` →
`$STACK_WORKDIR/status/` (live runs).**
