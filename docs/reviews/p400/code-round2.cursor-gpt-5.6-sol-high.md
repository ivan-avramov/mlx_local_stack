# P400 code review — round 2 of 3 (Cursor gpt-5.6-sol-high, `--mode ask`), fork `p400-tq-width2` `d4150165..78c9f99d`

Production code is byte-identical across the review range, as required. I’m focusing now on whether the new evidence chain is closed end-to-end: live leaf → census → required positive, and probe leg → loaded tree → measured request → verdict.Production diff verification passed: no non-test `mlx_vlm` changes from `d4150165` to `78c9f99d`.

C2 — High — `dev/p369_phase2/orchestrate.py:809-822`  
Problem: `smoke_positives` remains optional. If the entire field is absent, the gate never checks either the positives or `leaf_census`; existing `_smoke_record()` tests even pass this shape.  
Failure scenario: a worker/reporting regression drops `smoke_positives`; the smoke run still authorizes the full GPU run without any KV-codec positive.  
Fix: require exactly the scheduled T65536 positive block per pick, including its census, and test omission of the whole block.

C3 — High — `dev/p400_perf_probe.py:118-152`  
Problem: the probe records generated-token count but never requires 256 tokens.  
Failure scenario: early EOS produces a shorter, cheaper request—possibly different lengths between arms—yet its throughput and peak enter a passing verdict.  
Fix: require `generation_tokens == 256` and `finish_reason == "length"` for every warmup and measured request.

C4 — High — `dev/p400_perf_probe.py:170-214`  
Problem: arm identity is bound only to a directory path, not a commit or clean tree; identical A/B paths are accepted.  
Failure scenario: both arms load the same commit, or one worktree contains edits, and the probe reports `WITHIN_BOUNDS` as an old-versus-new comparison.  
Fix: reject identical arms; attest and record each tree’s HEAD and cleanliness, validating the expected old/new refs in every leg.

C5 — High — `dev/p400_perf_probe.py:185-190,234`  
Problem: the ten-minute idle rule is bypassable with `--idle-s < 600`, and the default multi-pick run performs no idle between the final leg of one pick and the first leg of the next.  
Failure scenario: residual thermal state biases the second pick while the report still claims every leg was separated by at least ten minutes.  
Fix: reject values below 600 and enforce/record idle time between every globally consecutive leg.

C6 — Medium — `dev/p400_perf_probe.py:77-90`  
Problem: the probe does not call the harness’s `served_state`/`assert_served`; seeing a width-two call does not prove the complete deployed MTP tuple, particularly `joint_v1`.  
Failure scenario: a CLI/overlay regression loses the configured verification policy, but width-two verification still occurs and the measurement passes.  
Fix: record and assert served state after startup for each pick and leg.

C7 — Low — `mlx_vlm/tests/test_p400_tq_width2.py:1-7`  
Problem: the module docstring still states that the uniform model serves TurboQuant, directly contradicting the newly established live affine cache and the cases below. The section heading at `mlx_vlm/tests/test_p369_phase2_observe.py:497` is similarly stale.  
Failure scenario: reviewers misread which case represents live production versus registry intent.  
Fix: describe TurboQuant as the registry-requested case and affine as the currently served P405 case.

VERDICT: NOT CLEARED C2 C3 C4 C5 C6 C7
