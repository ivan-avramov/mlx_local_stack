# Handoff — 2026-11-10 (session 20: M72 1.2 done — matrix-unit verify kernel, P2′ stage 1 prefill at 0.98× native16 end to end; C317: one pipelined-eval round, then 1.3; reboot pending at session end)

THE one handoff. Read this, then `docs/PLAN.md` rows M66–M75, then `docs/open-questions.md` top entries (newest first: C317,
S20-P19, C316, C315, S20-P18, C314 …). Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance: bias
for quality (spend tokens for better outcomes); drive to certified picks; ask only at Go / Accept / pushes / scope changes; lead
calls filed as they land; offer a fresh session at clean boundaries. Every Go'd build gets its PLAN row in the ruling's commit.

Decisions: session 20 ruled C312–C317. Discussion ids: session 20 used `S20-P1 … S20-P21`; a new session restarts at P1 and cites
`S21-P<n>`. Next decision id **C318**.

## THE GOAL — MET (C309); Phase 2 = M72

Both picks certified in their shipped config (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` native16 + MTP ON, P426 / C291;
`Qwen3.8-27B-mlx-uniform-4bit` TQ4 + MTP ON, C258). M72: can TQ4 beat native16 for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`?
Status: prefill reached parity (0.97–0.98× measured end to end, −5.8 / −11.7 GB at 131K / 262K); decode with MTP ON projects
1.10–1.19× via the matrix-unit verify kernel. Nothing is wired into the server yet (1.3).

## FIRST — verify (each "no" is a blocker)

1. The machine was rebooted for an OS update at the end of session 20: re-check power 140 W / 28 V, GPU idle utilization ≈ 0 % and
   the tiny-op floor ≈ 0.17 ms (`benchmark/results/m72/d1d2/floor.py`) before any GPU work; MLX / Metal behaviour after an OS update
   is unverified — rerun the stage-1 smoke (`m72_tq4_probe.py --mode p2s --max-t 32768`) and compare with `P2S.md` before measuring.
2. Nothing running: no router on :8000, no gate / probe / pytest (check from a script file, never with the patterns in your argv).
3. Pushes: fork `origin/main` = local `main` = `608e33ac` (stage-1 kernel). Stack `origin/main` = `c3d0072d`; local `main` is ahead
   (stage-1 spec / code / results, memory and real-activation spikes, end-to-end harness + results, records) and **has no PASS
   gate**: the clean-clone gate on `ed0348c2` failed one flaky test (S20-P19), the re-gate on `b4757409` was stopped for the reboot.
   Push after M75 lands and a gate passes on a quiet box (push approved in principle: "push as you think is reasonable").
4. Worktrees: none (stack: main checkout only; fork: `main` only). Gate scratch clones `$STACK_WORKDIR/gate/scratch/stack-b4757409*`
   and `stack-e86a39e3*` (2.4 GB each) are leftovers of killed gates: regenerable, delete.

## Done in session 20

- **D1 + D2 measured** (`D1D2.md`): exact multi-query verify fell short (per-query work, not the read, binds) → C312.
- **Matrix-unit verify kernel** (`dev/m72_mma_verify.py`, four-eyes light, accepted; `MMA.md`): TQ4 MTP ON decode projected
  1.10× / 1.19× of native16 at 131K / 260K; native16 arm ≈ flat (not shipped, C313). Tuning (`SWEEP.md`, `DIAG.md`): 512-token
  block cap −9–14 %; math-bound at k ≥ 3; spikes F2 (Neural Accelerator `matmul2d` in the JIT, 3.7×) and F3 (TQ4 unpack into NAX
  fragments exact but codebook-lookup-bound) → S20-P14: prefill first.
- **P2′ stage 1** (C314, four-eyes strict, accepted C315): `dev/m72_scratch_prefill.py` — fused TQ4 → fp16 dequantize into a
  cap-sized scratch + MLX fused SDPA. `P2S.md` (two passes), memory spike `benchmark/results/m72/memory/` (OS footprint ledger +
  MLX allocator, fresh process per scenario, known positives: one lazy 16-layer graph holds 6.4 scratches → per-layer evaluation is
  mandatory; T-sized scratch piles stale cache buffers → cap-sized), real activations `benchmark/results/m72/realact/` (fp16 370 /
  384 heads within the strict 2×, worst 3.84×, all within allclose 3e-2; bf16 fails → C316 keeps fp16), end to end
  `benchmark/results/m72/e2e/` (0.973× / 0.982× native16, −5.8 / −11.7 GB, per-layer evaluation included).
- Fork push via the operator's one `--no-verify` (naming false positive "the 4-bit indices" in a cited commit). <!-- allow-shorthand: quotes the hook's false positive -->

## Next, in order (C317)

1. FIRST checks above (post-reboot smoke).
2. **M75** (approved): `RUNSERVER_PORT_WAIT_S` override + the test at 3 s (failing test first), gate keeps full output on FAIL;
   then a clean-clone gate on the stack tip on a **quiet box** (nothing else running) → push stack.
3. **One pipelined-eval round** (C317 (1)): `m72_e2e_prefill.py --tokens 131072 --legs tq4_p2s:layer tq4_p2s:pipe2 tq4_p2s:pipe2
   tq4_p2s:layer --idle 600` → keep `pipe2` for 1.3 only if ≥ 1 % faster at ≤ 2 scratches (OS-ledger peak per leg); results under
   `benchmark/results/m72/e2e/`, records, the operator.
4. **M72 1.3** — production build of the whole TQ4 path: p2s prefill (per-layer evaluation inside the model forward; cap-sized fp16
   scratch), the matrix-unit kernel for MTP verify (block cap 512; residuals from `docs/reviews/m72-mma-verify/`: −1e30 sentinel,
   fp16 query range), D2 for plain decode; opt-in per pick; spec → cold design review → four-eyes strict → fork gate → Push → stack
   gitlink bump + gate → Push. Then 1.4 (P475-style matrix + quality vs native16 + MTP ON / OFF; real-data A1 of S20-P18).
5. Phase 2 M73 and Phase 3 hygiene (M67–M70, M74) in CPU gaps, never during measured legs or gates.

## Archives (local, no push)

- `$STACK_WORKDIR/m72/superseded-instrument-v1/`, `…-v2/` (probe outputs of the superseded instruments; not cited).
- `$STACK_WORKDIR/archive/p475-base-{1554bfe1,15d90757,9adbae45,35c15d7d}/` (run state, worktree logs; the `9adbae45` one holds
  the six false power-refused records); `$STACK_WORKDIR/archive/session18-worktrees/` (P426 / C258 logs).
- Branches: `archive/p475-u4-<arm>-{1554bfe1,15d90757,9adbae45,35c15d7d}`, `archive/c258x-off`.
- Scrubbed P475 worker / router logs for `evidence`: `$STACK_WORKDIR/archive/p475-base-35c15d7d/p475/evidence-stage/` (and the
  earlier bases' archives) — pushed with the results (C306 (2)).

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
