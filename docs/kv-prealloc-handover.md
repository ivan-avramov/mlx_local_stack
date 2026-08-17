# KV pre-allocation right-sizing — handoff (2026-07-09)

> ## ⚠️ HISTORICAL SNAPSHOT — 2026-07-09. DO NOT READ AS CURRENT STATE.
>
> Kept verbatim as the dated record of what was believed that day; nothing below has been rewritten.
> **Current state lives in `docs/PLAN.md` (the plan) · `docs/open-questions.md` (decisions) · `AGENTS.md` (rules).**
>
> Load-bearing claims below that are now FALSE or superseded:
> - **The TL;DR's proposal — pre-allocate to the request's own ceiling instead of the cap — now runs against a STANDING RULE.** `kv_prealloc_tokens` is set EQUAL to that model's `max_kv_cache_size` precisely so the cache is reserved at the full cap and never reallocs; `AGENTS.md` states "**Do NOT remove or lower prealloc**", because growing 128K→256K requires holding 384K of KV live during the double-buffer and that MEASURABLY OOMed. Do not revive this without going through **O15**, which is still OPEN and names the depth test that would settle it.
> - **Every line number here has drifted.** In `../mlx-vlm` today: `turboquant.py:5351` (`initial_alloc`) → ~5423 and `:5170` → `TurboQuantKVCache` at ~5207; `generate/common.py:262` (`maybe_quantize_kv_cache`) → ~287 and `:288/:292` → ~374; `server/generation.py:436` (`_resolve_generation_budget`) → ~542 and `:477` (`_apply_generation_budget`) → ~584; `apc.py:105` (`_pad_kv_for_capacity`) → ~292. Locate by symbol, not by line.
> - **The "Multi-turn / APC growth" scope bullet is moot:** APC is OFF everywhere as of 2026-08-13, benchmarks and daily driver alike.
> - **Do not paste the "Restart prompt" unchanged** — it would launch exactly the work the standing rule and O15 now govern.

**Status:** investigation done, not yet designed. Hand-off for a **fresh session** where you'll
**restart brainstorming and expand scope**. This captures what we found so a new session starts cold.
Edit the parent fork `../mlx-vlm` (not `src/mlx-vlm`); measurement discipline in `AGENTS.md` applies.

## TL;DR
The TurboQuant KV cache **pre-allocates its buffer to the global `max_kv_size` (e.g. 256K) on first
fill**, deliberately — to avoid the `mx.concatenate` double-buffer spike that incremental growth causes
(you hold the old cache while the new, larger one is allocated). Cost: a **small-prompt request still
grabs the full 256K KV buffer** (memory wasted on the turboquant models, e.g. Qwen3.6-27B-Opus-Distill-OptiQ-4bit). The proposed
fix is to pre-allocate to the **request's own ceiling** — `min(prompt_tokens + effective_max_tokens,
max_kv_size)` — keeping the anti-spike property while right-sizing per request.

## What we found (evidence)
- **Pre-alloc site:** `mlx_vlm/turboquant.py:5351` — `initial_alloc = max(new_end, self.max_kv_size or 0)`.
  On the first fill, `max_kv_size` (the global cap, 256K) dominates → the buffer is allocated to 256K in
  one shot, so every later append writes in-place (no realloc, no spike). `__init__` (`turboquant.py:5170`)
  stores `max_kv_size` and starts `keys=None` (alloc is lazy, on first `update_and_fetch`).
- **The two winners differ:**
  - **distill (turboquant KV)** → `TurboQuantKVCache`, pre-allocs to `max_kv_size`. This is the wasteful path.
  - **Ornith (fp16 KV, `kv_bits: 0`)** → **stock MLX `KVCache`**, which step-grows (default step 256) via
    concatenate — no big pre-alloc, but many small realloc/copy transients over a long sequence.
- **`max_kv_size` is the total-window cap** (prompt + generation). Runtime reserves generation room:
  `generation.py:_resolve_generation_budget` (~:436) computes `remaining = MAX_KV_SIZE − prompt`,
  soft-clamps `max_tokens`, and caps `thinking_budget` to 0.8× effective. So `effective_max_tokens` is
  already known at request time — the input the fix needs.
- **Data point (not pre-alloc at load):** M5 init log showed Qwen3.6-27B-Opus-Distill-OptiQ-4bit at load `ram_used_gb=34.5,
  subprocess_rss_mb≈17.5 GB` (weights); its 256K peak is ~43 GB. So the KV buffer is allocated per
  **request**, not at model load — a small request pre-allocs 256K on first token, not at startup.

## Proposed direction (starting point — expand in brainstorm)
Thread a **per-request capacity** into the cache instead of the flat global `max_kv_size`:

```
target_capacity = min(prompt_tokens + effective_max_tokens, max_kv_size)
initial_alloc   = max(new_end, target_capacity)
```

- Keeps the anti-spike property (buffer sized once to what *this* request can reach → all appends in-place).
- Recovers memory on small prompts (4K prompt + 8K gen → ~12K buffer, not 256K).
- Inputs already exist at cache creation: `prompt_tokens` (post-tokenize) and `effective_max_tokens`
  (`_resolve_generation_budget`). Plumb them to `maybe_quantize_kv_cache` / `TurboQuantKVCache(max_kv_size=…)`
  (see `generate/common.py:262`, `:288/:292`) as a per-request value.

## Scope to consider expanding (you flagged wanting to)
- **fp16 / stock `KVCache` path (Ornith):** step-256 growth = many small transients over 256K. Worth a
  matching pre-alloc-to-request-ceiling? (Would need a custom cache or an mlx patch.)
- **Multi-turn / APC growth:** growing-conversation reuse (APC snapshot/restore) reallocs across turns;
  `apc.py` pads to `min_capacity_tokens` (actual content, e.g. `len(tokens)+1`). How does per-request
  right-sizing interact with APC's prefix reuse + `_pad_kv_for_capacity`?
- **RotatingKVCache** (sliding-window gemma layers): does it pre-alloc its window? relevant for gemma refs.
- **Buffer-pool retention** (`mx.set_cache_limit` / `cache_limit_gb`, derived from `max_kv_size` in
  `cli.py:_derive_cache_limit_gb`): reclaimable pool ceiling, distinct from the KV buffer — but both scale
  with `max_kv_size`; right-sizing one may let you lower the other.
- **Growth policy vs pre-alloc:** alternative to per-request pre-alloc = grow in larger geometric steps
  (fewer reallocs) — trade transient-spike size vs steady memory.

## Constraints / discipline
- **A/B on the same box, same session**, metric `mx.get_peak_memory` (the campaign gate ≤46 GB@256K):
  prove (1) small-prompt peak drops, (2) 256K peak unchanged, (3) the anti-spike property still holds
  (no mid-generation realloc jump). Cross-box/stale baselines are invalid.
- **TDD** the cache sizing (unit test: given prompt N + max_tokens M, buffer allocs `min(N+M, cap)`, and
  a growth test proving no realloc within the request).
- Edit `../mlx-vlm`; test via `PYTHONPATH=../mlx-vlm`; bump the stack submodule to deploy.

## Key files / lines
- `mlx_vlm/turboquant.py:5170` (`TurboQuantKVCache.__init__`), `:5351` (`initial_alloc`).
- `mlx_vlm/generate/common.py:262` (`maybe_quantize_kv_cache`), `:288/:292` (`TurboQuantKVCache(max_kv_size=…)`).
- `mlx_vlm/server/generation.py:436` (`_resolve_generation_budget`), `:477` (`_apply_generation_budget`).
- `mlx_vlm/apc.py:105` (`_pad_kv_for_capacity`), cache classes ~`:1326–1392`.
- fp16 path: stock `mlx_lm.models.cache.KVCache` (step-grow).

## Restart prompt (paste into the fresh session)
> Continue the mlx_local_stack work. I want to design + build KV-cache pre-allocation right-sizing in the
> `../mlx-vlm` fork. Read `docs/kv-prealloc-handover.md` first — it has the finding (TurboQuant pre-allocs
> the KV buffer to the global `max_kv_size`, wasting memory on small prompts; the anti-spike reason it
> exists; the proposed `min(prompt + effective_max_tokens, max_kv_size)` per-request sizing) plus scope I
> want to expand (fp16/stock KVCache path, APC/multi-turn growth, RotatingKVCache, buffer-pool retention,
> growth-step policy). Start with the brainstorming skill — I want to widen scope before we design.
> Bias quality; measurement discipline in `AGENTS.md` (A/B `mx.get_peak_memory` same-box, TDD, edit the
> parent fork).
