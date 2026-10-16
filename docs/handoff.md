# Handoff — 2026-10-16 (evening): c144-base DONE (pick 2 86/86, pick 1 84/86, descriptive); M64 spec final draft awaiting BUILD go; main fast-forwarded (merged identity `ebcfe6fb…`)

THE one handoff. Read this, then `docs/open-questions.md` (top entries: C165, G1, G2, P340, C164, P309, C163–C159,
P299, P308, P288, P306, C157), `docs/reviews/m64-plan-2026-10-16/plan_final.md` (the agreed M64 plan),
`docs/campaign-results.md` (2026-10-13 P223, 2026-10-14 M63), `docs/PLAN.md` (M62–M64 rows), `README.md` B ladder.

## State of the world

- **Two boxes.** `m5max` (64 GB: codex CLI) and `m5max-128` (128 GB, chain box: cursor-agent). Quality rows pair
  across boxes (C153); latency/thermal/capacity never. **Cold reviewer: Cursor `gpt-5.6-sol-high` on m5max-128 only
  (operator 2026-10-16: "no more codex checks")** — `cursor-agent -p --output-format text --model gpt-5.6-sol-high
  --mode plan --sandbox enabled --force --trust --workspace <repo> "<prompt>"`; re-run until the report contains a
  verdict line.
- **Branches.** Local `main` = `m64-plan-review` (fast-forwarded 2026-10-16 after the chain) = `origin/main` + C164,
  C165, the plan and spec reviews, P309; **not pushed to `origin/main` yet** (push needs the operator). The sync
  worktree `$STACK_WORKDIR/worktrees/sync-1015` (branch `m64-plan-review`) can be removed once main is pushed.
  Probe identity on main: `ebcfe6fb…`.
- **c144-base DONE (2026-10-16 14:19Z, rc 0):** rows in `benchmark/results/<model>/opencode_v2_<lang>.c144base.*`,
  report `benchmark/results/c144_base/C144BASE_REPORT.md`; pick 2 86/86, pick 1 84/86, 0 `client_inactivity`; one web
  fetch audited `generic` (Cursor `2026.10.14`). Descriptive / power-input evidence (C165). Attempt-1 archive:
  `$STACK_WORKDIR/c144-base.archive/attempt1-guard-residual/`.
- **M64 spec:** `docs/specs/m64-scaffold-arms.md` FINAL DRAFT v9 (nine Cursor rounds, `docs/reviews/m64-spec/`),
  awaiting the operator's BUILD go. D1/D2 ruled (C165 2c/2d).
- **Rulings 2026-10-16:** C164 (P310 superseded by C165; P311 identity split approved; P314 no filler chains);
  C165 (E1 epochs, E2 spec requirements, G1 approved; web allowed per arm + P201 audit; PLAN M64 amended; R1 resumed).
- **Done 2026-10-15/16:** P299 + C163 (m5max) merged with this box's C157, P306, P288/P308; P309 (retry never re-audits
  a resolved error; unreadable auditor version fails before append); smoke PASSED on `d4319705…`.
- **Known weakness on main:** the C157/P306 guard drops recorded unreadable obligations once a process reads fine
  (narrow false-clear) — fixed by G1.
- **Not pushed to main:** `m64-plan-review` (push approval needed for main). Parked branches (keep, no deletions yet):
  `p297-uncertain-gone`, `c152-alloc-tool-scope-wip`, `sync-upstream-1015`.

## Next work, in order

1. **Operator: BUILD go on the M64 spec**, push approval for main.
2. **M64 build, after the go** (spec §12): power simulation from P223 / M63 / c144-base discordance → P311, P340,
   G1 (worktrees, test-first, Cursor review) → ArmAdapter + arm-aware runner + opencode parity → mlx-vlm receipts →
   Pi adapter → dsh research + adapter → snapshot/adoption tooling → per-arm smokes → operator go for the chain.
3. **P346** (degenerate-bootstrap "equivalent" labels in reports): proposal → operator go.
4. G2 stays open (design question).

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
- Edit-then-commit scripts must stop on failure (`set -e`, Edit tool): a failed edit once produced a commit whose message
  claimed changes it did not contain (M64 spec round 8).
- Pushes need explicit operator approval each time.

Next decision id C166; discussion ids continue from P341; open G-items G1, G2.
