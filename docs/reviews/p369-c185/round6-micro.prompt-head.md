Cold CODE review — OPERATOR-SANCTIONED MICRO-ROUND (round 6; tiny diff, confirm or refute). Fork `mlx-vlm`, branch `p369-mtp`,
HEAD `ccac74c4`; your round 5 CLEARED `f0b41d44`. Workspace `../mlx-vlm` at `24551869`; read with `git show ccac74c4:<path>`
(read-only). Production pinned at `4e6d0e03` (diff must stay empty — verify).

What happened: the bound GPU smoke on `f0b41d44` died in the C2 (`e1c_off`) job with `UnboundLocalError: compare` — the P398
change had put `from p369_phase2 import compare` inside `run_job`'s `e1c_pair` branch, making `compare` local to the whole
function; round 4 E8 then used it in the `e1c_off` branch. The diff `f0b41d44..ccac74c4` (inline) hoists the import to the top
of `run_job` and adds an AST guard test (every use of a name bound by a branch-local import must lie inside that block).

Check: (1) the fix is correct and complete (any other name in `run_job` or another worker function with the same hazard?);
(2) the guard test is sound (false negatives that matter?); (3) nothing else changed. Findings ids E11 onward, each: severity,
file:line, problem, failure scenario, fix. End with exactly one line: `VERDICT: CLEARED` or `VERDICT: NOT CLEARED <ids>`.
OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the VERDICT line.
