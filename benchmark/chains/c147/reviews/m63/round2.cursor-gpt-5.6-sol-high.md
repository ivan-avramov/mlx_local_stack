M4 — blocker — `benchmark/bench/chain_ops.py:454-460`: MTP validation checks only `--draft-kind`; it never verifies the registry’s external `draft_model` reached the worker. A missing/wrong sidecar can therefore produce rows falsely attributed to the shipped ON configuration. Require the worker’s `--draft-model` to match the selected model’s registry entry; test missing and mismatched values.

M5 — should-fix — `benchmark/bench/chain_ops.py:454-459`: `re.search` reads only the first space-form flag. It rejects valid `--draft-kind=mtp` and can misread duplicated flags whose last value is effective. Parse both forms with last-wins semantics, reject contradictory/duplicate flags, and test both orders.

M6 — should-fix — `benchmark/chains/c147/run_tg1_chain.py:765-777`: an opposite-arm `C147_OVERLAY` is checked only after creating the out-root, and `SystemExit("REFUSED…")` exits 1 despite the documented refusal/abort code 2. Validate the overlay before filesystem creation and return code 2; assert no out-root or RUNLOG remains.

Authorized suite: 276 passed. M1 and M2’s tests fail against `8a52557d`; M3 is coverage-only and its tests pass that implementation because the production wiring already existed. Docker-gate ordering remains intact.

not clearedAuthorized suite passed: 276 tests in 46s. No follow-up action needed.
