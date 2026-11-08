# Handoff — 2026-11-07 (session 18 END: P475 stage 1 DONE; C309 — THE GOAL met for both picks; `Qwen3.8-27B-mlx-uniform-4bit` ships as is (TQ4 + MTP ON, CERTIFIED C258); next: M72 TQ4 spike for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, M73)

THE one handoff. Read this, then `docs/PLAN.md` rows M66–M73, then `docs/open-questions.md` top entries (newest first: S18-P20,
S18-P19, C307, S18-P18, C306 … C296). Model names: FULL registry names only. Review rounds: 3 per artifact. Operator stance: bias
for quality; drive to certified picks; ask only at Go / Accept / pushes / scope changes; lead calls filed as they land; offer a
fresh session at clean boundaries. Every Go'd build gets its PLAN row in the ruling's commit (C303 / P642 gap 2).

Discussion ids: session 18 used `S18-P1 … S18-P20` in records; a new session restarts at P1 and cites `S19-P<n>`. Next decision id
**C311**.

## THE GOAL — MET (C309)

Both picks certified in their shipped config: `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` native16 + MTP ON (`CERTIFIED P426
2026-11-04`, C291); `Qwen3.8-27B-mlx-uniform-4bit` TurboQuant 4 KV + MTP ON (`CERTIFIED` C258, 2026-10-30). Next goal (Phase 2,
C307 (3) / C308): the TQ4 performance spike for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (M72) — if TQ4 can beat native16 there,
certify that combination.

## FIRST — verify (each "no" is a blocker)

1. Nothing running: no router on :8000, no P475 orchestrator / `qualify` / `worker.py` / `run_capacity` (check from a script file;
   never with the patterns in your own argv).
2. Pushes: `origin/main` = `35c15d7d`. Local `main` carries data + docs since (`c037cf5a` … this note): the P475 dossiers and
   generated matrix, README / lab-notebook evidence, decisions. **No push until this model's work completes** (C306 (2)): then one
   full stack gate and one push ask (data commits need the full gate; the pre-push hook needs the machine config sourced). Forks:
   `../mlx-vlm` = origin = `e3e38397`; `../mlx-serve` = `1ddf6f84`; stack gitlink `src/mlx-vlm` = `e3e38397`.
3. No worktrees: the stack has only its main checkout; the fork only `main` (session 18 removed the P475 arm worktrees and the
   P658 helper worktrees; all harvested).
4. Power: 140 W / 28 V before any GPU work, gated strictly (session 18 lost a queue to an unplugged adapter; `preflight()` now
   refuses it as NOT_STARTED, C302, but check before launching anyway).

## Done in session 18 (details in open-questions C296–C307)

- P475 stage-1 build fixed on the box: C296 (1) `53e2e321` (base resolution, NOT_STARTED preflights, fork venv, process-group
  reap), C297 `bc07cabc` (`run_capacity --out-dir`: legs write under the leg dir), C298 (old-base dossiers archived), C301
  `97672222` (ON engagement check + records bound to their base; gitlink → `e3e38397`), C302 `4a6a4fd6` (power / qualify pre-run
  refusals are NOT_STARTED). Gates: `9adbae45` PASS 11,937; `35c15d7d` PASS 11,950 (pushed).
- P658 (a) four-eyes light (C299 / C300; `docs/reviews/p658/`): fork `qualify --kv-arm --predictor on --engagement-only`
  (drafter-cache K3 check) + `bench.p475_kv` in `LAUNCHER_MODULES`; fork gate PASS 10,008; pushed.
- **P475 stage 1 DONE** on base `35c15d7d`: 11 checks PASS (OFF kv manifests; ON target + drafter manifests, every drafter cache
  one native `KVCache` == template); smokes VALID; full run 18 valid legs + 1 replacement (an 8 s battery blip), the deciding block
  b3 run as pre-registered (C304; its trigger was the degenerate near-unity case, S18-P13). Matrix
  `benchmark/results/p475/MATRIX.Qwen3.8-27B-mlx-uniform-4bit.md` (`a4ef6f96`); README evidence `02d0d0a9`; mechanism (two-term
  fit: the KV format changes only the context-proportional attention cost; TQ4 decode ≈ ⅕ of native16's effective KV bandwidth)
  in `docs/lab-notebook.md` 2026-11-07. At 260K: N16 46.08 GB / 275.7 prefill / 15.03 decode tok/s; TQ4 29.30 / 128.8 / 12.72.

## Next, in order (C310: the plan forward, with push points)

0. **Phase 0 (session 18, done if `origin/main` = the gated tip):** P475 logs on `evidence` (`eddf2e9c`), a full stack gate on the
   tip, **Push 1** `main` + `evidence`. If `origin/main` is still `35c15d7d`, check the gate receipt and push (pre-approved by C310
   only for that gate).
1. **Phase 1 = M72 — the focus:** the TQ4 performance spike for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` against its baseline
   (native16 + `fused_v1`), time-boxed, no pre-set bar. **1.1 Probe** (≈ a day, little GPU; a quiet box, power gated): per-kernel split
   of TQ4 prefill / decode at 128K / 256K, the forced-off Neural Accelerator control `MLX_METAL_GPU_ARCH=applegpu_g16s`, decode
   effective KV bandwidth, the cost of MTP verify blocks, the ceiling of each fix → the operator; **Push 2** (report + scripts).
   Then, each on the operator's go: **1.2** prototype kernels in the fork's `dev/` (fused decode first, then the never-built fused
   flash prefill) with microbenchmarks → the operator; **Push 3** (fork) when cited. **1.3** the production kernel (four-eyes strict;
   fork gate) → **Push 4**; stack gitlink bump + gate → **Push 5**. **1.4** a P475 matrix for that pick (`p475_kv` parametrized by
   pick first), then, if TQ4 wins, quality vs native16 (covering BOTH picks: it also closes the TQ4 residual of
   `Qwen3.8-27B-mlx-uniform-4bit`, C309 addendum) + MTP ON vs OFF on TQ4 (the P426 harness parametrized by entry), then the
   registry → **Push 6**. Read first: `docs/open-questions.md` S18-P18, S18-P21, P477; the fork's `mlx_vlm/turboquant.py`
   (`mse_prefill`, `_mse_prefill_fused` = never built, `TQ_FUSED_PREFILL`, `TQ_PREFILL_IMPL`); `docs/lab-notebook.md` 2026-08-31
   (Neural Accelerators active) and 2026-11-07 (the two-term fit).
2. **Phase 2 = M73 (S18-P20)**, a parallel CPU track: the sequential early-stopping design (four-eyes strict; decision from the
   boundary, sizes from full-set estimates via revisit; AGENTS.md wording to the operator) → **Push 7**; aim before 1.4.
3. **Phase 3 hygiene** (CPU gaps, never during measured legs): M67 (fork gate + push), M68, M69, M70 (needs Go), M74 (the
   open-questions audit) → one stack gate, **Push 8**.

Push policy (C310): push at every boundary where results or code are committed, within a day; never leave results only on this box;
each push is its own ask unless pre-authorized.

Queued after the GPU work (C303): M67 (S18-P8, fork `-n 4` flake), M68 (P643), M69 (P642 gap 1). Open: M70 (S18-P13, R16 floor).

## Archives (local, no push)

- `$STACK_WORKDIR/archive/p475-base-{1554bfe1,15d90757,9adbae45,35c15d7d}/` (run state, worktree logs; the `9adbae45` one holds
  the six false power-refused records); `$STACK_WORKDIR/archive/session18-worktrees/` (P426 / C258 logs).
- Branches: `archive/p475-u4-<arm>-{1554bfe1,15d90757,9adbae45,35c15d7d}`, `archive/c258x-off`.
- Scrubbed P475 worker / router logs for `evidence`: `$STACK_WORKDIR/archive/p475-base-35c15d7d/p475/evidence-stage/` (and the
  earlier bases' archives) — pushed with the results (C306 (2)).

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
