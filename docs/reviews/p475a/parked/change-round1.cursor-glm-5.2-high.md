I have enough. Writing findings now.

---

## Findings

### 1. MAJOR — Tests: every `qualify --kv-arm` driver test mocks `classify_kv_arm`; the real classifier is never driven through `qualify`.

**Location:** `mlx_vlm/tests/test_p475a_qualify_kv_arm.py:267-288` (`_drive_arm`), and `review/frozen_test_p475a_frozen.py:223-298` (`_drive_kv_arm`).

**Problem:** Both test harnesses `monkeypatch.setattr(registry_states, "classify_kv_arm", lambda text, fx, entry: ...)` to a stub returning a fixed `(off, delta)`, and stub `classify` to raise. No test calls `qualify.drive` with the *real* `classify_kv_arm` against a registry the real classifier actually accepts. The spec's AC2 ("expected manifest from the arm", "no `classify` path left under `--kv-arm`", "the `mtp_off` check uses the arm's off set") is therefore asserted only against a mock, not against the code path the orchestrator will hit.

**Failure scenario:** A future edit to `_classify_docs` or `classify_kv_arm` that makes it return `None` for a valid arm (e.g., a regression in the `KV_ARM_KEYS` replacement) would refuse every real arm worktree, but the driver tests would still pass because the mock returns a canned `(off, delta)`. Conversely, a regression where `drive` stops calling `classify_kv_arm` and falls back to `classify` would also pass — the `forbidden` spy is on the module attribute, and the mock already shadows it.

**Proposed change:** Add one driver test that builds a real arm registry (`_arm_text`) as the live `main_models.yaml`, does NOT mock `classify_kv_arm` or `classify`, and asserts: the run completes, `report["kv_arm"]` has the right delta, and a spy on `rs.classify` records zero calls.

---

### 2. MAJOR — Tests: no test proves the served argv follows the arm.

**Location:** `test_p475a_qualify_kv_arm.py:540-548` (mocks `t415._cmd`); `frozen_test_p475a_frozen.py:296-298` (mocks `qualify.full_command` via `t415._cmd(block)`).

**Problem:** `qualify.full_command` runs mlx-serve's `_build_command` on the registry path; under `--kv-arm` the path is the live arm registry (`qualify.py:1010-1011`, `arms[name] in ("served","mtp_off")`). Every driver test replaces `full_command` with a hand-built command. The spec explicitly names "the served argv ... follow the arm" as something to check. No test asserts that the argv built from an arm registry carries the arm's `--kv-bits` / `--kv-quant-scheme` and that `command_problems` accepts it.

**Failure scenario:** An arm worktree whose `_build_command` emits a stale or default KV flag (e.g., the arm commit changed `kv_bits` but mlx-serve reads a cached config, or the registry path passed is the wrong one) would pass `command_problems` in tests (the mock command is hand-built to match) but fail in the field with a confusing "argv lacks --kv-bits" refusal.

**Proposed change:** Add a test that runs `command_problems(expected_config(arm_entry), <argv built from arm_entry via the real _build_command flag spelling>)` for each of the five arms, asserting `[]`. At minimum, assert that `expected_config(arm_entry)["flags"]` contains exactly the arm's `--kv-bits`/`--kv-quant-scheme` for each arm.

---

### 3. MAJOR — Tests: the attention rule is never proven through the driver on a real arm.

**Location:** `test_p475a_qualify_kv_arm.py:227-263` (AC0 unit tests on `request_problems` with hand-built records); `_drive_arm`'s `good`/`native` run_job returns a hand-built record with a fixed `sdpa_forced=0`.

**Problem:** AC0 is tested only at the `request_problems` unit level and only with records the test fabricates. No test runs the driver end-to-end where the worker's actual `sdpa_forced` (from the served model under the arm's KV format) is checked against the arm's expected manifest. The spec's AC0 ("AF8/AF4 ... pass with `sdpa_forced == 0`") is a statement about the live run, not just the unit.

**Failure scenario:** A real AF8 arm where the worker still forces SDPA (because the server didn't actually engage the affine path) would be caught by `request_problems` in the field, but no test pins the driver→`request_problems` contract for it; a regression that loosens the attention check (e.g., dropping the `and native_attention` clause) would make the field run silently accept a wrong engagement, and the unit tests would catch the unit but the driver-level guard is unproven.

**Proposed change:** Add a driver test where `run_job` returns a record whose `sdpa_forced` is WRONG for the arm (e.g., `sdpa_forced=640` for an AF8 arm) and assert the entry is NOT COMPLETED with an `sdpa_forced` problem — through the real `request_problems`, not a mock.

---

### 4. MAJOR — Candidate: `native_attention` defaults to `True`, so a fused_v1 affine arm with a missing manifest/template is flagged with a spurious `sdpa_forced` problem.

**Location:** `qualify.py:382` (`native_attention = True`), `qualify.py:405-409` (the `fused != (forced > 0)` check).

**Problem:** `native_attention` is set to `True` before the `if not observed or not template:` guard and only re-computed inside the `else`. For a fused_v1 affine arm (AF8/AF4 on Fable) whose record lacks a manifest or template, the guard appends "no leaf manifest / template of the measured cache" AND, because `native_attention` stays `True`, `fused = True` so `sdpa_forced == 0` is also flagged as a problem. The second problem is wrong: the arm's expected manifest has no native leaf, so `sdpa_forced == 0` is the correct state. <!-- allow-shorthand: verbatim reviewer output -->

**Failure scenario:** On a real arm run, the worker fails to record the per-layer manifest (a worker bug or a crash before the manifest is captured). The operator reads the report and sees "sdpa_forced 0 (attention fused_v1)" as a *cause*, masking the real "no leaf manifest" cause, and may chase the attention path instead of the recording path. The entry fails either way, but the diagnosis is misleading.

**Proposed change:** Move `native_attention = False` as the default (or `None`), and only set it inside the `else` branch. Then a missing manifest yields only the manifest problem; the `fused != (forced>0)` check with `native_attention=False` would flag `sdpa_forced>0` for an affine arm, which is also correct. Alternatively, skip the attention check when the manifest/template is absent.

---

### 5. MAJOR — Candidate / Tests: the `quantized_kv_start` guard in `classify_kv_arm` is dead code; the `type(start) is not int` clause is stricter than the spec and untested through the stated path.

**Location:** `registry_states.py:321-324` (`if not _kv_arm_valid(arm) or type(start) is not int or start != 0: return None`).

**Problem:** `quantized_kv_start` is not in `KV_ARM_KEYS`, so `_classify_docs` already returns `None` for ANY `quantized_kv_start` that differs from the fixture's int `0` (type-aware `_same`). The `if delta:` block in `classify_kv_arm` is only reached when the arm matches the fixture except for KV keys — which means `quantized_kv_start` already equals int `0`. So `type(start) is not int` and `start != 0` are both unreachable. The frozen/implementer tests `test_quantized_kv_start_must_stay_zero` / `test_quantized_kv_start_nonzero_refuses` all pass via `_classify_docs` returning `None`, not via this guard. The `type(start) is not int` clause would refuse a hypothetical `0.0` arm on type alone — stricter than the spec's "must stay 0" (`0.0 == 0` is True) — but it is dead, so no real arm is affected.

**Failure scenario:** A maintainer reads the spec ("`quantized_kv_start` must stay 0"), sees this guard, and trusts it as the enforcement. They later relax `_classify_docs` (e.g., add `quantized_kv_start` to a tolerated set), assuming the guard still catches it — but the guard's `type(start) is not int` would then refuse a valid `0.0` arm, or the guard would be the only thing catching a non-zero start with a brittle type check.

**Proposed change:** Either drop the dead `type(start) is not int or start != 0` clause (the spec's guarantee is already enforced by `_classify_docs`), or keep `start != 0` and drop `type(start) is not int` to match the spec exactly, and add a test that reaches this branch by constructing an arm where `_classify_docs` passes but `quantized_kv_start` differs (currently impossible, which proves the guard is dead).

---

### 6. MINOR — Candidate: `caps =rec.get(...)` missing a space after `=`.

**Location:** `qualify.py:395`.

**Problem:** PEP 8 / black violation. The implementer noted black/isort was not run.

**Failure scenario:** A black-enforcing CI gate (the fork's `run_fork_tests.sh` may not run black, but the stack's CI might) fails on the production diff if this file is ever copied. No functional impact.

**Proposed change:** `caps = rec.get("capacities_by_path") or {}`.

---

### 7. MINOR — Tests: the 4 frozen-test failures in `TestQualifyKvArmReport` are helper defects, not candidate defects.

**Location:** `frozen_test_p475a_frozen.py:296-298` (`full_command` mock reuses `t415._cmd(block)` which returns a hardcoded STATIC command for arm blocks) and `:401` (delta tuple-vs-list after JSON round-trip). <!-- allow-shorthand: verbatim reviewer output -->

**Problem:** The test writer's report already identifies these as helper bugs. I confirm: the candidate's `command_problems` correctly flags the mismatched mock command, and the `kv_arm` field shape matches the spec (`{"entry": ..., "delta": ...}`) with lists after JSON round-trip. These 4 failures are not spec violations.

**Proposed change:** Fix the helper's `full_command` mock to build the command from `expected_config`'s flags (as the implementer's `_drive_arm` does), and compare `delta` as lists.

---

### Scope requests (requirements I would add beyond the request; no severity)

- **SR1:** A single end-to-end driver test (no `classify_kv_arm` / `classify` / `full_command` / `run_job` mocks beyond the worker boundary) that builds a real arm registry, runs `qualify --kv-arm --predictor off --entry <pick>` for one arm of each attention class (affine, native, TurboQuant), and asserts the entry COMPLETED with the arm's `kv_arm.delta`, the arm's `--kv-bits` in the served argv, and the arm's `sdpa_forced` rule. This is the only test that would catch a regression in the integration the orchestrator actually depends on.
- **SR2:** A test that `classify_kv_arm` accepts an arm built on a base where a *non-tested* entry is MTP-ON (one of the 16 states that is not all-OFF and not the pick-OFF base already covered), to pin the "any accepted state" half of the refusal boundary. (The existing `test_an_arm_on_top_of_an_mtp_off_state_is_accepted` covers pick-OFF + others-ON; an others-OFF + pick-ON base for a *different* pick's arm would close the remaining corner.)

---

Nothing else of substance: the `mtp_off` check correctly reads `off_entries` from `classify_kv_arm` (`qualify.py:1005-1009`); the `kv_arm` report field is recorded before the per-entry loop and survives entry failure (`qualify.py:936-937`); the reference label is added only on a COMPLETED entry and never refuses (`qualify.py:585-589`, guarded by `if rec and not error and not problems` at `:1076`); without `--kv-arm` the gate uses `classify` and the attention rule reduces to today's for the committed registries (N16→native leaf→forced, TQ4+auto→not fused→no forced); the refusal boundary for a second entry, a non-KV key, an unknown entry, and unparseable text is correctly `None`.
