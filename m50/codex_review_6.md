VERDICT: FAIL

**P30 — CONFIRMED-FIXED for the reported cases.** Environment precedence, empty lowercase overrides and `REQUEST_METHOD` handling match CPython at [provenance.py:608]($STACK_REPO/benchmark/bench/provenance.py:608). Child case-conflicts refuse at [provenance.py:637]($STACK_REPO/benchmark/bench/provenance.py:637). All four new tests passed; an independent **504-case comparison** also matched CPython.

**P32 — NEW BLOCKER: inconsistent URL normalization bypasses HTTPS proxy detection.**

[provenance.py:797]($STACK_REPO/benchmark/bench/provenance.py:797) determines the scheme using raw `startswith`, whereas the host/port parser and urllib accept leading whitespace.

Reproduced without network traffic:

```text
MLX_SERVE_BASE=' https://localhost:8000'
https_proxy=http://proxy.example:8888
```

With a matching fake router, the guard **accepted PID 123**. Actual `urllib.request.ProxyHandler` selected **proxy.example:8888**, with tunnel destination `localhost:8000`. The guard incorrectly checked `http_proxy`; traffic can escape the verified router while retaining its attribution.

**Fix:** derive scheme, host and port from one consistent URL parse, or reject noncanonical URLs before verification. Add this client-routing regression.

**P33 — NEW HARDENING: port-specific bypasses falsely refuse.**

At [provenance.py:649]($STACK_REPO/benchmark/bench/provenance.py:649), bypass matching receives only the hostname. With `http_proxy` set and `no_proxy=localhost:8000`, the guard refuses `http://localhost:8000`, although urllib connects directly.

**Fix:** match against the request authority, including its port. This is an availability issue, not false attribution.

**P34 — A1–A7 assessment**

| Criterion | Result | Evidence |
|---|---|---|
| A1 — Ordering and refusal outputs | PASS, regression check | Entry/refusal tests passed; guard remains before precheck and writes at [generate.py:450]($STACK_REPO/benchmark/bench/generate.py:450). |
| A2 — Config resolution | PASS, regression check | Path tests passed; router cwd/HOME and existing-file resolution at [provenance.py:743]($STACK_REPO/benchmark/bench/provenance.py:743). |
| A3 — Refusal and destination ownership | **FAIL** | Named refusal cases pass; P32 permits an unverified effective destination. |
| A4 — Accurate attribution | **FAIL** | Storage/history/scrubbing/fingerprint tests pass, but P32 can supply incorrect attribution to [provenance.py:1110]($STACK_REPO/benchmark/bench/provenance.py:1110). |
| A5 — Test adequacy | **FAIL** | **129 focused tests passed**, including P30 coverage at [test_provenance_fingerprint.py:908]($STACK_REPO/benchmark/bench/tests/test_provenance_fingerprint.py:908). P32/P33 are missing cases. |
| A6 — Original incident | PASS, regression check | Config-mismatch test passed at [test_provenance_fingerprint.py:488]($STACK_REPO/benchmark/bench/tests/test_provenance_fingerprint.py:488); entry guards show no regression. |
| A7 — Exceptions/discovery/API | PASS, regression check | Discovery and fatal restart/refresh tests passed; refresh failures escalate at [generate.py:303]($STACK_REPO/benchmark/bench/generate.py:303). |

Previously declined items remain declined. Repository files were unchanged; temporary test artifacts stayed under `STACK_WORKDIR`. No model requests were sent.