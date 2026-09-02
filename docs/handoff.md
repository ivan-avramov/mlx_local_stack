# Handoff — 2026-09-01 evening (M21 conversion chain IN FLIGHT + M21 ARMS CHAIN ARMED behind it; C41 plan awaiting approval)

Single box (M5 Max 64 GB). **TWO detached jobs are LIVE and must not be disturbed:**
1. the M21 conversion chain (`nohup`, pid in `$STACK_WORKDIR/m21/chain.pid`, logs
   `$STACK_WORKDIR/m21/{chain,download,convert_int8,convert_optiq,mem}.log`). int8 control DONE and
   verified (28 GB, 8.627 bpw, g64 affine, vision tower present). OptiQ-mixed KL sweep at 294/497
   17:26, ~76 layers/h → sweep ≈ 20:05, then allocation + write; the chain then restarts the bench
   router on the m6b draft-OFF overlay (that router is immediately replaced by job 2).
2. **the M21 ARMS chain** (`$STACK_WORKDIR/m21/arms_chain.py`, pid `m21/arms.pid`, log `m21/arms.log`,
   launched 17:35): waits for `chain DONE`, verifies both artifacts, restarts the router on the TEMP
   overlay `$STACK_WORKDIR/m21/bench_overlay_m21.yaml`, then pilot(5) → C35 gate → sizing → hep n=50
   → grade → compare for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` then
   `Qwen3.8-27B-Fable-Distill-mlx-uniform-8bit` (int8 DIAGNOSTIC-ONLY; watch `peak_mem_gb` in its
   rows, ~36–39 GB projected). Driver logs `m21/{pilot,full}.log`, watchers `m21/watch_*.log`,
   grade/compare `m21/grade.log`, `m21/compare_*.log`. It STOPS (`FATAL` line) on: artifact
   verification failure, router env wrong, C35 mismatch, pilot short/transport-error. Expected
   wall: OptiQ arm ≈ 1.5–2.5 h, int8 arm ≈ 3–5 h + runaway tail; done ≈ 03:00–06:00 2026-09-02. <!-- allow-shorthand -->
   Monitor by `tail -F m21/arms.log` (pid-file liveness first). After it finishes the router is left
   UP on the M21 overlay — restart it on the m6b overlay (or the registry) before any other work.
   New result dirs appear under `benchmark/results/Qwen3.8-27B-Fable-Distill-{OptiQ-4.5bpw-mixed,mlx-uniform-8bit}/` (to commit as `data(bench)` once graded). <!-- allow-shorthand -->

Fork main = `f5fff9b5` (pushed, submodule bumped). Stack pushed through `93291ab`/`8a2146f`;
**UNPUSHED: `e250df5`, `90a0bc3` and this session's commits** — push needs in-turn approval. Working tree: the SIX intentional `main_models.yaml` overrides (NEVER commit).
Test suite is fully green: 1261 passed, 0 failed (the two stale provenance tests widened to `mtp`,
operator-approved).

## Today (all recorded in campaign-results / lab-notebook / PLAN)
- **M12 CLOSED**: d128k cliff check — NO cliff (Δ strict 0.0 / +4.0 / −8.0pp; challenger's −8 = one
  82K-token meander, 29 % of its 8.4 h arm; prefill-bound ≈ 8 min at 135K on dense trunks). Pooling —
  `run.py compare --pool` built (stratified paired bootstrap; `5af51dc` + `8a2146f`, verifier SHIP with
  mutation checks): all three pooled hep+mbpp d64k pairs INCONCLUSIVE after Holm (n=100, MDE ±13pp;
  ~628 items to resolve ±5pp — not worth it).
- **M29 CLOSED at 1.18×** (profiler `mlx_vlm/speculative/mtp_profile.py` merged to fork main): round is
  verify-bound (81 %); registry stays draft-OFF for `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`.
- Rulings recorded: C40 (a), C41 fix (queued), C42 NO; AGENTS.md gained the C35 `MLX_SERVE_CONFIG` rule
  and PLAN gained **D12** (harness-traffic accounting, operator-approved).
- C35 recurrence (mine) on the first M12 launch: archived + regenerated; rule now in AGENTS.md.

## THE BOX QUEUE
1. **M21 arms — RUNNING via the arms chain (above).** When `=== m21 ARMS DONE ===` appears: read
   `m21/grade.log` + `m21/compare_*.log`, write the four numbers incl. runaway tax (DNF rate + wall
   share) per arm vs the `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` t0.6 reference (n=50, 5
   timeout-DNFs = the motivating 10 %), answer PRECISION-EVERYWHERE vs PRECISION-ON-SENSITIVE-LAYERS,
   record in campaign-results + PLAN M21 + lab-notebook, commit the result dirs.
2. **C41 fork fix** — plan drafted 2026-09-01 evening (planning agent), AWAITING OPERATOR APPROVAL:
   (0) regression test pinning the fused `experts.gate_up_proj` layout output; (a) hoist
   `Qwen3NextMTPSplitter.postprocess`'s separate-expert stacking into a module-level helper and give
   `Qwen3_5MTPSplitter` a `postprocess` that calls it (do NOT re-point `qwen3_5_moe` to the Next
   class — it has `draft_model_cls=None` and would drop the fused split + fp8 conversion);
   (b) `detect_mtp_splitter` tries `text_config.model_type` then root `model_type`, first REGISTERED
   wins; (c) `MTPSplitter.split` raises before writing if any key matches `\.experts\.\d+\.`.
   Files: `mlx_vlm/speculative/drafters/{mtp_split.py,qwen3_5_mtp/split.py}`, tests in
   `mlx_vlm/tests/test_models.py::TestMTPSplit` (synthetic 2-expert (8,8) tensors, mirrors the
   qwen3_next test). Fork markers required (`dev/check_fork_markers.py`). TDD, implementer + verifier,
   then bump the submodule.
3. Then M17 / D11 (blocked on Stage-2) / M18 (BFCL). NVSY/S1 stays parked per O32.

## Standing rules that bit today
- C35 again → AGENTS.md rule (driver env carries `MLX_SERVE_CONFIG`; verify pid + first manifest).
- `cut`/`head` buffer Monitor pipelines (memory file exists); zsh does not word-split `${VAR//,/ }`.
- `.venv/bin/hf` does not exist — `hf` lives in `.venv-optiq/bin`. `.venv` lacks `evalplus` — bench
  drivers run on `.venv-bench`.
- `optiq convert` logs a bpw line PER PHASE (uniform baseline first) and its reported bpw (5.485 for the <!-- allow-shorthand -->
  precedent) is not the manifest's `effective_bits` (4.98); parse the `optiq_mixed` phase and cite the manifest.
- `mlx_vlm.convert` int8 of a 27B is ~11 s (streaming cast at disk speed) — a fast rc=0 is NOT a skip;
  verify config.json + shards + the bpw line, never rc alone.

## Artifacts
M21 `$STACK_WORKDIR/m21/`; M12 `$STACK_WORKDIR/m12/` (comparators, false-provenance archive) + committed
`benchmark/results/*/humanevalplus.d128k.*`; M29 `$STACK_WORKDIR/m29/`. HF cache now also holds the
re-downloaded `TeichAI/Qwen3.8-27B-Fable-Distill` bf16 source checkpoint <!-- allow-shorthand --> (~54 GB, needed it for the conversions — keep).

**Order of resumption: this file → `$STACK_WORKDIR/m21/arms.log` (arms chain alive/where?) → `$STACK_WORKDIR/m21/chain.log` → `docs/PLAN.md` (M21 row) → `docs/open-questions.md`.**
