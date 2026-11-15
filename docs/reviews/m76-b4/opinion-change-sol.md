P1 — Location: `benchmark/chains/c147/run_tg1_chain.py:61-64,120-131`  
Severity: blocker  
Evidence: confirmed, source trace.  
Problem: tg2 is bound to tg1’s scaffold label and generation data (`opencode-v2-web-tg1`), contrary to tg2’s dedicated probe policy.  
Failure scenario: a conforming B4b probe accepts `opencode-v2-web-tg2`; the chain launches it with `--scaffold opencode-v2-web-tg1`, so every invocation refuses or records the wrong identity.  
Proposed change: define corpus-specific scaffold/probe data in `run_tg2_chain.py`; use them in `ArmBinding` and `core_specs`.

P2 — Location: `benchmark/bench/p426_harvest.py:264-324`; `benchmark/bench/tg2_grade.py:1000-1020,1040-1045,1070-1106`  
Severity: blocker  
Evidence: confirmed, source trace.  
Problem: the harvest’s closed evidence rules reject tg2 grader files such as `*.stdout`, `*.stderr`, `*.inspect`, `*.out`, and `*.err`. Only the namespace was added.  
Failure scenario: the first real smoke item grades successfully, but harvest reports “no harvest rule matches this file”; the sequencer stops with rc 4.  
Proposed change: add exact tg2-grade directory/file rules and a realistic end-to-end harvest fixture containing every terminal grader output.

P3 — Location: `benchmark/chains/c147/run_tg2_chain.py:183-229`; `benchmark/bench/p426_hooks.py:207-220`; `benchmark/bench/p426_signals.py:1606-1708,1972-2005`  
Severity: blocker  
Evidence: confirmed, source trace; `item_record`, `grade_outcome`, and the A8 adapter are only exercised by B4 tests.  
Problem: the proposed grader-to-item-record seam is disconnected from real execution. P426 writes reconciliation records without `corpus`, `leg`, `language`, or `passed`; standard rows also lack the custom metadata. `compute_kv` never adds A8.  
Failure scenario: all tg2 legs complete, but feeding harvested P426 item records or rows to `a8_decider_inputs` yields “no decider records”; no A8 verdict or panel input can be produced. A real DNF has no row, while `item_record(..., dnf=...)` still requires one.  
Proposed change: consume verified harvested rows, schedules, and DNF ledgers through the existing B8/signals pipeline; derive strict pass as execution pass ∧ convergence and add A8 to `compute_kv`. Avoid a second, unwritten item-record format.

P4 — Location: `benchmark/bench/p426_signals.py:1972-2005`; `benchmark/bench/m76_rule.py:650-662`  
Severity: major  
Evidence: confirmed, source trace.  
Problem: the A8 adapter checks only equality between arms. It does not require the committed 80 items, 20 per language, both `s1` and `s2` for every item, decider tier, draw SHA, or accepted-attempt provenance. Size mismatches merely become warnings.  
Failure scenario: both arms supply the same 8 items or only `s1`; `axis_verdict` can still return PASS with a size warning. Records labelled `leg=s1` but built for another tier/draw also pass.  
Proposed change: derive the expected IDs from the committed draw, require exactly `{s1,s2}` per item and 20 items per language, and consume only B8-accepted attempts whose frozen schedules and records match.

P5 — Location: `benchmark/bench/p426_wave2.py:47,470-472,884-950`; reference gate `benchmark/bench/p426_freeze.py:723-760`  
Severity: major  
Evidence: confirmed, source trace.  
Problem: tg2 bypasses the pilot gate. `VALID_WITH_DNF` is selectable, and amendment verification checks the receipt dossier but not strict `VALID`, zero DNF, four realized items, or speed validity.  
Failure scenario: a smoke arm has one DNF or a dead watcher; after B4b supplies a sealed amendment, positives and measured legs proceed.  
Proposed change: generalize the pilot gate for tg2 smoke names/counts and require both smoke arms strictly `VALID`, four reconciled rows each, zero DNF, speed-valid, engaged, and pair-gated before writing/accepting the amendment.

P6 — Location: `benchmark/chains/c147/run_tg2_chain.py:43-68,159-168`  
Severity: major  
Evidence: confirmed, source trace.  
Problem: `load_draw` trusts any adjacent sidecar; it never compares against the known committed draw SHA or verifies `universe_sha256` against the real universe. A consistently redrawn permutation with updated tier prefixes and sidecar passes.  
Failure scenario: both arm commits contain a canonical replacement draw and sidecar, and the record names that new SHA; every leg accepts it. The test’s “re-pinned redraw” changes only the permutation, leaving tier prefixes inconsistent, so it misses this case.  
Proposed change: pin the expected draw SHA independently, verify the draw’s universe SHA against the committed universe, and test a fully consistent redraw with a regenerated sidecar.

P7 — Location: `benchmark/chains/c147/run_tg2_chain.py:183-193`  
Severity: minor  
Evidence: confirmed, source trace.  
Problem: `grade_outcome` maps `storage_cap` to `grader_oom=True`, while real `oom` and `mem_kill` outcomes map both resource flags to false.  
Failure scenario: an OOM item scores as a failure but the row’s resource diagnostics deny the OOM; a storage-cap failure is falsely reported as OOM.  
Proposed change: map `oom` and `mem_kill` to their respective flags and leave `storage_cap` separate.
