**P6 — Changes, test files only**

- `test_opencode_probe_seeding.py`: added a shared, opt-in scan fixture for fake model `m`; added real-registry golden and unstubbed M58 refusal tests through `gather()`. Golden lookup forces no live worker.
- `test_scaffold_policy_compare.py`: uses that fixture for the legacy-row preservation test.
- `test_run_agentbench_os.py`: encoding now follows the fixture’s decoding resolver, including per-test overrides.

Production guards and existing assertions remain unchanged.

**P7 — Exact pytest summaries**

| Run | Before | After |
|---|---|---|
| Problem 1, permitted tests | `20 failed, 108 passed, 2 skipped, 2 deselected in 25.35s` | Included below |
| All three files, default temp | `22 failed, 259 passed, 2 skipped in 37.52s` | `281 passed, 2 skipped, 2 deselected in 35.80s` |
| Four transcript tests, default temp | `4 passed, 147 deselected in 1.21s` | Included above |
| Four transcript tests, workdir temp | `4 failed, 147 deselected in 0.93s` | `4 passed, 147 deselected in 1.08s` |

**P8 — Limits and verification**

Both reported causes were confirmed by execution and code inspection. Nothing substantive in the brief proved wrong.

Two integration tests initially failed on sandbox-denied mock-server binds; they were subsequently deselected to honor the no-server restriction. Thus the unrestricted full-suite success criterion remains unverified. Real `opencode` was disabled throughout.

All pytest runs finished naturally. `git diff --check` passed. No production edits, live-server requests, or repository Git mutations were made; unrelated working-tree changes were left untouched.