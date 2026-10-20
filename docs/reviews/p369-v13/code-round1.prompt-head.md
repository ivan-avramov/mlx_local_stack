Cold CODE review — ROUND 1 OF 3 (at most 3 rounds, then the operator decides open findings). Fork `mlx-vlm` branch
`p369-v13` HEAD `5f407d5d`, on top of the reviewed P405 head `64afc7dd`. Workspace `../mlx-vlm` at `24551869`; read with
`git show 5f407d5d:<path>` (read-only). Diff `64afc7dd..5f407d5d` inline below, then the operator-accepted P369 run plan v13
(`docs/specs/p369-phase2-run-plan.md`, C193; V17's wall cap withdrawn by C194). Production code is UNCHANGED
(`git diff 64afc7dd 5f407d5d -- mlx_vlm ':!mlx_vlm/tests'` must be empty — verify): this is the dev harness + tests for the
v13 build — the 16-state registry generator (V5 / V10), the four-entry PICKS + one-entry campaigns + argv scan check (V9 /
T15), pinned target / drafter files (V6 / V11), loaded-drafter assertions (V11 / V12), the borrowed panel + count-only
`--phase panel` (V4; a refinement — the counts are produced by a count-only worker boot that loads weights but generates
nothing, reviewed into the fixture before the entry's smoke), the phase-based projection (V13), MoE observability (V3 /
V15: routed banks in the manifest and telemetry, the drafter's draft-scope MoE inventory, smoke-gate requirement), the
qwen3_next split-path characterization (V12 / V14: the adversarial nested qwen3_next source is refused by strict load) and
the V3 (d) width-2/3 vs singleton bitwise MoE test. NOT YET RUN: the Metal-dependent tests (test_p369_phase2_moe.py b / c /
d / e, test_p369_phase2_worker.py) — a GPU campaign holds the device; the CPU-runnable ones pass.

Review adversarially against plan v13: (1) does each item close its finding, fail closed and avoid self-reference (expected
derived from the observed); (2) do the telemetry patches observe the real served MoE paths (verifier _switch_glu, SwitchGLU
incl. its exact fused helpers, the drafter's draft_block) without double counting or missing calls, and do the sabotage
tests prove it; (3) the borrowed panel's binding and the panel phase; (4) the projection formula's assumptions; (5) tests
that will not pass for the right reason on Metal, or do not prove their docstrings.

Findings ids M1 onward, each: severity, file:line, problem, failure scenario, fix. End with exactly one line:
`VERDICT: CLEARED` or `VERDICT: NOT CLEARED <ids>`. OUTPUT RULE: your FINAL message must contain EVERY finding in full, then
the VERDICT line.
