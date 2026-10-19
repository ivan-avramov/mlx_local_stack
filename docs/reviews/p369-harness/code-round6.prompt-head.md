Cold CODE review ROUND 6 — the P369 phase-2 GPU worker-conformance harness + P387 (fork `mlx-vlm`, branch `p369-mtp`):
the fix round for your round-5 findings, plus one operator-asked refinement.

Workspace: the `mlx-vlm` fork checkout at the base `24551869`; the branch commits are in this repository's object store —
read any file with `git show <HEAD>:<path>` (read-only; modify nothing). Production is pinned at `4e6d0e03` (diff must stay
empty — verify). Round 5 reviewed `db825821`; this round's diff is `db825821..<HEAD>` (inline below), each fix red test first.

Lead decisions this round (verify; challenge if wrong): H30 / H31 — `os.waitid` does not exist in macOS Python, so the worker's
exit is OBSERVED in the strict ps table (our own unreaped child stays a zombie, stat `Z`, same lstart) and the worker is
reaped only after `reap` proved extinction — its pid and group id stay anchored until then, and the numeric group id is
never trusted after reaping; tracker creation failing RAISES (never an untracked "exited"). H32 — `stop_worker`, `reap` and
the run_job cleanup run under `deferred_signals` and replay a further TERM only after extinction (the primary exception
propagates on the error path). H33 — ps calls inside a bounded cleanup are capped to its deadline plus `PS_MARGIN_S` (5 s).
H34 — a missing / non-boolean `pass` in comparator or kernel evidence RAISES (harness error), never E1c FAIL. H23 —
`Campaign(args)` reads nothing; the registry and params load in `prepare()` inside the persistence boundary (a signal before
the run directory exists is not persistable — disclosed). Operator-asked refinement (stack P394 (2) refined): a full PASS
needs E1c PASS, E2 PASS and E7a OBSERVED; E7b (scripted chat continuity, descriptive by plan §3) is reported, never gates;
the smoke runs one E7b session and its gate needs it to have run and reported. H12 stays deferred (P394 (5)).

Review adversarially: (1) for EACH open round-5 finding (H12, H22, H23, H24, H27, H29, H30, H31, H32, H33, H34): RESOLVED /
PARTIALLY RESOLVED / NOT RESOLVED, citing code; (2) NEW defects the fixes introduced (zombie-based exit detection and its
interaction with Popen, a worker killed by a signal, the deferred-signal scopes, the E7b smoke step and gate, test
determinism and orphan processes); (3) anything that could still let a run PASS without establishing the claim, or report a
harness failure as an MTP finding.

Findings ids H35 onward (re-cite older ids when not resolved), each: severity (BLOCKER / HIGH / MEDIUM / LOW), file:line,
the problem, a concrete failure scenario, the fix. End with exactly one line: `VERDICT: CLEARED` or
`VERDICT: NOT CLEARED <ids of blocking findings>`.
OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the VERDICT line.
