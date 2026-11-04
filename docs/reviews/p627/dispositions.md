# P627 — findings and dispositions (designer), 2026-11-04

| Finding | Severity | Disposition | Why |
|---|---|---|---|
| TW frozen `test_the_key_is_present_when_an_earlier_step_fails` fails on the candidate | minor | adopted (fix 1) | spec "always present": `baseline_skips_ran` and `baseline_skips_absent` are set to `[]` when the receipt is created, filled after the skip check |
| TW frozen `test_a_live_file_named_after_the_class_does_not_allow_the_entry` | test defect (amended in d2) | superseded by F1 | the designer ruled the longest-prefix reading; the d2 review then showed the hole the original test was guarding |
| impl P3 (fork repo top = the fork clone root), P4 (dotted-part guard) | — | accepted | consistent with how fork baselines name entries; the guard only narrows |
| TW d2 F1 a live-only longer-prefix file hides a module the gated tree HAS but did not collect (probed: PASS where today fails) | major (push-safety hole, from the designer's spec) | adopted (fix 2; spec v1.1) | gated tree first: any dotted prefix that is a `.py` file in the gated tree → not absent-allowed |
