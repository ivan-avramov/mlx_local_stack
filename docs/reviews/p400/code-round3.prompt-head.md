Cold CODE review — ROUND 3 OF 3 (the LAST round; afterwards open findings go to the operator). Fork `mlx-vlm` branch
`p400-tq-width2` HEAD `ce04439b`; your round 2 (inline below) returned NOT CLEARED C2–C7 on `d4150165..78c9f99d`. Workspace
`../mlx-vlm` at `24551869`; read with `git show ce04439b:<path>` (read-only). Diff `78c9f99d..ce04439b` inline below
(`2f14e7af` red tests, `ce04439b` fix). Production code is UNCHANGED (`git diff 78c9f99d ce04439b -- mlx_vlm
':!mlx_vlm/tests'` must be empty — verify). Fork suite on `ce04439b`: 6470 passed / 17 skipped twice, skips identical; eight
audits green.

First verify each of C2–C7 is resolved (say so per id, with the evidence), then review the diff afresh for anything that
weakens a claim (a gate that passes without its evidence, a probe statistic / bound / arm binding that can be bypassed) or a
test that does not prove what its docstring says. Only findings that must be fixed before the `Qwen3.8-27B-mlx-uniform-4bit`
re-certification GPU runs should block.

Findings ids C8 onward, each: severity, file:line, problem, failure scenario, fix. End with exactly one line:
`VERDICT: CLEARED` or `VERDICT: NOT CLEARED <ids>`. OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the
VERDICT line.
