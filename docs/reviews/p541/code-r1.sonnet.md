Findings (round 1). I did not run anything; every item below is traced in the source.

**1. `_touched` mangles the first path, so code can be classed docs-only**
- Location: `local_gate.py` `_touched` (change.diff:38-45), via `_git`'s `.strip()` (`local_gate.py.txt:175`).
- Severity: major. Evidence: confirmed by trace.
- Problem: `_git` returns `stdout.strip()`. With `-z` output, a leading-whitespace first path loses that whitespace. A commit adding only `" docs/evil.py"` (a top-level directory named ` docs`, with a leading space) gives `"docs/evil.py"`. `is_docs_path` accepts that. The same goes for a first path of `"\tdocs/..."`.
- Failure scenario: a push whose commits only touch ` docs/…` is classified docs-only and leaves with no receipt. Because `-z` was meant to make paths exact, this defeats the purpose of using it.
- Proposed change: in `_touched`, call `subprocess.run` directly, or add a `_git_raw` that does not strip. Split on NUL with no strip. Add a test for a ` docs/x.py` path, and one for a first path with a trailing newline or space.

**2. `introduced()` excludes commits on any remote ref, including `evidence` and other unreviewed branches (A1 only partly holds)**
- Location: `push_level` none-new branch and the `introduced` call (`local_gate.py.txt:403-404`).
- Severity: major (raise with the operator, since the spec fixes C). Evidence: confirmed by trace.
- Problem: C is "not on any `remote/*` ref". The stack's `remote/evidence` is an orphan branch that is PII-scanned only and may hold arbitrary code (the pre-existing evidence rule). Any commit reachable from it, or from a never-receipted remote branch, counts as already pushed.
- Failure scenario: push a new branch name, or a `refs/heads/release` ref, whose tip is an `origin/evidence` commit that carries code. C is empty, so the level is `none-new` and it is accepted with no receipt. Code from the data branch is thereby published as a code branch. Merging it in is caught by the first-parent diff, but a fast-forward or new-name push is not.
- Proposed change: either exclude `refs/remotes/<remote>/evidence` from the `--not` set for non-evidence pushes, or require `none-new` tips to be reachable from `<remote>/main`. If the spec forbids this, report it to the operator.

**3. `digest_for` now runs on every code push, which can raise or crash on pushes that never needed it**
- Location: `push_level` (`pass_receipt(..., digest_for(repo, local_sha))`) and `main`'s lambda (`local_gate.py.txt:639`).
- Severity: minor. Evidence: hypothesis.
- Problem: before this change, branch pushes never called `digest_for`. Now it reads `current_parity` and `audits_at` from `live[rp]` (the live checkout under `stack.parent/…`) at `sha`. If the push comes from another clone or worktree, the sha may not exist in `live`, so `_git` raises `GateError`. The hook then prints `[local_gate] REFUSED: git show … in …`, with no `[pre-push]` prefix and no level lines for the other refs. A missing `.github/workflows/upstream-parity.yml` has the same effect. The behaviour is a refusal, not a bypass, but the message does not say that no receipt was found.
- Proposed change: catch `GateError` around `digest_for` in `push_level` and return a level problem such as `REFUSED: <repo> <sha8>: cannot compute the policy digest (<reason>)`. Keep the other refs' level lines.

**4. A ref refused by a scan still prints a passing `level:` line**
- Location: `check_lines`, `_level_of` call sites (`local_gate.py.txt:476`, `480`).
- Severity: minor. Evidence: confirmed by trace.
- Problem: `levels` is appended whenever `push_level` has no problems, regardless of scan problems for the same ref. A ref with a PII or naming violation prints `[pre-push] level: docs-only refs/heads/main abcd1234` followed by its PII line, and the push exits 1. That is ambiguous output, and it conflicts with v1.1's "level lines of the refs that passed".
- Failure scenario: an operator reads `level: docs-only` and misses that the same ref was refused.
- Proposed change: record the scan problem count before `_scan`. Append the level line only if that ref produced no problems at all. Add a test that asserts no level line for a ref with a PII violation (`test_the_pii_scan_still_runs_at_every_level` only checks the problem).

**5. Test: "another-digest" only tests the filename glob**
- Location: `test_p541_push_level.py` `test_a_receipt_that_is_not_a_PASS_for_this_sha_under_this_policy_refuses`, and `_receipt`.
- Severity: minor. Evidence: confirmed by trace.
- Problem: the wrong-digest receipt is written as `…-eeeeeeeeeeee.json`, which the glob `…-dddddddddddd*.json` never matches. The `doc.get("policy_digest") == digest` and `doc.get("sha") == sha` checks in `pass_receipt` are never exercised. A receipt with the right filename but a wrong digest or sha inside is the case that matters, and it is untested in `test_p541_push_level.py`. (`test_p541_impl.py` only tests a FAIL verdict, not wrong contents.)
- Proposed change: add cases that write a file named for the correct sha and digest but with `policy_digest="e"*64` inside, and another with the wrong `sha` inside.

**6. Test: the `evidence` push is "data-only" by construction, even when `push_level` is called alone**
- Location: `push_level` (`remote_ref == EVIDENCE_REF`) and `test_a_stack_evidence_orphan_is_data_only_and_pii_only`.
- Severity: minor. Evidence: confirmed by trace.
- Problem: `push_level` returns `data-only` for any sha pushed to `refs/heads/evidence` without checking the orphan condition. The orphan rule lives only in `check_lines`. Any other caller of the public interface `push_level` gets a free data-only level for a non-orphan push. No test calls `push_level` with a non-orphan evidence sha; the one non-orphan test goes through `check_lines`.
- Proposed change: document the dependency on `check_lines`, or move the orphan check into `push_level` and make `check_lines` call it.

**Checked, no defect**
- A2 holds. `diff-tree -r parent[0] merge` covers the whole first-parent delta. The `-s ours` case and the second-parent commits in C are over-restrictive (they land in full), not a bypass.
- Receipt matching in `pass_receipt` checks `sha`, `policy_digest` and `verdict` inside the file, not only the file name.
- The stack-tag rule and the evidence orphan rule are unchanged. Fork tags peel to `sha`, so the receipt and the printed sha8 are the tagged commit's (v1.2).
- Pushing to a URL rather than a remote name makes C the whole history, so it lands in `full`. That is stricter, not a bypass.
