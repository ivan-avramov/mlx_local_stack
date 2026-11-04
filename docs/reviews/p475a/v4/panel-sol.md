P1 — `dev/p369_phase2/qualify.py:651`  
Severity: major  
Evidence: confirmed; reproduced.  
Problem: `forced = rec.get("sdpa_forced") or 0` treats a missing, `None`, negative, NaN, or other falsey counter as zero. The specification requires `sdpa_forced == 0`, not merely “not greater than zero.”  
Failure scenario: Fable AF8/AF4 or any Uniform cell can complete without evidence that forced SDPA calls were zero—for example, when the worker omits `sdpa_forced`.     <!-- allow-shorthand: verbatim reviewer output -->
Proposed change: when the manifest is available, require a present numeric counter; require `> 0` for fused/native and exactly `0` otherwise. Reject malformed or missing values. Add frozen tests using `None`, missing, negative, and NaN counters; current tests cover only `0` and positive integers.

P2 — `dev/p369_phase2/qualify.py:652`  
Severity: minor  
Evidence: confirmed; reproduced.  
Problem: the missing-manifest guard applies only when `fused` is true. With `attention_policy="auto"`, a missing manifest plus positive `sdpa_forced` produces both the manifest problem and a spurious attention problem, contrary to “only the manifest problem.”  
Failure scenario: a Uniform arm record lacking its manifest and reporting `sdpa_forced=3` gets two problems instead of only the manifest failure.  
Proposed change: skip the attention verdict whenever `native_attention is None`, regardless of attention policy. Add a missing-manifest test using the default-attention pick; frozen tests exercise only Fable’s `fused_v1`.   <!-- allow-shorthand: verbatim reviewer output -->
