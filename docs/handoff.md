# Handoff — 2026-10-17 (evening): resume in a FRESH session with P371 (shared arm-neutral runner core, C178)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C178, P371, P370, C177, C176, P369, C175,
P368, P367, P366, P365, P364, C174, P363, P362, P361, P360, C173, C172, P359 …), then the specs named below.

## State of the world

- **Box `m5max-128`, idle:** no router (:8000 free), no chain, no benchmark process. Docker (OrbStack) up; the agent shell needs
  `export PATH="$HOME/.orbstack/bin:$PATH"` and the machine config sourced (`. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`)
  or docker-backed tests skip.
- **Cold reviewer:** Cursor `gpt-5.6-sol-high` only (`cursor-agent -p --output-format text --model gpt-5.6-sol-high --mode plan
  --sandbox enabled --force --trust --workspace <repo> "<prompt>"`). **Every plan goes to Cursor before execution** (operator
  2026-10-17, memory `plans-through-cursor`), as well as specs and built code. Run ONE Cursor review at a time (concurrent runs
  return empty output); write outputs to the scratchpad, not inside the workspace (one output file vanished); re-run until a
  `VERDICT` line appears.
- **Daily driver is MTP-OFF (C177):** both B picks (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, `Qwen3.8-27B-mlx-uniform-4bit`)
  have `draft_kind` / `draft_model` (and Fable's `mtp_verify_scan: joint_v1`) commented out in `main_models.yaml` until the P369
  fixes ship and are re-certified. Restore all three lines + `bench/tests/test_opencode_probe_seeding.py` (expects `per_query` now).
- **tg1 epoch:** `probe_code_sha256` `ae7fca94e77b1ea025f67bbac27a0b816aa0f8de8b771aa3683a8170a80fc2a1` (P311-lite + P364 datefreeze),
  scaffold policy `33d79b32…`; **no rows recorded in it yet** — P371 will change it once more (accepted, C178).
- **Branches.** origin: `main`, `evidence` (orphan, irreproducible evidence — keep), `c152-alloc-tool-scope-wip`, `p297-uncertain-gone`
  (parked), `tg2-step2` (`b8bfe989`), `m64-build` (`406cc10e`). Local `main` is **ahead of origin by ~13 docs/registry commits**
  (P369 plan/results, C177 MTP-off registry, C178) — **push needs the operator**. Worktrees: `$STACK_WORKDIR/worktrees/{tg2,m64}`
  (each with an untracked `.venv-bench` symlink — never stage). Fork worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p369` (branch
  `p369-mtp`, **local only — fork push needs the operator**).
- **Push rule (C176):** active WIP build branches (`tg2-step2`, `m64-build`, any new stack build branch) may be pushed after each
  commit batch, privacy-scanned each time; `main`, the fork, tags, PRs and anything else need an explicit in-turn go.
- **Full suite on main:** 5404 passed (after tg2 step 1); later commits on main are docs + the C177 registry edit (its tests pass).

## Done this session (all on main unless noted)

M65 pilot (both picks 29/29 on Python + Go outside tg1 → saturated; `benchmark/results/m65_pilot/`); P351 runner `--universe`;
P348 audit; P357 power sim; G1 (operator override; residual races = G3); P359 / C172 / C173 wash verdict (no equivalence claims;
lever guard on the observed loss bound ≤ 10 pp; AGENTS.md amended); P311-lite (generation-only identity by import closure,
post-hoc web scoring, full pairing key); P364 datefreeze (frozen epoch date in opencode's prompt; reference arms reusable across
days); tg2 step 1 (grader + offline image, nonce ownership, list-and-refuse cleanup; P360–P365); C168 tiers (screen 40 / k = 1,
≈ 4 GPU h, diagnostic; decider 80 / k = 2, ≈ 18 GPU h; AGENTS.md k = 1 screen exception); C175 (tg2 GPU go after steps 3–4,
keep C++, M64 on the tg2 screen); branch cleanup (Cursor audit, `docs/reviews/branch-audit-2026-10-17/`).

## Next work, in order

1. **P371 (C178) — ONE shared arm-neutral item + chain core.** `arm_runner.py` (on `m64-build`) becomes the single implementation;
   tg1, tg2 and the M64 arms are configurations; `tg1_runner.py` a thin entry. It absorbs the **M64 step 4a fix round** — Cursor
   `benchmark/chains/m64/reviews/step4a-round1.cursor-gpt-5.6-sol-high.md` on `m64-build`, NOT CLEARED A1–A14: tg2-screen schedule
   + four languages (A1), spec §7 worker receipts (A3), tool-start watchdog (A4), epoch / snapshot pinning (A5), crash + recovery
   (A6–A8), one segment reader (A9), immutable per-arm A4 receipts (A10), adapter-owned client specifics (A11), P201 raw evidence
   (A12), real-client contract checks (A13), parity widened (A14); plus P370 (`compaction_failed` scored, post-hoc compaction tokens
   disclosed). New tg1 epoch accepted; amend tg2 spec T14 ("tg2 is a configuration of the shared core"). Process: **plan →
   Cursor plan review → test-first build → Cursor code review → full suite from the worktree alone → merge**. Built BEFORE tg2
   step 3 (tg2's runner IS the core). M64 spec §12 still lists Pi / dsh adapters, SearXNG service, snapshots, judge panel later.
2. **tg2 step 2 fixes** (branch `tg2-step2`, Cursor `benchmark/m65/reviews/step2-round1…`: CLEARED AFTER FIXES S1–S4): **S1 leak —
   `prepare_tree()` must exclude `.approaches/**`** (five items expose solution snippets) + corpus-backed leakage tests; S2 semver
   check of `[dependencies]` against vendored versions (tamper, not compile failure); S3 fingerprint freeze-cache records (corpus,
   image, grader/materializer version, policy) and reject mismatches; S4 assert reference sources are excluded. Then **regenerate the
   universe + draw** (current: universe `e8abba5c…`, draw `d6aae71b…`, 149 valid: Rust 30 / Java 45 / JS 48 / C++ 26; image
   `sha256:98559f41…`), full suite, lead verification, merge. A freeze takes ≈ 71 min — watch its log yourself.
3. **P369 MTP certification** (`docs/specs/p369-mtp-certification.md` v3): phase 1 DONE on fork branch `p369-mtp`
   (`88724023` E1a/E1b exactness tests, `0b43dae4` M4 + M3, `5e70c2e4` M2 + M5; fork suite 6037 passed). **Cursor code review of the
   fork diff is OWED** — it returned empty twice from the worktree workspace; re-run with `--workspace ~/ws/mlx-vlm` and
   `git diff 24551869...p369-mtp`. Then phase 2 (GPU, ≈ 1 h): E1c per-pick real-weight conformance (Fable native KV `joint_v1`
   with straddle counters; uniform TurboQuant `per_query`), E2 greedy identity, E7 firing rates; then fork push (operator) → submodule
   bump → per-pick re-certification (wash rule, fresh OFF controls) → restore MTP-ON in the registry (C177) → P368 layers 2–3.
4. **tg2 steps 3–4** on the shared core: runner + legs, injected positives per language, four-language smoke (GPU go given, C175),
   sizing report; then M64 spec amendment to the tg2 screen (C175 D3).
5. **M64** remaining build per its spec §12 (after P371): `../mlx-vlm` receipts (fork rules), Pi adapter, dsh adapter, SearXNG
   service, snapshots / adoption, per-box two-judge panel (C166), per-arm smokes, then the operator's chain go.

## Known gaps / owed

- G2, G3 (guard races; structural fix = per-item containment at an M64 epoch).
- MTP-ON arm-identity flag table check folds into the first MTP-ON smoke (C175).
- mlx 0.32.4 breaks the fork's quantized-verifier exactness tests — stay on 0.32.3 (box-notes).
- C154: re-check opencode's 60-min inactivity TTL and the datefreeze hooks on every opencode release.
- `docs/README.md` index: add the new specs/reports (P311 v4, P364, P369, m65 tg2, M65 pilot, reviews).

## Rules learned (2026-10-11 → 17)

- Never edit runner/probe/scoring files in the main checkout while a chain runs; build in worktrees. Never run the full suite under a
  live chain, and **never two full suites concurrently** (load flakes timing tests; once leaked a chain-test runner thread for 7 h).
  Suite: from `benchmark/`, `../.venv-bench/bin/python -m pytest bench/tests -q -p no:cacheprovider -o faulthandler_timeout=600 > <file>`;
  read the summary line from the file. Run the FULL suite from a branch's worktree before merging (symlinked venv hid failures).
- **Watch long jobs yourself:** an agent waiting on its own background job shows a frozen token count and looks stuck; check the job's
  log. When you kill a job an agent waits on, also kill the agent's waiter (a killed job never writes its EXIT marker).
- Edit-then-commit scripts must stop on failure; check `git show --stat` before trusting a commit.
- Archive a failed chain attempt with a sha256 manifest BEFORE moving anything.
- Decision epochs: cross-epoch results descriptive (C165 E1). No equivalence claims — wash + MDE + directional pick (C172).
- Never select items by which items the picks fail; pre-register draws.
- OrbStack bind mounts under `$TMPDIR` serve stale file sizes after in-place overwrites — mount fresh copies outside `$TMPDIR` (P361).
- `--print-identity` needs docker on PATH (grader image id; fails closed).

Next decision id C179; discussion ids continue from P372.
