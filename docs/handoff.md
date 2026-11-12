# Handoff — 2026-11-11 (session 22: M76 spec v1.2 written and cold-reviewed (rounds 1–2 of 3); awaiting the operator's Go)

THE one handoff. Read this, then `docs/PLAN.md` rows M66–M77, then `docs/open-questions.md` top entries (newest first: C324, C323,
S21-P17, C322, C321 …). Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance: bias for quality, GPU
time is the binding resource (funnel, C323); drive to certified picks; ask only at Go / Accept / pushes / scope changes.

Decisions: session 22 ruled C323 (S22-P1 … P11 + the funnel directive) and C324 (S22-P12 … P15 + the verify round). Discussion
ids: session 22 used `S22-P1 … S22-P15`; a new session restarts at P1. Next decision id **C325**.

## THE GOAL — MET (C309); Phase 2 = M72 → M76

Both picks certified in their shipped config (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` native16 + MTP ON, C291;
`Qwen3.8-27B-mlx-uniform-4bit` TQ4 + MTP ON, C258). M72 1.3 shipped the opt-in TQ4 mode `tq4_attention: m72_v1 | m72_exact` (C321).
**M76 (= 1.4)** certifies TQ4 `m72_exact` + MTP ON for the first pick; the accepted gain is memory.

## FIRST — verify (each "no" is a blocker)

1. Power 140 W / 28 V, GPU idle ≈ 0 % (`ioreg -r -d 1 -c IOAccelerator | grep "Device Utilization %"`), tiny-op floor ≈ 0.17 ms
   (`benchmark/results/m72/d1d2/floor.py`; 0.172 ms on 2026-11-11). OrbStack running before any gate (`~/.orbstack/bin/docker info`).
2. Nothing running (check from a script file, never with the patterns in your argv).
3. Pushes: fork `origin/main` = `5f83c84f`; mlx-serve `origin/main` = `0f2259f`; stack `origin/main` = `8c65dac0`. Local stack `main`
   is ahead by docs-only commits (session-21 close, C322 / C323 / C324, M76 spec v1 → v1.2, review ledgers, this handoff); push only
   on the operator's word.
4. Worktrees: none. Scratch (regenerable, ask before deleting): session 21's list below plus `$STACK_WORKDIR/reviews/m76-design-r1/`
   (read-only repository copy + briefs + raw outputs; the raw outputs are committed under `docs/reviews/m76-design/`).

## Done in session 22

- FIRST checks clean (140 W / 28 V, GPU 0 %, floor 0.172 ms, OrbStack + docker 29.8.2, heads as expected).
- **M76 spec** `docs/specs/m76-tq4-certification.md`: v1 (`7620adae`) → cold strict review round 1 (Sol, GLM, Sonnet; 20 findings,
  16 adopted / 3 adapted / 1 declined) → v1.1 (`e9386d67`) → verify round 2 (12 findings, all adopted / adapted) → v1.2
  (`11d997f1`, not re-reviewed). Ledgers `docs/reviews/m76-design/round{1,2}-ledger-report.md`.
- Code map (subagent, source read): TQ4 MTP OFF with the mode is not servable today (mlx-serve `config.py:175-178` / `:256-260`, fork
  `tq4_attention.py:88-90`, `:345-357`) → PLAN M77 (= M76 B0, approved C323); every harness (P475, qualify, P426, P369) hard-codes
  its pick / MTP delta / S′ pins — the adapters are B1–B5.
- Loss-bound feasibility simulated (`bench.stats.paired_delta`): tg1 at 43 items misses the 10 pp bound ≈ 25 % of the time when TQ4
  is harmless; 3 sessions ≈ 5–20 %; Math500 300 ≈ 0 %.
- Memory: `harness-funnel` (feedback) saved.

## Next, in order

1. FIRST checks above.
2. **The operator's Go on M76 spec v1.2** (or a round 3 of 3 review — the operator's call; v1.2's [r2] changes are not re-reviewed).
3. On Go: builds in the spec's §9 order — B0 (= M77, production, fork + mlx-serve, four-eyes light, gates, push asks, bump) + B1
   (P475 `f45`, campaign-scoped) + B2 (fork dev qualify / P369 tuple, push ask) first; then stages 0 → 1 → 2 on the GPU while B3
   (P426 lever `kv`, build `s3`), B4 (tg2 legs), B5 (Wave 1 extensions, `longctx`) and B7 (statistics + the rule simulation) are
   built. B7's simulation report + the timed A5 / tg2 smokes go to the operator with the stage-3 Go.
4. Carried (none blocks M76): S21-P17 (stale mlx-serve golden test; proposal); the 1.3 residuals (stale `_TQ4_MANIFESTS` entry per
   router port, exit route-counter snapshot only in the manifest-gathering process, the verifier's local rebinding,
   `dev/m72_scratch_prefill.py` I1 hazard); B6 (client paths reaching continuous batching) runs at smoke time.
5. Phase 2 M73 and Phase 3 hygiene (M67–M69, M74) in CPU gaps, never during measured legs or gates. M70 is folded into M76.

## Rules learned (session 22)

- A pre-registered decision rule needs its error checked, not only its power: simulate false-PASS at the harm boundary before
  keeping a sequential look; per-axis information fractions differ, so one fixed O'Brien–Fleming pair is wrong.
- Byte-identical MTP ON / OFF arms made P426's loss bounds easy; a lossy lever (KV format) diverges from the first differing logit,
  so size every axis for the reseed-level discordance (simulate at the planned n).
- An exact bound and a percentile interval in the same code can sit at different α (`stats.paired_delta`: 2.5 % tails vs 0.05):
  name both levels in any rule that uses both.
- A widened load-time refusal must receive the state it conditions on (B0: the stamp check never saw the drafter state).
- Sentinels for reusing agentic legs must use P640's identical-context criterion; whole-output identity fails on tool-output
  timestamps (P611).

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
