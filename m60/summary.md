# M60 generation summary — Qwen3.8-27B-Fable-Distill-OptiQ-4.5bpw-mixed @ m60ship

- Math500 `acc_strict@81920`: new 0.980 vs `m40on` 0.990; delta -0.010 CI95 [-0.050, +0.020], n=100, MDE ±0.125; new-only wins 1, `m40on`-only wins 2 -> **INCONCLUSIVE**
- descriptive vs `m37med`: delta +0.010 [-0.020, +0.050]
- Math500 non-converged 0/100 (red flag at >= 3): {}
- cjudge: converged 40/40, shared converged with `m40on` 40; token-length ratio 1.0697 (band [0.8, 1.25], in band: True); ready for the judge pass: True
- decode tok/s mean: math 45.83, cjudge 35.44 (descriptive; power ok on every tick: True)
- MTP acceptance pooled: math 0.7623, cjudge 0.6133
- counters: math {'verify_blocks_joint_v1': 1067200, 'verify_blocks_per_query': 0, 'verify_blocks_straddle': 864, 'verify_blocks_len1': 0, 'verify_blocks_straddle_len2': 0, 'verify_fallback_reasons': {}, 'sdpa_forced': 240, 'sdpa_auto': 2976}

Judge pass: see JUDGE.md (no GPU). No registry, pick or order change is made by this script.
