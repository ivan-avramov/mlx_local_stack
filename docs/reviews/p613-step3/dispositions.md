# P613 step 3 (the panel) — findings and dispositions (designer), 2026-11-04

Sources: panel opinion (GPT-5.6 Sol High P1–P9; GLM 5.2 F1–F4, H1, S1), implementer ambiguity notes, test-writer delivery 2 (pending
at first write). Sol ids are its own numbering.

| Finding | Severity | Disposition | Why |
|---|---|---|---|
| E1 / Sol P5 / GLM F1 `--panel` required | major | adopted (fix 1) | erratum E1: optional; absent → step-2 record byte-identical; present + missing FROZEN.json → refusal |
| E3 / Sol P6 / GLM F2 A1 eligibility 100 vs 96 | minor/major | adopted (fix 2) | erratum E3: A1 eligible = both correct (96, all identical), 4 "not both correct" counted; Wave 1 eligible identical 162 |
| Sol P1 FROZEN.json unsealed (lengths editable after verdicts) | major | adopted (fix 3) | every sealed / cursor verdict records the FROZEN.json sha; ingest and the sheet refuse a verdict bound to another FROZEN sha; FROZEN cross-checked against manifest.jsonl (items, slots, judges) |
| Sol P2 verdict-supplied provenance trusted; pre-sealed verdicts skipped | major | adopted (fix 4) | judge label / family / model / client / prompt sha come from FROZEN's judge list and the batch directory; a verdict whose fields disagree is rejected (counted); bare verdicts are always normalised |
| Sol P3 a failed packet is re-called on the next invocation | major | adopted (fix 5) | an attempt marker is written before each call; an attempted packet is never called again (retries 0 across invocations) |
| Sol P4 lengths from the raw diff; `strip_model_names` silently rewrites judged text | major | adopted (fix 6) | packets carry the exact diff (no rewriting); a leak refuses the export; judged length = characters of the rendered solution text in the packet |
| Sol P7 `--b8` / `--universe` arbitrary files | major | adapted (fix 7) | the production CLI requires the committed repository paths and verifies their bytes equal `git show HEAD:<path>` (clean); the low-level functions stay injectable |
| Sol P8 malformed Claude verdict crashes sealing; invalid choice sealed as null | major | adopted (fix 8) | each file handled alone; malformed / invalid → a permanent failed marker, counted missing |
| Sol P9 `a7_packet` public signature | minor | adopted (fix 9) | exact contract signature; cached context in a private helper |
| GLM F4 `missing_verdicts` can go negative on duplicates | minor | adopted (fix 10) | per item: min(valid, planned per item); duplicates counted separately |
| GLM H1 freeze hashes every file in out_dir | minor | adopted (fix 11) | the frozen set = the packets, manifest.jsonl and README_JUDGE.md, listed explicitly; other files ignored |
| GLM F3 frozen tests encode pre-errata behaviour (`test_panel_option_is_required`, 166) | test defect | to the test-writer | amend to E1 / E3 |
| GLM S1 a future non-identical Wave 1 pair needs a packet type | scope note | recorded | refusal is the safe behaviour today |
| Implementer P2 events bound through HARVEST | — | = erratum E2 | |
| Implementer P4 identical A7 pairs in the permutation vector at 0 | — | kept | spec §4.5: C217-identical pairs score 0.5 and stay in the test |
| TW d2 A4 absent from §4.5 | gap | adopted (fix 12) | spec §4.5: A4 draw distribution + panel scores, descriptive, never tested (here: 6 / 6 identical → 0.5, not judged) |
| TW d2 W1, W2, R1–R5, the E1 test, golden 166 | test defects | to the test-writer (d3) | candidate matches the real data (TW evidence copy: 102 / 117 pass) |
| TW d2 R6 model-name leak variant does not refuse | — | resolved by fix 6 | the export must refuse, not redact |
| TW d2 R6 `a7_packet` on an identical item | test over-reads the contract | to the test-writer (d3): drop | the contract does not require a refusal there |

## After fix round 1 (test-writer delivery 4: 130 / 134 + 686 regression; verdict merge)

| Finding | Severity | Disposition | Why |
|---|---|---|---|
| TW d4 4 failing tests (pre-sealed forged verdict checks the file not the marker; `a7_select` `_ctx` beyond fix 9; A4 table-row markup; "not both correct" wording) | test defects | to the test-writer (d5) | candidate values verified by the test-writer |
| TW d4 `len_on` / `len_off` editable between export and the first verdict | minor | adapted (procedure) | the frozen panel directory is COMMITTED before any judge runs; git fixes the bytes the verdicts bind to |
| TW d4 `a7-export` runner needs `MLX_BENCH_RESULTS` (fix 2 regrades A1) | — | test-runner amendment (allowed in d4) | |
| impl P3 the shared `seal_verdicts` still crashes on malformed JSON (other axes) | out of scope | residual → own proposal later | step 3 uses its own A7 seal path |
| impl P5 `provenance.json` rewritten per run; `a7-seal` accepts a cursor label | minor | residual | |

## Verify round (GPT-5.6 Sol High, GLM 5.2; both valid)

GLM: all 12 fixes resolved; F1–F3 = the d5 test defects. Sol: fixes resolved except as below.

| Finding | Severity | Disposition | Why |
|---|---|---|---|
| Sol v-P1 `a7-seal` seals bare verdicts under ANY frozen judge (incl. the Cursor one) | major | proposed fix round 2 (operator) | a false second-family verdict defeats C206 / C207; `a7-seal` must accept only the `claude-code:blind-judge` client and normalise `client_version` |
| Sol v-P2 A1 eligibility uses strict items | minor | proposed fix round 2 | AGENTS: the panel judges execution-PASSING outputs (lenient correctness); today strict = lenient (96) |
| Sol v-P3 A4 eligibility checks only `score == 1.0` | minor | proposed fix round 2 | the strict-draw predicate (+ `budget_hit` false, `finish_reason` stop), consistent with the sheet's A4 |
| Sol v-P4 / GLM F1 `a7_select` `_ctx` | minor | proposed fix round 2 | the contract signature, as fix 9 did for `a7_packet` |
| Sol v-P5 / GLM F2–F3 frozen-test defects | test | in d5 | |
| Sol v-P6 `provenance.json` rewritten on an all-skipped run | minor | residual | per-verdict provenance is correct; scoring unaffected |
| GLM note `test_fix10` exercises the refusal path, not the cap | test weakness | to the test-writer with round 2 | |

Post-Accept (designer, behaviour-preserving; the naming / PII hooks refused the commit): `p426_panel._a7_leaks` local variable renamed to `lowered`;
`test_p613s3_golden.py` the `qwen3.8` leak-scan needle line carries `allow-shorthand`; `test_p613s3_export.py` the fake home-path line
carries `allow-pii-pattern`. Suites before the edit: 826 passed; the three touched files re-run after it.
