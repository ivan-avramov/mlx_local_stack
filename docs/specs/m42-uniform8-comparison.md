# C82 proposed native16 versus uniform8 KV comparison

Status: proposed, not armed. C81 separately approves native16 as the provisional
recommendation and actual registry default. Model:
`Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`. Do not interpret native16 as uint16,
a weight conversion or a new checkpoint.

## Question and recommendation

Does MLX uniform 8-bit affine KV retain native16's useful quality and speed while
reducing cache memory on the M5 Max 64GB? Compare it directly with fresh native16
controls. Prefer this existing backend before implementing additional cache
formats. FP8 in MLX core is not itself an implemented FP8 cache in this fork.
No hardware speed advantage is assumed from bit width alone.

## Fixed arms

- Native16: `kv_bits: 0`, quantization disabled. Explicit worker `KV_BITS=0`.
- Uniform8: `kv_bits: 8`, `kv_quant_scheme: uniform`, group size64.
- Frozen source c5a6f97b/f8f1df4, MLX/Metal0.32.2 and the C80 serving pins.
  Preserve weights, repaired MTP ON, deployed t0.5/medium, sampling, cap and
  preallocation262144, prefill512, APC absent and retained sessions2.
- Inspect and verify cache classes, bit widths, group size, native dtype and
  preallocation in a bounded instrument check before real model work. Expected
  target: native16 has16 native full-attention caches; uniform8 quantizes all16
  eligible caches. The48 recurrent states and drafter settings stay unchanged.
  Do not reuse TQ4's15-quantized-plus-one-native description for uniform8.
  Unexpected layout or incompatibility stops preparation for review, not an
  unapproved runtime fix. Do not change frozen fork sources.

## Bounded measurements: 38 model generations

1. Repeat the exact C80 five Math500, five HumanEvalPlus and five MBPPPlus tasks
   in each state:15 pairs /30 fresh generations, no generation warmups. Reuse
   frozen corpus IDs, messages and seeds; verify byte-identical paired request
   payloads. Full deployed max_tokens102400 and resolved thinking budget81920.
   Keep the original C80 rows immutable and separate. Each five-task arm is the
   pilot; do not silently replace failures or expand the sample.
2. After valid completion/grading, repeat the three capacity rungs in each
   state: nominal131072/196608/262144, actual130783/196115/261449 prompt tokens.
   One equivalent calibration per state plus three measured requests gives
   eight generations. Reuse exact historical prompts/seeds and bounded256-token
   capacity settings; report these separately from full-budget quality tasks.
3. Record `mx.get_peak_memory`, prefill time/TTFT, decode rate, task wall time,
   output tokens, MTP acceptance and observed memory pressure/stability. Memory
   remains a rough48GB guideline, never an automatic46/48GB cutoff. Infrastructure
   failures abort rather than becoming incorrect answers. Do not kill legitimate
   generations merely for exceeding a time estimate.

Use fresh sessions and matched procedure for each state; alternate state order
between quality and capacity to avoid always favoring the same order. Capture
actual source/import paths, package pins, worker arguments/environment, overlays,
payloads and manifests. No second model, new task corpus, external judges,
production activation, automatic configuration switch or push.

## Implementation and verification after approval

Version private C80 generation/grading and capacity instruments under a new
directory inside `$STACK_WORKDIR/upstream/2026-09-13`; preserve original evidence.
Adapt the treatment/selection guards to native16/uniform8 and immutable new tags.
Test altered guard behavior with fake requests, then independent review before
launch. Retain root-owned router lifecycle, driver environment checks, exact
request-count guards, derived timeouts, no retries, detached supervision,
300-second assessments and known-positive SELFTEST/RUNNER-EXIT events.

Reuse canonical symbolic math grading and the verified network-disabled ARM64
EvalPlus sandbox, pinned image
`sha256:ff0ea20905962ccef0bcfc07f4ae0d389acdbafd4736c0b33eb51d350f048b43`.
Require root-pinned completion/input hashes; never execute generated code on the
host. Preserve official HumanEval/141 scores and the known prompt/reference
counterexample annotation. No grading-rule changes are part of this comparison.

## Interpretation and cost

Report ordinary/strict accuracy, convergence and failure kinds per axis, paired
exclusive solves, effect sizes and intervals. Five pairs per axis cannot certify
equivalence; zero-discordance bootstrap intervals do not bound unseen failures.
Report latency and token counts together, with short-task and capacity timings
separate. These capacity probes do not establish long-context quality.

Recommend uniform8 only if its measured quality, latency and memory tradeoff
improves the practical choice; less memory alone is not a win when native16 fits.
If native16 remains preferable, retain it. Any later larger quality/depth study
requires a concrete scope; no automatic expansion.

C80 native16's15 quality tasks took235.5 seconds of HTTP generation and its prior
three-rung capacity procedure took37.8 minutes including calibration. Uniform8
runtime is unmeasured. These observations guide planning, not a guaranteed ETA
or lower bound; update estimates from the new pilot's mean/max and allow loading,
grading and tail time. Do not infer that eight-bit computation must be faster.
