# Handoff — 2026-10-18 (early): P371 build phases 0–4 done on `m64-build`; Cursor code review round 1 running

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P381, P380, P379, C179, P378, P377, P376,
P375, P374, P373, P372, C178, P371, P370, C177, C176, P369, C175 …), then `docs/specs/p371-shared-runner-core.md` (PLAN v6).

## State of the world

- **Box `m5max-128`, idle:** no router (:8000 free), no chain, no benchmark process. Docker (OrbStack) up; the agent shell needs
  `export PATH="$HOME/.orbstack/bin:$PATH"` and the machine config sourced (`. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`)
  or docker-backed tests skip.
- **Cold reviewer:** Cursor `gpt-5.6-sol-high` only (`cursor-agent -p --output-format text --model gpt-5.6-sol-high --mode plan
  --sandbox enabled --force --trust --workspace <repo> "<prompt>"`). Every plan, spec and build goes to Cursor. ONE review at a
  time; outputs to the scratchpad; re-run until a `VERDICT` line appears. Fork reviews: workspace `../mlx-vlm` at the diff base with
  the diff INLINE (the worktree workspace returned empty twice).
- **Daily driver MTP-OFF (C177)** until P369 ships; restore the three registry lines + `test_opencode_probe_seeding.py` expectation.
- **Branches.** origin: `main` (pushed through `f0366550`; local main has docs commits after it — P378–P381, spec amendments,
  this handoff — push needs the operator), `evidence`, `c152-alloc-tool-scope-wip`, `p297-uncertain-gone`, `tg2-step2`
  (`b8bfe989`), `m64-build` (P371 build, pushed through `bda0f2b5`). Worktrees `$STACK_WORKDIR/worktrees/{tg2,m64}` (untracked
  `.venv-bench` symlink each — never stage). Fork worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p369` (branch `p369-mtp`, local only).
- **Push rule (C176):** WIP build branches may be pushed after each commit batch, privacy-scanned; `main`, the fork, tags, PRs
  need an explicit in-turn go (one go = one push).

## P371 (C178) — status

- **Plan closed at v6** (`docs/specs/p371-shared-runner-core.md`; Cursor plan rounds 1–4 `docs/reviews/p371/`; R1–R31 applied;
  P379 amendment).
- **Built on `m64-build`** (implementation subagents, lead-reviewed per phase; red-then-green commits):
  1a contracts (`run_config`, `corpus` + `corpus_tg1`, `worker_receipts`, `item_barrier`, `chain_hooks`, `web_evidence`,
  `schedules`, `chain_rows`); 1b `host` + the isolated pre-P371 baseline harness (`bench/tests/p371_baseline/`, `git archive
  0c9bd32a`, 19 scenarios); 2a ONE item core (`arm_runner.py`; `tg1_runner.py` thin; A11); 2b A2 `compaction_failed`, A3 runner
  side, item barrier, A4 `toolwindows.js` (works on real 2.0.20), R30, dependency rule; 3a ONE chain core (`chain_core.py`),
  disjoint pilot / full invocations (P376), progress inventory, web evidence chain-side, lifecycle closure, C179
  `--campaign-core`, R7 (all readers via `chain_rows`; stored reports byte-identical); 3b M64 on the core (A1, A5–A8, A10,
  hooks at the barrier, abort-path fence; `m64_schedule.py` deleted); 4 A13 contract suite on real runs + artifact mode
  (`benchmark/m64/contract_artifact.py --arm oc`: verdict `incomplete`, 13 checks pass, 3 OWED) + chain refusal, C179 on M64,
  closures per entry, R17 isolation.
- **Tests:** phase-4 bar (77 files, alone) 1992 passed / 4 skipped / 1 failed — the failure is P381 (date-hard-coded test,
  pre-existing, also fails on main since 2026-10-18). Baseline full suite before the build: 5590 passed.
- **Identities move until merge;** record the final tg1 / oc `probe_code_sha256` at the merge commit (`--print-identity`).
- **Next:** Cursor code review round 1 on `bda0f2b5` (running; prompt + output in the session scratchpad) → fixes (P375 revised:
  semantic fixes get another cold round) → P381 fix (needs the operator's go) → full suite from the m64 worktree ALONE → lead
  verification of plan §8 → merge `m64-build` into main (no chain live) → handoff with the new epoch's identities.

## Next work after P371, in order

2. **tg2 step 2 fixes** (branch `tg2-step2`, Cursor `benchmark/m65/reviews/step2-round1…`, CLEARED AFTER FIXES S1–S4: S1
   `.approaches/**` leak, S2 semver check, S3 freeze-cache fingerprint, S4 reference sources excluded); regenerate universe + draw
   (≈ 71 min freeze — watch its log), full suite, lead verification, merge. Then rebase tg2 step 3 onto the P371 core (tg2 =
   `run_tg2_probe.py` + `corpus_tg2.py` configuration; T14 amended).
3. **P369:** fork code review round 1 NOT CLEARED F1–F4 (B>1 MTP paths; `docs/reviews/p369-code-round1…`) → fix round in the fork
   (plain decoding wherever MTP cannot match it), test-first, Cursor round 2; then phase 2 on GPU (E1c, E2, E7), fork push
   (operator), submodule bump, re-certification, restore MTP-ON (C177).
4. tg2 steps 3–4 on the shared core (GPU go given for positives + smoke, C175); M64 spec amendment to the tg2 screen (C175 D3).
5. M64 remaining: fork receipt endpoint (P372, the A3 protocol fixture), Pi / dsh adapters, D2 SearXNG + MCP, snapshots /
   adoption, P201 hooks, two-judge panel, smokes, chain go.

## Known gaps / owed

- G2, G3 (guard races; structural fix = per-item containment at an M64 epoch).
- MTP-ON arm-identity flag table check folds into the first MTP-ON smoke (C175).
- mlx 0.32.4 breaks the fork's quantized-verifier exactness tests — stay on 0.32.3 (box-notes).
- C154: re-check opencode's 60-min inactivity TTL and the datefreeze + toolwindows hooks on every opencode release.
- `docs/README.md` index: add the new specs/reports (P311 v4, P364, P369, P371, m65 tg2, M65 pilot, reviews).
- P371 receipt fence on abort paths is exercised only against `FakeReceiptSource` (real HTTP source owed with P372).
- A14 item scenario `item_cooperative_cancel` flaked once under load — watch.

## Rules learned (2026-10-11 → 18)

- Never edit runner/probe/scoring files in the main checkout while a chain runs; build in worktrees. Never run the full suite under a
  live chain, and **never two full suites concurrently** (load flakes timing tests; once leaked a chain-test runner thread for 7 h).
  Suite: from `benchmark/`, `../.venv-bench/bin/python -m pytest bench/tests -q -p no:cacheprovider -o faulthandler_timeout=600 > <file>`;
  read the summary line from the file. Run the FULL suite from a branch's worktree before merging (symlinked venv hid failures).
- **Watch long jobs yourself,** including subagents' test runs: a subagent left an orphaned pytest bar (shell reparented to init)
  running beside its next one; check `ps` ancestry and kill orphans by PID (they may ignore SIGTERM).
- Subagent briefs must forbid literal usernames / emails / home paths even in privacy-check regexes (one landed in a red commit;
  history rewritten before push).
- Privacy scans: `ugrep` rejects `^\+\+\+` patterns — filter with `grep -E '^\+'` then the PII alternation, never a failing pipeline.
- Edit-then-commit scripts must stop on failure; check `git show --stat` before trusting a commit.
- Archive a failed chain attempt with a sha256 manifest BEFORE moving anything.
- Decision epochs: cross-epoch results descriptive (C165 E1); one shared core ⇒ core fixes rotate every identity (P377, C179).
- Never select items by which items the picks fail; pre-register draws.
- OrbStack bind mounts under `$TMPDIR` serve stale file sizes after in-place overwrites — mount fresh copies outside `$TMPDIR` (P361).
- `--print-identity` needs docker on PATH (grader image id; fails closed).

Next decision id C180; discussion ids continue from P382.
