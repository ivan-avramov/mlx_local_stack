# Test-writer report, delivery 4 — candidate 2

Candidate 1 reversed (`git apply -R`), candidate 2 applied; `git status` shows only the candidate's files (11 modified under
`benchmark/…` incl. tests, the amended spec, 3 new `test_s29_impl_*`), plus `.fe-material/`, `.venv-bench` (runner artefact) and
`benchmark/bench/tests/s29_frozen/`. Frozen hashes: 8 × OK (`shasum -a 256 -c .fe-material/FROZEN.sha256`). No frozen file edited.

## 1. Frozen tests on candidate 2
`../fe_test.sh stack bench/tests/s29_frozen --tb=no` → `87 passed in 12.01s` (also run with `-rA --tb=short`: no F, no E).
Candidate 1 had 24 failures on the same 87; baseline `67 failed, 20 passed`. All 24 are fixed: the 15 digest-in-listing, the 4
scrubbed-path refusals, committed-harvest window, atomic kept install, the two link-check refusals, H3b.

## 2. In-scope suite
Same list as before (`.fe-material/SCOPE_TESTS` + the three `test_s29_impl_*.py`), `--junitxml` to `tw/scratch/scope2.xml`.
Exact counts from the junit root element: `tests="4047" failures="1" errors="0" skipped="10"`, time 1710 s.
- Failure: `s26_frozen/test_s26_positives.py::test_fix_an_exception_message_never_carries_the_absolute_home_path` — the known,
  environment-dependent baseline failure (temp host paths under the home directory).
- Baseline (`.fe-material/baseline-scope.txt`, no junit; count reconstructed from the progress lines): 3994 tests, 2 failed (that same
  test and `test_s27_fe_r1.py::test_x10_…`, order-dependent). Candidate 2 − baseline = +53 tests = the implementer's 53 `test_s29_impl_*`
  tests (their report: 53), so the same tests ran. Skips: 10 on the candidate; the baseline progress shows skips on 2 lines, its exact
  number is not recorded, so I cannot say the 10 are unchanged.
- **No test that passed on the baseline fails on candidate 2.** `test_x10_…` passed this time (order-dependent on the baseline).

## 3. Adopted defects: coverage
| defect | frozen test that reproduces it | outcome |
|---|---|---|
| 1 P6b: no digest, scrubbed paths | `test_s29_v11.py::…no_digest_of_the_files_bytes`, `…path_the_scrub_would_change…[leg,evidence,run]`, every `listing()` test, `test_s29_harvest.py::…account_is_scrubbed…` | pass (failed on cand. 1) |
| 2 H5 committed-harvest window | `test_s29_v11.py::…harvest_is_published_but_not_recorded…` (+ control) | pass |
| 3 atomic kept original | `test_s29_v11.py::…installed_by_rename_and_a_failed_install_changes_nothing` (candidate uses `os.link`, accepted by the test) | pass |
| 4 harvest supersession link check | `test_s29_v11.py::…refuses_a_c384_leg_json_whose_kept_original_is_missing_differs_or_is_a_link[3]` + positive control | pass |
| 5 H3b | `test_s29_v11.py::test_fix_h3b_…` | pass |
| 6 kv test | not in the frozen set; by inspection (`s26_frozen/test_s26_sequencer.py:330-355`): `process` is stubbed to record the first leg reached; the `KeyError` pin is gone; log, `host_env_events` and no-STOP assertions kept. Weaker than a real kv run (it stops at the first leg), but it now proves the host check no longer stops the kv resume | accepted |
| 7 nits | by inspection (`latest = (…`, `done = latest…` fixed) | ok |
No new test written: every adopted defect is already reproduced by a frozen test, and the extra cases the implementer added
(`c384` not a dict, no `superseded_file_sha256`, crash after the link, scrubbed reference record) I read and found sound.

## 4. Review of candidate 2's changes since candidate 1
- `p426_harvest.py:841-863` `_check_supersession`: requires a dict block with a string `superseded_file_sha256`, `leg:leg.c360.json` in the inventory as a `main` regular file (symlinks are refused earlier by the inventory), bytes hashing to the recorded value, and a valid self-hash. Called before the chain checks. Correct. Note it reads the file with `_read_regular` (no follow). It does NOT check that the kept original's recorded `sha256` equals `superseded_sha256` (the self-hash value in `leg.json.c384`): two different hashes name the same file (bytes hash vs canonical self-hash). A kept file with the right bytes has both by construction, so this is redundant, not a hole.
- `p426_wave2.py:78-100` `install_kept`: fsynced same-directory temp, exclusive `os.link`, unlink temp, fsync of the directory. Atomic and non-replacing; a crash leaves the final path absent or complete. Hazards: (a) a crash between link and unlink leaves `.leg.c360.json.tmp`; if the leg is harvested before a resume cleans it, the harvest lists it as unrecognised (P6b) and does not refuse (implementer notes this): harmless, publishes a listing line; (b) `os.link` needs a filesystem with hard links (APFS/ext4: yes); (c) `FileExistsError` is swallowed and the caller compares the existing file; a different existing file stops rc 1 (kept from candidate 1).
- `Sequencer.c384_supersede` committed-harvest check: `os.path.lexists(ops.harvest_path(name)/"HARVEST.json")` — existence only, fail-closed; any stale file at that path (even an unverified one) blocks the re-derivation and sends the leg to the operator-decision stop. Acceptable and consistent with v1.1; it relies on the `harvest_path` seam being in `SEAMS` (it is).
- `host_env_final` (H3b): `host_env_after_last_leg` is rewritten on every final check once it exists, `[]` included; a run that never differed keeps no field. Correct and the invariants still hold; side effect: a field that is `[]` after a clean final check hides, in that field, the earlier difference (kept in `host_env_events` and the logs).
- `Unrecognised.records(scrub)` / `ref_records(scrub)`: `{source, size}` and `{reference, source, sha256_matches}`; the recorded digest is compared, only the boolean is stored; the listing no longer hashes unscanned bytes (`_stream_sha` is no longer used for them). Source and reference are scrubbed, so `HARVEST.json` no longer refuses on an account-named path. I found no remaining digest of the unrecognised bytes in `HARVEST.json`, the CLI line, or the sequencer's notes.
- One residual: `sha256_matches` still leaks one bit about the unscanned file only if the row's digest is attacker-chosen (a row asserts a digest, the harvest answers true/false): negligible, and the spec asks for it.
- Declined by the implementer, as agreed: refusing on a digest mismatch, the `.final_tree` loose-file refusal, limiting the reference relaxation to rows. These remain open designer decisions from my delivery-2 findings 4 and 5; nothing in candidate 2 makes them worse.

## 5. Findings
None blocking. Minor / informational:
1. `host_env_after_last_leg == []` can coexist with `host_env_events` listing an earlier difference (by design; document it where readers look).
2. Leftover `.leg.c360.json.tmp` after a crash is listed as an unrecognised file if harvested before a resume (cosmetic).
3. The kv test is a stub-at-first-leg test; the kv post-launch path is still not exercised (pre-existing fixture limit).

## 6. Verdict
**Merge.** All 87 frozen tests pass; the 4047-test scope run has only the known environment failure; every adopted defect is
reproduced by a frozen test that now passes; the review of the changes since candidate 1 found no defect. Remaining open items are the
designer decisions already recorded (digest mismatch on an unrecognised reference listed rather than refused; loose file in a
`.final_tree` listed rather than refused) and the cosmetic notes in section 5. Not done by me: a real tg2 end-to-end run and a real
harvest of a sequencer-produced root (the tg1 fake root fails the real harvest on this harness for PII-path reasons), so the H5 + harvest
chain is covered by the grafted-leg tests, not by one continuous run.
