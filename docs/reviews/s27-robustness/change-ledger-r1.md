# S27 robustness bundle — change review round 1 of 3 (panel verify of candidate 1) + test-writer delivery 2: ledger

Candidate 1 = patch sha256 `34a9f8f6…` on baseline `820897540`; frozen tests v1 (2026-11-20T08:39:36Z, blind) → v2
(13:17:58Z, amended to the candidate's interface under S28-P5); v2 on the candidate: 208 passed, 1 failed (X4).
Panel: GPT-5.6 Sol High (cursor-agent, checkout, user instructions unconfirmed), GLM 5.2 High (cursor-agent, same; 75 s, leans on
the reports), Claude Sonnet 5.5 (`claude -p`, checkout, session `c7fc6551…`; shares the test-writer's model). Raw outputs beside
this file. Judged by the designer; every adopted claim traced in the source (noted). Intent-first (S28-P5): adopt the problem,
not the member's mechanism.

| id | finding (raised by) | disposition | why |
|---|---|---|---|
| X1 | The probe CLIs reject `--tg*-inject interrupt` (`run_tg1_probe.py`, `run_tg2_probe.py`, `run_oc_probe.py`), so no positives record can pass v8 (Sol P1, Sonnet P2, implementer) | adopted | §4.5 requires the run; the files are in the spec's closure. One shared kind list; one test through the real parser. |
| X2 | `kill_inflight_failed` still decided by the `/metrics` sample vs the client's next request (Sol P2, Sonnet P3, implementer L1) | adopted (S28-P7) | P13; fail-closed now means a whole-leg INVALID. Accept on recorded evidence (open step in the stream at the signal, `|S|=|C|+1`, failed delta 1, the failed line the session's last and after the SIGTERM); the frozen B2 off-table test amended to keep its refusal for the unanchored variant. |
| X3 | An interim-grade fault first seen at `worker.finish()` after the client exited is labelled `stage="generation"` → the finished generation is regenerated (Sol P3) | adopted | traced (`arm_runner.py` `GradeWorker.check` / `finish`). Intent: rerun only when a fault prevents the outcome; after the client exits the final grade decides — the interim fault is recorded, the final-grade path (with its own regrade) proceeds. |
| X4 | Accounting sidecar: any `FileExistsError` (incl. `mkdir` on a file-shadowed `items`) counts as "already sealed" → continues instead of PAUSE (test-writer D, Sol P4, GLM F1, Sonnet P4) | adopted | frozen v2 test fails on it. "Already sealed" only when the exact sidecar is a regular file that verifies for this slot / row / attempt; else PAUSE. |
| X5 | `ctx["stage"]` stays `"done"` from item k's commit until item k+1's `_run_item`: an abort in k+1's discovery guard or `barrier.ready` is stamped outcome-present and blames item k as an accounting fault; the real fault is never counted, so the cap never holds (Sonnet P1) | adopted | traced (`arm_runner.py:476`, `:1428`, stamp at `:1470`). The stage follows the item that is actually running; red test: a ready-barrier fault on item 2. |
| X6 | Grader infrastructure faults matched by substring over messages that embed agent output (Sonnet P5, GLM F4, test-writer) | adopted | an agent's program printing "Connection refused" would turn a real failure into regrade ×3 → `grade_fault` DNF (outcome-dependent, agent-controlled). Classify where the harness itself fails (typed at the source), never from embedded output. |
| X7 | Watcher claims every process in the driver's session as ours; the sequencer launches the chain in the ambient (shell) session, so unrelated same-session load is never ALERTed (Sol P7) | adopted | traced (`p426_wave2.py` launch without a new session; `bench_watch.BoxSampler._ours`). Ours = driver descendants + sessions led by probe descendants. |
| X8 | `foreign_new` stores up to 64 full argv of unrelated same-uid processes in public rows (Sonnet P8) | adopted | data boundary (public repo, AGENTS.md): record-only needs identity, not content. Keep pid, create_time, sid, flags, executable basename, argc. |
| X9 | The `unpublished` shape waives the message-id check when the stream's last `step_start` id is missing (Sonnet P9) | adopted | §4.2 / C375 bind the recovered message to the open step; missing id → not this case. |
| X10 | The chain's second scan re-implements ownership (drift), matches session by bare `getsid`, silently skips uid-denied processes (GLM F3, Sonnet P7, test-writer, Sol P5) | adopted | one ownership rule, used by the guard and the chain scan; session members bounded by the probe's start; unreadable ones listed. |
| X11 | A process the scan cannot construct or whose `uids()` is denied is dropped before ownership is considered (Sol P5) | adapted | partly pre-existing (P585). Intent "owned never left alive unrecorded": such a pid that is tracked or in the probe-led session becomes a claimed obligation (existing uncertain path); else counted. |
| X12 | Interrupt PASS accepted on its verdict string; the writer skips row verification when the PASS row is missing (Sol P6) | adapted | the sealed record's trust model stays (v8 trusts the writer that ran `inject_verify`), but the interrupt is now the one cancellation proof: v8 requires its `probe_rc` 0, `verify_verdict` PASS and row sha; the writer fails a PASS whose row is missing (any kind). Sol's full causal re-validation in v8 declined as duplicate of `inject_verify`. |
| X13 | `survivors` keeps pids killed in the 3rd scan round even when verified gone → `CleanupUncertain` after a cleaned fork storm (Sonnet P11) | adopted | traced (`proc_guard.py` cleanup). Survivors = alive or not verified gone. |
| X14 | `Chain.__getattr__` + class-level defaults exist only for test doubles (Sonnet P11, test-writer) | adopted | hazard: a misspelt attribute silently reads a default in production. Remove; tests build the chain properly. |
| X15 | `unreadable_count` omits provably older processes with a denied cwd / environ (GLM F2, test-writer) | adopted | §3.4 says counted; record-only accuracy. |
| X16 | A `done` hook infra error that prevented the post-item ready checks becomes an accounting fault without saying so (Sonnet P6) | adopted (record only) | the sidecar names the checks not evaluated; the next `ready` already re-checks. |
| X17 | Dead `session_id` parameter on `ProcessGuard` / `_run_item` (Sonnet P11) | adopted (remove) | the chain launches probes with `start_new_session=True` (`chain_core.py:2098`), so §3.1's leader test applies; the explicit path is unused. |
| X18 | Frozen tests that pin pre-C372 behaviour are masked or edited (`test_b2_frozen_s4_reconcile::test_fix_the_done_hook_invalidates_a_server_count_that_differs_from_the_client`; edits to `s26_frozen`, `p586_frozen`, `test_b2_*`) (Sonnet P10, implementer) | adopted | each frozen-test edit is listed with its spec clause in the fix report; the designer checks each; the full suite runs on baseline and final candidate with the submodules present. |
| X19 | Two tests fail only in a broad run (`test_p585_proc_guard_systemerror::test_the_scan_skips_a_process_it_cannot_construct_and_keeps_the_rest`, `test_proc_guard::test_real_rapid_fork_detach_chdir_is_attributed_or_diagnostic`) (implementer, Sonnet P10) | adopted | zero flakes: root-cause (interference or defect), fix the cause. |
| X20 | The javascript lock omission rests on an unproven premise (Sonnet P11) | declined | the tg2 javascript grader runs the pre-installed jest (`tg2_grade.py:44`, `/opt/tg2/js/node_modules`), never an install, so a lock in the final tree is inert; C368 (1) settled. |
| X21 | §3.2 "as today": a denied read on a session-claimed process is killed-and-verified instead of uncertain (test-writer) | declined | meets the intent better (an owned process is gone, verified); uncertain only when not verified gone. |
| X22 | Reused session id after a long pause could hit a reused pid's session (test-writer) | merged into X10 | the probe-start bound covers it. |

## Fix round 1 outcome (fresh Claude Opus session `3a24a19a…`, 2026-11-20)

- X1–X4, X6–X19 fixed with red tests (`test_s27_impl_r1fix.py` and the impl files). X19 cause: a C157 fixture re-wrapped
  `ProcessGuard.__init__` via `monkeypatch`, whose late undo re-installed the conftest's hermetic wrapper for the rest of the run
  (the family scan then missed the p585 / rapid-fork cases); removed with X17, regression test added.
- **X5 corrected by the designer: not a defect.** Candidate 1 already resets the stage at each item start
  (`ctx.update(id=item, stage="ready")`, `arm_runner.py:1367`); the designer's trace grepped `ctx["stage"]` only and missed it.
  Kept: a boundary reset (`ctx.update(id=None, stage=None)`) as hardening, and its real-probe test.
- Frozen-test conflicts (7), judged: X3 → the frozen interim test is re-staged so the fault lands while the client still runs
  (keeps §10.1's "interim fault → one rerun"), and the X3 scenario added; X6 → the fixture's grader fault becomes the typed
  `GraderInfraError` (text matching is what X6 removes); X9 → the D1 fixture row carries `last_step_start` = the real step id from
  the recorded events (`msg_1f6b55ed0001…`), which the new probe records; the test models the new identity's row. Amended by the
  test-writer (delivery 3).
- Clarification within X18 / X6 (same session): the two `test_b2_frozen_s0_support` pins that §4.5 / §3.5 change (`run_inject.py`
  sha, the schema-2 cleanup keys) are updated with their clause; `structured_grade.parse_go` brought into X6's scope so tg1 Go
  docker faults are typed too (stage 4 may rerun tg1 legs).
