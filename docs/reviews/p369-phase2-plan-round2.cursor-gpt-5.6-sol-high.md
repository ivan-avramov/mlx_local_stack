Q15 — CLOSED — §2.2 Rows now compares position 0 and every output-relevant verifier row, excluding only unreachable post-rejection rows.

Q16 — NOT CLOSED — §2.2 State observes every commit, but ordinary commits compare only two 32-bit partial digests. That neither covers the complete valid state nor establishes exact equality; see Q28.

Q17 — CLOSED — §2.2 Reference isolates forcing to OFF, asserts drafter engagement correctly, and compares canonical post-transform distributions rather than raw-logit deltas.

Q18 — NOT CLOSED — §2.2 narrows dense-kernel scope correctly, but the proposed inventory and spies cannot yet prove which runtime kernel actually succeeded; see Q29.

Q19 — CLOSED — §2.2 constructs and verifies post-template lengths, records actual verifier key lengths/classifications, requires real boundary coverage, and invalidates early termination.

Q20 — CLOSED — §§1, 2.1 correctly limit the claim to worker conformance, sanitize subprocesses, and assert source paths, backend, APC and drafter state.

Q21 — CLOSED — §3 correctly labels C84-item reconstruction, pins builders/datasets, records token hashes and fails missing or length-inconsistent reconstruction.

Q22 — NOT CLOSED — §3 requires positive rounds and the greedy hooks, but exact quantized-argmax dispatch remains unproven because of the alias/spying issue in Q29.

Q23 — NOT CLOSED — §2.3 now defines the three predicates correctly. The remaining “run against `88724023` behaviour” step is not implementable merely by wrapping current code; see Q30.

Q24 — NOT CLOSED — §3 fixes censoring and moves incidence to requests, but E7b can create invalid tool histories and `cached_tokens > 0` is insufficient evidence of continuity. Its repeated requests are also session-clustered; see Q31 and Q33.

Q25 — CLOSED — §§2.4, 4 add the required lock, process/port checks, watchdogs, atomic status, cleanup checks and a substantially larger GPU reservation.

Q26 — CLOSED — §5 makes ordinary tests fixture-deterministic and moves live C177 comparison to an explicit integration test with a narrowly defined normalization.

Q27 — CLOSED — Status and §2 pin production to `4e6d0e03`, separate harness provenance, refuse production diffs and record the relevant executable/module/artifact paths.

Q28 — BLOCKER — §2.2 State exactness and cost  
Problem: Two linear 32-bit MAC digests are collision-prone, and hashing only newly written KV misses corruption of an older valid prefix or metadata. Periodic SHA-256 does not repair the unchecked ordinary commits. Consequently E1c can pass without establishing Q12 state equality. Probe forwards are feasible through `_MTPVerifyResult.abort()`, but add approximately one singleton target decode per commit; synchronization and hashing may dominate the stated estimate.  
Fix: At every commit hash a canonical byte stream of the complete logical valid state using SHA-256/BLAKE3: cache type, offsets, valid lengths, shapes/dtypes, all valid packed/native K/V components, TurboQuant codec metadata, and every recurrent component. Hash in bounded chunks and never include preallocated tails. Compare full probe logits bitwise and prove each probe is observationally neutral with before/after state hashes. Calibrate this at 65,536 during smoke and revise the wall estimate before the full run.

Q29 — HIGH — §§2.2, 3 Kernel inventory and spies  
Problem: Weight types establish potential eligibility only. Actual dispatch also depends on activation shape/dtype, device and which nested helper returns non-`None`. `qwen3_5/speculative_verifier.py` imports several `_target_verify_*` functions by value, while `_target_verify_quantized_{linear,argmax}` themselves dispatch among optimized, NVFP4, singleton and fallback paths. Spying only the named `speculative.ops.linear` wrappers can miss bound aliases or count a wrapper whose optimized kernel returned `None`.  
Fix: Keep the offline manifest as expected eligibility, but make runtime outcome telemetry authoritative. Instrument every consuming alias and nested implementation, count only non-`None` results, record module/shape/dtype, and classify every projection call exactly once. Require expected successful families, positive verifier/argmax calls per ON request, and zero unclassified or forbidden fallbacks. Gate the full campaign after this GPU smoke inventory reconciles with the static manifest.

Q30 — HIGH — §2.3 Historical E7 oracle  
Problem: Current-code wrappers can classify M4a/M4b/M3 traces, but they do not execute pre-fix behaviour and can encode the same mistaken interpretation as the classifier. M4b also spans `speculative/utils.py` and the generation consumer, not only `_mtp_rounds`.  
Fix: Run a self-contained external regression test against an isolated `88724023` tree and then `0b43dae4`, or execute SHA-pinned verbatim historical implementations. Require each scripted case to exhibit its precise old defect and its fixed outcome. Use current wrappers only for live event observation.

Q31 — HIGH — §3 E7b continuity  
Problem: A newly generated assistant turn may contain different tool calls or call IDs—or none—so appending recorded tool results can produce an invalid conversation. Moreover, `cached_tokens > 0` can represent reuse of only an early system/user prefix, not continuity through the generated assistant turn.  
Fix: Continue only protocol-compatible turns: execute the generated tool calls and append their actual results/IDs, or mark the session censored when that cannot be done. Assert reuse reaches the expected token boundary through the previous generated assistant turn and that the session/hash chain is the intended one.

Q32 — MEDIUM — §3 Smoke mutation  
Problem: A one-ULP raw-logit change may affect a filtered-out token, be rounded away by normalization, or leave post-transform probabilities unchanged. Requiring that mutation to trip the final comparator is not reliable.  
Fix: Test one-ULP sensitivity at the raw-logit recorder. Separately inject a precomputed in-support perturbation guaranteed to alter a retained transformed probability or support boundary.

Q33 — MEDIUM — §3 E7 statistics  
Problem: E7b contributes multiple correlated requests from only two sessions per pick. Pooling them into request-level Clopper–Pearson intervals still assumes independent Bernoulli trials and overstates precision.  
Fix: Report E7a and E7b separately. Keep request-level intervals only for independent E7a requests; report E7b descriptively by session or use a session-clustered bound, with censored sessions explicit.

VERDICT: DISAGREE Q16,Q18,Q22,Q23,Q24,Q28,Q29,Q30,Q31,Q32,Q33No follow-up needed; the completed reviews reinforce the issued findings.
