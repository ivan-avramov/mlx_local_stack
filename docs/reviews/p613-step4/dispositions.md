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
