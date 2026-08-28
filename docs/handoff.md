# Handoff — 2026-08-27 night (M9 STARTED, go pilot IN FLIGHT; M12 d64k block complete; 14 commits PUSHED)

Single box (M5 Max 64 GB). **A RUN IS LIVE: M9 go pilot on `Qwen3.8-27B-mlx-uniform-4bit`**
(nohup'd `run_opencode_probe.py`, launched ~22:02) — resuming session must CHECK IT FIRST:

- Driver PID was 26948 (`pgrep -f run_opencode_probe`); log
  `$STACK_WORKDIR/m9/pilot_q38_go.log`; rows
  `$STACK_WORKDIR/m9/Qwen3.8-27B-mlx-uniform-4bit.opencode_go.jsonl` (5 items:
  alphametics,beer-song,book-store,bottle-song,bowling — the O39 go set's first five).
  Sessions are progress-gated (tick 300 s, ceiling 3600 s) so the pilot self-bounds ≤ ~1.5 h;
  waiters from the launching session DIED WITH IT — poll the PID/log, nothing will notify you.
- **M9 plan (operator "push and proceed", 2026-08-27 — supersedes C21's replication gate):**
  roster = winners + `Qwen3.8-27B-mlx-uniform-4bit`; pairing-first order: (1) this pilot →
  full 22-item go leg (O39 item set, pairs vs both winners' existing
  `$STACK_WORKDIR/o39/*.opencode_go.jsonl` arms), (2) python leg on the M3 22-item set (pairs
  vs `benchmark/results/*/opencode.jsonl`), (3) rust/java/javascript draws — NOT yet designed,
  needs a seeded-draw rule decision. Protocol per O39: pinned opencode 1.18.15
  (`$STACK_WORKDIR/o39/opencode-1.18.15` on PATH), TMPDIR `$STACK_WORKDIR/scratch/octmp`
  (output-determining!), MLX_SERVE_CONFIG at the draft-stripped overlay, draft-OFF verified at
  worker, `--pure`.
- ⚠️ **UNCOMMITTED + not-yet-durable:** `benchmark/opencode_bench.json` hand-edit adds
  `Qwen3.8-27B-mlx-uniform-4bit` (it was missing — no registry `presentation` block → configgen
  never emitted it; first pilot attempt failed instantly rc=1 on the unknown model). The edit
  is DEPLOYED to the live `~/.config/opencode/opencode.json` (which is the bench config — the
  daily config backup is `$STACK_WORKDIR/opencode.json.probe-backup`). Durable fix at the next
  idle boundary: registry `presentation: role: candidate` (`NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` precedent) → configgen
  re-emit → verify it reproduces the hand-edit → regenerate the draft-OFF overlay → commit
  registry + emitted config together. Never mid-run.

## THE HEADLINE

**M12 coding-at-depth ran a COMPLETE d64k block: 6 n=50 arms (humanevalplus + mbppplus ×
3 models) at 65,536-token padded prompts, seed-0 prefix, deployed tunes, probe-timeout 9600 s
pinned, all graded, all committed.** NO depth cliff on any model; ALL SIX pairwise compares
INCONCLUSIVE at n=50 (MDE ±18pp):

| d64k n=50 | hep `acc`/`strict` | mbpp `acc`/`strict` | conv (hep/mbpp) | wall both |
|---|---|---|---|---|
| `Qwen3.8-27B-mlx-uniform-4bit` @t0.6 | 92.0 / 92.0 | 80.0 / 80.0 | 100% / 98% | 11.9 h |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` @t0.3 | 88.0 / 88.0 | 78.0 / 78.0 | 100% / 100% | 6.1 h |
| `Ornith-1.0-35B-mlx-uniform-4bit` @t0.4 | 88.0 / 86.0 | 76.0 / 76.0 | 98% / 98% | 2.6 h |

**The challenger leads all six point estimates** — first axis in the campaign where the
`Qwen3.8-27B` family has led <!-- allow-shorthand -->, and the axis its outside reputation was earned on — but
nothing resolves at n=50 (628 matched items needed), so this is DIRECTION, not a verdict, and
the B pick stands. It pays with time: 2–4× the wall-clock, 3–8× the completion tokens. Runaway
tax changed SHAPE at depth: worst items converge but cost 30–45 min each. **Truncation-forfeit
is MODEL-specific, not item-intrinsic**: `Mbpp/306` budget-hit on
`Ornith-1.0-35B-mlx-uniform-4bit` while both qwen3_5-family models converged on it; `Mbpp/593`
did the reverse on the challenger only. Data: `e2812e5`, `4fd28ad`, `fc35b6c`, `4da55dc`,
`5a20061`, `4dd0356`. Dated entry: campaign-results 2026-08-27 (late).

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

1. **M12 continuation**: deeper rungs (d128k+ — mind the `0.8 × (cap − prompt)` clamp window;
   at d128k the resolved budget starts shrinking) and pooling for power; the six d64k arms
   pair by construction (seed-0 prefix). A d128k block costs ~25 h at observed rates — worth
   an operator scope call against M9 first.
2. **M9 opencode Run C** (multi-language agentic) — the other differentiating axis; grading
   container validated (H2). Operator framing 2026-08-26: the `Qwen3.8-27B` family's missing <!-- allow-shorthand -->
   evidence lives on exactly these axes.
3. C30 (session-variance bound) now has the five same-model sessions PLUS three fresh seeded
   arms as material; C31 unchanged.

## Standing state

- **PUSHED through `027dd38`** (2026-08-27, operator-approved). Local-only since: the
  `benchmark/opencode_bench.json` hand-edit above (uncommitted by design until the configgen
  route lands) and this handoff update.
- Working tree: intentional `main_models.yaml` local overrides (NEVER commit) + older
  untracked m23-era result files + `transcript.md`.
- Bench-router invariants unchanged AND now enforced: draft-stripped overlay
  (`$STACK_WORKDIR/m6b/bench_overlay_draft_off.yaml`) + `MLX_VLM_CACHE_SESSION_MAX=2` + APC
  absent, verified at the worker; C35 makes the DRIVER carry `MLX_SERVE_CONFIG` too, and the
  tripwire refuses on divergence.
- Open operator items: C30, C31; M9 rust/java/javascript draw rule needs a design decision
  before those legs run. Next O/C number: **C36**.

**Order of resumption: this file → `docs/PLAN.md` → `docs/open-questions.md`.**
