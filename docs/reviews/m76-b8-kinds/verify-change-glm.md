## Findings

### K1–K8, F1–F5, R1 — resolved/not

**K1 — resolved (confirmed).** `EXISTING-TEST-AMENDMENTS.patch` adds `--axes m1` to the `n16,x` half of `test_main_kv_refuses_v_before_anything_runs` (`test_m76_b3_impl_wave1.py:152-153`). With the kv default axes now the five planned kinds, `preflight_kv` no longer refuses on `m1`; naming `m1` explicitly restores the certified-by refusal the test exists to check. Intent preserved.

**K2 — resolved (confirmed).** `verify_all_kv` keeps `kinds` (subsets for tests/fixtures), `None` = planned kinds, CLI never passes another set (`test_f4_the_cli_verifies_the_planned_kinds` spies `kinds=None`). The hazard is closed at the consumer by F2: `_kv_incomplete` + `kv_flags` emit one blocking `wave1_incomplete` per absent/rejected planned pair (`test_f4_an_empty_subset_never_reads_clean` → 10 flags; `test_f4_a_subset_record_records_dropped_and_is_flagged_by_compute_kv`).

**K3 — resolved (confirmed).** `compute_kv` reads `w1.get("dropped")`; dropped kinds report `status:"not_run"` with `ruling` for A2–A4 and M1 (never `missing`) (`p426_signals.py:1674-1677,1692-1694`). `_kv_incomplete` flags every rejected/absent planned pair (`p426_signals.py:1738-1747`).

**K4 — resolved (confirmed).** `test_m76_b8_kinds_impl_fixround1.py` has F2 tests that build a B8 record and run `compute_kv` on it (e.g. `test_f2_a_complete_record_raises_no_wave1_incomplete_and_m1_is_not_run`, `test_f2_a_rejected_planned_pair_is_a_blocking_wave1_incomplete`, `test_f2_an_absent_planned_pair_is_a_blocking_wave1_incomplete`).

**K5 — resolved (confirmed).** `verify_all_kv` sets `w1["dropped"] = kv_w1_dropped(build)` whenever `kinds is not None` (`p426_verify.py:2201-2204`), so a subset record still carries the build's `dropped`. The default path populates `dropped` inside `verify_wave1_kv`.

**K6 — resolved (confirmed).** `KV_W1_KINDS` is defined in `p426_plan.py:491`; `p426_verify.py:1366` imports it; `kv_w1_kinds` no longer references `p426_verify` (`test_f5_one_definition_of_the_kinds` asserts `V.KV_W1_KINDS is P.KV_W1_KINDS` and `"p426_verify" not in inspect.getsource(P.kv_w1_kinds)`).

**K7 — resolved (confirmed).** F1.1: `kv_provenance_problems` runs `_kv_foreign` on raw strings before normalising each arm's own worktree component via `_kv_own_paths` (`p426_verify.py:1700-1706`); a leaf naming another arm is a rule-2d reason. Content hashes beside paths stay compared (`test_f1_a_content_hash_beside_the_path_stays_compared`). F1.2 moves `result_file`/`result_sha256` out of the cross-arm diff (`KV_PROVENANCE_EXCLUDED`) into per-arm integrity (`_kv_result_reasons`).

**K8 — resolved (confirmed).** F3: `offline_counter` passes `deployed_template_kwargs(entry)` to every `apply_chat_template` (calibration included) and records `template_kwargs` in meta (`m76_ids.py:290-303`). ids.json regenerated; `IDS_CHANGES.md` records old/new sha256, chars/token, per-rung counts and budgets. Designer acceptance A2 confirms it loads and the diff is confined.

**F1 — resolved (confirmed).** F1.1 + F1.2 as above. `test_f1_arm_local_corpus_path_is_accepted`, `test_f1_a_corpus_path_naming_the_other_arm_is_rejected`, `test_f1_per_arm_result_file_and_sha_are_accepted`, `test_f1_one_arms_altered_result_bytes_reject_naming_that_arm`, `test_f1_a_result_file_naming_another_file_is_rejected`, `test_f1_a_stamp_absent_on_one_arm_is_rejected_naming_it`.

**F2 — resolved (confirmed).** As K3/K4.

**F3 — resolved (confirmed).** `test_f3_the_counter_passes_the_deployed_template_kwargs_to_every_call`, `test_f3_unset_kwargs_are_omitted`, `test_f3_the_committed_ids_records_the_served_template_and_loads`. Real-tokenizer reference now renders with `deployed_template_kwargs` (`test_m76_b3_fe_fix_v15.py:337-342`).

**F4 — resolved (confirmed).** `verify_all_kv(..., kinds=None, build="s3")`; `test_f4_verify_all_kv_default_is_the_planned_kinds`, `test_f4_the_cli_verifies_the_planned_kinds`, subset tests.

**F5 — resolved (confirmed).** As K6.

**R1 — resolved (confirmed).** `KV_STAMPED_KINDS = ("reasoning","longctx")` (`p426_verify.py:1641`); `_kv_result_reasons` requires both `result_file` and `result_sha256` on every manifest of those kinds, per arm/per A5 item, with no "neither arm has a stamp" skip (`p426_verify.py:1710-1733`). `test_r1_both_arms_stripped_of_their_stamps_are_rejected[reasoning,longctx]` and `test_r1_unstamped_kinds_stay_unstamped` lock it. The shared `World.leg` longctx branch is amended to stamp as the runners do (`EXISTING-TEST-AMENDMENTS.patch` → `test_m76_b3_impl_verify.py:138-141`), which is what the implementer's round-2 report identified as the cause of the 11 new read-only failures.

### Can it accept a wrong pair?

**Per-arm fact normalised away — not (confirmed).** The foreign-arm check (`_kv_foreign`) runs on raw strings before `_kv_own_paths` normalises only the arm's OWN component (`p426_verify.py:1700-1703`), so a path naming the other arm is flagged, not normalised into equality. Content hashes beside paths (e.g. `corpus_sha256`) are compared across arms (`test_f1_a_content_hash_beside_the_path_stays_compared`). The own-path regex is anchored to `m76-f45-<arm>`/`m76-q-<arm>` followed by `/` or end, so it does not over-match `m76-f45-<arm>-extra`.

**Stamp check satisfied by the wrong file — not (confirmed).** `_kv_result_reasons` binds both stamps to the file B8 actually read: `want = dict(result_file=Path(rel).name, result_sha256=reader.inputs.get(rel))` where `rel` is the path B8 read and `reader.inputs[rel]` is the sha256 of the bytes B8 read (`p426_verify.py:1726-1730`; `Reader.read_bytes` sets `inputs[rel]` at `p426_verify.py:96`). `result_file` is a basename that must equal the read file's basename (unique per directory), and `result_sha256` must equal the read file's sha256; both must hold together, so a different file cannot satisfy the check. A consistently tampered file+manifest is caught by the separate SCRUB sha (rule 1) check the designer's A4 exercised.

### Can it flag/refuse a valid one?

**Not on the real harvest (confirmed by designer acceptance A3).** B8 rc 0, 10/10 planned pairs accepted, `not_run` m1/b1,m1/b2, `dropped.m1`, signals rc 0 with no `wave1_incomplete`. The stamp requirement is restricted to the kinds whose runners write both stamps (`KV_STAMPED_KINDS`); Math500/cjudge/vision stay unstamped and are not rejected for missing stamps (`test_r1_unstamped_kinds_stay_unstamped`). A4 negative (A4) confirms a removed leg refuses and a flipped result byte is rejected and flagged.

### Is ids.json exactly the served counts with everything else unchanged?

**Resolved (confirmed).** `IDS_CHANGES.md` records 432 differing leaves, all in `axes.longctx.budget` (284, incl. `total` and the 196608 resolved budgets), `budget_inputs.prompt_tokens` (122), `budget_inputs.counter` (2: `chars_per_token`, new `template_kwargs`), and derived `prompt_deviation` (24) — the regions erratum v1.1a allows. A5 items, smoke items, blocks, tier list, sampler seeds, and the Math500/cjudge/vision/reasoning axes are byte-equal to the old file. Every served Wave 1 A5 row is 130,776 (the value K8 flagged); `m76_ids.load` accepts it. Per-item deltas 1,645–2,489, all inside the rung band.

### Do the existing-test amendments keep each test's intent?

**Resolved (confirmed).**
- K1: still tests the m1 certified-by refusal, just with `--axes m1` named explicitly.
- F3 stand-ins (`test_m76_b3_impl_counter.py:31`, `test_m76_b3_fe_fix_v15.py:293`): `apply_chat_template` now takes `**template_kwargs` and ignores them; the counting/defect checks are unchanged.
- F3 real tokenizer (`test_m76_b3_fe_fix_v15.py:337-342`): the reference renders with the same deployed kwargs as the counter, preserving the "counter == independent tokenisation" intent; it also asserts `meta["template_kwargs"] == kw`.
- A5 fixture stamping (`test_m76_b3_impl_verify.py:138-141`): `World.leg`'s longctx branch stamps `result_file`/`result_sha256` as `run_reasoning`/`run_retrieval` do, making the fixture match the real harvest shape the verifier now requires. The cjudge branch is unchanged (cjudge is not stamped).

### Anything else the diff breaks or leaves failing

**Finding A — minor; confirmed; verification gap.** The full regression on candidate 3 + `EXISTING-TEST-AMENDMENTS.patch` was not run by any single report. The implementer ran it pre-amendment (`after_all_r2.txt`: 23 failed — K1 + 11 F3 + 11 R1/`World.leg`); the test-writer ran only the seven named files on candidate 2 (214 pass); the designer ran real-data A2–A4. The amendments are constructed to fix exactly those 23, but no report confirms the 35-file set is green on candidate 3 + amendments.
- Scenario: a latent interaction between the R1 stamp requirement and a read-only test that builds a reasoning/longctx leg through a path other than `World.leg` (e.g. a bespoke fixture) would still fail and not be caught.
- Proposed change: run the full regression (`pytest` over every file importing `p426_plan`/`p426_verify`/`p426_wave1`/`p426_signals`/`m76_ids` plus `p613*`/`p586_frozen`) on candidate 3 + amendments and record the result before merge.

**Finding B — minor; confirmed; `not_run` incomplete for subset records.** In `verify_wave1_kv`, when `kinds is not None`, `dropped = {}` internally, so the trailing `for kind in KV_W1_KINDS: if kind in dropped and kind not in kinds` loop is a no-op and `not_run` does not list `m1/b1`,`m1/b2` for subset records (`p426_verify.py:1959-1963,2022-2023`). `verify_all_kv` then sets `w1["dropped"] = kv_w1_dropped(build)`, so `dropped` is correct and `compute_kv` reports M1 as `not_run` with ruling via `dropped` (`p426_signals.py:1692-1694`). The default/CLI path is correct (there, `dropped` is populated inside `verify_wave1_kv` and `not_run` lists m1).
- Scenario: a consumer that reads `wave1.not_run` directly (rather than `dropped`) for a subset record sees no m1 entries, while `coverage.dropped` and the M1 axis say `not_run`. Internally inconsistent for subsets only.
- Proposed change: in `verify_wave1_kv`, populate `dropped` from `kv_w1_dropped(build)` regardless of `kinds` (or have `verify_all_kv` also append the dropped blocks to `not_run`), so `not_run` and `dropped` agree for subset records too. Test/fixture-only impact, so minor.

**Finding C — minor (cosmetic); confirmed.** `kv_provenance_problems` truncates the foreign-path list to three items in the reason text: `f"{arm} manifest names another arm's worktree: {foreign[:3]}"` (`p426_verify.py:1704-1705`). A manifest naming many foreign-arm paths still rejects the pair, but the reason names only the first three.
- Proposed change: drop the `[:3]` or render a count, e.g. `f"{arm} manifest names another arm's worktree ({len(foreign)}): {foreign[:3]}…"`.

No blocker or major found.
