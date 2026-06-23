# Implementation-session handoff — EpiCache + BFCL + convergence (2026-06-22, part 2)

Follows the convergence-investigation handoff (`2026-06-22-session-handoff.md`). This one
covers the implementation push: convergence resolved, differentiation tooling, the
`/v1/completions` endpoint + proxy, and EpiCache v1+v2.

## State — all committed + pushed, both boxes idle
- **mlx-vlm `e25168f`** — `/v1/completions` endpoint; EpiCache v1 (eviction pipeline) + v2 (SnapKV attention-mass score).
- **mlx-serve `5c5de1e`** — `/completions` + `/v1/completions` proxy routes (model→hf_path rewrite).
- **stack `200a8ff`** — submodules bumped; `edf6209` carries the convergence harness fix + graded/vartrack probes + BFCL_v4 adapter rework.
- M2 router was redeployed (running `5c5de1e`/`e25168f`); both GPU boxes idle. bfcl-eval installed on **M2** only (`.venv-bench`), not M5.

## What this session established
1. **Convergence question CLOSED.** The CWE aggregation non-convergence is a degenerate repetition loop (gemma-MoE) / exhaustive enumeration (dense) — quant/temp/sampling-independent, an **adversarial probe artifact, not a model deficiency**. ALL candidates converge crisply on real reasoning (vartrack ~700–1300 tok) + coding. Harness fixed: `converged = finish=="stop" AND completion_tokens < thinking_budget`.
2. **Differentiation tooling** (`run_agg_graded.py`): enumeration-load ladder → token-efficiency signal. At n_distinct=20: **Qwen-OptiQ 4976 < gemma-8bit ~9.6K < gemma-4bit-OptiQ 13127** (arch + quant effects; cliff noisy at n=1 → use med_tok).
3. **EpiCache** (the long-ctx KV speed/memory lever) implemented + validated end-to-end on gemma-OptiQ (coherent + correct at ctx≫budget; RoPE-after-eviction fix proven; 7/7 unit tests).
4. **BFCL** infrastructure complete + verified (curl): backend `/v1/completions` (forces thinking off) + mlx-serve `/completions` proxy + model→hf_path rewrite.

## Plan — next steps (prioritized)

### 1. EpiCache ≤5% quality gate (the real validation) — gemma first
v1+v2 are implemented + coherence-validated, but the **quality gate is NOT yet run**. Do an on-vs-off comparison on a real long-context task:
- Restart a box's router with `MLX_EPICACHE_BUDGET=<M>` (+ `MLX_EPICACHE_BLOCK`) in its env (read in gemma4 `make_cache`); load gemma-OptiQ-4bit.
- Run the retrieval + latent-reasoning harnesses at ctx > budget, EpiCache **on vs off**, and compare accuracy (target ≤5% drop) + decode tok/s + peak mem (the win: bounded KV → faster decode + bigger ctx).
- Note: block-wise eviction evicts *before* the final question is seen, so a single needle-in-middle is a weak test; use the harness’s aggregate accuracy. Tune budget/sink/recent/obs_window.
- Then: **qwen3_5 port** (apply the same `rope_offset` dual-offset to qwen3_5 `language.py` — it’s mrope + GatedDeltaNet hybrid, wrap only its full-attn KVCache layers), then **TurboQuant inner cache** (wrap the quantized state; key-norm/observe need dequant).

### 2. BFCL coding H2H — finish the last-mile (the correct way)
Infra is done. The last-mile is **making bfcl send our registered model name** (NOT a proxy passthrough — mlx-serve is multi-model, guessing is wrong):
- Register a **custom bfcl ModelConfig** mapping our mlx-serve registry name (e.g. `gemma-4-26b-a4b-it-8bit`) → the gemma `OSSHandler` (template) + a **local** tokenizer (`REMOTE_OPENAI_TOKENIZER_PATH` = the model’s HF snapshot). Then `--model gemma-4-26b-a4b-it-8bit`: bfcl uses the handler for templating but sends the registered name → proxy rewrites to hf_path → deterministic routing. (bfcl-eval supports supplemental/local model configs — find the mechanism in `bfcl_eval`; avoid editing site-packages if possible.)
- Also fix the adapter `--limit`: bfcl-v4 `--run-ids` reads the id file from a **fixed site-packages path** — either write there or just use full-category runs.
- Run BFCL on **M2** (bfcl-eval installed there), gemma-OptiQ-4bit vs Qwen-OptiQ-4bit, AST categories (`simple_python,multiple,parallel,parallel_multiple`). Eyeball template fidelity (near-zero acc ⇒ template mismatch, not capability).

### 3. Daily-driver decision (the original campaign goal)
Synthetic axes are ceiling’d + convergence is resolved. The remaining differentiator is **coding** (BFCL above + LiveCodeBench/SWE if pursued). Candidates: gemma-OptiQ-4bit (fast MoE, most 256K headroom) vs Qwen-OptiQ-4bit (dense, more token-efficient reasoning) vs the M5-local OptiQ-distill (256K-fit, over-enumerates aggregation like all gemma/Qwen but converges on real reasoning).

## Gotchas / environment
- **Edit PARENT forks** `../mlx-vlm` + `../mlx-serve` (the `src/*` submodules import by default); commit fork → push → bump submodule, or test parent via `PYTHONPATH=../mlx-vlm`. `../mlx-vlm/.venv` imports the parent fork directly (handy for standalone tests).
- **Test python**: `.venv-bench` has mlx + pytest + json_repair (added) but NOT `mlx_audio` → `test_server.py` won’t collect there; `.venv` (and `src/mlx-serve/.venv`, `../mlx-vlm/.venv`) are full-deps. epicache tests run under `.venv-bench`.
- **EpiCache is opt-in** (`MLX_EPICACHE_BUDGET>0`) — dormant + zero behaviour change otherwise. gemma4 only (qwen3_5 not yet ported).
- M2 router restart recipe: `set -a; . ./.env 2>/dev/null; set +a; MLX_SERVE_CONFIG=main_models.yaml nohup uv run mlx-serve start >logs/main_model.log 2>&1 &`. One model per box; unload after testing.
- M5 has uncommitted local state (distill registry entry in `main_models.yaml`; a `stash@{0}` + `/tmp/m5_bfcl_backup/` from the BFCL probe). `git pull && git submodule update --force` to sync; preserve `main_models.yaml`.
