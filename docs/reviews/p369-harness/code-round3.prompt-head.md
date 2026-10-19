Cold CODE review ROUND 3 — the P369 phase-2 GPU worker-conformance harness (fork `mlx-vlm`, branch `p369-mtp`): the fix
round for your round-2 findings, AND the cold code review of P387 (test-only: the pinned registry fixture + an opt-in
live-registry check).

Workspace: the `mlx-vlm` fork checkout at the base `24551869`; the branch commits are in this repository's object store —
read any file with `git show <HEAD>:<path>` (read-only; modify nothing). Production is pinned at `4e6d0e03` (diff must stay
empty — verify). Round 2 reviewed `dec95d95`; this round's diff is `dec95d95..<HEAD>` (inline below): P387 (2 commits, the
build note v2 is inline) and the round-2 fixes (each red test first; `test(...) … red` commits name the failing ids and say
when a red is "helper absent" rather than behavioural).

Lead decisions this round (stack `docs/open-questions.md` P394, inline below; verify the code matches; challenge if wrong):
H15 precedence ABORT > FAIL > INCOMPLETE > PASS; a full PASS needs E7a / E7b OBSERVED; `--reviewed-head` optional for a
smoke (an unreviewed smoke never authorizes a full run) and required for the full run (== HEAD, and the smoke bound to that
same reviewed head); a tree guard before every worker launch; the binding extended (versions, env digest without values,
stack bench tree + C84 bundle shas); HF cache resolved as `huggingface_hub` does + the worker checks the snapshot revision
it resolves; `fcntl.flock` lock; process groups for workers (SIGHUP deliberately left to nohup); H12's CI enablement
(`fetch-depth: 0` + `MLX_REQUIRE_P369_ORACLE=1` in `tests.yml`) deferred to the fork `main` merge.

Review adversarially: (1) for EACH open round-2 finding (H2, H6, H8 residual, H9, H10, H12 residual, H14, H15, H16, H17,
H18): RESOLVED / PARTIALLY RESOLVED / NOT RESOLVED, citing code; (2) P387: does the build match build note v2 (K1–K4), can
the ordinary suite still depend on a sibling checkout or `MLX_STACK_REGISTRY`, can a registry that is neither the fixture
nor the exact C177 interim pass the opt-in check, can the exact interim fail spuriously, is the fixture byte-exact to the
stated source; (3) NEW defects the fixes introduced (the tuple-eligibility replica vs `quantized_verifier.optimized_affine_linears`,
the group kill paths incl. a non-leader process, the flock descriptor lifetime, the tree guard's git calls, the extended
binding vs a legitimate smoke→full sequence, E7 status edge cases, test determinism and orphan processes).

Findings ids H19 onward (re-cite older ids when not resolved), each: severity (BLOCKER / HIGH / MEDIUM / LOW), file:line,
the problem, a concrete failure scenario, the fix. End with exactly one line: `VERDICT: CLEARED` or
`VERDICT: NOT CLEARED <ids of blocking findings>`.
OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the VERDICT line.
