# Handoff — 2026-09-02 00:30 (M21 CLOSED — negative; C41 LANDED on the fork; box QUIET; pushes owed)

Single box (M5 Max 64 GB). **NO job is live; the router is DOWN on purpose (box quiet since 00:25).**
Restart for the daily driver: `runserver.sh`; for benchmarking: the lean router recipe in AGENTS.md
with `MLX_SERVE_CONFIG=$STACK_WORKDIR/m6b/bench_overlay_draft_off.yaml` (regenerate it after any
registry edit). The M21 temp overlay `$STACK_WORKDIR/m21/bench_overlay_m21.yaml` is retired.

Fork main = `f5fff9b5` (pushed, submodule bumped). Stack pushed through `93291ab`/`8a2146f`;
Stack pushed through `ce5c4c8`. **UNPUSHED: fork `57177a21` (C41 — push FIRST, the stack's submodule pointer references it), then stack `6ad8c9f`, `7bf57f8`, `23f89e6` + the M21 closure commit** — push needs in-turn approval. Working tree: the SIX intentional `main_models.yaml` overrides (NEVER commit).
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
1. **M21 CLOSED (2026-09-02, negative — campaign-results 2026-09-02, PLAN M21).** Three precisions of
   `Qwen3.8-27B-Fable-Distill` <!-- allow-shorthand --> converge on all 50 items; strict 88.0 (uniform-4bit re-measured `t0.6-r2`) /
   88.0 (`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`) / 86.0 (`Qwen3.8-27B-Fable-Distill-mlx-uniform-8bit`),
   all paired deltas INCONCLUSIVE. The 2026-08-20 10 % DNF was a pre-C28 orphan-timeout cascade. Registry
   unchanged. Housekeeping owed: P8 harness fix (empty `quant` block for local-path models since O34 —
   proposed, not applied), optional deletion of the 73 GB of M21 artifacts under `$STACK_WORKDIR`.
2. **C41 LANDED** (fork `57177a21`, stack `6ad8c9f`); C45 holds the verifier's follow-ups (N1 yes / N2
   accept / N3 yes recommended, one small fork commit when the fork is next touched).
3. Next: M17 / D11 (blocked on Stage-2) / M18 (BFCL). NVSY/S1 parked per O32.

## Standing rules that bit today
- A fallback LIST of candidate artifact dirs is a wrong-artifact generator: the M21 runner fell through to
  the converter's `static_mixed` byproduct once (caught in 2 min by reading the worker cmdline). Name the ONE
  admissible artifact; resolve safetensors-index names as paths (sidecars live in subdirs).
- `compare` refuses across fork shas (output-determining) — a reference older than the last fork bump
  must be re-measured before any paired claim; budget the re-measurement into every A/B.
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

**Order of resumption: this file → `docs/PLAN.md` → `docs/open-questions.md` (C45, P8 pending).**
