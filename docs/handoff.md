# Handoff — 2026-11-05 (session 18, clean boundary: C296 (1) + C297 + C298 built; `e86a39e3` pushed; six OFF preflights PASS + both smokes VALID on `15d90757`; next: P658 (a) in the fork)

THE one handoff. Read this, then `docs/open-questions.md` top entries (newest first: C298, S18-P4, S18-P3, C297, S18-P2, S18-P1,
C296, P659 …), then `docs/specs/p475-stage1-contract.md` (v1.3) and `docs/reviews/p475s1/dispositions.md`. Model names: FULL
registry names only. Review rounds: 3 per artifact. Operator stance: bias for quality; drive to certified picks; ask only at Go /
Accept / pushes / scope changes; lead calls filed as they land; offer a fresh session at clean boundaries.

Discussion ids restarted at P1 in session 18; durable records cite them as `S18-P<n>` (historical P1–P659 unchanged). Next decision id
C299; next discussion id S18-P5 (a new session may restart at its own `S19-P1`).

## THE GOAL

Certify the two picks in their ideal config. `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`: DONE — MTP ON `CERTIFIED P426 2026-11-04`
(C291). `Qwen3.8-27B-mlx-uniform-4bit`: its KV format first (P475 stage 1: memory / speed matrix of six arms, MTP ON as shipped; the
operator weighs the table; stage 2 quality only for formats kept), then its MTP ON vs OFF re-certification on the chosen format.

## FIRST — verify (each "no" is a blocker)

1. Nothing running: no router on :8000, no P475 orchestrator / `qualify` / `worker.py`. Check with a script file, never with the
   patterns in your own argv (session 18 tripped its own check once).
2. Pushes: `origin/main` = `e86a39e3` (pushed session 18; gate PASS 11,870 / 9 skipped / 1 xfailed). Local `main` carries the
   ungated session-18 commits from `8ce7befa` on: code `53e2e321` (C296 (1)), `bc07cabc` (C297), test `5920015e` (C298 guard),
   data `d13b13ff` (old-base dossier archived), `7c030035` (smokes), docs. They go out with the step-2 stack gate; no push without an
   in-turn ask. Forks `../mlx-vlm` = `d94e38a9`, `../mlx-serve` = `1ddf6f84`, both = origin.
3. Arm worktrees `$STACK_WORKDIR/worktrees/p475-u4-{n16,af8,tq8,af4,tq4,tq4-off}` on local branches `p475-u4-*` off base `15d90757`
   (each clean, diff = `main_models.yaml` only; `.venv`, `.venv-bench` and the fork venv built by `prepare`).

## Done in session 18

- `53e2e321` **C296 (1)** (red tests first, `test_c296_fixes.py`): P655 `--base` resolved to the full sha; P656 1–2 environmental
  preflight refusals = `NOT_STARTED` (no attempt, never final; `run` stops, never refuses the arm), proven live (`LockRefused:
  gate/RUNNING`, 0 attempts); P656 3 `prepare` builds `p369/phase2/` + the fork venv (pins from the arm `.venv` freeze); P656 4–5
  stderr tail kept, `RealOps.run` reaps the process group on timeout.
- `bc07cabc` **C297 / S18-P1 (c)**: `run_capacity --out-dir`; legs write to `$STACK_WORKDIR/p475/legs/<leg>/capacity/`; R1 strict
  (the ruled P659 exit-only tolerance superseded). Fakes dirty a worktree on any driver write. Contract v1.3.
- **S18-P2:** P426 / C258 worktrees removed (logs in `$STACK_WORKDIR/archive/session18-worktrees/`), `p426-{off,on}` deleted,
  `c258x-off` → local `archive/c258x-off`.
- **Re-prepare on `15d90757`:** old `$STACK_WORKDIR/p475/` + N16 worktree leftovers in `$STACK_WORKDIR/archive/p475-base-1554bfe1/`;
  old arm branches → local `archive/p475-u4-<arm>-1554bfe1`.
- **Six MTP-OFF preflights PASS**, first attempt (17–36 min each); manifests as session 17 (48 DeltaNet `ArraysCache` untouched;
  N16 16 native; AF8 / AF4 16 affine gs 64; TQ8 / TQ4 / TQ4-OFF 15 TurboQuant mse + layer 63 native). Runner
  `$STACK_WORKDIR/p475/pf_runner.py` (P656 item 6 workaround: `cd benchmark; P475_ARMS=<arms> ../.venv-bench/bin/python - <
  $STACK_WORKDIR/p475/pf_runner.py`).
- **Smokes VALID** (`7c030035`): `u4-n16-smoke.a2`, `u4-tq4-smoke.a1` — speed-valid, harvested, worktrees clean, no teardown
  survivors. **D1 answered:** psutil shows no `KV_*` / `TQ_*` in the TQ4 worker env → R2's "absent" guard stands. `u4-n16-smoke.a1`
  on this base was NOT_STARTED on the name collision (S18-P4 → C298: archive old-base dossiers under `results/p475/archive/<base12>/`
  at every re-prepare; required, the matrix's arm-commit check spans all top-level dossiers). Teardown escalates SIGKILL on the
  router's launcher wrapper every leg (also in the P426 RUNLOGs: existing ChainOps behaviour). Scrubbed worker / router logs wait in
  `$STACK_WORKDIR/p475/evidence-stage/` for the evidence push after the full run.

## Next, in order

1. **P658 (a), fork four-eyes light** (`../mlx-vlm`, `dev/` only, production byte-identical): `qualify --kv-arm --predictor on
   --engagement-only` (build the served MTP-ON path; target + drafter manifests vs expectation; no exactness / certification legs) +
   P656 item 6 (the quiet-box scan, `orchestrate.REFUSED_MODULES` incl. `bench`, exempts the caller's own ancestor chain). Cast as
   P475a (implementer Claude Opus 5.5, test-writer Claude Sonnet 5.5 via `claude -p`; panel GPT-5.6 Sol High + GLM 5.2 read-only).
   Fork gate `dev/ci.py`; **fork push needs its own ask**.
2. **Stack:** gitlink bump to the fork commit + `LIVE_GITLINKS` in `bench/tests/b2_frozen_support.py` (P632: never move
   `BASE_GITLINKS`); `p475_kv` calls the ON engagement check for ON arms; S18-P3 if approved; **one full gate**; push ask.
3. Re-prepare on that base (archive `$STACK_WORKDIR/p475/` whole; `git mv` this base's dossiers to
   `results/p475/archive/15d90757…12/` per C298), OFF preflights + ON engagement checks, the two smokes, then the full run (12 legs,
   ≈ 13 h GPU; ≥ 600 s idle; 140 W / 28 V). Harvest → generated `MATRIX.Qwen3.8-27B-mlx-uniform-4bit.md` → operator; push ask for
   results + scrubbed logs to `evidence`.

Open, lower priority: S18-P3 (a final preflight record is reused whatever its base), P643, P642's two process gaps.

## Worktrees / scratch (resolve each)

- Keep: the six `p475-u4-*` arm worktrees + branches (serve P475 stage 1 until the step-3 re-prepare; their legs are harvested).
- Local archive branches (no push): `archive/p475-u4-*-1554bfe1`, `archive/c258x-off`.

## Rules learned (session 18)

- An approved fix can be incomplete: trace it across every leg that reuses the same state (the P659 exit-only tolerance vs the
  entry check on an arm's second leg).
- Make the fake reproduce the real-box fact first (driver writes dirty the worktree); the red test then is the box failure verbatim.
- A busy check that greps `ps` must not run with its patterns in its own argv — put it in a script file.
- `git worktree remove` refuses worktrees with submodules: verify the submodules clean first, then `--force`.
- The pre-push hook needs the machine config in the pushing shell (`STACK_WORKDIR`); source it first.
- Names are per run but dossiers are committed per name: archive the previous base's dossiers at each re-prepare (C298).
