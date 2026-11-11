P1 — Major — Evidence: confirmed (source trace)

- Location: `SPEC.md` routing table and `decode_attention`; `speculative_verifier.py` per-query fallback; `base.py` TurboQuant dispatch.
- Problem: k>5/gapped verification falls back to singleton calls with sliced key states but the full cache object. The specified D2 interface derives T from `cache.offset`, not the sliced state.
- Failure scenario: For k=6 at T>2048, each fallback query can attend to later draft tokens, corrupting acceptance decisions.
- Proposed change: Pass the effective key length to D2, or use D2 only when `kv_sequence_length(keys) == cache.offset`. Test k=6/gapped fallback above 2048 for bit-identity.

P2 — Major — Evidence: confirmed (source trace)

- Location: `SPEC.md` server/routing goal; `_speculation_fallback_reason` and `PromptProcessingBatch.generate` in `generate/ar.py`.
- Problem: Ordinary non-session server requests use continuous batching, where MTP is explicitly disabled with reason `mtp_batched` and decoding proceeds plainly.
- Failure scenario: Registry and fingerprint report MTP ON, but the requested MMA verification path never runs. A6’s fallback counter can remain zero vacuously.
- Proposed change: Define which server path constitutes the arm. Require draft rounds and successful MMA-call counts in the stack smoke. If continuous batching must speculate, that requires an explicit scope addition and correctness repair.

P3 — Major — Evidence: confirmed (source trace)

- Location: `SPEC.md` “batch 1” scope and `supports`; `BatchGenerator` cache construction in `generate/ar.py`; `BatchTurboQuantKVCache` in `turboquant.py`.
- Problem: Fresh server requests use `BatchTurboQuantKVCache` even at batch 1. The spec only defines prototype-style scalar `cache.offset`; batch caches use array offsets, `_idx`, and left-padding. Layer 63 similarly uses `BatchKVCache`, not the routing table’s `KVCache`.
- Failure scenario: A letter-compliant implementation rejects batch-cache classes, so normal server calls silently bypass the mode; another implementation mishandles `_idx` or padding.
- Proposed change: Explicitly define support for batch-1 batch-cache classes, including physical length, masks and padding, or explicitly route and count them as fallback. Add fresh non-session server tests and successful-path counters.

P4 — Major — Evidence: confirmed (source trace)

- Location: `SPEC.md` layer-63 routing and mlx-serve scope; `ModelConfig._validate_attention_policy` in `mlx-serve/src/mlx_serve/config.py`.
- Problem: mlx-serve rejects `attention_policy: fused_v1` whenever `kv_bits != 0`. The required arm needs `kv_bits: 4`, `tq4_attention: m72_v1`, and `fused_v1` for layer 63. The spec only directs relaxation of `joint_v1`.
- Failure scenario: The intended registry arm fails validation; removing `fused_v1` violates layer-63 routing and changes prefill performance/memory.
- Proposed change: Permit `fused_v1` with TQ4 only when `tq4_attention: m72_v1`; explicitly amend `mtp_verify_scan.require_environment` and define load ordering. Test the complete registry combination.

P5 — Blocker — Evidence: confirmed (source trace and arithmetic)

- Location: `SPEC.md` A5; `m72_e2e_prefill.py`; registry `kv_prealloc_tokens`; `TurboQuantKVCache.update_and_fetch`.
- Problem: A5’s 4.30 GB baseline uses capacity 131,072, while production must preallocate 262,144. Compared with the baseline’s sixteen TQ4 layers, production’s fifteen TQ4 layers plus one native16 layer add approximately 2.98 GB of cache allocation; the cap-sized scratch adds another approximately 0.54 GB. A5 allows only approximately 0.67 GB.
- Failure scenario: An aligned measurement misses A5 by roughly 2.8 GB. Resetting the ledger after production allocation makes the comparison vacuous.
- Proposed change: Rebaseline the dev harness with capacity 262,144 and state exact measurement boundaries, then derive A5 from that matched configuration.

P6 — Major — Evidence: confirmed (specification and source branches)

- Location: `SPEC.md` A1, A4, A6 and R4; decode block selection in `turboquant.py`.
- Problem: Correctness gates stop at 40,960 tokens, while the target starts at 128K. D2 has a distinct >65,536 block tier; MMA’s fixed-512 plan also has materially larger block counts at target context. The ≥128K checks measure only speed or memory.
- Failure scenario: A cap-stride, grid-size, or 512-block-tier defect corrupts target-context outputs while every acceptance gate passes.
- Proposed change: Add p2s/MMA accuracy and D2 bit-identity cases above 65,536 and near 262,144, plus an end-to-end ≥128K output check.

P7 — Major — Evidence: confirmed (source trace)

- Location: D2 exactness requirements; `TurboQuantKVCache.decode_attention`; `TQ_DECODE_2PASS_LEGACY` and `_decode_2pass_num_blocks`.
- Problem: The promoted D2 prototype hardcodes the default production block plan. Today’s singleton can use the public legacy-pass environment switch or a block-count override, changing partitioning and therefore exact results.
- Failure scenario: With legacy decode enabled, D2 uses a different block count from the comparator and violates its bit-identity promise.
- Proposed change: Either mirror the active singleton plan exactly or fail startup when incompatible decode overrides are active. Add corresponding exactness tests.

P8 — Minor — Evidence: confirmed against `SWEEP.md`

- Location: `SPEC.md` block-plan statement and open question 3.
- Problem: The stated “−9–14% at k=3” is approximately −7.8% and −14.3%; the claim that only k=3 was measured is false because the sweep covers k=1, 3 and 5.
- Failure scenario: Later tuning decisions rely on misstated provenance.
- Proposed change: Correct the figures and acknowledge all measured k values.The cold-review task completed; its substantiated findings were already verified and incorporated into P1–P8. No follow-up action is needed.
