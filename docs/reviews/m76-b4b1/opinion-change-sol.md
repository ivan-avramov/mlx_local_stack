P1 — Location: `benchmark/m62/inject_verify.py:33-34,90-102`; `benchmark/bench/p426_wave2.py:1382-1405`  
Severity: blocker  
Evidence: confirmed (source trace)  
Problem: Every real injected positive carries `datefreeze` evidence because `positive_inject` supplies `--frozen-prompt-date`, but `inject_verify.check_files` requires exactly `events/export/stderr`. It therefore returns `FAIL:evidence_sha256_keys`.  
Failure scenario: All 12 box-side inject positives fail verification; `positives.json` is FAIL, v8 refuses it, and no tg2 leg can start. Fake `inject_verify` implementations in both test sets miss this.  
Proposed change: For tg2, require and verify `datefreeze_path`/`datefreeze` alongside the existing evidence fields; add a real-row integration test through `BoxSeqOps.positive_inject` and `inject_verify`.

P2 — Location: `benchmark/bench/corpus_tg2.py:133-169,199-219,249-271`  
Severity: major  
Evidence: confirmed (source trace)  
Problem: The replacement for `m65.tg2_universe.load()` checks the universe’s embedded polyglot SHA against the image record, but never checks the actual checkout used for materialisation and prompt text. `.docs` is absent from the prepared-manifest comparison.  
Failure scenario: A checkout with changed `.docs/instructions.md` but unchanged prepared files produces prompts for a different task. Its new SHA is merely folded into the live generation identity and frozen by v8; the leg is accepted rather than refused.  
Proposed change: Require `source_sha() == universe["polyglot_sha"]` before prompt/materialisation, and verify each selected item’s recorded `inputs_sha256`, including `.docs`. Preserve any narrowly justified exemption from the stale freezer-closure check rather than dropping these semantic checks.

P3 — Location: `benchmark/bench/p426_wave2.py:1074-1094`  
Severity: major  
Evidence: confirmed (source trace)  
Problem: Resume re-runs a re-check when `sequence.json` already records it but `recheck-s*.json` is missing. This contradicts the specified “re-verifies, never re-runs” rule.  
Failure scenario: After s1, the sealed record is deleted or lost; resume recalculates under potentially changed code/data and replaces the recorded result.  
Proposed change: If either the sequence entry or record exists without its counterpart, stop and refuse. Compute only when neither exists.

P4 — Location: `benchmark/bench/p426_wave2.py:402-439`  
Severity: major  
Evidence: confirmed (source trace; exposed by `test_strict_rows_refuses_a_stray_row`)  
Problem: `tg2_strict_rows` checks that every planned slot has a row or DNF, but silently ignores stray rows, stray DNFs, and row/DNF overlap.  
Failure scenario: Harvested evidence contains all planned rows plus `rust/not-planned`, or both a row and DNF for one slot; the nuisance re-check seals a result from the uncontaminated subset instead of refusing unverifiable evidence.  
Proposed change: Require exact set equality with planned slots and require rows and DNFs to be disjoint.

P5 — Location: `benchmark/chains/c147/run_tg2_chain.py:135`; `benchmark/bench/p426_freeze.py:103,1139-1165`; `benchmark/bench/p426_wave2.py:1491-1503`  
Severity: minor  
Evidence: confirmed (source trace)  
Problem: Direct tg2 freeze, positives, and chain interfaces accept arm V and V-containing pairs, although B4b-1 is N16/X and stage 4 is a non-goal. Only the wave-2 sequencer rejects V.  
Failure scenario: An operator can create tg2 rehearsal/v8 records and direct V legs that look like stage-3b evidence outside the canonical sequencer.  
Proposed change: Centralize the B4b-1 arm contract as exactly `("n16", "x")` and enforce it in all tg2 entry points.

P6 — Location: `configgen/targets.py:33-36`; `benchmark/bench/tests/test_registry_published_set.py:66-74`  
Severity: minor  
Evidence: confirmed (the two non-environment full-suite failures)  
Problem: The new configgen target has no model-ID extractor, so criterion 2 remains failed and the new generated carrier is not exercised by the registry protection.  
Failure scenario: CI always fails before validating the tg2 carrier’s model IDs.  
Proposed change: Add `opencode-bench-v2-web-tg2: _opencode_ids` and cover the new target alongside tg1.

P7 — Location: frozen delivery-1 tests, principally `test_m76_b4b1_fe_chain.py`, `test_m76_b4b1_fe_corpus.py`, `test_m76_b4b1_fe_grade.py`, and `test_m76_b4b1_fe_wave2.py`  
Severity: minor  
Evidence: confirmed (failure trace against source/spec)  
Problem: Of the 26 delivery failures, only P4 exposes a candidate defect. The other 25 impose unsupported or incorrect expectations: R2 defaults to N16 instead of X; slots must say N16 rather than tg1’s flat `oc`; argparse must expose `tg2_inject`; identity JSON must expose internal pins; tg2 validation is invoked without `grader="tg2"`; `t_coop` retains the inadequate 660-second join; and v8 refusal must occur during parsing rather than command execution.  
Failure scenario: Repairing toward these tests would weaken the grader bound, break the M64 four-language corpus, or allow R2 on the wrong arm.  
Proposed change: Have the test-writer amend those tests to exercise public behavior: pass `grader="tg2"`, use X for R2, assert only the specified slot prefix, test identity effects rather than JSON layout, use the corpus-derived join, and invoke v8 behavior rather than parser internals.
