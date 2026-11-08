# M72 step 1.1 — the TQ4 performance probe for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (2026-11-07, session 19)

Baseline: that pick as shipped (native16 + `fused_v1` + `joint_v1`, MTP ON). Numbers: the generated scoresheet `PROBE.md` (never
hand-edited; regenerate with `python benchmark/spikes/m72_probe_report.py benchmark/results/m72/probe`). Raw passes:
`probe/probe-nax-{on-1,off,on-2}.{json,log}` (ABA, 10-minute idles, 140 W / 28 V, battery 80 %); spike reruns
`probe/spike-{g,h}-4bit*.log` (their launcher log is `probe/launcher.spikes.log`; the probe passes it lists belong to the
superseded v2 instrument, archived under `$STACK_WORKDIR/m72/`). GPU used: ≈ 10 minutes of kernels over ≈ 1.5 h wall.

## Instrument

A synthetic per-layer microbenchmark at the pick's attention shapes (24 q / 4 kv heads, head dim 256, bf16), calling the fork's
production dispatch (`models.base.scaled_dot_product_attention`, the M58 verify helpers) on a TurboQuant 4 cache and a native16 buffer
both preallocated to the 262,144-token cap, as served. Sixteen full-attention layers are summed; everything else is taken from
measured end-to-end runs. Known-positive check against P475 (`Qwen3.8-27B-mlx-uniform-4bit`, same attention shapes): TQ4 prefill
predicted within −7…−8 % at 131K–260K, TQ4 decode (MTP OFF) within −5…−8 %; MTP ON decode over-predicted by +7…+18 % (both formats;
TQ4 more), so the MTP ON projections below lean optimistic. Two instrument revisions during the run, both before any result was
used: (v1→v2) `mx.sum` over a sliced buffer measures a copy, so the byte ceilings now read contiguous copies; (v2→v3) the at-cap
checkpoint (262,144) is contiguous and hides the layout copy, so the P475 rungs 196,608 / 260,096 were added and projections use
sub-cap points only.

## Findings (mechanisms)

1. **Decode already has a fused kernel; it is not the main loss.** The shipped 2-pass GQA kernel dequantizes in registers. On a
   contiguous state at 260K it takes 2.07 ms per layer vs native16 SDPA 2.27 ms: per call it is already slightly faster than
   native16. Two things cost it: (a) **the layout copy**: below the cap the state is a time-slice of the full-cap buffer, not
   contiguous across heads, and the custom Metal kernels copy their inputs first, 2.98 ms (+44 %) at 260K and +42 % at 128K;
   (b) **its access pattern**: 131 GB/s effective on 0.27 GB vs 361 GB/s for a plain read of the same bytes (native16 SDPA runs
   469 GB/s). The June spikes, rerun at 4-bit on this box: spike H (codebook in threadgroup memory, unrolled dims, grouped
   reductions) **1.00× at 262K, 0.94–1.04× elsewhere, with NAX on and off**, so per-token compute is not the lever; spike G's
   no-exp variant is ≈ 11 % faster (softmax share) and its "read-only" kernel is *slower* than the full one, so the bound is the
   per-simdgroup token-strided access pattern. Closing (b) needs a restructured kernel (coalesced loads, more tokens in flight):
   uncertain engineering, the last fix in value order.
2. **MTP verify is the largest decode loss.** TurboQuant caches take the per-query loop (P400 exactness; `joint_v1` excludes
   them): a k = 3 block costs 8.72 ms per layer at 260K vs native16's joint call 5.16 ms, 2.9× a single TQ4 decode, because each
   query re-reads and re-copies the whole state. A multi-query kernel that loads each KV tile once for all k queries costs about one
   decode pass.
3. **Prefill: TurboQuant's attention path does not use the Neural Accelerators; native16's does.** NAX-off / NAX-on time:
   native16 `fused_v1` 3.3–3.6×, TQ4 production loop 1.35–1.37× (the surrounding MLX ops only), TQ4 decode 1.00 (bandwidth /
   latency bound, as expected for one query; native16 decode also 1.00). Per 512-query chunk at 260K: TQ4 loop 409.6 ms vs
   `fused_v1` 102.7 ms (4.0×). **Dequantizing the layer's K/V to bf16 and calling MLX's fused SDPA puts TQ4 prefill on the
   accelerators with no new attention kernel** (2.6–2.9× NAX sensitivity): 156.6 ms per chunk with today's generic ops, 141.0 ms
   keeping the vectors in the codec's rotated space (exact: rotate q once, inverse-rotate the output once; matches production to
   bf16 rounding, rel ≤ 0.75 %). What remains is dequantization, 43–60 ms by generic MLX ops (noisy, NAX-insensitive) for a job
   whose pure traffic is ≈ 1.3 GB (≈ 3 ms): a small fused unpack kernel takes prefill to ≈ native16 parity. Transient cost: one
   layer's bf16 K/V (≈ 1.07 GB at 256K), sequential across layers.
4. KV append (quantize 512 tokens) is 0.27 ms per layer at long context, negligible (the 5 ms at 8K is warmup).

## Measured potential for `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed` (ratios vs its shipped native16; `PROBE.md` §4)

| fix (cumulative where marked) | prefill 128K / 260K | decode MTP ON 128K / 260K | decode MTP OFF 260K | build size |
|---|---|---|---|---|
| TQ4 today | 0.48× / 0.35× | 0.75× / 0.72× | 0.87× | — |
| P1 prefill via dequant + fused SDPA, generic ops (rotated space) | 0.89× / 0.83× | — | — | small: Python dispatch only |
| P2 + fused unpack kernel (ceiling = native16 attention cost) | ≈ 1.00× / ≈ 1.00× | — | — | small Metal kernel |
| D1 multi-query verify (one TQ4 pass per block) | — | 1.14× / 1.31× | — | medium: kernel variant + exactness |
| D2 + no layout copy (stride-aware inputs) | — | 1.25× / 1.51× | 1.04× | small |
| D3 + kernel at the TQ4-bytes read ceiling | — | 1.46× / 1.93× | 1.48× | large, uncertain (finding 1b) |

Memory: ≈ 12–13 GB less KV at 256K (17.2 → ≈ 4.5 GB; P477 arithmetic), i.e. ≈ 25–26 GB vs 38.25 GB peak, minus P1/P2's ≈ 1 GB
transient. Uncertainty: projections swap only the 16 layers' attention into the pick's own measured end-to-end time; the
validation bounds them at ≈ ±8 % (prefill, MTP OFF decode) and +7…+18 % optimistic (MTP ON decode). The 128K baselines are older
(M57 / M58, MLX 0.32.2); the 260K baselines are P426 M1 (260,096 tokens). Acceptance assumed unchanged on TQ4 (P475 saw TQ4
acceptance within noise of native16).

## Reading

- With D1 + D2 + P1/P2 (all small-to-medium, none of them the uncertain D3), the pick on TQ4 would decode ≈ 1.25× (128K) to
  ≈ 1.5× (260K) faster than shipped, prefill at ≈ parity (P2) or ≈ −15 % (P1 alone), with ≈ 12 GB less memory. Discounting the
  MTP ON optimism (≈ 15 %) still leaves ≈ +10…+30 % at 128K–260K. Short context (8K) gains ≈ nothing: attention is a small share there, and at
  8K TQ4 per-call overheads (≈ 0.55 ms of query prep / reduce / rotation per layer per call) exceed native16's.
- Every fix changes TQ4 numerics (P1/P2 at bf16 rounding vs today's TQ path; D1 must match the singleton kernel per query or MTP
  exactness needs re-certification). TQ4 itself is uncertified for this pick, so 1.4's quality campaign is required either way
  (C309 addendum: it covers both picks).
- **Recommendation (S19-P4): go on 1.2, prototypes in value order D1 + D2 (one stride-aware multi-query decode kernel, per-query
  bit-identical to the singleton kernel), then P1 → P2; D3 deferred until the others are measured end to end.** Counterpoint: the
  decode win is concentrated above ≈ 64K and the prefill track only reaches parity; if the daily workload rarely sits above 64K,
  the payoff is mostly the memory, which this pick does not need (38.25 GB vs ≈ 48 GB guidance).
