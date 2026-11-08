# Handoff — 2026-11-07 (session 19: M72 step 1.1 probe DONE; S19-P4 (go / no-go on the 1.2 prototypes) with the operator; Push 2 asked)

THE one handoff. Read this, then `docs/PLAN.md` rows M66–M74, then `docs/open-questions.md` top entries (newest first: S19-P4,
C310, C309 …). Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance: bias for quality; drive to
certified picks; ask only at Go / Accept / pushes / scope changes; lead calls filed as they land; offer a fresh session at clean
boundaries. Every Go'd build gets its PLAN row in the ruling's commit (C303 / P642 gap 2).

Discussion ids: session 19 used `S19-P1 … S19-P4`; a new session restarts at P1 and cites `S20-P<n>`. Next decision id **C311**.

## THE GOAL — MET (C309); Phase 2 = M72

Both picks certified in their shipped config (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` native16 + MTP ON, P426 / C291;
`Qwen3.8-27B-mlx-uniform-4bit` TQ4 + MTP ON, C258). M72: can TQ4 beat native16 for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`?

## FIRST — verify (each "no" is a blocker)

1. Nothing running: no router on :8000, no probe / `qualify` / `worker.py` / `run_capacity` (check from a script file; never with
   the patterns in your own argv).
2. Pushes: `origin/main` = `f27e7ec1` unless Push 2 happened (then = the session-19 tip). Local `main` carries the M72 probe
   (scripts, results, records). Forks unchanged: `../mlx-vlm` = origin = `e3e38397`; `../mlx-serve` = `1ddf6f84`; stack gitlink
   `src/mlx-vlm` = `e3e38397`.
3. No worktrees (stack: main checkout only; fork: `main` only).
4. Power: 140 W / 28 V before any GPU work (the probe refuses otherwise; check anyway).

## Done in session 19

- FIRST checks passed; Phase 0 was already complete (`origin/main` = `f27e7ec1`, `evidence` = `eddf2e9c`).
- **M72 step 1.1 probe DONE** (≈ 10 min GPU, ≈ 1.5 h wall, within the time box): `benchmark/spikes/m72_tq4_probe.py` (per-layer
  microbenchmark through the fork's production dispatch), `m72_run_probe.sh` (ABA NAX on / off / on, 10-min idles),
  `m72_probe_report.py` → generated `benchmark/results/m72/PROBE.md`; report `benchmark/results/m72/REPORT.md`; spikes G / H rerun at
  4-bit (`SPIKE_BITS`). Validated against P475 (TQ4 prefill −7…−8 %, MTP OFF decode −5…−8 %; MTP ON tok/s +7…+18 % optimistic).
  Mechanisms (lab notebook 2026-11-07 session 19): sub-cap layout copy (+44 % per decode call), per-query MTP verify (largest decode
  loss), TurboQuant prefill off the Neural Accelerators (dequantize + fused SDPA moves it on, no new attention kernel). Potential vs
  shipped at 260K: decode MTP ON 0.72× → 1.31× (multi-query verify) → 1.51× (+ no copy) → 1.93× (ceiling, uncertain kernel
  rewrite); prefill 0.35× → 0.83× (generic ops) → ≈ 1.00× (fused unpack); ≈ 12 GB less KV.
- Instrument revisions (both before any result was used; superseded outputs in `$STACK_WORKDIR/m72/superseded-instrument-v{1,2}/`):
  v1 byte ceilings read a sliced buffer (a copy); v2's at-cap checkpoint hid the layout copy.

## Next, in order (C310 plan)

1. **S19-P4 → the operator:** go / no-go on 1.2. Lead rec: go, D1 + D2 first (one stride-aware multi-query decode kernel,
   per-query bit-identical to the singleton kernel), then P1 → P2 (prefill: dequantize in rotated space + fused SDPA, then a fused
   unpack kernel), D3 deferred. On go: prototypes in the fork's `dev/` with microbenchmarks against `PROBE.md` → the operator;
   Push 3 (fork) when cited. Then 1.3 (production, four-eyes strict) → Push 4 / 5; 1.4 (P475 matrix for the pick incl. the deferred
   in-situ profilers `MLX_VLM_PREFILL_PROFILE` / `MLX_VLM_MTP_PROFILE`; quality for both picks; MTP ON vs OFF on TQ4) → Push 6.
2. **Push 2** (report + scripts) — asked at the end of session 19; if not yet done, ask again.
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
