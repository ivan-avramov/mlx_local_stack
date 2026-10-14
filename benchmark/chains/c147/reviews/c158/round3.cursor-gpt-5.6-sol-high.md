A6. low — `benchmark/bench/tests/test_c158_auditors.py:173-178` — A5’s test is not biting on boxes where a real CLI is absent: removing the fixture still yields the expected `FileNotFoundError` after actually spawning the version probe. Make `subprocess.run` fail in this test and iterate probes from `answer_key.declared_auditors()` dynamically.

A7. medium — `benchmark/bench/answer_key.py:114-119` — A malformed later resolution overwrites an earlier valid resolution before `audit_states` rejects its operator fields. Sequence: genuine `audit_error` → valid `generic` resolution → copy with empty `operator_reason`; the legitimately resolved row becomes unresolved. Validate both operator fields before replacing `out[key]`, and test this sequence.

A8. medium — `benchmark/web_audit.py:165-168` — Audit idempotence still trusts raw sidecar records rather than `accepted_audits`. A malformed record or resolution without a genuine predecessor marks its key done, while scoring rejects it; even `--retry-errors` cannot repair an `unclear` malformed tail. Build `done` from accepted records using the shared resolution validator and add a recovery test.

Authorized suite: 139 passed.

cleared after fixes (A6, A7, A8)The authorized C158 test suite completed successfully: 139 passed in 69.32s. No follow-up action is needed.
