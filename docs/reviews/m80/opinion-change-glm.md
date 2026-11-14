## Findings

### F1 — a marked test that errors at collection (not skips) can PASS the gate silently
**Location:** `mlx_local_stack/benchmark/bench/local_gate.py:419-432` (`_marked_problems`); `:120-131` (`ran_and_passed_from_junit`).
**Severity:** major.
**Evidence:** confirmed (traced in source).

`_marked_problems` builds `marked` from the union of the `--collect-only -m requires_mlx_serve` listing and junit `<property>` entries, then requires every marked id to be in `passed_ids`. `passed_ids` comes from `ran_and_passed_from_junit`, which only returns ids whose testcase has no `skipped`/`failure`/`error` child. A test that **errors during collection** (an `--collect-only` listing still reports it as a node id, but pytest's junit emits it as a `<testcase><error>`/`<failure>` entry, or omits the property) is excluded from `passed_ids` → it would be flagged "skipped". That part is fine. But the listing step itself runs `pytest --collect-only -m requires_mlx_serve` in the scratch; if that listing **errors** because the marked module fails to import (which is exactly what happens when mlx-serve is missing or its venv is broken), `_marked_problems` returns `[f"{SIBLING_MARKER} listing: rc {rc}"], [], out` — `marked = []`, and the only problem is the listing rc. The pytest step itself, however, runs first with `mlx_vlm/tests` (no `-m`), and a collection error there produces rc != 0 → `pytest: rc N` → FAIL. So in the common path the run already FAILs at pytest.

The gap is the **paired run whose fork venv imports cleanly but the sibling venv is half-built**: the `sibling-sync` step (`uv sync --frozen --all-extras`) succeeding does not guarantee `import mlx_serve` works at pytest time. If the marked tests then **skip via `pytest.skip()` inside the fixture** (the M76 B2 pattern: they call `make_stack_root` / `real_command` and skip when mlx-serve is absent), the junit carries `<skipped>` and the listing still collects them → the check fires. But if a marked test **xpasses via `xfail`** (the implementer's run reports `22 xfailed` in the full suite), an `xfail` testcase has neither `skipped` nor `failure` nor `error` in junit (it has `<properties>` with `xfail`), so `ran_and_passed_from_junit` returns it as **passed**. A marked test that is `xfail`-ing today would count as passed and the gate stays green even though it did not actually run successfully.

**Failure scenario:** a contributor marks a B2 test `requires_mlx_serve`, the test is written as `@pytest.mark.xfail(reason="serve flaky")`, mlx-serve is broken in the sibling so the test xfails. Receipt is PASS; the marker rule never fires.

**Proposed change:** in `ran_and_passed_from_junit` (or in `_marked_problems` only), treat a marked test whose junit entry carries `xfail`/`xpass` as not-passed for the marker rule; or have `_marked_problems` intersect the listing with the junit's actually-ran (non-skipped, non-xfail) ids rather than the broad `passed_ids`.

---

### F2 — the unpaired-PASS path (P2 deviation) lets a fork with zero marked tests PASS without mlx-serve
**Location:** `mlx_local_stack/benchmark/bench/local_gate.py:447-448` (the `paired = … if (mlx_serve_sha or (live.parent / SIBLING).exists()) else None`), `:462`, `:528`.
**Severity:** minor (the real fork has 146 marked tests, so the real path is safe; the deviation is from the literal spec wording).
**Evidence:** confirmed (traced; covered by `test_with_no_mlx_serve_checkout_the_run_is_unpaired_and_says_so`).

When `../mlx-serve` does not exist and no `--mlx-serve-sha` is given, `paired = None`, `receipt["paired"] = {}`, no `sibling`/`sibling-sync` steps, and `_marked_problems` still runs. The spec's Interfaces says "refuse (GateError) when that sha is not a commit in `../mlx-serve`" — the candidate only refuses when the directory exists or a pin is asked for. The implementer's P2 argues this is to keep `test_t3_frozen_gate` (fake forks with no sibling) green.

**Failure scenario:** an operator runs `bench.local_gate run --repo mlx-vlm` from a checkout whose sibling `../mlx-serve` was deleted (or never cloned). The run is unpaired, the fork has zero `requires_mlx_serve` tests (e.g. a fork branch that removed the B2 files), and the receipt is PASS with `paired: {}`. The Goal's "a PASS receipt shows the mlx-serve-dependent fork tests ran" holds vacuously, but the literal refuse-rule is violated.

**Proposed change:** this is a scope decision, not a code defect. If you want the spec literally, refuse when `../mlx-serve` is absent for an mlx-vlm run and update the frozen `t3_frozen_support.gate_run` to create a sibling. The implementer's recommendation (keep the deviation) is reasonable for the real fork.

---

### F3 — the pairing pin can be stale and the receipt still PASSes (by design, but unstated hazard)
**Location:** `mlx_local_stack/benchmark/bench/local_gate.py:285-302` (`pinned_mlx_serve`), `:810-811` (`_stack_repo`).
**Severity:** minor (hazard, not a defect — the spec says "the pairing is evidence, not a key").
**Evidence:** confirmed.

The default pin is the `src/mlx-serve` gitlink of `_stack_repo()`'s HEAD — the operator's stack checkout, not the fork's recorded dependency. The pre-push `check_lines` accepts a PASS receipt regardless of `paired` sha. So an operator whose stack checkout is behind gets a receipt paired against a stale mlx-serve, and the push passes. This is the spec's explicit choice ("a later stack bump's own gate re-runs the stack against both"), so it is not a blocker, but the receipt's `paired` is weaker evidence than the Goal implies: it records "the mlx-serve commit the fork was tested against" only in the sense of "the stack HEAD's gitlink at run time", not "the mlx-serve the fork's tests actually exercised."

**Failure scenario:** stack HEAD gitlink pins mlx-serve `A`; the fork's tests were actually written against mlx-serve `B` (newer API). The gate clones `A`, the marked tests pass against `A`'s old API, receipt PASS. The fork is pushed; downstream the stack bumps to `B` and the marked tests now fail.

**Proposed change:** none required by the request; if you want stronger evidence, record the sibling's `git rev-parse HEAD` after `sibling-sync` (which equals the pin) and surface a warning when the pin differs from `../mlx-serve`'s HEAD. (The test `test_a_paired_run_clones_the_sibling_at_the_pin_beside_the_fork_and_records_it` already asserts `sibling_head == s1`, so the pin, not the sibling HEAD, is used — correct.)

---

### F4 — `steps_for` pairing depends on the scratch directory's *name*, not on a real pairing flag from `run`
**Location:** `mlx_local_stack/benchmark/bench/local_gate.py:187-212` (`is_paired_layout`, `steps_for`).
**Severity:** minor.
**Evidence:** confirmed (the testwriter's F1; the implementer's P1).

`steps_for("mlx-vlm", scratch, …)` adds `sibling`/`sibling-sync` only when `scratch.name == "mlx-vlm"` (or `paired=True`). `run()` always passes `paired=paired is not None` explicitly, so the real gate is unaffected. But any future direct caller of `steps_for("mlx-vlm", <path not named mlx-vlm>, …)` silently gets the unpaired step list. The spec's Interfaces says "`steps_for("mlx-vlm", …)` gains, after `clone` and before `sync`: `sibling` … `sibling-sync`" — unconditionally. The deviation exists only to keep `test_fork_steps_order_and_audits` (`test_local_gate.py:241`, requires `names[:4] == ["clone","upstream","sync","extras"]`) green.

**Failure scenario:** a future helper calls `steps_for("mlx-vlm", tmp/"scratch", …)` to render the plan, gets the old step list, no sibling steps, and acts on it.

**Proposed change:** make `paired` default to `True` for mlx-vlm in `steps_for` (the spec's literal reading) and update `test_fork_steps_order_and_audits` to pass `paired=False` or to expect the sibling steps. The implementer's P1 recommends the opposite; the testwriter's F1 recommends accepting. This is a scope decision.

---

### F5 — the marker listing runs through the `runner` seam, so a fake runner can hide a real-collection failure
**Location:** `mlx_local_stack/benchmark/bench/local_gate.py:421-432`; tests `test_m80_impl_gate.py:299-321`.
**Severity:** minor (test gap, not a production defect).
**Evidence:** confirmed.

`_marked_problems` invokes the listing via `runner(argv, scratch, {})`. In production `runner=_real_runner` this is a real subprocess. The tests use a `Runner`/`SibRunner` that returns canned listing text, so no test exercises the real `pytest --collect-only -q -m requires_mlx_serve` output shape against `marked_from_listing`. The implementer and testwriter both ran the real command manually (146 collected), but there is no regression test that pins the real pytest output format. If a future pytest version changes the `--collect-only -q` summary wording (e.g. drops `tests collected` for `items collected`), `marked_from_listing` would raise `GateError` and every mlx-vlm run would FAIL with `requires_mlx_serve listing: …`.

**Failure scenario:** pytest upgrades, the summary line no longer matches `^(\d+)(?:/\d+)? tests? collected`, every mlx-vlm gate run FAILs on the listing parse.

**Proposed change:** add a test that feeds a realistic captured pytest `--collect-only -q` transcript (header, node ids, summary) through `marked_from_listing` and asserts the ids; or relax the count check to a warning when the summary line is absent.

---

### F6 — the policy digest changes for stack and mlx-serve too, invalidating their existing receipts (expected, but unflagged)
**Location:** `mlx_local_stack/benchmark/bench/local_gate.py:86-91` (`policy_digest` over `_gate_source()`).
**Severity:** minor (by-product, not a defect).
**Evidence:** confirmed.

`policy_digest` hashes the whole gate source for every repo. The M80 edit touches `local_gate.py`, so the digests for `stack` and `mlx-serve` also change, and every existing PASS receipt for them becomes unaccepted by `check_lines`/`push_level`. This is the normal "any gate change invalidates all receipts" behaviour, and the spec's Non-goals says the stack gate is unchanged in *behaviour*. But the implementer's report does not call out that a stack/mlx-serve re-run is needed after this change before the next push.

**Failure scenario:** operator applies the candidate, pushes a stack commit without re-running `bench.local_gate run --repo stack`; `check` refuses with "no PASS gate receipt under the current policy."

**Proposed change:** note in the commit message that stack and mlx-serve receipts must be regenerated; no code change.

---

### F7 — `dirty` is skipped for `sibling`, so a sibling-sync that mutates the sibling clone is not detected
**Location:** `mlx_local_stack/benchmark/bench/local_gate.py:498` (`if step.name not in ("clone", "submodules", "sibling") and dirty(...)`).
**Severity:** minor.
**Evidence:** confirmed.

The `dirty` check (which catches a step leaving tracked files modified in the *fork* scratch) is suppressed for `sibling`. `dirty(scratch, step.name)` is called with the fork `scratch`, not the sibling `step.cwd`, so it would never see sibling mutations anyway. The suppression is therefore harmless for the fork, but it also means a `sibling-sync` that writes into the fork clone (e.g. an editable install pointing back at the sibling) would not be caught. This is a latent gap, not a current failure.

**Proposed change:** if you want sibling cleanliness checked, call `dirty(step.cwd, step.name)` for `sibling-sync`; otherwise leave as-is.

---

### Scope requests (beyond the request, no severity)

- **S1:** The candidate's marker listing combines junit `<property>` and `--collect-only` (stricter than the spec, which names either). This is a beneficial extension; consider stating it in the spec so it is not "rolled back" by a future change.
- **S2:** The candidate accepts `rc=5` from the listing as "nothing selected, not a problem." The spec does not mention rc 5. Reasonable, but undocumented.

---

### Summary

The real-gate path (`bench.local_gate run --repo mlx-vlm` on the real fork, then `check`) is sound for the common case: the fork has 146 marked tests, the sibling is cloned at the stack HEAD gitlink, the marked tests run, and a skip is caught. The pre-push levels for stack and mlx-serve are unchanged in behaviour. The most material issue is **F1** (xfail marked tests count as passed), which is a real way for a marked test to "not run" while the receipt stays PASS. F2/F4 are spec-wording deviations the operator already ruled on (P1/P2). F3 is by-design evidence. F5/F6/F7 are minor test/process gaps.
