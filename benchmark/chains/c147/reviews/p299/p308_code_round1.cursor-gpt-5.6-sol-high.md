Review of commit `3d2aa8fb` against parent `784b70ee`.

Findings: none—no blocker, should-fix, or nit defects found.

1. Cancel paths are safe
   - STOP is the only pre-barrier cancellation path.
   - Idle cancellation requires `barrier_done`.
   - Barrier mismatches already retain `reasons` and abort with rc 2.
   - See `benchmark/chains/c147/run_tg1_chain.py:639-663`.

2. Skipped mismatches cannot become accepted evidence
   - No ACK is written after cancellation.
   - Post-exit validation rejects nonzero rc, incomplete rows, `transport_abort`, and identity mismatches.
   - STOP attempts are archived under `stopped/`, never restarted or resumed.
   - See `benchmark/chains/c147/run_tg1_chain.py:394-423`.

3. The live race is real
   - If cancellation arrives during pre-manifest discovery, the real probe subsequently writes its manifest, detects cancellation while awaiting ACK, stamps `transport_abort`, and exits.
   - If cancellation is already present at the earlier pre-discovery check, it exits without a manifest; that remains safely incomplete.
   - See `benchmark/bench/tg1_runner.py:1034-1035,1113-1117,1240-1252`.

4. Tests are adequate
   - `FAKE_ABORT_LINGER_S=0.5` deterministically exposes the abort-manifest/process-alive window; `0` covers natural timing.
   - Existing barrier mismatch tests retain coverage for worker, registry, and probe identity failures.
   - See `benchmark/bench/tests/test_c147_chain_runner.py:399-411`.

Tests were not run, per read-only instruction.

Verdict: cleared
