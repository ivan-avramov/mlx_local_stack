P1 — resolved  
Location: `benchmark/bench/p426_harvest.py`, `Unrecognised.records()` / `ref_records()`  
Severity: none  
Evidence: confirmed, source trace  
Problem: Fixed. Unrecognised entries publish only scrubbed source and size; references retain only `sha256_matches`.  
Concrete failure scenario: The prior digest disclosure no longer occurs.  
Proposed change: None.

P2 — resolved by v1.1 clarification  
Location: `benchmark/bench/p426_harvest.py`, `_check_references()` / `_ref()`  
Severity: none  
Evidence: confirmed, source trace  
Problem: The relaxation intentionally applies to references from any harvested record. Checks on the published referring files remain unchanged.  
Concrete failure scenario: An unknown target referenced by a manifest is listed rather than blocking, as v1.1 requires.  
Proposed change: None.

P3 — resolved  
Location: `benchmark/bench/p426_wave2.py`, `install_kept()` / `c384_check_kept()`  
Severity: none  
Evidence: confirmed, source trace  
Problem: The kept original is written to a same-directory temporary file, fsynced, installed through a non-replacing hard link, and followed by directory fsync.  
Concrete failure scenario: A crash can leave the final path absent or complete, not partially written; stale temporary files are recoverable.  
Proposed change: None.

P4 — resolved  
Location: `benchmark/bench/p426_wave2.py`, `Sequencer.host_env_final()`  
Severity: none  
Evidence: confirmed, source trace  
Problem: An existing `host_env_after_last_leg` is now overwritten on every final check, including with `[]`.  
Concrete failure scenario: A resumed run returning to baseline no longer publishes the previous stale difference.  
Proposed change: None.

P5  
Location: `benchmark/bench/p426_harvest.py`, `_check_supersession()`  
Severity: major  
Evidence: confirmed, source trace  
Problem: The link check validates the kept file’s byte hash and internal self-hash, but never verifies that `c384.superseded_sha256` equals the kept record’s `sha256`; it also does not verify `c384.superseded` names `leg.c360.json`. Thus the published supersession link can remain semantically false despite passing harvest.  
Concrete failure scenario: A sealed successor contains the correct `superseded_file_sha256` but an arbitrary `superseded_sha256`. Harvest succeeds, while `sequence.json` consumers receive a hash that does not identify the preserved original.  
Proposed change: Require `superseded == "leg.c360.json"` and compare `superseded_sha256` with the verified kept document’s `sha256`; add negative tests for both mismatches.

P6  
Location: `benchmark/bench/tests/s29_frozen/test_s29_harvest.py` and the `s29_support.make_a3` fixture used by H5 frozen tests  
Severity: major  
Evidence: confirmed, reported test execution and traced candidate behavior  
Problem: The candidate still leaves 22 frozen tests failing: 14 require the now-forbidden digest, and eight construct a committed `HARVEST.json` while expecting the leg to be treated as unharvested. This violates the acceptance criterion that the named tests pass.  
Concrete failure scenario: CI runs `s29_frozen` and fails despite the implementation following v1.1, preventing acceptance of the change.  
Proposed change: Update the 14 listing assertions to `{source, size}` and make the unharvested-a3 fixture omit its published `HARVEST.json`; then rerun the complete named suite.
