P1 — Location: `benchmark/bench/p426_plan.py:349-357,469-482,780-804`; `benchmark/bench/p426_wave1.py:186-206`; `benchmark/bench/p426_leg.py:530-549`; `benchmark/bench/p426_harvest.py:114-128`  
Severity: blocker  
Evidence: confirmed, traced in source.  
Problem: A4 and A5 share the same tune. A5’s `reasoning.<tune>.*` glob therefore matches A4 outputs.  
Concrete failure scenario: The default sequence runs A4 smoke before A5 smoke. A5 is refused at its destination pre-check because A4’s `reasoning.m76-<arm>-smoke.*` already exists. Harvest globs would also mix the axes if order changed. Tests use empty result directories and miss this.  
Proposed change: Give A5 an axis-specific tune/stem or use exact per-item paths; test A4 then A5 in one populated results directory.

P2 — Location: missing `benchmark/results/m76/ids.json`; loaded by `benchmark/bench/p426_plan.py:747-750`  
Severity: blocker  
Evidence: confirmed.  
Problem: The required committed Math500/A5 ID record is absent.  
Concrete failure scenario: Every KV Wave-1 leg fails while planning, before launch. The frozen tests expose the absence but the implementer tests exercise only generated in-memory documents.  
Proposed change: Generate and commit `ids.json` from the final B7 report and Math500 universe, then verify it rebuilds and can plan every axis.

P3 — Location: `benchmark/bench/p426_signals.py:1316-1447`; final contract in `docs/specs/m76-b7-statistics.md:160-177`  
Severity: blocker  
Evidence: confirmed, traced in source.  
Problem: Signals do not call B7 v1.4’s decision entry point `m76_rule.axis_verdict(axis, look, a, b)`. They independently call descriptive `paired_delta`/`paired_session_delta` and the older `verdict`, omitting the exact decision interval and blocking `size_warnings`.  
Concrete failure scenario: Final B7 returns UNDECIDED or a blocking size warning while `SIGNALS.md` reports PASS. Tests shim the obsolete API, so they pass by construction.  
Proposed change: Route every mechanical verdict through `axis_verdict`, preserve its alpha, bound, verdict and warnings, and test against the real B7 module.

P4 — Location: `benchmark/bench/p426_wave2.py:48-52,106-133`; `benchmark/bench/p426_verify.py:1804-1860`; `benchmark/bench/p426_signals.py:1656-1677`  
Severity: blocker  
Evidence: confirmed.  
Problem: A7 is hard-coded to s1 and s2; there is no s3 scheduling, verification, panel member or signals path.  
Concrete failure scenario: When `axis_plan("A7")` requires the final s1+s2+s3 look, the candidate declares two sessions complete and computes a verdict from incomplete evidence.  
Proposed change: Add seed-3003 s3 end-to-end and derive required sessions/look from `axis_plan`, refusing incomplete evidence.

P5 — Location: `benchmark/bench/p426_panel.py:1284-1348,1400-1448`; `benchmark/bench/p426_signals.py:1619-1646`  
Severity: blocker  
Evidence: confirmed.  
Problem: KV panel support provides helpers and an eligibility CLI only. It lacks packet export/freeze, judging, sealing and B8/input-hash binding. Signals accept a directory without checking `FROZEN.json`; even a single-family judge set is merely annotated, not refused.  
Concrete failure scenario: Stage 3 cannot produce the required frozen two-family panel through the tool, while a stale or incompletely constituted hand-built panel can affect signals. Tests cover helpers, not the operational workflow.  
Proposed change: Add an end-to-end KV panel CLI bound to B8 and packet hashes, enforce two judge families, seal verdicts, and verify the frozen record in signals.

P6 — Location: `benchmark/bench/p426_verify.py:1667-1704,1764-1784`; `benchmark/bench/tests/test_m76_b3_impl_verify.py:161-164`  
Severity: major  
Evidence: confirmed.  
Problem: Seed-mismatched items enter `keys_rejected`, but the enclosing pair remains `accepted=True`; acceptance depends only on unrelated `reasons`.  
Concrete failure scenario: An A5 row with the wrong request seed yields a B8-accepted pair and signals computes `verdict_a5` on fewer than the planned items. The test checks only that the key is listed as rejected.  
Proposed change: Any rejected planned key must reject the pair, or explicitly make the pair incomplete and prohibit verdict generation.

P7 — Location: `benchmark/bench/m76_ids.py:39,127-167`; `benchmark/bench/p426_plan.py:780-804`; `benchmark/bench/p426_signals.py:1386-1398`; `benchmark/bench/p426_verify.py:1418-1475`  
Severity: major  
Evidence: confirmed.  
Problem: A5 invents a 512-token prompt overhead, records 65,024 rather than the specified 65,536 budget at rung 196,608, and never freezes or verifies actual per-item prompt counts or equality across arms.  
Concrete failure scenario: A retrieval completion that converges between 65,024 and 65,536 tokens is scored non-converged; differing actual prompt lengths can also pass B8.  
Proposed change: Use the specified resolved cap, freeze actual prompt-token counts per item, and require each arm’s count to match and satisfy `prompt_tokens + resolved_max_tokens <= 262144`.

P8 — Location: `benchmark/bench/p426_verify.py:1603-1617`  
Severity: major  
Evidence: confirmed.  
Problem: B8 compares only `manifest.sampling` and selected `manifest.kv` fields, despite the contract requiring fingerprint/provenance equality outside the KV mode. Fields such as fingerprint version, runtime controls, sampling profile and serving-path hashes are ignored. Synthetic tests omit these fields.  
Concrete failure scenario: One arm records a different APC/session-retention runtime or serving-path fingerprint and is still accepted when sampling and non-exempt KV fields match.  
Proposed change: Compare the complete normalized provenance fingerprint with an explicit whitelist for the intended KV/mode and arm-commit fields.

P9 — Location: `benchmark/bench/p426_wave2.py:106-133,1090-1143`; `benchmark/bench/p426_verify.py:1804-1861`  
Severity: blocker  
Evidence: confirmed.  
Problem: Stage-4 Wave 2 cannot run V only, reuse stage-3 X evidence, perform the required sentinel, or derive the free V−N16 comparison. Every sequence runs both named arms and verification reads only one pair-specific sequence.  
Concrete failure scenario: After N16/X stage 3, triggering X/V stage 4 reruns X and still cannot bind V to the existing X and N16 attempts as required. Shared attempt destinations also collide. No tests exercise stage-3-to-stage-4 reuse.  
Proposed change: Add a V-only/reuse workflow, sentinel verification, and cross-sequence dossier binding for V−X and V−N16.

P10 — Location: `benchmark/bench/p426_wave1.py:186-223,260-275`; `benchmark/bench/p426_plan.py:752-769`  
Severity: major  
Evidence: confirmed.  
Problem: Default stage-4 Wave 1 schedules V M1, but V has no documented same-arm stage-2 certification record. Missing `--certified-by` is discovered only when that leg is reached.  
Concrete failure scenario: An X/V sequence spends earlier GPU legs, then fails at V M1 with no valid artifact available under the documented campaign.  
Proposed change: Resolve V’s M1 contract—add an authorized V certification or omit V M1 by specification—and validate all required bindings before launching any leg.

P11 — Location: `benchmark/bench/p426_signals.py:1508-1527`  
Severity: minor  
Evidence: confirmed.  
Problem: Decode speed uses the geometric mean of row-level `decode_tps` ratios rather than P426’s T2 estimator.  
Concrete failure scenario: Unequal completion lengths produce a different reported speed ratio from the pre-registered estimator.  
Proposed change: Reuse the T2 estimator and add a fixture where the two calculations diverge.
