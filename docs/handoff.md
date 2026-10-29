# Handoff — 2026-10-29 (session 11: MTP ON provisional for all four MTP entries, pushed; P369 full runs started; B2 s7 built, reviewed, fixed)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C251, P533, P529, P528, P527, C250, C249, C248,
C247, P531, P530, …), then `docs/specs/p426-b2-tg1-wave2.md` (v3.2 incl. §16) with `docs/reviews/p426-b2/` (newest:
`test-writer2-delivery3b-s7.md`, `final-fix-queue.md`). Model names: FULL registry names only, always (chat included). Skills: four-eyes
0.7.0, review-panel. Review rounds: AGENTS.md's 3 per artifact (C238); both specs have used rounds 1–2, round 3 is in reserve.

## Goal and path (C218, C232, C234, C235, C236, C244, C247, C248)

MTP blessing for the four MTP entries on the serving build S′ (fork `1c7c8fa1`, mlx-serve `1ddf6f84`, mlx 0.32.4). Done: T3, Wave 1 on S′
for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, MTP ON PROVISIONAL for all four (C244, C247). Remaining:
- **P369 full on all four (C248 / C249 / C251)** — exactness certification; ON / OFF memory and speed also needed before CERTIFIED (P523).
- **B2 (s8 → s9, verify, fix, Accept) → v8 freeze → pilots → amendment → Wave 2 (first pick only) → B8 / B6 → the ship call.**

## State — session 11, 2026-10-29 ~07:30Z

- **Pushed:** stack `main` `4686919a` (C247: MTP ON PROVISIONAL for `Qwen3.8-27B-mlx-uniform-4bit`, `Qwen3.6-27B-Opus-Distill-OptiQ-4bit`,
  `Ornith-1.0-35B-mlx-uniform-4bit`; gate PASS). Unpushed docs commits after it: `90bf15be`, `6256e1aa`, `664f87ee`, + this handoff.
- **P369 S′ smokes (P519):** SMOKE_PASS ×3 (`$STACK_WORKDIR/p369/phase2/20261029-1cce312f-smoke-*-s2`): E1c T = 1K / 64K 158 / 158 rows
  each, max TV 0; E2 identical; E7b observed.
- **P369 full (C248), RUNNING:** `Qwen3.8-27B-mlx-uniform-4bit` (`run_p369_full.sh`, out `$STACK_WORKDIR/p369/phase2/20261029-1cce312f-full-uniform-s2`,
  log `c248-full.log`). Stack root = worktree `$STACK_WORKDIR/worktrees/stack-p369-full-off` (branch `p369-full-off` = `4686919a` +
  `7081c7af` all four OFF; P527: the orchestrator's OFF arm is the stack root's registry). Fork root `$STACK_WORKDIR/p369/fork-1cce312f`,
  `--reviewed-head 1cce312f` (C251). A full run is bound by its smoke's `stack_bench` tree (`HEAD:benchmark/bench`): the first `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`
  full attempt (07:17Z) refused in 8 s, no GPU (its 10-28 smoke predates P518's `benchmark/bench` change). Order (P534, lead call):
  `Qwen3.8-27B-mlx-uniform-4bit` → `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` → `Ornith-1.0-35B-mlx-uniform-4bit` (their 10-29 smokes bind) → a fresh
  `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` smoke on the all-OFF stack root, then its full. One GPU job at a time, a B2 delivery
  between runs (C249 option B).
- **B2 s7: built (delivery 1 + s7b P531 + s7c fixes P54 / P55 / P56), reviewed (test-writer 3b: fix then merge → fixed).** Implementer
  copy `$STACK_WORKDIR/b2/arm-rebased/mlx_local_stack` (uncommitted s7 changes on `aeb607b4`); eval copy `b2/eval-s7` = `aeb607b4` +
  `f0b755e6` (s7 delivery 1 + s7b; s7c NOT yet applied). Gate self-exclusion proven (full suite with `STACK_WORKDIR` set and
  `gate/RUNNING` held: no lock file created). s7 implementer session `f91e5dc1-eb14-4f5e-b39d-a4b61701ddfc` (Claude Sonnet 5.5).
- **B2 test-writer** (session `44568a2b-2638-419f-8c1d-17b471a74c5e`, cwd `b2/tw2/mlx_local_stack`, now on `61d31bcd` + its set; P533:
  keep resuming it — `total_cost_usd` in the CLI JSON is the session's running total, per-job cost is the increment, ≈ $5–10).

## Next, in order

1. When the `Qwen3.8-27B-mlx-uniform-4bit` full run ends (waiter): commit the docs (no process runs during a P369 run, not even a git hook), read its summary,
   record. Then: apply `runs/s7c.sonnet.diff` to `b2/eval-s7` (new commit), run the frozen s7 file there, commit s7 in `arm-rebased`
   ("scratch: B2 s7 …"), launch the s8 implementer (fresh Claude Sonnet 5.5, `b2/briefs/s8.md`, launcher pattern `runs/launch_s7.sh`).
2. Then the next full run (`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`, smoke `20261029-1cce312f-smoke-qwen36-s2`); test-writer s8 review in the gap
   after it; s9; full suite; final delivery; strict verify; final fix round (`docs/reviews/p426-b2/final-fix-queue.md`); Accept.
3. P527 guard (C251): fork dev-only, test-first, in `../mlx-vlm` AFTER the four full runs.
4. P503 (six load-sensitive tests incl. `test_m61_web_audit.py::test_real_system_override`), after s7 per lead rec.
5. Wave-1 S′ analysis: the cjudge / vision two-judge panel (C161); signals sheet when B8 exists.

## Copies to resolve

`$STACK_WORKDIR/t3/*` (T3 accepted + harvested: delete), `$STACK_WORKDIR/p369/fork-1cce312f` (keep through the full runs),
worktrees `stack-p426-s2-{off,on}` + branch `p426-on-s2` (keep until Wave 2's freeze; never push), worktree `stack-p369-full-off` +
branch `p369-full-off` (keep through the four full runs; never push), `$STACK_WORKDIR/b2/*` scratch (harvest at Accept, then delete;
`b2/arm-rebased` is the live B2 base, `b2/eval-s7` the s7 eval copy, `b2/selfexcl-s7` scratch, `b2/tw2-backup-20261029` the pre-rebase
test-writer copy backup).

## Rules learned (session 11)

- A resumed helper's CLI JSON `total_cost_usd` is cumulative for the session; per-job cost is the difference.
- The P369 orchestrator's OFF arm is `<stack-root>/main_models.yaml`: once an entry is ON on `main`, full / smoke runs need an all-OFF
  stack-root worktree (P527).
- A helper copy's test runner must not see the real `$STACK_WORKDIR` (`env -u STACK_WORKDIR`); s7 locks live under it.
- The test-writer's eval wrapper unsets `STACK_WORKDIR`: a self-exclusion check must set it explicitly.
- `--plan-only` stops after preflight; the registry byte-state check runs at the start of the real run.
- No process during a P369 run — tests, helpers or git hooks.

## Rules learned (sessions 9–10, still apply)

- Write a helper's brief in one call and launch it in another; never put brief text on a launcher's command line (P454).
- Never run a suite in a copy a helper is editing; check GitHub state before any merge.
- A spec change after a freeze invalidates tests: only the test-writer amends them; tag post-reveal amendments.
- Pin every format the spec leaves open before the test-writer's first delivery.
- An eval copy needs its submodules checked out; a frozen worktree needs `.venv`, `.venv-bench` and `src/mlx-vlm/.venv`.
- Never commit with `--no-verify` (or hooks disabled); use the per-line `allow-shorthand` marker.
- In zsh never name a loop variable `path`; split lists with `${=var}`.
- Never run anything while a gate runs; tests never read the live registry state (P518 / P531).

Next decision id C252; discussion ids continue from P534.
