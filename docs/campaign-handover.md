# Campaign handover — 2026-07-06

Session checkpoint for the 256K-agentic-coding local-LLM selection campaign. Companions:
`docs/campaign-results.md` (full scoreboard) · `docs/campaign-queue.md` (durable worklist + recovery) · `AGENTS.md` (norms).

## TL;DR verdict
**Ornith-1.0-35B-mlx-uniform-4bit is the pick for local 256K *agentic* coding on 64GB.** NOTE Ornith is
ITSELF an MoE — `qwen3_5_moe`: 256 experts / **8 active** (fine-grained, moe_intermediate 512) + a shared
expert + **hybrid linear-attention** (30/40 layers GatedDeltaNet, 10 full-attn); 35B total but few active
params. That architecture IS why it wins: sparse activation → fast decode + light weights (~19GB @4bit);
linear-attn → tiny KV → fits true 256K. It's the only candidate that clears 256K (`mx.get_peak_memory`
32.4GB ≤46GB gate, retrieval 1.00), is fast enough for the agentic loop (37–75 tok/s, ~5–7× the dense
gemmas), and is respectable on every axis. So the comparison is NOT "dense vs MoE" — it's three specific
models: **Ornith (sparse-MoE + linear-attn) beats BOTH the dense gemma-4-31B AND the other MoE
(gemma-4-26B-A4B-it-OptiQ-4bit)** for this goal. Dense gemma-4-31B = stronger single-shot (LCB 86.7%) but
**192K-capped** + **too slow/finicky for agentic** (~3h/case, needed whole-format). gemma-4-26B-A4B MoE
leads tool-calling (BFCL 94%). Qwen3.6-27B arch DNFs LCB.

## Results (all axes; op-temps/configs in campaign-results.md)
| axis | Ornith-35B u4 (MoE+lin-attn, 8/256 active) | dense gemma-4-31B-6bit | gemma-4-26B-A4B MoE-OptiQ-4bit |
|---|---|---|---|
| 256K capacity | ✅ 32.4GB, ret 1.00 | ❌ 192K cap | — |
| decode speed | 37–75 tok/s | ~7–10 | fast |
| aider agentic (pr2) | **61.8%** (n=34, ~6min/case) | **60%** (n=5, ~3h/case, whole) | pending |
| LCB | 80% @t0.4 | **86.7%** | 80% |
| math500 | 83.3% | 83.3% | — |
| light he+/mbpp+ | 90/80 | 100/70–80 | 100/80 |
| BFCL tool-calling | 74.9% (n=1000) | 79.4% (n=1000) | **94%** (n=1000) |
- Ornith LCB **op-temp = 0.4** (temp-ladder: 0.5/0.6 meander; 0.3/0.4 both 80% pass@1, 0.4 converges best).
- Ornith quirk: meanders (budget-saturates) on the *hardest* items → strict-INVALID on some, but strong pass@1.

## Currently RUNNING
- **M2** → gemma-4-26B-A4B-it-OptiQ-4bit aider (whole, n=5): RUNNING. Log `/tmp/aider_moe_whole.log`. (gemma-4-31b-it-6bit aider DONE = 60% pr2, n=5.)
- **M5** → Ornith BFCL (native FC, full-N): **DONE = 74.9%** (s77.75/m85/p70/pm64; last of the 3 on tool-calling). M5 now FREE.
- Aider containers survive session exit — `docker ps`; grep pass_rate_ in the logs.

## Aider agentic — HOW IT WORKS (the session's main build)
Dockerized via aider's official flow. `benchmark/run_aider_docker.sh <served-model> [N] [edit_format] [run_name]`:
runs the `aider-benchmark` docker image against host mlx-serve (`host.docker.internal:8000`, must bind 0.0.0.0),
mounts `~/aider` + `~/polyglot-benchmark` + the settings YAML, passes `--read-model-settings`.
- **Per-model tuned params live in `aider_config/aider.model.settings.yml`** (SERVED-NAME entries): aider IGNORES
  extra_params in the metadata JSON — only the settings YAML is honored. Non-OpenAI knobs (top_k, rep_pen,
  enable_thinking, thinking_budget) go in `extra_body`; standard (temp/top_p/max_tokens/timeout) top-level.
- **edit_format: gemma = `whole`** (its diff SEARCH/REPLACE loops), **Ornith = `diff`** (works).
- **`timeout: 3600`** in settings is REQUIRED (local gen ~20min/req > litellm default 600s → retry loop).
- Model-metadata (token limits) must be added to the aider clone's `aider/resources/model-metadata.json`
  (M2 + M5 done for the served names) — that's what benchmark.py loads.
- Image built on BOTH boxes (`aider-benchmark`, M2 7GB / M5 4.77GB via `~/aider/benchmark/docker_build.sh`).
- ~15 min/case dense gemma, ~6 min/case Ornith → use subsets (n=10–34), NOT the full 225 (infeasible).

## RECOVERY if session drops
- Aider runs are `docker run` containers → SURVIVE session exit. Check `docker ps`; relaunch via
  `benchmark/run_aider_docker.sh`. Results in stdout logs (`grep pass_rate_`), NOT aider.json (that's the non-docker adapter path).
- M5 IP churns; find via subnet scan (`nc -G 3`). Non-interactive ssh needs PATH prefix (+ `$HOME/.orbstack/bin` for docker); HF_TOKEN via `zsh -ic`.
- M5 keeps an uncommitted `main_models.yaml` (local Ornith/distill entries) — never commit; sync via `git merge --ff-only`.
- Watchers do NOT survive — re-poll manually / re-launch background pollers.

## What's LEFT (next session)
1. Finish + grade: M2 gemma-whole aider (n=5), M5 Ornith BFCL — append to campaign-results.md.
2. (optional) gemma-MoE aider for the full dense-vs-MoE-vs-Ornith agentic H2H (MoE also swaps on co-resident M2 — consider M5 or a lighter setup).
3. (optional) Ornith uniform-6bit (quality variant), SWE-Verified-40 (heavier agentic), judge panel.
4. Deferred: preflight-profile-mismatch fix (canary hardcodes production temp); IFEval blocked (datasets version).
The core selection question is ANSWERED (Ornith for 256K agentic coding); remaining items are confirmation/breadth.
