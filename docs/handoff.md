# Handoff — 2026-11-11 (session 21: post-reboot checks clean; M75 built, gated, stack pushed; C317 round: pipe2 not kept; M72 1.3 spec v1.1 after the cold design review → the operator's Go)

THE one handoff. Read this, then `docs/PLAN.md` rows M66–M75, then `docs/open-questions.md` top entries (newest first: S21-P3,
S21-P2, C317, S20-P19, C316 …). Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance: bias for
quality (spend tokens for better outcomes); drive to certified picks; ask only at Go / Accept / pushes / scope changes; lead calls
filed as they land; offer a fresh session at clean boundaries. Every Go'd build gets its PLAN row in the ruling's commit.

Decisions: session 21 ruled C318 (Go on 1.3 v1.1), C319 (`m72_exact`); S21-P3 was decided by C317's pre-registered rule. Discussion ids: session 21 used
`S21-P1 … S21-P9`; a new session restarts at P1 and cites `S22-P<n>`. Next decision id **C320**.

## THE GOAL — MET (C309); Phase 2 = M72

Both picks certified in their shipped config (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` native16 + MTP ON, P426 / C291;
`Qwen3.8-27B-mlx-uniform-4bit` TQ4 + MTP ON, C258). M72: can TQ4 beat native16 for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`?
Status: prefill parity measured end to end (0.97–0.98×; per-layer evaluation, pipe2 not kept); decode MTP ON projects 1.10–1.19×;
savings −5.8 / −11.7 GB as measured on 16 TQ4 layers (production keeps layer 63 native16: ≈ 0.4 / 0.8 GB less, S21-P2). Nothing is
wired into the server yet: 1.3 spec v1.1 awaits the operator's Go.

## FIRST — verify (each "no" is a blocker)

1. Power 140 W / 28 V, GPU idle ≈ 0 %, tiny-op floor ≈ 0.17 ms before any GPU work. After a reboot: start OrbStack before any
   gate (a stopped Docker daemon turns 21 tg2-grader tests into skips → gate FAIL on the skip baseline).
2. Nothing running: no router on :8000, no gate / probe / pytest / review dispatch (check from a script file, never with the
   patterns in your argv).
3. Pushes: stack `origin/main` = `f31c4854` (M75, PASS receipt `stack-f31c4854…-760009f36921-1.json`). Local `main` is ahead with
   docs + data only (`b16c1d42` S21-P2 + spec draft, `cb2d3640` round data, `a34c2d65` records, `11cdd11e` spec v1.1 + ledger, and
   this handoff): a mixed docs + data range is level `full` → needs a PASS gate on the tip and the operator's push approval. Fork
   `origin/main` = local `main` = `608e33ac`; the stack pins `e3e38397` / mlx-serve `1ddf6f84` (PASS receipts under the M75 policy
   digest: `mlx-vlm-e3e38397…-41a7f81405cd.json`, `mlx-serve-1ddf6f84…-09cf0b600a14.json`).
4. Worktrees: none. Scratch, regenerable (raw copies are committed): `$STACK_WORKDIR/reviews/m72-1.3-design-r1/`,
   `$STACK_WORKDIR/m72/{s21-smoke, e2e-s21}/`, `$STACK_WORKDIR/gate/s21/`.

## Done in session 21

- Post-reboot checks: 140 W, GPU idle 0 %, floor 0.170 ms, MLX 0.32.4 `applegpu_g17s`; p2s smoke (`--max-t 32768`) exactness
  39 / 39, N1 fails, chunk times within 2 % of `P2S.md` (`benchmark/results/m72/p2s/p2s-smoke-s21.*`).
- **M75** (`9cf651a0`): `RUNSERVER_PORT_WAIT_S` (default 30, refused at start unless a positive whole number; the cleanup test
  sets 3 s); `bench.local_gate` keeps a FAIL's full step output + JUnit beside the receipt (`failure_artifacts`). Red first (9),
  70 green. It diagnosed the first stack gate's FAIL in minutes (OrbStack down after the reboot). Stack pushed `c3d0072d..f31c4854`.
- **C317 (1) round** (S21-P3, `cb2d3640`): pipe2 / layer = 0.994 at 131,072 (< 1 %) → per-layer evaluation for 1.3.
- **S21-P2**: the e2e harness quantizes all 16 full-attention layers; production keeps layer 63 native16.
- **M72 1.3 spec** `docs/specs/m72-1.3-tq4-production.md` v1 → cold design review round 1 of 3 (Sol, GLM, Sonnet; briefed) →
  v1.1: 15 findings adopted / adapted, 3 scope requests to the operator (`docs/reviews/m72-1.3-design/dispositions-report.md`).

## Next, in order

1. FIRST checks above.
2. **1.3 GO (C318 + C319)**: spec v1.1 + S2 (short prefill via the verify kernel) + `m72_exact` (lossless MTP verify) + A6's
   divergence diagnostic. Four-eyes strict in progress — see the PLAN row for its state.
3. Then four-eyes strict (cast on this box: implementer = fresh Claude Opus `claude -p` in a worktree, test-writer = Claude Sonnet,
   panel = GPT-5.6 Sol High + GLM 5.2 High read-only; shared-vendor gap stated) → fork gates → Push asks → stack bump + gate →
   A5 / A6 on the real model → the operator's Accept. Then 1.4 (P475-style matrix + quality vs native16 + MTP ON / OFF; real-data
   A1 of S20-P18; corrected savings, S21-P2).
4. Phase 2 M73 and Phase 3 hygiene (M67–M70, M74) in CPU gaps, never during measured legs or gates.

## Archives (local, no push)

- `$STACK_WORKDIR/m72/superseded-instrument-v1/`, `…-v2/` (probe outputs of the superseded instruments; not cited).
- `$STACK_WORKDIR/archive/p475-base-{1554bfe1,15d90757,9adbae45,35c15d7d}/`; `$STACK_WORKDIR/archive/session18-worktrees/`.
- Branches: `archive/p475-u4-<arm>-{1554bfe1,15d90757,9adbae45,35c15d7d}`, `archive/c258x-off`.
- Scrubbed P475 worker / router logs for `evidence`: `$STACK_WORKDIR/archive/p475-base-35c15d7d/p475/evidence-stage/`.

## Rules learned (session 21)

- After a reboot, start OrbStack before any gate; read a FAIL receipt's `failure_artifacts` before rerunning.
- A docs commit on top of a gated sha: push the gated sha (`git push origin <sha>:main`); the pre-push check levels the whole
  introduced range, so a mixed docs + data range needs its own gate.
- Check a harness's cache construction against production's (`maybe_quantize_kv_cache` skips the last cache entry) before citing
  its memory or quality numbers for a served configuration.
- Memory acceptance bounds compare legs at the same preallocated capacity; production capacity is `max_kv_cache_size`.
- A kernel serving a sliced state takes the caller's key length, never `cache.offset`.

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
