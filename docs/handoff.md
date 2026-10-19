# Handoff — 2026-10-19: resume in a FRESH session with the P369 phase-2 harness code review, then the GPU smoke

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C183, P391, P390, P389, P388, C182, P387,
P386, C181, C180, P385, P384, P383 …), then `docs/specs/p369-phase2-run-plan.md` (**v7, Cursor AGREE**),
`docs/specs/p383-build-plan.md` (v4), `docs/specs/p369-mtp-certification.md` (v3), `docs/specs/p371-shared-runner-core.md`
(PLAN v6), `docs/specs/m65-tg2-corpus.md` (v5) and `docs/specs/m64-scaffold-arms.md` §4–§8, §12.

## State of the world (2026-10-19)

- **Box `m5max-128`.** No router (:8000 / :8091 free), no chain. **ON BATTERY (no adapter attached, 68 % at handoff) — the
  P369 phase-2 preflight refuses until the 140 W adapter is attached; ask the operator if it still is not.** Docker
  (OrbStack) up; the agent shell needs `export PATH="$HOME/.orbstack/bin:$PATH"` and the machine config sourced
  (`. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`).
- **Possibly still running when you start** (launched by the previous session at about the handoff commit; verify with `ps`;
  never two Cursor runs at once): (a) the Cursor CODE review of the P369 harness at fork `c10205ae` — output in the previous
  session's scratchpad `/private/tmp/claude-502/-Users-<user>-ws-mlx-local-stack/89ebd352-12ee-4e58-b74d-7c49ff36237b/scratchpad/p369-harness-code-r1-a1.out`;
  if it is complete (has a `VERDICT` line) copy it to `docs/reviews/p369-harness/code-round1.cursor-gpt-5.6-sol-high.md`;
  else kill any stale `cursor-agent` (and its shell) and RE-RUN it: prompt = `docs/reviews/p369-harness/code-round1.prompt-head.md`
  with `<HEAD>` → the fork HEAD, then `git diff 4e6d0e03..HEAD`, a closing fence, then the plan v7 inline; workspace
  `~/ws/mlx-vlm` (at the base `24551869`; branch commits readable with `git show <sha>:<path>`). Already DONE on `c10205ae`:
  fork suite twice back to back **6202 passed / 17 skipped / 0 failed**, identical skip lists; eight audits green, exclusion
  counts 269 / 675 / 3 / 0 / 34 / 50 / 16.
- **Daily driver MTP-OFF (C177)** until P369 ships and is re-certified; then restore the three registry lines in `main_models.yaml`
  (`draft_kind` / `draft_model` for both B picks, Fable's `mtp_verify_scan: joint_v1`) + the `test_opencode_probe_seeding.py` expectation.
- **Branches / pushes:**
  - stack `main` is **18+ docs commits ahead of origin** (push needs the operator's in-turn go; see "Push points").
  - fork `../mlx-vlm` branch **`p369-mtp` at `c10205ae`, local only**, worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p369`:
    production fixes cleared by code review round 8 at `4e6d0e03` + the phase-2 harness (test / dev only; production diff vs
    `4e6d0e03` EMPTY — the orchestrator refuses otherwise). Push needs the operator.
  - Parked (keep): `c152-alloc-tool-scope-wip`, `p297-uncertain-gone`, orphan `evidence`.
  - Push rule (C176): WIP build branches may be pushed after each commit batch, privacy-scanned; `main`, the fork, tags, PRs
    need an explicit in-turn go (one go = one push).

## Next work, in order

1. **P369 harness code review → fixes → green.** Finish / re-run the Cursor code review (above); fix findings test-first (a cold
   re-review after any semantic fix, P375 rule); fork suite twice back to back (identical counts, 0 failed; the 17th skip is the
   documented `test_p369_phase2_orchestrate.py` live-registry skip — no sibling stack beside the worktree) + the EIGHT audits
   after `git add -A` (`--upstream-ref 952d4f6b`).
2. **P387 (C183, the Q26 design)** on `p369-mtp`, test-only, red first: ordinary P369 tests read the MTP tuple AND sampling from the
   pinned golden fixture (sibling presence must not change the normal suite); an opt-in `MLX_REQUIRE_STACK_REGISTRY=1` test
   compares the live registry field by field and accepts exactly identical or the C177 interim (the marked `draft_kind` lines and
   Fable's marked `mtp_verify_scan`; the adjacent UNMARKED `draft_model` must equal the fixture's). Verify by running the
   registry-reading modules with `MLX_STACK_REGISTRY=<stack>/main_models.yaml` (today: 56 failed + 9 errors + 1 collection error).
   Production diff vs `4e6d0e03` stays empty. Then suites ×2 + audits.
3. **P369 phase 2 on GPU** (C175 go; C183 budget 3–3.5 h). Adapter attached first. From the stack root, detached, with a background
   waiter (no foreground sleep): `set -a; . ./.env; set +a; nohup .venv/bin/python <fork-worktree>/dev/p369_phase2/orchestrate.py
   --stack-root . --fork-root <fork-worktree> --out $STACK_WORKDIR/p369/phase2/<run-id>-smoke --phase smoke > <log> 2>&1 &`
   (never READ `.env` — sourcing it in the launch shell is the lean-router convention). Watch `monitor.log` (5-min ticks) and the
   job dirs; check `summary.json` `smoke_gate` (every live positive fired — `tq_norm` REQUIRED for uniform; every E1c cell PASS incl.
   C1; E2 identical; projected full ≤ 3.5 h, else stop for the operator). Then `--phase full --smoke-summary <smoke>/summary.json`.
   Report per pick: E1c (same-instance pair; C1; C2 `identical | unestablished`), E2, E7a (Clopper–Pearson), E7b (descriptive);
   results → P369 + handoff. An E1c FAIL → the bound to the operator ("bounded non-neutrality"). The worker's first live boot is
   the smoke — expect harness fixes there, each test-first.
4. **Fork push (operator)** → stack submodule bump (full suites in BOTH repos; P387 makes the fork suite pass against the live
   registry) → per-pick re-certification ON vs OFF on real router chains (own plan, Cursor review, operator GPU go) → restore
   MTP-ON (C177) → P368 layers 2–3.
5. **P383 build + P389 + P388 snapshot (C180, C183)** — `docs/specs/p383-build-plan.md` v4, stack worktree `p383-build`; test-first;
   Cursor code review (commit named); full stack suite from the worktree alone (never while the fork suite runs); merge when no
   chain from main is live.
6. **P385 investigation (C181) with Cursor** — standalone repro first; ask the operator before the real-MoE GPU check.
7. **tg2 steps 3–4 on the P371 core**; 8. **M64 remaining** (fork receipt endpoint P372, branched from the fork AFTER the P369
   push; D2; Pi / dsh; snapshots; P201 auditor; two-judge panel; contract artifacts; smokes; the chain go).

## Push points (advice given to the operator 2026-10-19; each push still needs its in-turn go)

1. **Now:** stack `main` (docs only: the P369 fork review cleared, the phase-2 plan v1–v7 + seven Cursor rounds, the P383 plan
   v1–v4, P386–P391, C182, C183, this handoff) — preserves the plan of record for the other box; zero risk.
2. **Fork `p369-mtp` as a branch (not fork `main`):** once the harness code review clears and P387 lands — BEFORE the GPU smoke,
   so the exact code the phase-2 manifest names (`fork_head`) is published and recoverable.
3. **Fork `main` merge + stack submodule bump:** after phase 2 passes (with the merge-time suites in both repos).
4. **P383 build branch:** push after each commit batch (C176, privacy-scanned; no go needed). Stack `main` again after the P383
   merge and after the phase-2 results land.

## Done 2026-10-18 → 19

- **P369 fork review CLEARED** (round 8 on `e6d2c32c..124de41f`; F23 + F27–F30 test-first; F31 closed by lead verification in
  `4e6d0e03`); fork suite 6118 / 16 / 0 twice; eight audits green (P386: the fork CI gates on EIGHT, not six).
- **P369 phase-2 plan v7** — Cursor rounds 1–7 (`docs/reviews/p369-phase2-plan-round{1..7}…`), AGREE. Design: worker-conformance
  harness (the fork's real CLI with `uvicorn.run` intercepted + `TestClient`; argv from mlx-serve's `_build_command` on a
  C177-restoring overlay); E1c observation at the production sampler (`_PositionedTargetSampler.sample_target`), full-state SHA-256
  at every commit + neutral probes, runtime kernel telemetry, exact straddle sizing + key-length proof; P391 same-instance pairing
  (drafter detached) with C1 / C2; E2 OFF / ON / OFF-reload; E7 classes bound to measured pre-fix defects; per-pick precedence.
- **Harness built** (fork `dev/p369_phase2/*`, tests `mlx_vlm/tests/test_p369_phase2_*.py`). CPU / tiny-fixture facts: bf16-quantized
  MTP rows + full state + probes bit-identical for both picks' recipes; dense float32 NOT (P390 — E1a was a 1e-5 law tolerance);
  the pre-fix oracle shows each defect (M4a +1 committed past a first-draft stop; M4b terminal token missing on bonus / first
  token / length; M3 overshoot 2 / 1 / 0 with a cut forced sequence) and the fix none; the real argv per pick / arm matches the
  overlay; the C84-item reconstruction yields 20 items per pick (`.venv-bench`).
- **P383 plan v4** (Cursor rounds 1–3; R15 applied without a 4th round — the code review verifies it).
- Rulings: C182 (go with the recs), C183 (all six recs accepted).

## Known gaps / owed

- E7 tool-session exposure (no tool sessions in E7b; would need production MTP event counters in the worker).
- The TurboQuant live positive (`tq_norm`) was never exercised on a tiny fixture (the tiny path builds plain `KVCache`); the uniform
  smoke must fire it (the gate requires it).
- G2, G3 (guard races); the MTP-ON arm-identity flag table check folds into the first MTP-ON smoke (C175); C154 opencode release
  checks; `docs/README.md` index additions (P311 v4, P364, P369, P371, m65 tg2, M65 pilot, `docs/reviews/p371/`, the P369 rounds,
  the phase-2 plan + `docs/reviews/p369-harness/`); the P371 receipt fence on abort paths only against `FakeReceiptSource`; fork:
  the quantized length-17 MoE precision cases a smoke until P385; non-MTP drafter dynamic fallbacks lose logprobs.

## Rules learned (2026-10-11 → 19)

- Never edit runner / probe / scoring files in the main checkout while a chain runs; build in worktrees. Never run the full suite
  under a live chain, and **never two full suites concurrently**. Stack suite: from `benchmark/`,
  `../.venv-bench/bin/python -m pytest bench/tests -q -p no:cacheprovider -o faulthandler_timeout=600 -rs > <file>`. Fork suite:
  `(cd mlx_vlm && ../.venv/bin/python -m pytest -q ./tests --ignore=tests/test_smoke.py -rs)` from the worktree.
- **Zero flakes:** a test that passes on rerun is a bug to root-cause; compare skip lists between runs; seed every randomized test.
- **Red-first honesty:** a red test that passes against a stub raising `NotImplementedError` (a `RuntimeError` subclass) is vacuous —
  match the specific message. If implementation got written first, set it aside, commit the tests red against a stub, restore.
- **Edit scripts:** black reflows lines, so multi-replacement `python3` scripts abort before writing — and a chained `git commit`
  then commits a misleading message (happened twice on 2026-10-19; both amended). A failed `Write` (file changed since read) does
  the same. Use the Edit tool on the file as it reads, stop the chain on failure, check `git show --stat` before trusting a commit.
- Cursor: output may print only the last finding — add "your FINAL message must contain everything" and re-run; one run at a time.
- macOS: system-wide `psutil.net_connections` needs root — use `lsof -nP -iTCP:<port> -sTCP:LISTEN`. `datasets` lives in
  `.venv-bench`, `mlx_serve` in `.venv`, `mlx` 0.32.3 in the fork venv. Never read `.env` (secrets); source it in launch shells.
- Determinism holds within ONE loaded-model lifetime only (`docs/metrics.md`); compare ON / OFF on the same instance.
- Watch long jobs and subagents yourself; kill leftovers by PID (zsh: arrays). Monitors expire after 30 min — re-arm.
- Archive a failed chain attempt with a sha256 manifest BEFORE moving anything; never select items by which items the picks fail.

Next decision id C184; discussion ids continue from P392.
