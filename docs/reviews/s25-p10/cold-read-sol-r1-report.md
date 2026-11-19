P1  
Location: `benchmark/bench/local_gate.py:205-208,341-344`  
Severity: blocker  
Evidence: confirmed — traced  
Problem: The stack pytest step inherits `PYTEST_ADDOPTS` and external plugins. Thus assumption (c) is unsafe: the gate does not guarantee the full suite runs.  
Concrete failure scenario: `PYTEST_ADDOPTS="-k 'not tg1_carrier_and_plugins'"` deselects the closure test. Pytest still returns 0, JUnit does not list deselected tests, and the receipt can PASS while a protected file changed.  
Proposed change: For the stack pytest step, remove `PYTEST_ADDOPTS` and `PYTEST_PLUGINS` and pass `-o addopts=`, as the mlx-vlm gate already does.

P2  
Location: `benchmark/bench/tests/test_m64_arm_closure.py:53-59`  
Severity: blocker  
Evidence: confirmed — reproduced with an existing R100 rename  
Problem: `git diff --name-only` reports only the destination of a detected rename. Intersecting that output with the protected source paths misses a protected file renamed elsewhere.  
Concrete failure scenario: Rename `benchmark/opencode_plugins/datefreeze.js` to `datefreeze.old.js` without changing its contents. Git reports only the new path, `carrier_edits()` returns empty, and the test passes.  
Proposed change: Use `git diff --no-renames --name-only base HEAD`, or diff using the four protected paths as pathspecs. Add a rename regression test.

P3  
Location: `benchmark/bench/local_gate.py:259-264,484-495`  
Severity: blocker  
Evidence: confirmed — traced  
Problem: `run` treats the local remote-tracking ref as GitHub’s current `main` without fetching it. Assumption (a) is false when that ref is stale.  
Concrete failure scenario: Local `origin/main` is B with protected content X; GitHub main is C with Y. A candidate based on C changes the file back to X. The gate compares B..candidate and passes. Conversely, a candidate preserving Y is incorrectly refused because B..candidate reports a change.  
Proposed change: Fetch canonical `origin` successfully immediately before resolving `PUSHED_REF`, then capture the SHA. Keep the existing movement check during scratch setup.

P4  
Location: `benchmark/bench/local_gate.py:511-512,617-625,679-685,819-826,935-937`  
Severity: blocker  
Evidence: confirmed — traced  
Problem: Although `pushed_base` is recorded, neither pre-push `check` nor `release` validates it. A receipt remains acceptable after `origin/main` advances, even though the closure result depends on that base.  
Concrete failure scenario: A receipt passes against base B. Main advances to C and changes a protected file. `check` fetches C but accepts the B-based receipt solely by SHA and policy digest; `release` similarly reuses it. Under the required tree-diff semantics, C..candidate could fail.  
Proposed change: Stack receipt lookup must require `receipt["pushed_base"]` to equal the freshly resolved remote main. Apply the same validation in `release`; missing or mismatched fields must refuse.

P5  
Location: `benchmark/bench/local_gate.py:267-283,493-495`; `benchmark/bench/tests/test_s25_p10_pushed_base.py:61-63`  
Severity: major  
Evidence: confirmed — traced  
Problem: Nothing enforces the stated invariant that the pushed base cannot be the build itself. The new test even accepts an exported base equal to HEAD.  
Concrete failure scenario: On a new machine, `release` reruns the gate for an already-pushed stack HEAD without local receipts. `origin/main == HEAD`, so the protected-file diff is empty even if that commit changed a protected file relative to its predecessor.  
Proposed change: Refuse clearly when the resolved base equals the gated SHA/HEAD. If rerunning releases for already-pushed commits must remain supported, define a separate trusted way to supply and validate the pre-build base.
