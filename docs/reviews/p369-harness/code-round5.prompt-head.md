Cold CODE review ROUND 5 — the P369 phase-2 GPU worker-conformance harness + P387 (fork `mlx-vlm`, branch `p369-mtp`):
the fix round for your round-4 findings.

Workspace: the `mlx-vlm` fork checkout at the base `24551869`; the branch commits are in this repository's object store —
read any file with `git show <HEAD>:<path>` (read-only; modify nothing). Production is pinned at `4e6d0e03` (diff must stay
empty — verify). Round 4 reviewed `62f4f00c`; this round's diff is `62f4f00c..<HEAD>` (inline below), each fix red test first.

Lead decisions this round (verify; challenge if wrong): H27 — no signal mask: TERM / INT during the spawn and the
tracker's creation are recorded by temporary main-thread handlers (`deferred_signals`) and replayed inside the try that owns
cleanup. H28 — `ps_table` (LC_ALL=C, retries, timeout, strict parsing, must contain this process) raises; a ps outage during
a stop SIGKILLs the just-created group (safe while the worker is unreaped) and fails closed. H29 / H30 — `Descendants` holds
validated identities (pid + LC_ALL=C lstart; the root's start recorded; stale pids never traversed or signalled; a reused
root pid makes the group foreign); stops and `reap` signal identities (never a cached pgid) and `reap` re-scans until none
is alive, failing closed after its bound. Residuals (disclosed): a helper that spawns and escapes between two polls; pid
reuse within one lstart second (macOS pids are sequential). H9 — workers run with `HF_HUB_OFFLINE=1` (only the cached,
attested snapshots load; a symlink swap DURING the load that is restored before the post-load re-hash is outside the
single-operator threat model — disclosed); the stack bench state (tree + bundle shas) is re-checked against the manifest
before and after each reconstruction. H23 — preparation is inside the persistence boundary. H12 stays deferred (P394 (5)).

Review adversarially: (1) for EACH open round-4 finding (H9, H12, H22, H23, H24, H27, H28, H29, H30): RESOLVED / PARTIALLY
RESOLVED / NOT RESOLVED, citing code; (2) NEW defects the fixes introduced; (3) anything that could still let a run PASS
without establishing the claim, or report a harness failure as an MTP finding.

Findings ids H31 onward (re-cite older ids when not resolved), each: severity (BLOCKER / HIGH / MEDIUM / LOW), file:line,
the problem, a concrete failure scenario, the fix. End with exactly one line: `VERDICT: CLEARED` or
`VERDICT: NOT CLEARED <ids of blocking findings>`.
OUTPUT RULE: your FINAL message must contain EVERY finding in full, then the VERDICT line.
