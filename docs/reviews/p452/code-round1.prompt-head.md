Cold CODE review — ROUND 1 OF 3 (at most 3 rounds, then the operator decides open findings). The change is in the FORK at
`../mlx-vlm`, branch `p452-qualify-p426`, commits `426ca961` (red test) and `535e20a0` (green) on top of `0b603d03`; read it with
`git -C ../mlx-vlm diff 0b603d03 535e20a0` and `git -C ../mlx-vlm show 535e20a0:<path>`. Context: `docs/open-questions.md`
entry P452 (and C216 once written) in this STACK repo; the stack-side caller `benchmark/bench/p426_plan.py` (M1 leg argv) and
`benchmark/bench/p426_leg.py` (`run_qualify_leg`). Purpose: `dev/p369_phase2/qualify.py` must run as a CHILD of the P426 leg
wrapper (itself a child of the sequencer) on stack S, whose production `mlx_vlm/` carries P426 B1's log-only draft counters;
(1) the quiet-box preflight must not refuse the caller's own ancestors, (2) `--production-ref` names the production tree the
run attests (default the historical pin `7207179b`); the P369-evidence check in `mtp_gate_problems` keeps `7207179b` on purpose.

Review adversarially: (1) can the ancestor exemption let a REAL interfering process through (a benchmark launched by the same
shell, pid reuse, a parent that is itself a refused workload); (2) can `--production-ref` attest the wrong tree (a moving ref,
a branch name, an ancestor check missing, the report recording something other than what was diffed); (3) behaviour for the
existing callers (`orchestrate`'s own campaign, R7) — unchanged?; (4) test quality — would the tests catch a regression of the
Wave-1 failure (real parent / child topology); (5) anything over-built or missing. Findings ids F1 onward (or say none), each:
severity, file:line, problem, failure scenario, fix. End with exactly one line: `VERDICT: AGREE` or `VERDICT: DISAGREE <ids>`.
OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the VERDICT line.
