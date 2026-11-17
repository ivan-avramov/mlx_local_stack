I've traced both fixes in the round-2 diff against the current source and the round-2 verify reports. Here are my findings.

## V1 (Sol P2) — sealed re-check document checked against current selection on every resume

**Resolved.** `Sequencer.check_recheck_doc` (`benchmark/bench/p426_wave2.py:1143-1152`) computes `want = {gate, axis="A8", sessions, ref, test, attempts=recheck_attempts(gate)}` and raises `Stop(1)` if any field differs or `recheck` is not a dict. `ensure_recheck` (`:1086-1126`) calls it unconditionally whenever `path.exists()`, *before* the record/sha comparison, so it governs both the recorded and crash-window branches. `recover_recheck` (`:1154-1162`) no longer re-checks selection — it only records from the file, which is correct because `check_recheck_doc` already ran.

Every resume state traces correctly:

- **Record + file, same selection** → `check_recheck_doc` OK, sha matches → return (resume). Covered by `test_v1_a_recorded_recheck_of_the_current_selection_resumes`.
- **Record + file, changed selection** (a rerun selected another attempt) → `check_recheck_doc` → `Stop(1)`, "attempts" in reason, record unchanged, no recompute. Covered by `test_v1_a_recorded_recheck_of_another_selection_stops_on_resume[n16, x]`.
- **No record + file (crash window), same selection** → `check_recheck_doc` OK → `recover_recheck` records from file → ack check applies.
- **No record + file, changed selection** → `check_recheck_doc` → `Stop(1)`. Covered by the test-writer's delivery-4 "crash window, another selection" test.
- **Record + no file** → `Stop(1)` (never re-run). Unchanged from round 1.
- **No record + no file** → compute. Unchanged.
- **Outside + ack** (recorded or recovered): after `recover_recheck`/sha-match, `rec["inside"]` is False, gate is `"s1"`, so the early return at `:1119` is skipped; `rec.get("ack")` returns when acked, else `Stop(5)`. The recovered-outside path is covered by `test_l3_an_outside_sealed_file_without_its_record_still_stops_until_acked` (GLM round-2 confirmed).

One fail-closed tightening worth noting (not a defect): `recheck_attempts` raises `Stop(1)` if any selected leg has no VALID harvested attempt, so a resume with an incomplete selection now stops where round-1 only checked sha. This is the intended V1 behaviour ("against the current selection").

## V2 (Sol P1) — prompt path verifies the checkout sha

**Resolved.** `Tg2Corpus.spec_text` (`benchmark/bench/corpus_tg2.py:277-287`) now calls `self.verify_source(f"{lang}/{name}")` in place of `verify_inputs`. `verify_source` (`:239-245`) checks `source_sha() == universe["polyglot_sha"]` (refusing None or mismatch) then calls `verify_inputs`. `prompt` (`:289`) goes through `spec_text`, so a prompt on a checkout moved to another commit — even with byte-identical item bytes — refuses with `TransportAbort` naming "polyglot". Covered by `test_v2_the_prompt_refuses_a_checkout_at_another_commit`. The cost is one `git rev-parse` per prompt (test-writer noted); identity-only callers (`grader_timeouts`, `--print-identity`, `run_tg2_chain.load_names`, core `check_env`) do not call `spec_text`, so they are unaffected.

## Anything else the round-2 diff breaks or leaves failing

The round-2 diff (`FIX2-INTERDIFF.patch`) touches only `corpus_tg2.py` (V2), `p426_wave2.py` (V1), and the two test files. I traced nothing it breaks.

Two items remain open but are **not introduced or worsened by the round-2 diff** — both pre-date it and are explicitly held:

- **L1 tg1 widening (GLM F1 / implementer deviation 1).** `inject_verify.check_files` now accepts a tg1 row that records a hash-verified `datefreeze_path`, where candidate 1 returned `FAIL:evidence_sha256_keys`. This is a round-1 change; the round-2 diff does not touch `m62/inject_verify.py`. Held for the operator per the request (it touches the tg1 constraint; candidate unchanged).
- **`positives_session` seam untested (L17 / acceptance criterion 3).** The L1 box test bypasses `BoxSeqOps.positives_session` (lean router, A4 gate, worker load). Pre-existing; the round-2 diff adds no test for it. Remains the operator's gate.

NOTHING OF SUBSTANCE
