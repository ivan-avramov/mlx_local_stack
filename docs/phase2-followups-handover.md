# Phase-2 Follow-ups — Handover (2026-07-09)

Phase-2 (perf + KV-memory optimization on the two settled winners) is **complete and shipped**.
This hands off the remaining follow-ups for a fresh session. Read `AGENTS.md` first for operating rules.

> **STATUS UPDATE 2026-07-09:**
> - **FU-2 = SHIPPED + DEPLOYED** (stack `main` @ current; forks mlx-serve `8333436` / mlx-vlm `9f087c2`;
>   M2 + M5 deployed + runtime-verified). Registry-side default sampling via `main_models.yaml`
>   `generation_defaults`. Spec: `docs/superpowers/specs/2026-07-09-registry-default-sampling-design.md`.
> - **FU-1 = PARKED** with a cheap→heavy staged plan (Tier 0 smoke → Tier 1 cheap reject filter →
>   Tier 2 overnight gate). Full plan in `docs/campaign-queue.md` (PHASE-2 section). Low ROI (2.9 GB on
>   the alternative model, no speed) — resume only if that memory is wanted; run Tier 0+1 before the overnight.
> - **FU-3 = PARKED** (low ROI for this deployment; transferable-technique / B200 goal only).
> The section below is the original handover context.

## What shipped (context)

Winners: `Ornith-1.0-35B-mlx-uniform-4bit` (THE PICK — hybrid linear-attn MoE, **fp16 KV**) +
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` (alternative — dense qwen3_5, **turboquant 4-bit KV**).
Boxes: M2 (local, ≤192K, co-resident ~22 GB) + M5 (remote, 256K, deploy target).

- **#1 APC prefix caching** — SHIPPED (`runserver.sh`: `APC_ENABLED=1 APC_NUM_BLOCKS=16384`). Lossless, **34–147× agentic multi-turn TTFT**, no memory/speed cost @256K. Only shows in *multi-turn* use.
- **#4 suffix decoding** — SHIPPED both winners (`main_models.yaml`: `draft_kind: suffix`, no cooldown). Quality-neutral (distill he+94/mbpp+77; Ornith he+93/mbpp+86/LCB93.3 ≈ OFF, conv intact) + speed-positive (distill 1.2–2.7× edit; Ornith 2.41× verbatim / 1.09× novel — the MoE-hostile prior was wrong).
- **#5 fused GQA-tile-reuse DECODE kernel** — SHIPPED (fork `bf7c793`, submodule bumped). Lossless (fp32-exact), ~1.3× over legacy TQ decode; +2–7% end-to-end (attention is ~10/40 layers of these hybrids), does NOT beat native fp16.
- **#2 KV** — Ornith **stays fp16** (4-bit slower even with the new kernel); distill-kv3 → FU-1.

Stack pushed (`main` @ `38bade5`); fork pushed (`bf7c793`); M5 synced + router redeployed (APC on, suffix live on both winners). Full record: `docs/campaign-results.md` (PHASE-2 section), `docs/campaign-queue.md`.

## Follow-ups (priority order)

### FU-1 — distill kv3 reasoning gate (parked memory lever) · MEDIUM value, ~1 box-day
distill 4-bit → **3-bit** turboquant KV saves **2.9 GB @256K** (no speed change). PARKED because the
he+ gate (96.5 vs 95.7) is too weak — ceiling'd short-chain coding does NOT stress KV *fidelity*. The
open worry: 3-bit KV may degrade **multi-step math / precise long-context retrieval** (compounding
attention errors).
- **Do:** OFAT gate — distill kv4 (OFF) vs a `…-kv3` registry variant (ON), SAME items: **math500 (N≈30)
  + aime (N≈15) + a multi-needle / retrieval-at-depth probe @128–256K** (single-needle already held 1.0).
  Grade math/aime mechanically; retrieval via the needle harness (`benchmark/needle_256k.py`).
- **Bar:** quality-neutral on REASONING + retrieval, OFAT, measured at deploy length (not just coding).
  N=15/30 single-sample resolves DRAMATIC drops only — read convergence + big deltas, not subtle ones.
- **Verdict rule:** adopt kv3 only if clearly harmless. It's a modest win on the *alternative* model.

### FU-2 — registry-side default sampling in mlx-serve (config-consistency gap) · SMALL build, HIGH consistency value
The one real config hole (see AGENTS.md "Client/agent integrations"): **vscode + zed configs carry NO
sampling**, and mlx-serve holds no per-model defaults, so those clients run at the mlx_vlm worker's
DEFAULT sampling — the tuned op-temps + `presence_penalty 0.0` don't reach them, so **suffix may silently
fall back for vscode/zed**.
- **Do:** add per-model default sampling to the registry — `temperature`/`top_p`/`top_k`/`min_p`/
  `presence_penalty` in `main_models.yaml`, threaded `config.py` → `process_manager.py` (worker flag/
  defaults) → `mlx_vlm`, **applied only when the request omits them** (explicit request params still win).
  Same threading pattern as `kv_bits`/`draft_kind` (`config.py:79-85` + `process_manager.py:106-116`).
- **Bar:** a request without sampling gets the registry defaults; a request WITH them is unchanged. Then
  set the winners' tuned sampling as defaults → all 5 clients consistent + suffix engages everywhere.
- Edit the **parent forks** (`../mlx-serve`, `../mlx-vlm`), TDD, propose before commit/push.

### FU-3 — #5 decode-kernel follow-on builds · LOW ROI, optional
Design `docs/superpowers/specs/2026-06-17-unified-fused-quantized-kv-attention-design.md` (Phases 3–4):
**prefill MMA kernel** (M5 Metal-4 TensorOps / M2 `simdgroup_matrix` — the M5-specific backend), the
**Prod codec** (higher-fidelity KV), **gemma4 TQ generality**. LOW ROI for THIS deployment (APC amortizes
agentic prefill; the winners are set) — pursue only for the transferable-technique / B200 goal. Each is
its own brainstorm → spec → plan.

## Operating gotchas (the ones that bit this campaign)
- **ONE model per box.** ALWAYS `pkill -9` workers **and verify death** before launching on a box — a
  stray worker co-resident with a new one taints speed/memory (happened once here).
- **M5 sync:** `pull.rebase=true` → `git fetch origin main && git merge --ff-only origin/main` +
  `git submodule update --force`. Bare-PATH ssh: prepend `/opt/homebrew/bin:$HOME/.local/bin` (+
  `$HOME/.orbstack/bin` for docker). Preserve M5-local `benchmark/bfcl_shim/sitecustomize.py`.
- **Grading:** LCB → `.venv-lcbgrade` (M5) + LiveCodeBench cache; he+/mbpp+ evalplus **docker** works on
  **M2**, NOT in M5 headless ssh (OrbStack daemon isn't up) — grade he+/mbpp+ on M2 or via an interactive M5 session.
- **Meander tax:** distill (Ornith less so) meanders to the 81920 thinking budget on some hard items →
  quality gates are DNF-heavy + slow. Cap N or lean on robust signals (pass@1 *delta* + convergence, not
  absolute single-sample numbers). NEVER lower the thinking budget to "make it converge."
- **Suffix caveat:** shows only in multi-turn / high-reuse; the micro-bench "beats fp16" was vs *dequant*-
  fp16 (native fp16 is faster) — don't re-conflate.
