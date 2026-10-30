# P426 B2 fix round 5 — designer verification (C256: no fourth review round)

Candidate: scratch `1fc5a2d1` (fix5 on fix4 `608a9d47`), implementer session `bc1647f9-4024-42cb-9edb-d850dd5d900b` (Claude Sonnet 5.5),
brief `b2/briefs/fix5.md` = the five items open after strict verify round 3 (`strict-verify.dispositions.md` R3-1 … R3-5), spec §16.8
"after the strict verify round 3, C256". Report: `fix5.implementer-report.md`.

## Method

1. Read the production diff `608a9d47..1fc5a2d1` (`p426_wave2.py`, `p426_freeze.py`, `p426_harvest.py`) against each item and the pin.
2. Mutation, whole round: the three production files reset to `608a9d47`, the fix5 tests kept → every non-guard fix5 test must fail.
3. Mutation, targeted: only the amendment re-verification (`verify_amendment` → `reverify_recorded_dossier`) removed → a test must fail.
4. The independent frozen set (test-writer delivery 3i, amended to fix4 + fix5) and the full suite on the clean final copy.

## Per item

| Item | Diff read | Whole-round mutation | Verdict |
|---|---|---|---|
| R3-1 republication / amendment re-verify | `reverify_recorded_dossier` recomputes problems / differences / verdict from the current receipts and runs `verify_dossier`; called before every republication and by `verify_amendment` (PASS required) | 3 / 4 red (2 makeup variants, republication-alone); guard green | Resolved. `test_1_the_amendment_check_needs_the_freshly_verified_dossier_not_only_its_file_hash` passes on the pre-fix code too (a weak test); the targeted mutation (step 3) turns `…makeup_refuse_publishing_nothing[published]` red, so the path is covered. |
| R3-2 ready record for every ledger entry | `leg_items_problems` and `_check_references` require `items/<slot>.ready.json`, sealed, and `ready_sha256` = its self-hash, for rows and DNFs | 5 / 5 red; guard green | Resolved. |
| R3-3 staging | `lexists` refusal, `O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW`, own stages removed on failure, `lstat` S_ISREG after rename | 4 / 4 red; guard green | Resolved. The rename itself keeps a theoretical race; the post-rename check detects, cannot prevent (stated by the implementer; acceptable on a single-operator box). |
| R3-4 exit 4 | `run_files_failed` flag + exit-path failure → rc 4; the STOP line stays in the log | 1 / 1 red; 2 guards green | Resolved. |
| R3-5 credential sources | `frozen_env_files` reads `{off,on}_worktree` of `v8_base.json` (rehearsal: the manifest); `build_box_ops` | 3 / 3 red | Resolved. An unreadable record yields `[]`, but it cannot reach a publication: the `Sequencer` constructor refuses an unreadable `v8_base.json` / manifest before any run or publication (`p426_wave2.py` 347–352). No change. |

## Suites

- Implementer: 1359 passed (B2 + chain + gate suites) and 1595 passed, 1 skipped (adjacent suites).
- Frozen set (delivery 3i) on `1fc5a2d1`: 525 passed, 2 failed — the two baseline-only `test_b2_frozen_s0_support.py` checks, by design (they pass on the baseline).
- Full suite on the final copy: see the B2 Accept record.

## Open, for the operator (not defects)

- Delivery 3i could not test three seams the spec does not pin (`.env` source hand-off to `ops.publish_*`, `--rerun-reason` scanning, the post-rename check); the implementer's `test_b2_fix5.py` covers the first two on the candidate's own seams.
- Review coverage: Claude Sonnet read only the harvest / secrets / reconcile parts in all three rounds; sequencer, locks, hooks and receipt had two readers (sol, glm). See the B2 Accept table (P552).
