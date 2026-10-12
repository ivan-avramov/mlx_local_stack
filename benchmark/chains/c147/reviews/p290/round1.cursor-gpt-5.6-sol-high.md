D1 — should-fix — `benchmark/bench/chain_ops.py:261`: the gate inherits the runner environment, while probes use `env_base()`, which merges `.env`. PATH, HOME, `DOCKER_HOST`, or `DOCKER_CONTEXT` can therefore select a different CLI/socket. Run the check with `env=self.env_base()` and test environment parity.

D2 — should-fix — `benchmark/bench/chain_ops.py:261`: `docker info` does not verify the required `aider-benchmark:latest` image. Add `docker image inspect aider-benchmark:latest`; otherwise failure is delayed until Go grading.

D3 — should-fix — `benchmark/bench/tests/test_p290_docker_gate.py:30`: the tests cover normal Go launches but not a restarted Go leg. Add a restart test that drops Docker before the repeated Go attempt and proves no probe launches. The implementation’s centralized `run_step()` placement currently covers restarts; this closes the mutation gap. Permitted suite: 241 passed.

The 30-second, no-retry policy is appropriate for this fail-closed chain.

cleared after fixes (D1, D2, D3)The permitted test suite passed: 241 tests in 40.58s. No follow-up action needed.
