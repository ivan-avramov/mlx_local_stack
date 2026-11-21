# Test-writer report, delivery 3 — M76 B4b-2, fix round 1 (candidate 2 = candidate 1 + `fix-1.patch`)

Commands: `../fe_test.sh stack …` (candidate 2), `../../twb/fe_test.sh stack …` (baseline copy; my 6 test files copied there, fixtures were
already there). Nothing committed, pushed or reset. (`../scratch/tw3_patch1.py` is a blocked, never-run script; ignore it.)

## 1. Result

| set | baseline | candidate 2 |
|---|---|---|
| my whole set, 6 files, **159 tests** (140 amended v2 + 19 new) | 34 passed · 114 failed · 11 errors | **159 passed** (376 s) |

* Baseline: the 34 passes are the same invariants as before (goldens, A7 controls, leak rule on today's functions, world sanity); every failure is a missing A8
  symbol / argument. Outputs: `../scratch/tw3_base.txt`, `../scratch/tw3_cand2.txt`.
* Candidate 2: **no failure to report verbatim** — all 159 pass. Before my amendments 35 of the 140 v2 tests failed (the implementer's list); all 35 were the fixture conflicts
  below, none a candidate defect.

## 2. Fixture amendments (intent, class, item kept)

| finding | change (`test_m76_b4b2_fe_support.py` `World`) |
|---|---|
| B4 | `_v8()` carries `probe_code_sha256`, `scaffold_policy_sha256`, `generation_identity_sha256`, `tg2_image_id`, `grader_image_id` read from the pinned pilot manifests (`runtime…`), sealed; `chain.frozen_record` follows |
| B10 | `seed()` = `rowschema.sample_seed(id, 0, <session plan seed>)` (a reload shares s1's) |
| B3 | a `harness_fault` attempt (rerun and harness-DNF) names its main invocation when the language has one; that invocation's manifest `run_id` is in `seen_run_ids` |
| B2 | `edit_row` re-hashes the invocation record it changes (and re-seals an accounting sidecar over the new row) |
| B3 test | `test_manifest_of_a_discarded_rerun_attempt_is_not_an_orphan` now uses the 20-item reload session (the language keeps a main invocation) and publishes under the faulted invocation's manifest `run_id` |
| B10 test | `test_reload_control_refuses_when_seeds_differ` → `test_a_reload_with_seeds_off_the_plan_is_rejected_and_the_control_not_computed`: the reload is a B8-A8 REASON, the control "not computed", no "refused: seeds differ", the confirmatory verdict unaffected |
| B15 | `test_v8_arms_must_be_n16_x` now requires the **record** form (REASON mentioning arms), not a refusal |

## 3. New tests (19)

**`test_m76_b4b2_fe_packet.py` (13) — B12, scenario level** (synthetic tg2 world with real final trees on a real tmp git evidence ref, a synthetic rust exercise prepared by
`tg2_materialize.prepare_tree`, B8-A8 from `verify_a8_kv`; `kv_a8_context` → `_a8_packet`, and `kv_export(…, b8_a8_path=, a8_inputs=)`; the stub corpus replaces the pinned universe):
packet = runner's prompt + each arm's diff (c) · prompt not the runner's refuses (c) · quoted prompt accepted (c) · start tree not the bound one refuses (c) · final-tree object not its
name refuses (c) · manifest on `main` changed after B8-A8 refuses at the context (c) · protected test file changed refuses (c) · grader-accepted Rust `Cargo.toml` diffed as content (c) ·
new helper file in the diff (c) · leak report names patterns, never text (b) · a leaking item refuses the member export per item, writes nothing (c) · a clean item exports a member
frozen against B8-A8's **file** sha (c) · an A8 member without B8-A8 refuses (c). Baseline: all fail (no A8 interfaces); candidate: pass.

**`test_m76_b4b2_fe_b8.py` (+6), `…_signals.py` (+1)** — adopted findings the implementer's `r1fix` file does not exercise independently: B2 unregistered rows file with rows refuses / an empty
one is tolerated (c) · B4 a manifest with another probe code is rejected (c) · B10 a row seed from another session's plan rejects only that session (c) · B9 a rejected confirmatory session
leaves the document `incomplete` (c) · B9 + B10 at the sheet: the axis is incomplete, no verdict, no verdict flag (c). B1, B3 (own run / other seen run), B4 (v8 keys), B5, B6, B7, B8, B14, B16
are covered by `test_m76_b4b2_impl_r1fix.py`; I did not duplicate them (B6, B7, B8, B14, B16 only through the CLI / sheet paths my existing tests already run).

## 4. Review of fix 1 against B1–B16 (code read; every claim below is from `fix-1.patch`)

**Verdict: merge.** Every adopted finding is implemented as ruled, the 159 independent tests pass, and I found no defect that corrupts a verdict or a record. Minor items for the designer, none blocking:

| id | sev | where | evidence | note |
|---|---|---|---|---|
| f1 | minor | `p426_verify.py` `discarded_runs` / `final_tree_reasons` (B3) | the exemption is now only a `harness_fault` attempt (its invocation's manifest `run_id`, also in `seen_run_ids`); the old exemption for **cheat reruns** and DNF slots of pre-S27 tg1 chains is gone | A7 sessions already committed are unaffected (the golden passes), but a future tg1 A7 chain with a cheat rerun whose earlier attempt published a final tree would now be rejected as an orphan. Acceptable if no such A7 run is planned; say so in the spec |
| f2 | minor | `p426_verify.py` `main` (B6) | `B8.json` is written, then B8-A8; if A8 refuses, an older `B8-A8.json` beside it is left in place | the stale file is bound to the old base sha, so consumers refuse it (B16 / `check_b8_a8`) and rc is 2, but the operator could ship the pair by hand. Remove or rename a stale `B8-A8.json` when A8 refuses |
| f3 | minor | `p426_signals.py` `_a8_latency` / `a8_utc_seconds` (B7, C7) | a leg `started` / `ended` without a zone reads as None; the window then counts 0 rows and the summary prints `n: 0` silently | A tz-naive leg time in a real record would give an empty (not refused, not labelled) latency window. Label it `unparsed leg window` |
| f4 | minor | `check_b8_a8(…, repo_root)` callers (B14, C6) | the signals and the panel pass `V.STACK_REPO` (the stack that produced the draw), not a caller's repo | consistent and the draw is pinned, but `kv_export --repo` / `a8_inputs["repo"]` no longer say which repo B8-A8's draw is re-hashed in; document that the draw is the stack's |
| f5 | note | `_a8_accounting` (B5, C1) | row marker and `p426_accounting_faults` are bound only when present; the runner writes neither a row marker nor (per the implementer) always the list | the designer's C1 accepted it; my frozen world writes a row marker and no list and agrees. If the runner later writes the list, the "present ⇒ bound" rule needs one test with the list but no marker |
| f6 | note | `_a8_inventory` (B2) | `load_slots(check_unregistered=False)` plus an own check: an unregistered rows file holding rows refuses, an empty one does not | matches the frozen all-DNF world; an empty unregistered rows file still needs its provenance manifest (A7's rule) — my test writes one |

Findings B1 (both call forms), B2 (inventory authority, sidecar equality, reason-less fault refuses), B3 (per-slot run binding), B4 (v8 draw / universe pins, manifest identity, model),
B5 (agreement + orphan sidecar + tax + speed tier), B6 (B8.json first), B7 (UTC, numeric validation), B8 (pinned paths), B9, B10, B14, B15, B16: each read in the patch and, where my tests reach
it, confirmed by them; the real-pilot acceptance (`test_m76_b4b2_fe_real.py`, 18 tests) passes on candidate 2 against the real records.

## 5. Open / not run

* I did not rerun the existing test families (`test_m76_b3_*`, `b4b1`, `p426`, `p613*`, …) this round; the implementer's report gives 3 + 1 failures that name the absent commit `f2b61127…` and no others, and the unfinished-families caveat of my delivery 2 stands until they are rerun on candidate 2.
* §7.3 on the new-identity pilot pair and B11 (real packet / export bytes) remain the designer's step; my packet scenarios use synthetic bytes.
