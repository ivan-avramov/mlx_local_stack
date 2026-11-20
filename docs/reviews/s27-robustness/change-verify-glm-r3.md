I have traced all the call chains. Here is my review.

---

# Change review round 3 of 3 — S27 robustness bundle, candidate 3 (fix round 2)

Traced the call chains in the working tree. All six adopted findings and both clarification items are resolved under the conditions the request supports (a normal macOS box). No blocker; no major. Two minor residuals below, neither a defect introduced by the diff.

## Y1 — anchored case requires an integer-0 `/metrics` sample — **resolved**

`p426_reconcile._open_step_at_signal` (`p426_reconcile.py:394-395`) now returns `None` unless `_is_int(late.get("in_flight_at_kill")) and late["in_flight_at_kill"] == 0`. `_is_int` is `type(value) is int` (`:246`), so `None`, `bool`, `str` and `float` are all refused. The guard sits at the top of the function, before any anchor is read, so an absent/malformed sample can no longer enter the anchored case. The `unpublished` shape (`:376-380`) already carried the same check, so Y1 closes the one shape that lacked it. Traced; the red test `test_y1_..._never_stands_in_for_a_missing_or_malformed_sample[absent/None/bool/str/float]` and the control both match the source. No check that protects the outcome is weakened — this strictly tightens a refusal.

## Y2 — docker launch `OSError` typed at the source; OOM inspection tri-state — **resolved**

- Launch: `structured_grade.grade` (`structured_grade.py:398-400`) wraps the Go-branch `OSError` as `GraderInfraError(kind="spawn")`; the Python branch keeps the plain `TransportAbort`. `GraderInfraError` subclasses `TransportAbort` (`token_turn_gate.py:51`), so `final_grade`'s regrade catch (`arm_runner.py:997-1000`, `tg.grader_infra_fault`) picks it up — regrade, no regeneration. The Python interpreter `OSError` stays an untyped abort (a regrade cannot fix a missing interpreter); this matches the ledger's scope.
- Inspection: `ProcessGuard.container_oom` (`proc_guard.py:1051-1069`) is tri-state. `TimeoutExpired`/`OSError` → `GraderInfraError(kind="transport")`; `rc != 0` or stdout not in `("true","false")` → same. An unverified state never reads as "not OOM". The raise propagates out of `grade()`; the `finally: guard.remove_container(name)` (`:437`) still runs, so the container is removed (the red test `test_y2_an_unverified_oom_state_never_scores_the_item` asserts `guard.removed`). The raised `GraderInfraError(kind="transport")` is regraded in `final_grade`.

No new kill is introduced; the change only types two existing failure sites. Traced.

## Y3 — reused session leader not claimed; owned survivors still bounded — **resolved**

`ChainOps.owned_scan` (`chain_ops.py:1002-1016`) reads the start of the live process whose pid == `sid` before any session claim:
- leader alive and `start == not_before` → `owner` stays → members claimed, bounded by `not_before` (`:1063`). ✓
- leader gone (`NoSuchProcess`) → `lead_start = None`, `owner` stays → members still claimed, bounded by the probe's start. ✓
- leader unreadable (`AccessDenied`/`SystemError`/`TransportAbort`) → a problem is added, `owner = None` → no session claim, scan `certain` is False → PAUSED. ✓ (conservative, no silent survivor)
- live leader with `start != not_before` → `session_reused` recorded, `owner = None` → no session claim. ✓

On the "owned survivor of a live probe session left unclaimed" hazard: the only path that drops a session claim is the `start != not_before` branch. That branch fires when the process now holding `pid == sid` is not the recorded probe. For an *original* session that still has surviving members, the kernel does not reassign `pid == sid` while the session is alive (the sid stays reserved until the session is empty), so a live non-probe leader at that pid means the original session is already gone — there are no original members to leave unclaimed. This is the implementer's stated reasoning (choice 3) and it is the standard PID/session allocation guarantee on macOS/Linux. The `path_only` extension (clarification 1) lists, never kills, so it cannot kill an unowned process.

Minor residual (hypothesis, not a defect): the soundness rests on the kernel guarantee above, which is not proven in the material; the red tests cover the alive-leader and unreadable-leader cases but not the "original leader dead + pid reused while members live" case (which the guarantee says cannot occur). I could not construct it on this box.

## Y4 — one accounting-sidecar validator binds slot / rerun / row / disposition / record — **resolved**

`p426_hooks.accounting_problems` (`p426_hooks.py:92-120`) is the single contract. It requires: sealed; `disposition == "accounting_fault"`; same `slot`; `rerun_index` an int equal to the attempt's; `row_sha256` equal to the committed row's (a missing row fails — `want is None` → problem); `item_record_sha256` equal to the item record's, or `None` only when a done-step failure is recorded for this slot attempt (reason text descriptive, never matched). Used by:
- the chain: `accounting_sealed_for` (`:145-163`) reads the sidecar via `lstat` (no symlink) and the item record from `items/`, then delegates; `chain_core.p426_write_accounting` (`chain_core.py:3266-3269`) passes the in-hand failure plus this slot attempt's earlier `p426_accounting` reasons as `recorded`.
- freeze: `p426_freeze._accounting_problems` (`p426_freeze.py:444-466`) via `ledger_row` + `recorded_accounting`; the missing-record branch (`:413-419`) applies only when the record file is absent (`lexists`), and a corrupt/unreadable record is refused, not treated as "none written".
- harvest: `p426_harvest._accounting_problems` (`p426_harvest.py:701-728`) reads the row from the inventoried rows file via `_read_regular` (no symlink) and the item record from the inventory (symlinks excluded at inventory per §7.1, so a symlinked record yields `item=None` → refusal).

Both chain writers (done-hook route `chain_core.py:3195-3210`, abort route `:2909-2916`) append to `self.p426_accounting` and persist it as `p426_accounting_faults` (`:1151`), so a sidecar sealed with no item record always has a recorded failure for freeze/harvest to find. No refusal is lost between chain, freeze and harvest — they share one validator. The match is stricter than candidate 2 everywhere (a missing row now fails where `None == None` used to pass). Traced.

## Y5 — interim infra fault recorded on every join path — **resolved**

`arm_runner._record_finish` (`arm_runner.py:1011-1018`) calls `worker.finish()` and, on a returned fault, `termination.setdefault("interim_grade_fault", …)`. `setdefault` preserves an earlier record. It is used on the main path (`:788`) and on the unwind's non-aborting join (`:968`); the bare `worker.finish()` is gone from `_run_item` (the red test's source check confirms `src.count("_record_finish(worker, termination") == 2` and no bare `worker.finish()`). The abort path (`:958-961`) keeps its own `abort_join` + `grade_cancelled`/`grade_fault_before_abort` recording, which is correct (that path is C365, not X3). Traced.

## Y6 — `foreign_new` and `path_only` basename capped at 64 — **resolved**

`proc_guard.FOREIGN_ARGV0_CAP = 64` (`proc_guard.py:45`); `foreign_new` scrubs first, then caps (`:917`). The `path_only` site in `owned_scan` (`chain_ops.py:1064-1067`) caps the raw basename with the same constant. Scrub-then-cap order means a truncation cannot split a pattern the scrubber would have caught; a basename has no `/`, so the path-prefix scrub at persist (`portable_doc`, `chain_core.py:189`) is unaffected by the cut. Public rowscarry identity only (pid, basename, argc / sid for `foreign_new`); no argument, path or environment value. Traced.

## Clarification 1 — Y6 extended to `path_only` — **resolved**

Covered above. The `path_only` basename is capped at 64; the entry stays identity-only and is never killed.

## Clarification 2 — faulted interim grade's boundary discharged — **resolved**

`GradeWorker.grading` (`arm_runner.py:211`) is set before a grade (`:268`) and cleared after `on_grade` (`:278`). In `finish()` (`:319-326`), when a returned interim fault is a `grader_infra_fault`, the boundary still in `self.grading` is removed from `gate.pending` and `gate.stall_wait` under the gate lock, then `self.grading = None`. No grade is recorded for it (`trajectory` unchanged). This runs only in `finish()`, after the client exited and before `gate.terminal` (`:788` then later). While the client still generates, the generation-time path (`check()`, `:296-302`) is unchanged — discharging in the worker thread could let the stall rule fire first and turn a rerun into a scored stall. The red test `test_c2_a_faulted_interim_grade_returned_at_finish_leaves_the_terminal_decision_unchanged` shows the faulted case reaches `stalled` exactly like the counterfactual control; the boundary is not left pending. No nonconvergence flag is wrongly changed — the discharge makes the faulted case behave as if the capture never graded, which is the correct counterfactual.

## Hazards check (the request's list)

- **A process the harness did not spawn killed:** Y2 adds no kill. Y3's `session_reused` records and does *not* kill the reused leader; `path_only` lists, never kills. No regression. ✓
- **An owned one left alive unrecorded:** Y3's unreadable-leader path adds a problem → `certain` False → PAUSED (no silent survivor). Under the kernel guarantee (Y3 residual above), the dead-leader + pid-not-reused path still claims members. ✓
- **A check that protects the outcome passing what it refused (Y1, Y4 across chain/freeze/harvest):** Y1 is strictly tighter. Y4's shared validator binds slot/rerun/row/disposition/record at all three sites; a missing row now fails everywhere. No check weakened. ✓
- **A nonconvergence flag changed by a faulted interim grade:** clarification 2 discharges only the faulted boundary, restoring the counterfactual. ✓
- **A refusal lost at push or harvest:** fix-2 does not touch `push_level`; Y4 makes freeze and harvest share the chain's validator, so a sidecar the chain refuses is refused at harvest too. ✓
- **Public data carrying more than identity:** Y6 caps basenames; `foreign_new`/`path_only` keep identity only. ✓
- **Heavier than its intent:** nothing over-built. Y4's shared validator is a consolidation (replaces two ad-hoc checks); Y3 is one targeted guard; Y2/Y5/Y1/Y6 are minimal. ✓

## Anything else the diff breaks or leaves failing

The one failing frozen test the implementer reports, `test_s27_fe_r1.py::test_x10_a_session_member_started_after_the_probe_is_ours_and_is_killed` (`test_s27_fe_r1.py:366-372`), is a known conflict with the adopted Y3, not a defect in candidate 3: it spawns a fresh session leader and passes `not_before = started_at - 10**6` (a start a million seconds *before* the leader), then expects that leader killed. Under Y3 a live leader whose start ≠ `not_before` is exactly a reused session → no claim. The test predates Y3 and pins X10's start bound alone; the test-writer is re-staging it (set `not_before` to the leader's own start, or spawn a non-leader member inside the probe's session). No version of Y3 can satisfy both this test and the ledger.

The implementer's combined-run `fixture 'kit' not found` errors in `p586_frozen/test_p586_harvest.py` are a collection-ordering artifact (the file passes in its own family invocation), not a code defect.

## Minor residuals (not defects introduced by the diff)

1. **Y3 soundness rests on a kernel guarantee (hypothesis).** `owned_scan`'s `start != not_before` → `session_reused` branch is safe only because macOS/Linux do not reassign `pid == sid` while the session has live members. This is standard but not proven in the material, and no test exercises the "original leader dead + pid reused while members live" path (the guarantee says it cannot occur). Location: `chain_ops.py:1011-1016`. Proposed change: none required for the request's supported conditions; optionally a one-line docstring note that the reuse branch assumes the kernel's sid-reservation, so a future reviewer does not "fix" it into a kill.

2. **`accounting_sealed_for` reads the item record via `lexists` + `read_text` (follows symlinks), while the sidecar path is `lstat`-guarded (no symlink).** Location: `p426_hooks.py:158-162`. In normal operation the chain wrote the item record exclusively, so it is a regular file; a symlinked replacement is an integrity attack, out of scope for this round. The asymmetry is minor and pre-existing for the item-record read; harvest's inventory already excludes symlinks so it refuses a symlinked record. Proposed change: optional — use `lstat`/`S_ISREG` for the item record read here too, for symmetry with the sidecar guard.

Both are minor; neither blocks merge under the request's supported conditions.

## Verdict

Y1–Y6 and both clarification items are resolved in candidate 3, traced through the call chains. No blocker, no major. The one failing frozen test is the acknowledged Y3 conflict the test-writer is re-staging. Nothing else of substance.

NOTHING OF SUBSTANCE
