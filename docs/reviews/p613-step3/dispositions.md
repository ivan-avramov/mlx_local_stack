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
