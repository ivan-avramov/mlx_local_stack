# Handoff — 2026-11-12 (session 22: M76 Go; builds B0 = M77, B1, B2 accepted and pushed; M78 / M79 done; M80 next; GPU stages next)

THE one handoff. Read this, then `docs/PLAN.md` rows M66–M80, then `docs/open-questions.md` top entries (newest first: C329, C328,
C327, S22-P16, C326, C325, C324, C323 …). Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance: bias
for quality, GPU time is the binding resource (funnel, C323); ask only at Go / Accept / pushes / scope changes.

Decisions: session 22 ruled C323–C329. Discussion ids used `S22-P1 … S22-P17`; a new session restarts at P1. Next decision id **C330**.

## State (2026-11-12)

- **M76 spec** `docs/specs/m76-tq4-certification.md` v1.2 — GO (C325). Builds: B0 = **M77** (`tq4_attention` with MTP OFF; fork
  `f9bf743f`, mlx-serve `3b02e4c`; real-model criterion 6 PASS `benchmark/results/m77/`), **B1** (`bench.p475_kv` campaign `f45`;
  stack `d2369748`), **B2** (fork dev tools: `qualify` / `registry_states` / P369 tuple `m76-x`; fork `5762e66d` + `34a21208`) —
  all four-eyes light, accepted (C326 / C328), pushed. **M78** (P475 resume gaps, `d5dc4f1c`) and **M79** (mlx-serve stale golden,
  `0555b2f`, pushed) done. **M80** (the fork gate provides a sibling mlx-serve; spec `docs/specs/m80-gate-sibling-mlx-serve.md`) GO
  (C329), not built; until then the 146 mlx-serve-dependent B2 tests are TEMPORARY entries in `benchmark/gate/mlx-vlm.skips.txt`
  (`c8cd6981`) and their evidence is the full-layout local run (1,460 passed beside mlx-serve `0555b2f`).
- Pushed: fork `origin/main` = `34a21208`; mlx-serve `0555b2f`; stack `origin/main` = `bc89767f`. Local stack ahead: docs, M77
  records, M78, the temporary skip baseline, the B2 gitlink bump — stack gate pending → push ask.
- Remaining builds before their stages: B3 (P426 lever `kv`, build label `s3`), B4 (tg2 legs), B5 (Wave 1 extensions, `longctx`),
  B7 (statistics + rule simulation) — before stage 3; M80 before stage 2.
- GPU next (stage 0 → 1): `python -m bench.p475_kv --campaign f45 prepare` (base = the stack commit with the B2 bump), the per-arm
  `preflight` (OFF) + `--engagement` (X, V), smokes N16 / X (grid 8192), then the stage-1 run (two blocks, N16 → X → V → XO and the
  reverse); pass `--expected-rung-seconds` from the smoke walls; after any interruption wait 600 s before resuming (M78 fixed the
  window; the rule stays as a habit).

## FIRST — verify (each "no" is a blocker)

1. Power 140 W / 28 V, GPU idle ≈ 0 % (`ioreg -r -d 1 -c IOAccelerator | grep "Device Utilization %"`), tiny-op floor ≈ 0.17 ms
   (`benchmark/results/m72/d1d2/floor.py`). OrbStack running before any gate.
2. Nothing running (check from a script file, never with the patterns in your argv); `:8000` / `:8091` free.
3. Worktrees: none in the stack beyond main (the M77 check worktree was removed); four-eyes scratch under `$STACK_WORKDIR/fe-m77`,
   `fe-m76b1`, `fe-m76b2`, review copies under `$STACK_WORKDIR/reviews/m76-design-r1` (regenerable; ask before deleting).

## Rules learned (session 22)

- A pre-registered decision rule needs its error checked, not only its power: simulate false-PASS at the harm boundary before
  keeping a sequential look; per-axis information fractions differ, so one fixed O'Brien–Fleming pair is wrong.
- Size every axis of a lossy-lever comparison for reseed-level discordance (simulate at the planned n); MTP-ON/OFF byte identity
  made P426's bounds easy.
- An exact bound and a percentile interval in the same code can sit at different α: name both levels in any rule that uses both.
- A widened load-time refusal must receive the state it conditions on (M77: the stamp check never saw the drafter state).
- Agentic reuse sentinels use P640's identical-context criterion; whole-output identity fails on tool-output timestamps.
- Mocked tests miss real-path facts: two of B2's blockers (the production ref default; `joint_v1`'s `cache` reason below 2,048)
  were found only by reading the real call chain — ask the panel to trace real paths.
- Frozen tests must locate the fork from `__file__` (the gate's clean clone is not named `mlx-vlm`) and guard any sibling
  dependency; the fork's isort reorders imports that rely on a `sys.path` side effect (`# isort: skip_file`).
- The fork gate compares skips to `benchmark/gate/mlx-vlm.skips.txt`: new environment skips fail it — list them (temporarily) or
  provide the environment (M80).
- `run_capacity` gathers the manifest after the ladder: per-leg route counters are the exit snapshot's absolute values.
- The pre-push hook refuses a code range above a gated sha: push the gated sha itself.
- The router loads the worker on demand: `/health` on :8091 exists only after a first request.

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
