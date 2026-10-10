P17: Implemented C119:

- `benchmark/bench/generate.py` — abort classification, atomic manifest stamps, C106 check, resume history.
- `benchmark/bench/client.py` — added `TransportAbort`.
- `benchmark/bench/tests/test_generate_transport_abort.py` — 32 mocked regression tests, including CLI subprocess exit.
- `benchmark/README.md` — classification table.

P18: Red evidence: **“rows=5, probe_calls=5; no abort”**; CLI exited **0**. Saved under `$STACK_WORKDIR/c119/tmp/red.txt`.

P19: Final results:

- `32 passed in 0.17s`
- `3232 passed, 2 skipped, 2 warnings in 280.10s`

Full-suite success required sandbox escalation and unsetting inherited `STACK_WORKDIR`. Earlier attempts hit a native MLX abort and an unrelated existing dsh workdir-guard failure.

P20: **Existing tests edited: none.** `run.py` already propagates `RuntimeError`; its nonzero exit was verified by subprocess. Behavior was tested with mocks, not a live model. C124, unrelated working-tree changes, and git state were untouched.