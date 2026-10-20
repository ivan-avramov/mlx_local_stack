# P400 code review — round 3 of 3 (Cursor gpt-5.6-sol-high, `--mode ask`), fork `p400-tq-width2` `78c9f99d..ce04439b`

Post-review (lead): C8 and C9 fixed as specified, test-first (`d01b1066` red, `abbbfc84` green; dev tool only, production unchanged); escalated to the operator with the rec to accept without a fourth round (C188 precedent).

Production code is confirmed unchanged across `78c9f99d..ce04439b`. The fresh pass has identified one arm-attestation edge case and I’m tracing the KV “served codec” assertion through the actual cache-construction path before deciding whether either is blocking.Production verification passed: `git diff 78c9f99d ce04439b -- mlx_vlm ':!mlx_vlm/tests'` is empty.

Prior findings:
- C2 — Resolved. Smoke requires exactly `T1024` and `T65536`, with positives only on `T65536`; omission tests cover the block and either cell.
- C3 — Resolved. Every warmup and measured request requires 256 tokens, `finish_reason == "length"`, positive throughput, and width two.
- C4 — Not fully resolved. Distinct paths and clean trees are checked, but commit identity remains bypassable; see C8.
- C5 — Resolved. All globally consecutive legs idle, including between picks, and values below 600 seconds are rejected.
- C6 — Resolved in its original scope. Each leg calls `served_state`/`assert_served`, checking drafter, MTP kind, verification policy—including `joint_v1`—and argv KV configuration.
- C7 — Resolved. Documentation now distinguishes registry-requested TurboQuant from currently served affine KV.

C8 — High — `dev/p400_perf_probe.py:97-107`  
Problem: Commit identity uses `got["head"].startswith(ref)`, while distinctness compares the unresolved ref strings. Different spellings or prefixes resolving to the same commit therefore pass as different arms.  
Failure scenario: Two distinct worktree paths both at `ce04439b…`, with refs `ce04439b` and the full SHA, produce no problems. The probe can report `WITHIN_BOUNDS` for same-commit versus same-commit. An empty ref also matches every HEAD.  
Fix: Resolve both refs to full commit IDs, compare each HEAD by equality, and require the resolved IDs to differ. Add prefix/full aliases of one commit as a regression case.

C9 — Medium — `dev/p400_perf_probe.py:55-82`  
Problem: Request and verdict validation do not reject non-finite throughput or non-positive peak measurements. Consequently invalid telemetry can satisfy both bounds.  
Failure scenario: `tps=inf`, 256 tokens, `finish_reason="length"`, and width two passes `request_problems`; ten such B samples yield `tps_regression=-inf` and `WITHIN_BOUNDS`. A zero B peak similarly appears as a 100% improvement.  
Fix: Require finite positive `tps` and `decode_peak` per request, then defensively reject non-finite or non-positive aggregate inputs and ratios in `verdict`. Test zero, negative, NaN, and infinity.

VERDICT: NOT CLEARED C8 C9
