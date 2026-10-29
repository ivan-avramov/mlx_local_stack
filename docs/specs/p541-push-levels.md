# P541 — a push passes its stated level (C253) — spec v1

## Goal
Every branch push of the stack (`mlx_local_stack`), `../mlx-vlm` and `../mlx-serve` passes a named level, enforced by the machine-local pre-push hook (`bench.local_gate check`), and the push output says which level it passed. Today (P448) a branch push runs only the per-commit PII / naming scans; PASS gate receipts are required only for stack tags and the stack's gitlinks.

## Levels (for each pushed ref update `local_ref local_sha remote_ref remote_sha`, `local_sha` not all-zero)
Let C = the commits the push introduces (`git rev-list <local_sha> --not --remotes=<remote>`, as `introduced()` today) and P = the union of paths those commits touch (`git diff-tree --no-commit-id --name-only -r --root <c>` over C; a merge commit contributes its diff against its first parent).
1. **data-only** — the stack's `refs/heads/evidence` (the P447 orphan rule stays exactly as today: shares no history with `<remote>/main`, PII scan only, no naming scan). Also, for any stack branch: P non-empty and every path under `benchmark/results/`.
2. **docs-only** — P non-empty and every path matches `docs/**` or is a top-level `*.md` (a path with no `/` ending in `.md`).
3. **full** — otherwise: a PASS gate receipt for exactly `local_sha` under the current policy digest (`has_pass(gate_dir, repo, local_sha, digest_for(repo, local_sha))`).
- C empty (the tip is already on the remote, e.g. a new branch name for an existing commit): level **none-new**, accepted.
- The existing per-commit scans (PII + naming; evidence: PII only) still run for every level and still refuse.
- The existing stack TAG rules (P448: SemVer, release receipt, gitlinks) are unchanged; a tag push is not a branch push.
- A level is chosen in the order data-only, docs-only, full; a push that is neither data-only nor docs-only and has no PASS receipt is refused with `[pre-push] REFUSED: <repo> <sha8>: no PASS gate receipt for a code push (level full required; run: bench.local_gate run --repo <repo> --sha <sha>)`.
- On success the hook prints one line per ref: `[pre-push] level: full (receipt <file name>) <remote_ref> <sha8>`, `[pre-push] level: docs-only <remote_ref> <sha8>`, `[pre-push] level: data-only <remote_ref> <sha8>`, or `[pre-push] level: none-new <remote_ref> <sha8>`, to stderr.

## Interfaces
- `bench.local_gate.push_level(repo, repo_dir, remote, local_ref, local_sha, remote_ref, *, gate_dir, digest_for) -> (level: str, detail: str, problems: list[str])` — pure apart from `git` reads in `repo_dir` and receipt reads in `gate_dir`.
- `check_lines(...)` (existing) calls it per line and returns the problems; the hook entry (`main` → `check`) prints the level lines and exits 1 on any problem.
- Paths classification helpers are module functions with tests: `is_docs_path(path) -> bool`, `is_data_path(path) -> bool`.

## Non-goals
No "smoke" level; no change to `run`, `release`, receipts, the policy digest or the hooks' installation; no network beyond the `git fetch --prune` the check already does.

## Acceptance
- Tests (hermetic: tiny local git repos under `tmp_path`, an injected `gate_dir` and `digest_for`) cover: each level for stack and fork; a code push without a receipt refuses; a receipt for another sha, a FAIL receipt or a receipt under another policy digest refuses; mixed docs + code is full; mixed docs + data is full; an empty-diff commit (no paths) is full; evidence unchanged (orphan rule, PII-only); tags unchanged; the printed level lines; none-new.
- The full stack suite passes; the gate passes on the change.
