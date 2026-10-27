# Handoff — 2026-10-27 (session 9 END ~21:40Z): T3 candidate reviewed (fix then merge); B2 s1–s6 built, s1–s5 fixed; GPU rehearsal on provisional S′

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C240, C239, C238, P504, P501, P500, P503, P499,
C236 …), then `docs/specs/p426-t3-serving-build.md` (v2.1) with `docs/reviews/p426-t3/`, and `docs/specs/p426-b2-tg1-wave2.md` (v3.2
incl. §16) with `docs/reviews/p426-b2/` (newest: `final-fix-queue.md`, `test-writer2-delivery2d-fix-s1-s5.md`). Model names: FULL
registry names only, always (chat included). Skills: four-eyes 0.7.0, review-panel (updated 2026-10-27). Review rounds were reset by
the operator: AGENTS.md's 3 per artifact (C238); both specs have used rounds 1–2, round 3 is in reserve.

## Goal and path (C218, C232, C234, C235, C236)

MTP blessing for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` first, on the new serving build S′ (C236: fork `c688e722`, mlx-serve
v0.3.0 `e6a7a5a`, mlx 0.32.4): **T3 accepted → push (P509) → S′ cut + two committed arm worktrees → Wave-1 rerun on S′** (label `s2`,
≈ 18–23 h GPU) while B2 finishes → B2 R1–R3 → v8 base → pilots → amendment → Wave 2 → B8 / B6 → ship call. P475 / P475a PARKED.

## T3 — next steps, in order (four-eyes strict; Go C238)

State: candidate = `$STACK_WORKDIR/t3/runs/impl-1.diff` (B0 `1a4187e6` + spec → candidate), rebuilt clean in `t3/eval/mlx_local_stack`
(commit `b3fd6073`, own venvs from the candidate locks). Frozen tests `t3/frozen1/` (19:33:33Z). Reports in `docs/reviews/p426-t3/`.
Checked by the designer: acceptance 1 (locks / venvs, independently), 3 (fork suite in a venv pinned to the candidate lock: MTP subset
1124 passed / 1 skipped / 1 xfailed; full 9206 passed / 18 skipped / 22 xfailed / 0 failed), F4 (`uv pip check`: no new conflicts,
two removed; seven pre-existing bench-tool conflicts remain).
1. **Record field names (designer ruling):** the designer writes `frozen.s2.json` with the CANDIDATE's names (`uv_lock_sha256`,
   `bench_lock_sha256`, … — list in `implementer-report.md`). Continue the T3 test-writer (claude `--resume
   1396ee76-210e-4425-93a6-b6ee50bcf58d`, cwd `t3/tw/mlx_local_stack`) to amend its fixture names and its 4 baseline-only support checks
   (class c), re-freeze, rerun on `t3/eval` (runner `t3/tw/bin/run_candidate_tests.sh`). This exercises the S′ path (43 tests blocked +
   17 vacuous passes so far).
2. **Strict verify** (review-panel `verify`, fresh `gpt-5.6-sol-high` + `glm-5.2-high`, read-only copy of `t3/eval`; brief = the
   candidate diff, the frozen tests, BOTH reports, spec v2.1, the round-1 / round-2 dispositions, the sensitive hunks: evidence isolation,
   expected-build binding, arms-as-commits restore check, venv checks, local gate, naming exemption). Briefs in a file, launch separately
   (P454).
3. **Fix round** (fresh Sonnet, once): F1 patch-exact seeding-test restore check; F2 exact registry restore (lines in place, one note in
   `generation_defaults`); F3 / **P507** `new_side.py` — lead rec: accept only the pinned pair `ecd97da3…` → the committed S′ lock sha
   (operator ask at Accept); F5 venv versions from dist-info deterministic; plus adopted verify findings. Test-writer adds failing-case
   tests.
4. **Smoke (acceptance 6, GPU):** stop the P499 rehearsal at an item boundary (`t3/rehearsal.pid`; `scripts/stack_stop.sh`; verify
   :8000 free, no survivors); from scratch OFF / ON worktrees of the final candidate (ON = + the restore commit), lean router per arm, P426
   entry, 3 requests, ON draft counters on every ≥ 2-token request, OFF none, teardown verified; check P504 (qualify's ON copy
   byte-identical) and #2545 not reaching M1.
5. **Local gate (acceptance 5, P508):** fork receipts `c688e722`, `e6a7a5a` in the GPU window (the gate refuses while the box is busy);
   the stack commit's receipt after the commit lands, before the push.
6. **Accept** (operator): final diff + findings; apply to `main` = merge GitHub `main` as B0 did (gitlinks `c688e722` / `e6a7a5a`, our
   handoff, C182 → C237) + the candidate; then rebuild main's `.venv` / `.venv-bench` from the new locks (the B2 copies symlink them).
7. **Push point (P509, lead rec):** right after Accept + gate receipts — one push of stack `main` (≈ 75 local commits; GitHub `main`
   merged) — ASK the operator. Never push `p426-on-s2`.
8. **S′ cut:** `p426-on-s2` = S′ + the restore commit; worktrees `$STACK_WORKDIR/worktrees/stack-p426-s2-{off,on}` (fresh venvs);
   `frozen.s2.json` (candidate names); then `bench.p426_wave1 --build s2 --stack-root-off … --stack-root-on … --out
   $STACK_WORKDIR/p426/wave1.s2 …` (detached, daemon, per-leg harvest commits `data(bench)`).

## B2 — state and next steps (four-eyes strict; Go C235; fix pass C239 done)

- Spec v3.2 at main `6fe4c1f6`+ (§16.7 rulings). Frozen tests `b2/frozen6/` (23 files, 20:56:47Z; `POST_REVEAL_TAGS.json`); test-writer
  Claude Opus 5.5 session `44568a2b-2638-419f-8c1d-17b471a74c5e` (cwd `b2/tw2/mlx_local_stack`).
- Slices in `b2/arm-sonnet/mlx_local_stack` (scratch commits): s1–s5 fixed `4cd17cc8`, **s6 candidate `eb445b80`** (frozen s6: 3 passed,
  1 failed — `test_new_the_watcher_takes_its_power_reading_only_from_the_injected_source`, `bench_watch.py:507` TypeError str vs float:
  triage pending). Arm-A sous-agent PAUSED for the session (operator; session-only, nothing in AGENTS.md).
- Next: (1) test-writer review of s6 (+ P38 coverage: snapshot drift after load, legacy chain runs no receipt checks); (2) **after T3
  lands, rebase the B2 slices onto the new `main`** (T3 and s7 both change `bench.local_gate`); (3) s7 (brief ready:
  `b2/briefs/s7.md`, incl. P36 / P37), s8 freeze + sequencer, s9 harvest; (4) full suite, test-writer final delivery, strict verify, the
  final fix round (`docs/reviews/p426-b2/final-fix-queue.md`), Accept.

## GPU

P499 OFF tg1 rehearsal on the provisional S′ (`t3/stack-prov`, `fa8f7b13`), out-root `t3/tg1-rehearsal-20261027`: block 1 (P426 entry)
done — Python 22 / 22 rc 0, Go 21 items mean ≈ 410–980 s; block 2 (`Qwen3.8-27B-mlx-uniform-4bit`) running. Stop it for the T3 smoke.
TODO: compare its Go walls with P486's (old build); never graded / pooled.

## Other open items

- C237 PARKED (C240). P503 at the designer's discretion after B2 (C240). P498 (pins move only via certification) lead rec, not ruled.
  P478 after B2.
- sous-agent: NetApp/sous-agent#11 holds all feedback (latest 6451488159).

## Copies to resolve

`$STACK_WORKDIR/t3/{stack-prov, impl, tw, eval, dop, dop2, venv-fork, venv-fork2, frozen1}`, `$STACK_WORKDIR/b2/{tw, tw2, arm-sonnet,
arm-sous*, eval, eval-s3, eval-s4, eval-s5, eval-fix, dop, dop2, frozen*, judge-s3}` — scratch; harvest accepted candidates at Accept,
then delete. No git worktrees of the main checkout.

## Rules learned (session 9)

- Write a helper's brief in one call and launch it in another; never put brief text on a launcher's command line (P454).
- Never run a suite in a copy a helper is editing.
- Check the stack's and the forks' GitHub state before any merge.
- A spec change after a freeze invalidates tests: only the test-writer amends them; tag post-reveal amendments.
- Frozen-test fixtures and the code must agree on names the spec leaves open: pin every record field the designer writes.

Next decision id C241; discussion ids continue from P509.
