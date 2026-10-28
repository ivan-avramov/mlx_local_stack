# Handoff — 2026-10-27 (session 10 checkpoint ~23:35Z; was session 9 END ~21:40Z): T3 candidate reviewed (fix then merge); B2 s1–s6 built, s1–s5 fixed; GPU rehearsal on provisional S′

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C240, C239, C238, P504, P501, P500, P503, P499,
C236 …), then `docs/specs/p426-t3-serving-build.md` (v2.1) with `docs/reviews/p426-t3/`, and `docs/specs/p426-b2-tg1-wave2.md` (v3.2
incl. §16) with `docs/reviews/p426-b2/` (newest: `final-fix-queue.md`, `test-writer2-delivery2d-fix-s1-s5.md`). Model names: FULL
registry names only, always (chat included). Skills: four-eyes 0.7.0, review-panel (updated 2026-10-27). Review rounds were reset by
the operator: AGENTS.md's 3 per artifact (C238); both specs have used rounds 1–2, round 3 is in reserve.

## Goal and path (C218, C232, C234, C235, C236)

MTP blessing for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` first, on the new serving build S′ (C236: fork `c688e722`, mlx-serve
v0.3.0 `e6a7a5a`, mlx 0.32.4): **T3 accepted → push (P509) → S′ cut + two committed arm worktrees → Wave-1 rerun on S′** (label `s2`,
≈ 18–23 h GPU) while B2 finishes → B2 R1–R3 → v8 base → pilots → amendment → Wave 2 → B8 / B6 → ship call. P475 / P475a PARKED.

## T3 — state and next steps (four-eyes strict; Go C238) — session 10 checkpoint 2026-10-27 ~23:35Z

Done this session: (1) record names ruled = the candidate's; test-writer delivery 3 (`docs/reviews/p426-t3/test-writer-delivery3.md`):
fixtures renamed, 4 support checks fixed, a control twin on every refusal test → candidate 137 / 138 (the 1 = F1), baseline 93 failed
(all b); **frozen2** `t3/frozen2/` 23:22:51Z. (2) Strict verify (round 1 of 3) sol + glm → `change-verify.dispositions.md`: V1 / V2
exact-bytes restore (P511 pins the bytes), V3 / P507 pinned lock pair, V4 dist-info fail-closed, V5 plan §2 S-era bullets, V6 `--build
s` on the existing test; V7 declined. (3) Fix round launched 23:25Z: fresh Claude Sonnet 5.5, copy `t3/fix/mlx_local_stack` (base
`b3fd6073` + `77244972` docs; own venvs; frozen2 installed), brief `t3/briefs/fix-1.md`, outputs `t3/runs/fix-1.*`.
Next, in order:
1. Judge the fix report; export `fix-1.diff` (against `77244972`); build a clean eval copy (B0 + spec + candidate + fix, own venvs).
2. Test-writer delivery 4 (`--resume 1396ee76-…`): amend the restore fixture to P511 (expected: its correct-restore controls are
   refused by the fixed candidate until then), failing-case tests for V1–V4 / V6, run frozen set on baseline + fixed candidate.
3. Re-freeze (frozen3). No second verify unless the budget allows (verify budget spent: one per work item).
4. Smoke (acceptance 6, GPU): stop the P499 rehearsal at an item boundary (`t3/rehearsal.pid` = 86865; `scripts/stack_stop.sh`;
   verify :8000 free, no survivors); OFF / ON worktrees of the final candidate from scratch (ON = + the P511 restore commit); lean
   router per arm; 3 requests; ON draft counters on every ≥ 2-token request (worker log `$TMPDIR/mlx-manager-logs/<model>.log`
   `Request completed` + `draft_n=`), OFF none; teardown verified; P504 qualify ON copy byte-identical; #2545 not reaching M1.
5. Local gate receipts `c688e722`, `e6a7a5a` in that GPU window; stack receipt after the commit lands, before the push.
6. Accept (operator): final diff + findings (P507 / P510 / P511 ruled, C241); apply as B0 did; rebuild main's venvs.
7. Push point P509 (ask). 8. S′ cut + `p426-on-s2` (P511 form) + worktrees + `frozen.s2.json` (candidate names) + Wave 1 `--build s2`.

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

`$STACK_WORKDIR/t3/{stack-prov, impl, tw, eval, fix, vfy, dop, dop2, venv-fork, venv-fork2, frozen1, frozen2}`, `$STACK_WORKDIR/b2/{tw, tw2, arm-sonnet,
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

Next decision id C243; discussion ids continue from P512.
