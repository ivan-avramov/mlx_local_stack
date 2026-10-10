VERDICT: FAIL

| Finding | Disposition | Evidence |
|---|---|---|
| P26 | **CONFIRMED-FIXED** | Invalid/empty baseURL values refuse at [provenance.py:855]($STACK_REPO/benchmark/bench/provenance.py:855). All five regression cases passed. |
| P27 | **CONFIRMED-FIXED** | Existing config mismatch refuses; previous PID and history survive at [run_opencode_probe.py:568]($STACK_REPO/benchmark/run_opencode_probe.py:568). Atomic replacement at line 599. Regression passed. |
| P28 | **NOT-FIXED** | Basic driver/child tests pass, but proxy normalization differs from the actual client at [provenance.py:615]($STACK_REPO/benchmark/bench/provenance.py:615). See P30. |
| P29 | **CONFIRMED-FIXED** | The item destination check precedes lazy manifest writing at [run_opencode_probe.py:613]($STACK_REPO/benchmark/run_opencode_probe.py:613). Refusal test confirms neither manifest nor rows exist. |

**P30 — BLOCKER: proxy handling can still verify one router while traffic goes elsewhere.**

At [provenance.py:615]($STACK_REPO/benchmark/bench/provenance.py:615), empty values are discarded and casing is merged by iteration order. Python’s actual proxy resolution gives lowercase variables precedence—including an empty lowercase value overriding uppercase.

Reproduced without network traffic:

```text
http_proxy=http://proxy.example:8888
NO_PROXY=*
no_proxy=
```

The tripwire **accepted PID 123**, but the actual `urllib.request.ProxyHandler` changed the request destination to **proxy.example:8888**. A conflicting, nonempty lowercase/uppercase combination also reproduced this.

Additionally, [provenance.py:618]($STACK_REPO/benchmark/bench/provenance.py:618) considers only `http_proxy`: `https://localhost:8000` with `https_proxy` passed verification while urllib selected the proxy and a CONNECT tunnel.

These are routing errors, not a check/use timing window. A proxy can reach a different serving configuration while the manifest names the locally verified router.

**Concrete fix:** resolve proxies using the applicable client’s precedence, preserve empty lowercase overrides, and select by destination scheme. For opencode, use its actual proxy semantics or refuse ambiguous combinations. Add regression tests comparing the guard’s decision with client routing, without sending requests.

**Hardening:** no additional findings.

**P31 — A1–A7 re-test**

| Criterion | Result | Evidence |
|---|---|---|
| A1 — Guard ordering and empty refusal outputs | **PASS** | Checks precede benchmark reads/results/requests: [generate.py:450]($STACK_REPO/benchmark/bench/generate.py:450), [run.py:127]($STACK_REPO/benchmark/run.py:127), [session_cache_probe.py:361]($STACK_REPO/benchmark/bench/session_cache_probe.py:361), [stack_smoke.py:176]($STACK_REPO/benchmark/bench/stack_smoke.py:176), [parity_replay.py:66]($STACK_REPO/benchmark/bench/parity_replay.py:66), [vision_gate.py:278]($STACK_REPO/benchmark/vision_gate.py:278), [run_opencode_probe.py:549]($STACK_REPO/benchmark/run_opencode_probe.py:549). Seven incident-injected entry tests passed. |
| A2 — Config resolution | **PASS** | Router cwd/HOME, realpath and file existence handled at [provenance.py:714]($STACK_REPO/benchmark/bench/provenance.py:714); corresponding path tests passed. |
| A3 — Refusal modes and destination ownership | **FAIL** | Missing/ambiguous/non-router owners and config mismatches refuse; no explicit bypass found. P30 nevertheless permits an unverified effective destination. |
| A4 — Accurate persisted attribution | **FAIL** | Storage, scrubbing, history and fingerprint exclusion tests pass; [provenance.py:1080]($STACK_REPO/benchmark/bench/provenance.py:1080) persists the verified block. Under P30, that block identifies the wrong traffic destination. |
| A5 — Test adequacy | **FAIL** | **125 focused tests passed.** Discovery tests exercise production parsers and lookup composition at [test_provenance_fingerprint.py:614]($STACK_REPO/benchmark/bench/tests/test_provenance_fingerprint.py:614). Proxy tests at line 874 omit conflicting casing, empty lowercase overrides and HTTPS. |
| A6 — Exact original incident | **PASS** | All seven entry paths refused an injected overlay/daily-driver mismatch. Live read-only verification accepted daily-driver PID **96795**, then refused the overlay driver environment. No HTTP requests sent. |
| A7 — Exceptions, discovery and API behavior | **PASS** | Restart refusal/refresh-failure tests passed; live macOS discovery worked. Per-process psutil plus lsof discovery is at [provenance.py:629]($STACK_REPO/benchmark/bench/provenance.py:629). |

Repository files were unchanged. Test artifacts stayed under `STACK_WORKDIR`.