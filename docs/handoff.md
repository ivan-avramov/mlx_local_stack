# Handoff — 2026-10-18 (evening): P371 + tg2 step 2 MERGED (`7915bccc`, `436acd11`); next = P369 fork fix round

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P384, P383, P382, P381, P380, P379, C179,
P378, P377 … C178, P371), then `docs/specs/p371-shared-runner-core.md` (PLAN v6) for the new code layout.

## State of the world

- **Box `m5max-128`, idle:** no router (:8000 free), no chain, no benchmark process. Docker (OrbStack) up; the agent shell needs
  `export PATH="$HOME/.orbstack/bin:$PATH"` and the machine config sourced (`. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`)
  or docker-backed tests skip.
- **Cold reviewer:** Cursor `gpt-5.6-sol-high` only (`cursor-agent -p --output-format text --model gpt-5.6-sol-high --mode plan
  --sandbox enabled --force --trust --workspace <repo> "<prompt>"`). Every plan, spec and build goes to Cursor. ONE review at a
  time; outputs to the scratchpad; launch detached with a background waiter on its EXIT marker. Fork reviews: workspace
  `../mlx-vlm` at the diff base with the diff INLINE.
- **Daily driver MTP-OFF (C177)** until P369 ships; restore the three registry lines + `test_opencode_probe_seeding.py` expectation.
- **Branches.** origin: `main` (pushed through `f0366550`; local main is ahead with docs + the P371 merge — push needs the
  operator), `evidence`, `c152-alloc-tool-scope-wip`, `p297-uncertain-gone`, `tg2-step2` (`b8bfe989`), `m64-build` (P371 build,
  pushed through `a78d14a8`, merged). Worktrees `$STACK_WORKDIR/worktrees/{tg2,m64}` (untracked `.venv-bench` symlink each —
  never stage). Fork worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p369` (branch `p369-mtp`, local only).
- **Push rule (C176):** WIP build branches may be pushed after each commit batch, privacy-scanned; `main`, the fork, tags, PRs
  need an explicit in-turn go (one go = one push).

## P371 — DONE (merged `7915bccc`)

- ONE item core `benchmark/bench/arm_runner.py`, ONE chain core `benchmark/bench/chain_core.py`; tg1 (`run_tg1_probe.py`,
  `chains/c147/run_tg1_chain.py`) and M64 oc (`run_oc_probe.py`, `chains/m64/run_m64_chain.py`) are configurations; tg2 becomes
  one at tg2 step 3 (`run_tg2_probe.py` + `corpus_tg2.py`, T14 amended). Contracts: `run_config`, `corpus`/`corpus_tg1`,
  `worker_receipts` (P372 protocol fixture), `item_barrier`, `chain_hooks`, `web_evidence`, `schedules`, `chain_rows` (the ONLY
  chain-row reader), `campaign_core` (C179 `--campaign-core`), `contract_artifact`, `atomic_publish`.
- **New tg1 epoch** (no rows yet): `probe_code_sha256` `5a4a9df8875c1e43c28d0acd4fb92f55258400ceb24c2ba39fe2e6b2de8688a9`,
  `scaffold_policy_sha256` `42a2485b…`, `generation_identity_sha256` `1c2e748b8e97b386a7719e37d988eb74e0e01bc94bcd2eb8da76dc6e67bb5ad5`;
  `m64-oc-tg1` `probe_code_sha256` `e7733c413689c7b295fe0a189816f32af10d6b4ed5893a9fe85e642efe04ef22` (its `--print-identity`
  refuses until D2 exists). Any generation-path core change rotates all of them (P377; freeze per campaign, C179).
- Reviews: plan rounds 1–4, code rounds 1–7 (`docs/reviews/p371/`), cleared at `a78d14a8`. Full suite from the m64 worktree
  alone at `a78d14a8`: 6536 passed / 21 skipped (tg2 grader image not built 15, dsh absent 2, OWED contract checks 3, mlx-serve
  source 1) / 1 xfailed / 0 failed. Contract artifact `--arm oc` on this box: `incomplete` (13 pass, 3 OWED).
- Test flakes root-caused (P383): the guard's sweep records ambient box processes (Spotlight `mdworker_shared`) as unattributed
  orphans; real-guard tests are hermetic now (`bench/tests/hermetic_scan.py`, autouse; opt-out `real_process_scan`); stress
  regression test with an ambient generator. **Production decision for M64 A7 is OPEN (P383).**
- M64 real chain still refuses by design: D2 stub, worker receipts `required` until the P372 fork endpoint, OWED contract checks.

## Next work after P371, in order

2. **tg2 step 2 — DONE** (merged `436acd11`): Cursor rounds 1–4 cleared S1–S16 (`benchmark/m65/reviews/step2-round{1..4}…`);
   universe re-frozen `ff76573b…` (149 valid: Rust 30 / Java 45 / JS 48 / C++ 26; exclusions java/ledger, java/tree-building,
   javascript/ledger; five items lost `.approaches`; leaves unchanged), draw `8eb9d8ef…` (permutations unchanged); fingerprinted
   freeze cache under `$STACK_WORKDIR/m65/tg2-freeze-s16` (old universe e8abba5c / draw d6aae71b archived with a manifest in
   `$STACK_WORKDIR/m65/stale-universe-pre-s16`). Full suite from the tg2 worktree: 6861 passed / 6 skipped / 0 failed. tg1
   identity unchanged by the merge (`5a4a9df8…`). Next for tg2: step 3 on the P371 core (`run_tg2_probe.py` + `corpus_tg2.py`).
3. **P369 — NEXT:** fork code review round 1 NOT CLEARED F1–F4 (B>1 MTP paths; `docs/reviews/p369-code-round1…`) → fix round in the fork
   (plain decoding wherever MTP cannot match it), test-first, Cursor round 2; then phase 2 on GPU (E1c, E2, E7), fork push
   (operator), submodule bump, re-certification, restore MTP-ON (C177).
4. tg2 steps 3–4 on the shared core (GPU go given for positives + smoke, C175); M64 spec amendment to the tg2 screen (C175 D3).
6. **P383 build (C180, option a):** M64 incident retry no longer blocked by `orphans_unattributed` (recorded in the incident);
   test-first in a stack worktree, Cursor code review, full suite, merge — after the P369 fork fix round.
7. **P385 investigation — FRESH SESSION, with Cursor (C181):** MLX 0.32.3 quantized sorted-dispatch MoE prefill nondeterminism
   (incl. NaN; evidence in the P385 entry and fork commit `bbffeec1` / F13 `1f0e6b40`). Steps: (1) minimal standalone repro at the
   real MoE models' expert count / group size, many fresh processes, bitwise; check whether an isolated MLX upgrade changes it;
   (2) if it reproduces: one real quantized MoE model (`gemma-4-26B-A4B-it-OptiQ-4bit` or `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`),
   same prompt, greedy, ~10 fresh processes — a GPU job: ask the operator first; (3) upstream MLX report with the repro, disclosure on
   affected models' results, workaround decision. Cursor `gpt-5.6-sol-high` helps design the repro, read the kernel, and cold-reviews
   the conclusion.
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

Next decision id C180; discussion ids continue from P385.
