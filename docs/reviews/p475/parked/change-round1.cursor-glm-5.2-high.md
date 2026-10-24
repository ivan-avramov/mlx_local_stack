I have enough to write my findings now.

---

## Findings

### 1. NOT_STARTED stops the run — a transient pre-check failure kills the 27-hour run
**Location:** `p475_kv.py:643-645` (`run()`'s `cell()`, the fall-through after `do_leg`); also `p475_kv.py:617-619` (resume path).
**Severity:** major.
**Problem:** The spec says "stop the run on the first INVALID leg (a speed-invalid leg is queued for replacement)." NOT_STARTED is a pre-check refusal (power, busy, gate, destinations) — the router was never started. The candidate treats NOT_STARTED identically to INVALID: `cell()` returns 1 (stop) and harvests the NOT_STARTED receipt. On resume, `read_verdict` returns NOT_STARTED and `harvested()` is True (the dossier exists), so `cell()` returns 1 again — the run cannot advance past a NOT_STARTED leg without the operator manually deleting the receipt and dossier.
**Failure scenario:** A 27-hour, 20-leg run is on leg 3. A cron job, an auto-launching helper, or a momentary battery dip (20.0 %) makes `busy_procs()` or `power_ok()` return false for 30 seconds. The leg is NOT_STARTED, harvested, and the run stops. Resuming re-reads the NOT_STARTED receipt and stops again. The operator must manually locate and delete the receipt + dossier to continue. A single transient condition defeats the entire run.
**Proposed change:** Distinguish NOT_STARTED from INVALID: a NOT_STARTED leg should be retried (with its own idle wait) up to a small bound, or at minimum not harvested as terminal evidence so a resume can re-attempt it. The spec's pre-check is per-leg; a transient refusal is not the "first INVALID leg" the spec says to stop on.

### 2. Watcher startup failure orphans the driver subprocess
**Location:** `p475_kv.py:518-526` (`run_leg`: `proc = deps.launch_driver(...)` then `stop_watch = deps.start_watch(proc.pid, leg)`); `p475_kv.py:555-564` (the `finally`).
**Severity:** major.
**Problem:** `start_watch` is called after `launch_driver` but before `proc.wait()`. If `start_watch` raises (watcher binary missing, import error, or the watcher exits during the 10 s startup loop — `make_start_watch` raises `RuntimeError`), the `except BaseException` catches it and the `finally` calls `ops.stop_stack()` (kills router/worker) but never kills or reaps `proc` (the driver). The driver keeps running with its 7200 s request timeout. The tests never exercise this: `Rig.start_watch` always succeeds.
**Failure scenario:** The arm worktree's `benchmark/m1/bench_watch.py` has a syntax error or a missing dependency. The first leg's watcher exits during startup. `run_leg` receipts INVALID ("watch daemon was never started"), `stop_stack` kills the router, but the driver (`python -m bench.run_capacity`) is still alive, holding its stdout file and process slot. It eventually exits on connection-refused, but is never reaped (zombie). If it hangs in a long in-flight HTTP request, it lingers for up to 2 hours.
**Proposed change:** In the `finally` block (or the `except`), if `proc` was launched and `proc.poll() is None`, `proc.kill()` and `proc.wait()` before `stop_stack`. Equivalently, wrap the driver lifecycle so every exit path reaps it.

### 3. Driver timeout receipts INVALID but does not kill the driver
**Location:** `p475_kv.py:524-526`.
**Severity:** minor (disclosed as judgement call #7, but the operational consequence is unstated).
**Problem:** On `TimeoutExpired`, `rc = None` and a problem is appended, but `proc` is not killed. `stop_stack` kills the router/worker; the driver's in-flight HTTP request may hang for up to `request_timeout` (7200 s) before `run_ladder` catches the connection error and exits. `proc` is then never reaped.
**Failure scenario:** A leg hangs at the 7-hour `cfg.timeout_s`. The leg is receipted INVALID and the stack is stopped, but the driver lingers. Over a 20-leg run with multiple timeouts, zombie drivers accumulate. `busy_procs` won't detect them (`run_capacity` is not in `BUSY`), so the next leg starts against a box still running orphaned drivers.
**Proposed change:** `proc.kill(); proc.wait()` in the `TimeoutExpired` branch before the `finally`.

### 4. The deciding block 3 is folded into the matrix mean and the "paired" ratios
**Location:** `p475_kv.py:749-769` (`build_matrix`), `p475_kv.py:386-396` (`ratios_vs_n16`).
**Severity:** minor.
**Problem:** The spec's Output says "per pick × arm × rung each block's value and the mean" and "the paired block ratios vs N16", with "two order-balanced speed-valid legs per arm". When a deciding block 3 is scheduled, `build_matrix` sorts all present blocks (`sorted({b ...})`) and includes block 3 in the mean and in the ratio columns. The "paired" ratio becomes 3-way and the mean is over 3 values, not 2. The deciding block is a tiebreaker for instability, not a third measurement leg; folding it into the mean changes the numbers the operator weighs.
**Failure scenario:** AF8's block-1 and block-2 decode ratios vs N16 are 0.95 and 0.93 (stable, no flag). Block 3 runs as the deciding block for a *different* arm but AF8 is also re-measured; its block-3 ratio is 0.70 (cold cache). The matrix reports AF8's mean decode ratio as 0.86 rather than 0.94, shifting the operator's Pareto read.
**Proposed change:** Exclude block 3 from the mean and the ratio columns (report it in a separate "deciding block" column or section), or document that the mean is over all run blocks when a deciding block ran.

### 5. `read_verdict` prefers a non-VALID receipt over a VALID one for the same leg
**Location:** `p475_kv.py:881-885` (`main()`'s `read_verdict`).
**Severity:** minor.
**Problem:** `bad = [v for v in verdicts if v != "VALID"]; return bad[0] if bad else "VALID"`. `write_receipt` never overwrites the canonical `{leg.name}.receipt.json`; a second write for the same leg name falls back to `.refused-<ns>.receipt.json`. If both a VALID canonical and a non-VALID refused variant exist, `bad[0]` returns the non-VALID one, masking the VALID result.
**Failure scenario:** The operator manually re-runs a single leg (deletes the canonical, but a `.refused-` variant from a prior crash persists). The new run writes a VALID canonical. `read_verdict` finds [VALID, OLD_INVALID] and returns OLD_INVALID, so `cell()` stops the run on a leg that actually succeeded.
**Proposed change:** Prefer the canonical receipt's verdict, or take the newest by file mtime, or only consider the canonical and ignore `.refused-` variants for `read_verdict`.

### 6. `kv_line_problems` crashes on a list input (known name/signature mismatch, but the seam is fragile)
**Location:** `p475_kv.py:189` — `(log_text or "").splitlines()`.
**Severity:** minor.
**Problem:** Production passes a string (`read_worker_log` returns `str`), so this works today. But the function's signature accepts whatever the `read_worker_log` seam returns; a future caller passing a list of log lines (as the frozen tests assumed) gets `'list' object has no attribute 'splitlines'` — an unhandled crash, not a clean refusal.
**Failure scenario:** A maintenance change swaps `read_worker_log` to return `Path.read_text().splitlines()` for line-level filtering. Every leg crashes in `kv_line_problems` with an `AttributeError`, receipted INVALID, and the run stops on leg 1.
**Proposed change:** `lines = (log_text if isinstance(log_text, list) else (log_text or "").splitlines())`.

### 7. `kv_line_problems` requires the `KV cache resolved:` line to carry `quantized_kv_start` exactly as `str(int(...))`
**Location:** `p475_kv.py:205-206`.
**Severity:** minor.
**Problem:** `got.get("quantized_kv_start") != str(int(entry.get("quantized_kv_start") or 0))`. The regex parses the value as `\S+`, so `0`, `0.0`, `0.5` would all be captured as strings. The check requires exactly `"0"`. If the server logs `quantized_kv_start=0.0` (float) or omits the field (None), the check fails: `None != "0"` or `"0.0" != "0"`.
**Failure scenario:** The fork's `KV cache resolved:` line format changes to emit `quantized_kv_start=0.0` (or drops it when 0). Every leg is INVALID on the KV-line check, and the run stops on leg 1 — with the actual cache correct.
**Proposed change:** Parse the value numerically and compare `float(got.get("quantized_kv_start") or 0) == float(entry.get("quantized_kv_start") or 0)`, mirroring the `kv_bits` numeric comparison above.

### 8. MATRIX.md overwrite not refused (spec spirit vs text)
**Location:** `p475_kv.py:793-798` (`_write_matrix`).
**Severity:** minor.
**Problem:** `_write_matrix` overwrites an existing `MATRIX.md` unconditionally. `harvest_leg` refuses an existing destination; `_write_matrix` does not. The spec says MATRIX is "generated from the harvested receipts and rows (never hand-copied)". The test-writer's report notes the frozen `test_generate_matrix_refuses_if_a_destination_exists` passes only incidentally. A hand-edited MATRIX.md would be silently clobbered on `--matrix-only`, destroying the operator's annotations with no record.
**Failure scenario:** The operator annotates MATRIX.md with a decision note. A re-run with `--matrix-only` (or the end of a fresh `run`) overwrites it silently.
**Proposed change:** Refuse if `MATRIX.md` exists unless a `--force-matrix` flag is passed, or write to `MATRIX.md.<timestamp>` and log the rotation.

### 9. Scope request: a per-leg retry bound for NOT_STARTED
**Location:** `p475_kv.py:599-649` (`run()`'s `cell()`).
**Severity:** scope request (no severity).
**Problem:** The spec's pre-check is per-leg and the run is 27 hours. A single transient refusal (finding 1) stops the run. The spec does not require a retry, but a small bounded retry for NOT_STARTED (e.g., 3 attempts with the 600 s idle between each) would make the run robust to transient conditions without masking a persistent one (which would still stop after the bound). This is beyond the spec's literal text but directly serves the request's "20+ legs on real hardware" intent.

---

**Summary:** The strongest findings are #1 (NOT_STARTED stops the run, unresumable) and #2 (watcher startup failure orphans the driver). Both are untested by the implementer's tests (the `Rig` and `Seq` mocks never fail `start_watch` and never produce NOT_STARTED from a transient condition), and both would surface on the first real run.
