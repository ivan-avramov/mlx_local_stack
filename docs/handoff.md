# Handoff — 2026-10-19 (end of session 2): P369 harness review closed by the operator after 6 rounds (C186); next = 3 small evidence fixes, then C185 (same-instance E2), then the fork push + GPU smoke

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C186, C185, P395 (closed), P394, P393,
C184, P392, C183, P391 …), then `docs/specs/p369-phase2-run-plan.md` (v7; C185 makes §3 E2 v8 — not yet written),
`docs/specs/p387-build-note.md` (v2), `docs/specs/p383-build-plan.md` (v4).

## State of the world

- **Box `m5max-128`.** 140 W / 28 V adapter attached. No router, no chain, no Cursor run, no pytest running. **No `.env` on this
  box** (the shell already carries `HF_TOKEN`; never `. ./.env`). Machine config: `. "${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh"`.
- **Fork `../mlx-vlm` branch `p369-mtp` at `d9027a60`, local only**, worktree `$STACK_WORKDIR/worktrees/mlx-vlm-p369`, clean.
  Production diff vs `4e6d0e03` EMPTY. Holds: the P369 production fixes (cleared) + the phase-2 harness (review rounds 1–6 fixed
  test-first) + P387. Last green: `d9027a60` fork suite **6328 passed / 17 skipped / 0 failed twice**, identical skips; eight audits
  green, exclusions 269 / 675 / 3 / 0 / 34 / 50 / 16.
- **Stack `main` 37 commits ahead of origin** (docs only). Push needs the operator's in-turn go. One stray untracked file
  `docs/reviews/p369-harness/code-round2.prompt-head.md` — commit it with the next docs commit.
- Daily driver MTP-OFF (C177) until P369 ships + re-certification.

## Rulings this session (all in open-questions)

- **C184** no campaign hard stop by default (`--wall-limit-s` opt-in); per-request watchdogs only.
- **C185** (P393 approved) **E2 on the same-instance design**: in the ON worker per item greedy ON, then drafter detached → greedy
  OFF1 + within-instance OFF2 control; verdict ON vs OFF1; OFF1≠OFF2 = harness ABORT; the separate OFF process stays as a reported
  cross-load comparison (never decides); smoke and full. Reuse the E1c machinery (`drafter_detached`, `DetachedGuard`, `wait_idle`,
  `release_trajectory`, `c1_acceptance` pattern).
- **C186** (AGENTS.md "Reviews" line): **≤ 3 review rounds per artifact, then the operator; every prompt states "round k of 3";
  escalate as a table** (finding + context 2–3 sentences; recommendation + justification + strongest counterpoint 2–3 sentences).
  Supersedes P375 / "repeat until CLEARED". Operator ruling on the harness round-6 escalation: **fix H34, H36, H38; accept H35;
  record H37 as a residual; the harness review is CLOSED** after those fixes.
- P394 lead calls (refined): unreviewed smoke iterations allowed but never authorize a full run; full run needs `--reviewed-head`
  (= the commit the review closed on) + a passing smoke bound to it; E7b never gates a full PASS (E1c + E2 + E7a OBSERVED do); the
  smoke runs one E7b session. P392: fixture was pre-M58 (fixed in P387).

## Next work, in order

1. **H34 / H36 / H38 (test-first, red then green)** in `dev/p369_phase2/orchestrate.py` — exact-boolean evidence validation
   (raise "malformed evidence", a harness error, never an MTP outcome). Truthiness sites (`grep -n` at `d9027a60`): `pick_outcome`
   (c1/c2 `identical`), `e7a_stats` kernel `verdict.pass`, `e7b_session` verdict + `continuity`, `overall_status` smoke gate,
   `e1c()` `c1_ok = bool(...acceptance.pass)` and C2 `identical=bool(rows.pass and states.pass)`, `e2()` `verdict["pass"]`, `main()`
   full-run gate `gate.get("pass_") and gate.get("fits")` (H36: require exact `True`s AND `status == "SMOKE_PASS"`), `smoke_gate`
   E7b check (H38: exactly one session, the first reconstructed C84 item's name, typed fields, status re-derived via `e7b_status`).
   Record H35 (accepted: a completed request is a valid observation) and H37 (residual: total ps failure after a setsid helper) in
   `docs/reviews/p369-harness/code-round6…` as the closure note. Suites ×2 + 8 audits. No further review round (C186).
2. **C185 build** (test-first): write plan v8 §3 E2; implement same-instance E2 (worker mode, e.g. `e2_pair`, mirroring `e1c_pair`);
   tests; suites ×2 + audits; **review round 1 of 3** (Cursor, C186 prompt + table escalation). Fix, ≤ 3 rounds, escalate per C186.
3. **Ask the operator for the fork branch push** (`p369-mtp`) — then the **GPU smoke** (C175 go): from the stack root, detached,
   background waiter: `nohup .venv/bin/python <fork-worktree>/dev/p369_phase2/orchestrate.py --stack-root . --fork-root <fork-worktree>
   --out $STACK_WORKDIR/p369/phase2/<run-id>-smoke --phase smoke [--reviewed-head <closed sha>] > <log> 2>&1 &`. `--out` must be under
   `$STACK_WORKDIR/p369/phase2/`; lock is `$STACK_WORKDIR/p369/phase2/.lock` (flock). Watch `monitor.log` (5 min) + job dirs; exit 0
   SMOKE_PASS / 2 not pass / 1 harness error. Expect live-boot fixes (dry-run tokenization via `_preprocess_request`, kernel coverage
   on real weights, E7b continuity numbers) — fix test-first; smoke iterations need no review round (P394), the full run needs the
   reviewed head + a passing smoke on it. Then `--phase full --smoke-summary <smoke>/summary.json --reviewed-head <sha>`; report per
   pick E1c (pair, C1, C2), E2, E7a (Clopper–Pearson), E7b (descriptive) → P369 + handoff.
4. Then: fork main merge + submodule bump (suites in both repos) → per-pick re-certification (own plan, operator GPU go) → restore
   MTP-ON (C177 lines = `test_mtp_verify_scan.INTERIM_LINES` reversed) → P368 layers 2–3; P383 build (+P389, P388 snapshot); P385
   with Cursor; tg2 steps 3–4; M64.

## Known gaps / owed

- Residuals (disclosed): a helper that spawns and escapes between two ps polls; pid reuse within one lstart second; a cache
  symlink swap during model load restored before the re-hash; H37; H12 (CI oracle `fetch-depth: 0` + `MLX_REQUIRE_P369_ORACLE=1`)
  with the fork main merge. E2/E7 link to the original C84 runs is count-only (bundles store no digest). `tq_norm` positive and
  the kernel coverage set (`model.layers.*` + head) unproven on real weights until the smoke. E7 tool-session exposure not measured.
- `docs/README.md` index additions (P311 v4, P364, P369, P371, m65 tg2, M65 pilot, `docs/reviews/p371/`, `docs/reviews/p369-harness/`,
  `docs/reviews/p387/`, the phase-2 plan, the P387 note); one pre-existing pyflakes note in `test_mtp_verify_scan.py` (`harness`).

## Rules learned

- Suites: fork `(cd mlx_vlm && ../.venv/bin/python -m pytest -q ./tests --ignore=tests/test_smoke.py -rs -p no:cacheprovider)` ≈ 2.5 min;
  stack from `benchmark/`: `../.venv-bench/bin/python -m pytest bench/tests -q -p no:cacheprovider -o faulthandler_timeout=600 -rs`.
  Never two suites at once; never edit a worktree while its suite runs. Audits: the 8 `dev/check_*.py --upstream-ref 952d4f6b`
  (`--strict` for deletions) from the worktree with `.venv/bin/python`.
- **Cursor:** `cursor-agent -p --output-format stream-json --model gpt-5.6-sol-high --mode ask --sandbox enabled --force --trust
  --workspace ~/ws/mlx-vlm "<prompt>" > out.jsonl`, review text = the `type=="result"` event's `result`. `--mode plan` can end on a
  `createPlan` call with no text (cause of every empty output this session). One run at a time; state "round k of 3".
- Formatting: `uvx --offline black@26.3.1`, `isort@5.13.2 --profile=black`, `pyflakes`. zsh: arrays for file lists. BSD sed chokes on
  the em dash — use Python for exact-line edits. The Edit tool needs a fresh Read after black rewrites a file.
- Tests that start processes own them in fixtures that kill the PGID and any self-recorded child pid at teardown; signal-sending
  tests trigger the signal deterministically from inside the code under test (a timer killed pytest once).
- macOS: no `os.waitid`; our unreaped child shows as a `Z` row with its lstart in `ps` (the harness anchors on that).
- Zero flakes; red-first honesty (say "helper absent" vs behavioural); check `git show --stat` after every commit.

Next decision id C187; discussion ids continue from P396.
