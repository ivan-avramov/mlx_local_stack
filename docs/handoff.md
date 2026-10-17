# Handoff — 2026-10-17 (morning): M65 pilot DONE (both picks 29/29 — Python/Go saturated); G1 + P348 + P357 merged (new tg1 epoch `67e382b3…`); tg2 step 1, P311-lite, P359 in flight

THE one handoff. Read this, then `docs/open-questions.md` top entries (C172, P361, P360, C171, P359, P358, C170, G3, P357, C169, C168, P356, P355,
P353, P352, P351), `docs/specs/m65-tg2-corpus.md` (v5), `docs/specs/p311-identity-split.md` (v4), `benchmark/results/m65_pilot/M65_PILOT_REPORT.md`.

## Now (2026-10-17 ~06:30Z)

- **Box idle** (no chain; :8000 free). **P359 merged** (`eeee1784`, Cursor CLEARED AFTER FIXES W1–W6, verified): wash verdicts, no
  equivalence claims, lever guard on the observed loss bound (C172/C173); all 12 stored lever cells still ship. Full suite 4748 passed,
  3 skipped, 1 xfailed. **Pushed** `origin/main` 2ef70a67..eeee1784 (operator C173); later commits need a new push go.
- **M65 pilot DONE** (rc 0): `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` and `Qwen3.8-27B-mlx-uniform-4bit` both 12/12 Python + 17/17 Go strict;
  second pick ≈ 1.3–1.8× output tokens. One web row audited `generic` (Cursor auditor; codex is absent here — use
  `benchmark/web_audit_cursor.py`, C158).
- **Merged:** P351 runner, P348 audit, P357 power sim, **G1 by operator override (C170)** with residuals in G3. G1 changed the guard →
  **tg1 probe identity is now `67e382b32f7206242b72b088161da9973e52d072f042dff442b667dd60aafbc8`** (new epoch; old `ebcfe6fb…`).
- **In flight (worktrees under `$STACK_WORKDIR/worktrees/`, each with an untracked `.venv-bench` symlink):**
  - `tg2` / `tg2-build`: step 1 grader + offline image (`tg2-grader:m65-v1`, now `sha256:09f2b30e…`); Cursor round 2 NOT CLEARED
    (G18–G20) → round 3 with the implementer (+ P361 mount-source guard). Then steps 2–4; GPU runs need an operator go (C169).
- **P311-lite MERGED** (`7fcf0433` + test fixes `a9c6f62f`; Cursor build rounds 1–2, cleared after fixes, lead-verified): tg1 now runs
  `benchmark/run_tg1_probe.py`; web contact scored post hoc (`bench/tg1_score.py` sidecar, single fail-closed join `bench/row_scores.py`);
  identity = AST import closure + toolchain; pairing key = (generation identity, both arm identities, spawn-time prompt_date);
  expected policy sha derived per box at chain start (P362). **tg1 epoch `probe_code_sha256` `e91a2450acff07669865a81f1b7dfc0544fe9bce86c10be3540fb78b9e601bb7`**
  (generation composite `29f40799…`). `--print-identity` needs docker on PATH (grader image id; fails closed). Full suite 4994 passed.
  Before the next MTP-ON run: check `arm_identity.py`'s flag table against a live ON worker argv.
- **P364 MERGED** (`10fe6e7a`; design + build Cursor rounds, cleared after fixes; C174): `benchmark/opencode_plugins/datefreeze.js` freezes the date
  opencode shows the model (structured `context`/`compaction`/`generate`/`title` hooks; midnight `Today's date is now:` update removed); per-item
  receipts reconciled against requests and hash-checked in `validate_leg`; activation refuses any `failed to load plugin` line (covers all three
  plugins). Chain runner: `--frozen-prompt-date` / `--frozen-date-from <reference chain.json>` — never defaults to today; an old-epoch
  `chain.json` without a frozen date refuses on resume. Residual: the model's shell can read the frozen date + receipt path (same-UID evidence
  limit). **tg1 epoch now `probe_code_sha256` `ae7fca94e77b1ea025f67bbac27a0b816aa0f8de8b771aa3683a8170a80fc2a1`**, scaffold policy `33d79b32…`.
  Full suite on main 5092 passed. Reference arms are reusable across days within an epoch (C168's ≈ 4 GPU h screen holds).
- **tg2 step 1 MERGED** (`a22f0db7`; Cursor rounds 1–6 + round 7 closed by lead verification, P365): `bench/tg2_grade.py`
  (Rust/Java/JS/C++; phase-typed, nonce-marked, tmpfs-volume grading; nonce-label ownership; list-and-refuse leftovers, explicit
  `benchmark/m65/tg2_cleanup.py`), image `tg2-grader:m65-v1` `sha256:09f2b30e…` (`benchmark/m65/tg2_image/`). Main full suite 5404
  passed; tg2 docker tests need the machine config sourced (`STACK_WORKDIR`) or they skip. **Step 2 in progress** (branch `tg2-step2`):
  materializer, universe freeze, nested draw.
- **Operator answers pending:** none. Local main is ahead of origin (P311-lite, P364, tg2 step 1, docs) — push needs a new go.
- **Push rule (C176):** active WIP build branches (`tg2-step2`, `m64-build`, …) may be pushed after each commit batch (privacy scan each
  time); `main` and everything else still need an explicit in-turn go.
- **Rules:** never run two full suites concurrently (load flakes timing tests and once leaked a chain-test runner thread for 7 h — fixed
  defensively on `tg2-build`); always write suite output to a file and read the summary line.
- **P361:** OrbStack bind mounts under `$TMPDIR` serve stale sizes after in-place overwrites; tg1 unaffected (fresh snapshots under
  the run dir). See box-notes.

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
  `m64-plan-review`; active: `g1-fix`).
- **G1 reverted off main (P350, `2dd80916`):** its Cursor review was not cleared, so `main` carries the pre-G1 guard
  (C157 + P306 — byte-identical to `3cfb8c5d`, the guard that ran c144-base). The G1 attempt is on local branch
  **`g1-fix`** (= `5f9fdbc4`); fix it there and merge only after Cursor clears it.
- **Identity on main:** `probe_code_sha256` `ebcfe6fb890e723c06c6ccaed39869aa3f4c31e86007c9c089ef489e715df2ea`
  (re-verify with `run_opencode_probe_v2.py --print-identity` before any chain).
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

1. **M65 step 1 — headroom pilot (GPU; start it first so the GPU works while the CPU items run; runs from `main` on the
   pre-G1 guard — G1 is NOT on main):** both picks, k = 1,
   predictor OFF, on the 30 polyglot Python + Go items outside `benchmark/m62/universe.json` (12 Python, 18 Go): new
   universe file (same format; run `universe_preflight` on it), own out-root (e.g. `$STACK_WORKDIR/m65-pilot`),
   `--smoke` first, the runner's `--universe`. Check whether the runner's schedule (s1/s2/reload) needs a k=1 mode — a
   runner change is a runner-file change: test-first, never with a live chain. Report strict per pick vs tg1, nonconv
   kinds, tokens; this sizes tg2.
2. **G1 fix round on branch `g1-fix`, in a worktree** (`benchmark/chains/c147/reviews/g1/round1.cursor-gpt-5.6-sol-high.md`,
   NOT cleared): P1 record a
   later tick start-order failure; P2 keep root and descendant obligations separately (never drop a protected root's
   recorded children; refresh descendants from every cleanup listing for every exact recorded root); P3 resolve against
   (pid, start time), tri-state, an occupied (pid, None) stays unresolved; plus the rest. Test-first → Cursor round 2 →
   full suite. Watch the false-abort risk for young benign processes that flicker and stay alive. Merge into main only
   after Cursor clears it, and never while a chain launched from main is live.
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
- Run the FULL suite once from a branch's worktree before merging it: worktrees symlink `.venv-bench` outside the repo, which hid
  two P311-lite test failures that only showed on main (in-repo venv).

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
