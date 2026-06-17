# Plan: Enable APC block cache + disk tier (cross-request / cross-restart prefix reuse)

**Status:** Sketch (2026-06-16). Not started. Architecture + constraints verified against the fork.

**Goal:** Turn on the *second* tier of prompt caching — `apc.py`'s hash-based, block-level KV
reuse **across different requests/sessions**, plus the SSD disk tier that survives a process
restart — and validate it with an A/B. This is additive on top of the per-session cache that
already runs (Tier 1). The payoff for this workload: paste the same repo context / system
prompt into two *separate* chats and the second skips re-prefilling the shared blocks; and
after a model swap or server restart, the warm prefix restores from disk instead of
re-prefilling ~200K tokens cold.

---

## 0. The decisive constraint (read this first)

**APC is mutually exclusive with KV quantization.** `generate/ar.py:2234-2239`: if `kv_bits`
is set, APC is disabled (`apc_manager = None`) — quantized blocks can't be dequantized
generically for reuse. **Every model in `main_models.yaml` runs `kv_bits: 3` or `4`.** So APC
**cannot** layer onto the existing 256K-quantized main models as they are.

This is not a blocker — it's a *selector*. The `kv_bits` gate means: enable APC process-wide,
and quantized models silently ignore it while a dedicated **fp16-KV** model picks it up. The
design below uses that.

Second constraint: **APC only caches text blocks.** `ar.py:2361-2364, 2409-2410` discard any
prefix containing image/audio tokens. So APC helps text/code prefixes, not vision prefixes —
fine for the coding use case, irrelevant for the `:8092` vision task model.

---

## 1. Verified current state

- **Layered, not alternative** (`ar.py:2325-2420`, `PromptProcessingBatch._apc_pick_for`):
  APC sits *underneath* the Tier-1 session prefill. Lookup hierarchy per request: block-level
  prefix (`lookup_prefix`, `:2358`) → exact whole-prefix (`lookup_exact_cache`, `:2338/2368`)
  → disk (`lookup_prefix_disk_cache`, `:2376`), best match wins. Tier 1 (session continuation)
  stays on and is the fallback. **Enabling APC adds cross-request/cross-restart reuse; it does
  not replace the session cache.**
- **Consulted in the batched server path** (`_apc_pick_for` lives in the batch builder,
  consulted at `ar.py:2438`). The stack's server runs continuous batching, so normal requests
  flow through it — but this must be *verified* to engage for our request shape (see tests).
  The library single-stream `stream_generate` path uses only Tier 1.
- **Gating:** env-only, no CLI flag. `apc.py:3729-3773` `from_env()` checks `APC_ENABLED ∈
  {1,true,True,yes}`; wired at model load in `server/app.py:517`
  (`runtime.apc_manager = _apc.from_env(model_namespace=model_path)`). Default **OFF**.
- **Telemetry:** `apc_enabled` bool at `server/generation.py:601`; full `stats_snapshot()`
  (`apc.py:3304-3323`) exposes `hits/misses/matched_tokens/served_tokens/disk_hits/
  disk_writes/exact_hits/token_hit_rate/disk_bytes/...` via `app.py:90-94`.
- **Disk tier:** `DiskBlockStore` (`apc.py:755-903`); sharded `.safetensors` under
  `<APC_DISK_PATH>/<namespace>/`; index rebuilt by scanning shard headers on startup
  (`:868`) → survives restart. LRU evict at shard granularity to 90% watermark.
- **runserver.sh sets none of this** → APC is currently dormant. (Tier-1 session cache IS on:
  `--cache-session-max` defaults to 8.)

---

## 2. The hash-stability gotcha (or the disk tier silently never hits)

The default block hash is Python's `hash()` ("fast"), which is **process-local** (randomized
per process). After a restart, identical tokens hash differently → disk-restored blocks never
match. **For the disk tier to actually hit across restarts you must set `APC_HASH=sha256`**
(`apc.py:67`, ~100–200 ns/tok overhead). Without it, in-process reuse works but cross-restart
restore is dead weight. This single env var is the difference between the disk tier working
and not.

---

## 3. Design

### 3.1 Use the `kv_bits` gate as the per-model selector

Set APC env **process-wide** on mlx-serve (so every subprocess inherits it). Quantized models
auto-skip via the `kv_bits` gate; only an fp16-KV model engages APC. No per-model env plumbing
needed.

### 3.2 Add a dedicated fp16-KV coding model

APC's value is cross-session reuse of a large shared text prefix (repo context). That regime
wants **moderate context where fp16 KV fits 64 GB** — not 256K (fp16 KV at 256K is exactly
what you quantize to avoid). New `main_models.yaml` entry, no `kv_bits`:

```yaml
  - name: <coding-model>-apc-fp16kv
    type: vision                 # served via mlx-vlm; APC caches the text prefix
    on_demand: true
    hf_path: <a standard full-attention model>
    max_kv_cache_size: 65536     # ~64K: fp16 KV must fit alongside weights in 64 GB
    # NO kv_bits / kv_quant_scheme  -> APC eligible
    prefill_step_size: 512
    enable_thinking: true
```

Model choice caveat: APC reuses K/V *blocks*, cleanest on **standard full-attention**. Sliding-
window (Gemma MoE) and GatedDeltaNet (Qwen) layers don't block-cache their non-full state, so
the reuse benefit concentrates on full-attention layers. Start the A/B with a standard-
attention dense model to get a clean signal, then decide if SWA/hybrid is worth it.

### 3.3 Env to set (in `runserver.sh`, before launching mlx-serve)

```bash
export APC_ENABLED=1
export APC_HASH=sha256                 # REQUIRED for cross-restart disk hits (see §2)
export APC_DISK_PATH=/Volumes/fast-ssd/apc-cache   # fast local SSD
export APC_DISK_MAX_GB=40              # cap the cold tier
export APC_DISK_MIN_FREE_RAM_GB=6      # memory backstop (pairs with your set_cache_limit work)
export APC_MAX_POOL_TENSORS=300000     # cap in-RAM block pool on 64 GB
# defaults are fine: APC_BLOCK_SIZE=16, APC_DISK_READ_MODE=direct, APC_DISK_SHARD_MAX_BLOCKS=256
```

Tier 1 (session cache) stays exactly as-is — APC layers under it.

---

## 4. Design decisions (recommendations)

1. **Enable process-wide, select via `kv_bits` gate** (vs patching mlx-serve to set per-model
   env). Simpler, and the gate already does the selection for free.
2. **fp16-KV model at ~64K, not 256K.** APC needs unquantized KV; 64K is the sweet spot where
   fp16 KV fits 64 GB and a reused repo prefix is still large enough to matter. 256K stays on
   the quantized main models *without* APC (Tier-1 session cache only).
3. **`APC_HASH=sha256` whenever the disk tier is on.** Non-optional for restart persistence.
4. **Standard full-attention model for the first A/B.** Clean block-reuse signal before
   spending effort on SWA/GDN partial benefit.
5. **Keep peak-memory discipline.** fp16 KV + block pool + disk restore buffers all draw RAM;
   set the caps above and re-use the `mx.set_cache_limit` finding from the buffer-pool work.

---

## 5. Implementation phases

- **Phase 0 — model entry:** add the fp16-KV coding model to `main_models.yaml`; confirm it
  loads and that `apc_enabled: true` appears in its metrics (proves the gate let it through).
- **Phase 1 — env:** add the §3.3 block to `runserver.sh`; create the SSD cache dir.
- **Phase 2 — verify engagement:** confirm APC actually hits for the server request flow
  (integration test below), not just in unit tests.
- **Phase 3 — A/B + memory validation:** measure prefill/TTFT/peak-mem, APC on vs off.

---

## 6. Testing strategy (mirror `tests/test_apc.py`)

**Unit — in-memory (mirror `test_apc.py:109-199`):**
- store → lookup hit, partial-block-ignored (`:109-133`).
- refcount protects held blocks from LRU eviction (`:152-174`).
- `extra_hash` isolates different image/tenant prefixes (`:177-198`).

**Unit — disk survives restart (new, template from the cache map):**
```python
def test_apc_disk_tier_survives_restart(tmp_path, monkeypatch):
    monkeypatch.setenv("APC_ENABLED", "1")
    monkeypatch.setenv("APC_HASH", "sha256")          # <-- without this, the assert below fails
    monkeypatch.setenv("APC_DISK_PATH", str(tmp_path))
    m1 = APCManager.from_env(model_namespace="test-model")
    toks = list(range(48))                            # 3 full 16-tok blocks
    k, v = _make_fake_kv(seq_len=len(toks))
    m1.release(m1.store_kv_blocks(toks, k, v))
    assert m1.stats_snapshot()["disk_writes"] > 0
    m1.close()
    m2 = APCManager.from_env(model_namespace="test-model")   # simulated restart
    matched, matched_tokens = m2.lookup_prefix_disk_cache(toks)
    assert matched_tokens == 48
    m2.release(matched); m2.close()
```
- Add the **negative control**: same test with default (`fast`) hash asserts the cross-restart
  lookup *misses* — documents §2 so nobody "fixes" it by accident.

**Integration — APC engages on the server (the one that matters):**
- Bring up the fp16-KV model. Send the same large text prefix (≥ a few blocks) from **two
  different `chat_id`s**. Assert the 2nd request's `stats_snapshot()` shows `hits > 0` /
  `matched_tokens > 0` and lower derived prefill time / TTFT than the 1st. This proves
  cross-session reuse and that the batched server path consults APC (the open question in §1).
- Restart the server, send a 3rd identical request, assert `disk_hits > 0` and fast TTFT
  (cross-restart restore).

**A/B + memory (via `eval_harness.py` / `benchmark/`):**
- Workload: a shared 32–48K repo-context prefix + varied short suffixes, issued under several
  distinct `chat_id`s (simulating separate chats reusing the same context).
- Metrics: derived prefill tok/s + TTFT (cold 1st vs warm later), and `timings.peak_memory`.
- Pass: warm requests show materially lower prefill time at equal output; peak memory stays
  within the 64 GB budget with the §3.3 caps.

**Correctness note (do NOT mis-assert):** APC is numerically *exact* (byte-identical KV;
`apc.py:22-38`), but cold-vs-warm runs of the same prompt can differ slightly in logits due to
flash-attention **batch non-invariance** — long-Q cold prefill vs short-Q warm suffix use
different tile shapes. So **assert warm-to-warm determinism** (identical repeated warm requests
→ identical text), not cold == warm. Bit-equal cold==warm would need batch-invariant kernels,
which is out of scope.

---

## 7. Risks / gotchas

- **`kv_bits` mutual exclusion (§0)** — the central constraint; APC ⇒ fp16 KV ⇒ moderate
  context. Don't expect APC on the 256K quantized models.
- **Hash stability (§2)** — disk tier silently never hits without `APC_HASH=sha256`.
- **Text-only** — vision prefixes are discarded; no benefit for image-heavy turns.
- **Memory** — fp16 KV + RAM block pool; cap with `APC_MAX_POOL_TENSORS` /
  `APC_DISK_MIN_FREE_RAM_GB`; revisit `mx.set_cache_limit`.
- **SWA / GatedDeltaNet** — partial block-reuse benefit only on full-attention layers; start
  with a standard-attention model.
- **Engagement uncertainty** — confirm APC is consulted for the actual server request flow
  (the integration test is the proof, not the unit tests).

---

## 8. Acceptance criteria

1. `apc_enabled: true` in metrics for the fp16-KV model; `false` (auto-skip) for quantized
   models — proves the gate selector works.
2. Cross-session integration test: 2nd request (different `chat_id`) shows APC hits + lower
   prefill time.
3. Cross-restart: disk hits + fast TTFT after a server restart (with `sha256`).
4. Warm-to-warm determinism holds; peak memory within budget.
5. New unit tests pass (incl. the disk-restart + negative-control hash test); existing
   `test_apc.py` unaffected.
