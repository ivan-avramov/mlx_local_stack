P1 — Location: `benchmark/bench/p426_harvest.py`, `Unrecognised.records()` / `harvest_wave2()`  
Severity: major  
Evidence: confirmed (source trace)  
Problem: Unrecognised files bypass `Gate.check` and `piicheck`; their size and SHA-256 are nevertheless published in `HARVEST.json`. This violates the public-record constraint and can expose low-entropy secrets or PII through guessable hashes. Tests only place credentials in recognised files, not inside the unrecognised file itself.  
Concrete failure scenario: `execute.unknown` contains an employee identifier or short secret. Harvest succeeds and publishes its digest, whereas identical content in a recognised file is quarantined.  
Proposed change: scan every unrecognised file with the existing credential/PII gate before listing it; retain the no-copy behavior, but refuse under the unchanged scrub/PII rules.

P2 — Location: `benchmark/bench/p426_harvest.py`, `_check_references()` calls to `_ref(..., unrecognised=...)`  
Severity: major  
Evidence: confirmed (source trace)  
Problem: The candidate extends the row-reference relaxation to references from manifests and `p426_dnf` sidecars. This is beyond P6b and bypasses existing transitive evidence checks: a published main record may reference an absent, unverified file while harvest reports success.  
Concrete failure scenario: A recognised session manifest references `payload.bin`, which has no harvest rule. The manifest is published, `payload.bin` is merely listed, and its claimed digest may mismatch without refusal.  
Proposed change: permit unrecognised targets only from `_check_row`; keep baseline refusal behavior for manifest and sidecar references.

P3 — Location: `benchmark/bench/p426_wave2.py`, `Sequencer.c384_check_kept()`  
Severity: major  
Evidence: confirmed (source trace)  
Problem: `leg.c360.json` is created directly at its final path. A stop, process kill, or write failure after `O_EXCL` creation but before the complete write leaves a partial file. Every resume then permanently stops because the file does not match, and the no-hand-edit rule provides no recovery. Tests cover only a fully written side file.  
Concrete failure scenario: The sequencer is interrupted while writing the preserved original. On restart, `c384_check_kept` reports that `leg.c360.json` is foreign and the benchmark cannot resume.  
Proposed change: write and fsync a same-directory temporary file, atomically install it without replacement (for example with an exclusive hard link), then fsync the directory.

P4 — Location: `benchmark/bench/p426_wave2.py`, `Sequencer.host_env_final()`  
Severity: minor  
Evidence: confirmed (source trace)  
Problem: `host_env_after_last_leg` is updated only for a non-empty diff, so a resumed run that returns to the baseline retains a stale earlier final-host difference. Tests do not cover changed → baseline across resumes.  
Concrete failure scenario: A `--through` run records an added JDK; it is removed before resume, and later legs finish on the baseline. Published `sequence.json` still claims the JDK differed after the last leg.  
Proposed change: overwrite the final-host field on every final check, including `[]`, or record timestamped final-check events.
