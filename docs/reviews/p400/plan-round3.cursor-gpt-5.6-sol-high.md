# P400 plan — Cursor gpt-5.6-sol-high PLAN review round 3 of 3 (v3, 2026-10-19)

Prompt: `plan-round3.prompt-head.md` + the round-2 output + v3; `--mode ask`, stream-json — the `result` text verbatim:

### Round-2 findings

- **T4 — RESOLVED.** §5 unconditionally marks smoke 8 contaminated for timing and memory, forbids citing its performance evidence, and supersedes it with idle-box new-pin runs. The former operator decision was removed.

- **T6 — PARTIALLY RESOLVED.** §5.3 now specifies ABBA ordering, warmups, repetitions, throughput aggregation, and explicit throughput/memory bounds. However, its memory measurement is taken “after the prefill,” while the changed width-2 verifier executes during decode. See T10.

- **T8 — RESOLVED.** §3 specifies the required three-way `P < L`, `P > L`, and `P == L` algorithm. §4.7 covers 2-D and 3-D full-prompt slicing, equal-length block-local positions, Qwen4 verification, batched offsets, APC, and canonical prefill.

- **T9 — RESOLVED.** §3 explicitly excludes EpiCache from P401, identifies physical versus logical offsets, and assigns the correctness fix and value-level test to P402. This satisfies the alternative requested in round 2.

### New finding

- **T10 — HIGH / BLOCKER — The peak-memory gate does not measure the changed path.**
  
  **Problem:** §5.3 records `mx.get_peak_memory` “after the prefill.” Fix A changes width-2 speculative verification during the subsequent 256-token decode, so that observation cannot detect additional allocations caused by the per-query loop. The plan also does not say when peak tracking is reset or how the ten memory observations are aggregated.
  
  **Concrete failure scenario:** Both pins peak at 80 GB during the 8,192-token prefill. During decode, the old pin requires another 0.2 GB while the new per-query verifier requires another 2 GB. Measuring before decode reports identical peaks and passes the ≤1% bound despite the changed path materially increasing memory.
  
  **Change to plan:** For every measured repetition, complete and synchronize the identical prefill, reset peak tracking immediately before decode, run and synchronize all 256 decoded tokens, and then record the decode-phase peak. Pre-register the across-repetition statistic used for the ≤1% decision—preferably median per-arm decode peak, with maxima also reported—and state how repetitions are pooled across the two A and two B legs of ABBA.

VERDICT: DISAGREE T10
---

Lead: T10 applied in v4 (decode-phase peak after a reset, pooled ABBA statistic); rounds exhausted (C186) — escalated to the operator.
