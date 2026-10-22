G1 — HIGH — §1 Receipt, §3 Tests  
Problem: exclusive creation does not make receipts trustworthy. Any process with normal user access can create or edit JSON into a matching `PASS`; all fields, including `gate_code_sha`, are self-asserted.  
Failure scenario: a failed or nonexistent run becomes an accepted receipt after changing `verdict`, `sha`, and step return codes.  
Fix: define the threat boundary explicitly. If later same-user edits must be detected, use receipts signed by a protected helper/key and verify the signature; otherwise state that deliberate receipt modification is equivalent to `--no-verify` and outside the gate’s guarantees. Add a forged-receipt test.

G2 — HIGH — §1 Receipt/check  
Problem: `check` does not require receipt policy metadata to match the current gate, skip baseline, workflow-derived configuration, or dependency locks. Exact code SHA alone does not prevent stale receipts, especially for forks whose gate implementation and baseline live in the stack repository.  
Failure scenario: a fork SHA passed an older defective gate; after fixing the gate or changing the skip baseline, its old `PASS` remains sufficient forever.  
Fix: derive a policy digest from gate code, baseline, relevant workflow/configuration, lock inputs, and repository identity. `check` must accept only a receipt for both the exact target SHA and current policy digest.

G3 — HIGH — §1 exact-SHA worktree, §2 stack  
Problem: the stack suite is not specified to use the gitlinked fork code from the detached worktree. The existing `.venv-bench` resolves `mlx_vlm` and `mlx_serve` from the live stack checkout’s `src/` directories, while a new worktree has neither that venv nor initialized submodules.  
Failure scenario: stack SHA A points to broken fork gitlinks, but pytest imports different live-checkout fork SHAs and passes. Separate fork receipts do not test stack/fork integration.  
Fix: populate the exact gitlinks in isolated scratch clones/worktrees and force imports to those paths; assert `mlx_vlm.__file__` and `mlx_serve.__file__` resolve inside the scratch tree before pytest.

G4 — HIGH — §1 busy-box refusal, §3 Tests  
Problem: the one-time busy check has a TOCTOU race and creates no reservation. A paused `p426_wave1` run can resume, or another benchmark can start, after the check while a GPU-heavy suite is running.  
Failure scenario: `run` observes `PAUSE`, begins the fork suite, then the operator removes `PAUSE`; the next benchmark leg starts concurrently and its measurements are disturbed.  
Fix: introduce a shared machine reservation lock used by both the gate and every benchmark launch path. Acquire it before the final busy check and hold it through cleanup. Test the resume/start race.

G5 — HIGH — §1 check, §2 stack  
Problem: the plan does not implement C210’s naming and PII scan over every pushed commit. It delegates naming entirely to commit hooks and describes only a PII diff over `<remote>..<local>`; an endpoint diff misses a leak introduced and later removed. New branches have an all-zero remote SHA, and current scanners default to the staged diff.  
Failure scenario: two commits add then remove a credential or shorthand. The final tree and endpoint diff are clean, so the history is pushed publicly.  
Fix: enumerate introduced commits for normal, force, new-branch, and tag updates; scan each commit’s added lines with both checkers and each commit message with `message_violations`. Missing range objects or remote discovery must refuse. Clarify that `check` is receipt-plus-cheap-scans, not receipt-only.

G6 — HIGH — §1 Hooks, §3 bootstrap tests  
Problem: tracked `core.hooksPath` hooks disappear when the stack checkout switches to a commit predating the hook. The shared fork hook also depends on whichever stack branch is checked out. Additionally, bootstrap does not currently create the required sibling fork clones, so “all three repos” is undefined on a fresh box.  
Failure scenario: check out an old stack branch with no `githooks/pre-push`, then push that branch or either fork; Git finds no executable hook and proceeds unchecked.  
Fix: install a stable machine-local shim outside branch-controlled files, with a pinned policy digest. Define whether fork repositories are the required sibling clones or submodules; bootstrap must verify/install the exact three canonical repositories and refuse unknown identities.

G7 — HIGH — §1 stack gitlink checks  
Problem: fork receipts prove testing, not publication. Nothing verifies that each stack gitlink is reachable from the corresponding fork remote.  
Failure scenario: both local fork commits have valid receipts but were never pushed; the stack push succeeds and publishes uncheckoutable submodule references.  
Fix: before accepting a stack push, fetch each canonical fork origin and require the gitlink SHA to be reachable from the designated remote branch. Network or ancestry uncertainty must refuse.

G8 — HIGH — §2 mlx-vlm parity  
Problem: the generic “eight `check_*.py --upstream-ref`” command omits the exceptional `--strict` required by `check_upstream_deletions.py`; without it, findings deliberately return zero.  
Failure scenario: a fork wrongly retains content deleted upstream, the audit reports it, exits zero, and the receipt records PASS.  
Fix: list all eight exact argument vectors, including `check_upstream_deletions.py ... --strict`, and test those vectors.

G9 — MEDIUM — §2 mlx-serve parity  
Problem: the dead CI’s build job is omitted. That job runs `uv build` after tests; lint and pytest do not exercise package construction.  
Failure scenario: malformed packaging metadata or missing build inputs pass the local gate but would have failed CI’s build job.  
Fix: add `uv build` and a deterministic wheel-presence/content sanity check, or explicitly classify and justify the build job as an accepted parity gap.

G10 — MEDIUM — §2 repository environments  
Problem: recorded Python and lock hashes do not ensure the tested environment matches them. Stack reuses a driftable `.venv-bench`; mlx-vlm runs unlocked `uv sync` after the only cleanliness check; mlx-serve claims Python 3.12 but its command does not select 3.12.  
Failure scenario: mlx-vlm rewrites `uv.lock` in scratch and tests uncommitted resolution changes, or mlx-serve silently selects another compatible Python.  
Fix: verify stack venv conformance to `benchmark/requirements-bench.lock`; use explicit managed Python versions; use locked synchronization where authoritative; and perform a final tracked-file cleanliness check after every setup and test step.

G11 — MEDIUM — §1 scratch isolation, §2 mlx-vlm fetch  
Problem: a detached worktree shares repository configuration, refs, object storage, and `FETCH_HEAD` with the live clone. Adding/configuring `upstream` and fetching therefore mutate the live repository despite the isolation claim.  
Failure scenario: a gate run changes the operator’s remote configuration or refs while another operation uses the live fork repository.  
Fix: perform parity fetching in a disposable local clone under `$STACK_WORKDIR`, not a linked worktree; keep all remote configuration and fetched refs confined there.

VERDICT: DISAGREE G1,G2,G3,G4,G5,G6,G7,G8,G9,G10,G11
