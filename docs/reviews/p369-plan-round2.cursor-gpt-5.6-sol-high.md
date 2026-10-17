P1 — Round-1 closure
- Q1: Partially resolved. Hybrid/quantized fixtures and per-pick conformance were added, but E1c omitted Q1’s target cache/recurrent-state comparison. See Q12.
- Q2: Resolved in intent; Q11 is needed to make exact enumeration operational.
- Q3: Resolved, subject to the policy-specific correction in Q13.
- Q4–Q10: Resolved as requested.

P2 — Feasibility conclusions
- E1a is feasible through `generate_step`, but not by enumerating RNG seeds. It needs the branch-forcing harness specified in Q11.
- E1b is feasible without production changes. Supplying `seed=` selects `_PositionedTargetSampler`; plain and MTP sampling already use identical `(seed,row,position)` keys. The deployed transforms are supported.
- E1c requires test-only observation instrumentation, but no production-source hook. Existing M58 AB instrumentation compares attention tensors, not post-transform verifier distributions.

P3 — New findings

Q11 — blocker — Define the E1a exact enumerator

The production path returns sampled outputs, not joint probabilities. “Enumerate the exact joint law” is therefore underspecified and could become seed enumeration or a separate speculative-decoding implementation.

Specify a test sampler that:
- reuses `_PositionedTargetSampler._filter`;
- forces each candidate token by emitted position;
- records its exact `softmax(filtered_logits / temperature)` conditional mass;
- reruns clean ON/OFF state for every prefix in the finite support;
- uses deterministic scripted low/high-acceptance drafters.

This preserves `generate_step`, verifier, acceptance, and transaction code while replacing only categorical selection. E1b separately validates the real position-keyed categorical draw.

Q12 — high — Restore Q1’s production-state conformance

E1c compares transformed logits only, while round 1 also required cache-state conformance. Add per-pick comparison after each commit of:
- cache offsets and valid KV prefixes;
- recurrent/GDN state;
- next-step singleton logits.

Do not compare unused preallocated cache tails. E3’s stop-specific state checks do not cover general real-weight rollback/commit behavior.

Q13 — high — Specify the E1c observer and policy-specific assertions

At T > 0, `_mtp_rounds` requests hidden states and `_positioned_target_tokens` projects and samples internally; no API exposes post-transform verifier distributions. Add a test-local wrapper around `_mtp_verify_target`/`speculative_logits_from_hidden` that records inputs and outputs while returning values unchanged. Sequential clean replays are preferable to cloning 262K-preallocated real caches.

Also distinguish the picks:
- Fable: native KV, `joint_v1`; assert straddle counters.
- Uniform: TurboQuant KV, registered `per_query`; `joint_v1` is explicitly refused when `kv_bits > 0`, so joint/straddle counters cannot be required. Record externally verified boundary lengths and per-query/TurboQuant routing instead.

Q14 — non-blocking — Assert branch coverage explicitly

Quantization alone does not prove both `quantized_verifier` and dense `exact_speculative_verify` kernels executed. Use branch spies/counters and ensure tiny dimensions satisfy affine group-size/kernel eligibility.

VERDICT: AGREE WITH CHANGES Q11 Q12 Q13
