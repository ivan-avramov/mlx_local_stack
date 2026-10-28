# Handoff — 2026-10-28 (session 10 checkpoint ~15:00Z: T3 accepted + pushed; Wave 1 on S′ running): T3 candidate reviewed (fix then merge); B2 s1–s6 built, s1–s5 fixed; GPU rehearsal on provisional S′

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C240, C239, C238, P504, P501, P500, P503, P499,
C236 …), then `docs/specs/p426-t3-serving-build.md` (v2.1) with `docs/reviews/p426-t3/`, and `docs/specs/p426-b2-tg1-wave2.md` (v3.2
incl. §16) with `docs/reviews/p426-b2/` (newest: `final-fix-queue.md`, `test-writer2-delivery2d-fix-s1-s5.md`). Model names: FULL
registry names only, always (chat included). Skills: four-eyes 0.7.0, review-panel (updated 2026-10-27). Review rounds were reset by
the operator: AGENTS.md's 3 per artifact (C238); both specs have used rounds 1–2, round 3 is in reserve.

## Goal and path (C218, C232, C234, C235, C236)

MTP blessing for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` first, on the new serving build S′ (C236: fork `c688e722`, mlx-serve
v0.3.0 `e6a7a5a`, mlx 0.32.4): **T3 accepted → push (P509) → S′ cut + two committed arm worktrees → Wave-1 rerun on S′** (label `s2`,
≈ 18–23 h GPU) while B2 finishes → B2 R1–R3 → v8 base → pilots → amendment → Wave 2 → B8 / B6 → ship call. P475 / P475a PARKED.

## State — session 10, 2026-10-28 ~15:00Z

- **T3 accepted (C243), on `main`, PUSHED** (C245: stack `fd5ef108..10014b4a` via a one-time `--no-verify` — naming false positives in
  old commits; forks mlx-vlm `c688e722..1c7c8fa1`, mlx-serve `e6a7a5a..1ddf6f84` through their gates). Receipts PASS in
  `$STACK_WORKDIR/gate/` for stack `10014b4a`, `1c7c8fa1`, `1ddf6f84`. Skip baselines `benchmark/gate/{stack,mlx-vlm,mlx-serve}.skips.txt`.
- **Wave 1 on S′ RUNNING** (sequencer PID in `$STACK_WORKDIR/p426/wave1.s2.pid`, out `$STACK_WORKDIR/p426/wave1.s2`, log
  `sequence.log`): 15 / 30 VALID (10 smokes + math500 ×4 + cjudge off-b1) at 14:36Z; ETA ≈ 22:00–23:00Z. Arms: OFF worktree
  `$STACK_WORKDIR/worktrees/stack-p426-s2-off` at `10014b4a`, ON `…-s2-on` on local branch `p426-on-s2` (`f2b61127`, P511 restore; NEVER
  push); `frozen.s2.json` in `$STACK_WORKDIR/p426/`. Two archived attempts (P513 busy waiter, P514 fork venv). Monitor ONLY by port /
  PID / log lines — never a BUSY string on any command line. After each leg: commit its harvested dossier + rows (`data(bench)`, per
  leg, hooks on; the loop in this session's history: rows `benchmark/results/<entry>/<axis-prefix>.<tune>.*`, vision → `vision_gate`).
- `main` is 18 commits ahead of GitHub (docs + Wave-1 evidence); push after Wave 1 with a fresh stack gate receipt (box quiet).

## Next, in order

1. As each Wave-1 leg ends: commit its evidence. At the end: grade (generate→grade over HTTP per `benchmark/README.md`), the
   two-judge panel (C161), README / campaign-results evidence rows; report per axis to the operator.
2. **C244:** after Wave 1, the P369 regression smoke on S′ (`docs/specs/p369-phase2-run-plan.md`, smoke15 ≈ 30 min GPU; fork
   `dev/p369_phase2/`); PASS → one `main` commit = the `p426-on-s2` restore bytes (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` only, `PROVISIONAL P426`) → stack gate →
   push (ask); FAIL → stay OFF, report.
3. B2: rebase s1–s6 onto the new `main` (T3 and s7 both touch `bench.local_gate`; the B2 copies symlink `main`'s venvs, now mlx
   0.32.4); then s7 → s8 → s9, full suite, final test-writer delivery, strict verify, final fix round, Accept. With `main` ON after
   C244, Wave 2's OFF arm = `main` + a revert commit.
4. Queued small changes: the naming scan treats committed verbatim panel / helper outputs as data (C245); P503 (three
   load-sensitive tests) after B2; the frozen-worktree procedure includes `src/mlx-vlm/.venv` (P514).

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
