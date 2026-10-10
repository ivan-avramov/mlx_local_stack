**P8 — Implemented P154/P157; uncommitted. One acceptance blocker remains:** the unchanged dsh test fails its `STACK_WORKDIR` isolation guard, outside the allowed edit scope.

Files changed, one line each:

- `configgen/emitters/opencode.py`: native v2 client; separate, unchanged v1 bench output.
- `configgen/tests/test_opencode.py`: v2 assertions and real-binary validation controls.
- `configgen/tests/test_opencode_bench.py`: client namespace update and v1 byte-identity assertion.
- `opencode_config/opencode.json`: regenerated v2 configuration.
- `opencode_config/README.md`: v2 mappings, installation, compaction split, validation evidence.
- `scripts/session_pinning_gate.py`: hermetic v2 A4, explicit session resume, router-bound result recording.
- `benchmark/bench/session_cache_probe.py`: added v2 command helper; retained 1.18 helpers.
- `benchmark/bench/tests/test_session_pinning_a4_v2.py`: 17 tests covering pinning, isolation, hashes, failures, and CLI selection.
- `benchmark/README.md`: requested M59 subsection and freeze sentence.
- `AGENTS.md`: exact requested M50 sentence.

**P9 — Binary evidence and deviation:** 2.0.20 `/api/config` loaded all eight models with bodies and plugins intact. **Superpowers retained.** Contrary to the requested control expectation, unknown keys are stripped while the document survives; that behavior is asserted. A malformed-JSON control proved silent whole-document dropping with rc 0.

**P10 — Existing assertions changed:**

- Structure: `provider → providers`, sampling `options → body`, task suffix check → exact `agents.title.model`.
- Sparse-family sampling: same values and excluded keys, checked under `body`.
- Top-level allowlist: v1 keys → native v2 keys.
- Client attachment flags → image presence/absence in `capabilities.input`.
- Client `modalities → capabilities` for input/output assertions.
- Limit assertions: namespace updated; numeric expectations unchanged.
- Candidate exclusion: namespace updated; exclusion unchanged.

Shared v1 bench assertions remain intact.

**P11 — Validation:**

```text
Configgen: 71 passed in 1.63s
A4 tests: 17 passed in 3.04s
Benchmark suite: 1 failed, 3284 passed, 2 warnings in 234.76s
configgen check: PASS
```

The sole failure is `test_real_dsh_closed_port_escalates_transport_failure_and_writes_no_row`; it independently reproduces the inherited-workdir isolation failure. No out-of-scope fix or skip was applied.

Exactly ten allowed files changed. Fresh generation is byte-identical; the v1 bench carrier matches HEAD byte-for-byte.