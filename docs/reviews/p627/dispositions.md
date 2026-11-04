# P627 — findings and dispositions (designer), 2026-11-04

| Finding | Severity | Disposition | Why |
|---|---|---|---|
| TW frozen `test_the_key_is_present_when_an_earlier_step_fails` fails on the candidate | minor | adopted (fix 1) | spec "always present": `baseline_skips_ran` and `baseline_skips_absent` are set to `[]` when the receipt is created, filled after the skip check |
| TW frozen `test_a_live_file_named_after_the_class_does_not_allow_the_entry` | test defect (amended in d2) | superseded by F1 | the designer ruled the longest-prefix reading; the d2 review then showed the hole the original test was guarding |
| impl P3 (fork repo top = the fork clone root), P4 (dotted-part guard) | — | accepted | consistent with how fork baselines name entries; the guard only narrows |
| TW d2 F1 a live-only longer-prefix file hides a module the gated tree HAS but did not collect (probed: PASS where today fails) | major (push-safety hole, from the designer's spec) | adopted (fix 2; spec v1.1) | gated tree first: any dotted prefix that is a `.py` file in the gated tree → not absent-allowed |

## Panel opinion (GPT-5.6 Sol High P1–P5, GLM 5.2 F1–F5; on the pre-fix candidate)

| Finding | Severity | Disposition | Why |
|---|---|---|---|
| GLM F2 a live decoy shadows the gated module file | blocker | resolved by fix 2 (v1.1) | gated tree first |
| Sol P4 key not always present | minor | resolved by fix 1 | |
| Sol P1 / GLM F1 class-named file vs module file (ambiguous dotted path) | blocker (claimed) | adapted (fix 3, v1.2) | fail closed: if more than one dotted prefix is a `.py` file in the live tree, the entry is not absent-allowed |
| Sol P2 a failed / errored junit id reclassified as absent | blocker (claimed; unreachable in a real gate: a collected test means its module is in the gated tree, caught by v1.1) | adopted (fix 4, v1.2) | absent-allowed only if the id appears nowhere in the junit |
| Sol P3 / GLM F5 symlinks | major / minor | adopted (fix 5, v1.2) | the live file must be tracked at the live HEAD (git), not merely on disk; symlinks (git mode 120000) refused |
| Sol P5 / GLM F3 "absent in gated, present in live" ≠ "added later" (untracked live file; deleted then re-added) | scope request / major | adopted (fix 6, v1.2) | the file must be tracked at live HEAD and its adding commit (`git log --diff-filter=A` on live HEAD) must have the gated sha as an ancestor; else not allowed |
| GLM F4 the `-[...]` tail lists absent-allowed entries | minor | declined | C277's message stays unchanged (its tests pin it) |
