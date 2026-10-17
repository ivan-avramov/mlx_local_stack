W1 — Medium — `benchmark/bench/compare_predictor.py:370-381`, `benchmark/bench/tests/test_compare_predictor.py:414-420`: a shown loss whose lower bound is exactly −5 pp fails, contradicting the ≤5 pp lossy-lever rule. Floating-point noise also changes the verdict. Use an inclusive tolerance-aware comparison and correct the test.

W2 — High — `benchmark/results/p359_wash/scripts/rerun_jg.py:31-34`: regrading `judge_c_v1/ranking.json` drops the original `usage` block, losing tokens/task, latency, runaway share, and n. Preserve it; outputs are not currently byte-identical apart from labels.

W3 — Medium — `AGENTS.md:59`, `benchmark/bench/stats.py:254-255`: authoritative guidance still mandates the superseded MDE guard, while production correctly uses C173’s observed-loss bound. Update both directives to prevent reintroducing the wrong guard.

W4 — Medium — `docs/campaign-results.md:425-428,470,507,529,1006,1015`: paired results remain labelled “inconclusive” or “tie,” contradicting C172 and `P359_AUDIT.md:46`. Relabel as wash with MDE and directional qualification.

W5 — Medium — `README.md:58,72`, `docs/campaign-results.md:1276,2404`: phrases such as “tie within,” “show no difference,” and “legitimate no-difference reading” imply equality. Use “did not show a difference,” with the actual interval/MDE and directional pick.

W6 — Medium — `benchmark/bench/agentbench_compare.py:36,390-392,493`, `benchmark/bench/judge_gate.py:418-422`, `benchmark/run.py:350-351,511`: production help and generated reports still claim TOST/equivalence semantics although margin no longer drives verdicts. Remove or explicitly mark the compatibility-only parameter as decision-inert.

W7 — Low, non-blocking — `benchmark/bench/tests/test_compare_predictor.py:423-445`: C173 boundaries mostly test `_verdict` directly, not `compare_predictor()`. Add production-path coverage for −10 pp, n=28/29 zero-discordance, and OFF-advantage boundaries.

W8 — Low, non-blocking — three generated AgentBench Markdown files have extra blank lines at EOF.

Verified: −10 pp is inclusive; zero-discordance n≤28 blocks and n≥29 ships; tiny n fails safely; OFF advantage beyond −5 pp still fails; `main_models.yaml` values are unchanged; CERTIFIED formatting remains; no PII or private absolute paths were added.

VERDICT: CLEARED AFTER FIXES W1 W2 W3 W4 W5 W6Focused semantic tests passed successfully. No follow-up action is needed; the review findings and verdict remain unchanged.
