# Handoff — 2026-08-29 (M9 + M25 COMPLETE; NO run live; operator owes the scope call) <!-- allow-shorthand -->

Single box (M5 Max 64 GB). **No run is in flight.** Last resident model:
`Qwen3.8-27B-OptiQ-4.5bpw-mixed` (router :8000 up on the 2026-08-29 overlay,
SESSION_MAX=2, APC absent — verified at pid). Unload before serving anything else.

## M25 CLOSED (2026-08-29 ~08:00): recipe choice is a WASH — gate shut

`Qwen3.8-27B-OptiQ-4.5bpw-mixed` at screened t0.6: python 18/22, go 16/22; vs
`Qwen3.8-27B-mlx-uniform-4bit` pooled discordant 1:3 p=.625, equivalent stalls and wall.
Pre-registered verdict: NO further quant variants for the family (6bpw / official
`mlx-community/Qwen3.8-27B-OptiQ-4bit` / D8 DWQ stay dormant; M21 int8 = the causal test).
Secondary: it also beats `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` directionally both legs
(7:1, 6:2) — two quants of one base behaving identically makes the challenger direction a
BASE-MODEL property. Entries: campaign-results 2026-08-29 (later); PLAN M25. Python rows
committed `75bdf65`; go rows `$STACK_WORKDIR/m9/`.

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

- **PUSHED through `9bdd444`** (then rebased onto the operator's `5f85ef6`). Local-only:
  `53e1962` (C37 closure docs), `75bdf65` (M25 python data), + the M25-closure docs
  commit. Never push without in-turn approval.
- Working tree: the four intentional `main_models.yaml` local-path overrides (NEVER
  commit; stash-protect during rebases) + old untracked m23-era files + `transcript.md`.
- C37 data lives in `$STACK_WORKDIR/m9/` (9 legs × jsonl+manifest); python-leg precedent
  keeps repo commits for in-repo arms only.
- Bench-router invariants: draft-OFF overlay (regenerated 2026-08-29) + SESSION_MAX=2 +
  APC absent, verified at router pid after the restart; C35 tripwire live.
- HF cache pruned to 253G (operator hand pass + delegated deletions, 2026-08-28).
- Next O/C number: **C38**.

**Order of resumption: this file → `docs/PLAN.md` → `docs/open-questions.md`.**
