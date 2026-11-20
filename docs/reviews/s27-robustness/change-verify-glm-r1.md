 I've gathered enough to report. Let me verify the one confirmed defect by checking the `write_exclusive` mkdir behavior and the catch site once more, then deliver findings.

The key facts I've confirmed by tracing the source:

1. `p426_hooks.write_exclusive` (lines 56-62) calls `path.parent.mkdir(parents=True, exist_ok=True)` **before** `os.open(..., O_EXCL)`. `Path.mkdir(exist_ok=True)` raises `FileExistsError` when the parent path exists as a **non-directory** (e.g. a file shadowing `items/`).
2. `chain_core.p426_write_accounting` (lines 3264-3273) catches `FileExistsError` broadly and returns `True` ("the hook already sealed it for this attempt") for **any** `FileExistsError`, including the one from `mkdir`.
3. The frozen test `test_a_done_hook_infrastructure_error_with_an_unwritable_sidecar_pauses_the_leg` (test_s27_fe_chain.py:298-309) shadows `items/` with a file and asserts the leg PAUSES; the candidate continues instead. The testwriter report confirms this is the one (D) defect, left unamended, and that the read-only-`items` variant passes (because that path raises `PermissionError`, caught by the broad `except Exception`).

Here are my findings.

---

## Findings

### F1 — Unwritable accounting sidecar (file-shadowed `items/`) continues instead of PAUSING
- **Location:** `benchmark/bench/chain_core.py:3264-3273` (`p426_write_accounting`), with the root cause in `benchmark/bench/p426_hooks.py:56-62` (`write_exclusive`).
- **Severity:** major.
- **Evidence:** confirmed (traced in source; reproduced by the frozen test `test_a_done_hook_infrastructure_error_with_an_unwritable_sidecar_pauses_the_leg`, which the testwriter report states is the single (D) failure left unamended).
- **Problem:** `write_exclusive` does `path.parent.mkdir(parents=True, exist_ok=True)` then `os.open(path, O_CREAT|O_EXCL)`. Both can raise `FileExistsError`: the first when the parent exists as a non-directory (a file at `items/`), the second when the sidecar file itself exists. `p426_write_accounting` catches `FileExistsError` uniformly and returns `True` ("the hook already sealed it for this attempt"). When `items/` is shadowed by a file, the mkdir raises `FileExistsError` before the sidecar is written; the candidate treats this as "already sealed" and returns `True`, so the chain writes `.continue` and the leg proceeds with no sealed accounting sidecar. Spec §5.3 requires: "if it cannot [be persisted], the leg is PAUSED."
- **Failure scenario:** A prior crash or a scratch collision leaves a regular file at `<out_root>/items`. A `done`-stage hook infrastructure fault then fires on a finished item. `p426_write_accounting` swallows the mkdir `FileExistsError`, returns `True`; the chain continues past the barrier. The accounting-fault sidecar is absent, the leg is not PAUSED, and `leg_items_problems` later reports `an accounting fault without its sealed sidecar` — but the leg has already moved on, so the outcome is kept with no durable accounting record and no designer pause. (The read-only-`items` variant does not expose this because `mkdir(exist_ok=True)` on an existing directory is a no-op and the subsequent `os.open` raises `PermissionError`, caught by the broad `except Exception` → `False` → PAUSE.)
- **Proposed change:** Distinguish "sidecar file already exists" from "parent cannot be created." Either (a) in `write_exclusive`, move the `mkdir` above the exclusive `open` and let its `FileExistsError` propagate as a write failure (not as "already sealed"), so only the `os.open(..., O_EXCL)` `FileExistsError` means "already sealed"; or (b) in `p426_write_accounting`, narrow the catch: after `FileExistsError`, return `True` only when the sidecar file itself exists and verifies (`sealed_ok`), else return `False`. (a) is the smaller, intent-aligned fix.

### F2 — `unreadable_count` undercounts provably-older processes with denied non-liveness reads
- **Location:** `benchmark/bench/proc_guard.py:940-957` (`_classify`, unclaimed branch).
- **Severity:** minor.
- **Evidence:** confirmed (traced in source). The testwriter report also notes "A provably older process with a denied cwd is skipped instead of counted."
- **Problem:** Spec §3.4: "An unclaimed unreadable process is listed only when it is not provably older than the guard (age readable); the rest are counted (`unreadable_count`), not listed." The candidate, for an unclaimed process that is provably older (`order < started_order`) and not excluded, returns `("skip",)` unless the process is in `_live_denied` (denied liveness). The `cwd`/`environ` reads that would mark it `unreadable` happen only *after* the `if excluded or older` short-circuit, so a provably-older process with a denied cwd/environ (but readable liveness) is skipped rather than counted in `unreadable_count`.
- **Failure scenario:** A background daemon older than the guard denies `cwd`/`environ` reads but allows `status`/`start_order`. It is skipped; `unreadable_count` omits it. The receipt's `unreadable_count` undercounts such daemons.
- **Proposed change:** In the unclaimed branch, when `older` is true, check `p.pid in self._live_denied` OR a denied cwd/environ read, and return `("count", key[1])` in either case; only return `("skip",)` when the process is fully readable and provably older. (The count is record-only, so this is reporting accuracy, not a protection loss — hence minor.)

### F3 — `chain_ops.owned_scan` re-implements the guard's ownership rules
- **Location:** `benchmark/bench/chain_ops.py` (`owned_scan`, the chain's second scan per §5.8), vs `benchmark/bench/proc_guard.py` §3.2.
- **Severity:** minor (hazard).
- **Evidence:** confirmed (the testwriter report flags this: "chain_ops.owned_scan re-implements the guard's ownership rules, so the two can drift").
- **Problem:** §5.8's second scan re-derives OURS/foreign by the probe session id, hermetic roots and container prefix. This is a second copy of the ownership logic. If the guard's attribution rules change and `owned_scan` is not updated, the "second, independent scan" can prove certain while the guard would not (or vice versa), so an owned survivor could be left alive (scan says foreign) or a foreign process killed (scan says ours).
- **Failure scenario:** A future edit tightens the guard's env-marker rule but not `owned_scan`'s; an owned survivor that the guard would claim is judged foreign by the second scan → not killed → PAUSE avoided, owned process left live.
- **Proposed change:** Share one ownership helper (e.g. a pure `classify(proc, roots, session_id, env_markers, tracked_keys)` in `proc_guard`) used by both the guard and `owned_scan`, so the two cannot drift. (Scope request — beyond the request's "fix the bundle"; flagged without severity.)

### F4 — Grader-infrastructure faults matched by substring markers
- **Location:** `benchmark/bench/token_turn_gate.py` (`GRADER_INFRA_MARKERS`, used by the abort classifier), per the implementer's report.
- **Severity:** minor (hazard).
- **Evidence:** confirmed (the testwriter report flags brittleness against grader message drift).
- **Problem:** §5.1's closed list is matched by substring. If the grader's error wording drifts, a real infrastructure fault no longer matches and is treated as the item's outcome (not regraded), silently losing a valid item.
- **Failure scenario:** A grader transport-loss message is reworded; the substring misses; the final grade is not regraded and becomes a normal fail instead of a `grade_fault` DNF after retries.
- **Proposed change:** Match on structured signal (exit code / error type / a typed exception) rather than message text, or pin the markers to a grader version and fail closed on version drift.

---

## On the questions posed

- **Process not spawned killed / owned left unrecorded:** Not found in the traced paths. `_classify` requires tracked/ancestry/session/environment corroboration before `("ours", ...)`, and the kill loop verifies gone; unverified kills become `uncertain` (PAUSE route). A path-only match without corroboration is `foreign_new` (recorded, not killed). Resolved (no defect found).
- **Check that protects the outcome now passing what it refused before:** F1 is the one (an accounting-fault sidecar that cannot be written no longer PAUSES under the file-shadow condition). The reconciler's late-record shapes (`kill_boundary_late_record` unpublished/step_after_count) were traced: each premise is checked (`trailing == "unpublished"`, `unmatched == 1`, `step_starts == n`, `step_finishes == n-1`, `in_flight_at_kill == 0`, `after.in_flight == 0`, pairing on all n, worker deltas); the frozen tests confirm variants that break any premise are refused. No integrity-not-invalidating or regrade-regenerating path found. Positives `PASS_NO_INFLIGHT` is gated to stall/loop only and requires `in_flight_at_kill == 0`, unchanged `requests_started`, `after.in_flight == 0`, `trailing` not interrupted; `interrupt` requires PASS with in-flight proof. Push binding (`local_gate.push_binding_problems`) checks `pushed_base` present + exists in repo + `git diff` empty over `PROTECTED_PUSH_PATHS`; the five red cases are pinned. Harvest symlinks are excluded with scrubbed targets. Resolved except F1.
- **Two independent events deciding a verdict by order:** The recorded D1 case is exactly this, and it is reconciled order-tolerantly (`order: "unpublished"`); the first shape records `order`/`signal_order` from offsets. The `kill_inflight_failed` check is left as-is (the implementer's L1 note: a frozen B2 test pins it; built-and-reverted). Resolved.
- **What the tests miss:** The broad run was not completed (testwriter report: stopped at ~66% by the 1-hour cap; two `test_p585`/`test_proc_guard` tests fail under load, pass in isolation — unexplained, possibly cross-test interference or timing). The whole suite has not been run on the candidate. The frozen set's harvest test exercises inventory-level symlink exclusion only, not the `harvest_wave2` scrub step end-to-end. The interrupt positive cannot run end-to-end (probe entry scripts hard-code the old three inject kinds; the implementer flagged this as open).
- **Beyond the spec:** The candidate adds `signal_order` as a separate field, `.r1.` rerun suffix, env markers only under a guard root, an unreadable-session-id-as-claim rule, `chain.p426_harness_faults` separate from the ledger, epoch `start_t`/`end_t` pause episodes, and the watcher's `BoxSampler`/`box_alerts`. These are within the spec's "left room" choices.
- **Heavier than intent:** F3 (duplicated ownership) is the main case where the mechanism is heavier than the intent needs; a single shared classifier would keep the same protection with less drift surface.

The one finding I'd block merge on is **F1**; F2-F4 are minor hazards. The broad suite's two unexplained load failures remain unresolved (no evidence either way).
