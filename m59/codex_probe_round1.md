Not complete. Three corrections need approval; no commits were made.

**P169 — Plugin proof:** 2.0.20 logs `loading plugin` with the `noretry.js` path, never `bench.noretry`. Recommend accepting the exact canonical path, bound to the verified plugin SHA.

**P170 — Cap control:** deleting `body.max_tokens` still sends `max_tokens`. Verified replacement: set `limit.output=512`; intact body sends `102400`, deleted body sends `512`. Recommend this positive control.

**P171 — File scope:** add `benchmark/opencode_bench_v2.json` to `benchmark/bench/modelnames.py::GENERATED_PATHS`. That file is currently outside your allowlist.

**P172 — Validation:**

- Full benchmark: **9 failed, 3340 passed, 2 warnings in 283.13s**.
- Failures: seven plugin-proof refusals, one generated-path registration, one existing DSH test’s workdir-isolation guard.
- Real-binary cases: **8 ran; 1 passed, 7 failed; none skipped**.
- Legacy four files: **176 passed**, unchanged.
- New non-real tests: **73 passed**.
- Configgen: **70 passed**; `configgen check` passed.
- Proof: **33 moved functions and 29 retained functions byte-identical to HEAD**.
- Initial RED for tests (4)/(9): `AssertionError: v2 probe is missing: transport failures cannot abort and resume identity is unchecked`.

**P173 — Files changed:**

- `benchmark/run_opencode_probe_v2.py` — native probe, classification, exports, resume.
- `benchmark/bench/opencode_common.py` — shared legacy bodies.
- `benchmark/run_opencode_probe.py` — moves and compatibility re-exports.
- `benchmark/bench/provenance.py` — v2 environment/destination guards.
- `benchmark/opencode_plugins/noretry.js` — exact requested plugin.
- `configgen/emitters/opencode.py` — bench-v2 emitter.
- `configgen/targets.py` — BENCH registration.
- `benchmark/opencode_bench_v2.json` — generated carrier.
- `benchmark/bench/tests/opencode_v2_mock.py` — scripted HTTP mock.
- `benchmark/bench/tests/test_opencode_v2_probe.py` — probe acceptance tests.
- `benchmark/bench/tests/test_opencode_v2_provenance.py` — tripwire tests.
- `configgen/tests/test_opencode_bench_v2.py` — carrier tests.

Only allowed files changed; pre-existing `ts.md` remains untouched. Implemented adaptations: normalize `opencode v2.0.20` version output; omit dummy `apiKey` to obey the stricter settings rule.

Approve P169–P171? These change explicit acceptance wording and expand your allowed-file list, so I’ve preserved the current boundaries pending your ruling.

