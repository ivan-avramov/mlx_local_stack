# Handoff — 2026-10-29 (session 10 checkpoint ~00:30Z: Wave 1 on S′ done, MTP-ON provisional, all pushed): T3 candidate reviewed (fix then merge); B2 s1–s6 built, s1–s5 fixed; GPU rehearsal on provisional S′

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

## Next, in order

1. **B2:** launch s7 (brief `b2/briefs/s7.md`) in the rebased copy `$STACK_WORKDIR/b2/arm-rebased/mlx_local_stack` (main + s1–s5 fixed +
   s6; S′ submodules; `main`'s venvs). Note: `main` is now MTP ON — B2 tests or fixtures that read the live registry and assume
   C177 OFF will fail the same way T3's did (P518); pin them to `benchmark/bench/tests/fixtures/p426_off/`. Then the test-writer
   (B2 session `44568a2b…`; give it a copy of the rebased base) reviews s7; s8 → s9; full suite; final delivery; strict verify; final
   fix round (`docs/reviews/p426-b2/final-fix-queue.md`); Accept. Wave 2's OFF arm = `main` + a revert of the C244 restore.
2. **P503 (lead rec: right after s7):** five load-sensitive tests (three stack m64/agentbench, one more m64, one fork distributed).
3. Wave-1 S′ analysis: the cjudge / vision panel (C161), the signals sheet when B8 exists; README evidence rows.
4. Queued: the naming scan treats committed verbatim panel / helper outputs as data (C245); never commit with `--no-verify`.

## B2 — state (session 10)

- s6 reviewed (delivery 2e, `docs/reviews/p426-b2/test-writer2-delivery2e-s6.md`): fix then merge; P47 / P48 / P50 / P51 / P52 queued
  in `final-fix-queue.md`, P53 declined; P510 interval format pinned (epoch seconds), malformed-interval crash queued. Copy
  `b2/eval-s6` (submodules populated) = s1–s5 fixed + s6 + the test-writer's current set: 109 failed / 334 passed, all classified.
- Next: after T3 lands, rebase the slices onto the new `main`; then s7 (`b2/briefs/s7.md`), s8, s9, full suite, final delivery,
  strict verify, final fix round, Accept.

## GPU

P499 OFF tg1 rehearsal on the provisional S′ (`t3/stack-prov`, `fa8f7b13`), out-root `t3/tg1-rehearsal-20261027`: block 1 (P426 entry)
done — Python 22 / 22 rc 0, Go 21 items mean ≈ 410–980 s; block 2 (`Qwen3.8-27B-mlx-uniform-4bit`) running. Stop it for the T3 smoke.
TODO: compare its Go walls with P486's (old build); never graded / pooled.

## Other open items

- C237 PARKED (C240). P503 at the designer's discretion after B2 (C240). P498 (pins move only via certification) lead rec, not ruled.
  P478 after B2.
- sous-agent: NetApp/sous-agent#11 holds all feedback (latest 6451488159).

## Copies to resolve

`$STACK_WORKDIR/t3/{stack-prov, impl, tw, eval, fix, vfy, smoke, smoke-off, smoke-on, accept-dry, forkcheck, baselines, dop, dop2, venv-fork, venv-fork2, frozen1–4}` (T3 accepted: harvested; delete after the S′ cut), `$STACK_WORKDIR/b2/{tw, tw2, arm-sonnet,
arm-sous*, eval, eval-s3, eval-s6, eval-s4, eval-s5, eval-fix, dop, dop2, frozen*, judge-s3}` — scratch; harvest accepted candidates at Accept,
then delete. No git worktrees of the main checkout.

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
- In zsh never name a loop variable `path` (it is tied to `PATH`).

Next decision id C246; discussion ids continue from P517.
