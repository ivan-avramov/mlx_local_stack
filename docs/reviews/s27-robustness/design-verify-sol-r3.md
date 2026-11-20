P1 — RESOLVED. §5.3 now defines an explicit `accounting_fault` disposition, hash-bound sealed sidecar, and `chain_rows` exposure.

P2 — RESOLVED. §5.7 defines terminal `harness_fault_dnf`/`grade_fault` records and limits P426 attempts to indices 0–1 independently of legacy cheat reruns.

P3 — NOT RESOLVED.
- Location: spec §5.1–§5.2, §5.8; `arm_runner.py:172-247,619-658`; `p426_hooks.py:247-296`; `chain_core.py:2874-2917`
- Severity: major
- Evidence: confirmed
- Problem: abort routing still lacks lifecycle phase. §5.8 handles `grader_infra` only after generation finishes, although the concurrent `GradeWorker` can fail during generation. It also routes every `hook_infra` to §5.2, which defines only ready-stage faults; `after_attempt` can fail after an outcome exists.
- Concrete failure scenario: an interim grader loses Docker while the client is still generating. `worker.check()` aborts, but neither rerun nor regrade applies. Separately, an `after_attempt` item-record write fails after the row exists; the spec permits either an incorrect regeneration or no defined disposition.
- Proposed change: include stage and `generation_finished`/`outcome_present` in abort stamps. Route unfinished grader faults and ready-hook faults to the one permitted rerun; finished-generation grader faults to snapshot regrading; done-hook faults to outcome-preserving `accounting_fault`, or PAUSED if the annotation cannot be persisted. Add red tests for both omitted paths.
