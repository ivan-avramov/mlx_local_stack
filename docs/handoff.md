# Handoff — 2026-11-09 (session 20: M72 1.2 D1 + D2 MEASURED; C312: matrix-unit TQ4 verify next; Push 3 + stack push approved)

THE one handoff. Read this, then `docs/PLAN.md` rows M66–M74, then `docs/open-questions.md` top entries (newest first: S20-P2,
S20-P1, C311 …). Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance: bias for quality; drive to
certified picks; ask only at Go / Accept / pushes / scope changes; lead calls filed as they land; offer a fresh session at clean
boundaries. Every Go'd build gets its PLAN row in the ruling's commit (C303 / P642 gap 2).

Decisions: session 20 ruled C312, C313 (S20-P1 closed by measurement). Discussion ids: session 20 used `S20-P1 … S20-P8`; a new session
restarts at P1 and cites `S21-P<n>`. Next decision id **C314**.

## THE GOAL — MET (C309); Phase 2 = M72

Both picks certified in their shipped config (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` native16 + MTP ON, P426 / C291;
`Qwen3.8-27B-mlx-uniform-4bit` TQ4 + MTP ON, C258). M72: can TQ4 beat native16 for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`?

## FIRST — verify (each "no" is a blocker)

1. Nothing running: no router on :8000, no probe / `qualify` / `worker.py` / `run_capacity` (check from a script file; never with
   the patterns in your own argv).
2. Pushes: `origin/main` = `ebae76c8` unless the session-20 push happened (then = the session-20 tip). Fork `../mlx-vlm`: local
   `main` = `65583e27` (the D1 + D2 prototype, `dev/m72_mq_decode.py`), origin = `e3e38397` unless Push 3 happened; `../mlx-serve` =
   `1ddf6f84`; stack gitlink `src/mlx-vlm` = `e3e38397` (dev-only change, no bump).
3. No worktrees (stack: main checkout only; fork: `main` only).
4. Power 140 W / 28 V, **and GPU idle utilization ≈ 0 % with a tiny-op floor ≈ 0.17 ms** before any GPU work (S20-P1: a stuck-busy
   GPU read 100 % / ≈ 1 ms and cleared only on reboot). Script: `benchmark/results/m72/d1d2/floor.py`; launcher pattern
   `benchmark/results/m72/d1d2/run_mq.sh`.

## Done in session 20

- Morning (before a reboot): prototype `dev/m72_mq_decode.py` + `m72_tq4_probe.py --mode mq` + `m72_mq_report.py`; timing blocked
  (S20-P1). After the operator's restart: GPU quiet; 8K control within 4 % of `PROBE.md` (contiguous-copy reference lines ≈ 2×
  slow, unexplained, not used); two mq passes (10-min idle) → generated `benchmark/results/m72/D1D2.md`.
- **Result (S20-P2):** exact (100 / 100 per pass). D2 (no layout copy) as estimated: MTP OFF 1.04×. D1 short: k = 3 verify 5.73 ms
  vs native16 joint 4.97 at 260K → MTP ON 0.94× / 0.92× of native16 at 131K / 260K (estimate 1.25× / 1.51×). Mechanism: per-query
  per-token work binds (≈ 1.5 ms per extra query, same as native16's joint call); lab notebook 2026-11-09 session 20.
- Morning smoke outputs (busy GPU, not cited): `$STACK_WORKDIR/m72/d1d2-smoke/`; run dir `$STACK_WORKDIR/m72/d1d2-s20b/` (harvested
  into `benchmark/results/m72/d1d2/`).

## Next, in order

1. **M72 1.2 per C312:** a matrix-unit TQ4 verify kernel (R·k = 18 query rows per KV head over unpacked TQ4 tiles, simdgroup
   matrix ops), held to `joint_v1`'s tolerance (allclose ≈ 3 bf16 ulps vs the per-query reference), in the fork's `dev/`; extend
   `m72_tq4_probe.py --mode mq` with it, compare to `D1D2.md` → the operator. Then scale it to prefill on the Neural Accelerators
   (P2′; first the ≥ 3× tensor-op `matmul2d` microkernel). Exact D2 stays the k = 1 path; opt-in per pick like `joint_v1`.
   **C313:** the microbenchmark gets a native16 arm (if it speeds native16 verify, it ships for native16 too via 1.3 +
   certification; the KV choice is then measured against that better baseline); M72 targets ≥ 128K, no tighter time box.
2. **Push 3** (fork `65583e27`) and the stack push — approved (C312); done in session 20 after their full gates unless FIRST 2 says otherwise.
3. **Phase 2 = M73** (S18-P20), parallel CPU track: sequential early stopping (four-eyes strict) → Push 7; aim before 1.4.
4. **Phase 3 hygiene** (CPU gaps, never during measured legs): M67, M68, M69, M70 (needs Go), M74 → one stack gate, Push 8.

Push policy (C310): push at every boundary where results or code are committed, within a day; each push is its own ask unless
pre-authorized.

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
