P1
- Location: `benchmark/bench/tests/test_opencode_v2_probe.py:1090`
- Severity: minor
- Evidence: confirmed
- Problem: `match="plugin"` can accept unrelated plugin failures.
- Failure scenario: `/api/integration` exits nonzero; `"plugin activation discovery exit N"` satisfies the test without proving missing logging caused refusal.
- Proposed change: match `"lacks loading plugin"` exactly.

P2
- Location: `benchmark/bench/tests/test_opencode_v2_provenance.py:267-277`
- Severity: minor
- Evidence: confirmed
- Problem: the test checks only `OPENCODE_PRINT_LOGS`, not that the complete caller environment and subprocess parameters remain unchanged.
- Failure scenario: the activation call drops `OPENCODE_CONFIG_CONTENT` or uses another cwd while the fake still emits proof; the test passes.
- Proposed change: record and assert the complete `env`, `cwd`, `timeout`, and `stdin` arguments.
