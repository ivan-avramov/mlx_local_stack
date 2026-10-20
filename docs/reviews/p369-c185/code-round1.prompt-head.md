Cold CODE + PLAN review — ROUND 1 OF 3 (C186: at most 3 rounds, then the operator decides the open findings; prioritise what
must be fixed before a GPU smoke) — C185: P369 phase-2 E2 on the SAME-INSTANCE design (fork `mlx-vlm`, branch `p369-mtp`).

Workspace: the `mlx-vlm` fork checkout at the base `24551869`; the branch commits are in this repository's object store — read
any file with `git show <HEAD>:<path>` (read-only; modify nothing). Production is pinned at `4e6d0e03`
(`git diff 4e6d0e03 <HEAD> -- mlx_vlm ':!mlx_vlm/tests'` must stay empty — verify). SCOPE: only the C185 change —
`508bab78..<HEAD>` (inline below: red tests first, then the build) and plan v8 §3 E2 (inline below). The rest of the harness
(review rounds 1–6, closed by the operator after H34/H36/H38) is context, not scope; cite it only where C185 interacts with it.

Operator ruling C185: in the ON worker, per item greedy ON, then the drafter detached → greedy OFF1 + a within-instance OFF2
control on the same loaded target; verdict ON vs OFF1; OFF1 != OFF2 = harness ABORT; the separate OFF process stays as a
reported cross-load comparison that never decides (like E1c's C2); smoke and full; the claim reads "greedy MTP-ON equals plain
greedy decoding on the same MTP-loaded instance". Reuse the E1c machinery (`drafter_detached`, `DetachedGuard`, `wait_idle`,
the release pattern).

Lead decisions (verify; challenge if wrong): D1 — worker mode `e2_pair` (`dev/p369_phase2/worker.py`), each trajectory on a
fresh chat id, `release_session` before the next (no weak-reference retirement proof as in E1c: E2 holds no recorder cache
reference; the evidence of no reuse is `cached_tokens == 0`, exactly, on all three); OFF1/OFF2 must show zero MTP rounds, zero
verify-scope projection calls and no guard violation, else the job raises (harness error). D2 — precedence per pick: C1-E2
(OFF1 vs OFF2 token ids or finish reason) differs → ABORT; else any ON request not engaged (argmax readout > 0, exact-boolean
kernel verdict, MTP rounds > 0) or any prompt-digest problem (the four trajectories of a request must share one digest; C84
items equal the reconstruction) → INCOMPLETE; else ON != OFF1 → FAIL; else PASS. E2 never skips E7 (independent incidence).
D3 — v7's second OFF process (the reload control) is dropped; the cross-load OFF arm runs once and is reported as
`cross_load` (identical / unestablished). D4 — the triple gets 3× one request's timeout (ON + OFF1 + OFF2).

Review adversarially: (1) does the build implement plan v8 §3 E2 and C185 exactly (the verdict instrument, the control, the
non-deciding cross-load comparison, smoke and full); (2) can E2 PASS without the claim (e.g. ON not actually speculative, a
replay not actually plain, a reused prefix, the drafter not restored, a stale capture, the per-request result files of the
two jobs mis-joined by name), or can a harness / instrument failure be reported as an MTP FAIL; (3) new defects in the worker
branch (detachment window, idleness, session release, exception paths, what reaches result.json) and test gaps.

Findings ids E1 onward, each: severity (BLOCKER / HIGH / MEDIUM / LOW), file:line, the problem, a concrete failure scenario,
the fix. End with exactly one line: `VERDICT: CLEARED` or `VERDICT: NOT CLEARED <ids of blocking findings>`.
OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the VERDICT line.
