# Handoff — checkpointed 2026-08-18 for an operator OS upgrade + reboot

Single-box campaign (M5 Max 64GB, driver AND worker). Everything durable is committed and
pushed at `7f1f4af`; the only uncommitted file is `main_models.yaml` (INTENTIONAL dirt — the
three `Qwen3.8-27B` candidate entries <!-- allow-shorthand -->; backed up to
`$STACK_WORKDIR/main_models.yaml.pre-os-upgrade-2026-08-18`, md5 `f57077…`). Nothing was
generating at checkpoint time; no watchers or daemons were live. Git stash
`m5_bfcl_preserve` predates this session and survives in `.git` — leave it.

## Resume procedure after the reboot

1. `cd ~/ws/mlx_local_stack` — confirm `git log --oneline -1` shows `7f1f4af` and
   `git status` shows ONLY `main_models.yaml` modified (if the dirt is gone, restore from the
   workdir backup and verify by md5).
2. Restart the lean bench router when the next job needs it (no OWUI/docker for benchmarking):
   `set -a; . ./.env 2>/dev/null; set +a; MLX_SERVE_CONFIG=main_models.yaml nohup uv run mlx-serve start >logs/main_model.log 2>&1 </dev/null &` → :8000.
   Verify APC absent (`ps -Eww` on router AND worker pids) per standing rule.
3. Resume the session: `claude --continue` in the repo directory (or start fresh — this file
   plus `docs/PLAN.md` §3 is the full state).

## Where the campaign stands (2026-08-18 evening)

- **Winners unchanged**: `Ornith-1.0-35B-mlx-uniform-4bit` (B pick per repair result),
  runner-up `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`. Capacity is a GATE, not an axis
  (operator rule); ranking = quality + daily usability.
- **`Qwen3.8-27B` family**: <!-- allow-shorthand --> capacity/retrieval ladders all PASS (retrieval 1.0 through
  256K). `Qwen3.8-27B-mlx-uniform-4bit` Stage-1 PASS (t0.6, conv 15/15, pass@1 1.00).
  `Qwen3.8-27B-static-mixed-4bit` **PARKED** — Stage-1 FAIL on convergence (t0.4 rung:
  conv 13/15, two >3600s DNFs, HumanEval/146 wrong at 66K tokens; temp moves the runaway
  set rather than shrinking it). See the ledger rows for both.
- **Decode mechanism SETTLED by powermetrics probe**: kernel-internal (GPU 95% active,
  never boosts, ~21 W) — not CPU dispatch. Architecture-specific (48/64 linear-attention
  layers), not quant-specific, not runtime-wide. M6 native-MTP probe is the lever.
- **H1 reference smoke COMPLETE** (T1 seams / T2 order anchor / T3 depth anchor all
  PASSED, ~650K plan tokens, zero worker time). D9 coding-at-depth axis is validated and
  **M12 is READY** (pilot-first).
- **O31 ruled + shipped** (error rows are strict failures; corpus re-graded, comparable).
  **O15 closed by policy** (operator observed the realloc OOM firsthand; prealloc rule
  stands). **The only open question is O32** (switchyard router-system scope) — operator
  deferred, revisit when they raise it.

## Work queue (order per `docs/PLAN.md` §3 — that file is the backlog, this is a snapshot)

1. **Stage-2 paired screens** for the two `Qwen3.8-27B` passers <!-- allow-shorthand --> vs the leader on the
   guard-clean axes (humanevalplus/mbppplus, count/rate endpoints + honestly-sized pass@1).
2. **M6 native-MTP smoke** (~15 min, worker) — the decode-speed lever; serving-only,
   ±5pp OFAT gate if it works.
3. **M12 coding-at-depth pilot** (5 items at d64k on a winner; long-prompt prefill
   dominates cost — size the full run from the pilot).
4. M11 reasoning-depth ladder; opencode Runs A/B (gated on D7/opencode pinning);
   6 coding budget-hit re-runs at shipped cap; M7/M9/M10/D8 low priority.

Standing rules that bite: one resident model; full registry names everywhere (hooks
enforce); never push without an explicit ask in that turn; artifacts only under
`$STACK_WORKDIR`; `rm` is aliased interactive — use `rm -f` and verify.
