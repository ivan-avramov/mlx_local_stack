# B2 delivery 3f: s9 review, §14 mapping and verdicts

**Verdicts:**
- **s9: fix first.** The harvest is sound on secrets, symlinks, staging and the commit point. But a foreign email inside a `main`-destined file is published to the public `main` (P1), and an unset `user.email` silently turns off the operator-email refusal (P2).
- **B2 candidate as a whole: fix first.** It is not ready for the strict verify. The final-round queue is still open (flat-layout DNF, P510, R3-limit, P23), and P1 and P2 come on top.

Nothing was committed or pushed, and no candidate file was edited.

## Test runs

- **Support checks on the baseline:** `test_b2_frozen_s0_support.py` and `test_b2_frozen_add_support_check.py` gave **55 passed**.
- **Whole set on the s9 copy** (synced again with `sync_to_s9.sh`, run with `run_candidate_s9_tests.sh` over the 20 files): **469 tests collected, 17 FAILED, no ERROR lines.**
  - The pytest totals line was not captured, so the 452 passes are inferred from the collected count, not read from pytest.
  - My new launch-log test failed on the first run. The second run, after I fixed my test, is the one above.

### The 17 failures

| Test(s) | Count | Class | Evidence |
|---|---|---|---|
| s0 `legacy_chain_goldens_hold_on_the_base_commit`, `item_barrier_fake_probe_completes_under_the_baseline_chain` | 2 | By design | These only hold on the baseline, where they pass. |
| s7 `records_destined_for_main_…`, `p426_dnf_record_…`, `transport_dnf_…` ×3, `dnf_followed_by_a_normal_item…`, `third_dnf…`; add_ledger `dnf_is_ledgered…` | 8 | (a), queued: flat-layout DNF | `CHAIN ABORT: DNF refused: the rows of the failed attempt do not validate: runtime_epoch_id: None != …; row_arm: python/p1 None != 'oc'` |
| fix_cases `r3_the_dnf_limit…`, `p23_a_dnf_records_its_item_record…` | 2 | (a), queued: R3-limit and P23 | Same DNF abort. |
| fix_cases `p510_…[iso-strings, short-pair, not-a-pair, dict, not-a-list]` | 5 | (a), queued: P510 | `bench_watch.py:506–507` `_overlap`: `TypeError` / `IndexError` |

- **Nothing else remains.** No failure falls outside the queued items.
- **P67:** my set has no test tagged P67, so I cannot show P67 open or closed. It may be the same defect as the DNF rows above.
- **My one test defect this round (c), now fixed:** the launch-log test assumed the published file was named `<attempt>.stdout`. The candidate publishes it as `logs/launch.stdout`, and the spec leaves the name open. The test now uses the entry's own `published` path.

## Tests touched in 3f (all tagged post-reveal 3f)

- `test_b2_frozen_fix_cases.py::test_fix_p536_topology_a_makeup_leg_that_stops_early_records_its_unrun_occurrences` (amended): `not_run` now expects both occurrences, the unlaunched one and the one invalidated at its barrier.
- `test_b2_frozen_s9_harvest.py::test_new_a_foreign_email_is_listed_for_review_never_refused` (amended):
  - `HARVEST.json` carries `review.emails_count` and the file's portable path;
  - the address is only in `$STACK_WORKDIR/p426/review/<attempt>.emails.json`;
  - it is not under `main` and not printed.
- `test_b2_frozen_s9_harvest.py::test_new_the_sequencers_launch_log_is_inventoried_and_routed_to_evidence` (added): `<out-base>/logs/<attempt>.stdout` is inventoried with a typed source and its sha, published to the evidence stage, and absent from `main`.
- `test_b2_frozen_add_scrub.py::test_new_a_foreign_address_is_listed_for_review_and_published` (amended to the review-file shape, plus `monkeypatch` for `STACK_WORKDIR`). The module docstring is updated too.
- `test_b2_frozen_s4_reconcile.py::test_new_the_ready_hook_writes_the_ready_record_and_accepts` (amended): `log_cursor.path == "<WT>/logs/mlx_vlm.log"`.
- `test_b2_frozen_s7_locks.py::test_new_chain_json_is_portable` (added): a pilot leg with no DNF; `chain.json` has `argv` and `probe`, and contains neither `tmp_path` nor the home path.

All except the queued DNF and P510 tests pass on s9.

## s9 review findings

| Id | Where | Severity | What goes wrong |
|---|---|---|---|
| P1 | `p426_harvest.py`, `Gate.check` / `harvest_wave2` (diff 381–385, 839–844) | **High (data boundary)** | A foreign address in a `main`-destined file is only listed for review; the file itself is still published to `main`. The `piicheck` pass has no email pattern. Example: a model's Go diff keeps an `// Author: x@y.org` header; the per-item `*.diff` goes to public `main` with the address in it. §15 assumes third-party text lands "on `evidence` only". **Fix:** a foreign address in a `main` file refuses (quarantine for the operator). The 16.8 ruling only addressed `HARVEST.json`, so this is also a spec gap. None of my tests covers it. |
| P2 | `p426_wave2.py`, `Sequencer.run` (`self.emails = tuple(self.ops.operator_emails())`); `BoxSeqOps.operator_emails` | **Medium (fails open)** | With `user.email` unset or `git` failing, the email tuple is empty. The operator's own address is then treated as foreign: listed for review, not refused. **Fix:** an empty tuple is `REFUSED:` rc 2. |
| P3 | `BoxSeqOps.harvest` (diff-all 5401–5405) | Low (operability) | stdout and stderr are captured and dropped, so an rc-4 stop never shows the harvest's `REFUSED:` reason. The operator has to rerun the CLI by hand. **Fix:** log the `REFUSED:`/`ERROR:` line; it holds no values. | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| P4 | `_log_slices` (diff 693) | Low | A `finalized: false` record is not rejected here; the check is `finalized is None`. It is still refused later because `offset_end` is `None`, so this fails closed, but the stated reason is wrong. | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| P5 | `harvest_wave2` | Low | A VALID leg missing `watch.jsonl` is not refused, although §11.2 and §12 list the watcher receipt. In practice the sequencer would mark that leg speed-invalid first. | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| P6 | `chain_core.portable_doc` (diff 9–27) | Low, spec gap | A fourth token, `$HOME`, is used alongside the ruling's three. It passes the scrub-identity rule and leaks no username. The spec should list it or rule it out. | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->
| P7 | `_publish_records` (diff 959–960) | Low | A multi-file `publish_run_files` has no single commit point; a crash between renames leaves part of the set published. A rerun repairs it (same bytes count as done). | <!-- allow-shorthand: verbatim helper output (severity word / test constant) -->

**Data-boundary checks that came out clean:**
- Refusal lines carry only file names and pattern names (`piicheck` `why` is the pattern name, not the match).
- `OSError` output prints only `strerror`.
- Secret values stay in memory, and the scan covers both original and scrubbed bytes.
- Symlinks are opened with `O_NOFOLLOW` and walked with `lstat`.
- The review file is written only after a successful stage.
- `chain.json`, attempt JSONs, DNF sidecars and ready cursors are now portable. The attempt JSONs are written but never read back (`chain_core.py:1482–1546`), so not expanding them on resume is safe.

## The implementer's calls

| Call | Judgment |
|---|---|
| J1 stages and destinations | Accept |
| J2 routing | Accept; change for P1 (foreign email in a `main` file) |
| J3 run and evidence dirs found by `run_id` | Accept |
| J4 symlinks in a final tree | Accept |
| J5 reference shapes | Accept. Spec gap: bare `$STACK_WORKDIR` strings are not treated as references |
| J6 barrier rules | Accept |
| J7 `<WT>` from `--frozen-record` | Accept. A rehearsal worktree outside `$STACK_WORKDIR` would refuse "cannot be resolved", which fails closed |
| J8 | Superseded by the 16.8 ruling; the candidate now follows it |
| J9 dossier `harvest_sha256: None` | Accept. Spec gap: §16.7 does not say |
| J10 `piicheck` on `main` | Accept |
| J11 rc 2 / rc 1 | Accept |
| U3 fail-closed rule table | Accept as designed. Expect additions after the first real rehearsal harvest |
| Ready-cursor change in `p426_hooks` (beyond the ruling's wording) | Accept; my s4 test now pins it |

## §14 acceptance criteria → my tests

**1. §13 tests pass, full suite green, legacy goldens byte-identical.** Covered in part.
- Covered across s1–s9, add_* and fix_cases. Goldens: s1 `test_inv_*_golden_item_order` and `serialized_tg1_chain_config…`; s3 `test_inv_legacy_hooks…`; s2 `test_inv_*`; s0 baseline goldens.
- **Not covered:**
  - the full stack suite with `STACK_WORKDIR` set (the strict verify has to run it);
  - the `request_usage` ↔ log pairing on the committed rehearsal fixture;
  - the unmocked production topology, which my fix_cases `Topology` only approximates in-process.
- For the strict verify: the candidate changes `tests/p371_baseline/golden_refresh_c221.json` and the p371 tests. Someone needs to confirm that golden change is the approved C221 one.

**2. Rehearsal R1 VALID, R2 INVALID, R3 VALID with the kill scored.** Mechanics only.
- Tests: s1 `rehearsal_injections_refuse_without_rehearsal`; s7 `rehearsal_runs_the_smoke_shape…`; fix_cases R2 exact reason and R3 stall; s8 v8 gating on R1/R2/R3 records.
- The real criterion needs the real rehearsal.

**3. `p426_freeze` writes records only when checks pass; mutations refuse.** Covered by:
- s8: `freeze_rehearsal_writes…once`, `failed_precondition_refuses…`, `dirty_worktree…`, `amend_refuses…bad_self_hash`, the `v8_refuses_*` set, `settle_bound…`, `amendment_raises…`, `production_tree…`, `missing_freeze_seam…`;
- s1: wrong-kind, bad self-hash, missing record, amendment sibling.
- Registry, lock-state and probe-identity mutations are covered only through the generic `checks` refusal, not one test each.

**4. Rehearsal-stage harvest is complete with zero refusals.** Not covered.
- My s9 and add_scrub tests harvest synthetic NOT_STARTED legs and test the refusal paths.
- None harvests a hermetic VALID leg end-to-end; the candidate's own `test_a_real_p426_leg_harvests…` does.
- The criterion itself needs the real rehearsal stage.

**5. No push; no production-code or runner changes.** Not covered by a test.
- From reading `.b2-candidate-all.diff`: no `src/*`, `mlx-serve` or M59/M61/M62/M64/inject runner files are touched. The changed non-test files are `benchmark/bench/*`, `run_tg1_probe.py`, `bench_watch.py` and `chains/c147/*`.

**Next step:** queue P1 and P2 with the final fix round, then run the strict verify and the real rehearsal for criteria 2 and 4.
