VERDICT: FAIL

The exact incident is caught. Three remaining paths permit unverified routing or false router provenance.

| Round-3 finding | Round-4 disposition |
|---|---|
| **P5** | **CONFIRMED-FIXED** for the stated wildcard-family rules: [provenance.py:583]($STACK_REPO/benchmark/bench/provenance.py:583). IPv4 wildcard versus IPv6 destination regression passes. |
| **P7** | **CONFIRMED-FIXED**: program-position parsing at [provenance.py:556]($STACK_REPO/benchmark/bench/provenance.py:556) rejects the `http.server --directory /opt/mlx-serve` case. |
| **P6/P14/P20** | **NOT-FIXED completely**. Child cwd/env resolution and override-variable refusals are implemented at [provenance.py:805]($STACK_REPO/benchmark/bench/provenance.py:805), with per-item verification at [run_opencode_probe.py:589]($STACK_REPO/benchmark/run_opencode_probe.py:589). However, extracting `options.baseURL` does not always identify opencode’s effective destination; see P26. |
| **P21** | **CONFIRMED-FIXED** for previously attributed parity results: config changes refuse and PID changes preserve history at [parity_replay.py:73]($STACK_REPO/benchmark/bench/parity_replay.py:73). Zero-request regression passes. |
| **P22** | **CONFIRMED-FIXED** for the reported refresh failure: atomic replacement and fatal write errors at [generate.py:285]($STACK_REPO/benchmark/bench/generate.py:285); missing/unreadable restart manifests refuse at [generate.py:480]($STACK_REPO/benchmark/bench/generate.py:480). Injected `os.replace` failure stops after one probe and preserves the original manifest. |
| **P23** | **CONFIRMED-FIXED** for the named cases: parameters follow verification at [stack_smoke.py:175]($STACK_REPO/benchmark/bench/stack_smoke.py:175); leg-B destination verification precedes preload/staging at [session_cache_probe.py:359]($STACK_REPO/benchmark/bench/session_cache_probe.py:359). A separate ordering gap remains in P29. |

**P26 — NEW BLOCKER: empty/null opencode baseURL silently verifies the wrong port.**

[provenance.py:825]($STACK_REPO/benchmark/bench/provenance.py:825) returns `baseURL` without validating it. [Line 602]($STACK_REPO/benchmark/bench/provenance.py:602) converts both `""` and `None` into `http://localhost:8000`.

The pinned opencode instead falls back to `model.api.url` when the provider baseURL is empty/non-string; that URL can originate from `provider.api`. [Pinned provider implementation](https://github.com/anomalyco/opencode/blob/v1.18.15/packages/opencode/src/provider/provider.ts#L1592-L1611)

Reproduced with resolved configuration containing `options.baseURL: ""` or `null` and `api: "http://localhost:8123/v1"`: **the guard verifies port 8000**. This allows an overlay router on 8000 to pass while opencode targets a different router on 8123.

**Fix:** reject empty/non-string baseURLs before calling `assert_served_config`, or resolve the selected model’s final SDK destination. Add both fallback cases.

**P27 — NEW BLOCKER: opencode reruns overwrite historical router attribution.**

[run_opencode_probe.py:574]($STACK_REPO/benchmark/run_opencode_probe.py:574) unconditionally replaces the manifest, while [line 636]($STACK_REPO/benchmark/run_opencode_probe.py:636) appends rows.

Reproduced through `main()` with existing rows and **zero new requests**:

```text
before: router PID 111, config A, existing router_history
after:  router PID 222, config B, no router_history
existing rows: unchanged
exit: 0
```

This is P21’s attribution bug in another entry point.

**Fix:** inspect existing rows/manifest before replacement; refuse incompatible-config continuation and preserve prior router history for compatible continuation. Fail closed if required attribution cannot be persisted.

**P28 — NEW BLOCKER: inherited HTTP proxies bypass the verified destination.**

[provenance.py:749]($STACK_REPO/benchmark/bench/provenance.py:749) checks the URL’s local port, but the transport uses environment-aware `urllib.request.urlopen`, for example [client.py:24]($STACK_REPO/benchmark/bench/client.py:24).

With `http_proxy=http://proxy.example:8888` and no proxy exclusion, an in-memory transport interception produced:

```text
tripwire: verified local router PID 1234
HTTP connection destination: proxy.example:8888
request target: http://localhost:8000/v1/models/load
```

No network request was sent in this reproduction. The real transport would delegate routing to an unverified proxy; a remote proxy resolves `localhost` on its own machine.

**Fix:** bind benchmark traffic to direct transport, or refuse when the effective proxy configuration routes the destination through a proxy. Apply the policy to every transport and child environment.

**P29 — NEW HARDENING: per-item refusal can leave a newly written manifest.**

The neutral-cwd check passes, then [run_opencode_probe.py:574]($STACK_REPO/benchmark/run_opencode_probe.py:574) writes the manifest before the actual item’s destination check at [line 589]($STACK_REPO/benchmark/run_opencode_probe.py:589). A mismatching project config therefore refuses before model traffic, but fails the “nothing recorded” contract.

**Fix:** verify staged item destinations before publishing the result manifest. Temporary inspection/staging should be explicitly distinguished from recorded results.

**P30 — A1–A7 retest**

| Criterion | Result |
|---|---|
| **A1** | **FAIL, nonblocking ordering gap:** P29. Exact incident refuses before requests/result writes across all seven tested entry paths. |
| **A2** | **PASS within accepted scope:** router HOME/cwd, realpath and existing-file checks at [provenance.py:697]($STACK_REPO/benchmark/bench/provenance.py:697). Previously declined content-hash limitations remain. |
| **A3** | **FAIL:** P26/P28 allow the effective destination to differ from the verified destination. Named owner/config refusal cases pass. |
| **A4** | **FAIL:** P27 destroys historical attribution. Manifest insertion itself is correct at [provenance.py:1049]($STACK_REPO/benchmark/bench/provenance.py:1049); fingerprint independence tests pass. |
| **A5** | **FAIL on coverage completeness:** 116 tests pass, but omit P26–P29. Discovery tests exercise production functions; the [autouse owner fixture]($STACK_REPO/benchmark/bench/tests/conftest.py:207) means ordinary entry tests cannot establish real discovery correctness. |
| **A6** | **Exact incident PASS; overall FAIL:** all seven mismatch-entry tests pass, but P26/P28 permit routing variants. |
| **A7** | **PASS for the reported refresh-exception fix and observed local discovery.** Production discovery identified PID 96795 in approximately 0.07 seconds and refused a mismatched expected path. |

**P31 — Validation:** 116 focused tests passed, plus seven exact-incident entry-path retests. Adversarial reproductions established P26–P28. `git diff --check` passed; repository status remained unchanged. No repository files were modified, and no model requests or router restarts were performed.