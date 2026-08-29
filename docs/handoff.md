# Handoff — 2026-08-29 (M9 COMPLETE 5 languages; M25 OptiQ legs IN FLIGHT) <!-- allow-shorthand -->

Single box (M5 Max 64 GB). **A RUN IS LIVE: M25 — `Qwen3.8-27B-OptiQ-4.5bpw-mixed`
paired opencode legs** (python on the M3 22-item set, then go on the O39 22-item set),
launched ~04:30 2026-08-29 by orchestrator `$STACK_WORKDIR/m9/m25_orchestrator.py`:

- Driver `pgrep -f m25_orchestrator` (was pid 75079); log `$STACK_WORKDIR/m9/m25_orchestrator.log`;
  watch `$STACK_WORKDIR/m9/m25_watch.log`; per-leg logs `m25_Qwen3.8-27B-OptiQ-4.5bpw-mixed.<lang>.log`.
  Rows: python → `benchmark/results/Qwen3.8-27B-OptiQ-4.5bpw-mixed/opencode.jsonl` (in-repo),
  go → `$STACK_WORKDIR/m9/Qwen3.8-27B-OptiQ-4.5bpw-mixed.opencode_go.jsonl`. Fail-loud
  (rc≠0 aborts), per-leg 18000 s bound, expect ~5–6 h total. Waiters die with the launching
  session — poll the PID/log on resume.
- Runs at the recipe's screened **t0.6** (registry updated from checkpoint-default 1.0 in
  `52acc22` — read the commit before questioning the tune). Router was restarted at the
  idle boundary on the REGENERATED overlay (2026-08-29 header; SESSION_MAX=2 + APC-absent
  verified on pid); the regenerated carrier is deployed to the live
  `~/.config/opencode/opencode.json` (daily backup remains `$STACK_WORKDIR/opencode.json.probe-backup`).
- When it lands: evaluate both legs (session_pass, gate-kills, completed-fails, wall),
  pair vs `Qwen3.8-27B-mlx-uniform-4bit` + winners (same items/protocol by construction),
  then the **gated second-variant decision** (PLAN M25): beat-uniform → OptiQ ~6bpw rung <!-- allow-shorthand -->
  / official `mlx-community/Qwen3.8-27B-OptiQ-4bit` / D8 DWQ activate; wash → no more
  quant variants (M21 int8 stays the causal stall-tax test).

## THE HEADLINE — M9 IS COMPLETE (5 languages × 3 models, C37 block closed 04:17)

Totals over 110 paired items: **`Qwen3.8-27B-mlx-uniform-4bit` 80/110** (wins python 20,
go 16, javascript 19) vs `Ornith-1.0-35B-mlx-uniform-4bit` 71/110 (wins rust 17) vs
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` 69/110 (java 13). Pooled discordants: challenger vs
pick **24:13 p=.099**; vs runner-up 20:11 p=.15; winners even (18:20). **NOTHING survives
Holm across the 10-test family** — the python 8:0 (p=.0078) misses the .005 rung, and rust
flips AGAINST the challenger (3:5 vs pick, 0:4 vs runner-up). Mechanism: qwen3_5-family <!-- allow-shorthand -->
models fail SLOW (stall-kills, 600 s each), `Ornith-1.0-35B-mlx-uniform-4bit` fails
FAST-AND-WRONG (16 completed-fails java+js, legs 1–2 h vs ~3 h). Full tables:
campaign-results 2026-08-29; mechanics: lab-notebook 2026-08-29.

**Standing read: the challenger leads the point estimate on BOTH differentiating axes
(M12 depth, M9 multi-language) with zero Holm-surviving wins. The B pick stands on the
rules; the direction keeps accumulating.** Cheapest power move: a second session per arm
on python+javascript (~4 h/model, doubles pooled discordants, doubles as C30 replicates).

## Operator decisions now ripe

1. **Post-M9 scope call**: (a) power extension (second sessions, above), (b) M12 d128k
   (~25 h, answers depth-cliff not differentiation), (c) neither — proceed to
   consolidation. Session recommendation: (a) before (b).
2. M25 second-variant gate — auto-resolves when the in-flight legs land.
3. Standing: C30 bound (driver-side, material keeps growing), C31 deferred.

## Standing state

- **PUSHED through `9bdd444`**; rebased onto the operator's `5f85ef6` (searxng) 2026-08-28.
  Local-only since: the 2026-08-29 docs commit(s) for the C37 closure. Never push without
  in-turn approval.
- Working tree: the four intentional `main_models.yaml` local-path overrides (NEVER
  commit; stash-protect during rebases) + old untracked m23-era files + `transcript.md`.
- C37 data lives in `$STACK_WORKDIR/m9/` (9 legs × jsonl+manifest); python-leg precedent
  keeps repo commits for in-repo arms only.
- Bench-router invariants: draft-OFF overlay (regenerated 2026-08-29) + SESSION_MAX=2 +
  APC absent, verified at router pid after the restart; C35 tripwire live.
- HF cache pruned to 253G (operator hand pass + delegated deletions, 2026-08-28).
- Next O/C number: **C38**.

**Order of resumption: this file → `docs/PLAN.md` → `docs/open-questions.md`.**
