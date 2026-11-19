**Verdict: merge.** Candidate 3 passes the full suite and all 202 frozen tests, and I found no code defect.

- **Suite summary line, verbatim:** `15227 passed, 9 skipped, 1 xfailed, 2 warnings in 6513.31s (1:48:33)`. The exit code was 0.
- **Failing test ids:** none. There are no `FAILED` or `ERROR` lines in `s26-c3-suite.log`.
- **Frozen tests:** `202 passed in 363.53s (0:06:03)`. The suite total includes them.
- **Acceptance 2:** satisfied. The earlier suite had 15194 passed and 3 failed (my three defective tests); now all pass.

## Findings
- **No file-and-line defects.** The three adopted fixes behave as specified:
  - v8 now requires a 64-hex `declined_evidence.row_sha256` equal to the entry's own (`bench/p426_freeze.py`, `declined_ok`).
  - tg2's campaign-core `probe_data` includes `bench/tg2_gradle_home.py` and tg1's is unchanged (`chains/c147/run_tg2_chain.py:44-46`).
  - The guard's Stop lines carry no "operator" wording.
- **Open point (implementer's P4, not a defect).** tg2's recorded `ArmBinding.probe_data` also changes, because it is built from `CORE_SPECS["probe_data"]` (`run_tg2_chain.py:82`). Any previously recorded tg2 config will no longer match. No tg2 leg has run, so this is harmless.

## Carried over from earlier rounds
- **Real-box acceptance 3 not done:** `prefill`, `check`, and a tg2 positives run under the new rule.
- **tg1 `probe_code_sha256` rotation:** it still needs the designer's baseline-vs-candidate comparison on the real tg1 `--print-identity` (GLM R2-3). Do not apply the change to the arm worktrees while the current tg1 Wave 2 runs.
- **kv lever coverage:** the first-run baseline write and the post-leg INVALID path have no frozen test.