**BLOCKING** — 278 passed, 4 failed across 13 focused test files. Findings below are **VERIFIED** from code or tests; hypothetical inputs are failure scenarios, not observed campaign incidents.

- **B1 — Medium, introduced:** `benchmark/bench/provenance.py:1201`. `expand_portable` replaces tokens everywhere. A legitimate transcript directory `$STACK_WORKDIR/runs/$HOME/session` has its literal `$HOME` component rewritten on resume (`run_agentbench_os.py:193`), splitting transcripts across directories. **Minimal fix:** expand one leading, boundary-delimited placeholder only; preserve suffixes verbatim. Add literal-token and `$HOMEwork` cases.

- **B2 — Medium, failing regression tests:** `benchmark/bench/tests/test_run_agentbench_os.py:1972`, `:2047`, `:2076`, `:2133`. Four existing tests consume portable manifest paths as literal filesystem paths; one fails before exercising transcript preservation. **Minimal fix:** expand recorded paths before filesystem operations/comparisons, assert portable serialization separately, and redirect the resolver through test-local environment settings. Preserve the confinement guard.

- **B3 — Medium, incomplete sanitization:** `benchmark/bench/provenance.py:1190`. With home `/Users/x`, `"cwd=/Users/x"` remains unsanitized because the root neither equals the whole string nor ends with `/`. Conversely, `/backup/Users/x/ws` becomes `/backup$HOME/ws` because there is no leading boundary check. `/Users/xy/ws` is correctly preserved. **Minimal fix:** define boundary-aware replacement for embedded path tokens, including bare roots; test both boundaries. The “every occurrence” docstring currently overstates coverage.

- **B4 — Low, weakened test:** `benchmark/bench/tests/test_serving_state_drivers.py:140`. The always-raising gather stub now fails during preflight; `test_end_of_run_gather_no_longer_swallows_a_served_config_error` never reaches end-of-run gathering. **Minimal fix:** pass preflight, raise on the final gather, and assert the ladder actually ran. Other quarantine tests still provide coverage.

- **B5 — High, pre-existing residual:** `benchmark/bench/generate.py:591`. Transport exceptions become error rows and generation continues; after successful exit verification, line `630` announces completion. This violates the stated transport-abort rule and is unchanged by the digest fix. **Minimal fix:** distinguish transport failures and re-raise after any forensic recording; test that no subsequent request occurs.

Additional verified checks:

- `ExitGuard.__exit__` still verifies after `return 3` (`provenance.py:1401`). Stable preflight failure leaves no new artifacts; stable end-gather failure preserves pending results. Drift raises and quarantines tracked artifacts.
- Preflight performs filesystem/process/Git inspection, including safetensors **headers**, not weights (`quant_info.py:48`). Git calls lack timeouts (`provenance.py:1583`); the retention fallback can import MLX (`:549`). It is neither guaranteed cheap nor entirely side-effect-free; latency was not measured.
- Added hashes and `sdpa` do not alter inspected resume fingerprints or break dictionary-based consumers (`rowschema.py:24`, `provenance.py:383`, `scorecard.py:20`). Non-object manifests and missing results now return `False`. However, the unreadable-result docstring remains inaccurate for digestless manifests: `isfile()` alone returns `None` without checking readability (`provenance.py:706`).

No repository edits, servers, or benchmarks were run.
