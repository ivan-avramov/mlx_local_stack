**Dispositions of the opinion's findings**

1. **Registry TOCTOU: resolved.**
   - The registry is read once under the lock (`qualify.py.txt:1052`). That snapshot's bytes feed the gate, the derived and restored registries, and the sha.
   - `binding_problems` compares the live file's sha with the snapshot's sha before and after the job, so a later change refuses. `start` is taken with the snapshot, so a moved stack HEAD refuses too.
2. **`served_on` not bound to the certified configuration: resolved in the code.** The argv equality check (`certified_argv`, `argv_binding_problems`, `qualify.py.txt:199`) closes the gap. One caveat is in finding A below.
3. **Production comparison: resolved.** Both sides resolve to full shas in the fork and are compared for equality. An unresolvable value refuses.
4. **Registry names as paths: resolved.** `safe_id` and `out_path` keep every path under `--out`, and `out_dir` now uses them. No other `out / name` use remains.
5. **`mtp_off` removal: resolved.**
   - The code uses YAML node marks and the semantic-equality guard stays.
   - Flow style refuses, and a failure names the key and its line.
   - An anchor or merge key still refuses through the equality guard.
6. **"Served ON" by key presence: resolved, but it adds a crash path.** See finding B.
7. **`arm_for` restore without `name in registry_state`: resolved.**
8. **`rates` on a FAILED entry: resolved.** I accept the author's account that this is a test-only change.
9. **Style slip: resolved.** The spacing is fixed in the repair.

**New findings**

**A. The argv binding depends on `manifest.json` `picks[name].argv_on`, which the material doesn't show real P369 manifests carrying**
- **Location:** `qualify.py.txt:199–209` (`certified_argv`), `:300–311`.
- **Severity:** major. **Evidence:** hypothesis. The tests write `argv_on` themselves, and `orchestrate` isn't in the material.
- **Problem:** if real campaign manifests don't carry `argv_on` in that shape, every MTP-ON arm refuses.
- **Failure scenario:** the argv includes `--port 8091`. If the real P369 argv has a different port, a different `--model` spelling, or a different flag order, every real MTP-ON run refuses with "differs" or "no argv_on". The suite is green but the harness is unusable for its main purpose.
- **Proposed change:**
  - Confirm that `orchestrate` writes `picks[name].argv_on` into `manifest.json`, in that shape.
  - Add one test that loads a manifest produced by the real `orchestrate` writer, or its fixture.
  - Compare the argv with `--port` normalised (as `FIXED` does) and with order ignored, unless order is certified too.

**B. `serves_mtp` now calls `expected_config`, which can raise a non-`ValueError`**
- **Location:** `qualify.py.txt:64–70`; callers in `entry_problems` and `drive`.
- **Severity:** minor. **Evidence:** confirmed by tracing the source.
- **Problem:**
  - `expected_config` does `int(values["max_kv_cache_size"])`, and the same for `kv_bits`, `prefill_step_size` and `quantized_kv_start`. A registry key set to `null` makes `entry.get(k, default)` return `None`, so `int(None)` raises `TypeError`.
  - `entry_problems` catches only `ValueError`. Before the repair this failure was recorded per entry as `error` and the run continued.
  - `UnknownKey` is a `ValueError`, so it is fine.
- **Failure scenario:** a candidate entry has `kv_bits:` with an empty value. Before the repair that entry failed on its own. Now `drive` aborts with a traceback before the run, while holding the lock, and nothing is written to the report.
- **Proposed change:** catch `(ValueError, TypeError)` in `entry_problems` and report `<name>: <exc>`. Add a test with a null-valued key.

**C. Refusals now hold the run lock**
- **Location:** `qualify.py.txt:1048–1060`.
- **Severity:** minor. **Evidence:** traced, not reproduced.
- **Problem:** the pre-run refusals (unknown name, missing gate) now happen after `acquire_lock`.
- **Failure scenario:** a refused or mistyped invocation contends for, or fails on, the lock held by a long-running qualification. A bad invocation can no longer be refused while another run is in progress.
- **Proposed change:** this follows from v1.3's ruling that the snapshot is read right after the lock. If you want to keep it, state in the spec that refusals now require the lock, or have `acquire_lock` fail fast with a clear message.
