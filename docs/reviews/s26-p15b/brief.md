Cold read, round 1 of 3. Read-only. B8 (`benchmark/bench/p426_verify.py`) picks, after a labelled rerun, the pair record of the latest
attempts (committed earlier, S26-P15). A reviewer pointed out it never checks WHY the earlier attempt was replaced, so a clean result
could be silently replaced by a rerun (cherry-picking). This diff (S26-P15b) adds `_supersede_reasons`: a superseded record is allowed
only when, for every arm whose attempt it replaced, the replaced attempt was not clean (its leg.json state not VALID, or speed_valid
not True) AND sequence.json `reruns` (written by the sequencer's `--rerun LEG --rerun-reason`, benchmark/bench/p426_wave2.py) records a
non-empty reason for the newer attempt; otherwise the session pair gets a rule-3 reason (rejected), on both levers.
Files here: fix.diff, test_s26_p15_rerun_pairs.py. Question: can a clean result still be replaced (e.g. an INVALID rerun, a rerun of
one arm only, a make-up, a missing or unreadable leg.json, a `reruns` entry for another attempt), or can a legitimate rerun now be
refused? Does reading the superseded leg.json change B8's input set in a way a consumer (signals, panel FROZEN binding) mishandles?
Numbered findings with severity (blocker / major / minor), file:line, a concrete scenario; "no findings" if none. Do not modify any file.
