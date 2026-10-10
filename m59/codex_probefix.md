**P181 — P169, P171 and settings correction complete. P170 remains incomplete. No commit.**

Files changed this round:

- `benchmark/bench/provenance.py` — canonical plugin-path/SHA proof; exact FILE settings equality; rejects settings elsewhere.
- `benchmark/bench/modelnames.py` — registered generated v2 carrier.
- `benchmark/run_opencode_probe_v2.py` — portable plugin-proof path and semantics in manifest.
- `configgen/emitters/opencode.py` — restored `apiKey: "not-needed"`.
- `benchmark/opencode_bench_v2.json` — regenerated.
- `benchmark/bench/tests/test_opencode_v2_provenance.py` — path/SHA/settings refusal coverage.
- `benchmark/bench/tests/test_opencode_v2_probe.py` — cap controls, authorization header and manifest assertions.
- `configgen/tests/test_opencode_bench_v2.py` — restored-key expectation.

**P182 — Matched plugin log**, with canonical run directory rendered as `<R>`:

```text
timestamp=2026-10-07T02:34:13.104Z level=INFO run=4f6f28f4 msg="loading plugin" id=<R>/cfg/opencode/plugins/noretry.js entrypoint=file://<R>/cfg/opencode/plugins/noretry.js http.span=305 role=server
```

**P183 — Evidence and checks**

- Intact carrier: sent `max_tokens=102400`.
- Variant removing `body.max_tokens` and setting `limit.output=512`: sent `max_tokens=512`.
- Benchmark: `3353 passed, 2 skipped, 2 warnings in 295.07s (0:04:55)`.
- Configgen: `70 passed in 0.11s`.
- `configgen check`: passed.
- All **8 real opencode tests passed, none skipped**; the two full-suite skips were existing DSH tests.

**P184 — Open:** runtime semantics still use carrier inference, not the required first-request observation. Events/export lack the sent body.

Approve extending `noretry.js` with an `http.request` hook recording only `{sessionID, max_tokens}` under `<R>/data`, then using that evidence for row/manifest classification? This requires changing the original task’s explicitly byte-exact, one-line plugin requirement.