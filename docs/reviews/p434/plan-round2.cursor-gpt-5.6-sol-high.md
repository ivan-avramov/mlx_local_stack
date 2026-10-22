G1 — CLOSED — v2 explicitly limits the threat model to accidental pushes and treats same-user receipt tampering as equivalent to `--no-verify`.

G2 — CLOSED — exact repository SHA plus a digest covering gate code, baseline, commands, parity pin, and repository identity invalidates materially stale receipts; tracked locks/configuration are already bound by the SHA.

G3 — CLOSED — the stack gate builds a fresh environment against exact locally cloned gitlinks and verifies both imported packages resolve inside the scratch clone.

G4 — OPEN — the current run still relies on a human promise; rechecks do not prevent a benchmark from starting during a long gate step, and the durable reservation is deferred and limited to the next P426 sequencer rather than every benchmark launcher.

G5 — OPEN — `git rev-list <local> --not --remotes=origin` relies on potentially stale local remote-tracking refs, ignores the actual destination supplied to the hook, and therefore does not reliably enumerate every commit being introduced by normal, force, new-branch, and tag pushes.

G6 — OPEN — bootstrap only warns when sibling forks are absent and the shim does not pin an independently stable policy; a fresh box therefore lacks hooks on later-created sibling clones, while switching to an older but importable gate revision can reactivate an older policy.

G7 — CLOSED — stack pushes now fetch the canonical fork origins and require each gitlink to be reachable from its designated `origin/main`.

G8 — CLOSED — v2 specifies all eight audit commands, including `check_upstream_deletions.py --strict`, and tests their exact argument vectors.

G9 — CLOSED — v2 restores `uv build` and requires both wheel and source-distribution artifacts, covering the omitted build job.

G10 — CLOSED — v2 uses explicit managed Python, authoritative locked synchronization, fresh environments, and tracked-file cleanliness checks after setup and test steps.

G11 — CLOSED — all fetching and remote configuration for test execution occurs in disposable independent clones rather than linked worktrees.

H1 — HIGH — §2 Hooks  
Problem: the shim invokes `$STACK_REPO/.venv-bench/bin/python -m bench.local_gate` without adding `$STACK_REPO/benchmark` to `PYTHONPATH`. `bench` is not installed in `.venv-bench` and is not importable from either the stack root or sibling fork roots.  
Failure scenario: every pre-push invocation fails at module discovery, so no repository can be pushed through the new gate even with a valid receipt.  
Fix: invoke with `PYTHONPATH="$STACK_REPO/benchmark"` and add unmocked tests executing the installed shim from the stack and both sibling repository roots.

VERDICT: DISAGREE G4,G5,G6,H1
