# Proposal: transport failures abort — `generate` (C119) and the opencode probe (C124)

Status: PROPOSED 2026-10-06, awaiting operator approval. Nothing is built. Discussion ids P126–P132.
Rule being enforced (AGENTS.md): "HTTP/transport errors abort nonzero, never grade"; "Transport failures must abort"; retries = 0.

## The two defects (read from the code, 2026-10-06)

**C119 — `benchmark/bench/generate.py:623`.** One `except Exception` wraps the whole per-item body (parameter resolution, message
build, `probe_with_recovery`, row assembly). Everything except `ServedConfigError` becomes an error row and the loop moves to the
next item. Consequences:

- A dead or ghost-ready router turns every remaining queue item into a fast error row. The C106 exit check then fails, but the rows
  are on disk.
- A single HTTP 500 (worker OOM, Metal failure) on one item while the router survives: one error row, the run finishes, C106 passes,
  exit 0. At grade time that row is a strict FAILURE (O31) — a serving failure charged to the model. This is the path that violates
  the rule without any other tripwire firing.
- Harness bugs (a `KeyError` in row assembly, the vision-plus-depth `ValueError`) are recorded as "network/OOM" rows too.
- `client.preload` at line 527 is outside the `try` and already aborts — the behaviour is inconsistent inside one loop.

The one error row that is a legitimate measurement is the probe-timeout DNF (O35: elapsed ≥ 0.9 × the derived probe timeout; counted
as done on resume; a failure in `acc_strict`, O31). That stays.

**C124 — `benchmark/run_opencode_probe.py:1230–1298`.** After `_run_opencode` returns, the probe always exports, grades and appends a
row. `opencode_rc` is recorded but never read. Nothing distinguishes:

- a session opencode ended itself (`stop_reason == "completed"`) with exit 0,
- a session opencode ended with a nonzero exit (provider/HTTP error, crash) — possibly after an edit that makes the tests pass,
- a session the progress gate killed (`stalled` / `looping` / `hard_ceiling`; nonzero exit by construction) because the MODEL wedged,
- a session the progress gate killed as `stalled` because the ROUTER was gone and opencode sat retrying.

The last three are all appended and graded today.

## Evidence from the corpus (counted 2026-10-06, `benchmark/results/**`)

| population | count | read |
|---|---:|---|
| `generate` error rows with `error_kind: probe_timeout` | 36 | legitimate DNFs, unchanged |
| `generate` error rows with no `error_kind` | 58, in 18 files | every message is `timed out`; no connection-refused / HTTP-5xx row exists |
| opencode rows, `completed`, exit 0 | 625 (553 pass, 72 fail) | unaffected |
| opencode rows, `completed`, exit ≠ 0 | **0** | C124's exit-code path has never fired |
| opencode rows, gate-killed (`stalled` 86, `looping` 14) | 100 (1 `looping` row passed) | exit ≠ 0 by construction; router liveness at the kill was never checked |
| opencode rows with no `stop_reason` | 4 | pre-progress-gate rows |

Both gaps are latent in the committed corpus: no existing row is known to be a mis-scored transport failure, so this proposal asks
for **no regrade and no rerun**. The 58 legacy timeout rows keep their current treatment (retryable on resume, failures in
`acc_strict`). What cannot be recovered: whether the router was alive at each of the 86 `stalled` kills (the per-run C106 exit check
passed for every pooled row, which bounds but does not exclude a mid-run outage followed by a restart).

## Design

### P126 — one classification, fail-closed, in both drivers

| class | definition | action |
|---|---|---|
| **generation outcome** | the server answered, or the bound we set on the model was reached | row; graded; run continues |
| **gate outcome** (opencode only) | the progress gate killed the session AND the router was verified alive and unchanged immediately afterwards | row; graded as today; run continues |
| **transport / harness failure** | everything else | no row for the in-flight item; manifest stamped; exit nonzero; no further request or item |

The allowlist is the first two rows. Anything unrecognised is the third. A new failure signature that turns out to be a model
outcome gets added to the allowlist by its own ruling, never by default.

### P127 — `generate`

- Replace the broad `except` with: `ServedConfigError` → raise (unchanged); client timeout with `error_kind(elapsed, probe_timeout)
  == "probe_timeout"` → DNF error row, continue (unchanged behaviour, O35/O31); **every other exception → `TransportAbort`**
  (new `RuntimeError` subclass in `bench/client.py`, next to `MalformedResponseError`), raised out of `run()`.
- Before raising: stamp each manifest of the run with `transport_abort: {item, sample, error (scrubbed, ≤ 200 chars), elapsed_s,
  rows_on_disk}`; attempt the C106 exit check best-effort and record its result in the same stamp. No row is appended for the
  in-flight item, so a resume regenerates it under the same seed — the same outcome as today's retryable row, without the row.
- `run.py generate` already exits nonzero on an uncaught `RuntimeError`; a test pins that.
- A timeout that fires EARLY (elapsed < 0.9 × probe timeout — connect timeout, a stalled socket) is transport, not a DNF.
- Not changed: `probe_with_recovery`, the O35 ratio, resume semantics for legacy rows, `grade`.

### P128 — opencode probe

After `_run_opencode` returns and before export/grade:

1. `stop_reason == "completed"` and `rc == 0` and the export carries no provider/API error → generation outcome (today's path).
2. `stop_reason == "completed"` and `rc != 0` → transport/harness failure. Abort.
3. `stop_reason == "completed"`, `rc == 0`, but the session export records a provider/API error on any assistant message → abort.
   Reason: opencode retries provider errors internally; a retried request is a re-sample under retries ≠ 0, and the row would look
   clean.
4. Gate kill (`stalled` / `looping` / `hard_ceiling`) → run `provenance.assert_served_config_unchanged(router, oc_base)` right after
   the kill. Passes → gate outcome, graded as today. Raises → abort, drift stamp as today.
5. Abort = no row appended; the scratch log and export are copied to `$STACK_WORKDIR/opencode-probe/aborted/<run>/<item>/` (PII-scrubbed
   like transcripts); the manifest gets `transport_abort: {item, rc, stop_reason, signature}`; exit nonzero; the item loop does not
   continue. A `transport_abort` stamp does NOT block a later continuation (rows before it are clean; `served_config_drift` still does).

### P129 — measure opencode's failure signatures before writing the classifier (CPU only)

Rule 3 depends on how opencode 1.18.30 reports a provider error, which is not known from the code. Step 1 of the build, on the
existing mock-endpoint harness from C121 (`bench/tests/test_opencode_probe_seeding.py`), with the pinned binary, bench HOME, `--pure`:

| mock behaviour | record |
|---|---|
| connection refused from the first request | exit code, last log lines, export contents, wall time until exit |
| HTTP 500 on turn 2 | same, plus whether opencode retried and how many requests arrived |
| connection dropped mid-stream on turn 2 | same |
| HTTP 200 with an error envelope | same |
| HTTP 400 context-length error | same — the one candidate for a model-side outcome; default stays ABORT unless ruled otherwise |

The measured table goes into the lab notebook and becomes the classifier's fixture set. If opencode exits 0 with no recorded error
after a provider failure, rule 3 cannot be implemented from the export and falls back to counting requests at the mock/router —
that would be reported before building, not worked around.

### P130 — tests (failing first; mocked; no model)

`generate`:
- item 2 of 5 raises `URLError(ConnectionRefusedError)` → `TransportAbort`; exactly 1 row on disk; the probe was called exactly
  twice; `preload` not called again; manifest stamped; `run.py generate` exit ≠ 0. **Known positive: this test fails on today's
  code with 5 rows and 5 probe calls.**
- same for `HTTPError(500)`, `MalformedResponseError`, `ConnectionResetError`, `http.client.RemoteDisconnected`, a `KeyError`
  raised in row assembly, and a timeout at 0.1 × the probe timeout.
- a timeout at ≥ 0.9 × the probe timeout → `probe_timeout` row, items 3–5 still run (regression guard for O35).
- resume after an abort requests the aborted item first, with the same `sampler_seed`.

opencode probe (fake binaries as in the C121 tests):
- fake opencode edits the solution so the tests pass, then exits 1 → no row, the grade function is never called, one spawn only,
  manifest stamped, exit ≠ 0. **Known positive: today this writes `passed: true`.**
- exit 0 with a provider-error export (fixture from P129) → abort.
- gate kill with a healthy router → row graded exactly as today (byte-compare the row minus timestamps against the current output).
- gate kill with `assert_served_config_unchanged` raising → abort, no row.
- continuation after an abort re-runs the aborted item with the same seed and overlay hash; a `transport_abort` stamp does not
  refuse; a `served_config_drift` stamp still does.

### P131 — acceptance criteria

1. Every test in P130 red before, green after; the full benchmark suite green.
2. P129's table recorded with the pinned binary's sha; classifier fixtures derived from it, not from assumption.
3. One audit pass over every other driver's request path, reported as a table (`driver, catches, action`): `agent_loop.py:205` turns a
   transport exception into an `AO.SERVER_ERROR` outcome — AgentBench converts that to `TransportFailure`, but the frozen aider/dsh
   paths and `run_bfcl_fc.py` need a read. Findings become their own proposals; nothing outside the two files above is changed here.
4. One cold review each (Claude, Codex `gpt-6-astra`), self-contained prompts, each asked for a known positive it ran.
5. `benchmark/README.md` gains the classification table; AGENTS.md needs no change (the rule already says this).

## P132 — points where I recommend against the obvious alternative

- **Keep the probe-timeout DNF row.** Treating every timeout as transport would be simpler but reverses O35/O31 and costs ~2.4
  GPU-hours per known runaway on resume.
- **Do not make `grade` refuse legacy error rows.** All 58 are client timeouts from before `error_kind` existed; refusing them would
  force reruns of 18 files for rows that are, by their message, the same DNF class. After P127, a new non-DNF error row cannot be
  written, so the guard would only ever fire on history.
- **Abort on harness exceptions too**, not only network ones. A narrower "network errors abort, others row" rule keeps the current
  blind spot where a harness bug is scored as a model failure.
- **Context-length 400 stays an abort** until measured and ruled. On a 262144-token window it has not occurred in 730 opencode rows;
  silently converting it to a failed row would hide a harness-traffic problem the first time it does.

## Cost

CPU only; no model time; can be built while the stack is up. Estimated two build sessions (P129 measurement + `generate`; then the
probe), each with its review round.
