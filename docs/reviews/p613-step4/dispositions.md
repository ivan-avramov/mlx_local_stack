# P613 step 4 (divergence section + FINAL) — findings and dispositions (designer), 2026-11-04

| Finding | Severity | Disposition | Why |
|---|---|---|---|
| Sol P1 malformed / truncated `tool_use.state` read as `{}` (input `null`, output `"None"`) | major | adopted (fix 1) | a retained tool event must carry `state.input` and `state.output` (terminal status); else `RefusalError` naming the item |
| Sol P2 `_final_ready` accepts an axis whose `blocks` lack `b1` or `b2` | major | adopted (fix 2) | FINAL requires `set(blocks) == {b1, b2}` and every block accepted, for A1 / M1 / A2 / A3 / A4 |
| Sol P3 / GLM F1 the header / input prefix record the resolved full sha; the frozen golden expects the passed `b6ec7819` | contract ambiguity | adapted (fix 3) + test amendment | the full resolved sha is the unambiguous provenance (a short sha can collide later): keep `evidence_ref` = full sha and the `evidence:<full sha>:` prefix; ADD `evidence_ref_given` = the string as passed; the test-writer amends the golden |
| GLM F3 `--evidence-ref` without `--panel` yields a step-2 status on a step-4 header | minor | adopted (fix 4) | refuse `--evidence-ref` without `--panel` (rc 2, nothing written) |
| GLM F2 no test of a B8-rejected A7 session blocking FINAL | test gap | to the test-writer | |
| GLM F4 the section's position on the real sheet | test gap | to the test-writer | |
| TW d2 P1 the 11 HARVEST / unparseable tests edit HARVEST then re-run B8 — B8 rule 5 rejects the pair first (the binding is never reached) | test defect | to the test-writer | the binding refusals verified by the test-writer calling `_events` directly (9 cases raise) |
| TW d2 P2 the golden's flag helper matches the cross-wave flag text; the short vs full ref | test defect | to the test-writer | with fix 3 (`evidence_ref_given`) |
| TW d2 P3 46 / 49 `environment` items stop differing when digit runs in tool output are masked | observation | to the step-4 write-up | supports the clock / ASLR reading; the rule stays as specified |
| TW d2 P5 Pending reads "- none" when FINAL | — | accepted | the MTP call is the operator's, not a generated item |

## Verify (round 2 of 3, P633 / C289, 2026-11-04) — dispositions (designer)

Members: GPT-5.6 Sol High (`gpt-5.6-sol-high`) and GLM 5.2 (`glm-5.2-high`), `cursor-agent 2026.10.22 --mode ask`, fresh sessions (cursor-agent cannot resume), `checkout` (the fixed candidate + frozen-d3 tests; user instructions unconfirmed), both exit 0, no file modified. Raw: `verify-sol.md`, `verify-glm.md`. A verify checks the diff; it is not independent discovery. Driver rerun on the candidate: `bench/tests/p613s4` 110 passed, 2 skipped.

| Finding | Sol | GLM | Disposition |
|---|---|---|---|
| Sol P1 malformed tool state | resolved | resolved | resolved |
| Sol P2 FINAL needs b1 + b2 | resolved | resolved | resolved |
| Sol P3 / GLM F1 ref | resolved | resolved | resolved (full sha + `evidence_ref_given`) |
| GLM F2 B8-rejected A7 session | resolved | resolved | resolved |
| GLM F3 `--evidence-ref` without `--panel` | resolved | resolved | resolved |
| GLM F4 section position | resolved | resolved | resolved |
| GLM M1 `state.input` must be an object (contract: any JSON) | — | minor, confirmed | declined: stricter than the contract in the refusing direction — a non-object input stops the sheet naming the line, never misclassifies; no current event triggers it; a future one is a visible contract amendment |
| GLM M2 non-terminal `tool_use` refuses (contract: no status filter) | — | minor, confirmed | declined: same reason (refuse > misclassify; all retained events are terminal) |
| GLM M3 trailing `or "A7-s1" in text` assertion is vacuous | — | minor, confirmed (traced, `test_p613s4_fixes.py:196`) | declined for this round: the three assertions above it carry the check (`missing`, `ready`, `divergence.complete`); the test-writer flagged it in d3; frozen-test edits stay with the test-writer |

Note: Sol reports "12 error events across the 86 items" (A7 B8-accepted pairs); the implementer's 154 counts every `tool_use` in the evidence at `b6ec7819`. Different scope; not load-bearing (the golden counts reproduce).

Verdict: no blocker, no major; every round-1 finding resolved. Candidate ready for Accept.
