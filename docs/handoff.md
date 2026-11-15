# Handoff — 2026-11-14 (session 23 → 24: stack pushed; B4 candidate 1 reviewed only by its implementer; stage 3 split, C342)

THE one handoff. Read this, then `docs/PLAN.md` rows M76, M83, then `docs/open-questions.md` top entries (newest first: C342, S23-P93,
C341 … C331). Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance (C334): guardrails prevent wrong
data or wasted time, not ceremony; cheap fixes welcome; GPU time is the binding resource; label every point `S24-P<n>`.

Decisions: session 23 ruled C331–C342 (next **C343**); discussion ids restart at `S24-P1` (session 23 used S23-P1 … P100).

## Goal (restated for convergence, operator asked)

Certify `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` on TQ4 KV + `tq4_attention: m72_exact` + MTP ON as the shipped default (the gain is
memory: −13 GB at 256K). Ship when stage 1 memory ✔, stage 2 exactness ✔, and stage 3: A1, A5 (incl. per-task gates, each arm ≥ 0.85),
A7, A8 decider all PASS (point ≥ −5 pp, loss bound ≤ 10 pp), no tg2 HOLD (any language < −20 pp), no panel / interaction flag; else the
per-axis signals → the operator. Then publish (registry CERTIFIED, README, gate, push ask). Stage 4 (V) decided at the readout.

## FIRST

1. Local, unpushed: stack `6db8b56d..HEAD` (handoff + C342 + PLAN M83, docs only). Pushed: stack `6db8b56d`, fork `babb0c9d`,
   mlx-serve `0555b2f` (stack gitlinks fork `34a21208`, mlx-serve `3b02e4c`).
2. Nothing runs (no GPU, no helpers). Power 140 W / 28 V before GPU work; OrbStack up before a gate; no clean-clone gate while a
   helper runs a test suite (S20-P19).

## Next, in order

1. **B4 four-eyes, continue** (`$STACK_WORKDIR/fe-m76b4/`, baseline `6db8b56d`, spec `docs/specs/m76-b4-tg2-legs.md` v1.1):
   implementer candidate 1 = `candidate/candidate-1.diff` (+ `candidate/implementer-report.md`: its Q1 tg2 runner missing → C342; Q2
   who writes the tg2 walls → B4b's sizing report; Q3 judgement calls to settle); test-writer `86224b98` delivery 1 frozen
   2026-11-15T06:56:54Z (`frozen/v1`; its gaps: no grader-mapping test without a seam name — the implementer's is in
   `benchmark/chains/c147/run_tg2_chain.py`; interface guesses `--tg2-draw`, `BoxSeqOps(corpus=)`). Next: delivery 2 (reveal the
   candidate; apply it yourself in `tw/stack` — the helper cannot run `git apply`), panel opinion (Sol + GLM), one fix round, Accept.
2. **B4b spec** (PLAN M83, C342): M65 build steps 3–4 — `bench/tg2_runner.py`, `run_tg2_probe.py`, `bench/corpus_tg2.py` on the
   shared cores, positives, four-language smoke + sizing report (walls). Then four-eyes light.
3. **Stage 3a, in parallel with B4b's CPU work:** build stage-3 arm worktrees (N16 / X on the current base, `m76-q-<arm>` or as B3 §
   Settled constraints), the timed A5 smoke (quiet box) → measured hours → **stage-3a Go to the operator** (A1, A5 two looks, A7, M1,
   panel axes; ≈ 50 GPU h). Light-path follow-up first if cheap: S23-P88 (`m76_ids.load()` re-checks the prompt band).
4. Stage 3b (A8) after B4b; readout; publish or the operator's call; stage 4 decision (S23-P91: lean no).

## State of M76

- Stage 0 ✔; stage 1 ✔ (`benchmark/results/m76/matrix/`); stage 2 ✔ PASS (`benchmark/results/m76/stage2/`).
- Accepted builds: B0–B2 (session 22), B7 (C337), B7.1 (C340), B3+B5 (C341; `benchmark/results/m76/ids.json` sha `6c9455a2…`).
- Stage-3 plan (C337–C339, C342): A1 two looks; A5 two looks 72 → 120 (A5-2L); A7 one look s1–s3 α* 0.001; A8 decider ALWAYS (C338)
  α* 0.001 + HOLD < −20 pp; clean PASS at no loss ≈ 38 %; ≈ 72 whole-stage GPU h (B7.1 report) — the tg2 part unmeasured.
- Deferred: stage-4 V workflow (S23-P49).

## Worktrees and scratch

- Stack worktrees (M76 stages 1–4; remove after stage 4 harvest): `$STACK_WORKDIR/worktrees/m76-f45-{n16,x,v,xo}` (X `ec114753`, V
  `0795beb1`, XO `b9e6b91e`, N16 base `89205085`).
- Four-eyes scratch (regenerable; cited records committed): `$STACK_WORKDIR/fe-{m77,m76b1,m76b2,m80,m76b7,m76b3,m76b71}/`; ask before deleting.
- P369 runs: `$STACK_WORKDIR/p369/phase2/{m76-x-smoke,m76-x-smoke-rh,m76-x-full,m76-x-full.refused-unbound-smoke}` (only `-rh` and
  `-full` cited).

## Rules learned (session 23)

- A test helper running a real thread beside a fake fast clock needs explicit ordering at every handoff (S23-P93: three gate
  rounds); margins only move the race.
- Tests must not read local-only branches; commit sha-pinned fixture copies (a fresh clone would skip, and the gate refuses skips).

- A P369 smoke binds a full run only with `--reviewed-head` (M82 will bind by recorded identity, C333).
- The P369 orchestrator censuses processes only at launch; `qualify` before every entry — stack-only CPU helpers may overlap untimed
  GPU stages (C334); clean-clone gates still need a quiet box.
- Run `bench.*` modules from `benchmark/` (`cd benchmark && ../.venv-bench/bin/python -m bench.<mod>`).
- A conditional bound on the discordant split (Clopper–Pearson given b + c) is not a safe loss bound; use an exact unconditional test.
- Simulated safety transfers only if stage 3 calls the simulated statistic: share one function.
- Per-axis safety settings multiply: check the joint clean-PASS probability before a Go (B7.1).
- The naming hook flags the model snapshot inventory (a subfolder named after the quantizer) in P369 summaries: main gets a compact verdict + sha256, full files go to `evidence`.

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
