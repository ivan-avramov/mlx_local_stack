# Implementer report: M76 B4b-1 fix round 1 (L1–L6), change review round 1 of 3, spec v5 + erratum v5a

Every adopted implementer row (L1–L6) now has a test that was red on candidate 1 and is green after the fix. The impl test files pass, and so does every test file that imports a module I changed. Their result is unchanged from candidate 1 (all passed before and after). Nothing was committed. L7 and L14 were not touched (they are the designer's).

## Per adopted row

All new tests are in `benchmark/bench/tests/test_m76_b4b1_impl_wave2.py` (`test_l1_*`, `test_l3_*` to `test_l6_*`) and `benchmark/bench/tests/test_m76_b4b1_impl_corpus.py` (`test_l2_*`).

Red run on candidate 1, before any source edit: 29 tests, 25 failed, 4 passed (`../scratch/r1_red.txt`, `r1_red.xml`). The 4 that passed are guards for behaviour candidate 1 already had; they are listed under their rows. One test failed on candidate 1 with an IndexError because of a bug in the test (`perm("cpp")[30]`, out of range). I fixed the test and re-ran it red on candidate 1: `DID NOT RAISE Refusal` (`../scratch/r1_red_l4_dnf.txt`). Green run after the fixes: 29 passed, 0 failed (`r1_green.txt`, `r1_green.xml`).

### L1: `inject_verify` evidence keys of a v2 row
- **Change.** `benchmark/m62/inject_verify.py`:
  - new `V2_EVIDENCE_PATHS` (`datefreeze` → `datefreeze_path`, `toolwindows` → `toolwindows_path`), `REQUIRED_EVIDENCE` (tg2: `datefreeze`) and `evidence_paths(row, scaffold)`.
  - `check_files` now requires the `evidence_sha256` keys to equal exactly the artifacts the row records. That is the base three plus each v2 artifact whose path field the row carries; a tg2 row must carry `datefreeze`. Each artifact's path must exist and hash to its digest.
- **Tests.**
  - `test_l1_a_real_shaped_tg2_inject_row_verifies_through_the_box_seams[v2, v2+toolwindows]`. The row's evidence fields come from the real `OpencodeArm.row_fields` over the real `evidence_suffixes()`. Its grade reports come from the real `arm_runner.grade_reports` over the recorded real `rust/reference/rust__say` tree. The row goes through the real `BoxSeqOps.positive_inject` and then `BoxSeqOps.inject_verify`, which runs the real `m62/inject_verify.py` subprocess. Only the probe process is faked: the worktree's `.venv-bench/bin/python` answers the `run_tg2_probe.py` call by writing the prepared row, and execs the bench interpreter for everything else.
  - `test_l1_the_tg2_evidence_keys_are_the_rows_recorded_artifacts[5 cases]`: no datefreeze, wrong datefreeze sha, stray key, a toolwindows key without a path, a datefreeze key without a path.
- **Red:** 7/7 failed. The box seam returned `FAIL (inject_verify rc 1)`, and the direct calls gave `FAIL:evidence_sha256_keys` on the unmutated real-shaped row. **Green:** 7/7.

### L2: `Tg2Corpus` checks the live checkout before prompt and materialisation
- **Change.** `benchmark/bench/corpus_tg2.py`:
  - new `Tg2Corpus.verify_source(item)`: refuses unless `source_sha() == universe["polyglot_sha"]` (None refuses), then calls `verify_inputs`.
  - new `Tg2Corpus.verify_inputs(item)`: refuses unless `m65.tg2_universe.inputs_sha256(checkout, lang, slug)` equals the item's recorded `inputs_sha256`.
  - `prepare` calls `verify_source` before `tg2_materialize.prepare_tree`.
  - `spec_text`, which `prompt` uses, calls `verify_inputs` before reading `.docs`.
  - Every refusal is a `TransportAbort`.
- **Tests:**
  - `test_l2_a_checkout_at_another_commit_refuses_before_materialisation`: wrong sha and unknown sha; the destination is never created.
  - `test_l2_a_changed_exercise_refuses_before_materialisation`: a checkout at the pinned sha whose `.docs/instructions.md` changed.
  - `test_l2_the_prompt_never_reads_a_changed_specification`
  - `test_l2_the_live_checkout_is_the_universes` (guard; it passed on candidate 1).
- **Red:** 3/3 behaviour tests failed with `DID NOT RAISE TransportAbort`. **Green:** 4/4.

### L3: `ensure_recheck` re-verifies and never re-runs
- **Change.** `benchmark/bench/p426_wave2.py`:
  - `Sequencer.ensure_recheck` now handles four cases:
    - a record without its sealed file → `Stop(1)`;
    - a sealed file without a record (the crash window) → `recover_recheck`;
    - a file that does not verify, or a record/file sha mismatch → `Stop(1)`;
    - neither file nor record → compute (unchanged).
  - New `Sequencer.recheck_attempts(gate)`.
  - New `Sequencer.recover_recheck(gate, path, doc)`. It requires the sealed file's `gate`, `axis`, `sessions`, `ref`, `test` and `attempts` to equal this gate over the current selected attempts. It then records `sha256` / `path` / `inside` / `operator_review` from the file, saves `sequence.json` and logs `RE-CHECK <gate>: recorded from the sealed file …`. The rc 5 / `--recheck-ack` handling then applies as before.
- **Tests:**
  - `test_l3_a_record_without_its_sealed_file_stops_and_never_reruns` (`m76_sim.recheck` is patched to raise if called)
  - `test_l3_a_sealed_file_without_its_record_is_reverified_and_recorded`
  - `test_l3_an_outside_sealed_file_without_its_record_still_stops_until_acked`
  - `test_l3_a_changed_file_without_its_record_stops` (guard; it passed on candidate 1).
- **Red:** 3/3 behaviour tests failed. One re-ran the re-check; two hit `Stop` rc 1 instead of recording, or instead of rc 5. **Green:** 4/4.

### L4: `tg2_strict_rows` is exactly the planned slots
- **Change.** `p426_wave2.tg2_strict_rows` refuses (`fz.Refusal`) in three cases: a row whose id is not a planned slot of the session, a DNF record of the session that is not a planned slot, and a slot with both a row and a DNF record. The existing missing-slot refusal stays, so rows ∪ DNFs == planned and rows ∩ DNFs = ∅.
- **Tests:**
  - `test_l4_strict_rows_refuse_a_stray_row`
  - `_refuse_a_stray_dnf`
  - `_refuse_a_slot_with_both_a_row_and_a_dnf`
  - `test_l4_a_dnf_of_another_session_is_not_this_sessions` (guard; it passed on candidate 1).
- **Red:** 3/3 failed with `DID NOT RAISE Refusal`. **Green:** 4/4.
- The test-writer's restored refusal test (delivery 3) is not mine.

### L5: the tg2 v8 refuses `--r1-off` / `--r1-on`
- **Change.** `benchmark/bench/p426_freeze.py`:
  - `parse_args` (v8, `--corpus tg2`) refuses either flag.
  - `cmd_v8_tg2` refuses them too, for direct callers.
- **Test.** `test_l5_the_tg2_v8_refuses_the_r1_flags[--r1-off, --r1-on]`: rc 2, no v8 written, "R1" in the refusal.
- **Red:** 2/2 failed (rc 0, a v8 was written). **Green:** 2/2.

### L6: one tg2 pair contract `("n16", "x")` at every tg2 entry point
- **Change.**
  - `p426_freeze`: new `TG2_PAIR` and `check_tg2_pair(arms)`, applied in four places:
    - `parse_args` (rehearsal / v8 with `--corpus tg2`);
    - `cmd_rehearsal` (tg2);
    - `cmd_v8_tg2`;
    - `write_amendment_tg2` (the v8 base's arms).
  - `p426_wave2`:
    - `kv_tg2_legs` raises `ValueError` for any other pair;
    - `check_args` (tg2) calls `fz.check_tg2_pair`;
    - `check_positives_args` accepts only `--arm-worktree n16=<path>`.
  - `run_tg2_chain.py`:
    - `--kv-arm` choices are `TG2_PAIR`;
    - `check_frozen_record` refuses a record whose `arms` are not `["n16", "x"]`.
- **Tests:**
  - `test_l6_the_tg2_freeze_refuses_a_pair_other_than_n16_x[n16,v / x,v]`
  - `test_l6_the_tg2_leg_table_is_n16_x_only[2]`
  - `test_l6_the_positives_run_on_n16_only[x / v]`
  - `test_l6_the_tg2_chain_refuses_arm_v_and_a_record_of_another_pair` (`[n16,v]` and `[x,n16]` records refuse; `[n16,x]` passes)
  - `test_l6_the_tg2_sequencer_refuses_a_pair_other_than_n16_x` (guard; it passed on candidate 1, whose `_check_lever_args` already refuses V).
- **Red:** 7/7 behaviour tests failed. **Green:** 8/8.

## Files changed (one line each)
- `benchmark/m62/inject_verify.py`: L1. The evidence key set is the row's recorded artifacts; a tg2 row requires `datefreeze`.
- `benchmark/bench/corpus_tg2.py`: L2. `verify_source` / `verify_inputs`; called by `prepare`, before materialisation, and by `spec_text`.
- `benchmark/bench/p426_wave2.py`:
  - L3: `ensure_recheck`, `recheck_attempts`, `recover_recheck`.
  - L4: `tg2_strict_rows`.
  - L6: `kv_tg2_legs`, `check_args`, `check_positives_args`.
- `benchmark/bench/p426_freeze.py`:
  - L5: `parse_args`, `cmd_v8_tg2`.
  - L6: `TG2_PAIR`, `check_tg2_pair`, `parse_args`, `cmd_rehearsal`, `cmd_v8_tg2`, `write_amendment_tg2`.
- `benchmark/chains/c147/run_tg2_chain.py`: L6. `--kv-arm` choices and `check_frozen_record`.
- `benchmark/bench/tests/test_m76_b4b1_impl_wave2.py`: the L1, L3–L6 tests and their helpers; `_round_trip` takes `extra_v8`.
- `benchmark/bench/tests/test_m76_b4b1_impl_corpus.py`: the L2 tests.

No fixture was added. Outside the copy I wrote only to `../scratch/`, plus pytest's own tmp dirs. One stray file landed inside the copy and I moved it out; see "Commands and results".

## Commands and results
All commands were `../fe_test.sh stack …` with the full output redirected to `../scratch/<name>.txt`.

1. Before the first edit, on candidate 1 (git stash not used):
   - `r1_base_impl.txt`: the five impl files, 100 passed. That output is `-q` progress only: 100 dots, no F/E, no totals line.
   - `r1_base_importers.txt`: the 44 test files that import a module I changed (directly, or through `b2_frozen*_support`). rc 0, so no failure and no error; that output also has no totals line.
   - `r1_base_closures.txt` / `.xml`: `test_p371_closures.py` and `test_tg2_universe.py`, because the new import edge `corpus_tg2 → m65.tg2_universe` enters a closure. 86 passed.
2. Red run of the new tests on candidate 1 (`r1_red.txt` / `.xml`): 29 tests, 25 failed, 4 passed. The L4 stray-DNF re-red after its test fix is in `r1_red_l4_dnf.txt` (1 failed, as intended).
3. Green run of the new tests (`r1_green.txt` / `.xml`): 29 passed.
4. After the fixes, the five impl files plus `test_p371_closures.py` and `test_tg2_universe.py` (`r1_after_impl.txt` / `.xml`): 215 passed, 0 failed. That is 100 prior impl tests + 29 new + 86.
5. After the fixes, the same 44 importing files (`r1_after_importers.txt` / `.xml`): rc 0; junit: 1561 tests, 0 failures, 0 errors, 2 skipped (1559 passed). The pre-edit run was rc 0 too (no failure or error).

The full `bench/tests` suite was not run, as the brief says.

One junit file from step 1 landed in `stack/scratch/`, inside the copy, because the junit path was relative to `benchmark/`. I moved it to `../scratch/` and removed the empty directory. Every later junit path is absolute.

## Deviations, with the code fact that forced each
1. **L1, the tg1 scaffold is also covered by "the row's recorded artifacts".** The disposition says "for the v2 scaffolds". The real tg1 probe writes the same `datefreeze_path` through the same `OpencodeArm.row_fields`.
   - The read-only `test_c147_inject_verify.py` builds tg1 rows with only the three base keys, so `datefreeze` is required only for tg2 (`REQUIRED_EVIDENCE`).
   - For tg1, a row without `datefreeze_path` is checked exactly as before. A tg1 row that records `datefreeze_path` with a matching digest now verifies, where before it failed `FAIL:evidence_sha256_keys`. That is a tg1 behaviour change, and the operator / designer may want to confirm it.
2. **L2, the checks sit in `prepare` / `spec_text`, not in `load_universe`.** `load_universe` is called with no checkout, by `grader_timeouts`, `identity`, `--print-identity` and `run_tg2_chain.load_names`, and the shared core re-calls it in `check_env` for every item. A checkout requirement there would refuse identity-only callers and cost a `git rev-parse` per call. `prepare` runs before every materialisation and `spec_text` before every prompt, which is where the ledger asks for the checks.
3. **L2, the inputs hash is loaded with `from m65 import tg2_universe`.** This is a static import, so `identity_closure` follows it: `benchmark/m65/tg2_universe.py` and its imports enter the tg2 probe's code closure, which rotates the tg2 closure identities.
   - `test_p371_closures.py` still passes, because the tg1 closure does not reach `corpus_tg2`.
   - The import relies on `benchmark/` being on `sys.path`, which holds wherever `bench` is importable.
   - `m65/tg2_draw.py` loads the same module by file path instead, which would hide it from the closure; I chose the static import.
4. **L3, the recovery check goes beyond the ledger.** A sealed file without a record is accepted only if its `gate`, `axis`, `sessions`, `ref`, `test` and `attempts` equal this gate's over the current selected attempts. Otherwise it is `Stop(1)`. The ledger says "re-verify the seal"; the extra comparison stops a sealed file from another selection from being adopted.
5. **L6, also enforced below the CLI.** The pair is also checked in `cmd_rehearsal` / `cmd_v8_tg2` / `write_amendment_tg2` and in `kv_tg2_legs` (as `ValueError`, matching `p426_plan.check_kv_pair`). Callers can reach these without `parse_args`. `p426_plan.KV_PAIRS` is outside scope and unchanged.

## What I could not satisfy, and why
- **L1, the real probe is not run.** The real probe needs the router, the worker and opencode, so the probe process is faked by the worktree's interpreter shim. Everything after it runs for real: the row's evidence fields (`row_fields`), the grade reports (`grade_reports` over a recorded tree), `BoxSeqOps.positive_inject` / `inject_verify` and the `inject_verify.py` subprocess. Real output on the box stays acceptance criterion 3 (ledger L17).
- **Counts for the before/after importer comparison.** The pre-edit importer run has rc 0 but no totals line, because `fe_test.sh` runs quietly. The after run has junit counts. The comparison is therefore "all passed before (rc 0)" against the after counts above.

## Questions
- Deviation 1: should the tg1 scaffold keep the strict three-key set (tg1 rows that record `datefreeze` stay failing), or accept the recorded artifacts as implemented?

---

# Fix round 2 (verify round 2 of 3): V1, V2

Both adopted items are fixed, each with a test that failed before its fix and passes after. Nothing was committed.

Red run, before any round-2 source edit (`r2_red.txt` / `.xml`): 4 tests, 3 failed, 1 passed. The test that passed is a guard for behaviour the code already had. Green run (`r2_green.txt` / `.xml`): 4 passed.

## V1: every sealed re-check document is checked against the current selection
- **Change.** `benchmark/bench/p426_wave2.py`:
  - New `Sequencer.check_recheck_doc(gate, path, doc)`. It requires the document's `gate`, `axis`, `sessions`, `ref`, `test` and `attempts` to equal this gate over the currently selected attempts (`recheck_attempts`), and a `recheck` object to be present. A mismatch raises `Stop(1)` (the operator decides) and nothing is recomputed.
  - `ensure_recheck` calls it whenever a sealed file exists, with or without its record, before the record or sha comparison.
  - `recover_recheck` no longer runs its own copy of the check.
- **Tests** in `test_m76_b4b1_impl_wave2.py`:
  - `test_v1_a_recorded_recheck_of_another_selection_stops_on_resume[n16, x]`. Re-check 1 is recorded and sealed for s1 attempt 1. An s1 rerun of that arm then selects attempt 2. On resume: rc 1, "attempts" in the reason, the `sequence.json` record unchanged, and the re-check is not re-run.
  - `test_v1_a_recorded_recheck_of_the_current_selection_resumes` (guard; it already passed before the fix).
- **Red:** 2/2 behaviour tests failed with `DID NOT RAISE Stop`. **Green:** 3/3.

## V2: the prompt path verifies the checkout
- **Change.** In `benchmark/bench/corpus_tg2.py`, `Tg2Corpus.spec_text` (which `prompt` uses) now calls `verify_source`: the checkout sha must match, then the item's inputs. Before, it called only `verify_inputs`.
- **Test.** `test_v2_the_prompt_refuses_a_checkout_at_another_commit` in `test_m76_b4b1_impl_corpus.py`. The item is prepared on the pinned checkout. A corpus on the same, unchanged bytes then reports another checkout sha, and its prompt must refuse with `TransportAbort` naming "polyglot".
- **Red:** 1/1 failed with `DID NOT RAISE TransportAbort`. **Green:** 1/1.

## Files changed in round 2
- `benchmark/bench/p426_wave2.py`: V1 (`check_recheck_doc`, `ensure_recheck`, `recover_recheck`).
- `benchmark/bench/corpus_tg2.py`: V2 (`spec_text`).
- `benchmark/bench/tests/test_m76_b4b1_impl_wave2.py`: the V1 tests.
- `benchmark/bench/tests/test_m76_b4b1_impl_corpus.py`: the V2 test.

## Named test files re-run after round 2
- The five impl test files plus `test_p371_closures.py` and `test_tg2_universe.py` (`r2_after_impl.txt` / `.xml`): 219 passed, 0 failed. That is 215 from round 1 plus the 4 new tests.
- The same 44 importing files as in round 1 (`r2_after_importers.txt` / `.xml`): rc 0; junit 1561 tests, 0 failures, 0 errors, 2 skipped (1559 passed). Same as after round 1.
