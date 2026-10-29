# P537 / P527 fork harness change — code review round 1 of 3: opinion + verify, dispositions

Material: `../mlx-vlm` `dev/p369_phase2/orchestrate.py` + `mlx_vlm/tests/test_p369_phase2_orchestrate.py`, `1cce312f..cde6299f`
(opinion), repair `cde6299f..bca26e19` (verify); later commits `5ffa5fa3` (operator-approved scope test), `3867a425` (verify fixes).
Context: `briefed` (the diff + the four harness files as `.txt`). Budget: one opinion, one verify (review-panel), both used.

| Member | Runtime | Model (reported) | Session | Context | Opinion | Verify |
|---|---|---|---|---|---|---|
| sol | cursor-agent 2026.10.22 | `gpt-5.6-sol-high` (requested; not reported) | not reported | briefed, user instructions unconfirmed | 3 findings | fresh session (cursor-agent cannot resume): NOTHING OF SUBSTANCE |
| glm | cursor-agent 2026.10.22 | `glm-5.2-high` (requested; not reported) | not reported | briefed, user instructions unconfirmed | 3 findings + 1 scope request | fresh session: 2 minor |
| sonnet | claude 2.1.312 | `claude-sonnet-5-5` | `2f3e6e19-b067-4a6e-aee2-cd9e0e06dfed` (resumed for verify) | briefed, user instructions suppressed; same vendor as the driver | 6 findings | 2 minor |

## Opinion ledger

| # | Finding | Raised by | Disposition |
|---|---|---|---|
| 1 | E2's per-threshold straddle requests used the `T − 64` prompts, not the prompt E1c accepted at 65 / 66 | sol (major), sonnet (major) | Adopted: `accepted_prompts[pick]`, `e2_prompts(sized, accepted)` in `run_pick`. |
| 2 | A re-size without an exact prompt raised out of E1c (HARNESS_ERROR, attempts lost) | sonnet (major), glm (minor, hypothesis) | Adopted: re-sizes are `strict=False`; the cell is parked for the next offset; none sizable → INCOMPLETE with `no exact prompt at offset N`; `size_failures` recorded. |
| 3 | Re-sizing overwrote the `size` job directory | sonnet (minor) | Adopted: `size-o<offset>`. |
| 4 | The P527 test tested only the helper | sol, glm, sonnet (minor) | Adopted: a `Campaign.prepare()` test (green before the fix: the wiring was right; kept as a guard). |
| 5 | The retry test did not check the re-sized prompt is sent | sonnet (minor) | Adopted. |
| 6 | The projection omits retries | sol (major), sonnet (minor) | Adapted: the docstring states retries are not projected; no wall cap (C184 / C194); a schedule-aware projection declined as beyond the request. |
| 7 | `n >= 65` does not track the offset | glm (minor) | Declined: `straddle` implies the floor at every offset. |
| 8 | Scope: a multi-cell test with cells accepted at different offsets + the short cell | glm | Operator approved ("add the glm-suggested test"): `5ffa5fa3`, mutation-checked. |

## Verify ledger

All eight resolved or disposed as above (all three members). New:

| # | Finding | Raised by | Disposition |
|---|---|---|---|
| N1 | The initial `T − 64` sizing is still strict (an unsizable threshold is a HARNESS_ERROR, not INCOMPLETE) | glm (minor) | Declined: a non-strict first sizing would drop the threshold from E1c and let the pick pass without it; the pre-C252 behaviour stands. Disposition 2's wording narrowed to re-sizes. |
| N2 | The E7 test's offset-65 / 66 attempts carry the offset-64 `prompt_end` | glm (minor) | Adopted (`3867a425`). |
| A | `run_pick` → `e2` hand-off untested | sonnet (minor) | Adopted: `test_run_pick_hands_e2_the_prompts_e1c_accepted` (mutation-checked). |
| B | The parks test had a no-op assertion | sonnet (minor) | Adopted: asserts attempt offsets and that no attempt ran at the unsizable offset. |

Final: 511 passed, 1 skipped (`mlx_vlm/tests/test_p369_phase2_*.py`); production tree (`mlx_vlm/` excluding tests) unchanged since `1cce312f`.
