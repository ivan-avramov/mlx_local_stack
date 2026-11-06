# Handoff — 2026-11-05 (session 18, IN PROGRESS: C296 (1) + C297 built; arms re-prepared on `15d90757`; gate on `e86a39e3` running; next: push ask, OFF preflights, smokes, then P658 in the fork)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: S18-P3, C297, S18-P2, S18-P1, C296, P659 …),
then `docs/specs/p475-stage1-contract.md` (v1.3) and `docs/reviews/p475s1/dispositions.md`. Model names: FULL registry names only.
Review rounds: 3 per artifact. Operator stance: bias for quality; drive to certified picks; ask only at Go / Accept / pushes / scope
changes; lead calls filed as they land; offer a fresh session at clean boundaries.

Discussion ids restarted at P1 in session 18; durable records cite them as `S18-P<n>` (historical P1–P659 unchanged). Next decision id
C298; next discussion id S18-P4.

## THE GOAL

Certify the two picks in their ideal config. `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`: DONE — MTP ON `CERTIFIED P426 2026-11-04`
(C291). `Qwen3.8-27B-mlx-uniform-4bit`: its KV format first (P475 stage 1: memory / speed matrix of six arms, MTP ON as shipped; the
operator weighs the table; stage 2 quality only for formats kept), then its MTP ON vs OFF re-certification on the chosen format.

## FIRST — verify (each "no" is a blocker)

1. Nothing running: no router on :8000, no P475 orchestrator / `qualify` / `worker.py` (check with a script file such as the one
   below — never put BUSY markers in your own command line: session 18 tripped its own check once).
2. Pushes: `origin/main` = `1514f4b7`. Local `main` carries `c85bb865` (results) … `e86a39e3` (gate receipt pending at this
   writing: `$STACK_WORKDIR/gate/stack-e86a39e3…json`) and the session-18 commits `8ce7befa` … `15d90757` + this note. No push
   without an in-turn ask.
3. Arm worktrees `$STACK_WORKDIR/worktrees/p475-u4-{n16,af8,tq8,af4,tq4,tq4-off}` on local branches `p475-u4-*` off base `15d90757`
   (each clean, diff = `main_models.yaml` only; `.venv`, `.venv-bench` and the fork venv built by `prepare`).

## Done in session 18

- `53e2e321` **C296 (1) part 1** (red tests first, `test_c296_fixes.py`): P655 `--base` resolved to the full sha; P656 1–2
  environmental preflight refusals = `NOT_STARTED` (no attempt, never final; `run` stops, never refuses the arm) — **proven live**
  (N16 during the gate: `LockRefused: gate/RUNNING`, 0 attempts); P656 3 `prepare` builds `p369/phase2/` + the fork venv (pins
  from the arm `.venv` freeze; proven: mlx 0.32.4 / transformers 5.15.0); P656 4–5 stderr tail kept, `RealOps.run` reaps the group.
- `bc07cabc` **C297 / S18-P1 (c)**: `run_capacity --out-dir`; legs write to `$STACK_WORKDIR/p475/legs/<leg>/capacity/`; R1 stays
  strict (the ruled P659 exit-only tolerance superseded: it left each arm's second leg refused). Fakes now dirty a worktree on any
  driver write. Contract v1.3. P475 + capacity suites 895 passed.
- **S18-P2 done:** `stack-p426-{off,on}` / `stack-c258x-off` removed (logs in `$STACK_WORKDIR/archive/session18-worktrees/`),
  local `p426-{off,on}` deleted (commits on `origin/archive/p426-wave2-*`), `c258x-off` → local `archive/c258x-off`.
- **Re-prepare:** old `$STACK_WORKDIR/p475/` + the N16 worktree's logs / smoke outputs archived in
  `$STACK_WORKDIR/archive/p475-base-1554bfe1/`; old arm branches → local `archive/p475-u4-<arm>-1554bfe1`; `prepare --base
  15d90757` clean.

## Next, in order

1. Gate receipt for `e86a39e3`: PASS → push ask (`git push origin e86a39e3:refs/heads/main`); FAIL → diagnose.
2. The six MTP-OFF preflights after the gate (stdin workaround for P656 item 6: `cd benchmark; P475_ARMS=N16,AF8,TQ8,AF4,TQ4,TQ4-OFF
   ../.venv-bench/bin/python - < <runner>` calling `bench.p475_kv.preflight()`; the runner is in the session-18 scratchpad —
   recreate it from that description if gone). `run` reuses PASS records.
3. Smokes (N16, TQ4) detached: `run --smoke`; D1 answered by the TQ4 smoke; expect a short list of fail-closed integration bugs.
4. P658 (a) fork four-eyes light (as C296 (2)): `qualify --kv-arm --predictor on --engagement-only` + P656 item 6; fork gate; fork
   push ask.
5. Stack gitlink bump + `LIVE_GITLINKS` (P632), S18-P3 if approved, the ON engagement check wired for ON arms; one stack gate; push
   ask. Re-prepare on that base, OFF preflights + ON engagement checks, smokes, full run (12 legs, ≈ 13 h GPU). Harvest → generated
   `MATRIX.Qwen3.8-27B-mlx-uniform-4bit.md` → operator; push ask for results + scrubbed logs to `evidence`.

Open, lower priority: S18-P3 (preflight record bound to its base), P643, P642's two process gaps.

## Worktrees / scratch (resolve each)

- Keep: the six `p475-u4-*` arm worktrees + branches (serve P475 stage 1 until the step-5 re-prepare).
- Local archive branches (no push): `archive/p475-u4-*-1554bfe1`, `archive/c258x-off`.

## Rules learned (session 18)

- An approved fix can be incomplete: trace it across every leg that reuses the same state (the P659 exit-only tolerance vs the
  entry check on an arm's second leg).
- Make the fake reproduce the real-box fact first (driver writes dirty the worktree); the red test then is the box failure verbatim.
- A busy check that greps `ps` must not run with its patterns in its own argv — put it in a script file.
- `git worktree remove` refuses worktrees with submodules: verify the submodules clean first, then `--force`.
