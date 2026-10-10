**X1 — Verdict: revise M57 before implementation.** For `Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed`, `auto | force_fused` is a useful experimental control, **not a performance-maximal design**. The proposal misses a reachable failure boundary, understates verification complexity, and does not adequately qualify long-context quality. I fetched both MLX sources; dispatch conclusions below are source predictions, not runtime observations. No files, models, servers, or GPU workloads were changed.

**X2 — P25 confirmed for ordinary prefill; P27 refuted more substantially than recorded.** Ordinary prefill reaches the native helper through [`language.py:915`]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:915) and [`base.py:433`]($HOME/ws/mlx-vlm/mlx_vlm/models/base.py:433). Generation performs chunking, including shortened snapshot-boundary chunks: [`ar.py:660`]($HOME/ws/mlx-vlm/mlx_vlm/generate/ar.py:660).

But MTP verification bypasses that module’s `__call__`: its separate verifier handles length two jointly with an array mask, and larger unpadded blocks as individual single-query calls. Threading an attribute only through the ordinary call would miss these sites. See [`language.py:1800`]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:1800), [`speculative_verifier.py:114`]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/speculative_verifier.py:114). The existing ragged Metal path is another branch, restricted to single queries: [`language.py:635`]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:635).

**X3 — P30/P37 miss the decisive dispatch boundary.** For head dimension 256, GQA ratio `24/4=6`, valid inference inputs:

| Operation/query length | MLX 0.32.2 `auto` | Forced |
|---|---|---|
| Full 512-token chunk | Fallback | Fused; NAX for eligible dtype/device |
| Tail/continuation, 9–511 | Fallback | Fused |
| Tail/continuation, 6–8 | Fallback | **Raises: `q×6>32`** |
| 1–5, including verifier calls | Fused vector | Same family |
| Long-key single-token decode | Two-pass vector | Same family |
| 1024+, causal string, eligible NAX | Fused | Fused |
| 1024+, array mask | Fallback | Fused |

These follow [dispatch.cpp:618–717 and 759–854](https://github.com/ml-explore/mlx/blob/v0.32.2/mlx/backend/metal/scaled_dot_product_attention.cpp#L618). Odd lengths alone are not unsupported. Full preallocation does not itself require a contiguous KV copy for batch-one, unit-last-stride inputs; see [dispatch.cpp:749–793](https://github.com/ml-explore/mlx/blob/v0.32.2/mlx/backend/metal/scaled_dot_product_attention.cpp#L749).

Consequently, an unrestricted multi-query policy can pass the headline benchmark and fail legitimate continuations.

**X4 — P28 confirmed; P37’s sink warning is overgeneralized; the earlier memory conclusion is unsupported.** Native cache allocation preserves incoming dtype; `kv_bits: 0` does not mean FP16. BF16 is the documented checkpoint-based expectation, still requiring live observation: [`cache.py:3873`]($HOME/ws/mlx-vlm/mlx_vlm/models/cache.py:3873), [`PLAN.md:193`]($STACK_REPO/docs/PLAN.md:193).

MLX promotes Q/K/V to a common floating dtype. Valid sinks are accepted; invalid sink shapes/types and incompatible masks raise independently of forcing. Its fallback explicitly constructs QK scores, applies masking/softmax, and multiplies V: [fast.cpp:754–869](https://github.com/ml-explore/mlx/blob/v0.32.2/mlx/fast.cpp#L754).

The recorded ≤0.07 GiB transient therefore **does not establish absence of score materialization**. One logical FP16 score tensor is `24×512×131072×2 = 3 GiB`. Validate fresh computation, evaluation barriers, peak-reset placement, buffer donation and allocator accounting before interpreting that result. Actual materialization needs tracing.

**X5 — P26 arithmetic is approximately confirmed; causal attribution and P38–P39 costs are unverifiable.** The measured C82 endpoints are 324.84 and 1063.47 seconds at 130783 and 261449 tokens: [`campaign-results.md:2471`]($STACK_REPO/docs/campaign-results.md:2471).

Fitting those endpoints gives:

`T(N) ≈ 0.0008986N + 1.21209×10⁻⁸N² seconds`.

Dividing only the quadratic term by 3.1 predicts **110.95→75.68 seconds at 64K, 324.84→184.40 at 128K, 1063.47→502.21 near 256K**. These are estimates. The intermediate observation is 658.91 seconds versus fitted 642.41; the fit is not a component profile.

Direct microbenchmark integration predicts `0.098×16×512≈803 seconds` saved at 256K, versus the fit’s 561 seconds—explaining the stated ~1.4× discrepancy. Neither supports committing to 12–18 qualification hours before a representative pilot.

**X6 — Remaining record claims need differentiated verdicts.**

- **P29 confirmed:** short coding prompts do not qualify long-key behavior.
- **P30 partially confirmed:** overlay-only chunk testing is feasible; a random-tensor matrix cannot establish the served dtype or layout.
- **P31–P33:** proposed contract, not implemented behavior. Existing structural plumbing is suitable, but needs explicit validation/readback: [`config.py:139`]($HOME/ws/mlx-serve/src/mlx_serve/config.py:139), [`process_manager.py:139`]($HOME/ws/mlx-serve/src/mlx_serve/process_manager.py:139).
- **P34–P36:** experimental proposals, not established qualification. The pool confound is real: `ceil(24×step×262144×2/10⁹)+2` gives 9 and 15; application uses **GiB**, despite “GB” naming: [`cli.py:83`]($HOME/ws/mlx-vlm/mlx_vlm/server/cli.py:83), [`cli.py:122`]($HOME/ws/mlx-vlm/mlx_vlm/server/cli.py:122).
- **P40/P44:** support transcript analysis, but measure *actually reprocessed tokens*, cache misses and retirement work too.
- **P41/P42:** watch-list/evaluation proposals, not evidence.
- **P43:** reject the blanket exclusion of inference-time sparsity. HySparse2’s trained KV-sharing/early-exit architecture is confirmed by its [paper](https://arxiv.org/abs/2609.26368); that does not establish that every sparse retrofit requires retraining.

The following options are ranked by expected useful performance potential and quality preservation, not implementation effort. All gains are conditional estimates.

**X7 — Rank 1: versioned dispatch policy plus chunk-size co-design.** Keep `auto` and strict forcing as diagnostics; production should use an explicit, qualified shape/dtype/mask policy with declared fallback cases and actual-path counters. Compare 512/1024/2048 and boundary-aware chunking, initially fixing the pool.

The recorded 1024-query result normalizes to `84/2=42 ms` per 512 queries, versus forced 46 ms: **~9% additional attention-time reduction**, not end-to-end gain ([proposal:99]($STACK_REPO/docs/proposal-flash-attention.md:99)). Larger chunks also change non-attention work.

Confidence: medium. Quality risk: rounding and boundary bugs. **Decisive experiment:** served-layout matrix including query lengths 1–9 and snapshot tails, followed by one matched 128K prefill. Fund only policies that improve measured latency/memory without holes.

**X8 — Rank 2: eliminate remaining avoidable re-prefill.** This can exceed kernel gains on agentic traffic, but much is already implemented. M48 recorded 64K continuation latency **130→1.2 seconds** and retained a 16,117-token tool observation: [`PLAN.md:137`]($STACK_REPO/docs/PLAN.md:137). Do not count those gains again.

Estimate: preventing a *remaining* cold 128K replay could avoid much of the recorded 325-second prefill; expected benefit equals miss frequency × avoidable replay time. Confidence: high mechanism, unknown remaining opportunity. Risk: incorrect recurrent-state restoration. **Decisive experiment:** CPU transcript/cache-event accounting first; kill additional work if replay is already negligible. Otherwise test affected edit/tool/retirement paths against cold recomputation.

**X9 — Rank 3: custom exact long-context decode and verification kernels.** Target KV reuse across GQA heads and verifier queries, partitioning/reduction overhead, and accepted-token throughput. The verifier’s per-query decomposition is a concrete optimization surface ([`speculative_verifier.py:130`]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/speculative_verifier.py:130)).

Three separate queries versus one joint operation offers up to **3× fewer logical KV scans**, not 3× total decode speed. If attention occupies half a round and improves 2×, total speedup is `1/(0.5+0.5/2)=1.33×`.

Confidence: medium; output risk: changed reductions, acceptance and rollback. **Decisive experiment:** replay identical captured verifier inputs through existing and candidate exact kernels; measure the whole MTP round, accepted tokens, logits and post-rejection state.

**X10 — Rank 4: custom exact prefill kernels and MLX upstream work.** Tune the target shape’s tiling, GQA reuse, masks and long-key occupancy beyond generic forcing. Under X5’s fit, forcing leaves about **267 seconds quadratic +235 seconds other work** at 256K. Another 2× attention improvement gives `235+267/2≈369 seconds`, **1.36× beyond the projected forced result**.

Current MLX `main` broadens the 1024-query NAX route to array masks, but retains the 512-query fallback heuristic: [main dispatch.cpp:1341–1359](https://github.com/ml-explore/mlx/blob/main/mlx/backend/metal/scaled_dot_product_attention.cpp#L1341). Upgrading alone is not a demonstrated solution.

Confidence: low-to-medium upside, low semantic risk if exact. **Decisive experiment:** compare pinned upstream kernels and one specialized candidate on identical served tensors; fund integration only from measured end-to-end headroom. Pin a commit, not moving `main`.

**X11 — Rank 5: GatedDeltaNet and MLP prefill optimization.** The Metal recurrent kernel loops through time; a chunk-parallel formulation exists but is selected on the non-Metal/reference route: [`gated_delta.py:61`]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/gated_delta.py:61), [`gated_delta.py:441`]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/gated_delta.py:441). Every decoder layer also executes its MLP: [`language.py:1202`]($HOME/ws/mlx-vlm/mlx_vlm/models/qwen3_5/language.py:1202).

Investigate a Metal chunk-parallel recurrence, projection fusion and larger-chunk matrix efficiency. Do not equate 48/64 layers with 75% of runtime. Halving the fitted **entire** 235-second linear component would save at most ~118 seconds under that model; the GatedDeltaNet-only saving is smaller.

Confidence: unknown until profiling; risk: recurrent numerical drift. **Decisive experiment:** component timing plus long-sequence state parity for one layer before a full-stack retrofit.

**X12 — Rank 6: cache precision/layout redesign with fused consumption.** Native target KV backing is `16 layers×2×4 heads×256×262144×2 bytes =16 GiB`. Eight-bit storage ideally saves **8 GiB before metadata**; four-bit saves 12 GiB. These are storage calculations, not measured peak reductions.

Existing uniform8 lost badly at 256K—1609 versus 1063 seconds prefill, 5.673 versus 12.948 tok/s—so merely flipping precision is contraindicated ([results:2475]($STACK_REPO/docs/campaign-results.md:2475)). A tiled fused dequantization/attention implementation is a different candidate. Existing TurboQuant machinery is reusable, but its named fused MSE prefill implementation currently raises `NotImplementedError`: [`turboquant.py:5635`]($HOME/ws/mlx-vlm/mlx_vlm/turboquant.py:5635).

Confidence: high storage arithmetic, uncertain speed; quality risk: quantization. **Decisive experiment:** captured-cache error and bandwidth tests, then adversarial long-context quality. Preserve native16 until both pass.

**X13 — Rank 7: sparse/approximate attention, separately for prefill and decode.** Retain full KV initially and select blocks dynamically; this preserves fallback access but saves no persistent KV. Decode selection is the first candidate because sparse prefill corrupts representations subsequently consumed by recurrent layers and future turns.

Illustrative estimate: retaining 25% of attention work with selector overhead equal to 10% gives `0.25+0.10=0.35` of attention time. At attention share 60%, total speedup is `1/(0.4+0.6×0.35)=1.64×`. Neither fraction is measured.

Confidence: low; quality risk: highest. **Decisive experiment:** replay captured queries against full attention, measure missed attention mass, output/logit error and selector cost across distant dependencies. Fund kernel work only if conservative selection survives that screen; then require end-to-end retrieval, reasoning and code-edit tests. Prefill gets its own gate.

**X14 — AC1–AC10 are not executable acceptance criteria yet.** They are compressed into an unnumbered list ([proposal:171]($STACK_REPO/docs/proposal-flash-attention.md:171)). Assign stable definitions and add:

- An eligibility table covering X3, both verifier branches, snapshot cuts, cache retirement/refloor and near-cap appends.
- Independent numerical references, relative/RMS error, NaN checks, causal leakage tests and subsequent-state correctness—not just max-absolute difference.
- Actual kernel evidence; a forced-call counter proves an argument was passed.
- Worker readback of resolved policy, scope and implementation version. Absence in historical evidence must not become falsely observed `auto`.
- A narrowly scoped A/B comparison exception; never bypass unrelated provenance mismatches.
- Startup tests bounded below the router’s configured 300-second readiness timeout ([registry:16]($STACK_REPO/main_models.yaml:16)).

**X15 — Q1/Q4 can accept material quality damage.** Five retrieval plus five reasoning cases allow one loss: **10 percentage points overall, potentially 20 points on one axis**. Conversely, demanding retrieval 1.0 can reject a harmless stochastic miss. Short-code n=100 is not automatically sufficient for ±5pp noninferiority; size from observed discordance with uncertainty ([metrics:49]($STACK_REPO/docs/metrics.md:49)).

Separate retrieval, reasoning and agentic-code strata; include difficult distractors, remote symbol dependencies and sustained continuations. Predefine whether tolerance means relative percent or percentage points. Two sessions do not establish between-session variance; inconclusive evidence warrants a provisional recommendation or more evidence, not automatic equivalence.

**X16 — Q2/Q3/Q5 can reject good designs or approve misleading wins.** Mandatory improvements at every cold-prefill rung exclude useful memory or decode gains. One cached continuation at 128K poorly represents the workload. Use pre-registered workload weights, repeated timing blocks, tail latency, complete task time and clean power conditions. Separate fixed-token performance replay from freely generated quality tests.

Near-cap reasoning also lacks headroom: at 261449 tokens, only `262144−261449=695` remain, yielding at most `floor(0.8×695)=556` thinking tokens. The clamp is implemented at [`generation.py:461`]($HOME/ws/mlx-vlm/mlx_vlm/server/generation.py:461). Capacity completion is not full-budget reasoning qualification. Q5 must distinguish expected negative eligibility tests from failures on supported requests.

**X17 — Recommended roadmap and gates.**

1. **Correct the design record and register workload/quality endpoints.** No-go on implementation until policy coverage includes tails and verification.
2. **Validate instrumentation and capture component costs.** No-go on performance claims until evaluated work and memory accounting reconcile.
3. **Qualify dispatch × chunking**, with fixed allocator policy first. Choose the Pareto frontier; do not require forcing to win.
4. **Fund exact prefill, decode/verification and recurrent/MLP work from measured bottlenecks.** Re-profile after each gain.
5. **Test fused cache precision and sparse decode separately**, then sparse prefill only if its stronger quality gate passes.
6. **Adopt a pinned recipe only after representative multi-turn quality and full-context stability pass.** Treat inconclusive quality as unresolved, not safe by default.

I disagree specifically with unrestricted forcing, the memory inference, the narrow cold-TTFT adoption rule, and P43’s categorical exclusion of sparse retrofits.

