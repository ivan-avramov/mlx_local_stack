# Handoff — 2026-11-06 (session 18: P658 (a) accepted + fork pushed `e3e38397`; stack step 2 built `97672222`; full stack gate on `9adbae45` running; next: stack push ask, re-prepare, OFF preflights + ON engagement checks, smokes, full run)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C301, C300, S18-P8, C299, C298, S18-P4, S18-P3,
C297 …), then `docs/specs/p475-stage1-contract.md` (v1.4), `docs/specs/p658-qualify-engagement-only.md` and
`docs/reviews/p658/dispositions.md`. Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance: bias for
quality; drive to certified picks; ask only at Go / Accept / pushes / scope changes; lead calls filed as they land; offer a fresh
session at clean boundaries.

Discussion ids restarted at P1 in session 18; durable records cite them as `S18-P<n>`. Next decision id C302; next discussion id
S18-P11 (a new session may restart at `S19-P1`).

## THE GOAL

Certify the two picks in their ideal config. `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`: DONE — MTP ON `CERTIFIED P426 2026-11-04`
(C291). `Qwen3.8-27B-mlx-uniform-4bit`: its KV format first (P475 stage 1: memory / speed matrix of six arms, MTP ON as shipped; the
operator weighs the table; stage 2 quality only for formats kept), then its MTP ON vs OFF re-certification on the chosen format.

## FIRST — verify (each "no" is a blocker)

1. Nothing running: no router on :8000, no P475 orchestrator / `qualify` / `worker.py`. Check with a script file, never with the
   patterns in your own argv.
2. Gate: the full stack gate on `9adbae45` was started at 2026-11-06 ≈ 09:10 local (log `$STACK_WORKDIR/scratch/p475s1/gate-9adbae45.log`,
   receipt `$STACK_WORKDIR/gate/stack-9adbae45…json`). PASS → push ask for `origin/main` `e86a39e3..9adbae45` (+ the docs-only tail);
   FAIL → diagnose (P643 is the known load-sensitive test).
3. Forks: `../mlx-vlm` = origin = `e3e38397` (pushed session 18); `../mlx-serve` = `1ddf6f84`. The stack gitlink `src/mlx-vlm` =
   `e3e38397` from `97672222` on.
4. Arm worktrees `$STACK_WORKDIR/worktrees/p475-u4-*` are on the OLD base `15d90757` (fork gitlink `d94e38a9`): re-prepare (Next 2)
   before any preflight.

## Done in session 18

- **C296 (1)** `53e2e321`: P655 base resolution; P656 1–5 (NOT_STARTED preflights, proven live; `prepare` builds `p369/phase2/` + the
  fork venv; stderr tail; process-group reap).
- **C297** `bc07cabc`: `run_capacity --out-dir`; legs write under `$STACK_WORKDIR/p475/legs/<leg>/capacity/`; R1 strict.
- **S18-P2**: the P426 / C258 worktrees removed. **C298** `5920015e` / `d13b13ff`: old-base dossiers archived under
  `results/p475/archive/<base12>/`.
- On base `15d90757`: six OFF preflights PASS; smokes `u4-n16-smoke.a2` + `u4-tq4-smoke.a1` VALID (`7c030035`); D1 answered (psutil
  shows no `KV_*` / `TQ_*` in the worker env).
- **P658 (a)** four-eyes light (C299 Go, C300 Accept; `docs/reviews/p658/`): fork `a1e23203` (frozen tests) + `e3e38397`
  (`qualify --kv-arm --predictor on --engagement-only`; drafter-cache K3 check; `engagement_only: true, certifies: false`;
  `bench.p475_kv` in `LAUNCHER_MODULES`). Fork gate PASS 10,008; pushed (C301).
- **Stack step 2** `97672222` (C301): gitlink → `e3e38397` + `LIVE_GITLINKS`; `preflight --arm A --engagement` for the five MTP-ON
  arms (records `$STACK_WORKDIR/p475/engagement/`); the leg pre-check needs OFF + engagement PASS on this base (S18-P3); contract v1.4.
  The CLI preflight works again (no stdin workaround).

## Next, in order

1. Gate receipt → stack push ask.
2. Re-prepare on the gated base: archive `$STACK_WORKDIR/p475/` whole to `$STACK_WORKDIR/archive/p475-base-15d90757/`; `git mv`
   `results/p475/u4-n16-smoke.a2` + `u4-tq4-smoke.a1` to `results/p475/archive/15d90757…12/` (C298, `data(bench)`); remove the six arm
   worktrees (submodules clean → `--force`), rename their branches to local `archive/p475-u4-<arm>-15d90757`; `prepare --base <gated>`.
3. The six OFF preflights + five ON engagement checks (`python -m bench.p475_kv preflight --arm A [--engagement]`, detached, one after
   another; ≈ 2 h 45 min OFF + ≈ 2–3 h ON). Show the operator the ON target + drafter manifests.
4. The two smokes (`run --smoke`), then the full run (12 legs, ≈ 13 h GPU; ≥ 600 s idle; 140 W / 28 V). Harvest → generated
   `MATRIX.Qwen3.8-27B-mlx-uniform-4bit.md` → operator; push ask for results + scrubbed logs to `evidence`.

Open, lower priority: S18-P8 (fork `-n 4`-only flake), P643, P642's two process gaps.

## Worktrees / scratch (resolve each)

- Keep until Next 2: the six `p475-u4-*` arm worktrees + branches (base `15d90757`; their legs harvested).
- Remove after the stack push: fork worktrees `$STACK_WORKDIR/worktrees/p658-impl`, `p658-tests`, `$STACK_WORKDIR/scratch/p658/
  panel-checkout` (all harvested into `docs/reviews/p658/` and the fork commits) and the fork local branches `p658-impl`, `p658-tests`.
- Local archive branches (no push): `archive/p475-u4-*-1554bfe1`, `archive/c258x-off`.

## Rules learned (session 18)

- An approved fix can be incomplete: trace it across every leg that reuses the same state (P659's exit-only tolerance vs the entry
  check on an arm's second leg).
- Make the fake reproduce the real-box fact first; the red test then is the box failure verbatim.
- A busy check that greps `ps` must not carry its patterns in its own argv — use a script file.
- `git worktree remove` refuses worktrees with submodules: verify the submodules clean, then `--force`.
- The pre-push hook needs the machine config sourced in the pushing shell.
- Names are per run, dossiers per name: archive the previous base's dossiers at each re-prepare (C298).
- A shared venv's editable install makes a worktree's `import mlx_vlm` resolve to the main checkout: check a worktree-only failure on a
  pristine baseline worktree before blaming the candidate.
- Black reformatting can change docstrings (AST differs only there); check ASTs rather than trusting black's skipped safety check.
- The naming hook reads "low" as a model shorthand (allow-shorthand); verbatim helper outputs go under `docs/reviews/<item>/` as `*-report.md` /
  `opinion-*` (C293 data names).
