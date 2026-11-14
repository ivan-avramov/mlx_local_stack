P1
- Location: `mlx_local_stack/benchmark/bench/local_gate.py:304-306,419-432`; `test_m80_impl_gate.py:317-319`
- Severity: blocker
- Evidence: confirmed, traced in source.
- Problem: Both pytest runs inherit `PYTEST_ADDOPTS` and plugins; rc 5 with zero marked tests is accepted.
- Failure scenario: `PYTEST_ADDOPTS="-k 'not m76_b2'"` deselects all 146 marked tests from both runs. The receipt can PASS with `requires_mlx_serve_tests: 0`, and pre-push accepts it.
- Proposed change: Clear `PYTEST_ADDOPTS`/`PYTEST_PLUGINS`, override configured `addopts`, reject deselection, and require the expected marked-test set. Add a real-environment regression test.

P2
- Location: `local_gate.py:445-448,461-462`; `test_m80_impl_gate.py:250-270`
- Severity: blocker
- Evidence: confirmed; candidate tests explicitly require this behavior.
- Problem: Missing `../mlx-serve` permits an unpaired PASS with `paired: {}`, contrary to the Goal and pinned-pairing requirement.
- Failure scenario: An older fork SHA without these markers—or a future commit accidentally removing them—passes without cloning mlx-serve; pre-push accepts the receipt.
- Proposed change: Always resolve and validate the sibling pin for mlx-vlm runs. Remove the unpaired path and update affected fixtures to provide a sibling.

P3
- Location: `IMPLEMENTER-REPORT.md:12-17`; `benchmark/gate/mlx-vlm.skips.txt`; `local_gate.py:500-526`
- Severity: blocker
- Evidence: hypothesis, based on the reported exact suite result and source trace.
- Problem: The reported suite produced 18 skipped plus 22 xfailed testcases, while the cleaned baseline has 37 entries. Pytest JUnit normally represents xfails as skipped, implying 40 JUnit skips and an immediate baseline mismatch.
- Failure scenario: The real gate finishes pytest successfully, then emits `skip list != baseline`, writes FAIL, and pre-push refuses it.
- Proposed change: Run the exact gate with JUnit, inspect the three additional IDs, then either make them run or add reviewed baseline entries. Add an end-to-end JUnit test.

P4 — scope request
- Location: specification lines 27-33; `local_gate.py:566-573,609-632,657-665`
- Evidence: confirmed.
- Problem: Pairing may become stale by explicit design: neither receipt lookup nor stack gitlink checks compare `paired["mlx-serve"]`. The stack gate runs stack tests, not the fork’s marked suite.
- Failure scenario: Fork F passes against serve A; a later stack pins F with serve B. Separate receipts satisfy pre-push although F’s marked tests never ran against B.
- Proposed change: If exact-pair protection is desired beyond this specification, require the fork receipt’s paired SHA to match the stack gitlink.

P5
- Location: `local_gate.py:182-212`; `test_m80_fe_gate_sibling.py:113-136`
- Severity: minor
- Evidence: confirmed; three frozen tests fail.
- Problem: `steps_for("mlx-vlm", …)` silently depends on the scratch basename being `mlx-vlm`, an extra interface rule absent from the specification.
- Failure scenario: A direct caller using `/tmp/scratch` receives no sibling steps.
- Proposed change: Make pairing explicit and mandatory, independent of pathname, or make sibling steps the mlx-vlm default.

P6 — scope request
- Location: `local_gate.py:87-93,371-376,566-573`
- Evidence: confirmed.
- Problem: Stack/mlx-serve step lists and pre-push levels remain unchanged, but all their existing receipts become stale because every repository digest hashes the complete modified gate source.
- Failure scenario: The next stack or mlx-serve code push is refused until that unchanged gate is rerun.
- Proposed change: Document the required regating; if receipt continuity is required, introduce repository-specific policy-source digests.
