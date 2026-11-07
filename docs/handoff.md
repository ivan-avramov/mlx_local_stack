# Handoff — 2026-11-06 (session 18: P475 stage-1 FULL RUN in progress on base `35c15d7d` since 18:22 local; all 11 checks PASS; both smokes VALID; `origin/main` = `35c15d7d`)

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

1. The full run: `python -m bench.p475_kv run` (pid in `$STACK_WORKDIR/p475/run.pid`, log `$STACK_WORKDIR/p475/run.log`, RUNLOG
   `$STACK_WORKDIR/p475/RUNLOG.md`), started 2026-11-06 18:22 local, ≈ 13 h + replacements. Alive? → wait (never kill a BUSY run;
   verify a wedge before any kill). Exited? → read its RUNLOG / exit code; a resume is `run` again (state.json; caps monotonic).
2. Pushes: `origin/main` = `35c15d7d` (gate PASS 11,950; C302 pre-authorized push done). Local tail: `c037cf5a` (smoke dossiers)
   + docs; push with the results after the harvest (ask). Forks: `../mlx-vlm` = origin = `e3e38397`; `../mlx-serve` = `1ddf6f84`.
3. Arm worktrees `$STACK_WORKDIR/worktrees/p475-u4-*` on base `35c15d7d` (fork gitlink `e3e38397`), serving the run: never touch
   them while it runs.

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
- **S18-P12 / C302** `4a6a4fd6`: preflight power pre-check + `qualify`'s pre-run refusals are NOT_STARTED (found when the box
  ran on battery: six false REFUSED records, kept in `$STACK_WORKDIR/archive/p475-base-9adbae45/`). Gate `35c15d7d` PASS 11,950;
  pushed `e86a39e3..35c15d7d`.
- **On base `35c15d7d`:** six OFF preflights + five ON engagement checks PASS, first attempt each (ON: every drafter cache one native
  `KVCache` == its template, K3; target manifests as the arms; MTP-ON 256K-class decode N16 13.1 / AF8 6.3 / TQ8 6.7 / AF4 6.9 / TQ4
  9.7 tok/s, descriptive); smokes `u4-n16-smoke.a1` + `u4-tq4-smoke.a1` VALID (`c037cf5a`; within ≈ 1 % of the `15d90757` smokes).
- **Stack step 2** `97672222` (C301): gitlink → `e3e38397` + `LIVE_GITLINKS`; `preflight --arm A --engagement` for the five MTP-ON
  arms (records `$STACK_WORKDIR/p475/engagement/`); the leg pre-check needs OFF + engagement PASS on this base (S18-P3); contract v1.4.
  The CLI preflight works again (no stdin workaround).

## Next, in order

1. When the run ends: verify its exit and the harvested dossiers under `benchmark/results/p475/` (12 legs + any replacements /
   deciding block); `python -m bench.p475_kv matrix` → `MATRIX.Qwen3.8-27B-mlx-uniform-4bit.md` (generated, never hand-edited);
   commit `data(bench)`; README / campaign-results evidence update; the matrix to the operator with mechanisms, trends and the
   KV-format recommendation (the operator weighs the table; stage 2 quality only for formats kept).
2. Push ask: results + the docs tail to `main`; scrubbed logs (`$STACK_WORKDIR/p475/evidence-stage/`) to `evidence`.
3. Then the `Qwen3.8-27B-mlx-uniform-4bit` MTP ON vs OFF re-certification on the chosen format (THE GOAL).

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
