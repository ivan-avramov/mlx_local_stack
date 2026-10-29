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

## v1.1 — designer rulings after the independent tests (2026-10-29)
- The problem text is `REFUSED: <repo> <sha8>: no PASS gate receipt …` (as in Levels); `main` prefixes `[pre-push] `.
- `detail` = the receipt file name for **full**, `""` otherwise.
- Scan problems are reported by `check_lines` (as today); `push_level` returns only level problems.
- When one ref refuses, the level lines of the refs that passed are still printed; the push exits 1.
- **Fork tags** (`refs/tags/*` on `../mlx-vlm` / `../mlx-serve`) are no longer scan-only: a fork tag push needs a level exactly like a branch push (a tag uploads its commits). Stack tags keep the P448 release rule unchanged.
- Merges: as written — a merge contributes its diff against its first parent, so code merged in makes the push **full**.
- A docs commit plus an empty-diff commit: P is non-empty and all docs → **docs-only** (the empty commit adds nothing); a push whose P is empty → **full**.
- An `evidence` push sharing history with `<remote>/main` stays refused (as today).
- Paths are case-sensitive: `docs/**` needs the `docs/` prefix (a file named `docs` is not docs), top-level `*.md` is lower-case `.md` only, data needs the `benchmark/results/` prefix.
- The existing `test_local_gate.py::test_a_branch_push_needs_no_receipt_only_the_scans` asserts the pre-P541 behaviour; the implementer replaces it with the P541 expectation (a code branch push without a receipt refuses).
- (v1.2) A tag resolves to its commit (`<local_sha>^{commit}`, as `check_lines` already does): the receipt a fork tag push needs, and the sha its refusal and level lines name, are the tagged commit's.

## v1.3 — after the cold review round 1 (sol / glm / Claude Sonnet)
- **Paths are read losslessly**: the `-z` path list is split on NUL with nothing stripped (a path ` docs/x.py` — a top-level directory named ` docs` — is code, not docs; ` benchmark/results/x.py` is not data).
- **C for a non-`evidence` push** excludes from the `--not` set the remote's `evidence` ref (`refs/remotes/<remote>/evidence`): a commit reachable only from `evidence` counts as new, so pointing a code branch at a data commit is classified by its paths (normally **full**).
- **`push_level` owns the evidence rule**: it resolves `<local_sha>^{commit}` itself, and for the stack's `refs/heads/evidence` returns `data-only` only for an orphan (no merge base with `<remote>/main`); otherwise a level problem `REFUSED: stack <sha8>: pushed to refs/heads/evidence shares history with <remote>/main: not an orphan data commit`. `check_lines` relies on it (no duplicate check).
- **A failing policy digest** (`digest_for` raising) is a level problem `REFUSED: <repo> <sha8>: cannot compute the policy digest (<reason>)`; the other refs still get their lines.
- **A ref with any problem** (level or scan) prints no `level:` line; only refs with no problems at all print theirs.
- (v1.4) Any exception raised by `digest_for` becomes the v1.3 digest problem (`<reason>` = `type: message`); `push_level` returns level `full` with the not-orphan problem; the `<remote>/evidence` exclusion from the `--not` set applies to every repository that has such a ref.
