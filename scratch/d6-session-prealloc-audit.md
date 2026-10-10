# D6 — Session-cache × prealloc audit

Analysis-only, read-only. Repo `$STACK_REPO`, fork `$HOME/ws/mlx-vlm`.
No files modified, no models loaded, router untouched.

## 1. Where the floor materializes

**It is lazy, not eager.** `PromptCacheState.__init__` (`mlx_vlm/generate/common.py:573-584`)
sets `self.cache = None` — creating a session via `session_manager.get_or_create_prompt_cache_state`
(`mlx_vlm/server/session_manager.py:218-255`) allocates nothing but a Python dict entry
(`state`, `last_used`, `turn_hashes`). The actual per-layer KV arrays are built on that
session's **first request**, inside the generation path (`_process_cached_request`,
`mlx_vlm/server/generation.py:1706-1810`), which forwards `kv_prealloc_tokens` into
`gen_kwargs` (`generation.py:1761-1763`) and — because `prompt_cache_state.cache is None` on
that first call — the reuse branch at `mlx_vlm/generate/dispatch.py:929` is skipped and a
fresh cache is constructed instead.

The floor itself is written in three near-identical `if self.keys is None: allocate at
max(needed, prealloc_tokens)` sites, one per KV representation in use across the registry:

- **fp16 / no KV quant** (`kv_bits: 0`, e.g. `Ornith-1.0-35B-mlx-uniform-4bit`,
  `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit`): `PreallocKVCache.update_and_fetch`,
  `mlx_vlm/models/cache.py:2740-2753`. On first fill, `cap = max(target, prealloc_tokens)`
  rounded to `step=256`, and `mx.zeros((B, n_kv_heads, cap, head_dim))` is allocated for keys
  and values.
- **standard uniform-quantized KV** (`kv_quant_scheme: uniform`, integer `kv_bits`, e.g. both
  `gemma-4-*` entries): `PreallocQuantizedKVCache.update_and_fetch`, `cache.py:2790-2817`. Same
  shape, floored the same way, but the allocation is the `(packed uint32, scale, bias)` triple.
- **TurboQuant KV** (`kv_quant_scheme: turboquant`, fractional/turbo `kv_bits`, e.g. both
  campaign winners' `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` and the `Qwen3.8-27B` family):
  `TurboQuantKVCache.update_and_fetch`, `mlx_vlm/turboquant.py:5408-5427`. Same first-fill
  floor logic (`initial_alloc = max(new_end, prealloc_tokens, max_kv_size)`).

The floored arrays are then handed back into `PromptCacheState.update()` at the end of the
turn (call sites `mlx_vlm/generate/dispatch.py:1339/1357/1366`) and stay attached to that
session's dict entry — at full floored size — for as long as the session is retained, whether
or not it is ever used again.

**Eviction is LRU-by-count only, no idle timeout.** `get_or_create_prompt_cache_state`
(`session_manager.py:248-254`) pops the least-recently-used entry
(`_session_caches.popitem(last=False)`) whenever a **new** session is created and the dict
exceeds `_session_cache_max` (CLI default 8, `mlx_vlm/server/cli.py:462`,
`MLX_VLM_CACHE_SESSION_MAX`). `last_used` is recorded on every touch
(`session_manager.py:231,241,312,326`) but is **never read** anywhere else in the fork — there
is no idle-timeout reaper keyed off it, confirmed by grep across `mlx_vlm/server/*.py`. The
only other evictor is `clear_session_caches()` (`session_manager.py:258-261`), which drops
*all* sessions on model unload — the router's `inactivity_timeout_seconds: 10800` (3h,
`main_models.yaml:3`) is the only backstop, and it is whole-model, not per-session. Net effect:
under steady traffic, a resident model accumulates floored sessions until it hits the count cap
(8 by default) and holds them there for up to 3 hours of continued activity, regardless of how
stale most of them are.

This matches the mechanism already logged for the 2026-08-17 51GB incident
(`docs/lab-notebook.md:2108-2124`): fp16 (`kv_bits: 0`) floor × session retention was the exact
multiplier — that entry is the origin of this D6 item.

## 2. Worst-case memory table, daily-driver config

**Formula, by KV representation** (`B` = batch = 1, per full-attention layer; layers that are
`linear_attention`/Mamba-style don't hold a growing KV cache at all — their state is
fixed-size and untouched by `kv_prealloc_tokens`, confirmed by the layer-count math below
matching measured/registry figures):

```
fp16 (kv_bits=0):        bytes/token = 2(K+V) × n_kv_heads × head_dim × 2 (fp16)         × n_full_attn_layers
uniform-4bit (QuantizedKVCache, group_size=64 default, mlx_vlm/generate/common.py:26):
                          per-element = bits/8 + 2×(2/group_size)   [packed + fp16 scale + fp16 bias]
                          bytes/token = 2(K+V) × n_kv_heads × head_dim × per-element        × n_full_attn_layers
TurboQuant (kv4):         empirically ~16 KiB/token total (see below) — derivation differs
                          per-layer (norm+packed code, not group/scale/bias), not re-derived
                          from first principles here.
```

`n_full_attn_layers` and `n_kv_heads`/`head_dim` were read directly from each model's cached
`config.json` under `~/.cache/huggingface/hub` (read-only inspection, no model load) —
`num_hidden_layers` / `full_attention_interval` (`layer_types` cross-checked) give the
full-attention layer count; `layers_block_type` for the Nemotron `nemotron_h` hybrid.

TurboQuant's per-token rate is taken from two already-measured registry/notebook points
(`main_models.yaml:275`, `docs/lab-notebook.md:2120-2124`): ~2 GiB/session at cap 131072 for
the winner, ~4 GiB/session at cap 262144 for the `Qwen3.8-27B` family — both linear at
**16 KiB/token**, which also lines up with the fp16-equivalent-then-÷4 back-of-envelope for the
same architecture (64 layers, `full_attention_interval 4` → 16 full-attn layers, `n_kv_heads
4`, `head_dim 256` → fp16-equivalent would be 64 KiB/token; 4-bit is ~¼ of that).

| model | KV kind | full-attn layers | n_kv_heads | head_dim | B/token | prealloc cap | **floor/session** | weight footprint |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `gemma-4-31B-it-qat-6bit` | uniform-4bit | 10 (60÷6) | 16 | 256 | 46,080 B | 49,152 | **2.11 GiB** | 31.29 GB |
| `gemma-4-26B-A4B-it-OptiQ-4bit` | uniform-4bit | 5 (30÷6) | 8 | 256 | 11,520 B | 65,536 | **0.70 GiB** | 18.78 GB |
| `Ornith-1.0-35B-mlx-uniform-4bit` | fp16 | 10 (40÷4) | 2 | 256 | 20,480 B | 262,144 | **5.00 GiB** | 20.40 GB |
| `Qwen3.6-27B-Opus-Distill-OptiQ-4bit` | TQ4 | 16 (64÷4) | 4 | 256 | ~16,384 B | 262,144 | **~4.00 GiB** | 18.75 GB |
| `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` | fp16 | 6/52 (`nemotron_h` hybrid) | 2 | 128 | 6,144 B | 262,144 | **1.50 GiB (formula floor)** | 17.78 GB |
| `Qwen3.8-27B-mlx-uniform-4bit` | TQ4 | 16 (64÷4) | 4 | 256 | ~16,384 B | 262,144 | **~4.00 GiB** | 15.13 GB |
| `Qwen3.8-27B-static-mixed-4bit` | TQ4 | 16 | 4 | 256 | ~16,384 B | 262,144 | **~4.00 GiB** | 13.33 GB |
| `Qwen3.8-27B-OptiQ-4.5bpw-mixed` | TQ4 | 16 | 4 | 256 | ~16,384 B | 262,144 | **~4.00 GiB** | 18.44 GB |

⚠️ Nemotron caveat: the formula floor (attention-layer KV only, 1.5 GiB) is *lower* than what
the capacity-ladder growth rate in `main_models.yaml:213-217` implies (~1.1 GB per 65,536
tokens ⇒ ~4.4 GB projected at 262,144) — likely additional MoE/prefill-scratch state the
simple per-layer formula doesn't capture. Treat 1.5 GiB as a lower bound, not the number to
plan capacity around; re-measure directly (`/metrics` or a peak-memory probe across N idle
sessions) before relying on it.

**Worst case at the current default `MLX_VLM_CACHE_SESSION_MAX=8`** (steady-state resident
floor only — weights + N × per-session floor; excludes the *additional* prefill-scratch spike
the actively-generating session pays on top, so real MLX-peak will read higher than this table
for whichever session is live):

| model | n=1 | n=2 | n=4 | **n=8 (current default)** |
|---|---:|---:|---:|---:|
| `gemma-4-31B-it-qat-6bit` | 33.4 GB | 35.5 GB | 39.7 GB | **48.2 GB — over gate** |
| `gemma-4-26B-A4B-it-OptiQ-4bit` | 19.5 GB | 20.2 GB | 21.6 GB | 24.4 GB |
| **`Ornith-1.0-35B-mlx-uniform-4bit`** (winner) | 25.4 GB | 30.4 GB | 40.4 GB | **60.4 GB — over gate** |
| **`Qwen3.6-27B-Opus-Distill-OptiQ-4bit`** (winner) | 22.8 GB | 26.8 GB | 34.8 GB | **50.8 GB — over gate** |
| `NVIDIA-Nemotron-3.5-Lightning-30B-A3B-4bit` | 19.3 GB | 20.8 GB | 23.8 GB | 29.8 GB (formula floor; treat as a lower bound per caveat above) |
| `Qwen3.8-27B-mlx-uniform-4bit` | 19.1 GB | 23.1 GB | 31.1 GB | **47.1 GB — over gate** |
| `Qwen3.8-27B-static-mixed-4bit` | 17.3 GB | 21.3 GB | 29.3 GB | 45.3 GB |
| `Qwen3.8-27B-OptiQ-4.5bpw-mixed` | 22.4 GB | 26.4 GB | 34.4 GB | **50.4 GB — over gate** |

**Headline finding: this is not just the already-known candidate-screening incident.** Both
currently-*deployed daily-driver winners* — `Ornith-1.0-35B-mlx-uniform-4bit` and
`Qwen3.6-27B-Opus-Distill-OptiQ-4bit` — blow the 46 GB gate on steady-state floor alone at the
CLI's own default session cap of 8 (60.4 GB and 50.8 GB respectively), before any
prefill-scratch overhead is even added. A single busy OpenWebUI session with a handful of open
chat tabs reaches 8 distinct sessions well inside the 3-hour unload window with no idle-based
relief.

## 3. Recommendation

**`MLX_VLM_CACHE_SESSION_MAX` for `runserver.sh` daily use: 2, not the CLI default of 8.**

Derivation, folding in the measured *single-session* real peaks (which already include
prefill scratch on top of the steady floor) rather than the formula-only steady state:
- Ornith: measured 256K single-session peak 32.4 GB = 20.4 GB weights + 5.0 GB floor + ~7.0 GB
  scratch. At N retained sessions (only the active one pays scratch): `20.4 + 5.0N + 7.0 ≤ 46`
  ⇒ N ≤ 3.7 ⇒ **N=3 is the loosest safe value**.
- Qwen3.6-27B-Opus-Distill-OptiQ-4bit: measured 256K peak 37.6 GB = 18.75 + 4.0 + ~14.85 GB
  scratch (turboquant pack/unpack is evidently costlier here). `18.75 + 4.0N + 14.85 ≤ 46`
  ⇒ N ≤ 3.1 ⇒ **N=3**.

N=3 is the largest value both winners individually clear, with essentially no margin (both
land within ~1 GB of the gate). Given the campaign's standing bias ("when in doubt, do the
more rigorous thing") and that this number is a same-day fix rather than a measured
guarantee, **N=2** is the safer operating point until it's been run through an actual
multi-session peak-memory probe (open 2-3 real conversations, force generation on each, read
`mx.get_peak_memory`) — this audit derived the floor from code + config, not from a live
measurement, and the Nemotron discrepancy above is a reminder that the formula alone
under-counts at least once in this set.

**Is the fork fix worth it? Yes** — N=2 defeats most of the point of the session cache (its
whole value, per AGENTS.md's APC section, is the ~17× cost-per-total-token win on multi-turn
reuse; capping at 2 conversations makes every third-and-later concurrent chat pay full
re-prefill). The floor-per-idle-session behavior is a genuine design gap, not an inherent cost
of caching.

**Fix shape (sketched, not implemented):** the floor only needs to exist while a session is
the one actively being generated on — the server is already B=1/serial per chat_id
(`_process_cached_request` docstring, `generation.py:1728-1729`), so at any instant at most one
session is "hot." Shrink a session's cache back down to its real `offset` (no floor padding)
immediately after that turn finishes, and let the existing first-fill floor logic re-apply
lazily the next time that session is used:

- Add a `shrink_to_offset()` method to `PreallocKVCache` / `PreallocQuantizedKVCache`
  (`mlx_vlm/models/cache.py`, sibling to the existing offset-slicing pattern in
  `PreallocKVCache.to_quantized()`, `cache.py:2765-2778`) and an equivalent on
  `TurboQuantKVCache` (`turboquant.py`, near `update_and_fetch`, `:5408`) — allocate a
  step-256-rounded buffer sized to `self.offset` (not `prealloc_tokens`), copy the valid
  prefix, drop the padding.
- Call it from the three `prompt_cache_state.update(...)` sites
  (`mlx_vlm/generate/dispatch.py:1339,1357,1366`) right before the shrunk cache is stored, or
  equivalently from `PromptCacheState.update()` itself (`generate/common.py:596`) so every
  caller gets it uniformly.
- Trade-off to test before shipping: this reintroduces a one-time reallocate-and-copy on that
  session's *next* turn (exactly the cost prealloc exists to avoid), but only at the start of
  that turn's own prefill — a single clean allocation with no concurrent competing allocation,
  unlike the mid-generation double-buffer scenario the standing prealloc-floor rule guards
  against. Needs a latency measurement (extra ms per resumed turn) and a repeat of the O15-style
  memory probe before it's trusted, but the shape is sound: it keeps `MLX_VLM_CACHE_SESSION_MAX`
  at 8 for *routing/hash-match* purposes (cheap — just token-id lists and hashes) while bounding
  the expensive part (materialized KV arrays) to the single session actually in flight.

## Sources consulted (file:line)

- `mlx_vlm/generate/common.py:573-584` (`PromptCacheState.__init__`, cache=None)
- `mlx_vlm/server/session_manager.py:218-261` (session create/evict/clear)
- `mlx_vlm/server/generation.py:1706-1810` (`_process_cached_request`, kv_prealloc_tokens threading)
- `mlx_vlm/generate/dispatch.py:929-1016,1339,1357,1366` (reuse branch, cache store-back)
- `mlx_vlm/models/cache.py:2730-2847` (`PreallocKVCache`, `PreallocQuantizedKVCache`)
- `mlx_vlm/turboquant.py:5408-5434` (`TurboQuantKVCache.update_and_fetch`)
- `mlx_vlm/server/cli.py:462-468` (`MLX_VLM_CACHE_SESSION_MAX` default 8)
- `mlx_vlm/generate/common.py:26` (`DEFAULT_KV_GROUP_SIZE = 64`)
- `main_models.yaml` (current kv config for all 8 prealloc'd models)
- `docs/lab-notebook.md:2090-2124` (51 GB incident writeup, origin of PLAN D6)
- cached `config.json` for each model under `~/.cache/huggingface/hub` (architecture dims;
  read-only, no model load)
