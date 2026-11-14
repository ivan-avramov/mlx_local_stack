# M80 — change review (four-eyes light, opinion) — ledger

Implementer Claude Opus + one fix round (fresh session), test-writer Claude Sonnet (session continued, three deliveries; verdict
merge). Panel: Sol (`gpt-5.6-sol-high`) and GLM (`glm-5.2-high`), `cursor-agent --mode ask`, read-only snapshot; user instructions
unconfirmed. Raw: `opinion-change-{sol,glm}.md`.

| # | raised by | finding | disposition |
|---|---|---|---|
| 1 | Sol P1 (blocker) | `PYTEST_ADDOPTS` / plugins could deselect every marked test; rc 5 with zero marked accepted | **adopt**: both pytest calls drop the variables and pass `-o addopts=`; marker in the sources + empty listing → FAIL |
| 2 | Sol P2 (blocker), GLM F2 | an unpaired PASS when `../mlx-serve` is absent | **adopt**: always paired; no sibling → refusal before any step (the T3 fixture now provides a sibling) |
| 3 | Sol P3 | the cleaned baseline would mismatch xfails | **decline — refuted**: the real `34a21208` receipt skipped 183 = the 37-entry baseline (xfails included) + the 146 B2 tests |
| 4 | Sol P4, GLM F3 (scope request) | the receipt's pairing is not checked against the stack gitlink at push | **to the operator** (S22-P23, recommended as M81) |
| 5 | Sol P5, GLM F4, implementer P1 | the sibling steps depended on the scratch directory's name | **adopt** (designer erratum: always present; the existing step-order test updated) |
| 6 | Sol P6, GLM F6 | the gate-source change invalidates every receipt | **accept**: every repository is re-gated after M80 (process) |
| 7 | GLM F1 | an xfail marked test would count as passed | **decline — refuted**: pytest records xfail as `<skipped type="pytest.xfail">` in JUnit (checked); an xpass ran and passed |
| 8 | GLM F5 | no test of the real pytest collect-only transcript | **adopt** (a pytest-8-format transcript test) |
| 9 | GLM F7 | `dirty` is not applied to the sibling | **decline**: harmless (the fork scratch is what is checked) |
