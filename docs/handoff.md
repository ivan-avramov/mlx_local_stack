# Handoff — 2026-08-29 (M26 power extension IN FLIGHT; M9+M25 closed) <!-- allow-shorthand -->

Single box (M5 Max 64 GB). **A RUN IS LIVE: M26 — second-session (s2) opencode arms**,
3 models × {python, javascript}, launched 09:40 2026-08-29 by
`$STACK_WORKDIR/m9/m26_orchestrator.py` (was pid 77840) — resuming session must CHECK IT FIRST:

- `pgrep -f m26_orchestrator`; log `$STACK_WORKDIR/m9/m26_orchestrator.log`; 5-min watch
  `$STACK_WORKDIR/m9/m26_watch.log` (nohup'd, survives); per-leg logs `m26_<model>.<lang>.log`;
  rows `$STACK_WORKDIR/m9/<model>.opencode_<lang>.s2.jsonl`. Leg order: `Qwen3.8-27B-mlx-uniform-4bit`
  (py, js) → `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` → `Ornith-1.0-35B-mlx-uniform-4bit`;
  unload+pgrep-verified between models AND at start (fresh session per model). Fail-loud:
  any leg rc≠0 aborts the orchestrator. Per-leg bound 18000 s; expect ~10–14 h total
  (done ~20:00–24:00 08-29). Session waiters DIED with the launching session — poll PID/log.
- Protocol = O39 verbatim: opencode 1.18.15 on PATH from `$STACK_WORKDIR/o39/`, TMPDIR
  `$STACK_WORKDIR/scratch/octmp`, `MLX_SERVE_CONFIG` at the 2026-08-29 draft-OFF overlay,
  deployed profile, gate 300/3600/2. Items: python = the M3 22-item set; javascript = the
  C37 draw (`$STACK_WORKDIR/m9/c37_draws.json`).
- **Pre-registered analysis (PLAN M26)**: pool discordants over (item, session) pairs
  s1↔s1 / s2↔s2 for challenger-vs-each-rival on these two languages; s1/s2 same-model
  deltas are C30 session-variance replicates. When it lands: evaluate each leg
  (session_pass, gate-kills, completed-fails, wall), run the pooled McNemar, extract the
  C30 material, write the dated results entry, and — if the pooled split resolves — put
  the B-pick displacement question to the operator WITH the speed caveat (challenger is
  ~24 tok/s / 33-min 256K prefill, same class as the pick; MTP drafter probe-only).

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

## Operator decisions

- Scope call RESOLVED 2026-08-29: option (a) — M26 launched (this run). M12 d128k stays
  deferred behind it; M25 gate CLOSED (wash). Standing open: C30 bound (material now
  includes the coming s1/s2 replicates), C31 deferred. Nothing else blocks.

## Standing state

- **PUSHED through `df3ca80`** (operator-approved 2026-08-29; includes the C37 closure,
  M25 data + closure). Local-only: `d30035e` (M26 PLAN row) + this handoff commit. Never
  push without in-turn approval.
- Working tree: the four intentional `main_models.yaml` local-path overrides (NEVER
  commit; stash-protect during rebases) + old untracked m23-era files + `transcript.md`.
- C37 data lives in `$STACK_WORKDIR/m9/` (9 legs × jsonl+manifest); python-leg precedent
  keeps repo commits for in-repo arms only.
- Bench-router invariants: draft-OFF overlay (regenerated 2026-08-29) + SESSION_MAX=2 +
  APC absent, verified at router pid after the restart; C35 tripwire live.
- HF cache pruned to 253G (operator hand pass + delegated deletions, 2026-08-28).
- Next O/C number: **C38**.

**Order of resumption: this file → `docs/PLAN.md` → `docs/open-questions.md`.**
