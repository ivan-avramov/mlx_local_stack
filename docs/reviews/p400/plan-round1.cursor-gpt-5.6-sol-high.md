# P400 plan — Cursor gpt-5.6-sol-high PLAN review round 1 of 3 (`docs/specs/p400-tq-width2-fix.md` v1, 2026-10-19)

Prompt: `plan-round1.prompt-head.md` + the v1 plan; workspace `../mlx-vlm` at `24551869` (code read at `3a92943d`); `--mode ask`, stream-json — the `result` text verbatim:

P1 — The first material gap is already visible: `_attention` is not Qwen3.5/Qwen4-only. Gemma4 and Nemotron-H inherit the same width-2 branch, so option A’s stated blast radius and validation matrix are incomplete. I’m checking whether their overrides constrain or bypass that path, plus batch/left-padding dispatch and whether the proposed red tests truly enter `decode_attention` after the change.A is the right fix for the observed single-sequence TurboQuant defect, but the plan currently overstates its completeness.

### T1 — BLOCKER
Problem: A is not “exact by construction” for left-padded `BatchTurboQuantKVCache`. Singleton decoding converts `"left_padded_decode"` to `mask=None`; the ragged helper then declines caches with `bits`, leaving quantized fallback attention unmasked. A multi-token verifier instead receives an explicit mask from `BatchTurboQuantKVCache.make_mask`, and A preserves slices of that mask.

Concrete failure scenario: With B > 1 and one left-padded row, ordinary singleton decoding can attend padded keys while an MTP/DFlash verification block excludes them. ON/OFF rows can therefore differ after A for width 2 or wider.

Change to plan: Before implementation, characterize this case with a B=2 left-padded TurboQuant test. Either fix the singleton left-padding path in P400, or explicitly scope P400 to unpadded B=1 and record the batch defect separately. Remove the global “exact by construction” claim until resolved.

### T2 — HIGH
Problem: The proposed E1a/E1c matrix is underspecified and partly inconsistent. E1a enumerates a joint law and has no meaningful generation-seed dimension; token, row, and state equality are E1b/E1c assertions. Additionally, current E1c helpers identify only a literal `KVCache`; the existing corruption test will raise `StopIteration` after the uniform pick starts using TurboQuant.

Concrete failure scenario: Tests fail in fixture plumbing rather than at the width-2 assertion, or silently remain on native KV and pass without reproducing P400.

Change to plan:
- E1a: deterministic law comparison with an asserted width-2 verifier round.
- E1b: paired token identity across seeds.
- E1c: rows and complete logical state across selected lengths/seeds.
- Assert the actual cache class, codec, bit width, and observed verifier width.
- Adapt `_kv_leaf` and packed-state corruption for TurboQuant.
- Make the direct test compare independent block and sequential caches, including final cache state, and prove pre-fix L=2 uses the multi-query path while post-fix uses singleton calls.

### T3 — HIGH
Problem: The Fable full-run carryover rationale is insufficient. `joint_v1` bypasses A only for eligible blocks. For `per_query` fallback decisions, the policy returns `None`, so a fallback width-2 block reaches the branch A changes. A smoke pass does not prove the completed full workload never used that path.

Concrete failure scenario: The old full run contains width-2 fallback blocks because of mask, domain, or other eligibility failures. The new pin changes their execution and performance, but a shorter smoke never encounters them.

Change to plan: Carry the old full evidence only if its telemetry proves `verify_blocks_per_query == 0`—joint and policy-served straddle blocks are unaffected. Otherwise rerun the Fable full certification, or obtain an explicit operator waiver backed by targeted fallback-width-2 correctness and performance evidence.

### T4 — HIGH
Problem: A new worktree isolates files, not the Metal GPU. Running targeted Metal fixtures during the live full run can perturb timing, peak memory, scheduling, or cause resource failure.

Concrete failure scenario: The in-progress Fable run completes with degraded throughput or altered memory evidence because fixture kernels ran concurrently, making that full-run evidence unsuitable for carryover.

Change to plan: During the live run, permit implementation and CPU/static checks only. Run no Metal tests until it finishes. If any GPU tests have already overlapped, treat the run as contaminated and rerun it.

### T5 — MEDIUM
Problem: The affected-path description needs a precise model/drafter map. Qwen4 inherits `_attention`, but its sparse QSA width-2 path uses `dispatch_qsa_attention` and is unaffected by A; TurboQuant is currently unsupported for QSA auxiliary state. Gemma4 and Nemotron-H override `_attention`. Conversely, Qwen3.5 DFlash, EAGLE, and suffix verification can all reach this exact verifier, so A is not MTP-only.

Concrete failure scenario: Reviewers incorrectly conclude that A establishes TurboQuant exactness for future Qwen4 sparse verification, while omitting regressions in non-MTP Qwen3.5 verification.

Change to plan: Add this dispatch map. Run the existing Qwen4 block-2/sparse-boundary exactness test as a regression, and state that the route-level Qwen3.5 TurboQuant test covers all Qwen3.5 drafter types.

### T6 — MEDIUM
Problem: A remains preferable to B/C, but its performance claim is unmeasured. Width-2 can be a sustained adaptive size, not merely a terminal round, and the change occurs in every full-attention layer. On TurboQuant it replaces one prefill-style invocation with two decode invocations.

Concrete failure scenario: Exactness is restored but width-2-heavy traffic suffers a material throughput regression that the correctness-only smoke accepts.

Change to plan: Add a representative-prefix width-2 microbenchmark and a throughput/peak-memory comparison in both regression smokes, with an explicit acceptable regression bound. Keep A preferred because it restores the verifier’s singleton-equivalence contract; B preserves an accidental native-KV property and C has excessive kernel blast radius.

### T7 — LOW
Problem: Validation omits formatting and test-collection checks.

Concrete failure scenario: New parametrized tests are not collected as intended, or autoflake changes imports after the reviewed test run.

Change to plan: Run the pinned formatting hooks on touched files and compare `pytest --collect-only` counts before the final full suite and audits.

VERDICT: DISAGREE T1 T2 T3 T4