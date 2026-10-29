# Handoff — 2026-10-29 (session 10 END ~01:00Z: Wave 1 on S′ done, MTP-ON provisional for the first pick, all pushed; next B2 s7): T3 candidate reviewed (fix then merge); B2 s1–s6 built, s1–s5 fixed; GPU rehearsal on provisional S′

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C240, C239, C238, P504, P501, P500, P503, P499,
C236 …), then `docs/specs/p426-t3-serving-build.md` (v2.1) with `docs/reviews/p426-t3/`, and `docs/specs/p426-b2-tg1-wave2.md` (v3.2
incl. §16) with `docs/reviews/p426-b2/` (newest: `final-fix-queue.md`, `test-writer2-delivery2d-fix-s1-s5.md`). Model names: FULL
registry names only, always (chat included). Skills: four-eyes 0.7.0, review-panel (updated 2026-10-27). Review rounds were reset by
the operator: AGENTS.md's 3 per artifact (C238); both specs have used rounds 1–2, round 3 is in reserve.

## Goal and path (C218, C232, C234, C235, C236)

MTP blessing for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` first, on the new serving build S′ (C236: fork `c688e722`, mlx-serve
v0.3.0 `e6a7a5a`, mlx 0.32.4): **T3 accepted → push (P509) → S′ cut + two committed arm worktrees → Wave-1 rerun on S′** (label `s2`,
≈ 18–23 h GPU) while B2 finishes → B2 R1–R3 → v8 base → pilots → amendment → Wave 2 → B8 / B6 → ship call. P475 / P475a PARKED.

## State — session 10, 2026-10-29 ~00:30Z

- **Pushed** (all through the gate hooks): stack `main` `3d7cfaac`, mlx-vlm `1cce312f` (P369 harness production pin → `b26fa7c9`, dev
  only), mlx-serve `1ddf6f84`. Earlier the same day: T3 (C243), the one-time `--no-verify` push (C245).
- **Wave 1 on S′: DONE, 30 / 30 VALID**, evidence committed per leg; math500 graded (`acc_strict` 0.98 / 0.98, 0.94 / 0.94); ON outputs
  byte-identical to OFF on 166 / 166 items (math500 100, cjudge 40, vision 20 by description / verdict / tokens, reasoning 6); decode
  1.6–1.7×; 256K peak +0.32 GB. Not yet: the cjudge / vision two-judge panel (C161), the B8 signals sheet.
- **C244 done:** P369 regression smoke on S′ SMOKE_PASS (`$STACK_WORKDIR/p369/phase2/20261028-1cce312f-smoke-fable-s2`); MTP ON by default,
  PROVISIONAL, for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` on `main` (`3d7cfaac`); `Qwen3.8-27B-mlx-uniform-4bit` OFF.
- **P518 / C246 done:** T3's tests read a sha256-pinned OFF fixture (`benchmark/bench/tests/fixtures/p426_off/`, naming-exempt as data).
- The S′ arm worktrees (`$STACK_WORKDIR/worktrees/stack-p426-s2-{off,on}`, branch `p426-on-s2`) are kept for the Wave-1 analysis and
  until Wave 2's v8 freeze; never push `p426-on-s2`.

## Waiting on the operator

- **P519 (asked, unanswered):** `Qwen3.8-27B-mlx-uniform-4bit` provisional MTP-ON — run the P369 regression smoke on S′ (≈ 30 min GPU,
  command as C244's with `--pick Qwen3.8-27B-mlx-uniform-4bit`, fork root `$STACK_WORKDIR/p369/fork-1cce312f`); on PASS, the same
  restore-form commit for that entry (its served KV is TurboQuant 4, itself PROVISIONAL pending P405 R6; its HF drafter card still says
  PROBE-ONLY). `Ornith-1.0-35B-mlx-uniform-4bit` and `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` stay OFF (per-entry re-cert, plan §11).

## Next, in order

1. **B2 s7.** Rebased copy `$STACK_WORKDIR/b2/arm-rebased/mlx_local_stack` = `main` `61d31bcd` (MTP ON, P518) + `86341e04` s1–s5 fixed
   + `aeb607b4` s6; S′ submodules; `main`'s venvs; the test-writer's current B2 set copied in (untracked). Its B2 tests: 115 failed /
   713 passed (`$STACK_WORKDIR/b2/rebased-b2-tests.out`): 109 as on the old base (later slices + queued defects) plus 6 NEW from
   the rebase — `test_b2_s1_cli` ×4 and `test_b2_s2_probe` ×1 run the chain with `--predictor off` against the live registry, which
   is now ON (C221 refuses, correctly) → the P518 fix (pin to `benchmark/bench/tests/fixtures/p426_off/`); `test_b2_frozen_s0_support`
   +1 pins S's fork shas (base identity → S′). Fold both into the s7 brief (implementer: its own s1/s2 tests; the test-writer: s0 and
   any frozen test reading the live registry). Then the s7 implementer (fresh Claude Sonnet 5.5; brief `b2/briefs/s7.md`), the
   test-writer review (B2 session `44568a2b-2638-419f-8c1d-17b471a74c5e`, cwd `b2/tw2/mlx_local_stack` — rebase that copy onto the
   same base first), s8 → s9, full suite, final delivery, strict verify, final fix round (`docs/reviews/p426-b2/final-fix-queue.md`),
   Accept. Wave 2's OFF arm = `main` + a revert of the C244 restore; ON = that + the restore (the P511 check holds).
2. **P503 (lead rec: right after s7):** five load-sensitive tests (stack: agentbench P22, m64 selftest, m64 oc-contract ×2; fork:
   `test_models.py::test_distributed_model[minimax_m3_packed-bfloat16-4]`). Root-cause, failing test first, zero-flakes.
3. Wave-1 S′ analysis: the cjudge / vision two-judge panel (C161); the signals sheet when B8 exists.
4. Queued small: the naming scan treats committed verbatim panel / helper outputs as data (C245).

## GPU

Idle. Wave 1 on S′ done. Candidate GPU work: P519 smoke (if approved); later the Wave-2 pilot (needs B2 Accept). The P499 rehearsal is
stopped for good (its 15 block-2 Go walls are the data; `t3/tg1-rehearsal-20261027`, never graded / pooled). One resident model; a
gate run needs a quiet box (no BUSY process, nothing else running).

## Other open items

- C237 PARKED (C240). P503 (C240: designer's discretion; lead rec now: right after s7). P498 (pins move only via certification) lead rec, not ruled.
  P478 after B2.
- sous-agent: NetApp/sous-agent#11 holds all feedback (latest 6451488159).

## Copies to resolve

`$STACK_WORKDIR/t3/{stack-prov, impl, tw, eval, fix, vfy, smoke, smoke-off, smoke-on, accept-dry, forkcheck, baselines, p518, dop, dop2, venv-fork, venv-fork2, frozen1–4}` (T3 accepted + harvested: delete), `$STACK_WORKDIR/p369/fork-1cce312f` (smoke fork root; keep for P519), git worktrees `$STACK_WORKDIR/worktrees/stack-p426-s2-{off,on}` + local branch `p426-on-s2` (keep until Wave 2's freeze; never push), `$STACK_WORKDIR/b2/{tw, tw2, arm-sonnet,
arm-sous*, eval, eval-s3, eval-s6, eval-s4, eval-s5, eval-fix, dop, dop2, frozen*, judge-s3}` — scratch; harvest accepted candidates at Accept,
then delete (`b2/arm-rebased` is the live B2 base).

## Rules learned (session 9)

- Write a helper's brief in one call and launch it in another; never put brief text on a launcher's command line (P454).
- Never run a suite in a copy a helper is editing.
- Check the stack's and the forks' GitHub state before any merge.
- A spec change after a freeze invalidates tests: only the test-writer amends them; tag post-reveal amendments.
- Frozen-test fixtures and the code must agree on names the spec leaves open: pin every record field the designer writes.

## Rules learned (session 10)

- Every format the spec leaves open (record fields, restore bytes, value encodings) is pinned by the designer before the test-writer's first delivery; three such mismatches (P510, P511, the record names) cost a delivery each.
- cursor-agent briefs: pass a one-line argv pointing at the brief file (P454), even when the text is BUSY-free.
- An eval copy needs its submodules checked out (tests read the fork's `pins.json`).
- A frozen worktree needs `.venv`, `.venv-bench` and `src/mlx-vlm/.venv` (fork lock) — `qualify` runs from the fork venv (P514).
- Never commit with `--no-verify`; use the per-line `allow-shorthand` marker (the pre-push scan re-checks every commit, C245).
- In zsh never name a loop variable `path` (it is tied to `PATH`); split lists with `${=var}`.
- Never run anything (tests, helpers) while a gate runs; a gate FAILs on any BUSY-named process, incl. test fakes.
- Tests never read the live registry state; pin a fixture (P518) — the registry flips with every certification.

Next decision id C247; discussion ids continue from P519.
