P1  
Location: `spec.md:63-76, 126-128`  
Severity: major  
Evidence: confirmed  
Problem: The 2% unpack-cost assumption omits repetition across query-position threadgroups. With `P=16`, each KV head is unpacked 32 times per chunk. F3 demonstrates roughly 190–200G lookups/s, not enough to make this negligible.  
Concrete failure scenario: K+V require about 17G lookups at 260K, implying roughly 57–90ms of unpack work—comparable to the 102.7ms native16 baseline before attention overhead.  
Proposed change: Replace the 2% claim with a cost model containing the `512/P` repetition factor. Require measurement of unpack-only cost and allow packed-fragment/register lookup alternatives rather than mandating full half-tile expansion.

P2  
Location: `spec.md:63-71, 126-127`  
Severity: major  
Evidence: confirmed  
Problem: No stated `(BK,P,WN)` configuration has a complete threadgroup-memory lifetime budget. At `BK=32`, simultaneous half K/V consume 32KB. For `P=16, WN=2`, the reference dsplit score exchange consumes another 24KB. Packed staging, norms and codebook storage are omitted.  
Concrete failure scenario: A literal implementation allocates separate K, V and score-exchange arrays and fails compilation or launch despite satisfying the stated “≤32KB” rule.  
Proposed change: Provide a byte-and-lifetime table and one mandatory feasible default. Explicitly require phase reuse of storage—K staging, score exchange, then V staging—if that is the intended solution.

P3  
Location: `spec.md:63-70`  
Severity: major  
Evidence: confirmed  
Problem: `BK=16` is declared free, but `BaseNAXFrag::mma`’s relevant form produces 32 score columns from two B fragments. One 16-row simdgroup therefore needs a padded second fragment or a different 32-row packing.  
Concrete failure scenario: An implementer loads the nonexistent second half of a 16-token tile, causing out-of-bounds reads; zero-padding it instead wastes half QK work.  
Proposed change: Fix `BK=32`, or specify the safe `BK=16` fragment construction and its expected wasted work or paired-32-row mapping.

P4  
Location: `spec.md:63-65, 126-127`  
Severity: major  
Evidence: hypothesis  
Problem: The register/occupancy fallback is not demonstrated. `WN=1` needs 128 fp32 output accumulators per lane for D=256, plus scores, Q and softmax state. `WN=2` reduces registers but raises the launch to 384 threads for `P=16` and requires the score exchange from P2.  
Concrete failure scenario: `WN=1` spills and is structurally slow, while the nominal `WN=2` fallback exceeds memory unless storage is carefully aliased.  
Proposed change: Preselect a feasible default from an actual compile/resource probe and record thread count, allocated threadgroup memory and chosen split in `meta.p2_kernel`.

P5  
Location: `spec.md:63-75`  
Severity: major  
Evidence: confirmed  
Problem: GQA row linearization is unspecified. Causal position cannot be derived from the packed fragment row as MLX’s one-head reference does. Physical query loading also remains simple only when head-major `P` is a multiple of 16.  
Concrete failure scenario: With `P=16`, the second query head’s first packed row is mistaken for position `block_start+16`, exposing sixteen future tokens.  
Proposed change: Define `row = head_in_group*P + local_position`, `query_head = g*6 + row//P`, and absolute position `q_offset + block_start + row%P`; require `P % 16 == 0` and safe handling of partial blocks.

P6  
Location: `spec.md:55-58, 70-73`  
Severity: minor  
Evidence: confirmed  
Problem: The scaling and online-softmax instructions are contradictory or incomplete. `q′` already contains `scale`, while “scale folded” can be read as applying it again. It also does not state that the softmax denominator uses unmodified probabilities before value norms are folded into the PV operand.  
Concrete failure scenario: Copying MLX’s `scale·log2(e)` step after preparing `queries*scale` double-scales scores; summing value-norm-scaled probabilities corrupts normalization.  
Proposed change: State the update equations explicitly: apply model scale exactly once, multiply by `log2(e)` only for `exp2`, update sum from unscaled probabilities, and apply value norms only to the PV operand.

P7  
Location: `spec.md:80-90, 104-110`  
Severity: major  
Evidence: confirmed  
Problem: The TQ4 production accuracy comparator is not required to use a real prefix ending at the true query offset. Planted caches deliberately contain one extra token, unlike ordinary checkpoint states. The sibling specification explicitly required a real slice; this one omits it.  
Concrete failure scenario: Production attends to the planted future token, inflating `prod_rel_err` and weakening A1 rather than measuring the existing path on the same mathematical problem.  
Proposed change: Require real K/V-state slices through `q_offset+L` for both production comparators, including planted cases; proxy metadata alone must not qualify.

P8  
Location: `spec.md:89-94, 111`  
Severity: major  
Evidence: confirmed  
Problem: A5 has no isolated measurement window and conflicts with the fp32 reference. At 262K, full fp32 K/V dequantization is about 2.15GB, unpack intermediates can be similar, and each full 512×T score matrix is about 0.54GB per head. The single checkpoint `peak_GB` can therefore measure P1/reference allocations rather than P2 temporaries. At small T, the 0.4× allowance may also be smaller than query/output rotation buffers.  
Concrete failure scenario: A correct no-materialization kernel fails A5 because accuracy or P1 ran earlier; alternatively an implementation resets the peak opportunistically and passes a differently interpreted criterion.  
Proposed change: Reset and sample peak memory around each synchronized P2 call only, define which inputs/outputs and rotations are baseline-live, and separately assert that no K/V-sized tensor is materialized.

P9  
Location: `spec.md:79-90`  
Severity: major  
Evidence: hypothesis  
Problem: The long-context reference workload can perturb the timing it is meant to validate. The specification does not order checkpoint timings, multi-GB reference creation, cache clearing and idle/thermal gating.  
Concrete failure scenario: Exact 260K references execute immediately before P2 timings, leaving the GPU hot and allocator state changed; reversed arm order does not remove this bias.  
Proposed change: Run timed arms before checkpoint accuracy, or separate accuracy and timing processes. Compute references head-by-head and release them before any timed phase.

P10  
Location: `spec.md:80-86, 107-110`  
Severity: minor  
Evidence: confirmed  
Problem: The planted controls are underspecified. N1 is not guaranteed to fail unless KV heads have distinct signatures; N3 requires `q_offset≥1`; and N2/N3 generally need separate fixtures.  
Concrete failure scenario: Identical planted KV heads make `_kv_head_shift=1` output-identical, or N3 is invoked at offset zero and fails the interface assertion instead of testing masking.  
Proposed change: Define deterministic, head-distinct fixtures, separate leak/drop cases, sentinel values and valid nonzero offsets.

P11  
Location: `spec.md:92-102`  
Severity: major  
Evidence: confirmed  
Problem: The projection formula does not define `f` dimensionally and does not say whether native16 append already remains inside the residual. If `prefill_s` is end-to-end, subtracting only native attention and then adding full TQ4 append double-counts cache append work.  
Concrete failure scenario: P2 projections include both the baseline native append and TQ4 append, materially overstating projected TQ4 prefill time across hundreds of chunks.  
Proposed change: Give the complete formula, including division by baseline token count, chunk endpoints and interpolation. Subtract native attention and native append from the baseline, then add the selected arm’s attention and append—or add only the append delta.

P12  
Location: `spec.md:91-102`  
Severity: minor  
Evidence: confirmed  
Problem: Timing scope and pass compatibility are incomplete. It is unclear whether `p2_tq4` includes query preparation and inverse rotation, and the report need not reject passes with different `BK/P/WN` metadata.  
Concrete failure scenario: Kernel-only P2 timing is compared with end-to-end P1, or two passes using different tilings are averaged into one result.  
Proposed change: Time the complete public function for headline ratios, optionally report kernel-only timing separately, and require identical `meta.p2_kernel` plus a source/dirty-state identifier across passes.

P13  
Location: `spec.md:97-98, 109`  
Severity: minor  
Evidence: confirmed  
Problem: Requiring exactly six controls exceeds the goal and makes additional valid controls invalidate A3.  
Concrete failure scenario: An implementer adds a useful NaN-tail or fragment-mapping control and the report declares A3 false solely because seven controls exist.  
Proposed change: Require each of the six named controls exactly once, while permitting additional named controls.
