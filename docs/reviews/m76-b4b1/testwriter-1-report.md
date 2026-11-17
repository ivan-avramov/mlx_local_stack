Delivery 1 is written but only partly checked: 54 of the 247 new tests pass on the baseline and the other 193 fail. All 193 fail because the spec's behaviour doesn't exist yet. I did not run the stack suite.

The tests are in `benchmark/bench/tests/`:
- `test_m76_b4b1_fe_support.py` (helpers, no tests)
- `test_m76_b4b1_fe_corpus.py`, `test_m76_b4b1_fe_grade.py`, `test_m76_b4b1_fe_chain.py`, `test_m76_b4b1_fe_wave2.py`
- `test_m76_b4b1_fe_golden_tg1.py`
- fixtures under `fixtures/m76_b4b1_fe/`: the recorded `tg2_grade` trees (sha256-pinned) and the tg1 goldens

I committed nothing and touched no `.git`.

## Baseline result

- **54 pass:**
  - **Pins and fixtures:** the fixture pins and the committed draw and universe pins.
  - **Baseline contrast:** the baseline's symlink failure in `sg.manifest`, plus baseline `t_coop` and `validate_reports` behaviour.
  - **Unchanged tg1 behaviour:** the tg1 argv, the tg1 hooks (Go R2, Python stall target), the tg1 evidence and dossier-pair rules, the tg1 corpus and tg1 closure fields, and the tg1 B8 and SIGNALS regeneration (byte-identical to the committed P426 files).
  - **Cases the baseline already handles:** the sealed run records under `wave2.tg2` and the recorded tampered trees' classification.
- **193 fail** with `Failed: …` messages (one test, `test_tg1_probe_closure_identity_rotates`, fails by assertion). Almost all fail because `corpus_tg2`, `tg2_runner`, `run_tg2_chain.py`, `schedules.tg2_p426` / `check_tg2_p426`, `P426_CONFIG_IDS`, the tg2 carrier or the new CLI flags don't exist. The rest fail on specific behaviour:
  - `validate_reports` doesn't check tg2 artifacts or outcomes.
  - The harvest `classify` has no rule for the streams in a grade-sequence directory or for `.tg2-registry/*.json`.
  - `write_kv_dossier` takes no `corpus=`.
  - `t_coop` takes no corpus grader bound.
- **tg1 golden:** I recorded it on the baseline (schedules, argv, config, plan, harvest classes, validator, `t_coop`, corpus prompt and identity, probe identity). It is paired with the B8 and SIGNALS regeneration tests that pass; the closure-rotation test is among the 193 and fails on `probe_code_sha256` until the shared core is edited.

## Checks on the tests themselves

I ran the grade-mapping, schedule, strict-rows and re-check tests against throwaway reference code written literally from the spec, then deleted it. They gave 38/38 and 50/50, so the expectations and fixtures are consistent with the spec. They have not run against a real candidate.

## Name guesses

All are in `GUESSES` in the support module, and a wrong spelling fails with `SPELLING GUESS <key>: …`. The main ones:
- the `Tg2Corpus` constructor (tg1's signature);
- the chain entry's parsed attributes (`tg2_leg` and so on);
- `tg2_strict_rows(leg_roots, session)`, where `leg_roots` is a list of one arm's attempt roots;
- `tg2_p426(..., "r2"/"r3")` or `rehearsal=True` for the rehearsal schedules;
- the way `t_coop` receives the corpus bound;
- `write_kv_dossier(..., corpus=)`;
- the `p426_freeze` / `p426_wave2` flag spellings.

## Gaps in criterion 1

- **Sequencer behaviour is not tested:** the re-check stop (rc 5), the `--recheck-ack` resume, the positives-record resume refusal and the full freeze round-trip. Their driver (`Sequencer`, `SeqOps`) is too tied to code the spec doesn't name. I tested what is visible instead: the new flags parse, the re-check verdict on strict-row input, and the sealed-record publication.
- **`validate_leg` / A4 / `session_pinning_gate` and the `--evidence p426` argv for tg2 are not tested.** These need a driven chain.
- **No full run through `arm_runner` with a mocked agent.** I tested the corpus contract, the probe parser and the probe's `--print-identity`, but not an item run.
- **No recorded real trees for `timeout`, `mem_kill`, `crash` and `storage_cap`.** Those mappings use synthetic `Tg2Grade` objects, labelled as such in the tests.
- **The grade-call test patches `tg2_grade.grade_item`.** It only sees the call if the candidate calls it as `tg2_grade.grade_item`, not through a from-import.
- **One recorded file is dropped:** the 15 MB `rust/flood/.../execute.stdout`; the manifest lists it as `dropped`.

The golden regeneration used a temporary `.record` marker file (removed). Environment-variable prefixes on the test command were not allowed here.
