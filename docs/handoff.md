# Handoff — 2026-11-11 (session 21 → 22: M72 1.3 accepted + published — production TQ4 attention mode `tq4_attention` m72_v1 / m72_exact (C321); M72 1.4 = PLAN M76 GO (C322): spec it first)

THE one handoff. Read this, then `docs/PLAN.md` rows M66–M76, then `docs/open-questions.md` top entries (newest first: S21-P17,
C322, C321, C320, S21-P10, S21-P9, C319, C318, S21-P3, S21-P2 …). Model names: FULL registry names only. Review rounds: 3 per
artifact. Operator stance: bias for quality (spend tokens for better outcomes); drive to certified picks; ask only at Go / Accept /
pushes / scope changes; lead calls filed as they land; offer a fresh session at clean boundaries. Every Go'd build gets its PLAN row
in the ruling's commit.

Decisions: session 21 ruled C318 (Go on 1.3 v1.1), C319 (`m72_exact`), C320 (second fix round), C321 (Accept), C322 (1.4 Go);
S21-P3 was decided by C317's pre-registered rule. Discussion ids: session 21 used `S21-P1 … S21-P17`; a new session restarts at P1
and cites `S22-P<n>`. Next decision id **C323**.

## THE GOAL — MET (C309); Phase 2 = M72

Both picks certified in their shipped config (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` native16 + MTP ON, P426 / C291;
`Qwen3.8-27B-mlx-uniform-4bit` TQ4 + MTP ON, C258). M72 status: **the production TQ4 mode exists end to end (1.3, opt-in, no pick
change)** — `kv_bits: 4` + `tq4_attention: m72_v1 | m72_exact` (requires `attention_policy: fused_v1` + `mtp_verify_scan: joint_v1`;
layer 63 stays native16). Measured served: prefill ≈ the dev p2s path (1.004×; ≈ 0.98× native16), memory ≈ −5.4 / −10.9 GB at 131K /
262K; projected decode MTP ON 1.10–1.19× (`m72_v1`, not exact) / ≈ 0.95× (`m72_exact`, lossless). **M76 (= 1.4, C322)** certifies
TQ4 `m72_exact` + MTP ON as the candidate default; the operator accepts memory as the gain.

## FIRST — verify (each "no" is a blocker)

1. Power 140 W / 28 V, GPU idle ≈ 0 %, tiny-op floor ≈ 0.17 ms (`benchmark/results/m72/d1d2/floor.py`) before any GPU work. After a
   reboot: start OrbStack before any gate (a stopped Docker daemon turns 21 tg2-grader tests into skips → gate FAIL).
2. Nothing running: no router on :8000, no gate / probe / pytest / review dispatch (check from a script file, never with the
   patterns in your argv).
3. Pushes: fork `origin/main` = local = `5f83c84f`; mlx-serve `origin/main` = local = `0f2259f`; stack `origin/main` = `8c65dac0`
   (gated, receipt `stack-8c65dac0…-5b1e7efdd9f3.json`). Local stack `main` is ahead by docs-only commits (C322 / PLAN M76, the
   session-21 notebook / results / S21-P17 records, this handoff): docs-only level, no gate; push needs the operator's word.
4. Worktrees: none (all three repositories: main checkouts only). Scratch, regenerable (every cited record is committed) — ask the
   operator before deleting: `$STACK_WORKDIR/fe-m72-13/` (four-eyes clones, briefs, raw outputs; several GB),
   `$STACK_WORKDIR/reviews/m72-1.3-design-r1/`, `$STACK_WORKDIR/m72/{s21-smoke, e2e-s21, a5-s21, real-s21}/`, `$STACK_WORKDIR/gate/s21/`.

## Done in session 21

- Post-reboot checks clean; p2s smoke within 2 % of `P2S.md`.
- **M75** (`9cf651a0`, pushed): `RUNSERVER_PORT_WAIT_S`; the gate keeps a FAIL's full output + JUnit (`failure_artifacts`).
- **C317 round** (S21-P3): pipe2 0.58 % faster (< 1 %) → per-layer evaluation.
- **M72 1.3** — spec `docs/specs/m72-1.3-tq4-production.md` (v1.1 + errata a / b / c), cold design review (Sol, GLM, Sonnet), Go
  (C318 / C319), four-eyes strict (implementer Claude Opus `claude -p`, test-writer Claude Sonnet ×5, panel verify Sol + GLM), two fix
  rounds (C320), Accept (C321), published. Real-model acceptance `benchmark/results/m72/m72-13/`; ledgers + report block
  `docs/reviews/m72-1.3-design/`; mechanisms `docs/lab-notebook.md` 2026-11-11; recommendation `docs/campaign-results.md` 2026-11-11.
- Records: S21-P2 (harness layer 63), S21-P9 → C319 (corrected: seeded MTP never matched OFF sample for sample), S21-P10 (served path
  = every session-resolved request), S21-P17 (stale mlx-serve golden test).

## Next, in order

1. FIRST checks above.
2. **M76 (M72 1.4, C322): write its spec** → cold design review (strict) → the operator's Go. Read first: C322, `docs/specs/p475-kv-matrix.md`
   + `p475-stage1-contract.md` + `p475a-qualify-kv-arm.md` (the matrix and its arm qualification), `docs/specs/p426-fable-mtp-recert.md`
   (+ `p426-b2-tg1-wave2.md`, `p426-t3-serving-build.md`; the quality waves), the P369 exactness instrument behind C258 (find its spec /
   PLAN row), `benchmark/results/m72/m72-13/README.md`, `docs/metrics.md`, `docs/box-notes.md`, `benchmark/README.md`,
   `docs/regrade-vs-rerun-guideline.md`. The spec must cover: the `bench.p475_kv` / P426 adapters for the `tq4_attention` key and its
   arm identity (four-eyes light); arms as stack commits in worktrees (N16 = the shipped entry; TQ4 arms change only `kv_bits` +
   `tq4_attention`); stage (1) matrix, (2) `m72_exact` ON vs OFF exactness at scale, (3) quality vs N16 with the C172 / C173 rule,
   (4) conditional `m72_v1`; the real-data A1 of S20-P18; GPU budget and ETAs; the publish step (registry `CERTIFIED`, README tables,
   gate, push ask) only after the operator's pick approval.
3. Open items carried (none blocks M76): S21-P17 (stale mlx-serve golden test; proposal); residuals of 1.3 — stale `_TQ4_MANIFESTS`
   entry per router port, exit route-counter snapshot only in the manifest-gathering process, the verifier's local rebinding,
   `dev/m72_scratch_prefill.py` keeps the I1 stale-row hazard (dev only), S21-P10 batching-path fallback (list client paths in M76);
   the worker log does not carry `Request completed` at its level (A6 proof used route counters).
4. Phase 2 M73 and Phase 3 hygiene (M67–M70, M74) in CPU gaps, never during measured legs or gates.

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
