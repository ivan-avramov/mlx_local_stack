**Verdict: merge once the designer amends `test_registry_published_set`.** I found no defect in the candidate. The delivery-1 files plus the implementer's now run 392 passed, 0 failed.

## Counts

- **My delivery-1 files:** 292 passed, 0 failed. They are `_corpus`, `_grade`, `_chain`, `_wave2` and `_golden_tg1`, and the total includes 2 tests I added.
- **Implementer `test_m76_b4b1_impl_*.py`** (5 files): 100 passed, 0 failed.
- **Environment (`.venv-bench`):** none of these tests failed for the missing `.venv-bench`, so nothing needs naming. My probe tests spawn `sys.executable`.
- **Not run:** the full `bench/tests` suite, as instructed. I read `test_registry_published_set` without amending it; run on its own, it fails the same 2 as before.

## The 26 failures

All 26 were my seam guesses, so I amended the tests and kept each assertion's intent. None was a candidate defect. The first six rows are the 8 failing rows of the designer's list.

| Tests | Cause | Amendment |
|---|---|---|
| `test_rehearsal_mapping[r2]`, `test_record_kinds[argv4]`, `test_r2_*` (2) | My `_argv` ran R2 on N16. Spec §3 puts R2 on X and R3 on N16; the candidate enforces this (`run_tg2_chain.py:151`). | `_argv` picks arm `x` for r2. I added `test_rehearsal_on_the_wrong_arm_is_refused` (r2 on n16, r3 on x), 2 new tests. |
| `test_plan_of_a_frozen_tg2_schedule[pilot, s2]` | I expected slot base `tg2-p426\|n16\|…`. tg1's planner uses the `ArmBinding` arm id `oc`. The spec fixes only the `tg2-p426` prefix. | Expect `tg2-p426\|oc\|…`. **Accept.** |
| `test_t_coop_uses_the_corpus_grader_bound` (4) | I expected 1825, the 660 s join plus the corpus bound. The candidate gives 2545. tg1's 660 is `grade_join_timeout_s` over tg1's table, 2×300+60. For tg2 the same function over the corpus identity gives 1380. | Expected join is `arm_runner.grade_join_timeout_s(bound)`. The candidate is correct, and I judge deviation 13 accept. |
| `test_validate_reports_*` (11) | The tg2 rules are opt-in via `grader="tg2"`. | Pass `grader="tg2"` for tg2 languages. |
| `test_probe_parser…` | The `--tg2-inject` dest is `tg1_inject`. | Read either dest. |
| `test_probe_without_universe…`, `test_probe_identity_with_an_inject_kind` | I over-asserted. tg1's `--print-identity` also never prints the universe sha or the addendum digest. They enter only through `scaffold_policy_sha256`. | Default universe: policy sha equals the explicit tg2 universe's and differs under tg1's universe. Inject: plain plus stall, loop and alloc give 4 distinct policy shas, and a bogus kind is refused. |
| `test_strict_rows_refuses_a_stray_row` | The spec's only refusal is a planned slot with neither row nor DNF. The candidate ignores a stray row, so it never enters the result. | Now asserts the stray row is excluded (80 items) and a duplicate row refuses. |
| `test_freeze_v8_for_tg2…`, `test_freeze_v8_tg1_unchanged` | The candidate refuses missing `--positives` / `--r1-*` in the command (rc 2, `REFUSED:`), not in argparse. | Drive `p426_freeze.main` with a stub ops and read the refusal text. |

I dropped one assertion: that a tg2 v8 refuses extra `--r1-*` flags. The spec says "no R1" but does not say to refuse them, and the candidate ignores them silently.

**`grader="tg2"` coverage:** both production callers pass it for the tg2 scaffold. `chain_ops.validate_leg` does so via `flat_label_kw` at the two `chain_core` call sites (`chain_ops.py:1282`, `chain_core.py:2079` and `2789`). `m62/inject_verify.py:101` does too. The fragility is that a new consumer, for example in B4b-2, must remember to pass it.

## Review findings

| # | Severity | Where | Finding |
|---|---|---|---|
| 1 | Process | `test_registry_published_set.py:66` | `EXTRACTORS` lacks `"opencode-bench-v2-web-tg2": _opencode_ids`. This is legitimate fallout of the spec-required target. The designer adds the entry. |
| 2 | Low | `p426_wave2.py:1076-1094` | `ensure_recheck` seals the file (`write_exclusive`) and only then `save()`s `sequence.json`. A crash between the two leaves the file without a record, and a resume stops with rc 1 "not the sealed re-check sequence.json records". It fails closed and the operator can recover. |
| 3 | Low | `p426_wave2.py:1394` | `positive_inject` treats a non-zero probe rc with no output file as a transport abort. It retries once, then the kind fails. This is fail-closed, but a probe crash looks the same as a transport abort in the record. |
| 4 | Low, for B4b-2 | `row_scores.py:43` | `is_tg1` matches only the tg1 label, so tg2 rows get no sidecar join. Out of B4b-1 scope. B4b-2 should decide. |
| 5 | Info | `corpus_tg2.py:107` | `grade_outcome` raises `TransportAbort` for an outcome outside the scored set. The spec is silent. It is fail-closed, and I accept it. |

## The 17 deviations

All 17 are accepted. The notes that matter:

- **1, universe loader:** `Tg2Corpus.load_universe` (`corpus_tg2.py:134`) checks the recorded facts instead of `m65.tg2_universe.load`. Those facts are the sidecar sha, the pin, the grader, materializer, image and polyglot versions. The implementer reports that `m65.tg2_universe.load` refuses the committed universe on the baseline, on `freezer_sha256`. That is existing drift in code I was told is read-only, and I did not run it myself; the designer should know about it.
- **2, Rust `Cargo.lock`:** the normalised view omits any lock the prepared tree does not hold. This is consistent with H2 and with the grader regenerating the locks.
- **4, opt-in receipt rules:** see above.
- **5, harvest rule limited to tg2 item directories:** the regex `TG2_GRADES_RE` in `p426_harvest.py:229` covers real slugs and keeps the frozen tg1 tests unclassified.
- **7, `tg1_inject` dest:** the shared core reads one inject attribute.
- **8, tg1 chain import:** `run_tg2_chain` imports the tg1 chain module, so tg1 chain edits now rotate the tg2 chain closure. This is consistent with C178.
- **9, rehearsal directory:** `m76/p426/rehearsal.tg2` is the spec's literal path.
- **10, re-check 2 timing:** it runs after the reload pair, following the spec's order line. The spec's own text says "after s2", so it is internally inconsistent. Re-check 2 never stops, so this is harmless.
- **11, `positives.json` location:** the sequencer reads it from `--record-dir`. This is an operator-alignment point, and a mismatch refuses loudly.
- **12, docker gate:** it checks both `aider-benchmark` and `tg2-grader`.
- **15, 6 h pilot deadline:** `TG2_PILOT_DEADLINE_S` duplicates `REHEARSAL_DEADLINE_S`, and they are tested equal.

## Checked against the spec by reading

- **Amendment formula:** `1.5 × Σ n_lang × w_lang + 1800 + 3660` and the 382 s floor (`p426_freeze.py:1005-1041`).
- **Re-check gate:** seal, stop with rc 5, `--recheck-ack`, and re-check 2 never stopping (`ensure_recheck`).
- **Positives record fields and retry rule:** one retry per run, only on a transport abort.
- **`inject_verify` attempt handling:** it retains the latest attempt per kind, so a retry is handled correctly.

## Untested box-side seams

`positives_session`, `positive_inject` and `inject_verify` have only been exercised through fakes, never on a box. I read them and found them consistent with the spec, but nothing here ran them.

My frozen delivery-1 files no longer match `SHA256SUMS`, because of the amendments above.