# Handoff — 2026-10-16 (late): M64 BUILD in progress (C166); G1 review NOT cleared; P311 proposal agreed-with-changes; next: M65 pilot (GPU) + G1/P311/P348 (CPU)

THE one handoff. Read this, then `docs/open-questions.md` top entries (C167, P348, P347, P346, C166, C165, G1, G2,
P340, C164, P309), `docs/specs/m64-scaffold-arms.md` (APPROVED FOR BUILD, estimation screen), `docs/PLAN.md` M64 +
M65 rows, `docs/specs/p311-identity-split.md`, `README.md` B ladder.

## State of the world

- **Box `m5max-128` (this box), idle:** no router, :8000 free, no chain. Docker (OrbStack) up; the agent shell has no
  docker on PATH — launch chains with `benchmark/chains/c147/launchers/launch_tg1.sh <out-root-name> <runner args>`
  (adds `$HOME/.orbstack/bin`; writes `driver.chain.out/.rc` under the out-root). The other box `m5max` (64 GB, codex)
  is not used by this session; a throwaway worktree `~/ws/mlx_local_stack_workdir/worktrees/review-1016` on m5max can
  be removed by the operator (`git worktree remove`).
- **Cold reviewer: Cursor `gpt-5.6-sol-high` here only** (operator: "no more codex checks"): `cursor-agent -p
  --output-format text --model gpt-5.6-sol-high --mode plan --sandbox enabled --force --trust --workspace <repo>
  "<prompt>"`; re-run until the output has a verdict line; name the commit hash.
- **Branches.** Local `main` is ahead of `origin/main` (`2ef70a67`) by the P346 + review fixes, power sim, P347, P340 +
  review fixes, G1, P311 proposal and these docs — **push needs the operator**. `m64-plan-review` (pushed) is merged
  into main; the sync worktree `$STACK_WORKDIR/worktrees/sync-1015` can be removed (`git worktree remove`) — no branch
  deletions without the operator (parked: `p297-uncertain-gone`, `c152-alloc-tool-scope-wip`, `sync-upstream-1015`,
  `m64-plan-review`).
- **Identity on main:** `probe_code_sha256` changed with G1 (proc_guard) — recompute with
  `run_opencode_probe_v2.py --print-identity` before any chain.
- **Records:** P223, M63, c144-base (`benchmark/results/c144_base/C144BASE_REPORT.md`: pick 2 86/86, pick 1 84/86,
  descriptive). Reports print "no discordance — equivalence NOT established" for collapsed intervals (P346).
- **Full suite** after the G1 commit: 4676 passed, 3 skipped, 1 xfailed.

## Rulings to keep in mind (all in open-questions)

C164 (P311 identity split approved; no filler chains), C165 (decision epochs E1; M64 spec requirements E2; G1
approved; web allowed per arm + P201 audit; 2a capability principle — each arm's normal default tools; 2b compaction
ON, retries OFF with transport failures counted as transport DNF, equal ceilings; 2c no fan-out / ask-user tools; 2d
one shared local SearXNG search via a pinned MCP server, hosted search removed), C166 (M64 BUILD go; judges = two
providers, each the box's strongest model, configured per box, never hard-coded — on this box Claude Opus via Claude
Code + Cursor `gpt-5.6-sol-high`; P346 go), P347 (M64 = estimation screen), C167 (P348 audit approved; P349 → PLAN
M65 harder corpus).

## Next work, in order

1. **M65 step 1 — headroom pilot (GPU; start it first so the GPU works while the CPU items run):** both picks, k = 1,
   predictor OFF, on the 30 polyglot Python + Go items outside `benchmark/m62/universe.json` (12 Python, 18 Go): new
   universe file (same format; run `universe_preflight` on it), own out-root (e.g. `$STACK_WORKDIR/m65-pilot`),
   `--smoke` first, the runner's `--universe`. Check whether the runner's schedule (s1/s2/reload) needs a k=1 mode — a
   runner change is a runner-file change: test-first, never with a live chain. Report strict per pick vs tg1, nonconv
   kinds, tokens; this sizes tg2.
2. **G1 fix round** (`benchmark/chains/c147/reviews/g1/round1.cursor-gpt-5.6-sol-high.md`, NOT cleared): P1 record a
   later tick start-order failure; P2 keep root and descendant obligations separately (never drop a protected root's
   recorded children; refresh descendants from every cleanup listing for every exact recorded root); P3 resolve against
   (pid, start time), tri-state, an occupied (pid, None) stays unresolved; plus the rest. Test-first → Cursor round 2 →
   full suite. Watch the false-abort risk for young benign processes that flicker and stay alive. (Do this before any
   chain that should use the new guard; the M65 pilot may run on the current main if G1 is not done yet — record which.)
3. **P311 build** (`docs/specs/p311-identity-split.md`; Cursor round 1 AGREE WITH CHANGES P1–P9 in
   `benchmark/chains/c147/reviews/p311/round1.cursor-gpt-5.6-sol-high.md`): apply P1–P9 to the proposal, then
   test-first build (three hashes; `bench/deny_rules.py` carve-out; chain pins `generation_code_sha256`), Cursor review,
   full suite.
4. **P348 audit (CPU, approved):** re-run `compare_predictor` / `judge_gate` / `agentbench_compare` over committed rows
   with the P346 logic; relabel README / `main_models.yaml` CERTIFIED comments / campaign-results where a PASS or
   "equivalent" becomes not-established; no score changes.
5. **M65 step 2 — tg2 design (CPU):** Rust / JavaScript / Java / C++ grading in `structured_grade` (+ images), a draw
   rule independent of our models, size from the pilot + power math → proposal → Cursor review → operator.
6. **M64 build** (spec §12, after 2–3): ArmAdapter contract + arm-aware runner + opencode wrap/parity; `../mlx-vlm`
   receipts (fork rules; push needs the operator); Pi adapter; dsh research + adapter (REJECT/HOLD to the operator if it
   cannot meet a required contract); shared SearXNG service (M64-owned container; the daily stack's `searxng` must be
   stopped during M64 runs); per-box two-judge config (C166); arm-neutral P201; snapshot/adoption tooling; per-arm
   smokes; then the operator's chain go. M64's corpus is decided after M65 (spec amendment if tg2).

## Known gaps / owed (not blocking the above)

- The c144-base report has a pick-vs-pick comparison without the AGENTS.md two-judge subjective measure (the panel is
  an M64 build item); add it when the panel exists, or mark it owed in the report.
- G2 (readable never-recorded owned orphans) stays open — design question.
- C154: re-check opencode's 60-min inactivity TTL on every opencode release (standing).
- `docs/README.md` index: add the new specs/reports (M64 spec, P311 proposal, plan/spec review packets, c144-base,
  POWER_SIM).
- (Done 2026-10-16: the box-topology memory note was refreshed.)

## Rules learned (2026-10-11 → 16)

- Never edit runner/probe/scoring files in the main checkout while a chain runs; build in worktrees. Never run the full
  suite under a live chain. Suite: from `benchmark/`, `../.venv-bench/bin/python -m pytest bench/tests -q` (~11 min).
- Edit-then-commit scripts must stop on failure (`set -e`, Edit tool) — failed edits twice produced commits whose
  messages claimed changes they did not contain; check `git show --stat` before trusting a commit.
- Archive a failed chain attempt with a sha256 manifest BEFORE moving anything (the runner rewrites `chain.json`).
- Decision epochs: one immutable harness snapshot per decision family; cross-epoch results descriptive (C165 E1).
- A collapsed bootstrap interval (zero discordance) never establishes equivalence (P346).
- Never select "harder" items by which items the current picks fail (selection on noise) — pre-register the draw.
- Launch chains with a command line that names no watched process; after a reboot `docker info` before Go legs.
- Pushes need explicit operator approval each time.

Next decision id C168; discussion ids continue from P350.
