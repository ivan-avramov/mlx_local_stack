# KV Pre-allocation Right-sizing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fixed per-model `kv_prealloc_tokens` parameter that pre-allocates every KV cache variant to a token floor on first fill, so the deployed stack never reallocs mid-generation (no growth transient above the steady peak).

**Architecture:** A new pre-alloc value threads registry → mlx-serve cmdline → mlx-vlm worker env → per-request `gen_kwargs` → cache creation. Three single-sequence cache classes gain the floor (`PreallocKVCache` new, `TurboQuantKVCache` arg, `PreallocQuantizedKVCache` new fork subclass), plus their three batched twins. Pre-alloc is applied by a post-creation conversion pass (`maybe_preallocate_kv_cache`) that runs **after** `maybe_quantize_kv_cache`; every class keeps its existing growth path as a fallback.

**Tech Stack:** Python, MLX (`mlx.core`), mlx_lm cache classes, pytest. Two forks: `../mlx-vlm` and `../mlx-serve`.

## Global Constraints

- **Edit the parent forks** `../mlx-vlm` and `../mlx-serve`, NOT `src/*` submodules. Deploy by bumping the stack submodules.
- **Test mlx-vlm** with the fork venv: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest <path> -v`.
- **TDD**: write the failing test first, watch it fail, minimal code to pass.
- **Validation is fail-loud**: hard-error when `kv_prealloc_tokens > max_kv_size`. Equal is allowed.
- **Growth-path fallback is retained** in every cache class — pre-alloc only makes it hit zero times.
- **OOM-safety ordering (invariant):** `maybe_preallocate_kv_cache` runs AFTER `maybe_quantize_kv_cache`, touching only leftover fp16/uniform caches (never pre-alloc full-fp16 all-layers before quantizing).
- **Conversion timing (invariant, from `ar.py:539`):** `quantize_cache_fn` fires after each prefill chunk, so caches are non-empty (offset ≈ chunk) when conversion runs. Therefore: (a) fp16 models (`kv_bits is None`, e.g. Ornith) pre-alloc at cache *creation* (empty→`PreallocKVCache`, before prefill) — safe because no quantize will touch them; (b) quantized models thread `prealloc_tokens` into the TQ/uniform conversion (bulk layers) and rely on `maybe_preallocate_kv_cache` running *after* quantize to copy-convert the leftover fp16 skip-layer + any `QuantizedKVCache`. `maybe_preallocate_kv_cache` handles **non-empty** caches by copying content (it is idempotent — a no-op once a layer is already a Prealloc/TQ variant).
- **Cache-class ctor arg is `prealloc_tokens`; the request/config/env/threading param is `kv_prealloc_tokens`.** Keep this split consistent.
- **`configgen` is untouched**: `kv_prealloc_tokens` is a structural field (`configgen/source.py` ignores structural keys); the `configgen check` drift guard must stay green.
- **Commits**: work on a feature branch per fork; write commit messages from `git diff --staged`; do NOT push without asking.
- **Spec:** `docs/superpowers/specs/2026-07-09-kv-prealloc-rightsizing-design.md`.

---

### Task 1: `PreallocKVCache` (fp16, single-sequence)

**Files:**
- Modify: `../mlx-vlm/mlx_vlm/models/cache.py` (add class near stock `KVCache` import; imports `KVCache` from `mlx_lm.models.cache`)
- Test: `../mlx-vlm/mlx_vlm/tests/test_kv_prealloc.py` (create)

**Interfaces:**
- Produces: `PreallocKVCache(prealloc_tokens: int = 0)` — subclass of `mlx_lm.models.cache.KVCache`. Pre-allocs `(B, H, ceil(max(need, prealloc_tokens)/256)*256, D)` fp16 on first fill; inherits `state`/`offset`/`trim`/`to_quantized`; overflow beyond the floor falls back to the parent's step-256 concatenate growth.
- Produces: `PreallocKVCache.from_kvcache(src: KVCache, prealloc_tokens: int) -> PreallocKVCache` — copies a (possibly non-empty) plain cache's content into a freshly pre-allocated buffer. Used by `maybe_preallocate_kv_cache` to convert a mid-prefill fp16 cache without a growth transient.

- [ ] **Step 1: Write the failing test**

Add to `../mlx-vlm/mlx_vlm/tests/test_kv_prealloc.py`:

```python
import mlx.core as mx
from mlx_vlm.models.cache import PreallocKVCache

H, D = 8, 128


def _fake(T):
    return mx.zeros((1, H, T, D), mx.float16), mx.zeros((1, H, T, D), mx.float16)


def test_prealloc_kvcache_allocs_floor_and_never_reallocs():
    c = PreallocKVCache(prealloc_tokens=262144)
    k, v = _fake(1000)
    c.update_and_fetch(k, v)
    assert c.keys.shape[2] == 262144          # allocated to the floor, not 1024
    for _ in range(400):                       # decode
        c.update_and_fetch(*_fake(1))
    assert c.keys.shape[2] == 262144          # zero reallocs
    assert c.offset == 1400


def test_prealloc_kvcache_floor_below_prefill_uses_prefill():
    c = PreallocKVCache(prealloc_tokens=512)
    c.update_and_fetch(*_fake(1000))
    assert c.keys.shape[2] == 1024            # ceil(1000/256)*256; floor 512 < prefill


def test_prealloc_kvcache_zero_is_backward_compatible():
    c = PreallocKVCache(prealloc_tokens=0)
    c.update_and_fetch(*_fake(1000))
    assert c.keys.shape[2] == 1024            # identical to stock KVCache
    c.update_and_fetch(*_fake(400))
    assert c.keys.shape[2] > 1024             # grows (fallback)


def test_prealloc_kvcache_state_and_trim_inherited():
    c = PreallocKVCache(prealloc_tokens=4096)
    c.update_and_fetch(*_fake(1000))
    ks, vs = c.state
    assert ks.shape[2] == 1000                # state slices to offset, not capacity
    assert c.trim(200) == 200
    assert c.offset == 800


def test_prealloc_kvcache_from_kvcache_copies_nonempty():
    from mlx_lm.models.cache import KVCache
    src = KVCache()
    src.update_and_fetch(*_fake(512))          # a mid-prefill plain cache
    c = PreallocKVCache.from_kvcache(src, prealloc_tokens=262144)
    assert c.keys.shape[2] == 262144           # pre-allocated to the floor
    assert c.offset == 512                      # content preserved
    for _ in range(400):
        c.update_and_fetch(*_fake(1))
    assert c.keys.shape[2] == 262144           # zero reallocs after copy
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_kv_prealloc.py -v`
Expected: FAIL — `ImportError: cannot import name 'PreallocKVCache'`.

- [ ] **Step 3: Write minimal implementation**

In `../mlx-vlm/mlx_vlm/models/cache.py`, after the `KVCache` import/definition is available, add:

```python
class PreallocKVCache(KVCache):
    """fp16 KVCache that pre-allocates its buffer to a fixed token floor on the
    first fill, so later appends write in place (no realloc, no growth transient).
    Non-rotating. Overflow beyond the floor falls back to the parent's step-256
    concatenate growth."""

    def __init__(self, prealloc_tokens: int = 0):
        super().__init__()
        self.prealloc_tokens = int(prealloc_tokens or 0)

    def update_and_fetch(self, keys, values):
        if self.keys is None and self.prealloc_tokens > 0:
            B, n_kv_heads, _, k_head_dim = keys.shape
            v_head_dim = values.shape[3]
            prev = self.offset  # 0 on first fill
            target = max(prev + keys.shape[2], self.prealloc_tokens)
            cap = ((target + self.step - 1) // self.step) * self.step
            self.keys = mx.zeros((B, n_kv_heads, cap, k_head_dim), keys.dtype)
            self.values = mx.zeros((B, n_kv_heads, cap, v_head_dim), values.dtype)
            self.offset += keys.shape[2]
            self.keys[..., prev : self.offset, :] = keys
            self.values[..., prev : self.offset, :] = values
            return self.keys[..., : self.offset, :], self.values[..., : self.offset, :]
        return super().update_and_fetch(keys, values)

    @classmethod
    def from_kvcache(cls, src, prealloc_tokens):
        """Copy a (possibly non-empty) plain KVCache into a pre-allocated one."""
        c = cls(prealloc_tokens=int(prealloc_tokens or 0))
        if src.keys is not None and src.offset > 0:
            c.update_and_fetch(
                src.keys[..., : src.offset, :], src.values[..., : src.offset, :]
            )
        return c
```

If `KVCache` is not already imported at module top, add `from mlx_lm.models.cache import KVCache` (it is used by `make_prompt_cache` already — reuse the existing import).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_kv_prealloc.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
cd ../mlx-vlm && git add mlx_vlm/models/cache.py mlx_vlm/tests/test_kv_prealloc.py
git commit -m "feat(cache): PreallocKVCache — fp16 pre-alloc floor with growth fallback"
```

---

### Task 2: `PreallocQuantizedKVCache` (uniform, single-sequence)

**Files:**
- Modify: `../mlx-vlm/mlx_vlm/models/cache.py` (add `from mlx.utils import tree_map` if absent; add class)
- Test: `../mlx-vlm/mlx_vlm/tests/test_kv_prealloc.py`

**Interfaces:**
- Produces: `PreallocQuantizedKVCache(group_size: int = 64, bits: int = 8, prealloc_tokens: int = 0)` — subclass of `mlx_lm.models.cache.QuantizedKVCache`. Pre-sizes the quantized triple (packed uint32 + scales + biases) to the floor; inherits `state`/`meta_state`/`trim`; overflow falls back to parent step-256 growth.
- Produces: `PreallocQuantizedKVCache.from_quantized(src: QuantizedKVCache, prealloc_tokens: int) -> PreallocQuantizedKVCache` — copies a (possibly non-empty) quantized cache's triple directly into pre-allocated buffers (cannot round-trip through `update_and_fetch`, which re-quantizes fp inputs). Used by `maybe_preallocate_kv_cache`.

- [ ] **Step 1: Write the failing test**

Append to `test_kv_prealloc.py`:

```python
from mlx_vlm.models.cache import PreallocQuantizedKVCache


def test_prealloc_quantized_allocs_floor_and_never_reallocs():
    c = PreallocQuantizedKVCache(group_size=64, bits=4, prealloc_tokens=262144)
    c.update_and_fetch(*_fake(1000))
    assert c.keys[0].shape[2] == 262144       # packed dim pre-sized to floor
    for _ in range(400):
        c.update_and_fetch(*_fake(1))
    assert c.keys[0].shape[2] == 262144       # zero reallocs
    assert c.offset == 1400


def test_prealloc_quantized_zero_is_backward_compatible():
    c = PreallocQuantizedKVCache(group_size=64, bits=4, prealloc_tokens=0)
    c.update_and_fetch(*_fake(1000))
    assert c.keys[0].shape[2] == 1024         # step-256, like stock QuantizedKVCache


def test_prealloc_quantized_from_quantized_copies_nonempty():
    src = lmcache.QuantizedKVCache(group_size=64, bits=4)
    src.update_and_fetch(*_fake(512))          # a mid-prefill quantized cache
    c = PreallocQuantizedKVCache.from_quantized(src, prealloc_tokens=262144)
    assert c.keys[0].shape[2] == 262144        # pre-allocated triple
    assert c.offset == 512                      # content preserved
```

(Add `from mlx_lm.models import cache as lmcache` to the test imports if not already present.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_kv_prealloc.py -k quantized -v`
Expected: FAIL — `ImportError: cannot import name 'PreallocQuantizedKVCache'`.

- [ ] **Step 3: Write minimal implementation**

In `cache.py`, ensure `from mlx_lm.models.cache import KVCache, QuantizedKVCache` and `from mlx.utils import tree_map` are imported, then add:

```python
class PreallocQuantizedKVCache(QuantizedKVCache):
    """QuantizedKVCache that pre-allocates the quantized triple (packed uint32 +
    scales + biases) to a fixed token floor on first fill. Later appends write in
    place; overflow falls back to the parent's step-256 growth."""

    def __init__(self, group_size: int = 64, bits: int = 8, prealloc_tokens: int = 0):
        super().__init__(group_size=group_size, bits=bits)
        self.prealloc_tokens = int(prealloc_tokens or 0)

    def update_and_fetch(self, keys, values):
        if self.keys is None and self.prealloc_tokens > 0:
            B, n_kv_heads, num_steps, k_head_dim = keys.shape
            v_head_dim = values.shape[-1]
            prev = self.offset
            el_per_int = 8 * mx.uint32.size // self.bits
            target = max(prev + num_steps, self.prealloc_tokens)
            new_steps = ((target + self.step - 1) // self.step) * self.step
            shape = (B, n_kv_heads, new_steps)

            def init_quant(dim):
                return (
                    mx.zeros((*shape, dim // el_per_int), dtype=mx.uint32),
                    mx.zeros((*shape, dim // self.group_size), dtype=keys.dtype),
                    mx.zeros((*shape, dim // self.group_size), dtype=keys.dtype),
                )

            self.keys, self.values = init_quant(k_head_dim), init_quant(v_head_dim)
            self.offset += num_steps
            qk = mx.quantize(keys, group_size=self.group_size, bits=self.bits)
            qv = mx.quantize(values, group_size=self.group_size, bits=self.bits)
            for i in range(len(self.keys)):
                self.keys[i][..., prev : self.offset, :] = qk[i]
                self.values[i][..., prev : self.offset, :] = qv[i]
            return tree_map(lambda x: x[..., : self.offset, :], (self.keys, self.values))
        return super().update_and_fetch(keys, values)

    @classmethod
    def from_quantized(cls, src, prealloc_tokens):
        """Copy a (possibly non-empty) QuantizedKVCache's triple into a pre-allocated
        buffer. Copies quantized arrays directly (no re-quantization)."""
        c = cls(group_size=src.group_size, bits=src.bits,
                prealloc_tokens=int(prealloc_tokens or 0))
        c.offset = src.offset
        if src.keys is not None:
            n = src.offset
            cap = max(n, c.prealloc_tokens)
            cap = ((cap + c.step - 1) // c.step) * c.step

            def _grow(triple):
                out = []
                for arr in triple:
                    shp = list(arr.shape)
                    shp[2] = cap
                    buf = mx.zeros(tuple(shp), dtype=arr.dtype)
                    buf[..., :n, :] = arr[..., :n, :]
                    out.append(buf)
                return tuple(out)

            c.keys = _grow(src.keys)
            c.values = _grow(src.values)
        return c
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_kv_prealloc.py -k quantized -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
cd ../mlx-vlm && git add mlx_vlm/models/cache.py mlx_vlm/tests/test_kv_prealloc.py
git commit -m "feat(cache): PreallocQuantizedKVCache — uniform-quant pre-alloc floor"
```

---

### Task 3: `TurboQuantKVCache` pre-alloc arg

**Files:**
- Modify: `../mlx-vlm/mlx_vlm/turboquant.py:5170` (`__init__`), `:5216` (`from_cache`), `:5351` (`initial_alloc`)
- Test: `../mlx-vlm/mlx_vlm/tests/test_kv_prealloc.py`

**Interfaces:**
- Produces: `TurboQuantKVCache(bits, seed=…, max_kv_size=None, fused_prefill=None, kv_quant_mode=None, prealloc_tokens=None)`. First-fill `initial_alloc = max(new_end, prealloc_tokens or 0, max_kv_size or 0)`. `from_cache(..., prealloc_tokens=None)` forwards it. (Ctor arg is `prealloc_tokens`, matching the other cache classes; the caller passes the request-level `kv_prealloc_tokens` value into it.)

- [ ] **Step 1: Write the failing test**

Append to `test_kv_prealloc.py`:

```python
from mlx_vlm.turboquant import TurboQuantKVCache, _state_length


def test_turboquant_prealloc_floor_and_never_reallocs():
    c = TurboQuantKVCache(bits=4, prealloc_tokens=262144)
    c.update_and_fetch(*_fake(1000))
    assert _state_length(c.keys) == 262144
    for _ in range(400):
        c.update_and_fetch(*_fake(1))
    assert _state_length(c.keys) == 262144    # zero reallocs
    assert c.offset == 1400


def test_turboquant_none_is_backward_compatible():
    c = TurboQuantKVCache(bits=4, prealloc_tokens=None)
    c.update_and_fetch(*_fake(1000))
    assert _state_length(c.keys) == 1000      # grows from new_end (today's behavior)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_kv_prealloc.py -k turboquant -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'prealloc_tokens'`.

- [ ] **Step 3: Write minimal implementation**

In `turboquant.py`, `TurboQuantKVCache.__init__` (starts at `:5170`), add the parameter and store it. Add to the signature after `kv_quant_mode: Optional[str] = None,`:

```python
        prealloc_tokens: Optional[int] = None,
```

and in the body (near `self.max_kv_size = max_kv_size`):

```python
        self.prealloc_tokens = prealloc_tokens
```

At `:5351`, change:

```python
            initial_alloc = max(new_end, self.max_kv_size or 0)
```

to:

```python
            initial_alloc = max(
                new_end, self.prealloc_tokens or 0, self.max_kv_size or 0
            )
```

In `from_cache` (`:5216`), add `prealloc_tokens: Optional[int] = None,` to the signature and pass it into the constructor call `cls(bits=bits, seed=seed, max_kv_size=max_kv_size, prealloc_tokens=prealloc_tokens)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_kv_prealloc.py -k turboquant -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the existing turboquant suite (no regressions)**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_turboquant.py -q`
Expected: PASS (unchanged).

- [ ] **Step 6: Commit**

```bash
cd ../mlx-vlm && git add mlx_vlm/turboquant.py mlx_vlm/tests/test_kv_prealloc.py
git commit -m "feat(turboquant): kv_prealloc_tokens pre-alloc floor (distinct from max_kv_size)"
```

---

### Task 4: Batched twins pre-alloc

**Files:**
- Modify: `../mlx-vlm/mlx_vlm/turboquant.py:6490` (`BatchTurboQuantKVCache.__init__`), `:6546` (alloc)
- Modify: `../mlx-vlm/mlx_vlm/models/cache.py` (`BatchKVCache.__init__` + `_capacity_for` ~`:51`; `BatchQuantizedKVCache.__init__` `:193` + first-fill `init` `:225`)
- Test: `../mlx-vlm/mlx_vlm/tests/test_kv_prealloc.py`

**Interfaces:**
- Produces: each batched class accepts `prealloc_tokens: int = 0` (kw), pre-allocating its buffer on first fill to `max(new_end, prealloc_tokens)` (rounded to `step`/`cache_step`).

- [ ] **Step 1: Write the failing test**

Append to `test_kv_prealloc.py`:

```python
from mlx_vlm.turboquant import BatchTurboQuantKVCache
from mlx_vlm.models.cache import BatchKVCache, BatchQuantizedKVCache


def test_batch_turboquant_prealloc():
    c = BatchTurboQuantKVCache(left_padding=[0], bits=4, prealloc_tokens=262144)
    c.update_and_fetch(*_fake(1000))
    assert _state_length(c.keys) == 262144


def test_batch_kvcache_prealloc():
    c = BatchKVCache([0], prealloc_tokens=262144)
    c.update_and_fetch(*_fake(1000))
    assert c.keys.shape[2] == 262144


def test_batch_quantized_prealloc():
    c = BatchQuantizedKVCache([0], group_size=64, bits=4, prealloc_tokens=262144)
    c.update_and_fetch(*_fake(1000))
    assert c.keys[0].shape[2] == 262144
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_kv_prealloc.py -k batch -v`
Expected: FAIL — `TypeError: unexpected keyword argument 'prealloc_tokens'`.

- [ ] **Step 3: Implement `BatchTurboQuantKVCache`**

In `turboquant.py`, `BatchTurboQuantKVCache.__init__` (`:6490`): add `prealloc_tokens: int = 0,` to the signature and `self.prealloc_tokens = int(prealloc_tokens or 0)` in the body. At the first-fill alloc (`:6546`), change:

```python
            self.keys = _allocate_state_like(new_keys, new_end)
            self.values = _allocate_state_like(new_values, new_end)
```

to:

```python
            _cap = max(new_end, self.prealloc_tokens or 0)
            self.keys = _allocate_state_like(new_keys, _cap)
            self.values = _allocate_state_like(new_values, _cap)
```

- [ ] **Step 4: Implement `BatchKVCache`**

In `models/cache.py`, `BatchKVCache.__init__`: add `prealloc_tokens: int = 0` (keyword, after existing params) and `self.prealloc_tokens = int(prealloc_tokens or 0)`. In `_capacity_for` (`:51`), change:

```python
    def _capacity_for(self, needed: int) -> int:
        target = max(needed, self._target_size())
        return ((target + self.step - 1) // self.step) * self.step
```

to:

```python
    def _capacity_for(self, needed: int) -> int:
        target = max(needed, self._target_size(), self.prealloc_tokens or 0)
        return ((target + self.step - 1) // self.step) * self.step
```

- [ ] **Step 5: Implement `BatchQuantizedKVCache`**

In `models/cache.py`, `BatchQuantizedKVCache.__init__` (`:193`): add `prealloc_tokens: int = 0` and `self.prealloc_tokens = int(prealloc_tokens or 0)`. In `update_and_fetch`, at the first-fill branch, change the `new_steps` computation (`:225`, inside `if self.keys is None or …`):

```python
            new_steps = (self.step + num_steps - 1) // self.step * self.step
```

so that on the first allocation it honors the floor:

```python
            _target = num_steps if self.keys is not None else max(num_steps, prev + num_steps, self.prealloc_tokens or 0)
            new_steps = (self.step + _target - 1) // self.step * self.step
```

(On growth — `self.keys is not None` — `_target = num_steps` preserves the existing step-expand behavior.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_kv_prealloc.py -k batch -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
cd ../mlx-vlm && git add mlx_vlm/turboquant.py mlx_vlm/models/cache.py mlx_vlm/tests/test_kv_prealloc.py
git commit -m "feat(cache): prealloc floor for batched twins (Batch{KV,TurboQuant,Quantized}KVCache)"
```

---

### Task 5: `maybe_preallocate_kv_cache` + thread into `maybe_quantize_kv_cache`

**Files:**
- Modify: `../mlx-vlm/mlx_vlm/generate/common.py:262` (`maybe_quantize_kv_cache` signature + TQ construction at `:288`/`:292`), add new `maybe_preallocate_kv_cache`
- Modify: `../mlx-vlm/mlx_vlm/generate/__init__.py` (export `maybe_preallocate_kv_cache`)
- Test: `../mlx-vlm/mlx_vlm/tests/test_kv_prealloc.py`

**Interfaces:**
- Consumes: `PreallocKVCache`, `PreallocQuantizedKVCache` (Tasks 1–2); `TurboQuantKVCache(kv_prealloc_tokens=…)` (Task 3).
- Produces:
  - `maybe_quantize_kv_cache(..., kv_prealloc_tokens: Optional[int] = None)` — passes `prealloc_tokens=kv_prealloc_tokens` into every `TurboQuantKVCache(...)` it constructs.
  - `maybe_preallocate_kv_cache(prompt_cache, kv_prealloc_tokens)` — in-place converts plain `KVCache`→`PreallocKVCache` and `QuantizedKVCache`→`PreallocQuantizedKVCache`, **including non-empty caches** (copies content via `from_kvcache`/`from_quantized`), so it works when called mid-prefill after quantize. Leaves `TurboQuantKVCache`, existing `Prealloc*`, `RotatingKVCache`, `ChunkedKVCache`, `CacheList`, and linear-attn caches untouched (idempotent). No-op when `kv_prealloc_tokens` is falsy.

- [ ] **Step 1: Write the failing test**

Append to `test_kv_prealloc.py`:

```python
from mlx_lm.models import cache as lmcache
from mlx_vlm.generate.common import maybe_preallocate_kv_cache
from mlx_vlm.models.cache import PreallocKVCache, PreallocQuantizedKVCache


def test_maybe_preallocate_converts_empty_plain_and_quantized():
    pc = [lmcache.KVCache(), lmcache.QuantizedKVCache(group_size=64, bits=4)]
    maybe_preallocate_kv_cache(pc, 262144)
    assert isinstance(pc[0], PreallocKVCache) and pc[0].prealloc_tokens == 262144
    assert isinstance(pc[1], PreallocQuantizedKVCache) and pc[1].prealloc_tokens == 262144
    assert pc[1].group_size == 64 and pc[1].bits == 4


def test_maybe_preallocate_converts_nonempty_by_copy():
    pc = [lmcache.KVCache()]
    pc[0].update_and_fetch(*_fake(512))            # mid-prefill (non-empty)
    maybe_preallocate_kv_cache(pc, 262144)
    assert isinstance(pc[0], PreallocKVCache)
    assert pc[0].keys.shape[2] == 262144           # pre-allocated
    assert pc[0].offset == 512                       # content copied


def test_maybe_preallocate_zero_and_idempotent():
    pc = [lmcache.KVCache()]
    maybe_preallocate_kv_cache(pc, 0)
    assert type(pc[0]) is lmcache.KVCache           # untouched when floor is 0
    maybe_preallocate_kv_cache(pc, 262144)
    first = pc[0]
    maybe_preallocate_kv_cache(pc, 262144)          # second call is a no-op
    assert pc[0] is first
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_kv_prealloc.py -k preallocate -v`
Expected: FAIL — `ImportError: cannot import name 'maybe_preallocate_kv_cache'`.

- [ ] **Step 3: Implement**

In `common.py`, thread the floor through TQ construction. Change the `maybe_quantize_kv_cache` signature (`:262`) to add `kv_prealloc_tokens: Optional[int] = None,`. In the two `TurboQuantKVCache(...)` sites (`:288` and `:292`), add `prealloc_tokens=kv_prealloc_tokens` to each call (the `from_cache` at `:292` too).

Then add the new pass (import the Prealloc classes at top: `from ..models.cache import PreallocKVCache, PreallocQuantizedKVCache`):

```python
def maybe_preallocate_kv_cache(prompt_cache, kv_prealloc_tokens):
    """Convert leftover plain fp16 / uniform-quantized caches to their pre-allocating
    variants (including non-empty ones — copies content). Runs AFTER
    maybe_quantize_kv_cache so it never fp16-pre-allocs a to-be-quantized layer.
    Idempotent: a cache already a Prealloc*/TQ variant is left as-is (only its floor
    is refreshed)."""
    if not kv_prealloc_tokens:
        return
    floor = int(kv_prealloc_tokens)
    for i, entry in enumerate(prompt_cache):
        # Already a pre-alloc variant → just refresh the floor (idempotent).
        if isinstance(entry, (PreallocKVCache, PreallocQuantizedKVCache)):
            entry.prealloc_tokens = floor
        # QuantizedKVCache first (PreallocQuantizedKVCache subclasses it, handled above).
        elif isinstance(entry, cache.QuantizedKVCache):
            prompt_cache[i] = PreallocQuantizedKVCache.from_quantized(entry, floor)
        # Plain KVCache last (PreallocKVCache subclasses it, handled above).
        elif isinstance(entry, cache.KVCache):
            prompt_cache[i] = PreallocKVCache.from_kvcache(entry, floor)
        # TurboQuantKVCache, RotatingKVCache, ChunkedKVCache, linear-attn, CacheList: untouched.
```

The `isinstance` order matters: the `Prealloc*` check runs first (they subclass `QuantizedKVCache`/`KVCache`), then `QuantizedKVCache` before `KVCache` (the former is not a subclass of the latter, so order between them is by specificity of the copy path).

Export it in `generate/__init__.py`: add `maybe_preallocate_kv_cache` to the imports from `.common` and to `__all__`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_kv_prealloc.py -k preallocate -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
cd ../mlx-vlm && git add mlx_vlm/generate/common.py mlx_vlm/generate/__init__.py mlx_vlm/tests/test_kv_prealloc.py
git commit -m "feat(generate): maybe_preallocate_kv_cache + thread kv_prealloc_tokens through maybe_quantize"
```

---

### Task 6: Generate-path plumbing (`ar.py`)

**Files:**
- Modify: `../mlx-vlm/mlx_vlm/generate/ar.py:184` (`generate_step` signature), `:282-292` (quantize partial), `:335-337` (make_prompt_cache), add the preallocate call after quantize
- Test: `../mlx-vlm/mlx_vlm/tests/test_kv_prealloc.py`

**Interfaces:**
- Consumes: `maybe_quantize_kv_cache(kv_prealloc_tokens=…)`, `maybe_preallocate_kv_cache` (Task 5).
- Produces: `generate_step(..., kv_prealloc_tokens: Optional[int] = None)` forwards the floor to `maybe_quantize_kv_cache`, and runs `maybe_preallocate_kv_cache` at **two gated points** (per the conversion-timing invariant): (a) right after cache creation **when `kv_bits is None`** (fp16 models — pre-alloc empty caches before prefill); (b) after each `quantize_cache_fn` in the prefill loop (quantized models — copy-convert leftover fp16/`QuantizedKVCache` layers). It is idempotent, so (b) is a no-op once (a) has run. (`stream_generate` inherits the param via `**kwargs`.)

- [ ] **Step 1: Write the failing test (pipe spy)**

Append to `test_kv_prealloc.py`:

```python
import sys
from unittest.mock import patch
from mlx_vlm.generate import generate_step
from mlx_vlm.models import cache as kvc
from mlx_vlm.tests.test_kv_cache_quantization import MockModel


def test_generate_step_forwards_kv_prealloc_tokens():
    seen = {"quantize": [], "prealloc": []}

    def spy_quant(cache, **kw):
        seen["quantize"].append(kw.get("kv_prealloc_tokens", "ABSENT"))

    def spy_prealloc(cache, kv_prealloc_tokens):
        seen["prealloc"].append(kv_prealloc_tokens)

    def spy_make(model, *a, **kw):
        return [kvc.KVCache() for _ in range(2)]

    gen_mod = sys.modules["mlx_vlm.generate"]
    with patch("mlx_vlm.models.cache.make_prompt_cache", spy_make), \
         patch.object(gen_mod, "maybe_quantize_kv_cache", spy_quant), \
         patch.object(gen_mod, "maybe_preallocate_kv_cache", spy_prealloc):
        gen = generate_step(
            input_ids=mx.array([[1, 2, 3, 4, 5]]), model=MockModel(),
            pixel_values=mx.random.normal((1, 3, 336, 336)), mask=mx.ones((1, 5)),
            kv_bits=4, kv_group_size=64, quantized_kv_start=0, max_tokens=3,
            kv_prealloc_tokens=262144,
        )
        for _ in gen:
            pass
    assert seen["quantize"] and all(x == 262144 for x in seen["quantize"])
    assert seen["prealloc"] and all(x == 262144 for x in seen["prealloc"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_kv_prealloc.py -k forwards -v`
Expected: FAIL — `TypeError: generate_step() got an unexpected keyword argument 'kv_prealloc_tokens'`.

- [ ] **Step 3: Implement**

In `ar.py`, add to the `generate_step` signature (`:184`), after `quantized_kv_start: int = DEFAULT_QUANTIZED_KV_START,`:

```python
    kv_prealloc_tokens: Optional[int] = None,
```

In the `quantize_cache_fn` partial (`:282`), add `kv_prealloc_tokens=kv_prealloc_tokens,` to the `functools.partial(...)` kwargs alongside `max_kv_size=max_kv_size,`.

Add a module-level import near the `maybe_quantize_kv_cache` import (`:45`): `maybe_preallocate_kv_cache,`. Then define a bound helper next to `quantize_cache_fn`:

```python
    preallocate_cache_fn = functools.partial(
        _generate_module_override("maybe_preallocate_kv_cache", maybe_preallocate_kv_cache),
        kv_prealloc_tokens=kv_prealloc_tokens,
    )
```

**Call site (a) — fp16 models, at creation.** Right after the cache is built (`prompt_cache = cache.make_prompt_cache(model.language_model, max_kv_size=max_kv_size)`, `:335`), add:

```python
        if kv_bits is None:
            preallocate_cache_fn(prompt_cache)  # fp16 model: pre-alloc empty caches before prefill
```

(Gated on `kv_bits is None` so it never fp16-pre-allocs a to-be-quantized cache. This also covers the case where `prompt_cache` was passed in already-built.)

**Call site (b) — quantized models, in the chunked prefill loop.** Immediately after the `quantize_cache_fn(prompt_cache)` call in the chunked prefill loop (`:548`; only runs for prompts longer than `prefill_step_size`), add:

```python
                    preallocate_cache_fn(prompt_cache)
```

(Runs after quantization — OOM-safe. Copy-converts the leftover fp16 skip-layer and any `QuantizedKVCache` post-conversion; idempotent, so it settles after the first chunk and no-ops for fp16 models already handled by site (a).)

**Call site (c) — short/non-chunked prefill + decode, in `_step`.** `_step()` (the shared per-forward helper) handles non-chunked prefill (prompts ≤ `prefill_step_size`) AND every decode step, and calls `quantize_cache_fn(prompt_cache)` at `:409`. Immediately after THAT call, add:

```python
            preallocate_cache_fn(prompt_cache)
```

(REQUIRED — without it, quantized models on short prompts never pre-alloc: they skip the chunked loop (b) entirely and quantize only through `_step`. Idempotent, so on the decode path after conversion it is a no-op. This is the site the chunked-only plan originally missed.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_kv_prealloc.py -k forwards -v`
Expected: PASS.

- [ ] **Step 5: Run the generate + kv-quant suites (no regressions)**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_generate.py mlx_vlm/tests/test_kv_cache_quantization.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd ../mlx-vlm && git add mlx_vlm/generate/ar.py mlx_vlm/tests/test_kv_prealloc.py
git commit -m "feat(generate): thread kv_prealloc_tokens into generate_step (quantize then preallocate)"
```

---

### Task 7: Server plumbing (`generation.py`) + APC pass-through

**Files:**
- Modify: `../mlx-vlm/mlx_vlm/server/generation.py` (add `get_kv_prealloc_tokens()` near `get_quantized_kv_start` `:497`; add to inline gen_kwargs `:1335-1339`; thread into the batched `_make_cache` call at `:2138`)
- Modify: `../mlx-vlm/mlx_vlm/generate/ar.py:814` (`_make_cache` gains `kv_prealloc_tokens=0` → forwards to `_make_quant_cache` / `BatchKVCache`)
- Modify: `../mlx-vlm/mlx_vlm/apc.py` (thread `kv_prealloc_tokens` into `min_capacity_tokens` where APC builds its caches — sites `:2959`, `:3016`)
- Test: `../mlx-vlm/mlx_vlm/tests/test_kv_prealloc.py`

**Interfaces:**
- Consumes: `get_kv_prealloc_tokens()` reads `KV_PREALLOC_TOKENS` env (default 0 → None).
- Produces: inline `gen_kwargs["kv_prealloc_tokens"]`; `_make_cache(..., kv_prealloc_tokens=0)` passes the floor into batched cache constructors.

- [ ] **Step 1: Write the failing test**

Append to `test_kv_prealloc.py`:

```python
import os
from mlx_vlm.server import generation as G


def test_get_kv_prealloc_tokens_env(monkeypatch):
    monkeypatch.setenv("KV_PREALLOC_TOKENS", "262144")
    assert G.get_kv_prealloc_tokens() == 262144
    monkeypatch.delenv("KV_PREALLOC_TOKENS", raising=False)
    assert G.get_kv_prealloc_tokens() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_kv_prealloc.py -k prealloc_tokens_env -v`
Expected: FAIL — `AttributeError: module ... has no attribute 'get_kv_prealloc_tokens'`.

- [ ] **Step 3: Implement the getter + inline threading**

In `generation.py`, after `get_quantized_kv_start` (`:497`), add:

```python
def get_kv_prealloc_tokens():
    n = int(os.environ.get("KV_PREALLOC_TOKENS", 0))
    return n or None
```

In `_process_cached_request`, inside the `if self.kv_bits is not None:` block (`:1335`), add a line that ALWAYS threads the floor (independent of kv_bits, since fp16/Ornith has `kv_bits` None). Add just after the `gen_kwargs.setdefault("prefill_step_size", …)` line (`:1334`):

```python
        _prealloc = get_kv_prealloc_tokens()
        if _prealloc is not None:
            gen_kwargs["kv_prealloc_tokens"] = _prealloc
```

- [ ] **Step 4: Implement `_make_cache` + batched threading**

In `ar.py`, `_make_cache` (`:814`): add `kv_prealloc_tokens: int = 0,` to the signature. In `_make_quant_cache`, pass it: `BatchTurboQuantKVCache(lp, bits=kv_bits, prealloc_tokens=kv_prealloc_tokens)` and `cache.BatchQuantizedKVCache(lp, group_size=kv_group_size, bits=int(kv_bits), prealloc_tokens=kv_prealloc_tokens)`. In `to_batch_cache`, the fp16 branches that build `cache.BatchKVCache(left_padding)` become `cache.BatchKVCache(left_padding, prealloc_tokens=kv_prealloc_tokens)`.

In `generation.py`, the batched `make_speculative_prompt_cache(..., make_cache=_make_cache)` call (`:2133`) wraps `_make_cache`; thread the floor via `functools.partial`:

```python
                prompt_cache = make_speculative_prompt_cache(
                    lm, draft_kind=draft_kind, batch_size=B, left_padding=left_padding,
                    make_cache=functools.partial(
                        _make_cache, kv_prealloc_tokens=(get_kv_prealloc_tokens() or 0)
                    ),
                )
```

(`functools` is already imported in `generation.py`; confirm and add if not.)

- [ ] **Step 5: Implement APC pass-through**

In `apc.py`, at the two cache-build sites that set `min_capacity_tokens=len(token_tuple) + 1` (`:2959`, `:3016`), take the floor into account so APC-built caches also pre-alloc:

```python
                min_capacity_tokens=max(len(token_tuple) + 1, _kv_prealloc_floor()),
```

Add a small module helper at the top of `apc.py`:

```python
def _kv_prealloc_floor() -> int:
    import os
    return int(os.environ.get("KV_PREALLOC_TOKENS", 0) or 0)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_kv_prealloc.py -k prealloc_tokens_env -v`
Expected: PASS. Then the APC + server suites:
Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_apc.py -q` (and any `test_session_cache.py`)
Expected: PASS (no regressions).

- [ ] **Step 7: Commit**

```bash
cd ../mlx-vlm && git add mlx_vlm/server/generation.py mlx_vlm/generate/ar.py mlx_vlm/apc.py mlx_vlm/tests/test_kv_prealloc.py
git commit -m "feat(server): get_kv_prealloc_tokens + thread into inline/batched/APC cache builds"
```

---

### Task 8: mlx-vlm CLI arg + env + startup validation

**Files:**
- Modify: `../mlx-vlm/mlx_vlm/server/cli.py:261` (argparse, near `--max-kv-size`), `:502-504` (env export + validation)
- Test: `../mlx-vlm/mlx_vlm/tests/test_kv_prealloc.py`

**Interfaces:**
- Produces: `--kv-prealloc-tokens INT` (default `None`) → sets `KV_PREALLOC_TOKENS` env. Startup **raises** `SystemExit`/`ValueError` if `kv_prealloc_tokens > max_kv_size`.

- [ ] **Step 1: Write the failing test**

Append to `test_kv_prealloc.py`:

```python
import pytest
from mlx_vlm.server.cli import validate_kv_prealloc_tokens


def test_validate_kv_prealloc_rejects_over_cap():
    with pytest.raises(ValueError, match="kv_prealloc_tokens"):
        validate_kv_prealloc_tokens(300000, max_kv_size=262144)


def test_validate_kv_prealloc_allows_equal_and_none():
    validate_kv_prealloc_tokens(262144, max_kv_size=262144)  # equal OK
    validate_kv_prealloc_tokens(None, max_kv_size=262144)    # unset OK
    validate_kv_prealloc_tokens(1000, max_kv_size=None)      # no cap configured OK
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_kv_prealloc.py -k validate_kv_prealloc -v`
Expected: FAIL — `ImportError: cannot import name 'validate_kv_prealloc_tokens'`.

- [ ] **Step 3: Implement**

In `cli.py`, add the argparse block after the `--max-kv-size` one (`:265`):

```python
    parser.add_argument(
        "--kv-prealloc-tokens",
        type=int,
        default=None,
        help="Pre-allocate every KV cache to this fixed token floor on first fill "
             "(no mid-generation realloc). Must be <= --max-kv-size.",
    )
```

Add the validator (module-level, near the other helpers):

```python
def validate_kv_prealloc_tokens(kv_prealloc_tokens, max_kv_size):
    if kv_prealloc_tokens is None or max_kv_size is None:
        return
    if int(kv_prealloc_tokens) > int(max_kv_size):
        raise ValueError(
            f"kv_prealloc_tokens ({kv_prealloc_tokens}) must be <= max_kv_size "
            f"({max_kv_size}); a floor above the cap can never be honored."
        )
```

In the env-export section (near `:502`), add:

```python
    validate_kv_prealloc_tokens(args.kv_prealloc_tokens, args.max_kv_size)
    if args.kv_prealloc_tokens is not None:
        os.environ["KV_PREALLOC_TOKENS"] = str(args.kv_prealloc_tokens)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_kv_prealloc.py -k validate_kv_prealloc -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
cd ../mlx-vlm && git add mlx_vlm/server/cli.py mlx_vlm/tests/test_kv_prealloc.py
git commit -m "feat(cli): --kv-prealloc-tokens arg + KV_PREALLOC_TOKENS env + fail-loud validation"
```

---

### Task 9: mlx-serve — registry field + cmdline + parse validation

**Files:**
- Modify: `../mlx-serve/src/mlx_serve/config.py:69` (`ModelConfig` field), `:135` (`_load` parse + validation)
- Modify: `../mlx-serve/src/mlx_serve/process_manager.py:64` (`_build_command`, emit `--kv-prealloc-tokens` for vision workers after the `--max-kv-size` block `:87`)
- Test: `../mlx-serve/tests/test_process_manager.py` (cmd emit), `../mlx-serve/tests/test_config.py` (field + validation)

**Interfaces:**
- Consumes: mlx-vlm `--kv-prealloc-tokens` (Task 8).
- Produces: `ModelConfig.kv_prealloc_tokens: int = 0`; `_build_command` appends `["--kv-prealloc-tokens", str(...)]` when `> 0` and `type == "vision"`; `_load` raises `ValueError` when `kv_prealloc_tokens > max_kv_cache_size`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_process_manager.py` (import `_build_command` and `ModelConfig` the way the file already does):

```python
def test_kv_prealloc_tokens_emitted_for_vision():
    cfg = ModelConfig(name="m", type="vision", hf_path="x",
                      max_kv_cache_size=262144, kv_prealloc_tokens=262144)
    cmd = _build_command(cfg)
    assert "--kv-prealloc-tokens" in cmd
    assert cmd[cmd.index("--kv-prealloc-tokens") + 1] == "262144"
```

In `tests/test_config.py` (the validation lives in `_load`, so drive it through a temp registry the way the file's other `_load` tests do — or call the extracted validator if the file exposes one):

```python
def test_kv_prealloc_over_cap_fails_loud(tmp_path):
    import pytest, yaml
    from mlx_serve import config as cfgmod
    reg = tmp_path / "reg.yaml"
    reg.write_text(yaml.safe_dump({"models": [{
        "name": "m", "type": "vision", "hf_path": "x",
        "max_kv_cache_size": 262144, "kv_prealloc_tokens": 300000,
    }]}))
    with pytest.raises(ValueError, match="kv_prealloc_tokens"):
        cfgmod._load_path(str(reg))   # use the file's real load-from-path helper
```

(Match the test file's existing loader-invocation pattern; if `_load` reads a module-level path, follow how `test_config.py` already points it at a fixture.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ../mlx-serve && .venv/bin/python -m pytest tests/test_process_manager.py tests/test_config.py -k kv_prealloc -v`
Expected: FAIL — `TypeError: unexpected keyword argument 'kv_prealloc_tokens'`.

- [ ] **Step 3: Implement the dataclass field + parse + validation**

In `config.py`, add to `ModelConfig` after `quantized_kv_start` (`:69`):

```python
    kv_prealloc_tokens: int = 0  # pre-alloc every KV cache to this token floor; must be <= max_kv_cache_size
```

In `_load`, in the `ModelConfig(...)` construction (after `quantized_kv_start=entry.get("quantized_kv_start", 0),` `:135`):

```python
            kv_prealloc_tokens=entry.get("kv_prealloc_tokens", 0),
```

Immediately after building each `ModelConfig` (inside the `for entry` loop), add the fail-loud check:

```python
        if (
            models[entry["name"]].kv_prealloc_tokens
            and models[entry["name"]].max_kv_cache_size
            and models[entry["name"]].kv_prealloc_tokens > models[entry["name"]].max_kv_cache_size
        ):
            raise ValueError(
                f"Model '{entry['name']}': kv_prealloc_tokens "
                f"({models[entry['name']].kv_prealloc_tokens}) exceeds max_kv_cache_size "
                f"({models[entry['name']].max_kv_cache_size})."
            )
```

- [ ] **Step 4: Implement the cmdline emit**

In `process_manager.py`, after the `--max-kv-size` / `--max-kv-cache-size` block (`:87`), add:

```python
    if model_cfg.kv_prealloc_tokens > 0 and model_cfg.type == "vision":
        cmd += ["--kv-prealloc-tokens", str(model_cfg.kv_prealloc_tokens)]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ../mlx-serve && .venv/bin/python -m pytest tests/test_process_manager.py tests/test_config.py -k kv_prealloc -v` then `.venv/bin/python -m pytest tests/ -q` for regressions.
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd ../mlx-serve && git add src/mlx_serve/config.py src/mlx_serve/process_manager.py tests/
git commit -m "feat(config): kv_prealloc_tokens registry field + --kv-prealloc-tokens cmdline + fail-loud validation"
```

---

### Task 10: `main_models.yaml` values + AGENTS.md note + configgen drift check

**Files:**
- Modify: `main_models.yaml` (stack repo) — 4 router models
- Modify: `AGENTS.md` (stack repo)

**Interfaces:**
- Consumes: mlx-serve `kv_prealloc_tokens` parse (Task 9).

- [ ] **Step 1: Add the field to each router model**

In `main_models.yaml`, add `kv_prealloc_tokens: <value>` next to each model's `max_kv_cache_size` (same value):

| model | `max_kv_cache_size` | `kv_prealloc_tokens` |
|---|---|---|
| gemma-4-31B-it-qat-6bit | 196608 | 196608 |
| gemma-4-26B-A4B-it-OptiQ-4bit | 262144 | 262144 |
| Ornith-1.0-35B-mlx-uniform-4bit | 262144 | 262144 |
| Qwen3.6-27B-Opus-Distill-OptiQ-4bit | 262144 | 262144 |

Example (Ornith, after `max_kv_cache_size: 262144`):

```yaml
    max_kv_cache_size: 262144
    kv_prealloc_tokens: 262144     # pre-alloc full cap → never reallocs (KV pre-alloc, 2026-07-09)
    kv_bits: 0
```

- [ ] **Step 2: Verify configgen drift guard stays green**

Run: `python -m configgen check` (from the stack repo root; use the repo's actual invocation — see `runserver.sh`).
Expected: PASS with **no drift** — `kv_prealloc_tokens` is structural, so no client config changes.

- [ ] **Step 3: Verify mlx-serve loads the registry without error**

Run: `cd ../mlx-serve && MLX_SERVE_CONFIG=<abs path to main_models.yaml> .venv/bin/python -c "from mlx_serve.config import _load; print('loaded', len(_load()[0]), 'models')"`.
Expected: prints the model count; no `ValueError` (all `kv_prealloc_tokens == max_kv_cache_size`, so validation passes).

- [ ] **Step 4: Update AGENTS.md**

Add a line under the KV/config section noting `kv_prealloc_tokens` is a **structural** registry field (mlx-serve-only; `--kv-prealloc-tokens`), NOT a client-facing carrier — no configgen/emitter involvement — set to `max_kv_cache_size` per model so the stack never reallocs.

- [ ] **Step 5: Commit**

```bash
git add main_models.yaml AGENTS.md
git commit -m "feat(config): set kv_prealloc_tokens = max_kv_cache_size on all 4 router models"
```

---

### Task 11: Live acceptance — `mx.get_peak_memory` A/B on M5

**Files:**
- Create: `benchmark/spikes/kv_prealloc_ab.md` (record the run: box, config, on/off, peaks)

**Interfaces:**
- Consumes: the deployed forks (bump stack submodules to the Task 1–9 commits; sync M5 per AGENTS.md).

- [ ] **Step 1: Bump submodules + sync M5**

Bump `src/mlx-vlm` and `src/mlx-serve` to the feature commits; commit the stack pointer bump; sync M5 (`git fetch origin main && git merge --ff-only`; `git submodule update --force`), preserving M5's dirty local registry per AGENTS.md.

- [ ] **Step 2: OFF baseline (same box, same session)**

On M5, start the router with `kv_prealloc_tokens` UNSET for the distill (temporarily remove the field or export `KV_PREALLOC_TOKENS=0`). Fire a **small** (~1K) prompt and a **256K** prompt; record `peak_memory` (on the final `StreamingToken`) and count `Reallocating old:%d new:%d` lines in `logs/main_model.log`.
Expected: reallocs **> 0**; peak includes a growth transient.

- [ ] **Step 3: ON (right the deployed config)**

Restart with `kv_prealloc_tokens: 262144`. Fire the same two prompts; record `peak_memory` + realloc count.
Expected: **0** `Reallocating` lines; small-prompt and 256K peaks equal to the steady footprint with **no transient above it**; still **≤46 GB**.

- [ ] **Step 4: Repeat for Ornith (fp16 path)**

Same OFF/ON A/B for `Ornith-1.0-35B-mlx-uniform-4bit`. Expected: 0 reallocs ON; ≤46 GB (Ornith steady ~32.4 GB @256K).

- [ ] **Step 5: Record + commit the evidence**

Write box + config + on/off + peaks + realloc counts to `benchmark/spikes/kv_prealloc_ab.md` and to `docs/campaign-results.md`.

```bash
git add benchmark/spikes/kv_prealloc_ab.md docs/campaign-results.md
git commit -m "docs(bench): KV pre-alloc on/off mx.get_peak_memory A/B (M5) — 0 reallocs, no transient"
```

---

### Task 12: APC per-turn resize (completeness — off under `=cap`)

**Files:**
- Modify: `../mlx-vlm/mlx_vlm/apc.py:105` (`_pad_kv_for_capacity` — already pads; add adaptive per-turn target selection at the turn-boundary call sites)
- Test: `../mlx-vlm/mlx_vlm/tests/test_kv_prealloc.py`

**Interfaces:**
- Produces: an opt-in adaptive mode where a reused cache's per-turn `min_capacity_tokens = min(content + effective_max_tokens, cap)` — a controlled between-turn resize, never mid-generation. No-op when the fixed floor already sits at `cap`.

- [ ] **Step 1: Write the failing test**

Append to `test_kv_prealloc.py`:

```python
from mlx_vlm.apc import _resolve_turn_capacity


def test_turn_capacity_adaptive_min():
    # content 5000 + output 102400, cap 262144 -> 107400 (right-sized between turns)
    assert _resolve_turn_capacity(content=5000, effective_max_tokens=102400,
                                  cap=262144, fixed_floor=0) == 107400


def test_turn_capacity_fixed_floor_wins():
    # fixed floor at cap -> stays at cap (no per-turn shrink)
    assert _resolve_turn_capacity(content=5000, effective_max_tokens=102400,
                                  cap=262144, fixed_floor=262144) == 262144
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_kv_prealloc.py -k turn_capacity -v`
Expected: FAIL — `ImportError: cannot import name '_resolve_turn_capacity'`.

- [ ] **Step 3: Implement**

In `apc.py`:

```python
def _resolve_turn_capacity(content, effective_max_tokens, cap, fixed_floor):
    """Per-turn pre-alloc target for a reused (APC) cache. The fixed floor (if set)
    always wins; otherwise size to this turn's high-water, capped."""
    adaptive = min(int(content) + int(effective_max_tokens), int(cap))
    return max(adaptive, int(fixed_floor or 0))
```

Wire it at the turn-boundary cache-capacity sites (the `min_capacity_tokens=` calls touched in Task 7) so a reused cache resizes to `_resolve_turn_capacity(...)` when `effective_max_tokens` is known for the turn. Under the deployed `fixed_floor == cap`, this returns `cap` (no-op).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ../mlx-vlm && PYTHONPATH=. .venv/bin/python -m pytest mlx_vlm/tests/test_kv_prealloc.py -k turn_capacity -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
cd ../mlx-vlm && git add mlx_vlm/apc.py mlx_vlm/tests/test_kv_prealloc.py
git commit -m "feat(apc): _resolve_turn_capacity — adaptive per-turn pre-alloc (no-op under fixed cap)"
```

---

## Deployment (after all tasks)

- Push the fork feature branches (only when asked), open PRs to each fork's `main`, merge.
- Bump `src/mlx-vlm` and `src/mlx-serve` submodule pointers in the stack; commit; sync both boxes (`git submodule update --force`); restart routers.
- Re-run `configgen check` on both boxes (drift guard) and the live A/B (Task 11) to confirm the deployed config.
