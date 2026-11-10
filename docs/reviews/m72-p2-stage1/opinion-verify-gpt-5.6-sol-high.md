P1 — Design finding 1: resolved. `m72_p2s_report.py:attn_s/projection` converts attention and append milliseconds to seconds.

P2 — Design finding 2: resolved. Projection uses the existing `interp`, pins append data to T=260,096 and two-pass means, and has hand-calculated synthetic tests.

P3 — Design finding 3: resolved in source. The kernel emits cap-sized scratch arrays; the separate instrument includes growing-T and OS-ledger scenarios. Full-scale evidence remains absent under P19.

P4 — Design finding 4: resolved in source. Chain16 measures both one lazy graph and mandatory per-layer evaluation.

P5 — Design finding 5: resolved. fp16 is the default scratch dtype; bf16 remains optional.

P6 — Design finding 6: resolved. References take explicit T and the sweep records K/V fidelity.

P7 — Design finding 7: not fully resolved.
- Location: `material/candidate/stack.diff`, `P2S_PLANT_SCALE` and `fill_cache`
- Severity: minor
- Evidence: confirmed
- Problem: N1 uses random values scaled per head, not the specified distinct constants.
- Failure scenario: a different random realization weakens head separation and makes the control seed-dependent.
- Proposed change: plant deterministic, widely separated per-head values while retaining the unshifted positive control.

P8 — Design finding 8: resolved. Dequantization identity gates fidelity; full-path identity is diagnostic only.

P9 — Design finding 9: resolved. A4/A5 naming is corrected and rows above `--max-t` are explicitly listed as skipped.

P10 — Design finding 10: resolved as correctly declined. Candidate and reference both pass rotated `qr` to SDPA.

P11 — Design finding 11: resolved in source. The memory instrument has a resident pre-dequantized SDPA-only baseline. Its result remains unverified under P19.

P12 — Design finding 12: resolved. Both codebooks remain fp32 through the multiplication, followed by one output rounding.

P13 — Design finding 13: resolved. Bottom-right causal alignment for L<T is stated and exercised.

P14 — Design finding 14: resolved. The fp32 reference handles one KV/query head at a time and clears cached intermediates.

P15 — Design finding 15: resolved behaviorally. Full-cap state arrays are passed unsliced and sentinel-past-T tests pass when the frozen tests are overlaid.

P16 — Design finding 16: resolved. The implementation retains the codec’s D=256 query/output RHT operations.

P17 — Design finding 17: not resolved.
- Location: `material/candidate/stack.diff`, `m72_p2s_report.py:load/provenance_mismatch`
- Severity: major
- Evidence: confirmed
- Problem: the report accepts a single pass; complementary arm orders are checked only when exactly two runs happened to load.
- Failure scenario: after pass 2 fails, pass 1 alone emits official-looking tables and a projection without counterbalancing or two-pass averaging.
- Proposed change: require exactly `p2s-1.json` and `p2s-2.json`, then require one forward and one reverse order.

P18 — Design finding 18: resolved. Dequant-only timing is explicitly identified as diagnostic.

P19 — Full-cap acceptance has not been demonstrated.
- Location: `material/implementer-report.md:12-39,60-74`; `material/testwriter-2-report.md:51-56`; spec A4
- Severity: blocker
- Evidence: confirmed that checks are absent; full-cap runtime behavior remains a hypothesis
- Problem: no real 260,096 two-pass projection, 262,144 checkpoint/chain16, or full A4 memory run exists. The reported 32K smoke was also CPU-contaminated.
- Failure scenario: cap-scale buffer retention, chain scheduling, or performance could fail while every reduced smoke remains green.
- Proposed change: run the two-pass launcher on an idle M5 Max through cap, generate the report, and run every fresh-process `--impl p2s` A4 scenario with both instruments and known positives.

P20 — The sweep can incorrectly pass A1.
- Location: `material/candidate/stack.diff`, `m72_tq4_probe.py:p2s_a1_all`
- Severity: major
- Evidence: confirmed
- Problem: maximum candidate and production errors are taken independently across heads, then compared.
- Failure scenario: one head has candidate/production errors 0.006/0.001 while another has 0.004/0.004; the aggregate passes against 0.004 although the first head violates its own bound.
- Proposed change: set the aggregate result from `all(a["pass"] for a in per.values())`; retain maxima only for display.

P21 — A6 fails in the delivered candidate.
- Location: candidate diffs; `material/implementer-report.md:64-70`
- Severity: major
- Evidence: confirmed
- Problem: the required tests, parser-test amendment, and `stack.skips.txt` entry are outside the candidate diffs; the existing parser test consequently fails, and the clean-clone suite was not completed.
- Failure scenario: applying only the candidate leaves CI red and omits the specified regression protection despite the frozen tests passing when separately overlaid.
- Proposed change: integrate the frozen tests, amended MMA parser test, and skip entry, then run the clean-clone gate.

P22 — The documented dependency memory scenario is ineffective for p2s.
- Location: `material/context_memory_spike.py:159-166,247-254`
- Severity: minor
- Evidence: confirmed
- Problem: the p2s dequant wrapper ignores `dep`, so `fwd_dep` does not attach dequantization inputs to the preceding query as documented.
- Failure scenario: `fwd_dep` behaves like `fwd_lazy` and cannot diagnose the intended scheduler-lifetime distinction.
- Proposed change: dependency-wrap the state arrays passed to the kernel without mutating the state NamedTuple.
