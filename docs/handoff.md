# Handoff — 2026-11-13 (session 22 → 23: M76 stages 0–1 done, stage 2 smoke RUNNING; M80 applied, gates pending; B7 waits for S22-P25 / P26)

THE one handoff. Read this, then `docs/PLAN.md` rows M76–M80, then `docs/open-questions.md` top entries (newest first: S22-P25 / P26,
C330, S22-P18, C329, C328, C327 …). Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance: bias for
quality; GPU time is the binding resource (funnel, C323); ask only at Go / Accept / pushes / scope changes; lead calls filed.

Decisions: session 22 ruled C323–C330. **Discussion ids restart: session 23 uses `S23-P1 …`** (session 22 used S22-P1 … P26). Next
decision id **C331**.

## FIRST (each "no" is a blocker)

1. **A stage-2 process may be running.** The P369 smoke for tuple `m76-x` was launched 2026-11-13 (pid 13696; log
   `$STACK_WORKDIR/m76/p369-smoke.log`; out `$STACK_WORKDIR/p369/phase2/m76-x-smoke/`). Check by PID / log, never with a pattern
   in your argv. While it (or a later stage-2 full run) runs: **no pytest anywhere** (the P369 / qualify census refuses any `pytest`
   or `mlx-serve` in a process argv — `orchestrate.REFUSED_EXECUTABLES`), no gate, no four-eyes helper.
2. Power 140 W / 28 V, GPU idle ≈ 0 % before new GPU work; OrbStack up before any gate.
3. Pushed: stack `origin/main` = `c67dd7e9`; fork `34a21208`; mlx-serve `0555b2f`. Local, unpushed: stack `90098748` … `093e7176`
   + this handoff (S22-P18, stage-1 data `93290bd2`, specs B7 / B3+B5 / B4, M80 `093e7176`), fork `babb0c9d` (M80 marker).

## State of M76 (`docs/specs/m76-tq4-certification.md` v1.2, GO C325)

- **Builds:** B0 = M77 ✔ (pushed); B1 ✔ (pushed); B2 ✔ (pushed); M78 ✔; M79 ✔; **M80 accepted (C330), committed, not gated**;
  **B7** built (four-eyes: implementer + test-writer delivery 1 done in `$STACK_WORKDIR/fe-m76b7/`; candidate not yet reviewed)
  — its simulation found the rule unsafe for A5 / A8 → **S22-P25 / P26 OPEN** (designer's quality-biased rec recorded, incl. the addendum: A5 exact bound; A8 least-favourable α over a nuisance grid + a pre-registered re-check on the tg2 screen's real N16 data before the decider); the B7 fix
  round implements the operator's ruling, then test-writer delivery 2, change review, Accept. **B3 + B5** spec
  `docs/specs/m76-b3-b5-p426-kv-lever.md`, **B4** spec `docs/specs/m76-b4-tg2-legs.md`: not dispatched.
- **Stage 0 ✔:** 7 / 7 preflights PASS (`$STACK_WORKDIR/m76/p475/{preflight,engagement}/`); qualify phase peaks at 260,096
  tokens: N16 37.66 / 37.97 GB (MTP OFF / ON), TQ4 + `m72_exact` 26.33 / 26.64 GB.
- **Stage 1 ✔:** `benchmark/results/m76/matrix/MATRIX.Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed.md` (12 VALID legs incl. deciding
  b3): peak 39.86 → 26.81 GB (−13.0 GB, −33 %); prefill 0.95–0.99×; decode X 0.78–0.97×, V 0.86–1.41× (beats N16 1.34–1.41× at
  196K–256K), X / XO (MTP ON / OFF) 1.18–1.61×; **stage-4 trigger met** (V / X 1.30–1.47 at ≥ 128K). Caveat (S22-P22): one 256-token
  sample per rung, acceptance content-dependent — decode ratios directional; stage 3's per-item decode is the better speed evidence.
- **Stage 2 (P369 E1c + E2 on X, cross-load OFF = XO):** smoke RUNNING. On smoke PASS: the full run
  (`orchestrate.py --tuple m76-x --phase full --smoke-summary <smoke summary> --reviewed-head <fork HEAD of the X worktree>`) — if it
  projects > 8 h it refuses without `--operator-approved-hours` (ask the operator). Commands: run from
  `$STACK_WORKDIR/worktrees/m76-f45-x` with its `.venv/bin/python src/mlx-vlm/dev/p369_phase2/orchestrate.py --stack-root …/m76-f45-x
  --fork-root …/m76-f45-x/src/mlx-vlm --off-stack-root …/m76-f45-xo --tuple m76-x --out $STACK_WORKDIR/p369/phase2/<run>` (out must
  be under `$STACK_WORKDIR/p369/phase2/`). On FAIL → the operator (stage-2 FAIL / ABORT branches, spec §7).

## Next, in order

1. FIRST. Finish stage 2 (smoke → full; GPU; overnight if long).
2. When no stage-2 process runs: **M80 gates** — fork gate on `babb0c9d` (`bench.local_gate run --repo mlx-vlm`; criterion 2: the 146
   marked B2 tests run and pass inside the gate with the sibling; skip list = the 37-line baseline), then the stack gate on the
   latest stack commit (the gate source changed: every receipt re-runs); push asks (fork, stack).
3. The operator's ruling on S22-P25 / P26 → B7 fix round (fresh implementer in `$STACK_WORKDIR/fe-m76b7/`), test-writer delivery 2
   (session in `fe-m76b7/out/testwriter-1.json`), change review (Sol + GLM), Accept, commit with the regenerated simulation report.
4. B3 + B5 and B4 four-eyes (specs written; helper copies stack-only; never while a GPU stage runs).
5. Stage 3 Go to the operator with: B7's report (kept looks, A5 n, calibrated alphas), timed A5 / tg2 smokes, the per-axis plan; then
   stage 3 (and 4: V legs) per spec §7 / §8.
6. Open, not blocking: S22-P23 (pairing checked at push = M81, recommended).

## Worktrees and scratch

- Stack worktrees (serve M76 stages 1–4; remove after stage 4 is harvested): `$STACK_WORKDIR/worktrees/m76-f45-{n16,x,v,xo}` on
  local branches `m76-f45-*` (X `ec114753`, V `0795beb1`, XO `b9e6b91e`, N16 = base `89205085`).
- Four-eyes scratch (regenerable; the cited records are committed): `$STACK_WORKDIR/fe-{m77,m76b1,m76b2,m80,m76b7}/`; review copies
  `$STACK_WORKDIR/reviews/m76-design-r1/`; ask before deleting.

## Rules learned (session 22)

- Any `pytest` (or `mlx-serve` in an argv) on the box refuses P369 / qualify runs; chain legs similarly — GPU stages and four-eyes
  helpers cannot overlap; batch build windows and GPU runs. Name helper copies of mlx-serve neutrally (`serve/`).
- Timed legs (prefill / decode) run on a quiet box (S22-P18); untimed GPU work may overlap non-pytest CPU work only.
- A pre-registered decision rule needs its error simulated, not only its power; percentile bootstraps undercover with few discordant
  items — prefer exact bounds where they exist.
- Per-rung decode ratios from one generated sample are confounded by MTP acceptance (content); use many-item estimators for speed.
- Mocked tests miss real-path facts; ask the panel to trace real call chains (two B2 blockers, M80's PYTEST_ADDOPTS hole).
- Frozen tests must locate the fork from `__file__`, guard sibling dependencies, survive the fork's isort (`# isort: skip_file`).
- The fork gate compares skips to `benchmark/gate/mlx-vlm.skips.txt`; a gate-source change invalidates every receipt.
- `run_capacity` gathers the manifest after the ladder: per-leg route counters are the exit snapshot's absolute values.
- Push the gated sha itself when docs or code sit above it (the pre-push hook levels the whole range).
- The router loads the worker on demand: `/health` on :8091 only after a first request.

## Done in session 21 (for reference)

- Post-reboot checks clean; p2s smoke within 2 % of `P2S.md`.
- **M75** (`9cf651a0`, pushed): `RUNSERVER_PORT_WAIT_S`; the gate keeps a FAIL's full output + JUnit (`failure_artifacts`).
- **C317 round** (S21-P3): pipe2 0.58 % faster (< 1 %) → per-layer evaluation.
- **M72 1.3** — spec `docs/specs/m72-1.3-tq4-production.md` (v1.1 + errata a / b / c), cold design review (Sol, GLM, Sonnet), Go
  (C318 / C319), four-eyes strict (implementer Claude Opus `claude -p`, test-writer Claude Sonnet ×5, panel verify Sol + GLM), two fix
  rounds (C320), Accept (C321), published. Real-model acceptance `benchmark/results/m72/m72-13/`; ledgers + report block
  `docs/reviews/m72-1.3-design/`; mechanisms `docs/lab-notebook.md` 2026-11-11; recommendation `docs/campaign-results.md` 2026-11-11.
- Records: S21-P2 (harness layer 63), S21-P9 → C319 (corrected: seeded MTP never matched OFF sample for sample), S21-P10 (served path
  = every session-resolved request), S21-P17 (stale mlx-serve golden test).

## Archives (local, no push)

- `$STACK_WORKDIR/m72/superseded-instrument-v1/`, `…-v2/` (probe outputs of the superseded instruments; not cited).
- `$STACK_WORKDIR/archive/p475-base-{1554bfe1,15d90757,9adbae45,35c15d7d}/`; `$STACK_WORKDIR/archive/session18-worktrees/`.
- Branches: `archive/p475-u4-<arm>-{1554bfe1,15d90757,9adbae45,35c15d7d}`, `archive/c258x-off`; M72 1.3 (cited by
  `benchmark/results/m72/m72-13/README.md`): stack `archive/m72-13-arm-v1` (`b4b7052c`), `archive/m72-13-arm-exact` (`31625001`), fork and
  mlx-serve `archive/m72-13-cand3` (`83fc3bc8` / `436fee6`, trees = the merged candidate).
- `$STACK_WORKDIR/m72/real-s21/a4-*.invalid-unseeded-greedy.json` (the superseded first A4 run; not results).
- Scrubbed P475 worker / router logs for `evidence`: `$STACK_WORKDIR/archive/p475-base-35c15d7d/p475/evidence-stage/`.

## Rules learned (session 21)

- After a reboot, start OrbStack before any gate; read a FAIL receipt's `failure_artifacts` before rerunning.
- A docs commit on top of a gated sha: push the gated sha; the pre-push check levels the whole introduced range.
- Check a harness's cache construction against production's (`maybe_quantize_kv_cache` skips the last cache entry).
- Memory acceptance bounds compare legs at the same preallocated capacity; production capacity is `max_kv_cache_size`.
- A kernel serving a sliced state takes the caller's key length, never `cache.offset`.
- `generate_step(temperature=None)` samples at the checkpoint's generation-config temperature: pass `temperature=0.0` for greedy, and
  give every exactness instrument a repeat control (the same arm twice) before comparing arms.
- Speculative sampling preserves the distribution, not the samples: seeded MTP ON never equals MTP OFF token for token.
- Fork changes to upstream-shared files need a `# Fork` marker on the enclosing definition (`dev/check_fork_markers.py`, gate
  `audit:3`); run it before the fork gate.
- A waiter must match a marker unique to the run it waits for (an earlier `END rc=1` line ended one early).
- Never commit with hooks disabled; temp commits run the hooks too.
- The worker log does not carry `Request completed` at its level; prove the served path with the route counters.
- A gitlink bump has stack companions the four-eyes copies cannot see (their `src/` submodules are empty): the P632
  `LIVE_GITLINKS` pin, `bench.arm_identity` flag classes for any new worker flag (P311), and skip-baseline entries for modules that
  start running against the bumped fork (`benchmark/gate/stack.skips.txt`). Run those tests with the submodules populated before
  the stack gate.

## Rules learned (session 20)

- Before projecting a "load once, serve k queries" gain, check the single-query kernel is bandwidth-bound; if not, per-query work
  stays and only matrix units amortize it.
- Exactness constraints have a price: state what the bit-identity contract pins (partition, accumulation order) before estimating.
- Check GPU idle utilization and the tiny-op floor before each measured pass; a stuck-busy GPU can need a reboot.
- The fork has no commit-time naming hook: run `bench.modelnames` over a fork diff before committing ("the 4-bit …" in a <!-- allow-shorthand: quotes the hook's false positive -->
  docstring blocked a push of an already-cited commit).
- Never run GPU or CPU-heavy work during a clean-clone gate: timing-margin tests (runserver cleanup) can fail (S20-P19).
- Measure a transient's memory per process (OS footprint ledger + MLX allocator), in the real graph shape, with known positives;
  never memfree, never single-call windows (lazy graphs and the buffer cache change lifetimes).
- Spec a kernel's cost model with every repetition factor (unpack per threadgroup, not per KV head) before promising a ratio.
- MLX's steel headers are invisible to the `mx.fast.metal_kernel` JIT: inline them (spike F2) to use the NAX fragment.

## Rules learned (session 19)

- Measure a preallocated cache just below the cap, never at it: at exactly the cap the slice is contiguous and hides the copy that
  row-contiguous custom kernels make on every call.
- A byte-ceiling reduction over a sliced view measures a copy; read contiguous copies.
- An earlier spike with no recorded outcome is not evidence: rerun it (minutes) before building on its premise.

## Rules learned (session 18)

- An approved fix can be incomplete: trace it across every leg that reuses the same state.
- Make the fake reproduce the real-box fact first; the red test then is the box failure verbatim.
- A busy check that greps `ps` must not carry its patterns in its own argv — use a script file.
- `git worktree remove` refuses worktrees with submodules: verify the submodules clean, then `--force`.
- The pre-push hook needs the machine config sourced in the pushing shell.
- Names are per run, dossiers per name: archive the previous base's dossiers at each re-prepare (C298).
- A shared venv's editable install makes a worktree's `import mlx_vlm` resolve to the main checkout: check a worktree-only failure on
  a pristine baseline worktree before blaming the candidate.
- Black can change docstrings (AST differs only there); check ASTs when its safety check is skipped.
- Helper outputs go under `docs/reviews/<item>/` as `*-report.md` / `opinion-*` so the naming hook treats them as data.
- Gate power strictly before any GPU launch: an empty `pmset -g ac` reading is a stop, not a pass.
- A ratio-relative instability rule degenerates near a ratio of 1 (S18-P13): pre-register an absolute floor.
