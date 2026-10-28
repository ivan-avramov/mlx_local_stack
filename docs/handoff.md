# Handoff — 2026-10-28 (session 10 checkpoint ~04:00Z: T3 accepted; was session 9 END 2026-10-27 ~21:40Z): T3 candidate reviewed (fix then merge); B2 s1–s6 built, s1–s5 fixed; GPU rehearsal on provisional S′

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C240, C239, C238, P504, P501, P500, P503, P499,
C236 …), then `docs/specs/p426-t3-serving-build.md` (v2.1) with `docs/reviews/p426-t3/`, and `docs/specs/p426-b2-tg1-wave2.md` (v3.2
incl. §16) with `docs/reviews/p426-b2/` (newest: `final-fix-queue.md`, `test-writer2-delivery2d-fix-s1-s5.md`). Model names: FULL
registry names only, always (chat included). Skills: four-eyes 0.7.0, review-panel (updated 2026-10-27). Review rounds were reset by
the operator: AGENTS.md's 3 per artifact (C238); both specs have used rounds 1–2, round 3 is in reserve.

## Goal and path (C218, C232, C234, C235, C236)

MTP blessing for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` first, on the new serving build S′ (C236: fork `c688e722`, mlx-serve
v0.3.0 `e6a7a5a`, mlx 0.32.4): **T3 accepted → push (P509) → S′ cut + two committed arm worktrees → Wave-1 rerun on S′** (label `s2`,
≈ 18–23 h GPU) while B2 finishes → B2 R1–R3 → v8 base → pilots → amendment → Wave 2 → B8 / B6 → ship call. P475 / P475a PARKED.

## T3 — ACCEPTED (C243) and on `main` — session 10, 2026-10-28 ~04:00Z

`main`: `9e4ab5da` (GitHub `main` merged as B0 did; gitlinks → S′ `1c7c8fa1` / `1ddf6f84`, C242) + `d4861621` (the T3 change: impl-1 +
fix round 1 + the C242 pin move; frozen4 tests; fork skip baselines). Venvs rebuilt (mlx 0.32.4). Fork hygiene commits (local only, NOT
pushed): mlx-vlm `1c7c8fa1` (uv.lock refresh), mlx-serve `1ddf6f84` (ruff format; local `main` fast-forwarded to `e6a7a5a` first).
Next, in order:
1. Gate receipts: forks `1ddf6f84`, `1c7c8fa1`; stack run 1 lists the stack skips → review → commit `benchmark/gate/stack.skips.txt`
   (`chore(stack)`) → stack run 2 on that HEAD → PASS (box quiet; `$STACK_WORKDIR/gate/`).
2. Push (P509, ASK): forks first (gitlinks must be reachable), then stack `main`. Never push `p426-on-s2`.
3. S′ cut: OFF = `main` HEAD after step 1; `p426-on-s2` = OFF + the P511 restore commit (bytes as `t3/smoke-on`'s, checked by
   `restore_diff_problems` → `[]`); worktrees `$STACK_WORKDIR/worktrees/stack-p426-s2-{off,on}` (fresh venvs, submodules); `frozen.s2.json`
   with the candidate's field names; then `bench.p426_wave1 --build s2 --stack-root-off … --stack-root-on … --out
   $STACK_WORKDIR/p426/wave1.s2 …` detached + watcher daemon; per-leg harvest `data(bench)` commits.

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

Next decision id C244; discussion ids continue from P512.
