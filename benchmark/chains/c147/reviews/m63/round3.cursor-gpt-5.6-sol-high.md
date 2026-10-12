M7 — blocker — `benchmark/bench/chain_ops.py:430-433,482-500`: worker selection uses a substring match, which can match the requested model solely inside `--draft-model`; the checker never verifies `--model == entry["hf_path"]`. A worker serving different weights with the expected drafter is accepted. Parse and require exactly one matching `--model`; add wrong-main/correct-drafter tests for both picks.

M8 — should-fix — `benchmark/bench/chain_ops.py:482-500`: “exactly shipped” validation ignores flags forwarded by mlx-serve: `--mtp-verify-ab`, `--draft-block-size`, `--suffix-min-match`, and `--draft-cooldown`. The current entries omit them, so healthy workers pass, but an unshipped AB worker is accepted. Compare each flag against the overlay using mlx-serve’s omission rules and test unexpected extras.

Authorized suite: 295 passed. M4–M6’s new tests exercise behavior that fails on the round-2 code; no healthy current ON/OFF worker is refused.

not clearedAuthorized suite passed: 295 tests in 45.16s. No follow-up executed; review remains not cleared due to M7–M8.
