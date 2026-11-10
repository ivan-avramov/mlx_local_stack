I have enough to write the findings now.

## Verification: M72 P2′ stage 1 candidate vs spec v1.1

### Part 1 — Design-review findings (as disposed): resolved in the candidate?

All 18 disposed findings are resolved in the candidate, except F10 (adopted as an assumption, no code required) and F1 (declined as false, consistent with the candidate). Evidence is traced to source.

**Sol P1 (ms→s in projection) — RESOLVED.** `m72_p2s_report.py` `attn_s` divides the per-chunk sum by `1e3` and `append_ms[a] / 1e3` is applied per arm (`stack.diff:86,94`). Units are seconds throughout.

**Sol P2 (interp/append source; tautological native check) — RESOLVED.** `interp` is imported from `m72_probe_report`; `APPEND_T = 260096` and `APPEND_KEY` pin the field per arm family; the two-pass mean is taken over `names`. The synthetic report test checks the formula against hand-computed anchors.

**Sol P3 (growing scratch defeats reuse; A4 ignores cache) — RESOLVED.** The kernel writes cap-sized outputs (`fork.diff:127` `output_shapes=[(1, n_kv, cap, D), …]`); `scratch_prefill_tq4` slices to `[:, :, :T, :]` (`fork.diff:152-153`). The growing-T scenario lives in the driver's `context_memory_spike.py` `grow` scenario.

**Sol P4 (A4 window not chained) — RESOLVED (in the separate spike).** `context_memory_spike.py` runs `fwd_lazy`/`fwd_eval`/`fwd_dep` as chained 16-layer graphs; the probe's `p2s_chain16` measures lazy vs per-layer timing.

**Sol P5 (bit-identical P1 may fail A1) — RESOLVED.** `dequant_rotated` defaults to `mx.float16` (`fork.diff:111`); the preflight picked fp16 (1.16×, inside A1).

**Sol P6 (reference helpers lack explicit T) — RESOLVED.** `reference_dequant_rotated(state, T, codec, dtype)` and `reference_prefill(cache, queries, scale, T, dtype)` both take explicit `T` (`fork.diff:163,170`); the sweep records `bit_identical` per row.

**Sol P7 (N1 strength; heads miss KV head 2) — RESOLVED.** `P2S_PLANT_SCALE = (1.0, 4.0, 16.0, 64.0)`, `P2S_HEADS = (0, 6, 12, 18)` (one per KV head), and the shift is applied to the K/V fed to SDPA via `_perm` (`fork.diff:139-145,151-153`), so query group h reads KV head `(h+shift) mod n_kv`.

**Sol P8 (full-path bit identity exceeds requirement) — RESOLVED (adapted).** Dequant fidelity is the gate; full-path identity is recorded as `p2s_vs_reference_bit_identical` bool and the frozen test is `xfail` (`test_m72_scratch_prefill.py:428`).

**Sol P9 / GLM F8 (criterion naming; `--max-t` scope) — RESOLVED.** A4 = memory, A5 = in-place; sweep T above `--max-t` are skipped and listed in `skipped_T` (`stack.diff:455,461`).

**GLM F1 (`rot_fused` passes qp not qr) — declined as false; consistent.** The candidate's `scratch_prefill_tq4` computes `qr = cache.key_codec.prepare_queries(queries).astype(dtype)` and passes `qr` to SDPA (`fork.diff:154,156`).

**GLM F2 (A4 must exclude SDPA transients) — RESOLVED (in the spike).** `context_memory_spike.py` `fwd_resident` is the SDPA-only baseline (resident pre-dequantized copy), so SDPA's own transients cancel.

**GLM F3 (codebook dtype at multiply) — RESOLVED.** `threadgroup float cbk[16]; cbk[tid] = key_codebook[tid];` and `static_cast<OT>(cbk[...] * kn)` — codebook staged and read as fp32, fp32 product, one rounding (`fork.diff:51-53,68-69`).

**GLM F4 (causal alignment for L<T unstated) — RESOLVED.** `p2s_causal_alignment` compares `mask="causal"` against explicit bottom-right (`j <= i + (T - L)`) and top-left masks (`stack.diff:718-728`); the frozen test `test_causal_alignment_matches_an_explicit_mask` covers `scratch_prefill_tq4` directly.

**GLM F5 (projection append/fixed double-count) — RESOLVED.** `fixed = t_meas - LAYERS*attn_s(n16) - LAYERS*chunks*append_ms[n16]/1e3`; `t_X = fixed + LAYERS*attn_s(X) + LAYERS*chunks*append_ms[X]/1e3` (`stack.diff:92-94`). The native16 append is subtracted in `fixed`, so the native reconstruction is no longer tautological.

**GLM F6 (fp32 reference cost at 262144) — RESOLVED.** `p2s_ref_head` computes one head at a time on the CPU stream; `p2s_a1_heads` does `del ref; mx.clear_cache()` after each head; `measure_checkpoint_p2s` clears after the accuracy block (`stack.diff:702-704,848-849`).

**GLM F7 (N1 shift semantics) — RESOLVED.** `dequant_rotated` takes no shift; `_kv_head_shift` rolls KV heads in the SDPA grouping only (`fork.diff:139-145,151-153`).

**GLM F9 (in-place check unspecified) — RESOLVED.** `test_a5_kernel_inputs_are_the_unsliced_state_arrays` asserts the state's own arrays are passed (identity) and shape is full-cap; `test_a5_sentinel_past_t_does_not_change_the_output` asserts the sentinel past T leaves `[0,T)` unchanged.

**GLM F10 (RHT assumption) — RESOLVED as assumption.** Stated in spec Assumptions; no code required.

**GLM F11 (provenance refusal fields) — RESOLVED.** `provenance_mismatch` checks `meta.fork.head`, `meta.mlx`, `meta.device.architecture`, `meta.p2s_kernel`, checkpoint T list, and arm orders (one forward + one reverse) (`stack.diff:46-63`).

**GLM F12 (dequant share is diagnostic) — RESOLVED.** The report labels `p2s dequant only = the kernel alone (diagnostic)` in the table header and description (`stack.diff:193`).

### Part 2 — Anything else the candidate breaks or leaves failing

I found no blocker or major under the supported conditions. The kernel indexing, rounding, cap-sized outputs + slice to T, causal alignment, references and A1 logic, timing order, projection, refusals, launcher, and the candidate-side memory threats are all consistent with the spec and pass the frozen tests (per `testwriter-2-report.md`: 92+57+23+21 passed; the one prior failure was the amended parser-choices test). Below are the minor items and scope observations.

---

**M1 — `p2s_causal_alignment` exercises the reference helpers, not `scratch_prefill_tq4`.** Location: `stack.diff:718-728`. Severity: minor. Evidence: confirmed. Problem: the probe's recorded `causal_alignment` diagnostic runs `mx.fast.scaled_dot_product_attention` on `pm.reference_dequant_rotated` K/V, so it validates MLX's `mask="causal"` semantics, not the candidate's full path. Failure scenario: a regression that breaks alignment only inside `scratch_prefill_tq4` (e.g. a future change to the `[:, :, :T]` slice) would not show in this diagnostic. Proposed change: also record a `scratch_prefill_tq4`-based alignment sample, or rely on the frozen test (which already covers the full path) and note the diagnostic's scope. Note: the frozen `test_causal_alignment_matches_an_explicit_mask` covers the full path, so A3 itself holds.

**M2 — `p2s_a1_all` aggregates per-head A1 as `max` over heads 0/6/12/18 for the sweep's gating rows.** Location: `stack.diff:707-714`. Severity: minor. Evidence: confirmed. Problem: the spec says A1 "on the sweep's L = 512 rows" without specifying aggregation; the candidate's `pass = finite and close and rel <= 2*max(prod_rel, A1_FLOOR)` with `rel = max(per-head rel_err)` and `prod_rel = max(per-head prod_rel_err)` is conservative but unspecified. Failure scenario: a head-specific defect just under the aggregated bound could pass the sweep yet fail the per-head checkpoint check. Proposed change: none required; the per-head checkpoint check (`p2s_a1_heads`) catches head-specific defects. Optionally document the aggregation as `max`-over-heads.

**M3 — `_DTYPE_NAMES[dtype]` raises bare `KeyError` for unsupported dtypes.** Location: `fork.diff:39,121`. Severity: minor. Evidence: confirmed. Problem: a caller passing `dtype=mx.float32` gets an uninformative `KeyError` from `_kernel(out_t)`. Failure scenario: a future caller passes fp32 and sees a traceback deep in `_kernel`. Proposed change: raise `ValueError` with a clear message listing fp16/bf16. Not material under the supported conditions (fp16/bf16 only).

**M4 — The report hard-codes "262,144" in the header and chain16 line.** Location: `stack.diff:169,205`. Severity: minor. Evidence: confirmed. Problem: on shrunk-cap runs the header still says "262,144". Failure scenario: a shrunk smoke run reports a misleading cap. Proposed change: derive the cap from the data (`max(c["T"] for c in checkpoints)` or `meta.shapes.cap`). Not material under the supported conditions (cap = 262,144).

---

**Scope request S1 — `benchmark/spikes/m72_p2s_memory.py` `--impl p2s` wiring and A4 scenarios are not in the candidate.** Location: spec scope item 2; `stack.diff` (no `m72_p2s_memory.py` hunk). The spec assigns this file to the designer ("the designer owns this spike's instrument code"), and the implementer's report confirms A4 was read-only to it. The existing `m72_p2s_memory.py` in the impl tree has two defects for `--impl p2s` (the implementer flagged them): (a) `st.norms, st.indices = mx.depends(...)` raises because `TurboQuantMSEState` is a NamedTuple; (b) `prefill` casts queries to bf16 while `dequant_rotated` returns fp16, giving SDPA mixed dtypes. It also lacks the A4 scenarios (SDPA-only baseline, growing T). The driver's `context_memory_spike.py` is the working A4 instrument and has the correct `p2s` wiring. This is a designer gap, not a candidate defect; flagging only so A4's delivery does not silently depend on the broken spike. Proposed change: the designer either fixes `m72_p2s_memory.py` `--impl p2s` (replace the `depends` assignment with `mx.depends` on the kernel inputs; cast queries to fp16 or pass `dtype=mx.float16`) and adds `fwd_resident`/`grow`, or documents `context_memory_spike.py` as the A4 instrument of record.

---

**Summary.** Every disposed design-review finding is resolved in the candidate (F10 as assumption, F1 declined-as-false consistent). No blocker or major remains under the supported conditions. The four minor items (M1–M4) do not affect the spec's criteria; the one scope request (S1) is the designer's `m72_p2s_memory.py` gap, not the candidate's.The background `find` task completed successfully — it located the original probe files I needed (the impl-tree `m72_tq4_probe.py`, `m72_probe_report.py`, and `m72_p2s_memory.py`), which I used to confirm the candidate's `--mode p2s` wiring, the `interp`/`projection` helpers, and the pre-existing `--impl p2s` bugs. No further follow-up is needed; the verification findings above are complete.
