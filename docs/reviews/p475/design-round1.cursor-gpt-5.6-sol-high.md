1. Location: Output and Acceptance criteria (`p475-kv-matrix.md:51–64`)  
Severity: blocker  
Problem: Quality is excluded from the accepted deliverable. Only the apparent performance winner receives an unspecified later R6 study, while “N16 needs none.” That cannot support a whole-tradeoff choice when every non-native format is lossy and the current quality evidence was collected under different KV codecs/builds.  
Concrete failure scenario: AF8 wins the matrix, fails R6, and TQ4 becomes the fallback without matched quality evidence. Conversely, native16 changes the second pick from its evaluated quantized path but is adopted without a current control.  
Proposed change: Make matched predictor-OFF quality measurement part of acceptance for N16 and every performance-Pareto lossy arm. Select only after those results; do not test only the provisional winner.

2. Location: Peak-memory premise in Measurement (`p475-kv-matrix.md:36–39`)  
Severity: major  
Problem: “Ascending rungs, so each rung’s reading is that rung’s peak” is false. `peak_memory` comes from process-lifetime `mx.get_peak_memory()`, and `run_capacity` performs a calibration request before every rung. Full-cap KV preallocation happens on that calibration request, so every later row reports at least the calibration high-water.  
Concrete failure scenario: TQ4s calibrates below 131K using a full-cap native cache and reaches 47 GB. Its 260K quantized request peaks at 38 GB, but the row still reports 47 GB and attributes it to the 260K rung.  
Proposed change: Treat it only as a per-worker cumulative high-water, or use a dedicated harness with a sacrificial calibration worker followed by a fresh worker for each measured rung. Report actual active/retained memory separately if memory by rung is required.

3. Location: Prefill measurement in Measurement (`p475-kv-matrix.md:36–39`)  
Severity: major  
Problem: `bench.run_capacity` does not report the backend’s measured prefill time. `MlxServeDriver` computes `wall_s - predicted_ms`, although the response already contains `timings.prompt_ms` and `prompt_per_second`. The derived value includes routing, tokenization, response processing, and cache retirement/shrink. It also discards `cache_n`.  
Concrete failure scenario: A format with slower session-cache retirement appears to have slower prefill even when its actual backend prefill is faster; accidental prefix reuse produces an inflated effective tok/s and passes unnoticed.  
Proposed change: Persist and use raw `prompt_ms`, `prompt_per_second`, `prompt_n`, and `cache_n`; require `cache_n == 0` with unique session IDs for every measured request.

4. Location: Decode measurement in Measurement (`p475-kv-matrix.md:38–39`)  
Severity: major  
Problem: The requests permit up to 256 tokens but do not require exactly 256 or `finish_reason == "length"`. Retrieval answers can stop early and lossy arms can generate different lengths/content, making decode rates incomparable.  
Concrete failure scenario: One arm emits 20 tokens before EOS while another emits 220 thinking/answer tokens. Their reported decode tok/s reflect different workloads, yet the matrix presents a direct ratio.  
Proposed change: Use a fixed decode carrier that reliably reaches an exact token cap, reject short/EOS completions, and record completion tokens and finish reason. Keep retrieval requests separate from decode measurement.

5. Location: Engagement check and TQ4s arm (`p475-kv-matrix.md:28,40–41`)  
Severity: major  
Problem: Worker argv plus `KV cache resolved` proves configuration, not the live cache implementation. P405 specifically established that configured TurboQuant could serve affine cache. TQ4s is especially unverified: it starts native, later converts the entire existing prefix to TurboQuant, and can transiently hold both full-cap representations.  
Concrete failure scenario: The threshold is ignored or never crossed because actual prompt tokens are below the nominal rung; all legs still pass engagement because the startup line reports the requested value.  
Proposed change: Add a committed known-positive live-cache preflight for every codec and a threshold-crossing smoke for TQ4s. Record actual prompt tokens and transition evidence. Describe TQ4s as conversion-on-crossing, not a permanently mixed native-prefix/quantized-suffix cache.

6. Location: Arms table (`p475-kv-matrix.md:23–28`)  
Severity: major  
Problem: Affine 4-bit KV is omitted. It is directly relevant: historical certifications for these picks used affine 4-bit, and the checkout already contains a P405 affine4-versus-TQ4 performance instrument. AF8 cannot substitute because both bit width and implementation/layer coverage differ.  
Concrete failure scenario: AF4 provides materially better quality than TQ4 with acceptable memory and speed, but the matrix can never select it.  
Proposed change: Add AF4 for both picks, or cite current matched evidence sufficient to eliminate it before this matrix.

7. Location: Settled MTP state and engagement/acceptance (`p475-kv-matrix.md:15–18,40–64`)  
Severity: major  
Problem: Predictor-OFF is asserted from “the committed state” but is not an explicit validity check. Nothing requires absence of `--draft-kind`/`--draft-model`, a null manifest `runtime.draft_kind`, or absent draft counters.  
Concrete failure scenario: P476 enables MTP before arm branches are created. Every arm runs MTP-ON, passes its KV checks, and decode rankings include codec-specific speculative behavior contrary to the settled constraint.  
Proposed change: Fail every leg unless argv, manifest, and response telemetry independently prove predictor-OFF.

8. Location: Acceptance criterion 3 (`p475-kv-matrix.md:63`)  
Severity: major  
Problem: “speed-valid or labelled” allows acceptance with unusable speed observations. Merely labelling a thermally invalid or otherwise incomparable leg does not provide the requested matched basis.  
Concrete failure scenario: One block for AF8 violates power validity, is labelled, and the remaining single observation still enters the mean; all 16 legs satisfy acceptance.  
Proposed change: Require two speed-valid, order-balanced legs per arm for every reported speed ratio. Preserve labelled invalid legs as evidence, but require replacement runs.

9. Location: Q1 (`p475-kv-matrix.md:70–72`)  
Severity: minor  
Problem: TQ4 and AF8 do not “bracket” TQ6 because they change both scheme and width; performance and quality need not be monotonic across those implementations.  
Concrete failure scenario: TQ6 is substantially faster than AF8 and materially better quality than TQ4, yet is skipped because the endpoints appeared close or ordered.  
Proposed change: Remove the bracketing claim. Define a staged trigger for TQ6 based on the Pareto results and quality uncertainty.

10. Location: Measurement prompt and Output averaging (`p475-kv-matrix.md:36–39,51–54`)  
Severity: minor  
Problem: Each rung uses one highly repetitive ASCII filler/retrieval prompt per loaded instance, and the final statistic is a two-value mean with no instability rule. This can conceal content-sensitive quantization behavior and session variance.  
Concrete failure scenario: An arm is faster only on repetitive filler, or its two block ratios have opposite signs, but the mean still presents a clean ranking.  
Proposed change: Include a second committed, token-matched coding-like carrier and report paired block ratios. Label an arm inconclusive—and run a deciding block—when direction reverses or spread is decision-material.
