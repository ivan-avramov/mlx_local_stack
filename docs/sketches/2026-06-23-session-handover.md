# Session handover — EpiCache qwen3_5 port, BFCL FC-mode correction, open-source prep (2026-06-23)

Read alongside `AGENTS.md` (operating/measurement/impl guidelines) and the memories
`project-256k-execution-campaign`, `project-local-256k-eval-program`,
`project-suffix-decoding-nonlossless`.

## State — all committed + pushed; both machines synced; routers idle
- **Stack `mlx_local_stack`** @ `d530d3c` (origin/main). History **scrubbed of PII** (paths/hosts/usernames
  removed from all commits via `filter-repo --replace-text`; commits + messages + dates preserved, SHAs changed).
- **Fork `mlx-vlm`** @ `150a76f` (origin/main, also scrubbed). **`mlx-serve`** @ `5c5de1e` (unchanged; was already clean).
- Both GitHub repos are PUBLIC. Recovery bundles (machine-local, not in repo): pre-scrub `*.bundle` on the dev
  box, `m5_backup` on the remote box.
- **Machine-local config**: each box has `${XDG_CONFIG_HOME:-$HOME/.config}/mlx_local_stack/config.sh`
  (`$STACK_REPO / $REMOTE_HOST / $REMOTE_USER / $REMOTE_REPO / $REMOTE_HOME / $DISTILL_MODEL_PATH`); committed
  template is `config.example.sh`. Scripts source it; no absolute paths/hosts live in the repo. The remote box's
  `main_models.yaml` keeps an UNCOMMITTED local distill registry entry (literal local path) — never commit it.

## What this session accomplished
1. **EpiCache ported to `qwen3_5`** (`mlx-vlm` fork): `make_cache` wraps only the 16/64 full-attention KVCache
   layers (leaves the GatedDeltaNet `ArraysCache` linear layers); `_qwen35_scalar_positions` helper does the MRoPE
   split after eviction (query/new-keys RoPE at the TRUE `rope_offset`; mask/kv-length at the physical offset);
   SnapKV `observe` hook. Mirrors gemma4. Opt-in via `MLX_EPICACHE_BUDGET`, behaviour-preserving off-EpiCache.
   5 unit tests + 7 core. Live-validated on the dense Qwen-OptiQ: retrieval@16K acc 1.0 all depths (rope correct).
2. **EpiCache on-vs-off gates** (thinking on, per-model native config):
   - gemma-OptiQ: latent reasoning ≤5% PASS (acc 1.0 to 112K vs OFF 128K); retrieval recall lost under aggressive
     eviction (by design — pre-question block eviction). Decode "2.4×" number is **confounded** (M2-ON vs stale
     M5-OFF baseline) — re-measure clean same-box.
   - Qwen-OptiQ (clean, same-box remote): decode **1.89×** @160K (12.5→23.6 tps), MLX-peak 26.6→24.6GB, latent ≤5%
     PASS, retrieval recall **∝ budget:ctx ratio** (4:1→1.0, 8:1→0.67, 40:1→0.0). EpiCache = a long-ctx
     decode-speed + reasoning-safe lever, NOT safe for retrieval-heavy work at aggressive (fixed) budgets.
3. **BFCL coding H2H — methodology corrected (the big lesson).** First-pass numbers (gemma 0.93 > Qwen 0.835 >
   distill 0.74, "gemma wins coding") were a **pure artifact**: prompt-mode for all (Qwen/qwen3_5 native mode is FC
   `<tool_call>`) + bfcl's `min(4096)` generation cap truncating verbose thinking mid-`<think>` + Qwen3.6 emitting
   `"parameters"` (not `"arguments"`) → `KeyError`. **Clean FC-mode re-run** (each model native mode, thinking on,
   cap 16384, 0 truncations, 200 items): **gemma 0.93 ≈ Qwen 0.94 ≈ distill 0.94 — statistically TIED.** No longer
   contradicts published (Qwen ≥ gemma). Tool-calling does NOT discriminate the candidates.
4. **AGENTS.md** operating/measurement/implementation guidelines added; repo sanitized + history scrubbed for
   open-source. Reusable BFCL harness: `benchmark/bfcl_shim` registers our model names → the right handler
   (`GemmaEpiHandler` prompt / `QwenFCEpiHandler` native FC) with thinking-strip + cap-raise + FC-schema-normalize;
   `benchmark/run_bfcl_h2h.sh {gemma|qwen|distill}` launcher.

## Corrected campaign read
- **Daily-driver is UNSETTLED on capability.** Tool-calling (BFCL AST) is tied; the clean differentiator gemma has
  is **speed** (~2.9× decode, ~5.5× prefill, same-box) + **256K footprint**, while *matching* the dense models on
  tool-calling. Whether that's enough vs the dense models' edge on *harder* coding/reasoning (per published) is the
  open question — and BFCL AST is too easy to answer it.

## What's left (prioritized for the next session)
1. **EpiCache batched-generation support** (the explicit pending item). `EpiCacheKVCache` raises
   `"does not yet support batching"` in `generate/ar.py` `to_batch_cache` (the `BatchGenerator` path used by
   `/v1/completions`). The single-sequence `/v1/chat/completions` path works (that's where EpiCache runs today).
   Fix: teach `to_batch_cache` to wrap a batched inner cache for B=1 (and raise a clear error / fall back for B>1,
   which is memory-prohibitive for long ctx anyway). TDD; mirror the gemma4 path.
2. **Daily-driver discriminator — HARDER coding.** Tool-calling tied, so run **LiveCodeBench / SWE-bench / Aider
   polyglot** (adapters already built per `project-local-256k-eval-program`) on the 3 candidates
   (gemma-OptiQ-4bit, Qwen-OptiQ-4bit, Opus-distill-OptiQ) in **native mode, thinking ON, with a generous
   generation cap so reasoning finishes** (the BFCL lesson — never let truncation count as failure). This is what
   actually decides the daily-driver.
3. **EpiCache follow-ups**: (a) clean **same-box** gemma on-vs-off decode ratio (the 2.4× was confounded);
   (b) **budget-vs-recall curve** (how large a budget preserves recall at a given ctx); (c) a dedicated
   **code-symbol-retrieval probe** (the open "can it consult repo symbols under eviction?" question — answered so
   far only via the budget:ctx ratio pattern); (d) **TQ-inner-cache** integration (wrap the quantized state — from
   the original plan); (e) the **ship/don't-ship** call (EpiCache as an opt-in reasoning/long-ctx lever, off by
   default, never for retrieval-heavy coding).
4. Optional, if completing the full bake-off: IFEval, judge panel — but synthetic axes are ceiling'd; coding (#2)
   is the live differentiator.

## Gotchas (see AGENTS.md for the full set)
- **Thinking is ON for every test**; a `thinking_budget` hit or mid-`<think>` truncation is a FAIL to INVESTIGATE,
  never "fixed" by lowering the cap. **Apples-to-apples = same box/session/config** (this session burned time on
  cross-box / stale-baseline confounds). **When results contradict published, suspect the harness first.**
- One resident model per machine; unload between. Edit parent forks (`../mlx-vlm`, `../mlx-serve`), not `src/*`;
  commit fork → push → bump submodule. Propose before committing/pushing.
- `bfcl-eval` installed on both boxes (`.venv-bench`). BFCL token cap raised via `MLX_BFCL_MAX_TOKENS` (default 16384).
- After any crash, **restart the router** (degraded "ready, no subprocess → 500s" state bit us this session).
