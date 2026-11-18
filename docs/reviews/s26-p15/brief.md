Cold read, round 1 of 3. Read-only. B8 (`benchmark/bench/p426_verify.py`, the pair verifier of a benchmark's Wave 2) refused the first
real run after a labelled rerun: "wave2/run/sequence.json names 2 pair records for pilot (need exactly 1)". The sequencer
(`benchmark/bench/p426_wave2.py`) appends a pair record per attempt; the real run reran the X pilot (attempt a1 was speed-invalid
after a power dropout; the pilot gate used a2), so sequence.json holds pilot records (n16.a1, x.a1) and (n16.a1, x.a2); legs list
x-pilot attempts 1 and 2, both VALID. The fix: among a session's records, take the one whose attempts are, per arm, the
highest-numbered attempt of that leg in sequence.json's legs; exactly one must match, else refuse; others are reported as
`superseded` (key emitted only when non-empty, so outputs without reruns are byte-identical — a golden pins them).
Files here: fix.diff, test_s26_p15_rerun_pairs.py. Context in the repo: p426_verify.py `_sequence_pair*`, `verify_a7`, `verify_a7_kv`,
`_sequence_leg_reasons`; p426_wave2.py `Sequencer` (how `--rerun` creates attempts and pair records, `next_attempt`, the pilot gate).
Question: can this ever pick a pair the sequencer did NOT gate on or accept (e.g. a later attempt that was INVALID, a rerun of only
the first arm, a make-up), or accept a session whose latest attempt has no record? Does the mtp lever path (`verify_a7`) change
behaviour? Numbered findings with severity (blocker / major / minor), file:line, a concrete scenario; "no findings" if none.
Do not modify any file.
