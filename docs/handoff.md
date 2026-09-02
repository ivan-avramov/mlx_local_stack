# Handoff — 2026-09-01 evening checkpoint (M12 CLOSED; M21 conversions IN FLIGHT — chain survives the session restart)

Single box (M5 Max 64 GB). **ONE detached job is LIVE and must not be disturbed:** the M21 conversion
chain, `nohup`, pid in `$STACK_WORKDIR/m21/chain.pid`, logs `$STACK_WORKDIR/m21/{chain,download,convert_int8,convert_optiq,mem}.log`.
It already produced the int8 control (`$STACK_WORKDIR/models/Qwen3.8-27B-Fable-Distill-mlx-uniform-8bit`,
28G, 8.627 bpw, gs64 affine) and is now in the mixed-recipe KL sensitivity sweep <!-- allow-shorthand -->
(~218/497 layers at 18:30, ~76 layers/h → sweep done ≈ 20:30 + allocation/write; output
`$STACK_WORKDIR/optiq_out/Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, recipe: target-bpw 4.0,
candidate-bits 4,8, gs64 — the `Qwen3.8-27B-OptiQ-4.5bpw-mixed` recipe, ~4.5 effective bpw). **When it
finishes it RESTARTS the bench router itself** on the draft-OFF overlay and writes the listener pid to
`$STACK_WORKDIR/m12/router_off.pid`. :8000 is intentionally DOWN until then (quiet window). Swap-alarm
sampler runs inside the chain (`mem.log`, ALARM lines at +8 GB); swap flat so far. Monitor by
re-arming `tail -F` on `chain.log` — pid-file liveness + a known-positive line first.

Fork main = `f5fff9b5` (pushed, submodule bumped). Stack pushed through `93291ab`/`8a2146f`;
**UNPUSHED: `e250df5`** (draft_kind test widening + PLAN D12) and this handoff commit — push needs
in-turn approval. Working tree: the SIX intentional `main_models.yaml` overrides (NEVER commit).
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
1. **M21 arms — when the chain finishes**: verify both artifacts (config.json + shards + bpw line in the
   convert logs), register BOTH in a TEMP registry/overlay copy (never the committed registry; local
   paths; `generation_defaults` from `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`'s certified t0.6 tune,
   budget 81920, cap 262144, prealloc=cap), then per the M21 row: hep n=50 at t0.6, same items/seeds as
   the `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit` reference — 5-item seeded pilot first (standing rule), `--sampling-profile deployed`
   requires the temp registry in `MLX_SERVE_CONFIG` (C35!), bench_watch + monitor alongside. int8 is
   DIAGNOSTIC-ONLY (~36–39 GB peak projected — watch capacity); OptiQ-mixed is the deployable treatment.
   Compare each vs `Qwen3.8-27B-Fable-Distill-mlx-uniform-4bit`'s existing hep rows (t0.6, 10 % DNF was
   the motivating signal); the question is PRECISION-EVERYWHERE vs PRECISION-ON-SENSITIVE-LAYERS as the
   runaway driver — report the four numbers incl. runaway tax.
2. **C41 fork fix** (engineering, no box): qwen3_5 MTP splitter — separate-expert `postprocess`,
   detection fallback to root `model_type`, fail-loud on per-expert sidecar keys; TDD, implementer +
   verifier, then bump. Propose the plan first.
3. Then M17 / D11 (blocked on Stage-2) / M18 (BFCL). NVSY/S1 stays parked per O32 (operator re-affirmed
   interest 2026-09-01 — `docs/switchyard-plan.md` is the ready plan for when it re-enters).

## Standing rules that bit today
- C35 again → AGENTS.md rule (driver env carries `MLX_SERVE_CONFIG`; verify pid + first manifest).
- `cut`/`head` buffer Monitor pipelines (memory file exists); zsh does not word-split `${VAR//,/ }`.
- `.venv/bin/hf` does not exist — `hf` lives in `.venv-optiq/bin`. `.venv` lacks `evalplus` — bench
  drivers run on `.venv-bench`.
- `mlx_vlm.convert` int8 of a 27B is ~11 s (streaming cast at disk speed) — a fast rc=0 is NOT a skip;
  verify config.json + shards + the bpw line, never rc alone.

## Artifacts
M21 `$STACK_WORKDIR/m21/`; M12 `$STACK_WORKDIR/m12/` (comparators, false-provenance archive) + committed
`benchmark/results/*/humanevalplus.d128k.*`; M29 `$STACK_WORKDIR/m29/`. HF cache now also holds the
re-downloaded `TeichAI/Qwen3.8-27B-Fable-Distill` bf16 source checkpoint <!-- allow-shorthand --> (~54 GB, needed it for the conversions — keep).

**Order of resumption: this file → `$STACK_WORKDIR/m21/chain.log` (is the chain alive/done?) → `docs/PLAN.md` (M21 row) → `docs/open-questions.md`.**
