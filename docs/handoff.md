# Handoff — 2026-10-19 (session 2): P369 harness fix round 1 + P387 built; Cursor code round 2 in flight; P393 (E2 same-instance) awaits the operator

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: P393, C184, P392, C183, P391, P390,
P389, P388, C182, P387, P386, C181, C180, P385 …), then `docs/specs/p369-phase2-run-plan.md` (**v7, Cursor AGREE**; P393 would
make it v8), `docs/specs/p387-build-note.md` (v2), `docs/specs/p383-build-plan.md` (v4), `docs/specs/p369-mtp-certification.md`
(v3), `docs/specs/p371-shared-runner-core.md` (PLAN v6), `docs/specs/m65-tg2-corpus.md` (v5), `docs/specs/m64-scaffold-arms.md`.

## State of the world (2026-10-19, end of session 2)

- **Box `m5max-128`.** 140 W / 28 V adapter ATTACHED (operator, this session); no router (:8000 / :8091 free), no chain.
  **There is NO `.env` on this box** — the agent shell already carries `HF_TOKEN`; do not `. ./.env` (it errors and continues).
  Docker (OrbStack): `export PATH="$HOME/.orbstack/bin:$PATH"`; machine config: `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`.
- **Possibly still running:** the Cursor CODE review ROUND 2 of the harness at fork `dec95d95` (attempt 2; attempt 1 printed
  nothing). Prompt `docs/reviews/p369-harness/code-round2.prompt-head.md` (`<HEAD>` → `dec95d95`) + round-1 output + `git diff
  c10205ae..dec95d95` + plan v7, workspace `~/ws/mlx-vlm`. Output in session 2's scratchpad
  `/private/tmp/claude-502/-Users-<user>-ws-mlx-local-stack/dcde3cac-5ea1-4aec-96d2-ebe6a80be439/scratchpad/p369-harness-code-r2-a2.out`;
  if it has a `VERDICT` line copy it to `docs/reviews/p369-harness/code-round2.cursor-gpt-5.6-sol-high.md`, else kill stale
  `cursor-agent` and re-run (prompt rebuild: head + the round-1 output section + the diff + plan v7). Never two Cursor runs.
- **Fork `../mlx-vlm` branch `p369-mtp` at `764fe7dc`, local only**, worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p369`. Production
  diff vs `4e6d0e03` EMPTY (verified). On top of `c10205ae`: the round-1 fixes H1–H14 + C184 (`dec95d95`, 14 red/green commits)
  and P387 (2 commits). Fork suite on `dec95d95`: **6261 passed / 17 skipped / 0 failed twice**, identical skip lists; eight
  audits green, exclusions 269 / 675 / 3 / 0 / 34 / 50 / 16. NOT yet run on `764fe7dc` (P387): suites ×2 + audits owed.
- **Daily driver MTP-OFF (C177)** until P369 ships + re-certification; then restore the five marked registry lines (they are
  `test_mtp_verify_scan.INTERIM_LINES` in reverse) + the `test_opencode_probe_seeding.py` expectation.
- **Branches / pushes:** stack `main` 21+ docs commits ahead of origin; fork `p369-mtp` local only (push = operator); parked
  `c152-alloc-tool-scope-wip`, `p297-uncertain-gone`, orphan `evidence`. C176 push rule unchanged.

## What changed this session

- Harness code review round 1 (`docs/reviews/p369-harness/code-round1…`): NOT CLEARED H1–H9 (+ H10–H14). Fixed test-first:
  H1 state hash covers ArraysCache `left_padding` / `lengths` + TurboQuant codec mode / kind / bits / coordinates
  (`metadata_revision` excluded: an invalidation counter every ON block / probe bumps) and refuses an open transaction;
  H2 per-module kernel attributions (tuple fallbacks classified per module), expected families from the production
  eligibility predicates, coverage of every on-path projection; H3 allowlisted worker env (mlx-serve spawns with the router's
  inherited env; the tuple is in argv incl. `--generation-defaults`); H4 C1 needs every ON offset in both replays; H5 E7a
  counts only engaged uncensored requests; H6 templated-prompt digests bind E2 / E7 to the C84 reconstruction (the bundles
  store counts only — disclosed); H7 E7b echoes `content` + `reasoning_content` and checks token-level continuity against
  `PromptCacheState.token_ids` (production never appends the assistant hash); H8 per-request heartbeat + supervisor
  (request / boot / job deadlines, SIGTERM→SIGKILL, `timeout.json`), E7 censoring + relaunch; H9 clean fork tree, harness
  tree sha, the full run bound to its smoke; H10 E2 verdict + overall status, exit 0 / 2; H11 structural argv refusal;
  H12 oracle gate scoped to the git-dependent tests (`MLX_REQUIRE_P369_ORACLE=1` fails closed); H13 release clears the
  production session entry; H14 `{pid, create_time}` lock, stale reclaim only for a dead / reused owner; + 140 W AND 28 V.
- **C184 (operator):** no default campaign hard stop (`--wall-limit-s` opt-in); per-request watchdogs are the only automatic
  stops; each pick's step results reach `summary.json` as each step finishes.
- **P392 / P387:** the pinned fixture was pre-M58 (no Fable `joint_v1`); refreshed to the last MTP-ON registry `7021bdbb`;
  ordinary tests read only the fixture; opt-in live check accepts exactly the fixture or the byte-exact C177 interim
  (Cursor plan round 1 AGREE WITH CHANGES K1–K4, applied in build note v2). Acceptance in the commit message.
- **P393 (OPEN, operator):** E2 compares OFF and ON across two loads — reload nondeterminism would fail the smoke (no control)
  and make the full E2 at best INFORMATIVE_ONLY. Recommendation: E2 on the same-instance design (ON, detached OFF1 + OFF2
  control in the ON worker; the separate OFF process reported only). Needs the operator's go → plan v8 + Cursor plan check
  + test-first build in the same fix round as Cursor round 2's findings.

## Next work, in order

1. **Cursor round 2 → fixes → green.** Collect / re-run round 2 (above). Fix its findings test-first; with the operator's P393
   go, add the E2 same-instance change (plan v8, Cursor plan check first). Then fork suite twice back to back on the new HEAD
   (expect 17 skips: the opt-in live test + the opt-in overlay test replace the sibling skips; verify the list) + the EIGHT
   audits (`--upstream-ref 952d4f6b`, scratchpad script `run_audits.sh` pattern: the 8 `dev/check_*.py`), then a cold
   round 3 naming the commit (covers P387 + any P393 code too). Repeat until `VERDICT: CLEARED`.
2. **Fork branch push (operator go)** — before the GPU smoke, so the manifest's `fork_head` is published.
3. **P369 phase 2 on GPU** (C175; C183 budget 3–3.5 h projected; C184: no hard stop). From the stack root, detached:
   `nohup .venv/bin/python <fork-worktree>/dev/p369_phase2/orchestrate.py --stack-root . --fork-root <fork-worktree> --out
   $STACK_WORKDIR/p369/phase2/<run-id>-smoke --phase smoke > <log> 2>&1 &` with a background waiter; watch `monitor.log`
   (5-min ticks: job, current request from `progress.json`, power) and the job dirs. Exit 0 = `SMOKE_PASS`, 2 = completed
   without pass (read `summary.json`: `smoke_gate`, per-pick `outcome` / `e2.verdict`), 1 = harness error. Smoke gate: every live
   positive (`tq_norm` for uniform), every E1c cell PASS incl. C1, E2 PASS, projected full ≤ 3.5 h (else the operator). Then
   `--phase full --smoke-summary <smoke>/summary.json` (refuses unless the binding matches). Expect harness fixes at the first
   live boot (size / count dry runs through `_preprocess_request`, the kernel coverage set on real weights, the E7b
   continuity numbers), each test-first.
4. Fork `main` merge + submodule bump (suites in both repos; P387 makes the fork suite pass against the live registry) →
   per-pick re-certification (own plan, Cursor, operator GPU go) → restore MTP-ON (C177) → P368 layers 2–3.
5. P383 build + P389 + P388 snapshot (`docs/specs/p383-build-plan.md` v4, worktree `p383-build`); 6. P385 with Cursor (fresh
   session); 7. tg2 steps 3–4; 8. M64 remaining.

## Push points (each needs its in-turn go)

1. Stack `main` (docs: reviews, P387 note, P392, C184, P393, this handoff). 2. Fork `p369-mtp` as a branch once round N
clears — before the smoke. 3. Fork `main` merge + submodule bump after phase 2. 4. P383 build branch per C176.

## Known gaps / owed

- E7 tool-session exposure (no tool sessions in E7b); E2 / E7 link to the original C84 runs is count-only (no stored digest).
- `tq_norm` positive never exercised on a tiny fixture (uniform smoke must fire it); the kernel coverage set
  (`model.layers.*` + head) is unproven on the real checkpoints (an unexpected module fails closed in the smoke).
- G2, G3; MTP-ON arm-identity flag table check at the first MTP-ON smoke (C175); C154 checks; `docs/README.md` index additions
  (P311 v4, P364, P369, P371, m65 tg2, M65 pilot, `docs/reviews/p371/`, `docs/reviews/p369-harness/`, `docs/reviews/p387/`,
  the phase-2 plan, the P387 note); P371 receipt fence on abort paths only vs `FakeReceiptSource`; fork quantized length-17 MoE
  precision cases a smoke until P385; non-MTP drafter fallbacks lose logprobs; one pre-existing pyflakes note in
  `test_mtp_verify_scan.py` (`harness` unused, ~line 2112).

## Rules learned (2026-10-11 → 19)

- Never edit runner / probe / scoring files in the main checkout while a chain runs; build in worktrees; never two full suites
  at once; never edit a worktree while its suite runs. Stack suite: from `benchmark/`, `../.venv-bench/bin/python -m pytest
  bench/tests -q -p no:cacheprovider -o faulthandler_timeout=600 -rs > <file>`. Fork suite: `(cd mlx_vlm && ../.venv/bin/python
  -m pytest -q ./tests --ignore=tests/test_smoke.py -rs)` from the worktree (≈ 2.5 min).
- Formatting: `uvx --offline black@26.3.1` / `isort@5.13.2 --profile=black` / `pyflakes` (cached; no network). zsh: arrays for
  file lists (no word splitting); BSD `sed` chokes on the em dash — use Python for exact-line work.
- Zero flakes; red-first honesty (say when a red is "helper absent" vs behavioural); a test that starts subprocesses owns
  them in a fixture that kills them at teardown (a failing assertion left 4 sleepers this session — killed by PID).
- The Edit tool needs a Read of the file in this session (a `sed` view does not count); a failed Edit + chained commit:
  check `git show --stat` before trusting it.
- Cursor: an empty output (exit 0) happens — re-run; one run at a time; FINAL message must contain everything.
- macOS: `lsof` for ports; `datasets` in `.venv-bench`, `mlx_serve` in `.venv`, `mlx` 0.32.3 in the fork venv.
- Determinism holds within ONE loaded-model lifetime only (`docs/metrics.md`): compare ON / OFF on the same instance (P391, P393).

Next decision id C185; discussion ids continue from P394.
