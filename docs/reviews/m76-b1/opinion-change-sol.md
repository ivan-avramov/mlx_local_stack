P1
- location: `benchmark/bench/p475_kv.py:1128-1185`
- severity: blocker
- evidence: confirmed
- problem: Mode proof still uses exit-minus-creation deltas. Real creation snapshots are taken after the ladder, so healthy X/V/XO legs produce approximately zero deltas and become INVALID. Conversely, unchanged nonzero forbidden or `fallback:*` counters pass. Frozen tests encode the obsolete delta rule.
- concrete failure scenario: The first real X leg completes with positive absolute route counters, but required deltas are zero; the resumed campaign stops permanently at that INVALID leg.
- proposed change: Apply route rules to absolute exit counters, require exit `fallback:* == 0`, mode-check creation, and retain both snapshots.

P2
- location: `benchmark/bench/p475_kv.py:356-364,1277-1305,2436-2441,2654-2657`
- severity: major
- evidence: confirmed
- problem: `MLX_VLM_DRAFT_KIND` and `MLX_VLM_DRAFT_MODEL` are neither stripped from f45 environments nor checked before XO load. Exact argv and later telemetry checks occur too late.
- concrete failure scenario: An inherited or `.env` value makes XO attempt to load a drafter. M77 may refuse during load, but the required pre-load INVALID protection is absent.
- proposed change: Strip both variables after `.env` overlay on every f45 router/driver environment and reject their presence before XO load. Add environment-injection tests.

P3
- location: `benchmark/bench/p475_kv.py:676-709`
- severity: major
- evidence: confirmed
- problem: `prepare` is not interruption-idempotent: registry generation and submodule setup occur only when the worktree directory does not exist.
- concrete failure scenario: Interruption after `git worktree add` but before X’s registry commit leaves an existing base worktree. Resume skips the commit and repeatedly refuses the arm as divergent.
- proposed change: Reconcile each existing worktree phase-by-phase, completing a clean base-state arm and refusing only unrelated or dirty states. Add interruption-point tests.

P4
- location: `benchmark/bench/p475_kv.py:1540-1652`
- severity: major
- evidence: confirmed
- problem: Harvest publishes the dossier before updating `LAST_LEG_END`; resume treats an existing dossier as fully harvested and cannot repair a missing marker.
- concrete failure scenario: SIGINT lands after `os.rename(stage, final)` but before marker publication. Resume starts the next leg using an absent or old timestamp, violating the 600-second idle rule.
- proposed change: Journal the harvest completion timestamp in the dossier and repair the marker on resume, conservatively delaying if uncertain. Add a test for this exact interruption window.

P5
- location: `benchmark/bench/tests/test_m76_b1_fe_support.py:190-197`
- severity: major
- evidence: confirmed
- problem: Frozen fixtures create f45 preflight records without `campaign: "f45"`, contrary to Errata v1.1. Consequently, 153 tests stop at preflight and do not exercise their claimed behavior.
- concrete failure scenario: Mode-proof, KV, run, and matrix cases report NOT_STARTED solely because the fixture is interpreted as u4.
- proposed change: Stamp every fake f45 preflight and engagement record, then update mode-proof fixtures to absolute counters.

P6
- location: `benchmark/bench/p475_kv.py:1993-1996`
- severity: minor
- evidence: confirmed
- problem: The candidate emits `**stage-4 trigger: met**`; Errata v1.1 requires `stage-4 trigger: **met**` and the analogous not-met form.
- concrete failure scenario: An exact consumer cannot recognize the trigger.
- proposed change: Bold only the verdict. The frozen tests already catch this; their failure is not a test defect.

P7
- location: `benchmark/bench/tests/test_m76_b1_fe_f45_registry.py:75-77`
- severity: minor
- evidence: confirmed
- problem: The frozen exact-registry test searches the whole file for the first `kv_bits: 4`, selecting another model’s entry. It falsely rejects the candidate.
- concrete failure scenario: X/V/XO output is correct, but the adjacency assertion examines the earlier u4 entry.
- proposed change: Restrict the search to the f45 entry span. The candidate generator itself produces exactly the specified real-entry diff, including preserved XO values and no changes to other entries.

P8
- location: `benchmark/bench/p475_kv.py:485-533`
- severity: minor
- evidence: confirmed
- problem: Beyond the requested f45 edit model, missing-key refusal was widened for u4: TQ4-OFF now refuses when `draft_model` is absent, whereas baseline only required `draft_kind`.
- concrete failure scenario: Preparing u4 against that malformed legacy entry now fails where baseline generated an arm.
- proposed change: Preserve the legacy u4 path or explicitly accept and document this additional hardening.
