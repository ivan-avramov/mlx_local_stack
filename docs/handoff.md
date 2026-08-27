# Handoff — 2026-08-27 (M12 first depth block COMPLETE, three arms; C34+C35 fixed; box IDLE)

Single box (M5 Max 64 GB). **NOTHING RUNNING — no worker, no watchers, no drivers, port 8000
router up but model UNLOADED** (verified by `pgrep` after the last unload).

## THE HEADLINE

**M12 coding-at-depth ran its first full block: three n=50 arms at d64k (65,536-token padded
prompts, seed-0 prefix, deployed tunes, probe-timeout 9600 s pinned), all graded, all
committed.** NO depth cliff on any model; all pairwise compares INCONCLUSIVE at n=50 (MDE
±18pp):

| d64k n=50 | `acc` | `acc_strict@81920` | conv | wall |
|---|---|---|---|---|
| `Qwen3.8-27B-mlx-uniform-4bit` @t0.6 | 92.0 | 92.0 | 100% | 5.0 h |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` @t0.3 | 88.0 | 88.0 | 100% | 3.2 h |
| `Ornith-1.0-35B-mlx-uniform-4bit` @t0.4 | 88.0 | 86.0 | 98% | 1.4 h |

Challenger leads the point estimate (−4.0pp vs pick, CI [−14,+6]) on the axis its outside
reputation was earned on; runaway items `HumanEval/32`/`/146` CONVERGED on all models (the
zero-runaway pattern of seeded post-C26 sessions continues); the pick stays 3× terser and
1.6× faster than the challenger; `Ornith-1.0-35B-mlx-uniform-4bit` keeps its ~2pp truncation
forfeit at depth (`HumanEval/154` budget-hit). Data: `e2812e5`, `4fd28ad`, `fc35b6c`. Dated
entry: campaign-results 2026-08-27.

## Instrument fixes this session (both TDD, suite 1230/0 green)

- **C34 FIXED** (`dcf9f28`): tune-suffixed `*_samples.jsonl` evalplus sidecars no longer enter
  scoreboard largest-n selection (they shadowed graded cells as `164/378 ungraded`). Re-emit
  surfaced 15 graded cells incl. both winners' n=100 hep/mbpp; spliced with caveats (largest-n
  also surfaces the quarantined `t0.5prod` arms and the INVALIDATED m23 arms — presenter has
  no row-quality concept; changing selection needs its own proposal).
- **C35 FIXED** (`d875646`): provenance used to read `draft_kind` from the repo registry while
  the bench worker served the draft-stripped overlay — the first bench run of the pick after
  its MTP certification got stamped `mtp` while verifiably serving draft-OFF (caught by the
  provenance suite). Now: `paths.registry_path()` honors `MLX_SERVE_CONFIG`, and
  `registry_draft()` cross-checks the live worker cmdline (observed mismatch REFUSES the run;
  match stamps `registry+worker`). Poisoned pilot rows deleted (sizing preserved in PLAN M12).
  **NEW STANDING RULE: bench DRIVERS launch with `MLX_SERVE_CONFIG` pointed at the
  draft-stripped overlay, same as the router.**

## Other completions (2026-08-26 evening → 08-27)

- **Drafter uploaded** (C33 addendum, operator-reversed item 2):
  `caslca/Qwen3.8-27B-mlx-uniform-4bit-mtp-drafter` public, PROBE-ONLY card (1.58×/1.46× @
  75.8/68.3% acceptance, no quality OFAT); the certified
  `caslca/Qwen3.6-27B-Opus-Distill-OptiQ-4bit-mtp-drafter` got its missing card (M6b numbers);
  trunk card cross-links. (`53e3d82`)
- **M24 is DONE** — audit found its "remaining" provenance work already landed 2026-08-24
  (`de2d6d8`); PLAN row corrected. With C31 (no low arm, medium deferred), nothing left to run.
- M23-closure narrative sweep: campaign-results carried NO m23-era misreadings; dated closure
  section + m23c grades added (`8ed1fc9`); model-ledger was already re-headed IDENTITY.

## NEXT SESSION

1. **M12 continuation** (the depth block wants power and breadth): mbppplus at d64k, deeper
   rungs (d128k+ — mind the thinking-budget clamp window), and pooling; the three d64k arms
   pair by construction (seed-0 prefix).
2. **M9 opencode Run C** (multi-language agentic) — the other differentiating axis; grading
   container validated (H2). Operator framing 2026-08-26: the `Qwen3.8-27B` family's missing <!-- allow-shorthand -->
   evidence lives on exactly these axes.
3. C30 (session-variance bound) now has the five same-model sessions PLUS three fresh seeded
   arms as material; C31 unchanged.

## Standing state

- **UNPUSHED: everything after `f289a76`** (9 commits: `53e3d82`…`fc35b6c` — drafter docs, C34
  fix, C35 fix, three data commits, docs). Push only on explicit in-turn approval.
- Working tree: intentional `main_models.yaml` local overrides (NEVER commit) + older
  untracked m23-era result files + `transcript.md`.
- Bench-router invariants unchanged AND now enforced: draft-stripped overlay
  (`$STACK_WORKDIR/m6b/bench_overlay_draft_off.yaml`) + `MLX_VLM_CACHE_SESSION_MAX=2` + APC
  absent, verified at the worker; C35 makes the DRIVER carry `MLX_SERVE_CONFIG` too, and the
  tripwire refuses on divergence.
- Open operator items: C30, C31. Next O/C number: **C36**.

**Order of resumption: this file → `docs/PLAN.md` → `docs/open-questions.md`.**
