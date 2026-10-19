Cold CODE review ROUND 4 — the P369 phase-2 GPU worker-conformance harness + P387 (fork `mlx-vlm`, branch `p369-mtp`):
the fix round for your round-3 findings.

Workspace: the `mlx-vlm` fork checkout at the base `24551869`; the branch commits are in this repository's object store —
read any file with `git show <HEAD>:<path>` (read-only; modify nothing). Production is pinned at `4e6d0e03` (diff must stay
empty — verify). Round 3 reviewed `a004a922`; this round's diff is `a004a922..<HEAD>` (inline below), each fix red test first.

Lead decisions this round (verify; challenge if wrong): H9 — `--reviewed-head` is resolved with `git rev-parse --verify
<v>^{commit}` and compared as a full id; `XDG_CACHE_HOME` joins the HF cache precedence; the worker re-hashes every attested
snapshot file it loaded (≈ 15 GB per launch, accepted as cost); the stack bench inputs (`benchmark/bench` + the C84 bundle
files) must be clean in the worktree at prepare and before each reconstruction. H21 — ONE lock at
`$STACK_WORKDIR/p369/phase2/.lock`, `--out` must be a run directory under it. H22 — descendant tracking uses `ps` (pid + start
time; the fork venv has no psutil), scanned at every poll (a helper that both spawns and escapes between two polls is a
disclosed residual); macOS answers `killpg(pgid, 0)` with EPERM for a zombie-only group, so group extinction is decided by
`ps` (non-zombie members). H12's CI enablement stays deferred to the fork `main` merge (P394 (5)).

Review adversarially: (1) for EACH open round-3 finding (H8/H20, H9, H12, H16/H23, H17/H22, H19, H21, H24, H25, H26):
RESOLVED / PARTIALLY RESOLVED / NOT RESOLVED, citing code; (2) NEW defects the fixes introduced (the signal mask around
spawn, leadership caching, the `ps` parsing of `lstart`, kill-by-start-time, the extinction wait's bound, the persistence
boundary's status for each exit path, the hang_after promotion, the lock / out rules vs the handoff's launch command, the
snapshot re-hash on symlinked HF blobs, test determinism and orphan processes); (3) anything that could still let a run PASS
without establishing the claim, or report a harness failure as an MTP finding.

Findings ids H27 onward (re-cite older ids when not resolved), each: severity (BLOCKER / HIGH / MEDIUM / LOW), file:line,
the problem, a concrete failure scenario, the fix. End with exactly one line: `VERDICT: CLEARED` or
`VERDICT: NOT CLEARED <ids of blocking findings>`.
OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the VERDICT line.
