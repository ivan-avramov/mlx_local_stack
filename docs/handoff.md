# Handoff — 2026-10-16: M64 plan agreed + ruled (C165); c144-base attempt 2 LIVE on m5max-128; next: M64 spec, G1, P311, P340

THE one handoff. Read this, then `docs/open-questions.md` (top entries: C165, G1, G2, P340, C164, P309, C163–C159,
P299, P308, P288, P306, C157), `docs/reviews/m64-plan-2026-10-16/plan_final.md` (the agreed M64 plan),
`docs/campaign-results.md` (2026-10-13 P223, 2026-10-14 M63), `docs/PLAN.md` (M62–M64 rows), `README.md` B ladder.

## State of the world

- **Two boxes.** `m5max` (64 GB: codex CLI) and `m5max-128` (128 GB, chain box: cursor-agent). Quality rows pair
  across boxes (C153); latency/thermal/capacity never. **Cold reviewer: Cursor `gpt-5.6-sol-high` on m5max-128 only
  (operator 2026-10-16: "no more codex checks")** — `cursor-agent -p --output-format text --model gpt-5.6-sol-high
  --mode plan --sandbox enabled --force --trust --workspace <repo> "<prompt>"`; re-run until the report contains a
  verdict line.
- **Branches.** `origin/main` = the 2026-10-15 sync merge (`170af9c0`). `m64-plan-review` (pushed) = main + C164 +
  the plan review + C165 docs; fast-forward main to it when approved. The m5max-128 MAIN CHECKOUT is deliberately
  still on its pre-merge `main` (probe `d4319705…`) because c144-base runs from it: do not change it until the chain
  exits; build in `$STACK_WORKDIR/worktrees/` (sync worktree `$STACK_WORKDIR/worktrees/sync-1015` on
  `m64-plan-review`).
- **LIVE (m5max-128, 2026-10-16): c144-base attempt 2** = `chain s2 reload --probe-code-sha
  d431970599f696d4b79c76e1923524a6a4f982e7f60f023d37fa5e16c36172ea --out-root $STACK_WORKDIR/c144-base` (scratch
  launcher with `$HOME/.orbstack/bin` on PATH), ≈10 h. s1 (both picks, validated 2026-10-15) stays in the out-root.
  Attempt 1 (aborted 05:15Z, guard residual pid 89820) is archived with a sha256 manifest (2,111 files, incl. a copy of
  s1 and the 9 transcript roots) at `$STACK_WORKDIR/c144-base.archive/attempt1-guard-residual/`. Status per C165:
  descriptive / power-input evidence, NOT the M64 baseline. Never edit runner/probe/scoring files in the main checkout
  or run the full suite until it exits.
- **Rulings 2026-10-16:** C164 (P310 superseded by C165; P311 identity split approved; P314 no filler chains);
  C165 (E1 epochs, E2 spec requirements, G1 approved; web allowed per arm + P201 audit; PLAN M64 amended; R1 resumed).
- **Done 2026-10-15/16:** P299 + C163 (m5max) merged with this box's C157, P306, P288/P308; P309 (retry never re-audits
  a resolved error; unreadable auditor version fails before append); smoke PASSED on `d4319705…`.
- **Known weakness on main:** the C157/P306 guard drops recorded unreadable obligations once a process reads fine
  (narrow false-clear) — fixed by G1.
- **Not pushed to main:** `m64-plan-review` (push approval needed for main). Parked branches (keep, no deletions yet):
  `p297-uncertain-gone`, `c152-alloc-tool-scope-wip`, `sync-upstream-1015`.

## Next work, in order

1. **Watch c144-base attempt 2.** On rc 0: copy rows to `benchmark/results/<model>/…c144base…`, report (P223 repeat,
   descriptive; discordance estimates for the M64 power simulation), README evidence labelled descriptive.
2. **M64 spec** (`docs/specs/m64-scaffold-arms.md`, DRAFT 2026-10-16, C165 2a/2b applied) → Cursor cold review
   rounds (`docs/reviews/m64-spec/`) → operator go for the BUILD. Pi facts (source-read 2026-10-15, earendil-works/pi 4954d76) and the adapter-pattern map
   are in the review packet's context; attach dated URLs/package metadata.
3. **G1** (approved) and **P340** (A4 logs/TMPDIR under the OFF arm's out-root): test-first in a worktree, cold
   review, merge after the chain.
4. **P311** identity split (approved C164): proposal + test-first + cold review in a worktree.
5. After the chain: fast-forward the main checkout to `m64-plan-review`/main, full suite, P223/M63 reports unchanged,
   push on approval.

## Rules learned (2026-10-11 → 16)

- Never edit runner/probe/scoring files in the main checkout while a chain runs; build in worktrees. Never run the
  full suite under a live chain. Suite: from `benchmark/`, `../.venv-bench/bin/python -m pytest bench/tests -q` (~11 min).
- Fetch and diff before syncing during a live chain; merge in a worktree.
- Harness versions are not pinned for long: decision epochs (C165/E1) — one immutable snapshot per decision family,
  move to latest between families through the adoption gate; cross-epoch results are descriptive.
- Web access is an expected capability in agentic benches (C141); cheating is caught post hoc by the P201 audit.
- Archive a failed chain attempt with a sha256 manifest BEFORE moving anything (the runner rewrites `chain.json`).
- Launch chains with a command line that names no watched process. After a reboot: `docker info` before Go legs.
- A cold-review prompt names the commit hash; give reviewers the code and earlier rounds, not the conclusion.
- Pushes need explicit operator approval each time.

Next decision id C166; discussion ids continue from P341; open G-items G1, G2.
