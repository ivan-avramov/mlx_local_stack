# Test-writer report, delivery 2 — S29 record-not-block, candidate 1

Candidate applied with `git apply .fe-material/candidate-1.diff` (clean; 14 files). Frozen files verified before and unchanged:
`shasum -a 256 -c .fe-material/FROZEN.sha256` → 7 × OK. Nothing committed, nothing edited in the frozen directory.

## 1. Frozen tests on the candidate

Command: `../fe_test.sh stack bench/tests/s29_frozen --tb=no`
Summary line, verbatim: `1 failed, 71 passed in 23.77s` (baseline: `52 failed, 20 passed in 11.32s`).

Per test: baseline → candidate. All FIX/NEW tests that failed on the baseline now pass except one; all 20 baseline passes still pass.

| file | tests | baseline | candidate |
|---|---|---|---|
| `test_s29_host_sequencer.py` | 17 | 12 fail / 5 pass | 17 pass |
| `test_s29_host_positives.py` | 9 | 7 fail / 2 pass | 9 pass |
| `test_s29_h5_rederive.py` | 12 | 11 fail / 1 pass | 12 pass |
| `test_s29_harvest.py` | 31 | 22 fail / 9 pass | 30 pass, **1 fail** |
| `test_s29_oracles.py` | 3 | 3 pass | 3 pass |

(the individual test names and their baseline outcomes are in `testwriter-1-report.md`; every one of them is as listed there for the
baseline and passes on the candidate except the one below.)

### The one failure
`test_s29_harvest.py::test_fix_p6b_a_path_that_names_the_operator_account_is_scrubbed_in_the_listing` →
`HarvestError: HARVEST.json: quarantined or not portable` (`p426_harvest.py:1142`).
**Verdict: the candidate is (mildly) wrong; the test is not over-specific, but it is an edge I flagged as an assumption.**
Evidence: `Unrecognised.records()` (`p426_harvest.py:~570`) writes `source` verbatim (`leg:b2opuser/notes.dat`); the harvest's own gate
then finds the account name in `HARVEST.json`'s body and refuses the whole harvest. The spec says the listed path is "in portable
form"; the candidate does not run it through `scrub.text` (it relies on the final gate to catch it). Effect: fail-closed, nothing
leaks, but an unrecognised file under a directory named after the account turns P6b back into a whole-leg refusal, the very failure
P6b removes. One-line fix: `source=scrub.text(source)` (or the scrubbed form) when listing. Rarity is high (a directory named after
the account inside a leg root / run dir), so I class it as a small fix, not a blocker.

## 2. In-scope suite
Command: `../fe_test.sh stack -q <contents of .fe-material/SCOPE_TESTS> bench/tests/test_s29_impl_sequencer.py
bench/tests/test_s29_impl_harvest.py bench/tests/test_s29_impl_positives.py --tb=short` (candidate applied; output kept by the harness).

**The runner printed no final `N passed / M failed` line for this run** (same as the baseline file, which also ends with `rc=1 wall=…`
and no count line). I therefore give counts reconstructed from the progress lines (72 tests per full line), not a verbatim summary:
- baseline (`.fe-material/baseline-scope.txt`): 55 full lines + 34 = **3994 tests**, 2 failed (`test_s27_fe_r1.py::test_x10_…`,
  `test_s26_positives.py::…absolute_home_path`).
- candidate: 56 full lines + 1 = **4033 tests**, **1 failed**: `s26_frozen/test_s26_positives.py::test_fix_an_exception_message_never_carries_the_absolute_home_path`
  (the environment-dependent baseline failure: the temp host's bin-dir paths in the record lie under the home directory; same assertion text).
- Difference +39 tests = the three new `test_s29_impl_*` modules (I did not count them individually; the arithmetic is consistent,
  not proven). Same list of modules ran (same command plus the three).
- `test_x10_…` (order-dependent on the baseline) did not fail on the candidate.
- **No test that passed on the baseline fails on the candidate** (the only candidate failure is one of the two baseline failures).
- The `FAILED` list in the output holds that single test; I did not see any error/skip lines.
Limitation: counts by progress-line arithmetic; if exact counts matter, re-run with `-rA` or a runner that prints the summary.

## 3. Review of the candidate

Read: the whole diff of `p426_harvest.py`, `p426_wave2.py`, and the changed existing tests. Items marked (read) were judged by reading,
not by a probe test.

### Conforms to the spec (confirmed by the frozen tests)
H1 (before-diff logged, recorded on the entry, launch proceeds), H2 (`leg.json` carries `host_env_before` / `host_env_during` in separate
fields; state/reason/class from `classify_leg`), H3 (start / final / exception record + log, `after_leg` no longer stops), H4
(`host_env_changes`, no problem, v8 accepts), H5 (re-derivation only for unharvested, host-only, no-prior; original kept; consumers see the
new state without edits to freeze / signals / verify), P6a (`.marker` only directly in `<lang>__<item>.grades/seq-NNNN/`, scrubbed and gated),
P6b (listing, never copied, references listed, other refusals intact).

### Findings
1. **Harvest committed, `harvested` not yet saved, then H5 (read).** `Sequencer.harvest` saves the `harvested` entry after the harvest
   commits (`p426_wave2.py` `harvest()`). If the process dies between the harvest's commit rename and that save, a resume sees an
   unharvested INVALID host leg, `c384_supersede` rewrites `leg.json` (now VALID), and the re-harvest returns the already committed
   `HARVEST.json` (`_verified`, `p426_harvest.py:~975`, checks only the published copies, not the source), whose `state` is INVALID and
   whose `leg.json` entry has the OLD sha256. Result: published record says INVALID / old `leg.json`, sequence says VALID. Narrow window (not the
   a3: its harvest was refused, nothing committed), pre-existing idempotence rule, but H5 is the first thing that changes a source after a
   possible commit. Fix: in `c384_supersede`, also refuse / log-and-leave when `<main>/…/<attempt>/HARVEST.json` exists (ops seam
   `harvest_path`), or have `_verified` compare the source `leg.json` sha256.
2. **The supersession link is written but never checked downstream (read).** `leg.json.c384.superseded_file_sha256` names the kept file; the
   harvest only self-hash-checks `leg.c360.json` (`_is_immutable`) and publishes both; `p426_verify` / `p426_signals` do not read `c384`. A
   `leg.json` that claims a supersession of a different or missing `leg.c360.json` passes everything. `c384_check_kept` checks the pair only
   at supersession time and only while `entry["c384"]` is unset. Suggested: a harvest check that, when `leg.json` has a `c384` block, the
   `leg.c360.json` file exists and hashes to `superseded_file_sha256` (refusal otherwise); it is a small addition in `_check_references`.
   A tampered kept file is caught only on resume before the sequence is synced (`c384_check_kept` → Stop rc 1) — tested by the
   implementer.
3. **P6b: sha256 of an unscanned file is published.** Unchanged from my delivery-1 note: `Unrecognised.records()` hashes bytes the gate never
   read. For a low-entropy secret the digest is guessable. Mitigation options: scan the file with the gate (not copy, still refuse on a
   hit), or list size only. Spec says size + sha256 explicitly, so this is a spec-level decision for the designer, not a candidate defect.
4. **A reference whose recorded digest does not match an unrecognised file is listed, not refused** (`_ref`, `sha256_matches: false`). The
   spec says references are listed; but for recognised files a mismatch is a refusal ("changed after its record was written"). A row that
   names digest X for a file that is now Y passes silently. Consider refusing on `sha256_matches is False` (the file cannot be shown to be
   the one the row used) or at least logging it as UNRECOGNISED reference mismatch (the CLI line exists; the sequencer logs `notes`).
5. **A loose file inside a model's `.final_tree` is now unrecognised-not-copied** instead of refusing (the changed test
   `test_a_final_tree_under_the_leg_root_follows_the_same_rule`). A file in a final tree that is not in `objects/` or the manifest is an
   integrity anomaly of the harvested artifact, not a grader by-product. Spec-wise it is within P6b ("a regular file no rule matches"), but I
   would keep the refusal inside `*.final_tree` (one condition in `_inventory`). Designer's call.
6. **`host_env_before: []` for the re-derived a3 is inferred**, not recorded (`c384.host_env_before_basis` says so). Honest and labelled; the
   spec's "(a) what differed from the baseline at launch" cannot be known for it. Fine.
7. **`host_env_during` of a re-derived leg is `reason.split("; ")`** (`c360_changes`). Correct while `diff()` never emits `"; "`; the verbatim
   reason is also kept in `c384.superseded_reason`. Acceptable.
8. **Existing-test edits that weaken coverage (read).** `test_fix_the_kv_lever_sequencer_guards_the_host_too` now asserts
   `pytest.raises(KeyError, match="n16_worktree")` — it pins a fixture deficiency, so it no longer exercises the kv resume path past the
   launch checks. Better: build the kv v8 with its worktree keys, or assert the log/record lines and drop the launch. The p586 / b2 dry-run
   tests were switched from an unmatched file to a symlink as the problem trigger, which is faithful. The remaining listed edits are consistent
   with the spec (they pin the old refusal).
9. **Nits:** `latest =(self.entries(...)` and `done =latest[...]` in `process()` (missing space after `=`, `p426_wave2.py` ~1757 / ~1771).
   `host_env_events` grows by one entry per resume with a diff and is published with `sequence.json` (acceptable; bounded by the number of resumes).
10. **Crash windows of H5 itself (read, and tested by the implementer):** kept file written but `leg.json` not replaced → redone (equal bytes
    accepted); `leg.json` replaced but sequence not saved → synced from the superseding record after checking the kept file; a foreign
    `leg.c360.json` → Stop rc 1, never overwritten. The `atomic_text` replace is atomic. Missing: the window in finding 1, and no check that
    `leg.c360.json` is not a symlink pointing at the right bytes (`c384_check_kept` does reject symlinks: `os.path.islink` → Stop; fine).
11. **Consumers that recorded `leg.json`'s sha256 earlier (read):** `p426_freeze` records `leg_sha256` of a leg in pair dossiers / rechecks only for
    selected VALID legs; an INVALID unharvested leg has none. A leg that re-derives to VALID after a dossier would have been built cannot
    happen (dossiers need a harvested VALID attempt). `harvested` legs are left as recorded. So no recorded sha is invalidated by H5
    today; the risk would appear only if a later feature records `leg.json` shas of INVALID legs.

### Deviations from the spec
- None that contradict a "must". Where the spec left a mechanism free, the choices are: leg record rewritten and the original kept as
  `leg.c360.json` (spec: "original sealed `leg.json` kept byte-identical and harvested" — met: byte-identical, self-hash checked,
  published to `main`; the *path* `leg.json` now holds the successor, which the spec's "the record every consumer reads for the state
  shows the new state" requires); unreadable / tampered run baseline still stops (matches spec: sealed records stay verifiable).
- P6b path-portability is incomplete (the one failing frozen test).
- The spec's "(logged)" for unrecognised files is met by the CLI `UNRECOGNISED:` lines and `Sequencer.harvest` logging `notes`.

## 4. Verdict
**Fix then merge.** The candidate meets H1–H5, P6a and P6b on every frozen test but one, and the scope suite shows no regression.
Fixes, in order of weight:
1. (finding 1) Close the H5 / committed-harvest window: refuse or leave as recorded when the attempt's `HARVEST.json` already exists in
   `main`, or make the idempotent re-harvest compare the source `leg.json`. Add a test.
2. (finding 2) Have the harvest check a `c384` block in `leg.json` against `leg.c360.json` (exists, hash = `superseded_file_sha256`, itself
   self-hashed); refuse otherwise. Add a test.
3. (frozen failure) Scrub the `source` of each unrecognised-file record (and reference) before listing; the frozen test then passes.
4. (finding 8) Replace the `KeyError('n16_worktree')` assertion in `test_fix_the_kv_lever_sequencer_guards_the_host_too` with a real kv v8
   (or assert the recorded/logged difference only).
5. Designer's calls, not defects: finding 3 (digest of an unscanned file), 4 (digest mismatch on an unrecognised reference listed, not
   refused), 5 (loose file in a `.final_tree`). My recommendation: keep the refusal for 5 and for 4, decide 3 explicitly in the spec.
6. Nits (finding 9).
Frozen tests: none is over-specific by evidence; the single failure is the candidate's (item 3). No frozen test needs editing.
