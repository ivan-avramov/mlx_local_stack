# KV cache pre-allocation right-sizing — fixed per-model `kv_prealloc_tokens`

**Date:** 2026-07-09. **Status:** design, approved (execution authorized; no code yet).
**Forks:** `../mlx-vlm` + `../mlx-serve` (edit parents, not `src/*` submodules).

## Goal & the premise flip (established empirically)

Two goals pull against each other: **(1)** eliminate mid-generation KV realloc spikes; **(2)** don't
pre-allocate more than a request needs. The deployment resolves the tension by choosing goal #1
absolutely — set the pre-alloc to the **full cap** per model, so the cache **never reallocs**
(single-shot or APC multi-turn) and never risks a transient peak above the steady 256K footprint
(which already fits the ≤46 GB gate). That makes adaptive per-request right-sizing and the APC
per-turn resize moot for the deployed config.

**Premise flip vs the handover (`docs/kv-prealloc-handover.md`).** The handover assumed TurboQuant
pre-allocs 256K and wastes it on small prompts. That pre-alloc is **dormant, not active, on the
deployed path** (confirmed empirically). The pre-alloc code (`turboquant.py:5351`, `initial_alloc =
max(new_end, self.max_kv_size or 0)`) only fires when `max_kv_size` is non-None, but the deployed
suffix/inline path passes `max_kv_size=None`:

- `to_generate_kwargs()` omits it (traced, `server/generation.py:792`).
- `get_max_kv_size` returns None for quantized-KV models anyway (`generation.py:401`).

So **neither winner pre-allocs today; both grow (realloc) during decode** → goal #1 is currently
**unmet**.

**The real prize** is removing the growth **transient**, not saving small-prompt memory. Today
`_reserve_state_capacity` (`turboquant.py:4331`) grows geometric 1.25×∨step-256. Near high-water H
the worst realloc holds ~0.8H while allocating H, so the transient is ≈ **1.8× the KV high-water** —
and `mx.get_peak_memory` (the campaign gate) captures exactly that spike. Pre-allocating H once at
prefill removes it at **every** prompt size, including 256K.

## Evidence (two-tier probe, archived at `/tmp/kv_prealloc_probe/`)

**Tier 1 — deterministic, no model** (feed fake K/V: 1000-tok prefill then 400 decode steps):

| variant | first-fill cap | reallocs in decode |
|---|---|---|
| `TurboQuantKVCache(max_kv_size=None)` | 1000 (not 262144) | 2 (1000→1250→1562) |
| `TurboQuantKVCache(max_kv_size=262144)` | 262144 | 0 |
| plain `KVCache` (fp16, Ornith) | 1024 | 2 (1024→1280→1536) |
| `BatchTurboQuantKVCache` | 1000 | 2 |

**Tier 2 — real `generate_step`** with a monkeypatched (fast) fake model dispatch:

- `generate_step` forwards `max_kv_size` **verbatim** to both `make_prompt_cache` (`ar.py:337`) and
  `maybe_quantize_kv_cache` (`ar.py:288`): None→None, 262144→262144 (spied).
- Server `to_generate_kwargs()` contains **no** `max_kv_size` — the joint where it's dropped today.

Both probe scripts become fork unit/integration tests.

## Design — the `kv_prealloc_tokens` parameter

**Semantics:** an explicit **fixed pre-alloc floor** in tokens. On first fill each cache allocates
`max(new_end, kv_prealloc_tokens)`. Unset/0 ⇒ today's grow-from-`new_end` behavior (backward
compatible). **No adaptive / per-request `min(prompt+max_tokens, cap)` math on the hot path** —
deliberately traded away for the never-realloc guarantee.

**Validation — hard fail if `kv_prealloc_tokens > max_kv_size`**, at two fail-loud points:

- **mlx-serve registry parse** — earliest, before the worker launches.
- **mlx-vlm worker CLI startup** — authoritative; it owns the buffers.

Equal is allowed (that is the `= cap` config).

**Safety invariant:** every cache class keeps its existing growth path as a fallback. Pre-alloc just
makes it hit zero times in the common case; an under-estimate degrades to today's behavior, never a
crash.

## The cache variants + the new pre-alloc classes

The deployed 4-model router set exercises **three distinct single-sequence cache classes** (both gemma
refs share `QuantizedKVCache`); the work adds pre-alloc to those three plus their three batched twins
(six classes total). The per-model mapping:

| model | KV config | class | ownership |
|---|---|---|---|
| Ornith-1.0-35B-mlx-uniform-4bit (winner) | `kv_bits: 0` | `KVCache` (fp16) → new `PreallocKVCache` | fork |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit (winner) | `turboquant, kv_bits: 4` | `TurboQuantKVCache` | fork (`turboquant.py`) |
| gemma-4-31B-it-qat-6bit (ref) | `uniform, kv_bits: 4` | `QuantizedKVCache` → new fork `PreallocQuantizedKVCache` | mlx_lm upstream → fork subclass |
| gemma-4-26B-A4B-it-OptiQ-4bit (ref) | `uniform, kv_bits: 4` | `QuantizedKVCache` → fork subclass | mlx_lm upstream → fork subclass |

Per-class changes:

1. **`PreallocKVCache`** — new, in `mlx_vlm/models/cache.py` next to `KVCache`: fp16,
   **non-rotating**, drop-in for stock `KVCache` (same interface: `update_and_fetch`, `state`,
   `offset`, `trim`, plus APC snapshot fields). Pre-allocs `(B, H, kv_prealloc_tokens, D)` on first
   fill, writes in place, `state` slices `[:offset]`, no eviction, geometric growth fallback.
2. **`TurboQuantKVCache`** — add a `kv_prealloc_tokens` ctor arg **distinct from `max_kv_size`**;
   pre-alloc `max(new_end, kv_prealloc_tokens)`. (`__init__` at `turboquant.py:5170`, alloc at
   `:5351`.)
3. **`PreallocQuantizedKVCache`** — new fork subclass of mlx_lm `QuantizedKVCache` (which is upstream
   and step-256 grows — `step=256`, confirmed). Pre-sizes the quantized triple (packed uint32 +
   scales + biases) to `kv_prealloc_tokens`; growth fallback retained.
4. **Batched twins** `BatchKVCache`, `BatchTurboQuantKVCache` (`turboquant.py:6490`),
   `BatchQuantizedKVCache` (`mlx_vlm/models/cache.py:181`) — all fork-owned — add the same pre-alloc
   param.

### Integration = post-creation conversion pass

Pre-alloc can't be a swap inside `make_prompt_cache`, because for real models it returns
`model.make_cache()` (`mlx_vlm/models/cache.py:931`). So the pass mirrors the existing
`maybe_quantize_kv_cache`:

- Extend `maybe_quantize_kv_cache` (`generate/common.py:262`) to thread `kv_prealloc_tokens` into
  the TQ + uniform conversions.
- New `maybe_preallocate_kv_cache(cache, kv_prealloc_tokens)` converts **remaining** plain
  `KVCache`→`PreallocKVCache` (and any un-converted `QuantizedKVCache`→`PreallocQuantizedKVCache`);
  leaves TQ, `RotatingKVCache` (sliding-window/gemma — already bounded), linear-attn, and chunked
  caches untouched.

**OOM-safety ordering (critical).** `maybe_preallocate` runs **after** `maybe_quantize` and touches
only leftover fp16/uniform caches. Otherwise Qwen3.6-27B-Opus-Distill-OptiQ-4bit would briefly pre-alloc full-fp16 256K KV
for all layers (~4× its TQ budget) before quantizing → OOM. Net: distill quantized layers pre-alloc
on the TQ side; only the one intentionally-unquantized last layer (`common.py:307` skips it) gets
fp16 pre-alloc (~0.5 GB). Ornith pre-allocs all layers fp16.

## Threading chain (registry → cmdline → cache; all in our forks)

```
main_models.yaml:  kv_prealloc_tokens: <max_kv_cache_size>   (structural field, per model)
  → mlx-serve config.py:  ModelConfig.kv_prealloc_tokens = entry.get("kv_prealloc_tokens", 0)  [+ validate ≤ max_kv_cache_size]
  → mlx-serve process_manager.py:  cmd += ["--kv-prealloc-tokens", str(...)]   (vision worker only, per confirm #3)
  → mlx-vlm cli.py:  --kv-prealloc-tokens → KV_PREALLOC_TOKENS env  [+ validate ≤ --max-kv-size, fail loud]
  → server/generation.py:  get_kv_prealloc_tokens() → gen_kwargs (inline + batched paths)
  → ar.py stream_generate/generate_step:  forward to make_prompt_cache + maybe_quantize + maybe_preallocate
  → apc.py:  feed min_capacity_tokens = kv_prealloc_tokens so APC-built caches pre-alloc too (existing `_pad_kv_for_capacity` at apc.py:105)
```

**configgen is untouched.** `kv_prealloc_tokens` is a **structural** field; `configgen/source.py`
reads only `name`/`hf_path`/`presentation`/`generation_defaults` and ignores structural keys, so the
emitters never see it and the `configgen check` **drift guard stays green** (no client-config
change). It is **not** a `presentation:` field and gets no emitter. (Consistent with
config-generator-design.md §1: "structural fields … stay as-is".)

Tier-2 already proved `stream_generate` forwards params faithfully, so this is additive plumbing.

## `main_models.yaml` updates

Add `kv_prealloc_tokens: <value>` (= that entry's `max_kv_cache_size`) to every router model:

| model | value |
|---|---|
| gemma-4-31B-it-qat-6bit | 196608 |
| gemma-4-26B-A4B-it-OptiQ-4bit | 262144 |
| Ornith-1.0-35B-mlx-uniform-4bit | 262144 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | 262144 |

**Task model** (`Qwen2.5-1.5B-Instruct-4bit`, :8092) is launched by `runserver.sh` directly (not via
mlx-serve), has no `max_kv_cache_size`, and sits near no peak limit → **optional `runserver.sh`
follow-up**, out of the mlx-serve threading (confirm #3).

Update AGENTS.md: note `kv_prealloc_tokens` as a **structural** registry field (mlx-serve-only),
**not** a client-facing carrier — no configgen/emitter involvement.

## APC per-turn resize (completeness — built last, off by default)

`_pad_kv_for_capacity(min_capacity_tokens)` (`apc.py:105`) already pads a reused cache to a capacity.
Add an **adaptive mode**: at each turn boundary set `min_capacity_tokens = min(content +
effective_max_tokens, cap)` — a controlled **between-turn** resize, never mid-generation. The
deployed fixed `= cap` makes this a no-op (the cache is already at cap). Lowest priority.

## Testing (TDD)

- **Unit (Tier-1 → `test_kv_prealloc.py` in the fork):** each of the 4 classes pre-allocs to
  `kv_prealloc_tokens` with **0 reallocs** across decode; `PreallocKVCache` /
  `PreallocQuantizedKVCache` correctness (state slicing, growth fallback, `trim`); validation
  hard-fails when `kv_prealloc_tokens > max_kv_size`.
- **Pipe (Tier-2 → fork integration tests):** the server now **includes** `kv_prealloc_tokens` in
  gen_kwargs and it reaches both cache hooks; mlx-serve builds the `--kv-prealloc-tokens` arg; worker
  startup fails when `> max_kv_size`.
- **Live acceptance (`mx.get_peak_memory`, same-box M5, the campaign gate):** distill + Ornith (+
  optionally a gemma), small-prompt and 256K, pre-alloc **on vs off** — prove (a) **0** mid-decode
  reallocs (log check), (b) peak ≤ steady 256K footprint with **no growth transient above it**, (c)
  still ≤46 GB gate. Same-box/same-session per AGENTS.md measurement discipline; cross-box/stale
  baselines invalid.

## Risks / known

- Upstream `QuantizedKVCache` is mlx_lm-owned → cover via a **fork subclass**
  (`PreallocQuantizedKVCache`), consistent with the fp16 approach; the subclass must preserve the
  quantized-triple (packed/scales/biases) semantics.
- APC snapshot/restore/trim must work with `PreallocKVCache` — verify interface parity with stock
  `KVCache`.
- `RotatingKVCache` sliding-window (gemma) layers are left alone (already bounded to their window).
- The batched path is the secondary (concurrency/mtp) path, not the winners' suffix inline path;
  per-seq capacity = the fixed param.
- Task-model :8092 pre-alloc is not covered by mlx-serve threading (optional `runserver.sh`
  follow-up).

## Sequencing

TDD, failing tests first (the Tier-1/Tier-2 probes seed them):

1. `PreallocKVCache` + `PreallocQuantizedKVCache` + `TurboQuantKVCache` arg + batched twins.
2. `maybe_preallocate_kv_cache` + `maybe_quantize` threading + ordering guard.
3. ar.py/generation.py plumbing + `get_kv_prealloc_tokens`.
4. mlx-vlm CLI arg + env + startup validation.
5. mlx-serve `config.py` field + `process_manager.py` cmdline + parse validation.
6. `main_models.yaml` values + AGENTS.md note.
7. Live `mx.get_peak_memory` A/B on M5.
8. APC per-turn resize (completeness) last.

Edit parent forks, test via `PYTHONPATH=../mlx-vlm`, bump stack submodules to deploy.
