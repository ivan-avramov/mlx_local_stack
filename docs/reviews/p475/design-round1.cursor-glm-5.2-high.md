I have sufficient evidence. Here are my findings.

---

## Findings

### 1. BLOCKER — The TQ4s arm does not measure what the spec claims, and is redundant or misleading at every rung

**Location:** `p475-kv-matrix.md` Arms table, TQ4s row (`kv_bits: 4, kv_quant_scheme: turboquant, quantized_kv_start: 131072`), described as "native16 up to 131,072 tokens, quantized beyond."

**Problem.** The spec describes a *within-context* hybrid (the first 131,072 tokens of a long context stay native16, the rest quantized). The serving code does not implement that. In `mlx_vlm/generate/common.py` (TurboQuant branch, `quantize_entry`), `quantize_cache_fn` runs after **every prefill chunk** (`ar.py:745`), and the decision is keyed on the cache's **current `offset`**, not on per-token position:

- `current_offset == 0` → replace with `TurboQuantKVCache` (quantize on the fly);
- `current_offset < quantized_kv_start` → `return entry` (keep native);
- else → `TurboQuantKVCache.from_cache(entry)` → retroactively quantize the **entire** existing native cache, including the tokens below the start.

So for a fresh single-request prompt (which is what `bench.run_capacity` sends — no session reuse, distinct prompts per rung, no `MLX_BENCH_SESSION_PREFIX`):
- rung 8192: offset stays `< 131072` throughout → cache stays **fully native** → identical to N16.
- rung 131072: final offset `== 131072` → `131072 < 131072` is False → `from_cache` quantizes all 131,072 tokens → identical to TQ4.
- rung 260096: once offset crosses 131,072, `from_cache` quantizes the first 131,072 retroactively and the rest on the fly → final state identical to TQ4; the only difference is a transient native→quantized conversion peak.

The `quantized_kv_start` threshold only changes behavior *between contexts* (short contexts stay native, long contexts go fully quantized), not *within* a context. The within-context hybrid the operator is being offered does not exist on this code path.

**Failure scenario.** The operator reads MATRIX.md, sees TQ4s sitting between N16 and TQ4 on memory at rung 260096 (a conversion-spike artifact, not a steady-state property), and adopts it expecting "recent tokens stay native16 for quality." In real 256K agentic sessions the format behaves exactly like TQ4 — no quality benefit — or, under session reuse, behaves in a way this measurement never exercised. The arm consumes ~2 of the 16 legs and ~1.7 h for a number that is either redundant (N16 at 8192, TQ4 at 131072/260096) or an artifact.

**Change.** Drop TQ4s, or replace it with a format the server actually supports as a within-context hybrid (e.g., the `HybridQuantKVCache` path, which requires a non-homogeneous split-bit policy, not `turboquant`+integer bits). If kept, the spec must state that `quantized_kv_start` only takes effect under session-cache reuse and re-design the leg to exercise that (paired same-session requests), or explicitly relabel it as a between-context threshold.

---

### 2. MAJOR — The engagement check is the config-echo log line, not the per-layer manifest that was the actual P405 fix

**Location:** `p475-kv-matrix.md` Measurement → Engagement: "the worker log's `KV cache resolved` line reports the arm's `kv_bits` / scheme / start; a mismatch invalidates the leg (P405 lesson)."

**Problem.** The `KV cache resolved` line (`mlx_vlm/server/app.py:950`) logs what was **resolved from config** (`cfg.kv_quant_scheme`, `cfg.quantized_kv_start`, …). The P405 incident was precisely that the config asked TurboQuant but the **served per-layer cache** was affine (`runtime.config` froze the import-time default); the log line would have shown `turboquant` and passed. The P405 fix was the per-layer manifest validator (`dev/p369_phase2/kvmanifest.py`), which inspects the actual cache leaves. The spec invokes the "P405 lesson" but uses the weaker instrument that lesson refuted. The P405 root-cause fix is in fork `0f30522c` (verified: `2e66d89d` is an ancestor), so config now flows correctly — but the log line still cannot detect a future regression where config ≠ cache, and it is the *only* thing standing between a silent codec mismatch and a harvested leg. It also cannot verify the TQ4s hybrid path at all — `kvmanifest.expected_manifest` explicitly refuses non-zero `quantized_kv_start` ("only 0 is modelled; anything else is refused, never guessed"), so the very arm whose behavior is hardest to predict (Finding 1) is the one the available validator cannot check.

**Failure scenario.** A future fork bump silently re-freezes a default; TQ4 is served as affine 4-bit. The `KV cache resolved` line still reads `turboquant`, the leg is marked VALID, and the operator decides from affine numbers mislabelled as TurboQuant.

**Change.** Make the engagement gate the per-layer manifest check (`kvmanifest`), not the log line; keep the log line only as a secondary record. For any arm whose codec `kvmanifest` refuses to model (today, TQ4s), either extend the model or refuse the arm rather than falling back to the log line.

---

### 3. MAJOR — Acceptance criterion 3 passes on completeness while known-bad timing is averaged into the decision

**Location:** `p475-kv-matrix.md` Acceptance criteria §3 ("16 legs VALID (speed-valid or labelled)") and Output ("their mean").

**Problem.** A leg is `INVALID` (transport error) only on hard failure, which aborts the run. A leg that is `VALID` but **not speed-valid** (e.g., a thermal throttle, a background process inflating prefill_s, a decode stall) is "labelled" and still counts toward the 16. The Output section then takes "the two blocks' values and their mean" with no statement that speed-invalid legs are excluded from the mean. So a known-bad timing measurement is averaged with a good one, and the operator decides from the polluted mean.

**Failure scenario.** One of the two N16 legs for a pick is speed-invalid (a 20% prefill slowdown from throttling) but VALID; it is labelled and averaged. Every "ratio vs N16" for that pick is then computed against an inflated N16 baseline, making every lossy arm look ~10% faster on prefill than it is. AC3 still passes ("16 legs VALID (speed-valid or labelled)").

**Change.** Exclude speed-invalid legs from the mean (or re-run them), and require each arm to have at least two *speed-valid* legs; make AC3 "16 legs speed-valid" or define the labelled-leg handling for the mean explicitly before the run.

---

### 4. MAJOR — n=2 ABBA per arm with no interval cannot separate a small prefill/decode effect from noise

**Location:** `p475-kv-matrix.md` Output ("two order-balanced legs per arm, no interval claimed") and Order (16 legs).

**Problem.** Peak memory (`peak_mem_gb` = session-cumulative `mx.get_peak_memory`, confirmed monotone non-decreasing in `test_compare.py:291`) is allocation-deterministic, so n=2 memory is tight and the ascending grid correctly reads each rung's own peak. But `prefill_s`/`prefill_tps`/`decode_tps` are timing measurements with real run-to-run variance (thermal, background tasks, GPU state). Two legs per arm, ABBA, with no interval gives the operator a point estimate only. The operator's headline signal is "30% prefill speedup" (large vs noise) but the tradeoff is "for 5% extra memory" — and the spec's own Q1 ("add TQ6 if they are close") needs to detect *closeness*, which has no mechanism without an interval or a third leg. A single noisy leg (which still passes VALID per Finding 3) can flip a 5–10% prefill ratio.

**Failure scenario.** AF8 and TQ4 differ on prefill by 8% at rung 260096, within leg-to-leg noise. The operator reads the point-estimate table, sees AF8 "faster," and picks it — the 8% is noise. Q1's "add TQ6 if they are close" cannot fire because "close" is undefined without an interval.

**Change.** Either add a third leg per arm (still order-balanced, e.g. ABBA + midpoint) so a single outlier is visible, or state explicitly that the matrix is directional-only and that any within-≈15% prefill/decode difference is a wash to be resolved by R6/quality — and define the Q1 "close" trigger in those terms.

---

### 5. MINOR — The N16 arm is labelled "fused SDPA path" but only the Fable pick runs fused <!-- allow-shorthand: verbatim reviewer output -->

**Location:** `p475-kv-matrix.md` Arms table, N16 row "native16 (fused SDPA path)."

**Problem.** The Fable registry entry carries `attention_policy: fused_v1` and `lazy_prompt_embeddings: true`; the `Qwen3.8-27B-mlx-uniform-4bit` entry carries neither. Arms change only KV keys, so for the uniform-4bit pick every arm (including N16) runs the **unfused** attention path. The label is pick-specific, not universal. This is deployment-matched (correct for each pick's decision), but the spec does not flag that the two picks' prefill numbers sit on different attention kernels, so an informal cross-pick comparison of prefill ratios would be invalid. <!-- allow-shorthand: verbatim reviewer output -->

**Failure scenario.** The operator compares the Fable N16→TQ4 prefill ratio against the uniform-4bit N16→TQ4 ratio to decide which pick "benefits more" from quantization, not realizing the Fable ratios include the fused kernel and the uniform-4bit ratios do not. <!-- allow-shorthand: verbatim reviewer output -->

**Change.** Relabel N16 per pick ("fused SDPA" for Fable, "auto/unfused SDPA" for uniform-4bit), or add a one-line note that the two picks' absolute prefill numbers are not comparable across picks. <!-- allow-shorthand: verbatim reviewer output -->

---

### 6. MINOR — The grid wastes a rung and leaves one high-memory point for a "whole tradeoff"

**Location:** `p475-kv-matrix.md` Measurement → `--grid 8192,131072,260096`.

**Problem.** At rung 8192 the model weights (~17.8 GB for a 4-bit 27B) dominate; KV is tiny and nearly identical across all four formats, so 8192 contributes almost nothing to the KV-format decision. The 131072→260096 jump leaves exactly one rung near 256K, where the KV-format memory/speed differences are largest and where the operator's deployment sits. A "whole tradeoff" table with one informative high point is thin.

**Failure scenario.** AF8 and TQ4 look identical at 8192 and 131072 (KV still a minority of peak) and diverge only at 260096 — a single point the operator must trust with n=2 (Finding 4).

**Change.** Drop 8192 from the measured grid (keep it only for the AC2 smoke) and add a rung between 131072 and 260096 (e.g. 196608), so the memory/speed curve has two informative high points.

---

### SCOPE REQUEST — A TurboQuant 8-bit arm may be a distinct 8-bit middle ground

**Location:** `p475-kv-matrix.md` Arms table (AF8 = `uniform` 8-bit) and Open questions Q1 (considers TurboQuant 6, not TurboQuant 8).

The operator asked to "consider middle grounds (8-bit)." The spec's only 8-bit arm is affine (`kv_quant_scheme: uniform`), which per the registry header note engages the standard `QuantizedKVCache`, not TurboQuant. TurboQuant at 8-bit (`kv_quant_scheme: turboquant, kv_bits: 8`) is a distinct codec with different speed/quality characteristics and is the natural 8-bit point on the TurboQuant family that both picks' shipped 4-bit config uses. Whether it differs meaningfully from affine 8-bit is a quality question (R6), but the memory/speed matrix as written cannot speak to it. If the operator wants the 8-bit middle ground characterized on the same codec family as the shipped 4-bit, add a TQ8 arm; otherwise AF8 alone is a defensible 8-bit point. (No severity — this is a scope question for the operator, not a defect in the material.) <!-- allow-shorthand: verbatim reviewer output -->

---

### Notes on things checked and found sound
- Peak-memory semantics (designer assumption 1) confirmed: `peak_mem_gb` is the server's session-cumulative `mx.get_peak_memory` (`test_compare.py:291`, operator ruling 2026-08-17); fresh process per leg resets it; ascending grid reads each rung's own peak.
- The `KV cache resolved` log line exists and reports the fields the spec names (`app.py:950`).
- `bench.run_capacity` resolves on the current fork and its tests exercise the instrument; the AC2 smoke leg covers the live path.
- MTP state is correctly held OFF (both picks ship with `draft_kind` commented; arms change only KV keys).
- Prompt content is controlled across arms (fixed filler + fixed-depth needles, seed 0); cross-rung prefix overlap is ~200 tokens, so cache reuse between rungs is negligible.
